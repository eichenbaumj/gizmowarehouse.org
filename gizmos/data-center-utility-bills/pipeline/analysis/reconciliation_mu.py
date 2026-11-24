#!/usr/bin/env python3
"""Reconciliation rows M (Meeks, Pless, Qi and Wang) and U (Ryu and Hiatt): each step a function that takes its outcome
as an argument (PREANALYSIS.md, "The reconciliation rows (reported first, whatever they show)").

Reads NO price. Every step takes the outcome frame as an argument (utility_id_eia, state, year, value: the residential
price LEVEL, logged here) and opens no file to get it. `main()` reads quantity columns only (ownership, customers) and
writes a quantity-side summary to data/frozen/reconciliation_mu_design.json.

Where each element of the papers' specifications comes from
-----------------------------------------------------------
The plan fixes the unit, years, treatment rule, published numbers, bands and the sentences. For row M every element
below was checked in session 21 against the paper itself, "Who Pays for Growth? Evidence from Data Centers and the
Grid", Meeks, Pless, Qi and Wang, the SSRN copy dated 2026-10-23 on its title page
(docs/research/papers/meeks_pless_qi_wang_ssrn6967558/ssrn-6967558.pdf, read through pdftotext; the findings table is
docs/gate1/bounded-read-row-m-2026-11-19.md). Its page numbers are the paper's printed page numbers (SI-n for the online
appendix). That the file is the revision the plan cites (MIT CEEPR WP 2026-13r) is likely and not established; every
number the plan attributes to it matches. For row U every element below was checked in session 20 against the
paper itself (docs/research/papers/ryu_hiatt_usc/2026-05-22 Data Center Entry and US Electricity Prices.pdf, read
through pdftotext; the findings table is docs/gate1/bounded-read-row-u-2026-11-19.md). Page numbers for row U are the
paper's printed page numbers.

Row M, settled by the paper (constants MEEKS_* below, each with its printed page; file dated 2026-10-23):
  - Callaway and Sant'Anna group-time effects with the improved doubly robust step of Sant'Anna and Zhao, never-treated
    utility-state pairs as the only comparison group, an overall effect by eq. 15 (Sec. 5, pp. 20-21, eqs. 13-15). No
    software is named; "CSDID" (p. 20) is the paper's abbreviation, and no package's defaults are taken from it.
  - Standard errors clustered by utility-state pair (p. 20; Tables 2 to 4 notes, pp. 47-49), which is the unit.
  - Window 2010-2024 (p. 18); pairs first treated before 2010 are dropped (p. 20), the first entry being the earliest
    over the vendor's whole history (p. 18).
  - Outcome: log average residential price, revenue over sales, the bundled-service price (Sec. 4.1, p. 15; SI-3), in
    2024 dollars by the CPI (p. 15). A common deflator cancels from every group-time comparison of logs (each compares
    the same two years for treated and comparison units), so no deflator is applied; this is arithmetic, not a choice.
  - Ownership: separate runs with the treated group of one ownership type and ALL never-treated pairs as comparisons
    (Table 3 notes, p. 48); "public" is federal, state, municipal and political subdivision utilities (p. 16).
  - The contiguous United States (p. 18); no customer floor (none stated); utilities that ever file the EIA-861 Short
    Form are excluded (p. 15; again p. 21); pairs must serve residential, commercial and industrial customers and have
    "a retail component" (p. 21).
  - The 5 MW threshold, strictly above (p. 18). HOW it is counted is NOT settled: the paper sums newly activated
    capacity over a county-year (p. 18), the plan's row reads one data center above 5 MW, and that difference is with
    Joe. Both readings stay expressible (reconciliation_treatment.first_year_above_size, `counting`, no default).
  NOT settled by the paper (each a required field of MeeksSpec with no default; the candidates are in its docstring):
  covariates in the doubly robust step; aggregation weights; the error method; anticipation; how an unbalanced panel
  enters; whether pairs first treated after the window are comparisons; whether DC is in; the years over which the
  Short Form "ever" is read; the level and test of the three-class rule; what "a retail component" means; how a cohort
  first treated in the window's first year is handled; estimation weights. Treatment arguments (size column, territory
  vintage, county-year counting) and row M's ownership pick are required arguments of their own functions. Row U's
  ownership classes are settled (Joe, 2026-11-20, D-117 and D-119; adopted_row_u_ownership_classes).

Row U, the paper's specification, settled by the paper (constants RYU_* below, each with its page):
  - ln(residential price) on ln(DC MW + 1), DC MW the cumulative operating capacity in the utility's territory in the
    year (eq. p. 8 Sec. 3.3; Table A3 note p. 23); utility and year fixed effects (Table A3 col. 1, p. 23); clustered
    by state, 51 clusters (Table A3, p. 23); utility-state-years 2015-2024 (p. 6 Sec. 2.2); a multi-state utility's
    capacity identical in each of its states (p. 6 Sec. 2.2 and p. 8 Sec. 3.3); no controls in the pooled column we
    compare with (Table A4a, p. 25).
  - Ownership: cooperative, municipal and investor-owned betas; political subdivisions, state and federal utilities
    enter the pooled regression only (p. 8 Sec. 3.3).
  - Utilities that appear in fewer than 3 years of the panel are dropped (p. 6 Sec. 2.2), and only utilities reporting
    ownership-type data are kept (same sentence). Short Form (861-S) filers are excluded (endnote 10, p. 17).
Row U, this study's approximations (constants RYU_OURS_*, gathered with their labels in RYU_APPROXIMATIONS). OURS and
not the paper's: each element the paper does not state, adopted by Joe on 2026-11-19 (D-107, accepting D-106's R5).
Each is the row's specification, and RyuSpec.check refuses another value in words: separate regressions on each of the
three ownership classes; the three-year rule counted after every other restriction; the 51 jurisdictions read as the 50
states and the District of Columbia; capacity dated by the inventory's site-year load; the outcome
res_price_default_service; unweighted; the usual clustered correction for the number of clusters and parameters.
U0's assignment (Joe, 2026-11-19, D-109): the smallest containing polygon over every polygon of the layer, the type not
read, OUR labelled approximation (reconciliation_treatment.ROW_U_POLYGON and ROW_U_POLYGON_LABEL). The paper gives
retail providers priority over wholesale-only territories; this layer's TYPE field does not establish which polygons
are retail, so that priority is not applied and exact reproduction of the paper's assignment is unavailable. The rule
is the same as row C's at C0 to C2, so their agreement is one rule applied twice and not independent validation
(rt.ROW_U_C_COINCIDENCE). The sites associated with four of the layer's entity types are listed and decide nothing
(rt.entity_type_list). The Short Form exclusion (short_form_exclusion, a required field with no default) was adopted by
Joe on 2026-11-20 (D-115): a utility-state-year leaves where a record shows a Short Form filing (a row in the Short Form
table that year or, for 2019, a flag of true in the operational file), every other unit-year is kept with no record of
a filing, and the three-year count is taken after the exclusion. In this module's terms that is 'unit_years_filed'
(U_SHORT_FORM_ADOPTED_CODE) with flags built by short_form_filers.adopted_row_u_flags; the 2019 exclusion is
explicitly incomplete (U_SHORT_FORM_ADOPTED_LABEL). Outcome availability is never used in place of the Short Form
exclusion (D-109). Row U's ownership classes were settled by Joe on 2026-11-20 (D-117 and D-119). The class comes
from the panel's entity type, the utility-level modal reported type carried across the panel to every year and state
of the utility, and not the latest year-by-year EIA classification (D-119, OWNERSHIP_DESCRIPTION_D119). The code reads
it as the last nonmissing value of the panel's entity_type column over the quantity panel's years 2001 to 2025 (D-117),
which on this panel returns that same type for every utility-state. One class for every year of the unit, mapped by
U_MAP unchanged, a unit with no type in any year left with no class (OWNERSHIP_SPECIFICATION_D117,
OWNERSHIP_PICK_D117, adopted_row_u_ownership_classes). What the panel's entity_type column is, and Joe's ruling on it
(D-119, with no further raw-data investigation), are in PANEL_ENTITY_TYPE_STATEMENT. Exact reproduction is unavailable for the elements in RYU_UNAVAILABLE, and every result
says so.
What may be claimed (Joe, 2026-11-19, D-107 and D-109). Comparison-only, by his ruling of 2026-11-19 (D-109): the
pooled estimate at U0 is returned with the paper's figure and band beside it as a comparison band and no verdict
(U_POOLED_COMPARISON_LABEL); the ownership estimates at every step are a comparison under our specification
(U_OWNERSHIP_COMPARISON_LABEL), the paper's split carrying six controls we do not build. u1_sentence returns the adopted
U1 sentences, chosen by one fact (whether our co-op and municipal coefficients are each above our investor-owned one, in
our estimates without controls), each followed by U1_CONTROLS_SENTENCE. Every row U result carries the missing-coverage
qualification (rt.MISSING_COVERAGE_QUALIFICATION). No code path for row U returns a reproduction verdict.

Estimators here are written in numpy and checked in the tests against brute-force dummy-variable regressions:
  callaway_santanna()   the no-covariate group-time estimator (equal to the doubly robust one with a constant only),
                        never-treated comparisons, the overall effect by "simple" or "group" weights, the influence
                        function by unit (clustering by utility-state pair is clustering by unit), with the term for
                        estimated weights; or the multiplier bootstrap on that influence function.
  twfe()                least squares with utility and year effects removed exactly (utility means swept, year dummies
                        kept as regressors), clustered by a grouping.
A numerical failure (a cell with no comparison unit, a regressor with no variation, too few clusters, a price that is
not positive) is reported in words in the result, never dropped.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.analysis import reconciliation_treatment as rt  # noqa: E402

KEY = ["utility_id_eia", "state"]
# Paths main() reads and writes (module names so that a test can point them at invented files).
INTERIM = ROOT / "data" / "interim"
FROZEN = ROOT / "data" / "frozen"
SHORT_FORM_FILER_TABLE = INTERIM / "reconciliation_short_form_filers.parquet"   # written by the one authorized read (D-113)
SHORT_FORM_FLAGS = INTERIM / "reconciliation_short_form_flags.parquet"          # the 2019 flags, read by name
DESIGN_SUMMARY = FROZEN / "reconciliation_mu_design.json"
DEFAULT_SERVICE ="res_price_default_service"      # bundled revenue over bundled sales (pipeline/electricity/panel.py)
DELIVERY_INCLUSIVE = "res_price"                     # competitive supply added for delivery-only customers

CONTIGUOUS_48 = tuple(sorted({"AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "ID", "IL", "IN", "IA", "KS", "KY",
                              "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
                              "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
                              "WV", "WI", "WY"}))
CONTIGUOUS_48_AND_DC = tuple(sorted(CONTIGUOUS_48 + ("DC",)))
FIFTY_STATES_AND_DC = tuple(sorted(CONTIGUOUS_48_AND_DC + ("AK", "HI")))

M_CLASSES = ("investor_owned", "public", "cooperative")
U_CLASSES = ("cooperative", "municipal", "investor_owned")

# The plan's printed numbers and fixed bands. Row M: pooled and investor-owned from PREANALYSIS.md row M; public and
# cooperative are not printed in the plan. All four found in the paper (file dated 2026-10-23): pooled residential,
# Table 2 col. 2, p. 47; investor-owned, public and cooperative residential, Table 3 Panels A to C col. 2, p. 48. Row U: the figures the plan prints, each found in the paper (session 20): pooled without controls,
# Table A4a "No controls" column, p. 25; pooled with controls, Table A3 col. 1, p. 23, and Table A4a, p. 25 (its
# standard error, 0.0026, is printed there and not in the plan); by ownership with full controls, Table A3a Panel B
# col. 1, p. 24, and Table A4b col. A, p. 25. The paper prints no ownership figures without controls.
PAPER_M = {"pooled": (0.021, 0.008), "investor_owned": (0.052, 0.014), "public": (0.017, 0.015),
           "cooperative": (-0.007, 0.010)}
BAND_M = (0.005, 0.037)            # "pooled estimate between 0.5% and 3.7%" (log points; the paper reports 0.021 as 2.1%)
# The paper's printed sample sizes (reported beside ours, never used as a target; file dated 2026-10-23).
PAPER_M_N = {"observations": 14733,                  # p. 19; Table 2, p. 47
             "utility_state_pairs": 1048,            # p. 19
             "utilities": 973,                       # p. 19; Table 2, p. 47
             "states": 48,                           # p. 19
             "treated_utilities": 112,               # fn. 19, p. 22 (utilities, not pairs)
             "investor_owned_run_observations": 13585, "investor_owned_run_utilities": 900,   # Table 3 Panel A, p. 48
             "public_run_observations": 13607, "public_run_utilities": 911,                   # Table 3 Panel B, p. 48
             "cooperative_run_observations": 13687, "cooperative_run_utilities": 912}         # Table 3 Panel C, p. 48

# Row M elements the paper settles (session 21 bounded read; page = printed page; every one from the file dated
# 2026-10-23, docs/gate1/bounded-read-row-m-2026-11-19.md). MeeksSpec.check and run_m_step refuse any other value.
MEEKS_FILE = ("Meeks, Pless, Qi and Wang, 'Who Pays for Growth? Evidence from Data Centers and the Grid', "
              "SSRN 6967558, dated 2026-10-23")
MEEKS_FILE_DATE = "2026-10-23"
MEEKS_WINDOW = (2010, 2024)                 # "to 2010–2024" (p. 18)
MEEKS_ESTIMATOR = "callaway_santanna_never_treated_improved_doubly_robust"   # pp. 20-21, eqs. 13-15
MEEKS_COMPARISON = "never_treated"          # "compares ... to the corresponding change among never-treated pairs" (p. 21)
MEEKS_OWNERSHIP_COMPARISONS = "all_never_treated_any_ownership"   # Table 3 notes, p. 48
MEEKS_CLUSTER = "utility_state_pair"        # "clustered at the utility-state-pair level" (p. 20; Tables 2-4, pp. 47-49)
MEEKS_DROPS_FIRST_TREATED_BEFORE = 2010     # "we drop pairs whose first large data center activation occurred before" 2010 (p. 20)
MEEKS_SIZE_THRESHOLD_MW = 5.0               # "newly activated capacity above 5 MW", strictly above (p. 18)
# How the 5 MW is counted is NOT settled: the paper sums a county-year (p. 18), the plan's row reads one data center;
# the difference is with Joe. Both readings are accepted as the treatment's `counting` (no default).
MEEKS_SIZE_COUNTING_READINGS = {"county_year_new_capacity": "the paper's (p. 18): capacity activated in a county in a "
                                                            "year, summed over its facilities",
                                "site": "the plan row's wording: one data center above 5 MW"}
MEEKS_SIZE_COUNTING_STATUS = ("not settled: the paper (p. 18, file dated 2026-10-23) sums newly activated capacity by "
                              "county-year and the plan's row M reads one data center above 5 MW; the difference is with "
                              "Joe, and the treatment's counting is the caller's explicit argument")
MEEKS_PUBLIC_ENTITY_TYPES = ("Federal", "Municipal", "Political Subdivision", "State")   # p. 16
MEEKS_CUSTOMER_FLOOR = None                 # none stated; the Short Form rule is the only size screen (fn. 11, p. 15)
MEEKS_EXCLUDES_SHORT_FORM = True            # "We exclude utilities that ever file the EIA-861 Short Form" (p. 15; p. 21)
MEEKS_SHORT_FORM_LEVEL = "utility_ever"     # utilities, ever: all of a filer's state pairs in all years (p. 15)
MEEKS_REQUIRES_THREE_CLASSES = True         # "require pairs to serve residential, commercial, and industrial customers" (p. 21)
MEEKS_REQUIRES_RETAIL_COMPONENT = True      # "We retain only utility-state pairs with a retail component" (p. 21)
MEEKS_JURISDICTION_CHOICES = ("CONTIGUOUS_48", "CONTIGUOUS_48_AND_DC")   # "the contiguous U.S." (p. 18); "48 states" (p. 19); DC not stated
MEEKS_OUTCOME = DEFAULT_SERVICE             # log revenue over sales, bundled service (p. 15; SI-3; Table 2 notes, p. 47); M0 and M1
# Open elements the read showed row M needs, each a required MeeksSpec field; the candidates the code accepts.
MEEKS_THREE_CLASSES_LEVELS = ("unit", "unit_year")
MEEKS_THREE_CLASSES_TESTS = ("positive_sales", "positive_customers", "positive_sales_and_customers")
MEEKS_RETAIL_COMPONENT_RULES = ("implied_by_a_residential_price", "flag")
MEEKS_WINDOW_START_COHORT = ("left_out_and_counted", "base_year_before_window")
MEEKS_WEIGHTINGS = ("unweighted",)
if MEEKS_WINDOW[0] != MEEKS_DROPS_FIRST_TREATED_BEFORE:      # the estimator drops units first treated before window[0]
    raise ValueError("row M's window starts in 2010 and pairs first treated before 2010 are dropped (pp. 18, 20)")
PAPER_U = {"pooled_no_controls": (0.0095, 0.0026), "pooled_with_controls": (0.0094, 0.0026),
           "cooperative_with_controls": (0.0067, 0.0024), "municipal_with_controls": (0.0080, 0.0044),
           "investor_owned_with_controls": (0.0006, 0.0043)}
BAND_U = (0.0043, 0.0147)
# The paper's printed sample sizes for the 2015-2024 window (reported beside ours, never used as a target).
PAPER_U_N = {"pooled_observations": 16163,           # Table A3 col. 1 p. 23; Table A4a p. 25 (both columns)
             "pooled_utilities": 1798,               # Table A3 col. 1 p. 23; p. 6 Sec. 2.2
             "clusters": 51,                         # Table A3 heading text p. 23 ("51 clusters")
             "cooperative_observations": 7203,       # Table A3a Panel B p. 24; Table A4b p. 25
             "municipal_observations": 6384,         # same
             "investor_owned_observations": 1858}    # same

# Row U elements the paper settles (session 20 bounded read; page = printed page number of the PDF).
RYU_WINDOW = (2015, 2024)               # "EIA Form 861 annual utility revenue and sales, 2015-2024" (p. 6, Sec. 2.2)
RYU_CLUSTER = "state"                   # "Standard errors are clustered at the state level" (p. 8, Sec. 3.3; Table A3)
RYU_UNIT_EFFECT = "utility_id_eia"      # "Utility FE: Yes", "Utility-state FE: No" (Table A3 col. 1, p. 23)
RYU_N_JURISDICTIONS = 51                # "1,798 utilities across 51 jurisdictions" (p. 6, Sec. 2.2); 51 clusters (p. 23)
RYU_MIN_YEARS = 3                       # "dropping utilities that appear in fewer than 3 years of the panel" (p. 6)
RYU_MIN_YEARS_LEVEL = "utility"         # the same sentence counts utilities, not utility-states
RYU_EXCLUDES_SHORT_FORM = True          # 861-S filers "were excluded from the residential-rate regressions" (endnote 10, p. 17)
RYU_KEEPS_ONLY_REPORTED_OWNERSHIP = True  # "restricting to bundled-service utilities reporting ownership-type data" (p. 6)
# Not settled by the paper: whether a Short Form filer leaves for the years it filed or for good. The codes
# RyuSpec.short_form_exclusion accepts are below. Joe adopted the rule on 2026-11-20 (D-115); its code is
# 'unit_years_filed' (U_SHORT_FORM_ADOPTED_CODE), with the flags from short_form_filers.adopted_row_u_flags. The other two
# codes stay accepted here as they were, for tests on invented inputs. The registry narrows them for research execution
# (session 27): run_outcomes._row_u_guard refuses, on RunInputs.reconciliation_u_inputs_are ==
# RESEARCH_DATA_AFTER_THE_FREEZE, any code but U_SHORT_FORM_ADOPTED_CODE and any spec not equal to
# ryu_spec(U_SHORT_FORM_ADOPTED_CODE); nothing in this module narrows them.
SHORT_FORM_RULES = ("unit_years_filed", "utilities_ever_filed", "none_in_outcome_frame")

# Row U: this study's approximations, OURS and not the paper's, adopted by Joe on 2026-11-19 (D-107, accepting D-106's
# R5). Each is the row's specification; RyuSpec.check refuses another value in words.
OURS_D107 = "ours, not the paper's: this study's approximation, adopted by Joe on 2026-11-19 (D-107)"
RYU_OURS_OWNERSHIP_SPEC = "separate_subsamples"            # one regression per class, each with its own effects
RYU_OURS_MIN_YEARS_COUNTED_AFTER = "every_other_restriction"
RYU_OURS_MIN_YEARS = (RYU_MIN_YEARS, RYU_MIN_YEARS_LEVEL, RYU_OURS_MIN_YEARS_COUNTED_AFTER)
RYU_OURS_JURISDICTIONS = FIFTY_STATES_AND_DC
RYU_OURS_MW_SOURCE = "site_year_load"                       # reconciliation_treatment.cumulative_mw
RYU_OURS_POLYGON = dict(rt.ROW_U_POLYGON)                   # reconciliation_treatment.assign_polygon_smallest
RYU_OURS_OUTCOME = DEFAULT_SERVICE
RYU_OURS_WEIGHTING = "unweighted"
RYU_OURS_SS_CORRECTION = "clusters_and_parameters"          # G/(G-1) x (N-1)/(N-K), K counting the absorbed effects
RYU_APPROXIMATIONS = {
    "ownership_estimates": {"value": RYU_OURS_OWNERSHIP_SPEC, "label": OURS_D107,
                            "paper": "\"separate β coefficients for the three largest ownership categories\" (p. 8); "
                                     "the form of the regressions is not stated"},
    "three_year_rule_counted": {"value": RYU_OURS_MIN_YEARS_COUNTED_AFTER, "label": OURS_D107,
                                "paper": "\"dropping utilities that appear in fewer than 3 years of the panel\" (p. 6); "
                                         "when the count is taken is not stated"},
    "jurisdictions": {"value": "the 50 states and the District of Columbia", "label": OURS_D107,
                      "paper": "\"51 jurisdictions\" (p. 6), \"51 clusters\" (p. 23); not listed"},
    "capacity_dating": {"value": RYU_OURS_MW_SOURCE + " (the inventory's estimated load by site and year)",
                        "label": OURS_D107,
                        "paper": "cumulative operating capacity of matched facilities in a year (p. 5; p. 23); which "
                                 "year a facility starts to count is not stated"},
    "assignment": {"value": rt.ROW_U_POLYGON_LABEL,
                   "label": ("ours, not the paper's: this study's labelled approximation, adopted by Joe on 2026-11-19 "
                             "(D-109, in place of the retail-first form of D-107); the paper's retail priority is not "
                             "applied"),
                   "paper": "the polygon that \"strictly contains the facility's location, prioritizing retail providers "
                            "over wholesale-only territories\" (p. 5)"},
    "outcome_columns": {"value": RYU_OURS_OUTCOME + " (bundled revenue over bundled sales)", "label": OURS_D107,
                        "paper": "revenue divided by sales at bundled-service utilities (p. 6); the columns are not named"},
    "weights": {"value": RYU_OURS_WEIGHTING, "label": OURS_D107, "paper": "none stated; the equation (p. 8) has none"},
    "standard_errors": {"value": RYU_OURS_SS_CORRECTION, "label": OURS_D107,
                        "paper": "clustered by state (p. 8; p. 23); the small-sample factor and software are not stated"},
}
# Outcome 3 of the bounded read: exact reproduction unavailable (D-106 section 6). Said in every result.
RYU_UNAVAILABLE = (
    "the paper's small-sample factor and software are not stated, so exact reproduction of its standard errors is "
    "unavailable",
    "the paper's capacity is a vendor's utility power capacity on a purchased list (S&P Global 451 Research, p. 5); "
    "ours is estimated load from permits and public sources",
    "the vintage of the paper's territory layer is not given; ours is a later copy from a different endpoint",
    "the paper gives retail providers priority over wholesale-only territories; this layer's TYPE field does not "
    "establish which polygons are retail, so that priority is not applied and exact reproduction of the paper's "
    "assignment is unavailable (Joe, 2026-11-19, D-109)",
    "the paper's ownership split is printed with six controls (Table A3, p. 23) that are not built here",
    "the paper tests no difference between ownership coefficients, only each against zero",
)
OWNERSHIP_SPECS = (RYU_OURS_OWNERSHIP_SPEC,)
WEIGHTINGS = (RYU_OURS_WEIGHTING,)

M0_NOT_REPRODUCED = "On an open facility list the closest published design does not return its published answer"

# What row U may claim (Joe, 2026-11-19, D-107 and D-109). Comparison-only; no row U result carries a reproduction
# verdict.
U_OWNERSHIP_COMPARISON_LABEL = (
    "Comparison-only, by Joe's ruling of 2026-11-19 (D-109). A comparison under our specification, to which no "
    "reproduction claim attaches. Our ownership estimates come from separate regressions with no controls; the paper's "
    "printed ownership split (Table A3a Panel B, p. 24; Table A4b, p. 25) carries six controls that are not built here "
    "(Table A3, p. 23). The ordering here therefore counts neither as reproducing the paper's controlled result nor as "
    "failing to (Joe, 2026-11-19, D-107). The three coefficients and their errors are shown beside the paper's.")
U_POOLED_COMPARISON_LABEL = (
    "Comparison-only, by Joe's ruling of 2026-11-19 (D-109). Our pooled estimate under our specification is shown with "
    f"the paper's no-controls figure, {PAPER_U['pooled_no_controls'][0]} ({PAPER_U['pooled_no_controls'][1]}; Table A4a, "
    f"p. 25), and the band {BAND_U[0]} to {BAND_U[1]} beside it as a comparison band. No verdict is given, whether the "
    "estimate falls inside the band or outside it. Our regressor is the inventory's estimated load, not the paper's "
    "vendor capacity, and U0's assignment is our smallest-polygon approximation, not the paper's retail-first "
    "assignment.")
# U1's sentences, adopted by Joe on 2026-11-19 (D-109) as drafted in docs/gate1/rows-u-c-reproduction-assessment-
# 2026-11-19.md section 3. One fact chooses between the first two; the third follows either.
U1_SENTENCE_EACH_ABOVE = ("In our estimates without controls, the co-op and municipal coefficients are each above the "
                          "investor-owned one when the inventory's own assignment replaces the polygon.")
U1_SENTENCE_NOT_EACH_ABOVE = ("In our estimates without controls, the co-op and municipal coefficients are not each "
                              "above the investor-owned one when the inventory's own assignment replaces the polygon.")
U1_CONTROLS_SENTENCE = ("The paper estimates its ownership split with six controls that we do not build, so this "
                        "neither confirms nor contradicts its result.")
U1_WORDING_STATUS = ("Adopted by Joe on 2026-11-19 (D-109) as drafted (docs/gate1/rows-u-c-reproduction-assessment-"
                     "2026-11-19.md, section 3). The plan's earlier clause \"or the three are indistinguishable\" went "
                     "with the sentence it was in and is not used; no test of a difference between ownership "
                     "coefficients enters the choice.")
U_SHORT_FORM_NO_SUBSTITUTE = ("Outcome availability (whether a unit-year has a price) is not used in place of the "
                              "paper's Short Form exclusion (Joe, 2026-11-19, D-109).")
U_SHORT_FORM_NOT_APPLIED_LABEL = ("No Short Form exclusion is applied, so this is not the paper's sample, which excludes "
                                  "Short Form filers (endnote 10, p. 17). " + U_SHORT_FORM_NO_SUBSTITUTE)
# The Short Form rule Joe adopted on 2026-11-20 (D-115), in this module's code, and its label. The choices that build the
# flags are in one place, short_form_filers.ADOPTED_ROW_U_CHOICES, supplied by short_form_filers.adopted_row_u_flags.
U_SHORT_FORM_ADOPTED_CODE = "unit_years_filed"
U_SHORT_FORM_ADOPTED_LABEL = (
    "Short Form exclusion as adopted by Joe on 2026-11-20 (D-115): a utility-state-year leaves where a record shows a "
    "Short Form filing, a row in the Short Form table that year or, for 2019, a flag of true in the operational file. "
    "Every other unit-year is kept with no record of a filing, which is no claim about whether it filed. The three-year "
    "count is taken after the exclusion. The 2019 exclusion is explicitly incomplete. The table has no 2019 rows, the "
    "exclusion that year rests on the operational file's flags, and a 2019 unit-year with a missing flag or with no "
    "flags row is kept with no record either way. A missing flag or an absent row does not establish non-filing. The "
    "sample is still not the paper's sample, and the row is comparison-only (D-109). " + U_SHORT_FORM_NO_SUBSTITUTE)
U1_NO_SENTENCE = ("No U1 sentence is returned. An ownership coefficient could not be computed at U1 (see "
                  "numerical_failures), so the fact that chooses the sentence is not known.")
# The order in which row U applies the paper's sample rules that are row filters; the three-year count always comes
# after both and after the window, jurisdiction and missing-price rules (RYU_OURS_MIN_YEARS_COUNTED_AFTER). The order of
# the two filters is the agent's; tests/test_reconciliation_mu_invented.py shows both orders give the same sample.
U_SAMPLE_FILTER_ORDER = ("ownership", "short_form")

# What each step changes (one choice at a time, PREANALYSIS.md). rule = the prefix the treatment's rule must carry.
M_STEPS = {
    "M0": {"window": MEEKS_WINDOW, "price": MEEKS_OUTCOME, "rule": "county_touch|above_5mw",
           "change": "their treatment rule on our inventory"},
    "M1": {"window": MEEKS_WINDOW, "price": MEEKS_OUTCOME, "rule": "verified|above_5mw",
           "change": "the one utility that serves the site in place of every utility touching the county"},
    "M2": {"window": MEEKS_WINDOW, "price": DELIVERY_INCLUSIVE, "rule": "verified|above_5mw",
           "change": "our price with competitive supply added in place of default service only"},
    "M3": {"window": (2010, 2025), "price": DELIVERY_INCLUSIVE, "rule": "verified|above_5mw", "change": "2025 added"},
    "M4": {"window": (2010, 2025), "price": DELIVERY_INCLUSIVE, "rule": "verified|dose_at_least_0.02",
           "change": "our 2% load threshold in place of any site above 5 MW"},
}
U_STEPS = {
    "U0": {"window": RYU_WINDOW, "price": RYU_OURS_OUTCOME, "rule": "polygon_smallest_any_type|" + RYU_OURS_MW_SOURCE,
           "change": ("our smallest-polygon approximation of their assignment rule: the smallest territory polygon that "
                      "strictly contains the site, over every polygon of the layer, the type not read (ours, D-109); "
                      "the paper's priority for retail providers is not applied, the layer's TYPE field not "
                      "establishing which polygons are retail")},
    "U1": {"window": RYU_WINDOW, "price": RYU_OURS_OUTCOME, "rule": "verified|" + RYU_OURS_MW_SOURCE,
           "change": "the inventory's own assignment in place of the polygon"},
    "U2": {"window": RYU_WINDOW, "price": DELIVERY_INCLUSIVE, "rule": "verified|" + RYU_OURS_MW_SOURCE,
           "change": "our delivery-inclusive price in place of bundled-only"},
    "U3": {"window": (2015, 2025), "price": DELIVERY_INCLUSIVE, "rule": "verified|" + RYU_OURS_MW_SOURCE,
           "change": "add the full annual survey for 2025"},
}


@dataclass(frozen=True)
class MeeksSpec:
    """Row M's specification. Every field is required: no defaults. Where the paper settles a field (file dated
    2026-10-23, docs/gate1/bounded-read-row-m-2026-11-19.md), check() refuses any other value in words; every other
    field is an element the paper does not state, the caller's explicit choice, and nothing here decides it. The
    agent's proposals for those fields are in the bounded-read file, labelled ours, for Joe; none is coded as a default.

    Settled by the paper (refused if departed from):
    jurisdictions         CONTIGUOUS_48 or CONTIGUOUS_48_AND_DC: "the contiguous U.S." (p. 18), "48 states" (p. 19).
                          Whether DC is in is NOT stated, so the choice between the two stays the caller's.
    customer_floor        None: the paper states no customer floor (fn. 11, p. 15 gives the Short Form's sales cut).
    exclude_short_form    True: "We exclude utilities that ever file the EIA-861 Short Form" (p. 15; again p. 21), at
                          the level of the utility, all of its state pairs in all years. Needs sample_flags.
    require_three_classes True: "require pairs to serve residential, commercial, and industrial customers" (p. 21).
                          Needs sample_flags.

    Not stated by the paper (required, no default; the candidates the code accepts):
    covariates            () only. The paper names no covariate for the baseline doubly robust step. With no covariates
                          the doubly robust estimator is the difference in mean changes, which is what is built. A
                          non-empty tuple stops in words: the doubly robust step with covariates is NOT built.
    aggregation           "simple" (every post-treatment cell weighted by its cohort's size) or "group" (each cohort's
                          mean post-treatment effect, weighted by cohort size). Eq. 15 (p. 21) writes a cohort weight
                          w_g and does not define it.
    se_method             "influence_function" (analytic, by unit) or "multiplier_bootstrap" (needs bootstrap_draws,
                          bootstrap_weights in {"rademacher", "mammen"} and seed; the standard error is the
                          interquartile range over 1.349). The paper clusters by pair (p. 20) and names no method.
    anticipation          years of anticipation; the base year is g - 1 - anticipation. Not stated.
    unbalanced            "pairwise" (each cell uses the units observed at its base year and its year) or "balance"
                          (only units observed in every window year). Not stated; the paper's 14,733 observations on
                          1,048 pairs (p. 19) are fewer than a balanced 15 years.
    treated_after_window  "never_treated" or "dropped": units first treated after the window's last year. Not stated.
    short_form_years      (first, last): the years over which the Short Form "ever" is read. Not stated. sample_flags
                          must carry short_form_first_year_read and short_form_last_year_read equal to these.
    three_classes_level   "unit" (one flag per utility-state pair) or "unit_year" (a flag each pair-year). Not stated.
    three_classes_test    "positive_sales", "positive_customers" or "positive_sales_and_customers": what "serve"
                          means. Not stated. sample_flags must carry three_classes_test equal to this. (A test by
                          revenue is not offered: it would need revenue, which is not requested.)
    retail_component      "implied_by_a_residential_price" (no separate filter: a pair-year with a residential price
                          has one) or "flag" (sample_flags carries has_retail_component by pair). "a retail component"
                          (p. 21) is not defined.
    window_start_cohort   "left_out_and_counted" (a cohort whose base year falls before the window contributes no cell
                          and is left out, reported in words) or "base_year_before_window" (the outcome's years before
                          the window may serve as base years only, never as cells). The paper does not say whether its
                          price data reach 2009.
    weighting             "unweighted" only. The paper describes weights only for its matched design (SI-6, SI-30).
    """
    covariates: tuple
    aggregation: str
    se_method: str
    anticipation: int
    unbalanced: str
    treated_after_window: str
    jurisdictions: tuple
    customer_floor: int | None
    exclude_short_form: bool
    require_three_classes: bool
    short_form_years: tuple
    three_classes_level: str
    three_classes_test: str
    retail_component: str
    window_start_cohort: str
    weighting: str
    bootstrap_draws: int | None = None       # only with se_method="multiplier_bootstrap"
    bootstrap_weights: str | None = None
    seed: int | None = None

    def check(self) -> None:
        # settled by the paper (file dated 2026-10-23): refused in words
        if tuple(self.jurisdictions) not in (CONTIGUOUS_48, CONTIGUOUS_48_AND_DC):
            raise ValueError("row M's states are the contiguous United States (\"the contiguous U.S.\", p. 18, file "
                             "dated 2026-10-23): jurisdictions must be CONTIGUOUS_48 or CONTIGUOUS_48_AND_DC, whether DC "
                             "is in being the one open choice")
        if self.customer_floor is not MEEKS_CUSTOMER_FLOOR:
            raise ValueError("row M has no customer floor: the paper states none (file dated 2026-10-23); "
                             "customer_floor must be None")
        if self.exclude_short_form is not MEEKS_EXCLUDES_SHORT_FORM:
            raise ValueError("row M excludes utilities that ever file the EIA-861 Short Form, with all their state pairs "
                             "(p. 15, file dated 2026-10-23); exclude_short_form must be True")
        if self.require_three_classes is not MEEKS_REQUIRES_THREE_CLASSES:
            raise ValueError("row M keeps only pairs that serve residential, commercial and industrial customers "
                             "(p. 21, file dated 2026-10-23); require_three_classes must be True")
        # not stated by the paper: the caller's explicit choice among the built candidates
        if tuple(self.covariates):
            raise NotImplementedError("the doubly robust step with covariates is not built: the paper does not name its "
                                      "covariates, and no covariate data are in hand; covariates=() is the only built case")
        if self.aggregation not in ("simple", "group"):
            raise ValueError("aggregation must be 'simple' or 'group'")
        if self.se_method not in ("influence_function", "multiplier_bootstrap"):
            raise ValueError("se_method must be 'influence_function' or 'multiplier_bootstrap'")
        if self.se_method == "multiplier_bootstrap" and (self.bootstrap_draws is None or self.seed is None
                                                         or self.bootstrap_weights not in ("rademacher", "mammen")):
            raise ValueError("the multiplier bootstrap needs bootstrap_draws, seed and bootstrap_weights")
        if self.unbalanced not in ("pairwise", "balance"):
            raise ValueError("unbalanced must be 'pairwise' or 'balance'")
        if self.treated_after_window not in ("never_treated", "dropped"):
            raise ValueError("treated_after_window must be 'never_treated' or 'dropped'")
        if int(self.anticipation) < 0:
            raise ValueError("anticipation must be 0 or more")
        sfy = self.short_form_years
        if (sfy is None or len(tuple(sfy)) != 2 or not all(isinstance(x, (int, np.integer)) for x in sfy)
                or sfy[0] > sfy[1]):
            raise ValueError("short_form_years must be (first, last), two years in order: the years over which the "
                             "Short Form 'ever' is read, which the paper does not state")
        if self.three_classes_level not in MEEKS_THREE_CLASSES_LEVELS:
            raise ValueError(f"three_classes_level must be one of {MEEKS_THREE_CLASSES_LEVELS}: the paper does not say "
                             "whether 'serve' is tested once per pair or each year")
        if self.three_classes_test not in MEEKS_THREE_CLASSES_TESTS:
            raise ValueError(f"three_classes_test must be one of {MEEKS_THREE_CLASSES_TESTS}: the paper does not say "
                             "what 'serve' means")
        if self.retail_component not in MEEKS_RETAIL_COMPONENT_RULES:
            raise ValueError(f"retail_component must be one of {MEEKS_RETAIL_COMPONENT_RULES}: 'a retail component' "
                             "(p. 21) is not defined in the paper")
        if self.window_start_cohort not in MEEKS_WINDOW_START_COHORT:
            raise ValueError(f"window_start_cohort must be one of {MEEKS_WINDOW_START_COHORT}: the paper does not say "
                             "how a cohort first treated in the window's first year is handled")
        if self.weighting not in MEEKS_WEIGHTINGS:
            raise ValueError("weighting must be 'unweighted', the only one built: the paper describes weights only for "
                             "its matched design")


@dataclass(frozen=True)
class RyuSpec:
    """Row U's specification. Every field is required, with no default, so a caller states each one; every field but
    short_form_exclusion has one accepted value, and check() refuses any other in words. Session 20's bounded read of
    the paper is docs/gate1/bounded-read-row-u-2026-11-19.md; ryu_spec() builds the specification from the constants.

    ownership_spec   RYU_OURS_OWNERSHIP_SPEC, "separate_subsamples": one regression per class, each with its own
                     utility and year effects. Ours, adopted by Joe on 2026-11-19 (D-107). The paper: "The by-ownership
                     specification estimates separate β coefficients for the three largest ownership categories" (p. 8,
                     Sec. 3.3) and prints a sample size for each class and a control whose coefficient differs by class
                     (Table A3a Panel B, p. 24); it does not state the form.
    ss_correction    RYU_OURS_SS_CORRECTION, "clusters_and_parameters": G/(G-1) x (N-1)/(N-K), K counting every
                     coefficient including the absorbed utility and year effects. Ours (D-107); the paper names no
                     software or correction, so exact reproduction of its errors is unavailable.
    min_years        RYU_OURS_MIN_YEARS, (3, "utility", "every_other_restriction"). The count (3) and the level
                     (utility) are the paper's (p. 6, Sec. 2.2); counting after every other restriction is ours (D-107).
    jurisdictions    RYU_OURS_JURISDICTIONS, the 50 states and the District of Columbia: ours (D-107), the paper's
                     count of 51 (p. 6; p. 23) read as that list.
    short_form_exclusion  ADOPTED by Joe on 2026-11-20 (D-115) as U_SHORT_FORM_ADOPTED_CODE, "unit_years_filed", with
                     sample_flags from short_form_filers.adopted_row_u_flags: a unit-year leaves where a record shows a
                     Short Form filing, every other unit-year is kept with no record of a filing, and the three-year
                     count comes after (U_SHORT_FORM_ADOPTED_LABEL). The paper excludes 861-S filers (endnote 10,
                     p. 17) without saying for which years. The codes accepted: "unit_years_filed" (drop the unit-years
                     flagged `short_form` in sample_flags: KEY, year, short_form), "utilities_ever_filed" (drop every
                     unit-year of a utility flagged in any window year), or "none_in_outcome_frame" (the caller states
                     that the outcome frame holds no Short Form unit-year; recorded as the caller's statement and not
                     checked here; NO Short Form exclusion is applied and the sample is labelled as not the paper's
                     sample). The two codes other than the adopted one stay accepted as before; nothing here narrows
                     them. Whether a unit-year has a price (outcome availability) is never used in place of the
                     paper's exclusion (Joe, 2026-11-19, D-109).
    weighting        RYU_OURS_WEIGHTING, "unweighted": ours (D-107); the paper's equation (p. 8) carries no weights.
    """
    ownership_spec: str
    ss_correction: str
    min_years: tuple | None
    jurisdictions: tuple
    short_form_exclusion: str
    weighting: str

    def check(self) -> None:
        bad = []
        if self.ownership_spec != RYU_OURS_OWNERSHIP_SPEC:
            bad.append(f"ownership_spec is {self.ownership_spec!r}; row U's specification is {RYU_OURS_OWNERSHIP_SPEC!r}, "
                       f"separate regressions on each of the three ownership classes")
        if self.ss_correction != RYU_OURS_SS_CORRECTION:
            bad.append(f"ss_correction is {self.ss_correction!r}; row U's specification is {RYU_OURS_SS_CORRECTION!r}, "
                       f"the usual clustered correction for the number of clusters and parameters")
        mt = self.min_years
        if mt != RYU_OURS_MIN_YEARS:
            bad.append(f"min_years is {mt!r}, but the paper drops utilities that appear in fewer than {RYU_MIN_YEARS} "
                       f"years of the panel (Ryu and Hiatt p. 6, Sec. 2.2), counted by utility, and row U's "
                       f"specification counts them after every other restriction: {RYU_OURS_MIN_YEARS!r}")
        if tuple(sorted(self.jurisdictions)) != RYU_OURS_JURISDICTIONS:
            bad.append("jurisdictions must be the 50 states and the District of Columbia (RYU_OURS_JURISDICTIONS), row "
                       "U's reading of the paper's 51")
        if self.weighting not in WEIGHTINGS:
            bad.append(f"weighting is {self.weighting!r}; the paper states no weights, row U's specification is "
                       f"{RYU_OURS_WEIGHTING!r}, and no weighted fit is built")
        if bad:
            raise ValueError("Row U refuses to depart from its specification. " + "; ".join(bad) + ". The values are "
                             "this study's approximations, ours and not the paper's, adopted by Joe on 2026-11-19 "
                             "(D-107), or the paper's own where it states them.")
        if self.short_form_exclusion not in SHORT_FORM_RULES:
            raise ValueError(f"short_form_exclusion must be one of {SHORT_FORM_RULES} (the paper excludes Short Form "
                             f"filers, endnote 10 p. 17, without saying for which years)")


def ryu_spec(short_form_exclusion: str) -> RyuSpec:
    """Row U's specification from the constants. short_form_exclusion is an argument the caller supplies, settled by
    the rule Joe adopted on 2026-11-20 (D-115), whose code is U_SHORT_FORM_ADOPTED_CODE, 'unit_years_filed', with the
    flags built by short_form_filers.adopted_row_u_flags."""
    s = RyuSpec(ownership_spec=RYU_OURS_OWNERSHIP_SPEC, ss_correction=RYU_OURS_SS_CORRECTION,
                min_years=RYU_OURS_MIN_YEARS, jurisdictions=RYU_OURS_JURISDICTIONS,
                short_form_exclusion=short_form_exclusion, weighting=RYU_OURS_WEIGHTING)
    s.check()
    return s


# --------------------------------------------------------------------------------------------------------------------
# Estimators
# --------------------------------------------------------------------------------------------------------------------

def callaway_santanna(y: pd.DataFrame, first_year: pd.Series, window: tuple[int, int], spec: MeeksSpec,
                      treated_units=None) -> dict:
    """Overall effect of first treatment, Callaway and Sant'Anna with never-treated comparisons and no covariates.

    y            unit-by-year matrix of the outcome (rows: units, columns: years in the window), NaN where not observed
    first_year   by unit (same index), NaN for units never treated in the inventory
    treated_units  if given, only these units may be treated (an ownership run); other treated units leave the sample,
                 and every never-treated unit stays a comparison (Meeks et al., Table 3 notes, p. 48)
    Units first treated before the window's first year leave the sample (the paper's rule, p. 20). Under
    spec.window_start_cohort == "base_year_before_window" the outcome's years before the window (down to the earliest
    base year, lo - 1 - anticipation) serve as base years only, never as cells; otherwise only window years are kept.
    Returns estimate, se, the cells, cohorts and failures in words.
    """
    spec.check()
    lo, hi = window
    base_lo = lo - 1 - int(spec.anticipation) if spec.window_start_cohort == "base_year_before_window" else lo
    window_years = [t for t in y.columns if lo <= t <= hi]
    years = [t for t in y.columns if base_lo <= t <= hi]
    y = y[years]
    g = first_year.reindex(y.index).astype(float)
    failures, notes = [], []
    pre = g < lo
    if pre.any():
        notes.append(f"{int(pre.sum())} units first treated before {lo} are dropped (the paper's rule)")
    keep = ~pre
    after = g > hi
    if after.any():
        if spec.treated_after_window == "never_treated":
            notes.append(f"{int(after.sum())} units first treated after {hi} are comparison units")
            g = g.where(~after, np.nan)
        else:
            notes.append(f"{int(after.sum())} units first treated after {hi} are dropped")
            keep &= ~after
    if treated_units is not None:
        other = g.notna() & ~g.index.isin(list(treated_units))
        keep &= ~other
    if spec.unbalanced == "balance":
        full = y[window_years].notna().all(axis=1)
        if (~full & keep).any():
            notes.append(f"{int((~full & keep).sum())} units not observed in every window year are dropped (balance)")
        keep &= full
    # cohorts whose base year is outside the window cannot be estimated: reported, their units leave the sample
    for c in sorted(g[keep].dropna().unique()):
        base = int(c) - 1 - int(spec.anticipation)
        if base < base_lo:
            n = int(((g == c) & keep).sum())
            failures.append(f"cohort {int(c)}: its base year {base} is outside the years available as base years, so "
                            f"its {n} units cannot be estimated and are left out")
            keep &= ~(g == c)
    y, g = y[keep], g[keep]
    N = len(y)
    never = g.isna().values
    cohorts = sorted(int(c) for c in g.dropna().unique())
    Y = y.values
    col = {t: i for i, t in enumerate(years)}
    cells = []
    for c in cohorts:
        base = c - 1 - int(spec.anticipation)
        inc = (g == c).values
        for t in range(c, hi + 1):
            if t not in col:
                continue
            if base not in col:
                failures.append(f"cell ({c}, {t}): no outcome column for its base year {base}; not estimable, left out "
                                f"of the average")
                continue
            ok = ~np.isnan(Y[:, col[t]]) & ~np.isnan(Y[:, col[base]])
            tr, co = inc & ok, never & ok
            if tr.sum() == 0 or co.sum() == 0:
                failures.append(f"cell ({c}, {t}): {int(tr.sum())} treated and {int(co.sum())} comparison units observed "
                                f"at both {base} and {t}; not estimable, left out of the average")
                continue
            d = Y[:, col[t]] - Y[:, col[base]]
            mt, mc = d[tr].mean(), d[co].mean()
            inf = np.zeros(N)
            inf[tr] = N / tr.sum() * (d[tr] - mt)
            inf[co] = -N / co.sum() * (d[co] - mc)
            cells.append({"cohort": c, "year": t, "att": mt - mc, "n_treated": int(tr.sum()), "n_comparison": int(co.sum()),
                          "if": inf})
    out = {"estimate": None, "se": None, "n_units": N, "n_treated_units": int((~never).sum()),
           "n_comparison_units": int(never.sum()), "cohorts": cohorts, "failures": failures, "notes": notes,
           "cells": [{k: v for k, v in c.items() if k != "if"} for c in cells]}
    if not cells:
        failures.append("no estimable cell: no overall effect")
        return out
    if never.sum() == 0:
        failures.append("no comparison unit")
        return out
    p = {c: float((g == c).sum()) / N for c in cohorts}
    ind = {c: (g == c).values.astype(float) - p[c] for c in cohorts}       # influence of each cohort share
    used = sorted({c["cohort"] for c in cells})
    if spec.aggregation == "simple":
        units = [(c["cohort"], c["att"], c["if"]) for c in cells]
    else:
        units = []
        for c in used:
            mine = [x for x in cells if x["cohort"] == c]
            units.append((c, float(np.mean([x["att"] for x in mine])), np.mean([x["if"] for x in mine], axis=0)))
    S = sum(p[c] for c, _, _ in units)
    S_if = sum(ind[c] for c, _, _ in units)
    theta = sum(p[c] / S * a for c, a, _ in units)
    infl = sum(p[c] / S * f for c, _, f in units) + sum(a * (ind[c] / S - p[c] * S_if / S ** 2) for c, a, _ in units)
    out["estimate"] = float(theta)
    out["influence"] = infl
    if spec.se_method == "influence_function":
        out["se"] = float(np.sqrt(np.sum(infl ** 2)) / N)
    else:
        rng = np.random.default_rng(int(spec.seed))
        B = int(spec.bootstrap_draws)
        if spec.bootstrap_weights == "rademacher":
            v = rng.choice([-1.0, 1.0], size=(B, N))
        else:
            k = (np.sqrt(5) + 1) / (2 * np.sqrt(5))
            v = np.where(rng.random((B, N)) < k, -(np.sqrt(5) - 1) / 2, (np.sqrt(5) + 1) / 2)
        draws = v @ infl / N
        q75, q25 = np.quantile(draws, [0.75, 0.25])
        out["se"] = float((q75 - q25) / 1.3489795003921634)
    return out


def twfe(frame: pd.DataFrame, regressors: list[str], unit_col: str, year_col: str, cluster_col: str,
         ss_correction: str) -> dict:
    """OLS of `y` on `regressors` with `unit_col` and `year_col` effects removed exactly, clustered by `cluster_col`.

    The unit effects are swept by subtracting unit means from y, the regressors and the year dummies (one year left
    out); the year dummies stay as regressors. On any unbalanced panel this is the least-squares fit with both sets of
    effects (Frisch-Waugh-Lovell). Returns coefficients and clustered standard errors for `regressors`.
    """
    failures = []
    d = frame[[unit_col, year_col, cluster_col, "y"] + regressors].reset_index(drop=True)
    years = sorted(d[year_col].unique())
    yd = pd.get_dummies(d[year_col]).reindex(columns=years[1:], fill_value=False).astype(float).values
    X = np.column_stack([d[regressors].values.astype(float), yd]) if len(years) > 1 else d[regressors].values.astype(float)
    yv = d["y"].values.astype(float)
    codes, uniq = pd.factorize(d[unit_col])
    cnt = np.bincount(codes)

    def sweep(a):
        a = np.atleast_2d(a.T).T
        sums = np.zeros((len(uniq), a.shape[1]))
        np.add.at(sums, codes, a)
        return a - (sums / cnt[:, None])[codes]

    Xt, yt = sweep(X), sweep(yv)[:, 0]
    k = len(regressors)
    out = {"coef": {r: None for r in regressors}, "se": {r: None for r in regressors}, "n": int(len(d)),
           "n_units": int(len(uniq)), "n_clusters": int(d[cluster_col].nunique()), "failures": failures}
    for j, r in enumerate(regressors):
        if np.allclose(Xt[:, j], 0.0):
            failures.append(f"{r} has no variation within units; its coefficient cannot be estimated")
    if failures:
        return out
    XtX = Xt.T @ Xt
    if np.linalg.matrix_rank(XtX) < XtX.shape[0]:
        failures.append("the regressors are collinear after the fixed effects are removed; not estimable")
        return out
    A = np.linalg.inv(XtX)
    b = A @ (Xt.T @ yt)
    e = yt - Xt @ b
    gcodes, guniq = pd.factorize(d[cluster_col])
    G = len(guniq)
    if G < 2:
        failures.append(f"{G} cluster: a clustered standard error cannot be computed")
        for j, r in enumerate(regressors):
            out["coef"][r] = float(b[j])
        return out
    S = np.zeros((G, Xt.shape[1]))
    np.add.at(S, gcodes, Xt * e[:, None])
    V = A @ (S.T @ S) @ A
    n, K = len(d), Xt.shape[1] + len(uniq)
    if ss_correction == "clusters":
        V *= G / (G - 1)
    elif ss_correction == "clusters_and_parameters":
        if n - K <= 0:
            failures.append("as many parameters as observations: the small-sample factor is undefined")
            return out
        V *= G / (G - 1) * (n - 1) / (n - K)
    elif ss_correction != "none":
        raise ValueError(f"unknown ss_correction {ss_correction!r}")
    for j, r in enumerate(regressors):
        out["coef"][r] = float(b[j])
        out["se"][r] = float(np.sqrt(V[j, j]))
    return out


# --------------------------------------------------------------------------------------------------------------------
# Shared preparation
# --------------------------------------------------------------------------------------------------------------------

def _outcome_rows(outcome: pd.DataFrame, window: tuple[int, int], jurisdictions) -> tuple[pd.DataFrame, list, list]:
    """Window and jurisdictions applied; missing values counted; a non-positive price is a numerical failure in words."""
    rt._need(outcome, KEY + ["year", "value"], "outcome")
    lo, hi = window
    o = outcome[(outcome.year >= lo) & (outcome.year <= hi)].copy()
    notes, failures = [], []
    out_j = ~o.state.isin(list(jurisdictions))
    if out_j.any():
        notes.append(f"{int(out_j.sum())} unit-years outside the jurisdictions are left out")
    o = o[~out_j]
    miss = o.value.isna()
    if miss.any():
        notes.append(f"{int(miss.sum())} unit-years with no price are left out")
    o = o[~miss]
    nonpos = o.value <= 0
    if nonpos.any():
        failures.append(f"{int(nonpos.sum())} unit-years have a price that is not positive and has no log; left out")
    o = o[~nonpos]
    if o.duplicated(KEY + ["year"]).any():
        raise ValueError("the outcome has more than one row for a unit-year")
    o["y"] = np.log(o.value.astype(float))
    return o, notes, failures


def _check_step(step: str, steps: dict, outcome_name: str, treatment: rt.Treatment) -> dict:
    if step not in steps:
        raise ValueError(f"unknown step {step!r}")
    s = steps[step]
    if outcome_name != s["price"]:
        raise ValueError(f"step {step} uses the price {s['price']!r}, not {outcome_name!r}")
    if not str(treatment.rule).startswith(s["rule"]):
        raise ValueError(f"step {step} needs a treatment built under {s['rule']!r}, not {treatment.rule!r}")
    return s


def _ownership(ownership: pd.DataFrame, allowed) -> pd.Series:
    rt._need(ownership, KEY + ["ownership_class"], "ownership")
    o = ownership.drop_duplicates(KEY).set_index(KEY).ownership_class
    bad = set(o.unique()) - set(allowed) - {"other"}
    if bad:
        raise ValueError(f"ownership classes {sorted(bad)} are not among {list(allowed)} or 'other'")
    return o


def _unit_label(frame: pd.DataFrame) -> list[str]:
    return [f"{int(u)}:{s}" for u, s in zip(frame.utility_id_eia, frame.state)]


def _band(est, band) -> bool | None:
    return None if est is None else bool(band[0] <= est <= band[1])


# --------------------------------------------------------------------------------------------------------------------
# Row M
# --------------------------------------------------------------------------------------------------------------------

def _m_size_counting(step: str, rule: str) -> str | None:
    """The 5 MW threshold (settled, p. 18) and how it is counted (NOT settled; with Joe), read from the treatment's rule
    `assignment|above_<thr>mw|<counting>|<size column>` (reconciliation_treatment.first_year_above_size). M4 uses the
    plan's dose threshold instead and has no 5 MW count."""
    if step == "M4":
        return None
    parts = str(rule).split("|")
    want = f"above_{MEEKS_SIZE_THRESHOLD_MW:g}mw"
    if len(parts) < 3 or parts[1] != want:
        raise ValueError(f"row M's threshold is newly activated capacity above {MEEKS_SIZE_THRESHOLD_MW:g} MW, strictly "
                         f"(p. 18, file dated {MEEKS_FILE_DATE}); the treatment's rule {rule!r} does not carry {want!r}")
    if parts[2] not in MEEKS_SIZE_COUNTING_READINGS:
        raise ValueError(f"row M's treatment must name how the 5 MW is counted, one of "
                         f"{sorted(MEEKS_SIZE_COUNTING_READINGS)}; {MEEKS_SIZE_COUNTING_STATUS}")
    return parts[2]


