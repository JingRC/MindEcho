"""练声评分与评价体系

五级容差等级 + 五维评分 + S/A/B/C/D 总评等级。

参考依据:
  - 专业歌手偏差 15-20 cents (Biswas et al., 2020)
  - 人耳 JND ~25 cents (Pfordresher & Demorest, 2020)
  - 未训练者偏差 50+ cents (同上)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Tuple


# ── 音高等级 ────────────────────────────────────────────

class PitchGrade(Enum):
    """单音命中等级（按 cents 偏差递增）"""
    PERFECT = auto()   # ± 0-15 cents
    GREAT   = auto()   # ±16-25 cents
    GOOD    = auto()   # ±26-35 cents
    OK      = auto()   # ±36-50 cents
    MISS    = auto()   # >50 cents


# ── 等级配置 ────────────────────────────────────────────

GRADE_CONFIG = {
    PitchGrade.PERFECT: {
        "max_cents": 15,
        "label": "PERFECT!",
        "label_cn": "完美",
        "color": "gold_bright",
        "score": 1.00,
        "hex": "#FFD700",
    },
    PitchGrade.GREAT: {
        "max_cents": 25,
        "label": "GREAT",
        "label_cn": "优秀",
        "color": "gold",
        "score": 0.85,
        "hex": "#DAA520",
    },
    PitchGrade.GOOD: {
        "max_cents": 35,
        "label": "Good",
        "label_cn": "良好",
        "color": "gold_light",
        "score": 0.70,
        "hex": "#E8C84A",
    },
    PitchGrade.OK: {
        "max_cents": 50,
        "label": "",
        "label_cn": "可接受",
        "color": "silver_shimmer",
        "score": 0.40,
        "hex": "#C0C0C0",
    },
    PitchGrade.MISS: {
        "max_cents": float("inf"),
        "label": "Miss",
        "label_cn": "未命中",
        "color": "gray",
        "score": 0.0,
        "hex": "#666666",
    },
}

# ── 总评等级 ────────────────────────────────────────────

class OverallLevel(Enum):
    """练习结束后总评等级 — 七级制，搞笑游戏化命名，覆盖从小白到大神"""

    SS = ("SS · 天籁之音 🎤✨", "行走的CD！音准和稳定性无可挑剔，可以去开演唱会了", 97.0,
          "教练：我给你跪了！这水平还练什么，直接出道吧！🏆")
    S  = ("S · 麦霸本霸 🎙️",   "KTV里的绝对C位，音准极其稳定，朋友都不敢跟你合唱", 93.0,
          "教练：太强了！麦霸说的就是你，下次聚会你就是主角！🔥")
    A  = ("A · 实力唱将 🎵",    "音准扎实，已经超过大部分人，朋友圈发一段能收割一堆赞", 85.0,
          "教练：不错不错！可以考虑去参加校园歌手大赛了！💪")
    Bp = ("B+ · 渐入佳境 🌟",   "大部分音都抓得准，像刚学会走路的小鹿——偶尔踉跄但前途无量", 75.0,
          "教练：进步明显！再练练就能在朋友面前秀一把了！👍")
    B  = ("B · 略有小成 📈",    "音感已经觉醒了！虽然偶尔跑偏，但方向绝对正确",             60.0,
          "教练：有内味了！坚持下去，麦霸之位指日可待！🎯")
    C  = ("C · 初出茅庐 🌱",    "刚起步的小小白，音准还在飘忽中——但这正是最可爱的阶段",     40.0,
          "教练：别急！周杰伦也不是一天练成的，每天10分钟就够了！🌻")
    D  = ("D · 小白一枚 🐣",    "纯纯的新手村玩家，音感尚未觉醒，潜力无限！",                0.0,
          "教练：欢迎来到新手村！每个大神都是从这里出发的，哼鸣暖身走起～🐢")

    def __init__(self, label: str, description: str, min_score: float, encouragement: str = ""):
        self.label = label
        self.description = description
        self.min_score = min_score
        self.encouragement = encouragement


# ── 数据类 ──────────────────────────────────────────────

@dataclass
class NoteResult:
    """单个音符的判定结果"""
    target_midi: int               # 目标 MIDI 音符号
    target_label: str              # 目标音名 (如 "C4")
    detected_freq_hz: float        # 检测到的频率 (Hz), 0=未检测到
    cents_deviation: float         # 偏差 (cents), 999=未命中
    grade: PitchGrade              # 命中等级
    label: str                     # 评价标签 ("PERFECT!", "GREAT", etc.)
    timing_offset_ms: float = 0.0  # 起音偏差 (ms), 正=延后, 负=提前
    hold_ratio: float = 1.0        # 持续力 (实际/目标), 0-1
    frame_hit_rate: float = 1.0    # 帧级命中率 (0-1)，该音期间在OK阈值内的帧占比
    transition_time_s: float = 0.0 # 过渡耗时 (秒)，首次进入GREAT阈值的时间

    def to_dict(self) -> dict:
        return {
            "target_midi": self.target_midi,
            "target_label": self.target_label,
            "detected_freq_hz": self.detected_freq_hz,
            "cents_deviation": round(self.cents_deviation, 1),
            "grade": self.grade.name,
            "label": self.label,
            "timing_offset_ms": round(self.timing_offset_ms, 1),
            "hold_ratio": round(self.hold_ratio, 3),
            "frame_hit_rate": round(self.frame_hit_rate, 3),
            "transition_time_s": round(self.transition_time_s, 3),
        }


@dataclass
class ExerciseScore:
    """单个练习的多维度评分结果"""
    exercise_id: str
    notes: List[NoteResult] = field(default_factory=list)

    # 五维得分 (0-100)
    pitch_accuracy: float = 0.0    # 音准 (权重50%)
    stability: float = 0.0         # 稳定性 (权重20%)
    timing: float = 0.0            # 节奏 (权重15%)
    hold: float = 0.0              # 持续力 (权重10%)
    range_fit: float = 0.0         # 音域适应 (权重5%)

    total_score: float = 0.0       # 加权总分 (0-100)
    overall_level: OverallLevel = OverallLevel.D

    avg_frame_hit_rate: float = 0.0    # 平均帧命中率 (0-1)
    avg_transition_time: float = 0.0   # 平均过渡耗时 (秒)

    perfect_count: int = 0
    great_count: int = 0
    good_count: int = 0
    ok_count: int = 0
    miss_count: int = 0
    max_streak: int = 0            # 最大连击 (连续 Perfect/Great)

    def to_dict(self) -> dict:
        return {
            "exercise_id": self.exercise_id,
            "total_score": round(self.total_score, 1),
            "overall_level": self.overall_level.name,
            "overall_label": self.overall_level.label,
            "overall_desc": self.overall_level.description,
            "encouragement": self.overall_level.encouragement,
            "pitch_accuracy": round(self.pitch_accuracy, 1),
            "stability": round(self.stability, 1),
            "timing": round(self.timing, 1),
            "hold": round(self.hold, 1),
            "range_fit": round(self.range_fit, 1),
            "perfect_count": self.perfect_count,
            "great_count": self.great_count,
            "good_count": self.good_count,
            "ok_count": self.ok_count,
            "miss_count": self.miss_count,
            "max_streak": self.max_streak,
            "avg_frame_hit_rate": round(self.avg_frame_hit_rate, 3),
            "avg_transition_time": round(self.avg_transition_time, 3),
            "notes": [n.to_dict() for n in self.notes],
        }


# ── 核心函数 ────────────────────────────────────────────

def freq_to_midi(freq_hz: float) -> float:
    """频率 → MIDI 音符号（浮点，A4=69=440Hz）"""
    if freq_hz <= 0:
        return float("-inf")
    return 69.0 + 12.0 * math.log2(freq_hz / 440.0)


def midi_to_freq(midi_note: float) -> float:
    """MIDI 音符号 → 频率"""
    return 440.0 * (2.0 ** ((midi_note - 69.0) / 12.0))


def cents_deviation(target_midi: int, detected_freq_hz: float) -> float:
    """计算检测音高与目标音高的 cents 偏差。

    Args:
        target_midi: 目标 MIDI 音符号 (整数, 如 60 = C4)
        detected_freq_hz: 检测到的频率 (Hz), 0 = 未检测到

    Returns:
        cents 偏差 (始终为正), 999.0 = 未命中
    """
    if detected_freq_hz <= 0:
        return 999.0
    target_freq = midi_to_freq(float(target_midi))
    if target_freq <= 0:
        return 999.0
    try:
        cents = abs(1200.0 * math.log2(detected_freq_hz / target_freq))
        return float(cents)
    except (ValueError, OverflowError):
        return 999.0


def grade_pitch(
    target_midi: int,
    detected_freq_hz: float,
    tolerance_override: Optional[dict] = None,
) -> NoteResult:
    """对单个音高检测结果进行等级判定。

    Args:
        target_midi: 目标 MIDI 音符号
        detected_freq_hz: 检测到的频率 (Hz), 0 = 未命中
        tolerance_override: 可选的自定义容差, 如 {"PERFECT": 20, "GREAT": 30, "GOOD": 40, "OK": 60}

    Returns:
        NoteResult 包含等级、偏差、标签
    """
    target_label = _midi_to_note_name(target_midi)

    if detected_freq_hz <= 0:
        return NoteResult(
            target_midi=target_midi,
            target_label=target_label,
            detected_freq_hz=0.0,
            cents_deviation=999.0,
            grade=PitchGrade.MISS,
            label="Miss",
        )

    cents = cents_deviation(target_midi, detected_freq_hz)

    # 按容差判定等级（PERFECT→GREAT→GOOD→OK→MISS）
    thresholds = (
        tolerance_override
        if tolerance_override
        else {g.name: GRADE_CONFIG[g]["max_cents"] for g in PitchGrade}
    )

    for grade in (PitchGrade.PERFECT, PitchGrade.GREAT, PitchGrade.GOOD, PitchGrade.OK):
        if cents <= thresholds.get(grade.name, GRADE_CONFIG[grade]["max_cents"]):
            cfg = GRADE_CONFIG[grade]
            return NoteResult(
                target_midi=target_midi,
                target_label=target_label,
                detected_freq_hz=detected_freq_hz,
                cents_deviation=cents,
                grade=grade,
                label=cfg["label"],
            )

    # 超出 OK 容差 → MISS
    return NoteResult(
        target_midi=target_midi,
        target_label=target_label,
        detected_freq_hz=detected_freq_hz,
        cents_deviation=cents,
        grade=PitchGrade.MISS,
        label="Miss",
    )


def _resolve_tolerance(tolerance_level: str) -> dict:
    """将用户可选容差等级映射为实际阈值。

    tolerance_level: "beginner" | "intermediate" | "advanced"
    """
    levels = {
        "beginner":     {"PERFECT": 20, "GREAT": 35, "GOOD": 50, "OK": 65},
        "intermediate": {"PERFECT": 15, "GREAT": 25, "GOOD": 35, "OK": 50},
        "advanced":     {"PERFECT": 10, "GREAT": 20, "GOOD": 30, "OK": 40},
    }
    return levels.get(tolerance_level, levels["intermediate"])


def compute_exercise_score(
    exercise_id: str,
    note_results: List[NoteResult],
    freq_history: Optional[List[Tuple[float, float]]] = None,
    tolerance_level: str = "intermediate",
    user_vocal_range: Optional[Tuple[float, float]] = None,
) -> ExerciseScore:
    """根据单音判定结果计算多维度综合得分。

    Args:
        exercise_id: 练习 ID
        note_results: 每个目标音的结果
        freq_history: 可选的 [(timestamp, freq_hz), ...] 用于稳定性计算
        tolerance_level: "beginner" | "intermediate" | "advanced"
        user_vocal_range: (low_midi, high_midi) 用户已校准音域

    Returns:
        ExerciseScore 包含五维得分和总评等级
    """
    score = ExerciseScore(exercise_id=exercise_id, notes=note_results)
    n = len(note_results)
    if n == 0:
        return score

    # 重新按容差评级（如果容差等级与默认不同）
    if tolerance_level != "intermediate":
        override = _resolve_tolerance(tolerance_level)
        note_results = [
            grade_pitch(nr.target_midi, nr.detected_freq_hz, tolerance_override=override)
            if nr.detected_freq_hz > 0
            else nr
            for nr in note_results
        ]
        score.notes = note_results

    # ── 0. 帧级统计（先计算，供音准调整用）──
    hit_rates = [nr.frame_hit_rate for nr in note_results if nr.grade != PitchGrade.MISS]
    trans_times = [nr.transition_time_s for nr in note_results
                   if nr.transition_time_s > 0 and nr.grade != PitchGrade.MISS]
    if hit_rates:
        score.avg_frame_hit_rate = sum(hit_rates) / len(hit_rates)
    if trans_times:
        score.avg_transition_time = sum(trans_times) / len(trans_times)

    # ── 1. 音准 (50%) ──
    score_sum = sum(GRADE_CONFIG[nr.grade]["score"] for nr in note_results)
    score.pitch_accuracy = (score_sum / n) * 100.0

    # 帧命中率调节：±10%（命中率 100%→+10%, 50%→0%, 0%→-10%）
    if hit_rates:
        hit_mod = (score.avg_frame_hit_rate - 0.5) * 0.20  # range: [-0.10, +0.10]
        score.pitch_accuracy = max(0.0, min(100.0, score.pitch_accuracy * (1.0 + hit_mod)))

    # ── 2. 稳定性 (20%) ──
    # 基于命中音的 cents 偏差标准差
    hit_cents = [
        nr.cents_deviation
        for nr in note_results
        if nr.grade != PitchGrade.MISS and nr.cents_deviation < 999
    ]
    if hit_cents:
        mean_c = sum(hit_cents) / len(hit_cents)
        variance = sum((c - mean_c) ** 2 for c in hit_cents) / len(hit_cents)
        std_cents = math.sqrt(variance)
        # 标准偏差 0→100分, 50→0分
        score.stability = max(0.0, 100.0 - std_cents * 2.0)
    else:
        score.stability = 0.0

    # 基于原始频率历史的稳定性（如果提供）
    if freq_history and len(freq_history) > 3:
        freqs = [f for _, f in freq_history if f > 0]
        if len(freqs) > 3:
            semitones = []
            for i in range(1, len(freqs)):
                try:
                    semi = abs(12.0 * math.log2(max(freqs[i], 1e-9) / max(freqs[i-1], 1e-9)))
                    semitones.append(semi)
                except (ValueError, OverflowError):
                    pass
            if semitones:
                avg_jitter = sum(semitones) / len(semitones)
                # 抖动 0→+100, 0.5半音→+50, >1.0半音→+0
                freq_stability = max(0.0, 100.0 - avg_jitter * 100.0)
                score.stability = score.stability * 0.5 + freq_stability * 0.5

    # ── 3. 节奏 (15%) ──
    timed_notes = [nr for nr in note_results if nr.timing_offset_ms != 0.0]
    if timed_notes:
        on_time = sum(1 for nr in timed_notes if abs(nr.timing_offset_ms) < 150.0)
        score.timing = (on_time / len(timed_notes)) * 100.0
    else:
        score.timing = 80.0  # 无计时数据时默认良好

    # ── 4. 持续力 (10%) ──
    holds = [nr.hold_ratio for nr in note_results if nr.grade != PitchGrade.MISS]
    if holds:
        score.hold = (sum(holds) / len(holds)) * 100.0
    else:
        score.hold = 0.0

    # ── 5. 音域适应 (5%) ──
    if user_vocal_range:
        low_midi, high_midi = user_vocal_range
        target_midis = [nr.target_midi for nr in note_results]
        in_range = sum(1 for m in target_midis if low_midi <= m <= high_midi)
        score.range_fit = (in_range / len(target_midis)) * 100.0
    else:
        score.range_fit = 100.0  # 未校准默认满分

    # ── 加权总分 ──
    score.total_score = (
        score.pitch_accuracy * 0.50
        + score.stability * 0.20
        + score.timing * 0.15
        + score.hold * 0.10
        + score.range_fit * 0.05
    )

    # ── 计数统计 ──
    for nr in note_results:
        if nr.grade == PitchGrade.PERFECT:
            score.perfect_count += 1
        elif nr.grade == PitchGrade.GREAT:
            score.great_count += 1
        elif nr.grade == PitchGrade.GOOD:
            score.good_count += 1
        elif nr.grade == PitchGrade.OK:
            score.ok_count += 1
        else:
            score.miss_count += 1

    # ── 连击计算 ──
    current_streak = 0
    for nr in note_results:
        if nr.grade in (PitchGrade.PERFECT, PitchGrade.GREAT):
            current_streak += 1
            score.max_streak = max(score.max_streak, current_streak)
        else:
            current_streak = 0

    # ── 总评等级 ──
    score.overall_level = evaluate_level(score.total_score)

    return score


def evaluate_level(total_score: float) -> OverallLevel:
    """根据总分映射到 S/A/B/C/D 等级。"""
    for level in OverallLevel:
        if total_score >= level.min_score:
            return level
    return OverallLevel.D


# ── 辅助函数 ────────────────────────────────────────────

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _midi_to_note_name(midi_note: int) -> str:
    """MIDI 音符号 → 音名 + 八度 (如 60 → 'C4')"""
    octave = (midi_note // 12) - 1
    name = _NOTE_NAMES[midi_note % 12]
    return f"{name}{octave}"


def midi_from_name(note_name: str) -> int:
    """音名 + 八度 → MIDI 音符号 (如 'C4' → 60)"""
    name = note_name.strip()
    if len(name) >= 2:
        if name[1] in ("#", "b"):
            note_part = name[:2]
            octave = int(name[2:])
        else:
            note_part = name[0]
            octave = int(name[1:])
        if note_part in _NOTE_NAMES:
            return _NOTE_NAMES.index(note_part) + (octave + 1) * 12
    raise ValueError(f"无效音名: {note_name!r}")
