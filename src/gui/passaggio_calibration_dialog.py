"""换声点手动校准对话框 —— PassaggioCalibrationDialog

三阶段校准流程:
  Phase 1 - 引导: 说明演唱方法（滑音/半音阶），准备开始
  Phase 2 - 检测: 实时录音 + 多特征融合检测换声点
  Phase 3 - 校验: 可视化结果 + 手动微调 + 试听回放 + 保存

换声点检测基于多特征融合:
  - 频谱倾斜突变 (35%): 胸声→头声时 spectral_tilt 急剧下降
  - 音高断连检测 (25%): 未训练歌手在换声点出现"破音"式跳跃
  - HNR 骤降 (20%): 声带闭合模式变化导致谐波噪声比下降
  - 振幅骤降 (10%): 换声点不自觉弱唱
  - 声部先验 (10%): 根据声部缩小搜索窗口
"""

from __future__ import annotations

import math
import time
import os
import tempfile
from typing import List, Optional, Tuple, Deque
from collections import deque

import numpy as np

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QPointF
from PyQt6.QtGui import (
    QFont, QPainter, QColor, QPen, QLinearGradient, QBrush, QPainterPath, QFontMetrics,
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QFrame, QStackedWidget, QSlider, QMessageBox,
    QRadioButton, QButtonGroup, QSizePolicy, QScrollArea,
)

# ── 可选音频依赖 ──────────────────────────────────────────────
try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

from src.profiles.profile_model import SingerProfile, PassaggioData
from src.profiles.profile_manager import ProfileManager


# ── 常量 ──────────────────────────────────────────────────────

SAMPLE_RATE = 44100
FRAME_SIZE = 4096          # ~93ms per frame
HOP_SIZE = 2048            # 50% overlap, ~46ms hop
MAX_RECORD_SECONDS = 20    # 最大录音时长
DISPLAY_HISTORY_SECS = 8   # 实时显示保留最近 N 秒

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# 各声部典型第二换声点 (secondo passaggio) 频率 (Hz)
# 来源: Richard Miller 声乐教学文献
_VOICE_TYPE_PASSAGGIO_HZ = {
    "bass": 294.0,           # D4
    "baritone": 330.0,       # E4
    "tenor": 392.0,          # G4
    "contralto": 587.0,      # D5
    "mezzo_soprano": 659.0,  # E5
    "soprano": 740.0,        # F#5
}

# 声部显示名映射
_VOICE_TYPE_DISPLAY = {
    "tenor": "男高音", "baritone": "男中音", "bass": "男低音",
    "soprano": "女高音", "mezzo_soprano": "女中音", "contralto": "女低音",
}


def _hz_to_note_name(hz: float) -> str:
    """频率 → 音名+八度 (如 440.0 → 'A4')"""
    if hz <= 0:
        return "—"
    midi = 69 + 12 * math.log2(hz / 440.0)
    note_idx = int(round(midi)) % 12
    octave = int(round(midi)) // 12 - 1
    return f"{_NOTE_NAMES[note_idx]}{octave}"


def _hz_to_midi(hz: float) -> float:
    """频率 → MIDI 音符编号"""
    if hz <= 0:
        return 0.0
    return 69 + 12 * math.log2(hz / 440.0)


def _midi_to_hz(midi: float) -> float:
    """MIDI 音符编号 → 频率"""
    return 440.0 * (2 ** ((midi - 69) / 12))


# ── 主对话框 ──────────────────────────────────────────────────

