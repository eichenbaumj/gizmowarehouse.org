#!/usr/bin/env python3
"""What the precision rule says about each layer record on file (docs/gate1/precision-rule-2026-11-18.md; D-72 item 5;
D-85). It reads two files and writes one table. IT CHANGES NO CLASS: `pass_c_layer_conditions.csv` is not written.

Reads   pipeline/facilities/verified/pass_c_layer_conditions.csv   (one row per site: the class on file, the tie)
        pipeline/facilities/verified/pass_c_layer_precision.csv    (one row per site and layer: extent, distances)
Writes  pipeline/facilities/verified/pass_c_precision_rule.csv

No network, nothing under data/, no price or revenue. Run from the gizmo folder:
    python3 -I pipeline/facilities/pass_c_precision_rule.py            # writes the table
    python3 -I pipeline/facilities/pass_c_precision_rule.py --check    # compares with the table on file, writes nothing

The rule, as far as it can be read from fields (the rest is a reading, and the table says where one is needed):
  kind  S a statement or certificate; L a territory listing; M a depiction; N a lead. From the class on file.
  P1    the location is tied to the facility (the record's `tied_to_the_facility_by` is address, owner or both, and
        the precision row's location is a tied parcel).
  P2    on a layer: (low end of the distance to the nearest drawn line) x 0.985 - 5 m  >  the parcel's extent.
        Not shown where there is no distance, no extent, or the layer's own edge was not tested.
  P3    conflicting geometry at the point: the names the layers return there, compared after the spellings below are
        folded. A layer that returns nothing at the point is not compared. Whether a conflict comes only from a layer
        of lower standing (the national compilation, the Texas commission's layers) is recorded, because reading 3 of
        the rule's section 6 turns on it. A boundary known to have moved, and a stated tolerance, are not in these
        fields and are not tested here.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONDITIONS = HERE / "verified" / "pass_c_layer_conditions.csv"
PRECISION = HERE / "verified" / "pass_c_layer_precision.csv"
OUT = HERE / "verified" / "pass_c_precision_rule.csv"

GEOMETRY_FACTOR = 0.985          # the rule's section 5: a margin, not a bound
DATUM_M = 5.0                    # the rule's section 5: a convention, not a bound

# The session's readings, kept in one place so that Joe can strike any of them (the rule's section 6, reading 3).
# Spellings of one legal entity, folded before names are compared.
SAME_ENTITY = [
    {"pge", "portland general electric"},
    {"pacificorp", "pacific power (pacificorp)", "pacific power", "rocky mountain power"},   # one company, two trade names
    {"oppd", "omaha public power district"},
]
LOWER_STANDING = ("HIFLD", "Public Utility Commission of Texas")              # D-63 rule 2; D-65 item 2: leads
TIED = {"address", "owner", "address and owner"}

COLUMNS = ["site", "class_on_file", "kind", "tied_by", "P1_location_resolved", "parcel_extent_m",
           "P2_by_layer", "P2_whole_location_on_one_side", "P3_names_at_the_point", "P3_conflict",
           "P3_conflict_only_from_a_layer_of_lower_standing", "what_the_rule_says", "needs_a_reading"]


def kind_of(cls: str) -> str:
    c = cls.lower()
    if c.startswith("meets"):
        return "M"
    if c.startswith("supports a statement"):
        return "S"
    if c.startswith("checks a town listing"):
        return "L"
    if c.startswith("lead"):
        return "N"
    return "?"


def allowed_low(low: float) -> float:
    """The low end of a distance after the rule's allowances."""
    return low * GEOMETRY_FACTOR - DATUM_M


def fold(name: str) -> str:
    n = name.strip().lower()
    for group in SAME_ENTITY:
        if n in group:
            return sorted(group)[0]
    return n


def names_at_point(at_point: str) -> frozenset:
    """The names in an `at_point` cell, without the object ids. 'nothing' and unqueried rows give an empty set."""
    if not at_point or at_point.startswith(("nothing", "not queried", "error")):
        return frozenset()
    found = re.findall(r"'([^']*)'", at_point)
    return frozenset(fold(x) for x in found if x.strip())


def _f(x: str):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def p2_layer(row: dict, extent) -> tuple[str, str]:
    """('holds' | 'fails' | 'not shown', the arithmetic in words) for one layer."""
    low = _f(row["nearest_line_m_low"])
    if low is None:
        return "not shown", "no distance on file"
    if row["relation_used_for_contains"].startswith("none"):
        return "not shown", "the layer's own edge and holes were not tested"
    if not names_at_point(row["at_point"]):
        return "not shown", f"nothing at the point; nearest feature at {row['nearest_line_m_low']} m or more"
    if extent is None:
        return "not shown", "no parcel extent on file"
    a = allowed_low(low)
    verdict = "holds" if a > extent else "fails"
    return verdict, f"{low:g} m x {GEOMETRY_FACTOR} - {DATUM_M:g} = {a:.1f} m against an extent of {extent:g} m"


