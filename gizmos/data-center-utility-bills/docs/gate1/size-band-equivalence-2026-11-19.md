# The size-band side run: is one sub-experiment per host the pooled form? (2026-11-19, session 22)

Written by a build agent of session 22 under Joe's ruling of 2026-11-19 on the size-band form, in his words: "For the size-band form, test equivalence rather than infer it solely from the absence of shared cohort-and-cell hosts. Check weighting, duplicated rows, controls and fixed effects on invented inputs. Report any difference and defer a new research choice." His earlier question, also in his words: "explain whether the size-band construction's one-sub-experiment-per-host approach changes weighting or duplicates comparisons relative to the intended specification."

Nothing here reads a price, revenue, bill or outcome of a real utility. The comparison on real designs uses the regressors and the implied weights only. Estimates were made on invented outcomes only. Nothing in `pipeline/` was changed and no summary was regenerated. The plan is a DRAFT, not frozen.

## The answer

On the headline set at 2% as it stands, the per-host form as built and the pooled form by cohort and cell are the same design, by test. They stack the same 890 rows over the same 722 observed utility-years with the same multiplicities, the same 26 regressors at full rank, the same fixed effects and controls, and the same weight on every stacked row to within 1.1e-14. Nothing needs switching there.

Where two hosts share a cohort and a cell, the per-host form does change weighting and does duplicate comparisons, relative to the pooled form. Each comparison utility of the shared cell is stacked once per host instead of once, with its own utility effect in each copy. The comparison utilities' total weight on the outcome is not doubled by this. What moves is the weight between hosts: the stacked fit gives each sub-experiment weight in proportion to the within-block variance of the host indicator, so each host in its own block counts as n/(n+1), where pooled hosts sharing a block count as n/(n+m) each (n comparison utilities, m hosts). The per-host form therefore gives hosts that share a cell more weight against the other hosts than the pooled form does. Where ownership eligibility differs between hosts of one cell, the pooled form must also choose which units the block holds, and either choice departs from a rule the plan states (below). None of the headline set's seven hosts shares a cohort and a cell. The companion set, every cohort utility at 2%, has three such pairs.

## What each form is, from the code

**Per host (as built).** `pipeline/analysis/size_band_run.py` builds the design with `design.build_with_rules` under the headline rules with the support rule reported only and no nearest-ten cut, then keeps for each host every eligible unit of its pool whose size band in the cohort's reference year is the host's. The estimate is `outcome_analysis.estimate` on that design. `Design.blocks()` gives one block per host: the host's row and its cell's eligible units. `power_simulation.assemble` stacks each block over the host's ten window years (event years -6 to 3). Rows: the host's ten and ten for each comparison unit; a unit that is a comparison for k hosts enters k times. Fixed effects: one utility effect per unit per block, and block-by-region-by-year effects coded as (block, region in that year, window year). Within a per-host block every unit shares the host's reference-year region and band, so these are the host's cell-by-year effects, with the region read year by year as the main design reads it. Regressors: the host indicator times each event year but -3 (nine columns), heating and cooling degree days, and the state's 2008 to 2010 gas share times each calendar year of the stacked sample, the first calendar year left out and any column the fixed effects and earlier controls make redundant screened out. Clusters: states. Estimand: the mean of the event-year 2 and 3 coefficients.

