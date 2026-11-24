#!/usr/bin/env python3
"""Every run the plan lists on outcomes, in its order of unblinding, and the code that composes each design builder
with the estimation kernel. Reads NO outcome: the outcome frame is an argument supplied by the caller.

PREANALYSIS.md, "Order of unblinding", "Other runs, listed in advance", "Conditions tested", "Reported checks", "Other
outcomes and robustness" (the Sets paragraph, G-a, G-b, E1 to E7) and the Inference bullets "Where the validation does
not transfer" and "Numerical failures in the analysis". The plan was frozen on Joe's explicit approval on 2026-11-20 at
commit ea426c4 (approved specification ed3a2ff); it is internally frozen and not externally preregistered. GATE1_SIGNED
does not exist: freeze approval, implementation readiness and authorization to access outcomes are separate steps, and
only the first has been given.

What is here
------------
REGISTRY            one Entry per run, in the plan's order of unblinding: an id, the plan section, the set or sets it
                    applies to, how its design is built, how it is estimated, its labels and a status:
                      built        a design builder and an estimator exist and compose on invented inputs
                                   (tests/test_run_outcomes_invented.py shows it)
                      design_only  a builder exists and something named is missing before it can be estimated
                      needs_package  the pinned package is not installed (Callaway and Sant'Anna)
                      blocked      the run is defined and something named stops it; the reason says what (no entry
                                   since session 21: the second number's two sensitivity scenarios, blocked until Joe
                                   adopted them in D-107, are built)
                      not_built    the plan lists the run and no module covers it; the reason says what is missing
                      out_of_scope_for_this_freeze
                                   (OUT_OF_SCOPE) out of scope for this freeze by Joe's ruling of 2026-11-19 (D-109):
                                   row M. Listed after the executable order, in no executable order of unblinding and
                                   in no built count; its runner is not attached and its code is kept dormant
                                   (ROW_M_DORMANT_RUNNER); the paper's published numbers are carried as context only
                    An entry may also carry `stopped_on_research_inputs`: a built entry (it composes on invented inputs)
                    with a step that cannot run on the real quantity files until Joe rules, said in words. Since Joe
                    adopted row U's Short Form rule on 2026-11-20 (D-115) no entry carries one; the field and its count
                    in the registry document are kept, at zero.
ORDER_OF_UNBLINDING the executable order: REGISTRY less the entries out of scope for this freeze. It begins with rows U
                    and C.
run(entry_id, inputs, outcomes)
run_all(inputs, outcomes)
                    build each design from quantities (RunInputs), align the caller's outcome frame with the kernel's
                    helper (outcome_analysis.outcome_vector and its span form, second_number.outcome_matrix), estimate,
                    and return the result with its labels and any numerical failure in words. A run whose status is not
                    `built` returns its status and reason and estimates nothing; an entry out of scope for this freeze
                    is refused by run() in words (OutOfScopeForThisFreeze) before any input is looked at, and run_all
                    iterates ORDER_OF_UNBLINDING only. A failure in one run (or one set of a
                    run) is caught and recorded in words and the others still run: counted and reported, never dropped.
                    Every design that is not the headline design is passed validated_design=False, so its result carries
                    outcome_analysis.NOT_VALIDATED. main_headline_set on the headline set at 2% passes a
                    ValidationClaim built from RunInputs.validation_reference, which the kernel checks against the
                    design's inputs and rules; with no reference, or a design that does not check, it is labelled
                    NOT_VALIDATED and says why (session 19). Condition contrasts carry NO_RANGE_NO_VALIDATION.
every_cohort_utility_at(theta, q, dose, d34_table=, hold=)
                    every cohort utility as built at `theta` (the 1% set) from the D-34 table and the price hold the
                    caller passes; both are required and no file is opened (session 19, trap 4).
catches_drift_from_file(path=None)
                    RunInputs.catches_drift for the headline set at 2%, read by name from exercise 4a's result
                    (data/frozen/early_years_drift_selected_procedure.json; D-113): True when its outcome is 'added',
                    False when 'not added', nothing when split or when the file is absent, nothing for any other set;
                    refused in words on a wrong design-inputs hash, seed, drift or outcome. Called by no runner here.
carry_design_attributes(src, dst)
                    prefreeze_summaries.carry_design_attributes: the rules and lists a design built by build_with_rules
                    carries, put back on a design influence.leave_out returns (session 19, trap 3).
load_outcomes_after_the_freeze(*, reader=None, purpose=POST_FREEZE_PURPOSE, plan_state=None)
                    the only door to outcomes (session 27). It refuses in words, in this order: a purpose other than
                    POST_FREEZE_PURPOSE (either of panel.load_outcomes' exempt purposes is refused by name: the
                    construction and simulation routes are never taken through it); no gate file
                    (pipeline/electricity/panel.GATE_FILE); AUTH_ENV not "1"; a plan that is not the committed frozen one
                    (frozen_plan_state: PREANALYSIS.md committed with no uncommitted change, the freeze commit an
                    ancestor of HEAD); power_simulation.read_listed_outcomes as the reader. Then it calls the reader
                    (panel.load_outcomes, looked up when called, by default) once with purpose=POST_FREEZE_PURPOSE and
                    nothing else, and returns OutcomesRead: the frame untouched and a record with no outcome value. The
                    gate file is created only on Joe's separate authorization to access outcomes. No other code in this
                    module calls a reader of a price file.
frozen_plan_state(root=ROOT, *, freeze_commit=FREEZE_COMMIT, plan_file=PLAN_FILE)
                    the door's plan check, read-only git commands in the gizmo folder.
main()              prints the registry as a table and writes data/frozen/outcome_run_registry.json. No design is built
                    for it and no outcome is read: it is a list.

Adapters
--------
Only thin reshaping is done here, nothing that changes what is estimated: label parsing, the blocks with no comparison
rows left out before the long horizon's thirteen-year outcome vector is built (outcome_analysis.estimate_span leaves
them out of its stacking, and since session 19 stacked_rows_span does too, so the filter here is redundant and kept; the
kernel then names them), the removals of rule 2.4 rebuilt from supplier_exercise's own list of detected exclusions, and
the per-deletion designs of rule 7 rebuilt from influence.deletions' own rows through influence.leave_out, with the rules
and lists of the design they came from carried onto each.

Adding a built entry
--------------------
Write a runner `def _my_run(inputs, s, frame, entry) -> dict` that builds its design from RunInputs (quantities only),
builds the outcome vector with outcome_analysis.outcome_vector (or outcome_vector_span) on THAT design, calls the kernel
with validated_design=False, and returns the kernel's result with "estimated" set (estimate_design does all of this for
a Design). Any design changed after it was built gets carry_design_attributes(base, changed). A run that cannot be
computed raises or returns {"estimated": False, "failure_in_words": ...}; run() records it in words. Then add
Entry(id, section, sets, builder, estimator, labels + NV, BUILT, runner=_my_run) at its place in REGISTRY's order; an
estimator that is not the kernel names its own label (NOT_CALIBRATED, DESCRIPTIVE_CONTRAST) instead of NV. Any input
the run needs goes on RunInputs as an optional field and is fetched with inputs.need(attr, what).

Session 20 (Joe's rulings of 2026-11-19, D-105) built two entries and relabelled one. The five-highest-load deletion
(influence_load) ranks the hosts by data center load in GWh in their own event year 3, from side.dose's dc_gwh, drops
the five with their sub-experiments, keeps every other host's matches, carries the rules, makes the rank test before
any fit and estimates with validated_design=False; an exact tie at the line, a missing load or five or fewer hosts stop
it in words. The customer-weighted fit (weighted_fit) is a point estimate labelled descriptive with no range, its weights
side.q's res_customers in each host's reference year, with the nominal customer weight shares and the effective
contributions to the weighted headline reported apart. Callaway and Sant'Anna's range carries CS_RANGE_LABEL
(callaway_santanna.RANGE_LABEL): secondary and uncalibrated, the module's t-based construction on the bootstrap standard
error, never the package's interval. Neither new entry needs an input beyond what RunInputs.side already carries.

Session 21 (Joe's ruling of 2026-11-19, D-107) brought the registry to the modules other agents changed that day.
The second number: its bootstrap seed is second_number.BOOTSTRAP_SEED (second_number.bootstrap_rng; a config without a seed uses it, any
other seed is refused unless the config says the inputs are invented); the common-dose mapping is the ruled one
(common_dose_rule.established_as_ruled, Umatilla outside the exception); the two sensitivity scenarios (second_number_
scenarios, sensitivity scenarios and not bounds or necessarily one-change comparisons with the primary analysis) replace
the blocked entry, each with its sample's differences from the primary run's reported. Rows U and C return no
reproduction verdict (comparisons under our specification, the paper's band beside the pooled row U estimate and C0);
row U's entry carries its stopped steps. R7's runs are built: the three influence deletions (influence_deletions), the
size-band side run (size_band_run) and the timing run (timing_run); the inventory check (inventory_against_sales) runs
on its adopted settings and is told what its inputs are (RunInputs.inventory_inputs_are, refused for research data
before the freeze).

Session 22 (Joe's ruling of 2026-11-19, D-109). Row M is out of scope for this freeze: M0 to M4 are not run, the entry
has the status OUT_OF_SCOPE, sits after the executable order and is in no built count, and its code and tests are kept
dormant; its verdict logic is not applied, and the paper's published numbers are carried as context, nothing of ours
beside them as a test. Rows U and C are comparison-only: no step returns a reproduction verdict, the paper's figure and
band sit beside the pooled row U estimate and C0 as a comparison band, U1 returns the adopted sentences, and U0's
assignment is the smallest containing polygon over every polygon (our labelled approximation, the same rule as C0 to C2,
which is not independent validation). Row U's one stopped step is the Short Form rule outside 2019, and whether a
unit-year has a price is not used in place of the exclusion (reconciliation_mu.U_SHORT_FORM_NO_SUBSTITUTE). No assigned
site is not proof of no facility.

Session 24 (Joe's ruling of 2026-11-20, D-113). Stage 2 of the Short Form request was taken for its read and summaries
only, three columns of the one table (short_form_filers.py); the exclusion rule and its fallback are undecided, no rule is
coded, and row U's Short Form rule stays stopped outside 2019 (until session 25, a constant of this module said what the
stage 2 counts show). Exercise 4a
measured how often the early-years test detects a drift of 1% a year on the headline design; catches_drift_from_file
reads its result by name and gives the flag for the headline set, a figure carried into a reading the plan already
fixed, changing no rule.

Session 25 (Joe's ruling of 2026-11-20 on D-114, ledger entry D-115). Joe adopted row U's Short Form rule and its
fallback. A utility-state-year leaves where the Short Form table records a filing or, for 2019, the operational flag is
true; every other unit-year is kept with no record of a filing, which is no claim about whether it filed; the three-year
requirement is applied after the exclusion; the 2019 exclusion is explicitly incomplete. Row U's entry has no stopped
step (the constant that held one is gone), and the registry has no built entry with a stopped step. The caller passes
reconciliation_mu.ryu_spec(reconciliation_mu.U_SHORT_FORM_ADOPTED_CODE) and sample_flags from
short_form_filers.adopted_row_u_flags (NEEDS_U says how the frame is built); nothing here builds them, reads the Short
Form records or reads under data/raw. Row U stays comparison-only, and its sample is still not the paper's. E7's
quantity-side checks are wired on the quantity side for the headline set and for every cohort utility
(inventory_runs.E7_SETS); the E7 entries say what the caller's context for each set must be.

Session 26 (Joe's ruling of 2026-11-20 on D-116, ledger entry D-117). The three supplementary outcomes are settled
(supplementary_outcomes, which holds his words): the natural log of residential kWh per customer per month, of the
residential bill per customer per month in nominal dollars and of residential customer counts, with no constant added,
nothing imputed and nothing silently dropped. The caller's frame for each is the LEVEL in its Spec's unit, and
_other_outcome hands it to supplementary_outcomes.run_on_design, which takes the log; a missing, nonfinite or nonpositive
level on a required design row makes that outcome's result on that design non-computable, returned as a record with the
reasons and counts and no value, and it changes neither the headline price design nor the other outcomes. Row C's nominal
price is the panel's delivery-inclusive res_price in cents per kWh, put in real 2024 cents per kWh by the CPI-U annual
convention already adopted: our comparison specification and not a claim that the paper used exactly this construction
(reconciliation_c.PRICE_SERIES_LABEL; check_specification refuses another series, and no module can detect a frame built
from another column). The ownership classes of rows U and C come from the panel's entity type of each utility-state,
read as the last nonmissing value over the quantity panel's 2001 to 2025, time-invariant, each row's mapping unchanged
(reconciliation_mu.adopted_row_u_ownership_classes, reconciliation_c.adopted_row_c_ownership). Joe ruled the same day
(ledger entry D-119) that this type is kept, described as the utility-level modal reported type carried across the
panel and not the latest year-by-year EIA classification, with no further raw-data investigation
(reconciliation_mu.OWNERSHIP_DESCRIPTION_D119), and that the inventory-against-sales check is given the inventory as
built, the load history underlying the headline design, which the registry supplies as RunInputs.side.dose
(inventory_against_sales.INVENTORY_HISTORY_D119). E7's quantity-side shares
for every cohort utility are reported over the 36 hosts of the set's reference design, with the roster of 41 beside them,
by presentation only (e7_presentation). Nothing here reads, reshapes or assembles an outcome: every outcome frame is still
an argument the caller supplies, and the gate is unchanged.

Session 27 (Joe's approval of the freeze on 2026-11-20, D-120, and his authorization of bounded implementation work).
The plan is frozen at commit ea426c4. The door to outcomes is built in place of the NotImplementedError: it keeps the
gate file and the run's authorization, adds a check against git that the plan is the committed frozen one (the
session's reading of the freeze check), refuses the construction and simulation routes, and is tested with invented
readers and files only. Two disclosed enforcement gaps are closed. Row U on research data takes only the adopted Short
Form rule (D-115) and a specification equal to ryu_spec of it, with the gate file and the authorization required
(_row_u_guard; RunInputs.reconciliation_u_inputs_are, required). The inventory check and the headline design are shown
to use the same inventory as built (D-119) by equal content by hash against RunInputs.inventory_as_built and by the
headline set reproduced from side.dose (_same_inventory_as_built). Condition 4 takes its peak rows in the form
conditions.read_peaks returns (PEAKS_AS_READ) as well as in PEAK_COLUMNS form. When session 27 closed, GATE1_SIGNED did
not exist and no outcome had been read.

Readings that are the agent's, not the plan's, are marked where they are used.

Run:  python3 -I pipeline/analysis/run_outcomes.py      prints the registry, writes data/frozen/outcome_run_registry.json
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import callaway_santanna as csa  # noqa: E402
from pipeline.analysis import conditions as cn  # noqa: E402
from pipeline.analysis import design as dsg  # noqa: E402
from pipeline.analysis import estimators_table as et  # noqa: E402
from pipeline.analysis import future_hosts as fh  # noqa: E402
from pipeline.analysis import influence  # noqa: E402
from pipeline.analysis import influence_deletions as idl  # noqa: E402
from pipeline.analysis import influence_load as il  # noqa: E402
from pipeline.analysis import inventory_against_sales as ias  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import prefreeze_summaries as pf  # noqa: E402
from pipeline.analysis import reconciliation_c as rc  # noqa: E402
from pipeline.analysis import reconciliation_mu as rmu  # noqa: E402
from pipeline.analysis import second_number as sn  # noqa: E402
from pipeline.analysis import second_number_scenarios as ss  # noqa: E402
from pipeline.analysis import side_runs as sr  # noqa: E402
from pipeline.analysis import size_band_run as sbr  # noqa: E402
from pipeline.analysis import supplementary_outcomes as so  # noqa: E402
from pipeline.analysis import timing_run as tr  # noqa: E402
from pipeline.analysis import weighted_fit as wf  # noqa: E402
from pipeline.electricity import panel  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
OUT = FROZEN / "outcome_run_registry.json"
KEY = ps.KEY
OUTCOME = "value"                                   # the caller's outcome frame: utility_id_eia, state, year, value
AUTH_ENV = "DCUB_OUTCOME_RUN_AUTHORIZED"

# ---- statuses ---------------------------------------------------------------------------------------------------------
BUILT, DESIGN_ONLY, NEEDS_PACKAGE, BLOCKED, NOT_BUILT = "built", "design_only", "needs_package", "blocked", "not_built"
# Joe's ruling of 2026-11-19 (D-109): row M is out of scope for this freeze. An entry with this status is in no executable
# order of unblinding and in no built count; run() refuses it in words before any input is looked at.
OUT_OF_SCOPE = "out_of_scope_for_this_freeze"
STATUSES = (BUILT, DESIGN_ONLY, NEEDS_PACKAGE, BLOCKED, NOT_BUILT, OUT_OF_SCOPE)

# ---- outcomes ---------------------------------------------------------------------------------------------------------
PRICE = "log_residential_price"
# The three supplementary outcomes (Joe, 2026-11-20, D-117), named by supplementary_outcomes. The caller supplies each as a
# LEVEL in its Spec's unit (supplementary_outcomes.SPECS); the natural log is taken there, never here and never by the
# caller.
KWH = so.KWH                                         # "kwh_per_residential_customer"
BILL = so.BILL                                       # "bill_per_customer"
CUSTOMERS = so.CUSTOMERS                             # "residential_customers"
SUPPLEMENTARY = (KWH, BILL, CUSTOMERS)
# The reconciliation rows' price definitions, each its own named outcome frame (utility_id_eia, state, year, value) that
# the caller supplies. Nothing here builds a price. Rows M and U take price LEVELS (they log them). Row C takes the panel's
# delivery-inclusive res_price (reconciliation_c.OURS_PRICE_SERIES), nominal cents per kWh, converted by the caller to real
# 2024 cents per kWh with reconciliation_c.cpi_factors_to_2024 (the CPI-U annual convention, D-111): our comparison
# specification, settled by Joe on 2026-11-20 (D-117), and not a claim that the paper used exactly this construction
# (reconciliation_c.PRICE_SERIES_LABEL). No module can detect a frame built from another column
# (reconciliation_c.PRICE_SERIES_NOT_CHECKED).
PRICE_DEFAULT_SERVICE = rmu.DEFAULT_SERVICE          # "res_price_default_service": bundled revenue over bundled sales, a level
PRICE_DELIVERY_INCLUSIVE = rmu.DELIVERY_INCLUSIVE    # "res_price": our price with competitive supply added, a level
PRICE_CENTS_REAL_2024 = "res_price_cents_per_kwh_real_2024"     # row C's price, res_price in real 2024 cents per kWh
OUTCOMES = (PRICE, KWH, BILL, CUSTOMERS, PRICE_DEFAULT_SERVICE, PRICE_DELIVERY_INCLUSIVE, PRICE_CENTS_REAL_2024)
OUTCOME_IN_WORDS = {PRICE: "the log residential price",
                    **{n: f"the level of {so.SPECS[n].unit}, which supplementary_outcomes logs" for n in SUPPLEMENTARY},
                    PRICE_DEFAULT_SERVICE: "the default-service (bundled) residential price level",
                    PRICE_DELIVERY_INCLUSIVE: "the delivery-inclusive residential price level",
                    PRICE_CENTS_REAL_2024: (f"the panel's delivery-inclusive {rc.OURS_PRICE_SERIES} in cents per kWh, put "
                                            "in real 2024 cents per kWh by the CPI-U annual convention (our comparison "
                                            "specification, D-117)")}

# ---- sets -------------------------------------------------------------------------------------------------------------
HEADLINE_SET, TEN_YEAR_SET, PLUS_UNSETTLED, EVERY = ps.HEADLINE_SET, ps.TEN_YEAR_SET, dsg.PLUS_UNSETTLED, "every_cohort_utility"
E2_SAMPLE = "e2_eligible_future_host_sample"
H2, E2_ = (HEADLINE_SET, 0.02), (EVERY, 0.02)
PRIMARY_AND_COMPANION = (H2, E2_)                    # the Sets paragraph (Joe, D-99): headline at 2% and every cohort utility
SN_SAMPLE = ("second_number_sample", None)          # the second number's own sample (every usable unit with a region and size)
PAPER_SAMPLE = ("the_papers_specification_on_our_panel", None)   # rows M, U and C: their sample rules, not a set of ours
SIDE_BY_SIDE = ("four_stacked_sets_and_callaway_santanna_at_2pct", None)   # estimators_agree

# ---- labels -----------------------------------------------------------------------------------------------------------
HEADLINE = "headline"
VALIDATED_HERE = "the selected procedure (CR2, Satterthwaite) was validated on this design (headline set at 2%)"
NOT_VALIDATED = oa.NOT_VALIDATED
NOT_CALIBRATED = "not calibrated by the inference comparison"
SIDE_RUN = "side run"
EXPLORATORY = "exploratory"
SENSITIVITY = "labelled sensitivity"
STRESS_TEST = "stress test"
FALSIFICATION = "falsification and robustness run (reported whatever it shows; none is a gate)"
TIMING_WITH_REMATCHING = "timing sensitivity with rematching, not an isolated timing effect (G-a)"
REMOVES_UNITS = "removes units with no rematching (G-b)"
DESCRIPTIVE_CONTRAST = cn.DESCRIPTIVE_LABEL
POINT_ESTIMATES_ONLY = "point estimates only, no range per draw (E7)"
NEXT_TO_PRICE = "another outcome, reported next to price and not treated as a placebo"
READING = "the agent's reading: the plan does not settle this"
OTHER_ESTIMATOR = ("not applicable: an estimator other than the selected procedure, so no validation is claimed (None is "
                   "kept for the validated headline alone)")
QUANTITIES_ONLY = "not applicable: a quantity-side check that reads no outcome and estimates nothing on price"
RECONCILIATION = "reconciliation row: the paper's specification on our panel, reported first whatever it shows"
NO_OUTCOME = "none: reads quantities only"
# Rows U and C (Joe, 2026-11-19, D-107 and D-109): comparison-only; no step returns a reproduction verdict.
ROW_U_NO_VERDICT = ("comparisons under our specification, comparison-only by Joe's ruling of 2026-11-19 (D-109), no "
                    "reproduction verdict; the paper's figure and band are beside the pooled estimate as a comparison "
                    "band, and the ownership ordering is uncontrolled")
ROW_C_NO_VERDICT = ("comparisons under our specification, comparison-only by Joe's ruling of 2026-11-19 (D-109), no "
                    "reproduction verdict; every instrumented step and C5's yardstick, and C0 with the paper's figure and "
                    "band beside it as a comparison band")
# Row M (Joe, 2026-11-19, D-109): out of scope for this freeze.
ROW_M_OUT_OF_SCOPE_LABEL = ("out of scope for this freeze (Joe, 2026-11-19, D-109): M0 to M4 not run, the row's code "
                            "dormant")
ROW_M_CONTEXT_LABEL = "the paper's published numbers as the paper's, as context; nothing of ours beside them as a test"
NO_RANGE_NO_VALIDATION = ("not applicable: a descriptive contrast with no range and no test, so no validation is claimed "
                          "(None is kept for the validated headline alone)")
# Callaway and Sant'Anna's range (Joe, 2026-11-19, D-105): secondary and uncalibrated, the module's t-based construction on
# the bootstrap standard error, never the package's interval. callaway_santanna.RANGE_LABEL word for word.
CS_RANGE_LABEL = csa.RANGE_LABEL
# Callaway and Sant'Anna's comparison sample against the headline's (Joe, 2026-11-19, D-111): the 680 never-treated units in
# no cohort's host region stay in, disclosed prominently. callaway_santanna.REGION_SAMPLE_DIFFERENCE word for word.
CS_SAMPLE_DIFFERENCE = csa.REGION_SAMPLE_DIFFERENCE
# The customer-weighted fit (Joe, 2026-11-19, D-105): descriptive, no range, nominal customer weights kept apart from
# effective regression contributions (weighted_fit).
DESCRIPTIVE_WEIGHTED = wf.DESCRIPTIVE_LABEL
WEIGHTED_NO_VALIDATION = wf.NO_VALIDATION


class MissingInput(ValueError):
    """A built run needs an input the caller did not supply. Raised in words; the run is recorded as not computed."""


# ---- input bundles for the runs whose specification leaves elements open. No field has a default. ----------------------

@dataclass(frozen=True)
class RowMInputs:
    """DORMANT: row M is out of scope for this freeze by Joe's ruling of 2026-11-19 (D-109); this bundle and the runner
    that takes it (ROW_M_DORMANT_RUNNER) are kept as they are and nothing in the registry calls them.

    Row M (Meeks, Pless, Qi and Wang). spec: reconciliation_mu.MeeksSpec, its settled fields at the paper's values
    (file dated 2026-10-23) and every open element by name. treatments: {step: reconciliation_treatment.Treatment} for
    M0 to M4, first-year treatments built by first_year_above_size (M0 on the county-touch assignment, M1 to M3 on the
    verified one; the rule names how the 5 MW is counted) and first_year_at_dose (M4). ownership: KEY +
    ownership_class (reconciliation_mu.ownership_classes, scheme "M"). customers: accepted and not used (row M has no
    customer floor; pass None). sample_flags: REQUIRED (run_m_step refuses None in words): KEY, ever_short_form,
    short_form_first_year_read, short_form_last_year_read, has_three_classes, three_classes_test, plus year when
    three_classes_level is "unit_year" and has_retail_component when retail_component is "flag"."""
    spec: object
    treatments: dict
    ownership: pd.DataFrame
    customers: pd.DataFrame | None
    sample_flags: pd.DataFrame | None


@dataclass(frozen=True)
class RowUInputs:
    """Row U (Ryu and Hiatt). spec: reconciliation_mu.ryu_spec(reconciliation_mu.U_SHORT_FORM_ADOPTED_CODE), the
    Short Form rule Joe adopted on 2026-11-20 (D-115), every other field fixed (D-107). What these inputs are is
    RunInputs.reconciliation_u_inputs_are: on RESEARCH_DATA_AFTER_THE_FREEZE the registry's guard (_row_u_guard) refuses
    any other spec in words before a step runs; on INVENTED_INPUTS any of reconciliation_mu.SHORT_FORM_RULES is accepted
    for tests. treatments: {step: Treatment}
    for U0 to U3, cumulative-MW treatments on the inventory's site-year load (reconciliation_treatment.cumulative_mw; U0
    on the polygon assignment). ownership: KEY + ownership_class from
    reconciliation_mu.adopted_row_u_ownership_classes(q) on quantities that cover 2001 to 2025, the classes Joe settled on
    2026-11-20 (D-117 and D-119): the panel's entity type of each utility-state, the utility-level modal reported type
    carried across the panel and not the latest year-by-year EIA classification (D-119), read as the last nonmissing
    value over the quantity panel's 2001 to 2025 (D-117), time-invariant, mapped by reconciliation_mu.U_MAP unchanged, a
    unit with no type in any year given no class and never read as any class
    (reconciliation_mu.OWNERSHIP_SPECIFICATION_D117, OWNERSHIP_MISSING_TREATMENT). The panel's entity_type is one type
    per utility id, the type its own filings report most often, kept by Joe's ruling with no further raw-data
    investigation, and no claim is made that it equals EIA's year-by-year record
    (reconciliation_mu.PANEL_ENTITY_TYPE_STATEMENT). sample_flags: KEY + year + short_form,
    from short_form_filers.adopted_row_u_flags(frame, table, flags, step_window=(2015, 2025)) on a frame that covers
    every outcome unit-year reaching the Short Form filter at every step (U3's window is 2015 to 2025), with the filer
    table and the 2019 flags already on disk passed in (data/interim/reconciliation_short_form_filers.parquet and
    data/interim/reconciliation_short_form_flags.parquet; no new read under data/raw). Built that way they carry True
    where a record shows a filing and False (kept with no record of a filing, no claim about whether the unit filed)
    everywhere else. run_u_step refuses the rule in words on an outcome unit-year with no row or a missing flag, and the
    step is then recorded as not computed. Nothing here builds the flags. u1_indistinguishable: True,
    False or None, passed to reconciliation_mu.u1_sentence, which records it and decides nothing (the adopted U1
    sentences do not use it; D-109)."""
    spec: object
    treatments: dict
    ownership: pd.DataFrame
    sample_flags: pd.DataFrame | None
    u1_indistinguishable: bool | None


@dataclass(frozen=True)
class RowCInputs:
    """Row C (Scalera, Bosetti and Pecci), the arguments of reconciliation_c.run_row_c. choices must be
    reconciliation_c.SPECIFICATION and c4_cap reconciliation_c.OURS_C4_CAP (run_row_c refuses any other value in words).
    SPECIFICATION carries price_series = reconciliation_c.OURS_PRICE_SERIES ("res_price"): the outcome frame the caller
    supplies is the panel's delivery-inclusive res_price in cents per kWh, put in real 2024 cents per kWh with
    reconciliation_c.cpi_factors_to_2024, our comparison specification settled by Joe on 2026-11-20 (D-117) and not a
    claim that the paper used exactly this construction; check_specification refuses another series in words, and no
    module can detect a frame that was in fact built from another column (reconciliation_c.PRICE_SERIES_NOT_CHECKED).
    ownership: {(utility_id_eia, state): class} from reconciliation_c.adopted_row_c_ownership(q) on quantities that cover
    2001 to 2025 (D-117 and D-119): the panel's entity type, the utility-level modal reported type carried across the
    panel and not the latest year-by-year EIA classification (D-119), read as the last nonmissing value over the
    quantity panel's 2001 to 2025 (D-117), time-invariant, mapped by reconciliation_c.ROW_C_OWNERSHIP_MAP unchanged; a
    unit with no type in any year is absent from the mapping and the ownership split stops on it in words, never
    reading it as any class (the panel-column statement and Joe's ruling on it are
    reconciliation_mu.PANEL_ENTITY_TYPE_STATEMENT). share is an input the caller supplies, its content settled as the
    fiber shares from the December Form 477 filings (ours, adopted by Joe on 2026-11-19, D-107). counts_polygon may be None, and then C0 to C2 are reported as not run, with
    the reason."""
    choices: object
    counts_polygon: pd.DataFrame | None
    counts_verified: pd.DataFrame
    dose_verified: pd.DataFrame
    share: dict
    spending_tables: dict
    ownership: dict
    c4_cap: float | None
    hosts_for_c5: set
    c5_counts_name: str


@dataclass(frozen=True)
class CSSampleInputs:
    """The Callaway and Sant'Anna sample's lists (callaway_santanna.sample): the host and comparison set-asides
    (design.split's lists), the price hold (power_simulation.price_hold()) and the D-34 history (a dict, empty for none).
    Passed so that no file is read here."""
    host_aside: set
    comparison_aside: set
    hold: set
    history: dict


@dataclass(frozen=True)
class E5Inputs:
    """E5's inputs under Joe's ruling of 2026-11-19: the report's state_anchor block (side_runs.read_state_anchor_block())
    and the FULL state_anchor table (data/interim/state_anchor.parquet). E5's list of states is built from them by
    side_runs.e5_states and never typed by the caller."""
    block: list
    all_states: pd.DataFrame


# ---- what the caller's inputs are, and the inventory as built (session 27; Joe, 2026-11-20, D-120, item 4) -----------------
# Two notions, in words, as inventory_against_sales has them: invented inputs (tests) and research data after the freeze.
INVENTED_INPUTS = ias.INVENTED_INPUTS
RESEARCH_DATA_AFTER_THE_FREEZE = ias.RESEARCH_DATA_AFTER_THE_FREEZE
INPUTS_ARE = (INVENTED_INPUTS, RESEARCH_DATA_AFTER_THE_FREEZE)


def frame_fingerprint(frame: pd.DataFrame) -> str:
    """sha256 of a frame's content: its column names and types, its number of rows and every row's values, whatever the
    order of its rows and columns. Two frames with the same fingerprint hold the same rows. No value is shown."""
    f = frame.reindex(columns=sorted(frame.columns, key=str))
    rows = np.sort(pd.util.hash_pandas_object(f, index=False).to_numpy(dtype="uint64"))
    m = hashlib.sha256()
    m.update(json.dumps([[str(c), str(f[c].dtype)] for c in f.columns]).encode())
    m.update(str(len(f)).encode())
    m.update(rows.tobytes())
    return m.hexdigest()


@dataclass(frozen=True)
class InventoryAsBuilt:
    """The stamp the input assembler puts on the dose frame the sets were split from: the inventory as built, the load
    history underlying the headline design (Joe, 2026-11-20, D-119; inventory_against_sales.INVENTORY_HISTORY_D119).
    dose_fingerprint: frame_fingerprint of that frame, taken when the sets were split. source: where the frame came from,
    in words. split: None for design.split, the function the sets are split with on research data; a test on invented
    inputs may pass its own (theta, which, q, dose) -> (hosts with cohort, comparison-eligible units)."""
    dose_fingerprint: str
    source: str
    split: object = None


# ======================================================================================================================
# Inputs (quantities only)
# ======================================================================================================================

@dataclass
class RunInputs:
    """Everything the design builders take, from quantity files only. No price, revenue or bill.

    side                side_runs.Inputs under the headline rules: q, dose, regions, fuel, dd, ownership, usable, gas,
                        unknown_load, ownership_of
    sets                {(set name, threshold): (hosts with cohort, comparison-eligible units)}, as design.split gives
                        them at 2% and 5%; at 1% as every_cohort_utility_at(0.01, q, dose, d34_table=, hold=) gives them
                        (the D-34 table and the price hold passed explicitly; side_runs.every_cohort_at now requires
                        the history and the hold as well)
    suppliers, omissions  suppliers.load() and prefreeze_summaries.load_known_omissions() (rule 2.4)
    e5_anchor           E5Inputs: the state_anchor block and the full table; E5's list is side_runs.e5_states(...)["dropped"]
    e6_changers         E6's fixed list of comparison units that change region (side_runs.region_changers(...)["coded"])
    future_admitted     {cohort: [unit keys]}: future hosts admitted for each cohort and meeting the other rules
                        (future_hosts.main's admitted_by_cohort)
    e2_histories        {unit key: history record} as future_hosts.late_host_histories() returns them; E2's pseudo-hosts are
                        selected here by future_hosts.e2_units WITH the ownership table (Joe's ruling of 2026-11-19)
    e2_aside, e2_hold   the set-aside list and the price hold e2_units takes (sets; empty for none)
    e2_late             every late host (future_hosts.late_host_histories), kept out of E2's pool
    inventory           inventory_runs.Inventory (the rebuilt inventory in memory)
    inventory_contexts  {set name: inventory_runs.Context} for each set the inventory runs apply to (E4a, E4b, E7):
                        inventory_runs.Context.from_files(0.02) for the headline set and
                        inventory_runs.Context.from_files(0.02, which="every_cohort_utility") for every cohort utility,
                        which gives that set no set-aside list, as design.split does (inventory_runs.aside_for)
    e7_errors, e7_draws inventory_runs.load_errors() and the number of draws a direction (200 in the plan)
    peaks               the peak-demand rows for condition 4, in either form: PEAKS_AS_READ (utility_id_eia, state, year,
                        peak_mw, short_form, data_observed), what conditions.read_peaks returns and what the session's
                        one authorized read retains, used as it is after a check of its columns; or
                        conditions.PEAK_COLUMNS form, which goes through conditions.read_peaks(frame) (peaks_as_read)
    has_predecessors    panel units with summed predecessors (condition 4)
    succession          the succession table (pipeline.electricity.succession.load()), condition 4's footprint tests
    second_number       {"units": [...], "boot": int,
                         "assigned": {cap label: {uid: change as assigned}},
                         "changes": {cap label: {uid: within-history changes (an array)}},
                         "reach": {uid: bool}, "no_assigned": [uid],
                         "established": {uid: {cap label: {"established", "dose", "why"}}},
                         "scenario_units": [...], "scenario_points": {name: points}, "scenario_no_dose": {name: [...]},
                         and optionally "seed" and "invented_inputs"}
                        from second_number's own machinery. The bootstrap draws from second_number.bootstrap_rng: seed
                        second_number.BOOTSTRAP_SEED (Joe, D-107) when "seed" is absent or None; any other seed is refused in words unless
                        "invented_inputs" is True (tests). The runs on single doses classify each form at its own cap
                        (second_number.classify_by_cap, the adopted classification of D-105). `established` is the
                        common-dose mapping as ruled (common_dose_rule.established_as_ruled, equivalently
                        second_number.common_dose_finding()[0]; D-107) and is REQUIRED: a config without the key is
                        refused in words. The two sensitivity scenarios (second_number_scenarios.SCENARIOS) take
                        "scenario_units" (every panel unit less the price hold, the two load-unknown units included),
                        "scenario_points"[name] (load share in points by unit and year, second_number_scenarios.points_of
                        on realise_history) and "scenario_no_dose"[name] (the units with load and no positive base)
    catches_drift       {set name: bool}: whether the early-years test catches a drift of 1% a year in fewer than half
                        of datasets on that set (Reported checks). For the headline set at 2% the figure is in
                        data/frozen/early_years_drift_selected_procedure.json, the result of exercise 4a run once under
                        Joe's ruling of 2026-11-20 (D-113), whose two measured detection rates (G0 0.129, G6 0.0475) are
                        both under one half; catches_drift_from_file() reads it and gives True for that set alone. It is
                        a figure carried into a reading the plan already fixed and changes no rule, and it is a property
                        of this test on this design under made-up prices of two assumed kinds, not evidence about real
                        pre-trends. Nothing here fills this field: a caller passes it, and with no value for a set no
                        second sentence is selected
    names               (utility, state) -> name, for reports
    reconciliation_m, reconciliation_u, reconciliation_c
                        RowMInputs, RowUInputs, RowCInputs (rows M, U and C)
    inventory_inputs_are
                        what the inventory check's frames are: inventory_against_sales.INVENTED_INPUTS (tests) or
                        RESEARCH_DATA_AFTER_THE_FREEZE, which the module refuses unless the gate file exists and the run
                        is authorized. Required by that entry: None stops it in words and no value is chosen here. The
                        check reads side.q (nonres_mwh) and side.dose (dc_gwh) and no outcome
    reconciliation_u_inputs_are
                        what row U's inputs are: INVENTED_INPUTS (tests) or RESEARCH_DATA_AFTER_THE_FREEZE. Required by
                        that entry: None stops it in words and no value is chosen here. On research data the row is
                        refused in words without the gate file and the run's authorization, and the row's
                        specification must carry the Short Form rule Joe adopted on 2026-11-20 (D-115),
                        reconciliation_mu.U_SHORT_FORM_ADOPTED_CODE, and any other code is refused in words; so is any
                        specification not equal to ryu_spec(U_SHORT_FORM_ADOPTED_CODE) (session 27, _row_u_guard)
    inventory_as_built  InventoryAsBuilt: the stamp of the dose frame the sets were split from. On research data the
                        inventory check requires it and refuses in words unless side.dose is that frame and the headline
                        set, split again from side.dose, is the set supplied (session 27, _same_inventory_as_built); on
                        invented inputs the same checks run when a stamp is supplied
    inventory_readings  obsolete: the check's four elements are settled (D-107). None passes
                        inventory_against_sales.ADOPTED; a Readings is passed as given (Readings accepts only ADOPTED)
    timing_added        {(utility_id_eia, state): year}: the timing run's added hosts at their no-anchoring years, from
                        timing_run.no_anchoring_years(<the treatment_bounds.json record at timing_run.RECORD_PATH>,
                        <headline_set.csv frame>)["years"]. Required by that entry: None stops it in words; no file is
                        read here
    cs_sample           CSSampleInputs (Callaway and Sant'Anna)
    validation_reference
                        outcome_analysis.read_validation_reference(): the hashes of the validated design's inputs and
                        rules from the step E files. main_headline_set claims validation with it; without it the
                        headline is labelled NOT_VALIDATED and says why
    """
    side: sr.Inputs
    sets: dict
    suppliers: pd.DataFrame | None = None
    omissions: pd.DataFrame | None = None
    e5_anchor: E5Inputs | None = None
    e6_changers: set | None = None
    future_admitted: dict | None = None
    e2_histories: dict | None = None
    e2_aside: set | None = None
    e2_hold: set | None = None
    e2_late: set | None = None
    inventory: object = None
    inventory_contexts: dict | None = None
    e7_errors: dict | None = None
    e7_draws: int = 200
    peaks: pd.DataFrame | None = None
    has_predecessors: set = field(default_factory=set)
    succession: pd.DataFrame | None = None
    second_number: dict | None = None
    catches_drift: dict | None = None
    names: dict | None = None
    validation_reference: object = None
    reconciliation_m: RowMInputs | None = None
    reconciliation_u: RowUInputs | None = None
    reconciliation_c: RowCInputs | None = None
    inventory_readings: object = None
    inventory_inputs_are: str | None = None
    reconciliation_u_inputs_are: str | None = None
    inventory_as_built: InventoryAsBuilt | None = None
    timing_added: dict | None = None
    cs_sample: CSSampleInputs | None = None

    def set_frames(self, s: tuple) -> tuple[pd.DataFrame, pd.DataFrame]:
        if s not in self.sets:
            raise MissingInput(f"the set {set_label(s)} was not supplied (RunInputs.sets)")
        return self.sets[s]

    def need(self, attr: str, what: str):
        v = getattr(self, attr)
        if v is None:
            raise MissingInput(f"{what} was not supplied (RunInputs.{attr})")
        return v

    def need_side(self, attr: str, what: str):
        v = getattr(self.side, attr, None)
        if v is None:
            raise MissingInput(f"{what} was not supplied (RunInputs.side.{attr})")
        return v

    def build(self, s: tuple, rules: ps.Rules | None = None, treated=None, clean=None) -> dsg.Design:
        """design.build_with_rules for set `s` under `rules` (the headline rules by default)."""
        t, c = self.set_frames(s) if treated is None else (treated, clean)
        i = self.side
        return dsg.build_with_rules(t, c, i.q, i.regions, i.fuel, i.dd, rules or i.rules, ownership=i.ownership,
                                    usable=i.usable, gas=i.gas, ownership_of=i.ownership_of, unknown_load=i.unknown_load,
                                    theta=s[1])

    def build_kw(self, theta: float) -> dict:
        i = self.side
        return dict(ownership=i.ownership, usable=i.usable, gas=i.gas, ownership_of=i.ownership_of,
                    unknown_load=i.unknown_load, theta=theta)


def set_label(s: tuple) -> str:
    return s[0] if s[1] is None else f"{s[0]} at {s[1]:.0%}"


def _key(label: str) -> tuple:
    u, st = label.split(":")
    return (int(u), st)


def _label(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def _words(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


# ======================================================================================================================
# Shared pieces
# ======================================================================================================================

def design_facts(d) -> dict:
    """Quantity-only facts about a design, so nothing is silently dropped: hosts with cohorts and matches, every host
    dropped with its reason, and the lists the builders attach (G-b, unresolved ownership, load unknown)."""
    hosts = ([{"utility": _label(k), "cohort": int(g), "matches": [_label(m) for m in mk]}
              for k, g, mk in zip(d.hosts.key, d.hosts.cohort, d.hosts.match_keys)] if len(d.hosts) else [])
    out = {"hosts": hosts, "hosts_dropped": list(getattr(d, "dropped", []) or [])}
    for attr in ("gb", "unresolved_ownership", "load_unknown_excluded"):
        v = getattr(d, attr, None)
        if v is not None:
            out[attr] = v
    return out


def failure_in_words(r: dict) -> str | None:
    f = r.get("numerical_failure")
    if not f:
        return None
    return f"{f['in_words']} ({f['cause']}, at {f['where']}){': ' + f['detail'] if f.get('detail') else ''}"


def estimate_design(d, frame: pd.DataFrame, *, validated, absorbed: str | None = None, main_set: tuple | None = None,
                    inputs: RunInputs | None = None) -> dict:
    """outcome_analysis.estimate on design `d` for the caller's outcome, aligned by outcome_analysis.outcome_vector.

    `validated` False attaches NOT_VALIDATED; an outcome_analysis.ValidationClaim is checked by the kernel. With `main_set` (a main estimate) the early-years sentences and the six
    trend illustrations are attached (Reported checks); the sentences need RunInputs.catches_drift for the set, and where
    it is not supplied the record says so and chooses no sentence."""
    y = oa.outcome_vector(d, frame, OUTCOME)
    r = oa.estimate(d, y, validated_design=validated, absorbed_controls=absorbed)
    r["numerical_failure_in_words"] = failure_in_words(r)
    r["design"] = design_facts(d)
    if main_set is not None:
        r["trend_illustrations"] = oa.trend_illustrations(r)
        flag = (inputs.catches_drift or {}).get(main_set[0]) if inputs is not None else None
        r["early_years_reading"] = (oa.early_years_reading(r, flag) if isinstance(flag, bool) else
                                    ["not chosen: whether the test catches a drift of 1% a year in fewer than half of "
                                     "datasets on this set was not supplied (RunInputs.catches_drift)"])
    r["estimated"] = r["headline"]["log_points"] == r["headline"]["log_points"]       # a point estimate computed
    return r


EARLY_YEARS_DRIFT_FILE = FROZEN / "early_years_drift_selected_procedure.json"


class DriftFileRefused(ValueError):
    """The early-years drift file is not the one exercise 4a wrote on the current design, or holds an outcome its module
    does not define. Raised in words; no value is returned for any set."""


def catches_drift_from_file(path=None) -> dict:
    """RunInputs.catches_drift for the headline set, read BY NAME from the result of exercise 4a
    (data/frozen/early_years_drift_selected_procedure.json by default; its module pipeline/analysis/early_years_drift.py,
    its specification docs/gate1/simulation-spec-4a-early-years-drift-2026-11-20.md; Joe, 2026-11-20, D-113).

    Its reading_rule.outcome is one of the module's three strings. early_years_drift.ADDED (both processes' measured
    detection rates under one half) gives {HEADLINE_SET: True}; NOT_ADDED (both at or over) gives {HEADLINE_SET: False};
    SPLIT gives {}, and so does an absent file, so the code goes on selecting no second sentence. The value is for the
    headline set at 2% only: the exercise ran on that design, and every other set, the companion sets included, gets
    none. It is a figure carried into a reading the plan already fixed and changes no rule. The rates are a property of
    this test on this design under made-up prices of two assumed kinds and are not evidence about real pre-trends.

    Refused in words (DriftFileRefused) if the file's design_inputs_sha256 does not begin with
    early_years_drift.REQUIRED_DESIGN_INPUTS, if its seed or its drift is not the module's, or if the outcome is not one
    of the three strings. Nothing in this module calls it: a caller passes its value as RunInputs.catches_drift. The file
    is a frozen summary of made-up prices and holds no price, revenue or bill."""
    from pipeline.analysis import early_years_drift as eyd      # imported here so that importing this module runs nothing new
    p = EARLY_YEARS_DRIFT_FILE if path is None else Path(path)
    if not p.exists():
        return {}
    doc = json.loads(p.read_text())
    h = doc.get("design_inputs_sha256")
    if not isinstance(h, str) or not h.startswith(eyd.REQUIRED_DESIGN_INPUTS):
        raise DriftFileRefused(f"{p.name}: its design-inputs hash {h!r} does not begin with "
                               f"{eyd.REQUIRED_DESIGN_INPUTS!r}, the design exercise 4a requires; no value is given")
    seed = doc.get("seed")
    if isinstance(seed, bool) or seed != eyd.SEED:
        raise DriftFileRefused(f"{p.name}: its seed {seed!r} is not exercise 4a's ({eyd.SEED}); no value is given")
    drift = doc.get("drift_log_points_a_year")
    if isinstance(drift, bool) or drift != eyd.DRIFT:
        raise DriftFileRefused(f"{p.name}: its drift {drift!r} is not exercise 4a's ({eyd.DRIFT} log points a year); no "
                               "value is given")
    outcome = (doc.get("reading_rule") or {}).get("outcome")
    if outcome not in (eyd.ADDED, eyd.NOT_ADDED, eyd.SPLIT):
        raise DriftFileRefused(f"{p.name}: its reading-rule outcome {outcome!r} is none of {eyd.ADDED!r}, "
                               f"{eyd.NOT_ADDED!r} and {eyd.SPLIT!r}; no value is given")
    if outcome == eyd.SPLIT:
        return {}
    return {HEADLINE_SET: outcome == eyd.ADDED}


carry_design_attributes = pf.carry_design_attributes


def every_cohort_utility_at(theta: float, q: pd.DataFrame, dose: pd.DataFrame, *, d34_table: pd.DataFrame, hold: set) -> tuple:
    """(hosts with cohort, comparison-eligible units) for every cohort utility as built at `theta` (the 1% run's set):
    power_simulation.design with D-34 at `theta` read from `d34_table` (side_runs.history_at, given the table) and the
    price hold `hold`. Both are required, with no default, and None is refused: side_runs.every_cohort_at read the D-34
    table (pipeline/facilities/verified/utility_history.csv) when no history was passed, and power_simulation.design reads
    price_hold.csv when no hold is passed (before session 19; every_cohort_at now requires both), so a run on invented inputs
    could pick up real lists of units without saying so. No file is opened here. The caller reads the two lists (utility_history.load(), power_simulation.price_hold()) and
    passes them. Both are lists of units, not prices."""
    if d34_table is None:
        raise MissingInput("the D-34 table (pipeline.facilities.utility_history.load()) was not supplied; an empty frame "
                           "means no utility-level figures")
    if hold is None:
        raise MissingInput("the price hold (power_simulation.price_hold()) was not supplied; an empty set means no unit held")
    return sr.every_cohort_at(theta, q, dose, history=sr.history_at(theta, q, dose, table=d34_table), hold=set(hold))


def _roster(inputs: RunInputs, s: tuple) -> pd.DataFrame:
    from pipeline.analysis import inventory_runs as ir
    return ir.roster_of(inputs.set_frames(s)[0])


def _inventory(inputs: RunInputs, s: tuple):
    inv = inputs.need("inventory", "the rebuilt inventory (inventory_runs.Inventory)")
    ctxs = inputs.need("inventory_contexts", "the inventory runs' contexts (inventory_runs.Context per set)")
    if s[0] not in ctxs:
        raise MissingInput(f"no inventory_runs.Context for {set_label(s)} (RunInputs.inventory_contexts)")
    return inv, ctxs[s[0]]


# ======================================================================================================================
# Runners: one per kind of run. Each takes (inputs, set, outcome frame, entry) and returns a dict.
# ======================================================================================================================

def _main(inputs, s, frame, entry):
    d = inputs.build(s)
    claim = (oa.ValidationClaim(inputs.validation_reference, inputs.side.usable)
             if entry.id == "main_headline_set" and s == H2 else False)
    return estimate_design(d, frame, validated=claim, main_set=s, inputs=inputs)


def _non_computable_in_words(rec: dict) -> str:
    """supplementary_outcomes' sentence with counts, then the affected unit-years by key (at most
    supplementary_outcomes.EXAMPLES per reason). Keys and counts only: no value of an outcome."""
    keys = [f"{reason}: {', '.join(c['examples'])}" for reason, c in rec["reasons"].items() if c["unit_years"]]
    return (rec["in_words"] + f" Affected unit-years by key (at most {so.EXAMPLES} for each reason): " + "; ".join(keys)
            + ".")


def _other_outcome(inputs, s, frame, entry):
    """A supplementary outcome (Joe, 2026-11-20, D-117) on the main specification's design. `frame` holds the LEVEL in
    the Spec's unit (supplementary_outcomes.SPECS[entry.outcome].unit); supplementary_outcomes.run_on_design takes its
    natural log on exactly the design's required unit-years and calls estimate_design on it with validated_design=False.
    A missing, nonfinite or nonpositive level on a required row makes the result non-computable: it is returned as a
    record (estimated False, computable False, the reasons and counts, the affected unit-years by key in
    failure_in_words) and nothing is estimated. It is never raised out of the runner, it carries no value, and no other
    outcome or set is touched by it."""
    d = inputs.build(s)
    r = so.run_on_design(d, frame, entry.outcome, lambda dd, logged: estimate_design(dd, logged, validated=False))
    r["label"] = so.SUPPLEMENTARY_LABEL
    r["validation_limit"] = so.VALIDATION_LIMIT
    if not r.get("computable"):
        r.update(validation=NOT_VALIDATED, design=design_facts(d),
                 failure_in_words=_non_computable_in_words(r["non_computable"]))
    return r


def _rules_variant(rules):
    def run_(inputs, s, frame, entry):
        d = inputs.build(s, rules)
        r = estimate_design(d, frame, validated=False)
        r["rules"] = rules.label
        return r
    return run_


def _unresolved(inputs, s, frame, entry):
    sens = inputs.build(s, ps.UNRESOLVED_OWNERSHIP_EXCLUDED)
    head = inputs.build(s)
    r = estimate_design(sens, frame, validated=False)
    r["rules"] = ps.UNRESOLVED_OWNERSHIP_EXCLUDED.label
    r["against_the_headline_rules"] = pf.unresolved_ownership_sensitivity(head, sens, inputs.names)
    return r


def _suppliers(inputs, s, frame, entry):
    table = inputs.need("suppliers", "the supplier table (suppliers.load())")
    d = inputs.build(s)
    ex = pf.supplier_exercise(d, table, inputs.omissions, inputs.names)
    removals: dict = {}
    for x in ex["detected_exclusions"]:
        removals.setdefault((_key(x["host"]), int(x["cohort"])), set()).add(_key(x["match"]))
    e = pf.remove_pairs(d, removals)
    r = estimate_design(e, frame, validated=False)
    r["rule"] = ("rule 2.4: per host and match pair, no rematching; a host left with fewer than five matches is named as "
                 "inadequately supported and stays in; a host left with none or with zero weight is not estimable and "
                 "named, the estimate over the rest")
    r["supplier_exercise"] = {k: ex[k] for k in ("counts", "detected_exclusions", "known_omissions_reaching_this_design",
                                                 "after_removal_no_rematching", "negative_finding_means")}
    r["supplier_exercise"]["unknown_pairs_counted_not_removed"] = len(ex["unknown_pairs"])
    return r


def _deletions(kind: str):
    """Rule 7 on outcomes: each deletion of influence.deletions (kind "comparison" or "company") formed by
    influence.leave_out, then the kernel. What influence.deletions already returns on quantities (units, net weight
    removed, hosts under five, hosts with no matches or zero weight, the rank test) is carried; only the estimate and its
    range are added."""
    def run_(inputs, s, frame, entry):
        d = inputs.build(s)
        fc = d.rules.fuel_control
        dels = influence.deletions(d, inputs.side.ownership, inputs.side.ownership_of, fc)
        rows = dels[dels.kind == kind]
        full = estimate_design(d, frame, validated=False)
        base = full["headline"]["log_points"]
        out = []
        for r in rows.itertuples():
            e = carry_design_attributes(d, influence.leave_out(d, {_key(u) for u in r.units}))
            rec = {"removed": r.removed, "units": list(r.units), "net_weight_removed": float(r.net_weight_removed),
                   "hosts_with_fewer_than_five_matches_inadequate_support": list(r.hosts_with_fewer_than_five_matches),
                   "hosts_not_estimable_no_matches": list(r.hosts_with_no_matches),
                   "hosts_not_estimable_zero_weight": list(r.hosts_with_zero_weight),
                   "estimable_by_the_rank_test_before_any_fit": bool(r.estimable)}
            try:
                k = oa.estimate(e, oa.outcome_vector(e, frame, OUTCOME), validated_design=False)
                h = k["headline"]
                rec.update(estimate_log_points=h["log_points"], range_90_log_points=h["range_90_log_points"],
                           status=h["status"], count_N=k["count_N"], numerical_failure_in_words=failure_in_words(k),
                           validation=k["validation"])
                lo_hi = h["range_90_log_points"]
                rec["range_includes_zero"] = None if lo_hi is None else bool(lo_hi[0] <= 0 <= lo_hi[1])
            except Exception as exc:                                    # noqa: BLE001  counted, never dropped
                rec.update(estimate_log_points=float("nan"), range_90_log_points=None, status="not computed",
                           numerical_failure_in_words=_words(exc), validation=NOT_VALIDATED)
            out.append(rec)
        ests = [(x["estimate_log_points"], x["removed"]) for x in out if np.isfinite(x["estimate_log_points"])]
        most = max(ests, key=lambda t: abs(t[0] - base)) if ests and np.isfinite(base) else None
        return {"estimated": bool(ests), "validation": NOT_VALIDATED, "full_design": full, "deletions": out,
                "company_rows": dels.attrs.get("company_rows") if kind == "company" else None,
                "range_of_estimates_across_deletions": [min(e for e, _ in ests), max(e for e, _ in ests)] if ests else None,
                "deletion_that_moves_it_most": None if most is None else {"removed": most[1], "estimate_log_points": most[0],
                                                                          "moves_by_log_points": most[0] - base},
                "deletions_with_inadequate_support": sum(bool(x["hosts_with_fewer_than_five_matches_inadequate_support"]) for x in out),
                "deletions_with_a_host_not_estimable": sum(bool(x["hosts_not_estimable_no_matches"] or x["hosts_not_estimable_zero_weight"])
                                                           for x in out),
                "deletions_not_computed": [x["removed"] for x in out if not np.isfinite(x["estimate_log_points"])],
                "zero_note": "a deletion that makes the range include zero is reported as that, not as a reversal (rule 7)"}
    return run_


def _redated_design(inputs, s, rebuilt_dose, frame, extra: dict):
    """inventory_runs.redate on an alternative dose (eligibility re-read, then G-a), then the kernel."""
    from pipeline.analysis import inventory_runs as ir
    inv, ctx = _inventory(inputs, s)
    roster = _roster(inputs, s)
    ref = ir.redate(ctx, ir.dose_frame(inv.fy, inv.base), roster)
    alt = ir.redate(ctx, rebuilt_dose, roster, ref)
    summary = ir.summarise(alt)
    if alt.design is None or not len(alt.design.hosts):
        return {"estimated": False, "validation": NOT_VALIDATED, "redated": summary, **extra,
                "failure_in_words": "no host of the roster is retained on the alternative inventory: not estimable"}
    r = estimate_design(alt.design, frame, validated=False)
    r.update(redated=summary, **extra)
    return r


def _e4a(inputs, s, frame, entry):
    from pipeline.analysis import inventory_runs as ir
    inv, _ = _inventory(inputs, s)
    rb, rec = ir.e4a(inv)
    return _redated_design(inputs, s, ir.dose_frame(rb.fy, inv.base), frame, {"rows": rec, "factors": rb.factors})


def _e4b(inputs, s, frame, entry):
    from pipeline.analysis import inventory_runs as ir
    inv, _ = _inventory(inputs, s)
    rb = ir.e4b(inv)
    return _redated_design(inputs, s, ir.dose_frame(rb.fy, inv.base), frame, {"factors": rb.factors})


def _later_start(k: int):
    def run_(inputs, s, frame, entry):
        from pipeline.analysis import inventory_runs as ir
        inv, _ = _inventory(inputs, s)
        changed, bad = ir.later_start_rows(inv, k)
        rb = ir.rebuild(inv, changed, "recompute")
        return _redated_design(inputs, s, ir.dose_frame(rb.fy, inv.base), frame,
                               {"shift_years": k, "rows_whose_history_changes": len(changed), "incompatible_shifts": bad})
    return run_


def _e7(direction: str):
    """E7 in one direction: every draw's design (inventory_runs.e7_designs), the kernel's point estimate per draw. A draw
    that cannot be computed is counted by cause (a count of zero included); the 5th, 50th and 95th percentiles are over the
    draws that computed and say so. A draw is "computed" when its point estimate is finite: a failure of the selected
    procedure's range does not remove a point estimate, since E7 reports point estimates only (the agent's reading)."""
    def run_(inputs, s, frame, entry):
        from pipeline.analysis import inventory_runs as ir
        inv, ctx = _inventory(inputs, s)
        errors = inputs.need("e7_errors", "E7's permit-error distribution (inventory_runs.load_errors())")
        roster = _roster(inputs, s)
        ref = ir.redate(ctx, ir.dose_frame(inv.fy, inv.base), roster)
        draws, ests, causes, hosts_n = [], [], {}, []
        for dr in ir.e7_designs(ctx, inv, roster, direction, range(int(inputs.e7_draws)), reference=ref, errors=errors):
            draws.append(dr)
            if dr.failure is not None:
                c = "draw: " + dr.failure.split(":", 1)[0]
                causes[c] = causes.get(c, 0) + 1
                continue
            d = dr.redated.design
            if d is None or not len(d.hosts):
                causes["no host retained in the draw"] = causes.get("no host retained in the draw", 0) + 1
                continue
            try:
                k = oa.estimate(d, oa.outcome_vector(d, frame, OUTCOME), validated_design=False)
            except Exception as exc:                                    # noqa: BLE001  counted by cause
                c = "kernel: " + type(exc).__name__
                causes[c] = causes.get(c, 0) + 1
                continue
            v = k["headline"]["log_points"]
            if not np.isfinite(v):
                c = "kernel: " + (k["numerical_failure"] or {}).get("cause", "point estimate not finite")
                causes[c] = causes.get(c, 0) + 1
                continue
            ests.append(float(v))
            hosts_n.append(int(k["count_N"]) if k["count_N"] is not None else None)
        pct = {f"p{p}": float(np.percentile(ests, p)) for p in (5, 50, 95)} if ests else None
        return {"estimated": bool(ests), "validation": NOT_VALIDATED, "direction": direction,
                "draws_attempted": len(draws), "draws_computed": len(ests),
                "draws_that_could_not_be_computed": {"count": len(draws) - len(ests), "by_cause": causes},
                "percentiles_of_the_headline_point_estimate_log_points": pct,
                "percentiles_are_over": f"the {len(ests)} draws that computed, of {len(draws)}",
                "percentile_method": "numpy.percentile, linear interpolation (the agent's reading; the plan names none)",
                "point_estimates_log_points": ests,
                "quantity_side": ir.e7_summary(draws, roster, ir.e7_rows(inv)),
                "label": POINT_ESTIMATES_ONLY}
    return run_


def _longer_horizon(inputs, s, frame, entry):
    t, c = inputs.set_frames(s)
    lh = sr.long_horizon(inputs.side, t, c, s[1])
    if not len(lh.design.hosts):
        return {"estimated": False, "validation": NOT_VALIDATED, "design": design_facts(lh.design), "report": lh.report,
                "failure_in_words": "no host retained for the longer horizon: not estimable"}
    post = oa.windows_len(next(iter(lh.windows13.values()))) - ps.PRE - 1
    stacked = [b for b in lh.blocks13 if len(b[2])]                    # estimate_span leaves the others out; it names them
    y13 = oa.outcome_vector_span(lh.windows13, stacked, ps.PRE, post, frame, OUTCOME)
    y10 = oa.outcome_vector(lh.design, frame, OUTCOME)
    r = oa.estimate_long_horizon(lh, y13, y10)
    six, three = r["six_years"], r["three_years_same_utilities"]
    r.update(estimated=bool(np.isfinite(six["headline"]["log_points"])), design=design_facts(lh.design), report=lh.report,
             numerical_failure_in_words={"six_years": failure_in_words(six), "three_years_same_utilities": failure_in_words(three)})
    return r


def _future_hosts(inputs, s, frame, entry):
    admitted = inputs.need("future_admitted", "the future hosts admitted by cohort (future_hosts.main's admitted_by_cohort)")
    t, c = inputs.set_frames(s)
    i = inputs.side
    d = fh.side_run_design(t, c, admitted, i.q, i.regions, i.fuel, i.dd, i.rules, **inputs.build_kw(s[1]))
    head = inputs.build(s)
    r = estimate_design(d, frame, validated=False)
    r["against_the_headline_design"] = fh.compare_to_headline(d, head, {tuple(k) for ks in admitted.values() for k in ks})
    return r


def _own_state(inputs, s, frame, entry):
    t, c = inputs.set_frames(s)
    d = sr.own_state(inputs.side, t, c, s[1])
    r = estimate_design(d, frame, validated=False, absorbed=oa.LEAVE_OUT_IF_EXACTLY_ABSORBED)
    r["controls_note"] = ("control columns left out only where the code confirms each is absorbed exactly, which leaves the "
                          "fit unchanged; the run carries no controls for that reason where they are left out (Other runs)")
    return r


def _threshold(inputs, s, frame, entry):
    t, c = inputs.set_frames(s)
    out = {}
    if s[1] == 0.05:
        main, left = sr.without_rappahannock(t)
        d = inputs.build(s, treated=main, clean=c)
        out = estimate_design(d, frame, validated=False)
        out["set_aside_before_matching"] = left
        if left:
            foot = inputs.build(s, treated=t, clean=c)
            out["footnote_with_rappahannock"] = estimate_design(foot, frame, validated=False)
        return out
    d = inputs.build(s, treated=t, clean=c)
    out = estimate_design(d, frame, validated=False)
    if s[1] == 0.01:
        out["label"] = sr.EXPLORATORY_1PCT
    return out


def _e1(inputs, s, frame, entry):
    t, c = inputs.set_frames(s)
    d = sr.e1(inputs.side, t, c, s[1])
    r = estimate_design(d, frame, validated=False)
    r["left_out_before_matching"] = d.left_out
    if inputs.side.dose is not None and len(d.hosts):
        r["hosts_by_window"] = sr.e1_report(d, inputs.side.dose, s[1])
    r["cohort_note"] = "the design's cohorts are the fake dates g - 6; the fake headline is calendar years g-4 and g-3"
    return r


E2_OWNERSHIP_RULE = ("applied: an investor-owned pseudo-host with a year of its fake window that no ownership row covers is "
                     "left out and named (Joe's ruling of 2026-11-19; future_hosts.e2_units with the ownership table)")


def _e2(inputs, s, frame, entry):
    """E2's pseudo-hosts are selected HERE by future_hosts.e2_units with the ownership table and the panel's classes, so
    the ruling of 2026-11-19 cannot be skipped by a caller passing units chosen without it (session 19). The table is
    required: without it e2_units silently applies no rule, so its absence stops the run in words."""
    hist = inputs.need("e2_histories", "the late hosts' histories (future_hosts.late_host_histories()[0])")
    aside = inputs.need("e2_aside", "the set-aside list E2 applies (a set; empty for none)")
    hold = inputs.need("e2_hold", "the price hold E2 applies (power_simulation.price_hold(); a set, empty for none)")
    late = inputs.need("e2_late", "every late host (future_hosts.late_host_histories)")
    own = inputs.need_side("ownership", "the ownership table (ownership.load()), which E2's ownership rule of 2026-11-19 needs")
    own_of = inputs.need_side("ownership_of", "the panel's ownership classes (power_simulation.ownership_classes(q))")
    i = inputs.side
    e2, left = fh.e2_units(hist, set(aside), set(hold), i.unknown_load, 0.02, ownership=own, ownership_of=own_of)
    extra = {"e2_units_left_out": left, "e2_ownership_rule": E2_OWNERSHIP_RULE}
    if not len(e2):
        return {"estimated": False, "validation": NOT_VALIDATED, **extra, "failure_in_words": "no E2 unit: not estimable"}
    _, main_clean = inputs.set_frames(H2)
    d = fh.e2_design(e2, main_clean, late, i.q, i.regions, i.fuel, i.dd, i.rules, **inputs.build_kw(0.02))
    r = estimate_design(d, frame, validated=False)
    r.update(extra)
    return r


def _e3(inputs, s, frame, entry):
    t, c = inputs.set_frames(s)
    d = sr.e3(inputs.side, t, c, s[1])
    r = estimate_design(d, frame, validated=False)
    r["left_out_before_matching"] = d.left_out
    r["label"] = "earlier-cohort sensitivity: the same as restricting the main estimate to cohorts 2011 to 2017"
    if not len(d.hosts):
        r["failure_in_words"] = "no retained host meets the support rule and the full-window rule: not estimable"
    return r


def _e5(inputs, s, frame, entry):
    """E5's states from side_runs.e5_states over the FULL state_anchor table (Joe's ruling of 2026-11-19), never from a
    list the caller types (session 19). The fallback states are flagged and named, not dropped."""
    a = inputs.need("e5_anchor", "E5's state_anchor inputs (E5Inputs: the report block and the full state_anchor table)")
    lists = sr.e5_states(a.block, a.all_states)
    states = {r["state"] for r in lists["dropped"]}
    d = sr.e5(inputs.build(s), states)
    r = estimate_design(d, frame, validated=False)
    r["states_dropped"] = sorted(states)
    r["states_flagged_not_dropped"] = [x["state"] for x in lists["flagged_not_dropped"]]
    r["states_built_from"] = lists["built_from"]
    return r


def _e6(inputs, s, frame, entry):
    ch = inputs.need("e6_changers", "E6's fixed list of comparison units that change region (side_runs.region_changers)")
    d = sr.e6(inputs.build(s), set(ch))
    return estimate_design(d, frame, validated=False)


# Condition 4's peak rows in the form conditions.read_peaks returns them, the form the session's one authorized read
# retains (Joe, 2026-11-20, D-120's addendum): utility_id_eia, state, year, peak_mw, short_form, data_observed.
PEAKS_AS_READ = ("utility_id_eia", "state", "year", "peak_mw", "short_form", "data_observed")


def peaks_as_read(frame) -> pd.DataFrame:
    """RunInputs.peaks for condition 4, in either form. A frame with a peak_mw column is taken to be in the form
    conditions.read_peaks returns, and is used as it is after a check, in words, that its columns are exactly
    PEAKS_AS_READ (each once, in any order; the agent's reading of "exactly"); any other column set refuses it. Any other
    frame is in conditions.PEAK_COLUMNS form and goes through conditions.read_peaks(frame) as before. Never called with
    None: the caller's RunInputs.need stops a missing input first, so conditions.read_peaks is never called without a
    source here."""
    if frame is None:
        raise MissingInput("the peak-demand rows were not supplied (RunInputs.peaks)")
    cols = [str(c) for c in getattr(frame, "columns", [])]
    if "peak_mw" in cols:
        if len(cols) != len(PEAKS_AS_READ) or set(cols) != set(PEAKS_AS_READ):
            raise ValueError(f"the peak-demand rows carry peak_mw, so they are taken to be in the form "
                             f"conditions.read_peaks returns, but their columns are {cols}, not exactly "
                             f"{list(PEAKS_AS_READ)}")
        return frame
    return cn.read_peaks(frame)


def _condition(which: str):
    def run_(inputs, s, frame, entry):
        d = inputs.build(s)
        hosts = cn.hosts_of(d)
        i = inputs.side
        y = oa.outcome_vector(d, frame, OUTCOME)
        out = {"validation": NO_RANGE_NO_VALIDATION, "label": DESCRIPTIVE_CONTRAST}
        if which == "load_share":
            groupings = [cn.load_share_grouping(hosts, i.dose)]
        elif which == "ownership":
            groupings = [cn.ownership_grouping(hosts, i.ownership_of)]
        elif which == "retail_choice":
            groupings = [cn.retail_choice_grouping(hosts, i.q, cn.HOST_OWN), cn.retail_choice_grouping(hosts, i.q, cn.STATE_ANY)]
        else:
            peaks = peaks_as_read(inputs.need("peaks", "the peak-demand rows (in conditions.PEAK_COLUMNS form, or in "
                                                       "PEAKS_AS_READ form, as conditions.read_peaks returns them)"))
            # The succession table is passed, never left to conditions to read from pipeline/electricity/succession.csv
            # (it reads that file when given None); res_customers feeds the customer-continuity footprint test.
            succession = inputs.need("succession", "the succession table (pipeline.electricity.succession.load())")
            groupings = [cn.past_utilization_grouping(hosts, peaks, inputs.has_predecessors,
                                                      i.q[KEY + ["year", "res_customers"]], succession=succession)]
        recs = [cn.contrast(d, y, g, names=inputs.names) for g in groupings]
        out["contrast"] = recs[0]
        if len(recs) > 1:
            out["beside_it_the_state_reading"] = recs[1]
        out["estimated"] = bool(recs[0]["estimable"])
        if not recs[0]["estimable"]:
            out["failure_in_words"] = f"not estimable: {recs[0]['not_estimable_because']}"
        return out
    return run_


def _sn_config(inputs) -> dict:
    """The second number's inputs. No seed is asked for: the bootstrap seed is second_number.BOOTSTRAP_SEED, adopted by Joe on 2026-11-19
    (D-107), applied by second_number.bootstrap_rng (_sn_rng)."""
    return inputs.need("second_number", "the second number's inputs (units, boot, assigned, changes, reach, no_assigned, "
                                        "established; the scenarios' units, points and units with no dose)")


def _sn_rng(cfg: dict) -> np.random.Generator:
    """second_number.bootstrap_rng: seed second_number.BOOTSTRAP_SEED when the config gives none; another seed only when the config says the
    inputs are invented, and refused in words otherwise (ValueError, recorded by run())."""
    return sn.bootstrap_rng(cfg.get("seed"), invented_inputs=bool(cfg.get("invented_inputs")))


def _sn_frame(inputs, cfg, post=sn.POST):
    i = inputs.side
    return sn.build_frame(cfg["units"], i.q, i.regions, i.usable, post=post)


def _sn_primary(post):
    def run_(inputs, s, frame, entry):
        cfg = _sn_config(inputs)
        rng = _sn_rng(cfg)
        f = _sn_frame(inputs, cfg, post)
        r = sn.run(f, sn.dose_points(inputs.side.dose), frame, rng, boot=cfg.get("boot", sn.BOOT), outcome_col=OUTCOME)
        r.update(estimated=bool(np.isfinite(r[sn.cap_label(sn.MAIN_CAP)].get("est", np.nan))), label=NOT_CALIBRATED,
                 inference=sn.INFERENCE_LABEL, left_out=f.left_out, after_period=list(post))
        return r
    return run_


SN_SINGLE_KEYS = ("assigned", "changes", "reach", "no_assigned", "established")


def _sn_single(name: str):
    """Rule 8.3's runs on single doses (second_number.RUN_SETTLED or RUN_LEAVE_TEN), each form with its own cap's classes
    (the adopted classification, second_number section 3a): the caller's assigned changes, within-history changes, reach
    and the utilities with no dose as assigned are restricted to the frame's utilities, classed by
    second_number.classify_by_cap with the common-dose finding `established` (required; {} retains the exclusion), checked
    one class each (check_one_class_each), the members taken per form from run_samples, and run_single_dose fitted on the
    caller's outcome."""
    def run_(inputs, s, frame, entry):
        cfg = _sn_config(inputs)
        rng = _sn_rng(cfg)
        if "established" not in cfg:
            raise MissingInput("the second number's common-dose mapping ('established': common_dose_rule."
                               "established_as_ruled, equivalently second_number.common_dose_finding()[0], per Joe's "
                               "ruling D-107) was not supplied; it is required, with no default ({} retains the exclusion "
                               "at every form)")
        for k in SN_SINGLE_KEYS:
            if cfg.get(k) is None:
                raise MissingInput(f"the second number's {k!r} (the adopted classification's inputs) was not supplied")
        f = _sn_frame(inputs, cfg)
        uids = {sn._uid(k) for k in f.keys}
        assigned = {lab: {u: v for u, v in a.items() if u in uids} for lab, a in cfg["assigned"].items()}
        changes = {lab: {u: v for u, v in c.items() if u in uids} for lab, c in cfg["changes"].items()}
        reach = {u: v for u, v in cfg["reach"].items() if u in uids}
        no_assigned = [u for u in cfg["no_assigned"] if u in uids]
        cl = sn.classify_by_cap(assigned, changes, reach, no_assigned, cfg["established"])
        counts = sn.check_one_class_each(cl, uids)
        samples = sn.run_samples(f, cl)
        members = {lab: samples[name][lab]["utilities"] for lab in samples[name]}
        r = sn.run_single_dose(members, f, cl, frame, rng, boot=cfg.get("boot", sn.BOOT), outcome_col=OUTCOME)
        main = sn.cap_label(sn.MAIN_CAP)
        supplied = {u: {lab: bool((e or {}).get("established")) for lab, e in forms.items()}
                    for u, forms in cfg["established"].items()}
        r.update(estimated=bool(np.isfinite(r[main].get("est", np.nan))), label=NOT_CALIBRATED,
                 inference=sn.INFERENCE_LABEL, class_counts=counts,
                 sample={lab: {k: v for k, v in samples[name][lab].items() if k != "utilities"} for lab in samples[name]},
                 common_dose_finding={
                     "supplied": bool(cfg["established"]),
                     "established_by_utility_and_form": supplied,
                     "note": ("the mapping applied is the ruled one (common_dose_rule.established_as_ruled; Joe, "
                              "2026-11-19, D-107: the exception is judged on the wider admissible histories, and Umatilla "
                              "stays outside it); the forms where it establishes a common change take it, and an empty "
                              "mapping retains the exclusion at every form"),
                     "settled_is_conditional": sn.SETTLED_IS_CONDITIONAL})
        return r
    return run_


def _sn_year_by_year(inputs, s, frame, entry):
    cfg = _sn_config(inputs)
    rng = _sn_rng(cfg)
    i = inputs.side
    pf_ = sn.panel_frame(cfg["units"], i.q, i.regions, i.usable)
    r = sn.run(pf_, sn.dose_points(i.dose), frame, rng, boot=cfg.get("boot", sn.BOOT), outcome_col=OUTCOME)
    r.update(estimated=bool(np.isfinite(r[sn.cap_label(sn.MAIN_CAP)].get("est", np.nan))), label=NOT_CALIBRATED,
             inference=sn.INFERENCE_LABEL, left_out=pf_.left_out)
    return r


def _sn_scenario(name: str):
    """One of the second number's two sensitivity scenarios (Joe, 2026-11-19, D-107; second_number_scenarios): the
    scenario's load shares in points (`scenario_points`[name], from points_of on realise_history, supplied by the caller;
    nothing is realised or read here), its sample through scenario_frame over `scenario_units` less `scenario_no_dose`
    [name], then run_scenario (second_number.run, the wild cluster bootstrap as built) with the bootstrap seed of
    _sn_rng. Labelled with second_number_scenarios.LABELS[name] and NOT_CALIBRATED: a sensitivity scenario, not a bound
    and not necessarily a one-change comparison with the primary analysis. Its sample's differences from the primary
    run's sample (second_number.build_frame over `units`) are reported, as Joe asked."""
    def run_(inputs, s, frame, entry):
        cfg = _sn_config(inputs)
        rng = _sn_rng(cfg)
        for k in ("scenario_units", "scenario_points", "scenario_no_dose"):
            if cfg.get(k) is None or (k != "scenario_units" and cfg[k].get(name) is None):
                raise MissingInput(f"the second number's {k!r} for {name} was not supplied (second_number_scenarios: "
                                   "realise_history, then points_of)")
        i = inputs.side
        points, no_dose = cfg["scenario_points"][name], cfg["scenario_no_dose"][name]
        f = ss.scenario_frame(points, cfg["scenario_units"], i.q, i.regions, i.usable, sn.region_codes(i.regions), no_dose)
        r = ss.run_scenario(f, points, frame, rng, boot=cfg.get("boot", sn.BOOT), outcome_col=OUTCOME)
        primary = {sn._uid(k) for k in _sn_frame(inputs, cfg).keys}
        mine = {sn._uid(k) for k in f.keys}
        r.update(estimated=bool(np.isfinite(r[sn.cap_label(sn.MAIN_CAP)].get("est", np.nan))), label=NOT_CALIBRATED,
                 scenario=name, scenario_label=ss.LABELS[name], inference=r.get("label") or sn.INFERENCE_LABEL,
                 left_out=f.left_out,
                 sample_differences_from_the_primary_run={
                     "utilities_in_the_scenario": len(mine), "utilities_in_the_primary_run": len(primary),
                     "in_the_scenario_only": sorted(mine - primary), "in_the_primary_run_only": sorted(primary - mine),
                     "units_with_load_and_no_positive_base_no_dose": sorted(sn._uid(k) for k in no_dose)})
        r["label"] = NOT_CALIBRATED
        return r
    return run_


# ---- R7's runs (Joe, 2026-11-19, D-107): influence deletions, the size-band side run, the timing run -------------------

INFLUENCE_LABELS = {"region": "influence deletion: each market region present left out; " + NOT_VALIDATED,
                    "state": "influence deletion: each state present left out (Virginia apart); " + NOT_VALIDATED,
                    "virginia": idl.run_label(idl.STATE, idl.VIRGINIA)}


def _influence(kind: str):
    """Reported checks, Influence, by deletion (influence_deletions, R7 adopted in D-107). kind "region": each market
    region present (influence_deletions.regions_present) left out; "state": each state present except Virginia;
    "virginia": Virginia alone, with the module's sentence (no host and no matched unit of the design in Virginia,
    checked on the design, and an unchanged estimate not presented as a check passed). One registry entry per plan item,
    each through influence_deletions.estimate_deletion (rule 7's treatment and the rank test before any fit, then the
    kernel with validated_design=False); the region and state entries carry influence_deletions.summarise (the range
    across deletions and the deletion that moves it most). The full design's estimate beside them is fitted with
    validated_design=False: the validated headline is main_headline_set's own entry."""
    def run_(inputs, s, frame, entry):
        d = inputs.build(s)
        if kind == "virginia":
            todo = [(idl.STATE, idl.VIRGINIA)]
        elif kind == "region":
            todo = [(idl.REGION, r) for r in idl.regions_present(d)]
        else:
            todo = [(idl.STATE, x) for x in idl.states_present(d) if x != idl.VIRGINIA]
        full = oa.estimate(d, oa.outcome_vector(d, frame, OUTCOME), validated_design=False)
        runs = [idl.estimate_deletion(d, k, v, frame, OUTCOME, names=inputs.names) for k, v in todo]
        out = {"validation": NOT_VALIDATED, "label": INFLUENCE_LABELS[kind],
               "full_design": full, "deletions": runs, "design": design_facts(d),
               "deletions_not_estimated": [{"deletion": f"{x['kind']} {x['value']}", "failure_in_words": x["failure_in_words"]}
                                           for x in runs if not x["estimated"]],
               "estimated": bool(runs) and all(x["estimated"] for x in runs),
               "zero_note": idl.SPANS_ZERO}
        if kind == "virginia":
            (va,) = runs
            out["virginia"] = va["virginia"]
            if va["result"] is not None:
                h = va["result"]["headline"]
                out.update(estimate_log_points=h["log_points"], range_90_log_points=h["range_90_log_points"])
        else:
            out["summary"] = idl.summarise(full, runs)
        if not runs:
            out["failure_in_words"] = f"no {kind} is present in the design, so there is nothing to leave out"
        elif not out["estimated"]:
            out["failure_in_words"] = "; ".join(f"{x['deletion']}: {x['failure_in_words']}" for x in out["deletions_not_estimated"])
        return out
    return run_


def _kernel_summary(r: dict) -> dict:
    """The headline numbers of a module result whose kernel result sits under 'result'."""
    k = r.get("result")
    if not k:
        return {}
    h = k["headline"]
    return {"estimate_log_points": h["log_points"], "range_90_log_points": h["range_90_log_points"],
            "numerical_failure_in_words": failure_in_words(k), "count_N": k.get("count_N")}


def _size_band(inputs, s, frame, entry):
    """The size-band form as a side run (size_band_run, R7 adopted in D-107): cells of reference-year region by size band,
    every eligible unit of the host's cell its comparisons, the support rule's first limb as written; the rank test
    before any fit, then the kernel with validated_design=False; refuses a set in which hosts share a cohort and a cell
    (D-111)."""
    t, c = inputs.set_frames(s)
    i = inputs.side
    d = sbr.build(t, c, i.q, i.regions, i.fuel, i.dd, ownership=i.ownership, usable=i.usable, gas=i.gas,
                  ownership_of=i.ownership_of, unknown_load=i.unknown_load, theta=s[1])
    r = sbr.estimate_size_band(d, frame, OUTCOME)
    r.update(validation=NOT_VALIDATED, design=design_facts(d), cells=getattr(d, "cells", None), **_kernel_summary(r))
    return r


def _timing(inputs, s, frame, entry):
    """The timing run (timing_run, R7 adopted in D-107): the headline set with the two hosts added at their no-anchoring
    years (RunInputs.timing_added, required), each matched at its own reference year under every existing rule, the
    other hosts' matches unchanged (checked; a change stops it in words); the rank test before any fit, then the kernel
    with validated_design=False."""
    added = inputs.need("timing_added", "the timing run's added hosts at their no-anchoring years (timing_run."
                                        "no_anchoring_years(...)['years'])")
    t, c = inputs.set_frames(s)
    i = inputs.side
    d, record = tr.build(t, c, added, i.q, i.regions, i.fuel, i.dd, ownership=i.ownership, usable=i.usable, gas=i.gas,
                         ownership_of=i.ownership_of, unknown_load=i.unknown_load, theta=s[1], names=inputs.names)
    r = tr.estimate_timing_run(d, record, frame, OUTCOME)
    r.update(validation=NOT_VALIDATED, design=design_facts(d), **_kernel_summary(r))
    return r


# ---- the five-highest-load deletion and the customer-weighted fit (Joe's rulings of 2026-11-19, D-105) -----------------

def _five_highest_load(inputs, s, frame, entry):
    """Reported checks, Influence: the five hosts with the highest data center load (GWh, side.dose's dc_gwh) in their own
    event year 3 dropped with their sub-experiments (influence_load). The ranking, the gaps and any exact tie are
    reported whatever happens; an exact tie at the line between rank 5 and rank 6, a host with no load in its event year
    3, or five or fewer hosts stop the run in words. The rank test is made before any fit; the deleted design keeps its
    rules (carry_design_attributes) and is estimated with validated_design=False. The full design's estimate is beside it
    with the move, and a deletion whose range includes zero is reported as that, not as a reversal."""
    d = inputs.build(s)
    load = inputs.need_side("dose", "the load frame (utility_year_dose: utility_id_eia, state, year, dc_gwh)")
    full = estimate_design(d, frame, validated=False)
    r = il.estimate_without_the_five(d, load, frame, OUTCOME, names=inputs.names)
    out = {"validation": NOT_VALIDATED, "ranking": r["ranking"], "rank_test_before_any_fit": r["rank_test_before_any_fit"],
           "full_design_estimate_log_points": full["headline"]["log_points"], "deletion": r["result"],
           "estimated": bool(r["estimated"]),
           "zero_note": "a deletion that makes the range include zero is reported as that, not as a reversal (Influence)"}
    k = r["result"]
    if k is not None:
        h = k["headline"]
        lo_hi = h["range_90_log_points"]
        out.update(estimate_log_points=h["log_points"], range_90_log_points=lo_hi, status=h["status"],
                   validation=k["validation"], numerical_failure_in_words=failure_in_words(k),
                   moves_by_log_points=h["log_points"] - full["headline"]["log_points"],
                   range_includes_zero=None if lo_hi is None else bool(lo_hi[0] <= 0 <= lo_hi[1]))
    if r["failure_in_words"]:
        out["failure_in_words"] = r["failure_in_words"]
    return out


def _customer_weighted(inputs, s, frame, entry):
    """Weights: the same estimate weighted by each host's residential customers in its reference year (weighted_fit), a
    point estimate labelled descriptive with no range. The customers are side.q's res_customers for the host's own unit in
    cohort - 3; a host without one stops in words (CustomerWeightMissing, recorded by run()). The nominal customer weight
    shares and the effective contributions to the weighted headline are returned under their own names."""
    d = inputs.build(s)
    q = inputs.need_side("q", "the quantities frame with res_customers")
    w = wf.customer_weights(d, q)
    r = wf.weighted_fit(d, oa.outcome_vector(d, frame, OUTCOME), w)
    r["design"] = design_facts(d)
    return r


# ---- the reconciliation rows, the inventory check, Callaway and Sant'Anna, and the side-by-side table ------------------

def _words_or(exc) -> str:
    return _words(exc) if isinstance(exc, BaseException) else str(exc)


def _missing_frame(name: str) -> str:
    return f"no outcome frame was supplied for {name!r} ({OUTCOME_IN_WORDS.get(name, name)})"


def _row_mu(row: str):
    """Rows M and U, step by step in the plan's order. A step whose treatment or price frame is missing, or that fails,
    is recorded in words and the others still run. Row M's runner, _row_mu("M"), is dormant (Joe, 2026-11-19, D-109): it
    is kept as ROW_M_DORMANT_RUNNER, reached by no registry entry, and its describe_row_m and reconciliation_mu's row M
    verdict logic are not applied in this freeze."""
    steps = rmu.M_STEPS if row == "M" else rmu.U_STEPS
    attr, what = (("reconciliation_m", "row M's inputs (RowMInputs: MeeksSpec, the treatments for M0 to M4, ownership, "
                                       "sample flags)") if row == "M" else
                  ("reconciliation_u", "row U's inputs (RowUInputs: ryu_spec, the treatments for U0 to U3, ownership, "
                                       "sample flags, the U1 argument)"))

    def run_(inputs, s, frames, entry):
        b = inputs.need(attr, what)
        out, done = [], []
        for step, st in steps.items():
            tr, f = b.treatments.get(step), frames.get(st["price"])
            if tr is None:
                why = f"no treatment for {step} was supplied ({attr}.treatments[{step!r}]; {st['change']})"
            elif f is None:
                why = _missing_frame(st["price"])
            else:
                why = None
            if why:
                out.append({"row": row, "step": step, "computed": False, "failure_in_words": why})
                continue
            try:
                if row == "M":
                    r = rmu.run_m_step(step, f, st["price"], tr, b.ownership, b.spec, customers=b.customers,
                                       sample_flags=b.sample_flags)
                else:
                    r = rmu.run_u_step(step, f, st["price"], tr, b.ownership, b.spec, sample_flags=b.sample_flags)
                    if step == "U1":
                        r["u1_sentence"] = rmu.u1_sentence(r, b.u1_indistinguishable)
            except Exception as exc:                            # noqa: BLE001  recorded in words, never dropped
                out.append({"row": row, "step": step, "computed": False, "failure_in_words": _words(exc)})
                continue
            r["computed"] = r["pooled"]["estimate"] is not None
            out.append(r)
            if r["computed"]:
                done.append(r)
        res = {"estimated": bool(done), "validation": OTHER_ESTIMATOR, "label": RECONCILIATION, "steps": out,
               "steps_not_computed": [x["step"] for x in out if not x["computed"]]}
        if row == "M":
            res["movement"] = rmu.describe_row_m(done)
        if not done:
            res["failure_in_words"] = "; ".join(f"{x['step']}: {x.get('failure_in_words') or 'no estimate'}" for x in out)
        return res
    return run_


class RowUInputsRefused(PermissionError):
    """Row U's inputs are refused before any step runs: what they are is not one of INPUTS_ARE, or, on research data
    after the freeze, the gate file or the run's authorization is missing, or the specification is not the adopted one.
    Raised in words; run() records it as the entry's failure and no step is run."""


def _row_u_guard(inputs: RunInputs) -> dict:
    """The guard on row U (session 27, closing the gap reported with D-119: reconciliation_mu.RyuSpec accepts three
    Short Form codes and the runner refused none). RunInputs.reconciliation_u_inputs_are is required: None stops the row
    in words (MissingInput) and no value is chosen for the caller; a value outside INPUTS_ARE is refused in words.
    INVENTED_INPUTS: the row runs as before, with any of reconciliation_mu.SHORT_FORM_RULES (tests on invented inputs use
    the two codes other than the adopted one). RESEARCH_DATA_AFTER_THE_FREEZE: refused in words unless the gate file
    (panel.GATE_FILE, looked up when called) exists and AUTH_ENV is "1", in that order, as inventory_against_sales._gate
    has them; refused in words, naming the code passed, the adopted code and D-115, when the specification's
    short_form_exclusion is not reconciliation_mu.U_SHORT_FORM_ADOPTED_CODE; and refused in words when the specification
    is not equal to reconciliation_mu.ryu_spec(reconciliation_mu.U_SHORT_FORM_ADOPTED_CODE), every other field being fixed
    by D-107 (this last refusal is the session's reading of the fixed specification). Returns what was checked, in
    words; reads no outcome."""
    are = inputs.need("reconciliation_u_inputs_are", "what row U's inputs are (INVENTED_INPUTS for invented inputs, or "
                                                     "RESEARCH_DATA_AFTER_THE_FREEZE); no value is chosen for the caller")
    if are not in INPUTS_ARE:
        raise RowUInputsRefused(f"reconciliation_u_inputs_are is {are!r}; it must be {INVENTED_INPUTS!r} or "
                                f"{RESEARCH_DATA_AFTER_THE_FREEZE!r}, and no value is chosen for the caller")
    if are == INVENTED_INPUTS:
        return {"inputs_are": are, "short_form_rule_checked": False,
                "why": "invented inputs: any of reconciliation_mu.SHORT_FORM_RULES is accepted for tests"}
    gate = Path(panel.GATE_FILE)
    if not gate.exists():
        raise RowUInputsRefused(f"row U is not run on research data: the gate file {gate.name} does not exist (it is "
                                "created only on Joe's separate authorization to access outcomes)")
    if os.environ.get(AUTH_ENV) != "1":
        raise RowUInputsRefused(f"row U is not run on research data: the environment variable {AUTH_ENV} is not set to 1 "
                                "(no authorization for this run)")
    b = inputs.need("reconciliation_u", "row U's inputs (RowUInputs: ryu_spec, the treatments for U0 to U3, ownership, "
                                        "sample flags, the U1 argument)")
    code = getattr(b.spec, "short_form_exclusion", None)
    if code != rmu.U_SHORT_FORM_ADOPTED_CODE:
        raise RowUInputsRefused(f"row U is not run on research data with the Short Form rule {code!r}: the rule Joe "
                                f"adopted on 2026-11-20 (D-115) is {rmu.U_SHORT_FORM_ADOPTED_CODE!r}, and no other code is "
                                "accepted for research execution")
    adopted = rmu.ryu_spec(rmu.U_SHORT_FORM_ADOPTED_CODE)
    if b.spec != adopted:
        names = sorted(f.name for f in dataclasses.fields(adopted)
                       if getattr(b.spec, f.name, None) != getattr(adopted, f.name))
        raise RowUInputsRefused("row U is not run on research data: its specification is not reconciliation_mu.ryu_spec("
                                "reconciliation_mu.U_SHORT_FORM_ADOPTED_CODE), whose fields other than the Short Form rule "
                                "are fixed (D-107); the fields that differ: " + (", ".join(names) or "none by value, but "
                                f"the object is a {type(b.spec).__name__}") + " (refusing any departure is the session's "
                                "reading of the fixed specification)")
    return {"inputs_are": are, "short_form_rule_checked": True, "short_form_exclusion": code,
            "specification": "reconciliation_mu.ryu_spec(reconciliation_mu.U_SHORT_FORM_ADOPTED_CODE)"}


def _row_u_guarded(inner):
    """Row U's runner: _row_u_guard, then the steps of _row_mu("U") unchanged. A refusal is raised before any step, so
    run() records it as the entry's failure in words with no step run. Row M's dormant runner is not wrapped."""
    def run_(inputs, s, frames, entry):
        checked = _row_u_guard(inputs)
        res = inner(inputs, s, frames, entry)
        res["inputs_checked"] = checked
        return res
    return run_


def _row_c(inputs, s, frames, entry):
    frame = frames.get(PRICE_CENTS_REAL_2024)
    if frame is None:
        raise MissingInput(_missing_frame(PRICE_CENTS_REAL_2024))
    b = inputs.need("reconciliation_c", "row C's inputs (RowCInputs: Choices, the counts, load share, fiber share, spending "
                                        "tables, ownership, C4's cap, C5's hosts)")
    r = rc.run_row_c(frame, b.counts_polygon, b.counts_verified, b.dose_verified, b.share, b.spending_tables, b.choices,
                     b.ownership, b.c4_cap, b.hosts_for_c5, b.c5_counts_name)
    computed = [x for x in r["steps"] if isinstance(x.get("estimate"), float) and np.isfinite(x["estimate"])]
    r.update(estimated=bool(computed), validation=OTHER_ESTIMATOR, label=RECONCILIATION,
             steps_with_a_failure=[{"step": x.get("step"), "failure_in_words": x.get("failure")} for x in r["steps"]
                                   if x.get("failure")])
    if not computed:
        r["failure_in_words"] = "no step of row C computed: " + "; ".join(str(x["failure_in_words"]) for x in r["steps_with_a_failure"])
    return r


class InventoryNotAsBuilt(ValueError):
    """The frame the inventory check would be given is not shown to be the inventory as built, the frame the headline
    design's sets were split from (D-119). Raised in words before the check computes anything; run() records it."""


def _hosts_with_cohort(t: pd.DataFrame) -> set:
    return {(int(u), str(st), int(g)) for u, st, g in zip(t.utility_id_eia, t.state, t.cohort)}


def _unit_keys(c: pd.DataFrame) -> set:
    return {(int(u), str(st)) for u, st in zip(c.utility_id_eia, c.state)}


def _same_inventory_as_built(inputs: RunInputs, s: tuple, are) -> dict:
    """That the inventory check and the headline design use the same inventory as built (session 27, closing the gap
    reported with D-119). Identity is established two ways: equal content by hash (frame_fingerprint(side.dose) equals
    RunInputs.inventory_as_built.dose_fingerprint, the stamp taken when the sets were split), and the headline set
    reproduced from the frame (the split function on (theta, which, side.q, side.dose) gives exactly the hosts with
    their cohorts and exactly the comparison-eligible units that RunInputs.sets holds for the entry's set, compared as
    sets of keys).

    RESEARCH_DATA_AFTER_THE_FREEZE: the stamp is required, its split must be None, and the split is design.split (looked
    up when called); a substituted split is refused. INVENTED_INPUTS: with a stamp the same checks run, with the stamp's
    split when it is not None (tests supply an invented one); with no stamp nothing is checked and the check runs as
    before. Any other value is left to inventory_against_sales' own guard, which refuses it. A mismatch is refused in
    words (InventoryNotAsBuilt) with counts, never a list of utilities' data. Returns what was checked."""
    stamp = inputs.inventory_as_built
    if are == RESEARCH_DATA_AFTER_THE_FREEZE:
        if stamp is None:
            raise InventoryNotAsBuilt("the inventory check is not run on research data without RunInputs.inventory_as_built: "
                                      "the stamp of the dose frame the sets were split from is required, so that the "
                                      "check is shown to be given the inventory as built (D-119)")
        if not isinstance(stamp, InventoryAsBuilt):
            raise InventoryNotAsBuilt(f"RunInputs.inventory_as_built is a {type(stamp).__name__}, not an InventoryAsBuilt")
        if stamp.split is not None:
            raise InventoryNotAsBuilt("a substituted split function is refused on research data: the headline set is "
                                      "split again with design.split")
        split, split_name = dsg.split, "design.split"
    elif are == INVENTED_INPUTS:
        if stamp is None:
            return {"checked": False, "why": "invented inputs with no RunInputs.inventory_as_built: nothing to check"}
        if not isinstance(stamp, InventoryAsBuilt):
            raise InventoryNotAsBuilt(f"RunInputs.inventory_as_built is a {type(stamp).__name__}, not an InventoryAsBuilt")
        split = dsg.split if stamp.split is None else stamp.split
        split_name = ("design.split" if stamp.split is None else
                      f"{getattr(split, '__module__', '?')}.{getattr(split, '__qualname__', type(split).__name__)}")
    else:
        return {"checked": False, "why": f"inputs_are {are!r} is left to inventory_against_sales' own guard"}
    dose = inputs.need_side("dose", "the inventory's dose frame (side.dose)")
    got = frame_fingerprint(dose)
    if got != stamp.dose_fingerprint:
        raise InventoryNotAsBuilt("the frame the check would be given (RunInputs.side.dose) is not the frame the sets were "
                                  "split from: its fingerprint differs from RunInputs.inventory_as_built.dose_fingerprint "
                                  f"(stamp source: {stamp.source})")
    treated, clean = inputs.set_frames(s)
    t2, c2 = split(s[1], s[0], inputs.side.q, dose)
    h_sup, h_new, c_sup, c_new = _hosts_with_cohort(treated), _hosts_with_cohort(t2), _unit_keys(clean), _unit_keys(c2)
    if h_sup != h_new or c_sup != c_new:
        raise InventoryNotAsBuilt(
            f"the set {set_label(s)} split again from RunInputs.side.dose with {split_name} is not the set supplied in "
            f"RunInputs.sets: {len(h_sup - h_new)} host-and-cohort pairs supplied and not reproduced, {len(h_new - h_sup)} "
            f"reproduced and not supplied; {len(c_sup - c_new)} comparison-eligible units supplied and not reproduced, "
            f"{len(c_new - c_sup)} reproduced and not supplied")
    return {"checked": True, "dose_fingerprint": got, "stamp_source": stamp.source, "split": split_name,
            "hosts_with_cohort_reproduced": len(h_new), "comparison_eligible_units_reproduced": len(c_new)}


def _inventory_against_sales(inputs, s, frame, entry):
    """Quantities only: the hosts and their matches from the design, non-residential sales from side.q and the inventory's
    load from side.dose, the inventory as built, the load history underlying the headline design (Joe, 2026-11-20,
    D-119; inventory_against_sales.INVENTORY_HISTORY_D119). `frame` is not used (the entry's outcome is None) and no outcome is read. The four elements are
    the module's adopted settings (D-107); RunInputs.inventory_inputs_are is required and passed to the module's guard,
    which refuses research data unless the gate file exists and the run is authorized.

    Before the check computes anything, _same_inventory_as_built establishes that side.dose is the inventory as built in
    two ways: equal content by hash against RunInputs.inventory_as_built, and the headline set reproduced from the frame.
    On research data the stamp is required and design.split is the split (session 27). The module's guard
    (inventory_against_sales._gate) is called first, as it stands, and again inside the check."""
    are = inputs.need("inventory_inputs_are", "what the check's frames are (inventory_against_sales.INVENTED_INPUTS, or "
                                              "RESEARCH_DATA_AFTER_THE_FREEZE, which its guard refuses unless the gate file "
                                              "exists and the run is authorized)")
    readings = ias.ADOPTED if inputs.inventory_readings is None else inputs.inventory_readings
    # The module's own guard first, unchanged, so research data without the gate file and the authorization is refused
    # in its words before anything is split or compared (the agent's reading of the order); ias.check calls it again.
    ias._gate(are)
    as_built = _same_inventory_as_built(inputs, s, are)
    d = inputs.build(s)
    r = ias.check(ias.hosts_from_design(d), inputs.side.q, inputs.side.dose, readings, inputs_are=are)
    r.update(estimated=r["slope"].get("slope") is not None, validation=QUANTITIES_ONLY, design=design_facts(d),
             inventory_as_built_check=as_built)
    if not r["estimated"]:
        r["failure_in_words"] = r.get("reading_failure") or "the slope could not be computed"
    return r


CS_ONLY_IN_VENV = ("diff-diff 4.0.0 is installed only in the gizmo folder's .venv (run with .venv/bin/python -I); this "
                   "interpreter does not have it, so the run is not made and nothing is substituted")


def _callaway_santanna(inputs, s, frame, entry):
    """callaway_santanna.sample, frame and run (the pinned call on diff-diff 4.0.0) on the caller's price outcome. Where the
    package is not importable here, a failure in words; no fallback, no crash."""
    try:
        csa._import_pinned()
    except (csa.PackageMissing, csa.PackageVersionRefused) as exc:
        return {"estimated": False, "validation": OTHER_ESTIMATOR, "label": CS_RANGE_LABEL,
                "failure_in_words": f"{_words(exc)} {CS_ONLY_IN_VENV} (interpreter: {sys.executable})"}
    b = inputs.need("cs_sample", "the Callaway and Sant'Anna sample's lists (CSSampleInputs)")
    i = inputs.side
    dd_states = {str(x) for x in i.dd.index.get_level_values(0)}
    smp = csa.sample(s[1], s[0], i.q, i.dose, host_aside=set(b.host_aside), comparison_aside=set(b.comparison_aside),
                     hold=set(b.hold), unknown_load=i.unknown_load, ownership=i.ownership, ownership_of=i.ownership_of,
                     usable=i.usable, gas=i.gas, dd_states=dd_states, history=b.history)
    f = csa.frame(smp, i.regions, i.gas, frame.rename(columns={OUTCOME: "outcome"}), i.usable)
    r = csa.run(f)
    r.update(estimated=r["headline"] is not None, validation=OTHER_ESTIMATOR, label=CS_RANGE_LABEL,
             sample={"hosts": int(len(smp.hosts)), "never_treated": int(len(smp.never_treated)),
                     "steps": [{k: x[k] for k in ("step", "removed", "remaining")} for x in smp.steps],
                     "hosts_dropped": smp.hosts_dropped}, frame_report=f.report)
    if r["numerical_failure"]:
        r["numerical_failure_in_words"] = r["numerical_failure"]
    return r


SIDE_BY_SIDE_RUNS = (("main_headline_set", H2), ("main_ten_year_set", (TEN_YEAR_SET, 0.02)),
                     ("main_plus_unsettled", (PLUS_UNSETTLED, 0.02)), ("main_every_cohort_utility", E2_))


def _estimators_agree(inputs, s, frame, entry):
    """The side-by-side table (estimators_table.table) from the four stacked main estimates and Callaway and Sant'Anna on
    the headline set, each computed here by its own entry's runner on the same outcome. A run that fails, Callaway and
    Sant'Anna where the package is missing included, is a row failed in words and the table still assembles."""
    rows, parts = [], {}
    for eid, ss in SIDE_BY_SIDE_RUNS:
        name = f"stacked: {set_label(ss)}"
        try:
            r = REGISTRY_BY_ID[eid].runner(inputs, ss, frame, REGISTRY_BY_ID[eid])
            rows.append(et.from_stacked_result(name, ss[0], ss[1], r))
            parts[name] = r.get("validation_check")
        except Exception as exc:                                    # noqa: BLE001  a failed row, in words
            rows.append(et.row_input(name, et.STACKED, ss[0], ss[1], status=et.FAILED, estimate=None, range_low=None,
                                     range_high=None, units="log_points", label=None, failure_in_words=_words(exc),
                                     validated=False))
    name = f"Callaway and Sant'Anna: {set_label(H2)}"
    try:
        c = _callaway_santanna(inputs, H2, frame, REGISTRY_BY_ID["callaway_santanna"])
        rows.append(et.from_callaway_santanna_result(name, H2[0], H2[1], c) if c.get("estimated") else
                    et.row_input(name, et.CALLAWAY_SANTANNA, H2[0], H2[1], status=et.FAILED, estimate=None, range_low=None,
                                 range_high=None, units="log_points", label=c.get("label"),
                                 failure_in_words=c.get("failure_in_words") or c.get("numerical_failure") or "not computed",
                                 validated=False))
    except Exception as exc:                                        # noqa: BLE001
        rows.append(et.row_input(name, et.CALLAWAY_SANTANNA, H2[0], H2[1], status=et.FAILED, estimate=None, range_low=None,
                                 range_high=None, units="log_points", label=None, failure_in_words=_words(exc),
                                 validated=False))
    t = et.table(rows)
    return {"estimated": any(r["status"] == et.ESTIMATED for r in t["rows"]), "validation": OTHER_ESTIMATOR,
            "label": "side by side: " + et.NEED_NOT_AGREE, "table": t, "stacked_validation_checks": parts}


# ======================================================================================================================
# The registry, in the plan's order of unblinding
# ======================================================================================================================

@dataclass(frozen=True)
class Entry:
    id: str
    section: str
    sets: tuple
    builder: str
    estimator: str
    labels: tuple
    status: str
    reason: str = ""
    outcome: str | None = PRICE
    runner: object = field(default=None, compare=False, repr=False)
    outcomes: tuple = ()          # several named price frames (the reconciliation rows); the runner gets {name: frame}
    needs: str = ""               # what the caller must still supply before the run can be made on research data
    stopped_on_research_inputs: str = ""    # a built entry with a step STOPPED on the real quantity files, in words
    context: str = ""             # a paper's published numbers, attributed, reported as context and never as a test

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"{self.id}: unknown status {self.status!r}")
        if (self.status == BUILT) != (self.runner is not None):
            raise ValueError(f"{self.id}: a built entry has a runner and no other entry does")
        if self.status != BUILT and not self.reason:
            raise ValueError(f"{self.id}: an entry that is not built says why")
        if self.outcome is not None and self.outcome not in OUTCOMES:
            raise ValueError(f"{self.id}: unknown outcome {self.outcome!r}")
        if any(o not in OUTCOMES for o in self.outcomes):
            raise ValueError(f"{self.id}: unknown outcomes {self.outcomes!r}")
        if self.outcomes and self.outcome is not None:
            raise ValueError(f"{self.id}: an entry takes one outcome or several named ones, not both")
        if self.stopped_on_research_inputs and self.status != BUILT:
            raise ValueError(f"{self.id}: only a built entry carries stopped steps; an entry that is not built says why")
        if self.status == OUT_OF_SCOPE and (self.outcome is not None or self.outcomes or self.needs):
            raise ValueError(f"{self.id}: an entry out of scope for this freeze reads no outcome and lists no needs")

    def outcome_names(self) -> list:
        return list(self.outcomes) if self.outcomes else ([] if self.outcome is None else [self.outcome])

    def as_record(self) -> dict:
        return {"id": self.id, "plan_section": self.section, "sets": [set_label(s) for s in self.sets],
                "builder": self.builder, "estimator": self.estimator, "labels": list(self.labels),
                "status": self.status, "reason": self.reason or None,
                "outcome": self.outcome if not self.outcomes else list(self.outcomes),
                "reads_an_outcome": bool(self.outcome_names()),
                "needs_before_research_data": self.needs or None,
                "stopped_on_research_inputs": self.stopped_on_research_inputs or None,
                "context_reported_as_the_papers": self.context or None}


K = "outcome_analysis.estimate (CR2, Satterthwaite), outcome aligned by outcome_analysis.outcome_vector"
BW = "design.build_with_rules under the headline rules"
NV = (NOT_VALIDATED,)
REG = "Reconciliation rows (reported first, whatever they show)"
OTHER = "Other runs, listed in advance"
FR = "Other outcomes and robustness: falsification and robustness"
COND = "Conditions tested (four)"
RC = "Reported checks"
SN = "The second number: per point of load"
# What each built entry still needs from the caller before it can run on research data (Entry.needs). Row M's open
# elements (NEEDS_M, dormant and carried by no entry) are named as the modules name them; none has a default anywhere.
NEEDS_M = ("RunInputs.reconciliation_m (RowMInputs). MeeksSpec's settled fields must carry the paper's values (file dated "
           "2026-10-23): jurisdictions CONTIGUOUS_48 or CONTIGUOUS_48_AND_DC (whether DC is in is open), customer_floor "
           "None, exclude_short_form True, require_three_classes True. Its open elements: covariates, aggregation, "
           "se_method (bootstrap_draws, bootstrap_weights and seed if the multiplier bootstrap), anticipation, unbalanced, "
           "treated_after_window, short_form_years, three_classes_level, three_classes_test, retail_component, "
           "window_start_cohort, weighting. sample_flags is required: KEY, ever_short_form, short_form_first_year_read, "
           "short_form_last_year_read, has_three_classes, three_classes_test (plus year if three_classes_level is "
           "'unit_year', has_retail_component if retail_component is 'flag'), built from EIA-861 inputs under data/raw "
           "that are not read yet and not authorized. A first-year treatment for each of M0 to M4 "
           "(reconciliation_treatment: size_column and counting are open; how the 5 MW is counted, by site or by a "
           "county-year sum, is with Joe; M0 needs the county-touch assignment, which needs the EIA-861 service-territory "
           "table, a site-to-county table and territory_vintage, none read and none authorized; treatments must carry "
           "pre-2010 activations). The ownership classes (reconciliation_mu.ownership_classes; pick is open). customers is "
           "not used by row M. Outcome frames res_price_default_service and res_price (price levels).")
# Row M's entry text (Joe, 2026-11-19, D-109). NEEDS_M above is kept as it was, with the dormant code; no entry carries it.
OUT_OF_SCOPE_M = ("Out of scope for this freeze by Joe's ruling of 2026-11-19 (D-109). M0 to M4 are not run. The reasons, "
                  "as they are: the row's sample flags and M0's assignment need inputs that are not read and not "
                  "authorized (EIA-861 inputs under data/raw, the service-territory table, a site-to-county table and "
                  "county boundaries); several elements of the paper's specification would be approximations of ours that "
                  "Joe has not adopted; and he decided not to adopt them, not to read the additional tables and not to "
                  "fetch county boundaries for this freeze. The row's code and tests are kept as they are and are dormant "
                  "(run_outcomes._row_mu('M') as ROW_M_DORMANT_RUNNER, RowMInputs and NEEDS_M, and reconciliation_mu's "
                  "row M parts); its verdict logic is dormant and not applied in this freeze, and no row M result "
                  "supports a reproduction verdict. The paper's published numbers are reported as the paper's, as "
                  "context, and nothing of ours is set beside them as a test. A utility or county with no territory row, "
                  "no assigned site or no polygon is never described as untreated or as evidence of no treatment. Row M "
                  "is in no executable order of unblinding and in no built count, and run() refuses it in words.")
CONTEXT_M = ("The paper's published residential estimates, reported as the paper's and as context, with nothing of ours "
             "set beside them as a test (" + rmu.MEEKS_FILE + "; pooled, Table 2 col. 2, p. 47; investor-owned, public "
             "and cooperative, Table 3 Panels A to C col. 2, p. 48; standard errors in parentheses): "
             + ", ".join(f"{k.replace('_', '-')} {v[0]:.3f} ({v[1]:.3f})" for k, v in rmu.PAPER_M.items()) + ".")
# Ownership for rows U and C (Joe, 2026-11-20, D-117, and D-119 on what the type is; the specification is held in
# reconciliation_mu). The sentence on the panel's entity_type column carries the substance of
# reconciliation_mu.PANEL_ENTITY_TYPE_STATEMENT and names it.
OWNERSHIP_YEARS_TEXT = f"{rmu.OWNERSHIP_YEARS_SEARCHED[0]} to {rmu.OWNERSHIP_YEARS_SEARCHED[-1]}"
OWNERSHIP_PANEL_TEXT = ("The panel's entity_type is one type per utility id, the type its own filings report most often, "
                        "so on this panel the reading over the years searched changes no class. Joe ruled on 2026-11-20 "
                        "(D-119) that rows U and C keep this type, described as the utility-level modal reported type "
                        "carried across the panel and not the latest year-by-year EIA classification, with no further "
                        "raw-data investigation (his words are reconciliation_mu.OWNERSHIP_RULING_D119_WORDS); no claim "
                        "is made that it equals EIA's year-by-year record (reconciliation_mu.PANEL_ENTITY_TYPE_STATEMENT).")
OWNERSHIP_U_TEXT = ("The ownership classes are reconciliation_mu.adopted_row_u_ownership_classes(q), on quantities that "
                    f"cover {OWNERSHIP_YEARS_TEXT} (a subset of years is refused in words). Each utility-state's class "
                    f"comes from {rmu.OWNERSHIP_PICK_D117}; the years searched are the quantity panel's "
                    f"{OWNERSHIP_YEARS_TEXT}, and the class is time-invariant, mapped by reconciliation_mu.U_MAP "
                    "unchanged, " + rmu.OWNERSHIP_SETTLED_D117 +
                    " (reconciliation_mu.OWNERSHIP_SPECIFICATION_D117). " + rmu.OWNERSHIP_MISSING_TREATMENT + " "
                    + OWNERSHIP_PANEL_TEXT)
OWNERSHIP_C_TEXT = ("The ownership classes are reconciliation_c.adopted_row_c_ownership(q), on quantities that cover "
                    f"{OWNERSHIP_YEARS_TEXT} (a subset of years is refused in words). Each utility-state's class comes "
                    f"from {rmu.OWNERSHIP_PICK_D117}; the years searched are the quantity panel's "
                    f"{OWNERSHIP_YEARS_TEXT}, and the class is time-invariant, mapped by "
                    "reconciliation_c.ROW_C_OWNERSHIP_MAP unchanged, " + rmu.OWNERSHIP_SETTLED_D117 +
                    " (reconciliation_mu.OWNERSHIP_SPECIFICATION_D117). " + rmu.OWNERSHIP_MISSING_TREATMENT + " "
                    + OWNERSHIP_PANEL_TEXT)
NEEDS_U = ("RunInputs.reconciliation_u (RowUInputs) and RunInputs.reconciliation_u_inputs_are (INVENTED_INPUTS or "
           "RESEARCH_DATA_AFTER_THE_FREEZE; with no value the row stops in words and none is chosen for the caller). On "
           "research data the row is refused in words, before any step, without the gate file and the run's "
           "authorization, with a Short Form code other than the adopted one (D-115), or with a specification not "
           "equal to reconciliation_mu.ryu_spec(reconciliation_mu.U_SHORT_FORM_ADOPTED_CODE) (session 27; refusing a "
           "departure in any other field is the session's reading of the fixed specification). The specification is "
           "fixed: reconciliation_mu.ryu_spec("
           "reconciliation_mu.U_SHORT_FORM_ADOPTED_CODE), that is 'unit_years_filed', the Short Form rule adopted by Joe "
           "on 2026-11-20 (D-115); every other field is this study's approximation adopted by Joe on 2026-11-19 (D-107; "
           "U0's assignment D-109) or the paper's own value, refused in words if departed from. sample_flags come from "
           "short_form_filers.adopted_row_u_flags (its choices are short_form_filers.ADOPTED_ROW_U_CHOICES, the one "
           "named place) on a frame that covers every outcome unit-year reaching the Short Form filter, built from the "
           "filer table data/interim/reconciliation_short_form_filers.parquet (18,172 rows, one for each utility, state "
           "and year with a row in the Short Form table, written by the one authorized read of 2026-11-20, D-113) and "
           "the 2019 flags in data/interim/reconciliation_short_form_flags.parquet, both already on disk, and never from "
           "a new read under data/raw. Step U3's window is 2015 to 2025, so the flags are built with step_window=(2015, "
           "2025), the adopted rule applied year by year over the step's own window; one frame of 2015 to 2025 built "
           "that way serves every step, since a filing counts for its own year alone (the session's reading, which Joe "
           "may strike). On the records no 2025 unit-year of the quantity panel has a filer-table row (1,362 unit-years, "
           "0 with a record of a filing; data/frozen/reconciliation_mu_design.json). An outcome unit-year the frame does "
           "not cover stops the step in words and it is recorded as not computed; whether the frame covers every "
           "outcome unit-year cannot be shown before outcomes are read. " + rmu.U_SHORT_FORM_ADOPTED_LABEL + " On the "
           "quantity side (data/frozen/reconciliation_mu_design.json, short_form_flags_for_row_u), the frame with no "
           "exclusion has 16,648 unit-years and 1,808 utilities; one flagged unit-year of 2019 leaves directly, and the "
           "same utility's 2023 and 2024 leave through the three-year requirement, leaving 16,645 unit-years and 1,807 "
           "utilities. Of the frame's 1,974 unit-years of 2019, 1 has a flag of true, 1,780 have a missing flag and 193 "
           "have no flags row, the last two kept with no record either way. The filer table has rows in each year from "
           "2012 to 2018 and from 2020 to 2025 and none in 2019; of its 13,090 unit-years in row U's window of 2015 to "
           "2024, none has a row in the quantity panel (data/interim/panel_quantities.parquet). No price is read for "
           "these counts, so the paper's missing-price drop is not applied and this is not the paper's sample. The "
           "paper's 1,798 utilities retained and its Short Form group of approximately 560 are printed beside ours for "
           "comparison only and are no part of any reason. U0's treatment is cumulative_mw on "
           "reconciliation_treatment.assign_polygon_smallest(sites, "
           "data/interim/reconciliation_polygon_incidence.parquet, data/interim/panel_reported_ids.parquet, "
           "**ROW_U_POLYGON), the smallest containing polygon over every polygon with the type not read, our labelled "
           "approximation (D-109), built on the real quantity files 2026-11-19 (2,157 of 2,203 data center sites mapped "
           "to a panel unit; one exact area tie listed, not broken; that site has no assigned polygon, is listed apart in "
           "the entity-type list and counts in \"lying in any\" (adopted by Joe on 2026-11-19, D-111)). It is the same "
           "rule and the same assignment as C0 to C2, which is not independent validation. U1 to U3 need a cumulative-MW treatment on the inventory's "
           "site-year load (reconciliation_treatment.cumulative_mw, mw_source 'site_year_load'). " + OWNERSHIP_U_TEXT +
           " Outcome frames res_price_default_service and res_price. No assigned site is not "
           "proof of no facility. No step returns a reproduction verdict (D-107, D-109); u1_sentence returns the adopted "
           "U1 sentence chosen by whether our co-op and municipal coefficients are each above our investor-owned one, "
           "by a strict comparison of our point estimates, exactly equal coefficients giving \"not each above\" and no "
           "test entering the choice (adopted by Joe on 2026-11-19, D-111), and u1_indistinguishable decides nothing.")
NEEDS_C = ("RunInputs.reconciliation_c (RowCInputs). choices must equal reconciliation_c.SPECIFICATION (check_specification "
           "refuses any other value in words); c4_cap 99.5 (OURS_C4_CAP); spending_tables with 'paper' and 'current'; "
           "hosts_for_c5 equal to never_host_units(None, None, counts_verified, 'zero_count_panel_years'). counts_polygon "
           "for C0 to C2: operating_counts(sites, reconciliation_treatment.assign_polygon_smallest(sites, "
           "data/interim/reconciliation_polygon_incidence.parquet, data/interim/panel_reported_ids.parquet, "
           "**ROW_C_POLYGON).table)[0] (the smallest containing polygon by area over every territory, the type not "
           "read, our reading of the paper's words, adopted by Joe on 2026-11-19, D-111), built on the real quantity "
           "files 2026-11-19 (2,157 of 2,203 data center sites mapped to a panel unit; one exact area tie listed, not "
           "broken); this layer copy has 2,931 polygons against "
           "the paper's 3,805 territories, so it is not shown to be the paper's layer. The fiber shares "
           "are an input the caller supplies, their content settled as the shares from the December Form 477 filings "
           "(ours, adopted by Joe on 2026-11-19, D-107). " + OWNERSHIP_C_TEXT + " Outcome frame res_price_cents_per_kwh_real_2024: the "
           "panel's delivery-inclusive " + rc.OURS_PRICE_SERIES + ", nominal cents per kWh, put in real 2024 cents per "
           "kWh, our comparison specification, " + rc.SETTLED_D117_PRICE + ", and not a claim that the paper used "
           "exactly this construction; it is carried by reconciliation_c.SPECIFICATION as price_series "
           "(reconciliation_c.OURS_PRICE_SERIES) and is refused in words if departed from. " + rc.PRICE_SERIES_LABEL
           + " " + rc.PRICE_SERIES_NOT_CHECKED + " The real 2024 dollars are by row C's deflator, the CPI-U annual "
           "average (BLS CUUR0000SA0, cpi_u in "
           "data/frozen/dc_construction_spending.csv, factors from reconciliation_c.cpi_factors_to_2024), ours and not the "
           "paper's, adopted by Joe on 2026-11-19 (D-111); it is carried by reconciliation_c.SPECIFICATION as "
           "price_deflator, is not the caller's choice and is refused in words if departed from. The paper says only "
           "\"the CPI\"; our spending series deflated with it equals the paper's printed Table S3 for 2015 to 2023 at "
           "printed precision, which supports and does not establish that it is the paper's series. Comparison-only "
           "(D-109); no step returns a reproduction verdict. C0 to C2's assignment is the same rule as row U's U0, which is not independent "
           "validation. No assigned site is not proof of no facility; C5's never-host classification is the "
           "operational one and is not redefined.")
NEEDS_IAS = ("RunInputs.inventory_inputs_are (research data is refused by the module's guard unless the gate file exists "
             "and the run is authorized). side.q needs nonres_mwh "
             "including 2009 to 2011; side.dose needs dc_gwh (base_retail_gwh is no longer read). The history of the "
             "inventory is settled by Joe's ruling of 2026-11-20 (D-119), in his words: \"Use the inventory as built, "
             "the load history underlying the headline design, for the inventory-against-sales check.\" The check is "
             "given the inventory as built, which this registry supplies as RunInputs.side.dose, the dose frame the "
             "headline design's sets are split on (inventory_against_sales.INVENTORY_HISTORY_D119). The check cannot "
             "detect a frame built from another history, since it takes whatever frame it is given, so the registry "
             "establishes it before the check is called, in two ways (session 27): equal content by hash, "
             "run_outcomes.frame_fingerprint(side.dose) against RunInputs.inventory_as_built.dose_fingerprint, the stamp "
             "taken when the sets were split; and the headline set split again from the frame, design.split on side.q "
             "and side.dose giving exactly the hosts with their cohorts and the comparison-eligible units of "
             "RunInputs.sets. On research data RunInputs.inventory_as_built is required and a substituted split "
             "function is refused; a mismatch is refused in words and the check is not run.")
NEEDS_CS = ("RunInputs.cs_sample (CSSampleInputs: host and comparison set-asides, the price hold, the D-34 history). The "
            "run needs diff-diff 4.0.0, installed only in the gizmo folder's .venv; under another interpreter it is a "
            "failure in words.")
NEEDS_AGREE = "Whatever the four main entries and callaway_santanna need (the latter runs only under the .venv)."
NEEDS_SN_SINGLE = ("RunInputs.second_number['established']: the common-dose mapping, common_dose_rule.established_as_ruled"
                   "(...), equivalently second_number.common_dose_finding()[0], per Joe's ruling D-107 (judged on the "
                   "wider admissible histories; under it neither Portland General nor Umatilla has an established common "
                   "change at any form, so both stay outside the exception). Required, with no default.")
NEEDS_SN_SCENARIO = ("RunInputs.second_number['scenario_points'][name] (load share in points by unit and year, from "
                     "second_number_scenarios.points_of on realise_history) and ['scenario_no_dose'][name]; units "
                     "(['scenario_units']) = every panel unit less the price hold, the two load-unknown units included. "
                     "Quantity side only. The per-state reconstruction check must pass in a state before its scenario "
                     "work is used there (Joe, D-107).")
NEEDS_TIMING = ("RunInputs.timing_added: {(utility_id_eia, state): year} from timing_run.no_anchoring_years(<the "
                "treatment_bounds.json record at timing_run.RECORD_PATH>, <headline_set.csv frame>)['years']; required, no "
                "default; the registry reads no file.")
# Where the early-years reading's second sentence takes its flag for the headline set (Joe, 2026-11-20, D-113). The two
# rates and their exact intervals are the file's, written out here; a test checks them against the stored file.
DRIFT_SOURCE = ("; the second early-years sentence follows RunInputs.catches_drift, which a caller takes for the headline "
                "set at 2% from data/frozen/early_years_drift_selected_procedure.json through "
                "run_outcomes.catches_drift_from_file. That file is the result of exercise 4a "
                "(docs/gate1/simulation-spec-4a-early-years-drift-2026-11-20.md), run once under Joe's ruling of "
                "2026-11-20 (D-113). The early-years test detected a drift of 1% a year in 0.129 of datasets under G0 "
                "(exact 95% interval 0.11461 to 0.14449) and in 0.0475 under G6 (0.0386 to 0.05776), both under one "
                "half, so the file's outcome is 'added' and the function gives True for the headline set; the companion "
                "sets get no value. It is a figure carried into a reading the plan already fixed and changes no rule. "
                "The rates are a property of this test on this design under made-up prices of two assumed kinds and are "
                "not evidence about real pre-trends")

# E7's builder text (session 25). The quantity-side wiring for both sets is inventory_runs.E7_SETS; the caller's context for
# each set is RunInputs.inventory_contexts.
E7_BUILDER = ("inventory_runs.e7_designs (seed 20261203), redate (G-a) per draw. The caller's context for each set: "
              "inventory_runs.Context.from_files(0.02) for the headline set and "
              "inventory_runs.Context.from_files(0.02, which=\"every_cohort_utility\") for every cohort utility, which "
              "gives that set no set-aside list, as design.split does (inventory_runs.aside_for); the roster is the set's "
              "own hosts from RunInputs.sets. E7's quantity-side summary for the headline set and for every cohort "
              "utility is written by inventory_runs.main to data/frozen/inventory_run_designs.json, blocks E7 and "
              "E7_every_cohort_utility, at the specified 200 draws a direction under seed 20261203. For every cohort "
              "utility the primary reporting denominator of those quantity-side shares is the 36 hosts of the set's "
              "reference design, with the roster of 41 reported beside it (Joe, 2026-11-20, D-117), by presentation only "
              "with nothing redrawn: e7_presentation.denominators reads the stored block E7_every_cohort_utility, and "
              "data/frozen/e7_reporting_denominator.json holds both figures")

# The three supplementary outcomes' estimator text and labels (Joe, 2026-11-20, D-117; supplementary_outcomes).


def supplementary_estimator(name: str) -> str:
    spec = so.SPECS[name]
    return (K + " on the natural log of " + spec.unit + ", which supplementary_outcomes.run_on_design (log_frame_for_"
            "design) takes on the levels the caller supplies, in that unit (column " + spec.source_column + " of "
            + spec.source_file + "), with no constant added, nothing imputed and no row dropped. "
            + so.NON_COMPUTABLE_RULE + " Such a result is returned as a record with its reasons and counts, and nothing "
            "is estimated on that design for that outcome; the headline price design and the other outcomes are "
            "unchanged by it")


SUPPLEMENTARY_LABELS = (NEXT_TO_PRICE, so.SUPPLEMENTARY_LABEL, so.VALIDATION_LIMIT) + NV

REGISTRY: tuple = (
    Entry("reconciliation_row_U", f"{REG}, Row U (Ryu and Hiatt), steps U0 to U3", (PAPER_SAMPLE,),
          "reconciliation_treatment cumulative-MW treatments supplied per step (RowUInputs)",
          "reconciliation_mu.run_u_step (ln price on ln(MW + 1), utility and year effects, by state) per step, the "
          "ownership estimates and U0's pooled estimate returned as comparisons under our specification with no verdict; "
          "u1_sentence (the adopted U1 sentences, D-109)",
          (RECONCILIATION, "reported first", ROW_U_NO_VERDICT, OTHER_ESTIMATOR), BUILT, outcome=None,
          outcomes=(PRICE_DEFAULT_SERVICE, PRICE_DELIVERY_INCLUSIVE), runner=_row_u_guarded(_row_mu("U")), needs=NEEDS_U),
    Entry("reconciliation_row_C", f"{REG}, Row C (Scalera, Bosetti and Pecci), steps C0 to C4 and the test C5",
          (PAPER_SAMPLE,), "counts, load share, fiber share and spending supplied (RowCInputs)",
          "reconciliation_c.run_row_c (OLS and two-stage least squares, utility-state and state-by-year effects; C5's "
          "reduced form on never-host utility-states), every step returned as a comparison under our specification with "
          "no verdict",
          (RECONCILIATION, "reported first", ROW_C_NO_VERDICT, "C5's interval is the row's own (clustered by utility-state)",
           OTHER_ESTIMATOR),
          BUILT, outcome=None, outcomes=(PRICE_CENTS_REAL_2024,), runner=_row_c, needs=NEEDS_C),
    Entry("inventory_against_sales", f"{RC}, Does the inventory show up in sales?", (H2,),
          BW + "; non-residential sales (side.q) and the inventory's load (side.dose)",
          "inventory_against_sales.check on its adopted settings (D-107; quantities only: reads no outcome)",
          ("reported check", QUANTITIES_ONLY), BUILT,
          outcome=None, runner=_inventory_against_sales, needs=NEEDS_IAS),
    Entry("main_headline_set", "Electricity: the main estimate; The headline; Reported checks (early-years test, trend "
          "illustrations)", (H2,), BW, K + "; outcome_analysis.early_years_reading and trend_illustrations" + DRIFT_SOURCE,
          (HEADLINE, VALIDATED_HERE), BUILT, runner=_main),
    Entry("main_ten_year_set", "Electricity: the main estimate, the sets beside it; Order of unblinding",
          ((TEN_YEAR_SET, 0.02),), BW, K + "; early-years reading and trend illustrations",
          (STRESS_TEST, "reported beside the headline") + NV, BUILT, runner=_main),
    Entry("main_plus_unsettled", "Electricity: the main estimate, the sets beside it; Order of unblinding",
          ((PLUS_UNSETTLED, 0.02),), BW, K + "; early-years reading and trend illustrations",
          ("reported beside the headline", "rests on hosts unsettled on assignment") + NV, BUILT, runner=_main),
    Entry("main_every_cohort_utility", "Electricity: the main estimate, the sets beside it; Order of unblinding",
          (E2_,), BW, K + "; early-years reading and trend illustrations",
          ("reported beside the headline", "every cohort utility as built, assignment and dating limitations kept explicit") + NV,
          BUILT, runner=_main),
    Entry("timing_run_no_anchoring_years", "Electricity: the main estimate, the sets beside it ('As a timing run': Public "
          "Service of Colorado and Ohio Power at their no-anchoring years at 2%; R7, Joe, 2026-11-19, D-107)", (H2,),
          "timing_run.build (the headline set with the two hosts added at their no-anchoring years, each matched at its "
          "own reference year under every existing rule; the other hosts' matches checked unchanged)",
          "timing_run.estimate_timing_run (the rank test before any fit, then " + K + ")",
          ("timing run", tr.LABEL) + NV, BUILT, runner=_timing, needs=NEEDS_TIMING),
    Entry("customer_weighted", "Electricity: the main estimate, Weights ('the same estimate weighted by each host's "
          "residential customers in its reference year'; Joe, 2026-11-19, D-105)", (H2,),
          BW + "; each host's residential customers in its reference year from side.q (res_customers), on every row of "
          "its sub-experiment (weighted_fit.customer_weights)",
          "weighted_fit.weighted_fit (weighted least squares on the kernel's own regressors, inference_check.fixed_parts on "
          "outcome_analysis.stackable; point estimate only, no range), with the nominal customer weight shares and the "
          "effective contributions to the weighted headline reported apart, the effective contribution shown as the "
          "own-row headline weight (its definition accepted by Joe on 2026-11-19, D-111)",
          ("labelled", DESCRIPTIVE_WEIGHTED, WEIGHTED_NO_VALIDATION), BUILT, runner=_customer_weighted),
    Entry("other_outcome_kwh_per_customer", "Other outcomes and robustness: other outcomes; Electricity: the main estimate, "
          "Outcome", (H2,), BW, supplementary_estimator(KWH), SUPPLEMENTARY_LABELS, BUILT, outcome=KWH,
          runner=_other_outcome),
    Entry("other_outcome_bill_per_customer", "Other outcomes and robustness: other outcomes; The headline ('Any statement "
          "about an increase of 5%')", (H2,), BW, supplementary_estimator(BILL), SUPPLEMENTARY_LABELS, BUILT, outcome=BILL,
          runner=_other_outcome),
    Entry("other_outcome_residential_customers", "Other outcomes and robustness: other outcomes", (H2,), BW,
          supplementary_estimator(CUSTOMERS), SUPPLEMENTARY_LABELS, BUILT, outcome=CUSTOMERS, runner=_other_outcome),
    Entry("second_number_as_assigned", f"{SN}; rule 8.3, the run on doses as assigned", (SN_SAMPLE,),
          "second_number.build_frame (usable in all six years, region, size band)",
          "second_number.run (estimator.Fit, the wild cluster bootstrap as built, candidate A), outcome aligned by "
          "second_number.outcome_matrix", ("secondary, behind the main estimate", NOT_CALIBRATED), BUILT,
          runner=_sn_primary(sn.POST)),
    Entry("second_number_settled_only_classes_2_to_4", f"{SN}; rule 8.3 (the settled run: classes 2 to 4 at each form, "
          "no endpoint exposure in modeled histories, zero exposure change with load in reach, and settled; D-105)",
          (SN_SAMPLE,), "second_number.build_frame, classify_by_cap (each form at its own cap), run_samples",
          "second_number.run_single_dose (per form, each utility at its single dose)", (NOT_CALIBRATED,), BUILT,
          runner=_sn_single(sn.RUN_SETTLED), needs=NEEDS_SN_SINGLE),
    Entry("second_number_ten_highest_leverage_left_out", f"{SN}; rule 8.3 (at each form, the ten highest-leverage "
          "utilities among that form's classes 5 to 8, not settled, left out; D-105)", (SN_SAMPLE,),
          "second_number.build_frame, classify_by_cap (each form at its own cap), run_samples (leave_out_ten per form)",
          "second_number.run_single_dose (per form, each utility at its single dose)", (NOT_CALIBRATED,),
          BUILT, runner=_sn_single(sn.RUN_LEAVE_TEN), needs=NEEDS_SN_SINGLE),
    Entry("second_number_sensitivity_scenario_a_runner_up_placement", f"{SN}; rule 8.3 and 'A limitation, stated' "
          "(sensitivity scenario A, runner-up placement; Joe, 2026-11-19, D-107, adopting R2 of D-106)", (SN_SAMPLE,),
          "second_number_scenarios.realise_history (pass_c_exact.realise per state) with scenario_a_settings("
          "runner_up_placement(...)), then points_of, then scenario_frame",
          "second_number_scenarios.run_scenario (second_number.run, the wild cluster bootstrap as built, candidate A)",
          (ss.LABELS[ss.SCENARIO_A], NOT_CALIBRATED), BUILT, runner=_sn_scenario(ss.SCENARIO_A), needs=NEEDS_SN_SCENARIO),
    Entry("second_number_sensitivity_scenario_b_other_end_of_every_dated_interval", f"{SN}; rule 8.3 and 'A limitation, "
          "stated' (sensitivity scenario B, the other end of every dated interval; Joe, 2026-11-19, D-107, adopting R2 "
          "of D-106)", (SN_SAMPLE,),
          "second_number_scenarios.realise_history (pass_c_exact.realise per state) with scenario_b_settings(...), then "
          "points_of, then scenario_frame",
          "second_number_scenarios.run_scenario (second_number.run, the wild cluster bootstrap as built, candidate A)",
          (ss.LABELS[ss.SCENARIO_B], NOT_CALIBRATED), BUILT, runner=_sn_scenario(ss.SCENARIO_B), needs=NEEDS_SN_SCENARIO),
    Entry("second_number_e3_after_period_2024_2025", f"{FR}, E3 (the second number's after period of 2024 to 2025)",
          (SN_SAMPLE,), "second_number.build_frame(post=E3_POST)", "second_number.run",
          (FALSIFICATION, NOT_CALIBRATED), BUILT, runner=_sn_primary(sn.E3_POST)),
    Entry("second_number_year_by_year", f"{SN} (the year-by-year version, a side run)", (SN_SAMPLE,),
          "second_number.panel_frame", "second_number.run", (SIDE_RUN, NOT_CALIBRATED), BUILT, runner=_sn_year_by_year),
    Entry("affiliates_readmitted", f"{OTHER}: Affiliates readmitted (rule 2.3)", (H2,),
          "design.build_with_rules under power_simulation.AFFILIATES_READMITTED", K, (SENSITIVITY, READING + " (which sets)") + NV,
          BUILT, runner=_rules_variant(ps.AFFILIATES_READMITTED)),
    Entry("shared_suppliers_removed", f"{OTHER}: Shared suppliers removed (rule 2.4)", (H2,),
          BW + ", then prefreeze_summaries.supplier_exercise and remove_pairs (per host and match, no rematching)", K,
          (SENSITIVITY, READING + " (which sets)") + NV, BUILT, runner=_suppliers),
    Entry("leave_one_comparison_out", f"{OTHER}: Leave one comparison out (rule 7); {RC}, Influence", (H2,),
          BW + ", then influence.deletions and influence.leave_out per deletion", K + ", one fit per deletion",
          (SENSITIVITY, READING + " (which sets)") + NV, BUILT, runner=_deletions("comparison")),
    Entry("leave_one_company_out", f"{OTHER}: Leave one company out (rule 7); {RC}, Influence", (H2,),
          BW + ", then influence.deletions (company rows) and influence.leave_out per deletion; a utility with no "
          "ownership row is deleted alone, a deletion convention for the leave-one-company-out exercise and not evidence "
          "of independent ownership (Joe, 2026-11-19, D-111)", K + ", one fit per deletion",
          (SENSITIVITY, READING + " (which sets)") + NV, BUILT, runner=_deletions("company")),
    Entry("unresolved_ownership_excluded", "Electricity: the main estimate, Comparison utilities (the sensitivity that "
          "excludes hosts with unresolved ownership)", (H2, E2_),
          "design.build_with_rules under power_simulation.UNRESOLVED_OWNERSHIP_EXCLUDED", K, (SENSITIVITY,) + NV, BUILT,
          runner=_unresolved),
    Entry("later_start_plus_1", f"{OTHER}: The later-start sensitivity, on outcomes (+1 year)", (H2,),
          "inventory_runs.later_start_rows, rebuild, redate (G-a)", K, (STRESS_TEST, TIMING_WITH_REMATCHING) + NV, BUILT,
          runner=_later_start(1)),
    Entry("later_start_plus_3", f"{OTHER}: The later-start sensitivity, on outcomes (+3 years)", (H2,),
          "inventory_runs.later_start_rows, rebuild, redate (G-a)", K, (STRESS_TEST, TIMING_WITH_REMATCHING) + NV, BUILT,
          runner=_later_start(3)),
    Entry("later_start_plus_5", f"{OTHER}: The later-start sensitivity, on outcomes (+5 years)", (H2,),
          "inventory_runs.later_start_rows, rebuild, redate (G-a)", K, (STRESS_TEST, TIMING_WITH_REMATCHING) + NV, BUILT,
          runner=_later_start(5)),
    Entry("callaway_santanna", f"{OTHER}: Callaway and Sant'Anna's estimator with two years of anticipation", (H2,),
          "callaway_santanna.sample and frame (CSSampleInputs and RunInputs.side)",
          "callaway_santanna.run (diff-diff 4.0.0, pinned; installed in the gizmo folder's .venv only)",
          ("a second estimator of the same quantity", CS_RANGE_LABEL, CS_SAMPLE_DIFFERENCE, OTHER_ESTIMATOR), BUILT,
          runner=_callaway_santanna,
          needs=NEEDS_CS),
    Entry("estimators_agree", f"{RC}, Do the estimators agree?", (SIDE_BY_SIDE,),
          "the four main entries' runners and callaway_santanna's, on the same price outcome",
          "estimators_table.table (from_stacked_result, from_callaway_santanna_result)",
          ("reported check", et.NEED_NOT_AGREE,
           "the Callaway and Sant'Anna row carries estimators_table.CALLAWAY_SANTANNA_SAMPLE_LABEL (Joe, 2026-11-19, "
           "D-111): 680 of 1,670 never-treated units in no cohort's host region kept; a difference from the headline "
           "estimate cannot be attributed solely to the estimator"), BUILT, runner=_estimators_agree, needs=NEEDS_AGREE),
    Entry("longer_horizon", f"{OTHER}: A longer horizon", PRIMARY_AND_COMPANION,
          "side_runs.long_horizon (thirteen-year windows, rematched)",
          "outcome_analysis.estimate_long_horizon (estimate_span on event years -6 to 6, headline 4 to 6; and estimate on "
          "the same hosts and matches); outcome aligned by outcome_vector_span and outcome_vector",
          (SIDE_RUN,) + NV, BUILT, runner=_longer_horizon),
    Entry("future_hosts_as_comparisons", f"{OTHER}: Future hosts as a second comparison group", (H2,),
          "future_hosts.side_run_design (each cohort's pool plus its admitted future hosts)", K, (SIDE_RUN,) + NV, BUILT,
          runner=_future_hosts),
    Entry("own_state_comparisons", f"{OTHER}: Comparison utilities from the host's own state only",
          PRIMARY_AND_COMPANION, "side_runs.own_state",
          K + " with absorbed_controls=LEAVE_OUT_IF_EXACTLY_ABSORBED", (SIDE_RUN, "not shown beside the headline") + NV,
          BUILT, runner=_own_state),
    Entry("threshold_1pct", f"{OTHER}: Thresholds of 1% and 5% (the 1% run)", ((EVERY, 0.01),),
          "every cohort utility as built at 1% (every_cohort_utility_at, supplied by the caller), then build_with_rules", K,
          (EXPLORATORY,) + NV, BUILT, runner=_threshold),
    Entry("threshold_5pct", f"{OTHER}: Thresholds of 1% and 5% (the 5% run, both readings)",
          ((HEADLINE_SET, 0.05), (EVERY, 0.05)),
          "side_runs.without_rappahannock, then build_with_rules at 5% (the footnote with Rappahannock beside it)", K,
          ("both sets reported, the headline rules first (adopted by Joe on 2026-11-19, D-111)",) + NV, BUILT,
          runner=_threshold),
    Entry("fuel_mix_categorical", "Electricity: the main estimate, Fuel-mix control (labelled sensitivity: the "
          "categorical group-by-year specification)", (H2,),
          "design.build_with_rules under power_simulation.CATEGORICAL_FUEL", K, (SENSITIVITY, READING + " (place in the "
          "order and which sets)") + NV, BUILT, runner=_rules_variant(ps.CATEGORICAL_FUEL)),
    Entry("fuel_mix_none", "Electricity: the main estimate, Fuel-mix control (labelled sensitivity: no fuel-mix control)",
          (H2,), "design.build_with_rules under power_simulation.NO_FUEL_CONTROL", K,
          (SENSITIVITY, READING + " (place in the order and which sets)") + NV, BUILT, runner=_rules_variant(ps.NO_FUEL_CONTROL)),
    Entry("size_band_side_run", "Electricity: the main estimate, Size adjustment (the size-band form as a side run)", (H2,),
          "size_band_run.build (cells of reference-year region by size band, every eligible unit of the host's cell its "
          "comparisons, the support rule's first limb as written; R7, Joe, 2026-11-19, D-107; the tested per-host form, "
          "adopted by Joe on 2026-11-19 (D-111) for the headline set at 2%; a set in which two hosts share a cohort and a "
          "cell is refused in words as outside this freeze, and no extension is built)",
          "size_band_run.estimate_size_band (the rank test before any fit, then " + K + ")",
          (SIDE_RUN, sbr.LABEL) + NV, BUILT, runner=_size_band),
    Entry("E1", f"{FR}, E1 events shifted six years early", PRIMARY_AND_COMPANION, "side_runs.e1 (G-a at g-9)", K,
          (FALSIFICATION, TIMING_WITH_REMATCHING) + NV, BUILT, runner=_e1),
    Entry("E2", f"{FR}, E2 fake events for future hosts", ((E2_SAMPLE, 0.02),),
          "future_hosts.e2_design (each unit at its fake date f, the main pool, G-a)", K,
          (FALSIFICATION, TIMING_WITH_REMATCHING) + NV, BUILT, runner=_e2),
    Entry("E3", f"{FR}, E3 drop 2021 to 2023 (full windows)", PRIMARY_AND_COMPANION, "side_runs.e3", K,
          (FALSIFICATION, "earlier-cohort sensitivity") + NV, BUILT, runner=_e3),
    Entry("E4a", f"{FR}, E4(a) the slow path", PRIMARY_AND_COMPANION, "inventory_runs.e4a, redate (G-a)", K,
          (FALSIFICATION, TIMING_WITH_REMATCHING) + NV, BUILT, runner=_e4a),
    Entry("E4b", f"{FR}, E4(b) anchoring off", PRIMARY_AND_COMPANION, "inventory_runs.e4b, redate (G-a)", K,
          (FALSIFICATION, TIMING_WITH_REMATCHING) + NV, BUILT, runner=_e4b),
    Entry("E5", f"{FR}, E5 high-upward-scaling states dropped", PRIMARY_AND_COMPANION, BW + ", then side_runs.e5 (G-b)", K,
          (FALSIFICATION, REMOVES_UNITS) + NV, BUILT, runner=_e5),
    Entry("E6", f"{FR}, E6 comparison utilities that change market region dropped", PRIMARY_AND_COMPANION,
          BW + ", then side_runs.e6 (G-b)", K, (FALSIFICATION, REMOVES_UNITS) + NV, BUILT, runner=_e6),
    Entry("E7_earlier", f"{FR}, E7 permit-dated start years redrawn (earlier)", PRIMARY_AND_COMPANION,
          E7_BUILDER, K + ", point estimate per draw",
          (FALSIFICATION, TIMING_WITH_REMATCHING, POINT_ESTIMATES_ONLY) + NV, BUILT, runner=_e7("earlier")),
    Entry("E7_later", f"{FR}, E7 permit-dated start years redrawn (later, the mirror, an assumption)",
          PRIMARY_AND_COMPANION, E7_BUILDER,
          K + ", point estimate per draw", (FALSIFICATION, TIMING_WITH_REMATCHING, POINT_ESTIMATES_ONLY) + NV, BUILT,
          runner=_e7("later")),
    Entry("condition_1_load_share", f"{COND}, 1: load share of 10% or more in event year 3", PRIMARY_AND_COMPANION,
          BW + ", conditions.load_share_grouping", "conditions.contrast (outcome_analysis.point_fit; no range, no test)",
          (DESCRIPTIVE_CONTRAST, "companion set: " + READING), BUILT, runner=_condition("load_share")),
    Entry("condition_2_investor_owned", f"{COND}, 2: investor-owned against public and cooperative", PRIMARY_AND_COMPANION,
          BW + ", conditions.ownership_grouping", "conditions.contrast (no range, no test)",
          (DESCRIPTIVE_CONTRAST, "companion set: " + READING), BUILT, runner=_condition("ownership")),
    Entry("condition_3_retail_choice_proxy", f"{COND}, 3: retail choice by a proxy (the host's own unit; the state reading "
          "beside it)", PRIMARY_AND_COMPANION, BW + ", conditions.retail_choice_grouping (both readings)",
          "conditions.contrast (no range, no test)", (DESCRIPTIVE_CONTRAST, cn.PROXY_LABEL, "companion set: " + READING),
          BUILT, runner=_condition("retail_choice")),
    Entry("condition_4_past_utilization", f"{COND}, 4: past utilization above against at or below the median",
          PRIMARY_AND_COMPANION, BW + ", conditions.past_utilization_grouping", "conditions.contrast (no range, no test)",
          (DESCRIPTIVE_CONTRAST, "companion set: " + READING), BUILT, runner=_condition("past_utilization")),
    Entry("influence_each_market_region_left_out", f"{RC}, Influence (each market region left out; R7, Joe, 2026-11-19, "
          "D-107; its definitions of present regions and states, a state deletion, the range's members and \"moves most\" "
          "adopted by Joe on 2026-11-19, D-111)", (H2,),
          BW + ", then influence_deletions.delete_region for each region in regions_present (every host whose "
          "reference-year region it is leaves with its matches; nothing rematched)",
          "influence_deletions.estimate_deletion per region (rule 7's treatment and the rank test before any fit, then "
          + K + "); influence_deletions.summarise",
          ("reported check", INFLUENCE_LABELS["region"]) + NV, BUILT, runner=_influence("region")),
    Entry("influence_each_state_left_out", f"{RC}, Influence (each state left out; R7, Joe, 2026-11-19, D-107"
          "; its definitions of present regions and states, a state deletion, the range's members and \"moves most\" "
          "adopted by Joe on 2026-11-19, D-111)", (H2,),
          BW + ", then influence_deletions.delete_state for each state in states_present except Virginia (its hosts "
          "leave, its comparison utilities leave every remaining host's matches; nothing rematched)",
          "influence_deletions.estimate_deletion per state (rule 7's treatment and the rank test before any fit, then "
          + K + "); influence_deletions.summarise",
          ("reported check", INFLUENCE_LABELS["state"]) + NV, BUILT, runner=_influence("state")),
    Entry("influence_virginia_left_out", f"{RC}, Influence (Virginia left out; R7, Joe, 2026-11-19, D-107"
          "; its definitions of present regions and states, a state deletion, the range's members and \"moves most\" "
          "adopted by Joe on 2026-11-19, D-111)", (H2,),
          BW + ", then influence_deletions.delete_state(d, 'VA'), whether or not Virginia is in the design",
          "influence_deletions.estimate_deletion(d, 'state', 'VA', ...), with its sentence on what Virginia removes "
          "(checked on the design; an unchanged estimate is not presented as a check passed)",
          ("reported check", INFLUENCE_LABELS["virginia"]) + NV, BUILT, runner=_influence("virginia")),
    Entry("influence_five_highest_load_utilities_dropped", f"{RC}, Influence (the five highest-load utilities dropped; "
          "Joe, 2026-11-19, D-105: absolute data center load in event year 3, not load share)", (H2,),
          BW + ", then influence_load.drop_the_five (the five hosts with the largest dc_gwh from side.dose in their own "
          "event year 3, dropped with their sub-experiments; every other host keeps its matches; the rules carried)",
          K + " on the deleted design, after the rank test made before any fit (influence.estimable)",
          ("reported check",) + NV, BUILT, runner=_five_highest_load),
    Entry("tariff_check", f"{RC}, The tariff check (docs/tariff-check.md)", (), "none", "none", ("reported check",),
          NOT_BUILT, "no tariff is collected before the freeze and no module rebuilds bills from rate schedules"),
    Entry("regional_layer", "Electricity: regional layer (accounting, not an estimate)", (), "none", "none",
          (EXPLORATORY,), NOT_BUILT, "no module computes PJM capacity cost per customer or the exploratory description "
          "of bills after June 2025; nothing in the plan specifies the latter"),
    Entry("exploratory_work", "Order of unblinding (last: exploratory work)", (), "none", "none", (EXPLORATORY,),
          NOT_BUILT, "not specified by the plan, so there is nothing to build"),
    # Out of scope for this freeze (Joe, 2026-11-19, D-109): listed after the executable order, in no executable order of
    # unblinding and in no built count. Its runner is not attached; the code is kept dormant as ROW_M_DORMANT_RUNNER.
    Entry("reconciliation_row_M", "Reconciliation rows, Row M (Meeks, Pless, Qi and Wang), steps M0 to M4: out of scope "
          "for this freeze (Joe, 2026-11-19, D-109)", (PAPER_SAMPLE,),
          "none in this freeze (dormant: reconciliation_treatment first-year treatments per step, RowMInputs)",
          "none in this freeze (dormant: reconciliation_mu.run_m_step per step and describe_row_m; the row's verdict logic "
          "is not applied in this freeze)",
          (ROW_M_OUT_OF_SCOPE_LABEL, ROW_M_CONTEXT_LABEL), OUT_OF_SCOPE, OUT_OF_SCOPE_M, outcome=None, context=CONTEXT_M),
)

REGISTRY_BY_ID = {e.id: e for e in REGISTRY}
if len(REGISTRY_BY_ID) != len(REGISTRY):
    raise RuntimeError("two registry entries share an id")

# The executable order of unblinding: every entry but those out of scope for this freeze (row M, D-109). run_all iterates
# this and nothing else; it begins with rows U and C.
ORDER_OF_UNBLINDING: tuple = tuple(e for e in REGISTRY if e.status != OUT_OF_SCOPE)
OUT_OF_SCOPE_FOR_THIS_FREEZE: tuple = tuple(e for e in REGISTRY if e.status == OUT_OF_SCOPE)
if any(e.status == OUT_OF_SCOPE for e in REGISTRY[:len(ORDER_OF_UNBLINDING)]):
    raise RuntimeError("an entry out of scope for this freeze sits inside the executable order")

# Row M's runner, dormant (D-109): kept as it was, attached to no entry and called by nothing in this module. Tests call it
# directly on invented inputs as a test of dormant code.
ROW_M_DORMANT_RUNNER = _row_mu("M")


# ======================================================================================================================
# run and run_all
# ======================================================================================================================

def _outcome_frame(outcomes, name: str) -> tuple[pd.DataFrame | None, str | None]:
    """The caller's outcome for `name`. A DataFrame is the price outcome; a dict maps outcome names to frames. Checks the
    columns; every other check (a missing unit-year, a duplicate key, a value that is not finite) is the kernel's."""
    if isinstance(outcomes, pd.DataFrame):
        f = outcomes if name == PRICE else None
    elif isinstance(outcomes, dict):
        f = outcomes.get(name)
    else:
        return None, f"the outcomes are neither a frame nor a mapping of outcome name to frame ({type(outcomes).__name__})"
    if f is None:
        return None, _missing_frame(name)
    need = KEY + ["year", OUTCOME]
    miss = [c for c in need if c not in f.columns]
    if miss:
        return None, f"the outcome frame for {name!r} has no column {miss}"
    return f, None


class OutOfScopeForThisFreeze(PermissionError):
    """The entry is out of scope for this freeze (row M; Joe, 2026-11-19, D-109): it is not run through the registry."""


def run(entry_id: str, inputs: RunInputs, outcomes) -> dict:
    """One registry entry on the caller's outcome. Returns the entry's record with, for a built entry, one result per set
    (`results`), each carrying `estimated` and, where the run could not be computed, `failure_in_words`. Never raises for
    a failure inside a run: it is caught and recorded in words. An unknown id raises KeyError. An entry out of scope for
    this freeze (row M, D-109) raises OutOfScopeForThisFreeze in words before any input or outcome is looked at."""
    entry = REGISTRY_BY_ID[entry_id]
    if entry.status == OUT_OF_SCOPE:
        raise OutOfScopeForThisFreeze(f"{entry.id} is out of scope for this freeze by Joe's ruling of 2026-11-19 (D-109): "
                                      "it is not run through the registry, and no input or outcome was looked at")
    out = entry.as_record()
    if entry.status != BUILT:
        out.update(estimated=False, results=None)
        return out
    if entry.outcomes:
        # Several named price frames: the runner gets those supplied, and a step whose frame is missing says so. With
        # none supplied the entry is not run.
        frame, missing = {}, []
        for n in entry.outcomes:
            f, why = _outcome_frame(outcomes, n)
            if f is None:
                missing.append(why)
            else:
                frame[n] = f
        out["outcomes_missing"] = missing
        if not frame:
            out.update(estimated=False, results=None, failure_in_words="; ".join(missing))
            return out
    elif entry.outcome is None:
        frame = None                                   # reads quantities only; no outcome is asked for or passed
    else:
        frame, why = _outcome_frame(outcomes, entry.outcome)
        if frame is None:
            out.update(estimated=False, results=None, failure_in_words=why)
            return out
    results = {}
    for s in entry.sets:
        try:
            r = entry.runner(inputs, s, frame, entry)
        except Exception as exc:                                    # noqa: BLE001  recorded in words, never dropped
            r = {"estimated": False, "failure_in_words": _words(exc)}
        results[set_label(s)] = r
    out["results"] = results
    out["estimated"] = any(bool(r.get("estimated")) for r in results.values())
    out["failures_in_words"] = {k: r["failure_in_words"] for k, r in results.items() if r.get("failure_in_words")}
    return out


def run_all(inputs: RunInputs, outcomes) -> dict:
    """Every entry of the executable order of unblinding (ORDER_OF_UNBLINDING), in order. Returns {"runs": [...],
    "counts": ..., "out_of_scope_for_this_freeze": [...]}: every entry run returns a record with its status, whatever
    happens in the others. An entry out of scope for this freeze (row M, D-109) is not run and is listed by id with its
    reason."""
    runs = [run(e.id, inputs, outcomes) for e in ORDER_OF_UNBLINDING]
    by_status = {s: sum(1 for e in REGISTRY if e.status == s) for s in STATUSES}
    failed = [(r["id"], k) for r in runs for k, v in (r.get("results") or {}).items() if not v.get("estimated")]
    return {"runs": runs,
            "out_of_scope_for_this_freeze": [{"id": e.id, "status": e.status, "reason": e.reason}
                                             for e in OUT_OF_SCOPE_FOR_THIS_FREEZE],
            "counts": {"entries": len(runs), "by_status": by_status,
                                     "built_set_runs": sum(len(r.get("results") or {}) for r in runs),
                                     "built_set_runs_not_computed": len(failed),
                                     "not_computed": [f"{i} ({k})" for i, k in failed]}}


# ======================================================================================================================
# The door to outcomes (session 27; Joe, 2026-11-20, D-120): built, and shut until Joe separately authorizes access
# ======================================================================================================================
# The plan was frozen on 2026-11-20 at FREEZE_COMMIT (approved specification APPROVED_SPECIFICATION_COMMIT), internally
# frozen and not externally preregistered. Freeze approval, implementation readiness and authorization to access outcomes
# are three separate steps. The gate file is created only on Joe's separate authorization to access outcomes, and AUTH_ENV
# is set to "1" only for the run he authorizes; until both hold, load_outcomes_after_the_freeze refuses in words before
# any reader is looked up. It is the only place in this module that calls a reader of outcomes, and it calls the reader
# with POST_FREEZE_PURPOSE and nothing else: neither of panel.load_outcomes' exempt purposes (EXEMPT_PURPOSES) is ever
# passed through it, and power_simulation.read_listed_outcomes is refused by identity.

POST_FREEZE_PURPOSE = "outcome_analysis_after_the_freeze"
# panel.load_outcomes' two exempt purposes (pipeline/electricity/panel.py): the construction check of the price series on
# its own, and the power simulation's read of named never-treated units. Neither is ever passed by this door.
EXEMPT_PURPOSES = ("construction_qa", "power_simulation")
FREEZE_COMMIT = "ea426c4b3c971fcf826bdda1fd7a3f3e6bb9fb23"
APPROVED_SPECIFICATION_COMMIT = "ed3a2ff20ececaf005b0a3256a63c5d1d930095a"
PLAN_FILE = "PREANALYSIS.md"


class OutcomeAccessRefused(PermissionError):
    """Outcomes may not be read: a purpose other than POST_FREEZE_PURPOSE, no gate file, no authorization for this run,
    a plan that is not the committed frozen one, or a reader this door never calls. Raised in words."""


@dataclass(frozen=True)
class OutcomesRead:
    """What the door returns. frame: exactly what the reader returned, untouched. record: how it was read, with no
    outcome value in it (the purpose passed, the gate file and the variable, the plan-state record, the reader's name,
    the frame's shape, column names and types, and frame_fingerprint of the frame as the reader returned it)."""
    frame: pd.DataFrame
    record: dict


def _git(root, *args: str) -> subprocess.CompletedProcess:
    """One git command in `root`, read-only. GIT_OPTIONAL_LOCKS=0 keeps git status from refreshing the index."""
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, check=False,
                          env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})


