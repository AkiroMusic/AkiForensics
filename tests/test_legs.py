"""Unit tests for the three forensic legs on synthetic known-property audio."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures as fx  # noqa: E402
from akiforensics import config  # noqa: E402
from akiforensics import beatgrid, spectral  # noqa: E402
from akiforensics import decode  # noqa: E402
from akiforensics import verdict  # noqa: E402

CFG = config.load()


class BeatGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = fx.FixtureDir()
        cls.locked = fx.render_kick_track(cls.fx.dir / "locked.wav", bpm=128,
                                          jitter_ms=0, wander_ms=0)
        cls.jittered = fx.render_kick_track(cls.fx.dir / "jittered.wav", bpm=128,
                                            jitter_ms=3.0, wander_ms=2.0)
        _, m_lock = decode.decode_work(str(cls.locked))
        _, m_jit = decode.decode_work(str(cls.jittered))
        cls.res_lock = beatgrid.analyze(m_lock, 44100, CFG["beatgrid"])
        cls.res_jit = beatgrid.analyze(m_jit, 44100, CFG["beatgrid"])

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()

    def test_locked_grid_is_sample_locked(self):
        r = self.res_lock
        self.assertTrue(r["applicable"], r.get("reason"))
        self.assertLess(r["residual_std_ms"], 0.5)
        self.assertGreater(r["pct_within_0.3ms"], 70.0)
        self.assertAlmostEqual(r["bpm"], 128.0, delta=0.1)

    def test_locked_grades_human(self):
        g = verdict._grade_beatgrid(self.res_lock, CFG)
        self.assertEqual(g["verdict"], "human_consistent")

    def test_jittered_grid_shows_generative_wander(self):
        r = self.res_jit
        self.assertTrue(r["applicable"], r.get("reason"))
        self.assertGreater(r["residual_std_ms"], 1.5)
        self.assertLess(r["pct_within_0.3ms"], 30.0)
        self.assertAlmostEqual(r["bpm"], 128.0, delta=0.1)

    def test_jittered_grades_ai(self):
        g = verdict._grade_beatgrid(self.res_jit, CFG)
        self.assertEqual(g["verdict"], "ai_consistent")


class SpectralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = fx.FixtureDir()
        cls.full = fx.render_band_noise(cls.fx.dir / "full.wav", cutoff_hz=None)
        cls.walled = fx.render_band_noise(cls.fx.dir / "walled.wav", cutoff_hz=20500)
        _, m_full = decode.decode_work(str(cls.full))
        _, m_walled = decode.decode_work(str(cls.walled))
        cls.res_full = spectral.analyze(m_full, 44100, CFG["spectral"])
        cls.res_walled = spectral.analyze(m_walled, 44100, CFG["spectral"])

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()

    def test_full_band_has_no_cutoff(self):
        self.assertIsNone(self.res_full["cutoff_hz"])
        self.assertFalse(self.res_full["brick_wall"])

    def test_full_band_grades_human(self):
        g = verdict._grade_spectral(self.res_full, "wav", CFG)
        self.assertEqual(g["verdict"], "human_consistent")

    def test_brick_wall_detected_at_20k5(self):
        s = self.res_walled
        self.assertTrue(s["brick_wall"])
        self.assertIsNotNone(s["cutoff_hz"])
        self.assertLessEqual(s["cutoff_hz"], 20650)
        self.assertGreaterEqual(s["cutoff_hz"], 20300)

    def test_wall_in_lossless_container_grades_ai(self):
        g = verdict._grade_spectral(self.res_walled, "flac", CFG)
        self.assertEqual(g["verdict"], "ai_consistent")

    def test_wall_in_lossy_container_is_na(self):
        g = verdict._grade_spectral(self.res_walled, "mp3", CFG)
        self.assertEqual(g["verdict"], "na")


class VerdictAggregationTests(unittest.TestCase):
    def _meta(self, flags):
        return {"flags": flags, "platform_fingerprint": [], "vendor": "x",
                "container": "flac"}

    def test_strong_ai(self):
        bg = {"applicable": True, "residual_std_ms": 2.3,
              "pct_within_0.3ms": 7.0, "bpm": 135.97, "bpm_integer_distance": 0.03}
        sp = {"fake_lossless_suspect": True, "cutoff_hz": 20462,
              "brick_wall": True, "cliff_depth_db": 37.0}
        out = verdict.aggregate(self._meta(["picture_mime_mismatch", "decoder_errors"]),
                                sp, bg, "flac", CFG)
        self.assertEqual(out["verdict"], "STRONG_AI_EVIDENCE")

    def test_likely_human(self):
        bg = {"applicable": True, "residual_std_ms": 0.3,
              "pct_within_0.3ms": 95.0, "bpm": 128.0, "bpm_integer_distance": 0.0}
        sp = {"fake_lossless_suspect": False, "cutoff_hz": None, "brick_wall": False}
        out = verdict.aggregate(self._meta([]), sp, bg, "flac", CFG)
        self.assertEqual(out["verdict"], "LIKELY_HUMAN")

    def test_timing_only_likely_ai(self):
        bg = {"applicable": True, "residual_std_ms": 2.0,
              "pct_within_0.3ms": 10.0, "bpm": 128.3, "bpm_integer_distance": 0.3}
        sp = {"fake_lossless_suspect": False, "cutoff_hz": None, "brick_wall": False}
        out = verdict.aggregate(self._meta([]), sp, bg, "flac", CFG)
        self.assertEqual(out["verdict"], "LIKELY_AI")

    def test_inconclusive_when_timing_na(self):
        bg = {"applicable": False, "reason": "no kicks"}
        sp = {"fake_lossless_suspect": False, "cutoff_hz": None, "brick_wall": False}
        out = verdict.aggregate(self._meta([]), sp, bg, "flac", CFG)
        self.assertEqual(out["verdict"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
