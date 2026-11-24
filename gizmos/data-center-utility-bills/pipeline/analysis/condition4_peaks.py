#!/usr/bin/env python3
"""Condition 4's peak-demand rows: the path for the one authorized read, and the retained quantity-only input.

PREANALYSIS.md, "Conditions tested (four)", condition 4 (past utilization). The plan is frozen at commit ea426c4 (the
approved specification is commit ed3a2ff); it is internally frozen and not externally preregistered.

Joe authorized session 27, on 2026-11-20 (D-120, section 7), to read
data/raw/pudl/core_eia861__yearly_operational_data_misc.parquet once, through conditions.read_peaks, selecting only the
seven columns conditions.PEAK_COLUMNS names, solely to supply and check the quantity-side input for condition 4, and to
retain a reusable quantity-only input so that later assembly needs no further raw read. His words are AUTHORIZING_WORDS,
copied from HANDOVER_session27_2026-11-20.md, section 2. The session's decision: the read is ONE call of
conditions.read_peaks() as it stands, with no source, and what is retained is the frame that call returns, in the six
columns PEAKS_AS_READ (utility_id_eia, state, year, peak_mw, short_form, data_observed). The read selects the seven
columns by name, so no other column of the file (no revenue column) reaches memory, the retained file or the record.

What is here
------------
refuse_raw_or_blind(path)
                    refuses, in words, a path whose text lies under a folder data/raw or data/blind. It compares path
                    text only (os.path.abspath and normpath, no symlink resolution) and never touches the file system for
                    those folders. The input assembler calls it on every path it opens or hashes.
read_once_and_retain(*, retained=RETAINED, record=RECORD, reader=None, raw_file=None, command=None)
                    the one read. Refuses in words if the retained file or the record already exists (the authorization
                    is for one read; a second is not covered). Takes the sha256 of the raw file's bytes (the one hash the
                    authorization allows, for the record of the read), calls reader() exactly once with no argument
                    (conditions.read_peaks, looked up when called), and then stores the frame BEFORE anything else can
                    fail (a temporary name renamed into place; short_form as nullable boolean, else as text, else the
                    frame pickled beside the retained path), so the one read is never lost. The read-back check, the
                    column check and the counts do not raise: the record says whether the file reads back equal, with
                    any difference in words. If the record write fails, the record (counts only) is printed as JSON and
                    the failure raised.
load_retained(path=RETAINED, record=RECORD)
                    the retained frame in the six-column form, restored from the representation the record names, its
                    sha256 and columns checked against the record; a record whose reads_back_equal is false is refused
                    in words (the loader needs repair, not a second read). It never falls back to the raw file: if the
                    retained file is absent it raises in words that the read has not been made.
main()              with --read-once, makes the read and prints counts; with no flag it prints what it would do and reads
                    nothing.

Nothing here prints or records a utility's peak: the record holds counts, years, paths and hashes. Peak demand is a
quantity, not an outcome; no price, revenue or bill is read.

Run:  python3 -I pipeline/analysis/condition4_peaks.py               says what it would do; reads nothing
      python3 -I pipeline/analysis/condition4_peaks.py --read-once   the one authorized read (the session makes it)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.analysis import conditions as cn  # noqa: E402

RETAINED = ROOT / "data" / "interim" / "condition4_peak_rows.parquet"
RECORD = ROOT / "data" / "frozen" / "condition4_peak_read_record.json"
PEAKS_AS_READ = ("utility_id_eia", "state", "year", "peak_mw", "short_form", "data_observed")
REFUSED_FOLDERS = ("raw", "blind")

# Joe's words, 2026-11-20 (D-120, section 7), copied exactly from HANDOVER_session27_2026-11-20.md, section 2, the second
# quoted block (tests/test_condition4_peaks_invented.py checks them against that file).
AUTHORIZING_WORDS = (
    "I accept the freeze record and the reading that the completed final quantity regeneration and reconciliation "
    "satisfies the “read again” or “taken again at freeze” clauses. Do not repeat that work.\n\n"
    "One narrow exception to the prohibition on raw-data reads: I authorize Session 27 to read the existing "
    "`data/raw/pudl/core_eia861__yearly_operational_data_misc.parquet` through `conditions.read_peaks`, selecting only "
    "these seven columns:\n\n"
    "`utility_id_eia`, `state`, `report_date`, `summer_peak_demand_mw`, `winter_peak_demand_mw`, `short_form`, "
    "`data_observed`.\n\n"
    "Use this solely to supply and check the quantity-side input for condition 4 under the frozen specification. No "
    "other columns, revenue companion, other raw file, outcome access or condition-4 outcome analysis is authorized. "
    "Inspect and test the path on invented inputs first, record the read, and retain a reusable quantity-only input so "
    "subsequent assembly does not require another raw read.\n\n"
    "Carry this exception into the handover and implementation record. All other boundaries stand: no GATE1_SIGNED, "
    "outcome authorization variable on research data, outcome read or research analysis. Return the "
    "implementation-readiness package and stop.")
AUTHORIZATION = "Joe, 2026-11-20 (D-120, section 7)"


class PathRefused(PermissionError):
    """A path under data/raw or data/blind was offered to code that may not open or hash it."""


class SecondReadRefused(PermissionError):
    """The retained file or the record of the read already exists: the authorization covers one read only."""


class RetainedAbsent(FileNotFoundError):
    """The retained peak rows are not on disk: the authorized read has not been made. Nothing falls back to the raw file."""


class RetainedRefused(ValueError):
    """The retained file does not match the record of the read (hash or columns)."""


# ---- the path guard ---------------------------------------------------------------------------------------------------

def refuse_raw_or_blind(path) -> Path:
    """The path, made absolute and normalized as TEXT (os.path.abspath, os.path.normpath; no symlink is resolved and no
    file is touched), or PathRefused in words when it lies under a folder named data/raw or data/blind anywhere in it.
    The comparison ignores case, since the machine's file system does."""
    p = Path(os.path.normpath(os.path.abspath(os.fspath(path))))
    parts = [x.lower() for x in p.parts]
    for a, b in zip(parts, parts[1:]):
        if a == "data" and b in REFUSED_FOLDERS:
            raise PathRefused(f"{_as_text(p)} lies under data/{b}: this code may not open, list or hash anything there")
    return p


