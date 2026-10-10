// Shared model for the swing exhibit (<sic-volatility>): which governments are drawn, the group summaries, and the
// deterministic one-sided beeswarm. The component, the static stand-in, and the test all call these, so the
// chart, the crawler table, and models.json cannot drift apart.
//
// x = a government's costliest year in 2015 to 2024 divided by its own ten-year average (worst_over_mean, from
// stage 10). A government with a negative year (a reserve release booked as a negative claim) has no meaningful
// average: it is counted, left out of the drawing, and named in the note (stage 07 `volatility.left_out`).

import type { NyEntityRow } from "@/config/selfInsuranceCost";

export type Side = "self" | "covered";
export type ClassKey = "county" | "town" | "city" | "village";

export const SIDES: Side[] = ["self", "covered"];
export const CLASS_NAME: Record<ClassKey, [string, string, string]> = {
  county: ["Counties", "county", "counties"],
  town: ["Towns", "town", "towns"],
  city: ["Cities", "city", "cities"],
  village: ["Villages", "village", "villages"],
};
export const MIN_TICK = 5; // a half needs this many governments before a "typical" tick stands in for it
export const THIN_JUDGE = 3; // a band whose thinner half has fewer than this gets the "too few to judge" flag
export const X_LO = 1;
export const X_HI = 5;

export interface SwingRow {
  muni: string;
  name: string;
  cls: ClassKey;
  side: Side;
  pop: number;
  mean: number;
  max: number;
  ratio: number; // worst year / average
  swing: number; // sample std / mean over the window
  worstFy: number | null;
  budget: number | null; // (worst year - average) as a share of a year's spending
}

export interface LeftOut {
  name: string;
  cls: ClassKey;
  side: Side;
  nNeg: number;
}

export interface Half {
  n: number;
  ratio: number | null; // median worst year / average
  swing: number | null; // median swing
  ratios: number[];
  swings: number[];
}

type SwingFields = { worst_over_mean?: number | null; swing?: number | null; worst_fy?: number | null; n_neg_years?: number | null };

export function swingRows(rows: (NyEntityRow & SwingFields)[]): { drawn: SwingRow[]; leftOut: LeftOut[] } {
  const drawn: SwingRow[] = [];
  const leftOut: LeftOut[] = [];
  for (const r of rows) {
    if (!r.plotted || (r.treat !== "self" && r.treat !== "covered")) continue;
    if ((r.n_neg_years ?? 0) > 0) {
      leftOut.push({ name: r.entity_name, cls: r.cls as ClassKey, side: r.treat, nNeg: r.n_neg_years ?? 0 });
      continue;
    }
    if (r.worst_over_mean == null || r.swing == null) continue;
    drawn.push({
      muni: r.muni_code, name: r.entity_name, cls: r.cls as ClassKey, side: r.treat, pop: r.pop_mean ?? 0,
      mean: r.cor_liab_pc_mean ?? 0, max: r.cor_liab_pc_max ?? 0, ratio: r.worst_over_mean, swing: r.swing,
      worstFy: r.worst_fy ?? null, budget: r.worst_year_budget_share ?? null,
    });
  }
  return { drawn, leftOut };
}

const median = (xs: number[]): number | null => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

export function summarize(rows: SwingRow[]): Record<"all" | ClassKey, Record<Side, Half>> {
  const keys: ("all" | ClassKey)[] = ["all", "county", "town", "city", "village"];
  const out = {} as Record<"all" | ClassKey, Record<Side, Half>>;
  for (const k of keys) {
    out[k] = {} as Record<Side, Half>;
    for (const s of SIDES) {
      const g = rows.filter((r) => r.side === s && (k === "all" || r.cls === k));
      out[k][s] = {
        n: g.length, ratio: median(g.map((r) => r.ratio)), swing: median(g.map((r) => r.swing)),
        ratios: g.map((r) => r.ratio).sort((a, b) => a - b), swings: g.map((r) => r.swing).sort((a, b) => a - b),
      };
    }
  }
  return out;
}

/** Classes ordered by drawn headcount, so the thin ones fall to the bottom. */
export function classOrder(S: Record<"all" | ClassKey, Record<Side, Half>>): ClassKey[] {
  return (Object.keys(CLASS_NAME) as ClassKey[]).sort((a, b) => S[b].self.n + S[b].covered.n - (S[a].self.n + S[a].covered.n));
}

/** Greedy one-sided beeswarm: each dot (in x order) takes the lowest offset that clears every earlier dot. */
export function swarmOneSided(xs: number[], d: number): number[] {
  const placed: [number, number][] = [];
  const out: number[] = [];
  for (const x of xs) {
    const cands = [0];
    for (const [px, py] of placed) {
      const dx = Math.abs(x - px);
      if (dx < d) cands.push(py + Math.sqrt(d * d - dx * dx));
    }
    cands.sort((a, b) => a - b);
    let y = cands[cands.length - 1];
    for (const c of cands) {
      if (placed.every(([px, py]) => (x - px) ** 2 + (c - py) ** 2 >= d * d - 1e-6)) {
        y = c;
        break;
      }
    }
    placed.push([x, y]);
    out.push(y);
  }
  return out;
}

