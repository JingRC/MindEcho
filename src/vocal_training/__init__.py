# MindEcho 练声模式 (Vocal Training Mode)
#
# 在普通模式/低延模式之外提供交互式音准训练：
#   - 预设目标音符序列（音阶/琶音/旋律片段）
#   - 钢琴合成伴奏/参考音
#   - 银色→金色实时音高线反馈
#   - 多维度评分 + 评价体系
#
# Phase 1: 核心引擎 — 评分 + 练习库 + 状态机
# Phase 2: 可视化 — 钢琴卷帘 + 银色→金色音高线
# Phase 3: 伴奏引擎 — MIDI 事件生成 + 钢琴合成 + 实时播放
# Phase 6: 移调 + 音域检测

from src.vocal_training.scoring import (
    PitchGrade,
    NoteResult,
    ExerciseScore,
    OverallLevel,
    grade_pitch,
    evaluate_level,
    compute_exercise_score,
)

from src.vocal_training.exercise_library import (
    TargetNote,
    VocalExercise,
    get_exercises_by_difficulty,
    get_exercises_by_category,
    get_exercise,
    list_all_exercises,
    get_exercises_by_level,
    get_category_summary,
    search_exercises,
    EXERCISES,
    CATEGORIES,
)

from src.vocal_training.exercise_browser import (
    ExerciseBrowser,
    open_exercise_browser,
)

from src.vocal_training.training_engine import (
    TrainingState,
    TrainingEngine,
)

# 可视化需要 pyqtgraph，不可用时为 None
try:
    from src.vocal_training.training_visualizer import TrainingVisualizer
except ImportError:
    TrainingVisualizer = None

from src.vocal_training.accompaniment import (
    AccompanimentMode,
    AccompanimentEngine,
    PianoSynth,
    MidiEvent,
    midi_note_to_freq,
    freq_to_midi_note,
    quick_tone,
)

from src.vocal_training.exercise_generator import (
    ExerciseGenerator,
    generate_exercise_for_key,
    generate_all_beginner_exercises,
    list_available_keys,
    RECOMMENDED_KEYS,
)

from src.vocal_training.range_detector import (
    RangeDetector,
    RangeDetectionState,
    detect_range_from_pitches,
)

__all__ = [
    # scoring
    "PitchGrade", "NoteResult", "ExerciseScore", "OverallLevel",
    "grade_pitch", "evaluate_level", "compute_exercise_score",
    # exercises
    "TargetNote", "VocalExercise", "EXERCISES", "CATEGORIES",
    "get_exercises_by_difficulty", "get_exercises_by_category",
    "get_exercise", "list_all_exercises",
    "get_exercises_by_level", "get_category_summary", "search_exercises",
    # exercise browser
    "ExerciseBrowser", "open_exercise_browser",
    # engine
    "TrainingState", "TrainingEngine",
    # visualizer
    "TrainingVisualizer",
    # accompaniment
    "AccompanimentMode", "AccompanimentEngine", "PianoSynth",
    "MidiEvent", "midi_note_to_freq", "freq_to_midi_note", "quick_tone",
    # generator
    "ExerciseGenerator", "generate_exercise_for_key",
    "generate_all_beginner_exercises", "list_available_keys", "RECOMMENDED_KEYS",
    # range detector
    "RangeDetector", "RangeDetectionState", "detect_range_from_pitches",
]
