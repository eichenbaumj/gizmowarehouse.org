# Brief: the dependency adapter (D-72 item 3; authorized for implementation and synthetic testing only, D-83)

Written by the execution session on 2026-11-18 and committed before any code. Two pieces of work are made from it and neither sees the other: the session builds the adapter (section 6); an agent builds a brute-force evaluator and hand-worked toy cases (section 7) from sections 1 to 5 only. Where this brief and `docs/DECISIONS.md` D-72 or D-83 differ, they govern and the difference is a defect in this brief: stop and report it.

**Invented data only.** Nothing here opens anything under `data/`, reads a price or revenue column, or opens, lists or hashes the availability mask, its sidecar, P1's record or the preserved bundle. Every mask in a test is made up in the test. Nothing is written under `data/`. No pool is screened and no verification is deferred: this is code and tests.

## 1. The rulings it carries out, in Joe's words

D-72 item 3:

> No verification deferral yet. Before using the mask to defer work, build and test the dependency adapter. Use all relevant questions, not only kept questions. Derive anchoring influence directly from admissible contributions; absence of a classification effect does not establish an unchanged factor. Null or unknown means retain. Cover changes to corrections, candidates and dependencies in the reopening rule. Retire nothing outside the attribution’s coverage, and do not change host verification effort in response to availability flags.

The availability ruling, item 8 (route document, section A; adopted in D-73):

> Provisional use. Permit narrowing only for utilities that fail every permitted window, explicitly including both forms of the second estimate. Do not change host verification effort, timing conventions or rules in response to flags. Retiring one utility’s eligibility work must not retire any shared question that can affect another eligible utility or state anchoring. Recheck those dependencies. Reopen deferred work if changed inputs or adopted windows invalidate the screen.

D-83, on what the tests must cover:

> Test window eligibility and missing years; all relevant questions rather than only kept questions; direct anchoring dependencies; shared questions; conservative retention for unknown or uncovered cases; and reopening after changes to corrections, candidates, dependencies, mask identity or eligibility rules. Use independently worked toy cases, and establish any reference repair on which the adapter depends.

## 2. What is being decided

The verification pass keeps open questions about sites (who serves a site, when it began, how its capacity arrived). The availability mask says, for each utility-state and year, whether a usable residential price exists. A utility that is usable in no window any estimate uses cannot enter any estimate as a comparison. The adapter answers one thing: **which open questions may be set aside for now because nothing they could change reaches any utility that still matters or the state's anchoring.** It decides nothing else. It removes no site and no load from anything.

The guarantee the adapter has to give, stated so that it can be checked without the adapter's own definitions:

> If the adapter says a question may be deferred, then for every pair of configurations of the state's questions that differ only in that question: (a) every utility that is not narrowed has the same load, in every panel year, in both readings (as built and with no anchoring); and (b) the state's 2024 anchoring totals, measured and permit-based, are the same. And whether a question that reaches a host or a possible host is deferred never depends on the mask.

## 3. The model, as the pass already builds it

