# AkiForensics

**Forensic toolkit for detecting AI-generated music (Suno-style) from the audio file itself** — three evidence legs (beat-grid timing / lossy-cutoff fingerprint / metadata chain), graded verdicts, bilingual HTML reports. No listening required for a first pass.

**AI 生成音乐取证工具** —— 从音频文件本身鉴别 Suno 类生成式模型直出的曲子：三条证据链（节拍网格时序 / 有损截止指纹 / 元数据链），分级判定，双语 HTML 报告，首轮筛查无需试听。

> **Honesty note** · Thresholds `v0-n1` are calibrated on a single confirmed case. Verdicts are evidence-weighted, not ground truth. Run `calibrate` against a human/AI reference corpus before relying on binary calls.
>
> **诚实声明** · 阈值 `v0-n1` 基于单一确认案例校准。判定为证据加权结论，非 ground truth。在用 `calibrate` 跑过参考语料之前，不要把二值结论当真值用。

## How it works · 工作原理

Three independent evidence legs, graded and converged:

三条独立证据链，逐条分级后收敛：

| Leg | What it measures | Discriminative power |
|---|---|---|
| **A · Beat-grid timing** 时序 | Kick onsets vs best-fit constant-BPM grid; sub-ms residuals via cross-correlation. Quantized DAW render ⇒ residual std < 0.2–0.6 ms, ~100% within ±0.3 ms, round BPM. Generative models wander 2–40 ms with non-integer tempo. | **Decisive** (audio-intrinsic) |
| **B · Spectral fingerprint** 频谱 | Brick-wall cutoff + codec noise bed inside a nominally lossless container ⇒ lossy-source (fake lossless) fingerprint, e.g. LAME MP3 320's 20.5 kHz wall. | Delivery-chain evidence |
| **C · Metadata chain** 元数据 | FLAC block inventory, STREAMINFO MD5 integrity, cover MIME mismatches, platform farm tags (KuGou etc.), decoder errors. | Circumstantial |

Verdicts: `STRONG_AI_EVIDENCE` / `LIKELY_AI` / `LIKELY_AI_DELIVERY_ONLY` / `WEAK_AI_EVIDENCE` / `LIKELY_HUMAN` / `INCONCLUSIVE`. The timing leg is genre-gated: tracks without a steady kick grid report `N/A` for leg A instead of a guess.

判定等级：`STRONG_AI_EVIDENCE`（强 AI 特征）/ `LIKELY_AI`（倾向 AI）/ `LIKELY_AI_DELIVERY_ONLY`（仅交付链证据）/ `WEAK_AI_EVIDENCE`（弱证据）/ `LIKELY_HUMAN`（倾向人类）/ `INCONCLUSIVE`（证据不足）。时序链按曲风门控：无稳定底鼓网格的曲子 A 链报 `N/A`，不硬判。

## Requirements · 环境要求

- Python ≥ 3.11 with `numpy`, `scipy`, `matplotlib`
- `ffmpeg` / `ffprobe` on PATH

## Usage · 用法

```bash
# from repo root / 在仓库根目录
set PYTHONPATH=src          # Windows (bash: export PYTHONPATH=src)

# single file — console summary + JSON + HTML report in ./forensics_out/<stem>_report/
python -m akiforensics analyze "track.flac"

# batch — per-file JSON + summary.csv + index.html
python -m akiforensics analyze "D:\music\suspects" --out out
python -m akiforensics analyze "D:\music\suspects" --full   # + per-file HTML

# threshold suggestion from reference corpora (EXPERIMENTAL)
python -m akiforensics calibrate --human "D:\refs\human_daw" --ai "D:\refs\known_ai"

# custom thresholds
python -m akiforensics analyze track.flac --config config/thresholds.toml
```

## Tests · 测试

```bash
python run_tests.py -v
```

Synthetic fixtures prove each leg measures what it claims: a sample-locked 128 BPM kick grid grades `human_consistent` (std ≈ 0.1 ms); the same grid with ±3 ms jitter + slow wander grades `ai_consistent`; a 20.5 kHz brick wall inside FLAC grades `ai_consistent` (and `N/A` inside MP3). A corpus-driven integration test activates when you point it at a confirmed sample:

```bash
AKIFORENSICS_CASE_FILE="D:\refs\confirmed_ai\track.flac" python run_tests.py -v   # must not grade human-side
AKIFORENSICS_CASE_FILE="D:\refs\confirmed_human\track.flac" AKIFORENSICS_EXPECT=human python run_tests.py -v
```

合成 fixtures 验证每条链测的就是它声称的：采样级锁定 128 BPM 底鼓网格判 `human_consistent`（std ≈ 0.1 ms）；同网格加 ±3 ms 抖动+慢游移判 `ai_consistent`；FLAC 内 20.5 kHz 砖墙判 `ai_consistent`（MP3 内则正确报 `N/A`）。语料驱动的集成测试：把 `AKIFORENSICS_CASE_FILE` 指向任一已确认样本（文件名任意）即自动启用，断言引擎不作出反向判定（`AKIFORENSICS_EXPECT=human` 用于已确认人类样本）。

## Calibration status · 校准状态

- `v0-n1` (current): thresholds from one confirmed AI case (private reference sample, 2026-11-05) + DAW physics first principles. Human-side bounds are generous to avoid false accusations.
- Next: render a human reference set from your own DAW (quantized / unquantized, several tempi) and collect known AI output, then `calibrate` → bump threshold version.

- `v0-n1`（当前）：阈值来自单一已确认 AI 案例（私有参考样本，2026-11-05）+ DAW 物理第一性原理。人类侧阈值刻意放宽以避免冤枉真人作品。
- 下一步：用你自己的 DAW 渲染人类参考集（量化/不量化、多个速度），收集已知 AI 曲，跑 `calibrate` → 升级阈值版本号。

## Known limits · 已知局限

- Timing leg applies to steady-kick genres (EDM/pop/dance). Ballads, rock, orchestral ⇒ leg A `N/A`; verdict falls back to B+C evidence only.
- A lossy-cutoff wall alone does **not** prove AI — humans bounce through MP3 too. It is convergence evidence, not a verdict.
- Generative models improve; thresholds are versioned config, and every report carries its provenance.

- 时序链仅适用于稳定底鼓曲风（EDM/流行/舞曲）。抒情、摇滚、管弦 ⇒ A 链 `N/A`，判定退化为 B+C 证据。
- 有损截止墙本身不能证明 AI——人类也会走 MP3 母带。它是收敛证据，不是判决。
- 生成式模型在进化；阈值是带版本号的配置，每份报告都携带其校准来源。

## Repo layout · 目录结构

```
config/thresholds.toml    thresholds + provenance 阈值与校准来源
src/akiforensics/         engine: decode / metadata / spectral / beatgrid / verdict / report / cli / calibrate
tests/                    synthetic fixtures + unit + confirmed-case integration
skill/SKILL.md            ZCode skill wrapper (not registered globally; local to this repo)
release/                  packaged versions
run_tests.py              stdlib test runner
```
