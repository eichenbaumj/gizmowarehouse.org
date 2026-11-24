#!/usr/bin/env python3
"""After an authorized run: a durable, restricted copy of the availability mask, its sidecar and P1's record.

D-70 item 7 as amended by D-72 item 2, with D-74's repairs as D-75 adopted them and D-76's corrections: the mask and
sidecar stay in ignored storage (data/interim/availability/) for now; a durable copy is kept outside the
repository, readable by Joe's account only, and its hashes and definition go into the ledger. Publishing or
committing them is a separate decision.

    python3 -I pipeline/electricity/preserve_availability.py --authorized-by D-NN [--to DIR]

It refuses unless the entry named pins this step's code, the interpreter and Python's version, and unless the three
files are ONE completed run under THAT entry as it stands now (verify_bundle). The fields verify_bundle tests must
each be present and well formed, and nothing passes because two missing values compare equal; the fields it does
not test are recorded, not validated (availability_records.py lists both).

Order of work. It copies into "<name>.partial"; verifies the copy itself as a bundle and against the source's
hashes; writes the manifest; makes the files read-only, then the folder; and only then renames the folder to its
final name, which is the last change it makes. It then confirms the named folder. So a folder under the final
name is always complete and restricted: there is no moment at which it is named and still open (D-76, G7). A
final folder is never overwritten. A ".partial" folder left by an earlier attempt that stopped is not a preserved
copy: the next attempt removes it and says so. Only one attempt at a time (D-75; the checkpoint).

Permitted output, and nothing else:
- success (exit 0): if it applies, "removed an incomplete earlier attempt: <folder>"; then "preserved run <id>
  (audit attempt <id>) to <folder> (folder and files readable by this account only)", "definition <version>", and
  one line "  <file> <sha256>" per file;
- a stop before the folder is named (exit 4 for authorization or pins, 2 otherwise): one line, "nothing preserved
  by this attempt: <refusal>" or "nothing preserved by this attempt: stopped at <stage>: <exception class name>".
  A ".partial" folder may remain. An earlier attempt's final folder, if there is one, is untouched and is what the
  refusal names;
- a stop after the folder is named (exit 5): one line, "preservation stopped after the folder was named: <folder>
  exists and holds the verified copy, but the step stopped at <stage>: <exception class name>. This is not a
  completed preservation. Do not rerun: this stop returns to Joe".
A process killed outright prints nothing; what it left is a ".partial" folder or a final folder.

Whether a stopped attempt may be rerun is the execution instruction's rule, not this script's: a stop returns to Joe
unless its cause is known from outside the process, and a final folder that already exists always returns to him.

Reads (D-76, G6). This step runs outside the sandbox (it writes outside the repository) and installs no audit hook.
It reads the ledger, its pinned code, the three files of the bundle and its own copies of them. Within one
verification each file is read once, and what is hashed is what was parsed. The copy is a separate read of the
source, which is why the copy is verified again and compared with the first verification's hashes. The pin checks
and the import of the code they cover are separate reads too. The no-writer agreement covers those gaps; the route
is not an immutable snapshot.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.electricity import access_guard as guard  # noqa: E402
from pipeline.electricity import availability_codes as av  # noqa: E402
from pipeline.electricity import availability_records as records  # noqa: E402

SOURCE = ROOT / "data" / "interim" / "availability"
LEDGER = ROOT / "docs" / "DECISIONS.md"
FILES = ("outcome_availability.csv", "outcome_availability.json", "p1_record.json")
PRESERVED = (*FILES, "MANIFEST.json")
HEX32, HEX64 = records.HEX32, records.HEX64


class BundleRefused(Exception):
    """The three files are not one completed, consistent run. The message names files and fields only."""


class NotConfirmed(OSError):
    """The folder under its final name is not the complete, restricted folder this step made."""


class LateFailure(Exception):
    """The step stopped after the folder took its final name. The folder exists; the step did not complete."""

    def __init__(self, folder: str, stage: str, cause: str):
        super().__init__(f"{folder} exists; stopped at {stage}: {cause}")
        self.folder, self.stage, self.cause = folder, stage, cause


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hex(value, pattern) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def verify_bundle(source: Path, entry: str, pins: dict) -> dict:
    """The run's identifiers if the three files are one completed, consistent run under `entry` as it stands now;
    BundleRefused otherwise, listing every problem found. `pins` is the entry's pin block as check_authorization
    returns it. Each file is read once: what is hashed is what is parsed."""
    missing = [f for f in FILES if not (source / f).exists()]
    if missing:
        raise BundleRefused(f"incomplete bundle: missing {missing}")
    raw = {f: (source / f).read_bytes() for f in FILES}
    hashes = {f: hashlib.sha256(raw[f]).hexdigest() for f in FILES}
    try:
        side = json.loads(raw["outcome_availability.json"])
        p1 = json.loads(raw["p1_record.json"])
        rows = raw["outcome_availability.csv"].decode("utf-8").splitlines()
    except ValueError:
        raise BundleRefused("the mask, the sidecar or P1's record is not readable") from None
    if not isinstance(side, dict) or not isinstance(p1, dict):
        raise BundleRefused("the sidecar or P1's record is not a record")
    problems = []
    if side.get("status") != av.COMPLETED:
        problems.append("the sidecar does not say the audit completed")
    if p1.get("status") != av.COMPLETED:
        problems.append("P1's record does not say the flag build completed")
    if (side.get("schema_version"), side.get("mask_schema_version"), side.get("quantities_columns_schema_version")) != (
            av.SCHEMA_VERSIONS["sidecar"], av.SCHEMA_VERSIONS["mask"], av.SCHEMA_VERSIONS["quantities_columns"]):
        problems.append("the sidecar's schema versions are not this code's")
    if (p1.get("schema_version"), p1.get("quantities_columns_schema_version")) != (
            av.SCHEMA_VERSIONS["p1_record"], av.SCHEMA_VERSIONS["quantities_columns"]):
        problems.append("P1's record's schema versions are not this code's")
    if not (side.get("definition_version") == p1.get("definition_version") == av.DEFINITION_VERSION):
        problems.append("the definition versions disagree")
    if not (_hex(side.get("run_id"), HEX32) and side.get("run_id") == p1.get("run_id")):
        problems.append("the sidecar and P1's record do not name the same run")
    if not _hex(side.get("attempt_id"), HEX32):
        problems.append("the sidecar names no audit attempt")
    if not (_hex(side.get("mask_sha256"), HEX64) and side["mask_sha256"] == hashes["outcome_availability.csv"]):
        problems.append("the mask is not the one the sidecar names")
    if not (_hex(side.get("p1_record_sha256"), HEX64) and side["p1_record_sha256"] == hashes["p1_record.json"]):
        problems.append("P1's record is not the one the sidecar names")
    q_side = (side.get("inputs_sha256") or {}).get("quantities") if isinstance(side.get("inputs_sha256"), dict) else None
    if not (_hex(q_side, HEX64) and _hex(p1.get("quantities_written_sha256"), HEX64) and q_side == p1["quantities_written_sha256"]):
        problems.append("the quantities file the audit read is not one P1 is recorded as having written")
    checks = p1.get("checks")
    if not isinstance(checks, dict) or sorted(checks) != sorted(av.P1_CHECKS) or not all(checks[c] is True for c in av.P1_CHECKS):
        problems.append("P1's record does not show exactly the five named checks passed")
    if not (side.get("authorized_by") and side.get("authorized_by") == p1.get("authorized_by")):
        problems.append("the sidecar and P1's record do not name the same authorization")
    elif side["authorized_by"] != entry:
        problems.append(f"the bundle was made under {side['authorized_by']}, not {entry}")
    # The provenance each record must carry, and the fields the sidecar duplicates (D-76, G2).
    problems += records.p1_provenance_problems(p1, pins)
    problems += records.sidecar_provenance_problems(side, p1, pins)
    if not rows or rows[0].split(",") != list(av.MASK_COLUMNS):
        problems.append("the mask's columns are not this schema's")
    elif side.get("rows") != len(rows) - 1:
        problems.append("the mask's row count is not the sidecar's")
    if problems:
        raise BundleRefused("inconsistent bundle: " + "; ".join(problems))
    return {"run_id": side["run_id"], "attempt_id": side["attempt_id"], "authorized_by": side["authorized_by"],
            "authorization_entry_sha256": side["authorization_entry_sha256"],
            "definition_version": side["definition_version"], "analysis_filter": side["analysis_filter"],
            "files_sha256": hashes}


def _remove_partial(folder: Path) -> None:
    for p in [folder, *folder.rglob("*")]:
        os.chmod(p, 0o700 if p.is_dir() else 0o600)
    shutil.rmtree(folder)


def _confirm_final(final: Path) -> None:
    """The folder under its final name is the one this step made: read-only, holding exactly the four read-only files."""
    if stat.S_IMODE(os.stat(final).st_mode) != 0o500:
        raise NotConfirmed("the named folder is not read-only")
    if sorted(os.listdir(final)) != sorted(PRESERVED):
        raise NotConfirmed("the named folder does not hold exactly the preserved files")
    if any(stat.S_IMODE(os.stat(final / f).st_mode) != 0o400 for f in PRESERVED):
        raise NotConfirmed("a preserved file is not read-only")


def preserve(source: Path, to: Path, entry: str, pins: dict, today: str | None = None, stage: list | None = None) -> dict:
    stage = stage if stage is not None else ["verify source"]
    stage[0] = "verify source"
    run = verify_bundle(source, entry, pins)
    name = f"{today or dt.date.today().isoformat()}-availability-{run['run_id'][:8]}-{run['attempt_id'][:8]}"
    final, staging = to / name, to / (name + ".partial")
    if final.exists():
        raise BundleRefused(f"{final} already exists; a preserved copy is never overwritten, and an attempt that finds one "
                            "is not retried: this stop returns to Joe")
    removed = None
    if staging.exists():
        stage[0] = "remove an incomplete earlier attempt"
        _remove_partial(staging)
        removed = str(staging)
    stage[0] = "copy"
    to.mkdir(parents=True, exist_ok=True)
    staging.mkdir(mode=0o700)
    for f in FILES:
        shutil.copyfile(source / f, staging / f)
    stage[0] = "verify copy"
    copied = verify_bundle(staging, entry, pins)
    if copied != run:
        raise BundleRefused("the source changed while it was copied: the copy is not the bundle that was verified")
    stage[0] = "manifest"
    manifest = {"schema_version": av.SCHEMA_VERSIONS["preserved_manifest"], "preserved_from": str(source), **copied}
    (staging / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    stage[0] = "restrict"
    for f in PRESERVED:
        os.chmod(staging / f, 0o400)
    os.chmod(staging, 0o500)
    stage[0] = "name the folder"
    os.rename(staging, final)                 # the last change: from here on the final folder exists, complete and restricted
    try:
        stage[0] = "confirm the named folder"
        _confirm_final(final)
    except BaseException as e:                # noqa: BLE001 - whatever stops it now, the folder is there, and the step says so
        raise LateFailure(str(final), stage[0], type(e).__name__) from None
    return {"folder": str(final), "removed_incomplete_attempt": removed, **manifest}


def main(argv: list[str]) -> int:
    stage = ["authorization"]
    try:
        entry = argv[argv.index("--authorized-by") + 1] if "--authorized-by" in argv else None
        entry, pins = guard.check_authorization(LEDGER, entry, ROOT, av.PRESERVE_PINNED, av.PIN_HEADER)
        guard.check_interpreter(pins)
        guard.check_versions(pins["versions"], {"python": sys.version.split()[0]})
        to = Path(argv[argv.index("--to") + 1]) if "--to" in argv else Path(guard.access_records())
        m = preserve(SOURCE, to, entry, pins, stage=stage)
    except guard.Refusal as e:
        print(f"nothing preserved by this attempt: {e}")
        return 4
    except BundleRefused as e:
        print(f"nothing preserved by this attempt: {e}")
        return 2
    except LateFailure as e:
        print(f"preservation stopped after the folder was named: {e.folder} exists and holds the verified copy, but the step "
              f"stopped at {e.stage}: {e.cause}. This is not a completed preservation. Do not rerun: this stop returns to Joe")
        return 5
    except BaseException as e:            # noqa: BLE001 - every other exception is reduced to its class name
        print(f"nothing preserved by this attempt: stopped at {stage[0]}: {type(e).__name__}")
        return 2
    if m["removed_incomplete_attempt"]:
        print(f"removed an incomplete earlier attempt: {m['removed_incomplete_attempt']}")
    print(f"preserved run {m['run_id']} (audit attempt {m['attempt_id']}) to {m['folder']} (folder and files readable by this account only)")
    print(f"definition {m['definition_version']}")
    for f, h in m["files_sha256"].items():
        print(f"  {f} {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
