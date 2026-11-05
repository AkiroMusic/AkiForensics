"""Synthetic audio fixtures: render known-property tracks for regression tests."""

from __future__ import annotations

import subprocess
import shutil
import tempfile
from pathlib import Path

import numpy as np

SR = 44100


def _kick(t0: np.ndarray, sr: int, n: int) -> np.ndarray:
    """Decaying 55 Hz sine bursts centered at times t0 (seconds)."""
    y = np.zeros(n)
    tail = int(0.25 * sr)
    tt = np.arange(tail) / sr
    burst = np.sin(2 * np.pi * 55 * tt) * np.exp(-tt / 0.06)
    for t in t0:
        i0 = int(round(t * sr))
        if 0 <= i0 and i0 + tail <= n:
            y[i0:i0 + tail] += burst
    return y


def render_kick_track(path: Path, bpm: float = 128.0, dur: float = 60.0,
                      jitter_ms: float = 0.0, wander_ms: float = 0.0,
                      seed: int = 7) -> Path:
    """Kick grid at `bpm`. jitter_ms = per-hit gaussian offset; wander_ms =
    amplitude of a slow sinusoidal timing drift (generative-style)."""
    rng = np.random.default_rng(seed)
    sr = SR
    n = int(dur * sr)
    T = 60.0 / bpm
    t0 = np.arange(T / 2, dur - 0.3, T)
    exact = np.round(t0 * sr) / sr                      # sample-locked grid
    t0s = exact.copy()
    if jitter_ms:
        t0s = t0s + rng.normal(0, jitter_ms / 1000.0, len(t0s))
    if wander_ms:
        t0s = t0s + (wander_ms / 1000.0) * np.sin(2 * np.pi * t0s / 9.0)
    y = _kick(np.clip(t0s, 0, dur - 0.3), sr, n)
    y += rng.normal(0, 3e-3, n)                         # noise floor
    x = np.stack([y, y], axis=1)
    x = np.clip(x, -1, 1)
    pcm = (x * 32767).astype("<i2")
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def render_band_noise(path: Path, cutoff_hz: float | None = None,
                      dur: float = 10.0, sr: int = SR) -> Path:
    """Flat-spectrum noise; brick-wall lowpassed at cutoff_hz if given."""
    rng = np.random.default_rng(11)
    n = int(dur * sr)
    y = rng.normal(0, 0.1, n)
    if cutoff_hz is not None:
        Y = np.fft.rfft(y)
        f = np.fft.rfftfreq(n, 1 / sr)
        Y[f > cutoff_hz] = 0
        y = np.fft.irfft(Y, n)
    x = np.stack([y, y], axis=1)
    x = np.clip(x / np.abs(x).max(), -1, 1)
    pcm = (x * 32000).astype("<i2")
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def wav_to_flac(wav_path: Path, flac_path: Path, tags: dict | None = None) -> Path:
    cmd = [shutil.which("ffmpeg"), "-y", "-v", "error", "-i", str(wav_path)]
    for k, v in (tags or {}).items():
        cmd += ["-metadata", f"{k}={v}"]
    cmd.append(str(flac_path))
    subprocess.run(cmd, check=True, capture_output=True)
    return flac_path


class FixtureDir:
    """Context manager handing out a fresh temp dir with rendered fixtures."""

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="akiforensics_fixtures_"))

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)
