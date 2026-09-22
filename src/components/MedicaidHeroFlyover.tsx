// MedicaidHeroFlyover: scrollytelling intro to the Medicaid work-requirements
// gizmo. Four scroll steps, each driving a flyTo on its own MapLibre instance.
// Structure: scale, then a heterogeneity contrast (two states with opposite
// priorities), then a national pull-back that hands off to the six tools.
//   1. California:   state zoom, subject_count (the scale of the job)
//   2. Pennsylvania: state zoom, burden_index (weakest ex parte capability)
//   3. West Virginia: state zoom, burden_index (a different #1 priority)
//   4. National pull-back: loss_exposure, hands off to the tools/prose
//
// The sticky map releases after step 4. Prose follows (Who has to verify / Why
// most who lose coverage will still be working / Two paths to compliance),
// then the fully-interactive main embed (<medicaid-map>). This is the intro;
// the explore map below is the payoff.

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import "maplibre-gl/dist/maplibre-gl.css";

import { MEDICAID_MAP_CONFIG, type MedicaidMapMode } from "@/config/medicaidWorkRequirementsMap";
import { useInViewStep } from "@/hooks/useInViewStep";
import { isTouchPrimary } from "@/lib/isTouchPrimary";
import MethodologyInfo from "@/components/MethodologyInfo";
import { cartoTransformRequest } from "@/config/basemap";

// On touch devices the hero drops the 57 MB hex layer (see the map-init effect),
// so the county choropleth has to carry the whole color story by itself. The
// desktop county stops fade counties out under the hex (down to ~0.25); these
// flatter, higher stops keep the counties readable across the hero's z3.8–6.8
// range. Mirrors the explore map's counties-only opacity override.
const HERO_LITE_COUNTIES_OPACITY = [2.5, 0, 3, 0.5, 8, 0.45] as number[];

interface StateSummaryShape {
  national: {
    subject_count_strict: number;
    loss_exposure_strict: number;
  };
  concentration?: {
    share_in_top_n_counties?: Record<string, number>;
  };
}

interface Step {
  /** Headline shown in the floating caption */
  headline: string;
  /** Body paragraph */
  body: string;
  /** flyTo target */
  center: [number, number];
  /** Target zoom */
  zoom: number;
  /** Mode to switch to */
  mode: MedicaidMapMode;
  /** Percentile threshold (50 = show all, 80 = top 20%) */
  thresholdPct: number;
  /** Methodology disclosure ID for the inline link */
  disclosureId: string;
}

const STEPS: Step[] = [
  {
    headline: "California: 4.7 million subject adults",
    body:
      "That is more people than live in 26 entire states. Starting in 2027, California has to confirm at each six-month renewal that every one of them is working, in school, or exempt. At that scale, what decides who keeps coverage is the verification system, not whether people are actually working.",
    center: [-119.5, 37.5],
    zoom: 5.6,
    mode: "subject_count",
    thresholdPct: 50,
    disclosureId: "map.subject_count",
  },
  {
    headline: "Pennsylvania: a verification problem, not a work problem",
    body:
      "Pennsylvania has 769,000 subject adults. During the recent unwinding it renewed just 16% of Medicaid cases automatically, the weakest ex parte rate among the expansion states. Its enrollees aren't less likely to be working; the state is the least able to confirm it without paperwork. The first move here is wiring up automatic verification before anyone has to upload a thing.",
    center: [-77.6, 40.9],
    zoom: 6.3,
    mode: "burden_index",
    thresholdPct: 50,
    disclosureId: "map.burden_index",
  },
  {
    headline: "West Virginia: a completely different first move",
    body:
      "West Virginia's caseload is a fifth of Pennsylvania's, and its hardest category is medical frailty: chronic-condition status that doesn't flow cleanly from claims data. Same federal rule, opposite priority. The win here is a claims-and-health-information-exchange pull for medically-frail adults, not a wage-matching build. No two states should start in the same place.",
    center: [-80.6, 38.9],
    zoom: 6.8,
    mode: "burden_index",
    thresholdPct: 50,
    disclosureId: "map.burden_index",
  },
  {
    headline: "Same rule, very different operational realities",
    body:
      "Same federal rule, very different operational realities. So we built six tools, one for each question an agency has to answer: who has to verify, which paths a state can confirm automatically, how capable it already is, where the losses come from, where they concentrate, and a downloadable brief for every state. Start wherever your problem is.",
    center: [-97.5, 39.0],
    zoom: 3.8,
    mode: "loss_exposure",
    thresholdPct: 50,
    disclosureId: "map.loss_exposure",
  },
];

