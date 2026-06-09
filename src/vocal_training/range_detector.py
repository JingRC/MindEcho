"""音域自动检测 — 快速上下行测试确定舒适音域

用法:
    detector = RangeDetector()
    detector.start()

    # 音频循环中:
    detector.feed_pitch(freq_hz)  # 实时喂入

    # 完成后:
    low, high = detector.result  # (midi_low, midi_high)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Tuple

import numpy as np


A4_MIDI = 69
A4_FREQ = 440.0


class RangeDetectionState(Enum):
    IDLE = auto()
    ASCENDING = auto()    # 上行: 从低到高
    DESCENDING = auto()   # 下行: 从高到低
    FINISHED = auto()


@dataclass
class RangeDetector:
    """快速音域检测器。

    流程:
      1. 用户从 C4 开始上行唱 (do-re-mi...)，直到无法舒适地唱更高
      2. 用户从 C4 开始下行唱 (do-ti-la...)，直到无法舒适地唱更低
      3. 输出舒适音域 (low_midi, high_midi)

    需要约 10-15 秒完成。
    """

    # 配置
    start_midi: int = 60          # 起始音 C4
    step_semitones: int = 1       # 每次步进半音数
    min_hold_frames: int = 3      # 每个音需要保持的帧数
    confidence_threshold: float = 0.5  # 最低置信度

    # 状态
    state: RangeDetectionState = RangeDetectionState.IDLE
    _current_target: int = 60
    _current_hold_count: int = 0
    _valid_pitches: List[float] = field(default_factory=list)  # 收集的有效频率
    _ascending_max: int = 60      # 上行到达的最高音
    _descending_min: int = 60     # 下行到达的最低音
    _start_time: float = 0.0

    @property
    def is_running(self) -> bool:
        return self.state in (RangeDetectionState.ASCENDING, RangeDetectionState.DESCENDING)

    @property
    def current_target_midi(self) -> int:
        return self._current_target

    @property
    def current_target_label(self) -> str:
        _names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        return f"{_names[self._current_target % 12]}{self._current_target // 12 - 1}"

    @property
    def result(self) -> Tuple[int, int]:
        """返回 (low_midi, high_midi) 舒适音域。"""
        return (self._descending_min, self._ascending_max)

    @property
    def progress(self) -> float:
        """进度 0-1 (估算)"""
        if self.state == RangeDetectionState.IDLE:
            return 0.0
        if self.state == RangeDetectionState.FINISHED:
            return 1.0
        if self.state == RangeDetectionState.ASCENDING:
            return (self._current_target - self.start_midi) / 12.0 * 0.5
        # DESCENDING
        return 0.5 + (self.start_midi - self._current_target) / 12.0 * 0.5

    def start(self, start_midi: Optional[int] = None) -> None:
        """开始音域检测。"""
        if start_midi is not None:
            self.start_midi = start_midi
        self._current_target = self.start_midi
        self._current_hold_count = 0
        self._valid_pitches.clear()
        self._ascending_max = self.start_midi
        self._descending_min = self.start_midi
        self.state = RangeDetectionState.ASCENDING
        self._start_time = time.time()

    def feed_pitch(self, freq_hz: float, confidence: float = 0.9) -> Optional[str]:
        """喂入实时音高。

        Returns:
            "advance" — 当前音已确认，切换到下一音
            "switch_descending" — 上行完成，开始下行
            "finished" — 检测完成
            None — 继续收集当前音
        """
        if not self.is_running:
            return None

        if freq_hz <= 0 or confidence < self.confidence_threshold:
            return None

        # 转 MIDI
        midi = 69.0 + 12.0 * math.log2(max(freq_hz, 1e-9) / 440.0)

        # 检查是否接近当前目标（±60 cents）
        target_freq = 440.0 * (2.0 ** ((self._current_target - 69.0) / 12.0))
        cents = abs(1200.0 * math.log2(max(freq_hz, 1e-9) / max(target_freq, 1e-9)))

        if cents < 60:
            self._current_hold_count += 1
            self._valid_pitches.append(freq_hz)

            if self._current_hold_count >= self.min_hold_frames:
                return self._advance()
        else:
            # 偏离太大：可能是用户已经切换到下一音（尝试检测）
            self._valid_pitches.append(freq_hz)

        return None

    def skip_current(self) -> Optional[str]:
        """手动跳过当前目标音。"""
        return self._advance()

    def reset(self) -> None:
        self.state = RangeDetectionState.IDLE
        self._current_target = self.start_midi
        self._current_hold_count = 0
        self._valid_pitches.clear()

    def _advance(self) -> str:
        self._current_hold_count = 0

        if self.state == RangeDetectionState.ASCENDING:
            # 记录本轮最高
            detected_midi = self._estimate_sung_midi()
            if detected_midi is not None:
                self._ascending_max = max(self._ascending_max, detected_midi)

            # 下一音
            self._current_target += self.step_semitones
            if self._current_target > self.start_midi + 12:
                # 达到一个八度上限，切换到下行
                self.state = RangeDetectionState.DESCENDING
                self._current_target = self.start_midi - self.step_semitones
                return "switch_descending"
            return "advance"

        # DESCENDING
        detected_midi = self._estimate_sung_midi()
        if detected_midi is not None:
            self._descending_min = min(self._descending_min, detected_midi)

        self._current_target -= self.step_semitones
        if self._current_target < self.start_midi - 12:
            self.state = RangeDetectionState.FINISHED
            return "finished"
        return "advance"

    def _estimate_sung_midi(self) -> Optional[int]:
        if not self._valid_pitches:
            return None
        freqs = self._valid_pitches[-self.min_hold_frames * 2:]
        avg_freq = float(np.median(freqs))
        if avg_freq <= 0:
            return None
        midi = 69.0 + 12.0 * math.log2(max(avg_freq, 1e-9) / 440.0)
        return int(round(midi))


# ── 便捷函数 ──────────────────────────────────────────

def detect_range_from_pitches(
    frequencies_hz: List[float],
    percentile_low: float = 5.0,
    percentile_high: float = 90.0,
) -> Tuple[int, int]:
    """从一批音高数据中快速估计音域（离线方式）。

    用于已有的录音数据。
    """
    valid = [f for f in frequencies_hz if f > 0]
    if len(valid) < 20:
        return (60, 60)  # C4-C4 default

    midis = [69.0 + 12.0 * math.log2(f / 440.0) for f in valid]
    low = int(np.percentile(midis, percentile_low))
    high = int(np.percentile(midis, percentile_high))
    return (low, high)
