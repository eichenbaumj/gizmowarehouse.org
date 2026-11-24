#!/usr/bin/env python3
"""The exact attribution of the verification pass (docs/gate1/exact-attribution-brief-2026-11-16.md, written before
this code; D-65 item 4 as Joe ruled it; D-66 section 4 for the session's readings).

Load and sales only. Nothing here reads a price or revenue column, opens data/blind, or imports the price code. Nothing
is written under data/.

What it decides
---------------
The conservative joint check (`pass_c_expand.joint_check`, D-63 rule 7) keeps every open question that could change
any threshold status of a utility in any year, which over-includes. This keeps a question for a utility if and only
if two feasible configurations that differ only in that question give the utility a different OUTCOME:

  with a defined reference (place_ref, crossing_ref), under the criterion "either_reading" (the default; D-72 item 4,
      rule R7 of docs/gate1/reference-repair-rule-2026-11-18.md): the triple (place as built, place with no anchoring,
      accepted). Under the criterion "as_built", kept as a named alternative so a rerun can show which moves come from
      the reference and which from the criterion: D-66 4.1's pair (place as built, accepted). Accepted is the place being
      the reference's and, for a cohort reference, both first crossings (as built; with no anchoring) within one year of
      the reference's; for an early reference, the crossing with no anchoring also early; for a comparison reference,
      the largest share with no anchoring strictly under 0.5%. The place of a reading is the group of its first crossing,
      or "comparison" (largest share under 0.5%) or "neither" where there is none;
  with an undefined reference, under either criterion: (crossing as built, crossing with no anchoring, largest share as
      built < 0.5%, the same with no anchoring).

Everything is per state, and the questions, settings and loads are exactly `pass_c_expand._sites`'s, with the state's
factor `_factor(EPRI, measured total, permit total)` over the configuration's 2024 contributions, snapped to the frozen
factor within FACTOR_TOL as `scratch_state` does.

How, per utility k (brief section 5)
------------------------------------
  * The factor matters to k if the state's factor can move (the conservative range has high > low) and k carries
    permit-based load in some configuration.
  * Two settings of a question are merged for k if, for every setting of the same site's other questions, they put the
    same load on k in every panel year and (where the factor matters to k) count the same in the 2024 anchoring. This is
    exact: a site's load on another utility reaches k only through the anchoring.
  * A question is relevant to k if it has more than one merged setting. The count is the product of the numbers of
    merged settings of k's relevant questions (a Python integer however large).
  * The reference is fixed first (`reference_of`, rules R1 to R4 of the reference repair, D-72 item 4): every assignment
    as mapped, every date and capacity question at its convention. The reference-defining questions (here: no
    convention, or a date whose convention is provisional) that are relevant to k are enumerated at EVERY one of their
    merged classes for k (one representative each), in every combination; the reference is defined if and only if k's
    place and first crossing as built are the same in all of them (R2; R3 is the proof that the representatives lose
    nothing). Agreement at the two ends, or at the corners, decides nothing. Over the ceiling of combinations: undefined
    without the search, and the record says so with the count (R4). The place test in pass_c_expand.run_state takes its
    reference from the same function, with its own list (no convention only; it does not read the provisional mark).
    That narrower reference is a conditional diagnostic and no more (Joe, D-90): it holds only if every provisional
    convention is the site's start, it cannot override an undefined reference here, and neither it nor the place test's
    "keeps its place" is by itself a ground for eligibility or for pruning. The driver marks every place-test row against
    this run's reference and names, in the JSON's counts, the CSV's last column and the printed summary, each utility for
    which the place test shows a reference where this one is undefined.
  * At or under the ceiling every configuration of the relevant questions is evaluated at once (numpy, one array per
    reading, configurations x years), the other questions at the reference configuration's settings (a reference-
    defining question with no convention that is not relevant to k at its first setting, which by irrelevance changes
    nothing for k). A question is kept if its outcome varies along its axis for some setting of the others; a witness
    pair is recorded for each kept question.
  * Over the ceiling, or where a measured site that can be on k has an uncertain no-anchoring divisor, k keeps the
    conservative check's kept questions, marked "conservative", with the count and the reason.

What it does not test (Joe, D-90, 2026-11-18): eligibility as a future-host comparison
------------------------------------------------------------------------------------
The outcome above has no term for the future-host comparison group of the side run (D-29; D-86 list 1, item 11: a
utility that first crosses in 2023 or later, for a cohort through whose last window year it is under 0.5% and more than
three years short of its own crossing). Two configurations can give the same outcome here and differ in that
eligibility, for example a first crossing that moves inside the late group, or the year a share first reaches 0.5%. So a
question this attribution does not keep is NOT thereby shown to be irrelevant to a potential future-host comparison.
The criterion is not implemented as an outcome of the attribution, here or in pass_c_expand.py, and nothing is built for
it. Until it is implemented and tested on invented inputs, the unresolved questions that bear on it are retained: no
question is dropped, closed or deferred on this attribution's result where it could bear on that eligibility.

Rounding. The vectorised load is 8.76 x (measured MW on k + factor x the sum of permit-based raw MW on k); the scratch
rebuild scales each site before summing and keeps a non-rebuilt site's frozen rows (reproduced to 1e-9 MW). Totals can
therefore differ in the last bits, which matters only for a load within about one part in 1e9 of a threshold.

Run:
  python3 -I pipeline/facilities/pass_c_exact.py CORRECTIONS.json --targets pipeline/facilities/verified/pass_c_targets.csv \\
      --out docs/gate1/<name>.json --csv pipeline/facilities/verified/pass_c_exact_attribution.csv [--also-states AR,CA] \\
      [--criterion either_reading|as_built]
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

CEILING = 100_000
CRITERIA = ("either_reading", "as_built")    # R7's triple (the default), and D-66 4.1's pair kept as a named alternative
THETA = px.THETA
YEARS = px.YEARS
NY = len(YEARS)
NEVER = NY                                   # the crossing index meaning "no crossing"
GWH_PER_MW = 8.76
PLACES = ("early", "cohort", "late", "comparison", "neither")
HOSTS_EXPECTED = 26
HEADLINE = ROOT / "data" / "frozen" / "headline_set.csv"
# The group of a crossing index: 0 early, 1 cohort, 2 late, 3 no crossing.
_GROUP = np.array([0 if y < asg.COHORTS[0] else 1 if y <= asg.COHORTS[1] else 2 for y in YEARS] + [3])
CSV_COLUMNS = ["utility", "utility_name", "one_of_the_26_hosts", "method", "configurations", "complete",
               "reference_defined", "reference_place", "reference_crossing", "site", "question", "site_state",
               "site_is_on", "operator", "county", "mw_full", "already_on_the_target_list", "witness",
               # Added by the reference repair (D-72 item 4), after the old columns so that no existing reader trips:
               "reference_settings_enumerated", "reference_searched", "reference_why_undefined", "criterion",
               # Added under D-90, last: words where the place test shows a reference for the row's utility and the
               # reference in this file is undefined; empty otherwise. The place test's reference is in no other column.
               "place_test_reference_note"]


# ---- one state, prepared once ------------------------------------------------------------------------------------

@dataclass
class _Q:
    si: int                  # the site's position in the state's list
    qi: int                  # the question's column in the site's idx
    fid: str
    name: str                # "assignment" | "date" | "capacity"
    values: list
    default: int             # the setting index used where the question is not enumerated
    no_convention: bool      # a date or capacity question the corrected inventory has no setting for
    provisional: bool        # a date whose convention is provisional (the inventory's year-built rows, D-66 4.3)

    @property
    def ref_defining(self) -> bool:
        """Reference-defining for the exact attribution: no convention, or a provisional date (reference repair, 3)."""
        return self.no_convention or self.provisional


def _index_of_year(values: list, v) -> int:
    """A date's convention (a year or "never") as an index of its settings, clamped to the first or last year."""
    if v == "never":
        return values.index("never")
    years = [x for x in values if x != "never"]
    if v <= years[0]:
        return 0
    if v >= years[-1]:
        return len(years) - 1
    return years.index(int(v))


