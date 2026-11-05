"""Raw-file manifest + duckdb readers. The only module that touches the raw CSVs."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402


def raw_files() -> list[dict]:
    """Every raw input: (year, vintage label, path)."""
    files = [{"year": y, "vintage": "main", "path": config.RAW_NYC / f"nyc_raw_{y}.csv"} for y in config.YEARS]
    files.append({"year": 2025, "vintage": "held", "path": config.HELD_2025})
    return files


def _sig(path: Path) -> dict:
    st = path.stat()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
        if st.st_size > (2 << 20):
            f.seek(-(1 << 20), os.SEEK_END)
            h.update(f.read(1 << 20))
    return {"bytes": st.st_size, "mtime": int(st.st_mtime), "sha_head_tail": h.hexdigest()}


def file_key(entry: dict) -> str:
    return f"{entry['year']}_{entry['vintage']}"


def load_manifest() -> dict:
    p = config.CACHE_DIR / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_manifest(m: dict) -> None:
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (config.CACHE_DIR / "manifest.json").write_text(json.dumps(m, indent=1, sort_keys=True))


def needs_scan(entry: dict, manifest: dict, force: bool = False) -> bool:
    if force:
        return True
    k = file_key(entry)
    cache_dir = config.CACHE_DIR / k
    if not cache_dir.exists() or not (cache_dir / "violent_rows.parquet").exists():
        return True
    return manifest.get(k, {}).get("sig") != _sig(entry["path"])


def connect(threads: int = 3, mem_gb: int = 3) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET threads={threads}")
    con.execute(f"SET memory_limit='{mem_gb}GB'")
    return con


def read_csv_sql(path: Path) -> str:
    cols = ", ".join(f"'{c}': 'VARCHAR'" for c in config.SLIM_COLUMNS)
    return (f"read_csv('{path}', header=true, all_varchar=true, union_by_name=true, "
            f"ignore_errors=false, sample_size=-1)")


def signature(entry: dict) -> dict:
    return _sig(entry["path"])


def read_cache(name: str, years: list[int] | None = None, vintages: tuple[str, ...] = ("main", "held")) -> pd.DataFrame:
    parts = []
    for d in sorted(config.CACHE_DIR.iterdir()):
        if not d.is_dir():
            continue
        y, v = d.name.split("_")
        if years is not None and int(y) not in years:
            continue
        if v not in vintages:
            continue
        p = d / f"{name}.parquet"
        if p.exists():
            parts.append(pd.read_parquet(p))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
