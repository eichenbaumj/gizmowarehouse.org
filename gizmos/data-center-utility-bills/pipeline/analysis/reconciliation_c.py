#!/usr/bin/env python3
"""Reconciliation row C (Scalera, Bosetti and Pecci, CEPR DP21854): steps C0 to C4 and the test C5.

What the plan fixes (PREANALYSIS.md, "The reconciliation rows (reported first, whatever they show)", Row C). Their
specification: residential price in cents per kWh, real 2024 dollars, in levels, on the count of operating facilities
in the utility-state, capped each year at the 99.5th percentile; utility-state and state-by-year fixed effects;
clustered by utility-state; balanced panel 2015-2024. Instrument: an indicator for 2021 onward, times log national
private data center construction spending (Census), times the territory's 2017-2019 share of the nation's census
blocks with fiber to the premises. Their numbers: instrumented 0.182 (SE 0.034), first-stage F 59; uninstrumented
0.061 (0.018); with the cap removed, at the 99.9th and at the 99th percentile 0.110, 0.150, 0.236. The plan's bands
(0.025 to 0.097 uninstrumented; 0.114 to 0.250 instrumented with a first-stage F of at least 10) are kept as
comparison bands and shown beside our estimates; no step returns a reproduction verdict (below). Steps in order: C0
uninstrumented on their assignment rule (smallest overlapping polygon); C1 instrumented; C2 the cap removed, then at
the 99.9th and 99th percentiles; C3 the inventory's own assignment in place of the polygon; C4 our load share in place
of the facility count, same instrument. By investor-owned versus all other at C1 and C3. C5 is the instrument's direct
relationship with price (the reduced form) on utility-states that host no facility in any year, against the same
relationship on the full sample, read three ways.

What may be claimed (Joe, 2026-11-19, D-107 and D-109). "The instrumented comparisons cannot support reproduction
claims given the spatial-construction difference and the spending-unit approximation. Retain them only as explicitly
labelled comparisons under our specification" (D-107), and comparison-only status for C0 and the instrumented
comparisons is adopted (D-109). Every instrumented result (C1, C2, C3, C4, the ownership split at C1 and C3, and the
full-sample yardstick at C5) carries C_INSTRUMENTED_COMPARISON_LABEL and no verdict. C0 carries C0_COMPARISON_LABEL,
with the paper's figure and band beside it as a comparison band and no verdict. C5's two sentences are Joe's adopted
wording (D-109). Every result built on an assignment carries the missing-coverage qualification
(reconciliation_treatment.MISSING_COVERAGE_QUALIFICATION), and C5 says what its operational never-host classification
cannot establish without changing that classification (C5_NEVER_HOST_LIMITATION). C0 to C2's assignment is the same
rule as row U's U0 (reconciliation_treatment.ROW_U_C_COINCIDENCE). No code path here returns a reproduction verdict.

This study's approximations (D-107). Where the paper does not state an element, the row's specification is ours,
adopted by Joe on 2026-11-19 (D-107, accepting D-106's R5), labelled so in OURS_APPROXIMATIONS and carried by
SPECIFICATION; check_specification refuses any other value in words, and keeps the paper's settled values apart from
ours in its words. The price deflator is held the same way, as this study's convention adopted by Joe on 2026-11-19
(D-111), with its own label (PRICE_DEFLATOR_LABEL), and so is the nominal price series, our comparison specification
settled by Joe on 2026-11-20 (D-117; PRICE_SERIES_LABEL). The elements whose exact reproduction is unavailable are in
UNAVAILABLE and every result says so.

The bounded read (2026-11-19). The paper itself (docs/research/papers/scalera_cepr_dp21854/DP21854.pdf, revision of
2 November 2026) was read once in full under Joe's ruling of 2026-11-19; the findings, with page, section and table
for each, are in docs/gate1/bounded-read-row-c-2026-11-19.md. Page numbers below are the paper's printed page numbers
(printed page n is page n + 3 of the 82-page PDF). What the paper settles is carried as the constants under "The paper's
specification" and checked where it is used (`check_paper_settled`); what it does not settle is still a field of
`Choices` or a required argument with no default.

Nothing here opens a price file. Every function that will one day take residential price takes it as an argument:
a frame with columns utility_id_eia, state, year and a value column (default name "value"). THE CALLER must supply
residential price in cents per kWh in real 2024 dollars, in levels (the paper's, Table 1 notes, p. 13), converted to
2024 dollars with row C's deflator and no other. The paper converts with "the Consumer Price Index (CPI)" (section
2.1, p. 4; the same words without the series name in the notes to Table S2, p. 30, and for spending in section S1.5,
p. 33, and the notes to Table S3, p. 34) and does not name the series. Row C's deflator is the CPI-U annual average
(BLS CUUR0000SA0), held as column cpi_u of data/frozen/dc_construction_spending.csv (2014-2025; 313.689 for 2024),
applied through `cpi_factors_to_2024`, which returns the factor cpi_u[2024] / cpi_u[year] from that table and nothing
else: ours, not the paper's, this study's convention, adopted by Joe on 2026-11-19 (D-111) (OURS_PRICE_DEFLATOR,
PRICE_DEFLATOR_LABEL). It is carried by SPECIFICATION as Choices.price_deflator, so the caller does not choose it, and
check_specification refuses any other value in words. Our Census spending series deflated with this series equals
the paper's printed Table S3 at printed precision for 2015 to 2023 (data/frozen/instrument_report.json,
table_S3_check_real_2024_bn), which supports and does not establish that it is the paper's series; that the paper
used it for price is not established. Nothing is fetched for it. The paper builds
price as revenue over sales from the EIA-861 "Sales to Ultimate Customers" files ("dividing total revenue by total
sales, specific to each sector", section S1.3, p. 29) and does not say whether delivery-only or energy-only rows
enter. Row C's nominal series is the panel's delivery-inclusive res_price (OURS_PRICE_SERIES), which
pipeline/electricity/panel.py build() computes as res_revenue_full / res_mwh / 10.0, already in cents per kWh, with
competitive supply added for delivery-only customers: our comparison specification, settled by Joe on 2026-11-20
(D-117), and not a claim that the paper used exactly this construction (PRICE_SERIES_LABEL). It is carried by
SPECIFICATION as Choices.price_series and check_specification refuses any other value in words. No change of unit is
needed; putting each year's value in real 2024 cents per kWh with cpi_factors_to_2024's factor is done by the caller
before the frame is supplied, as settled (D-111 and D-117), and is not done here. The module checks the series a caller states and cannot detect a frame that was in fact built from
another column (PRICE_SERIES_NOT_CHECKED).

Ownership (Joe, 2026-11-20, D-117 and D-119). The classes for the ownership split at C1 and C3 come from the panel's
entity type of each utility-state, the utility-level modal reported type carried across the panel, and not the latest
year-by-year EIA classification (D-119), read as the last nonmissing value of the panel's column over 2001 to 2025
(D-117), one class for every year of the unit, mapped by ROW_C_OWNERSHIP_MAP (adopted_row_c_ownership); a unit with no
type in any year is absent from the mapping and the split stops in words on it. The description, the years searched,
what the panel's entity_type column is and Joe's ruling on it are held in reconciliation_mu
(OWNERSHIP_SPECIFICATION_D117, OWNERSHIP_DESCRIPTION_D119, PANEL_ENTITY_TYPE_STATEMENT), shared with row U.

The estimator is self-contained (no linearmodels, no pyfixest): exact removal of the two sets of fixed effects by
alternating projections to a stated tolerance, OLS and two-stage least squares, cluster-robust variance by
utility-state, the cluster-robust first-stage F on the excluded instrument(s), and the reduced form.

The first-stage F. The paper says first-stage F statistics are "cluster-robust" (notes to Tables 1, S5, S6, S14) and,
for its interaction models, "calculated following Sanderson and Windmeijer (2016)" (Table 3 notes, p. 17). With one
excluded instrument and one endogenous regressor this module's F is the squared cluster-robust t of the first-stage
coefficient; the paper's printed 0.849 (0.11) and F 59.43 (Table S5, p. 37) agree with that to rounding
(0.849 / 59.43^0.5 = 0.1101). With one instrument the Kleibergen-Paap Wald F and the effective F reduce to the same
statistic up to the small-sample factor; that equivalence is the agent's reading of the econometrics, not the paper's.

Small-sample correction. The paper says only that standard errors are "clustered at the utility-State level"
(footnote 10, p. 10; notes to Tables 1, S5, S6, S14). It names no regression software (R is named only for geocoding,
section S1.2, p. 26) and no finite-sample correction, so exact reproduction of its errors is unavailable. Row C's
specification uses "cr1_stata", the usual clustered correction for the number of clusters and parameters, labelled
ours (D-107; that R5's "the usual clustered correction" for row C means this one, the same formula as row U's, is the
agent's reading). The three the estimator computes:
  "none"        V = (X'X)^-1 meat (X'X)^-1, no scaling.
  "cr1_cluster" scaled by G/(G-1).
  "cr1_stata"   scaled by G/(G-1) * (N-1)/(N-K), the default of Stata's reghdfe for clustered OLS; K counts the slope
                coefficients plus the degrees of freedom of the fixed effects that are not nested within the clusters.
                The utility-state effects are nested in the utility-state clusters and count zero; the state-by-year
                effects count their number of levels less the number of connected components of the bipartite graph
                of utility-states and state-years (the redundant ones). This is the agent's reading of reghdfe's
                default and I am uncertain that it matches reghdfe's count exactly in every layout.
Nothing in the paper points to any of the three. On a panel the size of theirs (1,237 clusters, 12,370 rows, under 500
absorbed state-years) the three choices move a standard error by about 2% at most.

Settled by the read (constants below, checked where used): the share enters in percent, the sample is the contiguous
states, the ownership split is the paper's interaction model with "nonprofit" meaning anything but investor-owned,
the cap is taken within each year, a site counts every year from its start year on, and the smallest overlapping
polygon over every territory. Ours (D-107, OURS_*): the percentile's population and formula, spending in billions
inside the log, singleton groups dropped, December filings, the small-sample correction, the cap at C4, and at C5 the
never-host basis, the hosts' assignment, the spending series and the interval. Ours (D-111): the price deflator
(OURS_PRICE_DEFLATOR). Our comparison specification (D-117): the nominal price series (OURS_PRICE_SERIES).
`Choices` keeps its fields, with no
defaults, so that a caller states each one; SPECIFICATION carries the accepted values and check_specification refuses
any other in words.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.analysis import reconciliation_treatment as rt  # noqa: E402
# Row C's ownership specification (D-117 and D-119) is held in reconciliation_mu beside row U's; that module imports
# neither this one nor short_form_filers at its top, so there is no import cycle.
from pipeline.analysis import reconciliation_mu as rmu  # noqa: E402
FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
OUT = FROZEN / "reconciliation_c_design.json"

KEYS = ["utility_id_eia", "state"]

# ---------------------------------------------------------------------------------------------------------------
# The paper's specification, as settled by the bounded read (docs/gate1/bounded-read-row-c-2026-11-19.md).
# Each constant names where the paper says it (printed page numbers).
# ---------------------------------------------------------------------------------------------------------------
YEARS = tuple(range(2015, 2025))           # 2015-2024, balanced (plan; paper section S1.3, p. 30)
POST_FROM = 2021                           # "an indicator for years 2021 and onward" (paper section 3, p. 8)
CAP_MAIN = 99.5                            # "winsorize ... at the 99.5th percentile within-year" (paper footnote 3, p. 8)
C2_CAPS = (None, 99.9, 99.0)               # the cap removed, then the 99.9th and the 99th (plan, step C2; paper Table S14)
CAP_WITHIN_YEAR = True                     # "beyond the 99.9th percentile of that year's distribution" (paper S2.8, p. 50)
SHARE_IN_PERCENT = True                    # "the percent of national, fiber-containing Census blocks" (paper S2.1, p. 35);
                                           # the share's SD is 0.19 in the first-stage reading (S2.2, p. 36; Table S4)
OWNERSHIP_METHOD = "interaction"           # Table 3 col 1 (p. 17) and the double first stage of S2.19 (p. 78)
OWNERSHIP_OTHER_RULE = "every class except investor_owned"   # "anything except an investor-owned utility" (Table 3 notes)
CONTIGUOUS_ONLY = True                     # "a utility-by-State-by-year panel ... in the contiguous U.S." (section 2.1, p. 4)
FIBER_TECHNOLOGY_CODE = 50                 # "technology code 50, corresponding to 'fiber to end user'" (S1.5, p. 33)
FIBER_YEARS = (2017, 2018, 2019)           # mean of the yearly shares over 2017-2019 (section 3, p. 9; S1.5, p. 34)
SHARE_COLUMN = "fiber_share_dec"           # December Form 477 filings: ours, adopted by Joe on 2026-11-19 (D-107; the
                                           # plan's D-16 choice); the paper says only "annually" (S1.5, p. 33)
# The 48 contiguous states and D.C. The paper's price panel is "the contiguous U.S." (section 2.1, p. 4); its 3,805
# territories are "in the contiguous United States" (S1.1, p. 25); the plan's national fiber total is "over the 48
# states and D.C.".
NON_CONTIGUOUS = frozenset({"AK", "HI", "PR", "GU", "VI", "AS", "MP"})


# This study's approximations, OURS and not the paper's, adopted by Joe on 2026-11-19 (D-107, accepting D-106's R5).
OURS_D107 = "ours, not the paper's: this study's approximation, adopted by Joe on 2026-11-19 (D-107)"
OURS_PERCENTILE_METHOD = "stata_default"           # the order-statistic formula
OURS_CAP_POPULATION = "estimation_sample"          # the step's estimation sample in that year, zeros included
OURS_SPENDING_LOG_UNIT = "billions"                # billions of real 2024 dollars inside the log
OURS_SMALL_SAMPLE = "cr1_stata"                    # the usual clustered correction for clusters and parameters
OURS_DROP_SINGLETONS = True
OURS_C4_CAP = CAP_MAIN                             # at C4 the same within-year cap on the load share as on the count
OURS_NEVER_HOST_BASIS = "zero_count_panel_years"   # C5: no facility counted in any panel year
OURS_C5_HOSTS_FROM = "the inventory's own assignment (counts_verified)"
OURS_C5_SPENDING = ("paper", "current")            # the paper's printed series, with the current Census series beside it
OURS_INTERVAL = "t_G_minus_1"                      # C5: a t interval on the number of utility-state clusters less one
# Row C's price deflator, ours and not the paper's: this study's convention, adopted by Joe on 2026-11-19 (D-111), "the
# existing CPI-U annual series as our labelled convention, with no new fetch". The CPI-U annual average (BLS
# CUUR0000SA0), column cpi_u of data/frozen/dc_construction_spending.csv, applied through cpi_factors_to_2024.
OURS_PRICE_DEFLATOR = "cpi_u_annual_average"
DEFLATOR_SERIES_ID = "CUUR0000SA0"
DEFLATOR_TABLE = "data/frozen/dc_construction_spending.csv"
DEFLATOR_COLUMN = "cpi_u"
DEFLATOR_BASE_YEAR = 2024
OURS_D111_DEFLATOR = "ours, not the paper's: this study's convention, adopted by Joe on 2026-11-19 (D-111)"
PRICE_DEFLATOR_LABEL = (
    OURS_D111_DEFLATOR + ". The price is put in real 2024 dollars with the CPI-U annual average (BLS " + DEFLATOR_SERIES_ID
    + "), column " + DEFLATOR_COLUMN + " of " + DEFLATOR_TABLE + ", the factor cpi_u[2024] / cpi_u[year] "
    "(cpi_factors_to_2024); nothing is fetched for it. The paper says only \"the CPI\" (section 2.1, p. 4; notes to "
    "Table S2, p. 30) and names no series. Our Census spending series deflated with this series equals the paper's "
    "printed Table S3 at printed precision for 2015 to 2023, which supports and does not establish that it is the "
    "paper's series; that the paper used it for price is not established.")
# Row C's nominal price series, settled by Joe on 2026-11-20 (D-117), in his words: "Use this study's delivery-inclusive
# `res_price`, in cents per kWh, converted to real 2024 cents per kWh using the already adopted CPI-U annual convention.
# Label this as our comparison specification, not a claim that the paper used exactly this construction. No fetch, new
# price read or alternative price-series exercise is authorized." The series is the panel's res_price, which
# pipeline/electricity/panel.py build() computes as res_revenue_full / res_mwh / 10.0 (read as code): residential revenue
# over residential sales for bundled and delivery-only customers together, the supply of delivery-only customers priced
# at the state's observed supplier average (or, where none is observed and delivery-only customers are 1% of the unit's
# residential sales or less, at the unit's own implied supply price). Nominal, cents per kWh. The caller multiplies each
# year's value by cpi_factors_to_2024's factor for that year to put it in real 2024 cents per kWh.
OURS_PRICE_SERIES = "res_price"
PRICE_SERIES_UNIT = "cents per kWh, nominal (before row C's deflator)"
PRICE_SERIES_REAL_UNIT = "cents per kWh, real 2024 dollars (after cpi_factors_to_2024)"
PRICE_SERIES_CONSTRUCTION = (
    "res_revenue_full / res_mwh / 10.0, as pipeline/electricity/panel.py build() computes it (read as code): residential "
    "revenue over residential sales, bundled and delivery-only customers together, with the supply of delivery-only "
    "customers priced at the state's observed supplier average, or, where no supplier row is observed and delivery-only "
    "customers are 1% of the unit's residential sales or less, at the unit's own implied supply price; where neither "
    "applies the price is missing")
SETTLED_D117_PRICE = "settled by Joe on 2026-11-20 (D-117)"
PRICE_SERIES_LABEL = (
    "Our comparison specification, " + SETTLED_D117_PRICE + ", and not a claim that the paper used exactly this "
    "construction. Row C's nominal price is this study's delivery-inclusive res_price (" + PRICE_SERIES_CONSTRUCTION
    + "), in cents per kWh, put in real 2024 cents per kWh with row C's deflator (the CPI-U annual convention, D-111). "
    "The paper divides total residential revenue by total residential sales from the EIA-861 Sales to Ultimate "
    "Customers files (section S1.3, p. 29) and does not say whether delivery-only or energy-only rows enter. No other "
    "price series is built or compared, and nothing is fetched or read for it.")
PRICE_SERIES_NOT_CHECKED = (
    "This module checks the series a caller states (Choices.price_series); it cannot detect an outcome frame that was "
    "in fact built from another column. That the frame's values are res_price, deflated by cpi_factors_to_2024, is the "
    "caller's responsibility.")
OURS_APPROXIMATIONS = {
    "cap_population": {"value": OURS_CAP_POPULATION, "label": OURS_D107,
                       "paper": "\"that year's distribution\" (S2.8, p. 50); the population is not named"},
    "percentile_method": {"value": OURS_PERCENTILE_METHOD + " (order statistic)", "label": OURS_D107,
                          "paper": "no formula; capped maxima print as whole numbers (Table S14, p. 51)"},
    "spending_log_unit": {"value": "billions of real 2024 dollars", "label": OURS_D107,
                          "paper": "\"the natural log of national data center construction spending\" (p. 8), no unit; "
                                   "the series is printed in billions (Table S3, p. 34)"},
    "singleton_groups": {"value": "dropped, iterated", "label": OURS_D107,
                         "paper": "not stated; 49 states and 1,243 units fall to 48 and 1,237 unexplained"},
    "fiber_filings": {"value": "December Form 477 filings (" + SHARE_COLUMN + ")", "label": OURS_D107,
                      "paper": "\"annually\" (S1.5, p. 33); no release named"},
    "small_sample": {"value": OURS_SMALL_SAMPLE + " (G/(G-1) x (N-1)/(N-K))", "label": OURS_D107,
                     "paper": "clustered by utility-state; no correction or software named"},
    "c4_cap": {"value": f"the {OURS_C4_CAP}th percentile within year, as on the count", "label": OURS_D107,
               "paper": "no load share; both of its own measures are capped this way (Table 1 notes, p. 13)"},
    "c5_never_host": {"value": "no facility counted in any panel year (" + OURS_NEVER_HOST_BASIS + ")",
                      "label": OURS_D107,
                      "paper": "its never-treated group has no data center presence throughout (Table S11, p. 46)"},
    "c5_hosts_from": {"value": OURS_C5_HOSTS_FROM, "label": OURS_D107, "paper": "C5 is ours; no such test"},
    "c5_spending": {"value": "the paper's printed series (Table S3), the current Census series beside it",
                    "label": OURS_D107, "paper": "C5 is ours; no such test"},
    "c5_interval": {"value": "t with the number of utility-state clusters less one degrees of freedom",
                    "label": OURS_D107, "paper": "C5 is ours; its one clustered joint test prints G - 1 (Table S24)"},
    "price_deflator": {"value": ("the CPI-U annual average (BLS " + DEFLATOR_SERIES_ID + "), " + DEFLATOR_COLUMN + " in "
                                 + DEFLATOR_TABLE + ", factors cpi_u[2024]/cpi_u[year] (" + OURS_PRICE_DEFLATOR + ")"),
                       "label": PRICE_DEFLATOR_LABEL,
                       "paper": "\"the Consumer Price Index (CPI)\" (section 2.1, p. 4; Table S2 notes, p. 30); no "
                                "series named"},
    "price_series": {"value": (OURS_PRICE_SERIES + ", " + PRICE_SERIES_UNIT + ": " + PRICE_SERIES_CONSTRUCTION),
                     "label": PRICE_SERIES_LABEL,
                     "paper": "\"dividing total revenue by total sales, specific to each sector\" (section S1.3, p. 29); "
                              "whether delivery-only or energy-only rows enter is not stated"},
}
# Outcome 3 of the bounded read: exact reproduction unavailable (D-106 section 6). Said in every result.
UNAVAILABLE = (
    "the paper's small-sample correction and software are not stated",
    "why the paper's sample falls from 1,243 units with ten years of price to 1,237 in its regressions is not explained",
    "whether the paper's price includes delivery-only or energy-only rows is not stated",
)

# What row C may claim (Joe, 2026-11-19, D-107 and D-109). Comparison-only; no row C result carries a reproduction
# verdict.
C_INSTRUMENTED_COMPARISON_LABEL = (
    "Comparison-only, by Joe's ruling of 2026-11-19 (D-109). A comparison under our specification, to which no "
    "reproduction claim attaches. Our fiber share places each "
    "census block by its internal point in every territory that contains it, where the paper counts the blocks that "
    "intersect each territory after overlaps are given to the smallest polygon (S1.1, p. 25; S1.5, p. 34), so the two "
    "instruments differ unit by unit and not by one scale; and the unit of spending inside the log, billions of real "
    "2024 dollars, is our approximation, the paper naming none (p. 8). Retained only as a labelled comparison (Joe, "
    "2026-11-19, D-107).")
C0_COMPARISON_LABEL = (
    "Comparison-only, by Joe's ruling of 2026-11-19 (D-109). Our uninstrumented estimate under our specification is shown "
    "with the paper's figure, 0.061 (0.018; Table 1 Panel A col 1, p. 13), and the band 0.025 to 0.097 beside it as a "
    "comparison band. No verdict is given, whether the estimate falls inside the band or outside it. Its assignment is "
    "the smallest containing polygon over every polygon of our copy of the layer, the same rule as row U's U0, and our "
    "facility list is not the paper's.")
C5_WORDING_STATUS = (
    "Adopted by Joe on 2026-11-19 (D-109). The detection sentence is his wording and the non-detection sentence is the "
    "drafted one he adopted beside it; neither is a draft. Anything else is reported as unresolved, as the plan has it.")


def check_paper_settled(choices: "Choices") -> None:
    """Stop, in words, if a caller passes a value the bounded read settled from the paper otherwise."""
    bad = []
    if choices.share_in_percent is not SHARE_IN_PERCENT:
        bad.append("share_in_percent must be True: the paper's share enters in percent of national fiber blocks "
                   "(section S2.1, p. 35; section S2.2, p. 36; Table S4, p. 34)")
    if choices.ownership_method != OWNERSHIP_METHOD:
        bad.append("ownership_method must be 'interaction': the paper's ownership split is one regression with the "
                   "count and the count times not-investor-owned, instrumented by Z and Z times not-investor-owned "
                   "(Table 3 col 1, p. 17; section S2.19, p. 78); separate samples are not the paper's specification")
    if choices.contiguous_only is not CONTIGUOUS_ONLY:
        bad.append("contiguous_only must be True: the paper's panel is the contiguous U.S. (section 2.1, p. 4; "
                   "section S1.1, p. 25)")
    if bad:
        raise ValueError("Row C: a choice the paper settles was passed with another value. " + " ".join(bad) +
                         " (docs/gate1/bounded-read-row-c-2026-11-19.md)")


def check_specification(choices: "Choices") -> None:
    """The paper's settled values first (check_paper_settled), then this study's approximations: stop, in words, if a
    caller departs from row C's specification."""
    check_paper_settled(choices)
    want = {"percentile_method": OURS_PERCENTILE_METHOD, "cap_population": OURS_CAP_POPULATION,
            "spending_log_unit": OURS_SPENDING_LOG_UNIT, "small_sample": OURS_SMALL_SAMPLE,
            "drop_singletons": OURS_DROP_SINGLETONS, "interval": OURS_INTERVAL,
            "never_host_basis": OURS_NEVER_HOST_BASIS}
    bad = [f"{k} is {getattr(choices, k)!r}, the specification {v!r}" for k, v in want.items() if getattr(choices, k) != v]
    msgs = []
    if bad:
        msgs.append("; ".join(bad) + ". These values are this study's approximations, ours and not the paper's, "
                    "adopted by Joe on 2026-11-19 (D-107).")
    if choices.price_deflator != OURS_PRICE_DEFLATOR:
        msgs.append(f"price_deflator is {choices.price_deflator!r}, the specification {OURS_PRICE_DEFLATOR!r}. The "
                    "caller does not choose row C's deflator: the price must be in real 2024 dollars by the CPI-U "
                    f"annual average ({DEFLATOR_SERIES_ID}, {DEFLATOR_COLUMN} in {DEFLATOR_TABLE}, through "
                    f"cpi_factors_to_2024). {PRICE_DEFLATOR_LABEL}")
    if choices.price_series != OURS_PRICE_SERIES:
        msgs.append(f"price_series is {choices.price_series!r}, the specification {OURS_PRICE_SERIES!r}. The caller "
                    f"does not choose row C's nominal price series: it is the panel's {OURS_PRICE_SERIES}, in "
                    f"{PRICE_SERIES_UNIT}, deflated to {PRICE_SERIES_REAL_UNIT}. {PRICE_SERIES_LABEL} "
                    f"{PRICE_SERIES_NOT_CHECKED}")
    if msgs:
        raise ValueError("Row C refuses to depart from its specification: " + " ".join(msgs))


