# Umatilla and Portland General: is there an established common change in capped dose? (2026-11-19, session 20)

This is pre-freeze work on a DRAFT pre-analysis plan that is not frozen and is not registered with anyone outside. No price, revenue or bill was read. Every figure below comes from quantity-side files (load, sales, the inventory and its corrections) and is provisional on the design as it stands. Written by a build agent (claude-opus-5-5) for the session; it decides nothing. Which scope Joe's words mean is his to say, and this note reports both.

The code is `pipeline/analysis/common_dose_rule.py` (tests: `tests/test_common_dose_rule_invented.py`). `oregon_detail(scope)` reproduces every number in this note from the quantity files; `oregon_verdicts(scope)` returns the verdicts, with the scope as a required argument.

## 1. The rule being applied

Joe, 2026-11-19, unchanged: "Apply the common-dose exception consistently to Umatilla. If complete admissible histories establish one common change in capped dose, apply that exception for the capped form. Otherwise retain exclusion and state what remains unestablished. Do not decide this merely by following the current code. Keep analysis eligibility separate from simulation-access eligibility." His clarification: "For Umatilla, assess completeness or establish the common capped change by a justified argument within the adopted computational limits. Do not raise the ceiling or launch exhaustive enumeration merely to establish eligibility. If it remains unestablished, retain exclusion and explain the precise gap."

How the cap enters. `second_number.change` caps the load share in each year and then averages, so the change is the mean over 2023 to 2025 of min(share, cap) less the mean over 2008 to 2010 of min(share, cap). So a capped change equals the cap exactly in a history if and only if the share is zero in each of 2008, 2009 and 2010 and at or above the cap in each of 2023, 2024 and 2025 (the before mean cannot be negative, and the after mean cannot exceed the cap).

The computational limits were kept. The ceiling stays at 100,000. No enumeration larger than the one `second_number.unknown_load_histories` already runs was run. Besides rerunning that enumeration (972 configurations, 1,944 histories per utility), the only configurations evaluated were 7 single configurations for Umatilla and 2 for Portland General (one setting changed from the reference in each, two readings each), used as witnesses in section 5.

## 2. Two scopes, kept apart

**Scope (i), "rule_8_1_text".** The histories rule 8.1 and the paragraph "Sites with no load history" define in their own words. Rule 8.1: "The histories are D-46 ruling 4's cases for that utility (as assigned; every unresolved site on it taken off; every unresolved site that lists it as a candidate counted on it), as built and with no anchoring, and, for a utility a site with no load history reaches, that site's admissible histories (below)." The paragraph: "Its two endpoint doses are computed in every admissible history of each such site, crossed with rule 8.1's cases, with the state's factor recomputed in each. The admissible histories are each year of the site's admissible interval, including no operation within the period where the interval allows it, and for `bi:837-0` each capacity case of its open capacity question." and "Which timing cases carry it: the enumeration of `timing.py` for those two sites." In this scope the open questions of the two sites with no load history vary; every other question sits where the inventory as built has it.

**Scope (ii), "place_test_wider_set".** Every open question of every site that reaches the utility, as the place test enumerates it (`pipeline/facilities/timing.py`, module docstring, where the admissible histories are "every combination, one setting per site ... of: each unresolved assignment ... each date question at every year of its interval, open below where it is (full load from 2001), "never" where the interval allows it; each capacity question; the generic screen, CROSSED with all of the above"). The plan uses "every admissible history" in this wider sense for the place test and the future-host criterion ("Both are required in every admissible history the sets test (Joe, D-99)"). This is the set in which Umatilla has 99,574,272 configurations per screen case. The agent's reading is that scope (ii) rests on that usage and on Joe's phrase "complete admissible histories", not on any sentence of rule 8.1 itself.

**How every other utility's histories are defined under rule 8.1 (for "consistently").** For every utility no site with no load history reaches, the histories are the six matrices of `assignment.matrices` (as built, no anchoring, and the lower and upper cases of each), read by `second_number.case_points`. They are built from `facility_year` as the inventory has it, with every date and capacity question at its convention, the generic screen at no shift, the state's factor at its frozen value, and only the assignment of unresolved sites varying between cases. No date or capacity question varies in any ordinary utility's dose range. For example, Portland General's own interval-dated rows `bi:832-0` (2021 or 2022) and `bi:833-0` (2015 to 2019) sit at their conventions in every ordinary treatment, and so would the five Umatilla rows below if no load-unknown site reached Umatilla. Scope (i) gives Umatilla the treatment every other utility gets plus the two sites' histories. Scope (ii) gives Umatilla a set of date questions that no other utility's dose range varies.

