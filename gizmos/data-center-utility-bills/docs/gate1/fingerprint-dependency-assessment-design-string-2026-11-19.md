# Fingerprint dependency assessment for the descriptive string in design.py, 2026-11-19

Written 2026-11-19 by a build agent of session 22, under Joe's ruling of that day, which says in part: "Do not rewrite historical fingerprints or results to make checks pass. Verify that headline rows and validation compatibility remain unchanged; stop the affected work and report any unexpected change. Include correction of the stale descriptive string with its dependency assessment."

The plan, `PREANALYSIS.md`, is a DRAFT pre-analysis plan. It is not frozen and it is not registered with anyone outside. No outcome, price, revenue or bill was read for this work, and nothing under `data/blind` or `data/interim/availability` was opened, listed or hashed. No simulation and no step E stage was run, and `design.main` was not run. No stored fingerprint and no file on the list of preserved results was rewritten.

The form follows `docs/gate1/fingerprint-dependency-assessment-2026-11-19.md` and `docs/gate1/fingerprint-dependency-assessment-ownership-repair-2026-11-19.md`. The scripts used are in the agent's scratch folder and are not in the repository: a snapshot of every design before and after the edit, built from the quantity files with the existing builders (`design.split` and `design.build_with_rules`, as `design.main` builds them); an abstract-syntax-tree comparison with every string literal blanked; and the kernel's validation check run on designs in memory, with no outcome.

## Result in brief

- One string literal changed, inside `investor_owned_without_rows`. No name, operator, call, key, branch or number moved, and the file has the same 569 lines.
- Every design is identical before and after the edit: sixteen designs (four sets at 2% and at 5% under the headline rules, and the four sets at 2% under each of the two labelled ownership variants), in hosts, matches in order, eligible pools, dropped hosts and design-inputs hash.
- The kernel accepts the validation claim on the headline design at 2% after the edit, and refuses it on every cohort utility as built, as before.
- `python3 -I pipeline/analysis/pool_restrictions.py --check` printed "the ledger's transcription matches the sources" after the edit. `investor_owned_without_rows` is not among the transcribed functions.
- No stop condition was met.

## (a) What changed

`pipeline/analysis/design.py`, sha256 `71457777ed7e460849a1b20c9ede705e20ae1a45399e6f6a80b070d5c7265f5e` at HEAD (a1400d3) and `07aa7e29777ead3e160ea942879e9c7a7245fdb69851c4b7b23f5f4a9738cdf1` after the edit. Line count 569 before and after.

The complete `git diff` against HEAD:

```diff
diff --git a/gizmos/data-center-utility-bills/pipeline/analysis/design.py b/gizmos/data-center-utility-bills/pipeline/analysis/design.py
index 8b21933..0b6b60b 100644
--- a/gizmos/data-center-utility-bills/pipeline/analysis/design.py
+++ b/gizmos/data-center-utility-bills/pipeline/analysis/design.py
@@ -304,7 +304,7 @@ def investor_owned_without_rows(table: pd.DataFrame, units, ownership_of: dict,
         if key in have or key[0] in ids_all_states:
             continue
         out.append({"utility": f"{key[0]}:{key[1]}", "name": None if names is None else names.get(key), "role": role,
-                    "consequence": "not eligible as a comparison for an investor-owned host until it has a row (D-58 rule 2.2)"})
+                    "consequence": "not eligible as a comparison for an investor-owned host whose window has a year with no ownership row covering it (D-58 rule 2.2, read year by year, 2026-11-19)"})
     return out
 
 
```

Line by line: one hunk, the value of the `consequence` key, a string literal, replaced by another string literal. The key name is unchanged. The old wording said a unit with no row is barred "until it has a row"; since the ownership repair of 2026-11-19 the bar is read year by year, so a unit with a row for only part of a host's window is also barred for that host. The units this function lists have no row in the table at all, so for them the new wording and the old one bar the same hosts; the new wording states the rule as ruled.

