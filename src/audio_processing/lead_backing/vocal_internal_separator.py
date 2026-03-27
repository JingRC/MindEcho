from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .audio_io import load_audio_mono


def _normalize_quality_mode(mode: str) -> str:
    m = str(mode or "balanced").strip().lower()
    if m not in ("fast", "balanced", "quality"):
        return "balanced"
    return m


def _load_audio_mono(path: str) -> Tuple[object, int]:
    return load_audio_mono(path)


def _save_audio(path: str, data, sr: int) -> None:
    import numpy as np

    out = np.asarray(data, dtype=np.float32)
    if out.ndim == 1:
        out_save = out
        channels = 1
    elif out.ndim == 2:
        out_save = out
        channels = int(out.shape[1])
    else:
        out_save = np.asarray(out).reshape(-1)
        channels = 1
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 1.0:
        out_save = out_save / peak
    try:
        import soundfile as sf

        sf.write(path, out_save, int(sr))
    except Exception:
        import wave

        # wave fallback keeps compatibility for mono and stereo output.
        if channels > 2:
            arr = np.asarray(out_save, dtype=np.float32)
            if arr.ndim == 2:
                arr = arr.mean(axis=1)
            pcm = np.int16(np.clip(arr, -1.0, 1.0) * 32767)
            channels = 1
        elif channels == 2:
            arr = np.asarray(out_save, dtype=np.float32)
            if arr.ndim == 1:
                arr = np.stack([arr, arr], axis=1)
            pcm = np.int16(np.clip(arr, -1.0, 1.0) * 32767)
        else:
            arr = np.asarray(out_save, dtype=np.float32).reshape(-1)
            pcm = np.int16(np.clip(arr, -1.0, 1.0) * 32767)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(int(channels))
            wf.setsampwidth(2)
            wf.setframerate(int(sr))
            wf.writeframes(pcm.tobytes())


def _try_model_split_spleeter(vocals_path: str, quality_mode: str = "balanced"):
    """Try model-based vocal-internal split using Spleeter 2stems.

    Returns (lead_like, backing_like, sr, engine) on success, else None.
    """
    mode = _normalize_quality_mode(quality_mode)
    if mode == "fast":
        return None
    try:
        import numpy as np
        from spleeter.separator import Separator  # type: ignore
        from spleeter.audio.adapter import AudioAdapter  # type: ignore

        audio_loader = AudioAdapter.default()
        target_sr = 44100
        data, sr = audio_loader.load(vocals_path, sample_rate=target_sr)
        try:
            separator = Separator("spleeter:2stems", MWF=(mode != "fast"))
        except Exception:
            separator = Separator("spleeter:2stems")
        out = separator.separate(data)
        lead = out.get("vocals")
        back = out.get("accompaniment")
        if lead is None or back is None:
            return None
        lead = np.asarray(lead, dtype=np.float32)
        back = np.asarray(back, dtype=np.float32)
        if lead.ndim == 1:
            lead = lead[:, None]
        if back.ndim == 1:
            back = back[:, None]

        # Mix consistency to reduce crackling/artifacts.
        mix = np.asarray(data, dtype=np.float32)
        if mix.ndim == 1:
            mix = mix[:, None]
        n = int(min(mix.shape[0], lead.shape[0], back.shape[0]))
        mix = mix[:n]
        lead = lead[:n]
        back = back[:n]
        summ = lead + back
        err = mix - summ
        back = (back + 0.75 * err).astype(np.float32)
        lead = (mix - back).astype(np.float32)
        return lead, back, int(sr), f"spleeter-2stems:{mode}"
    except Exception:
        return None


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


