#!/usr/bin/env python3
"""The three supplementary outcomes, settled before the freeze: their units, their transformation and when they cannot be
computed. Reads NO outcome: every level is an argument the caller supplies.

Joe's ruling of 2026-11-20 (D-117, item 2) is carried word for word in JOE_WORDS. In short, the natural log of residential
kWh per customer per month, of the residential bill per customer per month in nominal dollars, and of residential customer
counts; no constant added, nothing imputed, nothing silently dropped; a missing, nonfinite or nonpositive value on a
required design row makes that outcome's result on that design non-computable, with the reason and the affected-row count
reported. The headline price design and the other outcomes are unchanged by it.

What is here, and what is not
-----------------------------
SPECS states each outcome (a Spec). check_levels classifies the levels a caller supplies for the unit-years a design needs.
log_frame_for_design returns the natural log of those levels or raises NotComputable with a record in words.
run_on_design hands the logged frame to an estimator the caller supplies, or returns the non-computable record without
calling it. None of these opens a file. Nothing here reads the outcome file, names a reader for it, reshapes its columns or
assembles inputs for a run: the caller builds the design and the levels frame. main() writes one quantity-side summary,
data/frozen/supplementary_outcomes_spec.json, from the quantity file's res_customers only.

Where the levels come from (read as code in pipeline/electricity/panel.py, never run)
--------------------------------------------------------------------------------------
res_kwh_per_customer_month is res_mwh * 1000 / res_customers / 12, and res_bill_per_customer_month is res_revenue_full /
res_customers / 12; both are set to missing by the panel where res_customers is not positive, and both are columns of the
panel's outcome file, which nobody reads before the freeze. res_customers is a column of the quantity file,
data/interim/panel_quantities.parquet. That res_revenue_full is in nominal dollars is the agent's reading of panel.py
(its price line divides that revenue by MWh and by 10 to give cents per kWh, which holds for dollars).

Values are never shown
----------------------
These are blinded outcomes. No message, record or exception raised here carries a value of an outcome: unit-years are
named by key ("id:ST in year") and counted, nothing else.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import outcome_analysis as oa  # noqa: E402

KEY = list(oa.KEY)                       # utility_id_eia, state
UNIT_YEAR = KEY + ["year"]
VALUE = "value"                          # the caller's frame column, as run_outcomes.OUTCOME names it

# The outcome names, the same strings as run_outcomes.KWH, BILL and CUSTOMERS (run_outcomes imports this module, not the
# other way round).
KWH = "kwh_per_residential_customer"
BILL = "bill_per_customer"
CUSTOMERS = "residential_customers"
NAMES = (KWH, BILL, CUSTOMERS)

JOE_WORDS_ATTRIBUTION = "Joe, 2026-11-20 (D-117)"
JOE_WORDS = (
    "Settle the supplementary outcome definitions before freezing. Use natural logs of: residential kWh per customer "
    "per month; residential bill per customer per month, in nominal dollars; residential customer counts. State those "
    "units and transformations explicitly. Do not add a constant, impute values, or silently drop observations to make a "
    "logarithm possible. A missing, nonfinite or nonpositive value on a required design row makes that outcome/design "
    "result non-computable, with the reason and affected-row count reported. It does not change the headline price "
    "design or other outcomes. Carry the existing limits on validation of these supplementary outcomes.")

SUPPLEMENTARY_LABEL = ("supplementary outcome: the natural log of the level, with no constant added, nothing imputed and "
                       "no row dropped (" + JOE_WORDS_ATTRIBUTION + ")")
TRANSFORMATION = "natural log"
NON_COMPUTABLE_RULE = ("A missing, nonfinite or nonpositive value on a required design row makes that outcome/design "
                       "result non-computable, with the reason and affected-row count reported. (" + JOE_WORDS_ATTRIBUTION
                       + ")")
VALIDATION_LIMIT = ("These outcomes run on the headline design under the procedure validated for the price outcome. No "
                    "validation was made for them, and each result carries the kernel's label for that (\""
                    + oa.NOT_VALIDATED + "\").")
OUTCOME_FILE_IN_WORDS = ("the panel's outcome file, read by no one before the freeze and after it only through the gated "
                         "door")
QUANTITY_FILE_IN_WORDS = "the panel's quantity file, data/interim/panel_quantities.parquet"

# The three reasons a required unit-year has no logarithm, in the order they are tested.
MISSING, NONFINITE, NONPOSITIVE = "missing", "nonfinite", "nonpositive"
REASONS = (MISSING, NONFINITE, NONPOSITIVE)
REASON_IN_WORDS = {MISSING: "missing (no row in the frame, or no value)",
                   NONFINITE: "not finite (plus or minus infinity)",
                   NONPOSITIVE: "zero or negative"}
EXAMPLES = 5


@dataclass(frozen=True)
class Spec:
    """One supplementary outcome as settled on 2026-11-20 (D-117)."""
    name: str
    source_column: str
    source_file: str
    level_in_the_panel: str
    unit: str
    transformation: str
    constant_added: None
    imputation: str
    rows_dropped: str
    non_computable_rule: str
    validation_limit: str

    def as_dict(self) -> dict:
        return asdict(self)


def _spec(name, column, source_file, level, unit) -> Spec:
    return Spec(name=name, source_column=column, source_file=source_file, level_in_the_panel=level, unit=unit,
                transformation=TRANSFORMATION, constant_added=None, imputation="none", rows_dropped="none",
                non_computable_rule=NON_COMPUTABLE_RULE, validation_limit=VALIDATION_LIMIT)


SPECS = MappingProxyType({
    KWH: _spec(KWH, "res_kwh_per_customer_month", OUTCOME_FILE_IN_WORDS,
               "res_mwh * 1000 / res_customers / 12, missing where res_customers is not positive (pipeline/electricity/panel.py)",
               "kWh per residential customer per month"),
    BILL: _spec(BILL, "res_bill_per_customer_month", OUTCOME_FILE_IN_WORDS,
                "res_revenue_full / res_customers / 12, missing where res_customers is not positive "
                "(pipeline/electricity/panel.py); no price index is applied",
                "nominal dollars per residential customer per month"),
    CUSTOMERS: _spec(CUSTOMERS, "res_customers", QUANTITY_FILE_IN_WORDS,
                     "res_customers as the quantity file carries it",
                     "residential customers, a count"),
})


class NotComputable(ValueError):
    """A supplementary outcome cannot be computed on a design: a required unit-year's level is missing, not finite, or not
    positive. `.record` is a JSON-ready dict with the reasons and counts; it names unit-years by key and carries no value."""

    def __init__(self, record: dict):
        super().__init__(record["in_words"])
        self.record = record


# ---- the check ---------------------------------------------------------------------------------------------------------

def _keys_of(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """The caller's frame cut to the key and the value, the key cast to int as the kernel casts it, stopping as the kernel
    stops (outcome_analysis._vector_for_rows) on a missing column or a repeated unit-year. Messages carry keys only."""
    need = UNIT_YEAR + [column]
    missing_cols = [c for c in need if c not in frame.columns]
    if missing_cols:
        raise oa.OutcomeMisaligned(f"the outcome frame has no column {missing_cols}")
    f = frame[need].copy()
    f["utility_id_eia"] = f.utility_id_eia.astype(int)
    f["year"] = f.year.astype(int)
    dup = f.duplicated(UNIT_YEAR, keep=False)
    if dup.any():
        first = f[dup].iloc[0]
        raise oa.OutcomeMisaligned(f"the outcome frame repeats a unit-year ({int(dup.sum())} rows), for example "
                                   f"{int(first.utility_id_eia)}:{first.state} in {int(first.year)}; stopping")
    return f


def _as_float(s: pd.Series) -> np.ndarray:
    """The values as floats, None and NaN alike becoming NaN. A value that is not a number stops in words without
    showing it."""
    try:
        return pd.to_numeric(s, errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError):
        raise oa.OutcomeMisaligned("the outcome frame's value column holds something that is not a number; stopping "
                                   "(the value is not shown)") from None


def _label(u, s, y) -> str:
    return f"{int(u)}:{s} in {int(y)}"


def check_levels(rows: pd.DataFrame, frame: pd.DataFrame, column: str = VALUE) -> dict:
    """Classify the levels a design needs. `rows` is outcome_analysis.stacked_rows(d); `frame` is the caller's levels,
    keyed by utility_id_eia, state and year, `column` in the Spec's unit.

    The required unit-years are the distinct (utility_id_eia, state, year) of `rows`. Each is fine or has exactly one
    reason, tested in this order: MISSING (no row in the frame, or the value is NaN or None), NONFINITE (plus or minus
    infinity), NONPOSITIVE (finite and at most zero). Counts are given in distinct unit-years and in stacked rows (a
    comparison utility matched to several hosts is one unit-year and several stacked rows). Rows of the frame the design
    does not use are never classified. A frame without the key or the value column, or one that repeats a unit-year
    anywhere, stops as the kernel stops (OutcomeMisaligned) and is not one of the three reasons. No value is returned."""
    f = _keys_of(frame, column)
    r = rows[UNIT_YEAR].copy()
    r["utility_id_eia"] = r.utility_id_eia.astype(int)
    r["year"] = r.year.astype(int)
    stacked_per = r.groupby(UNIT_YEAR, sort=True).size().rename("stacked_rows").reset_index()
    m = stacked_per.merge(f, on=UNIT_YEAR, how="left", indicator=True)
    vals = _as_float(m[column]) if len(m) else np.zeros(0)
    absent = (m["_merge"] == "left_only").to_numpy()
    missing = absent | np.isnan(vals)
    nonfinite = ~missing & np.isinf(vals)
    nonpositive = ~missing & ~nonfinite & (vals <= 0)
    reasons = {}
    for reason, mask in ((MISSING, missing), (NONFINITE, nonfinite), (NONPOSITIVE, nonpositive)):
        hit = m[mask]
        reasons[reason] = {"in_words": REASON_IN_WORDS[reason], "unit_years": int(mask.sum()),
                           "stacked_rows": int(hit.stacked_rows.sum()),
                           "examples": [_label(u, s, y) for u, s, y in zip(hit.utility_id_eia, hit.state, hit.year)][:EXAMPLES]}
    bad = missing | nonfinite | nonpositive
    return {"required_unit_years": int(len(m)), "required_stacked_rows": int(len(rows)),
            "affected_unit_years": int(bad.sum()), "affected_stacked_rows": int(m.stacked_rows[bad].sum()),
            "reasons": reasons}


def _in_words(spec: Spec, check: dict) -> str:
    parts = [f"{c['unit_years']} {reason} ({c['stacked_rows']} stacked rows)"
             for reason, c in check["reasons"].items() if c["unit_years"]]
    return (f"The natural log of {spec.unit} ({spec.name}) cannot be computed on this design, because "
            f"{check['affected_unit_years']} of its {check['required_unit_years']} required unit-years "
            f"({check['affected_stacked_rows']} of {check['required_stacked_rows']} stacked rows) have no positive finite "
            f"level, by reason {', '.join(parts)}; no constant is added, nothing is imputed and no row is dropped.")


def _spec_of(name: str) -> Spec:
    if name not in SPECS:
        raise KeyError(f"{name!r} is not a supplementary outcome; one of {list(SPECS)}")
    return SPECS[name]


def log_frame_for_design(d, frame: pd.DataFrame, name: str, column: str = VALUE) -> tuple[pd.DataFrame, dict]:
    """(the natural log of the levels on exactly the design's required unit-years, a record), or NotComputable.

    The returned frame is new: utility_id_eia, state, year and `column`, one row per required unit-year, sorted by key,
    `column` = numpy.log(level). No constant is added, nothing is filled, no required row is dropped and rows the design
    does not use are left out. The caller's frame and the design are not changed."""
    spec = _spec_of(name)
    rows = oa.stacked_rows(d)
    check = check_levels(rows, frame, column)
    base = {"outcome": spec.name, "label": SUPPLEMENTARY_LABEL, "source_column": spec.source_column, "unit": spec.unit,
            "transformation": spec.transformation, "constant_added": "none",
            "required_unit_years": check["required_unit_years"], "required_stacked_rows": check["required_stacked_rows"]}
    if check["affected_unit_years"]:
        raise NotComputable({**base, "computable": False, "reasons": check["reasons"],
                             "affected_unit_years": check["affected_unit_years"],
                             "affected_stacked_rows": check["affected_stacked_rows"], "in_words": _in_words(spec, check)})
    need = rows[UNIT_YEAR].drop_duplicates().astype({"utility_id_eia": int, "year": int})
    f = _keys_of(frame, column)
    out = need.merge(f, on=UNIT_YEAR, how="left").sort_values(UNIT_YEAR).reset_index(drop=True)
    out[column] = np.log(_as_float(out[column]))
    return out, {**base, "computable": True}


def run_on_design(d, frame: pd.DataFrame, name: str, estimate: Callable[[object, pd.DataFrame], dict], *,
                  column: str = VALUE) -> dict:
    """The supplementary outcome `name` on design `d`: the caller's `estimate(d, logged_frame)` on the logged levels, or,
    where they cannot be computed, the non-computable record with `estimate` not called. Builds and changes no design."""
    spec = _spec_of(name)
    try:
        logged, record = log_frame_for_design(d, frame, name, column)
    except NotComputable as exc:
        return {"estimated": False, "computable": False, "specification": spec.as_dict(), "non_computable": exc.record,
                "failure_in_words": exc.record["in_words"]}
    r = dict(estimate(d, logged))
    r.update({"computable": True, "specification": spec.as_dict(), "supplementary": record})
    return r


# ---- the quantity-side summary ----------------------------------------------------------------------------------------

FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
OUT_NAME = "supplementary_outcomes_spec.json"
THIS_FILE = "pipeline/analysis/supplementary_outcomes.py"
THETA = 0.02
EXPECTED_DESIGN_INPUTS_PREFIX = "b8515c35cba1"     # the headline set at 2%, as the session records it

WHAT_THIS_IS = (
    "The settled specification of the three supplementary outcomes (Joe, 2026-11-20, D-117) and one quantity-side check "
    "of residential customer counts on the headline set at 2%. PROVISIONAL: the design stands as of 2026-11-18 and the "
    "plan is a DRAFT, not frozen. No price, revenue, bill or kWh-per-customer value is read; the only level read is "
    "res_customers from the quantity file. Written by " + THIS_FILE + ".")
NOT_CHECKED_HERE = (
    "kWh per residential customer and the bill per customer are columns of the panel's outcome file, which is not read "
    "before the freeze, so whether they are missing, not finite or not positive on the design's rows cannot be checked "
    "this way. They were not constructed here from quantity columns.")


def spec_part() -> dict:
    """The part of the summary that is specification only (no figure)."""
    return {"specifications": {n: s.as_dict() for n, s in SPECS.items()},
            "joe_words": {"text": JOE_WORDS, "attribution": JOE_WORDS_ATTRIBUTION},
            "label": SUPPLEMENTARY_LABEL, "reasons": dict(REASON_IN_WORDS)}


def headline_design():
    """The headline set at 2% under the headline rules, built in memory as pipeline/analysis/design_support_current.py's
    build_report builds it (quantity files only). Returns (design, usable set, rules)."""
    from pipeline.analysis import design
    from pipeline.analysis import power_simulation as ps
    from pipeline.analysis import usable_flag
    rules = ps.HEADLINE_RULES
    q, dose, regions, fuel, dd = design.load()
    flags = usable_flag.read() if rules.usable == "flag" else None
    ownership, usable, gas = ps.rule_inputs(rules, q, usable=None if flags is None else flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    treated, clean = design.split(THETA, ps.HEADLINE_SET, q, dose)
    d = design.build_with_rules(treated, clean, q, regions, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas,
                                ownership_of=ownership_of, unknown_load=unknown, theta=THETA)
    return d, usable, rules


def customers_check(d, levels: pd.DataFrame) -> dict:
    """check_levels on the design's stacked rows with res_customers as the level. Counts and keys only."""
    rows = oa.stacked_rows(d)
    frame = levels.rename(columns={"res_customers": VALUE})
    c = check_levels(rows, frame, VALUE)
    return {"hosts_in_the_design": int(len(d.hosts)),
            "hosts_stacked": int(rows.loc[rows.is_host, UNIT_YEAR[:2]].drop_duplicates().shape[0]),
            "stacked_rows": c["required_stacked_rows"], "required_unit_years": c["required_unit_years"],
            "affected_unit_years": c["affected_unit_years"], "affected_stacked_rows": c["affected_stacked_rows"],
            "by_reason": c["reasons"], "computable": c["affected_unit_years"] == 0}


def build_summary() -> dict:
    d, usable, rules = headline_design()
    h = oa.design_hashes(d, usable, rules.fuel_control)["design_inputs"]
    if not h.startswith(EXPECTED_DESIGN_INPUTS_PREFIX):
        raise RuntimeError(f"the headline set's design-inputs hash begins {h[:12]}, not {EXPECTED_DESIGN_INPUTS_PREFIX}; "
                           "stopping, nothing written")
    levels = pd.read_parquet(INTERIM / "panel_quantities.parquet", columns=UNIT_YEAR + ["res_customers"])
    return {"what_this_is": WHAT_THIS_IS, **spec_part(),
            "quantity_side_check": {
                "outcome": CUSTOMERS, "set": "headline_set", "threshold": THETA, "rules": rules.label,
                "level": "res_customers from data/interim/panel_quantities.parquet, read by the columns utility_id_eia, "
                         "state, year and res_customers only",
                "design_inputs_sha256_prefix": h[:12],
                **customers_check(d, levels)},
            "not_checked_here": NOT_CHECKED_HERE}


def main() -> int:
    out = FROZEN / OUT_NAME
    summary = build_summary()
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print("wrote", f"data/frozen/{OUT_NAME}", hashlib.sha256(out.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