## 3. What the enumeration covers (route A)

Read from `second_number.unknown_load_histories`, `rule4_case_settings` and `oregon_state`; `pass_c_exact._State` (`grid`, `factor`, `relevance`); `pass_c_expand._sites`, `_date_values`, `_capacity_values`; the corrections in force (`pipeline/facilities/verified/pass_c_corrections_s17.json`); `data/frozen/unknown_load_sites_and_affected_utilities.json`; `data/frozen/timing_place_test.json`. Rerun through the module's own functions on the quantity files.

The state object is `oregon_state(["bi:837-0", "bi:852-0"])`: Oregon, 43 panel units, 89 sites, screen shift 0 only (`tm.StateRun(..., screen=(0,))`). The enumeration varies every setting of the date and capacity questions of the two sites (`hist_q`), crossed with ruling 4's three cases (assignment questions fixed per case), and stacks the as-built and no-anchoring readings. Every other question is at the reference configuration (`_State.default`). The factor is recomputed in every configuration (`_State.grid` computes `F = factor(M, P)` per configuration from the configuration's 2024 anchoring totals, then as built `8.76 x (measured MW + F x permit raw MW)`, with no anchoring `8.76 x (measured MW / divisor + permit raw MW)`).

| Question | Admissible, from the correction entry | Enumerated | Covered |
|---|---|---|---|
| `bi:837-0` date | earliest 2011, latest 2019, no "never": 2011 to 2019 | 2011 to 2019 (9) | yes |
| `bi:837-0` capacity | rest_earliest 2011 to inventory year 2019 | 2011 to 2019 (9) | yes |
| `bi:852-0` date | earliest 2024, open above, "never" possible: 2024, 2025, any later start (one history, no load in a panel year or in the 2024 anchoring, entered as 2026), never | 2024, 2025, 2026, never (4) | yes |

