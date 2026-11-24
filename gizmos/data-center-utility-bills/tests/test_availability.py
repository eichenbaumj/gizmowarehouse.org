"""The availability flag, the audit's checks and output, eligibility and the provisional narrowing, in-process.

Made-up data only (tests/availability_synth.py). Nothing here opens a file under data/. Route:
docs/gate1/availability-audit-route.md, as Joe ruled on it on 2026-11-16. The two processes themselves, run
under the sandbox on a made-up tree, are in test_availability_runs.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import availability_synth as syn  # noqa: E402

from pipeline.analysis import availability as avail  # noqa: E402
from pipeline.analysis import design  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402
from pipeline.electricity import access_guard as guard  # noqa: E402
from pipeline.electricity import audit_availability as p2  # noqa: E402
from pipeline.electricity import availability_codes as av  # noqa: E402
from pipeline.electricity import panel  # noqa: E402
from pipeline.electricity import write_usable_flag as p1  # noqa: E402

KEYS = list(av.KEYS)
FIXTURES = HERE / "fixtures"


@pytest.fixture(scope="module")
def built():
    q, o = panel.build(syn.sales_frame(), succession=syn.mapping())
    return q, o


def at(q, u, st, year=syn.YEAR):
    r = q[(q.utility_id_eia == u) & (q.state == st) & (q.year == year)]
    assert len(r) <= 1
    return None if r.empty else r.iloc[0]


# ---- the flag in panel.build ----------------------------------------------------------------------

def test_every_case_gets_its_first_exclusion_reason(built):
    q, _ = built
    for (u, st), want in syn.EXPECTED.items():
        r = at(q, u, st)
        if want is None:
            assert r is None, (u, st)
        else:
            assert r is not None and r[av.REASON_COL] == want, (u, st, None if r is None else r[av.REASON_COL])
            assert bool(r[av.FLAG_COL]) == (want == av.NO_EXCLUSION), (u, st)


def test_supplier_row_status_only_where_the_state_supplier_average_sets_the_price(built):
    q, _ = built
    got = {(int(u), s): st for u, s, y, st in q[KEYS + [av.SUPPLIER_COL]].itertuples(index=False) if st != "not_used"}
    assert got == syn.SUPPLIER_STATUS                         # NJ's unflagged supplier row makes NJ unknown; its
    assert at(q, 9, "TX")[av.SUPPLIER_COL] == "not_used"     # imputed-flagged row (93) counts in neither price nor status
    assert set(q[av.SUPPLIER_COL]) <= set(av.SUPPLIER_STATUS)
    assert ((q[av.SUPPLIER_COL] != "not_used") == (q.supply_price_basis == "state_observed_suppliers")).all()


def test_the_flag_is_the_analysis_filter_row_by_row(built):
    q, o = built
    m = q.merge(o, on=KEYS)
    assert len(m) == len(q) == len(o)
    filt = m.meets_size_floor & (m.res_price > 0)                  # power_simulation.py, every place the price is filtered
    assert (filt == m[av.FLAG_COL]).all()
    assert ((m[av.REASON_COL] == av.NO_EXCLUSION) == m[av.FLAG_COL]).all()


def test_the_supply_predicate_is_supply_price_basis_none_available(built):
    """Stated from the inputs, independently of the reason order."""
    q, _ = built
    got = {(int(u), s) for u, s, y, b in q[KEYS + ["supply_price_basis"]].itertuples(index=False)
           if b == "none_available" and y == syn.YEAR}
    assert got == syn.NONE_AVAILABLE
    assert at(q, 9, "TX").supply_price_basis == "own_default_service_small_share"   # exactly 1% takes the fallback
    assert at(q, 14, "PA").supply_price_basis == "state_observed_suppliers"


def test_precedence_quantity_reasons_first(built):
    q, _ = built
    assert at(q, 20, "GA")[av.REASON_COL] == "under_customer_floor"        # also a negative price
    assert at(q, 21, "GA")[av.REASON_COL] == "no_residential_sales"        # also under the floor
    assert at(q, 13, "TX")[av.REASON_COL] == "no_supply_price"             # also bundled revenue missing
    assert [c for c, _, src in av.REASON_ORDER if src == "quantities"] == list(av.BUILD_REASONS[:3])


def test_imputed_rows_dropped_unknown_flags_kept_and_said(built):
    q, o = built
    assert at(q, 15, "GA") is None                                        # every row imputed: absent
    r16 = at(q, 16, "GA")
    assert r16.res_mwh == 10_000 and pd.isna(r16.res_mwh_delivery)         # the imputed delivery row went with its sales
    assert at(q, 17, "GA")[av.UNKNOWN_COL] == "unknown"
    assert set(q[av.UNKNOWN_COL]) <= set(av.IMPUTATION_STATUS)
    assert {(int(u), s) for u, s, st in q[["utility_id_eia", "state", av.UNKNOWN_COL]].itertuples(index=False)
            if st == "unknown"} == syn.UNKNOWN_STATUS


def test_partly_missing_revenue_in_a_summed_unit_counts_as_present_as_the_code_sums(built):
    """Faithful reproduction, not an endorsement: the route's last section says this can move positivity."""
    q, o = built
    r = at(q, 19, "GA")
    assert r.res_customers == 4000 and r.res_mwh == 15_000 and r[av.FLAG_COL]
    assert at(q, 18, "GA") is None


def test_a_non_finite_price_on_a_priceable_row_stops_without_showing_values():
    with pytest.raises(panel.NonFinitePrice) as e:
        panel.build(syn.sales_frame(syn.with_infinite_revenue()), succession=syn.mapping())
    assert not re.search(r"\d", str(e.value))


def test_outcomes_and_old_quantity_columns_are_unchanged_by_the_edit(built):
    q, o = built
    before_q = pd.read_parquet(FIXTURES / "availability_panel_before_quantities.parquet")
    before_o = pd.read_parquet(FIXTURES / "availability_panel_before_outcomes.parquet")
    assert p1.same_frame(p1.roundtrip(o), before_o, KEYS)
    old = list(before_q.columns)
    assert list(q.columns) == old + list(av.NEW_QUANTITY_COLS)
    assert p1.same_frame(p1.roundtrip(q)[old], before_q, KEYS)


def test_the_quantities_file_gains_no_value_derived_from_revenue(built):
    q, _ = built
    assert q[av.FLAG_COL].dtype == bool
    assert all(q[c].map(type).eq(str).all() for c in (av.REASON_COL, av.UNKNOWN_COL, av.SUPPLIER_COL))
    assert not {"res_price", "res_revenue_full", "res_price_delivery_only", "res_price_default_service"} & set(q.columns)


# ---- P1's identity comparison -----------------------------------------------------------------------

def frame():
    return pd.DataFrame({"utility_id_eia": [1, 1, 2], "state": ["GA", "GA", "TX"], "year": [2019, 2020, 2020],
                         "x": [1.5, np.nan, 3.0]})


def test_identity_ignores_row_order_and_index_only():
    a = frame()
    b = a.iloc[::-1].set_index(pd.Index([7, 8, 9]))
    assert p1.same_frame(a, b, KEYS)
    assert p1.same_frame(a, b[["x", "year", "state", "utility_id_eia"]], KEYS)


@pytest.mark.parametrize("change", ["value", "nan_to_value", "dtype", "duplicate_key", "extra_column", "missing_row"])
def test_identity_catches_every_real_difference(change):
    a, b = frame(), frame()
    if change == "value":
        b.loc[2, "x"] = 3.0000001
    elif change == "nan_to_value":
        b.loc[1, "x"] = 0.0
    elif change == "dtype":
        b["year"] = b.year.astype("int32")
    elif change == "duplicate_key":
        a.loc[2, ["utility_id_eia", "state", "year"]] = [1, "GA", 2020]
        b = a.copy()
    elif change == "extra_column":
        b["y"] = 0
    elif change == "missing_row":
        b = b.iloc[:2]
    assert not p1.same_frame(a, b, KEYS)


