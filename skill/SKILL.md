---
name: akiforensics
description: Detect AI-generated (Suno-style) music from an audio file — forensic beat-grid timing, lossy-cutoff and metadata analysis plus human-in-the-loop task cards (RX12/UVR5/PureAnalyzer). Use when the user asks whether a track is AI-generated, wants to 打假/鉴别 AI 曲, or provides a song file for authenticity analysis.
---

# AkiForensics — AI-generated music forensics

Tool location: `E:\Code\Akiro Project\AkiForensics\` (engine in `src/akiforensics`, thresholds in `config/thresholds.toml`, protocols in `docs/`).

## Workflow

1. **Run the CLI** on the suspect file (package lives in `src`):

   ```bash
   cd "/e/Code/Akiro Project/AkiForensics" && PYTHONPATH=src python -m akiforensics analyze "<FILE>" --out <OUTDIR>
   ```

   Batch: pass a directory (per-file JSON + `summary.csv` + `index.html`; `--full` adds per-file HTML).

2. **Read `report.json`** and interpret:
   - Legs report MEASUREMENTS. `timing_variation` = variability present (generative OR unquantized live — do not attribute alone). `timing_locked` = positive for quantized DAW render. `no_anomaly_detected` = NOT source-diagnostic. `lossy_source_fingerprint` = delivery-chain anomaly only.
   - Top verdicts: STRONG_AI_EVIDENCE / LIKELY_AI / LIKELY_HUMAN / DELIVERY_CHAIN_ANOMALY / INCONCLUSIVE. Delivery-chain findings (spectral+metadata) are fused as ONE vote — never re-sum them.
   - Always present the numbers behind each leg; never a bare binary claim.

3. **Human-in-the-loop round (protocol 1.0)** — `report.json.manual_tasks` holds generated task cards (RX-001 cutoff verification, RX-002 kick inspection, DAW-001 listening checklist; stage-2 UVR-001/PA-001 on demand). For each card:
   - Render the card's `steps_zh` as the operating sheet for the user (Chinese steps, tool terms in English).
   - **Blinding**: cards default `blinded: true` — NEVER reveal engine expectations (cutoff Hz, residual ms) until the user's number sheet is complete. If asked, explain blinding first.
   - Receive results: parse the number sheet FIRST (screenshots are consistency witnesses only; settings must be visible in them). `null` is a valid measurement.
   - Compare dual-track vs engine values per the card's acceptance criteria; record BOTH values; agreement raises confidence, contradiction spawns a targeted follow-up (different segment / second tool) — never silently overwrite either side.
   - Stage-2: DAW-001 with ≥2 vocal flags → issue UVR-001 (`force=("UVR-001",)` via regenerate or read template from docs/HUMAN_WORKFLOW.md).

4. **Distribution leg (session-only)** — WebSearch artist + exact title: Spotify/Audiomack pages, ℗ label line, catalog pattern (many "(hot song)(电音版)" remixes = content-farm signature). Circumstantial; record as narrative.

5. **Report** — convergent grading only; state threshold provenance (v0-n1, single confirmed case) in every verdict; final call always includes a listening pass recommendation.

## Rules

- Ask for a local path; download URLs to a temp dir first if a URL is provided.
- No public accusations — reports are technical evidence for the user's own judgment.
- INCONCLUSIVE means say so plainly and name the missing evidence.
- Human tasks: never let the user modify the original file; RX repair modules are observation-only.
- Update `release/` and README (bilingual, EN-first) whenever engine, thresholds, or protocols change.
