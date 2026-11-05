"""Orchestrate the hoyt-schermerhorn-crime-analysis pipeline and print a QA report.

Usage:
    python3 run_all.py                 # full run (stage 01 rescans only changed raw files)
    python3 run_all.py --check         # validate existing outputs only
    python3 run_all.py --from 05       # start at a stage
    python3 run_all.py --to 07         # stop after a stage
    python3 run_all.py --force         # rescan raw files
    python3 run_all.py --skip-tests    # do not run pytest first

Hard gates (exit non-zero) are the `fail` statuses in output/dq.json plus the checks in validate().
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
STAGES = [
    ("01", "01_scan_citywide"), ("02", "02_build_core"), ("03", "03_cell_panel"), ("04", "04_comparators"),
    ("05", "05_dq_audit"), ("06", "06_stats"), ("07", "07_headlines"), ("08", "08_geo"), ("09", "09_export"), ("10", "10_imagery"), ("11", "11_context_city"),
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
        out = ["", "=" * 72, f"QA REPORT: {config.SLUG} pipeline", "=" * 72]
        out += [f"[{lvl}] {msg}" for lvl, msg in self.lines]
        out += ["=" * 72, "RESULT: " + ("FAIL (hard gate tripped)" if self.failed else "GREEN"), "=" * 72]
        return "\n".join(out)


def run_stage(mod: str, force: bool) -> None:
    spec = importlib.util.spec_from_file_location(mod, config.HERE / f"{mod}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if mod == "01_scan_citywide":
        m.main(force=force)
    else:
        m.main()


def validate(report: Report) -> None:
    dq_path = config.OUT_DIR / "dq.json"
    if not dq_path.exists():
        report.add(FAIL, "output/dq.json missing: stage 07 did not run")
        return
    dq = json.loads(dq_path.read_text())
    fails = [t for t in dq["tests"] if t["status"] == "fail"]
    warns = [t for t in dq["tests"] if t["status"] == "warn"]
    kills = [t for t in dq["tests"] if t["status"] == "kill"]
    report.add(FAIL if fails else PASS, f"{len(fails)} integrity gates failed" + (": " + ", ".join(t["id"] for t in fails) if fails else ""))
    report.add(WARN if warns else PASS, f"{len(warns)} warnings carry footnotes: " + ", ".join(t["id"] for t in warns))
    for cid, c in dq["claims"].items():
        lvl = WARN if not c["publishable"] else PASS
        report.add(lvl, f"{cid} {c['label']}: primary {c['primary']['value']}, range {c['range']}, publishable={c['publishable']}"
                        + (f", kills={c['kill_reasons']}" if c["kill_reasons"] else ""))
    for name, cap in (("stops.json", config.PUBLIC_JSON_MAX_BYTES), ("footprints.geojson", config.FOOTPRINTS_MAX_BYTES), ("grid.geojson", config.PUBLIC_JSON_MAX_BYTES * 2)):
        p = config.PUBLIC_DATA_DIR / name
        if p.exists():
            report.add(PASS if p.stat().st_size <= cap else FAIL, f"{name}: {p.stat().st_size / 1e6:.2f} MB (cap {cap / 1e6:.1f} MB)")
        else:
            report.add(WARN, f"{name} not exported yet")
    for p in config.ASSETS_DIR.glob(f"{config.ASSET_PREFIX}*.csv"):
        first = p.open().readline()
        ok_header = first.startswith("#") and config.SLUG in first
        cols = p.open().readlines()[1].strip().split(",") if ok_header else []
        leak = [c for c in config.DROP_FROM_DOWNLOADS if c in cols]
        report.add(PASS if ok_header and not leak and p.stat().st_size <= config.ASSET_MAX_BYTES else FAIL,
                   f"{p.name}: header {'ok' if ok_header else 'MISSING'}, demographic columns {leak or 'none'}, {p.stat().st_size / 1e6:.1f} MB")
    ctx = config.PUBLIC_DATA_DIR / "context.json"
    if ctx.exists():
        c = json.loads(ctx.read_text())
        report.add(PASS if c.get("cell", {}).get("rank_all") == dq["claims"]["claim_7"]["primary"]["value"] else FAIL, "context.json rank matches headlines")
        missing = [k for k in config.CONTEXT_STAGE11_BLOCKS if k not in c]
        report.add(PASS if not missing else FAIL, f"context.json carries the stage 11 blocks{'' if not missing else ': missing ' + ', '.join(missing)}")
        # the opening says "the highest robbery rate of any large American city" in 1990; the words hold only at rank 1
        rk = c.get("opening", {}).get("robbery_rank_1990")
        report.add(PASS if rk == 1 else FAIL, f"opening: NYC 1990 large-city robbery rank is {rk} (prose needs 1)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--from", dest="start", default="01")
    ap.add_argument("--to", dest="stop", default="11")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--skip-tests", action="store_true")
    a = ap.parse_args()
    report = Report()
    if not a.check:
        if not a.skip_tests:
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", str(config.HERE / "tests")], capture_output=True, text=True)
            report.add(PASS if r.returncode == 0 else FAIL, "pytest: " + (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[-200:]))
            if r.returncode != 0:
                print(r.stdout[-3000:], r.stderr[-3000:])
                print(report.render())
                sys.exit(1)
        for key, mod in STAGES:
            if key < a.start or key > a.stop:
                continue
            print(f"\n=== stage {key}: {mod} ===")
            try:
                run_stage(mod, a.force)
            except SystemExit as e:
                if e.code not in (0, None):
                    report.add(FAIL, f"stage {key} exited {e.code}")
                    print(report.render())
                    sys.exit(1)
    validate(report)
    print(report.render())
    sys.exit(1 if report.failed else 0)


if __name__ == "__main__":
    main()
