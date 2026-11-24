#!/usr/bin/env python3
"""The availability audit's full-scale synthetic exercise (D-74; D-75 item 3). Invented data only.

    python3 -I tests/availability_scale.py --out <empty scratch folder> [--units 3300] [--raw-rows 1500000] [--seed 20261116]

Builds a made-up warehouse tree in --out, shaped like the real one: copies of the availability code, a made-up
ledger whose entry pins those copies, an invented raw sales table, and outcome and quantities files built from it
as the panel build would. The table has about 3,300 utility-states over 2001 to 2025 by default, with every
customer class and service type, partial spans, mergers, imputed and unflagged rows, missing revenue, and varied
names and codes, padded with invented supplier rows to about 1.5 million rows. Then it runs P1, P2 and preservation
through the real launch route, each under `/usr/bin/time -l -o <file>`, which reports the peak resident memory of
the whole launched step into a file of its own, so the step's standard error is captured apart from it. It records
elapsed time, peak memory, output sizes, exit codes, whether each step printed exactly its permitted lines (every
line of all three steps is matched against a pattern, preservation's included) and whether its standard error was
empty, against the engineering targets fixed beforehand (D-75):

    P1 within 20 minutes and 8 GB; P2 within 2 minutes; preservation within 2 minutes.

What it shows is capacity for the structure it builds, at the sizes it was run at. It does not show that the real
table is no larger, and it is not a general threshold (D-76, G9). `--units` fixes the number of utility-states, and
with it the utility rows, the panel rows and the number of outcome files; `--raw-rows` above that only adds
supplier rows. So two runs that differ in `--raw-rows` alone compare supplier padding and nothing else: their
difference in memory says nothing about a table with more utilities, more years or other grouping. A miss is an
implementation or resource decision for Joe, never a reason to shrink the research sample.

This is not collected by pytest (its name does not start with "test_"); it takes minutes. It never opens anything
under this repository's data/.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import test_availability_runs as T  # noqa: E402

from pipeline.electricity import availability_codes as av  # noqa: E402
from pipeline.electricity import panel  # noqa: E402
from pipeline.electricity import succession as succ  # noqa: E402

TARGETS = {"p1": {"seconds": 20 * 60, "bytes": 8 * 1024 ** 3}, "p2": {"seconds": 120, "bytes": None},
           "preserve": {"seconds": 120, "bytes": None}}
YEARS = np.arange(2001, 2026)
CLASSES = ("residential", "commercial", "industrial", "transportation")
ENTITIES = ("Investor Owned", "Cooperative", "Municipal", "Political Subdivision", "State", "Federal")


def words(rng, n, lo=4, hi=40):
    letters = np.array(list("abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ-&."))
    lengths = rng.integers(lo, hi, n)
    return ["".join(rng.choice(letters, k)) for k in lengths]


def invent_sales(n_units: int, raw_rows: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(raw sales rows, succession table). Every value invented."""
    rng = np.random.default_rng(seed)
    states = [a + b for a in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for b in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"][:51]
    ba_codes = words(rng, 60, 3, 6)
    ids = rng.choice(np.arange(10_000, 99_999), n_units, replace=False)
    unit_state = rng.choice(states, n_units)
    ent = rng.choice(ENTITIES, n_units, p=[.15, .35, .3, .1, .05, .05])
    names = words(rng, n_units)
    first = np.where(rng.random(n_units) < 0.85, 2001, rng.integers(2002, 2020, n_units))
    last = np.where(rng.random(n_units) < 0.8, 2025, rng.integers(2010, 2025, n_units))
    last = np.maximum(last, first)
    cust = np.exp(rng.normal(9, 1.6, n_units)).astype(int) + 100
    rows = []
    for i in range(n_units):
        yrs = YEARS[(YEARS >= first[i]) & (YEARS <= last[i])]
        k = len(yrs)
        base = dict(utility_id_eia=int(ids[i]), state=unit_state[i], entity_type=ent[i], utility_name_eia=names[i])
        for cls, svc, share, frac in (("residential", "bundled", 1.0, 1.0), ("residential", "delivery", 0.3, 0.25),
                                      ("commercial", "bundled", 1.0, 0.6), ("commercial", "delivery", 0.3, 0.3),
                                      ("industrial", "bundled", 0.9, 0.8), ("industrial", "delivery", 0.3, 0.4),
                                      ("transportation", "bundled", 0.1, 0.01)):
            if rng.random() >= share:
                continue
            c = (cust[i] * frac * rng.uniform(0.9, 1.1, k)).astype(int)
            mwh = c * rng.uniform(8, 14, k)
            rev = mwh * rng.uniform(60, 180, k)
            rev[rng.random(k) < 0.005] = np.nan
            obs = rng.choice(np.array([True, False, None], dtype=object), k, p=[0.97, 0.02, 0.01])
            for j in range(k):
                rows.append({**base, "year": int(yrs[j]), "customer_class": cls, "service_type": svc, "data_observed": obs[j],
                             "balancing_authority_code_eia": ba_codes[(i + j) % 60], "customers": int(c[j]), "sales_mwh": float(mwh[j]),
                             "sales_revenue": float(rev[j])})
    units = pd.DataFrame(rows)
    pad = max(0, raw_rows - len(units))
    sup = pd.DataFrame({
        "utility_id_eia": rng.integers(900_000, 999_999, pad), "state": rng.choice(states, pad), "year": rng.choice(YEARS, pad),
        "customer_class": rng.choice(CLASSES[:3], pad), "service_type": "energy", "entity_type": "Retail Power Marketer",
        "data_observed": rng.choice(np.array([True, False, None], dtype=object), pad, p=[0.9, 0.08, 0.02]),
        "utility_name_eia": rng.choice(words(rng, 2_000), pad), "balancing_authority_code_eia": rng.choice(ba_codes, pad),
        "customers": rng.integers(1, 5_000, pad), "sales_mwh": rng.uniform(1, 50_000, pad)})
    sup["sales_revenue"] = sup.sales_mwh * rng.uniform(40, 140, pad)
    # Mergers: 50 predecessors summed into a successor in the same state.
    by_state = pd.DataFrame({"id": ids, "state": unit_state}).groupby("state").id.apply(list)
    pairs = []
    for st, members in by_state.items():
        if len(members) >= 2 and len(pairs) < 50:
            pairs.append((int(members[0]), st, int(members[1])))
    table = pd.DataFrame([{**T.syn.SUCCESSION_ROW, "predecessor_id": p, "state": st, "successor_id": s,
                           "predecessor_name": f"U{p}", "successor_name": f"U{s}"} for p, st, s in pairs], columns=succ.COLUMNS)
    return pd.concat([units, sup], ignore_index=True), table


def make_scale_tree(out: Path, n_units: int, raw_rows: int, seed: int) -> tuple[Path, dict]:
    t = out / "repo" / "gizmos" / "gizmo"
    for rel in T.CODE:
        (t / rel).parent.mkdir(parents=True, exist_ok=True)
        if rel != "pipeline/electricity/succession.csv":
            (t / rel).write_bytes((ROOT / rel).read_bytes())
    sales, table = invent_sales(n_units, raw_rows, seed)
    table.to_csv(t / "pipeline/electricity/succession.csv", index=False)
    raw = t / "data/raw/pudl"
    raw.mkdir(parents=True)
    T.syn.write_sales_parquet(sales, raw / "core_eia861__yearly_sales.parquet")
    loaded = panel.load_sales(raw / "core_eia861__yearly_sales.parquet")
    q, o = panel.build(loaded, succession=succ.resolve(succ.load(t / "pipeline/electricity/succession.csv")))
    old = panel.INTERIM, panel.BLIND
    try:
        panel.INTERIM, panel.BLIND = t / "data/interim", t / "data/blind"
        panel.write(q.drop(columns=list(av.NEW_QUANTITY_COLS)), o)
    finally:
        panel.INTERIM, panel.BLIND = old
    (out / "home" / ".claude" / "projects" / T.SLUG / "access-records").mkdir(parents=True)
    T.write_ledger(t)
    shape = {"raw_rows": int(len(sales)), "unit_rows_in_raw": int((sales.service_type != "energy").sum()),
             "supplier_padding_rows_in_raw": int((sales.service_type == "energy").sum()),
             "utility_states_in_panel": int(q[["utility_id_eia", "state"]].drop_duplicates().shape[0]),
             "panel_rows": int(len(q)), "by_unit_files": len(list((t / "data/blind/outcomes_by_unit").iterdir())),
             "raw_file_bytes": (raw / "core_eia861__yearly_sales.parquet").stat().st_size, "mergers": int(len(table))}
    return t, shape


def timed(cmd: list[str], env: dict, usage: Path) -> dict:
    """Run one step under /usr/bin/time, whose report goes to `usage`, so the step's own standard error is kept whole."""
    start = time.monotonic()
    r = subprocess.run(["/usr/bin/time", "-l", "-o", str(usage), *cmd], capture_output=True, text=True, env=env, timeout=3600)
    elapsed = time.monotonic() - start
    m = re.search(r"(\d+)\s+maximum resident set size", usage.read_text() if usage.exists() else "")
    return {"exit": r.returncode, "seconds": round(elapsed, 1), "peak_bytes": int(m.group(1)) if m else None,
            "stdout": r.stdout, "stderr": r.stderr}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--units", type=int, default=3300)
    ap.add_argument("--raw-rows", type=int, default=1_500_000)
    ap.add_argument("--seed", type=int, default=20261116)
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() and any(out.iterdir()):
        print(f"--out must be empty: {out}")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    t, shape = make_scale_tree(out, a.units, a.raw_rows, a.seed)
    shape["seconds_to_build_the_invented_tree"] = round(time.monotonic() - t0, 1)
    env = T.env_for(t)
    launcher = str(t / "pipeline/electricity/run_availability.sh")
    steps = {
        "p1": (timed(["sh", launcher, "p1", "--authorized-by", T.AUTH], env, out / "time_p1.txt"), T.P1_OK),
        "p2": (timed(["sh", launcher, "p2", "--authorized-by", T.AUTH], env, out / "time_p2.txt"), T.P2_OK),
        "preserve": (timed([os.path.realpath(sys.executable), "-I", "-B", str(t / "pipeline/electricity/preserve_availability.py"),
                            "--authorized-by", T.AUTH, "--to", str(out / "preserved")], env, out / "time_preserve.txt"), T.PRESERVE_OK),
    }
    report = {"what_this_is": "The availability audit's full-scale synthetic exercise (D-75 item 3). Invented data only. Capacity "
                              "for this invented structure at this size; it does not show that the real table is no larger, and "
                              "it is not a general threshold (D-76, G9).",
              "targets": TARGETS, "shape": shape, "steps": {}}
    for name, (res, patterns) in steps.items():
        got = res.pop("stdout").strip().splitlines()
        err = res.pop("stderr")
        tgt = TARGETS[name]
        res.update({"permitted_lines_only": len(got) == len(patterns) and all(re.fullmatch(p, g) for p, g in zip(patterns, got)),
                    "stdout_lines": len(got), "stderr_empty": err == "", "stderr_bytes": len(err.encode()),
                    "within_time": res["seconds"] <= tgt["seconds"],
                    "within_memory": None if tgt["bytes"] is None or res["peak_bytes"] is None else res["peak_bytes"] <= tgt["bytes"]})
        report["steps"][name] = res
    files = {"quantities": t / "data/interim/panel_quantities.parquet", "mask": t / "data/interim/availability/outcome_availability.csv",
             "sidecar": t / "data/interim/availability/outcome_availability.json", "p1_record": t / "data/interim/availability/p1_record.json"}
    report["output_bytes"] = {k: (f.stat().st_size if f.exists() else None) for k, f in files.items()}
    report["all_within_targets"] = all(s["exit"] == 0 and s["permitted_lines_only"] and s["stderr_empty"] and s["peak_bytes"] is not None
                                       and s["within_time"] and s["within_memory"] is not False for s in report["steps"].values())
    (out / "scale_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "what_this_is"}, indent=2))
    return 0 if report["all_within_targets"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
