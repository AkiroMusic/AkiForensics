"""Single-file analysis pipeline used by CLI, batch and calibrate."""

from __future__ import annotations

from pathlib import Path

from . import beatgrid, config, decode, metadata, spectral, tasks, verdict


def analyze_single(path: str | Path, cfg: dict | None = None,
                   generate_task_cards: bool = True,
                   blinded_tasks: bool = True,
                   blinding_level: str = "value",
                   force_tasks: tuple[str, ...] = ()) -> dict:
    path = str(Path(path).resolve())
    cfg = cfg or config.load()
    probe_info = decode.probe(path)
    audio = next((s for s in probe_info["streams"] if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise ValueError(f"no audio stream in {path}")

    meta = metadata.analyze(path, probe_info)
    # NATIVE rate + float working copies — resampling or 16-bit truncation
    # would manufacture artifacts the forensic legs would then measure.
    sr_native = int(audio["sample_rate"])
    sr, stereo, mono = decode.decode_work(path, sample_rate=sr_native,
                                          channels=audio.get("channels"))
    spec = spectral.analyze(mono, sr, cfg["spectral"])
    beats = beatgrid.analyze(mono, sr, cfg["beatgrid"])
    verd = verdict.aggregate(meta, spec, beats, meta.get("container", ""), cfg)

    result = {
        "file": {"path": path, "name": Path(path).name,
                 "size_bytes": Path(path).stat().st_size,
                 "duration_s": meta.get("duration_s"),
                 "sha256": tasks._sha256(path)},
        "metadata": meta,
        "spectral": spec,
        "beatgrid": beats,
        "verdict": verd,
        "analysis_revision": 1,
        "evidence_revision": 0,
        "channels_meta": {
            "channel_count": int(audio.get("channels") or 1),
            "layout": audio.get("channel_layout") or "unknown",
            "downmix_method": ("equal-mean-2ch" if (audio.get("channels") or 1) == 2
                               else "experimental-equal-mean-multichannel"),
            "multichannel_support": ("experimental" if (audio.get("channels") or 1) > 2
                                      else "stable"),
        },
        "_stereo": stereo,
    }
    if generate_task_cards:
        result["manual_tasks"] = tasks.generate_tasks(
            result, blinded=blinded_tasks, blinding_level=blinding_level,
            force=force_tasks)
    return result
