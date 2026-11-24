"""The command that would use the mask (pipeline/analysis/run_availability_screen.py), on an invented tree only.

Every path the command reads or writes under data/ is pointed at a made-up folder, the inventory is the made-up state of
tests/test_availability_adapter.py, and the ledger is a made-up file. The real ledger is read once, to show that no entry
in it lets the command start. Nothing under the project's data/ is opened, and the real mask is not read, listed or hashed.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline.analysis import run_availability_screen as rs  # noqa: E402
from pipeline.electricity import availability_codes as av  # noqa: E402
from pipeline.facilities import pass_c_exact  # noqa: E402
from pipeline.facilities import pass_c_expand as px  # noqa: E402
from test_availability_adapter import ZZ_CORRECTIONS, ZZ_POOL, ZZ_UNITS, all_years, mask_of, zz  # noqa: E402

ENTRY = "D-900"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A made-up tree: a ledger whose one entry carries the pin block for the code as it is, a mask in which utility 12
    fails every window, its sidecar, a pool, a corrections file and a headline file."""
    out_dir = tmp_path / "data" / "interim" / "availability"
    out_dir.mkdir(parents=True)
    mask = mask_of(ZZ_UNITS, all_years((12, "ZZ")))
    # The three columns the command must not parse are present and filled with text that would break a numeric parse.
    for c in ("first_exclusion_reason", "imputation_status", "supplier_rows_imputation_status"):
        mask[c] = "made-up"
    mask_bytes = mask.to_csv(index=False).encode()
    (out_dir / "outcome_availability.csv").write_bytes(mask_bytes)
    side = {"status": av.COMPLETED, "definition_version": av.DEFINITION_VERSION, "mask_sha256": sha(mask_bytes),
            "rows": len(mask), "run_id": "1" * 32, "attempt_id": "2" * 32}
    (out_dir / "outcome_availability.json").write_text(json.dumps(side))
    corrections = json.dumps(ZZ_CORRECTIONS).encode()
    (tmp_path / "corrections.json").write_bytes(corrections)
    pool = pd.DataFrame(ZZ_POOL, columns=["utility_id_eia", "state"]).to_csv(index=False).encode()
    (tmp_path / "pool.csv").write_bytes(pool)
    (tmp_path / "headline_set.csv").write_text("made-up\n1\n")
    ledger = tmp_path / "DECISIONS.md"
    ledger.write_text(f"## D-899. Something else\n\nNothing here.\n\n## {ENTRY}. A made-up instruction for the availability "
                      f"screen\n\nWords.\n\n```\n{rs.pin_block()}\n```\n\nMore words.\n")
    monkeypatch.setattr(rs, "LEDGER", ledger)
    monkeypatch.setattr(rs, "OUT_DIR", out_dir)
    monkeypatch.setattr(rs, "MASK", out_dir / "outcome_availability.csv")
    monkeypatch.setattr(rs, "SIDECAR", out_dir / "outcome_availability.json")
    monkeypatch.setattr(rs, "HEADLINE", tmp_path / "headline_set.csv")
    monkeypatch.setattr(rs, "HOSTS_EXPECTED", 1)
    monkeypatch.setattr(pass_c_exact, "hosts_from_headline", lambda head: [(14, "ZZ")])
    monkeypatch.setattr(px, "load_frozen", zz)
    args = {"authorized-by": ENTRY, "corrections": str(tmp_path / "corrections.json"), "corrections-sha256": sha(corrections),
            "pool": str(tmp_path / "pool.csv"), "pool-sha256": sha(pool), "mask-sha256": sha(mask_bytes), "states": "ZZ",
            "out": str(out_dir / "screen.json")}
    return {"tmp": tmp_path, "out_dir": out_dir, "ledger": ledger, "args": args, "side": side, "mask_bytes": mask_bytes}


def call(tree, capsys, **change):
    a = {**tree["args"], **change}
    code = rs.main([x for k, v in a.items() if v is not None for x in (f"--{k}", v)])
    return code, capsys.readouterr().out.splitlines()


def refused(tree, capsys, match, code=2, **change):
    before = sorted(p.name for p in tree["out_dir"].iterdir())
    got, lines = call(tree, capsys, **change)
    assert got == code and lines[-1] == "wrote nothing" and re.search(match, lines[0]), lines
    assert sorted(p.name for p in tree["out_dir"].iterdir()) == before          # nothing written, no temporary file left


