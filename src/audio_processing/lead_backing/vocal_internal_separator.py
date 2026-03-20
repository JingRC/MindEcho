from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple


def _load_audio_mono(path: str) -> Tuple[object, int]:
    import numpy as np

    try:
        import soundfile as sf

        data, sr = sf.read(path, always_2d=True)
        if data.ndim == 2 and data.shape[1] > 1:
            data = data.mean(axis=1)
        else:
            data = data.squeeze()
        return np.asarray(data, dtype=np.float32), int(sr)
    except Exception:
        import wave

        with wave.open(path, "rb") as wf:
            sr = wf.getframerate()
            n = wf.getnframes()
            ch = wf.getnchannels()
            raw = wf.readframes(n)
        arr = np.frombuffer(raw, dtype=np.int16)
        if ch > 1:
            arr = arr.reshape(-1, ch).mean(axis=1)
        return arr.astype(np.float32) / 32768.0, int(sr)


def _save_audio(path: str, data, sr: int) -> None:
    import numpy as np

    out = np.asarray(data, dtype=np.float32)
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 1.0:
        out = out / peak
    try:
        import soundfile as sf

        sf.write(path, out, int(sr))
    except Exception:
        import wave

        pcm = np.int16(np.clip(out, -1.0, 1.0) * 32767)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(sr))
            wf.writeframes(pcm.tobytes())


def _band_split(x, sr: int):
    """Heuristic split for lead-like / backing-like components.

    - lead_like: emphasizes vocal formant area (roughly 150-2200 Hz)
    - residual:  x - lead_like
    """
    import numpy as np
    from scipy.signal import butter, filtfilt

    if len(x) < 64:
        return x.copy(), np.zeros_like(x), np.zeros_like(x)

    nyq = max(1.0, sr * 0.5)
    low = max(20.0, min(150.0, nyq * 0.95))
    high = max(low + 20.0, min(2200.0, nyq * 0.98))
    if high <= low + 1.0:
        high = min(nyq * 0.98, low + 100.0)

    b_bp, a_bp = butter(4, [low / nyq, high / nyq], btype="band")
    lead_like = filtfilt(b_bp, a_bp, x).astype(np.float32)
    residual = (x - lead_like).astype(np.float32)

    b_lp, a_lp = butter(3, min(300.0 / nyq, 0.95), btype="low")
    b_hp, a_hp = butter(3, min(1200.0 / nyq, 0.95), btype="high")
    backing_low = filtfilt(b_lp, a_lp, residual).astype(np.float32)
    backing_high = filtfilt(b_hp, a_hp, residual).astype(np.float32)
    return lead_like, backing_low, backing_high


def _spectral_mask_split(x, sr: int):
    """Split vocal stem into lead-like / backing-like components.

    Method: STFT + time-median background estimate (REPET-like) + soft mask.
    This is still heuristic, but performs better than pure band split for
    dense vocal harmonies and avoids near-silent backing in many cases.
    """
    import numpy as np

    if x is None:
        return None
    arr = np.asarray(x, dtype=np.float32).reshape(-1)
    if arr.size < 1024:
        return None

    try:
        from scipy import signal
        from scipy.ndimage import median_filter
    except Exception:
        return None

    nperseg = 2048
    noverlap = 1536
    hop = max(1, nperseg - noverlap)
    try:
        _f, _t, zxx = signal.stft(
            arr,
            fs=int(sr),
            nperseg=nperseg,
            noverlap=noverlap,
            boundary="zeros",
            padded=True,
            window="hann",
        )
    except Exception:
        return None
    if zxx is None or zxx.size == 0:
        return None

    mag = np.abs(zxx).astype(np.float32)
    eps = 1e-9
    p = 2.0

    # HPSS: harmonic tends to long horizontal ridges, rap/transients/consonants
    # tend to vertical structures. This is more suitable for "high-note + rap"
    # overlap than pure band split.
    t_ks_h = int(max(9, round((0.90 * sr) / hop)))
    if (t_ks_h % 2) == 0:
        t_ks_h += 1
    f_ks_p = 31
    if (f_ks_p % 2) == 0:
        f_ks_p += 1

    harm_med = median_filter(mag, size=(1, t_ks_h), mode="nearest").astype(np.float32)
    perc_med = median_filter(mag, size=(f_ks_p, 1), mode="nearest").astype(np.float32)
    harm_pow = np.power(harm_med, p)
    perc_pow = np.power(perc_med, p)
    den_hp = harm_pow + perc_pow + eps
    harm_mask = harm_pow / den_hp
    perc_mask = perc_pow / den_hp

    harmonic_stft = zxx * harm_mask
    percussive_stft = zxx * perc_mask
    residual_stft = zxx - harmonic_stft - percussive_stft

    # Split harmonic part by F0 region: high-register singing into lead,
    # lower-register talking/rap-like voiced content into backing.
    freqs = np.linspace(0.0, sr * 0.5, num=mag.shape[0], dtype=np.float32)
    split_hz = 320.0
    trans_hz = 55.0
    hi_w = 1.0 / (1.0 + np.exp(-(freqs - split_hz) / max(8.0, trans_hz)))
    hi_w = hi_w.reshape(-1, 1).astype(np.float32)
    lo_w = (1.0 - hi_w).astype(np.float32)

    lead_harm = harmonic_stft * hi_w
    backing_harm = harmonic_stft * lo_w

    # Residual is mostly assigned to backing to preserve rap articulations.
    lead_stft = lead_harm + (0.20 * residual_stft)
    backing_stft = backing_harm + percussive_stft + (0.80 * residual_stft)

    try:
        _, lead = signal.istft(
            lead_stft,
            fs=int(sr),
            nperseg=nperseg,
            noverlap=noverlap,
            input_onesided=True,
            boundary=True,
            window="hann",
        )
        _, backing = signal.istft(
            backing_stft,
            fs=int(sr),
            nperseg=nperseg,
            noverlap=noverlap,
            input_onesided=True,
            boundary=True,
            window="hann",
        )
    except Exception:
        return None

    n = arr.shape[0]
    if lead.shape[0] < n:
        lead = np.pad(lead, (0, n - lead.shape[0]))
    if backing.shape[0] < n:
        backing = np.pad(backing, (0, n - backing.shape[0]))
    lead = lead[:n].astype(np.float32)
    backing = backing[:n].astype(np.float32)

    # Energy rebalance: avoid near-silent backing in challenging songs.
    mix_rms = float(np.sqrt(np.mean(arr * arr) + eps))
    lead_rms = float(np.sqrt(np.mean(lead * lead) + eps))
    backing_rms = float(np.sqrt(np.mean(backing * backing) + eps))

    # If backing is too weak, blend residual/complement to recover audible rap.
    if backing_rms < (mix_rms * 0.06):
        residual = (arr - lead).astype(np.float32)
        backing = (0.45 * backing + 0.55 * residual).astype(np.float32)
        backing_rms = float(np.sqrt(np.mean(backing * backing) + eps))

    # If lead is too weak, reinforce from residual complement.
    if lead_rms < (mix_rms * 0.18):
        lead = (arr - backing).astype(np.float32)

    # Keep simple consistency.
    summ = lead + backing
    err = arr - summ
    backing = (backing + 0.8 * err).astype(np.float32)
    lead = (arr - backing).astype(np.float32)

    return lead, backing


