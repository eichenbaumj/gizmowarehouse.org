import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { Map as MapLibreMap } from "maplibre-gl";
import { Protocol } from "pmtiles";
import "maplibre-gl/dist/maplibre-gl.css";

import { NYC_TAX_MAP_CONFIG, NycTaxMapMode } from "@/config/nycPropertyTaxMap";
import { cartoStyleUrl, cartoTransformRequest } from "@/config/basemap";
import { bldgClassLabel } from "@/lib/bldgClass";

// Format a ratio (etr / median) as a plain-language multiplier.
//   2.7  → "2.7× as much"
//   6.1  → "6× as much"
//   1.05 → "about the same"
//   0.6  → "about 60% of"
//   0.3  → "less than half of"
function fmtMultiplier(ratio: number | null | undefined): string {
  if (ratio == null || !isFinite(ratio)) return "—";
  if (ratio >= 2) return `${Math.round(ratio)}× as much as`;
  if (ratio >= 1.2) return `${ratio.toFixed(1)}× as much as`;
  if (ratio >= 0.85) return "about the same as";
  if (ratio >= 0.5) return `about ${Math.round(ratio * 100)}% of what`;
  return "less than half of what";
}

// Co-op denominator caveat fires when the parcel is a co-op type that DOF
// systematically undervalues. Conservative rule: tax_class === "2C", OR
// the building class explicitly tags walk-up co-op (C6/C7/C8).
function shouldShowCoopCaveat(taxClass?: string, bldgClass?: string): boolean {
  if ((taxClass || "").trim() === "2C") return true;
  const bc = (bldgClass || "").trim().toUpperCase();
  return bc.startsWith("C6") || bc.startsWith("C7") || bc.startsWith("C8");
}

// Class 1 cap caveat fires for Class 1 parcels paying notably less than
// half their class median — a heuristic for "the cap is doing visible work
// on this parcel." Imperfect; flagged as such in the copy.
function shouldShowCapCaveat(
  taxClass?: string,
  etr?: number,
  classMedian?: number,
): boolean {
  if (!etr || !classMedian) return false;
  const tc = (taxClass || "").trim();
  if (!tc.startsWith("1")) return false;
  return etr < 0.5 * classMedian;
}

// One-line answer to "how did DOF arrive at this market value?"
// Branches on tax class + building class. Co-op detection mirrors
// shouldShowCoopCaveat so the two stay consistent.
function mvMethodology(taxClass?: string, bldgClass?: string): string {
  if (shouldShowCoopCaveat(taxClass, bldgClass)) {
    return "stock-comparison vs. comparable rentals";
  }
  const tc = (taxClass || "").trim();
  if (tc === "2") return "DOF income approach (~2-yr RPIE lag)";
  if (tc.startsWith("2")) return "sales-comparable; capped";
  if (tc.startsWith("1")) return "sales-comparable; bill held below MV by the AV cap";
  if (tc === "4") return "DOF income capitalization";
  return "DOF estimate";
}

// True when the parcel carries any data_quality flag that the map's
// hideFlags filter excludes from paint. The polygon won't render on the
// map, but querySourceFeatures (used by the address-search flow) still
// returns it — so click/search handlers need to re-check before opening
// the detail popup, otherwise the user gets an em-dash card with no
// useful information.
function isHiddenByFlags(props?: { data_quality?: string }): boolean {
  if (!props?.data_quality) return false;
  return props.data_quality
    .split(",")
    .some((f) => NYC_TAX_MAP_CONFIG.hideFlags.includes(f.trim()));
}

