#!/usr/bin/env python3
"""Step E: the inference comparison on made-up outcomes over the real final design. Reads NO price and NO outcome.

The specification is docs/gate1/step-e-rules-2026-11-18.md (D-95), with docs/DECISIONS.md D-49 (G0 to G6), D-59 rule 4
(the candidates, G7 to G10), D-59 item 7 (G11, G12) and D-61 sections 7 and 8 as the rules file amends them.

Subcommands, run in this order, each as a file (it starts worker processes), each building the design exactly as
design.main does (headline rules: the ownership table, the usable flag, the unknown-load file, the gas shares) on the
headline set at 2%:

  python3 -I pipeline/analysis/inference_comparison.py benchmark      [--workers=10] [--g8-ownership-only]
  python3 -I pipeline/analysis/inference_comparison.py write-budget
  python3 -I pipeline/analysis/inference_comparison.py stage1         [--workers=10] [--g8-ownership-only]
  python3 -I pipeline/analysis/inference_comparison.py stage2         [--workers=10] [--g8-ownership-only]

benchmark     E5.2, E5.3, E5.6. Seed 20261130; each candidate, 20 datasets for each of 13 processes, the full computation;
              seconds a dataset measured inside workers while every worker is busy. Writes only timings, projected
              hours, machine, workers, commit and fingerprint (data/frozen/inference_comparison_benchmark.json).
write-budget  E5.4. Reads the benchmark's timings only; writes data/frozen/inference_validation_budget.json.
stage1        E1.1 to E2.4. Seed 20261201; 2,000 datasets a process; all three candidates on the same datasets. Refuses
              without a benchmark of the same fingerprint projecting at most twelve hours, and without the budget file.
              Writes data/frozen/inference_comparison_stage1.json (per-dataset blocks under data/interim/inference_comparison/).
stage2        E5.1. Seed 20261202; the candidate stage 1 selected, alone; the budget's datasets a process. Refuses if stage 1
              selected nothing, on another seed, or to extend a finished run. Writes data/frozen/inference_validation_stage2.json.

Every driver: workers started fresh (spawn); a dataset's numbers depend only on (stage seed, process, dataset), never on
the worker count or block; resumable block by block; a fingerprint through design.run_fingerprint; a stop in words on any
missing input.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from pipeline.analysis import candidates as cd  # noqa: E402
from pipeline.analysis import design, estimator  # noqa: E402
from pipeline.analysis import inference_check as ic  # noqa: E402
from pipeline.analysis import ownership as own_rules  # noqa: E402
from pipeline.analysis import power_simulation as ps  # noqa: E402

FROZEN = ROOT / "data" / "frozen"
INTERIM = ROOT / "data" / "interim"
SUPPLIERS = Path(__file__).resolve().parent / "suppliers.csv"
OWN_FILES = ("pipeline/analysis/candidates.py", "pipeline/analysis/inference_comparison.py")

SEEDS = {"benchmark": 20261130, "stage1": 20261201, "stage2": 20261202}       # E5.2, E1.1, E5.1; each used nowhere else
BENCHMARK_DATASETS = 20                                                         # E5.2
STAGE1_DATASETS = 2000                                                          # E1.1
LADDER = (20_000, 10_000, 5_000)                                                # E5.4
STAGE1_HOURS, VALIDATION_HOURS = 12.0, 72.0                                     # E1.4 / E5.3, E5.4
OVERHEAD, WORKERS = 1.25, 10                                                    # E5.3
BLOCK = 25                                                                      # datasets a block (resumability only)
SCREEN_RATE, SCREEN_ALPHA_TOTAL = 0.10, 0.05                                    # E1.2
STANDARD = 0.11                                                                 # E5.1
Z_ONE_SIDED_95 = 1.645

# ---- the thirteen price processes (D-49; D-59 rule 4.2; D-59 item 7; D-61 section 8) --------------------------------
G7_SCALE, G7_COMPARISONS, G7_HOSTS = 3.0, 5, 2
G8_SD, G8_RHO = 0.02, 0.6
G9_LOADING_SD = 0.5
G10_TREND_SD = 0.005
G11_STEP_SD = 0.05
G12_STATE_DEVIATION_SD = 0.1
ADDED = {
    "G7_high_variance_where_the_weight_is": "G0 with own noise times 3 at the 5 comparison utilities with the largest net weight and the "
                                            "2 hosts with the largest weight on the final design, the same units in every dataset",
    "G8_company_and_supplier_shocks": "G0 plus a shock (sd 0.02, persistence 0.6) for each ultimate parent in ownership.csv and each "
                                      "supplier in suppliers.csv, shared by all of its units in every state",
    "G9_unequal_regional_exposure": "G0 with each utility's loading on its region's walk 1 + 0.5 z",
    "G10_own_trends": "G0 plus a linear trend for each utility, sd 0.5% a year",
    "G11_fuel_shocks_linear_in_the_share": "G0 plus a national walk (step 0.05) loaded by the state's 2008-2010 gas share",
    "G12_fuel_shocks_not_linear_in_the_share": "G0 plus the same walk loaded by the square root of the share plus a state deviation "
                                               "(sd 0.1, fixed within a dataset)",
}
PROCESSES = tuple(ic.GRID) + tuple(ADDED)
assert len(PROCESSES) == 13
WALK_PROCESSES = ("G11_fuel_shocks_linear_in_the_share", "G12_fuel_shocks_not_linear_in_the_share")
G8_OWNERSHIP_ONLY = "--g8-ownership-only"


class Refused(SystemExit):
    """A driver that will not run, with its reason in words (exit status 2)."""

    def __init__(self, why: str):
        super().__init__(2)
        self.why = why

    def __str__(self) -> str:
        return self.why


# ================================================================================================================
# Seeds (E1.5)
# ================================================================================================================

def streams(stage_seed: int, p: int, k: int) -> tuple[np.random.Generator, np.random.SeedSequence]:
    """Dataset k of process p: its own data generator from (stage seed, p, k, 0) and a SEPARATE bootstrap seed from
    (stage seed, p, k, 1) (E1.5). Each candidate that draws builds a fresh generator from the bootstrap seed, so every
    candidate sees the same dataset and the same weights, and adding or removing a candidate changes nothing for another."""
    return (np.random.default_rng(np.random.SeedSequence([stage_seed, p, k, 0])),
            np.random.SeedSequence([stage_seed, p, k, 1]))


def bootstrap_weights(boot_seed: np.random.SeedSequence, boot: int, clusters: int) -> np.ndarray:
    return estimator.rademacher(np.random.default_rng(boot_seed), boot, clusters)


# ================================================================================================================
# The design-level context
# ================================================================================================================

def label(k) -> str:
    return f"{int(k[0])}:{k[1]}"


def g7_units(d: design.Design, fuel_control: str = ps.GAS_SHARE) -> dict:
    """G7's seven utilities from the final design's weights, quantities only (D-59 rule 4.2): the five comparison utilities
    with the largest net weight (inference_check.net_weights) and the two hosts with the largest headline weight."""
    wt = ic.implied_weights(d, fuel_control)
    net = ic.net_weights(wt).net_weight
    head = wt[wt.is_host & wt.event_year.isin(ps.HEADLINE)].groupby("utility").weight.sum().sort_values(ascending=False, kind="stable")
    comps = list(net.sort_values(ascending=False, kind="stable").index[:G7_COMPARISONS])
    hosts = list(head.index[:G7_HOSTS])
    return {"comparison_utilities": [{"utility": label(k), "net_weight": round(float(net[k]), 6)} for k in comps],
            "hosts": [{"utility": label(k), "weight": round(float(head[k]), 6)} for k in hosts],
            "keys": [tuple(k) for k in comps + hosts], "weights": wt}


def host_weights(wt: pd.DataFrame) -> list:
    """(cohort, headline weight) of each host's block: the sum of its rows' weights in event years 2 and 3."""
    head = wt[wt.is_host & wt.event_year.isin(ps.HEADLINE)]
    return [(int(c), float(w)) for (_, c), w in head.groupby(["utility", "cohort"]).weight.sum().items()]


SUPPLIER_COLUMNS = ("utility_id_eia", "state", "name", "supplier", "supplier_kind", "from_year", "to_year", "from_year_basis",
                    "to_year_basis", "source_url", "source_kind", "quote", "date_opened", "note")


def load_suppliers(path: Path | None = None, ownership_only: bool = False) -> tuple[pd.DataFrame | None, str]:
    """The supplier table for G8, or (None, mode) when G8 runs on ownership alone by the labelled flag. Stops in words if
    the file is absent and the flag was not given, or if it lacks a column or a year."""
    path = path or SUPPLIERS
    if ownership_only:
        return None, "ownership only (labelled: --g8-ownership-only); no supplier shock"
    if not path.exists():
        raise Refused(f"{path} is missing: G8 needs each unit's suppliers (D-59 rule 4.2). Wait for the supplier table, or run "
                      f"G8 on ownership alone with the labelled flag {G8_OWNERSHIP_ONLY} (recorded in the output and the fingerprint)")
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in SUPPLIER_COLUMNS if c not in t.columns]
    if missing:
        raise Refused(f"{path.name} lacks columns {missing}; G8 cannot be built")
    t = t.apply(lambda c: c.str.strip())
    for i, r in t.iterrows():
        try:
            int(r.utility_id_eia), int(r.from_year), int(r.to_year)
        except ValueError:
            raise Refused(f"row {i + 2} of {path.name} has an id or year that is not a whole number; G8 cannot be built") from None
    t["utility_id_eia"] = t.utility_id_eia.astype(int)
    t["from_year"], t["to_year"] = t.from_year.astype(int), t.to_year.astype(int)
    return t, f"ownership and suppliers ({path.name}, sha256 {hashlib.sha256(path.read_bytes()).hexdigest()})"


def g8_loadings(unit_keys: list, ownership: pd.DataFrame | None, suppliers: pd.DataFrame | None,
                years=range(ic.FIRST_YEAR, ic.LAST_YEAR + 1)) -> dict:
    """Which shock each unit carries in each year (D-59 rule 4.2; the session's working-out where the rule is silent).

    Company: the unit's ultimate parents that year (ownership.parents; a blank state means every state); a unit with no
    row that year is its own company. Supplier: suppliers.csv rows for the unit (its state, or blank for every state)
    whose spell covers the year; a unit with no row, or whose supplier is "unknown" or blank, gets no supplier shock.
    Where a unit has two parents (the year a sale closes, rule 2.1) or two suppliers in a year, it carries their MEAN, so
    every unit carries one company shock's worth and at most one supplier shock's worth. Returns index arrays
    (unit, year, entity, weight) and the entity names, fixed before any dataset is drawn."""
    years = list(years)
    ents: dict = {}
    rows, cols, ent, wts = [], [], [], []

    def eid(name):
        return ents.setdefault(name, len(ents))

    def spells(table, col):
        """id -> [(state, from, to, name)]: the same rows ownership.parents reads (a blank state means every state)."""
        out: dict = {}
        if table is None or not len(table):
            return out
        for r in table.itertuples():
            out.setdefault(int(r.utility_id_eia), []).append((r.state, int(r.from_year), int(r.to_year), getattr(r, col)))
        return out

    def covering(sp, key, y):
        return sorted({n for st, lo, hi, n in sp.get(key[0], ()) if (st == key[1] or st == "") and lo <= y <= hi})
    own_sp, sup_sp = spells(ownership, "ultimate_parent"), spells(suppliers, "supplier")
    counts = {"units": len(unit_keys), "unit_years_with_a_parent_from_the_table": 0, "unit_years_their_own_company": 0,
              "unit_years_with_a_supplier": 0}
    for u, key in enumerate(unit_keys):
        key = (int(key[0]), key[1])
        for t, y in enumerate(years):
            parents = covering(own_sp, key, y)
            if parents:
                counts["unit_years_with_a_parent_from_the_table"] += 1
                names = [f"company:{p}" for p in parents]
            else:
                counts["unit_years_their_own_company"] += 1
                names = [f"company:own:{label(key)}"]
            for n in names:
                rows.append(u), cols.append(t), ent.append(eid(n)), wts.append(1.0 / len(names))
            s_names = [n for n in covering(sup_sp, key, y) if n and n.lower() != "unknown"]
            if s_names:
                counts["unit_years_with_a_supplier"] += 1
            for n in s_names:
                rows.append(u), cols.append(t), ent.append(eid(f"supplier:{n}")), wts.append(1.0 / len(s_names))
    counts["companies"] = sum(1 for n in ents if n.startswith("company:") and not n.startswith("company:own:"))
    counts["units_that_are_their_own_company_in_some_year"] = len({n for n in ents if n.startswith("company:own:")})
    counts["suppliers"] = sum(1 for n in ents if n.startswith("supplier:"))
    return {"unit": np.array(rows, dtype=int), "year": np.array(cols, dtype=int), "entity": np.array(ent, dtype=int),
            "weight": np.array(wts, dtype=float), "entities": len(ents), "counts": counts}


def build_context(d: design.Design, regions: pd.DataFrame, q: pd.DataFrame, ownership: pd.DataFrame | None,
                  suppliers: pd.DataFrame | None, g8_mode: str, rules: ps.Rules = ps.HEADLINE_RULES, boot: int = cd.BOOT,
                  names=cd.CANDIDATES) -> dict:
    """Everything a worker needs, fixed before any dataset is drawn: the assembled problem, the candidates' design-level
    precomputation, the units' region/state/ownership codes, G7's units, G8's loadings, the gas shares by unit, and each
    host's cohort and weight (for G11 and G12's realised path). Quantities only."""
    if d.gas is None:
        raise Refused("the design carries no gas shares: G11 and G12 load the walk by the state's 2008-2010 share (D-59 item 7)")
    # The made-up prices are drawn for every unit in the panel's codes (design.build's `everyone`), but only the rows of the
    # assembled design are ever read. A unit whose state has no row in fuel_mix_groups.csv (a territory such as AS) has no
    # fuel-mix group, so power_simulation.build_windows leaves it out of every window and it is never a host or a
    # comparison. That is checked here, in words, before anything is assembled.
    in_design = sorted({k[1] for g, tr, comp in d.blocks() for k in (d.windows[g].keys[r] for r in np.concatenate([tr, comp]))})
    bad = [st for st in in_design if st not in d.gas or not np.isfinite(float(d.gas[st]))]
    if bad:
        raise Refused(f"the assembled design has rows in {bad}, which have no 2008-2010 gas share: the design should never "
                      "admit them (build_windows needs a fuel-mix group from the same file); this is a defect on the design side, stopping")
    f = ic.fixed_parts(d, rules.fuel_control)
    problem = cd.Problem.from_fixed_parts(f)
    units = ic.unit_arrays(d, regions, q)
    keys = list(d.unit_code)
    # Every observed row's region must be a real one. unit_arrays fills a missing region with code 0 for units the design
    # never reads (job U's convention); a missing region on a row that IS read would silently take another region's walk.
    codes = {r: i for i, r in enumerate(sorted(regions.region.dropna().unique()))}
    raw = ps.region_matrix(regions, pd.MultiIndex.from_tuples(keys), range(ic.FIRST_YEAR, ic.LAST_YEAR + 1), codes)
    holes = np.isnan(raw[f["obs_unit"], f["obs_year"]])
    if holes.any():
        where = sorted({(label(keys[u]), ic.FIRST_YEAR + int(t)) for u, t in zip(f["obs_unit"][holes], f["obs_year"][holes])})
        raise Refused(f"rows of the assembled design have no market region in an observed year: {where[:10]}; the made-up "
                      "regional walk cannot be assigned, stopping")
    g7 = g7_units(d, rules.fuel_control)
    scale = np.ones(len(keys))
    for k in g7["keys"]:
        scale[d.unit_code[k]] = G7_SCALE
    states = sorted(d.state_code, key=d.state_code.get)
    # G11 and G12 load the walk by the state's share. A panel state with no share (no row in fuel_mix_groups.csv) has no
    # unit in the design (checked above); its units get NO fuel walk (loading zero, G12's deviation included), listed.
    has_share = np.array([s in d.gas and np.isfinite(float(d.gas[s])) for s in states])
    share_state = np.array([float(d.gas[s]) if ok else 0.0 for s, ok in zip(states, has_share)])
    no_share = [s for s, ok in zip(states, has_share) if not ok]
    design_units = np.unique(f["obs_unit"])
    ctx = {"problem": problem, "candidates": cd.prepare(problem, names, boot), "boot": boot, "names": tuple(names),
           "obs_unit": f["obs_unit"], "obs_year": f["obs_year"], **units,
           "g7_scale": scale, "g8": g8_loadings(keys, ownership, suppliers), "share_state": share_state, "has_share": has_share,
           "hosts": host_weights(g7["weights"]), "truth": 0.0}
    quantities = {"g7_units": {"comparison_utilities": g7["comparison_utilities"], "hosts": g7["hosts"]},
                  "g8": {"mode": g8_mode, **ctx["g8"]["counts"]},
                  "host_weights_sum_to": round(float(sum(w for _, w in ctx["hosts"])), 6),
                  "states_with_no_gas_share_given_no_fuel_walk": no_share,
                  "units_in_the_panel_codes": len(keys), "units_in_the_assembled_design": int(len(design_units)),
                  "design_units_with_an_ownership_class_outside_the_three":
                      int((units["owner_all"][design_units] == len(ic.OWNERSHIP)).sum()),
                  "clusters": int(problem.G), "rows": int(problem.N), "regressors": int(problem.K)}
    return {"ctx": ctx, "quantities": quantities}


# ================================================================================================================
# The made-up prices
# ================================================================================================================

def _ar1(rng, rows, years, rho, sd):
    e = rng.normal(0, 1.0, (rows, years))
    for t in range(1, years):
        e[:, t] += rho * e[:, t - 1]
    return e * sd


def realised_change(walk: np.ndarray, hosts: list) -> float:
    """The change in the common walk between each host's reference year and its event years 2 and 3 (their mean, as the
    headline), averaged over hosts with the design's weights (D-61 section 8)."""
    at = lambda year: walk[year - ic.FIRST_YEAR]  # noqa: E731
    return float(sum(w * (0.5 * (at(g + 2) + at(g + 3)) - at(g + ps.REF)) for g, w in hosts))


