#!/usr/bin/env python3
"""The execution owner's checker: reads what one availability step printed and says what the owner may do next.

    python3 -I pipeline/electricity/availability_run_check.py p1|p2|preserve --log DIR [--before DIR] [--stopped DIR] [--retry]

An aid for whoever carries out Joe's execution instruction, built at his word after the instruction was adopted
(D-80). It is not one of the audit's steps, no step imports it, and it is not pinned. It opens nothing under data/.
It reads four small files the owner captured for one attempt of one step, in DIR:

    <step>.out      the step's standard output
    <step>.err      the step's standard error
    <step>.exit     the step's exit status, as `echo $?` wrote it (empty if the step was killed and none was captured)
    time_<step>.txt the report `/usr/bin/time -l -o` wrote

and, for P2 and preservation, the standard output of the step before (`p1.out` or `p2.out`, in --before DIR, or in
DIR if --before is not given). For a P1 retry, --stopped DIR is the folder of the stopped attempt.

It answers with one of four verdicts, then the facts and its reasons, as plain lines for the run log:

    ADVANCE                   the step exited 0 and everything item 3 of the instruction names holds: exactly its
                              permitted lines, nothing on standard error, within its resource targets, and its
                              identifiers match the step before (for a P1 retry: its three input hashes equal the
                              stopped attempt's).
    DO NOT ADVANCE            the step exited 0 and something in that list does not hold. It returns to Joe.
    RETURN TO JOE             the step stopped, and what it printed settles that it is not to be rerun.
    NOT DECIDED BY THE OUTPUT the step stopped, and nothing it printed rules a rerun out. That is not permission.
                              A rerun is allowed only if all five conditions of section H.3 hold, and the checker
                              can see none of the ones that matter most (above all, whether the cause is known
                              from outside the process).

What it cannot see, and the owner still answers for: that the files are those of the current invocation; that the
checkpoint held; that session 11's confirmation is recorded; and how many times a step has been tried. The
instruction and docs/gate1/availability-audit-route.md, section H.3, govern. Where this checker and they differ,
they are right and the checker is wrong: stop and tell Joe.

It is deliberately one-sided. Anything it does not recognize is RETURN TO JOE or DO NOT ADVANCE, never ADVANCE.

The patterns of each step's permitted success output live here and nowhere else: the process tests and the scale
exercise import them from this module.

Known limits, recorded 2026-11-18 after the one run it was used for (D-83; run log, section 4.3). None is fixed here.
Deal with them before relying on this checker again:

  1. A missing <step>.err is read as empty, so a step whose standard error was never captured passes that test.
     Confirm the file exists.
  2. The definition is matched as any non-blank text. It is not compared between steps, or with
     availability_codes.DEFINITION_VERSION.
  3. P2's eight counts and its row count are matched as digits. They are not added or compared.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.electricity import availability_codes as av  # noqa: E402

ADVANCE, DO_NOT_ADVANCE, RETURN, UNDECIDED = "ADVANCE", "DO NOT ADVANCE", "RETURN TO JOE", "NOT DECIDED BY THE OUTPUT"
STEPS = ("p1", "p2", "preserve")
NAME = {"p1": "P1", "p2": "P2", "preserve": "preservation"}

# The engineering targets of D-75, as the scale exercise measures them. A step that REACHES its time target has
# breached it: the owner interrupts at the target (the instruction, item 7).
TARGETS = {"p1": {"seconds": 20 * 60, "bytes": 8 * 1024 ** 3}, "p2": {"seconds": 120, "bytes": None},
           "preserve": {"seconds": 120, "bytes": None}}

# ---- each step's permitted success output, line by line ---------------------------------------------------
P1_OK = [r"P1 availability flag build, definition \S+",
         r"inputs: sales [0-9a-f]{64} \| succession [0-9a-f]{64} \| quantities [0-9a-f]{64}",
         r"outcomes identical to disk: yes", r"by-unit files identical to disk: yes",
         r"existing quantity columns identical to disk: yes", r"flag equals the analysis filter on every row: yes",
         r"one first exclusion reason per row from the fixed list, consistent with the quantity columns: yes",
         r"wrote: data/interim/panel_quantities\.parquet, data/interim/availability/p1_record\.json \(run [0-9a-f]{32}\)"]
P2_OK = [r"P2 availability audit, definition \S+", r"read: data/interim/panel_quantities\.parquet [0-9a-f]{64} \(run [0-9a-f]{32}\)",
         r"first applicable exclusion reason, utility-years: " + r" \| ".join(rf"{c} \d+" for c in av.ALL_CODES),
         r"wrote: data/interim/availability/outcome_availability\.csv \(\d+ rows\), data/interim/availability/outcome_availability\.json "
         r"\(audit attempt [0-9a-f]{32}\)"]
PRESERVE_FILES = ("outcome_availability.csv", "outcome_availability.json", "p1_record.json")
PRESERVE_OK = [r"preserved run [0-9a-f]{32} \(audit attempt [0-9a-f]{32}\) to .+ \(folder and files readable by this account only\)",
               r"definition \S+"] + [rf"  {re.escape(f)} [0-9a-f]{{64}}" for f in PRESERVE_FILES]
# Printed before the success line by a preservation attempt that removed a stopped attempt's partial folder (Joe,
# D-78: the success line is not always the first line).
PRESERVE_REMOVED = r"removed an incomplete earlier attempt: .+\.partial"
OK = {"p1": P1_OK, "p2": P2_OK, "preserve": PRESERVE_OK}

P1_WROTE = re.compile(r"wrote: .* \(run ([0-9a-f]{32})\)")
P2_READ = re.compile(r"read: .* \(run ([0-9a-f]{32})\)")
P2_WROTE = re.compile(r"wrote: .* \(audit attempt ([0-9a-f]{32})\)")
KEPT = re.compile(r"preserved run ([0-9a-f]{32}) \(audit attempt ([0-9a-f]{32})\) to .+")

# ---- the stop table (route document, section H.3) ---------------------------------------------------------
# Every stage each step can name. A test fails if a step gains or renames a stage and this is not brought up to date.
KNOWN_STAGES = {
    "p1": {"start", "arguments", "guard", "authorization", "isolation", "imports", "inputs", "load", "build", "checks", "identity",
           "record", "mark attempt", "write quantities", "write record"},
    "p2": {"start", "arguments", "guard", "authorization", "isolation", "imports", "the flag build's record", "read", "validate",
           "mask", "sidecar", "mark attempt", "write mask", "write sidecar"},
    "preserve": {"authorization", "verify source", "remove an incomplete earlier attempt", "copy", "verify copy", "manifest",
                 "restrict", "name the folder", "confirm the named folder"},
}
# The stages at which a stop is not, by the table, sent straight back to Joe. Everything else is.
RETRY_NOT_EXCLUDED = {"p1": {"mark attempt"}, "p2": {"mark attempt", "write mask", "write sidecar"},
                      "preserve": {"copy", "verify copy", "manifest", "restrict", "name the folder"}}
# P1 replaces the quantities file, one of its own inputs, before it completes its record (Joe, D-78).
P1_MAY_HAVE_REPLACED = {"write quantities", "write record"}
ALWAYS_RETURN_CLASSES = {"MemoryError": "MemoryError at any stage is a possible resource breach",
                         "NonFinitePrice": "NonFinitePrice: a non-finite constructed price on a priceable row"}
EXITS = {"p1": {1, 2, 3, 4}, "p2": {2, 3, 4}, "preserve": {2, 4, 5}}
CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class Result:
    step: str
    exit_code: int | None
    verdict: str = ""
    problems: list = field(default_factory=list)      # why not ADVANCE; for a stop, why it returns or what is undecided
    notes: list = field(default_factory=list)
    identifiers: dict = field(default_factory=dict)
    seconds: float | None = None
    peak_bytes: int | None = None

    @property
    def reasons(self) -> list:
        return self.problems


def parse_time(text: str) -> tuple[float | None, int | None]:
    """(elapsed seconds, peak resident bytes) from `/usr/bin/time -l`'s report; (None, None) if it is not one."""
    real = re.search(r"^\s*([0-9]+(?:\.[0-9]+)?) real\b", text, flags=re.M)
    peak = re.search(r"^\s*([0-9]+)\s+maximum resident set size", text, flags=re.M)
    if not real or not peak:
        return None, None
    return float(real.group(1)), int(peak.group(1))


