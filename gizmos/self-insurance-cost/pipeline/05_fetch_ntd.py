"""Stage 05: pull the NTD operating-expense (by type) and service (by mode) datasets
from the DOT open-data portal (Socrata), 2022–2024, into raw/ntd/*.json."""

from __future__ import annotations

import json
import sys

import config
import fetchers


def main(argv: list[str] | None = None) -> int:
    argv = argv or []
    force = "--force" in argv
    config.ensure_dirs()
    for name, ds in (("opex_by_type", config.NTD_OPEX_BY_TYPE), ("service_by_mode", config.NTD_SERVICE_BY_MODE)):
        dest = config.RAW_NTD / f"{name}_{ds}.json"
        if dest.exists() and not force:
            print(f"  cached {dest.name}")
            continue
        rows = fetchers.socrata_all(ds)
        dest.write_text(json.dumps(rows))
        print(f"  wrote {dest.name}: {len(rows):,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
