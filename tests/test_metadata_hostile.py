"""Metadata parser robustness: hostile/malformed blocks must not crash."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from akiforensics.metadata import _parse_vorbis_comment, _picture_info  # noqa: E402


def _make_pic(mime: bytes, magic: bytes) -> bytes:
    pic = bytearray()
    pic += (0).to_bytes(4, "big")            # picture type
    pic += len(mime).to_bytes(4, "big")      # mime len
    pic += mime
    pic += (0).to_bytes(4, "big")            # desc len
    pic += b"\x00" * 16                       # width/height/depth/colors
    pic += len(magic).to_bytes(4, "big")     # data len
    pic += magic
    return bytes(pic)


class PictureInfoTests(unittest.TestCase):
    def test_valid_png_mime_match(self):
        info = _picture_info(_make_pic(b"image/png", b"\x89PNG\r\n\x1a\n\x00\x00"))
        self.assertEqual(info["declared_mime"], "image/png")
        self.assertEqual(info["actual_mime"], "image/png")
        self.assertFalse(info["mime_mismatch"])

    def test_mime_mismatch_detected(self):
        info = _picture_info(_make_pic(b"image/jpeg", b"\x89PNG\r\n\x1a\n\x00\x00"))
        self.assertTrue(info["mime_mismatch"])

    def test_hostile_inputs_do_not_crash(self):
        # empty / truncated / absurd lengths / bad utf-8 — all must return dicts
        cases = [
            b"",
            b"\x00" * 4,
            (0xFFFFFFFF).to_bytes(4, "big"),          # absurd mime len
            b"\x00" * 8 + (10).to_bytes(4, "big"),    # mime len beyond payload
            b"\x00" * 8 + (4).to_bytes(4, "big") + b"\xff\xfe\xfd\xfc",  # bad utf-8
        ]
        for pic in cases:
            info = _picture_info(pic)
            self.assertIsInstance(info, dict)
            self.assertIn("mime_mismatch", info)


class VorbisCommentTests(unittest.TestCase):
    def test_roundtrip(self):
        vendor = b"test-vendor"
        entry = "TITLE=hello".encode("utf-8")
        vc = len(vendor).to_bytes(4, "little") + vendor + \
            (1).to_bytes(4, "little") + len(entry).to_bytes(4, "little") + entry
        out = _parse_vorbis_comment(vc)
        self.assertEqual(out["vendor"], "test-vendor")
        self.assertEqual(out["tags"]["TITLE"], "hello")

    def test_hostile_inputs_do_not_crash(self):
        cases = [
            b"",
            b"\x00" * 3,
            (0xFFFFFFFF).to_bytes(4, "little"),          # absurd vendor len
            (4).to_bytes(4, "little") + b"abc",          # vendor len beyond payload
            (4).to_bytes(4, "little") + b"vend" +
                (0xFFFFFFFF).to_bytes(4, "little"),      # absurd comment count
            (4).to_bytes(4, "little") + b"vend" +
                (2).to_bytes(4, "little") +
                (0xFFFF).to_bytes(4, "little") + b"x",   # comment len beyond payload
        ]
        for vc in cases:
            out = _parse_vorbis_comment(vc)
            self.assertIsInstance(out, dict)
            self.assertIn("tags", out)


if __name__ == "__main__":
    unittest.main()
