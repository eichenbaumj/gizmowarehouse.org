# Freeze readiness and analysis readiness, assessed from code only (2026-11-20)

Written 2026-11-20 by session 25 (job 6), under Joe's ruling of that day on D-114 (D-115, item 6): "Distinguish freeze readiness from analysis readiness. The final package must identify the bounded work still needed to connect the outcome reader and execution flow after authorization; the current outcome gate remains deliberately unimplemented. Assess and describe that work from code only. Do not enable outcome access or perform that execution work in this session. Preserve the recorded order of unblinding, beginning with U and C."

**How it was made.** A read-only agent (claude-opus-5-5) read the code and ran nothing. The session then read the door, the panel's reader, the order of unblinding, the registry's `run`, the validation check and the inventory check's guard itself, and found them as the agent described. Nothing was run on outcomes, no environment variable was set, no gate file was created, nothing under `data/blind` was opened, listed or checked, and nothing in the gate was edited. Line numbers below are of `run_outcomes.py` as commit `54a90f9` left it and of the other modules as they stood on the morning of 2026-11-20; later edits of the session moved some of them, so each statement also names its function. The plan is a draft pre-analysis plan, not frozen and not registered with anyone outside. Readings that are not the code's or the plan's are marked.

## Two kinds of readiness

**Freeze readiness** is what must be true before Joe can freeze the plan. From the code, that is the plan's list "Required before the freeze" and nothing else. The registry now carries no built entry with a stopped step (`run_outcomes.registry_document`: `built_entries_with_stopped_steps` is 0 since this session). The only test of the freeze anywhere in the code is whether one file exists (section 1).

**Analysis readiness** is what must be built after the freeze and before any outcome is read. The code says plainly that it is not there. `run_outcomes.load_outcomes_after_the_freeze` ends in `NotImplementedError("outcome execution is authorized and wired after the freeze")`, and the registry's document says that "built" means the builder and the estimator compose on invented inputs, nothing more. Sections 2 to 7 describe that work. None of it was done, and none of it is recommended before the freeze.

## 1. Creating `GATE1_SIGNED` and committing the plan as frozen (Joe's)

- **Path and name.** `pipeline/electricity/panel.py` sets `ROOT` to the gizmo folder and `GATE_FILE = ROOT / "GATE1_SIGNED"` (lines 76 and 81). The file is `gizmos/data-center-utility-bills/GATE1_SIGNED`, with no extension. The reader's message says "at the repo root", which is loose wording for the gizmo folder (the session's reading of the path).
- **Contents.** Never read. Every check is whether the file exists (`run_outcomes.load_outcomes_after_the_freeze`; `inventory_against_sales._gate`; `panel.load_outcomes`). An empty file passes. Nothing ties the file to a commit, to the plan's text or to a person.
- **Git.** The folder's `.gitignore` has no line for it, so it can be committed. None exists today.
- **What the file unlocks by itself, which matters.** With the file present, `panel.load_outcomes` called with any purpose other than its two exempt ones returns the whole outcome file, with no second condition (lines 397 to 402). Only `load_outcomes_after_the_freeze` and `inventory_against_sales._gate` also require the environment variable `DCUB_OUTCOME_RUN_AUTHORIZED` to be `1`. So creating the file is the moment the panel's own reader opens to any caller. The door of section 2 should exist and be tested before the file does (the session's recommendation on order; it changes no rule).

## 2. The outcome door

**Today** (`run_outcomes.load_outcomes_after_the_freeze`): no gate file, it raises `OutcomeAccessRefused`; the environment variable not `1`, it raises `OutcomeAccessRefused`; otherwise `NotImplementedError`. It takes no argument, opens no file and never calls the panel's reader. Its test replaces the gate file's path and checks all three.

**What the panel's reader offers** (`panel.load_outcomes`):

- `purpose="power_simulation"` requires a list of units, opens one file per named unit, has no gate of its own and silently skips a named unit with no file. Its sanctioned caller is `power_simulation.read_listed_outcomes`, which checks the access list first.
- `purpose="construction_qa"` returns the whole file with no gate.
- Any other purpose raises unless the gate file exists, then returns the whole outcome file.
- The outcome file's columns are `utility_id_eia`, `state`, `year`, `res_revenue_full`, `res_price` (cents per kWh), `res_price_delivery_only`, `res_price_default_service`, `res_bill_per_customer_month`, `res_kwh_per_customer_month` and `energy_price_state`. Residential customers are a quantity column. `panel.py` is fingerprinted, so the door is new code that calls this reader as it stands.

