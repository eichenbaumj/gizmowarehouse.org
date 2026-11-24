"""The inventory's load rule and the state anchoring. Synthetic sites only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.facilities import build_inventory as bi  # noqa: E402

# An Epoch campus that Epoch's timeline shows at 100 MW in 2023, 150 in 2024 and 900 in 2025.
EPOCH_PATH = {("Big Campus", 2023): 100.0, ("Big Campus", 2024): 150.0, ("Big Campus", 2025): 900.0}


def test_epoch_site_follows_its_dated_timeline():
    assert bi.site_mw("epoch", "epoch:Big Campus", 2023, 900.0, 2022, EPOCH_PATH) == 0.0
    assert bi.site_mw("epoch", "epoch:Big Campus", 2023, 900.0, 2024, EPOCH_PATH) == 150.0
    assert bi.site_mw("epoch", "epoch:Big Campus", 2023, 900.0, 2025, EPOCH_PATH) == 900.0


def test_other_sites_ramp_to_full_load_over_three_years():
    assert bi.site_mw("bi", "bi:1-0", 2020, 60.0, 2019, {}) == 0.0
    assert bi.site_mw("bi", "bi:1-0", 2020, 60.0, 2020, {}) == pytest.approx(20.0)
    assert bi.site_mw("bi", "bi:1-0", 2020, 60.0, 2022, {}) == pytest.approx(60.0)
    assert bi.site_mw("bi", "bi:1-0", np.nan, 60.0, 2022, {}) == 0.0


def test_state_anchor_counts_an_epoch_site_at_its_2024_timeline_value():
    """The anchoring and the dose must use the same 2024 quantity for an Epoch site (D-26, D-27).

    Before the fix the anchoring took the campus at its present 900 MW on the generic ramp
    (two thirds of it in its second year: 600 MW, 5.3 TWh), which left nothing of EPRI's
    4 TWh for the permit-based sites and scaled them to the floor.
    """
    fac = pd.DataFrame({
        "fid": ["epoch:Big Campus", "bi:1-0", "bi:2-0"], "src": ["epoch", "bi", "bi"], "state": ["XX", "XX", "XX"],
        "energized_year": [2023.0, 2015.0, 2016.0], "mw_full": [900.0, 100.0, 100.0]})
    measured = fac.src == "epoch"
    epri = pd.Series({"XX": 4.0})
    t = bi.state_anchor(fac, measured, epri, EPOCH_PATH)
    assert t.loc["XX", "epoch_twh"] == pytest.approx(150.0 * 8.76 / 1000.0)
    assert t.loc["XX", "permit_twh"] == pytest.approx(200.0 * 8.76 / 1000.0)
    assert t.loc["XX", "raw_factor"] == pytest.approx((4.0 - 1.314) / 1.752)
    assert t.loc["XX", "flag"] == "ok"
    # and the dose's 2024 value for the same site is the same number
    assert bi.site_mw("epoch", "epoch:Big Campus", 2023.0, 900.0, 2024, EPOCH_PATH) * 8.76 / 1000.0 == pytest.approx(
        t.loc["XX", "epoch_twh"])


def test_state_anchor_leaves_measured_loads_unscaled_and_flags_thin_states():
    fac = pd.DataFrame({
        "fid": ["bi:1-0", "bi:2-0", "bi:3-0"], "src": ["bi", "bi", "bi"], "state": ["AA", "AA", "BB"],
        "energized_year": [2010.0, 2012.0, 2012.0], "mw_full": [100.0, 50.0, 10.0]})
    measured = pd.Series([True, False, False])          # the first site's load is a public figure
    t = bi.state_anchor(fac, measured, pd.Series({"AA": 2.0, "BB": 5.0}), {})
    assert t.loc["AA", "epoch_twh"] == pytest.approx(0.876)
    assert t.loc["AA", "factor"] == pytest.approx((2.0 - 0.876) / 0.438)
    assert t.loc["BB", "flag"] == "undercounted" and t.loc["BB", "factor"] == bi.SCALE_HI
