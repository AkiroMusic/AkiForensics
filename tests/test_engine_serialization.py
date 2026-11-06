"""End-to-end serialization: real engine output must never leak runtime
arrays into report.json (the _stereo bug of v0.3.0)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures as fx  # noqa: E402
from akiforensics import config, report  # noqa: E402
from akiforensics.engine import analyze_single  # noqa: E402

CFG = config.load()


class SerializationTests(unittest.TestCase):
    def test_real_analysis_json_has_no_underscore_keys(self):
        fxd = fx.FixtureDir()
        try:
            wav = fx.render_kick_track(fxd.dir / "ser.wav", bpm=128, dur=10)
            flac = fx.wav_to_flac(wav, fxd.dir / "ser.flac")
            r = analyze_single(str(flac), CFG)
            self.assertIn("_stereo", r)  # engine does carry the working array...
            js = json.dumps(report._jsonable(r))
            self.assertNotIn('"_stereo"', js)   # ...but it never reaches JSON
            self.assertNotIn('"_plotdata"', js)
            # sane size: a 10 s file must not embed PCM
            self.assertLess(len(js), 2_000_000, "report JSON suspiciously large")
        finally:
            fxd.cleanup()

    def test_verdict_fields_complete(self):
        fxd = fx.FixtureDir()
        try:
            wav = fx.render_kick_track(fxd.dir / "ser2.wav", bpm=128, dur=10)
            flac = fx.wav_to_flac(wav, fxd.dir / "ser2.flac")
            r = analyze_single(str(flac), CFG)
            v = r["verdict"]
            for key in ("verdict", "positive_evidence", "alternative_hypotheses",
                        "calibration_status", "human_reference_status",
                        "probability_calibrated", "threshold_version"):
                self.assertIn(key, v)
            self.assertEqual(v["calibration_status"], "preliminary")
            self.assertEqual(v["probability_calibrated"], False)
        finally:
            fxd.cleanup()


if __name__ == "__main__":
    unittest.main()
