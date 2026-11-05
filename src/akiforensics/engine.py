"""Single-file analysis pipeline used by CLI, batch and calibrate."""

from __future__ import annotations

from pathlib import Path

from . import beatgrid, config, decode, metadata, spectral, verdict


def analyze_single(path: str | Path, cfg: dict | None = None) -> dict:
    path = str(Path(path).resolve())
    cfg = cfg or config.load()
    probe_info = decode.probe(path)
    audio = next((s for s in probe_info["streams"] if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise ValueError(f"no audio stream in {path}")

    meta = metadata.analyze(path, probe_info)
    sr, mono = decode.decode_work(path)
    spec = spectral.analyze(mono, sr, cfg["spectral"])
    beats = beatgrid.analyze(mono, sr, cfg["beatgrid"])
    verd = verdict.aggregate(meta, spec, beats, meta.get("container", ""), cfg)

    return {
        "file": {"path": path, "name": Path(path).name,
                 "size_bytes": Path(path).stat().st_size},
        "metadata": meta,
        "spectral": spec,
        "beatgrid": beats,
        "verdict": verd,
    }
