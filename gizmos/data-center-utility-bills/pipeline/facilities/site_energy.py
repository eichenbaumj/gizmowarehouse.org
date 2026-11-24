#!/usr/bin/env python3
"""A site's electricity as its operator reports it, year by year.

Meta and Apple publish the electricity each of their data centers used in each
year. Where an operator does that, the site's load in a reported year is the
year's MWh divided by 8,760, in place of the generator-based size and the
assumed ramp (docs/DECISIONS.md, D-35). Load quantities only; no price.

Two tables under verified/, each row read by the session model on the
operator's own document:

  site_energy.csv        campus, year, MWh, the value as printed, the source
  site_energy_sites.csv  campus -> inventory row(s). Two rows on one campus
                         share the campus's figure in proportion to their
                         generator capacity.

Rules (D-35):
  * before the first year with a figure above zero the site carries nothing;
  * a year inside the series with no row carries the year before it;
  * after the last reported year the site carries the last reported figure,
    and an Epoch site carries Epoch's timeline for those years if it is higher.

Run:  python3 -I pipeline/facilities/site_energy.py --check
      re-fetches every cited document into data/raw/operator_energy/ and checks
      that each printed value appears in its text.
"""
from __future__ import annotations

import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

VERIFIED = ROOT / "pipeline" / "facilities" / "verified"
ENERGY = VERIFIED / "site_energy.csv"
SITES = VERIFIED / "site_energy_sites.csv"
RAW = ROOT / "data" / "raw" / "operator_energy"
ENERGY_COLUMNS = ["campus", "operator", "year", "mwh", "year_type", "printed_value", "printed_unit", "source_url",
                  "document", "page", "source_quote", "confidence", "checked_on", "note"]
SITE_COLUMNS = ["campus", "fid", "site_as_the_operator_names_it", "match_basis"]
OPERATOR_DOMAINS = {"sustainability.atmeta.com", "apple.com"}
HOURS = 8760.0


def load(energy: Path | None = None, sites: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    e_path, s_path = energy or ENERGY, sites or SITES
    if not e_path.exists() or not s_path.exists():
        return pd.DataFrame(columns=ENERGY_COLUMNS), pd.DataFrame(columns=SITE_COLUMNS)
    e = pd.read_csv(e_path, dtype={"printed_value": str, "source_quote": str, "note": str, "checked_on": str})
    s = pd.read_csv(s_path, dtype=str)
    return validate(e, s)


def validate(e: pd.DataFrame, s: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Refuse tables the build should not read: every figure needs the operator's own document, opened."""
    for t, cols, name in ((e, ENERGY_COLUMNS, "site energy"), (s, SITE_COLUMNS, "site energy sites")):
        missing = [c for c in cols if c not in t.columns]
        if missing:
            raise ValueError(f"{name} table is missing columns: {missing}")
    if not len(e):
        return e[ENERGY_COLUMNS], s[SITE_COLUMNS]
    if e[["campus", "year", "mwh", "source_url", "source_quote", "checked_on", "printed_value"]].isna().any().any():
        raise ValueError("every site energy row needs a campus, a year, a figure as printed, a source, a quote and the date opened")
    if (e.mwh < 0).any() or e.duplicated(["campus", "year"]).any():
        raise ValueError("one figure per campus and year, and none below zero")
    dom = e.source_url.map(lambda u: urlparse(u).netloc.replace("www.", ""))
    if not dom.isin(OPERATOR_DOMAINS).all():
        raise ValueError("a site energy figure comes from the operator's own document")
    if not e.confidence.isin(["high", "medium"]).all() or not e.year_type.isin(["calendar", "fiscal"]).all():
        raise ValueError("site energy rows are high or medium confidence, for a calendar or a fiscal year")
    if not set(e.campus) <= set(s.campus):
        raise ValueError("every campus with a figure needs an inventory row in site_energy_sites.csv")
    if s.fid.duplicated().any() or s.isna().any().any():
        raise ValueError("an inventory row belongs to one campus, and every match needs its basis")
    return e[ENERGY_COLUMNS], s[SITE_COLUMNS]


def paths(e: pd.DataFrame, s: pd.DataFrame, generator_kw: dict | None = None) -> dict[str, dict[int, float]]:
    """fid -> {year: average MW the operator's figure implies}.

    A campus with two inventory rows is split in proportion to `generator_kw`; it is an
    error if either row has none. A campus whose figures are all zero gives no path.
    """
    out: dict[str, dict[int, float]] = {}
    for campus, g in e.groupby("campus"):
        if g.mwh.max() <= 0:
            continue
        fids = list(s[s.campus == campus].fid)
        if len(fids) == 1:
            shares = {fids[0]: 1.0}
        else:
            kw = {f: (generator_kw or {}).get(f) for f in fids}
            if any(v is None or pd.isna(v) or v <= 0 for v in kw.values()):
                raise ValueError(f"{campus}: a campus split across rows needs each row's generator capacity")
            total = sum(kw.values())
            shares = {f: v / total for f, v in kw.items()}
        for f, share in shares.items():
            out[f] = {int(y): float(m) * share / HOURS for y, m in zip(g.year, g.mwh)}
    return out


def first_year(path: dict[int, float]) -> int:
    """The first year the operator reports any electricity at the site."""
    return min(y for y, v in path.items() if v > 0)


def energy_mw(path: dict[int, float], year: int, after: float | None = None) -> float:
    """Load in `year` for a site with an operator-reported series.

    `after` is what another measured source (Epoch's timeline) shows for the year; it is used
    only past the end of the series, and only if it is higher than the last reported figure.
    """
    start, last = first_year(path), max(path)
    if year < start:
        return 0.0
    if year > last:
        return max(path[last], after or 0.0)
    while year not in path:                     # a gap inside the series carries the year before it
        year -= 1
    return path[year]


def check() -> int:
    """Re-fetch every cited document and confirm each printed value is in its text."""
    e, _ = load()
    RAW.mkdir(parents=True, exist_ok=True)
    bad = 0
    for url, g in e.groupby("source_url"):
        pdf = RAW / Path(urlparse(url).path).name
        if not pdf.exists():
            req = urllib.request.Request(url, headers={"User-Agent": "research-fetch/1.0"})
            pdf.write_bytes(urllib.request.urlopen(req, timeout=120).read())
        text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
        lines = text.splitlines()
        for r in g.itertuples():
            site = r.source_quote.split(" [...] ")[1 if r.operator == "Apple" else 0]
            hit = any(site.split(",")[0] in ln and r.printed_value in ln for ln in lines)
            bad += not hit
            if not hit:
                print(f"NOT FOUND: {r.campus} {r.year} '{r.printed_value}' in {pdf.name}")
        print(f"{pdf.name}: {len(g)} figures checked")
    print("all printed values found in the fetched documents" if not bad else f"{bad} values not found")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(check() if "--check" in sys.argv else (print(load()[0].groupby("campus").year.agg(["min", "max", "size"])) or 0))
