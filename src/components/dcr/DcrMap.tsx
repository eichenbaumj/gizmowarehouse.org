// DcrMap — the national data-center restriction map (<dcr-map />).
//
// Redesigned around one question: where is it easy vs. hard to build?
// Layered read: state fill = the state's posture (legend is a difficulty
// ladder, hardest first); county shading = documented LOCAL action in force
// today (solid red = county-wide restriction, red hatch = a town's, blue =
// conditions); a shaded county inside a dark state is the hardest ground.
// Individual actions appear as circles once you zoom past CIRCLE_MINZOOM.
// Pending and lapsed measures are behind toggles, off by default. County
// categories are derived client-side (countyCategories.ts) so every toggle
// re-shades fills, counts, and the side panel through one code path.
//
// MapLibre skeleton notes: static-camera constructor + deferred fitBounds
// (the container can be 0-wide in hidden windows), refit dance, StrictMode-
// safe create effect — all inherited from the first version; don't regress.

import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  BASEMAP,
  CLASS_STYLE,
  COUNTY_STYLE,
  FOLLOWUP_LINE_COLOR,
  FOOTPRINT_STYLE,
  LAPSED_STATUSES,
  LIVE_STATUSES,
  OUTCOME_STYLE,
  REROUTE_LINE_COLOR,
  STATE_STATUS_STYLE,
  type ActionRow,
  type ActionsData,
  type CountyCategory,
  type CountyProps,
  type FootprintBlock,
  type OutcomeProject,
  type OutcomesData,
  type StateStatusKey,
} from "@/config/dataCenterRestrictionCost";
import { deriveCountyDisplay, type CountyDisplay } from "./countyCategories";
import { cartoTransformRequest } from "@/config/basemap";

const CIRCLE_MINZOOM = 4.5; // circles appear once county fills get cramped

const ACTION_TYPE_LABELS: Record<string, string> = {
  moratorium: "Moratorium",
  ban: "Ban",
  zoning_exclusion: "Zoning exclusion",
  project_rejection: "Project rejection",
  ordinance_conditions: "Conditions ordinance",
  referendum: "Referendum",
  tax_action: "Tax action",
  ratepayer_law: "Ratepayer law",
  large_load_tariff: "Large-load tariff",
  preemption: "State preemption of local control",
  executive_order: "Executive order",
};

const typeLabel = (t: string) => ACTION_TYPE_LABELS[t] ?? t.replace(/_/g, " ");
const isLive = (s: string) => (LIVE_STATUSES as readonly string[]).includes(s);

function bakeStatus(geo: any, data: ActionsData): void {
  for (const f of geo.features) {
    const fips = f.properties.STATEFP as string;
    f.properties.status = data.state_status[fips]?.status ?? "none";
    f.properties.tariff = data.state_status[fips]?.tariff ?? "";
  }
}

function localsFC(actions: ActionRow[], cls: "restriction" | "condition") {
  return {
    type: "FeatureCollection",
    features: actions
      .filter((a) => a.level === "local" && a.lat != null && a.lon != null && a.class === cls)
      .map((a) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [a.lon, a.lat] },
        properties: {
          kind: "local",
          id: a.id,
          jurisdiction: a.jurisdiction,
          action_type: a.action_type,
          cls: a.class,
          status: a.status,
          date: a.date ?? "",
          summary: a.summary,
          source_url: a.source_url,
          source_name: a.source_name,
          dataset: a.dataset,
          county_fips: a.county_fips ?? "",
        },
      })),
  } as any;
}

// Counties whose display category is null keep category "none" so setData can
// hide them via filters without rebuilding geometry.
function countiesFC(countiesGeo: any, display: Map<string, CountyDisplay>) {
  return {
    type: "FeatureCollection",
    features: countiesGeo.features.map((f: any) => {
      const p = f.properties as CountyProps;
      const d = display.get(p.GEOID);
      return {
        type: "Feature",
        geometry: f.geometry,
        properties: {
          GEOID: p.GEOID,
          state_fips: p.state_fips,
          state_abbr: p.state_abbr,
          county_name: p.county_name,
          category: d?.category ?? "none",
          n_live: d?.nLive ?? 0,
          n_pending: d?.nPending ?? 0,
          n_lapsed: d?.nLapsed ?? 0,
          n_live_county: d?.nLiveCountyWide ?? 0,
          n_live_town: d?.nLiveTown ?? 0,
        },
      };
    }),
  } as any;
}

// Where data centers actually run: one ring per state, area ∝ 2024 annual
// energy (EPRI). States under 0.5 TWh are dropped as visual dust.
function footprintFC(fp: FootprintBlock) {
  return {
    type: "FeatureCollection",
    features: Object.entries(fp.states)
      .filter(([, s]) => s.lat != null && s.lon != null && (s.twh_2024 ?? 0) >= 0.5)
      .map(([fips, s]) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [s.lon, s.lat] },
        properties: {
          kind: "footprint",
          state_fips: fips,
          abbr: s.abbr,
          twh: s.twh_2024,
          twh30: s.twh_2030_medium,
          r: Math.sqrt(s.twh_2024 ?? 0),
        },
      })),
  } as any;
}

function footprintPopupHTML(p: any, stateName: string): string {
  const proj = p.twh30 ? `<div style="color:#6B7280;font-size:11px">EPRI medium scenario: ${p.twh30} TWh by 2030</div>` : "";
  return `<div style="font-family:'Source Sans 3',sans-serif;font-size:12px;line-height:1.35;max-width:240px">
    <strong style="color:#1F1FD6">${stateName || p.abbr}</strong><br/>
    <span style="color:#3B3B3B">Data centers used <strong>${p.twh} TWh</strong> of electricity in 2024</span>${proj}
    <div style="color:#9AA0A6;font-size:9.5px;margin-top:2px">EPRI, Powering Intelligence 2026</div>
  </div>`;
}