def _spectral_mask_split(x, sr: int, quality_mode: str = "balanced"):
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

    mode = _normalize_quality_mode(quality_mode)
    if mode == "quality":
        nperseg = 4096 if int(sr) >= 32000 else 2048
        noverlap = int(round(nperseg * 0.84))
        t_h_sec = 1.25
        f_ks_p = 45
        split_hz = 300.0
        trans_hz = 40.0
        p = 2.4
        residual_to_lead = 0.15
        residual_to_back = 0.85
    elif mode == "fast":
        nperseg = 1024
        noverlap = 768
        t_h_sec = 0.55
        f_ks_p = 21
        split_hz = 345.0
        trans_hz = 70.0
        p = 1.9
        residual_to_lead = 0.24
        residual_to_back = 0.76
    else:
        nperseg = 2048
        noverlap = 1536
        t_h_sec = 0.90
        f_ks_p = 31
        split_hz = 320.0
        trans_hz = 55.0
        p = 2.0
        residual_to_lead = 0.20
        residual_to_back = 0.80

    noverlap = max(0, min(nperseg - 1, int(noverlap)))
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
    # HPSS: harmonic tends to long horizontal ridges, rap/transients/consonants
    # tend to vertical structures. This is more suitable for "high-note + rap"
    # overlap than pure band split.
    t_ks_h = int(max(9, round((float(t_h_sec) * sr) / hop)))
    if (t_ks_h % 2) == 0:
        t_ks_h += 1
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
    hi_w = 1.0 / (1.0 + np.exp(-(freqs - split_hz) / max(8.0, trans_hz)))
    hi_w = hi_w.reshape(-1, 1).astype(np.float32)
    lo_w = (1.0 - hi_w).astype(np.float32)

    lead_harm = harmonic_stft * hi_w
    backing_harm = harmonic_stft * lo_w

    # Residual is mostly assigned to backing to preserve rap articulations.
    lead_stft = lead_harm + (float(residual_to_lead) * residual_stft)
    backing_stft = backing_harm + percussive_stft + (float(residual_to_back) * residual_stft)

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

    # One more light refinement in quality mode to reduce leakage without
    # introducing heavy model dependencies.
    if mode == "quality":
        try:
            lead_m = np.maximum(np.abs(lead), 1e-9)
            back_m = np.maximum(np.abs(backing), 1e-9)
            w = lead_m / (lead_m + back_m + 1e-9)
            w = np.clip(w, 0.08, 0.92)
            lead = (arr * w).astype(np.float32)
            backing = (arr - lead).astype(np.float32)
        except Exception:
            pass

    return lead, backing


def _split_backing_components(backing, sr: int):
    import numpy as np

    x = np.asarray(backing, dtype=np.float32).reshape(-1)
    if x.size < 128:
        return x.copy(), np.zeros_like(x)
    try:
        from scipy.signal import butter, filtfilt

        nyq = max(1.0, sr * 0.5)
        cut = min(360.0, nyq * 0.88)
        b_lp, a_lp = butter(4, cut / nyq, btype="low")
        low = filtfilt(b_lp, a_lp, x).astype(np.float32)
        high = (x - low).astype(np.float32)
        return low, high
    except Exception:
        # FFT fallback split.
        n = x.size
        spec = np.fft.rfft(x)
        freqs = np.fft.rfftfreq(n, 1.0 / float(max(1, sr)))
        low_mask = (freqs <= 360.0).astype(np.float32)
        low = np.fft.irfft(spec * low_mask, n=n).astype(np.float32)
        high = (x - low).astype(np.float32)
        return low, high


def _to_mono_f32(x):
    import numpy as np

    arr = np.asarray(x, dtype=np.float32)
    if arr.ndim == 2:
        return arr.mean(axis=1).astype(np.float32)
    return arr.reshape(-1).astype(np.float32)


def _quick_sep_score(mix, lead, back) -> float:
    """Quick quality proxy: lower inter-stem correlation + audible backing energy."""
    import numpy as np

    m = _to_mono_f32(mix)
    l = _to_mono_f32(lead)
    b = _to_mono_f32(back)
    n = int(min(m.size, l.size, b.size))
    if n <= 1024:
        return 0.0
    m = m[:n]
    l = l[:n]
    b = b[:n]
    eps = 1e-9
    lm = float(np.sqrt(np.mean(l * l) + eps))
    bm = float(np.sqrt(np.mean(b * b) + eps))
    mm = float(np.sqrt(np.mean(m * m) + eps))
    if mm <= 1e-8:
        return 0.0
    lc = l - float(np.mean(l))
    bc = b - float(np.mean(b))
    den = float(np.sqrt(np.sum(lc * lc) * np.sum(bc * bc)) + eps)
    corr = float(np.sum(lc * bc) / den) if den > eps else 0.0
    corr_term = max(0.0, 1.0 - min(1.0, abs(corr)))
    back_term = max(0.0, min(1.0, bm / max(eps, mm * 0.55)))
    lead_term = max(0.0, min(1.0, lm / max(eps, mm * 0.85)))
    return float(0.55 * corr_term + 0.30 * back_term + 0.15 * lead_term)