def draw(p: int, rng: np.random.Generator, ctx: dict) -> tuple[np.ndarray, float | None]:
    """Units by years log prices from process p, and (G11, G12) the realised change in the common walk.

    G0 to G6 are inference_check.made_up with inference_check.GRID, unchanged. G7 and G9 are made_up with one optional key
    each; G8, G10, G11 and G12 are G0 plus a part drawn after it from the same dataset generator."""
    name = PROCESSES[p]
    ra, sa, oa = ctx["region_all"], ctx["state_all"], ctx["owner_all"]
    base = ic.GRID["G0_as_in_D38"]
    if name in ic.GRID:
        return ic.made_up(ra, sa, oa, rng, ic.GRID[name]), None
    if name.startswith("G7_"):
        return ic.made_up(ra, sa, oa, rng, {**base, "own_scale_fixed": ctx["g7_scale"]}), None
    if name.startswith("G9_"):
        return ic.made_up(ra, sa, oa, rng, {**base, "region_loading_sd": G9_LOADING_SD}), None
    P = ic.made_up(ra, sa, oa, rng, base)
    n, years = P.shape
    if name.startswith("G8_"):
        g = ctx["g8"]
        shocks = _ar1(rng, g["entities"], years, G8_RHO, G8_SD)
        np.add.at(P, (g["unit"], g["year"]), g["weight"] * shocks[g["entity"], g["year"]])
        return P, None
    if name.startswith("G10_"):
        return P + rng.normal(0, G10_TREND_SD, n)[:, None] * np.arange(years)[None, :], None
    walk = rng.normal(0, G11_STEP_SD, years).cumsum()
    if name.startswith("G11_"):
        load = ctx["share_state"][sa]
    else:
        dev = rng.normal(0, G12_STATE_DEVIATION_SD, len(ctx["share_state"]))
        load = np.where(ctx["has_share"], np.sqrt(ctx["share_state"]) + dev, 0.0)[sa]     # no share: no walk
    return P + load[:, None] * walk[None, :], realised_change(walk, ctx["hosts"])


