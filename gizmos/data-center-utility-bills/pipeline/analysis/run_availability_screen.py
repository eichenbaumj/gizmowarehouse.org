#!/usr/bin/env python3
"""The one command that would use the availability mask: the provisional screen of the dependency adapter.

    python3 -I pipeline/analysis/run_availability_screen.py --print-pins
    python3 -I pipeline/analysis/run_availability_screen.py --authorized-by D-NN --corrections PATH --corrections-sha256 HEX \\
        --pool PATH --pool-sha256 HEX --mask-sha256 HEX --states AA,BB,... --out PATH
    python3 -I pipeline/analysis/run_availability_screen.py --authorized-by D-NN ...the same inputs... --recheck RECORD

The third form writes nothing. It recomputes the five fingerprints from what is then in force and says whether the
record still stands or names what changed. If anything changed the whole screen is void (the adapter, brief 4.8).

Built on 2026-11-18 under D-83, which authorizes implementation and synthetic testing only. **It has never been run on
research data, and building it authorizes nothing.** It refuses to start unless `--authorized-by` names a ledger entry
that speaks of the availability audit and carries a pin block, headed `availability-screen-pins v1`, with the hash of
every project module this process has loaded, the versions of its libraries and its interpreter. No entry in the
ledger carries that block. Joe's separate instruction would be the first.

What it would read, and nothing else under data/:
  * the mask `data/interim/availability/outcome_availability.csv`: its bytes once, hashed, and four columns parsed
    (utility_id_eia, state, year, usable). The first exclusion reason and the two imputation statuses are not parsed;
  * the mask's sidecar: run identifier, audit attempt, definition version, status, mask hash;
  * the frozen inventory, through `pass_c_expand.load_frozen()` (load and sales; no price or revenue column);
  * `data/frozen/headline_set.csv`, for the list of hosts;
  * the corrections file and the pool file named on the command line, each checked against the hash given there.

What it would write: one record, at --out, which must be inside `data/interim/availability/` (ignored by git). What it
prints: the mask's identity, counts, and the record's five fingerprints. It prints no utility, no site and no flag.

It decides nothing about hosts. A listed host or a possible host is never narrowed (the adapter, brief 4.5).

A limit, stated: the permitted windows come from `power_simulation.py`, which imports the panel-build code at its top.
So this process loads that module. It calls nothing in it and opens no price file. Every project module the process
has loaded is pinned, that one included, and the mask is not read if the loaded set differs from the pinned set.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.analysis import availability_adapter as adapter  # noqa: E402
from pipeline.electricity import access_guard as guard  # noqa: E402
from pipeline.electricity import availability_codes as av  # noqa: E402
from pipeline.facilities import match_county_gis  # noqa: E402,F401  buildout imports it inside a function: loaded here so that it is pinned
from pipeline.facilities import pass_c_exact  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

PIN_HEADER = "availability-screen-pins v1"
LEDGER = ROOT / "docs" / "DECISIONS.md"
OUT_DIR = ROOT / "data" / "interim" / "availability"
MASK = OUT_DIR / "outcome_availability.csv"
SIDECAR = OUT_DIR / "outcome_availability.json"
HEADLINE = ROOT / "data" / "frozen" / "headline_set.csv"
HOSTS_EXPECTED = pass_c_exact.HOSTS_EXPECTED
LIBRARIES = ("python", "numpy", "pandas", "pyarrow")


def library_versions() -> dict:
    import numpy
    import pyarrow
    return {"python": sys.version.split()[0], "numpy": numpy.__version__, "pandas": pd.__version__, "pyarrow": pyarrow.__version__}


def loaded_project_files(root: Path = ROOT) -> tuple:
    """Every file of this project's `pipeline` package that this process has imported, as paths relative to the root."""
    out = set()
    for name, m in list(sys.modules.items()):
        f = getattr(m, "__file__", None)
        if f and (name == "pipeline" or name.startswith("pipeline.") or name == "__main__"):
            p = Path(f).resolve()
            if root.resolve() in p.parents:
                out.add(p.relative_to(root.resolve()).as_posix())
    out.add(Path(__file__).resolve().relative_to(ROOT.resolve()).as_posix())
    return tuple(sorted(out))