def _roughness_ratio(x) -> float:
    """Simple artifact proxy: excessive temporal roughness indicates over-processing."""
    import numpy as np

    a = _to_mono_f32(x)
    if a.size <= 16:
        return 0.0
    eps = 1e-9
    rms = float(np.sqrt(np.mean(a * a) + eps))
    drms = float(np.sqrt(np.mean(np.diff(a) * np.diff(a)) + eps))
    return float(drms / max(eps, rms))


def _safe_corr(a, b) -> float:
    import numpy as np

    x = _to_mono_f32(a)
    y = _to_mono_f32(b)
    n = int(min(x.size, y.size))
    if n <= 32:
        return 0.0
    x = x[:n] - float(np.mean(x[:n]))
    y = y[:n] - float(np.mean(y[:n]))
    den = float(np.sqrt(np.sum(x * x) * np.sum(y * y)) + 1e-9)
    if den <= 1e-9:
        return 0.0
    return float(np.sum(x * y) / den)


def _framewise_debleed(backing, lead, base_k: float, quality_mode: str = "balanced"):
    """Frame-wise projection suppression: less aggressive and more natural than global subtraction."""
    import numpy as np

    b = _to_mono_f32(backing)
    l = _to_mono_f32(lead)
    n = int(min(b.size, l.size))
    if n <= 1024:
        return b[:n].astype(np.float32)

    mode = _normalize_quality_mode(quality_mode)
    if mode == "quality":
        win = 4096
        hop = 2048
    elif mode == "fast":
        win = 2048
        hop = 1024
    else:
        win = 3072
        hop = 1536

    b = b[:n]
    l = l[:n]
    out = np.zeros(n, dtype=np.float32)
    wsum = np.zeros(n, dtype=np.float32)
    eps = 1e-9
    w = np.hanning(win).astype(np.float32)
    if not np.isfinite(w).all() or float(np.sum(w)) <= 0.0:
        w = np.ones(win, dtype=np.float32)

    for st in range(0, n, hop):
        ed = min(n, st + win)
        bw = b[st:ed].astype(np.float32)
        lw = l[st:ed].astype(np.float32)
        ww = w[: (ed - st)]
        if bw.size <= 32 or lw.size <= 32:
            out[st:ed] += bw * ww
            wsum[st:ed] += ww
            continue

        denom = float(np.dot(lw, lw) + eps)
        proj = float(np.dot(bw, lw) / denom)
        corr = abs(_safe_corr(bw, lw))
        brms = float(np.sqrt(np.mean(bw * bw) + eps))
        lrms = float(np.sqrt(np.mean(lw * lw) + eps))
        # 仅在“可能有明显主唱串入伴唱”时增强抑制。
        corr_gate = max(0.0, min(1.0, (corr - 0.12) / 0.52))
        energy_gate = max(0.0, min(1.0, (lrms / max(eps, brms) - 0.85) / 2.8))
        sign_gate = 1.0 if proj > 0.0 else 0.35
        k_local = float(base_k) * corr_gate * energy_gate * sign_gate
        k_local = max(0.0, min(0.88, k_local))

        rw = (bw - float(k_local) * proj * lw).astype(np.float32)
        out[st:ed] += rw * ww
        wsum[st:ed] += ww

    mask = (wsum > 1e-8)
    out[mask] = out[mask] / wsum[mask]
    out[~mask] = b[~mask]
    return out.astype(np.float32)