def dataset(stage_seed: int, p: int, k: int, ctx: dict) -> tuple[np.ndarray, np.random.SeedSequence, float | None]:
    rng, boot_seed = streams(stage_seed, p, k)
    P, change = draw(p, rng, ctx)
    return P[ctx["obs_unit"], ctx["obs_year"]], boot_seed, change


def run_candidates(y, boot_seed, ctx: dict, names=None) -> dict:
    out = {}
    for n in names or ctx["names"]:
        c = ctx["candidates"][n]
        v = bootstrap_weights(boot_seed, ctx["boot"], ctx["problem"].G) if n in ("A", "B") else None
        out[n] = c.run(y, ctx["truth"], v)
    return out


def one(stage_seed: int, p: int, k: int, ctx: dict) -> dict:
    y, boot_seed, change = dataset(stage_seed, p, k, ctx)
    return {"process": PROCESSES[p], "k": int(k), "realised_change": change, "results": run_candidates(y, boot_seed, ctx)}


# ================================================================================================================
# Workers and blocks
# ================================================================================================================

_W: dict = {}


def _init(ctx: dict, counter=None, workers: int = 0) -> None:
    _W.clear()
    _W.update(ctx=ctx, counter=counter, workers=workers)


def _block(args) -> dict:
    stage_seed, p, b, k0, k1 = args
    return {"process": PROCESSES[p], "p": p, "block": b, "k_from": k0, "k_to": k1,
            "records": [one(stage_seed, p, k, _W["ctx"]) for k in range(k0, k1)]}


