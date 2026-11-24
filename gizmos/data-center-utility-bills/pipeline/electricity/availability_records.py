"""What a reader requires of the provenance in P1's record and in the sidecar, in one place (D-76, G2).

Pure: no I/O, and nothing imported from the pipeline but the constants. The flag build (P1) and the audit (P2) run
these checks on the record they are about to write, before they replace anything; the audit runs them on P1's
record; the preservation step runs them on both records. One set of checks, so the writers and the readers cannot
drift apart.

Each function returns a list of problems, in words that name files and fields only. An empty list means the
fields below are present, well formed and consistent. It does NOT mean every field of the record was checked.

Required and checked here:
- the analysis filter, which must be this code's fixed text;
- the input hashes (P1: sales, succession, quantities, outcomes; the sidecar: quantities, p1_record), each present
  and well formed, and exactly those;
- the sidecar's two copies of the hash of P1's record, which must agree, and its copy of P1's fields, each of which
  must equal P1's record;
- the interpreter, library versions and sandbox profile each record says it ran with, against the pin block of the
  authorizing entry (Joe's choice, D-76);
- the hash of the authorizing entry's text each record carries, against the entry as it stands now (D-76, G8).

Recorded by the writers and NOT independently validated by any reader: the values of the sales, succession,
outcomes and pre-write quantities hashes (no later step may read those files, or the pre-write file no longer
exists); the git commit; the list of pinned files; the count of by-unit files; the declared native reads; the
recorded access events; and, in the sidecar, the order of reasons, the counts, the explanatory notes, the years and
the columns read. That is a limit of the readers, not evidence about the writers.

The statuses, identifiers, schema and definition versions, the five named checks, the authorization's name and the
hashes that link the three files are checked where they always were: in the audit's `check_p1_record` and in the
preservation step's `verify_bundle`.
"""
from __future__ import annotations

import re

from pipeline.electricity import availability_codes as av

HEX32, HEX64 = re.compile(r"[0-9a-f]{32}"), re.compile(r"[0-9a-f]{64}")


def is_hex(value, pattern=HEX64) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _hashes_ok(value, names) -> bool:
    return isinstance(value, dict) and set(value) == set(names) and all(is_hex(value[n]) for n in names)


def _pinned(rec: dict, who: str, libraries, profile: str, pins: dict) -> list[str]:
    """The interpreter, versions and profile `rec` says it ran with, against the pin block. Nothing passes because two
    missing values compare equal: each recorded value must be a string and equal a pinned string."""
    out = []
    want = pins.get("interpreter")
    if not (isinstance(rec.get("interpreter"), str) and isinstance(want, str) and rec["interpreter"] == want):
        out.append(f"{who} does not record the pinned interpreter")
    have, pinned = rec.get("versions"), pins.get("versions") or {}
    if not (isinstance(have, dict) and set(have) == set(libraries)
            and all(isinstance(have[lib], str) and isinstance(pinned.get(lib), str) and have[lib] == pinned[lib] for lib in libraries)):
        out.append(f"{who} does not record every library it used at its pinned version")
    if not (is_hex(rec.get("sandbox_profile_sha256")) and rec["sandbox_profile_sha256"] == (pins.get("files") or {}).get(profile)):
        out.append(f"{who} does not record the pinned sandbox profile")
    if not (is_hex(rec.get("authorization_entry_sha256")) and rec["authorization_entry_sha256"] == pins.get("entry_sha256")):
        out.append(f"{who} was not made under this text of the authorizing entry (the entry has changed since, or no hash of it is recorded)")
    return out


def p1_provenance_problems(p1, pins: dict) -> list[str]:
    """Problems in the provenance of P1's record, against the pin block `pins` (as check_authorization returns it)."""
    who = "P1's record"
    if not isinstance(p1, dict):
        return [f"{who} is not a record"]
    out = []
    if p1.get("analysis_filter") != av.ANALYSIS_FILTER:
        out.append(f"{who} does not carry this code's analysis filter")
    if not _hashes_ok(p1.get("inputs_sha256"), av.P1_INPUT_HASHES):
        out.append(f"{who} does not carry a well-formed hash for each of its four inputs ({', '.join(av.P1_INPUT_HASHES)}), and only those")
    return out + _pinned(p1, who, av.P1_LIBRARIES, av.P1_PROFILE, pins)


def sidecar_provenance_problems(side, p1, pins: dict) -> list[str]:
    """Problems in the provenance of the sidecar, against P1's record `p1` and the pin block `pins`."""
    who = "the sidecar"
    if not isinstance(side, dict):
        return [f"{who} is not a record"]
    out = []
    if side.get("analysis_filter") != av.ANALYSIS_FILTER:
        out.append(f"{who} does not carry this code's analysis filter")
    inputs = side.get("inputs_sha256")
    if not _hashes_ok(inputs, av.P2_INPUT_HASHES):
        out.append(f"{who} does not carry a well-formed hash for each of its two inputs ({', '.join(av.P2_INPUT_HASHES)}), and only those")
    copy = inputs.get("p1_record") if isinstance(inputs, dict) else None
    if not (is_hex(copy) and is_hex(side.get("p1_record_sha256")) and copy == side["p1_record_sha256"]):
        out.append(f"{who}'s two copies of the hash of P1's record disagree, or one is missing")
    fb = side.get("flag_build")
    if not (isinstance(fb, dict) and isinstance(p1, dict) and set(fb) == set(av.SIDECAR_FLAG_BUILD_KEYS)
            and all(k in p1 and fb[k] == p1[k] for k in av.SIDECAR_FLAG_BUILD_KEYS)):
        out.append(f"{who}'s copy of P1's fields is not P1's record's")
    return out + _pinned(side, who, av.P2_LIBRARIES, av.P2_PROFILE, pins)
