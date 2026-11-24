#!/usr/bin/env python3
"""P2, the availability audit: reads the flag build's columns from the quantities file and nothing that holds a price.

Route: docs/gate1/availability-audit-route.md. Rulings: D-70 as amended by D-72, adopted in D-73. A run on
research data needs Joe's separate execution instruction, logged as a ledger entry carrying the pin block, and is
started only by run_availability.sh:

    sh pipeline/electricity/run_availability.sh p2 --authorized-by D-NN

It does not know who is a host. It opens the ledger (the entry named), P1's record, and the quantities file (ten
named columns: the keys, P1's four, and four quantity columns used only for consistency checks). It refuses unless
P1's record shows the five named checks passed, carries a run identifier, matches the quantities file byte for
byte, carries its four input hashes and this code's analysis filter, records the pinned interpreter, library
versions and sandbox profile, and was made under the authorizing entry as it stands now (check_p1_record;
availability_records.py says which fields are checked and which are only recorded). It writes one row per utility, state and year in 2001-2025 (the mask), then a sidecar that names the run,
the mask's hash and P1's record's hash and says it completed, with predetermined counts by first applicable
exclusion reason. The counts depend on the order of the reasons: a utility-year that fails several tests is
counted once, under the first.

Permitted output, success (exit 0), and nothing else:
    P2 availability audit, definition <version>
    read: data/interim/panel_quantities.parquet <sha256> (run <32 hex>)
    first applicable exclusion reason, utility-years: <code> <n> | ... (every code, in order, zeros included)
    wrote: data/interim/availability/outcome_availability.csv (<rows> rows), data/interim/availability/outcome_availability.json (audit attempt <32 hex>)
Permitted output, stopped: the status lines already printed, if any, then one line, "P2 stopped at <stage>:
<refusal or exception class name>", exit 2, 3 (isolation not in force) or 4 (not authorized, or code, a library or
the interpreter not as pinned). A refusal names identifiers only. Standard error is closed.

Failure handling. P2 refuses unless P1's record is "completed", names this authorization, and wrote exactly the
quantities file it reads (hashed and parsed from one read). Before writing, it checks the sidecar it would write
against the readers' own provenance checks, then rewrites the sidecar with this attempt's identifier and status
"in_progress", so no earlier sidecar still vouches for the mask; then the mask; then the sidecar "completed",
naming the mask's hash. A stop after the first of those writes and before the last leaves a sidecar that is not
"completed", which the preservation step refuses (tested after an earlier successful run). A process killed
outright can leave a ".tmp" file, which the next write replaces.

What the marker does not show (D-76, G3). A stop BEFORE the marker is replaced leaves the earlier sidecar, which
still correctly describes the earlier mask, and a process can write "completed" and stop before it reports
success. A "completed" sidecar never shows that THIS invocation succeeded. Preservation starts only after this
invocation exits 0 and prints its "wrote:" line; that line's audit attempt identifier, and the run identifier on
the "read:" line, are the ones preservation's success line ("preserved run ...") must repeat. That is not always
preservation's first line: a retry that removes a partial folder says so first.
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
QUANT = D / "interim" / "panel_quantities.parquet"
OUT_DIR = D / "interim" / "availability"
P1_RECORD = OUT_DIR / "p1_record.json"
MASK = OUT_DIR / "outcome_availability.csv"
SIDECAR = OUT_DIR / "outcome_availability.json"
LEDGER = ROOT / "docs" / "DECISIONS.md"
PROFILE = ROOT / "pipeline" / "electricity" / "sandbox" / "p2.sb"
PROBE = ROOT / "pipeline" / "electricity" / "sandbox" / "denied_probe.txt"
BANNED = frozenset({"duckdb", "_duckdb", "pipeline.electricity.panel", "pipeline.electricity.succession",
                    "pipeline.electricity.write_usable_flag"})


def policy() -> guard.Policy:
    n = lambda p: os.path.normpath(str(p))  # noqa: E731
    tmp = lambda p: n(str(p) + ".tmp")  # noqa: E731
    return guard.standard_policy(ROOT, reads=frozenset({n(QUANT), n(P1_RECORD)}), writes=frozenset({tmp(MASK), tmp(SIDECAR)}),
                                 renames=frozenset({(tmp(MASK), n(MASK)), (tmp(SIDECAR), n(SIDECAR))}), banned_imports=BANNED)


HEX32, HEX64 = r"[0-9a-f]{32}", r"[0-9a-f]{64}"


def check_p1_record(p1, quantities_sha: str, entry: str, pins: dict) -> str:
    """Refuse unless P1's record is complete and is the one behind this quantities file. Returns the run identifier.

    Every field tested here must be present and well formed; nothing passes because two missing values compare equal
    (D-74, from R3). That covers the status, the versions, the five checks, the identifiers, the linking hash, the
    authorization and the provenance in availability_records.p1_provenance_problems. It does not cover every field
    P1 writes: that module's docstring lists what is recorded and not independently validated (D-76, G2)."""
    import re
    if not isinstance(p1, dict):
        raise guard.Refusal("the flag build's record is not a record")
    if p1.get("status") != av.COMPLETED:
        raise guard.Refusal("the flag build's record is not marked completed (an attempt stopped part way): rerun P1")
    if p1.get("definition_version") != av.DEFINITION_VERSION:
        raise guard.Refusal("the flag build's record is for another definition version: rerun P1")
    if p1.get("schema_version") != av.SCHEMA_VERSIONS["p1_record"]:
        raise guard.Refusal("the flag build's record has an unknown schema version")
    if p1.get("quantities_columns_schema_version") != av.SCHEMA_VERSIONS["quantities_columns"]:
        raise guard.Refusal("the flag build's record names an unknown quantities-column schema version")
    checks = p1.get("checks")
    if not isinstance(checks, dict) or tuple(sorted(checks)) != tuple(sorted(av.P1_CHECKS)):
        raise guard.Refusal("the flag build's record does not name exactly the five checks")
    if not all(checks[c] is True for c in av.P1_CHECKS):
        raise guard.Refusal("the flag build's record does not show all five named checks passed")
    if not re.fullmatch(HEX32, str(p1.get("run_id", ""))):
        raise guard.Refusal("the flag build's record carries no run identifier")
    if not re.fullmatch(HEX64, str(p1.get("quantities_written_sha256", ""))):
        raise guard.Refusal("the flag build's record carries no hash of the quantities file it wrote")
    if p1.get("authorized_by") != entry:
        raise guard.Refusal("the flag build ran under another authorization than this audit")
    if p1["quantities_written_sha256"] != quantities_sha:
        raise guard.Refusal("the quantities file is not the one the flag build wrote (stale or changed since): rerun P1")
    problems = records.p1_provenance_problems(p1, pins)
    if problems:
        raise guard.Refusal("; ".join(problems))
    return p1["run_id"]


