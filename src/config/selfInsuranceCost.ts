// Constants and types for the self-insurance-cost gizmo.
//
// Numeric literals here are single-line so gizmos/self-insurance-cost/verify_claims.py can
// read them by regex and lock them to the pipeline's JSON. Bump DATA_VERSION on every
// re-export so Lovable's edge cache serves the new JSON.

export const DATA_VERSION = 2;
export const dataUrl = (name: "ny_entities" | "ntd_agencies" | "models" | "attribution" | "ny_switchers") =>
  `/data/self-insurance-cost/${name}.json?v=${DATA_VERSION}`;

// Headline numbers (locked to public/data/self-insurance-cost/models.json by verify_claims.py)
export const SIC_MODEL = {
  snapshotDate: "2026-10-08",
  windowStart: 2015,
  windowEnd: 2024,
  nCountiesRead: 57,
  nRead: 135,
  nTransitRead: 104,
  coreSelf: 35,
  coreCovered: 49,
  ratioCentral: 1.224,
  ratioLow: 0.831,
  ratioHigh: 2.018,
  swingSelf: 0.514,
  swingCovered: 0.232,
  swingMatched: 1.809,
  worstSelf: 2.041,
  worstCovered: 1.409,
  policeDeptRatio: 2.359,
} as const;

// Structure palette. Validated with the dataviz skill's validator (2026-10-08): Cobalt vs Carolina pass the
// colorblind and normal-vision separation checks; Carolina needs label relief (direct labels + static table).
// Charcoal reads as gray, so "unclear" rows get a neutral hollow marker rather than a third hue.
export const STRUCTURE_STYLE = {
  self: { color: "#1F1FD6", label: "Carries its own liability" },
  covered: { color: "#21A8E0", label: "Buys coverage from a pool or insurer" },
  other: { color: "#AEB9D6", label: "Unclear or mixed (hollow)" },
} as const;
export type Treat = keyof typeof STRUCTURE_STYLE;

export interface NyEntityRow {
  cls: "county" | "city" | "town" | "village";
  muni_code: string;
  entity_name: string;
  county: string;
  region: string;
  pop_mean: number | null;
  pop_bin: number | null;
  n_years: number;
  cor_liab_pc_mean: number | null;
  ins_liab_pc_mean: number | null;
  jc_liab_pc_mean: number | null;
  cor_liab_pc_max: number | null;
  cor_liab_pc_p90: number | null;
  cor_liab_share_mean: number | null;
  cor_pc_mean: number | null;
  cor_op_pc_mean: number | null;
  cor_liab_budget_share: number | null;
  worst_year_budget_share: number | null;
  has_police_dept: boolean | null;
  structure: string;
  structure_raw: string | null;
  sir_per_occurrence: string | null;
  pool_name: string | null;
  nymir_member: boolean | null;
  label_source: "document" | "inferred" | "unknown";
  sig_structure: string;
  jc_contaminated: boolean;
  coded_elsewhere_holdout: boolean;
  premiums_elsewhere_holdout: boolean | null;
  holdout_reason: string | null;
  in_label_rule: boolean | null;
  plotted: boolean;
  n_neg_years?: number | null;
  worst_fy?: number | null;
  worst_over_mean?: number | null;
  swing?: number | null;
  treat: "self" | "covered" | "other";
}
export interface GroupSummary {
  n: number; n_county: number; n_city: number;
  median_cor_pc: number; median_ins_pc: number; median_jc_pc: number; median_max: number;
  mean_cor_pc: number; mean_ins_pc: number; mean_jc_pc: number; premium_share_of_cost: number;
}
export interface NyEntitiesData {
  snapshot: string;
  window: [number, number];
  rows: NyEntityRow[];
  summary: Partial<Record<"self" | "covered", GroupSummary>>;
  summary_by_class: Record<string, Partial<Record<"self" | "covered", { n: number; median_cor_pc: number; median_ins_pc: number; median_jc_pc: number; median_max: number }>>>;
  bins: Record<string, Partial<Record<"self" | "covered", { n: number; mean_cor_pc: number; median_cor_pc: number }>>>;
  holdouts: { entity_name: string; structure: string; holdout_reason: string }[];
  thin: { entity_name: string; n_years: number }[];
  years: number[];
  series: Record<string, (number | null)[]>;
  pop_bins: number[];
}
export interface NtdAgencyRow {
  ntd_id: string; agency: string; city: string; state: string; structure: string;
  label_source: "document" | "unknown"; cl_share: number; cl_per_vrm: number; vrm: number;
  total_opex: number; cl_expense: number; n: number; cap_type?: string | null;
}
export interface NtdAgenciesData { snapshot: string; years: string[]; rows: NtdAgencyRow[] }
export interface ModelSpec {
  spec_id: string; outcome?: string; sample?: string; estimator?: string; n_self?: number; n_covered?: number;
  coef: number | null; lo: number | null; hi: number | null; n?: number; perm_p?: number | null; exploratory?: boolean;
  strata?: { stratum: string; n_self: number; n_covered: number; self: number; covered: number }[] | null;
}
export interface VolatilityData {
  yoy_cv_self: number; yoy_cv_covered: number; n_self: number; n_covered: number;
  max_over_mean_self: number; max_over_mean_covered: number; p90_over_mean_self: number; p90_over_mean_covered: number;
  matched_ratio: number; matched_lo: number; matched_hi: number;
  controlled_ratio: number; controlled_lo: number; controlled_hi: number;
  left_out: { muni_code: string; entity_name: string; cls: string; treat: string; n_neg_years: number }[];
  by_class: Record<string, { n_self: number; n_covered: number; yoy_cv_self: number | null; yoy_cv_covered: number | null; max_over_mean_self: number | null; max_over_mean_covered: number | null }>;
}
export interface ModelsData {
  snapshot: string;
  ny: { specs: ModelSpec[]; sample: Record<string, unknown>; volatility?: VolatilityData;
        exposure?: Record<string, unknown>;
        heterogeneity?: Record<string, { n: number; n_self: number; n_covered: number; ratio: number; lo: number; hi: number; matched: number | null }> };
  ntd: Record<string, unknown>;
}

export const POP_BIN_LABELS = ["under 2,500", "2,500 to 10,000", "10,000 to 50,000", "50,000 to 150,000", "150,000 and up"];
