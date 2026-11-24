"""The classification Joe adopted for the second number on 2026-11-19 (D-105), its runs on single doses per form and the
common-dose exception per capped form (pipeline/analysis/second_number.py, sections 3a and 4). Invented inputs only: no
file under data/ is read, no price exists here; every "price" is a number made up in the test.

Three of the planted checks are shown able to fail by breaks made in the test process (monkeypatch), not in the code:
the two-point line, the meaning of "not settled" in the leverage shares, and the common-dose exception."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import second_number as sn  # noqa: E402
from pipeline.analysis import second_number_classes as sc  # noqa: E402
from test_second_number_invented import invented_world, log_outcome  # noqa: E402

U, C25, C50 = sn.cap_label(None), sn.cap_label(25.0), sn.cap_label(50.0)
LABS = (U, C25, C50)
TOL = 1e-10

# ---- an invented population that reaches all eight classes ----------------------------------------------------------
# (changes at every form, in three histories; the first is the history as assigned)
SAME = {
    "2:AA": (0.0, [0.0, 0.0, 0.0], False),       # 2 no endpoint exposure in modeled histories
    "4:AA": (1.0, [1.0, 0.5, 1.2], True),        # 4 settled
    "6:AA": (5.0, [5.0, 1.0, 9.0], True),        # 5 uncertain positive exposure
    "7:AA": (0.0, [0.0, 0.0, 6.0], True),        # 6 apparent zero
    "8:AA": (8.0, [8.0, 0.0, 8.0], True),        # 7 positive as assigned, zero in some history
    "9:AA": (0.0, [0.0, -3.0, 0.0], True),       # 8 other, not settled
}
# Karnes-like: above the 25-point cap at both ends in its upper history, so zero change at 25 and not at 50 or uncapped.
# And a settled utility at 25 and 50 that is zero as assigned (kept flag), apparent zero uncapped.
BY_CAP = {
    "3:AA": {C25: (0.0, [0.0, 0.0, 0.0]), C50: (0.0, [0.0, 0.0, 5.13]), U: (0.0, [0.0, 0.0, 1014.1])},
    "5:AA": {C25: (0.0, [0.0, 0.0, 1.5]), C50: (0.0, [0.0, 0.0, 1.5]), U: (0.0, [0.0, 0.0, 3.0])},
}
REACH = {**{u: r for u, (_, _, r) in SAME.items()}, "3:AA": True, "5:AA": True}
UNASSIGNED = {"1:AA": {U: [18.8, 27.3], C25: [18.8, 22.7], C50: [18.8, 27.3]}}      # Portland-General-like: class 1

PLANTED = {
    C25: {"1:AA": sn.NO_SINGLE_DOSE, "2:AA": sn.NO_ENDPOINT_EXPOSURE, "3:AA": sn.ZERO_CHANGE_LOAD_IN_REACH,
          "4:AA": sn.SETTLED, "5:AA": sn.SETTLED, "6:AA": sn.UNCERTAIN, "7:AA": sn.APPARENT_ZERO,
          "8:AA": sn.POSITIVE_ZERO_SOME, "9:AA": sn.OTHER_NOT_SETTLED},
}
PLANTED[C50] = {**PLANTED[C25], "3:AA": sn.APPARENT_ZERO}
PLANTED[U] = {**PLANTED[C25], "3:AA": sn.APPARENT_ZERO, "5:AA": sn.APPARENT_ZERO}


def population(extra_unassigned=None):
    assigned, changes = {lab: {} for lab in LABS}, {lab: {} for lab in LABS}
    for lab in LABS:
        for u, (a, v, _) in SAME.items():
            assigned[lab][u], changes[lab][u] = a, np.array(v)
        for u, by in BY_CAP.items():
            assigned[lab][u], changes[lab][u] = by[lab][0], np.array(by[lab][1])
        for u, by in {**UNASSIGNED, **(extra_unassigned or {})}.items():
            changes[lab][u] = np.array(by[lab])
    return assigned, changes, dict(REACH), sorted({**UNASSIGNED, **(extra_unassigned or {})})


def classified_population(established=None, extra_unassigned=None):
    a, ch, r, na = population(extra_unassigned)
    return sn.classify_by_cap(a, ch, r, na, {} if established is None else established)


def one_cell_frame(ids):
    keys = [(int(u.split(":")[0]), u.split(":")[1]) for u in ids]
    n = len(keys)
    z = np.zeros(n, dtype=int)
    return sn.Frame("long_difference", keys, list(sn.PRE) + list(sn.POST), 3, [z.copy()], z.copy(), z.copy(), z.copy(),
                    z.copy(), z.copy())


# ---- planted checks, written as functions so a break made in the test process can be shown to trip them ----------------

def check_planted_classes():
    got = classified_population()
    for lab in LABS:
        assert {u: e["class"] for u, e in got[lab].items()} == PLANTED[lab], lab


def check_leverage_shares_by_hand():
    """One cell, the eight utilities with a single dose at 25 points. Leverage is (d - mean)^2 over its sum."""
    cl = classified_population()
    ids = [u for u in sorted(cl[C25]) if cl[C25][u]["class"] != sn.NO_SINGLE_DOSE]
    f = one_cell_frame(ids)
    d = np.array([cl[C25][u]["dose"] for u in ids])                      # 0, 0, 1, 0, 5, 0, 8, 0 for 2..9
    assert list(d) == [0.0, 0.0, 1.0, 0.0, 5.0, 0.0, 8.0, 0.0]
    dev = (d - d.mean()) ** 2
    lev = dev / dev.sum()
    by_hand_5_to_8 = lev[[4, 5, 6, 7]].sum()                              # 6, 7, 8, 9:AA
    by_hand_class_2 = lev[0]                                              # 2:AA
    r = sn.run_summary({C25: ids}, f, cl)[C25]
    assert r["share_of_leverage_held_by_classes_5_to_8_not_settled"] == pytest.approx(by_hand_5_to_8, abs=1e-6)
    assert r["share_of_leverage_held_by_class_2_no_endpoint_exposure"] == pytest.approx(by_hand_class_2, abs=1e-6)
    assert r["not_settled_utilities_classes_5_to_8"] == 4
    assert r["settled_utilities_flagged_not_a_verified_zero"] == 1
    assert r["class_counts"][sn.NO_ENDPOINT_EXPOSURE] == 1 and r["class_counts"][sn.NO_SINGLE_DOSE] == 0


UMATILLA_LIKE = {"10:AA": {U: [461.9, 1244.3], C25: [25.0, 25.0, 25.0], C50: [50.0, 50.0, 50.0]}}


def check_exclusion_retained_without_a_finding():
    """Every history here gives one capped change, but with no finding the exclusion is retained at both capped forms."""
    cl = classified_population(established={}, extra_unassigned=UMATILLA_LIKE)
    for lab in LABS:
        assert cl[lab]["10:AA"]["class"] == sn.NO_SINGLE_DOSE, lab
    assert "no common-dose finding supplied" in cl[C25]["10:AA"]["why"]


# ---- 1. one class per utility at each form ---------------------------------------------------------------------------

def test_every_utility_is_in_exactly_one_class_at_each_form_and_all_eight_are_reached():
    check_planted_classes()
    cl = classified_population()
    counts = sn.check_one_class_each(cl, list(PLANTED[C25]))
    for lab in LABS:
        assert sum(counts[lab].values()) == 9
    assert all(n == 1 for c, n in counts[C25].items() if c not in (sn.SETTLED,))
    assert counts[C25][sn.SETTLED] == 2
    assert set(c for c, n in counts[C25].items() if n) == set(sn.ADOPTED_CLASSES)       # all eight at 25 points
    with pytest.raises(ValueError, match="have no class"):
        sn.check_one_class_each(cl, list(PLANTED[C25]) + ["99:AA"])


def test_a_utilitys_class_differs_between_forms():
    cl = classified_population()
    assert cl[C25]["3:AA"]["class"] == sn.ZERO_CHANGE_LOAD_IN_REACH
    assert cl[C50]["3:AA"]["class"] == sn.APPARENT_ZERO and cl[U]["3:AA"]["class"] == sn.APPARENT_ZERO
    assert cl[C25]["5:AA"]["class"] == sn.SETTLED and cl[U]["5:AA"]["class"] == sn.APPARENT_ZERO


def _predicates(a, v, reach):
    """Each adopted class written out on its own, "not classed above" explicit, for a utility with a single dose."""
    lo, hi = float(np.min(v)), float(np.max(v))
    c2 = not reach
    c3 = reach and lo == 0 and hi == 0
    c4 = not (c2 or c3) and hi - lo < 2
    rest = not (c2 or c3 or c4)
    c5 = rest and lo > 0
    c6 = rest and not c5 and a == 0 and hi > 0
    c7 = rest and not (c5 or c6) and a > 0 and lo <= 0
    c8 = rest and not (c5 or c6 or c7)
    return {sn.NO_ENDPOINT_EXPOSURE: c2, sn.ZERO_CHANGE_LOAD_IN_REACH: c3, sn.SETTLED: c4, sn.UNCERTAIN: c5,
            sn.APPARENT_ZERO: c6, sn.POSITIVE_ZERO_SOME: c7, sn.OTHER_NOT_SETTLED: c8}


def test_exhaustive_and_exclusive_on_a_random_invented_population():
    rng = np.random.default_rng(11)
    grid = np.array([-3.0, -1.0, 0.0, 0.0, 0.0, 0.5, 1.0, 1.99, 2.0, 3.0, 25.0])
    seen = set()
    for _ in range(20000):
        h = int(rng.integers(1, 7))
        v = rng.choice(grid, h) if rng.random() < 0.6 else np.round(rng.normal(0, 4, h), int(rng.integers(0, 3)))
        a = float(v[int(rng.integers(0, h))])
        reach = True if np.any(v != 0) else bool(rng.random() < 0.5)
        r = sn.adopted_class(a, v, reach)
        p = _predicates(a, v, reach)
        assert sum(p.values()) == 1 and p[r["class"]], (a, v, reach, r)
        assert (r["flag"] == sn.NOT_A_VERIFIED_ZERO) == (r["class"] == sn.SETTLED and a == 0 and v.max() > 0)
        seen.add(r["class"])
    assert seen == set(sn.ADOPTED_CLASSES) - {sn.NO_SINGLE_DOSE}


def test_boundaries():
    assert sn.adopted_class(3.0, [3.0, 1.0, 3.0], True)["class"] == sn.UNCERTAIN            # exactly two apart
    assert sn.adopted_class(3.0, [3.0, 1.0 + 1e-9, 3.0], True)["class"] == sn.SETTLED
    assert sn.adopted_class(1e-12, [1e-12, 0.0], True)["class"] == sn.SETTLED              # not exactly zero: not class 3
    with pytest.raises(ValueError, match="inconsistent"):
        sn.adopted_class(0.0, [0.0, 2.0], False)
    with pytest.raises(ValueError, match="outside the range"):
        sn.adopted_class(5.0, [1.0, 2.0], True)
    with pytest.raises(ValueError, match="must be stated"):
        sn.adopted_class(None, [1.0], True)


# ---- 2. the retained flag ------------------------------------------------------------------------------------------

def test_a_settled_utility_that_is_zero_as_assigned_keeps_the_flag():
    cl = classified_population()
    assert cl[C25]["5:AA"]["class"] == sn.SETTLED and cl[C25]["5:AA"]["flag"] == sn.NOT_A_VERIFIED_ZERO
    assert cl[C25]["4:AA"]["flag"] is None                                          # positive as assigned: no flag
    assert cl[U]["5:AA"]["flag"] is None                                            # apparent zero uncapped: the class says it
    assert sn.NOT_A_VERIFIED_ZERO == "not_a_verified_zero"


# ---- 3. leverage shares --------------------------------------------------------------------------------------------

def test_leverage_shares_classes_5_to_8_and_class_2_on_separate_lines_by_hand():
    check_leverage_shares_by_hand()


# ---- 4. run membership per form ------------------------------------------------------------------------------------

def test_run_membership_per_form():
    cl = classified_population()
    ids = sorted(PLANTED[C25])
    f = one_cell_frame(ids)
    s = sn.run_samples(f, cl, n=2)
    for lab in LABS:
        assert s[sn.RUN_AS_ASSIGNED][lab]["utilities"] == [u for u in ids if u != "1:AA"]
        assert "1:AA" in s[sn.RUN_AS_ASSIGNED][lab]["left_out_named"]
        assert "1:AA" in s[sn.RUN_SETTLED][lab]["left_out_named"] and "1:AA" in s[sn.RUN_LEAVE_TEN][lab]["left_out_named"]
    assert s[sn.RUN_SETTLED][C25]["utilities"] == ["2:AA", "3:AA", "4:AA", "5:AA"]
    assert s[sn.RUN_SETTLED][C50]["utilities"] == ["2:AA", "4:AA", "5:AA"]
    assert s[sn.RUN_SETTLED][U]["utilities"] == ["2:AA", "4:AA"]
    # The two highest-leverage utilities among classes 5 to 8 at each form, by hand (one cell: (d - mean)^2).
    for lab in LABS:
        pool = [u for u in ids if u != "1:AA"]
        d = np.array([cl[lab][u]["dose"] for u in pool])
        lev = dict(zip(pool, (d - d.mean()) ** 2))
        cand = sorted((u for u in pool if cl[lab][u]["class"] in sn.NOT_SETTLED), key=lambda u: (-lev[u], u))[:2]
        assert s[sn.RUN_LEAVE_TEN][lab]["the_ten"] == cand, lab
        assert s[sn.RUN_LEAVE_TEN][lab]["utilities"] == [u for u in pool if u not in cand]
    # At 25 points 3:AA (class 3) cannot be among them; uncapped (class 6, dose 0) it is a candidate.
    assert "3:AA" not in s[sn.RUN_LEAVE_TEN][C25]["the_ten"]


def test_the_runs_never_call_the_superseded_classes(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the superseded as-built classes were called from the analysis path")
    monkeypatch.setattr(sn, "classify", boom)
    monkeypatch.setattr(sn, "classify_without_assigned", boom)
    monkeypatch.setattr(sn, "common_dose", boom)
    cl = classified_population()
    f = one_cell_frame(sorted(PLANTED[C25]))
    s = sn.run_samples(f, cl)
    sn.run_summary({lab: s[sn.RUN_SETTLED][lab]["utilities"] for lab in LABS}, f, cl)
    assert sn.NO_SITE not in sn.ADOPTED_CLASSES and all("no_site" not in c for c in sn.ADOPTED_CLASSES)
    assert all("no_site" not in r for r in sn.RUNS)


# ---- 5. the common-dose exception, per capped form -------------------------------------------------------------------

def test_without_a_finding_the_exclusion_is_retained_even_where_the_histories_agree():
    check_exclusion_retained_without_a_finding()


def test_an_established_common_change_at_one_capped_form_and_exclusion_at_another():
    est = {"10:AA": {C25: {"established": True, "dose": 25.0, "why": "invented: every admissible history at or above 25"},
                     C50: {"established": False, "dose": None, "why": "invented: completeness of its histories unassessed"},
                     U: {"established": True, "dose": 999.0, "why": "invented: must not be read for the uncapped form"}}}
    cl = classified_population(established=est, extra_unassigned=UMATILLA_LIKE)
    e25 = cl[C25]["10:AA"]
    assert e25["class"] == sn.SETTLED and e25["dose"] == 25.0 and e25["dose_source"] == "common_dose_rule finding"
    assert not e25["has_assigned_dose"] and e25["flag"] is None
    assert cl[C50]["10:AA"]["class"] == sn.NO_SINGLE_DOSE
    assert "completeness of its histories unassessed" in cl[C50]["10:AA"]["why"]
    assert cl[U]["10:AA"]["class"] == sn.NO_SINGLE_DOSE                              # no exception uncapped
    assert "no common-dose exception applies" in cl[U]["10:AA"]["why"]
    ids = sorted({*PLANTED[C25], "10:AA"}, key=lambda u: int(u.split(":")[0]))
    f = one_cell_frame(ids)
    s = sn.run_samples(f, cl)
    assert "10:AA" not in s[sn.RUN_AS_ASSIGNED][C25]["utilities"]                    # never in the primary run
    assert "enters this form's other runs" in s[sn.RUN_AS_ASSIGNED][C25]["left_out_named"]["10:AA"]
    assert "10:AA" in s[sn.RUN_SETTLED][C25]["utilities"] and "10:AA" in s[sn.RUN_LEAVE_TEN][C25]["utilities"]
    assert "10:AA" not in s[sn.RUN_SETTLED][C50]["utilities"] and "10:AA" in s[sn.RUN_SETTLED][C50]["left_out_named"]
    assert "10:AA" not in s[sn.RUN_LEAVE_TEN][U]["utilities"]
    assert sn.single_doses(cl)[C25]["10:AA"] == 25.0 and "10:AA" not in sn.single_doses(cl)[C50]


def test_the_uncapped_form_enters_only_where_its_histories_give_one_change():
    same_uncapped = {"11:AA": {U: [7.0, 7.0, 7.0], C25: [7.0, 7.0, 7.0], C50: [7.0, 7.0, 7.0]}}
    cl = classified_population(established={}, extra_unassigned=same_uncapped)
    assert cl[U]["11:AA"]["class"] == sn.SETTLED and cl[U]["11:AA"]["dose"] == 7.0      # rule 8.3 as written
    assert cl[C25]["11:AA"]["class"] == sn.NO_SINGLE_DOSE                               # capped: only the finding counts


def test_a_zero_common_change_stops_in_words():
    est = {"10:AA": {C25: {"established": True, "dose": 0.0, "why": "invented"}}}
    with pytest.raises(ValueError, match="cannot be classed.*unknown_load_histories does not return endpoint loads"):
        classified_population(established=est, extra_unassigned={"10:AA": {U: [0.0, 1.0], C25: [0.0, 0.0], C50: [0.0, 0.0]}})


def test_the_finding_is_required_and_checked():
    a, ch, r, na = population()
    with pytest.raises(TypeError):
        sn.classify_by_cap(a, ch, r, na)                                    # no default
    with pytest.raises(TypeError):
        sn.design_summary()                                                 # no default; stops before any file is read
    with pytest.raises(TypeError):
        sn.design_summary({})                                               # the scopes' verdicts are required too
    with pytest.raises(ValueError, match="no finite dose"):
        classified_population(established={"1:AA": {C25: {"established": True, "dose": None, "why": "x"}}})
    with pytest.raises(ValueError, match="must be"):
        classified_population(established={"1:AA": {C25: {"dose": 20.0}}})
    with pytest.raises(ValueError, match="outside the range"):                 # a finding its histories do not contain
        classified_population(established={"1:AA": {C25: {"established": True, "dose": 30.0, "why": "x"}}})


# ---- 6. the runs on outcomes ----------------------------------------------------------------------------------------

def _world_classified(units, q, regions, dose, usable, upper_bump: float):
    """Classes for the invented world: each utility's histories are its own trace and the same plus `upper_bump` points
    after 2012 on its host (an invented upper case), as built by second_number's own functions."""
    f = sn.build_frame(units, q, regions, usable)
    pts = sn.dose_points(dose)
    x = sn.dose_matrix(pts, f.keys, f.years)
    up = x.copy()
    hosts = np.array([k[0] % 100 == 0 for k in f.keys])
    up[hosts, f.n_pre:] += upper_bump
    assigned, changes = {}, {}
    for c in ps.CAPS:
        lab = sn.cap_label(c)
        a, b = sn.change(x, f.n_pre, c), sn.change(up, f.n_pre, c)
        assigned[lab] = dict(zip(map(sn._uid, f.keys), a))
        changes[lab] = {sn._uid(k): np.array([a[i], b[i]]) for i, k in enumerate(f.keys)}
    reach = {sn._uid(k): bool((np.vstack([x[i], up[i]]) > 0).any()) for i, k in enumerate(f.keys)}
    return f, x, sn.classify_by_cap(assigned, changes, reach, [], {})


