"""EXPERIMENTAL v0: threshold suggestion from reference corpora.

Ingests known-human and known-AI track directories, runs the analysis engine,
prints per-class metric distributions (median / P10 / P90) and the gap between
classes so thresholds can be moved off the single-case defaults.
"""

from __future__ import annotations

import numpy as np
from pathlib import Path

from .engine import analyze_single


def _collect(directory: str, label: str, cfg: dict) -> list[dict]:
    rows = []
    for p in sorted(Path(directory).rglob("*")):
        if p.suffix.lower() not in {".flac", ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma"}:
            continue
        try:
            r = analyze_single(p, cfg)
        except Exception as e:
            print(f"[SKIP] {label} {p.name}: {e}")
            continue
        b = r["beatgrid"]
        if b.get("applicable"):
            rows.append({"class": label, "residual_std_ms": b["residual_std_ms"],
                         "pct03": b["pct_within_0.3ms"],
                         "int_dist": b["bpm_integer_distance"]})
    return rows


def _stats(rows: list[dict], key: str) -> tuple[float, float, float] | None:
    vals = np.array([r[key] for r in rows], dtype=float)
    if len(vals) == 0:
        return None
    return float(np.median(vals)), float(np.percentile(vals, 10)), float(np.percentile(vals, 90))


def run(human_dir: str, ai_dir: str, cfg: dict) -> None:
    print("AkiForensics calibrate (EXPERIMENTAL v0) — distributions below are")
    print("median / P10 / P90 per class; suggested thresholds sit in the gap.\n")
    for label, d in (("HUMAN", human_dir), ("AI", ai_dir)):
        rows = _collect(d, label, cfg)
        print(f"[{label}] usable tracks (timing leg applicable): {len(rows)}")
        for key, unit in (("residual_std_ms", "ms"), ("pct03", "%"), ("int_dist", "BPM")):
            st = _stats(rows, key)
            if st:
                print(f"  {key:16s} median={st[0]:8.3f}  P10={st[1]:8.3f}  P90={st[2]:8.3f} {unit}")
        print()
    print("Next: adjust config/thresholds.toml so human-P90 < ai-P10 margins,")
    print("bump [meta].version (e.g. v0.2-corpus), and re-run the test suite.")
