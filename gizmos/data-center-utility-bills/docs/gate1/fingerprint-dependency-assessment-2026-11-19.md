# Fingerprint dependency assessment, 2026-11-19

Written 2026-11-19 by a maintenance agent of the session, under Joe's ruling of that day, which says in part: "A fingerprint change alone does not require step E to run again where a documented dependency assessment establishes no effect on its calculations. Correct the inaccurate simulation label on that same basis, without changing calculations or rewriting preserved results."

Two fingerprinted code files were edited on 2026-11-19: `pipeline/analysis/power_simulation.py` (the `moments_are_over` label in three places and one docstring) and `pipeline/facilities/step_d_check.py` (the reference check now reads the exact attribution rerun on 2026-11-19, s18). Their sha256 no longer equals the hash recorded inside preserved results. This file establishes, from what was run on 2026-11-19, whether any calculation those results rest on changed. No stored fingerprint in any preserved result was rewritten. The only outputs regenerated that day by this work are `data/frozen/step_d_check_reference.json` (the reference check, against s18) and `data/frozen/design_weights.csv` with its new sidecar `data/frozen/design_weights_provenance.json`.

The scripts used for the checks below were run from the session's scratch folder and are not in the repository: an abstract-syntax-tree comparison with every string literal blanked, a search of the commit history for the tree that gives each stored `code_version` component, and an in-memory recomputation of each set's `design_inputs` component (quantities only; nothing written; no price read).

## (a) The two edited files

| File | sha256 at HEAD (61917d0) | sha256 after the edit |
|---|---|---|
| `pipeline/analysis/power_simulation.py` | `79d613647ff3d0563f9c046f09522ee4270c7d705287b61d6f4860d8ab5b5f4e` | `146043ef334387637a6015e7903e020749e6ba18aae8f1805da623c69b1894d7` |
| `pipeline/facilities/step_d_check.py` | `9eb97e8049b3785329e259597157668b71730c53921a3e78c8305399468eebc9` | `f87804b726d4a94c46ec41388de094844412bd192818ed102f9f87415b4ff385` |

### `pipeline/analysis/power_simulation.py`

The complete `git diff` against HEAD:

