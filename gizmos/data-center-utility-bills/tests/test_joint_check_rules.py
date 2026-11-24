"""Rule 6.4 from step D: the joint check by host reads the design built under the headline rules (ownership table,
usable flag, support rule). Invented quantities only."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.facilities import joint_check as jc  # noqa: E402
from test_matching_rules import COOP, FUEL, IOU, YEARS, ladder, table, world  # noqa: E402

GAS = {"AA": 0.10, "AB": 0.30, "BB": 0.60, "BC": 0.80}


def scene():
    host = (1, "AA", 10_000, IOU)
    comps = [(40, "AA", 10_005, IOU), (41, "AA", 10_010, COOP)] + ladder(60, 12, own=COOP)
    treated, clean, q, regions, dd = world([host], comps)
    t = table([{"utility_id_eia": 1, "state": "AA", "ultimate_parent": "P", "from_year": 2001, "to_year": 2025}])
    usable = {(u, st, y) for u, st, *_ in [host] + comps for y in YEARS} - {(41, "AA", 2012)}
    units = [(u, st) for u, st, *_ in [host] + comps]
    yrs = [y for y in YEARS if y <= jc.LAST]
    d = pd.DataFrame(np.inf, index=pd.MultiIndex.from_tuples(units), columns=yrs)
    d.loc[[(40, "AA"), (41, "AA")], :] = 1.0                       # the two ruled-out ones are the cheapest to tip
    ok = d.notna() & np.isfinite(d)
    return treated, clean, q, regions, dd, t, usable, d, ok


def test_a_comparison_ruled_out_by_ownership_or_the_usable_flag_is_not_among_a_hosts_matches():
    treated, clean, q, regions, dd, t, usable, d, ok = scene()
    dsg = jc.headline_design(treated, clean, q, regions, FUEL, dd, ownership=t, usable=usable, gas=GAS,
                             unknown_load=ps.UnknownLoad.none("invented data"))
    hosts, rows = jc.host_results(dsg, d, ok, {"AA": 1e9}, pd.Series(dtype=object))
    assert list(hosts) == ["1:AA"]
    keys = [tuple(k) for k in dsg.hosts.match_keys.iloc[0]]
    assert (40, "AA") not in keys and (41, "AA") not in keys and len(keys) == 10
    assert hosts["1:AA"]["could_fail_somewhere_in_its_window_within_the_remainders"] == 0
    assert hosts["1:AA"]["clean_left_in_the_worst_case"] == 10


def test_the_bare_design_would_have_counted_them():
    from pipeline.analysis import design
    treated, clean, q, regions, dd, t, usable, d, ok = scene()
    bare = design.build(treated, clean, q, regions, FUEL, dd)
    hosts, _ = jc.host_results(bare, d, ok, {"AA": 1e9}, pd.Series(dtype=object))
    assert hosts["1:AA"]["could_fail_somewhere_in_its_window_within_the_remainders"] == 2


def test_main_builds_through_the_rules():
    import inspect
    src = inspect.getsource(jc.main)
    assert "headline_design(" in src and "design.build(" not in src
    assert "build_with_rules(" in inspect.getsource(jc.headline_design)


def test_a_comparison_whose_load_the_frame_cannot_settle_is_not_a_match():
    treated, clean, q, regions, dd, t, usable, d, ok = scene()
    d.loc[(60, "AA"), :] = 1.0
    unk = ps.UnknownLoad(frozenset({(60, "AA")}), {}, "invented", 1)
    dsg = jc.headline_design(treated, clean, q, regions, FUEL, dd, ownership=t, usable=usable, gas=GAS, unknown_load=unk)
    keys = [tuple(k) for k in dsg.hosts.match_keys.iloc[0]]
    assert (60, "AA") not in keys
    hosts, _ = jc.host_results(dsg, d, ok, {"AA": 1e9}, pd.Series(dtype=object))
    assert hosts["1:AA"]["could_fail_somewhere_in_its_window_within_the_remainders"] == 0
