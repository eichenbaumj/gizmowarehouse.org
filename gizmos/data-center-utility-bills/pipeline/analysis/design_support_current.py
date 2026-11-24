#!/usr/bin/env python3
"""The current design summary: data/frozen/design_support_current.json and design_support_current.csv.

Written 2026-11-19 under Joe's ruling of that day, his words: "Keep the historical step E files untouched at their
existing paths. Write current design summaries under distinct names and have the prefreeze summary reader explicitly use
those current files. Verify the writer's suffix behavior before relying on it. The kernel's historical validation
references remain unchanged."

Why a driver and not design.main
--------------------------------
design.main picks its output names from the rules alone: `suffix = "" if rules == ps.HEADLINE_RULES else
f"_{rules.label}"`, the rules coming from `--rules=<label>` (power_simulation.rules_from_argv) and the folder from the
module global design.FROZEN. Under the headline rules the suffix is empty, so a run writes data/frozen/design_support.json,
design_support.csv and full_window_eligibility.csv, the historical step E record. The only other names it can write
belong to a labelled variant, which is a different design. design.main therefore cannot write a current summary under the
headline rules without overwriting the historical files or an edit to design.py, and it is not run. This driver calls
design.py's own functions in the order design.main calls them, for the same sets, rules and threshold, and writes to new
names only. It is built the way pipeline/analysis/design_weights.py is.

What it writes and what it does not
-----------------------------------
It writes CURRENT_JSON and CURRENT_CSV and nothing else. It never opens a historical file for writing; it reads
data/frozen/design_support.json and full_window_eligibility.csv to say, per set, whether the current design's inputs equal
the historical record's, and whether the per-unit eligibility rows design.main would write equal the historical file's.
No current full-window eligibility file is written: the prefreeze reader reads the eligibility block of the JSON only, and
the rows are compared with the historical file instead (see `eligibility_rows_against_the_historical_file`). That no
current full-window eligibility file is written, and that the step E record stays at its paths beside these current
summaries, were accepted by Joe on 2026-11-19 (D-111, item 6: "accept ... the separation of historical validation
records from current design summaries").

Each set's entry is the entry design.main writes, field for field, with the same fingerprint assumptions and settings;
its `code_version` component also covers this file (CODE_FILES), as design_weights.py's does. The JSON's top level adds
`what_this_is`, `written_by`, `historical_record` and `against_the_historical_record`.

Quantities only: the quantities file (load, sales, customers, ownership, the usable flag read by explicit columns through
usable_flag.read), the dose file, the frozen controls, the ownership table and the unknown-load file. No price, revenue
or bill; no outcome file and no availability file is opened.

Run:  python3 -I pipeline/analysis/design_support_current.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.analysis import design  # noqa: E402
from pipeline.analysis import ownership as own_rules  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
CURRENT_JSON_NAME = "design_support_current.json"
CURRENT_CSV_NAME = "design_support_current.csv"
HISTORICAL_JSON_NAME = "design_support.json"             # the step E record; read here, never written
HISTORICAL_CSV_NAME = "design_support.csv"
HISTORICAL_ELIGIBILITY_NAME = "full_window_eligibility.csv"
HISTORICAL_NAMES = (HISTORICAL_JSON_NAME, HISTORICAL_CSV_NAME, HISTORICAL_ELIGIBILITY_NAME)
THIS_FILE = "pipeline/analysis/design_support_current.py"
CODE_FILES = design.CODE_FILES + (THIS_FILE,)
THETA = 0.02

WHAT_THIS_IS = (
    "A current design summary: for each set of hosts at the 2% threshold under the headline rules, every host's matched "
    "comparison utilities and two support counts in every year of its window, on the design as it stands after the "
    "ownership repair of 2026-11-19 (rule 2.2 read year by year). It is not a validation record. The historical step E "
    "record is data/frozen/design_support.json, left untouched at its path; the kernel's validation reference "
    "(outcome_analysis.read_validation_reference) reads that file and not this one. Written under distinct names by "
    "pipeline/analysis/design_support_current.py, which calls design.py's functions as design.main does (Joe, "
    "2026-11-19). Load and sales only; no price is read. PROVISIONAL: the plan is a DRAFT, not frozen, and every figure "
    "here moves with the design.")


def header(rules: ps.Rules, flags) -> dict:
    """The top of the report, as design.main writes it, with this file's own `what_this_is` and provenance."""
    report = {"what_this_is": WHAT_THIS_IS,
              "written_by": THIS_FILE,
              "historical_record": {"file": f"data/frozen/{HISTORICAL_JSON_NAME}",
                                    "status": "untouched: the step E record, read by the kernel's validation reference"},
              "rules": {"label": rules.label, "ownership": rules.ownership, "usable": rules.usable, "support": rules.support,
                        "fuel_control": rules.fuel_control, "unresolved_ownership": rules.unresolved_ownership},
              "ownership_assumption": "municipal systems, public power districts and distribution cooperatives with no row in the "
                                      "ownership table are each taken as their own owner, from EIA's ownership class (D-58 rule 2.2)",
              "gas_share_assumption": ps.GAS_ASSUMPTION if rules.fuel_control == ps.GAS_SHARE else None,
              "pool": "eligible comparison utilities in the host's sub-experiment that are in the host's region that year",
              "matched": "of the host's ten matched comparison utilities (matched once, on the reference year), how many are in the host's region that year",
              "sets": {}}
    if flags is not None:
        report["usable_flag"] = {"source": "the quantities file's res_price_usable column, read by explicit columns (D-94)",
                                 "rows_read": flags.rows, "usable_unit_years": len(flags.usable)}
    return report


