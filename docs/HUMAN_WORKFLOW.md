# HUMAN_WORKFLOW — Human-in-the-Loop Forensic Protocol / 人工取证协作协议

Version 1.0. The AI (AkiForensics engine + session assistant) generates task cards; a human executes them in professional audio tools and returns structured results; the AI parses, compares, and merges evidence. 人工任务由 AI 发卡、真人执行、AI 解析合并。

## Protocol rules 协议规则

1. **Deterministic segments 确定性分段** — segment times are computed by the engine from detected features and written into the card ("analyze 94.20–104.20 s"). Never "pick a stable part". 分段由引擎按检出特征算出并写死，禁止"自己找一段"。
2. **Blinding by default 默认盲化** — a card never contains the engine's own numbers. The human records measurements **before** asking the AI anything. Comparison is done afterwards, dual-track. 卡内不含引擎测量值；回传前不得向 AI 询问预期值；事后双轨比对。
3. **Fixed settings 写死参数** — FFT size, window, model names, selection rules are in the card. Any deviation must be recorded in the return. 参数改动必须写进回传。
4. **Falsifiable acceptance 可证伪验收** — every card defines confirm / refute / undetermined **before** execution. `null` is a valid measurement. 验收标准先于执行确定；`null` 是合法测量值。
5. **Dual-track merge 双轨合并** — human records never overwrite engine records. Agreement raises confidence; contradiction spawns the next round. 人工记录永不覆盖引擎记录；矛盾触发下一轮。
6. **No originals modified 不动原件** — analysis is done on copies/reads only; repair modules (RX De-clip etc.) are observation-only, never applied to evidence. 只读分析；修复类模块仅作观察对照，永不作用于证据文件。

## Task lifecycle 任务生命周期

```
report.json.manual_tasks → AI 渲染操作单 → 真人执行 → 回传（数值表 + 截图）
→ AI 解析（数值优先，截图仅一致性目检且设置必须入镜）
→ 与引擎值比对 → 双轨入库 → 一致→置信提升 / 矛盾→发下一轮任务 → 更新判定
```

---

## RX-001 · High-frequency cutoff verification 高频截止验证

**Tool**: iZotope RX 12 — Spectrogram + Spectrum Analyzer · **Segment**: engine-computed 10 s window (codec-noise maximum), three equal sub-segments.

**Steps 步骤**（详见卡内 `steps_zh`，此处为协议备份）:
1. Open the ORIGINAL file（原始文件，禁用转码副本）, jump to `segment.start_s`.
2. Select exactly `start–end`; Spectrogram: **FFT 8192 / Hann**, screenshot with axes visible.
3. Spectrum Analyzer: average the whole segment **separately for L and R**; screenshot each, settings in frame.
4. Read the rolloff frequency in each of the three sub-segments; `null` if unreadable.
5. Record RX version.

**Record**: `cutoff_hz_left`, `cutoff_hz_right`, `wall_stable_across_subsegments`, `lr_consistent`, `above_wall_silence`, `rx_version`, screenshots.
**Accept**: wall stable ±200 Hz across sub-segments, L/R consistent → confirms lossy-source fingerprint. **Refute**: no wall, or sub-segment drift >500 Hz. **Undetermined**: unmeasurable edge.

## RX-002 · Kick waveform inspection 底鼓波形检查

**Tool**: RX 12 — Waveform + Spectrogram · **Segment**: 5 engine-picked beat timestamps (quintiles of the refined grid).

1. Jump to each of the 5 timestamps; capture ±100 ms waveform + spectrogram per kick, same zoom for all five.
2. Compare: identical waveform? sharp attack? same timbre?
3. Mark outliers (fills/variations) with timestamps.

**Record**: `kicks_identical`, `attack_sharp`, `outlier_timestamps`, screenshots ×5.
**Accept**: identical → sample reuse (NEUTRAL: DAW and sample-based generation both do this). **Refute**: mostly different → weak human-side hint (performance/synthesis variety).

## DAW-001 · Structured listening checklist 结构化听检清单

**Tool**: any DAW/player + headphones · **Segment**: full track, vocals re-checked.

Eight checks, all filled (no blanks): `VOCAL-ARTICULATION`（咬字含糊/粘连）· `VOCAL-DOUBLE`（相位化双重声）· `BREATH`（气口缺失/不自然）· `REVERB`（混响尾不一致）· `ARRANGEMENT`（配器/和声/衔接不合逻辑）· `ENDING`（收尾方式）· `STEREO`（声像跳变）· `OTHER`.
Each: `present yes/no/unsure` + `timestamp_s` + note. Record listening environment.

**Accept**: ≥2 vocal-related yes → listening suspicion stands, triggers UVR-001. **Refute**: all no / ≤1 non-vocal yes. Listening evidence is subjective and never decides provenance alone. 听检为主观证据，永不单独定来源。

## UVR-001 · Stem separation (stage-2, on demand) 分离取证

**Tool**: Ultimate Vocal Remover 5 · **Segment**: engine-computed 45 s excerpt only.
**Fixed model/settings**: use ONE model consistently, recorded by name and version in the return (v1 does not pin a specific model; the card names whatever was standardized at generation time — deviation must be recorded). 只对片段做 2-stem（Vocals/Instrumental）；导出保持原始采样率、零后处理；回传 stem 文件 + 模型名/设置截图。**后续频谱/时序分析由引擎自动重跑** — the human's job ends at operating the tool.
⚠️ Separation artifacts ≠ generation artifacts. Stem anomalies are first compared against the model's baseline behavior; residuals are separation error, not "AI evidence". 分离伪迹 ≠ 生成痕迹。

## PA-001 · Realtime mastering profile 实时画像（描述性）

**Tool**: Flux Pure Analyzer — Spectrum / Stereo / Loudness · **Segment**: engine-computed 60 s loudest window, played continuously.
Record: stereo correlation min/max, integrated LUFS, true peak dBTP, correlation stability, settings screenshot.
⚠️ Descriptive only — LUFS/TP/correlation are mastering characteristics, not AI-diagnostic features. 描述性画像，不参与来源判定。

---

## Agent-side ingestion rules AI 侧回传处理规则

1. Numbers first: parse the returned value sheet into the evidence object; screenshots are consistency witnesses (settings must be visible), never a substitute for numbers. 数值表是第一证据。
2. Compare dual-track: engine vs human. |Δ| within the card's tolerance → agreement (confidence ↑). Outside → contradiction: record BOTH, issue a targeted follow-up task (e.g. different segment, second tool). 双轨比对，矛盾不裁决、只加证。
3. Update `report.json` evidence, re-run `verdict.aggregate`, and only then present the next verdict to the user. 合并后再更新判定。
4. Never reveal engine expectations before the human's sheet is complete (blinding), unless the card was issued with `blinded: false`. 盲化卡在回传完成前不得泄露引擎预期值。