def _default(c, name: str, values: list) -> tuple[int, bool, bool]:
    """(the reference configuration's setting index, no convention, a provisional date convention).

    A question with no convention has no setting in the reference configuration; where it is not enumerated it sits at
    its first setting (which, where it is not relevant to the utility in hand, changes nothing for that utility)."""
    if name == "assignment":
        return 0, False, False                                            # values[0] is the utility the site is on
    conv = c.convention(name)
    if name == "date":
        provisional = c.date.get("convention_is") == "provisional"
        if conv is None:
            return 0, True, False
        return _index_of_year(values, c.start(conv)), False, provisional
    if conv is None:
        return 0, True, False
    return (0 if conv == px.EARLY else len(values) - 1), False, False    # the rest with the first phase, or at the inventory year


def _value(v):
    """A setting as it is written out: a utility id, "off_panel", a year, "never", "early" or "late"."""
    if v is None:
        return px.OFF
    if isinstance(v, (int, np.integer)):
        return int(v)
    return str(v)


class _State:
    def __init__(self, inp: px.Inputs, corr: dict, st: str):
        units = inp.units[inp.units.get_level_values("state") == st]
        self.st = st
        self.units = [(int(u), s) for u, s in units]
        self.sites, self.no_load, self.removed = px._sites(inp, corr, st, units)
        self.fr = px._factor_range(inp, st, self.sites, self.removed)
        self.factor_can_move = bool(self.fr["high"] > self.fr["low"])
        self.epri = float(inp.anchor.epri_twh.get(st, 0.0)) if "epri_twh" in inp.anchor else 0.0
        self.m0 = float(inp.measured_fixed.get(st, 0.0)) - self.removed
        self.frozen = inp.frozen_factor(st)
        self.qs: list[_Q] = []
        self.site_qids: list[list[int]] = []
        self.default, self.lookup, ref_rows = [], [], []
        for si, s in enumerate(self.sites):
            c = corr.get(s.fid)
            d, ids = [], []
            for qi, name in enumerate(s.questions):
                dflt, loose, prov = _default(c, name, list(s.values[qi]))
                ids.append(len(self.qs))
                self.qs.append(_Q(si, qi, s.fid, name, list(s.values[qi]), dflt, loose, prov))
                d.append(dflt)
            self.site_qids.append(ids)
            self.default.append(tuple(d))
            lk = {tuple(int(x) for x in row): r for r, row in enumerate(s.idx)}
            if len(lk) != len(s.idx):
                raise ValueError(f"{s.fid}: two rows of its settings have the same indices")
            self.lookup.append(lk)
            ref_rows.append(lk[tuple(d)])
        n = len(self.sites)
        self.permit = np.array([s.kind == "permit" for s in self.sites], dtype=bool)
        self.L_ref = np.vstack([s.load[r] for s, r in zip(self.sites, ref_rows)]) if n else np.zeros((0, NY))
        self.a_ref = np.array([float(s.a[r]) for s, r in zip(self.sites, ref_rows)])
        self.unit_ref = [s.unit[r] for s, r in zip(self.sites, ref_rows)]
        self.div = np.array([float(s.na_div[0]) for s in self.sites])
        self.units_of = [{u for u in s.unit if u is not None} for s in self.sites]
        self._a_classes: dict[int, list] = {}
        self._relevance: dict[tuple, tuple] = {}

    # -- the reference-defining questions (reference repair, section 3) ----------------------------------------------
    def defining(self, which: str) -> list[int]:
        """The question ids that define a reference: "exact" (no convention, or a provisional date) or "place_test" (no
        convention only: the place test has never read the provisional mark)."""
        if which == "exact":
            return [i for i, q in enumerate(self.qs) if q.ref_defining]
        if which == "place_test":
            return [i for i, q in enumerate(self.qs) if q.no_convention]
        raise ValueError(f"reference-defining questions are listed for 'exact' or 'place_test', not {which!r}")

    # -- relevance, per utility (brief section 5) ----------------------------------------------------------------------
    def relevance(self, k: tuple) -> tuple[bool, list]:
        """(whether the factor matters to k, [(question id, merged classes)] for every question relevant to k)."""
        if k in self._relevance:
            return self._relevance[k]
        carries_permit = False
        for si in range(len(self.sites)):
            s = self.sites[si]
            if k in self.units_of[si] and s.kind == "permit":
                on = np.array([u == k for u in s.unit], dtype=bool)
                if (s.load[on] > 0).any():
                    carries_permit = True
                    break
        factor_matters = self.factor_can_move and carries_permit
        rel = []
        for qid in range(len(self.qs)):
            cl = self.classes(qid, k, factor_matters)
            if len(cl) > 1:
                rel.append((qid, cl))
        self._relevance[k] = (factor_matters, rel)
        return self._relevance[k]

    # -- merging ------------------------------------------------------------------------------------------------
    def _group(self, q: _Q, key_of_rows) -> list[list[int]]:
        s = self.sites[q.si]
        others = np.delete(s.idx, q.qi, axis=1)
        classes: dict[bytes, list[int]] = {}
        for j in range(len(q.values)):
            rows = np.flatnonzero(s.idx[:, q.qi] == j)
            if others.shape[1]:
                rows = rows[np.lexsort(others[rows].T[::-1])]
            classes.setdefault(key_of_rows(rows), []).append(j)
        return list(classes.values())

    def classes(self, qid: int, k: tuple, factor_matters: bool) -> list[list[int]]:
        """The question's settings merged for utility k (brief section 5), each class a list of setting indices."""
        q = self.qs[qid]
        s = self.sites[q.si]
        if len(q.values) == 1:
            return [[0]]
        if k not in self.units_of[q.si]:
            if not factor_matters:
                return [list(range(len(q.values)))]
            if qid not in self._a_classes:
                a = s.a + 0.0
                self._a_classes[qid] = self._group(q, lambda rows: a[rows].tobytes())
            return self._a_classes[qid]
        on = np.array([u == k for u in s.unit], dtype=bool)
        load_k = s.load * on[:, None] + 0.0
        a = s.a + 0.0
        if factor_matters:
            return self._group(q, lambda rows: load_k[rows].tobytes() + b"|" + a[rows].tobytes())
        return self._group(q, lambda rows: load_k[rows].tobytes())

    # -- evaluation ---------------------------------------------------------------------------------------------
    def grid(self, k: tuple, axes: list[tuple[int, list[int]]]):
        """Utility k's GWh by year, as built and with no anchoring, over every combination of the axes.

        axes: (question id, [setting indices]) in the order of self.qs; every other question at its default setting.
        Returns (as built, no anchoring), each of shape (configurations, years) in C order over the axes, and the shape.
        """
        shape = tuple(len(sel) for _, sel in axes) or (1,)
        nd = len(shape)
        by_site: dict[int, list] = {}
        for pos, (qid, sel) in enumerate(axes):
            by_site.setdefault(self.qs[qid].si, []).append((pos, qid, sel))
        n = len(self.sites)
        fixed = np.ones(n, dtype=bool)
        fixed[list(by_site)] = False
        onk = np.array([u == k for u in self.unit_ref], dtype=bool) if n else np.zeros(0, dtype=bool)
        sel_p, sel_m = fixed & onk & self.permit, fixed & onk & ~self.permit
        R = np.zeros(shape + (NY,)) + self.L_ref[sel_p].sum(axis=0)
        Mm = np.zeros(shape + (NY,)) + self.L_ref[sel_m].sum(axis=0)
        Mna = np.zeros(shape + (NY,)) + (self.L_ref[sel_m] / self.div[sel_m][:, None]).sum(axis=0)
        P = np.zeros(shape) + float(self.a_ref[fixed & self.permit].sum())
        M = np.zeros(shape) + self.m0 + float(self.a_ref[fixed & ~self.permit].sum())
        for si, items in by_site.items():
            s = self.sites[si]
            sub = [len(sel) for _, _, sel in items]
            L = np.zeros(sub + [NY])
            A = np.zeros(sub)
            for combo in itertools.product(*[range(m) for m in sub]):
                idx = list(self.default[si])
                for (_, qid, sel), ci in zip(items, combo):
                    idx[self.qs[qid].qi] = sel[ci]
                row = self.lookup[si][tuple(idx)]
                if s.unit[row] == k:
                    L[combo] = s.load[row]
                A[combo] = s.a[row]
            full = [1] * nd
            for (pos, _, _), m in zip(items, sub):
                full[pos] = m
            Lb, Ab = L.reshape(full + [NY]), A.reshape(full)
            if s.kind == "permit":
                R = R + Lb
                P = P + Ab
            else:
                Mm = Mm + Lb
                Mna = Mna + Lb / float(s.na_div[0])
                M = M + Ab
        F = self.factor(M, P)
        ab = GWH_PER_MW * (Mm + F[..., None] * R)
        na = GWH_PER_MW * (Mna + R)
        return ab.reshape(-1, NY), na.reshape(-1, NY), shape

    def factor(self, M: np.ndarray, P: np.ndarray) -> np.ndarray:
        """pass_c_expand._factor, elementwise, with scratch_state's snapping to the frozen factor."""
        with np.errstate(divide="ignore", invalid="ignore"):
            raw = np.maximum(self.epri - M, 0.0) / np.where(P != 0, P, 1.0)
        f = np.where(P != 0, np.minimum(np.maximum(raw, px.SCALE_LO), px.SCALE_HI), 1.0)
        snap = np.abs(f - self.frozen) <= px.FACTOR_TOL * max(1.0, abs(self.frozen))
        return np.where(snap, self.frozen, f)


