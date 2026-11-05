"""pytest for the hoyt-schermerhorn pipeline: classifier fixture, lattice geometry, words helper."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import config  # noqa: E402
from lib import classify, geo  # noqa: E402
from lib.words import share_words, times_words  # noqa: E402

FIX = pd.read_csv(HERE / "fixtures" / "classify_rows.csv", dtype=str).fillna("")


def test_classify_fixture():
    got = classify.classify_frame(FIX)
    bad = FIX[got.values != FIX["expected_class"].values]
    assert bad.empty, bad[["ky_cd", "pd_desc", "prem_typ_desc", "expected_class"]].assign(got=got[bad.index])


def test_zone_fixture():
    at = FIX["at_courthouse"] == "1"
    got = classify.zone_frame(FIX, at)
    bad = FIX[got.values != FIX["expected_zone"].values]
    assert bad.empty, bad[["juris_desc", "prem_typ_desc", "expected_zone"]].assign(got=got[bad.index])


def test_cell_edges_and_half_open():
    e = geo.cell_edges(config.CELL_ID)
    for k in e:
        assert abs(e[k] - config.CELL_EDGES[k]) < 1e-7
    ids, off = geo.assign_cells(np.array([e["west"], e["east"], e["west"], e["east"] - 1e-9]), np.array([e["south"], e["south"], e["north"], e["north"] - 1e-9]))
    assert ids[0] == config.CELL_ID and ids[3] == config.CELL_ID
    assert ids[1] != config.CELL_ID and ids[2] != config.CELL_ID
    assert not off.any()


def test_station_and_courthouse_in_cell():
    ids, _ = geo.assign_cells(np.array([config.STATION_LON, config.COURTHOUSE_LON]), np.array([config.STATION_LAT, config.COURTHOUSE_LAT]))
    assert list(ids) == [config.CELL_ID, config.CELL_ID]


def test_times_square_anchor():
    ids, _ = geo.assign_cells(np.array([config.HUB_ANCHORS["Times Square / Port Authority"][1]]), np.array([config.HUB_ANCHORS["Times Square / Port Authority"][0]]))
    assert ids[0] == config.TIMES_SQUARE_CELL


def test_haversine():
    d = geo.haversine_m(40.6885, -73.9850, 40.6885 + 0.009, -73.9850)
    assert 990 < float(d) < 1010


@pytest.mark.parametrize("r,words", [(1.0, "about the same"), (1.05, "about the same"), (1.23, "about 23 percent higher"), (0.71, "about 29 percent lower"), (2.604, "about 2.5 times"), (3.17, "about 3 times"), (3.97, "about 4 times")])
def test_times_words(r, words):
    assert times_words(r) == words


def test_share_words():
    assert share_words(0.224) == "22 percent"