# ---------------------------------------------------------------------------------------------------------------
# The paper's printed numbers and the plan's fixed bands and sentences
# ---------------------------------------------------------------------------------------------------------------
# Plan numbers, each checked against the paper in the bounded read (printed pages). Standard errors and F for C2 are
# from the paper's Table S14, Panel A (winsorize), not the plan; the plan prints only the three point estimates. The
# printed C0 coefficient is 0.0610. Ownership numbers are from the paper's Table 3, column 1 (an interaction model;
# "nonprofit" is anything but investor-owned); the plan prints none for the ownership split. "max_stock" is Table S14's
# "Max Data Center Stock" row and "units_adjusted" the paper's "we adjust the data center measures of only 8
# utilities" (S2.8, p. 50) for the 99.5th; both are for comparison only, not bands.
PAPER = {
    "C0": {"estimate": 0.061, "se": 0.018, "first_stage_f": None, "n_obs": 12370, "n_units": 1237,
           "source": "plan; paper Table 1 Panel A col 1, p. 13"},
    "C1": {"estimate": 0.182, "se": 0.034, "first_stage_f": 59.43, "n_obs": 12370, "n_units": 1237, "max_stock": 62,
           "units_adjusted": 8, "source": "plan; paper Table 1 Panel A col 3, p. 13; Table S14 A col 3, p. 51"},
    "C2_none": {"estimate": 0.110, "se": 0.044, "first_stage_f": 9.60, "max_stock": 280,
                "source": "plan (estimate); paper Table S14 A col 1, p. 51"},
    "C2_99.9": {"estimate": 0.150, "se": 0.034, "first_stage_f": 35.57, "max_stock": 127,
                "source": "plan (estimate); paper Table S14 A col 2, p. 51"},
    "C2_99.0": {"estimate": 0.236, "se": 0.044, "first_stage_f": 71.20, "max_stock": 38,
                "source": "plan (estimate); paper Table S14 A col 4, p. 51"},
    "C5_full_reduced_form": {"estimate": 0.155, "se": 0.028, "first_stage_f": None,
                             "source": "plan; paper Table S6 Panel A col 1, p. 39. Reported beside ours, not tested "
                                       "against (plan, D-16)"},
    "ownership_interaction": {"iou": 0.215, "iou_se": 0.042, "nonprofit_minus_iou": -0.192,
                              "nonprofit_minus_iou_se": 0.064, "sw_f_baseline": 55.44, "sw_f_interaction": 44.18,
                              "source": "paper Table 3 col 1, p. 17; not in the plan"},
    "first_stage_coef_count": {"estimate": 0.849, "se": 0.11, "first_stage_f": 59.43, "within_r2": 0.288,
                               "dep_var_mean": 1.17, "dep_var_sd": 5.00,
                               "source": "paper Table S5 col 1, p. 37 (share in percent)"},
    "thirteen_percent": {"effect_cents": 1.82, "post_2021_mean_price_cents": 14.01, "sd_stock": 10,
                         "basis": ("0.182 x a standard deviation of ten facilities, the un-winsorized SD of the "
                                   "post-2021 stock, over the post-2021 mean price"),
                         "source": "paper section 4.1, p. 12; section S2.4, p. 38"},
    "sample": {"territories": 3805, "territories_ten_years_of_price": 1243, "states_ten_years": 49,
               "regression_units": 1237, "regression_obs": 12370, "states_in_analysis": 48,
               "never_treated_units": 970,
               "source": "paper S1.1 p. 25; Table S2 p. 30; Table 1 p. 13; S2.11 p. 59 and Table S20; Table S11 p. 46"},
    "fiber_share_percent": {"mean": 0.0655, "sd": 0.190, "min": 0.00, "p10": 0.000527, "median": 0.0159,
                            "p90": 0.132, "max": 2.29, "units_positive": 1217,
                            "source": ("paper Table S4, p. 34, 'computed across all utility-State territories in the "
                                       "estimation sample', units percent; 1,217 positive: S2.10, p. 57")},
    "spending_table_s3_bn_real_2024": {2015: 3.63, 2016: 5.39, 2017: 5.97, 2018: 8.66, 2019: 10.4, 2020: 11.2,
                                       2021: 11.5, 2022: 13.5, 2023: 20.6, 2024: 31.1,
                                       "source": "paper Table S3, p. 34, billions of real 2024 dollars"},
}
# The plan's two bands, kept as comparison bands and shown beside the estimates (D-107); no other step has one.
BANDS = {"C0": (0.025, 0.097), "C1": (0.114, 0.250)}
F_FLOOR = 10.0                                       # the plan's instrumented band also asked for a first-stage F of 10
# The plan's caveat on every row's comparison (opening paragraph of the reconciliation rows), in its own words. Its
# sentence "A miss is reported as a miss" is not emitted for rows U and C, which return no verdict since D-107.
FACILITY_LIST_CAVEAT = ("our facility list is not theirs: all three papers use purchased lists, and ours is built from "
                        "permits and public sources.")
