"""对比分析引擎 —— 用户 vs 专业歌手音高曲线对比"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from ..context.builder import ComparisonResult


# ═══════════════════════════════════════════════════════════════
# DTW 对齐引擎
# ═══════════════════════════════════════════════════════════════


class DTWAligner:
    """动态时间规整 (Dynamic Time Warping) —— 对齐两段音高曲线"""

    def __init__(self, radius: int = 50):
        self.radius = radius  # Sakoe-Chiba band 半径，限制搜索范围

    def align(
        self,
        user_pitch: np.ndarray,
        ref_pitch: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        """对齐两段音高序列

        Args:
            user_pitch: 用户音高序列 (Hz)，shape (N,)
            ref_pitch: 参考音高序列 (Hz)，shape (M,)

        Returns:
            (user_aligned, ref_aligned, total_cost)
            - user_aligned: 对齐后用户序列，shape (K,)
            - ref_aligned: 对齐后参考序列，shape (K,)
            - total_cost: 总对齐代价（越小越好）
        """
        N, M = len(user_pitch), len(ref_pitch)

        # 提取有效音高（过滤掉静音帧）
        user_valid = user_pitch > 60
        ref_valid = ref_pitch > 60

        if not user_valid.any() or not ref_valid.any():
            return np.array([]), np.array([]), float("inf")

        u_pitch = user_pitch[user_valid]
        r_pitch = ref_pitch[ref_valid]

        # 转换为音分空间（使距离度量更有音乐意义）
        u_cents = self._hz_to_cents(u_pitch)
        r_cents = self._hz_to_cents(r_pitch)

        # 构建距离矩阵并计算 DTW
        n, m = len(u_cents), len(r_cents)
        cost = self._compute_dtw(u_cents, r_cents, n, m)

        # 回溯路径
        path = self._traceback(cost, n, m)
        if not path:
            return np.array([]), np.array([]), float("inf")

        # 提取对齐序列
        u_aligned = u_pitch[[p[0] for p in path]]
        r_aligned = r_pitch[[p[1] for p in path]]

        total_cost = cost[n, m] / len(path)
        return u_aligned, r_aligned, total_cost

    def _hz_to_cents(self, hz: np.ndarray, ref: float = 440.0) -> np.ndarray:
        return 1200.0 * np.log2(np.maximum(hz, 1.0) / ref)

    def _compute_dtw(
        self, u: np.ndarray, r: np.ndarray, n: int, m: int
    ) -> np.ndarray:
        cost = np.full((n + 1, m + 1), np.inf)
        cost[0, 0] = 0

        for i in range(1, n + 1):
            j_start = max(1, i - self.radius)
            j_end = min(m, i + self.radius)
            for j in range(j_start, j_end + 1):
                dist = abs(u[i - 1] - r[j - 1])
                cost[i, j] = dist + min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])

        return cost

    def _traceback(self, cost: np.ndarray, n: int, m: int) -> list[tuple[int, int]]:
        path = []
        i, j = n, m
        while i > 0 and j > 0:
            path.append((i - 1, j - 1))
            diag = cost[i - 1, j - 1]
            up = cost[i - 1, j]
            left = cost[i, j - 1]
            if diag <= up and diag <= left:
                i -= 1; j -= 1
            elif up <= left:
                i -= 1
            else:
                j -= 1

        # 裁掉头和尾 10%（对齐边界往往不稳定）
        trim = max(1, len(path) // 10)
        return path[trim:-trim][::-1] if len(path) > trim * 2 else path[::-1]


# ═══════════════════════════════════════════════════════════════
# PitchComparer
# ═══════════════════════════════════════════════════════════════


class PitchComparer:
    """用户 vs 参考歌手音高对比分析器"""

    def __init__(self):
        self.aligner = DTWAligner()

    def compare(
        self,
        user_json: str | Path,
        ref_json: str | Path,
        *,
        reference_name: str = "专业歌手",
        segment_labels: Optional[list[dict]] = None,
    ) -> ComparisonResult:
        """对比两段演唱

        Args:
            user_json: 用户演唱的 MindEcho 分析 JSON
            ref_json: 参考歌手演唱的 MindEcho 分析 JSON
            reference_name: 参考歌手名称
            segment_labels: 分段标签 [{"start": 0, "end": 15, "label": "verse1"}, ...]

        Returns:
            ComparisonResult
        """
        user_data = self._load_json(user_json)
        ref_data = self._load_json(ref_json)

        u_pitch = self._extract_pitch_array(user_data)
        r_pitch = self._extract_pitch_array(ref_data)

        if len(u_pitch) == 0 or len(r_pitch) == 0:
            return ComparisonResult(reference_name=reference_name)

        # DTW 对齐
        u_aligned, r_aligned, dtw_cost = self.aligner.align(u_pitch, r_pitch)

        if len(u_aligned) == 0:
            return ComparisonResult(reference_name=reference_name)

        # 逐帧音分偏差
        u_cents = 1200.0 * np.log2(np.maximum(u_aligned, 1.0) / 440.0)
        r_cents = 1200.0 * np.log2(np.maximum(r_aligned, 1.0) / 440.0)
        deviations = np.abs(u_cents - r_cents)

        overall_gap = float(np.mean(deviations))
        result = ComparisonResult(
            reference_name=reference_name,
            overall_accuracy_gap=round(overall_gap, 1),
            dtw_aligned_points=len(u_aligned),
            strengths=[],
            weaknesses=[],
        )

        # 分段分析
        if segment_labels:
            self._segment_compare(u_aligned, r_aligned, deviations, result, segment_labels, len(u_pitch))

        # 判断优劣
        if overall_gap < 25:
            result.strengths.append("整体音准接近专业水平")
        elif overall_gap < 50:
            result.strengths.append("音准基础良好")
        else:
            result.weaknesses.append(f"整体音准偏差 {overall_gap:.0f} 音分，建议加强基础音准训练")

        # 技巧对比
        user_tech = self._extract_techniques(user_data)
        ref_tech = self._extract_techniques(ref_data)
        result.technique_comparison = {
            "颤音": {"user": f"{user_tech['vibrato_count']}次", "ref": f"{ref_tech['vibrato_count']}次"},
            "滑音": {"user": f"{user_tech['slide_count']}次", "ref": f"{ref_tech['slide_count']}次"},
        }

        return result

    def _load_json(self, path: str | Path) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _extract_pitch_array(self, data: dict) -> np.ndarray:
        pitch_data = data.get("pitch_data", [])
        if not pitch_data:
            return np.array([])

        values = []
        for p in pitch_data:
            f0 = p.get("f0_smooth") or p.get("detected_frequency") or p.get("f0_raw") or 0
            if p.get("has_pitch", f0 > 60):
                values.append(f0)
            else:
                values.append(0)
        return np.array(values)

    def _extract_techniques(self, data: dict) -> dict:
        events = data.get("technique_events", [])
        vibrato = sum(1 for e in events if e.get("type") == "vibrato")
        slide = sum(1 for e in events if e.get("type") == "slide")
        return {"vibrato_count": vibrato, "slide_count": slide}

    def _segment_compare(
        self,
        u_aligned: np.ndarray,
        r_aligned: np.ndarray,
        deviations: np.ndarray,
        result: ComparisonResult,
        segment_labels: list[dict],
        user_total_frames: int,
    ):
        """按段落评估对比"""
        best_seg = ("", float("inf"))
        worst_seg = ("", 0.0)

        for seg in segment_labels:
            start_ratio = seg["start"] / max(user_total_frames, 1)
            end_ratio = seg["end"] / max(user_total_frames, 1)
            i_start = int(start_ratio * len(deviations))
            i_end = int(end_ratio * len(deviations))
            i_start = max(0, min(i_start, len(deviations) - 1))
            i_end = max(i_start + 1, min(i_end, len(deviations)))

            seg_dev = float(np.mean(deviations[i_start:i_end]))
            label = seg.get("label", f"段落")
            if seg_dev < best_seg[1]:
                best_seg = (label, seg_dev)
            if seg_dev > worst_seg[1]:
                worst_seg = (label, seg_dev)

        result.best_segment = best_seg[0]
        result.worst_segment = worst_seg[0]