```diff
diff --git a/gizmos/data-center-utility-bills/pipeline/analysis/power_simulation.py b/gizmos/data-center-utility-bills/pipeline/analysis/power_simulation.py
index 47947c5..0d6de59 100644
--- a/gizmos/data-center-utility-bills/pipeline/analysis/power_simulation.py
+++ b/gizmos/data-center-utility-bills/pipeline/analysis/power_simulation.py
@@ -574,7 +574,11 @@ def summarise(rows: pd.DataFrame, scale: float = 100.0) -> dict:
         "smallest_effect_detected_in_80pct_of_draws": pct(smallest_detectable(rows.est.values, half_lo)),
         "clusters_median": int(rows.clusters.median()),
         "numerical_failures": failure_summary(rows),
-        "moments_are_over": "draws without a numerical failure; every rate counts a failed draw as a miss (D-95 item 7)",
+        "moments_are_over": ("each mean, standard deviation and median is over the draws whose value for it is not NaN (pandas "
+                             "skips NaN and nothing else). A failed draw keeps what it computed: its estimate enters the mean and "
+                             "standard deviation of estimates, and its standard error the mean standard error, unless NaN. Its "
+                             "range is NaN whenever its bootstrap or its standard error is not finite, and then it is left out "
+                             "of the range widths, does not cover zero, and never detects in the smallest effect (D-95 item 7)"),
     }
 
 
@@ -1387,8 +1391,12 @@ def read_draws(draws: list[dict], hosts: int, procedure: str = AS_BUILT) -> dict
 
     Power at a planted effect is the share of draws whose 90% range lies entirely above zero (`POWER`, adopted on
     2026-11-18 after the results were available); the smallest planted effect at which it reaches 80% is the "smallest
-    increase detected in the correct direction four times in five" (SMALLEST_INCREASE_KEY). Moments (means, standard deviations) exist only for draws that computed, and are
-    labelled as such: a failed draw has no estimate to average.
+    increase detected in the correct direction four times in five" (SMALLEST_INCREASE_KEY). Moments (means, standard
+    deviations, medians) are pandas reductions, which skip NaN and nothing else, and are labelled as such: a draw that
+    failed before an estimate existed (failed_reading: a rank-deficient fit, or under C a design failure) is NaN
+    everywhere and is left out of every moment; a draw that failed after its estimate was computed keeps its estimate,
+    and its standard error unless that is NaN, in the moments, while its range is NaN and is left out of the range widths.
+    Every failed draw is counted in the failure counts and in every rate's denominator.
     """
     pct = lambda x: round(100.0 * float(x), 3)  # noqa: E731
     zero = pd.DataFrame([d["exact"][0] for d in draws])
@@ -1404,7 +1412,12 @@ def read_draws(draws: list[dict], hosts: int, procedure: str = AS_BUILT) -> dict
            "rates_include_numerical_failures": True,
            "power": dict(POWER),
            "nothing_planted": {
-               "moments_are_over": "draws without a numerical failure",
+               "moments_are_over": ("every draw whose value for the moment is not NaN (pandas skips NaN and nothing else). A draw "
+                                    "that failed before an estimate existed has none and is left out. A draw that failed after its "
+                                    "estimate was computed keeps its estimate and its standard error in these moments, each unless "
+                                    "it is NaN; its range is NaN, so it is left out of the range widths. Every failed draw is counted "
+                                    "as a failure, as a range that misses zero, as an early-years test that rejects and as no "
+                                    "detection"),
                "mean_estimate": pct(zero.est.mean()), "sd_of_estimates": pct(zero.est.std()), "mean_standard_error": pct(zero.se.mean()),
                "range_half_width_mean": pct((zero.hi - zero.lo).mean() / 2), "range_width_median": pct((zero.hi - zero.lo).median()),
                "range_covers_zero": round(float(covers.mean()), 3),
@@ -1846,7 +1859,12 @@ def run_second_number(q: pd.DataFrame, dose: pd.DataFrame, clean: pd.DataFrame,
             hx = per_point_frame(name, hd, hd)[0]
             dev = np.sort((hx.max(1) - hx.max(1).mean()) ** 2)[::-1]
             d["uncapped" if cap is None else f"capped_at_{cap:.0f}_points"] = {
-                "numerical_failures": failure_summary(base), "moments_are_over": "draws without a numerical failure",
+                "numerical_failures": failure_summary(base),
+                "moments_are_over": ("every draw whose value for the moment is not NaN (pandas skips NaN and nothing else). A draw "
+                                     "that failed before an estimate existed (a rank-deficient fit) has none and is left out. A draw "
+                                     "that failed after its estimate was computed keeps its estimate, unless NaN, in the mean "
+                                     "estimate; its range is NaN, so it is left out of the range widths. Every failed draw is "
+                                     "counted as a failure and as a range that does not cover zero"),
                 "mean_estimate_nothing_planted": round(100 * float(base.est.mean()), 4),
                 "range_half_width_mean": round(100 * float((base.hi - base.lo).mean() / 2), 4),
                 "range_covers_zero": round(float(((base.lo <= 0) & (base.hi >= 0) & ~failed(base)).mean()), 3),
```

Line by line:

- Hunk 1 (`summarise`, about line 577): the value of the `moments_are_over` key, a string literal, is replaced by another string literal (split over five lines inside parentheses, which Python joins into one string). The key name is unchanged.
- Hunk 2 (`read_draws`, docstring): docstring lines only.
- Hunk 3 (`read_draws`, the `nothing_planted` dictionary): the value of `moments_are_over`, a string literal, replaced by another string literal. The key name is unchanged.
- Hunk 4 (`run_second_number`): the line that held both `"numerical_failures": failure_summary(base)` and the `moments_are_over` entry is split in two. The first entry is unchanged in key and value (moved to a line of its own); the second entry's value, a string literal, is replaced by another. The key name is unchanged.

