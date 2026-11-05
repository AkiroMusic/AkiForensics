"""Convergence grading across the three evidence legs.

v0-n1 caveat: thresholds come from one confirmed case. Every verdict carries
that provenance; treat graded output as evidence weighting, not ground truth.
"""

from __future__ import annotations

DISCLAIMER = ("Thresholds v0-n1: calibrated on a single confirmed case. "
              "Verdicts are evidence-weighted, not ground truth.")


def _grade_beatgrid(b: dict, cfg: dict) -> dict:
    if not b.get("applicable"):
        return {"leg": "beatgrid", "verdict": "na", "reason": b.get("reason")}
    bc = cfg["beatgrid"]
    std = b["residual_std_ms"]
    pct03 = b["pct_within_0.3ms"]
    if std >= bc["residual_std_ai_ms"] and pct03 <= bc["pct03_ai_max"]:
        v = "ai_consistent"
    elif std <= bc["residual_std_human_ms"] and pct03 >= bc["pct03_human_min"]:
        v = "human_consistent"
    else:
        v = "inconclusive"
    return {"leg": "beatgrid", "verdict": v,
            "residual_std_ms": std, "pct_within_0.3ms": pct03,
            "bpm": b["bpm"], "bpm_integer_distance": b["bpm_integer_distance"]}


def _grade_spectral(s: dict, container: str, cfg: dict) -> dict:
    lossless_like = any(k in container.lower() for k in ("flac", "wav", "alac"))
    if s.get("brick_wall"):
        if lossless_like:
            return {"leg": "spectral", "verdict": "ai_consistent",
                    "why": (f"brick wall at {s['cutoff_hz']:.0f} Hz "
                            f"(cliff {s['cliff_depth_db']} dB) inside a lossless container"),
                    "cutoff_hz": s.get("cutoff_hz"), "brick_wall": True}
        return {"leg": "spectral", "verdict": "na",
                "why": "source container already lossy; cutoff expected, not diagnostic",
                "cutoff_hz": s.get("cutoff_hz"), "brick_wall": True}
    if not lossless_like:
        return {"leg": "spectral", "verdict": "na",
                "why": "source container already lossy; cutoff expected, not diagnostic",
                "cutoff_hz": s.get("cutoff_hz"), "brick_wall": False}
    if s.get("cutoff_hz") is None:
        return {"leg": "spectral", "verdict": "human_consistent",
                "why": "full-band spectrum to Nyquist; no lossy-encoder fingerprint",
                "cutoff_hz": None, "brick_wall": False}
    return {"leg": "spectral", "verdict": "inconclusive",
            "why": f"rolloff edge at {s['cutoff_hz']:.0f} Hz, not a clean brick wall",
            "cutoff_hz": s.get("cutoff_hz"), "brick_wall": False}


def _grade_metadata(m: dict) -> dict:
    flags = list(m.get("flags", []))
    suspicious = [f for f in flags if f not in ("platform_quality_tag_present",)]
    v = "ai_consistent" if len(suspicious) >= 2 else (
        "suspicious" if suspicious else "clean")
    return {"leg": "metadata", "verdict": v, "flags": flags,
            "platform_fingerprint": m.get("platform_fingerprint", []),
            "vendor": m.get("vendor")}


def aggregate(metadata: dict, spectral: dict, beatgrid: dict,
              container: str, cfg: dict) -> dict:
    legs = {
        "beatgrid": _grade_beatgrid(beatgrid, cfg),
        "spectral": _grade_spectral(spectral, container, cfg),
        "metadata": _grade_metadata(metadata),
    }
    bg, sp, md = legs["beatgrid"]["verdict"], legs["spectral"]["verdict"], legs["metadata"]["verdict"]

    if bg == "ai_consistent" and (sp == "ai_consistent" or md in ("ai_consistent", "suspicious")):
        verdict = "STRONG_AI_EVIDENCE"
    elif bg == "ai_consistent":
        verdict = "LIKELY_AI"
    elif bg == "human_consistent" and sp in ("human_consistent", "na") and md == "clean":
        verdict = "LIKELY_HUMAN"
    elif bg == "na" and sp == "ai_consistent" and md in ("ai_consistent", "suspicious"):
        verdict = "LIKELY_AI_DELIVERY_ONLY"
    elif bg == "inconclusive" and sp == "ai_consistent":
        verdict = "WEAK_AI_EVIDENCE"
    else:
        verdict = "INCONCLUSIVE"

    return {"verdict": verdict, "legs": legs, "threshold_version": cfg["meta"]["version"],
            "disclaimer": DISCLAIMER}
