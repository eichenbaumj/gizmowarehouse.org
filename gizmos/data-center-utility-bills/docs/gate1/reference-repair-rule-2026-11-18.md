# The reference repair: the rule, written before the code (D-72 item 4; session 13, 2026-11-18)

Written by the session on 2026-11-18 and committed before any code or test below exists. Two pieces of work are made from it and neither sees the other: one agent changes the implementation (section 7); another builds the independent test (section 8) from sections 1 to 6 only. Where this file and `docs/DECISIONS.md` D-72 differ, D-72 governs and the difference is a defect here: stop and report it.

Load and sales only. Nothing here reads a price or revenue column, opens `data/blind`, or opens, lists or hashes the availability mask, its sidecar, P1's record, the manifest or the preserved bundle. Nothing is written under `data/`. **No code written from this file is run on the real inventory until both pieces are finished and the independent test passes** (Joe, session 13: the repair and its test are prerequisites of the rerun, not companions).

## 1. The ruling, in Joe's words (D-72 item 4)

> Repair references and adopt the attribution scope. Endpoint agreement alone does not define a reference where anchoring can change. Enumerate admissible reference settings, prove a valid reduction, or mark the reference undefined. Test this independently of the existing shared endpoint assumption. Retain questions when either reading changes group or acceptance changes. Adopt per-utility merging within the stated model and retain the conservative ceiling fallback. Keep affected attribution and pruning conclusions provisional until these changes are checked.

## 2. The defect, and where it lives

A reference is a utility's place and first crossing on the corrected inventory as built, fixed before attribution. Some questions have no setting in the corrected inventory (a start with no convention, a capacity split with none), and some have a setting that is provisional (the inventory's year-built rows). The rule on file decides whether a reference exists by trying each such question at its two ends only, the first and the last of its settings, in every combination.

That is not enough where a question can move the state's anchoring. A site's start year changes what it counts in the state's 2024 permit total, so it changes the factor every permit-based site in the state is scaled by. For a site on the utility itself the two effects pull opposite ways: a later start takes the site's own load away from early years and raises the factor on everything else the utility carries. The utility's first crossing is therefore not monotone in the date, and a crossing at an interior year can differ from the crossing at both ends. With "never" among the settings the last setting is "never", so every year but the first is interior.

The endpoint rule is written in three places:

1. `pipeline/facilities/pass_c_exact.py`, `_attribute`: the exact attribution's reference (`axes = [(q, [0, len(values) - 1]) ...]`), with a limit of twelve questions.
2. `pipeline/facilities/pass_c_expand.py`, `run_state`: the place test's reference, "one reference variant per combination of their two ends" (`itertools.product((EARLY, LATE), repeat=len(loose))`).
3. `tests/exhaustive_evaluator.py`, `reference()`: the evaluator the implementation was checked against (`itertools.product(*(q.ends for q in defining))`).

The first and the third agree with each other on every case tried. That agreement shows nothing about the rule they share (D-71, issue 1).

## 3. Definitions kept as they are

From the exact attribution's brief (`exact-attribution-brief-2026-11-16.md`, sections 2 to 4), unchanged:

- Questions, settings and the load model are `pass_c_expand._sites`'s, per state.
- *The reference configuration:* every assignment question at the utility the site is on; every date and capacity question at its convention.
- *Place and first crossing as built* of a utility in a configuration: brief section 3.
- *Reference-defining questions, for the exact attribution:* a date or capacity question with no convention, and a date question whose correction carries `"convention_is": "provisional"` (D-66 4.3; D-72 left it standing, subject to this repair).
- *Reference-defining questions, for the place test:* a date or capacity question with no convention. The place test has never read the provisional mark and this file does not change that. It is stated wherever the two references are shown together.

