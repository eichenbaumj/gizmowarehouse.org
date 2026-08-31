"""Assemble per-state Jinja2 context for the PDF brief.

Joins the state-level summary, county GeoJSON properties, baked top
counties, demographic profile, and grid-cell highlights into a single
dictionary the template renders from.
"""
from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd

import config  # type: ignore

REPO = config.REPO_ROOT
COUNTIES_PATH = REPO / "public/data/medicaid-counties.geojson"
SUMMARY_PATH = REPO / "public/data/medicaid-state-summary.json"
GRID_PATH = REPO / "gizmos/medicaid-work-requirements/pipeline/output/grid_1mi.geojson"
LOSS_BREAKDOWN_PATH = REPO / "public/data/medicaid-loss-breakdown.json"
NARRATIVES_PATH = REPO / "gizmos/medicaid-work-requirements/pipeline/state_narratives.json"

# Lazy module-level caches.
_counties_cache: gpd.GeoDataFrame | None = None
_grid_cache: gpd.GeoDataFrame | None = None
_summary_cache: dict | None = None
_loss_breakdown_cache: dict | None = None
_narratives_cache: dict | None = None


def _counties() -> gpd.GeoDataFrame:
    global _counties_cache
    if _counties_cache is None:
        _counties_cache = gpd.read_file(COUNTIES_PATH)
    return _counties_cache


def _grid() -> gpd.GeoDataFrame:
    global _grid_cache
    if _grid_cache is None and GRID_PATH.exists():
        _grid_cache = gpd.read_file(GRID_PATH)
        # The grid carries state_fips + county_fips per cell; derive the
        # 5-digit county_geoid (state||county) so downstream lookups can
        # filter on a single key.
        if "county_geoid" not in _grid_cache.columns and {
            "state_fips", "county_fips"
        }.issubset(_grid_cache.columns):
            _grid_cache["county_geoid"] = (
                _grid_cache["state_fips"].astype(str).str.zfill(2)
                + _grid_cache["county_fips"].astype(str).str.zfill(3)
            )
    return _grid_cache if _grid_cache is not None else gpd.GeoDataFrame()


def summary() -> dict:
    global _summary_cache
    if _summary_cache is None:
        _summary_cache = json.loads(SUMMARY_PATH.read_text())
    return _summary_cache


def loss_breakdown() -> dict | None:
    """Load medicaid-loss-breakdown.json (produced by stage 07b) if available."""
    global _loss_breakdown_cache
    if _loss_breakdown_cache is None:
        if not LOSS_BREAKDOWN_PATH.exists():
            return None
        _loss_breakdown_cache = json.loads(LOSS_BREAKDOWN_PATH.read_text())
    return _loss_breakdown_cache


def state_narratives() -> dict:
    """Load per-state authored narratives (see state_narratives.json _meta).

    Returns an empty dict if the file is missing, so the template can still
    fall through to the generic concentration callout.
    """
    global _narratives_cache
    if _narratives_cache is None:
        if not NARRATIVES_PATH.exists():
            _narratives_cache = {}
        else:
            _narratives_cache = json.loads(NARRATIVES_PATH.read_text())
    return _narratives_cache


def _render_inline_md(text: str) -> str:
    """Minimal inline-markdown to HTML.

    Handles **bold** and *italic*. The narratives in state_narratives.json use
    Markdown emphasis for readability in the source; we render to <strong>/<em>
    so the WeasyPrint HTML template can display them.
    """
    import re
    if text is None:
        return ""
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    out = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", out)
    return out


def narrative_for(state_fips: str) -> dict | None:
    """Return the authored narrative for a state, or None if not authored.

    Inline-markdown emphases (**bold**, *italic*) are pre-rendered to HTML so
    the template can pass the strings through `| safe`.
    """
    src = state_narratives().get(state_fips)
    if src is None:
        return None
    out: dict = {
        "cover_callout": _render_inline_md(src.get("cover_callout", "")),
        "section_title": src.get("section_title", "Within-state variation"),
        "section_intro": _render_inline_md(src.get("section_intro", "")),
        "convergence_note": _render_inline_md(src.get("convergence_note", "")),
        "paths": [],
    }
    for p in src.get("paths", []):
        out["paths"].append({
            "name": p.get("name", ""),
            "metric_label": _render_inline_md(p.get("metric_label", "")),
            "counties_label": p.get("counties_label", ""),
            "color_class": p.get("color_class", "cobalt"),
            "body_paragraphs": [_render_inline_md(x) for x in p.get("body_paragraphs", [])],
        })
    return out