def set_entry(which: str, treated: pd.DataFrame, clean: pd.DataFrame, d: design.Design, names, rules: ps.Rules, *,
              ownership, ownership_of: dict, flags, gas, usable) -> tuple[dict, pd.DataFrame, pd.DataFrame | None]:
    """(the set's entry, its support table with the set's name, its window gaps or None): design.main's loop body for one
    set, calling the same design.py functions with the same arguments."""
    s = design.support(d)
    s["set"] = which
    hosts = []
    for h in d.hosts.itertuples():
        mine = s[(s.utility_id_eia == h.key[0]) & (s.state == h.key[1])].set_index("event_year")
        row = {"utility": f"{h.key[0]}:{h.key[1]}", "name": names.get(h.key), "cohort": h.cohort, "region_in_the_reference_year": h.region,
               "pool": {"reference_year": int(mine.pool[ps.REF]), "event_year_2": int(mine.pool[2]), "event_year_3": int(mine.pool[3]),
                        "smallest_in_the_window": int(mine.pool.min())},
               "matched": {"reference_year": int(mine.matched[ps.REF]), "event_year_2": int(mine.matched[2]), "event_year_3": int(mine.matched[3]),
                           "smallest_in_the_window": int(mine.matched.min())},
               "matched_set_size": len(h.matches),
               "matched_utilities": [{"utility": f"{k[0]}:{k[1]}", "name": names.get(k)} for k in h.match_keys],
               "host_changes_region_in_its_window": bool(mine.host_region.nunique() > 1)}
        if "excluded_from_its_pool" in d.hosts.columns:
            row["excluded_from_its_pool"] = h.excluded_from_its_pool
        hosts.append(row)
    thin = [x["name"] for x in hosts if x["pool"]["reference_year"] < design.THIN]
    units = [((int(u), st), "host") for u, st in zip(treated.utility_id_eia, treated.state)] + \
            [((int(u), st), "comparison") for u, st in zip(clean.utility_id_eia, clean.state)]
    entry = {
        "hosts_in_the_set": int(len(treated)), "hosts_in_the_estimate": int(len(d.hosts)), "hosts_dropped": d.dropped,
        "eligible_comparison_utilities": int(len(clean)),
        "load_unknown_excluded": d.load_unknown_excluded, "load_unknown_source": d.unknown_load_source,
        "support_rule": ("applied: a host that does not keep its place is dropped and named (D-54 ruling 2)" if rules.support == "applied"
                         else "reported only (labelled variant)"),
        "support_rule_by_host": [] if d.support_table is None else d.support_table.to_dict("records"),
        "hosts_with_fewer_than_ten_eligible_in_their_region_in_the_reference_year": thin,
        "hosts_with_fewer_than_ten_matched_in_their_region_in_event_year_2_or_3":
            [x["name"] for x in hosts if min(x["matched"]["event_year_2"], x["matched"]["event_year_3"]) < design.THIN],
        "hosts": hosts}
    gaps = None
    if ownership is not None:
        entry["investor_owned_units_with_no_ownership_row"] = design.investor_owned_without_rows(ownership, units, ownership_of, names)
        fate = "excluded" if rules.unresolved_ownership == "hosts_excluded" else "kept in the estimate"
        entry["hosts_with_unresolved_ownership"] = {
            "limitation": own_rules.UNRESOLVED_LIMITATION.format(fate=fate),
            "hosts": [{"utility": x["utility"], "name": names.get(design._key_of(x["utility"])), "cohort": x["cohort"], "years": x["years"],
                       "reason": x["reason"], "in_this_run": x["in_this_run"]} for x in (d.unresolved_ownership or [])]}
    if flags is not None:
        entry["full_window_eligibility"] = design.eligibility_summary(flags, treated, clean, names, rules)
        gaps = design.window_gaps(flags, design.unit_windows(treated, clean))
    if gas is not None and len(d.hosts):
        entry["gas_share_against_matches"] = design.gas_share_ranges(d, gas, names)
    entry["fingerprint"] = design.run_fingerprint(d, rules=rules, usable=usable, assumptions={"kind": "design", "set": which, "threshold": THETA},
                                                  settings={"match_k": ps.MATCH_K, "thin": design.THIN, "in_region_of_ten": design.IN_REGION_OF_TEN},
                                                  seeds=None, code_files=CODE_FILES)
    return entry, s, gaps