def test_with_a_pinned_entry_it_writes_one_record_and_prints_counts_only(tree, capsys):
    code, lines = call(tree, capsys)
    assert code == 0, lines
    assert len(lines) == 6 and lines[0] == f"availability screen, rule 2026-11-18.1, under {ENTRY}"
    assert lines[1] == f"mask: run {'1' * 32} | audit attempt {'2' * 32} | definition {av.DEFINITION_VERSION} | {tree['args']['mask-sha256']}"
    assert lines[2] == "states covered 1 of 1 named | pool 4 | listed hosts 1 | protected 1 | narrowed 1"
    assert lines[3] == ("questions: deferrable 1 | retained 3 | moves the state's anchoring 1 | "
                        "reaches a utility that is not narrowed 2")
    assert lines[4].startswith("fingerprints: corrections ") and lines[5] == "wrote: data/interim/availability/screen.json"
    # No utility, site or flag is printed: no unit key, no question id.
    text = "\n".join(lines)
    assert not re.search(r"\b\d+:ZZ\b", text) and "passes" not in text
    assert not any(qid in text for qid in ("d date", "e date", "x assignment", "y assignment"))
    record = json.loads((tree["out_dir"] / "screen.json").read_text())
    assert record["deferrable"] == ["d date"] and record["narrowed"] == ["12:ZZ"]
    assert record["protected"] == {"14:ZZ": "a listed host"} and record["provisional"] is True
    assert record["authorized_by"] == ENTRY and record["mask_identity"]["mask_sha256"] == tree["args"]["mask-sha256"]
    assert sorted(p.name for p in tree["out_dir"].iterdir()) == ["outcome_availability.csv", "outcome_availability.json", "screen.json"]


def test_it_refuses_without_an_entry_that_carries_its_pins(tree, capsys):
    refused(tree, capsys, "not authorized", 4, **{"authorized-by": None})
    refused(tree, capsys, "not authorized: D-901 is not an entry", 4, **{"authorized-by": "D-901"})
    refused(tree, capsys, "does not speak of the availability audit", 4, **{"authorized-by": "D-899"})
    text = tree["ledger"].read_text()
    # An entry that speaks of availability but carries no pin block.
    tree["ledger"].write_text(text.split("```")[0] + "\n")
    refused(tree, capsys, "carries no pin block", 4)
    # A pinned file that has changed since the entry was written.
    line = next(ln for ln in text.splitlines() if ln.endswith("pipeline/analysis/availability_adapter.py"))
    tree["ledger"].write_text(text.replace(line, f"sha256 {'0' * 64} pipeline/analysis/availability_adapter.py"))
    refused(tree, capsys, "availability_adapter.py differs from the version D-900 pins", 4)
    # A project module the entry does not pin.
    tree["ledger"].write_text(text.replace(next(ln for ln in text.splitlines() if ln.endswith("pipeline/facilities/buildout.py")) + "\n", ""))
    refused(tree, capsys, "does not pin pipeline/facilities/buildout.py", 4)
    # An entry that pins a project module this process has not loaded: the loaded set is not exactly the pinned set.
    tree["ledger"].write_text(text.replace("version python", f"sha256 {'0' * 64} pipeline/analysis/a_module_never_loaded.py\nversion python"))
    refused(tree, capsys, "not exactly the ones the entry pins", 2)
    # Another interpreter, another library version.
    tree["ledger"].write_text(re.sub(r"interpreter \S+", "interpreter /made/up/python", text))
    refused(tree, capsys, "not the pinned interpreter", 4)
    tree["ledger"].write_text(re.sub(r"version pandas \S+", "version pandas 0.0.0", text))
    refused(tree, capsys, "pandas is not at the pinned version", 4)


def test_no_entry_in_the_real_ledger_lets_it_start(tree, capsys, monkeypatch):
    """Building the command authorizes nothing: tried against every entry of the real ledger, it refuses each."""
    monkeypatch.setattr(rs, "LEDGER", ROOT / "docs" / "DECISIONS.md")
    entries = re.findall(r"^## (D-\d+)\.", (ROOT / "docs" / "DECISIONS.md").read_text(), flags=re.M)
    assert len(entries) >= 83
    for e in entries:
        code, lines = call(tree, capsys, **{"authorized-by": e})
        assert code == 4 and lines[0].startswith("screen refused: not authorized") and lines[-1] == "wrote nothing", (e, lines)
    assert not (tree["out_dir"] / "screen.json").exists()


def test_it_refuses_a_mask_a_sidecar_or_an_input_that_is_not_the_one_named(tree, capsys):
    refused(tree, capsys, "the mask is not the file the instruction names", **{"mask-sha256": "0" * 64})
    refused(tree, capsys, "the corrections file is not the file the instruction names", **{"corrections-sha256": "0" * 64})
    refused(tree, capsys, "the pool file is not the file the instruction names", **{"pool-sha256": "0" * 64})
    side = tree["out_dir"] / "outcome_availability.json"
    for field, value, match in (("status", av.IN_PROGRESS, "not marked completed"), ("definition_version", "other", "another definition"),
                                ("mask_sha256", "0" * 64, "records another hash"), ("rows", 3, "number of rows")):
        side.write_text(json.dumps({**tree["side"], field: value}))
        refused(tree, capsys, match)
    side.write_text(json.dumps({**tree["side"], "run_id": ""}))
    with pytest.raises(ValueError, match="not identified"):                  # the adapter's own refusal: no run identifier
        call(tree, capsys)
    assert not (tree["out_dir"] / "screen.json").exists()