def _as_text(p) -> str:
    """The path relative to the gizmo folder where it lies inside it (so no file records the machine's home folder),
    else as given."""
    p = Path(os.path.normpath(os.path.abspath(os.fspath(p))))
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- writing and reading the retained frame ---------------------------------------------------------------------------
#
# Three representations, tried in this order, so that the one read is never lost (the coordinator's instruction of
# 2026-11-20): the parquet with short_form as pandas' nullable boolean; if that conversion or write fails, the parquet with
# every column as returned except short_form, written as text ("True", "False", "" for missing); if that fails too, the
# frame pickled beside the retained path. The record says which was stored and load_retained restores it.

NULLABLE = "parquet, short_form as pandas nullable boolean"
TEXT = "parquet, short_form as text ('True', 'False', '' for missing), every other column as returned"
PICKLE = "pickle (pandas.DataFrame.to_pickle), the last resort"
REPRESENTATIONS = (NULLABLE, TEXT, PICKLE)


def _to_storage(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame as stored under NULLABLE: short_form, which read_peaks returns as a numpy array of True, False and pandas
    NA (object) or of booleans (bool) when no value is missing, is stored as pandas' nullable "boolean"."""
    f = frame[list(PEAKS_AS_READ)].copy()
    f["short_form"] = pd.array(list(frame["short_form"]), dtype="boolean")
    return f


def _to_text_storage(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame as stored under TEXT: every column as returned, short_form as str of each entry, missing as ''."""
    f = frame.copy()
    if "short_form" in f.columns:
        f["short_form"] = ["" if pd.isna(x) else str(x) for x in frame["short_form"]]
    return f


def _from_storage(stored: pd.DataFrame, representation: str = NULLABLE) -> pd.DataFrame:
    """The stored frame back in the representation conditions.read_peaks returns: short_form through
    .astype("boolean").to_numpy(), exactly as read_peaks builds it (from text under TEXT: 'True' True, 'False' False,
    '' missing), state as object."""
    if representation not in REPRESENTATIONS:
        raise ValueError(f"unknown stored representation {representation!r}")
    f = stored.copy()
    if "short_form" in f.columns:
        if representation == TEXT:
            m = {"True": True, "False": False, "": pd.NA}
            bad = sorted({str(x) for x in f["short_form"] if str(x) not in m})
            if bad:
                raise ValueError(f"short_form stored as text holds {len(bad)} values other than 'True', 'False' and ''")
            f["short_form"] = pd.array([m[str(x)] for x in f["short_form"]], dtype="boolean").to_numpy()
        else:
            f["short_form"] = f["short_form"].astype("boolean").to_numpy()
    if "state" in f.columns:
        f["state"] = f["state"].astype(object)
    return f.reset_index(drop=True)


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    frame.to_parquet(path, index=False)


def _write_pickle(frame: pd.DataFrame, path: Path) -> None:
    frame.to_pickle(path)


def _read_stored(path: Path, representation: str) -> pd.DataFrame:
    return pd.read_pickle(path) if representation == PICKLE else pd.read_parquet(path)


def _write_json(obj: dict, path: Path) -> None:
    path.write_text(json.dumps(obj, indent=1) + "\n")


def _partial(retained: Path) -> Path:
    return retained.with_name(retained.name + ".partial")


def _pickled(retained: Path) -> Path:
    return retained.with_name(retained.stem + ".pkl")


def _store(frame: pd.DataFrame, retained: Path) -> tuple[Path, str, list]:
    """Put the frame on disk before anything else can fail: each representation in turn, written to a temporary name in
    the same folder and renamed to the retained path (os.replace); the pickle beside it last. Returns (the stored path,
    its representation, the failures before it in words: exception type and the step, never a value). Raises only if
    every representation fails."""
    failures = []
    tmp = _partial(retained)
    for rep, conv in ((NULLABLE, _to_storage), (TEXT, _to_text_storage)):
        try:
            _write_parquet(conv(frame), tmp)
            os.replace(tmp, retained)
            return retained, rep, failures
        except Exception as exc:                                    # noqa: BLE001  the next representation is tried
            failures.append(f"{rep}: {type(exc).__name__}")
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
    pk = _pickled(retained)
    tmp = _partial(pk)
    try:
        _write_pickle(frame, tmp)
        os.replace(tmp, pk)
    except Exception as exc:                                        # noqa: BLE001
        failures.append(f"{PICKLE}: {type(exc).__name__}")
        raise RuntimeError("the frame read once could not be stored in any representation (" + "; ".join(failures)
                           + "); it is lost with this process and a second read is not covered without Joe's word") from exc
    return pk, PICKLE, failures


def _difference(a: pd.DataFrame, b: pd.DataFrame) -> str:
    """How two frames differ, in words: column names, dtypes and counts of rows that differ. Never a value."""
    out = []
    if list(a.columns) != list(b.columns):
        out.append(f"columns read {list(a.columns)} against stored {list(b.columns)}")
    da = {str(c): str(t) for c, t in a.dtypes.items()}
    db = {str(c): str(t) for c, t in b.dtypes.items()}
    diff_t = {c: (da.get(c), db.get(c)) for c in sorted(set(da) | set(db)) if da.get(c) != db.get(c)}
    if diff_t:
        out.append(f"dtypes that differ (read, stored): {diff_t}")
    if len(a) != len(b):
        out.append(f"rows read {len(a)} against stored {len(b)}")
    else:
        common = [c for c in a.columns if c in b.columns]
        rows = np.zeros(len(a), dtype=bool)
        for c in common:
            x, y = a[c].reset_index(drop=True), b[c].reset_index(drop=True)
            same = (x.astype(object) == y.astype(object)).fillna(False).to_numpy(dtype=bool) | (pd.isna(x) & pd.isna(y)).to_numpy()
            rows |= ~same
            if (~same).any():
                out.append(f"column {c}: {int((~same).sum())} rows differ")
        out.append(f"rows that differ in some common column: {int(rows.sum())} of {len(a)}")
    return "; ".join(out) if out else "no difference found by column, dtype or row, yet the equality check failed"


def counts(frame: pd.DataFrame) -> dict:
    """Counts on the six-column frame, no value of a peak: rows, first and last year, distinct utility-state pairs, rows
    with a peak, rows not observed, rows marked short form (and with the mark missing), repeated (utility, state, year)
    keys."""
    k = ["utility_id_eia", "state", "year"]
    dup = frame.duplicated(k, keep=False)
    sf = pd.array(list(frame["short_form"]), dtype="boolean")
    return {"rows": int(len(frame)),
            "first_year": None if not len(frame) else int(frame.year.min()),
            "last_year": None if not len(frame) else int(frame.year.max()),
            "distinct_utility_state_pairs": int(frame[["utility_id_eia", "state"]].drop_duplicates().shape[0]),
            "rows_with_a_peak": int(frame.peak_mw.notna().sum()),
            "rows_not_observed": int((~frame.data_observed.astype(bool)).sum()),
            "rows_marked_short_form": int((sf == True).sum()),                                 # noqa: E712
            "rows_with_the_short_form_mark_missing": int(pd.isna(sf).sum()),
            "rows_sharing_a_utility_state_year_key": int(dup.sum()),
            "repeated_utility_state_year_keys": int(frame.loc[dup, k].drop_duplicates().shape[0])}


# ---- the one read ----------------------------------------------------------------------------------------------------

def read_once_and_retain(*, retained=None, record=None, reader=None, raw_file=None, command: str | None = None) -> dict:
    """The one authorized read (Joe, 2026-11-20, D-120, section 7) and the retained input. Returns the record written.

    Before the read: retained and record (RETAINED and RECORD by default, looked up when called) are refused if they lie
    under data/raw or data/blind, and the call is refused in words if the retained file, its temporary name, the pickle
    beside it or the record already exists (one read only). reader: conditions.read_peaks by default, looked up when
    called. raw_file: conditions.PEAK_FILE, looked up when called; another path is refused. The raw file's sha256 is the
    one hash taken under data/raw.

    After reader() returns, nothing can lose the frame: it is stored first (_store: NULLABLE, else TEXT, else PICKLE,
    each to a temporary name renamed into place). The read-back check does not raise: the record says reads_back_equal
    true, or false with the difference in words (and load_retained then refuses the file until its loader is repaired;
    no second read is needed). Columns other than PEAKS_AS_READ are recorded by name and also make the file refused by
    load_retained. A failure of the counts is recorded by its exception type. If the record write fails, the record (counts
    only) is printed as JSON to standard output so the session can save it, and the failure is raised."""
    retained = refuse_raw_or_blind(RETAINED if retained is None else retained)
    record = refuse_raw_or_blind(RECORD if record is None else record)
    for p, what in ((retained, "the retained peak rows"), (_partial(retained), "a partly written retained file"),
                    (_pickled(retained), "the retained peak rows as a pickle"), (record, "the record of the read")):
        if p.exists():
            raise SecondReadRefused(f"{what} already exist at {_as_text(p)}: the authorization (Joe, 2026-11-20, D-120) "
                                    "covers one read of the peak table, and a second is not covered; nothing was read")
    reader = cn.read_peaks if reader is None else reader
    authorized = Path(cn.PEAK_FILE)
    raw = authorized if raw_file is None else Path(raw_file)
    if os.path.normpath(os.path.abspath(raw)) != os.path.normpath(os.path.abspath(authorized)):
        raise PathRefused(f"{_as_text(raw)} is not conditions.PEAK_FILE ({_as_text(authorized)}), the one file the "
                          "authorization names and the reader reads; nothing was read")
    raw_sha = _sha256_file(raw)                       # the one hash under data/raw, for the record of the read
    frame = reader()                                  # exactly once, with no argument
    read_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---- the frame goes to disk before anything else can fail
    frame = frame.reset_index(drop=True)
    stored_path, representation, storage_failures = _store(frame, retained)

    problems = []
    cols = [str(c) for c in frame.columns]
    columns_ok = cols == list(PEAKS_AS_READ)
    if not columns_ok:
        problems.append(f"the reader returned the columns {cols}, not exactly {list(PEAKS_AS_READ)}")
    try:
        back = _from_storage(_read_stored(stored_path, representation), representation)
        try:
            pd.testing.assert_frame_equal(frame, back, check_exact=True)
            equal = True
        except AssertionError:
            equal = False
            problems.append("the stored frame does not read back equal: " + _difference(frame, back))
    except Exception as exc:                                        # noqa: BLE001  recorded in words, never raised
        equal = False
        problems.append(f"the read-back itself failed ({type(exc).__name__}); the file is on disk and was not checked")
    try:
        c = counts(frame)
    except Exception as exc:                                        # noqa: BLE001
        c = {"failed_in_words": f"the counts could not be computed ({type(exc).__name__})"}
    try:
        stored_sha = _sha256_file(stored_path)
    except Exception as exc:                                        # noqa: BLE001
        stored_sha = None
        problems.append(f"the stored file's sha256 could not be taken ({type(exc).__name__})")
    ok = bool(equal and columns_ok and stored_sha is not None)
    doc = {"what_this_is": ("The record of the one authorized read of condition 4's peak-demand rows (Joe, 2026-11-20, "
                            "D-120, section 7): counts only, no utility's peak. The plan is frozen at commit ea426c4. The "
                            "read was one call of conditions.read_peaks() with no source, a select of exactly the seven "
                            "columns below; the retained file is the frame that call returned, in six columns, a "
                            "quantity-only input reused by later assembly so that no further raw read is needed."),
           "authorization": AUTHORIZATION,
           "authorizing_words": AUTHORIZING_WORDS,
           "raw_file": {"path": _as_text(raw), "sha256": raw_sha},
           "columns_selected": list(cn.PEAK_COLUMNS),
           "reader": f"{getattr(reader, '__module__', '?')}.{getattr(reader, '__qualname__', repr(reader))}",
           "columns_retained": list(PEAKS_AS_READ),
           "columns_returned_by_the_reader": cols,
           "counts": c,
           "read_at_utc": read_at,
           "command": command,
           "retained_file": {"path": _as_text(stored_path), "sha256": stored_sha, "representation": representation,
                             "representations_that_failed_before_it": storage_failures,
                             "reads_back_equal": bool(equal)},
           "usable_by_load_retained": ok,
           "problems_in_words": problems,
           "written_by": "pipeline/analysis/condition4_peaks.py read_once_and_retain"}
    try:
        _write_json(doc, record)
    except Exception:
        print("THE RECORD COULD NOT BE WRITTEN; the frame is retained at " + _as_text(stored_path) + ". The record, counts "
              "only, follows as JSON for the session to save:")
        print(json.dumps(doc, indent=1))
        raise
    if not ok:
        print("The frame is retained at " + _as_text(stored_path) + " (" + representation + "), but the retained file "
              "needs a look before use: " + "; ".join(problems) + ". No second read is needed.")
    return doc


def load_retained(path=None, record=None) -> pd.DataFrame:
    """The retained peak rows in the six-column form conditions.read_peaks returns (PEAKS_AS_READ), restored from the
    representation the record names. The file's sha256 and columns are checked against the record, and a record whose
    reads_back_equal is false (or that marks the file unusable) is refused in words. Never reads the raw file: an absent
    retained file or record raises RetainedAbsent in words. `path` is the retained parquet path; under PICKLE the pickle
    beside it is read."""
    path = refuse_raw_or_blind(RETAINED if path is None else path)
    record = refuse_raw_or_blind(RECORD if record is None else record)
    if not record.exists():
        if not path.exists() and not _pickled(path).exists():
            raise RetainedAbsent(f"{_as_text(path)} is not on disk: the authorized read of the peak table has not been "
                                 "made (python3 -I pipeline/analysis/condition4_peaks.py --read-once, made by the "
                                 "session). The raw file is not read in its place")
        raise RetainedAbsent(f"{_as_text(record)}, the record of the read, is not on disk, so the retained file cannot be "
                             "checked; it is not used and the raw file is not read in its place (the retained file "
                             "exists: no second read is needed, the record is to be restored)")
    doc = json.loads(record.read_text())
    rf = doc.get("retained_file") or {}
    if not rf.get("reads_back_equal") or doc.get("usable_by_load_retained") is False:
        raise RetainedRefused("the retained file exists but its record says it does not read back equal or is not "
                              "usable (" + "; ".join(doc.get("problems_in_words") or []) + "). It needs repair of the "
                              "loader, not a second read")
    representation = rf.get("representation", NULLABLE)
    stored_path = _pickled(path) if representation == PICKLE else path
    if not stored_path.exists():
        raise RetainedAbsent(f"{_as_text(stored_path)} is not on disk although the record of the read exists; the raw "
                             "file is not read in its place and a second read is not covered")
    want = rf.get("sha256")
    got = _sha256_file(stored_path)
    if got != want:
        raise RetainedRefused(f"{_as_text(stored_path)} has sha256 {got[:12]}, not the {str(want)[:12]} the record of the "
                              "read gives; it is not used")
    if list(doc.get("columns_retained") or []) != list(PEAKS_AS_READ):
        raise RetainedRefused(f"the record's retained columns {doc.get('columns_retained')} are not {list(PEAKS_AS_READ)}")
    stored = _read_stored(stored_path, representation)
    if list(stored.columns) != list(PEAKS_AS_READ):
        raise RetainedRefused(f"{_as_text(stored_path)} has the columns {list(stored.columns)}, not {list(PEAKS_AS_READ)}")
    return _from_storage(stored, representation)


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description="Condition 4's peak rows: the one authorized read (Joe, 2026-11-20, D-120)")
    a.add_argument("--read-once", action="store_true", help="make the one authorized read and retain the frame")
    args = a.parse_args(argv)
    if not args.read_once:
        print("Nothing read. With --read-once this would: refuse if " + _as_text(RETAINED) + " or " + _as_text(RECORD)
              + " exists; take the sha256 of " + _as_text(cn.PEAK_FILE) + "; call conditions.read_peaks() once (a select "
              "of " + ", ".join(cn.PEAK_COLUMNS) + "); write the six-column frame to " + _as_text(RETAINED)
              + " and confirm it reads back equal; write the record, counts only, to " + _as_text(RECORD) + ".")
        return 0
    command = " ".join([os.path.basename(sys.executable), "-I", "pipeline/analysis/condition4_peaks.py"]
                       + list(sys.argv[1:] if argv is None else argv))
    doc = read_once_and_retain(command=command)
    print("read once and retained; counts only:")
    for k, v in doc["counts"].items():
        print(f"  {k}: {v}")
    print("retained", doc["retained_file"]["path"], doc["retained_file"]["sha256"][:12])
    print("record", _as_text(RECORD))
    return 0


if __name__ == "__main__":
    sys.exit(main())
