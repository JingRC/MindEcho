from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class ChunkSchedule:
    sample_rate: int = 44100
    chunk_sec: float = 0.75
    hop_sec: float = 0.20

    def normalized(self) -> "ChunkSchedule":
        sr = max(8000, int(self.sample_rate or 44100))
        chunk = max(0.08, float(self.chunk_sec or 0.75))
        hop = max(0.02, float(self.hop_sec or 0.20))
        if hop > chunk:
            hop = chunk
        return ChunkSchedule(sample_rate=sr, chunk_sec=chunk, hop_sec=hop)

    @property
    def chunk_samples(self) -> int:
        s = self.normalized()
        return max(1, int(round(s.chunk_sec * s.sample_rate)))

    @property
    def hop_samples(self) -> int:
        s = self.normalized()
        return max(1, int(round(s.hop_sec * s.sample_rate)))

    @property
    def overlap_ratio(self) -> float:
        s = self.normalized()
        return max(0.0, min(0.98, 1.0 - (s.hop_sec / max(1e-9, s.chunk_sec))))


class RealtimeChunkScheduler:
    """Chunk scheduler for near-realtime stage2 pipeline."""

    def __init__(self, schedule: ChunkSchedule | None = None):
        self.schedule = (schedule or ChunkSchedule()).normalized()

    def get_schedule(self) -> ChunkSchedule:
        return self.schedule.normalized()

    def estimate_first_frame_latency_ms(self) -> float:
        s = self.get_schedule()
        # 首帧至少需要积累一个 chunk，再加上半个 hop 的处理/调度冗余估计
        return max(1.0, (s.chunk_sec + 0.5 * s.hop_sec) * 1000.0)

    def build_windows(self, total_samples: int, *, pad_last: bool = False) -> List[Tuple[int, int]]:
        total = max(0, int(total_samples or 0))
        if total <= 0:
            return []
        chunk = self.schedule.chunk_samples
        hop = self.schedule.hop_samples
        out: List[Tuple[int, int]] = []

        start = 0
        while start < total:
            end = start + chunk
            if end <= total:
                out.append((start, end))
            else:
                if pad_last:
                    out.append((start, end))
                break
            start += hop
        return out

    def build_timeline_seconds(self, total_samples: int, *, pad_last: bool = False) -> List[Tuple[float, float]]:
        sr = float(self.schedule.sample_rate)
        return [(s / sr, e / sr) for s, e in self.build_windows(total_samples, pad_last=pad_last)]

    def summary(self, total_samples: int) -> Dict[str, float]:
        total = max(0, int(total_samples or 0))
        windows = self.build_windows(total, pad_last=False)
        coverage = 0
        if windows:
            coverage = max(0, windows[-1][1] - windows[0][0])
        return {
            "sample_rate": float(self.schedule.sample_rate),
            "chunk_sec": float(self.schedule.chunk_sec),
            "hop_sec": float(self.schedule.hop_sec),
            "overlap_ratio": float(self.schedule.overlap_ratio),
            "chunk_samples": float(self.schedule.chunk_samples),
            "hop_samples": float(self.schedule.hop_samples),
            "window_count": float(len(windows)),
            "coverage_ratio": float(coverage / total) if total > 0 else 0.0,
            "first_frame_latency_ms": float(self.estimate_first_frame_latency_ms()),
        }
