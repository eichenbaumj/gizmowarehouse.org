"""Orchestrate the self-insurance-cost pipeline and print a QA report.

Usage:
    python3 run_all.py                 # full run
    python3 run_all.py --check         # validate existing outputs only
    python3 run_all.py --from 03       # start at a stage
    python3 run_all.py --to 06         # stop after a stage
    python3 run_all.py --force         # refetch / rebuild

Hard gates (exit non-zero) are listed in validate(); see SCOPING.md and DECISIONS.md.
"""

from __future__ import annotations

import importlib
import json
import re
import sys

import pandas as pd

import config

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

STAGES = [
    ("01", "01_fetch_osc"),
    ("02", "02_tidy_osc"),
    ("03", "03_build_ny_panel"),
    ("04b", "04b_compile_labels"),
    ("04c", "04c_infer_signatures"),
    ("04d", "04d_validate_labels"),
    ("04e", "04e_compile_ntd_labels"),
    ("05", "05_fetch_ntd"),
    ("06", "06_tidy_ntd"),
    ("07", "07_models_ny"),
    ("08", "08_models_ntd"),
    ("09", "09_attribution"),
    ("10", "10_export"),
]


class Report:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []
        self.failed = False

    def add(self, level: str, msg: str) -> None:
        self.lines.append((level, msg))
        if level == FAIL:
            self.failed = True

    def render(self) -> str:
        out = ["", "=" * 72, f"QA REPORT — {config.SLUG} pipeline", "=" * 72]
        out += [f"[{lvl}] {msg}" for lvl, msg in self.lines]
        out += ["=" * 72, "RESULT: " + ("FAIL (hard gate tripped)" if self.failed else "GREEN"), "=" * 72]
        return "\n".join(out)


