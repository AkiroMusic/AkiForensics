"""Metadata leg tests on ffmpeg-produced FLAC fixtures (incl. KuGou tags)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures as fx  # noqa: E402
from akiforensics import config, decode, metadata  # noqa: E402

CFG = config.load()


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = fx.FixtureDir()
        wav = fx.render_kick_track(cls.fx.dir / "base.wav", bpm=128, dur=8.0)
        cls.plain = fx.wav_to_flac(wav, cls.fx.dir / "plain.flac")
        cls.kugou = fx.wav_to_flac(
            wav, cls.fx.dir / "kugou.flac",
            tags={"KGHASH": "ABCDEF0123456789", "QUALITY": "flac"})

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()

    def test_flac_md5_ok_and_blocks(self):
        m = metadata.analyze(str(self.plain))
        flac = m["flac"]
        self.assertIsNotNone(flac)
        self.assertIn("STREAMINFO", flac["blocks"])
        self.assertTrue(flac["md5_check"]["md5_ok"])
        self.assertIsNotNone(flac.get("vendor"))

    def test_kugou_fingerprint_detected(self):
        m = metadata.analyze(str(self.kugou))
        fps = m["platform_fingerprint"]
        self.assertTrue(any(p["platform"] == "kugou" for p in fps))
        self.assertIn("platform_quality_tag_present", m["flags"])

    def test_non_audio_raises_or_flags(self):
        with self.assertRaises(Exception):
            decode.probe(str(self.fx.dir))  # directory is not a media file


if __name__ == "__main__":
    unittest.main()
