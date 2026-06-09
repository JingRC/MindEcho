"""练习生成器 — 从 C 大调模板自动生成所有 12 个大调练习

用法:
    gen = ExerciseGenerator()
    exercises = gen.generate_all_keys("major_scale_ascending_c")
    # → 返回 12 个练习 (C, C#, D, ..., B)
"""

from __future__ import annotations

from typing import Dict, List, Optional

from src.vocal_training.exercise_library import (
    VocalExercise, TargetNote, EXERCISES, get_exercise,
)


# ── 调性定义 ──────────────────────────────────────────

MAJOR_KEYS = [
    ("C", 0), ("C#", 1), ("D", 2), ("D#", 3),
    ("E", 4), ("F", 5), ("F#", 6), ("G", 7),
    ("G#", 8), ("A", 9), ("A#", 10), ("B", 11),
]

# 对应移调半音数 (相对于 C)
KEY_SEMITONES = {name: semitones for name, semitones in MAJOR_KEYS}

# 适合练声的推荐调性（避免极端高/低）
RECOMMENDED_KEYS = ["C", "D", "E", "F", "G", "A"]


class ExerciseGenerator:
    """从 C 大调模板生成所有 12 个调性的练习。"""

    def __init__(self):
        self._generated: Dict[str, Dict[str, VocalExercise]] = {}
        # key: exercise_id → {key_name: VocalExercise}

    def generate_all_keys(
        self,
        exercise_id: str,
        octave_shift: int = 0,  # 额外八度偏移, 0=保持原音域
    ) -> List[VocalExercise]:
        """为指定练习生成所有 12 个调性版本。

        Args:
            exercise_id: C 大调模板 ID (如 "major_scale_ascending_c")
            octave_shift: 0=原音域, -1=低八度, +1=高八度

        Returns:
            12 个 VocalExercise (C, C#, D, ..., B)
        """
        template = get_exercise(exercise_id)
        if template is None:
            return []

        result = []
        for key_name, semitones in MAJOR_KEYS:
            total_shift = semitones + octave_shift * 12
            ex = template.transposed(total_shift)
            # 修复 ID 和名称
            ex.id = f"{exercise_id.replace('_c', '')}_{key_name.lower().replace('#', 's')}"
            ex.key = key_name
            ex.name = template.name.replace("C大调", f"{key_name}大调")
            if "C大三和弦" in ex.name:
                ex.name = ex.name.replace("C大三和弦", f"{key_name}大三和弦")
            result.append(ex)

        self._generated[exercise_id] = {e.key: e for e in result}
        return result

    def generate_for_keys(
        self,
        exercise_id: str,
        keys: List[str],
        octave_shift: int = 0,
    ) -> List[VocalExercise]:
        """为指定调性列表生成练习。"""
        all_ex = self.generate_all_keys(exercise_id, octave_shift)
        key_set = set(keys)
        return [e for e in all_ex if e.key in key_set]

    def generate_beginner_set(self) -> List[VocalExercise]:
        """生成入门练习集: C/D/E/F/G/A 调性的全部模板。"""
        template_ids = [
            "warmup_humming_c",
            "single_note_c4_c5",
            "pentatonic_ascending_c",
            "major_scale_ascending_c",
            "major_scale_descending_c",
            "major_arpeggio_ascending_c",
        ]
        result = []
        for tid in template_ids:
            exs = self.generate_for_keys(tid, RECOMMENDED_KEYS)
            result.extend(exs)
        return result

    def generate_intermediate_set(self) -> List[VocalExercise]:
        """生成中级练习集: 全 12 调性。"""
        template_ids = [
            "major_scale_full_c",
            "major_arpeggio_full_c",
            "thirds_ascending_c",
        ]
        result = []
        for tid in template_ids:
            exs = self.generate_all_keys(tid)
            result.extend(exs)
        return result

    def get_cached(self, exercise_id: str, key: str) -> Optional[VocalExercise]:
        """从缓存获取已生成的练习。"""
        return self._generated.get(exercise_id, {}).get(key)


# ── 便捷函数 ──────────────────────────────────────────

def generate_exercise_for_key(exercise_id: str, key: str = "C") -> Optional[VocalExercise]:
    """快捷生成单个调性练习。"""
    gen = ExerciseGenerator()
    exs = gen.generate_for_keys(exercise_id, [key])
    return exs[0] if exs else None


def generate_all_beginner_exercises() -> List[VocalExercise]:
    """生成完整入门练习库（6 模板 × 6 调性 = 36 个）。"""
    gen = ExerciseGenerator()
    return gen.generate_beginner_set()


def get_key_semitones(key: str) -> int:
    """调性名 → 相对 C 的半音数。"""
    return KEY_SEMITONES.get(key, 0)


def list_available_keys() -> List[str]:
    """列出可用调性名。"""
    return [k for k, _ in MAJOR_KEYS]