# ---- outcomes ------------------------------------------------------------------------------------------------------

def _readings(v: np.ndarray, base_k: float, theta: float):
    """(first crossing index, NEVER if none; largest share strictly under the floor; the largest share)."""
    pos = bool(pd.notna(base_k) and base_k > 0)
    top = v.max(axis=1)
    if pos:
        hit = v >= theta * base_k
        c = np.where(hit.any(axis=1), hit.argmax(axis=1), NEVER)
        share = np.where(top > 0, top / base_k, 0.0)
    else:                                                                 # no positive base: no crossing, any load is infinite
        c = np.full(len(v), NEVER)
        share = np.where(top > 0, np.inf, 0.0)
    return c.astype(int), share < asg.CLEAN_BELOW, share


def _place_codes(c: np.ndarray, under: np.ndarray) -> np.ndarray:
    g = _GROUP[c]
    return np.where(g < 3, g, np.where(under, 3, 4))


def _check_criterion(criterion: str) -> str:
    if criterion not in CRITERIA:
        raise ValueError(f"the criterion is one of {', '.join(CRITERIA)}, not {criterion!r}")
    return criterion


def _outcomes(ab, na, base_k, theta, ref, criterion: str = "either_reading"):
    """One integer per configuration, equal exactly when the outcomes are equal, and the parts for writing out.

    With a defined reference: R7's triple (place as built, place with no anchoring, accepted) under "either_reading",
    D-66 4.1's pair (place as built, accepted) under "as_built". With none: the four values, under either criterion."""
    _check_criterion(criterion)
    c_ab, u_ab, s_ab = _readings(ab, base_k, theta)
    c_na, u_na, s_na = _readings(na, base_k, theta)
    p_ab = _place_codes(c_ab, u_ab)
    p_na = _place_codes(c_na, u_na)
    parts = {"c_ab": c_ab, "c_na": c_na, "u_ab": u_ab, "u_na": u_na, "s_ab": s_ab, "s_na": s_na, "p_ab": p_ab, "p_na": p_na}
    if ref is None:
        code = ((c_ab * (NY + 1) + c_na) * 2 + u_ab) * 2 + u_na
        return code, parts
    p_ref, c_ref = ref
    acc = p_ab == p_ref
    if PLACES[p_ref] == "cohort":
        acc &= ((_GROUP[c_ab] == 1) & (np.abs(c_ab - c_ref) < asg.MOVE_TOLERANCE)
                & (_GROUP[c_na] == 1) & (np.abs(c_na - c_ref) < asg.MOVE_TOLERANCE))
    elif PLACES[p_ref] == "early":
        acc &= _GROUP[c_na] == 0
    elif PLACES[p_ref] == "comparison":
        acc &= u_na
    parts["acc"] = acc
    if criterion == "as_built":
        return p_ab * 2 + acc, parts
    return (p_ab * len(PLACES) + p_na) * 2 + acc, parts


