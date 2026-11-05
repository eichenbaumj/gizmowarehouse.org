"""The phrases the prose must use for a ratio or a share. Mirrored in src/lib (TypeScript) so vitest
and Python agree; keep the rules identical."""
from __future__ import annotations


def times_words(r: float | None) -> str:
    if r is None:
        return "no comparison"
    if 0.9 <= r <= 1.1:
        return "about the same"
    if r < 0.9:
        return f"about {round((1 - r) * 100):d} percent lower"
    if r < 1.9:
        return f"about {round((r - 1) * 100):d} percent higher"
    rounded = round(r * 2) / 2
    txt = f"{rounded:g}" if rounded != int(rounded) else f"{int(rounded)}"
    return f"about {txt} times"


def share_words(s: float) -> str:
    pct = round(s * 100)
    return f"{pct} percent"
