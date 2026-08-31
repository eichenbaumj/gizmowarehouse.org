// Concentration math helpers — surface "X% of subject enrollees live in Y%
// of counties" stats that mirror NPE's load-bearing callout.
//
// Inputs come from medicaid-state-summary.json's `concentration` block, which
// the bake script precomputes at top-N values [5, 10, 25, 50, 100, 250, 500].

export interface ConcentrationData {
  share_in_top_n_counties: Record<string, number>;
  p90_county_subject_count?: number;
  p95_county_subject_count?: number;
  p99_county_subject_count?: number;
}

const NATIONAL_COUNTIES = 3109; // CONUS counties (NPE geometry source)

/** Find the smallest top-N where share ≥ targetShare. Returns null if none. */
export function topNForShare(
  data: ConcentrationData,
  targetShare: number,
): { n: number; share: number; pctOfCounties: number } | null {
  const entries = Object.entries(data.share_in_top_n_counties)
    .map(([k, v]) => [Number(k), Number(v)] as [number, number])
    .sort((a, b) => a[0] - b[0]);
  for (const [n, share] of entries) {
    if (share >= targetShare) {
      return {
        n,
        share,
        pctOfCounties: n / NATIONAL_COUNTIES,
      };
    }
  }
  return null;
}

/** Headline callout phrase. e.g. "70% of subject enrollees live in just 12% of US counties." */
export function concentrationCalloutText(data: ConcentrationData | undefined): string | null {
  if (!data) return null;
  // Find the top-N that captures ~70% of subject (a dramatic, clear stat)
  const result = topNForShare(data, 0.70);
  if (!result) return null;
  const sharePct = (result.share * 100).toFixed(0);
  const countyPct = (result.pctOfCounties * 100).toFixed(1);
  return `${sharePct}% of subject enrollees live in just ${countyPct}% of US counties — the top ${result.n}.`;
}
