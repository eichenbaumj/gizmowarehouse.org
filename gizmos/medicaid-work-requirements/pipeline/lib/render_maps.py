"""Static map renderers for per-state PDF briefs.

Three map types per state:
- State-level county choropleth (subject_count_strict)
- Top-impact county at 1-mile grid resolution (subject_rate, or subject_count)
- State-level burden_index_centered choropleth (diverging palette)

Reuses the brand color ramps that the React map uses. Output is cached at
gizmos/medicaid-work-requirements/pipeline/output/state_maps/{ABBR}_*.png.
"""
from __future__ import annotations

import io
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

import config  # type: ignore

REPO = config.REPO_ROOT
COUNTIES_PATH = REPO / "public/data/medicaid-counties.geojson"
GRID_PATH = REPO / "gizmos/medicaid-work-requirements/pipeline/output/grid_1mi.geojson"
STATE_MAP_DIR = config.OUTPUT_DIR / "state_maps"
STATE_MAP_DIR.mkdir(parents=True, exist_ok=True)

# Brand color ramps — keep in sync with src/config/medicaidWorkRequirementsMap.ts.
STOPS_SUBJECT_COUNT_COUNTY = [
    (0, "#EFF6FF"), (800, "#BFDBFE"), (2_500, "#60A5FA"), (6_000, "#FEF9C3"),
    (11_000, "#FDE047"), (17_000, "#FB923C"), (33_000, "#DC2626"), (91_000, "#7F1D1D"),
]
STOPS_SUBJECT_COUNT_GRID = [
    (0, "#EFF6FF"), (2, "#DBEAFE"), (6, "#BFDBFE"), (19, "#FEF9C3"),
    (53, "#FDE047"), (105, "#FB923C"), (325, "#DC2626"), (1_000, "#7F1D1D"),
]
STOPS_SUBJECT_RATE = [
    (0, "#EFF6FF"), (0.05, "#DBEAFE"), (0.13, "#BFDBFE"), (0.20, "#FEF9C3"),
    (0.27, "#FDE047"), (0.32, "#FB923C"), (0.40, "#DC2626"), (0.45, "#7F1D1D"),
]
STOPS_BURDEN = [
    (-30, "#1F1FD6"), (-15, "#7B9BE0"), (-5, "#D6E4F2"), (0, "#F2F2F2"),
    (5, "#FCE7B5"), (15, "#E69138"), (25, "#B45309"), (40, "#7C2D12"),
]


def _make_cmap(stops):
    """Build a matplotlib BoundaryNorm + ListedColormap from (value, hex) stops."""
    boundaries = [s[0] for s in stops] + [float("inf")]
    colors = [s[1] for s in stops]
    return ListedColormap(colors), BoundaryNorm(boundaries=boundaries, ncolors=len(colors))


def _load_counties() -> gpd.GeoDataFrame:
    if not hasattr(_load_counties, "_cache"):
        _load_counties._cache = gpd.read_file(COUNTIES_PATH)
    return _load_counties._cache  # type: ignore[attr-defined]


def _load_grid_for_county(county_geoid: str) -> gpd.GeoDataFrame:
    """Filter the (huge) 1-mile grid GeoJSON to a single county. Lazy.

    The 815 MB grid file is too large to keep in memory for all 51 states.
    We load it once into module cache and filter per call.
    """
    if not hasattr(_load_grid_for_county, "_cache"):
        _load_grid_for_county._cache = gpd.read_file(GRID_PATH)  # type: ignore[attr-defined]
    grid = _load_grid_for_county._cache  # type: ignore[attr-defined]
    return grid[grid["county_geoid"] == county_geoid].copy()