def test_the_run_as_assigned_on_single_doses_equals_the_primary_fit():
    units, q, regions, dose, prices, usable = invented_world()
    f, x, cl = _world_classified(units, q, regions, dose, usable, upper_bump=0.0)
    s = sn.run_samples(f, cl)
    members = {lab: s[sn.RUN_AS_ASSIGNED][lab]["utilities"] for lab in LABS}
    a = sn.run_single_dose(members, f, cl, log_outcome(prices), np.random.default_rng(4), boot=99)
    b = sn.run(f, sn.dose_points(dose), log_outcome(prices), np.random.default_rng(4), boot=99)
    for lab in LABS:
        for k in ("est", "se", "lo", "hi"):
            assert abs(a[lab][k] - b[lab][k]) <= 1e-12, (lab, k)


def test_a_planted_slope_is_recovered_on_members_that_differ_by_form():
    """Each state's host carries 33 to 39 points after 2022 and none before; an invented upper case adds 40 points after.
    At 25 points both histories give a change of 25 (settled, in the settled run); at 50 points and uncapped they are
    more than two points apart and above zero (class 5, out of it). So the settled run's members differ by form.
    y's change = b * (change at that form) + a cell effect, noise free: each form recovers b to 1e-10."""
    units, q, regions, dose, prices, usable = invented_world(host_dose=0.30)
    f, x, cl = _world_classified(units, q, regions, dose, usable, upper_bump=40.0)
    s = sn.run_samples(f, cl)
    members = {lab: s[sn.RUN_SETTLED][lab]["utilities"] for lab in LABS}
    assert len({len(v) for v in members.values()}) > 1                       # the members differ between forms
    b = 0.004
    rng = np.random.default_rng(1)
    cell_eff = {c: rng.normal(0, 0.05) for c in np.unique(f.cell)}
    for lab in LABS:
        dx = np.array([cl[lab][sn._uid(k)]["dose"] for k in f.keys])
        dy = b * dx + np.array([cell_eff[c] for c in f.cell])
        out = q[sn.KEY + ["year"]].copy()
        out["log_price"] = 0.0
        post = out.year.isin(sn.POST)
        dmap = dict(zip(f.keys, dy))
        out.loc[post, "log_price"] = [dmap.get((u, st), 0.0) for u, st in zip(out.utility_id_eia[post], out.state[post])]
        r = sn.run_single_dose(members, f, cl, out, np.random.default_rng(2), boot=49)
        assert abs(r[lab]["est"] - b) <= TOL, (lab, r[lab]["est"])
        assert r[lab]["utilities"] == len(members[lab])