function registerPMTilesProtocol() {
  const p = new Protocol();
  try { maplibregl.removeProtocol("pmtiles"); } catch { /* not yet registered */ }
  try { maplibregl.addProtocol("pmtiles", p.tile); } catch { /* already registered */ }
}

function buildFillColor(mode: MedicaidMapMode, primitive: "counties" | "hex5mi" | "grid"): any {
  const cfg = MEDICAID_MAP_CONFIG.modes[mode];
  const stops =
    primitive === "hex5mi" ? ((cfg as any).stopsHex5mi ?? cfg.stopsGrid) :
    primitive === "grid" ? cfg.stopsGrid :
    cfg.stopsCounty;
  const valueExpr: any = ["coalesce", ["get", cfg.property], 0];
  const step: any[] = ["step", valueExpr, stops[0][1]];
  for (let i = 1; i < stops.length; i++) {
    step.push(stops[i][0], stops[i][1]);
  }
  return [
    "case",
    // Subject via a sized 1115-waiver slice (WI/GA): metric color, not gray.
    ["==", ["get", "subject_via_waiver"], true],
    step,
    // Listed by CMS but not quantified (TN counties): distinct flagged fill.
    ["==", ["get", "waiver_listed"], true],
    MEDICAID_MAP_CONFIG.waiverListedFill,
    // Truly unaffected non-expansion states: gray.
    ["==", ["get", "expansion"], false],
    MEDICAID_MAP_CONFIG.nonExpansionFill,
    step,
  ];
}

function buildFillOpacity(layerOpacityStops: number[], threshold: number | null, mode: MedicaidMapMode): any {
  // MapLibre's data-driven paint: `zoom` can only appear as the INPUT to a
  // top-level step/interpolate. Wrapping zoom-interpolates inside a `case`
  // (the previous shape) is silently rejected — `setPaintProperty` returns
  // without error but the expression isn't applied. Fix: put
  // `interpolate ["zoom"]` at the top level, with each stop's VALUE being
  // a `case` that dims by feature property.
  if (threshold === null || threshold === undefined) {
    const arr: any[] = ["interpolate", ["linear"], ["zoom"]];
    for (let i = 0; i < layerOpacityStops.length; i += 2) {
      arr.push(layerOpacityStops[i], layerOpacityStops[i + 1]);
    }
    return arr;
  }
  const prop = MEDICAID_MAP_CONFIG.modes[mode].property;
  const above: any = [">=", ["coalesce", ["get", prop], 0], threshold];
  const dim = MEDICAID_MAP_CONFIG.opacityBelowThreshold / MEDICAID_MAP_CONFIG.opacityAboveThreshold;
  const arr: any[] = ["interpolate", ["linear"], ["zoom"]];
  for (let i = 0; i < layerOpacityStops.length; i += 2) {
    const z = layerOpacityStops[i];
    const op = layerOpacityStops[i + 1];
    arr.push(z, ["case", above, op, op * dim]);
  }
  return arr;
}

function cutoffFor(summary: any, mode: MedicaidMapMode, prim: string, pct: number): number | null {
  if (pct <= 50) return null;
  const pcts = summary?.percentile_cutoffs?.[mode]?.[prim];
  if (!pcts) return null;
  const available = Object.keys(pcts).map(Number).sort((a, b) => a - b);
  if (available.length === 0) return null;
  const nearest = available.reduce((p, c) =>
    Math.abs(c - pct) < Math.abs(p - pct) ? c : p,
  );
  return pcts[String(nearest)];
}