# C5's two readings, Joe's adopted wording (2026-11-19, D-109), character for character. The detection sentence is his
# own (note the curly apostrophe in "paper’s", as he wrote it); the non-detection sentence is the drafted one he adopted
# beside it, the qualifier now inside it.
C5_SENTENCE_INSTRUMENT_REACHES = (
    "If a relationship is detected, our instrument also predicts price changes among utilities classified as never "
    "hosting a data center. This does not distinguish spillovers from other correlated influences, and it does not "
    "establish whether the paper’s differently constructed instrument identifies an effect of hosting.")
C5_SENTENCE_NOT_DETECTED = (
    "The test did not detect a relationship between our instrument and price among utilities classified as never "
    "hosting a data center. That is a failure to detect, with a test that may have low power, and it does not show "
    "that our instrument or the paper's is valid.")
# What C5's operational never-host classification cannot establish (Joe, 2026-11-19, D-109). The classification itself
# is unchanged: never-host utility-states are those with no facility counted in any panel year under the inventory's
# own assignment (OURS_NEVER_HOST_BASIS, OURS_C5_HOSTS_FROM).
C5_NEVER_HOST_LIMITATION = (
    "C5's never-host utility-states are those with no facility counted in any panel year 2015-2024 under the inventory's "
    "own assignment; that operational classification is unchanged. It cannot establish that a unit has no data center: "
    "no assigned site is not proof of no facility, and a facility the inventory misses, or one it holds with no start "
    "year, leaves its unit among the never-host units. This says what the classification cannot establish and "
    "redefines nothing.")
C5_LEVEL = 0.90                                      # "The 90% interval is the row's own"


@dataclass(frozen=True)
class Choices:
    """Row C's choices. No defaults on purpose, so that a caller states each one. The accepted values are in
    SPECIFICATION; check_specification refuses any other in words. The elements the paper does not state are ours,
    adopted by Joe on 2026-11-19 (D-107); the alternatives below are kept as a record of what was weighed.

    Ours since D-107 (docs/gate1/bounded-read-row-c-2026-11-19.md; printed page numbers):
    percentile_method: how the yearly percentile is computed. "linear" is numpy's default (type 7); "stata_default"
        is Stata's _pctile/summarize default (with n*p/100 = i: the mean of the i-th and (i+1)-th order statistics
        when i is whole, else the ceil(i)-th), which winsor2 uses. The paper says "We winsorize the data center
        stock measure at the 99.5th percentile within-year" (footnote 3, p. 8) and names no formula. Its Table S14
        (p. 51) prints the capped maximum as whole numbers (127, 62, 38), which an order-statistic rule gives and
        linear interpolation on counts generally does not; display rounding cannot be ruled out (outcome 2, weak).
        Specification: "stata_default" (OURS_PERCENTILE_METHOD).
    cap_population: over which utility-states the year's percentile is taken. "estimation_sample" means the
        utility-states in the regression sample that year, zeros included; "supplied_universe" means the units in a
        frame the caller passes (for example all 3,805 HIFLD territories, which we do not hold). The paper says
        "that year's distribution" (S2.8, p. 50) without naming the population. Its "only 8 utilities" adjusted at
        the 99.5th (p. 50) and the 8, 2 and 14 utility-states removed at the 99.5th, 99.9th and 99th (Table S14
        Panel B: 1,229, 1,235 and 1,223 of 1,237) fit a year's distribution over about 1,237 units with zeros, not
        over 3,805 territories or over positive counts only (outcome 2, the agent's reading of those counts).
        Specification: "estimation_sample" (OURS_CAP_POPULATION); the "supplied_universe" path is no longer built.
    spending_log_unit: the unit of national spending inside the log, "billions" or "millions". The paper prints the
        series in billions of real 2024 dollars (Table S3, p. 34; Figure 2 notes, p. 11) and calls the term "the
        natural log of national data center construction spending" (p. 8) without a unit (outcome 2). It is not a
        rescaling: ln(c*S) = ln S + ln c adds ln c times post x share, which the fixed effects do not absorb.
        Specification: "billions" (OURS_SPENDING_LOG_UNIT).
    small_sample: "none", "cr1_cluster" or "cr1_stata" (module docstring). Exact reproduction unavailable (outcome 3).
        Specification: "cr1_stata" (OURS_SMALL_SAMPLE), labelled ours.
    drop_singletons: drop rows that are alone in a fixed-effect group, iterated (reghdfe's default). The paper does
        not say. Its 1,243 utility-states with ten years of price in 49 states (Table S2, p. 30) against 1,237 in
        the regressions (Table 1) in 48 states (S2.11, p. 59; Table S20 state clusters, p. 60) fit the loss of a
        state with one balanced unit, which is what singleton dropping does under state-by-year effects; the paper
        also mentions restrictions "based on the availability of additional data" (S1.3, p. 31), so this is not
        established (outcome 2). Point estimates do not depend on it; N, the cluster count and the small-sample
        factor do. Specification: True (OURS_DROP_SINGLETONS).
    interval: C5's 90% interval, "t_G_minus_1" or "normal". C5 is ours; the paper's one clustered joint test prints
        "Degrees of freedom (5, 1,236)", G - 1 in the denominator (Table S24, p. 68) (outcome 2). Specification:
        "t_G_minus_1" (OURS_INTERVAL).
    never_host_basis: what "host no facility in any year" means. "no_assigned_site": no data-center site (dated or
        undated, any energized year) is assigned to the unit under the assignment in use; "zero_count_panel_years":
        the operating count is zero in every year 2015-2024. C5 is ours; the paper's nearest group, its "never
        treated" territories, "have no data center presence throughout the sample period" (Table S11 notes, p. 46;
        970 of 1,237), and its stock counts only dated sites (outcome 2). Specification: "zero_count_panel_years"
        (OURS_NEVER_HOST_BASIS).
    price_deflator: the series that put the outcome frame's price in real 2024 dollars. The paper says only "the
        CPI" (section 2.1, p. 4). Specification: "cpi_u_annual_average" (OURS_PRICE_DEFLATOR), the CPI-U annual
        average through cpi_factors_to_2024; ours, adopted by Joe on 2026-11-19 (D-111), and not the caller's
        choice. check_specification refuses any other value in words (PRICE_DEFLATOR_LABEL).
    price_series: the panel column the outcome frame's nominal price comes from. Specification: "res_price"
        (OURS_PRICE_SERIES), this study's delivery-inclusive price in cents per kWh, our comparison specification
        settled by Joe on 2026-11-20 (D-117) and not a claim that the paper used exactly this construction
        (PRICE_SERIES_LABEL). Not the caller's choice; check_specification refuses any other value in words. The module
        cannot detect a frame built from another column (PRICE_SERIES_NOT_CHECKED).

    Settled by the read and checked against the constants by `check_paper_settled` (still accepted as fields):
    share_in_percent: must be True (SHARE_IN_PERCENT).
    ownership_method: must be "interaction" (OWNERSHIP_METHOD); "split_samples" is accepted here and refused where
        used, in words.
    contiguous_only: must be True (CONTIGUOUS_ONLY).
    """
    percentile_method: str
    cap_population: str
    spending_log_unit: str
    small_sample: str
    drop_singletons: bool
    share_in_percent: bool
    ownership_method: str
    interval: str
    never_host_basis: str
    contiguous_only: bool
    price_deflator: str
    price_series: str

    def __post_init__(self):
        allowed = {"percentile_method": ("linear", "stata_default"),
                   "cap_population": ("estimation_sample", "supplied_universe"),
                   "spending_log_unit": ("billions", "millions"),
                   "small_sample": ("none", "cr1_cluster", "cr1_stata"),
                   "ownership_method": ("split_samples", "interaction"),
                   "interval": ("t_G_minus_1", "normal"),
                   "never_host_basis": ("no_assigned_site", "zero_count_panel_years")}
        for k, ok in allowed.items():
            if getattr(self, k) not in ok:
                raise ValueError(f"Choices.{k} must be one of {ok}, not {getattr(self, k)!r}")


# Row C's specification: the paper's settled values, this study's approximations (ours, D-107), the price deflator
# (ours, D-111) and the nominal price series (our comparison specification, D-117).
SPECIFICATION = Choices(percentile_method=OURS_PERCENTILE_METHOD, cap_population=OURS_CAP_POPULATION,
                        spending_log_unit=OURS_SPENDING_LOG_UNIT, small_sample=OURS_SMALL_SAMPLE,
                        drop_singletons=OURS_DROP_SINGLETONS, share_in_percent=SHARE_IN_PERCENT,
                        ownership_method=OWNERSHIP_METHOD, interval=OURS_INTERVAL,
                        never_host_basis=OURS_NEVER_HOST_BASIS, contiguous_only=CONTIGUOUS_ONLY,
                        price_deflator=OURS_PRICE_DEFLATOR, price_series=OURS_PRICE_SERIES)

# Row C's ownership classes, settled by Joe on 2026-11-20 (D-117 and D-119): the panel's entity type of each
# utility-state, the utility-level modal reported type carried across the panel and not the latest year-by-year EIA
# classification (D-119), read as the last nonmissing value over 2001 to 2025
# (reconciliation_mu.last_nonmissing_entity_type, the same reading as row U's), one class for
# every year of the unit (the paper's ownership is "time-invariant", section 4.3, p. 16), mapped by row C's existing
# mapping, the panel's grouping (pipeline/electricity/panel.py OWNERSHIP_GROUP, held here as a copy and checked equal in
# the tests). The ownership split puts investor_owned on one side and every other class on the other
# (OWNERSHIP_OTHER_RULE, unchanged).
ROW_C_OWNERSHIP_MAP = {"Investor Owned": "investor_owned", "Cooperative": "cooperative", "Municipal": "public",
                       "Political Subdivision": "public", "State": "public", "Federal": "public"}


def adopted_row_c_ownership(quantities: pd.DataFrame) -> dict:
    """{(utility_id_eia, state): class} for row C's ownership split, as Joe settled it on 2026-11-20 (D-117 and D-119).

    The panel's entity type, the utility-level modal reported type carried across the panel and not the latest
    year-by-year EIA classification (D-119), read as the last nonmissing value over 2001 to 2025
    (reconciliation_mu.last_nonmissing_entity_type, which refuses quantities whose years are not exactly 2001 to 2025;
    D-117), mapped by ROW_C_OWNERSHIP_MAP. One class per
    utility-state, the same in every year. A unit with no entity type in any year is ABSENT from the mapping, so
    ownership_split stops in words on it; it is never put on the "all other" side and never read as any class. An entity
    type outside the six the mapping knows stops in words: a guard on an input the panel cannot produce (its units are
    kept only when their type is one of those six), not a new research rule. Takes no pick; the classification is the
    settled one. Pure; opens no file."""
    et = rmu.last_nonmissing_entity_type(quantities)
    typed = et[et.entity_type.notna()]
    unknown = sorted({str(e) for e in typed.entity_type if e not in ROW_C_OWNERSHIP_MAP})
    if unknown:
        raise ValueError(f"entity types {unknown} are not among the six row C's mapping knows "
                         f"({sorted(ROW_C_OWNERSHIP_MAP)}); no class is guessed for them")
    return {(int(u), s): ROW_C_OWNERSHIP_MAP[e] for u, s, e in zip(typed.utility_id_eia, typed.state, typed.entity_type)}