def blocks(datasets: int, processes=range(len(PROCESSES)), block: int = BLOCK) -> list:
    return [(p, b, b * block, min(datasets, (b + 1) * block)) for p in processes for b in range((datasets + block - 1) // block)]


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=_jsonable) + "\n")
    tmp.replace(path)


def _jsonable(x):
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    return str(x)


def run_blocks(stage: str, stage_seed: int, ctx: dict, run_dir: Path, datasets: int, workers: int, manifest: dict) -> list:
    """Every block of the stage, resuming from the block files already written. Refuses a run directory written under
    another fingerprint, seed, size or candidate list. Returns every record in (process, dataset) order."""
    run_dir.mkdir(parents=True, exist_ok=True)
    mpath = run_dir / "manifest.json"
    if mpath.exists():
        old = json.loads(mpath.read_text())
        for key in ("fingerprint_sha256", "seed", "datasets_per_process", "candidates", "stage"):
            if old.get(key) != manifest.get(key):
                raise Refused(f"{run_dir} holds a {old.get('stage')} run with {key} = {old.get(key)!r}, not {manifest.get(key)!r}; "
                              "a run is resumed only with the same seeds, size, candidates and fingerprint")
    else:
        _write_json(mpath, manifest)
    todo = []
    for p, b, k0, k1 in blocks(datasets):
        f = run_dir / f"block_{p:02d}_{b:05d}.json"
        if not f.exists():
            todo.append((stage_seed, p, b, k0, k1))
    if todo:
        if workers <= 1:
            _init(ctx)
            for t in todo:
                r = _block(t)
                _write_json(run_dir / f"block_{r['p']:02d}_{r['block']:05d}.json", r)
        else:
            import multiprocessing as mp
            from concurrent.futures import ProcessPoolExecutor, as_completed
            with ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn"), initializer=_init, initargs=(ctx,)) as ex:
                futs = [ex.submit(_block, t) for t in todo]
                for fu in as_completed(futs):
                    r = fu.result()
                    _write_json(run_dir / f"block_{r['p']:02d}_{r['block']:05d}.json", r)
    out = []
    for p, b, k0, k1 in blocks(datasets):
        out += json.loads((run_dir / f"block_{p:02d}_{b:05d}.json").read_text())["records"]
    return out


# ================================================================================================================
# The benchmark (E5.2, E5.3, E5.6)
# ================================================================================================================

def _timed(args) -> list:
    """Time each candidate on each dataset of this worker's list, then stay busy, untimed, until every worker is done
    (E5.2: measured while all the workers are busy). The candidates' outputs are discarded here, unread (E5.6)."""
    stage_seed, items = args
    ctx, counter, workers = _W["ctx"], _W["counter"], _W["workers"]
    out = []
    for p, k in items:
        t0 = time.perf_counter()
        y, boot_seed, _ = dataset(stage_seed, p, k, ctx)
        row = {"process": PROCESSES[p], "generation": time.perf_counter() - t0, "candidates": {}}
        for n in ctx["names"]:
            t1 = time.perf_counter()
            run_candidates(y, boot_seed, ctx, [n])            # computed to be timed; the output is dropped unread
            row["candidates"][n] = time.perf_counter() - t1
        out.append(row)
    if counter is not None:
        with counter.get_lock():
            counter.value += 1
        p, k = items[0]
        while counter.value < workers:                        # padding: keeps this worker busy while others finish
            y, boot_seed, _ = dataset(stage_seed, p, k, ctx)
            run_candidates(y, boot_seed, ctx)
    return out


def benchmark_timings(ctx: dict, workers: int, datasets: int = BENCHMARK_DATASETS, seed: int = SEEDS["benchmark"]) -> list:
    """Per-dataset seconds (generation, and each candidate's full computation), from inside the workers."""
    items = [(p, k) for k in range(datasets) for p in range(len(PROCESSES))]
    lists = [items[i::workers] for i in range(workers)]
    lists = [x for x in lists if x]
    if workers <= 1:
        _init(ctx)
        return [r for x in lists for r in _timed((seed, x))]
    import multiprocessing as mp
    m = mp.get_context("spawn")
    counter = m.Value("i", 0)
    with m.Pool(len(lists), initializer=_init, initargs=(ctx, counter, len(lists))) as pool:
        parts = pool.map(_timed, [(seed, x) for x in lists], chunksize=1)
    return [r for x in parts for r in x]


