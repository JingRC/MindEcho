"""练声可视化器 — 钢琴卷帘 + 银色→金色音高线 + 命中特效

基于 pyqtgraph，用于练声模式的实时视觉反馈：
  - 钢琴卷帘背景 (横向 = 时间, 纵向 = MIDI 音符)
  - 目标音符条 (灰色待命 → 银色演唱中 → 金色命中)
  - 用户音高线 (实时 ECG, 颜色随命中等级变化)
  - PERFECT / GREAT / Good 标签弹出动画
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

# ── Qt & pyqtgraph imports ──
try:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QScrollBar, QGridLayout
    from PyQt6.QtCore import Qt, QTimer, QRectF, pyqtSignal
    from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush
    QT_VERSION = 6
except ImportError:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QScrollBar, QGridLayout
    from PyQt5.QtCore import Qt, QTimer, QRectF, pyqtSignal
    from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QBrush
    QT_VERSION = 5

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False

from src.vocal_training.scoring import PitchGrade, NoteResult, ExerciseScore, OverallLevel, GRADE_CONFIG
from src.vocal_training.exercise_library import VocalExercise, TargetNote


# ── 颜色常量 ────────────────────────────────────────────

COLORS = {
    "bg":              "#0D1117",   # 深色背景 (GitHub Dark)
    "grid":            "#30363D",   # 网格线
    "text":            "#C9D1D9",   # 文字
    "piano_white":     "#E8E8E8",   # 白键
    "piano_black":     "#30363D",   # 黑键
    "target_waiting":  "#484F58",   # 未开始 — 暗灰
    "target_active":   "#A0A0A0",   # 演唱中未命中 — 银色
    "target_hit_miss": "#3A3A3A",   # 错过 — 深灰
    "pitch_silver":    "#C0C0C0",   # OK 级别 — 银色
    "pitch_gold_light":"#E8C84A",   # Good — 淡金
    "pitch_gold":      "#DAA520",   # Great — 金色
    "pitch_gold_bright":"#FFD700",  # Perfect — 亮金
    "label_perfect":   "#FFD700",
    "label_great":     "#DAA520",
    "label_good":      "#E8C84A",
    "streak_fire":     "#FF6B35",   # 连击火焰色
}

# ── 音名标签 (钢琴卷帘 Y 轴) ──────────────────────────

# ── 常量 ──────────────────────────────────────────────

PREPARATION_OFFSET: float = 3.0   # 练声准备时间（秒），标注从第3秒开始
PIANO_EARLY_ENTRY: float = 0.5    # 钢琴比第一个标注早0.5秒进入

_NOTE_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _midi_to_note(midi: int) -> str:
    return f"{_NOTE_NAMES_SHARP[midi % 12]}{midi // 12 - 1}"


# ── 浮动标签 (命中特效) ──────────────────────────────

@dataclass
class _FloatingLabel:
    """一个飘浮标签的状态"""
    text: str
    x: float          # 数据坐标 X (时间)
    y: float          # 数据坐标 Y (MIDI)
    color: str
    birth_time: float
    lifetime: float = 1.2  # 存活秒数
    opacity: float = 1.0
    vy: float = 0.15       # 上飘速度 (MIDI/秒)


class TrainingVisualizer(QWidget):
    """练声模式可视化器。

    信号:
        ready — 初始化完成
    """

    ready = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        if not PYQTGRAPH_AVAILABLE:
            raise ImportError("练声可视化需要 pyqtgraph: pip install pyqtgraph")

        self._exercise: Optional[VocalExercise] = None
        self._total_duration: float = 10.0  # 总时长(秒)
        self._elapsed: float = 0.0          # 已过时间
        self._note_index: int = 0
        self._note_results: List[NoteResult] = []
        self._current_grade: PitchGrade = PitchGrade.MISS

        # 音高线数据（约 24 秒历史，防止多次练习累积卡顿）
        self._pitch_history: deque = deque(maxlen=1200)
        self._time_history: deque = deque(maxlen=1200)
        self._grade_history: deque = deque(maxlen=1200)  # per-sample grade

        # 浮动标签
        self._floating_labels: List[_FloatingLabel] = []

        # 目标音符条状态
        self._bar_states: Dict[int, str] = {}  # note_index → "waiting"|"active"|"hit"|"miss"

        # 连击显示
        self._streak: int = 0
        self._show_streak: bool = False
        self._streak_timer: float = 0.0

        # 计时器
        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(33)  # ~30fps

        self._init_ui()

    # ── UI 构建 ─────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── 顶部状态栏 ──
        self._status_bar = QHBoxLayout()
        self._phase_label = QLabel("")
        self._phase_label.setStyleSheet(
            f"color: {COLORS['pitch_gold']}; font-size: 13px; font-weight: bold;")
        self._status_label = QLabel("准备就绪")
        self._status_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 12px;")
        self._score_label = QLabel("")
        self._score_label.setStyleSheet(f"color: {COLORS['pitch_gold']}; font-size: 14px; font-weight: bold;")
        self._streak_label = QLabel("")
        self._streak_label.setStyleSheet(f"color: {COLORS['streak_fire']}; font-size: 18px; font-weight: bold;")
        self._status_bar.addWidget(self._phase_label)
        self._status_bar.addWidget(self._status_label)
        self._status_bar.addStretch()
        self._status_bar.addWidget(self._streak_label)
        self._status_bar.addWidget(self._score_label)
        layout.addLayout(self._status_bar)

        # ── pyqtgraph 主图 ──
        self._plot = pg.PlotWidget()
        self._plot.setBackground(COLORS["bg"])
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.setLabel("left", "MIDI Note / Pitch")
        self._plot.setLabel("bottom", "Time (s)")

        # Y 轴: 初始 C3~C6 (48~84)，完整人声范围
        self._y_lo, self._y_hi = 45.0, 81.0  # 含上下余量
        self._plot.setYRange(self._y_lo, self._y_hi)
        self._update_y_ticks(self._y_lo, self._y_hi)

        # X 轴: 初始 0-8s 窗口
        self._x_view_range = 8.0
        self._plot.setXRange(0, self._x_view_range)
        self._plot.setMenuEnabled(False)

        # 参考唱歌模式: 左键拖拽=平移, 滚轮=纵轴
        vb = self._plot.getViewBox()
        vb.setMouseMode(vb.PanMode)
        vb.setMouseEnabled(x=True, y=True)
        vb.disableAutoRange()  # 禁止 pyqtgraph 自动调整范围，手动控制

        # ── X 轴防负值 + Y 轴范围限制 ──
        self._clamp_guard = False
        def _clamp_view_range(_vb, new_range):
            if self._clamp_guard:
                return
            x_range, y_range = list(new_range[0]), list(new_range[1])
            changed = False
            # X 轴不能为负
            if x_range[0] < 0:
                shift = -x_range[0]
                x_range = [0.0, x_range[1] + shift]
                changed = True
            # X 轴最小 span
            if x_range[1] - x_range[0] < 2.0:
                x_range[1] = x_range[0] + max(2.0, self._x_view_range)
                changed = True
            # Y 轴不超出 MIDI 40-100
            if y_range[0] < 40:
                y_range[1] = 40 + (y_range[1] - y_range[0])
                y_range[0] = 40
                changed = True
            if y_range[1] > 100:
                y_range[0] = 100 - (y_range[1] - y_range[0])
                y_range[1] = 100
                changed = True
            if changed:
                self._clamp_guard = True
                try:
                    _vb.setRange(xRange=tuple(x_range), yRange=tuple(y_range), padding=0)
                finally:
                    self._clamp_guard = False
            self._sync_scrollbars_from_view()
        vb.sigRangeChanged.connect(_clamp_view_range)

        # 滚轮 → 纵向滚动条（而非直接调整 Y 轴）
        def _training_wheel_event(ev):
            delta = ev.angleDelta().y()
            if delta == 0:
                return
            # 每格滚轮移动 50 步（~3 半音），方向自然
            step = -50 if delta > 0 else 50
            new_val = self._v_scrollbar.value() + step
            new_val = max(0, min(1000, new_val))
            self._v_scrollbar.setValue(new_val)
        self._plot.wheelEvent = _training_wheel_event

        # ── 双滚动条 (参考唱歌模式 create_plot_with_scrollbars) ──
        _scrollbar_style = """
            QScrollBar { background-color: rgba(0,0,0,0.2); border: none; }
            QScrollBar::handle { background-color: rgba(88,166,255,0.35); border-radius: 6px; }
            QScrollBar::handle:hover { background-color: rgba(88,166,255,0.55); }
            QScrollBar::add-line, QScrollBar::sub-line { border: none; background: none; }
        """

        self._v_scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self._v_scrollbar.setRange(0, 1000)
        self._v_scrollbar.setValue(500)
        self._v_scrollbar.setSingleStep(10)
        self._v_scrollbar.setPageStep(100)
        self._v_scrollbar.setStyleSheet(_scrollbar_style + "QScrollBar:vertical { width: 12px; }")
        self._v_scrollbar.valueChanged.connect(self._on_v_scroll)

        self._h_scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self._h_scrollbar.setRange(0, 1000)
        self._h_scrollbar.setValue(0)
        self._h_scrollbar.setSingleStep(10)
        self._h_scrollbar.setPageStep(100)
        self._h_scrollbar.setStyleSheet(_scrollbar_style + "QScrollBar:horizontal { height: 12px; }")
        self._h_scrollbar.valueChanged.connect(self._on_h_scroll)

        # ── QGridLayout: plot + scrollbars (参考唱歌模式) ──
        _plot_grid = QGridLayout()
        _plot_grid.setContentsMargins(0, 0, 0, 0)
        _plot_grid.setSpacing(0)
        _plot_grid.addWidget(self._plot, 0, 0)
        _plot_grid.addWidget(self._v_scrollbar, 0, 1)
        _plot_grid.addWidget(self._h_scrollbar, 1, 0)
        # 右下角占位方块
        _corner = QWidget()
        _corner.setFixedSize(12, 12)
        _corner.setStyleSheet("background-color: rgba(0,0,0,0.2);")
        _plot_grid.addWidget(_corner, 1, 1)

        layout.addLayout(_plot_grid, stretch=1)

        # 播放头竖线
        self._playhead_line = pg.InfiniteLine(
            pos=0, angle=90, pen=pg.mkPen("#58A6FF", width=2, style=pg.QtCore.Qt.PenStyle.DashLine)
        )
        self._playhead_line.setZValue(8)
        self._playhead_line.setVisible(False)
        self._plot.addItem(self._playhead_line)

        # 横向参考辅助线（半透明虚线，帮助对齐音高目标）
        self._guide_line = pg.InfiniteLine(
            pos=60, angle=0, pen=pg.mkPen("#A78BFA", width=1, style=pg.QtCore.Qt.PenStyle.DotLine)
        )
        self._guide_line.setZValue(1)
        self._guide_line.setVisible(False)
        self._plot.addItem(self._guide_line)

        # 音符条存储 (用于实时颜色更新)
        self._bar_items: List[tuple] = []

        # ── 持久音高线 + 散点（用 setData 更新，避免每帧 remove/create）──
        self._pitch_line = self._plot.plot(
            [], [], pen=pg.mkPen(COLORS["pitch_silver"], width=2.5)
        )
        self._pitch_line.setZValue(5)
        self._pitch_dots = pg.ScatterPlotItem(
            [], [], pen=None, brush=pg.mkBrush(COLORS["pitch_silver"]), size=4
        )
        self._pitch_dots.setZValue(6)
        self._plot.addItem(self._pitch_dots)

        # ── 底部进度条 ──
        self._progress_bar = pg.PlotWidget()
        self._progress_bar.setBackground(COLORS["bg"])
        self._progress_bar.setMaximumHeight(28)
        self._progress_bar.setYRange(0, 1)
        self._progress_bar.setXRange(0, 1)
        self._progress_bar.hideAxis("left")
        self._progress_bar.hideAxis("bottom")
        self._progress_bar.setMenuEnabled(False)
        self._progress_fill = self._progress_bar.plot(
            [0, 0], [0, 1],
            fillLevel=0,
            brush=QColor(COLORS["pitch_gold"]),
            pen=None,
        )
        layout.addWidget(self._progress_bar)

    # ── 公开 API ─────────────────────────────────────

    def load_exercise(self, exercise: VocalExercise, keep_history: bool = False) -> None:
        """加载练习，重置评分状态。

        Args:
            exercise: 要加载的练习
            keep_history: True=保留音高历史（预览切换时），False=完全重置（开始练习时）
        """
        self._exercise = exercise
        self._total_duration = PREPARATION_OFFSET + exercise.duration_seconds + 1.0
        self._elapsed = 0.0
        self._note_index = 0
        self._note_results.clear()
        self._current_grade = PitchGrade.MISS

        if not keep_history:
            self._pitch_history.clear()
            self._time_history.clear()
            self._grade_history.clear()

        self._floating_labels.clear()
        self._bar_states.clear()
        self._streak = 0
        self._show_streak = False

        # 初始化目标音符条状态
        for i in range(len(exercise.notes)):
            self._bar_states[i] = "waiting"

        # ── 先配置 X 轴滚动条范围（避免后续 scrollbar 信号覆盖 Y 轴）──
        self._x_view_range = 8.0  # 默认 8 秒窗口
        self._update_scrollbar_range()

        # ── 调整 Y 轴：以练习音域为中心，但确保 C3~C6 完整可见 ──
        low, high = exercise.midi_range
        # 练习音域外的额外空间（至少能看到上下一个八度）
        margin = 12
        y_lo = float(min(low - margin, 45))   # 不低于 MIDI 45
        y_hi = float(max(high + margin, 72))  # 不低于 MIDI 72
        self._plot.setYRange(y_lo, y_hi)
        self._update_y_ticks(y_lo, y_hi)

        # ── X 轴：始终从 0 开始，宽度自适应 ──
        self._plot.setXRange(0, self._x_view_range)

        # 绘制目标音符条
        self._draw_target_bars()

        # 同步滚动条到实际视图位置
        self._sync_scrollbars_from_view()
        self._redraw()

        # 横向参考辅助线：置于练习的第一个目标音位置
        if len(exercise.notes) > 0:
            first_midi = float(exercise.notes[0].midi_note)
            self._guide_line.setPos(first_midi)
            self._guide_line.setVisible(True)

        self._status_label.setText(f"已加载: {exercise.name}")
        self._score_label.setText("")

    def set_note_active(self, note_index: int) -> None:
        """设定当前激活的音符索引。"""
        self._note_index = note_index
        for i in self._bar_states:
            if i < note_index:
                if self._bar_states[i] == "active":
                    self._bar_states[i] = "waiting"
            elif i == note_index:
                self._bar_states[i] = "active"

    def update_phase(self, phase: str) -> None:
        """更新当前阶段提示。

        Args:
            phase: "countdown" | "reference" | "singing" | "silence" | "finished"
        """
        labels = {
            "countdown": "🔔 预备...",
            "reference": "🎹 聆听参考音",
            "singing": "🎤 跟唱！",
            "silence": "",
            "finished": "✅ 完成",
        }
        self._phase_label.setText(labels.get(phase, ""))

    def update_countdown(self, seconds: int) -> None:
        """更新倒计时显示（准备阶段用）。"""
        if seconds > 0:
            self._phase_label.setText(f"🔔 {seconds}")
        else:
            self._phase_label.setText("🔔 预备...")

    def on_note_graded(self, note_index: int, result: NoteResult) -> None:
        """收到音符评定结果。"""
        self._note_results.append(result)
        self._bar_states[note_index] = "hit" if result.grade != PitchGrade.MISS else "miss"

        # 添加浮动标签
        if result.label:
            note = self._exercise.notes[note_index] if self._exercise else None
            note_midi = note.midi_note if note else 60
            note_time = self._get_note_time(note_index)
            self._add_floating_label(
                text=result.label,
                x=note_time,
                y=float(note_midi),
                color=self._grade_color(result.grade),
            )

        self._current_grade = result.grade
        self._redraw()

    def on_streak_updated(self, streak: int) -> None:
        """连击更新。"""
        self._streak = streak
        if streak >= 3:
            self._show_streak = True
            self._streak_timer = time.time()
            self._streak_label.setText(f"{streak}x STREAK!" if streak >= 3 else "")

    def on_exercise_completed(self, score: ExerciseScore) -> None:
        """练习完成，显示总评。"""
        self._score_label.setText(
            f"{score.total_score:.0f}% — {score.overall_level.name}"
        )
        self._status_label.setText(score.overall_level.description)
        self._streak_label.setText("")
        self._update_progress(1.0)
        self._redraw()

    def feed_pitch_point(self, timestamp: float, freq_hz: float, grade: Optional[PitchGrade] = None) -> None:
        """输入实时音高点用于音高线绘制。"""
        if freq_hz <= 0:
            return
        midi = 69.0 + 12.0 * math.log2(max(freq_hz, 1e-9) / 440.0)
        self._pitch_history.append(midi)
        self._time_history.append(timestamp)
        self._grade_history.append(grade or self._current_grade)

        # 自动清理旧数据
        cutoff = timestamp - self._total_duration
        while self._time_history and self._time_history[0] < cutoff:
            self._time_history.popleft()
            self._pitch_history.popleft()
            if self._grade_history:
                self._grade_history.popleft()

        # 定期日志
        if not hasattr(self, '_feed_dbg_cnt'):
            self._feed_dbg_cnt = 0
        self._feed_dbg_cnt += 1
        if self._feed_dbg_cnt % 60 == 1:
            print(f"[Viz] feed_pitch #{self._feed_dbg_cnt} | t={timestamp:.3f}s "
                  f"freq={freq_hz:.1f}Hz midi={midi:.1f} "
                  f"grade={self._current_grade.name} "
                  f"history_len={len(self._pitch_history)}")

    def set_total_duration(self, total_sec: float) -> None:
        """设置实际总时长（由 AccompanimentEngine 提供，含参考+演唱）。"""
        self._total_duration = max(self._total_duration, total_sec)
        self._update_scrollbar_range()

    def update_elapsed(self, elapsed: float) -> None:
        """更新练习已用时间。"""
        self._elapsed = elapsed
        self._update_progress(elapsed / max(self._total_duration, 1.0))

    def reset(self) -> None:
        """完全重置。"""
        self._exercise = None
        self._elapsed = 0.0
        self._note_index = 0
        self._note_results.clear()
        self._pitch_history.clear()
        self._time_history.clear()
        self._grade_history.clear()
        self._floating_labels.clear()
        self._bar_states.clear()
        self._bar_items.clear()
        self._streak = 0
        self._show_streak = False
        self._playhead_line.setVisible(False)
        self._guide_line.setVisible(False)
        self._pitch_line.setData([], [])
        self._pitch_dots.setData([], [])
        self._x_view_range = 8.0
        self._h_scrollbar.setValue(0)
        self._v_scrollbar.setValue(500)
        self._plot.clear()
        self._plot.setXRange(0, 8)
        self._plot.setYRange(45, 81)
        self._update_y_ticks(45, 81)
        self._phase_label.setText("")
        self._status_label.setText("准备就绪")
        self._score_label.setText("")
        self._streak_label.setText("")

    # ── 内部方法 ─────────────────────────────────────

    def _draw_target_bars(self) -> None:
        """绘制所有目标音符条（存储引用供实时颜色更新）。"""
        if not self._exercise:
            return
        # 清除旧条
        for rect_item, label_item in self._bar_items:
            try:
                self._plot.removeItem(rect_item)
                self._plot.removeItem(label_item)
            except Exception:
                pass
        self._bar_items.clear()

        note_times = self._compute_note_times()

        for i, note in enumerate(self._exercise.notes):
            t_start = note_times[i]
            t_end = note_times[i] + note.duration_beats * self._beat_duration()

            state = self._bar_states.get(i, "waiting")
            color = self._bar_color(state)

            rect_item = pg.QtWidgets.QGraphicsRectItem(
                QRectF(t_start, note.midi_note - 0.4, t_end - t_start, 0.8)
            )
            rect_item.setPen(pg.mkPen(color, width=1))
            rect_item.setBrush(pg.mkBrush(color + "44"))
            rect_item.setZValue(0)
            self._plot.addItem(rect_item)

            label = pg.TextItem(
                note.label, color=COLORS["text"], anchor=(0, 0.5)
            )
            label.setPos(t_start + 0.05, float(note.midi_note))
            label.setFont(QFont("Microsoft YaHei", 8))
            label.setZValue(2)
            self._plot.addItem(label)

            self._bar_items.append((rect_item, label))

    def _beat_duration(self) -> float:
        if not self._exercise:
            return 0.6
        return 60.0 / max(self._exercise.tempo, 1)

    def _compute_note_times(self) -> List[float]:
        """计算每个音符的开始时间 (秒)，含准备时间偏移。

        所有标注从 PREPARATION_OFFSET (3.0s) 开始，
        前3秒为准备/倒计时阶段。
        """
        if not self._exercise:
            return []
        times = []
        t = PREPARATION_OFFSET  # 所有标注从第3秒开始
        for note in self._exercise.notes:
            times.append(t)
            t += note.duration_beats * self._beat_duration()
        return times

    def _get_note_time(self, note_index: int) -> float:
        times = self._compute_note_times()
        if 0 <= note_index < len(times):
            return times[note_index]
        return 0.0

    def _add_floating_label(self, text: str, x: float, y: float, color: str) -> None:
        self._floating_labels.append(_FloatingLabel(
            text=text, x=x, y=y, color=color, birth_time=time.time(),
        ))

    def _redraw(self) -> None:
        """触发重绘（在 _tick 中自动调用）。"""
        pass  # pyqtgraph auto-paints; barrier items are managed in _tick

    def _on_v_scroll(self, value: int) -> None:
        """垂直滚动条 → 平移 Y 轴 (MIDI 音域)。"""
        if self._clamp_guard:
            return
        y_range = self._plot.getViewBox().viewRange()[1]
        y_span = y_range[1] - y_range[0]
        ratio = 1.0 - value / 1000.0
        total_span = 60.0
        new_lo = 40.0 + ratio * (total_span - y_span)
        new_hi = new_lo + y_span
        self._plot.setYRange(new_lo, new_hi, padding=0)
        self._update_y_ticks(new_lo, new_hi)

    def _on_h_scroll(self, value: int) -> None:
        """水平滚动条 → 平移 X 轴 (时间)。"""
        if self._clamp_guard:
            return
        max_time = max(12.0, self._total_duration)
        max_offset = max(0.0, max_time - self._x_view_range)
        if max_offset <= 0:
            self._plot.setXRange(0, self._x_view_range, padding=0)
            return
        ratio = value / 1000.0
        offset_sec = ratio * max_offset
        self._plot.setXRange(offset_sec, offset_sec + self._x_view_range, padding=0)

    def _sync_scrollbars_from_view(self) -> None:
        """根据 ViewBox 当前范围同步滚动条位置。"""
        try:
            x_range, y_range = self._plot.getViewBox().viewRange()
        except Exception:
            return

        y_span = y_range[1] - y_range[0]
        total_span = 60.0
        if total_span > y_span:
            ratio = (y_range[0] - 40.0) / (total_span - y_span)
            ratio = max(0.0, min(1.0, ratio))
            v_val = int((1.0 - ratio) * 1000)
        else:
            v_val = 500
        self._v_scrollbar.blockSignals(True)
        try:
            self._v_scrollbar.setValue(v_val)
        finally:
            self._v_scrollbar.blockSignals(False)

        max_time = max(12.0, self._total_duration)
        max_offset = max(0.0, max_time - self._x_view_range)
        if max_offset > 0:
            ratio = x_range[0] / max_offset
            ratio = max(0.0, min(1.0, ratio))
            h_val = int(ratio * 1000)
        else:
            h_val = 0
        self._h_scrollbar.blockSignals(True)
        try:
            self._h_scrollbar.setValue(h_val)
        finally:
            self._h_scrollbar.blockSignals(False)

    def _update_scrollbar_range(self) -> None:
        """更新横轴滚动条范围（总时长变化时调用）。

        默认视图宽度 ~8 秒（与参考设计一致），长练习通过滚动条平移。
        滚动条始终 0-1000 范围，由 _on_h_scroll 做比例映射。
        """
        total_with_prep = self._total_duration  # 已包含 PREPARATION_OFFSET
        # 默认显示 8 秒窗口，若练习更短则显示全部
        if total_with_prep <= 8.0:
            self._x_view_range = total_with_prep
        else:
            self._x_view_range = 8.0
        # 重置水平滚动条到起点
        self._h_scrollbar.blockSignals(True)
        try:
            self._h_scrollbar.setValue(0)
        finally:
            self._h_scrollbar.blockSignals(False)
        self._plot.setXRange(0, self._x_view_range, padding=0)

    def _update_progress(self, pct: float) -> None:
        pct = max(0.0, min(1.0, pct))
        self._progress_fill.setData([0, pct, pct, 0], [0, 0, 1, 1])

    def _tick(self) -> None:
        """每帧更新：播放头、音符条高亮、音高线、浮动标签。

        滚动逻辑（与普通模式完全一致）：
          - 活跃时间 = _elapsed（如果练习进行中）否则 = 最新音高时间
          - 练习结束后活跃时间冻结在最终位置，视图不再移动
          - 活跃时间超过视图 25% 位置 → 左移视图保持活跃点在 25% 处
        """
        now = time.time()

        # ── 练习结束检测（3秒缓冲，与 _update_ui_tick 自动结束一致）──
        exercise_ended = (
            self._total_duration > 1.0
            and self._elapsed > 0.5
            and self._elapsed >= self._total_duration - 3.0
        )

        # ── 确定活跃时间 ──
        if exercise_ended:
            # 练习结束：冻结在最终位置，不使用环境噪声继续推进
            active_time = self._total_duration - 0.5
        elif self._elapsed > 0.05:
            # 练习进行中：使用伴奏位置
            active_time = self._elapsed
        elif len(self._time_history) > 0:
            # 预览/等待中：使用最新音高时间
            active_time = self._time_history[-1]
        else:
            active_time = 0.0

        # ── 播放头 ──
        if active_time > 0 and self._exercise and len(self._bar_items) > 0:
            self._playhead_line.setPos(active_time)
            self._playhead_line.setVisible(True)

            # ── 自动滚动（与普通模式一致：保持活跃点在视图左侧 25% 处）──
            if not exercise_ended:
                x_left, x_right = self._plot.getViewBox().viewRange()[0]
                view_w = x_right - x_left
                target_left = active_time - view_w * 0.25
                # 只有差异超过 0.5s 才滚动（防止微小抖动）
                if abs(x_left - target_left) > 0.5:
                    new_left = max(0.0, target_left)
                    new_right = new_left + view_w
                    self._plot.setXRange(new_left, new_right, padding=0)
                    self._sync_scrollbars_from_view()
                    if not hasattr(self, '_scroll_log_cnt'):
                        self._scroll_log_cnt = 0
                    self._scroll_log_cnt += 1
                    if self._scroll_log_cnt % 30 == 1:
                        print(f"[Viz] scroll #{self._scroll_log_cnt} | "
                              f"active_t={active_time:.1f}s xRange=[{new_left:.1f}..{new_right:.1f}] "
                              f"ended={exercise_ended}")

            # ── 音符条高亮（使用伴奏位置或活跃时间）──
            highlight_t = self._elapsed if self._elapsed > 0.05 else active_time
            note_times = self._compute_note_times()
            for i, (rect, _) in enumerate(self._bar_items):
                if i >= len(note_times):
                    continue
                t_start = note_times[i]
                note = self._exercise.notes[i]
                t_end = t_start + note.duration_beats * self._beat_duration()

                if t_start <= highlight_t < t_end:
                    state = self._bar_states.get(i, "active")
                    if state == "hit":
                        color = COLORS["pitch_gold_bright"]
                    elif state == "miss":
                        color = COLORS["target_hit_miss"]
                    else:
                        color = "#58A6FF"
                elif highlight_t < t_start:
                    color = COLORS["target_waiting"]
                else:
                    state = self._bar_states.get(i, "waiting")
                    if state == "hit":
                        color = COLORS["pitch_gold_bright"]
                    elif state == "miss":
                        color = COLORS["target_hit_miss"]
                    else:
                        color = COLORS["target_waiting"]

                rect.setPen(pg.mkPen(color, width=1))
                rect.setBrush(pg.mkBrush(color + "44"))

            # ── 动态横向辅助线：跟随当前活跃音符 ──
            if self._exercise:
                # 从播放头位置确定当前活跃音符索引
                note_times = self._compute_note_times()
                current_note_idx = 0
                for i, nt in enumerate(note_times):
                    if highlight_t >= nt:
                        current_note_idx = i
                if current_note_idx < len(self._exercise.notes):
                    self._note_index = current_note_idx
                    active_note_midi = float(self._exercise.notes[current_note_idx].midi_note)
                    self._guide_line.setPos(active_note_midi)
                    self._guide_line.setVisible(True)
        else:
            self._playhead_line.setVisible(False)
            self._guide_line.setVisible(False)

        # ── 绘制音高线（裁剪：只显示播放头左侧的已发生数据，参考普通模式 ECG）──
        if len(self._time_history) > 1:
            times = list(self._time_history)
            pitches = list(self._pitch_history)
            grades = list(self._grade_history) if self._grade_history else []

            if len(times) < 2:
                self._pitch_line.setData([], [])
                self._pitch_dots.setData([], [])
            else:
                if grades:
                    last_grade = grades[-1] if grades else PitchGrade.MISS
                    color = self._grade_color(last_grade)
                else:
                    color = COLORS["pitch_silver"]

                # 音高线：最多渲染 800 点（~16s），散点：最多 200 点（~4s）
                line_n = min(800, len(times))
                self._pitch_line.setData(times[-line_n:], pitches[-line_n:])
                self._pitch_line.setPen(pg.mkPen(color, width=2.5))

                dot_n = min(200, len(times))
                self._pitch_dots.setData(
                    times[-dot_n:], pitches[-dot_n:],
                    brush=pg.mkBrush(color), size=5,
                )

            # ── Y 轴自适应：音高超出范围时扩展（只扩不缩，避免抖动）──
            if len(times) >= 4 and len(pitches) >= 4:
                y_lo, y_hi = self._plot.getViewBox().viewRange()[1]
                # 用 P5/P95 代替 min/max，避免偶发野值拉扯轴范围
                sorted_p = sorted(pitches)
                p5 = sorted_p[max(0, len(sorted_p) // 20)]        # 下 5%
                p95 = sorted_p[min(len(sorted_p) - 1, len(sorted_p) * 19 // 20)]  # 上 95%
                expand_lo = y_lo
                expand_hi = y_hi
                if p5 < y_lo + 2.0:
                    expand_lo = p5 - 4.0
                if p95 > y_hi - 2.0:
                    expand_hi = p95 + 4.0
                if expand_lo < y_lo or expand_hi > y_hi:
                    self._clamp_guard = True
                    try:
                        self._plot.setYRange(expand_lo, expand_hi, padding=0)
                        self._update_y_ticks(expand_lo, expand_hi)
                    finally:
                        self._clamp_guard = False

            # 强制刷新确保渲染
            self._plot.update()

            # 定期日志（仅在有数据时打印）
            if len(times) >= 2:
                if not hasattr(self, '_dbg_cnt'):
                    self._dbg_cnt = 0
                self._dbg_cnt += 1
                if self._dbg_cnt % 60 == 1:
                    xr = self._plot.getViewBox().viewRange()[0]
                    yr = self._plot.getViewBox().viewRange()[1]
                    print(f"[Viz] tick#{self._dbg_cnt} | pts={len(times)}/{len(self._time_history)} "
                          f"active={active_time:.2f}s t=[{times[0]:.2f}..{times[-1]:.2f}] "
                          f"midi=[{pitches[-1]:.1f}] "
                          f"grade={last_grade.name if grades else 'NONE'} "
                          f"xRange=[{xr[0]:.1f}..{xr[1]:.1f}] yRange=[{yr[0]:.1f}..{yr[1]:.1f}]")
        else:
            self._pitch_line.setData([], [])
            self._pitch_dots.setData([], [])

        # ── 浮动标签 ──
        alive = []
        for fl in self._floating_labels:
            age = now - fl.birth_time
            if age < fl.lifetime:
                fl.opacity = max(0.0, 1.0 - age / fl.lifetime)
                fl.y += fl.vy * 0.033

                if not hasattr(fl, "_item") or fl._item is None:
                    fl._item = pg.TextItem(
                        fl.text, color=QColor(fl.color), anchor=(0.5, 0.5))
                    fl._item.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
                    fl._item.setZValue(10)
                    self._plot.addItem(fl._item)

                fl._item.setPos(fl.x, fl.y)
                fl._item.setOpacity(fl.opacity)
                alive.append(fl)
            else:
                if hasattr(fl, "_item") and fl._item is not None:
                    self._plot.removeItem(fl._item)
                    fl._item = None
        self._floating_labels = alive

        # ── 连击标签淡出 ──
        if self._show_streak and now - self._streak_timer > 2.0:
            self._show_streak = False
            self._streak_label.setText("")

    def _update_y_ticks(self, y_lo: float, y_hi: float) -> None:
        """根据当前 Y 轴范围重新生成音名刻度标签。"""
        lo_int = max(0, int(y_lo) - 1)
        hi_int = min(127, int(y_hi) + 2)
        y_ticks = []
        for midi in range(lo_int, hi_int):
            if midi % 12 in (0, 2, 4, 5, 7, 9, 11):
                y_ticks.append((midi, _midi_to_note(midi)))
        self._plot.getAxis("left").setTicks([y_ticks])

    # ── 颜色辅助 ─────────────────────────────────────

    @staticmethod
    def _bar_color(state: str) -> str:
        return {
            "waiting": COLORS["target_waiting"],
            "active":  COLORS["target_active"],
            "hit":     COLORS["pitch_gold_bright"],
            "miss":    COLORS["target_hit_miss"],
        }.get(state, COLORS["target_waiting"])

    @staticmethod
    def _grade_color(grade: PitchGrade) -> str:
        return {
            PitchGrade.PERFECT: COLORS["pitch_gold_bright"],
            PitchGrade.GREAT:   COLORS["pitch_gold"],
            PitchGrade.GOOD:    COLORS["pitch_gold_light"],
            PitchGrade.OK:      COLORS["pitch_silver"],
            PitchGrade.MISS:    COLORS["pitch_silver"],  # 可见银色（区别于音符条的暗灰）
        }.get(grade, COLORS["pitch_silver"])
