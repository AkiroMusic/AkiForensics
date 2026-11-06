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

import json
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


def validate(submission: dict, card: dict) -> None:
    """Structural validation against the task card."""
    _require(isinstance(submission, dict), "submission must be a JSON object")
    _require(submission.get("task_id") == card["task_id"],
             f"task_id mismatch: submission={submission.get('task_id')} "
             f"card={card['task_id']}")
    _require(submission.get("file_sha256") == card.get("file_sha256"),
             "file_sha256 does not match the analyzed file — wrong file returned?")
    values = submission.get("values")
    _require(isinstance(values, dict), "missing 'values' object")
    for k in card["record_fields"]:
        if k == "screenshots":
            continue
        _require(k in values, f"missing record field '{k}' (null is a valid value)")


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
    for k, human_v in values.items():
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
            "result": _compare_numeric(eng_v, human_v, tol) if tol else "recorded",
        })

    evidence = {
        "task_id": card["task_id"],
        "source": {"type": "human_tool", "tool": card["tool"]["name"]},
        "values": values,
        "screenshots": submission.get("screenshots", []),
        "operator_notes": submission.get("operator_notes", ""),
        "deviations": submission.get("deviations", ""),
        "blinded": card.get("blinded", True),
        "comparisons": comparisons,
        "summary": ("agreement" if all(c["result"] == "agreement" for c in comparisons)
                    and comparisons else
                    "contradiction" if any(c["result"] == "contradiction"
                                           for c in comparisons) else
                    "recorded"),
    }
    out = dict(analysis)
    out.pop("_stereo", None)  # working arrays never enter persisted evidence
    out["human_evidence"] = out.get("human_evidence", []) + [evidence]
    return out


def load_submission(path: str | Path) -> dict:
    with open(path, "rb") as f:
        sub = json.load(f)
    _require(isinstance(sub, dict), "submission file must contain a JSON object")
    return sub
