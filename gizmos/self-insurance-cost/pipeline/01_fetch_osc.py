"""Stage 01: download the NY State Comptroller account-level bulk zips, one per class.

Idempotent: skips files already in raw/osc/ unless --force. Verifies each file is a
real zip (the OSC server returns an HTML 404 page under a .zip name for wrong class names).
"""

from __future__ import annotations

import sys

import config
import fetchers


def main(argv: list[str] | None = None) -> int:
    argv = argv or []
    force = "--force" in argv
    config.ensure_dirs()
    for cls in config.OSC_CLASSES:
        url = config.OSC_ZIP_URL.format(cls=cls)
        dest = config.RAW_OSC / f"{cls}_all_years.zip"
        fetchers.download(url, dest, force=force, expect_zip=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
