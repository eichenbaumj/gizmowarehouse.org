"""An exhaustive evaluator of the exact attribution (docs/gate1/exact-attribution-brief-2026-11-16.md, section 7).

Load and sales only; no price is read and nothing is written. Written from sections 1 to 4 of the brief and the load
model of pipeline/facilities/pass_c_expand.py, apart from the implementation (which this file never imports). It uses
nothing from the brief's section 5: no merged settings, no relevance, no ceiling. Every question of the state is
enumerated at every setting, every configuration of the full product is realised through `pass_c_expand.scratch_state`
and `assignment.evaluate`, and each utility's outcome is computed here from the `as_built` and `no_anchoring` matrices.

It is meant for made-up states small enough for the full product (a few thousand configurations). It is slow by
design: one scratch rebuild per configuration.

Readings this file makes where the brief does not settle the point (the report lists them too):

* A `candidates` correction ({"fid", "kind": "candidates", "candidates": [utility, ...]}) adds candidate suppliers to
  a site; the site stays on the utility it is on and is unresolved from then on. Its candidate list is the given list
  followed by any inventory candidate it leaves out (none, where parse_corrections requires the given list to contain
  them). It changes no load, so it is used only to list the site's assignment
  question and its settings, and is not passed to `parse_corrections` (every configuration assigns that site
  explicitly, as every assignment question is assigned in every configuration).
* A reference-defining question with no convention has no setting in the reference configuration; where one is
  needed (a witness that omits the question) its first setting is used.
* The reference (changed under docs/gate1/reference-repair-rule-2026-11-18.md, section 8.3): it is no longer found
  at the ends of the reference-defining questions. It is taken from tests/reference_enumerator.py, which realises
  every combination of every setting of every reference-defining question (rule R2), with a provisional date among
  them (`provisional_defines=True`, the exact attribution's list). The limit of twelve questions is replaced by a
  refusal above REFERENCE_COMBINATION_LIMIT combinations, which keeps a made-up case small.
* The outcome with a defined reference (rule R7): the triple (place as built, place with no anchoring, accepted) under
  `criterion="either_reading"`, the default; `criterion="as_built"` gives D-66 4.1's pair (place as built, accepted).
  "Place with no anchoring" is the place of the brief's section 3 read from the no-anchoring reading. An undefined
  reference's outcome (the four values) is the same under both.
* A crossing is a float year or None; a share with any load and no positive base (zero or missing) is infinite.
"""
from __future__ import annotations

import dataclasses
import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402

import reference_enumerator as enumerator  # noqa: E402

YEARS = asg.YEARS
FLOOR = asg.CLEAN_BELOW
REFERENCE_COMBINATION_LIMIT = 4096   # combinations of reference settings: made-up cases only
CRITERIA = ("either_reading", "as_built")
OFF_PANEL = "off_panel"          # how a witness names the off-panel setting; inside this file it is None
CANDIDATES_KIND = "candidates"
ADDED = "candidates_added"       # a utility_assign that is neither verified nor one territory: unresolved


# ---- outcomes (brief section 3), computed here from the two matrices ------------------------------------------------

def _positive(base_k) -> bool:
    return base_k is not None and not (isinstance(base_k, float) and math.isnan(base_k)) and base_k > 0


def reading(v, base_k, theta: float) -> dict:
    """First crossing, largest share and place of one reading (GWh by panel year) of one utility."""
    v = np.asarray(v, dtype=float)
    crossing = None
    if _positive(base_k):
        hit = np.nonzero(v >= theta * base_k)[0]
        crossing = float(YEARS[int(hit[0])]) if len(hit) else None
    top = float(v.max())
    share = 0.0 if not top > 0 else (top / base_k if _positive(base_k) else math.inf)
    if crossing is not None:
        place = asg.group(crossing)
    else:
        place = "comparison" if share < FLOOR else "neither"
    return {"crossing": crossing, "share": share, "place": place}


