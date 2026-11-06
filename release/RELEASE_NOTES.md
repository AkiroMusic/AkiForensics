# AkiForensics v0.3.1 — 2026-11-07

Adversarial review round 3 response: all six main claims reproduced and fixed,
evidence-model v3.1 hardening. Thresholds unchanged (v0-n1.1).

## P0 (all reproduced before fixing)

- **report.json PCM leak**: `_stereo` working array was serialized into JSON
  (17.2 MB for a 10 s file). `_jsonable` now strips ALL underscore-prefixed
  runtime keys; new integration test asserts real engine output serializes
  without `_stereo`/`_plotdata` and under a 2 MB sanity cap.
- **LIKELY_HUMAN with spectral `na`**: lossy-container input could grade
  LIKELY_HUMAN with zero spectral information. Now requires MEASURED
  `no_anomaly_detected`; `na` ⇒ INCONCLUSIVE. Regression: MP3 + locked grid
  → INCONCLUSIVE.
- **FLAC MD5 all-zero field** (RFC 9639 §8.2): treated as unknown, never a
  mismatch; unit-tested via direct injection.

## Verdict hardening (v3.1)

- Convergence requires the SPECTRAL fingerprint: metadata INTEGRITY anomalies
  can raise a standalone DELIVERY_CHAIN_ANOMALY but never upgrade to
  AI_EVIDENCE_CONVERGENT (they may be corruption, not transcoding).
- Dedicated `alternative_hypotheses` for the timing-only branch (live
  performance / kick-detection error / genre applicability) — no longer
  reuses the convergent list.
- Every verdict carries `calibration_status: preliminary`,
  `human_reference_status: insufficient`, `probability_calibrated: false`.

## Engineering

- Native channel layout: `decode_work(channels=)` passed from probe — no
  `-ac 2` collapse of mono/multichannel sources.
- Full decode-error scan decoupled from SEEKTABLE presence.
- True hypothesis-blinded operator view: neutral full-band survey steps
  (`blind_steps_zh`) + generic record schema (`boundaries: [{freq_hz, note}]`)
  — field names like `cutoff_hz_left` no longer leak the target; HTML task
  table renders the operator view, never the analyst card; leakage asserted
  in tests.
- Submission identity: `task_instance_id` + `card_sha256` on cards, validated
  on merge (stale-card submissions rejected); value type validation;
  `comparison_basis` marks engine-mono vs per-channel human comparisons as
  indicative only; merge-submission now regenerates the HTML report.
- UVR-001: structured `model {name, version, sha256}` object on the card
  (was doc-only in v0.3.0 — caught by review).
- RX-003 redefined as Multi-Resolution MEASUREMENT ROBUSTNESS: FFT-size
  stability validates the boundary estimate, it does NOT discriminate codec
  cutoff vs human EQ (a real filter's cutoff does not move with FFT size
  either — the v0.3.0 claim was wrong).
- calibrate.py: brick-wall rate + median/P10/P90 for cutoff, cliff depth and
  HF variability per class; output explicitly framed as proposal-only.
- Corpus naming: "Suno Reference Set" (not a general AI-music set) across
  config/docs; three-version note (software / protocol 1.0 / thresholds).

## Bonus robustness fix

Pure-noise input (no kicks) crashed `_fit_grid` with an empty-vector polyfit
(two paths). Guarded; regression via full-flow walled-noise analysis
(beatgrid `na` + RX-001 card issued).

## Tests

51 tests (was 46): serialization-leak integration, MD5 zero guard,
LIKELY_HUMAN lossy-container block, integrity-never-upgrades-convergent,
operator-view leakage assertions (no `cutoff_hz` in operator blob, no analyst
wording in HTML), blinding levels with generic blind schema, card identity.

## Review loop

Full adjudication: `AkiForensics-Response-R4.md` (round-3 review: 6/6 claims
verified — strongest round so far; RX-003 methodology corrected on our side).
