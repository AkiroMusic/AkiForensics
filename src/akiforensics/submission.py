"""Human submission ingestion — the return path of protocol 1.0.

Closes the loop: a returned number sheet (JSON, per the card's record_fields)
is validated against its task card, compared dual-track against the engine's
stored measurement, and merged into the analysis as a human evidence object.
Neither side ever overwrites the other; agreement raises confidence,
contradiction is recorded as new evidence.

Expected submission shape:
{
  "task_id": "RX-001",
  "file_sha256": "...",                     # must match the analysis
  "values": {"cutoff_hz_left": 20120, ...}, # keys per card record_fields
  "screenshots": ["spectrum_L.png"],        # optional paths
  "operator_notes": "free text",
  "deviations": "any deviations from card steps, or empty"
}
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

# Numeric comparison tolerances per task (card acceptance criteria in ms/Hz).
TOLERANCES = {
    "RX-001": {"cutoff_hz_left": 200.0, "cutoff_hz_right": 200.0},
}


class SubmissionError(ValueError):
    pass


def _require(cond: bool, msg: str):
    if not cond:
        raise SubmissionError(msg)


def card_fingerprint(card: dict) -> str:
    """Stable hash of the card content. Excludes operator_view AND the
    card_sha256 field itself, so fingerprint(card) == fingerprint(stored_card)
    at merge time (self-referential stability)."""
    excluded = {"operator_view", "card_sha256"}
    payload = {k: v for k, v in card.items() if k not in excluded}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def validate(submission: dict, card: dict) -> None:
    """Structural validation against the task card."""
    _require(isinstance(submission, dict), "submission must be a JSON object")
    if card.get("model_unpinned"):
        raise SubmissionError(
            "model_unpinned — stem submissions are BLOCKED until a real model "
            "is registered in config/uvr_models.toml (enforcement, not a hint)")
    _require(submission.get("task_id") == card["task_id"],
             f"task_id mismatch: submission={submission.get('task_id')} "
             f"card={card['task_id']}")
    _require(submission.get("file_sha256") == card.get("file_sha256"),
             "file_sha256 does not match the analyzed file — wrong file returned?")
    _require(submission.get("task_instance_id") == card.get("task_instance_id"),
             "task_instance_id mismatch — submission does not answer THIS card "
             "instance (wrong round or wrong file)")
    _require(submission.get("card_sha256") == card.get("card_sha256"),
             "card_sha256 mismatch — submission answers a DIFFERENT card version "
             "(protocol/segment changed between rounds)")
    values = submission.get("values")
    _require(isinstance(values, dict), "missing 'values' object")
    expected = card.get("record_fields", {})
    if card.get("operator_view"):
        # hypothesis-blinded card: the operator filled the GENERIC schema
        expected = card["operator_view"].get("record_fields", expected)
    for k in expected:
        if k == "screenshots":
            continue
        _require(k in values, f"missing record field '{k}' (null is a valid value)")
    for k, v in values.items():
        _require(v is None or isinstance(v, (str, int, float, list)),
                 f"record field '{k}': unsupported type {type(v).__name__} "
                 "(allowed: string / number / boolean-free list / null)")


def _compare_numeric(engine_val: float, human_val: float, tol: float) -> str:
    if engine_val is None or human_val is None:
        return "not_comparable"
    return "agreement" if abs(engine_val - human_val) <= tol else "contradiction"


def merge(submission: dict, analysis: dict, card: dict) -> dict:
    """Validate, compare dual-track, and attach the human evidence object.

    Returns a NEW analysis dict with 'human_evidence' attached. Does not
    mutate the input. Verdict recalculation is the caller's job (it needs
    the fused interpretation rules per task — v0.3 keeps human evidence as
    an attached, versioned record; the session AI applies the card's
    acceptance criteria and re-issues tasks on contradiction).
    """
    validate(submission, card)
    values = submission["values"]
    engine_card = next((t for t in analysis.get("manual_tasks", [])
                        if t["task_id"] == card["task_id"]), card)
    comparisons = []
    hypothesis_returned = card.get("operator_view") is not None
    for k, human_v in list(values.items()):
        if k == "screenshots" or not isinstance(human_v, (int, float)) or isinstance(human_v, bool):
            continue
        if hypothesis_returned:
            # hypothesis-blinded returns use generic field names: no
            # mechanical name-matched comparison exists — the session AI
            # applies the card's acceptance criteria to the returned
            # boundary list instead.
            continue
        if k == "screenshots" or not isinstance(human_v, (int, float)) or \
                isinstance(human_v, bool):
            continue
        eng_v = None
        if k == "cutoff_hz_left" or k == "cutoff_hz_right":
            eng_v = analysis.get("spectral", {}).get("cutoff_hz")
        tol = TOLERANCES.get(card["task_id"], {}).get(k)
        comparisons.append({
            "field": k, "engine": eng_v, "human": human_v,
            "tolerance": tol,
            "comparison_basis": ("engine mono-downmix cutoff vs per-channel human "
                                 "measurement — indicative only until per-channel "
                                 "spectral analysis ships") if eng_v is not None else None,
            "result": _compare_numeric(eng_v, human_v, tol) if tol else "recorded",
        })

    # comparison strength: RX-001 numeric checks are indicative until
    # per-channel spectral analysis ships; only authoritative comparisons
    # may drive formal agreement/contradiction summaries.
    STRENGTH = {"RX-001": "indicative"}
    strength = STRENGTH.get(card["task_id"], "indicative")

    evidence = {
        "task_id": card["task_id"],
        "task_instance_id": card.get("task_instance_id", card["task_id"]),
        "card_sha256": card_fingerprint(card),
        "comparison_strength": strength,
        "source": {"type": "human_tool", "tool": card["tool"]["name"]},
        "values": values,
        "screenshots": submission.get("screenshots", []),
        "operator_notes": submission.get("operator_notes", ""),
        "deviations": submission.get("deviations", ""),
        "blinded": card.get("blinded", True),
        "comparisons": comparisons,
        "summary": ("agreement" if comparisons and strength == "authoritative"
                    and all(c["result"] == "agreement" for c in comparisons) else
                    "contradiction" if strength == "authoritative"
                    and any(c["result"] == "contradiction" for c in comparisons) else
                    "agreement_indicative" if comparisons
                    and all(c["result"] == "agreement" for c in comparisons) else
                    "contradiction_indicative" if any(c["result"] == "contradiction"
                                                      for c in comparisons) else
                    "recorded"),
    }
    out = dict(analysis)
    out.pop("_stereo", None)  # working arrays never enter persisted evidence
    out["human_evidence"] = out.get("human_evidence", []) + [evidence]
    # evidence_revision advances on every accepted human return; both reports
    # are regenerated from this same snapshot (version consistency).
    out["evidence_revision"] = int(analysis.get("evidence_revision") or 0) + 1
    out["verdict_reevaluation"] = reevaluate(evidence, out)
    return out


def load_submission(path: str | Path) -> dict:
    with open(path, "rb") as f:
        sub = json.load(f)
    _require(isinstance(sub, dict), "submission file must contain a JSON object")
    return sub

# Per-task interpretation rules: what a human return MEANS for the case.
# The session AI applies card acceptance criteria to these interpretations —
# the source verdict is never auto-flipped by a human return.
_INTERPRETATIONS = {
    "RX-001": {
        "agreement_indicative": "人工分声道测量与引擎 mono 截止一致（指示性）：有损源"
                                "指纹方向获得独立方法学佐证，置信提升一档",
        "contradiction_indicative": "人工测量与引擎不一致：两值均保留，需换段/换工具"
                                    "复核（矛盾不裁决，只加证）",
        "recorded": "人工边界清单已入库（全盲模式：与引擎 mono 截止的对照由会话 AI "
                    "按卡面验收标准执行，结论指示性）",
    },
    "RX-002": {"recorded": "kick 波形一致性作为制作方式辅助上下文（中性线索）"},
    "DAW-001": {"recorded": "结构化听检为主观证据，永不单独定来源；≥2 项人声 yes 时建议 UVR-001"},
    "PA-001": {"recorded": "母带画像（描述性），不参与来源评分"},
    "UVR-001": {"recorded": "stem 为衍生证据；引擎重跑声部分析后按双轨合并"},
}


def reevaluate(evidence: dict, analysis: dict) -> dict:
    """Explicit verdict re-evaluation entry point: applies the evidence
    summary to the current verdict and returns a RECOMMENDATION — the
    verdict object itself is never mutated here."""
    task = evidence["task_id"]
    interp = _INTERPRETATIONS.get(task, {}).get(
        evidence["summary"], "已记录（无预定义解释规则）")
    return {
        "task_instance_id": evidence.get("task_instance_id"),
        "evidence_summary": evidence["summary"],
        "comparison_strength": evidence.get("comparison_strength", "indicative"),
        "interpretation": interp,
        "verdict_before": (analysis.get("verdict") or {}).get("verdict"),
        "verdict_after": (analysis.get("verdict") or {}).get("verdict"),
        "changed": False,
        "note": ("evidence ingestion only — verdict changes require the session "
                 "AI to apply the card's acceptance criteria across ALL evidence, "
                 "or a corpus-calibrated rule update"),
    }


_BOUNDARY_LINE = re.compile(r"^(\d+(?:\.\d+)?)\s+(.+)$")


def parse_operator_md(md_text: str, task_id: str | None = None) -> dict:
    """Extract filled record fields from an operator MD sheet.

    Field lines look like 'key ='; the value is every following line until
    the next field line or a code-fence end. Comment lines (# ...) are
    hints and ignored. 'none' -> None; 'freq note' lines -> {'freq_hz',
    'note'} dicts; anything else joins into a string. With task_id, only
    that task's `## ` section is parsed (sheets contain several tasks).
    """
    values: dict = {}
    current, buf = None, []

    def flush():
        nonlocal current, buf
        if current is None:
            return
        lines = [l.strip() for l in buf
                 if l.strip() and not l.strip().startswith("#")]
        if not lines or (len(lines) == 1 and lines[0].lower() == "none"):
            values[current] = None
        elif all(_BOUNDARY_LINE.match(l) for l in lines):
            values[current] = [
                {"freq_hz": float(m.group(1)), "note": m.group(2)}
                for m in map(_BOUNDARY_LINE.match, lines)]
        else:
            values[current] = " ".join(lines)
        current, buf = None, []

    text = md_text
    if task_id:
        sections = re.split(r"^## ", md_text, flags=re.M)
        sect = next((s_ for s_ in sections if s_.startswith(task_id)), None)
        if sect is None:
            raise SubmissionError(f"operator sheet has no section for {task_id}")
        text = sect
    for line in text.splitlines():
        m = re.match(r"^(\w+)\s*=\s*(.*)$", line)
        if m and not line.strip().startswith("#"):
            flush()
            current = m.group(1)
            if m.group(2).strip():
                buf.append(m.group(2))
            continue
        if line.strip().startswith("```"):
            flush()
            continue
        if current is not None:
            buf.append(line)
    flush()
    return values


def submission_from_operator_md(md_text: str, card: dict) -> dict:
    """Build a complete submission from a filled operator sheet: identity
    comes from the card, values from the parsed blanks (scoped to the
    card's own task section)."""
    return {
        "task_id": card["task_id"],
        "task_instance_id": card["task_instance_id"],
        "card_sha256": card["card_sha256"],
        "file_sha256": card["file_sha256"],
        "values": parse_operator_md(md_text, card["task_id"]),
        "screenshots": [],
        "operator_notes": "filled in operator_tasks.md",
        "deviations": "",
    }