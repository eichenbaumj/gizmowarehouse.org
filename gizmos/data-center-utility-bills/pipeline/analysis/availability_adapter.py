"""The dependency adapter: which open questions of the verification pass may be set aside on an availability mask.

Brief: docs/gate1/dependency-adapter-brief-2026-11-18.md, written and committed before this code. Rulings: D-72 item 3
and the availability ruling's item 8 (route document, section A). Authorized for implementation and synthetic testing
only (D-83). Building this module authorizes nothing: no mask is read here, no pool is screened and no verification is
deferred until Joe gives a separate instruction for using the mask.

Load and sales only. This module opens no file. It reads no price or revenue column. Its inputs are objects the caller
already holds: a `pass_c_expand.Inputs`, parsed corrections, and a mask as a table of (utility, state, year, usable).

What it answers
---------------
One thing: which open questions may be set aside for now because nothing they could change reaches any utility that
still matters or the state's anchoring. It removes no site and no load from anything.

The guarantee (brief, section 2). If a question is listed as deferrable, then for every pair of configurations that
differ only in that question, (a) every utility that is not narrowed has the same load in every panel year in both
readings, and (b) the state's 2024 anchoring totals are the same. Whether a question that reaches a host or a possible
host is deferred never depends on the mask.

How (brief, section 4)
----------------------
  * A question reaches a utility directly if, for some setting of the same site's other questions, two of its settings
    put different load on the utility in some panel year.
  * A question moves the state's anchoring if, for some setting of the site's other questions, two of its settings
    give the site a different 2024 contribution. Read from the contributions and from nothing else: not from whether
    the factor's range is one number, not from any classification. A contribution that is not a finite number makes
    the answer None, and None is retained.
  * Every question `pass_c_expand._sites` lists is considered. The exact attribution's kept sets and its reference are
    not inputs, so nothing here depends on the reference repair of D-72 item 4.
  * A state the caller does not name as covered, or whose table could not be built, has nothing deferred.
  * A listed host, and a possible host (a utility whose upper bound of load reaches the host threshold in some year in
    either reading), is protected: never narrowed. The mask is not consulted in deciding who is protected.
  * A unit is narrowed only if it is in the caller's pool, is not protected, and fails every permitted window.
  * A screen's record carries five fingerprints. If any differs later, the whole screen is void.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from pipeline.analysis import availability as avail
from pipeline.facilities import pass_c_expand as px

RULE_VERSION = "2026-11-18.1"
FINGERPRINTS = ("corrections", "candidates", "dependencies", "mask_identity", "eligibility_rules")
MASK_IDENTITY_FIELDS = ("run", "audit_attempt", "definition", "mask_sha256")
MASK_COLUMNS = ("utility_id_eia", "state", "year", "usable")

OUTSIDE = "outside the attribution's coverage"
UNKNOWN = "anchoring unknown: retained"
MOVES = "moves the state's anchoring"
NO_UTILITY = "reaches no utility: cannot show it affects none"
NOT_NARROWED = "reaches a utility that is not narrowed: "


def _key(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def _unit(key: str) -> tuple[int, str]:
    u, s = key.split(":", 1)
    return int(u), s


def _value(v):
    """A setting as it is written out: a utility id, "off_panel", a year, "never", "early" or "late"."""
    if v is None:
        return px.OFF
    if isinstance(v, (int, np.integer)):
        return int(v)
    return str(v)


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


# ---- the table: what each question reaches, and whether it moves the anchoring ------------------------------------

def _groups(idx: np.ndarray, qi: int) -> list[list[int]]:
    """The site's settings grouped by the settings of its other questions: within a group only question qi differs."""
    others = np.delete(idx, qi, axis=1)
    groups: dict[tuple, list[int]] = {}
    for r in range(len(idx)):
        groups.setdefault(tuple(int(x) for x in others[r]), []).append(r)
    return list(groups.values())


