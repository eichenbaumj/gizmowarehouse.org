#!/usr/bin/env python3
"""P1, the availability flag build: the only availability process that sees revenue.

Route: docs/gate1/availability-audit-route.md. Rulings: D-70 as amended by D-72, adopted in D-73. A run on research
data needs Joe's separate execution instruction, logged as a ledger entry that carries the pin block
(availability_pins.py), and is started only by run_availability.sh, under the committed sandbox profile:

    sh pipeline/electricity/run_availability.sh p1 --authorized-by D-NN

Before it opens anything under data/, it checks that the entry exists, speaks of the availability audit, and pins
the hash of every file it uses, and that it runs under the committed profile with the probe file unreadable.
After its imports, that every library it uses is at the pinned version.

What it does. Builds the panel exactly as panel.build does, from the raw sales snapshot on disk (nothing is
fetched). Checks, inside the process, that the outcomes it built are identical to the outcome files on disk,
that every existing quantity column is identical to the quantities file on disk, that the new flag equals the
analysis's filter on every row, and that every row has a valid first exclusion reason, imputation status and
supplier-row status consistent with the quantity columns. If all five checks pass it writes the quantities file
with the four new columns, then its record, which carries a run identifier the audit and the preservation step
link to. It never writes under data/blind/ and never prints, logs or saves a revenue, a price, a sum or a ratio.

Permitted output, success (exit 0) and the "not identical" failure (exit 1), and nothing else:
    P1 availability flag build, definition <version>
    inputs: sales <sha256> | succession <sha256> | quantities <sha256>
    outcomes identical to disk: yes|no
    by-unit files identical to disk: yes|no
    existing quantity columns identical to disk: yes|no
    flag equals the analysis filter on every row: yes|no
    one first exclusion reason per row from the fixed list, consistent with the quantity columns: yes|no
    wrote: data/interim/panel_quantities.parquet, data/interim/availability/p1_record.json (run <32 hex>)   (or: wrote nothing)
Permitted output, stopped: the status lines already printed, if any, then one line, "P1 stopped at <stage>:
<refusal or exception class name>", exit 2, 3 (isolation not in force) or 4 (not authorized, or code, a library or
the interpreter not as pinned). Standard error is closed.

Failure handling. Every check runs before anything is written, including a check that the record this attempt
would write passes the readers' own provenance checks (availability_records.py). Then, in order: the record is
rewritten with this attempt's identifier and status "in_progress" (so no earlier record still vouches for the
quantities file), the quantities file is replaced, and the record is rewritten "completed". A stop after the
first of those and before the last leaves a record that is not "completed", which the audit and the preservation
step refuse (tested after an earlier successful run). Each write goes through a ".tmp" file and a rename; a
process killed outright can leave a ".tmp" file, which the next write replaces.

What the marker does not show (D-76, G3). A stop BEFORE the marker is replaced leaves the earlier record, which
still correctly describes the earlier quantities file: those artifacts pass every later check. A process can also
write "completed" and stop before it reports success. So a "completed" record never shows that THIS invocation
succeeded. The next step starts only after this invocation exits 0 and prints its "wrote:" line, whose run
identifier the next step's output must repeat. Whether a stopped attempt may be retried is not this script's to
say: the execution instruction's rule is that a stop returns to Joe unless its cause is known from outside the
process. One consequence of the order above: this script replaces the quantities file, which is one of its own
inputs, before it completes its record. A rerun after a stop at or after "write quantities" may therefore read a
different quantities file and print a different quantities hash on its "inputs:" line than the stopped attempt
did. An interrupted write is not for that reason retryable: under the execution instruction a retry's input hashes
must equal the stopped attempt's, and a stop that may have replaced the file returns to Joe (tested both ways).

Reads. The raw sales file is hashed before and after DuckDB reads it: a check, not proof that it was unchanged
throughout the read (D-75 item 2). The quantities, outcome and succession inputs are hashed and parsed from one
read. The code files are hashed against their pins and imported afterwards, which are separate reads, under the
no-writer agreement (D-76, G6).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.electricity import access_guard as guard  # noqa: E402
from pipeline.electricity import availability_codes as av  # noqa: E402
from pipeline.electricity import availability_records as records  # noqa: E402

D = ROOT / "data"
SALES = D / "raw" / "pudl" / "core_eia861__yearly_sales.parquet"
SUCCESSION = ROOT / "pipeline" / "electricity" / "succession.csv"
QUANT = D / "interim" / "panel_quantities.parquet"
OUTCOMES = D / "blind" / "panel_outcomes.parquet"
BY_UNIT = D / "blind" / "outcomes_by_unit"
RECORD_DIR = D / "interim" / "availability"
RECORD = RECORD_DIR / "p1_record.json"
LEDGER = ROOT / "docs" / "DECISIONS.md"
PROFILE = ROOT / "pipeline" / "electricity" / "sandbox" / "p1.sb"
PROBE = ROOT / "pipeline" / "electricity" / "sandbox" / "denied_probe.txt"
KEYS = list(av.KEYS)


def policy() -> guard.Policy:
    n = lambda p: os.path.normpath(str(p))  # noqa: E731
    tmp = lambda p: n(str(p) + ".tmp")  # noqa: E731
    return guard.standard_policy(
        ROOT,
        # The by-unit files become readable one by one, by the names the one scoped listing returns (main).
        reads=frozenset({n(SALES), n(QUANT), n(OUTCOMES)}),
        writes=frozenset({tmp(QUANT), tmp(RECORD)}),
        listable=frozenset({n(BY_UNIT)}),
        renames=frozenset({(tmp(QUANT), n(QUANT)), (tmp(RECORD), n(RECORD))}),
    )


def roundtrip(df):
    """`df` as it comes back from a parquet file written the way panel.write writes it (index=False)."""
    import io

    import pyarrow.parquet as pq
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    return pq.read_table(buf).to_pandas()


def parse_parquet(data: bytes, columns=None):
    """A parquet file's bytes, already read once and hashed, parsed with no second read (D-75 item 2)."""
    import io

    import pyarrow.parquet as pq
    return pq.read_table(io.BytesIO(data), columns=columns).to_pandas()