# ---- P2's checks and its mask -----------------------------------------------------------------------

@pytest.fixture()
def quantities(built):
    q, _ = built
    return q[list(av.AUDIT_READ_COLS)].copy()


def test_the_audit_accepts_the_build(quantities):
    p2.validate(quantities)


@pytest.mark.parametrize("break_it, words", [
    (lambda q: pd.concat([q, q.iloc[:1]]), "duplicate utility-state-year keys"),
    (lambda q: q.assign(**{av.FLAG_COL: q[av.FLAG_COL].astype(object).where(q.index != q.index[0], None)}), "null flag"),
    (lambda q: q.assign(**{av.REASON_COL: q[av.REASON_COL].where(q.index != q.index[0], "made_up_reason")}), "unknown first exclusion reason"),
    (lambda q: q.assign(**{av.REASON_COL: q[av.REASON_COL].where(q.index != q.index[0], av.NOT_IN_PANEL)}), "unknown first exclusion reason"),
    (lambda q: q.assign(**{av.FLAG_COL: ~q[av.FLAG_COL]}), "disagree"),
    (lambda q: q.assign(res_mwh=0.0), "no_residential_sales does not match"),
    (lambda q: q.assign(meets_size_floor=False), "under_customer_floor does not match"),
    (lambda q: q.assign(supply_price_basis="none_available"), "does not match"),
    (lambda q: q.assign(year=q.year.where(q.index != q.index[0], 2030)), "outside 2001-2025"),
    (lambda q: q.assign(**{av.UNKNOWN_COL: "maybe"}), "unknown imputation status"),
    (lambda q: q.assign(**{av.SUPPLIER_COL: "maybe"}), "unknown supplier-row status"),
    (lambda q: q.assign(**{av.SUPPLIER_COL: "known"}), "supplier-row status does not match"),
    (lambda q: q.assign(**{av.SUPPLIER_COL: q[av.SUPPLIER_COL].astype(object).where(q.index != q.index[0], None)}), "null flag, reason or status"),
    (lambda q: q.drop(columns=[av.FLAG_COL]), "lacks"),
])
def test_the_audit_refuses_in_words_naming_identifiers_only(quantities, break_it, words):
    with pytest.raises(guard.Refusal) as e:
        p2.validate(break_it(quantities))
    assert words in str(e.value)
    assert not any(c in str(e.value) for c in syn.CANARY_STRINGS)


def test_the_mask_covers_every_panel_year_and_says_not_in_panel(quantities):
    m = p2.mask_from(quantities)
    assert list(m.columns) == list(av.MASK_COLUMNS)
    units = quantities[["utility_id_eia", "state"]].drop_duplicates()
    assert len(m) == len(units) * len(av.PANEL_YEARS) and not m.duplicated(KEYS).any()
    r = m[(m.utility_id_eia == 1) & (m.state == "GA")].set_index("year")
    assert r.loc[2020, "usable"] and r.loc[2019, "usable"] and r.loc[2020, "first_exclusion_reason"] == av.NO_EXCLUSION
    assert not r.loc[2018, "usable"] and r.loc[2018, "first_exclusion_reason"] == av.NOT_IN_PANEL
    assert r.loc[2018, "imputation_status"] == "no_rows" and r.loc[2018, "supplier_rows_imputation_status"] == "no_rows"
    assert r.loc[2020, "supplier_rows_imputation_status"] == "not_used"
    assert set(m.first_exclusion_reason) <= set(av.ALL_CODES)
    assert ((m.first_exclusion_reason == av.NO_EXCLUSION) == m.usable).all()


def test_counts_are_predetermined_every_code_in_order(quantities):
    c = p2.counts(p2.mask_from(quantities))
    assert list(c) == list(av.ALL_CODES)
    assert sum(c.values()) == quantities[["utility_id_eia", "state"]].drop_duplicates().shape[0] * len(av.PANEL_YEARS)
    assert c["price_not_above_zero"] == 2 and c["no_supply_price"] == 5


# ---- writing ----------------------------------------------------------------------------------------

def test_an_interrupted_write_leaves_the_old_file_whole(tmp_path):
    f = tmp_path / "out.csv"
    f.write_bytes(b"old")

    def half(fh):
        fh.write(b"new and partial")
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        guard.write_atomically(f, half)
    assert f.read_bytes() == b"old" and not (tmp_path / "out.csv.tmp").exists()
    guard.write_atomically(f, lambda fh: fh.write(b"new"))
    assert f.read_bytes() == b"new"


# ---- the guard's decisions (pure; nothing installed) --------------------------------------------------

@pytest.fixture()
def pol(tmp_path):
    root = tmp_path / "gz"
    d = root / "data"
    return guard.Policy(root=str(root), reads=frozenset({str(d / "interim" / "q.parquet")}),
                        writes=frozenset({str(d / "interim" / "out.csv.tmp")}), listable=frozenset({str(d / "blind" / "by_unit")}),
                        renames=frozenset({(str(d / "interim" / "out.csv.tmp"), str(d / "interim" / "out.csv"))}),
                        banned_imports=frozenset({"duckdb", "pipeline.electricity.panel"}))


def test_guard_decisions(pol):
    d = pol.data
    ok = lambda e, *a: guard.decide(e, a, pol)[0]  # noqa: E731
    assert ok("open", f"{d}/interim/q.parquet", "rb", 0)
    assert not ok("open", f"{d}/blind/panel_outcomes.parquet", "rb", 0)
    assert not ok("open", f"{d}/interim/../blind/x.parquet", "rb", 0)              # normalized before the test
    assert not ok("open", f"{d}/interim/q.parquet", "wb", 0)                         # readable is not writable
    assert ok("open", f"{d}/interim/out.csv.tmp", "wb", 0)
    assert not ok("open", "/tmp/anything.txt", "w", 0)                               # no write outside the list, anywhere
    assert not ok("open", f"{d}/interim/q.parquet", None, 0o1101)                    # os.open with write flags
    assert ok("open", "/usr/lib/python3.13/os.py", "r", 0)                           # code outside data/ is readable
    assert not ok("os.listdir", d) and not ok("os.scandir", f"{d}/blind")
    assert ok("os.scandir", f"{d}/blind/by_unit")
    assert not ok("glob.glob", f"{d}/*", False)
    assert not ok("os.symlink", f"{d}/blind", "/tmp/link", -1)
    assert not ok("shutil.copytree", f"{d}/blind", "/tmp/copy")
    assert not ok("subprocess.Popen", "ls", ["ls"], None, None)
    assert not ok("os.system", b"ls")
    assert not ok("import", "duckdb") and not ok("import", "pipeline.electricity.panel") and ok("import", "pandas")
    assert ok("os.replace", f"{d}/interim/out.csv.tmp", f"{d}/interim/out.csv", -1, -1)
    assert not ok("os.replace", f"{d}/interim/out.csv.tmp", f"{d}/blind/x", -1, -1)
    assert ok("os.remove", f"{d}/interim/out.csv.tmp", -1)
    assert not ok("os.remove", f"{d}/interim/q.parquet", -1)
    assert not ok("ctypes.dlopen", f"{d}/blind/x.so")


def test_guard_records_what_touches_the_gizmo_folder_and_every_refusal(pol):
    d = pol.data
    _, rec = guard.decide("open", (f"{d}/interim/q.parquet", "rb", 0), pol)
    assert rec == {"event": "open", "path": f"{d}/interim/q.parquet", "what": "read", "allowed": True}
    _, rec = guard.decide("open", ("/tmp/elsewhere", "w", 0), pol)
    assert rec["allowed"] is False
    assert guard.decide("open", ("/usr/lib/x.py", "r", 0), pol)[1] is None


