"""Convergence grading across the evidence legs — evidence-model v2 (v0-n1).

Design rules (see docs/evidence-model.md):
1. Legs report MEASUREMENT statements, not source attributions.
2. Delivery-chain findings (spectral fingerprint + metadata anomalies) come
   from the same upstream event (a transcode); they corroborate ONE hypothesis
   and are fused as a single vote, never summed as independent evidence.
3. Absence of an anomaly is NOT positive evidence for any source
   (`no_anomaly_detected` != human-consistent).
4. Only positive findings can drive a verdict; every verdict names its
   positive evidence.
"""

from __future__ import annotations

DISCLAIMER = ("Thresholds v0-n1: calibrated on a single confirmed case. "
              "Verdicts are evidence-weighted, not ground truth.")


def _grade_beatgrid(b: dict, cfg: dict) -> dict:
    if not b.get("applicable"):
        return {"leg": "beatgrid", "verdict": "na", "reason": b.get("reason"),
                "interpretation_en": "no steady kick grid; temporal leg not applicable",
                "interpretation_zh": "无稳定底鼓网格，时序链不适用"}
    bc = cfg["beatgrid"]
    std, pct03 = b["residual_std_ms"], b["pct_within_0.3ms"]
    if std >= bc["residual_std_ai_ms"] and pct03 <= bc["pct03_ai_max"]:
        return {"leg": "beatgrid", "verdict": "timing_variation",
                "residual_std_ms": std, "pct_within_0.3ms": pct03,
                "bpm": b["bpm"], "bpm_integer_distance": b["bpm_integer_distance"],
                "interpretation_en": ("timing variability present: consistent with "
                                      "generative audio OR unquantized live playing; "
                                      "source attribution needs converging evidence"),
                "interpretation_zh": ("检测到时序变异：与生成式音频或未量化实录均兼容，"
                                      "来源归因需收敛证据")}
    if std <= bc["residual_std_human_ms"] and pct03 >= bc["pct03_human_min"]:
        return {"leg": "beatgrid", "verdict": "timing_locked",
                "residual_std_ms": std, "pct_within_0.3ms": pct03,
                "bpm": b["bpm"], "bpm_integer_distance": b["bpm_integer_distance"],
                "interpretation_en": ("sample-locked grid: positive evidence for a "
                                      "quantized DAW render (loop/sampler use included)"),
                "interpretation_zh": ("时序采样级锁定：支持量化 DAW 渲染的正向证据"
                                      "（含 loop/采样器使用）")}
    return {"leg": "beatgrid", "verdict": "timing_inconclusive",
            "residual_std_ms": std, "pct_within_0.3ms": pct03,
            "bpm": b["bpm"], "bpm_integer_distance": b["bpm_integer_distance"],
            "interpretation_en": "residuals between decision bounds",
            "interpretation_zh": "残差介于判定界之间"}


def _grade_spectral(s: dict, container: str, cfg: dict) -> dict:
    lossless_like = any(k in container.lower() for k in ("flac", "wav", "alac"))
    if s.get("brick_wall"):
        if lossless_like:
            return {"leg": "spectral", "verdict": "lossy_source_fingerprint",
                    "why": (f"brick wall at {s['cutoff_hz']:.0f} Hz "
                            f"(cliff {s['cliff_depth_db']} dB) inside a lossless container"),
                    "cutoff_hz": s.get("cutoff_hz"), "brick_wall": True}
        return {"leg": "spectral", "verdict": "na",
                "why": "container already lossy; cutoff expected, not diagnostic",
                "cutoff_hz": s.get("cutoff_hz"), "brick_wall": True}
    if not lossless_like:
        return {"leg": "spectral", "verdict": "na",
                "why": "container already lossy; cutoff expected, not diagnostic",
                "cutoff_hz": s.get("cutoff_hz"), "brick_wall": False}
    if s.get("cutoff_hz") is None:
        return {"leg": "spectral", "verdict": "no_anomaly_detected",
                "why": ("full-band spectrum to Nyquist — consistent with BOTH a true "
                        "lossless master and high-quality AI output; not source-diagnostic"),
                "cutoff_hz": None, "brick_wall": False}
    return {"leg": "spectral", "verdict": "inconclusive",
            "why": f"rolloff edge at {s['cutoff_hz']:.0f} Hz, not a clean brick wall",
            "cutoff_hz": s.get("cutoff_hz"), "brick_wall": False}


def _grade_metadata(m: dict) -> dict:
    flags = list(m.get("flags", []))
    suspicious = [f for f in flags if f != "platform_quality_tag_present"]
    v = "anomalies_present" if suspicious else "clean"
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

    # Delivery-chain findings corroborate ONE hypothesis (a transcode event):
    # fused as a single vote, not added as independent evidence.
    delivery_anomaly = sp == "lossy_source_fingerprint" or md == "anomalies_present"

    if bg == "timing_variation" and delivery_anomaly:
        verdict = "STRONG_AI_EVIDENCE"
        positive = ("timing variability (audio-intrinsic) + delivery-chain anomaly "
                    "(correlated group: spectral/metadata)")
    elif bg == "timing_variation":
        verdict = "LIKELY_AI"
        positive = "timing variability (audio-intrinsic) without delivery-chain corroboration"
    elif bg == "timing_locked" and sp in ("no_anomaly_detected", "na") and md == "clean":
        verdict = "LIKELY_HUMAN"
        positive = ("sample-locked grid + full-band spectrum + clean metadata "
                    "(positive consistency, not proof)")
    elif delivery_anomaly:
        verdict = "DELIVERY_CHAIN_ANOMALY"
        positive = ("delivery-chain anomaly only; commonly a transcode of a human OR "
                    "an AI master — timing leg gave no evidence")
    else:
        verdict = "INCONCLUSIVE"
        positive = "no positive evidence in any leg"

    return {"verdict": verdict, "positive_evidence": positive, "legs": legs,
            "delivery_chain_fused": True,
            "threshold_version": cfg["meta"]["version"], "disclaimer": DISCLAIMER}
