# Brief: the exact attribution of the verification pass (D-65 item 4, D-66 section 4)

Written by the session on 2026-11-16 and committed before any code. Two agents work from it and neither sees the other's work: one builds the implementation, the other builds an exhaustive evaluator and the made-up cases that compare the two. Where this brief and `docs/DECISIONS.md` D-65 differ, D-65 governs and the difference is a defect in this brief: stop and report it.

Load and sales only. Nothing here reads a price or revenue column, opens `data/blind`, or imports the price code. Nothing is written under `data/`.

## 1. What is being decided

The verification pass keeps a list of open questions about sites: who serves a site (assignment), when it began operating (date), and how its capacity arrived (capacity). A question matters to a utility if settling it could change where the utility stands. The conservative joint check (`pass_c_expand.joint_check`, D-63 rule 7) keeps every question that could change any threshold status in any year, which over-includes. The exact attribution keeps a question for a utility if and only if two feasible configurations that differ only in that question give the utility a different outcome.

Everything is per state. A utility is a `(utility_id_eia, state)` unit of the panel, and a state's utilities depend only on that state's sites and that state's anchoring factor.

## 2. Questions, settings and the load model

These are exactly as `pass_c_expand._sites` builds them for the conservative check, and as `pass_c_expand.scratch_state` rebuilds a state. In words:

- *Assignment question:* a site that `assignment.resolved` reads as unresolved (a `reopen` included), that is on a utility, and that carries load in some setting. Settings: the utility it is on, each candidate, and off the panel. A site has one assignment in a configuration.
- *Date question:* a `date` correction. Settings: every start year from its early end to its late end, and "never" where that is possible. A start at or before 1999 is one setting (full load in every panel year); a start after the last panel year is one setting. `pass_c_expand._date_values` lists them.
- *Capacity question:* a `capacity_split` correction. Settings: its two cases, or, with `rest_earliest`, every year the rest of the row may arrive (`pass_c_expand._capacity_values`). The rest never arrives before the first phase: `Correction.history` enforces that, and it is the dependency between a site's date and capacity questions.
- *A configuration* sets every question once. A site with several questions takes one setting of each.
- *Loads.* A permit-based site's load on its utility in a year is its raw load under the setting's history times the state's factor (as built), or times 1 (with no anchoring). A measured site's load is not scaled. The state's factor in a configuration is `pass_c_expand._factor(epri, measured total, permit total)` over the configuration's 2024 contributions, and it is replaced by the frozen factor when it is within `FACTOR_TOL * max(1, |frozen|)` of it, as `scratch_state` does. Utility energy in a year is 8.76 times its MW, in GWh.
- If any site that can be on a utility has a no-anchoring divisor range (`_Site.na_div`) whose two ends differ, that utility is not attributed exactly: it takes the conservative result, and the output says why.

## 3. The outcome of a utility in a configuration

Let `ab[y]` and `na[y]` be the utility's GWh in each panel year as built and with no anchoring, `base` its base-period sales (`inp.base`), `theta` the host threshold (0.02) and `floor` the comparison floor (`assignment.CLEAN_BELOW`, 0.005).

- *First crossing* of a reading `v`: the first panel year with `v[y] >= theta * base`, if `base > 0`; otherwise none.
- *Largest share:* `max(v) / base` if `max(v) > 0`, else 0. With no positive base and any load the share is infinite: such a utility never crosses the host threshold and any load puts it over the floor, as `assignment.evaluate` reads it.
- *Place* of a reading: `assignment.group` of its first crossing (early before 2011, cohort 2011 to 2022, late after); if there is no crossing, "comparison" when the largest share is strictly under `floor`, otherwise "neither".
- *Within one year:* `assignment.same_place(a, b)`: the same group, and for cohort years a difference of at most one year.

**With a defined reference** `(place_ref, crossing_ref)` the outcome is the pair `(place as built, accepted)`. `accepted` is true when the place as built equals `place_ref` and:

- for a cohort reference: `same_place(crossing_ref, crossing as built)` and `same_place(crossing_ref, crossing with no anchoring)`;
- for an early reference: the crossing with no anchoring is also early;
- for a comparison reference: the largest share with no anchoring is also strictly under `floor`;
- for a late or "neither" reference: nothing more.

**With an undefined reference** the outcome is the four values `(crossing as built, crossing with no anchoring, largest share as built < floor, largest share with no anchoring < floor)`. Any difference in any of them is a different outcome.

## 4. The reference

Fixed before attribution and never recalculated per configuration.