Evidence beyond reading: the old and new files parse to the same syntax tree once every string literal is blanked (comments are not part of the tree). No name, operator, call, argument, key, branch or number differs. `python3 -I pipeline/analysis/pool_restrictions.py --check` printed "the ledger's transcription matches the sources" before and after the edit; none of the edited functions is transcribed in the ledger.

### `pipeline/facilities/step_d_check.py`

The complete `git diff` against HEAD:

```diff
diff --git a/gizmos/data-center-utility-bills/pipeline/facilities/step_d_check.py b/gizmos/data-center-utility-bills/pipeline/facilities/step_d_check.py
index 0894178..e5f10f2 100644
--- a/gizmos/data-center-utility-bills/pipeline/facilities/step_d_check.py
+++ b/gizmos/data-center-utility-bills/pipeline/facilities/step_d_check.py
@@ -5,12 +5,17 @@ Load and sales only. Writes data/frozen/step_d_check.json and exits 1 on anythin
   reproduce   after `apply_verified.py --no-pass-records` and `build_inventory.py --no-step-d`: every inventory file
               must equal the snapshot of 2026-11-14 exactly (the claim "with no corrections the rebuild reproduces the
               frozen inventory").
-  reference   after the corrected build: every utility whose exact reference is defined in
-              docs/gate1/expansion-test-2026-11-18-s17.json must show that place and first crossing at 2% on the
-              rebuilt inventory as built. Legitimate differences, each traced to a named site: a coordinate correction
-              (the pass never modelled location), a map-placed site the rerun moved (Joe, R5), a convention entered after
-              the run (the corrections in force against the s17 file), a utility a LOAD UNKNOWN site reaches (compared
-              through timing.py's enumerated reference instead of the frame), a load within 1e-9 of a threshold.
+  reference   after the corrected build: every utility whose exact reference is defined in the reference attribution
+              must show that place and first crossing at 2% on the rebuilt inventory as built. The reference attribution
+              is docs/gate1/expansion-test-2026-11-19-s18.json, the exact attribution rerun on 2026-11-19 on the
+              corrections in force (66 entries, pipeline/facilities/verified/pass_c_corrections_s17.json) by
+              pipeline/facilities/pass_c_exact_s18.py. Until 2026-11-19 the reference was
+              docs/gate1/expansion-test-2026-11-18-s17.json, built on an earlier state of that corrections file.
+              Legitimate differences, each traced to a named site: a coordinate correction (the pass never modelled
+              location), a map-placed site the rerun moved (Joe, R5), a convention entered after the reference run (the
+              corrections in force against the corrections file the reference attribution was built on), a utility a
+              LOAD UNKNOWN site reaches (compared through timing.py's enumerated reference instead of the frame), a load
+              within 1e-9 of a threshold.
               Also: every batch_c site the corrections do not assign or reopen is on its snapshot utility.
 
 Run:  python3 -I pipeline/facilities/step_d_check.py reproduce
@@ -37,8 +42,10 @@ from pipeline.facilities import pass_c_expand as px  # noqa: E402
 INTERIM = ROOT / "data" / "interim"
 FROZEN = ROOT / "data" / "frozen"
 SNAPSHOT = INTERIM / "snapshot-2026-11-14"
-EXACT = ROOT / "docs" / "gate1" / "expansion-test-2026-11-18-s17.json"
-S17 = cx.VER / "pass_c_corrections_s17.json"
+EXACT = ROOT / "docs" / "gate1" / "expansion-test-2026-11-19-s18.json"     # the reference attribution (s18, 2026-11-19)
+# The corrections file the reference attribution was built on: the s18 run read this file with its 66 entries, the
+# corrections in force. A correction that differs from this file's entry was entered after the reference run.
+REFERENCE_CORRECTIONS = cx.VER / "pass_c_corrections_s17.json"
 INVENTORY_FILES = ("facilities.parquet", "facility_year.parquet", "utility_year_dose.parquet", "state_anchor.parquet",
                    "state_load_by_year.parquet", "epoch_gaps.parquet")
 MAP_KINDS = ("unique", "smallest_polygon", "next_larger_load_feasible", "fallback_largest_flagged")
@@ -81,9 +88,12 @@ def _margin(gwh, base_k, theta) -> float:
     return float(np.min(np.abs(gwh / base_k - theta)) / theta)
 
 
-def explained(rebuilt: pd.DataFrame, snap: pd.DataFrame, report: dict, corrections: list[dict], s17: list[dict],
+def explained(rebuilt: pd.DataFrame, snap: pd.DataFrame, report: dict, corrections: list[dict], reference_corrections: list[dict],
               unknown: set) -> dict:
-    """utility -> the named reasons a difference from the s17 reference is legitimate."""
+    """utility -> the named reasons a difference from the reference attribution is legitimate.
+
+    `reference_corrections` is the corrections list the reference attribution was built on (REFERENCE_CORRECTIONS for
+    the s18 reference); a correction in force that differs from its entry there was entered after the reference run."""
     why: dict[str, list[str]] = {}
 
     def add(st, utilities, reason):
@@ -102,11 +112,11 @@ def explained(rebuilt: pd.DataFrame, snap: pd.DataFrame, report: dict, correctio
         add(rebuilt.state[f], [u for u in (snap.utility_id_eia[f], rebuilt.utility_id_eia[f]) if pd.notna(u)],
             f"{f}: moved by the map rerun (Joe, R5)")
     key = lambda c: (c["fid"], c["kind"])  # noqa: E731
-    old = {key(c): {k: v for k, v in c.items() if k != "why"} for c in s17}
+    old = {key(c): {k: v for k, v in c.items() if k != "why"} for c in reference_corrections}
     for c in corrections:
         if old.get(key(c)) != {k: v for k, v in c.items() if k != "why"}:
             st = rebuilt.state.get(c["fid"])
-            add(st, [u for u, s in {k for k in _units_in(rebuilt, st)}], f"{c['fid']}: a correction entered after the s17 run")
+            add(st, [u for u, s in {k for k in _units_in(rebuilt, st)}], f"{c['fid']}: a correction entered after the reference run")
     for u in unknown:
         why.setdefault(u, []).append("a LOAD UNKNOWN site reaches it: compared through the enumerated reference (Joe, R2)")
     return {"by_utility": why, "moved_by_the_map": moved}
@@ -128,7 +138,7 @@ def reference_check(corrections_path: Path) -> dict:
     timing = {r["utility"]: r for r in json.loads((FROZEN / "timing_place_test.json").read_text())["utilities"]
               if abs(r["theta"] - 0.02) < 1e-12}
     corrections = cx.load(corrections_path)
-    ex = explained(fac, snap, report, corrections, json.loads(S17.read_text()), unknown)
+    ex = explained(fac, snap, report, corrections, json.loads(REFERENCE_CORRECTIONS.read_text()), unknown)
     got = places(fac, fy)
     rows, unexplained = [], []
     for st, s in exact.items():
@@ -147,7 +157,7 @@ def reference_check(corrections_path: Path) -> dict:
             reasons = list(ex["by_utility"].get(u, []))
             if mine["margin"] < 1e-9:
                 reasons.append("a load within 1e-9 of the threshold")
-            r = {"utility": u, "s17_reference": {"place": ref["place"], "crossing": ref["crossing"]}, "rebuilt": mine,
+            r = {"utility": u, "reference": {"place": ref["place"], "crossing": ref["crossing"]}, "rebuilt": mine,
                  "explained_by": reasons}
             rows.append(r)
             if not reasons:
@@ -164,7 +174,11 @@ def reference_check(corrections_path: Path) -> dict:
             a, b = snap.utility_id_eia[f], fac.utility_id_eia[f]
             if not ((pd.isna(a) and pd.isna(b)) or a == b) and f not in report.get("locations_corrected", {}):
                 off.append({"site": f, "snapshot_utility": a, "rebuilt_utility": b})
-    return {"differences": rows, "unexplained": unexplained, "moved_by_the_map": ex["moved_by_the_map"],
+    return {"reference_attribution": {"file": str(EXACT.relative_to(ROOT)),
+                                      "built_on_corrections": str(REFERENCE_CORRECTIONS.relative_to(ROOT)),
+                                      "what": "the exact attribution rerun on 2026-11-19 on the corrections in force (s18); "
+                                              "each difference's `reference` is that attribution's place and first crossing at 2%"},
+            "differences": rows, "unexplained": unexplained, "moved_by_the_map": ex["moved_by_the_map"],
             "batch_c_sites_off_their_snapshot_utility": off}
 
 
```

