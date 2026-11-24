"""The references of the exact attribution and of the place test against the brute-force enumerator
(docs/gate1/reference-repair-rule-2026-11-18.md, section 8.4).

Load and sales only; no price is read. Every state is made up with mini() from tests/test_pass_c_expand.py and is small
enough for the full product of its reference settings.

Written to the interface of the rule's section 7 and of docs/gate1/exact-attribution-brief-2026-11-16.md, without
sight of the implementation (agent B's checkout never opened pipeline/facilities/pass_c_exact.py at any version), and
not run there. Everything that depends on that interface is in the two helpers under "The interface" below, so that a
difference in field names is mended in one place. The implementation is imported inside them: a missing or broken
module fails loudly rather than skipping.

What is compared, state by state (every case of the rule's section 8.2 and RANDOM_SEEDS' states):
* for every panel utility of the state, the exact attribution's reference (`defined`, `place`, `crossing`) equals the
  enumerator's with provisional_defines=True; its `searched` is true and `settings_enumerated` an integer from 1 to
  the enumerator's number of combinations (R3 can only merge, never add);
* for every utility the place test touches, whether `expand()`'s row has a reference, and its place and crossing,
  equal the enumerator's with provisional_defines=False;
* at least five of the states have a utility whose reference the enumerator finds undefined while every combination
  of the defining questions' first and last settings agrees (`differs_inside_only`), so this comparison cannot pass on
  cases the endpoint rule also gets right (counted, and the count asserted).
"""
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.facilities import pass_c_expand as px  # noqa: E402
from test_pass_c_expand import GWH, date, mini, split  # noqa: E402

import reference_enumerator as en  # noqa: E402
from test_reference_enumerator import HAND_CASES  # noqa: E402


# ---- The interface (the only interface-dependent code in this file) --------------------------------------------------

def implementation_references(inp, corrections: list[dict], st: str) -> dict:
    """{"<utility_id_eia>:<state>": {"defined", "place", "crossing", "searched", "settings_enumerated"}} from
    pass_c_exact.exact_attribution's reference records. Crossing as "2015"-style text, "never", or None."""
    from pipeline.facilities import pass_c_exact     # imported here: a missing implementation fails, it does not skip
    res = pass_c_exact.exact_attribution(inp, px.parse_corrections(corrections, inp), st, criterion="either_reading")
    out = {}
    for key, u in res["utilities"].items():
        r = u["reference"]
        out[key] = {"defined": bool(r["defined"]), "place": r["place"],
                    "crossing": None if r["crossing"] is None else str(r["crossing"]),
                    "searched": r["searched"], "settings_enumerated": r["settings_enumerated"]}
    return out


def place_test_references(inp, corrections: list[dict]) -> dict:
    """{"<utility_id_eia>:<state>": {"defined", "place", "crossing"}} for every utility expand()'s place test touches.
    A row's reference is a dict {"place", "crossing", "verdict"} where it has one, and text beginning "none" where not."""
    res = px.expand(corrections, inputs=inp)
    out = {}
    for row in res["utilities"]:
        r = row["reference"]
        if isinstance(r, str):
            assert r.startswith("none"), (row["utility"], r)
            out[row["utility"]] = {"defined": False, "place": None, "crossing": None}
        else:
            out[row["utility"]] = {"defined": True, "place": r["place"], "crossing": str(r["crossing"])}
    return out


# ---- the enumerator's answer in the same form -------------------------------------------------------------------------

