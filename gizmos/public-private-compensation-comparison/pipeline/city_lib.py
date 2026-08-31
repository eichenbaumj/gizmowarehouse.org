"""City payroll helpers: free-text job title -> occupation domain.

The ordered keyword rules live in crosswalks/title_keywords.csv (versioned,
hand-auditable). First match by ascending priority wins. Trade-titled "engineers"
(operating/stationary engineer) are ordered before professional engineering so
they don't pollute the engineering domain — the single most important exclusion.
"""

from __future__ import annotations

import re
import pandas as pd

import config


def load_title_rules() -> list[tuple[int, str, re.Pattern]]:
    df = pd.read_csv(config.CROSSWALK_DIR / "title_keywords.csv")
    rules = [(int(r.priority), r.domain, re.compile(r.pattern, re.IGNORECASE))
             for r in df.itertuples()]
    return sorted(rules, key=lambda t: t[0])


def classify_title(title: str, rules) -> str:
    if not isinstance(title, str):
        return "other"
    for _, domain, pat in rules:
        if pat.search(title):
            return domain
    return "other"
