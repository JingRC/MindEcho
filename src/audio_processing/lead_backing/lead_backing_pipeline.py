from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .quality_metrics import compute_stage2_metrics
from .realtime_chunk_scheduler import ChunkSchedule, RealtimeChunkScheduler
from .singer_embedding import select_lead_track
from .vocal_internal_separator import separate_vocals_internal


@dataclass
class LeadBackingConfig:
    enable_stage2: bool = False
    include_backing: bool = False
    expected_backing_count: int = 0
    singer_mode: str = "auto"  # auto | template
    template_path: Optional[str] = None
    # C01: 近实时分块基础参数
    sample_rate: int = 44100
    chunk_sec: float = 0.75
    hop_sec: float = 0.20
    quality_mode: str = "balanced"  # fast | balanced | quality
    fallback_strategy: str = "auto"  # auto | none


class LeadBackingPipeline:
    """Stage2 orchestrator for lead/backing split on top of vocal stem.

    This initial version is intentionally conservative: it is opt-in and
    defaults to pass-through behavior unless explicitly enabled.
    """

    def __init__(self, config: LeadBackingConfig, message_cb: Optional[Callable[[str], None]] = None, progress_cb: Optional[Callable[[int], None]] = None):
        self.config = config
        self._message_cb = message_cb
        self._progress_cb = progress_cb
        self._last_progress = 0

    def _emit(self, message: str) -> None:
        if callable(self._message_cb):
            try:
                self._message_cb(message)
            except Exception:
                pass

    def _progress(self, value: int) -> None:
        if not callable(self._progress_cb):
            return
        try:
            v = int(max(0, min(100, int(value))))
        except Exception:
            return
        if v < int(getattr(self, '_last_progress', 0)):
            v = int(getattr(self, '_last_progress', 0))
        self._last_progress = v
        try:
            self._progress_cb(v)
        except Exception:
            pass

    def _build_scheduler(self) -> RealtimeChunkScheduler:
        schedule = ChunkSchedule(
            sample_rate=int(self.config.sample_rate or 44100),
            chunk_sec=float(self.config.chunk_sec or 0.75),
            hop_sec=float(self.config.hop_sec or 0.20),
        )
        return RealtimeChunkScheduler(schedule)

    def process(self, vocals_path: str) -> Dict[str, Any]:
        scheduler = self._build_scheduler()
        self._progress(3)
        if not self.config.enable_stage2:
            self._progress(100)
            return {
                "enabled": False,
                "lead_track": vocals_path,
                "backing_tracks": [],
                "candidate_tracks": [vocals_path],
                "metrics": compute_stage2_metrics(vocals_path, 0),
                "realtime": scheduler.summary(0),
                "message": "stage2-disabled",
            }

        self._emit("Stage2: 开始主唱/伴唱分离…")
        self._progress(8)
        req_mode = str(getattr(self.config, "quality_mode", "balanced") or "balanced").strip().lower()
        if req_mode not in ("fast", "balanced", "quality"):
            req_mode = "balanced"
        fallback = str(getattr(self.config, "fallback_strategy", "auto") or "auto").strip().lower()

        attempts = [req_mode]
        if fallback == "auto":
            if req_mode == "quality":
                attempts.append("balanced")
            if req_mode in ("quality", "balanced"):
                attempts.append("fast")

        # 去重保序
        uniq_attempts = []
        seen = set()
        for m in attempts:
            if m in seen:
                continue
            seen.add(m)
            uniq_attempts.append(m)
        attempts = uniq_attempts or ["balanced"]

        # 用户启用了伴唱输出但未给人数时，至少尝试 1 条伴唱轨。
        effective_backing_count = int(self.config.expected_backing_count or 0)
        if bool(self.config.include_backing) and effective_backing_count <= 0:
            effective_backing_count = 1

        accepted_payload: Dict[str, Any] | None = None
        quality_threshold = {
            "quality": 0.56,
            "balanced": 0.50,
            "fast": 0.44,
        }

        mode = (self.config.singer_mode or "auto").strip().lower()
        template_path = self.config.template_path if mode == "template" else None

        for idx, sep_mode in enumerate(attempts):
            span_start = 12 + int((78 * idx) / max(1, len(attempts)))
            span_end = 12 + int((78 * (idx + 1)) / max(1, len(attempts)))
            span_size = max(8, span_end - span_start)
            self._emit(f"Stage2: 分离尝试 {idx + 1}/{len(attempts)}（{sep_mode}）…")
            self._progress(span_start)

            def _sub_progress(p: int) -> None:
                try:
                    pp = int(max(0, min(100, int(p))))
                except Exception:
                    pp = 0
                mapped = span_start + int((span_size * pp) / 100)
                self._progress(mapped)

            sep = separate_vocals_internal(
                vocals_path,
                effective_backing_count,
                quality_mode=sep_mode,
                message_cb=self._emit,
                progress_cb=_sub_progress,
            )
            candidates = list(sep.get("candidate_tracks") or [])
            if not candidates:
                self._progress(min(95, span_end))
                continue

            self._progress(min(95, span_start + int(span_size * 0.78)))

            preferred_lead = str(sep.get("preferred_lead_track", "") or "").strip() if isinstance(sep, dict) else ""
            if preferred_lead and mode != "template":
                lead_track = preferred_lead
                backing_tracks = [p for p in candidates if str(p).strip() and str(p).strip() != preferred_lead]
                sel = {
                    "ok": True,
                    "mode": "separator-priority",
                    "lead_track": lead_track,
                    "backing_tracks": backing_tracks,
                }
            else:
                sel = select_lead_track(candidates, template_path=template_path)
                lead_track = sel.get("lead_track") if isinstance(sel, dict) else vocals_path
                backing_tracks = list(sel.get("backing_tracks") or []) if isinstance(sel, dict) else []
            if not self.config.include_backing:
                backing_tracks = []

            metrics = compute_stage2_metrics(
                lead_track,
                len(backing_tracks),
                backing_tracks=backing_tracks,
            )
            self._progress(min(96, span_start + int(span_size * 0.92)))
            q_score = float(metrics.get("quality_score", 0.0) or 0.0)
            gate = float(quality_threshold.get(sep_mode, 0.50))

            payload = {
                "enabled": True,
                "lead_track": lead_track,
                "backing_tracks": backing_tracks,
                "candidate_tracks": candidates,
                "selector": sel,
                "separator": sep,
                "metrics": metrics,
                "realtime": scheduler.summary(0),
                "quality_mode_used": sep_mode,
                "quality_gate": {
                    "score": q_score,
                    "threshold": gate,
                    "passed": bool(q_score >= gate),
                },
            }

            accepted_payload = payload
            if q_score >= gate or idx == (len(attempts) - 1):
                break
            self._emit(f"Stage2: 质量分 {q_score:.3f} 低于阈值 {gate:.3f}，自动回退到下一策略…")
            self._progress(min(97, span_end))

        if accepted_payload is None:
            self._progress(100)
            return {
                "enabled": False,
                "lead_track": vocals_path,
                "backing_tracks": [],
                "candidate_tracks": [vocals_path],
                "metrics": compute_stage2_metrics(vocals_path, 0),
                "realtime": scheduler.summary(0),
                "message": "stage2-separation-failed",
            }

        self._emit("Stage2: 主唱/伴唱分离完成。")
        self._progress(100)
        return accepted_payload