Line by line:

- Hunk 1: module docstring lines only (which attribution is the reference, and what the guard for later corrections compares).
- Hunk 2: `EXACT`, a path constant, now names `docs/gate1/expansion-test-2026-11-19-s18.json` in place of `...-2026-11-18-s17.json`, with a comment. The constant `S17` is renamed `REFERENCE_CORRECTIONS`; its value is the same path, `pipeline/facilities/verified/pass_c_corrections_s17.json`, with a two-line comment. Nothing else imported `S17` (searched `pipeline/` and `tests/`).
- Hunk 3: in `explained`, the parameter `s17` is renamed `reference_corrections` (positional, and every caller passes it by position), and the docstring is rewritten.
- Hunk 4: in `explained`, the loop reads the renamed parameter; the reason string "a correction entered after the s17 run" becomes "a correction entered after the reference run".
- Hunk 5: `reference_check` passes the renamed constant.
- Hunk 6: in each difference row the key `s17_reference` becomes `reference` (wording; no code reads `step_d_check_reference.json`: searched every `.py`, `.md`, `.json`, `.csv`, `.txt` and `.yml` file of the gizmo folder outside the excluded folders, and the file is named only in `HANDOVER_step_g_2026-11-18.md` and `docs/gate1/referee-read-2026-11-19.md`, which describe it).
- Hunk 7: `reference_check` adds one key to its output, `reference_attribution`, which names the attribution file and the corrections file it was built on. The comparison logic, the guard and the exit rule are unchanged.

