"""The comparison pool's restrictions as the ledger holds them (docs/DECISIONS.md, D-65 item 5; D-67).

The transcription changes no rule. These tests show that the ledger's block is word for word what the plan and the
code say today. When one fails, a source has moved: a change to a pool restriction is a research decision (D-56), so
log it, then transcribe again (`python3 -I pipeline/analysis/pool_restrictions.py`) under a dated note in the ledger.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.analysis import pool_restrictions as pr  # noqa: E402


def test_the_ledgers_transcription_is_word_for_word_what_the_sources_say():
    assert pr.in_ledger() == pr.transcribe()


@pytest.mark.parametrize("heading, path, kind, locator", pr.SOURCES)
def test_every_transcribed_piece_is_found_whole_in_its_source(heading, path, kind, locator):
    body = pr.extract(path, kind, locator)
    assert body.strip()
    text = (ROOT / path).read_text()
    if kind == "lines":                                            # whole lines of the file, in file order, not adjacent
        assert all(line in text.split("\n") for line in body.split("\n"))
    else:
        assert body in text                                        # a contiguous run of the file


def test_a_function_is_taken_to_its_last_line_and_no_further():
    text = "X = 1\n\ndef a(x):\n    y = (\n        x\n    )\n    return y\n\n\nZ = 2\ndef b():\n    return 0\n"
    assert pr._def(text, "a", "made up") == "def a(x):\n    y = (\n        x\n    )\n    return y"
    with pytest.raises(ValueError, match="expected one"):
        pr._def(text, "c", "made up")


def test_the_transcriber_reads_text_and_imports_no_analysis_code():
    src = (ROOT / "pipeline" / "analysis" / "pool_restrictions.py").read_text()
    imports = [ln for ln in src.split("\n") if ln.startswith(("import ", "from "))]
    assert all(ln.split()[1].split(".")[0] in ("__future__", "re", "sys", "pathlib") for ln in imports), imports
    assert "read_parquet" not in src and "read_csv" not in src


# ---- the rules step D switched on (D-94, D-95, D-96; HANDOVER.md D.2) ------------------------------------------------

NEW_SOURCES = [
    ("pipeline/analysis/design.py", "def", "build_with_rules"),
    ("pipeline/analysis/design.py", "def", "apply_support_rule"),
    ("pipeline/analysis/power_simulation.py", "class", "Rules"),
    ("pipeline/analysis/power_simulation.py", "lines", ("HEADLINE_RULES =",)),
    ("pipeline/analysis/power_simulation.py", "lines", ("LISTS_THAT_SET_NO_ONE_ASIDE =",)),
    ("pipeline/analysis/power_simulation.py", "class", "Exclusions"),
    ("pipeline/analysis/power_simulation.py", "def", "real_hosts"),
    ("pipeline/analysis/power_simulation.py", "def", "outcome_rows"),
    ("pipeline/analysis/usable_flag.py", "def", "validate"),
    ("pipeline/analysis/usable_flag.py", "def", "read"),
    ("pipeline/analysis/power_simulation.py", "class", "UnknownLoad"),
    ("pipeline/analysis/power_simulation.py", "def", "load_unknown_load"),
    # Stop 3 (2026-11-18): hosts with unresolved ownership
    ("pipeline/analysis/power_simulation.py", "lines", ("UNRESOLVED_OWNERSHIP_EXCLUDED =",)),
    ("pipeline/analysis/ownership.py", "def", "unresolved_ownership_hosts"),
    ("pipeline/analysis/design.py", "def", "_apply_unresolved_ownership"),
]


@pytest.mark.parametrize("path, kind, locator", NEW_SOURCES)
def test_each_rule_step_d_switched_on_is_transcribed_and_found_exactly_once(path, kind, locator):
    assert any((p, k) == (path, kind) and (loc == locator or (kind == "lines" and set(locator) <= set(loc)))
               for _, p, k, loc in pr.SOURCES), (path, kind, locator)
    text = (ROOT / path).read_text()
    if kind == "def":
        assert len(re.findall(rf"^def {re.escape(locator)}\(", text, flags=re.M)) == 1
    elif kind == "class":
        assert len(re.findall(rf"^class {re.escape(locator)}\b", text, flags=re.M)) == 1
    else:
        for loc in locator:
            assert sum(ln.lstrip().startswith(loc) for ln in text.split("\n")) == 1
    assert pr.extract(path, kind, locator).strip()


def test_a_class_is_taken_with_its_decorator_to_its_last_line_and_no_further():
    text = "X = 1\n\n\n@dataclass(frozen=True)\nclass A:\n    x: int = 1\n\n    def f(self):\n        return (\n            2\n        )\n\n\nB = A()\n"
    assert pr._class(text, "A", "made up") == "@dataclass(frozen=True)\nclass A:\n    x: int = 1\n\n    def f(self):\n        return (\n            2\n        )"
    with pytest.raises(ValueError, match="expected one"):
        pr._class(text, "C", "made up")


@pytest.mark.parametrize("kind, locator, old, new", [
    ("def", "keep", "    return x > 0", "    return x >= 0"),
    ("class", "Rule", "    usable: str = \"flag\"", "    usable: str = \"positive_sales\""),
    ("lines", ("LIMIT =",), "LIMIT = 0.005", "LIMIT = 0.006"),
])
def test_changing_one_transcribed_line_of_an_invented_source_changes_the_transcription(tmp_path, monkeypatch, kind, locator, old, new):
    src = ("LIMIT = 0.005\n\n\n@dataclass(frozen=True)\nclass Rule:\n    usable: str = \"flag\"\n\n\n"
           "def keep(x):\n    return x > 0\n")
    (tmp_path / "made_up.py").write_text(src)
    monkeypatch.setattr(pr, "ROOT", tmp_path)
    before = pr.extract("made_up.py", kind, locator)
    assert old in before
    (tmp_path / "made_up.py").write_text(src.replace(old, new))
    after = pr.extract("made_up.py", kind, locator)
    assert after != before and new in after
    monkeypatch.setattr(pr, "SOURCES", [("Made up", "made_up.py", kind, locator)])
    (tmp_path / "made_up.py").write_text(src)
    one = pr.transcribe()
    (tmp_path / "made_up.py").write_text(src.replace(old, new))
    assert pr.transcribe() != one