# ---- 7. the record of the proposal is not rewritten ------------------------------------------------------------------

def test_the_proposals_record_is_never_rewritten(monkeypatch):
    def no_write(self, *a, **k):
        raise AssertionError(f"something tried to write {self}")
    monkeypatch.setattr(Path, "write_text", no_write)
    assert sc.main() == 0
    with pytest.raises(sc.SupersededRecord):
        sc.summary()


# ---- 8. the checks above can fail: deliberate breaks in the test process --------------------------------------------

def test_the_planted_classes_check_can_fail(monkeypatch):
    monkeypatch.setattr(sn, "SETTLED_BELOW", 0.0)                       # no range is settled any more
    with pytest.raises(AssertionError):
        check_planted_classes()


def test_the_leverage_share_check_can_fail(monkeypatch):
    monkeypatch.setattr(sn, "NOT_SETTLED", sn.NOT_SETTLED + (sn.NO_ENDPOINT_EXPOSURE,))   # class 2 counted as not settled
    with pytest.raises(AssertionError):
        check_leverage_shares_by_hand()


def test_the_exclusion_check_can_fail(monkeypatch):
    real = sn.single_dose_without_assignment

    def follow_the_code(uid, lab, changes, established):              # decides from the histories, as Joe said not to
        c = sn.common_by_cap({lab: np.asarray(changes, dtype=float)})[lab]
        return (c, "taken from the histories", "x") if c is not None else real(uid, lab, changes, established)
    monkeypatch.setattr(sn, "single_dose_without_assignment", follow_the_code)
    with pytest.raises(AssertionError):
        check_exclusion_retained_without_a_finding()