def _key(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def expected(e: dict) -> dict:
    if not e["defined"]:
        return {"defined": False, "place": None, "crossing": None}
    return {"defined": True, "place": e["place"], "crossing": "never" if e["crossing"] is None else str(int(e["crossing"]))}


# ---- seeded random states ---------------------------------------------------------------------------------------------

MAX_COMBINATIONS = 96            # per state, with provisional_defines=True: keeps the full product small
EPRI_MULTIPLIERS = (0.04, 0.5, 0.8, 1.0, 1.5, 2.5, 30.0)   # the factor at the floor, moving, at the cap


def random_state(seed: int):
    """A made-up state from `seed`: (inputs, corrections, state). Raises ValueError where parse_corrections refuses it.

    Two to four sites on one to three utilities (some measured, some unresolved between two utilities); one to three
    date questions (intervals mostly reaching 2023 or later, "never" in some, open above in some; conventions absent,
    provisional or plain); a capacity split on some (with rest_earliest in some, convention absent or not); the EPRI
    total a multiple of the inventory's permit-based 2024 load, from far under it (the factor at the floor) to far over
    it (at the cap). Sizes and bases are drawn from continuous ranges and rounded to 1e-3, so ties with a threshold are
    left to RANDOM_SEEDS' check.
    """
    rng = random.Random(seed)
    st = "RS"
    n_util = rng.choice((1, 2, 2, 3))
    sites = []
    for i in range(rng.randint(2, 4)):
        u = rng.randint(1, n_util)
        s = {"fid": f"s{i}", "st": st, "u": u, "raw": round(rng.uniform(0.6, 5.0), 3), "year": rng.randint(2004, 2024)}
        if rng.random() < 0.15:
            s["basis"] = "verified_public_figure"
        elif n_util > 1 and rng.random() < 0.25:
            other = rng.choice([v for v in range(1, n_util + 1) if v != u])
            s.update(cands=f"{u};{other}", assign="smallest_polygon")
        sites.append(s)
    corrections = []
    dated = rng.sample([s["fid"] for s in sites], k=min(len(sites), rng.choice((1, 1, 2, 2, 3))))
    for fid in dated:
        e = None if rng.random() < 0.1 else rng.randint(2006, 2022)
        never = rng.random() < 0.35
        if never and rng.random() < 0.5:
            latest = None
        elif rng.random() < 0.75:
            latest = rng.randint(max(2023, e or 2023), 2026)
        else:
            latest = rng.randint(e or 2000, 2022)
        lo = e if e is not None else 1999
        hi = latest if latest is not None else 2026
        r = rng.random()
        if r < 0.45:
            conv, prov = None, False
        elif r < 0.75:
            conv, prov = rng.randint(lo, hi), True
        elif never and r < 0.8:
            conv, prov = "never", False
        else:
            conv, prov = rng.randint(lo, hi), False
        c = date(fid, e, latest, conv, never=never)
        if prov:
            c["convention_is"] = "provisional"
        corrections.append(c)
    if rng.random() < 0.35:
        s = rng.choice(sites)
        first = None if s["fid"] in dated else rng.randint(2004, s["year"])
        rest = None
        if rng.random() < 0.5:
            rest = rng.randint(max(first or 2004, s["year"] - 4), s["year"])
        conv = rng.choice((None, None, "early", "late"))
        corrections.append(split(s["fid"], first, rng.choice((0.3, 0.5, 0.6)), rest_earliest=rest, convention=conv))
    # The EPRI total against the inventory's permit-based 2024 load (raw), plus the measured load.
    def y24(s):
        a = s["year"]
        return 0.0 if a > 2024 else s["raw"] * min(1.0, (2024 - a + 1) / 3)
    permit = sum(y24(s) for s in sites if "basis" not in s)
    measured = sum(y24(s) for s in sites if "basis" in s)
    epri = rng.choice(EPRI_MULTIPLIERS) * max(permit, 0.5) + measured
    bases = {}
    for u in range(1, n_util + 1):
        bases[(u, st)] = 1e6 if rng.random() < 0.1 else round(rng.uniform(0.4, 9.0), 3) * GWH / 0.02
    inp = mini(sites, bases, {st: epri * GWH / 1000})
    px.parse_corrections(corrections, inp)            # refuses in words what cannot be applied
    return inp, corrections, st


# Seeds whose states are valid (parse_corrections accepts them), have at least one reference-defining question with
# provisional_defines=True and at most MAX_COMBINATIONS combinations, and put no load within one part in a million of
# the 2% threshold or of the 0.5% floor at any reference setting. Found by running random_state over seeds 0, 1, 2, ...
# and kept in order (seeds 0 to 60 tried, 44 kept); test_the_random_states_are_what_they_claim checks every condition
# again. When chosen (agent B, 2026-11-18), seeds 2 and 23 had a utility with an interior-only disagreement, and the
# unrepaired place test (pass_c_expand.expand at commit 466a1fe) called both references defined ("neither", never).
RANDOM_SEEDS = [1, 2, 3, 4, 5, 6, 7, 9, 10, 12, 15, 16, 17, 19, 21, 22, 23, 24, 25, 26, 27, 31, 32, 34, 35, 36, 39, 40,
                41, 42, 43, 44, 45, 47, 48, 50, 52, 53, 55, 56, 57, 58, 59, 60]


def _random_builder(seed):
    return lambda: random_state(seed)


STATES = {**{f"hand_{name}": build for name, build in HAND_CASES.items()},
          **{f"seed_{seed}": _random_builder(seed) for seed in RANDOM_SEEDS}}


def enumerated(build):
    inp, corrections, st = build()
    t_exact = en.table(inp, corrections, st, provisional_defines=True)
    t_place = en.table(inp, corrections, st, provisional_defines=False)
    return inp, corrections, st, t_exact, t_place


# ---- the checks that need no implementation ---------------------------------------------------------------------------

def test_there_are_at_least_forty_random_states():
    assert len(RANDOM_SEEDS) >= 40 and len(set(RANDOM_SEEDS)) == len(RANDOM_SEEDS)


@pytest.mark.parametrize("seed", RANDOM_SEEDS)
def test_the_random_states_are_what_they_claim(seed):
    inp, corrections, st, t_exact, t_place = enumerated(_random_builder(seed))
    assert t_exact["questions"] and 1 <= t_exact["combinations"] <= MAX_COMBINATIONS
    for t in (t_exact, t_place):
        for r in t["rows"]:
            assert min(r["gap"].values()) > 1e-6, (seed, r["setting"])


def test_the_states_cover_what_section_8_4_names():
    """Intervals reaching 2023 or later, "never", provisional marks, capacity splits, factors that move, that are held at
    the cap and that are held at the floor; and at least five states with an interior-only disagreement."""
    seen = {"reaches_2023": 0, "never": 0, "provisional": 0, "capacity": 0, "rest_earliest": 0,
            "factor_moves": 0, "factor_at_cap": 0, "factor_at_floor": 0}
    inside = []
    for name, build in STATES.items():
        inp, corrections, st, t_exact, t_place = enumerated(build)
        for c in corrections:
            if c["kind"] == "date":
                seen["reaches_2023"] += c["latest"] is None or c["latest"] >= 2023
                seen["never"] += bool(c["never_is_possible"])
                seen["provisional"] += c.get("convention_is") == "provisional"
            if c["kind"] == "capacity_split":
                seen["capacity"] += 1
                seen["rest_earliest"] += c.get("rest_earliest") is not None
        factors = {r["factor"] for r in t_exact["rows"]}
        seen["factor_moves"] += len(factors) > 1
        seen["factor_at_cap"] += px.SCALE_HI in factors
        seen["factor_at_floor"] += px.SCALE_LO in factors
        refs = {**{(k, True): v for k, v in en.from_table(t_exact).items()},
                **{(k, False): v for k, v in en.from_table(t_place).items()}}
        if any(v["differs_inside_only"] for v in refs.values()):
            inside.append(name)
    assert all(v > 0 for v in seen.values()), seen
    assert len(inside) >= 5, inside


# ---- the comparison (needs the implementation) -------------------------------------------------------------------------

@pytest.mark.parametrize("name", list(STATES))
def test_the_exact_attributions_reference_is_the_enumerators(name):
    inp, corrections, st, t_exact, _ = enumerated(STATES[name])
    want = {_key(k): expected(v) for k, v in en.from_table(t_exact).items()}
    got = implementation_references(inp, corrections, st)
    assert set(got) == set(want), (name, sorted(got), sorted(want))
    for key in want:
        g = got[key]
        assert {f: g[f] for f in ("defined", "place", "crossing")} == want[key], (name, key, g, want[key])
        assert g["searched"] is True, (name, key, g)
        assert isinstance(g["settings_enumerated"], int) and 1 <= g["settings_enumerated"] <= t_exact["combinations"], \
            (name, key, g, t_exact["combinations"])


@pytest.mark.parametrize("name", list(STATES))
def test_the_place_tests_reference_is_the_enumerators(name):
    inp, corrections, st, _, t_place = enumerated(STATES[name])
    want = {_key(k): expected(v) for k, v in en.from_table(t_place).items()}
    got = place_test_references(inp, corrections)
    assert set(got) <= set(want), (name, sorted(set(got) - set(want)))
    for key, g in got.items():
        assert g == want[key], (name, key, g, want[key])
