"""练声模式面板 — 练习浏览器 + 可视化 + 伴奏控制 + 评分显示

作为 QWidget 嵌入主窗口，提供练声模式的完整 UI：
  - 顶部: 练习选择器 + 启动/停止按钮 + 容差等级
  - 中部: TrainingVisualizer (钢琴卷帘 + 银色→金色音高线)
  - 底部: 伴奏模式 + 速度/移调 + 实时得分
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

# ── Qt imports ──
try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QComboBox, QSlider, QGroupBox, QGridLayout, QProgressBar,
        QSplitter, QCheckBox, QSpinBox, QDoubleSpinBox,
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal
    from PyQt6.QtGui import QFont, QColor
    QT_VERSION = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QComboBox, QSlider, QGroupBox, QGridLayout, QProgressBar,
        QSplitter, QCheckBox, QSpinBox, QDoubleSpinBox,
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal
    from PyQt5.QtGui import QFont, QColor
    QT_VERSION = 5

from src.vocal_training.scoring import (
    PitchGrade, NoteResult, ExerciseScore, OverallLevel,
    grade_pitch, compute_exercise_score, GRADE_CONFIG,
)
from src.vocal_training.exercise_library import (
    VocalExercise, get_exercises_by_difficulty, list_all_exercises,
    get_exercise,
)
from src.vocal_training.exercise_generator import (
    ExerciseGenerator, generate_exercise_for_key,
)
from src.vocal_training.training_engine import (
    TrainingState, TrainingEngine,
)
from src.vocal_training.accompaniment import (
    AccompanimentMode, AccompanimentEngine,
)
from src.vocal_training.training_visualizer import TrainingVisualizer
from src.vocal_training.exercise_browser import ExerciseBrowser


# ── 样式常量 ──────────────────────────────────────────

PANEL_STYLE = """
    QGroupBox {
        border: 1px solid #30363D;
        border-radius: 6px;
        margin-top: 8px;
        padding-top: 16px;
        color: #C9D1D9;
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 6px;
    }
    QPushButton {
        background-color: #21262D;
        border: 1px solid #30363D;
        border-radius: 6px;
        padding: 6px 14px;
        color: #C9D1D9;
    }
    QPushButton:hover { border-color: #58A6FF; }
    QPushButton:pressed { background-color: #30363D; }
    QComboBox {
        background-color: #21262D;
        border: 1px solid #30363D;
        border-radius: 4px;
        padding: 4px 8px;
        color: #C9D1D9;
    }
    QSlider::groove:horizontal {
        background: #30363D;
        height: 4px;
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: #58A6FF;
        width: 12px;
        margin: -4px 0;
        border-radius: 6px;
    }
    QLabel { color: #C9D1D9; }
    QProgressBar {
        background-color: #21262D;
        border: 1px solid #30363D;
        border-radius: 4px;
        text-align: center;
        color: #C9D1D9;
    }
    QProgressBar::chunk {
        background-color: #DAA520;
        border-radius: 3px;
    }
"""

START_BTN_STYLE = """
    QPushButton {
        background-color: #238636;
        border: 1px solid #2EA043;
        border-radius: 8px;
        padding: 10px 30px;
        color: white;
        font-size: 14px;
        font-weight: bold;
    }
    QPushButton:hover { background-color: #2EA043; }
"""

STOP_BTN_STYLE = """
    QPushButton {
        background-color: #DA3633;
        border: 1px solid #F85149;
        border-radius: 8px;
        padding: 10px 30px;
        color: white;
        font-size: 14px;
        font-weight: bold;
    }
    QPushButton:hover { background-color: #F85149; }
"""


class TrainingPanel(QWidget):
    """练声模式完整面板。

    信号:
        exercise_started(exercise_id) — 练习开始
        exercise_completed(score)     — 练习完成 + 评分
        panel_closed()                — 面板关闭
    """

    exercise_started = pyqtSignal(str)
    exercise_completed = pyqtSignal(object)  # ExerciseScore
    panel_closed = pyqtSignal()
    session_duration_changed = pyqtSignal(float)  # 练声时长变化

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_STYLE)
        # 嵌入式 QWidget，由主窗口 QStackedWidget 管理

        # ── 核心模块 ──
        self._engine = TrainingEngine(tolerance_level="intermediate")
        self._accompaniment = AccompanimentEngine(sample_rate=48000)
        self._audition_engine = AccompanimentEngine(sample_rate=48000)  # 试听专用
        self._viz = TrainingVisualizer()

        # 状态
        self._is_running = False
        self._is_auditioning = False     # 试听播放中
        self._accomp_enabled = True      # 练声时伴奏开关
        self._viz_frozen = False         # 可视化器冻结（仅在 _stop_exercise 时置 True）
        self._exercise_start_time: float = 0.0
        self._last_pitch_time: float = 0.0
        self._auto_level = "beginner"  # 默认入门，由 Profile 覆盖

        # 音频输入提供者/停止者（由 TrainingIntegration 设置）
        self._audio_input_provider = None  # callable: () -> bool
        self._audio_input_stopper = None   # callable: () -> None

        # ── 练声时长追踪 ──
        self._session_duration: float = 0.0            # 本次会话累计练声时长（秒）
        self._current_exercise_duration: float = 0.0   # 当前练习已用时间（秒）
        # session_duration_changed 信号在类级别声明

        # 伴奏音频流 (练声模式)
        self._accomp_stream = None
        self._accomp_callback_timer = QTimer(self)
        self._accomp_callback_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._accomp_callback_timer.timeout.connect(self._pump_accompaniment)

        # 试听音频流（独立于练声）
        self._audition_stream = None
        self._audition_timer = QTimer(self)
        self._audition_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._audition_timer.timeout.connect(self._pump_audition)

        # UI 更新计时器
        self._ui_timer = QTimer(self)
        self._ui_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._ui_timer.timeout.connect(self._update_ui_tick)
        self._ui_timer.start(50)  # 20fps

        self._init_ui()
        self._wire_engine()

    # ── UI 构建 ─────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── 顶部: 控制栏 ──
        ctrl_row = QHBoxLayout()

        # 练习选择器 — 现代风格浏览器按钮
        ctrl_row.addWidget(QLabel("练习:"))
        self._exercise_btn = QPushButton("🎵 选择练习")
        self._exercise_btn.setStyleSheet(
            "QPushButton { background-color: #21262D; border: 2px solid #58A6FF; "
            "border-radius: 6px; padding: 7px 16px; color: #58A6FF; font-size: 13px; "
            "font-weight: bold; }"
            "QPushButton:hover { background-color: #292E36; border-color: #A78BFA; color: #A78BFA; }"
        )
        self._exercise_btn.setToolTip("打开练习浏览器 — 浏览 40 个分级练声曲谱")
        self._exercise_btn.clicked.connect(self._on_browse_exercises)
        ctrl_row.addWidget(self._exercise_btn)

        # 存储当前选中的练习ID（首次用默认练习）
        self._selected_exercise_id: str = "warmup_humming_c"

        # 等级 (自动从 Profile 读取，只读显示)

        # 调性选择器 (Phase 6)
        ctrl_row.addWidget(QLabel("调:"))
        self._key_combo = QComboBox()
        self._key_combo.addItems(["C", "D", "E", "F", "G", "A", "C#", "D#", "F#", "G#", "A#", "B"])
        self._key_combo.setCurrentText("C")
        self._key_combo.setFixedWidth(55)
        self._key_combo.currentTextChanged.connect(self._on_key_changed)
        ctrl_row.addWidget(self._key_combo)

        # 八度偏移选择器
        ctrl_row.addWidget(QLabel("8°:"))
        self._octave_combo = QComboBox()
        self._octave_combo.addItems(["-1", "0", "+1"])
        self._octave_combo.setCurrentText("0")
        self._octave_combo.setFixedWidth(45)
        self._octave_combo.setToolTip("八度偏移: -1=低八度(更低沉), 0=原调, +1=高八度(更明亮)")
        self._octave_combo.currentTextChanged.connect(self._on_key_changed)
        ctrl_row.addWidget(self._octave_combo)

        # 等级 (自动从 Profile 读取，只读显示)
        self._level_label = QLabel("🐣 小白")
        self._level_label.setStyleSheet(
            "color: #DAA520; font-weight: bold; font-size: 12px; "
            "background-color: #21262D; border: 1px solid #30363D; "
            "border-radius: 4px; padding: 4px 10px;"
        )
        self._level_label.setToolTip("训练等级自动晋升: 入门 → 中级 → 高级 → 专家级\n"
                                      "容差随等级自动收紧，无需手动设置")
        ctrl_row.addWidget(self._level_label)

        # 当前用户标签
        self._user_label = QLabel("👤 访客")
        self._user_label.setStyleSheet(
            "color: #58A6FF; font-weight: bold; font-size: 12px; "
            "background-color: #21262D; border: 1px solid #30363D; "
            "border-radius: 4px; padding: 4px 10px;"
        )
        self._user_label.setToolTip("当前练声数据将记录到此用户存档")
        ctrl_row.addWidget(self._user_label)

        # 速度
        ctrl_row.addWidget(QLabel("BPM:"))
        self._tempo_spin = QSpinBox()
        self._tempo_spin.setRange(40, 200)
        self._tempo_spin.setValue(100)
        self._tempo_spin.setFixedWidth(60)
        ctrl_row.addWidget(self._tempo_spin)

        ctrl_row.addStretch()

        # ── 试听按钮：播放选中练习的标准钢琴声（从头到尾）──
        self._audition_btn = QPushButton("🔊 试听")
        self._audition_btn.setStyleSheet(
            "QPushButton { background-color: #21262D; border: 2px solid #39D2C0; "
            "border-radius: 6px; padding: 7px 14px; color: #39D2C0; font-size: 12px; "
            "font-weight: bold; }"
            "QPushButton:hover { background-color: #292E36; border-color: #58F5E0; color: #58F5E0; }"
        )
        self._audition_btn.setToolTip("试听：播放整段练声的标准钢琴音，熟悉旋律和节奏")
        self._audition_btn.clicked.connect(self._on_audition_toggle)
        ctrl_row.addWidget(self._audition_btn)

        # ── 伴奏开关：练声时钢琴是否跟弹 ──
        self._accomp_toggle_btn = QPushButton("伴奏 开")
        self._accomp_toggle_btn.setCheckable(True)
        self._accomp_toggle_btn.setChecked(True)
        self._accomp_toggle_btn.setStyleSheet(
            "QPushButton { background-color: #1B3A2A; border: 2px solid #3FB950; "
            "border-radius: 6px; padding: 7px 14px; color: #3FB950; font-size: 12px; "
            "font-weight: bold; }"
            "QPushButton:hover { background-color: #214A32; }"
            "QPushButton:checked { background-color: #1B3A2A; border-color: #3FB950; color: #3FB950; }"
            "QPushButton:!checked { background-color: #3A1B1B; border-color: #F85149; color: #F85149; }"
        )
        self._accomp_toggle_btn.setToolTip("伴奏开关：开启时练声有钢琴跟弹，关闭时仅显示目标音高线")
        self._accomp_toggle_btn.toggled.connect(self._on_accomp_toggled)
        ctrl_row.addWidget(self._accomp_toggle_btn)

        # 启动/停止
        self._start_btn = QPushButton("开始练声")
        self._start_btn.setStyleSheet(START_BTN_STYLE)
        self._start_btn.clicked.connect(self._on_start_stop)
        ctrl_row.addWidget(self._start_btn)

        layout.addLayout(ctrl_row)

        # ── 中部: 可视化器 ──
        self._viz.setMinimumHeight(300)
        layout.addWidget(self._viz, stretch=1)

        # ── 底部: 状态栏 ──
        bottom = QHBoxLayout()

        # 实时状态
        self._state_label = QLabel("准备就绪 — 选择练习并按开始")
        self._state_label.setFont(QFont("Microsoft YaHei", 10))
        bottom.addWidget(self._state_label)

        bottom.addStretch()

        # 伴奏音量
        bottom.addWidget(QLabel("音量:"))
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(70)
        self._volume_slider.setFixedWidth(100)
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        bottom.addWidget(self._volume_slider)

        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(180)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        bottom.addWidget(self._progress_bar)

        layout.addLayout(bottom)

        # 初始加载第一个练习的预览（在 UI 构造完成后延迟一帧执行，确保可视化器就绪）
        QTimer.singleShot(0, self._preview_current_exercise)

    # ── 引擎回调接线 ─────────────────────────────────

    def _wire_engine(self):
        eng = self._engine
        eng.on("state_changed", self._on_engine_state)
        eng.on("note_changed", lambda i, n: self._viz.set_note_active(i))
        eng.on("pitch_graded", self._on_note_graded)
        eng.on("streak_updated", lambda s: self._viz.on_streak_updated(s))
        eng.on("exercise_completed", self._on_exercise_completed)

    # ── 公开方法 ─────────────────────────────────────

    def feed_pitch(self, freq_hz: float, confidence: float = 0.9, rms: float = 0.0) -> None:
        """输入实时音高检测结果（display_frequency — 已经过普通模式完整后处理）。

        练声模式轻量八度纠错：YIN 在高音区容易将 2nd 谐波误判为基频，
        导致检测频率偏高一个八度。这里利用已知目标音做保守校验：
        若频率远超目标且除以 2 后更接近，则自动修正。
        """
        ts = time.time()

        # ── 轻量八度/谐波过冲校验（利用引擎当前目标音）──
        # YIN 在高音区 (E4+) 容易将谐波误判为基频：
        #   - 2nd 谐波 → 频率 ×2 (八度过冲)
        #   - 3rd 谐波 → 频率 ×3 (八度+五度过冲)
        #   - 3:2 比锁定 → 频率 ×1.5 (纯五度过冲，假声/头声过渡常见)
        if freq_hz > 0 and self._is_running:
            target_note = self._engine.current_note
            if target_note is not None:
                target_midi = float(target_note.midi_note)
                target_hz = 440.0 * (2.0 ** ((target_midi - 69.0) / 12.0))
                detected_midi = 69.0 + 12.0 * np.log2(max(freq_hz, 1e-9) / 440.0)
                target_deviation = detected_midi - target_midi  # 正=偏高，负=偏低

                # 偏高超过 5 个半音 → 可能是 YIN 谐波误锁
                if target_deviation > 5.0:
                    # 尝试多种频率回退：八度(/2)、双八度(/4)、三倍谐波(/3)、五度(×2/3)
                    candidates = [
                        (freq_hz / 2, '/2 (八度)'),
                        (freq_hz / 3, '/3 (三倍谐波)'),
                        (freq_hz * 2.0 / 3.0, '×2/3 (五度下修)'),
                        (freq_hz / 4, '/4 (双八度)'),
                        (freq_hz * 3.0 / 4.0, '×3/4 (四度下修)'),
                    ]
                    best_freq = freq_hz
                    best_dev = abs(target_deviation)
                    best_label = ''
                    for candidate_hz, label in candidates:
                        if candidate_hz < 40.0:  # 低于低音下限
                            continue
                        candidate_midi = 69.0 + 12.0 * np.log2(candidate_hz / 440.0)
                        candidate_dev = abs(candidate_midi - target_midi)
                        # 回退后偏差在 6 半音内且比当前最佳更接近 → 采用
                        if candidate_dev < 6.0 and candidate_dev < best_dev:
                            best_freq = candidate_hz
                            best_dev = candidate_dev
                            best_label = label
                    if best_freq != freq_hz:
                        orig_midi_str = f"{detected_midi:.1f}"
                        new_midi_str = f"{69.0 + 12.0 * np.log2(best_freq / 440.0):.1f}"
                        print(f"[Panel] 谐波过冲修正: {freq_hz:.0f}Hz({orig_midi_str}MIDI) "
                              f"→ {best_freq:.0f}Hz({new_midi_str}MIDI) "
                              f"| target={target_midi:.0f}MIDI {best_label}")
                        freq_hz = best_freq

        # ── 时间轴管理 ──
        if self._exercise_start_time == 0.0:
            self._exercise_start_time = ts

        relative_t = ts - self._exercise_start_time

        # ── 可视化器冻结检查（仅在 _stop_exercise 完全停止后才冻结）──
        if not self._viz_frozen:
            self._viz.feed_pitch_point(relative_t, freq_hz)

        # ── 评分及引擎处理仅在练声进行中 ──
        if self._is_running:
            if self._last_pitch_time == 0:
                self._last_pitch_time = ts
            self._engine.feed_pitch(freq_hz, confidence, ts)
            self._last_pitch_time = ts

        # 对比日志（每30帧打印，方便与普通模式对比）
        if not hasattr(self, '_feed_dbg_cnt'):
            self._feed_dbg_cnt = 0
        self._feed_dbg_cnt += 1
        if self._feed_dbg_cnt % 30 == 1:
            midi = 69.0 + 12.0 * np.log2(max(freq_hz, 1e-9) / 440.0) if freq_hz > 0 else 0
            print(f"[Panel] feed #{self._feed_dbg_cnt} | "
                  f"freq={freq_hz:.1f}Hz midi={midi:.1f} conf={confidence:.2f} rms={rms:.4f}")

    def set_sample_rate(self, sr: int) -> None:
        """更新伴奏合成采样率。"""
        self._accompaniment = AccompanimentEngine(sample_rate=sr)

    def closeEvent(self, event):
        self._stop_exercise()
        self.panel_closed.emit()
        super().closeEvent(event)

    # ── 内部槽 ─────────────────────────────────────

    def _on_start_stop(self):
        if self._is_running:
            self._stop_exercise()
        else:
            self._start_exercise()

    def _start_exercise(self):
        exercise_id = self._selected_exercise_id
        if not exercise_id:
            return
        if self._is_auditioning:
            return  # 试听中不允许开始练声
        exercise = get_exercise(exercise_id)
        if not exercise:
            return

        # ── 确保音频输入在运行 ──
        if self._audio_input_provider is not None:
            try:
                if not self._audio_input_provider():
                    print("[Panel] ⚠️ 音频输入启动失败，练声将没有音高数据")
            except Exception as _e:
                print(f"[Panel] 音频输入启动异常: {_e}")

        # ── 同步伴奏采样率到当前实际音频采样率 ──
        try:
            main = self.parent()  # IntegratedRecordingInterface
            ap = getattr(main, 'audio_processor', None)
            if ap is not None:
                actual_sr = int(getattr(ap, 'active_input_samplerate', 0)
                                or getattr(ap, 'sample_rate', 48000))
                if actual_sr > 0 and actual_sr != getattr(self._accompaniment, 'sr', 0):
                    self._accompaniment = AccompanimentEngine(sample_rate=actual_sr)
                    print(f"[Panel] 伴奏采样率同步: {actual_sr}Hz")
        except Exception:
            pass

        # 重置自动结束日志计数器
        self._auto_end_dbg = 0

        # Phase 6: 根据选择的调性和八度偏移生成移调练习
        selected_key = self._key_combo.currentText()
        octave_shift = self._get_octave_shift()
        if selected_key != "C" or octave_shift != 0:
            exercise = generate_exercise_for_key(exercise_id, selected_key, octave_shift=octave_shift)
            if exercise is None:
                exercise = get_exercise(exercise_id)

        # ── tempo 统一：将 UI 旋钮值写入练习对象，确保引擎/伴奏/可视化器三端一致 ──
        exercise = self._apply_tempo(exercise)

        # 等级自动映射: TrainingStats.level → 容差
        _level_map = {"beginner": "beginner", "intermediate": "intermediate",
                       "advanced": "advanced", "expert": "advanced"}
        tolerance = _level_map.get(self._auto_level, "intermediate")

        # 伴奏：开关控制 → 开=全程伴奏，关=静默
        accomp_mode = AccompanimentMode.CONTINUOUS if self._accomp_enabled else AccompanimentMode.SILENT

        # 加载并启动（三端共用同一份 exercise 对象，tempo 已统一）
        self._engine.load_exercise(exercise, tolerance_level=tolerance)
        self._accompaniment.load_exercise(
            exercise, mode=accomp_mode,
            is_first_attempt=True, tempo_override=exercise.tempo,
        )
        self._viz.load_exercise(exercise)
        # 同步伴奏实际总时长 (二者 tempo 一致后应相等)
        self._viz.set_total_duration(self._accompaniment.total_duration_sec)

        # ── 先设时间基准再启动伴奏，确保音高时间戳与伴奏位置对齐 ──
        self._exercise_ever_started = True
        self._viz_frozen = False
        self._exercise_start_time = time.time()
        self._last_pitch_time = 0.0
        self._current_exercise_duration = 0.0
        self._is_running = True

        self._engine.start(countdown_beats=2)
        self._accompaniment.start()
        self._start_accomp_output()

        self._start_btn.setText("停止练声")
        self._start_btn.setStyleSheet(STOP_BTN_STYLE)
        self._state_label.setText(f"练声中: {exercise.name}")
        self._progress_bar.setValue(0)

        self.exercise_started.emit(exercise_id)

    def _stop_exercise(self):
        self._is_running = False
        self._viz_frozen = True  # 完全停止后才冻结可视化器
        self._viz.disable_follow()  # 冻结镜头跟随，允许用户自由拖动滚动条
        self._stop_accomp_output()
        # 停止由练声模式启动的录音（练习结束 = 不再需要音频输入）
        if self._audio_input_stopper is not None:
            try:
                self._audio_input_stopper()
            except Exception:
                pass
        # 累加本次练习时长到会话总时长
        self._session_duration += max(0.0, self._current_exercise_duration)
        self._current_exercise_duration = 0.0
        self.session_duration_changed.emit(self._session_duration)
        # 重置状态标志（为下一次练习或预览准备）
        self._exercise_ever_started = False
        # 如果试听还在播放，一并停止
        if self._is_auditioning:
            self._stop_audition()

        if self._engine.current_state not in (
            TrainingState.FINISHED, TrainingState.IDLE
        ):
            score = self._engine.finish_exercise()
            self._viz.on_exercise_completed(score)

        self._accompaniment.stop()
        self._start_btn.setText("开始练声")
        self._start_btn.setStyleSheet(START_BTN_STYLE)
        self._start_btn.setEnabled(True)
        self._state_label.setText("准备就绪 — 选择练习并按开始")
        self._progress_bar.setValue(0)

    def _on_engine_state(self, state: TrainingState):
        if state == TrainingState.COUNTDOWN:
            self._state_label.setText("预备...")
            self._viz.update_phase("countdown")
            # 延迟至 t≈2.5s 进入聆听（对齐钢琴提前进入，第一标注在 3.0s）
            # 然后聆听 0.5s 后在 t≈3.0s 进入演唱
            QTimer.singleShot(2500, self._engine.advance_to_listening)
        elif state == TrainingState.LISTENING:
            self._state_label.setText("聆听参考音...")
            self._viz.update_phase("reference")
            QTimer.singleShot(500, self._engine.advance_to_singing)
        elif state == TrainingState.SINGING:
            self._state_label.setText("演唱中 —— 跟唱！")
            self._viz.update_phase("singing")
        elif state == TrainingState.FINISHED:
            self._state_label.setText("评分完成")
            self._viz.update_phase("finished")

    def _on_note_graded(self, result: NoteResult):
        note_idx = self._engine.current_note_index - 1
        if note_idx >= 0:
            self._viz.on_note_graded(note_idx, result)

    def set_auto_level(self, profile_level: str) -> None:
        """从 Profile 同步训练等级。"""
        _names = {
            "beginner": "🐣 小白", "intermediate": "🌟 渐入佳境",
            "advanced": "🎵 实力唱将", "expert": "🎤 麦霸",
        }
        self._auto_level = profile_level
        self._level_label.setText(_names.get(profile_level, "🐣 小白"))

    def set_user_label(self, name: str) -> None:
        """更新面板上的当前用户标识。"""
        display = name if name else "访客"
        if len(display) > 6:
            display = display[:5] + "…"
        self._user_label.setText(f"👤 {display}")
        self._user_label.setToolTip(
            f"当前用户: {name}\n练声数据将记录到此用户存档"
            if name else "访客模式 — 练声数据不会保存"
        )

    def _on_exercise_completed(self, score: ExerciseScore):
        """引擎评分完成回调 — 仅更新 UI 评分展示和发信号保存结果。

        不停止伴奏输出、不设 _is_running=False、不冻结可视化器。
        伴奏尾巴和音高线的最后一段由 _update_ui_tick 检测伴奏结束后
        统一调用 _stop_exercise 来完全停止。
        """
        self._viz.on_exercise_completed(score)
        # 练习结束 — 展示完整评语
        self._state_label.setText(
            f"{score.overall_level.label} — {score.total_score:.0f}%  |  "
            f"音准:{score.pitch_accuracy:.0f} 稳定:{score.stability:.0f} 节奏:{score.timing:.0f}"
        )
        if score.overall_level.encouragement:
            self._state_label.setText(
                f"{score.overall_level.label} — {score.total_score:.0f}%  |  "
                f"{score.overall_level.encouragement}"
            )
        self._progress_bar.setValue(100)
        self._start_btn.setText("开始练声")
        self._start_btn.setStyleSheet(START_BTN_STYLE)
        self.exercise_completed.emit(score)

    def _on_browse_exercises(self):
        """打开古籍书苑练习浏览器。"""
        def _on_select(exercise_id: str):
            self._selected_exercise_id = exercise_id
            self._preview_current_exercise()
            # 更新按钮文字
            from src.vocal_training.exercise_library import get_exercise
            ex = get_exercise(exercise_id)
            if ex:
                self._exercise_btn.setText(f"🎵 {ex.name[:10]}{'...' if len(ex.name)>10 else ''}")
                self._exercise_btn.setToolTip(f"当前练习: {ex.name}\n{ex.star_display}  {ex.category_name}\n点击更换")
            self._state_label.setText(f"已选: {ex.name if ex else exercise_id} — 按开始练声")
            self._state_label.setStyleSheet("color: #8B6914; font-weight: bold;")

        browser = ExerciseBrowser(self, on_start_exercise=_on_select)
        # 点击"开始练声"会触发 on_start_exercise 并关闭对话框
        browser.exercise_selected.connect(lambda eid: self._on_browser_select(eid))
        browser.exec()

    def _on_browser_select(self, exercise_id: str):
        """浏览器中选择练习后的回调。"""
        self._selected_exercise_id = exercise_id
        self._preview_current_exercise()
        from src.vocal_training.exercise_library import get_exercise
        ex = get_exercise(exercise_id)
        if ex:
            self._exercise_btn.setText(f"🎵 {ex.name[:12]}{'...' if len(ex.name)>12 else ''}")
            self._state_label.setText(f"已选: {ex.name} — 按开始练声")
            self._state_label.setStyleSheet("color: #8B6914; font-weight: bold;")

    def _preview_current_exercise(self):
        """将当前选中的练习 + 调性加载到可视化器预览（不启动引擎）。

        只更新目标音符条，调性/八度变化时保留音高历史。
        切换到不同练习时清除音高历史并同步 tempo。
        """
        if self._is_running:
            return  # 练习中不打断
        exercise_id = self._selected_exercise_id
        if not exercise_id:
            return
        selected_key = self._key_combo.currentText()
        octave_shift = self._get_octave_shift()
        from src.vocal_training.exercise_library import get_exercise
        ex_base = get_exercise(exercise_id)
        if not ex_base:
            return
        ex = generate_exercise_for_key(exercise_id, selected_key, octave_shift=octave_shift) if (selected_key != "C" or octave_shift != 0) else ex_base
        if ex:
            # 同练习调性/八度切换保留历史，切换练习则清除
            prev_ex_id = getattr(self, '_previewed_exercise_id', None)
            same_exercise = (prev_ex_id == exercise_id)
            self._previewed_exercise_id = exercise_id

            # 新练习 → 同步 tempo 旋钮到练习默认值
            if not same_exercise:
                self._sync_tempo_to_exercise(ex)

            # 应用 UI tempo 到练习对象，确保标注条与即将播放的钢琴对齐
            ex = self._apply_tempo(ex)

            self._viz.load_exercise(ex, keep_history=same_exercise)
            # 不重置 _exercise_start_time — 由 _start_exercise 统一管理
            # 预览模式下隐藏 playhead
            self._viz.update_phase("silence")
            self._viz._playhead_line.setVisible(False)

    def _get_octave_shift(self) -> int:
        """读取八度偏移选择器的当前值。"""
        try:
            return int(self._octave_combo.currentText())
        except Exception:
            return 0

    def _apply_tempo(self, exercise: VocalExercise) -> VocalExercise:
        """确保练习对象的 tempo 与 UI 旋钮一致。

        伴奏引擎、可视化器和评分引擎共用同一份练习对象，
        tempo 必须统一才能保证标注条、钢琴音、音符时长对齐。
        """
        spin_tempo = self._tempo_spin.value()
        if exercise.tempo != spin_tempo:
            import copy
            ex = copy.copy(exercise)
            ex.tempo = spin_tempo
            print(f"[Panel] tempo 覆盖: {exercise.tempo} → {spin_tempo} BPM")
            return ex
        return exercise

    def _sync_tempo_to_exercise(self, exercise: VocalExercise) -> None:
        """切换练习时将 UI 旋钮同步到练习的默认 tempo。"""
        if self._tempo_spin.value() != exercise.tempo:
            self._tempo_spin.blockSignals(True)
            try:
                self._tempo_spin.setValue(exercise.tempo)
            finally:
                self._tempo_spin.blockSignals(False)

    def _on_key_changed(self, key: str):
        """调性或八度变化时刷新练习预览。"""
        self._preview_current_exercise()

    def _on_volume_changed(self, value: int):
        self._accompaniment.volume = value / 100.0
        self._audition_engine.volume = value / 100.0

    # ── 试听（预览标准钢琴声）────────────────────────────

    def _on_audition_toggle(self):
        """试听按钮：播放/停止当前练习的完整钢琴伴奏。"""
        if self._is_auditioning:
            self._stop_audition()
        else:
            self._start_audition()

    def _start_audition(self):
        """开始试听：加载当前练习并播放完整钢琴音。"""
        if self._is_auditioning or self._is_running:
            return
        exercise_id = self._selected_exercise_id
        if not exercise_id:
            return
        from src.vocal_training.exercise_library import get_exercise
        ex_base = get_exercise(exercise_id)
        if not ex_base:
            return

        # 生成当前调性和八度的练习
        selected_key = self._key_combo.currentText()
        octave_shift = self._get_octave_shift()
        ex = generate_exercise_for_key(exercise_id, selected_key, octave_shift=octave_shift) if (selected_key != "C" or octave_shift != 0) else ex_base
        if not ex:
            return

        # 应用 UI tempo 确保试听速度与标注条预览一致
        ex = self._apply_tempo(ex)

        # 加载到试听引擎（全程伴奏模式）
        self._audition_engine.load_exercise(
            ex, mode=AccompanimentMode.CONTINUOUS,
            is_first_attempt=True, tempo_override=ex.tempo,
        )
        self._audition_engine.start()

        # 启动试听音频流
        self._start_audition_stream()

        self._is_auditioning = True
        self._audition_btn.setText("⏹ 结束试听")
        self._audition_btn.setStyleSheet(
            "QPushButton { background-color: #3A1B1B; border: 2px solid #F85149; "
            "border-radius: 6px; padding: 7px 14px; color: #F85149; font-size: 12px; "
            "font-weight: bold; }"
            "QPushButton:hover { background-color: #4A2222; }"
        )
        # 试听期间禁用开始练声
        self._start_btn.setEnabled(False)
        self._state_label.setText(f"🔊 试听中: {ex.name}")
        self._state_label.setStyleSheet("color: #39D2C0; font-weight: bold;")

    def _stop_audition(self):
        """停止试听。"""
        self._is_auditioning = False
        self._stop_audition_stream()
        self._audition_engine.stop()

        self._audition_btn.setText("🔊 试听")
        self._audition_btn.setStyleSheet(
            "QPushButton { background-color: #21262D; border: 2px solid #39D2C0; "
            "border-radius: 6px; padding: 7px 14px; color: #39D2C0; font-size: 12px; "
            "font-weight: bold; }"
            "QPushButton:hover { background-color: #292E36; border-color: #58F5E0; color: #58F5E0; }"
        )
        self._start_btn.setEnabled(True)
        self._state_label.setText("试听已结束 — 选择练习并按开始")
        self._state_label.setStyleSheet("color: #C9D1D9;")

    def _start_audition_stream(self):
        """启动试听音频输出流。"""
        try:
            import sounddevice as sd
            if self._audition_stream is not None:
                self._stop_audition_stream()

            audition_sr = getattr(self._audition_engine, 'sr', 48000)
            self._audition_stream = sd.OutputStream(
                samplerate=audition_sr, channels=2, dtype="float32",
                blocksize=1024,
                callback=self._audition_callback,
            )
            self._audition_stream.start()
        except Exception:
            self._audition_stream = None
            self._audition_timer.start(21)

    def _stop_audition_stream(self):
        """停止试听音频输出流。"""
        self._audition_timer.stop()
        try:
            if self._audition_stream is not None:
                self._audition_stream.stop()
                self._audition_stream.close()
        except Exception:
            pass
        self._audition_stream = None

    def _audition_callback(self, outdata, frames, time_info, status):
        """试听 sounddevice 回调。"""
        if not self._is_auditioning or self._audition_engine is None:
            outdata.fill(0)
            return
        try:
            chunk = self._audition_engine.get_audio_chunk(frames)
            # 检测是否播放完毕
            if not self._audition_engine.is_playing:
                outdata.fill(0)
                # 通知主线程结束试听
                QTimer.singleShot(0, self._stop_audition)
                return
            outdata[:, 0] = chunk[:, 0]
            outdata[:, 1] = chunk[:, 1]
        except Exception:
            outdata.fill(0)

    def _pump_audition(self):
        """QTimer 驱动试听（静默回退模式）。"""
        if not self._is_auditioning:
            self._audition_timer.stop()
            return
        chunk = self._audition_engine.get_audio_chunk(1024)
        if not self._audition_engine.is_playing:
            self._stop_audition()

    # ── 伴奏开关 ──────────────────────────────────────

    def _on_accomp_toggled(self, checked: bool):
        """伴奏开关切换。"""
        self._accomp_enabled = checked
        if checked:
            self._accomp_toggle_btn.setText("伴奏 开")
        else:
            self._accomp_toggle_btn.setText("伴奏 关")

    # ── 伴奏输出（练声模式）─────────────────────────────

    def _start_accomp_output(self):
        """启动伴奏音频输出流。"""
        try:
            import sounddevice as sd
            if self._accomp_stream is not None:
                self._stop_accomp_output()

            # 使用 sounddevice OutputStream 播放伴奏（采样率与伴奏引擎一致）
            accomp_sr = getattr(self._accompaniment, 'sr', 48000)
            self._accomp_stream = sd.OutputStream(
                samplerate=accomp_sr, channels=2, dtype="float32",
                blocksize=1024,
                callback=self._accomp_callback,
            )
            self._accomp_stream.start()
        except Exception:
            self._accomp_stream = None
            # 回退：使用 QTimer 不播放音频（静默模式也能用）
            self._accomp_callback_timer.start(21)  # ~48fps

    def _stop_accomp_output(self):
        self._accomp_callback_timer.stop()
        try:
            if self._accomp_stream is not None:
                self._accomp_stream.stop()
                self._accomp_stream.close()
        except Exception:
            pass
        self._accomp_stream = None

    def _accomp_callback(self, outdata, frames, time_info, status):
        """sounddevice 回调：输出伴奏音频。"""
        if not self._is_running:
            outdata.fill(0)
            return
        try:
            chunk = self._accompaniment.get_audio_chunk(frames)
            outdata[:, 0] = chunk[:, 0]
            outdata[:, 1] = chunk[:, 1]
        except Exception:
            outdata.fill(0)

    def _pump_accompaniment(self):
        """QTimer 驱动伴奏（静默回退模式）。"""
        if not self._is_running:
            return
        self._accompaniment.get_audio_chunk(1024)  # 推进播放位置

    def _update_ui_tick(self):
        """定期更新进度条 + 可视化时间轴 + 相位提示 + 自动结束检测。"""
        if not self._is_running:
            return
        if self._accompaniment and self._accompaniment.total_duration_sec > 0:
            pos = self._accompaniment.position_sec
            total = self._accompaniment.total_duration_sec
            pct = min(100, int(pos / max(total, 0.01) * 100))
            self._progress_bar.setValue(pct)
            # 驱动可视化时间轴
            self._viz.update_elapsed(pos)
            # ── 更新练声时长（取有效歌唱时间，排除准备阶段）──
            effective_pos = max(0.0, pos - 3.0)  # 减去 3s 准备时间
            self._current_exercise_duration = min(effective_pos, total - 3.0)  # 上限=练习总歌唱时长
            self.session_duration_changed.emit(
                self._session_duration + self._current_exercise_duration
            )
            # 相位提示（3秒准备时间：0-3s 为倒计时/预备阶段）
            section = self._accompaniment.get_current_section_type()
            if section == "reference":
                self._viz.update_phase("reference")
                self._state_label.setText("🎹 聆听参考音...")
            elif section == "singing":
                self._viz.update_phase("singing")
                self._state_label.setText("🎤 跟唱！")
            elif section == "silence":
                if pos < 3.0:
                    remaining = max(0, 3 - int(pos))
                    self._viz.update_countdown(remaining)
                    self._state_label.setText(f"准备中... {remaining}秒后开始")
                else:
                    self._viz.update_phase("silence")

            # ── 自动结束检测（伴奏播完后给引擎宽限期完成最后的音）──
            accomp_done = not self._accompaniment.is_playing
            engine_done = self._engine.current_state in (
                TrainingState.FINISHED, TrainingState.IDLE
            )

            # 宽限期管理：伴奏停播后不立即强退，等引擎自然完成或超时再收尾
            if not hasattr(self, '_accomp_done_time'):
                self._accomp_done_time: Optional[float] = None
            if accomp_done and self._accomp_done_time is None:
                self._accomp_done_time = time.time()
                print(f"[AutoEnd] 伴奏已停播，等待引擎完成最后音符 (当前 note={self._engine.current_note_index}/{self._engine.total_notes})")
            elif not accomp_done:
                self._accomp_done_time = None

            grace_timeout = 3.0  # 伴奏停播后最多等3秒让最后音符自然完成
            grace_elapsed = (time.time() - self._accomp_done_time) if self._accomp_done_time else 0.0

            # 定期日志（每 60 帧 ~3 秒一次）
            if not hasattr(self, '_auto_end_dbg'):
                self._auto_end_dbg = 0
            self._auto_end_dbg += 1
            if self._auto_end_dbg % 60 == 1:
                print(f"[AutoEnd] tick#{self._auto_end_dbg} | "
                      f"pos={pos:.1f}s total={total:.1f}s "
                      f"accomp_done={accomp_done} engine_state={self._engine.current_state.name} "
                      f"note={self._engine.current_note_index}/{self._engine.total_notes}"
                      + (f" grace={grace_elapsed:.1f}s" if self._accomp_done_time else ""))

            if accomp_done and self._accomp_done_time is not None:
                if engine_done:
                    print(f"[AutoEnd] 引擎已自然完成 → 触发自动结束")
                    if self._is_running:
                        self._stop_exercise()
                        self._viz.update_phase("finished")
                elif grace_elapsed >= grace_timeout:
                    print(f"[AutoEnd] 宽限期超时 ({grace_timeout:.0f}s)，强制结束引擎")
                    self._engine.finish_exercise()
                    if self._is_running:
                        self._stop_exercise()
                        self._viz.update_phase("finished")