def read_parquet(path, columns=None):
    """Open in Python (so the guard records it) and parse what was read."""
    return parse_parquet(guard.read_once(path)[1], columns)


def flag_domain_ok(observed) -> bool:
    """EIA's observation flag holds only true, false or missing, the domain on which panel.py's two spellings of the
    imputed-row filter (`fillna(True)` and `isna() | == True`) agree. Anything else stops P1 (D-74, from R5)."""
    import pandas as pd
    vals = observed[observed.notna()]
    return bool(vals.map(lambda v: type(v).__name__ in ("bool", "bool_")).all()) and not isinstance(observed.dtype, pd.StringDtype)


def same_frame(a, b, keys) -> bool:
    """Keyed identity: the same columns, keys unique on both sides, and equal values and types row for row after
    sorting by the keys. Row order, the index and column order are incidental and normalized away."""
    if sorted(a.columns) != sorted(b.columns) or len(a) != len(b):
        return False
    if a.duplicated(keys).any() or b.duplicated(keys).any():
        return False
    cols = list(a.columns)
    a2 = a[cols].sort_values(keys, kind="stable").reset_index(drop=True)
    b2 = b[cols].sort_values(keys, kind="stable").reset_index(drop=True)
    return bool(a2.dtypes.equals(b2.dtypes) and a2.equals(b2))


def unit_name(u, st) -> str:
    return f"{int(u)}_{st}.parquet"


def by_unit_names() -> set[str]:
    """The one directory listing P1 makes: the names of the by-unit outcome files, to find a missing or extra file."""
    with os.scandir(BY_UNIT) as it:
        return {e.name for e in it}