def projections(seconds: dict, generation: dict, names=cd.CANDIDATES) -> dict:
    """E5.3: hours = 1.25 x N x (sum over processes of mean seconds a dataset) / (10 x 3,600).

    Stage 1 pays the dataset's generation once and every candidate; a validation run pays generation and one candidate."""
    per = lambda n: sum(generation[p] + seconds[n][p] for p in PROCESSES)  # noqa: E731
    hours = lambda n_ds, s: OVERHEAD * n_ds * s / (WORKERS * 3600.0)  # noqa: E731
    stage1 = hours(STAGE1_DATASETS, sum(generation[p] + sum(seconds[n][p] for n in names) for p in PROCESSES))
    return {"stage1_all_three_candidates_2000_a_process": round(stage1, 4),
            "validation_by_candidate": {n: {str(N): round(hours(N, per(n)), 4) for N in LADDER} for n in names},
            "formula": "1.25 x N x (sum over the 13 processes of mean seconds a dataset) / (10 x 3,600) (E5.3)"}


def summarise_timings(rows: list, names=cd.CANDIDATES) -> dict:
    gen = {p: float(np.mean([r["generation"] for r in rows if r["process"] == p])) for p in PROCESSES}
    sec = {n: {p: float(np.mean([r["candidates"][n] for r in rows if r["process"] == p])) for p in PROCESSES} for n in names}
    return {"seconds_a_dataset": {"generation_shared_by_the_candidates": {p: round(v, 6) for p, v in gen.items()},
                                  "by_candidate_and_process": {n: {p: round(v, 6) for p, v in sec[n].items()} for n in names},
                                  "timed_datasets_per_candidate_and_process": BENCHMARK_DATASETS if rows else 0},
            "projected_hours": projections(sec, gen, names)}


def machine() -> dict:
    return {"platform": platform.platform(), "processor": platform.processor() or platform.machine(), "logical_cpus": os.cpu_count(),
            "python": platform.python_version(), "numpy": np.__version__}


def commit() -> str | None:
    """HEAD's commit id, read from the repository's files (no git command). None if it cannot be read."""
    for parent in [ROOT, *ROOT.parents]:
        g = parent / ".git"
        if g.is_file() and g.read_text().startswith("gitdir: "):        # a worktree: .git names the real directory
            g = (parent / g.read_text()[8:].strip()).resolve()
        if g.is_dir():
            head = (g / "HEAD").read_text().strip()
            if not head.startswith("ref: "):
                return head
            ref = head[5:]
            if (g / ref).exists():
                return (g / ref).read_text().strip()
            packed = g / "packed-refs"
            if packed.exists():
                for line in packed.read_text().splitlines():
                    if line.endswith(" " + ref):
                        return line.split()[0]
            return None
    return None


def benchmark(ctx: dict, fp: dict, workers: int, out: Path, datasets: int = BENCHMARK_DATASETS) -> dict:
    """Times the full computation and writes timings only (E5.6). No rate, estimate, range, p-value, width, end state or
    failure count is computed, kept or written: the candidates' outputs never leave the workers."""
    rows = benchmark_timings(ctx, workers, datasets)
    report = {"what_this_is": "Step E's benchmark (E5.2, E5.3, E5.6): seconds a dataset by candidate and process, measured inside "
                              "the workers while all of them were busy, and the projected hours. The candidates' outputs were "
                              "computed to be timed and discarded unread.",
              "seed": SEEDS["benchmark"], "datasets_per_process": datasets, "processes": list(PROCESSES),
              "candidates": list(ctx["names"]), "bootstrap_replications": ctx["boot"],
              "workers": workers, "machine": machine(), "commit": commit(), "fingerprint": fp, **summarise_timings(rows, ctx["names"]),
              "twelve_hour_limit_for_stage_1": STAGE1_HOURS}
    _write_json(out, report)
    return report


# ================================================================================================================
# The budget (E5.4)
# ================================================================================================================

NONE_FITS = "none fits: return to the owner before stage 1"


def write_budget(bench_path: Path, out: Path) -> dict:
    """For each candidate, the largest of 20,000, 10,000 and 5,000 datasets a process whose projected validation is at most
    72 hours, from the benchmark's timings alone."""
    if not bench_path.exists():
        raise Refused(f"{bench_path} is missing: run the benchmark first (E5.2); the budget is fixed from timing alone (E5.4)")
    b = json.loads(bench_path.read_text())
    hours = b["projected_hours"]["validation_by_candidate"]
    budget = {}
    for n, by_n in hours.items():
        fits = [N for N in LADDER if by_n[str(N)] <= VALIDATION_HOURS]
        budget[n] = max(fits) if fits else NONE_FITS
    report = {"what_this_is": "The validation budget (E5.4), fixed for each candidate from the benchmark's timings alone, before stage 1.",
              "datasets_per_process_by_candidate": budget, "ceiling_hours": VALIDATION_HOURS, "ladder": list(LADDER),
              "projected_validation_hours": hours, "benchmark": str(bench_path.name), "fingerprint": b["fingerprint"],
              "benchmark_commit": b.get("commit")}
    _write_json(out, report)
    return report


# ================================================================================================================
# Stage 1: the screen, then width (E1.2, E2.1 to E2.4)
# ================================================================================================================

def screen_threshold(n: int, rate: float = SCREEN_RATE, alpha: float = SCREEN_ALPHA_TOTAL / 26) -> int:
    """The smallest count c with P(Binomial(n, rate) >= c) <= alpha: the exact one-sided test of "true rate at most 10%"
    at 0.05/26 (E1.2). At n = 2,000 it is 241."""
    c = int(stats.binom.ppf(1 - alpha, n, rate))
    while stats.binom.sf(c - 1, n, rate) > alpha:
        c += 1
    while c > 0 and stats.binom.sf(c - 2, n, rate) <= alpha:
        c -= 1
    return c


def clopper_pearson(k: int, n: int, level: float = 0.95) -> list:
    a = (1 - level) / 2
    lo = 0.0 if k == 0 else float(stats.beta.ppf(a, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1 - a, k + 1, n - k))
    return [round(lo, 5), round(hi, 5)]


def count(hits) -> dict:
    hits = np.asarray(hits, dtype=bool)
    n, k = len(hits), int(hits.sum())
    return {"count": k, "datasets": n, "rate": round(k / n, 5) if n else None, "exact_95_interval": clopper_pearson(k, n) if n else None}


def widths(w) -> dict:
    w = np.asarray(w, dtype=float)
    q = lambda x: float(np.quantile(w, x, method="inverted_cdf"))  # noqa: E731
    return {"median": float(np.median(w)), "p90": q(0.90), "p95": q(0.95), "infinite": int(np.isinf(w).sum())}


