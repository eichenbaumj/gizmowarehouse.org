"""What the customer-weighted fit's two shares measure (pipeline/analysis/weighted_fit.py, NOMINAL_DEFINITION and
EFFECTIVE_DEFINITION), on invented quantities and invented outcomes only. No file under data/ is read.

Joe, 2026-11-19: "For customer-weighted shares, retain the calculations and clarify exactly what 'effective contribution'
measures. No influence analysis is requested." The leave-one-out refits below are made on invented outcomes inside the
test, only to show that the effective contribution is not an influence measure; no influence analysis is run on real data.

The invented world is tests/test_outcome_analysis_invented.py's (four hosts, forty comparison utilities, gas-share
control). Planted answers:
- The effective contributions add to 1 over the stacked hosts under any positive customer weights (tolerance 1e-10), and
  the nominal shares add to 1.
- Raising every outcome on one host's own rows in event years 2 and 3 by c moves the weighted headline by exactly c times
  that host's effective contribution (tolerance 1e-10), the definition's "in exact terms" sentence.
- A planted world in which the hosts ranked by effective contribution and ranked by the size of the leave-one-out change
  in the weighted estimate come out in different orders, while the effective contributions are the same in two outcome
  worlds whose leave-one-out rankings differ.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import influence  # noqa: E402
from pipeline.analysis import outcome_analysis as oa  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import weighted_fit as wf  # noqa: E402
from test_outcome_analysis_invented import make  # noqa: E402
from test_weighted_fit_invented import customers_frame, outcome  # noqa: E402

TOL = 1e-10


@pytest.fixture(scope="module")
def built():
    return make()


def weights_of(d, q):
    return wf.customer_weights(d, customers_frame(q))


# ---- the shares add to one -------------------------------------------------------------------------------------------

def check_sums(d, w):
    eff = wf.effective_contributions(d, w)["by_host"]
    assert abs(sum(eff.values()) - 1.0) < TOL
    assert abs(sum(wf.nominal_shares(w).values()) - 1.0) < TOL


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_the_shares_sum_to_one_under_any_positive_weights(built, seed):
    d, q, regions, dd = built
    rng = np.random.default_rng(seed)
    w = {oa._host_label(k): float(v) for k, v in zip(d.hosts.key, rng.uniform(1.0, 1e6, len(d.hosts)))}
    check_sums(d, w)


def test_the_sum_check_fails_when_the_per_host_sum_is_not_omega(built, monkeypatch):
    """A deliberate break in the test process: each host's sum taken over |omega|. The shares no longer add to one."""
    d, q, regions, dd = built
    real = wf._per_host
    monkeypatch.setattr(wf, "_per_host", lambda rows, omega: real(rows, np.abs(omega) * 1.5))
    with pytest.raises(AssertionError):
        check_sums(d, weights_of(d, q))


# ---- what it measures, in exact terms --------------------------------------------------------------------------------

def test_raising_a_hosts_own_headline_rows_by_c_moves_the_weighted_headline_by_c_times_its_share(built):
    d, q, regions, dd = built
    w = weights_of(d, q)
    eff = wf.effective_contributions(d, w)["by_host"]
    rows = oa.stacked_rows(d)
    y = np.asarray(oa.outcome_vector(d, outcome(dd, noise=0.01), "value"), dtype=float)
    base = wf.weighted_fit(d, y, w)["estimate_log_points"]
    label = rows.block_host_id.astype(int).astype(str) + ":" + rows.block_host_state.astype(str)
    c = 0.37
    for h in eff:
        own = (rows.is_host & rows.event_year.isin(list(ps.HEADLINE)) & (label == h)).to_numpy()
        assert own.sum() == 2
        moved = wf.weighted_fit(d, y + c * own, w)["estimate_log_points"]
        assert abs((moved - base) - c * eff[h]) < TOL, h


# ---- it is not an influence measure ----------------------------------------------------------------------------------

def leave_one_out(d, q, dd, levels):
    """{host: weighted estimate with every host - weighted estimate without that host's sub-experiment}, on invented
    outcomes with host h's own level in event years 2 and 3 (no noise)."""
    w = weights_of(d, q)
    frame = outcome(dd, levels=levels)
    full = wf.weighted_fit(d, oa.outcome_vector(d, frame, "value"), w)["estimate_log_points"]
    out = {}
    for h in w:
        keep = np.array([oa._host_label(k) != h for k in d.hosts.key])
        e = influence._without(d, keep)
        r = wf.weighted_fit(e, oa.outcome_vector(e, frame, "value"), {k: v for k, v in w.items() if k != h})
        assert r["estimated"], r["failure_in_words"]
        out[h] = full - r["estimate_log_points"]
    return out


def order(values: dict) -> list:
    return sorted(values, key=lambda h: (-values[h], h))


# Levels in event years 2 and 3. World A puts the extreme level on the host with the SMALLEST effective contribution; world
# B puts it on the host with the LARGEST. The effective contributions do not depend on these levels at all.
LEVELS_A = {(1, "AA"): 0.90, (2, "AC"): 0.02, (3, "BA"): 0.02, (4, "BC"): 0.02}
LEVELS_B = {(1, "AA"): 0.02, (2, "AC"): 0.02, (3, "BA"): 0.02, (4, "BC"): 0.90}