def test_authorization_needs_a_ledger_entry_about_the_availability_audit(tmp_path):
    ledger = tmp_path / "DECISIONS.md"
    ledger.write_text("## D-1. Something else\n\ntext\n\n## D-2. Joe authorizes the availability audit run\n\nwords\n")
    assert guard.check_authorization(ledger, "D-2")[0] == "D-2"
    for bad, code in ((None, 4), ("D-1", 4), ("D-3", 4), ("D-2; rm", 4)):
        with pytest.raises(guard.Refusal) as e:
            guard.check_authorization(ledger, bad)
        assert e.value.code == code


INTERP = "/opt/made-up/bin/python3.13"


def pinned_tree(tmp_path, extra=""):
    root = tmp_path / "gz"
    for rel in ("a.py", "b/c.sb"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(f"contents of {rel}\n")
    block = "\n".join([av.PIN_HEADER, f"sha256 {guard.sha256(root / 'a.py')} a.py", f"sha256 {guard.sha256(root / 'b/c.sb')} b/c.sb",
                       "version python 3.13.5", "version pandas 2.2.3", f"interpreter {INTERP}"])
    ledger = tmp_path / "DECISIONS.md"
    ledger.write_text(f"## D-5. Joe instructs the availability audit run\n\nwords\n\n```\n{block}\n```\n{extra}\n## D-6. Next\n")
    return root, ledger


def test_pins_are_parsed_and_every_pinned_file_must_match(tmp_path):
    root, ledger = pinned_tree(tmp_path)
    entry, pins = guard.check_authorization(ledger, "D-5", root, ("a.py", "b/c.sb"), av.PIN_HEADER)
    assert entry == "D-5" and pins["versions"] == {"python": "3.13.5", "pandas": "2.2.3"} and pins["interpreter"] == INTERP
    with pytest.raises(guard.Refusal, match="does not pin d.py"):
        guard.check_authorization(ledger, "D-5", root, ("a.py", "d.py"), av.PIN_HEADER)
    (root / "b/c.sb").write_text("changed\n")
    with pytest.raises(guard.Refusal, match="b/c.sb differs from the version D-5 pins") as e:
        guard.check_authorization(ledger, "D-5", root, ("a.py", "b/c.sb"), av.PIN_HEADER)
    assert e.value.code == 4


@pytest.mark.parametrize("extra, words", [
    ("sha256 " + "0" * 64 + " a.py", "outside the pin block"),                       # a later line that would override
    ("version pandas 9.9.9", "outside the pin block"),
    ("interpreter /usr/bin/python3", "outside the pin block"),
    ("```\n" + av.PIN_HEADER + "\nversion python 3.13.5\n```", "more than one pin block"),
])
def test_a_pin_line_outside_the_one_block_is_refused(tmp_path, extra, words):
    root, ledger = pinned_tree(tmp_path, extra=extra)
    with pytest.raises(guard.Refusal, match=words):
        guard.check_authorization(ledger, "D-5", root, ("a.py",), av.PIN_HEADER)


@pytest.mark.parametrize("dup, words", [
    ("sha256 " + "1" * 64 + " a.py", "a.py is pinned twice"),
    ("version pandas 2.2.3", "pandas is pinned twice"),
    ("interpreter " + INTERP, "interpreter is pinned twice"),
])
def test_a_duplicate_or_conflicting_pin_inside_the_block_is_refused(dup, words):
    block = "\n".join([av.PIN_HEADER, "sha256 " + "0" * 64 + " a.py", "version pandas 2.2.3", f"interpreter {INTERP}", dup])
    with pytest.raises(guard.Refusal, match=words):
        guard.parse_pins(block, av.PIN_HEADER)


def test_pin_parsing_is_literal_not_a_markdown_or_path_validator(tmp_path):
    """D-76, G4: the parser recognizes three exact line shapes inside one block. A line in any other shape is neither a
    pin nor a refusal, and a path is matched as the string that was pinned, never resolved."""
    inert = "- sha256 " + "0" * 64 + " a.py\n`version pandas 9.9.9`\nSHA256 " + "0" * 64 + " a.py\ninterpreter: /usr/bin/python3"
    root, ledger = pinned_tree(tmp_path, extra=inert)
    _, pins = guard.check_authorization(ledger, "D-5", root, ("a.py",), av.PIN_HEADER)
    assert pins["files"]["a.py"] == guard.sha256(root / "a.py") and pins["versions"]["pandas"] == "2.2.3" and pins["interpreter"] == INTERP
    with pytest.raises(guard.Refusal, match=r"does not pin \./a\.py"):                 # the same file, another spelling
        guard.check_authorization(ledger, "D-5", root, ("./a.py",), av.PIN_HEADER)


def test_the_entry_hash_covers_the_entry_alone_and_changes_with_its_words(tmp_path):
    """D-76, G8: P1's record and the sidecar carry the hash of the authorizing entry's text; a later step compares it
    with the entry as it then stands. Entries appended elsewhere do not move it; a changed word or pin does."""
    root, ledger = pinned_tree(tmp_path)
    text = ledger.read_text()
    h = lambda: guard.check_authorization(ledger, "D-5", root, ("a.py",), av.PIN_HEADER)[1]["entry_sha256"]  # noqa: E731
    first = h()
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert guard.check_authorization(ledger, "D-5")[1]["entry_sha256"] == first
    ledger.write_text("## D-4. An earlier entry\n\nwords\n\n" + text + "\n## D-7. A later entry, appended\n\nwords\n")
    assert h() == first
    ledger.write_text(text.replace("## D-6. Next", "\n\n## D-6. Next, reworded"))        # blank lines after it; a later title
    assert h() == first
    ledger.write_text(text.replace("words", "other words", 1))
    assert h() != first
    ledger.write_text(text.replace("Joe instructs", "Joe instructed", 1))               # the title is part of the entry
    assert h() != first
    ledger.write_text(text.replace("version pandas 2.2.3", "version pandas 2.2.4"))
    assert h() != first


def test_an_entry_with_no_pin_block_does_not_authorize(tmp_path):
    root, ledger = pinned_tree(tmp_path)
    ledger.write_text("## D-4. The availability audit, no pins here\n\nwords\n\n" + ledger.read_text())
    with pytest.raises(guard.Refusal, match="carries no pin block"):
        guard.check_authorization(ledger, "D-4", root, ("a.py",), av.PIN_HEADER)
    with pytest.raises(guard.Refusal, match="no pin block header"):
        guard.parse_pins("words\nversion pandas 2.2.3\n", av.PIN_HEADER)


def test_the_interpreter_must_be_the_pinned_one(monkeypatch):
    import os
    here = os.path.realpath(sys.executable)
    assert guard.check_interpreter({"interpreter": here}) == here
    with pytest.raises(guard.Refusal, match="not the pinned interpreter"):
        guard.check_interpreter({"interpreter": INTERP})
    with pytest.raises(guard.Refusal, match="no interpreter is pinned"):
        guard.check_interpreter({"interpreter": None})


def test_library_versions_must_match_their_pins():
    guard.check_versions({"python": "3.13.5", "pandas": "2.2.3"}, {"python": "3.13.5", "pandas": "2.2.3"})
    with pytest.raises(guard.Refusal, match="pandas is not at the pinned version"):
        guard.check_versions({"python": "3.13.5", "pandas": "2.2.3"}, {"pandas": "2.3.0"})
    with pytest.raises(guard.Refusal, match="no version of duckdb is pinned"):
        guard.check_versions({"python": "3.13.5"}, {"duckdb": "1.1.0"})


def test_the_pin_block_covers_every_file_each_step_uses_and_parses_back():
    from pipeline.electricity import availability_pins as pins
    block = pins.pin_block(ROOT, versions={k: "x" for k in ("python", "numpy", "pandas", "pyarrow", "duckdb")})
    parsed = guard.parse_pins(block, av.PIN_HEADER)
    assert set(parsed["files"]) == set(av.P1_PINNED) | set(av.P2_PINNED) | set(av.PRESERVE_PINNED)
    assert all(guard.sha256(ROOT / rel) == h for rel, h in parsed["files"].items())
    assert set(parsed["versions"]) == set(av.P1_LIBRARIES) | set(av.P2_LIBRARIES) | set(av.PRESERVE_LIBRARIES)
    assert parsed["interpreter"] == pins.interpreter()
    assert "pipeline/electricity/sandbox/denied_probe.txt" not in parsed["files"]   # checked by the launcher and inside instead


def test_the_two_extra_read_denies(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo" / "gizmos" / "me"
    pol = guard.standard_policy(root)
    ok = lambda p: guard.decide("open", (str(p), "rb", 0), pol)[0]  # noqa: E731
    assert not ok(tmp_path / "home/.claude/projects" / "-Users-jeichenbaum-Projects-personal-gizmo-warehouse" / "access-records/x.jsonl")
    assert not ok(tmp_path / "repo/gizmos/other/data/blind/x.parquet")
    assert not ok(tmp_path / "repo/gizmos/other/data")
    assert ok(tmp_path / "repo/gizmos/other/pipeline/x.py")               # other gizmos' code stays readable
    assert ok(tmp_path / "repo/gizmos/other/datasets.md")                 # "data" is a folder name, not a prefix
    assert ok(tmp_path / "home/.claude/projects/elsewhere/x.md")
    assert not guard.decide("os.listdir", (str(tmp_path / "repo/gizmos/other/data"),), pol)[0]


def test_read_once_hashes_exactly_the_bytes_it_returns_with_one_open(tmp_path, monkeypatch):
    import builtins
    import hashlib
    f = tmp_path / "q.parquet"
    f.write_bytes(b"made-up bytes")
    opened = []
    real = builtins.open
    monkeypatch.setattr(builtins, "open", lambda *a, **k: (opened.append(a[0]), real(*a, **k))[1])
    h, data = guard.read_once(f)
    assert opened == [f] and data == b"made-up bytes" and h == hashlib.sha256(data).hexdigest()


# ---- the observation flag's domain (D-74, from R5) -----------------------------------------------------

def test_the_two_spellings_of_the_imputed_row_filter_agree_on_true_false_and_missing():
    s = pd.Series([True, False, None, True, None], dtype=object)
    a = s.fillna(True).astype(bool)                                    # panel._observed_with_units, state_energy_price
    b = s.isna() | (s == True)                                         # noqa: E712 - panel.state_supplier_imputation_status
    assert (a == b).all()
    for dtype in ("boolean", bool):
        t = pd.Series([True, False] + ([None] if dtype == "boolean" else []), dtype=dtype)
        assert (t.fillna(True).astype(bool) == (t.isna() | (t == True))).all()  # noqa: E712


@pytest.mark.parametrize("values, ok", [
    ([True, False, None], True), ([True, False], True), ([None, None], True),
    (["Y", True], False), ([1, 0], False), (["True", "False"], False), ([1.0, None], False),
])
def test_p1_accepts_only_true_false_or_missing_flags(values, ok):
    assert p1.flag_domain_ok(pd.Series(values, dtype=object)) is ok
    s = pd.Series(["Y", "N"], dtype=object)
    assert s.fillna(True).astype(bool).tolist() != (s.isna() | (s == True)).tolist()   # noqa: E712 - why the domain matters


# ---- P2's check of P1's record ---------------------------------------------------------------------------

DROP = object()
# The pin block of the made-up authorizing entry, as check_authorization returns it. The fixtures below carry every
# field the real writers write (test_availability_runs.py checks their key sets against real records), so an accepted
# fixture is a whole record, not a minimal one (D-76, G2).
PINS = {"files": {av.P1_PROFILE: "1" * 64, av.P2_PROFILE: "2" * 64},
        "versions": {"python": "3.13.5", "numpy": "2.4.6", "pandas": "2.2.3", "pyarrow": "19.0.0", "duckdb": "1.5.5"},
        "interpreter": INTERP, "entry_sha256": "9" * 64}


def p1_record(**over):
    r = {"what_this_is": "made up", "schema_version": av.SCHEMA_VERSIONS["p1_record"],
         "quantities_columns_schema_version": av.SCHEMA_VERSIONS["quantities_columns"], "status": "completed", "run_id": "a" * 32,
         "definition_version": av.DEFINITION_VERSION, "analysis_filter": av.ANALYSIS_FILTER, "authorized_by": "D-900",
         "authorization_entry_sha256": PINS["entry_sha256"], "pinned_files": list(av.P1_PINNED), "interpreter": INTERP,
         "sandbox_profile_sha256": PINS["files"][av.P1_PROFILE], "git_commit": "0" * 40,
         "inputs_sha256": {k: "d" * 64 for k in av.P1_INPUT_HASHES}, "by_unit_files": 1,
         "checks": {c: True for c in av.P1_CHECKS}, "versions": {lib: PINS["versions"][lib] for lib in av.P1_LIBRARIES},
         "quantities_written_sha256": "b" * 64, "native_reads_declared": [], "recorded_events": [], "recorded_events_note": "made up"}
    r.update(over)
    return {k: v for k, v in r.items() if v is not DROP}


@pytest.mark.parametrize("over, words", [
    ({"analysis_filter": DROP}, "does not carry this code's analysis filter"),
    ({"analysis_filter": "res_price > 0"}, "does not carry this code's analysis filter"),
    ({"inputs_sha256": DROP}, "each of its four inputs"),
    ({"inputs_sha256": "d" * 64}, "each of its four inputs"),
    ({"inputs_sha256": {k: "d" * 64 for k in av.P1_INPUT_HASHES[:3]}}, "each of its four inputs"),
    ({"inputs_sha256": {**{k: "d" * 64 for k in av.P1_INPUT_HASHES}, "sales": "D" * 64}}, "each of its four inputs"),
    ({"inputs_sha256": {**{k: "d" * 64 for k in av.P1_INPUT_HASHES}, "outcomes": "d" * 63}}, "each of its four inputs"),
    ({"inputs_sha256": {**{k: "d" * 64 for k in av.P1_INPUT_HASHES}, "outcomes": None}}, "each of its four inputs"),
    ({"inputs_sha256": {**{k: "d" * 64 for k in av.P1_INPUT_HASHES}, "another": "d" * 64}}, "each of its four inputs"),
    ({"versions": DROP}, "every library it used at its pinned version"),
    ({"versions": {**{lib: PINS["versions"][lib] for lib in av.P1_LIBRARIES}, "pandas": "9.9.9"}}, "every library it used at its pinned version"),
    ({"versions": {lib: PINS["versions"][lib] for lib in av.P1_LIBRARIES[:-1]}}, "every library it used at its pinned version"),
    ({"interpreter": DROP}, "does not record the pinned interpreter"),
    ({"interpreter": "/usr/bin/python3"}, "does not record the pinned interpreter"),
    ({"sandbox_profile_sha256": "3" * 64}, "does not record the pinned sandbox profile"),
    ({"sandbox_profile_sha256": DROP}, "does not record the pinned sandbox profile"),
    ({"authorization_entry_sha256": DROP}, "not made under this text of the authorizing entry"),
    ({"authorization_entry_sha256": "8" * 64}, "not made under this text of the authorizing entry"),
])
def test_p2_requires_the_essential_provenance_of_the_flag_build(over, words):
    """D-76, G2: the input hashes and the fixed analysis filter are required; the recorded interpreter, versions and
    profile must be the pinned ones (Joe's choice); the record must be made under the entry's present text."""
    assert p2.check_p1_record(p1_record(), "b" * 64, "D-900", PINS) == "a" * 32
    with pytest.raises(guard.Refusal, match=words):
        p2.check_p1_record(p1_record(**over), "b" * 64, "D-900", PINS)


def test_p2_refuses_a_record_that_is_not_a_record_or_pins_that_pin_nothing():
    for not_a_record in ([], "completed", None, 3):
        with pytest.raises(guard.Refusal, match="is not a record"):
            p2.check_p1_record(not_a_record, "b" * 64, "D-900", PINS)
    # Nothing passes because two missing values compare equal: empty pins match no recorded value.
    empty = {"files": {}, "versions": {}, "interpreter": None, "entry_sha256": None}
    bare = p1_record(interpreter=DROP, versions=DROP, sandbox_profile_sha256=DROP, authorization_entry_sha256=DROP)
    with pytest.raises(guard.Refusal):
        p2.check_p1_record(bare, "b" * 64, "D-900", empty)
    with pytest.raises(guard.Refusal):
        p2.check_p1_record(p1_record(), "b" * 64, "D-900", empty)


@pytest.mark.parametrize("over, words", [
    ({"status": "in_progress"}, "not marked completed"),
    ({"status": DROP}, "not marked completed"),
    ({"checks": {**{c: True for c in av.P1_CHECKS[:4]}, "renamed": True}}, "exactly the five checks"),
    ({"checks": {**{c: True for c in av.P1_CHECKS}, "extra": True}}, "exactly the five checks"),
    ({"checks": {**{c: True for c in av.P1_CHECKS}, av.P1_CHECKS[2]: False}}, "all five named checks passed"),
    ({"checks": {**{c: True for c in av.P1_CHECKS}, av.P1_CHECKS[0]: "yes"}}, "all five named checks passed"),
    ({"run_id": ""}, "no run identifier"),
    ({"quantities_written_sha256": DROP}, "no hash of the quantities file"),
    ({"quantities_written_sha256": "c" * 64}, "stale or changed"),
    ({"definition_version": "2026-11-16.1"}, "another definition version"),
    ({"schema_version": 2}, "unknown schema version"),
    ({"quantities_columns_schema_version": DROP}, "quantities-column schema version"),
    ({"authorized_by": "D-901"}, "another authorization"),
])
def test_p2_requires_a_completed_well_formed_record_under_the_same_authorization(over, words):
    assert p2.check_p1_record(p1_record(), "b" * 64, "D-900", PINS) == "a" * 32
    with pytest.raises(guard.Refusal, match=words):
        p2.check_p1_record(p1_record(**over), "b" * 64, "D-900", PINS)


# ---- the preserved bundle -------------------------------------------------------------------------------

def sidecar_for(p1: dict, mask: bytes, p1_bytes: bytes) -> dict:
    """A made-up sidecar with every field the audit writes, for the made-up P1 record `p1`."""
    import hashlib
    p1_sha = hashlib.sha256(p1_bytes).hexdigest()
    return {"what_this_is": "made up", "schema_version": av.SCHEMA_VERSIONS["sidecar"], "mask_schema_version": av.SCHEMA_VERSIONS["mask"],
            "quantities_columns_schema_version": av.SCHEMA_VERSIONS["quantities_columns"], "status": "completed",
            "run_id": "a" * 32, "attempt_id": "c" * 32, "definition_version": av.DEFINITION_VERSION, "authorized_by": "D-900",
            "authorization_entry_sha256": PINS["entry_sha256"], "mask_sha256": hashlib.sha256(mask).hexdigest(),
            "p1_record_sha256": p1_sha, "analysis_filter": av.ANALYSIS_FILTER, "first_exclusion_reason_order": [],
            "counts_by_first_applicable_exclusion_reason": {}, "counts_note": "made up", "imputation_status": "made up",
            "supplier_rows_imputation_status": "made up", "years": [2001, 2025], "rows": 1, "pinned_files": list(av.P2_PINNED),
            "interpreter": INTERP, "sandbox_profile_sha256": PINS["files"][av.P2_PROFILE], "git_commit": "0" * 40,
            "inputs_sha256": {"quantities": "b" * 64, "p1_record": p1_sha},
            "flag_build": {k: p1.get(k) for k in av.SIDECAR_FLAG_BUILD_KEYS}, "columns_read": list(av.AUDIT_READ_COLS),
            "versions": {lib: PINS["versions"][lib] for lib in av.P2_LIBRARIES}, "recorded_events": [], "recorded_events_note": "made up"}


def bundle(tmp_path, name="availability", p1_over=None, **side_over):
    """A made-up bundle. An override that is a function is given the sidecar as built and returns the field's value."""
    import json
    d = tmp_path / name
    d.mkdir()
    mask = (",".join(av.MASK_COLUMNS) + "\n1,GA,2020,True,none,known,not_used\n").encode()
    (d / "outcome_availability.csv").write_bytes(mask)
    p1 = p1_record(**(p1_over or {}))
    p1b = json.dumps(p1).encode()
    (d / "p1_record.json").write_bytes(p1b)
    side = sidecar_for(p1, mask, p1b)
    side.update({k: (v(side) if callable(v) else v) for k, v in side_over.items()})
    side = {k: v for k, v in side.items() if v is not DROP}
    (d / "outcome_availability.json").write_text(json.dumps(side))
    return d


def test_a_consistent_bundle_is_accepted(tmp_path):
    from pipeline.electricity import preserve_availability as keep
    r = keep.verify_bundle(bundle(tmp_path), "D-900", PINS)
    assert r["run_id"] == "a" * 32 and r["attempt_id"] == "c" * 32 and r["authorization_entry_sha256"] == PINS["entry_sha256"]
    assert r["analysis_filter"] == av.ANALYSIS_FILTER


def test_verifying_a_bundle_reads_each_file_once_and_hashes_what_it_parsed(tmp_path, monkeypatch):
    """Within one verification a file is read once; the hash reported is of the bytes that were parsed (D-76, G6)."""
    import hashlib
    from pipeline.electricity import preserve_availability as keep
    d = bundle(tmp_path)
    reads, real = [], Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda self: (reads.append(self.name), real(self))[1])
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: pytest.fail("a second, separate read"))
    r = keep.verify_bundle(d, "D-900", PINS)
    assert sorted(reads) == sorted(keep.FILES)
    assert r["files_sha256"] == {f: hashlib.sha256(real(d / f)).hexdigest() for f in keep.FILES}


