# Specification for G12's mean estimate with nothing planted (session 24, exercise 4b)

Written 2026-11-20 by session 24 and committed before any per-dataset record is read. The plan, `PREANALYSIS.md`, is a draft pre-analysis plan. It is not frozen and it is not registered with anyone outside. Every price behind these records is made up. No price is read, and nothing under `data/blind` is opened.

## 1. The authorization

Joe, 2026-11-20 (D-113): "G12's mean estimate with nothing planted". With: "Carry the existing specifications, failure-reporting rules and reporting limits into the handover. Preserve historical simulation records and write these results separately. Report what the exercises find; do not silently retune the procedure, change the design or start a new procedure-selection exercise. If a finding requires a new research decision, bring it back with one recommendation."

## 2. Why it is wanted

The plan, Fuel-mix control: "G12's mean estimate with nothing planted is reported beside the rates and read separately, since a mean away from zero there is a failure of the adjustment, which no inference procedure repairs, and good rates under G11 do not show the linear adjustment is adequate. If validation fails, the failure rule applies and the fuel specification is not changed in response." The two stage files hold G12's rates, widths, power and realised-path statistics and no mean estimate.

## 3. The exercise, as the session reads it (Joe's to strike)

The figure "beside the rates" is the mean of the headline estimate over the G12 datasets of the runs those rates come from, with nothing planted. It is computed from the per-dataset records that survive on disk under `data/interim/inference_comparison/stage1` and `stage2`. No dataset is drawn and no stage is rerun. If he meant a fresh run of G12, this is not it.

## 4. Every element, with its source

| Element | Value | Source |
|---|---|---|
| The records | the block files `block_PP_BBBBB.json` of the two stage folders, read by path; each record carries the dataset's process, number, realised change and each candidate's reading, the estimate among them | `inference_comparison.run_blocks`, `one`, `candidates.result` |
| The runs | stage 1: seed 20261201, 2,000 datasets a process, candidates A, B and C. Stage 2: seed 20261202, 20,000 a process, candidate C. Both under the comparison fingerprint in force, `fd914a7b…` | the two manifests and the two stage files, read on 2026-11-20 |
| The named figure | for stage 2's 20,000 G12 datasets under candidate C, and for stage 1's 2,000 under candidate C beside it: the mean estimate, its standard deviation, its standard error, a 95% interval, the count of datasets used and the count that failed | the plan's sentence; the handover |
| Which datasets enter the mean | those in which the candidate computed an estimate: no failure recorded and a finite estimate. The count used and the count left out are given, and the left-out by cause | `inference_comparison.realised_path` ("datasets whose candidate computed an estimate"); the plan, Inference, "Numerical failures in the analysis" |
| Beside it, labelled as not the named figure | G11's mean, computed the same way, for the comparison the plan's sentence makes | the handover |
| Beside it, read from files by name and not recomputed | stage 2's stored realised-path statistics for G12 and G11 (the slope of the estimate on the realised change and the root-mean-square error), and the selected procedure's mean range half-width on the headline set from `power_simulation.json` (6.652%), so that the size of a mean can be judged | `inference_validation_stage2.json` if it holds them, otherwise stage 1's file, said which; `power_simulation.json`, `new_host_estimate`, `2%`, `headline_set`, `nothing_planted`, `range_half_width_mean` |

**The session's, with no existing source, none able to change what the figure means:**

- *The interval:* the mean plus and minus 1.96 standard errors. With 20,000 and 2,000 datasets the choice of interval moves nothing that could be read.
- *Stage 1's other candidates.* The estimate is the same least-squares number under every candidate on a dataset, so stage 1's mean is given under candidate C, and the runner checks that the three candidates' estimates agree on the datasets where all three computed one and says so. It reports no other figure for A or B.

## 5. Before the records are used, show that they are the runs' own

For each stage, all three must hold:

1. the manifest's fingerprint equals the stage file's;
2. the count of records for G12 equals the stage file's datasets a process, with every block present and every dataset number present once;
3. the two rates recomputed from the records for G12 under candidate C (the range missing the true value, and the early-years test rejecting a flat history) equal the stage file's stored counts exactly.

The same three checks are made for G11 before its mean is given.

**If any fails, or a block is missing, the exercise stops.** The stages are not rerun to refill the records (a validation run is never extended or rerun after its answer is seen, E5.1), and the matter comes back with one recommendation.

## 6. The runner

A small new module, `pipeline/analysis/g12_mean_estimate.py`, reads those block files by path and writes its own file, `data/frozen/g12_mean_estimate_nothing_planted.json`. It calls no stage function of the comparison, so the comparison's fingerprint guard is not met and is not changed or bypassed. It opens no other folder of made-up datasets. Tests are on invented block files in a temporary folder (`tests/test_g12_mean_estimate_invented.py`), each shown able to fail: the mean with a known answer; a failed dataset counted and left out of the mean; each of the three checks of section 5 refusing in words.