def validate(q) -> None:
    """Refuse, naming identifiers only, unless every row carries one valid flag, reason and statuses consistent with
    the quantities."""
    missing = [c for c in av.AUDIT_READ_COLS if c not in q.columns]
    if missing:
        raise guard.Refusal(f"the quantities file lacks {missing}: it was not written by the flag build")
    keys = list(av.KEYS)

    def first(mask, what):
        if mask.any():
            r = q[mask].iloc[0]
            raise guard.Refusal(f"{what}: first at {int(r.utility_id_eia)}:{r.state}:{int(r.year)}")

    first(q.duplicated(keys, keep=False), "duplicate utility-state-year keys")
    first(q[list(av.KEYS)].isna().any(axis=1), "a key is missing")
    first(~q.year.isin(av.PANEL_YEARS), "a year outside 2001-2025")
    first(q[list(av.NEW_QUANTITY_COLS)].isna().any(axis=1), "a null flag, reason or status")
    first(~q[av.FLAG_COL].isin([True, False]), "a flag that is not true or false")
    first(~q[av.REASON_COL].isin(av.BUILD_REASONS + (av.NO_EXCLUSION,)), "an unknown first exclusion reason")
    first(~q[av.UNKNOWN_COL].isin(av.IMPUTATION_STATUS), "an unknown imputation status")
    first(~q[av.SUPPLIER_COL].isin(av.SUPPLIER_STATUS), "an unknown supplier-row status")
    r, flag = q[av.REASON_COL], q[av.FLAG_COL].astype(bool)
    first((r == av.NO_EXCLUSION) != flag, "the flag and the first exclusion reason disagree")
    sales = q.res_mwh.fillna(0) > 0
    floor = q.meets_size_floor.eq(True)
    none_basis = q.supply_price_basis == "none_available"
    first((r == "no_residential_sales") != ~sales, "no_residential_sales does not match the residential sales column")
    first((r == "under_customer_floor") != (sales & ~floor), "under_customer_floor does not match the customer floor column")
    first((r == "no_supply_price") != (sales & floor & none_basis), "no_supply_price does not match supply_price_basis")
    first(none_basis & ~(q.res_mwh_delivery.fillna(0) > 0), "supply_price_basis is none_available with no delivery-only sales")
    first((q[av.SUPPLIER_COL] != "not_used") != (q.supply_price_basis == "state_observed_suppliers"),
          "the supplier-row status does not match supply_price_basis")


