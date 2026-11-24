# The older size-band simulation, identified and labelled (2026-11-19, session 23, job 4)

Written by a read-and-report agent of session 23 (model `claude-opus-5-5`) under Joe's ruling of 2026-11-19 (D-111), item 4, in his words: "Older size-band simulation: identify which stored figures or claims use the construction that admits the 16 units excluded by the implemented ownership rule. Label those as belonging to that older construction, not as validation of the current side run. State the scope of the mismatch without implying that it invalidates the headline validation. No simulation rerun is authorized by this item."

What was done. Code was read; no simulation, no `main` and no test was run. Stored simulation records were read by their keys, labels and settings: `data/frozen/power_simulation.json`, `data/frozen/superseded/design-before-stop3/` (its README and its three files), the two step E stage files, and the earlier versions of `data/frozen/power_simulation.json` in git history (`git show <commit>:<that path>`, saved under the session's scratch folder). Those files hold simulation results on never-host utilities and made-up prices; no host price is in them, and no outcome file was opened. One pure function was called (`design._sha` on the six rule variants, to match the stage files' recorded rules hash). The ledger was not opened; D-31, D-32, D-39, D-52 and D-110 section 10 were read from the excerpts the session cut. Nothing in `pipeline/`, `tests/`, `data/` or the plan was edited. This file is the only file written.

No host utility's price in the outcome data has been read; one lapse in source access is disclosed in the plan and qualifies that statement. The plan is a DRAFT, not frozen.

## The answer in brief

- The simulation's size-band form is built in one place, the `size_band` branch of `power_simulation.build_blocks`, and that branch never uses the `excluded` argument. No ownership exclusion reaches a size-band block on any call path in the code as it stands.
- Only one stored run ever used the size-band form: the simulation under D-31 whose results are D-32 (seed 20261112, committed at `7e9f21c` and reproduced number for number at `1dc64ba`, both 2026-11-12). Its file has since been overwritten and survives in git history only. No file now under `data/frozen` or `data/frozen/superseded` holds a size-band result.
- In that run the ten-closest form applied no ownership exclusion either. The `excluded` argument was added to `build_blocks` on 2026-11-15 (`8ddaee2`) and the `Exclusions` class on 2026-11-18 (`a715f0f`), after the run. So the D-31 and D-32 comparison of the two forms was between two forms neither of which applied the ownership rules, on the main set of that date (25 hosts in the panel at 2%), with a simpler specification than the plan's.
- The "16 units" are a count for the headline set as it stands (seven hosts), made by the size-band equivalence test's literal reconstruction of the coded blocks. They are not a figure from any stored simulation run, and the corresponding count for D-32's sets was never made.
- The selected inference procedure was compared (stage 1) and validated (stage 2) on the matched headline design, the ten closest in size, built with the ownership rules applied before matching. That was confirmed from the code and from both stage records. **One part of the handover's proposed scope sentence could not be confirmed as written.** Stage 1 and stage 2 used no stand-ins. They ran on made-up prices over the real hosts and their real matched comparison utilities, and the ownership rules reached that design through `design.build` (`ownership.ineligible_for`), not through `Exclusions`. `Exclusions` applies to stand-ins in the step E power and range-width simulation (the current `power_simulation.json`), which ran in the matched form. The scope paragraph below says each of these separately.

## Part 1. What the code and the records show

Line numbers are of the working tree on 2026-11-19. `pipeline/analysis/size_band_run.py` was being edited by another agent of this session while this was written, so it is cited by function name only.

### (a) Where the size-band form is built

`pipeline/analysis/power_simulation.py`:

- `SIZE_FORMS = ("none", "size_band", "nearest_in_size")`, line 117; `SIZE_BANDS = (10_000, 100_000)`, line 115; `size_band()`, line 158; each stack's band `Stack.band`, line 314 (residential customers in the cohort's reference year).
- `build_blocks`, lines 375 to 422. The size-band form is the final `else` branch, lines 413 to 414: `cell = np.array([f"{r}|{b}" for r, b in zip(s.region, s.band)])`. Lines 415 to 421 then form, for each cohort, one block per cell holding every stand-in of that cohort in the cell (`tr`) and every unit of the cohort's stack in the cell that is not a stand-in anywhere in the draw (`comp`, with `ok = ~pseudo[s.unit]`, line 395). The `none` and `same_state` forms share this branch with a different cell (lines 409 to 412).

This is the code. The same branch, with the same lines of logic, is in the version that ran under D-31 (`git show 7e9f21c:.../power_simulation.py`, `build_blocks` at its line 237).

### (b) Whether any ownership exclusion reaches it in a draw

