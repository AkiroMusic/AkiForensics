"""Unit tests for the forensic legs on synthetic known-property audio.

Vocabulary v2: legs report measurements (timing_locked / timing_variation /
no_anomaly_detected / lossy_source_fingerprint); source attribution happens
only in verdict.aggregate with correlated delivery-chain evidence fused.
"""

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
        sr_l, _st, m_lock = decode.decode_work(str(cls.locked), sample_rate=44100)
        sr_j, _st, m_jit = decode.decode_work(str(cls.jittered), sample_rate=44100)
        cls.res_lock = beatgrid.analyze(m_lock, sr_l, CFG["beatgrid"])
        cls.res_jit = beatgrid.analyze(m_jit, sr_j, CFG["beatgrid"])

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()

    def test_locked_grid_is_sample_locked(self):
        r = self.res_lock
        self.assertTrue(r["applicable"], r.get("reason"))
        self.assertLess(r["residual_std_ms"], 0.5)
        self.assertGreater(r["pct_within_0.3ms"], 70.0)
        self.assertAlmostEqual(r["bpm"], 128.0, delta=0.1)

    def test_locked_reports_confidence_metrics(self):
        r = self.res_lock
        self.assertIsNotNone(r["onset_confidence"])
        self.assertGreater(r["onset_confidence"], 0.6)
        self.assertIsNotNone(r["grid_hit_rate"])
        self.assertLess(r["local_bpm_drift"], 0.05)

    def test_locked_grades_timing_locked(self):
        g = verdict._grade_beatgrid(self.res_lock, CFG)
        self.assertEqual(g["verdict"], "timing_locked")
        self.assertIn("production-consistency", g["interpretation_en"])

    def test_jittered_grid_shows_generative_wander(self):
        r = self.res_jit
        self.assertTrue(r["applicable"], r.get("reason"))
        self.assertGreater(r["residual_std_ms"], 1.5)
        self.assertLess(r["pct_within_0.3ms"], 30.0)
        self.assertAlmostEqual(r["bpm"], 128.0, delta=0.1)

    def test_jittered_grades_timing_variation(self):
        g = verdict._grade_beatgrid(self.res_jit, CFG)
        self.assertEqual(g["verdict"], "timing_variation")
        self.assertIn("unquantized live playing", g["interpretation_en"])


class TwoStepPatternTests(unittest.TestCase):
    """Broken kick patterns (two-step): the main-kick cluster (downbeat) is the
    standard; ghost/syncopated kicks must not pollute the grid fit."""

    @classmethod
    def setUpClass(cls):
        cls.fx = fx.FixtureDir()
        cls.locked = fx.render_kick_track(cls.fx.dir / "ts_locked.wav", bpm=136,
                                          jitter_ms=0, wander_ms=0, dur=90,
                                          pattern="twostep")
        cls.jittered = fx.render_kick_track(cls.fx.dir / "ts_jit.wav", bpm=136,
                                            jitter_ms=3.0, wander_ms=2.0, dur=90,
                                            pattern="twostep")
        sr, _st, m1 = decode.decode_work(str(cls.locked), sample_rate=44100)
        _, _st, m2 = decode.decode_work(str(cls.jittered), sample_rate=44100)
        cls.res_lock = beatgrid.analyze(m1, sr, CFG["beatgrid"])
        cls.res_jit = beatgrid.analyze(m2, sr, CFG["beatgrid"])

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()

    def test_locked_twostep_is_locked_on_main_cluster(self):
        r = self.res_lock
        self.assertTrue(r["applicable"], r.get("reason"))
        self.assertEqual(r["kick_selection"]["mode"], "main-cluster")
        self.assertLess(r["kick_selection"]["n_selected"],
                        r["kick_selection"]["n_candidates"])
        self.assertLess(r["residual_std_ms"], 0.5)
        self.assertGreater(r["pct_within_0.3ms"], 70.0)
        self.assertAlmostEqual(r["bpm"], 136.0, delta=0.2)

    def test_jittered_twostep_shows_variation(self):
        r = self.res_jit
        self.assertTrue(r["applicable"], r.get("reason"))
        self.assertGreater(r["residual_std_ms"], 1.5)
        self.assertLess(r["pct_within_0.3ms"], 30.0)

    def test_locked_twostep_grades_timing_locked(self):
        g = verdict._grade_beatgrid(self.res_lock, CFG)
        self.assertEqual(g["verdict"], "timing_locked")


class SpectralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = fx.FixtureDir()
        cls.full = fx.render_band_noise(cls.fx.dir / "full.wav", cutoff_hz=None)
        cls.walled = fx.render_band_noise(cls.fx.dir / "walled.wav", cutoff_hz=20500)
        sr_f, _st, m_full = decode.decode_work(str(cls.full), sample_rate=44100)
        sr_w, _st, m_walled = decode.decode_work(str(cls.walled), sample_rate=44100)
        cls.res_full = spectral.analyze(m_full, sr_f, CFG["spectral"])
        cls.res_walled = spectral.analyze(m_walled, sr_w, CFG["spectral"])

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()

    def test_full_band_has_no_cutoff(self):
        self.assertIsNone(self.res_full["cutoff_hz"])
        self.assertFalse(self.res_full["brick_wall"])

    def test_full_band_is_no_anomaly_not_human(self):
        g = verdict._grade_spectral(self.res_full, "flac", CFG)
        self.assertEqual(g["verdict"], "no_anomaly_detected")
        self.assertIn("not source-diagnostic", g["why"])

    def test_brick_wall_detected_at_20k5(self):
        s = self.res_walled
        self.assertTrue(s["brick_wall"])
        self.assertIsNotNone(s["cutoff_hz"])
        self.assertLessEqual(s["cutoff_hz"], 20650)
        self.assertGreaterEqual(s["cutoff_hz"], 20300)

    def test_wall_in_lossless_container_is_fingerprint(self):
        g = verdict._grade_spectral(self.res_walled, "flac", CFG)
        self.assertEqual(g["verdict"], "lossy_source_fingerprint")

    def test_wall_in_lossy_container_is_na(self):
        g = verdict._grade_spectral(self.res_walled, "mp3", CFG)
        self.assertEqual(g["verdict"], "na")


class VerdictAggregationTests(unittest.TestCase):
    def _bg(self, std, pct03, applicable=True):
        return {"applicable": applicable, "reason": None if applicable else "no kicks",
                "residual_std_ms": std, "pct_within_0.3ms": pct03,
                "bpm": 128.0, "bpm_integer_distance": 0.0}

    def _sp(self, wall, cutoff):
        return {"brick_wall": wall, "cutoff_hz": cutoff,
                "cliff_depth_db": 37.0 if wall else None}

    def _meta(self, flags, families=None):
        return {"flags": flags, "flag_families": families or {}, "platform_fingerprint": [],
                "vendor": "x", "container": "flac"}

    def test_convergent_ai_with_alternatives(self):
        fams = {"integrity": ["decoder_errors"], "packaging": [], "provenance": []}
        out = verdict.aggregate(self._meta(["decoder_errors"], fams),
                                self._sp(True, 20462), self._bg(2.3, 7.0), "flac", CFG)
        self.assertEqual(out["verdict"], "AI_EVIDENCE_CONVERGENT")
        self.assertTrue(out["delivery_chain_fused"])
        self.assertTrue(out["alternative_hypotheses"])
        self.assertTrue(out["human_gate_recommended"])
        self.assertTrue(out["disclaimer"].startswith(f"Thresholds {CFG['meta']['version']}"))

    def test_likely_ai_timing_only(self):
        out = verdict.aggregate(self._meta([]), self._sp(False, None),
                                self._bg(2.0, 10.0), "flac", CFG)
        self.assertEqual(out["verdict"], "LIKELY_AI")
        self.assertFalse(out["human_gate_recommended"])
        self.assertTrue(out["alternative_hypotheses"])

    def test_likely_human_requires_positive_everywhere(self):
        out = verdict.aggregate(self._meta([]), self._sp(False, None),
                                self._bg(0.3, 95.0), "flac", CFG)
        self.assertEqual(out["verdict"], "LIKELY_HUMAN")
        # production-consistency, not authorship: alternative must be listed
        self.assertIn("AI-hybrid", out["alternative_hypotheses"][0])

    def test_no_cutoff_alone_is_not_human(self):
        # full-band spectrum + no timing evidence => nothing to say
        out = verdict.aggregate(self._meta([]), self._sp(False, None),
                                self._bg(0.0, 0.0, applicable=False), "flac", CFG)
        self.assertEqual(out["verdict"], "INCONCLUSIVE")

    def test_delivery_chain_alone_does_not_attribute(self):
        out = verdict.aggregate(self._meta([]), self._sp(True, 20462),
                                self._bg(0.0, 0.0, applicable=False), "flac", CFG)
        self.assertEqual(out["verdict"], "DELIVERY_CHAIN_ANOMALY")

    def test_packaging_flag_never_votes(self):
        # picture MIME mismatch is packaging — must NOT produce a delivery verdict
        out = verdict.aggregate(
            self._meta(["picture_mime_mismatch"],
                       {"integrity": [], "packaging": ["picture_mime_mismatch"],
                        "provenance": []}),
            self._sp(False, None), self._bg(0.0, 0.0, applicable=False), "flac", CFG)
        self.assertEqual(out["verdict"], "INCONCLUSIVE")

    def test_integrity_flag_votes_into_delivery(self):
        out = verdict.aggregate(
            self._meta(["md5_mismatch"],
                       {"integrity": ["md5_mismatch"], "packaging": [], "provenance": []}),
            self._sp(False, None), self._bg(0.0, 0.0, applicable=False), "flac", CFG)
        self.assertEqual(out["verdict"], "DELIVERY_CHAIN_ANOMALY")


if __name__ == "__main__":
    unittest.main()