def pin_block(root: Path = ROOT) -> str:
    """The block Joe's instruction would carry. Printed, never written into the ledger by this code."""
    v = library_versions()
    lines = [PIN_HEADER]
    lines += [f"sha256 {guard.sha256(Path(root) / rel)} {rel}" for rel in loaded_project_files(root)]
    lines += [f"version {lib} {v[lib]}" for lib in LIBRARIES]
    lines += [f"interpreter {os.path.realpath(sys.executable)}"]
    return "\n".join(lines)


def _checked(path, expected: str, what: str) -> bytes:
    sha, data = guard.read_once(path)
    if sha != expected:
        raise guard.Refusal(f"{what} is not the file the instruction names (its hash differs)")
    return data


def read_mask(expected_sha: str) -> tuple[pd.DataFrame, dict]:
    """(the mask's four columns, its identity). One read of the mask's bytes: what is hashed is what is parsed."""
    side = json.loads(Path(SIDECAR).read_text())
    if side.get("status") != av.COMPLETED:
        raise guard.Refusal("the mask's sidecar is not marked completed")
    if side.get("definition_version") != av.DEFINITION_VERSION:
        raise guard.Refusal("the mask's sidecar is for another definition version")
    data = _checked(MASK, expected_sha, "the mask")
    if side.get("mask_sha256") != expected_sha:
        raise guard.Refusal("the mask's sidecar records another hash for the mask")
    mask = pd.read_csv(io.BytesIO(data), usecols=list(adapter.MASK_COLUMNS), dtype={"state": str})
    if len(mask) != side.get("rows"):
        raise guard.Refusal("the mask does not have the number of rows its sidecar records")
    identity = {"run": str(side.get("run_id") or ""), "audit_attempt": str(side.get("attempt_id") or ""),
                "definition": str(side.get("definition_version") or ""), "mask_sha256": expected_sha}
    return mask, identity


def read_pool(data: bytes) -> list:
    pool = pd.read_csv(io.BytesIO(data), dtype={"state": str})
    if list(pool.columns) != ["utility_id_eia", "state"]:
        raise guard.Refusal("the pool file's columns are not exactly utility_id_eia, state")
    if pool.isna().any().any() or pool.duplicated().any():
        raise guard.Refusal("the pool file has a missing value or a repeated unit")
    return [(int(u), s) for u, s in pool.itertuples(index=False)]


def out_path(p) -> Path:
    p = Path(p).resolve()
    if OUT_DIR.resolve() not in p.parents or p.suffix != ".json" or p.exists():
        raise guard.Refusal("--out must be a new .json file inside data/interim/availability/")
    return p


def _prepare(a):
    """Everything both forms share: the authorization, the named inputs, the table, and last of all the mask."""
    entry, pins = guard.check_authorization(LEDGER, a.authorized_by, ROOT, loaded_project_files(), PIN_HEADER)
    guard.check_interpreter(pins)
    guard.check_versions(pins["versions"], {lib: library_versions()[lib] for lib in LIBRARIES})
    states = sorted({s.strip() for s in a.states.split(",") if s.strip()})
    if not states:
        raise guard.Refusal("no state named: nothing is covered")
    corrections = json.loads(_checked(a.corrections, a.corrections_sha256, "the corrections file"))
    pool = read_pool(_checked(a.pool, a.pool_sha256, "the pool file"))
    hosts = pass_c_exact.hosts_from_headline(pd.read_csv(HEADLINE))
    if len(hosts) != HOSTS_EXPECTED:
        raise guard.Refusal(f"the headline file gives {len(hosts)} hosts, not {HOSTS_EXPECTED}")
    inp = px.load_frozen()
    table = adapter.dependency_table(inp, px.parse_corrections(corrections, inp), states)
    # The mask is read last, after everything that does not need it has been settled.
    if loaded_project_files() != tuple(sorted(pins["files"])):
        raise guard.Refusal("the project modules loaded are not exactly the ones the entry pins")
    mask, identity = read_mask(a.mask_sha256)
    return entry, pins, states, corrections, pool, hosts, table, mask, identity


