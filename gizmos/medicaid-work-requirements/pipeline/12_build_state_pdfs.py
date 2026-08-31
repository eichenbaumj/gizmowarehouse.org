"""Stage 12 — generate per-state PDF briefs (HTML-first via WeasyPrint).

Replaces the v1 ReportLab implementation. Now builds a 5-6 page state brief
designed for senior staff in state Medicaid operations:
  - Cover with hero stat
  - Geography page: state county map + top 10 counties + concentration callout
  - Within-county page: top county at 1-mile grid resolution + highest-impact cells
  - Demographics + burden page
  - Action page: tailored operational checklist, peer states, methodology, CSV download
  - Appendix: full county breakdown

Pipeline:
  1. Per state: assemble Jinja2 context (counties + grid + demographics + peers + checklist)
  2. Render 3 maps + 1 chart as PNG (cached to pipeline/output/state_maps/)
  3. Render Jinja2 HTML template
  4. WeasyPrint HTML → PDF
  5. Per-state CSV → public/assets/medicaid-data/
  6. PDFs land in public/assets/medicaid-briefs/

WeasyPrint requires libpango/libcairo/gdk-pixbuf system libs. On macOS these
are at $(brew --prefix)/lib but Python's libloader doesn't find them by
default — set DYLD_FALLBACK_LIBRARY_PATH (or just run with the env var).

Usage:
  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib python3 12_build_state_pdfs.py
  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib python3 12_build_state_pdfs.py --state CA
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Make sure brew's library path is on DYLD_FALLBACK_LIBRARY_PATH so WeasyPrint
# can load libpango / libcairo / libgdk_pixbuf on macOS. Safe no-op on Linux.
if sys.platform == "darwin":
    brew_lib = "/opt/homebrew/lib"
    existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    if brew_lib not in existing.split(":"):
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
            f"{brew_lib}:{existing}" if existing else brew_lib
        )

import config  # type: ignore
from lib import render_maps, render_charts, state_brief_context, write_csv  # type: ignore

OUT_DIR = config.PUBLIC_ASSETS_DIR / "medicaid-briefs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
STATE_SUMMARY_IN = config.OUTPUT_DIR / "state_summary.json"
TEMPLATE_DIR = Path(__file__).parent / "templates"


def _ensure_summary() -> dict:
    if not STATE_SUMMARY_IN.exists():
        # Fall back to public/data/medicaid-state-summary.json (the bake script's
        # output landing zone for v0).
        public_summary = config.REPO_ROOT / "public/data/medicaid-state-summary.json"
        if public_summary.exists():
            STATE_SUMMARY_IN.parent.mkdir(parents=True, exist_ok=True)
            STATE_SUMMARY_IN.write_text(public_summary.read_text())
        else:
            print(f"ERROR: {STATE_SUMMARY_IN} (and public fallback) missing.", file=sys.stderr)
            sys.exit(1)
    return json.loads(STATE_SUMMARY_IN.read_text())


def render_brief(state: dict) -> bytes:
    """Render one state's PDF brief. Returns PDF bytes."""
    state_fips = state["state_fips"]
    state_abbr = state["state_abbr"]

    # v9 5-page rebuild: the only map in the brief is the compliance-burden
    # choropleth (page 3, "where verification will fail hardest"). The county
    # subject-count map, the 1-mile within-county grid, and the demographics
    # chart were dropped, so we no longer render them.
    maps: dict[str, Path] = {}
    # Expansion states + subject-via-waiver states (WI/GA) get the burden map.
    if state["expansion"] or state.get("subject_via_waiver"):
        maps["state_burden"] = render_maps.render_state_burden_map(state_abbr, state_fips)

    context = state_brief_context.build_context(state, maps=maps)

    # Jinja2 render
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tmpl = env.get_template("state_brief.html.j2")
    html_str = tmpl.render(**context)

    # WeasyPrint HTML → PDF. state_brief.css carries __BRAND_ROOT__ placeholders
    # so the committed template stays machine-independent; resolve them here.
    from weasyprint import HTML, CSS
    brand_root = os.environ.get("BRAND_ROOT")
    if not brand_root:
        sys.exit("BRAND_ROOT not set — point it at the brand-assets directory (needs fonts/).")
    css_path = TEMPLATE_DIR / "state_brief.css"
    css_text = css_path.read_text().replace("__BRAND_ROOT__", str(Path(brand_root).resolve()))
    pdf_bytes = HTML(string=html_str, base_url=str(TEMPLATE_DIR)).write_pdf(
        stylesheets=[CSS(string=css_text, base_url=str(TEMPLATE_DIR))]
    )
    return pdf_bytes


def main(only_state: str | None = None) -> None:
    summary = _ensure_summary()
    states = summary["states"]
    if only_state:
        states = [s for s in states if s["state_abbr"].upper() == only_state.upper()]
        if not states:
            print(f"ERROR: state {only_state} not found in summary.", file=sys.stderr)
            sys.exit(1)

    n_pdf = 0
    n_csv = 0
    for state in states:
        t0 = time.time()
        # CSV (cheap, always)
        write_csv.write_state_csv(state["state_fips"], state["state_abbr"])
        n_csv += 1

        # PDF
        pdf = render_brief(state)
        out = OUT_DIR / f"medicaid_brief_{state['state_abbr']}.pdf"
        out.write_bytes(pdf)
        n_pdf += 1
        size_kb = out.stat().st_size / 1024
        print(f"  [{state['state_abbr']}] {size_kb:>6.1f} KB  ({time.time()-t0:.1f}s)")

    print(f"\n-> {n_pdf} PDF briefs in {OUT_DIR.relative_to(config.REPO_ROOT)}/")
    print(f"-> {n_csv} CSVs in public/assets/medicaid-data/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", help="Only build this state (2-letter abbr)", default=None)
    args = ap.parse_args()
    t0 = time.time()
    main(args.state)
    print(f"\nStage 12 done in {time.time() - t0:.1f}s")