def _matches(lines: list, patterns: list) -> bool:
    return len(lines) == len(patterns) and all(re.fullmatch(p, g) for p, g in zip(patterns, lines))


def _first(lines, pattern):
    for ln in lines or []:
        m = pattern.fullmatch(ln)
        if m:
            return m
    return None


def _inputs_line(lines) -> str | None:
    return next((ln for ln in lines or [] if re.fullmatch(P1_OK[1], ln)), None)


def _resources(step: str, seconds, peak) -> list[str]:
    out, tgt = [], TARGETS[step]
    if seconds is not None and seconds >= tgt["seconds"]:
        out.append(f"it reached or passed its time target ({seconds:g} s against {tgt['seconds']} s): a resource breach")
    if peak is not None and tgt["bytes"] is not None and peak > tgt["bytes"]:
        out.append(f"it passed its memory target ({peak} bytes against {tgt['bytes']}): a resource breach")
    return out


def _success(r: Result, lines, stderr, before, stopped, retry) -> None:
    step, p = r.step, r.problems
    body = list(lines)
    if step == "preserve" and body and re.fullmatch(PRESERVE_REMOVED, body[0]):
        body = body[1:]
        if retry:
            r.notes.append("it removed a partial folder left by a stopped attempt, which is permitted only on a retry the instruction's item 5 allows")
        else:
            p.append("it removed a partial folder, so it is a retry, but this run was not declared a retry (--retry)")
    if not _matches(body, OK[step]):
        p.append("its output is not exactly its permitted lines")
    if stderr != "":
        p.append("its standard error is not empty")
    if r.seconds is None or r.peak_bytes is None:
        p.append("its timing report could not be read, so its resource targets cannot be shown to hold")
    p.extend(_resources(step, r.seconds, r.peak_bytes))
    if step == "p1":
        m = _first(body, P1_WROTE)
        if m:
            r.identifiers["run"] = m.group(1)
        if retry:
            if stopped is None:
                p.append("this is a retry, and the stopped attempt's output was not supplied (--stopped), so its input hashes cannot be compared")
            elif _inputs_line(stopped) is None:
                r.notes.append("the stopped attempt printed no inputs line: it wrote nothing, and this run's inputs line is the one recorded")
            elif _inputs_line(stopped) != _inputs_line(body):
                p.append("its input hashes differ from the stopped attempt's: the mismatch is never waived, and this returns to Joe")
    elif step == "p2":
        run, att, was = _first(body, P2_READ), _first(body, P2_WROTE), _first(before, P1_WROTE)
        if run:
            r.identifiers["run"] = run.group(1)
        if att:
            r.identifiers["audit_attempt"] = att.group(1)
        if was is None:
            p.append("the step before (P1) printed no success line to match: its output was not supplied, or it did not succeed")
        elif run and run.group(1) != was.group(1):
            p.append("the run identifier on its \"read:\" line is not the one in P1's \"wrote:\" line")
    else:
        kept, run, att = _first(body, KEPT), _first(before, P2_READ), _first(before, P2_WROTE)
        if kept:
            r.identifiers.update(run=kept.group(1), audit_attempt=kept.group(2))
        if run is None or att is None:
            p.append("the step before (P2) printed no success line to match: its output was not supplied, or it did not succeed")
        elif kept:
            if kept.group(1) != run.group(1):
                p.append("the run identifier on its success line is not the one on P2's \"read:\" line")
            if kept.group(2) != att.group(1):
                p.append("the audit attempt on its success line is not the one in P2's \"wrote:\" line")
    r.verdict = ADVANCE if not p else DO_NOT_ADVANCE


