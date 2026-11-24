# Step E: the adopted rules for the inference comparison, the validation budget and the simulation's access list

**Status.** Adopted by Joe on 2026-11-18 (D-95), with his corrections, consolidated here.
Written before any performance result of step E exists.
Nothing was run: no pipeline code, simulation or test; no file under `data/` was opened.

Each rule is marked ADOPTED (D-95), CARRIED (with its earlier entry), or "session's working-out of D-95" where his words left a step open; he can strike any of the last kind. Known when written: D-52 and D-53 (the bootstrap as built on the old specification). A *cell* is one price process and one rate (the 90% range misses the true value; a flat history fails the early-years test at 0.10): 13 processes, 26 cells a candidate. A *worker* is a computer process, never a price process.

## 1. Stage 1 screening (replaces D-61 7.1 step 1, struck by D-72 item 8)

**E1.1 CARRIED** (D-59 item 3; D-61 section 7). Stage 1 selects and never certifies: 2,000 datasets a process, seed 20261201, the same datasets for every candidate.

**E1.2 ADOPTED (D-95).** A candidate is excluded if any cell rejects "true rate at most 10%" in an exact one-sided binomial test at 0.05/26 = 0.0019. At 2,000 datasets that is a count of **241 or more** (12.05%) in any cell; 240 would not meet the level (its tail probability is 0.0020).

> "This is a screening rule, not certification: surviving it does not establish that all true rates are at most 10%."

Illustrations only, not guarantees across the 26 cells (they treat cells singly or as independent): a cell truly at 10% reaches 241 with probability 0.16%; at 11%, 7%; at 11.5%, 23%; at 12%, 48%. Bonferroni bounds at 5% the chance that a candidate at or under 10% in every cell is excluded, whatever the dependence.

**E1.3 ADOPTED (D-95).** Every rate is reported with its count and exact 95% interval; no average enters anything.

**E1.4 CARRIED** (D-58 4.3, 4.4; D-59 item 3), retained by D-95. Twelve-hour stop for stage 1 on ten workers; nothing added on the spot; datasets, replications and processes never cut to fit.

**E1.5 ADOPTED (D-95).** Dataset k of process p has its own seed (20261201, p, k) and bootstrap weights a separate stream, so no candidate changes another's datasets. `inference_check._chunk` (lines 136 to 143) now draws both from one generator and is changed before step E runs.

## 2. Calibration screening, then width ranking

**E2.1 ADOPTED (D-95).** Among candidates that survive E1.2, the narrowest median range pooled over the 26,000 datasets is selected. Rates below 10% earn nothing.

> "Record this as calibration screening followed by width ranking, with independent stage-two certification still required."

**E2.2 ADOPTED (D-95). Paired ties, no margin.** Per dataset d = log(width X / width Y), with both infinite as 0 and one infinite as plus or minus infinity. X is narrower only if the distribution-free 95% interval for the median of d over the 26,000 pairs lies wholly below zero; otherwise tied. A tie including the bootstrap as built goes to it (CARRIED, D-59 item 3). B tied with C goes to the lower share of incomplete and failed ranges, then to C.

**E2.3 ADOPTED (D-95). If no candidate survives.** That result is reported; no excluded candidate is selected for validation; the screen is not relaxed; no candidate is added.

> "If no candidate survives, report that result without relaxing the screen or adding candidates after seeing the simulations."

*Session's working-out of D-95:* no stage 2 is run, nothing is called calibrated, and the analysis's ranges are exploratory, labelled as D-58 4.5 labels them ("exploratory, with its measured rates stated beside it"). D-58 4.5 also names the candidate with the smallest worst rate as the one reported; D-95 does not say whether that part stands, so which procedure's range is shown returns to Joe before the freeze.

**E2.4 ADOPTED (D-95).** Reported, never selecting: cells under 5%; 90th and 95th percentile widths; shares of incomplete and failed sides; power at a planted 5%.

## 3. Coverage and endpoints

**E3.1 ADOPTED (D-95).** Coverage is decided by one test at the true value: covered if its p-value is 0.10 or more. A numerical failure of that test is reported explicitly and is never counted as coverage; the dataset is a failed dataset under section 4.

**E3.2 ADOPTED (D-95).** B's bracket doubles from the estimate (10, 20, up to 640 clustered standard errors) until p falls below 0.10, then bisects to 0.05% of price (D-58 4.1). Each side ends **bounded**, **search incomplete** or **numerical failure**. "Unbounded" is never assigned and no limit argument is built.

> "If an endpoint is not found within the fixed 640-standard-error search, label that side 'search incomplete,' not 'unbounded.'"

No additional endpoint-search round is authorized.

**E3.3 ADOPTED (D-95).** For width ranking, any range with an incomplete or failed side is infinitely wide and stays in the median. Incomplete searches and numerical failures are reported separately, by simulation cell. In the analysis an incomplete side reads "search incomplete beyond X".

## 4. Numerical failures