# ---- 9. Joe's ruling of 2026-11-19 (D-107): the ruled scope, "settled" conditional, and the seed --------------------

def _scopes(narrow, wide):
    return {"rule_8_1_text": {"9:XX": narrow}, "place_test_wider_set": {"9:XX": wide}}


def test_the_summary_refuses_any_mapping_but_the_ruled_scope_before_reading_a_file(monkeypatch):
    """Planted: rule 8.1's histories establish 25.0, the wider set does not. The narrow scope's mapping, and an empty
    mapping where the ruled scope would establish a change, are refused in words; nothing is read (any read fails)."""
    from pipeline.analysis import common_dose_rule as cdr

    def no_read(*a, **k):
        raise AssertionError("a file was read before the mapping was checked")
    monkeypatch.setattr(pd, "read_parquet", no_read)
    est = {"established": True, "dose": 25.0, "why": "a"}
    not_est = {"established": False, "dose": None, "why": "b"}
    by_scope = _scopes({C25: est}, {C25: not_est})
    with pytest.raises(ValueError, match="established_as_ruled.*D-107"):
        sn.design_summary(by_scope["rule_8_1_text"], by_scope)            # the narrow scope's verdicts as the mapping
    by_scope2 = _scopes({C25: not_est}, {C25: est})
    with pytest.raises(ValueError, match="Another mapping is refused"):
        sn.design_summary({}, by_scope2)                                  # exclusion kept where the ruled scope establishes
    assert cdr.established_as_ruled(by_scope2)["9:XX"][C25]["dose"] == 25.0