def state_dependencies(inp: px.Inputs, corr: dict, st: str, theta: float = px.THETA) -> dict:
    """One state's table (brief sections 4.1, 4.2 and 4.5). Raises whatever refusal the pass's own code raises."""
    units = inp.units[inp.units.get_level_values("state") == st]
    sites, _, _ = px._sites(inp, corr, st, units)
    questions = []
    for s in sites:
        a = np.asarray(s.a, dtype=float)
        load = np.asarray(s.load, dtype=float)
        on_units = {u for u in s.unit if u is not None}
        for qi, name in enumerate(s.questions):
            groups = _groups(s.idx, qi)
            reached = set()
            for k in on_units:
                lk = load * np.array([u == k for u in s.unit], dtype=bool)[:, None]
                for rows in groups:
                    block = lk[rows]
                    # A load that is not a finite number cannot be shown equal across settings: it counts as reaching.
                    if not np.isfinite(block).all() or (block.max(axis=0) != block.min(axis=0)).any():
                        reached.add(k)
                        break
            if not np.isfinite(a).all():
                moves = None
            else:
                moves = bool(any(np.ptp(a[rows]) > 0 for rows in groups))
            questions.append({"question_id": f"{s.fid} {name}", "fid": s.fid, "question": name,
                              "settings": [_value(v) for v in s.values[qi]],
                              "utilities": sorted((_key(k) for k in reached), key=_unit),
                              "moves_anchoring": moves})
    return {"state": st, "theta": float(theta), "questions": questions,
            "possible_hosts": _possible_hosts(inp, corr, st, units, theta), "units": [_key(k) for k in units]}


def _possible_hosts(inp: px.Inputs, corr: dict, st: str, units, theta: float) -> list[str]:
    """Units whose upper bound of load reaches theta x base in some panel year in either reading (brief 4.5).

    The bound is the conservative joint check's, widened outward as that check widens it. No positive base: never a
    host, as assignment.evaluate reads it. A bound that is not a finite number: a possible host.
    """
    bounds = px.joint_check(inp, corr, st, theta)["bounds"]
    out = []
    for k in units:
        base_k = inp.base.get(k, np.nan)
        if not (pd.notna(base_k) and base_k > 0):
            continue
        possible = k not in bounds
        for reading in px.READINGS:
            if possible:
                break
            hi = np.asarray(bounds[k][reading][1], dtype=float)
            hi_e = hi + (px.BOUND_EPS_ABS + px.BOUND_EPS_REL * np.abs(hi))
            possible = bool((~np.isfinite(hi_e)).any() or (hi_e >= theta * float(base_k)).any())
        if possible:
            out.append(_key(k))
    return out


def dependency_table(inp: px.Inputs, corr: dict, states, theta: float = px.THETA) -> dict:
    """Every named state's table. A state whose table cannot be built is recorded as refused and is not covered."""
    out = {"states": {}, "refused": {}}
    for st in sorted(set(states)):
        try:
            out["states"][st] = state_dependencies(inp, corr, st, theta)
        except Exception as e:  # noqa: BLE001  any refusal means the state is not covered; the reason is kept in words
            out["refused"][st] = f"{type(e).__name__}: {e}"
    return out


# ---- the screen ----------------------------------------------------------------------------------------------------

def _check_mask(mask: pd.DataFrame) -> None:
    missing = [c for c in MASK_COLUMNS if c not in mask.columns]
    if missing:
        raise ValueError(f"the mask has no column {', '.join(missing)}")
    if mask[list(MASK_COLUMNS)].isna().any().any():
        raise ValueError("the mask has a missing value in a key column or in `usable`: nothing is screened on it")
    if mask.duplicated(["utility_id_eia", "state", "year"]).any():
        raise ValueError("the mask has two rows for one utility, state and year: nothing is screened on it")


def _check_identity(mask_identity: dict) -> dict:
    bad = [f for f in MASK_IDENTITY_FIELDS if not (isinstance(mask_identity.get(f), str) and mask_identity.get(f))]
    if bad:
        raise ValueError(f"the mask is not identified: {', '.join(bad)} missing. Nothing is screened on an unidentified mask")
    return {f: mask_identity[f] for f in MASK_IDENTITY_FIELDS}


def _units(xs) -> set:
    return {(int(u), s) for u, s in xs}


def _covered(table: dict, covered_states) -> set:
    return {st for st in set(covered_states) if st in table["states"] and st not in table["refused"]}


def fingerprints(mask: pd.DataFrame, mask_identity: dict, pool, hosts, table: dict, covered_states, corrections,
                 windows: dict | None = None) -> dict:
    """The five things a screen rests on, each as one hash (brief 4.8)."""
    _check_mask(mask)
    windows = windows or avail.permitted_windows()
    covered = sorted(_covered(table, covered_states))
    st = table["states"]
    candidates = [[s, q["question_id"], q["settings"]] for s in covered for q in st[s]["questions"]]
    dependencies = [[s, [[q["question_id"], q["utilities"], q["moves_anchoring"]] for q in st[s]["questions"]],
                     sorted(st[s]["possible_hosts"]), sorted(st[s]["units"])] for s in covered]
    rows = avail.screen_fingerprint(mask, {})                      # the mask's rows alone; the windows are hashed below
    return {
        "corrections": _sha(corrections),
        "candidates": _sha(candidates),
        "dependencies": _sha([dependencies, sorted(table["refused"].items())]),
        "mask_identity": _sha([_check_identity(mask_identity), rows]),
        "eligibility_rules": _sha({"windows": {k: list(v) for k, v in windows.items()}, "rule_version": RULE_VERSION,
                                   # The host threshold each covered state's table was built at. A table written
                                   # in the brief's shape, without it, hashes as "None".
                                   "theta": sorted({repr(st[s].get("theta")) for s in covered}),
                                   "pool": sorted(_key(k) for k in _units(pool)),
                                   "hosts": sorted(_key(k) for k in _units(hosts)),
                                   "covered_states": sorted(set(covered_states))}),
    }