def mask_from(q):
    """Every utility-state with a row, crossed with every panel year. A missing year is not_in_panel, not usable."""
    import pandas as pd
    units = q[["utility_id_eia", "state"]].drop_duplicates()
    grid = units.merge(pd.DataFrame({"year": list(av.PANEL_YEARS)}), how="cross")
    m = grid.merge(q[list(av.KEYS) + list(av.NEW_QUANTITY_COLS)], on=list(av.KEYS), how="left", indicator=True)
    present = m._merge == "both"
    out = pd.DataFrame({
        "utility_id_eia": m.utility_id_eia.astype(int), "state": m.state, "year": m.year.astype(int),
        "usable": present & m[av.FLAG_COL].eq(True),
        "first_exclusion_reason": m[av.REASON_COL].where(present, av.NOT_IN_PANEL),
        "imputation_status": m[av.UNKNOWN_COL].where(present, "no_rows"),
        "supplier_rows_imputation_status": m[av.SUPPLIER_COL].where(present, "no_rows"),
    })
    return out.sort_values(list(av.KEYS), kind="stable").reset_index(drop=True)[list(av.MASK_COLUMNS)]


def counts(mask) -> dict:
    vc = mask.first_exclusion_reason.value_counts()
    return {code: int(vc.get(code, 0)) for code in av.ALL_CODES}


def write_sidecar(sidecar: dict) -> None:
    guard.write_atomically(SIDECAR, lambda f: f.write((json.dumps(sidecar, indent=2) + "\n").encode()))