*Note of 2026-11-18, under Joe's ruling D-90 (session 14). The text above is left as written.* Joe accepted the repair and ruled on the place test's narrower list: "Keep the place test's narrower reference only as an explicitly conditional diagnostic: it cannot override an undefined exact reference or independently justify eligibility or pruning." So the place test's reference is a reference only on a condition, that every provisional convention is the site's start. It is a diagnostic on that condition and nothing more. Where the exact attribution's reference is undefined, for either reason (it turns on a question, or it was not searched under R4), that is the utility's state, whatever the place test shows. Neither the place test's reference nor its "keeps its place" is by itself a ground for eligibility or for pruning a question. He also accepted "group" as the stated place categories for this attribution (R7's reading) and the ceiling of 100,000 with its conservative fallback (R4), and the correction about the twelve-question limit (section 5's dated correction).

## 4. The rule

**R1. Admissible reference settings.** For a state, the admissible reference settings are every combination of every setting of its reference-defining questions, as `_sites` lists them: every start year of a date question's interval, "never" where it is a setting, and every capacity case or arrival year. Every other question sits at the reference configuration.

**R2. Defined by enumeration.** A utility's reference is defined if and only if its place as built and its first crossing as built are the same at every admissible reference setting. It is then that place and that crossing. Agreement at the ends, at corners, or at any other subset of the settings does not define a reference.

**R3. The one reduction allowed, with its proof.** For a utility `k` the enumeration may be made over the reference-defining questions that are relevant to `k`, at one representative of each of the question's merged classes for `k`, as the brief's section 5 defines relevance and merging (per-utility merging, adopted in D-72 item 4 within its stated model).

*Proof that this loses nothing.* In a configuration, `k`'s load as built in a year is the sum of the measured load on `k` and the factor times the permit-based raw load on `k`. The factor is a function of the state's two 2024 totals, each a sum of one contribution per site.
- If the factor matters to `k` (it can move, and `k` carries permit-based load in some configuration), two settings are merged for `k` only if, for every setting of the same site's other questions, they put the same load on `k` in every year and give the site the same 2024 contribution. Replacing a setting by another of its class therefore leaves `k`'s own load from that site and both state totals unchanged, so the factor and `k`'s whole history as built are unchanged.
- If the factor does not matter to `k`, either it takes one value in every configuration, or `k` carries no permit-based load in any configuration and its load as built does not contain the factor. Settings are then merged on `k`'s own load alone, and replacing one by another of its class leaves `k`'s history as built unchanged.
- A question with one merged class for `k` is irrelevant to `k` by the same argument, at any setting.
So every history as built that `k` can have at any admissible reference setting is the history at some combination of class representatives of its relevant reference-defining questions. The enumeration over those combinations sees every place and crossing that R2's enumeration sees. ∎

The proof rests on two things outside itself, which the independent test does not assume: that `_sites` lists every setting, and that "the factor takes one value in every configuration" is read correctly from the factor's range (D-66 section 3 has that argument; the range's grid check stays as a guard).

No other reduction is used. In particular: not the two ends, not the all-early and all-late corners, and no appeal to an earlier start meaning more load.

**R4. Undefined without the search.** If the number of combinations under R3 is more than the ceiling of 100,000, the reference is undefined and the output says that it was not searched and gives the number. The limit of twelve questions is removed. For a utility attributed exactly this cannot happen: its reference-defining relevant questions are among its relevant questions, and the product over all of those is at or under the ceiling.

**R5. An undefined reference** is handled as before: the wider outcome of the brief's section 3 (both first crossings and both under-the-floor readings), under which any change keeps the question (D-66 4.2, standing under D-72).

**R6. One implementation.** The place test takes its reference from the same code as the exact attribution, with its own list of reference-defining questions (section 3). No code path decides a reference from ends. The place test's scenarios (the reference variants at the ends, all earliest, all latest, the flips and the envelope) are unchanged, and its result stays what it has been called: a test on the scenarios run. This repair changes whether a reference exists. It does not make the place test exhaustive.

