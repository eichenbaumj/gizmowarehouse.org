#!/usr/bin/env python3
"""The exact attribution's driver, rerun on the corrections in force with the host list the rebuilt headline set gives.

Load and sales only. Nothing here reads a price or revenue column, opens data/blind, or imports the price code. Nothing
is written under data/.

Why this file exists. `pass_c_exact.main` stops unless the headline set gives exactly `HOSTS_EXPECTED` (26) hosts. That
count was written for the host list of the run of 2026-11-16 and is a guard, not research logic: the hosts enter the
attribution only as labels (the printed summary, the JSON's `hosts` and `counts.hosts`, and the CSV's
`one_of_the_26_hosts` column). Every utility's attribution, reference, count and kept questions is computed per state by
`pass_c_exact.exact_attribution`, which never sees the host list. After the step D rebuild and Stop 3 the headline set
gives a different number of hosts, so this driver does what `pass_c_exact.main` does, line for line, through the same
functions, unchanged, except that it takes the host list as `pass_c_exact.hosts_from_headline` gives it from
data/frozen/headline_set.csv, does not stop on its count, and labels the count in its outputs:

  * the JSON gains one top-level key, `host_list`, with the count, the rule and the source;
  * the printed summary already prints "The <n> hosts:" from the list's length;
  * the CSV keeps pass_c_exact.CSV_COLUMNS unchanged, so every existing reader keeps working: its column
    `one_of_the_26_hosts` marks the hosts of THIS list (the name is kept; `host_list.csv_column_note` says so).

No ceiling, rule, criterion or default is changed. `pass_c_exact.py` is not modified.

Run (all fifty entries of the state table, as the s17 run was):
  python3 -I pipeline/facilities/pass_c_exact_s18.py pipeline/facilities/verified/pass_c_corrections_s17.json \\
      --targets pipeline/facilities/verified/pass_c_targets.csv --out docs/gate1/expansion-test-2026-11-19-s18.json \\
      --csv pipeline/facilities/verified/pass_c_exact_attribution_s18.csv --realise-witnesses --also-states <the 50>
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.facilities import pass_c_exact as pe  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402


def host_list_label(hosts: list, headline: Path = pe.HEADLINE) -> dict:
    """The label written into the JSON: how many hosts, from where, by which rule, and what the CSV column now means."""
    return {"n": len(hosts),
            "source": str(Path(headline).resolve().relative_to(ROOT)) if Path(headline).resolve().is_relative_to(ROOT)
            else str(headline),
            "rule": pe.hosts_from_headline.__doc__,
            "pass_c_exact_HOSTS_EXPECTED": pe.HOSTS_EXPECTED,
            "note": (f"Driven by pipeline/facilities/pass_c_exact_s18.py: the host list is taken as the headline set gives it "
                     f"({len(hosts)} hosts), not checked against pass_c_exact.HOSTS_EXPECTED ({pe.HOSTS_EXPECTED}), a guard "
                     f"written for an earlier host list. The hosts are labels only; no utility's attribution depends on them."),
            "csv_column_note": (f"The CSV column one_of_the_26_hosts keeps its name for existing readers; in this run it marks "
                                f"the {len(hosts)} hosts listed here.")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("corrections")
    ap.add_argument("--targets")
    ap.add_argument("--out")
    ap.add_argument("--csv")
    ap.add_argument("--also-states", help="comma-separated states to run besides those with a correction")
    ap.add_argument("--theta", type=float, default=pe.THETA)
    ap.add_argument("--ceiling", type=int, default=pe.CEILING)
    ap.add_argument("--realise-witnesses", action="store_true",
                    help="rebuild both sides of every witness through scratch_state and assignment.evaluate and compare")
    ap.add_argument("--criterion", choices=pe.CRITERIA, default="either_reading")
    ap.add_argument("--headline", default=str(pe.HEADLINE), help="the headline set the host list is read from")
    a = ap.parse_args(argv)
    out = px.check_out_path(Path(a.out)) if a.out else None
    csv_out = px.check_out_path(Path(a.csv)) if a.csv else None
    t0 = time.time()
    corrections = json.loads(Path(a.corrections).read_text())
    inp = px.load_frozen()
    hosts = pe.hosts_from_headline(pd.read_csv(a.headline))
    states = ([s.strip() for s in a.also_states.split(",") if s.strip()] if a.also_states else sorted({s for _, s in hosts}))
    res = pe.run(corrections, inp, targets=a.targets, states=states, hosts=hosts, theta=a.theta, ceiling=a.ceiling,
                 realise_witnesses=a.realise_witnesses, criterion=a.criterion)
    total = time.time() - t0
    res["json"]["counts"]["seconds"]["total"] = round(total, 2)
    res["json"]["host_list"] = host_list_label(hosts, Path(a.headline))
    print(res["summary"])
    print(f"  host list: {len(hosts)} hosts from {a.headline} (pass_c_exact.HOSTS_EXPECTED is {pe.HOSTS_EXPECTED}; "
          f"not applied by this driver)")
    print(f"  seconds in all (inputs loaded, expand, exact, outputs built): {total:.1f}")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(pe._dumps(res["json"]))
        print("written:", out)
    if csv_out:
        csv_out.parent.mkdir(parents=True, exist_ok=True)
        with csv_out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=pe.CSV_COLUMNS)
            w.writeheader()
            w.writerows(res["csv"])
        print("written:", csv_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