def test_it_refuses_a_malformed_pool_no_state_and_a_bad_output_path(tree, capsys):
    bad = b"utility_id_eia,state,extra\n10,ZZ,1\n"
    (tree["tmp"] / "pool.csv").write_bytes(bad)
    refused(tree, capsys, "pool file's columns", **{"pool-sha256": sha(bad)})
    twice = b"utility_id_eia,state\n10,ZZ\n10,ZZ\n"
    (tree["tmp"] / "pool.csv").write_bytes(twice)
    refused(tree, capsys, "repeated unit", **{"pool-sha256": sha(twice)})
    refused(tree, capsys, "no state named", states=" , ")
    refused(tree, capsys, "--out must be a new .json file", out=str(tree["tmp"] / "elsewhere.json"))
    refused(tree, capsys, "--out must be a new .json file", out=str(tree["out_dir"] / "screen.csv"))
    refused(tree, capsys, "--out must be a new .json file", out=str(tree["out_dir"] / "outcome_availability.json"))
    refused(tree, capsys, "missing: --states", 4, states=None)


def test_a_recheck_writes_nothing_and_names_what_changed(tree, capsys):
    assert call(tree, capsys)[0] == 0
    record = str(tree["out_dir"] / "screen.json")
    names = sorted(p.name for p in tree["out_dir"].iterdir())
    code, lines = call(tree, capsys, out=None, recheck=record)
    assert code == 0 and lines[1] == "the screen stands: none of the five fingerprints has changed"
    # The pool loses a unit: the eligibility rules have changed, and the whole screen is void.
    fewer = b"utility_id_eia,state\n10,ZZ\n11,ZZ\n12,ZZ\n"
    (tree["tmp"] / "pool.csv").write_bytes(fewer)
    code, lines = call(tree, capsys, out=None, recheck=record, **{"pool-sha256": sha(fewer)})
    assert code == 1 and lines[1].endswith("Changed: eligibility_rules")
    # One more state named, and a corrections file with one more correction.
    more = json.dumps(ZZ_CORRECTIONS + [{"fid": "h", "kind": "assign", "to": [14, "ZZ"]}]).encode()
    (tree["tmp"] / "corrections.json").write_bytes(more)
    code, lines = call(tree, capsys, out=None, recheck=record, **{"pool-sha256": sha(fewer), "corrections-sha256": sha(more)})
    assert code == 1 and lines[1].endswith("Changed: corrections, eligibility_rules")
    assert sorted(p.name for p in tree["out_dir"].iterdir()) == names                 # a recheck writes nothing
    refused(tree, capsys, "give --out or --recheck, not both", 4, recheck=record)
    refused(tree, capsys, "--recheck must name a record inside", out=None, recheck=str(tree["tmp"] / "pool.csv"))
    refused(tree, capsys, "not authorized", 4, out=None, recheck=record, **{"authorized-by": "D-899"})


def test_a_wrong_host_count_stops_it(tree, capsys, monkeypatch):
    monkeypatch.setattr(rs, "HOSTS_EXPECTED", 26)
    refused(tree, capsys, "gives 1 hosts, not 26")


def test_the_pin_block_names_every_project_module_the_command_loads_and_only_code():
    block = rs.pin_block().splitlines()
    assert block[0] == rs.PIN_HEADER != av.PIN_HEADER                         # not the audit's block: the audit's steps refuse it
    files = [ln.split()[2] for ln in block if ln.startswith("sha256 ")]
    assert files == sorted(files) == list(rs.loaded_project_files())
    assert all(f.startswith("pipeline/") and f.endswith(".py") for f in files)
    for must in ("pipeline/analysis/availability_adapter.py", "pipeline/analysis/availability.py",
                 "pipeline/analysis/run_availability_screen.py", "pipeline/analysis/power_simulation.py",
                 "pipeline/facilities/pass_c_expand.py", "pipeline/facilities/assignment.py", "pipeline/facilities/pass_c_exact.py",
                 "pipeline/facilities/match_county_gis.py", "pipeline/electricity/market_region.py"):
        assert must in files, must
    assert [ln.split()[1] for ln in block if ln.startswith("version ")] == list(rs.LIBRARIES)
    assert block[-1].startswith("interpreter /")


def test_the_command_names_no_file_under_data_beyond_the_four_it_states():
    src = (ROOT / "pipeline" / "analysis" / "run_availability_screen.py").read_text()
    assert "blind" not in src and "p1_record" not in src and "access-records" not in src and "panel_quantities" not in src
    assert "usecols=list(adapter.MASK_COLUMNS)" in src