// Hide parcels that aren't really "property paying property tax" — they
// are legally tax-exempt or otherwise produce misleading visual artifacts
// (e.g. a giant dark blob over Greenwood Cemetery in $/sqft mode because a
// tiny maintenance building divides into a multi-million-dollar bill).
//
// Building-class prefixes filtered out:
//   V* = vacant land
//   Z* = parks / cemeteries / public open space
//   T* = transit (MTA yards, etc.)
//   Q* = outdoor recreation (golf, beaches, marinas)
//   M* = religious (churches, mosques, synagogues)
//   W* = educational structures (schools, colleges)
//   I* = hospitals & health-care institutional
//   P* = public-sector facilities (libraries, post offices, civic)
//   Y* = selected government installations
//
// Plus: tax_class === "3" (utility special franchises like Verizon, Con Ed)
// — billed at entity level, not parcel level, ~19 parcels citywide.
//
// We DO keep abated 421-a / 485-x towers visible (they're legally taxpayers
// paying reduced amounts and are central to the post's narrative). Those
// have building class D*/R*, not the prefixes above.
const SHOWABLE_PARCEL: any = [
  "all",
  [
    "!",
    [
      "in",
      ["slice", ["coalesce", ["get", "bldg_class"], "  "], 0, 1],
      ["literal", ["V", "Z", "T", "Q", "M", "W", "I", "P", "Y"]],
    ],
  ],
  ["!=", ["coalesce", ["get", "tax_class"], ""], "3"],
  // Hide parcels that didn't join PVAD or have no usable market value.
  // Without this, those parcels render as grey polygons with em-dash
  // tooltips. The flag set is declared in NYC_TAX_MAP_CONFIG.hideFlags.
  ...NYC_TAX_MAP_CONFIG.hideFlags.map((flag) => [
    "!",
    ["in", flag, ["coalesce", ["get", "data_quality"], ""]],
  ]),
];

function registerPMTilesProtocol() {
  // Documented pmtiles 4.x + maplibre-gl integration: pass `protocol.tile`
  // (the auto-detecting shim that handles both callback-style maplibre 3
  // and Promise-style maplibre 5+).
  const p = new Protocol();
  try { maplibregl.removeProtocol("pmtiles"); } catch {}
  try { maplibregl.addProtocol("pmtiles", p.tile); } catch {}
}

interface ParcelProps {
  bbl?: string;
  bldg_class?: string;
  tax_class?: string;
  market_value?: number;
  billable_av?: number;
  tax_bill?: number;
  etr?: number;
  tax_per_sqft?: number;
  exempt_fraction?: number;
  exempt_total?: number;
  bldg_area?: number;
  units_total?: number;
  year_built?: number;
  num_floors?: number;
  data_quality?: string;
  // Per-BBL MV history snapshots from PVAD year-rows. Used to render the
  // "Up X% since 2023" line under the current MV. Suppressed for condo
  // aggregations (per-unit sums fake growth when unit count drifted).
  mv_y2023?: number;
  mv_y2026?: number;
  // Set when stage 03 aggregated multiple condo unit BBLs into the lot
  // polygon. aggregation === "condo" implies financials are summed across
  // units_aggregated unit BBLs.
  aggregation?: string;
  units_aggregated?: number;
  // From parcels-manifest (sample mode only):
  address?: string;
  borough?: string;
  _lon?: number;
  _lat?: number;
}

interface NTAProps {
  nta2020?: string;
  ntaname?: string;
  boroname?: string;
  n_parcels?: number;
  median_etr?: number;
  median_tax_per_sqft?: number;
  median_market_value?: number;
  median_tax_bill?: number;
  median_exempt_fraction?: number;
  pct_abated?: number;
}