This file's syntax tree, with strings blanked, differs from HEAD in exactly the two renamed constant assignments, `explained` (the renamed parameter) and `reference_check` (the renamed constant, the renamed row key is a string, and the added `reference_attribution` entry with its two `relative_to` calls). These are wording and a path constant, as the brief allowed, plus the one added output key. The rename and the added key are more than string edits and are listed here so that nothing is smoothed.

The guard for corrections "entered after the reference run": `explained` compares the corrections in force with the corrections file the reference attribution was built on, by (`fid`, `kind`), ignoring `why`. The s18 attribution was built on `pass_c_corrections_s17.json` with its 66 entries, which is the file in force (`corrections.CORRECTIONS`) and the file `S17` already named. So the path did not change; only its name and wording did. With the default `--corrections`, the guard compares the file with itself and flags nothing, which is correct now that the reference was built on that same file. It was not correct while the reference was the s17 attribution: the s17 attribution was built on an earlier state of that file, before the five Oregon entries of commit 307c3ca, and the guard then also compared the file with itself. The agent's reading: the guard would only become meaningful again if the corrections file changed after the s18 run, and since it compares against the live file rather than a copy pinned at the s18 run's hash, it would not see such a change. The record of which file state the s18 run used is the commit (61917d0) and the corrections file's hash in `step_d_check_reference.json` (`724d08ce...`). No logic was changed for this; it is reported.

The reference check was rerun on 2026-11-19 (`python3 -I pipeline/facilities/step_d_check.py reference`; the reproduce mode was not run). Differences: none. Unexplained: none. Sites moved by the map: none. batch_c sites off their snapshot utility: none. The s18 file defines a reference for 3,145 utilities, as the s17 file did. Against the file it replaced, the new `step_d_check_reference.json` differs in the added `reference_attribution` key and in two fingerprint entries: the attribution file (s18, `25761f28...`, in place of s17, `29106878...`) and `step_d_check.py` (`f87804b7...`). Every other recorded hash (the corrections file, the other twelve step D code files, the six inventory files and the six snapshot files) is unchanged.

