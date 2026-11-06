"""Tests for the human-submission return path (protocol 1.0 ingestion)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures as fx  # noqa: E402
from akiforensics import config  # noqa: E402
from akiforensics import submission  # noqa: E402
from akiforensics.engine import analyze_single  # noqa: E402
from akiforensics.tasks import generate_tasks as tasks_cards  # noqa: E402

CFG = config.load()


class SubmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        from akiforensics import beatgrid, decode, spectral, verdict
        cls.fx = fx.FixtureDir()
        wav = fx.render_kick_track(cls.fx.dir / "sub_k.wav", bpm=128, dur=30,
                                   jitter_ms=3.0, wander_ms=2.0)
        noise = fx.render_band_noise(cls.fx.dir / "sub_n.wav", cutoff_hz=20500)
        sr, _st, m_k = decode.decode_work(str(wav), sample_rate=44100, channels=2)
        sr_n, _st2, m_n = decode.decode_work(str(noise), sample_rate=44100, channels=2)
        beats = beatgrid.analyze(m_k, sr, CFG["beatgrid"])
        spec = spectral.analyze(m_n, sr_n, CFG["spectral"])
        meta = {"flags": [], "flag_families": {"integrity": [], "packaging": [],
               "provenance": []}, "platform_fingerprint": [], "vendor": "libFLAC",
               "container": "flac", "duration_s": 30.0}
        verd = verdict.aggregate(meta, spec, beats, "flac", CFG)
        cls.analysis = {"file": {"path": str(wav), "name": wav.name,
                                 "sha256": "x" * 64, "duration_s": 30.0},
                        "metadata": meta, "spectral": spec,
                        "beatgrid": beats, "verdict": verd}
        rx = next(t for t in tasks_cards(cls.analysis) if t["task_id"] == "RX-001")
        cls.analysis["manual_tasks"] = tasks_cards(cls.analysis)
        cls.analysis["file"]["sha256"] = rx["file_sha256"]
        cls.card = rx
        cls.sha = rx["file_sha256"]

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()

    def _submission(self, **over):
        fields = {k: None for k in self.card["record_fields"] if k != "screenshots"}
        fields.update(over.pop("values", {}))
        sub = {"task_id": self.card["task_id"], "file_sha256": self.sha,
               "values": fields, "screenshots": [], "operator_notes": "ok",
               "deviations": ""}
        sub.update(over)
        return sub

    def test_validate_and_merge_recorded(self):
        sub = self._submission()
        merged = submission.merge(sub, self.analysis, self.card)
        ev = merged["human_evidence"][-1]
        self.assertEqual(ev["task_id"], self.card["task_id"])
        self.assertEqual(ev["summary"], "recorded")
        self.assertNotIn("_stereo", merged)  # helper arrays stay out of merges? (dict copy keeps them; check separately)

    def test_agreement_detected(self):
        # RX-001-style card: feed human cutoff equal to engine cutoff
        rx = next((t for t in self.analysis["manual_tasks"]
                   if t["task_id"] == "RX-001"), None)
        if rx is None:
            self.skipTest("fixture produced no RX-001 card")
        eng = self.analysis["spectral"]["cutoff_hz"]
        sub = {"task_id": "RX-001", "file_sha256": self.sha,
               "values": {k: None for k in rx["record_fields"] if k != "screenshots"},
               "screenshots": [], "operator_notes": "", "deviations": ""}
        sub["values"]["cutoff_hz_left"] = eng
        sub["values"]["cutoff_hz_right"] = eng
        merged = submission.merge(sub, self.analysis, rx)
        ev = merged["human_evidence"][-1]
        self.assertEqual(ev["summary"], "agreement")

    def test_contradiction_detected(self):
        rx = next((t for t in self.analysis["manual_tasks"]
                   if t["task_id"] == "RX-001"), None)
        if rx is None:
            self.skipTest("fixture produced no RX-001 card")
        sub = {"task_id": "RX-001", "file_sha256": self.sha,
               "values": {k: None for k in rx["record_fields"] if k != "screenshots"},
               "screenshots": [], "operator_notes": "", "deviations": ""}
        sub["values"]["cutoff_hz_left"] = (self.analysis["spectral"]["cutoff_hz"] or 0) + 2000
        merged = submission.merge(sub, self.analysis, rx)
        ev = merged["human_evidence"][-1]
        self.assertEqual(ev["summary"], "contradiction")
        self.assertIn("contradiction", ev["comparisons"][0]["result"])

    def test_validation_failures(self):
        with self.assertRaises(submission.SubmissionError):
            submission.merge({"task_id": "WRONG"}, self.analysis, self.card)
        bad = self._submission(file_sha256="0" * 64)
        with self.assertRaises(submission.SubmissionError):
            submission.merge(bad, self.analysis, self.card)
        incomplete = {"task_id": self.card["task_id"], "file_sha256": self.sha,
                      "values": {}}
        with self.assertRaises(submission.SubmissionError):
            submission.merge(incomplete, self.analysis, self.card)

    def test_engine_values_never_overwritten(self):
        eng_before = self.analysis["spectral"]["cutoff_hz"]
        rx = next((t for t in self.analysis["manual_tasks"]
                   if t["task_id"] == "RX-001"), None)
        if rx is None:
            self.skipTest("fixture produced no RX-001 card")
        sub = {"task_id": "RX-001", "file_sha256": self.sha,
               "values": {k: None for k in rx["record_fields"] if k != "screenshots"},
               "screenshots": [], "operator_notes": "", "deviations": ""}
        sub["values"]["cutoff_hz_left"] = 99999
        merged = submission.merge(sub, self.analysis, rx)
        self.assertEqual(merged["spectral"]["cutoff_hz"], eng_before)
        self.assertEqual(merged["human_evidence"][-1]["values"]["cutoff_hz_left"], 99999)


if __name__ == "__main__":
    unittest.main()
