"""v0.3.x acceptance run — the 11-item checklist from GPT review round 5.

Portable: works on a clean checkout. Audio path comes from argv/env (no
hardcoded machine paths); the corpus structure is verified in a TEMP dir
initialized from the versioned template in docs/corpus/.

Usage:
  python run_acceptance.py [path-to-audio-file]
  (env AKIFORENSICS_ACCEPT_AUDIO as fallback; without audio, items run on a
   synthetic fixture and the summary marks the source as SYNTHETIC.)

Result states: PASS / FAIL / PENDING-OWNER.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import fixtures as fx  # noqa: E402
from akiforensics import config, report, submission  # noqa: E402
from akiforensics.engine import analyze_single  # noqa: E402
from akiforensics.tasks import generate_tasks  # noqa: E402

CFG = config.load()
R = []


def rec(item, state, detail):
    assert state in ("PASS", "FAIL", "PENDING-OWNER"), state
    R.append({"item": item, "state": state, "detail": detail})
    print(f"{state:<14} {item}: {detail}")


def init_corpus_structure(base: Path) -> bool:
    """Initialize + verify the corpus structure from the versioned template."""
    for sub in ("human/daw_quantized", "human/daw_unquantized", "human/loop_based",
                "human/mp3_to_flac", "ai/suno", "ai/other_generators",
                "ai/ai_post_daw", "hybrid/ai_vocals_human_instrumental",
                "hybrid/human_stems_ai_processing", "manifests"):
        (base / "corpus" / sub).mkdir(parents=True, exist_ok=True)
    for name in ("README.md",):
        src = ROOT / "docs" / "corpus" / name
        if src.exists():
            shutil.copy(src, base / "corpus" / name)
    schema = ROOT / "docs" / "corpus" / "metadata.schema.md"
    if schema.exists():
        shutil.copy(schema, base / "corpus" / "manifests" / "metadata.schema.md")
    need = ["corpus/human/daw_quantized", "corpus/ai/suno",
            "corpus/hybrid/ai_vocals_human_instrumental", "corpus/manifests",
            "corpus/README.md", "corpus/manifests/metadata.schema.md"]
    return all((base / n).exists() for n in need)


def main() -> int:
    audio = Path(sys.argv[1] if len(sys.argv) > 1
                 else os.environ.get("AKIFORENSICS_ACCEPT_AUDIO", ""))
    real = bool(audio) and audio.exists() and audio.is_file()
    out = Path(tempfile.mkdtemp(prefix="akif_accept_"))
    fxd = fx.FixtureDir()
    try:
        if real:
            src_audio = audio
            source = "REAL"
        else:
            wav = fx.render_kick_track(fxd.dir / "acc_k.wav", bpm=136,
                                       jitter_ms=3.0, wander_ms=2.0, dur=50)
            src_audio = fx.wav_to_flac(wav, fxd.dir / "acc.flac")
            source = ("SYNTHETIC (audio arg/env missing — pass a real file "
                      "for REAL acceptance evidence)")
        print(f"audio source: {source}\n")

        # ---- 1. analyze -> dual reports
        r = analyze_single(str(src_audio), CFG)
        outdir = out / "case"
        outdir.mkdir(parents=True)
        analyst = Path(report.render_html(r, outdir))
        operator = analyst.with_name("operator_tasks.html")
        rec("1. analyze_single -> dual reports",
            "PASS" if (analyst.exists() and operator.exists()) else "FAIL",
            f"verdict={r['verdict']['verdict']} (source: {source.split(' ')[0]})")

        # ---- 2/2b. level-aware operator leak audit
        ops = operator.read_text(encoding="utf-8")
        v, co = r["verdict"], r["spectral"]["cutoff_hz"]
        value_leaks = ([x for x in (v["verdict"], v["verdict"].replace("_", " "),
                                    f"{co:.0f}", "有损源指纹", "确证/推翻")
                        if x in ops] if co else [])
        r_h = analyze_single(str(src_audio), CFG, blinding_level="hypothesis")
        d_h = out / "hypo"
        d_h.mkdir(parents=True, exist_ok=True)
        report.render_html(r_h, d_h)
        ops_h = (d_h / "operator_tasks.html").read_text(encoding="utf-8")
        hyp_leaks = [x for x in ("cutoff_hz_left", "cutoff_hz_right",
                                 "wall_stable_across_subsegments",
                                 "above_wall_silence") if x in ops_h]
        indirect_ok = ("<img" not in ops and "<img" not in ops_h
                       and src_audio.stem not in ops
                       and not any(w in ops + ops_h for w in
                                   ("可改变", "证据缺口", "alternative_hypotheses")))
        rec("2. operator leak audit (value level: no engine values/verdict)",
            "PASS" if not value_leaks else "FAIL", f"leaks: {value_leaks or 'none'}")
        rec("2b. operator leak audit (hypothesis level: no target fields)",
            "PASS" if not hyp_leaks and indirect_ok else "FAIL",
            f"field leaks: {hyp_leaks or 'none'}; plots/path/analyst-wording: "
            f"{'none' if indirect_ok else 'FOUND'}; residual: segment position "
            f"visible (documented; random/control design = future work)")

        # ---- 3. human RX-001 — owner only
        rx = next(t for t in r["manual_tasks"] if t["task_id"] == "RX-001")
        rec("3. human executes RX-001 via operator_tasks.html", "PENDING-OWNER",
            "requires a real RX 12 session by the project owner; the return "
            "path below uses a clearly-labeled SIMULATED number sheet")

        # ---- 4. correct identity
        sub = {"task_id": rx["task_id"],
               "task_instance_id": rx["task_instance_id"],
               "card_sha256": rx["card_sha256"],
               "file_sha256": rx["file_sha256"],
               "values": {k: None for k in rx["record_fields"]
                          if k != "screenshots"},
               "screenshots": [], "operator_notes": "SIMULATED acceptance return",
               "deviations": ""}
        eng = r["spectral"]["cutoff_hz"]
        sub["values"]["cutoff_hz_left"] = eng
        sub["values"]["cutoff_hz_right"] = (eng or 0) + 60
        sub["values"]["wall_stable_across_subsegments"] = "yes"
        sub["values"]["lr_consistent"] = "yes"
        sub["values"]["above_wall_silence"] = "yes"
        sub["values"]["rx_version"] = "SIM-12.0"
        try:
            submission.validate(sub, rx)
            rec("4. correct instance id + card sha accepted", "PASS",
                f"instance={rx['task_instance_id']}")
        except submission.SubmissionError as e:
            rec("4. correct identity accepted", "FAIL", str(e))

        # ---- 5. rejection paths
        rejects = []
        for name, s_ in (("wrong card_sha256", dict(sub, card_sha256="f" * 64)),
                         ("wrong round", dict(sub, task_instance_id="R99-WRONG")),
                         ("missing identity",
                          {k: v2 for k, v2 in sub.items()
                           if k not in ("task_instance_id", "card_sha256")})):
            try:
                submission.validate(s_, rx)
                rejects.append(f"{name}: NOT REJECTED")
            except submission.SubmissionError:
                rejects.append(f"{name}: rejected")
        ok5 = all(r2.endswith("rejected") for r2 in rejects)
        rec("5. identity rejection paths", "PASS" if ok5 else "FAIL", str(rejects))

        # ---- 6. merge
        merged = submission.merge(sub, r, rx)
        ev = merged["human_evidence"][-1]
        rec("6. merge-submission", "PASS",
            f"evidence_revision={merged['evidence_revision']}")

        # ---- 7. indicative isolation
        rec("7. indicative never enters authoritative fusion",
            "PASS" if (ev["summary"] == "agreement_indicative"
                       and ev["comparison_strength"] == "indicative") else "FAIL",
            f"summary={ev['summary']} strength={ev['comparison_strength']}")

        # ---- 8. verdict never flipped
        rec("8. verdict never auto-flipped",
            "PASS" if (merged["verdict"]["verdict"] == r["verdict"]["verdict"]
                       and merged["verdict_reevaluation"]["changed"] is False)
            else "FAIL",
            f"{r['verdict']['verdict']} unchanged; recommendation recorded")

        # ---- 9. UVR block
        cards = generate_tasks(merged, force=("UVR-001",))
        uvr = next(c for c in cards if c["task_id"] == "UVR-001")
        stem_sub = {"task_id": "UVR-001", "file_sha256": uvr["file_sha256"],
                    "task_instance_id": uvr["task_instance_id"],
                    "card_sha256": uvr["card_sha256"], "values": {},
                    "screenshots": [], "operator_notes": "", "deviations": ""}
        try:
            submission.validate(stem_sub, uvr)
            rec("9. UVR model_unpinned blocks stem returns", "FAIL",
                "submission NOT rejected")
        except submission.SubmissionError as e:
            rec("9. UVR model_unpinned blocks stem returns", "PASS", f"rejected: {e}")

        # ---- 10. REAL post-merge re-render + footer revision parity
        m_analyst = Path(report.render_html(merged, out / "merged"))
        m_ops = m_analyst.with_name("operator_tasks.html")
        a_html = m_analyst.read_text(encoding="utf-8")
        o_html = m_ops.read_text(encoding="utf-8")
        stamp = f"evidence rev {merged['evidence_revision']}"
        both = stamp in a_html and stamp in o_html
        rec("10. post-merge dual-report re-render + revision parity",
            "PASS" if both else "FAIL",
            f"both footers carry '{stamp}': {both}")

        # ---- 11. corpus portability (clean-checkout simulation in temp dir)
        ok11 = init_corpus_structure(out)
        rec("11. corpus structure from versioned template (temp dir)",
            "PASS" if ok11 else "FAIL",
            "human/ai/hybrid/manifests initialized from docs/corpus/ — "
            "reproducible on a clean checkout; audio stays local")
    finally:
        fxd.cleanup()
        shutil.rmtree(out, ignore_errors=True)

    print("\n==== ACCEPTANCE SUMMARY ====")
    for st in ("PASS", "FAIL", "PENDING-OWNER"):
        n = sum(1 for x in R if x["state"] == st)
        if n:
            print(f"{st}: {n}")
    print("audio source:", "REAL" if real else "SYNTHETIC")
    out_json = ROOT / "acceptance_results.json"
    json.dump(R, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"results written: {out_json}")
    return 0 if not any(x["state"] == "FAIL" for x in R) else 1


if __name__ == "__main__":
    sys.exit(main())