function fmtMoney(n?: number) {
  if (n == null || !isFinite(n)) return "—";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1000)}K`;
  return `$${Math.round(n)}`;
}
function fmtPct(n?: number, digits = 2) {
  if (n == null || !isFinite(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}
// Build a paint expression for a render mode, against either the parcels
// source ("parcels") or the NTA source ("nta"). Some modes don't have an
// NTA equivalent (etr_vs_class) — caller should hide the NTA layer for
// those modes.
function buildPaint(
  mode: NycTaxMapMode,
  source: "parcels" | "nta",
  citywideMedian: number | null,
  classMedians: Record<string, number> | null,
): any {
  const cfg = NYC_TAX_MAP_CONFIG.modes[mode];
  const stops = (source === "nta" && (cfg as any).ntaStops
    ? (cfg as any).ntaStops
    : cfg.stops) as [number, string][];

  // Determine which property to read.
  let valueExpr: any;
  if (source === "nta") {
    const ntaProp = (cfg as any).ntaProperty;
    if (!ntaProp) return ["literal", "transparent"]; // unsupported on NTA
    valueExpr = ["coalesce", ["get", ntaProp], 0];
  } else {
    valueExpr = ["coalesce", ["get", cfg.property], 0];
  }

  // Diverging-mode transforms: (value / reference - 1).
  if ((cfg as any).diverging === "citywide" && citywideMedian) {
    valueExpr = ["-", ["/", valueExpr, citywideMedian], 1];
  } else if ((cfg as any).diverging === "class" && classMedians && source === "parcels") {
    // Build a `match` expression: for each tax_class, divide by its median.
    // `etr / class_median[class] - 1`
    const matchArgs: any[] = ["match", ["coalesce", ["get", "tax_class"], "_"]];
    for (const [cls, med] of Object.entries(classMedians)) {
      matchArgs.push(cls, med);
    }
    matchArgs.push(0); // default: no class median => 0 fallback
    const denom = matchArgs;
    valueExpr = [
      "case",
      ["==", denom, 0],
      0,
      ["-", ["/", ["coalesce", ["get", cfg.property], 0], denom], 1],
    ];
  }

  // Linear interpolate across stops.
  const interp: any[] = ["interpolate", ["linear"], valueExpr];
  for (const [v, color] of stops) {
    interp.push(v, color);
  }
  return interp;
}

interface GeoSearchHit {
  bbl?: string;
  label: string;
  housenumber?: string;
  street?: string;
  borough?: string;
  lon: number;
  lat: number;
}

const GEOSEARCH_URL =
  "https://geosearch.planninglabs.nyc/v2/autocomplete";

async function fetchGeoSearch(text: string, signal?: AbortSignal): Promise<GeoSearchHit[]> {
  if (text.trim().length < 3) return [];
  const url = `${GEOSEARCH_URL}?text=${encodeURIComponent(text)}&size=5`;
  const r = await fetch(url, { signal });
  if (!r.ok) return [];
  const j = await r.json();
  return (j.features || [])
    .map((f: any): GeoSearchHit | null => {
      const [lon, lat] = f.geometry?.coordinates || [];
      if (lon == null || lat == null) return null;
      const p = f.properties || {};
      const bbl = p.addendum?.pad?.bbl;
      return {
        bbl,
        label: p.label || p.name,
        housenumber: p.housenumber,
        street: p.street,
        borough: p.borough,
        lon,
        lat,
      };
    })
    .filter(Boolean) as GeoSearchHit[];
}

export default function NYCPropertyTaxMap() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [mode, setMode] = useState<NycTaxMapMode>(NYC_TAX_MAP_CONFIG.defaultMode);
  const [selected, setSelected] = useState<ParcelProps | null>(null);
  const [hovered, setHovered] = useState<ParcelProps | null>(null);
  const [hoveredNta, setHoveredNta] = useState<NTAProps | null>(null);
  const [stats, setStats] = useState<any>(null);
  const [classMedians, setClassMedians] = useState<Record<string, number> | null>(null);
  const [search, setSearch] = useState("");
  const [searchHits, setSearchHits] = useState<GeoSearchHit[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchMsg, setSearchMsg] = useState<string | null>(null);
  const [currentZoom, setCurrentZoom] = useState<number>(NYC_TAX_MAP_CONFIG.zoom);
  const searchAbortRef = useRef<AbortController | null>(null);

  // Citywide stats (medians for legend annotations).
  useEffect(() => {
    fetch(NYC_TAX_MAP_CONFIG.statsUrl)
      .then((r) => (r.ok ? r.json() : null))
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  // Per-class ETR medians for the "ETR vs same-class median" mode.
  useEffect(() => {
    fetch(NYC_TAX_MAP_CONFIG.classMediansUrl)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!j) return;
        // The file may be { tax_year, class_medians: {...} } or directly {class: median}.
        const meds = j.class_medians || j;
        setClassMedians(meds);
      })
      .catch(() => setClassMedians(null));
  }, []);

  const citywideMedian = stats?.etr_overall?.median ?? null;

  // Initialize map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    registerPMTilesProtocol();

    const map = new maplibregl.Map({
      container: containerRef.current,
      transformRequest: cartoTransformRequest,
      // Keeps the WebGL buffer readable so element screenshots (tools/social-capture.mjs) aren't blank.
      canvasContextAttributes: { preserveDrawingBuffer: true } as any,
      style: cartoStyleUrl("voyager"),
      center: NYC_TAX_MAP_CONFIG.center,
      zoom: NYC_TAX_MAP_CONFIG.zoom,
      minZoom: NYC_TAX_MAP_CONFIG.minZoom,
      maxZoom: NYC_TAX_MAP_CONFIG.maxZoom,
    });
    mapRef.current = map;
    if (import.meta.env.DEV) (window as any).__nycTaxMap = map;

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");

    const addLayers = () => {
      const style = map.getStyle();
      if (!style || !style.sources || Object.keys(style.sources).length === 0) return;
      if (map.getLayer("parcels-fill")) return; // already added

      // ── NTA aggregate source + layer (low zoom) ───────────────────────
      if (!map.getSource("nta")) {
        map.addSource("nta", {
          type: "geojson",
          data: NYC_TAX_MAP_CONFIG.ntaGeoJsonUrl,
        });
      }
      map.addLayer({
        id: "nta-fill",
        type: "fill",
        source: "nta",
        maxzoom: NYC_TAX_MAP_CONFIG.ntaMaxZoom,
        paint: {
          "fill-color": "#F2F2F2", // overridden in the mode-update effect
          "fill-opacity": [
            "interpolate",
            ["linear"],
            ["zoom"],
            ...NYC_TAX_MAP_CONFIG.ntaOpacityStops,
          ],
          "fill-outline-color": "rgba(31,31,214,0.25)",
        },
      });
      map.addLayer({
        id: "nta-line",
        type: "line",
        source: "nta",
        maxzoom: NYC_TAX_MAP_CONFIG.ntaMaxZoom,
        paint: {
          "line-color": "rgba(31,31,214,0.35)",
          "line-width": 0.5,
        },
      });

      // ── Parcels source + fill + outline (high zoom) ───────────────────
      const pmtUrl = NYC_TAX_MAP_CONFIG.parcelsPmtilesUrl.startsWith("http")
        ? NYC_TAX_MAP_CONFIG.parcelsPmtilesUrl
        : `${window.location.origin}${NYC_TAX_MAP_CONFIG.parcelsPmtilesUrl}`;
      if (!map.getSource("parcels")) {
        map.addSource("parcels", {
          type: "vector",
          url: `pmtiles://${pmtUrl}`,
        });
      }
      map.addLayer({
        id: "parcels-fill",
        type: "fill",
        source: "parcels",
        "source-layer": NYC_TAX_MAP_CONFIG.parcelsSourceLayer,
        minzoom: NYC_TAX_MAP_CONFIG.parcelMinZoom,
        filter: SHOWABLE_PARCEL,
        paint: {
          "fill-color": "#F2F2F2",
          "fill-opacity": [
            "interpolate",
            ["linear"],
            ["zoom"],
            ...NYC_TAX_MAP_CONFIG.parcelOpacityStops,
          ],
          "fill-outline-color": "rgba(60,60,60,0.18)",
        },
      });
      map.addLayer({
        id: "parcels-hover",
        type: "line",
        source: "parcels",
        "source-layer": NYC_TAX_MAP_CONFIG.parcelsSourceLayer,
        paint: { "line-color": "#1F1FD6", "line-width": 2 },
        filter: ["all", SHOWABLE_PARCEL, ["==", ["get", "bbl"], ""]],
      });

      // ── Interactions ──────────────────────────────────────────────────
      let hoveredBbl: string | null = null;
      map.on("mousemove", "parcels-fill", (e) => {
        if (!e.features || !e.features.length) return;
        const props = e.features[0].properties as ParcelProps;
        setHovered(props);
        setHoveredNta(null);
        const bbl = props?.bbl;
        if (bbl && bbl !== hoveredBbl) {
          hoveredBbl = bbl;
          map.setFilter("parcels-hover", ["all", SHOWABLE_PARCEL, ["==", ["get", "bbl"], bbl]]);
          map.getCanvas().style.cursor = "pointer";
        }
      });
      map.on("mouseleave", "parcels-fill", () => {
        hoveredBbl = null;
        setHovered(null);
        map.setFilter("parcels-hover", ["all", SHOWABLE_PARCEL, ["==", ["get", "bbl"], ""]]);
        map.getCanvas().style.cursor = "";
      });
      map.on("click", "parcels-fill", (e) => {
        if (!e.features || !e.features.length) return;
        setSelected(e.features[0].properties as ParcelProps);
      });

      map.on("mousemove", "nta-fill", (e) => {
        if (!e.features || !e.features.length) return;
        // Only show NTA tooltip when parcels aren't visible (low zoom).
        if (map.getZoom() >= NYC_TAX_MAP_CONFIG.ntaMaxZoom) return;
        setHoveredNta(e.features[0].properties as NTAProps);
      });
      map.on("mouseleave", "nta-fill", () => {
        setHoveredNta(null);
      });
    };

    map.on("load", addLayers);
    map.on("styledata", addLayers);
    map.on("zoom", () => setCurrentZoom(map.getZoom()));

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Update paint when mode / class-medians / citywide-median change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      if (map.getLayer("parcels-fill")) {
        map.setPaintProperty(
          "parcels-fill",
          "fill-color",
          buildPaint(mode, "parcels", citywideMedian, classMedians),
        );
      }
      if (map.getLayer("nta-fill")) {
        map.setPaintProperty(
          "nta-fill",
          "fill-color",
          buildPaint(mode, "nta", citywideMedian, classMedians),
        );
      }
    };
    apply();
    map.on("styledata", apply);
    return () => {
      map.off("styledata", apply);
    };
  }, [mode, citywideMedian, classMedians]);

  // Debounced GeoSearch autocomplete.
  useEffect(() => {
    if (!search.trim()) {
      setSearchHits([]);
      return;
    }
    const ctrl = new AbortController();
    searchAbortRef.current?.abort();
    searchAbortRef.current = ctrl;
    const t = setTimeout(async () => {
      try {
        const hits = await fetchGeoSearch(search, ctrl.signal);
        setSearchHits(hits);
        setSearchOpen(true);
      } catch {
        // aborted or network error
      }
    }, 200);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [search]);

  function gotoHit(hit: GeoSearchHit) {
    const map = mapRef.current;
    if (!map) return;
    setSearch(hit.label);
    setSearchOpen(false);
    setSearchMsg(null);
    map.flyTo({ center: [hit.lon, hit.lat], zoom: 17, duration: 800 });

    // Poll for the parcel to appear in queryable features. Citywide PMTiles
    // need a moment to fetch tiles at z=17 over R2; we wait up to ~12s.
    let attempts = 0;
    const maxAttempts = 60;
    const poll = () => {
      attempts += 1;
      const all = (() => {
        try {
          return map.querySourceFeatures("parcels", {
            sourceLayer: NYC_TAX_MAP_CONFIG.parcelsSourceLayer,
          });
        } catch {
          return [];
        }
      })();
      const match = hit.bbl
        ? all.find((f: any) => f.properties?.bbl === hit.bbl)
        : null;
      if (match) {
        const props = match.properties as ParcelProps;
        if (isHiddenByFlags(props)) {
          // Parcel exists in the tiles but didn't join PVAD (or has no MV).
          // The polygon is filtered out of the map paint; show a message
          // instead of the standard popup with em-dashes everywhere.
          setSelected(null);
          setSearchMsg(
            `Found ${hit.label} (BBL ${hit.bbl}), but this parcel is missing ` +
              `tax data in DOF's per-BBL valuation file (PVAD). Usually a condo ` +
              `whose unit-level records exist but didn't roll up to the building ` +
              `polygon — a fresh data refresh should resolve it.`,
          );
          return;
        }
        setSelected(props);
        try { map.setFilter("parcels-hover", ["all", SHOWABLE_PARCEL, ["==", ["get", "bbl"], hit.bbl!]]); } catch {}
        return;
      }
      if (attempts >= maxAttempts) {
        if (hit.bbl) {
          setSelected(null);
          setSearchMsg(
            `Address resolved (BBL ${hit.bbl}), but we couldn't find a parcel ` +
              `record at that location. Tiles may still be loading — try clicking ` +
              `the parcel directly on the map.`,
          );
        } else {
          setSearchMsg("Couldn't resolve that address to a parcel.");
        }
        return;
      }
      setTimeout(poll, 200);
    };
    setTimeout(poll, 300);
  }

  const modeCfg = NYC_TAX_MAP_CONFIG.modes[mode];
  const legendStops = (currentZoom < NYC_TAX_MAP_CONFIG.ntaMaxZoom && (modeCfg as any).ntaStops
    ? (modeCfg as any).ntaStops
    : modeCfg.stops) as readonly (readonly [number, string])[];

  // Legend label for the unit on each ramp stop.
  const formatStop = (v: number): string => {
    if (mode === "tax_per_sqft") return `$${v}`;
    if (mode === "market_value") {
      return v >= 1_000_000 ? `$${v / 1_000_000}M` : `$${v / 1000}K`;
    }
    if (mode === "etr_vs_citywide" || mode === "etr_vs_class") {
      const sign = v > 0 ? "+" : "";
      return `${sign}${Math.round(v * 100)}%`;
    }
    if (mode === "abatement") return `${Math.round(v * 100)}%`;
    return String(v);
  };

  return (
    <div className="relative my-8 not-prose">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {/* Search */}
        <div className="relative w-full sm:w-[320px] flex-shrink-0">
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setSearchMsg(null);
            }}
            onFocus={() => searchHits.length && setSearchOpen(true)}
            onBlur={() => setTimeout(() => setSearchOpen(false), 150)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && searchHits[0]) {
                e.preventDefault();
                gotoHit(searchHits[0]);
              } else if (e.key === "Escape") {
                setSearchOpen(false);
              }
            }}
            placeholder="Search any NYC address (e.g. 19 Cranberry Street)"
            className="w-full px-3 py-1.5 text-xs font-sans rounded-md border border-cobalt/30 focus:border-cobalt focus:outline-none focus:ring-1 focus:ring-cobalt/40"
          />
          {searchOpen && searchHits.length > 0 && (
            <ul className="absolute z-20 mt-1 w-full bg-white border border-slate-200 rounded-md shadow-lg max-h-80 overflow-y-auto">
              {searchHits.map((h, i) => (
                <li key={i}>
                  <button
                    onMouseDown={(e) => {
                      e.preventDefault();
                      gotoHit(h);
                    }}
                    className="w-full text-left px-3 py-2 text-xs font-sans hover:bg-slate-50 border-b border-slate-100 last:border-b-0"
                  >
                    <div className="font-semibold truncate">{h.label}</div>
                    {h.bbl && (
                      <div className="text-[10px] text-steel">BBL {h.bbl}</div>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Mode toggle */}
        {(Object.keys(NYC_TAX_MAP_CONFIG.modes) as NycTaxMapMode[]).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`px-3 py-1.5 text-xs font-sans font-semibold rounded-md border transition-colors ${
              m === mode
                ? "bg-cobalt text-white border-cobalt"
                : "bg-white text-cobalt border-cobalt/30 hover:border-cobalt"
            }`}
          >
            {NYC_TAX_MAP_CONFIG.modes[m].label}
          </button>
        ))}
      </div>

      {searchMsg && (
        <div className="mb-3 text-xs font-sans text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          {searchMsg}
        </div>
      )}

      <div
        ref={containerRef}
        className="w-full rounded-lg border border-slate-200 overflow-hidden"
        style={{ height: "75vh", minHeight: 480 }}
      />

      {/* Legend */}
      <div className="absolute left-3 bottom-10 z-10 bg-white/95 backdrop-blur-sm rounded-md shadow-md p-3 text-xs font-sans max-w-[280px]">
        <div className="font-semibold text-cobalt mb-1">{modeCfg.label}</div>
        <div className="flex items-center gap-1">
          {legendStops.map(([v, c], i) => (
            <div key={i} className="flex flex-col items-center" style={{ flex: 1 }}>
              <div
                className="w-full h-3"
                style={{
                  background: c,
                  borderRadius:
                    i === 0 ? "3px 0 0 3px" :
                    i === legendStops.length - 1 ? "0 3px 3px 0" : 0,
                }}
              />
              <div className="text-[10px] text-steel mt-0.5">{formatStop(v as number)}</div>
            </div>
          ))}
        </div>
        {mode === "etr_vs_citywide" && stats?.etr_overall && (
          <div className="text-[11px] text-steel mt-2">
            Typical NYC parcel pays <strong>{(stats.etr_overall.median * 100).toFixed(2)}%</strong> of
            its market value in tax each year. Cobalt = paying less than that; amber = paying more.
          </div>
        )}
        {mode === "etr_vs_class" && classMedians && (
          <div className="text-[11px] text-steel mt-2">
            Each parcel compared to the median ETR within its tax class
            (Class 1: {((classMedians["1"] || 0) * 100).toFixed(2)}%, Class 2:{" "}
            {((classMedians["2"] || 0) * 100).toFixed(2)}%, Class 4:{" "}
            {((classMedians["4"] || 0) * 100).toFixed(2)}%). Reveals within-class outliers.
          </div>
        )}
        {mode === "abatement" && (
          <div className="text-[11px] text-steel mt-2">
            Share of assessed value that's tax-exempt (e.g. 421-a, 485-x, J-51).
            Deep teal = highest abatement.
          </div>
        )}
      </div>

      {/* Hover tooltip — parcel */}
      {hovered && !selected && (
        <div className="absolute right-3 top-3 z-10 bg-white/95 backdrop-blur-sm rounded-md shadow-md p-3 text-xs font-sans max-w-[280px] pointer-events-none">
          <div className="font-semibold truncate">
            {hovered.address || `BBL ${hovered.bbl}`}
          </div>
          <div className="text-steel">{bldgClassLabel(hovered.bldg_class)}</div>
          <div className="mt-1">
            Tax: <strong>{fmtMoney(hovered.tax_bill)}/yr</strong>
            {hovered.tax_per_sqft != null && (
              <> · {`$${hovered.tax_per_sqft}/sqft`}</>
            )}
          </div>
          <div>
            Effective rate: <strong>{fmtPct(hovered.etr)}</strong> · Market value:{" "}
            {fmtMoney(hovered.market_value)}
          </div>
          {hovered.exempt_fraction != null && hovered.exempt_fraction > 0.05 && (
            <div className="text-teal-700">
              Tax break: {Math.round(hovered.exempt_fraction * 100)}% exempt
            </div>
          )}
          <div className="text-steel mt-1">Click for full details</div>
        </div>
      )}

      {/* Hover tooltip — NTA (low zoom) */}
      {hoveredNta && !selected && !hovered && (
        <div className="absolute right-3 top-3 z-10 bg-white/95 backdrop-blur-sm rounded-md shadow-md p-3 text-xs font-sans max-w-[280px] pointer-events-none">
          <div className="font-semibold truncate">{hoveredNta.ntaname}</div>
          <div className="text-steel">{hoveredNta.boroname} · {(hoveredNta.n_parcels || 0).toLocaleString()} parcels</div>
          <div className="mt-1">
            Median ETR: <strong>{fmtPct(hoveredNta.median_etr)}</strong>
          </div>
          <div>
            Median tax / sqft: <strong>{hoveredNta.median_tax_per_sqft != null ? `$${hoveredNta.median_tax_per_sqft}` : "—"}</strong>
          </div>
          {hoveredNta.pct_abated != null && hoveredNta.pct_abated > 0.02 && (
            <div className="text-teal-700">
              {Math.round((hoveredNta.pct_abated || 0) * 100)}% of parcels with active abatement
            </div>
          )}
          <div className="text-steel mt-1">Zoom in for individual parcels</div>
        </div>
      )}

      {/* Click panel — parcel */}
      {selected && (
        <div className="absolute right-3 top-3 z-10 bg-white rounded-md shadow-lg p-4 text-sm font-sans max-w-[340px] border border-slate-200">
          <button
            onClick={() => setSelected(null)}
            className="absolute top-2 right-2 text-steel hover:text-cobalt"
            aria-label="Close"
          >
            ×
          </button>

          {/* Title: street address (falls back to BBL if address missing). */}
          <div className="font-serif font-bold text-cobalt text-lg leading-tight pr-6">
            {selected.address || `BBL ${selected.bbl}`}
          </div>
          {/* Subtitle: building type + year + units. */}
          <div className="text-steel text-sm mt-1 leading-snug">
            {[
              bldgClassLabel(selected.bldg_class),
              selected.year_built && Number(selected.year_built) > 1800
                ? `built ${selected.year_built}`
                : null,
              selected.units_total
                ? `${selected.units_total} unit${Number(selected.units_total) > 1 ? "s" : ""}`
                : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </div>
          {selected.bbl && (
            <div className="text-steel text-[11px] mt-0.5">BBL {selected.bbl}</div>
          )}
          {selected.aggregation === "condo" && selected.units_aggregated ? (
            <div className="text-steel text-[11px] mt-0.5 mb-4 italic">
              Aggregated from {selected.units_aggregated.toLocaleString()} DOF
              records (each apartment, garage space, and storage unit is billed
              separately; the map sums them at the building level).
            </div>
          ) : (
            selected.bbl && <div className="mb-4" />
          )}

          {/* Hero stats: the two numbers a reader cares about most. */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div>
              <div className="text-steel text-[11px] uppercase tracking-wide">Annual tax bill</div>
              <div className="font-bold text-2xl text-cobalt leading-tight">
                {fmtMoney(selected.tax_bill)}
              </div>
            </div>
            <div>
              <div className="text-steel text-[11px] uppercase tracking-wide">Tax / sqft</div>
              <div className="font-bold text-2xl text-cobalt leading-tight">
                {selected.tax_per_sqft != null ? `$${selected.tax_per_sqft.toFixed(2)}` : "—"}
              </div>
            </div>
          </div>

          {/* Rate context as a sentence, not a labeled stat. */}
          {selected.etr != null && (
            <div className="border-t border-slate-200 pt-3 mb-3 text-sm leading-snug">
              This building pays{" "}
              <strong className="text-cobalt">{fmtPct(selected.etr)}</strong>{" "}
              of its market value in property tax each year.
              {citywideMedian && (
                <>
                  {" "}That's{" "}
                  <strong>
                    {fmtMultiplier(selected.etr / citywideMedian)}
                  </strong>{" "}
                  the typical NYC parcel pays
                  {classMedians &&
                  selected.tax_class &&
                  classMedians[selected.tax_class] ? (
                    <>
                      , and{" "}
                      <strong>
                        {fmtMultiplier(selected.etr / classMedians[selected.tax_class])}
                      </strong>{" "}
                      the typical building in this category.
                    </>
                  ) : (
                    <>.</>
                  )}
                </>
              )}
            </div>
          )}

          {/* Caveat: co-op denominator (DOF undervalues co-ops). */}
          {shouldShowCoopCaveat(selected.tax_class, selected.bldg_class) && (
            <div className="text-xs bg-amber-50 border border-amber-200 rounded px-2 py-1.5 mb-3 leading-snug">
              <strong>Co-op caveat:</strong> DOF tends to undervalue co-ops via its
              stock-comparison method. The rate above is mechanically high because
              the denominator (market value) is too low; the real burden per
              shareholder is closer to the typical Class 1 owner.
            </div>
          )}

          {/* Caveat: Class 1 cap visibly shielding the bill. */}
          {selected.tax_class &&
            classMedians &&
            shouldShowCapCaveat(
              selected.tax_class,
              selected.etr,
              classMedians[selected.tax_class],
            ) && (
              <div className="text-xs bg-cobalt/5 border border-cobalt/20 rounded px-2 py-1.5 mb-3 leading-snug">
                <strong>The cap is doing real work here.</strong> This parcel's bill
                is held below what an uncapped market-value calculation would
                produce — likely because the current owner has held the property
                long enough for the assessment cap to slow-walk the taxable value
                far behind the actual market.
              </div>
            )}

          {/* Quiet line: DOF market value, with provenance. */}
          <div className="text-xs flex items-baseline justify-between">
            <span className="text-steel">Market value (DOF estimate)</span>
            <span className="font-semibold">{fmtMoney(selected.market_value)}</span>
          </div>
          {(selected.tax_class || selected.bldg_class) && (
            <div className="text-[11px] text-steel mt-0.5 leading-snug">
              {mvMethodology(selected.tax_class, selected.bldg_class)}
              {(() => {
                const base = selected.mv_y2023;
                const latest = selected.mv_y2026 ?? selected.market_value;
                if (
                  selected.aggregation !== "condo" &&
                  base != null &&
                  latest != null &&
                  base > 0
                ) {
                  const pct = Math.round(((latest - base) / base) * 100);
                  if (Number.isFinite(pct)) {
                    if (pct === 0) return ". Flat since 2023.";
                    const sign = pct > 0 ? "+" : "";
                    return `. ${sign}${pct}% since 2023.`;
                  }
                }
                return ".";
              })()}
            </div>
          )}

          {/* Abatement, if active — keep prominent because it's part of the story. */}
          {selected.exempt_fraction != null && selected.exempt_fraction > 0.01 && (
            <div className="border-t border-slate-200 pt-3 mt-3 text-sm leading-snug">
              <strong className="text-teal-700">Tax break in effect</strong> —{" "}
              {Math.round(selected.exempt_fraction * 100)}% of the assessed value is
              exempt (typically a 421-a, 485-x, J-51, ICAP, SCHE, or DHE program).
              {selected.exempt_total != null && selected.exempt_total > 0 && (
                <span className="text-xs text-steel block mt-0.5">
                  Exempt assessed value: {fmtMoney(selected.exempt_total)}
                </span>
              )}
            </div>
          )}

          {selected.data_quality && selected.data_quality !== "ok" && (
            <div className="mt-3 text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded">
              Data note: {selected.data_quality}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