def separate_vocals_internal(vocals_path: str, expected_backing_count: int = 0) -> Dict[str, object]:
    expected = max(0, int(expected_backing_count or 0))
    candidates: List[str] = []

    try:
        x, sr = _load_audio_mono(vocals_path)
        lead_like = None
        backing_low = None
        backing_high = None

        # Prefer spectral-mask split; fallback to original band split.
        spec = _spectral_mask_split(x, sr)
        if spec is not None:
            lead_like, backing_low = spec
            backing_high = (x.astype(lead_like.dtype) - lead_like - backing_low).astype(lead_like.dtype)
            engine = "spectral-mask-repet"
        else:
            lead_like, backing_low, backing_high = _band_split(x, sr)
            engine = "heuristic-band-split"

        base = Path(vocals_path)
        out_dir = base.parent if base.parent.name == "_lead_backing_stage2" else (base.parent / "_lead_backing_stage2")
        out_dir.mkdir(parents=True, exist_ok=True)

        lead_path = str((out_dir / f"{base.stem}_lead.wav").resolve())
        _save_audio(lead_path, lead_like, sr)
        candidates.append(lead_path)

        if expected > 0:
            b1_path = str((out_dir / f"{base.stem}_backing_1.wav").resolve())
            _save_audio(b1_path, backing_low, sr)
            candidates.append(b1_path)
        if expected > 1:
            b2_path = str((out_dir / f"{base.stem}_backing_2.wav").resolve())
            _save_audio(b2_path, backing_high, sr)
            candidates.append(b2_path)

        # Basic diagnostics for downstream display and troubleshooting.
        try:
            import numpy as np

            def _rms(a) -> float:
                a = np.asarray(a, dtype=np.float32)
                if a.size <= 0:
                    return 0.0
                return float(np.sqrt(np.mean(a * a)))

            rms_mix = _rms(x)
            rms_lead = _rms(lead_like)
            rms_b1 = _rms(backing_low)
            rms_b2 = _rms(backing_high)
        except Exception:
            rms_mix = rms_lead = rms_b1 = rms_b2 = 0.0

        return {
            "ok": True,
            "engine": engine,
            "expected_backing_count": expected,
            "candidate_tracks": candidates,
            "output_dir": str(out_dir),
            "diagnostics": {
                "rms_mix": rms_mix,
                "rms_lead": rms_lead,
                "rms_backing_1": rms_b1,
                "rms_backing_2": rms_b2,
            },
        }
    except Exception as e:
        return {
            "ok": False,
            "engine": "heuristic-band-split",
            "expected_backing_count": expected,
            "candidate_tracks": [vocals_path],
            "error": str(e),
        }