class NumericalFailure(RuntimeError):
    """A fit that cannot be computed. Reported in words with the step, never dropped."""


# ---------------------------------------------------------------------------------------------------------------
# Inputs on the quantity side: counts, cap, balanced panel, instrument
# ---------------------------------------------------------------------------------------------------------------
def operating_counts(sites: pd.DataFrame, assignment: pd.DataFrame, years: Iterable[int] = YEARS) -> tuple[pd.DataFrame, dict]:
    """Count of operating data centers by utility-state and year under one assignment table.

    sites: one row per inventory site with fid, energized_year, is_crypto. assignment: one row per (site, unit) with
    fid, utility_id_eia, state. A site operates in year t when its energized year is t or earlier and counts every
    year from then on, as the paper's stock does: "the cumulative stock ... among all facilities that had begun
    operation by that year" (S1.2, p. 28); neither has retirement dates. Crypto mines are not data centers and are
    not counted (ours; the paper's list is data centers only). A site with no energized year cannot be placed in any
    year and is not counted, as in the paper (2,749 of its 3,021 operational sites, 91%, have a year; S1.2, p. 28);
    one with no utility in the assignment is not counted. Both are reported. A site with several assignment rows
    counts at each. Returns only unit-years with a positive count; the panel builder fills zeros.

    The paper's assignment for C0 to C2 is a point-in-polygon merge to HIFLD territories after "we attribute the
    intersected region to the smallest polygon" wherever polygons overlap (S1.1, p. 25; S1.2, p. 28), over all
    3,805 territories, so a site inside a small territory outside the balanced sample counts for no sample unit.
    Building that table is the polygon assignment's job, not this function's.
    """
    s = sites[["fid", "energized_year", "is_crypto"]].copy()
    if s.fid.duplicated().any():
        raise ValueError(f"{int(s.fid.duplicated().sum())} duplicate fid rows in sites")
    a = assignment[["fid", "utility_id_eia", "state"]].dropna(subset=["utility_id_eia"]).copy()
    a["utility_id_eia"] = a.utility_id_eia.astype(int)
    a = a.drop_duplicates()
    dc = s[~s.is_crypto.astype(bool)]
    m = a.merge(dc, on="fid", how="inner")
    report = {
        "sites": int(len(s)), "crypto_sites_not_counted": int(s.is_crypto.astype(bool).sum()),
        "data_center_sites": int(len(dc)),
        "data_center_sites_without_energized_year": int(dc.energized_year.isna().sum()),
        "data_center_sites_without_an_assigned_utility": int((~dc.fid.isin(a.fid)).sum()),
        "data_center_sites_with_more_than_one_assigned_unit": int((m.groupby("fid").size() > 1).sum()),
    }
    m = m[m.energized_year.notna()]
    rows = []
    for y in years:
        on = m[m.energized_year <= y]
        if len(on):
            g = on.groupby(KEYS).fid.nunique().rename("value").reset_index()
            g["year"] = int(y)
            rows.append(g)
    out = (pd.concat(rows, ignore_index=True) if rows else
           pd.DataFrame({"utility_id_eia": pd.Series(dtype=int), "state": pd.Series(dtype=object),
                         "value": pd.Series(dtype=float), "year": pd.Series(dtype=int)}))
    out["value"] = out.value.astype(float)
    report["counted_site_years"] = int(out.value.sum()) if len(out) else 0
    return out[KEYS + ["year", "value"]], report


def load_share(dose: pd.DataFrame, column: str = "dose") -> pd.DataFrame:
    """C4's regressor: our load share (`dose` in data/interim/utility_year_dose.parquet) as a frame with `value`."""
    d = dose[KEYS + ["year", column]].rename(columns={column: "value"}).copy()
    d["utility_id_eia"] = d.utility_id_eia.astype(int)
    return d


def percentile(values: np.ndarray, p: float, method: str) -> float:
    """The p-th percentile (0-100) of values. "linear" is numpy's default; "stata_default" is Stata's _pctile rule."""
    v = np.sort(np.asarray(values, dtype=float))
    n = len(v)
    if n == 0:
        raise ValueError("no values for a percentile")
    if method == "linear":
        return float(np.percentile(v, p))
    if method == "stata_default":
        i = n * p / 100.0
        k = math.floor(i)
        if abs(i - round(i)) < 1e-9:                     # whole: mean of the i-th and (i+1)-th (1-based)
            k = int(round(i))
            if k <= 0:
                return float(v[0])
            if k >= n:
                return float(v[-1])
            return float((v[k - 1] + v[k]) / 2.0)
        return float(v[min(k, n - 1)])                    # the ceil(i)-th, 1-based
    raise ValueError(f"unknown percentile method {method!r}")


def yearly_caps(frame: pd.DataFrame, p: float | None, method: str) -> dict[int, float]:
    """{year: cap} with the cap the p-th percentile of `value` over the rows given for that year (zeros included)."""
    if p is None:
        return {}
    return {int(y): percentile(g.value.to_numpy(), p, method) for y, g in frame.groupby("year")}


def apply_cap(frame: pd.DataFrame, caps: Mapping[int, float]) -> pd.DataFrame:
    """Values above their year's cap set to the cap (top only: the paper winsorizes a count whose floor is zero)."""
    out = frame.copy()
    if caps:
        c = out.year.map(caps).astype(float)
        out["value"] = np.minimum(out.value.to_numpy(float), c.to_numpy())
    return out


def balanced_units(observed: pd.DataFrame, years: Sequence[int] = YEARS) -> set:
    """Utility-states with a row in every year of `years` (the caller passes only rows whose outcome is non-missing).

    The paper's rule, section S1.3 (p. 30): "non-missing residential electricity price data in the EIA 861 for all ten
    years", 2015-2024 (also S1.1, p. 25). The paper gets 1,243 such territories and runs its regressions on 1,237
    (Table 1); the six are not explained. Duplicate keys stop.
    """
    o = observed[KEYS + ["year"]]
    if o.duplicated().any():
        raise ValueError(f"{int(o.duplicated().sum())} duplicate utility-state-year keys")
    o = o[o.year.isin(years)]
    n = o.groupby(KEYS).year.nunique()
    return {(int(u), s) for (u, s), k in n.items() if k == len(set(years))}


def spending_series(table: pd.DataFrame, which: str) -> dict[int, float]:
    """{year: national private data center construction spending, billions of 2024 dollars}.

    table is data/frozen/dc_construction_spending.csv. which = "paper": their printed Table S3 (column
    paper_table_s3_real_2024_bn, 2015-2024). which = "current": the Census series on file (real_2024_musd / 1000),
    where 2024 is $34.8 billion against their $31.1 billion. The plan: the instrumented steps use the paper's printed
    series and are repeated on the current one.
    """
    if which == "paper":
        s = table.set_index("year").paper_table_s3_real_2024_bn.dropna()
    elif which == "current":
        s = table.set_index("year").real_2024_musd.dropna() / 1000.0
    else:
        raise ValueError("which is 'paper' or 'current'")
    return {int(y): float(v) for y, v in s.items()}


def instrument(units_years: pd.DataFrame, share: Mapping[tuple, float], spending_bn: Mapping[int, float],
               choices: Choices) -> np.ndarray:
    """Z = 1[year >= 2021] x ln(spending_year) x share_unit, row by row of units_years (utility_id_eia, state, year).

    spending_bn is in billions of 2024 dollars; choices.spending_log_unit sets the unit inside the log (open). The share
    is multiplied by 100, the paper's percent (SHARE_IN_PERCENT; checked). A post year with no spending value stops.
    """
    check_specification(choices)
    mult = 1000.0 if choices.spending_log_unit == "millions" else 1.0
    yrs = units_years.year.to_numpy(int)
    post = yrs >= POST_FROM
    missing = sorted({int(y) for y in yrs[post] if y not in spending_bn})
    if missing:
        raise ValueError(f"no spending value for post years {missing}")
    lns = np.array([math.log(spending_bn[y] * mult) if p else 0.0 for y, p in zip(yrs, post)])
    sh = np.array([share[(int(u), s)] for u, s in zip(units_years.utility_id_eia, units_years.state)], dtype=float)
    if choices.share_in_percent:
        sh = sh * 100.0
    return post.astype(float) * lns * sh


def share_map(fiber: pd.DataFrame, column: str = SHARE_COLUMN) -> dict[tuple, float]:
    """{(utility_id_eia, state): share} from data/frozen/fiber_share_by_unit.csv (fraction of national fiber blocks)."""
    f = fiber.dropna(subset=[column])
    if f[KEYS].duplicated().any():
        raise ValueError("duplicate units in the fiber share table")
    return {(int(u), s): float(v) for u, s, v in zip(f.utility_id_eia, f.state, f[column])}


def cpi_factors_to_2024(table: pd.DataFrame) -> dict[int, float]:
    """{year: cpi_u[2024] / cpi_u[year]} from data/frozen/dc_construction_spending.csv. A factor table, no prices.

    Row C's deflator (OURS_PRICE_DEFLATOR; PRICE_DEFLATOR_LABEL): ours, not the paper's, this study's convention,
    adopted by Joe on 2026-11-19 (D-111). A price in year t times the factor for t is in real 2024 dollars. A table
    with no positive, finite cpi_u for a year of row C's window (YEARS, 2015-2024) is refused in words."""
    c = table.set_index("year")[DEFLATOR_COLUMN]
    have = {int(y) for y, v in c.items() if np.isfinite(v) and v > 0}
    missing = sorted(set(YEARS) - have)
    if missing:
        raise ValueError(f"row C's deflator ({DEFLATOR_COLUMN}, {DEFLATOR_SERIES_ID}) has no positive value for "
                         f"{missing}; row C's window is {YEARS[0]}-{YEARS[-1]}. Nothing is fetched to fill it.")
    return {int(y): float(c.loc[DEFLATOR_BASE_YEAR] / v) for y, v in c.items()}


# ---------------------------------------------------------------------------------------------------------------
# The estimator: two-way within transformation, OLS and 2SLS, cluster-robust variance, first-stage F, reduced form
# ---------------------------------------------------------------------------------------------------------------
def _codes(values) -> np.ndarray:
    return pd.factorize(pd.Series(list(values)))[0]


def drop_singletons(g1: np.ndarray, g2: np.ndarray) -> np.ndarray:
    """Boolean keep-mask after iteratively dropping rows alone in their group of either fixed effect."""
    keep = np.ones(len(g1), dtype=bool)
    while True:
        c1 = np.bincount(g1[keep], minlength=g1.max() + 1 if len(g1) else 0)
        c2 = np.bincount(g2[keep], minlength=g2.max() + 1 if len(g2) else 0)
        bad = keep & ((c1[g1] == 1) | (c2[g2] == 1))
        if not bad.any():
            return keep
        keep &= ~bad


def within(M: np.ndarray, g1: np.ndarray, g2: np.ndarray, tol: float = 1e-13, max_iter: int = 10_000) -> np.ndarray:
    """Remove two sets of fixed effects from every column of M by alternating projections (exact at convergence).

    Converges when the largest change in a sweep is below tol times the columns' scale; a design that does not
    converge raises NumericalFailure rather than returning an approximate answer.
    """
    M = np.array(M, dtype=float, copy=True)
    if M.ndim == 1:
        M = M[:, None]
    n1, n2 = g1.max() + 1, g2.max() + 1
    c1 = np.bincount(g1, minlength=n1).astype(float)
    c2 = np.bincount(g2, minlength=n2).astype(float)
    scale = max(1.0, float(np.abs(M).max()))
    for it in range(max_iter):
        before = M.copy()
        for j in range(M.shape[1]):
            M[:, j] -= (np.bincount(g1, weights=M[:, j], minlength=n1) / c1)[g1]
            M[:, j] -= (np.bincount(g2, weights=M[:, j], minlength=n2) / c2)[g2]
        if np.abs(M - before).max() <= tol * scale:
            return M
    raise NumericalFailure(f"the fixed effects were not removed to tolerance in {max_iter} sweeps")


def absorbed_df_not_nested(g1: np.ndarray, g2: np.ndarray) -> int:
    """Degrees of freedom of the second effect not redundant given the first: its levels less connected components.

    The first effect (utility-state) is nested in the clusters and counts zero under "cr1_stata"; this is what the
    second (state-by-year) adds to K.
    """
    n1, n2 = g1.max() + 1, g2.max() + 1
    parent = list(range(n1 + n2))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in set(zip(g1.tolist(), (g2 + n1).tolist())):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    comps = len({find(x) for x in range(n1 + n2)})
    return int(n2 - comps)


@dataclass
class Fit:
    coef: np.ndarray
    vcov: np.ndarray
    n_obs: int
    n_clusters: int
    k: int
    dof_scale: float
    first_stage_f: float | None = None
    first_stage_coef: np.ndarray | None = None
    first_stage_se: np.ndarray | None = None
    first_stage_se_failure: str | None = None       # words when a first-stage standard error is not a number (D-122)

    @property
    def se(self) -> np.ndarray:
        return np.sqrt(np.diag(self.vcov))


def _scale(small_sample: str, G: int, N: int, K: int) -> float:
    if small_sample == "none":
        return 1.0
    if G < 2:
        raise NumericalFailure("fewer than two clusters; no cluster-robust variance")
    if small_sample == "cr1_cluster":
        return G / (G - 1)
    if small_sample == "cr1_stata":
        if N - K <= 0:
            raise NumericalFailure(f"no residual degrees of freedom (N = {N}, K = {K})")
        return G / (G - 1) * (N - 1) / (N - K)
    raise ValueError(small_sample)


def _mat(a) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    return a[:, None] if a.ndim == 1 else a


def _check_rank(A: np.ndarray, what: str) -> None:
    if A.shape[1] == 0:
        return
    if np.linalg.matrix_rank(A, tol=1e-10 * max(1.0, float(np.abs(A).max())) * max(A.shape)) < A.shape[1]:
        raise NumericalFailure(f"{what} has no variation left after the fixed effects (rank deficient)")