def eligibility_frame(gaps: list) -> pd.DataFrame | None:
    """The per-unit rows design.main would write to full_window_eligibility.csv: once for every set, sorted the same way."""
    if not gaps:
        return None
    return (pd.concat(gaps, ignore_index=True).drop_duplicates(["utility_id_eia", "state", "cohort"])
            .sort_values(["state", "utility_id_eia", "cohort"]))


def eligibility_rows_against_the_historical_file(rows: pd.DataFrame | None, frozen: Path = FROZEN) -> dict:
    """Whether the rows design.main would write equal the historical full_window_eligibility.csv byte for byte. Reads the
    historical file; writes nothing."""
    path = Path(frozen) / HISTORICAL_ELIGIBILITY_NAME
    if rows is None:
        return {"file": f"data/frozen/{HISTORICAL_ELIGIBILITY_NAME}", "compared": False, "why": "no usable flag in this run"}
    now = rows.to_csv(index=False).encode()
    old = path.read_bytes() if path.exists() else None
    same = old is not None and old == now
    return {"file": f"data/frozen/{HISTORICAL_ELIGIBILITY_NAME}", "compared": True, "historical_file_exists": old is not None,
            "rows_equal_the_historical_file_byte_for_byte": same,
            "sha256_of_the_rows_this_run_computes": hashlib.sha256(now).hexdigest(),
            "sha256_of_the_historical_file": None if old is None else hashlib.sha256(old).hexdigest(),
            "reading": ("the per-unit rows are those of the historical file, which is left untouched; no current copy is written"
                        if same else
                        "the rows this run computes differ from the historical file; the historical file is left untouched and "
                        "no current copy is written, so the per-unit detail for the current design is not on file")}


def against_the_historical_record(report: dict, frozen: Path = FROZEN) -> dict:
    """Per set: the current design-inputs hash beside the one the historical design_support.json records. Reads it only."""
    path = Path(frozen) / HISTORICAL_JSON_NAME
    old = json.loads(path.read_text())["sets"] if path.exists() else {}
    out = {}
    for which, e in report["sets"].items():
        now = e["fingerprint"]["of"]["design_inputs"]
        was = old.get(which, {}).get("fingerprint", {}).get("of", {}).get("design_inputs")
        out[which] = {"design_inputs_now": now, "design_inputs_in_the_historical_record": was, "equal": now == was}
    return out


def write(report: dict, tables: list, frozen: Path = FROZEN) -> dict:
    """Write CURRENT_JSON_NAME and CURRENT_CSV_NAME into `frozen`, and nothing else. Returns {name: sha256}."""
    if {CURRENT_JSON_NAME, CURRENT_CSV_NAME} & set(HISTORICAL_NAMES):
        raise RuntimeError("the current names must differ from the historical ones; stopping, nothing written")
    frozen = Path(frozen)
    csv_path, json_path = frozen / CURRENT_CSV_NAME, frozen / CURRENT_JSON_NAME
    pd.concat(tables, ignore_index=True).to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (json_path, csv_path)}


def build_report(frozen: Path = FROZEN) -> tuple[dict, list, pd.DataFrame | None]:
    """Every named set under the headline rules at 2%, built as design.main builds it. Returns (report, support tables,
    eligibility rows)."""
    from pipeline.analysis import usable_flag
    rules = ps.HEADLINE_RULES
    q, dose, regions, fuel, dd = design.load()
    names = q.groupby(design.KEY).utility_name.last()
    flags = usable_flag.read() if rules.usable == "flag" else None
    ownership, usable, gas = ps.rule_inputs(rules, q, usable=None if flags is None else flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    report = header(rules, flags)
    tables, gaps = [], []
    for which in design.SETS:
        treated, clean = design.split(THETA, which, q, dose)
        d = design.build_with_rules(treated, clean, q, regions, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas,
                                    ownership_of=ownership_of, unknown_load=unknown, theta=THETA)
        entry, s, g = set_entry(which, treated, clean, d, names, rules, ownership=ownership, ownership_of=ownership_of,
                                flags=flags, gas=gas, usable=usable)
        report["sets"][which] = entry
        tables.append(s)
        if g is not None:
            gaps.append(g)
        print(which, "| hosts", len(treated), "| in the estimate", len(d.hosts), "| design inputs",
              entry["fingerprint"]["of"]["design_inputs"][:12], flush=True)
    rows = eligibility_frame(gaps)
    report["full_window_eligibility_rows"] = eligibility_rows_against_the_historical_file(rows, frozen)
    report["against_the_historical_record"] = against_the_historical_record(report, frozen)
    return report, tables, rows


def main() -> int:
    report, tables, _ = build_report()
    hashes = write(report, tables)
    for name, h in hashes.items():
        print("wrote", f"data/frozen/{name}", h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