def _plot_choropleth(
    gdf: gpd.GeoDataFrame,
    column: str,
    cmap,
    norm,
    title: str,
    subtitle: str,
    out_path: Path,
    figsize=(8, 6),
    edgecolor="#9CA3AF",
    linewidth=0.3,
    basemap=False,
) -> Path:
    fig, ax = plt.subplots(figsize=figsize, dpi=200)
    gdf.plot(
        column=column,
        cmap=cmap,
        norm=norm,
        ax=ax,
        edgecolor=edgecolor,
        linewidth=linewidth,
    )
    if basemap:
        try:
            import contextily as cx
            # Use Carto Voyager to match the web map's basemap. CARTO key-enforces
            # its free basemaps (2026-08-26); keyless tiles come back watermarked.
            # Same public key as src/config/basemap.ts.
            provider = cx.providers.CartoDB.VoyagerNoLabels
            provider = provider(url=provider.url + "?key=cb1_271o_1_f779989250ccc009272193f4")
            cx.add_basemap(ax, crs=gdf.crs, source=provider, zoom="auto")
        except Exception as e:
            print(f"  (basemap skipped: {e})")

    ax.set_axis_off()
    ax.set_title(title, fontsize=13, fontweight="600", color="#1F1FD6", loc="left", pad=8)
    ax.text(0, -0.05, subtitle, transform=ax.transAxes, fontsize=9, color="#3B3B3B")
    plt.tight_layout()
    fig.savefig(out_path, bbox_inches="tight", facecolor="white", dpi=200)
    plt.close(fig)
    return out_path


def render_state_county_map(state_abbr: str, state_fips: str, mode: str = "subject_count") -> Path:
    """Render a county-level choropleth for one state."""
    out = STATE_MAP_DIR / f"{state_abbr}_county_{mode}.png"
    if out.exists() and out.stat().st_mtime > COUNTIES_PATH.stat().st_mtime:
        return out  # cached

    counties = _load_counties()
    state_counties = counties[counties["state_fips"] == state_fips].copy()
    if state_counties.empty:
        return out  # nothing to render

    column_map = {
        "subject_count": "subject_count_strict",
        "subject_rate": "subject_rate",
        "loss_exposure": "loss_exposure_strict",
        "burden_index": "burden_index_centered",
    }
    stops_map = {
        "subject_count": STOPS_SUBJECT_COUNT_COUNTY,
        "subject_rate": STOPS_SUBJECT_RATE,
        "loss_exposure": [(s[0] / 3, s[1]) for s in STOPS_SUBJECT_COUNT_COUNTY],
        "burden_index": STOPS_BURDEN,
    }
    column = column_map[mode]
    cmap, norm = _make_cmap(stops_map[mode])

    title_map = {
        "subject_count": "People subject to monthly work-requirement verification",
        "subject_rate": "Share of working-age adults subject to verification",
        "loss_exposure": "Projected coverage loss (30% admin churn)",
        "burden_index": "Verification-burden index (centered on national median)",
    }
    _plot_choropleth(
        state_counties,
        column,
        cmap,
        norm,
        title_map[mode],
        f"County-level estimates, {state_abbr}",
        out,
        figsize=(8, 6),
    )
    return out


def render_county_grid_map(state_abbr: str, county_geoid: str, county_name: str, mode: str = "subject_rate") -> Path:
    """Render a 1-mile grid choropleth for one county."""
    out = STATE_MAP_DIR / f"{state_abbr}_grid_{county_geoid}_{mode}.png"
    if out.exists():
        return out

    grid = _load_grid_for_county(county_geoid)
    if grid.empty:
        # County might be non-expansion or missing from grid. Skip.
        return out

    column_map = {
        "subject_count": ("subject_count_strict", STOPS_SUBJECT_COUNT_GRID),
        "subject_rate": ("subject_rate", STOPS_SUBJECT_RATE),
        "loss_exposure": ("loss_exposure_strict", [(s[0] / 3, s[1]) for s in STOPS_SUBJECT_COUNT_GRID]),
    }
    column, stops = column_map[mode]
    cmap, norm = _make_cmap(stops)

    title_map = {
        "subject_count": f"{county_name} — subject enrollees per 1-mile cell",
        "subject_rate": f"{county_name} — share of working-age adults subject (1-mile cells)",
        "loss_exposure": f"{county_name} — projected coverage loss per 1-mile cell",
    }
    _plot_choropleth(
        grid,
        column,
        cmap,
        norm,
        title_map[mode],
        "1-mile grid resolution. South-Side concentrations vs suburban areas.",
        out,
        figsize=(10, 8),
        edgecolor="none",
        linewidth=0,
        basemap=True,
    )
    return out


def render_state_burden_map(state_abbr: str, state_fips: str) -> Path:
    """Render a burden-index diverging choropleth for one state."""
    return render_state_county_map(state_abbr, state_fips, mode="burden_index")