def iv_fit(y: np.ndarray, X: np.ndarray, Z: np.ndarray | None, cluster: np.ndarray, small_sample: str,
           k_absorbed: int, W: np.ndarray | None = None) -> Fit:
    """OLS (Z None) or 2SLS of y on X (endogenous) and W (exogenous), all already within-transformed.

    beta = (Xh'X)^-1 Xh'y with Xh the projection of [X W] on [Z W]. V = c (Xh'Xh)^-1 (sum_g Xh_g'u_g u_g'Xh_g)
    (Xh'Xh)^-1 with u = y - [X W] beta (structural residuals) and c the small-sample scale. When instrumented, the
    first-stage F is the cluster-robust Wald statistic on the excluded instruments divided by their number (one
    endogenous) or Sanderson and Windmeijer's conditional F (several; `sw_conditional_f`).
    """
    y = np.asarray(y, float).ravel()
    X = _mat(X)
    W = np.zeros((len(y), 0)) if W is None else _mat(W)
    Xa = np.hstack([X, W])
    if Z is None:
        Za = Xa
    else:
        Z = _mat(Z)
        if Z.shape[1] < X.shape[1]:
            raise ValueError("fewer instruments than endogenous regressors")
        Za = np.hstack([Z, W])
    _check_rank(Za, "the instrument set" if Z is not None else "the regressor set")
    Xh = Za @ np.linalg.lstsq(Za, Xa, rcond=None)[0] if Z is not None else Xa
    _check_rank(Xh, "the fitted regressors")
    A = Xh.T @ Xa
    beta = np.linalg.solve(A, Xh.T @ y)
    u = y - Xa @ beta
    cl = _codes(cluster)
    G = int(cl.max() + 1)
    S = np.zeros((G, Xa.shape[1]))
    np.add.at(S, cl, Xh * u[:, None])
    bread = np.linalg.inv(Xh.T @ Xh)
    K = Xa.shape[1] + k_absorbed
    c = _scale(small_sample, G, len(y), K)
    V = c * bread @ (S.T @ S) @ bread
    if not np.all(np.isfinite(beta)) or not np.all(np.isfinite(V)):
        raise NumericalFailure("the fit returned a non-finite coefficient or variance")
    fit = Fit(coef=beta, vcov=V, n_obs=len(y), n_clusters=G, k=K, dof_scale=c)
    if Z is not None:
        if X.shape[1] == 1:
            fs = iv_fit(X[:, 0], np.zeros((len(y), 0)), None, cluster, small_sample, k_absorbed, W=Za)
            L = Z.shape[1]
            b, Vb = fs.coef[:L], fs.vcov[:L, :L]
            fit.first_stage_f = _wald(b, Vb) / L
            fit.first_stage_coef, fit.first_stage_se = b, np.sqrt(np.diag(Vb))
            fit.first_stage_se_failure = first_stage_se_in_words(np.diag(Vb))
        else:
            fit.first_stage_f = None
    return fit


def first_stage_se_in_words(variance_diagonal) -> str | None:
    """Words for the step's record when a first-stage standard error is not a number, and None otherwise.

    A reporting-only repair (Joe, 2026-11-20, D-122: "Report it in words"; and his technical note of that day: "zero
    variance produces a zero standard error; negative variance produces NaN."). The standard error is the square root of
    the diagonal of the first stage's cluster-robust variance, left exactly as computed. Where an entry of that diagonal
    is negative or not finite its square root is not a number, and this says so in words with counts and no value. A
    zero variance gives a standard error of zero, which is a number: it is left as computed and is not reported (the
    session's reading of his note). No estimate, sample, instrument or inference rule is changed by this function, which
    computes nothing that is used anywhere else."""
    d = np.asarray(variance_diagonal, dtype=float).ravel()
    negative = np.isfinite(d) & (d < 0)
    not_finite = ~np.isfinite(d)
    if not (negative.any() or not_finite.any()):
        return None
    return (f"the first-stage standard error is not a number for {int((negative | not_finite).sum())} of the {d.size} "
            f"excluded-instrument coefficients: the first stage's cluster-robust variance is negative for "
            f"{int(negative.sum())} and not finite for {int(not_finite.sum())}, so its square root is not a number. The "
            "value is left as computed and nothing is replaced; the first-stage F is computed from the same variance "
            "and is also left as computed; the step's estimate, standard error, sample and instrument are unchanged")


def sw_conditional_f(X: np.ndarray, Z: np.ndarray, cluster: np.ndarray, small_sample: str, k_absorbed: int,
                     W: np.ndarray | None = None, notes: list | None = None) -> list[float]:
    """Sanderson and Windmeijer's (2016) conditional first-stage F for each endogenous regressor, cluster-robust.

    For endogenous j: 2SLS of X_j on the other endogenous regressors (and W) with all instruments; regress its
    residual on [Z W]; the cluster-robust Wald statistic on Z divided by (L - p + 1). This is the paper's statistic for
    its interaction models (Table 3 notes). That it matches the paper's software to the digit is not established; I
    am uncertain about the robust variant's exact form in their software.

    notes (reporting only, D-122): a list the caller passes to be told, in words, when the helper fit of one endogenous
    regressor on the others had a first-stage standard error that is not a number (iv_fit computes one as a by-product
    of that fit). Nothing returned here uses that standard error, and passing `notes` changes no number.
    """
    X = _mat(X)
    n, p = X.shape
    Z = _mat(Z)
    L = Z.shape[1]
    W0 = np.zeros((n, 0)) if W is None else _mat(W)
    out = []
    for j in range(p):
        others = np.delete(X, j, axis=1)
        if others.shape[1]:
            f = iv_fit(X[:, j], others, Z, cluster, small_sample, k_absorbed, W=W0)
            if notes is not None and f.first_stage_se_failure:
                notes.append(f"in the helper fit for endogenous regressor {j + 1} of {p}, {f.first_stage_se_failure}")
            e = X[:, j] - np.hstack([others, W0]) @ f.coef
        else:
            e = X[:, j]
        r = iv_fit(e, np.zeros((n, 0)), None, cluster, small_sample, k_absorbed, W=np.hstack([Z, W0]))
        b, Vb = r.coef[:L], r.vcov[:L, :L]
        out.append(_wald(b, Vb) / (L - p + 1))
    return out


def _wald(b: np.ndarray, Vb: np.ndarray) -> float:
    """b' Vb^-1 b. A singular clustered variance (the clusters' scores lie on a line) is a numerical failure in words,
    not an exception (added 2026-11-19, session 21: an invented world in which ownership is constant within each state
    gave a singular variance for the conditional F)."""
    try:
        return float(b @ np.linalg.solve(Vb, b))
    except np.linalg.LinAlgError as e:
        raise NumericalFailure(f"the clustered variance of the excluded instruments is singular ({e}); no first-stage F")


# ---------------------------------------------------------------------------------------------------------------
# The panel for one step
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Panel:
    frame: pd.DataFrame                    # utility_id_eia, state, year, y, d (capped regressor), z
    caps: dict
    accounting: dict


def build_panel(outcome: pd.DataFrame, regressor: pd.DataFrame, share: Mapping[tuple, float],
                spending_bn: Mapping[int, float] | None, choices: Choices, cap: float | None,
                value_column: str = "value", restrict_units: set | None = None) -> Panel:
    """Assemble the balanced 2015-2024 panel for one step.

    outcome: utility_id_eia, state, year and `value_column`: the panel's res_price (choices.price_series, which must be
    OURS_PRICE_SERIES, D-117), which is already in cents per kWh (panel.py divides revenue over MWh by 10), each
    year's value multiplied by the caller by cpi_factors_to_2024's factor so that it is in real 2024 cents per kWh
    (choices.price_deflator, which must be OURS_PRICE_DEFLATOR, D-111). No change of unit is needed; the deflation is
    done by the caller before the frame is supplied. Nothing here converts or reads a price, and nothing here can detect a frame built from another
    column (PRICE_SERIES_NOT_CHECKED). Rows with a missing value are not observed.
    Sample: units observed in every year 2015-2024 (the paper's balanced rule), in the contiguous states (the paper's;
    checked), and with a fiber share (the instrument cannot be formed without one). The paper's OLS and shift-share
    columns have the same 12,370 observations and 1,237 units (Table 1, p. 13), so the same sample serves both. A
    unit whose share is zero stays, as in the paper (Table S4 minimum 0.00; 1,217 of 1,237 positive, S2.10, p. 57).
    restrict_units narrows the sample further (C5's never-host units).
    regressor: unit-years with a positive count or share (`value`); missing unit-years are zero.
    Cap: each year's `cap` percentile over the estimation sample's units that year, zeros included, by the
    order-statistic formula (both ours, D-107). spending_bn None leaves z empty (the uninstrumented step).
    The accounting reports the largest regressor value before and after the cap, beside the paper's Table S14 row
    "Max Data Center Stock" (280, 127, 62 and 38 for no cap and the 99.9th, 99.5th and 99th).
    """
    check_specification(choices)
    o = outcome[KEYS + ["year", value_column]].rename(columns={value_column: "y"}).copy()
    o["utility_id_eia"] = o.utility_id_eia.astype(int)
    o = o[o.year.isin(YEARS) & o.y.notna()]
    acc = {"outcome_units_any_year": int(o[KEYS].drop_duplicates().shape[0])}
    units = balanced_units(o)
    acc["balanced_units"] = len(units)
    units = {u for u in units if u[1] not in NON_CONTIGUOUS}
    acc["balanced_units_contiguous"] = len(units)
    no_share = {u for u in units if u not in share or not np.isfinite(share[u])}
    units -= no_share
    acc["balanced_units_dropped_no_fiber_share"] = len(no_share)
    if restrict_units is not None:
        units &= {(int(u), s) for u, s in restrict_units}
        acc["units_after_restriction"] = len(units)
    keep = pd.Series([(u, s) in units for u, s in zip(o.utility_id_eia, o.state)], index=o.index)
    f = o[keep].copy()
    r = regressor[KEYS + ["year", "value"]].copy()
    r["utility_id_eia"] = r.utility_id_eia.astype(int)
    if r[KEYS + ["year"]].duplicated().any():
        raise ValueError("duplicate unit-years in the regressor")
    f = f.merge(r, on=KEYS + ["year"], how="left").fillna({"value": 0.0})
    caps = {} if cap is None else yearly_caps(f, cap, choices.percentile_method)
    raw = f.value.to_numpy(float)
    f = apply_cap(f, caps)
    acc["unit_years_changed_by_cap"] = int((f.value.to_numpy(float) < raw).sum())
    acc["units_changed_by_cap"] = int(f.loc[f.value.to_numpy(float) < raw, KEYS].drop_duplicates().shape[0])
    acc["max_regressor_before_cap"] = float(raw.max()) if len(raw) else float("nan")
    acc["max_regressor_after_cap"] = float(f.value.max()) if len(f) else float("nan")
    f = f.rename(columns={"value": "d"})
    f["z"] = instrument(f, share, spending_bn, choices) if spending_bn is not None else np.nan
    acc["rows"] = int(len(f))
    acc["units"] = int(f[KEYS].drop_duplicates().shape[0])
    return Panel(frame=f.sort_values(KEYS + ["year"]).reset_index(drop=True), caps=caps, accounting=acc)


def _design(p: Panel, choices: Choices):
    f = p.frame
    g1 = _codes(zip(f.utility_id_eia, f.state))
    g2 = _codes(zip(f.state, f.year))
    keep = drop_singletons(g1, g2) if choices.drop_singletons else np.ones(len(f), bool)
    dropped = int((~keep).sum())
    f = f[keep].reset_index(drop=True)
    g1 = _codes(zip(f.utility_id_eia, f.state))
    g2 = _codes(zip(f.state, f.year))
    return f, g1, g2, dropped


# ---------------------------------------------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class StepResult:
    step: str
    label: str
    estimator: str                          # "ols", "2sls", "reduced_form"
    spending_series: str | None
    estimate: float = float("nan")
    se: float = float("nan")
    first_stage_f: float | None = None
    first_stage_coef: float | None = None
    n_obs: int = 0
    n_units: int = 0
    singleton_rows_dropped: int = 0
    paper: dict | None = None
    band: tuple | None = None               # the plan's band, shown beside the estimate for comparison only
    comparison: dict = field(default_factory=dict)   # the label and why no verdict attaches (D-107)
    failure: str | None = None
    caps: dict = field(default_factory=dict)
    accounting: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def _compare(r: StepResult, band_key: str | None) -> StepResult:
    """The comparison each step returns in place of a verdict (Joe, 2026-11-19, D-107). An instrumented step carries
    C_INSTRUMENTED_COMPARISON_LABEL; C0 carries C0_COMPARISON_LABEL. The plan's band, where the step has one, is
    shown beside the estimate. Nothing here says reproduced or not."""
    if band_key in BANDS:
        r.band = BANDS[band_key]
    r.comparison = {"label": C_INSTRUMENTED_COMPARISON_LABEL if r.estimator == "2sls" else C0_COMPARISON_LABEL,
                    "verdict": None, "caveat": FACILITY_LIST_CAVEAT, "missing_coverage": rt.MISSING_COVERAGE_QUALIFICATION,
                    "paper_printed": r.paper, "band_beside": r.band,
                    "first_stage_f_ours": r.first_stage_f, "first_stage_f_floor_in_the_plans_band": (
                        F_FLOOR if r.estimator == "2sls" and r.band is not None else None)}
    return r