**The work, bounded.**

1. *One door function* in place of the `NotImplementedError`. It keeps both refusals, calls the gated reader with a named post-freeze purpose, and never passes either exempt purpose and never calls `read_listed_outcomes`. It should also refuse a read when the frozen plan is not committed, which no code checks today. Its tests replace the gate file's path and the reader with invented ones, as the existing test does, and include a test that no exempt purpose can be passed.
2. *One reshaper* from the outcome file into the seven frames the registry takes (`utility_id_eia`, `state`, `year`, `value`), one per named outcome: the log residential price; the default-service price and the delivery-inclusive price as levels for row U, which logs them itself; row C's price in cents, real 2024 dollars; kWh per residential customer; bill per customer; and residential customers, which comes from the quantity file and needs no outcome read. Tests on invented frames for each column, type and duplicate. **Three elements the code marks as not stated, each Joe's and not chosen here:** the scale and transformation of the kWh and bill outcomes (`run_outcomes._other_outcome` says "scale and transformation are not stated in the plan"); which nominal price column row C deflates (the code fixes the deflator and not the column); and the ownership-class pick for rows U and C, which the registry's text calls open while the quantity summaries use the last reported type.
3. *An assembler of `RunInputs` from real quantity files.* None exists; the only constructions are in the test file. It follows each module's `main` (section 3).
4. *A results writer.* `run_all` returns a dictionary and nothing writes it, and nothing records the frozen commit, the gate file, a hash of the outcome file or the interpreter. The writer is also where the order of unblinding becomes real (section 5).

One whole-file read covers every entry: rows U and C take every panel unit-year in their windows and filter their own samples, and the stacked runs read only their design's stacked rows (`outcome_analysis.outcome_vector`). The door must not fill a frame the kernel would refuse (a missing column, a duplicate unit-year, a missing unit-year or a value that is not finite all stop in `outcome_analysis._vector_for_rows`).

## 3. How `RunInputs` is filled on real inputs

`RunInputs` has two required fields, `side` and `sets`, and 26 optional ones. A runner that fetches a missing optional field raises `MissingInput`, and `run` records that in words.