## (b) Preserved files that record a hash of either file

How the hashes are recorded:

- `design.run_fingerprint` writes, per run, a sha256 for each of six components (`design_inputs`, `rules`, `code_version`, `assumptions`, `settings`, `seeds`). `code_version` is the sha256 of a dictionary of file hashes for `design.CODE_FILES`, which lists `pipeline/analysis/power_simulation.py`. `inference_comparison.comparison_fingerprint` uses `design.CODE_FILES + inference_comparison.OWN_FILES`. The raw hash of `power_simulation.py` is therefore inside a component and does not appear in any file: a search of `data/frozen/*.json` and `data/frozen/superseded/` for `79d61364...` found nothing.
- `corrections.fingerprint` writes each file's raw sha256 in a `files` map. `corrections.code_files()` lists `step_d_check.py`. A search for `9eb97e80...` found it in the files below.

Files whose `code_version` component covers `power_simulation.py` (the component was matched to commits by recomputing it from the committed blobs of each of the last 80 commits that touched `pipeline/`):

| File | Fingerprints in it | Stored `code_version` | Tree it equals | Produced by |
|---|---|---|---|---|
| `data/frozen/design_support.json` | 4, one per set | `5b1864bde1...` | HEAD 61917d0 (same component since 307c3ca) | `design.main`, step E's design and support |
| `data/frozen/influence_on_quantities.json` | 2, headline and ten-year sets | `5b1864bde1...` | the same | `influence.main`, step E's rule 7 deletions on quantities |
| `data/frozen/power_simulation.json` | 10 (new-host estimate at 2% and 5%, the early-years size check, the same-state side runs) | `5b1864bde1...` | the same | the simulation, `power_simulation.main` |
| `data/frozen/inference_comparison_benchmark.json` | 1 | `131077f03b...` | HEAD 61917d0 (same since 307c3ca) | `inference_comparison`, the benchmark |
| `data/frozen/inference_validation_budget.json` | 1 | `131077f03b...` | the same | `inference_comparison`, the validation budget |
| `data/frozen/inference_comparison_stage1.json` | 1 | `131077f03b...` | the same | stage 1 |
| `data/frozen/inference_validation_stage2.json` | 1 | `131077f03b...` | the same | stage 2 |
| `data/frozen/superseded/design-before-stop3/power_simulation.json` | 10 | `9473a21688...` | commit ace9a81 | superseded simulation |
| `data/frozen/superseded/design-before-stop3/inference_comparison_stage1.json`, `.../inference_validation_stage2.json` | 1 each | `77760a270c...` | commit 37218ae | superseded stages 1 and 2 |

For every current file in that table, the stored `code_version` equals the component computed from the HEAD tree, and the only file of the fingerprinted set whose live hash differs from HEAD is `power_simulation.py`. The live components are `00465ab94d...` (design.CODE_FILES) and `219ec28d2e...` (with OWN_FILES). The three superseded files already differed from the tree before 2026-11-19 in four or five files (design.py, power_simulation.py, inference_check.py, ownership.py, and influence.py for stages 1 and 2); they are superseded records and are not assessed further. `data/frozen/inference_check.json` carries no fingerprint in its sets.

`data/frozen/design_weights_provenance.json`, written on 2026-11-19 after both edits, records the live tree (its `code_version` also covers `pipeline/analysis/design_weights.py`).

Files that record the raw hash of `step_d_check.py` (`9eb97e80...`), all in a `corrections.fingerprint` `files` map:

| File | Produced by (step D) |
|---|---|
| `data/frozen/inventory_report.json` | `build_inventory.py` (the step D rebuild), in `step_d.fingerprint` |
| `data/frozen/unknown_load_sites_and_affected_utilities.json` | `build_inventory.py` |
| `data/frozen/timing_place_test.json` | `timing.py` |
| `data/frozen/timing_ceiling_per_screen_case_comparison.json` | `timing.py`, labelled comparison |
| `data/frozen/timing_oregon_looser_reading_comparison.json` | `timing.py`, labelled comparison |
| `data/frozen/treatment_bounds.json` | `treatment_bounds.py`; twice, in its own fingerprint and in the copy of timing's fingerprint it carries |
| `data/frozen/dating_sensitivity.json` | `dating_sensitivity.py` |
| `data/frozen/ten_year_screen.json` | `ten_year.py` |
| `data/frozen/later_start_sensitivity.json` | `later_start.py` |
| `data/frozen/step_d_check_reproduce.json` | `step_d_check.py reproduce`, 2026-11-18 (see (f)) |