def _conditions(step: str) -> list[str]:
    out = ["nothing it printed rules a rerun out. That is not permission. Rerun only if all five conditions of section H.3 hold:",
           "  1. the cause is known from outside the process (the owner interrupted it by hand, the machine slept, or it lost power)",
           "  2. nothing suggests a resource breach (an interrupt at the time target is a breach; so is a kill the owner cannot explain)",
           "  3. there is no discrepancy of any kind",
           "  4. the code, the environment and the inputs are unchanged"
           + (" (for P1: a rerun's three input hashes must equal the stopped attempt's; check it with --stopped)" if step == "p1" else ""),
           "  5. this step has not been retried before in any session"
           + (", and no final folder exists at the destination" if step == "preserve" else ""),
           "Otherwise it returns to Joe."]
    return out


def _stop(r: Result, lines, stderr) -> None:
    step, code, back, undecided = r.step, r.exit_code, [], False
    if stderr != "":
        back.append("its standard error is not empty")
    back.extend(_resources(step, r.seconds, r.peak_bytes))
    killed = code is None or code < 0 or code > 128
    inputs_printed = step == "p1" and _inputs_line(lines) is not None
    if killed:
        if inputs_printed:
            back.append("it ended with no stop line after it printed its inputs line: it may have replaced the quantities file, one of its own inputs")
        else:
            r.notes.append("it ended with no exit status of its own (killed, or ended by a signal). A kill the owner cannot explain returns to Joe")
            undecided = True
    elif code not in EXITS[step]:
        back.append(f"exit {code} is not an exit this step uses: not recognized")
    elif code in (3, 4):
        back.append(f"exit {code}: " + ("operating-system isolation is not in force or cannot be shown" if code == 3 else
                                        "not authorized, or code, a library or the interpreter is not as pinned, or the command was not as written"))
    elif code == 5:
        back.append("it stopped after the folder was named: the final folder exists. It is never rerun, and nothing is repaired by hand")
    elif code == 1:
        back.append("a check answered no" if lines and lines[-1] == "wrote nothing" else "exit 1 without \"wrote nothing\": not recognized")
    else:                                                               # exit 2: one stop line, after any status lines
        last = lines[-1] if lines else ""
        if step == "preserve":
            m = re.fullmatch(r"nothing preserved by this attempt: stopped at (.+?): (.+)", last)
            refusal = m is None and last.startswith("nothing preserved by this attempt: ")
        else:
            m = re.fullmatch(rf"{NAME[step]} stopped at (.+?): (.+)", last)
            refusal = False
        if refusal:
            back.append("a refusal: " + last.split(": ", 1)[1])
        elif m is None:
            back.append("it ended with no stop line after it printed its inputs line: it may have replaced the quantities file, one of its own inputs"
                        if inputs_printed else "its last line is not a stop line this step prints: not recognized")
        else:
            stage, what = m.group(1), m.group(2)
            if stage not in KNOWN_STAGES[step]:
                back.append(f"stage {stage} is not one this step names: not recognized")
            elif not CLASS.fullmatch(what):
                back.append("a refusal: " + what)
            elif what in ALWAYS_RETURN_CLASSES:
                back.append(ALWAYS_RETURN_CLASSES[what])
            elif step == "p1" and stage in P1_MAY_HAVE_REPLACED:
                back.append(f"it stopped at {stage}: it may have replaced the quantities file, one of its own inputs, so a rerun's input "
                            "hashes could not be shown equal to this attempt's. Not retried")
            elif stage in RETRY_NOT_EXCLUDED[step]:
                undecided = True
            else:
                back.append(f"stage {stage}: the stop table sends a stop at this stage back to Joe")
    if back:
        r.verdict, r.problems = RETURN, back
    elif undecided:
        r.verdict, r.problems = UNDECIDED, _conditions(step)
    else:                                                               # unreachable by construction; never ADVANCE
        r.verdict, r.problems = RETURN, ["not recognized"]


