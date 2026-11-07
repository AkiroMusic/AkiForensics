"""Report generation: dark bilingual HTML, JSON, console summary, batch index."""

from __future__ import annotations

import base64
import csv
import html as _html
import json
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def _jsonable(o):
    if isinstance(o, dict):
        # keys starting with "_" are runtime working data (arrays etc.),
        # never report content — _plotdata, _stereo, ...
        return {k: _jsonable(v) for k, v in o.items()
                if not (isinstance(k, str) and k.startswith("_"))}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return o


def write_json(result: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(result), ensure_ascii=False, indent=2),
                    encoding="utf-8")


def render_plots(result: dict, outdir: str | Path) -> dict[str, str]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    pd = result["spectral"].get("_plotdata") or {}
    if pd:
        f, avg_db = pd["freqs"], pd["avg_db"]
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(f[1:], avg_db[1:], lw=0.8)
        ax.set_xscale("log"); ax.set_xlim(20, 22050); ax.grid(alpha=0.3)
        ax.set_xlabel("Hz"); ax.set_ylabel("dB")
        co = result["spectral"].get("cutoff_hz")
        if co:
            ax.axvline(co, color="r", ls="--", lw=0.9, label=f"cutoff {co:.0f} Hz")
            ax.legend()
        fig.tight_layout(); fig.savefig(outdir / "avg_spectrum.png", dpi=120); plt.close(fig)
        paths["avg_spectrum"] = str(outdir / "avg_spectrum.png")

        spec_db, t = pd["spec_db"], pd["spec_t"]
        hb = (f >= 11000) & (f <= 22050)
        step = max(1, len(t) // 700)
        fig, ax = plt.subplots(figsize=(14, 5.5))
        mesh = ax.pcolormesh(t[::step], f[hb], spec_db[hb][::, ::step],
                             vmin=spec_db.max() - 75, vmax=spec_db.max(),
                             cmap="magma", shading="auto")
        ax.set_ylim(11000, 22050)
        if co:
            ax.axhline(co, color="c", ls="--", lw=1)
        fig.colorbar(mesh, ax=ax, label="dB")
        ax.set_xlabel("s"); ax.set_ylabel("Hz")
        fig.tight_layout(); fig.savefig(outdir / "spec_high.png", dpi=110); plt.close(fig)
        paths["spec_high"] = str(outdir / "spec_high.png")

    bp = result["beatgrid"].get("_plotdata") or {}
    if result["beatgrid"].get("applicable") and bp:
        k, res = np.asarray(bp["beat_index"]), np.asarray(bp["residual_ms"])
        fig, ax = plt.subplots(figsize=(13, 3.8))
        ax.plot(k, res, ".-", ms=4)
        for y in (0.3, -0.3, 2, -2):
            ax.axhline(y, color="g" if abs(y) < 1 else "orange", ls=":", lw=0.9)
        ax.set_xlabel("beat index"); ax.set_ylabel("residual (ms)")
        ax.set_title(f"Kick grid residuals: std={result['beatgrid']['residual_std_ms']} ms "
                     f"@ {result['beatgrid']['bpm']} BPM")
        ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(outdir / "kick_grid.png", dpi=120); plt.close(fig)
        paths["kick_grid"] = str(outdir / "kick_grid.png")
    return paths


def _img64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


_VERDICT_ZH = {
    "AI_EVIDENCE_CONVERGENT": "AI 证据收敛（时序变异 + 交付链异常；替代假设已列明，听检门已排队）",
    "LIKELY_AI": "倾向 AI 生成（音频内在时序证据；替代假设已列明）",
    "DELIVERY_CHAIN_ANOMALY": "仅交付链异常（无时序证据，不判来源）",
    "LIKELY_HUMAN": "倾向人类制作（制作一致性证据，非作者身份证明）",
    "INCONCLUSIVE": "证据不足，无法判定",
}
_LEG_ZH = {
    "timing_locked": "时序锁定（量化渲染的制作一致性证据）",
    "timing_variation": "时序变异（需归因）",
    "timing_inconclusive": "时序不确定",
    "lossy_source_fingerprint": "有损源指纹（交付链线索）",
    "no_anomaly_detected": "无异常（非来源诊断）",
    "integrity_anomalies": "完整性异常（integrity 族）",
    "clean": "干净", "na": "不适用", "inconclusive": "不确定",
}
_LEG_BAD = {"timing_variation", "lossy_source_fingerprint", "integrity_anomalies"}
_LEG_GOOD = {"timing_locked", "clean"}


def console_summary(result: dict) -> str:
    v = result["verdict"]
    lines = [
        "=" * 62,
        f"AKIFORENSICS  {result['file']['path']}",
        "=" * 62,
        f"VERDICT : {v['verdict']}   (thresholds {v['threshold_version']})",
        f"  basis : {v['positive_evidence']}",
        f"  legs  : beatgrid={v['legs']['beatgrid']['verdict']}"
        f"  spectral={v['legs']['spectral']['verdict']}"
        f"  metadata={v['legs']['metadata']['verdict']}",
    ]
    b = result["beatgrid"]
    if b.get("applicable"):
        lines += [
            f"  timing: bpm={b['bpm']}  residual_std={b['residual_std_ms']} ms"
            f"  <0.3ms={b['pct_within_0.3ms']}%  int_dist={b['bpm_integer_distance']}"
            f"  drift={b.get('local_bpm_drift')} BPM  conf={b.get('onset_confidence')}",
        ]
    else:
        lines.append(f"  timing: N/A ({b.get('reason')})")
    s = result["spectral"]
    lines.append(f"  spectral: cutoff={s.get('cutoff_hz')} Hz  brick_wall={s.get('brick_wall')}"
                 f"  hf_variability={s.get('hf_band_level_variability_db')} dB")
    m = result["metadata"]
    lines.append(f"  metadata: flags={m.get('flags') or 'none'}  integrity={m.get('flag_families', {}).get('integrity') or 'none'}")
    v0 = result["verdict"]
    for alt in v0.get("alternative_hypotheses", []):
        lines.append(f"  ALT   ▶ {alt}")
    for t in result.get("manual_tasks", []):
        lines.append(f"  TASK ▶ {t['task_id']} [{t['tool']['name']}] "
                     f"{t['segment']['start_s']}–{t['segment']['end_s']}s "
                     f"blinded={t['blinded']}  gap: {t['evidence_gap']}")
    lines.append(f"  NOTE  : {v['disclaimer']}")
    lines.append("=" * 62)
    return "\n".join(lines)


def _leg_badge(leg_v: str) -> str:
    cls = "bad" if leg_v in _LEG_BAD else ("good" if leg_v in _LEG_GOOD else "")
    zh = _LEG_ZH.get(leg_v, leg_v)
    return f"<span class='{cls}'>{_html.escape(leg_v)}</span><br><span class='zh'>{zh}</span>"


def _tasks_html(tasks_list: list[dict]) -> str:
    if not tasks_list:
        return ("<p class='zh'>本轮无待办人工任务（无足以改变判定的证据缺口）。</p>"
                "<p>No pending manual tasks this round (no verdict-moving evidence gaps).</p>")
    rows = ""
    for t in tasks_list:
        # hypothesis-blinded runs: the HTML operator table must show the
        # operator_view projection, never the full analyst card
        shown = t.get("operator_view") if "operator_view" in t else t
        hyp = shown.get("hypothesis_zh") or shown.get("instruction_zh", "")
        gap = shown.get("evidence_gap", "—")
        rec = "; ".join(f"<code>{_html.escape(k)}</code>: {_html.escape(str(v))}"
                        for k, v in shown.get("record_fields",
                                              t["record_fields"]).items())
        rows += f"""<tr><td><b>{_html.escape(t['task_id'])}</b><br>
<span class="zh">盲化 {"开" if t['blinded'] else "关"}</span></td>
<td>{_html.escape(t['tool']['name'])}<br><span class="zh">{_html.escape(t['tool']['module'])}</span></td>
<td>{t['segment']['start_s']} – {t['segment']['end_s']} s</td>
<td class="zh">{_html.escape(hyp)}</td>
<td class="zh">{_html.escape(gap)}</td>
<td>{rec}</td></tr>"""
    head = ("全步骤见 <code>docs/HUMAN_WORKFLOW.md</code>；执行后把数值表与截图回传给 AI 会话，"
            "按双轨合并规则入库（人工记录永不覆盖引擎测量）。<br>"
            "Full steps in <code>docs/HUMAN_WORKFLOW.md</code>; return the number sheet + "
            "screenshots to the AI session for dual-track evidence merging.")
    return f"<p class='zh'>{head}</p><table><tr><th>Task / 盲化</th><th>Tool 工具</th><th>Segment 分段 (s)</th><th>Hypothesis 假设</th><th>Evidence gap 证据缺口</th><th>Record 需回传</th></tr>{rows}</table>"


def render_html(result: dict, outdir: str | Path) -> str:
    outdir = Path(outdir)
    plots = render_plots(result, outdir)
    f = result["file"]; v = result["verdict"]
    b = result["beatgrid"]; s = result["spectral"]; m = result["metadata"]
    revision = (f"analysis rev {result.get('analysis_revision', 1)} · "
                f"evidence rev {result.get('evidence_revision', 0)}")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    esc_path = _html.escape(f["path"])
    esc_name = _html.escape(f["name"])
    verdict_en = v["verdict"].replace("_", " ")
    verdict_zh = _VERDICT_ZH.get(v["verdict"], v["verdict"])

    timing_rows = ""
    if b.get("applicable"):
        def row(en, zh, val):
            return f"<tr><td>{en}<br><span class='zh'>{zh}</span></td><td>{val}</td></tr>"
        timing_rows = (
            row("Tempo 速度", "", f"{b['bpm']} BPM (integer distance 距整数 {b['bpm_integer_distance']})") +
            row("Grid residual std 网格残差标准差", "", f"{b['residual_std_ms']} ms (max {b['residual_max_ms']})") +
            row("Beats within ±0.3 / ±1 / ±2 ms", "各容差内节拍占比", f"{b['pct_within_0.3ms']}% / {b['pct_within_1ms']}% / {b['pct_within_2ms']}%") +
            row("Refined beats / coverage", "精化节拍数 / 覆盖率", f"{b['n_beats_refined']} / {b['coverage']}") +
            row("8-beat wander range", "8 拍游移幅度", f"{b['wander_8beat_range_ms']} ms") +
            row("Local tempo drift (20s windows)", "局部速度漂移", f"{b.get('local_bpm_drift')} BPM") +
            row("Onset confidence (xcorr quality)", "onset 置信度（互相关质量均值）", f"{b.get('onset_confidence')}") +
            row("Grid hit rate", "网格命中率", f"{b.get('grid_hit_rate')}") +
            row("Interpretation 解读", "", f"<span class='zh'>{_html.escape(v['legs']['beatgrid'].get('interpretation_zh', ''))}</span><br>{_html.escape(v['legs']['beatgrid'].get('interpretation_en', ''))}") +
            "<tr><td>Reference (human DAW) 人工 DAW 参考</td><td>std &lt; 0.2–0.6 ms, ±0.3 ms ≈ 100%, round BPM</td></tr>"
            "<tr><td>Reference (generative AI) 生成式 AI 参考</td><td>std 2–40 ms, ±0.3 ms ≈ random, arbitrary BPM</td></tr>")
    else:
        timing_rows = f"<tr><td colspan='2'>N/A — {b.get('reason')}</td></tr>"

    spec_rows = (
        f"<tr><td>Cutoff 截止频率</td><td>{s.get('cutoff_hz')} Hz</td></tr>"
        f"<tr><td>Brick wall 砖墙</td><td>{s.get('brick_wall')} (cliff 悬崖 {s.get('cliff_depth_db')} dB, above-cutoff mean 墙上均值 {s.get('above_cutoff_mean_db')} dB)</td></tr>"
        f"<tr><td>HF band level variability 高频带能量波动 (非编码噪声底)</td><td>{s.get('hf_band_level_variability_db')} dB</td></tr>"
        f"<tr><td>Energy &gt;20.5 kHz 高频能量占比</td><td>{s['energy_fractions_pct'].get('pct_above_20.5k')}%</td></tr>")

    md_flags = ", ".join(_html.escape(str(x)) for x in (m.get("flags") or [])) or "none 无"
    integrity = ", ".join(m.get("flag_families", {}).get("integrity") or []) or "none"
    alts = "<br>".join("· " + _html.escape(a) for a in v.get("alternative_hypotheses", []))
    fp = m.get("platform_fingerprint") or []
    fp_rows = "".join(
        f"<tr><td>{_html.escape(p['platform'])}: {', '.join(_html.escape(str(x)) for x in p['fields'])}</td></tr>"
        for p in fp) or "<tr><td>none 无</td></tr>"

    imgs = ""
    if "kick_grid" in plots:
        imgs += f"<figure><img src='data:image/png;base64,{_img64(plots['kick_grid'])}'><figcaption>EN · Kick onsets vs best-fit constant-BPM grid.<br><span class='zh'>中文 · 底鼓 onset 与最优恒定 BPM 网格的残差。</span></figcaption></figure>"
    if "spec_high" in plots:
        imgs += f"<figure><img src='data:image/png;base64,{_img64(plots['spec_high'])}'><figcaption>EN · High-band spectrogram 11–22 kHz with detected cutoff.<br><span class='zh'>中文 · 高频段频谱图 11–22 kHz，红线为检测截止。</span></figcaption></figure>"
    if "avg_spectrum" in plots:
        imgs += f"<figure><img src='data:image/png;base64,{_img64(plots['avg_spectrum'])}'><figcaption>EN · Long-term average spectrum.<br><span class='zh'>中文 · 全曲平均频谱。</span></figcaption></figure>"

    tasks_html = _tasks_html(result.get("manual_tasks", []))
    basis = _html.escape(v["positive_evidence"])

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>AkiForensics — {esc_name}</title><style>
:root{{--bg:#0d1117;--page:#151b23;--text:#d9e1ea;--muted:#8a97a6;--accent:#6cb2ff;--border:#2a3441;--thead:#1c242e;--rowalt:#181f28;--zh:#b9c6d4;}}
body{{font-family:"Segoe UI",system-ui,"Microsoft YaHei",sans-serif;margin:0;background:var(--bg);color:var(--text);line-height:1.7}}
.page{{max-width:900px;margin:0 auto;background:var(--page);padding:40px 52px}}
h1{{font-size:1.5em;border-bottom:3px solid var(--accent);padding-bottom:.3em}}
h2{{font-size:1.15em;color:var(--accent);border-bottom:1px solid var(--border);padding-bottom:.25em;margin-top:2em}}
.meta{{color:var(--muted);font-size:.9em}}
.verdict{{background:#10161f;border:1px solid #3b82c4;border-radius:10px;padding:18px 22px;margin:1.2em 0}}
.verdict .big{{font-size:1.25em;font-weight:700;color:#8ec7ff}}
.zh{{color:var(--zh)}}
table{{border-collapse:collapse;width:100%;margin:1em 0;font-size:.9em}}
th,td{{border:1px solid var(--border);padding:6px 10px;text-align:left;vertical-align:top}}
th{{background:var(--thead);color:#a8c7e8}} tr:nth-child(even) td{{background:var(--rowalt)}}
.good{{color:#5fd08a;font-weight:600}}.bad{{color:#ff7b72;font-weight:600}}
figure{{margin:1.3em 0;text-align:center}}figure img{{max-width:100%;border:1px solid var(--border);border-radius:6px}}
figcaption{{font-size:.84em;color:var(--muted);margin-top:.5em;text-align:left}}
.warn{{background:#241d12;border-left:4px solid #d9a436;padding:10px 14px;font-size:.9em}}
code{{background:#212a35;padding:1px 5px;border-radius:3px;font-size:.88em}}
footer{{margin-top:2.5em;font-size:.82em;color:var(--muted);border-top:1px solid var(--border);padding-top:1em}}
</style></head><body><div class="page">
<h1>AkiForensics Report<br><span class="zh" style="font-size:.7em">AI 曲取证报告</span></h1>
<div class="meta">File 文件: <code>{esc_path}</code><br>Generated 生成: {now} · thresholds 阈值 {v['threshold_version']} · evidence-model v2 · {revision}</div>
<div class="verdict"><div class="big">{verdict_en}</div>
<div class="big zh">{verdict_zh}</div>
<div class="meta" style="margin-top:.6em">Positive basis 正向依据: {basis}<br>
Alternatives standing 替代假设: {alts if alts else "none（当前证据组合下无已建模替代解释）"}<br>
legs 证据链: beatgrid 时序={_LEG_ZH.get(v['legs']['beatgrid']['verdict'], '')} · spectral 频谱={_LEG_ZH.get(v['legs']['spectral']['verdict'], '')} · metadata 元数据={_LEG_ZH.get(v['legs']['metadata']['verdict'], '')}</div></div>
<div class="warn">{v['disclaimer']}<br><span class="zh">阈值 v0-n1：基于单一确认案例校准。判定为证据加权结论，非 ground truth。无异常 ≠ 人类特征。</span></div>
<h2>1 · Timing forensics 时序取证 <span style="color:#8a97a6;font-size:.85em">(measurement 时序测量，来源归因见解读行)</span></h2>
<table><tr><th>Metric 指标</th><th>Value 值</th></tr>{timing_rows}</table>
<h2>2 · Spectral forensics 频谱取证 <span style="color:#8a97a6;font-size:.85em">(delivery chain 交付链)</span></h2>
<table><tr><th>Metric 指标</th><th>Value 值</th></tr>{spec_rows}</table>
<h2>3 · Metadata forensics 元数据取证</h2>
<table><tr><th>Flags 标记</th></tr><tr><td>{md_flags}</td></tr></table>
<table><tr><th>Integrity family 参与交付链投票的 integrity 族</th></tr><tr><td>{integrity}</td></tr></table>
<table><tr><th>Platform fingerprint 平台指纹</th></tr>{fp_rows}</table>
<p>Vendor 编码器: <code>{_html.escape(str(m.get('vendor') or 'n/a'))}</code> · Container 容器: <code>{_html.escape(str(m.get('container')))}</code> · {m.get('sample_rate')} Hz / {m.get('channels')} ch</p>
<h2>4 · Manual verification queue 待办人工验证</h2>
{tasks_html}
<h2>5 · Plots 图证</h2>
{imgs}
<h2>6 · Method 方法</h2>
<p>EN · Timing: 30–130 Hz kick isolation, RANSAC tempo/phase scan, linear grid fit, grid-position cross-correlated sub-ms refinement. Spectral: 8192-pt Hann spectrogram, brick-wall cliff detection vs 14–20 kHz reference band. Metadata: streamed FLAC block inventory + STREAMINFO MD5 verify + tag fingerprints. Delivery-chain findings are fused as one correlated vote, never summed.</p>
<p class="zh">中文 · 时序：30–130 Hz 底鼓分离、RANSAC 速度/相位扫描、线性网格拟合、网格位置互相关亚毫秒精化。频谱：8192 点 Hann 频谱图、以 14–20 kHz 参考频带做砖墙悬崖检测。元数据：流式 FLAC 块清单 + STREAMINFO MD5 校验 + 平台 tag 指纹。交付链发现按相关性合票，不叠加计分。</p>
<footer>AkiForensics v0.3.3 · evidence report only; final judgment (incl. listening check) belongs to the recipient. 仅陈述技术证据；最终判定（含试听）由使用者作出。</footer>
</div></body></html>"""
    out = outdir / "analyst_report.html"
    out.write_text(html, encoding="utf-8")
    # Operator file: task sheets ONLY — no verdict, no engine measurements,
    # no analyst hypothesis/gap/acceptance wording.
    ops_rows = ""
    for t in result.get("manual_tasks", []):
        shown = t.get("operator_view") if "operator_view" in t else t
        steps = "<br>".join(_html.escape(x) for x in shown.get("steps_zh", []))
        rec = "<br>".join(f"<code>{_html.escape(k)}</code>: {_html.escape(str(v))}"
                          for k, v in shown.get("record_fields", {}).items())
        sel = shown.get("segment", {}).get("selection_rule", "")
        sel_html = (f"<br><span class='zh'>{_html.escape(sel)}</span>" if sel else "")
        ops_rows += f"""<tr><td><b>{_html.escape(t['task_id'])}</b></td>
<td>{_html.escape(t['tool']['name'])}<br><span class="zh">{_html.escape(t['tool']['module'])}</span></td>
<td>{t['segment']['start_s']} – {t['segment']['end_s']} s{sel_html}</td>
<td>{steps}</td><td>{rec}</td></tr>"""
    ops_head = ("请按步骤独立完成测量并如实记录；不要向 AI 询问任何预期值，也不要根据既往分析"
                "推测目标结果。回传数值表与截图（设置必须入镜）。<br>"
                "Complete the measurements independently and return the number sheet "
                "+ screenshots (settings in frame).")
    ops_html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>AkiForensics — Operator Tasks 操作任务单</title><style>
body{{font-family:"Segoe UI","Microsoft YaHei",sans-serif;background:#0d1117;color:#d9e1ea;line-height:1.7}}
.page{{max-width:900px;margin:0 auto;background:#151b23;padding:40px 52px}}
h1{{font-size:1.4em;border-bottom:3px solid var(--accent,#6cb2ff);padding-bottom:.3em}}
table{{border-collapse:collapse;width:100%;margin:1em 0;font-size:.9em}}
th,td{{border:1px solid #2a3441;padding:6px 10px;text-align:left;vertical-align:top}}
th{{background:#1c242e;color:#a8c7e8}}tr:nth-child(even) td{{background:#181f28}}
code{{background:#212a35;padding:1px 5px;border-radius:3px;font-size:.88em}}
.zh{{color:#b9c6d4}}</style></head><body><div class="page">
<h1>Operator Tasks 操作任务单</h1>
<p class="zh">{ops_head}</p>
<table><tr><th>Task 任务</th><th>Tool 工具</th><th>Segment 分段 (s)</th><th>Steps 步骤</th><th>Record 记录</th></tr>{ops_rows}</table>
<footer>AkiForensics operator sheet · 本文件不含分析结论，可整份交给执行人。 · {revision}</footer>
</div></body></html>"""
    (outdir / "operator_tasks.html").write_text(ops_html, encoding="utf-8")
    return str(out)


AUDIO_EXTS = {".flac", ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma"}


def write_batch_summary(results: list[dict], outdir: str | Path) -> str:
    outdir = Path(outdir)
    csv_path = outdir / "summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fcsv:
        w = csv.writer(fcsv)
        w.writerow(["file", "verdict", "beatgrid", "bpm", "residual_std_ms",
                    "pct_0.3ms", "spectral", "cutoff_hz", "brick_wall",
                    "metadata", "flags", "manual_tasks"])
        for r in results:
            v = r["verdict"]["legs"]
            b = r["beatgrid"]
            w.writerow([r["file"]["name"], r["verdict"]["verdict"],
                        v["beatgrid"]["verdict"], b.get("bpm"),
                        b.get("residual_std_ms"), b.get("pct_within_0.3ms"),
                        v["spectral"]["verdict"], r["spectral"].get("cutoff_hz"),
                        r["spectral"].get("brick_wall"),
                        v["metadata"]["verdict"],
                        ";".join(r["metadata"].get("flags") or []),
                        ";".join(t["task_id"] for t in r.get("manual_tasks", []))])
    rows = ""
    for r in results:
        vd = r["verdict"]["verdict"]
        cls = "bad" if "AI" in vd else ("good" if vd == "LIKELY_HUMAN" else "")
        rows += (f"<tr><td>{_html.escape(r['file']['name'])}</td>"
                 f"<td class='{cls}'>{_html.escape(vd)}<br><span class='zh'>{_VERDICT_ZH.get(vd, '')}</span></td>"
                 f"<td>{_html.escape(r['verdict']['legs']['beatgrid']['verdict'])}</td>"
                 f"<td>{r['beatgrid'].get('residual_std_ms') or '—'}</td>"
                 f"<td>{r['spectral'].get('cutoff_hz') or '—'}</td>"
                 f"<td>{_html.escape(', '.join(r['metadata'].get('flags') or []) or '—')}</td>"
                 f"<td>{', '.join(t['task_id'] for t in r.get('manual_tasks', [])) or '—'}</td></tr>")
    idx = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>AkiForensics batch</title>
<style>body{{font-family:"Segoe UI","Microsoft YaHei",sans-serif;background:#0d1117;color:#d9e1ea}}
.page{{max-width:1080px;margin:0 auto;background:#151b23;padding:32px}}
h1{{color:#6cb2ff}}table{{border-collapse:collapse;width:100%;font-size:.9em}}
th,td{{border:1px solid #2a3441;padding:6px 10px;text-align:left}}
th{{background:#1c242e;color:#a8c7e8}}tr:nth-child(even) td{{background:#181f28}}
.good{{color:#5fd08a;font-weight:600}}.bad{{color:#ff7b72;font-weight:600}}.zh{{color:#b9c6d4}}</style></head>
<body><div class="page"><h1>AkiForensics — Batch Summary 批量汇总</h1>
<table><tr><th>File 文件</th><th>Verdict 判定</th><th>Timing 时序</th><th>Residual ms</th><th>Cutoff Hz</th><th>Flags</th><th>Tasks 任务</th></tr>{rows}</table>
<p class="zh">阈值 {results[0]['verdict']['threshold_version']}（单一案例校准），判定为证据加权结论；交付链发现已合票。</p></div></body></html>"""
    (outdir / "index.html").write_text(idx, encoding="utf-8")
    return str(csv_path)