def _fmt_n(n: float | int, *, compact: bool = False) -> str:
    """Format a number with commas, or compact M/K notation."""
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return "—"
    n = float(n)
    if compact:
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{round(n/1_000):,}K"
        return f"{round(n):,}"
    return f"{round(n):,}"


def _fmt_pct(p: float, digits: int = 1) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "—"
    return f"{p*100:.{digits}f}%"


_EMPTY_CONCENTRATION = {
    "total_counties": 0, "n50": 0, "n80": 0, "n90": 0,
    "pct_counties_for_50": "—", "pct_counties_for_80": "—", "pct_counties_for_90": "—",
    "top5_names": [], "top_county_name": "", "top_county_geoid": "",
    "top_county_subject": 0, "top_county_share": "—",
}


def _concentration(state_counties: gpd.GeoDataFrame) -> dict:
    """Compute share of subject pool held by top-N counties."""
    s = state_counties.sort_values("subject_count_strict", ascending=False).copy()
    total = float(s["subject_count_strict"].sum())
    if total == 0:
        return dict(_EMPTY_CONCENTRATION, total_counties=len(s))
    s["share"] = s["subject_count_strict"] / total
    s["cumulative"] = s["share"].cumsum()
    n_counties = len(s)

    def _find_at_least(threshold: float) -> int:
        idx = s[s["cumulative"] >= threshold].index
        if len(idx) == 0:
            return n_counties
        return int(s.index.get_loc(idx[0])) + 1

    n50 = _find_at_least(0.50)
    n80 = _find_at_least(0.80)
    n90 = _find_at_least(0.90)
    top5_names = s.head(5)["county_name"].tolist()
    top_county = s.iloc[0]

    return {
        "total_counties": n_counties,
        "n50": n50, "n80": n80, "n90": n90,
        "pct_counties_for_50": _fmt_pct(n50 / n_counties, 1),
        "pct_counties_for_80": _fmt_pct(n80 / n_counties, 1),
        "pct_counties_for_90": _fmt_pct(n90 / n_counties, 1),
        "top5_names": top5_names,
        "top_county_name": top_county["county_name"],
        "top_county_geoid": top_county["GEOID"],
        "top_county_subject": int(top_county["subject_count_strict"]),
        "top_county_share": _fmt_pct(float(top_county["subject_count_strict"]) / total, 1),
    }


def _top_county_cells(county_geoid: str, max_n: int = 8) -> list[dict]:
    g = _grid()
    if g.empty:
        return []
    cells = g[g["county_geoid"] == county_geoid].copy()
    if cells.empty:
        return []
    cells = cells.sort_values("subject_count_strict", ascending=False).head(max_n)
    out = []
    for _, c in cells.iterrows():
        # Phase-2 fields take precedence (place_name / place_parent); legacy
        # nearest_place_name is the back-compat fallback for grids built
        # before tools/bake-medicaid-place-labels.py ran.
        place_name = (c.get("place_name") or "").strip()
        place_parent = (c.get("place_parent") or "").strip()
        landmark = (c.get("landmark_name") or "").strip()
        rank = int(c.get("landmark_category") or 99)
        connector = "by" if 1 <= rank <= 7 else "near"
        if place_name and place_parent:
            head = f"{place_name} · {place_parent}"
        elif place_name:
            head = place_name
        else:
            legacy = (c.get("nearest_place_name") or "").strip()
            head = f"Near {legacy}" if legacy else ""
        if head and landmark:
            loc = f"{head} · {connector} {landmark}"
        elif head:
            loc = head
        elif landmark:
            loc = f"{connector} {landmark}"
        else:
            loc = "—"
        out.append({
            "location": loc,
            "subject_count": int(c["subject_count_strict"]),
            "projected_loss": int(c["loss_exposure_strict"]),
        })
    return out


