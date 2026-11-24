"""The execution owner's output checker (pipeline/electricity/availability_run_check.py), on made-up output.

The checker reads only what a step printed and what /usr/bin/time reported about it. These tests give it made-up
lines for every row of the stop table in docs/gate1/availability-audit-route.md, section H.3, and for every way a
step that exited 0 can still fail the advancement rule. The checker run against real processes, captured the way
the run log's commands capture them, is in test_availability_runs.py. Nothing here opens a file under data/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from pipeline.electricity import availability_codes as av  # noqa: E402
from pipeline.electricity import availability_run_check as chk  # noqa: E402

RUN, RUN2, ATT = "a" * 32, "b" * 32, "c" * 32
H = {k: k * 64 for k in "123456"}
FOLDER = "/made-up/access-records/2026-11-16-availability-aaaaaaaa-cccccccc"


def p1_lines(run=RUN, quantities=H["3"], **answers) -> list[str]:
    yn = lambda k: answers.get(k, "yes")  # noqa: E731
    return [f"P1 availability flag build, definition {av.DEFINITION_VERSION}",
            f"inputs: sales {H['1']} | succession {H['2']} | quantities {quantities}",
            f"outcomes identical to disk: {yn('outcomes')}", "by-unit files identical to disk: yes",
            "existing quantity columns identical to disk: yes", "flag equals the analysis filter on every row: yes",
            "one first exclusion reason per row from the fixed list, consistent with the quantity columns: yes",
            f"wrote: data/interim/panel_quantities.parquet, data/interim/availability/p1_record.json (run {run})"]


def p2_lines(run=RUN, attempt=ATT) -> list[str]:
    return [f"P2 availability audit, definition {av.DEFINITION_VERSION}",
            f"read: data/interim/panel_quantities.parquet {H['4']} (run {run})",
            "first applicable exclusion reason, utility-years: " + " | ".join(f"{c} {i}" for i, c in enumerate(av.ALL_CODES)),
            "wrote: data/interim/availability/outcome_availability.csv (82500 rows), data/interim/availability/outcome_availability.json "
            f"(audit attempt {attempt})"]


def keep_lines(run=RUN, attempt=ATT, removed=False) -> list[str]:
    out = [f"removed an incomplete earlier attempt: {FOLDER}.partial"] if removed else []
    return out + [f"preserved run {run} (audit attempt {attempt}) to {FOLDER} (folder and files readable by this account only)",
                  f"definition {av.DEFINITION_VERSION}"] + [f"  {f} {H['5']}" for f in chk.PRESERVE_FILES]


TIME_OK = "       13.52 real        11.02 user         2.31 sys\n          1552072704  maximum resident set size\n                   0  average shared memory size\n"


def result(step, lines, exit_code=0, stderr="", time_text=TIME_OK, **kw):
    return chk.check(step, exit_code, lines, stderr, time_text, **kw)


# ---- the timing report ------------------------------------------------------------------------------------

def test_the_timing_report_is_parsed_and_an_unreadable_one_is_not_guessed():
    assert chk.parse_time(TIME_OK) == (13.52, 1552072704)
    assert chk.parse_time("") == (None, None) and chk.parse_time("something else\n") == (None, None)
    assert chk.TARGETS["p1"] == {"seconds": 1200, "bytes": 8 * 1024 ** 3}
    assert chk.TARGETS["p2"] == chk.TARGETS["preserve"] == {"seconds": 120, "bytes": None}


# ---- a step that exited 0: advance only if everything the instruction's item 3 names holds -----------------

def test_a_clean_run_of_each_step_may_advance():
    a = result("p1", p1_lines())
    assert a.verdict == chk.ADVANCE and a.problems == [] and a.identifiers == {"run": RUN}
    b = result("p2", p2_lines(), before=p1_lines())
    assert b.verdict == chk.ADVANCE and b.identifiers == {"run": RUN, "audit_attempt": ATT}
    c = result("preserve", keep_lines(), before=p2_lines())
    assert c.verdict == chk.ADVANCE and c.identifiers == {"run": RUN, "audit_attempt": ATT}
    assert (a.seconds, a.peak_bytes) == (13.52, 1552072704)


@pytest.mark.parametrize("step, lines, kw, words", [
    ("p1", p1_lines() + ["one more line"], {}, "not exactly its permitted lines"),
    ("p1", p1_lines()[:-1], {}, "not exactly its permitted lines"),
    ("p1", [x.replace("definition ", "definition  ") for x in p1_lines()], {}, "not exactly its permitted lines"),
    ("p1", p1_lines(), {"stderr": "a warning\n"}, "standard error is not empty"),
    ("p1", p1_lines(), {"time_text": ""}, "timing report could not be read"),
    ("p1", p1_lines(), {"time_text": TIME_OK.replace("13.52 real", "1200.01 real")}, "time target"),
    ("p1", p1_lines(), {"time_text": TIME_OK.replace("1552072704", str(8 * 1024 ** 3 + 1))}, "memory target"),
    ("p2", p2_lines(), {"time_text": TIME_OK.replace("13.52 real", "120.5 real"), "before": p1_lines()}, "time target"),
    ("p2", p2_lines(run=RUN2), {"before": p1_lines()}, "run identifier"),
    ("p2", p2_lines(), {}, "the step before"),                                              # P1's output not supplied
    ("p2", p2_lines(), {"before": p1_lines()[:-1]}, "the step before"),                     # P1 printed no success line
    ("preserve", keep_lines(run=RUN2), {"before": p2_lines()}, "run identifier"),
    ("preserve", keep_lines(attempt="d" * 32), {"before": p2_lines()}, "audit attempt"),
    ("preserve", keep_lines() + ["  another.csv " + H["6"]], {"before": p2_lines()}, "not exactly its permitted lines"),
    ("preserve", keep_lines(removed=True), {"before": p2_lines()}, "not declared a retry"),
])
def test_a_step_that_exited_0_does_not_advance_when(step, lines, kw, words):
    r = result(step, lines, **kw)
    assert r.verdict == chk.DO_NOT_ADVANCE and any(words in p for p in r.problems), r.problems


def test_preservations_success_line_is_matched_wherever_it_stands():
    """Joe, D-78: after an allowed retry the success line is not the first line."""
    r = result("preserve", keep_lines(removed=True), before=p2_lines(), retry=True)
    assert r.verdict == chk.ADVANCE and r.identifiers == {"run": RUN, "audit_attempt": ATT}
    assert any("removed a partial folder" in n for n in r.notes)


def test_a_p1_retry_must_print_the_stopped_attempts_three_input_hashes():
    stopped = p1_lines()[:2] + ["P1 stopped at mark attempt: KeyboardInterrupt"]
    assert result("p1", p1_lines(), stopped=stopped, retry=True).verdict == chk.ADVANCE
    r = result("p1", p1_lines(quantities=H["6"]), stopped=stopped, retry=True)
    assert r.verdict == chk.DO_NOT_ADVANCE and any("input hashes differ from the stopped attempt's" in p for p in r.problems)
    early = ["P1 stopped at imports: KeyboardInterrupt"]                                  # it printed no inputs line: nothing to compare
    r = result("p1", p1_lines(), stopped=early, retry=True)
    assert r.verdict == chk.ADVANCE and any("printed no inputs line" in n for n in r.notes)
    r = result("p1", p1_lines(), retry=True)                                              # a retry with nothing to compare against
    assert r.verdict == chk.DO_NOT_ADVANCE and any("stopped attempt's output" in p for p in r.problems)


# ---- a step that stopped: the table in section H.3, row by row ---------------------------------------------

P1_HEAD = p1_lines()[:2]


@pytest.mark.parametrize("step, exit_code, lines, verdict, words", [
    # the launcher
    ("p1", 4, ["usage: run_availability.sh p1|p2 --authorized-by D-NN"], chk.RETURN, "exit 4"),
    ("p2", 3, ["run_availability.sh stopped: the probe file is not readable outside the sandbox"], chk.RETURN, "exit 3"),
    # any step: authorization, pins, interpreter, libraries, isolation
    ("p1", 4, ["P1 stopped at authorization: not authorized: this is not the pinned interpreter"], chk.RETURN, "exit 4"),
    ("p2", 3, ["P2 stopped at isolation: operating-system isolation is not in force (the probe file is readable): stopped"], chk.RETURN, "exit 3"),
    # P1: a check "no"
    ("p1", 1, p1_lines(outcomes="no")[:-1] + ["wrote nothing"], chk.RETURN, "a check answered no"),
    # P1: before anything is written
    ("p1", 2, P1_HEAD + ["P1 stopped at build: NonFinitePrice"], chk.RETURN, "NonFinitePrice"),
    ("p1", 2, P1_HEAD + ["P1 stopped at build: ValueError"], chk.RETURN, "stage build"),
    ("p1", 2, P1_HEAD + ["P1 stopped at identity: KeyboardInterrupt"], chk.RETURN, "stage identity"),
    ("p1", 2, P1_HEAD + ["P1 stopped at load: the raw sales file changed while it was being read: stopped"], chk.RETURN, "a refusal"),
    ("p1", 2, P1_HEAD + ["P1 stopped at load: an observation flag outside true, false or missing: stopped"], chk.RETURN, "a refusal"),
    ("p1", 2, p1_lines()[:-1] + ["P1 stopped at record: the record this build would write does not pass the readers' checks (x): stopped"],
     chk.RETURN, "a refusal"),
    ("p1", 2, P1_HEAD + ["P1 stopped at load: MemoryError"], chk.RETURN, "MemoryError"),
    # P1: its three writes
    ("p1", 2, p1_lines()[:-1] + ["P1 stopped at mark attempt: OSError"], chk.UNDECIDED, "five conditions"),
    ("p1", 2, p1_lines()[:-1] + ["P1 stopped at mark attempt: MemoryError"], chk.RETURN, "MemoryError"),
    ("p1", 2, p1_lines()[:-1] + ["P1 stopped at write quantities: KeyboardInterrupt"], chk.RETURN, "may have replaced the quantities file"),
    ("p1", 2, p1_lines()[:-1] + ["P1 stopped at write record: OSError"], chk.RETURN, "may have replaced the quantities file"),
    # P1: ended with no stop line
    ("p1", 137, P1_HEAD, chk.RETURN, "no stop line after it printed its inputs line"),
    ("p1", None, p1_lines()[:-1], chk.RETURN, "no stop line after it printed its inputs line"),
    ("p1", 137, [], chk.UNDECIDED, "five conditions"),
    ("p1", 2, p1_lines()[:-1], chk.RETURN, "no stop line after it printed its inputs line"),
    # P2
    ("p2", 2, ["P2 stopped at the flag build's record: the flag build's record is not marked completed (an attempt stopped part way): rerun P1"],
     chk.RETURN, "a refusal"),
    ("p2", 2, ["P2 stopped at the flag build's record: FileNotFoundError"], chk.RETURN, "stage the flag build's record"),
    ("p2", 2, p2_lines()[:2] + ["P2 stopped at validate: duplicate utility-state-year keys: first at 1:GA:2020"], chk.RETURN, "a refusal"),
    ("p2", 2, p2_lines()[:2] + ["P2 stopped at mask: MemoryError"], chk.RETURN, "MemoryError"),
    ("p2", 2, p2_lines()[:2] + ["P2 stopped at mark attempt: OSError"], chk.UNDECIDED, "five conditions"),
    ("p2", 2, p2_lines()[:2] + ["P2 stopped at write mask: KeyboardInterrupt"], chk.UNDECIDED, "five conditions"),
    ("p2", 2, p2_lines()[:2] + ["P2 stopped at write sidecar: OSError"], chk.UNDECIDED, "five conditions"),
    ("p2", 143, p2_lines()[:2], chk.UNDECIDED, "five conditions"),
    # preservation
    ("preserve", 4, ["nothing preserved by this attempt: not authorized: D-80 does not pin pipeline/electricity/availability_records.py"],
     chk.RETURN, "exit 4"),
    ("preserve", 2, ["nothing preserved by this attempt: inconsistent bundle: the sidecar does not say the audit completed"], chk.RETURN, "a refusal"),
    ("preserve", 2, [f"nothing preserved by this attempt: {FOLDER} already exists; a preserved copy is never overwritten, and an attempt "
                     "that finds one is not retried: this stop returns to Joe"], chk.RETURN, "a refusal"),
    ("preserve", 2, ["nothing preserved by this attempt: stopped at copy: OSError"], chk.UNDECIDED, "five conditions"),
    ("preserve", 2, ["nothing preserved by this attempt: stopped at restrict: PermissionError"], chk.UNDECIDED, "five conditions"),
    ("preserve", 2, ["nothing preserved by this attempt: stopped at name the folder: OSError"], chk.UNDECIDED, "five conditions"),
    ("preserve", 2, ["nothing preserved by this attempt: stopped at verify copy: MemoryError"], chk.RETURN, "MemoryError"),
    ("preserve", 2, ["nothing preserved by this attempt: stopped at verify source: OSError"], chk.RETURN, "stage verify source"),
    ("preserve", 2, ["nothing preserved by this attempt: stopped at remove an incomplete earlier attempt: OSError"], chk.RETURN,
     "stage remove an incomplete earlier attempt"),
    ("preserve", 5, [f"preservation stopped after the folder was named: {FOLDER} exists and holds the verified copy, but the step stopped at "
                     "confirm the named folder: OSError. This is not a completed preservation. Do not rerun: this stop returns to Joe"],
     chk.RETURN, "never rerun"),
    ("preserve", 137, [], chk.UNDECIDED, "no final folder exists"),
    # anything the checker does not recognize is never waved through
    ("p1", 2, ["something unexpected"], chk.RETURN, "not recognized"),
    ("p2", 7, ["P2 stopped at mark attempt: OSError"], chk.RETURN, "exit 7"),
])
def test_a_stopped_step_is_classified_as_the_stop_table_says(step, exit_code, lines, verdict, words):
    r = result(step, lines, exit_code=exit_code)
    assert r.verdict == verdict, (r.verdict, r.reasons)
    assert any(words in x for x in r.reasons), r.reasons
    assert r.verdict != chk.ADVANCE


def test_a_stopped_step_past_a_resource_target_returns_whatever_else_it_printed():
    lines = p2_lines()[:2] + ["P2 stopped at write mask: KeyboardInterrupt"]              # the owner's interrupt at the time target
    r = result("p2", lines, exit_code=2, time_text=TIME_OK.replace("13.52 real", "120.00 real"))
    assert r.verdict == chk.RETURN and any("time target" in x for x in r.reasons)
    r = result("p1", p1_lines()[:-1] + ["P1 stopped at mark attempt: OSError"], exit_code=2,
               time_text=TIME_OK.replace("1552072704", str(9 * 1024 ** 3)))
    assert r.verdict == chk.RETURN and any("memory target" in x for x in r.reasons)


def test_anything_on_standard_error_from_a_stopped_step_returns():
    r = result("p2", p2_lines()[:2] + ["P2 stopped at mark attempt: OSError"], exit_code=2, stderr="Killed: 9\n")
    assert r.verdict == chk.RETURN and any("standard error" in x for x in r.reasons)


def test_the_undecided_verdict_spells_out_the_conditions_and_never_says_retry():
    r = result("p2", p2_lines()[:2] + ["P2 stopped at write sidecar: OSError"], exit_code=2)
    text = "\n".join(r.reasons)
    for needle in ("known from outside the process", "resource breach", "no discrepancy", "unchanged", "not been retried before in any session",
                   "Otherwise it returns to Joe"):
        assert needle in text, needle
    assert chk.UNDECIDED == "NOT DECIDED BY THE OUTPUT" and "retry it" not in text.lower()


def test_every_stage_the_steps_can_name_is_one_the_checker_knows():
    """If a step gains or renames a stage, this fails until the checker's table is brought up to date."""
    src = {"p1": "write_usable_flag.py", "p2": "audit_availability.py", "preserve": "preserve_availability.py"}
    for step, name in src.items():
        stages = set(re.findall(r'stage\[0\] = "([^"]+)"', (ROOT / "pipeline/electricity" / name).read_text()))
        assert stages and stages <= chk.KNOWN_STAGES[step], stages - chk.KNOWN_STAGES[step]
        assert chk.RETRY_NOT_EXCLUDED[step] <= chk.KNOWN_STAGES[step]


def test_the_report_is_plain_lines_fit_for_the_run_log():
    r = result("p2", p2_lines(), before=p1_lines())
    text = chk.report(r)
    assert text.splitlines()[0] == "p2: ADVANCE" and f"run {RUN}" in text and f"audit attempt {ATT}" in text
    assert "13.52 s" in text and "1552072704 bytes" in text
    r = result("p1", P1_HEAD + ["P1 stopped at build: NonFinitePrice"], exit_code=2)
    assert chk.report(r).splitlines()[0] == "p1: RETURN TO JOE"
