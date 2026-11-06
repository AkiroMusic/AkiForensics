# AkiForensics v0.2.0 — 2026-11-07

Evidence-model v2 + Human-in-the-Loop task cards (protocol 1.0). Threshold provenance unchanged: `v0-n1` (single confirmed case).

## Evidence model v2 (breaking vocabulary change)

- Legs now report measurements, not attributions: `timing_locked` / `timing_variation` / `no_anomaly_detected` / `lossy_source_fingerprint` / `anomalies_present` / `clean` / `na`.
- **`no_anomaly_detected` no longer grades as human-consistent** — full-band spectrum is consistent with both true masters and high-quality AI output.
- Delivery-chain findings (spectral fingerprint + metadata anomalies) fuse as ONE correlated vote; never summed as independent evidence.
- New verdict `DELIVERY_CHAIN_ANOMALY`: delivery evidence without timing evidence → attribution withheld.
- `LIKELY_HUMAN` requires positive evidence everywhere (sample-locked grid + no anomaly + clean metadata).
- `LIKELY_AI` = timing variability as audio-intrinsic evidence, with explicit "consistent with unquantized live playing" caveat in the leg interpretation.

## Engine hardening

- `decode_work` keeps the NATIVE sample rate (no more unconditional 44.1 kHz resample manufacturing artifacts).
- metadata.py: streamed FLAC block parser with bounds checks (oversized/truncated block flags) replacing the fixed 4 MB read.
- report.py: HTML escaping on all file-controlled strings; new timing metrics in reports.
- beatgrid: new metrics — `local_bpm_drift`, `onset_confidence` (mean xcorr quality), `grid_hit_rate`, `beat_times`.

## Human-in-the-loop task cards (protocol 1.0)

- `tasks.py` generates verdict-moving task cards from analysis results: RX-001 cutoff verification, RX-002 kick waveform inspection, DAW-001 structured listening checklist; stage-2 UVR-001 stem separation and PA-001 Pure Analyzer profile on demand (`force=`).
- Deterministic segments (computed from detected features), fixed tool settings, falsifiable acceptance criteria (confirm/refute/undetermined).
- **Blinded by default**: cards never contain engine measurement values; comparison is dual-track after return (human records never overwrite engine records).
- Cards land in `report.json.manual_tasks`, the HTML report, the console summary, and batch CSV.
- Protocols: `docs/evidence-model.md`, `docs/HUMAN_WORKFLOW.md`; session loop protocol in `skill/SKILL.md`.

## Tests

29 tests: synthetic fixtures, new-vocabulary assertions, verdict table incl. "delivery-chain alone never attributes", task-card determinism/completeness/blinding/gap-targeting/stage-2, corpus-driven integration (`AKIFORENSICS_CASE_FILE`).

## Known limits

Unchanged (README §Known limits). Binary verdicts are not ground truth until corpus-calibrated.