def _year(c: int) -> str:
    return "never" if c == NEVER else str(YEARS[c])


def _share(x: float):
    return "infinite" if np.isinf(x) else float(x)


def _outcome_dict(parts: dict, i: int, ref, criterion: str = "either_reading") -> tuple[dict, dict]:
    detail = {"place_as_built": PLACES[int(parts["p_ab"][i])], "place_no_anchoring": PLACES[int(parts["p_na"][i])],
              "crossing_as_built": _year(int(parts["c_ab"][i])), "crossing_no_anchoring": _year(int(parts["c_na"][i])),
              "largest_share_as_built": _share(parts["s_ab"][i]), "largest_share_no_anchoring": _share(parts["s_na"][i])}
    if ref is None:
        return ({"crossing_as_built": detail["crossing_as_built"], "crossing_no_anchoring": detail["crossing_no_anchoring"],
                 "under_floor_as_built": bool(parts["u_ab"][i]), "under_floor_no_anchoring": bool(parts["u_na"][i])}, detail)
    if criterion == "as_built":
        return {"place": detail["place_as_built"], "accepted": bool(parts["acc"][i])}, detail
    return {"place": detail["place_as_built"], "place_no_anchoring": detail["place_no_anchoring"],
            "accepted": bool(parts["acc"][i])}, detail


# ---- one utility ---------------------------------------------------------------------------------------------------

def _qref(q: _Q) -> dict:
    return {"fid": q.fid, "question": q.name}


def _names(qs: list) -> str:
    return ", ".join(f"{q.fid} {q.name}" for q in qs)


def reference_of(S: _State, k: tuple, base_k: float, theta: float, defining: list[int],
                 ceiling: int = CEILING) -> tuple[dict, tuple | None]:
    """Utility k's reference under rules R2 to R4 of the reference repair (docs/gate1/reference-repair-rule-2026-11-18.md;
    D-72 item 4), for a given list of reference-defining question ids. The one function both the exact attribution
    (S.defining("exact")) and the place test (S.defining("place_test")) take a reference from (R6).

    R2: defined if and only if k's place as built and first crossing as built are the same at every admissible reference
        setting, every other question at the reference configuration; it is then that place and crossing.
    R3: the enumeration is over the listed questions that are relevant to k, at one representative of each of their
        classes merged for k (brief section 5); the rule file proves this loses nothing. No other reduction: not the ends,
        not the corners, no monotonicity.
    R4: more than `ceiling` combinations: undefined without the search, said in words with the count.

    Returns (the record, (place code, crossing index) or None). The record: defined, place, crossing ("2015" | "never"),
    why_undefined (words), undefined_by ([{fid, question}], the questions some two settings of which, everything else
    equal, give different places or crossings; every listed question when not searched), settings_enumerated (the number
    of combinations under R3, a Python integer however large), searched (false only under R4), and pair (where searched
    and undefined: one such question and two settings of it, with every enumerated question's value, as
    {"fid", "question", "a": {"settings": {"<fid> <question>": value}, "place", "crossing"}, "b": {...}}; realise() takes
    either side's settings as they are).
    """
    _, rel = S.relevance(k)
    listed = set(defining)
    axes_cl = [(qid, cl) for qid, cl in rel if qid in listed]
    qs = [S.qs[qid] for qid, _ in axes_cl]
    n = math.prod(len(cl) for _, cl in axes_cl)
    rec = {"defined": False, "place": None, "crossing": None, "why_undefined": None, "undefined_by": [],
           "settings_enumerated": int(n), "searched": False, "pair": None}
    if n > ceiling:
        rec.update(why_undefined=(f"not searched: {n} combinations of the settings of the reference-defining questions "
                                  f"relevant to this utility ({_names(qs)}), over the ceiling of {ceiling}; the reference "
                                  f"is undefined without the search"),
                   undefined_by=[_qref(q) for q in qs])
        return rec, None
    rec["searched"] = True
    axes = [(qid, [g[0] for g in cl]) for qid, cl in axes_cl]
    ab, _, shape = S.grid(k, axes)
    c_ab, u_ab, _ = _readings(ab, base_k, theta)
    p_ab = _place_codes(c_ab, u_ab)
    pc = (p_ab * (NY + 1) + c_ab).reshape(shape)
    if (pc == pc.flat[0]).all():
        rec.update(defined=True, place=PLACES[int(p_ab[0])], crossing=_year(int(c_ab[0])))
        return rec, (int(p_ab[0]), int(c_ab[0]))
    diffs = [(pos, pc != np.take(pc, [0], axis=pos)) for pos in range(len(axes))]
    by = [(pos, d) for pos, d in diffs if d.any()]
    pos, d = by[0]
    b = tuple(int(x) for x in np.unravel_index(int(np.flatnonzero(d)[0]), shape))
    a = list(b)
    a[pos] = 0
    sides = {}
    for side, at in (("a", tuple(a)), ("b", b)):
        i = int(np.ravel_multi_index(at, shape))
        sides[side] = {"settings": {f"{S.qs[q].fid} {S.qs[q].name}": _value(S.qs[q].values[sel[at[p]]])
                                    for p, (q, sel) in enumerate(axes)},
                       "place": PLACES[int(p_ab[i])], "crossing": _year(int(c_ab[i]))}
    q = qs[pos]
    name = f"{q.fid} {q.name}"
    va, vb = sides["a"]["settings"][name], sides["b"]["settings"][name]
    rec.update(undefined_by=[_qref(qs[p]) for p, _ in by], pair={**_qref(q), **sides},
               why_undefined=(f"the place or the first crossing as built is not the same at every admissible reference "
                              f"setting ({n} combinations of {len(qs)} reference-defining questions relevant to this "
                              f"utility, every setting of each, one per class of settings merged for it); it turns on "
                              f"{_names([qs[p] for p, _ in by])}. For example, {name} at {va} gives "
                              f"{sides['a']['place']} {sides['a']['crossing']} and at {vb} gives {sides['b']['place']} "
                              f"{sides['b']['crossing']}, every other enumerated question as in the pair"))
    return rec, None