*Note of 2026-11-18, under D-90 (session 14). R6 is left as written.* What R6 calls the place test's reference is, by Joe's ruling, a conditional diagnostic (the note in section 3 has his words). The outputs now say so, and say which reference governs:
- Every place-test row carries `reference_is` ("conditional diagnostic"), and beside its own reference the exact attribution's for the same utility (`exact_reference_defined`, `exact_reference_why_undefined`), from the same function with the exact attribution's list.
- Where the exact reference is undefined and the place test still shows one, the row's `reference_shown_where_exact_is_undefined` is true and `reference_warning` says in words that the row's reference and its "keeps its place" are the diagnostic only, do not override the undefined exact reference, and are no ground for eligibility or pruning. The place test's own values on the row are not changed: it is still reported, as a diagnostic.
- The driver marks every row against the reference of its own run, lists those utilities in the JSON's counts (`place_test_reference_shown_where_exact_is_undefined`), prints them in the summary, and puts the words in a last CSV column, `place_test_reference_note`. No other CSV column has ever carried the place test's reference.
- One synthetic test on invented inputs: `tests/test_pass_c_exact.py`, `test_the_place_tests_reference_is_only_a_conditional_diagnostic_where_the_exact_reference_is_undefined`. Its made-up state has a provisional date whose two ends agree in both readings and whose interior differs, so the exact reference is undefined while the place test shows a reference and "keeps its place: True".
- *Read, not run:* no code path prunes a question or decides eligibility on the place test's reference or on `keeps_its_place`. Inside `run_state` they reach the row's `reference`, `reference_differs_from_original`, `keeps_its_place` and `first_failure` and nothing else; `joins` come from the joint check; the exact attribution's kept sets come from its own reference. The only modules that import either file are the dependency adapter, which takes `_sites` and `joint_check`, and the screen command, which takes the loader, the parser and the host list.
- *The outputs on file predate the labels.* The JSON, CSV and text files of D-89's four runs were written before this note and are not regenerated here: no research-data run is authorized. They are to be read under D-90. In the D-65 run on file (`expansion-test-2026-11-18-d65.json`, read as text) four utilities have an undefined exact reference where the place test shows one: Guadalupe Valley (`7752:TX`), Duke Energy Ohio (`3542:OH`) and Entergy Texas (`55937:TX`), whose place-test rows each already read "keeps its place: False", and Virginia Electric and Power (`19876:VA`), whose exact reference is not searched (R4) and whose place-test row shows early 2010 and "keeps its place: True". D-90's work list named the first three only. Virginia Electric and Power's row is the one the ruling bites on: its "keeps its place" is the diagnostic, and its reference is undefined.

**R7. The keep criterion, as Joe widened it (D-72 item 4).** With a defined reference a utility's outcome in a configuration is the triple: place as built, place with no anchoring, accepted. A question is kept if two configurations that differ only in it give a different triple. *The session's reading, for Joe to strike:* "group" in "either reading changes group" is the place of the brief's section 3: the group of the first crossing, and "comparison" or "neither" where there is none. The narrower outcome of D-66 4.1 (place as built, accepted) is kept in the code as a named alternative so that the rerun can show which moves come from the reference and which from the criterion. It decides nothing.

## 5. What the repair can and cannot do to a result (stated before any result)

- *A reference defined under R2 was defined under the endpoint rule, with the same value.* The ends are among the admissible settings, and the value is read at the reference configuration in both. So the repair can turn a defined reference into an undefined one and can do nothing else to a reference.
- *An undefined reference keeps at least what a defined one kept.* The defined outcome under either criterion is a function of the four values of the undefined outcome: place as built is a function of the crossing as built and the under-the-floor reading as built; place with no anchoring likewise; and acceptance against any reference is a function of the places and crossings.
- *The widened criterion keeps at least what the narrower one kept:* the pair is part of the triple.
- So, utility by utility, the rerun's kept set must contain the kept set on file (D-68), and its relevant questions and configuration counts must be unchanged. **If any kept question on file is missing after the rerun, or a count differs, that is a defect and the rerun is not reported as a result until it is explained.**
- For the 21 utilities over the ceiling nothing changes but the reported reference.

*Corrected 2026-11-18, before the rerun, on a defect the agent who built the independent test found in this section. The text above is left as written.* The first claim is not true of every utility. Under the rule on file, a utility with more than twelve relevant reference-defining questions had an undefined reference without any search. R4 removes that limit and searches up to 100,000 combinations, so such a reference can become **defined**, and a defined reference can keep fewer questions than the wider outcome did. The claims of this section therefore hold for every utility whose reference on file was not "undefined without the search", and for the others the direction is open. The rerun's check is made accordingly: utilities whose reference on file was undefined for the twelve-question limit are listed by name and compared separately, and a kept question missing for one of them is reported as a consequence of R4 and not as a defect. For every other utility a missing question or a changed count is still a defect. The second claim's wording is also loose: for a comparison reference, acceptance turns on the under-the-floor reading with no anchoring, which is one of the four values of the undefined outcome and not a place or a crossing. The conclusion stands.

No count of who moves under this rule was made before it was written. Known when it was written: D-68's table, and that Guadalupe Valley's reference is already undefined.

## 6. What the independent test must not share

It must not use, call or copy: the two ends of a question; the corners; any monotonicity; merging; relevance; `_factor_range` or `factor_varies`; anything in `pass_c_exact.py`; the `reference()` of `tests/exhaustive_evaluator.py` as it stood before this repair; or `run_state`'s reference. It decides a reference one way only: by realising every admissible reference setting of a made-up state through the scratch rebuild and reading every utility's place and crossing as built in each.

