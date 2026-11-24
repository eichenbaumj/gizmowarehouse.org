"""The simulation's never-host access list (step-e rules section 9, ADOPTED, D-95), and the one reader of prices.

Invented inputs only. N5's history is read from a temporary git repository built in the test.
"""
from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.analysis import simulation_access_list as sal  # noqa: E402

YEARS = range(2001, 2026)
UNITS = list(range(10, 21))          # every one clean on the frame, in state AA


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    (root / "data" / "frozen").mkdir(parents=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.org")
    git(root, "config", "user.name", "test")
    return root


def commit(root, rel, text, msg):
    (root / rel).write_text(text)
    git(root, "add", rel)
    git(root, "commit", "-q", "-m", msg)
    return subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%H"], capture_output=True, text=True).stdout.strip()


HEADLINE_HEADER = "threshold,utility_id_eia,state,name\n"


def frozen_world(root: Path, lists=None):
    f = root / "data" / "frozen"
    (f / "dating_sensitivity.json").write_text(json.dumps({"thresholds": {"2%": {"dependent_utilities": []}, "5%": {"dependent_utilities": []}}}))
    (f / "buildout_sensitivity.json").write_text(json.dumps({"thresholds": {"2%": {"utilities_still_unsettled": []},
                                                                          "5%": {"utilities_still_unsettled": []}}}))
    lists = lists or {"does_not_keep_its_place": ["15:AA"], "unsettled_on_assignment_under_ruling_4": []}
    (f / "treatment_bounds.json").write_text(json.dumps({"thresholds": {t: {"lists": lists, "sets": {}} for t in ("2%", "5%")}}))
    pd.DataFrame([{"utility_id_eia": 12, "state": "AA", "max_share_a": 0.006, "clean_b": "True", "place_2%": "comparison",
                   "place_5%": "comparison", "lost_2%": "", "ruling_4_2%": "", "lost_5%": "", "ruling_4_5%": ""},
                  {"utility_id_eia": 13, "state": "AA", "max_share_a": 0.001, "clean_b": "True", "place_2%": "comparison",
                   "place_5%": "comparison", "lost_2%": "D-46: no anchoring", "ruling_4_2%": "", "lost_5%": "", "ruling_4_5%": ""}]
                 ).to_csv(f / "treatment_bounds_by_utility.csv", index=False)
    (f / "timing_place_test.json").write_text(json.dumps({"utilities": [
        {"utility": "14:AA", "theta": 0.02, "reference": {"place": "comparison"}, "keeps_its_place": None, "status": "unsettled"},
        {"utility": "10:AA", "theta": 0.02, "reference": {"place": "comparison"}, "keeps_its_place": True, "status": "keeps"}]}))
    return f


def quantities():
    q = pd.DataFrame([(u, "AA", y, f"Utility {u}") for u in UNITS for y in YEARS], columns=["utility_id_eia", "state", "year", "utility_name"])
    dose = pd.DataFrame([(u, "AA", 2015, 0.0, 0.0, 1000.0) for u in UNITS],
                        columns=["utility_id_eia", "state", "year", "dose", "crypto_mw", "base_retail_gwh"])
    return q, dose


def usable():
    return {(u, "AA", y) for u in UNITS for y in YEARS if u != 19} | {(19, "AA", y) for y in range(2001, 2006)}


def allow(tmp_path, rows=()):
    p = tmp_path / "allow.csv"
    pd.DataFrame(list(rows), columns=sal.ALLOW_COLUMNS).to_csv(p, index=False)
    return p


def hold(tmp_path):
    p = tmp_path / "hold.csv"
    p.write_text("utility_id_eia,state,name,why\n16,AA,Held,held until Gate 1\n")
    return p


@pytest.fixture
def world(tmp_path):
    root = repo(tmp_path)
    f = frozen_world(root)
    c1 = commit(root, "data/frozen/headline_set.csv", HEADLINE_HEADER + "2%,17,AA,Seventeen\n2%,18,AA,Eighteen\n", "v1: 17 and 18 hosts")
    commit(root, "data/frozen/headline_set.csv", HEADLINE_HEADER + "2%,99,BB,Elsewhere\n", "v2: they are gone")
    unknown = ps.UnknownLoad(frozenset({(11, "AA")}), {}, "invented", 1)
    return {"root": root, "frozen": f, "c1": c1, "unknown": unknown, "tmp": tmp_path}


def generate(w, allow_rows=(), exists=lambda k: k != (20, "AA"), unknown=None, set_files=sal.SET_FILES):
    q, dose = quantities()
    return sal.generate(q, dose, frozen=w["frozen"], root=w["root"], usable=usable(), unknown=unknown or w["unknown"], rebuilt=True,
                        allow_path=allow(w["tmp"], allow_rows), hold_path=hold(w["tmp"]), exists=exists, set_files=set_files)


# ---- N1 to N7 --------------------------------------------------------------------------------------------------------

def test_each_condition_excludes_with_its_first_failing_reason(world):
    listed, excluded = generate(world)
    why = dict(zip(zip(excluded.utility_id_eia, excluded.state), excluded.reason))
    assert why == {(11, "AA"): "load_unknown_D96", (12, "AA"): "N1_not_under_0.5pct_with_no_anchoring",
                   (13, "AA"): "N2_not_under_0.5pct_in_every_admissible_history",
                   (14, "AA"): "N2_not_under_0.5pct_in_every_admissible_history",
                   (15, "AA"): "N3_set_aside_or_on_a_bounds_list", (16, "AA"): "N4_price_hold",
                   (17, "AA"): "N5_former_host_without_an_allow_row", (18, "AA"): "N5_former_host_without_an_allow_row",
                   (19, "AA"): "N6_no_full_usable_window", (20, "AA"): "N7_no_per_unit_outcome_file"}
    assert list(zip(listed.utility_id_eia, listed.state)) == [(10, "AA")]
    assert set(listed.columns) == {"utility_id_eia", "state", "name"} and listed.name.iloc[0] == "Utility 10"


def test_a_former_host_is_found_in_a_committed_version_no_longer_on_disk_with_its_file_and_commit(world):
    _, excluded = generate(world)
    r = excluded.set_index(["utility_id_eia", "state"]).loc[(17, "AA")]
    assert r.n5_file == "data/frozen/headline_set.csv" and r.n5_commit == world["c1"]
    assert "17,AA" not in (world["root"] / "data/frozen/headline_set.csv").read_text()      # the file on disk no longer shows it


def test_an_allow_row_with_its_entry_and_quoted_words_lets_a_former_host_through(world):
    listed, _ = generate(world, allow_rows=[{"utility_id_eia": 18, "state": "AA", "ledger_entry": "D-99",
                                             "quoted_words": "18 may be read for the simulation"}])
    assert (18, "AA") in set(zip(listed.utility_id_eia, listed.state)) and (17, "AA") not in set(zip(listed.utility_id_eia, listed.state))


def test_an_allow_row_without_its_quoted_words_stops(world):
    with pytest.raises(sal.AccessListError, match="quoted words"):
        generate(world, allow_rows=[{"utility_id_eia": 18, "state": "AA", "ledger_entry": "D-99", "quoted_words": ""}])


def test_the_committed_allow_file_starts_with_a_header_and_no_rows():
    assert sal.ALLOW_PATH.read_text() == ",".join(sal.ALLOW_COLUMNS) + "\n" and sal.load_allow() == {}


def test_hosts_are_read_from_every_kind_of_set_file():
    tb = json.dumps({"thresholds": {"2%": {"sets": {"headline_set": {"left": [{"utility": "1:AA"}], "lost": [{"utility": "2:AA"}]}},
                                           "early_hosts": {"do_not": [{"utility": "3:AA"}]},
                                           "comparison_utilities": {"do_not": [{"utility": "4:AA"}]},
                                           "lists": {"does_not_keep_its_place": ["5:AA"]}}}})
    assert sal.host_keys_in("data/frozen/treatment_bounds.json", tb) == {(1, "AA"), (2, "AA"), (3, "AA")}
    csv = "utility_id_eia,state,place_2%,place_5%\n1,AA,comparison,late\n2,AA,neither,comparison\n3,AA,early,cohort\n4,AA,comparison,outside_cohorts\n"
    assert sal.host_keys_in("data/frozen/treatment_bounds_by_utility.csv", csv) == {(1, "AA"), (3, "AA"), (4, "AA")}
    with pytest.raises(sal.AccessListError, match="N5 cannot be established"):
        sal.host_keys_in("data/frozen/treatment_bounds_by_utility.csv", "utility_id_eia,state,place_2%\n1,AA,mystery\n")
    ps_json = json.dumps({"new_host_estimate": {"2%": {"headline_set": {"hosts_not_given_a_stand_in": [{"utility": "7:AA"}],
                                                                          "draws": 3}}}, "seed": 1})
    assert sal.host_keys_in("data/frozen/power_simulation.json", ps_json) == {(7, "AA")}


def test_a_path_that_is_not_a_repository_stops_n5(tmp_path):
    (tmp_path / "data" / "frozen").mkdir(parents=True)
    with pytest.raises(sal.AccessListError, match="git log"):
        sal.former_hosts(tmp_path, ("data/frozen/headline_set.csv",))


def test_the_outcome_file_is_checked_by_path_only():
    src = inspect.getsource(sal.outcome_file_exists)
    assert "os.path.exists(panel.unit_file(" in src and "read" not in src.split('"""')[2] and "listdir" not in src


# ---- the files it writes ---------------------------------------------------------------------------------------------

def test_write_records_the_hash_and_a_changed_list_is_refused(world, tmp_path):
    listed, excluded = generate(world)
    paths = {"list_path": tmp_path / "list.csv", "excluded_path": tmp_path / "ex.csv", "hash_path": tmp_path / "list.sha256"}
    h = sal.write(listed, excluded, **paths)
    assert paths["hash_path"].read_text() == f"{h}  list.csv\n"
    assert sal.verified_list(paths["list_path"], paths["hash_path"]) == {(10, "AA")}
    paths["list_path"].write_text(paths["list_path"].read_text() + "11,AA,Eleven\n")
    with pytest.raises(sal.AccessListError, match="does not match"):
        sal.verified_list(paths["list_path"], paths["hash_path"])
    paths["hash_path"].unlink()
    with pytest.raises(sal.AccessListError, match="missing"):
        sal.verified_list(paths["list_path"], paths["hash_path"])


def test_main_prints_counts_by_reason_only(world, monkeypatch, capsys, tmp_path):
    from pipeline.analysis import design, usable_flag
    q, dose = quantities()
    monkeypatch.setattr(sal, "FROZEN", world["frozen"])
    monkeypatch.setattr(sal, "ROOT", world["root"])
    for name, p in (("LIST_PATH", tmp_path / "l.csv"), ("EXCLUDED_PATH", tmp_path / "e.csv"), ("HASH_PATH", tmp_path / "l.sha256")):
        monkeypatch.setattr(sal, name, p)
    monkeypatch.setattr(sal, "outcome_file_exists", lambda k: True)
    monkeypatch.setattr(sal, "ALLOW_PATH", allow(tmp_path))
    monkeypatch.setattr(ps, "PRICE_HOLD", hold(tmp_path))
    monkeypatch.setattr(ps, "rebuilt_inventory", lambda interim=None: True)
    monkeypatch.setattr(ps, "load_unknown_load", lambda *a, **k: world["unknown"])
    monkeypatch.setattr(design, "load", lambda: (q, dose, None, None, None))
    monkeypatch.setattr(usable_flag, "read", lambda path=None: usable_flag.Flags(usable=usable(), reason={}, rows=0))
    assert sal.main() == 0
    out = capsys.readouterr().out.strip().split("\n")
    assert out[0] == sal.DESCRIPTION                                    # the rule in words (Stop 3), then counts only
    out = out[1:]
    assert out[0] == "listed: 2" and out[-1].startswith("sha256 of l.csv: ")
    assert all(line.startswith("excluded, ") for line in out[1:-1]) and len(out) == len(sal.REASONS) + 2
    assert "Utility" not in "\n".join(out)                              # counts only: no names


# ---- the one reader ----------------------------------------------------------------------------------------------------

@pytest.fixture
def listed(tmp_path):
    lp, hp = tmp_path / "list.csv", tmp_path / "list.sha256"
    sal.write(pd.DataFrame({"utility_id_eia": [10, 11, 12], "state": ["AA"] * 3, "name": ["a", "b", "c"]}),
              pd.DataFrame(columns=["utility_id_eia", "state", "name", "reason"]), lp, tmp_path / "ex.csv", hp)
    return lp, hp


def test_the_reader_passes_exactly_the_requested_listed_units_and_never_widens(listed, monkeypatch):
    seen = []
    monkeypatch.setattr(ps.panel, "load_outcomes", lambda *, purpose, units: seen.append((purpose, units.copy())) or units)
    ps.read_listed_outcomes(pd.DataFrame({"utility_id_eia": [11, 11], "state": ["AA", "AA"]}), *listed)
    purpose, units = seen[0]
    assert purpose == "power_simulation" and list(zip(units.utility_id_eia, units.state)) == [(11, "AA")]


def test_the_reader_refuses_a_unit_off_the_list_naming_how_many(listed, monkeypatch):
    monkeypatch.setattr(ps.panel, "load_outcomes", lambda **k: pytest.fail("no price may be read"))
    with pytest.raises(PermissionError, match=r"2 requested units are not on the simulation's access list \(first: 13:AA, 14:AA\)"):
        ps.read_listed_outcomes(pd.DataFrame({"utility_id_eia": [10, 13, 14], "state": ["AA"] * 3}), *listed)


def test_the_reader_refuses_a_changed_list_or_a_missing_hash(listed, monkeypatch):
    monkeypatch.setattr(ps.panel, "load_outcomes", lambda **k: pytest.fail("no price may be read"))
    lp, hp = listed
    lp.write_text(lp.read_text() + "13,AA,d\n")
    with pytest.raises(sal.AccessListError, match="does not match"):
        ps.read_listed_outcomes(pd.DataFrame({"utility_id_eia": [10], "state": ["AA"]}), lp, hp)
    hp.unlink()
    with pytest.raises(sal.AccessListError, match="missing"):
        ps.read_listed_outcomes(pd.DataFrame({"utility_id_eia": [10], "state": ["AA"]}), lp, hp)


def test_restrict_keeps_only_listed_comparisons(listed):
    clean = pd.DataFrame({"utility_id_eia": [10, 12, 13], "state": ["AA"] * 3})
    kept, off = ps.restrict_to_access_list(clean, *listed)
    assert list(kept.utility_id_eia) == [10, 12] and off == 1


def test_every_price_read_goes_through_the_one_reader_and_the_inference_check_reads_none():
    src = Path(ps.__file__).read_text()
    code = [ln for ln in src.split("\n") if "panel.load_outcomes(" in ln and not ln.lstrip().startswith(("#", "(", "(c)"))]
    assert len(code) == 1 and "return panel.load_outcomes" in code[0]
    assert "read_listed_outcomes(clean)" in inspect.getsource(ps.main) and "read_listed_outcomes(clean)" in inspect.getsource(ps.run_added)
    assert "restrict_to_access_list(clean)" in inspect.getsource(ps.main)
    ic_src = Path(ic.__file__).read_text()
    assert "load_outcomes" not in ic_src and "read_listed_outcomes" not in ic_src
