#!/usr/bin/env python3
"""Print the pin block for the availability audit's code, profiles and libraries as they are now (D-72 item 2).

    python3 -I pipeline/electricity/availability_pins.py

The block goes, unchanged, into the ledger entry that carries Joe's execution instruction. P1, P2 and the
preservation step each refuse to run unless every file they use hashes to the value pinned there and every
library they import is at the pinned version. Reads code files only; opens nothing under data/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.electricity import access_guard as guard  # noqa: E402
from pipeline.electricity import availability_codes as av  # noqa: E402


def library_versions() -> dict:
    import duckdb
    import numpy
    import pandas
    import pyarrow
    return {"python": sys.version.split()[0], "numpy": numpy.__version__, "pandas": pandas.__version__,
            "pyarrow": pyarrow.__version__, "duckdb": duckdb.__version__}


def interpreter() -> str:
    """The resolved path of the interpreter running this, which is what run_availability.sh starts (realpath of python3)."""
    import os
    return os.path.realpath(sys.executable)


def pin_block(root: Path, versions: dict | None = None, interp: str | None = None) -> str:
    files = sorted(set(av.P1_PINNED) | set(av.P2_PINNED) | set(av.PRESERVE_PINNED))
    versions = versions or library_versions()
    libs = sorted(set(av.P1_LIBRARIES) | set(av.P2_LIBRARIES) | set(av.PRESERVE_LIBRARIES))
    lines = [av.PIN_HEADER]
    lines += [f"sha256 {guard.sha256(Path(root) / rel)} {rel}" for rel in files]
    lines += [f"version {lib} {versions[lib]}" for lib in libs]
    lines += [f"interpreter {interp or interpreter()}"]
    return "\n".join(lines)


if __name__ == "__main__":
    print(pin_block(ROOT))