**E4.1 ADOPTED (D-95), with D-59 items 3 and 7 CARRIED.** Any actual numerical failure in a candidate's computation for a dataset (fit, restricted fit, adjustment, degrees of freedom, either test, the endpoint computation), including any non-finite bootstrap replication, fails the dataset. It stays in the denominator and counts against that candidate as a miss and a rejection. Nothing is dropped or replaced. Rank is checked before anything is inverted.

**E4.2 ADOPTED (D-95).** Reaching the 640 cap without a crossing is "search incomplete", not a failure, and costs only infinite width.

**E4.3 ADOPTED (D-95).** Failure counts and causes are reported apart from ordinary misses and rejections, by process and candidate, and the combined rates are labelled as including failure penalties.

**E4.4 Session's working-out of D-95.** `estimator.py` (lines 191, 208) and `power_simulation.py` (398, 402) now drop non-finite replications through `nanquantile`, and no simulation loop catches `RankDeficient`. Both are changed to E4.1 before step E runs.

## 5. The validation budget

**E5.1 CARRIED** (D-59 item 3; D-61 addendum point 2, adopted by D-72 item 8). The one-sided 95% Monte Carlo upper bound (rate plus 1.645 standard errors) is at or under 11% in every process, for the range and the early-years test separately; no averages. Fresh datasets, seed 20261202. A failure is exploratory inference, no runner-up, no other seed, reported as "observed excess rejection" or "insufficient precision to certify". A run is never extended after its answer is seen.

**E5.2 ADOPTED (D-95). The benchmark.** Each candidate, 20 datasets for each of 13 processes, on the final design, the real run's machine and ten workers, seed 20261130 (used nowhere else). It times **the same full computation as stage 1 and validation**, endpoint computation included, measured inside workers while all ten are busy.

**E5.3 ADOPTED (D-95). Cost.** Hours for N a process = 1.25 × N × (sum over processes of mean seconds a dataset) / (10 × 3,600). The twelve-hour limit applies to stage 1 (all three candidates, N = 2,000); if the projection exceeds it, the session stops and reports before stage 1.

**E5.4 ADOPTED (D-95). Ceiling and ladder.** Validation uses the largest of 20,000, 10,000 or 5,000 fresh datasets a process whose projection is 72 hours or less. The budget is fixed for each candidate and recorded in the ledger before stage 1, from timing alone. If even 5,000 does not fit, the session returns to Joe before stage 1.

**E5.5 ADOPTED (D-95).** The 11% standard is unchanged; certification is less likely at smaller budgets.

> "failure to certify does not itself establish invalidity. No result-dependent extensions or runner-up validation."

What a nominal procedure faces (normal-approximation pass line; the all-26 columns are illustrations treating cells as independent):

| A process | A cell passes at a count of at most | True 10%: one cell | True 10%: all 26 | 9.5%: all 26 | 9.0%: all 26 |
|---|---|---|---|---|---|
| 20,000 | 2,128 (10.64%) | 99.9% | 97% | about 100% | about 100% |
| 10,000 | 1,049 (10.49%) | 95% | 26% | 99% | about 100% |
| 5,000 | 514 (10.28%) | 75% | 0.06% | 46% | 98% |

**E5.6 ADOPTED (D-95).** The benchmark executes the required computations to measure their time, and does not inspect, summarize or retain their performance outputs. It prints only seconds a dataset by candidate and process, projected hours, machine, workers, commit and fingerprint.

## 6. Order of work, and what a performance result is

**E6.1 ADOPTED (D-95).** (1) Step D done; every expensive run fingerprinted (CARRIED, D-59 item 5). (2) Support, net weights after all controls, fully absorbed hosts, each host's gas share against its matches' range. (3) Influence deletions on quantities. (4) G7's utilities fixed from those weights. (5) Code for B, C, G7 to G12, E1.5, sections 3 and 4, tested on invented designs; committed. (6) Benchmark and budget entry. (7) Stage 1. (8) Stage 2, if a candidate survives. (9) Access list and hash committed, then the simulation under the selected procedure (D-58 4.7). Joe's adoption of these rules (D-95) is done.

**E6.2 ADOPTED (D-95).** A performance result is any statistic computed from a candidate's output on a stage-1, stage-2, benchmark or simulation dataset (rate, p-value, estimate, range, width, endpoint state, failure count). Steps 2 to 4, timings and this document's arithmetic are not.

## 7. Window definitions for what step E runs, as coded (ADOPTED, D-95)

Constants are in `pipeline/analysis/power_simulation.py` unless named.