def _m_unit_flag(sample_flags: pd.DataFrame, col: str) -> pd.Series:
    """One value of `col` per utility-state pair; refused in words if a pair carries two."""
    f = sample_flags[KEY + [col]].drop_duplicates()
    if f.duplicated(KEY).any():
        raise ValueError(f"sample_flags carries more than one {col} for a utility-state pair; {col} is one value per pair")
    return f.set_index(KEY)[col]


def _m_sample_rules(o: pd.DataFrame, spec: MeeksSpec, sample_flags: pd.DataFrame | None) -> tuple[pd.DataFrame, list]:
    """The paper's sample rules (p. 15, p. 21, file dated 2026-10-23), held at every step so one choice changes at a
    time: Short Form filers out by utility, ever; pairs serving the three classes; a retail component. A flag missing
    for a unit-year in the outcome is refused, never read as a pass."""
    notes = []
    if sample_flags is None:
        raise ValueError("row M needs sample_flags: the paper excludes Short Form filers (p. 15) and keeps pairs that serve "
                         "residential, commercial and industrial customers (p. 21); both flags come from EIA-861 inputs "
                         "that are not in the quantities file")
    need = ["ever_short_form", "short_form_first_year_read", "short_form_last_year_read", "has_three_classes",
            "three_classes_test"]
    if spec.three_classes_level == "unit_year":
        need.append("year")
    if spec.retail_component == "flag":
        need.append("has_retail_component")
    missing = [c for c in KEY + need if c not in sample_flags.columns]
    if missing:
        raise ValueError(f"sample_flags lacks {missing}, which the spec's sample rules need")
    sf = sample_flags
    read = sf[["short_form_first_year_read", "short_form_last_year_read"]].drop_duplicates()
    if len(read) != 1 or tuple(int(x) for x in read.iloc[0]) != tuple(int(x) for x in spec.short_form_years):
        raise ValueError(f"sample_flags' Short Form flag was not read over the spec's years {tuple(spec.short_form_years)}")
    if set(sf.three_classes_test.unique()) != {spec.three_classes_test}:
        raise ValueError(f"sample_flags' has_three_classes was not built under the spec's test {spec.three_classes_test!r}")

    def lookup(flag: pd.Series, keys) -> pd.Series:
        val = pd.Series([flag.get(k) for k in keys], index=o.index)
        if val.isna().any():
            raise ValueError(f"sample_flags has no {flag.name} for {int(val.isna().sum())} unit-years in the outcome")
        return val.astype(bool)

    pairs = list(zip(o.utility_id_eia, o.state))
    # Short Form: a utility that ever files leaves with every one of its state pairs (p. 15)
    ever = _m_unit_flag(sf, "ever_short_form")
    ever_pair = lookup(ever, pairs)
    filers = set(o.utility_id_eia[ever_pair.values])
    drop = o.utility_id_eia.isin(filers)
    notes.append(f"{int(drop.sum())} unit-years left out by ever_short_form ({len(filers)} utilities, every state pair; "
                 f"read over {spec.short_form_years[0]}-{spec.short_form_years[1]})")
    o = o[~drop.values]
    pairs = list(zip(o.utility_id_eia, o.state))
    # three classes (p. 21): once per pair, or each pair-year
    if spec.three_classes_level == "unit":
        three = lookup(_m_unit_flag(sf, "has_three_classes"), pairs)
    else:
        f = sf[KEY + ["year", "has_three_classes"]].drop_duplicates()
        if f.duplicated(KEY + ["year"]).any():
            raise ValueError("sample_flags carries more than one has_three_classes for a unit-year")
        f = f.set_index(KEY + ["year"]).has_three_classes
        three = lookup(f, list(zip(o.utility_id_eia, o.state, o.year)))
    notes.append(f"{int((~three).sum())} unit-years left out by has_three_classes "
                 f"({spec.three_classes_level}, {spec.three_classes_test})")
    o = o[three.values]
    # a retail component (p. 21, not defined)
    if spec.retail_component == "flag":
        rc = lookup(_m_unit_flag(sf, "has_retail_component"), list(zip(o.utility_id_eia, o.state)))
        notes.append(f"{int((~rc).sum())} unit-years left out by has_retail_component")
        o = o[rc.values]
    else:
        notes.append("retail component: no separate filter; a pair-year with a residential price is taken to have one "
                     "(the caller's choice; the paper does not define the term)")
    return o, notes