@pytest.mark.parametrize("over, p1_over, words", [
    # D-76, G2: the fixed analysis filter, the essential input hashes, the duplicated fields, the pinned provenance.
    ({"analysis_filter": DROP}, None, "the sidecar does not carry this code's analysis filter"),
    ({"analysis_filter": "another filter"}, None, "the sidecar does not carry this code's analysis filter"),
    ({}, {"analysis_filter": DROP}, "P1's record does not carry this code's analysis filter"),
    ({}, {"inputs_sha256": {k: "d" * 64 for k in av.P1_INPUT_HASHES[1:]}}, "P1's record does not carry a well-formed hash for each of its four inputs"),
    ({"inputs_sha256": {"quantities": "b" * 64}}, None, "each of its two inputs"),
    ({"inputs_sha256": lambda s: {**s["inputs_sha256"], "p1_record": "0" * 64}}, None, "two copies of the hash of P1's record disagree"),
    ({"inputs_sha256": lambda s: {**s["inputs_sha256"], "p1_record": s["p1_record_sha256"].upper()}}, None, "each of its two inputs"),
    ({"p1_record_sha256": "0" * 64}, None, "two copies of the hash of P1's record disagree"),
    ({"flag_build": DROP}, None, "copy of P1's fields is not P1's record"),
    ({"flag_build": lambda s: {**s["flag_build"], "run_id": "e" * 32}}, None, "copy of P1's fields is not P1's record"),
    ({"flag_build": lambda s: {**s["flag_build"], "inputs_sha256": {**s["flag_build"]["inputs_sha256"], "sales": "0" * 64}}}, None,
     "copy of P1's fields is not P1's record"),
    ({"flag_build": lambda s: {k: v for k, v in s["flag_build"].items() if k != "checks"}}, None, "copy of P1's fields is not P1's record"),
    ({"versions": {"python": "3.13.5", "pandas": "0", "pyarrow": "19.0.0"}}, None, "the sidecar does not record every library it used"),
    ({"versions": DROP}, None, "the sidecar does not record every library it used"),
    ({"interpreter": "/usr/bin/python3"}, None, "the sidecar does not record the pinned interpreter"),
    ({}, {"interpreter": DROP}, "P1's record does not record the pinned interpreter"),
    ({}, {"versions": {lib: "0" for lib in av.P1_LIBRARIES}}, "P1's record does not record every library it used"),
    ({"sandbox_profile_sha256": PINS["files"][av.P1_PROFILE]}, None, "the sidecar does not record the pinned sandbox profile"),
    ({}, {"sandbox_profile_sha256": PINS["files"][av.P2_PROFILE]}, "P1's record does not record the pinned sandbox profile"),
    ({"authorization_entry_sha256": "8" * 64}, None, "the sidecar was not made under this text of the authorizing entry"),
    ({"authorization_entry_sha256": DROP}, None, "the sidecar was not made under this text of the authorizing entry"),
    ({}, {"authorization_entry_sha256": "8" * 64}, "P1's record was not made under this text of the authorizing entry"),
    ({"status": "in_progress"}, None, "does not say the audit completed"),
    ({}, {"status": "in_progress"}, "does not say the flag build completed"),
    ({"run_id": "e" * 32}, None, "do not name the same run"),
    ({"attempt_id": DROP}, None, "names no audit attempt"),
    ({"mask_sha256": "0" * 64}, None, "mask is not the one"),
    ({"mask_sha256": DROP}, None, "mask is not the one"),
    ({"p1_record_sha256": "0" * 64}, None, "record is not the one"),
    ({"inputs_sha256": {"quantities": "0" * 64}}, None, "not one P1 is recorded"),
    ({"inputs_sha256": {}}, {"quantities_written_sha256": DROP}, "not one P1 is recorded"),      # both missing: refused
    ({"inputs_sha256": DROP}, None, "not one P1 is recorded"),
    ({"definition_version": "x"}, None, "definition versions disagree"),
    ({"schema_version": 99}, None, "schema versions"),
    ({"quantities_columns_schema_version": DROP}, None, "schema versions"),
    ({}, {"quantities_columns_schema_version": 9}, "P1's record's schema versions"),
    ({"authorized_by": "D-901"}, None, "same authorization"),
    ({"rows": 7}, None, "row count"),
])
def test_an_inconsistent_bundle_is_refused(tmp_path, over, p1_over, words):
    from pipeline.electricity import preserve_availability as keep
    with pytest.raises(keep.BundleRefused, match=words):
        keep.verify_bundle(bundle(tmp_path, p1_over=p1_over, **over), "D-900", PINS)


