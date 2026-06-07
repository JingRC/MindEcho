"""声部鉴定测评对话框 —— VoiceTypeAssessmentDialog

四阶段声部鉴定流程:
  Entry   — 询问是否已知声部 → 手动填写 或 开始测评
  Phase 1 — 音域测定: 低音滑音 + 高音滑音，提取最低/最高舒适音
  Phase 2 — 换声点检测: 复用多特征融合检测逻辑
  Phase 3 — 音色分析: 持续元音录制，计算 FHE + Spectral Centroid
  Result  — 分类决策矩阵，输出声部 + 置信度 + 次选

分类依据 (权重):
  - 换声点 (45%): 最可靠指标，secondo passaggio 频率
  - 音域 (30%): 最低/最高舒适音 + 音域跨度
  - 音色 (25%): FHE (Frequency of Half Energy) + Spectral Centroid

参考数据来源:
  - Richard Miller 声乐教学文献 (passaggio zones)
  - Müller et al. 2022 Nature Scientific Reports (FHE per voice type)
  - 德国 Fach 体系 (range, tessitura, passaggio, timbre)
"""

from __future__ import annotations

import math
import time
import os
import tempfile
from typing import List, Optional, Tuple, Deque
from collections import deque

import numpy as np

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPointF
from PyQt6.QtGui import (
    QFont, QPainter, QColor, QPen, QLinearGradient, QBrush, QPainterPath,
    QFontMetrics,
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QFrame, QStackedWidget, QComboBox, QMessageBox,
    QSizePolicy, QScrollArea, QRadioButton,
)

# ── 可选音频依赖 ──
try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

from src.profiles.profile_model import SingerProfile, PassaggioData
from src.profiles.profile_manager import ProfileManager
from src.audio_processing.pitch_service import PitchDetectionService

# ── 常量 ──

SAMPLE_RATE = 44100
FRAME_SIZE = 4096
HOP_SIZE = 2048
MAX_RECORD_SECONDS = 25

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# ── 各声部换声点参考 (secondo passaggio, Hz) ──
_VOICE_TYPE_PASSAGGIO = {
    "bass":          294.0,   # D4
    "baritone":      349.0,   # F4  (~354Hz, 男中音标准值)
    "tenor":         392.0,   # G4
    "contralto":     587.0,   # D5
    "mezzo_soprano": 659.0,   # E5
    "soprano":       740.0,   # F#5
}

# ── 各声部换声点范围 (Hz) ──
_PASSAGGIO_RANGE = {
    "bass":          (247, 294),    # B3-D4
    "baritone":      (311, 392),    # D#4-G4
    "tenor":         (349, 440),    # F4-A4
    "contralto":     (523, 622),    # C5-D#5
    "mezzo_soprano": (622, 698),    # D#5-F5
    "soprano":       (698, 831),    # F5-G#5
}

# ── 各声部音域参考 (Hz): (最低舒适音中心, 最高舒适音中心, σ) ──
_RANGE_REFERENCE = {
    "bass":          (98.0, 311.0, 0.25),    # G2→D#4
    "baritone":      (123.5, 370.0, 0.25),   # B2→F#4
    "tenor":         (164.8, 440.0, 0.25),   # E3→A4
    "contralto":     (196.0, 659.3, 0.25),   # G3→E5
    "mezzo_soprano": (220.0, 740.0, 0.25),   # A3→F#5
    "soprano":       (261.6, 880.0, 0.25),   # C4→A5
}

# ── 各声部 FHE 参考值 (Hz ± SD), 来源: Müller et al. 2022 ──
_TIMBRE_FHE = {
    "bass":          2384,    # ± 164
    "baritone":      2454,    # ± 206
    "tenor":         2705,    # ± 221
    "contralto":     2800,    # estimated from literature
    "mezzo_soprano": 3000,    # estimated
    "soprano":       3300,    # estimated
}

# ── 显示名 ──
_VOICE_TYPE_DISPLAY = {
    "tenor": "男高音 (Tenor)",
    "baritone": "男中音 (Baritone)",
    "bass": "男低音 (Bass)",
    "soprano": "女高音 (Soprano)",
    "mezzo_soprano": "女中音 (Mezzo-Soprano)",
    "contralto": "女低音 (Contralto)",
}

_VOICE_TYPE_SHORT = {
    "tenor": "男高音", "baritone": "男中音", "bass": "男低音",
    "soprano": "女高音", "mezzo_soprano": "女中音", "contralto": "女低音",
}

_MALE_VOICE_TYPES = ["bass", "baritone", "tenor"]
_FEMALE_VOICE_TYPES = ["contralto", "mezzo_soprano", "soprano"]


# ═══════════════════════════════════════════════════════════════
# 独立评分函数（供外部报告生成使用，不依赖 UI）
# ═══════════════════════════════════════════════════════════════

def _score_passaggio_for_hz(passaggio_hz: float, voice_type: str) -> float:
    """评分换声点匹配度 (0-1) — 独立函数"""
    if passaggio_hz <= 0:
        return 0.5
    lo, hi = _PASSAGGIO_RANGE.get(voice_type, (0, 9999))
    if lo <= passaggio_hz <= hi:
        return 1.0
    center = (lo + hi) / 2
    dist_semitones = abs(12 * math.log2(passaggio_hz / center))
    return max(0.0, 1.0 - dist_semitones / 12.0)


def _score_range_for_hz(low_hz: float, high_hz: float, voice_type: str) -> float:
    """评分音域匹配度 (0-1) — 独立函数，sigma=0.5 octave"""
    if low_hz <= 0 or high_hz <= 0:
        return 0.5
    ref_low, ref_high, sigma = _RANGE_REFERENCE.get(voice_type, (100, 500, 0.5))
    low_ratio = math.log2(low_hz / ref_low)
    high_ratio = math.log2(high_hz / ref_high)
    s_low = math.exp(-0.5 * (low_ratio / sigma) ** 2)
    s_high = math.exp(-0.5 * (high_ratio / sigma) ** 2)
    return float(np.clip((s_low + s_high) / 2, 0.0, 1.0))


def _score_timbre_for_fhe(fhe_hz: float, voice_type: str) -> float:
    """评分音色匹配度 (0-1) — 独立函数，z-score 封顶 3.0"""
    if fhe_hz <= 0:
        return 0.5
    ref_fhe = _TIMBRE_FHE.get(voice_type, 2700)
    z = min(abs(fhe_hz - ref_fhe) / 220.0, 3.0)
    return float(np.clip(math.exp(-0.5 * z ** 2), 0.0, 1.0))


def generate_report_from_profile(profile, profile_manager) -> str:
    """从已保存的 profile 数据生成并导出 HTML 报告

    不依赖 VoiceTypeAssessmentDialog UI，可用于报告重生成。
    Returns: 报告文件路径 (str)
    """
    p = profile
    pp = p.passaggio
    ps = p.pitch_stats
    t = p.timbre

    passaggio_hz = pp.t4_hz
    passaggio_confidence = pp.confidence
    low_range_hz = ps.min_hz if ps.min_hz > 0 else 0.0
    high_range_hz = ps.max_hz if ps.max_hz > 0 else 0.0
    fhe_hz = t.fhe_hz
    spectral_centroid_hz = t.spectral_centroid_hz
    timbre_quality = t.timbre_quality
    best_vt = p.voice_type_inferred or ""

    if not best_vt:
        raise ValueError("profile 中未找到声部鉴定结果 (voice_type_inferred 为空)")

    candidates = _FEMALE_VOICE_TYPES if p.is_female else _MALE_VOICE_TYPES

    # 重新计算所有候选声部分数
    scores = {}
    for vt in candidates:
        s_passaggio = _score_passaggio_for_hz(passaggio_hz, vt)
        s_range = _score_range_for_hz(low_range_hz, high_range_hz, vt)
        s_timbre = _score_timbre_for_fhe(fhe_hz, vt)

        base_weights = {"passaggio": 0.45, "range": 0.30, "timbre": 0.25}
        available = 0.0
        pp_weight = 0.0
        if passaggio_hz > 0:
            pp_weight = base_weights["passaggio"] * max(0.25, passaggio_confidence)
            available += pp_weight
        if low_range_hz > 0 and high_range_hz > 0:
            available += base_weights["range"]
        if fhe_hz > 0:
            available += base_weights["timbre"]

        if available < 0.01:
            total = 1.0
        else:
            total = (
                (s_passaggio * pp_weight if passaggio_hz > 0 else 0) +
                (s_range * base_weights["range"] if low_range_hz > 0 else 0) +
                (s_timbre * base_weights["timbre"] if fhe_hz > 0 else 0)
            ) / available
        scores[vt] = total

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # 雷达数据
    radar = {}
    if low_range_hz > 0 and high_range_hz > 0:
        st_range = 12 * math.log2(high_range_hz / low_range_hz)
        radar["range"] = float(np.clip(st_range / 30.0, 0.0, 1.0))
    else:
        radar["range"] = 0.0
    radar["passaggio"] = passaggio_confidence if passaggio_hz > 0 else 0.0
    if fhe_hz > 0:
        ref_fhe = _TIMBRE_FHE.get(best_vt, 2700.0)
        radar["brightness"] = float(np.clip(0.5 + (fhe_hz - ref_fhe) / 440.0 * 0.25, 0.05, 0.95))
    else:
        radar["brightness"] = 0.0
    radar["quality"] = timbre_quality if fhe_hz > 0 else 0.0
    radar["stability"] = 0.0
    radar["dynamics"] = 0.0

    # gap / conf
    gap = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else 0.0
    if gap > 0.30:
        conf_pct = 0.85
    elif gap > 0.15:
        conf_pct = 0.65
    elif gap > 0.05:
        conf_pct = 0.45
    else:
        conf_pct = 0.30
    if passaggio_confidence > 0:
        conf_pct = 0.6 * conf_pct + 0.4 * passaggio_confidence

    # ── 用最小实例生成 HTML ──
    # 创建无 UI 的临时 dialog 对象，仅设置 generate_html_report 需要的字段
    dlg = VoiceTypeAssessmentDialog.__new__(VoiceTypeAssessmentDialog)
    dlg._profile = p
    dlg._mgr = profile_manager
    dlg._passaggio_hz = passaggio_hz
    dlg._passaggio_confidence = passaggio_confidence
    dlg._low_range_hz = low_range_hz
    dlg._high_range_hz = high_range_hz
    dlg._fhe_hz = fhe_hz
    dlg._phe = 0.5
    dlg._spectral_centroid_hz = spectral_centroid_hz
    dlg._timbre_quality = timbre_quality
    dlg._spr_db = 0.0
    dlg._alpha_ratio = 0.0
    dlg._vibrato_rate_hz = 0.0
    dlg._vibrato_extent_cents = 0.0
    dlg._clarity = 0.0
    dlg._dynamic_range_db = 0.0
    dlg._pitch_stability = 0.0
    dlg._full_audio = None

    html = dlg.generate_html_report()

    # 保存
    from pathlib import Path
    profile_dir = profile_manager._root / p.folder_name
    report_dir = profile_dir / "reports" if profile_dir.exists() else Path.home() / ".mindecho" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    import time as _time
    timestamp = _time.strftime("%Y%m%d_%H%M%S")
    filepath = report_dir / f"report_{timestamp}.html"
    filepath.write_text(html, encoding='utf-8')

    import webbrowser
    try:
        webbrowser.open(str(filepath))
    except Exception:
        pass

    return str(filepath)


def _hz_to_note_name(hz: float) -> str:
    if hz <= 0:
        return "—"
    midi = 69 + 12 * math.log2(hz / 440.0)
    note_idx = int(round(midi)) % 12
    octave = int(round(midi)) // 12 - 1
    return f"{_NOTE_NAMES[note_idx]}{octave}"


def _hz_to_midi(hz: float) -> float:
    if hz <= 0:
        return 0.0
    return 69 + 12 * math.log2(hz / 440.0)


# ═══════════════════════════════════════════════════════════════
# 主对话框
# ═══════════════════════════════════════════════════════════════