## 7. The implementation (agent A)

Files: `pipeline/facilities/pass_c_exact.py`, `pipeline/facilities/pass_c_expand.py`, `tests/test_pass_c_exact.py`, `tests/test_pass_c_expand.py`. Tests first.

- `pass_c_exact.py`: a function that returns a utility's reference under R2 to R4 for a given list of reference-defining questions; `_attribute` uses it with the exact attribution's list. `REFERENCE_QUESTION_LIMIT` goes. The reference record gains `settings_enumerated` (the number of combinations under R3, an integer however large) and `searched` (false only under R4); `why_undefined` names the questions and, for one of them, a pair of settings that give different places or crossings, so that a reader can realise the pair.
- The outcome with a defined reference becomes R7's triple. A keyword `criterion`, `"either_reading"` by default and `"as_built"` for D-66 4.1's pair, on `exact_attribution` and on the driver (`--criterion`). The witness's `outcome` carries `place_no_anchoring` as well.
- `pass_c_expand.run_state`: the place test's `ref` comes from the same function (a lazy import is acceptable), with the place test's list of reference-defining questions. Where it is defined, `refs[0]` must show the same place and crossing, and the code raises if it does not. Where it is not, the row's `reference` says so in words: which questions, or that it was not searched. The docstring's "Scenarios" paragraph is brought up to date. `check_unresolved_count` and its message are left alone unless they no longer describe what the code does.
- The driver's JSON, CSV and printed summary carry the new reference fields. The CSV gains no column that an existing reader would trip on: add at the end.
- Every existing test whose expectation rested on the endpoint rule is listed in the report with what it expected and why it changed. No expectation is changed for any other reason.
- New tests, on made-up inputs built with `world()` and `mini()` from `tests/test_pass_c_expand.py`: a site on the utility whose date has no convention, where the ends agree and an interior year gives another crossing (the reference must be undefined, and the named pair must realise differently through `realise`); the same with "never" as the last setting; a provisional date with the same shape; a case where every setting agrees (defined, same value as the ends); a capacity question with `rest_earliest`; a utility over a small ceiling (R4, said in words); the place test and the exact attribution agreeing on every utility of a state with no provisional question; `criterion="as_built"` reproducing the narrower outcome; and the triple keeping a question that only the no-anchoring place separates.

