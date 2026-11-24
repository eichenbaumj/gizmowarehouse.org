"""Step D: the date screen recomputes the state's factor in every case (D-58 rule 1.7, last point). Made-up inputs."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stepd_world as W  # noqa: E402
from pipeline.facilities import dating_sensitivity as ds  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402


def world():
    """AA: a permit site 'late' of 30 MW from 2023 on utility 2 (its 2024 load is 2/3 of full), and 'x' of 9 MW from 2010
    on utility 1, whose 2% threshold is 10 MW. EPRI is set so the factor is 1 as built."""
    sites = [{"fid": "late", "state": "AA", "mw": 30, "year": 2023, "utility": 2},
             {"fid": "x", "state": "AA", "mw": 9, "year": 2010, "utility": 1}]
    epri = {"AA": (20 + 9) * 8.76 / 1000}
    inp = W.make(sites, {(1, "AA"): 10.0, (2, "AA"): 1000.0}, epri=epri)
    fac = inp.fac.assign(is_crypto=False)
    fy = inp.fy.assign(crypto=False)
    base = inp.base
    return fac, fy, inp.anchor, base


def test_held_reproduces_the_screen_as_first_written():
    fac, fy, anchor, base = world()
    und = fac.loc[["late"]]
    years = range(2001, 2026)
    held = ds.crossings(ds.shifted_rows(fac, fy, anchor, und, years, -3, recompute=False), base, 0.02)
    where = fy[fy.fid.isin(und.index)].drop_duplicates("fid").set_index("fid")[ds.KEY]
    rest = fy[~fy.fid.isin(und.index)][ds.KEY + ["year", "mw"]]
    old = ds.first_crossings(rest, und, where, base, years, 0.02, -3)
    pd.testing.assert_series_equal(held.sort_index(), old.sort_index(), check_names=False)


def test_starting_a_2023_site_earlier_lowers_the_factor_on_every_other_site():
    fac, fy, anchor, base = world()
    f = ds.factor_after_shift(fac, fy, anchor, ["late"], -3)
    assert f["AA"] < float(anchor.factor["AA"])
    rows = ds.shifted_rows(fac, fy, anchor, fac.loc[["late"]], range(2001, 2026), -3, recompute=True)
    x24 = rows[(rows.utility_id_eia == 1) & (rows.year == 2024)].mw.sum()
    assert x24 < 9.0 * float(anchor.factor["AA"])


def test_starting_it_later_raises_the_factor_and_can_move_another_utility():
    fac, fy, anchor, base = world()
    years = range(2001, 2026)
    # Later by 3: the late site carries nothing in 2024, the factor rises to the band edge and x crosses 10 MW.
    rec = ds.crossings(ds.shifted_rows(fac, fy, anchor, fac.loc[["late"]], years, 3, recompute=True), base, 0.02)
    held = ds.crossings(ds.shifted_rows(fac, fy, anchor, fac.loc[["late"]], years, 3, recompute=False), base, 0.02)
    assert (1, "AA") in rec.index and (1, "AA") not in held.index