def test_a_bundle_whose_authorizing_entry_has_since_changed_is_refused(tmp_path):
    """D-76, G8: the execution entry's words and pins are frozen; both records carry the hash of the text they ran under."""
    from pipeline.electricity import preserve_availability as keep
    with pytest.raises(keep.BundleRefused) as e:
        keep.verify_bundle(bundle(tmp_path), "D-900", {**PINS, "entry_sha256": "7" * 64})
    assert "the sidecar was not made under this text" in str(e.value) and "P1's record was not made under this text" in str(e.value)


def test_a_bundle_made_under_another_entry_is_refused(tmp_path):
    from pipeline.electricity import preserve_availability as keep
    with pytest.raises(keep.BundleRefused, match="made under D-900, not D-902"):
        keep.verify_bundle(bundle(tmp_path), "D-902", PINS)


def test_an_incomplete_bundle_is_refused_and_nothing_is_copied(tmp_path):
    from pipeline.electricity import preserve_availability as keep
    d = bundle(tmp_path)
    (d / "outcome_availability.json").unlink()
    with pytest.raises(keep.BundleRefused, match="incomplete bundle"):
        keep.preserve(d, tmp_path / "records", "D-900", PINS)
    assert not (tmp_path / "records").exists()


def test_preserve_stages_verifies_names_for_the_attempt_and_never_overwrites(tmp_path):
    import os
    from pipeline.electricity import preserve_availability as keep
    d = bundle(tmp_path)
    m = keep.preserve(d, tmp_path / "records", "D-900", PINS, today="2026-11-16")
    dest = Path(m["folder"])
    assert dest.name == "2026-11-16-availability-aaaaaaaa-cccccccc" and oct(dest.stat().st_mode & 0o777) == "0o500"
    assert all(oct((dest / f).stat().st_mode & 0o777) == "0o400" for f in (*keep.FILES, "MANIFEST.json"))
    assert m["run_id"] == "a" * 32 and set(m["files_sha256"]) == set(keep.FILES)
    assert not list((tmp_path / "records").glob("*.partial"))
    with pytest.raises(keep.BundleRefused, match="never overwritten"):
        keep.preserve(d, tmp_path / "records", "D-900", PINS, today="2026-11-16")
    os.chmod(dest, 0o700)