def run_step(step: str, label: str, outcome: pd.DataFrame, regressor: pd.DataFrame, share: Mapping[tuple, float],
             spending_bn: Mapping[int, float] | None, series_name: str | None, choices: Choices, cap: float | None,
             instrumented: bool, paper_key: str | None, band_key: str | None, value_column: str = "value",
             restrict_units: set | None = None) -> StepResult:
    """One step: build the panel, remove the fixed effects, fit, and return the labelled comparison (no verdict)."""
    r = StepResult(step=step, label=label, estimator="2sls" if instrumented else "ols",
                   spending_series=series_name if instrumented else None,
                   paper=PAPER.get(paper_key) if paper_key else None)
    try:
        p = build_panel(outcome, regressor, share, spending_bn if instrumented else None, choices, cap,
                        value_column, restrict_units)
        r.caps, r.accounting = p.caps, p.accounting
        f, g1, g2, dropped = _design(p, choices)
        r.singleton_rows_dropped = dropped
        cols = ["y", "d", "z"] if instrumented else ["y", "d"]
        M = within(f[cols].to_numpy(float), g1, g2)
        kabs = absorbed_df_not_nested(g1, g2)
        fit = iv_fit(M[:, 0], M[:, 1:2], M[:, 2:3] if instrumented else None, g1, choices.small_sample, kabs)
        r.estimate, r.se = float(fit.coef[0]), float(fit.se[0])
        r.n_obs, r.n_units = fit.n_obs, fit.n_clusters
        if instrumented:
            r.first_stage_f = fit.first_stage_f
            r.first_stage_coef = float(fit.first_stage_coef[0])
            if fit.first_stage_se_failure:
                # Reporting only (D-122): the step is estimated and `failure` stays None; the words are added to the
                # step's record under a key the coordinator's report lists with the failures in words.
                r.extra["first_stage_se_failure"] = f"{step}: {fit.first_stage_se_failure}"
    except NumericalFailure as e:
        r.failure = f"{step} could not be estimated: {e}"
    return _compare(r, band_key)


def ownership_split(step: str, outcome: pd.DataFrame, regressor: pd.DataFrame, share: Mapping[tuple, float],
                    spending_bn: Mapping[int, float], series_name: str, choices: Choices, cap: float | None,
                    ownership: Mapping[tuple, str], value_column: str = "value") -> dict:
    """Investor-owned against all other, instrumented, at C1 or C3 (plan), in the paper's form.

    The paper's form (Table 3 col 1, p. 17; section S2.19, p. 78): one regression with the count and the count times
    "nonprofit", instrumented by Z and Z times "nonprofit", utility-state and state-by-year effects, clustered by
    utility-state, F statistics Sanderson and Windmeijer's conditional F. "Nonprofit utilities are defined as anything
    except an investor-owned utility" (Table 3 notes); ownership is "time-invariant" (section 4.3, p. 16).
    choices.ownership_method must be "interaction" (checked); separate samples are refused in words.
    ownership: {(utility_id_eia, state): class}, row C's classes from adopted_row_c_ownership (D-117 and D-119: the
    panel's entity type, the utility-level modal reported type carried across the panel and not the latest
    year-by-year EIA classification, read over 2001 to 2025, time-invariant); "investor_owned" is one side, every other
    class the other. A unit missing from `ownership` (for example one with no entity type in any year) stops, in
    words; it is not put on either side. The "all other" effect is the sum of the two coefficients with its standard
    error.
    """
    check_specification(choices)
    p = build_panel(outcome, regressor, share, spending_bn, choices, cap, value_column)
    missing = {u for u in zip(p.frame.utility_id_eia, p.frame.state) if u not in ownership}
    if missing:
        raise ValueError(f"{len(missing)} units have no ownership class; a unit with no class is not put on the "
                         f"investor-owned side or the all-other side, and the split is not run")
    other = np.array([ownership[u] != "investor_owned" for u in zip(p.frame.utility_id_eia, p.frame.state)])
    out = {"step": step, "spending_series": series_name, "method": OWNERSHIP_METHOD, "other_side": OWNERSHIP_OTHER_RULE,
           "caps": p.caps, "paper": PAPER["ownership_interaction"],
           "comparison": {"label": C_INSTRUMENTED_COMPARISON_LABEL, "verdict": None,
                          "missing_coverage": rt.MISSING_COVERAGE_QUALIFICATION}}
    f = p.frame.assign(other=other.astype(float))
    try:
        f, g1, g2, dropped = _design(Panel(frame=f, caps=p.caps, accounting={}), choices)
        f = f.assign(d_other=f.d * f.other, z_other=f.z * f.other)
        M = within(f[["y", "d", "d_other", "z", "z_other"]].to_numpy(float), g1, g2)
        kabs = absorbed_df_not_nested(g1, g2)
        fit = iv_fit(M[:, 0], M[:, 1:3], M[:, 3:5], g1, choices.small_sample, kabs)
        notes: list = []
        try:
            sw = sw_conditional_f(M[:, 1:3], M[:, 3:5], g1, choices.small_sample, kabs, notes=notes)
            out["sw_f_failure"] = None
        except NumericalFailure as e:                  # the coefficients stand; the F is reported as not computed
            sw = [None, None]
            out["sw_f_failure"] = f"{step}, Sanderson and Windmeijer's F could not be computed: {e}"
        if notes:
            # Reporting only (D-122): the square root at iv_fit's first-stage line is taken inside the conditional F's
            # helper fits too, where nothing reads it. It is said in words here so that it is not silent.
            out["first_stage_se_failure"] = (
                f"{step}, interaction, inside Sanderson and Windmeijer's conditional F: " + "; ".join(notes)
                + ". That standard error and that helper fit's own F are by-products which nothing in this step reads: "
                "the conditional F is computed from the residual regression, and the step's estimates are unchanged")
        a = np.array([1.0, 1.0])
        out.update(investor_owned={"estimate": float(fit.coef[0]), "se": float(fit.se[0]), "sw_f": sw[0]},
                   other_minus_investor_owned={"estimate": float(fit.coef[1]), "se": float(fit.se[1]), "sw_f": sw[1]},
                   all_other={"estimate": float(a @ fit.coef), "se": float(np.sqrt(a @ fit.vcov @ a))},
                   n_obs=fit.n_obs, n_clusters=fit.n_clusters, singleton_rows_dropped=dropped, failure=None)
    except NumericalFailure as e:
        out["failure"] = f"{step}, interaction: could not be estimated: {e}"
    return out


def c0(outcome, counts_polygon, share, choices, **kw) -> StepResult:
    """C0: uninstrumented, their assignment (smallest overlapping polygon), cap at the 99.5th. Band 0.025 to 0.097."""
    return run_step("C0", "uninstrumented, polygon assignment, count capped at the 99.5th", outcome, counts_polygon,
                    share, None, None, choices, CAP_MAIN, False, "C0", "C0", **kw)


def c1(outcome, counts_polygon, share, spending_bn, series_name, choices, **kw) -> StepResult:
    """C1: instrumented, otherwise as C0. Band 0.114 to 0.250 with first-stage F of at least 10."""
    return run_step("C1", "instrumented, polygon assignment, count capped at the 99.5th", outcome, counts_polygon,
                    share, spending_bn, series_name, choices, CAP_MAIN, True, "C1", "C1", **kw)


def c2(outcome, counts_polygon, share, spending_bn, series_name, choices, **kw) -> list[StepResult]:
    """C2: C1 with the cap removed, then at the 99.9th and the 99th. The plan fixes no band for these."""
    out = []
    for cap in C2_CAPS:
        key = "C2_none" if cap is None else f"C2_{cap}"
        lab = "cap removed" if cap is None else f"cap at the {cap}th"
        out.append(run_step(key, f"instrumented, polygon assignment, {lab}", outcome, counts_polygon, share,
                            spending_bn, series_name, choices, cap, True, key, None, **kw))
    return out


def c3(outcome, counts_verified, share, spending_bn, series_name, choices, **kw) -> StepResult:
    """C3: C1 with the inventory's own assignment in place of the polygon."""
    return run_step("C3", "instrumented, the inventory's own assignment, count capped at the 99.5th", outcome, counts_verified,
                    share, spending_bn, series_name, choices, CAP_MAIN, True, None, None, **kw)


def c4(outcome, dose_verified, share, spending_bn, series_name, choices, cap: float | None, **kw) -> StepResult:
    """C4: C3 with our load share in place of the count, same instrument.

    `cap` is required and must be OURS_C4_CAP: the same within-year cap at the 99.5th percentile on the load share as
    on the count, ours, adopted by Joe on 2026-11-19 (D-107). The paper has no load share; it caps both of its own
    measures, the count and the land area, this way ("both winsorized at the 99.5th percentile within-year", Table 1
    notes, p. 13). Any other value is refused in words.
    """
    if cap != OURS_C4_CAP:
        raise ValueError(f"C4's cap is {cap!r}; row C's specification caps the load share at the {OURS_C4_CAP}th "
                         f"percentile within year, as the count (ours, D-107)")
    lab = f"capped at the {cap}th"
    return run_step("C4", f"instrumented, the inventory's own assignment, load share {lab}", outcome, dose_verified, share,
                    spending_bn, series_name, choices, cap, True, None, None, **kw)


# ---------------------------------------------------------------------------------------------------------------
# C5
# ---------------------------------------------------------------------------------------------------------------
def never_host_units(sites: pd.DataFrame, assignment: pd.DataFrame, counts: pd.DataFrame, basis: str) -> set:
    """Units that DO host under the chosen basis (the complement is taken against the sample by `c5`).

    no_assigned_site: every unit to which a data-center site (not crypto), dated or not, is assigned.
    zero_count_panel_years: every unit with a positive operating count in some year 2015-2024.
    """
    if basis == "no_assigned_site":
        dc = set(sites.loc[~sites.is_crypto.astype(bool), "fid"])
        a = assignment[assignment.fid.isin(dc)].dropna(subset=["utility_id_eia"])
        return {(int(u), s) for u, s in zip(a.utility_id_eia, a.state)}
    if basis == "zero_count_panel_years":
        c = counts[counts.year.isin(YEARS) & (counts.value > 0)]
        return {(int(u), s) for u, s in zip(c.utility_id_eia, c.state)}
    raise ValueError(basis)


def c5_reading(never_estimate: float, never_lo: float, never_hi: float, full_estimate: float) -> dict:
    """The plan's three-way reading of C5, as a pure function.

    Branch "instrument_reaches_non_hosts": never-host figure at least half of the full-sample figure AND its 90%
    interval excludes zero. Branch "not_detected": the interval includes zero AND the point estimate is under half.
    Anything else: "unresolved". "At least half" is >=; "under half" is <; the interval includes zero when
    lo <= 0 <= hi (an endpoint exactly at zero includes it). The plan does not say what happens when the full-sample
    figure is zero or negative (half of it is then not a threshold of the kind the sentences describe, and the first
    sentence speaks of "price increases"); the agent's handling is to report "unresolved_plan_silent" with the
    literal branch kept beside it. Non-finite inputs are a numerical failure, reported as such.
    """
    vals = (never_estimate, never_lo, never_hi, full_estimate)
    if not all(np.isfinite(v) for v in vals):
        return {"reading": "numerical_failure", "sentence": None, "literal_branch": None,
                "note": "C5 could not be read: a figure or interval bound is not a finite number"}
    if never_lo > never_hi:
        raise ValueError("interval lower bound above upper bound")
    half = 0.5 * full_estimate
    includes_zero = never_lo <= 0.0 <= never_hi
    if never_estimate >= half and not includes_zero:
        literal = "instrument_reaches_non_hosts"
    elif includes_zero and never_estimate < half:
        literal = "not_detected"
    else:
        literal = "unresolved"
    out = {"literal_branch": literal, "half_of_full": half, "interval_includes_zero": includes_zero,
           "ratio_never_to_full": (never_estimate / full_estimate) if full_estimate != 0 else None}
    if full_estimate <= 0:
        out.update(reading="unresolved_plan_silent", sentence=None,
                   note=("The full-sample figure is zero or negative; the plan's reading is written for a positive "
                         "yardstick and does not say what to do here (agent's handling: reported as unresolved)."))
        return out
    if literal == "instrument_reaches_non_hosts":
        out.update(reading=literal, sentence=C5_SENTENCE_INSTRUMENT_REACHES, note=None)
    elif literal == "not_detected":
        out.update(reading=literal, sentence=C5_SENTENCE_NOT_DETECTED, note=None)
    else:
        out.update(reading="unresolved", sentence=None, note="Reported as unresolved (plan: anything else).")
    return out


def _interval(est: float, se: float, G: int, interval: str, level: float = C5_LEVEL) -> tuple[float, float]:
    q = (1 + level) / 2
    crit = stats.t.ppf(q, G - 1) if interval == "t_G_minus_1" else stats.norm.ppf(q)
    return est - crit * se, est + crit * se


def reduced_form(outcome, regressor, share, spending_bn, series_name, choices, restrict_units=None,
                 label="", **kw) -> StepResult:
    """Price on Z with the two sets of fixed effects, clustered by utility-state; 90% interval in `extra`."""
    r = StepResult(step="C5", label=label, estimator="reduced_form", spending_series=series_name)
    try:
        p = build_panel(outcome, regressor, share, spending_bn, choices, None, restrict_units=restrict_units, **kw)
        r.accounting = p.accounting
        f, g1, g2, dropped = _design(p, choices)
        r.singleton_rows_dropped = dropped
        M = within(f[["y", "z"]].to_numpy(float), g1, g2)
        fit = iv_fit(M[:, 0], M[:, 1:2], None, g1, choices.small_sample, absorbed_df_not_nested(g1, g2))
        r.estimate, r.se, r.n_obs, r.n_units = float(fit.coef[0]), float(fit.se[0]), fit.n_obs, fit.n_clusters
        lo, hi = _interval(r.estimate, r.se, fit.n_clusters, choices.interval)
        r.extra = {"interval_90": (lo, hi), "interval_basis": choices.interval}
    except NumericalFailure as e:
        r.failure = f"C5 ({label}) could not be estimated: {e}"
    return r


