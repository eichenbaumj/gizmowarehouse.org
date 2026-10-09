"""Stage 02: one long parquet from the OSC zips.

Row = entity × fiscal year × account code. Columns:
  cls, muni_code, entity_name, county, fy, fy_end, section (REVENUE|EXPENDITURE|GL),
  account_code, fund, acct (4-digit body), obj (object digit or ''), narrative,
  level1, level2, object_label, amount

Handles the 2015+ vs pre-2015 column drift (DECISIONS.md). Only the account codes the
analysis needs are kept (config.KEEP_ACCTS) plus every EXPENDITURE row, so total
expenditures can be computed; GL rows are kept for the claims-liability accounts only.
"""

from __future__ import annotations

import io
import re
import sys
import zipfile

import pandas as pd

import config

PREFIX_RE = re.compile(r"^([A-Z]+)(\d{3,4})(\d?)$")

KEEP_ACCTS = {
    config.ACCT_INSURANCE, config.ACCT_JUDGMENTS, config.ACCT_PROPERTY_LOSS,
    config.ACCT_SELF_INS_ADMIN, config.ACCT_DUES, config.ACCT_OTHER_GG, config.ACCT_LAW,
    config.ACCT_POLICE, config.ACCT_JAIL, config.ACCT_HIGHWAY, config.ACCT_WORKERS_COMP,
    config.ACCT_INTERFUND_TRANSFER,
}
KEEP_GL = {config.GL_CLAIMS_PAYABLE, config.GL_INSURANCE_RESERVE}
KEEP_REV = {config.REV_INSURANCE_RECOVERIES}


def _split_code(code: str) -> tuple[str, str, str]:
    """'A19104' -> ('A', '1910', '4'); 'W686' -> ('W', '686', ''); 'MS17104' -> ('MS','1710','4')."""
    m = PREFIX_RE.match(code.strip())
    if not m:
        return ("", code.strip(), "")
    fund, body, obj = m.groups()
    # GL balance-sheet codes are 3 digits (W686, A863); expenditure/revenue are 4 (+ object digit)
    if len(body) == 4 and obj == "" and body[0] in "2345678" and False:
        pass
    return (fund, body, obj)


def _normalize(df: pd.DataFrame, cls: str, year: int) -> pd.DataFrame:
    cols = {c: c.upper() for c in df.columns}
    df = df.rename(columns=cols)
    out = pd.DataFrame()
    out["cls"] = cls
    out["cls"] = out["cls"].astype("string")
    out = pd.DataFrame({
        "cls": cls,
        "muni_code": df["MUNICIPAL_CODE"].astype(str),
        "entity_name": df["ENTITY_NAME"].astype(str).str.strip(),
        "county": df["COUNTY"].astype(str).str.strip(),
        "fy": year,
        "fy_end": df["PERIOD_END"] if "PERIOD_END" in df else df["FISCAL_YEAR_END"],
        "section": (df["ACCOUNT_CODE_SECTION"] if "ACCOUNT_CODE_SECTION" in df
                    else df["FINANCIAL_STATEMENT"]).astype(str).str.upper().str.strip(),
        "account_code": df["ACCOUNT_CODE"].astype(str).str.strip(),
        "narrative": df["ACCOUNT_CODE_NARRATIVE"].astype(str).str.strip(),
        "level1": df.get("LEVEL_1_CATEGORY", "").astype(str),
        "level2": df.get("LEVEL_2_CATEGORY", "").astype(str),
        "object_label": df.get("OBJECT_OF_EXPENDITURE", "").astype(str),
        "amount": pd.to_numeric(df["AMOUNT"], errors="coerce").fillna(0.0),
    })
    # pre-2015 files label the section differently; map anything containing these words
    sec = out["section"]
    out["section"] = sec.where(sec.isin(["REVENUE", "EXPENDITURE", "GL"]), other=sec.map(
        lambda s: "EXPENDITURE" if "EXPEND" in s else "REVENUE" if "REVENUE" in s else "GL"))
    parts = out["account_code"].map(_split_code)
    out["fund"] = [p[0] for p in parts]
    out["acct"] = [p[1] for p in parts]
    out["obj"] = [p[2] for p in parts]
    keep = (
        (out["section"] == "EXPENDITURE")
        | ((out["section"] == "GL") & out["acct"].isin(KEEP_GL))
        | ((out["section"] == "REVENUE") & out["acct"].isin(KEEP_REV))
    )
    return out[keep].reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    argv = argv or []
    force = "--force" in argv
    if config.OSC_LONG_PARQUET.exists() and not force:
        print(f"  cached {config.OSC_LONG_PARQUET.name}")
        return 0
    frames = []
    drift_log = []
    for cls in config.OSC_CLASSES:
        zpath = config.RAW_OSC / f"{cls}_all_years.zip"
        if not zpath.exists():
            print(f"FATAL: {zpath} missing; run 01_fetch_osc.py")
            return 1
        with zipfile.ZipFile(zpath) as z:
            names = sorted(n for n in z.namelist() if n.lower().endswith(".csv"))
            for n in names:
                year = int(re.match(r"(\d{4})", n.split("/")[-1]).group(1))
                raw = z.read(n)
                df = pd.read_csv(io.BytesIO(raw), encoding="latin-1", dtype=str, low_memory=False)
                drift_log.append((cls, year, tuple(df.columns)))
                frames.append(_normalize(df, cls, year))
                print(f"  {cls} {year}: {len(df):,} rows -> kept {len(frames[-1]):,}")
    long = pd.concat(frames, ignore_index=True)
    long["fy"] = long["fy"].astype("int16")
    for c in ("cls", "section", "fund", "acct", "obj", "county"):
        long[c] = long[c].astype("category")
    long.to_parquet(config.OSC_LONG_PARQUET, index=False)
    print(f"  wrote {config.OSC_LONG_PARQUET} ({len(long):,} rows)")
    # column-drift log for DECISIONS.md
    schemas = {}
    for cls, year, cols in drift_log:
        schemas.setdefault(cols, []).append(f"{cls}:{year}")
    with open(config.OUTPUT_DIR / "osc_schema_drift.txt", "w") as f:
        for cols, where in schemas.items():
            f.write(", ".join(cols) + "\n    " + " ".join(where) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