def frozen_plan_state(root=ROOT, *, freeze_commit: str = FREEZE_COMMIT, plan_file: str = PLAN_FILE) -> dict:
    """Whether the plan in `root` is the committed frozen one, read from git (paths relative to `root`, which may be a
    subfolder of a larger repository). Read-only: rev-parse, status and merge-base, nothing else.

    head                                  HEAD's full hash
    plan_blob                             the blob id of `plan_file` at HEAD (None when HEAD's tree has no such file)
    freeze_commit                         the commit named as the freeze
    freeze_commit_is_an_ancestor_of_head  git merge-base --is-ancestor freeze_commit HEAD
    plan_has_no_uncommitted_change        the file is in HEAD's tree and git status --porcelain prints nothing for it,
                                          staged or not, untracked included
    plan_equals_the_freeze_commits        the plan at HEAD is byte for byte the plan at the freeze commit (equal blob
                                          ids). False means a committed amendment exists: it is recorded and not
                                          refused, since an amendment is made in the plan's Deviations log and committed
    established                           False, with `why` in words, when git cannot be run, the folder is not in a
                                          repository, or a command fails (a freeze commit that is not in the repository,
                                          or whose tree holds no plan file, included)
    No absolute path is recorded."""
    rec = {"plan_file": plan_file, "freeze_commit": freeze_commit, "head": None, "plan_blob": None,
           "freeze_commit_is_an_ancestor_of_head": None, "plan_has_no_uncommitted_change": None,
           "plan_equals_the_freeze_commits": None, "established": False, "why": None}

    def not_established(why: str) -> dict:
        rec["why"] = why
        return rec

    rel = f"./{plan_file}"
    try:
        inside = _git(root, "rev-parse", "--is-inside-work-tree")
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return not_established(f"the plan's folder is not inside a git work tree (git rev-parse "
                                   f"--is-inside-work-tree returned {inside.returncode})")
        head = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
        if head.returncode != 0:
            return not_established("HEAD could not be read (git rev-parse --verify HEAD failed): no commit")
        rec["head"] = head.stdout.strip()
        at_head = _git(root, "rev-parse", "--verify", "--quiet", f"HEAD:{rel}")
        rec["plan_blob"] = at_head.stdout.strip() if at_head.returncode == 0 else None
        status = _git(root, "status", "--porcelain", "--untracked-files=all", "--", plan_file)
        if status.returncode != 0:
            return not_established(f"git status on {plan_file} failed (returned {status.returncode})")
        rec["plan_has_no_uncommitted_change"] = rec["plan_blob"] is not None and status.stdout.strip() == ""
        anc = _git(root, "merge-base", "--is-ancestor", freeze_commit, "HEAD")
        if anc.returncode not in (0, 1):
            return not_established(f"the freeze commit {freeze_commit} could not be found or compared with HEAD in this "
                                   f"repository (git merge-base --is-ancestor returned {anc.returncode})")
        rec["freeze_commit_is_an_ancestor_of_head"] = anc.returncode == 0
        at_freeze = _git(root, "rev-parse", "--verify", "--quiet", f"{freeze_commit}:{rel}")
        if at_freeze.returncode != 0:
            return not_established(f"the freeze commit {freeze_commit} holds no {plan_file} in this folder")
        rec["plan_equals_the_freeze_commits"] = rec["plan_blob"] == at_freeze.stdout.strip()
    except (OSError, ValueError) as exc:
        return not_established(f"git could not be run in the plan's folder ({type(exc).__name__})")
    rec["established"] = True
    return rec