def _attribute(S: _State, k: tuple, base_k: float, theta: float, ceiling: int, jc_u: dict,
               criterion: str = "either_reading") -> dict:
    on_sites = [si for si in range(len(S.sites)) if k in S.units_of[si]]
    bad_div = sorted(S.sites[si].fid for si in on_sites
                     if S.sites[si].kind == "measured" and S.sites[si].na_div[0] != S.sites[si].na_div[1])
    factor_matters, rel = S.relevance(k)
    count = 1
    for _, cl in rel:
        count *= len(cl)

    # ---- the reference (reference repair, rules R2 to R4; one function with the place test, R6) ----
    reference, ref_codes = reference_of(S, k, base_k, theta, S.defining("exact"), ceiling)

    relevant = [{**_qref(S.qs[qid]), "settings": len(cl),
                 "merged_settings": [[_value(S.qs[qid].values[j]) for j in g] for g in cl]} for qid, cl in rel]
    out = {"method": "exact", "why_conservative": None, "configurations": count, "complete": False,
           "reference": reference, "relevant_questions": relevant, "kept_questions": [], "joins": [],
           "factor_matters": bool(factor_matters)}
    why = None
    if bad_div:
        why = (f"a measured site that can be on this utility has a no-anchoring divisor that is not one number "
               f"({', '.join(bad_div)}); the brief sends such a utility to the conservative rule")
    elif count > ceiling:
        why = f"{count} configurations, over the ceiling of {ceiling}"
    if why:
        out.update(method="conservative", why_conservative=why,
                   kept_questions=[dict(q) for q in jc_u["kept_questions"]], joins=list(jc_u["joins"]))
        return out

    # ---- every configuration of the relevant questions (brief section 5) ----
    axes = [(qid, [g[0] for g in cl]) for qid, cl in rel]
    ab, na, shape = S.grid(k, axes)
    code, parts = _outcomes(ab, na, base_k, theta, ref_codes, criterion)
    O = code.reshape(shape)
    kept = []
    for pos, (qid, sel) in enumerate(axes):
        diff = O != np.take(O, [0], axis=pos)
        if not diff.any():
            continue
        b = np.unravel_index(int(np.flatnonzero(diff)[0]), shape)
        a = list(b)
        a[pos] = 0
        sides = {}
        for side, at in (("a", tuple(a)), ("b", tuple(int(x) for x in b))):
            i = int(np.ravel_multi_index(at, shape))
            settings = {f"{S.qs[q].fid} {S.qs[q].name}": _value(S.qs[q].values[s_[at[p]]]) for p, (q, s_) in enumerate(axes)}
            o, detail = _outcome_dict(parts, i, ref_codes, criterion)
            sides[side] = {"settings": settings, "outcome": o, "detail": detail}
        kept.append({**_qref(S.qs[qid]), "witness": sides})
    out.update(complete=True, kept_questions=kept, joins=sorted({q["fid"] for q in kept}))
    return out


def exact_attribution(inp: px.Inputs, corr: dict, st: str, theta: float = THETA, ceiling: int = CEILING,
                      criterion: str = "either_reading") -> dict:
    """The exact attribution for every panel utility of one state (brief section 6; reference repair, R2 to R7).

    criterion: "either_reading" (R7's triple, the default) or "as_built" (D-66 4.1's pair, a named alternative)."""
    return _exact(inp, corr, st, theta, ceiling, criterion)[0]


def _exact(inp: px.Inputs, corr: dict, st: str, theta: float, ceiling: int,
           criterion: str = "either_reading") -> tuple[dict, dict]:
    """exact_attribution's result and the conservative joint check it was given, for the driver's comparison."""
    _check_criterion(criterion)
    S = _State(inp, corr, st)
    jc = px.joint_check(inp, corr, st, theta)
    res = {"state": st, "theta": theta, "ceiling": ceiling, "criterion": criterion, "factor_can_move": S.factor_can_move,
           "factor_range": {"low": float(S.fr["low"]), "high": float(S.fr["high"])},
           "questions": [dict(q) for q in jc["questions"]], "utilities": {}}
    for k in S.units:
        key = f"{k[0]}:{k[1]}"
        base_k = float(inp.base.get(k, np.nan))
        res["utilities"][key] = _attribute(S, k, base_k, theta, ceiling, jc["utilities"][key], criterion)
    return res, jc


# ---- the driver ----------------------------------------------------------------------------------------------------

def hosts_from_headline(head: pd.DataFrame) -> list[tuple[int, str]]:
    """The 26 hosts: rows at the 2% threshold in the headline set, or out of it for ruling 4's reasons only."""
    h = head[head.threshold == "2%"]
    sel = h[h.in_headline_set.astype(bool) | h.why_not_in_the_headline_set.apply(asg.only_ruling_4)]
    return sorted(((int(u), str(s)) for u, s in zip(sel.utility_id_eia, sel.state)), key=lambda k: (k[1], k[0]))


