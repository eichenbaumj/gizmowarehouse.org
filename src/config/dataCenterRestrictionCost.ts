// Data contract + constants for the data-center-restriction-cost gizmo:
// the national restriction map (<dcr-map />) and the town calculator
// (<dcr-town-calc />).
//
// gizmos/data-center-restriction-cost/verify_claims.py parses the DCR_MODEL
// literal below and asserts every constant matches the pipeline's
// benchmarks.json, so the widget and the downloadable dataset cannot drift.
// Keep values as plain numeric literals on single lines — the verify gate
// reads them by regex.

// ---------------------------------------------------------------------------
// Types mirroring public/data/data-center-restriction-cost/*.json
// ---------------------------------------------------------------------------

export type StateStatusKey =
  | "enacted_restriction"
  | "enacted_conditions"
  | "incentive_rollback"
  | "preemption"
  | "none";

export type ActionClass = "restriction" | "condition" | "preemption";

export interface ActionRow {
  id: string;
  level: "state" | "local" | "puc";
  state_fips: string;
  state: string;
  jurisdiction: string;
  jurisdiction_type: string;
  action_type: string;
  class: ActionClass;
  status: string;
  date: string | null;
  mw_threshold: number | null;
  lat: number | null;
  lon: number | null;
  geocode: string;
  county_fips: string | null;
  county_name: string | null;
  county_wide: boolean;
  summary: string;
  source_url: string;
  source_name: string;
  dataset: string;
}

// Mirrors the pipeline's county_assign.LIVE_STATUSES — an action counts as
// "in force today" only with one of these statuses.
export const LIVE_STATUSES = ["enacted", "in_force"] as const;
export const LAPSED_STATUSES = ["expired", "replaced"] as const;

export type CountyCategory =
  | "county_restriction"
  | "town_restriction"
  | "conditions_only"
  | "pending_only"
  | "lapsed_only";

export interface CountyProps {
  GEOID: string;
  state_fips: string;
  state_abbr: string;
  county_name: string;
  category: CountyCategory;
  n_total: number;
  n_live: number;
  n_pending: number;
  n_lapsed: number;
  n_live_county_restriction: number;
  n_live_town_restriction: number;
  n_live_conditions: number;
  action_ids: string[];
}

export interface StateStatus {
  abbr: string;
  name: string;
  status: StateStatusKey;
  tariff: "approved" | "pending" | null;
  action_ids: string[];
}

export interface FootprintState {
  abbr: string;
  twh_2024: number | null;
  gw_2024_nominal: number | null;
  twh_2030_medium: number | null;
  lat: number | null;
  lon: number | null;
}

export interface FootprintBlock {
  source: string;
  source_url: string;
  year: number;
  projection: string;
  us_twh_2024: number | null;
  us_twh_2030_medium: number | null;
  states: Record<string, FootprintState>;
}

export interface ActionsData {
  snapshot_date: string;
  sources: { id: string; name: string; url: string; license: string; retrieved: string; note: string }[];
  counts: Record<string, number | string>;
  state_status: Record<string, StateStatus>;
  footprint?: FootprintBlock | null;
  actions: ActionRow[];
}

// The footprint rings are neutral ink (charcoal), deliberately outside the
// categorical fill palette so they read as an overlay, not a fifth category.
export const FOOTPRINT_STYLE = { stroke: "#3B3B3B", fill: "rgba(59,59,59,0.16)" };

export type OutcomeKey = "died" | "rerouted" | "delayed_then_built" | "pending_litigating";

// Softest relocation tier: the same developer explicitly reported building or
// seeking a site nearby, not confirmed as the same project. Never changes the
// project's outcome; mutually exclusive with destination (gated in the
// pipeline). distance_mi is computed by the pipeline, never hand-entered.
export interface OutcomeFollowup {
  name: string;
  lat: number;
  lon: number;
  same_metro: boolean;
  distance_mi?: number | null;
  note: string;
  sources: { name: string; url: string }[];
}

export interface OutcomeProject {
  id: string;
  name: string;
  developer: string;
  jurisdiction: string;
  state: string;
  lat: number;
  lon: number;
  claimed_capex_usd_b: number | null;
  capex_label: string | null;
  mw: number | null;
  decision_date: string | null;
  outcome: OutcomeKey;
  destination: { name: string; lat: number; lon: number; same_metro: boolean; distance_mi?: number | null } | null;
  followup?: OutcomeFollowup | null;
  months_lost: number | null;
  confidence: "high" | "medium";
  note: string;
  sources: { name: string; url: string }[];
}

export interface OutcomesData {
  snapshot_date: string;
  tally: Record<OutcomeKey, number>;
  projects: OutcomeProject[];
}

// ---------------------------------------------------------------------------
// Basemap (same CARTO voyager rasters as the other map gizmos)
// ---------------------------------------------------------------------------

export const BASEMAP = {
  tiles: [
    "https://a.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}.png",
    "https://b.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}.png",
    "https://c.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}.png",
    "https://d.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}.png",
  ],
  labels: [
    "https://a.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png",
    "https://b.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png",
    "https://c.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png",
    "https://d.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png",
  ],
  attribution:
    '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
  statesGeoJsonUrl: "/data/us-states.geojson",
  actionsUrl: "/data/data-center-restriction-cost/actions.json",
  outcomesUrl: "/data/data-center-restriction-cost/outcomes.json",
  countiesUrl: "/data/data-center-restriction-cost/counties.geojson",
  bounds: [-128, 23, -66, 50] as [number, number, number, number],
};

// ---------------------------------------------------------------------------
// Colors — validated with the dataviz palette validator (all-pairs, light
// surface): state fills #C4553B/#3B5BD6/#D89020/#1B8A6B pass CVD + normal
// floors; the amber's <3:1 surface contrast is relieved by the labeled legend,
// popups, and the downloadable table. Circle pair passes all checks.
// ---------------------------------------------------------------------------

