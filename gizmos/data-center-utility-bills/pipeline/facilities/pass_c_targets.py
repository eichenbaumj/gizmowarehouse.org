#!/usr/bin/env python3
"""The fixed target list for the verification pass (docs/DECISIONS.md, D-58, rule 3.1; D-56, ruling 3).

Built from the frozen files of 2026-11-14 and from nothing else, before any lookup of the pass is sent.
Load and sales only; no price is read. It runs no design and recomputes no set.

Hosts: the headline set and the hosts unsettled on assignment (D-50), at the 2% threshold.
Sites, for each host:
  determining       every determining site, however it was placed
  unresolved        (an unsettled host) every unresolved site in its rows, on it or listing it as a candidate
                    territory, that carries load in or before its crossing year plus one
  one_territory     (a current host) every site on it resolved only by lying in one territory that carries
                    load in or before its crossing year plus one

Run:  python3 -I pipeline/facilities/pass_c_targets.py
Output: pipeline/facilities/verified/pass_c_targets.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
OUT = Path(__file__).resolve().parent / "verified" / "pass_c_targets.csv"
RULING_4 = "D-46, ruling 4"
ONE_TERRITORY = "unique"
PERMIT_DATED = "first_generator_permit_plus_lag"


def hosts(headline: pd.DataFrame) -> pd.DataFrame:
    """The hosts of the pass: in the headline set, or kept out of it by ruling 4 and nothing else."""
    h = headline[headline.threshold == "2%"].copy()
    why = h.why_not_in_the_headline_set.fillna("")
    only_r4 = why.map(lambda w: bool(w) and all(x.strip().startswith(RULING_4) for x in w.split(";")))
    h["status"] = ["current host" if a else ("unsettled on assignment" if b else None) for a, b in zip(h.in_headline_set, only_r4)]
    h = h[h.status.notna()]
    h["host"] = [f"{int(u)}:{s}" for u, s in zip(h.utility_id_eia, h.state)]
    return h[["host", "name", "status", "first_crossing"]]


def targets(sites: pd.DataFrame, headline: pd.DataFrame) -> pd.DataFrame:
    h = hosts(headline).set_index("host")
    s = sites[sites.host.isin(h.index)].copy()
    s["status"] = s.host.map(h.status)
    by_then = s.start_year.fillna(9999) <= s.host_first_crossing + 1
    on_host = s.now_on == "this host"
    why = []
    for det, res, how, status, early, on in zip(s.determining_site, s.resolved, s.how_placed, s.status, by_then, on_host):
        if det:
            why.append("determining")
        elif status == "unsettled on assignment" and not res and early:
            why.append("unresolved")
        elif status == "current host" and on and res and how == ONE_TERRITORY and early:
            why.append("one_territory")
        else:
            why.append(None)
    s["why_on_the_list"] = why
    s = s[s.why_on_the_list.notna()]
    s["seeks_date_evidence"] = s.year_rests_on == PERMIT_DATED
    cols = ["host", "host_name", "status", "host_first_crossing", "site", "site_label", "why_on_the_list", "now_on", "how_placed", "resolved",
            "start_year", "year_rests_on", "seeks_date_evidence", "mw_in_the_crossing_year", "share_of_threshold_in_the_crossing_year"]
    return s[cols].sort_values(["status", "host", "why_on_the_list", "mw_in_the_crossing_year"], ascending=[True, True, True, False]).reset_index(drop=True)


def main() -> int:
    t = targets(pd.read_csv(FROZEN / "assignment_evidence_sites.csv"), pd.read_csv(FROZEN / "headline_set.csv"))
    t.to_csv(OUT, index=False)
    print(len(t), "target rows,", t.site.nunique(), "distinct sites, on", t.host.nunique(), "hosts")
    print(t.groupby(["status", "why_on_the_list"]).size().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
