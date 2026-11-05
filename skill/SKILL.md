---
name: akiforensics
description: Detect AI-generated (Suno-style) music from an audio file — forensic beat-grid timing, lossy-cutoff and metadata analysis with evidence-based verdicts. Use when the user asks whether a track is AI-generated, wants to 打假/鉴别 AI 曲, or provides a song file for authenticity analysis.
---

# AkiForensics — AI-generated music forensics

Tool location: `E:\Code\Akiro Project\AkiForensics\` (package in `src/akiforensics`, thresholds in `config/thresholds.toml`).

## Workflow

1. **Run the CLI** on the suspect file (quote paths; the package lives in `src`):

   ```bash
   cd "/e/Code/Akiro Project/AkiForensics" && PYTHONPATH=src python -m akiforensics analyze "<FILE>" --out <OUTDIR>
   ```

   Batch: pass a directory. For a directory, per-file JSON + `summary.csv` + `index.html` are produced; add `--full` for per-file HTML reports.

2. **Read `report.json`** from the output dir and interpret the three legs:
   - `beatgrid` — decisive. `ai_consistent` requires residual_std ≥ 1.5 ms AND pct<0.3ms ≤ 30%. `human_consistent` requires std ≤ 0.6 ms AND pct ≥ 70%. `na` = no steady kick grid (non-EDM) — do NOT improvise timing claims.
   - `spectral` — brick-wall cutoff inside FLAC/WAV = lossy-source (fake lossless). `na` for already-lossy containers.
   - `metadata` — flags (`picture_mime_mismatch`, `md5_mismatch`, `decoder_errors`), platform fingerprints (KuGou), vendor.

3. **Add the distribution leg (C extended)** — only possible inside this session, not via CLI:
   - WebSearch the artist + exact track title: Spotify/Audiomack/QQ音乐 pages, release label (℗ line), catalog pattern (many "(hot song)(电音版)" remixes = content-farm signature), monthly listeners.
   - This leg is circumstantial; record it as narrative evidence in the final answer.

4. **Report** — convergent grading only:
   - beatgrid ai + (spectral ai OR metadata suspicious) → STRONG_AI_EVIDENCE
   - beatgrid ai alone → LIKELY_AI
   - Never output a binary "is/is not AI" — output the verdict grade + the numbers behind each leg.
   - Always state: thresholds v0-n1 calibrated on a single confirmed case; final confirmation should include a human listening pass (vocal texture) and, where possible, a DAW/producer claim check.

## Rules

- If the file is not locally accessible, ask for the path; do not analyze URLs directly (download to a temp dir first if the user provides one).
- Do not accuse anyone publicly; the report is technical evidence for the user's own judgment.
- If `verdict` is INCONCLUSIVE, say so plainly and list what evidence is missing.
- Update `release/` and README (bilingual, EN-first) whenever thresholds or engine change.
