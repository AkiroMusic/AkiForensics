# Evidence Model (evidence-model v3)

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

| Verdict | Requires 要求 | Standing alternatives 必列替代假设 |
|---|---|---|
| `AI_EVIDENCE_CONVERGENT` | `timing_variation` **and** delivery-chain anomaly 收敛；auto-issues the listening gate 自动签发听检门 | unquantized live performance + lossy transcode of a human master |
| `LIKELY_AI` | `timing_variation` alone（音频内在证据，无交付链佐证） | same as above |
| `LIKELY_HUMAN` | `timing_locked` **and** spectral `no_anomaly_detected` (MEASURED, not `na`) **and** clean metadata 制作一致性而非作者身份；lossy 容器下 spectral 为 `na` ⇒ 证据不全，不进入此判定 | loop/sampler-based AI-hybrid production |
| `DELIVERY_CHAIN_ANOMALY` | Delivery anomaly without timing evidence — attribution withheld 归因保留 | n/a (no attribution made) |
| `INCONCLUSIVE` | No positive evidence 无正向证据 | n/a |

Source-leaning verdicts MUST carry `alternative_hypotheses`（来源倾向判定必须披露剩余解释）. Absence of anomalies is never positive evidence. 无异常永远不是正向证据。

## 4 · Human evidence (Task Cards) 人工证据

Human measurements enter as separate evidence objects — **dual-track**: engine values and human values are both recorded; neither overwrites the other. Agreement raises confidence; contradiction is itself new evidence and spawns the next task round. Return path: `submission.py` + `akiforensics merge-submission` (validate → compare → attach; verdict reinterpretation per card acceptance criteria in-session).

人工测量以独立证据对象入库——**双轨制**：引擎值与人工值同时记录，互不覆盖。一致提升置信；矛盾本身就是新证据，触发下一轮任务。回传闭环：`submission.py` + CLI `merge-submission`。

Blinding levels 盲化分级: `value`（默认——卡含假设不含引擎值）/ `hypothesis`（operator_view 剥离假设，测量者不知系统怀疑什么）/ `none`（对照模式）。Research-grade runs should prefer `hypothesis`. Task cards follow protocol 1.0 (`src/akiforensics/tasks.py`); full protocol: `docs/HUMAN_WORKFLOW.md`.

## 5 · Threshold provenance 阈值溯源

Every verdict carries `threshold_version` (read from `config/thresholds.toml [meta].version` — the single source of truth) + a dynamic disclaimer. Current calibration state is documented in the config header. 判定携带从配置动态读取的阈值版本；校准状态以配置头注释为准。