function outcomePtsFC(projects: OutcomeProject[]) {
  return {
    type: "FeatureCollection",
    features: projects.map((p) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
      properties: {
        kind: "outcome",
        id: p.id,
        name: p.name,
        jurisdiction: p.jurisdiction,
        outcome: p.outcome,
        capex: p.claimed_capex_usd_b ?? -1,
        capex_label: p.capex_label ?? "announced",
        mw: p.mw ?? -1,
        date: p.decision_date ?? "",
        note: p.note,
        dest: p.destination?.name ?? "",
        dest_mi: p.destination?.distance_mi ?? -1,
        followup_name: p.followup?.name ?? "",
        followup_mi: p.followup?.distance_mi ?? -1,
        source_url: p.sources[0]?.url ?? "",
        source_name: p.sources[0]?.name ?? "",
      },
    })),
  } as any;
}

function rerouteLinesFC(projects: OutcomeProject[]) {
  return {
    type: "FeatureCollection",
    features: projects
      .filter((p) => p.outcome === "rerouted" && p.destination)
      .map((p) => ({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: [
            [p.lon, p.lat],
            [p.destination!.lon, p.destination!.lat],
          ],
        },
        properties: { id: p.id },
      })),
  } as any;
}

// Followup arcs (soft tier: same developer, nearby build, not confirmed as
// the same project) get their own source + layer rather than a data-driven
// dasharray on outcome-lines: they differ in color, width, and opacity too,
// and one layer per visual category is this file's idiom.
function followupLinesFC(projects: OutcomeProject[]) {
  return {
    type: "FeatureCollection",
    features: projects
      .filter((p) => p.followup)
      .map((p) => ({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: [
            [p.lon, p.lat],
            [p.followup!.lon, p.followup!.lat],
          ],
        },
        properties: { id: p.id },
      })),
  } as any;
}

const outcomeColorExpr: any = [
  "match",
  ["get", "outcome"],
  "died",
  OUTCOME_STYLE.died.color,
  "rerouted",
  OUTCOME_STYLE.rerouted.color,
  "delayed_then_built",
  OUTCOME_STYLE.delayed_then_built.color,
  OUTCOME_STYLE.pending_litigating.color,
];

const circleRadius: any = ["interpolate", ["linear"], ["zoom"], 3, 3.2, 5, 5, 7, 8];

// ---------------------------------------------------------------------------
// Popup HTML
// ---------------------------------------------------------------------------

function localPopupHTML(p: any, pinned: boolean): string {
  const clsStyle = CLASS_STYLE[p.cls as "restriction" | "condition"] ?? CLASS_STYLE.restriction;
  const chip = `<span style="display:inline-block;padding:0 5px;border-radius:3px;background:${clsStyle.color};color:#fff;font-size:9px;font-weight:700;text-transform:uppercase">${p.cls}</span>`;
  const statusNote =
    p.status && p.status !== "enacted" && p.status !== "in_force"
      ? `<span style="color:#B45309;font-weight:700"> · ${String(p.status).replace(/_/g, " ")}</span>`
      : "";
  const src = pinned && p.source_url
    ? `<div style="margin-top:3px"><a href="${p.source_url}" target="_blank" rel="noopener noreferrer" style="color:#21A8E0;font-size:11px">${p.source_name || "Source"} ↗</a></div>`
    : "";
  const hint = pinned ? "" : `<div style="margin-top:2px;color:#9AA0A6;font-size:9.5px">click to pin + source</div>`;
  return `<div style="font-family:'Source Sans 3',sans-serif;font-size:12px;line-height:1.35;max-width:250px">
    <strong style="color:#1F1FD6">${p.jurisdiction}</strong><br/>
    ${chip} <span style="color:#3B3B3B;font-weight:600">${typeLabel(p.action_type)}</span>${statusNote}
    ${p.date ? `<span style="color:#6B7280"> · ${p.date}</span>` : ""}
    <div style="color:#3B3B3B;margin-top:2px">${p.summary}</div>${src}${hint}
  </div>`;
}

function outcomePopupHTML(p: any, pinned: boolean): string {
  const st = OUTCOME_STYLE[p.outcome as keyof typeof OUTCOME_STYLE];
  const chip = `<span style="display:inline-block;padding:0 5px;border-radius:3px;background:${st.color};color:#fff;font-size:9px;font-weight:700;text-transform:uppercase">${st.label}</span>`;
  const capex = p.capex > 0 ? `<span style="color:#6B7280"> · $${p.capex}B (${p.capex_label})</span>` : "";
  const dest = p.dest
    ? `<div style="color:#0F6B4F;font-size:11px;margin-top:2px">→ ${p.dest}${p.dest_mi > 0 ? ` · ~${p.dest_mi} mi` : ""}</div>`
    : "";
  const followup = p.followup_name
    ? `<div style="color:#3B3B3B;font-size:11px;margin-top:2px;font-style:italic">⇢ ${p.followup_name}${p.followup_mi > 0 ? ` · ~${p.followup_mi} mi` : ""} · same developer building nearby, not confirmed as the same project</div>`
    : "";
  const src = pinned && p.source_url
    ? `<div style="margin-top:3px"><a href="${p.source_url}" target="_blank" rel="noopener noreferrer" style="color:#21A8E0;font-size:11px">${p.source_name || "Source"} ↗</a></div>`
    : "";
  const hint = pinned ? "" : `<div style="margin-top:2px;color:#9AA0A6;font-size:9.5px">click to pin + source</div>`;
  return `<div style="font-family:'Source Sans 3',sans-serif;font-size:12px;line-height:1.35;max-width:260px">
    <strong style="color:#1F1FD6">${p.name}</strong><br/>
    <span style="color:#3B3B3B">${p.jurisdiction}</span>${capex}<br/>
    ${chip} ${p.date ? `<span style="color:#6B7280">${p.date}</span>` : ""}${dest}${followup}
    <div style="color:#3B3B3B;margin-top:2px">${p.note}</div>${src}${hint}
  </div>`;
}