def run_m_step(step: str, outcome: pd.DataFrame, outcome_name: str, treatment: rt.Treatment, ownership: pd.DataFrame,
               spec: MeeksSpec, customers: pd.DataFrame | None = None, sample_flags: pd.DataFrame | None = None) -> dict:
    """One step of row M. `outcome` is (utility_id_eia, state, year, value) with value the residential price level named
    `outcome_name`; `treatment` a first-year Treatment (reconciliation_treatment); `ownership` (KEY, ownership_class in
    M_CLASSES or "other"). Pooled, then one run per ownership class with all never-treated units as comparisons
    (Table 3 notes, p. 48, file dated 2026-10-23).

    sample_flags  REQUIRED in practice (MeeksSpec refuses exclude_short_form or require_three_classes False): KEY,
                  ever_short_form, short_form_first_year_read, short_form_last_year_read, has_three_classes,
                  three_classes_test; plus year when three_classes_level is "unit_year" and has_retail_component when
                  retail_component is "flag".
    customers     accepted and not used: row M has no customer floor (the paper states none).
    The 5 MW threshold is checked on the treatment's rule; how it is counted (by site or by a county-year sum) is
    the treatment's explicit argument and is reported with the result, the difference from the plan's row being
    with Joe (MEEKS_SIZE_COUNTING_STATUS).
    """
    spec.check()
    counting = _m_size_counting(step, treatment.rule)           # the paper's words first, then the step's rule prefix
    s = _check_step(step, M_STEPS, outcome_name, treatment)
    lo, hi = s["window"]
    read_lo = lo - 1 - int(spec.anticipation) if spec.window_start_cohort == "base_year_before_window" else lo
    o, notes, failures = _outcome_rows(outcome, (read_lo, hi), spec.jurisdictions)
    if read_lo < lo:
        notes.append(f"years {read_lo} to {lo - 1} are read as base years only, never as cells (window_start_cohort)")
    o, more = _m_sample_rules(o, spec, sample_flags)
    notes += more
    Y = o.assign(unit=_unit_label(o)).pivot(index="unit", columns="year", values="y")
    tt = treatment.table.drop_duplicates(KEY)
    fy = pd.Series(tt.first_year.values.astype(float), index=_unit_label(tt))
    if not set(Y.index) <= set(fy.index):
        raise ValueError("the treatment has no row for some outcome units; the input is incomplete")
    o_m = _ownership(ownership, M_CLASSES)
    own = dict(zip([f"{int(u)}:{s}" for u, s in o_m.index], o_m.values))
    res = {"row": "M", "step": step, "change": s["change"], "outcome_name": outcome_name, "years": list(s["window"]),
           "treatment_rule": treatment.rule, "spec": {k: v for k, v in asdict(spec).items()},
           "paper_file": MEEKS_FILE, "size_counting": counting,
           "size_counting_status": None if counting is None else MEEKS_SIZE_COUNTING_STATUS,
           "notes": notes, "numerical_failures": list(failures)}
    pooled = callaway_santanna(Y, fy, s["window"], spec)
    res["pooled"] = {k: pooled[k] for k in ("estimate", "se", "n_units", "n_treated_units", "n_comparison_units",
                                            "cohorts", "failures", "notes", "cells")}
    res["by_ownership"] = {}
    for c in M_CLASSES:
        mine = [k for k in Y.index if own.get(k) == c]
        r = callaway_santanna(Y, fy, s["window"], spec, treated_units=mine)
        res["by_ownership"][c] = {k: r[k] for k in ("estimate", "se", "n_treated_units", "n_comparison_units", "failures")}
        if r["n_treated_units"] == 0:
            res["by_ownership"][c]["failures"] = r["failures"] + [f"no treated {c} unit"]
    unknown = [k for k in Y.index if pd.notna(fy.get(k)) and own.get(k) is None]
    if unknown:
        res["notes"].append(f"{len(unknown)} treated units have no ownership class and enter only the pooled run")
    for part in [res["pooled"]] + list(res["by_ownership"].values()):
        res["numerical_failures"] += part["failures"]
    est = res["pooled"]["estimate"]
    iou, pub, coop = (res["by_ownership"][c]["estimate"] for c in M_CLASSES)
    ordering = None if None in (iou, pub, coop) else bool(iou > pub and iou > coop)
    res["paper_printed"] = PAPER_M
    res["band"] = list(BAND_M)
    res["in_band"] = _band(est, BAND_M)
    res["ownership_ordering_holds"] = ordering
    res["ownership_ordering_is"] = "investor-owned estimate larger than the public and the cooperative estimates"
    if step == "M0":
        res["reproduced"] = None if (res["in_band"] is None or ordering is None) else bool(res["in_band"] and ordering)
        if res["reproduced"] is False:
            res["sentence"] = (f"{M0_NOT_REPRODUCED}, {est:.4f} against the published {PAPER_M['pooled'][0]:.3f} "
                               f"(log points, residential).")
        elif res["reproduced"] is None:
            res["sentence"] = None
            res["sentence_why_none"] = "the estimate or an ownership estimate could not be computed (numerical_failures)"
        else:
            res["sentence"] = None
            res["sentence_why_none"] = "the plan fixes a sentence for M0 only when it is not reproduced"
    return res