def outcome(ab, na, base_k, ref: dict, theta: float, criterion: str = "either_reading") -> tuple:
    """The outcome of brief section 3, widened by rule R7. `ref` is {"defined", "place", "crossing"}.

    Defined reference: ("defined", place as built, place with no anchoring, accepted) under "either_reading";
    ("defined", place as built, accepted) under "as_built". Undefined: the four values, under either criterion.
    """
    if criterion not in CRITERIA:
        raise ValueError(f"criterion is one of {CRITERIA}, not {criterion!r}")
    a, n = reading(ab, base_k, theta), reading(na, base_k, theta)
    if not ref["defined"]:
        return ("undefined", a["crossing"], n["crossing"], a["share"] < FLOOR, n["share"] < FLOOR)
    accepted = a["place"] == ref["place"]
    if accepted:
        if ref["place"] == "cohort":
            accepted = asg.same_place(ref["crossing"], a["crossing"]) and asg.same_place(ref["crossing"], n["crossing"])
        elif ref["place"] == "early":
            accepted = asg.group(n["crossing"]) == "early"
        elif ref["place"] == "comparison":
            accepted = n["share"] < FLOOR
    if criterion == "as_built":
        return ("defined", a["place"], bool(accepted))
    return ("defined", a["place"], n["place"], bool(accepted))


# ---- questions, settings and the reference configuration (brief sections 2 and 4) -----------------------------------

@dataclasses.dataclass
class Question:
    fid: str
    question: str                  # "assignment" | "date" | "capacity"
    settings: list                 # assignment: utility ids and None (off the panel); date: years and "never"; capacity
    reference: object              # the reference configuration's setting (None for an assignment means off the panel)
    defining: bool                 # a reference-defining question (no convention, or a provisional date)

    @property
    def key(self) -> tuple:
        return (self.fid, self.question)

    @property
    def ends(self) -> tuple:
        return (self.settings[0], self.settings[-1])


