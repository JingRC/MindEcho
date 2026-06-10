"""练声伴奏引擎 — MIDI 事件生成 + 钢琴合成 + 实时播放

纯 NumPy + sounddevice 实现，零额外依赖。
后续可升级 FluidSynth 获得更佳音色。

四种伴奏模式:
  - listen_repeat : 弹参考音 → 停顿 → 用户跟唱
  - continuous    : 全程钢琴伴奏
  - silent        : 无音频，仅视觉提示
  - smart         : 首次→listen_repeat，重练→continuous
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False

from src.vocal_training.exercise_library import VocalExercise, TargetNote


# ── 常量 ──────────────────────────────────────────────

A4_MIDI = 69
A4_FREQ = 440.0
SAMPLE_RATE = 48000  # 默认合成采样率

# 练声时间线对齐常量（与 training_visualizer.py 的 PREPARATION_OFFSET 一致）
PREPARATION_OFFSET: float = 3.0   # 标注从第3秒开始（准备时间）
PIANO_EARLY_ENTRY: float = 0.5    # 钢琴比第一个标注早0.5秒进入


class AccompanimentMode(Enum):
    LISTEN_REPEAT = "listen_repeat"
    CONTINUOUS    = "continuous"
    SILENT        = "silent"
    SMART         = "smart"


# ── MIDI 事件 ────────────────────────────────────────

@dataclass
class MidiEvent:
    """一个 MIDI 事件（合成引擎内部使用，不依赖 mido）"""
    type: str           # "note_on" | "note_off"
    note: int           # MIDI 音符号
    velocity: int       # 0-127
    time_sec: float     # 相对开始时间的秒数
    duration_sec: float = 0.0  # note_on 事件的持续秒数（note_off 由 duration 自动生成）


# ── 钢琴音色合成器 ──────────────────────────────────

class PianoSynth:
    """基于加法合成的钢琴音色渲染器。

    模拟钢琴频谱特征:
      - 基频 + 2nd–7th 谐波，指数衰减
      - ADSR 包络 (Attack 4ms, Decay 200ms, Sustain 0.7, Release 300ms)
      - 轻微失谐 + 击弦噪声
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sr = sample_rate

        # 谐波振幅 (钢琴典型频谱)
        self._harmonic_amps = np.array([
            1.0,      # 基频
            0.60,     # 2nd harmonic
            0.35,     # 3rd
            0.15,     # 4th
            0.08,     # 5th
            0.04,     # 6th
            0.02,     # 7th
        ], dtype=np.float32)

        # ADSR (秒)
        self._attack = 0.004
        self._decay = 0.20
        self._sustain_level = 0.70
        self._release = 0.30

    def midi_to_freq(self, midi_note: int) -> float:
        """MIDI → 频率"""
        return A4_FREQ * (2.0 ** ((midi_note - A4_MIDI) / 12.0))

    def render_note(self, midi_note: int, duration_sec: float, velocity: int = 80) -> np.ndarray:
        """合成单个音符的 PCM 音频。

        Args:
            midi_note: MIDI 音符号
            duration_sec: 持续秒数
            velocity: 力度 0-127

        Returns:
            float32 数组 [-1, 1], shape=(n_samples,)
        """
        num_samples = int(self.sr * duration_sec) + 1
        t = np.linspace(0, duration_sec, num_samples, endpoint=False, dtype=np.float32)
        freq = self.midi_to_freq(midi_note)
        amp = float(velocity) / 127.0

        # 加法合成
        signal = np.zeros(num_samples, dtype=np.float32)
        for h_idx, harm_amp in enumerate(self._harmonic_amps):
            h_freq = freq * (h_idx + 1)
            # 轻微失谐 (高次谐波稍偏离整数倍)
            if h_idx >= 2:
                detune = 1.0 + (h_idx - 1) * 0.0003
                h_freq = freq * (h_idx + 1) * detune
            signal += harm_amp * np.sin(2.0 * math.pi * h_freq * t)

        # 归一化
        signal /= max(np.max(np.abs(signal)), 1e-9)

        # ADSR 包络
        env = self._make_envelope(num_samples, duration_sec)

        # 击弦噪声 (极短白噪声在 attack 阶段)
        noise_len = int(self.sr * 0.002)  # 2ms
        if noise_len > 0 and num_samples > noise_len:
            hammer_noise = np.random.randn(noise_len).astype(np.float32) * 0.02
            signal[:noise_len] += hammer_noise

        signal = signal * env * amp

        # 钳位
        np.clip(signal, -0.99, 0.99, out=signal)

        # 非常轻的指数衰减混响模拟
        signal = self._add_light_reverb(signal)

        return signal.astype(np.float32)

    def render_midi_events(
        self,
        events: List[MidiEvent],
        total_duration_sec: float,
    ) -> np.ndarray:
        """将 MIDI 事件序列合成为完整音频。

        Args:
            events: MIDI 事件列表 (按时间排序)
            total_duration_sec: 输出总时长 (秒)

        Returns:
            float32 立体声数组 shape=(n_samples, 2)
        """
        n_samples = int(self.sr * total_duration_sec) + 1
        output = np.zeros((n_samples, 2), dtype=np.float32)

        for evt in events:
            if evt.type != "note_on":
                continue
            start_sample = int(evt.time_sec * self.sr)
            if start_sample >= n_samples:
                continue

            note_audio = self.render_note(
                midi_note=evt.note,
                duration_sec=evt.duration_sec,
                velocity=evt.velocity,
            )

            end_sample = min(start_sample + len(note_audio), n_samples)
            n_insert = end_sample - start_sample

            if n_insert > 0:
                output[start_sample:end_sample, 0] += note_audio[:n_insert] * 0.7  # 左声道
                output[start_sample:end_sample, 1] += note_audio[:n_insert] * 0.7  # 右声道

        # 轻量限制
        max_val = np.max(np.abs(output))
        if max_val > 0.95:
            output *= 0.95 / max_val

        return output.astype(np.float32)

    def _make_envelope(self, num_samples: int, duration_sec: float) -> np.ndarray:
        """生成 ADSR 包络"""
        env = np.ones(num_samples, dtype=np.float32)

        # Attack
        attack_samples = int(self._attack * self.sr)
        if attack_samples > 0 and num_samples > 0:
            n = min(attack_samples, num_samples)
            env[:n] = np.linspace(0, 1, n, dtype=np.float32)

        # Decay
        decay_samples = int(self._decay * self.sr)
        if decay_samples > 0:
            decay_start = attack_samples
            decay_end = min(decay_start + decay_samples, num_samples)
            if decay_end > decay_start:
                env[decay_start:decay_end] = np.linspace(
                    1.0, self._sustain_level, decay_end - decay_start, dtype=np.float32
                )

        # Release
        release_samples = int(self._release * self.sr)
        if release_samples > 0 and num_samples > release_samples:
            rel_start = num_samples - release_samples
            env[rel_start:] = np.linspace(
                self._sustain_level, 0.0, num_samples - rel_start, dtype=np.float32
            )

        return env

    def _add_light_reverb(self, signal: np.ndarray) -> np.ndarray:
        """极简延迟混响"""
        delay_ms = 40
        delay_samples = int(self.sr * delay_ms / 1000.0)
        if delay_samples >= len(signal):
            return signal
        wet = np.zeros_like(signal)
        wet[delay_samples:] = signal[:-delay_samples] * 0.15
        return signal + wet


