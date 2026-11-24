#!/usr/bin/env python3
"""The headline number's implied weights on every utility-year, from the regressors alone: data/frozen/design_weights.csv.

Written 2026-11-19 under Joe's ruling of that day ("Regenerate design_weights.csv through the existing regressors-only
weight calculation, without running simulation stages"). `inference_check.main` writes this CSV, but the same run also
rewrites data/frozen/inference_check.json, which holds preserved results of 2026-11-14, and writes
second_number_leverage.csv, and without --quantities-only it runs made-up datasets. This driver does only the weights.

For each set of design.SETS at the 2% threshold under the headline rules it builds the design exactly as design.main
and inference_check.main do (design.load, the usable flag read once through usable_flag.read, ps.rule_inputs,
ps.ownership_classes, ps.load_unknown_load, design.split, design.build_with_rules with the same arguments), calls
inference_check.implied_weights under the headline fuel control and writes the rows in exactly the columns and
formatting inference_check.main uses. A set whose fit is rank deficient has no weights; the reason is written in words in
the sidecar, as inference_check.main writes it into its report.

Quantities only. The path reads data/interim/panel_quantities.parquet (load, sales, customers, ownership and the usable
flag; no price column), utility_year_dose.parquet, the frozen controls, the ownership table and the unknown-load file.
implied_weights sets every window's outcome to zeros before assembling the regressors (inference_check.fixed_parts); no
outcome enters. Nothing under data/blind is opened, and no made-up dataset is drawn.

Writes data/frozen/design_weights.csv and data/frozen/design_weights_provenance.json, and nothing else.

Against the step E record (added 2026-11-19, after the ownership repair of that day). The sidecar says, set by set, whether
the design-inputs hash of the design the weights were computed on equals the one the historical step E record
data/frozen/design_support.json carries, and the one the current design summary data/frozen/design_support_current.json
carries (`against_the_design_records`), with a plain note on why a set differs. Both files are read, never written.

Run:  python3 -I pipeline/analysis/design_weights.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.analysis import design, estimator  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
STEP_E_RECORD = "design_support.json"                 # the historical step E record: read for its hashes, never written
CURRENT_SUMMARY = "design_support_current.json"       # the current design summary (design_support_current.py)
EXPECTED_TO_DIFFER = "every_cohort_utility"           # the one set the ownership repair of 2026-11-19 changed
WHY_A_SET_DIFFERS = (
    "The step E record, data/frozen/design_support.json, was written before the ownership repair of 2026-11-19 (D-58 rule 2.2 "
    "read year by year: an investor-owned candidate is barred for an investor-owned host when some year of the host's window "
    "has no ownership row covering the candidate). The repair left the headline set, the set with the ten-year case and the "
    "set with unsettled hosts put back unchanged, so their hashes here equal the step E record's. In every cohort utility as "
    "built it replaced eight matches of three hosts (Commonwealth Edison, Ohio Power and NSTAR), so that set's weights are "
    "computed on a different design from the one the step E record describes, and its hash here does not equal the step E "
    "record's. It equals the current design summary's. The step E record is kept as it is; it is not rewritten to agree.")
CSV_NAME = "design_weights.csv"
PROVENANCE_NAME = "design_weights_provenance.json"
COMMAND = "python3 -I pipeline/analysis/design_weights.py"
THIS_FILE = "pipeline/analysis/design_weights.py"
CODE_FILES = design.CODE_FILES + (THIS_FILE,)


def weights_for(designs: dict, fuel_control: str = ps.GAS_SHARE) -> tuple[list, dict]:
    """(weight frames with their set, per set: hosts in the estimate and whether weights could be computed).

    `designs` maps a set's name to its design.Design. A rank-deficient fit is caught as inference_check.main catches
    it, and its message kept in words; the set has no weight rows."""
    frames, info = [], {}
    for which, d in designs.items():
        entry = {"hosts_in_the_estimate": int(len(d.hosts)), "weights_computed": False}
        try:
            wt = ic.implied_weights(d, fuel_control)
        except estimator.RankDeficient as e:
            entry["implied_weights"] = {"not_computed": str(e)}
            wt = None
        if wt is not None:
            entry["weights_computed"] = True
            entry["weight_rows"] = int(len(wt))
            frames.append(wt.assign(set=which))
        info[which] = entry
    return frames, info


def csv_frame(frames: list) -> pd.DataFrame:
    """The rows exactly as inference_check.main writes them: keys as "id:state", the weight rounded to 8 places."""
    w = pd.concat(frames, ignore_index=True)
    w["block_host"] = [f"{k[0]}:{k[1]}" for k in w.block_host]
    w["utility"] = [f"{k[0]}:{k[1]}" for k in w.utility]
    return w.assign(weight=w.weight.round(8))


def write(frames: list, provenance: dict, frozen: Path = FROZEN) -> dict:
    """Write the CSV (when any set has weights) and the sidecar into `frozen`. Touches no other file."""
    path = Path(frozen) / CSV_NAME
    if frames:
        csv_frame(frames).to_csv(path, index=False)
        provenance["csv"] = {"file": f"data/frozen/{CSV_NAME}", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    else:
        provenance["csv"] = {"file": f"data/frozen/{CSV_NAME}", "sha256": None, "written": False,
                             "why": "no set's fit could be computed; a design_weights.csv already in the folder is not from this run"}
    (Path(frozen) / PROVENANCE_NAME).write_text(json.dumps(provenance, indent=2, default=str) + "\n")
    return provenance


def against_the_design_records(info: dict, frozen: Path = FROZEN) -> dict:
    """Per set: the design-inputs hash the weights were computed on, beside the hash the step E record and the current
    design summary carry for the same set, and whether each is equal. Reads both files (None where one is missing)."""
    def hashes(name):
        path = Path(frozen) / name
        if not path.exists():
            return None
        return {w: e["fingerprint"]["of"]["design_inputs"] for w, e in json.loads(path.read_text())["sets"].items()}
    old, cur = hashes(STEP_E_RECORD), hashes(CURRENT_SUMMARY)
    out = {}
    for which, e in info.items():
        now = e.get("design_inputs_sha256")
        a = None if old is None else old.get(which)
        b = None if cur is None else cur.get(which)
        out[which] = {"design_inputs_of_these_weights": now,
                      f"design_inputs_in_{STEP_E_RECORD}": a, "equal_to_the_step_e_record": None if a is None else a == now,
                      f"design_inputs_in_{CURRENT_SUMMARY}": b, "equal_to_the_current_design_summary": None if b is None else b == now}
    differ = sorted(w for w, v in out.items() if v["equal_to_the_step_e_record"] is False)
    why = (WHY_A_SET_DIFFERS if differ == [EXPECTED_TO_DIFFER] else
           "no set differs from the step E record" if not differ else
           f"UNEXPECTED: the sets {differ} differ from the step E record, which the ownership repair of 2026-11-19 does not "
           "explain; these weights are not to be used until the difference is assessed")
    return {"sets": out, "sets_differing_from_the_step_e_record": differ, "why_a_set_differs_from_the_step_e_record": why,
            "files": {"step_e_record": f"data/frozen/{STEP_E_RECORD} (historical, untouched)",
                      "current_design_summary": f"data/frozen/{CURRENT_SUMMARY}"}}


def main() -> int:
    from pipeline.analysis import usable_flag
    rules = ps.HEADLINE_RULES
    q, dose, regions, fuel, dd = design.load()
    flags = usable_flag.read()                       # the five columns, validated (D-94); no price
    ownership, usable, gas = ps.rule_inputs(rules, q, usable=flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    designs, prints = {}, {}
    for which in design.SETS:
        treated, clean = design.split(0.02, which, q, dose)
        d = design.build_with_rules(treated, clean, q, regions, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas,
                                    ownership_of=ownership_of, unknown_load=unknown, theta=0.02)
        designs[which] = d
        prints[which] = design.run_fingerprint(d, rules=rules, usable=usable,
                                               assumptions={"kind": "design_weights", "set": which, "threshold": 0.02},
                                               settings={"fuel_control": rules.fuel_control}, seeds=None, code_files=CODE_FILES)
    frames, info = weights_for(designs, rules.fuel_control)
    for which in info:
        info[which]["fingerprint"] = prints[which]
        info[which]["design_inputs_sha256"] = prints[which]["of"]["design_inputs"]
    provenance = {
        "what_this_is": ("The headline number's implied weight on every stacked utility-year, from the regressors alone, for each "
                         "set at 2% under the headline rules (inference_check.implied_weights). First regenerated on 2026-11-19 "
                         "under Joe's ruling of that day through this driver, and again at the final quantity regeneration on the "
                         "day `date` gives; the driver writes only these two files: inference_check.json "
                         "and second_number_leverage.csv are not touched, and no made-up dataset is run. Quantities only; no "
                         "price is read. Provisional: the design stands as it is after the ownership repair of 2026-11-19, and "
                         "the plan is a DRAFT, not frozen. The every-cohort set's design-inputs hash is not the one the step E "
                         "record carries; against_the_design_records says so set by set and why."),
        "date": dt.date.today().isoformat(),
        "command": COMMAND,
        "rules": {"label": rules.label, "ownership": rules.ownership, "usable": rules.usable, "support": rules.support,
                  "fuel_control": rules.fuel_control, "unresolved_ownership": rules.unresolved_ownership},
        "columns": ["block_host", "cohort", "utility", "is_host", "event_year", "weight", "set"],
        "design_inputs_note": ("design_inputs_sha256 is the design_inputs component of design.run_fingerprint, the same component "
                               "design.main writes into design_support.json for the set"),
        "sets": info,
        "against_the_design_records": against_the_design_records(info),
    }
    write(frames, provenance)
    for which, e in info.items():
        print(f"{which}: hosts in the estimate {e['hosts_in_the_estimate']}, weights "
              f"{'computed, ' + str(e['weight_rows']) + ' rows' if e['weights_computed'] else 'not computed: ' + e['implied_weights']['not_computed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