def _peer_states(state: dict, n: int = 3) -> list[dict]:
    """3 states with subject_count closest to this state's (excluding self)."""
    target = state["subject_count_strict"]
    others = [
        s for s in summary()["states"]
        if s["state_abbr"] != state["state_abbr"] and s["expansion"] and s["subject_count_strict"] > 0
    ]
    others.sort(key=lambda s: abs(s["subject_count_strict"] - target))
    return [
        {
            "name": s["state_name"],
            "abbr": s["state_abbr"],
            "subject_count": s["subject_count_strict"],
            "subject_rate": s["subject_rate"],
            "burden_index": s["burden_index_centered"],
        }
        for s in others[:n]
    ]


def _checklist(state: dict, concentration: dict, lb: dict | None = None) -> list[str]:
    """State-tailored operational checklist lines.

    v4 ordering principle: the leverage on procedural disenrollment lives
    upstream — in ex parte plumbing, cross-program data, vendor configuration,
    and the enrollee comms plan that ships before the rule activates. Local
    outreach to people who are already losing coverage is structurally a
    rear-guard action. The checklist below leads with the upstream work and
    treats geographic targeting as a lower-priority field-level concern.
    """
    items: list[str] = []
    abbr = state["state_abbr"]
    if not state["expansion"] and not state.get("subject_via_waiver"):
        if state.get("waiver_listed"):
            # Tennessee: named on CMS's June 2026 list, but the affected 1115
            # population is not publicly quantified, so we model no loss for it.
            items.append(
                f"{state['state_name']} is named on CMS's June 2026 list of states whose Section "
                f"1115 waiver enrollees are subject to the OBBBA work requirement, but the specific "
                f"affected population is not quantified in public data. This brief therefore models "
                f"no {state['state_name']}-specific coverage-loss estimate — treat the state as in "
                f"scope and watch for CMS detail on the affected waiver group."
            )
            return items
        items.append(
            f"{state['state_name']} has not adopted ACA Medicaid expansion and has no Section 1115 "
            f"waiver population subject to the requirement. The OBBBA work requirement applies "
            f"specifically to the expansion-adult eligibility group, which doesn't exist here. This "
            f"brief covers the working-age uninsured baseline that would be subject if your state expanded."
        )
        items.append(
            "If your state is considering expansion: model the verification infrastructure "
            "build before the rule takes effect — early implementers (AR, MT, NE) have a 12-18 month head start."
        )
        return items

    if state.get("already_work_conditional"):
        # Georgia: subject via Pathways, which already imposes the work requirement.
        items.append(
            f"{state['state_name']} did not adopt ACA Medicaid expansion but is subject to the OBBBA "
            f"work requirement through its Section 1115 Pathways to Coverage waiver "
            f"(~{int(state['subject_count_strict']):,} enrolled). Pathways ALREADY conditions coverage "
            f"on 80 hours/month of qualifying activity, so the federal rule adds no net-new procedural "
            f"loss for current enrollees — the binding work requirement is already in force. Pathways "
            f"runs through 2026-12-31, after which the state must comply with the federal OBBBA framework."
        )
        return items

    if state.get("subject_via_waiver"):
        # Wisconsin: subject via BadgerCare childless-adult waiver; modeled like an
        # expansion state but flagged as a waiver slice sized from admin enrollment.
        items.append(
            f"{state['state_name']} did not adopt ACA Medicaid expansion, but its Section 1115 waiver "
            f"population — {state.get('waiver_note') or 'an expansion-like adult group'} — is subject "
            f"to the OBBBA work requirement per CMS's June 2026 list. The estimates below model that "
            f"waiver slice, sized from administrative enrollment and run through the same exemption and "
            f"documentation-failure model used for expansion states. Treat the figure as a projection: "
            f"there is no state-specific verification-feed data for this population yet."
        )

    n = state["subject_count_strict"]
    # Use the bottom-up total (same figure as the cover, stats strip, and Sankey)
    # so every loss number in the brief agrees. Fall back to loss_exposure only
    # if the bottom-up breakdown is unavailable for this state.
    loss = (lb or {}).get("total_loss") or state["loss_exposure_strict"]
    sn = state["state_name"]

    # v9: tailor the lead by the state's actual ex parte standing.
    scores = (lb or {}).get("ex_parte_scores") or {}
    comp = scores.get("composite")
    obs = scores.get("observed_ex_parte")
    band = (lb or {}).get("ex_parte_band")
    ex_subs = (lb or {}).get("exemption_subs") or []
    top_ex = max(ex_subs, key=lambda s: s["count"]) if ex_subs else None

    # ---- Upstream work (do this first; this is where the leverage is) ----
    if comp is not None and band == "high":
        obs_txt = f", and {obs}/100 on observed ex parte" if obs is not None else ""
        items.append(
            f"<strong>Start here: {sn}'s ex parte capability is in the bottom tier (composite {comp}/100{obs_txt}).</strong> "
            f"The {_fmt_n(loss)} projected losses are largely set before December 31 by how many data sources flow into the "
            f"eligibility decision automatically. The single highest-leverage move is standing up UI wage match and "
            f"Medicaid-claims feeds; treat almost everything else as secondary until those are live."
        )
    elif comp is not None and band == "low":
        items.append(
            f"<strong>{sn} already auto-renews at a high rate (composite {comp}/100); the gap is the work-requirement-specific feeds.</strong> "
            f"Income-renewal ex parte is necessary but not sufficient. Confirm UI wage hours, Medicaid-claims frailty flags, and the "
            f"National Student Clearinghouse feed are wired into the work-requirement decision, not just the income renewal."
        )
    else:
        items.append(
            f"<strong>Ex parte plumbing matters more than anything else on this list.</strong> The {_fmt_n(loss)} projected losses for "
            f"{sn} are largely set before December 31 by how many data sources flow into the eligibility decision automatically. Field "
            f"outreach after the rule activates can recover individual enrollees but cannot meaningfully change the aggregate number."
        )
    items.append(
        "Stand up UI wage match in the eligibility system if it's not already operational. UI wage data is the "
        "single most important data source — it auto-verifies the ~45% of subject enrollees who are working but "
        "would otherwise have to upload paystubs every month."
    )
    items.append(
        "Coordinate with managed-care plans to flag medically-frail enrollees up-front. "
        "Adding the disability-determination flag at the eligibility layer (not at verification) "
        "removes the ~19% of the loss-by-2034 picture that's medically frail without a recent provider letter."
    )
    if top_ex is not None:
        _label = top_ex["label"]
        if "American Indian" in _label or "AI/AN" in _label:
            _hint = "wire up IHS / tribal-enrollment data sharing so the exemption auto-applies"
        elif "Medically frail" in _label:
            _hint = "a Medicaid-claims and health-information-exchange pull for chronic conditions"
        elif "disabled adult" in _label:
            _hint = "SSI/SSDI linkage to the care recipient plus household matching"
        elif "Parent caregivers" in _label:
            _hint = "the child's own Medicaid case, which already carries the household link"
        elif "SUD" in _label:
            _hint = "behavioral-health MCO enrollment data"
        elif "student" in _label.lower():
            _hint = "the National Student Clearinghouse API"
        else:
            _hint = "an explicit self-attestation pathway in the portal"
        items.append(
            f"Your single largest exempt-but-at-risk group is <strong>{_label}</strong> "
            f"(about {_fmt_n(top_ex['count'])}). The feed that clears it: {_hint}."
        )
    items.append(
        "Cross-reference SNAP work-compliance rolls. Those enrollees are categorically exempt "
        "under §1902(xx)(2)(F) — the bill explicitly recognizes the overlap. Estimated to "
        "remove ~8% from the verification load nationally."
    )
    hardship = state.get("hardship_exception_status", "unknown")
    if hardship == "adopting":
        items.append(
            "Adopting the high-unemployment hardship exception: identify qualifying counties (8%+ "
            "unemployment or 1.5× national average over 12 months) and file the CMS waiver request."
        )
    elif hardship == "not_adopting":
        items.append(
            "State has declined the high-unemployment hardship exception. Counties with sustained "
            "8%+ unemployment will lose coverage despite work being unavailable. Confirm this is the policy intent."
        )
    elif hardship == "undecided":
        items.append(
            "Hardship-exception decision still pending. Decide before September 2026 — late "
            "filing pushes back qualifying-county determinations into the verification window."
        )

    # ---- Portal & comms (mid-priority pre-rule work) ----
    items.append(
        f"Build (or harden) a verification portal that accepts paystubs, school transcripts, training-program letters, and "
        f"caregiver attestations. Nationally, about {_fmt_pct(config.NATIONAL_EXEMPTION_RATES['parent_caretaker_child_under_14'])} of subject enrollees have a child under 14 in the household; "
        f"caregiver self-attestation prevents most needless terminations."
    )
    items.append(
        "Ship a Q4 2026 comms plan now. Most procedural disenrollments are people who never saw the "
        "verification letter. Postal address validation, MCO-channel outreach, and a SMS/email reminder "
        "schedule reach far more enrollees than any post-activation door-knocking campaign."
    )
    early = state.get("early_implementer")
    if early:
        items.append(
            f"Early implementer status: {early}. Document lessons learned for peer states and CMS."
        )

    # ---- Field-level / informational (do these LAST; rear-guard) ----
    if concentration.get("n50"):
        items.append(
            f"<em>Geographic targeting (useful for staffing, but a lower priority for moving the loss number):</em> "
            f"{concentration['n50']} counties ({concentration['pct_counties_for_50']} of {state['state_name']}'s "
            f"counties) hold 50% of the subject pool: {', '.join(concentration['top5_names'][:min(concentration['n50'], 5)])}"
            f"{', and others' if concentration['n50'] > 5 else ''}. Concentrate field staff and county-office support there. "
            f"Note that most of the enrollees a field campaign would reach in these counties have already been "
            f"terminated by the verification system; staffing there speeds recovery rather than preventing the initial loss."
        )
    return items