- *The reference configuration:* every assignment question at the utility the site is on (the as-mapped reading); every date and capacity question at its convention (`Correction.convention`; a convention year is mapped into the question's settings, clamped to the first or last where it lies outside them).
- *Reference-defining questions:* a date or capacity question with no convention, and a date question whose correction carries `"convention_is": "provisional"` (the inventory's year-built rows). Each is taken at its two ends: the first and the last of its settings as `_date_values` or `_capacity_values` list them.
- *Defined, for one utility:* take the reference-defining questions that are relevant to the utility (section 5). The reference is defined if the utility's `(place as built, crossing as built)` is identical over every combination of their ends, with everything else at the reference configuration. It is then that place and crossing. If more than twelve such questions are relevant to the utility, the reference is undefined without the search. The output says which case applied and names the questions that leave it undefined.

## 5. Relevance, merged settings and the count, per utility

For one utility `k`:

- *The factor matters to `k`* if the state's factor can move (the conservative check's factor range has `high > low`) and `k` carries permit-based (factor-scaled) load in some configuration.
- *Two settings of a question are the same for `k`* if, for every setting of the same site's other questions, they put the same load on `k` in every panel year (with `k`'s load zero when the site is on another utility or off the panel) and, where the factor matters to `k`, they count the same in the state's 2024 anchoring. Merge them. This is exact: a site's load on another utility reaches `k` only through the anchoring.
- *A question is relevant to `k`* if it has more than one merged setting for `k`.
- *The count* is the product of the numbers of merged settings over `k`'s relevant questions. Compute it as an integer even when it is huge.
- *At or under the ceiling (100,000):* evaluate every configuration of the relevant questions (the others can sit at any setting; use the reference configuration's). **A question is kept for `k` if, for some setting of every other relevant question, two of its merged settings give different outcomes.** Record a witness for each kept question: the two configurations in full (every relevant question's setting, by `fid` and question name, with the setting's actual value) and the two outcomes.
- *Over the ceiling:* `k` keeps the conservative check's kept questions (`joint_check(...)["utilities"]["uid:st"]["kept_questions"]`), marked `method: "conservative"`, with the count. No sampling, no partial enumeration.
- A utility with no relevant question has one configuration, is exact and complete, and keeps nothing.

## 6. The implementation (agent A)

New file `pipeline/facilities/pass_c_exact.py`. It may import and use `pass_c_expand` internals (`_sites`, `_factor`, `_factor_range`, `_date_values`, `_capacity_values`, `joint_check`, `parse_corrections`, `Inputs`, `load_frozen`, `expand`) and `assignment`. Do not change `pass_c_expand.py`, `assignment.py` or any existing test; if one of them seems wrong, stop and report.

```python
CEILING = 100_000
REFERENCE_QUESTION_LIMIT = 12

def exact_attribution(inp, corr, st, theta=0.02, ceiling=CEILING) -> dict
```

`corr` is `pass_c_expand.parse_corrections(...)`'s result. Returns:

```
{"state": st, "theta": theta, "ceiling": ceiling,
 "factor_can_move": bool,
 "questions": [{"fid", "question", "settings"}],            # as the conservative check lists them, unmerged
 "utilities": {"<utility_id_eia>:<state>": {
     "method": "exact" | "conservative",
     "why_conservative": None | str,
     "configurations": int,                                  # the count of section 5, however large
     "complete": bool,                                       # true only when every configuration was evaluated
     "reference": {"defined": bool, "place": str | None, "crossing": "2015" | "never" | None,
                   "why_undefined": None | str, "undefined_by": [{"fid", "question"}]},
     "relevant_questions": [{"fid", "question", "settings": <merged count>}],
     "kept_questions": [{"fid", "question",
                         "witness": {"a": {"settings": {"<fid> <question>": value, ...}, "outcome": {...}},
                                     "b": {"settings": {...}, "outcome": {...}}}}],
     "joins": [fid, ...]}}}
```

For a conservative utility `kept_questions` entries are `{"fid", "question", "channel"}` as the joint check gives them, with no witness. Everything in the result must survive `json.dumps` (off the panel as `"off_panel"`, a missing crossing as `"never"`).

Tests first, in `tests/test_pass_c_exact.py`, on made-up inputs built with `world()` and `mini()` from `tests/test_pass_c_expand.py`. At least: two of four equal sites (all four kept, each with a witness); a crossing that moves by one cohort year only (not kept) and by two (kept); a date that reaches another utility only through the factor; a comparison utility that can and one that cannot reach the floor; an undefined reference; a provisional reference; a count over a small `ceiling` falling back to the conservative result unchanged; merged settings (an assignment question with five candidates counts as two settings for a utility on its list); and that every witness pair differs in exactly the named question. Then the code.

Then a driver in the same file:

```
python3 -I pipeline/facilities/pass_c_exact.py CORRECTIONS.json --targets pipeline/facilities/verified/pass_c_targets.csv \
    --out docs/gate1/<name>.json --csv pipeline/facilities/verified/pass_c_exact_attribution.csv [--also-states AR,CA,GA,NM,NV]
```

- It runs `pass_c_expand.expand` on the corrections (the place test and the conservative check, unchanged) and `exact_attribution` in every state with a correction and every state in `--also-states`. When `--also-states` is not given, it uses the states of the 26 hosts: the rows of `data/frozen/headline_set.csv` at the 2% threshold that are in the headline set or whose only reasons for being out are ruling 4's (`assignment.only_ruling_4`). It checks that this gives 26 and stops in words if not.
- JSON out: `{"expansion": <expand's result>, "exact": {state: <exact_attribution's result>}, "hosts": [...], "counts": {...}}`. It refuses a path under `data/` (`pass_c_expand.check_out_path`).
- CSV out, one row per utility and kept question: `utility, utility_name, one_of_the_26_hosts, method, configurations, complete, reference_defined, reference_place, reference_crossing, site, question, site_state, site_is_on, operator, county, mw_full, already_on_the_target_list, witness` (the witness as compact JSON; empty for a conservative row).
- Printed summary, plain text: for each of the 26 hosts its method, configuration count, reference (or why undefined) and kept sites; then counts: utilities exact and conservative; sites kept for the 26 hosts and how many are not on the target list; sites kept for every utility and how many are not on the list; and, beside each, the conservative check's count for the same utilities so the two can be compared. Counts are reports. None is a target.

Speed matters only enough to finish: Texas has about 150 units and Virginia about 75 date questions (nearly every Virginia utility will be over the ceiling, which is the rule working). Vectorise the evaluation over configurations with numpy; do not evaluate configurations one at a time through `scratch_state`.

Inputs agent A may read: this brief; `docs/DECISIONS.md` from the heading "D-63" rule 7, "D-65" and "D-66" only; `pipeline/facilities/pass_c_expand.py`, `assignment.py`, `buildout.py`; `tests/test_pass_c_expand.py`; and, through `pass_c_expand.load_frozen()` only, `data/interim/facilities.parquet`, `facility_year.parquet`, `state_anchor.parquet`, `epoch_gaps.parquet`, `panel_quantities.parquet`, `utility_year_dose.parquet`, the build-out files `buildout.load()` reads, and `data/frozen/headline_set.csv`. Nothing else under `data/`. Never open, list, link or copy `data/blind`. Make no scratch copy of the repository. Run Python as `python3 -I` from the gizmo folder. Commit nothing.

## 7. The evaluator and the comparison (agent B)

Agent B works in a separate checkout that has no `data/` folder and needs none. It does not see agent A's file and must not look for it.

New file `tests/exhaustive_evaluator.py`:

```python
def pivotal_questions(inp, corrections: list[dict], st: str, theta: float = 0.02) -> dict
# {"configurations": int,
#  "reference": {(utility_id_eia, state): {"defined": bool, "place": str | None, "crossing": float | None}},
#  "pivotal": {(utility_id_eia, state): {(fid, question), ...}}}
```

It is written from sections 1 to 4 of this brief and from nothing in section 5 or 6: no merging, no relevance, no ceiling. It lists every question and every setting itself from the corrections and the inventory (it may call `_date_values` and `_capacity_values` for the lists of years, and `assignment.resolved` and `assignment.candidates`), enumerates the full product over every question in the state, and realises each configuration through `pass_c_expand.scratch_state` and `assignment.evaluate` (the way `_realize` in `tests/test_pass_c_expand.py` does: an assignment setting becomes an `assign` correction for that configuration, and a date or capacity setting goes in `choice`). It computes outcomes from the `as_built` and `no_anchoring` matrices by its own code. The reference is found by its own enumeration of the ends. A question is pivotal for a utility if some two configurations that differ only in it give different outcomes.

New file `tests/test_exhaustive_evaluator.py`: the evaluator checked against answers worked out by hand on cases small enough to do so (two of four equal sites; one site whose date decides a cohort crossing; a comparison utility at the floor).

New file `tests/test_pass_c_exact_against_evaluator.py`: made-up states, built with `world()` and `mini()` from `tests/test_pass_c_expand.py`, each small enough for the full product (a few thousand configurations at most). For each: `pass_c_exact.exact_attribution(inp, parse_corrections(corrections, inp), st)` and `pivotal_questions(inp, corrections, st)`; assert that for every utility the kept set equals the pivotal set, that the references agree, that `complete` is true, and that each witness pair, realised through the evaluator's own realisation, differs in exactly the named question and gives different outcomes. The cases must cover, each in at least one state: a question that is pivotal only at an interior year of its interval; the factor at its cap in every setting, at its floor in every setting, and reaching the cap in some settings only; a permit total that is zero in some setting, and in every setting; a utility with no base or a zero base; a reopened assignment; a date question and a capacity split with `rest_earliest` on one site; a utility at the comparison floor; an undefined reference (a question with no convention that moves a utility's crossing); a provisional reference (`"convention_is": "provisional"`); a date of 2023 or later that reaches another utility only through the factor; an assignment question with several candidates; and "never". Choose made-up numbers so that no load sits within one part in a million of a threshold. This file cannot run in agent B's checkout, because the implementation is not there; write it to the interface in section 6 and say so in the report.

Inputs agent B may read: this brief; `pipeline/facilities/pass_c_expand.py`, `assignment.py`, `buildout.py`; `tests/test_pass_c_expand.py`. No data. Do not create, link or copy a `data/` folder. Run Python as `python3 -I`. Commit the three new files on the checkout's branch and nothing else.

## 8. Reports

Each agent ends with: the model id it ran as; the files it wrote; the tests it ran and their counts; every reading it made that this brief does not settle; and anything in the brief or the existing code it believes is wrong. A report is a claim: the session reruns everything.
