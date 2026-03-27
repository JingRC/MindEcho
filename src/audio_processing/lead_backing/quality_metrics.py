from __future__ import annotations

from typing import Dict, Optional, Sequence

from .audio_io import load_audio_mono as _decode_audio_mono


def _load_audio_mono(path: str):
    try:
        data, _sr = _decode_audio_mono(path)
        return data
    except Exception:
        try:
            import numpy as np

            return np.zeros((0,), dtype=np.float32)
        except Exception:
            return []


def _rms(x) -> float:
    try:
        import numpy as np

        a = np.asarray(x, dtype=np.float32)
        if a.size <= 0:
            return 0.0
        return float(np.sqrt(np.mean(a * a) + 1e-12))
    except Exception:
        return 0.0


def _corr(a, b) -> float:
    try:
        import numpy as np

        x = np.asarray(a, dtype=np.float32)
        y = np.asarray(b, dtype=np.float32)
        n = int(min(x.size, y.size))
        if n <= 64:
            return 0.0
        x = x[:n] - float(np.mean(x[:n]))
        y = y[:n] - float(np.mean(y[:n]))
        den = float(np.linalg.norm(x) * np.linalg.norm(y)) + 1e-12
        if den <= 1e-12:
            return 0.0
        return float(abs(np.dot(x, y) / den))
    except Exception:
        return 0.0


def _spectral_overlap(a, b) -> float:
    try:
        import numpy as np

        x = np.asarray(a, dtype=np.float32)
        y = np.asarray(b, dtype=np.float32)
        n = int(min(x.size, y.size))
        if n <= 256:
            return 0.0
        nfft = int(min(8192, max(1024, 1 << (int(n - 1).bit_length() - 1))))
        x = x[:nfft]
        y = y[:nfft]
        wx = np.hanning(x.size)
        wy = np.hanning(y.size)
        sx = np.abs(np.fft.rfft(x * wx)).astype(np.float32)
        sy = np.abs(np.fft.rfft(y * wy)).astype(np.float32)
        nx = sx / (float(np.sum(sx)) + 1e-9)
        ny = sy / (float(np.sum(sy)) + 1e-9)
        return float(np.sum(np.minimum(nx, ny)))
    except Exception:
        return 0.0


def compute_stage2_metrics(lead_track: Optional[str], backing_count: int, *, backing_tracks: Optional[Sequence[str]] = None) -> Dict[str, object]:
    """Compute lightweight but actionable stage2 quality metrics.

    The score is designed for relative gate decisions inside the pipeline,
    not as an absolute perceptual metric.
    """
    out = {
        "has_lead": bool(lead_track),
        "backing_count": max(0, int(backing_count or 0)),
        "quality_score": 0.0,
        "diagnostics": {},
    }
    if not lead_track:
        return out

    try:
        import numpy as np

        lead = _load_audio_mono(str(lead_track))
        lead_rms = _rms(lead)

        tracks = [str(p).strip() for p in (backing_tracks or []) if str(p).strip()]
        mix = None
        if tracks:
            arrs = [
                _load_audio_mono(p)
                for p in tracks
            ]
            arrs = [a for a in arrs if getattr(a, "size", 0) > 0]
            if arrs:
                n = int(min([a.size for a in arrs] + [lead.size if getattr(lead, "size", 0) > 0 else 0]))
                if n > 0:
                    acc = np.zeros((n,), dtype=np.float32)
                    for a in arrs:
                        acc += np.asarray(a[:n], dtype=np.float32)
                    mix = (acc / max(1, len(arrs))).astype(np.float32)

        backing_rms = _rms(mix) if mix is not None else 0.0
        leak_corr = _corr(lead, mix) if mix is not None else 0.0
        overlap = _spectral_overlap(lead, mix) if mix is not None else 0.0
        energy_balance = (backing_rms / max(1e-8, lead_rms)) if lead_rms > 0 else 0.0

        # Score assembly
        score = 1.0
        score -= min(0.52, leak_corr * 0.62)
        score -= min(0.24, overlap * 0.34)

        # Overly weak backing usually indicates leakage-dominant or collapse.
        if tracks:
            if energy_balance < 0.05:
                score -= 0.20
            elif energy_balance < 0.10:
                score -= 0.10
            elif energy_balance > 2.5:
                score -= 0.08

        if lead_rms < 1e-4:
            score -= 0.25

        score = float(max(0.0, min(1.0, score)))
        out["quality_score"] = score
        out["diagnostics"] = {
            "lead_rms": float(lead_rms),
            "backing_rms": float(backing_rms),
            "energy_balance": float(energy_balance),
            "lead_backing_corr": float(leak_corr),
            "spectral_overlap": float(overlap),
        }
        return out
    except Exception as e:
        out["diagnostics"] = {"error": str(e)}
        return out