def _witness_ok(q: dict) -> bool:
    w = q.get("witness")
    if not w:
        return False
    a, b = w["a"]["settings"], w["b"]["settings"]
    return (set(a) == set(b) and [x for x in a if a[x] != b[x]] == [f"{q['fid']} {q['question']}"]
            and w["a"]["outcome"] != w["b"]["outcome"])


def realise(inp: px.Inputs, corr: dict, st: str, settings: dict) -> dict:
    """One configuration through the scratch rebuild and assignment.evaluate (not through this module's arithmetic).

    `settings` maps "<fid> <question>" to a value as a witness writes it. A date or capacity question left out takes its
    convention, or its first setting where it has none; an assignment left out stays as mapped. Returns the matrices.
    """
    import dataclasses
    corr = dict(corr)
    choice = {}
    for key, v in settings.items():
        fid, q = key.rsplit(" ", 1)
        if q == "assignment":
            to = px.OFF if v == px.OFF else (int(v), st)
            c = corr.get(fid) or px.Correction(fid=fid, state=st, inventory_year=inp.fac.energized_year[fid])
            corr[fid] = dataclasses.replace(c, assign=to, reopen=None, narrow=None, widen=None)
        else:
            choice[(fid, q)] = v
    for fid, c in corr.items():
        if c.state == st:
            for q in c.questions():
                if (fid, q) not in choice and c.convention(q) is None:
                    choice[(fid, q)] = (px._date_values(c) if q == "date" else px._capacity_values(c))[0]
    fac, fy, _ = px.scratch_state(inp, corr, st, choice)
    u = inp.units[inp.units.get_level_values("state") == st]
    _, m, _ = asg.evaluate(fac, fy, u, inp.base.reindex(u), inp.regions.reindex(u), thresholds=(px.THETA,))
    return m


def realised_outcome(m: dict, k: tuple, base_k: float, theta: float, reference: dict,
                     criterion: str = "either_reading") -> dict:
    """The brief's outcome from the rebuilt matrices, through pass_c_expand._row_outcome (scalar, not vectorised here).

    With a crossing at the host threshold the share is at least 2%, so "under the floor" is the place being comparison.
    With a defined reference: R7's triple under "either_reading", D-66 4.1's pair under "as_built".
    """
    _check_criterion(criterion)
    ab = m["as_built"].loc[k].values.astype(float)
    na = m["no_anchoring"].loc[k].values.astype(float)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)                  # a zero base: the share is infinite, as intended
        p, c, pn, cn = px._row_outcome(ab, na, base_k, theta)
    if not reference["defined"]:
        return {"crossing_as_built": _fmt_year(c), "crossing_no_anchoring": _fmt_year(cn),
                "under_floor_as_built": p == "comparison", "under_floor_no_anchoring": pn == "comparison"}
    rp = reference["place"]
    rc = np.nan if reference["crossing"] == "never" else float(reference["crossing"])
    acc = p == rp
    if acc and rp == "cohort":
        acc = asg.same_place(rc, c) and asg.same_place(rc, cn)
    elif acc and rp == "early":
        acc = asg.group(cn) == "early"
    elif acc and rp == "comparison":
        acc = pn == "comparison"
    if criterion == "as_built":
        return {"place": p, "accepted": bool(acc)}
    return {"place": p, "place_no_anchoring": pn, "accepted": bool(acc)}


def _fmt_year(y) -> str:
    return "never" if y is None or pd.isna(y) else str(int(y))


