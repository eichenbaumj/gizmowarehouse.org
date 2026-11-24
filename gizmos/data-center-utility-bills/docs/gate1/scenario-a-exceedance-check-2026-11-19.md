# Sensitivity scenario A: the capacity exceedance check (session 23, 2026-11-19)

Written by a build agent of session 23 for job 1 of `HANDOVER_session23_2026-11-19.md`, stage 1 only. Quantity side only: site assignments, candidate lists, scaled full loads and retail sales (as capacity). Nothing here reads a dose, a price, a revenue, a bill or an estimate. Neither `pipeline/analysis/second_number_scenarios.py`, its tests nor `data/frozen/second_number_scenarios.json` was edited for the check itself (see the note below). The plan is a DRAFT and not frozen; every figure here is provisional, on the design as it stands.

**Note added 2026-11-19, after the check.** The session verified this check, and since neither deferring case occurs, Joe's rule was applied: `pipeline/analysis/second_number_scenarios.py` was brought to the lift-first rule after this check was made. The checker's `MODULE_READING` is now the lift-first reading, and the reading this file first called the module's is kept as `EARLIER_MODULE_READING`. In this file and in the CSV the comparison reading is therefore named the module's earlier reading (`earlier_module_reading` in the CSV's `reading` column, and `carries_one_under_earlier_module_reading_only` for the flag). The CSV was regenerated with those names and its figures are unchanged.

Joe's words (D-111): "check whether returning a site to its original utility when no alternative fits creates a final capacity exceedance because other sites have occupied that space. Distinguish pre-existing exceedances from newly introduced ones." His clarification: "defer the item if lifting first either introduces a capacity exceedance or increases a pre-existing exceedance."

**Result.** Lifting first does not introduce a capacity exceedance, and does not increase a pre-existing one. Under the lift-first rule, two units are over capacity at the end, both over capacity already in the inventory as assigned, and neither carries more at the end than as assigned. No returned site finds its space taken by arriving sites: on the 14 units where a returned site and arriving sites end together, the smallest headroom left is 162.9 GWh. The module's earlier reading gives the same two units in the same class.

## 1. What was checked, and how

The check is `tests/scenario_a_exceedance_check.py`, written beside the independent checker of session 22 (`tests/scenario_a_independent_check.py`) and built on its placement function and its named readings. It imports nothing from `second_number_scenarios.py` and calls no function in `pipeline/`. It reads what the checker reads and nothing else: nine columns of `data/interim/facilities.parquet` and five of `data/interim/panel_quantities.parquet`, and the balancing-authority table read as data from `pipeline/electricity/market_region.py`.

Two placements are accounted for, on the same inputs:

- **The lift-first rule** (Joe's preferred rule; the checker's `Reading(carried="resolved_only")`). The 460 unresolved load-carrying sites are lifted off, every other site stays counted where the inventory has it, and the 460 are placed in descending size, ties by site id. Each site goes to the first other candidate that can hold it on top of what that candidate carries at that moment; if none can, it is returned to the unit it was on, with no capacity test, and its load is counted there from its turn on.
- **The module's earlier reading** (interpretation N-2; `EARLIER_MODULE_READING` in the checker, `earlier_module_reading` in the CSV), for comparison only. Every site of the inventory counts where it sits at the start, the 460 included, and a site that moves is taken off its old unit and added to its new one.

**The definitions, in words.**

- *Capacity:* the unit's largest annual total retail sales in 2020 and later, in GWh (MWh over 1,000). The panel ends in 2025, so this is 2020 to 2025. It is computed in `pipeline/facilities/build_inventory.py` just before `pick_utilities` is called (`capacity = (q[q.year >= 2020].groupby(["utility_id_eia", "state"]).total_retail_mwh.max() / 1000.0)`, line 524) and passed to it; the checker's `capacity_from_sales` computes the same. A unit with no sales value in those years has no recorded capacity measure; the rule has no measure for it.
- *Load as assigned:* every site of the inventory on the unit (utility and state not missing), at scaled full load (`mw_full` times 8.76, in GWh), the 460 included where they sit now. This is what the checker counts at the start under the module's earlier reading. It includes crypto mines and sites with no start date, and a site with no full load counts zero, as the checker counts them.
- *Final load:* every site that is not one of the 460, where the inventory has it, plus each of the 460 where the placement ends it, moved or returned.
- *Over capacity:* load strictly greater than capacity. `pick_utilities` treats `used + gwh <= cap` as fitting (line 172), and the checker does the same (`have + g <= capacity`), so a load equal to capacity is within it. No tolerance is used anywhere.
- *Returned site:* one of the 460 that ends on the unit it was on, either because no other candidate fit or because it had no other panel candidate; the reason is listed with each. *Arriving site:* one of the 460 placed on the unit from elsewhere.

**The three classes** of a unit whose final load exceeds its capacity:

1. *pre-existing:* over capacity as assigned, and its final load no larger than its load as assigned;
2. *newly introduced:* within capacity as assigned, over it at the end;
3. *pre-existing and made larger:* over capacity as assigned, and its final load larger than its load as assigned.

The second and the third defer the item and are reported apart. A unit with no recorded capacity measure cannot be classed and is reported as such.

**Arithmetic.** Each unit's loads are summed with `math.fsum` over its sites' loads, so a unit carrying the same sites before and after has exactly the same load before and after. As a separate check, each moved site's capacity test was recounted in processing order with `fsum`; every arrival passes under the recount too, and the smallest margin is 0.0985 GWh (unit 27000 in Colorado), so no test sits within floating-point noise of its capacity. No unit's load is within 1e-6 GWh of its capacity, and no unit's difference is nonzero and under 1e-6 GWh. Summed over all units in the table, load as assigned and final load are equal under both readings (difference exactly 0.0).

## 2. The placements are the checker's

| | Lift-first | Module's earlier reading |
|---|---:|---:|
| Sites placed | 460 | 460 |
| Sites that move | 380 | 379 |
| Units gaining or losing a site | 121 | 120 |
| Sites returned: no other candidate fits | 62 | 63 |
| Sites returned: no other panel candidate | 18 | 18 |
| Units carrying any of the 460 before or after (the table) | 131 | 131 |

The counts 380 and 121, and 379 and 120, are the ones on file in `docs/gate1/scenario-a-count-reconciliation-2026-11-19.md`, so the accounting sits on the same placements. Every unit that carries one of the 460 under the module's earlier reading also carries one under the lift-first rule; no unit is in the table only under the earlier reading. The 27 sites whose destination differs between the two readings are listed site by site in that file, section 4.

## 3. Classification counts

| Class | Lift-first | Module's earlier reading |
|---|---:|---:|
| Within capacity at the end (and as assigned) | 128 | 128 |
| Over as assigned, within at the end | 0 | 0 |
| Pre-existing | 2 | 2 |
| **Newly introduced** | **0** | **0** |
| **Pre-existing and made larger** | **0** | **0** |
| No recorded capacity measure (cannot be classed) | 1 | 1 |
| Total units | 131 | 131 |

## 4. Every unit over capacity, or with no recorded capacity measure, under either reading

The two readings give the same figures for these three units.

| Unit | Capacity (GWh) | Load as assigned | Final load | Difference | Class | Excess at the end | Excess as a share of capacity |
|---|---:|---:|---:|---:|---|---:|---:|
| 6182, TX | 1,883.777 | 3,810.600 | 3,810.600 | 0.000 | pre-existing | 1,926.823 | 102.3% |
| 3461, WY | 2,674.936 | 2,939.520 | 2,895.225 | -44.295 | pre-existing | 220.289 | 8.2% |
| 44372, TX | no measure | 773.683 | 773.683 | 0.000 | no recorded capacity measure | | |

What makes up each one:

- **6182 in Texas.** Its only site is `bi:930-0`, one of the 460, at 3,810.600 GWh, returned because no other candidate fits. No other site is on the unit as assigned or at the end, and nothing arrives. The site's own load is about twice the unit's capacity; its other panel candidates are 8620 (688.222 GWh), 18976 (1,574.149 GWh), 40051 and 44372, neither of which has a recorded capacity measure, so none could hold it either. The inventory has it as `fallback_largest_flagged`. The excess is the site alone and not a site finding its space taken.
- **3461 in Wyoming.** The sites that are not among the 460 carry 2,895.225 GWh, of which two hand-verified sites carry 2,895.225 (`bi:1122-0`, 1,563.705 GWh, and `epoch:Meta Cheyenne`, 1,331.520 GWh); fifteen other sites on it carry no load. Those alone exceed the capacity. The one site of the 460 on it, `bi:1123-0` (44.295 GWh), leaves for 19545 under both readings. No site is returned to it and none arrives. Its excess falls from 264.584 GWh as assigned to 220.289 at the end.
- **44372 in Texas** has no retail sales value in 2020 to 2025, the years the placement rule measures capacity from (its panel rows are for 2001, 2008 and 2009 only), so the rule has no recorded capacity measure for it and it cannot be over or within. Its one site of the 460, `bi:900-0` (773.683 GWh), is returned because its one other panel candidate, 40051, has no recorded capacity measure either, for the same reason (the session's reading on 2026-11-20 that Joe's wording for 44372 covers a unit in the same situation; his to strike). Its load does not change.

## 5. Returned sites that end beside arriving sites

This answers Joe's question directly. Under the lift-first rule 27 units end with at least one returned site, and 14 of those also receive arriving sites. On each, the final load and the headroom left (capacity less final load), in GWh:

| Unit | Capacity | Load as assigned | Final load | Headroom | Returned | Arriving |
|---|---:|---:|---:|---:|---:|---:|
| 19490, TX | 2,848.697 | 902.280 | 2,685.804 | 162.893 | 1 | 3 |
| 27369, TX | 575.297 | 0.000 | 0.000 | 575.297 | 1 | 1 |
| 12260, VA | 2,826.211 | 2,258.808 | 1,845.360 | 980.851 | 2 | 3 |
| 27000, CA | 3,647.866 | 0.208 | 2,451.912 | 1,195.954 | 1 | 95 |
| 12698, MO | 8,766.142 | 543.539 | 863.970 | 7,902.172 | 5 | 2 |
| 55937, TX | 22,023.350 | 2,011.327 | 2,040.563 | 19,982.787 | 3 | 1 |
| 54913, MA | 23,410.577 | 827.192 | 1,123.929 | 22,286.648 | 2 | 3 |
| 14354, UT | 27,665.375 | 3,306.567 | 3,300.720 | 24,364.655 | 3 | 1 |
| 15466, CO | 28,932.674 | 1,454.960 | 1,806.524 | 27,126.150 | 28 | 3 |
| 16572, AZ | 34,397.819 | 6,739.030 | 6,060.924 | 28,336.895 | 3 | 2 |
| 14006, OH | 55,525.629 | 9,884.075 | 11,792.727 | 43,732.902 | 2 | 3 |
| 14328, CA | 78,906.970 | 2,627.774 | 5,245.827 | 73,661.143 | 4 | 74 |
| 7140, GA | 89,298.710 | 11,871.891 | 15,376.329 | 73,922.381 | 2 | 8 |
| 17609, CA | 83,507.623 | 893.773 | 816.778 | 82,690.845 | 2 | 7 |

(Unit 27369 in Texas carries two of the 460 with a full load of zero.) The module's earlier reading gives the same 14 units with the same figures except 16572 in Arizona, where `bi:13-0` stays: four returned sites and a final load of 6,453.863 GWh.

Across all 131 units, the units nearest their capacity at the end are ones that receive arrivals and no returned site (27000 in Colorado, 0.098 GWh of headroom; 19604, 12351, 65261, 176 and 5729 in Arizona, 0.44 to 1.55 GWh under the lift-first rule).

## 6. The comparison table for the module's earlier reading

The classes are the same (section 3), and the same units are over (section 4). Nine units end with a different final load under the two readings, all within capacity under both (GWh):

| Unit | Capacity | Final load, lift-first | Final load, module's earlier reading |
|---|---:|---:|---:|
| 803, AZ | 34,197.800 | 11,505.874 | 11,386.589 |
| 5729, AZ | 406.453 | 404.901 | 402.994 |
| 12351, AZ | 326.386 | 325.659 | 325.975 |
| 16572, AZ | 34,397.819 | 6,060.924 | 6,453.863 |
| 19604, AZ | 238.810 | 238.370 | 78.870 |
| 27000, AZ | 328.755 | 54.123 | 0.000 |
| 65261, AZ | 279.168 | 278.423 | 219.983 |
| 1175, TX | 742.094 | 657.000 | 659.190 |
| 7752, TX | 3,030.467 | 2,458.494 | 2,456.304 |

The complete per-unit table under both readings (131 units each, 262 rows) is `data/frozen/scenario_a_exceedance_check.csv`, quantity side only, with each unit's capacity, resident sites and load, load as assigned, final load, difference, class, a floating-point flag, and the returned, arriving and leaving sites with each site's full load.

## 7. Units already over capacity in the inventory as assigned

Five panel units are over capacity as assigned (all sites counted): the two in section 4, and three that carry none of the 460.

| Unit | Capacity | Load as assigned | Excess | Its sites, by how the build placed them |
|---|---:|---:|---:|---|
| 162, SC | 1,043.438 | 1,130.040 | 86.602 | 1 hand-verified |
| 3461, WY | 2,674.936 | 2,939.520 | 264.584 | 2 hand-verified, 1 with candidates widened by a correction, 15 smallest polygon (no load) |
| 6182, TX | 1,883.777 | 3,810.600 | 1,926.823 | 1 `fallback_largest_flagged` |
| 9605, KY | 876.155 | 1,200.120 | 323.965 | 1 hand-verified (a crypto mine) |
| 12268, TX | 1,660.386 | 2,257.452 | 597.066 | 1 `fallback_largest_flagged` (not in the dose) |

**Why that can happen, from the code.** The build places sites with a capacity test only inside `pick_utilities`, and three paths put a site on a unit without one. (a) In `pick_utilities` itself, when no candidate can hold a site, it is placed on the largest reporting candidate anyway and flagged `fallback_largest_flagged` (lines 176 to 181); 6182 and 12268 in Texas are this. (b) After `pick_utilities`, hand-verified assignments from the overrides file are written over its choice with no capacity test (lines 528 to 535); 162, 9605 and the two loaded sites on 3461 are this. (c) The correction entries (`corrections.apply_assignment`, applied after the hand-verified block) assign, reopen or widen candidates, and I found no capacity test in that function. A site's assignment label is what the build recorded; that each of these units became over capacity through the path its labels suggest is the agent's reading of the labels and the code, and the order of events for each unit is not otherwise established.

## 8. What this check does not settle (gaps, not resolved here)

- **Whether the original unit is itself tried.** R2 says "with the utility it is on now moved to the end" and then "if no other candidate fits, the site stays where it is". The checker drops the unit the site is on from the candidates it tests and returns the site there with no capacity test. R2 could also be read as testing that unit last like any other candidate. Either way R2 then keeps the site where it is, so the placement is the same; what differs is only whether a return is called fitting. This check counts every return with no test, as the checker does.
- **When a returned site's load counts.** The checker adds a returned site's load to its unit at the site's own turn in the descending order, so smaller sites tested afterwards see it. R2 does not say when, under the lift-first rule, a returned site counts. Counting returns only after every site has been placed could let more arrivals onto a unit that a returned site later rejoins. Not tried: that would be another placement rule. *Settled 2026-11-20 (Joe, D-113): counting a returned site from its own turn in the ordering stands, and no further placement variant is tested.*
- **The sites with no other panel candidate** (18) are returned with no capacity test as well. Joe's words speak of a site returned "when no alternative fits"; this check counts both kinds as returned and labels each with its reason.
- **What "load as assigned" counts.** It follows the checker's earlier module reading (`all_assigned`): every site on a unit, crypto mines and sites with no start date included. A different scope for the sites that are not among the 460 would change loads as assigned and final loads by the same amount on each unit and could change which units are over; it was not tried.

## Files

- `tests/scenario_a_exceedance_check.py`: the accounting (`site_table`, `account`, `classify`, `arrival_slack`, `inventory_over_capacity`, `run_both`, `main`). `python3 -I tests/scenario_a_exceedance_check.py` prints the summary; with `--write` it also writes the CSV.
- `tests/test_scenario_a_exceedance_check_invented.py`: tests on invented inputs, one world per class and one with none, and four deliberate breaks made in the test process.
- `data/frozen/scenario_a_exceedance_check.csv`: the complete per-unit table, both readings.

Corrected 2026-11-20 at Joe's instruction (D-113): Texas unit 44372 is described as having no recorded capacity measure, where this document first said it had no capacity. No number changed.