def flag_checks(q, o) -> tuple[bool, bool]:
    """(the flag equals the analysis's filter on every row, valid reasons and statuses consistent with the quantities)."""
    m = q[KEYS + [av.FLAG_COL, "meets_size_floor"]].merge(o[KEYS + ["res_price"]], on=KEYS, how="outer", indicator=True)
    filt = m.meets_size_floor.astype(bool) & (m.res_price > 0)
    flag_ok = bool(len(m) == len(q) == len(o) and (m._merge == "both").all() and m[av.FLAG_COL].notna().all()
                   and (filt == m[av.FLAG_COL].astype(bool)).all())
    r = q[av.REASON_COL]
    none_basis = q.supply_price_basis == "none_available"
    sales = q.res_mwh > 0
    floor = q.meets_size_floor.astype(bool)
    reason_ok = bool(
        r.notna().all() and r.isin(av.BUILD_REASONS + (av.NO_EXCLUSION,)).all()
        and ((r == av.NO_EXCLUSION) == q[av.FLAG_COL].astype(bool)).all()
        and ((r == "no_residential_sales") == ~sales).all()
        and ((r == "under_customer_floor") == (sales & ~floor)).all()
        and ((r == "no_supply_price") == (sales & floor & none_basis)).all()
        and q[av.UNKNOWN_COL].isin(av.IMPUTATION_STATUS).all()
        and q[av.SUPPLIER_COL].isin(av.SUPPLIER_STATUS).all()
        and ((q[av.SUPPLIER_COL] != "not_used") == (q.supply_price_basis == "state_observed_suppliers")).all())
    return flag_ok, reason_ok


def write_record(record: dict) -> None:
    guard.write_atomically(RECORD, lambda f: f.write((json.dumps(record, indent=2) + "\n").encode()))