class PassaggioCalibrationDialog(QDialog):
    """换声点手动校准对话框

    三阶段流程:
      0. GUIDE    — 引导说明 + 模式选择
      1. DETECT   — 实时录音 + 特征追踪 + 自动检测
      2. VALIDATE — 结果展示 + 手动微调 + 试听 + 保存

    用法:
      dlg = PassaggioCalibrationDialog(profile, profile_manager, parent)
      if dlg.exec() == QDialog.DialogCode.Accepted:
          # profile.passaggio 已被更新并保存
          ...
    """

    PHASE_GUIDE = 0
    PHASE_DETECT = 1
    PHASE_VALIDATE = 2

    calibration_saved = pyqtSignal(str)  # 发射 profile.id

    def __init__(
        self,
        profile: SingerProfile,
        profile_manager: ProfileManager,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._profile = profile
        self._mgr = profile_manager
        self._phase = self.PHASE_GUIDE

        # 校准参数
        self._mode = "glissando"  # "glissando" | "chromatic"

        # 录音数据
        self._recorded_audio: List[np.ndarray] = []       # 音频块列表
        self._pitch_track: List[Tuple[float, float]] = []  # [(time_sec, freq_hz), ...]
        self._feature_track: List[Tuple[float, float, float, float, float, float]] = []  # [(time, tilt, hnr, rms, l1l2, h2h3), ...]
        self._current_freq: float = 0.0
        self._current_tilt: float = 0.0
        self._current_hnr: float = 0.0
        self._current_rms: float = 0.0
        self._current_l1l2: float = 0.0
        self._current_h2h3: float = 1.0

        # 检测结果
        self._detected_t4: float = 0.0       # 检测到的换声点频率
        self._detection_confidence: float = 0.0
        self._adjusted_t4: float = 0.0       # 用户微调后的值
        self._feature_scores: List[Tuple[float, float, float]] = []  # [(time, freq, score), ...]
        self._candidates: List[dict] = []    # 自动检测候选人 [{freq, fusion_score, tilt, pitch_jump, hnr, rms, prior}, ...]
        self._manual_candidates: List[dict] = []  # 用户手动选取的候选点 [{freq, time, note, source: 'manual'}, ...]

        # 原始特征分数 (用于诊断)
        self._raw_tilt_score = np.array([])
        self._raw_pitch_score = np.array([])
        self._raw_hnr_score = np.array([])
        self._raw_rms_score = np.array([])
        self._raw_l1l2_score = np.array([])
        self._raw_h2h3_score = np.array([])
        self._raw_prior_score = np.array([])

        # 录音状态
        self._is_recording = False
        self._record_start_time: float = 0.0
        self._audio_stream: Optional[sd.InputStream] = None
        self._display_timer: Optional[QTimer] = None
        self._display_counter: int = 0

        # 临时音频文件(回放用)
        self._temp_audio_file: Optional[str] = None
        self._full_audio: Optional[np.ndarray] = None

        # ── UI 初始化 ──
        self.setWindowTitle("🔄 换声点校准")
        self.setMinimumSize(600, 680)
        self.setModal(True)
        self.setStyleSheet("PassaggioCalibrationDialog { background-color: #0D1117; }")

        self._build_ui()
        self._switch_phase(self.PHASE_GUIDE)

        # 如果没有音频设备，提前显示警告
        if not HAS_SOUNDDEVICE:
            self._show_error("sounddevice 未安装，无法进行音频录制。\n请运行: pip install sounddevice")

    # ═══════════════════════════════════════════════════════════
    # UI 框架
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        """主布局: 顶部进度条 + StackedWidget(三页) + 底部导航"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # ── 顶部: 进度指示器 ──
        main_layout.addWidget(self._build_progress_indicator())

        # ── 中间: 三阶段页面 ──
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._stack.addWidget(self._build_guide_page())    # index 0
        self._stack.addWidget(self._build_detect_page())   # index 1
        self._stack.addWidget(self._build_validate_page()) # index 2
        main_layout.addWidget(self._stack, 1)

        # ── 底部: 导航按钮 ──
        main_layout.addWidget(self._build_nav_buttons())

    def _build_progress_indicator(self) -> QWidget:
        """三阶段进度条"""
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        steps = [
            ("📖", "引导"),
            ("🎤", "录音检测"),
            ("✅", "校验确认"),
        ]

        self._progress_frames: List[QFrame] = []
        self._progress_labels: List[QLabel] = []
        self._progress_icons: List[QLabel] = []

        for i, (icon, label) in enumerate(steps):
            # 步骤容器
            step = QFrame()
            step.setStyleSheet("background: transparent;")
            step_layout = QVBoxLayout(step)
            step_layout.setContentsMargins(0, 0, 0, 0)
            step_layout.setSpacing(4)
            step_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            icon_lbl = QLabel(icon)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet("font-size: 18px; background: transparent; color: #484F58;")
            step_layout.addWidget(icon_lbl)

            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 10px; color: #484F58; background: transparent;")
            step_layout.addWidget(lbl)

            self._progress_icons.append(icon_lbl)
            self._progress_labels.append(lbl)

            layout.addWidget(step)

            # 步骤间连线
            if i < len(steps) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFixedHeight(2)
                line.setMinimumWidth(40)
                line.setStyleSheet("QFrame { background-color: #21262D; border: none; }")
                layout.addWidget(line, 1, Qt.AlignmentFlag.AlignVCenter)

            self._progress_frames.append(step)

        return widget

    def _update_progress(self) -> None:
        """更新进度条高亮"""
        for i in range(3):
            active = i <= self._phase
            color = "#58A6FF" if active else "#484F58"
            weight = "bold" if i == self._phase else "normal"
            self._progress_icons[i].setStyleSheet(
                f"font-size: 18px; background: transparent; color: {color};"
            )
            self._progress_labels[i].setStyleSheet(
                f"font-size: 10px; color: {color}; font-weight: {weight}; background: transparent;"
            )

    def _build_nav_buttons(self) -> QWidget:
        """底部导航按钮"""
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 返回按钮
        self._back_btn = QPushButton("← 返回")
        self._back_btn.setMinimumHeight(38)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8B949E;
                padding: 8px 18px; border-radius: 8px;
                font-size: 12px; border: 1px solid #30363D;
            }
            QPushButton:hover { background: #21262D; color: #C9D1D9; }
        """)
        self._back_btn.clicked.connect(self._on_back)

        layout.addWidget(self._back_btn)
        layout.addStretch()

        # 下一步 / 确认按钮
        self._next_btn = QPushButton("开始校准 →")
        self._next_btn.setMinimumHeight(38)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #58A6FF, stop:1 #3FB950);
                color: #FFFFFF; font-weight: bold;
                padding: 8px 24px; border-radius: 8px;
                font-size: 12px; border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #79B8FF, stop:1 #56D364);
            }
            QPushButton:disabled {
                background: #21262D; color: #484F58; border: 1px solid #30363D;
            }
        """)
        self._next_btn.clicked.connect(self._on_next)
        layout.addWidget(self._next_btn)

        # 关闭按钮(始终可见)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(38, 38)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8B949E;
                padding: 0; border-radius: 8px;
                font-size: 16px; border: 1px solid #30363D;
            }
            QPushButton:hover { background: #21262D; color: #F85149; border-color: #F85149; }
        """)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)

        return widget

    def _switch_phase(self, phase: int) -> None:
        """切换阶段"""
        self._phase = phase
        self._stack.setCurrentIndex(phase)
        self._update_progress()

        # 更新按钮
        if phase == self.PHASE_GUIDE:
            self._back_btn.setVisible(False)
            self._next_btn.setText("开始校准 →")
            self._next_btn.setEnabled(True)
        elif phase == self.PHASE_DETECT:
            self._back_btn.setVisible(True)
            self._next_btn.setText("⏹ 停止录音")
            self._next_btn.setEnabled(True)
            self._next_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #F85149, stop:1 #DA3633);
                    color: #FFFFFF; font-weight: bold;
                    padding: 8px 24px; border-radius: 8px;
                    font-size: 12px; border: none;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #FF6B63, stop:1 #F85149);
                }
            """)
        elif phase == self.PHASE_VALIDATE:
            self._back_btn.setVisible(True)
            self._next_btn.setText("💾 确认保存")
            self._next_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #3FB950, stop:1 #238636);
                    color: #FFFFFF; font-weight: bold;
                    padding: 8px 24px; border-radius: 8px;
                    font-size: 12px; border: none;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #56D364, stop:1 #3FB950);
                }
            """)

    # ═══════════════════════════════════════════════════════════
    # Phase 1 — 引导页
    # ═══════════════════════════════════════════════════════════

    def _build_guide_page(self) -> QWidget:
        """引导说明页"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # 标题
        title = QLabel("🔍 换声点校准引导")
        title.setStyleSheet("color: #E6EDF3; font-size: 18px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        desc = QLabel("换声点（Secondo Passaggio）是胸声向头声/混声转换的关键音高区域。\n"
                      "准确测定换声点可以帮助 AI 教练给出更精准的声部识别和技巧建议。")
        desc.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent; line-height: 1.5;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addWidget(self._section_divider())

        # ── 演唱方法说明 ──
        method_title = QLabel("🎵 演唱方法")
        method_title.setStyleSheet("color: #C9D1D9; font-size: 14px; font-weight: bold; background: transparent;")
        layout.addWidget(method_title)

        # 模式选择卡片
        mode_card = QFrame()
        mode_card.setStyleSheet("""
            QFrame {
                background: #161B22; border: 1px solid #30363D; border-radius: 10px;
            }
        """)
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setContentsMargins(16, 14, 16, 14)
        mode_layout.setSpacing(10)

        # 滑音模式
        self._glissando_radio = QRadioButton("滑音 (Glissando) — 推荐 ✨")
        self._glissando_radio.setChecked(True)
        self._glissando_radio.setCursor(Qt.CursorShape.PointingHandCursor)
        self._glissando_radio.setStyleSheet(self._radio_style())
        mode_layout.addWidget(self._glissando_radio)

        glissando_hint = QLabel(
            "  像救护车鸣笛一样，用「啊——」从低音缓慢连续滑到高音。\n"
            "  更自然、更容易暴露换声点，适合首次校准。"
        )
        glissando_hint.setStyleSheet("color: #8B949E; font-size: 11px; background: transparent; line-height: 1.4;")
        glissando_hint.setWordWrap(True)
        mode_layout.addWidget(glissando_hint)

        # 半音阶模式
        self._chromatic_radio = QRadioButton("半音阶 (Chromatic Scale)")
        self._chromatic_radio.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chromatic_radio.setStyleSheet(self._radio_style())
        mode_layout.addWidget(self._chromatic_radio)

        chromatic_hint = QLabel(
            "  半音半音逐级上升，每个音保持约 1 秒。\n"
            "  更精确，但需要一定声乐基础。唱不上去的那个音即为换声点。"
        )
        chromatic_hint.setStyleSheet("color: #8B949E; font-size: 11px; background: transparent; line-height: 1.4;")
        chromatic_hint.setWordWrap(True)
        mode_layout.addWidget(chromatic_hint)

        layout.addWidget(mode_card)

        # ── 前置准备 ──
        prep_title = QLabel("📋 准备工作")
        prep_title.setStyleSheet("color: #C9D1D9; font-size: 14px; font-weight: bold; background: transparent;")
        layout.addWidget(prep_title)

        prep_items = [
            "🔇 找一个安静的环境，减少背景噪音干扰",
            "🎤 距麦克风约 15-30cm，保持距离稳定",
            "🗣️ 选择你最舒服的元音（推荐「啊 /a/」或「哦 /o/」）",
            "🫁 用中等音量演唱，不要刻意用力或压嗓",
        ]
        for item in prep_items:
            item_lbl = QLabel(item)
            item_lbl.setStyleSheet("color: #C9D1D9; font-size: 12px; background: transparent; padding: 2px 0;")
            item_lbl.setWordWrap(True)
            layout.addWidget(item_lbl)

        layout.addStretch()

        # ── 参考信息: 典型换声点 ──
        ref_card = QFrame()
        ref_card.setStyleSheet("""
            QFrame { background: rgba(88, 166, 255, 0.06); border: 1px solid #1F2A3A; border-radius: 8px; }
        """)
        ref_layout = QVBoxLayout(ref_card)
        ref_layout.setContentsMargins(14, 10, 14, 10)
        ref_layout.setSpacing(4)

        ref_title = QLabel("📊 各声部典型换声点（仅供参考）")
        ref_title.setStyleSheet("color: #58A6FF; font-size: 11px; font-weight: bold; background: transparent;")
        ref_layout.addWidget(ref_title)

        ref_text = "男低音 D4 (294Hz)  |  男中音 E4 (330Hz)  |  男高音 G4 (392Hz)\n"
        ref_text += "女低音 D5 (587Hz)  |  女中音 E5 (659Hz)  |  女高音 F#5 (740Hz)"
        ref_lbl = QLabel(ref_text)
        ref_lbl.setStyleSheet("color: #8B949E; font-size: 11px; background: transparent; font-family: monospace;")
        ref_layout.addWidget(ref_lbl)

        # 标注当前声部
        vt = self._profile.effective_voice_type
        if vt in _VOICE_TYPE_PASSAGGIO_HZ:
            expected_hz = _VOICE_TYPE_PASSAGGIO_HZ[vt]
            vt_display = _VOICE_TYPE_DISPLAY.get(vt, vt)
            note = _hz_to_note_name(expected_hz)
            hint = QLabel(f"💡 你的声部: {vt_display} → 预期换声点在 {note} ({expected_hz:.0f} Hz) 附近")
            hint.setStyleSheet("color: #3FB950; font-size: 11px; background: transparent; padding-top: 4px;")
            ref_layout.addWidget(hint)

        layout.addWidget(ref_card)

        return page

    def _radio_style(self) -> str:
        return """
            QRadioButton {
                color: #C9D1D9; font-size: 13px; font-weight: bold;
                background: transparent; spacing: 8px;
            }
            QRadioButton::indicator {
                width: 18px; height: 18px;
                border-radius: 9px;
                border: 2px solid #30363D;
                background: #0D1117;
            }
            QRadioButton::indicator:checked {
                border-color: #58A6FF;
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                    stop:0 #58A6FF, stop:0.4 #58A6FF, stop:0.5 #0D1117, stop:1 #0D1117);
            }
            QRadioButton::indicator:hover { border-color: #58A6FF; }
        """

    # ═══════════════════════════════════════════════════════════
    # Phase 2 — 检测页
    # ═══════════════════════════════════════════════════════════

    def _build_detect_page(self) -> QWidget:
        """实时录音 + 多特征融合检测页面 (增强版可视化)"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ── 状态栏 ──
        status_row = QHBoxLayout()

        self._rec_status = QLabel("⏺ 准备录音")
        self._rec_status.setStyleSheet(
            "color: #3FB950; font-size: 13px; font-weight: bold; background: transparent;"
            "padding: 6px 12px; border: 1px solid #30363D; border-radius: 8px;"
        )
        status_row.addWidget(self._rec_status)
        status_row.addStretch()

        self._rec_timer_label = QLabel("00:00")
        self._rec_timer_label.setStyleSheet(
            "color: #E6EDF3; font-size: 20px; font-weight: bold; background: transparent;"
            "font-family: 'SF Mono', 'Cascadia Code', monospace;"
        )
        status_row.addWidget(self._rec_timer_label)

        layout.addLayout(status_row)

        # ── 增强音高画布 ──
        self._pitch_canvas = _PassaggioCanvas()
        self._pitch_canvas.setMinimumHeight(220)
        layout.addWidget(self._pitch_canvas, 3)

        # ── 多特征指标面板 ──
        indicators_card = QFrame()
        indicators_card.setStyleSheet("""
            QFrame { background: #161B22; border: 1px solid #30363D; border-radius: 8px; }
        """)
        ind_layout = QVBoxLayout(indicators_card)
        ind_layout.setContentsMargins(14, 10, 14, 10)
        ind_layout.setSpacing(6)

        # 双列布局
        cols = QHBoxLayout()
        cols.setSpacing(20)

        # 左列: 频谱特征
        left_col = QVBoxLayout()
        left_col.setSpacing(5)

        feat_lbl = QLabel("频谱特征")
        feat_lbl.setStyleSheet("color: #8B949E; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; background: transparent;")
        left_col.addWidget(feat_lbl)

        # 频谱倾斜
        self._tilt_row_data = self._build_indicator_row("频谱倾斜", "#58A6FF")
        left_col.addLayout(self._tilt_row_data)

        # L1-L2 谐波比 (新增)
        self._l1l2_row_data = self._build_indicator_row("L1-L2 谐波比", "#A78BFA")
        left_col.addLayout(self._l1l2_row_data)

        # HNR
        self._hnr_row_data = self._build_indicator_row("谐波噪声比", "#3FB950")
        left_col.addLayout(self._hnr_row_data)

        cols.addLayout(left_col)

        # 右列: 音高特征
        right_col = QVBoxLayout()
        right_col.setSpacing(5)

        pitch_feat_lbl = QLabel("音高特征")
        pitch_feat_lbl.setStyleSheet("color: #8B949E; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; background: transparent;")
        right_col.addWidget(pitch_feat_lbl)

        # H2/H3 主导度 (新增)
        self._h2h3_row_data = self._build_indicator_row("H2/H3 主导度", "#D29922")
        right_col.addLayout(self._h2h3_row_data)

        # 音高平滑度
        self._smooth_row_data = self._build_indicator_row("音高平滑度", "#F0883E")
        right_col.addLayout(self._smooth_row_data)

        # RMS 音量
        self._rms_row_data = self._build_indicator_row("音量", "#58A6FF")
        right_col.addLayout(self._rms_row_data)

        cols.addLayout(right_col)
        ind_layout.addLayout(cols)

        # 底部区域状态
        self._region_label = QLabel("等待录音...")
        self._region_label.setStyleSheet(
            "color: #8B949E; font-size: 12px; background: transparent;"
            "padding: 4px 0;"
        )
        ind_layout.addWidget(self._region_label)

        layout.addWidget(indicators_card)

        # ── 提示 ──
        hint = QLabel("💡 用滑音从低到高连续唱「啊——」，系统自动追踪频谱特征变化定位换声点")
        hint.setStyleSheet("color: #484F58; font-size: 11px; background: transparent;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        return page

    @staticmethod
    def _build_indicator_row(label: str, color_hex: str) -> QHBoxLayout:
        """构建一个指标行: 标签 + 条形图 + 数值"""
        row = QHBoxLayout()
        row.setSpacing(6)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: #8B949E; font-size: 10px; background: transparent;")
        lbl.setFixedWidth(68)
        row.addWidget(lbl)

        bar = _IndicatorBar(QColor(color_hex))
        row.addWidget(bar, 1)

        val = QLabel("—")
        val.setStyleSheet("color: #8B949E; font-size: 10px; background: transparent;")
        val.setFixedWidth(70)
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(val)

        # 存储引用到 row 的属性中以供后续更新
        row.bar = bar
        row.val_label = val
        return row

    def _update_indicator_row(self, row: QHBoxLayout, value: float, text: str, norm: float) -> None:
        """更新指标行"""
        row.bar.set_value(norm)
        row.val_label.setText(text)

    # ═══════════════════════════════════════════════════════════
    # Phase 3 — 校验页
    # ═══════════════════════════════════════════════════════════

    def _build_validate_page(self) -> QWidget:
        """校验确认页"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; }
            QScrollBar::handle:vertical { background: #30363D; border-radius: 3px; }
            QScrollBar::handle:vertical:hover { background: #484F58; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # 标题
        title = QLabel("✅ 校准结果")
        title.setStyleSheet("color: #E6EDF3; font-size: 18px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        # ── 结果卡片 ──
        result_card = QFrame()
        result_card.setStyleSheet("""
            QFrame { background: #161B22; border: 1px solid #30363D; border-radius: 10px; }
        """)
        rc_layout = QVBoxLayout(result_card)
        rc_layout.setContentsMargins(20, 16, 20, 16)
        rc_layout.setSpacing(12)

        # 检测到的换声点
        detected_row = QHBoxLayout()
        detected_label = QLabel("自动检测:")
        detected_label.setStyleSheet("color: #8B949E; font-size: 13px; background: transparent;")
        detected_row.addWidget(detected_label)
        self._detected_t4_label = QLabel("—")
        self._detected_t4_label.setStyleSheet(
            "color: #58A6FF; font-size: 18px; font-weight: bold; background: transparent;"
        )
        detected_row.addWidget(self._detected_t4_label)
        detected_row.addStretch()

        self._confidence_label = QLabel("置信度: —%")
        self._confidence_label.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
        detected_row.addWidget(self._confidence_label)
        rc_layout.addLayout(detected_row)

        # 置信度进度条
        self._conf_bar = QFrame()
        self._conf_bar.setFixedHeight(6)
        self._conf_bar.setStyleSheet("background: #21262D; border-radius: 3px;")
        rc_layout.addWidget(self._conf_bar)

        # 置信度详情说明
        self._conf_detail_label = QLabel("")
        self._conf_detail_label.setStyleSheet("color: #8B949E; font-size: 11px; background: transparent;")
        self._conf_detail_label.setWordWrap(True)
        rc_layout.addWidget(self._conf_detail_label)

        rc_layout.addWidget(self._section_divider())

        # ── 钢琴键盘可视化 ──
        piano_title = QLabel("🎹 换声点在键盘上的位置")
        piano_title.setStyleSheet("color: #C9D1D9; font-size: 12px; font-weight: bold; background: transparent;")
        rc_layout.addWidget(piano_title)

        # 钢琴 + 左右滚动按钮
        piano_container = QHBoxLayout()
        piano_container.setSpacing(4)

        self._piano_left_btn = QPushButton("◀")
        self._piano_left_btn.setFixedSize(26, 80)
        self._piano_left_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._piano_left_btn.setStyleSheet("""
            QPushButton { background: #21262D; color: #8B949E; border: 1px solid #30363D;
                border-radius: 4px; font-size: 12px; font-weight: bold; }
            QPushButton:hover { background: #30363D; color: #E6EDF3; border-color: #58A6FF; }
        """)
        self._piano_left_btn.clicked.connect(lambda: self._piano_widget.scroll_by_half(-1))
        piano_container.addWidget(self._piano_left_btn)

        self._piano_widget = _PianoKeyboardWidget()
        self._piano_widget.setMinimumHeight(80)
        self._piano_widget.passaggio_selected.connect(self._on_piano_passaggio_selected)
        piano_container.addWidget(self._piano_widget, 1)

        self._piano_right_btn = QPushButton("▶")
        self._piano_right_btn.setFixedSize(26, 80)
        self._piano_right_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._piano_right_btn.setStyleSheet("""
            QPushButton { background: #21262D; color: #8B949E; border: 1px solid #30363D;
                border-radius: 4px; font-size: 12px; font-weight: bold; }
            QPushButton:hover { background: #30363D; color: #E6EDF3; border-color: #58A6FF; }
        """)
        self._piano_right_btn.clicked.connect(lambda: self._piano_widget.scroll_by_half(1))
        piano_container.addWidget(self._piano_right_btn)

        rc_layout.addLayout(piano_container)

        rc_layout.addWidget(self._section_divider())

        # ── 手动微调滑块 ──
        adjust_title = QLabel("🔧 手动微调（如果自动检测不够准确）")
        adjust_title.setStyleSheet("color: #C9D1D9; font-size: 12px; font-weight: bold; background: transparent;")
        rc_layout.addWidget(adjust_title)

        slider_row = QHBoxLayout()
        slider_row.setSpacing(10)

        self._slider_min_label = QLabel("")
        self._slider_min_label.setStyleSheet("color: #484F58; font-size: 10px; background: transparent;")
        self._slider_min_label.setFixedWidth(60)
        self._slider_min_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        slider_row.addWidget(self._slider_min_label)

        self._adjust_slider = QSlider(Qt.Orientation.Horizontal)
        self._adjust_slider.setMinimum(0)
        self._adjust_slider.setMaximum(200)
        self._adjust_slider.setValue(100)
        self._adjust_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #21262D; height: 6px; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #58A6FF; width: 16px; height: 16px;
                margin: -6px 0; border-radius: 8px;
            }
            QSlider::handle:horizontal:hover { background: #79B8FF; }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3FB950, stop:0.4 #58A6FF, stop:1 #F85149);
                border-radius: 3px;
            }
        """)
        self._adjust_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self._adjust_slider, 1)

        self._slider_max_label = QLabel("")
        self._slider_max_label.setStyleSheet("color: #484F58; font-size: 10px; background: transparent;")
        self._slider_max_label.setFixedWidth(60)
        slider_row.addWidget(self._slider_max_label)

        rc_layout.addLayout(slider_row)

        # 当前调整值
        self._adjusted_value_label = QLabel("")
        self._adjusted_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._adjusted_value_label.setStyleSheet(
            "color: #E6EDF3; font-size: 16px; font-weight: bold; background: transparent;"
        )
        rc_layout.addWidget(self._adjusted_value_label)

        layout.addWidget(result_card)

        # ── 音高轨迹回放画布 ──
        canvas_title = QLabel("📈 录音音高轨迹（悬停查看，点击选取换声点）")
        canvas_title.setStyleSheet("color: #C9D1D9; font-size: 12px; font-weight: bold; background: transparent;")
        layout.addWidget(canvas_title)

        self._validate_canvas = _ValidatePitchCanvas()
        self._validate_canvas.setMinimumHeight(200)
        self._validate_canvas.passaggio_selected.connect(self._on_piano_passaggio_selected)
        layout.addWidget(self._validate_canvas)

        # ── 候选换声点 (自动检测 + 手动选取) ──
        self._candidates_card = QFrame()
        self._candidates_card.setStyleSheet("""
            QFrame { background: #161B22; border: 1px solid #21262D; border-radius: 8px; }
        """)
        cand_layout = QVBoxLayout(self._candidates_card)
        cand_layout.setContentsMargins(14, 10, 14, 10)
        cand_layout.setSpacing(6)

        cand_title = QLabel("📊 候选换声点")
        cand_title.setStyleSheet("color: #8B949E; font-size: 11px; font-weight: bold; background: transparent;")
        cand_layout.addWidget(cand_title)

        cand_desc = QLabel("自动检测候选 + 手动选取的候选点。点击 🔊 试听，点击「选此」设为当前换声点。")
        cand_desc.setStyleSheet("color: #484F58; font-size: 10px; background: transparent;")
        cand_desc.setWordWrap(True)
        cand_layout.addWidget(cand_desc)

        # 动态候选行容器
        self._candidates_rows_layout = QVBoxLayout()
        self._candidates_rows_layout.setSpacing(6)
        cand_layout.addLayout(self._candidates_rows_layout)

        # 存储当前行的 widget 引用以便重建时清理
        self._candidate_row_widgets: List[QWidget] = []
        self._candidate_row_data: List[dict] = []  # [{index, source, freq, ...}]

        layout.addWidget(self._candidates_card)

        # ── 声部推测 ──
        self._voice_type_hint_card = QFrame()
        self._voice_type_hint_card.setStyleSheet("""
            QFrame { background: rgba(63, 185, 80, 0.06); border: 1px solid #1F3622; border-radius: 8px; }
        """)
        vt_layout = QVBoxLayout(self._voice_type_hint_card)
        vt_layout.setContentsMargins(14, 10, 14, 10)
        self._voice_type_hint_label = QLabel("")
        self._voice_type_hint_label.setStyleSheet("color: #3FB950; font-size: 12px; background: transparent;")
        self._voice_type_hint_label.setWordWrap(True)
        vt_layout.addWidget(self._voice_type_hint_label)
        layout.addWidget(self._voice_type_hint_card)

        # ── 操作按钮行 ──
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        # 重新校准按钮
        retry_btn = QPushButton("🔄 重新校准")
        retry_btn.setMinimumHeight(36)
        retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        retry_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #F85149;
                padding: 8px 16px; border-radius: 8px;
                font-size: 12px; border: 1px solid #30363D;
            }
            QPushButton:hover { background: rgba(248, 81, 73, 0.1); border-color: #F85149; }
        """)
        retry_btn.clicked.connect(self._on_retry)
        action_row.addWidget(retry_btn)

        action_row.addStretch()
        layout.addLayout(action_row)

        layout.addStretch()
        scroll.setWidget(content)

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

        return page

    # ═══════════════════════════════════════════════════════════
    # Phase 切换逻辑
    # ═══════════════════════════════════════════════════════════

    def _on_back(self) -> None:
        if self._phase == self.PHASE_DETECT:
            # 停止录音并回到引导
            self._stop_recording(abort=True)
            self._switch_phase(self.PHASE_GUIDE)
        elif self._phase == self.PHASE_VALIDATE:
            # 回到检测页（重新录）
            self._switch_phase(self.PHASE_DETECT)

    def _on_next(self) -> None:
        if self._phase == self.PHASE_GUIDE:
            # 读取模式选择
            if self._chromatic_radio.isChecked():
                self._mode = "chromatic"
            else:
                self._mode = "glissando"
            self._switch_phase(self.PHASE_DETECT)
            self._start_recording()

        elif self._phase == self.PHASE_DETECT:
            # 停止录音 → 分析 → 进入校验
            self._stop_recording(abort=False)

        elif self._phase == self.PHASE_VALIDATE:
            # 保存校准结果
            self._save_calibration()

    # ═══════════════════════════════════════════════════════════
    # 录音 & 实时检测
    # ═══════════════════════════════════════════════════════════

    def _start_recording(self) -> None:
        """开始录音"""
        if not HAS_SOUNDDEVICE:
            self._show_error("音频设备不可用")
            return

        # 清理旧数据
        self._recorded_audio.clear()
        self._pitch_track.clear()
        self._feature_track.clear()
        self._feature_scores.clear()
        self._candidates.clear()
        self._manual_candidates.clear()
        self._detected_t4 = 0.0
        self._detection_confidence = 0.0
        self._full_audio = None
        if self._temp_audio_file and os.path.exists(self._temp_audio_file):
            try:
                os.unlink(self._temp_audio_file)
            except Exception:
                pass
        self._temp_audio_file = None

        # 清空显示
        self._pitch_canvas.clear()
        # 设置预期换声区 (基于声部)
        vt = self._profile.effective_voice_type
        expected_t4 = _VOICE_TYPE_PASSAGGIO_HZ.get(vt, 400.0)
        self._pitch_canvas.set_expected_t4(expected_t4, self._profile.is_female)
        self._rec_timer_label.setText("00:00")

        try:
            self._audio_stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                blocksize=HOP_SIZE,
                callback=self._audio_callback,
                dtype='float32',
            )
            self._audio_stream.start()
        except Exception as e:
            self._show_error(f"无法打开音频设备:\n{e}")
            self._switch_phase(self.PHASE_GUIDE)
            return

        self._is_recording = True
        self._record_start_time = time.time()
        self._display_counter = 0

        # 启动显示更新定时器 (~15 fps)
        self._display_timer = QTimer(self)
        self._display_timer.timeout.connect(self._update_detect_display)
        self._display_timer.start(67)

        self._rec_status.setText("🔴 正在录音... 从低音滑到高音")
        self._rec_status.setStyleSheet(
            "color: #F85149; font-size: 14px; font-weight: bold; background: transparent;"
            "padding: 8px 14px; border: 1px solid #F85149; border-radius: 8px;"
        )

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """音频流回调（后台线程）"""
        if not self._is_recording:
            return

        if status:
            pass  # 忽略 xrun 警告

        chunk = indata[:, 0].copy()
        self._recorded_audio.append(chunk)

        # 检测当前帧的音高和频谱特征 (6维)
        freq, tilt, hnr, rms, l1l2, h2h3 = self._process_frame(chunk)
        elapsed = time.time() - self._record_start_time

        if freq > 0:
            self._pitch_track.append((elapsed, freq))
            self._current_freq = freq

        self._feature_track.append((elapsed, tilt, hnr, rms, l1l2, h2h3))
        self._current_tilt = tilt
        self._current_hnr = hnr
        self._current_rms = rms
        self._current_l1l2 = l1l2
        self._current_h2h3 = h2h3

        # 自动停止 (超时)
        if elapsed > MAX_RECORD_SECONDS:
            pass  # 主线程的 display timer 会处理

    def _process_frame(self, chunk: np.ndarray) -> Tuple[float, float, float, float, float, float]:
        """处理一帧音频: 返回 (freq_hz, spectral_tilt_dB, hnr_dB, rms_dB, l1l2_dB, h2h3_ratio)"""
        if len(chunk) < FRAME_SIZE:
            chunk = np.pad(chunk, (0, FRAME_SIZE - len(chunk)))

        # 去均值
        chunk = chunk - np.mean(chunk)

        # ── 音高检测 (简化 YIN) ──
        freq = self._yin_pitch(chunk[:FRAME_SIZE])

        # ── 频谱分析 ──
        windowed = chunk[:FRAME_SIZE] * np.hanning(FRAME_SIZE)
        fft = np.fft.rfft(windowed)
        mag = np.abs(fft)
        mag_db = 20 * np.log10(mag + 1e-10)

        freqs = np.fft.rfftfreq(FRAME_SIZE, 1.0 / SAMPLE_RATE)

        # 只考虑人声范围
        voice_mask = (freqs >= 80) & (freqs <= 3000)
        if not np.any(voice_mask):
            return 0.0, 0.0, 0.0, -60.0, 0.0, 0.0

        f_voice = freqs[voice_mask]
        m_voice = mag_db[voice_mask]

        # 频谱倾斜度 (线性回归) — 聚焦 500-2500 Hz 中高频段
        tilt_mask = (f_voice >= 500) & (f_voice <= 2500)
        if np.sum(tilt_mask) >= 3:
            log_f_tilt = np.log10(f_voice[tilt_mask] + 1e-10)
            tilt = self._linear_slope(log_f_tilt, m_voice[tilt_mask])
        else:
            log_f = np.log10(f_voice + 1e-10)
            tilt = self._linear_slope(log_f, m_voice)

        # HNR (谐波噪声比)
        hnr = self._compute_hnr(mag, freqs, freq)

        # RMS
        rms = 20 * np.log10(np.sqrt(np.mean(chunk ** 2)) + 1e-10)

        # ── L1-L2 谐波比 (研究文献关键特征) ──
        # L1-L2 = 基频与前两个谐波的幅度比
        # 换声点标志: L1-L2 从负值变为正值 (特别是女声)
        l1l2 = self._compute_l1l2(mag, freqs, freq)

        # ── H2/H3 主导度 (男声换声关键) ──
        # 胸声时 H2 主导; 换声后 H3 获得 F2 共振而增强
        # H2/H3 比值下降是即将换声的信号
        h2h3 = self._compute_h2h3_ratio(mag, freqs, freq)

        return freq, tilt, hnr, rms, l1l2, h2h3

    def _yin_pitch(self, audio_frame: np.ndarray) -> float:
        """简化 YIN 音高检测，返回频率 Hz 或 0.0"""
        frame_len = len(audio_frame)
        half_len = frame_len // 2

        # 差函数
        diff = np.zeros(half_len)
        for tau in range(1, half_len):
            diff[tau] = np.sum((audio_frame[:half_len] - audio_frame[tau:tau + half_len]) ** 2)

        # CMNDF
        cmndf = np.ones(half_len)
        running_sum = 0.0
        for tau in range(1, half_len):
            running_sum += diff[tau]
            cmndf[tau] = diff[tau] / (running_sum / tau) if running_sum > 0 else 1.0

        # 找第一个低于阈值的最小值
        min_period = int(SAMPLE_RATE / 2000)   # 最高检测频率
        max_period = int(SAMPLE_RATE / 70)     # 最低检测频率
        threshold = 0.15

        tau_est = min_period
        for tau in range(min_period, min(max_period, len(cmndf))):
            if cmndf[tau] < threshold:
                while tau + 1 < len(cmndf) and cmndf[tau + 1] < cmndf[tau]:
                    tau += 1
                tau_est = tau
                break

        if tau_est <= min_period:
            return 0.0

        freq = SAMPLE_RATE / tau_est
        if 70 <= freq <= 2000:
            return freq
        return 0.0

    @staticmethod
    def _linear_slope(x: np.ndarray, y: np.ndarray) -> float:
        """计算线性回归斜率 (dB / decade)"""
        if len(x) < 2:
            return 0.0
        n = len(x)
        sx, sy = np.sum(x), np.sum(y)
        sxy, sxx = np.sum(x * y), np.sum(x * x)
        denom = n * sxx - sx * sx
        if abs(denom) < 1e-10:
            return 0.0
        slope = (n * sxy - sx * sy) / denom
        return float(slope)

    @staticmethod
    def _compute_hnr(mag: np.ndarray, freqs: np.ndarray, f0: float) -> float:
        """计算谐波噪声比 (dB)

        HNR = 10 * log10(谐波能量 / 非谐波能量)
        """
        if f0 <= 0:
            return 0.0

        # 标记谐波 bins (±5% 容差)
        n_harmonics = 10
        harmonic_energy = 0.0
        harmonic_mask = np.zeros(len(freqs), dtype=bool)

        for h in range(1, n_harmonics + 1):
            hf = f0 * h
            if hf > SAMPLE_RATE / 2:
                break
            # 找到最接近的 bin
            idx = np.argmin(np.abs(freqs - hf))
            # 取 ±2 bins 范围
            lo = max(0, idx - 2)
            hi = min(len(freqs), idx + 3)
            harmonic_energy += np.sum(mag[lo:hi] ** 2)
            harmonic_mask[lo:hi] = True

        total_energy = np.sum(mag ** 2)
        noise_energy = max(total_energy - harmonic_energy, 1e-10)

        if harmonic_energy < 1e-10:
            return -10.0

        hnr = 10 * np.log10(harmonic_energy / noise_energy)
        return float(np.clip(hnr, -20, 40))

    @staticmethod
    def _compute_l1l2(mag: np.ndarray, freqs: np.ndarray, f0: float) -> float:
        """计算 L1-L2 谐波比 (dB) — 换声点关键指标

        L1 = 基频能量, L2 = 第二谐波能量。
        文献: 女声第二换声点 L1-L2 从负变正; 男声也有特征性变化。
        """
        if f0 <= 0:
            return 0.0

        def _get_harmonic_energy(h: int) -> float:
            hf = f0 * h
            if hf > SAMPLE_RATE / 2:
                return 0.0
            idx = np.argmin(np.abs(freqs - hf))
            lo = max(0, idx - 2)
            hi = min(len(freqs), idx + 3)
            return float(np.sum(mag[lo:hi] ** 2))

        e1 = _get_harmonic_energy(1)
        e2 = _get_harmonic_energy(2)

        if e1 < 1e-12 or e2 < 1e-12:
            return 0.0

        l1l2 = 10 * np.log10(e1 / e2)
        return float(np.clip(l1l2, -20, 20))

    @staticmethod
    def _compute_h2h3_ratio(mag: np.ndarray, freqs: np.ndarray, f0: float) -> float:
        """计算 H2/H3 主导度 (男声换声点关键)

        胸声区 H2 由 F1 共振主导 → H2/H3 > 1.5
        换声点附近 F2 共振转移到 H3 → H2/H3 逐步降至 < 1.0
        """
        if f0 <= 0:
            return 1.0

        def _get_harmonic_energy(h: int) -> float:
            hf = f0 * h
            if hf > SAMPLE_RATE / 2:
                return 0.0
            idx = np.argmin(np.abs(freqs - hf))
            lo = max(0, idx - 2)
            hi = min(len(freqs), idx + 3)
            return float(np.sum(mag[lo:hi] ** 2))

        e2 = _get_harmonic_energy(2)
        e3 = _get_harmonic_energy(3)

        if e3 < 1e-12:
            return 5.0  # H2 明显主导

        ratio = e2 / e3
        return float(np.clip(ratio, 0.1, 10.0))

    def _update_detect_display(self) -> None:
        """定时器回调: 更新实时显示（主线程）"""
        if not self._is_recording:
            return

        self._display_counter += 1
        elapsed = time.time() - self._record_start_time

        # 更新计时器
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        self._rec_timer_label.setText(f"{mins:02d}:{secs:02d}")

        # ── 更新音高画布 ──
        if self._current_freq > 0:
            self._pitch_canvas.add_point(elapsed, self._current_freq)

        # ── 更新 6 项指标 ──
        # 频谱倾斜: 归一化 [-35, -8] → [0, 1]
        tilt_norm = np.clip((self._current_tilt + 35) / 27, 0.0, 1.0)
        self._update_indicator_row(
            self._tilt_row_data, self._current_tilt,
            f"{self._current_tilt:.1f} dB", tilt_norm
        )

        # L1-L2 谐波比: 归一化 [-15, 15] → [0, 1]
        l1l2_norm = np.clip((self._current_l1l2 + 15) / 30, 0.0, 1.0)
        l1l2_status = "L1>L2" if self._current_l1l2 > 2 else "L1≈L2" if abs(self._current_l1l2) <= 2 else "L2>L1"
        self._update_indicator_row(
            self._l1l2_row_data, self._current_l1l2,
            f"{self._current_l1l2:+.1f} dB {l1l2_status}", l1l2_norm
        )

        # HNR: 归一化 [-5, 25] → [0, 1]
        hnr_norm = np.clip((self._current_hnr + 5) / 30, 0.0, 1.0)
        self._update_indicator_row(
            self._hnr_row_data, self._current_hnr,
            f"{self._current_hnr:.1f} dB", hnr_norm
        )

        # H2/H3 主导度: 归一化 [0.3, 5.0] → [0, 1]
        h2h3_norm = np.clip((self._current_h2h3 - 0.3) / 4.7, 0.0, 1.0)
        h2h3_status = "H2>>H3" if self._current_h2h3 > 2.0 else "H2>H3" if self._current_h2h3 > 1.2 else "H3↗"
        self._update_indicator_row(
            self._h2h3_row_data, self._current_h2h3,
            f"{self._current_h2h3:.2f} {h2h3_status}", h2h3_norm
        )

        # 音高平滑度: 基于最近3帧半音差
        smooth_score = 0.5
        if len(self._pitch_track) >= 3:
            recent_freqs = [f for _, f in list(self._pitch_track)[-3:] if f > 0]
            if len(recent_freqs) >= 2:
                diffs = [abs(math.log2(recent_freqs[i] / recent_freqs[i - 1])) for i in range(1, len(recent_freqs))]
                avg_diff = sum(diffs) / len(diffs)
                smooth_score = float(np.clip(1.0 - avg_diff / 0.3, 0.0, 1.0))  # 0.3 octave = very rough
        self._update_indicator_row(
            self._smooth_row_data, smooth_score,
            f"{'稳定 ✓' if smooth_score > 0.7 else '波动' if smooth_score > 0.3 else '⚠'}",
            smooth_score
        )

        # RMS: 归一化 [-50, -10] → [0, 1]
        rms_norm = np.clip((self._current_rms + 50) / 40, 0.0, 1.0)
        self._update_indicator_row(
            self._rms_row_data, self._current_rms,
            f"{self._current_rms:.1f} dB", rms_norm
        )

        # ── 更新区域判断 ──
        if self._current_freq > 0:
            region = self._estimate_current_region()
            self._region_label.setText(region)
            self._pitch_canvas.set_region(region)

        # 超时自动停止
        if elapsed > MAX_RECORD_SECONDS:
            self._stop_recording(abort=False)

    def _estimate_current_region(self) -> str:
        """根据当前特征估算发声区域"""
        freq = self._current_freq
        tilt = self._current_tilt

        if freq <= 0:
            return "等待人声..."

        # 用声部先验估计
        vt = self._profile.effective_voice_type
        expected_t4 = _VOICE_TYPE_PASSAGGIO_HZ.get(vt, 400.0)

        if freq < expected_t4 * 0.85:
            region = "胸声区 ●"
            color = "#3FB950"
        elif freq < expected_t4 * 1.1:
            region = "换声区 ◐"
            color = "#D29922"
        else:
            region = "头声区 ○"
            color = "#58A6FF"

        return f'<span style="color:{color}; font-weight:bold;">{region}</span>'

    def _stop_recording(self, abort: bool = False) -> None:
        """停止录音"""
        self._is_recording = False

        # 停止音频流
        if self._audio_stream is not None:
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None

        # 停止定时器
        if self._display_timer is not None:
            self._display_timer.stop()
            self._display_timer = None

        self._rec_status.setText("⏹ 录音已停止")
        self._rec_status.setStyleSheet(
            "color: #8B949E; font-size: 14px; font-weight: bold; background: transparent;"
            "padding: 8px 14px; border: 1px solid #30363D; border-radius: 8px;"
        )

        # 恢复按钮样式
        self._next_btn.setText("💾 确认保存")
        self._next_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3FB950, stop:1 #238636);
                color: #FFFFFF; font-weight: bold;
                padding: 8px 24px; border-radius: 8px;
                font-size: 12px; border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #56D364, stop:1 #3FB950);
            }
        """)

        if abort:
            return

        # 保存完整音频
        if self._recorded_audio:
            self._full_audio = np.concatenate(self._recorded_audio)

            # 保存临时 WAV 文件供回放
            try:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.wav', prefix='mindecho_cal_')
                # 写入简单 WAV
                self._write_wav(tmp.name, self._full_audio)
                self._temp_audio_file = tmp.name
            except Exception:
                self._temp_audio_file = None

        # 运行换声点检测
        self._detect_passaggio()

        # 切换到校验页
        self._switch_phase(self.PHASE_VALIDATE)
        self._update_validate_page()

    def _write_wav(self, filepath: str, audio: np.ndarray) -> None:
        """写入 16-bit PCM WAV 文件 — 带静音修剪和淡入淡出"""
        # ── 修剪首尾静音 ──
        audio = self._trim_silence(audio)

        if len(audio) < 100:
            return

        # ── 短促淡入淡出 (5ms) ──
        fade_len = int(SAMPLE_RATE * 0.005)
        if fade_len > 1 and len(audio) > fade_len * 4:
            fade_in = np.linspace(0, 1, fade_len)
            fade_out = np.linspace(1, 0, fade_len)
            audio[:fade_len] *= fade_in
            audio[-fade_len:] *= fade_out

        # ── 温和标准化: -3dBFS 峰值 ──
        peak = np.max(np.abs(audio))
        if peak > 0.01:
            target_peak = 0.707  # -3dBFS
            gain = target_peak / peak
            # 限制增益不超过 12dB，避免过度放大底噪
            gain = min(gain, 4.0)
            audio = audio * gain
        elif peak > 0:
            # 非常安静的信号，保持原样避免放大噪声
            pass

        audio_int16 = (audio * 32767).astype(np.int16)

        # WAV 文件头
        import struct
        n_samples = len(audio_int16)
        data_size = n_samples * 2
        with open(filepath, 'wb') as f:
            f.write(b'RIFF')
            f.write(struct.pack('<I', 36 + data_size))
            f.write(b'WAVE')
            f.write(b'fmt ')
            f.write(struct.pack('<I', 16))        # chunk size
            f.write(struct.pack('<H', 1))         # PCM
            f.write(struct.pack('<H', 1))         # mono
            f.write(struct.pack('<I', SAMPLE_RATE))
            f.write(struct.pack('<I', SAMPLE_RATE * 2))  # byte rate
            f.write(struct.pack('<H', 2))         # block align
            f.write(struct.pack('<H', 16))        # bits per sample
            f.write(b'data')
            f.write(struct.pack('<I', data_size))
            f.write(audio_int16.tobytes())

    @staticmethod
    def _trim_silence(audio: np.ndarray, threshold_db: float = -40.0) -> np.ndarray:
        """修剪首尾静音段

        Args:
            audio: 原始音频数据
            threshold_db: 静音判定阈值 (dB)，低于此值视为静音
        Returns:
            修剪后的音频
        """
        if len(audio) < 100:
            return audio

        # 计算 RMS 包络 (10ms 窗口)
        win_len = int(SAMPLE_RATE * 0.01)  # 10ms
        if win_len < 4:
            return audio

        n_windows = len(audio) // win_len
        if n_windows < 3:
            return audio

        rms = np.zeros(n_windows)
        for i in range(n_windows):
            chunk = audio[i * win_len:(i + 1) * win_len]
            rms[i] = 20 * np.log10(np.sqrt(np.mean(chunk ** 2)) + 1e-10)

        # 找首尾超过阈值的段落
        active = rms > threshold_db
        if not np.any(active):
            return audio  # 全是静音，保留原样

        first_active = np.argmax(active)
        last_active = len(active) - np.argmax(active[::-1]) - 1

        # 前后各保留 50ms 的缓冲
        margin = max(1, int(0.05 / 0.01))
        start_idx = max(0, first_active - margin) * win_len
        end_idx = min(len(audio), (last_active + 1 + margin) * win_len)

        return audio[start_idx:end_idx]

    # ═══════════════════════════════════════════════════════════
    # 换声点检测算法 (多特征融合)
    # ═══════════════════════════════════════════════════════════

    def _detect_passaggio(self) -> None:
        """多特征融合检测换声点 (鲁棒增强版)

        改进:
          - 原始特征先平滑再差分，减少帧间噪声
          - 更宽的声部先验 (σ=4 半音)，降低错误引导
          - 自适应特征权重: 信号弱的特征自动降权
          - 找 top-3 候选峰，不只看全局最高
          - 置信度基于峰显著度 (相对次高峰的比值)
        """
        if len(self._pitch_track) < 5 or len(self._feature_track) < 5:
            self._detected_t4 = 0.0
            self._detection_confidence = 0.0
            self._candidates = []
            return

        # ── 对齐时间轴 ──
        ft_times = np.array([t for t, _, _, _, _, _ in self._feature_track])
        ft_tilts = np.array([tilt for _, tilt, _, _, _, _ in self._feature_track])
        ft_hnrs = np.array([hnr for _, _, hnr, _, _, _ in self._feature_track])
        ft_rmss = np.array([rms for _, _, _, rms, _, _ in self._feature_track])
        ft_l1l2s = np.array([l1l2 for _, _, _, _, l1l2, _ in self._feature_track])
        ft_h2h3s = np.array([h2h3 for _, _, _, _, _, h2h3 in self._feature_track])

        pitch_times = np.array([t for t, _ in self._pitch_track])
        pitch_freqs = np.array([f for _, f in self._pitch_track])

        if len(ft_times) < 2 or len(pitch_times) < 2:
            self._detected_t4 = 0.0
            self._detection_confidence = 0.0
            self._candidates = []
            return

        # 插值特征到音高时间点
        tilts_raw = np.interp(pitch_times, ft_times, ft_tilts)
        hnrs_raw = np.interp(pitch_times, ft_times, ft_hnrs)
        rmss_raw = np.interp(pitch_times, ft_times, ft_rmss)

        n = len(pitch_times)

        # ── 特征平滑 (3帧移动平均，降低帧间噪声) ──
        def _smooth3(x: np.ndarray) -> np.ndarray:
            if len(x) < 3:
                return x.copy()
            s = x.copy()
            for i in range(1, len(x) - 1):
                s[i] = (x[i - 1] + x[i] + x[i + 1]) / 3.0
            return s

        tilts = _smooth3(tilts_raw)
        hnrs = _smooth3(hnrs_raw)
        rmss = _smooth3(rmss_raw)

        # ── 1. 频谱倾斜突变分数 ──
        # 胸→头时 tilt 变得更负
        tilt_drop = np.zeros(n)
        tilt_drop[1:] = np.clip(-np.diff(tilts), 0, None)
        tilt_quality = self._feature_snr(tilt_drop)
        tilt_score = self._normalize_score(tilt_drop)

        # ── 2. 音高断连分数 ──
        semitone_diff = np.zeros(n)
        for i in range(1, n):
            if pitch_freqs[i] > 0 and pitch_freqs[i - 1] > 0:
                semitone_diff[i] = abs(12 * math.log2(pitch_freqs[i] / max(pitch_freqs[i - 1], 1e-6)))
        semitone_diff = _smooth3(semitone_diff)
        pitch_quality = self._feature_snr(semitone_diff)
        pitch_jump_score = self._normalize_score(semitone_diff)

        # ── 3. HNR 骤降分数 ──
        hnr_drop = np.zeros(n)
        hnr_drop[1:] = np.clip(-np.diff(hnrs), 0, None)
        hnr_quality = self._feature_snr(hnr_drop)
        hnr_score = self._normalize_score(hnr_drop)

        # ── 4. 振幅骤降分数 ──
        rms_drop = np.zeros(n)
        rms_drop[1:] = np.clip(-np.diff(rmss), 0, None)
        rms_quality = self._feature_snr(rms_drop)
        rms_score = self._normalize_score(rms_drop)

        # ── 5. L1-L2 谐波比逆转 (研究文献关键特征) ──
        # L1-L2 从负变正 → 换声标志 (特别是女声)
        # L1-L2 负→正发生在第二换声点，是文献中最稳定的声学指标之一
        l1l2s = _smooth3(np.interp(pitch_times, ft_times, ft_l1l2s))
        l1l2_rise = np.zeros(n)
        l1l2_rise[1:] = np.clip(np.diff(l1l2s), 0, None)  # L1-L2 上升
        l1l2_quality = self._feature_snr(l1l2_rise)
        l1l2_score = self._normalize_score(l1l2_rise)

        # ── 6. H2/H3 主导度转换 (男声换声关键) ──
        # H2/H3 从 > 1.5 逐步降至 < 1.0 → 换声标志
        h2h3s = _smooth3(np.interp(pitch_times, ft_times, ft_h2h3s))
        h2h3_drop = np.zeros(n)
        h2h3_drop[1:] = np.clip(-np.diff(h2h3s), 0, None)  # H2/H3 下降
        h2h3_quality = self._feature_snr(h2h3_drop)
        h2h3_score = self._normalize_score(h2h3_drop)

        # ── 7. 声部先验 —— 手动 vs 自动推断区分 ──
        vt = self._profile.effective_voice_type
        is_manual_vt = bool(getattr(self._profile, 'voice_type_manual', ''))
        expected_t4 = _VOICE_TYPE_PASSAGGIO_HZ.get(vt, None)
        prior_sigma = 4.0 if is_manual_vt else 6.0  # 自动推断用更宽 σ
        prior_score = np.ones(n) * 0.5
        if expected_t4 is not None:
            for i, f in enumerate(pitch_freqs):
                if f > 0:
                    semitone_dist = abs(12 * math.log2(f / expected_t4))
                    prior_score[i] = math.exp(-0.5 * (semitone_dist / prior_sigma) ** 2)

        # ── 自适应权重: 信号质量越高的特征权重越大 ──
        qualities = {
            'tilt': max(tilt_quality, 0.1),
            'pitch': max(pitch_quality, 0.1),
            'hnr': max(hnr_quality, 0.1),
            'rms': max(rms_quality, 0.1),
            'l1l2': max(l1l2_quality, 0.1),
            'h2h3': max(h2h3_quality, 0.1),
        }
        prior_contrib = 1.0 if (expected_t4 is not None and is_manual_vt) else 0.6
        q_sum = sum(qualities.values()) + prior_contrib  # 自动推断时降低先验权重
        # 基础权重: tilt 28%, pitch 18%, hnr 15%, rms 8%, l1l2 11%, h2h3 10%, prior 10%
        base_w = {'tilt': 0.28, 'pitch': 0.18, 'hnr': 0.15, 'rms': 0.08, 'l1l2': 0.11, 'h2h3': 0.10}
        w_tilt = base_w['tilt'] * qualities['tilt'] / max(q_sum * base_w['tilt'], 0.01)
        w_pitch = base_w['pitch'] * qualities['pitch'] / max(q_sum * base_w['pitch'], 0.01)
        w_hnr = base_w['hnr'] * qualities['hnr'] / max(q_sum * base_w['hnr'], 0.01)
        w_rms = base_w['rms'] * qualities['rms'] / max(q_sum * base_w['rms'], 0.01)
        w_l1l2 = base_w['l1l2'] * qualities['l1l2'] / max(q_sum * base_w['l1l2'], 0.01)
        w_h2h3 = base_w['h2h3'] * qualities['h2h3'] / max(q_sum * base_w['h2h3'], 0.01)
        # 声部手动设置 → 10% prior；自动推断 → 约 6% prior
        w_prior = 0.10 if (expected_t4 is not None and is_manual_vt) else 0.06

        # 归一化总权重
        w_total = w_tilt + w_pitch + w_hnr + w_rms + w_l1l2 + w_h2h3 + w_prior
        w_tilt /= w_total
        w_pitch /= w_total
        w_hnr /= w_total
        w_rms /= w_total
        w_l1l2 /= w_total
        w_h2h3 /= w_total
        w_prior /= w_total

        # ── 融合打分 ──
        fusion_score = (
            w_tilt * tilt_score +
            w_pitch * pitch_jump_score +
            w_hnr * hnr_score +
            w_rms * rms_score +
            w_l1l2 * l1l2_score +
            w_h2h3 * h2h3_score +
            w_prior * prior_score
        )

        # 保存各特征原始分数 (用于诊断展示)
        self._raw_tilt_score = tilt_score.copy()
        self._raw_pitch_score = pitch_jump_score.copy()
        self._raw_hnr_score = hnr_score.copy()
        self._raw_rms_score = rms_score.copy()
        self._raw_l1l2_score = l1l2_score.copy()
        self._raw_h2h3_score = h2h3_score.copy()
        self._raw_prior_score = prior_score.copy()

        # ── 时间平滑 (高斯核, 自适应宽度) ──
        kernel_width = max(3, n // 15)  # 略窄的核，保留更多细节
        if kernel_width % 2 == 0:
            kernel_width += 1
        kernel = np.exp(-0.5 * np.linspace(-2.5, 2.5, kernel_width) ** 2)
        kernel /= kernel.sum()
        fusion_smooth = np.convolve(fusion_score, kernel, mode='same')

        # ── 找 top-3 局部极大值 ──
        # 换声点生理上限: 最高声部(女高音)约 F#5(740Hz)，给安全余量到 A5(880Hz)
        # 男声换声点最高约 G4(392Hz)，给余量到 C5(523Hz)
        min_freq = 250.0 if self._profile.is_female else 150.0
        max_freq = 880.0 if self._profile.is_female else 550.0
        valid_mask = (pitch_freqs > min_freq) & (pitch_freqs < max_freq)
        valid_idx = np.where(valid_mask)[0]

        if len(valid_idx) < 3:
            self._detected_t4 = 0.0
            self._detection_confidence = 0.0
            self._candidates = []
            return

        # 找局部极大值
        peaks = []
        for i in range(1, n - 1):
            if not valid_mask[i]:
                continue
            if fusion_smooth[i] > fusion_smooth[i - 1] and fusion_smooth[i] >= fusion_smooth[i + 1]:
                peaks.append((i, fusion_smooth[i], pitch_freqs[i]))

        # 按分数排序取 top-3
        peaks.sort(key=lambda x: x[1], reverse=True)
        top_peaks = peaks[:3]

        # ── 存储候选人 ──
        self._candidates = []
        for idx, score, freq in top_peaks:
            # 计算每个特征在此位置的贡献
            candidate = {
                'freq': float(freq),
                'fusion_score': float(score),
                'tilt': float(tilt_score[idx]),
                'pitch_jump': float(pitch_jump_score[idx]),
                'hnr': float(hnr_score[idx]),
                'rms': float(rms_score[idx]),
                'l1l2': float(l1l2_score[idx]),
                'h2h3': float(h2h3_score[idx]),
                'prior': float(prior_score[idx]),
            }
            self._candidates.append(candidate)

        # ── 融合分重标定: 增强可读性 ──
        # 原始融合分经过 baseline 减法后通常偏低 (0.05~0.5)，
        # 重标定到 0.20~0.92 区间，保持排序但让数值更直观。
        if self._candidates:
            top_score = self._candidates[0]['fusion_score']
            if top_score > 0.01:
                for c in self._candidates:
                    ratio = c['fusion_score'] / top_score
                    c['fusion_score'] = float(np.clip(0.20 + ratio * 0.72, 0.15, 0.92))

        if not self._candidates:
            self._detected_t4 = 0.0
            self._detection_confidence = 0.0
            return

        best = self._candidates[0]
        self._detected_t4 = best['freq']
        self._adjusted_t4 = self._detected_t4

        # ── 置信度: 基于峰显著度 + 特征一致性 ──
        if len(self._candidates) >= 2:
            peak_ratio = self._candidates[1]['fusion_score'] / max(best['fusion_score'], 0.001)
        else:
            peak_ratio = 0.0

        # 背景水平 (加下限防止除零和过度放大)
        background = max(float(np.median(fusion_smooth[valid_idx])), 0.015)
        peak_prominence = best['fusion_score'] / background

        # 峰显著度 → 基础置信度 (sigmoid)
        # 新归一化下 prominence 通常在 3~25 范围
        # center=6.0, slope=0.45: prominence=3→21%, 6→50%, 12→84%, 20→95%
        raw_conf = float(np.clip(1.0 / (1.0 + math.exp(-(peak_prominence - 6.0) * 0.45)), 0.10, 0.92))

        # 一致性惩罚: 次高峰越接近，越不确定
        # 用平滑的 sigmoid 替代硬截断
        if peak_ratio < 0.3:
            # 次高峰远低于主峰 → 几乎无惩罚
            consistency = 1.0
        elif peak_ratio < 0.6:
            # 次高峰中度接近 → 轻度惩罚
            consistency = 1.0 - 0.25 * (peak_ratio - 0.3) / 0.3
        else:
            # 次高峰很近 → 线性加重惩罚, 最低 0.25
            consistency = max(0.25, 1.0 - 0.75 * (peak_ratio - 0.3) / 0.7)

        # 特征一致性加分: 如果多个特征同时指向相近频率，提升置信度
        feat_agreement = self._compute_feature_agreement(best, self._candidates)

        self._detection_confidence = float(np.clip(
            raw_conf * consistency * (0.85 + 0.15 * feat_agreement),
            0.10, 0.95
        ))

        # 保存融合分数用于可视化
        self._feature_scores = [
            (pitch_times[i], pitch_freqs[i], fusion_smooth[i])
            for i in range(n) if pitch_freqs[i] > 0
        ]

    @staticmethod
    def _feature_snr(x: np.ndarray) -> float:
        """计算特征的信号质量 (峰值/中值比)

        返回值接近 1.0 = 有明确峰值(好信号)
        返回值接近 0.0 = 接近平坦噪声(差信号)
        """
        if len(x) < 3:
            return 0.0
        peak = np.max(x)
        median = np.median(np.abs(x))
        if peak < 1e-8 or median < 1e-8:
            return 0.0
        ratio = peak / median
        # 映射: ratio=2→0.3, ratio=5→0.6, ratio=10→0.8
        return float(np.clip(np.log2(ratio) / 4.0, 0.0, 1.0))

    @staticmethod
    def _compute_feature_agreement(best: dict, candidates: list) -> float:
        """计算各特征在最佳候选点的一致性

        如果 tilt/pitch/HNR/rms 的峰值都指向相近频率 → 高一致性
        如果各特征峰值分散在不同频率 → 低一致性（说明信号噪声大）
        返回 0.0~1.0
        """
        if not candidates or len(candidates) < 2:
            return 0.5

        # 提取各特征分数向量 (来自 best candidate)
        feat_names = ['tilt', 'pitch_jump', 'hnr', 'rms']
        best_feats = {k: best.get(k, 0.0) for k in feat_names}

        # 计算各特征在 best 点的值 — 高值 = 该特征也指向这里
        gaps = [best_feats[k] for k in feat_names if best_feats[k] >= 0]

        if not gaps:
            return 0.0

        # 一致性 = 各特征分数的均值 (都高 → 一致，有高有低 → 不一致)
        mean_val = sum(gaps) / len(gaps)
        return float(np.clip(mean_val * 1.5, 0.0, 1.0))

    @staticmethod
    def _normalize_score(x: np.ndarray) -> np.ndarray:
        """信号保留归一化到 [0, 1]

        关键教训: P95 除法 (x/P95) 会让噪声特征也产生 1.0 的"伪峰"，因为
        每个特征至少有一个值接近 P95。这些伪峰在融合时抬高背景，压低真实
        峰的显著度 → 置信度偏低。

        新方案: 用中位数作为噪声基线减去，用 (P95-中位数) 作为动态范围。
        - 纯噪声特征: 中位数 ≈ P95/2, 减去基线后大部分值接近 0, 不会产生伪峰
        - 有信号特征: 中位数 ≈ 0, P95 ≈ 峰值, 基线减法不改变峰的结构
        - 融合背景从中位数级 (~0.2-0.5) 降到 0.05 以下, 峰显著度提升 5-10 倍
        """
        if len(x) < 2:
            return np.zeros_like(x)
        med = float(np.median(x))
        p95 = float(np.percentile(x, 95))
        dynamic_range = max(p95 - med, 1e-8)
        return np.clip((x - med) / dynamic_range, 0.0, 1.0)

    # ═══════════════════════════════════════════════════════════
    # Phase 3 — 校验页更新 & 交互
    # ═══════════════════════════════════════════════════════════

    def _update_validate_page(self) -> None:
        """填充校验页数据"""
        t4 = self._detected_t4
        conf = self._detection_confidence

        if t4 <= 0:
            # 未检测到
            self._detected_t4_label.setText("未检测到换声点")
            self._detected_t4_label.setStyleSheet(
                "color: #F85149; font-size: 16px; font-weight: bold; background: transparent;"
            )
            self._confidence_label.setText("请重新录音")
            self._conf_bar.setStyleSheet("background: #21262D; border-radius: 3px;")
            self._voice_type_hint_label.setText("⚠️ 检测失败，请用更明显的滑音重试。确保从低音跨到高音。")
            self._adjusted_value_label.setText("")
            self._piano_widget.clear()
            self._candidates_card.setVisible(False)
            # 禁用保存
            self._next_btn.setEnabled(False)
            self._next_btn.setText("⚠️ 未检测到换声点")
            return

        self._next_btn.setEnabled(True)
        self._next_btn.setText("💾 确认保存")

        note = _hz_to_note_name(t4)
        self._detected_t4_label.setText(f"首选: {t4:.0f} Hz  ({note})")
        self._detected_t4_label.setStyleSheet(
            "color: #58A6FF; font-size: 18px; font-weight: bold; background: transparent;"
        )

        # ── 置信度分级标签 ──
        if conf >= 0.70:
            tier_text = "🟢 高置信度"
            tier_detail = "各特征指向一致，检测结果可信"
            tier_color = "#3FB950"
        elif conf >= 0.40:
            tier_text = "🟡 中等置信度"
            tier_detail = "建议试听确认；如有疑虑可从下方备选候选中选择"
            tier_color = "#D29922"
        elif conf >= 0.20:
            tier_text = "🟠 较低置信度"
            tier_detail = "多个候选点竞争，建议查看备选候选或重新录制"
            tier_color = "#F0883E"
        else:
            tier_text = "🔴 低置信度"
            tier_detail = "信号特征不明显。推荐用更大幅度的滑音重新录制，或手动选择候选"
            tier_color = "#F85149"

        self._confidence_label.setText(f"{tier_text}　｜　{conf:.0%}")
        self._confidence_label.setStyleSheet(
            f"color: {tier_color}; font-size: 13px; font-weight: bold; background: transparent;"
        )

        # 置信度详情提示
        if hasattr(self, '_conf_detail_label'):
            self._conf_detail_label.setText(tier_detail)

        # 置信度条
        self._conf_bar.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {tier_color}, stop:{conf:.2f} {tier_color},
                    stop:{conf:.2f} #21262D, stop:1 #21262D);
                border-radius: 3px;
            }}
        """)

        # 钢琴键盘
        self._piano_widget.set_t4(t4)

        # 音高轨迹画布
        self._validate_canvas.set_data(
            list(self._pitch_track),
            list(self._all_candidates_flat()),
            t4,
        )

        # 滑块范围: ±3 半音
        midi_center = _hz_to_midi(t4)
        self._slider_midi_min = midi_center - 3
        self._slider_midi_max = midi_center + 3
        self._slider_min_label.setText(_hz_to_note_name(_midi_to_hz(self._slider_midi_min)))
        self._slider_max_label.setText(_hz_to_note_name(_midi_to_hz(self._slider_midi_max)))
        self._adjust_slider.setValue(100)  # 居中
        self._on_slider_changed(100)

        # ── 备选候选点填充 ──
        self._populate_candidates()

        # 声部推测
        self._update_voice_type_hint()

    def _all_candidates_flat(self) -> List[dict]:
        """返回所有候选 (自动检测在前，手动选取在后)，每个带 'source' 和 'flat_index'"""
        result = []
        for c in self._candidates:
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

    def _add_manual_candidate(self, hz: float, time_s: float = 0.0) -> bool:
        """添加用户手动选取的候选点，并从原始特征数据中查找该频率的实际评分

        Returns:
            True 如果成功添加，False 如果是重复或无效
        """
        if hz <= 0:
            return False
        # 去重: 与已有候选差距 < 2Hz 视为重复
        for existing in self._all_candidates_flat():
            if abs(existing['freq'] - hz) < 2.0:
                return False

        note = _hz_to_note_name(hz)

        # ── 从原始特征数据中查找该频率的实际评分 ──
        feat = self._lookup_feature_scores_at_hz(hz)
        fusion = feat['fusion']

        self._manual_candidates.append({
            'freq': hz,
            'time': time_s,
            'note': note,
            'source': 'manual',
            'fusion_score': fusion,
            'tilt': feat['tilt'],
            'pitch_jump': feat['pitch_jump'],
            'hnr': feat['hnr'],
            'rms': feat['rms'],
            'l1l2': feat['l1l2'],
            'h2h3': feat['h2h3'],
            'prior': feat['prior'],
        })
        return True

    def _lookup_feature_scores_at_hz(self, target_hz: float) -> dict:
        """在原始特征数组中查找最接近 target_hz 的频点的各特征评分

        从 self._pitch_track 和 self._raw_*_score 中查找最近邻。
        如果没有原始数据，返回零值 dict。
        """
        zero = {'tilt': 0.0, 'pitch_jump': 0.0, 'hnr': 0.0, 'rms': 0.0,
                'l1l2': 0.0, 'h2h3': 0.0, 'prior': 0.0, 'fusion': 0.0}

        if not self._pitch_track:
            return zero

        pitch_times = np.array([t for t, _ in self._pitch_track])
        pitch_freqs = np.array([f for _, f in self._pitch_track])

        if len(pitch_freqs) < 2:
            return zero

        # 找最近频点
        best_i = 0
        best_dist = float('inf')
        for i, f in enumerate(pitch_freqs):
            if f <= 0:
                continue
            dist = abs(f - target_hz)
            if dist < best_dist:
                best_dist = dist
                best_i = i

        if best_dist > target_hz * 0.3:
            return zero

        # 安全提取各原始评分
        def _safe_get(arr: np.ndarray, idx: int) -> float:
            if arr is None or len(arr) == 0 or idx >= len(arr):
                return 0.0
            val = float(arr[idx])
            return max(0.0, min(1.0, val))

        raw_scores = {
            'tilt':        _safe_get(getattr(self, '_raw_tilt_score', None), best_i),
            'pitch_jump':  _safe_get(getattr(self, '_raw_pitch_score', None), best_i),
            'hnr':         _safe_get(getattr(self, '_raw_hnr_score', None), best_i),
            'rms':         _safe_get(getattr(self, '_raw_rms_score', None), best_i),
            'l1l2':        _safe_get(getattr(self, '_raw_l1l2_score', None), best_i),
            'h2h3':        _safe_get(getattr(self, '_raw_h2h3_score', None), best_i),
            'prior':       _safe_get(getattr(self, '_raw_prior_score', None), best_i),
        }

        # 融合分 = 加权平均 (使用与检测算法相同的权重比例)
        w = {'tilt': 0.28, 'pitch_jump': 0.18, 'hnr': 0.15, 'rms': 0.08,
             'l1l2': 0.11, 'h2h3': 0.10, 'prior': 0.10}
        fusion = sum(w[k] * raw_scores[k] for k in w)
        raw_scores['fusion'] = float(np.clip(fusion, 0.0, 1.0))

        return raw_scores

    def _rebuild_candidates_ui(self) -> None:
        """清除并重建候选点行 (响应新增/删除候选)"""
        # 清除旧行
        for w in self._candidate_row_widgets:
            self._candidates_rows_layout.removeWidget(w)
            w.deleteLater()
        self._candidate_row_widgets.clear()
        self._candidate_row_data.clear()

        all_cands = self._all_candidates_flat()
        n_cands = len(all_cands)

        for flat_idx, c in enumerate(all_cands):
            row = QHBoxLayout()
            row.setSpacing(6)

            # 来源标识
            is_auto = (c['source'] == 'auto')
            is_selected = (abs(c['freq'] - self._adjusted_t4) < 1.0) if self._adjusted_t4 > 0 else False

            # 来源图标
            src_lbl = QLabel("🤖" if is_auto else "✋")
            src_lbl.setFixedWidth(22)
            src_lbl.setToolTip("自动检测" if is_auto else "手动选取")
            src_lbl.setStyleSheet("font-size: 13px; background: transparent;")
            row.addWidget(src_lbl)

            # 频率信息和描述
            note = _hz_to_note_name(c['freq'])
            fusion = c.get('fusion_score', 0.0)

            # 构建特征贡献排行 (自动和手动都适用)
            top_feats = [
                ('频谱倾斜', c.get('tilt', 0)),
                ('音高突变', c.get('pitch_jump', 0)),
                ('HNR骤降', c.get('hnr', 0)),
                ('音量突变', c.get('rms', 0)),
                ('L1-L2逆转', c.get('l1l2', 0)),
                ('H2/H3转换', c.get('h2h3', 0)),
                ('先验', c.get('prior', 0)),
            ]
            top_feats.sort(key=lambda x: x[1], reverse=True)
            feat_str = " | ".join([f"{n}:{v:.2f}" for n, v in top_feats[:2]])

            if is_auto:
                info_text = f"{c['freq']:.0f} Hz ({note})  |  综合: {fusion:.2f}  |  {feat_str}"
            else:
                if fusion > 0.01:
                    info_text = f"{c['freq']:.0f} Hz ({note})  |  综合: {fusion:.2f}  |  {feat_str}  ✋手动"
                else:
                    info_text = f"{c['freq']:.0f} Hz ({note})  — 手动选取 (无匹配特征数据)"

            if is_selected:
                info_text = "★ 当前 → " + info_text

            cand_lbl = QLabel(info_text)
            cand_style = ("color: #58A6FF; font-weight: bold;" if is_selected else
                         "color: #C9D1D9;") + " font-size: 11px; background: transparent;"
            cand_lbl.setStyleSheet(cand_style)
            cand_lbl.setWordWrap(True)
            row.addWidget(cand_lbl, 1)

            # 试听按钮 (每个候选都有)
            preview_btn = QPushButton("🔊")
            preview_btn.setFixedSize(26, 26)
            preview_btn.setToolTip(f"试听 {note} ({c['freq']:.0f}Hz) 附近 0.5 秒录音")
            preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            preview_btn.setStyleSheet("""
                QPushButton {
                    background: transparent; border: 1px solid #30363D;
                    border-radius: 13px; font-size: 11px; color: #8B949E;
                }
                QPushButton:hover {
                    background: #1A2540; border-color: #58A6FF; color: #58A6FF;
                }
            """)
            preview_btn.clicked.connect(lambda checked, fi=flat_idx: self._preview_candidate_audio(fi))
            row.addWidget(preview_btn)

            # 选择按钮
            if is_selected:
                select_text = "← 当前"
                select_style = """
                    QPushButton {
                        background: rgba(88, 166, 255, 0.15); color: #58A6FF;
                        padding: 4px 8px; border-radius: 4px;
                        font-size: 10px; border: 1px solid #58A6FF;
                    }
                """
            else:
                select_text = "选此"
                select_style = """
                    QPushButton {
                        background: #21262D; color: #58A6FF;
                        padding: 4px 8px; border-radius: 4px;
                        font-size: 10px; border: 1px solid #30363D;
                    }
                    QPushButton:hover { background: #30363D; border-color: #58A6FF; }
                """
            select_btn = QPushButton(select_text)
            select_btn.setFixedWidth(60)
            select_btn.setMinimumHeight(24)
            select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            select_btn.setStyleSheet(select_style)
            select_btn.clicked.connect(lambda checked, fi=flat_idx: self._on_select_candidate(fi))
            row.addWidget(select_btn)

            # 将 row layout 包装成 QWidget 以便加入 QVBoxLayout
            row_widget = QWidget()
            if is_selected:
                row_widget.setStyleSheet(
                    "background: rgba(88, 166, 255, 0.10);"
                    "border: 1px solid rgba(88, 166, 255, 0.35);"
                    "border-radius: 6px;"
                )
            else:
                row_widget.setStyleSheet("background: transparent;")
            row_widget.setLayout(row)
            self._candidates_rows_layout.addWidget(row_widget)
            self._candidate_row_widgets.append(row_widget)
            self._candidate_row_data.append(c)

        # 候选面板可见: 有候选或曾经有候选时显示
        self._candidates_card.setVisible(n_cands >= 2)

    def _populate_candidates(self) -> None:
        """兼容旧调用 — 委托给新的动态重建方法"""
        self._rebuild_candidates_ui()

    def _update_voice_type_hint(self) -> None:
        """根据检测到的换声点推测声部"""
        t4 = self._adjusted_t4 if self._adjusted_t4 > 0 else self._detected_t4
        if t4 <= 0:
            return

        # 找最近的声部换声点
        best_vt = ""
        best_dist = float('inf')
        for vt, expected_hz in _VOICE_TYPE_PASSAGGIO_HZ.items():
            dist = abs(12 * math.log2(t4 / expected_hz))
            if dist < best_dist:
                best_dist = dist
                best_vt = vt

        vt_display = _VOICE_TYPE_DISPLAY.get(best_vt, best_vt)
        expected_hz = _VOICE_TYPE_PASSAGGIO_HZ.get(best_vt, 0)
        expected_note = _hz_to_note_name(expected_hz)
        current_vt = self._profile.effective_voice_type
        current_display = _VOICE_TYPE_DISPLAY.get(current_vt, current_vt) if current_vt else "未指定"

        if best_dist < 1.5:
            hint = (
                f"🎯 测得的换声点 ({_hz_to_note_name(t4)}) 非常接近 {vt_display} 的典型值 "
                f"({expected_note}, {expected_hz:.0f} Hz)。"
            )
            if current_vt and current_vt != best_vt:
                hint += f"\n⚠️ 你当前声部设置为「{current_display}」，与检测结果不同。建议在校准后更新声部。"
        else:
            hint = (
                f"📊 测得的换声点在 {_hz_to_note_name(t4)}，最接近 {vt_display} "
                f"(偏差 {best_dist:.1f} 个半音)。建议多次校准以提高准确性。"
            )

        self._voice_type_hint_label.setText(hint)

    def _on_slider_changed(self, value: int) -> None:
        """手动微调滑块变化"""
        # value: 0-200, 100 = 中心（自动检测值）
        # 0 → -3 半音, 100 → 中心, 200 → +3 半音
        ratio = value / 200.0
        midi_adj = self._slider_midi_min + ratio * (self._slider_midi_max - self._slider_midi_min)
        self._adjusted_t4 = _midi_to_hz(midi_adj)

        note = _hz_to_note_name(self._adjusted_t4)
        if abs(value - 100) < 2:
            self._adjusted_value_label.setText(f"{note}  ({self._adjusted_t4:.0f} Hz)  ← 自动检测值")
            self._adjusted_value_label.setStyleSheet(
                "color: #E6EDF3; font-size: 16px; font-weight: bold; background: transparent;"
            )
        else:
            delta_semitones = _hz_to_midi(self._adjusted_t4) - _hz_to_midi(self._detected_t4)
            direction = "+" if delta_semitones > 0 else ""
            self._adjusted_value_label.setText(
                f"{note}  ({self._adjusted_t4:.0f} Hz)  "
                f"[{direction}{delta_semitones:.1f} 半音]"
            )
            self._adjusted_value_label.setStyleSheet(
                "color: #D29922; font-size: 16px; font-weight: bold; background: transparent;"
            )

        # 更新钢琴键盘
        self._piano_widget.set_t4(self._adjusted_t4)
        self._update_voice_type_hint()

    def _on_select_candidate(self, flat_index: int) -> None:
        """选择候选点（自动或手动）作为当前换声点 — 置信度跟随该候选点变化"""
        all_cands = self._all_candidates_flat()
        if flat_index < 0 or flat_index >= len(all_cands):
            return
        cand = all_cands[flat_index]
        self._detected_t4 = cand['freq']

        fusion = cand.get('fusion_score', 0.0)

        # ── 基于该候选点的融合分数重新计算置信度 ──
        if cand['source'] == 'manual' and fusion < 0.01:
            # 手动选取但没有特征数据 → 用户确认 = 较高置信度
            self._detection_confidence = 0.88
        else:
            # 将融合分数映射到 0.15~0.92 的置信度区间
            # 高融合分 (>0.5) → 高置信度 (>0.75)
            # 中融合分 (0.2~0.5) → 中置信度 (0.40~0.75)
            # 低融合分 (<0.2) → 低置信度 (<0.40)
            mapped_conf = float(np.clip(fusion * 1.35 + 0.10, 0.15, 0.92))
            self._detection_confidence = mapped_conf

            # 如果是手动选取且有特征数据 → 额外加成 (用户视觉确认)
            if cand['source'] == 'manual':
                self._detection_confidence = min(self._detection_confidence + 0.08, 0.95)

        self._adjusted_t4 = self._detected_t4
        self._update_validate_page()

    def _on_playback(self) -> None:
        """试听录音回放"""
        if not HAS_SOUNDDEVICE:
            self._show_error("sounddevice 未安装，无法回放")
            return

        audio = self._full_audio
        if audio is None and self._temp_audio_file and os.path.exists(self._temp_audio_file):
            try:
                import wave
                with wave.open(self._temp_audio_file, 'rb') as wf:
                    n_frames = wf.getnframes()
                    audio = np.frombuffer(wf.readframes(n_frames), dtype=np.int16).astype(np.float32) / 32767.0
            except Exception:
                pass

        if audio is None or len(audio) == 0:
            self._show_error("没有可回放的录音数据")
            return

        try:
            sd.play(audio, SAMPLE_RATE)
            sd.wait()
        except Exception as e:
            self._show_error(f"回放失败:\n{e}")

    def _preview_passaggio_audio(self, target_hz: float) -> None:
        """截取换声点附近 0.5 秒录音片段并播放"""
        if not HAS_SOUNDDEVICE:
            return
        audio = self._full_audio
        pitch_track = self._pitch_track
        if audio is None or len(audio) == 0:
            QMessageBox.information(self, "试听不可用", "没有找到录音数据。")
            return
        if not pitch_track:
            QMessageBox.information(self, "试听不可用", "没有音高轨迹数据。")
            return

        # 找最接近目标频率的时间点
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
            QMessageBox.information(
                self, "试听不可用",
                f"录音中未找到接近 {note} ({target_hz:.0f}Hz) 的片段。\n"
                f"最近匹配偏差 {best_dist:.0f} Hz。"
            )
            return

        # 截取 ±0.25 秒
        half_window = 0.25
        sr = SAMPLE_RATE
        center_sample = int(best_time * sr)
        start_sample = max(0, center_sample - int(half_window * sr))
        end_sample = min(len(audio), center_sample + int(half_window * sr))
        segment = audio[start_sample:end_sample]

        if len(segment) < int(0.1 * sr):
            return

        # 淡入淡出
        fade_len = min(int(0.01 * sr), len(segment) // 4)
        if fade_len > 1:
            fade_in = np.linspace(0, 1, fade_len)
            fade_out = np.linspace(1, 0, fade_len)
            if segment.ndim > 1:
                segment[:fade_len] = (segment[:fade_len].T * fade_in).T
                segment[-fade_len:] = (segment[-fade_len:].T * fade_out).T
            else:
                segment[:fade_len] = segment[:fade_len] * fade_in
                segment[-fade_len:] = segment[-fade_len:] * fade_out

        # 归一化
        peak = max(np.max(np.abs(segment)), 0.001)
        segment = segment / peak * 0.7

        try:
            sd.play(segment.astype(np.float32) if segment.ndim == 1 else segment.astype(np.float32), sr)
        except Exception as exc:
            print(f"⚠️ 试听播放失败: {exc}")

    def _on_piano_passaggio_selected(self, hz: float) -> None:
        """钢琴/画布选取换声点回调 → 加入候选列表并设为当前 T4"""
        # 添加为手动候选（去重，同时查询特征评分）
        added = self._add_manual_candidate(hz)
        # 设为当前换声点
        self._adjusted_t4 = hz
        self._detected_t4 = hz
        # 基于实际特征评分设定置信度
        if added:
            cand = self._manual_candidates[-1] if self._manual_candidates else None
            fusion = cand.get('fusion_score', 0.0) if cand else 0.0
            if fusion > 0.01:
                self._detection_confidence = float(np.clip(fusion * 1.35 + 0.18, 0.20, 0.95))
            else:
                self._detection_confidence = 0.88
        note = _hz_to_note_name(hz)
        self._detected_t4_label.setText(f"{note} ({hz:.0f} Hz) — 手动选取")
        self._update_validate_page()

    def _preview_candidate_audio(self, flat_index: int) -> None:
        """试听候选换声点附近的录音片段 (自动或手动)"""
        all_cands = self._all_candidates_flat()
        if flat_index < 0 or flat_index >= len(all_cands):
            return
        self._preview_passaggio_audio(all_cands[flat_index]['freq'])

    def _on_retry(self) -> None:
        """重新校准"""
        reply = QMessageBox.question(
            self, "重新校准",
            "确定要放弃当前检测结果并重新录制吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            # 清理临时文件
            if self._temp_audio_file and os.path.exists(self._temp_audio_file):
                try:
                    os.unlink(self._temp_audio_file)
                except Exception:
                    pass
            self._temp_audio_file = None
            self._full_audio = None
            self._switch_phase(self.PHASE_GUIDE)

    # ═══════════════════════════════════════════════════════════
    # 保存校准结果
    # ═══════════════════════════════════════════════════════════

    def _save_calibration(self) -> None:
        """保存校准结果到 profile"""
        t4 = self._adjusted_t4 if self._adjusted_t4 > 0 else self._detected_t4
        if t4 <= 0:
            self._show_error("未检测到换声点，无法保存")
            return

        conf = self._detection_confidence
        # 如果用户手动微调过，提升置信度
        if abs(self._adjusted_t4 - self._detected_t4) > 0.01:
            conf = max(conf, 0.85)  # 手动确认视为高置信度

        # 更新 PassaggioData
        today = time.strftime("%Y-%m-%d")
        pp = self._profile.passaggio

        # 保存之前的自动估计值
        if pp.t4_hz > 0 and pp.source == "auto_estimated":
            pp.auto_estimated_t4 = pp.t4_hz

        pp.t4_hz = t4
        pp.source = "calibrated"
        pp.confidence = conf
        pp.last_calibrated = today
        pp.calibration_scan_file = ""

        # 保存临时音频文件到 profile 目录
        if self._temp_audio_file and os.path.exists(self._temp_audio_file):
            try:
                import shutil
                profile_dir = self._mgr.profile_folder_path(self._profile.id)
                if profile_dir is not None:
                    profile_dir = str(profile_dir)
                    os.makedirs(profile_dir, exist_ok=True)
                    dest = os.path.join(profile_dir, "calibration_audio.wav")
                    shutil.copy2(self._temp_audio_file, dest)
                    pp.calibration_scan_file = "calibration_audio.wav"
            except Exception:
                pass

        # 持久化
        try:
            self._mgr.save_profile(self._profile)
        except Exception as e:
            self._show_error(f"保存失败:\n{e}")
            return

        # 清理临时文件
        if self._temp_audio_file and os.path.exists(self._temp_audio_file):
            try:
                os.unlink(self._temp_audio_file)
            except Exception:
                pass

        self.calibration_saved.emit(self._profile.id)
        self.accept()

    # ═══════════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════════

    def _section_divider(self) -> QFrame:
        """区块分割线"""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("QFrame { background-color: #21262D; max-height: 1px; border: none; }")
        return line

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "错误", message)

    def closeEvent(self, event) -> None:
        """关闭时清理资源"""
        if self._is_recording:
            self._stop_recording(abort=True)
        if self._temp_audio_file and os.path.exists(self._temp_audio_file):
            try:
                os.unlink(self._temp_audio_file)
            except Exception:
                pass
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════
# 自定义控件
# ═══════════════════════════════════════════════════════════════

class _PassaggioCanvas(QWidget):
    """增强版换声点检测画布 — 实时音高轨迹 + 换声参考区 + 梯度着色

    视觉特征:
      - 对数 Y 轴带音名网格（C3-C6）
      - 换声点参考区域半透明高亮
      - 轨迹颜色梯度: 绿色(胸声区) → 金色(换声区) → 蓝色(头声区)
      - 实时音高数字叠加
      - 左下角音名标签

    查找父级 PassaggioCalibrationDialog 获取实时数据的方法:
      getattr(self, '_get_context', None)  → 返回 dict 或 None
    """

    # 参考网格音名和频率
    _GRID_NOTES = [
        ("C3", 130.8), ("E3", 164.8), ("G3", 196.0),
        ("C4", 261.6), ("E4", 329.6), ("G4", 392.0),
        ("C5", 523.3), ("E5", 659.3), ("G5", 784.0), ("C6", 1046.5),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setStyleSheet("background: #0D1117; border: 1px solid #21262D; border-radius: 8px;")
        self._points: Deque[Tuple[float, float]] = deque(maxlen=600)
        self._current_freq: float = 0.0
        self._expected_t4: float = 0.0
        self._passaggio_lo: float = 0.0
        self._passaggio_hi: float = 0.0
        self._is_female: bool = False
        self._last_region: str = ""

    def set_expected_t4(self, hz: float, is_female: bool = False) -> None:
        self._expected_t4 = hz
        self._is_female = is_female
        # 换声区范围: ±2 半音
        if hz > 0:
            self._passaggio_lo = hz / (2 ** (2.0 / 12))
            self._passaggio_hi = hz * (2 ** (2.0 / 12))

    def add_point(self, elapsed: float, freq_hz: float) -> None:
        self._points.append((elapsed, freq_hz))
        self._current_freq = freq_hz
        self.update()

    def set_region(self, region: str) -> None:
        self._last_region = region

    def clear(self) -> None:
        self._points.clear()
        self._current_freq = 0.0
        self.update()

    def _freq_to_y(self, f: float, plot_h: float, margin_top: float) -> float:
        """频率 → Y 坐标 (log, C3-C6)"""
        if f <= 0:
            return margin_top + plot_h
        log_f = math.log2(max(f, 65.4))  # C2
        log_min = math.log2(65.4)
        log_max = math.log2(1046.5)  # C6
        ratio = (log_f - log_min) / (log_max - log_min)
        return margin_top + plot_h * (1.0 - max(0.0, min(1.0, ratio)))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        ml, mr, mt, mb = 56, 16, 14, 28
        plot_w = w - ml - mr
        plot_h = h - mt - mb
        if plot_w <= 0 or plot_h <= 0:
            painter.end()
            return

        # ── 背景填充 ──
        painter.fillRect(0, 0, w, h, QColor("#0D1117"))

        # ── 换声区参考带 ──
        if self._passaggio_lo > 0 and self._passaggio_hi > 0:
            y_lo = self._freq_to_y(self._passaggio_lo, plot_h, mt)
            y_hi = self._freq_to_y(self._passaggio_hi, plot_h, mt)
            zone_y = min(y_lo, y_hi)
            zone_h = abs(y_hi - y_lo)
            painter.fillRect(
                ml, int(zone_y), plot_w, int(zone_h),
                QColor(210, 153, 34, 25)  # 金色半透明
            )
            # 标签
            painter.setPen(QColor(210, 153, 34, 100))
            font_s = painter.font()
            font_s.setPixelSize(9)
            painter.setFont(font_s)
            painter.drawText(ml + 4, int(zone_y) + 14, "换声区预期范围")

        # ── 网格线 + 音名标签 ──
        font_grid = painter.font()
        font_grid.setPixelSize(9)
        painter.setFont(font_grid)
        for note_name, hz in self._GRID_NOTES:
            y = self._freq_to_y(hz, plot_h, mt)
            if mt <= y <= mt + plot_h:
                painter.setPen(QPen(QColor(22, 27, 34), 1))
                painter.drawLine(ml, int(y), ml + plot_w, int(y))
                painter.setPen(QColor("#30363D"))
                painter.drawText(2, int(y) + 4, note_name)

        # ── 垂直时间网格 ──
        for i in range(5):
            x = ml + plot_w * i // 4
            painter.setPen(QPen(QColor(22, 27, 34), 1))
            painter.drawLine(int(x), mt, int(x), mt + plot_h)

        # ── 音高轨迹 ──
        if self._points:
            now = self._points[-1][0]
            window_start = max(0, now - DISPLAY_HISTORY_SECS)

            # 分段构建路径（根据换声区域着色）
            segments = []  # [(color, QPainterPath)]
            current_path = QPainterPath()
            current_color = QColor("#58A6FF")
            first_in_path = True

            for t, f in self._points:
                if t < window_start:
                    continue
                x = ml + plot_w * (t - window_start) / DISPLAY_HISTORY_SECS
                y = self._freq_to_y(f, plot_h, mt)

                # 确定点颜色
                if f <= 0:
                    color = QColor("#484F58")
                elif self._passaggio_lo > 0 and self._passaggio_lo <= f <= self._passaggio_hi:
                    color = QColor("#D29922")  # 金色 = 换声区
                elif self._expected_t4 > 0 and f < self._expected_t4:
                    color = QColor("#3FB950")  # 绿色 = 胸声区
                else:
                    color = QColor("#58A6FF")  # 蓝色 = 头声区

                if color != current_color:
                    if not first_in_path:
                        segments.append((current_color, current_path))
                    current_path = QPainterPath()
                    current_color = color
                    first_in_path = True

                if first_in_path:
                    current_path.moveTo(x, y)
                    first_in_path = False
                else:
                    current_path.lineTo(x, y)

            if not first_in_path:
                segments.append((current_color, current_path))

            # 绘制各段
            for seg_color, seg_path in segments:
                # 发光层
                glow = QPen(QColor(seg_color.red(), seg_color.green(), seg_color.blue(), 50), 4)
                glow.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(glow)
                painter.drawPath(seg_path)

                # 主线
                main = QPen(seg_color, 2)
                main.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(main)
                painter.drawPath(seg_path)

        # ── 当前音高指示点 ──
        if self._current_freq > 0:
            now = self._points[-1][0] if self._points else 0
            x = ml + plot_w
            y = self._freq_to_y(self._current_freq, plot_h, mt)
            note = _hz_to_note_name(self._current_freq)

            # 亮点
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(QPointF(x, y), 5, 5)
            painter.setBrush(QColor(88, 166, 255, 80))
            painter.drawEllipse(QPointF(x, y), 10, 10)

            # 音名标签
            font_note = painter.font()
            font_note.setPixelSize(12)
            font_note.setBold(True)
            painter.setFont(font_note)
            text = f" {note} ({self._current_freq:.0f}Hz)"
            fm = QFontMetrics(font_note)
            tw = int(fm.horizontalAdvance(text))
            label_bg_x = int(min(x + 16, w - tw - 12))
            painter.fillRect(label_bg_x, int(y) - 10, tw + 8, 20, QColor(13, 17, 23, 220))
            painter.setPen(QColor("#E6EDF3"))
            painter.drawText(label_bg_x + 4, int(y) + 5, text)

        # ── 时间轴标签 ──
        font_time = painter.font()
        font_time.setPixelSize(9)
        painter.setFont(font_time)
        painter.setPen(QColor("#484F58"))
        painter.drawText(ml, h - 4, f"-{DISPLAY_HISTORY_SECS}s")
        painter.drawText(w - mr - 20, h - 4, "0s")

        # ── 图例 ──
        legend_x = w - mr - 180
        legend_y = mt + 4
        for label, color in [("胸声区", "#3FB950"), ("换声区", "#D29922"), ("头声区", "#58A6FF")]:
            painter.setPen(QColor(color))
            painter.drawText(legend_x, legend_y, f"● {label}")
            legend_y += 14

        painter.end()


class _ValidatePitchCanvas(QWidget):
    """校验页音高轨迹画布 — 全量回放 + 候选点标记 + 悬停高亮 + 点击选取换声点

    显示完整录音音高轨迹，标记 top-3 候选点和当前 T4，
    鼠标悬停显示音高，点击选取换声点。
    """

    _GRID_NOTES = [
        ("C3", 130.8), ("E3", 164.8), ("G3", 196.0),
        ("C4", 261.6), ("E4", 329.6), ("G4", 392.0),
        ("C5", 523.3), ("E5", 659.3), ("G5", 784.0), ("C6", 1046.5),
    ]

    passaggio_selected = pyqtSignal(float)  # 用户点击选取的 Hz

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setStyleSheet("background: #0D1117; border: 1px solid #21262D; border-radius: 8px;")
        self._pitch_data: List[Tuple[float, float]] = []    # [(t, hz), ...]
        self._candidates: List[dict] = []                   # freq markers
        self._t4_hz: float = 0.0
        self._hovered_t: float = -1.0
        self._hovered_hz: float = 0.0
        self._hovered_x: float = 0.0
        self._hovered_y: float = 0.0

    def set_data(self, pitch_data: List[Tuple[float, float]], candidates: List[dict],
                 t4_hz: float) -> None:
        self._pitch_data = pitch_data
        self._candidates = candidates
        self._t4_hz = t4_hz
        self.update()

    def _freq_to_y(self, f: float, plot_h: float, margin_top: float) -> float:
        if f <= 0:
            return margin_top + plot_h
        log_f = math.log2(max(f, 65.4))
        log_min = math.log2(65.4)
        log_max = math.log2(1046.5)
        ratio = (log_f - log_min) / (log_max - log_min)
        return margin_top + plot_h * (1.0 - max(0.0, min(1.0, ratio)))

    def _y_to_freq(self, y: float, plot_h: float, margin_top: float) -> float:
        ratio = 1.0 - max(0.0, min(1.0, (y - margin_top) / plot_h))
        log_min = math.log2(65.4)
        log_max = math.log2(1046.5)
        return 2 ** (log_min + ratio * (log_max - log_min))

    def mouseMoveEvent(self, event) -> None:
        w, h = self.width(), self.height()
        ml, mr, mt, mb = 56, 16, 14, 28
        plot_w = w - ml - mr
        plot_h = h - mt - mb
        if plot_w <= 0 or plot_h <= 0:
            return
        px, py = event.position().x(), event.position().y()

        if not (ml <= px <= ml + plot_w and mt <= py <= mt + plot_h):
            self._hovered_t = -1.0
            self.update()
            return

        # 查找最近的数据点
        if not self._pitch_data:
            return
        data_start = self._pitch_data[0][0]
        data_end = self._pitch_data[-1][0]
        dur = data_end - data_start
        if dur <= 0:
            dur = 1.0
        ratio = (px - ml) / plot_w
        hover_t = data_start + ratio * dur

        best_dist = float('inf')
        best_hz = 0.0
        best_t = hover_t
        for t, f in self._pitch_data:
            if f <= 0:
                continue
            dist = abs(t - hover_t)
            if dist < best_dist:
                best_dist = dist
                best_hz = f
                best_t = t

        if best_dist < dur * 0.05 and best_hz > 0:  # within ~5% of total duration
            self._hovered_t = best_t
            self._hovered_hz = best_hz
            # X 坐标从匹配到的时间点反算，确保高亮对准数据位置
            self._hovered_x = ml + plot_w * (best_t - data_start) / dur
            self._hovered_y = self._freq_to_y(best_hz, plot_h, mt)
        else:
            self._hovered_t = -1.0
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered_t = -1.0
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._hovered_t < 0 or self._hovered_hz <= 0:
            return
        note = _hz_to_note_name(self._hovered_hz)
        # 自定义样式确保高对比度可读
        msg = QMessageBox(self)
        msg.setWindowTitle("选择换声点")
        msg.setText(
            f"是否将换声点设置为曲线上\n"
            f"<b style='color:#FFD54F;'>{note} ({self._hovered_hz:.0f} Hz)</b> 的位置？"
        )
        msg.setInformativeText(f"录音时间: {self._hovered_t:.1f}s")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #161B22; color: #E6EDF3;
            }
            QMessageBox QLabel {
                color: #E6EDF3; font-size: 13px; background: transparent;
            }
            QPushButton {
                background: #21262D; color: #E6EDF3; border: 1px solid #30363D;
                border-radius: 6px; padding: 6px 20px; font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover { background: #30363D; border-color: #58A6FF; }
        """)
        reply = msg.exec()
        if reply == QMessageBox.StandardButton.Yes:
            self.passaggio_selected.emit(self._hovered_hz)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        ml, mr, mt, mb = 56, 16, 14, 28
        plot_w = w - ml - mr
        plot_h = h - mt - mb
        if plot_w <= 0 or plot_h <= 0:
            painter.end()
            return

        painter.fillRect(0, 0, w, h, QColor("#0D1117"))

        # ── 确定绘图数据范围 ──
        data_start = 0.0
        data_end = 1.0
        dur = 1.0
        if self._pitch_data:
            data_start = self._pitch_data[0][0]
            data_end = self._pitch_data[-1][0]
            dur = data_end - data_start
            if dur <= 0:
                dur = 1.0

        # ── 换声区半透明带 (T4 ± 2 半音) ──
        if self._t4_hz > 0:
            zone_lo = self._t4_hz / (2 ** (3.0 / 12))
            zone_hi = self._t4_hz * (2 ** (3.0 / 12))
            y_lo = self._freq_to_y(zone_lo, plot_h, mt)
            y_hi = self._freq_to_y(zone_hi, plot_h, mt)
            painter.fillRect(
                int(ml), int(min(y_lo, y_hi)),
                int(plot_w), int(abs(y_hi - y_lo)),
                QColor(210, 153, 34, 18)
            )

        # ── 水平网格 ──
        font_grid = painter.font()
        font_grid.setPixelSize(9)
        painter.setFont(font_grid)
        for note_name, hz in self._GRID_NOTES:
            y = self._freq_to_y(hz, plot_h, mt)
            if mt <= y <= mt + plot_h:
                painter.setPen(QPen(QColor(22, 27, 34), 1))
                painter.drawLine(ml, int(y), ml + plot_w, int(y))
                # 音名标签加半透明底色增强可读性
                fm = QFontMetrics(font_grid)
                label_w = fm.horizontalAdvance(note_name)
                painter.fillRect(0, int(y) - 2, int(label_w) + 6, 12, QColor(13, 17, 23, 180))
                painter.setPen(QColor("#484F58"))
                painter.drawText(3, int(y) + 4, note_name)

        # ── 垂直时间网格 (每 25%) ──
        for pct in [0.25, 0.5, 0.75]:
            gx = ml + int(plot_w * pct)
            painter.setPen(QPen(QColor(22, 27, 34), 1, Qt.PenStyle.DotLine))
            painter.drawLine(gx, mt, gx, mt + plot_h)

        # ── 音高轨迹 (分区着色: 绿色胸声 → 金色换声 → 蓝色头声) ──
        if self._pitch_data and dur > 0:
            segments = []
            current_path = QPainterPath()
            current_color = QColor("#58A6FF")
            first_pt = True

            for t, f in self._pitch_data:
                if f <= 0:
                    continue
                x = ml + plot_w * (t - data_start) / dur
                y = self._freq_to_y(f, plot_h, mt)

                # 确定颜色
                if self._t4_hz > 0:
                    if f < self._t4_hz * 0.85:
                        color = QColor("#3FB950")   # 胸声区 绿色
                    elif f < self._t4_hz * 1.15:
                        color = QColor("#D29922")   # 换声区 金色
                    else:
                        color = QColor("#58A6FF")   # 头声区 蓝色
                else:
                    color = QColor("#58A6FF")

                if color != current_color:
                    if not first_pt:
                        segments.append((current_color, current_path))
                    current_path = QPainterPath()
                    current_color = color
                    first_pt = True

                if first_pt:
                    current_path.moveTo(x, y)
                    first_pt = False
                else:
                    current_path.lineTo(x, y)

            if not first_pt:
                segments.append((current_color, current_path))

            for seg_color, seg_path in segments:
                glow = QPen(QColor(seg_color.red(), seg_color.green(), seg_color.blue(), 35), 4)
                glow.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(glow)
                painter.drawPath(seg_path)
                main = QPen(seg_color, 1.8)
                main.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(main)
                painter.drawPath(seg_path)

        # ── T4 水平参考线 ──
        if self._t4_hz > 0:
            y_t4 = self._freq_to_y(self._t4_hz, plot_h, mt)
            painter.setPen(QPen(QColor(255, 213, 79, 140), 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(ml, int(y_t4), ml + plot_w, int(y_t4))
            t4_note = _hz_to_note_name(self._t4_hz)
            font_l = painter.font()
            font_l.setPixelSize(10)
            font_l.setBold(True)
            painter.setFont(font_l)
            label = f"T4: {t4_note} ({self._t4_hz:.0f}Hz)"
            fm_l = QFontMetrics(font_l)
            lw = int(fm_l.horizontalAdvance(label))
            painter.fillRect(ml + 2, int(y_t4) - 16, lw + 8, 16, QColor(13, 17, 23, 210))
            painter.setPen(QColor("#FFD54F"))
            painter.drawText(ml + 6, int(y_t4) - 3, label)

        # ── 候选点标记 (自动 + 手动) ──
        candidate_entries = []  # [(hz, time, score, source), ...]
        for c in self._candidates:
            c_hz = c['freq']
            best_t = 0.0
            best_d = float('inf')
            for t, f in self._pitch_data:
                if f <= 0:
                    continue
                d = abs(f - c_hz)
                if d < best_d:
                    best_d = d
                    best_t = t
            if best_d < c_hz * 0.3 and dur > 0:
                is_auto = c.get('source', 'auto') == 'auto'
                candidate_entries.append((c_hz, best_t, c.get('fusion_score', 0), 'auto' if is_auto else 'manual'))

        # 按分数排序，自动候选优先
        candidate_entries.sort(key=lambda x: (0 if x[3] == 'auto' else 1, -x[2]))

        for rank, (c_hz, ct, cscore, source) in enumerate(candidate_entries):
            cx = ml + plot_w * (ct - data_start) / dur
            cy = self._freq_to_y(c_hz, plot_h, mt)
            note = _hz_to_note_name(c_hz)

            if source == 'manual':
                # 手动选取: 菱形标记
                marker_color = QColor("#E040FB")  # 紫色
                radius = 5
                # 绘制菱形
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(marker_color)
                diamond = QPainterPath()
                diamond.moveTo(cx, cy - radius)
                diamond.lineTo(cx + radius, cy)
                diamond.lineTo(cx, cy + radius)
                diamond.lineTo(cx - radius, cy)
                diamond.closeSubpath()
                painter.drawPath(diamond)
                painter.setBrush(QColor(marker_color.red(), marker_color.green(), marker_color.blue(), 35))
                diamond2 = QPainterPath()
                diamond2.moveTo(cx, cy - radius - 4)
                diamond2.lineTo(cx + radius + 4, cy)
                diamond2.lineTo(cx, cy + radius + 4)
                diamond2.lineTo(cx - radius - 4, cy)
                diamond2.closeSubpath()
                painter.drawPath(diamond2)
                prefix = "✋ "
            elif rank == 0:
                marker_color = QColor("#FFD54F")  # 金色 = 首选
                radius = 7
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(marker_color)
                painter.drawEllipse(QPointF(cx, cy), radius, radius)
                painter.setBrush(QColor(marker_color.red(), marker_color.green(), marker_color.blue(), 40))
                painter.drawEllipse(QPointF(cx, cy), radius + 5, radius + 5)
                prefix = ""
            else:
                marker_color = QColor(88, 166, 255, 160)  # 蓝色 = 备选
                radius = 5
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(marker_color)
                painter.drawEllipse(QPointF(cx, cy), radius, radius)
                painter.setBrush(QColor(marker_color.red(), marker_color.green(), marker_color.blue(), 40))
                painter.drawEllipse(QPointF(cx, cy), radius + 5, radius + 5)
                prefix = ""

            font_m = painter.font()
            font_m.setPixelSize(10)
            font_m.setBold(rank == 0)
            painter.setFont(font_m)
            label = f"{prefix}#{rank + 1} {note}"
            fm = QFontMetrics(font_m)
            tw = int(fm.horizontalAdvance(label))
            lx = int(min(cx + 12, w - tw - 8))
            ly = int(cy - 8)
            painter.fillRect(lx - 2, ly - 2, tw + 8, 16, QColor(13, 17, 23, 210))
            painter.setPen(marker_color)
            painter.drawText(lx + 2, ly + 10, label)

        # ── 悬停高亮 ──
        if self._hovered_t >= 0 and self._hovered_hz > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(88, 166, 255, 60))
            painter.drawEllipse(QPointF(self._hovered_x, self._hovered_y), 12, 12)
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(QPointF(self._hovered_x, self._hovered_y), 4, 4)

            note = _hz_to_note_name(self._hovered_hz)
            font_h = painter.font()
            font_h.setPixelSize(11)
            font_h.setBold(True)
            painter.setFont(font_h)
            hover_text = f"{note} ({self._hovered_hz:.0f}Hz) — 点击选取"
            fm = QFontMetrics(font_h)
            tw = int(fm.horizontalAdvance(hover_text))
            lx = int(min(self._hovered_x + 14, w - tw - 8))
            ly = max(4, int(self._hovered_y) - 30)
            painter.fillRect(lx - 4, ly - 2, tw + 12, 20, QColor(13, 17, 23, 230))
            painter.setPen(QColor("#58A6FF"))
            painter.drawText(lx, ly + 13, hover_text)

        # ── 底部: 时间轴 + 图例 ──
        painter.setPen(QColor("#484F58"))
        font_b = painter.font()
        font_b.setPixelSize(9)
        painter.setFont(font_b)
        if dur > 0:
            painter.drawText(ml, h - 14, f"0s")
            painter.drawText(ml + plot_w - 20, h - 14, f"{dur:.1f}s")
        # 图例
        legend_x = w - mr - 210
        legend_y = mt + 4
        for label, color_hex in [("胸声区", "#3FB950"), ("换声区", "#D29922"), ("头声区", "#58A6FF")]:
            painter.setPen(QColor(color_hex))
            painter.drawText(legend_x, legend_y, f"● {label}")
            legend_y += 14
        # 底部提示
        painter.setPen(QColor("#484F58"))
        painter.drawText(ml, h - 2, "悬停查看　点击选取换声点　候选点已标注")

        painter.end()


class _IndicatorBar(QWidget):
    """实时指标条"""

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = color
        self._value = 0.0
        self.setFixedHeight(12)
        self.setStyleSheet("background: #0D1117; border-radius: 4px;")

    def set_value(self, v: float) -> None:
        self._value = float(np.clip(v, 0.0, 1.0))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        w, h = self.width(), self.height()

        # 背景
        painter.fillRect(0, 0, w, h, QColor("#0D1117"))

        # 填充
        fill_w = int(w * self._value)
        if fill_w > 0:
            gradient = QLinearGradient(0, 0, w, 0)
            c = self._color
            gradient.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 200))
            gradient.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 120))
            painter.fillRect(0, 0, fill_w, h, QBrush(gradient))

        # 边框
        painter.setPen(QPen(QColor("#21262D"), 1))
        painter.drawRoundedRect(0, 0, w - 1, h - 1, 4, 4)
        painter.end()