def median_interval_order(n: int, level: float = 0.95) -> int:
    """r for the distribution-free interval [d_(r), d_(n+1-r)] for a median: the largest r with P(Bin(n, 1/2) <= r-1) <= (1-level)/2."""
    a = (1 - level) / 2
    r = int(stats.binom.ppf(a, n, 0.5))
    while r >= 1 and stats.binom.cdf(r - 1, n, 0.5) > a:
        r -= 1
    while stats.binom.cdf(r, n, 0.5) <= a:
        r += 1
    return max(r, 1)


def paired_log_ratio(wx, wy) -> np.ndarray:
    """d = log(width X / width Y) per dataset; both infinite 0; one infinite +/- infinity (E2.2)."""
    wx, wy = np.asarray(wx, dtype=float), np.asarray(wy, dtype=float)
    ix, iy = np.isinf(wx), np.isinf(wy)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.log(wx / wy)
    d[ix & iy] = 0.0
    d[ix & ~iy] = np.inf
    d[~ix & iy] = -np.inf
    return d


def narrower(wx, wy, level: float = 0.95) -> tuple[bool, list]:
    """X is narrower than Y only if the distribution-free 95% interval for the median of d lies wholly below zero (E2.2)."""
    d = np.sort(paired_log_ratio(wx, wy))
    n = len(d)
    r = median_interval_order(n, level)
    lo, hi = float(d[r - 1]), float(d[n - r])
    return bool(hi < 0), [lo, hi]


def select(cells: dict, widths_by: dict, incomplete_or_failed_share: dict, n: int) -> dict:
    """The screen, then width (E1.2, E2.1, E2.2, E2.3). `cells[c]` = {cell name: count of n}; `widths_by[c]` = the pooled
    per-dataset widths, paired across candidates; `incomplete_or_failed_share[c]` = share of ranges with an incomplete or
    failed side. Width is looked at only among survivors.

    Among survivors (the session's working-out of the pairwise rule for three): the candidate with the narrowest pooled
    median W is compared with each other survivor Y; Y is out if W is narrower (E2.2); the others are tied with W. A tie
    including A goes to A; B tied with C goes to the lower share of incomplete and failed ranges, then to C."""
    thr = screen_threshold(n)
    over = {c: sorted(k for k, v in cs.items() if v >= thr) for c, cs in cells.items()}
    survivors = [c for c in cd.CANDIDATES if c in cells and not over[c]]
    out = {"screen": {"threshold_count": thr, "datasets_per_cell": n, "level": "0.05/26",
                      "cells_at_or_over_the_threshold": over, "survivors": survivors,
                      "note": "a screening rule, not certification: surviving it does not establish that all true rates are at most 10%"}}
    if not survivors:
        out.update(selected=None, statement="No candidate survives the screen (E1.2). No candidate is selected; the screen is not "
                                            "relaxed and no candidate is added (E2.3). No stage 2 is run, and nothing is called calibrated.")
        return out
    med = {c: float(np.median(widths_by[c])) for c in survivors}
    order = sorted(survivors, key=lambda c: (med[c], cd.CANDIDATES.index(c)))
    W = order[0]
    tied, comparisons = [W], {}
    for Y in order[1:]:
        is_narrower, ci = narrower(widths_by[W], widths_by[Y])
        comparisons[f"{W}_against_{Y}"] = {"narrower": is_narrower, "median_log_ratio_interval_95": ci}
        if not is_narrower:
            tied.append(Y)
    if "A" in tied:
        chosen, why = "A", "a tie including the bootstrap as built goes to it (E2.2)" if len(tied) > 1 else "narrowest"
    elif set(tied) == {"B", "C"}:
        sb, sc = incomplete_or_failed_share["B"], incomplete_or_failed_share["C"]
        chosen = "B" if sb < sc else "C"
        why = "B tied with C: the lower share of incomplete and failed ranges" + (", then C" if sb == sc else "")
    else:
        chosen, why = W, "narrower than every other survivor (E2.2)" if len(survivors) > 1 else "the only survivor"
    out["width"] = {"pooled_median_width": med, "comparisons": comparisons, "tied_with_the_narrowest": tied}
    out.update(selected=chosen, why=why)
    return out


def _side_shares(rs: list) -> dict:
    return {side: {s: round(sum(r[f"{side}_state"] == s for r in rs) / len(rs), 5) for s in cd.END_STATES} for side in ("lo", "hi")}


def _failures(rs: list) -> dict:
    causes, where = {}, {}
    for r in rs:
        if r["failure"]:
            causes[r["failure"]["cause"]] = causes.get(r["failure"]["cause"], 0) + 1
            where[r["failure"]["where"]] = where.get(r["failure"]["where"], 0) + 1
    return {"count": sum(bool(r["failure"]) for r in rs), "causes": causes, "where": where}


def realised_path(rs: list, changes: list) -> dict:
    """G11 and G12 (D-61 section 8): slope of the estimate on the realised change, the estimate's root-mean-square error
    about the true value (0), and miss and rejection counts within thirds of the datasets by the size (absolute value) of
    the realised change. Reported, never selecting. Slope and RMSE are over the datasets that computed, and say so."""
    ch = np.asarray(changes, dtype=float)
    ok = np.array([r["failure"] is None for r in rs])
    est = np.array([r["estimate"] for r in rs], dtype=float)
    fine = ok & np.isfinite(est)
    out = {"over": "datasets whose candidate computed an estimate", "datasets_used": int(fine.sum())}
    if fine.sum() > 1:
        x, yv = ch[fine], est[fine]
        out["slope_of_the_estimate_on_the_realised_change"] = float(np.polyfit(x, yv, 1)[0]) if np.ptp(x) > 0 else None
        out["root_mean_square_error"] = float(np.sqrt(np.mean(yv ** 2)))
    order = np.argsort(np.abs(ch), kind="stable")
    thirds = np.array_split(order, 3)
    out["thirds_by_size_of_the_realised_change"] = [
        {"absolute_change_from": float(np.abs(ch[t]).min()) if len(t) else None, "absolute_change_to": float(np.abs(ch[t]).max()) if len(t) else None,
         "range_misses": count([rs[i]["miss"] for i in t]), "early_years_test_rejects": count([rs[i]["reject"] for i in t])}
        for t in thirds]
    return out


