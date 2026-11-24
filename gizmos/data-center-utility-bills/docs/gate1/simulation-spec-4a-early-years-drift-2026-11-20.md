# Specification for the drift exercise under the selected procedure (session 24, exercise 4a)

Written 2026-11-20 by session 24 and committed before any dataset of the exercise is drawn. The plan, `PREANALYSIS.md`, is a draft pre-analysis plan. It is not frozen and it is not registered with anyone outside. Every price in this exercise is made up. No price is read, and nothing under `data/blind` is opened.

## 1. The authorization

Joe, 2026-11-20 (D-113): "how often the early-years test detects a drift of 1% a year under the selected procedure on the current design". With: "Carry the existing specifications, failure-reporting rules and reporting limits into the handover. Preserve historical simulation records and write these results separately. Report what the exercises find; do not silently retune the procedure, change the design or start a new procedure-selection exercise. If a finding requires a new research decision, bring it back with one recommendation."

## 2. Why it is wanted

The plan's early-years reading (Reported checks, "Flat before"): if the test does not fail, "The test did not detect a difference in the years before." Then: "Where the comparison finds the test catches a drift of 1% a year in fewer than half of datasets on the set, it is followed by: 'On a set this small it would miss a large one.'" No file holds that figure for the selected procedure on the design as it stands, so the code chooses no second sentence (`outcome_analysis.early_years_reading`; `run_outcomes.RunInputs.catches_drift`). `inference_check.json` holds the figure for the bootstrap as built on an earlier design (D-49, D-53), and the stage files hold no planted drift.

## 3. Every element, with its source

An element with an existing source is carried unchanged. An element with none that cannot change what the figure means is fixed here and marked as the session's.

| Element | Value | Source |
|---|---|---|
| The design | the real one, no stand-ins: the headline set at 2% under the headline rules as it stands, built as the comparison builds it. Its design-inputs hash must be `b8515c35cba1`, and the runner stops if it is not | `inference_comparison.real_design`, `build_context`; D-49 part 1 ("The design is the real one"); the handover's reading of "on the current design" as the headline set at 2%, the design the validation ran on |
| The procedure | the selected one, candidate C: CR2 with the Satterthwaite range for the headline, and the approximate Hotelling test on event years -6, -5 and -4 for the early years, failing at p below 0.10 | `candidates.CandidateC`, `candidates.ALPHA`; step E's selection and validation |
| The drift | the hosts' log prices drift away from their comparison utilities' by 0.01 a year over the whole window: 0.01 times the host indicator times years past the reference year, added to a made-up history with nothing else in it | D-49, "Power against a pre-trend of a stated size"; `inference_check.TREND_PATH`, `fixed_parts`'s `trend`. His words name 1% a year. D-49's 0.5% is not named and is not run |
| The price processes | G0, the one D-38 used, and G6, all of it | D-49 ("On G0 and on G6"); `inference_check.GRID`, `TREND_VERSIONS`; drawn by the comparison's `draw` |
| How many | 2,000 datasets a process, in fixed blocks, each dataset with its own seed | D-49, "How many" |
| What is reported | for each process: how often the early-years test fails with the drift planted, with its exact 95% interval; the mean headline estimate; numerical failures by cause | D-49 ("Reported: how often the early-years test fails ... and the mean headline estimate"); the handover |
| A dataset that fails numerically | counted in the denominator, reported by cause, and counted as no detection | the plan, Inference, "Numerical failures in the analysis"; D-95; D-99; `inference_check.summarise` ("Under a planted pre-trend, a failed dataset counts as no detection") |
| Moments | the mean headline estimate is over the datasets in which the candidate computed an estimate, and the count used is given | `inference_comparison.realised_path` ("datasets whose candidate computed an estimate") |

**The session's, with no existing source, none able to change what the figure means:**

- *The seed:* 20261206, used nowhere else. A search of `pipeline/analysis`, `pipeline/electricity`, `pipeline/facilities` and `tests` on 2026-11-20 found no file with it. Dataset k of process p draws from `numpy.random.SeedSequence([20261206, p, k, 0])`, the layout of the comparison's `streams`, with p the comparison's index of the process (0 for G0, 6 for G6). Candidate C draws nothing, so there is no bootstrap seed.
- *Blocks and workers:* blocks of 25 datasets; the number of worker processes is whatever the machine gives. A dataset's numbers depend only on the seed, the process and the dataset's number.
- *The same datasets with nothing planted.* The drift is added to a flat dataset, as D-49's exercise did it, so each dataset is also read with nothing planted. That rate is written in the result file as a mechanics reading, to show how much of the detection rate is the test's ordinary rate of failing a flat history. It is not a validation figure, it is not set against the 11% standard, and stage 2's rates stand as the validation.
- *The interval:* Clopper and Pearson's exact interval, as the comparison computes it (`inference_comparison.clopper_pearson`).

## 4. Which sentence follows, fixed before the run

The plan's rule is "in fewer than half of datasets on the set" and names no process.

- If both processes' measured rates are under one half, the second sentence is added for the headline set.
- If both are at or over one half, it is not added.
- **If one is under and one is not, the session chooses no rule (not the lower, not the higher, not an average). The two rates are reported, the code is left choosing no second sentence, and the matter comes back to Joe with one recommendation.**

The comparison is of the measured share with one half, as the plan's words have it. The exact interval is reported beside each share, and if an interval contains one half that is said. That reading of the plan's words is the session's and is Joe's to strike.

The companion sets get no figure, and the code goes on choosing no second sentence for them.

## 5. The runner, the mechanics check and the one run

A new module, `pipeline/analysis/early_years_drift.py`, calls the comparison's design builder and made-up price generator, D-49's trend path and candidate C's own methods, and edits none of them. It calls no stage function of the comparison, so the comparison's fingerprint guard is not met and is not changed or bypassed. It reads no price.

Tests on invented designs come first (`tests/test_early_years_drift_invented.py`): a planted drift of zero gives the flat-history rate; a large planted drift is detected in nearly every dataset; a dataset that fails numerically is counted and not dropped; the drift moves the headline by 5.5 times its yearly size, as D-53 found. Each is shown able to fail.

One run. It is not extended after its answer is seen, and no other seed, process, drift size or set is run (E5.1). The result goes to a new file of its own, `data/frozen/early_years_drift_selected_procedure.json`, whose `what_this_is` names the exercise, the authorization, this file, the seed, the counts, the code's hashes and the design-inputs hash, and what it is not.

## 6. Stops

- The design-inputs hash is not `b8515c35cba1`: the runner stops before a dataset is drawn.
- The runner cannot run without an edit to a fingerprinted file: it stops, and that is the finding.
- A historical record's hash changes (`docs/gate1/historical-record-hashes-before-2026-11-20.txt`): reported, and nothing is restored by hand without saying so.

## 7. Reporting limits, and what is not done

The rate is a property of this test on this design under made-up prices of two assumed kinds. It is not evidence about real pre-trends. "Not failing is not proof of anything" stands as the plan has it. The figures of D-39, D-41 and D-53 stay on the record for the bootstrap as built on the earlier specification.

Whatever the figure is, the selected procedure stays candidate C, the design stays as it is, no candidate is added and no stage is rerun. If both processes fall on one side of one half, the figure is carried into the reading the plan already fixed: `RunInputs.catches_drift` is given its value for the headline set from the result file by name, the registry says where the value comes from, and the plan's "Flat before" bullet states the two rates and which sentence follows. That changes no rule.
