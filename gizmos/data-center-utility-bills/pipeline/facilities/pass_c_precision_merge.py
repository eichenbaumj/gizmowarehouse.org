#!/usr/bin/env python3
"""Carry the precision fields onto each layer-based record (docs/DECISIONS.md, D-65 item 2; D-66 section 5; D-69).

`pass_c_precision.py` writes one row per site and layer to verified/pass_c_layer_precision.csv. This script folds those
rows into five columns of verified/pass_c_layer_conditions.csv, one row per site, so the record itself carries them.
It fetches nothing, changes no other column, and can be run again after any rerun of the precision script. Nothing
under data/ is read.

Run:  python3 -I pipeline/facilities/pass_c_precision_merge.py [--check]
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONDITIONS = HERE / "verified" / "pass_c_layer_conditions.csv"
PRECISION = HERE / "verified" / "pass_c_layer_precision.csv"
NEW = ["location_uncertainty", "nearest_drawn_line_m_by_layer", "publishers_on_accuracy_and_completeness",
       "conflicting_geometry", "precision_limitation"]
csv.field_size_limit(10 ** 9)


def _line(r: dict) -> str:
    name = r["layer_name"] or "no layer"
    lo, hi = r["nearest_line_m_low"], r["nearest_line_m_high"]
    if not lo and not hi:
        return f"{name}: {r['at_point']}"
    span = lo if lo == hi or not hi else f"{lo} to {hi}"
    return f"{name}: {span} ({r['what_changes_there']})" if r["what_changes_there"] else f"{name}: {span}"


def fold(rows: list[dict]) -> dict:
    """The five columns for one site, from its precision rows, in the order the precision file gives them."""
    def uniq(xs):
        return list(dict.fromkeys(x for x in xs if x))
    pubs = [f"{r['layer_name'] or 'no layer'}: accuracy: {r['statements_on_accuracy']}; completeness: "
            f"{r['statements_on_completeness']}" for r in rows]
    return {"location_uncertainty": " | ".join(uniq(f"{r['location_basis']}; {r['location_uncertainty']}" for r in rows)),
            "nearest_drawn_line_m_by_layer": " | ".join(_line(r) for r in rows),
            "publishers_on_accuracy_and_completeness": " | ".join(uniq(pubs)),
            "conflicting_geometry": " | ".join(uniq(r["conflicting_geometry"] for r in rows)),
            "precision_limitation": " | ".join(uniq(r["limitation"] for r in rows))}


def merged(conditions: list[dict], precision: list[dict]) -> tuple[list[dict], list[str]]:
    by: dict[str, list] = {}
    for r in precision:
        by.setdefault(r["site"], []).append(r)
    missing = [c["site"] for c in conditions if c["site"] not in by]
    if missing:
        raise ValueError(f"no precision rows for {', '.join(missing)}: run pass_c_precision.py for them first")
    out = [{**{k: v for k, v in c.items() if k not in NEW}, **fold(by[c["site"]])} for c in conditions]
    fields = [k for k in conditions[0] if k not in NEW] + NEW
    return out, fields


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    with open(CONDITIONS, newline="") as f:
        conditions = list(csv.DictReader(f))
    with open(PRECISION, newline="") as f:
        precision = list(csv.DictReader(f))
    out, fields = merged(conditions, precision)
    if "--check" in argv:
        same = all(all(a.get(k, "") == b[k] for k in fields) for a, b in zip(conditions, out)) and len(conditions) == len(out)
        print("the conditions file carries the precision fields as the precision file has them" if same else
              "the conditions file does not match the precision file: run this script without --check")
        return 0 if same else 1
    with open(CONDITIONS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} records now carry: {', '.join(NEW)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