def test_settled_is_conditional_on_the_modeled_histories():
    s = sn.SETTLED_IS_CONDITIONAL
    assert "rule 8.1's modeled histories with dates held at their conventions" in s and "D-107" in s
    assert "—" not in s                                               # no em dash in the plan's wording


def check_the_seed():
    assert sn.BOOTSTRAP_SEED == 20261205
    a = sn.bootstrap_rng().integers(0, 2**31, 8)
    b = np.random.default_rng(20261205).integers(0, 2**31, 8)
    assert (a == b).all()


def test_the_seed_is_20261205_and_is_the_default():
    check_the_seed()
    units, q, regions, dose, prices, usable = invented_world()
    f = sn.build_frame(units, q, regions, usable)
    x = sn.dose_matrix(sn.dose_points(dose), f.keys, f.years)
    y = sn.outcome_matrix(log_outcome(prices), f.keys, f.years)
    by_default = sn.fit(f, x, y, boot=49, caps=(25.0,))[C25]
    explicit = sn.fit(f, x, y, np.random.default_rng(20261205), boot=49, caps=(25.0,))[C25]
    assert by_default["lo"] == explicit["lo"] and by_default["hi"] == explicit["hi"]      # the same draws, exactly
    other = sn.fit(f, x, y, sn.bootstrap_rng(7, invented_inputs=True), boot=49, caps=(25.0,))[C25]
    assert (other["lo"], other["hi"]) != (by_default["lo"], by_default["hi"])


def test_another_seed_is_refused_for_a_research_run():
    with pytest.raises(ValueError, match="20261205.*refused for a research run"):
        sn.bootstrap_rng(5)
    with pytest.raises(TypeError):
        sn.bootstrap_rng("20261205")
    assert sn.bootstrap_rng(5, invented_inputs=True).integers(0, 9) == np.random.default_rng(5).integers(0, 9)


def test_the_seed_is_used_nowhere_else_in_pipeline_analysis():
    root = Path(__file__).resolve().parents[1] / "pipeline" / "analysis"
    users = sorted(p.name for p in root.glob("*.py") if "20261205" in p.read_text())
    assert users == ["second_number.py"], users


def test_the_seed_check_can_fail(monkeypatch):
    """A deliberate break in the test process: another default seed."""
    monkeypatch.setattr(sn, "BOOTSTRAP_SEED", 20261204)
    with pytest.raises(AssertionError):
        check_the_seed()
