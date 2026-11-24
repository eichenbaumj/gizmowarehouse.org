#!/usr/bin/env python3
"""The simulation's never-host access list (docs/gate1/step-e-rules-2026-11-18.md section 9, ADOPTED, D-95).

The owner's words, which govern:

    "The rule must define never-host eligibility and honor all existing price holds; absence from the final host set alone
    is insufficient. Previously classified hosts may enter only where an adopted ruling explicitly permits their price
    access. Otherwise exclude them from the simulation's access list without holding up other work. Generate and commit
    the list and its hash before opening any outcome file, and restrict the reader to those named units. This grants
    access only to their per-unit price files for the authorized simulation, not the full outcome panel."

    "Former hosts without explicit price-access authorization remain excluded; comparison eligibility alone is not
    permission to read prices."

A unit (utility, state) is on the list only if every condition holds; an excluded unit carries the FIRST that fails.
Full-window usability (N6) is a requirement in addition to the never-host restrictions (N1, N2, N3, N5) and the price-hold
restriction (N4) and replaces none of them; the previously authorized availability handling is unchanged (adopted by the
owner on 2026-11-18, Stop 3, after the simulation's results were available; wording only, the list is built as before):

    load_unknown_D96  checked first: a load-unknown site reaches it (D-96), so the inventory frame cannot settle any of
                      the conditions below for it, and the frame is not allowed to decide price access.
    N1  comparison-eligible as power_simulation.design defines it, as built (the universe) and with no anchoring
        (treatment_bounds_by_utility.csv, max_share_a and clean_b).
    N2  under 0.5% in every admissible history the sets test: D-46 ruling 4 and the frame's place test
        (treatment_bounds_by_utility.csv, lost_* and ruling_4_*), and every timing configuration (timing_place_test.json:
        its place must be "comparison" and kept). I am uncertain whether every capacity case of D-61 section 5 reaches
        these two files; the inventory side's files are what is read.
    N3  not in set_aside (either variant), any bounds_lists list or dates_and_histories_reasons, at 2% or 5%.
    N4  not in price_hold.csv (a hold recorded anywhere else must be added there first; this script cannot find it).
    N5  never an early, cohort, late or outside-cohort host at 2% or 5% in any frozen set file on disk or any committed
        version of one, unless the allow-file names it with its ledger entry and quoted words.
    N6  usable (usable_flag.read) in all ten years of at least one cohort window, or in all six years of the second
        number's long form. That reading is the session's working-out of D-95, labelled so in the rules file.
    N7  a per-unit outcome file exists, checked by path only (os.path.exists on panel.unit_file's path; never opened,
        never listed by directory).

The universe is every unit power_simulation.design() returns as comparison-eligible at 2% or 5% with no price hold
applied (so held units are named under N4 rather than vanishing).

Reads quantity files only: the quantities file and the dose file (through the panel's and the design's own loaders), the
frozen reports, the timing and unknown-load files, the usable flag, price_hold.csv, the allow-file, and the set files'
committed versions (read-only `git log` and `git show` on those paths, the one use of git). No price, no revenue, nothing
under data/blind is opened.

Writes simulation_access_list.csv (utility_id_eia, state, name), simulation_access_excluded.csv (reason codes, with the
file and commit for N5) and simulation_access_list.sha256 beside this file, and prints counts by reason only.

Run:  python3 -I pipeline/analysis/simulation_access_list.py          after the rebuild and step D, before any outcome file
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.analysis import power_simulation as ps  # noqa: E402

HERE = Path(__file__).resolve().parent
FROZEN = ROOT / "data" / "frozen"
LIST_PATH = HERE / "simulation_access_list.csv"
EXCLUDED_PATH = HERE / "simulation_access_excluded.csv"
HASH_PATH = HERE / "simulation_access_list.sha256"
ALLOW_PATH = HERE / "simulation_access_allow.csv"
ALLOW_COLUMNS = ["utility_id_eia", "state", "ledger_entry", "quoted_words"]
SET_FILES = ("data/frozen/headline_set.csv", "data/frozen/headline_set_before_ruling_4.csv", "data/frozen/treatment_bounds.json",
             "data/frozen/treatment_bounds_by_utility.csv", "data/frozen/power_simulation.json")
THETAS = (0.02, 0.05)
HOST_PLACES = {"cohort", "early", "late", "outside_cohorts"}
NON_HOST_PLACES = {"comparison", "neither", "never", ""}
REASONS = ("load_unknown_D96", "N1_not_under_0.5pct_with_no_anchoring",
           "N2_not_under_0.5pct_in_every_admissible_history", "N3_set_aside_or_on_a_bounds_list", "N4_price_hold",
           "N5_former_host_without_an_allow_row", "N6_no_full_usable_window", "N7_no_per_unit_outcome_file")
UNIT = re.compile(r"^\d+:[A-Z]{2}$")
DESCRIPTION = ("The simulation's never-host access list (step E rules section 9, D-95): a unit is listed only if no load-unknown site "
               "reaches it (D-96), it passes every never-host restriction (comparison-eligible with no anchoring and in every admissible history; not set aside or on "
               "a bounds list; never a former host without an allow row), is not under a price hold, has a per-unit outcome file, "
               "and is usable in all ten years of a cohort window or all six years of the long form. Full-window usability is a "
               "requirement in addition to the never-host and price-hold restrictions and replaces none of them; the "
               "previously authorized availability handling is unchanged. Wording adopted by the owner on 2026-11-18 (Stop 3), "
               "after the simulation's results were available.")


class AccessListError(RuntimeError):
    """The list cannot be generated, or a list on disk cannot be trusted. Nothing is read until it is fixed."""


# ---- the list and its hash ---------------------------------------------------------------------------------------

def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verified_list(list_path: Path | None = None, hash_path: Path | None = None) -> set:
    """The listed units, after recomputing the list's SHA-256 and comparing it with the committed one. Refuses otherwise."""
    list_path, hash_path = Path(list_path or LIST_PATH), Path(hash_path or HASH_PATH)
    for p in (list_path, hash_path):
        if not p.exists():
            raise AccessListError(f"{p.name} is missing: the simulation reads no price until the access list and its hash "
                                  "are generated and committed (step-e rules section 9)")
    recorded = hash_path.read_text().split()[0] if hash_path.read_text().split() else ""
    if file_sha256(list_path) != recorded:
        raise AccessListError(f"{list_path.name} does not match {hash_path.name}: the list changed after its hash was recorded; "
                              "no price is read")
    t = pd.read_csv(list_path, dtype={"utility_id_eia": int, "state": str}, keep_default_na=False)
    if list(t.columns[:2]) != ["utility_id_eia", "state"] or t.duplicated(["utility_id_eia", "state"]).any():
        raise AccessListError(f"{list_path.name} is malformed (columns or repeated units)")
    return set(zip(t.utility_id_eia.astype(int), t.state))