def test_an_interrupted_preservation_leaves_only_a_partial_folder_the_next_attempt_removes(tmp_path, monkeypatch):
    import os
    import shutil as sh
    from pipeline.electricity import preserve_availability as keep
    d = bundle(tmp_path)
    real, calls = sh.copyfile, []

    def fail_second(src, dst):
        calls.append(src)
        if len(calls) == 2:
            raise OSError("disk full (made up)")
        return real(src, dst)

    monkeypatch.setattr(keep.shutil, "copyfile", fail_second)
    with pytest.raises(OSError):
        keep.preserve(d, tmp_path / "records", "D-900", PINS, today="2026-11-16")
    left = list((tmp_path / "records").iterdir())
    assert [p.name for p in left] == ["2026-11-16-availability-aaaaaaaa-cccccccc.partial"]
    monkeypatch.setattr(keep.shutil, "copyfile", real)
    m = keep.preserve(d, tmp_path / "records", "D-900", PINS, today="2026-11-16")
    assert m["removed_incomplete_attempt"].endswith(".partial")
    assert [p.name for p in (tmp_path / "records").iterdir()] == ["2026-11-16-availability-aaaaaaaa-cccccccc"]
    os.chmod(m["folder"], 0o700)


def test_a_source_that_changes_while_it_is_copied_is_not_preserved(tmp_path, monkeypatch):
    import json
    from pipeline.electricity import preserve_availability as keep
    d = bundle(tmp_path)
    real, calls = keep.shutil.copyfile, []

    def change_after_first(src, dst):
        r = real(src, dst)
        calls.append(src)
        if len(calls) == 1:                                    # the mask is copied; a new mask and sidecar land in the source
            (d / "outcome_availability.csv").write_text(",".join(av.MASK_COLUMNS) + "\n2,GA,2020,True,none,known,not_used\n")
            side = json.loads((d / "outcome_availability.json").read_text())
            side["mask_sha256"] = keep.sha(d / "outcome_availability.csv")
            (d / "outcome_availability.json").write_text(json.dumps(side))
        return r

    monkeypatch.setattr(keep.shutil, "copyfile", change_after_first)
    with pytest.raises(keep.BundleRefused, match="mask is not the one|source changed"):
        keep.preserve(d, tmp_path / "records", "D-900", PINS, today="2026-11-16")
    assert not [p for p in (tmp_path / "records").iterdir() if not p.name.endswith(".partial")]