def screen(mask: pd.DataFrame, mask_identity: dict, pool, hosts, table: dict, covered_states, corrections,
           windows: dict | None = None) -> dict:
    """Which questions may be deferred on this mask, which are retained and why, and the record to recheck later.

    Decides nothing about hosts: a listed host or a possible host is never narrowed, whatever its flags.
    """
    _check_mask(mask)
    windows = windows or avail.permitted_windows()
    usable = avail.usable_set(mask)
    pool, hosts = _units(pool), _units(hosts)
    covered = _covered(table, covered_states)
    st = table["states"]
    possible = {_unit(k) for s in st for k in st[s]["possible_hosts"]}
    in_table = {_unit(k) for s in st for k in st[s]["units"]}

    # Who is protected is settled before any flag is looked at.
    protected = {k: "a listed host" for k in hosts}
    protected.update({k: "a possible host" for k in possible if k not in protected})

    narrowed, why_not = set(), {}
    for k in sorted(pool):
        if k in protected:
            continue
        if k[1] not in covered:
            why_not[k] = "its state is outside the attribution's coverage, so it cannot be shown not to be a possible host"
        elif k not in in_table:
            why_not[k] = "not a panel unit of its state's table"
        else:
            passes = [name for name, w in windows.items() if avail.eligible(usable, k, w)]
            if passes:
                why_not[k] = "passes " + ", ".join(passes)
            else:
                narrowed.add(k)

    def why(k) -> str:
        if k in protected:
            return f"{_key(k)} ({protected[k]})"
        if k not in pool:
            return f"{_key(k)} (not in the pool)"
        return f"{_key(k)} ({why_not[k]})"

    deferrable, retained, generic = [], {}, []
    for s in sorted(st):
        for q in st[s]["questions"]:
            qid, moves = q["question_id"], q["moves_anchoring"]
            reached = [_unit(k) for k in q["utilities"]]
            if s not in covered:
                retained[qid] = OUTSIDE
                continue
            generic.append({"question_id": qid, "utilities": reached, "moves_anchoring": moves})
            if moves is None or not isinstance(moves, bool):
                retained[qid] = UNKNOWN
            elif moves:
                retained[qid] = MOVES
            elif not reached:
                retained[qid] = NO_UTILITY
            elif any(k not in narrowed for k in reached):
                retained[qid] = NOT_NARROWED + "; ".join(why(k) for k in reached if k not in narrowed)
            else:
                deferrable.append(qid)

    # The receiving end decides the same thing from the generic list. The two must agree, or nothing is returned.
    back = avail.retirable_questions(generic, narrowed)
    if sorted(back["retirable"]) != sorted(deferrable):
        raise AssertionError("the adapter and availability.retirable_questions disagree on what may be deferred")

    return {"rule_version": RULE_VERSION,
            "narrowed": sorted((_key(k) for k in narrowed), key=_unit),
            "protected": {_key(k): v for k, v in sorted(protected.items())},
            "not_narrowed": {_key(k): v for k, v in sorted(why_not.items())},
            "deferrable": sorted(deferrable), "retained": dict(sorted(retained.items())),
            "refused_states": dict(sorted(table["refused"].items())),
            "fingerprints": fingerprints(mask, mask_identity, pool, hosts, table, covered_states, corrections, windows)}


def reopen_reasons(record: dict, mask: pd.DataFrame, mask_identity: dict, pool, hosts, table: dict, covered_states,
                   corrections, windows: dict | None = None) -> list[str]:
    """[] if the screen still stands. Otherwise the fingerprints that differ: the whole screen is void and every
    question it deferred is open again until a new screen is made (brief 4.8). There is no partial reopening."""
    now = fingerprints(mask, mask_identity, pool, hosts, table, covered_states, corrections, windows)
    then = record.get("fingerprints", {})
    return [name for name in FINGERPRINTS if then.get(name) != now[name]]
