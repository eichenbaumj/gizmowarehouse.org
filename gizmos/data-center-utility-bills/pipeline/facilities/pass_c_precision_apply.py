"""The precision rule's results applied to the classes on file (D-72 item 5; Joe's readings in D-94).

Reads two files and writes one. It opens no data file, decides nothing a ruling has not decided, and changes no
record: `verified/pass_c_layer_conditions.csv` keeps its classes as they were, and the class each record carries
under the rule is written beside them in `verified/pass_c_precision_classes.csv`.

  verified/pass_c_precision_rule.csv          what the rule says about each of the layer records, from the fields on file
                                              (pass_c_precision_rule.py)
  verified/pass_c_precision_resolutions.json  how the records the table leaves "needing a reading" are settled: by Joe's
                                              words, or by a resolving record under the session's reading, marked as such

A resolution marked `the_sessions_reading` is a proposal until Joe adopts it; the output says so on the row.
`--check` compares with the file on disk and exits non-zero if it differs.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULE = HERE / "verified" / "pass_c_precision_rule.csv"
RESOLUTIONS = HERE / "verified" / "pass_c_precision_resolutions.json"
OUT = HERE / "verified" / "pass_c_precision_classes.csv"

COLUMNS = ("site", "kind", "class_on_file", "what_the_rule_says", "class_under_the_precision_rule", "basis",
           "stated_limitation", "rests_on_a_reading_of_the_sessions")

STANDS = "reliance stands, with unknown accuracy as a stated limitation"
LEAD = "a lead: adds candidates and does nothing else"
STATEMENT = "does not rely on a depiction: the precision fields decide nothing"
UNKNOWN_ACCURACY = "the layer's accuracy is unknown (D-65 item 2)"


def classify(row: dict, res: dict) -> dict:
    """One record's class under the rule. Raises on a record the rule's table and the resolutions do not settle."""
    site, says, on_file = row["site"], row["what_the_rule_says"], row["class_on_file"]
    out = dict(site=site, kind=row["kind"], class_on_file=on_file, what_the_rule_says=says,
               stated_limitation="", rests_on_a_reading_of_the_sessions="no")
    special = res.get("sites", {}).get(site)
    omaha = res.get("omaha", {})
    if special is not None:
        r = special["resolution"]
        if r not in ("resolved", "stands", "unresolved"):
            raise ValueError(f"{site}: unknown resolution {r!r}")
        out["rests_on_a_reading_of_the_sessions"] = "yes" if special.get("the_sessions_reading") else "no"
        if r == "unresolved":
            out["class_under_the_precision_rule"] = ("reliance defeated (reading 3): the assignment is unresolved and the "
                                                     "depiction or listing is a lead for this site")
            out["basis"] = "no record resolves the name " + special["conflicting_name"]
        else:
            out["class_under_the_precision_rule"] = on_file
            out["basis"] = f"the conflict with {special['conflicting_name']} is settled by: {special['resolved_by']}"
            out["stated_limitation"] = UNKNOWN_ACCURACY if row["kind"] == "M" else ""
        return out
    if site in omaha.get("sites", ()):
        if says != STANDS:
            raise ValueError(f"{site}: the Omaha application expects the rule's table to say reliance stands")
        out.update(class_under_the_precision_rule=on_file,
                   basis="relies on the two measured layers; the utility's own PDF map is corroboration, not a depiction relied on (D-94)",
                   stated_limitation=UNKNOWN_ACCURACY)
        return out
    if row.get("needs_a_reading"):
        raise ValueError(f"{site}: the rule's table says it needs a reading ({row['needs_a_reading']}) and no resolution is on file")
    if says == STANDS:
        out.update(class_under_the_precision_rule=on_file, basis="the rule's three conditions hold on the fields on file",
                   stated_limitation=UNKNOWN_ACCURACY)
    elif says == LEAD:
        out.update(class_under_the_precision_rule=on_file, basis="a lead before and after: it adds candidates and verifies nothing")
    elif says == STATEMENT:
        out.update(class_under_the_precision_rule=on_file, basis="rests on a statement about the site; outside the map tests (reading 7)")
    else:
        raise ValueError(f"{site}: the rule's table says {says!r}, which nothing here settles")
    return out


def build(rule_rows: list[dict], res: dict) -> list[dict]:
    seen = {r["site"] for r in rule_rows}
    for s in list(res.get("sites", {})) + list(res.get("omaha", {}).get("sites", [])):
        if s not in seen:
            raise ValueError(f"{s} has a resolution and is not in the rule's table")
    return [classify(r, res) for r in rule_rows]


def render(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", default=str(RULE))
    ap.add_argument("--resolutions", default=str(RESOLUTIONS))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = render(build(list(csv.DictReader(open(a.rule))), json.load(open(a.resolutions))))
    if a.check:
        same = Path(a.out).exists() and Path(a.out).read_text() == text
        print("identical" if same else "not identical")
        return 0 if same else 1
    Path(a.out).write_text(text)
    print(f"written: {a.out} ({text.count(chr(10)) - 1} records)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