It does not. This is read from the code, not inferred.

- `build_blocks`' docstring, lines 380 to 382: "`excluded(cohort, host_row)`, optional, gives the rows of that cohort's stack that may not be that host's comparisons ... In the nearest_in_size form they leave the pool before the nearest MATCH_K are taken ... The other forms do not use it." The code agrees. `excluded` is read only inside the `nearest_in_size` branch, lines 399 to 402. The size-band branch, lines 413 to 421, never reads it. So even a caller that passes `Exclusions` gets size-band blocks with no ownership exclusion.

Every call path to `build_blocks` (searched over `pipeline/analysis/*.py` and `tests/*.py` by name):

| Caller | Lines | Form it passes | `excluded` passed | Ownership exclusion in a size-band block |
|---|---|---|---|---|
| `run_event_study` (the D-31 three-form runner) | 585 to 661; call at 621 | each of `SIZE_FORMS` (default `forms=SIZE_FORMS`, line 587) | none | none. This is the only caller that ever passes `size_band`. |
| `_host_chunk`, from `run_new_hosts` | 1580 to 1598, call at 1590; `run_new_hosts` 1601, `Exclusions` built at 1626 | `c["form"]`, default `"nearest_in_size"` (line 1603) | `Exclusions` under the headline rules | not reached: `main` never passes `size_band` (below); if it did, the branch would ignore `Exclusions` |
| `_size_chunk`, from `run_size_check` | 1694 to 1710, call at 1705; `run_size_check` 1713, `Exclusions` at 1737 | `c["form"]`, default `"nearest_in_size"` (line 1714) | `Exclusions` | not reached, as above |
| `_shortcut_chunk`, from `run_added` | 1948 to 1971, call at 1956; `Exclusions` at 2006 | `"nearest_in_size"`, fixed | `Exclusions` | not reached |
| `main` | 2024 to 2096 | `run_new_hosts` at 2080 and `run_size_check` at 2085 with no `form`, so `nearest_in_size`; the own-state side run at 2090 to 2091 with `form="same_state"` | `Exclusions` through `rk` | no size-band run at all |
| `inference_comparison.py` (`main` 892 to 923, `real_design` 874 to 889, `build_context` 233 to 286) | | does not call `build_blocks` | | builds the real design with `design.build_with_rules` under `ps.HEADLINE_RULES` and takes its blocks from `Design.blocks()` through `inference_check.fixed_parts` (line 250) |
| `inference_check.py` (`main` 438 to 471; `fixed_parts` 100 to 110) | | does not call `build_blocks` | | `design.build_with_rules` at line 461; blocks from `d.blocks()` at line 107 |

`run_event_study` and `choose_size_form` (lines 664 to 679) are called by nothing in `pipeline/analysis` now; `main` and `run_added` do not call them. They survive as the code of the D-31 run. Tests call `build_blocks` with `"size_band"` and `choose_size_form` on invented inputs only (`tests/test_power_simulation.py`, lines 220, 238 and 394 to 400).

What the mismatch means inside a draw, as far as the code shows. A draw replaces each real host with a stand-in drawn from never-host units (`pick_stand_ins`, lines 324 to 372). In the size-band form the stand-in's block is every non-stand-in unit of its cohort's stack in its region-and-band cell. Applied to that stand-in as a host, the rules the side run applies (through `design.build_with_rules` and `ownership.ineligible_for`; in the simulation, `Exclusions.__call__`, lines 1491 to 1503, whose docstring, lines 1479 to 1484, says "the rules are applied to it as a host") would remove from it: a unit of the stand-in's own utility (the same EIA id, in another state); with the ownership table, a same-parent affiliate in any year of its window; and, if the stand-in is investor-owned, an investor-owned candidate with no ownership row (rule 2.2, read year by year in `ownership.py` since 2026-11-19). The size-band block keeps all of these. Where several stand-ins of one cohort share a cell, the block is pooled, so a unit excluded for one stand-in and eligible for another stays in for both; the code has no rule for that case. How many units this admits in any draw depends on which stand-ins are drawn. It was never counted for any stored run.

"The 16 units" (Arizona Public Service 3, PacifiCorp in Utah 5, Public Service of New Mexico 3, Sierra Pacific 5; 1,050 stacked rows against 890) come from `docs/gate1/size-band-equivalence-2026-11-19.md`. Its agent built `pooled_simulation_literal` in `tests/size_band_pooled_form.py`, a reconstruction of the coded size-band blocks applied to the seven real headline hosts as hosts. The count is a property of the construction on the headline set as it stands. It is not a stand-in draw and not a stored simulation figure. This agent confirmed the code reason (the branch ignores `excluded`) and did not recount the 16.

