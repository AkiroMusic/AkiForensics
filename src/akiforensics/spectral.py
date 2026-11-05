"""Spectral forensics: lossy-encoder brick-wall cutoff, codec noise bed,
band-energy distribution. Works on the decoded working signal (mono float)."""

from __future__ import annotations

import numpy as np
from scipy import signal as sps


def analyze(mono: np.ndarray, sr: int, cfg: dict) -> dict:
    nper = 8192
    f, t, Sxx = sps.spectrogram(mono, sr, nperseg=nper, noverlap=nper // 2,
                                window="hann")
    avg = Sxx.mean(axis=1) + 1e-14
    avg_db = 10 * np.log10(avg)
    total = avg.sum()

    lo, hi = cfg["band_max_lo_hz"], cfg["band_max_hi_hz"]
    band = (f >= lo) & (f <= hi)
    band_max_db = float(avg_db[band].max()) if band.any() else -200.0

    # last frequency whose level stays within cliff_delta of the band max
    cliff = cfg["cliff_delta_db"]
    cutoff_hz = None
    for i in range(len(f) - 1, -1, -1):
        if f[i] > hi and avg_db[i] > band_max_db - cliff:
            cutoff_hz = float(f[i])
            break
    # content reaching Nyquist = full-band lossless, no meaningful cutoff
    if cutoff_hz is not None and cutoff_hz > sr / 2 * 0.97:
        cutoff_hz = None

    above_db, silence = None, False
    if cutoff_hz is not None:
        above = (f > cutoff_hz + 150) & (f <= min(sr / 2 * 0.995, 21950))
        if above.any():
            above_db = float(avg_db[above].mean())
            silence = above_db < cfg["digital_silence_db"] + 12

    # energy fractions
    def frac(l1: float, l2: float) -> float:
        m = (f >= l1) & (f < l2)
        return float(avg[m].sum() / total * 100.0)

    energy = {
        "pct_20_2k": frac(20, 2000),
        "pct_2k_8k": frac(2000, 8000),
        "pct_8k_12k": frac(8000, 12000),
        "pct_12k_15.5k": frac(12000, 15500),
        "pct_15.5k_20.5k": frac(15500, 20500),
        "pct_above_20.5k": frac(20500, sr / 2),
    }

    # codec noise bed: steadiness of a high band through time
    nb = (f >= cfg["noise_bed_lo_hz"]) & (f <= cfg["noise_bed_hi_hz"])
    bed_db = 10 * np.log10(Sxx[nb].mean(axis=0) + 1e-14)
    bed_std = float(bed_db.std())

    lossy_container_note = None
    wall = bool(cutoff_hz and cutoff_hz < cfg["cutoff_fake_max_hz"]
                and above_db is not None and (band_max_db - above_db) > cliff)
    if wall:
        # a wall is only suspicious for a nominally lossless container
        lossy_container_note = "lossless container with lossy-source cutoff"

    return {
        "cutoff_hz": cutoff_hz,
        "band_max_db_14_20k": round(band_max_db, 1),
        "above_cutoff_mean_db": None if above_db is None else round(above_db, 1),
        "above_cutoff_digital_silence": silence,
        "cliff_depth_db": None if cutoff_hz is None else round(band_max_db - (above_db or -200.0), 1),
        "brick_wall": wall,
        "fake_lossless_suspect": wall and lossy_container_note is not None,
        "noise_bed_std_db": round(bed_std, 2),
        "energy_fractions_pct": {k: round(v, 4) for k, v in energy.items()},
        "_plotdata": {
            "freqs": f, "avg_db": avg_db,
            "spec_db": 10 * np.log10(Sxx), "spec_t": t,
            "cutoff_hz": cutoff_hz,
        },
    }