class Evaluator:
    """One state's questions, realisations (cached by configuration), references and outcomes."""

    def __init__(self, inp, corrections: list[dict], st: str, theta: float = 0.02, criterion: str = "either_reading"):
        if criterion not in CRITERIA:
            raise ValueError(f"criterion is one of {CRITERIA}, not {criterion!r}")
        self.inp, self.st, self.theta, self.criterion = inp, st, theta, criterion
        self.corrections = list(corrections)
        self.units = inp.units[inp.units.get_level_values("state") == st]
        self.base = inp.base.reindex(self.units)
        self.regions = inp.regions.reindex(self.units)
        added: dict[str, list] = {}
        rest = []
        for c in corrections:
            if c.get("kind") == CANDIDATES_KIND:
                fid = c["fid"]
                if fid not in inp.fac.index:
                    raise ValueError(f"{fid} is not in the inventory")
                if fid in added:
                    raise ValueError(f"{fid}: two candidates corrections")
                added[fid] = [int(u) for u in c["candidates"]]
            else:
                rest.append(c)
        self.added = added
        self.corr = px.parse_corrections(rest, inp)
        self.provisional = {c["fid"] for c in corrections
                            if c.get("kind") == "date" and c.get("convention_is") == "provisional"}
        self.questions = self._list_questions()
        self.by_key = {q.key: q for q in self.questions}
        self._cache: dict = {}
        self._reference = None

    # -- listing --

    def _site_loads(self, fid: str, c) -> list[np.ndarray]:
        """The site's MW by panel year in every setting of its own date and capacity questions (before any factor)."""
        inp = self.inp
        r = inp.fac.loc[fid]
        crypto = bool(r.is_crypto) if "is_crypto" in inp.fac else False
        if bool(inp.fixed[fid]):
            if c is not None and c.not_a_site:
                return [np.zeros(len(YEARS))]
            rows = inp.fy[inp.fy.fid == fid].groupby("year").mw.sum().reindex(YEARS).fillna(0.0).values
            return [rows]
        raw = c.size if (c is not None and c.size is not None) else r.mw_full_raw

        def vec(h, has):
            if not has or crypto or pd.isna(raw):
                return np.zeros(len(YEARS))
            return np.array([px.site_mw(h, raw, y) for y in YEARS])
        if c is None:
            return [vec(inp.hist[fid], bool(inp.fac.in_dose[fid]))]
        if c.not_a_site:
            return [np.zeros(len(YEARS))]
        qs = c.questions()
        if not qs:
            h = c.history({}) or inp.hist[fid]
            return [vec(h, h[0] != "never")]
        vals = [px._date_values(c) if q == "date" else px._capacity_values(c) for q in qs]
        out = []
        for combo in itertools.product(*vals):
            h = c.history({(fid, q): v for q, v in zip(qs, combo)})
            out.append(vec(h, h[0] != "never"))
        return out

    def _list_questions(self) -> list[Question]:
        inp, st = self.inp, self.st
        fac = inp.fac[inp.fac.state == st].copy()
        for fid in self.added:
            if fid not in fac.index:
                raise ValueError(f"{fid} is not in {st}")
        # The corrected assignment, candidates and status of every site, as this file reads the corrections.
        on: dict = {}
        cands: dict = {}
        for fid in fac.index:
            u = fac.utility_id_eia[fid]
            on[fid] = int(u) if pd.notna(u) else None
            cands[fid] = asg.candidates(fac.utility_candidates[fid])
            c = self.corr.get(fid)
            if c is not None:
                if c.assign == px.OFF:
                    on[fid] = None
                    fac.loc[fid, "utility_assign"] = "wholesale_direct"
                elif c.assign is not None:
                    on[fid] = int(c.assign[0])
                    fac.loc[fid, "utility_assign"] = "verified_by_hand"
                if c.narrow is not None:
                    cands[fid] = list(c.narrow)
                if c.reopen is not None:
                    on[fid] = on[fid] if on[fid] in c.reopen else c.reopen[0]
                    cands[fid] = list(c.reopen)
                    fac.loc[fid, "utility_assign"] = "reopened"
            if fid in self.added:
                cands[fid] = list(dict.fromkeys(self.added[fid] + cands[fid]))
                fac.loc[fid, "utility_assign"] = ADDED
            fac.loc[fid, "utility_candidates"] = ";".join(str(x) for x in cands[fid])
        ercot = {k for k in self.units if self.regions.get(k) == asg.ERCOT_REGION}
        res = asg.resolved(fac, ercot)
        out = []
        for fid in fac.index:
            c = self.corr.get(fid)
            loads = self._site_loads(fid, c)
            has_load = any(v.any() for v in loads)
            if not res[fid] and on[fid] is not None and has_load:
                settings = list(dict.fromkeys([on[fid]] + cands[fid])) + [None]
                out.append(Question(fid, "assignment", settings, on[fid], False))
            if c is None or bool(inp.fixed[fid]):
                continue
            for q in c.questions():
                if q == "date":
                    vals = px._date_values(c)
                    conv = c.date.get("convention")
                    if conv is None:
                        ref = None
                    elif conv == "never":
                        ref = "never"
                    else:
                        years = [v for v in vals if v != "never"]
                        ref = min(max(int(conv), years[0]), years[-1])
                    defining = conv is None or fid in self.provisional
                else:
                    vals = px._capacity_values(c)
                    conv = c.split.get("convention")
                    ref = None if conv is None else (vals[0] if conv == px.EARLY else vals[-1])
                    defining = conv is None
                out.append(Question(fid, q, vals, ref if ref is not None else vals[0], defining))
        return out

    # -- configurations --

    def reference_configuration(self) -> dict:
        return {q.key: q.reference for q in self.questions}

    def normalise(self, settings: dict) -> dict:
        """A full configuration from a partial one keyed (fid, question) or "<fid> <question>"; absent: the reference."""
        cfg = self.reference_configuration()
        for k, v in settings.items():
            if isinstance(k, str):
                fid, q = k.rsplit(" ", 1)
                k = (fid, q)
            if k not in self.by_key:
                raise KeyError(f"{k} is not a question of {self.st}")
            if k[1] == "assignment":
                v = None if (v is None or v == OFF_PANEL) else int(v)
            elif v not in ("never", px.EARLY, px.LATE):
                v = int(v)
            if v not in self.by_key[k].settings:
                raise ValueError(f"{v!r} is not a setting of {k}: {self.by_key[k].settings}")
            cfg[k] = v
        return cfg

    def realise(self, cfg: dict) -> dict:
        """The as_built and no_anchoring matrices of one full configuration, through scratch_state and evaluate."""
        key = tuple(cfg[q.key] for q in self.questions)
        if key in self._cache:
            return self._cache[key]
        corr = dict(self.corr)
        choice = {}
        for (fid, q), v in cfg.items():
            if q == "assignment":
                c = corr.get(fid) or px.Correction(fid=fid, state=self.st, inventory_year=self.inp.fac.energized_year[fid])
                corr[fid] = dataclasses.replace(c, assign=px.OFF if v is None else (int(v), self.st), reopen=None, narrow=None)
            else:
                choice[(fid, q)] = v
        fac, fy, factor = px.scratch_state(self.inp, corr, self.st, choice)
        _, m, _ = asg.evaluate(fac, fy, self.units, self.base, self.regions, thresholds=(self.theta,))
        out = {"as_built": m["as_built"], "no_anchoring": m["no_anchoring"], "factor": factor}
        self._cache[key] = out
        return out

    def row(self, m: dict, k) -> tuple:
        return (m["as_built"].loc[k].reindex(YEARS).values.astype(float),
                m["no_anchoring"].loc[k].reindex(YEARS).values.astype(float))

    # -- the reference (brief section 4) --

    def reference(self) -> dict:
        """Every reference-defining question at every setting, realised by tests/reference_enumerator.py (rule R2)."""
        if self._reference is not None:
            return self._reference
        defining = [q for q in self.questions if q.defining]
        n = math.prod(len(q.settings) for q in defining)
        if n > REFERENCE_COMBINATION_LIMIT:
            raise ValueError(f"{n} combinations of reference settings in {self.st}, more than "
                             f"{REFERENCE_COMBINATION_LIMIT}: keep the made-up case smaller")
        t = enumerator.table(self.inp, self.corrections, self.st, self.theta, provisional_defines=True,
                             limit=REFERENCE_COMBINATION_LIMIT)
        # The enumerator lists the questions by its own code; they have to be the ones this file calls defining.
        if sorted((q["fid"], q["question"], tuple(q["settings"])) for q in t["questions"]) != \
                sorted((q.fid, q.question, tuple(q.settings)) for q in defining):
            raise AssertionError(f"{self.st}: the enumerator's reference-defining questions differ from this file's")
        found = enumerator.from_table(t)
        ref = {}
        for k in self.units:
            r = found[k]
            ref[k] = {"defined": r["defined"], "place": r["place"], "crossing": r["crossing"]}
        self._reference = ref
        return ref

    def outcomes(self, cfg: dict) -> dict:
        ref, m = self.reference(), self.realise(cfg)
        return {k: outcome(*self.row(m, k), self.base[k], ref[k], self.theta, self.criterion) for k in self.units}

    # -- the full product --

    def configurations(self):
        qs = self.questions
        for combo in itertools.product(*(q.settings for q in qs)):
            yield dict(zip((q.key for q in qs), combo))

    def n_configurations(self) -> int:
        return math.prod(len(q.settings) for q in self.questions)

    def pivotal(self) -> dict:
        qs = self.questions
        outs = {}
        for cfg in self.configurations():
            outs[tuple(cfg[q.key] for q in qs)] = self.outcomes(cfg)
        piv = {k: set() for k in self.units}
        for i, q in enumerate(qs):
            groups: dict = {}
            for combo, o in outs.items():
                groups.setdefault(combo[:i] + combo[i + 1:], []).append(o)
            for k in self.units:
                if any(len({o[k] for o in g}) > 1 for g in groups.values()):
                    piv[k].add(q.key)
        return piv


