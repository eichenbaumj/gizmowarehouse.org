"""The pass's tools read the frozen inventory of 2026-11-14, never the step D rebuild (pass_c_expand.frozen_frame_dir,
load_frozen). Invented folder trees only."""
import inspect
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.facilities import assignment as asg  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402


def tree(root: Path, rebuilt: bool, snapshot: bool) -> Path:
    interim = root / "interim"
    interim.mkdir()
    cols = {"fid": ["a"], "state": ["AA"]}
    if rebuilt:
        cols["date_rule"] = [None]
    pd.DataFrame(cols).to_parquet(interim / "facilities.parquet")
    if snapshot:
        snap = interim / px.SNAPSHOT_NAME
        snap.mkdir()
        for f in px.FROZEN_FRAME_FILES:
            pd.DataFrame({"x": [1]}).to_parquet(snap / f)
    return interim


def test_a_rebuilt_live_inventory_with_its_snapshot_reads_the_snapshot(tmp_path):
    interim = tree(tmp_path, rebuilt=True, snapshot=True)
    assert px.frozen_frame_dir(interim) == interim / px.SNAPSHOT_NAME


def test_a_rebuilt_live_inventory_without_its_snapshot_stops_in_words(tmp_path):
    interim = tree(tmp_path, rebuilt=True, snapshot=False)
    with pytest.raises(FileNotFoundError, match="apply_verified.py --no-pass-records") as e:
        px.frozen_frame_dir(interim)
    assert "build_inventory.py --no-step-d" in str(e.value) and "facilities.parquet" in str(e.value)


def test_a_rebuilt_live_inventory_with_a_partial_snapshot_stops(tmp_path):
    interim = tree(tmp_path, rebuilt=True, snapshot=True)
    (interim / px.SNAPSHOT_NAME / "epoch_gaps.parquet").unlink()
    with pytest.raises(FileNotFoundError, match="epoch_gaps.parquet"):
        px.frozen_frame_dir(interim)


def test_an_unrebuilt_live_inventory_is_read_as_before_even_with_a_snapshot_beside_it(tmp_path):
    interim = tree(tmp_path, rebuilt=False, snapshot=True)
    assert px.frozen_frame_dir(interim) == interim


def test_load_frozen_takes_every_frame_file_from_the_chosen_folder(tmp_path, monkeypatch):
    """The frame (facilities, site-years, dose, anchor, Epoch gaps) follows the switch; the sales side does not."""
    seen = {}

    def fake_inputs(frame_dir=None):
        seen["frame_dir"] = frame_dir
        raise RuntimeError("stop after recording")
    monkeypatch.setattr(px.asg, "load_inputs", fake_inputs)
    interim = tree(tmp_path, rebuilt=True, snapshot=True)
    with pytest.raises(RuntimeError, match="stop after recording"):
        px.load_frozen(interim)
    assert seen["frame_dir"] == interim / px.SNAPSHOT_NAME
    src = inspect.getsource(px.load_frozen)
    for f in ("facility_year.parquet", "state_anchor.parquet", "epoch_gaps.parquet"):
        assert f'frame / "{f}"' in src and f'INTERIM / "{f}"' not in src


def test_the_assignment_table_still_reads_the_live_inventory():
    assert inspect.signature(asg.load_inputs).parameters["frame_dir"].default is None
    src = inspect.getsource(asg.load_inputs)
    assert 'INTERIM / "panel_quantities.parquet"' in src                 # sales from the live folder always
    assert "load_inputs(frame_dir" not in inspect.getsource(asg.main)    # the table itself: the live (rebuilt) frame


def test_timing_reads_the_rebuild_not_the_snapshot():
    from pipeline.facilities import timing as tm
    src = inspect.getsource(tm.load_rebuilt)
    assert "asg.load_inputs()" in src and "load_frozen(" not in src and "frozen_frame_dir" not in src