FINAL = "2026-11-16-availability-aaaaaaaa-cccccccc"


def test_the_final_name_appears_only_on_a_folder_already_complete_and_restricted(tmp_path, monkeypatch):
    """D-76, G7: the rename is the last change. At the moment the folder takes its final name it already holds the
    verified files and the manifest, all read-only, and is itself read-only."""
    import os
    from pipeline.electricity import preserve_availability as keep
    d = bundle(tmp_path)
    seen, real = [], os.rename

    def watch(src, dst):
        src = Path(src)
        seen.append((oct(src.stat().st_mode & 0o777), sorted((f.name, oct(f.stat().st_mode & 0o777)) for f in src.iterdir())))
        return real(src, dst)

    monkeypatch.setattr(keep.os, "rename", watch)
    m = keep.preserve(d, tmp_path / "records", "D-900", PINS, today="2026-11-16")
    assert seen == [("0o500", sorted((f, "0o400") for f in (*keep.FILES, "MANIFEST.json")))]
    os.chmod(m["folder"], 0o700)


def test_a_failure_at_the_folder_permission_change_leaves_only_a_partial_folder(tmp_path, monkeypatch):
    """The failure the outside read named (between the rename and the folder's permission change) can no longer leave
    a final folder: the permission change now comes first, so a failure there leaves a .partial folder only."""
    import os
    from pipeline.electricity import preserve_availability as keep
    d = bundle(tmp_path)
    real = os.chmod

    def fail_on_the_folder(path, mode, **k):
        if mode == 0o500:
            raise PermissionError("made up")
        return real(path, mode, **k)

    monkeypatch.setattr(keep.os, "chmod", fail_on_the_folder)
    with pytest.raises(PermissionError):
        keep.preserve(d, tmp_path / "records", "D-900", PINS, today="2026-11-16")
    assert [p.name for p in (tmp_path / "records").iterdir()] == [FINAL + ".partial"]


@pytest.mark.parametrize("failure", [OSError("made up"), KeyboardInterrupt(), MemoryError()])
def test_a_failure_after_the_folder_is_named_is_a_late_failure_never_nothing_preserved(tmp_path, monkeypatch, failure):
    """D-76, G7: whatever stops the step after the rename, the final folder exists, and the step says so."""
    import os
    from pipeline.electricity import preserve_availability as keep
    d = bundle(tmp_path)

    def fail(final):
        raise failure

    monkeypatch.setattr(keep, "_confirm_final", fail)
    with pytest.raises(keep.LateFailure) as e:
        keep.preserve(d, tmp_path / "records", "D-900", PINS, today="2026-11-16")
    final = tmp_path / "records" / FINAL
    assert e.value.folder == str(final) and e.value.stage == "confirm the named folder" and e.value.cause == type(failure).__name__
    assert [p.name for p in (tmp_path / "records").iterdir()] == [FINAL]                 # a final folder, no .partial
    assert sorted(p.name for p in final.iterdir()) == sorted([*keep.FILES, "MANIFEST.json"])
    monkeypatch.undo()
    with pytest.raises(keep.BundleRefused, match="never overwritten.*returns to Joe"):   # no automatic recovery
        keep.preserve(d, tmp_path / "records", "D-900", PINS, today="2026-11-16")
    os.chmod(final, 0o700)


def test_the_named_folder_is_confirmed_before_success_is_reported(tmp_path):
    import os
    from pipeline.electricity import preserve_availability as keep
    d = bundle(tmp_path)
    m = keep.preserve(d, tmp_path / "records", "D-900", PINS, today="2026-11-16")
    final = Path(m["folder"])
    keep._confirm_final(final)
    os.chmod(final, 0o700)
    with pytest.raises(OSError):                                                         # not restricted: not confirmed
        keep._confirm_final(final)
    os.chmod(final / "MANIFEST.json", 0o600)
    (final / "MANIFEST.json").unlink()
    os.chmod(final, 0o500)
    with pytest.raises(OSError):                                                         # a file missing: not confirmed
        keep._confirm_final(final)
    os.chmod(final, 0o700)


def test_isolation_check_stops_outside_the_sandbox(tmp_path, monkeypatch):
    profile, probe = tmp_path / "p.sb", tmp_path / "probe.txt"
    profile.write_text("(version 1)")
    probe.write_text("readable")
    monkeypatch.delenv(guard.PROFILE_ENV, raising=False)
    monkeypatch.delenv(guard.PROBE_ENV, raising=False)
    with pytest.raises(guard.Refusal) as e:
        guard.check_isolation(profile, probe)
    assert e.value.code == 3
    monkeypatch.setenv(guard.PROFILE_ENV, guard.sha256(profile))
    with pytest.raises(guard.Refusal, match="did not read the probe outside"):
        guard.check_isolation(profile, probe)
    monkeypatch.setenv(guard.PROBE_ENV, guard.PROBE_READ_OUTSIDE)
    with pytest.raises(guard.Refusal, match="probe file is readable"):        # the right hash, a readable probe: no sandbox
        guard.check_isolation(profile, probe)


def test_a_probe_refused_by_file_permissions_does_not_pass_for_isolation(tmp_path, monkeypatch):
    import os
    profile, probe = tmp_path / "p.sb", tmp_path / "probe.txt"
    profile.write_text("(version 1)")
    probe.write_text("x")
    os.chmod(probe, 0)
    monkeypatch.setenv(guard.PROFILE_ENV, guard.sha256(profile))
    monkeypatch.setenv(guard.PROBE_ENV, guard.PROBE_READ_OUTSIDE)
    try:
        with pytest.raises(guard.Refusal, match="file permissions, not the sandbox"):
            guard.check_isolation(profile, probe)
    finally:
        os.chmod(probe, 0o600)


# ---- source checks (supporting evidence, not proof) ---------------------------------------------------

def source(module):
    return Path(module.__file__).read_text()


def test_p1_prints_only_its_predetermined_lines():
    s = source(p1)
    prints = re.findall(r"print\((.*)\)", s)
    allowed = ("f\"P1 availability flag build", "f\"inputs: ", "f\"outcomes identical", "f\"by-unit files identical",
               "f\"existing quantity columns", "f\"flag equals", "f\"one first exclusion reason", "\"wrote nothing\"", "f\"wrote: ")
    assert prints and all(p.startswith(allowed) for p in prints), prints
    for banned in ("assert_frame_equal", "import logging", "to_string(", ".describe(", "breakpoint("):
        assert banned not in s


def test_p2_reads_one_data_file_and_imports_nothing_that_reads_revenue():
    s = source(p2)
    for banned in ("glob", "listdir", "scandir", "os.walk", "subprocess", "import duckdb", "electricity import panel",
                   "load_outcomes", "data\" / \"blind", "data\" / \"raw", "assert_frame_equal", "import logging"):
        assert banned not in s, banned
    prints = re.findall(r"print\((.*)\)", s)
    assert all(p.startswith(("f\"P2 availability audit", "f\"read: ", "\"first applicable exclusion reason", "f\"wrote: "))
               for p in prints), prints


def test_codes_module_does_no_io():
    s = source(av)
    assert not re.search(r"\bopen\(|import (os|pandas|pathlib)|from pipeline", s)


# ---- eligibility (the outcome rule) -------------------------------------------------------------------

def mask_of(units, missing=()):
    rows = [(u, s, y, (u, s, y) not in set(missing)) for u, s in units for y in av.PANEL_YEARS]
    m = pd.DataFrame(rows, columns=["utility_id_eia", "state", "year", "usable"])
    m["first_exclusion_reason"] = np.where(m.usable, av.NO_EXCLUSION, "price_not_above_zero")
    return m