function countyPopupHTML(p: any): string {
  const cat = p.category as CountyCategory;
  const label =
    cat === "county_restriction"
      ? COUNTY_STYLE.county_restriction.label
      : cat === "town_restriction"
        ? COUNTY_STYLE.town_restriction.label
        : cat === "conditions_only"
          ? COUNTY_STYLE.conditions_only.label
          : cat === "pending_only"
            ? COUNTY_STYLE.pending_only.label
            : COUNTY_STYLE.lapsed_only.label;
  const bits: string[] = [];
  if (p.n_live > 0) bits.push(`${p.n_live} in force`);
  if (p.n_pending > 0) bits.push(`${p.n_pending} pending`);
  if (p.n_lapsed > 0) bits.push(`${p.n_lapsed} lapsed`);
  return `<div style="font-family:'Source Sans 3',sans-serif;font-size:12px;line-height:1.35;max-width:240px">
    <strong style="color:#1F1FD6">${p.county_name}, ${p.state_abbr}</strong><br/>
    <span style="color:#3B3B3B;font-weight:600">${label}</span>
    <div style="color:#6B7280;font-size:11px">${bits.join(" · ")} · click for the list</div>
  </div>`;
}

function statePopupHTML(
  name: string,
  status: StateStatusKey,
  tariff: string,
  nLocal: number,
  nLive: number,
  twh24: number | null
): string {
  const st = STATE_STATUS_STYLE[status];
  const tariffLine = tariff
    ? `<div style="color:#3B5BD6;font-size:11px">Large-load tariff ${tariff}</div>`
    : "";
  const fpLine =
    twh24 != null && twh24 >= 0.05
      ? `<div style="color:#3B3B3B;font-size:11px">Data centers used ~${twh24} TWh here in 2024 (EPRI)</div>`
      : "";
  return `<div style="font-family:'Source Sans 3',sans-serif;font-size:12px;line-height:1.35">
    <strong style="color:#1F1FD6">${name}</strong><br/>
    <span style="color:#3B3B3B">${st.label}</span>${tariffLine}${fpLine}
    <div style="color:#6B7280;font-size:11px">${nLocal} documented local action${nLocal === 1 ? "" : "s"} (${nLive} in force) · click for the list</div>
  </div>`;
}

type Selection = { kind: "state"; id: string } | { kind: "county"; id: string } | null;

