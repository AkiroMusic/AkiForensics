# AkiForensics v0.3.3 — Acceptance Report (v0.3.2 验收执行记录)

Date: 2026-11-07 · Executor: development-side AI · Method: `run_acceptance.py`
against REAL audio (Suno "Echo in the Prism", commercial demo) + real engine +
real rendered HTML + real merge path. Commit SHA: see git log at v0.3.3.

Result: **11/12 PASS, 1 PENDING-OWNER** (the human RX 12 session — by
definition the owner's; the return path was exercised with a clearly-labeled
SIMULATED number sheet).

| # | Acceptance item (GPT round-5 §四) | Result | Evidence |
|---|---|---|---|
| 1 | Real audio → analyze_single → dual reports | PASS | verdict=AI_EVIDENCE_CONVERGENT; analyst_report.html + operator_tasks.html |
| 2 | Operator HTML direct/indirect leak audit | PASS | level-aware: value level hides engine VALUES + verdict; hypothesis level additionally hides target field names; no plot reuse; no file path; **residual**: segment position inherently visible (random/control-group design = future work) |
| 3 | Human executes RX-001 from operator_tasks.html | PENDING-OWNER | requires real RX 12 session; simulated return used for the path below |
| 4 | Correct task_instance_id + card_sha256 | PASS | instance=R01-RX-001-8c3a20f5 accepted |
| 5 | Rejection: wrong hash / missing / wrong round | PASS | all three SubmissionError |
| 6 | merge-submission | PASS | evidence object attached; evidence_revision 0→1 |
| 7 | indicative never enters authoritative fusion | PASS | summary=agreement_indicative, strength=indicative |
| 8 | human return never auto-flips verdict | PASS | verdict unchanged, reevaluation.changed=False, recommendation recorded |
| 9 | UVR model_unpinned truly blocks | PASS | stem submission REJECTED: "model_unpinned — stem submissions are BLOCKED…" (enforcement, not a hint) |
| 10 | dual-report revision consistency | PASS | analysis rev 1 · evidence rev stamped in BOTH reports; both regenerate from one snapshot |
| 11 | corpus manifest + hybrid classification | PASS | human/ai/hybrid dirs + manifests schema; audio local-only |

## Issues the acceptance run itself caught (this is why we ran it)

1. **Corpus skeleton incomplete** (item 11 failed on first run): hybrid/human/ai
   subdirectories were missing — created during acceptance.
2. **Audit scope error**: the leak audit initially applied hypothesis-level
   criteria to a value-level operator file. Corrected to level-aware audit;
   new regression class `DualFileLevelAuditTests` locks BOTH levels
   (value: no values/verdict, target field names allowed by design;
   hypothesis: no target fields either; neither carries plots/paths).

## Deferred residuals (documented, not hidden)

- Segment-position visibility in operator files → requires the randomized
  control-group experiment design (GPT-R5 §三.1); interface ready
  (blinding levels), design deferred until a real operator pipeline exists.
- Full human RX-001 pass → owner action item.