def summarise_stage(records: list, names, n: int) -> dict:
    """Per candidate and process: the two cell counts with exact intervals (failures included, labelled), failures apart,
    end-state shares, widths, cells under 5%, power at a planted 5%, and for G11 and G12 the realised-path statistics.
    No averages over cells anywhere (E1.3)."""
    by = {}
    for c in names:
        procs = {}
        for p in PROCESSES:
            rs = [r["results"][c] for r in records if r["process"] == p]
            cell = {"range_misses_the_true_value": count([r["miss"] for r in rs]),
                    "early_years_test_rejects_a_flat_history": count([r["reject"] for r in rs]),
                    "rates_include_failure_penalties": True,
                    "numerical_failures": _failures(rs),
                    "ordinary_misses": int(sum(r["failure"] is None and not r["covered"] for r in rs)),
                    "ordinary_rejections": int(sum(r["failure"] is None and bool(r["early_rejected"]) for r in rs)),
                    "end_states_by_side": _side_shares(rs), "widths": widths([r["width"] for r in rs]),
                    "power_at_a_planted_5pct_ramp": {**count([r["power_detects"] for r in rs]),
                                                     "planted_computation_failures_counted_as_no_detection": int(sum(bool(r["power_failure"]) for r in rs))}}
            if p in WALK_PROCESSES:
                cell["realised_path"] = realised_path(rs, [r["realised_change"] for r in records if r["process"] == p])
            procs[p] = cell
        allr = [r["results"][c] for r in records]
        under5 = [f"{p}: {k}" for p, cell in procs.items() for k in ("range_misses_the_true_value", "early_years_test_rejects_a_flat_history")
                  if cell[k]["count"] < 0.05 * cell[k]["datasets"]]
        by[c] = {"by_process": procs, "cells_under_5pct": under5, "pooled_widths": widths([r["width"] for r in allr]),
                 "share_of_ranges_with_an_incomplete_or_failed_side": round(float(np.mean([np.isinf(r["width"]) for r in allr])), 5)}
    return by


def stage1_from_records(records: list, names, n: int) -> dict:
    s = summarise_stage(records, names, n)
    cells = {c: {f"{p}: {k}": s[c]["by_process"][p][k]["count"] for p in PROCESSES
                 for k in ("range_misses_the_true_value", "early_years_test_rejects_a_flat_history")} for c in names}
    wid = {c: np.array([r["results"][c]["width"] for r in records], dtype=float) for c in names}
    share = {c: s[c]["share_of_ranges_with_an_incomplete_or_failed_side"] for c in names}
    return {"by_candidate": s, "selection": select(cells, wid, share, n)}


# ================================================================================================================
# Stage 2: validation (E5.1)
# ================================================================================================================

PASSED, EXCESS, IMPRECISE = "passed", "observed excess rejection", "insufficient precision to certify"


def verdict(counts: dict, n: int) -> dict:
    """E5.1 for one rate across the processes: the one-sided 95% Monte Carlo upper bound (rate + 1.645 standard errors) at
    or under 11% in every process. Otherwise "observed excess rejection" where a measured rate is above 11%, or
    "insufficient precision to certify" where none is but a bound is above 11%."""
    rows = {}
    for p, k in counts.items():
        r = k / n
        upper = r + Z_ONE_SIDED_95 * np.sqrt(r * (1 - r) / n)
        rows[p] = {"count": int(k), "rate": round(r, 5), "upper_bound_95": round(float(upper), 5), "at_or_under_11pct": bool(upper <= STANDARD),
                   "exact_95_interval": clopper_pearson(int(k), n)}
    if all(x["at_or_under_11pct"] for x in rows.values()):
        v = PASSED
    elif any(x["rate"] > STANDARD for x in rows.values()):
        v = EXCESS
    else:
        v = IMPRECISE
    return {"verdict": v, "by_process": rows}


def stage2_from_records(records: list, chosen: str, n: int) -> dict:
    out = {"range": verdict({p: sum(r["results"][chosen]["miss"] for r in records if r["process"] == p) for p in PROCESSES}, n),
           "early_years_test": verdict({p: sum(r["results"][chosen]["reject"] for r in records if r["process"] == p) for p in PROCESSES}, n),
           "rates_include_failure_penalties": True,
           "numerical_failures": {p: _failures([r["results"][chosen] for r in records if r["process"] == p]) for p in PROCESSES}}
    out["note"] = ("failure to certify does not itself establish invalidity; no result-dependent extension and no runner-up "
                   "validation (E5.5). The two results are reported separately (E5.1).")
    return out


# ================================================================================================================
# The drivers
# ================================================================================================================

PATHS = {"benchmark": "inference_comparison_benchmark.json", "budget": "inference_validation_budget.json",
         "stage1": "inference_comparison_stage1.json", "stage2": "inference_validation_stage2.json"}


def comparison_fingerprint(d: design.Design, rules: ps.Rules, usable, quantities: dict, boot: int, names) -> dict:
    """design.run_fingerprint over the design inputs, this code and the modules it runs, the processes (with G7's units and
    G8's source), and the procedures' settings. Seeds are left out so that the benchmark, stage 1 and stage 2 of one
    design and code share it; each output records its own seed."""
    return design.run_fingerprint(
        d, rules=rules, usable=usable,
        assumptions={"kind": "inference_comparison", "set": ps.HEADLINE_SET, "threshold": 0.02, "processes": list(PROCESSES),
                     "grid": ic.GRID, "added": ADDED, "g7_units": quantities["g7_units"], "g8": quantities["g8"],
                     "truth": 0.0, "planted_power": cd.PLANTED_POWER},
        settings={"bootstrap_replications": boot, "level": cd.LEVEL, "alpha": cd.ALPHA, "bracket": list(cd.BRACKET),
                  "tolerance": cd.TOLERANCE, "tie": cd.TIE, "cr2_eigen_tolerance": cd.CR2_EIGEN_TOLERANCE, "candidates": list(names)},
        seeds=None, code_files=design.CODE_FILES + OWN_FILES)


def _need(path: Path, what: str) -> dict:
    if not path.exists():
        raise Refused(f"{path} is missing: {what}")
    return json.loads(path.read_text())


