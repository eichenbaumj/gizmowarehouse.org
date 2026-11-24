# Callaway and Sant'Anna: never-treated units in regions with no host (counted 2026-11-19, session 22)

A count from quantity-side files. It adopts nothing and changes no file. Provisional: the design stands as of 2026-11-18 and the plan is a DRAFT, not frozen. No price, revenue or bill was read.

## The question

The run's sample for the headline set at 2% has 7 hosts and 1,670 never-treated units (`data/frozen/callaway_santanna_sample.json`). Its own list of differences from the main estimate says that never-treated units in a region with no host in its reference year stay in the sample and inform the gas-share slope (`pipeline/analysis/callaway_santanna.py`, `sample_difference`). How many are they, and in which regions?

## How the module reads "region"

Year by year. `frame()` gives each unit-year its own region from `market_region.by_unit_year(q)` as dummy columns, and the package reads covariates at the base period of each group-time effect, which under two years of anticipation is g-3, the cohort's reference year (module docstring, "Covariates and the region of a unit that changes region"). So for cohort g, a never-treated unit's region is its region in g-3, and a host's region is its region in its own g-3. A never-treated unit serves every cohort, so it can be in a host's region for one cohort and not for another; there is no single region per never-treated unit.

The seven hosts keep one region through their whole windows: West (803:AZ, cohort 2020; 14354:UT, 2015; 15473:NM, 2019; 17166:NV, 2017), ERCOT (6958:TX, 2017), SPP (14127:NE, 2019) and Southeast (20065:GA, 2021).

## Method

The sample file lists the steps and counts but not the never-treated units by id, and carries no region. So the module's own `sample()` was called, from a script in the agent's scratch folder, on exactly the inputs its `main()` builds for the headline set at 2%: `panel.load_quantities()` (`data/interim/panel_quantities.parquet`, which has no price column), `utility_year_dose.parquet`, `market_region.by_unit_year(q)` (with `market_moves.csv` and `pjm_late_zones.csv`), `ps.load_controls()` and `ps.rule_inputs()` (the frozen fuel-mix and degree-day files, `ownership.csv`, and the usable flag read through `usable_flag.read`, five columns of the quantities file), `ps.load_unknown_load()`, `ps.history_settled(0.02)`, `ps.price_hold()` and `aside_sets(0.02, "headline_set")`. Before calling it, the code was read to confirm that `sample()` takes every input as an argument and opens no file, and that none of these loaders opens an outcome (`frame()` and `run()`, which take outcomes, were not called; neither was `design.build_with_rules`). The call returned 7 hosts and 1,670 never-treated units, the figures in the sample file. Regions were then looked up in `market_region.by_unit_year(q)`.

## The count

**By cohort, as the package reads it** (a never-treated unit's region in g-3 against the regions of that cohort's hosts in g-3). "Usable at g-3" matters because only a unit with a row at g-3 enters that cohort's cells.

| Cohort | g-3 | Its hosts' regions | Never-treated units in another region | of them usable at g-3 | Never-treated units in a host's region |
|---|---|---|---|---|---|
| 2015 | 2012 | West | 1,446 | 1,228 | 224 |
| 2017 | 2014 | ERCOT, West | 1,381 | 1,185 | 289 |
| 2019 | 2016 | SPP, West | 1,206 | 1,015 | 464 |
| 2020 | 2017 | West | 1,438 | 1,218 | 232 |
| 2021 | 2018 | Southeast | 1,211 | 1,005 | 459 |

By region, units outside the cohort's host regions:

| Cohort (g-3) | California | ERCOT | ISO-NE | MISO | NYISO | PJM | SPP | Southeast | Upper Midwest, no market | West |
|---|---|---|---|---|---|---|---|---|---|---|
| 2015 (2012) | 21 | 66 | 63 | 334 | 27 | 163 | 188 | 531 | 53 | |
| 2017 (2014) | 22 | | 63 | 394 | 27 | 178 | 187 | 457 | 53 | |
| 2019 (2016) | 22 | 66 | 63 | 391 | 26 | 179 | | 459 | | |
| 2020 (2017) | 22 | 66 | 63 | 392 | 26 | 179 | 231 | 459 | | |
| 2021 (2018) | 22 | 66 | 63 | 392 | 26 | 179 | 231 | | | 232 |

**Units that are never in a host's region, two readings:**

- *In no cohort's host region at that cohort's own g-3:* **680 units** of 1,670. In 2017 they are in California (21), ISO-NE (63), MISO (391), NYISO (26) and PJM (179). In 2012, 75 of them were in Southeast and moved to MISO by 2014. 77 of the 680 change region across the five reference years, and 6 have no usable year from 2005 to 2025.
- *In none of the four host regions (West, ERCOT, SPP, Southeast) at any of the five reference years:* **605 units**: California 21, ISO-NE 63, MISO 332, NYISO 26 and PJM 163 in 2017. This is a subset of the 680.

Counted one reference year at a time against the four host regions together, the units outside them number 661 (2012), 737 (2014), 681 (2016), 682 (2017) and 682 (2018); 53 units in 2012 and 2014 sit in "Upper Midwest, no market" and are in SPP from 2016.

How each region was set, for the never-treated units in the reference years: by EIA's reported code for most (1,383 to 1,436 units a year from 2014; in 2012 none was reported and 1,424 were carried from the nearest year with a code), by a dated market move for 11 to 217, and by the state's most common region for 29 (`market_region.by_unit_year`, column `basis`). 139 of the 1,670 change region across the five reference years.

## Consequence

If the 680 units that are in no cohort's host region at that cohort's reference year were dropped, the run would have 990 never-treated units against the same 7 hosts (1,065 if only the 605 of the stricter reading were dropped); dropping units cohort by cohort instead would leave 224 to 464 per cohort, which one frame cannot carry, since one never-treated unit serves every cohort (module docstring).

## Limits

The count reads region as `market_region.by_unit_year` sets it, including carried and state-based codes, and does not test them. It says nothing about whether such units should stay; the module states that they do and that region enters as a covariate rather than as a matching rule. Whether the package uses a unit-year's region dummy for a region with no treated unit in a cell is a property of its outcome regression and was not examined here.
