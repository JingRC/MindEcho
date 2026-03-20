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


class LeadBackingPipeline:
    """Stage2 orchestrator for lead/backing split on top of vocal stem.

    This initial version is intentionally conservative: it is opt-in and
    defaults to pass-through behavior unless explicitly enabled.
    """

    def __init__(self, config: LeadBackingConfig, message_cb: Optional[Callable[[str], None]] = None):
        self.config = config
        self._message_cb = message_cb

    def _emit(self, message: str) -> None:
        if callable(self._message_cb):
            try:
                self._message_cb(message)
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
        if not self.config.enable_stage2:
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
        sep = separate_vocals_internal(vocals_path, self.config.expected_backing_count)
        candidates = list(sep.get("candidate_tracks") or [])

        mode = (self.config.singer_mode or "auto").strip().lower()
        template_path = self.config.template_path if mode == "template" else None
        sel = select_lead_track(candidates, template_path=template_path)

        lead_track = sel.get("lead_track") if isinstance(sel, dict) else vocals_path
        backing_tracks = list(sel.get("backing_tracks") or []) if isinstance(sel, dict) else []
        if not self.config.include_backing:
            backing_tracks = []
        metrics = compute_stage2_metrics(lead_track, len(backing_tracks))

        self._emit("Stage2: 主唱/伴唱分离完成。")
        return {
            "enabled": True,
            "lead_track": lead_track,
            "backing_tracks": backing_tracks,
            "candidate_tracks": candidates,
            "selector": sel,
            "separator": sep,
            "metrics": metrics,
            "realtime": scheduler.summary(0),
        }


def run_lead_backing_stage2(vocals_path: str, options: Optional[Dict[str, Any]] = None, message_cb: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
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
    )
    pipeline = LeadBackingPipeline(config, message_cb=message_cb)
    return pipeline.process(vocals_path)
