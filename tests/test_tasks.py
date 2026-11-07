"""Task-card system tests: determinism, blinding, completeness, gap targeting."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures as fx  # noqa: E402
from akiforensics import config, decode, spectral, beatgrid, verdict, tasks  # noqa: E402

CFG = config.load()
REQUIRED_KEYS = {"task_id", "protocol", "blinded", "tool", "segment",
                 "hypothesis_zh", "hypothesis_en", "steps_zh", "record_fields",
                 "acceptance", "evidence_gap"}


def _build_analysis(fxd: fx.FixtureDir, wall: bool, jitter: bool) -> dict:
    """Real engine legs on fixtures, merged into one analysis dict."""
    wav = fx.render_kick_track(fxd.dir / (("jit" if jitter else "lock") + "_k.wav"),
                               bpm=128, jitter_ms=3.0 if jitter else 0.0,
                               wander_ms=2.0 if jitter else 0.0, dur=60)
    noise = fx.render_band_noise(fxd.dir / (("walled" if wall else "full") + "_n.wav"),
                                 cutoff_hz=20500 if wall else None)
    sr, _st, m_k = decode.decode_work(str(wav), sample_rate=44100, channels=2)
    sr_n, _st, m_n = decode.decode_work(str(noise), sample_rate=44100, channels=2)
    beats = beatgrid.analyze(m_k, sr, CFG["beatgrid"])
    spec = spectral.analyze(m_n, sr_n, CFG["spectral"])
    meta = {"flags": [], "platform_fingerprint": [], "vendor": "libFLAC",
            "container": "flac", "duration_s": 60.0}
    verd = verdict.aggregate(meta, spec, beats, "flac", CFG)
    return {"file": {"path": str(wav), "name": wav.name},
            "metadata": meta, "spectral": spec, "beatgrid": beats, "verdict": verd}


class TaskCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = fx.FixtureDir()
        cls.rich = _build_analysis(cls.fx, wall=True, jitter=True)   # RX-001 + RX-002
        cls.clean = _build_analysis(cls.fx, wall=False, jitter=False)  # DAW-001

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()

    def test_gap_targeting_issues_right_cards(self):
        ids = [t["task_id"] for t in tasks.generate_tasks(self.rich)]
        # rich = timing variation + wall => convergent: RX-001 + RX-002 + DAW-001 gate
        self.assertIn("RX-001", ids)
        self.assertIn("RX-002", ids)
        self.assertIn("DAW-001", ids)  # human gate for the convergent verdict

    def test_clean_track_gets_listening_gate(self):
        ids = [t["task_id"] for t in tasks.generate_tasks(self.clean)]
        self.assertEqual(ids, ["DAW-001"])

    def test_blinding_levels(self):
        for level in ("value", "hypothesis", "none"):
            cards = tasks.generate_tasks(self.rich, blinding_level=level)
            self.assertTrue(cards)
        v = tasks.generate_tasks(self.rich, blinding_level="value")
        self.assertTrue(all(c["blinded"] for c in v))
        self.assertTrue(all("operator_view" not in c for c in v))
        n = tasks.generate_tasks(self.rich, blinding_level="none")
        self.assertTrue(all(not c["blinded"] for c in n))
        h = tasks.generate_tasks(self.rich, blinding_level="hypothesis")
        self.assertTrue(all(c["blinded"] and "operator_view" in c for c in h))
        op = h[0]["operator_view"]
        self.assertNotIn("hypothesis_zh", op)
        self.assertNotIn("evidence_gap", op)
        self.assertIn("steps_zh", op)
        with self.assertRaises(ValueError):
            tasks.generate_tasks(self.rich, blinding_level="bogus")

    def test_cards_are_deterministic(self):
        a = json.dumps(tasks.generate_tasks(self.rich), sort_keys=True, ensure_ascii=False)
        b = json.dumps(tasks.generate_tasks(self.rich), sort_keys=True, ensure_ascii=False)
        self.assertEqual(a, b)

    def test_cards_are_complete(self):
        for t in tasks.generate_tasks(self.rich) + tasks.generate_tasks(self.clean):
            self.assertTrue(REQUIRED_KEYS.issubset(t.keys()), t["task_id"])
            self.assertTrue(len(t["steps_zh"]) >= 3, t["task_id"])
            self.assertIn("confirm", t["acceptance"], t["task_id"])
            self.assertIn("refute", t["acceptance"], t["task_id"])

    def test_blinding_hides_engine_values(self):
        cutoff = self.rich["spectral"]["cutoff_hz"]
        std = self.rich["beatgrid"]["residual_std_ms"]
        cards = tasks.generate_tasks(self.rich, blinded=True)
        blob = json.dumps(cards, ensure_ascii=False)
        self.assertNotIn(str(int(round(cutoff))), blob)
        self.assertNotIn(str(std), blob)
        self.assertTrue(all(c["blinded"] for c in cards))

    def test_unblinded_mode_available(self):
        cards = tasks.generate_tasks(self.rich, blinding_level="none")
        self.assertTrue(all(not c["blinded"] for c in cards))

    def test_stage2_cards_on_demand(self):
        cards = tasks.generate_tasks(self.rich, force=("UVR-001", "PA-001"))
        ids = [t["task_id"] for t in cards]
        self.assertIn("UVR-001", ids)
        self.assertIn("PA-001", ids)
        uvr = next(t for t in cards if t["task_id"] == "UVR-001")
        # no real model registered in config/uvr_models.toml -> blocked card
        self.assertTrue(uvr.get("model_unpinned"))
        self.assertIn("模型未锁定", uvr["hypothesis_zh"])
        self.assertNotIn("model_sha256", uvr["record_fields"])
        self.assertEqual(uvr["acceptance"], {"confirm": "n/a", "refute": "n/a"})
        self.assertIn("model_unpinned", uvr["evidence_gap"])

    def test_file_sha256_recorded(self):
        cards = tasks.generate_tasks(self.rich)
        for c in cards:
            self.assertEqual(len(c["file_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
