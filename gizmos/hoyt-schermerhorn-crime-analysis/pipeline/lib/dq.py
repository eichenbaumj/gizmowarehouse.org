"""Data-quality result registry. Statuses:
  fail     GATE tripped: the build exits non-zero
  warn     passes; its footnote ships in dq.json and the methods note must carry it
  kill     a claim is unpublishable; verify_claims and vitest refuse the prose
  report   a number shipped without judgment
  pass     a gate that held
  skipped  a test whose material does not exist yet (recorded with the reason)"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class DqResult:
    id: str
    group: str
    title: str
    status: str
    value: object = None
    threshold: object = None
    reading: str = ""
    affects: list = field(default_factory=list)
    footnote: str | None = None


class Registry:
    def __init__(self) -> None:
        self.results: list[DqResult] = []

    def add(self, r: DqResult) -> DqResult:
        self.results.append(r)
        flag = {"fail": "FAIL", "warn": "WARN", "kill": "KILL", "pass": "PASS", "report": "rep ", "skipped": "skip"}[r.status]
        print(f"  [{flag}] {r.id} {r.title}: {r.reading}")
        return r

    def gate(self, id, group, title, ok: bool, value, threshold, reading, affects=(), footnote=None, warn_only=False):
        status = "pass" if ok else ("warn" if warn_only else "fail")
        return self.add(DqResult(id, group, title, status, value, threshold, reading, list(affects), footnote if not ok else None))

    def warn_if(self, id, group, title, bad: bool, value, threshold, reading, affects=(), footnote=None):
        return self.add(DqResult(id, group, title, "warn" if bad else "pass", value, threshold, reading, list(affects), footnote if bad else None))

    def kill_if(self, id, group, title, bad: bool, value, threshold, reading, affects=(), footnote=None):
        return self.add(DqResult(id, group, title, "kill" if bad else "pass", value, threshold, reading, list(affects), footnote if bad else None))

    def report(self, id, group, title, value, reading, affects=(), footnote=None):
        return self.add(DqResult(id, group, title, "report", value, None, reading, list(affects), footnote))

    def skipped(self, id, group, title, reason, affects=()):
        return self.add(DqResult(id, group, title, "skipped", None, None, reason, list(affects)))

    def failed(self) -> bool:
        return any(r.status == "fail" for r in self.results)

    def kills(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for r in self.results:
            if r.status == "kill":
                for c in r.affects:
                    out.setdefault(c, []).append(r.id)
        return out

    def footnotes(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for r in self.results:
            if r.status == "warn" and r.footnote:
                for c in r.affects or ["general"]:
                    out.setdefault(c, []).append(r.footnote)
        return out

    def to_json(self) -> list[dict]:
        return clean_nan([asdict(r) for r in self.results])

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), indent=1, default=_default))

    @staticmethod
    def load(path: Path) -> "Registry":
        reg = Registry()
        for d in json.loads(path.read_text()):
            reg.results.append(DqResult(**d))
        return reg


def clean_nan(o):
    """Recursively turn NaN/inf into None so every public file is strict JSON."""
    import math
    if isinstance(o, dict):
        return {k: clean_nan(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_nan(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    try:
        import numpy as np
        if isinstance(o, np.floating) and (np.isnan(o) or np.isinf(o)):
            return None
    except Exception:
        pass
    return o


def _default(o):
    try:
        import numpy as np
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:
        pass
    return str(o)
