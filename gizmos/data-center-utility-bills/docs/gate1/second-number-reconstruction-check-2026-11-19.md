# The per-state reconstruction check for the second number's sensitivity scenarios (2026-11-19)

Written by a build agent of session 21 under Joe's ruling of 2026-11-19 (D-107): "Require the per-state reconstruction check outside Oregon. Report any discrepancy and stop the affected scenario work rather than changing rules to obtain agreement." Quantity-side only: load shares, sales and the corrections in force. No price, revenue or bill is read. The plan is a DRAFT and not frozen.

## 1. The comparison, written down before the check was run

**What is reconstructed.** For every state with a panel unit, one configuration through `pass_c_exact.realise` (the scratch rebuild `pass_c_expand.scratch_state` and `assignment.evaluate`, not the enumeration's arithmetic), set up exactly as `second_number.oregon_state` sets it up for Oregon: the inputs from `assignment.load_inputs()` (the live `data/interim` inventory) with `timing.patch_unknown`, `facility_year.parquet`, `state_anchor.parquet`, the buildout records and an empty `frozen_2024_mw`; the corrections are the history entries in force (`timing.timing_entries` of `pipeline/facilities/verified/pass_c_corrections_s17.json`) for the state's sites, parsed by `pass_c_expand.parse_corrections`, at the generic screen's shift 0 (no screen entries). The settings passed are none: every date and capacity question takes its convention, an assignment stays as mapped, and a question with no convention takes its first setting, which is what `realise` does. Only the two Oregon sites with no load history (`bi:852-0`, `bi:837-0`) have questions with no convention.

**Against what.** `data/interim/utility_year_dose.parquet`. A unit-year with no row there carries no data center load.

**Which units.** Every panel unit of the state that no load-unknown site reaches, that is, every unit except those in `every_affected_utility` of `data/frozen/unknown_load_sites_and_affected_utilities.json` (Portland General and Umatilla in Oregon). Every year 2001 to 2025.

**The quantity compared.** The load share in points: the realised as-built GWh over the unit's 2009 to 2011 base (`assignment.load_inputs`'s base, which is the dose file's `base_retail_gwh` where the dose file has one) times 100, against the dose file's `dose` times 100. For a unit with no positive base the load share is undefined; its realised GWh is compared with the dose file's `dc_gwh` instead and the unit is listed. The recomputed state factor is reported beside the frozen one (`state_anchor.parquet`'s `factor`), since a factor that moved would move every permit-based load in the state.

**The tolerance.** The Oregon check on file (`second_number_design.json`, `reproduction_checks.enumeration_against_the_as_built_case`, built by `second_number.design_summary`) reports the largest absolute difference (0.0 points over 39 units) and states no tolerance; neither does the as-built case's check against the dose file beside it, nor any test that reads them. So, as the session's prompt directs where none is stated: **agreement is equality to floating-point rounding, a difference of at most 1e-9 of the larger of the two values in absolute terms (relative), and exact equality where either value is zero.** This is the agent's reading of "exact" where no tolerance is on file.

**What a discrepancy does.** Any unit-year outside the tolerance is a discrepancy. It is reported here with the unit, the years and both values, and it stops the scenario work in that state (the agent's reading of "affected": a scenario recomputes every state's history through the same `realise` call, so a state whose primary history `realise` does not reproduce cannot be trusted under either scenario there; a scenario summary that would include that state is not written). No rule, tolerance or input is changed to obtain agreement, and the check is not narrowed.

## 2. The result

Run on 2026-11-19 by `pipeline/analysis/second_number_scenarios.py` (`reconstruction_check`), tolerance 1e-09 relative as stated above. Load shares in points unless a unit has no positive base.

**Every state passes: 3229 of 3229 units agree in 55 states.**