Evidence beyond reading: the old and new files parse to the same syntax tree once every string literal is blanked. Of the 358 string literals in each file, exactly one differs, the one in the diff. The function's docstring was not changed (the brief authorized the one string only); it still says "Such a unit is not eligible as a comparison for an investor-owned host", which remains true of units with no row at all.

## (b) Where the string is used

`design.investor_owned_without_rows` is called by:

- `design.main` (line 544), which writes the list per set into `data/frozen/design_support.json` under `investor_owned_units_with_no_ownership_row`;
- `pipeline/analysis/design_support_current.py` (new on 2026-11-19), which writes the same list into `data/frozen/design_support_current.json`;
- `inference_check.main` (line 471), which writes it into `data/frozen/inference_check.json`.

No code reads the `consequence` field back. A search of `pipeline/analysis`, `pipeline/electricity` and `tests` finds it written at line 307 and read only by `tests/test_step_d_rules.py`, which asserts that the field contains "not eligible"; the new string still does, and that test passes. No number in any output is computed from it.

Which stored outputs carry the string:

| File | Carries | Status |
|---|---|---|
| `data/frozen/design_support.json` | the old string, in 324 entries (80, 80, 84 and 80 over its four sets) | historical step E record; not rewritten |
| `data/frozen/design_support_current.json` | the new string, in the same 324 entries for the same units | current design summary, written 2026-11-19 after the edit |
| `data/frozen/inference_check.json` | none: its stored sets hold no `investor_owned_units_with_no_ownership_row` block | preserved result of 2026-11-14; not rewritten |
| `data/frozen/superseded/*` | none | superseded records; not touched |

## (c) No calculation behind a stored result changed

Every design was built twice from the quantity files, once before the edit and once after it, in separate processes. Each snapshot recorded, per design, the hosts with their cohorts, each host's matches in order, each host's eligible pool in the reference year, the dropped hosts with their reasons, and the `design_inputs` and `rules` component hashes (`outcome_analysis.design_hashes`). The two snapshots are identical for every design:

| Design | Hosts | design_inputs (before and after) |
|---|---|---|
| 2% headline_set, headline rules | 7 | b8515c35cba1 |
| 2% headline_set_with_the_ten_year_case, headline rules | 6 | d0bd87b0b760 |
| 2% every_cohort_utility, headline rules | 36 | 073871ef1eb8 |
| 2% headline_set_plus_hosts_unsettled_on_assignment, headline rules | 17 | e98127e4fd75 |
| 5% headline_set, headline rules | 5 | 7ea3fdcbf138 |
| 5% headline_set_with_the_ten_year_case, headline rules | 5 | 7ea3fdcbf138 |
| 5% every_cohort_utility, headline rules | 29 | 30cee8bca828 |
| 5% headline_set_plus_hosts_unsettled_on_assignment, headline rules | 11 | c5f756dde070 |
| 2% headline_set, unresolved-ownership sensitivity | 5 | 7f3b3ac5eb11 |
| 2% headline_set_with_the_ten_year_case, unresolved-ownership sensitivity | 5 | 7f3b3ac5eb11 |
| 2% every_cohort_utility, unresolved-ownership sensitivity | 31 | e6b8814813fa |
| 2% headline_set_plus_hosts_unsettled_on_assignment, unresolved-ownership sensitivity | 15 | cbfaba204e58 |
| 2% headline_set, affiliates readmitted | 7 | 414c5ef3e24d |
| 2% headline_set_with_the_ten_year_case, affiliates readmitted | 6 | f69e46069035 |
| 2% every_cohort_utility, affiliates readmitted | 37 | 12fd9a1c6beb |
| 2% headline_set_plus_hosts_unsettled_on_assignment, affiliates readmitted | 17 | 58e39bda4727 |

The `rules` component is `626514815103` for every design under the headline rules, before and after. Every hash in the table equals the one the ownership repair's assessment lists after that repair.

