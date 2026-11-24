# Sensitivity scenario A: reconciling 379 with 380 sites and 120 with 121 units (session 22, 2026-11-19)

Written by a build agent of session 22 for the verification item Joe opened in D-109. Quantity side only. Nothing here reads a dose, a price, a revenue, a bill or an estimate: site assignments, candidate lists, full loads, retail sales (as capacity) and the corrections file only. The inventory's boolean `in_dose` flag is read as a flag, to select load-carrying sites. No rule, tolerance or input was changed, and neither `pipeline/analysis/second_number_scenarios.py` nor `data/frozen/second_number_scenarios.json` was edited. The plan is a DRAFT and not frozen.

His words: "Scenario A: reconcile 379 versus 380 relocated sites and 120 versus 121 affected units using existing permitted records. Identify the site and reason if recoverable. Do not change a rule, tolerance or input to match the earlier count." And: "If the discrepancy comes from an unresolved interpretation of the capacity accounting, bring that specific choice back with a recommendation; do not classify it automatically as a bug or alter the rule to recover the old count."

**Conclusion, form (ii).** The difference turns on one reading of R2's clause "on top of what that candidate already carries": whether the 460 sites being placed count, at the start, as load carried by the unit each is on now. The module counts them (the session's interpretation N-2) and gets 379 sites and 120 units. Counting them only once each is placed, with every other site where the inventory has it, gives exactly 380 and 121. The extra site is `bi:13-0` (Arizona) and the extra unit is WAPA in Arizona (27000:AZ). The reading also changes where 26 other sites in Arizona and Texas go. It is not classed as a bug. The agent's recommendation is in section 5. That the second reading reproduces R2's numbers is consistent with session 20 having used it, and does not establish that it did: no record of that calculation survives (section 1).

## 1. Surviving earlier records

Searched, by text, for the session 20 calculation (the strings 380, 121, "runner-up", "alternative A", "unresolved load-carrying", "carry different load", "assignments alone"):

- `docs/gate1/*.md` and `*.json` other than files starting `availability`. Hits for 380 are site ids such as `bi:380-0` in the expansion-test files; "runner-up" hits are in the inference validation rules (no runner-up validation), which are unrelated.
- `data/frozen/*` (not `water/`). The only file carrying 380 and 121 as counts is `second_number_scenarios.json`, which quotes R2's figures as `r2_counts`.
- `HANDOVER_session20_2026-11-19.md` and `HANDOVER_session21_2026-11-19.md`. Session 20's handover asks for the recommendation and names no counts. Session 21's quotes R2's definitions and the uncertainty about the capacity test's starting load, and no calculation.
- `pipeline/analysis` and `tests`. The only hits are `second_number_scenarios.py`, its test file and `run_outcomes.py`'s registry label, all from session 21.
- The file lists of the commits on this folder from session 20 (`090f667`) onward, by name only (`git log --name-only`; `docs/DECISIONS.md` was filtered from the listing and not opened). Session 20's commit holds no script, scratch output or note for scenario A's count.

The excerpt of the ledger given to this agent (D-106 section 12) says the count was made by an agent of session 20 "from assignments and the correction entries alone" and kept nowhere in the repository. **Nothing permitted survives that shows how 380 and 121 were computed.** What follows reconstructs the difference from the rule's words, not from that calculation.

## 2. The independent check

`tests/scenario_a_independent_check.py` implements R2's rule from its words and from `build_inventory.pick_utilities`, apart from the module. It imports nothing from `second_number_scenarios.py` and calls no function in `pipeline/`. It reads `data/interim/facilities.parquet` (nine columns: site, state, assignment, its status, candidate list, `in_dose`, crypto flag, scaled and unscaled full load) and `data/interim/panel_quantities.parquet` (utility, state, year, total retail sales, balancing authority). The one thing it takes from `pipeline/` is the table of balancing authority codes to regions in `pipeline/electricity/market_region.py`, read as data, to find the ERCOT units that ruling 4's Texas clause needs. Its readings that R2 does not state are listed in its docstring.

It agrees with the module site by site and unit by unit under the module's own stated reading:

| What | Checker | Module | Agree |
|---|---|---|---|
| The 460 sites (unresolved, in the dose, with a state, not crypto) | 460 | 460 | same ids |
| Sites that move, with origin and destination | 379 | 379 | same ids, same origin and destination for each, same processing order |
| Sites that stay because no other candidate fits | 63 | 63 | same ids |
| Sites that stay because they have no other panel candidate | 18 | 18 | same ids |
| Units gaining or losing a site | 120 | 120 | same units |
| Inputs: panel units, capacities, start load, ERCOT units | 1,379 capacities; 125 ERCOT units | same | equal; start load equal to 7.3e-12 GWh |

The module's per-site reasons for staying were read by calling its pure function `runner_up_placement` on its own `placement_inputs` in a scratch run; its moves were read from `second_number_scenarios.json`. The checker's inputs were compared with the module's directly in the same run.

## 3. Variants

Each row is the checker with one reading changed (a named switch in `Reading`), on the real quantity-side inputs. "Units gaining or losing a site" is the unit count the module reports against R2's 121. The other unit columns are plain counting alternatives. Size ties are common (58 of the 460 share a load with another), so the tie rule was tested.

| Variant | Sites moving | Units gaining or losing a site | Units whose placed full load changes | Utility ids (once over states) | Stay: no other panel candidate / none fits |
|---|---|---|---|---|---|
| The module's reading (N-2): every site on a unit at its scaled full load, updated as sites move | 379 | 120 | 116 | 117 | 18 / 63 |
| **The 460 not counted on their current unit at the start; each added where it ends; every other site where the inventory has it** | **380** | **121** | 116 | 117 | 18 / 62 |
| **Nothing carried at the start (pick_utilities' start); each of the 460 added where it ends** | **380** | **121** | 116 | 117 | 18 / 62 |
| Carried as assigned and never updated | 401 | 123 | 119 | 119 | 18 / 41 |
| A moved site not taken off its old unit | 356 | 122 | 118 | 118 | 18 / 86 |
| Carried: sites in the dose only | 379 | 120 | 116 | 117 | 18 / 63 |
| Carried: crypto mines left out | 379 | 120 | 116 | 117 | 18 / 63 |
| Full load unscaled by the state factor, for order and test | 379 | 120 | 116 | 116 | 18 / 63 |
| Unscaled and never updated | 405 | 124 | 120 | 120 | 18 / 37 |
| Strict less-than in the capacity test | 379 | 120 | 116 | 117 | 18 / 63 |
| Ties by the inventory's row order instead of site id | 379 | 120 | 116 | 117 | 18 / 63 |
| The 460 not counted at the start, never updated | 413 | 121 | 117 | 118 | 18 / 29 |
| Nothing at the start, unscaled | 382 | 120 | 116 | 116 | 18 / 60 |
| Other sites at a replay of pick_utilities before the overrides (the agent's approximation, see below); the 460 not counted at the start | 378 | 119 | 114 | 115 | 18 / 64 |
| The same, never updated | 413 | 121 | 117 | 118 | 18 / 29 |

Counting alternatives that change nothing here: no site id appears twice in the inventory or the 460; every one of the 460 is on a panel unit that is among its own stored candidates, so no runner-up can equal the current unit; the candidate lists of the five rows a correction entry reopened or widened (`bi:1123-0`, `bi:910-0`, `epoch:Microsoft SAT40`, `bi:848-0`, `bi:1257-0`) are identical to the stored lists, and every `assign` entry's site is resolved and outside the 460. Two other selections of "load-carrying" give 461 (any state, which is no count R2 uses since R2 says "with a state") and 463 (a positive load and a utility in place of `in_dose`); only `in_dose` gives 460. Counting a utility once over its states gives 117, and adding the unit of every site that stays gives 130; neither is 121. Counting units whose placed full load changes gives 116 under both readings, so R2's 121 matches the count of units gaining or losing a site, not of units whose load changes.

The replay row: R2's record notes as uncertain "whether the capacity test's starting load matches what the build used before its overrides". The build's own pre-override assignment is not stored in a permitted file (the overrides write over `utility_id_eia` and `utility_assign`). As an approximation, `pick_utilities` was called on the current inventory's stored candidate lists, loads and capacities in a scratch run; it puts 2,143 of 2,244 rows, and every one of the 460, where they are now. Its start differs from the build's in candidate lists changed later by relocation and corrections, which cannot be undone from permitted records. It gives 378 and 119, not 380 and 121.

## 4. The sites and the unit that differ

Between the module's reading and the reading in bold, the sets of moving sites differ by one site and the sets of units by one unit. Every site the module moves also moves under the other reading.

- **The extra site:** `bi:13-0`, Arizona, 392.9 GWh full load, on Salt River Project (16572). Its other panel candidates with sales, in stored order: City of Mesa (12351, capacity 326.4 GWh), Electrical District No. 8 Maricopa (5729, 406.5), Gila River Indian Utility Authority (65261, 279.2), USBIA San Carlos Project (19604, 238.8), WAPA (27000, 328.8). The three larger Arizona sites among the 460 (`bi:32-0`, `bi:37-0`, `bi:12-0`) stay under both readings, so it is placed before any Arizona site has moved. Under the module's reading Electrical District No. 8 already carries 406.4 GWh, all of it unresolved sites the build packed onto it, so 406.4 + 392.9 exceeds 406.5 and no candidate fits; the site stays. Counting the 460 only once placed, that unit carries nothing at that moment and the site moves there.
- **The extra unit:** WAPA in Arizona (27000:AZ). Under the other reading six small Arizona sites (`bi:49-0`, `bi:41-0`, `bi:48-0`, `bi:42-0`, `bi:23-0`, `bi:47-0`) find the small Arizona units filled by the sites placed before them and go on to WAPA; under the module's reading they go to Gila River or Electrical District No. 8, whose packed load has by then been moved off.
- **Other sites whose destination changes,** with the count of sites and units the same: 24 in Arizona and 3 in Texas (`bi:929-0`, `bi:1212-0`, `bi:911-0`, which swap between Bandera Electric Coop, 1175, and Guadalupe Valley Electric Coop, 7752, because Bandera carries one of the 460, `epoch:Microsoft SAT40`, under the module's reading).

Every site whose destination differs, by its place in the processing order (load in GWh; utility ids as above, plus Arizona Public Service 803 and City of San Antonio 16604):

| Order | Site | State | Load | On now | Module's destination | Other reading's destination |
|---|---|---|---|---|---|---|
| 24 | `bi:929-0` | TX | 657.0 | 16604 | 7752 | 1175 |
| 33 | `bi:1212-0` | TX | 519.0 | 16604 | 1175 | 7752 |
| 55 | `bi:13-0` | AZ | 392.9 | 16572 | stays | 5729 |
| 116 | `bi:46-0` | AZ | 145.2 | 16572 | 5729 | 65261 |
| 119 | `bi:911-0` | TX | 140.2 | 16604 | 1175 | 7752 |
| 127 | `bi:27-0` | AZ | 126.0 | 65261 | 5729 | 19604 |
| 192 | `bi:54-0` | AZ | 45.1 | 65261 | 5729 | 19604 |
| 208 | `bi:33-0` | AZ | 39.2 | 65261 | 5729 | 803 |
| 223 | `bi:29-0` | AZ | 31.2 | 65261 | 5729 | 12351 |
| 230 | `bi:35-0` | AZ | 29.7 | 65261 | 19604 | 803 |
| 232 | `bi:57-0` | AZ | 29.2 | 16572 | 12351 | 65261 |
| 269 | `bi:34-0` | AZ | 18.8 | 16572 | 65261 | 19604 |
| 270 | `bi:38-0` | AZ | 18.7 | 19604 | 65261 | 803 |
| 290 | `bi:49-0` | AZ | 14.1 | 16572 | 65261 | 27000 |
| 292 | `bi:1269-0` | AZ | 14.0 | 19604 | 65261 | 803 |
| 305 | `bi:14-0` | AZ | 12.0 | 16572 | 65261 | 5729 |
| 312 | `bi:41-0` | AZ | 10.7 | 16572 | 65261 | 27000 |
| 323 | `bi:48-0` | AZ | 9.1 | 16572 | 65261 | 27000 |
| 328 | `bi:42-0` | AZ | 8.6 | 16572 | 65261 | 27000 |
| 341 | `bi:25-0` | AZ | 7.1 | 5729 | 12351 | 19604 |
| 348 | `bi:23-0` | AZ | 5.9 | 16572 | 5729 | 27000 |
| 349 | `bi:47-0` | AZ | 5.7 | 16572 | 5729 | 27000 |
| 350 | `bi:45-0` | AZ | 5.7 | 5729 | 65261 | 803 |
| 359 | `bi:56-0` | AZ | 4.7 | 16572 | 5729 | 12351 |
| 368 | `bi:43-0` | AZ | 4.3 | 65261 | 19604 | 803 |
| 374 | `bi:50-0` | AZ | 4.1 | 19604 | 65261 | 803 |
| 380 | `bi:58-0` | AZ | 3.5 | 65261 | 19604 | 803 |

The two readings in bold in section 3 (the 460 left off their current units with every other site counted, and nothing counted at the start) give the same placement for all 460 sites on these inputs.

## 5. The choice, and the agent's recommendation

**The interpretation.** R2: "each site takes the first candidate that can hold its full load on top of what that candidate already carries". Reading N-2 (the module): a candidate carries every site the inventory places on it, the 460 included, at its scaled full load, updated as sites move. The other reading: a candidate carries every site the inventory places on it other than the 460, plus each of the 460 already placed in this pass, where it was placed.

**The consequence.** 379 or 380 sites move; 120 or 121 units gain or lose a site; 27 sites in Arizona and Texas have a different destination, `bi:13-0` moves or stays, and WAPA in Arizona does or does not take six sites. Units whose load in the realised history differs (the module's 114) were not recomputed under the other reading, since that needs the module's realise loop, which this check does not reimplement.

**The agent's recommendation, for Joe to rule on:** adopt the other reading, that the 460 count as carried load only once each has been placed in the pass, with every resolved site counted where the inventory has it. The reasons: R2 asks for the runner-up "under the inventory's own placement rule", and that rule (`pick_utilities`) counts a site's load against a unit only after placing it there; every one of the 460 is being placed again in this pass, so under N-2 a unit can turn away a larger site because of smaller sites that will leave it later in the same pass, which is what keeps `bi:13-0` on Salt River Project while the Arizona small units it is turned away from are emptied after it. Against: N-2 is the more literal reading of "already carries" at the moment of each test, and R2 also says every capacity stays as the inventory has it. That the recommended reading also reproduces R2's 380 and 121 is not a reason for it, and the recommendation would stand if it did not. The module and its summary stay as they are until he rules.

## 6. Limits, and what is uncertain

- The session 20 calculation does not survive, so whether it used the recommended reading cannot be known. I am uncertain about this: two readings (section 3, in bold) reproduce both of R2's numbers exactly and no other variant tried does, which makes it likely but not established that session 20 counted the 460 off their current units or started from nothing. It is also possible a different reading not tried here gives the same pair.
- Not tried, because not expressible from permitted records: the build's actual start before its overrides (the replay in section 3 approximates it and gives 378 and 119); any candidate list as it stood before relocation or before the corrections in force.
- R2 says "counted on assignments alone". Every count here is from placement, not from realised load by year.
- The ERCOT units are found from the region table read as data from `market_region.py`; the checker's region rule is written from that file's docstring and agrees with the module's 125 ERCOT units.

## Files

- `tests/scenario_a_independent_check.py`: the checker (pure functions, `Reading` switches, `main()` printing and returning the moves, the stays and the units).
- `tests/test_scenario_a_independent_check_invented.py`: tests on invented inputs, one per clause of the rule, the readings, the counts, and three deliberate breaks made in the test process.

## 7. Closing, 2026-11-19 (session 23): Joe's ruling applied

His ruling (D-111): "my preferred rule is to lift the 460 unresolved sites first, keeping all other load counted, then place them in the adopted descending-size order. Before finalizing it, check whether returning a site to its original utility when no alternative fits creates a final capacity exceedance because other sites have occupied that space. Distinguish pre-existing exceedances from newly introduced ones. If none is introduced, apply this rule and regenerate the scenario summary." His clarification: "defer the item if lifting first either introduces a capacity exceedance or increases a pre-existing exceedance." Matching the earlier count is not the reason for the rule.

**The check came first** (`docs/gate1/scenario-a-exceedance-check-2026-11-19.md`, made apart from the module and verified by the session). Lifting first introduces no capacity exceedance and increases none: two units are over capacity at the end (6182 in Texas and 3461 in Wyoming), both over already in the inventory as assigned and neither carrying more at the end; 44372 in Texas has no recorded capacity measure (no sales on file in 2020 to 2025, the years the placement rule measures capacity from) and its load does not change. So the rule was applied.

**What changed in the module** (`pipeline/analysis/second_number_scenarios.py`, scenario A's placement only). The starting load of each unit leaves the 460 out and counts every other site of the inventory where it is (`carried_without`, used by `placement_inputs`), and in `runner_up_placement` each of the 460 is added where it lands, with a moved site no longer taken off a unit it was never counted on. A site that no other candidate can hold, or that has no other panel candidate, stays where it is and counts on its unit from its own turn in the order; that clause is the session's reading of his rule, Joe's to strike, and counting such a site only after every site is placed was not tried. Nothing that scenario B or the reconstruction check uses was changed (`realise_history`, `reconstruction_check`, `scenario_b_settings`, `other_end` and the rest are as they were; the only other change in `main` adds the rule's text to scenario A's summary). The independent checker's `MODULE_READING` is now this rule and the earlier reading is kept as `EARLIER_MODULE_READING`; under the rule the checker agrees with the module site by site: the same 460 sites, the same 380 moves with the same origin and destination in the same order, the same 62 and 18 sites that stay, the same 121 units, and the start load equal to 1.8e-12 GWh.

**The counts now.** 380 of the 460 sites move and 121 units gain or lose a site. The one more site that moves is `bi:13-0` (Arizona, 392.9 GWh), which goes from Salt River Project (16572) to Electrical District No. 8 (5729); the unit added is the Western Area Power Administration's in Arizona (27000:AZ). Units whose realised load differs from the reconstruction in some year: 115, against 114 under the earlier reading; the one added is 27000:AZ.

**The 27 changed destinations**, in processing order (full load in GWh at scaled full load; "now" is the module's rule):

| Site | State | Full load | On now | Earlier reading | Now |
|---|---|---:|---|---|---|
| `bi:929-0` | TX | 657.0 | 16604 | 7752 | 1175 |
| `bi:1212-0` | TX | 519.0 | 16604 | 1175 | 7752 |
| `bi:13-0` | AZ | 392.9 | 16572 | stays | 5729 |
| `bi:46-0` | AZ | 145.2 | 16572 | 5729 | 65261 |
| `bi:911-0` | TX | 140.2 | 16604 | 1175 | 7752 |
| `bi:27-0` | AZ | 126.0 | 65261 | 5729 | 19604 |
| `bi:54-0` | AZ | 45.1 | 65261 | 5729 | 19604 |
| `bi:33-0` | AZ | 39.2 | 65261 | 5729 | 803 |
| `bi:29-0` | AZ | 31.2 | 65261 | 5729 | 12351 |
| `bi:35-0` | AZ | 29.7 | 65261 | 19604 | 803 |
| `bi:57-0` | AZ | 29.2 | 16572 | 12351 | 65261 |
| `bi:34-0` | AZ | 18.8 | 16572 | 65261 | 19604 |
| `bi:38-0` | AZ | 18.7 | 19604 | 65261 | 803 |
| `bi:49-0` | AZ | 14.1 | 16572 | 65261 | 27000 |
| `bi:1269-0` | AZ | 14.0 | 19604 | 65261 | 803 |
| `bi:14-0` | AZ | 12.0 | 16572 | 65261 | 5729 |
| `bi:41-0` | AZ | 10.7 | 16572 | 65261 | 27000 |
| `bi:48-0` | AZ | 9.1 | 16572 | 65261 | 27000 |
| `bi:42-0` | AZ | 8.6 | 16572 | 65261 | 27000 |
| `bi:25-0` | AZ | 7.1 | 5729 | 12351 | 19604 |
| `bi:23-0` | AZ | 5.9 | 16572 | 5729 | 27000 |
| `bi:47-0` | AZ | 5.7 | 16572 | 5729 | 27000 |
| `bi:45-0` | AZ | 5.7 | 5729 | 65261 | 803 |
| `bi:56-0` | AZ | 4.7 | 16572 | 5729 | 12351 |
| `bi:43-0` | AZ | 4.3 | 65261 | 19604 | 803 |
| `bi:50-0` | AZ | 4.1 | 19604 | 65261 | 803 |
| `bi:58-0` | AZ | 3.5 | 65261 | 19604 | 803 |

These are the 27 of section 4, now taken from the regenerated summary and the summary on record. Every site the earlier reading moved also moves now.

**State factors.** No factor moves with the rule. Under A only Oregon's factor differs from the inventory's (0.41250 recomputed against 0.41744), as before; Texas stays at 3.0. Moving a site between units of one state leaves the state's totals, and so its factor, as they were.

**Umatilla and Portland General** (unchanged by the rule). Under A: Umatilla (19325:OR) 461.887 points uncapped, 25.0 and 50.0 at the caps of 25 and 50; Portland General (15248:OR) 18.837 points at every form. Under B: Umatilla 315.841 uncapped and 0.0 at both caps; Portland General 18.899 at every form.

**Sample differences against the primary run** (unchanged from the file on record). Each scenario's sample is 1,184 utilities against the primary run's 1,182: Portland General and Umatilla added, none dropped. The sample units whose change in dose differs from the primary's at some form are 96 under A, the same 96 units as before, and 34 under B.

**Scenario A's doses that change, by unit** (change in dose in points, uncapped / capped at 25 / capped at 50; the primary run as assigned in the last column):

| Unit | Earlier reading | Now | Primary as assigned |
|---|---|---|---|
| 1175:TX Bandera Electric Coop | 96.201 / 25.0 / 50.0 | 39.409 / 0.0 / 3.530 | 90.377 / 16.667 / 33.333 |
| 7752:TX Guadalupe Valley Elec Coop | 75.531 / 2.929 / 17.577 | 92.219 / 15.736 / 40.736 | 54.580 / 25.0 / 49.646 |
| 803:AZ Arizona Public Service | 16.085 at every form | 16.334 at every form | 14.849 at every form |
| 12351:AZ City of Mesa | 73.069 / 5.070 / 24.668 | 65.813 / 5.070 / 24.668 | 65.967 / 22.735 / 42.818 |
| 16572:AZ Salt River Project | 12.684 at every form | 11.689 at every form | 13.121 at every form |
| 19604:AZ USBIA-San Carlos Project | 8.983 at every form | 46.244 / 10.531 / 35.531 | 11.825 at every form |

Electrical District No. 8 (5729:AZ), Gila River (65261:AZ) and the Western Area Power Administration's Arizona unit (27000:AZ) are not in the primary run's sample or the scenario's, so no dose is reported for them; 16604:TX (City of San Antonio) is in the sample and its dose under A did not change. No scenario B field changed.

**The regenerated summary** (`data/frozen/second_number_scenarios.json`), compared field by field with the file on record: scenario A's counts (sites moved 379 to 380, staying 81 to 80, units gaining or losing a site 120 to 121, units with different realised load 114 to 115, the count staying because nothing fits 63 to 62), its `differs_from_r2` (now empty), its moves (380, with `bi:13-0` added and 26 destinations changed), its list of units with different realised load (27000:AZ added), the six units' doses above, a new field `rule` carrying his rule and that matching the earlier count is not the reason, and the first `uncertain` sentence brought to the rule. Every other field, scenario B's included, is unchanged. The summary's writer reran the reconstruction check, as its `main` always does: every state passes, 3,229 of 3,229 units, as on file. That run rewrote the check document's Nebraska row with a largest difference of 1.1e-16 where the file on record has 0, with all 162 units agreeing. The same difference appears with the module's code from before the change, so it is floating-point noise in the check and not from this change, and the check document was put back exactly as it was on record.

**Complete.** The reconciliation item is closed by his ruling: the module uses the lift-first rule, its summary is regenerated, and the earlier reading is kept only as the checker's named variant.

Corrected 2026-11-20 at Joe's instruction (D-113): Texas unit 44372 is described as having no recorded capacity measure, where this document first said it had no capacity. No number changed.