`data/frozen/step_d_check_reference.json` recorded it too and was regenerated on 2026-11-19 with the new hash (job 2).

## (c) Step E's files and the simulation's

The `design_inputs` component was recomputed in memory for each set at 2% under the headline rules, building each design as `design.main` does (`design.load`, `usable_flag.read`, `ps.rule_inputs`, `ps.ownership_classes`, `ps.load_unknown_load`, `design.split`, `design.build_with_rules`), and for the simulation's sets as `power_simulation.main` builds them (`ps.design` with `history_settled`, the comparison pool restricted to the committed access list by `restrict_to_access_list`, `set_aside`, then `simulation_hosts`), at 2% and at 5%. Quantities only; no price file was opened and nothing was written.

| Stored fingerprint | Stored `design_inputs` | Live | Equal |
|---|---|---|---|
| `design_support.json`, headline_set | `b8515c35cba1` | `b8515c35cba1` | yes |
| `design_support.json`, headline_set_with_the_ten_year_case | `d0bd87b0b760` | `d0bd87b0b760` | yes |
| `design_support.json`, every_cohort_utility | `2e3d2f599bd4` | `2e3d2f599bd4` | yes |
| `design_support.json`, headline_set_plus_hosts_unsettled_on_assignment | `e98127e4fd75` | `e98127e4fd75` | yes |
| `influence_on_quantities.json`, headline_set | `b8515c35cba1` | `b8515c35cba1` | yes |
| `influence_on_quantities.json`, headline_set_with_the_ten_year_case | `d0bd87b0b760` | `d0bd87b0b760` | yes |
| `power_simulation.json`, 2% headline_set (new-host estimate, early-years check, same-state side run) | `b8515c35cba1` | `b8515c35cba1` | yes |
| `power_simulation.json`, 2% every_cohort_utility (the same three) | `3b4dfbd4992e` | `3b4dfbd4992e` | yes |
| `power_simulation.json`, 2% headline_set_with_the_ten_year_case (two entries) | `d0bd87b0b760` | `d0bd87b0b760` | yes |
| `power_simulation.json`, 5% headline_set | `7ea3fdcbf138` | `7ea3fdcbf138` | yes |
| `power_simulation.json`, 5% every_cohort_utility | `53ce02f3970c` | `53ce02f3970c` | yes |
| the four `inference_comparison` / `inference_validation` files (headline set) | `b8515c35cba1` | `b8515c35cba1` | yes |

The simulation's every_cohort_utility inputs differ from `design_support.json`'s for the same set (`3b4dfbd4992e` against `2e3d2f599bd4`) because the simulation restricts the comparison pool to the access list (1,626 eligible units left out at each threshold); both reproduce exactly with their own construction.