def check(step: str, exit_code: int | None, lines: list, stderr: str, time_text: str, before: list | None = None,
          stopped: list | None = None, retry: bool = False) -> Result:
    """The verdict for one attempt of one step. `lines` is its standard output, split; `before` the step before's;
    `stopped` the stopped attempt's, for a P1 retry."""
    if step not in STEPS:
        raise ValueError(step)
    r = Result(step=step, exit_code=exit_code)
    r.seconds, r.peak_bytes = parse_time(time_text)
    if exit_code == 0:
        _success(r, lines, stderr, before, stopped, retry or stopped is not None)
    else:
        if r.seconds is None:
            r.notes.append("its timing report could not be read")
        _stop(r, lines, stderr)
    return r


def report(r: Result) -> str:
    tgt = TARGETS[r.step]
    out = [f"{r.step}: {r.verdict}",
           f"exit {'none captured' if r.exit_code is None else r.exit_code}; "
           + (f"{r.seconds:g} s (target {tgt['seconds']} s); peak {r.peak_bytes} bytes "
              f"({'no memory target' if tgt['bytes'] is None else 'target ' + str(tgt['bytes'])})" if r.seconds is not None
              else "no timing report read")]
    if r.identifiers:
        out.append("identifiers: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in r.identifiers.items()))
    out += [("- " + x if not x.startswith("  ") else x) for x in r.problems]
    out += ["note: " + n for n in r.notes]
    out.append("(Reads only what the step printed. The instruction and the route document's section H.3 govern.)")
    return "\n".join(out)


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Check one attempt of one availability step from its captured output.")
    ap.add_argument("step", choices=STEPS)
    ap.add_argument("--log", required=True, help="folder holding <step>.out, <step>.err, <step>.exit and time_<step>.txt for this attempt")
    ap.add_argument("--before", help="folder holding the step before's .out file (default: --log)")
    ap.add_argument("--stopped", help="for a P1 retry: the folder of the stopped attempt")
    ap.add_argument("--retry", action="store_true", help="this attempt is a retry the instruction's item 5 allows")
    a = ap.parse_args(argv)
    log = Path(a.log)
    if not (log / f"{a.step}.out").exists():
        print(f"{a.step}: {RETURN}\n- {log / (a.step + '.out')} does not exist: nothing to check")
        return 1
    raw = _read(log / f"{a.step}.exit").strip()
    code = int(raw) if re.fullmatch(r"-?\d+", raw) else None
    prior = {"p2": "p1", "preserve": "p2"}.get(a.step)
    before = _read(Path(a.before or a.log) / f"{prior}.out").splitlines() if prior else None
    stopped = _read(Path(a.stopped) / f"{a.step}.out").splitlines() if a.stopped else None
    r = check(a.step, code, _read(log / f"{a.step}.out").splitlines(), _read(log / f"{a.step}.err"), _read(log / f"time_{a.step}.txt"),
              before=before, stopped=stopped, retry=a.retry)
    print(report(r))
    return 0 if r.verdict == ADVANCE else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
