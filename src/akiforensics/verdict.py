"""Convergence grading across the evidence legs — evidence-model v2/v3.

Design rules (docs/evidence-model.md):
1. Legs report MEASUREMENT statements, not source attributions.
2. Delivery-chain findings (spectral fingerprint + metadata integrity
   anomalies) come from the same upstream event (a transcode/processing
   chain); they corroborate ONE hypothesis and are fused as a single vote,
   never summed as independent evidence. Packaging/provenance metadata
   flags do NOT feed the vote (context only).
3. Absence of an anomaly is NOT positive evidence for any source
   (`no_anomaly_detected` != human-consistent).
4. Every source-leaning verdict names its positive evidence AND its
   standing alternative hypotheses — shrinking the explanation space is
   the job; hiding the remaining explanations is not.
"""

from __future__ import annotations

_ALT_AI_CONVERGENT = [
    "unquantized live performance + lossy transcode of a human master "
    "(构造性反例路径：实录底鼓 + 人工母带走有损交付)",
]
_ALT_AI_TIMING_ONLY = [
    "unquantized live performance by human musicians "
    "(真人未量化实录同样产生时序变异)",
    "kick-detection or grid-fit error on syncopated material "
    "(同步切分素材上的底鼓检测/网格拟合误差)",
    "genre outside the model's applicability "
    "(曲风超出时序链适用范围)",
]
_ALT_HUMAN = [
    "loop/sampler-based AI-hybrid production can also be sample-locked "
    "(采样器/loop 式 AI 混合制作同样锁格)",
]


def _disclaimer(version: str) -> str:
    return (f"Thresholds {version}: calibrated on one confirmed case + a small "
            "real-AI reference set, human side physics-based. Verdicts are "
            "evidence-weighted hypotheses, not ground truth.")


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
                "interpretation_en": ("sample-locked grid: production-consistency "
                                      "evidence for a quantized render (loop/sampler "
                                      "workflows included — not authorship proof)"),
                "interpretation_zh": ("时序采样级锁定：量化渲染的制作一致性证据"
                                      "（含 loop/采样器工作流，非作者身份证明）")}
    return {"leg": "beatgrid", "verdict": "timing_inconclusive",
            "residual_std_ms": std, "pct_within_0.3ms": pct03,
            "bpm": b["bpm"], "bpm_integer_distance": b["bpm_integer_distance"],
            "interpretation_en": "residuals between decision bounds",
            "interpretation_zh": "残差介于判定界之间"}


def _grade_spectral(s: dict, container: str, cfg: dict) -> dict:
    lossless_like = any(k in container.lower() for k in ("flac", "wav", "alac"))
    if s.get("not_applicable"):
        return {"leg": "spectral", "verdict": "na",
                "why": s.get("na_reason", "spectral leg not applicable at this sample rate"),
                "cutoff_hz": None, "brick_wall": False}
    if s.get("brick_wall"):
        if lossless_like:
            return {"leg": "spectral", "verdict": "lossy_source_fingerprint",
                    "why": (f"stable HF boundary at {s['cutoff_hz']:.0f} Hz "
                            f"(cliff {s['cliff_depth_db']} dB) inside a lossless "
                            "container — consistent with a lossy transcode; master "
                            "LPF/hardware limits remain possible (see RX-001/RX-003)"),
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
    fams = m.get("flag_families") or {}
    integrity = fams.get("integrity") or [f for f in flags if f in
                                          ("md5_mismatch", "decoder_errors",
                                           "metadata_truncated", "metadata_read_error",
                                           "metadata_block_oversized")]
    v = "integrity_anomalies" if integrity else "clean"
    return {"leg": "metadata", "verdict": v, "flags": flags,
            "flag_families": fams,
            "integrity_flags": integrity,
            "platform_fingerprint": m.get("platform_fingerprint", []),
            "vendor": m.get("vendor"),
            "note": ("packaging/provenance flags are context only — they do not "
                     "feed the delivery-chain vote；packaging/provenance 仅作上下文，不参与交付链投票")}


def aggregate(metadata: dict, spectral: dict, beatgrid: dict,
              container: str, cfg: dict) -> dict:
    legs = {
        "beatgrid": _grade_beatgrid(beatgrid, cfg),
        "spectral": _grade_spectral(spectral, container, cfg),
        "metadata": _grade_metadata(metadata),
    }
    bg, sp, md = legs["beatgrid"]["verdict"], legs["spectral"]["verdict"], legs["metadata"]["verdict"]
    version = cfg["meta"]["version"]

    # Convergence requires the SPECTRAL fingerprint: metadata INTEGRITY
    # anomalies may be corruption/editing, not transcoding — they can raise a
    # standalone DELIVERY_CHAIN_ANOMALY but must never upgrade to CONVERGENT.
    delivery_anomaly = sp == "lossy_source_fingerprint"
    integrity_anomaly = md == "integrity_anomalies"

    if bg == "timing_variation" and delivery_anomaly:
        verdict = "AI_EVIDENCE_CONVERGENT"
        positive = ("timing variability (audio-intrinsic) + delivery-chain anomaly "
                    "(correlated group: spectral/metadata-integrity)")
        alternatives = _ALT_AI_CONVERGENT
        human_gate = True
    elif bg == "timing_variation":
        verdict = "LIKELY_AI"
        positive = "timing variability (audio-intrinsic) without delivery-chain corroboration"
        alternatives = _ALT_AI_TIMING_ONLY
        human_gate = False
    elif bg == "timing_locked" and sp == "no_anomaly_detected" and md == "clean":
        verdict = "LIKELY_HUMAN"
        positive = ("sample-locked grid + MEASURED full-band spectrum + clean metadata "
                    "(production-consistency evidence, not authorship proof)")
        alternatives = _ALT_HUMAN
        human_gate = False
    elif delivery_anomaly or integrity_anomaly:
        verdict = "DELIVERY_CHAIN_ANOMALY"
        why = ("spectral lossy-source fingerprint" if delivery_anomaly
              else "metadata integrity anomalies (corruption/editing possible)")
        positive = (f"{why} only; commonly a transcode of a human OR an AI master — "
                    "timing leg gave no evidence")
        alternatives = []
        human_gate = False
    else:
        verdict = "INCONCLUSIVE"
        positive = "no positive evidence in any leg"
        alternatives = []
        human_gate = False

    return {"verdict": verdict, "positive_evidence": positive,
            "alternative_hypotheses": alternatives,
            "human_gate_recommended": human_gate,
            "calibration_status": "preliminary",
            "human_reference_status": "insufficient",
            "probability_calibrated": False,
            "legs": legs, "delivery_chain_fused": True,
            "threshold_version": version, "disclaimer": _disclaimer(version)}