The admissible lists were derived from the entries apart from the enumeration's code (`common_dose_rule.admissible_settings`) and compared setting by setting. Ruling 4's cases were derived apart as well (`common_dose_rule.rule4_cases`) and match what the enumeration applies. For Umatilla they are as assigned (nothing fixed), lower (`bi:848-0` off the panel; it is the only unresolved site on Umatilla in the inventory), and upper (nothing, since the rows listing Umatilla as a candidate are already on it). On the inventory's own matrices, Umatilla's lower case is lower than its as-built case by 473.69 GWh in 2023 (`bi:848-0`'s 129.54 MW at the frozen factor) and its upper case equals as built, which agrees. For Portland General no assignment question exists in Oregon's enumeration, so its three cases are identical. The count is 2 readings x 3 cases x 9 x 9 x 4 = 1,944 histories per utility, as returned.

Two further facts the coverage check makes plain. `bi:837-0` is not relevant to Umatilla at all. Its 2024 anchoring is 0.13797 TWh in every setting (so it never moves the factor), and its load is on Portland General only. `bi:852-0` reaches Umatilla only through the factor, in two classes (a start in 2024, counting 0.03266 TWh in the anchoring, or any other setting, counting none). So the 1,944 histories hold only 6 distinct Umatilla load paths: 2 factor values x 2 assignment states as built, and 2 assignment states with no anchoring.

The reference configuration reproduces the inventory as built for Umatilla except for the factor. In every year the enumeration's reference load is 0.988164 of `assignment.matrices` as built, which is the ratio of the recomputed factor (0.412500) to the frozen one (0.417440, `state_anchor.parquet` through `inp.frozen_factor`).

**Scope (i) verdict on coverage: complete.** Every admissible setting of every question of the two sites, ruling 4's three cases and both readings are enumerated, with the factor recomputed in each, for both utilities.

**Scope (ii) verdict on coverage: not complete.** Questions relevant to the utility (`_State.relevance`, the place test's set at screen shift 0) that the enumeration holds:

Umatilla (19325:OR), every one held at the reference:

| Site, question | Reference | Admissible settings (place test) |
|---|---|---|
| `bi:819-0` date (open below) | 2022 | 1999 to 2022 (24; 1999 stands for every start up to 1999) |
| `bi:846-0` date (open below) | 2022 | 1999 to 2022 (24) |
| `bi:822-0` date (open below) | 2019 | 1999 to 2019 (21) |
| `bi:823-0` date (open below) | 2019 | 1999 to 2019 (21) |
| `bi:820-0` date | 2019 | 2018, 2019 |
| `bi:848-0` date | 2018 | 2012 to 2018 (7) |
| `bi:817-0` date | 2018 | 2012 to 2018 (7) |
| generic screen shift | 0 | 0, 3, 5 years earlier for `bi:847-0`, `bi:853-0`, `bi:818-0`, `bi:816-0` (energized 2023, 2024, 2023, 2020 in `facilities.parquet`) |

`bi:848-0`'s assignment (on Umatilla, on 14354:OR, off the panel) is varied only through ruling 4's cases, but its two classes for Umatilla (on it; not on it) are both reached, so it leaves no gap. The product of the merged classes is 24 x 24 x 2 x 21 x 21 x 2 x 7 x 7 x 2 = 99,574,272 per screen case, the place test's count (`timing_place_test.json`). The 903,168 per screen case in the plan's record of the looser Oregon reading is the same product with `bi:822-0` and `bi:823-0` bounded not before 2018 (two settings each): 24 x 24 x 2 x 2 x 2 x 2 x 7 x 7 x 2.

Portland General (15248:OR), held at the reference: `bi:832-0` date (2022 of 2021, 2022), `bi:833-0` date (2015 of 2015 to 2019), and the generic screen shift for `bi:839-0`. Its place-test count is 2,430 per screen case.

## 4. The argument with no enumeration (route B)

Method (`common_dose_rule.load_extremes`, `bounds_argument`). The load on a utility is additive over sites (`_State.grid` sums each site's load), and each site's setting is its own, so the least (greatest) load in a year over every combination of settings is the sum over sites of each site's least (greatest) load on the utility over its admitted settings, a site not on the utility contributing zero. The factor is the only quantity shared across sites. It is bounded first by its clip limits, 0.2 to 3.0 (`pass_c_expand.SCALE_LO`, `SCALE_HI`), which needs no property of the factor; and second, only where the clip limits leave a year open, by its value at the greatest and least anchoring totals (it falls as either total rises), widened by the snap tolerance. Each year is then decided if its greatest load share is zero (capped value zero in every history) or its least is at or above the cap (capped value the cap in every history). A lower bound within one part in 10^9 of the cap is not taken as deciding the year. Shares are in points of the 2009 to 2011 base (`inp.base`, from `utility_year_dose.parquet` `base_retail_gwh` and `panel_quantities.parquet`): Umatilla 910.7837 GWh, so 25 points is 227.70 GWh and 50 points 455.39 GWh; Portland General 19,138.23 GWh.

### Umatilla, scope (i)

Settings admitted: every setting of the two sites' questions; `bi:848-0` on Umatilla or off the panel; every other question at the reference. Nothing on Umatilla is measured; every site on it is permit-based.

Step 1, the before years. The greatest raw permit load on Umatilla in each of 2008, 2009 and 2010 over every admitted setting is 0 MW: the earliest start of any site on Umatilla at its admitted settings is after 2010 (the reference starts are 2022 for `bi:819-0` and `bi:846-0`, 2019 for `bi:820-0`, `bi:822-0` and `bi:823-0`, 2018 for `bi:848-0` and `bi:817-0`; the reference load on Umatilla is first positive in 2013), and the varied questions put no load on Umatilla. Zero load times any factor is zero, in both readings. So the capped share is 0 in each before year in every history. Holds.

Step 2, the after years. The least raw permit load on Umatilla is 927.48 MW in 2023, 1,193.67 MW in 2024 and 1,371.42 MW in 2025 (with `bi:848-0` off the panel). At the factor's lower clip limit of 0.2, the as-built share is at least 178.41, 229.62 and 263.81 points; with no anchoring (raw load) it is higher. Each is above 50, so the capped share is the cap in each after year in every history, at either cap. Holds with the clip limits alone. (With the factor bounded at its anchoring totals, 0.41250 to 0.41344, the least shares are 367.97, 473.58 and 544.11 points, which equal the per-year minima of the 1,944 enumerated histories.)

So the capped change is 25 - 0 = 25.0 points at the 25-point cap and 50.0 at the 50-point cap in every scope (i) history. This agrees with the enumeration and does not depend on it.

### Umatilla, scope (ii)

Settings admitted: every setting of every question in Oregon's enumeration at screen shift 0.

Step 1 fails in each of 2008, 2009 and 2010. The greatest raw permit load on Umatilla in each before year is 527.13 MW, from the four open-below rows at their earliest settings: `bi:819-0` 132.54 MW, `bi:846-0` 132.76 MW, `bi:822-0` 130.91 MW, `bi:823-0` 130.91 MW. The least is 0 MW. So the before-year share runs from 0 to 506.99 points (with the factor bounded at its anchoring totals; 1,520.98 at the clip limit), neither zero in every history nor at the cap in every history, 25 (or 50) points short at its least.

That is a failure of the bound, and a direct check shows the change is in fact not common. One single configuration, `bi:819-0` starting in 1999 (an admissible setting in the place test; under the three-year ramp, full load from 2001) with every other question at the reference, gives Umatilla 52.6 points in each before year as built (above both caps), so its capped change is 0.0 at both caps in both readings, against 25.0 and 50.0 at the reference. The same holds for `bi:846-0`, `bi:822-0` or `bi:823-0` started in 1999 (0.0 at both caps). `bi:820-0` at 2018, `bi:848-0` at 2012 and `bi:817-0` at 2012 each still give 25.0 and 50.0. Starts in 2009 or 2010 for an open-below row give partial ramp load in the before years and so changes between 0 and the cap (the agent's reading of the ramp; not evaluated).

Step 2 holds in scope (ii) as well: the least after-year load is the same as in scope (i) (927.48, 1,193.67 and 1,371.42 MW raw; the held date questions all reach full load by 2023 at their latest settings except `bi:819-0` and `bi:846-0`, already counted at two thirds in 2023). The generic screen's shifts of 3 and 5 years move the four screened rows' starts to no earlier than 2015, so they add no before-year load; they add after-year load and change the factor only within its clip limits. They were not evaluated as configurations; they cannot rescue step 1.

### Portland General, both scopes

The 1,944 enumerated histories already differ: 18.780 to 22.746 points at the 25-point cap, 18.780 to 27.261 at the 50-point cap, 18.780 to 27.261 uncapped. Histories that differ cannot be made common by adding histories, so no completeness question arises and the verdict is the same in both scopes. The bound fails as expected: Portland General carries 5.245 MW raw in each before year (`bi:828-0`, at the reference in every setting), 0.099 to 0.240 points, and its after-year shares (least 11.72, 22.09 and 22.79 points with the factor bounded at its anchoring totals) are below 25 in some histories and above it in others. The two scope (ii) witnesses (`bi:832-0` at 2021, `bi:833-0` at 2015) widen the capped range to 18.780 to 22.895.

## 5. Verdicts

| Utility | Form | Scope (i), rule 8.1's text | Scope (ii), place test's wider set |
|---|---|---|---|
| Umatilla (19325:OR) | capped at 25 points | established, 25.0 (enumeration complete; bounds argument holds independently) | not established; not common (0.0 in an admissible history, 25.0 at the reference) |
| Umatilla (19325:OR) | capped at 50 points | established, 50.0 (as above) | not established; not common (0.0 and 50.0) |
| Umatilla (19325:OR) | uncapped | not established (the exception is for a capped form; the histories give 461.89 to 1,244.32) | not established (461.34 to 1,244.32 in the histories evaluated) |
| Portland General (15248:OR) | capped at 25 points | not established; not common (18.780 to 22.746) | not established; not common (18.780 to 22.895) |
| Portland General (15248:OR) | capped at 50 points | not established; not common (18.780 to 27.261) | not established; not common (18.780 to 27.410) |
| Portland General (15248:OR) | uncapped | not established (18.780 to 27.261) | not established (18.780 to 27.410) |

What remains unestablished. In scope (i), nothing remains for Umatilla's capped forms. Completeness is shown setting by setting and the common change is also proved without the enumeration. In scope (ii), Umatilla's capped change is not merely unestablished; it is shown not to be common, by single admissible configurations, so the gap is not one more enumeration could close. The before-period load of the four open-below rows (`bi:819-0`, `bi:846-0`, `bi:822-0`, `bi:823-0`, each admissible from 1999) can put Umatilla's share in 2008 to 2010 anywhere from 0 to above either cap. Portland General has no common change in either scope.

The answer therefore differs by scope, and the scope is Joe's to decide. Under scope (i) the exception would apply to Umatilla's two capped forms at 25.0 and 50.0, and Umatilla would get exactly the treatment of every other utility plus its load-unknown sites' histories. Under scope (ii) Umatilla stays excluded from every run on single doses, and it would be the only utility whose dose range is judged over date questions that rule 8.1 holds at their conventions for everyone else.

## 6. Things to keep apart, and what this note does not do

Analysis eligibility and simulation access. This note concerns only whether Umatilla's capped change is established for the second number's runs on single doses. It changes nothing in the simulation, which reads doses as assigned and leaves out every utility a load-unknown site reaches (`power_simulation.run_second_number`; plan, "A limitation, stated").

The class under rule 8.2 is a separate matter. The design file classes Umatilla "settled" on its scope (i) range at 25 points; a scope (ii) range would be 0 to 25 and not settled. Not decided here.

`second_number.common_dose` as first built required a common change at every cap including the uncapped one, which kept Umatilla out of every run. Joe's rule judges each capped form on its own and never the uncapped form; `common_dose_rule.apply_rule` does that. The file `second_number.py` is being edited by another agent; this note's code imports only `unknown_load_histories`, `oregon_state`, `cap_label`, `CAPS` and `change` from it.

## 7. Uncertainties, said plainly

I am uncertain whether the correction entries in force are the right source of "the site's admissible interval" for the two sites; the note takes them to be, as the enumeration does. The representation of every start at or before 1999 by 1999, and of every start after 2025 by 2026, rests on the three-year linear ramp in `buildout.ramp_mw`; under that ramp they give identical histories in every panel year and in the 2024 anchoring. The statement that starts in 2009 or 2010 give intermediate changes is the agent's reading of the ramp and was not evaluated. The scope (ii) witnesses were evaluated at screen shift 0 only. The scope (ii) count of 99,574,272 counts merged classes, not raw settings; the witnesses do not depend on it.

## 8. Note added 2026-11-19, after Joe's ruling (D-107)

Joe ruled on 2026-11-19 (D-107): "Keep Umatilla excluded from the common-dose exception: the wider admissible histories contain a counterexample. Do not narrow those histories to obtain settled status." The scope is therefore no longer open, and section 5's last paragraph is superseded by the ruling: the exception is judged on scope (ii), the place test's wider set, and Umatilla stays excluded from every run on single doses at every form. Portland General was not established under either scope and stays excluded too.

What this note found is kept as found. Under scope (i) Umatilla's capped change is common, 25.0 and 50.0 points, and that verdict is recorded in `second_number_design.json` beside the ruled one (`common_dose_finding.verdicts_by_scope` and, inside each `mapping_applied` entry, "recorded beside it, not applied"). It is not applied. The code applies the ruled scope only (`common_dose_rule.RULED_SCOPE`, `established_as_ruled`), and `second_number.design_summary` refuses any other mapping in words. No class count or leverage share of the summary moved when it was regenerated; only strings changed.

His clarification of the same day adds that "settled" is conditional on rule 8.1's modeled histories with dates held at their conventions. The session's suggested wording, his to change, is carried in the summary's definitions (`settled_is_conditional`): a settled utility is settled within those histories, and its dose was not tested against the admissible range of any site's date. In the adopted classification Umatilla and Portland General are class 1 (no single dose) at every form in the regenerated summary, so section 6's remark about a "settled" class for Umatilla describes an earlier state of the design file and no longer applies.