def check_not_influence(d, q, dd):
    w = weights_of(d, q)
    eff = wf.effective_contributions(d, w)["by_host"]          # computed before any outcome exists
    by_share = order(eff)
    assert by_share[-1] == "1:AA" and by_share[0] == "4:BC"   # the planted customers make 1:AA the smallest, 4:BC the largest
    loo_a = leave_one_out(d, q, dd, LEVELS_A)
    loo_b = leave_one_out(d, q, dd, LEVELS_B)
    size_a = order({h: abs(v) for h, v in loo_a.items()})
    size_b = order({h: abs(v) for h, v in loo_b.items()})
    # In world A the host with the smallest share moves the estimate most when left out: the two rankings differ.
    assert size_a[0] == "1:AA" and size_a != by_share
    # The same shares, two outcome worlds, two different leave-one-out rankings.
    assert size_a != size_b
    assert wf.effective_contributions(d, w)["by_host"] == eff
    return eff, loo_a, loo_b


def test_a_planted_world_where_the_share_and_a_leave_one_out_change_rank_hosts_differently(built):
    d, q, regions, dd = built
    check_not_influence(d, q, dd)


def test_the_influence_check_fails_if_the_share_were_the_leave_one_out_change(built, monkeypatch):
    """A deliberate break in the test process: effective_contributions made to return world A's leave-one-out changes.
    The shares would then rank hosts as the leave-one-out change does, and the check fails."""
    d, q, regions, dd = built
    loo = leave_one_out(d, q, dd, LEVELS_A)
    real = wf.effective_contributions

    def fake(d_, w_, fuel_control=None):
        r = real(d_, w_, fuel_control)
        if len(d_.hosts) == len(d.hosts):
            r["by_host"] = {h: abs(v) for h, v in loo.items()}
        return r
    monkeypatch.setattr(wf, "effective_contributions", fake)
    with pytest.raises(AssertionError):
        check_not_influence(d, q, dd)


# ---- the definition text ---------------------------------------------------------------------------------------------

EFFECTIVE_MUST_SAY = (
    "sum of omega over that host's own rows in event years 2 and 3",
    "add to exactly 1",
    "share of the weighted headline's total weight on host rows in event years 2 and 3",
    "rose by the same amount c",
    "computed from the design's regressors, its fixed effects and the customer weights alone",
    "not a measure of statistical influence on the estimate",
    "not leverage",
    "not how far the estimate would move if the host were left out",
    "supersedes the earlier phrase 'effective regression contributions'",
    "was accepted by Joe on 2026-11-19 (D-111)",
)
NOMINAL_MUST_SAY = ("residential customers in its reference year", "computed from the customer counts alone",
                    "not a measure of statistical influence", "not leverage", "not how far the estimate would move without the host")


def check_definitions(doc):
    for p in EFFECTIVE_MUST_SAY:
        assert p in doc["effective_definition"], p
    for p in NOMINAL_MUST_SAY:
        assert p in doc["nominal_definition"], p
    assert doc["effective_label"] == wf.EFFECTIVE_LABEL and doc["nominal_label"] == wf.NOMINAL_LABEL
    for text in (doc["effective_definition"], doc["nominal_definition"], doc["effective_label"], doc["nominal_label"]):
        assert "—" not in text


def test_the_definition_text_is_in_the_summary_and_in_every_result(built):
    d, q, regions, dd = built
    w = weights_of(d, q)
    doc = wf.summary_hosts(d, w)
    check_definitions(doc)
    assert abs(doc["sums"]["effective_weighted"] - 1.0) < TOL and abs(doc["sums"]["nominal"] - 1.0) < TOL
    assert [x["host"] for x in doc["hosts"]] == ["4:BC", "3:BA", "2:AC", "1:AA"]          # largest nominal share first
    r = wf.weighted_fit(d, oa.outcome_vector(d, outcome(dd), "value"), w)
    check_definitions(r)


def test_the_definition_check_fails_without_the_supersession_sentence(built, monkeypatch):
    """A deliberate break in the test process: the definition constant cut before its last sentence."""
    d, q, regions, dd = built
    monkeypatch.setattr(wf, "EFFECTIVE_DEFINITION", wf.EFFECTIVE_DEFINITION.split(" This definition supersedes")[0])
    with pytest.raises(AssertionError):
        check_definitions(wf.summary_hosts(d, weights_of(d, q)))


def test_the_definition_is_marked_accepted_and_no_longer_a_reading():
    """D-111 item 6: the effective-contribution definition, its label and what is summed are Joe's, not a reading."""
    assert "agent's reading" not in wf.EFFECTIVE_DEFINITION and "session's reading" not in wf.EFFECTIVE_DEFINITION
    assert "accepted by Joe on 2026-11-19 (D-111)" in " ".join(wf.__doc__.split())
    assert wf.EFFECTIVE_LABEL.startswith("own-row headline weight")


def test_the_acceptance_check_fails_on_the_old_mark(built, monkeypatch):
    """A deliberate break in the test process: the reading mark of session 20 put back in place of the acceptance."""
    d, q, regions, dd = built
    monkeypatch.setattr(wf, "EFFECTIVE_DEFINITION", wf.EFFECTIVE_DEFINITION.replace(
        "read from 'the implied weight on its own treated rows', was accepted by Joe on 2026-11-19 (D-111) with this "
        "definition", "is the agent's reading (session 20) of 'the implied weight on its own treated rows'"))
    with pytest.raises(AssertionError):
        check_definitions(wf.summary_hosts(d, weights_of(d, q)))
    with pytest.raises(AssertionError):
        test_the_definition_is_marked_accepted_and_no_longer_a_reading()