def test_full_window_rule():
    w = avail.stacked_window(2015)
    assert w == tuple(range(2009, 2019)) and 2012 in w                      # ten years, the reference year included
    full = avail.usable_set(mask_of([(1, "AA")]))
    assert avail.eligible(full, (1, "AA"), w)
    assert not avail.eligible(avail.usable_set(mask_of([(1, "AA")], [(1, "AA", 2012)])), (1, "AA"), w)   # reference year
    assert not avail.eligible(avail.usable_set(mask_of([(1, "AA")], [(1, "AA", 2018)])), (1, "AA"), w)   # nine of ten
    assert avail.eligible(avail.usable_set(mask_of([(1, "AA")], [(1, "AA", 2003)])), (1, "AA"), w)       # outside the window
    assert not avail.eligible(full, (2, "AA"), w)                                                         # wholly absent


def test_the_mask_feeds_design_build_and_drops_by_name():
    from test_matching_rules import FUEL, ladder, world
    hosts = [(1, "AA", 10_000, "cooperative"), (2, "AA", 10_000, "cooperative")]
    comps = ladder(10, 12)
    treated, clean, q, regions, dd = world(hosts, comps)
    units = [(u, s) for u, s, *_ in hosts + comps]
    m = mask_of(units, [(10, "AA", 2012), (2, "AA", 2010)])
    d = design.build(treated, clean, q, regions, FUEL, dd, usable=avail.usable_set(m))
    assert list(d.hosts.key) == [(1, "AA")]
    assert d.dropped == [{"utility": "2:AA", "cohort": 2015, "why": design.NOT_USABLE}]
    assert (10, "AA") not in [tuple(k) for k in d.hosts.match_keys.iloc[0]]


def test_permitted_windows_include_every_cohort_and_both_forms_of_the_second_estimate():
    w = avail.permitted_windows()
    assert {f"cohort_{g}" for g in range(2011, 2023)} <= set(w)
    assert w["second_estimate_long_difference"] == (2008, 2009, 2010, 2023, 2024, 2025)
    assert w["second_estimate_panel"] == tuple(range(2005, 2026))


# ---- the provisional narrowing (ruling, item 8) -------------------------------------------------------

def test_narrowing_drops_only_units_that_fail_every_permitted_window():
    units = [(1, "AA"), (2, "AA"), (3, "AA")]
    # 2: usable only in the long difference's six years. 3: never usable.
    only_long = [(2, "AA", y) for y in av.PANEL_YEARS if y not in (2008, 2009, 2010, 2023, 2024, 2025)]
    never = [(3, "AA", y) for y in av.PANEL_YEARS]
    r = avail.provisional_narrowing(mask_of(units, only_long + never), units)
    assert r["narrowed"] == {(3, "AA")}
    assert r["kept"][(2, "AA")] == ["second_estimate_long_difference"]
    assert len(r["kept"][(1, "AA")]) == len(avail.permitted_windows())


def test_narrowing_does_not_depend_on_who_the_hosts_are():
    import inspect
    assert list(inspect.signature(avail.provisional_narrowing).parameters) == ["mask", "units"]


def test_a_shared_question_is_never_retired_with_one_utility():
    narrowed = {(3, "AA"), (4, "AA")}
    qs = [{"question_id": "a", "utilities": [(3, "AA")], "moves_anchoring": False},
          {"question_id": "b", "utilities": [(3, "AA"), (1, "AA")], "moves_anchoring": False},
          {"question_id": "c", "utilities": [(3, "AA"), (4, "AA")], "moves_anchoring": True},
          {"question_id": "d", "utilities": [], "moves_anchoring": False},
          {"question_id": "e", "utilities": [(4, "AA")]}]                              # anchoring unknown: kept
    r = avail.retirable_questions(qs, narrowed)
    assert r["retirable"] == ["a"]
    assert set(r["kept"]) == {"b", "c", "d", "e"} and "1:AA" in r["kept"]["b"]


def test_a_changed_flag_or_window_makes_the_screen_stale():
    units = [(1, "AA"), (3, "AA")]
    m = mask_of(units, [(3, "AA", y) for y in av.PANEL_YEARS])
    fp = avail.provisional_narrowing(m, units)["fingerprint"]
    assert avail.screen_still_valid(fp, m)
    m2 = m.copy()
    m2.loc[(m2.utility_id_eia == 1) & (m2.year == 2015), "usable"] = False
    assert not avail.screen_still_valid(fp, m2)
    w = avail.permitted_windows()
    w["cohort_2011"] = tuple(range(2004, 2015))
    assert not avail.screen_still_valid(fp, m, w)


# ---- the design-side exclusion report (ruling, item 4) -------------------------------------------------

def test_design_exclusions_report_exactly_who_build_windows_drops():
    from test_matching_rules import FUEL, world
    comps = [(10 + i, st, 10_000 + 100 * i, "cooperative") for i, st in enumerate(["AA"] * 4 + ["BB"] * 3 + ["ZZ"])]
    treated, clean, q, regions, dd = world([(1, "AA", 10_000, "cooperative")], comps)
    regions.loc[(regions.utility_id_eia == 11) & (regions.year == 2016), "region"] = None       # no region one window year
    dd = dd.copy()
    dd.loc[("BB", 2013), "hdd"] = np.nan                                                          # no degree days one year
    q.loc[(q.utility_id_eia == 12) & (q.year == 2012), "res_customers"] = 0                      # nobody in the reference year
    units = [(1, "AA")] + [(u, s) for u, s, *_ in comps]
    usable = avail.usable_set(mask_of(units))
    rep = avail.design_exclusions([2015], usable, units, q, regions, FUEL, dd)
    template = pd.DataFrame([(u, s, y) for u, s, y in usable], columns=KEY_Y).assign(log_price=0.0)
    unit_code = {k: i for i, k in enumerate(units)}
    state_code = {s: i for i, s in enumerate(sorted({s for _, s in units}))}
    w = ps.build_windows([2015], template, q, regions, FUEL, dd, unit_code, state_code)[2015]
    dropped = {(int(r.utility_id_eia), r.state) for r in rep.itertuples()}
    assert set(units) - dropped == {tuple(k) for k in w.keys}
    whys = {(int(r.utility_id_eia), r.state): r.why for r in rep.itertuples()}
    assert whys[(11, "AA")] == "no region in some window year"
    assert whys[(12, "AA")] == "no residential customers in the reference year"
    assert whys[(17, "ZZ")] == "no fuel-mix group; no heating degree days in some window year; no cooling degree days in some window year"
    assert all("heating degree days" in whys[(u, "BB")] for u in (14, 15, 16))


def test_second_estimate_exclusions_report_both_forms():
    from test_matching_rules import world
    comps = [(10 + i, "AA", 10_000 + 100 * i, "cooperative") for i in range(4)]
    treated, clean, q, regions, dd = world([(1, "AA", 10_000, "cooperative")], comps)
    regions.loc[(regions.utility_id_eia == 11) & (regions.year == 2024), "region"] = None    # in both forms' windows
    regions.loc[(regions.utility_id_eia == 12) & (regions.year == 2015), "region"] = None    # in the panel form's only
    q.loc[(q.utility_id_eia == 13) & (q.year == 2010), "res_customers"] = 0                 # the long difference's size year
    units = [(1, "AA")] + [(u, s) for u, s, *_ in comps]
    rep = avail.second_estimate_exclusions(avail.usable_set(mask_of(units)), units, q, regions)
    got = {(r.form, int(r.utility_id_eia)): r.why for r in rep.itertuples()}
    assert got == {("long_difference", 11): "no region in some year of the window",
                   ("panel", 11): "no region in some year of the window",
                   ("panel", 12): "no region in some year of the window",
                   ("long_difference", 13): "no residential customers in 2010"}


KEY_Y = ["utility_id_eia", "state", "year"]
