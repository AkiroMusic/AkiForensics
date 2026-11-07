# AkiForensics v0.3.2 — 2026-11-07

Adversarial review round 4 response: rendered-HTML blindness, task identity
lifecycle, evidence interpretation layer. Thresholds unchanged (v0-n1.1).

## P0 — true hypothesis-blinding (render layer + isolation)

- `_tasks_html` used the ANALYST record_fields even when showing the operator
  view (the R4 leak, found by review at runtime). Record schema now follows
  the shown view.
- **Two report files**: `analyst_report.html` (verdict, engine values, acceptance
  criteria) + `operator_tasks.html` (task/tool/segment/steps/record ONLY — no
  verdict, no engine numbers, no analyst wording). Operator file is safe to
  hand to the executor whole.
- selection_rule neutralized in operator views ("按统一规则选取——选择依据不向
  执行人公开"); blind steps now survey the FULL band (no 5–22 kHz hint).
- New test class exercises real `render_html` output: operator file must not
  contain the verdict (raw or spaced), engine cutoff value, analyst field
  names, or analyst acceptance wording; must contain the neutral rule.

## P0 — task identity lifecycle

- `card_fingerprint` excludes `card_sha256` itself (self-referential
  stability; was non-reproducible at merge time).
- `round_id` parameter: instance ids are now `R{round}-{task}-{sha8}` and
  DIFFER across rounds of the same file (was deterministic per file+task).
- Strict identity validation: submissions MUST carry matching
  `task_instance_id` AND `card_sha256`; missing or stale = rejected.
- CLI locates cards by instance id first, falls back to task_id.

## P1 — submission interpretation layer

- `comparison_strength` (authoritative / indicative / descriptive): RX-001
  mono-vs-per-channel checks are `indicative` and can only produce
  `agreement_indicative` / `contradiction_indicative` — never formal
  agreement/contradiction until per-channel spectral analysis ships.
- `reevaluate()` explicit entry point + per-task interpretation rules: merge
  produces an evidence interpretation and a re-evaluation RECOMMENDATION;
  the source verdict is never auto-flipped by a human return (the session AI
  applies card acceptance criteria across all evidence).
- merge-submission prints interpretation + verdict-before/after.

## P1 — UVR model registry

- `config/uvr_models.toml` (real values only — name/version/MODEL-FILE
  sha256/architecture). Cards without a valid entry are `model_unpinned` and
  separation forensics are BLOCKED (no placeholder identities — the v0.3.0/3.1
  doc/code desync is closed at the code level).
- Returns now require UVR5 version, segment size, overlap, output rate,
  post-processing (none) and both stem SHA-256s.

## P2 — verdict semantics

- `LIKELY_HUMAN` → `QUANTIZED_PRODUCTION_CONSISTENT` (the evidence is
  production-consistency for a quantized render, not authorship).
- `FILE_INTEGRITY_ANOMALY` split from `DELIVERY_CHAIN_ANOMALY` (metadata
  integrity issues may be corruption, not transcoding).
- `delivery_chain_fused: true` (always) replaced by three honest flags:
  `delivery_chain_detected` / `metadata_integrity_correlated` /
  `evidence_family_fusion_applied`; stale convergent wording fixed.
- Multichannel: native layout preserved + `channels_meta` (count/layout/
  downmix method) with >2ch marked EXPERIMENTAL (equal-mean downmix is not
  channel-aware; full multichannel DSP is future work).

## Corpus

`corpus/` skeleton adopted from review §十一 (human/ai/hybrid classes,
manifest schema, discipline rules: no cross-class transcodes, per-work
splits). Audio stays local; only manifests may ever be committed.

## Tests

65 (was 51): new `test_acceptance_r4.py` — rendered-HTML leakage (both
files), fingerprint self-stability, round-distinct instance ids, strict
identity rejection (missing/wrong round/wrong card), reevaluate
never-mutates, UVR unpinned blocking.

## Review loop

`AkiForensics-Response-R5.md` adjudicates round 4: 5/6 claims verified
(one check-string error on our side — the verdict WAS in the single HTML);
v0.3.2 acceptance target = the full loop defined by the reviewer.