// Key order IS the legend order: a difficulty ladder, hardest place to build
// at the top, easiest at the bottom (preemption removes the local veto).
export const STATE_STATUS_STYLE: Record<StateStatusKey, { color: string; label: string }> = {
  enacted_restriction: { color: "#C4553B", label: "Statewide restriction in force" },
  incentive_rollback: { color: "#D89020", label: "Incentives paused or narrowed" },
  enacted_conditions: { color: "#3B5BD6", label: "Statewide conditions enacted" },
  none: { color: "#EFEFEA", label: "No enacted state action" },
  preemption: { color: "#1B8A6B", label: "Local restrictions preempted by the state" },
};

// County friction layer. Solid-fill pair #A82818/#7D95E8 passes the palette
// validator all-pairs; town-level uses a red hatch on a near-white base
// (texture is the validator-sanctioned relief — a second red fails CVD checks
// against the amber incentive_rollback states, where 100+ town-level rows
// live). Fallback solid if the hatch moirés at national zoom: #D97B5F
// (validated within the county set; carries the amber caveat).
export const COUNTY_STYLE = {
  county_restriction: { color: "#A82818", label: "County-wide restriction" },
  town_restriction: { stripe: "#A82818", base: "#F7F1EE", label: "Restriction in part of the county" },
  conditions_only: { color: "#7D95E8", label: "Conditions only" },
  pending_only: { outline: "#B45309", label: "Pending only — not yet in force" },
  lapsed_only: { wash: "#E4E2DA", outline: "#9AA0A6", label: "Lapsed — expired or replaced" },
} as const;

export const CLASS_STYLE: Record<"restriction" | "condition", { color: string; label: string }> = {
  restriction: { color: "#A82818", label: "Local restriction (moratorium, ban, rejection)" },
  condition: { color: "#3B5BD6", label: "Local conditions (noise, setback, cooling rules)" },
};

export const OUTCOME_STYLE: Record<OutcomeKey, { color: string; label: string }> = {
  died: { color: "#7A1B10", label: "Died" },
  rerouted: { color: "#1B8A6B", label: "Rerouted" },
  delayed_then_built: { color: "#D89020", label: "Delayed, then built" },
  pending_litigating: { color: "#6B7280", label: "Pending / litigating" },
};

export const REROUTE_LINE_COLOR = "#1B8A6B";
// Followup arcs are annotation ink (same charcoal as FOOTPRINT_STYLE), not a
// fifth category color: the validator's categorical checks don't apply to an
// overlay, and the pair passes the applicable ones (CVD/normal separation vs
// the reroute green and pending gray, ≥3:1 surface contrast). Identity is
// carried by the dotted-vs-dashed pattern plus the legend, never color alone.
export const FOLLOWUP_LINE_COLOR = "#3B3B3B";

// ---------------------------------------------------------------------------
// Town calculator model. Every numeric literal here is locked against
// benchmarks.json by verify_claims.py — single-line literals only.
//
// Regimes are case-anchored per-campus ANNUAL local revenue ranges (not
// per-MW rates — that model is Phase 2, from county CAFRs). Scale multiplies
// the whole campus; 1.0x is a Project Blue-sized campus (~$3.6B build), and
// the slider readout is denominated in announced build cost (capex), because
// that is what the multiplier actually is — displaying MW would imply the
// per-MW model this deliberately isn't.
// Tucson's own local yield (~$15.7M/yr) sits BELOW the Georgia-anchored
// partial-abatement band — tax regime, not facility size, drives the spread,
// which is the point the calculator teaches.
// No counterfactual discount: the calculator assumes a live proposal (the
// situation where a town actually faces the vote, and the same undiscounted
// basis as Pima County's own Project Blue estimate). The would-it-have-come
// question lives in the prose, where the audit evidence is cited.
// ---------------------------------------------------------------------------

export const DCR_MODEL = {
  horizonYears: 10,
  scaleMin: 0.25,
  scaleMax: 4,
  scaleElPasoMeta: 2.8, // ~$10B El Paso Meta campus / $3.6B Project Blue
  referenceCapexUsdB: 3.6, // Project Blue, developer-announced
  referenceMw: 286,
  referenceLocal10yrUsdM: 157, // $97M city + $60M county over 10 years, Pima County FAQ
  jobsPerFacilityPermanent: 50, // JLARC: ~50 permanent workers per typical facility
} as const;

export interface Regime {
  id: string;
  label: string;
  anchor: string;
  lowM: number; // annual local revenue, $M/yr, low end
  highM: number; // annual local revenue, $M/yr, high end
}

export const REGIMES: Regime[] = [
  { id: "aggressive_abatement", label: "Aggressive abatement", anchor: "Morrow County, OR enterprise-zone deal", lowM: 2, highM: 3 },
  { id: "partial_abatement", label: "Partial abatement", anchor: "Georgia audit's representative campus, El Paso Meta", lowM: 27.8, highM: 56 },
  { id: "unabated_equipment_tax", label: "Unabated, equipment-taxed", anchor: "Virginia-style rates (Loudoun is the ceiling)", lowM: 50, highM: 90 },
];

export interface ForegoneResult {
  low10: number; // $M over the horizon
  high10: number;
}

export function computeForegone(regimeId: string, scale: number): ForegoneResult {
  const r = REGIMES.find((x) => x.id === regimeId) ?? REGIMES[1];
  return {
    low10: r.lowM * DCR_MODEL.horizonYears * scale,
    high10: r.highM * DCR_MODEL.horizonYears * scale,
  };
}