| State | Units compared | Agree | Largest absolute difference | Largest relative difference | Factor recomputed | Factor frozen | Left out (reached by a load-unknown site) |
|---|---|---|---|---|---|---|---|
| AK | 78 | 78 | 0 | 0 | 1.0 | 1.0 | none |
| AL | 64 | 64 | 0 | 0 | 1.0 | 1.0 | none |
| AR | 36 | 36 | 0 | 0 | 0.2 | 0.2 | none |
| AS | 1 | 1 | 0 | 0 | 1.0 | 1.0 | none |
| AZ | 50 | 50 | 0 | 0 | 0.490932891004505 | 0.490932891004505 | none |
| CA | 62 | 62 | 0 | 0 | 0.9480568446678316 | 0.9480568446678316 | none |
| CO | 60 | 60 | 0 | 0 | 0.8233898069292344 | 0.8233898069292344 | none |
| CT | 11 | 11 | 0 | 0 | 1.0 | 1.0 | none |
| DC | 1 | 1 | 0 | 0 | 0.2 | 0.2 | none |
| DE | 11 | 11 | 0 | 0 | 0.2 | 0.2 | none |
| FL | 52 | 52 | 0 | 0 | 3.0 | 3.0 | none |
| GA | 99 | 99 | 0 | 0 | 3.0 | 3.0 | none |
| GU | 1 | 1 | 0 | 0 | 1.0 | 1.0 | none |
| HI | 4 | 4 | 0 | 0 | 1.0 | 1.0 | none |
| IA | 188 | 188 | 0 | 0 | 1.6913073861754802 | 1.6913073861754802 | none |
| ID | 34 | 34 | 0 | 0 | 1.0 | 1.0 | none |
| IL | 73 | 73 | 0 | 0 | 1.106842170132156 | 1.106842170132156 | none |
| IN | 120 | 120 | 0 | 0 | 3.0 | 3.0 | none |
| KS | 159 | 159 | 0 | 0 | 0.5717231722117382 | 0.5717231722117382 | none |
| KY | 64 | 64 | 0 | 0 | 1.0 | 1.0 | none |
| LA | 39 | 39 | 0 | 0 | 1.0 | 1.0 | none |
| MA | 47 | 47 | 0 | 0 | 1.6120923546104597 | 1.6120923546104597 | none |
| MD | 12 | 12 | 0 | 0 | 0.2 | 0.2 | none |
| ME | 10 | 10 | 0 | 0 | 3.0 | 3.0 | none |
| MI | 58 | 58 | 0 | 0 | 0.6471603754451558 | 0.6471603754451558 | none |
| MN | 178 | 178 | 0 | 0 | 1.9416640365367872 | 1.9416640365367872 | none |
| MO | 137 | 137 | 0 | 0 | 2.611111679168805 | 2.611111679168805 | none |
| MS | 51 | 51 | 0 | 0 | 0.7872775940796725 | 0.7872775940796725 | none |
| MT | 39 | 39 | 0 | 0 | 1.9973342959859077 | 1.9973342959859077 | none |
| NC | 109 | 109 | 0 | 0 | 2.2266206255592413 | 2.2266206255592413 | none |
| ND | 40 | 40 | 0 | 0 | 1.0 | 1.0 | none |
| NE | 162 | 162 | 0 | 0 | 0.2 | 0.2 | none |
| NH | 11 | 11 | 0 | 0 | 0.2 | 0.2 | none |
| NJ | 14 | 14 | 0 | 0 | 1.179779930656193 | 1.179779930656193 | none |
| NM | 33 | 33 | 0 | 0 | 0.2 | 0.2 | none |
| NV | 22 | 22 | 0 | 0 | 0.2 | 0.2 | none |
| NY | 62 | 62 | 0 | 0 | 1.8157912705918935 | 1.8157912705918935 | none |
| OH | 117 | 117 | 0 | 0 | 0.5744344617254172 | 0.5744344617254172 | none |
| OK | 97 | 97 | 0 | 0 | 3.0 | 3.0 | none |
| OR | 41 | 41 | 0 | 0 | 0.41249962805698687 | 0.4174402691339885 | 15248:OR, 19325:OR |
| PA | 57 | 57 | 0 | 0 | 3.0 | 3.0 | none |
| PR | 1 | 1 | 0 | 0 | 1.0 | 1.0 | none |
| RI | 3 | 3 | 0 | 0 | 1.0 | 1.0 | none |
| SC | 46 | 46 | 0 | 0 | 1.0 | 1.0 | none |
| SD | 75 | 75 | 0 | 0 | 3.0 | 3.0 | none |
| TN | 91 | 91 | 0 | 0 | 0.2 | 0.2 | none |
| TX | 160 | 160 | 1.78e-15 | 2.03e-16 | 3.0 | 3.0 | none |
| UT | 54 | 54 | 0 | 0 | 0.7627926333811607 | 0.7627926333811607 | none |
| VA | 34 | 34 | 0 | 0 | 0.41501257956863474 | 0.41501257956863474 | none |
| VI | 1 | 1 | 0 | 0 | 1.0 | 1.0 | none |
| VT | 21 | 21 | 0 | 0 | 1.0 | 1.0 | none |
| WA | 67 | 67 | 0 | 0 | 1.621446345518231 | 1.621446345518231 | none |
| WI | 119 | 119 | 0 | 0 | 3.0 | 3.0 | none |
| WV | 16 | 16 | 0 | 0 | 0.2 | 0.2 | none |
| WY | 37 | 37 | 0 | 0 | 1.6855053333665404 | 1.6855053333665404 | none |