class _PianoKeyboardWidget(QWidget):
    """钢琴键盘可视化 — 点击试听 + 右键选择换声点 + 悬停高亮"""

    WHITE_KEYS = [0, 2, 4, 5, 7, 9, 11]  # MIDI note % 12
    BLACK_KEYS = [1, 3, 6, 8, 10]

    passaggio_selected = pyqtSignal(float)  # 发送 Hz

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t4_hz: float = 0.0
        self._midi_min = 48   # C3
        self._midi_max = 84   # C6
        self._clicked_midi: int = -1
        self._hovered_midi: int = -1
        self._click_fade_timer: Optional[QTimer] = None
        self.setMinimumHeight(70)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setStyleSheet("background: #0D1117; border-radius: 6px;")
        self._hover_label: Optional[QLabel] = None

    def set_t4(self, hz: float) -> None:
        self._t4_hz = hz
        self.update()

    def clear(self) -> None:
        self._t4_hz = 0.0
        self.update()

    def scroll_by_half(self, direction: int) -> None:
        """向左(-1)或向右(+1)滚动半个可见范围"""
        span = self._midi_max - self._midi_min
        shift = max(1, span // 2) * direction
        new_min = max(21, self._midi_min + shift)   # A0 = MIDI 21
        new_max = min(108, self._midi_max + shift)   # C8 = MIDI 108
        if new_max - new_min < 12:  # 至少保留 1 个八度
            return
        self._midi_min = new_min
        self._midi_max = new_max
        self.update()

    def _pixel_to_midi(self, px: float, py: float) -> int:
        w, h = self.width(), self.height()
        n_white = 0
        for midi in range(self._midi_min, self._midi_max + 1):
            if midi % 12 in self.WHITE_KEYS:
                n_white += 1
        if n_white == 0:
            return -1
        white_w = w / n_white
        key_h = h - 4
        black_w = white_w * 0.6
        black_h = key_h * 0.58

        # Build white key positions
        white_idx = 0
        white_x_map = {}
        for midi in range(self._midi_min, self._midi_max + 1):
            if midi % 12 in self.WHITE_KEYS:
                white_x_map[midi] = (white_idx * white_w + 1, white_w - 2)
                white_idx += 1

        # Check black keys first
        if py <= black_h:
            for midi in range(self._midi_min, self._midi_max + 1):
                if midi % 12 in self.BLACK_KEYS:
                    prev_white = midi - 1
                    if prev_white in white_x_map:
                        wx, ww = white_x_map[prev_white]
                        bx = wx + ww - black_w / 2
                        if bx <= px <= bx + black_w:
                            return midi

        # Check white keys
        for midi, (wx, ww) in white_x_map.items():
            if wx <= px <= wx + ww:
                return midi
        return -1

    @staticmethod
    def _play_tone(midi: int) -> None:
        """模拟电子钢琴音色 — 真实钢琴谐波结构 + ADSR包络 + 击弦瞬态

        基于真实钢琴频谱分析:
          - 基频最强，2次谐波约 -6dB，3次约 -10dB，逐次衰减
          - 轻微不谐和性 (inharmonicity): 高次谐波频率略微偏高
          - 快速起音 (2ms) + 双阶段衰减 (琴槌反弹 → 琴弦能量散失)
          - 锤击噪声瞬态模拟琴槌敲击琴弦
          - 轻微震音效果模拟电钢琴扬声器特性
        """
        if not HAS_SOUNDDEVICE:
            return
        freq = 440.0 * 2 ** ((midi - 69) / 12.0)
        sr = 44100
        duration = 1.2
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        # ── 钢琴谐波结构 (幅值基于真实钢琴频谱归一化) ──
        # (谐波次数, 相对幅值, 不谐和偏离/cent)
        harmonics = [
            (1,  1.000, 0.00),   # 基频
            (2,  0.520, 0.06),   # 2次谐波
            (3,  0.300, 0.15),   # 3次
            (4,  0.165, 0.28),   # 4次
            (5,  0.088, 0.50),   # 5次
            (6,  0.046, 0.78),   # 6次
            (7,  0.023, 1.10),   # 7次
            (8,  0.011, 1.50),   # 8次
            (9,  0.005, 1.95),   # 9次
        ]

        tone = np.zeros_like(t)
        for k, amp, detune_cents in harmonics:
            # 真实钢琴的不谐和性: 高次谐波略高于理论频率
            detune_factor = 1.0 + detune_cents * 0.00055
            harmonic_freq = freq * k * detune_factor
            # 相位随机化避免所有谐波同相 (减少"蜂鸣"感)
            phase = (k * 0.37 * np.pi) % (2 * np.pi)
            tone += amp * np.sin(2 * np.pi * harmonic_freq * t + phase)

        # ── 锤击瞬态噪声 (钢琴琴槌敲击琴弦的高频成分) ──
        noise_len = int(sr * 0.010)  # 10ms
        noise = np.random.randn(noise_len)
        # 高频强调: 对噪声做高通效果
        noise_hp = np.zeros(noise_len)
        if noise_len > 2:
            noise_hp[1:] = noise[1:] - 0.7 * noise[:-1]
            noise_hp[0] = noise[0]
        else:
            noise_hp = noise
        # 噪声包络: 极快速衰减
        hammer_env = np.exp(-np.arange(noise_len) / (sr * 0.0035))
        hammer_noise = noise_hp * hammer_env * 0.18

        # ── ADSR 钢琴包络 ──
        att = int(sr * 0.002)        # 2ms 起音
        d1  = int(sr * 0.13)         # 130ms 第一阶段衰减 (琴槌反弹)
        d2  = int(sr * 0.55)         # 550ms 第二阶段衰减 (弦能散失)
        sus_len = max(0, len(t) - att - d1 - d2)

        env = np.concatenate([
            np.linspace(0, 1.0, att),                # 快速起音
            np.linspace(1.0, 0.38, d1),              # 第一阶段衰减
            np.linspace(0.38, 0.05, d2),             # 第二阶段衰减
            np.ones(sus_len) * 0.05,                 # 尾部持音
        ])[:len(t)]

        # ── 混合 ──
        hammer_signal = np.zeros_like(t)
        hammer_signal[:noise_len] = hammer_noise[:noise_len]
        mixed = tone * env + hammer_signal * 0.55

        # ── 轻柔震音 (电钢琴特征) ──
        trem_rate = 5.5  # Hz
        trem_depth = 0.07
        tremolo = 1.0 + trem_depth * np.sin(2 * np.pi * trem_rate * t + 0.3)
        mixed = mixed * tremolo

        # ── 温和峰值限制 ──
        peak = max(np.max(np.abs(mixed)), 0.01)
        mixed = mixed / peak * 0.26

        try:
            sd.play(mixed.astype(np.float32), sr)
        except Exception:
            pass

    def mouseMoveEvent(self, event) -> None:
        midi = self._pixel_to_midi(event.position().x(), event.position().y())
        if midi != self._hovered_midi:
            self._hovered_midi = midi
            self.update()
            self._update_hover_label(event.position().x(), event.position().y(), midi)

    def leaveEvent(self, event) -> None:
        self._hovered_midi = -1
        self.update()
        if self._hover_label is not None:
            self._hover_label.hide()

    def _update_hover_label(self, x, y, midi):
        if midi < 0:
            if self._hover_label:
                self._hover_label.hide()
            return
        note = _hz_to_note_name(440.0 * 2 ** ((midi - 69) / 12.0))
        hz = 440.0 * 2 ** ((midi - 69) / 12.0)
        if self._hover_label is None:
            self._hover_label = QLabel(self)
            self._hover_label.setStyleSheet(
                "background: rgba(22,27,34,0.9); color: #58A6FF; font-size: 10px;"
                "font-weight: bold; padding: 2px 6px; border: 1px solid #58A6FF; border-radius: 4px;"
            )
        self._hover_label.setText(f"{note} ({hz:.0f}Hz) ◄ 右键选择")
        self._hover_label.adjustSize()
        lx = int(x + 14)
        ly = int(y - self._hover_label.height() - 6)
        self._hover_label.move(min(lx, self.width() - self._hover_label.width() - 4), max(ly, 2))
        self._hover_label.show()

    def mousePressEvent(self, event) -> None:
        midi = self._pixel_to_midi(event.position().x(), event.position().y())
        if midi < 0:
            return
        if event.button() == Qt.MouseButton.RightButton:
            hz = 440.0 * 2 ** ((midi - 69) / 12.0)
            note = _hz_to_note_name(hz)
            msg = QMessageBox(self)
            msg.setWindowTitle("选取换声点")
            msg.setText(
                f"是否将换声点设置为键盘上的\n"
                f"<b style='color:#FFD54F;'>{note} ({hz:.0f} Hz)</b>？"
            )
            msg.setInformativeText("该点将被加入候选列表，同时设为当前换声点。")
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setDefaultButton(QMessageBox.StandardButton.Yes)
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #161B22; color: #E6EDF3;
                }
                QMessageBox QLabel {
                    color: #E6EDF3; font-size: 13px; background: transparent;
                }
                QPushButton {
                    background: #21262D; color: #E6EDF3; border: 1px solid #30363D;
                    border-radius: 6px; padding: 6px 20px; font-size: 12px;
                    min-width: 80px;
                }
                QPushButton:hover { background: #30363D; border-color: #58A6FF; }
            """)
            reply = msg.exec()
            if reply == QMessageBox.StandardButton.Yes:
                self.set_t4(hz)
                self.passaggio_selected.emit(hz)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._play_tone(midi)
            self._clicked_midi = midi
            self.update()
            if self._click_fade_timer:
                self._click_fade_timer.stop()
            self._click_fade_timer = QTimer(self)
            self._click_fade_timer.setSingleShot(True)
            self._click_fade_timer.timeout.connect(lambda: (setattr(self, '_clicked_midi', -1), self.update()))
            self._click_fade_timer.start(300)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        n_white = 0
        for midi in range(self._midi_min, self._midi_max + 1):
            if midi % 12 in self.WHITE_KEYS:
                n_white += 1

        if n_white == 0:
            painter.end()
            return

        white_w = w / n_white
        key_h = h - 4
        black_w = white_w * 0.6
        black_h = key_h * 0.58

        t4_midi = int(round(_hz_to_midi(self._t4_hz))) if self._t4_hz > 0 else -1

        # 绘制白键
        white_idx = 0
        white_positions = {}
        for midi in range(self._midi_min, self._midi_max + 1):
            if midi % 12 not in self.WHITE_KEYS:
                continue
            x = white_idx * white_w + 1
            note_name = _NOTE_NAMES[midi % 12]

            is_t4 = (midi == t4_midi)

            if is_t4:
                # 高亮键
                gradient = QLinearGradient(0, 0, 0, key_h)
                gradient.setColorAt(0.0, QColor("#FFD54F"))
                gradient.setColorAt(0.6, QColor("#FFA000"))
                gradient.setColorAt(1.0, QColor("#E65100"))
                painter.fillRect(int(x), 0, int(white_w - 2), int(key_h), QBrush(gradient))
            else:
                painter.fillRect(int(x), 0, int(white_w - 2), int(key_h), QColor("#E8EAED"))

            painter.setPen(QColor("#CCCCCC"))
            painter.drawRect(int(x), 0, int(white_w - 2), int(key_h))

            # C 键标注
            if note_name == "C":
                octave = (midi // 12) - 1
                painter.setPen(QColor("#999999"))
                font = painter.font()
                font.setPixelSize(9)
                painter.setFont(font)
                painter.drawText(int(x) + 3, int(key_h) - 5, f"C{octave}")

            white_positions[midi] = (x, white_w)
            white_idx += 1

        # 绘制黑键
        for midi in range(self._midi_min, self._midi_max + 1):
            if midi % 12 not in self.BLACK_KEYS:
                continue
            # 黑键在两白键之间
            prev_white = midi - 1
            if prev_white % 12 not in self.WHITE_KEYS:
                continue
            if prev_white not in white_positions:
                continue

            wx, ww = white_positions[prev_white]
            bx = wx + ww - black_w / 2

            is_t4 = (midi == t4_midi)

            if is_t4:
                painter.fillRect(int(bx), 0, int(black_w), int(black_h), QColor("#FF6D00"))
            else:
                painter.fillRect(int(bx), 0, int(black_w), int(black_h), QColor("#2D2D2D"))

            painter.setPen(QColor("#555555"))
            painter.drawRect(int(bx), 0, int(black_w), int(black_h))

        # ── 悬停高亮 ──
        hover_midi = self._hovered_midi
        if hover_midi >= 0 and hover_midi != t4_midi:
            if hover_midi % 12 in self.WHITE_KEYS and hover_midi in white_positions:
                hx, hww = white_positions[hover_midi]
                painter.fillRect(int(hx), 0, int(hww), int(key_h), QColor(88, 166, 255, 60))
            elif hover_midi % 12 in self.BLACK_KEYS:
                prev_white = hover_midi - 1
                if prev_white in white_positions:
                    hx, hww = white_positions[prev_white]
                    hbx = hx + hww - black_w / 2
                    painter.fillRect(int(hbx), 0, int(black_w), int(black_h), QColor(88, 166, 255, 80))

        # ── 点击高亮 ──
        click_midi = self._clicked_midi
        if click_midi >= 0 and click_midi != t4_midi:
            if click_midi % 12 in self.WHITE_KEYS and click_midi in white_positions:
                cx, cww = white_positions[click_midi]
                painter.fillRect(int(cx), 0, int(cww), int(key_h), QColor(88, 166, 255, 120))
            elif click_midi % 12 in self.BLACK_KEYS:
                prev_white = click_midi - 1
                if prev_white in white_positions:
                    cx, cww = white_positions[prev_white]
                    cbx = cx + cww - black_w / 2
                    painter.fillRect(int(cbx), 0, int(black_w), int(black_h), QColor(88, 166, 255, 160))

        # T4 标注箭头
        if self._t4_hz > 0:
            t4_note = _hz_to_note_name(self._t4_hz)
            painter.setPen(QColor("#FFD54F"))
            font = painter.font()
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            label = f"▲ T4: {t4_note} ({self._t4_hz:.0f}Hz)"
            fm = QFontMetrics(font)
            text_w = fm.horizontalAdvance(label)
            painter.drawText((w - text_w) // 2, int(key_h) + 16, label)

        painter.end()