def _refine_two_stem_consistent(mix, lead, backing, sr: int, quality_mode: str = "balanced"):
    """Refine two stems via mask re-estimation + consistency + de-bleeding."""
    import numpy as np

    mode = _normalize_quality_mode(quality_mode)
    m = _to_mono_f32(mix)
    l0 = _to_mono_f32(lead)
    b0 = _to_mono_f32(backing)
    n = int(min(m.size, l0.size, b0.size))
    if n <= 2048:
        # 最低限一致性修正
        b = b0[:n].astype(np.float32)
        m2 = m[:n].astype(np.float32)
        b = (b + 0.55 * (m2 - (l0[:n] + b))).astype(np.float32)
        l = (m2 - b).astype(np.float32)
        return l, b

    m = m[:n]
    l0 = l0[:n]
    b0 = b0[:n]
    eps = 1e-9
    pre_score = _quick_sep_score(m, l0, b0)

    try:
        from scipy import signal
    except Exception:
        b = (b0 + 0.65 * (m - (l0 + b0))).astype(np.float32)
        l = (m - b).astype(np.float32)
        return l, b

    if mode == "quality":
        nperseg = 4096 if int(sr) >= 32000 else 2048
        noverlap = int(round(nperseg * 0.86))
        p = 2.35
        prior_mix = 0.22
        leak_k = 0.30
    elif mode == "fast":
        nperseg = 1024
        noverlap = 768
        p = 1.85
        prior_mix = 0.12
        leak_k = 0.20
    else:
        nperseg = 2048
        noverlap = 1536
        p = 2.05
        prior_mix = 0.16
        leak_k = 0.25

    try:
        _f, _t, zm = signal.stft(m, fs=int(sr), nperseg=nperseg, noverlap=noverlap, boundary="zeros", padded=True, window="hann")
        _f2, _t2, zl = signal.stft(l0, fs=int(sr), nperseg=nperseg, noverlap=noverlap, boundary="zeros", padded=True, window="hann")
        _f3, _t3, zb = signal.stft(b0, fs=int(sr), nperseg=nperseg, noverlap=noverlap, boundary="zeros", padded=True, window="hann")
    except Exception:
        b = (b0 + 0.65 * (m - (l0 + b0))).astype(np.float32)
        l = (m - b).astype(np.float32)
        return l, b

    ml = np.abs(zl).astype(np.float32) + eps
    mb = np.abs(zb).astype(np.float32) + eps
    wl = (ml ** p) / ((ml ** p) + (mb ** p) + eps)

    # 主唱频带先验（弱约束）：提高人声核心频带归主唱的概率。
    freqs = np.linspace(0.0, float(sr) * 0.5, num=wl.shape[0], dtype=np.float32)
    lo = 1.0 / (1.0 + np.exp(-(freqs - 95.0) / 35.0))
    hi = 1.0 / (1.0 + np.exp((freqs - 3200.0) / 180.0))
    prior = (lo * hi).reshape(-1, 1).astype(np.float32)
    wl = np.clip((1.0 - prior_mix) * wl + prior_mix * prior, 0.06, 0.94).astype(np.float32)
    wb = (1.0 - wl).astype(np.float32)

    zl2 = zm * wl
    zb2 = zm * wb
    try:
        _, l2 = signal.istft(zl2, fs=int(sr), nperseg=nperseg, noverlap=noverlap, input_onesided=True, boundary=True, window="hann")
        _, b2 = signal.istft(zb2, fs=int(sr), nperseg=nperseg, noverlap=noverlap, input_onesided=True, boundary=True, window="hann")
    except Exception:
        b = (b0 + 0.65 * (m - (l0 + b0))).astype(np.float32)
        l = (m - b).astype(np.float32)
        return l, b

    if l2.size < n:
        l2 = np.pad(l2, (0, n - l2.size))
    if b2.size < n:
        b2 = np.pad(b2, (0, n - b2.size))
    l2 = l2[:n].astype(np.float32)
    b2 = b2[:n].astype(np.float32)

    # 一致性修正：保证两轨之和逼近原混合。
    b2 = (b2 + 0.72 * (m - (l2 + b2))).astype(np.float32)
    l2 = (m - b2).astype(np.float32)

    # 去串音：自适应分帧抑制，避免单一全局投影造成过处理。
    corr_abs = abs(_safe_corr(b2, l2))
    leak_scale = max(0.35, min(1.18, (corr_abs - 0.06) / 0.46))
    b3 = _framewise_debleed(b2, l2, float(leak_k) * float(leak_scale), quality_mode=mode)
    # 再做一次一致性修正，避免声音“空洞化”。
    b3 = (b3 + 0.42 * (m - (l2 + b3))).astype(np.float32)
    l3 = (m - b3).astype(np.float32)

    # 抗过处理：若时间粗糙度上升过多，则与较自然版本做保守混合。
    rough_mid = max(_roughness_ratio(l2), _roughness_ratio(b2))
    rough_new = max(_roughness_ratio(l3), _roughness_ratio(b3))
    if rough_new > (rough_mid * 1.20 + 1e-9):
        over = max(0.0, rough_new / max(1e-9, rough_mid) - 1.20)
        blend = max(0.0, min(0.62, 0.45 * over))
        if blend > 1e-4:
            b3 = ((1.0 - blend) * b3 + blend * b2).astype(np.float32)
            l3 = (m - b3).astype(np.float32)

    # 保护伴唱可听性，避免“干净但太薄”。
    bm = float(np.sqrt(np.mean(b3 * b3) + eps))
    mm = float(np.sqrt(np.mean(m * m) + eps))
    if bm < (mm * 0.055):
        b3 = (0.86 * b3 + 0.14 * b2).astype(np.float32)
        l3 = (m - b3).astype(np.float32)

    mid_score = _quick_sep_score(m, l2, b2)
    post_score = _quick_sep_score(m, l3, b3)
    if (post_score + 0.006 >= max(pre_score, mid_score)) or (post_score + 0.010 >= pre_score):
        return l3, b3
    if mid_score + 0.004 >= pre_score:
        return l2, b2
    return l2, b2


