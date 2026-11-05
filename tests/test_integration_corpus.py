"""Corpus-driven integration test.

Point AKIFORENSICS_CASE_FILE at any *confirmed-AI* audio file (any name, any
delivery format); the test verifies the engine never grades it human-side.
Skipped when the variable is unset or the path does not exist. Optional
AKIFORENSICS_EXPECT=human inverts the invariant for confirmed-human samples.
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


@unittest.skipUnless(CASE and Path(CASE).exists(),
                     "set AKIFORENSICS_CASE_FILE to a confirmed sample to enable")
class TestConfirmedSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = analyze_single(CASE, config.load())
        b = cls.r["beatgrid"]
        print("\n[case] bpm=%s std=%sms pct03=%s%% verdict=%s" % (
            b.get("bpm"), b.get("residual_std_ms"), b.get("pct_within_0.3ms"),
            cls.r["verdict"]["verdict"]))

    def test_decisive_leg_never_grades_opposite(self):
        bg = self.r["verdict"]["legs"]["beatgrid"]["verdict"]
        if EXPECT_HUMAN:
            self.assertNotEqual(bg, "ai_consistent")
        else:
            self.assertNotEqual(bg, "human_consistent")

    def test_overall_verdict_not_opposite(self):
        v = self.r["verdict"]["verdict"]
        if EXPECT_HUMAN:
            self.assertNotIn(v, ("STRONG_AI_EVIDENCE", "LIKELY_AI"))
        else:
            self.assertNotEqual(v, "LIKELY_HUMAN")


if __name__ == "__main__":
    unittest.main()
