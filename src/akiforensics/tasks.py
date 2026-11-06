"""Human-in-the-loop task card generation (protocol 1.0).

Design rules (docs/HUMAN_WORKFLOW.md):
- Cards are generated deterministically from analysis results: the same
  analysis always yields the same cards (segment positions are computed,
  never "pick a stable part").
- Blinding levels: "value" (default; card shows the hypothesis but never the
  engine's own numbers), "hypothesis" (card also strips hypothesis/evidence-
  gap/acceptance into an operator_view — the operator measures without
  knowing what is suspected), "none" (open mode for对照 runs). The
  dual-track comparison happens after return, on both records.
- Cards target evidence gaps: a task is issued only if its outcome can move
  the verdict. Max 3 auto cards per round; stage-2 cards (UVR-001) are
  generated on demand after stage-1 flags.

任务卡生成（协议 1.0）。原则：确定性分段、盲化分级（value/hypothesis/none）、
按证据缺口发卡、验收可证伪。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

PROTOCOL = "1.0"
BLINDING_LEVELS = ("value", "hypothesis", "none")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _band_center_segment(analysis: dict, lo_hz: float, hi_hz: float,
                         width_s: float, duration: float) -> tuple[float, float]:
    """Deterministic segment: center at the smoothed band-energy maximum."""
    pd = analysis["spectral"].get("_plotdata") or {}
    f, spec_db, t = pd.get("freqs"), pd.get("spec_db"), pd.get("spec_t")
    if f is None:
        return (max(0.0, duration / 2 - width_s / 2),
                min(duration, duration / 2 + width_s / 2))
    band = (f >= lo_hz) & (f <= hi_hz)
    if not band.any():
        return (0.0, min(width_s, duration))
    levels = 10 ** (spec_db[band].mean(axis=0) / 10)
    k = max(1, int(2.0 / (t[1] - t[0]))) if len(t) > 1 else 1
    kernel = np.ones(k) / k
    sm = np.convolve(levels, kernel, "same")
    center = float(t[int(np.argmax(sm))])
    half = width_s / 2
    start = float(np.clip(center - half, 0, max(0.0, duration - width_s)))
    return start, min(start + width_s, duration)


def _loudest_segment(analysis: dict, width_s: float, duration: float) -> tuple[float, float]:
    pd = analysis["spectral"].get("_plotdata") or {}
    f, spec_db, t = pd.get("freqs"), pd.get("spec_db"), pd.get("spec_t")
    if f is None:
        return (0.0, min(width_s, duration))
    band = (f >= 50) & (f <= 8000)
    levels = 10 ** (spec_db[band].mean(axis=0) / 10)
    k = max(1, int(2.0 / (t[1] - t[0]))) if len(t) > 1 else 1
    sm = np.convolve(levels, np.ones(k) / k, "same")
    if len(t) > 1:
        step = t[1] - t[0]
        w = int(width_s / step)
        if w > 0 and w < len(sm):
            csum = np.convolve(sm, np.ones(w), "valid")
            start = float(t[int(np.argmax(csum))])
        else:
            start = 0.0
    else:
        start = 0.0
    start = float(np.clip(start, 0, max(0.0, duration - width_s)))
    return start, min(start + width_s, duration)


def _pick_beats(analysis: dict, n: int = 5) -> list[float]:
    bt = (analysis["beatgrid"].get("_plotdata") or {}).get("beat_times")
    if bt is None or len(bt) < n:
        return []
    arr = np.asarray(bt, dtype=float)
    q = np.linspace(0.1, 0.9, n)
    return [round(float(arr[int(p * (len(arr) - 1))]), 2) for p in q]


def _card(task_id, tool, segment, hypothesis_zh, hypothesis_en, steps, record,
          acceptance, gap, blinded=True, extra=None) -> dict:
    card = {
        "task_id": task_id, "protocol": PROTOCOL, "blinded": blinded,
        "tool": tool,
        "segment": {"start_s": round(segment[0], 2), "end_s": round(segment[1], 2),
                    "selection_rule": "engine 按检出特征计算，非人工挑选"},
        "hypothesis_zh": hypothesis_zh, "hypothesis_en": hypothesis_en,
        "steps_zh": steps, "record_fields": record,
        "acceptance": acceptance,
        "evidence_gap": gap,
    }
    if extra:
        card.update(extra)
    return card


def _blind_steps(task_id: str, segment: tuple) -> list[str]:
    """Hypothesis-blinded measurement instructions: a neutral full-band survey,
    never naming the suspected phenomenon."""
    return [
        f"1. 打开原始音频文件，跳转至 {segment[0]:.2f}s",
        f"2. 选中 {segment[0]:.2f}s – {segment[1]:.2f}s（整段，不要改选）",
        "3. Spectrogram：FFT Size = 8192、Window = Hann，截图（含时间轴与频率轴刻度）",
        "4. Spectrum Analyzer：分别对 L / R 声道做整段平均，各截图一张（设置入镜）",
        "5. 记录 5 kHz–22 kHz 范围内所有你观察到的明显频率边界或异常（频率 + 简述）；没有就写 none",
        "6. 记录工具版本号",
    ]


def _operator_view(card: dict) -> dict:
    """Hypothesis-blinded projection: measurement task only — no hypothesis,
    no evidence gap, no acceptance wording that hints at what is suspected."""
    steps = card.get("blind_steps_zh", card["steps_zh"])
    record = card["record_fields"]
    if "blind_steps_zh" in card:
        # fully hypothesis-blinded: generic record schema — field names like
        # cutoff_hz_left would leak what is being hunted
        record = {"boundaries_left": "数组：[{freq_hz, note}] 或 none",
                  "boundaries_right": "数组：[{freq_hz, note}] 或 none",
                  "tool_version": "字符串"}
    return {"task_id": card["task_id"], "protocol": card["protocol"],
            "tool": card["tool"], "segment": card["segment"],
            "steps_zh": steps, "record_fields": record,
            "instruction_zh": ("请按步骤独立完成测量并如实记录；不要向 AI 询问任何预期值，"
                               "也不要根据既往分析推测目标结果。"),
            "file_sha256": card.get("file_sha256")}


def generate_tasks(analysis: dict, blinded: bool = True,
                   blinding_level: str = "value",
                   force: tuple[str, ...] = ()) -> list[dict]:
    """Auto cards target evidence gaps; `force` adds on-demand stage-2 cards."""
    if blinding_level not in BLINDING_LEVELS:
        raise ValueError(f"blinding_level must be one of {BLINDING_LEVELS}")
    blinded = blinding_level != "none"
    duration = float(analysis["metadata"].get("duration_s") or 0) or \
        float(analysis.get("file", {}).get("duration_s") or 0)
    legs = analysis["verdict"]["legs"]
    sp, bg, md = legs["spectral"], legs["beatgrid"], legs["metadata"]
    sha = analysis["file"].get("sha256") or _sha256(analysis["file"]["path"])
    cards: list[dict] = []

    # RX-001 — cutoff verification (only when a wall was detected)
    if sp["verdict"] == "lossy_source_fingerprint":
        seg = _band_center_segment(analysis, 16000, 19500, 10.0, duration)
        s1, s2, s3 = (round(seg[0] + (seg[1] - seg[0]) * f, 2) for f in (0, 1 / 3, 2 / 3))
        cards.append(_card(
            "RX-001",
            {"name": "iZotope RX 12", "module": "Spectrogram + Spectrum Analyzer", "version": "由执行人记录"},
            seg,
            "高频能量在固定频率处终止（有损转码伪迹），而非全频带自然延展（真无损母带）",
            "HF energy terminates at a fixed frequency (transcode artifact) vs. full-band extension (true lossless master)",
            [
                f"1. 打开原始音频文件（禁止使用任何已转码副本），跳转至 {seg[0]:.2f}s",
                f"2. 选中 {seg[0]:.2f}s – {seg[1]:.2f}s（整 10 秒，不要改选其他区间）",
                "3. Spectrogram：FFT Size = 8192、Window = Hann，对整段截图（含时间轴与频率轴刻度）",
                "4. Spectrum Analyzer：分别对 L / R 声道做整段平均，各截图一张（设置入镜）",
                f"5. 在三个子段（{s1}s–{s2}s、{s2}s–{round(seg[0] + (seg[1] - seg[0]) * 2 / 3, 2)}s、"
                f"{round(seg[0] + (seg[1] - seg[0]) * 2 / 3, 2)}s–{seg[1]}s）分别读取能量骤降处的频率；读不到填 null",
                "6. 记录：墙是否在三个子段保持同一频率；L/R 是否一致；墙上方是否接近数字静默",
                "7. 记录你使用的 RX 版本号",
            ],
            {"cutoff_hz_left": "数值或 null", "cutoff_hz_right": "数值或 null",
             "wall_stable_across_subsegments": "yes / no",
             "lr_consistent": "yes / no", "above_wall_silence": "yes / no / partial",
             "rx_version": "字符串", "screenshots": ["spectrogram.png", "spectrum_L.png", "spectrum_R.png"]},
            {"confirm": "墙存在、三个子段稳定（±200 Hz）且 L/R 一致 → 确认稳定高频边界存在"
                        "（与有损转码兼容；母带低通/硬件频限仍可能，需 RX-003 多分辨率对照排除）",
             "refute": "无墙，或子段间截止漂移 >500 Hz → 推翻转码假设",
             "undetermined": "边界模糊无法测量"},
            "可改变 spectral 链结论（确证/推翻有损源指纹）",
            blinded=blinded,
            extra={"file_sha256": sha,
                   "blind_steps_zh": _blind_steps("RX-001", seg),
                   "blinding_note": "测量盲化：记录全部数值前，不要向 AI 询问任何预期值"}))

    # RX-002 — kick waveform inspection (only when timing variation detected)
    if bg["verdict"] == "timing_variation":
        beats = _pick_beats(analysis, 5)
        if beats:
            cards.append(_card(
                "RX-002",
                {"name": "iZotope RX 12", "module": "Waveform + Spectrogram", "version": "由执行人记录"},
                (beats[0], min(beats[-1] + 0.5, duration)),
                "底鼓为同一采样样本的重复触发（采样器/采样型生成），还是每次波形各异（实录/多样化合成）",
                "Kicks are repeats of one identical sample (sampler/sample-based generation) vs. varying waveforms (live/synth variety)",
                [f"1. 跳转至以下 5 个时间点：{', '.join(f'{b:.2f}s' for b in beats)}",
                 "2. 每个时间点截取该 kick 起振前后约 200 ms 的波形 + 频谱截图（横向缩放到相同精度）",
                 "3. 对比 5 张截图：底鼓波形彼此是否高度一致；起振是否尖锐；音色是否相同",
                 "4. 若发现某 kick 明显不同（fill/变奏），单独标注其时间点"],
                {"kicks_identical": "yes / no / mostly", "attack_sharp": "yes / no",
                 "outlier_timestamps": "列表或空", "screenshots": ["kick_1.png … kick_5.png"]},
                {"confirm": "5 个 kick 波形高度一致（同一采样样本复用）",
                 "refute": "多数 kick 波形明显不同（演奏/合成多样性）",
                 "undetermined": "部分一致或截图精度不足",
                 "note": "本任务不单独定来源，只为时序变异提供上下文"},
                "为 timing 变异补充上下文证据",
                blinded=blinded, extra={"file_sha256": sha, "beat_times": beats}))

    # DAW-001 — structured listening gate: both for clean-looking tracks
    # (final confirmation) and for convergent AI verdicts (alternative-
    # hypothesis check: a human unquantized+transcode production should NOT
    # show generative vocal artifacts).
    convergent = analysis["verdict"]["verdict"] == "AI_EVIDENCE_CONVERGENT"
    clean_track = (bg["verdict"] == "timing_locked"
                   and sp["verdict"] in ("no_anomaly_detected", "na")
                   and md["verdict"] == "clean")
    if convergent or clean_track:
        gap = ("收敛判定的听感终审：排查替代假设（实录+转码的人工曲不应有人声生成伪影）"
               if convergent else "自动链全净时的最终确认门")
        cards.append(_card(
            "DAW-001",
            {"name": "任意 DAW / 播放器 + 耳机", "module": "人工听检", "version": "n/a"},
            (0.0, duration),
            "全曲。逐项检查人声与制作是否存在生成式伪影（清单制，逐项给时间戳）",
            "Full-track structured listening for generative artifacts (checklist with timestamps)",
            [
                "1. 全曲完整听 1 遍，再对有人声的段落复听",
                "2. 逐项检查并在记录表填写：是否有、出现时间（秒）、备注",
                "   VOCAL-ARTICULATION 咬字含糊/粘连/无意义音节",
                "   VOCAL-DOUBLE 人声相位化双重/合唱感异常",
                "   BREATH 气口缺失或不自然",
                "   REVERB 混响尾长度/空间感前后不一致",
                "   ARRANGEMENT 乐器数量、和声进行、段落衔接不合逻辑",
                "   ENDING 结尾淡出/骤停方式是否像真人收尾",
                "   STEREO 声像异常跳变",
                "   OTHER 任何\"不像人做出来\"的细节",
                "3. 全部 8 项都要填（没有写 no），不留空",
            ],
            {"checks": [{"id": "VOCAL-ARTICULATION|VOCAL-DOUBLE|BREATH|REVERB|ARRANGEMENT|ENDING|STEREO|OTHER",
                          "present": "yes / no / unsure", "timestamp_s": "数值或 null", "note": "自由文本"}],
             "listening_environment": "耳机/音箱型号"},
            {"confirm": "≥2 项人声相关检查为 yes → 听感疑点成立，触发 UVR-001 分离验证",
             "refute": "全部 no，或仅 ≤1 项非人声 yes → 听感层面无异常（低强度证据）",
             "undetermined": "多项 unsure，需换环境复听",
             "note": "听检为主观证据，永远不单独定来源"},
            gap,
            blinded=blinded, extra={"file_sha256": sha}))

    # PA-001 — Pure Analyzer realtime profile (descriptive, on demand or when locked)
    if "PA-001" in force:
        seg = _loudest_segment(analysis, 60.0, duration)
        cards.append(_card(
            "PA-001",
            {"name": "Flux Pure Analyzer", "module": "Realtime Spectrum / Stereo / Loudness", "version": "由执行人记录"},
            seg,
            "刻画响度/立体声/动态的母带特征（描述性证据，不判来源）",
            "Describe mastering profile (loudness/stereo/dynamics) — descriptive only, not source-diagnostic",
            [
                f"1. 将 Pure Analyzer 挂在 DAW 主总线，播放 {seg[0]:.1f}s – {seg[1]:.1f}s（整段连续播放，中途不动任何控制）",
                "2. 记录：Stereo Correlation 最小值/最大值、Integrated LUFS、True Peak (dBTP)",
                "3. 观察 Correlation 表在全段是否稳定，截图仪表状态（参数入镜）",
                "4. 记录采样率与测量模式设置",
            ],
            {"stereo_corr_min": "数值", "stereo_corr_max": "数值",
             "lufs_integrated": "数值", "true_peak_dbtp": "数值",
             "correlation_stable": "yes / no", "screenshots": ["meters.png"]},
            {"interpretation": "描述性画像：与交付链/母带风格分析相关，不参与来源判定",
             "note": "LUFS/TP 等本身不是 AI 鉴别特征"},
            "母带画像（描述性）",
            blinded=False, extra={"file_sha256": sha}))

    # UVR-001 — stem separation (stage-2, on demand after vocal flags)
    if "UVR-001" in force:
        seg = _loudest_segment(analysis, 45.0, duration)
        model = analysis.get("_uvr_model") or {
            "name": "standardized-at-generation-time",
            "version": "standardized-at-generation-time",
            "sha256": "standardized-at-generation-time",
        }
        cards.append(_card(
            "UVR-001",
            {"name": "Ultimate Vocal Remover 5", "module": "2-Stage Separation",
             "version": "由执行人记录"},
            seg,
            "分离人声/伴奏后，分别检查声部内异常（注意：分离伪迹 ≠ 生成痕迹）",
            "Inspect separated stems for within-stem anomalies (separation artifacts ≠ generation artifacts)",
            [
                f"1. 使用任务指定的模型：{model['name']} v{model['version']} (sha256 {model['sha256'][:16]}…)，"
                "任何偏离必须写进回传 deviations",
                f"2. 只对 {seg[0]:.1f}s – {seg[1]:.1f}s 片段做 2-stem（Vocals/Instrumental）分离",
                "3. 导出两个 stem 文件（保持原始采样率，不做任何后处理）",
                "4. 回传 stem 文件 + 模型设置截图；后续频谱/时序分析由引擎自动完成",
            ],
            {"vocal_stem": "文件", "instrumental_stem": "文件",
             "model_name": "字符串（必须与卡片一致）", "model_version": "字符串",
             "model_sha256": "模型文件 SHA-256（与卡片一致，偏离记录 deviations）",
             "settings_screenshot": "settings.png"},
            {"interpretation": "引擎对 stem 重跑 spectral/beatgrid；结果按双轨合并",
             "note": "分离伪迹 ≠ 生成痕迹；分离模型自身会引入伪迹，任何 stem 异常先与模型基线比对"},
            "声部级取证（全混音无法定位的疑点）",
            blinded=blinded, extra={"file_sha256": sha}))

    # Identity stamps AFTER all cards are built: instance ids distinguish
    # repeated rounds of the same task type on one file.
    from .submission import card_fingerprint
    for c in cards:
        c["task_instance_id"] = f"{c['task_id']}-{c['file_sha256'][:8]}"
        c["card_sha256"] = card_fingerprint(c)

    # Hypothesis-blinded operator views: attach AFTER identity stamps.
    if blinding_level == "hypothesis":
        for c in cards:
            c["operator_view"] = _operator_view(c)

    return cards