def describe_row_m(results: list[dict]) -> list[str]:
    """At each step, how far the estimate moved and whether the ownership ordering survived (PREANALYSIS.md, row M).
    The plan fixes the content, not the wording; this wording is the agent's. Movement is from the step before (one
    change at a time) and from M0."""
    out, prev, first = [], None, None
    for r in results:
        est = r["pooled"]["estimate"]
        if est is None:
            out.append(f"{r['step']}: no estimate ({'; '.join(r['numerical_failures'])}).")
            continue
        moved = "" if prev is None else f", {est - prev[1]:+.4f} from {prev[0]} and {est - first[1]:+.4f} from {first[0]}"
        o = r["ownership_ordering_holds"]
        ord_txt = ("the ordering could not be computed" if o is None else
                   "the investor-owned estimate is above both the public and the cooperative estimates" if o else
                   "the investor-owned estimate is not above both the public and the cooperative estimates")
        out.append(f"{r['step']}: {est:.4f} log points{moved}; {ord_txt}.")
        if first is None:
            first = (r["step"], est)
        prev = (r["step"], est)
    return out


# --------------------------------------------------------------------------------------------------------------------
# Row U
# --------------------------------------------------------------------------------------------------------------------

def _min_years(o: pd.DataFrame, n: int, level: str) -> tuple[pd.DataFrame, str]:
    """Drop the unit-years of utilities (level "utility") seen in fewer than n distinct years of `o`, which by then
    has had every other restriction applied (RYU_OURS_MIN_YEARS_COUNTED_AFTER)."""
    cols = ["utility_id_eia"] if level == "utility" else KEY
    cnt = o.groupby(cols).year.transform("nunique")
    drop = cnt < int(n)
    return o[~drop], (f"{int(drop.sum())} unit-years of {level.replace('_', '-')}s with fewer than {n} years are left "
                      f"out (Ryu and Hiatt p. 6, Sec. 2.2; counted after every other restriction, ours, D-107)")


