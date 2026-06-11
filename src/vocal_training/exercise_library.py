"""练声练习库

定义 TargetNote / VocalExercise 数据结构，
以及完整的 V2.0 练习集 — 10 大分类 × 30+ 练习，每项含 ⭐ 难度分级。

难度映射：
  difficulty 1-2 → ⭐       (入门)
  difficulty 3-4 → ⭐⭐     (初级)
  difficulty 5-6 → ⭐⭐⭐   (进阶)
  difficulty 7-8 → ⭐⭐⭐⭐  (中级)
  difficulty 9-10→ ⭐⭐⭐⭐⭐ (高级)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── 数据结构 ────────────────────────────────────────────

@dataclass
class TargetNote:
    """单个目标音"""
    midi_note: int           # MIDI 音符号 (60 = C4)
    duration_beats: float    # 持续拍数 (以 ♩ 为单位)
    label: str = ""          # 显示标签 (如 "C4")
    lyric: str = ""          # 可选用歌词/元音 ("ah", "ee", "la", "")

    def __post_init__(self):
        if not self.label:
            _names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
            _oct = (self.midi_note // 12) - 1
            self.label = f"{_names[self.midi_note % 12]}{_oct}"


@dataclass
class VocalExercise:
    """一个练声练习"""
    id: str                        # 唯一 ID (如 "c_major_scale_ascending")
    name: str                      # 显示名称
    description: str               # 练习说明
    difficulty: int                # 1-10
    stars: int                     # ⭐ 数量 (1-5)
    category: str                  # 分类
    category_name: str             # 分类中文名
    key: str                       # 调性 (如 "C")
    notes: List[TargetNote]        # 目标音符序列
    tempo: int = 100               # 默认 BPM
    transition_gap_beats: float = 0.0  # 音符间过渡间隙（拍数），0=无缝连续
    tags: List[str] = field(default_factory=list)
    unlock_level: int = 0          # 课程模式解锁所需等级 (0=默认解锁)
    accompaniment_type: str = "scale"  # 伴奏模式提示
    tip: str = ""                  # 练习小贴士

    # 显示属性
    @property
    def note_count(self) -> int:
        return len(self.notes)

    @property
    def duration_seconds(self) -> float:
        """总时长 (秒) — 包含间隙 + 准备时间 + 尾部留白。

        公式：音符总拍数 + 过渡间隙拍数 → 秒 + 5s 固定开销
        （3s 准备时间 PREPARATION_OFFSET + 2s 尾部留白）
        """
        beat_dur = 60.0 / max(self.tempo, 1)
        # 音符本体
        total_beats = sum(n.duration_beats for n in self.notes)
        # 音符间过渡间隙
        gap_count = max(0, len(self.notes) - 1)
        total_beats += self.transition_gap_beats * gap_count
        # 转为秒 + 5s 固定开销
        return total_beats * beat_dur + 5.0

    @property
    def midi_range(self) -> tuple:
        """音域范围 (low_midi, high_midi)"""
        midis = [n.midi_note for n in self.notes]
        return (min(midis), max(midis))

    @property
    def star_display(self) -> str:
        """⭐ 显示字符串"""
        return "⭐" * self.stars + "☆" * (5 - self.stars)

    @property
    def difficulty_label(self) -> str:
        """难度标签"""
        labels = {1: "入门", 2: "入门", 3: "初级", 4: "初级",
                   5: "进阶", 6: "进阶", 7: "中级", 8: "中级",
                   9: "高级", 10: "高级"}
        return labels.get(self.difficulty, "未知")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "difficulty": self.difficulty,
            "stars": self.stars,
            "star_display": self.star_display,
            "category": self.category,
            "category_name": self.category_name,
            "key": self.key,
            "note_count": self.note_count,
            "duration_seconds": round(self.duration_seconds, 1),
            "tempo": self.tempo,
            "transition_gap_beats": self.transition_gap_beats,
            "tags": self.tags,
            "tip": self.tip,
            "midi_range": list(self.midi_range),
            "notes": [
                {
                    "midi_note": n.midi_note,
                    "label": n.label,
                    "duration_beats": n.duration_beats,
                    "lyric": n.lyric,
                }
                for n in self.notes
            ],
        }

    def transposed(self, semitones: int) -> "VocalExercise":
        """返回移调后的新练习（不移改原对象）。"""
        new_notes = [
            TargetNote(
                midi_note=n.midi_note + semitones,
                duration_beats=n.duration_beats,
                lyric=n.lyric,
            )
            for n in self.notes
        ]
        new_key = _transpose_key_name(self.key, semitones)
        return VocalExercise(
            id=f"{self.id}_transposed_{semitones:+d}",
            name=f"{self.name} ({new_key})",
            description=self.description,
            difficulty=self.difficulty,
            stars=self.stars,
            category=self.category,
            category_name=self.category_name,
            key=new_key,
            notes=new_notes,
            tempo=self.tempo,
            transition_gap_beats=self.transition_gap_beats,
            tags=self.tags + ["transposed"],
            unlock_level=self.unlock_level,
            tip=self.tip,
        )


# ── 分类定义 ────────────────────────────────────────────

CATEGORIES = {
    "breath":    {"name": "🌬️ 气息控制", "icon": "🌬️", "order": 1,
                  "desc": "歌唱的根基——气息是声音的引擎"},
    "warmup":    {"name": "🔥 暖声唤醒", "icon": "🔥", "order": 2,
                  "desc": "循序渐进激活声带，安全打开嗓音"},
    "scale":     {"name": "🎼 音阶训练", "icon": "🎼", "order": 3,
                  "desc": "音准与调性感的基石——从五声到半音"},
    "arpeggio":  {"name": "🎹 琶音和弦", "icon": "🎹", "order": 4,
                  "desc": "跳进音准与和弦感的培养"},
    "interval":  {"name": "📐 音程跳跃", "icon": "📐", "order": 5,
                  "desc": "精准跨越音与音之间的距离"},
    "agility":   {"name": "💨 灵活跑动", "icon": "💨", "order": 6,
                  "desc": "花腔、快速音群与节奏控制"},
    "resonance": {"name": "🔔 共鸣音色", "icon": "🔔", "order": 7,
                  "desc": "寻找最美的声音位置与泛音"},
    "register":  {"name": "🎭 声区过渡", "icon": "🎭", "order": 8,
                  "desc": "胸声→混声→头声的丝滑切换"},
    "melody":    {"name": "🎵 旋律歌唱", "icon": "🎵", "order": 9,
                  "desc": "用熟悉的旋律检验综合音准"},
    "range":     {"name": "🚀 音域拓展", "icon": "🚀", "order": 10,
                  "desc": "拓宽高音与低音的边界"},
}


# ── 难度 → ⭐ 映射 ──────────────────────────────────────

def _stars(difficulty: int) -> int:
    """difficulty 1-10 → stars 1-5"""
    if difficulty <= 2:
        return 1
    elif difficulty <= 4:
        return 2
    elif difficulty <= 6:
        return 3
    elif difficulty <= 8:
        return 4
    else:
        return 5


# ── C 大调音高常量 ──────────────────────────────────────

C3, D3, E3, F3, G3, A3, B3 = 48, 50, 52, 53, 55, 57, 59
C4, D4, E4, F4, G4, A4, B4, C5 = 60, 62, 64, 65, 67, 69, 71, 72
D5, E5, F5, G5, A5 = 74, 76, 77, 79, 81


# ── 快捷构造 ────────────────────────────────────────────

def _n(midi: int, beats: float = 1.0, lyric: str = "") -> TargetNote:
    """快捷构造 TargetNote"""
    return TargetNote(midi_note=midi, duration_beats=beats, lyric=lyric)


def _make_exercise(
    id_: str, name: str, desc: str, difficulty: int,
    category: str, key: str, notes: List[TargetNote],
    tempo: int = 100, gap: float = 0.0,
    tags: List[str] | None = None,
    tip: str = "", unlock_level: int = 0,
) -> VocalExercise:
    """快捷构造 VocalExercise，自动填充 stars / category_name。"""
    cat_info = CATEGORIES.get(category, {"name": category, "icon": ""})
    return VocalExercise(
        id=id_, name=name, description=desc,
        difficulty=difficulty, stars=_stars(difficulty),
        category=category, category_name=cat_info["name"],
        key=key, notes=notes, tempo=tempo,
        transition_gap_beats=gap,
        tags=tags or [], tip=tip, unlock_level=unlock_level,
    )


# ══════════════════════════════════════════════════════════
#  练 习 库
# ══════════════════════════════════════════════════════════

EXERCISES: Dict[str, VocalExercise] = {}


# ── 🌬️ 气息控制 ───────────────────────────────────────

EXERCISES["breath_sustained_hiss"] = _make_exercise(
    "breath_sustained_hiss", "平稳呼气（嘶声控制）",
    "深吸气后，用'嘶——'声均匀吐气 8 拍。"
    "保持肋骨扩张，腹部缓缓内收，气息不断、不抖。"
    "这是歌唱气息支撑的第一课。",
    difficulty=1, category="breath", key="C",
    notes=[_n(C4, 8, "sss")],
    tempo=60,
    tags=["入门", "气息", "长音"],
    tip="手放肋骨两侧，感受吐气时肋骨不塌陷。",
)

EXERCISES["breath_pulse"] = _make_exercise(
    "breath_pulse", "脉冲呼吸",
    "短促有力的 4 次鼻吸气（脉冲式），然后一次长'嘶'吐完。"
    "锻炼横膈膜的灵活性与爆发力。",
    difficulty=2, category="breath", key="C",
    notes=[
        _n(C4, 2, "(吸)"), _n(D4, 2, "(吸)"),
        _n(E4, 2, "(吸)"), _n(F4, 2, "(吸)"),
        _n(G4, 8, "sss"),
    ],
    tempo=80,
    tags=["入门", "气息", "横膈膜"],
    tip="吸气要安静无声，像闻花香一样自然。",
)

EXERCISES["breath_messa_di_voce"] = _make_exercise(
    "breath_messa_di_voce", "渐强渐弱（Messa di Voce）",
    "在一个舒适音高上，用'ah'元音从极弱(p)渐强到强(f)再渐弱回极弱。"
    "气息的终极控制练习——均匀、丝滑、不断裂。",
    difficulty=5, category="breath", key="C",
    notes=[_n(G4, 16, "ah")],
    tempo=50,
    tags=["进阶", "气息", "动态控制", "古典"],
    tip="从头到尾保持音色一致，不要因为音量变化而变扁或变闷。",
)


# ── 🔥 暖声唤醒 ───────────────────────────────────────

EXERCISES["warmup_humming_c"] = _make_exercise(
    "warmup_humming_c", "C大调哼鸣暖声",
    "闭口哼鸣'Mmm'，从 C4 下行五度再返回。"
    "嘴唇轻闭，牙齿分开，感受面罩共振。适合每次练声开始时做。",
    difficulty=1, category="warmup", key="C",
    notes=[
        _n(C4, 2, "mm"), _n(G3, 2, "mm"), _n(C4, 4, "mm"),
    ],
    tempo=80, gap=0.25,
    tags=["入门", "暖声", "哼鸣", "SOVT"],
    tip="嘴唇像含着一口水，牙齿不咬合，感受面部的嗡嗡振动。",
)

EXERCISES["warmup_lip_trill"] = _make_exercise(
    "warmup_lip_trill", "唇颤音（Lip Trill）半音阶",
    "用'brrr'唇颤音从 C4 上行五度再返回，每步移高半音。"
    "唇颤音是天然的气息-发声协调器，保护声带，放松喉咙。",
    difficulty=2, category="warmup", key="C",
    notes=[
        _n(C4, 2, "brr"), _n(D4, 2, "brr"), _n(E4, 2, "brr"),
        _n(F4, 2, "brr"), _n(G4, 2, "brr"),
        _n(F4, 2, "brr"), _n(E4, 2, "brr"), _n(D4, 2, "brr"), _n(C4, 4, "brr"),
    ],
    tempo=90,
    tags=["入门", "暖声", "唇颤", "放松"],
    tip="嘴唇不用力紧闭，让气流自然吹开双唇——像小孩子玩口水的声音。",
)

EXERCISES["warmup_siren_c"] = _make_exercise(
    "warmup_siren_c", "C大调滑音（Siren 警笛）",
    "从 C4 滑到 C5 再滑回，用'oo'元音，轻松连接胸声和头声。"
    "保持气息流畅，不要在中途断掉。",
    difficulty=2, category="warmup", key="C",
    notes=[
        _n(C4, 3, "oo"), _n(C5, 3, "oo"), _n(C4, 4, "oo"),
    ],
    tempo=60,
    tags=["入门", "暖声", "滑音", "声区连接"],
    tip="想象声音像电梯一样丝滑上升下降，中间没有台阶。",
)

EXERCISES["warmup_five_tone_desc"] = _make_exercise(
    "warmup_five_tone_desc", "五音下行暖声",
    "从 G4 下行五音到 C4：So-Fa-Mi-Re-Do。"
    "每个音用'gee'清晰起音，练声必备用曲。逐步半音上移。",
    difficulty=2, category="warmup", key="C",
    notes=[
        _n(G4, 1, "gee"), _n(F4, 1, "gee"), _n(E4, 1, "gee"),
        _n(D4, 1, "gee"), _n(C4, 4, "gee"),
    ],
    tempo=100, gap=0.25,
    tags=["入门", "暖声", "五音", "经典"],
    tip="'Gee' 像在微笑，嘴角上扬，声音自然放前面。",
)


# ── 🎼 音阶训练 ───────────────────────────────────────

EXERCISES["single_note_c4_c5"] = _make_exercise(
    "single_note_c4_c5", "C大调单音匹配 (C4→C5)",
    "逐个唱准 C 大调自然音阶的每个音。"
    "每个音持续 2 拍，用'ah'元音，先听后唱。培养基础音准感。",
    difficulty=1, category="scale", key="C",
    notes=[
        _n(C4, 2, "ah"), _n(D4, 2, "ah"), _n(E4, 2, "ah"),
        _n(F4, 2, "ah"), _n(G4, 2, "ah"), _n(A4, 2, "ah"),
        _n(B4, 2, "ah"), _n(C5, 2, "ah"),
    ],
    tempo=80, gap=0.5,
    tags=["入门", "单音", "自然音阶"],
    tip="唱每个音前先在脑海里'预听'这个音高，再张口。",
)

EXERCISES["pentatonic_ascending_c"] = _make_exercise(
    "pentatonic_ascending_c", "C大调五声音阶上行",
    "C-D-E-G-A 五声音阶上行，每音 1 拍。"
    "五声音阶是中国民谣、布鲁斯和流行音乐的母语。用'la'轻唱。",
    difficulty=2, category="scale", key="C",
    notes=[
        _n(C4, 1, "la"), _n(D4, 1, "la"), _n(E4, 1, "la"),
        _n(G4, 1, "la"), _n(A4, 1, "la"), _n(C5, 2, "la"),
    ],
    tempo=100, gap=0.3,
    tags=["入门", "五声音阶", "上行"],
    tip="五声音阶天生'好听'——每个音都和谐，适合建立自信。",
)

EXERCISES["pentatonic_descending_c"] = _make_exercise(
    "pentatonic_descending_c", "C大调五声音阶下行",
    "C-A-G-E-D-C 五声音阶下行。下行比上行更难保持音高位置，"
    "注意不要偏低。用'la'演唱。",
    difficulty=2, category="scale", key="C",
    notes=[
        _n(C5, 1, "la"), _n(A4, 1, "la"), _n(G4, 1, "la"),
        _n(E4, 1, "la"), _n(D4, 1, "la"), _n(C4, 2, "la"),
    ],
    tempo=100, gap=0.3,
    tags=["入门", "五声音阶", "下行"],
    tip="下行时想象音的走向'往上'，防止音偏低。",
)

EXERCISES["major_scale_ascending_c"] = _make_exercise(
    "major_scale_ascending_c", "C大调音阶上行",
    "完整的 C 大调八度音阶上行，每音 1 拍。"
    "用'ah'元音保持喉咙打开、软腭抬起。",
    difficulty=3, category="scale", key="C",
    notes=[
        _n(C4, 1, "ah"), _n(D4, 1, "ah"), _n(E4, 1, "ah"),
        _n(F4, 1, "ah"), _n(G4, 1, "ah"), _n(A4, 1, "ah"),
        _n(B4, 1, "ah"), _n(C5, 2, "ah"),
    ],
    tempo=100, gap=0.2,
    tags=["初级", "大调音阶", "上行"],
    tip="唱上行音阶时，想象楼梯——每一步稳稳踏上去。",
)

EXERCISES["major_scale_descending_c"] = _make_exercise(
    "major_scale_descending_c", "C大调音阶下行",
    "完整的 C 大调八度音阶下行，每音 1 拍。"
    "下行比上行更难——保持声音向前、不塌、不掉。",
    difficulty=3, category="scale", key="C",
    notes=[
        _n(C5, 1, "ah"), _n(B4, 1, "ah"), _n(A4, 1, "ah"),
        _n(G4, 1, "ah"), _n(F4, 1, "ah"), _n(E4, 1, "ah"),
        _n(D4, 1, "ah"), _n(C4, 2, "ah"),
    ],
    tempo=100, gap=0.2,
    tags=["初级", "大调音阶", "下行"],
    tip="下行时保持'吸气的感觉'，腹部不要突然松掉。",
)

EXERCISES["major_scale_full_c"] = _make_exercise(
    "major_scale_full_c", "C大调音阶上下行",
    "C 大调八度音阶上行+下行。上行渐强、下行渐弱。"
    "这是所有练声练习中最核心的一条——练好它，其他事半功倍。",
    difficulty=4, category="scale", key="C",
    notes=[
        _n(C4, 1, "ah"), _n(D4, 1, "ah"), _n(E4, 1, "ah"),
        _n(F4, 1, "ah"), _n(G4, 1, "ah"), _n(A4, 1, "ah"),
        _n(B4, 1, "ah"), _n(C5, 1, "ah"),
        _n(B4, 1, "ah"), _n(A4, 1, "ah"), _n(G4, 1, "ah"),
        _n(F4, 1, "ah"), _n(E4, 1, "ah"), _n(D4, 1, "ah"),
        _n(C4, 2, "ah"),
    ],
    tempo=100, gap=0.2,
    tags=["初级", "大调音阶", "完整"],
    tip="像爬山：上坡渐强，山顶最亮；下坡渐弱，回到山脚依然稳健。",
)

EXERCISES["chromatic_scale_c"] = _make_exercise(
    "chromatic_scale_c", "半音阶（Chromatic Scale）",
    "从 C4 到 G4 逐半音上行再返回——12 个音，一个不漏。"
    "半音阶是音准的'显微镜'，任何微小偏差都会被放大。",
    difficulty=5, category="scale", key="C",
    notes=[
        _n(C4, 0.5, "ee"), _n(61, 0.5, "ee"), _n(D4, 0.5, "ee"),
        _n(63, 0.5, "ee"), _n(E4, 0.5, "ee"), _n(F4, 0.5, "ee"),
        _n(66, 0.5, "ee"), _n(G4, 0.5, "ee"),
        _n(66, 0.5, "ee"), _n(F4, 0.5, "ee"), _n(E4, 0.5, "ee"),
        _n(63, 0.5, "ee"), _n(D4, 0.5, "ee"), _n(61, 0.5, "ee"),
        _n(C4, 1, "ee"),
    ],
    tempo=80,
    tags=["进阶", "半音阶", "音准"],
    tip="用'ee'元音保持亮色——半音阶最怕模糊。",
)

EXERCISES["minor_scale_ascending_c"] = _make_exercise(
    "minor_scale_ascending_c", "c小调自然音阶上行",
    "c 小调音阶：C-D-Eb-F-G-Ab-Bb-C。"
    "小调是大调的'影子兄弟'——更忧郁、更深邃。注意 Eb 和 Ab 的降号。",
    difficulty=5, category="scale", key="Cm",
    notes=[
        _n(C4, 1, "oo"), _n(D4, 1, "oo"), _n(63, 1, "oo"),  # Eb
        _n(F4, 1, "oo"), _n(G4, 1, "oo"), _n(68, 1, "oo"),  # Ab
        _n(70, 1, "oo"), _n(C5, 2, "oo"),                    # Bb
    ],
    tempo=90, gap=0.2,
    tags=["进阶", "小调音阶", "上行"],
    tip="小调的色彩靠降三级和降六级——这两个音要特别小心。",
)


# ── 🎹 琶音和弦 ───────────────────────────────────────

EXERCISES["major_arpeggio_ascending_c"] = _make_exercise(
    "major_arpeggio_ascending_c", "C大三和弦琶音上行",
    "C-E-G-C 大三和弦琶音上行，每音 1.5 拍。"
    "跳进比级进难——琶音是突破音准瓶颈的利器。用'ma'元音。",
    difficulty=3, category="arpeggio", key="C",
    notes=[
        _n(C4, 1.5, "ma"), _n(E4, 1.5, "ma"),
        _n(G4, 1.5, "ma"), _n(C5, 2.5, "ma"),
    ],
    tempo=90, gap=0.4,
    tags=["初级", "琶音", "大三和弦", "上行"],
    tip="想象在键盘上弹 C-E-G-C——每个音都稳稳落在和弦里。",
)

EXERCISES["major_arpeggio_full_c"] = _make_exercise(
    "major_arpeggio_full_c", "C大三和弦琶音上下行",
    "C-E-G-C-G-E-C 大三和弦琶音上下行。"
    "下行时特别注意保持音高位置——这是最常见的失分点。",
    difficulty=4, category="arpeggio", key="C",
    notes=[
        _n(C4, 1, "ma"), _n(E4, 1, "ma"), _n(G4, 1, "ma"),
        _n(C5, 1, "ma"),
        _n(G4, 1, "ma"), _n(E4, 1, "ma"), _n(C4, 2, "ma"),
    ],
    tempo=90, gap=0.4,
    tags=["初级", "琶音", "大三和弦", "完整"],
    tip="下行 G→E→C 最容易偏低——想象还站在高处。",
)

EXERCISES["minor_arpeggio_c"] = _make_exercise(
    "minor_arpeggio_c", "c小三和弦琶音",
    "C-Eb-G-C 小三和弦琶音。三音降半音（Eb），色彩由明亮转忧郁。"
    "大小三和弦的切换是进阶的标志。",
    difficulty=5, category="arpeggio", key="Cm",
    notes=[
        _n(C4, 1.5, "ma"), _n(63, 1.5, "ma"),  # Eb
        _n(G4, 1.5, "ma"), _n(C5, 2.5, "ma"),
    ],
    tempo=90, gap=0.4,
    tags=["进阶", "琶音", "小三和弦"],
    tip="先唱一遍大三和弦，再唱小三和弦——感受只有第 3 音差半音。",
)

EXERCISES["dominant_seventh_arpeggio_c"] = _make_exercise(
    "dominant_seventh_arpeggio_c", "G属七和弦琶音",
    "G-B-D-F 属七和弦琶音上下行。增加了七音（F），"
    "和弦色彩更丰富——爵士、布鲁斯的灵魂和弦。",
    difficulty=6, category="arpeggio", key="C",
    notes=[
        _n(G4, 1, "la"), _n(B4, 1, "la"), _n(D5, 1, "la"),
        _n(F5, 1, "la"),
        _n(D5, 1, "la"), _n(B4, 1, "la"), _n(G4, 2, "la"),
    ],
    tempo=85, gap=0.4,
    tags=["进阶", "琶音", "属七和弦", "爵士"],
    tip="七音 F5 有种'想往下走'的张力——这就是属七的魔力。",
)

EXERCISES["octave_jump_arpeggio_c"] = _make_exercise(
    "octave_jump_arpeggio_c", "八度跳进琶音",
    "C4→C5→G4→C5→E5→C5 八度大跳。"
    "大跳后的回落最考验音准——利用琶音结构确保落点准确。",
    difficulty=7, category="arpeggio", key="C",
    notes=[
        _n(C4, 1, "ah"), _n(C5, 1, "ah"), _n(G4, 1, "ah"),
        _n(C5, 1, "ah"), _n(E5, 1, "ah"), _n(C5, 1, "ah"),
        _n(G4, 1, "ah"), _n(C4, 2, "ah"),
    ],
    tempo=80, gap=0.5,
    tags=["中级", "琶音", "八度跳进"],
    tip="跳大音程前先在脑内'预听'目标音，让声带提前准备。",
)


# ── 📐 音程跳跃 ───────────────────────────────────────

EXERCISES["thirds_ascending_c"] = _make_exercise(
    "thirds_ascending_c", "C大调三度模进上行",
    "C-E-D-F-E-G-F-A-G-B-A-C 三度模进上行。"
    "三度是旋律中最常见的音程——掌握它就掌握了旋律的密码。用'ee'元音保持亮色。",
    difficulty=5, category="interval", key="C",
    notes=[
        _n(C4, 0.75, "ee"), _n(E4, 0.75, "ee"),
        _n(D4, 0.75, "ee"), _n(F4, 0.75, "ee"),
        _n(E4, 0.75, "ee"), _n(G4, 0.75, "ee"),
        _n(F4, 0.75, "ee"), _n(A4, 0.75, "ee"),
        _n(G4, 0.75, "ee"), _n(B4, 0.75, "ee"),
        _n(A4, 0.75, "ee"), _n(C5, 1.5, "ee"),
    ],
    tempo=100, gap=0.2,
    tags=["进阶", "音程", "三度", "模进"],
    tip="C-E, D-F, E-G——像走楼梯每步跨两级，保持节奏均匀。",
)

EXERCISES["fourths_ascending_c"] = _make_exercise(
    "fourths_ascending_c", "C大调四度音程上行",
    "C-F-D-G-E-A-F-B 纯四度模进上行。"
    "四度跳进在旋律中极常见（如'祝你生日快乐'），像爬山跨大步。",
    difficulty=6, category="interval", key="C",
    notes=[
        _n(C4, 1, "ah"), _n(F4, 1, "ah"),
        _n(D4, 1, "ah"), _n(G4, 1, "ah"),
        _n(E4, 1, "ah"), _n(A4, 1, "ah"),
        _n(F4, 1, "ah"), _n(B4, 1.5, "ah"),
    ],
    tempo=90, gap=0.3,
    tags=["进阶", "音程", "四度"],
    tip="四度 = 往上跨 3 个半音——想象'祝你生日快乐'第一句。",
)

EXERCISES["fifths_ascending_c"] = _make_exercise(
    "fifths_ascending_c", "C大调五度音程上行",
    "C-G-D-A-E-B 纯五度模进上行。"
    "五度是调性音乐的基石——主→属。大跳需要大胆的气息支持。",
    difficulty=7, category="interval", key="C",
    notes=[
        _n(C4, 1, "ah"), _n(G4, 1, "ah"),
        _n(D4, 1, "ah"), _n(A4, 1, "ah"),
        _n(E4, 1, "ah"), _n(B4, 1.5, "ah"),
    ],
    tempo=80, gap=0.35,
    tags=["中级", "音程", "五度"],
    tip="五度 = 往上跨 4 个半音——比四度再多一步，气息要给足。",
)

EXERCISES["octave_leap_c"] = _make_exercise(
    "octave_leap_c", "八度大跳练习",
    "C4→C5 的八度往返。低音→高音→低音，每个八度都是同音名。"
    "考验精准落音——高八度不高不低、低八度不沉不死。",
    difficulty=7, category="interval", key="C",
    notes=[
        _n(C4, 1, "yah"), _n(C5, 1, "yah"),
        _n(D4, 1, "yah"), _n(D5, 1, "yah"),
        _n(E4, 1, "yah"), _n(E5, 1, "yah"),
        _n(F4, 1, "yah"), _n(F5, 1, "yah"),
        _n(G4, 1, "yah"), _n(G5, 2, "yah"),
    ],
    tempo=75, gap=0.5,
    tags=["中级", "音程", "八度"],
    tip="八度大跳像跳水——起跳稳，落点准，中间不散。",
)


# ── 💨 灵活跑动 ───────────────────────────────────────

EXERCISES["agility_five_note_run"] = _make_exercise(
    "agility_five_note_run", "快速五音跑动",
    "C-D-E-F-G-F-E-D-C 快速五音上下行，每音半拍。"
    "像声带'跑步'——轻巧、均匀、不拖泥带水。用'da-da-da'轻点。",
    difficulty=5, category="agility", key="C",
    notes=[
        _n(C4, 0.5, "da"), _n(D4, 0.5, "da"), _n(E4, 0.5, "da"),
        _n(F4, 0.5, "da"), _n(G4, 0.5, "da"),
        _n(F4, 0.5, "da"), _n(E4, 0.5, "da"), _n(D4, 0.5, "da"),
        _n(C4, 1, "da"),
    ],
    tempo=120,
    tags=["进阶", "灵活", "快速跑动"],
    tip="每个音像珠子，串成一条线——不要有的粗有的细。",
)

EXERCISES["agility_syncopation"] = _make_exercise(
    "agility_syncopation", "切分节奏练习",
    "用'pa-pa-pa'唱切分节奏型：弱拍进→强拍延→弱拍出。"
    "节奏感是歌唱的骨架——唱对节奏比唱对音更重要。",
    difficulty=7, category="agility", key="C",
    notes=[
        _n(C4, 0.5, "pa"), _n(D4, 1.0, "pa"), _n(D4, 0.5, "pa"),
        _n(E4, 0.5, "pa"), _n(F4, 1.0, "pa"), _n(F4, 0.5, "pa"),
        _n(G4, 0.5, "pa"), _n(A4, 1.0, "pa"), _n(A4, 0.5, "pa"),
        _n(G4, 0.5, "pa"), _n(F4, 0.5, "pa"), _n(E4, 0.5, "pa"),
        _n(D4, 0.5, "pa"), _n(C4, 1, "pa"),
    ],
    tempo=110,
    tags=["中级", "灵活", "切分", "节奏"],
    tip="切分像一个字：'长-短-长'——在心里打拍子，脚踩稳了再唱。",
)

EXERCISES["agility_melismatic_turn"] = _make_exercise(
    "agility_melismatic_turn", "花腔转音（Turn）",
    "C-D-C-B-C 四音一组的花腔装饰音——上邻音→本音→下邻音→本音。"
    "花腔不是炫技——是让旋律像水一样流淌。",
    difficulty=9, category="agility", key="C",
    notes=[
        _n(C4, 0.25, "ah"), _n(D4, 0.25, "ah"), _n(C4, 0.25, "ah"),
        _n(B3, 0.25, "ah"), _n(C4, 0.5, "ah"),
        _n(D4, 0.25, "ah"), _n(E4, 0.25, "ah"), _n(D4, 0.25, "ah"),
        _n(61, 0.25, "ah"), _n(D4, 0.5, "ah"),                    # C#
        _n(E4, 0.25, "ah"), _n(F4, 0.25, "ah"), _n(E4, 0.25, "ah"),
        _n(D4, 0.25, "ah"), _n(E4, 0.5, "ah"),
        _n(G4, 2, "ah"),
    ],
    tempo=70,
    tags=["高级", "灵活", "花腔", "装饰音"],
    tip="先极慢练准每一个音，然后再加速——花腔的秘诀是慢练。",
)


# ── 🔔 共鸣音色 ───────────────────────────────────────

EXERCISES["resonance_humming_buzz"] = _make_exercise(
    "resonance_humming_buzz", "哼鸣找共鸣",
    "从 C4 到 C5 上行哼鸣'Mmm'，每个音感受面部（鼻梁、颧骨、额头）"
    "的振动。共鸣不是'做出来'的——是'找出来'的。",
    difficulty=2, category="resonance", key="C",
    notes=[
        _n(C4, 2, "mm"), _n(E4, 2, "mm"), _n(G4, 2, "mm"),
        _n(C5, 4, "mm"),
    ],
    tempo=70, gap=0.3,
    tags=["入门", "共鸣", "哼鸣", "面罩"],
    tip="闭眼感受：哪里在振动？嘴唇？鼻子？额头？——那是你的'面罩'。",
)

EXERCISES["resonance_nasal_oral"] = _make_exercise(
    "resonance_nasal_oral", "鼻音→开口音过渡",
    "从'Mmm'（闭口鼻音）过渡到'Ahhh'（开口元音）。"
    "M→Ah 的过渡保持振动位置不变——这是'打开'的正确路径。",
    difficulty=3, category="resonance", key="C",
    notes=[
        _n(G4, 4, "Mmm→Ahh"),
        _n(A4, 4, "Mmm→Ahh"),
        _n(B4, 4, "Mmm→Ahh"),
        _n(C5, 6, "Mmm→Ahh"),
    ],
    tempo=70, gap=0.3,
    tags=["初级", "共鸣", "过渡"],
    tip="从 M 到 Ah 时，想象振动从鼻子'滑'到口腔顶部——别让它掉进喉咙。",
)

EXERCISES["resonance_vowel_migration"] = _make_exercise(
    "resonance_vowel_migration", "五元音共鸣迁移",
    "同一音高 G4 上唱五个元音：ee→eh→ah→oh→oo。"
    "同一音、不同元音——保持共鸣位置'不搬家'。这是音色统一的秘诀。",
    difficulty=4, category="resonance", key="C",
    notes=[
        _n(G4, 2, "ee"), _n(G4, 2, "eh"), _n(G4, 2, "ah"),
        _n(G4, 2, "oh"), _n(G4, 2, "oo"),
    ],
    tempo=70, gap=0.3,
    tags=["初级", "共鸣", "元音"],
    tip="五个元音，一个位置。用手轻触鼻梁——每个元音都感受到相同振动就对了。",
)


# ── 🎭 声区过渡  ──────────────────────────────────────

EXERCISES["register_slide_bridge"] = _make_exercise(
    "register_slide_bridge", "跨声区滑音",
    "从 C4 滑到 G5 再滑回——用'oo'或唇颤音。"
    "不换声、不断裂，感受胸声→混声→头声的渐变。声区不是墙，是坡。",
    difficulty=4, category="register", key="C",
    notes=[
        _n(C4, 4, "oo"), _n(G5, 4, "oo"), _n(C4, 4, "oo"),
    ],
    tempo=50,
    tags=["初级", "声区", "滑音", "混声"],
    tip="声区过渡像开车换挡——好的换挡乘客感觉不到顿挫。",
)

EXERCISES["register_chest_head_switch"] = _make_exercise(
    "register_chest_head_switch", "胸声↔头声切换",
    "在 G4 附近用'yah'切换胸声和头声——'yah'(胸)→'yee'(头)。"
    "先分别找到两种声音，再练习无缝切换。",
    difficulty=6, category="register", key="C",
    notes=[
        _n(G4, 2, "yah(胸)"), _n(G4, 2, "yee(头)"),
        _n(A4, 2, "yah(胸)"), _n(A4, 2, "yee(头)"),
        _n(B4, 2, "yah(胸)"), _n(B4, 2, "yee(头)"),
        _n(C5, 2, "yah(胸)"), _n(C5, 2, "yee(头)"),
    ],
    tempo=80, gap=0.4,
    tags=["进阶", "声区", "切换", "胸声", "头声"],
    tip="胸声→头声时，想象声音'飘'到头腔而不是'冲'上去。",
)

EXERCISES["register_mix_voice"] = _make_exercise(
    "register_mix_voice", "混声练习",
    "在换声区（E4-G5）用'nay'找混声位置——带一点鼻音的明亮感。"
    "混声是流行唱法的圣杯——把胸声的力量带到高音而不扯嗓子。",
    difficulty=8, category="register", key="C",
    notes=[
        _n(E4, 1.5, "nay"), _n(G4, 1.5, "nay"),
        _n(C5, 1.5, "nay"), _n(E5, 1.5, "nay"),
        _n(G5, 1.5, "nay"),
        _n(E5, 1.5, "nay"), _n(C5, 1.5, "nay"),
        _n(G4, 1.5, "nay"), _n(E4, 2, "nay"),
    ],
    tempo=85, gap=0.3,
    tags=["中级", "声区", "混声", "流行"],
    tip="混声像胸声和头声的'鸡尾酒'——各取一半，调出最舒服的比例。",
)


# ── 🎵 旋律歌唱 ───────────────────────────────────────

EXERCISES["melody_twinkle_c"] = _make_exercise(
    "melody_twinkle_c", "小星星 第一句",
    "C-C-G-G-A-A-G——全世界最著名的旋律。"
    "用'la'轻唱，检验你的基础音准。",
    difficulty=2, category="melody", key="C",
    notes=[
        _n(C4, 1, "la"), _n(C4, 1, "la"), _n(G4, 1, "la"),
        _n(G4, 1, "la"), _n(A4, 1, "la"), _n(A4, 1, "la"),
        _n(G4, 2, "la"),
    ],
    tempo=100,
    tags=["入门", "旋律", "儿歌"],
    tip="小星星是音准的试金石——如果它不对，任何旋律都不会对。",
)

EXERCISES["melody_twinkle_full_c"] = _make_exercise(
    "melody_twinkle_full_c", "小星星 完整版",
    "《小星星》完整 12 小节。用'la'演唱全曲，注意 F4→E4→D4→C4 这句。",
    difficulty=3, category="melody", key="C",
    notes=[
        _n(C4, 1, "la"), _n(C4, 1, "la"), _n(G4, 1, "la"),
        _n(G4, 1, "la"), _n(A4, 1, "la"), _n(A4, 1, "la"),
        _n(G4, 2, "la"),
        _n(F4, 1, "la"), _n(F4, 1, "la"), _n(E4, 1, "la"),
        _n(E4, 1, "la"), _n(D4, 1, "la"), _n(D4, 1, "la"),
        _n(C4, 2, "la"),
    ],
    tempo=100,
    tags=["初级", "旋律", "儿歌"],
    tip="第二句下行的 F-F-E-E-D-D-C 最容易偏低——注意最后一个 C。",
)

EXERCISES["melody_ode_to_joy"] = _make_exercise(
    "melody_ode_to_joy", "欢乐颂（贝多芬第九交响曲）",
    "B-B-C-D-D-C-B-A-G-G-A-B-B-A-A——贝多芬笔下最伟大的旋律。"
    "级进为主的优美线条，练习歌唱性和连贯感。",
    difficulty=3, category="melody", key="C",
    notes=[
        _n(B3, 1, "la"), _n(B3, 1, "la"), _n(C4, 1, "la"),
        _n(D4, 1, "la"), _n(D4, 1, "la"), _n(C4, 1, "la"),
        _n(B3, 1, "la"), _n(A3, 1, "la"),
        _n(G3, 1, "la"), _n(G3, 1, "la"), _n(A3, 1, "la"),
        _n(B3, 1, "la"), _n(B3, 1.5, "la"), _n(A3, 0.5, "la"),
        _n(A3, 2, "la"),
    ],
    tempo=110,
    tags=["初级", "旋律", "古典", "贝多芬"],
    tip="级进旋律最重要的是'连'——音与音之间像拉丝一样不断开。",
)

EXERCISES["melody_jasmine"] = _make_exercise(
    "melody_jasmine", "茉莉花（江苏民歌）",
    "E-E-G-A-C-A-G——中国最美的旋律之一。"
    "五声音阶的典型代表，东方韵味的音准试炼。用'la'或'啊'演唱。",
    difficulty=5, category="melody", key="C",
    notes=[
        _n(E4, 1.5, "la"), _n(E4, 0.5, "la"), _n(G4, 1, "la"),
        _n(A4, 0.5, "la"), _n(C5, 2.5, "la"),
        _n(A4, 0.5, "la"), _n(G4, 2, "la"),
        _n(E4, 1.5, "la"), _n(D4, 0.5, "la"), _n(E4, 1, "la"),
        _n(G4, 1, "la"), _n(A4, 2, "la"),
        _n(G4, 1, "la"), _n(E4, 1, "la"), _n(D4, 2, "la"),
        _n(C4, 2, "la"),
    ],
    tempo=70,
    tags=["进阶", "旋律", "民歌", "五声"],
    tip="中国民歌讲究'韵味'——装饰音不写出来，但心里要有。",
)


# ── 🚀 音域拓展 ───────────────────────────────────────

EXERCISES["range_extension_slide"] = _make_exercise(
    "range_extension_slide", "音域拓展滑音",
    "从 C4 滑到你能达到的最高音再滑回——用'oo'或唇颤音。"
    "每天扩展一点，像拉伸橡皮筋——温柔而持续。",
    difficulty=3, category="range", key="C",
    notes=[
        _n(C4, 4, "oo"), _n(C5, 2, "oo"), _n(G5, 4, "oo"),
        _n(C5, 2, "oo"), _n(C4, 4, "oo"),
    ],
    tempo=50,
    tags=["初级", "音域", "滑音", "拓展"],
    tip="不要硬冲——像拉筋一样，微微有拉伸感就够了。每天坚持比一次冲顶更重要。",
)

EXERCISES["range_low_extension"] = _make_exercise(
    "range_low_extension", "低音区拓展",
    "从 C4 下行八度到 C3，用'oh'元音。低音需要放松——"
    "喉咙打开，像叹气一样自然下沉。",
    difficulty=5, category="range", key="C",
    notes=[
        _n(C4, 2, "oh"), _n(B3, 2, "oh"),
        _n(A3, 2, "oh"), _n(G3, 2, "oh"),
        _n(F3, 2, "oh"), _n(E3, 2, "oh"),
        _n(D3, 2, "oh"), _n(C3, 4, "oh"),
    ],
    tempo=70, gap=0.3,
    tags=["进阶", "音域", "低音"],
    tip="低音不要压——像叹一口很深的气，声音自然到底。",
)

EXERCISES["range_high_extension"] = _make_exercise(
    "range_high_extension", "高音区拓展",
    "从 G4 逐步上探到 E5，用'yah'元音，短促有弹性。"
    "每个音站稳了再走下一个——高音是一场马拉松，不是短跑。",
    difficulty=8, category="range", key="C",
    notes=[
        _n(G4, 1.5, "yah"), _n(A4, 1.5, "yah"),
        _n(B4, 1.5, "yah"), _n(C5, 1.5, "yah"),
        _n(D5, 1.5, "yah"), _n(E5, 1.5, "yah"),
        _n(D5, 1, "yah"), _n(C5, 1, "yah"),
        _n(B4, 1, "yah"), _n(G4, 2, "yah"),
    ],
    tempo=85, gap=0.3,
    tags=["中级", "音域", "高音"],
    tip="上高音前先深吸+提软腭（打哈欠的感觉）——空间越大，高音越轻松。",
)


# ── 查询函数 ────────────────────────────────────────────

def get_exercise(exercise_id: str) -> Optional[VocalExercise]:
    """根据 ID 获取练习"""
    return EXERCISES.get(exercise_id)


def get_exercises_by_difficulty(max_difficulty: int = 3) -> List[VocalExercise]:
    """获取难度 ≤ max_difficulty 的练习，按难度排序"""
    exercises = [e for e in EXERCISES.values() if e.difficulty <= max_difficulty]
    exercises.sort(key=lambda e: (e.difficulty, e.name))
    return exercises


def get_exercises_by_category(category: str) -> List[VocalExercise]:
    """按类别筛选练习"""
    exercises = [e for e in EXERCISES.values() if e.category == category]
    exercises.sort(key=lambda e: (e.difficulty, e.name))
    return exercises


def get_exercises_by_tag(tag: str) -> List[VocalExercise]:
    """按标签筛选练习"""
    return [e for e in EXERCISES.values() if tag in e.tags]


def get_exercises_by_level(level: str) -> List[VocalExercise]:
    """按等级筛选：beginner(⭐), intermediate(⭐⭐-⭐⭐⭐), advanced(⭐⭐⭐⭐-⭐⭐⭐⭐⭐)"""
    if level == "beginner":
        exercises = [e for e in EXERCISES.values() if e.stars <= 1]
    elif level == "intermediate":
        exercises = [e for e in EXERCISES.values() if 2 <= e.stars <= 3]
    elif level == "advanced":
        exercises = [e for e in EXERCISES.values() if e.stars >= 4]
    else:
        exercises = list(EXERCISES.values())
    exercises.sort(key=lambda e: (e.difficulty, e.name))
    return exercises


def get_category_summary() -> List[dict]:
    """获取各分类概要（分类名、练习数、难度范围）"""
    result = []
    for cat_key in sorted(CATEGORIES.keys(), key=lambda k: CATEGORIES[k]["order"]):
        cat_info = CATEGORIES[cat_key]
        exercises = get_exercises_by_category(cat_key)
        if not exercises:
            continue
        diffs = [e.difficulty for e in exercises]
        result.append({
            "key": cat_key,
            "name": cat_info["name"],
            "icon": cat_info["icon"],
            "desc": cat_info["desc"],
            "count": len(exercises),
            "min_difficulty": min(diffs),
            "max_difficulty": max(diffs),
            "min_stars": _stars(min(diffs)),
            "max_stars": _stars(max(diffs)),
        })
    return result


def list_all_exercises() -> List[VocalExercise]:
    """列出所有练习，按难度→名称排序"""
    exercises = list(EXERCISES.values())
    exercises.sort(key=lambda e: (e.difficulty, e.name))
    return exercises


def get_exercise_ids_by_level(unlock_level: int = 0) -> List[str]:
    """获取课程模式下已解锁的练习 ID 列表"""
    return [e.id for e in EXERCISES.values() if e.unlock_level <= unlock_level]


def search_exercises(query: str) -> List[VocalExercise]:
    """模糊搜索练习（名称、描述、标签）"""
    q = query.lower()
    results = []
    for e in EXERCISES.values():
        if (q in e.name.lower()
                or q in e.description.lower()
                or q in e.category_name.lower()
                or q in e.category.lower()
                or any(q in t.lower() for t in e.tags)):
            results.append(e)
    results.sort(key=lambda e: (e.difficulty, e.name))
    return results


# ── 内部辅助 ────────────────────────────────────────────

def _midi_to_name(midi: int) -> str:
    """MIDI → 音名 (60 → 'C4')"""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (midi // 12) - 1
    return f"{names[midi % 12]}{octave}"


def _transpose_key_name(key: str, semitones: int) -> str:
    """移调调名 (如 'C' + 7 → 'G')"""
    key_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    if key in key_names:
        idx = key_names.index(key)
        return key_names[(idx + semitones) % 12]
    return key