The `rules` component is equal everywhere (`626514815103`). For `design_support.json` and `influence_on_quantities.json` the whole fingerprint was recomputed on the live tree with the assumptions and settings their `main` functions pass: in each of the six, the only component that differs is `code_version`. For the simulation and the comparison files, `assumptions`, `settings` and `seeds` were not recomputed (they need the run's processes, grids and seeds, which the agent did not rebuild); `design_inputs` and `rules` were compared and are equal, and `code_version` differs only by `power_simulation.py`, as shown in (b).

What the label edit can reach in the simulation's output: only the three `moments_are_over` strings, written as output fields by `summarise`, `read_draws` and `run_second_number`. A search of every `.py` file in the gizmo folder (outside the excluded folders) for `moments_are_over` finds it written at those three places and at `inference_check.py` line 211, and read only in `tests/test_numerical_failures.py`. No code reads the field to compute anything, and no number in any output is computed from it. The docstring edit is not executed.

## (d) Step D's files

`step_d_check.py` is in `corrections.code_files()`, so every step D output records its hash. No step D builder imports or executes it: a search of `pipeline/` for `step_d_check` finds only the module itself and three mentions in `corrections.py` (the `code_files` list and two comments), and no builder starts it as a subprocess (the only `subprocess` uses in `pipeline/facilities` and `pipeline/analysis` are `pdftotext` in `site_energy.py` and `git` in `simulation_access_list.py`). No step D output's content depends on it; each records its hash only. The step D outputs listed in (b) were not regenerated.

## (e) Conclusions

- Step E and the simulation (`design_support.json`, `influence_on_quantities.json`, `power_simulation.json`, the benchmark, the budget, stage 1, stage 2): no calculation changed; the recorded fingerprint is of the code as it stood when the result was produced; the live tree differs in the lines shown in (a) for `power_simulation.py`, which are string literals and a docstring, and every result's `design_inputs` recomputes equal.
- Step D (`inventory_report.json`, `unknown_load_sites_and_affected_utilities.json`, `timing_place_test.json`, the two timing comparisons, `treatment_bounds.json`, `dating_sensitivity.json`, `ten_year_screen.json`, `later_start_sensitivity.json`): no calculation changed; the recorded fingerprint is of the code as it stood when the result was produced; the live tree differs in the lines shown in (a) for `step_d_check.py`, a module none of these builders runs.
- `step_d_check_reference.json`: regenerated on 2026-11-19 against s18; it records the new hashes. Its calculation changed in what it compares against (the s18 attribution in place of s17), as Joe ruled; the comparison logic did not change.
- Guards that compare a stored fingerprint with a live one (none was disabled or changed): `inference_comparison.stage1` refuses when the benchmark's or the budget's fingerprint differs from the live comparison fingerprint; `inference_comparison.stage2` refuses when stage 1's differs (and refuses anyway because its output exists); `inference_comparison.run_blocks` refuses to resume a block run whose manifest fingerprint differs. Each live fingerprint includes `power_simulation.py` through `design.CODE_FILES`, so after the label edit each of these would refuse if run; before it, the live component equalled the stored one. Nothing is to be run now, and the rule the ruling quotes leaves a rerun to a documented assessment, which this is. `power_simulation`'s check of the selected procedure compares stage 1's stored fingerprint with stage 2's stored fingerprint, not with the live tree, so the edits do not trip it. `availability_adapter.reopen_reasons` compares the availability screen's five fingerprints (corrections, candidates, dependencies, mask identity, eligibility rules), none of which is a code hash; the edits do not reach it. No guard in `influence.py`, `timing.py`, `treatment_bounds.py` or the other step D builders compares a stored fingerprint with a live one; they only record.

## (f) The reproduction check's output

`data/frozen/step_d_check_reproduce.json` is a historical record of the reproduction check as run on 2026-11-18 (commit a715f0f): with no corrections, the rebuild reproduced the 2026-11-14 snapshot in all six inventory files. Of the 27 hashes it records, 11 were not the tree's before 2026-11-19 (the corrections file, five step D code files and the five live inventory files the corrected rebuild has since replaced); with the edit of `step_d_check.py` it is 12. Nothing in the design reads it: a search of every `.py`, `.md`, `.json`, `.csv`, `.txt` and `.yml` file of the gizmo folder (outside `data/blind`, `data/interim/availability`, the water folders, the snapshot folder, `.git`, `docs/DECISIONS.md` and `docs/prior-work-detail.md`, none of which was opened) for `step_d_check_reproduce` finds it named only in `PREANALYSIS.md`, `HANDOVER.md`, `HANDOVER_step_g_2026-11-18.md` and `docs/gate1/referee-read-2026-11-19.md`, all of which describe it; no code opens it. It is not regenerated, because that needs an inventory build with no corrections over the working inventory, which Joe's ruling does not ask for. Its bytes were checked unchanged after the work of 2026-11-19 (`905ef290...`).