def _u_drop_no_ownership(o: pd.DataFrame, ownership: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    """Only utilities reporting an ownership type are kept (p. 6); "other" stays for the pooled run (p. 8). A row filter
    on each unit's own class."""
    rt._need(ownership, KEY + ["ownership_class"], "ownership")
    own = _ownership(ownership.dropna(subset=["ownership_class"]), U_CLASSES)
    o = o.copy()
    o["cls"] = [own.get(k) for k in zip(o.utility_id_eia, o.state)]
    no_own = o.cls.isna()
    note = (f"{int(no_own.sum())} unit-years with no ownership class are left out (the paper keeps utilities reporting "
            f"ownership-type data, p. 6)") if no_own.any() else None
    return o[~no_own], note


def _u_drop_short_form(o: pd.DataFrame, spec: RyuSpec, sample_flags: pd.DataFrame | None,
                       window: tuple[int, int]) -> tuple[pd.DataFrame, str]:
    """Short Form filers out (endnote 10, p. 17) under spec.short_form_exclusion. A row filter: "unit_years_filed" reads
    each row's own flag and "utilities_ever_filed" the utility's flags over the window from sample_flags, never from
    the rows that are left, so it does not matter which filter comes first.

    A flag is read only where it is True or False. A unit-year of the outcome with no flag row, or with a missing flag,
    and under "utilities_ever_filed" a missing flag in any window year of a utility in the outcome, stops the step in
    words, and nothing here reads a missing flag as False. Under the rule Joe adopted on 2026-11-20 (D-115) the reading
    of a missing 2019 flag, of no flags row and of no table row is made where the flags are built, by
    short_form_filers.adopted_row_u_flags (each kept with no record of a filing, which is no claim about whether the unit
    filed), so flags built that way carry True or False on every unit-year of the frame they were built on. That frame
    must cover every outcome unit-year that reaches this filter; whether it does cannot be shown before outcomes are read,
    and this stop is what catches a gap. Rows of sample_flags that share a unit-year are accepted only if their flags
    agree. The table's data_observed column is not read."""
    sf = spec.short_form_exclusion
    if sf == "none_in_outcome_frame":
        return o, ("Short Form: no exclusion applied. The caller states the outcome frame holds no Short Form unit-year; "
                   "that is not checked here, so this is not the paper's sample. " + U_SHORT_FORM_NO_SUBSTITUTE)
    if sample_flags is None or not {"utility_id_eia", "state", "year", "short_form"} <= set(sample_flags.columns):
        raise ValueError(f"short_form_exclusion={sf!r} needs sample_flags with utility_id_eia, state, year and "
                         f"short_form (the Short Form flags table, passed by the caller; nothing under data/raw is "
                         f"read here)")
    f = sample_flags[KEY + ["year", "short_form"]].copy()
    f["short_form"] = f.short_form.astype("boolean")
    clash = f.groupby(KEY + ["year"]).short_form.apply(lambda x: x.astype(object).where(x.notna(), "NA").nunique() > 1)
    if clash.any():
        raise ValueError(f"sample_flags carries {int(clash.sum())} unit-years whose rows disagree on short_form; no row is "
                         f"chosen among them")
    f = f.drop_duplicates(KEY + ["year"])
    m = o[KEY + ["year"]].merge(f, on=KEY + ["year"], how="left", indicator=True)
    no_row = int((m._merge == "left_only").sum())
    missing = int(((m._merge == "both") & m.short_form.isna()).sum())
    if no_row or missing:
        raise ValueError(f"short_form_exclusion={sf!r}: {no_row} outcome unit-years have no row in sample_flags and "
                         f"{missing} have a missing flag. sample_flags must carry True or False for every outcome "
                         f"unit-year; under the adopted rule (D-115) they are built by "
                         f"short_form_filers.adopted_row_u_flags on a frame that covers every outcome unit-year. The "
                         f"rule is not applied here, and no missing flag is read as False")
    if sf == "utilities_ever_filed":
        lo, hi = window
        fw = f[(f.year >= lo) & (f.year <= hi) & f.utility_id_eia.isin(set(o.utility_id_eia))]
        if fw.short_form.isna().any():
            raise ValueError(f"short_form_exclusion='utilities_ever_filed': {int(fw.short_form.isna().sum())} window "
                             f"unit-years of the outcome's utilities have a missing flag, so whether each utility ever "
                             f"filed is not known; the rule is not applied")
        flag = o.utility_id_eia.isin(set(fw[fw.short_form.astype(bool)].utility_id_eia)).values
    else:
        flag = m.short_form.astype(bool).values
    return o[~flag], f"{int(flag.sum())} unit-years left out as Short Form filers ({sf})"


def u_sample_rules(o: pd.DataFrame, ownership: pd.DataFrame, spec: RyuSpec, sample_flags: pd.DataFrame | None,
                   window: tuple[int, int], *, order: tuple = U_SAMPLE_FILTER_ORDER) -> tuple[pd.DataFrame, list]:
    """The paper's three sample rules on rows that have had the window, jurisdiction and missing-price rules applied:
    the two row filters (ownership reported, Short Form filers out) in `order`, then the three-year count, which is
    always last (RYU_OURS_MIN_YEARS_COUNTED_AFTER). `order` exists so that a test can show the two filters commute;
    run_u_step uses U_SAMPLE_FILTER_ORDER. Returns the rows (with `cls`) and the notes."""
    if tuple(sorted(order)) != ("ownership", "short_form"):
        raise ValueError("order must be the two row filters 'ownership' and 'short_form' in some order; the three-year "
                         "count is always taken last")
    notes = []
    for step in order:
        if step == "ownership":
            o, note = _u_drop_no_ownership(o, ownership)
        else:
            o, note = _u_drop_short_form(o, spec, sample_flags, window)
        if note:
            notes.append(note)
    o, note = _min_years(o, RYU_MIN_YEARS, RYU_MIN_YEARS_LEVEL)
    notes.append(note)
    return o, notes


def _ownership_comparison(res: dict) -> dict:
    """Row U's ownership estimates beside the paper's controlled ones, labelled, with no verdict (D-107)."""
    ours = {c: {"estimate": res["by_ownership"][c]["estimate"], "se": res["by_ownership"][c]["se"],
                "n": res["by_ownership"][c].get("n")} for c in U_CLASSES}
    est = [ours[c]["estimate"] for c in U_CLASSES]
    coop, muni, iou = est
    return {"label": U_OWNERSHIP_COMPARISON_LABEL, "verdict": None,
            "ours_without_controls": ours,
            "paper_with_six_controls": {c: PAPER_U[f"{c}_with_controls"] for c in U_CLASSES},
            "paper_sample_sizes": {c: PAPER_U_N[f"{c}_observations"] for c in U_CLASSES},
            "co_op_and_municipal_each_above_investor_owned_in_our_estimates":
                None if None in est else bool(coop > iou and muni > iou)}


def run_u_step(step: str, outcome: pd.DataFrame, outcome_name: str, treatment: rt.Treatment, ownership: pd.DataFrame,
               spec: RyuSpec, sample_flags: pd.DataFrame | None = None) -> dict:
    """One step of row U. `treatment` a cumulative-MW Treatment (KEY, year, mw) built on the inventory's site-year load
    (RYU_OURS_MW_SOURCE; U0 on reconciliation_treatment.assign_polygon_smallest under ROW_U_POLYGON); `ownership` (KEY,
    ownership_class in U_CLASSES or "other"). ln(price) on ln(MW + 1), utility and year effects, clustered by state,
    no controls, no customer floor, unweighted. Pooled, and by ownership in separate regressions.

    The paper's sample rules, held at every step (one choice changes at a time): window and jurisdictions, missing or
    non-positive price, then u_sample_rules (ownership reported, Short Form filers out, then the three-year count).
    A site the assignment left out because its unit depends on how an ambiguous polygon is classed is named in the
    result, which says the estimate depends on those sites.

    No verdict: comparison-only by Joe's ruling of 2026-11-19 (D-109). The ownership estimates come back as a
    comparison under our specification beside the paper's controlled ones (U_OWNERSHIP_COMPARISON_LABEL), and at U0
    the pooled estimate as a comparison with the paper's figure and band beside it (U_POOLED_COMPARISON_LABEL). Every
    result carries the missing-coverage qualification (a unit with no assigned site is not shown to have no facility),
    U0's the label of its assignment rule and the coincidence with row C's, and every result the Short Form status
    (under "none_in_outcome_frame", no exclusion applied and not the paper's sample; under the adopted code
    "unit_years_filed", U_SHORT_FORM_ADOPTED_LABEL, which holds when sample_flags come from
    short_form_filers.adopted_row_u_flags)."""
    spec.check()
    s = _check_step(step, U_STEPS, outcome_name, treatment)
    o, notes, failures = _outcome_rows(outcome, s["window"], spec.jurisdictions)
    o, more = u_sample_rules(o, ownership, spec, sample_flags, s["window"])
    notes += more
    rt._need(treatment.table, KEY + ["year", "mw"], "treatment")
    o = o.merge(treatment.table[KEY + ["year", "mw"]], on=KEY + ["year"], how="left")
    if o.mw.isna().any():
        raise ValueError(f"the treatment has no MW for {int(o.mw.isna().sum())} outcome unit-years; the input is incomplete")
    if (o.mw < 0).any():
        raise ValueError("negative MW in the treatment")
    o["x"] = np.log(o.mw.astype(float) + 1.0)
    res = {"row": "U", "step": step, "change": s["change"], "outcome_name": outcome_name, "years": list(s["window"]),
           "treatment_rule": treatment.rule, "spec": asdict(spec), "notes": notes, "numerical_failures": list(failures),
           "specification": {"settled_from_the_paper": "constants RYU_* (docs/gate1/bounded-read-row-u-2026-11-19.md)",
                             "ours_adopted_2026_11_19_d107": RYU_APPROXIMATIONS,
                             "short_form_exclusion": {"as_supplied": spec.short_form_exclusion,
                                                      "adopted_code": U_SHORT_FORM_ADOPTED_CODE,
                                                      "adopted": "by Joe on 2026-11-20 (D-115)"},
                             "exact_reproduction_unavailable": list(RYU_UNAVAILABLE)}}
    dep = list(getattr(treatment, "depends_on_ambiguous", []) or [])
    res["sites_depending_on_ambiguous_polygon_classes"] = dep
    if dep:
        res["notes"].append(f"this step's result depends on {len(dep)} sites left out because their unit depends on how "
                            f"ambiguous territory polygons are classed: {dep}")
    pooled = twfe(o, ["x"], RYU_UNIT_EFFECT, "year", RYU_CLUSTER, spec.ss_correction)
    res["pooled"] = {"estimate": pooled["coef"]["x"], "se": pooled["se"]["x"], "n": pooled["n"],
                     "n_utilities": pooled["n_units"], "n_clusters": pooled["n_clusters"],
                     "n_unit_years_with_mw": int((o.mw > 0).sum()), "failures": pooled["failures"]}
    res["by_ownership"] = {}
    for c in U_CLASSES:
        sub = o[o.cls == c]
        if sub.empty:
            res["by_ownership"][c] = {"estimate": None, "se": None, "n": 0, "failures": [f"no {c} unit-year"]}
            continue
        r = twfe(sub, ["x"], RYU_UNIT_EFFECT, "year", RYU_CLUSTER, spec.ss_correction)
        res["by_ownership"][c] = {"estimate": r["coef"]["x"], "se": r["se"]["x"], "n": r["n"],
                                  "n_clusters": r["n_clusters"], "failures": r["failures"]}
    for part in [res["pooled"]] + list(res["by_ownership"].values()):
        res["numerical_failures"] += part["failures"]
    res["paper_printed"] = PAPER_U
    res["paper_printed_sample_sizes"] = PAPER_U_N
    res["jurisdictions_in_sample"] = int(o.state.nunique())
    res["paper_jurisdictions"] = RYU_N_JURISDICTIONS
    res["ownership_comparison"] = _ownership_comparison(res)
    res["missing_coverage"] = rt.MISSING_COVERAGE_QUALIFICATION
    if spec.short_form_exclusion == "none_in_outcome_frame":
        res["short_form_status"] = U_SHORT_FORM_NOT_APPLIED_LABEL
    elif spec.short_form_exclusion == U_SHORT_FORM_ADOPTED_CODE:
        res["short_form_status"] = (f"Short Form unit-years excluded by the flags supplied ({U_SHORT_FORM_ADOPTED_CODE}); "
                                    "the label below holds when the flags come from "
                                    "short_form_filers.adopted_row_u_flags. " + U_SHORT_FORM_ADOPTED_LABEL)
    else:
        res["short_form_status"] = (f"Short Form filers excluded by the flags supplied ({spec.short_form_exclusion}). "
                                    + U_SHORT_FORM_NO_SUBSTITUTE)
    if step == "U0":
        res["assignment_rule"] = {"label": rt.ROW_U_POLYGON_LABEL, "coincidence_with_row_c": rt.ROW_U_C_COINCIDENCE}
        res["pooled_comparison"] = {"label": U_POOLED_COMPARISON_LABEL, "verdict": None,
                                    "ours": {"estimate": res["pooled"]["estimate"], "se": res["pooled"]["se"]},
                                    "paper_no_controls": PAPER_U["pooled_no_controls"],
                                    "paper_band_beside": list(BAND_U),
                                    "missing_coverage": rt.MISSING_COVERAGE_QUALIFICATION}
    return res


def u1_sentence(result: dict, indistinguishable: bool | None = None) -> dict:
    """U1's sentences as Joe adopted them on 2026-11-19 (D-109), chosen by ONE fact: whether our co-op and municipal
    coefficients are each above our investor-owned one, in our estimates without controls
    (ownership_comparison["co_op_and_municipal_each_above_investor_owned_in_our_estimates"]). The chosen sentence is
    followed by U1_CONTROLS_SENTENCE. Where an ownership coefficient could not be computed the fact is unknown and no
    sentence is returned (U1_NO_SENTENCE). `indistinguishable` is accepted so that existing callers keep working,
    recorded, and decides nothing: the clause "or the three are indistinguishable" went with the plan's earlier
    sentence and is not used, and the paper tests no difference between ownership coefficients."""
    if result.get("step") != "U1":
        raise ValueError("the plan fixes this sentence for U1 only")
    comp = result["ownership_comparison"]
    fact = comp["co_op_and_municipal_each_above_investor_owned_in_our_estimates"]
    if fact is None:
        sentence, why = None, U1_NO_SENTENCE
    else:
        sentence = (U1_SENTENCE_EACH_ABOVE if fact else U1_SENTENCE_NOT_EACH_ABOVE) + " " + U1_CONTROLS_SENTENCE
        why = ("chosen by whether our co-op and municipal coefficients are each above our investor-owned one, in our "
               "estimates without controls: " + ("they are" if fact else "they are not"))
    return {"sentence": sentence, "why": why, "wording_status": U1_WORDING_STATUS, "comparison": comp,
            "indistinguishable_as_passed": indistinguishable,
            "indistinguishable_decides": "nothing: the adopted sentences do not use it"}


# --------------------------------------------------------------------------------------------------------------------
# Ownership classes from the quantities file (for the summary; the steps take ownership as an argument)
# --------------------------------------------------------------------------------------------------------------------

M_MAP = {"Investor Owned": "investor_owned", "Cooperative": "cooperative", "Municipal": "public",
         "Political Subdivision": "public", "State": "public", "Federal": "public"}
U_MAP = {"Investor Owned": "investor_owned", "Cooperative": "cooperative", "Municipal": "municipal"}


def _check_m_public_types(m_map: dict | None = None) -> None:
    """Row M's public class is exactly the paper's four types (p. 16, file dated 2026-10-23); refused otherwise."""
    m_map = M_MAP if m_map is None else m_map
    public = {k for k, v in m_map.items() if v == "public"}
    if public != set(MEEKS_PUBLIC_ENTITY_TYPES) or {m_map.get("Investor Owned"), m_map.get("Cooperative")} != \
            {"investor_owned", "cooperative"}:
        raise ValueError("row M's public class is federal, state, municipal and political subdivision utilities "
                         f"(p. 16, file dated 2026-10-23); the mapping gives {sorted(public)}")


# --------------------------------------------------------------------------------------------------------------------
# Ownership for rows U and C, settled by Joe on 2026-11-20 (D-117). In his words: "Use the last nonmissing reported EIA
# entity type for each utility-state over the existing quantity panel's 2001–2025 years, matching the convention used in
# the current quantity summaries. Apply the existing row-specific ownership mappings and missing-ownership treatment.
# Missing ownership must not become evidence of independent ownership. Make the years searched and the time-invariant
# classification explicit." Inspection then found that the panel's entity_type column is one type per utility id, the
# type its own filings report most often (PANEL_ENTITY_TYPE_STATEMENT), and Joe ruled on it the same day (D-119), in his
# words: "Keep the existing panel entity type for rows U and C, accurately described as the utility-level modal reported
# type carried across the panel, not the latest year-by-year EIA classification. No further raw-data investigation."
# So the classification is the panel's entity type, described as D-119 describes it (OWNERSHIP_DESCRIPTION_D119), and the
# last nonmissing value over 2001 to 2025 (D-117) is how the code reads that column (OWNERSHIP_HOW_READ_D117). The
# specification is held here, in one named place, and both rows import it from here
# (reconciliation_c imports this module; this module imports neither reconciliation_c nor short_form_filers at its top,
# so there is no import cycle). Row M is dormant and out of scope: its classes still come from ownership_classes with a
# pick stated by the caller.
# --------------------------------------------------------------------------------------------------------------------
OWNERSHIP_SETTLED_D117 = ("settled by Joe on 2026-11-20 (D-117), the type described as his ruling of the same day "
                          "states (D-119)")
# Joe's ruling of 2026-11-20 on what the type is (D-119), his words verbatim, and the description the texts carry.
OWNERSHIP_RULED_D119 = "Joe, 2026-11-20 (D-119)"
OWNERSHIP_RULING_D119_WORDS = ("Keep the existing panel entity type for rows U and C, accurately described as the "
                               "utility-level modal reported type carried across the panel, not the latest year-by-year "
                               "EIA classification. No further raw-data investigation.")
OWNERSHIP_DESCRIPTION_D119 = ("the panel's entity type, the utility-level modal reported type carried across the panel to "
                              "every year and state of the utility, and not the latest year-by-year EIA classification")
OWNERSHIP_HOW_READ_D117 = ("read as the last nonmissing value of the panel's entity_type column over 2001 to 2025 "
                           "(D-117), which on this panel returns that same type for every utility-state")
# OWNERSHIP_DESCRIPTION_D119 + " (D-119), " + OWNERSHIP_HOW_READ_D117, written out (a test checks the two agree)
OWNERSHIP_PICK_D117 = ("the panel's entity type, the utility-level modal reported type carried across the panel to every "
                       "year and state of the utility, and not the latest year-by-year EIA classification (D-119), read "
                       "as the last nonmissing value of the panel's entity_type column over 2001 to 2025 (D-117), which "
                       "on this panel returns that same type for every utility-state")
OWNERSHIP_YEARS_SEARCHED = tuple(range(2001, 2026))          # the quantity panel's years, 2001 to 2025
OWNERSHIP_TIME_INVARIANT = ("time-invariant: one class per utility-state, the same class in every year of that "
                            "utility-state")
OWNERSHIP_MISSING_TREATMENT = (
    "A utility-state with no entity type in any year searched gets no class. Under row U it leaves the sample, as a "
    "utility not reporting ownership-type data (Ryu and Hiatt p. 6). Under row C it is absent from the mapping, and "
    "ownership_split stops in words. A missing type is never read as any ownership class.")
OWNERSHIP_SPECIFICATION_D117 = {
    "settled": OWNERSHIP_SETTLED_D117,
    "pick": OWNERSHIP_PICK_D117 + " (missing values dropped explicitly before the last nonmissing value is taken)",
    "years_searched": [OWNERSHIP_YEARS_SEARCHED[0], OWNERSHIP_YEARS_SEARCHED[-1]],
    "classification": OWNERSHIP_TIME_INVARIANT,
    "missing_entity_type": OWNERSHIP_MISSING_TREATMENT,
    "row_u_mapping": "reconciliation_mu.U_MAP, unchanged; every other entity type is 'other' and enters the pooled run only",
    "row_c_mapping": "reconciliation_c.ROW_C_OWNERSHIP_MAP, the panel's grouping; investor_owned against every other class",
}
# What the panel's entity_type column is, read as code by the agent in pipeline/electricity/panel.py build() (the
# lines that compute `ent` and join it on utility_id_eia), what was not established, and Joe's ruling of 2026-11-20 on it
# (D-119), his words carried verbatim. Said in both summaries.
PANEL_ENTITY_TYPE_STATEMENT = (
    "The panel's entity_type column (data/interim/panel_quantities.parquet) is not a year-by-year report. "
    "pipeline/electricity/panel.py build(), read as code by the agent, computes it once per utility id as the type that "
    "id's own non-imputed filings report most often (value_counts().index[0] over the rows with a type), keeps only ids "
    "whose type is one of the six distribution entity types, and joins it to every row on utility_id_eia, so it is the "
    "same in every year of a utility-state and in every state of a utility; the panel's ownership column is that type "
    "mapped by panel.OWNERSHIP_GROUP. On this panel the last nonmissing type over 2001 to 2025 and the most frequent "
    "type are therefore the same for every utility-state by construction, and the years searched change no class. "
    "Joe ruled on 2026-11-20 (D-119) that rows U and C keep this type, in his words: \"Keep the existing panel entity "
    "type for rows U and C, accurately described as the utility-level modal reported type carried across the panel, not "
    "the latest year-by-year EIA classification. No further raw-data investigation.\" The classes of rows U and C are "
    "therefore the utility-level modal reported type carried across the panel. Whether a year-by-year record of EIA's "
    "would differ for some utility was NOT established; it would need a read of the EIA-861 sales table under "
    "data/raw, which was not made, and under the same ruling no further raw-data investigation is made. Nothing here "
    "claims equivalence with EIA's year-by-year record.")


def last_nonmissing_entity_type(quantities: pd.DataFrame) -> pd.DataFrame:
    """Each utility-state's last nonmissing value of the entity_type column over the years searched
    (OWNERSHIP_YEARS_SEARCHED, 2001 to 2025), which is how rows U and C read their classes (Joe, 2026-11-20, D-117).
    Pure: takes the quantities (utility_id_eia, state, year, entity_type) and opens no file.

    On the panel that column is one type per utility id, the utility-level modal reported type carried across the
    panel, and Joe ruled on 2026-11-20 (D-119) that rows U and C keep it, described as that and not as the latest
    year-by-year EIA classification; so on the panel the value read is that type (PANEL_ENTITY_TYPE_STATEMENT). On
    invented quantities whose type changes across years it is the type of the last year that has one.

    Rows whose entity_type is missing are dropped explicitly before the last value is taken, so a unit whose type is
    missing in its last year takes the type of the last year that has one; nothing relies on a pandas default to skip a
    missing value. A unit with no type in any year stays in the result with entity_type None and entity_type_year None.
    The result has one row per utility-state (time-invariant: the class built from it is the same in every year of the
    unit).

    The years must be exactly the years searched: a frame with any year outside 2001 to 2025, or with a year of that
    range absent from the frame as a whole, is refused in words, so that a subset of years cannot pass silently (the
    session's reading of "over the existing quantity panel's 2001–2025 years"). Rows of one unit-year that carry two
    different nonmissing types stop in words, since the last would then be ambiguous (a guard on an input the panel
    does not produce, which has one row per unit-year; the agent's reading, not a research rule)."""
    rt._need(quantities, KEY + ["year", "entity_type"], "quantities")
    years = {int(y) for y in pd.unique(quantities.year)}
    want = set(OWNERSHIP_YEARS_SEARCHED)
    outside, absent = sorted(years - want), sorted(want - years)
    if outside or absent:
        raise ValueError(
            f"the ownership pick for rows U and C searches exactly {OWNERSHIP_YEARS_SEARCHED[0]} to "
            f"{OWNERSHIP_YEARS_SEARCHED[-1]} ({OWNERSHIP_SETTLED_D117}); the quantities given have years outside that "
            f"range {outside} and lack years of that range {absent}. A subset of years is not accepted.")
    q = quantities[KEY + ["year", "entity_type"]].copy()
    q["year"] = q.year.astype(int)
    units = q[KEY].drop_duplicates()
    typed = q[q.entity_type.notna()]                                   # missing types dropped explicitly, here
    clash = typed.drop_duplicates().groupby(KEY + ["year"]).entity_type.nunique()
    if (clash > 1).any():
        raise ValueError(f"{int((clash > 1).sum())} unit-years carry two different entity types; the last nonmissing "
                         f"type is ambiguous there and none is chosen")
    last = (typed.sort_values(KEY + ["year"], kind="mergesort").drop_duplicates(KEY, keep="last")
            .rename(columns={"year": "entity_type_year"}))
    out = units.merge(last, on=KEY, how="left")
    # None, not NaN, where a unit has no type: built as object Series so that pandas does not turn None into NaN or the
    # years into floats
    out["entity_type"] = pd.Series([None if pd.isna(e) else e for e in out.entity_type], index=out.index, dtype=object)
    out["entity_type_year"] = pd.Series([None if pd.isna(y) else int(y) for y in out.entity_type_year], index=out.index,
                                        dtype=object)
    return out[KEY + ["entity_type", "entity_type_year"]].reset_index(drop=True)


def adopted_row_u_ownership_classes(quantities: pd.DataFrame) -> pd.DataFrame:
    """Row U's ownership classes as Joe settled them on 2026-11-20 (D-117 and D-119). The class comes from the panel's
    entity type, the utility-level modal reported type carried across the panel, and not the latest year-by-year EIA
    classification (D-119), read as the last nonmissing value over 2001 to 2025 (last_nonmissing_entity_type, D-117),
    mapped by U_MAP unchanged, every other type "other" (pooled run only, Ryu and Hiatt p. 8). One class per
    utility-state, the same in every year. A unit with no entity type in any year gets no class (None), exactly as
    scheme U of ownership_classes gives it, so run_u_step leaves it out; it is never read as "other" or as any class.
    Takes no pick; the classification is the settled one. Returns utility_id_eia, state, ownership_class."""
    et = last_nonmissing_entity_type(quantities)
    cls = pd.Series([None if e is None else U_MAP.get(e, "other") for e in et.entity_type], index=et.index,
                    dtype=object)
    return et[KEY].assign(ownership_class=cls).reset_index(drop=True)


def ownership_classes(quantities: pd.DataFrame, scheme: str, pick: str) -> pd.DataFrame:
    """One class per unit from EIA entity types. scheme "M": public = federal, state, municipal and political
    subdivision utilities, Meeks et al.'s grouping ("public utilities (including federal, state, municipal, and
    political subdivision utilities)", p. 16, file dated 2026-10-23; MEEKS_PUBLIC_ENTITY_TYPES); other EIA types are
    "other" and enter the pooled run only (the agent's reading; the paper names no other type). scheme "U":
    Ryu and Hiatt's three classes, everything else "other" (p. 8, Sec. 3.3: political subdivisions, state and federal
    utilities "enter the pooled regression but not the ownership-specific β estimates"); under scheme "U" a unit with no
    entity type in any year gets no class, so run_u_step leaves it out (the paper keeps utilities "reporting
    ownership-type data", p. 6).

    Row U's classification is settled (Joe, 2026-11-20, D-117 and D-119): the panel's entity type, the utility-level
    modal reported type carried across the panel and not the latest year-by-year EIA classification, read as the last
    nonmissing value over 2001 to 2025, time-invariant, which adopted_row_u_ownership_classes applies with the years
    checked; row U's callers use that.
    This function is kept with its signature for dormant row M code and existing tests, and checks no years. pick:
    "last" (pandas' groupby last, which skips a missing value by its default) or "most_often"; for row M, which is
    dormant and outside D-117, the pick is still the caller's (the Meeks paper does not say, checked in session 21)."""
    rt._need(quantities, KEY + ["year", "entity_type"], "quantities")
    if scheme == "M":
        _check_m_public_types()
    mp = M_MAP if scheme == "M" else U_MAP if scheme == "U" else None
    if mp is None or pick not in ("last", "most_often"):
        raise ValueError("scheme must be 'M' or 'U' and pick 'last' or 'most_often'")
    q = quantities.sort_values(KEY + ["year"])
    if pick == "last":
        et = q.groupby(KEY).entity_type.last()
    else:
        et = q.groupby(KEY).entity_type.agg(lambda s: s.value_counts().sort_index().idxmax())
    if scheme == "U":
        cls = et.map(lambda e: None if pd.isna(e) else mp.get(e, "other"))
    else:
        cls = et.map(lambda e: mp.get(e, "other"))
    return cls.rename("ownership_class").reset_index()


def _row_u_ownership_block(q: pd.DataFrame) -> dict:
    """The summary block for row U's ownership classes under D-117 and D-119. Pure: counts on the quantities passed in
    (utility_id_eia, state, year, entity_type). Counts only. The comparison with "most often" is taken over the rows
    with a type only, so that a unit with no type is not given one by either pick."""
    adopted = adopted_row_u_ownership_classes(q).set_index(KEY).ownership_class
    et = last_nonmissing_entity_type(q).set_index(KEY)
    typed = q[q.entity_type.notna()]
    n_types = typed.groupby(KEY).entity_type.nunique()
    most = ownership_classes(typed, "U", "most_often").set_index(KEY).ownership_class if len(typed) else pd.Series(
        dtype=object)
    before = ownership_classes(q, "U", "last").set_index(KEY).ownership_class
    has = [k for k in adopted.index if adopted[k] is not None]

    def _none(x) -> bool:
        return x is None or (isinstance(x, float) and np.isnan(x))

    def _same(a, b) -> bool:
        return (_none(a) and _none(b)) or (not _none(a) and not _none(b) and a == b)
    return {
        "specification": OWNERSHIP_SPECIFICATION_D117,
        "pick": OWNERSHIP_PICK_D117,
        "years_searched": [OWNERSHIP_YEARS_SEARCHED[0], OWNERSHIP_YEARS_SEARCHED[-1]],
        "classification": OWNERSHIP_TIME_INVARIANT,
        "mapping": dict(U_MAP),
        "other_types": "every other entity type is 'other' and enters the pooled run only (Ryu and Hiatt p. 8)",
        "years_present_in_the_quantities": sorted(int(y) for y in pd.unique(q.year)),
        "utility_states": int(len(adopted)),
        "utility_states_with_more_than_one_distinct_entity_type_across_years": int((n_types > 1).sum()),
        "utilities_with_more_than_one_distinct_entity_type_across_years_and_states": int(
            (typed.groupby("utility_id_eia").entity_type.nunique() > 1).sum()),
        "utility_states_with_no_entity_type_in_any_year": int(et.entity_type.isna().sum()),
        "utility_states_whose_class_differs_last_nonmissing_against_most_often": int(
            sum(1 for k in has if most.get(k) != adopted[k])),
        "utility_states_whose_class_differs_from_the_summarys_earlier_classes": int(
            sum(1 for k in adopted.index if not _same(adopted[k], before.get(k)))),
        "earlier_classes_were": ("ownership_classes(q, 'U', 'last'), pandas' groupby last over every year of the "
                                 "quantities, which skips a missing type by its default"),
        "class_counts": {str(k): int(v) for k, v in
                         pd.Series([c if c is not None else "no class (no entity type in any year)"
                                    for c in adopted.values]).value_counts().items()},
        "no_class_is": OWNERSHIP_MISSING_TREATMENT,
        "what_the_panel_column_is": PANEL_ENTITY_TYPE_STATEMENT,
    }


# --------------------------------------------------------------------------------------------------------------------
# main: quantity-side summary only
# --------------------------------------------------------------------------------------------------------------------

def main() -> int:
    """Writes data/frozen/reconciliation_mu_design.json: how many units each buildable step treats, in which first years,
    by ownership, and how the inventory's sites are placed, and row U's quantity-side sample under the Short Form rule
    Joe adopted on 2026-11-20 (D-115). Reads facilities, facility_year, utility_year_dose, the quantity columns
    (ownership, customers) of panel_quantities, the polygon incidence tables, the Short Form filer table
    (SHORT_FORM_FILER_TABLE, written once by the authorized read and never regenerated here) and the 2019 flags
    (SHORT_FORM_FLAGS, read by name). No price, no outcome, no data/raw. If the filer table or the flags file is missing
    it stops in words, before reading anything, and writes nothing, and the raw read is not repeated."""
    absent = [p for p in (SHORT_FORM_FILER_TABLE, SHORT_FORM_FLAGS) if not Path(p).exists()]
    if absent:
        print("STOPPED, nothing written: " + "; ".join(str(p) for p in absent) + " not on disk. Row U's sample under "
              "the adopted Short Form rule is built from these records only, and the read under data/raw that wrote "
              "the filer table is not repeated.")
        return 1
    interim, frozen = INTERIM, FROZEN
    fac = pd.read_parquet(interim / "facilities.parquet")
    fy = pd.read_parquet(interim / "facility_year.parquet")
    dose = pd.read_parquet(interim / "utility_year_dose.parquet")
    q = pd.read_parquet(interim / "panel_quantities.parquet",
                        columns=KEY + ["year", "entity_type", "ownership", "res_customers"])
    units = q[KEY].drop_duplicates()
    own_m = ownership_classes(q, "M", "last").set_index(KEY).ownership_class      # row M: dormant, outside D-117
    own_u = adopted_row_u_ownership_classes(q).set_index(KEY).ownership_class     # row U: D-117
    ver = rt.assign_verified(fac)

    def in_window_units(lo, hi, states):
        w = q[(q.year >= lo) & (q.year <= hi) & q.state.isin(states)]
        return set(zip(w.utility_id_eia, w.state))

    def m_summary(tr, window, states):
        live = in_window_units(*window, states)
        t = tr.table[[k in live for k in zip(tr.table.utility_id_eia, tr.table.state)]]
        c = rt.cohort_counts(rt.Treatment(tr.rule, t, tr.excluded_sites), window)
        inside = t[(t.first_year >= window[0]) & (t.first_year <= window[1])]
        c["inside_window_by_ownership"] = {k: int(v) for k, v in pd.Series(
            [own_m.get(k, "unknown") for k in zip(inside.utility_id_eia, inside.state)]).value_counts().items()}
        c["first_treated_in_the_window_s_first_year_so_no_base_year"] = int((inside.first_year == window[0]).sum())
        return c

    out = {"what_this_is": ("Quantity-side design summary for reconciliation rows M and U (PREANALYSIS.md, 'The "
                            "reconciliation rows'): how many panel units each buildable step treats, in which first "
                            "years and by ownership class, and how the inventory places its sites. PROVISIONAL: the "
                            "design stands as of 2026-11-18, the plan is a DRAFT and not frozen, and these counts move "
                            "with the inventory. No price, revenue or outcome was read; counts are before any outcome-"
                            "based sample rule (usable price, Short Form, three classes, the paper's 3-year rule) and "
                            "before the treatment rules' own choices are settled, so each count names the choice it uses. "
                            "The one exception is short_form_flags_for_row_u, which counts row U's quantity-side sample "
                            "under the Short Form rule Joe adopted on 2026-11-20 (D-115), still with no price read."),
           "written_by": ("pipeline/analysis/reconciliation_mu.py main(), written in session 19 and extended for row U in "
                          "session 21, 2026-11-19 (the U0 assignment on the polygon incidence table and the Short Form "
                          "flags' coverage), and in session 22 for Joe's ruling D-109 (U0 on the smallest containing "
                          "polygon over every polygon, built; the four entity types listed; U0's identity with C0 to "
                          "C2 computed; the missing-coverage qualification), and in session 25, 2026-11-20, for Joe's "
                          "ruling D-115 (row U's quantity-side sample under the adopted Short Form rule, in "
                          "short_form_flags_for_row_u), and in session 26, 2026-11-20, for Joe's ruling D-117 (row U's "
                          "ownership classes from the panel's entity type read over 2001 to 2025, in "
                          "row_u_ownership_classification_d117), and for his ruling D-119 of the same day (that type "
                          "kept and described as the utility-level modal reported type carried across the panel, not "
                          "the latest year-by-year EIA classification, with no further raw-data investigation)"),
           "rows_u_and_c_status": ("Comparison-only by Joe's ruling of 2026-11-19 (D-109). " + rt.ROW_U_C_COINCIDENCE
                                   + " " + rt.MISSING_COVERAGE_QUALIFICATION),
           "ownership_classes_used_here": ("Row U: the panel's entity type of each utility-state, the utility-level "
                                           "modal reported type carried across the panel and not the latest "
                                           "year-by-year EIA classification (D-119), read as the last nonmissing value "
                                           "of the panel's column over 2001 to 2025 (D-117), one class for every year "
                                           "of the unit, mapped by "
                                           "reconciliation_mu.U_MAP, " + OWNERSHIP_SETTLED_D117 + "; "
                                           "adopted_row_u_ownership_classes, row_u_ownership_classification_d117. "
                                           "Row M, dormant and outside D-117: the unit's last reported type by "
                                           "ownership_classes(q, 'M', 'last'), mapped by M_MAP, the agent's reading "
                                           "for this summary, not a ruling."),
           "row_u_ownership_classification_d117": _row_u_ownership_block(q),
           "not_built": {
               "M0": ("county_touch needs the EIA-861 service-territory table (county by utility and state), "
                      "data/raw/pudl/core_eia861__yearly_service_territory.parquet, which this agent may not read, and a "
                      "county for every site: facilities.county_name is missing for "
                      f"{int(fac.county_name.isna().sum())} of {len(fac)} rows."),
               "M1_to_M3_county_year_counting": ("the paper's county-year summing needs each site's county; missing "
                                                 f"for {int(fac.county_name.isna().sum())} rows, so not built here.")},
           "sites": {"all_rows": int(len(fac)), "crypto": int(fac.is_crypto.sum()),
                     "verified_rule_unassigned": {k: int(v) for k, v in ver.unassigned.reason.value_counts().items()},
                     "placed_by": {k: int(v) for k, v in fac.utility_assign.value_counts().items()},
                     "with_more_than_one_candidate_territory": int((fac.n_candidates > 1).sum()),
                     "data_centers_with_size_and_year": int((~fac.is_crypto & fac.mw_full.notna() & fac.energized_year.notna()).sum()),
                     "where_the_two_size_columns_disagree_about_5_mw": int(((fac.mw_full > 5) != (fac.mw_full_raw > 5)).sum()),
                     "how_rules_differ_site_by_site": ("only the verified rule can be built from permitted files; "
                                                       "placed_by and the candidate count describe where the geometric "
                                                       "rules could differ from it, and are not those rules")},
           "steps": {}}
    for size_col in ("mw_full", "mw_full_raw"):
        tr = rt.first_year_above_size(fac, ver, units, size_column=size_col, counting="site")
        excl = tr.excluded_sites.drop_duplicates("fid").reason.value_counts()
        for step in ("M1", "M3"):
            w = M_STEPS[step]["window"]
            out["steps"][f"{step}|site|{size_col}"] = {
                "treatment_rule": tr.rule, "window": list(w), "jurisdictions": "CONTIGUOUS_48",
                "same_treatment_as": "M2 (only the price changes)" if step == "M1" else None,
                **m_summary(tr, w, CONTIGUOUS_48),
                "sites_left_out": {k: int(v) for k, v in excl.items()}}
    trd = rt.first_year_at_dose(dose, units, 0.02)
    out["steps"]["M4|dose_2pct"] = {"treatment_rule": trd.rule, "window": [2010, 2025], "jurisdictions": "CONTIGUOUS_48",
                                    **m_summary(trd, (2010, 2025), CONTIGUOUS_48), "notes": trd.notes}
    u0_assignment = rt.assign_polygon_smallest(fac, pd.read_parquet(interim / "reconciliation_polygon_incidence.parquet"),
                                               pd.read_parquet(interim / "panel_reported_ids.parquet"), **RYU_OURS_POLYGON)
    for src in (RYU_OURS_MW_SOURCE,):          # row U's specification since D-107; the other source is not built
        for step in ("U0", "U1", "U3"):
            w = U_STEPS[step]["window"]
            asg = u0_assignment if step == "U0" else ver
            tr = rt.cumulative_mw(asg, units, range(w[0], w[1] + 1), src, site_year=fy, sites=fac)
            live = in_window_units(*w, FIFTY_STATES_AND_DC)
            t = tr.table[[k in live for k in zip(tr.table.utility_id_eia, tr.table.state)]]
            pos = t[t.mw > 0]
            first_pos = pos.groupby(KEY).year.min()
            any_units = list(first_pos.index)
            out["steps"][f"{step}|{src}"] = {
                "treatment_rule": tr.rule, "window": list(w), "jurisdictions": "FIFTY_STATES_AND_DC",
                "same_treatment_as": "U2 (only the price changes)" if step == "U1" else None,
                "units_in_window": len(live), "units_with_mw_above_zero_in_some_window_year": len(any_units),
                "of_which_by_ownership": {k: int(v) for k, v in pd.Series([own_u.get(k, "unknown") for k in any_units]).value_counts().items()},
                "first_window_year_with_mw_above_zero": {int(k): int(v) for k, v in first_pos.value_counts().sort_index().items()},
                "units_above_zero_in_the_first_window_year": int((first_pos == w[0]).sum()),
                "units_whose_mw_comes_from_another_state_of_the_same_utility": int(len({
                    k for k in any_units if k not in set(zip(asg.table.utility_id_eia, asg.table.state))})),
                "unit_years_with_mw_above_zero": int(len(pos)),
                "sites_left_out": {k: int(v) for k, v in tr.excluded_sites.drop_duplicates("fid").reason.value_counts().items()},
                "missing_coverage": rt.MISSING_COVERAGE_QUALIFICATION,
                "notes": tr.notes}
            if step == "U0":
                out["steps"][f"{step}|{src}"]["assignment_rule"] = rt.ROW_U_POLYGON_LABEL
                out["steps"][f"{step}|{src}"]["coincidence_with_row_c"] = rt.ROW_U_C_COINCIDENCE
    out["U0_assignment_on_the_real_layer"] = _u0_on_the_layer(fac, interim)
    sf_flags = pd.read_parquet(SHORT_FORM_FLAGS)
    sf_table = pd.read_parquet(SHORT_FORM_FILER_TABLE)
    sf_table["state"] = sf_table.state.astype("string")
    out["short_form_flags_for_row_u"] = _short_form_for_row_u(q, own_u, sf_flags, sf_table)
    path = DESIGN_SUMMARY
    path.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print("wrote", path.relative_to(ROOT))
    return 0


def _u0_on_the_layer(fac: pd.DataFrame, interim: Path) -> dict:
    """U0's assignment on data/interim/reconciliation_polygon_incidence.parquet under row U's rule (ROW_U_POLYGON, the
    smallest containing polygon over every polygon, the type not read; D-109), every site accounted for; the list of
    the sites associated with the four entity types, from data/interim/reconciliation_polygon_incidence_types.parquet;
    and the site-by-site identity with C0 to C2's assignment, computed. Quantity-side only; reads no file under
    data/raw."""
    inc = pd.read_parquet(interim / "reconciliation_polygon_incidence.parquet")
    typed = pd.read_parquet(interim / "reconciliation_polygon_incidence_types.parquet")
    rep_ids = pd.read_parquet(interim / "panel_reported_ids.parquet")
    a = rt.assign_polygon_smallest(fac, inc, rep_ids, **RYU_OURS_POLYGON)
    c = rt.assign_polygon_smallest(fac, inc, rep_ids, **rt.ROW_C_POLYGON)
    dc = fac[~fac.is_crypto.fillna(False).astype(bool)]
    no_point = set(dc.fid[dc.lat.isna() | dc.lon.isna()]) if {"lat", "lon"} <= set(dc.columns) else set()
    un = a.unassigned.drop_duplicates("fid").set_index("fid").reason
    in_dc = un[un.index.isin(set(dc.fid))]
    # the typed table is the same incidence with the layer's TYPE value: checked here row for row on its four columns
    same = (len(typed) == len(inc) and list(typed.fid.astype(str)) == list(inc.fid.astype(str))
            and np.allclose(typed.area.to_numpy(float), inc.area.to_numpy(float), rtol=0, atol=1e-9)
            and bool((typed.utility_id_reported.astype("Int64") == inc.utility_id_reported.astype("Int64")).all()))
    if not same:
        raise ValueError("the typed incidence table does not match the incidence table row for row; rebuild it with "
                         "reconciliation_inputs.py --types-only")

    def kind(r: str) -> str:
        if r.startswith("its unit depends on how the ambiguous") or r.startswith("inside "):
            return "depends_on_ambiguous_polygon_classes"
        for k in ("no territory polygon contains the site", "only wholesale-only polygons contain the site",
                  "tie in area", "not a panel unit", "the site has no state"):
            if r.startswith(k) or k in r:
                return k
        return r
    kinds = pd.Series([kind(r) for r in in_dc.values], index=in_dc.index)
    none_kind = kinds[kinds == "no territory polygon contains the site"]
    ties = {f: un[f] for f in kinds[kinds == "tie in area"].index}
    ident = rt.identical_site_by_site(a, c, dc.fid)
    lst = rt.entity_type_list(fac, typed, a)
    return {
        "status": ("BUILT on the real quantity files (no price read): U0's assignment by Joe's ruling of 2026-11-19 "
                   "(D-109), the smallest containing polygon over every polygon of the layer, the type not read, as our "
                   "labelled approximation. Before D-109 row U used retail first, and every polygon of this layer being "
                   "classed ambiguous, U0 placed 0 of 2,203 data center sites and was stopped. U0 itself is a regression "
                   "on price and waits for the freeze."),
        "rule": a.rule, "rule_label": rt.ROW_U_POLYGON_LABEL,
        "coincidence_with_c0_to_c2": rt.ROW_U_C_COINCIDENCE,
        "missing_coverage": rt.MISSING_COVERAGE_QUALIFICATION,
        "inputs": ["data/interim/reconciliation_polygon_incidence.parquet",
                   "data/interim/reconciliation_polygon_incidence_types.parquet",
                   "data/interim/panel_reported_ids.parquet", "data/interim/facilities.parquet"],
        "typed_incidence_table": ("data/interim/reconciliation_polygon_incidence_types.parquet, written by "
                                  "reconciliation_inputs.py --types-only on 2026-11-19 (session 22) from one read of the "
                                  "territory layer by ID, TYPE and geometry (D-109); its fid, utility_id_reported and "
                                  "area match the incidence table row for row (checked here and when it was written)"),
        "incidence_rows": int(len(inc)), "polygon_ids_containing_a_site": int(inc.utility_id_reported.nunique()),
        "polygons_in_layer": "2,931 (data/frozen/reconciliation_polygon_incidence_summary.json, counts.polygons_in_layer)",
        "type_class_read": False,
        "inventory_rows": int(len(fac)), "crypto_rows_not_counted": int(len(fac) - len(dc)),
        "data_center_sites": int(len(dc)),
        "data_center_sites_assigned_to_a_panel_unit": int(a.table[a.table.fid.isin(set(dc.fid))].fid.nunique()),
        "data_center_sites_listed_as_depending_on_ambiguous_polygons": int(len(a.depends_on_ambiguous)),
        "data_center_sites_with_no_point": int(len(no_point)),
        "data_center_sites_with_a_point_in_no_polygon": int(len(set(none_kind.index) - no_point)),
        "data_center_sites_unassigned_by_kind": {k: int(v) for k, v in kinds.value_counts().items()},
        "exact_area_ties_not_broken": ties,
        "before_d109": {"rule": "polygon_smallest (retail first, D-107)", "data_center_sites_assigned_to_a_panel_unit": 0,
                        "data_center_sites_listed_as_depending_on_ambiguous_polygons": 2192},
        "identity_with_c0_to_c2_site_by_site": {
            **{k: (len(v) if k == "differ" else v) for k, v in ident.items()},
            "differing_fids": ident["differ"],
            "what_it_means": "one rule applied twice; not independent validation (rt.ROW_U_C_COINCIDENCE)"},
        "entity_type_list": lst,
        "note": ("A site with no point has no incidence row and is listed by the assignment as in no polygon; it is "
                 "counted here apart, from facilities.parquet's lat and lon."),
    }


def _short_form_for_row_u(q: pd.DataFrame, own_u: pd.Series, flags: pd.DataFrame, table: pd.DataFrame) -> dict:
    """The Short Form flags' coverage, and row U's quantity-side sample under the Short Form rule Joe adopted on
    2026-11-20 (D-115). Pure: takes the quantities, the scheme U ownership classes, the 2019 flags (the whole flags file)
    and the filer table, all passed in by main(). Quantity-side only; no price read.

    short_form_filers imports this module at its top, so short_form_filers is imported here, inside the function, and
    not at this module's top; nothing else about either module changes (the agent's resolution of the circular
    import)."""
    from pipeline.analysis import short_form_filers as sff   # lazy: short_form_filers imports this module
    f = flags
    lo, hi = RYU_WINDOW
    fw = f[(f.year >= lo) & (f.year <= hi)]
    # row U's quantity-side frame: unit-years in the window and the 51 jurisdictions with an ownership class (scheme U),
    # then the three-year count on those rows. A stand-in: the paper's rules on price (a missing price) cannot be applied
    # without reading price.
    w_pre = q[(q.year >= lo) & (q.year <= hi) & q.state.isin(RYU_OURS_JURISDICTIONS)][KEY + ["year"]].drop_duplicates()
    w_pre = w_pre[[own_u.get(k) is not None for k in zip(w_pre.utility_id_eia, w_pre.state)]]
    w, _ = _min_years(w_pre, RYU_MIN_YEARS, RYU_MIN_YEARS_LEVEL)
    m = w.merge(f.drop_duplicates(KEY + ["year"])[KEY + ["year", "short_form"]], on=KEY + ["year"], how="left",
                indicator=True)
    adopted = sff.adopted_row_u_sample(w_pre, table, f)
    # Step U3 runs on 2015 to 2025, one year past row U's own window. The adopted rule is applied year by year over the
    # step's window (short_form_filers.adopted_row_u_flags, step_window; the session's reading, Joe's to strike). What
    # that does in 2025, counted on the quantity side:
    lo3, hi3 = U_STEPS["U3"]["window"]
    w3 = q[(q.year >= lo3) & (q.year <= hi3) & q.state.isin(RYU_OURS_JURISDICTIONS)][KEY + ["year"]].drop_duplicates()
    w3 = w3[[own_u.get(k) is not None for k in zip(w3.utility_id_eia, w3.state)]]
    f3 = sff.adopted_row_u_flags(w3, table, f, step_window=(lo3, hi3))
    past = f3[f3.year > hi]
    step_u3 = {
        "what_this_is": ("Step U3's window is 2015 to 2025. The rule Joe adopted is stated for a utility-state-year, so for "
                         "this step it is applied year by year over the step's own window (the session's reading, his to "
                         "strike). Counted here on the quantity side, before the three-year count: the unit-years of the "
                         "years past row U's own window, and how many of them a record shows as a filing. Where that count "
                         "is zero, this reading and a reading with no exclusion in those years give the same flags."),
        "window": [int(lo3), int(hi3)],
        "unit_years_before_the_three_year_count": int(len(w3)),
        "unit_years_in_the_years_past_row_us_own_window": {str(int(y)): int(n) for y, n in past.groupby("year").size().items()},
        "of_them_with_a_record_of_a_filing": int(past.short_form.astype(bool).sum()),
        "of_them_kept_with_no_record_of_a_filing": int((~past.short_form.astype(bool)).sum()),
        "flags_of_row_us_own_window_equal_under_either_window": bool(
            f3[f3.year <= hi].sort_values(KEY + ["year"]).short_form.astype(bool).tolist()
            == sff.adopted_row_u_flags(w_pre, table, f).sort_values(KEY + ["year"]).short_form.astype(bool).tolist()),
    }
    return {
        "status": ("The Short Form rule for row U was adopted by Joe on 2026-11-20 (D-115) and is applied below, on the "
                   "quantity side, in sample_under_the_adopted_short_form_rule. " + U_SHORT_FORM_ADOPTED_LABEL
                   + " The records are the filer table (data/interim/reconciliation_short_form_filers.parquet, written "
                   "once by the authorized read of 2026-11-20, D-113, and not regenerated) and the 2019 flags "
                   "(data/interim/reconciliation_short_form_flags.parquet); the read under data/raw is not repeated. "
                   "The flag in the flags file is True on some rows of 2019 and missing on every other row, and it is "
                   "never False; under the adopted rule only a flag of true in 2019 is read as a record of a filing. "
                   "Whether this flag is what the paper means by Short Form filers (endnote 10, p. 17) is not "
                   "established."),
        "table": "data/interim/reconciliation_short_form_flags.parquet",
        "filer_table": "data/interim/reconciliation_short_form_filers.parquet",
        "filer_table_rows": int(len(table)),
        "rows": int(len(f)), "years": [int(f.year.min()), int(f.year.max())],
        "rows_by_year": {int(k): int(v) for k, v in f.groupby("year").size().items()},
        "short_form_true_rows": int((f.short_form == True).sum()),                       # noqa: E712
        "short_form_false_rows": int((f.short_form == False).sum()),                     # noqa: E712
        "short_form_missing_rows": int(f.short_form.isna().sum()),
        "short_form_true_rows_by_year": {int(k): int(v) for k, v in
                                         f[f.short_form == True].groupby("year").size().items()},  # noqa: E712
        "data_observed_false_rows": int((~f.data_observed.astype(bool)).sum()),
        "rows_sharing_a_unit_year_with_another_row": int(f.duplicated(KEY + ["year"], keep=False).sum()),
        "window_rows": int(len(fw)),
        "row_u_quantity_sample_in_the_window": {
            "what_this_is": ("row U's frame with no Short Form exclusion, the frame the adopted rule is applied to: "
                             "unit-years 2015-2024 in the 50 states and DC with an ownership class (scheme U, the "
                             "panel's entity type, the utility-level modal reported type carried across the panel, read "
                             "over 2001 to 2025; D-117 and D-119) and the three-year count on "
                             "those rows; no price was read, so the paper's "
                             "missing-price drop is not applied. NOT the paper's sample."),
            "unit_years": int(len(w)), "units": int(w[KEY].drop_duplicates().shape[0]),
            "utilities": int(w.utility_id_eia.nunique()),
            "unit_years_with_no_flag_row": int((m._merge == "left_only").sum()),
            "unit_years_with_a_missing_flag": int(((m._merge == "both") & m.short_form.isna()).sum()),
            "unit_years_flagged_true": int((m.short_form == True).sum()),                  # noqa: E712
        },
        "sample_under_the_adopted_short_form_rule": adopted,
        "step_u3_window_under_the_adopted_rule": step_u3,
        "data_observed_is_read": False,
    }


if __name__ == "__main__":
    sys.exit(main())