class VoiceTypeAssessmentDialog(QDialog):
    """声部鉴定测评对话框

    用法:
      dlg = VoiceTypeAssessmentDialog(profile, profile_manager, parent)
      if dlg.exec() == QDialog.DialogCode.Accepted:
          # profile.voice_type_inferred 已被更新并保存
          ...
    """

    PAGE_ENTRY = 0
    PAGE_MANUAL = 1
    PAGE_PHASE1_LOW = 2
    PAGE_PHASE1_HIGH = 3
    PAGE_PHASE2 = 4
    PAGE_PHASE3 = 5
    PAGE_RESULT = 6

    assessment_completed = pyqtSignal(str)  # profile.id

    def __init__(
        self,
        profile: SingerProfile,
        profile_manager: ProfileManager,
        parent: Optional[QWidget] = None,
        start_page: int = PAGE_ENTRY,  # 支持从指定阶段启动
    ):
        super().__init__(parent)
        self._profile = profile
        self._mgr = profile_manager
        self._start_page = start_page

        # ── 测评数据 ──
        self._known_voice_type: str = ""      # 手动填写的声部
        self._known_passaggio_hz: float = 0.0 # 手动填写的换声点
        self._known_range_low: str = ""       # 手动填写的最低音
        self._known_range_high: str = ""      # 手动填写的最高音
        self._training_years: int = 0         # 声乐训练年限

        # Phase 1 数据
        self._low_range_hz: float = 0.0       # 检测到的最低舒适音
        self._high_range_hz: float = 0.0      # 检测到的最高舒适音
        self._low_pitch_track: List[Tuple[float, float]] = []
        self._high_pitch_track: List[Tuple[float, float]] = []

        # Phase 2 数据 (换声点)
        self._p2_mode: str = "glissando"       # "glissando" | "chromatic"
        self._passaggio_hz: float = 0.0
        self._passaggio_confidence: float = 0.0
        self._passaggio_candidates: List[dict] = []
        self._manual_candidates: List[dict] = []  # 用户手动选取的候选点
        self._selected_candidate_index: int = 0  # 用户选择的候选点索引 (0=自动首选)

        # Phase 3 数据 (音色)
        self._fhe_hz: float = 0.0
        self._spectral_centroid_hz: float = 0.0
        self._timbre_quality: float = 0.0

        # 雷达图辅助数据
        self._dynamic_range_db: float = 0.0    # Phase 2 glissando RMS 动态范围 (dB)
        self._pitch_stability: float = 0.0     # Phase 3 元音 F0 稳定性 (0-1, 高=稳定)

        # P1: 扩展分析维度
        self._phe: float = 0.0                # PHE (Position of Half Energy), 0-1
        self._vibrato_rate_hz: float = 0.0    # Vibrato 速率 (Hz)
        self._vibrato_extent_cents: float = 0.0  # Vibrato 幅度 (cents)
        self._clarity: float = 0.0            # 发音清晰度 (0-1)
        self._spr_db: float = 0.0            # Singing Power Ratio (dB)
        self._alpha_ratio: float = 0.0        # Alpha Ratio (高频/低频能量比)

        # 录音状态
        self._is_recording = False
        self._record_start_time: float = 0.0
        self._audio_stream = None
        self._recorded_chunks: List[np.ndarray] = []
        self._display_timer: Optional[QTimer] = None
        self._pitch_track: List[Tuple[float, float]] = []
        self._current_freq: float = 0.0
        self._current_voiced: bool = False
        self._feature_track: List[Tuple[float, float, float, float, float, float, float, float]] = []  # (t, tilt, hnr, rms, l1l2, h2h3, f1, f2)
        self._current_tilt: float = 0.0
        self._current_hnr: float = 0.0
        self._current_rms: float = 0.0
        self._current_l1l2: float = 0.0
        self._current_h2h3: float = 1.0
        self._current_f1: float = 0.0
        self._current_f2: float = 0.0

        # 自适应噪声门限 (VAD) — 通过环境噪声校准步骤采集
        self._noise_floor: float = 0.0
        self._noise_samples: List[float] = []  # 校准期间收集的 RMS 采样
        self._voice_threshold: float = 0.004   # 保守回退值，校准后更新
        self._env_noise_floor: float = 0.0     # 预校准的环境噪声底噪（持久化，不随重新录音而丢失）

        # 环境噪声校准
        self._is_calibrating: bool = False
        self._calibration_countdown: int = 0
        self._calibration_timer: Optional[QTimer] = None

        # 临时文件
        self._full_audio: Optional[np.ndarray] = None

        # ── 音高检测服务 (使用主应用成熟的 YIN 实现) ──
        self._pitch_service = PitchDetectionService(
            sample_rate=SAMPLE_RATE,
            min_frequency=55.0,   # 支持极低男低音 (A1≈55Hz)
            max_frequency=1400.0,
            yin_threshold=0.10,
        )

        # ── UI ──
        self.setWindowTitle("🎤 声部鉴定测评")
        self.setMinimumSize(620, 620)
        self.setModal(True)
        self.setStyleSheet("VoiceTypeAssessmentDialog { background-color: #0D1117; }")

        self._build_ui()
        # 根据 start_page 跳转到指定阶段
        if self._start_page == self.PAGE_PHASE1_LOW:
            self._switch_page(self.PAGE_PHASE1_LOW)
            self._set_progress(1)
            self._back_btn.setVisible(True)
            self._next_btn.setText("▶ 开始低音区录音")
        elif self._start_page == self.PAGE_PHASE3:
            self._switch_page(self.PAGE_PHASE3)
            self._set_progress(3)
            self._back_btn.setVisible(True)
            self._next_btn.setText("▶ 开始录音（元音）")
        elif self._start_page == self.PAGE_PHASE2:
            self._switch_page(self.PAGE_PHASE2)
            self._set_progress(2)
            self._back_btn.setVisible(True)
            self._next_btn.setText("▶ 开始滑音录音")
        else:
            self._switch_page(self.PAGE_ENTRY)

        if not HAS_SOUNDDEVICE:
            self._show_warning("sounddevice 未安装，录音功能不可用。\n请运行: pip install sounddevice")

    # ═══════════════════════════════════════════════════════════
    # UI 框架
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # 进度条
        main_layout.addWidget(self._build_progress())

        # 页面栈
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._stack.addWidget(self._build_entry_page())
        self._stack.addWidget(self._build_manual_page())
        self._stack.addWidget(self._build_phase1_low_page())
        self._stack.addWidget(self._build_phase1_high_page())
        self._stack.addWidget(self._build_phase2_page())
        self._stack.addWidget(self._build_phase3_page())
        self._stack.addWidget(self._build_result_page())
        main_layout.addWidget(self._stack, 1)

        # 底部导航
        main_layout.addWidget(self._build_nav())

    def _build_progress(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        steps = [("📋", "入口"), ("🎵", "音域测定"), ("🔄", "换声点"), ("🎨", "音色分析"), ("📊", "结果")]

        self._progress_dots: List[QLabel] = []
        self._progress_texts: List[QLabel] = []

        for i, (icon, label) in enumerate(steps):
            step_w = QWidget()
            step_w.setStyleSheet("background: transparent;")
            sl = QVBoxLayout(step_w)
            sl.setContentsMargins(0, 0, 0, 0)
            sl.setSpacing(2)
            sl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            dot = QLabel(icon)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setStyleSheet("font-size: 16px; background: transparent; color: #484F58;")
            sl.addWidget(dot)

            txt = QLabel(label)
            txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            txt.setStyleSheet("font-size: 9px; color: #484F58; background: transparent;")
            sl.addWidget(txt)

            self._progress_dots.append(dot)
            self._progress_texts.append(txt)
            layout.addWidget(step_w)

            if i < len(steps) - 1:
                sep = QLabel("—")
                sep.setStyleSheet("color: #21262D; font-size: 10px; background: transparent;")
                layout.addWidget(sep)

        return widget

    def _set_progress(self, active: int) -> None:
        for i, (dot, txt) in enumerate(zip(self._progress_dots, self._progress_texts)):
            if i <= active:
                dot.setStyleSheet("font-size: 16px; background: transparent; color: #58A6FF;")
                txt.setStyleSheet("font-size: 9px; color: #58A6FF; background: transparent; font-weight: bold;")
            else:
                dot.setStyleSheet("font-size: 16px; background: transparent; color: #484F58;")
                txt.setStyleSheet("font-size: 9px; color: #484F58; background: transparent;")

    def _build_nav(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._back_btn = QPushButton("← 上一步")
        self._back_btn.setMinimumHeight(36)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet("""
            QPushButton { background: #21262D; color: #C9D1D9; padding: 8px 18px;
                border-radius: 8px; font-size: 12px; border: 1px solid #30363D; }
            QPushButton:hover { background: #30363D; }
        """)
        self._back_btn.clicked.connect(self._on_back)
        self._back_btn.setVisible(False)
        layout.addWidget(self._back_btn)

        layout.addStretch()

        self._next_btn = QPushButton("开始测评 →")
        self._next_btn.setMinimumHeight(36)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #58A6FF, stop:1 #A78BFA); color: #FFFFFF; font-weight: bold;
                padding: 8px 24px; border-radius: 8px; font-size: 12px; border: none; }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #79B8FF, stop:1 #B794F4); }
            QPushButton:disabled { background: #21262D; color: #484F58; }
        """)
        self._next_btn.clicked.connect(self._on_next)
        layout.addWidget(self._next_btn)

        skip_btn = QPushButton("跳过测评")
        skip_btn.setMinimumHeight(36)
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #8B949E; padding: 8px 14px;
                border-radius: 8px; font-size: 11px; border: 1px solid #30363D; }
            QPushButton:hover { background: #21262D; color: #C9D1D9; }
        """)
        skip_btn.clicked.connect(self.reject)
        layout.addWidget(skip_btn)

        return widget

    # ═══════════════════════════════════════════════════════════
    # 页面构建
    # ═══════════════════════════════════════════════════════════

    def _section(self, title: str, content_widget: QWidget) -> QWidget:
        """带标题的 section 容器"""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)

        header = QLabel(title)
        header.setStyleSheet("color: #E6EDF3; font-size: 14px; font-weight: bold; background: transparent;")
        l.addWidget(header)

        card = QFrame()
        card.setStyleSheet("""
            QFrame { background: #161B22; border: 1px solid #30363D; border-radius: 10px; }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.addWidget(content_widget)
        l.addWidget(card)
        return w

    # ── Entry 页 ──

    def _build_entry_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(18)

        # Hero
        hero = QFrame()
        hero.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1A1F2E, stop:0.5 #1C2333, stop:1 #1A2030);
                border: 1px solid #30363D; border-radius: 12px;
            }
        """)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        hero_layout.setSpacing(8)

        title = QLabel("🎤 声部鉴定")
        title.setStyleSheet("color: #E6EDF3; font-size: 20px; font-weight: bold; background: transparent;")
        hero_layout.addWidget(title)

        desc = QLabel(
            "声部（Voice Type）决定了你最适合演唱的音域和作品风格。\n"
            "本测评通过音域测定、换声点检测和音色分析，综合判断你的声部类型。"
        )
        desc.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
        desc.setWordWrap(True)
        hero_layout.addWidget(desc)

        note = QLabel("⏱ 测评约需 3 分钟　｜　🔄 非强制，可随时跳过　｜　🔒 数据仅本地保存")
        note.setStyleSheet("color: #484F58; font-size: 10px; background: transparent;")
        hero_layout.addWidget(note)

        layout.addWidget(hero)

        # 问题
        q_label = QLabel("你是否已经知道自己的声部信息？")
        q_label.setStyleSheet("color: #E6EDF3; font-size: 15px; font-weight: bold; background: transparent;")
        layout.addWidget(q_label)

        # 选项按钮
        btn_known = QPushButton("✅ 是的，我是专业歌手 / 已有声部判断\n　　　直接填写声部、换声点和音域信息")
        btn_known.setMinimumHeight(58)
        btn_known.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_known.setStyleSheet("""
            QPushButton { background: #161B22; color: #E6EDF3; padding: 12px 20px;
                border-radius: 10px; font-size: 12px; border: 1px solid #30363D;
                text-align: left; }
            QPushButton:hover { background: #1C2533; border-color: #58A6FF; }
        """)
        btn_known.clicked.connect(lambda: self._on_entry_choice("known"))
        layout.addWidget(btn_known)

        btn_assess = QPushButton("🔍 我不确定，开始测评\n　　　通过音域 + 换声点 + 音色综合测定（约3分钟）")
        btn_assess.setMinimumHeight(58)
        btn_assess.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_assess.setStyleSheet("""
            QPushButton { background: #161B22; color: #E6EDF3; padding: 12px 20px;
                border-radius: 10px; font-size: 12px; border: 1px solid #30363D;
                text-align: left; }
            QPushButton:hover { background: #1C2533; border-color: #A78BFA; }
        """)
        btn_assess.clicked.connect(lambda: self._on_entry_choice("assess"))
        layout.addWidget(btn_assess)

        layout.addStretch()
        return page

    def _on_entry_choice(self, choice: str) -> None:
        if choice == "known":
            self._switch_page(self.PAGE_MANUAL)
            self._back_btn.setVisible(True)
            self._next_btn.setText("💾 保存并应用")
        else:
            self._switch_page(self.PAGE_PHASE1_LOW)
            self._set_progress(1)
            self._back_btn.setVisible(True)
            self._next_btn.setText("▶ 开始录音（低音区）")

    # ── Manual 页 ──

    def _build_manual_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)

        title = QLabel("📋 填写声部信息")
        title.setStyleSheet("color: #E6EDF3; font-size: 18px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        # 声部选择
        vt_label = QLabel("你的声部类型")
        vt_label.setStyleSheet("color: #C9D1D9; font-size: 12px; background: transparent;")
        layout.addWidget(vt_label)

        self._manual_voice = QComboBox()
        self._manual_voice.setMinimumHeight(36)
        self._manual_voice.addItem("请选择...", "")
        for key in ["tenor", "baritone", "bass", "soprano", "mezzo_soprano", "contralto"]:
            self._manual_voice.addItem(_VOICE_TYPE_SHORT[key], key)
        self._manual_voice.setStyleSheet("""
            QComboBox { background: #161B22; color: #E6EDF3; padding: 8px 14px;
                border: 1px solid #30363D; border-radius: 8px; font-size: 12px; }
            QComboBox:hover { border-color: #58A6FF; }
            QComboBox QAbstractItemView { background: #161B22; color: #E6EDF3;
                selection-background-color: #1F2A3A; border: 1px solid #30363D; }
        """)
        layout.addWidget(self._manual_voice)

        # 换声点
        pp_label = QLabel("你的换声点（Secondo Passaggio，如已知）")
        pp_label.setStyleSheet("color: #C9D1D9; font-size: 12px; background: transparent;")
        layout.addWidget(pp_label)

        pp_row = QHBoxLayout()
        self._manual_pp_note = QComboBox()
        self._manual_pp_note.setMinimumHeight(36)
        self._manual_pp_note.addItem("不指定", "")
        for midi in range(48, 85):  # C3 - C6
            hz = 440.0 * (2 ** ((midi - 69) / 12))
            note_name = _hz_to_note_name(hz)
            self._manual_pp_note.addItem(f"{note_name} ({hz:.0f} Hz)", str(int(hz)))
        self._manual_pp_note.setStyleSheet(self._manual_voice.styleSheet())
        pp_row.addWidget(self._manual_pp_note)
        layout.addLayout(pp_row)

        # 音域
        range_label = QLabel("你的舒适音域（最低音 → 最高音，如已知）")
        range_label.setStyleSheet("color: #C9D1D9; font-size: 12px; background: transparent;")
        layout.addWidget(range_label)

        range_row = QHBoxLayout()

        self._manual_low = QComboBox()
        self._manual_low.setMinimumHeight(36)
        self._manual_low.addItem("最低音...", "")
        for midi in range(28, 73):  # E1 - C5
            hz = 440.0 * (2 ** ((midi - 69) / 12))
            note_name = _hz_to_note_name(hz)
            self._manual_low.addItem(note_name, str(int(hz)))
        self._manual_low.setStyleSheet(self._manual_voice.styleSheet())
        range_row.addWidget(QLabel("最低："))
        range_row.addWidget(self._manual_low)

        range_row.addWidget(QLabel("  →  "))

        self._manual_high = QComboBox()
        self._manual_high.setMinimumHeight(36)
        self._manual_high.addItem("最高音...", "")
        for midi in range(48, 97):  # C3 - C#7
            hz = 440.0 * (2 ** ((midi - 69) / 12))
            note_name = _hz_to_note_name(hz)
            self._manual_high.addItem(note_name, str(int(hz)))
        self._manual_high.setStyleSheet(self._manual_voice.styleSheet())
        range_row.addWidget(QLabel("最高："))
        range_row.addWidget(self._manual_high)
        layout.addLayout(range_row)

        # 训练年限
        yr_label = QLabel("声乐训练年限（可选）")
        yr_label.setStyleSheet("color: #C9D1D9; font-size: 12px; background: transparent;")
        layout.addWidget(yr_label)

        self._manual_years = QComboBox()
        self._manual_years.setMinimumHeight(36)
        self._manual_years.addItem("无正式训练", "0")
        self._manual_years.addItem("1-2 年", "1")
        self._manual_years.addItem("3-5 年", "3")
        self._manual_years.addItem("6-10 年", "6")
        self._manual_years.addItem("10 年以上", "10")
        self._manual_years.setStyleSheet(self._manual_voice.styleSheet())
        layout.addWidget(self._manual_years)

        layout.addStretch()
        return page

    # ── Phase 1 Low 页 ──

    def _build_phase1_low_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)

        title = QLabel("🎵 Phase 1/3 — 低音区测定")
        title.setStyleSheet("color: #E6EDF3; font-size: 18px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        guide = QLabel(
            "📖 指导：\n"
            "① 从你说话最舒服的音高开始，用\"呼———\"的下行滑音缓慢往下唱\n"
            "② 保持自然音量，不要刻意压喉或气泡音\n"
            "③ 当声音开始\"劈\"、断掉、或完全发不出声时，就是你当前的下限\n"
            "④ 系统自动从滑音轨迹中提取最低舒适音（约 P10 百分位）"
        )
        guide.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
        guide.setWordWrap(True)
        layout.addWidget(guide)

        self._p1_low_status = QLabel("⏸ 等待开始录音...")
        self._p1_low_status.setStyleSheet("color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;")
        layout.addWidget(self._p1_low_status)

        # 实时反馈区 — 当前音高大字
        self._p1_low_feedback = QLabel("")
        self._p1_low_feedback.setMinimumHeight(50)
        self._p1_low_feedback.setMaximumHeight(50)
        self._p1_low_feedback.setStyleSheet("""
            color: #58A6FF; font-size: 26px; font-weight: bold;
            background: #161B22; border: 2px solid #30363D; border-radius: 10px;
            padding: 8px;
        """)
        self._p1_low_feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._p1_low_feedback)

        # 实时音高轨迹画布 (300px 高, C1-C7 八度标签完整显示)
        self._p1_low_canvas = _PitchTraceCanvas()
        self._p1_low_canvas.setMinimumHeight(300)
        self._p1_low_canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        layout.addWidget(self._p1_low_canvas, 1)

        # 检测到的音
        self._p1_low_detected = QLabel("")
        self._p1_low_detected.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
        layout.addWidget(self._p1_low_detected)

        # 重新测试按钮 (录音完成后显示)
        self._p1_low_retry_btn = QPushButton("🔄 重新测试")
        self._p1_low_retry_btn.setVisible(False)
        self._p1_low_retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._p1_low_retry_btn.clicked.connect(self._on_p1_low_retry)
        self._p1_low_retry_btn.setStyleSheet("""
            QPushButton {
                background: #21262D; color: #C9D1D9; border: 1px solid #30363D;
                border-radius: 8px; padding: 8px 16px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover {
                background: #30363D; border-color: #F0883E; color: #F0883E;
            }
        """)
        layout.addWidget(self._p1_low_retry_btn)

        layout.addStretch()
        return page

    # ── Phase 1 High 页 ──

    def _build_phase1_high_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)

        title = QLabel("🎵 Phase 1/3 — 高音区测定")
        title.setStyleSheet("color: #E6EDF3; font-size: 18px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        guide = QLabel(
            "📖 指导：\n"
            "从舒适的中音区开始，用真声或混声往上滑唱。\n"
            "找到你能用真声/混声稳定发出的最高音。\n"
            "不要强行转假声——当你感觉必须\"翻\"到假声才能继续时，\n"
            "那个翻转点之前的最高音就是你的舒适上限。"
        )
        guide.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
        guide.setWordWrap(True)
        layout.addWidget(guide)

        self._p1_high_status = QLabel("⏸ 等待开始录音...")
        self._p1_high_status.setStyleSheet("color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;")
        layout.addWidget(self._p1_high_status)

        # 实时反馈区 — 当前音高大字
        self._p1_high_feedback = QLabel("")
        self._p1_high_feedback.setMinimumHeight(50)
        self._p1_high_feedback.setMaximumHeight(50)
        self._p1_high_feedback.setStyleSheet("""
            color: #A78BFA; font-size: 26px; font-weight: bold;
            background: #161B22; border: 2px solid #30363D; border-radius: 10px;
            padding: 8px;
        """)
        self._p1_high_feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._p1_high_feedback)

        # 实时音高轨迹画布 (300px 高, C1-C7 八度标签完整显示)
        self._p1_high_canvas = _PitchTraceCanvas()
        self._p1_high_canvas.setMinimumHeight(300)
        self._p1_high_canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        layout.addWidget(self._p1_high_canvas, 1)

        self._p1_high_detected = QLabel("")
        self._p1_high_detected.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
        layout.addWidget(self._p1_high_detected)

        # 重新测试按钮 (录音完成后显示)
        self._p1_high_retry_btn = QPushButton("🔄 重新测试")
        self._p1_high_retry_btn.setVisible(False)
        self._p1_high_retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._p1_high_retry_btn.clicked.connect(self._on_p1_high_retry)
        self._p1_high_retry_btn.setStyleSheet("""
            QPushButton {
                background: #21262D; color: #C9D1D9; border: 1px solid #30363D;
                border-radius: 8px; padding: 8px 16px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover {
                background: #30363D; border-color: #F0883E; color: #F0883E;
            }
        """)
        layout.addWidget(self._p1_high_retry_btn)

        layout.addStretch()
        return page

    # ── Phase 2 页 (换声点) ──

    def _build_phase2_page(self) -> QWidget:
        # ── 外层 ScrollArea — 内容较多，允许上下滚动 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            QScrollBar:vertical {
                background: #0D1117; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #30363D; border-radius: 4px; min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #484F58; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)

        title = QLabel("🔄 Phase 2/3 — 换声点检测")
        title.setStyleSheet("color: #E6EDF3; font-size: 18px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        # ── 模式选择 ──
        mode_label = QLabel("🎵 选择演唱方式")
        mode_label.setStyleSheet("color: #C9D1D9; font-size: 13px; font-weight: bold; background: transparent;")
        layout.addWidget(mode_label)

        mode_card = QFrame()
        mode_card.setStyleSheet("""
            QFrame { background: #161B22; border: 1px solid #30363D; border-radius: 10px; }
        """)
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setContentsMargins(16, 14, 16, 14)
        mode_layout.setSpacing(8)

        # 滑音模式 (默认)
        self._p2_glissando_radio = QRadioButton("滑音 (Glissando) — 推荐 ✨")
        self._p2_glissando_radio.setChecked(True)
        self._p2_glissando_radio.setCursor(Qt.CursorShape.PointingHandCursor)
        self._p2_glissando_radio.toggled.connect(self._on_p2_mode_changed)
        self._p2_glissando_radio.setStyleSheet("""
            QRadioButton { color: #E6EDF3; font-size: 12px; font-weight: bold;
                background: transparent; spacing: 8px; padding: 4px 0; }
            QRadioButton::indicator { width: 16px; height: 16px; }
            QRadioButton::indicator:unchecked {
                border: 2px solid #30363D; border-radius: 8px; background: #0D1117; }
            QRadioButton::indicator:checked {
                border: 2px solid #58A6FF; border-radius: 8px; background: #58A6FF; }
        """)
        mode_layout.addWidget(self._p2_glissando_radio)

        self._p2_glissando_hint = QLabel(
            "  像救护车鸣笛一样，用「啊——」从低音缓慢连续滑到高音。\n"
            "  更自然、更容易暴露换声点，适合大多数人。"
        )
        self._p2_glissando_hint.setStyleSheet(
            "color: #8B949E; font-size: 11px; background: transparent; line-height: 1.4;"
        )
        self._p2_glissando_hint.setWordWrap(True)
        mode_layout.addWidget(self._p2_glissando_hint)

        # 半音阶模式
        self._p2_chromatic_radio = QRadioButton("半音阶 (Chromatic Scale)")
        self._p2_chromatic_radio.setCursor(Qt.CursorShape.PointingHandCursor)
        self._p2_chromatic_radio.toggled.connect(self._on_p2_mode_changed)
        self._p2_chromatic_radio.setStyleSheet("""
            QRadioButton { color: #E6EDF3; font-size: 12px; font-weight: bold;
                background: transparent; spacing: 8px; padding: 4px 0; }
            QRadioButton::indicator { width: 16px; height: 16px; }
            QRadioButton::indicator:unchecked {
                border: 2px solid #30363D; border-radius: 8px; background: #0D1117; }
            QRadioButton::indicator:checked {
                border: 2px solid #58A6FF; border-radius: 8px; background: #58A6FF; }
        """)
        mode_layout.addWidget(self._p2_chromatic_radio)

        self._p2_chromatic_hint = QLabel(
            "  半音半音逐级上升，每个音保持约 1-1.5 秒。\n"
            "  更精确，适合有一定声乐基础的用户。唱到声音\"翻\"了的那个音即为换声点。"
        )
        self._p2_chromatic_hint.setStyleSheet(
            "color: #8B949E; font-size: 11px; background: transparent; line-height: 1.4;"
        )
        self._p2_chromatic_hint.setWordWrap(True)
        mode_layout.addWidget(self._p2_chromatic_hint)

        layout.addWidget(mode_card)

        # 指导文本 (根据模式动态更新)
        self._p2_guide = QLabel(
            "📖 指导：\n"
            "从现在检测到的低音附近开始，用连续的滑音（glissando）\n"
            "缓慢地往上唱，一直唱到高音区。保持自然音量，不要刻意用力。\n"
            "系统会通过分析频谱倾斜、音高变化、谐波噪声比等特征，\n"
            "自动识别胸声→头声的转换点（Secondo Passaggio）。"
        )
        self._p2_guide.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
        self._p2_guide.setWordWrap(True)
        layout.addWidget(self._p2_guide)

        self._p2_status = QLabel("⏸ 等待开始录音...")
        self._p2_status.setStyleSheet(
            "color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(self._p2_status)

        # 实时音高轨迹画布
        self._p2_canvas = _PitchTraceCanvas()
        self._p2_canvas.passaggio_selected.connect(self._on_piano_passaggio_selected)
        self._p2_canvas.setMinimumHeight(180)
        self._p2_canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        layout.addWidget(self._p2_canvas)

        # 实时音高显示
        self._p2_pitch_display = QLabel("")
        self._p2_pitch_display.setMinimumHeight(40)
        self._p2_pitch_display.setMaximumHeight(40)
        self._p2_pitch_display.setStyleSheet("""
            color: #58A6FF; font-size: 20px; font-weight: bold;
            background: #161B22; border: 2px solid #30363D; border-radius: 10px;
            padding: 6px;
        """)
        self._p2_pitch_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._p2_pitch_display)

        # 试听当前换声点按钮
        preview_row = QHBoxLayout()
        self._p2_preview_btn = QPushButton("🔊 试听当前换声点 (0.5s)")
        self._p2_preview_btn.setToolTip("截取换声点附近 0.5 秒录音进行试听\n帮助判断该位置是否确实是换声发声位置")
        self._p2_preview_btn.setStyleSheet("""
            QPushButton {
                background: #1A2540; border: 1px solid #30363D; border-radius: 6px;
                padding: 6px 16px; color: #8B949E; font-size: 12px;
            }
            QPushButton:hover {
                background: #1F3050; border-color: #58A6FF; color: #58A6FF;
            }
        """)
        self._p2_preview_btn.clicked.connect(
            lambda: self._preview_audio_at_hz(self._passaggio_hz) if self._passaggio_hz > 0 else None
        )
        self._p2_preview_btn.setVisible(False)
        preview_row.addStretch()
        preview_row.addWidget(self._p2_preview_btn)
        preview_row.addStretch()
        layout.addLayout(preview_row)

        # 检测状态
        self._p2_detect_status = QLabel("")
        self._p2_detect_status.setStyleSheet("color: #8B949E; font-size: 11px; background: transparent;")
        layout.addWidget(self._p2_detect_status)

        # ── 候选点卡片 (检测后显示, 可点击选择) ──
        self._p2_candidates_card = QFrame()
        self._p2_candidates_card.setStyleSheet("""
            QFrame { background: #161B22; border: 1px solid #21262D; border-radius: 8px; }
        """)
        self._p2_candidates_card.setVisible(False)
        cand_outer = QVBoxLayout(self._p2_candidates_card)
        cand_outer.setContentsMargins(14, 10, 14, 10)
        cand_outer.setSpacing(6)

        cand_title_row = QHBoxLayout()
        cand_title = QLabel("📊 候选换声点")
        cand_title.setStyleSheet("color: #8B949E; font-size: 11px; font-weight: bold; background: transparent;")
        cand_title_row.addWidget(cand_title)
        cand_hint = QLabel("（点击可选择，系统自动选 #1）")
        cand_hint.setStyleSheet("color: #6E7681; font-size: 10px; background: transparent;")
        cand_title_row.addWidget(cand_hint)
        cand_title_row.addStretch()
        cand_outer.addLayout(cand_title_row)

        self._p2_candidate_cards: List[QFrame] = []
        self._p2_candidate_checkmarks: List[QLabel] = []
        self._p2_candidate_name_labels: List[QLabel] = []
        self._p2_candidate_detail_labels: List[QLabel] = []
        self._p2_candidate_preview_btns: List[QPushButton] = []
        # 动态候选行容器 (替代 cand_outer 中直接添加)
        self._p2_candidates_layout = QVBoxLayout()
        self._p2_candidates_layout.setSpacing(6)
        cand_outer.addLayout(self._p2_candidates_layout)

        layout.addWidget(self._p2_candidates_card)

        # ── 钢琴键盘可视化 (检测后显示, 左右箭头滚屏) ──
        piano_hint = QLabel("💡 点击 ◀ ▶ 箭头滚动键盘，点击琴键试听音高")
        piano_hint.setStyleSheet("color: #6E7681; font-size: 10px; background: transparent;")
        piano_hint.setVisible(False)
        layout.addWidget(piano_hint)
        self._p2_piano_hint = piano_hint

        # 箭头 + 钢琴的横向布局
        piano_row = QHBoxLayout()
        piano_row.setContentsMargins(0, 0, 0, 0)
        piano_row.setSpacing(4)

        # 左箭头
        self._p2_piano_left_btn = QPushButton("◀")
        self._p2_piano_left_btn.setFixedSize(28, 85)
        self._p2_piano_left_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._p2_piano_left_btn.setVisible(False)
        self._p2_piano_left_btn.setStyleSheet("""
            QPushButton {
                background: #21262D; color: #8B949E; border: 1px solid #30363D;
                border-radius: 6px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover {
                background: #30363D; color: #E6EDF3; border-color: #58A6FF;
            }
            QPushButton:pressed {
                background: #1A1F26; color: #58A6FF;
            }
        """)
        piano_row.addWidget(self._p2_piano_left_btn)

        # 钢琴
        self._p2_piano = _PianoKeyboardWidget()
        self._p2_piano.setMinimumHeight(85)
        self._p2_piano.setMaximumHeight(95)
        self._p2_piano.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._p2_piano.setVisible(False)
        self._p2_piano.passaggio_selected.connect(self._on_piano_passaggio_selected)
        piano_row.addWidget(self._p2_piano, 1)

        # 右箭头
        self._p2_piano_right_btn = QPushButton("▶")
        self._p2_piano_right_btn.setFixedSize(28, 85)
        self._p2_piano_right_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._p2_piano_right_btn.setVisible(False)
        self._p2_piano_right_btn.setStyleSheet("""
            QPushButton {
                background: #21262D; color: #8B949E; border: 1px solid #30363D;
                border-radius: 6px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover {
                background: #30363D; color: #E6EDF3; border-color: #58A6FF;
            }
            QPushButton:pressed {
                background: #1A1F26; color: #58A6FF;
            }
        """)
        piano_row.addWidget(self._p2_piano_right_btn)

        # 连接箭头到滚动
        def _on_left():
            self._p2_piano.scroll_by(-self._p2_piano.width() * 0.45)
        def _on_right():
            self._p2_piano.scroll_by(self._p2_piano.width() * 0.45)

        self._p2_piano_left_btn.clicked.connect(_on_left)
        self._p2_piano_right_btn.clicked.connect(_on_right)

        layout.addLayout(piano_row)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _on_p2_mode_changed(self) -> None:
        """当用户切换滑音/半音模式时更新指导文本"""
        if self._p2_glissando_radio.isChecked():
            self._p2_guide.setText(
                "📖 指导（滑音模式）：\n"
                "从现在检测到的低音附近开始，用连续的滑音（glissando）\n"
                "缓慢地往上唱，一直唱到高音区。保持自然音量，不要刻意用力。\n"
                "像救护车鸣笛一样「啊————」连续滑上去。"
            )
        else:
            self._p2_guide.setText(
                "📖 指导（半音阶模式）：\n"
                "从你舒适的中低音开始，逐一半音向上唱。\n"
                "每个音保持约 1-1.5 秒，用钢琴/键盘辅助找音准。\n"
                "唱到某个音突然\"翻\"成假声或发不出声时，那个音就是换声点。\n"
                "💡 如果唱不上去，不要强行用力——系统会记录转折特征。"
            )

    # ── Phase 3 页 (音色) ──

    def _build_phase3_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)

        title = QLabel("🎨 Phase 3/3 — 音色分析")
        title.setStyleSheet("color: #E6EDF3; font-size: 18px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        # 推荐音高
        note_hint = self._get_mid_note_hint()
        guide = QLabel(
            f"📖 指导：\n"
            f"用你最自然的说话感（胸声/真声）唱一个持续的长元音 \"啊———\"（约8秒）。\n"
            f"建议音高：{note_hint}（你的中音区舒适音）\n"
            f"⚠️ 重要：请用真声而非假声！不要唱太高，用你说话的音高即可。\n"
            f"   音色分析依赖你自然声区的频谱特征，假声/过高音高会导致误判。\n"
            f"💡 录音时屏幕会实时显示音高，尽量保持稳定（波动<±20音分最佳）。\n"
            f"📊 分析维度：FHE · PHE · SPR · 频谱重心 · 音色质量 · Vibrato"
        )
        guide.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
        guide.setWordWrap(True)
        layout.addWidget(guide)

        self._p3_status = QLabel("⏸ 等待开始录音...")
        self._p3_status.setStyleSheet("color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;")
        layout.addWidget(self._p3_status)

        self._p3_freq_display = QLabel("")
        self._p3_freq_display.setMinimumHeight(50)
        self._p3_freq_display.setStyleSheet("""
            color: #A78BFA; font-size: 26px; font-weight: bold;
            background: #161B22; border: 2px solid #30363D; border-radius: 10px;
            padding: 10px;
        """)
        self._p3_freq_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._p3_freq_display)

        self._p3_timbre_info = QLabel("")
        self._p3_timbre_info.setStyleSheet("color: #8B949E; font-size: 11px; background: transparent;")
        layout.addWidget(self._p3_timbre_info)

        layout.addStretch()
        return page

    def _get_mid_note_hint(self) -> str:
        """推荐的中音区元音音高"""
        if self._profile.is_female:
            return "G4 或 A4 (约 392-440 Hz)"
        else:
            return "G3 或 A3 (约 196-220 Hz)"

    # ── Result 页 ──

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")

        # 内容容器
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)

        title = QLabel("📊 声部鉴定结果")
        title.setStyleSheet("color: #E6EDF3; font-size: 20px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        self._result_primary = QLabel("")
        self._result_primary.setMinimumHeight(60)
        self._result_primary.setStyleSheet("""
            color: #FFFFFF; font-size: 30px; font-weight: bold;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #238636, stop:1 #1F6FEB);
            border-radius: 12px; padding: 16px;
        """)
        self._result_primary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._result_primary)

        self._result_confidence = QLabel("")
        self._result_confidence.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
        self._result_confidence.setWordWrap(True)
        layout.addWidget(self._result_confidence)

        # ── 可视化行: 条形图 + 雷达图并排 ──
        viz_row = QHBoxLayout()
        viz_row.setSpacing(12)

        self._result_bar_chart = _ScoreBarChart()
        self._result_bar_chart.setMinimumHeight(158)
        self._result_bar_chart.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        viz_row.addWidget(self._result_bar_chart, 1)

        self._result_radar_chart = _RadarChart()
        self._result_radar_chart.setMinimumSize(240, 240)
        self._result_radar_chart.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        viz_row.addWidget(self._result_radar_chart)

        layout.addLayout(viz_row)

        # 详细数据
        self._result_details = QLabel("")
        self._result_details.setStyleSheet("""
            color: #C9D1D9; font-size: 12px; background: #161B22;
            border: 1px solid #30363D; border-radius: 10px; padding: 14px;
        """)
        self._result_details.setWordWrap(True)
        layout.addWidget(self._result_details)

        # 频谱缩略图
        self._result_spectrum = _SpectrumThumbnail()
        self._result_spectrum.setMinimumHeight(140)
        layout.addWidget(self._result_spectrum)

        # 导出报告按钮
        export_row = QHBoxLayout()
        export_row.addStretch()
        self._result_export_btn = QPushButton("📄 导出 HTML 报告")
        self._result_export_btn.setMinimumHeight(36)
        self._result_export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._result_export_btn.setStyleSheet("""
            QPushButton {
                color: #FFFFFF; font-size: 13px; font-weight: bold;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #238636, stop:1 #1F6FEB);
                border: none; border-radius: 8px; padding: 8px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2EA043, stop:1 #388BFD);
            }
        """)
        self._result_export_btn.clicked.connect(self._export_report)
        self._result_export_btn.setVisible(False)  # 仅在有结果时显示
        export_row.addWidget(self._result_export_btn)
        export_row.addStretch()
        layout.addLayout(export_row)

        # 分数分解
        self._result_scores = QLabel("")
        self._result_scores.setStyleSheet("color: #8B949E; font-size: 11px; background: transparent;")
        self._result_scores.setWordWrap(True)
        layout.addWidget(self._result_scores)

        layout.addStretch()

        # ── 包裹在 ScrollArea 中 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: #0D1117; width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #30363D; border-radius: 4px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return page

    # ═══════════════════════════════════════════════════════════
    # 页面导航
    # ═══════════════════════════════════════════════════════════

    def _switch_page(self, page_idx: int) -> None:
        self._stack.setCurrentIndex(page_idx)

    def _on_back(self) -> None:
        # 如果正在录音或校准中，先停止
        if self._is_recording or self._is_calibrating:
            self._stop_audio_stream()
            self._next_btn.setEnabled(True)

        current = self._stack.currentIndex()
        if current == self.PAGE_MANUAL:
            self._switch_page(self.PAGE_ENTRY)
            self._back_btn.setVisible(False)
            self._next_btn.setText("开始测评 →")
        elif current == self.PAGE_PHASE1_LOW:
            self._switch_page(self.PAGE_ENTRY)
            self._set_progress(0)
            self._back_btn.setVisible(False)
            self._next_btn.setText("开始测评 →")
            self._p1_low_status.setText("⏸ 等待开始录音...")
            self._p1_low_status.setStyleSheet(
                "color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;"
            )
        elif current == self.PAGE_PHASE1_HIGH:
            self._switch_page(self.PAGE_PHASE1_LOW)
            self._set_progress(1)
            self._next_btn.setText("▶ 开始录音（低音区）")
            self._p1_high_status.setText("⏸ 等待开始录音...")
            self._p1_high_status.setStyleSheet(
                "color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;"
            )
        elif current == self.PAGE_PHASE2:
            self._switch_page(self.PAGE_PHASE1_HIGH)
            self._set_progress(1)
            self._next_btn.setText("▶ 开始录音（高音区）")
            self._p2_status.setText("⏸ 等待开始滑音录音...")
            self._p2_status.setStyleSheet(
                "color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;"
            )
        elif current == self.PAGE_PHASE3:
            self._switch_page(self.PAGE_PHASE2)
            self._set_progress(2)
            self._next_btn.setText("▶ 开始滑音录音")
            self._p3_status.setText("⏸ 等待开始录音...")
            self._p3_status.setStyleSheet(
                "color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;"
            )
        elif current == self.PAGE_RESULT:
            self._switch_page(self.PAGE_PHASE3)
            self._set_progress(3)
            self._next_btn.setText("▶ 开始录音（元音）")

    def _on_next(self) -> None:
        if self._is_recording:
            return  # 正在录音中，忽略重复点击
        current = self._stack.currentIndex()

        if current == self.PAGE_MANUAL:
            self._save_manual_and_apply()
        elif current == self.PAGE_PHASE1_LOW:
            self._start_phase1_low()
        elif current == self.PAGE_PHASE1_HIGH:
            self._start_phase1_high()
        elif current == self.PAGE_PHASE2:
            self._start_phase2()
        elif current == self.PAGE_PHASE3:
            self._start_phase3()
        elif current == self.PAGE_RESULT:
            self.accept()

    # ═══════════════════════════════════════════════════════════
    # 手动填写逻辑
    # ═══════════════════════════════════════════════════════════

    def _save_manual_and_apply(self) -> None:
        vt = self._manual_voice.currentData() or ""
        if not vt:
            QMessageBox.warning(self, "未选择声部", "请选择你的声部类型。")
            return

        pp_val = self._manual_pp_note.currentData() or ""
        low_val = self._manual_low.currentData() or ""
        high_val = self._manual_high.currentData() or ""
        years = int(self._manual_years.currentData() or "0")

        pp_hz = float(pp_val) if pp_val else 0.0
        low_hz = float(low_val) if low_val else 0.0
        high_hz = float(high_val) if high_val else 0.0

        # 更新 profile
        self._profile.voice_type_manual = vt

        if pp_hz > 0:
            self._profile.passaggio.t4_hz = pp_hz
            self._profile.passaggio.source = "calibrated"
            self._profile.passaggio.confidence = 0.90
            self._profile.passaggio.last_calibrated = time.strftime("%Y-%m-%d")

        # 更新音域
        if low_hz > 0 and high_hz > 0:
            stats = self._profile.pitch_stats
            if stats.total_voiced_frames == 0:
                stats.total_voiced_frames = 100
            if stats.min_hz <= 0 or low_hz < stats.min_hz:
                stats.min_hz = low_hz
            if stats.max_hz <= 0 or high_hz > stats.max_hz:
                stats.max_hz = high_hz

        self._mgr.save_profile(self._profile)
        self.assessment_completed.emit(self._profile.id)
        self.accept()

    # ═══════════════════════════════════════════════════════════
    # Phase 1: 音域测定
    # ═══════════════════════════════════════════════════════════

    def _start_phase1_low(self) -> None:
        self._current_phase = "p1_low"
        self._pitch_track = []
        self._recorded_chunks = []

        self._p1_low_canvas.clear()
        self._p1_low_feedback.setText("🤫")
        self._p1_low_detected.setText("")
        self._p1_low_retry_btn.setVisible(False)

        self._next_btn.setEnabled(False)
        self._next_btn.setText("⏳ 校准中...")

        # ── 第一步: 环境噪声校准 (有动画) ──
        self._start_calibration_stream()

    def _stop_phase1_low(self) -> None:
        if not self._is_recording:
            return
        self._stop_audio_stream()

        # 提取有效音高 — 仅使用有声帧
        # 同时过滤明显异常的极低频（<70Hz 通常是环境噪声/电流声/身体晃动）
        freq_floor = 70.0 if not self._profile.is_female else 150.0
        freqs = [f for t, f in self._pitch_track if f > freq_floor]

        if len(freqs) < 10:
            self._p1_low_status.setText("⚠️ 检测到的有效音高不足，请重试\n💡 提示：确保正在用叹气声往下滑唱，不要停顿")
            self._p1_low_status.setStyleSheet("color: #F85149; font-size: 13px; font-weight: bold; background: transparent;")
            self._p1_low_retry_btn.setVisible(True)
            self._next_btn.setEnabled(True)
            self._next_btn.setText("🔄 重新录音（低音区）")
            return

        # 取 P10 作为最低舒适音（比 P5 更稳健，排除个别破音/噪声帧）
        freqs_sorted = sorted(freqs)
        self._low_range_hz = float(np.percentile(freqs_sorted, 10))
        self._low_pitch_track = list(self._pitch_track)

        note_name = _hz_to_note_name(self._low_range_hz)
        self._p1_low_feedback.setText(f"↓ {note_name} ({self._low_range_hz:.0f} Hz)")
        self._p1_low_detected.setText(
            f"检测到 {len(freqs)} 个有效音高点 (已过滤静音)　｜　最低舒适音 ≈ P10 = {self._low_range_hz:.0f} Hz ({note_name})"
        )

        self._p1_low_status.setText("✅ 低音区测定完成！点击「下一步」继续高音区")
        self._p1_low_status.setStyleSheet("color: #3FB950; font-size: 13px; font-weight: bold; background: transparent;")
        self._p1_low_retry_btn.setVisible(True)

        self._next_btn.setEnabled(True)
        self._next_btn.setText("▶ 开始录音（高音区）")
        self._next_btn.clicked.disconnect()
        self._next_btn.clicked.connect(self._go_to_phase1_high)

    def _on_p1_low_retry(self) -> None:
        """低音区重新测试 — 重置页面状态并开始新的校准+录音"""
        self._p1_low_feedback.setText("🤫")
        self._p1_low_detected.setText("")
        self._p1_low_canvas.clear()
        self._p1_low_retry_btn.setVisible(False)
        self._p1_low_status.setText("⏳ 正在重新校准环境噪声...")
        self._p1_low_status.setStyleSheet(
            "color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;"
        )
        self._next_btn.setEnabled(False)
        self._next_btn.setText("⏳ 校准中...")
        self._low_range_hz = 0.0
        self._low_pitch_track = []
        self._start_calibration_stream()

    def _go_to_phase1_high(self) -> None:
        self._next_btn.clicked.disconnect()
        self._next_btn.clicked.connect(self._on_next)
        self._switch_page(self.PAGE_PHASE1_HIGH)
        self._set_progress(1)
        self._next_btn.setText("▶ 开始录音（高音区）")

    def _start_phase1_high(self) -> None:
        self._current_phase = "p1_high"
        self._pitch_track = []
        self._recorded_chunks = []

        self._p1_high_canvas.clear()
        self._p1_high_feedback.setText("...")
        self._p1_high_detected.setText("")
        self._p1_high_retry_btn.setVisible(False)

        self._next_btn.setEnabled(False)

        # 如果已有校准过的环境噪声门限，直接开始录音；否则先校准
        if self._env_noise_floor > 0:
            self._p1_high_status.setText("🔴 录音中... 从舒适区往上滑唱，找到最高舒适音")
            self._p1_high_status.setStyleSheet(
                "color: #F85149; font-size: 13px; font-weight: bold; background: transparent;"
            )
            self._next_btn.setText("🔴 录音中... (20秒后自动停止)")
            self._is_recording = True
            self._record_start_time = time.time()
            QTimer.singleShot(20000, self._stop_phase1_high)
            self._start_audio_stream()
        else:
            self._p1_high_feedback.setText("🤫")
            self._next_btn.setText("⏳ 校准中...")
            self._start_calibration_stream()

    def _stop_phase1_high(self) -> None:
        if not self._is_recording:
            return
        self._stop_audio_stream()

        # 高音区: 过滤明显不可能是高音的低频噪声 (男声<120Hz, 女声<200Hz)
        freq_floor = 120.0 if not self._profile.is_female else 200.0
        # 同时过滤异常高频 (>1400Hz, 基本不可能是人声舒适音)
        freq_ceil = 1400.0
        freqs = [f for t, f in self._pitch_track if freq_floor < f < freq_ceil]

        if len(freqs) < 10:
            self._p1_high_status.setText("⚠️ 检测到的有效音高不足，请重试\n💡 提示：确保从舒适中音区往上滑唱，不要停顿")
            self._p1_high_status.setStyleSheet("color: #F85149; font-size: 13px; font-weight: bold; background: transparent;")
            self._p1_high_retry_btn.setVisible(True)
            self._next_btn.setEnabled(True)
            self._next_btn.setText("🔄 重新录音（高音区）")
            return

        # P90 作为最高舒适音 (比 P95 更稳健，排除个别破音/octave error 帧)
        freqs_sorted = sorted(freqs)
        self._high_range_hz = float(np.percentile(freqs_sorted, 90))
        self._high_pitch_track = list(self._pitch_track)

        note_name = _hz_to_note_name(self._high_range_hz)
        self._p1_high_feedback.setText(f"↑ {note_name} ({self._high_range_hz:.0f} Hz)")
        self._p1_high_detected.setText(
            f"检测到 {len(freqs)} 个有效音高点 (已过滤静音)　｜　最高舒适音 ≈ P90 = {self._high_range_hz:.0f} Hz ({note_name})"
        )

        # 显示音域
        low_note = _hz_to_note_name(self._low_range_hz)
        high_note = _hz_to_note_name(self._high_range_hz)
        semitones = 12 * math.log2(self._high_range_hz / self._low_range_hz) if self._low_range_hz > 0 else 0

        self._p1_high_status.setText(
            f"✅ 音域测定完成！你的舒适音域: {low_note} → {high_note}（{semitones:.0f} 半音）"
        )
        self._p1_high_status.setStyleSheet("color: #3FB950; font-size: 13px; font-weight: bold; background: transparent;")
        self._p1_high_retry_btn.setVisible(True)

        self._next_btn.setEnabled(True)
        self._next_btn.setText("▶ 下一步：换声点检测 →")
        self._next_btn.clicked.disconnect()
        self._next_btn.clicked.connect(self._go_to_phase2)

    def _on_p1_high_retry(self) -> None:
        """高音区重新测试 — 重置页面状态并开始新录音"""
        self._p1_high_feedback.setText("...")
        self._p1_high_detected.setText("")
        self._p1_high_canvas.clear()
        self._p1_high_retry_btn.setVisible(False)
        self._high_range_hz = 0.0
        self._high_pitch_track = []

        self._next_btn.setEnabled(False)
        # 环境噪声已校准过，直接开始录音
        if self._env_noise_floor > 0:
            self._p1_high_status.setText("🔴 录音中... 从舒适区往上滑唱，找到最高舒适音")
            self._p1_high_status.setStyleSheet(
                "color: #F85149; font-size: 13px; font-weight: bold; background: transparent;"
            )
            self._next_btn.setText("🔴 录音中... (20秒后自动停止)")
            self._is_recording = True
            self._record_start_time = time.time()
            QTimer.singleShot(20000, self._stop_phase1_high)
            self._start_audio_stream()
        else:
            self._p1_high_status.setText("⏳ 正在校准环境噪声...")
            self._p1_high_status.setStyleSheet(
                "color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;"
            )
            self._next_btn.setText("⏳ 校准中...")
            self._start_calibration_stream()

    def _go_to_phase2(self) -> None:
        self._next_btn.clicked.disconnect()
        self._next_btn.clicked.connect(self._on_next)
        self._switch_page(self.PAGE_PHASE2)
        self._set_progress(2)
        self._next_btn.setText("▶ 开始滑音录音")

    # ═══════════════════════════════════════════════════════════
    # Phase 2: 换声点检测 (复用 passaggio 校准逻辑)
    # ═══════════════════════════════════════════════════════════

    def _start_phase2(self) -> None:
        self._current_phase = "p2"

        # ── 读取模式 ──
        if hasattr(self, '_p2_chromatic_radio') and self._p2_chromatic_radio.isChecked():
            self._p2_mode = "chromatic"
        else:
            self._p2_mode = "glissando"

        self._pitch_track = []
        self._feature_track = []
        self._recorded_chunks = []
        self._manual_candidates = []
        self._passaggio_candidates = []
        self._passaggio_hz = 0.0
        self._selected_candidate_index = 0

        self._p2_pitch_display.setText("...")
        self._p2_detect_status.setText("")
        if hasattr(self, '_p2_canvas') and self._p2_canvas is not None:
            self._p2_canvas.clear()
        self._p2_candidates_card.setVisible(False)
        self._p2_piano.setVisible(False)
        self._p2_piano_left_btn.setVisible(False)
        self._p2_piano_right_btn.setVisible(False)
        if hasattr(self, '_p2_piano_hint'):
            self._p2_piano_hint.setVisible(False)

        self._next_btn.setEnabled(False)

        # 模式相关的时长和提示
        if self._p2_mode == "chromatic":
            max_secs = 25
            status_text = "🔴 录音中... 半音半音逐级向上唱（最长25秒）"
            btn_text = "🔴 录音中... (25秒后自动停止)"
        else:
            max_secs = 20
            status_text = "🔴 录音中... 请从低到高缓慢滑唱（最长20秒）"
            btn_text = "🔴 录音中... (20秒后自动停止)"

        # 如果已有校准过的环境噪声门限，直接开始录音；否则先校准
        if self._env_noise_floor > 0:
            self._p2_status.setText(status_text)
            self._p2_status.setStyleSheet(
                "color: #F85149; font-size: 13px; font-weight: bold; background: transparent;"
            )
            self._next_btn.setText(btn_text)
            self._is_recording = True
            self._record_start_time = time.time()
            QTimer.singleShot(max_secs * 1000, self._stop_phase2)
            self._start_audio_stream(track_features=True)
        else:
            self._next_btn.setText("⏳ 校准中...")
            self._start_calibration_stream()

    def _stop_phase2(self) -> None:
        if not self._is_recording:
            return
        self._stop_audio_stream()
        self._full_audio = np.concatenate(self._recorded_chunks) if self._recorded_chunks else None

        # ── 计算动态范围 (用于雷达图) ──
        self._compute_dynamic_range(self._full_audio)

        self._p2_status.setText("⏳ 分析中... 正在用多特征融合检测换声点")
        self._p2_status.setStyleSheet("color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;")

        # 运行检测
        self._detect_passaggio()

        if self._passaggio_hz > 0:
            note = _hz_to_note_name(self._passaggio_hz)
            self._p2_pitch_display.setText(f"T4 ≈ {self._passaggio_hz:.0f} Hz ({note})")
            self._p2_detect_status.setText(
                f"置信度: {self._passaggio_confidence:.0%}　｜　"
                f"候选数: {len(self._passaggio_candidates)}"
            )
            self._p2_status.setText("✅ 换声点检测完成！")
            self._p2_status.setStyleSheet("color: #3FB950; font-size: 13px; font-weight: bold; background: transparent;")
            self._p2_preview_btn.setVisible(False)  # 隐藏独立试听按钮，各候选行已有 🔊

            # ── 填充候选点卡片 (动态重建，含试听按钮) ──
            self._p2_candidates_card.setVisible(True)
            self._selected_candidate_index = 0
            self._update_candidate_selection_ui()

            # ── 钢琴键盘高亮 ──
            if hasattr(self, '_p2_piano_hint'):
                self._p2_piano_hint.setVisible(True)
            self._p2_piano.setVisible(True)
            self._p2_piano_left_btn.setVisible(True)
            self._p2_piano_right_btn.setVisible(True)
            self._p2_piano.set_t4(self._passaggio_hz)
            # 切换画布到回放模式
            if hasattr(self, '_p2_canvas') and self._p2_canvas is not None:
                self._p2_canvas.set_review_data(
                    [(t, f) for t, f in self._pitch_track if f > 0],
                    self._passaggio_hz,
                )
        else:
            self._p2_pitch_display.setText("未检测到")
            if self._p2_mode == "chromatic":
                hint = "请用更明显的半音阶重试（确保每个音保持稳定，跨过换声区）"
            else:
                hint = "请用更明显的滑音重试（确保从低音跨到高音，不要停顿）"
            self._p2_detect_status.setText(hint)
            self._p2_status.setText("⚠️ 检测失败，请重试")
            self._p2_status.setStyleSheet("color: #F85149; font-size: 13px; font-weight: bold; background: transparent;")
            self._p2_candidates_card.setVisible(False)
            self._p2_piano.setVisible(False)
            self._p2_piano_left_btn.setVisible(False)
            self._p2_piano_right_btn.setVisible(False)
            if hasattr(self, '_p2_piano_hint'):
                self._p2_piano_hint.setVisible(False)

        self._next_btn.setEnabled(True)
        self._next_btn.setText("▶ 下一步：音色分析 →")
        self._next_btn.clicked.disconnect()
        self._next_btn.clicked.connect(self._go_to_phase3)

    def _all_candidates_flat(self) -> List[dict]:
        """返回所有候选 (自动检测在前，手动选取在后)，每个带 'source'"""
        result = []
        for c in self._passaggio_candidates:
            d = dict(c)
            d['source'] = 'auto'
            result.append(d)
        for c in self._manual_candidates:
            d = dict(c)
            d['source'] = 'manual'
            result.append(d)
        for i, d in enumerate(result):
            d['flat_index'] = i
        return result

    def _add_manual_candidate(self, hz: float) -> bool:
        """添加用户手动选取的候选点 (去重)"""
        if hz <= 0:
            return False
        for existing in self._all_candidates_flat():
            if abs(existing['freq'] - hz) < 2.0:
                return False
        # 尝试查找特征评分
        feat = self._lookup_feature_scores_at_hz(hz)
        note = _hz_to_note_name(hz)
        self._manual_candidates.append({
            'freq': hz, 'note': note, 'source': 'manual',
            'fusion_score': feat.get('fusion', 0.0),
            'tilt': feat.get('tilt', 0.0),
            'pitch_jump': feat.get('pitch_jump', 0.0),
            'hnr': feat.get('hnr', 0.0),
            'rms': feat.get('rms', 0.0),
            'l1l2': feat.get('l1l2', 0.0),
            'h2h3': feat.get('h2h3', 0.0),
            'f1h2': feat.get('f1h2', 0.0),
            'spec_smooth': feat.get('spec_smooth', 0.0),
            'prior': feat.get('prior', 0.0),
        })
        return True

    def _lookup_feature_scores_at_hz(self, target_hz: float) -> dict:
        """在音高轨迹中查找最接近 target_hz 的频点 — 估算融合评分"""
        zero = {'tilt': 0.0, 'pitch_jump': 0.0, 'hnr': 0.0, 'rms': 0.0,
                'l1l2': 0.0, 'h2h3': 0.0, 'f1h2': 0.0, 'spec_smooth': 0.0, 'prior': 0.0, 'fusion': 0.0}
        if not self._pitch_track:
            return zero
        pitch_freqs = np.array([f for _, f in self._pitch_track])
        best_i, best_d = 0, float('inf')
        for i, f in enumerate(pitch_freqs):
            if f <= 0:
                continue
            d = abs(f - target_hz)
            if d < best_d:
                best_d, best_i = d, i
        if best_d > target_hz * 0.3 or best_i >= len(pitch_freqs):
            return zero
        # 基于声部先验给一个基础评分
        vt = self._profile.effective_voice_type
        expected_t4 = _VOICE_TYPE_PASSAGGIO.get(vt, 400.0)
        st_dist = abs(12 * math.log2(target_hz / max(expected_t4, 1e-6)))
        prior_val = math.exp(-0.5 * (st_dist / 6.0) ** 2) if expected_t4 else 0.5
        # 综合分 = 先验权重为主 (因为其他特征需要原始数组)
        fusion = float(np.clip(prior_val * 0.7 + 0.15, 0.10, 0.80))
        return {'tilt': 0.0, 'pitch_jump': 0.0, 'hnr': 0.0, 'rms': 0.0,
                'l1l2': 0.0, 'h2h3': 0.0, 'prior': float(prior_val), 'fusion': fusion}

    def _on_candidate_selected(self, index: int) -> None:
        """用户点击候选换声点卡片，切换所选换声点"""
        all_cands = self._all_candidates_flat()
        if index < 0 or index >= len(all_cands):
            return
        if index == self._selected_candidate_index:
            return
        self._selected_candidate_index = index
        c = all_cands[index]
        self._passaggio_hz = c['freq']
        note = _hz_to_note_name(self._passaggio_hz)
        self._p2_pitch_display.setText(f"T4 ≈ {self._passaggio_hz:.0f} Hz ({note})")
        if hasattr(self, '_p2_piano') and self._p2_piano is not None:
            self._p2_piano.set_t4(self._passaggio_hz)
        self._update_candidate_selection_ui()

    def _update_candidate_selection_ui(self) -> None:
        """重建候选点卡片 (动态支持自动检测 + 手动选取)"""
        all_cands = self._all_candidates_flat()

        # 清除旧卡片
        for card in self._p2_candidate_cards:
            self._p2_candidates_layout.removeWidget(card)
            card.deleteLater()
        self._p2_candidate_cards.clear()
        self._p2_candidate_checkmarks.clear()
        self._p2_candidate_name_labels.clear()
        self._p2_candidate_detail_labels.clear()
        self._p2_candidate_preview_btns.clear()

        n_cands = len(all_cands)
        if n_cands == 0 or not self._p2_candidates_card.isVisible():
            return

        for idx, c in enumerate(all_cands):
            is_auto = (c.get('source', 'auto') == 'auto')
            is_selected = (idx == self._selected_candidate_index)
            note = _hz_to_note_name(c['freq'])
            fusion = c.get('fusion_score', 0.0)

            # 构建得分文字
            top_feats = [
                ('tilt', c.get('tilt', 0)), ('pitch_jump', c.get('pitch_jump', 0)),
                ('hnr', c.get('hnr', 0)), ('rms', c.get('rms', 0)),
                ('L1L2', c.get('l1l2', 0)), ('H2H3', c.get('h2h3', 0)),
                ('F1H2', c.get('f1h2', 0)), ('平滑度', c.get('spec_smooth', 0)),
            ]
            top_feats.sort(key=lambda x: x[1], reverse=True)
            feat_str = " | ".join([f"{n}:{v:.2f}" for n, v in top_feats[:2]])

            if is_auto:
                detail = f"综合: {fusion:.2f}  |  {feat_str}"
            else:
                detail = f"综合: {fusion:.2f}  |  {feat_str}  ✋手动"

            name_text = f"{'🤖' if is_auto else '✋'} #{idx + 1}  {note} ({c['freq']:.0f} Hz)"

            # ── 构建卡片 ──
            card = QFrame()
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setObjectName("P2CandidateCard")
            card_row = QHBoxLayout(card)
            card_row.setContentsMargins(8, 6, 8, 6)
            card_row.setSpacing(8)

            chk = QLabel("●" if is_selected else "○")
            chk.setFixedWidth(18)
            chk.setStyleSheet(
                f"color: {'#58A6FF' if is_selected else '#484F58'}; font-size: 14px; font-weight: bold; background: transparent;"
            )
            card_row.addWidget(chk)

            name_lbl = QLabel(name_text)
            name_lbl.setStyleSheet(
                f"color: {'#58A6FF' if is_selected else '#C9D1D9'}; font-size: 12px; font-weight: bold; background: transparent;"
            )
            card_row.addWidget(name_lbl)

            detail_lbl = QLabel(detail)
            detail_lbl.setStyleSheet("color: #8B949E; font-size: 10px; background: transparent;")
            detail_lbl.setWordWrap(True)
            card_row.addWidget(detail_lbl, 1)

            # 试听按钮
            preview_btn = QPushButton("🔊")
            preview_btn.setFixedSize(28, 28)
            preview_btn.setToolTip(f"试听 {note} 附近 0.5 秒录音")
            preview_btn.setStyleSheet("""
                QPushButton {
                    background: transparent; border: 1px solid #30363D;
                    border-radius: 14px; font-size: 12px; color: #8B949E;
                }
                QPushButton:hover {
                    background: #1A2540; border-color: #58A6FF; color: #58A6FF;
                }
            """)
            preview_btn.clicked.connect(lambda checked, fi=idx: self._preview_candidate_audio_by_index(fi))
            card_row.addWidget(preview_btn)

            # 卡片样式
            if is_selected:
                card.setStyleSheet("""
                    QFrame#P2CandidateCard {
                        background: #1A2540; border: 2px solid #58A6FF;
                        border-radius: 6px; padding: 6px 10px;
                    }
                """)
            else:
                card.setStyleSheet("""
                    QFrame#P2CandidateCard {
                        background: #0D1117; border: 1px solid #21262D;
                        border-radius: 6px; padding: 6px 10px;
                    }
                    QFrame#P2CandidateCard:hover {
                        border-color: #58A6FF; background: #161B22;
                    }
                """)

            # 点击事件
            card.mousePressEvent = lambda ev, fi=idx: self._on_candidate_selected(fi)

            self._p2_candidates_layout.addWidget(card)
            self._p2_candidate_cards.append(card)
            self._p2_candidate_checkmarks.append(chk)
            self._p2_candidate_name_labels.append(name_lbl)
            self._p2_candidate_detail_labels.append(detail_lbl)
            self._p2_candidate_preview_btns.append(preview_btn)

    def _preview_candidate_audio_by_index(self, index: int) -> None:
        """试听第 index 个候选换声点附近的录音片段 (自动或手动)"""
        all_cands = self._all_candidates_flat()
        if index < 0 or index >= len(all_cands):
            return
        self._preview_audio_at_hz(all_cands[index]['freq'])

    def _preview_audio_at_hz(self, target_hz: float) -> None:
        """在换声点目标频率附近截取 0.5 秒录音片段并播放"""
        if not HAS_SOUNDDEVICE:
            return
        audio = self._full_audio
        pitch_track = self._pitch_track

        # 重试: 如果 _full_audio 为空，尝试从 _recorded_chunks 重建
        if (audio is None or len(audio) == 0) and hasattr(self, '_recorded_chunks') and self._recorded_chunks:
            audio = np.concatenate(self._recorded_chunks)
            self._full_audio = audio

        if audio is None or len(audio) == 0:
            self._show_preview_error("没有找到录音数据。\n请重新录制后再试。")
            return
        if not pitch_track:
            self._show_preview_error("没有音高轨迹数据。")
            return

        # 找到 pitch_track 中最接近目标频率的时间点
        best_time = 0.0
        best_dist = float('inf')
        for t, f in pitch_track:
            if f <= 0:
                continue
            dist = abs(f - target_hz)
            if dist < best_dist:
                best_dist = dist
                best_time = t

        if best_dist > target_hz * 0.5:
            note = _hz_to_note_name(target_hz)
            self._show_preview_error(
                f"录音中未找到接近 {note} ({target_hz:.0f} Hz) 的片段。\n"
                f"最近匹配偏差 {best_dist:.0f} Hz。\n请确保录音时唱到了该音高范围。"
            )
            return

        # 截取 ±0.25 秒 (共 0.5 秒) — 鲁棒边界处理
        sr = SAMPLE_RATE
        half_samples = int(0.25 * sr)

        # 基于样本数计算实际录音时长，修正 wall-clock 漂移
        audio_duration_s = len(audio) / sr
        if best_time > audio_duration_s * 1.05:
            best_time = audio_duration_s * 0.5

        center_sample = int(best_time * sr)
        start_sample = center_sample - half_samples
        end_sample = center_sample + half_samples

        # 如果窗口超出音频边界，向内偏移
        if start_sample < 0:
            shift = -start_sample
            start_sample = 0
            end_sample = min(len(audio), end_sample + shift)
        if end_sample > len(audio):
            shift = end_sample - len(audio)
            end_sample = len(audio)
            start_sample = max(0, start_sample - shift)

        start_sample = max(0, min(start_sample, len(audio) - 1))
        end_sample = max(start_sample + int(0.05 * sr), min(end_sample, len(audio)))

        segment = audio[start_sample:end_sample].copy()

        if len(segment) < int(0.05 * sr):
            fallback_start = max(0, center_sample - int(0.5 * sr))
            fallback_end = min(len(audio), center_sample + int(0.5 * sr))
            if fallback_end - fallback_start >= int(0.05 * sr):
                segment = audio[fallback_start:fallback_end].copy()
            else:
                self._show_preview_error("截取的音频片段太短。")
                return

        # 应用短淡入淡出避免咔嗒声
        fade_len = min(int(0.01 * sr), len(segment) // 4)
        if fade_len > 1:
            fade_in = np.linspace(0, 1, fade_len)
            fade_out = np.linspace(1, 0, fade_len)
            segment[:fade_len] *= fade_in
            segment[-fade_len:] *= fade_out

        # 温和归一化 (-6dBFS)
        peak = max(np.max(np.abs(segment)), 0.001)
        segment = (segment / peak * 0.5).astype(np.float32)

        try:
            sd.stop()  # 停止之前在播的音频
            sd.play(segment, sr)
        except Exception as exc:
            self._show_preview_error(f"播放失败:\n{exc}")

    def _show_preview_error(self, message: str) -> None:
        """显示深色主题的试听错误提示"""
        msg = QMessageBox(self)
        msg.setWindowTitle("试听不可用")
        msg.setText(message)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setStyleSheet("""
            QMessageBox { background-color: #161B22; color: #E6EDF3; }
            QMessageBox QLabel { color: #E6EDF3; font-size: 12px; background: transparent; }
            QPushButton { background: #21262D; color: #E6EDF3; border: 1px solid #30363D;
                border-radius: 6px; padding: 6px 20px; font-size: 12px; min-width: 60px; }
            QPushButton:hover { background: #30363D; border-color: #58A6FF; }
        """)
        msg.exec()

    def _on_piano_passaggio_selected(self, hz: float) -> None:
        """钢琴/画布右键选择换声点的回调 → 加入候选列表并设为当前"""
        added = self._add_manual_candidate(hz)
        self._passaggio_hz = hz
        note = _hz_to_note_name(hz)
        self._p2_pitch_display.setText(f"T4 ≈ {hz:.0f} Hz ({note}) — 手动选取")
        # 如果添加了新候选，刷新候选面板并设为新候选的 index
        if added:
            self._selected_candidate_index = len(self._all_candidates_flat()) - 1
        self._update_candidate_selection_ui()

    def _go_to_phase3(self) -> None:
        self._next_btn.clicked.disconnect()
        self._next_btn.clicked.connect(self._on_next)
        self._switch_page(self.PAGE_PHASE3)
        self._set_progress(3)
        self._next_btn.setText("▶ 开始录音（元音）")

    # ═══════════════════════════════════════════════════════════
    # Phase 3: 音色分析
    # ═══════════════════════════════════════════════════════════

    def _start_phase3(self) -> None:
        self._current_phase = "p3"
        self._pitch_track = []
        self._feature_track = []
        self._recorded_chunks = []

        self._p3_freq_display.setText("...")
        self._p3_timbre_info.setText("")

        self._next_btn.setEnabled(False)

        # 如果已有校准过的环境噪声门限，直接开始录音；否则先校准
        if self._env_noise_floor > 0:
            self._p3_status.setText("🔴 录音中... 唱持续长元音 \"啊———\"（约6-8秒）")
            self._p3_status.setStyleSheet(
                "color: #F85149; font-size: 13px; font-weight: bold; background: transparent;"
            )
            self._next_btn.setText("🔴 录音中... (8秒后自动停止)")
            self._is_recording = True
            self._record_start_time = time.time()
            QTimer.singleShot(8000, self._stop_phase3)
            self._start_audio_stream(track_features=True)

            # ── 实时显示当前音高，帮助用户保持目标音高 ──
            self._display_timer = QTimer(self)
            self._display_timer.setInterval(80)  # ~12 fps
            self._display_timer.timeout.connect(self._update_p3_live_display)
            self._display_timer.start()
        else:
            self._next_btn.setText("⏳ 校准中...")
            self._start_calibration_stream()

    def _stop_phase3(self) -> None:
        if not self._is_recording:
            return
        self._stop_audio_stream()
        self._full_audio = np.concatenate(self._recorded_chunks) if self._recorded_chunks else None

        self._p3_status.setText("⏳ 分析中... 正在计算音色特征")
        self._p3_status.setStyleSheet("color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;")

        if self._full_audio is not None and len(self._full_audio) > SAMPLE_RATE * 1.0:
            self._analyze_timbre(self._full_audio)

        # ── 计算 F0 稳定性 (用于雷达图) ──
        self._compute_pitch_stability()

        if self._fhe_hz > 0:
            self._p3_freq_display.setText(f"FHE = {self._fhe_hz:.0f} Hz")
            detail_parts = [
                f"频谱重心: {self._spectral_centroid_hz:.0f} Hz　｜　"
                f"音色质量: {self._timbre_quality:.0%}",
            ]
            if self._spr_db != 0.0:
                spr_label = "偏亮 (SPR>0)" if self._spr_db > 0 else "偏暖 (SPR<0)"
                detail_parts.append(f"SPR: {self._spr_db:+.1f} dB ({spr_label})")
            if self._alpha_ratio > 0:
                detail_parts.append(f"α比值: {self._alpha_ratio:.2f}")
            self._p3_timbre_info.setText("\n".join(detail_parts))
            self._p3_status.setText("✅ 音色分析完成！")
            self._p3_status.setStyleSheet("color: #3FB950; font-size: 13px; font-weight: bold; background: transparent;")
        else:
            self._p3_freq_display.setText("分析失败")
            self._p3_timbre_info.setText("请用更稳定的长音重试")
            self._p3_status.setText("⚠️ 分析失败，请重试")
            self._p3_status.setStyleSheet("color: #F85149; font-size: 13px; font-weight: bold; background: transparent;")

        self._next_btn.setEnabled(True)
        self._next_btn.setText("▶ 查看鉴定结果 →")
        self._next_btn.clicked.disconnect()
        self._next_btn.clicked.connect(self._go_to_result)

    def _go_to_result(self) -> None:
        self._next_btn.clicked.disconnect()
        self._next_btn.clicked.connect(self._on_next)
        self._compute_and_display_result()

    def _update_p3_live_display(self) -> None:
        """Phase 3 录音期间实时显示当前音高，帮助用户保持目标音高"""
        if not self._is_recording or self._current_phase != "p3":
            return
        freq = self._current_freq
        if freq > 60 and self._current_voiced:
            note = _hz_to_note_name(freq)
            # 显示音高 + 稳定性指示
            self._p3_freq_display.setText(f"🎵 {note} ({freq:.0f} Hz)")
            self._p3_freq_display.setStyleSheet("""
                color: #7EE787; font-size: 26px; font-weight: bold;
                background: #161B22; border: 2px solid #238636; border-radius: 10px;
                padding: 10px;
            """)
        else:
            self._p3_freq_display.setText("🎤 等待发声...")
            self._p3_freq_display.setStyleSheet("""
                color: #A78BFA; font-size: 26px; font-weight: bold;
                background: #161B22; border: 2px solid #30363D; border-radius: 10px;
                padding: 10px;
            """)

    # ═══════════════════════════════════════════════════════════
    # 音频流管理
    # ═══════════════════════════════════════════════════════════

    def _start_audio_stream(self, track_features: bool = False) -> None:
        """启动音频流 (非校准模式 — 用于已有 _env_noise_floor 的后续阶段)"""
        if not HAS_SOUNDDEVICE:
            return
        # 确保之前的流完全释放 (portaudio 有时需要一点时间)
        if self._audio_stream is not None:
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None
            time.sleep(0.1)  # 给 portaudio 一点时间释放设备

        self._is_calibrating = False
        self._is_recording = False
        self._recorded_chunks = []
        self._pitch_track = []

        # 使用已校准的环境噪声门限 (如果存在)
        if self._env_noise_floor > 0:
            self._noise_floor = self._env_noise_floor
            sensitivity = 1.8 if self._current_phase in ("p1_low",) else (1.5 if self._current_phase == "p3" else 2.4)
            self._voice_threshold = self._env_noise_floor * sensitivity
        else:
            self._noise_floor = 0.0
            self._noise_samples = []
            self._voice_threshold = 0.002

        self._noise_samples = []
        if track_features:
            self._feature_track = []
        try:
            self._audio_stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype='float32',
                blocksize=HOP_SIZE,
                callback=self._audio_callback,
            )
            self._audio_stream.start()
            self._is_recording = True
        except Exception as e:
            self._is_recording = False
            self._show_warning(f"无法启动音频流: {e}")

    def _start_calibration_stream(self) -> None:
        """启动环境噪声校准音频流 — 仅收集 RMS，不检测音高，带倒计时动画"""
        if not HAS_SOUNDDEVICE:
            return
        # 确保之前的流完全释放
        if self._audio_stream is not None:
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None
            time.sleep(0.1)

        self._is_calibrating = True
        self._is_recording = False  # callback 中检查，calibrating 模式下也算 "recording"
        self._noise_samples = []
        self._noise_floor = 0.0
        self._voice_threshold = 0.002

        # 重置录制相关
        self._recorded_chunks = []
        self._pitch_track = []

        try:
            self._audio_stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype='float32',
                blocksize=HOP_SIZE,
                callback=self._audio_callback,
            )
            self._audio_stream.start()
            self._is_recording = True  # 让 callback 开始收集 RMS
        except Exception as e:
            self._is_recording = False
            self._is_calibrating = False
            self._show_warning(f"无法启动音频流: {e}")
            return

        # ── 开始倒计时动画 ──
        self._calibration_countdown = 3  # 3 秒倒计时
        self._update_calibration_display()

        if self._calibration_timer is not None:
            self._calibration_timer.stop()
        self._calibration_timer = QTimer(self)
        self._calibration_timer.timeout.connect(self._on_calibration_tick)
        self._calibration_timer.start(1000)  # 每秒 tick

    def _on_calibration_tick(self) -> None:
        """校准倒计时 tick — 每秒更新一次 UI"""
        self._calibration_countdown -= 1
        self._update_calibration_display()

        if self._calibration_countdown <= 0:
            # 停止倒计时
            if self._calibration_timer:
                self._calibration_timer.stop()
            self._finish_calibration_and_start_recording()

    def _update_calibration_display(self) -> None:
        """更新校准动画显示"""
        count = max(0, self._calibration_countdown)

        if self._current_phase == "p1_low":
            self._p1_low_status.setText(
                f"🎤 正在采集环境噪声... 请保持安静 ({count}秒)"
            )
            self._p1_low_status.setStyleSheet(
                "color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;"
            )
            if count > 0:
                bar = "█" * ((3 - count) * 5) + "░" * (count * 5)
                self._p1_low_feedback.setText(f"🤫 {bar}")
            else:
                self._p1_low_feedback.setText("🎵 开始!")
        elif self._current_phase == "p1_high":
            self._p1_high_status.setText(
                f"🎤 正在采集环境噪声... 请保持安静 ({count}秒)"
            )
            self._p1_high_status.setStyleSheet(
                "color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;"
            )
            if count > 0:
                bar = "█" * ((3 - count) * 5) + "░" * (count * 5)
                self._p1_high_feedback.setText(f"🤫 {bar}")
            else:
                self._p1_high_feedback.setText("🎵 开始!")
        elif self._current_phase == "p2":
            self._p2_status.setText(
                f"🎤 正在采集环境噪声... 请保持安静 ({count}秒)"
            )
            self._p2_status.setStyleSheet(
                "color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;"
            )
        elif self._current_phase == "p3":
            self._p3_status.setText(
                f"🎤 正在采集环境噪声... 请保持安静 ({count}秒)"
            )
            self._p3_status.setStyleSheet(
                "color: #F0883E; font-size: 13px; font-weight: bold; background: transparent;"
            )

    def _finish_calibration_and_start_recording(self) -> None:
        """完成环境噪声校准，计算底噪门限，无缝切换到正式录音"""
        self._is_calibrating = False

        # ── 计算环境噪声底噪 ──
        if self._noise_samples and len(self._noise_samples) >= 5:
            nf = float(np.median(self._noise_samples))
            self._env_noise_floor = max(nf, 0.00015)  # 绝对下限更保守
        else:
            self._env_noise_floor = max(self._env_noise_floor, 0.0002)

        # 设置 VAD 门限
        sensitivity = 1.8 if self._current_phase in ("p1_low",) else 2.4
        self._noise_floor = self._env_noise_floor
        self._voice_threshold = self._env_noise_floor * sensitivity

        self._noise_samples.clear()

        # ── 重置正式录音状态 ──
        self._record_start_time = time.time()
        self._pitch_track = []
        self._recorded_chunks = []

        # ── 根据当前阶段设置 UI 和自动停止 ──
        if self._current_phase == "p1_low":
            self._p1_low_canvas.clear()
            self._p1_low_status.setText("🔴 录音中... 用叹气声往下滑唱，找到最低舒适音")
            self._p1_low_status.setStyleSheet(
                "color: #F85149; font-size: 13px; font-weight: bold; background: transparent;"
            )
            self._p1_low_feedback.setText("...")
            self._next_btn.setText("🔴 录音中... (20秒后自动停止)")
            QTimer.singleShot(20000, self._stop_phase1_low)
        elif self._current_phase == "p1_high":
            self._p1_high_canvas.clear()
            self._p1_high_status.setText("🔴 录音中... 从舒适区往上滑唱，找到最高舒适音")
            self._p1_high_status.setStyleSheet(
                "color: #F85149; font-size: 13px; font-weight: bold; background: transparent;"
            )
            self._p1_high_feedback.setText("...")
            self._next_btn.setText("🔴 录音中... (20秒后自动停止)")
            QTimer.singleShot(20000, self._stop_phase1_high)
        elif self._current_phase == "p2":
            self._p2_pitch_display.setText("...")
            self._p2_detect_status.setText("")
            if hasattr(self, '_p2_canvas') and self._p2_canvas is not None:
                self._p2_canvas.clear()
            self._p2_candidates_card.setVisible(False)
            self._p2_piano.setVisible(False)
            self._p2_piano_left_btn.setVisible(False)
            self._p2_piano_right_btn.setVisible(False)
            if hasattr(self, '_p2_piano_hint'):
                self._p2_piano_hint.setVisible(False)
            # 启用 feature tracking
            if not hasattr(self, '_feature_track') or self._feature_track is None:
                self._feature_track = []
            # 模式相关的文案和时长
            if getattr(self, '_p2_mode', 'glissando') == "chromatic":
                self._p2_status.setText("🔴 录音中... 半音半音逐级向上唱（最长25秒）")
                self._next_btn.setText("🔴 录音中... (25秒后自动停止)")
                QTimer.singleShot(25000, self._stop_phase2)
            else:
                self._p2_status.setText("🔴 录音中... 请从低到高缓慢滑唱（最长20秒）")
                self._next_btn.setText("🔴 录音中... (20秒后自动停止)")
                QTimer.singleShot(20000, self._stop_phase2)
            self._p2_status.setStyleSheet(
                "color: #F85149; font-size: 13px; font-weight: bold; background: transparent;"
            )
        elif self._current_phase == "p3":
            self._p3_freq_display.setText("...")
            self._p3_timbre_info.setText("")
            self._p3_status.setText("🔴 录音中... 唱持续长元音 \"啊———\"（约3-5秒）")
            self._p3_status.setStyleSheet(
                "color: #F85149; font-size: 13px; font-weight: bold; background: transparent;"
            )
            self._feature_track = []
            self._next_btn.setText("🔴 录音中... (5秒后自动停止)")
            QTimer.singleShot(5000, self._stop_phase3)

    def _stop_audio_stream(self) -> None:
        self._is_recording = False
        self._is_calibrating = False
        stream = self._audio_stream
        self._audio_stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        # 清理校准定时器
        if self._calibration_timer is not None:
            self._calibration_timer.stop()
            self._calibration_timer = None
        # 清理显示定时器
        if self._display_timer is not None:
            self._display_timer.stop()
            self._display_timer = None

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if not self._is_recording:
            return
        chunk = indata[:, 0].copy()
        rms = float(np.sqrt(np.mean(chunk ** 2) + 1e-12))

        # ── 环境噪声校准模式: 只收集 RMS，不做音高检测也不画图 ──
        if self._is_calibrating:
            self._noise_samples.append(rms)
            return

        self._recorded_chunks.append(chunk)
        elapsed = time.time() - self._record_start_time

        # ── VAD: 使用预校准的环境噪声门限 ──
        threshold = self._voice_threshold if self._noise_floor > 0 else 0.002
        voiced = rms > threshold

        freq = 0.0
        pitch_conf = 0.0
        if voiced:
            freq, pitch_conf = self._pitch_service.detect(chunk)
            # 低音区放宽置信度要求 (低音周期性强但 CMNDF 谷不如高音深)
            min_conf = 0.12 if self._current_phase in ("p1_low", "p3") else 0.20
            if pitch_conf < min_conf:
                freq = 0.0
                voiced = False

        self._current_freq = freq
        self._current_voiced = voiced
        self._pitch_track.append((elapsed, freq if voiced else 0.0))

        # 频谱特征 (仅有声帧) — 8 维: tilt, hnr, rms, l1l2, h2h3, f1, f2
        if hasattr(self, '_feature_track') and self._feature_track is not None:
            if voiced:
                tilt = self._compute_spectral_tilt(chunk, SAMPLE_RATE)
                hnr = self._compute_hnr(chunk, SAMPLE_RATE)
                l1l2 = self._compute_l1l2(chunk, SAMPLE_RATE, freq)
                h2h3 = self._compute_h2h3_ratio(chunk, SAMPLE_RATE, freq)
                f1, f2 = self._estimate_formants(chunk * np.hanning(len(chunk)), SAMPLE_RATE, freq)
            else:
                tilt, hnr, l1l2, h2h3, f1, f2 = 0.0, 0.0, 0.0, 1.0, 0.0, 0.0
            self._current_tilt = tilt
            self._current_hnr = hnr
            self._current_rms = rms
            self._current_l1l2 = l1l2
            self._current_h2h3 = h2h3
            self._current_f1 = f1
            self._current_f2 = f2
            self._feature_track.append((elapsed, tilt, hnr, rms, l1l2, h2h3, f1, f2))

        # 实时 UI 更新
        self._update_live_display(freq, elapsed, voiced)

    def _update_live_display(self, freq: float, elapsed: float, voiced: bool = False) -> None:
        if freq > 0 and voiced:
            note = _hz_to_note_name(freq)
            disp = f"{note} ({freq:.0f} Hz)"

            if self._current_phase == "p1_low":
                self._p1_low_feedback.setText(f"↓ {disp}")
                self._p1_low_canvas.add_point(elapsed, freq)
            elif self._current_phase == "p1_high":
                self._p1_high_feedback.setText(f"↑ {disp}")
                self._p1_high_canvas.add_point(elapsed, freq)
            elif self._current_phase == "p2":
                self._p2_pitch_display.setText(disp)
                if hasattr(self, '_p2_canvas') and self._p2_canvas is not None:
                    self._p2_canvas.add_point(elapsed, freq)
                if len(self._pitch_track) >= 10:
                    span_notes = self._estimate_span()
                    self._p2_detect_status.setText(f"音高范围: {span_notes}　｜　已录 {elapsed:.1f} 秒")
            elif self._current_phase == "p3":
                self._p3_freq_display.setText(disp)
                if elapsed > 0.5:
                    self._p3_timbre_info.setText(f"保持稳定... 已录 {elapsed:.1f} 秒")
        elif not voiced:
            # 静音帧: 不更新 canvas, 保留上次显示
            pass

    def _estimate_span(self) -> str:
        freqs = [f for t, f in self._pitch_track if f > 60.0]
        if len(freqs) < 3:
            return "—"
        low = _hz_to_note_name(min(freqs))
        high = _hz_to_note_name(max(freqs))
        return f"{low} → {high}"

    @staticmethod
    def _compute_spectral_tilt(signal: np.ndarray, sr: int) -> float:
        """计算频谱倾斜 (500-2500 Hz 频段线性回归)"""
        n = len(signal)
        spec = np.abs(np.fft.rfft(signal * np.hanning(n)))
        freq = np.fft.rfftfreq(n, 1.0 / sr)

        lo, hi = 500.0, 2500.0
        mask = (freq >= lo) & (freq <= hi)
        if np.sum(mask) < 5:
            return 0.0

        log_f = np.log10(freq[mask])
        log_mag = np.log10(spec[mask] + 1e-10)

        # 线性回归
        x = log_f
        y = log_mag
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        num = np.sum((x - x_mean) * (y - y_mean))
        den = np.sum((x - x_mean) ** 2)
        if den < 1e-10:
            return 0.0
        return float(num / den)

    @staticmethod
    def _compute_mid_high_ratio(signal: np.ndarray, sr: int) -> float:
        """计算中高频能量比 mid(300-3000Hz) / high(>3000Hz)

        值越高 → 中频能量更丰富（胸声、温暖音色）
        值越低 → 高频能量更突出（头声、明亮音色）
        """
        n = len(signal)
        spec = np.abs(np.fft.rfft(signal * np.hanning(n)))
        freq = np.fft.rfftfreq(n, 1.0 / sr)

        mid_mask = (freq >= 300.0) & (freq <= 3000.0)
        high_mask = freq > 3000.0

        mid_e = float(np.mean(spec[mid_mask])) if np.any(mid_mask) else 0.0
        high_e = float(np.mean(spec[high_mask])) if np.any(high_mask) else 1e-12

        if mid_e < 1e-12 or high_e < 1e-12:
            return 1.0
        return float(np.clip(mid_e / high_e, 0.1, 10.0))

    @staticmethod
    def _compute_hm_over_hh(signal: np.ndarray, sr: int) -> float:
        """计算高中频/高高频能量比 (2-6kHz) / (>6kHz)

        值越高 → 2-6kHz 谐波丰富（歌手共振峰强）
        值越低 → 极高频占优（气息声、齿音多）
        """
        n = len(signal)
        spec = np.abs(np.fft.rfft(signal * np.hanning(n)))
        freq = np.fft.rfftfreq(n, 1.0 / sr)

        hm_mask = (freq >= 2000.0) & (freq <= 6000.0)
        hh_mask = freq > 6000.0

        hm_e = float(np.mean(spec[hm_mask])) if np.any(hm_mask) else 0.0
        hh_e = float(np.mean(spec[hh_mask])) if np.any(hh_mask) else 1e-12

        if hm_e < 1e-12 or hh_e < 1e-12:
            return 1.0
        return float(np.clip(hm_e / hh_e, 0.1, 10.0))

    @staticmethod
    def _compute_hnr(signal: np.ndarray, sr: int) -> float:
        """计算谐波噪声比 (Harmonic-to-Noise Ratio)"""
        n = len(signal)
        spec = np.abs(np.fft.rfft(signal * np.hanning(n)))
        freq = np.fft.rfftfreq(n, 1.0 / sr)

        # 粗略估计基频
        max_idx = np.argmax(spec[:len(spec)//2])
        f0_est = freq[max_idx]
        if f0_est < 60:
            return 0.0

        # 谐波 bin: f0 的整数倍 ±5%
        harmonic_mask = np.zeros_like(spec, dtype=bool)
        max_harmonic = int(4000.0 / f0_est)
        for k in range(1, min(max_harmonic, 20) + 1):
            h_freq = f0_est * k
            if h_freq < sr / 2:
                idx = np.argmin(np.abs(freq - h_freq))
                width = max(1, int(idx * 0.05))
                lo = max(0, idx - width)
                hi = min(len(spec) - 1, idx + width)
                harmonic_mask[lo:hi + 1] = True

        h_power = np.sum(spec[harmonic_mask] ** 2)
        n_power = np.sum(spec[~harmonic_mask] ** 2)

        if n_power < 1e-10:
            return 20.0
        if h_power < 1e-10:
            return 0.0
        ratio = max(h_power / n_power, 1e-10)
        return float(10.0 * math.log10(ratio))

    @staticmethod
    def _compute_l1l2(signal: np.ndarray, sr: int, f0: float) -> float:
        """计算 L1-L2 谐波比 (dB) — 换声点关键指标
        L1=基频能量, L2=第二谐波能量。换声时 L1-L2 从负变正 (尤其女声)。
        """
        if f0 <= 0:
            return 0.0
        n = len(signal)
        spec = np.abs(np.fft.rfft(signal * np.hanning(n)))
        freq = np.fft.rfftfreq(n, 1.0 / sr)

        def _harmonic_energy(h: int) -> float:
            hf = f0 * h
            if hf > sr / 2:
                return 0.0
            idx = np.argmin(np.abs(freq - hf))
            lo, hi = max(0, idx - 2), min(len(spec) - 1, idx + 3)
            return float(np.sum(spec[lo:hi + 1] ** 2))

        e1 = _harmonic_energy(1)
        e2 = _harmonic_energy(2)
        if e1 < 1e-12 or e2 < 1e-12:
            return 0.0
        l1l2 = 10 * math.log10(e1 / e2 + 1e-12)
        return float(np.clip(l1l2, -20, 20))

    @staticmethod
    def _compute_h2h3_ratio(signal: np.ndarray, sr: int, f0: float) -> float:
        """计算 H2/H3 主导度 — 男声换声关键
        胸声区 H2 由 F1 共振主导 → H2/H3 > 1.5
        换声点附近 F2 共振转移到 H3 → H2/H3 < 1.0
        """
        if f0 <= 0:
            return 1.0
        n = len(signal)
        spec = np.abs(np.fft.rfft(signal * np.hanning(n)))
        freq = np.fft.rfftfreq(n, 1.0 / sr)

        def _harmonic_energy(h: int) -> float:
            hf = f0 * h
            if hf > sr / 2:
                return 0.0
            idx = np.argmin(np.abs(freq - hf))
            lo, hi = max(0, idx - 2), min(len(spec) - 1, idx + 3)
            return float(np.sum(spec[lo:hi + 1] ** 2))

        e2 = _harmonic_energy(2)
        e3 = _harmonic_energy(3)
        if e3 < 1e-12:
            return 5.0
        return float(np.clip(e2 / e3, 0.1, 10.0))

    @staticmethod
    def _estimate_formants(signal: np.ndarray, sr: int, f0: float, order: int = 14) -> Tuple[float, float]:
        """LPC 共振峰估计 → (F1, F2) in Hz (P3)"""
        if len(signal) < order * 2 or f0 <= 0:
            return 0.0, 0.0
        n = len(signal)
        r = np.zeros(order + 1)
        for lag in range(order + 1):
            r[lag] = np.dot(signal[:n - lag], signal[lag:])
        a = np.zeros(order + 1); a[0] = 1.0
        e = r[0] if r[0] > 1e-10 else 1e-10
        for i in range(1, order + 1):
            k = -np.dot(a[:i], r[i:0:-1]) / e if e > 1e-10 else 0.0
            k = np.clip(k, -0.999, 0.999)
            a[1:i + 1] += k * a[i:0:-1]; a[i] = k
            e *= (1.0 - k * k)
            if e < 1e-12: e = 1e-12
        n_fft = max(1024, 2 ** int(np.ceil(np.log2(n))))
        A = np.fft.rfft(a, n=n_fft)
        H = 1.0 / (np.abs(A) + 1e-10)
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
        lo = int(np.searchsorted(freqs, max(f0 * 1.1, 200.0)))
        hi_f1, hi_f2 = int(np.searchsorted(freqs, 1200.0)), int(np.searchsorted(freqs, 3000.0))
        f1_hz, f2_hz = 0.0, 0.0
        if lo < hi_f1:
            seg = H[lo:hi_f1 + 1]
            peaks = [(j + lo, seg[j]) for j in range(1, len(seg) - 1) if seg[j] > seg[j - 1] and seg[j] >= seg[j + 1]]
            if peaks: peaks.sort(key=lambda x: x[1], reverse=True); f1_hz = freqs[peaks[0][0]]
        f1_idx = int(np.searchsorted(freqs, f1_hz + 100.0)) if f1_hz > 0 else lo
        if f1_idx < hi_f2:
            seg = H[f1_idx:hi_f2 + 1]
            peaks = [(j + f1_idx, seg[j]) for j in range(1, len(seg) - 1) if seg[j] > seg[j - 1] and seg[j] >= seg[j + 1]]
            if peaks: peaks.sort(key=lambda x: x[1], reverse=True); f2_hz = freqs[peaks[0][0]]
        return max(0.0, f1_hz), max(0.0, f2_hz)

    # ═══════════════════════════════════════════════════════════
    # 换声点检测
    # ═══════════════════════════════════════════════════════════

    def _detect_passaggio(self) -> None:
        """多特征融合换声点检测 (鲁棒增强版)

        改进 (来自 passaggio_calibration_dialog 的成熟逻辑):
          - 原始特征先平滑再差分，减少帧间噪声
          - 自适应特征权重: 信号质量高的特征自动提权
          - 信号保留归一化 (P95-median 基线减法)
          - 更宽的声部先验 (σ=4 半音)
          - top-3 候选峰 + 峰间一致性评分
        """
        if len(self._feature_track) < 5 or len(self._pitch_track) < 5:
            return

        ft_times = np.array([t for t, _, _, _, _, _, _, _ in self._feature_track])
        ft_tilts = np.array([tilt for _, tilt, _, _, _, _, _, _ in self._feature_track])
        ft_hnrs = np.array([hnr for _, _, hnr, _, _, _, _, _ in self._feature_track])
        ft_rmss = np.array([rms for _, _, _, rms, _, _, _, _ in self._feature_track])
        ft_l1l2s = np.array([l1l2 for _, _, _, _, l1l2, _, _, _ in self._feature_track])
        ft_h2h3s = np.array([h2h3 for _, _, _, _, _, h2h3, _, _ in self._feature_track])
        ft_f1s = np.array([f1 for _, _, _, _, _, _, f1, _ in self._feature_track])
        ft_f2s = np.array([f2 for _, _, _, _, _, _, _, f2 in self._feature_track])

        pitch_times = np.array([t for t, _ in self._pitch_track])
        pitch_freqs = np.array([f for _, f in self._pitch_track])

        if len(ft_times) < 2 or len(pitch_times) < 2:
            return

        # 插值到音高时间点
        tilts_raw = np.interp(pitch_times, ft_times, ft_tilts)
        hnrs_raw = np.interp(pitch_times, ft_times, ft_hnrs)
        rmss_raw = np.interp(pitch_times, ft_times, ft_rmss)
        l1l2s_raw = np.interp(pitch_times, ft_times, ft_l1l2s)
        h2h3s_raw = np.interp(pitch_times, ft_times, ft_h2h3s)

        n = len(pitch_times)

        # ── 特征平滑 (3帧移动平均) ──
        def _smooth3(x):
            if len(x) < 3:
                return x.copy()
            s = x.copy()
            for i in range(1, len(x) - 1):
                s[i] = (x[i - 1] + x[i] + x[i + 1]) / 3.0
            return s

        tilts = _smooth3(tilts_raw)
        hnrs = _smooth3(hnrs_raw)
        rmss = _smooth3(rmss_raw)
        l1l2s = _smooth3(l1l2s_raw)
        h2h3s = _smooth3(h2h3s_raw)

        # ── 滑动窗口变化量 (P1): 替代逐帧差分，捕获 200-500ms 过渡 ──
        # hop ~46ms, 窗口 8 帧 ≈ 370ms
        def _windowed_drop(x: np.ndarray, win: int = 8) -> np.ndarray:
            result = np.zeros_like(x)
            half = max(1, win // 2)
            for i in range(win, len(x)):
                start_mean = np.mean(x[i - win : i - half])
                end_mean = np.mean(x[i - half : i])
                result[i] = start_mean - end_mean  # 正值 = 下降 (换声信号)
            return np.clip(result, 0, None)

        def _windowed_rise(x: np.ndarray, win: int = 8) -> np.ndarray:
            result = np.zeros_like(x)
            half = max(1, win // 2)
            for i in range(win, len(x)):
                start_mean = np.mean(x[i - win : i - half])
                end_mean = np.mean(x[i - half : i])
                result[i] = end_mean - start_mean  # 正值 = 上升 (换声信号)
            return np.clip(result, 0, None)

        # 1. 频谱倾斜 — 换声时下降 (变得更负)
        tilt_change = _windowed_drop(tilts)
        tilt_quality = self._feature_snr(tilt_change)
        tilt_score = self._normalize_feature(tilt_change)

        # 2. 音高断连 — 换声时半音跳跃增大
        semitone_diff = np.zeros(n)
        for i in range(1, n):
            if pitch_freqs[i] > 0 and pitch_freqs[i - 1] > 0:
                semitone_diff[i] = abs(12 * math.log2(pitch_freqs[i] / max(pitch_freqs[i - 1], 1e-6)))
        semitone_smooth = _smooth3(semitone_diff)
        pitch_change = _windowed_rise(semitone_smooth)  # 跳跃增大 = 上升
        pitch_quality = self._feature_snr(pitch_change)
        pitch_score = self._normalize_feature(pitch_change)

        # 3. HNR — 换声时下降
        hnr_change = _windowed_drop(hnrs)
        hnr_quality = self._feature_snr(hnr_change)
        hnr_score = self._normalize_feature(hnr_change)

        # 4. 振幅 — 换声时下降
        rms_change = _windowed_drop(rmss)
        rms_quality = self._feature_snr(rms_change)
        rms_score = self._normalize_feature(rms_change)

        # 5. L1-L2 谐波比 — 换声时上升 (从负变正)  [P0 新增]
        l1l2_change = _windowed_rise(l1l2s)
        l1l2_quality = self._feature_snr(l1l2_change)
        l1l2_score = self._normalize_feature(l1l2_change)

        # 6. H2/H3 主导度 — 换声时下降 (H2 主导 → H3 主导)  [P0 新增]
        h2h3_change = _windowed_drop(h2h3s)
        h2h3_quality = self._feature_snr(h2h3_change)
        h2h3_score = self._normalize_feature(h2h3_change)

        # ── 7. F1/H2 穿越 (P3) — 换声点物理机制 ──
        f1s = _smooth3(np.interp(pitch_times, ft_times, ft_f1s))
        f2s = _smooth3(np.interp(pitch_times, ft_times, ft_f2s))
        f1_h2_gap = np.zeros(n)
        for i in range(n):
            if pitch_freqs[i] > 0 and f1s[i] > 0:
                h2 = 2.0 * pitch_freqs[i]
                gap = abs(f1s[i] - h2) / max(h2, 1e-6)
                f1_h2_gap[i] = max(0.0, 1.0 - gap / 0.15)
        f1h2_quality = self._feature_snr(f1_h2_gap)
        f1h2_score = self._normalize_feature(f1_h2_gap)

        # ── 8. 频谱平滑度 (P4) ──
        spec_smooth = np.ones(n) * 0.5
        if n >= 2:
            for i in range(1, n):
                if f1s[i] > 0 and f1s[i - 1] > 0:
                    f1_rel_change = abs(f1s[i] - f1s[i - 1]) / max(f1s[i - 1], 1e-6)
                    spec_smooth[i] = max(0.0, 1.0 - f1_rel_change / 0.30)
        spec_smooth_quality = self._feature_snr(spec_smooth)
        spec_smooth_score = self._normalize_feature(spec_smooth)

        # 9. 声部先验 —— 手动设置 vs 自动推断 区分对待
        vt = self._profile.effective_voice_type
        is_manual_vt = bool(getattr(self._profile, 'voice_type_manual', ''))
        expected_t4 = _VOICE_TYPE_PASSAGGIO.get(vt, None)
        prior_sigma = 4.0 if is_manual_vt else 6.0
        prior_score = np.ones(n) * 0.5
        if expected_t4 is not None:
            for i, f in enumerate(pitch_freqs):
                if f > 0:
                    st_dist = abs(12 * math.log2(f / expected_t4))
                    prior_score[i] = math.exp(-0.5 * (st_dist / prior_sigma) ** 2)

        # ── 8 特征自适应权重 ──
        qualities = {
            'tilt': max(tilt_quality, 0.1),
            'pitch': max(pitch_quality, 0.1),
            'hnr': max(hnr_quality, 0.1),
            'rms': max(rms_quality, 0.1),
            'l1l2': max(l1l2_quality, 0.1),
            'h2h3': max(h2h3_quality, 0.1),
            'f1h2': max(f1h2_quality, 0.1),
            'spec_smooth': max(spec_smooth_quality, 0.1),
        }
        prior_base = 1.5 if (expected_t4 is not None and is_manual_vt) else 1.0
        q_sum = sum(qualities.values()) + prior_base

        base_w = {'tilt': 0.22, 'pitch': 0.15, 'hnr': 0.10, 'rms': 0.06,
                  'l1l2': 0.10, 'h2h3': 0.08, 'f1h2': 0.12, 'spec_smooth': 0.07}
        w_tilt = base_w['tilt'] * qualities['tilt'] / max(q_sum * base_w['tilt'], 0.01)
        w_pitch = base_w['pitch'] * qualities['pitch'] / max(q_sum * base_w['pitch'], 0.01)
        w_hnr = base_w['hnr'] * qualities['hnr'] / max(q_sum * base_w['hnr'], 0.01)
        w_rms = base_w['rms'] * qualities['rms'] / max(q_sum * base_w['rms'], 0.01)
        w_l1l2 = base_w['l1l2'] * qualities['l1l2'] / max(q_sum * base_w['l1l2'], 0.01)
        w_h2h3 = base_w['h2h3'] * qualities['h2h3'] / max(q_sum * base_w['h2h3'], 0.01)
        w_f1h2 = base_w['f1h2'] * qualities['f1h2'] / max(q_sum * base_w['f1h2'], 0.01)
        w_spec_smooth = base_w['spec_smooth'] * qualities['spec_smooth'] / max(q_sum * base_w['spec_smooth'], 0.01)
        w_prior = 0.10 if (expected_t4 is not None and is_manual_vt) else 0.06

        w_total = w_tilt + w_pitch + w_hnr + w_rms + w_l1l2 + w_h2h3 + w_f1h2 + w_spec_smooth + w_prior
        w_tilt /= w_total; w_pitch /= w_total; w_hnr /= w_total; w_rms /= w_total
        w_l1l2 /= w_total; w_h2h3 /= w_total; w_f1h2 /= w_total; w_spec_smooth /= w_total; w_prior /= w_total

        # ── 融合打分 (9 特征) ──
        fusion = (w_tilt * tilt_score + w_pitch * pitch_score +
                  w_hnr * hnr_score + w_rms * rms_score +
                  w_l1l2 * l1l2_score + w_h2h3 * h2h3_score +
                  w_f1h2 * f1h2_score + w_spec_smooth * spec_smooth_score +
                  w_prior * prior_score)

        # 高斯平滑
        kw = max(3, n // 15)
        if kw % 2 == 0:
            kw += 1
        kernel = np.exp(-0.5 * np.linspace(-2.5, 2.5, kw) ** 2)
        kernel /= kernel.sum()
        fusion_smooth = np.convolve(fusion, kernel, mode='same')

        # ── P2: 基于 Phase 1 实测音域缩小搜索窗口 ──
        # 换声点不可能在最低舒适音的 1.3 倍以下，也不可能超过最高舒适音的 85%
        min_freq = 250.0 if self._profile.is_female else 150.0
        max_freq = 880.0 if self._profile.is_female else 550.0

        if hasattr(self, '_low_range_hz') and self._low_range_hz > 60:
            min_freq = max(min_freq, self._low_range_hz * 1.30)
        if hasattr(self, '_high_range_hz') and self._high_range_hz > 60:
            max_freq = min(max_freq, self._high_range_hz * 0.85)

        # 确保 min < max，且在合理范围内
        min_freq = max(120.0, min(min_freq, max_freq - 30.0))
        max_freq = min(1000.0, max(max_freq, min_freq + 30.0))

        valid = (pitch_freqs > min_freq) & (pitch_freqs < max_freq)

        peaks = []
        for i in range(1, n - 1):
            if not valid[i]:
                continue
            if fusion_smooth[i] > fusion_smooth[i - 1] and fusion_smooth[i] >= fusion_smooth[i + 1]:
                peaks.append((i, fusion_smooth[i], pitch_freqs[i]))

        peaks.sort(key=lambda x: x[1], reverse=True)
        top_peaks = peaks[:3]

        self._passaggio_candidates = []
        for idx, score, freq in top_peaks:
            self._passaggio_candidates.append({
                'freq': float(freq),
                'fusion_score': float(score),
                'tilt': float(tilt_score[idx]),
                'pitch_jump': float(pitch_score[idx]),
                'hnr': float(hnr_score[idx]),
                'rms': float(rms_score[idx]),
                'l1l2': float(l1l2_score[idx]),
                'h2h3': float(h2h3_score[idx]),
                'f1h2': float(f1h2_score[idx]),
                'spec_smooth': float(spec_smooth_score[idx]),
                'prior': float(prior_score[idx]),
            })

        # ── 融合分重标定: 增强可读性 ──
        if self._passaggio_candidates:
            top_score = self._passaggio_candidates[0]['fusion_score']
            if top_score > 0.01:
                for c in self._passaggio_candidates:
                    ratio = c['fusion_score'] / top_score
                    c['fusion_score'] = float(np.clip(0.20 + ratio * 0.72, 0.15, 0.92))

        if not self._passaggio_candidates:
            return

        best = self._passaggio_candidates[0]
        self._passaggio_hz = best['freq']
        self._selected_candidate_index = 0

        # ── 置信度: 基于重标定后的融合分 + 一致性 ──
        rescaled_fusion = best['fusion_score']
        mapped_conf = float(np.clip(rescaled_fusion * 1.1, 0.15, 0.92))

        if len(self._passaggio_candidates) >= 2:
            peak_ratio = self._passaggio_candidates[1]['fusion_score'] / max(rescaled_fusion, 0.001)
            consistency = 0.75 if peak_ratio > 0.85 else (0.88 if peak_ratio > 0.60 else 1.0)
        else:
            consistency = 1.0

        feat_agreement = self._compute_feature_agreement(best, self._passaggio_candidates)
        self._passaggio_confidence = float(np.clip(
            mapped_conf * consistency * (0.88 + 0.12 * feat_agreement), 0.15, 0.95))

    @staticmethod
    def _feature_snr(x: np.ndarray) -> float:
        """计算特征的信号质量 (峰值/中值比)

        > 1.0: 有明确峰值 (好信号)
        ≈ 0.0: 接近平坦噪声 (差信号)
        """
        if len(x) < 3:
            return 0.0
        peak = np.max(x)
        median = np.median(np.abs(x))
        if peak < 1e-8 or median < 1e-8:
            return 0.0
        ratio = peak / median
        return float(np.clip(np.log2(ratio) / 3.0, 0.0, 1.0))

    @staticmethod
    def _compute_feature_agreement(best: dict, candidates: list) -> float:
        """计算各特征在最佳候选点的一致性

        高值 = tilt/pitch/HNR/rms 的峰值都指向同一频率 → 信号可靠
        低值 = 各特征峰值分散在不同频率 → 信号噪声大
        """
        if not candidates or len(candidates) < 1:
            return 0.5
        feat_names = ['tilt', 'pitch_jump', 'hnr', 'rms']
        best_feats = {k: best.get(k, 0.0) for k in feat_names}
        gaps = [best_feats[k] for k in feat_names if best_feats[k] >= 0]
        if not gaps:
            return 0.0
        mean_val = sum(gaps) / len(gaps)
        return float(np.clip(mean_val * 2.0, 0.0, 1.0))

    @staticmethod
    def _normalize_feature(x: np.ndarray) -> np.ndarray:
        """信号保留归一化 (与 passaggio_calibration_dialog 一致)"""
        if len(x) < 2:
            return np.zeros_like(x)
        med = float(np.median(x))
        p95 = float(np.percentile(x, 95))
        dr = max(p95 - med, 1e-8)
        return np.clip((x - med) / dr, 0.0, 1.0)

    # ═══════════════════════════════════════════════════════════
    # 音色分析
    # ═══════════════════════════════════════════════════════════

    def _analyze_timbre(self, audio: np.ndarray) -> None:
        """分析持续元音的音色特征: FHE + PHE + Spectral Centroid + SPR + Alpha

        P1 增强:
          - 声部自适应频段: 女声 2300-4500 Hz, 男声 2000-3600 Hz (Müller et al. 2022)
          - PHE (Position of Half Energy): 半能量点在频段内的相对位置 0-1
          - SPR (Singing Power Ratio): 0-2kHz vs 2-4kHz 能量比 (dB)
          - Alpha Ratio: 高频(>1kHz) vs 低频(<1kHz) 能量比
          - Welch 方法: 多窗平均降低频谱方差
        """
        n = len(audio)

        # ── Welch 方法: 50% overlap 多窗平均 ──
        win_len = min(8192, n // 3)
        if win_len < 1024:
            win_len = n
        hop = win_len // 2
        n_windows = max(1, (n - win_len) // hop + 1)
        window = np.hanning(win_len)

        spec_accum = None
        for wi in range(n_windows):
            start = wi * hop
            frame = audio[start:start + win_len]
            if len(frame) < win_len:
                break
            frame_spec = np.abs(np.fft.rfft(frame * window))
            if spec_accum is None:
                spec_len = len(frame_spec)
                spec_accum = np.zeros(spec_len, dtype=np.float64)
            if len(frame_spec) == spec_len:
                spec_accum += frame_spec

        if spec_accum is None or np.max(spec_accum) < 1e-10:
            return

        spec = spec_accum / n_windows
        freq = np.fft.rfftfreq(win_len, 1.0 / SAMPLE_RATE)

        # ── 声部自适应频段 (Müller et al. 2022) ──
        if self._profile.is_female:
            band_low, band_high = 2300.0, 4500.0   # 女高音/女中音
        else:
            band_low, band_high = 2000.0, 3600.0   # 男声声部

        band_mask = (freq >= band_low) & (freq <= band_high)
        band_spec = spec[band_mask]
        band_freq = freq[band_mask]

        if len(band_spec) < 10:
            return

        # ── FHE + PHE ──
        power = band_spec ** 2
        total_power = np.sum(power)
        if total_power < 1e-10:
            return

        cumsum = np.cumsum(power)
        half_idx = np.argmax(cumsum >= total_power / 2)
        if half_idx > 0:
            self._fhe_hz = float(band_freq[half_idx])
            # PHE: 半能量点在频段内的相对位置 (0 = 偏暗/偏低频, 1 = 偏亮/偏高频)
            self._phe = float(np.clip(half_idx / max(len(band_freq) - 1, 1), 0.0, 1.0))

        # Spectral Centroid: 频谱重心
        self._spectral_centroid_hz = float(
            np.sum(band_freq * power) / total_power
        ) if total_power > 1e-10 else 0.0

        # 音色质量: 基于频谱峰均比 (singer's formant 突出度)
        peak = np.max(power)
        mean_power = np.mean(power)
        if mean_power > 0:
            self._timbre_quality = float(np.clip(np.log10(peak / mean_power) / 2.0, 0.1, 0.95))

        # ── SPR (Singing Power Ratio): 0-2kHz vs 2-4kHz ──
        mask_low = (freq >= 80.0) & (freq < 2000.0)
        mask_high = (freq >= 2000.0) & (freq <= 4000.0)
        e_low = np.sum(spec[mask_low] ** 2)
        e_high = np.sum(spec[mask_high] ** 2)
        if e_low > 1e-10 and e_high > 1e-10:
            self._spr_db = float(10 * math.log10(e_high / e_low))
        elif e_low > 1e-10:
            self._spr_db = -30.0
        else:
            self._spr_db = 0.0

        # ── Alpha Ratio: >1kHz vs <1kHz ──
        e_below = np.sum(spec[(freq >= 80.0) & (freq < 1000.0)] ** 2)
        e_above = np.sum(spec[(freq >= 1000.0) & (freq <= 4000.0)] ** 2)
        if e_below > 1e-10 and e_above > 1e-10:
            self._alpha_ratio = float(e_above / e_below)
        else:
            self._alpha_ratio = 0.0

        # ── 发音清晰度: 基于 ZCR 稳定性 ──
        self._compute_clarity(audio)

        # ── Vibrato 参数提取 ──
        self._detect_vibrato()

    def _compute_clarity(self, audio: np.ndarray) -> None:
        """从元音录音计算发音清晰度 (0-1)

        使用零交叉率 (ZCR) 的帧间变异性衡量:
        - 稳定的元音 → ZCR 一致 → 高清晰度
        - 气息声/沙哑 → ZCR 波动大 → 低清晰度
        """
        frame_len = int(SAMPLE_RATE * 0.025)  # 25ms 帧
        hop = frame_len // 2
        n_frames = (len(audio) - frame_len) // hop
        if n_frames < 4:
            self._clarity = 0.0
            return

        zcr_vals = []
        for i in range(n_frames):
            frame = audio[i * hop:i * hop + frame_len]
            # ZCR = 过零次数 / (2 * 帧长)
            zcr = np.sum(np.abs(np.diff(np.sign(frame)))) / (2 * len(frame))
            zcr_vals.append(zcr)

        zcr_vals = np.array(zcr_vals)
        median_zcr = float(np.median(zcr_vals))
        if median_zcr < 1e-8:
            self._clarity = 0.0
            return

        # 变异系数越低 → 越稳定 → 越清晰
        cv = float(np.std(zcr_vals) / median_zcr)
        self._clarity = float(np.clip(1.0 - cv / 0.5, 0.0, 1.0))

    def _detect_vibrato(self) -> None:
        """从 Phase 3 元音录音的音高轨迹提取 Vibrato 参数

        使用自相关法检测 F0 轨道的周期性调制:
        - vibrato_rate_hz: 典型范围 4.5-7.5 Hz (古典) / 3.0-6.0 Hz (流行)
        - vibrato_extent_cents: 典型范围 50-200 cents (0.5-2.0 半音)

        参考: Sundberg (1994) Acoustic and psychoacoustic aspects of vocal vibrato
        """
        if not self._pitch_track:
            return

        # 取有声帧，排除开头/结尾的不稳定段
        freqs = [(t, f) for t, f in self._pitch_track if f > 60.0]
        if len(freqs) < 30:
            return

        # 跳过前 20% 和后 10% — 取稳定中段
        n_total = len(freqs)
        start = n_total // 5
        end = int(n_total * 0.9)
        if end - start < 20:
            start, end = 0, n_total
        seg = freqs[start:end]

        # 转为半音偏差序列
        median_f = float(np.median([f for _, f in seg]))
        if median_f < 1.0:
            return
        cents_seq = np.array([1200 * math.log2(f / median_f) for _, f in seg])

        # 去直流 + 去线性趋势 (排除滑音影响)
        cents_seq = cents_seq - np.mean(cents_seq)
        t_idx = np.arange(len(cents_seq))
        if len(t_idx) > 10:
            slope, intercept = np.polyfit(t_idx, cents_seq, 1)
            cents_detrended = cents_seq - (slope * t_idx + intercept)
        else:
            cents_detrended = cents_seq

        # 自相关检测周期性
        max_lag = min(len(cents_detrended) // 2, int(SAMPLE_RATE / HOP_SIZE * 0.5))  # max 500ms lag
        min_lag = max(2, int(SAMPLE_RATE / HOP_SIZE * 0.08))  # min 80ms → 12.5 Hz max
        if max_lag <= min_lag:
            return

        ac = np.correlate(cents_detrended, cents_detrended, mode='full')
        ac = ac[len(ac) // 2:]  # 只取正半轴
        if len(ac) <= max_lag + 1:
            return
        ac = ac[min_lag:max_lag + 1]
        ac = ac / max(ac[0], 1e-10)

        # 找最大峰值
        peak_idx = int(np.argmax(ac))
        if peak_idx <= 0 or peak_idx >= len(ac) - 1:
            return
        peak_lag = peak_idx + min_lag
        peak_val = float(ac[peak_idx])

        # 显著性检查: 峰值需 > 0.35 才有意义
        if peak_val < 0.35:
            return

        # 计算速率 (Hz): hop_size_in_seconds = HOP_SIZE / SAMPLE_RATE
        hop_sec = HOP_SIZE / SAMPLE_RATE
        period_sec = peak_lag * hop_sec
        if period_sec < 1e-6:
            return
        rate = 1.0 / period_sec

        # 仅接受合理范围
        if not (3.0 <= rate <= 9.0):
            return

        self._vibrato_rate_hz = float(rate)

        # 幅度 (cents): 用滑动窗口 RMS 估计
        window = min(len(cents_detrended) // 4, peak_lag * 3)
        if window < 4:
            return
        rms_envelope = np.array([
            np.sqrt(np.mean(cents_detrended[max(0, i - window // 2):
                                             min(len(cents_detrended), i + window // 2)] ** 2))
            for i in range(0, len(cents_detrended), max(1, window // 3))
        ])
        self._vibrato_extent_cents = float(np.clip(np.median(rms_envelope) * 2.0, 0.0, 300.0))

    def _compute_dynamic_range(self, audio: Optional[np.ndarray]) -> None:
        """从滑音录音计算 RMS 动态范围 (dB)

        用于雷达图的「动态范围」维度。
        使用帧 RMS 的 P5-P95 范围，自动去除非发声段噪声。
        """
        if audio is None or len(audio) < SAMPLE_RATE * 0.5:
            self._dynamic_range_db = 0.0
            return
        frame_len = int(SAMPLE_RATE * 0.05)  # 50ms 帧
        n_frames = len(audio) // frame_len
        if n_frames < 4:
            self._dynamic_range_db = 0.0
            return
        rms_vals = []
        for i in range(n_frames):
            frame = audio[i * frame_len:(i + 1) * frame_len]
            rms = np.sqrt(np.mean(frame ** 2))
            if rms > 1e-8:
                rms_vals.append(rms)
        if len(rms_vals) < 4:
            self._dynamic_range_db = 0.0
            return
        p5 = float(np.percentile(rms_vals, 5))
        p95 = float(np.percentile(rms_vals, 95))
        if p5 > 1e-8:
            self._dynamic_range_db = float(np.clip(20 * math.log10(p95 / p5), 0.0, 40.0))
        else:
            self._dynamic_range_db = 0.0

    def _compute_pitch_stability(self) -> None:
        """从 Phase 3 元音录音的音高轨迹计算 F0 稳定性 (0-1)

        用于雷达图的「音准稳定性」维度。
        高稳定 = 元音保持在同一音高上，F0 标准差小。
        """
        # 获取有声频率: 优先实时 _pitch_track，不足时回退到离线检测
        freqs = [f for t, f in (self._pitch_track or []) if f > 60.0]
        total_frames = len(self._pitch_track) if self._pitch_track else 0
        print(f"[音准稳定性] 总帧数={total_frames}, 有声帧={len(freqs)}, 需要≥5")

        if len(freqs) < 5:
            # 回退: 对 _full_audio 做一次离线音高检测
            if self._full_audio is not None and len(self._full_audio) > SAMPLE_RATE * 0.5:
                print(f"[音准稳定性] 实时帧不足 — 尝试离线回退")
                try:
                    freqs = self._offline_pitch_track(self._full_audio)
                except Exception as exc:
                    print(f"[音准稳定性] 离线回退异常: {exc}")
                    freqs = []

            if len(freqs) < 5:
                print(f"[音准稳定性] 所有来源有声帧不足 (需要 5, 实际 {len(freqs)}) — 设为 0%")
                self._pitch_stability = 0.0
                return

        median_f = float(np.median(freqs))
        if median_f < 1.0:
            print(f"[音准稳定性] 中位频率异常 ({median_f:.1f}Hz) — 设为 0%")
            self._pitch_stability = 0.0
            return
        # 半音域标准差
        semitones = [12 * math.log2(f / median_f) for f in freqs]
        stdev_st = float(np.std(semitones))
        stability = float(np.clip(1.0 - stdev_st / 1.5, 0.0, 1.0))
        print(f"[音准稳定性] 中位={median_f:.0f}Hz, std={stdev_st:.2f}半音, "
              f"有声帧={len(freqs)}/{total_frames}, stability={stability:.1%}")
        self._pitch_stability = stability

    def _offline_pitch_track(self, audio: np.ndarray) -> List[float]:
        """对完整音频做离线音高检测，返回频率列表

        用于当实时 _pitch_track 不足时的回退方案。
        复用 _pitch_service + 低 VAD/低置信度阈值。
        """
        sr = SAMPLE_RATE
        hop = HOP_SIZE
        frame = FRAME_SIZE
        pitch_svc = getattr(self, '_pitch_service', None)
        if pitch_svc is None:
            from src.audio_processing.pitch_service import PitchDetectionService
            pitch_svc = PitchDetectionService(sr, frame, hop)

        freqs = []
        for start in range(0, len(audio) - frame, hop):
            chunk = audio[start:start + frame].astype(np.float64)
            if len(chunk) < frame:
                break
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            if rms < 0.0002:  # 极低阈值
                continue
            try:
                freq, conf = pitch_svc.detect(chunk)
                if conf > 0.06 and 60.0 < freq < 2000.0:
                    freqs.append(freq)
            except Exception:
                continue
        print(f"[音准稳定性] 离线检测: 扫描 {len(audio)//hop} 帧, 检测到 {len(freqs)} 帧")
        return freqs

    # ═══════════════════════════════════════════════════════════
    # 分类决策
    # ═══════════════════════════════════════════════════════════

    def _compute_and_display_result(self) -> None:
        """综合评分，输出声部鉴定结果"""
        # 确定性别候选集
        if self._profile.is_female:
            candidates = _FEMALE_VOICE_TYPES
        else:
            candidates = _MALE_VOICE_TYPES

        scores = {}
        breakdowns = {}

        for vt in candidates:
            s_passaggio = self._score_passaggio(vt)
            s_range = self._score_range(vt)
            s_timbre = self._score_timbre(vt)

            # 加权: 换声点 45%, 音域 30%, 音色 25%
            # 换声点权重按置信度折扣：低置信度时降低换声点贡献，侧重音域/音色
            base_weights = {"passaggio": 0.45, "range": 0.30, "timbre": 0.25}
            available = 0.0
            pp_weight = 0.0
            if self._passaggio_hz > 0:
                # 置信度折扣：低于 50% 时逐步降低换声点权重，最低保留 25%
                conf_discount = max(0.25, self._passaggio_confidence)
                pp_weight = base_weights["passaggio"] * conf_discount
                available += pp_weight
            if self._low_range_hz > 0 and self._high_range_hz > 0:
                available += base_weights["range"]
            if self._fhe_hz > 0:
                available += base_weights["timbre"]

            if available < 0.01:
                total = 1.0
            else:
                total = (
                    (s_passaggio * pp_weight if self._passaggio_hz > 0 else 0) +
                    (s_range * base_weights["range"] if self._low_range_hz > 0 else 0) +
                    (s_timbre * base_weights["timbre"] if self._fhe_hz > 0 else 0)
                ) / available

            scores[vt] = total
            breakdowns[vt] = {"passaggio": s_passaggio, "range": s_range, "timbre": s_timbre}

        # 排序
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_vt, best_score = ranked[0]
        runner_up = ranked[1] if len(ranked) > 1 else None

        # 置信度映射
        gap = best_score - (runner_up[1] if runner_up else 0.0)
        if gap > 0.30:
            conf_level = "高"
            conf_pct = 0.85
        elif gap > 0.15:
            conf_level = "中"
            conf_pct = 0.65
        elif gap > 0.05:
            conf_level = "较低 (边界声部)"
            conf_pct = 0.45
        else:
            conf_level = "低 (数据不足以区分)"
            conf_pct = 0.30

        # 考虑换声点置信度
        if self._passaggio_confidence > 0:
            conf_pct = 0.6 * conf_pct + 0.4 * self._passaggio_confidence

        # ── 显示结果 ──
        display_name = _VOICE_TYPE_SHORT.get(best_vt, best_vt)
        self._result_primary.setText(f"🎤 {display_name}")
        self._result_primary.setStyleSheet("""
            color: #FFFFFF; font-size: 30px; font-weight: bold;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #238636, stop:1 #1F6FEB);
            border-radius: 12px; padding: 16px;
        """)

        self._result_confidence.setText(
            f"置信度: {conf_level} ({conf_pct:.0%})　｜　"
            f"与次选「{_VOICE_TYPE_SHORT.get(runner_up[0], runner_up[0])}」差距: {gap:.1%}"
        )

        # ── 可视化: 条形图 + 雷达图 + 频谱 ──
        # 1. 条形图 — 各声部得分
        bar_data = [(vt, scores[vt], vt == best_vt) for vt, _ in ranked]
        self._result_bar_chart.set_scores(bar_data)

        # 2. 雷达图 — 6 维声乐画像
        radar = {}

        # 音域: 半音跨度归一化 (0-30 semitones → 0-1)
        if self._low_range_hz > 0 and self._high_range_hz > 0:
            st_range = 12 * math.log2(self._high_range_hz / self._low_range_hz)
            radar["range"] = float(np.clip(st_range / 30.0, 0.0, 1.0))
        else:
            radar["range"] = 0.0

        # 换声点确定度: 直接使用 confidence
        radar["passaggio"] = self._passaggio_confidence if self._passaggio_hz > 0 else 0.0

        # 音色亮度: FHE 相对于声部参考值的归一化
        if self._fhe_hz > 0:
            ref_fhe = _TIMBRE_FHE.get(best_vt, 2700.0)
            # FHE 偏高 → 更亮; 偏低 → 更暗; 以 ±2σ (440 Hz) 为区间映射到 0-1
            brightness_z = (self._fhe_hz - ref_fhe) / 440.0
            radar["brightness"] = float(np.clip(0.5 + brightness_z * 0.25, 0.05, 0.95))
        else:
            radar["brightness"] = 0.0

        # 音色质量
        radar["quality"] = self._timbre_quality if self._fhe_hz > 0 else 0.0

        # 音准稳定性
        radar["stability"] = self._pitch_stability

        # 动态范围: 6-30 dB → 0-1
        radar["dynamics"] = float(np.clip((self._dynamic_range_db - 6.0) / 24.0, 0.0, 1.0)) \
            if self._dynamic_range_db > 0 else 0.0

        self._result_radar_chart.set_values(radar)

        # 3. 频谱缩略图
        if self._fhe_hz > 0 and self._full_audio is not None:
            # 根据最佳声部自适应选择频段
            if best_vt == "soprano":
                band_low, band_high = 2300, 4500
            else:
                band_low, band_high = 2000, 3600
            self._result_spectrum.set_spectrum(
                self._full_audio, self._fhe_hz, band_low, band_high
            )

        # 详细数据
        lines = []
        lines.append("📊 检测数据汇总")
        lines.append("─" * 30)

        if self._low_range_hz > 0 and self._high_range_hz > 0:
            low_n = _hz_to_note_name(self._low_range_hz)
            high_n = _hz_to_note_name(self._high_range_hz)
            st = 12 * math.log2(self._high_range_hz / self._low_range_hz)
            lines.append(f"🎵 音域: {low_n} → {high_n} ({st:.0f} 半音)")

        if self._passaggio_hz > 0:
            pp_n = _hz_to_note_name(self._passaggio_hz)
            lines.append(f"🔄 换声点: {pp_n} ({self._passaggio_hz:.0f} Hz)　置信度 {self._passaggio_confidence:.0%}")

        if self._fhe_hz > 0:
            band_str = "2300-4500 Hz" if self._profile.is_female else "2000-3600 Hz"
            lines.append(f"🎨 音色 FHE: {self._fhe_hz:.0f} Hz ({band_str} 频段)")
            lines.append(f"   PHE: {self._phe:.0%}　｜　频谱重心: {self._spectral_centroid_hz:.0f} Hz")
            quality_label = "⭐" if self._timbre_quality > 0.7 else "✨" if self._timbre_quality > 0.4 else "💨"
            lines.append(f"   音色质量: {quality_label} {self._timbre_quality:.0%}")
        if self._spr_db != 0.0:
            spr_label = "偏亮" if self._spr_db > -3 else "平衡" if self._spr_db > -8 else "偏暖"
            lines.append(f"📐 SPR: {self._spr_db:+.1f} dB ({spr_label})")
        if self._alpha_ratio > 0:
            lines.append(f"    α比值: {self._alpha_ratio:.2f} (高频/低频能量比)")

        if self._vibrato_rate_hz > 0:
            lines.append(f"〰️ Vibrato: {self._vibrato_rate_hz:.1f} Hz　幅度 {self._vibrato_extent_cents:.0f} cents")

        if self._clarity > 0:
            lines.append(f"🗣️ 发音清晰度: {self._clarity:.0%}")

        if self._dynamic_range_db > 0:
            lines.append(f"📢 动态范围: {self._dynamic_range_db:.0f} dB")

        lines.append(f"🎯 音准稳定性: {self._pitch_stability:.0%}"
                     + ("  ⚠️ 数据不足" if self._pitch_stability < 0.01 else ""))

        # FHE 异常检测：偏差 > 2.5σ 时发出警告
        if self._fhe_hz > 0 and best_vt in _TIMBRE_FHE:
            ref_fhe = _TIMBRE_FHE.get(best_vt, 2700)
            fhe_z = abs(self._fhe_hz - ref_fhe) / 220.0
            if fhe_z > 2.5:
                is_high = self._fhe_hz > ref_fhe
                lines.append("")
                lines.append(f"⚠️ 音色数据异常 (FHE 偏差 {fhe_z:.1f}σ)："
                           f"测得 FHE = {self._fhe_hz:.0f} Hz，"
                           f"{_VOICE_TYPE_DISPLAY.get(best_vt, best_vt)}参考值 {ref_fhe} Hz。")
                if is_high:
                    lines.append("   可能原因：① Phase 3 未发声或音量过低　② 使用了假声而非真声")
                else:
                    lines.append("   可能原因：① 音频含有低频噪声　② 话筒距嘴过近产生近讲效应")
                lines.append("   建议重新进行声部鉴定测评，注意 Phase 3 用胸声/真声唱。")

        self._result_details.setText("\n".join(lines))

        # 各声部得分
        score_lines = ["📈 声部分数 (0-1):"]
        for vt, score in ranked:
            bar_len = int(score * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            name = _VOICE_TYPE_SHORT.get(vt, vt)
            marker = " ← 最优" if vt == best_vt else ""
            score_lines.append(f"  {name:6s} [{bar}] {score:.3f}{marker}")

        if self._passaggio_hz > 0:
            score_lines.append(f"\n💡 换声点 {_hz_to_note_name(self._passaggio_hz)} ({self._passaggio_hz:.0f} Hz) "
                             f"— 参考: 男中音 D4-F4 (294-349 Hz), 男高音 F4-A4 (349-440 Hz)")

        self._result_scores.setText("\n".join(score_lines))

        # 显示导出按钮
        self._result_export_btn.setVisible(True)

        # ── 自动保存 ──
        self._profile.voice_type_inferred = best_vt
        if self._passaggio_hz > 0:
            self._profile.passaggio.t4_hz = self._passaggio_hz
            self._profile.passaggio.source = "calibrated"
            self._profile.passaggio.confidence = self._passaggio_confidence
            self._profile.passaggio.last_calibrated = time.strftime("%Y-%m-%d")
        # 更新音域统计
        if self._low_range_hz > 0:
            stats = self._profile.pitch_stats
            if stats.total_voiced_frames == 0:
                stats.total_voiced_frames = 100
            stats.min_hz = self._low_range_hz
            stats.max_hz = self._high_range_hz
        # 更新音色 — 所有特征均从录制音频计算，不再硬编码 0
        if self._fhe_hz > 0:
            self._profile.timbre.update(
                spectral_tilt=self._compute_spectral_tilt_from_audio(),
                hm_over_hh=self._compute_hm_over_hh_from_audio(),
                mid_high_ratio=self._compute_mid_high_ratio_from_audio(),
                zcr=self._compute_zcr_from_audio(),
                rms=self._compute_rms_from_audio(),
            )
            self._profile.timbre.fhe_hz = self._fhe_hz
            self._profile.timbre.spectral_centroid_hz = self._spectral_centroid_hz
            self._profile.timbre.timbre_quality = self._timbre_quality

        self._mgr.save_profile(self._profile)
        self.assessment_completed.emit(self._profile.id)

        # 自动导出 HTML 报告
        try:
            self._export_report()
        except Exception:
            pass  # 静默失败，不影响测评流程

        self._set_progress(4)
        self._back_btn.setVisible(False)
        self._next_btn.setText("✅ 完成")
        self._switch_page(self.PAGE_RESULT)

    def _score_passaggio(self, voice_type: str) -> float:
        """评分换声点匹配度 (0-1)"""
        return _score_passaggio_for_hz(self._passaggio_hz, voice_type)

    def _score_range(self, voice_type: str) -> float:
        """评分音域匹配度 (0-1)"""
        return _score_range_for_hz(self._low_range_hz, self._high_range_hz, voice_type)

    def _score_timbre(self, voice_type: str) -> float:
        """评分音色匹配度 (0-1) 基于 FHE"""
        return _score_timbre_for_fhe(self._fhe_hz, voice_type)

    def _compute_spectral_tilt_from_audio(self) -> float:
        """从录制音频计算频谱倾斜（用于保存到 timbre fingerprint）"""
        if self._full_audio is not None and len(self._full_audio) > 0:
            return self._compute_spectral_tilt(self._full_audio, SAMPLE_RATE)
        return 0.0

    def _compute_mid_high_ratio_from_audio(self) -> float:
        """从录制音频计算中高频能量比 mid(300-3000Hz) / high(>3000Hz)"""
        if self._full_audio is None or len(self._full_audio) == 0:
            return 1.0
        return self._compute_mid_high_ratio(self._full_audio, SAMPLE_RATE)

    def _compute_hm_over_hh_from_audio(self) -> float:
        """从录制音频计算中高频谐波能量比 hm(2-6kHz) / hh(>6kHz)"""
        if self._full_audio is None or len(self._full_audio) == 0:
            return 1.0
        return self._compute_hm_over_hh(self._full_audio, SAMPLE_RATE)

    def _compute_zcr_from_audio(self) -> float:
        """从录制音频计算过零率"""
        if self._full_audio is None or len(self._full_audio) == 0:
            return 0.0
        return float(np.mean(np.abs(np.diff(np.sign(self._full_audio)))) / 2)

    def _compute_rms_from_audio(self) -> float:
        """从录制音频计算 RMS 能量"""
        if self._full_audio is None or len(self._full_audio) == 0:
            return 0.0
        return float(np.sqrt(np.mean(self._full_audio ** 2)))

    # ═══════════════════════════════════════════════════════════
    # 报告生成 (P2)
    # ═══════════════════════════════════════════════════════════

    def generate_html_report(self) -> str:
        """生成自包含的 HTML 声乐评估报告

        包含:
          - 歌手信息头部 + 声部鉴定结果
          - SVG 雷达图
          - CSS 声部分数条形图
          - 详细指标表格
          - AI 教练建议区
        """
        # ── 收集数据 ──
        profile_name = self._profile.name or "未命名"
        date_str = time.strftime("%Y-%m-%d %H:%M")
        best_vt = self._profile.voice_type_inferred or ""
        display_vt = _VOICE_TYPE_DISPLAY.get(best_vt, best_vt) if best_vt else "未测定"

        # 计算各个声部得分 (recompute for the report)
        if self._profile.is_female:
            candidates = _FEMALE_VOICE_TYPES
        else:
            candidates = _MALE_VOICE_TYPES

        scores = {}
        for vt in candidates:
            s_passaggio = self._score_passaggio(vt) if self._passaggio_hz > 0 else 0.5
            s_range = self._score_range(vt) if self._low_range_hz > 0 else 0.5
            s_timbre = self._score_timbre(vt) if self._fhe_hz > 0 else 0.5
            weights = {"passaggio": 0.45, "range": 0.30, "timbre": 0.25}
            available = 0.0
            if self._passaggio_hz > 0:
                available += weights["passaggio"]
            if self._low_range_hz > 0 and self._high_range_hz > 0:
                available += weights["range"]
            if self._fhe_hz > 0:
                available += weights["timbre"]
            if available < 0.01:
                scores[vt] = 0.5
            else:
                total = (s_passaggio * weights["passaggio"] if self._passaggio_hz > 0 else 0)
                total += (s_range * weights["range"] if self._low_range_hz > 0 else 0)
                total += (s_timbre * weights["timbre"] if self._fhe_hz > 0 else 0)
                scores[vt] = total / available

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_score = ranked[0][1] if ranked else 0.0
        runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0
        gap = best_score - runner_up_score

        # 置信度
        if gap > 0.30:
            conf_level, conf_pct = "高", 0.85
        elif gap > 0.15:
            conf_level, conf_pct = "中", 0.65
        elif gap > 0.05:
            conf_level, conf_pct = "较低 (边界声部)", 0.45
        else:
            conf_level, conf_pct = "低", 0.30
        if self._passaggio_confidence > 0:
            conf_pct = 0.6 * conf_pct + 0.4 * self._passaggio_confidence

        # ── 雷达图数据 ──
        radar = {}
        if self._low_range_hz > 0 and self._high_range_hz > 0:
            st_range = 12 * math.log2(self._high_range_hz / self._low_range_hz)
            radar["音域"] = min(1.0, st_range / 30.0)
        else:
            radar["音域"] = 0.0
        radar["换声点确定度"] = self._passaggio_confidence if self._passaggio_hz > 0 else 0.0
        if self._fhe_hz > 0:
            ref_fhe = _TIMBRE_FHE.get(best_vt, 2700.0)
            radar["音色亮度"] = float(np.clip(0.5 + (self._fhe_hz - ref_fhe) / 440.0 * 0.25, 0.05, 0.95))
        else:
            radar["音色亮度"] = 0.0
        radar["音色质量"] = self._timbre_quality
        radar["音准稳定性"] = self._pitch_stability
        radar["动态范围"] = float(np.clip((self._dynamic_range_db - 6.0) / 24.0, 0.0, 1.0)) if self._dynamic_range_db > 0 else 0.0

        # ── 生成 SVG 雷达图 ──
        radar_svg = self._build_svg_radar(radar)

        # ── 生成 HTML ──
        lines = []
        lines.append('<!DOCTYPE html>')
        lines.append('<html lang="zh-CN">')
        lines.append('<head>')
        lines.append('<meta charset="UTF-8">')
        lines.append(f'<title>MindEcho 声乐评估报告 — {profile_name}</title>')
        lines.append('<style>')
        lines.append(self._html_report_css())
        lines.append('</style>')
        lines.append('</head>')
        lines.append('<body>')

        # ── 头部 ──
        lines.append('<header class="report-header">')
        lines.append(f'<h1>🎤 MindEcho 声乐评估报告</h1>')
        lines.append(f'<p class="subtitle">歌手: {profile_name}　｜　评估时间: {date_str}</p>')
        lines.append('</header>')

        # ── 声部鉴定摘要 ──
        lines.append('<section class="summary">')
        lines.append(f'<div class="voice-type-badge">{display_vt}</div>')
        lines.append(f'<p class="confidence">置信度: {conf_level} ({conf_pct:.0%})　｜　与次选差距: {gap:.1%}</p>')
        lines.append('</section>')

        # ── 雷达图 + 条形图并排 ──
        lines.append('<section class="charts-row">')

        # 雷达图
        lines.append('<div class="chart-box">')
        lines.append('<h3>🎯 声乐画像 (6维雷达)</h3>')
        lines.append(radar_svg)
        lines.append('</div>')

        # 条形图
        lines.append('<div class="chart-box">')
        lines.append('<h3>📈 声部分数</h3>')
        bar_colors = {
            "bass": "#8B5CF6", "baritone": "#3B82F6", "tenor": "#06B6D4",
            "contralto": "#F59E0B", "mezzo_soprano": "#EF4444", "soprano": "#EC4899",
        }
        for vt, score in ranked:
            short = _VOICE_TYPE_SHORT.get(vt, vt)
            pct = int(score * 100)
            color = bar_colors.get(vt, "#6E7681")
            is_best = vt == ranked[0][0]
            star = ' ★' if is_best else ''
            lines.append(f'<div class="bar-row">')
            lines.append(f'<span class="bar-label">{short}{star}</span>')
            lines.append(f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color};"></div></div>')
            lines.append(f'<span class="bar-pct">{score:.0%}</span>')
            lines.append(f'</div>')
        lines.append('</div>')

        lines.append('</section>')

        # ── 详细指标表格 ──
        lines.append('<section class="details">')
        lines.append('<h3>📊 详细检测指标</h3>')
        lines.append('<table>')
        rows = []

        if self._low_range_hz > 0 and self._high_range_hz > 0:
            low_n = _hz_to_note_name(self._low_range_hz)
            high_n = _hz_to_note_name(self._high_range_hz)
            st = 12 * math.log2(self._high_range_hz / self._low_range_hz)
            rows.append(('🎵 舒适音域', f'{low_n} → {high_n} ({st:.0f} 半音)'))
        if self._passaggio_hz > 0:
            pp_n = _hz_to_note_name(self._passaggio_hz)
            rows.append(('🔄 第二换声点 (T4)', f'{pp_n} ({self._passaggio_hz:.0f} Hz) — 置信度 {self._passaggio_confidence:.0%}'))
        if self._fhe_hz > 0:
            band_str = '2300-4500 Hz' if self._profile.is_female else '2000-3600 Hz'
            rows.append(('🎨 FHE (半能量频率)', f'{self._fhe_hz:.0f} Hz ({band_str})'))
            rows.append(('📍 PHE (半能量位置)', f'{self._phe:.0%}'))
            rows.append(('📐 频谱重心', f'{self._spectral_centroid_hz:.0f} Hz'))
            rows.append(('💎 音色质量', f'{self._timbre_quality:.0%}'))
        if self._vibrato_rate_hz > 0:
            rows.append(('〰️ Vibrato 速率', f'{self._vibrato_rate_hz:.1f} Hz'))
            rows.append(('〰️ Vibrato 幅度', f'{self._vibrato_extent_cents:.0f} cents'))
        if self._clarity > 0:
            rows.append(('🗣️ 发音清晰度', f'{self._clarity:.0%}'))
        if self._spr_db != 0.0:
            rows.append(('📐 SPR (歌唱功率比)', f'{self._spr_db:+.1f} dB'))
        if self._alpha_ratio > 0:
            rows.append(('🔢 α比值 (高低频能量比)', f'{self._alpha_ratio:.2f}'))
        if self._dynamic_range_db > 0:
            rows.append(('📢 动态范围', f'{self._dynamic_range_db:.0f} dB'))
        rows.append(('🎯 音准稳定性', f'{self._pitch_stability:.0%}'
                     + (' ⚠️ 数据不足' if self._pitch_stability < 0.01 else '')))

        for label, value in rows:
            lines.append(f'<tr><td class="metric-label">{label}</td><td class="metric-value">{value}</td></tr>')

        # FHE 异常警告行
        if self._fhe_hz > 0 and best_vt in _TIMBRE_FHE:
            ref_fhe = _TIMBRE_FHE.get(best_vt, 2700)
            fhe_z = abs(self._fhe_hz - ref_fhe) / 220.0
            if fhe_z > 2.5:
                is_high = self._fhe_hz > ref_fhe
                cause = ("未发声/音量过低，或使用了假声" if is_high
                         else "低频噪声干扰，或话筒距嘴过近")
                lines.append(f'<tr class="warning-row">'
                           f'<td class="metric-label">⚠️ FHE 异常</td>'
                           f'<td class="metric-value">偏差 {fhe_z:.1f}σ — 可能原因：{cause}。建议重新测评。</td>'
                           f'</tr>')

        lines.append('</table>')
        lines.append('</section>')

        # ── 参考范围对比 ──
        if self._passaggio_hz > 0 and best_vt in _PASSAGGIO_RANGE:
            pp_lo, pp_hi = _PASSAGGIO_RANGE[best_vt]
            pp_note = _hz_to_note_name(self._passaggio_hz)
            lo_note = _hz_to_note_name(pp_lo)
            hi_note = _hz_to_note_name(pp_hi)
            in_range = "✅ 在范围内" if pp_lo <= self._passaggio_hz <= pp_hi else "⚠️ 超出典型范围"
            lines.append('<section class="comparison">')
            lines.append(f'<h3>📏 换声点参考对比 ({_VOICE_TYPE_SHORT.get(best_vt, best_vt)})</h3>')
            lines.append(f'<p>你的 T4: <strong>{pp_note} ({self._passaggio_hz:.0f} Hz)</strong></p>')
            lines.append(f'<p>参考范围: {lo_note}–{hi_note} ({pp_lo:.0f}–{pp_hi:.0f} Hz) — {in_range}</p>')
            lines.append('</section>')

        # ── AI 教练建议区 ──
        lines.append('<section class="recommendations">')
        lines.append('<h3>🤖 AI 教练建议</h3>')
        lines.append('<div class="coach-notes">')
        if best_vt:
            lines.append(f'<p>你的声部被鉴定为 <strong>{display_vt}</strong>。建议重点练习以下内容:</p>')
            lines.append('<ul>')
            if best_vt in ("tenor", "soprano"):
                lines.append('<li>关注换声区过渡技巧 (passaggio technique)，练习在换声点附近保持音色统一</li>')
                lines.append('<li>加强高音区头声共鸣训练</li>')
            elif best_vt in ("baritone", "mezzo_soprano"):
                lines.append('<li>发挥中音区丰富音色的优势，扩展高低音域的灵活性</li>')
                lines.append('<li>练习换声区平滑过渡，避免明显的音色断裂</li>')
            else:
                lines.append('<li>利用低音区共鸣优势，逐步向上扩展音域</li>')
                lines.append('<li>练习呼吸支持以增强高音区的稳定性</li>')
            lines.append(f'<li>已记录你的换声点 T4 ≈ {_hz_to_note_name(self._passaggio_hz)} — AI Coach 会在后续练习中针对性提示</li>')\
                if self._passaggio_hz > 0 else ''
            lines.append('</ul>')
        else:
            lines.append('<p>尚未完成声部鉴定。请完成所有测评阶段以获得个性化建议。</p>')
        lines.append('</div>')
        lines.append('</section>')

        # ── 页脚 ──
        lines.append('<footer>')
        lines.append(f'<p>MindEcho v1.0 — 智能声乐教练　｜　报告生成: {date_str}</p>')
        lines.append('<p>参考数据来源: Müller et al. (2022) Scientific Reports; Richard Miller 声乐教学文献</p>')
        lines.append('</footer>')

        lines.append('</body>')
        lines.append('</html>')

        return '\n'.join(lines)

    def _build_svg_radar(self, values: dict) -> str:
        """生成内嵌 SVG 雷达图 (用于 HTML 报告)

        values: {"音域": 0.7, "换声点确定度": 0.85, ...}
        """
        dims = [
            ("音域", 0), ("换声点\n确定度", 1), ("音色\n亮度", 2),
            ("音色\n质量", 3), ("音准\n稳定性", 4), ("动态\n范围", 5),
        ]
        n = len(dims)
        cx, cy, r = 150, 150, 110
        axis_colors = ["#3B82F6", "#8B5CF6", "#F59E0B", "#EF4444", "#06B6D4", "#10B981"]

        svg = []
        svg.append(f'<svg viewBox="0 0 300 320" width="300" height="320" xmlns="http://www.w3.org/2000/svg">')

        # 背景网格
        for level in [0.33, 0.66, 1.0]:
            pts = []
            for i in range(n):
                angle = -math.pi / 2 + 2 * math.pi * i / n
                x = cx + r * level * math.cos(angle)
                y = cy + r * level * math.sin(angle)
                pts.append(f'{x:.1f},{y:.1f}')
            poly = ' '.join(pts)
            stroke = '#30363D' if level < 0.99 else '#484F58'
            svg.append(f'<polygon points="{poly}" fill="none" stroke="{stroke}" stroke-width="1"/>')

        # 轴线
        for i in range(n):
            angle = -math.pi / 2 + 2 * math.pi * i / n
            ex = cx + r * math.cos(angle)
            ey = cy + r * math.sin(angle)
            svg.append(f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{axis_colors[i]}" stroke-opacity="0.3" stroke-width="0.7"/>')

        # 数据多边形
        pts = []
        for dim_name, i in dims:
            val = values.get(dim_name.replace('\n', ''), 0.0)
            val = max(0.0, min(1.0, val))
            angle = -math.pi / 2 + 2 * math.pi * i / n
            x = cx + r * val * math.cos(angle)
            y = cy + r * val * math.sin(angle)
            pts.append(f'{x:.1f},{y:.1f}')
        poly = ' '.join(pts)
        svg.append(f'<polygon points="{poly}" fill="#1F6FEB" fill-opacity="0.25" stroke="#58A6FF" stroke-width="2"/>')

        # 顶点
        for pt in pts:
            x, y = pt.split(',')
            svg.append(f'<circle cx="{x}" cy="{y}" r="3.5" fill="#58A6FF"/>')

        # 标签
        for dim_name, i in dims:
            angle = -math.pi / 2 + 2 * math.pi * i / n
            lx = cx + (r + 32) * math.cos(angle)
            ly = cy + (r + 32) * math.sin(angle)
            color = axis_colors[i]
            lines = dim_name.split('\n')
            for li, line in enumerate(lines):
                offset_y = (li - (len(lines) - 1) / 2) * 12
                svg.append(f'<text x="{lx:.1f}" y="{ly + offset_y:.1f}" text-anchor="middle" '
                           f'fill="{color}" font-size="10" font-weight="bold" '
                           f'font-family="sans-serif">{line}</text>')

        svg.append('</svg>')
        return '\n'.join(svg)

    @staticmethod
    def _html_report_css() -> str:
        """报告 CSS 样式 (暗色主题)"""
        return '''
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                background: #0D1117; color: #C9D1D9;
                max-width: 800px; margin: 0 auto; padding: 24px 20px 40px;
                line-height: 1.6;
            }
            .report-header {
                text-align: center; padding-bottom: 20px;
                border-bottom: 2px solid #21262D; margin-bottom: 24px;
            }
            .report-header h1 { font-size: 26px; color: #E6EDF3; }
            .subtitle { color: #8B949E; font-size: 13px; margin-top: 6px; }
            .summary { text-align: center; margin-bottom: 28px; }
            .voice-type-badge {
                display: inline-block; font-size: 28px; font-weight: bold;
                color: #FFFFFF;
                background: linear-gradient(135deg, #238636, #1F6FEB);
                border-radius: 12px; padding: 14px 40px; margin-bottom: 10px;
            }
            .confidence { color: #8B949E; font-size: 13px; }
            .charts-row {
                display: flex; gap: 20px; margin-bottom: 28px;
                justify-content: center; flex-wrap: wrap;
            }
            .chart-box {
                background: #161B22; border: 1px solid #21262D;
                border-radius: 10px; padding: 16px; min-width: 280px;
            }
            .chart-box h3 { color: #8B949E; font-size: 14px; margin-bottom: 12px; text-align: center; }
            .bar-row { display: flex; align-items: center; margin-bottom: 8px; gap: 10px; }
            .bar-label { width: 80px; text-align: right; font-size: 12px; color: #C9D1D9; }
            .bar-track {
                flex: 1; height: 20px; background: #21262D;
                border-radius: 4px; overflow: hidden; min-width: 100px;
            }
            .bar-fill {
                height: 100%; border-radius: 4px;
                transition: width 0.3s;
            }
            .bar-pct { width: 40px; font-size: 12px; color: #8B949E; }
            .details {
                background: #161B22; border: 1px solid #21262D;
                border-radius: 10px; padding: 20px; margin-bottom: 24px;
            }
            .details h3 { color: #E6EDF3; font-size: 16px; margin-bottom: 14px; }
            table { width: 100%; border-collapse: collapse; }
            .metric-label {
                padding: 8px 12px; border-bottom: 1px solid #21262D;
                color: #8B949E; font-size: 13px; width: 40%;
            }
            .metric-value {
                padding: 8px 12px; border-bottom: 1px solid #21262D;
                color: #E6EDF3; font-size: 13px; font-weight: 500;
            }
            .warning-row td {
                background: rgba(210, 153, 34, 0.1); color: #D29922;
                padding: 8px 12px; border-bottom: 1px solid #21262D;
                font-size: 12px;
            }
            .comparison {
                background: #161B22; border: 1px solid #21262D;
                border-radius: 10px; padding: 20px; margin-bottom: 24px;
            }
            .comparison h3 { color: #E6EDF3; font-size: 16px; margin-bottom: 10px; }
            .comparison p { color: #C9D1D9; font-size: 13px; margin-bottom: 4px; }
            .recommendations {
                background: #161B22; border: 1px solid #21262D;
                border-radius: 10px; padding: 20px; margin-bottom: 24px;
            }
            .recommendations h3 { color: #E6EDF3; font-size: 16px; margin-bottom: 10px; }
            .coach-notes p { color: #C9D1D9; font-size: 13px; margin-bottom: 8px; }
            .coach-notes ul { margin-left: 20px; color: #8B949E; font-size: 13px; }
            .coach-notes li { margin-bottom: 5px; }
            footer {
                text-align: center; padding-top: 20px;
                border-top: 1px solid #21262D; color: #484F58; font-size: 11px;
            }
            footer p { margin-bottom: 2px; }
            @media (max-width: 640px) {
                .charts-row { flex-direction: column; }
                .chart-box { min-width: auto; }
            }
        '''

    def _export_report(self) -> None:
        """导出 HTML 声乐评估报告到文件

        保存到 profiles/<name>/reports/ 目录下，
        文件名格式: report_YYYYMMDD_HHMMSS.html
        """
        # 生成 HTML
        html = self.generate_html_report()

        # 确定保存路径: profiles/<name>/reports/
        from pathlib import Path
        profile_dir = self._mgr._root / self._profile.folder_name
        if profile_dir.exists():
            report_dir = profile_dir / "reports"
        else:
            report_dir = Path.home() / ".mindecho" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"report_{timestamp}.html"
        filepath = report_dir / filename

        try:
            filepath.write_text(html, encoding='utf-8')
        except Exception as e:
            QMessageBox.warning(self, "导出失败", f"无法写入文件:\n{filepath}\n\n错误: {e}")
            return

        # 尝试用默认浏览器打开
        import webbrowser
        try:
            webbrowser.open(str(filepath))
        except Exception:
            pass

        QMessageBox.information(
            self, "报告已导出",
            f"声乐评估报告已保存到:\n{filepath}\n\n已在浏览器中打开。"
        )

    # ═══════════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════════

    def _show_warning(self, msg: str) -> None:
        QMessageBox.warning(self, "提示", msg)

    def closeEvent(self, event) -> None:
        self._stop_audio_stream()
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════
# 自定义控件
# ═══════════════════════════════════════════════════════════════

_DISPLAY_HISTORY_SECS = 20  # 显示最近 N 秒的音高轨迹


class _PitchTraceCanvas(QWidget):
    """ECG 风格实时音高轨迹画布 + 录音后交互选取换声点

    实时模式: add_point() 追加数据
    回放模式: set_review_data() 全量显示 + 悬停高亮 + 点击选取
    """

    passaggio_selected = pyqtSignal(float)  # 用户点击选取的 Hz

    # 颜色映射: (freq_min, freq_max, color_hex)
    _COLOR_BANDS = [
        (30, 65,   "#1E3A6E"),   # C1-B1: 极低音深蓝
        (65, 131,  "#1E90FF"),   # C2-B2: 低音蓝
        (131, 262, "#00BFFF"),   # C3-B3: 中低音青
        (262, 523, "#00FF7F"),   # C4-B4: 中音绿
        (523, 785, "#ADFF2F"),   # C5-G5: 中高音黄绿
        (785, 1175, "#FF8C00"),  # G5-D6: 高音橙
        (1175, 2100, "#FF4444"), # D#6-C7: 超高音红
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet(
            "background: #0A0E14; border: 1px solid #1C2333; border-radius: 8px;"
        )
        self._points: Deque[Tuple[float, float]] = deque(maxlen=700)
        # 回放模式数据
        self._review_data: List[Tuple[float, float]] = []
        self._review_t4: float = 0.0
        self._is_review_mode: bool = False
        self._hovered_hz: float = 0.0
        self._hovered_x: float = -1.0
        self._hovered_y: float = 0.0

    def add_point(self, elapsed: float, freq_hz: float) -> None:
        self._points.append((elapsed, freq_hz))
        self.update()

    def set_review_data(self, pitch_data: List[Tuple[float, float]], t4_hz: float) -> None:
        """切换到回放模式: 显示完整轨迹 + 支持悬停点击选取"""
        self._review_data = [(t, f) for t, f in pitch_data if f > 0]
        self._review_t4 = t4_hz
        self._is_review_mode = True
        self._points.clear()
        self.update()

    def clear(self) -> None:
        self._points.clear()
        self._review_data.clear()
        self._review_t4 = 0.0
        self._is_review_mode = False
        self._hovered_hz = 0.0
        self._hovered_x = -1.0
        self.update()

    def _find_nearest_data(self, px: float, py: float, ml: float, plot_w: float, plot_h: float, mt: float) -> Tuple[float, float, float]:
        """查找最接近鼠标位置的数据点 → (freq_hz, screen_x)"""
        data = self._review_data if self._is_review_mode else list(self._points)
        if not data or plot_w <= 0:
            return 0.0, 0.0
        data_start, data_end = data[0][0], data[-1][0]
        dur = data_end - data_start
        if dur <= 0:
            dur = 1.0
        hover_t = data_start + ((px - ml) / plot_w) * dur
        best_d, best_hz, best_t = float('inf'), 0.0, hover_t
        for t, f in data:
            d = abs(t - hover_t)
            if d < best_d:
                best_d, best_hz, best_t = d, f, t
        if best_d > dur * 0.05:
            return 0.0, 0.0
        x = ml + plot_w * (best_t - data_start) / dur
        return best_hz, x

    def mouseMoveEvent(self, event) -> None:
        if not self._is_review_mode:
            return
        w, h = self.width(), self.height()
        ml, mr, mt, mb = 48, 14, 14, 22
        plot_w, plot_h = w - ml - mr, h - mt - mb
        if plot_w <= 0:
            return
        px, py = event.position().x(), event.position().y()
        if not (ml <= px <= ml + plot_w and mt <= py <= mt + plot_h):
            self._hovered_x = -1.0
            self.update()
            return
        hz, x = self._find_nearest_data(px, py, ml, plot_w, plot_h, mt)
        if hz > 0:
            self._hovered_hz = hz
            self._hovered_x = x
            self._hovered_y = self._freq_to_y_scaled(hz, plot_h, mt)
        else:
            self._hovered_x = -1.0
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered_x = -1.0
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._is_review_mode:
            return
        if self._hovered_hz <= 0:
            return
        note = _hz_to_note_name(self._hovered_hz)
        msg = QMessageBox(self)
        msg.setWindowTitle("选取换声点")
        msg.setText(f"是否将换声点设置为\n<b style='color:#FFD54F;'>{note} ({self._hovered_hz:.0f} Hz)</b>？")
        msg.setInformativeText("该点将被加入候选列表。")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        msg.setStyleSheet("""
            QMessageBox { background-color: #161B22; color: #E6EDF3; }
            QMessageBox QLabel { color: #E6EDF3; font-size: 13px; background: transparent; }
            QPushButton { background: #21262D; color: #E6EDF3; border: 1px solid #30363D;
                border-radius: 6px; padding: 6px 20px; font-size: 12px; min-width: 80px; }
            QPushButton:hover { background: #30363D; border-color: #58A6FF; }
        """)
        if msg.exec() == QMessageBox.StandardButton.Yes:
            self.passaggio_selected.emit(self._hovered_hz)

    @staticmethod
    def _freq_to_color(f: float) -> QColor:
        """频率 → 彩虹色 (线性插值)"""
        for lo, hi, c in _PitchTraceCanvas._COLOR_BANDS:
            if lo <= f < hi:
                return QColor(c)
        if f < 30:
            return QColor("#1E3A6E")
        return QColor("#FF4444")

    def _freq_to_y_scaled(self, f: float, plot_h: float, margin_top: float) -> float:
        """对数 Y 映射: 30 Hz (C1≈32.7) → 2100 Hz (C7≈2093)"""
        if f <= 0:
            return margin_top + plot_h
        fmin, fmax = 30.0, 2100.0  # C1-C7 全覆盖
        log_f = math.log2(max(f, fmin))
        ratio = (log_f - math.log2(fmin)) / (math.log2(fmax) - math.log2(fmin))
        return margin_top + plot_h * (1.0 - np.clip(ratio, 0.0, 1.0))

    @staticmethod
    def _hz_to_note_y(f: float) -> str:
        """频率 → 音名 (仅显示升降号)"""
        if f <= 0:
            return ""
        midi = 69 + 12 * math.log2(f / 440.0)
        ni = int(round(midi)) % 12
        octave = int(round(midi)) // 12 - 1
        return f"{_NOTE_NAMES[ni]}{octave}"

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        ml, mr, mt, mb = 48, 14, 14, 22
        plot_w = w - ml - mr
        plot_h = h - mt - mb
        if plot_w <= 0 or plot_h <= 0:
            painter.end()
            return

        # ── 背景 ──
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, QColor("#0D1117"))
        bg_grad.setColorAt(1.0, QColor("#0A0E14"))
        painter.fillRect(0, 0, w, h, bg_grad)

        # ── 八度粗网格 (C1-C7) ──
        # C4 = middle C ≈ 261.63 Hz; C_n = C4 * 2^(n-4)
        C4_HZ = 261.6256
        painter.setPen(QPen(QColor("#1A2230"), 0.8))
        for octave in [1, 2, 3, 4, 5, 6, 7]:
            hz = C4_HZ * (2 ** (octave - 4))
            y = self._freq_to_y_scaled(hz, plot_h, mt)
            if mt <= y <= mt + plot_h:
                painter.drawLine(ml, int(y), ml + plot_w, int(y))

        # ── G 音参考线 (G1-G6, 更暗淡) ──
        # G4 ≈ 392.0 Hz; G_n = G4 * 2^(n-4)
        G4_HZ = 392.0
        painter.setPen(QPen(QColor("#111820"), 0.4))
        for octave in [1, 2, 3, 4, 5, 6]:
            hz_g = G4_HZ * (2 ** (octave - 4))
            y_g = self._freq_to_y_scaled(hz_g, plot_h, mt)
            if mt <= y_g <= mt + plot_h:
                painter.drawLine(ml, int(y_g), ml + plot_w, int(y_g))

        # ── 垂直时间网格 (0s 左 → 20s 右, 2秒间隔) ──
        painter.setPen(QPen(QColor("#111820"), 0.5))
        for t_sec in range(0, _DISPLAY_HISTORY_SECS + 1, 2):
            x = ml + plot_w * (t_sec / _DISPLAY_HISTORY_SECS)
            painter.drawLine(int(x), mt, int(x), mt + plot_h)

        if not self._points:
            painter.setPen(QColor("#1A2230"))
            font = painter.font()
            font.setPixelSize(14)
            painter.setFont(font)
            painter.drawText(ml, mt, plot_w, plot_h,
                             Qt.AlignmentFlag.AlignCenter, "等待音高数据...")
            painter.end()
            return

        # ── 时间窗口 ──
        now = self._points[-1][0]
        ws = max(0, now - _DISPLAY_HISTORY_SECS)

        # ── 分段绘制彩色音高曲线 ──
        # 将点按颜色分桶，每个颜色段画一条 QPainterPath
        segments: List[List[Tuple[float, float]]] = []
        current_seg = []
        current_color_band = -1
        for t, f in self._points:
            if t < ws:
                continue
            band = -1
            for bi, (lo, hi, _c) in enumerate(self._COLOR_BANDS):
                if lo <= f < hi:
                    band = bi
                    break
            if band != current_color_band and current_seg:
                segments.append(current_seg)
                current_seg = [(t, f)]
            else:
                current_seg.append((t, f))
            current_color_band = band
        if current_seg:
            segments.append(current_seg)

        for seg in segments:
            if len(seg) < 2:
                continue
            mid_f = seg[len(seg)//2][1]
            color = self._freq_to_color(mid_f)

            # 发光光晕
            glow = QColor(color)
            glow.setAlpha(55)
            glow_pen = QPen(glow, 5)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(glow_pen)

            glow_path = QPainterPath()
            for i, (t, f) in enumerate(seg):
                x = ml + plot_w * (t - ws) / _DISPLAY_HISTORY_SECS
                y = self._freq_to_y_scaled(f, plot_h, mt)
                if i == 0:
                    glow_path.moveTo(x, y)
                else:
                    glow_path.lineTo(x, y)
            painter.drawPath(glow_path)

            # 主线
            line_pen = QPen(color, 2.2)
            line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(line_pen)

            main_path = QPainterPath()
            for i, (t, f) in enumerate(seg):
                x = ml + plot_w * (t - ws) / _DISPLAY_HISTORY_SECS
                y = self._freq_to_y_scaled(f, plot_h, mt)
                if i == 0:
                    main_path.moveTo(x, y)
                else:
                    main_path.lineTo(x, y)
            painter.drawPath(main_path)

        # ── Y 轴: 八度音名标签 (C1-C7，易读间距) ──
        C4_HZ = 261.6256
        painter.setPen(QColor("#6E7681"))
        font = painter.font()
        font.setPixelSize(9)
        painter.setFont(font)
        for octave in [1, 2, 3, 4, 5, 6, 7]:
            hz = C4_HZ * (2 ** (octave - 4))
            y = self._freq_to_y_scaled(hz, plot_h, mt)
            if mt + 4 <= y <= mt + plot_h - 4:
                note = f"C{octave}"
                # 绘制标签背景条
                text_w = 28
                painter.fillRect(0, int(y) - 7, text_w, 14, QColor(13, 17, 23, 180))
                painter.drawText(3, int(y) + 4, note)

        # ── X 轴: 0s (录音开始) → 10s (当前) ──
        painter.drawText(ml, h - 3, "0s")
        painter.drawText(w - mr - 28, h - 3, f"{_DISPLAY_HISTORY_SECS}s")

        # ── 回放模式叠加层 ──
        if self._is_review_mode and self._review_data:
            data_start, data_end = self._review_data[0][0], self._review_data[-1][0]
            rev_dur = data_end - data_start
            if rev_dur <= 0:
                rev_dur = 1.0

            # T4 水平线
            if self._review_t4 > 0:
                y_t4 = self._freq_to_y_scaled(self._review_t4, plot_h, mt)
                painter.setPen(QPen(QColor(255, 213, 79, 140), 1.5, Qt.PenStyle.DashLine))
                painter.drawLine(ml, int(y_t4), ml + plot_w, int(y_t4))
                note = _hz_to_note_name(self._review_t4)
                font_l = painter.font()
                font_l.setPixelSize(10)
                font_l.setBold(True)
                painter.setFont(font_l)
                label = f"T4: {note} ({self._review_t4:.0f}Hz)"
                fm_l = QFontMetrics(font_l)
                lw = int(fm_l.horizontalAdvance(label))
                painter.fillRect(ml + 2, int(y_t4) - 16, lw + 8, 16, QColor(13, 17, 23, 210))
                painter.setPen(QColor("#FFD54F"))
                painter.drawText(ml + 6, int(y_t4) - 3, label)

            # 悬停高亮
            if self._hovered_x >= 0 and self._hovered_hz > 0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(88, 166, 255, 60))
                painter.drawEllipse(QPointF(self._hovered_x, self._hovered_y), 10, 10)
                painter.setBrush(QColor("#FFFFFF"))
                painter.drawEllipse(QPointF(self._hovered_x, self._hovered_y), 4, 4)
                note_h = _hz_to_note_name(self._hovered_hz)
                font_h = painter.font()
                font_h.setPixelSize(11)
                font_h.setBold(True)
                painter.setFont(font_h)
                hover_text = f"{note_h} ({self._hovered_hz:.0f}Hz) — 点击选取"
                fm = QFontMetrics(font_h)
                tw = int(fm.horizontalAdvance(hover_text))
                lx = int(min(self._hovered_x + 14, w - tw - 8))
                ly = max(4, int(self._hovered_y) - 30)
                painter.fillRect(lx - 4, ly - 2, tw + 12, 20, QColor(13, 17, 23, 230))
                painter.setPen(QColor("#58A6FF"))
                painter.drawText(lx, ly + 13, hover_text)

            # 底部提示
            painter.setPen(QColor("#484F58"))
            font_tip = painter.font()
            font_tip.setPixelSize(9)
            painter.setFont(font_tip)
            painter.drawText(ml, h - 2, "悬停查看　点击选取换声点")

        painter.end()


# ═══════════════════════════════════════════════════════════════
# 钢琴键盘可视化 (Phase 2 换声点检测用)
# ═══════════════════════════════════════════════════════════════

class _PianoKeyboardWidget(QWidget):
    """钢琴键盘可视化 — 高亮换声点 + 点击发声 + 右键选择换声点 + 悬停高亮 + 箭头滚屏"""

    WHITE_KEYS = [0, 2, 4, 5, 7, 9, 11]  # MIDI note % 12
    BLACK_KEYS = [1, 3, 6, 8, 10]
    KEY_WIDTH = 28       # 每白键像素宽
    KEY_HEIGHT_RATIO = 0.58  # 黑键高度比

    # 信号：用户右键选择了换声点
    passaggio_selected = pyqtSignal(float)  # 发送 Hz

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t4_hz: float = 0.0
        self._midi_min = 36   # C2 — 完整 5 个八度
        self._midi_max = 96   # C7
        self._clicked_midi: int = -1
        self._hovered_midi: int = -1
        self._click_fade_timer: Optional[QTimer] = None
        self._scroll_offset: float = 0.0
        self.setMinimumHeight(70)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)  # 启用悬停追踪
        self.setStyleSheet("background: #0D1117; border-radius: 6px;")
        # 悬停提示标签
        self._hover_label: Optional[QLabel] = None

    def _content_width(self) -> int:
        """返回完整键盘的总像素宽度"""
        n_white = sum(1 for m in range(self._midi_min, self._midi_max + 1)
                      if m % 12 in self.WHITE_KEYS)
        return n_white * self.KEY_WIDTH + 4

    def _max_scroll(self) -> float:
        """最大可滚动偏移"""
        return max(0.0, self._content_width() - self.width())

    def scroll_by(self, delta: float) -> None:
        """按 delta 像素滚动键盘 (正=右移, 负=左移)"""
        self._scroll_offset = max(0.0, min(self._max_scroll(),
                                           self._scroll_offset + delta))
        self.update()

    def scroll_to_t4(self) -> None:
        """滚动使 T4 键居中"""
        if self._t4_hz <= 0:
            return
        midi = int(round(_hz_to_midi(self._t4_hz)))
        n_white = 0
        t4_x = 0
        for m in range(self._midi_min, midi):
            if m % 12 in self.WHITE_KEYS:
                n_white += 1
        if midi % 12 in self.WHITE_KEYS:
            t4_x = n_white * self.KEY_WIDTH + self.KEY_WIDTH // 2
        else:
            t4_x = n_white * self.KEY_WIDTH - self.KEY_WIDTH // 4
        self._scroll_offset = min(
            self._max_scroll(),
            max(0.0, t4_x - self.width() / 2)
        )
        self.update()

    def sizeHint(self):
        return self._content_width(), 70

    def set_t4(self, hz: float) -> None:
        self._t4_hz = hz
        self.scroll_to_t4()

    def clear(self) -> None:
        self._t4_hz = 0.0
        self.update()

    # ── 点击发声 ──

    def mouseMoveEvent(self, event) -> None:
        """悬停高亮"""
        midi = self._pixel_to_midi(
            event.position().x() + self._scroll_offset,
            event.position().y()
        )
        if midi != self._hovered_midi:
            self._hovered_midi = midi
            self.update()
            # 更新悬停提示
            self._update_hover_tooltip(event.position().x(), event.position().y(), midi)

    def leaveEvent(self, event) -> None:
        """鼠标离开时清除悬停"""
        self._hovered_midi = -1
        self.update()
        self._hide_hover_tooltip()

    def _update_hover_tooltip(self, x: float, y: float, midi: int) -> None:
        """显示悬停音符提示"""
        if midi < 0:
            self._hide_hover_tooltip()
            return
        note = _hz_to_note_name(440.0 * 2 ** ((midi - 69) / 12.0))
        hz = 440.0 * 2 ** ((midi - 69) / 12.0)
        if self._hover_label is None:
            self._hover_label = QLabel(self)
            self._hover_label.setStyleSheet(
                "background: rgba(22,27,34,0.92); color: #58A6FF; font-size: 11px; "
                "font-weight: bold; padding: 3px 7px; border: 1px solid #58A6FF; border-radius: 4px;"
            )
        self._hover_label.setText(f"{note} ({hz:.0f}Hz)  ◄ 右键选择")
        self._hover_label.adjustSize()
        lx = int(x + 14)
        ly = int(y - self._hover_label.height() - 8)
        lx = min(lx, self.width() - self._hover_label.width() - 4)
        ly = max(ly, 2)
        self._hover_label.move(lx, ly)
        self._hover_label.show()

    def _hide_hover_tooltip(self) -> None:
        if self._hover_label is not None:
            self._hover_label.hide()

    def mousePressEvent(self, event) -> None:
        # 将屏幕坐标转内容坐标后查找琴键
        midi = self._pixel_to_midi(
            event.position().x() + self._scroll_offset,
            event.position().y()
        )
        if midi < 0:
            return

        if event.button() == Qt.MouseButton.RightButton:
            # 右键 → 选择为换声点
            hz = 440.0 * 2 ** ((midi - 69) / 12.0)
            note = _hz_to_note_name(hz)
            reply = QMessageBox.question(
                self, "选择换声点",
                f"是否将换声点设置为 {note} ({hz:.0f} Hz)？\n\n"
                f"当前换声点: {_hz_to_note_name(self._t4_hz) if self._t4_hz > 0 else '未设置'}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.set_t4(hz)
                self.passaggio_selected.emit(hz)
                self._clicked_midi = midi
                self.update()
                if self._click_fade_timer:
                    self._click_fade_timer.stop()
                self._click_fade_timer = QTimer(self)
                self._click_fade_timer.setSingleShot(True)
                self._click_fade_timer.timeout.connect(self._clear_click_highlight)
                self._click_fade_timer.start(600)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self._play_tone(midi)
            self._clicked_midi = midi
            self.update()
            if self._click_fade_timer:
                self._click_fade_timer.stop()
            self._click_fade_timer = QTimer(self)
            self._click_fade_timer.setSingleShot(True)
            self._click_fade_timer.timeout.connect(self._clear_click_highlight)
            self._click_fade_timer.start(300)

    def wheelEvent(self, event) -> None:
        """鼠标滚轮水平滚动"""
        delta = event.angleDelta().y() // 8  # 每格 15°, 转成像素步长
        new_offset = self._scroll_offset - delta
        self._scroll_offset = max(0.0, min(self._max_scroll(), new_offset))
        self.update()

    def _clear_click_highlight(self) -> None:
        self._clicked_midi = -1
        self.update()

    def _pixel_to_midi(self, px: float, py: float) -> int:
        """将像素坐标映射为 MIDI 音符编号 (px 应为内容坐标 = 屏幕坐标 + scroll_offset)"""
        _, h = self.width(), self.height()
        key_h = h - 4
        black_h = key_h * self.KEY_HEIGHT_RATIO
        white_w = self.KEY_WIDTH
        black_w = white_w * 0.58

        # 建立白键 x 坐标映射 (内容坐标)
        white_idx = 0
        white_x_map = {}
        for midi in range(self._midi_min, self._midi_max + 1):
            if midi % 12 in self.WHITE_KEYS:
                white_x_map[midi] = white_idx * white_w + 2
                white_idx += 1

        # 先检查黑键 (z-order 在上面)
        if py <= black_h:
            for midi in range(self._midi_min, self._midi_max + 1):
                if midi % 12 in self.BLACK_KEYS:
                    prev_white = midi - 1
                    if prev_white in white_x_map:
                        wx = white_x_map[prev_white]
                        bx = wx + white_w - black_w / 2 - 2
                        if bx <= px <= bx + black_w:
                            return midi

        # 再检查白键
        for midi, wx in white_x_map.items():
            if wx <= px <= wx + white_w - 3:
                return midi

        return -1

    @staticmethod
    def _play_tone(midi: int) -> None:
        """播放对应 MIDI 音符的钢琴音色"""
        if not HAS_SOUNDDEVICE:
            return
        freq = 440.0 * 2 ** ((midi - 69) / 12.0)
        sr = 44100
        duration = 1.5  # 更长以模拟钢琴自然衰减
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        # 钢琴泛音列: 基频 + 8 个泛音，振幅按 1/n^0.85 衰减
        # 高泛音略有非谐和性 (inharmonicity) 使音色更真实
        tone = np.zeros_like(t)
        for k in range(1, 10):
            partial_freq = freq * k * (1.0 + 0.00008 * k * k)
            amp = 1.0 / (k ** 0.88)
            tone += np.sin(2 * np.pi * partial_freq * t) * amp

        # 钢琴包络: 极快起音 → 快速衰减 → 低电平延持 → 自然释放
        attack = int(sr * 0.003)        # 3ms 锤击起音
        decay = int(sr * 0.06)          # 60ms 初始衰减
        sustain_level = 0.18            # 低调延持
        sustain_len = int(sr * 0.80)
        rel_len = int(sr * 0.35)
        remaining = len(t) - attack - decay - sustain_len - rel_len
        if remaining > 0:
            sustain_len += remaining

        env = np.concatenate([
            np.linspace(0, 1.0, attack),
            np.linspace(1.0, sustain_level, decay),
            np.ones(sustain_len) * sustain_level,
            np.linspace(sustain_level, 0, rel_len),
        ])
        if len(env) > len(t):
            env = env[:len(t)]

        # 极轻微的击弦噪声 (高频短脉冲)
        noise_len = int(sr * 0.004)
        noise = np.random.randn(noise_len) * 0.015
        noise_env = np.linspace(1.0, 0, noise_len)
        tone[:noise_len] += noise * noise_env

        tone = tone * env
        tone = tone / np.max(np.abs(tone)) * 0.28

        try:
            sd.play(tone.astype(np.float32), sr)
        except Exception:
            pass

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        offset = self._scroll_offset

        white_w = self.KEY_WIDTH
        key_h = h - 4
        black_w = white_w * 0.6
        black_h = key_h * self.KEY_HEIGHT_RATIO

        t4_midi = int(round(_hz_to_midi(self._t4_hz))) if self._t4_hz > 0 else -1
        click_midi = self._clicked_midi

        # ── 白键 (以固定 KEY_WIDTH 绘制，应用 scroll offset) ──
        white_idx = 0
        white_positions = {}
        for midi in range(self._midi_min, self._midi_max + 1):
            if midi % 12 not in self.WHITE_KEYS:
                continue

            # 内容坐标
            content_x = white_idx * white_w + 2
            # 屏幕坐标
            screen_x = content_x - offset
            screen_w = white_w - 3

            # 裁剪: 完全不在视口内的跳过
            if screen_x + screen_w < -2 or screen_x > w + 2:
                white_idx += 1
                continue

            note_name = _NOTE_NAMES[midi % 12]
            is_t4 = (midi == t4_midi)

            if is_t4:
                gradient = QLinearGradient(0, 0, 0, key_h)
                gradient.setColorAt(0.0, QColor("#FFD54F"))
                gradient.setColorAt(0.6, QColor("#FFA000"))
                gradient.setColorAt(1.0, QColor("#E65100"))
                painter.fillRect(int(screen_x), 0, int(screen_w), int(key_h), QBrush(gradient))
            else:
                painter.fillRect(int(screen_x), 0, int(screen_w), int(key_h), QColor("#E8EAED"))

            painter.setPen(QColor("#CCCCCC"))
            painter.drawRect(int(screen_x), 0, int(screen_w), int(key_h))

            # C 键标注八度
            if note_name == "C":
                octave = (midi // 12) - 1
                painter.setPen(QColor("#999999"))
                font = painter.font()
                font.setPixelSize(9)
                painter.setFont(font)
                painter.drawText(int(screen_x) + 3, int(key_h) - 5, f"C{octave}")

            white_positions[midi] = (content_x, screen_x, screen_w)
            white_idx += 1

        # ── 黑键 ──
        for midi in range(self._midi_min, self._midi_max + 1):
            if midi % 12 not in self.BLACK_KEYS:
                continue
            prev_white = midi - 1
            if prev_white % 12 not in self.WHITE_KEYS:
                continue
            if prev_white not in white_positions:
                continue

            content_px, _, pw = white_positions[prev_white]
            content_bx = content_px + white_w - black_w / 2 - 2
            screen_bx = content_bx - offset

            if screen_bx + black_w < -2 or screen_bx > w + 2:
                continue

            is_t4 = (midi == t4_midi)

            if is_t4:
                painter.fillRect(int(screen_bx), 0, int(black_w), int(black_h), QColor("#FF6D00"))
            else:
                painter.fillRect(int(screen_bx), 0, int(black_w), int(black_h), QColor("#2D2D2D"))

            painter.setPen(QColor("#555555"))
            painter.drawRect(int(screen_bx), 0, int(black_w), int(black_h))

        # ── 悬停高亮 ──
        hover_midi = self._hovered_midi
        if hover_midi >= 0 and hover_midi != t4_midi:
            if hover_midi % 12 in self.WHITE_KEYS and hover_midi in white_positions:
                _, hsx, hsw = white_positions[hover_midi]
                painter.fillRect(int(hsx), 0, int(hsw), int(key_h), QColor(88, 166, 255, 60))
            elif hover_midi % 12 in self.BLACK_KEYS:
                prev_white = hover_midi - 1
                if prev_white in white_positions:
                    content_px, _, pw = white_positions[prev_white]
                    content_bx = content_px + white_w - black_w / 2 - 2
                    screen_bx = content_bx - offset
                    painter.fillRect(int(screen_bx), 0, int(black_w), int(black_h), QColor(88, 166, 255, 80))

        # ── 点击高亮 ──
        if click_midi >= 0:
            if click_midi % 12 in self.WHITE_KEYS and click_midi in white_positions:
                _, sx, sw = white_positions[click_midi]
                painter.fillRect(int(sx), 0, int(sw), int(key_h), QColor(88, 166, 255, 120))
            elif click_midi % 12 in self.BLACK_KEYS:
                prev_white = click_midi - 1
                if prev_white in white_positions:
                    content_px, _, pw = white_positions[prev_white]
                    content_bx = content_px + white_w - black_w / 2 - 2
                    screen_bx = content_bx - offset
                    painter.fillRect(int(screen_bx), 0, int(black_w), int(black_h), QColor(88, 166, 255, 160))

        # ── T4 标注 (始终在视口中央底部) ──
        if self._t4_hz > 0 and t4_midi >= 0:
            # 找到 T4 键的屏幕位置标注
            t4_note = _hz_to_note_name(self._t4_hz)
            if t4_midi in white_positions:
                _, sx, sw = white_positions[t4_midi]
                label_x = int(sx + sw / 2)
            else:
                label_x = w // 2
            painter.setPen(QColor("#FFD54F"))
            font = painter.font()
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            label = f"▲ T4: {t4_note} ({self._t4_hz:.0f}Hz)"
            fm = QFontMetrics(font)
            text_w = fm.horizontalAdvance(label)
            painter.drawText(max(4, min(w - text_w - 4, label_x - text_w // 2)), int(key_h) + 16, label)

        painter.end()


# ═══════════════════════════════════════════════════════════════
# 声部分数横向条形图 (P0 可视化)
# ═══════════════════════════════════════════════════════════════

# 各声部显示色
_VOICE_TYPE_BAR_COLORS = {
    "bass":          QColor("#8B5CF6"),   # 紫色
    "baritone":      QColor("#3B82F6"),   # 蓝色
    "tenor":         QColor("#06B6D4"),   # 青色
    "contralto":     QColor("#F59E0B"),   # 琥珀
    "mezzo_soprano": QColor("#EF4444"),   # 红色
    "soprano":       QColor("#EC4899"),   # 粉色
}


class _ScoreBarChart(QWidget):
    """横向条形图 — 显示各声部评分对比

    set_scores([(name, score, is_best), ...])
    - score: 0.0-1.0
    - is_best: 最高分的声部高亮
    """

    BAR_HEIGHT = 22
    BAR_GAP = 6
    LEFT_MARGIN = 80
    RIGHT_MARGIN = 50

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scores: list = []
        self.setMinimumHeight(140)
        self.setStyleSheet("background: #0D1117; border: 1px solid #21262D; border-radius: 8px;")

    def set_scores(self, scores: list) -> None:
        """scores: [(voice_type_key, score_0_1, is_best), ...]"""
        self._scores = scores
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        bar_area_w = w - self.LEFT_MARGIN - self.RIGHT_MARGIN
        max_bars = max(len(self._scores), 1)
        total_h = max_bars * (self.BAR_HEIGHT + self.BAR_GAP)
        start_y = max(8, (h - total_h) // 2)

        # 标题
        painter.setPen(QColor("#8B949E"))
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.LEFT_MARGIN, start_y - 16, "📈 声部分数")

        font.setPixelSize(10)
        font.setBold(False)
        painter.setFont(font)

        for i, (vt_key, score, is_best) in enumerate(self._scores):
            y = start_y + i * (self.BAR_HEIGHT + self.BAR_GAP)

            # 标签
            display = _VOICE_TYPE_SHORT.get(vt_key, vt_key)
            painter.setPen(QColor("#C9D1D9" if is_best else "#8B949E"))
            painter.drawText(0, y, self.LEFT_MARGIN - 6, self.BAR_HEIGHT,
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, display)

            bar_w = int(bar_area_w * max(0.02, min(1.0, score)))

            # 条形渐变
            base_color = _VOICE_TYPE_BAR_COLORS.get(vt_key, QColor("#6E7681"))
            grad = QLinearGradient(self.LEFT_MARGIN, 0, self.LEFT_MARGIN + bar_area_w, 0)
            if is_best:
                grad.setColorAt(0.0, base_color.lighter(130))
                grad.setColorAt(1.0, base_color)
            else:
                dim = QColor(base_color)
                dim.setAlpha(120)
                grad.setColorAt(0.0, dim.lighter(110))
                grad.setColorAt(1.0, dim)

            painter.fillRect(self.LEFT_MARGIN, y, bar_w, self.BAR_HEIGHT, QBrush(grad))

            # 分数文本
            pct_text = f"{score:.0%}"
            painter.setPen(QColor("#FFFFFF" if is_best else "#8B949E"))
            text_x = self.LEFT_MARGIN + bar_w + 4
            if text_x + 36 > w - self.RIGHT_MARGIN:
                text_x = self.LEFT_MARGIN + bar_w - 38
            painter.drawText(int(text_x), y, 40, self.BAR_HEIGHT,
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, pct_text)

            # 最优标记
            if is_best:
                star_x = self.LEFT_MARGIN - 16
                painter.setPen(QColor("#F0C000"))
                painter.drawText(int(star_x), y, 16, self.BAR_HEIGHT,
                                 Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter, "★")

        painter.end()


# ═══════════════════════════════════════════════════════════════
# 雷达图 (P0 可视化)
# ═══════════════════════════════════════════════════════════════

class _RadarChart(QWidget):
    """6 维声乐画像雷达图 (蜘蛛网图)

    维度:
      - 音域范围 (Range Span)
      - 换声点确定度 (Passaggio Confidence)
      - 音色亮度 (Timbre Brightness)
      - 音色质量 (Timbre Quality)
      - 音准稳定性 (Pitch Stability)
      - 动态范围 (Dynamic Range)
    """

    DIMENSIONS = [
        ("音域", "range"),
        ("换声点\n确定度", "passaggio"),
        ("音色\n亮度", "brightness"),
        ("音色\n质量", "quality"),
        ("音准\n稳定性", "stability"),
        ("动态\n范围", "dynamics"),
    ]

    # 外圈颜色
    AXIS_COLORS = [
        QColor("#3B82F6"),   # 蓝 — 音域
        QColor("#8B5CF6"),   # 紫 — 换声点
        QColor("#F59E0B"),   # 琥珀 — 亮度
        QColor("#EF4444"),   # 红 — 质量
        QColor("#06B6D4"),   # 青 — 稳定性
        QColor("#10B981"),   # 绿 — 动态
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._values: dict = {}
        self.setMinimumSize(240, 240)
        self.setStyleSheet("background: #0D1117; border: 1px solid #21262D; border-radius: 8px;")

    def set_values(self, values: dict) -> None:
        """values: {"range": 0.7, "passaggio": 0.85, ...} — 每维度 0-1"""
        self._values = values
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2 + 6
        r = min(cx, cy) - 22
        n = len(self.DIMENSIONS)

        if r < 30:
            painter.end()
            return

        # ── 背景网格 (3 层同心多边形: 0.33, 0.66, 1.0) ──
        for level in [0.33, 0.66, 1.0]:
            lr = r * level
            path = QPainterPath()
            for i in range(n):
                angle = -math.pi / 2 + 2 * math.pi * i / n
                x = cx + lr * math.cos(angle)
                y = cy + lr * math.sin(angle)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            path.closeSubpath()
            painter.setPen(QPen(QColor("#21262D"), 0.8 if level < 0.99 else 1.2))
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.drawPath(path)

        # ── 轴线 + 标签 ──
        for i, (label_text, key) in enumerate(self.DIMENSIONS):
            angle = -math.pi / 2 + 2 * math.pi * i / n
            ex = cx + r * math.cos(angle)
            ey = cy + r * math.sin(angle)

            axis_color = self.AXIS_COLORS[i]
            axis_color_dim = QColor(axis_color)
            axis_color_dim.setAlpha(60)
            painter.setPen(QPen(axis_color_dim, 0.7))
            painter.drawLine(int(cx), int(cy), int(ex), int(ey))

            # 标签
            label_angle = angle
            lx = cx + (r + 18) * math.cos(label_angle)
            ly = cy + (r + 18) * math.sin(label_angle)

            painter.setPen(axis_color)
            font = painter.font()
            font.setPixelSize(9)
            font.setBold(True)
            painter.setFont(font)

            # 多行标签处理
            text_lines = label_text.split('\n')
            for li, line in enumerate(text_lines):
                fm = QFontMetrics(font)
                tw = fm.horizontalAdvance(line)
                th = fm.height()
                offset_y = (li - (len(text_lines) - 1) / 2) * th
                painter.drawText(
                    int(lx - tw / 2), int(ly + offset_y - th / 2),
                    int(tw), int(th),
                    Qt.AlignmentFlag.AlignCenter, line
                )

        # ── 数据多边形 ──
        if self._values:
            data_path = QPainterPath()
            points = []
            for i, (label_text, key) in enumerate(self.DIMENSIONS):
                val = self._values.get(key, 0.0)
                val = max(0.0, min(1.0, val))
                angle = -math.pi / 2 + 2 * math.pi * i / n
                x = cx + r * val * math.cos(angle)
                y = cy + r * val * math.sin(angle)
                points.append((x, y))

            # 填充
            fill_path = QPainterPath()
            for i, (x, y) in enumerate(points):
                if i == 0:
                    fill_path.moveTo(x, y)
                else:
                    fill_path.lineTo(x, y)
            fill_path.closeSubpath()

            fill_color = QColor("#1F6FEB")
            fill_color.setAlpha(55)
            painter.setBrush(QBrush(fill_color))
            painter.setPen(QPen(QColor("#58A6FF"), 2.0))
            painter.drawPath(fill_path)

            # 顶点小圆点
            for x, y in points:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#58A6FF"))
                painter.drawEllipse(QPointF(x, y), 3.5, 3.5)

        # ── 标题 ──
        painter.setPen(QColor("#8B949E"))
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(0, 10, w, 18, Qt.AlignmentFlag.AlignCenter, "🎯 声乐画像")

        painter.end()


# ═══════════════════════════════════════════════════════════════
# 频谱缩略图 (P0 可视化)
# ═══════════════════════════════════════════════════════════════

class _SpectrumThumbnail(QWidget):
    """歌手共振峰区域频谱图 — 显示 FHE 和谱能量分布

    展示 2-4 kHz 频谱 (singer's formant 关键区域)，
    标注 FHE (半能量频率) 位置。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._spec_data: Optional[np.ndarray] = None
        self._freq_axis: Optional[np.ndarray] = None
        self._fhe_hz: float = 0.0
        self._band_low: int = 2000
        self._band_high: int = 3600
        self.setMinimumHeight(130)
        self.setStyleSheet("background: #0D1117; border: 1px solid #21262D; border-radius: 8px;")

    def set_spectrum(self, audio: Optional[np.ndarray], fhe_hz: float,
                     band_low: int = 2000, band_high: int = 3600) -> None:
        """设置音频数据并计算频谱"""
        self._fhe_hz = fhe_hz
        self._band_low = band_low
        self._band_high = band_high

        if audio is None or len(audio) < 1024:
            self._spec_data = None
            self._freq_axis = None
            self.update()
            return

        n = len(audio)
        spec = np.abs(np.fft.rfft(audio * np.hanning(n)))
        freq = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)

        # 聚焦频段
        mask = (freq >= band_low) & (freq <= band_high)
        self._spec_data = spec[mask]
        self._freq_axis = freq[mask]
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        ml, mr, mt, mb = 40, 12, 22, 22
        plot_w = w - ml - mr
        plot_h = h - mt - mb

        # 标题
        painter.setPen(QColor("#8B949E"))
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(ml, mt - 4, plot_w, 16, Qt.AlignmentFlag.AlignLeft, "🔊 频谱分析 (歌手共振峰区域)")

        if self._spec_data is None or self._freq_axis is None or len(self._spec_data) < 2:
            painter.setPen(QColor("#484F58"))
            font.setPixelSize(12)
            font.setBold(False)
            painter.setFont(font)
            painter.drawText(ml, mt, plot_w, plot_h,
                             Qt.AlignmentFlag.AlignCenter, "无频谱数据 (需要完成 Phase 3 元音录音)")
            painter.end()
            return

        if plot_w <= 0 or plot_h <= 0:
            painter.end()
            return

        spec = self._spec_data
        freq = self._freq_axis
        band_low, band_high = self._band_low, self._band_high

        # 归一化
        smax = float(np.max(spec))
        if smax < 1e-10:
            painter.end()
            return
        spec_norm = spec / smax

        # ── 填充区域 ──
        fill_path = QPainterPath()
        fill_path.moveTo(ml, mt + plot_h)
        for i in range(len(spec_norm)):
            x = ml + plot_w * (freq[i] - band_low) / (band_high - band_low)
            y = mt + plot_h * (1.0 - spec_norm[i])
            fill_path.lineTo(x, y)
        fill_path.lineTo(ml + plot_w, mt + plot_h)
        fill_path.closeSubpath()

        fill_grad = QLinearGradient(0, mt, 0, mt + plot_h)
        fill_grad.setColorAt(0.0, QColor("#58A6FF"))
        fill_grad.setColorAt(1.0, QColor("#1F6FEB"))
        fill_color = QColor("#58A6FF")
        fill_color.setAlpha(70)
        painter.setBrush(QBrush(fill_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(fill_path)

        # ── 频谱曲线 ──
        curve_path = QPainterPath()
        for i in range(len(spec_norm)):
            x = ml + plot_w * (freq[i] - band_low) / (band_high - band_low)
            y = mt + plot_h * (1.0 - spec_norm[i])
            if i == 0:
                curve_path.moveTo(x, y)
            else:
                curve_path.lineTo(x, y)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#58A6FF"), 1.2))
        painter.drawPath(curve_path)

        # ── FHE 标记线 ──
        if self._fhe_hz > 0 and band_low <= self._fhe_hz <= band_high:
            fhe_x = ml + plot_w * (self._fhe_hz - band_low) / (band_high - band_low)
            # 虚线
            dash_pen = QPen(QColor("#FFD54F"), 1.2)
            dash_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(dash_pen)
            painter.drawLine(int(fhe_x), mt, int(fhe_x), mt + plot_h)

            # 标注
            painter.setPen(QColor("#FFD54F"))
            font = painter.font()
            font.setPixelSize(9)
            font.setBold(True)
            painter.setFont(font)
            label = f"FHE {self._fhe_hz:.0f} Hz"
            fm = QFontMetrics(font)
            lw = fm.horizontalAdvance(label)
            label_x = int(fhe_x + 4)
            if label_x + lw > ml + plot_w:
                label_x = int(fhe_x - lw - 4)
            painter.drawText(label_x, mt + 12, label)

        # ── X 轴 ──
        painter.setPen(QColor("#6E7681"))
        font = painter.font()
        font.setPixelSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.drawLine(ml, mt + plot_h, ml + plot_w, mt + plot_h)
        # 标签
        painter.drawText(ml, mt + plot_h + 12, f"{band_low} Hz")
        mid_label = f"{(band_low + band_high) // 2} Hz"
        fm = QFontMetrics(font)
        painter.drawText(ml + plot_w // 2 - fm.horizontalAdvance(mid_label) // 2,
                         mt + plot_h + 12, mid_label)
        hi_label = f"{band_high} Hz"
        painter.drawText(ml + plot_w - fm.horizontalAdvance(hi_label),
                         mt + plot_h + 12, hi_label)

        # ── Y 轴标签 ──
        painter.setPen(QColor("#6E7681"))
        painter.drawText(2, mt, 36, 14, Qt.AlignmentFlag.AlignRight, "峰")
        painter.drawText(2, mt + plot_h - 14, 36, 14, Qt.AlignmentFlag.AlignRight, "0")

        painter.end()
