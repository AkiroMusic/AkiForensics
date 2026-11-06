# AkiForensics v0.3.0 — 2026-11-07

Adversarial review round 2 response: 3 confirmed P0 bugs fixed, verdict semantics
hardened (evidence-model v3), human-submission loop closed. Threshold provenance
`v0-n1.1` unchanged (single source of truth: config/thresholds.toml).

## P0 fixes (all reproduced before fixing)

- **metadata.py**: `_picture_info` double-`errors` decode TypeError (crash on any
  FLAC with a PICTURE block — never triggered by old fixtures, found by review);
  full bounds checks in `_picture_info` + `_parse_vorbis_comment`; PICTURE layout
  corrected to the FLAC spec (w/h/depth/colors + dataLen skip). Regression-tested
  with direct byte injection incl. hostile/truncated/absurd-length inputs.
- **tests**: corpus integration test asserted v1 labels (`ai_consistent`) —
  vacuously passing since v2. Rewritten for v3 with explicit `na` handling and
  mandatory alternative-disclosure assertion.
- **version drift**: disclaimer hard-coded `v0-n1` vs config `v0-n1.1`. The
  disclaimer is now generated from `cfg["meta"]["version"]`; docs reference the
  config as the single source of truth.

## Evidence-model v3 semantics

- `STRONG_AI_EVIDENCE` → `AI_EVIDENCE_CONVERGENT`; EVERY source-leaning verdict
  carries mandatory `alternative_hypotheses` (e.g. "unquantized live performance +
  lossy transcode of a human master"; `LIKELY_HUMAN` discloses "loop/sampler-based
  AI-hybrid production"). Convergent verdicts auto-issue the DAW-001 listening
  gate (alternative-hypothesis check).
- Metadata flags classified into families: integrity / packaging / provenance.
  Only spectral fingerprint + INTEGRITY flags feed the delivery-chain vote;
  packaging (cover MIME mismatch) and provenance (platform tags) are context only.
- `noise_bed_std_db` → `hf_band_level_variability_db` (it measures HF band level
  variation through time, not a codec noise floor).
- Spectral leg: Nyquist guard (low sample rates → `na` with reason, never
  "no anomaly").
- RX-001 acceptance de-attributed: confirms "a stable HF boundary exists"
  (transcode-compatible, not exclusive); RX-003 multi-resolution verification
  (2048/4096/8192) added to the protocol.

## Engineering

- `decode_work`: float32 working copies at NATIVE rate (24-bit sources no longer
  quantized to 16-bit), stereo preserved alongside the mono downmix for future
  stereo/mid-side forensics; `decode_pcm` annotation fixed.
- calibrate.py: spectral features (cutoff/cliff/hf_variability/wall-rate) now
  included in per-class stats; output framed as THRESHOLD PROPOSAL (never
  auto-applied).
- Human-submission loop closed: `submission.py` (validate against task card →
  dual-track comparison with per-task tolerances → attach evidence object; engine
  values never overwritten) + CLI `akiforensics merge-submission`.
- Blinding levels: `value` (default) / `hypothesis` (operator_view strips
  hypothesis, gap, and acceptance wording) / `none`; `analyze --blinding` flag.
- `analyze --task UVR-001 --task PA-001` for stage-2 cards.
- README/docs wording: evidence families (not "independent legs"), empirical
  ranges labeled with n, v3 vocabulary in test descriptions.

## Tests

46 tests (was 32): hostile-metadata byte injection, submission
validate/merge/agreement/contradiction/no-overwrite, blinding levels +
operator_view projection, packaging-flag-never-votes, dynamic-disclaimer,
two-step main-cluster regression, corpus integration (v3 labels).

## Declined (with reasons, see docs/reviews response)

- Full evidence-graph / task-store infrastructure (single-session loop;
  submission.py covers the six-stage return path minus state management).
- Stripping attribution entirely from verdicts (replaced by mandatory
  alternative-hypotheses disclosure — shrinking the explanation space IS the job).