# ── 伴奏引擎 ────────────────────────────────────────

class AccompanimentEngine:
    """练声伴奏引擎。

    用法:
        engine = AccompanimentEngine(sample_rate=48000)
        engine.load_exercise(exercise, mode=AccompanimentMode.SMART)
        engine.start()

        # 获取音频块:
        chunk = engine.get_audio_chunk(n_samples)
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sr = sample_rate
        self._synth = PianoSynth(sample_rate=sample_rate)

        self._exercise: Optional[VocalExercise] = None
        self._mode: AccompanimentMode = AccompanimentMode.SMART
        self._is_first_attempt: bool = True

        # 渲染的音频
        self._audio: Optional[np.ndarray] = None   # 完整伴奏 PCM (n, 2)
        self._position: int = 0                     # 当前播放位置 (采样)
        self._is_playing: bool = False
        self._start_time: float = 0.0

        # 参考音 vs 用户唱的时间段
        self._reference_sections: List[Tuple[float, float]] = []  # (start, end) 参考音时间
        self._singing_sections: List[Tuple[float, float]] = []    # (start, end) 用户唱时间

        # 音量
        self._volume: float = 0.7

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, v: float):
        self._volume = max(0.0, min(1.0, float(v)))

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def position_sec(self) -> float:
        """当前播放位置 (秒)"""
        return self._position / max(self.sr, 1)

    @property
    def total_duration_sec(self) -> float:
        """伴奏总时长 (秒)"""
        if self._audio is None:
            return 0.0
        return len(self._audio) / max(self.sr, 1)

    def load_exercise(
        self,
        exercise: VocalExercise,
        mode: AccompanimentMode = AccompanimentMode.SMART,
        is_first_attempt: bool = True,
        tempo_override: Optional[int] = None,
    ) -> None:
        """加载练习并预渲染伴奏音频。

        Args:
            exercise: 要伴奏的练习
            mode: 伴奏模式
            is_first_attempt: 是否首次尝试 (影响 smart 模式)
            tempo_override: 覆盖速度 (BPM), None = 用练习默认
        """
        self._exercise = exercise
        self._mode = mode
        self._is_first_attempt = is_first_attempt

        # 生成 MIDI 事件
        tempo = tempo_override or exercise.tempo
        events, ref_sections, sing_sections = self._exercise_to_midi(
            exercise, mode, is_first_attempt, tempo
        )
        self._reference_sections = ref_sections
        self._singing_sections = sing_sections

        # 计算总时长
        max_t = 0.0
        for evt in events:
            t_end = evt.time_sec + evt.duration_sec
            if t_end > max_t:
                max_t = t_end
        total_dur = max_t + 2.0  # +2s tail（1s 自然衰减 + 1s 时间线余量）

        # 合成音频
        if mode == AccompanimentMode.SILENT or not events:
            self._audio = np.zeros((int(self.sr * total_dur), 2), dtype=np.float32)
        else:
            self._audio = self._synth.render_midi_events(events, total_dur)

        self._position = 0
        self._is_playing = False

    def start(self) -> None:
        """开始/重置播放。"""
        self._position = 0
        self._is_playing = True
        self._start_time = time.time()

    def stop(self) -> None:
        """停止播放。"""
        self._is_playing = False

    def get_audio_chunk(self, n_samples: int) -> np.ndarray:
        """获取下一段音频数据。

        Args:
            n_samples: 要获取的样本数

        Returns:
            float32 数组 shape=(n, 2), 播放完毕后返回零填充
        """
        if not self._is_playing or self._audio is None:
            return np.zeros((n_samples, 2), dtype=np.float32)

        end_pos = min(self._position + n_samples, len(self._audio))
        chunk_len = end_pos - self._position

        if chunk_len <= 0:
            self._is_playing = False
            return np.zeros((n_samples, 2), dtype=np.float32)

        chunk = self._audio[self._position:end_pos].copy()
        self._position = end_pos

        # 补齐不足部分
        if chunk_len < n_samples:
            pad = np.zeros((n_samples - chunk_len, 2), dtype=np.float32)
            chunk = np.concatenate([chunk, pad], axis=0)
            self._is_playing = False

        # 应用音量
        if self._volume != 1.0:
            chunk *= self._volume

        return chunk.astype(np.float32)

    def get_current_section_type(self) -> str:
        """返回当前时刻属于哪个段落: 'reference' | 'singing' | 'silence'"""
        pos = self.position_sec
        for start, end in self._reference_sections:
            if start <= pos < end:
                return "reference"
        for start, end in self._singing_sections:
            if start <= pos < end:
                return "singing"
        return "silence"

    def seek(self, position_sec: float) -> None:
        """跳到指定位置。"""
        self._position = int(position_sec * self.sr)
        self._position = max(0, min(self._position, len(self._audio) if self._audio is not None else 0))

    # ── 内部方法 ─────────────────────────────────────

    def _exercise_to_midi(
        self,
        exercise: VocalExercise,
        mode: AccompanimentMode,
        is_first_attempt: bool,
        tempo: int,
    ) -> Tuple[List[MidiEvent], List[Tuple[float, float]], List[Tuple[float, float]]]:
        """将 VocalExercise 转换为 MIDI 事件序列。

        Returns:
            (events, reference_sections, singing_sections)
        """
        # 确定模式
        effective_mode = mode
        if mode == AccompanimentMode.SMART:
            effective_mode = (
                AccompanimentMode.LISTEN_REPEAT if is_first_attempt
                else AccompanimentMode.CONTINUOUS
            )

        if effective_mode == AccompanimentMode.SILENT:
            return [], [], []

        beat_dur = 60.0 / max(tempo, 1)
        events: List[MidiEvent] = []
        ref_sections: List[Tuple[float, float]] = []
        sing_sections: List[Tuple[float, float]] = []

        current_time = 0.0  # 音符相对偏移（不含准备时间）
        gap_beats = getattr(exercise, 'transition_gap_beats', 0.0)
        gap_sec = gap_beats * beat_dur  # 音符间过渡间隙（秒）
        prep_beats = 0  # 预备拍 (listen_repeat 模式下每个音前弹参考)

        for i, note in enumerate(exercise.notes):
            note_dur = note.duration_beats * beat_dur

            if effective_mode == AccompanimentMode.LISTEN_REPEAT:
                # 先弹参考音（从 PREPARATION_OFFSET 开始偏移）
                if i == 0:
                    # 第一个音：钢琴参考早0.5s进入，时长多0.5s
                    ref_start = PREPARATION_OFFSET - PIANO_EARLY_ENTRY
                    ref_dur = note_dur + PIANO_EARLY_ENTRY
                else:
                    ref_start = PREPARATION_OFFSET + current_time
                    ref_dur = note_dur

                events.append(MidiEvent(
                    type="note_on", note=note.midi_note, velocity=90,
                    time_sec=ref_start, duration_sec=ref_dur,
                ))
                ref_sections.append((ref_start, ref_start + ref_dur))

                # 用户跟唱 (无需新 MIDI 事件)
                sing_start = ref_start + ref_dur
                sing_sections.append((sing_start, sing_start + note_dur))
                current_time = sing_start + note_dur - PREPARATION_OFFSET

            elif effective_mode == AccompanimentMode.CONTINUOUS:
                if i == 0:
                    # 第一个音：钢琴早 0.5s 进入，时长多 0.5s
                    piano_start = PREPARATION_OFFSET - PIANO_EARLY_ENTRY  # 2.5s
                    piano_dur = note_dur + PIANO_EARLY_ENTRY               # 延长0.5s
                else:
                    # 后续音：钢琴与标注对齐 (PREPARATION_OFFSET + current_time)
                    piano_start = PREPARATION_OFFSET + current_time
                    piano_dur = note_dur

                events.append(MidiEvent(
                    type="note_on", note=note.midi_note, velocity=85,
                    time_sec=piano_start, duration_sec=piano_dur,
                ))
                vocal_start = PREPARATION_OFFSET + current_time
                vocal_end = vocal_start + note_dur
                ref_sections.append((vocal_start, vocal_end))
                sing_sections.append((vocal_start, vocal_end))
                current_time += note_dur

            # ── 音符间过渡间隙（最后一个音后不加）──
            if i < len(exercise.notes) - 1:
                current_time += gap_sec

        return events, ref_sections, sing_sections


# ── 便捷函数 ────────────────────────────────────────

def midi_note_to_freq(midi_note: int) -> float:
    """MIDI 音符号 → 频率 (Hz), A4=440"""
    return A4_FREQ * (2.0 ** ((midi_note - A4_MIDI) / 12.0))


def freq_to_midi_note(freq_hz: float) -> float:
    """频率 (Hz) → MIDI 音符号 (浮点)"""
    if freq_hz <= 0:
        return float("-inf")
    return A4_MIDI + 12.0 * math.log2(freq_hz / A4_FREQ)


def quick_tone(midi_note: int, duration_sec: float = 0.5, sr: int = SAMPLE_RATE) -> np.ndarray:
    """快速生成一个钢琴音 (便捷函数，测试用)。"""
    synth = PianoSynth(sample_rate=sr)
    return synth.render_note(midi_note, duration_sec)