- **Event study:** years g−6 to g+3 for cohort g, g−3 the omitted reference (`PRE, POST, REF`, line 84; `build_windows`, `assemble`, `design.build`); cohorts 2011 to 2022 (`COHORTS`; `design()`), at 2% and, in the simulation, 5%; size and region matched in g−3.
- **Early-years test:** event years −6, −5, −4, failing at bootstrap p below 0.10 (`EARLY`; `estimator.Fit.summary`). **Headline:** mean of event years 2 and 3 (`HEADLINE`, `COMBO`).
- **Made-up prices:** 2001 to 2025 (`inference_check.made_up`). **Pre-trend power:** drift times (event year + 3), on G0 and G6 (`TREND_PATH`).
- **Planted effects:** a third a year from event year 0, full from 2; 0% to 12% (`planted_path`, `TAUS_PCT`).
- **Misdating:** true crossing = recorded + an error from the host's distribution; 69 or more (no crossing) becomes 60, outside the window (`misdating.crossing_errors`; `draw_errors`).
- **Second number:** long form, mean log price 2023 to 2025 less 2008 to 2010, region in 2009 and 2024, size band from 2010, caps 25 (main), 50, none; year-by-year form 2005 to 2025, size band from 2005 (`LONG_PRE`, `LONG_POST`, `PANEL_YEARS`; `run_second_number`; `inference_check.second_number_leverage`).
- **Side set:** own-state comparison utilities, same window, no degree-day or fuel controls (`build_blocks`, `same_state`).

Not run by step E, from `PREANALYSIS.md` line 134: events six years early; fake events for future hosts; drop 2021 to 2023; alternative inventories; thin-coverage states dropped; the 21 region-changers dropped; start years redrawn both ways without the four unsettled sites. Their definitions wait for step F. The misdating test uses the same permit errors, on stand-ins with the four sites kept; it is not the line-134 run.

## 8. The two confirmations owed from D-61 section 7, as given in D-95

**Q-a, confirmed:** width decides among stage-1 survivors, with the paired tie rule and no 2% margin. "Among survivors, choose the narrowest median interval using the specified paired-width tie rule and final bootstrap tie-break."

**Q-b, confirmed with a change:** the doubling bracket to 640 standard errors stands, with three end states, not four: "Never assign unbounded." It replaces D-72 item 8's "Retain the four endpoint states".

## 9. The simulation's never-host access list (ADOPTED, D-95)

> "Former hosts without explicit price-access authorization remain excluded; comparison eligibility alone is not permission to read prices."

A unit (utility, state) is on `pipeline/analysis/simulation_access_list.csv` only if all of these hold:

- **N1.** Comparison-eligible as `power_simulation.design` defines it (load share under 0.5% every year, crypto under 2%, a 2009 to 2011 sales base) on the rebuilt inventory, as built and with no anchoring.
- **N2.** Under 0.5% in every admissible history the sets test: D-46 ruling 4's cases, every timing case (screen, ten-year stress test, open lower end, permit-error sensitivity) and every capacity case (D-61 section 5).
- **N3.** Not in `set_aside` (either variant), any `bounds_lists` list or `dates_and_histories_reasons`, at 2% or 5%.
- **N4.** Not in `price_hold.csv`; any hold recorded elsewhere is added there first.
- **N5.** Never an early, cohort or late host at 2% or 5% in any frozen set file on disk or any committed version of one, unless an adopted ruling explicitly permits its price access, listed with entry and quoted words in an allow-file committed with the script.
- **N6.** Usable in the rebuilt design: full-window availability eligibility from step D, read from the quantities file's usable flag (the source authorized at Stop 1), carried into E. *Session's working-out of D-95:* a unit qualifies under N6 if it is usable in all ten years of at least one cohort window, or in all six years of the second number's long form.
- **N7.** A per-unit outcome file exists, checked by path only.

The script reads quantity files only (`data/frozen/treatment_bounds.json`, `dating_sensitivity.json`, `buildout_sensitivity.json`, the quantities file with its usable flag, the rebuilt dose file, frozen first, `price_hold.csv`, the allow-file, the frozen set files' git history). It writes the list, the excluded units with reason codes and the list's SHA-256. These are generated and committed after step D and before any outcome file is opened. `panel.load_outcomes(purpose="power_simulation")` then refuses any unit off the list or a changed hash. Access covers those per-unit files for the authorized simulation, never the outcome panel. Today the reader (`power_simulation.main`, line 1233; `run_added`, 1178) takes every unit `design()` returns, a wider set; it is narrowed to the list before the simulation runs.

**By name:** Braintree, North Attleborough, Lower Yellowstone and Montana-Dakota are excluded; D-54 ruling 5 made them eligible comparison utilities and gave no explicit price-access authorization. Huntsville stays held (D-54 ruling 5; `price_hold.csv`). Any other unit N5 catches is excluded and named by the script.

## 10. Still the session's working-out, for Joe to strike

1. E2.3: if no candidate survives, no stage 2 is run; D-58 4.5's exploratory labelling applies; which procedure's range is shown returns to Joe before the freeze.
2. E2.2: a tie between B and C goes to the lower share of incomplete and failed ranges, then to C.
3. E4.4: the code changes to `estimator.py`, `power_simulation.py` and the simulation loops so that failures are counted, not dropped.
4. N6: "usable" for the access list means usable in all years of at least one cohort window or of the second number's long form.
