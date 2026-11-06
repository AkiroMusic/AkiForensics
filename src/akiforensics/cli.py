"""CLI entry: `akiforensics analyze <file|dir>` / `akiforensics calibrate`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, report
from .engine import analyze_single


def _iter_audio(path: Path):
    if path.is_file():
        yield path
    else:
        for p in sorted(path.rglob("*")):
            if p.suffix.lower() in report.AUDIO_EXTS:
                yield p


def cmd_analyze(args) -> int:
    cfg = config.load(args.config)
    target = Path(args.path)
    if not target.exists():
        print(f"error: path not found: {target}")
        return 2
    files = list(_iter_audio(target))
    if not files:
        print(f"error: no audio files under {target}")
        return 2

    batch = len(files) > 1
    outroot = Path(args.out) if args.out else Path("forensics_out")
    results = []
    for fp in files:
        outdir = outroot / fp.stem if batch else outroot / (fp.stem + "_report")
        try:
            r = analyze_single(fp, cfg, blinding_level=args.blinding,
                               force_tasks=tuple(args.task or ()))
        except Exception as e:  # keep batch running on a bad file
            print(f"[SKIP] {fp.name}: {e}")
            continue
        results.append(r)
        report.write_json(r, outdir / "report.json")
        if not batch or args.full:
            report.render_html(r, outdir)
        print(report.console_summary(r))

    if batch and results:
        csv_path = report.write_batch_summary(results, outroot)
        print(f"batch summary: {csv_path}  index: {outroot / 'index.html'}")
    return 0


def cmd_merge_submission(args) -> int:
    """Merge a returned human task sheet into an existing report.json."""
    from . import submission
    rpath = Path(args.report)
    analysis = json.loads(rpath.read_text(encoding="utf-8"))
    sub = submission.load_submission(args.submission)
    card = next((t for t in analysis.get("manual_tasks", [])
                 if t["task_id"] == sub.get("task_id")), None)
    if card is None:
        print(f"error: task {sub.get('task_id')} not in this report's manual_tasks")
        return 2
    merged = submission.merge(sub, analysis, card)
    report.write_json(merged, rpath)
    try:
        report.render_html(merged, rpath.parent)  # keep HTML in sync with JSON
    except Exception as e:
        print(f"note: HTML regeneration failed ({e}); JSON is updated")
    ev = merged["human_evidence"][-1]
    print(f"merged {ev['task_id']}: summary={ev['summary']}")
    for c in ev["comparisons"]:
        print(f"  {c['field']}: engine={c['engine']} human={c['human']} "
              f"tol={c['tolerance']} -> {c['result']}")
    if ev["summary"] == "contradiction":
        print("  NOTE: contradiction recorded — issue a follow-up task "
              "(different segment / second tool); never overwrite either side.")
    return 0


def cmd_calibrate(args) -> int:
    from . import calibrate
    calibrate.run(args.human, args.ai, config.load(args.config))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="akiforensics",
                                 description="AI-generated music forensics")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="analyze a file or a directory (batch)")
    a.add_argument("path", help="audio file or directory")
    a.add_argument("--out", help="output directory (default ./forensics_out)")
    a.add_argument("--config", help="thresholds.toml override")
    a.add_argument("--full", action="store_true",
                   help="render per-file HTML in batch mode")
    a.add_argument("--blinding", choices=("value", "hypothesis", "none"),
                   default="value", help="task-card blinding level (default value)")
    a.add_argument("--task", action="append",
                   help="force stage-2 task cards (repeatable: --task UVR-001)")
    a.set_defaults(func=cmd_analyze)

    m = sub.add_parser("merge-submission",
                       help="merge a returned human task sheet into report.json")
    m.add_argument("report", help="path to report.json")
    m.add_argument("submission", help="path to the returned submission JSON")
    m.set_defaults(func=cmd_merge_submission)

    c = sub.add_parser("calibrate",
                       help="EXPERIMENTAL: suggest thresholds from reference corpora")
    c.add_argument("--human", required=True, help="directory of known-human tracks")
    c.add_argument("--ai", required=True, help="directory of known-AI tracks")
    c.add_argument("--config", help="thresholds.toml override")
    c.set_defaults(func=cmd_calibrate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