def run_lead_backing_stage2(vocals_path: str, options: Optional[Dict[str, Any]] = None, message_cb: Optional[Callable[[str], None]] = None, progress_cb: Optional[Callable[[int], None]] = None) -> Dict[str, Any]:
    opts = dict(options or {})
    config = LeadBackingConfig(
        enable_stage2=bool(opts.get("enable_stage2", False)),
        include_backing=bool(opts.get("include_backing", False)),
        expected_backing_count=max(0, int(opts.get("expected_backing_count", 0) or 0)),
        singer_mode=str(opts.get("singer_mode", "auto") or "auto"),
        template_path=(str(opts.get("template_path")).strip() if opts.get("template_path") else None),
        sample_rate=max(8000, int(opts.get("sample_rate", 44100) or 44100)),
        chunk_sec=max(0.08, float(opts.get("chunk_sec", 0.75) or 0.75)),
        hop_sec=max(0.02, float(opts.get("hop_sec", 0.20) or 0.20)),
        quality_mode=str(opts.get("quality_mode", "balanced") or "balanced"),
        fallback_strategy=str(opts.get("fallback_strategy", "auto") or "auto"),
    )
    pipeline = LeadBackingPipeline(config, message_cb=message_cb, progress_cb=progress_cb)
    return pipeline.process(vocals_path)