def pivotal_questions(inp, corrections: list[dict], st: str, theta: float = 0.02, criterion: str = "either_reading") -> dict:
    """Brief section 7: the full product over every setting of every question in the state; the outcome by `criterion`
    (rule R7: "either_reading", the default, or "as_built").

    {"configurations": int,
     "reference": {(utility_id_eia, state): {"defined": bool, "place": str | None, "crossing": float | None}},
     "pivotal": {(utility_id_eia, state): {(fid, question), ...}}}
    """
    ev = Evaluator(inp, corrections, st, theta, criterion)
    return {"configurations": ev.n_configurations(), "reference": ev.reference(), "pivotal": ev.pivotal()}


def configuration_outcome(inp, corrections: list[dict], st: str, settings: dict, theta: float = 0.02,
                          evaluator: Evaluator | None = None, criterion: str = "either_reading") -> dict:
    """One explicit configuration: its outcome for every utility and its realised matrices.

    `settings` is keyed (fid, question) or "<fid> <question>", with the setting's value (a utility id or "off_panel",
    a year, "never", "early" or "late"); a question left out is held at the reference configuration.
    """
    ev = evaluator or Evaluator(inp, corrections, st, theta, criterion)
    cfg = ev.normalise(settings)
    m = ev.realise(cfg)
    return {"configuration": cfg, "outcomes": ev.outcomes(cfg),
            "as_built": m["as_built"], "no_anchoring": m["no_anchoring"], "factor": m["factor"]}