**Pooled (the plan's words).** PREANALYSIS.md, Size adjustment, defines the side run as "cells of reference-year region by size band; utility effects and cell-by-year effects", and says that the simulation's form "pooled by cohort and cell". `power_simulation.build_blocks` with form `size_band` forms, for each cohort, one block per cell holding every host of that cohort in the cell and every comparison unit in the cell. Stacked by the same `assemble`, everything above is the same except the blocks: one per cohort and cell instead of one per host, so a unit of a shared cell enters once and the block's year effects are fit on all its hosts and comparisons together.

The agent's construction of the pooled form is `tests/size_band_pooled_form.py`, labelled as test support and not a replacement for the module. Its stack calls `power_simulation.assemble` and reproduces `inference_check.fixed_parts` exactly on the per-host blocks (tested). Where the plan's words admit more than one pooled construction it builds each as a named variant:

| Variant | The words it follows | What it does with a unit eligible for one host of a block and not another |
|---|---|---|
| pooled_union | "comparison utilities every unit eligible under the main design's rules", read for the block | keeps it for every host of the block, so the ownership exclusion is not kept for the host it excludes |
| pooled_intersection | the same words, read as eligible for each host | drops it for every host, so a host loses a unit eligible for it |
| pooled_simulation_literal | `power_simulation.build_blocks` as coded, which applies ownership exclusions in the nearest-in-size form only | keeps every comparison-eligible unit of the cell, ownership exclusions not applied at all |
| pooled_union_cell_year_across_cohorts | "cell-by-year effects" read with no cohort in it | union blocks; the year effects of one cell are shared by blocks of different cohorts |

Not built: a block that is a cell alone across cohorts with one copy of each comparison unit. A unit's band and region are measured in each cohort's reference year and can differ between cohorts, and the windows differ, so that form needs choices the plan does not make. The agent's reading is that the plan intends cohort-by-cell blocks, since it names the simulation's form and the simulation's blocks are one cohort each; the across-cohorts variant is built only to show that the reading matters.

## The three invented worlds

The worlds are those of `tests/test_size_band_run_invented.py`: one region over four states, twelve comparison utilities under 10,000 customers, twelve of 10,000 to 99,999 and ten of 100,000 or more. W1 has four hosts in cohorts 2013 to 2016, so no two share a cohort and a cell (hosts 2 and 3 share the middle cell in cohorts 2014 and 2015). W2 puts hosts 2 and 3 both in cohort 2014 in the middle cell, with the same eligible comparisons. W3 adds to W2 a unit of host 3's own utility in another state, in the middle band, so it is eligible for host 2 and not for host 3. Per host is compared with pooled_union unless a row says otherwise; differences are pooled minus per host.

| | W1 | W2 | W3 |
|---|---|---|---|
| Blocks | 4 and 4, the same blocks | 4 and 3 | 4 and 3 |
| Stacked rows | 500 and 500 | 500 and 380 | 510 and 390 (intersection 380) |
| Duplicated rows | none beyond stacking: in both forms a middle-band unit enters once in cohort 2014 and once in 2015 (largest multiplicity 2 in both) | 120 utility-years (the cell's twelve units over ten years) stacked twice per host, once pooled | the same 120; the own-utility unit enters 10 rows in both, with host 3 in its block only under union; intersection drops it, so 10 utility-years used per host are not used at all |
| Fixed effects | 50 utility and 40 cell-by-year in both, partitions identical | 50 and 40 against 38 and 30 | 51 and 40 against 39 and 30 |
| Rank and regressors | 23 of 23 in both, same columns | 23 of 23 in both, same columns | 23 of 23 in both, same columns |
| Controls | the same: degree days and gas share by year, 2007 left out as the first year, none absorbed by the fixed effects | the same | the same |
| Weights on the outcome | identical on every stacked row (largest difference 2.5e-16) | host weights per host 0.2564, 0.2593, 0.2700, 0.2143 against pooled 0.2644, 0.2487, 0.2636, 0.2233; largest difference on a utility-year 0.0081 | largest host-weight difference 0.0105 (union), 0.0116 (intersection); largest on a utility-year 0.0175 and 0.0187 |
| Planted common effect, no noise | both 0.03 exactly | both 0.03 exactly | all three 0.03 exactly |
| Planted host-specific effect (1%, 5%, 5%, 1% in event years 2 and 3) | not run (identical weights) | per host 0.03117, pooled 0.03049 log points, each the sum of its own host weights times the effects | not run |
| One invented outcome with noise (selected procedure) | estimate, CR2 standard error and range identical to 1e-10 | estimate +0.0043, standard error +0.0016 | estimate +0.0034, standard error +0.0015 (union) |
| Across-cohort cell-year variant | a different design: 31 cell-by-year effects instead of 40, largest host-weight difference 0.0029 | the same as union here | the same as union here |

In W2 the weighting follows the closed form exactly when the controls are taken out (a diagnostic, not a form): each block's weight is m n/(m + n), split evenly among its hosts, so hosts 2 and 3 get 12/13 each per host and 12/14 each pooled, against 12/13 for host 1 and 10/11 for host 4 (tested to 1e-12). The controls add a smaller difference of their own, because the duplicated comparison rows count twice in fitting the control coefficients.

## The headline set at 2% as it stands

Built as `size_band_run.main` builds it, from the quantity-side files only. The ten-nearest headline design on the same inputs has design-inputs hash `b8515c35cba1`, the hash on record. Seven hosts, each in its own cohort and cell; no host fails the first limb and none has an empty cell.

| | Per host | pooled_union and pooled_intersection |
|---|---|---|
| Blocks | 7 | 7, the same blocks |
| Stacked rows | 890 | 890 |
| Observed utility-years | 722 | 722 |
| Largest multiplicity | 4 (a comparison unit stacked in up to four cohorts' blocks) | 4 |
| Utility-years with a different multiplicity | | 0 |
| Regressors and rank | 26 of 26 | 26 of 26, same columns |
| Smallest singular value ratio | 0.019878 | 0.019878 |
| Fixed effects | 89 utility, 72 cell-by-year (span 154) | the same, partitions identical row by row |
| Controls | degree days, gas share by year, 2009 left out as the first year, none absorbed | the same |
| Regressors and weight on every stacked row, element by element | | largest difference 1.1e-14 |
| Host headline weights | 803:AZ 0.1393, 6958:TX 0.1609, 14127:NE 0.1552, 14354:UT 0.1471, 15473:NM 0.1297, 17166:NV 0.1099, 20065:GA 0.1580 | the same (largest difference 3.2e-15) |

So the per-host form and the pooled cohort-by-cell form are the same design on this set by the test, not by the absence of shared cells alone. Since the stacked rows, regressors, fixed effects and clusters are identical up to the order of rows, every reading of the selected procedure on any outcome should be identical too (the agent's reading: least squares, the CR2 standard error and its degrees of freedom do not depend on the order of rows; checked on W1 with an invented outcome, not run on the real design, where no outcome was used).

Two variants are not the same design on this set, for reasons other than per host against pooled.

- pooled_simulation_literal stacks 1,050 rows, 160 more, because it admits 16 units the ownership rules exclude for their host (803:AZ 3, 14354:UT 5, 15473:NM 3, 17166:NV 5, by rule 2.2's fail-closed reading for investor-owned units, the own-utility rule and rule 2.3's shared parent). Its largest host-weight difference is 0.0069. This is a difference between the simulation's coded size-band blocks and the plan's definition of the side run, which includes ownership. The side run as built follows the plan here.
- The across-cohort cell-year reading merges the West, 100,000 or more cell's year effects across its four hosts' cohorts (2015, 2017, 2019, 2020): 47 cell-by-year effects instead of 72, largest host-weight difference 0.0112.

## The companion set, where hosts do share a cohort and a cell

The module's `build` and `quantity_summary` take any set, so the companion set, every cohort utility at 2%, is countable with the module's own functions and no new rule. The plan does not say the size-band side run is run on the companion set, and this count does not decide that it is; it shows what would happen. 37 hosts stay after the first limb (14154:NY fails it). Three cohort-and-cell pairs share a block: 3989:CO and 9336:CO (2012, West, 100,000 or more, 13 comparisons each), 4262:TX and 7559:TX (2012, ERCOT, 10,000 to 99,999, 31 each) and 15466:CO and 15473:NM (2019, West, 100,000 or more, 9 each). In each pair both hosts have the same eligible comparisons, so union and intersection agree and no ownership conflict arises.

| | Per host | Pooled |
|---|---|---|
| Blocks | 37 | 34 |
| Stacked rows | 17,880 | 17,350 (530 fewer: the 53 shared-cell units once instead of twice) |
| Utility-years with a different multiplicity | | 503 (27 of the 530 duplicated utility-years fall in both West pairs' overlapping windows) |
| Rank | 31 of 31 | 31 of 31, same controls (2005 left out, none absorbed) |
| Fixed effects | 1,788 utility, 435 cell-by-year | 1,735 and 405 |
| Host weights in the shared pairs | 0.0272 each; 0.0285 each; 0.0265 and 0.0264 | 0.0256 each; 0.0279 each; 0.0243 and 0.0242 |
| Largest host-weight difference | | 0.0022 (15473:NM) |
| Largest difference on a utility-year | | 0.0022 |

On that set the two forms are different designs. The six hosts in shared cells carry between about 2% and 8% less weight pooled than per host (the ERCOT pair, with 31 comparisons each, the least; the 2019 West pair, with 9, the most), and the other 31 hosts together carry correspondingly more, since the host weights sum to one in both forms.

## Recommendation (the agent's, for the owner)

Keep the per-host form as built and switch nothing. On the headline set at 2% it is the pooled form by test. Record beside the side run that this equivalence was tested, and that on a set where hosts share a cohort and a cell the per-host form gives each such host its own block's weight, n/(n+1), where the plan's pooled form gives n/(n+m), so the two are different designs there; and that the plan's parenthetical ("the two are the same design wherever no two hosts share a cohort and a cell") holds for cohort-by-cell blocks with each host's ownership exclusions applied, and not for the simulation's coded blocks, which apply none, nor for cell-by-year effects shared across cohorts. Whether the side run is applied to the companion set, and which form governs where hosts share a cell, is Joe's choice and is not made here.

## Files and how to check

- `tests/size_band_pooled_form.py`: the pooled constructions, the stack, the implied weights (w = X̃(X̃'X̃)⁻¹c, c the mean of event years 2 and 3), the comparison, the selected procedure's reading on an invented outcome, and `python3 -I tests/size_band_pooled_form.py [set]`, which prints the comparison on a real set at 2% from the quantity side and writes nothing.
- `tests/test_size_band_equivalence_invented.py`: the three worlds, 26 tests.
- Run: `python3 -I -m pytest -q -p no:cacheprovider tests/test_size_band_equivalence_invented.py tests/test_size_band_run_invented.py` (36 passed on 2026-11-19).
- The headline and companion figures above were computed on the working tree of 2026-11-19, with `design.py` carrying another agent's one-string change to a description, which builds nothing.