## 7. How it is read, and the limits, fixed before the records are read

- **The plan sets no threshold for "away from zero" and none is invented.** The mean is reported in log points and in percent with its interval, beside the half-width above.
- **A limit that follows from the code, the session's reading, written here before any record is read.** In G12 the fuel shock is a national walk whose steps are normal with mean zero (`inference_comparison.draw`: `rng.normal(0, G11_STEP_SD, years).cumsum()`), loaded by the square root of a state's gas share plus a state deviation. The walk and its mirror image are equally likely, and the headline estimate is a linear function of the outcome. So the estimate's mean over datasets is zero in expectation whatever the adjustment does, and a measured mean near zero is what this construction gives whether or not the linear adjustment is adequate. The mean with nothing planted can show a failure only if it is away from zero, and it cannot show adequacy. What bears on adequacy in these records is how the estimate moves with the realised walk, which the stage files already hold as the slope on the realised change and the root-mean-square error. Those are reported beside the mean for that reason, read from the stored files.
- If the interval excludes zero, that is said plainly as a finding about the linear adjustment under one assumed process, with one recommendation.
- **The fuel specification is not changed in response to anything found,** and no new process, candidate or control is tried. Whether the plan's sentence should name the slope beside the mean is a research decision, and it goes to Joe with one recommendation.

## 8. Stops

- Any check of section 5 failing, or a missing block.
- A historical record's hash changing (`docs/gate1/historical-record-hashes-before-2026-11-20.txt`): reported, and nothing is restored by hand without saying so. The block files and manifests are read and never written.

## 9. Addendum, 2026-11-20, written and committed before any per-dataset record was read

Four things the runner's builder found or added, none of which changes what the named figure means. They are the session's, marked.

1. **Stage 2's stored file holds no realised-path statistics** (established by reading the stage file, which is a frozen summary and not a record). Section 4 says they are read from stage 2's file "if it holds them, otherwise stage 1's file, said which". So stage 1's stored statistics under candidate C are read by name. Beside them, stage 2's slope and root-mean-square error are computed from stage 2's records by the comparison's own function, `inference_comparison.realised_path`, imported and not reimplemented, and labelled as recomputed from the records. They sit beside the mean and are not the named figure.
2. **The candidates' agreement on stage 1's estimates** is judged at a tolerance of 1e-9 log points, and the largest absolute difference is reported as it is.
3. **Two more stops, read as part of check 2:** a block file whose header is not the one its name gives, and a record with no reading for candidate C.
4. **The count of numerical failures** recomputed from the records is compared with the stored count and recorded. It is not one of the three checks and does not stop the exercise.

The standard deviation has n - 1 in its divisor, and percent is 100 times the log-point figure, as the stage reports give it.

## 10. Dated note, 2026-11-20, after the exercise (session 25; Joe's ruling of that day on D-114, D-115)

Added by session 25. Nothing above is rewritten, and the exercise is not rerun.

Section 1 quotes the plan's sentence as it stood: G12's mean is read separately "since a mean away from zero there is a failure of the adjustment, which no inference procedure repairs". Joe ruled on 2026-11-20: "Keep the mean and report the existing slope and root-mean-square error for G12 and G11, identifying their sources and units. State that the mean is zero in expectation under the construction and cannot establish adequacy of the fuel adjustment. Correct the older sentence that treats a nonzero mean as necessarily identifying failure of that adjustment. These are descriptive diagnostics, not a new validation verdict or selection criterion. Set no new threshold, change no fuel control, and run no additional simulation."

The plan's sentence is corrected there (Fuel-mix control) under that ruling. Read with it:

- The result file's text `limit_read_from_the_code` says the mean can show a failure only if it is away from zero. The file is the record of one authorized exercise and stays as written. What the plan and the final package now say is his ruling: the mean is zero in expectation under the construction and cannot establish adequacy of the fuel adjustment, and a mean away from zero would not necessarily identify a failure of that adjustment either.
- The slope of the estimate on the realised change and the root-mean-square error, for G12 and G11, are reported beside the mean as descriptive diagnostics, with their sources and units, in the plan and in `data/frozen/prefreeze_quantity_summaries.json` (`open_item_13.g12_descriptive_diagnostics`, carried from the result file by `prefreeze_summaries.g12_descriptive_diagnostics` and not recomputed). They are not a validation verdict and not a selection criterion. No threshold is set, no fuel control is changed, and no simulation was run.
- Section 7's phrase on what "bears on adequacy" is the specification's wording of 2026-11-20 and is kept here as a record. The plan no longer uses it (the session's reading of his words, his to strike).
