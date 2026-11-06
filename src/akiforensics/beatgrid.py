"""Beat-grid timing forensics (the discriminative leg).

Pipeline: kick isolation (30-130 Hz SOS bandpass) -> onset envelope -> candidate
peaks -> coarse/fine RANSAC tempo+phase scan -> linear grid fit with outlier
rejection -> cross-correlation sub-ms refinement -> residual statistics.

A quantized DAW render places every kick at integer sample positions of a
constant tempo: residuals sit at the measurement noise floor (<~0.2 ms) and a
large fraction within +-0.3 ms of an exact grid. Generative models wander
(typically 2-40 ms) and cannot satisfy any constant grid.
"""

from __future__ import annotations

import numpy as np
from scipy import signal as sps

EPS = 1e-12


def _kick_candidates(mono: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    sos = sps.butter(4, [30, 130], "bandpass", fs=sr, output="sos")
    kb = sps.sosfiltfilt(sos, mono)
    env = np.sqrt(np.convolve(kb ** 2, np.ones(128) / 128, "same"))
    pk, props = sps.find_peaks(env, distance=int(0.24 * sr),
                               height=np.percentile(env, 85))
    return pk / sr, (kb, props["peak_heights"])


def _scan_grid(kt: np.ndarray, bpm_lo: float, bpm_hi: float, step_bpm: float,
               n_phase_bins: int = 64) -> tuple[float, float]:
    """Coarse RANSAC: for each tempo, histogram kick times modulo the period;
    the dominant phase bin gives (T, phase) with the most matched kicks."""
    best = (None, None, -1)
    for bpm in np.arange(bpm_lo, bpm_hi, step_bpm):
        T = 60.0 / bpm
        r = (kt + T / 2) % T
        hist, edges = np.histogram(r, bins=n_phase_bins, range=(0, T))
        i = int(hist.argmax())
        cnt = int(hist[i])
        if cnt > best[2]:
            best = (T, float((edges[i] + edges[i + 1]) / 2 - T / 2), cnt)
    T, ph, _ = best
    return T, ph


def _fit_grid(kt: np.ndarray, T: float, ph: float, tol_ms: float = 35.0,
              reject_ms: float = 6.0):
    for _ in range(6):
        r = np.abs(((kt - ph + T / 2) % T) - T / 2)
        sel = r < tol_ms
        ts, ks = kt[sel], np.round((kt[sel] - ph) / T)
        for _ in range(5):
            T, ph = np.polyfit(ks, ts, 1)
            res = (ts - (ph + ks * T)) * 1000.0
            ok = np.abs(res) < reject_ms
            if ok.all():
                break
            ts, ks = ts[ok], ks[ok]
        if len(ts) < 10:
            break
    return ts, ks, T, ph


def _xcorr_refine(kb: np.ndarray, sr: int, ks: np.ndarray,
                  T: float, ph: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Re-measure each beat by waveform alignment against a reference kick.

    Segments are cut at GRID positions (not detected onsets): a segment then
    contains its kick at offset win_pre + (true_time - grid_time), so the
    correlation lag isolates the true timing jitter. Cutting at detected
    onsets would cancel the jitter and collapse residuals to ~0.
    Returns (beat_indices, refined_times, correlation_qualities).
    """
    win_pre, win_post = int(0.02 * sr), int(0.13 * sr)
    segs, ks_ok = [], []
    for k in ks:
        g = ph + k * T
        i0 = int(g * sr) - win_pre
        seg = kb[i0:i0 + win_pre + win_post]
        if len(seg) == win_pre + win_post:
            segs.append(seg)
            ks_ok.append(k)
    if len(segs) < 10:
        return np.asarray(ks), (ph + np.asarray(ks) * T), np.array([])
    segs = np.asarray(segs)
    ks_ok = np.asarray(ks_ok)
    ref = segs[int(np.argmax([np.abs(s).max() for s in segs]))]
    ref_n = np.sqrt(np.sum(ref ** 2)) + EPS
    lags, quals = [], []
    for s in segs:
        c = sps.correlate(s, ref, mode="full", method="fft")
        c /= np.sqrt(np.sum(s ** 2)) * ref_n
        mid = len(ref) - 1
        lo, hi = mid - int(0.01 * sr), mid + int(0.01 * sr)
        j = lo + int(np.argmax(c[lo:hi]))
        if 1 <= j < len(c) - 1:
            y0, y1, y2 = c[j - 1], c[j], c[j + 1]
            d = (y0 - y2) / (2 * (y0 - 2 * y1 + y2) + EPS)
            lags.append((j - mid + d) / sr * 1000.0)
            quals.append(c[j])
    lags, quals = np.asarray(lags), np.asarray(quals)
    good = quals > 0.6
    if good.sum() < 10:
        return ks_ok, (ph + ks_ok * T), quals
    return ks_ok[good], (ph + ks_ok[good] * T) + lags[good] / 1000.0, quals[good]


def _select_main_cluster(kt: np.ndarray, kh: np.ndarray, T: float,
                         tol_s: float = 0.035) -> np.ndarray:
    """Main-kick cluster selection for broken kick patterns (two-step etc.).

    Kicks at different structural positions of a bar (downbeat vs syncopated
    ghost kicks) must NOT be mixed into one grid fit: in a DAW render each
    position is sample-locked but at a different phase, so mixing inflates
    residuals and would fake timing variation. Cluster by phase modulo the
    beat period, weighted by kick strength; the strongest coherent cluster is
    the main kick (downbeat). Any coherent cluster works for the verdict —
    quantized positions stay locked wherever they sit.
    """
    nbins = 128
    hist = np.zeros(nbins)
    idx = (((kt + T / 2) % T) / T * nbins).astype(int) % nbins
    for i, h in zip(idx, kh):
        hist[i] += h
    b = int(hist.argmax())
    center = (b + 0.5) / nbins * T - T / 2
    r = np.abs(((kt - center + T / 2) % T) - T / 2)
    return kt[r < tol_s]


def analyze(mono: np.ndarray, sr: int, cfg: dict) -> dict:
    duration = len(mono) / sr
    kt_all, (kb, kh) = _kick_candidates(mono, sr)
    na = {"applicable": False, "reason": None}

    if len(kt_all) < max(20, cfg["min_kicks"] // 2):
        na["reason"] = f"too few kick candidates ({len(kt_all)})"
        return na

    T, ph = _scan_grid(kt_all, 60.0, 200.0, 0.25)
    # fine scan +-0.5 % around coarse tempo
    bpm0 = 60.0 / T
    T, ph = _scan_grid(kt_all, bpm0 * 0.995, bpm0 * 1.005, 0.002, n_phase_bins=160)

    # main-kick cluster selection (prevents mixing structural positions in
    # broken patterns; harmless for house-style every-beat kicks)
    kt = _select_main_cluster(kt_all, kh, T)
    mode = "main-cluster"
    if len(kt) < cfg.get("min_kicks_cluster", 24):
        kt = kt_all
        mode = "all"
    if len(kt) < 10:
        na["reason"] = "no coherent kick cluster"
        return na

    ts, ks, T, ph = _fit_grid(kt, T, ph)
    if len(ts) < 10:
        na["reason"] = "grid fit collapsed"
        return na

    ks_r, t_ref, quals = _xcorr_refine(kb, sr, ks, T, ph)
    for _ in range(5):
        T2, p2 = np.polyfit(ks_r, t_ref, 1)
        res = (t_ref - (p2 + ks_r * T2)) * 1000.0
        ok = np.abs(res) < 6.0
        if ok.all():
            break
        ks_r, t_ref = ks_r[ok], t_ref[ok]
    T2, p2 = np.polyfit(ks_r, t_ref, 1)
    res = (t_ref - (p2 + ks_r * T2)) * 1000.0
    bpm_grid = 60.0 / T2
    # With main-kick-only fitting the grid may sit on a sub-harmonic (e.g.
    # downbeats on a half-bar grid). Fold into the musical range [90, 180) for
    # reporting and the integer-BPM distance; residuals are unaffected.
    bpm = float(bpm_grid)
    while bpm < 90.0:
        bpm *= 2.0
    while bpm >= 180.0:
        bpm /= 2.0
    span = (ks_r.max() - ks_r.min()) * T2
    coverage = span / duration if duration else 0.0
    t_abs = p2 + ks_r * T2

    # local tempo drift: per-20s-window linear fit -> BPM curve
    local_bpms = []
    for w0 in np.arange(t_abs.min(), max(t_abs.max() - 20.0, t_abs.min()), 20.0):
        m = (t_abs >= w0) & (t_abs < w0 + 20.0)
        if m.sum() >= 8:
            Tw, _ = np.polyfit(ks_r[m], t_abs[m], 1)
            local_bpms.append(60.0 / Tw)
    drift_bpm = float(max(local_bpms) - min(local_bpms)) if len(local_bpms) >= 2 else 0.0

    # confidence: waveform-match quality + share of expected beats actually found
    onset_conf = float(np.mean(quals)) if len(quals) else None
    expected = int(round(span / T2)) + 1 if span > 0 else 0
    hit_rate = float(len(ks_r) / expected) if expected else None

    ma = np.convolve(res, np.ones(8) / 8, "same")
    dist_int = min(abs(bpm - b) for b in cfg.get("common_edm_bpm", []))

    applicable = len(ks_r) >= (cfg["min_kicks"] if mode == "all" else cfg.get("min_kicks_cluster", 24)) \
        and coverage >= cfg["min_coverage"]
    out = {
        "applicable": bool(applicable),
        "reason": None if applicable else (
            f"insufficient beats ({len(ks_r)})"
            if len(ks_r) < (cfg["min_kicks"] if mode == "all" else cfg.get("min_kicks_cluster", 24))
            else f"grid coverage too low ({coverage:.2f} < {cfg['min_coverage']})"),
        "kick_selection": {"mode": mode, "n_candidates": int(len(kt_all)),
                           "n_selected": int(len(kt))},
        "bpm": round(float(bpm), 4),
        "bpm_grid_raw": round(float(bpm_grid), 4),
        "bpm_integer_distance": round(float(dist_int), 3),
        "n_beats_refined": int(len(ks_r)),
        "coverage": round(float(coverage), 3),
        "residual_std_ms": round(float(res.std()), 3),
        "residual_max_ms": round(float(np.abs(res).max()), 3),
        "pct_within_0.3ms": round(float(np.mean(np.abs(res) < 0.3) * 100), 1),
        "pct_within_1ms": round(float(np.mean(np.abs(res) < 1.0) * 100), 1),
        "pct_within_2ms": round(float(np.mean(np.abs(res) < 2.0) * 100), 1),
        "wander_8beat_range_ms": round(float(ma.max() - ma.min()), 3),
        "local_bpm_drift": round(drift_bpm, 4),
        "onset_confidence": None if onset_conf is None else round(onset_conf, 3),
        "grid_hit_rate": None if hit_rate is None else round(hit_rate, 3),
        "_plotdata": {"beat_index": ks_r, "residual_ms": res,
                      "beat_times": np.round(t_abs, 4)},
    }
    return out
