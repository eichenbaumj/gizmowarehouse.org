"""Demographic profile chart renderer for per-state PDF briefs.

Renders three stacked horizontal bar trios (age band, kids under 14, work
hours) using the synthetic shares baked into medicaid-subject-profile.json.
Output: single PNG per state.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import config  # type: ignore

REPO = config.REPO_ROOT
PROFILE_PATH = REPO / "public/data/medicaid-subject-profile.json"
OUT_DIR = config.OUTPUT_DIR / "state_maps"

AGE_ORDER = ["19-24", "25-34", "35-44", "45-54", "55-64"]
KIDS_ORDER = ["yes", "no"]
HOURS_ORDER = ["80_plus", "20-79", "1-19", "0"]
HOURS_LABEL = {"80_plus": "≥80 hrs/mo (already compliant)", "20-79": "20–79 hrs/wk",
               "1-19": "1–19 hrs/wk", "0": "Not working"}

COBALT = "#1F1FD6"


def _load_profile() -> dict:
    if not hasattr(_load_profile, "_cache"):
        _load_profile._cache = json.loads(PROFILE_PATH.read_text())
    return _load_profile._cache  # type: ignore[attr-defined]


def render_demographic_chart(state_fips: str, state_abbr: str, subject_total: int) -> Path:
    """Render the 3-panel demographic chart and return the PNG path."""
    out = OUT_DIR / f"{state_abbr}_demographics.png"
    if out.exists():
        return out

    profile = _load_profile()
    entry = profile.get(state_fips) or profile.get("_national")

    fig, axes = plt.subplots(1, 3, figsize=(10, 3.2), dpi=200)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.86, bottom=0.10, wspace=0.55)

    # Panel 1 — Age band
    ax = axes[0]
    vals = [entry["age_band"][k] for k in AGE_ORDER]
    ns = [int(v * subject_total) for v in vals]
    y = np.arange(len(AGE_ORDER))
    ax.barh(y, vals, color=COBALT, alpha=0.85, height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(AGE_ORDER, fontsize=9)
    ax.set_xlim(0, max(vals) * 1.2)
    ax.set_xticks([])
    ax.invert_yaxis()
    ax.set_title("By age band", fontsize=10, color="#3B3B3B", loc="left")
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    for i, (v, n) in enumerate(zip(vals, ns)):
        ax.text(v + max(vals) * 0.02, i, f"{int(v*100)}%  ({n//1000:,}k)",
                va="center", fontsize=8, color="#3B3B3B")

    # Panel 2 — Has kids under 14
    ax = axes[1]
    vals = [entry["has_kids_under_14"][k] for k in KIDS_ORDER]
    ns = [int(v * subject_total) for v in vals]
    labels = ["Has child <14", "No child <14"]
    y = np.arange(len(labels))
    ax.barh(y, vals, color=[COBALT, "#7B9BE0"], alpha=0.9, height=0.55)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlim(0, max(vals) * 1.2)
    ax.set_xticks([])
    ax.invert_yaxis()
    ax.set_title("Family responsibility", fontsize=10, color="#3B3B3B", loc="left")
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    for i, (v, n) in enumerate(zip(vals, ns)):
        ax.text(v + max(vals) * 0.02, i, f"{int(v*100)}%  ({n//1000:,}k)",
                va="center", fontsize=8, color="#3B3B3B")

    # Panel 3 — Work hours
    ax = axes[2]
    vals = [entry["work_hours_per_wk"][k] for k in HOURS_ORDER]
    ns = [int(v * subject_total) for v in vals]
    labels = [HOURS_LABEL[k] for k in HOURS_ORDER]
    y = np.arange(len(labels))
    ax.barh(y, vals, color=COBALT, alpha=0.85, height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlim(0, max(vals) * 1.2)
    ax.set_xticks([])
    ax.invert_yaxis()
    ax.set_title("Current weekly hours", fontsize=10, color="#3B3B3B", loc="left")
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    for i, (v, n) in enumerate(zip(vals, ns)):
        ax.text(v + max(vals) * 0.02, i, f"{int(v*100)}%  ({n//1000:,}k)",
                va="center", fontsize=8, color="#3B3B3B")

    fig.suptitle(
        f"Subject pool composition — {state_abbr}",
        fontsize=11.5, fontweight="600", color=COBALT, x=0.07, ha="left", y=0.97,
    )
    fig.savefig(out, bbox_inches="tight", facecolor="white", dpi=200)
    plt.close(fig)
    return out
