from __future__ import annotations

from typing import Dict, List, Optional


def _load_audio_mono(path: str):
    import numpy as np

    try:
        import soundfile as sf

        data, _sr = sf.read(path, always_2d=True)
        if data.ndim == 2 and data.shape[1] > 1:
            data = data.mean(axis=1)
        else:
            data = data.squeeze()
        return np.asarray(data, dtype=np.float32)
    except Exception:
        return np.zeros((0,), dtype=np.float32)


def _embedding(path: str):
    import numpy as np

    x = _load_audio_mono(path)
    if x.size == 0:
        return np.asarray([0.0, 0.0, 0.0, 0.0], dtype=np.float32)

    abs_x = np.abs(x)
    e_mean = float(np.mean(abs_x))
    e_std = float(np.std(abs_x))
    zcr = float(np.mean(np.abs(np.diff(np.sign(x))) > 0)) if x.size > 1 else 0.0
    crest = float(np.max(abs_x) / max(1e-6, e_mean))
    return np.asarray([e_mean, e_std, zcr, crest], dtype=np.float32)


def _cosine(a, b) -> float:
    import numpy as np

    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na <= 1e-9 or nb <= 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _auto_score(path: str) -> float:
    import numpy as np

    x = _load_audio_mono(path)
    if x.size == 0:
        return -1e9
    rms = float(np.sqrt(np.mean(x * x)))
    # 轻量启发：中等能量 + 更明显的有声结构倾向
    abs_x = np.abs(x)
    crest = float(np.max(abs_x) / max(1e-6, float(np.mean(abs_x))))
    zcr = float(np.mean(np.abs(np.diff(np.sign(x))) > 0)) if x.size > 1 else 0.0
    score = (rms * 1.8) + (min(crest, 6.0) * 0.06) - (zcr * 0.15)
    return float(score)


def select_lead_track(
    candidate_tracks: List[str],
    template_path: Optional[str] = None,
) -> Dict[str, object]:
    if not candidate_tracks:
        return {
            "ok": False,
            "lead_track": None,
            "backing_tracks": [],
            "reason": "no-candidates",
        }

    mode = "template" if template_path else "auto"
    ranking = []

    if template_path:
        ref = _embedding(template_path)
        for p in candidate_tracks:
            ranking.append((p, _cosine(ref, _embedding(p))))
    else:
        for p in candidate_tracks:
            ranking.append((p, _auto_score(p)))

    ranking.sort(key=lambda it: it[1], reverse=True)
    lead = ranking[0][0]
    backing = [p for p, _s in ranking[1:]]

    return {
        "ok": True,
        "mode": mode,
        "lead_track": lead,
        "backing_tracks": backing,
        "template_path": template_path,
        "ranking": [{"path": p, "score": float(s)} for p, s in ranking],
    }