def load_outcomes_after_the_freeze(*, reader=None, purpose: str = POST_FREEZE_PURPOSE, plan_state=None) -> OutcomesRead:
    """The only door to outcomes. Refuses in words (OutcomeAccessRefused), in this order:
      1. a `purpose` other than POST_FREEZE_PURPOSE, whatever the state of the gate; either of panel.load_outcomes'
         exempt purposes is refused by name, since the construction and simulation routes are never taken here;
      2. no gate file (pipeline/electricity/panel.GATE_FILE, looked up when called);
      3. the environment variable AUTH_ENV not exactly "1";
      4. a plan that is not the committed frozen one: plan_state() (frozen_plan_state, looked up when called, when
         plan_state is None) not established, PLAN_FILE with an uncommitted change or not in HEAD, or FREEZE_COMMIT not an
         ancestor of HEAD. A committed amendment (plan_equals_the_freeze_commits False) is recorded and not refused.
         Reading "retaining the freeze check" as this check against git is the session's reading;
      5. a reader that is power_simulation.read_listed_outcomes (by identity, or as a functools.partial of it, the
         latter the agent's reading), or that cannot be called.
    Then the reader is called exactly once, as reader(purpose=POST_FREEZE_PURPOSE), with no other argument. reader None
    means panel.load_outcomes, looked up when this function is called and never bound at definition or import time. A
    result that is not a DataFrame is refused in words. Returns OutcomesRead(frame, record): the frame untouched, and a
    record with no outcome value in it."""
    if purpose != POST_FREEZE_PURPOSE:
        if purpose in EXEMPT_PURPOSES:
            raise OutcomeAccessRefused(f"outcomes are not read: {purpose!r} is one of panel.load_outcomes' exempt purposes "
                                       f"({', '.join(EXEMPT_PURPOSES)}), and the construction and simulation routes are "
                                       f"never taken through this door, which passes {POST_FREEZE_PURPOSE!r} and nothing "
                                       "else")
        raise OutcomeAccessRefused(f"outcomes are not read: the purpose {purpose!r} is not {POST_FREEZE_PURPOSE!r}, the "
                                   "only purpose this door passes")
    gate = Path(panel.GATE_FILE)
    if not gate.exists():
        raise OutcomeAccessRefused(f"outcomes are not read: the gate file {gate.name} does not exist (the plan is frozen at "
                                   f"commit {FREEZE_COMMIT[:7]}, and the gate file is created only on Joe's separate "
                                   "authorization to access outcomes)")
    if os.environ.get(AUTH_ENV) != "1":
        raise OutcomeAccessRefused(f"outcomes are not read: the environment variable {AUTH_ENV} is not set to 1 (no "
                                   "authorization for this run)")
    state = (frozen_plan_state if plan_state is None else plan_state)()
    if not isinstance(state, dict) or state.get("established") is not True:
        why = state.get("why") if isinstance(state, dict) else f"the plan check returned a {type(state).__name__}"
        raise OutcomeAccessRefused(f"outcomes are not read: whether {PLAN_FILE} is the committed frozen plan could not be "
                                   f"established ({why})")
    if state.get("plan_has_no_uncommitted_change") is not True:
        raise OutcomeAccessRefused(f"outcomes are not read: {PLAN_FILE} has an uncommitted change, staged or not, or is not "
                                   "in HEAD's tree; the plan must be the committed one (an amendment is made in the "
                                   "plan's Deviations log and committed)")
    if state.get("freeze_commit_is_an_ancestor_of_head") is not True:
        raise OutcomeAccessRefused(f"outcomes are not read: the freeze commit {state.get('freeze_commit')} is not an "
                                   f"ancestor of HEAD {state.get('head')}, so this checkout is not on the frozen plan's "
                                   "history")
    if reader is None:
        reader = panel.load_outcomes
    if reader is ps.read_listed_outcomes or getattr(reader, "func", None) is ps.read_listed_outcomes:
        raise OutcomeAccessRefused("outcomes are not read: power_simulation.read_listed_outcomes is the power "
                                   "simulation's reader of listed never-treated units, and the simulation route is never "
                                   "taken through this door")
    if not callable(reader):
        raise OutcomeAccessRefused(f"outcomes are not read: the reader is a {type(reader).__name__}, which cannot be "
                                   "called")
    frame = reader(purpose=POST_FREEZE_PURPOSE)
    if not isinstance(frame, pd.DataFrame):
        raise OutcomeAccessRefused(f"outcomes are not passed on: the reader returned a {type(frame).__name__}, not a "
                                   "DataFrame")
    module = getattr(reader, "__module__", None) or type(reader).__module__
    qualname = getattr(reader, "__qualname__", None) or type(reader).__qualname__
    record = {"purpose_passed": POST_FREEZE_PURPOSE,
              "gate_file": gate.name, "gate_file_existed": True,
              "authorization_variable": AUTH_ENV, "authorization_variable_was_1": True,
              "freeze_commit_required": FREEZE_COMMIT, "approved_specification_commit": APPROVED_SPECIFICATION_COMMIT,
              "plan_state": dict(state),
              "reader": {"module": str(module), "qualified_name": str(qualname)},
              "frame_shape": [int(frame.shape[0]), int(frame.shape[1])],
              "frame_columns": [str(c) for c in frame.columns],
              "frame_dtypes": [[str(c), str(t)] for c, t in zip(frame.columns, frame.dtypes)],
              "frame_fingerprint": frame_fingerprint(frame),
              "frame_fingerprint_means": ("sha256 of the outcome frame as the reader returned it, by "
                                          "run_outcomes.frame_fingerprint: its column names and types, its number of rows "
                                          "and every row's values, whatever their order; no value is shown"),
              "read_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return OutcomesRead(frame=frame, record=record)


# ======================================================================================================================
# main: the registry as a list (no design is built, no outcome is read)
# ======================================================================================================================

# What a stated need is, as the needs texts read after session 26 (D-117 settled the supplementary outcomes, row C's price
# series and the ownership of rows U and C; D-119 described that ownership type and settled the inventory's history for
# inventory_against_sales). A test checks that no needs text of a built entry names a caller's choice.
BUILT_IS_NOT_READY = (
    "'built' means the builder and the estimator compose on invented inputs, nothing more. A built entry with a non-empty "
    "needs_before_research_data still needs those inputs from the caller before it can run on research data. They are "
    "inputs built by named functions from named files under rules the plan and Joe's rulings state, row C's fiber shares "
    "(December filings, D-107) among them. No needs text of a built entry names an element as the caller's choice; the "
    "last one so named, which history of the inventory is supplied to inventory_against_sales, was settled by Joe on "
    "2026-11-20 (D-119) as the inventory as built, the load history underlying the headline design, which the registry "
    "supplies as RunInputs.side.dose. Some needs carry a condition that "
    "cannot be checked before outcomes are read (whether row U's flags frame covers every outcome unit-year) or before a "
    "check passes (the per-state reconstruction check, before a scenario's work is used in that state), and row U's flags "
    "over step U3's window rest on the session's reading of that window, which Joe may strike.")


def registry_document() -> dict:
    return {"what_this_is": ("The registry of every run the pre-analysis plan lists on outcomes, in its order of unblinding, "
                             "with each run's plan section, sets, design builder, estimator, labels and status. A list only: "
                             "no design is built for it and no outcome, price, revenue or bill is read. The plan was frozen "
                             "on Joe's explicit approval on 2026-11-20 at commit ea426c4 (approved specification ed3a2ff); "
                             "it is internally frozen and not externally preregistered. When this registry was last brought "
                             "to the code, on 2026-11-20 (session 27), the gate file GATE1_SIGNED did not exist and "
                             "access to outcomes had not been authorized. A status of 'built' means "
                             "the builder and the estimator compose on invented inputs "
                             "(tests/test_run_outcomes_invented.py), nothing more. Row M is out of scope for this freeze "
                             "by Joe's ruling of 2026-11-19 (D-109) and is listed after the executable order of "
                             "unblinding, not in it."),
            "built_by": "pipeline/analysis/run_outcomes.py",
            "statuses": {BUILT: "design builder and estimator exist and compose on invented inputs",
                         DESIGN_ONLY: "a builder exists; what is missing is named",
                         NEEDS_PACKAGE: "the pinned package is not installed",
                         BLOCKED: "the run is defined and something named stops it",
                         NOT_BUILT: "the plan lists the run and no module covers it",
                         OUT_OF_SCOPE: ("out of scope for this freeze by Joe's ruling of 2026-11-19 (D-109): not run, in "
                                        "no executable order of unblinding and in no built count; its code is dormant")},
            "outcome_access": (f"load_outcomes_after_the_freeze is the only door to outcomes. It refuses in words a "
                               f"purpose other than {POST_FREEZE_PURPOSE!r} (panel.load_outcomes' exempt purposes, "
                               f"construction QA and the power simulation, are never taken through it), then refuses "
                               f"unless {Path(panel.GATE_FILE).name} exists, then unless {AUTH_ENV}=1, then unless "
                               f"{PLAN_FILE} is committed with no uncommitted change and the freeze commit "
                               f"{FREEZE_COMMIT[:7]} is an ancestor of HEAD, and it refuses "
                               "power_simulation.read_listed_outcomes as a reader. Only then does it call the reader, "
                               f"panel.load_outcomes by default, once, with purpose={POST_FREEZE_PURPOSE!r} and nothing "
                               "else, and it returns the frame untouched with a record of how it was read that carries no "
                               "outcome value. The gate file is created only on Joe's separate authorization to access "
                               "outcomes. No other path in this module loads "
                               "outcomes, and every runner takes its outcome frame as an argument."),
            "counts_by_status": {s: sum(1 for e in REGISTRY if e.status == s) for s in STATUSES},
            "order_of_unblinding": [e.id for e in ORDER_OF_UNBLINDING],
            "order_of_unblinding_means": ("the executable order: every entry but those out of scope for this freeze, in "
                                          "the plan's order; run_all runs these and no other"),
            "out_of_scope_for_this_freeze": {"count": len(OUT_OF_SCOPE_FOR_THIS_FREEZE),
                                             "ids": [e.id for e in OUT_OF_SCOPE_FOR_THIS_FREEZE],
                                             "ruling": "Joe, 2026-11-19 (D-109)"},
            "built_is_not_ready": BUILT_IS_NOT_READY,
            "built_entries_with_needs": sum(1 for e in REGISTRY if e.status == BUILT and e.needs),
            "built_entries_with_needs_ids": [e.id for e in REGISTRY if e.status == BUILT and e.needs],
            "built_entries_with_stopped_steps": sum(1 for e in REGISTRY if e.stopped_on_research_inputs),
            "built_entries_with_stopped_steps_ids": [e.id for e in REGISTRY if e.stopped_on_research_inputs],
            "stopped_steps_means": ("a built entry composes on invented inputs; a step listed in its "
                                    "stopped_on_research_inputs cannot run on the real quantity files until Joe rules or "
                                    "authorizes what it names"),
            "entries": [e.as_record() for e in REGISTRY]}


def main() -> int:
    doc = registry_document()
    w = max(len(e.id) for e in REGISTRY)
    print(f"{'id':<{w}}  {'status':<29}  plan section")
    for e in REGISTRY:
        print(f"{e.id:<{w}}  {e.status:<29}  {e.section}")
    print(doc["counts_by_status"])
    OUT.write_text(json.dumps(doc, indent=1) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