def table(conditions: list[dict], precision: list[dict]) -> list[dict]:
    by_site: dict[str, list[dict]] = {}
    for r in precision:
        by_site.setdefault(r["site"], []).append(r)
    out = []
    for c in conditions:
        site, rows = c["site"], by_site.get(c["site"], [])
        kind = kind_of(c["class_under_D63"])
        tied = c["tied_to_the_facility_by"] in TIED and any(r["location_basis"].startswith("tied parcel") for r in rows)
        extent = next((_f(r["parcel_extent_m"]) for r in rows if _f(r["parcel_extent_m"]) is not None), None)
        per_layer, verdicts = [], []
        for r in rows:
            v, why = p2_layer(r, extent)
            lower = r["layer_publisher"].startswith(LOWER_STANDING)
            per_layer.append(f"{r['layer_name'][:40]}{' [lower standing]' if lower else ''}: {v} ({why})")
            if not lower:
                verdicts.append(v)
        if not verdicts:
            p2 = "not shown"
        elif "fails" in verdicts:
            p2 = "fails"
        elif "not shown" in verdicts:
            p2 = "holds where a distance is on file; not shown on a layer or map with none"
        else:
            p2 = "holds"
        sets = [(r["layer_publisher"].startswith(LOWER_STANDING), names_at_point(r["at_point"])) for r in rows]
        sets = [(lw, s) for lw, s in sets if s]
        upper = {s for lw, s in sets if not lw}
        everyone = {s for _, s in sets}
        conflict = len(everyone) > 1
        only_lower = conflict and len(upper) <= 1
        names = " | ".join(sorted("; ".join(sorted(s)) for s in everyone)) or "no layer returns a name at the point"
        if kind == "M":
            if not tied:
                says = "reliance defeated: P1, the location is not tied to the facility"
            elif p2 == "fails":
                says = "reliance defeated: P2, a drawn line may lie within the location's extent"
            elif p2 == "not shown":
                says = "reliance defeated: P2 is not shown on any layer the record could rely on"
            elif conflict and not only_lower:
                says = "reliance defeated: P3, layers of equal standing name different suppliers at the point"
            elif conflict:
                says = ("reliance defeated under reading 3 (a conflict with a layer of lower standing, not resolved by a "
                        "record); stands if reading 3 is struck")
            else:
                says = "reliance stands, with unknown accuracy as a stated limitation"
        elif kind == "S":
            says = "does not rely on a depiction: the precision fields decide nothing"
        elif kind == "L":
            if conflict:
                says = ("a layer returns another name at the point: the listing no longer suffices unless a record shows "
                        "that name is not a supplier of retail delivery there")
            elif p2 == "fails":
                says = "a drawn line may lie within the location's extent: the listing no longer suffices"
            elif not tied:
                says = "the layers cannot check the listing at a point that is not tied; the listing stands on D-48's own terms"
            else:
                says = "the layers do not undo the listing"
        else:
            says = "a lead: adds candidates and does nothing else"
        need = []
        if kind in ("M", "L") and conflict:
            need.append("whether a record on file resolves the conflict, or shows the other name is not a retail supplier there")
        if kind == "M" and "not shown on a layer or map" in p2:
            need.append("whether the record relies on the map that has no distance")
        if kind == "?":
            need.append("the class on file is not one this script knows")
        out.append({"site": site, "class_on_file": c["class_under_D63"], "kind": kind,
                    "tied_by": c["tied_to_the_facility_by"], "P1_location_resolved": "yes" if tied else "no",
                    "parcel_extent_m": "" if extent is None else f"{extent:g}", "P2_by_layer": " || ".join(per_layer),
                    "P2_whole_location_on_one_side": p2, "P3_names_at_the_point": names,
                    "P3_conflict": "yes" if conflict else "no",
                    "P3_conflict_only_from_a_layer_of_lower_standing": "yes" if only_lower else ("no" if conflict else ""),
                    "what_the_rule_says": says, "needs_a_reading": "; ".join(need)})
    return out


def _read(path: Path) -> list[dict]:
    csv.field_size_limit(10 ** 9)
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="compare with the table on file and write nothing")
    args = ap.parse_args(argv)
    rows = table(_read(CONDITIONS), _read(PRECISION))
    if args.check:
        on_file = _read(OUT)
        same = on_file == [{k: str(v) for k, v in r.items()} for r in rows]
        print("the table on file is what the rule gives" if same else "the table on file DIFFERS from what the rule gives")
        return 0 if same else 1
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT.relative_to(HERE.parents[1])}: {len(rows)} sites; no class was changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