Exactly as `pipeline/facilities/pass_c_expand._sites` builds a state and `scratch_state` rebuilds one (the exact attribution's brief, `exact-attribution-brief-2026-11-16.md`, section 2, says the same in words):

- Everything is per state. A utility is a `(utility_id_eia, state)` unit of the panel.
- A site has zero or more questions: `assignment` (the utility it is on, each candidate, or off the panel), `date` (each start year of its interval, and "never" where possible), `capacity` (its two cases, or each year the rest may arrive). A configuration sets every question once.
- In a setting, a site is on one panel unit or on none, carries a load in MW in each panel year, and counts some TWh in its state's 2024 anchoring, on the permit-based side or the measured side according to the site's kind.
- The state's factor in a configuration is `_factor(EPRI, measured total, permit total)` over the configuration's 2024 contributions. A permit-based site's load on its utility is its raw load times the factor (as built) or times 1 (no anchoring). A measured site's load is not scaled.

## 4. Definitions

**4.1 A question reaches a utility directly.** Question `q` of site `s` reaches utility `k` directly if, for some setting of `s`'s other questions, two settings of `q` put different load on `k` in some panel year, where the site's load on `k` in a setting is its load when that setting puts the site on `k` and zero otherwise. This is relevance through own load. It does not ask whether any classification, crossing or acceptance changes, and it uses no reference.

**4.2 A question moves the state's anchoring.** `q` moves anchoring if, for some setting of `s`'s other questions, two settings of `q` give `s` a different 2024 contribution. It is read from the contributions and from nothing else. It is **not** conditioned on whether the factor's range is a single number, on whether any utility carries scaled load, or on whether any utility's classification changes. The answer is `True`, `False`, or `None` when a contribution is not a finite number. `None` is unknown, and unknown means retain.

**4.3 All relevant questions.** The questions considered are every question `_sites` lists for the state, whether or not the exact attribution keeps it for anyone. The exact attribution's kept sets and its reference are not inputs.

**4.4 Coverage.** The caller names the states the pass's check covers (`covered_states`). A question is covered if its state is named and the adapter built that state's table without a refusal. A question in any other state is retained, whatever the mask says. A state whose table cannot be built (any refusal `_sites` or `parse_corrections` raises) is not covered, and the reason is recorded.

**4.5 A possible host.** Utility `k` is a possible host if, over the state's settings, the upper bound on its load reaches the host threshold (2% of its base-period sales) in some panel year in either reading. The upper bound is the conservative joint check's (`pass_c_expand.joint_check(...)["bounds"]`, widened outward as that check widens it). A utility with no positive base is never a host, as `assignment.evaluate` reads it. A utility whose bound cannot be computed is a possible host. Every unit the caller lists in `hosts` is protected as well. A protected unit (a listed host or a possible host) is never narrowed, and so no question that reaches one directly is ever deferred. **Availability flags are not consulted in deciding who is protected.**

**4.6 Narrowed.** A unit is narrowed if and only if it is in the caller's `pool` (the prospective comparison pool), is not protected, and fails every permitted window on the mask. The permitted windows are `pipeline.analysis.availability.permitted_windows()`: each cohort's ten years `g-6` to `g+3` for `g` from 2011 to 2022, the second estimate's long difference (2008, 2009, 2010, 2023, 2024, 2025) and its panel form (2005 to 2025). A unit passes a window only if it is usable in every year of it. A year missing from the mask is not usable. A unit absent from the mask passes no window. A unit that is not in the pool is never narrowed, whatever its flags.

**4.7 May be deferred.** A question may be deferred if and only if all of these hold: it is covered (4.4); it moves anchoring is exactly `False` (4.2); it reaches at least one utility directly; and every utility it reaches directly is narrowed (4.6). Otherwise it is retained, with the first reason that applies, in this order: outside coverage; anchoring unknown; moves the state's anchoring; reaches no utility (it cannot be shown to affect none); reaches a utility that is not narrowed (each named, with why: a listed host, a possible host, not in the pool, or the windows it passes).

**4.8 The record, and reopening.** A screen's record carries a fingerprint of each thing it rests on:

- *corrections:* the corrections in force, as given;
- *candidates:* every question of every covered state with its full list of settings (an assignment question's settings are the site's candidates, so a changed candidate list changes this);
- *dependencies:* the table of 4.1 and 4.2 for every covered state, with each state's protected units;
- *mask identity:* what the caller says identifies the mask (run identifier, audit attempt, definition version, the mask file's hash as preservation printed it), and a hash of the mask's rows;
- *eligibility rules:* the permitted windows, the adapter's rule version, the host threshold, the pool, the listed hosts and the covered states.

A later check recomputes each from what is then in force and names every one that differs. **If any differs, the whole screen is void and every question it deferred is open again** until a new screen is made. There is no partial reopening.

## 5. What does not depend on what

- The adapter uses no reference and no kept set. Its answers must be the same whether a question has a convention, a provisional convention or none. (So the reference repair of D-72 item 4 is not a dependency of the adapter. It stays owed for the attribution itself.)
- Who is protected does not depend on the mask.
- Narrowing does not depend on who today's hosts are except through protection: a host is never narrowed.

## 6. The adapter (the session)

New file `pipeline/analysis/availability_adapter.py`, beside its receiving end `pipeline/analysis/availability.py`. It imports `pipeline.facilities.pass_c_expand` and changes nothing in it.

```python
RULE_VERSION = "2026-11-18.1"

def state_dependencies(inp, corr, st, theta=0.02) -> dict
# {"state": st,
#  "questions": [{"question_id": "<fid> <question>", "fid", "question", "settings": [value, ...],
#                 "utilities": ["<utility_id_eia>:<state>", ...],          # 4.1, sorted
#                 "moves_anchoring": True | False | None}],                # 4.2
#  "possible_hosts": ["<utility_id_eia>:<state>", ...],                    # 4.5, without the caller's list
#  "units": ["<utility_id_eia>:<state>", ...]}

def dependency_table(inp, corr, states) -> dict
# {"states": {st: state_dependencies(...)}, "refused": {st: "<the refusal, in words>"}}

def screen(mask, mask_identity, pool, hosts, table, covered_states, corrections, windows=None) -> dict
# {"rule_version", "narrowed": [...], "protected": {unit: why}, "not_narrowed": {unit: why},
#  "deferrable": [question_id, ...], "retained": {question_id: reason}, "fingerprints": {...five names...}}

def reopen_reasons(record, mask, mask_identity, pool, hosts, table, covered_states, corrections, windows=None) -> list[str]
# [] if the screen still stands; otherwise the names of the fingerprints that differ
```

`inp` is a `pass_c_expand.Inputs`; `corr` is `pass_c_expand.parse_corrections(corrections, inp)`; `corrections` is the list of correction dicts as given. A setting is written as the exact attribution writes it: a utility id, `"off_panel"`, a year, `"never"`, `"early"` or `"late"`. Everything returned survives `json.dumps`.

The receiving end, `availability.retirable_questions`, treats a `moves_anchoring` of `None` as "does not move". That is wrong under D-72 item 3 and is corrected with the adapter, with a test.

*Added 2026-11-18, after the adapter was built and before the readiness review:* a command that would run the screen, `pipeline/analysis/run_availability_screen.py`, so that the draft instruction for using the mask can name one. It refuses to start unless a ledger entry carries a pin block, under a header of its own, for every project module it has loaded. No entry does. It is tested on an invented tree only (`tests/test_availability_screen_run.py`) and has never been run on research data. The adapter also gained `fingerprints(...)`, which `screen` and `reopen_reasons` both call, and `screen` returns `refused_states` beside the fields listed above.

## 7. The evaluator and the toy cases (the agent)

The agent works in a separate checkout that has no `data/` folder and needs none. It does not see the adapter and must not look for it. *(Corrected 2026-11-18, before the agent started: a git worktree does carry the 36 committed files under `data/frozen/`. The agent was told to open, list, read or hash nothing under `data/` and to create no `data/` folder.)*

**7.1 `tests/adapter_evaluator.py`**, written from sections 1 to 5 and from nothing in section 6:

```python
def brute_force(inp, corrections: list[dict], st: str, theta: float = 0.02) -> dict
# {"configurations": int,
#  "reaches": {(fid, question): {(utility_id_eia, state), ...}},      # 4.1, by enumeration
#  "moves_anchoring": {(fid, question): bool},                        # 4.2, by enumeration
#  "can_cross": {(utility_id_eia, state), ...},                       # crosses the host threshold in some configuration, either reading
#  "loads": {configuration key: {(utility_id_eia, state): {"as_built": [...], "no_anchoring": [...]}}},
#  "anchoring": {configuration key: (measured total, permit total)}}

def violations(result: dict, deferrable: set, narrowed: set) -> list
# every breach of the guarantee in section 2: a deferrable question, a pair of configurations differing only in it,
# and either a utility not in `narrowed` whose load differs in some year in either reading, or differing anchoring totals
```

It lists every question and every setting itself from the corrections and the inventory (it may call `pass_c_expand._date_values` and `_capacity_values` for the lists of years, and `assignment.resolved` and `assignment.candidates`), enumerates the full product over every question in the state, and realises each configuration through `pass_c_expand.scratch_state` and `assignment.evaluate`, the way `_realize` in `tests/test_pass_c_expand.py` does. A question reaches a utility if two configurations that differ only in it give the utility a different no-anchoring load in some year (the no-anchoring reading has no factor in it, so a difference there is the site's own load). The 2024 anchoring totals of a configuration are computed by the evaluator's own arithmetic from the configuration's rebuilt inventory, measured side and permit side apart; it does not read them from `_sites`. It must not call `pass_c_expand._sites`, `joint_check` or anything in `pass_c_exact.py`.

**7.2 `tests/test_adapter_evaluator.py`:** the evaluator checked against answers worked out by hand, on cases small enough to work by hand, with the working shown in comments. At least: an assignment question between two utilities (reaches both, does not move anchoring); a date question wholly before the anchoring year's ramp (reaches its utility, does not move anchoring); a date question whose interval includes years that change the 2024 load (moves anchoring) in a state whose factor is held at one value in every setting, so that no other utility's load changes and the question still moves anchoring; a date question with "never".

**7.3 `tests/test_adapter_toy_cases.py`:** toy cases for the adapter, each with its expected answer worked by hand from sections 1 and 4, the working in comments, and no expectation taken from running any code. Written to the interface in section 6; it cannot run in the agent's checkout, because the adapter is not there, and the report says so. Cover each item of D-83's list at least once:

- *window eligibility and missing years:* a unit usable in every year; a unit missing one year that sits in every cohort window but not in the long difference (not narrowed); a unit missing years so that exactly one cohort window survives (work out which); a unit with a year absent from the mask altogether; a unit absent from the mask; a unit that fails every permitted window (narrowed, if in the pool and not protected);
- *all relevant questions, not only kept:* a question that reaches a comparison utility that passes a window, where nothing the question can do changes that utility's place (it stays far under the floor): retained;
- *direct anchoring dependencies:* a date question on a narrowed utility's only site whose settings change the 2024 contribution: retained, including in a state whose factor cannot move;
- *shared questions:* an assignment question whose candidates are one narrowed utility and one utility that is not narrowed: retained, naming the second; the same question when both are narrowed: may be deferred;
- *unknown and uncovered:* a question in a state not in `covered_states`; a state whose table is refused; `moves_anchoring` of `None` passed to `availability.retirable_questions`;
- *hosts:* a question reaching a listed host that fails every window: retained; a question reaching a possible host (not listed) that fails every window: retained; and for a fixed table, changing any flag of a protected unit changes nothing about its questions;
- *reopening:* one change to each of corrections, a candidate list, a dependency, the mask's rows, the mask's stated identity, a window, the pool, the listed hosts and the covered states, each naming the right fingerprint; and no change naming none.

**7.4 `tests/test_adapter_against_evaluator.py`:** made-up states built with `world()` and `mini()` from `tests/test_pass_c_expand.py`, each small enough for the full product. For each, and for several invented masks (including all usable, none usable, and seeded random ones): build the adapter's table and screen; assert `violations(...)` is empty; assert the adapter's `utilities` for each question contain the evaluator's `reaches`; assert `moves_anchoring` agrees exactly; assert every unit in `can_cross` is among the adapter's possible hosts. Written to the interface in section 6.

Made-up numbers are chosen so that no load sits within one part in a million of a threshold.

Inputs the agent may read: this brief; `docs/DECISIONS.md` from the headings "D-72" and "D-83" only; `pipeline/facilities/pass_c_expand.py`, `assignment.py`, `buildout.py`; `pipeline/analysis/availability.py`; `tests/test_pass_c_expand.py`; `tests/exhaustive_evaluator.py` (for how a configuration is realised; its reference rule is not used here). No data. Do not create, link or copy a `data/` folder. Run Python as `python3 -I`. Commit the new files on the checkout's branch and nothing else.

## 8. Reports

The agent ends with: the model id it ran as; the files it wrote; the tests it ran and their counts; every reading it made that this brief does not settle; and anything in this brief or the existing code it believes is wrong. A report is a claim: the session reruns everything, and changes the adapter itself to see that the tests catch it.
