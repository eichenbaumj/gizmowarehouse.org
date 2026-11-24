"""E7 reporting denominator for the set "every cohort utility" (presentation only).

Joe, 2026-11-20 (D-117), item 5: "Settle E7's reporting denominator. For the comparison with the 'every cohort utility as
built' analysis, use the 36 hosts in its reference design as the primary denominator, with the 41-host roster figures
reported beside them and the distinction explained. Retain both sets of existing results. This changes presentation only:
no redraws, new seed, simulation rerun or research-rule change."

This module only reads the stored block E7_every_cohort_utility in data/frozen/inventory_run_designs.json and recomputes
shares from its per-host figures. It draws nothing, takes no seed and imports nothing from inventory_runs. It reads no
price, revenue or bill. PROVISIONAL: the design stands as of 2026-11-18, the plan is a draft and not frozen.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GIZMO = HERE.parent.parent
STORED = GIZMO / "data" / "frozen" / "inventory_run_designs.json"
OUT_FILE = GIZMO / "data" / "frozen" / "e7_reporting_denominator.json"
BLOCK_KEY = "E7_every_cohort_utility"

RULING = ("Settle E7's reporting denominator. For the comparison with the 'every cohort utility as built' analysis, use the "
          "36 hosts in its reference design as the primary denominator, with the 41-host roster figures reported beside them "
          "and the distinction explained. Retain both sets of existing results. This changes presentation only: no redraws, "
          "new seed, simulation rerun or research-rule change.")
ATTRIBUTION = "Joe, 2026-11-20 (D-117)"
PRIMARY_DENOMINATOR = "the hosts in the set's reference design (status 'retained' in the block's reference.hosts)"
BESIDE_DENOMINATOR = "the set's roster (every host in reference.hosts, as design.split gives them)"
DISTINCTION = ("The roster is the set's hosts as design.split gives them. The hosts marked 'out' are on the roster but are not "
               "in the reference design, so they are not in the 'every cohort utility as built' analysis that the figure is "
               "set beside. The primary figure therefore covers the reference-design hosts only; the roster figure, which is "
               "the one E7 stored, is reported beside it.")
SHARES = ("exact", "within_1_year", "true_crossing_2_or_more_years_earlier", "true_crossing_5_or_more_years_earlier",
          "true_crossing_2_or_more_years_later", "never_reaches_the_threshold")
DIRECTIONS = ("earlier", "later")
RETAINED, OUT = "retained", "out"
# Every by_host share and the stored pooled share are rounded to 3 decimals (misdating.describe), so the mean of rounded
# per-host shares can differ from the rounded pooled share by at most 0.0005 + 0.0005.
TOLERANCE = 0.001 + 1e-9


def _refuse(msg: str):
    raise ValueError(msg)


def denominators(block: dict) -> dict:
    """Return, per direction and share, the figure over the reference-design hosts (primary) and over the roster (beside).

    The stored pooled figure is a share of host-draws over the roster. Every roster host has the same number of computed
    draws in a direction (inventory_runs.e7_summary builds each host's errors from the same list of computed draws), so
    that pooled share equals the plain mean of the hosts' shares, up to the 3-decimal rounding. The same plain mean over
    the reference-design hosts gives the primary figure. The input is not changed."""
    if block.get("partial_timing_run") is not False:
        _refuse("This block is not a full run (partial_timing_run is not false); a partial timing run is not reported.")
    hosts = (block.get("reference") or {}).get("hosts")
    if not hosts:
        _refuse("The block has no reference.hosts list.")
    status = {}
    for h in hosts:
        if h.get("status") not in (RETAINED, OUT):
            _refuse(f"Reference host {h.get('utility')!r} has an unknown status {h.get('status')!r}; expected 'retained' or 'out'.")
        if h["utility"] in status:
            _refuse(f"Reference host {h['utility']!r} appears twice.")
        status[h["utility"]] = h["status"]
    retained = [u for u, s in status.items() if s == RETAINED]
    if not retained:
        _refuse("No host is retained in the reference design.")
    dirs = block.get("directions") or {}
    result = {"hosts_in_reference_design": len(retained), "hosts_in_roster": len(status), "directions": {}}
    for d in DIRECTIONS:
        if d not in dirs:
            _refuse(f"The block has no direction {d!r}.")
        dd = dirs[d]
        by_host = dd.get("by_host") or {}
        if set(by_host) != set(status):
            only_b = sorted(set(by_host) - set(status))
            only_r = sorted(set(status) - set(by_host))
            _refuse(f"{d}: by_host and reference.hosts name different hosts (only in by_host: {only_b}; only in reference: {only_r}).")
        if not dd.get("draws_computed"):
            _refuse(f"{d}: no computed draws.")
        pooled = dd.get("set_pooled_over_host_draws")
        if not pooled:
            _refuse(f"{d}: no stored set_pooled_over_host_draws to check against.")
        shares = {}
        for s in SHARES:
            for u in status:
                if not isinstance(by_host[u].get(s), (int, float)):
                    _refuse(f"{d}: host {u!r} has no numeric {s}.")
            if not isinstance(pooled.get(s), (int, float)):
                _refuse(f"{d}: stored pooled figure has no numeric {s}.")
            roster_fig = sum(by_host[u][s] for u in status) / len(status)
            ref_fig = sum(by_host[u][s] for u in retained) / len(retained)
            diff = roster_fig - pooled[s]
            if abs(diff) > TOLERANCE:
                _refuse(f"{d}: {s}: the roster mean recomputed from by_host ({roster_fig:.6f}) differs from the stored "
                        f"set_pooled_over_host_draws ({pooled[s]}) by {diff:+.6f}, more than {TOLERANCE:.4f}. Not reconciled.")
            shares[s] = {"over_reference_design_hosts_primary": ref_fig, "over_roster_beside": roster_fig,
                         "stored_set_pooled_over_host_draws": pooled[s], "roster_recomputed_minus_stored": diff}
        result["directions"][d] = {
            "draws_computed": dd["draws_computed"], "shares": shares,
            "check": {"roster_recomputed_from_by_host_equals_stored_pooled": True, "tolerance": TOLERANCE}}
    result["roster_hosts_not_in_reference_design"] = [
        {"host_record": copy.deepcopy(h),
         "share_of_draws_in_the_design": {d: dirs[d]["by_host"][h["utility"]].get("share_of_draws_in_the_design") for d in DIRECTIONS}}
        for h in hosts if h["status"] == OUT]
    return result


def main() -> int:
    raw = STORED.read_bytes()
    block = json.loads(raw)[BLOCK_KEY]
    res = denominators(block)
    stored_pooled = {d: block["directions"][d]["set_pooled_over_host_draws"] for d in DIRECTIONS}
    doc = {
        "what_this_is": ("Presentation only, derived from the stored block E7_every_cohort_utility with no redraw, no new seed "
                         "and no rerun. PROVISIONAL: the design stands as of 2026-11-18, the plan is a draft and not frozen. "
                         "No price, revenue or bill is read."),
        "ruling": {"words": RULING, "attribution": ATTRIBUTION},
        "primary_denominator": PRIMARY_DENOMINATOR, "reported_beside": BESIDE_DENOMINATOR, "distinction": DISTINCTION,
        "source_file": "data/frozen/inventory_run_designs.json", "source_key": BLOCK_KEY,
        "source_file_sha256": hashlib.sha256(raw).hexdigest(),
        "result": res,
        "existing_results_retained": {
            "roster_pooled_figures_as_stored": stored_pooled,
            "reference_design_figures_as_derived": {d: {s: v["over_reference_design_hosts_primary"] for s, v in res["directions"][d]["shares"].items()}
                                                    for d in DIRECTIONS}}}
    OUT_FILE.write_text(json.dumps(doc, indent=2) + "\n")
    for d in DIRECTIONS:
        sh = res["directions"][d]["shares"]
        print(d, {s: (round(sh[s]["over_reference_design_hosts_primary"], 4), sh[s]["stored_set_pooled_over_host_draws"])
                  for s in ("exact", "within_1_year")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