def separate_vocals_internal(vocals_path: str, expected_backing_count: int = 0, *, quality_mode: str = "balanced", message_cb: Optional[Callable[[str], None]] = None, progress_cb: Optional[Callable[[int], None]] = None) -> Dict[str, object]:
    expected = max(0, int(expected_backing_count or 0))
    mode = _normalize_quality_mode(quality_mode)
    candidates: List[str] = []

    def _emit(msg: str) -> None:
        if callable(message_cb):
            try:
                message_cb(msg)
            except Exception:
                pass

    def _progress(v: int) -> None:
        if callable(progress_cb):
            try:
                progress_cb(int(max(0, min(100, int(v)))))
            except Exception:
                pass

    try:
        _emit(f"Stage2 内部分离: 模式={mode}")
        _progress(6)
        x, sr = _load_audio_mono(vocals_path)
        import numpy as np
        _progress(15)
        lead_like = None
        backing_low = None
        backing_high = None

        model_res = _try_model_split_spleeter(vocals_path, quality_mode=mode)
        if model_res is not None:
            _emit("Stage2: 已启用模型分离（Spleeter）")
            lead_like, backing_low, sr_model, engine = model_res
            sr = int(sr_model)
            _progress(68)
            if expected > 1:
                # For multi-backing request, split the backing stem into two components.
                if getattr(backing_low, "ndim", 1) == 2:
                    bmono = np.asarray(backing_low, dtype=np.float32).mean(axis=1)
                else:
                    bmono = backing_low
                b1, b2 = _split_backing_components(bmono, sr)
                backing_low = b1
                backing_high = b2
            else:
                backing_high = None
        else:
            _emit("Stage2: 正在进行频谱分离…")
            _progress(24)
            spec = _spectral_mask_split(x, sr, quality_mode=mode)
            if spec is not None:
                lead_like, backing_low = spec
                _progress(64)
                # If multiple backing tracks requested, split backing for richer output.
                if expected > 1:
                    b1, b2 = _split_backing_components(backing_low, sr)
                    backing_low, backing_high = b1, b2
                else:
                    backing_high = (x.astype(lead_like.dtype) - lead_like - backing_low).astype(lead_like.dtype)
                engine = f"spectral-mask-repet:{mode}"
            else:
                _emit("Stage2: 频谱分离失败，回退启发式分离…")
                lead_like, backing_low, backing_high = _band_split(x, sr)
                _progress(58)
                engine = f"heuristic-band-split:{mode}"

        # 质量后处理：统一做一次双干路一致性重估与串音抑制。
        _emit("Stage2: 优化主唱/伴唱串音抑制…")
        try:
            import numpy as np

            mix_ref = np.asarray(x, dtype=np.float32)
            lead_mono = _to_mono_f32(lead_like)
            back_mono = _to_mono_f32(backing_low)
            if mix_ref.size <= 0:
                mix_ref = (lead_mono + back_mono).astype(np.float32)
            elif (mix_ref.shape[0] != lead_mono.shape[0]) or (mix_ref.shape[0] != back_mono.shape[0]):
                mix_ref = (lead_mono + back_mono).astype(np.float32)
            lead_like, backing_low = _refine_two_stem_consistent(mix_ref, lead_mono, back_mono, sr, quality_mode=mode)
            if expected > 1:
                b1, b2 = _split_backing_components(backing_low, sr)
                backing_low, backing_high = b1, b2
            elif backing_high is None:
                backing_high = (mix_ref[: lead_like.shape[0]] - lead_like - backing_low).astype(np.float32)
            _progress(70)
        except Exception:
            pass

        base = Path(vocals_path)
        out_dir = base.parent if base.parent.name == "_lead_backing_stage2" else (base.parent / "_lead_backing_stage2")
        out_dir.mkdir(parents=True, exist_ok=True)

        lead_path = str((out_dir / f"{base.stem}_lead.wav").resolve())
        _emit("Stage2: 写入主唱/伴唱轨道…")
        _progress(74)
        _save_audio(lead_path, lead_like, sr)
        candidates.append(lead_path)

        if expected > 0:
            b1_path = str((out_dir / f"{base.stem}_backing_1.wav").resolve())
            _save_audio(b1_path, backing_low, sr)
            candidates.append(b1_path)
            _progress(84)
        if expected > 1:
            b2_path = str((out_dir / f"{base.stem}_backing_2.wav").resolve())
            _save_audio(b2_path, backing_high, sr)
            candidates.append(b2_path)
            _progress(91)

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
            "quality_mode": mode,
            "expected_backing_count": expected,
            "candidate_tracks": candidates,
            "preferred_lead_track": lead_path,
            "output_dir": str(out_dir),
            "diagnostics": {
                "rms_mix": rms_mix,
                "rms_lead": rms_lead,
                "rms_backing_1": rms_b1,
                "rms_backing_2": rms_b2,
            },
        }
    except Exception as e:
        # 最后兜底：即使前序流程异常，也尽量产出 lead/backing 两轨，避免上层退化为未分离路径。
        try:
            import numpy as np

            x, sr = _load_audio_mono(vocals_path)
            lead_like, backing_low, backing_high = _band_split(x, sr)
            base = Path(vocals_path)
            out_dir = base.parent if base.parent.name == "_lead_backing_stage2" else (base.parent / "_lead_backing_stage2")
            out_dir.mkdir(parents=True, exist_ok=True)
            lead_path = str((out_dir / f"{base.stem}_lead.wav").resolve())
            b1_path = str((out_dir / f"{base.stem}_backing_1.wav").resolve())
            _save_audio(lead_path, lead_like, sr)
            _save_audio(b1_path, backing_low if backing_low is not None else (np.asarray(x, dtype=np.float32) - np.asarray(lead_like, dtype=np.float32)), sr)
            candidates = [lead_path, b1_path]
            if expected > 1 and backing_high is not None:
                b2_path = str((out_dir / f"{base.stem}_backing_2.wav").resolve())
                _save_audio(b2_path, backing_high, sr)
                candidates.append(b2_path)
            return {
                "ok": True,
                "engine": f"emergency-band-fallback:{mode}",
                "quality_mode": mode,
                "expected_backing_count": expected,
                "candidate_tracks": candidates,
                "preferred_lead_track": lead_path,
                "output_dir": str(out_dir),
                "diagnostics": {
                    "fallback": True,
                    "reason": str(e),
                },
            }
        except Exception:
            pass
        _progress(100)
        return {
            "ok": False,
            "engine": f"heuristic-band-split:{mode}",
            "quality_mode": mode,
            "expected_backing_count": expected,
            "candidate_tracks": [vocals_path],
            "error": str(e),
        }