The current design summary was also written into scratch before and after the edit. The two differ in exactly three kinds of field, all strings or hashes: the 324 `consequence` strings, and in each of the four sets `fingerprint.of.code_version` and `fingerprint.sha256` (the code hash now covers the edited file). The support CSV is byte for byte the same before and after, and equals the historical `design_support.csv` (`6b7c7181...`).

## (d) Stored records that carry the old code hash and are not rewritten

`design.run_fingerprint` stores a `code_version` component, the sha256 of the hashes of `design.CODE_FILES`, which lists `pipeline/analysis/design.py`; `inference_comparison` uses `design.CODE_FILES` plus its own files. The raw hash of `design.py` therefore sits inside a component in these files, which all recorded a tree other than the live one already (the ownership repair and the label edit of 2026-11-19 had changed `ownership.py` and `power_simulation.py` since step E), and none is rewritten:

- the historical step E record and the step E results: `design_support.json` (4 fingerprints), `influence_on_quantities.json` (2), `power_simulation.json` (10), `inference_comparison_benchmark.json`, `inference_comparison_stage1.json`, `inference_validation_budget.json`, `inference_validation_stage2.json` (1 each);
- the superseded records under `data/frozen/superseded/design-before-stop3/`;
- other agents' and earlier sessions' summaries whose fingerprint includes a `code_version` component: `influence_deletions_design.json`, `size_band_design.json`, `timing_run_design.json`. Their calculations did not change by this edit; whether they are regenerated is the session's decision.

The raw sha256 of `design.py` before the edit (`71457777...`) appears verbatim in the `code_version` maps of `future_host_runs.json`, `inventory_run_designs.json` and `side_run_designs.json`. Those records are not rewritten by this agent; their designs are unchanged by this edit (section c covers the builders they use; the edit is not in any code they execute for a number).

Regenerated on 2026-11-19 after the edit, and so recording the new hash: `design_support_current.json` (new), `design_weights_provenance.json`, `customer_weighted_fit_design.json`, `influence_five_highest_load.json` and `prefreeze_quantity_summaries.json` (which records the fingerprints of the summary it read). In `customer_weighted_fit_design.json` and `influence_five_highest_load.json` the only fingerprint fields that moved are `fingerprint.of.code_version` and `fingerprint.sha256`.

A changed fingerprint alone neither requires a simulation rerun nor permits rewriting a preserved result. Nothing was rerun and nothing preserved was rewritten.

## (e) The inference comparison's guards and the kernel's validation claim afterwards

- The kernel. `outcome_analysis.read_validation_reference()` reads the `design_inputs` and `rules` components from the four step E files and from the historical `design_support.json`'s headline set (it still reads that file; `outcome_analysis.py` was not edited) and requires them to agree. `outcome_analysis._validation` compares a claimed design's recomputed `design_inputs` and `rules` with that reference. Neither reads `code_version`. Run after the edit on designs only, with no outcome: the headline set at 2% gives `passed: true`, "checked: the design's inputs and rules are those the procedure was validated on", the reference read from all five files (`b8515c35cba1`, `626514815103`); every cohort utility as built at 2% gives `passed: false`, "refused: the design's inputs ... differ from those of the validated design", as before this edit (it has differed since the ownership repair).
- The inference comparison's guards (`inference_comparison` stage 1, stage 2 and `run_blocks`) compare a whole stored fingerprint, `code_version` included, with a live one. They already refused after the label edit to `power_simulation.py` and after the ownership repair, and they still refuse. None was run, changed or disabled.
- `prefreeze_summaries.main`'s reproduction guard now compares the rebuilt designs with the current design summary, `design_support_current.json`, by name, under Joe's ruling of 2026-11-19. It passed for all four sets.

## (f) Not done

- `design.main` was not run, here or in a test: under the headline rules it would write the historical files (`design_support.json`, `design_support.csv`, `full_window_eligibility.csv`).
- `inference_check.main` was not run; `inference_check.json` is a preserved result.
- `conditions.main` was not run and `conditions_groups.json` was not regenerated (the session handles them).
- No stored fingerprint was edited to match the live tree.