def run(corrections: list[dict], inp: px.Inputs, targets=None, states=None, hosts=None, theta: float = THETA,
        ceiling: int = CEILING, realise_witnesses: bool = False, criterion: str = "either_reading") -> dict:
    """Everything the CLI writes: the JSON, the CSV rows and the printed summary."""
    _check_criterion(criterion)
    t0 = time.time()
    expansion = px.expand(corrections, inputs=inp, theta=theta, targets=targets)
    t_expand = time.time() - t0
    corr = px.parse_corrections(corrections, inp)
    hosts = list(hosts or [])
    run_states = sorted({c.state for c in corr.values()} | set(states or []))
    listed = None
    if targets:
        t = pd.read_csv(targets)
        listed = set(t["site"].astype(str)) if "site" in t else set(t["fid"].astype(str))
    exact, conservative, timing = {}, {}, {}
    for st in run_states:
        t1 = time.time()
        exact[st], jc = _exact(inp, corr, st, theta, ceiling, criterion)
        conservative[st] = jc["utilities"]
        timing[st] = round(time.time() - t1, 2)

    # D-90: the place test's reference is a conditional diagnostic. Every place-test row is marked against the reference
    # of THIS run (at the default ceiling it is the record run_state already used; at another ceiling this run's governs),
    # and each utility for which the place test shows a reference where this one is undefined is named.
    shown_without = []
    for row in expansion["utilities"]:
        key = row["utility"]
        row.update(px.reference_diagnostic(isinstance(row["reference"], dict),
                                           exact[key.split(":")[1]]["utilities"][key]["reference"]))
        if row["reference_shown_where_exact_is_undefined"]:
            shown_without.append({"utility": key, "name": row["name"],
                                  "place_test_reference": f"{row['reference']['place']} {row['reference']['crossing']}",
                                  "place_test_keeps_its_place": row["keeps_its_place"], "warning": row["reference_warning"]})
    place_test_note = {x["utility"]: x["warning"] for x in shown_without}

    # As mapped, with the corrections applied: the utility each site is on in the reference configuration.
    fac = inp.fac.copy()
    measured = inp.measured.copy()
    for c in corr.values():
        px._apply_fields(fac, measured, c)
    off_kinds = [a for a in asg.VERIFIED if a != "verified_by_hand"]

    def site_is_on(fid):
        u = fac.utility_id_eia[fid]
        if pd.notna(u):
            return f"{int(u)}:{fac.state[fid]}"
        return "off_panel" if fac.utility_assign[fid] in off_kinds else "none"

    def text(x):
        return "" if x is None or (isinstance(x, float) and math.isnan(x)) else str(x)

    host_keys = {f"{u}:{s}" for u, s in hosts}
    rows, violations, n_wit, bad_wit, n_real, bad_real = [], [], 0, [], 0, []
    t2 = time.time()
    for st, r in exact.items():
        for key, u in r["utilities"].items():
            cons = {(q["fid"], q["question"]) for q in conservative[st][key]["kept_questions"]}
            if u["method"] == "exact":
                extra = {(q["fid"], q["question"]) for q in u["kept_questions"]} - cons
                violations += [{"utility": key, "fid": f, "question": q} for f, q in sorted(extra)]
                k = (int(key.split(":")[0]), st)
                for q in u["kept_questions"]:
                    n_wit += 1
                    if not _witness_ok(q):
                        bad_wit.append({"utility": key, "fid": q["fid"], "question": q["question"]})
                    if realise_witnesses:
                        for side in ("a", "b"):
                            got = realised_outcome(realise(inp, corr, st, q["witness"][side]["settings"]), k,
                                                   float(inp.base.get(k, np.nan)), theta, u["reference"], criterion)
                            n_real += 1
                            if got != q["witness"][side]["outcome"]:
                                bad_real.append({"utility": key, "fid": q["fid"], "question": q["question"], "side": side,
                                                 "realised": got, "recorded": q["witness"][side]["outcome"]})
            uid = int(key.split(":")[0])
            ref = u["reference"]
            for q in u["kept_questions"]:
                f = q["fid"]
                rows.append({"utility": key, "utility_name": text(inp.names.get((uid, st))),
                             "one_of_the_26_hosts": key in host_keys, "method": u["method"],
                             "configurations": u["configurations"], "complete": u["complete"],
                             "reference_defined": ref["defined"], "reference_place": text(ref["place"]),
                             "reference_crossing": text(ref["crossing"]), "site": f, "question": q["question"],
                             "site_state": text(inp.fac.state[f]), "site_is_on": site_is_on(f),
                             "operator": text(inp.fac.operator[f]) if "operator" in inp.fac else "",
                             "county": text(inp.fac.county_name[f]) if "county_name" in inp.fac else "",
                             "mw_full": text(inp.fac.mw_full[f]),
                             "already_on_the_target_list": (f in listed) if listed is not None else "",
                             "witness": json.dumps(q["witness"], separators=(",", ":")) if "witness" in q else "",
                             "reference_settings_enumerated": ref["settings_enumerated"],
                             "reference_searched": ref["searched"],
                             "reference_why_undefined": text(ref["why_undefined"]), "criterion": criterion,
                             "place_test_reference_note": place_test_note.get(key, "")})

    def sites_kept(keys, source):
        out = set()
        for st, r in exact.items():
            for key in r["utilities"]:
                if keys is None or key in keys:
                    out |= set(source(st, key))
        return out

    def not_listed(s):
        return None if listed is None else len({f for f in s if f not in listed})

    ex_h = sites_kept(host_keys, lambda st, key: exact[st]["utilities"][key]["joins"])
    co_h = sites_kept(host_keys, lambda st, key: conservative[st][key]["joins"])
    ex_a = sites_kept(None, lambda st, key: exact[st]["utilities"][key]["joins"])
    co_a = sites_kept(None, lambda st, key: conservative[st][key]["joins"])
    allu = [(st, key, u) for st, r in exact.items() for key, u in r["utilities"].items()]
    hostu = [(st, key, u) for st, key, u in allu if key in host_keys]
    missing_hosts = sorted(host_keys - {key for _, key, _ in allu})

    def tally(us):
        return {"exact": sum(u["method"] == "exact" for _, _, u in us),
                "conservative": sum(u["method"] == "conservative" for _, _, u in us),
                "conservative_over_the_ceiling": sum(u["method"] == "conservative" and "ceiling" in u["why_conservative"]
                                                     for _, _, u in us),
                "conservative_divisor": sum(u["method"] == "conservative" and "divisor" in u["why_conservative"]
                                            for _, _, u in us),
                "reference_undefined": sum(not u["reference"]["defined"] for _, _, u in us),
                "reference_not_searched": sum(not u["reference"]["searched"] for _, _, u in us)}

    counts = {"states": run_states, "criterion": criterion, "utilities": tally(allu), "hosts": {**tally(hostu), "n": len(hostu),
                                                                          "not_found_in_the_states_run": missing_hosts},
              "sites_kept_for_the_hosts": {"exact": len(ex_h), "exact_not_on_the_target_list": not_listed(ex_h),
                                           "conservative": len(co_h), "conservative_not_on_the_target_list": not_listed(co_h)},
              "sites_kept_for_every_utility": {"exact": len(ex_a), "exact_not_on_the_target_list": not_listed(ex_a),
                                               "conservative": len(co_a), "conservative_not_on_the_target_list": not_listed(co_a)},
              "place_test_reference_shown_where_exact_is_undefined": shown_without,
              "kept_not_in_the_conservative_set": len(violations), "violations": violations,
              "witnesses_checked": n_wit, "witnesses_failing": len(bad_wit), "failing_witnesses": bad_wit,
              "witness_sides_realised": n_real if realise_witnesses else None,
              "witness_sides_realised_differing": len(bad_real) if realise_witnesses else None,
              "realised_differing": bad_real,
              "seconds": {"expand": round(t_expand, 2), "exact_by_state": timing,
                          "checks_and_rows": round(time.time() - t2, 2)}}
    out = {"what_this_is": ("The exact attribution of the verification pass (docs/gate1/exact-attribution-brief-2026-11-16.md; "
                            "D-65 item 4), with the reference repair (docs/gate1/reference-repair-rule-2026-11-18.md; "
                            "D-72 item 4). Load and sales only. Counts are reports; none is a target."),
           "criterion": criterion, "place_test_reference": px.REFERENCE_CONDITION, "expansion": expansion, "exact": exact,
           "hosts": [{"utility": f"{u}:{s}", "name": text(inp.names.get((u, s)))} for u, s in hosts],
           "counts": counts}
    return {"json": out, "csv": rows, "summary": _summary(out, hosts, listed is not None)}