def c5(outcome, share, spending_bn, series_name, choices, hosts: set, value_column: str = "value") -> dict:
    """C5: the reduced form on never-host utility-states against the same on the full sample, then the reading.

    hosts: units that host under the chosen basis (`never_host_units`). The regressor plays no part in a reduced form,
    so an empty one is passed. The paper's 0.155 (0.028) is reported beside our full-sample yardstick as a comparison
    under our specification (C_INSTRUMENTED_COMPARISON_LABEL), not tested against and carrying no verdict.
    """
    empty = pd.DataFrame({"utility_id_eia": pd.Series(dtype=int), "state": pd.Series(dtype=object),
                          "year": pd.Series(dtype=int), "value": pd.Series(dtype=float)})
    full = reduced_form(outcome, empty, share, spending_bn, series_name, choices, label="full sample",
                        value_column=value_column)
    o = outcome.dropna(subset=[value_column])
    all_units = {(int(u), s) for u, s in zip(o.utility_id_eia, o.state)}
    never = all_units - {(int(u), s) for u, s in hosts}
    nh = reduced_form(outcome, empty, share, spending_bn, series_name, choices, restrict_units=never,
                      label="never-host utility-states", value_column=value_column)
    if full.failure or nh.failure:
        reading = {"reading": "numerical_failure", "sentence": None,
                   "note": "; ".join(x for x in (full.failure, nh.failure) if x)}
    else:
        lo, hi = nh.extra["interval_90"]
        reading = c5_reading(nh.estimate, lo, hi, full.estimate)
    if reading.get("sentence") in (C5_SENTENCE_INSTRUMENT_REACHES, C5_SENTENCE_NOT_DETECTED):
        reading["wording_status"] = C5_WORDING_STATUS
    return {"full_sample": full.as_dict(), "never_host": nh.as_dict(), "reading": reading,
            "paper_full_sample": PAPER["C5_full_reduced_form"], "never_host_basis": choices.never_host_basis,
            "never_host_limitation": C5_NEVER_HOST_LIMITATION, "never_host_units_in_outcome": len(never),
            "missing_coverage": rt.MISSING_COVERAGE_QUALIFICATION,
            "yardstick_comparison": {"label": C_INSTRUMENTED_COMPARISON_LABEL, "verdict": None,
                                     "ours_full_sample": full.estimate, "paper_full_sample": PAPER["C5_full_reduced_form"]}}


def run_row_c(outcome, counts_polygon, counts_verified, dose_verified, share, spending_tables: Mapping[str, Mapping],
              choices: Choices, ownership: Mapping[tuple, str], c4_cap: float | None, hosts_for_c5: set,
              c5_counts_name: str, value_column: str = "value") -> dict:
    """Every step in the plan's order, each instrumented step on each spending series given, the paper's first.

    counts_polygon may be None when the polygon assignment does not exist yet; C0 to C2 are then reported as not run,
    with the reason. The specification is checked first and stops the row in words: Choices (check_specification),
    c4_cap (OURS_C4_CAP), the spending series ("paper" required, "current" beside it; a missing "current" is noted),
    and C5's hosts, which must be the units with a positive count in some panel year under the inventory's own
    assignment (counts_verified; OURS_C5_HOSTS_FROM). Every result carries its comparison label and no verdict.
    """
    check_specification(choices)
    if c4_cap != OURS_C4_CAP:
        raise ValueError(f"c4_cap is {c4_cap!r}; row C's specification caps the load share at C4 at the {OURS_C4_CAP}th "
                         f"percentile within year, as the count (ours, D-107)")
    unknown = sorted(set(spending_tables) - set(OURS_C5_SPENDING))
    if unknown or "paper" not in spending_tables:
        raise ValueError(f"spending_tables must carry 'paper' (the paper's printed series, Table S3) and may carry "
                         f"'current' beside it; got {sorted(spending_tables)}")
    own_hosts = never_host_units(None, None, counts_verified, OURS_NEVER_HOST_BASIS)
    if {(int(u), s) for u, s in hosts_for_c5} != own_hosts:
        raise ValueError("hosts_for_c5 is not the set of units with a facility counted in some panel year under the "
                         "inventory's own assignment (counts_verified); row C's specification takes C5's hosts from "
                         "that assignment (ours, D-107)")
    kw = {"value_column": value_column}
    out = {"choices": asdict(choices), "c4_cap": c4_cap, "steps": [],
           "specification": {"settled_from_the_paper": "the module's constants (docs/gate1/bounded-read-row-c-2026-11-19.md)",
                             "ours_adopted_2026_11_19_d107": OURS_APPROXIMATIONS,
                             "exact_reproduction_unavailable": list(UNAVAILABLE)},
           "status": "comparison-only by Joe's ruling of 2026-11-19 (D-109); no step returns a verdict",
           "assignment_c0_to_c2": rt.ROW_U_C_COINCIDENCE,
           "missing_coverage": rt.MISSING_COVERAGE_QUALIFICATION,
           "c5_hosts_from": c5_counts_name}
    if "current" not in spending_tables:
        out["notes"] = ["the current Census spending series was not supplied; the specification reports every "
                        "instrumented step and C5 on it beside the paper's series"]
    if counts_polygon is None:
        out["steps"].append({"step": "C0-C2", "failure": "the polygon assignment table was not supplied; not run"})
    else:
        out["steps"].append(c0(outcome, counts_polygon, share, choices, **kw).as_dict())
    for name in [n for n in OURS_C5_SPENDING if n in spending_tables]:
        sp = spending_tables[name]
        if counts_polygon is not None:
            out["steps"].append(c1(outcome, counts_polygon, share, sp, name, choices, **kw).as_dict())
            out["steps"].append(ownership_split("C1", outcome, counts_polygon, share, sp, name, choices, CAP_MAIN,
                                                ownership, **kw))
            out["steps"].extend(r.as_dict() for r in c2(outcome, counts_polygon, share, sp, name, choices, **kw))
        out["steps"].append(c3(outcome, counts_verified, share, sp, name, choices, **kw).as_dict())
        out["steps"].append(ownership_split("C3", outcome, counts_verified, share, sp, name, choices, CAP_MAIN,
                                            ownership, **kw))
        out["steps"].append(c4(outcome, dose_verified, share, sp, name, choices, c4_cap, **kw).as_dict())
        res = c5(outcome, share, sp, name, choices, hosts_for_c5, value_column)
        res["hosts_from"] = c5_counts_name
        out["steps"].append({"step": "C5", **res})
    return out


# ---------------------------------------------------------------------------------------------------------------
# main(): a quantity-only design summary. Reads no price, revenue or bill.
# ---------------------------------------------------------------------------------------------------------------
def _dist(x: np.ndarray) -> dict:
    x = np.asarray(x, float)
    if len(x) == 0:
        return {"n": 0}
    q = np.percentile(x, [0, 10, 50, 90, 99, 100])
    return {"n": int(len(x)), "mean": float(x.mean()), "sd": float(x.std(ddof=1)) if len(x) > 1 else 0.0,
            "min": float(q[0]), "p10": float(q[1]), "median": float(q[2]), "p90": float(q[3]), "p99": float(q[4]),
            "max": float(q[5]), "share_zero": float((x == 0).mean())}


def _first_stage_on_stand_in(stand: pd.DataFrame, counts: pd.DataFrame, share, spend: pd.DataFrame, ch: Choices) -> dict:
    """The count on the instrument, quantities only, on the stand-in panel with the count capped at the 99.5th."""
    stand_c = stand.merge(counts, on=KEYS + ["year"], how="left").fillna({"value": 0.0})
    caps = yearly_caps(stand_c, CAP_MAIN, ch.percentile_method)
    out = {}
    for name in ("paper", "current"):
        sp = spending_series(spend, name)
        z = instrument(stand_c, share, sp, ch)
        try:
            pan = Panel(frame=apply_cap(stand_c, caps).rename(columns={"value": "d"}).assign(z=z), caps={}, accounting={})
            f, g1, g2, dropped = _design(pan, ch)
            M = within(f[["d", "z"]].to_numpy(float), g1, g2)
            fit = iv_fit(M[:, 0], M[:, 1:2], None, g1, ch.small_sample, absorbed_df_not_nested(g1, g2))
            out[name] = {"coef": float(fit.coef[0]), "se": float(fit.se[0]),
                         "cluster_robust_f": float((fit.coef[0] / fit.se[0]) ** 2), "n_obs": fit.n_obs,
                         "n_clusters": fit.n_clusters, "singleton_rows_dropped": dropped, "failure": None}
        except NumericalFailure as e:
            out[name] = {"failure": f"first stage could not be estimated: {e}"}
    return out


