"""Integration test against the confirmed real-world case (skipped when the
file is absent): DJ Konatal "洛春赋 (电音版)" — confirmed AI-generated."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from akiforensics import config  # noqa: E402
from akiforensics.engine import analyze_single  # noqa: E402

_DEFAULT_CASE = Path(r"C:\Users\Akiro\Desktop\DJ Konatal - 洛春赋 (电音版).flac")
CASE = Path(os.environ.get("AKIFORENSICS_CASE_FILE", str(_DEFAULT_CASE)))


@unittest.skipUnless(CASE.exists(), "case file not present on this machine")
class TestConfirmedCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = analyze_single(str(CASE), config.load())

    def test_timing_leg_is_applicable_and_ai_consistent(self):
        b = self.r["beatgrid"]
        self.assertTrue(b["applicable"], b.get("reason"))
        self.assertGreater(b["residual_std_ms"], 1.5)
        self.assertLess(b["pct_within_0.3ms"], 30.0)
        self.assertAlmostEqual(b["bpm"], 135.97, delta=0.15)

    def test_spectral_leg_flags_fake_lossless(self):
        s = self.r["spectral"]
        self.assertTrue(s["brick_wall"])
        self.assertLess(s["cutoff_hz"], 20800)
        self.assertTrue(s["fake_lossless_suspect"])

    def test_overall_verdict(self):
        self.assertIn(self.r["verdict"]["verdict"],
                      ("STRONG_AI_EVIDENCE", "LIKELY_AI"))


if __name__ == "__main__":
    unittest.main()
