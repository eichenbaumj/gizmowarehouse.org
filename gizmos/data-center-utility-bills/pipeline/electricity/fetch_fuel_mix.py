#!/usr/bin/env python3
"""Fetch EIA state net generation and cut states into natural-gas-share groups.

Source: EIA "Net Generation by State by Type of Producer by Energy Source"
(annual_generation_state.xlsx, linked from https://www.eia.gov/electricity/data/state/).
The raw workbook goes under data/raw/eia_state_generation/ (gitignored, re-fetchable).

For each state and each of 2008, 2009 and 2010: natural gas net generation divided by
total net generation, rows for type of producer "Total Electric Power Industry" and
energy sources "Natural Gas" and "Total". Then the simple mean of the three shares.

Groups: the 48 contiguous states plus DC (49 units) are cut at the terciles of that
mean (numpy linear-interpolation quantiles at 1/3 and 2/3). Rule, written so that 49
units split 16/17/16:  low = mean < cut_low;  mid = cut_low <= mean <= cut_high;
high = mean > cut_high (with 49 units this is 16/17/16). Alaska and Hawaii are not in the 49: each gets the group its own
share falls in under the same two cut points and in_tercile_sample = False.
A positive Total row with no Natural Gas row counts as zero gas only when the state-year's
other listed sources sum to the Total within 1 MWh (checked, and recorded in the report);
the share is then 0.0 and gas_row_absent = True. Any other missing or non-positive figure
is reported, never filled: shares and group are left blank and the state leaves the sample.
(As of the 2025 release this applies to DC and HI for 2008-2010; DC is petroleum only.)

Outputs: data/frozen/fuel_mix_groups.csv, data/frozen/fuel_mix_report.json

Run:  python3 -I pipeline/electricity/fetch_fuel_mix.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "eia_state_generation"
FROZEN = ROOT / "data" / "frozen"
PAGE_URL = "https://www.eia.gov/electricity/data/state/"
URL = "https://www.eia.gov/electricity/data/state/annual_generation_state.xlsx"
UA = {"User-Agent": "research-data-fetch/1.0"}
YEARS = (2008, 2009, 2010)
PRODUCER = "Total Electric Power Industry"
OFF_SAMPLE = ("AK", "HI")
CONTIGUOUS_PLUS_DC = ("AL AZ AR CA CO CT DE DC FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM "
                      "NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
assert len(CONTIGUOUS_PLUS_DC) == 49


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / "annual_generation_state.xlsx"
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        with urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=180) as r:
            data = r.read()
            last_modified = r.headers.get("Last-Modified")
    except Exception as e:
        print("FAIL", URL, repr(e))
        return 1
    dest.write_bytes(data)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pd.read_excel(dest, header=1)
        title = str(pd.read_excel(dest, header=None, nrows=1).iloc[0, 0]).replace("\n", " | ")
    raw.columns = ["year", "state", "producer", "source", "mwh"]
    sub = raw[(raw.producer == PRODUCER) & raw.year.isin(YEARS) & raw.source.isin(["Natural Gas", "Total"])]
    piv = sub.pivot_table(index="state", columns=["source", "year"], values="mwh", aggfunc="sum")

    allrows = raw[(raw.producer == PRODUCER) & raw.year.isin(YEARS)]
    rows, missing, absent_handled = [], [], []
    for st in CONTIGUOUS_PLUS_DC + list(OFF_SAMPLE):
        rec = {"state": st, "gas_row_absent": False}
        bad = []
        for y in YEARS:
            try:
                g, t = piv.loc[st, ("Natural Gas", y)], piv.loc[st, ("Total", y)]
            except KeyError:
                g, t = np.nan, np.nan
            if pd.isna(t) or t <= 0:
                bad.append(y)
                rec[f"gas_share_{y}"] = np.nan
            elif pd.isna(g):
                # Positive Total but no Natural Gas row: zero only if the other listed sources add up to the Total.
                oth = allrows[(allrows.state == st) & (allrows.year == y) & ~allrows.source.isin(["Total", "Natural Gas"])]
                osum = float(oth.mwh.sum())
                if abs(osum - float(t)) <= 1.0:
                    rec[f"gas_share_{y}"] = 0.0
                    rec["gas_row_absent"] = True
                    absent_handled.append({"state": st, "year": y, "total_mwh": float(t),
                                           "sum_of_other_listed_sources_mwh": osum,
                                           "difference_mwh": round(float(t) - osum, 3),
                                           "other_sources": oth.groupby("source").mwh.sum().to_dict(),
                                           "gas_share_set_to": 0.0})
                else:
                    bad.append(y)
                    rec[f"gas_share_{y}"] = np.nan
                    absent_handled.append({"state": st, "year": y, "total_mwh": float(t),
                                           "sum_of_other_listed_sources_mwh": osum,
                                           "difference_mwh": round(float(t) - osum, 3),
                                           "gas_share_set_to": None})
            else:
                rec[f"gas_share_{y}"] = g / t
        if bad:
            missing.append({"state": st, "years_missing_or_nonpositive_total_or_unreconciled": bad})
        rec["gas_share_mean"] = np.mean([rec[f"gas_share_{y}"] for y in YEARS]) if not bad else np.nan
        rec["in_tercile_sample"] = st not in OFF_SAMPLE
        rows.append(rec)
    df = pd.DataFrame(rows)
    gap = {m["state"] for m in missing}
    df["in_tercile_sample"] = df.in_tercile_sample & ~df.state.isin(gap)
    if missing:
        print("MISSING DATA, reported and left blank, nothing filled:", missing)

    samp = df[df.in_tercile_sample].gas_share_mean.to_numpy()
    cut_low, cut_high = (float(v) for v in np.quantile(samp, [1 / 3, 2 / 3]))
    df["fuel_mix_group"] = np.where(df.gas_share_mean < cut_low, "low",
                                    np.where(df.gas_share_mean > cut_high, "high", "mid"))
    df.loc[df.gas_share_mean.isna(), "fuel_mix_group"] = ""
    out = df[["state", "gas_share_2008", "gas_share_2009", "gas_share_2010", "gas_share_mean",
              "fuel_mix_group", "in_tercile_sample", "gas_row_absent"]].copy()
    for c in ("gas_share_2008", "gas_share_2009", "gas_share_2010", "gas_share_mean"):
        out[c] = out[c].round(6)
    FROZEN.mkdir(parents=True, exist_ok=True)
    out.to_csv(FROZEN / "fuel_mix_groups.csv", index=False)

    in_s = out[out.in_tercile_sample]
    report = {
        "source_page": PAGE_URL,
        "source_url": URL,
        "workbook_title_cell": title,
        "date_fetched": fetched_at,
        "last_modified_header": last_modified,
        "raw_path": str(dest.relative_to(ROOT)),
        "raw_sha256": hashlib.sha256(data).hexdigest(),
        "type_of_producer": PRODUCER,
        "years": list(YEARS),
        "units_in_tercile_sample": int(df.in_tercile_sample.sum()),
        "cut_rule": "low: mean < cut_low; mid: cut_low <= mean <= cut_high; high: mean > cut_high; "
                    "cuts are numpy linear quantiles at 1/3 and 2/3 of the tercile sample (the contiguous states plus DC that have data)",
        "cut_points": {"cut_low": round(cut_low, 6), "cut_high": round(cut_high, 6)},
        "count_per_group_sample": in_s.fuel_mix_group.value_counts().reindex(["low", "mid", "high"]).astype(int).to_dict(),
        "off_sample_groups": {r.state: r.fuel_mix_group for r in out[~out.in_tercile_sample].itertuples()
                              if r.fuel_mix_group},
        "shares_outside_0_1": [{"state": r.state, "year": y, "share": round(float(getattr(r, f"gas_share_{y}")), 6)}
                               for r in out.itertuples() for y in YEARS
                               if pd.notna(getattr(r, f"gas_share_{y}")) and not 0 <= getattr(r, f"gas_share_{y}") <= 1],
        "shares_outside_0_1_note": "EIA reports a small negative net generation for some state-source-years "
                                   "(station use exceeding output); kept as published, not clipped",
        "gas_row_absent_handling": "positive Total row, no Natural Gas row: share set to 0.0 only if the other listed "
                                   "sources sum to Total within 1 MWh (gas_row_absent = True); otherwise left blank",
        "gas_row_absent_state_years": absent_handled,
        "states_with_missing_data": missing,
        
    }
    (FROZEN / "fuel_mix_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["cut_points"]), report["count_per_group_sample"], report["off_sample_groups"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