def _polygon_assignment(sites_full: pd.DataFrame, stand: pd.DataFrame, share, spend: pd.DataFrame, ch: Choices,
                        verified_counts: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """C0 to C2's assignment on data/interim/reconciliation_polygon_incidence.parquet under row C's rule
    (reconciliation_treatment.ROW_C_POLYGON: the smallest containing polygon over every territory in the layer, the type
    not read), mapped through data/interim/panel_reported_ids.parquet, and compared site by site with the inventory's
    own assignment (C3). Quantities only; no file under data/raw is read."""
    inc = pd.read_parquet(INTERIM / "reconciliation_polygon_incidence.parquet")
    rep_ids = pd.read_parquet(INTERIM / "panel_reported_ids.parquet")
    poly = rt.assign_polygon_smallest(sites_full, inc, rep_ids, **rt.ROW_C_POLYGON)
    ver = rt.assign_verified(sites_full)
    dc = sites_full[~sites_full.is_crypto.fillna(False).astype(bool)]
    no_point = set(dc.fid[dc.lat.isna() | dc.lon.isna()])
    un = poly.unassigned.drop_duplicates("fid").set_index("fid").reason
    un = un[un.index.isin(set(dc.fid))]
    kinds = {}
    for fid, r in un.items():
        k = ("no point" if fid in no_point else "a point in no polygon") if r.startswith("no territory polygon") else \
            "an exact tie in area, not broken" if r.startswith("tie in area") else \
            "the chosen polygon's utility is not a panel unit in the site's state" if "not a panel unit" in r else r
        kinds.setdefault(k, []).append(fid)
    cmp = rt.compare_assignments(ver, poly)
    cmp = cmp[cmp.fid.isin(set(dc.fid))]
    both = cmp[(cmp[ver.rule].map(len) > 0) & (cmp[poly.rule].map(len) > 0)]
    counts_poly, report = operating_counts(sites_full[["fid", "energized_year", "is_crypto"]], poly.table)
    stand_p = stand.merge(counts_poly, on=KEYS + ["year"], how="left").fillna({"value": 0.0})
    stand_v = stand.merge(verified_counts, on=KEYS + ["year"], how="left").fillna({"value": 0.0})
    cap = yearly_caps(stand_p, CAP_MAIN, ch.percentile_method)
    capped = apply_cap(stand_p, cap)
    hit = capped.value.to_numpy(float) < stand_p.value.to_numpy(float)
    out = {
        "status": ("Built and run on the real quantity files for the assignment and the counts (no price read). C0 to C2 "
                   "themselves are regressions on price and wait for the freeze."),
        "rule": poly.rule,
        "rule_is": ("the smallest polygon containing the site over every territory in the layer, the type not read "
                    "(Scalera, Bosetti and Pecci S1.1, p. 25; section 2.1, p. 4); that the type plays no part is our "
                    "reading of the paper's words, adopted by Joe on 2026-11-19 (D-111). Every polygon of this copy is "
                    "classed ambiguous, which this rule does not read."),
        "coincidence_with_row_u_u0": rt.ROW_U_C_COINCIDENCE,
        "identity_with_u0_site_by_site": {
            k: (len(v) if k == "differ" else v) for k, v in
            rt.identical_site_by_site(poly, rt.assign_polygon_smallest(sites_full, inc, rep_ids, **rt.ROW_U_POLYGON),
                                      dc.fid).items()},
        "missing_coverage": rt.MISSING_COVERAGE_QUALIFICATION,
        "status_d109": "comparison-only by Joe's ruling of 2026-11-19 (D-109); C0 to C2 return no verdict",
        "layer_note": ("This copy of the HIFLD layer has 2,931 polygons (data/frozen/reconciliation_polygon_incidence_"
                       "summary.json), where the paper counts 3,805 utility-State territories in the contiguous states "
                       "(S1.1, p. 25), so it is not shown to be the paper's layer; exact reproduction of the "
                       "assignment is unavailable."),
        "inputs": ["data/interim/reconciliation_polygon_incidence.parquet", "data/interim/panel_reported_ids.parquet",
                   "data/interim/facilities.parquet"],
        "data_center_sites": int(len(dc)),
        "data_center_sites_mapped_to_a_panel_unit": int(poly.table.fid.nunique()),
        "data_center_sites_not_placed_by_kind": {k: len(v) for k, v in sorted(kinds.items())},
        "exact_area_ties_not_broken": {f: un[f] for f in kinds.get("an exact tie in area, not broken", [])},
        "sites_depending_on_ambiguous_polygon_classes": int(len(poly.depends_on_ambiguous)),
        "against_the_inventorys_own_assignment_C3": {
            "data_center_sites_placed_by_C3": int(ver.table[ver.table.fid.isin(set(dc.fid))].fid.nunique()),
            "placed_by_both": int(len(both)),
            "placed_by_both_on_the_same_unit": int(both.agree.sum()),
            "placed_by_both_on_different_units": int((~both.agree).sum()),
            "placed_by_the_polygon_rule_only": int(((cmp[poly.rule].map(len) > 0) & (cmp[ver.rule].map(len) == 0)).sum()),
            "placed_by_C3_only": int(((cmp[ver.rule].map(len) > 0) & (cmp[poly.rule].map(len) == 0)).sum()),
        },
        "operating_counts_polygon_assignment": report,
        "on_stand_in_panel": {
            "units_with_one_or_more_in_2024": {"polygon": int((stand_p[stand_p.year == 2024].value > 0).sum()),
                                               "C3_inventory": int((stand_v[stand_v.year == 2024].value > 0).sum())},
            "sites_operating_in_panel_units_2024": {"polygon": float(stand_p[stand_p.year == 2024].value.sum()),
                                                    "C3_inventory": float(stand_v[stand_v.year == 2024].value.sum())},
            "units_where_the_2024_count_differs": int((stand_p[stand_p.year == 2024].value.to_numpy()
                                                       != stand_v[stand_v.year == 2024].value.to_numpy()).sum()),
            "cap_99_5": {"units_changed": int(capped.loc[hit, KEYS].drop_duplicates().shape[0]),
                         "unit_years_changed": int(hit.sum()), "max_before_cap": float(stand_p.value.max()),
                         "max_after_cap": float(capped.value.max())},
            "first_stage_count_on_instrument_cap_99_5": _first_stage_on_stand_in(stand, counts_poly, share, spend, ch),
        },
    }
    return counts_poly, out


def ownership_comparison_block(q: pd.DataFrame, sample_units: set, adopted: Mapping[tuple, str]) -> dict:
    """The unit-by-unit comparison, counts only, between row C's classes under D-117 and D-119 (`adopted`, from
    adopted_row_c_ownership) and the panel's `ownership` column as this summary read it before D-117 (the first row of
    each utility-state, q.drop_duplicates(KEYS)). Pure: takes the quantities (utility_id_eia, state, year,
    entity_type, ownership), the balanced stand-in sample's units and the adopted mapping.

    Compared on every panel unit and on the stand-in sample's units: units whose class differs, and units whose side
    of the ownership split differs (investor_owned against every other class, what C1's and C3's split use). A unit
    absent from `adopted` (no entity type in any year) is counted apart as having no class and is not compared as if
    it had one. The years present, units with more than one distinct entity type or ownership value across years, and
    units with no entity type are reported, with the plain statement of what the panel's column is and of Joe's
    ruling on it, that rows U and C keep it, described as the utility-level modal reported type carried across the
    panel, with no further raw-data investigation (reconciliation_mu.PANEL_ENTITY_TYPE_STATEMENT, D-119). Nothing here
    claims equivalence with EIA's year-by-year record."""
    units = [(int(u), s) for u, s in q[KEYS].drop_duplicates().itertuples(index=False, name=None)]
    before = {(int(u), s): o for (u, s), o in q.drop_duplicates(KEYS).set_index(KEYS).ownership.items()}
    et_n = q[q.entity_type.notna()].groupby(KEYS).entity_type.nunique()
    own_n = q[q.ownership.notna()].groupby(KEYS).ownership.nunique()
    no_type = q.groupby(KEYS).entity_type.apply(lambda s: bool(s.isna().all()))

    def cmp(us) -> dict:
        us = sorted(us)
        no_class = [u for u in us if u not in adopted]
        both = [u for u in us if u in adopted]
        before_missing = [u for u in both if before.get(u) is None or (isinstance(before.get(u), float)
                                                                       and np.isnan(before.get(u)))]
        comparable = [u for u in both if u not in set(before_missing)]
        return {"units": len(us), "units_with_no_class_under_d117": len(no_class),
                "units_with_a_class_under_d117_and_no_value_in_the_panel_ownership_column": len(before_missing),
                "units_compared": len(comparable),
                "units_whose_class_differs": sum(1 for u in comparable if adopted[u] != before[u]),
                "units_whose_investor_owned_side_differs": sum(
                    1 for u in comparable if (adopted[u] == "investor_owned") != (before[u] == "investor_owned"))}
    years = sorted(int(y) for y in pd.unique(q.year))
    return {
        "specification": rmu.OWNERSHIP_SPECIFICATION_D117,
        "mapping": dict(ROW_C_OWNERSHIP_MAP),
        "split": "investor_owned on one side; on the other, " + OWNERSHIP_OTHER_RULE + " (OWNERSHIP_OTHER_RULE, unchanged)",
        "compared_against": ("the panel's ownership column as this summary read it before D-117: the first row of each "
                             "utility-state (q.drop_duplicates on utility_id_eia and state)"),
        "all_panel_units": cmp(units),
        "balanced_stand_in_sample_units": cmp(sample_units),
        "steps_a_difference_would_touch": ("C1's and C3's ownership split (ownership_split, investor_owned against every "
                                           "other class), on each spending series; no other step of row C reads "
                                           "ownership. The by_ownership count of this summary also uses it."),
        "years_present_in_the_panel": {"first": years[0] if years else None, "last": years[-1] if years else None,
                                       "count": len(years),
                                       "equal_to_the_years_searched": years == list(rmu.OWNERSHIP_YEARS_SEARCHED)},
        "units_with_more_than_one_distinct_entity_type_across_years": int((et_n > 1).sum()),
        "units_with_more_than_one_distinct_ownership_value_across_years": int((own_n > 1).sum()),
        "units_with_no_entity_type_in_any_year": int(no_type.sum()),
        "what_the_panel_column_is": rmu.PANEL_ENTITY_TYPE_STATEMENT,
        "not_established": ("the type EIA reports for each utility year by year. The panel carries one type per utility "
                            "id, and Joe ruled on 2026-11-20 (D-119) that rows U and C keep it, described as the "
                            "utility-level modal reported type carried across the panel, with no further raw-data "
                            "investigation, so no comparison with a year-by-year record is made. These are counts on "
                            "the panel's column only."),
        "no_class_is": rmu.OWNERSHIP_MISSING_TREATMENT,
    }


def main() -> int:
    sites = pd.read_parquet(INTERIM / "facilities.parquet",
                            columns=["fid", "state", "energized_year", "mw_full", "is_crypto", "utility_id_eia",
                                     "utility_assign", "lat", "lon"])
    verified = sites[["fid", "utility_id_eia", "state"]]
    q = pd.read_parquet(INTERIM / "panel_quantities.parquet",
                        columns=["utility_id_eia", "state", "year", "entity_type", "ownership"])
    q["utility_id_eia"] = q.utility_id_eia.astype(int)
    own_c = adopted_row_c_ownership(q)                       # D-117
    fiber = pd.read_csv(FROZEN / "fiber_share_by_unit.csv")
    spend = pd.read_csv(FROZEN / "dc_construction_spending.csv")
    share = share_map(fiber)
    ch = SPECIFICATION

    counts, count_report = operating_counts(sites, verified)
    units_q = balanced_units(q[q.year.isin(YEARS)][KEYS + ["year"]].drop_duplicates())
    contiguous = {u for u in units_q if u[1] not in NON_CONTIGUOUS}
    with_share = {u for u in contiguous if u in share}
    hosts_any = never_host_units(sites, verified, counts, "no_assigned_site")
    hosts_count = never_host_units(sites, verified, counts, "zero_count_panel_years")

    # The quantity-row panel: a stand-in for the price-balanced sample, which needs non-missing prices to form.
    stand = pd.DataFrame([(u, s, y) for (u, s) in sorted(with_share) for y in YEARS], columns=KEYS + ["year"])
    stand_c = stand.merge(counts, on=KEYS + ["year"], how="left").fillna({"value": 0.0})
    caps = {m: {str(p): yearly_caps(stand_c, p, m) for p in (99.5, 99.9, 99.0)} for m in ("stata_default", "linear")}
    counts_by_year = {int(y): {"sites_operating_in_panel_units": float(g.value.sum()),
                               "units_with_one_or_more": int((g.value > 0).sum()), "max": float(g.value.max())}
                      for y, g in stand_c.groupby("year")}

    inst, first = {}, {}
    for name in ("paper", "current"):
        sp = spending_series(spend, name)
        z = instrument(stand_c, share, sp, ch)
        inst[name] = {"spending_bn_2021_2024": {y: sp[y] for y in range(2021, 2025)},
                      "z_post_years": _dist(z[stand_c.year.to_numpy() >= POST_FROM])}
        try:
            pan = Panel(frame=apply_cap(stand_c, caps["stata_default"]["99.5"]).rename(columns={"value": "d"})
                        .assign(z=z), caps={}, accounting={})
            f, g1, g2, dropped = _design(pan, ch)
            M = within(f[["d", "z"]].to_numpy(float), g1, g2)
            fit = iv_fit(M[:, 0], M[:, 1:2], None, g1, ch.small_sample, absorbed_df_not_nested(g1, g2))
            first[name] = {"coef": float(fit.coef[0]), "se": float(fit.se[0]),
                           "cluster_robust_f": float((fit.coef[0] / fit.se[0]) ** 2), "n_obs": fit.n_obs,
                           "n_clusters": fit.n_clusters, "singleton_rows_dropped": dropped, "failure": None}
        except NumericalFailure as e:
            first[name] = {"failure": f"first stage could not be estimated: {e}"}

    dose = pd.read_parquet(INTERIM / "utility_year_dose.parquet", columns=KEYS + ["year", "dose"])
    _, poly_summary = _polygon_assignment(sites, stand, share, spend, ch, counts)
    cap_check = {}
    for m in ("stata_default", "linear"):
        capped = apply_cap(stand_c, caps[m]["99.5"])
        hit = capped.value.to_numpy(float) < stand_c.value.to_numpy(float)
        cap_check[m] = {"units_changed": int(capped.loc[hit, KEYS].drop_duplicates().shape[0]),
                        "unit_years_changed": int(hit.sum()), "max_after_cap": float(capped.value.max()),
                        "max_before_cap": float(stand_c.value.max())}
    s3 = {k: v for k, v in PAPER["spending_table_s3_bn_real_2024"].items() if isinstance(k, int)}
    on_file = spending_series(spend, "paper")
    paper_comparison = {
        "what_this_is": ("Quantity-side figures beside the numbers the paper prints, from the bounded read "
                         "(docs/gate1/bounded-read-row-c-2026-11-19.md). For comparison only; no band applies."),
        "cap_99_5_on_stand_in_panel": cap_check,
        "paper_cap_99_5": {"units_adjusted": PAPER["C1"]["units_adjusted"], "max_stock_after_cap": PAPER["C1"]["max_stock"],
                           "source": "paper S2.8, p. 50; Table S14 Panel A col 3, p. 51"},
        "fiber_share_percent_paper_table_s4": PAPER["fiber_share_percent"],
        "spending_column_matches_paper_table_s3": bool(set(on_file) == set(s3) and
                                                       all(abs(on_file[y] - s3[y]) < 1e-9 for y in s3)),
    }
    summary = {
        "what_this_is": ("Provisional quantity-side summary for reconciliation row C (Scalera, Bosetti and Pecci). "
                         "No price, revenue or bill is read. The design stands as of 2026-11-18 and the pre-analysis "
                         "plan is a draft, not frozen. Every figure below uses row C's specification: the paper's values "
                         "where the bounded read of 2026-11-19 settled them and this study's approximations, ours and "
                         "not the paper's, adopted by Joe on 2026-11-19 (D-107; reconciliation_c.SPECIFICATION), and the panel "
                         "here is balanced on the quantity file's rows, a stand-in for the paper's rule (ten years of "
                         "non-missing price), which cannot be applied without reading price. The nominal price series "
                         "(res_price, our comparison specification) and the ownership classes (the panel's entity "
                         "type, read over 2001 to 2025) were settled by Joe on 2026-11-20 (D-117), and he ruled the "
                         "same day (D-119) that the type is kept and described as the utility-level modal reported "
                         "type carried across the panel, not the latest year-by-year EIA classification; the "
                         "price series is stated here and no price is read for it."),
        "written_by": ("pipeline/analysis/reconciliation_c.py main(); the polygon assignment for C0 to C2 added in "
                       "session 21, 2026-11-19; the D-109 labels, the identity with row U's U0 and the missing-coverage "
                       "qualification added in session 22; the price deflator as ours (D-111) and the polygon rule's "
                       "reading unmarked (D-111) in session 23; the nominal price series as our comparison "
                       "specification and the ownership classes by the panel's entity type read over 2001 "
                       "to 2025 (both D-117) in session 26, 2026-11-20, and that type described as the utility-level "
                       "modal reported type carried across the panel under Joe's ruling of the same day (D-119)"),
        "choices_specification_d107": asdict(ch),
        "facility_counts_verified_assignment": {"report": count_report, "by_year_on_stand_in_panel": counts_by_year},
        "balanced_panel_by_quantity_rows": {
            "units_with_a_row_every_year_2015_2024": len(units_q),
            "of_which_contiguous_48_and_dc": len(contiguous),
            "of_which_with_a_fiber_share": len(with_share),
            "contiguous_without_a_fiber_share": len(contiguous - with_share),
            "by_ownership": pd.Series([own_c[u] for u in sorted(with_share) if u in own_c],
                                      dtype=object).value_counts().to_dict(),
            "by_ownership_is": ("row C's classes by adopted_row_c_ownership, " + rmu.OWNERSHIP_SETTLED_D117 + "; "
                                "units of the stand-in sample with no class are counted apart in "
                                "row_c_ownership_classification_d117 and are in no class here"),
        },
        "never_hosts_on_stand_in_panel": {
            "no_assigned_site": len(with_share - hosts_any),
            "zero_count_panel_years": len(with_share - hosts_count),
            "specification": OURS_NEVER_HOST_BASIS + " (unchanged by D-109)",
            "limitation": C5_NEVER_HOST_LIMITATION,
        },
        "rows_u_and_c_status": ("Comparison-only by Joe's ruling of 2026-11-19 (D-109). " + rt.MISSING_COVERAGE_QUALIFICATION),
        "caps_by_year_on_stand_in_panel": caps,
        "fiber_share_percent_on_stand_in_panel": _dist(np.array([share[u] * 100 for u in sorted(with_share)])),
        "instrument": inst,
        "first_stage_count_on_instrument_verified_assignment_cap_99_5": first,
        "c4_load_share_on_stand_in_panel": _dist(
            stand.merge(dose.assign(utility_id_eia=dose.utility_id_eia.astype(int)), on=KEYS + ["year"], how="left")
            .dose.fillna(0.0).to_numpy()),
        "polygon_assignment_steps_C0_to_C2": poly_summary,
        "paper_comparison": paper_comparison,
        "deflator_on_file": "cpi_u in data/frozen/dc_construction_spending.csv; factors cpi_u[2024]/cpi_u[year]",
        "price_deflator_specification_d111": {
            **OURS_APPROXIMATIONS["price_deflator"], "choices_field": "price_deflator = " + OURS_PRICE_DEFLATOR,
            "years_on_file": sorted(cpi_factors_to_2024(spend)),
            "covers_row_c_window": f"{YEARS[0]}-{YEARS[-1]} (reconciliation_c.YEARS), checked by cpi_factors_to_2024"},
        "price_series_specification_d117": {
            **OURS_APPROXIMATIONS["price_series"], "choices_field": "price_series = " + OURS_PRICE_SERIES,
            "unit_nominal": PRICE_SERIES_UNIT, "unit_after_deflator": PRICE_SERIES_REAL_UNIT,
            "deflator": "price_deflator = " + OURS_PRICE_DEFLATOR + " (D-111), factors from cpi_factors_to_2024",
            "what_the_module_cannot_check": PRICE_SERIES_NOT_CHECKED,
            "price_read_for_this_block": False},
        "row_c_ownership_classification_d117": ownership_comparison_block(q, with_share, own_c),
    }
    OUT.write_text(json.dumps(summary, indent=2, default=lambda o: o.item() if isinstance(o, np.generic) else str(o)) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