def main(stage) -> int:
    stage[0] = "arguments"
    argv = sys.argv[1:]
    if len(argv) != 2 or argv[0] != "--authorized-by":
        raise guard.Refusal("usage: run_availability.sh p2 --authorized-by D-NN", 4)
    stage[0] = "guard"
    pol = policy()
    guard.install(pol)
    stage[0] = "authorization"
    entry, pins = guard.check_authorization(LEDGER, argv[1], ROOT, av.P2_PINNED, av.PIN_HEADER)
    interpreter = guard.check_interpreter(pins)
    stage[0] = "isolation"
    profile_sha = guard.check_isolation(PROFILE, PROBE)

    stage[0] = "imports"
    import io
    import uuid

    import pandas as pd
    import pyarrow
    import pyarrow.parquet as pq
    versions = {"python": sys.version.split()[0], "pandas": pd.__version__, "pyarrow": pyarrow.__version__}
    guard.check_versions(pins["versions"], versions)
    attempt_id = uuid.uuid4().hex

    stage[0] = "the flag build's record"
    p1_sha, p1_bytes = guard.read_once(P1_RECORD)
    p1 = json.loads(p1_bytes)
    q_sha, q_bytes = guard.read_once(QUANT)            # hashed and parsed from one read (D-75 item 2)
    run_id = check_p1_record(p1, q_sha, entry, pins)

    stage[0] = "read"
    schema = pq.read_schema(io.BytesIO(q_bytes))
    missing = [c for c in av.AUDIT_READ_COLS if c not in schema.names]
    if missing:
        raise guard.Refusal(f"the quantities file lacks {missing}: it was not written by the flag build")
    q = pq.read_table(io.BytesIO(q_bytes), columns=list(av.AUDIT_READ_COLS)).to_pandas()
    del q_bytes
    print(f"P2 availability audit, definition {av.DEFINITION_VERSION}")
    print(f"read: data/interim/panel_quantities.parquet {q_sha} (run {run_id})")

    stage[0] = "validate"
    validate(q)
    stage[0] = "mask"
    mask = mask_from(q)
    del q
    c = counts(mask)
    mask_bytes = mask.to_csv(index=False).encode()

    import hashlib
    attempt = {
        "what_this_is": "The availability mask's sidecar: definition, inputs, predetermined counts and recorded access events. "
                        "No revenue, price, sum or ratio.",
        "schema_version": av.SCHEMA_VERSIONS["sidecar"],
        "mask_schema_version": av.SCHEMA_VERSIONS["mask"],
        "quantities_columns_schema_version": av.SCHEMA_VERSIONS["quantities_columns"],
        "status": av.IN_PROGRESS,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "definition_version": av.DEFINITION_VERSION,
        "authorized_by": entry,
        "authorization_entry_sha256": pins["entry_sha256"],
    }
    sidecar = {
        **attempt,
        "status": av.COMPLETED,
        "mask_sha256": hashlib.sha256(mask_bytes).hexdigest(),
        "p1_record_sha256": p1_sha,
        "analysis_filter": av.ANALYSIS_FILTER,
        "first_exclusion_reason_order": [{"code": av.NOT_IN_PANEL, "test": "no row in the panel for this utility-year", "from": "grid"}]
        + [{"code": code, "test": test, "from": src} for code, test, src in av.REASON_ORDER]
        + [{"code": av.NO_EXCLUSION, "test": "usable", "from": "-"}],
        "counts_by_first_applicable_exclusion_reason": c,
        "counts_note": "Utility-years, counted once each under the FIRST applicable reason in the order above. The counts depend on "
                       "that order: they are not the number of utility-years each test fails.",
        "imputation_status": "known: every contributing residential row carried EIA's imputation flag; unknown: at least one "
                             "had no flag and was kept as observed (D-70 item 2); no_rows: not in the panel.",
        "supplier_rows_imputation_status": "The status of the supplier rows underlying the selected supply component: known or "
                                           "unknown as above where the state's observed supplier average is that component; "
                                           "not_used where it is not; no_rows: not in the panel (D-72 item 2). A utility-year "
                                           "can select that component and still lack a usable outcome for another reason. "
                                           "Neither status certifies completeness.",
        "years": [av.PANEL_YEARS[0], av.PANEL_YEARS[-1]],
        "rows": int(len(mask)),
        "pinned_files": list(av.P2_PINNED),
        "interpreter": interpreter,
        "sandbox_profile_sha256": profile_sha,
        "git_commit": guard.git_commit(REPO),
        "inputs_sha256": {"quantities": q_sha, "p1_record": p1_sha},
        "flag_build": {k: p1.get(k) for k in av.SIDECAR_FLAG_BUILD_KEYS},
        "columns_read": list(av.AUDIT_READ_COLS),
        "versions": versions,
    }
    stage[0] = "sidecar"
    problems = records.sidecar_provenance_problems(sidecar, p1, pins)   # the readers' own checks, before anything is replaced
    if problems:
        raise guard.Refusal("the sidecar this audit would write does not pass the readers' checks (" + "; ".join(problems) + "): stopped")
    stage[0] = "mark attempt"
    write_sidecar(attempt)                             # any earlier sidecar stops vouching for the mask from here on
    stage[0] = "write mask"
    guard.write_atomically(MASK, lambda f: f.write(mask_bytes))
    stage[0] = "write sidecar"
    sidecar.update({
        "recorded_events": pol.record,
        "recorded_events_note": "Events the Python audit hook saw. They are not proof of every access; the sandbox profile "
                                "limits what native code can open.",
    })
    write_sidecar(sidecar)
    print("first applicable exclusion reason, utility-years: " + " | ".join(f"{k} {v}" for k, v in c.items()))
    print(f"wrote: data/interim/availability/outcome_availability.csv ({len(mask)} rows), "
          f"data/interim/availability/outcome_availability.json (audit attempt {attempt_id})")
    return 0


if __name__ == "__main__":
    sys.exit(guard.run(main, "P2"))
