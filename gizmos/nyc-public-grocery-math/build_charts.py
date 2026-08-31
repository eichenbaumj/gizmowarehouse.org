#!/usr/bin/env python3
"""Generate supporting PNG charts for the grocery math gizmo.

Outputs to public/assets/.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

OUT = Path(__file__).resolve().parent.parent.parent / "public" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

# 17A brand
COBALT = "#1F1FD6"
CAROLINA = "#21A8E0"
CHARCOAL = "#3B3B3B"
RED_ACCENT = "#C0392B"
GREY = "#999999"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.edgecolor": CHARCOAL,
    "axes.labelcolor": CHARCOAL,
    "axes.titlecolor": CHARCOAL,
    "xtick.color": CHARCOAL,
    "ytick.color": CHARCOAL,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titleweight": "bold",
    "axes.titlesize": 13,
    "text.usetex": False,
    "mathtext.default": "regular",
})


# ---------------------------------------------------------------------
# Chart 1: Capex benchmark — $/sqft
# ---------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(11, 5))

categories = [
    "RSMeans US avg supermarket\n(2019, union labor, 44k sqft)",
    "NYC center retail\n(Statista / CBRE, 2022)",
    "NYC commercial avg\n(Turner & Townsend, 2025)",
    "La Marqueta\nflagship (new build)",
]
values = [151, 473, 534, 3333]
colors = [GREY, GREY, CAROLINA, RED_ACCENT]

bars = ax.barh(categories, values, color=colors, edgecolor="white", linewidth=1.5)

# Dollar labels at end of bars
for bar, v in zip(bars, values):
    ax.text(
        v + max(values) * 0.01,
        bar.get_y() + bar.get_height() / 2,
        f"\\${v:,}/sqft",
        va="center",
        fontsize=11,
        fontweight="bold",
        color=CHARCOAL,
    )

ax.set_xlim(0, max(values) * 1.25)
ax.set_xlabel("Construction cost per selling square foot (\\$)")
ax.set_title("La Marqueta flagship vs published construction benchmarks",
             loc="left", pad=15)
# Source caption — placed as a figure-level annotation below the axis label
fig.text(0.02, -0.02,
         "Sources: RSMeans Supermarket Model (2019, union labor); Statista / CBRE NYC retail shopping (2022);"
         " Turner & Townsend International Construction Market Survey (2025).\n"
         "All-in NYC ground-up grocery construction with soft costs plausibly runs $600–1,200/sqft,"
         " putting the like-for-like multiple nearer 3–6× (August 2026 re-audit; see the update's methodology notes).",
         fontsize=8, color=GREY, style="italic")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"\\${x:,.0f}"))
ax.grid(axis="x", color="#EEEEEE", linewidth=0.8)
ax.set_axisbelow(True)

plt.tight_layout()
plt.savefig(OUT / "grocery-capex-benchmark.png", dpi=150, facecolor="white",
            bbox_inches="tight", pad_inches=0.3)
plt.close()
print(f"Wrote {OUT / 'grocery-capex-benchmark.png'}")


# ---------------------------------------------------------------------
# Chart 2: Leverage comparison — $ food benefit per $ public spend
# ---------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 6))

# Corrected August 2026 (adversarial re-audit; see the update's methodology notes):
# school meals repriced at full public cost (~1.0x, was 10x on the state top-up);
# FRESH re-based to Comptroller FN 4-2024 costs + evidence-supported access value
# (2-8x, plotted at the conservative midpoint); bodega deduplicated (10-20x, was
# 32.9x on overlapping catchments). Plan rows unchanged (April reach x spend frame).
interventions = [
    ("Bodega produce upgrade", 15.0, "10–20×", CAROLINA),
    ("New supermarkets via\nFRESH-style abatements", 5.0, "2–8×", CAROLINA),
    ("School meals on weekends\n(full public cost)", 1.0, "~1.0×", CAROLINA),
    ("Costco / BJ's subsidy\nfor SNAP households", 6.5, "6.5×", CAROLINA),
    ("Five city-owned stores\n(charitable case)", 1.3, "1.3×", "#D4AC0D"),
    ("Health Bucks expansion", 1.0, "1.0×", GREY),
    ("SNAP supplement\n($20/mo)", 1.0, "1.0×", GREY),
    ("Five city-owned stores\n(central case)", 0.6, "0.6×", RED_ACCENT),
]
# Sort ascending so the biggest bar lands on top
interventions_sorted = sorted(interventions, key=lambda x: x[1])
names = [i[0] for i in interventions_sorted]
leverages = [i[1] for i in interventions_sorted]
labels = [i[2] for i in interventions_sorted]
cols = [i[3] for i in interventions_sorted]

bars = ax.barh(names, leverages, color=cols, edgecolor="white", linewidth=1.5)

# Leverage labels (ranged rows carry their range, not the plotted midpoint)
for bar, v, lab in zip(bars, leverages, labels):
    ax.text(
        v + 0.4,
        bar.get_y() + bar.get_height() / 2,
        lab,
        va="center",
        fontsize=11,
        fontweight="bold",
        color=CHARCOAL,
    )

# Reference line at 1x
ax.axvline(1.0, color=CHARCOAL, linestyle="--", linewidth=1, alpha=0.5)
ax.text(1.05, -0.5, "1× = direct transfer baseline", fontsize=9, color=CHARCOAL, alpha=0.7,
        style="italic")

ax.set_xlim(0, max(leverages) * 1.15)
ax.set_xlabel("Dollars of food benefit delivered to households  ÷  dollars of public expenditure (10-yr basis)")
ax.set_title("Leverage: nutrition delivered per public dollar spent",
             loc="left", pad=15)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}×"))
ax.grid(axis="x", color="#EEEEEE", linewidth=0.8)
ax.set_axisbelow(True)

plt.tight_layout()
plt.savefig(OUT / "grocery-leverage-comparison.png", dpi=150, facecolor="white")
plt.close()
print(f"Wrote {OUT / 'grocery-leverage-comparison.png'}")


# =============================================================================
# July 2026 update charts — the 30% announcement
# =============================================================================
# Brand-correct set: Source Sans 3 / Source Serif 4 from tools/.fonts-cache,
# and the 17A brand accent palette. As of the August 2026 re-audit the two April
# charts above regenerate like everything else (their byte-freeze retired when
# their data was corrected in place — see DECISION_LEDGER.md D-13). All figures
# derive from the model's July 2026 Update tab; verify_claims.py compares the
# arrays below numerically.
from matplotlib import font_manager

FONTS_CACHE = Path(__file__).resolve().parent.parent.parent / "tools" / ".fonts-cache"
for f in FONTS_CACHE.glob("*.ttf"):
    font_manager.fontManager.addfont(str(f))
plt.rcParams["font.family"] = "Source Sans 3"
TITLE_FONT = font_manager.FontProperties(
    fname=str(FONTS_CACHE / "SourceSerif4-Bold.ttf"), size=14)

STEEL = "#878786"        # footnote text only — not a bar color
DEEP_BLUE = "#1A0068"
WARM_YELLOW = "#FFBD3D"
VELLUM = "#F1F1F2"

# ---- Chart 3: updated leverage comparison -----------------------------------
# Stores rows are throughput-consistent (benefit capped at what five stores can
# physically sell) and leverage is present value at the model's 4% rate ("in
# today's dollars"): April central on that frame = 0.30x; announced central
# (18% blend x $1,019/sqft) = 0.69x. Ranged alternatives (FRESH 2-8x, bodega
# 10-20x deduped) plot conservative midpoints and carry range labels; plain
# cash keeps its deep-blue identity from the reach chart.
lev_rows = [
    ("5 stores — April model\n(10% off, quieter store)",        0.30, "0.30×",            WARM_YELLOW),
    ("5 stores — announced plan\n(30% basket, busy store)",   0.69, "0.69×",            COBALT),
    ("Plain cash transfer",                                   1.0,  "1.0×",             DEEP_BLUE),
    ("SNAP-style supplement\n(\\$20/mo)",                      1.0,  "1.0×",             CAROLINA),
    ("Expand school meals\n(weekends, full cost)",            1.0,  "~1.0×",            CAROLINA),
    ("New private supermarkets via\nFRESH-style abatements",  5.0,  "2–8×",             CAROLINA),
    ("Costco / BJ's subsidy\nfor SNAP households",            6.5,  "6.5×",             CAROLINA),
    ("Bodega produce upgrade",                                15.0, "10–20×",           CAROLINA),
]
fig, ax = plt.subplots(figsize=(11, 6))
names = [r[0] for r in lev_rows]
vals = [r[1] for r in lev_rows]
labels = [r[2] for r in lev_rows]
cols = [r[3] for r in lev_rows]
ax.barh(names, vals, color=cols, edgecolor="white", linewidth=1.5)
for i, (v, lab) in enumerate(zip(vals, labels)):
    ax.text(v + 0.25, i, lab,
            va="center", fontsize=11, fontweight="bold", color=CHARCOAL)
ax.axvline(1.0, color=CHARCOAL, linestyle="--", linewidth=1, alpha=0.5)
ax.text(1.05, -0.55, "1× = plain-cash-transfer floor", fontsize=9, color=CHARCOAL,
        alpha=0.7, style="italic")
ax.set_xlim(0, 20)
ax.set_xlabel("Dollars of food benefit delivered to households  ÷  dollars of public expenditure, in today's dollars (10-yr basis)")
ax.set_title("In today's dollars, the 30% announcement\nmore than doubles the plan's efficiency",
             loc="left", pad=15, fontproperties=TITLE_FONT, color=CHARCOAL)
ax.xaxis.set_major_locator(mticker.MultipleLocator(2))
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}×"))
ax.grid(axis="x", color="#EEEEEE", linewidth=0.8)
ax.set_axisbelow(True)
fig.text(0.02, -0.08,
         "Store rows are throughput-consistent: benefit capped at what five stores can physically sell (model, July 2026 Update tab). Leverage compares\n"
         "ten-year totals in today's dollars (defined in the methodology notes). Announced central: 30% core basket ≈ 18% blended store-wide, industry-average\n"
         "\\$1,019/sqft traffic (FMI 2025), ≈\\$167M ten-year envelope. School meals repriced at full public cost; FRESH shown as its 2–8× access-estimate range;\n"
         "bodega reach deduplicated (~3.33M households). Alternatives tab, rebuilt August 2026.",
         fontsize=8, color=STEEL, style="italic")
plt.tight_layout()
plt.savefig(OUT / "grocery-30-leverage.png", dpi=150, facecolor="white",
            bbox_inches="tight", pad_inches=0.3)
plt.close()
print(f"Wrote {OUT / 'grocery-30-leverage.png'}")

# ---- Chart 4: the ten-year public envelope ----------------------------------
fig, ax = plt.subplots(figsize=(7, 5.2))
cats = ["April model\n(10% off, quieter store)", "Announced plan\n(30% basket, busy store)"]
capex = [70, 70]
subsidy = [30.35, 97.34]
sub_colors = [CAROLINA, COBALT]
x = [0, 1]
ax.bar(x, capex, width=0.55, color=CHARCOAL, edgecolor="white", linewidth=1.5,
       label="Construction (\\$70M, unchanged)")
ax.bar(x, subsidy, width=0.55, bottom=capex, color=sub_colors, edgecolor="white", linewidth=1.5)
ax.set_xticks(x, cats)
totals = [100.35, 167.34]
for i, t in enumerate(totals):
    label = f"\\${t:.0f}M" if i == 0 else f"\\${t:.0f}M  (+67%)"
    ax.text(i, t + 3, label, ha="center", fontsize=13, fontweight="bold", color=CHARCOAL)
ax.text(0, 70 + 30.35 / 2, "\\$30M operating subsidy\nto stores, ten years\n(April frame)", ha="center", va="center",
        fontsize=9.5, color="white", fontweight="bold")
ax.text(1, 70 + 97.34 / 2, "\\$97M operating subsidy\nto stores, ten years", ha="center", va="center",
        fontsize=9.5, color="white", fontweight="bold")
for i in range(2):
    ax.text(i, 35, "\\$70M\nconstruction", ha="center", va="center", fontsize=9.5,
            color="white", fontweight="bold")
ax.set_ylim(0, 190)
ax.set_ylabel("Ten-year public cost (\\$M)")
ax.set_title("Every dollar of discount requires a dollar of operating subsidy",
             loc="left", pad=15, fontproperties=TITLE_FONT, color=CHARCOAL)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"\\${y:.0f}M"))
ax.grid(axis="y", color="#EEEEEE", linewidth=0.8)
ax.set_axisbelow(True)
fig.text(0.02, -0.05,
         "Central cases from the model's July 2026 Update tab (13,800 selling sqft per store, RFP-consistent). The official documents give different\n"
         "store sizes, which moves the announced envelope between \\$156M and \\$173M; a bounding case where the city pays operators the full\n"
         "discount runs ≈\\$197M. No official operating-subsidy figure exists anywhere in the public record as of August 2026.",
         fontsize=8, color=STEEL, style="italic")
plt.tight_layout()
plt.savefig(OUT / "grocery-30-envelope.png", dpi=150, facecolor="white",
            bbox_inches="tight", pad_inches=0.3)
plt.close()
print(f"Wrote {OUT / 'grocery-30-envelope.png'}")

# ---- Chart 5: the reach chart (the money visual) ----------------------------
# Same ~$167M envelope, spent five ways. Bars in thousands of New Yorkers
# (households x 2.48 Census citywide average, applied uniformly); depth per
# household stated in every row label so reach and depth are visible together.
# Depth encoded in the color families: the two full-depth ($1,080) rows in the
# primary blues, the shallower rows in carolina/warm yellow. The FRESH bar
# plots the genuinely-low-access population (USDA FARA band, top of range),
# not the raw catchment; the catchment ceiling lives in the footnote.
reach_rows = [
    ("Five city-owned stores\nfull deal, \\$1,080/HH/yr",          29.1,  COBALT),
    ("Plain cash at the stores'\nown depth, \\$1,080/HH/yr",       38.4,  DEEP_BLUE),
    ("SNAP-style supplement\n\\$240/HH/yr",                        172.9, CAROLINA),
    ("Warehouse-club memberships\n≈\\$600/HH/yr realized",         446.9, WARM_YELLOW),
    ("New private supermarkets via\nFRESH-style abatements\n(access benefit, not a transfer)", 355.0, CAROLINA),
]
fig, ax = plt.subplots(figsize=(11, 6))
names = [r[0] for r in reach_rows]
vals = [r[1] for r in reach_rows]
cols = [r[2] for r in reach_rows]
ax.barh(names, vals, color=cols, edgecolor="white", linewidth=1.5)
end_labels = ["29,000 New Yorkers", "38,000", "173,000", "447,000",
              "≈355,000 New Yorkers beyond a half-mile walk\nto a supermarket (USDA, all incomes)"]
for i, (v, lab) in enumerate(zip(vals, end_labels)):
    ax.text(v + 7, i, lab, va="center", fontsize=11, fontweight="bold", color=CHARCOAL)
ax.set_xlim(0, 640)
ax.set_xlabel("New Yorkers covered per year, same ten-year ≈\\$167M envelope")
ax.set_title("The same \\$167M: 29,000 New Yorkers at full depth,\nor up to fifteen times as many shallower",
             loc="left", pad=15, fontproperties=TITLE_FONT, color=CHARCOAL)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(
    lambda v, _: f"{v/1000:.0f}M" if v >= 1000 else (f"{v:,.0f}k" if v > 0 else "0")))
ax.grid(axis="x", color="#EEEEEE", linewidth=0.8)
ax.set_axisbelow(True)
fig.text(0.02, -0.16,
         "Every row spends the announced plan's envelope: \\$70M capital + \\$9.7M/yr operating subsidy ≈ \\$167M over ten years (\\$16.7M/yr). People from households\n"
         "at the citywide 2.48 persons/household (Census 2020–2024), applied uniformly. Stores row: transfer capacity at industry-average traffic (\\$1,019/sqft,\n"
         "FMI 2025), 30% core basket ≈ 18% blended. Warehouse row: \\$65 memberships, 257,000 funded, ~70% actively used (an author assumption) at ≈\\$600/yr\n"
         "realized savings. FRESH row: an access benefit (2–8× per public dollar), not a transfer; the envelope funds ~150 stores at ≈\\$1.08M public cost each,\n"
         "~15 a year against the program's historic ~2 — a ceiling on uptake, not a forecast — so the bar shows who could genuinely gain access. We use\n"
         "USDA's half-mile distance test as the right instrument for a walking city (the one-mile suburban standard returns ~0 for NYC); the low-income\n"
         "core of that population is roughly 32,000 households, about 80,000 people — see the methodology notes. The bodega route does not fit this axis: ~3.33M households\n"
         "(deduplicated), at shallower depth (see table). Model, July 2026 Update tab.",
         fontsize=8, color=STEEL, style="italic")
plt.tight_layout()
plt.savefig(OUT / "grocery-30-reach.png", dpi=150, facecolor="white",
            bbox_inches="tight", pad_inches=0.3)
plt.close()
print(f"Wrote {OUT / 'grocery-30-reach.png'}")


# ---------------------------------------------------------------------
# Freshness manifest: sha256 of every chart this script just wrote, so the
# verification gate can prove the shipped PNGs came from the current script run
# (the same edit-without-rebuild trap the workbook fingerprint closes).
# ---------------------------------------------------------------------
import hashlib as _hashlib
import json as _json

_manifest = {}
for _name in ("grocery-capex-benchmark.png", "grocery-leverage-comparison.png",
              "grocery-30-leverage.png", "grocery-30-envelope.png", "grocery-30-reach.png"):
    _fp = OUT / _name
    _manifest[_name] = _hashlib.sha256(_fp.read_bytes()).hexdigest()
_manifest_path = Path(__file__).resolve().parent / "charts-manifest.json"
_manifest_path.write_text(_json.dumps(_manifest, indent=1) + "\n")
print(f"Wrote {_manifest_path}")