def recheck(a) -> int:
    path = Path(a.recheck).resolve()
    if OUT_DIR.resolve() not in path.parents or not path.is_file():
        raise guard.Refusal("--recheck must name a record inside data/interim/availability/")
    record = json.loads(path.read_text())
    entry, pins, states, corrections, pool, hosts, table, mask, identity = _prepare(a)
    reasons = adapter.reopen_reasons(record, mask, identity, pool, hosts, table, states, corrections)
    print(f"availability screen recheck, rule {adapter.RULE_VERSION}, under {entry}")
    if reasons:
        print("the screen is void: every question it deferred is open again. Changed: " + ", ".join(reasons))
        return 1
    print("the screen stands: none of the five fingerprints has changed")
    return 0


def run(a) -> int:
    out = out_path(a.out)
    entry, pins, states, corrections, pool, hosts, table, mask, identity = _prepare(a)
    record = adapter.screen(mask, identity, pool, hosts, table, states, corrections)
    record.update({"authorized_by": entry, "authorization_entry_sha256": pins["entry_sha256"], "mask_identity": identity,
                   "inputs_sha256": {"corrections": a.corrections_sha256, "pool": a.pool_sha256},
                   "covered_states": states, "provisional": True,
                   "note": "Provisional. It removes no site and no load from the inventory, the anchoring or the joint check, "
                           "decides nothing about hosts, and is not a sample size. Recheck with reopen_reasons before relying on it."})
    guard.write_atomically(out, lambda f: f.write((json.dumps(record, indent=1) + "\n").encode()))
    why = {}
    for r in record["retained"].values():
        key = adapter.NOT_NARROWED.rstrip(": ") if r.startswith(adapter.NOT_NARROWED) else r
        why[key] = why.get(key, 0) + 1
    print(f"availability screen, rule {record['rule_version']}, under {entry}")
    print(f"mask: run {identity['run']} | audit attempt {identity['audit_attempt']} | definition {identity['definition']} | {identity['mask_sha256']}")
    print(f"states covered {len(states) - len(record['refused_states'])} of {len(states)} named | pool {len(pool)} | "
          f"listed hosts {len(hosts)} | protected {len(record['protected'])} | narrowed {len(record['narrowed'])}")
    print(f"questions: deferrable {len(record['deferrable'])} | retained {len(record['retained'])}"
          + "".join(f" | {k} {n}" for k, n in sorted(why.items())))
    print("fingerprints: " + " | ".join(f"{k} {record['fingerprints'][k]}" for k in adapter.FINGERPRINTS))
    print(f"wrote: data/interim/availability/{out.name}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The provisional availability screen. Refuses without Joe's pinned ledger entry.")
    ap.add_argument("--print-pins", action="store_true", help="print the pin block for the code as it is now, and stop")
    for name in ("authorized-by", "corrections", "corrections-sha256", "pool", "pool-sha256", "mask-sha256", "states", "out", "recheck"):
        ap.add_argument(f"--{name}")
    a = ap.parse_args(argv)
    if a.print_pins:
        print(pin_block())
        return 0
    try:
        if a.out and a.recheck:
            raise guard.Refusal("give --out or --recheck, not both", 4)
        missing = [n for n in ("corrections", "corrections_sha256", "pool", "pool_sha256", "mask_sha256", "states")
                   + (() if a.recheck else ("out",)) if not getattr(a, n)]
        if missing:
            raise guard.Refusal("missing: " + ", ".join("--" + n.replace("_", "-") for n in missing), 4)
        return recheck(a) if a.recheck else run(a)
    except guard.Refusal as e:
        print(f"screen refused: {e}")
        print("wrote nothing")
        return getattr(e, "code", 2) or 2


if __name__ == "__main__":
    sys.exit(main())