def _summary(out: dict, hosts: list, has_targets: bool) -> str:
    L = ["The exact attribution (brief 2026-11-16; D-65 item 4), with the reference repair (D-72 item 4). Load and sales "
         "only. Counts are reports; none is a target.",
         f"criterion: {out['criterion']} ("
         + ("R7's triple: place as built, place with no anchoring, accepted" if out["criterion"] == "either_reading"
            else "D-66 4.1's pair: place as built, accepted") + ")", ""]
    L.append(f"The {len(hosts)} hosts:")
    for u, s in hosts:
        key = f"{u}:{s}"
        r = out["exact"].get(s, {}).get("utilities", {}).get(key)
        name = next((h["name"] for h in out["hosts"] if h["utility"] == key), "")
        if r is None:
            L.append(f"  {key} {name}: not a panel unit in the states run")
            continue
        ref = r["reference"]
        rtxt = (f"{ref['place']} {ref['crossing']}" if ref["defined"] else f"undefined ({ref['why_undefined']})")
        rtxt += f" [{ref['settings_enumerated']} settings enumerated" + ("" if ref["searched"] else ", not searched") + "]"
        method = r["method"] + (f" ({r['why_conservative']})" if r["why_conservative"] else "")
        L.append(f"  {key} {name}: {method}; {r['configurations']} configurations"
                 f"{'; complete' if r['complete'] else ''}; reference {rtxt}")
        L.append(f"      kept sites: {', '.join(r['joins']) or 'none'}")
    c = out["counts"]
    L += ["", "counts"]
    u, h = c["utilities"], c["hosts"]
    L.append(f"  states run: {', '.join(c['states'])}")
    L.append(f"  utilities: {u['exact'] + u['conservative']} ({u['exact']} exact, {u['conservative']} conservative: "
             f"{u['conservative_over_the_ceiling']} over the ceiling, {u['conservative_divisor']} for a divisor); "
             f"reference undefined for {u['reference_undefined']} ({u['reference_not_searched']} of them not searched)")
    L.append(f"  the {h['n']} hosts found: {h['exact']} exact, {h['conservative']} conservative "
             f"({h['conservative_over_the_ceiling']} over the ceiling, {h['conservative_divisor']} for a divisor); "
             f"reference undefined for {h['reference_undefined']} ({h['reference_not_searched']} of them not searched)"
             + (f"; not found: {', '.join(h['not_found_in_the_states_run'])}" if h["not_found_in_the_states_run"] else ""))
    for label, k in (("the hosts", "sites_kept_for_the_hosts"), ("every utility in the states run", "sites_kept_for_every_utility")):
        x = c[k]
        tl = (lambda n: f" ({n} not on the target list)") if has_targets else (lambda n: "")
        L.append(f"  sites kept for {label}: {x['exact']}{tl(x['exact_not_on_the_target_list'])}; "
                 f"the conservative check for the same utilities: {x['conservative']}{tl(x['conservative_not_on_the_target_list'])}")
    shown = c["place_test_reference_shown_where_exact_is_undefined"]
    L.append(f"  {out['place_test_reference']}")
    L.append(f"  the place test shows a reference where the reference here is undefined: {len(shown)}"
             + ("" if not shown else ". For each, the place test's reference and its \"keeps its place\" are the diagnostic "
                                     "only and do not override the undefined reference:"))
    for x in shown:
        L.append(f"      {x['utility']} {x['name']}: the place test shows {x['place_test_reference']}, keeps its place "
                 f"{x['place_test_keeps_its_place']}; the reference here is undefined")
    L.append(f"  kept questions not in the conservative check's set (must be 0): {c['kept_not_in_the_conservative_set']}")
    L.append(f"  witness pairs checked: {c['witnesses_checked']}; failing: {c['witnesses_failing']}")
    if c["witness_sides_realised"] is not None:
        L.append(f"  witness sides rebuilt through scratch_state and assignment.evaluate: {c['witness_sides_realised']}; "
                 f"outcome different from the one recorded: {c['witness_sides_realised_differing']}")
    else:
        L.append("  witness sides rebuilt through scratch_state: not run (--realise-witnesses)")
    sec = c["seconds"]
    L.append(f"  seconds: expand {sec['expand']}; exact by state "
             + ", ".join(f"{s} {t}" for s, t in sec["exact_by_state"].items())
             + f"; checks and rows {sec['checks_and_rows']}")
    return "\n".join(L)


def _dumps(x) -> str:
    return json.dumps(x, indent=2, default=lambda v: None if isinstance(v, float) and math.isnan(v) else
                      (v.item() if isinstance(v, np.generic) else str(v))) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("corrections")
    ap.add_argument("--targets")
    ap.add_argument("--out")
    ap.add_argument("--csv")
    ap.add_argument("--also-states", help="comma-separated states to run besides those with a correction")
    ap.add_argument("--theta", type=float, default=THETA)
    ap.add_argument("--ceiling", type=int, default=CEILING)
    ap.add_argument("--realise-witnesses", action="store_true",
                    help="rebuild both sides of every witness through scratch_state and assignment.evaluate and compare")
    ap.add_argument("--criterion", choices=CRITERIA, default="either_reading",
                    help="the keep criterion with a defined reference: R7's triple (either_reading, the default) or D-66 "
                         "4.1's pair (as_built), a named alternative that decides nothing (D-72 item 4)")
    a = ap.parse_args(argv)
    out = px.check_out_path(Path(a.out)) if a.out else None
    csv_out = px.check_out_path(Path(a.csv)) if a.csv else None
    t0 = time.time()
    corrections = json.loads(Path(a.corrections).read_text())
    inp = px.load_frozen()
    hosts = hosts_from_headline(pd.read_csv(HEADLINE))
    if len(hosts) != HOSTS_EXPECTED:
        raise SystemExit(f"{HEADLINE}: the rows at 2% that are in the headline set or out of it for ruling 4's reasons only "
                         f"number {len(hosts)}, not {HOSTS_EXPECTED}. The run stops: the hosts are not what the brief "
                         f"describes, so the states and the summary would not be.")
    states = ([s.strip() for s in a.also_states.split(",") if s.strip()] if a.also_states else sorted({s for _, s in hosts}))
    res = run(corrections, inp, targets=a.targets, states=states, hosts=hosts, theta=a.theta, ceiling=a.ceiling,
              realise_witnesses=a.realise_witnesses, criterion=a.criterion)
    total = time.time() - t0
    res["json"]["counts"]["seconds"]["total"] = round(total, 2)
    print(res["summary"])
    print(f"  seconds in all (inputs loaded, expand, exact, outputs built): {total:.1f}")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_dumps(res["json"]))
        print("written:", out)
    if csv_out:
        csv_out.parent.mkdir(parents=True, exist_ok=True)
        with csv_out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            w.writeheader()
            w.writerows(res["csv"])
        print("written:", csv_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
