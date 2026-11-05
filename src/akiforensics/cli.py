"""CLI entry: `akiforensics analyze <file|dir>` / `akiforensics calibrate`."""

from __future__ import annotations

import argparse
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
            r = analyze_single(fp, cfg)
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
    a.set_defaults(func=cmd_analyze)

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
