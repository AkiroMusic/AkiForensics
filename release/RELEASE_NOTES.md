# AkiForensics v0.1.0 — 2026-11-06

First release. Threshold provenance `v0-n1` (single confirmed case).

## Engine

- **beatgrid**: 30–130 Hz kick isolation (SOS zero-phase) → RANSAC tempo/phase scan (60–200 BPM) → linear grid fit with outlier rejection → cross-correlated sub-ms refinement **cut at grid positions** (cutting at detected onsets cancels jitter — fixed during TDD) → residual statistics + wander shape + integer-BPM distance. Genre-gated: `N/A` without a steady kick grid.
- **spectral**: 8192-pt Hann spectrogram; brick-wall detection vs 14–20 kHz reference band; cutoff frequency, cliff depth, above-wall silence, codec noise-bed steadiness, band energy fractions. Full-band-to-Nyquist correctly reports no cutoff.
- **metadata**: FLAC block inventory, STREAMINFO MD5 integrity verify, PICTURE MIME-vs-magic check, KuGou tag fingerprinting, decoder error scan; MP3/WAV/M4A basic profile.
- **verdict**: per-leg grading + convergence into STRONG_AI_EVIDENCE / LIKELY_AI / LIKELY_AI_DELIVERY_ONLY / WEAK_AI_EVIDENCE / LIKELY_HUMAN / INCONCLUSIVE. Every output carries threshold provenance + disclaimer.
- **report**: single-file dark bilingual (EN/中文) HTML with embedded plots (kick residuals, high-band spectrogram, avg spectrum), JSON, ASCII console summary, batch CSV + index.
- **calibrate** (EXPERIMENTAL): reference-corpus ingestion → per-class metric distributions for threshold tuning.

## Tests

19 tests: synthetic fixtures (sample-locked vs jittered grids, brick-wall vs full-band noise, ffmpeg FLAC with/without KuGou tags), verdict aggregation table, and an auto-skipping integration test on the confirmed case (`AKIFORENSICS_CASE_FILE` env override supported).

## Known limits

See README §Known limits. Binary verdicts are not ground truth until calibrated against a corpus.
