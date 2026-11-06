# Evidence Model (evidence-model v2)

How measurements become verdicts. / 测量如何变成判定。

## 1 · Vocabulary 词汇表

Legs report **measurements**, never source attributions. Attribution happens only in `verdict.aggregate`, on top of positive findings.

各证据链只输出**测量陈述**，来源归因只发生在 `verdict.aggregate`，且只基于正向发现。

| Leg value | Meaning 语义 | Source-diagnostic? 可归因？ |
|---|---|---|
| `timing_locked` | Beat grid sample-locked (residual std ≤ 0.6 ms, ≥70% beats within ±0.3 ms) | Positive for a quantized DAW render (loops/samplers included) — **human-side positive** |
| `timing_variation` | Grid residuals ≥ 1.5 ms std, ≤30% within ±0.3 ms | Consistent with generative audio **OR** unquantized live playing — needs converging evidence |
| `no_anomaly_detected` | Full-band spectrum to Nyquist | **Not diagnostic** — true lossless masters and high-quality AI output are both full-band |
| `lossy_source_fingerprint` | Brick-wall cutoff inside a lossless container | Delivery-chain anomaly only; the transcode could originate from human OR AI masters |
| `anomalies_present` / `clean` | Metadata flags | Circumstantial |
| `na` | Leg not applicable (genre gate / lossy container) | — |

## 2 · Correlated evidence fuses as ONE vote 相关证据合票

Cutoff wall, codec noise bed, and metadata anomalies typically originate from a **single transcode event**. They corroborate one hypothesis; `verdict.aggregate` fuses spectral + metadata into a single `delivery_anomaly` vote. They are never summed as independent evidence.

截止墙、编码噪声底、元数据异常通常来自**同一次转码事件**——它们佐证同一假设。聚合器把 spectral + metadata 合成一票 `delivery_anomaly`，绝不按独立证据叠加。

## 3 · Verdict table 判定表

| Verdict | Requires 要求 |
|---|---|
| `STRONG_AI_EVIDENCE` | `timing_variation` **and** delivery-chain anomaly 收敛 |
| `LIKELY_AI` | `timing_variation` alone（音频内在证据，无交付链佐证） |
| `LIKELY_HUMAN` | `timing_locked` **and** no delivery anomaly（正向一致性，非证明） |
| `DELIVERY_CHAIN_ANOMALY` | Delivery anomaly without timing evidence — attribution withheld 归因保留 |
| `INCONCLUSIVE` | No positive evidence 无正向证据 |

Absence of anomalies is never positive evidence. 无异常永远不是正向证据。

## 4 · Human evidence (Task Cards) 人工证据

Human measurements enter as separate evidence objects — **dual-track**: engine values and human values are both recorded; neither overwrites the other. Agreement raises confidence; contradiction is itself new evidence and spawns the next task round.

人工测量以独立证据对象入库——**双轨制**：引擎值与人工值同时记录，互不覆盖。一致提升置信；矛盾本身就是新证据，触发下一轮任务。

Task cards follow protocol 1.0 (`src/akiforensics/tasks.py`): deterministic segments, blinding by default, falsifiable acceptance criteria. Full protocol: `docs/HUMAN_WORKFLOW.md`.

## 5 · Threshold provenance 阈值溯源

Every verdict carries `threshold_version` + disclaimer. `v0-n1` = one confirmed case + DAW physics; do not treat binary calls as ground truth until `calibrate` runs on a corpus.
