"""练声核心引擎 — 状态机 + 音高流处理

管理一堂练声的完整生命周期：
  IDLE → COUNTDOWN → LISTENING(参考音) → SINGING(用户唱) → SCORING → FINISHED

信号驱动 UI 更新:
  - note_changed(current_index, target_note)
  - pitch_graded(note_result)
  - exercise_completed(score)
  - state_changed(new_state)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from src.vocal_training.exercise_library import VocalExercise, TargetNote
from src.vocal_training.scoring import (
    NoteResult,
    ExerciseScore,
    PitchGrade,
    OverallLevel,
    grade_pitch,
    compute_exercise_score,
    _resolve_tolerance,
    cents_deviation,
)


class TrainingState(Enum):
    """练声状态"""
    IDLE       = "空闲 — 等待选择练习"
    COUNTDOWN  = "倒计时 — 预备开始"
    LISTENING  = "聆听参考音 — 钢琴在弹"
    SINGING    = "演唱中 — 用户跟唱"
    SCORING    = "评分中 — 计算结果"
    FINISHED   = "完成 — 显示结果"


@dataclass
class _ActiveNote:
    """当前正在跟踪的目标音"""
    index: int
    target: TargetNote
    start_time: float          # 该音开始时的时间戳
    expected_duration: float   # 该音应持续的秒数
    freq_samples: List[float] = field(default_factory=list)  # 该音期间采集的频率
    onset_detected: bool = False
    onset_time: float = 0.0


class TrainingEngine:
    """练声核心引擎。

    用法:
        engine = TrainingEngine()
        engine.load_exercise(exercise)
        engine.start()

        # 音频处理循环中:
        engine.feed_pitch(freq_hz, confidence, timestamp)

        # UI 查询:
        engine.current_state
        engine.current_note_index
        engine.progress  # 0.0 - 1.0
    """

    def __init__(self, tolerance_level: str = "intermediate"):
        self._state: TrainingState = TrainingState.IDLE
        self._exercise: Optional[VocalExercise] = None
        self._tolerance_level = tolerance_level
        self._tolerance_override = _resolve_tolerance(tolerance_level)

        # 当前音符跟踪
        self._active_note: Optional[_ActiveNote] = None
        self._note_index: int = 0
        self._note_results: List[NoteResult] = []

        # 时序
        self._exercise_start_time: float = 0.0
        self._current_note_start_time: float = 0.0
        self._beat_duration: float = 0.0   # 一拍的秒数

        # 频率历史 (用于稳定性分析)
        self._freq_history: List[Tuple[float, float]] = []  # [(timestamp, freq), ...]

        # 连击
        self._current_streak: int = 0
        self._max_streak: int = 0

        # 伴奏模式
        self._accompaniment_mode: str = "smart"  # smart / listen_repeat / continuous / silent

        # 回调 / 信号
        self._callbacks: Dict[str, List[Callable]] = {
            "state_changed": [],
            "note_changed": [],       # (note_index, target_note)
            "pitch_graded": [],       # (note_result)
            "streak_updated": [],     # (current_streak)
            "exercise_completed": [], # (exercise_score)
        }

    # ── 属性 ────────────────────────────────────────────

    @property
    def current_state(self) -> TrainingState:
        return self._state

    @property
    def current_exercise(self) -> Optional[VocalExercise]:
        return self._exercise

    @property
    def current_note_index(self) -> int:
        return self._note_index

    @property
    def total_notes(self) -> int:
        return len(self._exercise.notes) if self._exercise else 0

    @property
    def progress(self) -> float:
        """练习进度 0.0 - 1.0"""
        if not self._exercise or self.total_notes == 0:
            return 0.0
        return self._note_index / self.total_notes

    @property
    def current_note(self) -> Optional[TargetNote]:
        if self._exercise and 0 <= self._note_index < self.total_notes:
            return self._exercise.notes[self._note_index]
        return None

    # ── 回调注册 ────────────────────────────────────────

    def on(self, event: str, callback: Callable) -> None:
        """注册事件回调。

        Events: state_changed, note_changed, pitch_graded,
                streak_updated, exercise_completed
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _emit(self, event: str, *args) -> None:
        for cb in self._callbacks.get(event, []):
            try:
                cb(*args)
            except Exception:
                pass

    # ── 公开方法 ────────────────────────────────────────

    def load_exercise(
        self,
        exercise: VocalExercise,
        accompaniment_mode: str = "smart",
        tolerance_level: Optional[str] = None,
    ) -> None:
        """加载练习（不立即开始）。

        Args:
            exercise: 要练习的 VocalExercise
            accompaniment_mode: "smart" | "listen_repeat" | "continuous" | "silent"
            tolerance_level: "beginner" | "intermediate" | "advanced"，None=保持当前
        """
        self._exercise = exercise
        self._accompaniment_mode = accompaniment_mode
        if tolerance_level is not None:
            self._tolerance_level = tolerance_level
            self._tolerance_override = _resolve_tolerance(tolerance_level)
        self._note_index = 0
        self._note_results.clear()
        self._freq_history.clear()
        self._current_streak = 0
        self._max_streak = 0
        self._beat_duration = 60.0 / max(exercise.tempo, 1.0)
        self._active_note = None
        self._set_state(TrainingState.IDLE)

    def start(self, countdown_beats: int = 4) -> None:
        """启动练习倒计时。

        Args:
            countdown_beats: 预备拍数 (默认 4 拍 = 1 小节)
        """
        if not self._exercise:
            raise RuntimeError("请先 load_exercise()")
        if self._state != TrainingState.IDLE:
            return

        self._note_index = 0
        self._note_results.clear()
        self._freq_history.clear()
        self._current_streak = 0
        self._max_streak = 0
        self._exercise_start_time = time.time()
        self._active_note = None

        self._set_state(TrainingState.COUNTDOWN)

    def advance_to_listening(self) -> None:
        """倒计时结束，进入聆听/准备阶段。"""
        if self._state != TrainingState.COUNTDOWN:
            return
        self._set_state(TrainingState.LISTENING)
        self._begin_current_note()

    def advance_to_singing(self) -> None:
        """参考音播放完毕，用户开始唱。"""
        if self._state not in (TrainingState.LISTENING, TrainingState.IDLE):
            return
        self._set_state(TrainingState.SINGING)

    def feed_pitch(
        self,
        freq_hz: float,
        confidence: float = 1.0,
        timestamp: Optional[float] = None,
    ) -> Optional[NoteResult]:
        """输入实时音高检测结果。

        仅在 SINGING 状态时处理。

        Args:
            freq_hz: 检测到的基频 (Hz), 0 = 无音高
            confidence: YIN 置信度 (0-1)
            timestamp: 可选时间戳，默认 time.time()

        Returns:
            NoteResult 当完成当前音时，否则 None
        """
        if self._state != TrainingState.SINGING:
            return None
        if not self._active_note:
            return None

        ts = timestamp or time.time()
        self._freq_history.append((ts, freq_hz))

        an = self._active_note
        an.freq_samples.append(freq_hz)

        elapsed = ts - an.start_time

        # 起音检测：首个有效音高
        if not an.onset_detected and freq_hz > 0 and confidence > 0.4:
            an.onset_detected = True
            an.onset_time = ts

        # 持续时长达到目标 → 完成当前音
        if elapsed >= an.expected_duration:
            return self._finish_current_note(ts)

        return None

    def skip_to_next_note(self) -> Optional[NoteResult]:
        """强制跳到下一个音（用于提前结束当前音）。"""
        if not self._active_note:
            return None
        return self._finish_current_note(time.time())

    def finish_exercise(self) -> ExerciseScore:
        """手动结束练习并返回最终得分。"""
        # 消费当前未完成的音
        if self._active_note:
            self._finish_current_note(time.time(), force=True)

        # 填充 MISS 给未唱到的剩余音符
        if self._exercise:
            remaining = self.total_notes - len(self._note_results)
            for i in range(remaining):
                note = self._exercise.notes[len(self._note_results)]
                self._note_results.append(NoteResult(
                    target_midi=note.midi_note,
                    target_label=note.label,
                    detected_freq_hz=0.0,
                    cents_deviation=999.0,
                    grade=PitchGrade.MISS,
                    label="Miss",
                ))

        score = compute_exercise_score(
            exercise_id=self._exercise.id if self._exercise else "unknown",
            note_results=self._note_results,
            freq_history=self._freq_history,
            tolerance_level=self._tolerance_level,
        )
        self._set_state(TrainingState.FINISHED)
        self._emit("exercise_completed", score)
        return score

    # ── 内部方法 ────────────────────────────────────────

    def _set_state(self, new_state: TrainingState) -> None:
        old = self._state
        self._state = new_state
        if old != new_state:
            self._emit("state_changed", new_state)

    def _begin_current_note(self) -> None:
        """开始跟踪当前音符。"""
        if not self._exercise or self._note_index >= self.total_notes:
            return
        target = self._exercise.notes[self._note_index]
        note_duration = target.duration_beats * self._beat_duration
        self._active_note = _ActiveNote(
            index=self._note_index,
            target=target,
            start_time=time.time(),
            expected_duration=note_duration,
        )
        self._emit("note_changed", self._note_index, target)

    def _finish_current_note(self, ts: float, force: bool = False) -> Optional[NoteResult]:
        """结束当前音的跟踪并评级。"""
        if not self._active_note or not self._exercise:
            return None

        an = self._active_note
        target = an.target

        # 计算代表频率：取该音期间样本的中值（抗离群）
        valid_freqs = [f for f in an.freq_samples if f > 0]
        if valid_freqs:
            detected_freq = float(np.median(valid_freqs))
        else:
            detected_freq = 0.0

        # 评级
        result = grade_pitch(
            target_midi=target.midi_note,
            detected_freq_hz=detected_freq,
            tolerance_override=self._tolerance_override,
        )

        # 计时
        if an.onset_detected and an.onset_time > 0:
            expected_onset = an.start_time + self._beat_duration * 0.15  # 15% 容差
            result.timing_offset_ms = (an.onset_time - expected_onset) * 1000.0
        else:
            result.timing_offset_ms = 999.0  # 未检测到起音

        # 持续力
        if an.expected_duration > 0:
            actual_hold = max(0.0, ts - an.start_time)
            result.hold_ratio = min(1.0, actual_hold / an.expected_duration)
        else:
            result.hold_ratio = 1.0

        # 连击
        if result.grade in (PitchGrade.PERFECT, PitchGrade.GREAT):
            self._current_streak += 1
            self._max_streak = max(self._max_streak, self._current_streak)
        else:
            self._current_streak = 0
        self._emit("streak_updated", self._current_streak)

        self._note_results.append(result)
        self._emit("pitch_graded", result)

        # 推进到下一音
        self._note_index += 1
        self._active_note = None

        if self._note_index >= self.total_notes:
            # 练习完成
            self.finish_exercise()
        elif not force:
            self._begin_current_note()

        return result

    def reset(self) -> None:
        """完全重置引擎状态。"""
        self._state = TrainingState.IDLE
        self._exercise = None
        self._note_index = 0
        self._note_results.clear()
        self._freq_history.clear()
        self._current_streak = 0
        self._max_streak = 0
        self._active_note = None
