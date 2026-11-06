"""Corpus-driven integration test.

Point AKIFORENSICS_CASE_FILE at a *confirmed-AI* audio file (any name, any
delivery format); the test verifies the engine never grades it as human-
production-consistent. Optional AKIFORENSICS_EXPECT=human inverts the
invariant for confirmed-human samples. `na` outcomes are legal for both
classes (the leg may be inapplicable) and never satisfy the opposite class.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from akiforensics import config  # noqa: E402
from akiforensics.engine import analyze_single  # noqa: E402

CASE = os.environ.get("AKIFORENSICS_CASE_FILE", "").strip()
EXPECT_HUMAN = os.environ.get("AKIFORENSICS_EXPECT", "ai").lower() == "human"

AI_LEGS = {"timing_variation"}
HUMAN_LEGS = {"timing_locked"}
AI_VERDICTS = {"AI_EVIDENCE_CONVERGENT", "LIKELY_AI"}
HUMAN_VERDICTS = {"LIKELY_HUMAN"}


@unittest.skipUnless(CASE and Path(CASE).exists(),
                     "set AKIFORENSICS_CASE_FILE to a confirmed sample to enable")
class TestConfirmedSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = analyze_single(str(Path(CASE)), config.load())
        b = cls.r["beatgrid"]
        print("\n[case] bpm=%s std=%sms pct03=%s%% verdict=%s" % (
            b.get("bpm"), b.get("residual_std_ms"), b.get("pct_within_0.3ms"),
            cls.r["verdict"]["verdict"]))

    def test_decisive_leg_never_grades_opposite(self):
        bg = self.r["verdict"]["legs"]["beatgrid"]["verdict"]
        if EXPECT_HUMAN:
            self.assertNotIn(bg, AI_LEGS,
                             "confirmed-human sample graded as timing variation")
        else:
            self.assertNotIn(bg, HUMAN_LEGS,
                             "confirmed-AI sample graded as timing locked")

    def test_overall_verdict_not_opposite(self):
        v = self.r["verdict"]["verdict"]
        if EXPECT_HUMAN:
            self.assertNotIn(v, AI_VERDICTS)
        else:
            self.assertNotIn(v, HUMAN_VERDICTS)

    def test_na_is_not_either_class(self):
        bg = self.r["verdict"]["legs"]["beatgrid"]["verdict"]
        if bg == "na":
            self.assertNotIn(self.r["verdict"]["verdict"],
                             AI_VERDICTS | HUMAN_VERDICTS,
                             "N/A timing must not produce a source-attributed verdict")

    def test_source_verdicts_disclose_alternatives(self):
        v = self.r["verdict"]
        if v["verdict"] in AI_VERDICTS | HUMAN_VERDICTS:
            self.assertTrue(v["alternative_hypotheses"],
                            "source-leaning verdict without alternative_hypotheses")


if __name__ == "__main__":
    unittest.main()