export default function MedicaidHeroFlyover() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const [summary, setSummary] = useState<StateSummaryShape | null>(null);

  // 5 step elements; activeStep is 0..4 or -1 (out of view)
  const stepRefs = useRef<(HTMLElement | null)[]>([]);
  const activeStep = useInViewStep(stepRefs);

  // Fetch summary for caption tokens
  useEffect(() => {
    fetch(MEDICAID_MAP_CONFIG.stateSummaryUrl)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then((j) => setSummary(j))
      .catch(() => setSummary(null));
  }, []);

  // Init MapLibre
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    registerPMTilesProtocol();

    // Touch-primary devices get a featherweight hero: counties only. The hero
    // never zooms past 6.8, so the 1-mile grid (minzoom 8) never paints anyway,
    // and the 57 MB hex GeoJSON is fine texture the county choropleth stands in
    // for at these zooms. Skipping both is the bulk of the mobile memory win.
    // Desktop (fine pointer) keeps the full source/layer set, unchanged.
    const lite = isTouchPrimary();

    const map = new maplibregl.Map({
      container: containerRef.current,
      transformRequest: cartoTransformRequest,
      style: {
        version: 8,
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
        sources: {
          base: {
            type: "raster",
            tiles: MEDICAID_MAP_CONFIG.basemapTiles,
            tileSize: 256,
          } as any,
          counties: {
            type: "geojson",
            data: MEDICAID_MAP_CONFIG.countiesGeoJsonUrl,
            promoteId: "GEOID",
          } as any,
          ...(lite
            ? {}
            : {
                hex5mi: {
                  type: "geojson",
                  data: MEDICAID_MAP_CONFIG.hex5miGeoJsonUrl,
                  promoteId: "coarse_id",
                } as any,
                grid: {
                  type: "vector",
                  url: `pmtiles://${MEDICAID_MAP_CONFIG.gridPmtilesUrl}`,
                  promoteId: "cell_id",
                } as any,
              }),
        },
        layers: [
          { id: "base", type: "raster", source: "base" } as any,
          {
            id: "counties-fill",
            type: "fill",
            source: "counties",
            paint: {
              "fill-color": buildFillColor(STEPS[0].mode, "counties"),
              "fill-opacity": buildFillOpacity(
                lite ? HERO_LITE_COUNTIES_OPACITY : MEDICAID_MAP_CONFIG.countiesOpacityStops,
                null, STEPS[0].mode,
              ),
            },
          } as any,
          ...(lite
            ? []
            : [
                {
                  id: "hex5mi-fill",
                  type: "fill",
                  source: "hex5mi",
                  paint: {
                    "fill-color": buildFillColor(STEPS[0].mode, "hex5mi"),
                    "fill-opacity": buildFillOpacity(
                      MEDICAID_MAP_CONFIG.hex5miOpacityStops, null, STEPS[0].mode,
                    ),
                  },
                } as any,
                {
                  id: "medicaid-grid-1mi",
                  type: "fill",
                  source: "grid",
                  "source-layer": MEDICAID_MAP_CONFIG.gridSourceLayer,
                  minzoom: 8,
                  paint: {
                    "fill-color": buildFillColor(STEPS[0].mode, "grid"),
                    "fill-opacity": buildFillOpacity(
                      MEDICAID_MAP_CONFIG.gridOpacityStops, null, STEPS[0].mode,
                    ),
                  },
                } as any,
              ]),
          {
            id: "counties-outline",
            type: "line",
            source: "counties",
            paint: {
              "line-color": "rgba(15,23,42,0.25)",
              "line-width": 0.4,
            },
          } as any,
        ],
      },
      center: STEPS[0].center,
      zoom: STEPS[0].zoom,
      minZoom: 3,
      maxZoom: 13,
      attributionControl: false,
      interactive: false, // scroll-driven only
    });

    mapRef.current = map;
    if (import.meta.env.DEV) (window as any).__heroMap = map;

    // Keep the canvas in sync with the sticky h-screen container. On mobile
    // Safari, 100vh changes as the URL bar shows/hides, but MapLibre's
    // internal resize handler doesn't fire — the canvas stays at the
    // initial size, leaving a blank band below the rendered map content.
    const ro = containerRef.current
      ? new ResizeObserver(() => {
          try { map.resize(); } catch {}
        })
      : null;
    if (ro && containerRef.current) ro.observe(containerRef.current);

    return () => {
      try { ro?.disconnect(); } catch {}
      try { map.remove(); } catch {}
      mapRef.current = null;
    };
  }, []);

  // React to activeStep
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const step = STEPS[activeStep];
    if (!step) return;

    const apply = () => {
      map.flyTo({
        center: step.center,
        zoom: step.zoom,
        duration: 1800,
        essential: true,
      });

      const countiesCutoff = cutoffFor(summary, step.mode, "counties", step.thresholdPct);
      const hexCutoff = cutoffFor(summary, step.mode, "hex5mi", step.thresholdPct);
      const gridCutoff = cutoffFor(summary, step.mode, "grid", step.thresholdPct);

      if (map.getLayer("counties-fill")) {
        map.setPaintProperty("counties-fill", "fill-color", buildFillColor(step.mode, "counties"));
        map.setPaintProperty(
          "counties-fill", "fill-opacity",
          buildFillOpacity(
            isTouchPrimary() ? HERO_LITE_COUNTIES_OPACITY : MEDICAID_MAP_CONFIG.countiesOpacityStops,
            countiesCutoff, step.mode,
          ),
        );
      }
      if (map.getLayer("hex5mi-fill")) {
        map.setPaintProperty("hex5mi-fill", "fill-color", buildFillColor(step.mode, "hex5mi"));
        map.setPaintProperty(
          "hex5mi-fill", "fill-opacity",
          buildFillOpacity(MEDICAID_MAP_CONFIG.hex5miOpacityStops, hexCutoff, step.mode),
        );
      }
      if (map.getLayer("medicaid-grid-1mi")) {
        map.setPaintProperty("medicaid-grid-1mi", "fill-color", buildFillColor(step.mode, "grid"));
        map.setPaintProperty(
          "medicaid-grid-1mi", "fill-opacity",
          buildFillOpacity(MEDICAID_MAP_CONFIG.gridOpacityStops, gridCutoff, step.mode),
        );
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [activeStep, summary]);

  const visibleStep = activeStep >= 0 ? STEPS[activeStep] : STEPS[0];
  const visibleStepIdx = activeStep >= 0 ? activeStep : 0;

  return (
    <section
      className="not-prose relative my-10"
      style={{
        // Break out of the prose container's max-width
        width: "min(100vw - 1.5rem, 80rem)",
        marginLeft: "calc(50% - min(50vw - 0.75rem, 40rem))",
        marginRight: "calc(50% - min(50vw - 0.75rem, 40rem))",
      }}
    >
      <div className="relative" style={{ height: `${STEPS.length * 100}vh` }}>
        {/* Sticky map + caption */}
        <div className="sticky top-0 h-screen overflow-hidden bg-slate-50">
          <div ref={containerRef} className="absolute inset-0" />

          {/* Floating caption */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center px-3 pb-4 sm:px-6 sm:pb-10">
            <div className="pointer-events-auto max-w-2xl rounded-xl bg-white/95 px-4 py-3 shadow-2xl ring-1 ring-slate-200 backdrop-blur-sm sm:px-7 sm:py-5">
              <div className="mb-1 flex items-baseline justify-between sm:mb-1.5">
                <div className="font-sans text-[10px] font-semibold uppercase tracking-[0.18em] text-cobalt">
                  {visibleStepIdx + 1} of {STEPS.length}
                </div>
                <div className="font-sans text-[10px] uppercase tracking-[0.1em] text-slate-400">
                  Scroll to continue ↓
                </div>
              </div>
              <h2 className="font-serif text-[clamp(1.05rem,2.4vw,1.8rem)] font-semibold leading-[1.15] text-charcoal">
                {visibleStep.headline}
              </h2>
              <p className="mt-1.5 text-[0.85rem] leading-snug text-slate-600 sm:mt-2 sm:text-[0.95rem]">
                {visibleStep.body}
              </p>
              <div className="mt-2 sm:mt-3">
                <MethodologyInfo
                  id={visibleStep.disclosureId}
                  variant="inline"
                  align="left"
                  label="Methods"
                />
              </div>
            </div>
          </div>

          {/* Step dots — visual progress indicator */}
          <div className="pointer-events-none absolute right-6 top-1/2 flex -translate-y-1/2 flex-col gap-2">
            {STEPS.map((_, i) => (
              <div
                key={i}
                className={
                  "h-2 w-2 rounded-full transition-all " +
                  (i === visibleStepIdx
                    ? "bg-cobalt scale-150"
                    : "bg-slate-400/60")
                }
              />
            ))}
          </div>
        </div>

        {/* Invisible step anchors — full-height blocks that drive scroll position */}
        {STEPS.map((_, i) => (
          <div
            key={i}
            ref={(el) => { stepRefs.current[i] = el; }}
            className="absolute left-0 w-full"
            style={{
              top: `${i * 100}vh`,
              height: "100vh",
              pointerEvents: "none",
            }}
            aria-hidden
          />
        ))}
      </div>

      <div className="bg-slate-50 px-6 py-4 text-center font-sans text-[12px] uppercase tracking-[0.14em] text-slate-500">
        Read on ↓
      </div>
    </section>
  );
}