def _svg_escape(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _truncate(s: str, n: int = 30) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _build_sankey_svg(lb: dict) -> str:
    """Build a static 3-column sankey SVG (source → 3 buckets → top subgroups)
    for the PDF brief's lead page. WeasyPrint renders inline SVG (rects, bezier
    paths, text only — no gradients/filters). Mirrors the web Sankey's shape.
    """
    wd = float(lb.get("workdoc_total") or 0)
    ex = float(lb.get("exemption_total") or 0)
    nc = float(lb.get("noncompliant_total") or 0)
    total = wd + ex + nc
    if total <= 0:
        return ""

    VB_W, VB_H = 680, 360
    TOP, BOT, GAP = 24, 336, 16
    H = BOT - TOP
    avail = H - 2 * GAP
    SRC_X, SRC_W = 96, 20
    BKT_X, BKT_W = 300, 16
    SUB_X, SUB_W = 470, 13
    LABEL_X = SUB_X + SUB_W + 7
    COBALT, CAROLINA, GRAY = "#1F1FD6", "#21A8E0", "#94A3B8"
    COBALT_F, CAROLINA_F, GRAY_F = "#C9D6F5", "#C2E6F6", "#E2E8F0"

    def px(n: float) -> float:
        return (n / total) * avail

    def band(x0, x1, s_top, s_bot, t_top, t_bot, fill, op):
        c = x0 + (x1 - x0) * 0.5
        return (f'<path d="M {x0:.1f} {s_top:.1f} C {c:.1f} {s_top:.1f} {c:.1f} {t_top:.1f} {x1:.1f} {t_top:.1f} '
                f'L {x1:.1f} {t_bot:.1f} C {c:.1f} {t_bot:.1f} {c:.1f} {s_bot:.1f} {x0:.1f} {s_bot:.1f} Z" '
                f'fill="{fill}" fill-opacity="{op}"/>')

    p: list[str] = []
    p.append(f'<rect x="{SRC_X}" y="{TOP}" width="{SRC_W}" height="{H}" fill="{COBALT}" fill-opacity="0.9"/>')
    p.append(f'<text x="{SRC_X - 12}" y="{TOP + H/2 - 5:.0f}" text-anchor="end" '
             f'font-family="Source Serif 4, Georgia, serif" font-size="34" font-weight="700" fill="{COBALT}">'
             f'{_svg_escape(lb.get("total_loss_compact", ""))}</text>')
    p.append(f'<text x="{SRC_X - 12}" y="{TOP + H/2 + 14:.0f}" text-anchor="end" '
             f'font-size="11" fill="#3B3B3B">lose coverage by 2034</text>')

    buckets = [
        ("Compliant, can't prove it", wd, COBALT, COBALT_F, lb.get("workdoc_subs", [])),
        ("Exempt, can't prove it", ex, CAROLINA, CAROLINA_F, lb.get("exemption_subs", [])),
        ("Not in qualifying activity", nc, GRAY, GRAY_F, []),
    ]
    by = sy = TOP
    for name, val, color, faint, subs in buckets:
        bh = px(val)
        if bh <= 0:
            continue
        b_top, b_bot = by, by + bh
        s_top, s_bot = sy, sy + bh
        p.append(band(SRC_X + SRC_W, BKT_X, s_top, s_bot, b_top, b_bot, faint, 0.85))
        p.append(f'<rect x="{BKT_X}" y="{b_top:.1f}" width="{BKT_W}" height="{bh:.1f}" fill="{color}" fill-opacity="0.9"/>')
        mid = (b_top + b_bot) / 2
        p.append(f'<text x="{BKT_X - 8}" y="{mid - 2:.1f}" text-anchor="end" font-size="10.5" font-weight="700" fill="{color}">{_svg_escape(name)}</text>')
        p.append(f'<text x="{BKT_X - 8}" y="{mid + 11:.1f}" text-anchor="end" font-size="9.5" fill="#475569">'
                 f'{_svg_escape(_fmt_n(val, compact=True))} ({round(val / total * 100)}%)</text>')
        top = sorted(subs, key=lambda s: -s["count"])[:5]
        subtotal = sum(s["count"] for s in top) or 1
        # Gap the sub side (node padding) so each subgroup reads as its own
        # proportionally-sized bar instead of merging into one bucket-height
        # block. The bucket side stays contiguous, so flows fan from the full
        # bucket and taper to the separated leaves.
        SUB_GAP = 3.0
        bar_space = max(bh - (len(top) - 1) * SUB_GAP, bh * 0.55)
        cy_src = cy_tgt = b_top
        for s in top:
            frac = s["count"] / subtotal
            src_h = frac * bh           # bucket side: contiguous, fills the bucket
            sh = frac * bar_space       # sub side: proportional, gapped
            if sh >= 0.5:
                p.append(band(BKT_X + BKT_W, SUB_X, cy_src, cy_src + src_h, cy_tgt, cy_tgt + sh, color, 0.4))
                p.append(f'<rect x="{SUB_X}" y="{cy_tgt:.1f}" width="{SUB_W}" height="{max(sh,1):.1f}" fill="{color}" fill-opacity="0.9"/>')
                p.append(f'<text x="{LABEL_X}" y="{cy_tgt + sh/2 + 3:.1f}" font-size="8.5" fill="#3B3B3B">'
                         f'{_svg_escape(_truncate(s["label"], 34))}  {_svg_escape(s["count_compact"])}</text>')
            cy_src += src_h
            cy_tgt += sh + SUB_GAP
        by = b_bot + GAP
        sy = s_bot

    return (f'<svg viewBox="0 0 {VB_W} {VB_H}" width="100%" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="Source Sans 3, sans-serif">' + "".join(p) + "</svg>")


def _to_data_uri(png_path: Path) -> str:
    """base64-encode a PNG for embedding in HTML."""
    if not png_path or not png_path.is_file() or png_path.suffix.lower() != ".png":
        return ""
    return "data:image/png;base64," + base64.b64encode(png_path.read_bytes()).decode("ascii")


def build_context(state: dict, *, maps: dict[str, Path]) -> dict:
    """Build the full Jinja2 context for one state."""
    state_fips = state["state_fips"]
    counties_all = _counties()
    state_counties = counties_all[counties_all["state_fips"] == state_fips].copy()
    state_counties = state_counties.sort_values("subject_count_strict", ascending=False)

    concentration = _concentration(state_counties) if not state_counties.empty else {}

    top10 = state_counties.head(10).to_dict("records")
    top10_rows = []
    total_subject = float(state_counties["subject_count_strict"].sum()) or 1.0
    for i, r in enumerate(top10):
        top10_rows.append({
            "rank": i + 1,
            "name": r["county_name"],
            "subject": int(r["subject_count_strict"]),
            "loss": int(r["loss_exposure_strict"]),
            "rate": _fmt_pct(float(r["subject_rate"]), 1),
            "burden": f"{r['burden_index_centered']:+.1f}",
            "share": _fmt_pct(float(r["subject_count_strict"]) / total_subject, 1),
        })

    burden_top5 = state_counties.sort_values("burden_index_centered", ascending=False).head(5).to_dict("records")
    burden_rows = [
        {
            "name": r["county_name"],
            "burden": f"{r['burden_index_centered']:+.1f}",
            "subject": int(r["subject_count_strict"]),
        }
        for r in burden_top5
    ]

    appendix_rows = []
    for r in state_counties.sort_values("county_name").to_dict("records"):
        appendix_rows.append({
            "name": r["county_name"],
            "fips": r["GEOID"],
            "total_pop": int(r["total_pop"]),
            "working_age_pop": int(r["working_age_pop"]),
            "subject": int(r["subject_count_strict"]),
            "loss": int(r["loss_exposure_strict"]),
            "rate": _fmt_pct(float(r["subject_rate"]), 1),
            "burden": f"{r['burden_index_centered']:+.1f}",
        })

    top_county_cells = []
    if concentration.get("top_county_geoid"):
        top_county_cells = _top_county_cells(concentration["top_county_geoid"])

    csv_url = (
        f"https://data.gizmowarehouse.org/medicaid-work-requirements/data/"
        f"medicaid_counties_{state['state_abbr']}.csv"
    )

    # Loss-breakdown subset (stage 07b) for the "documentation-shaped holes" page.
    lb_root = loss_breakdown()
    lb_entry = None
    if lb_root is not None:
        lb_entry = lb_root.get("states", {}).get(state_fips)
    lb_section = None
    if lb_entry is not None:
        def _band_label(b):
            if b == "low":
                return "admin churn likely substantially mitigated"
            if b == "mid":
                return "mid range"
            if b == "high":
                return "admin churn likely Arkansas-grade"
            return "—"

        def _fmt(n):
            return _fmt_n(n)

        wd_subs = lb_entry["work_hours_doc_failures"]["subgroups"]
        ex_subs = lb_entry["exemption_doc_failures"]["subgroups"]
        wd_total = lb_entry["work_hours_doc_failures"]["total"]
        ex_total = lb_entry["exemption_doc_failures"]["total"]
        total_loss = lb_entry["total_loss_2034"]

        # v8: pull observed-rate-led scores (composite + observed + sources + core) and sub-components.
        ex_scores = lb_entry.get("scores") or {}
        ex_bands = lb_entry.get("bands") or {}
        ex_core_components = lb_entry.get("core_components") or None
        ex_source_components = lb_entry.get("source_components") or None

        lb_section = {
            "total_loss": total_loss,
            "total_loss_compact": _fmt_n(total_loss, compact=True),
            "total_loss_full": _fmt(total_loss),
            "workdoc_total": wd_total,
            "workdoc_total_compact": _fmt_n(wd_total, compact=True),
            "workdoc_pct": _fmt_pct(wd_total / total_loss if total_loss else 0, 0),
            "exemption_total": ex_total,
            "exemption_total_compact": _fmt_n(ex_total, compact=True),
            "exemption_pct": _fmt_pct(ex_total / total_loss if total_loss else 0, 0),
            "noncompliant_total": lb_entry["genuinely_noncompliant"],
            "noncompliant_compact": _fmt_n(lb_entry["genuinely_noncompliant"], compact=True),
            "noncompliant_pct": _fmt_pct(lb_entry["genuinely_noncompliant"] / total_loss if total_loss else 0, 0),
            # Back-compat headline (composite); keep field name so old templates work.
            "ex_parte_score": lb_entry.get("ex_parte_score"),
            "ex_parte_band": lb_entry.get("ex_parte_band"),
            "ex_parte_band_label": _band_label(lb_entry.get("ex_parte_band")),
            # v8: observed-rate-led scores. observed_ex_parte is the dominant factor;
            # core_capability is retained as context only.
            "ex_parte_scores": {
                "composite": ex_scores.get("composite"),
                "observed_ex_parte": ex_scores.get("observed_ex_parte"),
                "data_sources": ex_scores.get("data_sources"),
                "core_capability": ex_scores.get("core_capability"),
            },
            "ex_parte_bands": {
                "composite": ex_bands.get("composite"),
                "composite_label": _band_label(ex_bands.get("composite")),
                "core_capability": ex_bands.get("core_capability"),
                "core_capability_label": _band_label(ex_bands.get("core_capability")),
                "data_sources": ex_bands.get("data_sources"),
                "data_sources_label": _band_label(ex_bands.get("data_sources")),
            },
            "ex_parte_core_components": ex_core_components,
            "ex_parte_source_components": ex_source_components,
            "system_vendor": lb_entry.get("system_vendor", ""),
            "workdoc_subs": [
                {
                    "label": v["label"],
                    "count": v["count"],
                    "count_compact": _fmt_n(v["count"], compact=True),
                    "share_within_bucket": v["count"] / wd_total if wd_total else 0,
                    "narrative": v.get("narrative", ""),
                }
                for v in wd_subs.values()
            ],
            "exemption_subs": [
                {
                    "label": v["label"],
                    "count": v["count"],
                    "count_compact": _fmt_n(v["count"], compact=True),
                    "share_within_bucket": v["count"] / ex_total if ex_total else 0,
                    "narrative": v.get("narrative", ""),
                }
                for v in ex_subs.values()
            ],
        }
        lb_section["sankey_svg"] = _build_sankey_svg(lb_section)
        _all_subs = list(wd_subs.values()) + list(ex_subs.values())
        if _all_subs:
            _td = max(_all_subs, key=lambda s: s["count"])
            lb_section["top_driver"] = {
                "label": _td["label"],
                "count_compact": _fmt_n(_td["count"], compact=True),
            }

    return {
        "state": {
            "name": state["state_name"],
            "abbr": state["state_abbr"],
            "fips": state_fips,
            "expansion": state["expansion"],
            "subject_count": int(state["subject_count_strict"]),
            "subject_count_compact": _fmt_n(state["subject_count_strict"], compact=True),
            "subject_count_full": _fmt_n(state["subject_count_strict"]),
            "loss_exposure": int(state["loss_exposure_strict"]),
            "loss_exposure_compact": _fmt_n(state["loss_exposure_strict"], compact=True),
            "loss_exposure_full": _fmt_n(state["loss_exposure_strict"]),
            "subject_rate": _fmt_pct(float(state["subject_rate"]), 1),
            "burden_index": f"{state['burden_index_centered']:+.1f}",
            "hardship_exception_status": state.get("hardship_exception_status", "unknown"),
            "early_implementer": state.get("early_implementer", ""),
            "note": state.get("note", ""),
        },
        "top_counties": top10_rows,
        "burden_top5": burden_rows,
        "appendix": appendix_rows,
        "concentration": concentration,
        "top_county_cells": top_county_cells,
        "peers": _peer_states(state),
        "checklist": _checklist(state, concentration, lb_section),
        "maps": {
            "state_county_count": _to_data_uri(maps.get("state_county_count", Path())),
            "county_grid": _to_data_uri(maps.get("county_grid", Path())),
            "state_burden": _to_data_uri(maps.get("state_burden", Path())),
            "demographics": _to_data_uri(maps.get("demographics", Path())),
        },
        "csv_url": csv_url,
        "national": summary()["national"],
        "loss_breakdown": lb_section,
        "narrative": narrative_for(state_fips),
    }