### (c) Which stored runs used the size-band form

Read by key and label. Values were read only where needed to match a figure quoted elsewhere.

| Record | Size-band result in it? | What it holds |
|---|---|---|
| `data/frozen/power_simulation.json` (step E, under procedure C; committed `ec34007`, 2026-11-18) | No | `new_host_estimate/*/*/comparison_form` is `nearest_in_size` in every entry; `side_runs/*/comparison_form` is `same_state`; `rules.ownership` is `table`; no `size_adjustment` key |
| `data/frozen/superseded/design-before-stop3/power_simulation.json` | No | the same keys and forms, on the design before Stop 3 |
| `data/frozen/superseded/design-before-stop3/inference_comparison_stage1.json`, `inference_validation_stage2.json` | No | step E on the design before Stop 3 (README: 7 hosts with Umatilla, 770 rows, 28 regressors) |
| `data/frozen/inference_comparison_stage1.json`, `inference_validation_stage2.json` | No | see (d) |
| `power_simulation.json` at `7e9f21c` (the D-31 run, D-32) | **Yes** | `new_host_estimate/{2%,5%}/{main_set,every_cohort_utility}/size_adjustment/{none,size_band,nearest_in_size}` and `size_adjustment_chosen` for each; `standard`: "docs/DECISIONS.md, D-31, committed before this was run."; seed 20261112 |
| `power_simulation.json` at `1dc64ba` (the same run reproduced from the committed code) | **Yes** | `new_host_estimate` identical to `7e9f21c`; only `per_point_of_load` differs |
| `power_simulation.json` at `31677ef` (D-24), `03cd067` (D-39), `9de14bb` (D-52), `cc02b62` (step E before Stop 3) | No | D-24 has no size form (a stand-in pool sensitivity, `twenty_closest_in_size`); the others record `comparison_form` `nearest_in_size` or `same_state` only |