def main(stage) -> int:
    stage[0] = "arguments"
    argv = sys.argv[1:]
    if len(argv) != 2 or argv[0] != "--authorized-by":
        raise guard.Refusal("usage: run_availability.sh p1 --authorized-by D-NN", 4)
    stage[0] = "guard"
    pol = policy()
    guard.install(pol)
    stage[0] = "authorization"
    entry, pins = guard.check_authorization(LEDGER, argv[1], ROOT, av.P1_PINNED, av.PIN_HEADER)
    interpreter = guard.check_interpreter(pins)
    stage[0] = "isolation"
    profile_sha = guard.check_isolation(PROFILE, PROBE)

    stage[0] = "imports"
    import io
    import uuid

    import duckdb
    import numpy as np
    import pandas as pd
    import pyarrow
    versions = {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__,
                "pyarrow": pyarrow.__version__, "duckdb": duckdb.__version__}
    guard.check_versions(pins["versions"], versions)
    np.seterr(all="ignore")
    from pipeline.electricity import panel
    from pipeline.electricity import succession as succ
    run_id = uuid.uuid4().hex                          # this attempt's identifier

    stage[0] = "inputs"
    names = by_unit_names()
    for n in names:                                    # the scoped listing's names, and only those, become readable
        pol.reads = pol.reads | {os.path.normpath(str(BY_UNIT / n))}
    succession_sha, succession_bytes = guard.read_once(SUCCESSION)
    quantities_sha, quantities_bytes = guard.read_once(QUANT)
    outcomes_sha, outcomes_bytes = guard.read_once(OUTCOMES)
    sales_sha = guard.sha256(SALES)                    # DuckDB reads this file itself: hashed before and after (below)
    inputs = {"sales": sales_sha, "succession": succession_sha, "quantities": quantities_sha, "outcomes": outcomes_sha}
    print(f"P1 availability flag build, definition {av.DEFINITION_VERSION}")
    print(f"inputs: sales {sales_sha} | succession {succession_sha} | quantities {quantities_sha}")

    stage[0] = "load"
    sales = panel.load_sales(SALES)                    # a native read, declared in the record
    if guard.sha256(SALES) != sales_sha:
        raise guard.Refusal("the raw sales file changed while it was being read: stopped")
    if not flag_domain_ok(sales.data_observed):
        raise guard.Refusal("an observation flag outside true, false or missing: stopped")
    mapping = succ.resolve(succ.load(io.BytesIO(succession_bytes)))
    stage[0] = "build"
    q, o = panel.build(sales, succession=mapping)      # NonFinitePrice stops here (D-70 item 1)
    del sales
    stage[0] = "checks"
    if q.duplicated(KEYS).any() or o.duplicated(KEYS).any():
        raise guard.Refusal("duplicate utility-state-year keys in the build: stopped")
    stage[0] = "identity"
    o_rt, q_rt = roundtrip(o), roundtrip(q)
    outcomes_ok = same_frame(o_rt, parse_parquet(outcomes_bytes), KEYS)
    del outcomes_bytes
    want = {unit_name(u, st) for u, st in o_rt[["utility_id_eia", "state"]].drop_duplicates().itertuples(index=False)}
    by_unit_ok = names == want
    if by_unit_ok:
        for (u, st), rows in o_rt.groupby(["utility_id_eia", "state"], sort=False):
            if not same_frame(rows, read_parquet(BY_UNIT / unit_name(u, st)), KEYS):
                by_unit_ok = False
                break
    disk_q = parse_parquet(quantities_bytes)
    del quantities_bytes
    existing = [c for c in disk_q.columns if c not in av.NEW_QUANTITY_COLS]
    quant_ok = (set(existing) == set(q_rt.columns) - set(av.NEW_QUANTITY_COLS)
                and same_frame(q_rt[existing], disk_q[existing], KEYS))
    del disk_q
    stage[0] = "checks"
    flag_ok, reason_ok = flag_checks(q, o)
    del o, o_rt
    checks = dict(zip(av.P1_CHECKS, (outcomes_ok, by_unit_ok, quant_ok, flag_ok, reason_ok)))
    yn = lambda b: "yes" if b else "no"  # noqa: E731
    print(f"outcomes identical to disk: {yn(outcomes_ok)}")
    print(f"by-unit files identical to disk: {yn(by_unit_ok)}")
    print(f"existing quantity columns identical to disk: {yn(quant_ok)}")
    print(f"flag equals the analysis filter on every row: {yn(flag_ok)}")
    print(f"one first exclusion reason per row from the fixed list, consistent with the quantity columns: {yn(reason_ok)}")
    if not all(checks.values()):
        print("wrote nothing")
        return 1

    record = {
        "what_this_is": "P1's record: the flag build's inputs, checks and recorded access events. No revenue, price, sum or ratio.",
        "schema_version": av.SCHEMA_VERSIONS["p1_record"],
        "quantities_columns_schema_version": av.SCHEMA_VERSIONS["quantities_columns"],
        "status": av.IN_PROGRESS,
        "run_id": run_id,
        "definition_version": av.DEFINITION_VERSION,
        "analysis_filter": av.ANALYSIS_FILTER,
        "authorized_by": entry,
        "authorization_entry_sha256": pins["entry_sha256"],
        "pinned_files": list(av.P1_PINNED),
        "interpreter": interpreter,
        "sandbox_profile_sha256": profile_sha,
        "git_commit": guard.git_commit(REPO),
        "inputs_sha256": inputs,
        "by_unit_files": len(names),
        "checks": checks,
        "versions": versions,
    }
    stage[0] = "record"
    problems = records.p1_provenance_problems(record, pins)   # the readers' own checks, before anything is replaced
    if problems:
        raise guard.Refusal("the record this build would write does not pass the readers' checks (" + "; ".join(problems) + "): stopped")
    stage[0] = "mark attempt"
    write_record(record)                               # any earlier record stops describing the file from here on
    stage[0] = "write quantities"
    guard.write_atomically(QUANT, lambda f: q.to_parquet(f, index=False))
    stage[0] = "write record"
    record.update({
        "status": av.COMPLETED,
        "quantities_written_sha256": guard.sha256(QUANT),
        "native_reads_declared": [{"path": str(SALES), "by": "duckdb (panel.load_sales)",
                                   "note": "not seen by the audit hook; limited by the sandbox profile; hashed before and after, "
                                           "which does not prove it was unchanged throughout the read (D-75 item 2)"}],
        "recorded_events": pol.record,
        "recorded_events_note": "Events the Python audit hook saw. They are not proof of every access: native libraries open "
                                "files without raising Python events, and the sandbox profile is what limits those.",
    })
    write_record(record)
    print(f"wrote: data/interim/panel_quantities.parquet, data/interim/availability/p1_record.json (run {run_id})")
    return 0


if __name__ == "__main__":
    sys.exit(guard.run(main, "P1"))
