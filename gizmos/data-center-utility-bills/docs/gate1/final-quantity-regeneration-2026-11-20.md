# The final quantity regeneration and reconciliation, 2026-11-20

Written 2026-11-20 by session 25, under Joe's ruling of that day on D-114 (D-115, item 5) and his three clarifications of the same day. The ledger entry is D-116. The plan, `PREANALYSIS.md`, is a draft pre-analysis plan. It is not frozen and it is not registered with anyone outside. No host utility's price in the outcome data has been read, with the lapse in source access the plan discloses as its qualification. This session read no price of any utility and opened nothing under `data/blind`.

His words: "Proceed with final quantity regeneration and reconciliation now that I have settled the Short Form rule. ... Follow job 5 of `HANDOVER_session24_2026-11-20.md`, preserving historical validation records at their existing paths and regenerating the designated current summaries. Complete the specified provenance and wording updates, row U sample checks, E5 lists including the DC/West Virginia check, E7 summaries, and other named quantity checks. Reconciliation means checking the plan against quantity records, not running outcome reconciliation rows. Report changed numbers and their causes. A change affecting headline membership, design or validation compatibility stops only the affected work and comes back with one recommendation."

## 1. The result in brief

- Every current summary on the handover's list was regenerated from the quantity-side files and compared field by field with a copy saved before the session's work.
- **No number of the design moved.** The headline set at 2% still has design-inputs hash `b8515c35cba1`. No host's place, no match and no design-inputs hash of any set changed. Nothing in this work touches headline membership, the design or validation compatibility, so nothing was stopped and nothing comes back on that ground.
- What changed in the stored summaries is what the handover expected: recorded code hashes, the wording of readings Joe has since adopted, the scenario summary's `rule` text, row U's sample block under the adopted Short Form rule, run timings, a date, and three additions (the G12 diagnostics, row U's sample under the rule, and E7 for every cohort utility).
- Every historical record is byte for byte as it was (section 2).
- The reconciliation checked 604 figures of the plan against the records. On the first reading 563 matched, 34 were pending the E7 run or the registry (closed in sections 6 and 7), 2 did not match and 5 were not found as stated. Three figures were corrected in the plan with dated notes: one miscount, and two figures of an earlier simulation that the plan quotes beside a citation and that the stored simulation does not hold. One count sentence was reworded. None of the corrections touches the design (section 9).
- E7's quantity-side checks are complete for the headline set and for every cohort utility, each at the specified 200 draws a direction under seed 20261203 (section 6).

## 2. Hashes and saved copies

- **Before anything was run:** `docs/gate1/stored-file-hashes.sh` hashed every file directly under `data/frozen`, everything under `data/frozen/superseded`, the simulation access list and its hash file, the reconstruction-check document, and the four tables under `data/interim` that record an authorized read and are not in git. The result is `docs/gate1/stored-file-hashes-before-session25-2026-11-20.txt`, 89 files. The script extends `docs/gate1/historical-record-hashes.sh`, whose output equalled session 24's before-file.
- **Saved copies:** every one of those 89 files was copied, byte for byte, into one folder of the session's scratch space that nothing else wrote to, each copy's hash was checked against its original, and the folder was made read-only. Git was not relied on for any of them.
- **After:** `docs/gate1/stored-file-hashes-after-session25-2026-11-20.txt`, by the same script. The files whose hashes differ are exactly the regenerated current summaries of section 3. Every file the handover names as historical or as a record of an authorized read has the hash it had before.
- **One preserved file was rewritten by a writer and restored.** `second_number_scenarios.py` always rewrites `docs/gate1/second-number-reconstruction-check-2026-11-19.md`, as the handover warned. This run changed one row of it by floating-point noise (Nebraska's two difference cells, 0 and 0 before, 1.11e-16 and 2.79e-16 after). The document was restored from the copy saved before the session's work, and its hash was verified equal to the original, `72060a76e556ad42261ea6ed81ff40b4e896e2e54da8d8818f001b8022e591e1`. No other preserved file was rewritten.

## 3. Each current summary, regenerated and compared

Each was run from this folder as `python3 -I <path>`, after its writer was read. "Text" means strings only. "Code hash" means a recorded hash of a code file.

| Command | Writes | What differs from the copy saved before the session | Numbers moved |
|---|---|---|---|
| `pipeline/analysis/design_support_current.py` | `design_support_current.json`, `.csv` | The JSON's recorded code version and the fingerprints that contain it, for all four sets. The CSV is byte for byte equal. Design inputs equal for every set (`b8515c35cba1`, `d0bd87b0b760`, `073871ef1eb8`, `e98127e4fd75`). | none |
| `pipeline/analysis/design_weights.py` | `design_weights.csv`, `design_weights_provenance.json` | The CSV is byte for byte equal. The sidecar's date, its `what_this_is` (the hard-coded "Regenerated on 2026-11-19" brought to both dates) and the code version that includes the driver itself. The one set that differs from the step E record is every cohort utility, as before, with the stated reason and no UNEXPECTED note. | none |
| `pipeline/analysis/prefreeze_summaries.py` | `prefreeze_quantity_summaries.json` | The hash of the design summary it read; two texts on what the step E files hold, brought to the records that now hold the drift figure and G12's mean; a new block `open_item_13.g12_descriptive_diagnostics` (job 2). The rebuilt designs reproduce the matches in the current design summary for all four sets. | none |
| `pipeline/analysis/second_number.py` | `second_number_design.json` | Three texts, each a reading's label brought from "the agent's reading" to its adoption by Joe on 2026-11-19 (D-111). | none |
| `pipeline/analysis/second_number_scenarios.py` | `second_number_scenarios.json`, and the reconstruction document | The scenario A `rule` text, now the wording Joe ruled in D-113. The reconstruction check passes 3,229 of 3,229. The document was restored (section 2). | none |
| `pipeline/analysis/side_runs.py` | `side_run_designs.json` | Ten run timings; two code hashes (`design.py`, `side_runs.py`); eight texts brought to D-111's adoptions (E5's lists, the own-state rank note, the longer horizon's reading). | none but timings |
| `pipeline/analysis/future_hosts.py` | `future_host_runs.json` | One text and two code hashes. | none |
| `pipeline/analysis/timing_run.py` | `timing_run_design.json` | The code version and the fingerprint that contains it. | none |
| `pipeline/analysis/size_band_run.py` | `size_band_design.json` | The code version and fingerprint; four texts brought to D-111. | none |
| `pipeline/analysis/influence_deletions.py` | `influence_deletions_design.json` | The code version and fingerprint; two texts brought to D-111. | none |
| `pipeline/analysis/influence_load.py` | `influence_five_highest_load.json` | Byte for byte equal. | none |
| `pipeline/analysis/weighted_fit.py` | `customer_weighted_fit_design.json` | One text brought to Joe's acceptance. | none |
| `pipeline/analysis/callaway_santanna.py` | `callaway_santanna_sample.json` | Byte for byte equal. | none |
| `pipeline/analysis/conditions.py` | `conditions_groups.json` | Six texts brought to D-111. This writer reads the seven peak columns of the operational file under `data/raw` through `conditions.read_peaks`, once, the one read under `data/raw` the handover permits. The app's permission check allowed it. | none |
| `pipeline/analysis/reconciliation_c.py` | `reconciliation_c_design.json` | Byte for byte equal. | none |
| `pipeline/analysis/reconciliation_mu.py` | `reconciliation_mu_design.json` | Row U's block under the adopted rule (section 4): the stopped status replaced, the 2019-only block removed, and `sample_under_the_adopted_short_form_rule`, `step_u3_window_under_the_adopted_rule`, `filer_table` and `filer_table_rows` added. Every figure outside that block is equal. | none outside the new block |
| `pipeline/analysis/short_form_rule_consequences.py` | `reconciliation_short_form_rule_consequences.json` | Its `what_this_is` and a new field naming the alternative Joe adopted. Every count of every alternative is equal. | none |
| `tests/scenario_a_exceedance_check.py --write` | `scenario_a_exceedance_check.csv` | Byte for byte equal. | none |
| `pipeline/tariffs/sample.py` | `tariff_check_sample.csv` | Byte for byte equal. | none |
| `pipeline/analysis/misdating.py` | `misdating.json` | Byte for byte equal. It is the older calculation and is no part of E7. | none |
| `pipeline/analysis/inventory_runs.py --e7-budget-minutes 600` | `inventory_run_designs.json` | Section 6. | section 6 |
| `pipeline/analysis/run_outcomes.py` | `outcome_run_registry.json` | Section 7. | one count, 1 to 0 |

**The cause of the changed code hashes.** `pipeline/analysis/design.py` was last committed on 2026-11-19 at 21:43 with the correction of one string (D-110), after most of these summaries were last written, and the drivers this session edited in strings record their own hashes. `side_run_designs.json` and `future_host_runs.json` record `design.py`'s hash by file, and it moves from `71457777…` to `07aa7e29…` in both. No fingerprinted file was edited this session, and the working tree shows none modified. That the composite code versions in the other summaries move for the same reason is an inference from those two files and from the commit times, not a separate computation.

**Not regenerated, by the handover's list:** `design_support.json`, `design_support.csv`, `full_window_eligibility.csv`, the two stage files, the benchmark and budget files, `power_simulation.json`, `power_simulation_figures_for_the_bootstrap_as_built.json`, `inference_check.json`, `early_years_drift_selected_procedure.json`, `g12_mean_estimate_nothing_planted.json`, `second_number_classification_proposal.json`, `step_d_check_reproduce.json`, `headline_set_before_ruling_4.csv`, everything under `data/frozen/superseded`, the access list and its hash file, and the three records of an authorized raw read. Also not regenerated, on the handover's reading, which is Joe's to strike: `influence_on_quantities.json` and `second_number_leverage.csv`. The reconciliation found no figure in the plan quoted from either of those two as current.

**Never run:** `design.py`'s `main`, `inference_check.py`, `power_simulation.py`, `inference_comparison.py`, `early_years_drift.py`, `g12_mean_estimate.py`, `simulation_access_list.py`, `reconciliation_inputs.py`, `short_form_filers.py`'s `main`, `short_form_schema.py`, `step_d_check.py`, anything that builds the panel, the inventory or the instrument, and any fetcher.

## 4. Row U's sample under the adopted Short Form rule

From `data/frozen/reconciliation_mu_design.json`, `short_form_flags_for_row_u.sample_under_the_adopted_short_form_rule`, built from the filer table and the 2019 flags file already on disk. The raw file was not read again. No price is read, so the paper's missing-price drop is not applied, and this is not the paper's sample.

| | Unit-years | Utility-states | Utilities |
|---|---|---|---|
| Rows before the three-year count | 17,721 | 3,052 | 2,863 |
| The frame with no exclusion (after the three-year count) | 16,648 | 1,988 | 1,808 |
| Leaving directly, where a record shows a filing | 1, in 2019 | 1 | 1 |
| Leaving through the three-year requirement after the exclusion | 2, in 2023 and 2024 | the same one | the same one |
| The sample under the adopted rule | 16,645 | 1,987 | 1,807 |

- **The three-row reduction, said accurately:** one flagged unit-year of 2019 leaves directly, and two other years of the same utility, 2023 and 2024, leave through the three-year requirement.
- **In the order the row's code takes it** (the filter on the rows before the count, then the count): 17,721 rows, 1,037 of them flagged, 16,684 after the filter, 16,645 after the count. It is the same sample. Of the 1,038 utility-states flagged true in 2019, 1,037 are in the quantity panel in 2019; 1,036 of those are in the panel in no other window year, so the three-year count removes them with or without the exclusion; the 1,038th is in the panel in no window year (the session's recount from the flags file and the panel).
- **2019, explicitly incomplete.** The filer table has no 2019 rows. Of the frame's 1,974 unit-years of 2019, one is flagged true and leaves, 1,780 have a missing flag and 193 have no row in the flags file. Those 1,973 are kept with no record either way. A missing flag or an absent row does not establish non-filing.
- **The filer table:** 18,172 rows, in 2012 to 2018 and 2020 to 2025. None of its unit-years has a row in the quantity panel in any year (the session's recount over every table year: 0 of 18,172).
- **Step U3,** which adds 2025: 19,083 unit-years before the three-year count on 2015 to 2025, 1,362 of them in 2025, none of those with a record of a filing. So applying the rule year by year over the step's window, which is the session's reading and Joe's to strike, gives the same flags in 2025 as applying no exclusion there. The flags of 2015 to 2024 are equal under either window.
- **A coincidence a reader will meet.** In the same block, the count of frame unit-years with no flags row over the whole window is 1,780 (198, 193, 193, 194, 193, 162, 162, 163, 162 and 160 by year), and the count of 2019 unit-years with a missing flag is also 1,780. They are two different quantities. Two readers flagged the equal values as a possible swapped label; the session recounted both from the flags file and both are right.
- **Printed beside ours, for comparison only and no part of any reason:** the paper retains 1,798 utilities and describes a Short Form group of "approximately 560".

## 5. The named checks

- **E5's two lists of states, fixed again** (`data/frozen/side_run_designs.json`, `e5_lists`; recomputed from `data/interim/state_anchor.parquet` by an agent's own script and spot-checked by the session). Dropped, a computed factor of 2 or more: Florida, Georgia, Indiana, Maine, Missouri, North Carolina, Oklahoma, Pennsylvania, South Dakota, Texas and Wisconsin, 11. Flagged and not dropped, a fallback factor: Alaska, Alabama, Connecticut, Hawaii, Idaho, Kentucky, Louisiana, North Dakota, Rhode Island, South Carolina and Vermont, 11. At the lower limit of 0.2 and on neither list: Arkansas, the District of Columbia, Delaware, Maryland, Nebraska, New Hampshire, New Mexico, Nevada, Tennessee and West Virginia, 10. The stored file, the plan and the recount agree.
- **The District of Columbia and West Virginia.** Each has a reference total of 0.0, a raw factor of 0.0 and a factor of 0.2 in the state table. **The check puts neither on a list,** so by D-111 neither is brought to Joe. One limit, said plainly: the state table cannot show whether those two zero totals are reported zeros or values filled with zero when the table was built, and the source file is under `data/raw` and was not opened. I am uncertain about this. Under the rule and the code as they stand it changes nothing.
- **Callaway and Sant'Anna's two counts, counted again** by an agent's own script, which called the module's `sample()` on exactly the inputs its `main()` builds for the headline set at 2% and never called `frame`, `run` or `main`: 7 hosts and 1,670 never-treated units; 680 units in no cohort's host region at that cohort's reference year; 605 in none of the four host regions at any of the five reference years. All equal to the figures on file, as is every cell of the by-cohort table in `docs/gate1/callaway-santanna-regions-without-host-2026-11-19.md`. The stored field `main_design_eligible_pool_units`, which is also 680, counts a different quantity (the union of the hosts' eligible pools in the main design) and shares the number by coincidence; that reading is from the code and the file's own fields, and the pool was not recomputed.
- **The supplier exercise's list of known omissions, frozen.** `pipeline/analysis/supplier_known_omissions.csv` has two rows, both entered on 2026-11-19 and neither amended; git shows one commit and no later change; the regenerated summary carries exactly the file's rows; the plan's description matches.
- **The registry's three counts carried as text:** 18,172 rows and 13,090 unit-years of the filer table in 2015 to 2024, both recounted from the table; 2,157 of 2,203 data center sites given a panel unit by the smallest-polygon assignment, equal in the two stored summaries that record it and not recounted from the incidence table.
- **The pool's restrictions:** `python3 -I pipeline/analysis/pool_restrictions.py --check` before and after every change to the plan this session. Each time the ledger's transcription matched the sources. No transcribed line changed, so the transcription in D-112 stands.
- **Validation compatibility:** section 8.

## 6. E7, for the headline set and for every cohort utility

His words: "Complete E7's already specified quantity-side checks for both the headline set and every cohort utility. Routine wiring of the existing E7 functions to the specified sets is within scope, provided it changes no research rule. Do not substitute the older misdating calculation. Preserve the specified seed and 200 draws per direction; a partial timing run is not completion."

**The command, run once:** `python3 -I pipeline/analysis/inventory_runs.py --e7-budget-minutes 600`. It wrote `data/frozen/inventory_run_designs.json` and nothing else, read no price, and took 4,838 seconds, about 81 minutes, with other light work of the session on the machine. The budget flag is the existing time box and not a research rule; it was set high so that neither set could stop as a partial timing run.

**Both sets ran in full.** Each block says "the specified 200 draws a direction" with `partial_timing_run` false, seed 20261203, 200 draws attempted and 200 computed in each direction, none that could not be computed, and no draw held at a sourced bound. The same 779 rows are redrawn for both sets (688 under 20 MW, 62 from 20 to 50, 29 of 50 and over), from the same errors (`data/frozen/dating_report.json`, `permit_dating_error.errors_in_years_by_generator_based_size_mw`), and draw i redraws the inventory identically for both sets; only the hosts, the reference design and the roster differ. The seven headline hosts have the same shares in both blocks, host by host, which is what that reading of the seed implies.

| | Headline set, block `E7` | Every cohort utility, block `E7_every_cohort_utility` |
|---|---|---|
| Hosts in the roster (`design.split`) | 7 | 41 |
| Hosts in the reference design | 7 | 36, with 5 out |
| Comparison pool of the reference | 3,019 | 3,087 |
| Seconds a draw | 2.43 | 9.31 |
| **Earlier:** recorded first crossing reproduced exactly, share of host-draws pooled over the roster | 95.5% | 55.8% |
| Earlier: within one year | 97.6% | 69.7% |
| Earlier: true crossing two or more years earlier; five or more | 2.4%; 1.0% | 23.2%; 11.9% |
| Earlier: true crossing two or more years later; never reaches the threshold | 0%; 0% | 4.6%; 2.5% |
| Earlier: mean hosts a draw in the design | 7.0 | 30.5 |
| **Later:** reproduced exactly | 99.4% | 59.4% |
| Later: within one year | 100% | 73.3% |
| Later: mean hosts a draw in the design | 7.0 | 32.1 |

- **The headline set's block is equal to the stored one in every figure.** The only fields of it that differ are the measured seconds a draw, the projected minutes and the budget. So are the E4a, E4b and later-start blocks, which the same command writes.
- **Every cohort utility, over the 36 hosts in its reference design** (the mean of `by_host` over those hosts, each host having the same draws): earlier 53.8% exactly and 68.3% within one year; later 56.4% and 71.4%. The plan says the figure for a set is pooled over the set's hosts. The roster is the set's 41 hosts, of which 5 are not in the reference design (one with no usable outcome in every window year, two that fail the support rule, two with load unknown). Both figures are given, and neither is chosen here as the one the write-up quotes (the session's reading, Joe's to strike).
- **Across the 41 hosts** the exact share earlier runs from under 1% to 100%: 15 hosts are reproduced in every draw, the median host in 69.5% of draws, and eight hosts in 13% or less.
- **Not a substitute, and shown only so the reader can see the two are different things:** the older calculation in `data/frozen/misdating.json` gives 58.3% and 70.0% for every cohort utility. It redraws each utility's own permit-dated sites and does not recompute a state's factor or the design. E7's figures are E7's.
- **What was wired, and what was not changed.** `inventory_runs.py` runs the same functions (`e7_rows`, `load_errors`, `e7_draw`, `e7_summary`) once for each set of `E7_SETS`, each with its own reference design and roster from `design.split` and `design.build_with_rules`, and stops in words if the core's comparison pool is not `design.split`'s or the design differs. Which rows are redrawn, from which errors, how many draws and the seed are untouched. One existing defect was corrected because the second set's reference design could not be built without it: `Context.from_files(which="every_cohort_utility")` gave that set the headline set's set-aside list, a pool 68 units short of `design.split`'s 3,087. The stored file had never used that context.
- **Provisional twice over,** as the plan says of the headline set's figures: the design is not final until the freeze, and the error distribution on file is taken again at the freeze.

## 7. The registry

`python3 -I pipeline/analysis/run_outcomes.py`, by its one owner, after every text was final. It builds the registry's document and writes only `data/frozen/outcome_run_registry.json`; it reads no outcome. Against the copy saved before the session: `built_entries_with_stopped_steps` 1 to 0 and its list of ids emptied; row U's `stopped_on_research_inputs` text to null; row U's `needs_before_research_data` rewritten to D-115; the builder text of `E7_earlier` and `E7_later` extended with each set's context. Nothing else changed: 58 entries, 54 built, none blocked, 3 with no code, 1 out of scope for this freeze, 10 built entries with a stated need; the order of unblinding is identical and begins with `reconciliation_row_U` and `reconciliation_row_C`. The plan's statements of those counts match the regenerated file, which closes the 23 figures the reconciliation marked as pending on the registry.

## 8. Validation compatibility

Checked on the quantity side, with no outcome and no stage file opened beyond their fingerprints: the four sets were built as `design.main` builds them, and `outcome_analysis._validation` was called with `ValidationClaim(read_validation_reference(), usable)`. The reference's design-inputs hash is `b8515c35cba1`. The headline set at 2% has that hash and the check passes ("checked: the design's inputs and rules are those the procedure was validated on"). The set with the ten-year case (`d0bd87b0b760`), every cohort utility (`073871ef1eb8`) and the set with the unsettled hosts put back (`e98127e4fd75`) are refused, as they should be: no validation was made on those designs.

## 9. The reconciliation: the plan checked against the quantity records

Three readers, each with one part of the plan, each read-only, checked every figure that describes the data, the design or a stored result against the file and field it comes from. Rules and constants of the specification, figures attributed to a paper, the Water section and counts of tests were not in scope. The session spot-checked figures from each part against the files and verified every exception itself. Line numbers are the plan's as it stood when read, before the session's later edits moved them.

**Totals.** 604 figures checked. On the first reading 563 matched, 34 were pending (11 on the E7 run, 23 on the registry), 2 did not match and 5 were not found as stated. The 34 pending are closed: the headline set's E7 figures in the plan equal the regenerated block (section 6), and the registry's counts equal the regenerated registry (section 7).

**Changed in the plan, each with a dated note and its cause.** None touches headline membership, the design or validation compatibility.

| Where | The plan said | The record | Cause | What was done |
|---|---|---|---|---|
| The second number, the ten highest-leverage utilities | at 50 points two of the ten differ from the first-built ten | three differ (`second_number_design.json`, `runs.ten_highest_leverage_not_settled_left_out.the_ten_by_form`) | a miscount when the sentence was written; the stored file held three before and after the regeneration | corrected to three, dated |
| Load share capped at 25 points | uncapped, three utilities account for two thirds of the variation (D-32) | 0.624 in the stored simulation (`power_simulation.json`, `per_point_of_load.long_difference.uncapped.share_of_load_share_variation_from_the_three_largest_hosts`) | the plan quotes D-32's figure, 67% on the simulation of 2026-11-12 | D-32's figure kept, the stored figure given beside it in a dated note |
| Comparison utilities from the host's own state | the simulation's estimate moved by about two and a half points between this and the market-region comparison (D-32) | 0.83 points on the headline set at 2% (minus 0.149% against plus 0.685%) and 0.90 on every cohort utility (minus 0.378% against plus 0.520%) | the plan quotes D-32's figure, minus 1.5% against plus 1.0% on the simulation of 2026-11-12 | D-32's figure kept, the stored figures given beside it in a dated note, and the write-up quotes the stored ones |
| Row U, the flagged units | of the 1,038 utility-states flagged in 2019, 1,036 appear in the panel in no other window year | 1,037 of the 1,038 are in the panel in 2019; 1,036 of those are in it in no other window year; the 1,038th is in it in no window year | imprecise wording; the count that matters, 1,036 removed by the three-year count with or without the exclusion, was right | reworded where the plan carries it |

**Not found as stated, and left as they are.** A historical clause on E5 ("four units and three hosts before the ownership repair") has no stored record and cannot be checked from current files. "The five Oregon rows ... are interval rows" is consistent with the inventory, which has six Oregon interval rows, and no field marks the five. That no unit-year of the filer table has a row in the quantity panel "in any year" was stored for the window only; the session recounted it over every table year and it holds, 0 of 18,172.

### Plan lines 1 to 100 (as numbered before the session's later edits to the plan)

Read by an agent (claude-opus-5-5), read-only. 139 figures checked, 138 matched, none mismatched, none not found, 1 pending the E7 run when read (line 79; closed below).

| Line | Figure as the plan states it | File and field | Stored value | Match |
|---|---|---|---|---|
| 17 | 32 utilities above the threshold before 2011 | `prefreeze_quantity_summaries.json`, `open_item_13.late_hosts_and_shares_of_2025_load.counts.long_time_hosts` | 32 | yes |
| 17 | 41 cohort utilities at 2%, 7 in the headline set | same, `counts.cohort_utilities`, `headline_set` | 41, 7 | yes |
| 17 | 21 late hosts at 2% | same, `counts.late_hosts` | 21 | yes |
| 17 | shares of 2025 load 49.5, 36.3, 9.8 points, 10.8, 3.4 (5) | same, `shares_of_the_years_data_center_load` | 0.495206, 0.363425, 0.097797, 0.107833, 0.033537 | yes, all 5 |
| 35 | 115 year-built rows; 27, 22, 66, 76 (5) | `inventory_report.json`, `step_d.year_built_rows`; `year_built_rows.csv` | 115; 27, 22, 66, 76; 115 rows | yes, all 5 |
| 36 | two Oregon sites; Portland General direct, Umatilla through the factor | `unknown_load_sites_and_affected_utilities.json` | as stated | yes |
| 38-41 | the five Oregon rows' bounds (5 rows) | `pipeline/facilities/verified/pass_c_corrections_s17.json` | as stated | yes, all 5 |
| 43 | Umatilla, 99,574,272 configurations a case | `headline_set.csv` `why_not`; `timing_oregon_looser_reading_comparison.json`, `in_force.configurations_by_screen_shift` | 99574272 | yes |
| 43 | looser reading 903,168; no verdict changes | same file, `looser_reading`, `utilities_whose_verdict_differs` | 903168; none | yes |
| 44 | three sites moved to a parcel centroid | `inventory_report.json`, `step_d.locations_corrected` | 3 | yes |
| 44 | NSA row at 0.84 of the threshold | `assignment_evidence_sites.csv`, `bi:937-0` | 0.84 | yes |
| 47 | permit-error reach 10, 16, 10 years | `treatment_bounds.json`, `step_d.timing_fingerprint.settings.permit_error_reach` | 10, 16, 10 | yes |
| 52 | 7 hosts in 7 states | `treatment_bounds.json`, `thresholds.2%.sets.headline_set`; `headline_set.csv` | 7, 7 | yes |
| 52 | the seven first crossings (7) | `headline_set.csv`, `first_crossing` at 2% | as stated | yes, all 7 |
| 52 | 4 investor-owned, 2 public, 1 cooperative | `treatment_bounds.json`, `headline_set.after_by_ownership` | 4, 2, 1 | yes |
| 52 | six with the ten-year case, APS out | `set_with_the_ten_year_case.after`; `headline_set.csv` | 6 | yes |
| 52 | at 5%, five named, the same five with the ten-year case | `treatment_bounds.json` 5% | 5, 5 | yes |
| 52 | ten hosts unsettled on assignment, named | `treatment_bounds.json`, `unsettled_on_assignment` | 10, same names | yes |
| 54 | 7 of 41; the other 34 with a reason | `headline_set.csv`, `why_not_in_the_headline_set` | 34 | yes |
| 56 | unsettled hosts put back: 17 at 2%, 11 at 5% | `treatment_bounds.json`, `labelled_runs_beside_the_headline` | 17, 11 | yes |
| 56 | every cohort utility 41 at 2%, 35 at 5% | `headline_set.csv`; `every_cohort_utility.before` | 41, 35 | yes |
| 56 | timing run years 2015 and 2017; SMUD an early host | `treatment_bounds.json`, `timing_run_at_no_anchoring_years` | 2015, 2017; 2004 | yes |
| 56 | both added hosts ten of ten; the seven's matches unchanged | `timing_run_design.json`, `added_hosts`, `original_hosts_unchanged` | 10 of 10 each; true | yes |
| 56 | Delmarva in Maryland and Pepco in the District barred for Ohio Power | `timing_run_design.json`, `added_hosts[1].rules.ownership_exclusions_on_its_pool` | 5027:MD, 15270:DC, 2011 to 2015 | yes |
| 56 | 5 of 7 unaffected; Walton and Garland as early as 2001 | `treatment_bounds.json`, `headline_set.left[].with_the_remainder_unassigned` | as stated | yes |
| 58 | Montana-Dakota's Montana unit off the access list, two other states on | `simulation_access_list.csv`; `simulation_access_excluded.csv` | SD and WY listed; MT excluded | yes |
| 62 | 62 late-zone rows; 55, 3, 4 (4) | `pipeline/electricity/pjm_late_zones.csv` | 62; 55, 3, 4 | yes, all 4 |
| 65 | 3,019 under 0.5% keeping their place; 1,742 above the floor | `treatment_bounds.json`, `thresholds.2%.comparison_utilities` | 3019, 1742 | yes |
| 67 | rows with no size (13 figures) | `prefreeze_quantity_summaries.json`, `rows_with_no_size` | 1105 of 2244; 42; 15; 9; and the rest as stated | yes, all 13 |
| 69 | ownership table 104 rows for 88 units | `pipeline/analysis/ownership.csv` | 104, 88 | yes |
| 69 | 33 units with no row | `pipeline/analysis/leads/ownership_unsourced_2026-11-18.csv` | 33 | yes |
| 69 | 25 more with a row for some spells only | same leads file against the table | 27 with rows, 2 now fully covered | yes (derived) |
| 69 | 5, 66, 33 by basis | `ownership.csv`, the two basis columns | 5; 66; 33 | yes, all 3 |
| 75 | hosts with unresolved ownership by set (5 sets) | `power_simulation.json`, `hosts_with_unresolved_ownership`; `prefreeze_quantity_summaries.json` | as stated | yes, all 5 |
| 79 | 20 investor-owned pairs, each with a row every window year | `prefreeze_quantity_summaries.json`, `assumed_ownership_spells.headline_set` | 20, 20 | yes |
| 79 | every cohort utility at 2%: eight matches of three hosts replaced | `design_support.json` against `design_support_current.json` | 3 + 4 + 1 = 8 | yes |
| 79 | every cohort utility at 5%: 3 and 6 matches, host counts unchanged | `docs/gate1/fingerprint-dependency-assessment-ownership-repair-2026-11-19.md` | 3; 6; 29, 29 | yes (a document's record) |
| 79 | E7's summary, 200 draws a direction | `inventory_run_designs.json`, `E7` | see the E7 section | closed after the run |
| 80 | each host 6 to 26 comparison utilities in its cell | `size_band_design.json` | 6, 26; no failures | yes |
| 80 | 890 stacked rows, 722 utility-years, 26 of 26, weights equal to 1e-14 | `docs/gate1/size-band-equivalence-2026-11-19.md` | 890; 722; 26 of 26; 1.1e-14 | yes (rounding; see the notes) |
| 80 | three pairs; 16 units | same document | as stated | yes |
| 83 | G12's and G11's means and intervals (8) | `g12_mean_estimate_nothing_planted.json`, `figures` | -0.00587 (-0.0393, 0.0276); 0.0231 (-0.0833, 0.1295); 0.0189; -0.0264 | yes, all 8 |
| 87 | slopes -0.021, 0.001, -0.018, 0.009 | same, `realised_path`; stage 1 also in `inference_comparison_stage1.json` | -0.02071, 0.00111, -0.01783, 0.00934 | yes, all 4 |
| 89 | root-mean-square error 2.42, 2.38, 2.43, 2.40 | same | 0.024153, 0.023764, 0.024270, 0.024021 | yes, all 4 |
| 89 | design inputs `073871ef1eb8` against `2e3d2f599bd4` | `design_support_current.json`, `design_support.json`, `design_weights_provenance.json` | as stated | yes |
| 89 | the other three sets' weights unchanged | `design_weights_provenance.json`, `against_the_design_records` | true | yes |
| 89 | nominal customer shares (7) | `customer_weighted_fit_design.json`, `nominal_customer_weight_share` | 0.3538, 0.2366, 0.1510, 0.1060, 0.0931, 0.0389, 0.0206 | yes, all 7 |
| 89 | effective contributions (7) | same, `effective_contribution_to_the_weighted_headline` | 0.3378, 0.2539, 0.1409, 0.1224, 0.0796, 0.0434, 0.0220 | yes, all 7 |
| 89 | unweighted 12.1% to 15.4% a host | same, `unweighted_fit_contribution_for_reference` | 0.12076, 0.15351 | yes |
| 96 | candidate C selected, passed both rates | `inference_comparison_stage1.json`, `inference_validation_stage2.json` | C; passed, passed | yes |
| 99 | stage 1 count 241; 2,000 datasets a process | stage 1 file | 241; 2000 | yes |
| 100 | stage 2 at 20,000 a process | stage 2 file | 20000 | yes |

Notes from the reader, each an uncertainty said plainly. Line 80's "equal to 1e-14" rests on a document that records a largest difference of 1.1e-14, which matches to one significant figure and is slightly over if read strictly. Line 69's "25 more" is held in no stored field and was derived from the leads file. Two groups rest on documents under `docs/gate1` and on no stored summary: the 5% rematches and the size-band equivalence figures. Not checked, because no stored file records them: the disclosed lapse's counts on line 9, and historical statements dated 2026-11-14 or earlier.

### Plan lines 101 to 208 (as numbered before the session's later edits to the plan)

Read by an agent (claude-opus-5-5), read-only. 297 figures checked: 294 matched, 2 did not, 1 had no stored source, none pending. The three exceptions were verified by the session and are corrected in the plan with dated notes (the section on changed figures above).

| Line | Figure as the plan states it | File and field | Stored value | Match |
|---|---|---|---|---|
| 106 | each row 2,000 draws | `power_simulation.json`, `new_host_estimate.*.draws` | 2000 | yes |
| 110-116 | the stand-in table, 7 rows of a host count and 5 statistics (42) | `power_simulation.json`, `new_host_estimate` and `side_runs`, `nothing_planted` and `early_years_test` | for example -0.149, 3.065, 6.652, 0.95, 0.033 on the headline set at 2% | yes, all 42 |
| 119 | 94.4% of drawn errors zero, headline set at 2% | `power_simulation.json`, `date_errors_drawn_for_these_hosts.exact`; `misdating.json` | 0.944 in both | yes |
| 128 | 1,461 listed units; the list byte-identical to its recorded hash; the Montana-Dakota units | `pipeline/analysis/simulation_access_list.csv` and `.sha256` | 1461; equal; as stated | yes (3) |
| 138 | rows with no size: 1,105 of 2,244; 15 of 42; 40%; 14.5% | `prefreeze_quantity_summaries.json`, `rows_with_no_size` | 1105, 2244, 15, 42, 0.400266, 0.1448 | yes (6) |
| 153 | the second number's range covers zero in 96.6, 94.9 and 84.9% of 2,000 | `power_simulation.json`, `per_point_of_load.long_difference` | 0.966, 0.949, 0.849 | yes (4) |
| 155 | cooperatives at two to six times base | `data/interim/utility_year_dose.parquet` | largest 6.03 | yes |
| 155 | three utilities hold two thirds of the variation (D-32) | `power_simulation.json`, `...uncapped.share_of_load_share_variation_from_the_three_largest_hosts` | 0.624 | not found as stated; D-32's figure of 2026-11-12 was 67%; dated note added |
| 163 | at 25 points the ten are those first built | `second_number_design.json`, `the_ten_by_form`; `second_number_classification_proposal.json` | the same ten | yes |
| 163 | at 50 points two of them differ | `second_number_design.json`, `the_ten_by_form.capped_at_50_points` | 3 differ | NO; corrected to three |
| 163 | uncapped, five differ | same | 5 | yes |
| 167 | the two Oregon sites' 2024 load; 1,944 histories; Umatilla's capped and uncapped changes; Portland General 18.8 to 22.7; Umatilla under A and B (16) | `unknown_load_sites_and_affected_utilities.json`; `second_number_design.json`; `second_number_scenarios.json`; `docs/gate1/umatilla-common-dose-finding-2026-11-19.md` | as stated | yes, all 16 |
| 169 | 1,182 with a dose; 2,046 left out | `second_number_design.json`, `sample` | 1182; 2046 | yes (2) |
| 169 | class counts at three forms (25) | same, `class_counts_by_form` | as stated | yes, all 25 |
| 169 | eleven change class | same | 11 | yes |
| 169 | classes 5 to 8 hold 63.8, 71.9 and 91.9%; the run on classes 2 to 4 has 1,102, 1,098 and 1,095; the ten left out 45.3, 50.5 and 80.5%; class 2 holds 10.5, 8.6 and 6.1% (14) | same, `runs` | 0.637568, 0.719293, 0.918947 and the rest as stated | yes, all 14 |
| 169 | the 2024 to 2025 run adds six and drops none | same, `e3_after_period_2024_2025` | 6; none | yes (2) |
| 169 | superseded figures 69, 21, 33, 1,020 and 75, 7, 56% | the committed version of 2026-11-19 in git | as stated | yes (7, from history) |
| 169 | 39 zero-dose units: 10, 24, 5 | same, `analysis_eligibility_apart_from_simulation_access` | 39, 10, 24, 5 | yes (4) |
| 169 | scenario A 460 sites; scenario B 48 date entries; reconstruction 3,229 of 3,229 over 55 jurisdictions to 2e-15 (8) | `second_number_scenarios.json`; the reconstruction document | as stated | yes, all 8 |
| 169 | scenario A: 380 of 460 move; 121 units; 131 units in the check; the exceedance statements; 14 units, smallest headroom 163 GWh; the earlier reading's counts; six sample units (22) | `second_number_scenarios.json`; `scenario_a_exceedance_check.csv`; the count document | as stated | yes, all 22 |
| 169 | scenario B: 45 rows, 24 earlier, 21 later; samples of 1,184; doses under A and B; 96 and 34 units (13) | `second_number_scenarios.json` | as stated | yes, all 13 |
| 175 | 17 and 41 at 2% | `design_support_current.json` | 17; 41 | yes (2) |
| 176 | the own-state estimate moved about 2.5 points against the market-region comparison (D-32) | `power_simulation.json`, `side_runs` against `new_host_estimate` | 0.83 points on the headline set, 0.90 on every cohort utility | NO; D-32's figure of 2026-11-12; dated note added |
| 176 | five of seven hosts in; 8 and 4 eligible | `side_run_designs.json`, `own_state` | 5; 8; 4 | yes (3) |
| 177 | 48 at 1%; 41 in the design; 42 before the repair; Tampa Electric seven of ten; 5%: five, 28 or 29 (7) | `side_run_designs.json`, `thresholds`; git for the earlier count | as stated | yes, all 7 |
| 178 | 21 late hosts, 20 fully enumerated; seven meet the criterion; the match change for Garland (7) | `future_host_runs.json` | as stated | yes, all 7 |
| 179 | the longer horizon: five of seven; 28 of 36 (4) | `side_run_designs.json`, `longer_horizon` | as stated | yes, all 4 |
| 180 | 680 of 1,670; 605; 7 hosts in five cohorts; 42 matched, 36 among them; eleven removed, four matched; two more (11) | `callaway_santanna_sample.json` | as stated | yes, all 11 |
| 182 | 26 membership-only rows; the supplier exercise's counts 70, 18, 2, 56, 12; two hosts keep nine; two known omissions (12) | `pipeline/analysis/suppliers.csv`; `prefreeze_quantity_summaries.json`, `shared_supplier_exercise`; `supplier_known_omissions.csv` | as stated | yes, all 12 |
| 184 | later starts: 796 rows and the per-shift counts (10); the sensitivity's counts (8) | `inventory_run_designs.json`, `runs.later_start_plus_*`; `later_start_sensitivity.json` | as stated | yes, all 18; the first ten equal after the session's run |
| 185 | 44 pairs, two utilities differ; no Oregon verdict changes (4) | `timing_ceiling_per_screen_case_comparison.json`; `timing_oregon_looser_reading_comparison.json` | as stated | yes, all 4 |
| 194-196 | the four conditions on the headline set and on every cohort utility (34) | `conditions_groups.json`; git for the counts before the footprint tests | as stated | yes, all 34 |
| 202 | the drift exercise: 258 of 2,000, 12.9% (11.5 to 14.4); 95 of 2,000, 4.75% (3.9 to 5.8); no failure; 99 and 73; 5.5% (13) | `early_years_drift_selected_procedure.json` | as stated | yes, all 13 |
| 206 | the five highest-load utilities; the deletion runs' counts (9) | `influence_five_highest_load.json`; `influence_deletions_design.json` | as stated | yes, all 9 |
| 207 | the tariff check covers 41 at 2% | `tariff_check_sample.csv` | 41 | yes |

Notes from the reader. Some figures have no stored summary and were checked against documents under `docs/gate1` (178 points of base, the earlier reading's 379 and 120, the 27 sites, the six units, 1.78e-15 stated as 2e-15) or against committed versions in git (the superseded counts). The lines quote no figure from `influence_on_quantities.json` or `second_number_leverage.csv`, the two files read as historical and not regenerated. The plan quotes `power_simulation.json` as the preserved simulation and does not quote the labelled run's figures for every cohort utility as the study's.

### Plan lines 209 to 379 (as numbered before the session's later edits to the plan)

Read by an agent (claude-opus-5-5), read-only. 168 figures checked: 131 matched, none mismatched, 4 not found as stated, 33 pending when read (10 on the E7 run, 23 on the registry; both closed below). File names drop `data/frozen/`. "mu" is `reconciliation_mu_design.json`, "c" is `reconciliation_c_design.json`.

| Line | Figure as the plan states it | File and field | Stored value | Match |
|---|---|---|---|---|
| 213 | 181 sites verified by hand | mu, `sites/placed_by`; `facilities.parquet` | 181 | yes |
| 213 | first stage 0.411; F 20.9 | c, `first_stage_count_on_instrument_verified_assignment_cap_99_5/paper` | 0.41095; 20.938 | yes (2) |
| 213 | 920 of 2,203 sites with no start year | c, `facility_counts_verified_assignment/report` | 920; 2203 | yes (2) |
| 217 | 2,931 polygons | `reconciliation_polygon_incidence_summary.json`, `counts/polygons_in_layer` | 2931 | yes |
| 217 | TYPE has ten values; NOT AVAILABLE on 1,685 | same, `polygons_by_type_value` | 10; 1685 | yes (2) |
| 217 | wholesale power marketer: one polygon, no site | same | 1; 0 | yes (2) |
| 217 | the retail-first rule places none and lists 2,192 | mu, `U0_assignment_on_the_real_layer/before_d109` | 0; 2192 | yes (2) |
| 217 | `short_form` true on 1,038 rows, all 2019, never false | mu, `short_form_flags_for_row_u` | 1038; 2019 only; 0 false | yes |
| 217 | C0 to C2: 2,157 of 2,203; one exact tie | c, `polygon_assignment_steps_C0_to_C2` | 2157; 1 | yes (2) |
| 217 | 1,890 on the same unit, 240 on a different one | c, `against_the_inventorys_own_assignment_C3` | 1890; 240 | yes (2) |
| 217 | polygon first stage 0.322, F 22.0 | c, `on_stand_in_panel/first_stage_count_on_instrument_cap_99_5/paper` | 0.3216; 22.035 | yes (2) |
| 219 | U0: 2,157; 35; one tie; 8 in no polygon, 5 with no point; 2 with no state | mu, `U0_assignment_on_the_real_layer` | as stated | yes (6) |
| 219 | 167 units against 174 | mu, steps U0 and U1 | 167; 174 | yes (2) |
| 219 | entity types: federal 29 and 459, state 6 and 42, municipal marketing authority 4 and 10, wholesale power marketer 0 and 0 | mu, `entity_type_list/by_type` | as stated | yes (8) |
| 219 | 39 sites listed, 35 map to a panel unit | mu, `entity_type_list` | 39; 35 | yes (2) |
| 219 | same unit 2,157, 46 unplaced | mu, `identity_with_c0_to_c2_site_by_site` | 2157; 46 | yes (2) |
| 219 | the table has rows for 2012 to 2018 and 2020 to 2025, none for 2019 | `reconciliation_short_form_filers_summary.json`, `years_with_rows` | as stated | yes |
| 219 | no unit-year of the table has a row in the quantity panel | same, window field; recounted over every table year by the session | 0 in the window; 0 of 18,172 over every year | yes |
| 227 | 181 rows verified by hand, 159 of them data center sites | `facilities.parquet` | 181; 159 | yes (2) |
| 246 | 2024 spending revised from $31.1bn to $34.8bn | c, `instrument` | 31.1; 34.797 | yes (2) |
| 246 | shares sum to 205% | `instrument_report.json`, `sum_of_shares_dec` | 2.049 | yes |
| 280 | E1, headline set: all 7 in, with the named match changes | `side_run_designs.json`, `sets/headline_set_2pct/E1` | as stated | yes (3) |
| 280 | E1, every cohort utility: 30 of 36; nine left out; Orange and Rockland enters | same, `every_cohort_utility_2pct/E1` | 30; 9; 14154:NY | yes (3) |
| 280 | highest fake-window load shares 1.82% and 1.80% | same | 0.018183; 0.017981 | yes (2) |
| 288 | E2: six units, ten matches each | `future_host_runs.json`, `E2` | 6; 10 each | yes (2) |
| 288 | the named match change for Imperial; the fake dates | same | as stated | yes (2) |
| 288 | 15 left out, 12 also set aside | same, `E2/left_out` | 15; 12 | yes (2) |
| 288 | seven units before the ruling | same, `admitted_by_cohort_meeting_the_other_rules` | 7 | yes |
| 289 | Entergy Mississippi admitted for cohorts 2011 to 2018, in no headline host's pool | same, `side_run` | as stated | yes |
| 293 | E3: 3 of 7; 23 of 36 | `side_run_designs.json`, `E3` | 3; 23 | yes (3) |
| 300 | no headline host at 2% on the still-unsettled list | `buildout_sensitivity.json` against `headline_set.csv` | no overlap | yes |
| 302 | E4a: 327 rows; factors move in 10 states; Arizona 0.49 to 0.51; 7 retained; APS 2021 | `inventory_run_designs.json`, `runs/E4a_slow_path` | as stated | yes (6); equal after the session's run |
| 302 | E4b: 7 retained; PacifiCorp in Utah 2014; 4 units become eligible; Omaha's matches change by one | same, `runs/E4b_anchoring_off` | as stated | yes (4); equal after the session's run |
| 307 | E5: 11 states dropped; Maine, South Dakota, Wisconsin raw factors 4.2, 7.1, 3.9 | `side_run_designs.json`, `e5_lists` | as stated; 4.215, 7.133, 3.940 | yes (4) |
| 307 | 11 flagged, 5 added from outside the report block | same | 11; 5 | yes (2) |
| 307 | four states at 0.2 named, three holding headline hosts; six more at the limit; DC and West Virginia with a reference total of 0 | `state_anchor.parquet`; `headline_set.csv` | as stated | yes (4) |
| 307 | E5, headline set: two hosts out; Omaha left with 4; 4 remain | `side_run_designs.json`, headline `E5` | as stated | yes (3) |
| 307 | E5, every cohort utility: 22 of 36 (23 before); one host out; three units leave two hosts' matches | same | as stated | yes (4) |
| 307 | "four units and three hosts before the ownership repair" | none | a historical figure, no stored record | not found |
| 312 | E6: 23 units; 28 under the other reading | `side_run_designs.json`, `e6_list` | 23; 28 | yes (2) |
| 312 | E6, headline set: two matches removed; none under five; 7 remain | same | as stated | yes (3) |
| 315 | 866 permit-dated rows | `inventory_report.json`; `facilities.parquet` | 866 | yes |
| 315 | the five Oregon rows are interval rows | `facilities.parquet` | 6 Oregon interval rows; no field marks the five | not found (consistent) |
| 316 | the four sites named, permit-dated and carrying load | `facilities.parquet`; `inventory_run_designs.json`, `E7` | as stated | yes |
| 317 | the error field with three size classes | `dating_report.json`, `permit_dating_error/errors_in_years_by_generator_based_size_mw` | 136, 58 and 102 errors | yes |
| 322 | 779 redrawn (688, 62, 29); 4 with no load; 83 with no year or size; none with a sourced bound | `inventory_run_designs.json`, `E7` | as stated | yes (6) |
| 322 | 200 draws each direction, none failed; the shares and percentiles | same | see the E7 section | closed after the run |
| 340-347 | the registry's counts | `outcome_run_registry.json` | see the registry section | closed after the registry |
| 343 | 14,635 numeric fields | `second_number_design.json` | 14635 | yes |
| 345 | scenario A: 380 sites, 121 units; 27 changed destinations; two pre-existing exceedances | `second_number_scenarios.json`; the count document; `scenario_a_exceedance_check.csv` | as stated | yes (4) |
| 345, 357 | 680 and 605 of 1,670 | `callaway_santanna_sample.json`; recounted by the named check | 680; 605; 1670 | yes (4) |
| 347 | 18,172 rows; 1,461 listed units | filers summary; `simulation_access_list.csv` | 18172; 1461 | yes (2) |
| 353 | 1,038 utility-states flagged in 2019 | filers summary, `the_2019_flags` | 1038 | yes |
| 353 | "1,036 appear in the panel in no other window year" | no stored field; recounted by the session | 1,037 of the 1,038 are in the panel in 2019; 1,036 of those are in the panel in no other window year; the 1,038th is in the panel in no window year | not found as stated; wording corrected |
| 353 | no table row in the panel "in any year" | filers summary covers the window; recounted by the session | 0 of 18,172 over every table year | yes on the recount |
| 353 | frame 16,648 unit-years and 1,808 utilities; three leave | mu, `sample_under_the_adopted_short_form_rule` | 16648; 1808; 16645 | yes (3) |
| 353 | "ever filed" removes 3,186 unit-years of 629 utility-states | `reconciliation_short_form_rule_consequences.json` | 3186; 629 | yes (2) |
| 353 | 1,973 unflagged unit-years of 2019 | mu, `year_2019_explicitly_incomplete` | 1780 + 193 | yes |
| 367 | tariff sample 41 rows, 40 paired, one unpaired | `tariff_check_sample.csv` | 41; 40 | yes (3) |

Notes from the reader, each an uncertainty said plainly. The E7 error field sits under `permit_dating_error` in `dating_report.json`, and the plan names it without its parent. The 14,635 counts numeric leaves without booleans, which is assumed to be how it was first counted. In mu's block for row U, the whole-window count of frame unit-years with no flags row is 1,780 and the 2019 count with a missing flag is also 1,780; the reader could not tell a coincidence from a label swap. The session recounted both from the flags file: they are two different quantities with the same value (no flags row by year: 198, 193, 193, 194, 193, 162, 162, 163, 162 and 160, which sum to 1,780; in 2019 alone, 193 with no flags row, 1,780 with a missing flag and 1 flagged true).

## 10. Disclosures

1. **A preserved file rewritten by a writer and restored** (section 2): the reconstruction-check document, one row, floating-point noise, restored from the saved copy with its original hash verified.
2. **A helper of the session's own was refused by the app's safety check,** on the ground that the shell might read it differently than it was parsed. It was a shell function that would have run seven writers in a row and logged each comparison. Nothing ran. Each writer was then issued as the plain command the handover's table gives. That is read as stopping the helper and not the writers (the session's reading, Joe's to strike).
3. **`design_weights.py` was run twice** (section 3). The weights are byte for byte equal in both runs.
4. **One existing defect was corrected as part of the E7 wiring** (section 6), and two small behaviours of `inventory_runs.py` changed with it, neither a research rule: a full run made with a draw count other than 200 is labelled as not the specified 200, and the number of timing draws is capped at twice the draws.
5. **The E7 agent made five timing draws a set in memory where its brief allowed three.** Nothing was written.
6. **The E7 run shared the machine** with the session's agents, their test runs and the second suite command. With the budget set to 600 minutes this could not turn either set into a partial timing run; it does mean the 81 minutes is not a clean timing.
7. **Counted but not recounted from source:** the 2,157 of 2,203 sites of the smallest-polygon assignment, which two stored summaries record independently and equally; the main design's eligible pool of 680 units, which is a different quantity from the 680 never-treated units outside the hosts' regions.
8. **The composite code versions' cause is an inference** (section 3), from two summaries that record the design script's hash by file and from the commit times.

## Dated notes, 2026-11-20 (session 26, D-118)

Added under Joe's ruling of 2026-11-20 on D-116 (D-117, item 8). The text above is a record and is left as it was written.

1. **Section 1's first bullet and the heading of section 3 do not say that one writer ran twice.** The accurate account, in his words: "the weights writer ran twice and produced identical output." `pipeline/analysis/design_weights.py` was run, its hard-coded date was corrected, and it was run again; `design_weights.csv` is byte for byte equal in both runs and equal to the copy saved before the session's work (section 3's row for that writer, and section 10, item 3). Every other writer of section 3 ran once. No summary line of this report should be read as saying that every current summary was regenerated exactly once.
2. **Two process deviations are kept as deviations:** the refused-helper workaround (section 10) and the excess timing draws of the E7 agent, five a set where its brief allowed three, with nothing written from them. His words: "do not describe the session as unqualified compliance. These disclosures do not call for a scientific rerun." No stored number depends on either.
3. **Section 6's two poolings for every cohort utility now have an order** (D-117, item 5): the 36 hosts of the set's reference design are the primary denominator, and the roster of 41 is reported beside it. Both sets of figures are kept, nothing was redrawn, and `data/frozen/inventory_run_designs.json` was not regenerated.