The three-form loop and `size_adjustment_chosen` were added to the code at `9cd80b7` and removed at `c7bba8c`, both 2026-11-12 (D-38's standard). So the D-31 run is the only run of the size-band form.

What the D-31 run's record says, by form, at 2% (values from `7e9f21c`):

| | none | size band | ten closest |
|---|---|---|---|
| Main set, 25 hosts in the panel: mean with nothing planted | -1.536 | -1.647 | -1.283 |
| half-width of the range | 3.607 | 3.551 | 3.342 |
| range covers zero | 0.891 | 0.862 | 0.892 |
| smallest effect detected in 80% of draws | 6.544 | 6.589 | 6.099 |
| planted 5%, range excludes zero from above | 0.452 | 0.447 | 0.574 |
| rule's choice | | eligible | **chosen** (`abs_drift_pct` 1.647 and 1.283) |
| Every cohort utility, 47 hosts: mean with nothing planted | -1.023 | -0.895 | -0.461 |
| half-width | 2.741 | 2.737 | 2.654 |
| range covers zero | 0.913 | 0.925 | 0.956 |
| smallest effect | 4.767 | 4.684 | 4.183 |
| rule's choice | | **chosen** (the only eligible form) | not eligible (covers zero 95.6%) |

At 5%: main set half-widths 3.801, 3.795, 3.646 and smallest effects 6.645, 6.766, 6.173; every cohort utility half-widths 2.931, 2.939, 2.852 and smallest effects 4.324, 4.451, 4.088. The rule chose the ten closest on both sets at 5%. D-31 applies the rule to the main set at 2% and uses its pick everywhere.

### (d) What the selected procedure was compared and validated on

From `inference_comparison.py` and both stage records:

- **The design form is the matched one, the ten closest in size.** `real_design` (lines 874 to 889) builds `design.build_with_rules(..., ps.HEADLINE_RULES, ownership=ownership, ...)` on `design.split(0.02, ps.HEADLINE_SET, ...)`. `design.build` (design.py lines 79 to 156) takes each host's `k = ps.MATCH_K` nearest in size (line 150; `MATCH_K = 10`, power_simulation.py line 116), and `Design.blocks()` (design.py lines 54 to 56) gives one block per host, the host and its matched set. `build_context` assembles exactly those blocks (`ic.fixed_parts`, inference_check.py lines 100 to 110). Stage 1 records `design_quantities` of 49 units, 19 clusters, 770 rows and 26 regressors. 770 is seven hosts, each with ten comparison utilities, over ten years. A size-band design on this set stacks 890 rows (size-band equivalence file).
- **The design is the headline design on record.** Both stage files carry the same comparison fingerprint, `fd914a7b...`, with component `design_inputs` `b8515c35cba1...`, the headline design-inputs hash on record (handover section 1), and component `rules` `62651481...`. `design._sha` over the six rule variants gives that value for `headline` only (`ownership` "table", `usable` "flag", `support` "applied", gas-share control, unresolved ownership "kept"). Stage 1 selected candidate C. Stage 2 validated C alone on 20,000 datasets a process, and `power_simulation.json`'s `procedure.stage2_verdicts` records both rates as "passed".
- **The ownership rules reached that design before matching, through `design.build`, not through `Exclusions`.** With the ownership table, a host's pool loses every candidate `ownership.ineligible_for` names before the ten nearest are taken (design.py lines 144 to 150; `build_with_rules` passes the table at lines 251 to 252; `Rules.ownership` defaults to "table", power_simulation.py lines 826 and 848). Stage 1 and stage 2 draw made-up prices for the real design's units (`draw`, `dataset`, lines 307 to 342). **No stand-in is drawn, and `Exclusions` is not called.** The code that wrote both files is unchanged since the commit that holds them (`ec34007`; `git diff --stat` empty for `inference_comparison.py` and `inference_check.py`). At that commit `design.build` already applied `ineligible_for` before matching.
- **Where `Exclusions` is applied to stand-ins.** In the step E power and range-width simulation under the selected procedure (the current `power_simulation.json`). `run_new_hosts` builds `Exclusions` whenever `rules.ownership` is not "off" (line 1626), and the matched form removes the excluded rows before the ten nearest are taken (lines 396 to 407). That record has `rules.ownership` "table" and `comparison_form` `nearest_in_size`. The same lines are in the code at `ec34007`, which wrote it.
- The design has not moved since. D-108 records that the headline designs are identical at 2% and 5% after the ownership repair, and the handover gives the same hash.

## Part 2. Stored figures and claims, and whether each rests on the size-band construction

"The D-31 run" is the run of seed 20261112 at `7e9f21c` (reproduced at `1dc64ba`). "In part" means the figure or claim takes a value or a conclusion from the size-band form of that run beside the other forms.

| # | File | Place (line) | Figure or claim, quoted exactly | Stored run | Rests on the size-band form? |
|---|---|---|---|---|---|
| 1 | `PREANALYSIS.md` | Electricity: the main estimate, "- **Size adjustment (D-26).**" (line 80) | "Two forms were simulated on never-host utilities and one adopted by the rule in D-31: size band by region by year (under 10,000 customers; 10,000 to 99,999; 100,000 or more), or matching each host to the ten comparison utilities in its region closest to it in size. **Adopted: the ten closest in size (D-32).**" | the D-31 run | **In part.** The adoption compares the two forms' simulated drifts (1.283 against 1.647); the size-band side of that comparison is the older construction. The sentence was added in the D-32 commit (`7e9f21c`). |
| 2 | `PREANALYSIS.md` | same bullet, "Two other pooled constructions are not the same design" (line 80) | "the simulation's blocks as coded, which apply no ownership exclusion and admit 16 units the rules exclude" | none (the equivalence test's construction on the headline set) | No. It states the mismatch; it is not a figure from the older run. |
| 3 | `PREANALYSIS.md` | same bullet, last sentences (line 80) | "A size adjustment addresses one observed warning (hosts are larger than the typical comparison utility and such utilities did not track their region's average)." | none | No. It was added at `9cd80b7`, before the D-31 run was made. |
| 4 | `PREANALYSIS.md` | Inference, "*The simulation's readings with nothing planted*" and its table (lines 106 to 116) | the seven rows, e.g. "Headline, 2% (7) \| -0.15% \| 3.07% \| 6.65% \| 95.0% \| 3.3%" | current `power_simulation.json` | No. The record has `comparison_form` `nearest_in_size` (and `same_state` for the two side-run rows), `rules.ownership` "table". |
| 5 | `PREANALYSIS.md` | Inference, "*On the design as it stands.*" and the stage 1, stage 2 and rerun-rule bullets (lines 96 to 101) and "*Where the validation does not transfer*" (line 105) | e.g. "Both runs selected candidate (C), CR2 with Satterthwaite degrees of freedom, and the selected procedure passed validation on both rates" | the two stage files | No. They are on the matched design (Part 1 (d)). |
| 6 | `PREANALYSIS.md` | Reported checks (lines 198 to 207) | no sentence names the size-band form or the D-31 comparison | | No. |
| 7 | `PREANALYSIS.md` | Other runs, "**Comparison utilities from the host's own state only.**" (line 176) | "With nothing to find, the simulation's estimate moved by about two and a half points between this and the market-region comparison (D-32)" | the D-31 run (its added own-state run) | No. D-32 gives this as "minus 1.5 against the region, plus 1.0 against the state". -1.5 is the whole-region form (-1.536); the size-band form's -1.647 would round to -1.6. I am fairly confident of this match but it is read from rounding, not from a label. |
| 8 | `PREANALYSIS.md` | Required before the freeze, item 3 (line 352) | "on the headline set at 2% the form as built and the pooled form are the same design" | none (equivalence test) | No. Its "pooled form" is the test's construction with each host's ownership exclusions kept, not the simulation's. |
| 9 | `HANDOVER.md` | "What exists" table, row "Power simulation, rerun on the sets job V leaves" (line 96) | "The D-22 and D-31 runs are superseded and in the git history" | the D-31 run | No figure. It points to the run that holds the size-band results and calls it superseded, which is accurate. No label needed. |
| 10 | `HANDOVER.md` | Next jobs, item 4 (line 618) | "Joe ruled (D-26); session 5 rebuilt it and reran it (D-31, D-32)." | the D-31 run | No figure, history only. No label needed. |
| 11 | `HANDOVER.md` | line 217 | "**The size-band form** is the pooled form on the headline set by test" | none | No (as item 8). |
| 12 | `docs/gate1/GATE1_REPORT.md` | whole file | its simulation figures are D-52's (line 83), matched form; line 92 says "no package can restrict to the ten closest in size" | D-52 run | No. |
| 13 | `docs/gate1/step-f-draft-2026-11-18.md` | 4.8 Size adjustment (line 232) | "**Adopted: the ten closest in size (D-32).** ..." | the D-31 run (by quotation of the plan) | In part, as item 1. A record of its date. |
| 14 | `docs/gate1/referee-read-2026-11-19.md` | line 94 | "it cites D-32 for a gap of "about two and a half points" between own-state and regional comparisons" | the D-31 run | No (as item 7). |
| 15 | `docs/gate1/step-e-rules-2026-11-18.md` | line 102 | "size band from 2010 ... size band from 2005" | none | No. These are the second number's region-by-band cells, a separate construction (`run_second_number`, `second_number.py`) that never calls `build_blocks`. |
| 16 | Ledger D-31 | "**The size adjustment, and the rule that picks one.**" | "Three forms are run on every draw: none; size band by region by year (under 10,000 residential customers, 10,000 to 99,999, 100,000 or more); and the ten comparison utilities in the region closest in size. ... The rule is applied to the main set at 2% and the form it picks is used everywhere." | the D-31 run (its standard) | **In part.** It specifies the older construction and the comparison; it carries no figure. |
| 17 | Ledger D-32 | the table, row "Range, size band" | "plus or minus 3.6% \| plus or minus 2.7%" | the D-31 run | **Yes** (3.551 and 2.737). |
| 18 | Ledger D-32 | the table, row "Range covers zero (nominal 90%)" | "86% to 89% \| 91% to 96%" | the D-31 run | **In part.** The 86% is the size-band form's (0.862); 92.5% lies inside the second range. |
| 19 | Ledger D-32 | the table, row "Mean estimate with nothing planted" | "-1.3% to -1.6% \| -0.5% to -1.0%" | the D-31 run | **In part.** -1.6% is the size-band form's (-1.647); -0.895 lies inside the second range. |
| 20 | Ledger D-32 | the table, row "Smallest effect whose range excludes zero in 80% of draws" | "6.1% to 6.6% \| 4.2% to 4.8%" | the D-31 run | **In part.** 6.6% is the size-band form's (6.589); 4.684 lies inside the second range. |
| 21 | Ledger D-32 | the table, row "Planted 5%: range excludes zero" | "45% to 57% of draws \| 83% to 92%" | the D-31 run | **In part.** The size-band form gives 44.7% and the whole-region form 45.2%, both rounding to 45%; 84.8% lies inside the second range. |
| 22 | Ledger D-32 | paragraph under the table, "At the 5% threshold" | "plus or minus 3.6% to 3.8% for the main set (21 hosts in the panel) and plus or minus 2.9% for every cohort utility (39), with smallest detectable effects of 6.2% to 6.8% and 4.1% to 4.5%" | the D-31 run | **In part.** 3.8% is the size-band (3.795) and whole-region (3.801) forms'; 6.8% and 4.5% are the size-band form's (6.766, 4.451); 2.9% includes it (2.939). |
| 23 | Ledger D-32 | "**What will be said, as D-31 wrote it.**" | "The wider set's range is about a fifth narrower (2.7 against 3.3 to 3.6)" | the D-31 run | **In part.** 3.6 is the whole-region and size-band forms' (3.607, 3.551). |
| 24 | Ledger D-32 | "**The size adjustment the rule adopts: the ten comparison utilities closest in size.**" | "On the main set at 2% both forms were eligible and matching had the smaller drift (1.28 against 1.65)." | the D-31 run | **In part.** 1.65 is the size-band form's drift. |
| 25 | Ledger D-32 | same paragraph | "On the wider set matching's range covers zero 95.6% of the time, a shade outside the band, which the rule would have made ineligible there; the rule is applied on the main set, as written." | the D-31 run | **In part.** The record shows the rule's choice on that set was the size-band form (`size_adjustment_chosen.chosen` = `size_band`, the only eligible form), which the sentence does not say. |
| 26 | Ledger D-32 | "**The combined pre-period test is not calibrated yet.**" | "19.4 on the main set (ten nearest in size) and 8.0 on the wider set" | the D-31 run | No. These are the matched form's (19.42 and 7.95). |
| 27 | Ledger D-32 | "**The drift, and what it can and cannot show.**" | "in-state lookalikes of the hosts ran 1.3 to 1.6 points below their market region's comparison utilities over these windows" | the D-31 run | **In part.** The range spans the forms; 1.6 is the size-band form's. |
| 28 | Ledger D-39 | "**The drift with nothing planted is now small.**" and "**Against D-32.**" | "against minus 1.3 in D-32"; "Main set: plus or minus 3.3% with 25 hosts then" | the D-31 run | No. These are the matched form's (-1.283, 3.342). |
| 29 | Ledger D-39 | "**The set-asides cost about an eighth of the range.**" | "In D-32 it was a fifth (3.3 against 2.7)." | the D-31 run | No, the agent's reading. D-31 used the rule's pick everywhere, so 2.7 is read as the matched form's 2.654. Every form rounds to 2.7 on that set, so the figure is the same whichever was meant. |
| 30 | Ledger D-52 | whole entry | all figures | D-52 run, matched form | No. |
| 31 | Ledger D-110, section 10 | "**Two things the test also found:**" | "the simulation's blocks as coded apply no ownership exclusion and admit 16 units the rules exclude, so the simulation's form is not the module's design even on the headline set (largest difference in a host's weight 0.0069)" | none | No. It is the finding that identifies the mismatch. |

Nothing in `HANDOVER.md`, `GATE1_REPORT.md` or the step E files under `docs/gate1` gives a size-band figure from the D-31 run. The figures that rest on it are in ledger entry D-32 and, through the adoption sentence, in the plan.

## Part 3. The labels, drafted for the session to apply

Each label says the same four things. The figure or claim belongs to the older size-band construction of the simulation. That construction applied no ownership exclusion in its size-band blocks. It is not a validation of the current size-band side run (`size_band_run.py`). The note is dated 2026-11-19 and cites D-111.

**Which documents get a note.**

- `PREANALYSIS.md` is a current document, the specification. It gets a note beside item 1. Items 2 to 8 need none.
- `HANDOVER.md` is a current document, but no sentence in it carries a figure or a validation claim from the size-band form (items 9 to 11). No note is proposed. The session may add one beside item 9 if it wants the pointer to say what the run holds.
- `docs/gate1/step-f-draft-2026-11-18.md` is a record of its date. It is a draft already applied to the plan, and its quotation is of the plan's sentence. It is left alone, and the label sits where the plan carries the sentence (item 1).
- `docs/gate1/GATE1_REPORT.md`, `referee-read-2026-11-19.md` and `step-e-rules-2026-11-18.md` are records of their date, and none rests on the form. They are left alone.
- The ledger entries are records. Dated notes are drafted to be added under D-31 and D-32, and neither entry is rewritten. D-39, D-52 and D-110 need none.
- The stored records (`power_simulation.json` in git history at `7e9f21c` and `1dc64ba`) are not edited. The labels sit where the plan and the ledger cite them.

**Label 1, the plan.** Place: `PREANALYSIS.md`, the bullet "- **Size adjustment (D-26).**" (line 80), immediately after "**Adopted: the ten closest in size (D-32).**" and before "The set is chosen on the region of the cohort's reference year".

> *Dated note (2026-11-19, D-111).* The simulation that compared the two forms (D-31, D-32; seed 20261112) belongs to the older size-band construction of the simulation (`power_simulation.build_blocks`, form `size_band`), which applied no ownership exclusion in its size-band blocks. Its size-band figures, and the comparison by which the ten closest were adopted over the size band, are not a validation of the current size-band side run (`pipeline/analysis/size_band_run.py`). In that run the ten-closest form applied no ownership exclusion either, since the ownership rules came later, and it was run on the main set of that date, not on the headline set as it stands. No simulation has been rerun.

**Label 2, ledger D-31.** Place: a dated note added at the end of entry D-31, after its last bullet ("**One run, seed 20261112.** ..."). Optional. D-31 specifies the construction and carries no figure, but it is where the rule is stated.

> *Note added 2026-11-19 (D-111).* The size-band form specified here was coded as `power_simulation.build_blocks`, form `size_band`, one block per cohort and cell, and it applied no ownership exclusion; nor did the ten-closest form in this run, since the ownership rules (D-54, D-58) came later. The run under this standard and its size-band figures (D-32) belong to that older construction and are not a validation of the current size-band side run (`size_band_run.py`). This entry is not otherwise changed.

**Label 3, ledger D-32.** Place: a dated note added at the end of entry D-32, after the paragraph "For Joe, none decided here: ...".

> *Note added 2026-11-19 (D-111).* The size-band figures in this entry belong to the older size-band construction of the simulation (`power_simulation.build_blocks`, form `size_band`), which applied no ownership exclusion in its size-band blocks. They are the table's row "Range, size band"; the size-band end or part of the rows "Range covers zero" (86%), "Mean estimate with nothing planted" (-1.6%), "Smallest effect ..." (6.6%) and "Planted 5%" (45%); the 5% paragraph's upper ends (3.8%, 6.8%, 4.5%); "3.3 to 3.6"; "1.28 against 1.65"; and "1.3 to 1.6". They, and the adoption of the ten closest over the size band, are not a validation of the current size-band side run (`size_band_run.py`). In this run the ten-closest form applied no ownership exclusion either; the ownership rules came later. On the wider set at 2% the rule's choice recorded in the run's file was the size band, the only eligible form there, and D-31 applies the rule on the main set. No simulation has been rerun, and the entry is not otherwise changed.

**Label 4, the scope paragraph** goes into the plan as Part 4 gives it. It sits best in the same bullet, after the sentence that names "the simulation's blocks as coded, which apply no ownership exclusion and admit 16 units the rules exclude" (line 80).

## Part 4. The scope statement for the plan

### Paragraph (seven sentences)

> *The older size-band simulation and the scope of its mismatch (Joe, 2026-11-19, D-111).* The simulation's size-band form (`power_simulation.build_blocks`, form `size_band`) puts every stand-in of a cohort and every other never-host unit of that cohort in the same region and size band into one block and applies no ownership exclusion, its `excluded` argument being used by the nearest-in-size form only. It was run once, in the simulation under D-31 whose results are D-32, and its figures there belong to that older construction and are not a validation of the size-band side run as implemented (`size_band_run.py`), which applies the ownership rules for each host; applied to the headline set as it stands, the coded construction would admit 16 units those rules exclude. The mismatch is between those two size-band constructions. The headline design is the ten comparison utilities closest in size, built under the headline rules with the ownership rules applied to each host's pool before the ten are taken, and not the size-band form. The selected procedure was compared (stage 1) and validated (stage 2) on that matched design, on made-up prices over the real hosts and their matched comparison utilities, and both records carry its design-inputs hash and the headline rules. The power and range-width simulation under the selected procedure was run in the matched form, with each stand-in's comparison utilities subject to the ownership rules through `Exclusions`. Whether D-31's rule would have chosen differently between the two forms with the ownership rules applied in the size-band blocks is not known, since no simulation has been rerun; in that run the ten-closest form applied no ownership exclusion either.

### Evidence for each sentence

1. **Construction.** `power_simulation.py` `build_blocks`, lines 375 to 422; size-band cell at lines 413 to 414; blocks at 415 to 421; `excluded` used only at lines 399 to 402 inside the `nearest_in_size` branch; docstring lines 380 to 382 ("The other forms do not use it.").
2. **Run once; the 16 units.** The only caller passing `size_band` is `run_event_study` (line 621, no `excluded`), called by no current entry point. The only stored results with a `size_band` key are `power_simulation.json` at `7e9f21c` and `1dc64ba` (identical `new_host_estimate`, seed 20261112, standard D-31). No file now under `data/frozen` or `data/frozen/superseded` has one. That the side run applies the ownership rules per host is from `size_band_run.build`, which calls `design.build_with_rules` under the headline rules with the support rule reported only (`SIZE_BAND_RULES`), and from the plan's line 80. The 16 units and 1,050 against 890 rows are from `docs/gate1/size-band-equivalence-2026-11-19.md` (`tests/size_band_pooled_form.py`, `pooled_simulation_literal`); this agent did not recount them.
3. **Between the two size-band constructions.** Follows from 1 and 2. No other stored result uses the size-band form (Part 1 (c)).
4. **Headline design is the ten closest, ownership before matching.** `design.build`, lines 142 to 150 (`ownership.ineligible_for` removes candidates from `pool`, then `[:k]` nearest); `k = ps.MATCH_K = 10`; `build_with_rules` lines 251 to 253; `Rules.ownership` default "table" (power_simulation.py lines 826, 848); the plan's "**Adopted: the ten closest in size (D-32).**"
5. **Compared and validated on that design.** `inference_comparison.real_design` (lines 874 to 889: `design.build_with_rules` under `ps.HEADLINE_RULES` on the headline set at 2%); `build_context` (`ic.fixed_parts` on `Design.blocks()`); made-up prices in `draw`/`dataset` (lines 307 to 342), with no stand-in. Stage 1 `design_quantities`: 770 rows, 49 units, 26 regressors, 19 clusters (seven hosts each with ten, over ten years). Both stage files: `fingerprint.of.design_inputs` = `b8515c35cba1...`, `fingerprint.of.rules` = `62651481...` = `design._sha` of the `headline` rules (computed for all six variants; only `headline` matches); stage 2 candidate C; `power_simulation.json` `procedure.stage2_verdicts` "passed" for both. The code is unchanged since `ec34007`.
6. **Step E simulation's stand-ins and `Exclusions`.** `run_new_hosts` line 1626 builds `Exclusions` when `rules.ownership != "off"`; `_host_chunk` line 1590 passes it to `build_blocks`; matched branch lines 396 to 407 removes the excluded rows before the ten nearest; `Exclusions.__call__` lines 1491 to 1503 applies `ownership.ineligible_for` to the stand-in as a host. Record: current `power_simulation.json` `rules.ownership` "table", `new_host_estimate/*/*/comparison_form` `nearest_in_size`. The same lines exist in the code at `ec34007`, the commit that holds the record. The rules are as they stood when it was run, on 2026-11-18, before rule 2.2 was read year by year; D-108 records the headline design unchanged by that repair.
7. **Not known; the old matched form had no exclusion either.** No rerun was made (D-111 authorizes none). `build_blocks` at `7e9f21c` has no `excluded` parameter (its line 237). The parameter was added at `8ddaee2` (2026-11-15) and `Exclusions` at `a715f0f` (2026-11-18).

### What the paragraph does not say, and why

- It does not say the handover's wording "whose stand-ins had the ownership rules applied through `Exclusions`" of the stage 1 and stage 2 design. **That could not be confirmed, because it is not what the code does.** Stage 1 and stage 2 have no stand-ins. The ownership rules reached their design through `design.build`. `Exclusions` is the step E simulation's, and sentences 4 to 6 say each fact where it holds.
- It does not say the mismatch is harmless, and it does not say how much it would move any figure. Nothing was rerun or recounted for D-32's sets.
- It does not say the headline validation is invalid. Nothing found bears on it. The validation's design is the matched design, and no stored result of the size-band form enters stage 1, stage 2 or the step E simulation.

## Other things found, outside this job, reported and not acted on

- **The own-state side run applies no ownership exclusion in its blocks either.** `main` passes `Exclusions` to the own-state side run (lines 2090 to 2091, `form="same_state"`), but the `same_state` branch shares the cell code path with the size-band form and ignores `excluded`, as the docstring says. This is outside Joe's item 4 and is not labelled here. The plan's stand-in table quotes two own-state rows from the current `power_simulation.json`. The agent's reading is that the session may want to say so where that side run is described. No change is proposed here.
- The second number's "size band" (step E rules line 102; `second_number.py`; `inference_check.second_number_leverage`) is a different construction, region-by-band cells in the per-point design. The label here does not apply to it.

## Not confirmed, said plainly

- I am uncertain whether item 7's "minus 1.5 against the region" is the whole-region form. It matches -1.536 by rounding and does not match the size-band form's -1.647, but D-32 does not name the form.
- I am uncertain which form D-39's "2.7" (item 29) refers to. It makes no difference to the figure, since every form rounds to 2.7 on that set.
- The 16 units were not recounted by this agent. The figure stands on the equivalence file's construction.
- I did not establish when the ownership table (`pipeline/analysis/ownership.csv`) was first committed. "The ownership rules came later" rests on the code's dating of `excluded` and `Exclusions` and on the docstrings' citations of D-54 and D-58, both after D-32.
