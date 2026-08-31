// Client-side county category derivation — the TS twin of the pipeline's
// county_assign.aggregate_counties, plus display gating for the map toggles.
//
// The map always derives displayed county categories from actions.json rows
// (never from the baked counties.geojson summary) so the community-rows and
// pending/lapsed toggles re-shade counties consistently with the circles and
// the side panel. verify_claims.py recomputes the python twin against the
// baked file, which pins the two implementations together.

import {
  LAPSED_STATUSES,
  LIVE_STATUSES,
  type ActionRow,
  type CountyCategory,
} from "@/config/dataCenterRestrictionCost";

export interface CountyDisplay {
  category: CountyCategory | null; // null = nothing to show under current toggles
  nLive: number;
  nPending: number;
  nLapsed: number;
  nLiveCountyWide: number;
  nLiveTown: number;
  nLiveConditions: number;
}

export interface DisplayOpts {
  includePending: boolean;
  includeLapsed: boolean;
  showDct: boolean;
}

const live = (s: string) => (LIVE_STATUSES as readonly string[]).includes(s);
const lapsed = (s: string) => (LAPSED_STATUSES as readonly string[]).includes(s);

export function deriveCountyDisplay(
  actions: ActionRow[],
  opts: DisplayOpts
): Map<string, CountyDisplay> {
  const byCounty = new Map<string, ActionRow[]>();
  for (const a of actions) {
    if (a.level !== "local" || !a.county_fips) continue;
    if (!opts.showDct && a.dataset === "datacentertracker") continue;
    const rows = byCounty.get(a.county_fips);
    if (rows) rows.push(a);
    else byCounty.set(a.county_fips, [a]);
  }

  const out = new Map<string, CountyDisplay>();
  for (const [geoid, rows] of byCounty) {
    const liveRows = rows.filter((r) => live(r.status));
    const pendingRows = rows.filter((r) => r.status === "pending");
    const lapsedRows = rows.filter((r) => lapsed(r.status));
    const liveRestr = liveRows.filter((r) => r.class === "restriction");
    const liveCond = liveRows.filter((r) => r.class === "condition");
    const nLiveCountyWide = liveRestr.filter((r) => r.county_wide).length;

    let category: CountyCategory | null;
    if (nLiveCountyWide > 0) category = "county_restriction";
    else if (liveRestr.length > 0) category = "town_restriction";
    else if (liveCond.length > 0) category = "conditions_only";
    else if (pendingRows.length > 0) category = opts.includePending ? "pending_only" : null;
    else category = opts.includeLapsed ? "lapsed_only" : null;

    out.set(geoid, {
      category,
      nLive: liveRows.length,
      nPending: pendingRows.length,
      nLapsed: lapsedRows.length,
      nLiveCountyWide,
      nLiveTown: liveRestr.length - nLiveCountyWide,
      nLiveConditions: liveCond.length,
    });
  }
  return out;
}
