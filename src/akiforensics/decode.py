"""Audio decoding helpers backed by ffmpeg/ffprobe CLI."""

from __future__ import annotations

import json
import shutil
import subprocess

import numpy as np


class DecodeError(RuntimeError):
    pass


def _bin(name: str) -> str:
    p = shutil.which(name)
    if p is None:
        raise DecodeError(f"{name} not found on PATH; ffmpeg is required")
    return p


def probe(path: str) -> dict:
    """ffprobe JSON: streams + format tags."""
    cmd = [_bin("ffprobe"), "-v", "error", "-show_streams", "-show_format",
           "-print_format", "json", path]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise DecodeError(proc.stderr.decode("utf-8", "replace")[-500:])
    return json.loads(proc.stdout.decode("utf-8", "replace"))


def decode_pcm(path: str, sample_rate: int | None = None,
               channels: int | None = None,
               sample_fmt: str = "s16le") -> tuple[int, np.ndarray]:
    """Decode first audio stream to raw interleaved PCM bytes.

    Returns (sample_rate, flat_int8-viewable buffer as np.ndarray of uint8).
    sample_rate/channels=None keeps the source layout (needed for FLAC MD5).
    """
    cmd = [_bin("ffmpeg"), "-v", "error", "-i", path, "-map", "0:a:0",
           "-f", sample_fmt]
    if sample_rate is not None:
        cmd += ["-ar", str(sample_rate)]
    if channels is not None:
        cmd += ["-ac", str(channels)]
    cmd.append("-")
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise DecodeError(proc.stderr.decode("utf-8", "replace")[-800:])
    return proc.stdout


def decode_work(path: str, sample_rate: int = 44100) -> tuple[int, np.ndarray]:
    """Decode to float64 mono at `sample_rate` for analysis pipelines."""
    raw = decode_pcm(path, sample_rate=sample_rate, channels=2, sample_fmt="s16le")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    x = x.reshape(-1, 2).mean(axis=1)
    return sample_rate, x


def decode_errors(path: str) -> list[str]:
    """Collect decoder warning lines (broken frames etc.) from a full decode pass."""
    cmd = [_bin("ffmpeg"), "-v", "info", "-i", path, "-map", "0:a", "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    lines = proc.stderr.decode("utf-8", "replace").splitlines()
    keys = ("error", "invalid", "fail", "corrupt")
    return [ln.strip() for ln in lines if any(k in ln.lower() for k in keys)][:10]