export default function DcrMap() {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const hoverPopupRef = useRef<any>(null);
  const pinnedPopupRef = useRef<any>(null);
  const roRef = useRef<ResizeObserver | null>(null);
  const hoverFipsRef = useRef<string>("");
  const hoverGeoidRef = useRef<string>("");

  const [data, setData] = useState<ActionsData | null>(null);
  const [outcomes, setOutcomes] = useState<OutcomesData | null>(null);
  const [outcomesSettled, setOutcomesSettled] = useState(false);
  const [geo, setGeo] = useState<any>(null);
  const [countiesGeo, setCountiesGeo] = useState<any>(null);
  const [countiesSettled, setCountiesSettled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [selected, setSelected] = useState<Selection>(null);
  const [showTrace, setShowTrace] = useState(false);
  const [showDct, setShowDct] = useState(true);
  const [includePending, setIncludePending] = useState(false);
  const [includeLapsed, setIncludeLapsed] = useState(false);
  const [showFootprint, setShowFootprint] = useState(true);

  useEffect(() => {
    fetch(BASEMAP.actionsUrl)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then(setData)
      .catch((e) => setError(String(e)));
    fetch(BASEMAP.statesGeoJsonUrl)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then(setGeo)
      .catch((e) => setError(String(e)));
    // Both overlays are optional — the map still ships without them.
    fetch(BASEMAP.outcomesUrl)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => setOutcomes(j))
      .catch(() => setOutcomes(null))
      .finally(() => setOutcomesSettled(true));
    fetch(BASEMAP.countiesUrl)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!j) console.warn("[dcr map] counties.geojson missing — falling back to circles-only view");
        setCountiesGeo(j);
      })
      .catch(() => setCountiesGeo(null))
      .finally(() => setCountiesSettled(true));
  }, []);

  const dataRef = useRef<ActionsData | null>(data);
  dataRef.current = data;

  const display = useMemo(
    () => (data ? deriveCountyDisplay(data.actions, { includePending, includeLapsed, showDct }) : new Map()),
    [data, includePending, includeLapsed, showDct]
  );
  const displayRef = useRef(display);
  displayRef.current = display;

  const countyIndex = useMemo(() => {
    const m = new Map<string, CountyProps>();
    if (countiesGeo) for (const f of countiesGeo.features) m.set(f.properties.GEOID, f.properties);
    return m;
  }, [countiesGeo]);

  // Create the map once everything needed is settled (synchronous body →
  // StrictMode-safe: mount/unmount/mount creates and removes one instance).
  useEffect(() => {
    if (!mapContainer.current || mapRef.current || !data || !geo || !outcomesSettled || !countiesSettled) return;
    bakeStatus(geo, data);
    const hasCounties = !!countiesGeo;

    const statusFill: any = [
      "match",
      ["get", "status"],
      "enacted_restriction",
      STATE_STATUS_STYLE.enacted_restriction.color,
      "enacted_conditions",
      STATE_STATUS_STYLE.enacted_conditions.color,
      "incentive_rollback",
      STATE_STATUS_STYLE.incentive_rollback.color,
      "preemption",
      STATE_STATUS_STYLE.preemption.color,
      STATE_STATUS_STYLE.none.color,
    ];

    const sources: Record<string, any> = {
      "carto-base": {
        type: "raster",
        tiles: BASEMAP.tiles,
        tileSize: 256,
        attribution: BASEMAP.attribution,
      },
      "carto-labels": { type: "raster", tiles: BASEMAP.labels, tileSize: 256 },
      states: { type: "geojson", data: geo, promoteId: "STATEFP" },
      "local-restrictions": { type: "geojson", data: localsFC(data.actions, "restriction") },
      "local-conditions": { type: "geojson", data: localsFC(data.actions, "condition") },
    };
    if (hasCounties) {
      sources.counties = { type: "geojson", data: countiesFC(countiesGeo, displayRef.current), promoteId: "GEOID" };
    }
    if (outcomes) {
      sources["outcome-pts"] = { type: "geojson", data: outcomePtsFC(outcomes.projects) };
      sources["outcome-lines"] = { type: "geojson", data: rerouteLinesFC(outcomes.projects) };
      sources["followup-lines"] = { type: "geojson", data: followupLinesFC(outcomes.projects) };
    }
    if (data.footprint) {
      sources.footprint = { type: "geojson", data: footprintFC(data.footprint) };
    }

    const circleLayer = (id: string, source: string, color: string) =>
      ({
        id,
        type: "circle",
        source,
        minzoom: hasCounties ? CIRCLE_MINZOOM : 0,
        paint: {
          "circle-color": color,
          "circle-radius": circleRadius,
          "circle-opacity": 0.85,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.25,
        },
      }) as any;

    const layers: any[] = [
      { id: "carto-base", type: "raster", source: "carto-base" },
      {
        id: "states-fill",
        type: "fill",
        source: "states",
        paint: { "fill-color": statusFill, "fill-opacity": 0.72 },
      },
    ];
    if (hasCounties) {
      layers.push(
        {
          id: "counties-lapsed-fill",
          type: "fill",
          source: "counties",
          filter: ["==", ["get", "category"], "lapsed_only"],
          paint: { "fill-color": COUNTY_STYLE.lapsed_only.wash, "fill-opacity": 0.8 },
        } as any,
        {
          id: "counties-fill",
          type: "fill",
          source: "counties",
          filter: ["in", ["get", "category"], ["literal", ["county_restriction", "conditions_only"]]],
          paint: {
            "fill-color": [
              "match",
              ["get", "category"],
              "county_restriction",
              COUNTY_STYLE.county_restriction.color,
              COUNTY_STYLE.conditions_only.color,
            ],
            "fill-opacity": 0.9,
          },
        } as any,
        {
          id: "counties-hatch",
          type: "fill",
          source: "counties",
          filter: ["==", ["get", "category"], "town_restriction"],
          paint: { "fill-pattern": "town-hatch" },
        } as any,
        {
          id: "counties-outline",
          type: "line",
          source: "counties",
          filter: ["!=", ["get", "category"], "none"],
          paint: {
            "line-color": [
              "case",
              ["boolean", ["feature-state", "selected"], false],
              "#111111",
              ["boolean", ["feature-state", "hover"], false],
              "#3B3B3B",
              "#ffffff",
            ],
            "line-width": [
              "case",
              ["boolean", ["feature-state", "selected"], false],
              2.2,
              ["boolean", ["feature-state", "hover"], false],
              1.4,
              0.75,
            ],
          },
        } as any,
        {
          id: "counties-pending-line",
          type: "line",
          source: "counties",
          filter: ["==", ["get", "category"], "pending_only"],
          paint: {
            "line-color": COUNTY_STYLE.pending_only.outline,
            "line-width": 1.2,
            "line-dasharray": [2, 1.5],
          },
        } as any
      );
    }
    layers.push(
      {
        id: "states-outline",
        type: "line",
        source: "states",
        paint: {
          "line-color": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            "#111111",
            ["boolean", ["feature-state", "hover"], false],
            "#3B3B3B",
            "#ffffff",
          ],
          "line-width": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            2.4,
            ["boolean", ["feature-state", "hover"], false],
            1.6,
            0.6,
          ],
        },
      } as any,
      { id: "carto-labels", type: "raster", source: "carto-labels" } as any
    );
    if (data.footprint) {
      layers.push({
        id: "footprint-circles",
        type: "circle",
        source: "footprint",
        paint: {
          "circle-color": FOOTPRINT_STYLE.fill,
          "circle-stroke-color": FOOTPRINT_STYLE.stroke,
          "circle-stroke-width": 1.5,
          // area ∝ TWh: radius = sqrt(twh) × a zoom-scaled factor
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3,
            ["*", ["get", "r"], 3.2],
            6,
            ["*", ["get", "r"], 6.5],
          ],
        },
      } as any);
    }
    layers.push(
      circleLayer("local-restriction", "local-restrictions", CLASS_STYLE.restriction.color),
      circleLayer("local-condition", "local-conditions", CLASS_STYLE.condition.color)
    );
    if (outcomes) {
      layers.push({
        id: "outcome-lines",
        type: "line",
        source: "outcome-lines",
        layout: { visibility: "none" },
        paint: {
          "line-color": REROUTE_LINE_COLOR,
          "line-width": 1.8,
          "line-dasharray": [2, 1.6],
          "line-opacity": 0.9,
        },
      } as any);
      layers.push({
        id: "followup-lines",
        type: "line",
        source: "followup-lines",
        layout: { visibility: "none" },
        paint: {
          "line-color": FOLLOWUP_LINE_COLOR,
          "line-width": 1.6,
          "line-dasharray": [1, 2],
          "line-opacity": 0.75,
        },
      } as any);
      const pts = circleLayer("outcome-pts", "outcome-pts", "#000");
      pts.minzoom = 0;
      pts.paint["circle-color"] = outcomeColorExpr;
      pts.paint["circle-radius"] = ["interpolate", ["linear"], ["zoom"], 3, 4.5, 7, 10];
      pts.layout = { visibility: "none" };
      layers.push(pts);
    }

    let map: any;
    try {
      map = new maplibregl.Map({
        container: mapContainer.current,
        transformRequest: cartoTransformRequest,
        style: { version: 8, glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf", sources, layers } as any,
        center: [-97, 38.5],
        zoom: 3.2,
        attributionControl: {
          compact: true,
          customAttribution:
            'Data: <a href="https://mjbommar.github.io/moratorium-data-2026/">Moratorium Nation</a> · <a href="https://datacentertracker.org/">datacentertracker.org</a> · <a href="https://powering-intelligence.epri.com/dashboard/">EPRI</a>',
        } as any,
        dragRotate: false,
        maxZoom: 9,
        minZoom: 2,
        // Lets Playwright capture the WebGL canvas (linkedin/capture.mjs);
        // without it the map screenshots as a blank rectangle.
        canvasContextAttributes: { preserveDrawingBuffer: true } as any,
      });
    } catch (err: any) {
      console.error("[dcr map] constructor threw:", err?.message, err?.stack);
      setError("map init: " + (err?.message ?? err));
      return;
    }
    mapRef.current = map;
    (window as any).__dcrMap = map; // debug handle
    map.on("error", (e: any) => console.warn("[dcr map]", e?.error || e));

    // The town-level hatch: red 45° stripes on an opaque near-white base,
    // synthesized on demand (fill-pattern references it before load).
    map.on("styleimagemissing", (e: any) => {
      if (e.id !== "town-hatch" || map.hasImage("town-hatch")) return;
      const size = 12;
      const c = document.createElement("canvas");
      c.width = size * 2;
      c.height = size * 2;
      const ctx = c.getContext("2d")!;
      ctx.fillStyle = COUNTY_STYLE.town_restriction.base;
      ctx.fillRect(0, 0, size * 2, size * 2);
      ctx.strokeStyle = COUNTY_STYLE.town_restriction.stripe;
      ctx.lineWidth = 2.5;
      for (let i = -2; i <= 4; i++) {
        ctx.beginPath();
        ctx.moveTo(i * 8 - 4, size * 2 + 4);
        ctx.lineTo(i * 8 + size * 2 + 4, -4);
        ctx.stroke();
      }
      const img = ctx.getImageData(0, 0, size * 2, size * 2);
      map.addImage("town-hatch", { width: size * 2, height: size * 2, data: new Uint8Array(img.data.buffer) }, { pixelRatio: 2 });
    });

    hoverPopupRef.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
    pinnedPopupRef.current = new maplibregl.Popup({ closeButton: true, closeOnClick: true, offset: 8, maxWidth: "280px" });

    const fitted = { done: false };
    const refit = () => {
      map.resize(); // container width can settle after init (MountWhenNear + grid + hidden windows)
      const w = mapContainer.current?.clientWidth ?? 0;
      if (w >= 200) {
        map.fitBounds(BASEMAP.bounds, { padding: 16, animate: false });
        fitted.done = true;
      }
    };
    map.on("load", () => {
      refit();
      setReady(true);
      setTimeout(refit, 250);
    });
    const ro = new ResizeObserver(() => {
      map.resize();
      if (!fitted.done) refit();
    });
    ro.observe(mapContainer.current);
    roRef.current = ro;

    // Unified hover/click, query priority = render order (circles > counties > states).
    const interactive = () =>
      [
        "outcome-pts",
        "local-restriction",
        "local-condition",
        "counties-fill",
        "counties-hatch",
        "counties-lapsed-fill",
        "counties-pending-line",
        "footprint-circles",
        "states-fill",
      ].filter((l) => map.getLayer(l));

    const clearHoverStates = () => {
      if (hoverFipsRef.current) {
        map.setFeatureState({ source: "states", id: hoverFipsRef.current }, { hover: false });
        hoverFipsRef.current = "";
      }
      if (hoverGeoidRef.current && map.getSource("counties")) {
        map.setFeatureState({ source: "counties", id: hoverGeoidRef.current }, { hover: false });
        hoverGeoidRef.current = "";
      }
    };

    map.on("mousemove", (e: any) => {
      const feats = map.queryRenderedFeatures(e.point, { layers: interactive() });
      const f = feats[0];
      if (!f) {
        map.getCanvas().style.cursor = "";
        clearHoverStates();
        hoverPopupRef.current?.remove();
        return;
      }
      map.getCanvas().style.cursor = "pointer";
      const layerId = f.layer.id;
      if (layerId === "states-fill") {
        const fips = f.properties.STATEFP as string;
        clearHoverStates();
        hoverFipsRef.current = fips;
        map.setFeatureState({ source: "states", id: fips }, { hover: true });
        const d = dataRef.current;
        const localsHere = d ? d.actions.filter((a) => a.level === "local" && a.state_fips === fips) : [];
        hoverPopupRef.current
          .setLngLat(e.lngLat)
          .setHTML(
            statePopupHTML(
              f.properties.NAME as string,
              (f.properties.status as StateStatusKey) ?? "none",
              (f.properties.tariff as string) ?? "",
              localsHere.length,
              localsHere.filter((a) => isLive(a.status)).length,
              dataRef.current?.footprint?.states[fips]?.twh_2024 ?? null
            )
          )
          .addTo(map);
      } else if (layerId.startsWith("counties-")) {
        const geoid = f.properties.GEOID as string;
        clearHoverStates();
        hoverGeoidRef.current = geoid;
        map.setFeatureState({ source: "counties", id: geoid }, { hover: true });
        hoverPopupRef.current.setLngLat(e.lngLat).setHTML(countyPopupHTML(f.properties)).addTo(map);
      } else if (layerId === "footprint-circles") {
        clearHoverStates();
        const name = dataRef.current?.state_status[f.properties.state_fips]?.name ?? f.properties.abbr;
        hoverPopupRef.current.setLngLat(e.lngLat).setHTML(footprintPopupHTML(f.properties, name)).addTo(map);
      } else {
        clearHoverStates();
        const html = layerId === "outcome-pts" ? outcomePopupHTML(f.properties, false) : localPopupHTML(f.properties, false);
        hoverPopupRef.current.setLngLat(e.lngLat).setHTML(html).addTo(map);
      }
    });

    map.on("mouseout", () => {
      map.getCanvas().style.cursor = "";
      clearHoverStates();
      hoverPopupRef.current?.remove();
    });

    map.on("click", (e: any) => {
      const feats = map.queryRenderedFeatures(e.point, { layers: interactive() });
      const f = feats[0];
      if (!f) return;
      if (f.layer.id === "states-fill") {
        setSelected({ kind: "state", id: f.properties.STATEFP as string });
        return;
      }
      if (f.layer.id.startsWith("counties-")) {
        setSelected({ kind: "county", id: f.properties.GEOID as string });
        return;
      }
      if (f.layer.id === "footprint-circles") {
        setSelected({ kind: "state", id: f.properties.state_fips as string });
        return;
      }
      hoverPopupRef.current?.remove();
      const html = f.layer.id === "outcome-pts" ? outcomePopupHTML(f.properties, true) : localPopupHTML(f.properties, true);
      pinnedPopupRef.current.setLngLat(e.lngLat).setHTML(html).addTo(map);
    });

    return () => {
      roRef.current?.disconnect();
      roRef.current = null;
      map.remove();
      mapRef.current = null;
      (window as any).__dcrMap = null;
    };
  }, [data, geo, outcomesSettled, countiesSettled]); // eslint-disable-line react-hooks/exhaustive-deps

  // Toggle reactions: re-shade counties, filter circles, flip overlays.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const setVis = (id: string, on: boolean) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
    };
    setVis("outcome-pts", showTrace);
    setVis("outcome-lines", showTrace);
    setVis("followup-lines", showTrace);
    setVis("footprint-circles", showFootprint);

    if (map.getSource("counties") && countiesGeo) {
      map.getSource("counties").setData(countiesFC(countiesGeo, display));
    }

    const allowed: string[] = [...LIVE_STATUSES];
    if (includePending) allowed.push("pending");
    if (includeLapsed) allowed.push(...LAPSED_STATUSES);
    const statusFilter: any = ["in", ["get", "status"], ["literal", allowed]];
    const filter: any = showDct
      ? statusFilter
      : ["all", statusFilter, ["!=", ["get", "dataset"], "datacentertracker"]];
    for (const id of ["local-restriction", "local-condition"]) {
      if (map.getLayer(id)) map.setFilter(id, filter);
    }
  }, [showTrace, showDct, includePending, includeLapsed, showFootprint, display, countiesGeo, ready]);

  // Reflect selection as feature-state on the right source.
  const prevSelected = useRef<Selection>(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const apply = (sel: Selection, on: boolean) => {
      if (!sel) return;
      const source = sel.kind === "state" ? "states" : "counties";
      if (map.getSource(source)) map.setFeatureState({ source, id: sel.id }, { selected: on });
    };
    apply(prevSelected.current, false);
    apply(selected, true);
    prevSelected.current = selected;
  }, [selected, ready]);

  // ---- derived view state --------------------------------------------------

  const visibleLocal = (a: ActionRow) =>
    a.level === "local" && (showDct || a.dataset !== "datacentertracker");

  const liveLocalCount = useMemo(
    () => (data ? data.actions.filter((a) => visibleLocal(a) && isLive(a.status)).length : 0),
    [data, showDct] // eslint-disable-line react-hooks/exhaustive-deps
  );
  const documentedLocal = useMemo(
    () => (data ? data.actions.filter(visibleLocal).length : 0),
    [data, showDct] // eslint-disable-line react-hooks/exhaustive-deps
  );
  const countiesShaded = useMemo(
    () => [...display.values()].filter((d) => d.category != null).length,
    [display]
  );
  const statesWithAction = useMemo(
    () => (data ? Object.values(data.state_status).filter((s) => s.status !== "none").length : 0),
    [data]
  );

  const selectedState = selected?.kind === "state" && data ? data.state_status[selected.id] : null;
  const selectedCounty = selected?.kind === "county" ? countyIndex.get(selected.id) ?? null : null;
  const selectedActions = useMemo(() => {
    if (!data || !selected) return [];
    const rows = data.actions.filter((a) => {
      if (selected.kind === "state") return a.state_fips === selected.id && (a.level !== "local" || visibleLocal(a));
      return a.county_fips === selected.id && visibleLocal(a);
    });
    const rank = (s: string) => (isLive(s) ? 0 : s === "pending" ? 1 : 2);
    return rows.sort((a, b) => rank(a.status) - rank(b.status) || (b.date ?? "").localeCompare(a.date ?? ""));
  }, [data, selected, showDct]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    return (
      <div className="my-8 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Couldn't load the restriction dataset ({error}). The map needs{" "}
        <code>/data/data-center-restriction-cost/actions.json</code> — run the pipeline (
        <code>run_all.py</code>) to generate it.
      </div>
    );
  }

  const tariffApproved = data?.counts["tariff_states_approved_eei"] ?? data?.counts["tariff_states_approved"] ?? "—";
  const eeiVintage = (data?.counts["eei_vintage"] as string) ?? "EEI, mid-2026";
  const selectedDisplay = selectedCounty ? display.get(selectedCounty.GEOID) : null;

  return (
    <div className="not-prose lg:relative lg:left-1/2 lg:w-[min(1200px,94vw)] lg:-translate-x-1/2">
      {/* Hero strip */}
      {data && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            [String(liveLocalCount), "Local actions in force today", `of ${documentedLocal} documented — toggles add the rest`],
            [String(countiesShaded), "Counties shaded", "solid = county-wide, striped = town-level"],
            [String(statesWithAction), "States with enacted laws", "restriction, condition, or rollback"],
            [String(tariffApproved), "States with large-load tariffs", String(eeiVintage)],
          ].map(([val, label, sub]) => (
            <div key={label} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
              <div className="font-serif text-xl font-bold text-cobalt">{val}</div>
              <div className="text-[11px] font-semibold leading-tight text-charcoal">{label}</div>
              <div className="text-[10px] text-steel">{sub}</div>
            </div>
          ))}
        </div>
      )}

      {/* Controls */}
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2">
        <label className="flex cursor-pointer items-center gap-1.5 text-[13px] font-semibold text-charcoal">
          <input type="checkbox" checked={includePending} onChange={(e) => setIncludePending(e.target.checked)} className="accent-[#B45309]" />
          Include pending
        </label>
        <label className="flex cursor-pointer items-center gap-1.5 text-[13px] font-semibold text-charcoal">
          <input type="checkbox" checked={includeLapsed} onChange={(e) => setIncludeLapsed(e.target.checked)} className="accent-[#9AA0A6]" />
          Include lapsed
        </label>
        {outcomes && (
          <label className="flex cursor-pointer items-center gap-1.5 text-[13px] font-semibold text-charcoal">
            <input type="checkbox" checked={showTrace} onChange={(e) => setShowTrace(e.target.checked)} className="accent-cobalt" />
            Traced blocked projects
            <span className="text-[11px] font-normal text-steel">
              ({outcomes.projects.length} · dashed = confirmed reroute{outcomes.projects.some((p) => p.followup) ? " · dotted = same developer nearby" : ""})
            </span>
          </label>
        )}
        <label className="flex cursor-pointer items-center gap-1.5 text-[13px] font-semibold text-charcoal">
          <input type="checkbox" checked={showDct} onChange={(e) => setShowDct(e.target.checked)} className="accent-cobalt" />
          Community-tracked rows
          <span className="text-[11px] font-normal text-steel">(datacentertracker.org, sample-audited)</span>
        </label>
        {data?.footprint && (
          <label className="flex cursor-pointer items-center gap-1.5 text-[13px] font-semibold text-charcoal">
            <input
              type="checkbox"
              checked={showFootprint}
              onChange={(e) => setShowFootprint(e.target.checked)}
              className="accent-[#3B3B3B]"
            />
            Where they run today
            <span className="text-[11px] font-normal text-steel">(EPRI, 2024 electricity use)</span>
          </label>
        )}
        <div className="ml-auto">
          <select
            aria-label="Find your state"
            value={selected?.kind === "state" ? selected.id : ""}
            onChange={(e) => setSelected(e.target.value ? { kind: "state", id: e.target.value } : null)}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-charcoal"
          >
            <option value="">Find your state…</option>
            {data &&
              Object.entries(data.state_status)
                .sort((a, b) => a[1].name.localeCompare(b[1].name))
                .map(([fips, s]) => (
                  <option key={fips} value={fips}>
                    {s.name}
                  </option>
                ))}
          </select>
        </div>
      </div>

      {/* How to read */}
      <p className="mb-2 text-xs text-steel">
        <span className="font-semibold text-charcoal">How to read:</span> dark state = state friction, shaded county =
        local friction. Both at once = hardest to build. Zoom in for individual actions.
      </p>

      {/* Map + side panel */}
      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <div className="relative">
          <div ref={mapContainer} className="h-[560px] w-full overflow-hidden rounded-lg border border-gray-200" />
          {/* Legend */}
          <div className="absolute bottom-2 left-2 max-w-[240px] rounded-md border border-gray-200 bg-white/95 px-2.5 py-2 shadow-sm">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-steel">
              State posture — hardest to easiest
            </div>
            {(Object.keys(STATE_STATUS_STYLE) as StateStatusKey[]).map((k) => (
              <div key={k} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm border border-gray-300"
                  style={{ backgroundColor: STATE_STATUS_STYLE[k].color }}
                />
                <span className="text-[9px] leading-tight text-charcoal">{STATE_STATUS_STYLE[k].label}</span>
              </div>
            ))}
            <div className="mb-1 mt-1.5 text-[10px] font-semibold uppercase tracking-wide text-steel">
              County shading — local action in force
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm border border-gray-300"
                style={{ backgroundColor: COUNTY_STYLE.county_restriction.color }}
              />
              <span className="text-[9px] leading-tight text-charcoal">{COUNTY_STYLE.county_restriction.label}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm border border-gray-300"
                style={{
                  background: `repeating-linear-gradient(45deg, ${COUNTY_STYLE.town_restriction.stripe} 0 1.5px, ${COUNTY_STYLE.town_restriction.base} 1.5px 4.5px)`,
                }}
              />
              <span className="text-[9px] leading-tight text-charcoal">{COUNTY_STYLE.town_restriction.label}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm border border-gray-300"
                style={{ backgroundColor: COUNTY_STYLE.conditions_only.color }}
              />
              <span className="text-[9px] leading-tight text-charcoal">{COUNTY_STYLE.conditions_only.label}</span>
            </div>
            {includePending && (
              <div className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm border-2 border-dashed"
                  style={{ borderColor: COUNTY_STYLE.pending_only.outline }}
                />
                <span className="text-[9px] leading-tight text-charcoal">{COUNTY_STYLE.pending_only.label}</span>
              </div>
            )}
            {includeLapsed && (
              <div className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm border border-dotted"
                  style={{ backgroundColor: COUNTY_STYLE.lapsed_only.wash, borderColor: COUNTY_STYLE.lapsed_only.outline }}
                />
                <span className="text-[9px] leading-tight text-charcoal">{COUNTY_STYLE.lapsed_only.label}</span>
              </div>
            )}
            {showFootprint && data?.footprint && (
              <>
                <div className="mb-1 mt-1.5 text-[10px] font-semibold uppercase tracking-wide text-steel">
                  Rings: data center electricity, 2024
                </div>
                <div className="flex items-end gap-2">
                  {[2, 10, 34].map((twh) => (
                    <div key={twh} className="flex flex-col items-center">
                      <span
                        className="inline-block rounded-full border"
                        style={{
                          width: Math.sqrt(twh) * 2 * 3.2,
                          height: Math.sqrt(twh) * 2 * 3.2,
                          borderColor: FOOTPRINT_STYLE.stroke,
                          backgroundColor: FOOTPRINT_STYLE.fill,
                        }}
                      />
                      <span className="text-[8px] text-steel">{twh}</span>
                    </div>
                  ))}
                  <span className="pb-1 text-[8px] text-steel">TWh (EPRI)</span>
                </div>
              </>
            )}
            {showTrace && outcomes && (
              <>
                <div className="mb-1 mt-1.5 text-[10px] font-semibold uppercase tracking-wide text-steel">Blocked projects</div>
                {(Object.keys(OUTCOME_STYLE) as (keyof typeof OUTCOME_STYLE)[]).map((k) => (
                  <div key={k} className="flex items-center gap-1.5">
                    <span
                      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full border border-white shadow-sm"
                      style={{ backgroundColor: OUTCOME_STYLE[k].color }}
                    />
                    <span className="text-[9px] leading-tight text-charcoal">{OUTCOME_STYLE[k].label}</span>
                  </div>
                ))}
                <div className="mt-0.5 flex items-center gap-1.5">
                  <span className="inline-block h-0 w-5 shrink-0 border-t-2 border-dashed" style={{ borderColor: REROUTE_LINE_COLOR }} />
                  <span className="text-[9px] leading-tight text-charcoal">Confirmed reroute</span>
                </div>
                {outcomes.projects.some((p) => p.followup) && (
                  <div className="flex items-center gap-1.5">
                    <span className="inline-block h-0 w-5 shrink-0 border-t-2 border-dotted" style={{ borderColor: FOLLOWUP_LINE_COLOR }} />
                    <span className="text-[9px] leading-tight text-charcoal">Same developer nearby, not confirmed</span>
                  </div>
                )}
              </>
            )}
            <div className="mt-1.5 border-t border-gray-100 pt-1 text-[9px] italic leading-snug text-steel">
              Documented actions, not a census.
              <br />
              As of {data?.snapshot_date ?? "2026-08-15"}.
            </div>
          </div>
        </div>

        {/* Side panel */}
        <div className="h-[560px] overflow-y-auto rounded-lg border border-gray-200 bg-white p-4">
          {!selected ? (
            <div className="flex h-full flex-col items-center justify-center px-4 text-center">
              <p className="text-sm text-steel">
                Click a state or a shaded county — or use <em>Find your state</em> — for its laws and every documented
                local action with sources.
              </p>
            </div>
          ) : (
            <>
              <div className="mb-1 flex items-baseline justify-between">
                <h3 className="font-serif text-lg font-bold text-cobalt">
                  {selectedState ? selectedState.name : selectedCounty ? `${selectedCounty.county_name}, ${selectedCounty.state_abbr}` : "—"}
                </h3>
                <button onClick={() => setSelected(null)} className="text-[11px] text-steel hover:text-cobalt">
                  clear
                </button>
              </div>
              {selectedState && (
                <div className="mb-2 text-[12px] font-semibold text-charcoal">
                  {STATE_STATUS_STYLE[selectedState.status].label}
                  {selectedState.tariff && (
                    <span className="ml-1 font-normal text-[#3B5BD6]">· large-load tariff {selectedState.tariff}</span>
                  )}
                </div>
              )}
              {selectedCounty && (
                <div className="mb-2 text-[12px] text-charcoal">
                  <span className="font-semibold">
                    {selectedDisplay?.category
                      ? COUNTY_STYLE[selectedDisplay.category].label
                      : "No action under current toggles"}
                  </span>
                  <button
                    onClick={() => setSelected({ kind: "state", id: selectedCounty.state_fips })}
                    className="ml-2 text-[11px] text-carolina hover:underline"
                  >
                    view {selectedCounty.state_abbr} statewide
                  </button>
                </div>
              )}
              {selectedActions.length === 0 ? (
                <p className="text-xs text-steel">No documented actions under the current toggles.</p>
              ) : (
                <div className="space-y-2">
                  {selectedActions.map((a) => (
                    <div
                      key={a.id}
                      className={`rounded-md border border-gray-200 p-2 ${isLive(a.status) ? "" : "opacity-60"}`}
                    >
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-[12px] font-bold text-charcoal">{a.jurisdiction}</span>
                        <span
                          className="shrink-0 rounded-sm px-1.5 py-0.5 text-[9px] font-bold uppercase text-white"
                          style={{
                            backgroundColor:
                              a.class === "restriction"
                                ? CLASS_STYLE.restriction.color
                                : a.class === "condition"
                                  ? CLASS_STYLE.condition.color
                                  : STATE_STATUS_STYLE.preemption.color,
                          }}
                        >
                          {a.class}
                        </span>
                      </div>
                      <div className="text-[10px] text-steel">
                        {typeLabel(a.action_type)}
                        {a.status !== "enacted" && ` · ${a.status.replace(/_/g, " ")}`}
                        {a.date && ` · ${a.date}`}
                        {a.mw_threshold != null && ` · ${a.mw_threshold} MW+`}
                        {a.level === "local" && a.county_name && selected.kind === "state" && ` · ${a.county_name}`}
                      </div>
                      <div className="mt-0.5 text-[11px] leading-snug text-charcoal">{a.summary}</div>
                      <a
                        href={a.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-0.5 inline-block text-[10px] text-carolina hover:underline"
                      >
                        {a.source_name || "Source"}
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
      <p className="mt-2 text-[11px] text-steel">
        Sources:{" "}
        <a
          href="https://mjbommar.github.io/moratorium-data-2026/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-carolina hover:underline"
        >
          Moratorium Nation
        </a>{" "}
        by Michael Bommarito, ALEA Institute (CC-BY-4.0);{" "}
        <a
          href="https://datacentertracker.org/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-carolina hover:underline"
        >
          datacentertracker.org
        </a>{" "}
        by Cam Acosta &amp; George Ingebretsen (CC-BY-4.0); electricity rings from{" "}
        <a
          href="https://powering-intelligence.epri.com/dashboard/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-carolina hover:underline"
        >
          EPRI
        </a>
        ; hand-curated state and PUC layers with primary citations. Full dataset and coding rules in the downloads at
        the top of this page.
      </p>
    </div>
  );
}
