"""Single-file analysis pipeline used by CLI, batch and calibrate."""

from __future__ import annotations

from pathlib import Path

from . import beatgrid, config, decode, metadata, spectral, tasks, verdict


def analyze_single(path: str | Path, cfg: dict | None = None,
                   generate_task_cards: bool = True,
                   blinded_tasks: bool = True,
                   force_tasks: tuple[str, ...] = ()) -> dict:
    path = str(Path(path).resolve())
    cfg = cfg or config.load()
    probe_info = decode.probe(path)
    audio = next((s for s in probe_info["streams"] if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise ValueError(f"no audio stream in {path}")

    meta = metadata.analyze(path, probe_info)
    # NATIVE rate for the working signal — resampling manufactures artifacts
    # the forensic legs would then measure.
    sr_native = int(audio["sample_rate"])
    sr, mono = decode.decode_work(path, sample_rate=sr_native)
    spec = spectral.analyze(mono, sr, cfg["spectral"])
    beats = beatgrid.analyze(mono, sr, cfg["beatgrid"])
    verd = verdict.aggregate(meta, spec, beats, meta.get("container", ""), cfg)

    result = {
        "file": {"path": path, "name": Path(path).name,
                 "size_bytes": Path(path).stat().st_size,
                 "duration_s": meta.get("duration_s")},
        "metadata": meta,
        "spectral": spec,
        "beatgrid": beats,
        "verdict": verd,
    }
    if generate_task_cards:
        result["manual_tasks"] = tasks.generate_tasks(
            result, blinded=blinded_tasks, force=force_tasks)
    return result