def _stage_key(s: str) -> tuple[int, str]:
    m = re.match(r"(\d+)([a-z]?)", s)
    return (int(m.group(1)), m.group(2))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(report: Report) -> None:
    # ---- raw manifest ------------------------------------------------------
    if not config.RAW_MANIFEST.exists():
        report.add(FAIL, "raw/manifest.json missing — stage 01 did not run")
        return
    manifest = json.loads(config.RAW_MANIFEST.read_text())
    missing = [c for c in config.OSC_CLASSES if f"osc/{c}_all_years.zip" not in manifest]
    if missing:
        report.add(FAIL, f"OSC zips missing from manifest: {missing}")
    else:
        report.add(PASS, f"OSC zips present for {len(config.OSC_CLASSES)} classes "
                         f"({sum(manifest[f'osc/{c}_all_years.zip']['bytes'] for c in config.OSC_CLASSES)/1e6:.0f} MB)")

    # ---- long table --------------------------------------------------------
    if not config.OSC_LONG_PARQUET.exists():
        report.add(FAIL, "osc_long.parquet missing — stage 02 did not run")
        return
    long = pd.read_parquet(config.OSC_LONG_PARQUET, columns=["cls", "entity_name", "fy", "section", "acct", "amount"])
    y = long[long["fy"] == config.PIN_YEAR]
    for cls, (lo, hi) in config.ENTITY_BANDS.items():
        n = y[y["cls"] == cls]["entity_name"].nunique()
        lvl = PASS if lo <= n <= hi else FAIL
        report.add(lvl, f"{cls} entities in {config.PIN_YEAR}: {n} (band {lo}–{hi})")
    exp = y[y["section"] == "EXPENDITURE"]
    for cls, pins in config.PIN_TOTALS.items():
        sub = exp[exp["cls"] == cls]
        got_ins = sub[sub["acct"] == config.ACCT_INSURANCE]["amount"].sum()
        got_jc = sub[sub["acct"] == config.ACCT_JUDGMENTS]["amount"].sum()
        for name, got, want in (("insurance", got_ins, pins["insurance"]), ("judgments", got_jc, pins["judgments"])):
            rel = abs(got - want) / want
            lvl = PASS if rel <= config.PIN_TOLERANCE else FAIL
            report.add(lvl, f"{cls} {name} {config.PIN_YEAR}: ${got/1e6:.1f}M vs pin ${want/1e6:.1f}M ({rel:.2%})")

    # ---- panel -------------------------------------------------------------
    if not config.NY_PANEL_PARQUET.exists():
        report.add(WARN, "ny_panel.parquet missing (stage 03 not run yet)")
        return
    panel = pd.read_parquet(config.NY_PANEL_PARQUET)
    dupes = panel.duplicated(["cls", "muni_code", "fy"]).sum()
    report.add(FAIL if dupes else PASS, f"panel duplicate entity-years: {dupes}")
    core = panel[panel["cls"].isin(config.OSC_CORE_CLASSES)]
    zero_share = (core["cost_of_risk"] <= 0).mean()
    report.add(WARN if zero_share > config.ZERO_COR_WARN_SHARE else PASS,
               f"core entity-years with zero cost of risk: {zero_share:.1%} (warn > {config.ZERO_COR_WARN_SHARE:.0%})")
    missing_pop = core[core["fy"] >= config.HEADLINE_YEARS[0]]["population"].isna().mean()
    report.add(WARN if missing_pop > 0.05 else PASS, f"headline-window core rows without population: {missing_pop:.1%}")

    # ---- labels ------------------------------------------------------------
    if config.NY_LABELS_CSV.exists():
        lab = pd.read_csv(config.NY_LABELS_CSV, dtype=str).fillna("")
        bad_enum = sorted(set(lab["structure"]) - config.VALID_STRUCTURES)
        no_src = int(((lab["source_doc_url"] == "") | (lab["quote"] == "")).sum())
        report.add(FAIL if bad_enum else PASS, f"label structures valid ({len(lab)} rows); bad: {bad_enum}")
        report.add(FAIL if no_src else PASS, f"label rows without source_doc_url+quote: {no_src}")
        n_doc = lab["entity_name"].nunique()
        report.add(PASS if n_doc >= config.MIN_DOC_LABELS else WARN,
                   f"document-labeled entities: {n_doc} (target >= {config.MIN_DOC_LABELS})")
        unknown_in_panel = sorted(set(lab["entity_name"]) - set(panel["entity_name"]))
        report.add(FAIL if unknown_in_panel else PASS, f"labeled entities absent from panel: {unknown_in_panel[:5]}")
    else:
        report.add(WARN, "ny_treatment_labels.csv not present yet")
    if config.LABEL_VALIDATION_JSON.exists():
        v = json.loads(config.LABEL_VALIDATION_JSON.read_text())
        acc = v.get("accuracy")
        report.add(PASS if (acc or 0) >= config.LABEL_MIN_ACCURACY else WARN,
                   f"signature-vs-document agreement: {acc} (gate {config.LABEL_MIN_ACCURACY}; below it the piece runs on the core only)")

    # ---- NTD ---------------------------------------------------------------
    if config.NTD_PANEL_PARQUET.exists():
        ntd = pd.read_parquet(config.NTD_PANEL_PARQUET)
        bad = ntd[(ntd["cl_share"] < 0) | (ntd["cl_share"] > 0.5)]
        report.add(FAIL if len(bad) else PASS, f"NTD cl_share in [0, 0.5]: {len(bad)} violations over {len(ntd)} rows")
        top = ntd[ntd["fy"] == int(config.NTD_YEARS[-1])].nlargest(config.NTD_LABEL_TOP_N, "vrm")
        unl = int((top["label_source"] == "unknown").sum()) if "label_source" in top else len(top)
        report.add(WARN if unl else PASS, f"top-{config.NTD_LABEL_TOP_N} transit agencies without a label: {unl}")
    else:
        report.add(WARN, "ntd_panel.parquet not present yet")

    # ---- models / export ---------------------------------------------------
    if config.MODELS_NY_JSON.exists():
        m = json.loads(config.MODELS_NY_JSON.read_text())
        ids = {r["spec_id"] for r in m.get("specs", [])}
        report.add(PASS if config.PRIMARY_SPEC in ids else FAIL, f"primary spec present: {config.PRIMARY_SPEC in ids} ({len(ids)} specs)")
        incomplete = [r["spec_id"] for r in m.get("specs", []) if not r.get("exploratory") and any(r.get(k) is None for k in ("coef", "lo", "hi", "n"))]
        report.add(FAIL if incomplete else PASS, f"specs with missing coef/lo/hi/n: {incomplete[:5]}")
    for name, path in config.PUBLIC_JSON.items():
        if path.exists():
            size = path.stat().st_size
            report.add(FAIL if size > config.PUBLIC_JSON_MAX_BYTES else PASS, f"public {name}.json {size/1024:.0f} KB")
            if name in ("models", "attribution", "ny_switchers"):
                # client rule (Joe, 2026-10-10): agencies may be named from public data among peers; no output
                # may describe any agency as a client or carry engagement detail
                hit = re.search(r"\bclients?\b|engagement", path.read_text(), re.I)
                report.add(FAIL if hit else PASS, f"client-language gate on {name}.json: {'HIT' if hit else 'clean'}")
    for p in (config.ASSET_NY_PANEL_CSV, config.ASSET_NTD_PANEL_CSV, config.ASSET_LABELS_CSV):
        if p.exists():
            first = p.open(encoding="utf-8").readline()
            ok = first.startswith("#") and config.SNAPSHOT_DATE in first and "CC-BY-4.0" in first and "joe@group17a.com" in first
            report.add(PASS if ok else FAIL, f"asset header on {p.name}: {'ok' if ok else 'missing snapshot/license/contact'}")


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    force = "--force" in argv
    start = argv[argv.index("--from") + 1] if "--from" in argv else "01"
    stop = argv[argv.index("--to") + 1] if "--to" in argv else "10"
    config.ensure_dirs()
    sys.path.insert(0, str(config.PIPELINE_DIR))
    if not check_only:
        for key, modname in STAGES:
            if _stage_key(key) < _stage_key(start) or _stage_key(key) > _stage_key(stop):
                continue
            path = config.PIPELINE_DIR / f"{modname}.py"
            if not path.exists():
                print(f"[{key}] {modname}: not written yet — skipping")
                continue
            print(f"[{key}] {modname}")
            mod = importlib.import_module(modname)
            rc = mod.main(["--force"] if force else [])
            if rc != 0:
                print(f"FATAL: stage {key} returned {rc}")
                return rc
    else:
        print("--check: validating existing outputs (no rebuild)")
    report = Report()
    validate(report)
    print(report.render())
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