- `side` is built as `side_runs.main` builds it: `design.load()`, `usable_flag.read()`, `power_simulation.rule_inputs`, `load_unknown_load` and the names. `sets` are `design.split` at 2% and 5% for the four sets; the 1% set refuses unless the D-34 table and the price hold are passed.
- **The registry has 58 entries: 54 built, 3 with no code, 1 out of scope for this freeze.** 57 are in the executable order.
- **Entries that need something from the caller, by the registry's own field: 10** (`built_entries_with_needs` in the stored registry): rows U and C, the inventory against sales, the timing run, the second number's two single-form runs and its two sensitivity scenarios, Callaway and Sant'Anna, and the side-by-side table of estimators. The handover of this session said 11; the code and the stored registry give 10, and what the 11 counted was not established. I am uncertain about this.
- **By what the runners actually fetch** (the agent's count, not recounted by the session): 25 built entries raise `MissingInput` when an optional field is absent. They are rows U and C, the inventory against sales, the timing run, the seven second-number runs, the supplier exercise, the three later starts, Callaway and Sant'Anna, future hosts as comparisons, E2, E4a, E4b, E5, E6, the two E7 runs and condition 4.
- **`catches_drift`** comes from `run_outcomes.catches_drift_from_file`, which reads `data/frozen/early_years_drift_selected_procedure.json` by name, refuses a file whose design-inputs hash, seed, drift or outcome is not the exercise's, and gives a value for the headline set alone. Nothing calls it; the caller passes its value. Every other main set gets the "not chosen" sentence by design, and an empty result is a fact to report and not a success.
- **Row U's flags** come from `short_form_filers.adopted_row_u_flags(frame, table, flags, step_window=...)` under `reconciliation_mu.ryu_spec("unit_years_filed")`, with the filer table and the 2019 flags file already on disk. **The frame has to cover every outcome unit-year that reaches the Short Form filter,** in the step's own window, with no unit-year repeated. `reconciliation_mu._u_drop_short_form` raises on any outcome unit-year with no row or a missing value in the flags, and the registry records the step as not computed, in words. Whether a frame built on the quantity side covers every outcome unit-year cannot be shown before outcomes are read; it is tested on invented inputs only. The safest frame is the quantity-side frame before the three-year count, over the step's window. Step U3 runs on 2015 to 2025, and the session's reading of the rule for that extra year is in the plan and is Joe's to strike.
- **E4a, E4b, the later starts and E7** take a context per set from the caller. For every cohort utility the context has no set-aside list (`inventory_runs.Context.from_files(0.02, which="every_cohort_utility")`, corrected this session; before, it gave that set the headline's list, a pool 68 units short of `design.split`'s).

## 4. The validation claim for the headline run

`run_outcomes._main` passes `outcome_analysis.ValidationClaim(inputs.validation_reference, inputs.side.usable)` for the headline set at 2% and `False` everywhere else. `outcome_analysis._validation` refuses, in this order: a value that is not a `ValidationClaim` (a `TypeError`); no reference; the absorbed-controls option; a design with no rules; a design whose inputs cannot be computed; a rules hash or a design-inputs hash that differs from the reference's. The caller passes `outcome_analysis.read_validation_reference()`, which reads the step E files and the step E record's headline set, and the usable set the validated design was built on. If either is absent or differs, the run is labelled "under the procedure validated on the headline set; no validation was made on this design", says why, and still estimates.

**Checked this session on the quantity side, with no outcome:** the headline set at 2% as built today has design-inputs hash `b8515c35cba1`, and `_validation` returns passed, "checked: the design's inputs and rules are those the procedure was validated on". The other three sets are refused, as they should be.

## 5. The order of unblinding as recorded, and what enforces it

`ORDER_OF_UNBLINDING` is every registry entry that is not out of scope, in the registry's order. It begins: `reconciliation_row_U`, `reconciliation_row_C`, `inventory_against_sales`, `main_headline_set`, `main_ten_year_set`, `main_plus_unsettled`, `main_every_cohort_utility`, `timing_run_no_anchoring_years`, `customer_weighted`, then the three other outcomes, the seven second-number runs, the affiliate, supplier, deletion, ownership and later-start runs, `callaway_santanna`, `estimators_agree`, the longer horizon, future hosts, own-state comparisons, the two thresholds, the two fuel-mix sensitivities, the size-band side run, E1 to E7, the four conditions, the four influence runs, and last `tariff_check`, `regional_layer` and `exploratory_work`. Row M sits outside it. The stored registry carries the full list (`order_of_unblinding`), unchanged by this session.

**What enforces it:** a check at import that no out-of-scope entry is inside the order; `run_all`, which iterates the order and nothing else; and tests that rows U and C come first, that `run_all` follows the order and that the stored document matches.

**What does not.** Nothing enforces it as an order of unblinding. `run` runs any entry on any frame at any time, with no record of earlier runs and no check that rows U and C ran or were reported first. Neither `run` nor `run_all` checks the gate. `run_all` passes one outcome object to all 57 entries and returns everything together. So "reported first" in the plan's sense depends on how results are written and read, and no code governs that today (the agent's reading, which the session shares). Preserving the recorded order therefore falls to the results writer of section 2 and to the person who reads its output.

## 6. The inventory against sales on the real panel