Agent A may read: this file; `docs/gate1/exact-attribution-brief-2026-11-16.md`; `docs/DECISIONS.md` from the headings "D-65", "D-66", "D-68" and "D-72" only; the four files it changes; `pipeline/facilities/assignment.py`, `buildout.py`; `tests/exhaustive_evaluator.py` and `tests/test_pass_c_exact_against_evaluator.py` to read, not to change (they are agent B's). It works on made-up inputs only: it does not call `load_frozen`, does not run the driver, and does not run `exact_attribution`, `expand` or `joint_check` on the real inventory. The tests in `tests/test_pass_c_expand.py` that load the real inventory (the rebuild with no corrections, the factor channel with no corrections, the refusal check) may run as part of that file; they compute no reference and no attribution. It opens nothing else under `data/`, makes no scratch copy of the repository, runs Python as `python3 -I` from the gizmo folder, and commits nothing.

## 8. The independent test (agent B)

Agent B works in a separate checkout. It must not open `pipeline/facilities/pass_c_exact.py` or `tests/test_pass_c_exact.py`, in the checkout or in version control, at any commit. It opens, lists, reads or hashes nothing under `data/` and creates no `data/` folder.

**8.1 `tests/reference_enumerator.py`** (new), written from sections 1 to 6:

```python
def admissible_reference_settings(inp, corrections: list[dict], st: str, provisional_defines: bool) -> dict
# {"questions": [{"fid", "question", "settings": [value, ...]}], "combinations": int}

def references(inp, corrections: list[dict], st: str, theta: float = 0.02, provisional_defines: bool = True) -> dict
# {(utility_id_eia, state): {"defined": bool, "place": str | None, "crossing": float | None,
#                            "seen": [(place, crossing), ...],            # every distinct pair, sorted
#                            "differs_inside_only": bool}}                # the ends all agree and some interior setting does not
```

It lists the reference-defining questions and every setting of each from the correction dicts by its own code, from the words of the brief's section 2 (a date's years from its early end to its late end, a start at or before 1999 entered once, a start after the last panel year entered once, "never" where possible; a capacity question's two cases or, with `rest_earliest`, each arrival year), and asserts that its lists equal `pass_c_expand._date_values` and `_capacity_values` on every case it runs. It realises every combination through `pass_c_expand.scratch_state` and `assignment.evaluate`, the way `_realize` in `tests/test_pass_c_expand.py` does, and computes each utility's place and first crossing as built by its own arithmetic from the `as_built` matrix. `differs_inside_only` is computed for reporting: it is how a case shows that the endpoint rule would have called the reference defined.

**8.2 `tests/test_reference_enumerator.py`** (new): the enumerator against answers worked by hand, the arithmetic in comments, on cases small enough to work by hand. At least:
- a site on the utility whose start has no convention, in a state whose factor moves with that start, where the first and last settings give the same place and crossing and an interior year gives another (`defined` false, `differs_inside_only` true);
- the same shape with "never" as the last setting;
- the same shape with a provisional convention, checked with `provisional_defines` true and false;
- a state whose factor is held at one value in every setting, where the ends agreeing does imply every setting agrees (defined);
- a site on another utility whose start reaches this one only through the factor;
- a capacity question with `rest_earliest`;
- two reference-defining questions, where the reference is undefined only at a combination interior to both.

**8.3 `tests/exhaustive_evaluator.py`** (change): `reference()` takes its answer from the enumerator, for every reference-defining question at every setting, and no longer from the ends; the limit of twelve questions is replaced by a refusal above a number of combinations that keeps a made-up case small. `outcome` with a defined reference returns R7's triple, with a `criterion` argument (`"either_reading"` by default, `"as_built"` for the pair) passed down from `pivotal_questions`. Nothing else in the file changes. `tests/test_exhaustive_evaluator.py` is brought up to date, each changed expectation listed with its reason.

**8.4 `tests/test_reference_against_enumerator.py`** (new), written to the interface of section 7 and of the exact attribution's brief; it cannot run in agent B's checkout, and the report says so. For made-up states built with `world()` and `mini()`, each small enough for the full product, including every case of 8.2 and at least forty seeded random states (random sites, sizes, intervals reaching 2023 or later, "never", provisional marks, capacity splits, factors that move, are capped and are floored):
- for every utility, the exact attribution's reference (`exact_attribution(...)["utilities"][key]["reference"]`: `defined`, `place`, `crossing`) equals the enumerator's with `provisional_defines=True`;
- for every utility the place test touches, whether `expand(...)`'s row has a reference, and its place and crossing, equal the enumerator's with `provisional_defines=False`;
- at least five of the states have a utility with `differs_inside_only` true, and the file asserts that count, so that the comparison cannot pass on cases the endpoint rule also gets right.

**8.5 `tests/test_pass_c_exact_against_evaluator.py`** (change): states added so that each case of 8.2 is among those on which the kept sets are compared, under both criteria. Existing states and assertions stay.

Made-up numbers are chosen so that no load sits within one part in a million of a threshold.

Agent B may read: this file; `docs/gate1/exact-attribution-brief-2026-11-16.md`, sections 1 to 4 and 7; `docs/DECISIONS.md` from the heading "D-72" only; `pipeline/facilities/pass_c_expand.py`, `assignment.py`, `buildout.py`; `tests/test_pass_c_expand.py`; `tests/exhaustive_evaluator.py`, `tests/test_exhaustive_evaluator.py` and `tests/test_pass_c_exact_against_evaluator.py`, which it changes. Run Python as `python3 -I`. It commits its files on the checkout's branch and nothing else.

## 9. Reports, and what the session does with them

Each agent ends with: the model id it ran as; the files it wrote or changed; the tests it ran and their counts; every reading it made that this file does not settle; and anything in this file or the existing code it believes is wrong. A report is a claim. The session then:

1. runs agent B's new tests against the implementation **as it stood before the repair**, and records how many fail and that the failures are the interior cases (if none fails, the test is not apart from the endpoint assumption and is sent back);
2. runs every test against the repaired implementation;
3. changes the repaired implementation on purpose (ends only; corners only; the provisional mark ignored; "never" dropped from the enumeration; the factor ignored in merging; the place test left on its own ends; the criterion's no-anchoring place dropped) and watches which tests notice;
4. only then makes the rerun (section 5 says what it must show).
