"""Round-4 acceptance tests: rendered-HTML leakage, card identity lifecycle,
submission identity enforcement — the three v0.3.2 verdict-critical paths."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures as fx  # noqa: E402
from akiforensics import config, report, submission  # noqa: E402
from akiforensics.engine import analyze_single  # noqa: E402
from akiforensics.tasks import generate_tasks  # noqa: E402

CFG = config.load()


class HtmlLeakageTests(unittest.TestCase):
    """The GPT-R4 leak was in the RENDER layer, not the data layer — tests
    must exercise report.render_html on real engine output."""

    @classmethod
    def setUpClass(cls):
        cls.fx = fx.FixtureDir()
        cls.tmp = Path(tempfile.mkdtemp(prefix="akif_html_"))
        noise = fx.render_band_noise(cls.fx.dir / "h_n.wav", cutoff_hz=20500)
        flac = fx.wav_to_flac(noise, cls.fx.dir / "h.flac")
        cls.r = analyze_single(str(flac), blinding_level="hypothesis")
        cls.outdir = cls.tmp / "rep"
        cls.outdir.mkdir(parents=True)
        cls.analyst = Path(report.render_html(cls.r, cls.outdir)).read_text("utf-8")
        cls.operator = (cls.outdir / "operator_tasks.html").read_text("utf-8")
        rx = next(t for t in cls.r["manual_tasks"] if t["task_id"] == "RX-001")
        cls.rx = rx

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_both_files_exist(self):
        self.assertTrue((self.outdir / "analyst_report.html").exists())
        self.assertTrue((self.outdir / "operator_tasks.html").exists())

    def test_operator_html_has_no_verdict(self):
        verdict = self.r["verdict"]["verdict"]
        spaced = verdict.replace("_", " ")
        for leak in (verdict, spaced, "AI 证据收敛", "交付链异常"):
            self.assertNotIn(leak, self.operator)

    def test_operator_html_has_no_engine_measurements(self):
        co = self.r["spectral"]["cutoff_hz"]
        self.assertIsNotNone(co)
        self.assertNotIn(f"{co:.0f}", self.operator)
        self.assertNotIn(f"{co:.0f}", self.operator.replace(",", ""))

    def test_operator_html_has_no_analyst_field_names(self):
        for name in ("cutoff_hz_left", "cutoff_hz_right",
                     "wall_stable_across_subsegments", "above_wall_silence"):
            self.assertNotIn(name, self.operator)

    def test_operator_html_has_no_analyst_wording(self):
        for phrase in ("确证/推翻", "可改变 spectral 链结论", "有损源指纹",
                       "engine 按检出特征计算"):
            self.assertNotIn(phrase, self.operator)

    def test_operator_html_has_neutral_selection_rule(self):
        self.assertIn("不向执行人公开", self.operator)

    def test_analyst_html_contains_everything(self):
        self.assertIn(self.r["verdict"]["verdict"].replace("_", " "),
                      self.analyst)
        self.assertIn(str(self.rx["task_id"]), self.analyst)

    def test_operator_record_schema_is_generic(self):
        self.assertIn("boundaries_left", self.operator)
        self.assertNotIn("cutoff_hz", self.operator)


class CardIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = fx.FixtureDir()
        noise = fx.render_band_noise(cls.fx.dir / "i_n.wav", cutoff_hz=20500)
        cls.flac = fx.wav_to_flak = fx.wav_to_flac(
            noise, cls.fx.dir / "i.flac")
        cls.r1 = analyze_single(str(cls.flac))
        cls.r2 = analyze_single(str(cls.flac))

    @classmethod
    def tearDownClass(cls):
        cls.fx.cleanup()

    def test_fingerprint_self_stable(self):
        c = self.r1["manual_tasks"][0]
        h1 = submission.card_fingerprint(c)
        stored = dict(c)
        stored["card_sha256"] = c["card_sha256"]
        self.assertEqual(submission.card_fingerprint(stored), h1)
        self.assertEqual(c["card_sha256"], h1)

    def test_instance_id_differs_by_round(self):
        c1 = generate_tasks(self.r1, force=("PA-001",), round_id=1)
        c2 = generate_tasks(self.r2, force=("PA-001",), round_id=2)
        i1 = next(t for t in c1 if t["task_id"] == "PA-001")["task_instance_id"]
        i2 = next(t for t in c2 if t["task_id"] == "PA-001")["task_instance_id"]
        self.assertNotEqual(i1, i2)
        self.assertTrue(i1.startswith("R01-"))
        self.assertTrue(i2.startswith("R02-"))

    def test_submission_rejects_missing_identity(self):
        c = self.r1["manual_tasks"][0]
        sub = {"task_id": c["task_id"], "file_sha256": c["file_sha256"],
               "values": {k: None for k in c["record_fields"] if k != "screenshots"}}
        with self.assertRaises(submission.SubmissionError):
            submission.merge(sub, self.r1, c)
        bad_round = dict(sub, task_instance_id="R99-WRONG", card_sha256=c["card_sha256"])
        with self.assertRaises(submission.SubmissionError):
            submission.merge(bad_round, self.r1, c)
        bad_card = dict(sub, task_instance_id=c["task_instance_id"],
                        card_sha256="f" * 64)
        with self.assertRaises(submission.SubmissionError):
            submission.merge(bad_card, self.r1, c)

    def test_fingerprint_changes_when_segment_changes(self):
        c = self.r1["manual_tasks"][0]
        h1 = c["card_sha256"]
        c2 = dict(c)
        c2["segment"] = dict(c["segment"], start_s=c["segment"]["start_s"] + 1.0)
        self.assertNotEqual(submission.card_fingerprint(c2), h1)


class ReevaluateTests(unittest.TestCase):
    def test_reevaluate_never_mutates_verdict(self):
        fxd = fx.FixtureDir()
        try:
            noise = fx.render_band_noise(fxd.dir / "r_n.wav", cutoff_hz=20500)
            flac = fx.wav_to_flac(noise, fxd.dir / "r.flac")
            r = analyze_single(str(flac))
            c = next(t for t in r["manual_tasks"] if t["task_id"] == "RX-001")
            sub = {"task_id": "RX-001", "file_sha256": c["file_sha256"],
                   "task_instance_id": c["task_instance_id"],
                   "card_sha256": c["card_sha256"],
                   "values": {k: None for k in c["record_fields"]
                              if k != "screenshots"},
                   "screenshots": [], "operator_notes": "", "deviations": ""}
            sub["values"]["cutoff_hz_left"] = 20700
            merged = submission.merge(sub, r, c)
            self.assertEqual(merged["verdict"]["verdict"],
                             r["verdict"]["verdict"])  # never auto-flipped
            reev = merged["verdict_reevaluation"]
            self.assertFalse(reev["changed"])
            self.assertEqual(reev["comparison_strength"], "indicative")
            self.assertIn("interpretation", reev)
        finally:
            fxd.cleanup()


class UvrRegistryTests(unittest.TestCase):
    def test_unpinned_blocks_separation_claim(self):
        fxd = fx.FixtureDir()
        try:
            noise = fx.render_band_noise(fxd.dir / "u_n.wav", cutoff_hz=20500)
            flac = fx.wav_to_flac(noise, fxd.dir / "u.flac")
            r = analyze_single(str(flac))
            cards = generate_tasks(r, force=("UVR-001",))
            uvr = next(c for c in cards if c["task_id"] == "UVR-001")
            self.assertTrue(uvr.get("model_unpinned"))
            self.assertFalse(uvr.get("model_pinned", False))
            blob = repr(uvr)
            self.assertNotIn("standardized-at-generation-time", blob)
        finally:
            fxd.cleanup()


if __name__ == "__main__":
    unittest.main()