It reads no price and opens no file. It takes the headline design's hosts and matches, quantities with non-residential sales that include 2009 to 2011, and the dose frame with data center load. Which inventory history to supply is the caller's choice (the registry's text). Its guard runs on invented inputs freely and on research data only with the gate file present and the environment variable set, and the module itself calls that "a stated guard and not a proof". It is third in the order and takes no outcome frame, so after the freeze and authorization it can run on quantities alone, before any outcome is read.

## 7. Tested only on invented inputs, so unproven on real ones

The design builders have run on real quantity files through each module's `main`, and the validation hashes check. What has never met a real outcome:

- **The door and the reshaper,** not written. Kinds of failure to expect: a state column of one type meeting another at a merge (the kernel casts the id and the year, not the state); 32-bit against 64-bit keys; duplicate unit-years; per-unit files skipped silently by the exempt route, which is one reason the door must not use it.
- **`outcome_vector` on real designs.** It stops on any stacked unit-year that is missing or not finite. Alignment depends on the usable flag and the outcome file coming from the same build.
- **Row U on the real panel:** a unit-year with no flags row; a treatment with no megawatts for an outcome unit-year, which raises; prices at or below zero, which are counted; an ownership class outside the row's classes.
- **Row C:** the balanced sample depends on which unit-years have a price, and its hosts for C5 must match its own recomputation.
- **The second number:** no function assembles its configuration for the registry.
- **Callaway and Sant'Anna** runs only where `diff-diff` 4.0.0 imports, which is under `.venv`. Under the machine's Python it is a failure in words, and so is its row in the side-by-side table. A full run has to be made under `.venv`, or that entry run apart there.
- **E7 on outcomes** is the longest job: 200 draws a direction, on two sets, with a fit per draw. On the quantity side this session measured about 2.4 seconds a draw for the headline set and about 9.5 for every cohort utility before any fit.
- **Condition 4:** the set of units with predecessors defaults to empty, so a caller who forgets it marks no unit and nothing refuses.
- **The supplier exercise:** the list of known omissions is passed through unchecked, so the checked loader has to be the one passed.

## 8. What stays after the freeze by its nature

The tariff check's collection, the regional layer and exploratory work are the registry's three entries with no code (`tariff_check`, `regional_layer`, `exploratory_work`); `run` returns their status and reason. Row M is out of scope for this freeze, is refused by `run` before any input is looked at, and M0 to M4 are not run.

## The bounded steps between freeze approval and the first outcome run, in order

1. Joe approves the freeze, and the plan is committed as frozen. The session's recommendation on order, his to strike: `GATE1_SIGNED` is created only after steps 2 to 6 are built and tested on invented inputs, because the file alone opens the panel's reader (section 1). If he prefers the file created with the frozen commit, as the hard rule of D-12 words it, steps 2 to 6 follow it and nothing calls the panel's reader until the door exists.
2. The door, in place of the `NotImplementedError`, with its tests.
3. The reshaper into the seven frames, after Joe settles the three elements the code marks as not stated.
4. The assembler of `RunInputs` from real quantity files, with the validation reference, the drift value from its file, row U's bundle (the adopted flags on a covering frame) and row C's bundle.
5. The results writer, which records the frozen commit, the gate file, a hash of the outcome file and the interpreter, and writes results in the order of unblinding, rows U and C first.
6. On quantities alone, before any outcome is read: the inventory against sales, the headline validation check and the coverage check of row U's flags frame.
7. `GATE1_SIGNED` created, by Joe or on his word, if it was not created at step 1.
8. Outcomes read once through the door, under `.venv` if Callaway and Sant'Anna runs in the same pass, then `run_all`, with rows U and C reported first.

## Uncertain, said plainly

- I am uncertain about this: what the handover's count of 11 entries counted. The code and the stored registry give 10.
- I am uncertain about this: whether the outcome file and the quantity file agree on disk in keys and types. The code writes both from one frame in one build; nothing under `data/blind` was checked.
- I am uncertain about this: which nominal price column row C deflates, and the scale and transformation of the kWh and bill outcomes. The code marks both as not stated.
- I am uncertain about this: whether the ownership-class pick for rows U and C is settled. The registry's text says it is open, and the quantity summaries use the last reported type.
- I am uncertain about this: whether every other built entry runs under `.venv` on real inputs, and how long a full run takes.
- I am uncertain about this: whether the panel's two exempt routes are called anywhere outside the modules read. No wider search was made.
- The count of 25 entries by what the runners fetch is the agent's and was not recounted.

## Dated section, 2026-11-20 (session 26, D-118): the sequence corrected, as a description only

Added by session 26 under Joe's ruling of 2026-11-20 on D-116 (D-117, item 7). **This section supersedes the step list above ("The bounded steps between freeze approval and the first outcome run, in order") and step 1's recommendation there. The list above is left as it was written.** Nothing in the gate was changed to write this: no environment variable was set, no gate file was created, `load_outcomes_after_the_freeze` was not edited, and none of the steps below was carried out. The plan is a draft pre-analysis plan, not frozen and not registered with anyone outside.

His words: "Correct the readiness sequence. Freeze approval, implementation readiness and authorization to read outcomes are separate steps. The proposed future sequence must: place construction and invented-input testing of the reader, reshaper, input assembler and results writer before any outcome access; distinguish quantity-side checks possible beforehand from actual outcome-key and value checks performed at the authorized read; respect the inventory-against-sales check's existing gate and authorization requirements; preserve the recorded order, with U and C reported before the inventory check; identify creation of `GATE1_SIGNED` as a separately authorized action that changes access, not an incidental implementation step. Describe this sequence only. Change nothing in the gate and execute none of these post-freeze steps now."

**What was wrong in the list above** (the session's reading of what his correction answers, D-117 section 3, reading 10). Its step 6 ran the inventory against sales on the real panel before any outcome was read, which put it ahead of rows U and C and passed over the check's own guard. Its steps 1 and 7 treated the creation of `GATE1_SIGNED` as a step among the others. And it did not tell freeze approval, implementation readiness and authorization to read apart.

### Three separate steps, each his

- **Freeze approval.** His explicit approval of the final package, after which the plan is committed as frozen. It authorizes nothing else. It does not create `GATE1_SIGNED`, and it does not authorize any outcome to be read.
- **A statement that the implementation is ready.** Made by a session after the construction and testing of step 2 and the quantity-side checks of step 3 below, and received by him. It is a report on code, and it authorizes nothing.
- **Authorization to read outcomes.** His own word, separate from both. The creation of `GATE1_SIGNED` belongs here and nowhere earlier (step 5).

### The sequence

1. **Freeze approval, and the plan committed as frozen.** No gate file is created by this step, and no environment variable is set.
2. **Construction and testing on invented inputs, with no outcome access and no gate file.** Four pieces, none of which exists today:
   - *The reader,* the door in place of the `NotImplementedError` in `run_outcomes.load_outcomes_after_the_freeze`: both refusals kept, the panel's gated reader called with a named post-freeze purpose, neither exempt purpose ever passed, `power_simulation.read_listed_outcomes` never called, and a refusal when the frozen plan is not committed. Its tests replace the gate file's path and the reader with invented ones.
   - *The reshaper,* from the outcome file's columns into the seven frames the registry takes. The definitions it follows are settled (D-117, in the plan): the three supplementary outcomes are supplied as levels in their stated units and logged by `supplementary_outcomes`, which makes a result non-computable on a missing, nonfinite or nonpositive required row; row C's frame is `res_price` in cents per kWh times row C's CPI-U factor. Tests on invented frames for each column, type and duplicate.
   - *The input assembler,* which fills `RunInputs` from real quantity files: the sets, the contexts with each set's own set-aside list, the validation reference, the drift value read from its file for the headline set alone, row U's bundle (the adopted flags and the adopted ownership classes) and row C's bundle (its specification and its adopted ownership mapping).
   - *The results writer,* which records the frozen commit, the gate file, a hash of the outcome file and the interpreter, and writes results in the recorded order of unblinding. It is where that order is enforced, since nothing in the code enforces it today (section 5).
3. **Quantity-side checks possible before any outcome is read.** They need no gate file and no authorization to read outcomes, and they are told apart here from the checks of step 6:
   - the headline validation check (the design-inputs and rules hashes against the reference), which this study has already made on the quantity side;
   - the assembler's output on the real quantity files: every design builds, and the rank tests that precede a fit pass or stop in words;
   - row U's flags frame and ownership classes, and row C's ownership mapping, against the quantity panel's unit-years and units. This shows coverage of the quantity panel only. It cannot show coverage of the outcome file's unit-years;
   - residential customers, a quantity column, positive and finite on every required row of the headline design (made by session 26 on the design as it stands, counts only);
   - the registry's stated needs, each matched to what the assembler supplies.

   **Not among them: the inventory against sales on the real panel.** It reads quantities only, but its guard (`inventory_against_sales._gate`) refuses research data unless the gate file exists and the environment variable `DCUB_OUTCOME_RUN_AUTHORIZED` is `1`, and the recorded order puts it third, after rows U and C. It is not run in this step, and its guard is not worked around by naming real frames as invented ones.
4. **The statement that the implementation is ready,** reported with the test results of step 2 and the checks of step 3, and received by him.
5. **His authorization to read outcomes, and the creation of `GATE1_SIGNED`.** The creation of the file is a separately authorized action that changes access. It is checked only for existence, and once it exists `panel.load_outcomes` returns the whole outcome file to any caller that names a purpose other than its two exempt ones, with no second condition (section 1). So it is created on his word alone, for the authorized run, and not as an incidental step of the implementation. The environment variable is set for the authorized run only.
6. **The authorized read, once, through the door, and the checks that can only be made then.** Before any estimate: the outcome file's keys and types against the quantity file's (the state column and the widths of the id and the year at a merge); duplicate unit-years; unit-years a design needs that the outcome file lacks; values that are missing or not finite on stacked rows; whether row U's flags frame covers every outcome unit-year that reaches the Short Form filter; whether each usable unit-year has a positive price row; whether each required row of the kWh and bill outcomes can be logged; and row C's price-balanced sample. A failure stops the affected run in words and is recorded. Nothing is filled, imputed or dropped to pass a check.
7. **Execution in the recorded order of unblinding.** Rows U and C are run and reported first. The inventory against sales follows them, under its own guard, with the gate file present, the environment variable set and its inputs named as research data after the freeze. Then the main estimate on the headline set, and the rest of `ORDER_OF_UNBLINDING` as the plan's "Order of unblinding" gives it.
8. **After that, by their nature:** the tariff check's collection, the regional layer and exploratory work. Row M is out of scope for this freeze.

**The session's readings in this section, his to strike.** "Reported before the inventory check" is read as the results writer writing and reporting rows U and C before the inventory check is run. Whether the run pauses there for him is not decided by this description. The list of step 3 and the list of step 6 are the session's sorting of checks into those possible on quantities and those possible only at the read. The hard rule of D-12, as `HANDOVER.md` words it ("then create `GATE1_SIGNED` yourself"), is read as governed by his ruling of 2026-11-20: the file is created on his separate word.

## Dated section, 2026-11-20 (session 27, D-121): steps 1 to 4 of the corrected sequence are done; where what was built differs from the description above

Added by session 27. The plan is frozen (freeze commit `ea426c4`, approved specification `ed3a2ff`), internally frozen and not externally preregistered. **Steps 1 to 3 of the sequence in the section above are done, and step 4, the statement that the implementation is ready, is `docs/gate1/implementation-readiness-package-session27-2026-11-20.md`. Step 5 and everything after it are his: `GATE1_SIGNED` does not exist, no variable is set, no outcome was read and no analysis was run.** Sections 1 to 8 above and the first step list are left as they were written and describe the code before this work.

Where what was built differs from, or adds to, what the section above describes:

- **The door has one more refusal and an order.** It refuses a purpose other than its one post-freeze purpose first, whatever the state of the gate. The refusal "when the frozen plan is not committed" is a read-only check against git that `PREANALYSIS.md` has no uncommitted change and that the freeze commit is an ancestor of the current commit; a committed amendment is recorded and not refused. It returns the frame with a record of the read.
- **The reshaper's row C frame carries the years of row C's own window,** 2015 to 2024, and not every year of the outcome file. The frozen price-index table has no factor before 2014, and the row keeps those years as its first step.
- **The assembler stamps the dose frame,** and the registry's inventory check requires the stamp on research data. Step 3's checks were made on the real quantity files, with one more than listed: condition 4's grouping from the retained peak rows against the stored summary.
- **Condition 4's peak rows** are supplied from a retained copy of the one authorized read, in the form the reading function returns, which the registry's runner now takes beside the raw form.
- **The results writer is also the coordinator,** and it is the one place where the order of unblinding is enforced: each entry runs only when every entry before it is written and reported, and the state of the order is read from the manifest on disk.
- **Step 8's choice is made.** The whole research execution is one pass under `.venv`, where Callaway and Sant'Anna's package imports, and the coordinator refuses to start otherwise. The two interpreters had the same library versions on 2026-11-20, and every record carries its versions.
- **Section 1's warning still stands.** Once `GATE1_SIGNED` exists, `panel.load_outcomes` returns the whole outcome file to any caller that names a purpose other than its two exempt ones. The door, the guards and the coordinator do not change that reader, which is not edited. So the file is created only on his word, for the authorized run.
