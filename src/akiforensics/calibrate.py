"""EXPERIMENTAL v0: threshold suggestion from reference corpora.

Ingests known-human and known-AI track directories, runs the analysis engine,
prints per-class metric distributions (median / P10 / P90) and the gap between
classes so thresholds can be moved off the single-case defaults.
"""

from __future__ import annotations

import numpy as np
from pathlib import Path

from .engine import analyze_single


def _collect(directory: str, label: str, cfg: dict) -> tuple[list[dict], list[dict]]:
    """Returns (timing_rows, spectral_rows)."""
    rows, rows_spectral = [], []
    for p in sorted(Path(directory).rglob("*")):
        if p.suffix.lower() not in {".flac", ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma"}:
            continue
        try:
            r = analyze_single(p, cfg, generate_task_cards=False)
        except Exception as e:
            print(f"[SKIP] {label} {p.name}: {e}")
            continue
        b = r["beatgrid"]
        if b.get("applicable"):
            rows.append({"class": label,
                         "residual_std_ms": b.get("residual_std_ms"),
                         "pct03": b.get("pct_within_0.3ms"),
                         "int_dist": b.get("bpm_integer_distance")})
        s = r["spectral"]
        if not s.get("not_applicable"):
            rows_spectral.append({"class": label,
                                  "cutoff_hz": s.get("cutoff_hz"),
                                  "cliff_depth_db": s.get("cliff_depth_db"),
                                  "hf_var": s.get("hf_band_level_variability_db"),
                                  "wall": s.get("brick_wall")})
    return rows, rows_spectral


def _stats(rows: list[dict], key: str) -> tuple[float, float, float] | None:
    vals = np.array([r[key] for r in rows], dtype=float)
    if len(vals) == 0:
        return None
    return float(np.median(vals)), float(np.percentile(vals, 10)), float(np.percentile(vals, 90))


def run(human_dir: str, ai_dir: str, cfg: dict) -> None:
    print("AkiForensics calibrate (EXPERIMENTAL) — distributions below are")
    print("median / P10 / P90 per class; suggested thresholds sit in the gap.")
    print("These are THRESHOLD PROPOSALS — review and version-bump manually;\n"
          "nothing here auto-applies to config/thresholds.toml.\n")
    all_spectral = []
    for label, d in (("HUMAN", human_dir), ("AI", ai_dir)):
        rows, rows_s = _collect(d, label, cfg)
        all_spectral.extend(rows_s)
        print(f"[{label}] tracks with applicable timing leg: {len(rows)}")
        for key, unit in (("residual_std_ms", "ms"), ("pct03", "%"), ("int_dist", "BPM")):
            st = _stats(rows, key)
            if st:
                print(f"  {key:16s} median={st[0]:8.3f}  P10={st[1]:8.3f}  P90={st[2]:8.3f} {unit}")
        if rows_s:
            walls = sum(1 for s in rows_s if s["wall"])
            cuts = [s["cutoff_hz"] for s in rows_s if s["cutoff_hz"]]
            hvs = [s["hf_var"] for s in rows_s if s["hf_var"] is not None]
            print(f"  spectral (n={len(rows_s)}): brick-wall {walls}/{len(rows_s)}"
                  + (f", cutoff {min(cuts):.0f}-{max(cuts):.0f} Hz" if cuts else "")
                  + (f", hf_variability {min(hvs):.1f}-{max(hvs):.1f} dB" if hvs else ""))
        print()
    if all_spectral:
        print(f"spectral rows total: {len(all_spectral)} (per-class above)")
    print("Next: adjust config/thresholds.toml so human-P90 < ai-P10 margins,")
    print("bump [meta].version, and re-run the test suite.")