const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];
export const word = (n: number) => (n >= 0 && n < 10 ? WORDS[n] : String(n));
export const fx = (v: number) => `${v.toFixed(1)}×`;
export const halfRound = (v: number) => Math.round(v * 2) / 2;
const fnum = (v: number) => String(+v.toFixed(1));

export function countPhrase(n: number, s: Side): string {
  if (s === "self") return n === 1 ? `${n} carries its own` : `${n} carry their own`;
  return n === 1 ? `${n} buys coverage` : `${n} buy coverage`;
}

export function shortName(name: string, countySuffix = false): string {
  for (const pre of ["County of ", "City of ", "Town of ", "Village of "]) {
    if (name.startsWith(pre)) {
      const base = name.slice(pre.length);
      return countySuffix && pre === "County of " ? `${base} County` : base;
    }
  }
  return name;
}

/** The "too few to judge" flag for a band, or null. */
export function thinFlag(k: ClassKey, S: Record<"all" | ClassKey, Record<Side, Half>>): string | null {
  const thin: Side = S[k].self.n <= S[k].covered.n ? "self" : "covered";
  const n = S[k][thin].n;
  if (n >= THIN_JUDGE) return null;
  const [, sing, plur] = CLASS_NAME[k];
  const verb = thin === "covered" ? (n === 1 ? "buys coverage" : "buy coverage") : n === 1 ? "carries its own liability" : "carry their own liability";
  return `Only ${word(n)} ${n === 1 ? sing : plur} ${verb}, too few to judge on ${n === 1 ? "its" : "their"} own.`;
}

export interface SwingModelNumbers {
  matched_ratio: number; matched_lo: number; matched_hi: number;
  controlled_ratio: number; controlled_lo: number; controlled_hi: number;
}

/** Subtitle and footnote copy, generated from the data (nothing hard-coded). */
export function swingCopy(rows: SwingRow[], leftOut: LeftOut[], v: SwingModelNumbers): { sub: string; foot: string } {
  const S = summarize(rows);
  // one decimal when the two estimates agree there (1.81 and 1.82 -> "about 1.8 times"), else the half-rounded pair
  const [a1, b1] = [v.controlled_ratio, v.matched_ratio].map((x) => Math.round(x * 10) / 10).sort((a, b) => a - b);
  const [lo, hi] = [halfRound(v.controlled_ratio), halfRound(v.matched_ratio)].sort((a, b) => a - b);
  const swing = a1 === b1 ? `about ${a1.toFixed(1)} times` : lo === hi ? `about ${fnum(lo)} times` : `about ${fnum(lo)} to ${fnum(hi)} times`;
  const rlo = Math.min(v.matched_lo, v.controlled_lo), rhi = Math.max(v.matched_hi, v.controlled_hi);
  const a = S.all;
  const sub =
    `Each dot is one government, placed by its costliest year as a multiple of its own ten-year average. ` +
    `The typical self-insured government's worst year cost ${(a.self.ratio ?? 0).toFixed(1)} times its average; ` +
    `a covered government's, ${(a.covered.ratio ?? 0).toFixed(1)} times.`;
  const thin = (Object.keys(CLASS_NAME) as ClassKey[])
    .filter((k) => S[k].covered.n < THIN_JUDGE)
    .map((k) => `${word(S[k].covered.n)} ${S[k].covered.n === 1 ? CLASS_NAME[k][1] : CLASS_NAME[k][2]}`);
  const thinSentence = thin.length
    ? ` Only ${thin.join(" and ")} ${thin.length === 1 && thin[0].startsWith("one ") ? "buys" : "buy"} coverage, too few to judge ${thin.length === 1 ? "that type" : "those types"} on their own.`
    : "";
  const loSentence = leftOut
    .map((q) => ` ${shortName(q.name, true)} is left out because its recorded cost fell below zero in ${word(q.nNeg)} of the ten years, leaving no meaningful average.`)
    .join("");
  const foot =
    `Across all ten years, a self-insured bill typically lands ${swing} as far from its own average as a covered bill of the same type and size ` +
    `(the data allow about ${rlo.toFixed(1)} to ${rhi.toFixed(1)} times). ` +
    "Liability cost is insurance premiums plus judgments and claims per resident, in 2024 dollars, from filings with the State Comptroller; " +
    `each arrangement was read from audited statements. The dark tick marks the middle government of a group of ${word(MIN_TICK)} or more.` +
    thinSentence + loSentence + " Tap or hover over a dot for its numbers.";
  return { sub, foot };
}