# ---- inputs --------------------------------------------------------------------------------------------------------

def load_allow(path: Path | None = None) -> dict:
    """(utility, state) -> its row. Every row needs the ledger entry and the quoted words of an adopted ruling."""
    path = Path(path or ALLOW_PATH)
    if not path.exists():
        raise AccessListError(f"{path.name} is missing: it is committed with this script, starting as a header with no rows")
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(t.columns) != ALLOW_COLUMNS:
        raise AccessListError(f"{path.name} must have exactly the columns {ALLOW_COLUMNS}")
    out = {}
    for i, r in t.iterrows():
        if not (r.utility_id_eia.strip().isdigit() and r.state.strip() and r.ledger_entry.strip() and r.quoted_words.strip()):
            raise AccessListError(f"row {i + 2} of {path.name} lacks a unit, its ledger entry or the ruling's quoted words")
        out[(int(r.utility_id_eia), r.state.strip())] = dict(r)
    return out


def _key(x) -> tuple:
    u, st = str(x).split(":")
    return (int(u), st)


def _walk_units(obj) -> set:
    """Every unit named anywhere inside `obj`: "id:ST" strings, or dicts with a "utility" field of that form."""
    out = set()
    if isinstance(obj, dict):
        if isinstance(obj.get("utility"), str) and UNIT.match(obj["utility"]):
            out.add(_key(obj["utility"]))
        for v in obj.values():
            out |= _walk_units(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _walk_units(v)
    elif isinstance(obj, str) and UNIT.match(obj):
        out.add(_key(obj))
    return out


def host_keys_in(relpath: str, text: str) -> set:
    """The units one version of one set file shows as an early, cohort, late or outside-cohort host. Stops if it cannot
    tell: an unparseable version cannot establish N5, and treating it as harmless is not allowed."""
    name = Path(relpath).name
    try:
        if name in ("headline_set.csv", "headline_set_before_ruling_4.csv"):
            t = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
            if "utility" in t.columns and "utility_id_eia" not in t.columns:
                return {_key(x) for x in t.utility if UNIT.match(x)}
            return {(int(u), st) for u, st in zip(t.utility_id_eia, t.state) if u.strip()}     # every row is a cohort utility
        if name == "treatment_bounds_by_utility.csv":
            t = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
            places = [c for c in t.columns if c.startswith("place_")]
            if not places:
                raise ValueError("no place column")
            bad = {v for c in places for v in t[c].unique()} - HOST_PLACES - NON_HOST_PLACES
            if bad:
                raise ValueError(f"place values not recognized: {sorted(bad)}")
            host = t[places].isin(HOST_PLACES).any(axis=1)
            return set(zip(t.utility_id_eia[host].astype(int), t.state[host]))
        if name == "treatment_bounds.json":
            doc = json.loads(text)
            out = set()
            for r in doc.get("thresholds", {}).values():
                for k, v in r.items():
                    if k in ("sets", "early_hosts", "labelled_runs_beside_the_headline"):
                        out |= _walk_units(v)
            return out
        if name == "power_simulation.json":
            doc = json.loads(text)

            def hosts(o):
                found = set()
                if isinstance(o, dict):
                    for k, v in o.items():
                        found |= _walk_units(v) if "host" in k.lower() else hosts(v)
                elif isinstance(o, list):
                    for v in o:
                        found |= hosts(v)
                return found
            return hosts(doc)
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        raise AccessListError(f"cannot read the hosts in a version of {relpath}: {e}; N5 cannot be established") from None
    raise AccessListError(f"{relpath} is not a set file this script knows how to read")


def git_versions(root: Path, relpath: str) -> list:
    """[(commit, text)] for every committed version of `relpath`, newest first. Read-only git, on that path alone."""
    try:
        log = subprocess.run(["git", "-C", str(root), "log", "--format=%H", "--", relpath], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise AccessListError(f"git log on {relpath} failed ({e}); N5 needs every committed version") from None
    out = []
    for c in log.stdout.split():
        r = subprocess.run(["git", "-C", str(root), "show", f"{c}:./{relpath}"], capture_output=True, text=True)
        if r.returncode == 0:                         # a commit that deleted the file has no version of it
            out.append((c, r.stdout))
    return out


def former_hosts(root: Path, set_files=SET_FILES) -> dict:
    """(utility, state) -> {"file", "commit"}: the first version (working tree, then newest commit first) showing it as a host."""
    found: dict = {}
    for rel in set_files:
        versions = []
        disk = Path(root) / rel
        if disk.exists():
            versions.append(("working tree", disk.read_text()))
        versions += git_versions(Path(root), rel)
        for commit, text in versions:
            for k in host_keys_in(rel, text):
                found.setdefault(k, {"file": rel, "commit": commit})
    return found


def n1_n2_frame(frozen: Path) -> tuple[dict, dict]:
    """From treatment_bounds_by_utility.csv: N1 failures with no anchoring, and N2 failures under ruling 4 or the frame's
    place test. A unit with no row there had no load share in any of the bounds' readings."""
    path = frozen / "treatment_bounds_by_utility.csv"
    if not path.exists():
        raise AccessListError(f"{path.name} is missing: run treatment_bounds.py on the rebuilt inventory first")
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    n1, n2 = {}, {}
    for _, r in t.iterrows():
        k = (int(r.utility_id_eia), r.state)
        share_a = pd.to_numeric(r.get("max_share_a", ""), errors="coerce")
        if str(r.get("clean_b", "True")) == "False" or (pd.notna(share_a) and share_a >= ps.CLEAN_BELOW):
            n1[k] = "no anchoring puts it at 0.5% or more, or as built it is not clean"
        why = [f"{c}: {r[c]}" for c in t.columns if c.startswith(("lost_", "ruling_4_")) and str(r[c]).strip()]
        if why:
            n2[k] = "; ".join(why)[:300]
    return n1, n2


def n2_timing(frozen: Path, rebuilt: bool) -> dict:
    """From timing_place_test.json: a unit whose place is not "comparison" in every admissible timing configuration."""
    path = frozen / "timing_place_test.json"
    if not path.exists():
        if rebuilt:
            raise AccessListError(f"{path.name} is missing on a rebuilt inventory: run timing.py first")
        return {}
    out = {}
    for r in json.loads(path.read_text()).get("utilities", []):
        place = (r.get("reference") or {}).get("place")
        if r.get("keeps_its_place") is not True or place != "comparison":
            out.setdefault(_key(r["utility"]), f"timing at {float(r['theta']):.0%}: place {place}, keeps its place "
                                               f"{r.get('keeps_its_place')}, {r.get('status', '')}"[:300])
    return out


def n3_set_aside(frozen: Path) -> dict:
    out: dict = {}
    for theta in THETAS:
        t = f"{theta:.0%}"
        for ten in (False, True):
            for k in ps.set_aside(theta, frozen, ten_year_case=ten):
                out.setdefault(k, f"set_aside at {t}" + (" with the ten-year case" if ten else ""))
        for name, members in ps.bounds_lists(theta, frozen).items():
            for k in members:
                out.setdefault(k, f"bounds list {name} at {t}")
        for k in ps.dates_and_histories_reasons(theta, frozen):
            out.setdefault(k, f"dates and histories at {t}")
    return out


def n6_usable(usable: set) -> set:
    """Units usable in all ten years of at least one cohort window, or all six years of the long form (session's reading)."""
    by: dict = {}
    for u, st, y in usable:
        by.setdefault((int(u), st), set()).add(int(y))
    windows = [set(range(g - ps.PRE, g + ps.POST + 1)) for g in range(ps.COHORTS[0], ps.COHORTS[1] + 1)]
    long_form = set(ps.LONG_PRE + ps.LONG_POST)
    return {k for k, ys in by.items() if long_form <= ys or any(w <= ys for w in windows)}


def outcome_file_exists(key: tuple) -> bool:
    """N7: by path only. os.path.exists on the path panel.load_outcomes would open; the file is never opened or listed."""
    from pipeline.electricity import panel
    return os.path.exists(panel.unit_file(key[0], key[1]))


# ---- the list ---------------------------------------------------------------------------------------------------------

def generate(q: pd.DataFrame, dose: pd.DataFrame, *, frozen: Path, root: Path, usable: set, unknown: "ps.UnknownLoad",
             rebuilt: bool, allow_path: Path | None = None, hold_path: Path | None = None, exists=None,
             set_files=SET_FILES) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(listed, excluded). Every unit design() would read is in exactly one of them. Paths left as None are the committed
    ones (ALLOW_PATH, power_simulation.PRICE_HOLD); `exists` defaults to outcome_file_exists."""
    allow_path = ALLOW_PATH if allow_path is None else allow_path
    hold_path = ps.PRICE_HOLD if hold_path is None else hold_path
    exists = outcome_file_exists if exists is None else exists
    universe: dict = {}
    for theta in THETAS:
        _, clean = ps.design(q, dose, theta, ps.history_settled(theta, frozen), hold=set())
        for k in zip(clean.utility_id_eia.astype(int), clean.state):
            universe.setdefault(k, None)
    names = q.groupby(ps.KEY).utility_name.last() if "utility_name" in q.columns else pd.Series(dtype=str)
    held = ps.price_hold(hold_path)
    allow = load_allow(allow_path)
    n1, n2 = n1_n2_frame(frozen)
    n2t = n2_timing(frozen, rebuilt)
    n3 = n3_set_aside(frozen)
    hosts = former_hosts(root, set_files)
    good = n6_usable(usable)
    listed, excluded = [], []
    for k in sorted(universe):
        reason, detail, src = None, "", {}
        if k in unknown.affected:
            reason, detail = "load_unknown_D96", ps.LOAD_UNKNOWN
        elif k in n1:
            reason, detail = "N1_not_under_0.5pct_with_no_anchoring", n1[k]
        elif k in n2 or k in n2t:
            reason, detail = "N2_not_under_0.5pct_in_every_admissible_history", n2.get(k) or n2t[k]
        elif k in n3:
            reason, detail = "N3_set_aside_or_on_a_bounds_list", n3[k]
        elif k in held:
            reason, detail = "N4_price_hold", "price_hold.csv"
        elif k in hosts and k not in allow:
            reason, detail, src = "N5_former_host_without_an_allow_row", "shown as a host", hosts[k]
        elif k not in good:
            reason, detail = "N6_no_full_usable_window", "no cohort window and no long form usable in every year"
        elif not exists(k):
            reason, detail = "N7_no_per_unit_outcome_file", "no file at the per-unit path"
        row = {"utility_id_eia": k[0], "state": k[1], "name": names.get(k)}
        if reason is None:
            listed.append(row)
        else:
            excluded.append({**row, "reason": reason, "detail": detail, "n5_file": src.get("file", ""), "n5_commit": src.get("commit", "")})
    return (pd.DataFrame(listed, columns=["utility_id_eia", "state", "name"]),
            pd.DataFrame(excluded, columns=["utility_id_eia", "state", "name", "reason", "detail", "n5_file", "n5_commit"]))


def write(listed: pd.DataFrame, excluded: pd.DataFrame, list_path: Path | None = None, excluded_path: Path | None = None,
          hash_path: Path | None = None) -> str:
    list_path, excluded_path, hash_path = list_path or LIST_PATH, excluded_path or EXCLUDED_PATH, hash_path or HASH_PATH
    listed.to_csv(list_path, index=False)
    excluded.to_csv(excluded_path, index=False)
    h = file_sha256(list_path)
    Path(hash_path).write_text(f"{h}  {Path(list_path).name}\n")
    return h


def main() -> int:
    from pipeline.analysis import design, usable_flag
    rebuilt = ps.rebuilt_inventory()
    unknown = ps.load_unknown_load(rebuilt=rebuilt)
    q, dose, _regions, _fuel, _dd = design.load()
    listed, excluded = generate(q, dose, frozen=FROZEN, root=ROOT, usable=usable_flag.read().usable, unknown=unknown, rebuilt=rebuilt)
    h = write(listed, excluded)
    counts = Counter(excluded.reason)
    print(DESCRIPTION)
    print(f"listed: {len(listed)}")
    for r in REASONS:
        print(f"excluded, {r}: {counts.get(r, 0)}")
    print(f"sha256 of {Path(LIST_PATH).name}: {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
