"""County + tract total / working-age (19-64) population from raw ACS B01001.

Stage 07 uses `county_population()` for the per-capita denominator behind
`subject_rate` (the "share of working-age adults 19-64" the map legend
describes). Stage 08b uses `tract_population()` for the same denominator at the
1-mile grid: it threads each tract's 19-64 population down to the cell (even
split, like subject_count) so the grid/hex per-capita view matches the county
model. Earlier stage 07 divided subject_count by `expansion_pool`, which made
subject_rate a near-constant (~subject/pool ≈ 0.94 everywhere); and the
placeholder county geojson used `total_pop x 0.60` (a flat share). This computes
the real 19-64 population from the ACS B01001 (Sex by Age) table that stage 01
already fetches at BOTH the county and tract level.

B01001 estimate columns (E):
  Male  ages 20-64   = _008 .. _019      Female ages 20-64   = _032 .. _043
  Male  ages 18-19   = _007              Female ages 18-19   = _031
We take all of 20-64 plus half of the combined 18-19 bin as a ~19-64 proxy
(the bin lumps 18 and 19; the subject pool itself is 19-64).
"""
from __future__ import annotations

import pandas as pd

import config  # type: ignore

_MALE_20_64 = [f"B01001_{i:03d}E" for i in range(8, 20)]
_FEMALE_20_64 = [f"B01001_{i:03d}E" for i in range(32, 44)]
_BIN_18_19 = ["B01001_007E", "B01001_031E"]


def _working_age(df: pd.DataFrame) -> pd.Series:
    """19-64 proxy: all of 20-64 plus half of the combined 18-19 bin."""
    full_bins = _MALE_20_64 + _FEMALE_20_64
    return df[full_bins].sum(axis=1) + 0.5 * df[_BIN_18_19].sum(axis=1)


def _population(parquet_name: str, geoid_width: int) -> pd.DataFrame:
    """Return DataFrame[GEOID, total_pop, working_age_pop] from a raw ACS parquet.

    `geoid_width` is 5 for counties, 11 for tracts. working_age_pop ≈ the 19-64
    population (20-64 + half of the 18-19 bin).
    """
    df = pd.read_parquet(config.RAW_DIR / parquet_name)
    df = df.copy()
    df["GEOID"] = df["GEOID"].astype(str).str.zfill(geoid_width)
    return pd.DataFrame(
        {
            "GEOID": df["GEOID"],
            "total_pop": df["B01001_001E"].astype(float),
            "working_age_pop": _working_age(df).astype(float),
        }
    )


def county_population() -> pd.DataFrame:
    """Return DataFrame[GEOID(5), total_pop, working_age_pop] for all counties."""
    return _population("acs_county.parquet", 5)


def tract_population() -> pd.DataFrame:
    """Return DataFrame[GEOID(11), total_pop, working_age_pop] for all tracts.

    Same B01001 formula as `county_population()`, read from the tract-level ACS
    pull (`raw/acs_tract.parquet`, which stage 01 already fetches). Used by stage
    08b as the working-age denominator threaded to the 1-mile grid.
    """
    return _population("acs_tract.parquet", 11)