def stage1(ctx: dict, fp: dict, quantities: dict, frozen: Path, run_root: Path, workers: int, datasets: int = STAGE1_DATASETS) -> dict:
    bench = _need(frozen / PATHS["benchmark"], "stage 1 does not start before the benchmark (E5.2, E6.1 step 6)")
    if bench["fingerprint"]["sha256"] != fp["sha256"]:
        raise Refused("the benchmark was run under another fingerprint (design, code, processes or settings differ); "
                      "rerun the benchmark and the budget on this one before stage 1")
    hours = bench["projected_hours"]["stage1_all_three_candidates_2000_a_process"]
    if hours > STAGE1_HOURS:
        raise Refused(f"the benchmark projects stage 1 at {hours} hours, over the twelve-hour limit (E1.4, E5.3): stop and report "
                      "before stage 1. Datasets, replications and processes are not cut to fit")
    budget = _need(frozen / PATHS["budget"], "the validation budget is fixed and recorded before stage 1 (E5.4): run write-budget")
    if budget["fingerprint"]["sha256"] != fp["sha256"]:
        raise Refused("the budget was written from a benchmark under another fingerprint; rerun the benchmark and write-budget")
    names = list(ctx["names"])
    if names != list(cd.CANDIDATES):
        raise Refused("stage 1 runs all three candidates on the same datasets (E1.1)")
    manifest = {"stage": "stage1", "seed": SEEDS["stage1"], "datasets_per_process": datasets, "candidates": names,
                "fingerprint_sha256": fp["sha256"]}
    records = run_blocks("stage1", SEEDS["stage1"], ctx, run_root / "stage1", datasets, workers, manifest)
    report = {"what_this_is": "Step E stage 1 (E1.1 to E2.4): selects and never certifies. Calibration screening followed by width "
                              "ranking, with independent stage-two certification still required.",
              "seed": SEEDS["stage1"], "datasets_per_process": datasets, "processes": list(PROCESSES), "candidates": names,
              "bootstrap_replications": ctx["boot"], "design_quantities": quantities, "fingerprint": fp,
              "budget": budget["datasets_per_process_by_candidate"], **stage1_from_records(records, names, datasets)}
    _write_json(frozen / PATHS["stage1"], report)
    return report


def stage2(ctx_for, fp: dict, quantities: dict, frozen: Path, run_root: Path, workers: int, datasets: int | None = None) -> dict:
    """`ctx_for(name)` builds the context with the selected candidate only. `datasets` overrides the budget in tests only."""
    s1 = _need(frozen / PATHS["stage1"], "stage 2 validates the candidate stage 1 selected; run stage 1 first")
    chosen = s1["selection"]["selected"]
    if chosen is None:
        raise Refused("stage 1 selected no candidate: no stage 2 is run (E2.3), and no excluded candidate is validated")
    if s1["fingerprint"]["sha256"] != fp["sha256"]:
        raise Refused("stage 1 was run under another fingerprint; stage 2 validates only on the design and code stage 1 selected on")
    out = frozen / PATHS["stage2"]
    if out.exists():
        raise Refused(f"{out.name} exists: a validation run is never extended or rerun after its answer is seen (E5.1)")
    budget = _need(frozen / PATHS["budget"], "the validation budget (E5.4)")
    n = budget["datasets_per_process_by_candidate"].get(chosen)
    if not isinstance(n, int):
        raise Refused(f"no validation budget fits for candidate {chosen} ({n!r}): return to the owner (E5.4)")
    n = datasets if datasets is not None else n
    manifest = {"stage": "stage2", "seed": SEEDS["stage2"], "datasets_per_process": n, "candidates": [chosen],
                "fingerprint_sha256": fp["sha256"]}
    mpath = run_root / "stage2" / "manifest.json"
    if mpath.exists() and json.loads(mpath.read_text()).get("seed") != SEEDS["stage2"]:
        raise Refused("a stage-2 run exists under another seed: no other seed is drawn (E5.1)")
    ctx = ctx_for(chosen)
    records = run_blocks("stage2", SEEDS["stage2"], ctx, run_root / "stage2", n, workers, manifest)
    report = {"what_this_is": "Step E stage 2, validation (E5.1), of the candidate stage 1 selected, alone, on fresh datasets.",
              "candidate": chosen, "seed": SEEDS["stage2"], "datasets_per_process": n, "processes": list(PROCESSES),
              "standard": "one-sided 95% Monte Carlo upper bound (rate + 1.645 standard errors) at or under 11% in every process, "
                          "for the range and for the early-years test separately; no averages",
              "fingerprint": fp, **stage2_from_records(records, chosen, n)}
    _write_json(out, report)
    return report


def real_design(g8_ownership_only: bool):
    """The design exactly as design.main builds it under the headline rules, on the headline set at 2%."""
    from pipeline.analysis import usable_flag
    rules = ps.HEADLINE_RULES
    suppliers, mode = load_suppliers(ownership_only=g8_ownership_only)            # stops in words before anything heavy
    q, dose, regions, fuel, dd = design.load()
    flags = usable_flag.read()
    ownership, usable, gas = ps.rule_inputs(rules, q, usable=flags.usable)
    ownership_of = ps.ownership_classes(q)
    unknown = ps.load_unknown_load()
    treated, clean = design.split(0.02, ps.HEADLINE_SET, q, dose)
    d = design.build_with_rules(treated, clean, q, regions, fuel, dd, rules, ownership=ownership, usable=usable, gas=gas,
                                ownership_of=ownership_of, unknown_load=unknown, theta=0.02)
    if not len(d.hosts):
        raise Refused("the headline set has no host in the estimate; there is nothing to compare")
    return d, regions, q, ownership, suppliers, mode, rules, usable


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmds = [a for a in argv if not a.startswith("--")]
    if len(cmds) != 1 or cmds[0] not in ("benchmark", "write-budget", "stage1", "stage2"):
        print(__doc__)
        return 2
    cmd = cmds[0]
    workers = int(next((a.split("=", 1)[1] for a in argv if a.startswith("--workers=")), WORKERS))
    only = G8_OWNERSHIP_ONLY in argv
    try:
        if cmd == "write-budget":
            r = write_budget(FROZEN / PATHS["benchmark"], FROZEN / PATHS["budget"])
            print(json.dumps(r["datasets_per_process_by_candidate"], indent=1))
            return 0
        d, regions, q, ownership, suppliers, mode, rules, usable = real_design(only)
        built = build_context(d, regions, q, ownership, suppliers, mode, rules)
        fp = comparison_fingerprint(d, rules, usable, built["quantities"], cd.BOOT, cd.CANDIDATES)
        if cmd == "benchmark":
            r = benchmark(built["ctx"], fp, workers, FROZEN / PATHS["benchmark"])
            print(json.dumps({k: r[k] for k in ("seconds_a_dataset", "projected_hours", "workers", "machine", "commit")}, indent=1))
            print("fingerprint", fp["sha256"])
        elif cmd == "stage1":
            r = stage1(built["ctx"], fp, built["quantities"], FROZEN, INTERIM / "inference_comparison", workers)
            print(json.dumps(r["selection"], indent=1, default=_jsonable))
        else:
            ctx_for = lambda name: build_context(d, regions, q, ownership, suppliers, mode, rules, names=[name])["ctx"]  # noqa: E731
            r = stage2(ctx_for, fp, built["quantities"], FROZEN, INTERIM / "inference_comparison", workers)
            print(json.dumps({"candidate": r["candidate"], "range": r["range"]["verdict"], "early_years_test": r["early_years_test"]["verdict"]}, indent=1))
    except Refused as e:
        print(f"REFUSED: {e.why}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