States with no site of the inventory, where realise cannot be called (assignment.matrices fails on an empty frame) and every unit carries zero load in any history, compared as zero against the dose file: AK, AS, GU, HI, RI, VI. Their factor is reported as the inventory's.

States whose recomputed factor differs from the inventory's: OR. In Oregon this is expected and does not reach a unit compared: realise sets the two sites with no load history at their first setting (bi:852-0 from 2024; bi:837-0's date and the rest of its capacity at 2011), where the inventory carries no load for them, so the 2024 permit total and the factor move; in the live inventory every permit-based Oregon site in the dose is on Portland General or Umatilla (checked on facilities.parquet), the two units left out, so every Oregon unit compared carries measured load or none.

Units with no positive base, compared in GWh: 10262:WV, 10325:CA, 10539:NM, 11269:TX, 11591:AK, 12030:SD, 12155:TX, 12658:ND, 12698:KS, 12853:KY, 1307:WY, 13183:KS, 13190:MO, 13433:MA, 13433:NH, 13433:VT, 13941:KS, 14088:ND, 14237:NE, 1513:TX, 15296:NY, 15497:PR, 1594:KY, 16023:IA, 16182:VT, 17106:MO, 17454:KS, 17535:IL, 17583:TX, 17699:TX, 17706:IA, 17718:KS, 17718:OK, 18205:UT, 18521:AK, 18554:IA, 18589:TX, 18642:VA, 18877:AK, 189:AL, 19498:WV, 19869:LA, 19879:VI, 20078:WV, 20395:ND, 20404:TX, 21002:NC, 21073:TX, 25495:TX, 27000:ID, 27000:OR, 27000:WA, 27490:MT, 3155:WA, 3278:TX, 3703:NE, 3990:CA, 40051:TX, 40305:TN, 40362:AZ, 40428:GU, 40429:AS, 409:AK, 4184:NH, 4265:AZ, 44372:TX, 4793:MN, 49848:MA, 5139:TX, 5188:MT, 5567:WA, 55962:CA, 55:AL, 56621:WA, 5779:WV, 58113:TX, 58123:AZ, 58123:CA, 58123:NV, 58124:FL, 58125:CA, 58126:CA, 58139:SD, 58789:CA, 58851:CA, 59013:WA, 59505:IN, 60080:IA, 60502:CA, 6069:LA, 60715:CA, 60839:KS, 61353:PA, 6207:CT, 62107:CA, 6257:NV, 62779:CA, 65261:AZ, 65352:OR, 653:AK, 66052:CA, 66058:UT, 66062:CA, 7174:KY, 7197:GA, 8116:NC, 8289:KY, 8347:MN, 8347:WI, 8779:MA, 8901:TX, 9191:NV, 924:MO, 967:ID, 9737:KS, 9898:AK, 9975:UT.

Every unit that disagrees, with its years and both values: none.

## 3. What stopped

Nothing stopped: every state reproduces the dose file, so both scenarios were built in every state.
