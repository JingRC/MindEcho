#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQtGraph 分段音高线渲染器 — 替代 matplotlib draw_segmented_pitch_line。

Phase 1: 核心渲染引擎，独立于 ECGStylePitchVisualizer 可测试。
Phase 2+: 通过 _use_pyqtgraph 标志桥接到主类。
"""

import sys
import numpy as np

# ── 导入 pyqtgraph ──
PYQTGRAPH_AVAILABLE = False
try:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtWidgets
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    pass

# ── 导入 Qt ──
try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    QT_VERSION = 6
except ImportError:
    from PyQt5.QtWidgets import *
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *
    QT_VERSION = 5


# ── 音符标注浮窗（独立矩形标签，置于放大镜上层）──
class _MagnifierLabel(QWidget):
    """音符标注浮窗 — 独立矩形标签，浮于放大镜上方。

    对齐 normal 模式 _magn_overlay_label：单独的 frameless QLabel，
    不在放大镜内部，不受圆形裁剪影响，始终完整显示。
    """

    def __init__(self):
        super().__init__(None)
        try:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.ToolTip |
                Qt.WindowType.WindowStaysOnTopHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        except Exception:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            "color: #e8f0f8; background: #101820; font-size: 10px; "
            "padding: 4px 12px; border: 1px solid rgba(128,200,255,180);"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self.hide()

    def show_at(self, global_pos: QPoint, text: str = ""):
        """在指定全局位置（放大镜顶部中心）上方居中显示标注。"""
        try:
            if not text:
                self.hide()
                return
            self._label.setText(text)
            self.adjustSize()
            # 水平居中于 global_pos，垂直置于其上方 2px
            x = int(global_pos.x() - self.width() // 2)
            y = int(global_pos.y() - self.height() - 2)
            # 屏幕边界修正
            try:
                from PyQt6.QtGui import QGuiApplication
            except Exception:
                from PyQt5.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                if x < geo.x():
                    x = geo.x()
                if x + self.width() > geo.x() + geo.width():
                    x = int(geo.x() + geo.width() - self.width())
                if y < geo.y():
                    y = int(geo.y())
            self.move(x, y)
            self.show()
            self.raise_()
        except Exception:
            self.hide()


# ── 放大镜浮窗（pyqtgraph 版）──
class _MagnifierOverlay(QWidget):
    """圆形放大镜浮窗 — 仅显示放大的像素截图，不含文字。

    对齐 normal 模式 _magn_overlay_window：
    - 圆形裁剪 + 蓝色细边框
    - 音符标注由独立的 _MagnifierLabel 在上层显示
    """

    SIZE = 160          # 直径（像素）
    CAPTURE_HALF = 40   # 抓取半边长（像素），80px → 160px = 2x 放大

    def __init__(self):
        super().__init__(None)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._set_flags()
        self._make_circular_mask()
        self._pixmap = None
        self.hide()

    def _set_flags(self):
        try:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.ToolTip |
                Qt.WindowType.WindowStaysOnTopHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        except Exception:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WA_TranslucentBackground, True)

    def _make_circular_mask(self):
        bitmap = QBitmap(self.SIZE, self.SIZE)
        bitmap.fill(Qt.GlobalColor.color0)
        painter = QPainter(bitmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.GlobalColor.color1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self.SIZE, self.SIZE)
        painter.end()
        self.setMask(bitmap)

    def show_at(self, cursor_global: QPoint, crop_pixmap):
        """在光标附近显示放大镜（偏移 +36px 右, 上方）。"""
        try:
            if crop_pixmap is None or crop_pixmap.isNull():
                self.hide()
                return
            self._pixmap = crop_pixmap

            # 放大镜放在光标右上方
            x = int(cursor_global.x()) + 36
            y = int(cursor_global.y()) - self.SIZE - 36

            # 屏幕边界修正
            try:
                from PyQt6.QtGui import QGuiApplication
            except Exception:
                from PyQt5.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                if x + self.SIZE > geo.x() + geo.width():
                    x = int(cursor_global.x()) - self.SIZE - 36
                if y < geo.y():
                    y = int(cursor_global.y()) + 36

            self.move(x, y)
            self.show()
            self.update()
        except Exception:
            self.hide()

    def paintEvent(self, event):
        if self._pixmap is None or self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 裁剪为圆形
        clip = QPainterPath()
        clip.addEllipse(0, 0, self.SIZE, self.SIZE)
        painter.setClipPath(clip)

        # 填充深色背景
        painter.setBrush(QColor(26, 26, 26))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self.SIZE, self.SIZE)

        # 绘制放大的截图（FastTransformation = 最近邻，像素级清晰）
        scaled = self._pixmap.scaled(
            self.SIZE, self.SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )
        ox = (self.SIZE - scaled.width()) // 2
        oy = (self.SIZE - scaled.height()) // 2
        painter.drawPixmap(ox, oy, scaled)

        # 圆形边框
        painter.setClipping(False)
        pen = QPen(QColor(128, 200, 255, 230))
        pen.setWidthF(1.6)
        try:
            pen.setCosmetic(True)
        except AttributeError:
            pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(1, 1, self.SIZE - 2, self.SIZE - 2)
        painter.end()


class _PitchPlotWidget(pg.PlotWidget):
    """自定义 PlotWidget：滚轮 → Y 轴滚动/Ctrl+滚轮 → X 轴缩放。"""
    wheel_scrolled = pyqtSignal(float, object)  # delta_y, modifiers (Qt.KeyboardModifier)

    def wheelEvent(self, ev):
        delta = ev.angleDelta().y()
        if delta != 0:
            mods = ev.modifiers() if hasattr(ev, 'modifiers') else ev.keyboardModifiers() if hasattr(ev, 'keyboardModifiers') else None
            self.wheel_scrolled.emit(float(delta), mods)
        ev.accept()


class PyQtGraphPitchRenderer(QWidget):
    """pyqtgraph 分段音高线渲染器。

    替代 draw_segmented_pitch_line 的核心渲染。关键设计：
    - PlotDataItem 复用池，通过 setData() 更新，绝不每帧 removeItem + plot
    - NaN 断点连接（connect='finite'），自动处理换气段间的不连线
    - 内置 autoDownsample + clipToView，GPU 级 LOD + 裁剪
    - InfiniteLine 池用于网格，setPos() 更新而非重建
    - 音符标签缓存：仅在内容变化时重建，不每帧销毁创建
    - 范围缓存：set_x_range / set_y_range 跳过未变化的值
    - 滚轮 → Y 轴滚动（对齐正常模式），不缩放 X
    - X 轴起点固定为 0，不允许负时间
    """

    # 池大小常量
    MAX_SEGMENTS = 60       # 同时活跃分段数上限
    MAX_GRID_LINES = 40     # 水平网格线数上限

    @staticmethod
    def _make_feather_cursor():
        """生成蓝色羽毛 QCursor（对齐 normal 模式 _ensure_blue_feather_cursor）。"""
        try:
            try:
                from PyQt6.QtGui import (
                    QCursor, QPixmap, QPainter, QPen, QBrush,
                    QColor, QPainterPath, QLinearGradient,
                )
            except Exception:
                from PyQt5.QtGui import (
                    QCursor, QPixmap, QPainter, QPen, QBrush,
                    QColor, QPainterPath, QLinearGradient,
                )
            size = 36
            pm = QPixmap(size, size)
            pm.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pm)
            try:
                try:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                except Exception:
                    painter.setRenderHint(QPainter.Antialiasing, True)

                path = QPainterPath()
                path.moveTo(7, 8)
                path.cubicTo(12, 3, 22, 3, 29, 12)
                path.cubicTo(31, 16, 29, 24, 22, 29)
                path.cubicTo(16, 33, 10, 28, 10, 22)
                path.cubicTo(10, 18, 12, 14, 15, 12)
                stem = QPainterPath()
                stem.moveTo(13, 31)
                stem.lineTo(24, 9)

                shadow = QPainterPath(path)
                shadow.translate(1.5, 1.5)
                painter.setPen(QPen(QColor(0, 0, 0, 50), 1.0))
                painter.setBrush(QBrush(QColor(0, 0, 0, 40)))
                painter.drawPath(shadow)

                blue = QColor(66, 170, 255)
                blue2 = QColor(30, 120, 210)
                dark = QColor(24, 96, 168)
                grad = QLinearGradient(7, 8, 29, 30)
                grad.setColorAt(0.0, blue)
                grad.setColorAt(1.0, blue2)
                painter.setPen(QPen(dark, 1.2))
                painter.setBrush(QBrush(grad))
                painter.drawPath(path)
                painter.setPen(QPen(dark, 1.5))
                painter.drawPath(stem)
            finally:
                painter.end()

            try:
                return QCursor(pm, 7, 8)
            except Exception:
                return QCursor(pm)
        except Exception:
            return None

    def __init__(self, parent=None):
        super().__init__(parent)

        if not PYQTGRAPH_AVAILABLE:
            layout = QVBoxLayout(self)
            label = QLabel("pyqtgraph not available\npip install pyqtgraph")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: red; font-size: 14px;")
            layout.addWidget(label)
            self._ready = False
            return

        self._ready = True

        # ── 布局 ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── PlotWidget 配置 ──
        pg.setConfigOption('background', '#1a1a1a')
        pg.setConfigOption('foreground', '#ffffff')
        pg.setConfigOption('antialias', True)   # 启用抗锯齿，消除音调线锯齿

        self.plot_widget = _PitchPlotWidget()
        self.plot_widget.setLabel('left', 'Pitch (octave)', color='#aaaaaa')
        self.plot_widget.setLabel('bottom', 'Time (s)', color='#aaaaaa')
        self.plot_widget.showGrid(x=True, y=False, alpha=0.15)

        # 禁用自动范围，防止 setData() 触发 auto-range 后再被 setXRange 覆盖（双重刷新）
        vb = self.plot_widget.getViewBox()
        vb.disableAutoRange()
        vb.setAutoVisible(y=False)

        # Y 轴默认范围：1-7 八度（对应 C2-C7）
        self.plot_widget.setYRange(1.0, 7.0, padding=0.02)
        self.plot_widget.setXRange(0, 16.0, padding=0.0)

        # Y 轴：显示音调标签（通过 setTicks 动态更新）
        self._left_axis = self.plot_widget.getPlotItem().getAxis('left')
        self._left_axis.setStyle(showValues=True)
        self._left_axis.setPen(pg.mkPen(color='#555555', width=1))
        self._left_axis.setTextPen(pg.mkPen(color='#999999'))
        self._left_axis.setStyle(tickTextOffset=5)
        self._setup_y_axis_ticks(1.0, 7.0, 'zoom_1_5')  # 初始默认（对齐 zoom_level=1.0）

        # ── 鼠标交互配置 ──
        vb.setMouseEnabled(x=True, y=False)    # 左键拖拽平移 X（时间），禁止平移 Y
        vb.setMouseMode(vb.PanMode)            # 左键平移，右键缩放框

        # 滚轮 → Y 轴滚动（对齐正常模式 on_mouse_scroll）
        self.plot_widget.wheel_scrolled.connect(self._on_wheel)
        self.on_wheel_scroll = None  # callable(delta_y)，由父组件设置

        self.plot_widget.scene().sigMouseClicked.connect(self._on_mouse_clicked)
        vb.sigRangeChangedManually.connect(self._on_user_view_changed)

        # ── 蓝色羽毛光标（对齐 normal 模式 _ensure_blue_feather_cursor）──
        self._feather_cursor = self._make_feather_cursor()
        self._feather_cursor_active = False
        try:
            self.plot_widget.viewport().setMouseTracking(True)
        except Exception:
            pass

        # ── 辅助线（对齐正常模式 update_guides）──
        #  主线和柔光底线叠加实现 glow 效果
        #  样式对齐 normal 模式: 银灰 #C0C0C0，主线细虚线 + 柔光底线
        guide_glow_pen = pg.mkPen(color='#C0C0C0', width=2.2, style=QtCore.Qt.PenStyle.SolidLine)
        guide_main_pen = pg.mkPen(color='#C0C0C0', width=0.8, style=QtCore.Qt.PenStyle.DashLine)

        self._v_guide_glow = pg.InfiniteLine(angle=90, pen=guide_glow_pen, movable=False)
        self._v_guide_main = pg.InfiniteLine(angle=90, pen=guide_main_pen, movable=False)
        self._v_guide_glow.setOpacity(0.12)
        self._v_guide_main.setOpacity(0.90)
        self._v_guide_glow.setZValue(80)
        self._v_guide_main.setZValue(90)
        self._v_guide_glow.setVisible(False)
        self._v_guide_main.setVisible(False)
        self.plot_widget.addItem(self._v_guide_glow)
        self.plot_widget.addItem(self._v_guide_main)

        self._h_guide_glow = pg.InfiniteLine(angle=0, pen=guide_glow_pen, movable=False)
        self._h_guide_main = pg.InfiniteLine(angle=0, pen=guide_main_pen, movable=False)
        self._h_guide_glow.setOpacity(0.12)
        self._h_guide_main.setOpacity(0.90)
        self._h_guide_glow.setZValue(80)
        self._h_guide_main.setZValue(90)
        self._h_guide_glow.setVisible(False)
        self._h_guide_main.setVisible(False)
        self.plot_widget.addItem(self._h_guide_glow)
        self.plot_widget.addItem(self._h_guide_main)

        self._guides_enabled = True
        self._guides_visible = False

        # 注意：辅助线不由鼠标驱动，而是由父组件根据 current_global_time / last_active_pitch_y 更新
        # （对齐 normal 模式 update_guides 行为）

        layout.addWidget(self.plot_widget)

        # ── 回调（由父组件设置，用于状态回写）──
        self.on_view_changed = None  # callable(x_range, y_range)
        self.on_click_at_time = None  # callable(time_x, y_value, scene_pos, event)
        self.on_hover_info = None    # callable(x, y, text) — 格式化悬停文本
        self.on_selection_drag = None    # callable(x, y) — 选区拖拽中
        self.on_selection_release = None  # callable() — 选区拖拽结束
        self.on_listenback_button = None  # callable('play'|'pause'|'stop') — 回听控制按钮
        self.on_mouse_press_data = None   # callable(x, y) -> bool — press 时检测交互类型，返回 True 表示已拦截

        # ── 悬停高亮 + 注记（对齐 normal 模式样式）──
        # 柔光：半透明浅蓝，视觉直径约 21px
        self._hover_glow = pg.ScatterPlotItem(
            [0], [0], size=22, pen=None, brush=pg.mkBrush('#3388ff'), pxMode=True
        )
        self._hover_glow.setOpacity(0.25)
        self._hover_glow.setZValue(100)
        self._hover_glow.setVisible(False)
        self.plot_widget.addItem(self._hover_glow)

        # 外环：透明填充 + 淡蓝白细边，视觉直径约 10px
        self._hover_ring = pg.ScatterPlotItem(
            [0], [0], size=12, pen=pg.mkPen('#c0d8ff', width=1.4), brush=None, pxMode=True
        )
        self._hover_ring.setOpacity(0.92)
        self._hover_ring.setZValue(101)
        self._hover_ring.setVisible(False)
        self.plot_widget.addItem(self._hover_ring)

        self._hover_annot = pg.TextItem(
            '', color='#ffffff', anchor=(0.5, 1.0),
            fill=pg.mkBrush(0, 0, 0, 180)
        )
        self._hover_annot.setZValue(102)
        self._hover_annot.setVisible(False)
        self.plot_widget.addItem(self._hover_annot)

        self._hover_hit_radius = 18  # 命中半径（像素），对齐 normal 模式
        self._hover_last_t = 0.0
        self._hover_throttle_sec = 0.03  # ~33Hz，比 normal 模式更灵敏

        # ── 悬停滞回：避免在相邻点间频繁跳变（对齐 normal 模式的隐式稳定）──
        self._hover_last_point = None     # (x, y) 上一帧命中的点
        self._hover_stick_radius2 = 64.0  # 滞回距离²（8px），在此范围内保持上一命中点

        # ── 放大镜浮窗 + 独立标注标签（对齐 normal 模式 _magn_overlay_window + _magn_overlay_label）──
        self._magnifier = _MagnifierOverlay()
        self._magn_label = _MagnifierLabel()
        self._magn_enabled = True

        # ── 选区拖拽状态 ──
        self._sel_dragging = False  # 由父组件控制，True 时 viewport 事件过滤器转发拖拽事件

        # ── 鼠标追踪 ──
        # viewport 事件过滤器：捕获原始 widget 像素坐标（不受 ViewBox 范围变化影响）
        try:
            vp = self.plot_widget.viewport()
            vp.installEventFilter(self)
        except Exception:
            pass
        self._cursor_widget_pos = QtCore.QPointF(0, 0)
        self._cursor_global_pos = QtCore.QPointF(0, 0)

        self._mouse_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=60, slot=self._on_mouse_moved
        )

        # ── 艺术家复用池 ──
        self._line_pool: list = []       # PlotDataItem 列表（分段线）
        self._scatter_pool: list = []    # PlotDataItem 列表（分段散点）
        self._grid_lines: list = []      # InfiniteLine 列表（水平网格）
        self._playhead: object = None    # InfiniteLine（播放头）
        self._sel_left: object = None    # InfiniteLine（选区左边界）
        self._sel_right: object = None   # InfiniteLine（选区右边界）
        self._note_labels: list = []     # TextItem 列表（音符标签）

        self._init_pools()

        # ── 缓存（避免重复计算/刷新）──
        self._current_segment_count = 0
        self._segments_cache: list = []  # 当前活跃 segments（供悬停命中检测）
        self._last_x_range = (None, None)
        self._last_y_range = (None, None)
        self._last_grid_cache_key = None
        self._last_note_label_key = None
        self._note_label_data = []

    # ═══════════════════════════════════════════
    # 池初始化
    # ═══════════════════════════════════════════

    def _init_pools(self):
        """预分配艺术家池。创建后通过 setData() 更新，不再新建/删除。"""
        base_pen = pg.mkPen(color='#ff6b35', width=1.5)
        # 透明符号笔（对齐 matplotlib edgecolors='none'）
        base_scatter_pen = pg.mkPen(None)

        for _ in range(self.MAX_SEGMENTS):
            line = self.plot_widget.plot(
                [], [],
                pen=base_pen,
                connect='finite',
                skipFiniteCheck=True,
                autoDownsample=True,
                clipToView=True,
                antialias=True,
            )
            line.setVisible(False)
            self._line_pool.append(line)

            scatter = self.plot_widget.plot(
                [], [],
                pen=None,
                symbol='o',
                symbolSize=4,         # 默认大小（像素），后续由 set_point_size 动态更新
                symbolBrush='#ffffff',
                symbolPen=base_scatter_pen,
                skipFiniteCheck=True,
                autoDownsample=False,  # 散点不降采样，保留所有细节点
                clipToView=True,       # 但仍只渲染可见范围
                antialias=True,
            )
            scatter.setVisible(False)
            self._scatter_pool.append(scatter)

        self._line_color = '#ff6b35'
        self._line_width = 1.5
        self._point_size = 5

    # ═══════════════════════════════════════════
    # 公开 API（与现有 matplotlib 调用方对齐）
    # ═══════════════════════════════════════════

    # 音符名称表
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    def _pitch_to_note(self, y_val):
        """将八度制音高值转换为音符名（如 4.0 → 'C4', 4.0833 → 'C#4'）。"""
        octave = int(y_val)
        semitone = int(round((y_val - octave) * 12))
        if semitone >= 12:
            octave += 1
            semitone = 0
        elif semitone < 0:
            octave -= 1
            semitone = 11
        return f'{self.NOTE_NAMES[semitone]}{octave}'

    @staticmethod
    def _should_show_note(octave, semitone, zoom_mode):
        """依据 zoom 配置判断该半音是否应显示（对齐正常模式 _get_zoom_profile 的 note_filter）。
        返回 (show: bool, is_major: bool) — is_major 用于样式加权。"""
        if zoom_mode is None:
            # 无 profile 时回退：所有 C 为 major，其余显示
            return True, (semitone == 0)

        if zoom_mode == 'zoom_0_5':
            return (semitone == 0 and 3 <= octave <= 5), True
        if zoom_mode == 'zoom_0_8':
            return (semitone == 0), True
        if zoom_mode == 'zoom_1_5':
            # C(0), F(5), G(7)
            return (semitone in (0, 5, 7)), (semitone == 0)
        if zoom_mode == 'zoom_2_5':
            if 3 <= octave <= 5:
                # 窗口内全自然音 (C,D,E,F,G,A,B)
                show = semitone in (0, 2, 4, 5, 7, 9, 11)
            else:
                show = semitone in (0, 5, 7)
            return show, (semitone == 0)
        # zoom_5_0: 全部半音
        return True, (semitone == 0)

    def _setup_y_axis_ticks(self, y_start, y_end, zoom_mode):
        """根据可见范围和 zoom 配置设置 Y 轴刻度标签（音符名）。
        使用与正常模式一致的 note_filter 过滤，避免标签拥挤。"""
        ticks = []
        for octave in range(max(0, int(y_start) - 1), min(9, int(y_end) + 2)):
            for semitone in range(12):
                y_pos = octave + semitone / 12.0
                if not (y_start <= y_pos <= y_end):
                    continue
                show, _is_major = self._should_show_note(octave, semitone, zoom_mode)
                if not show:
                    continue
                name = self.NOTE_NAMES[semitone]
                ticks.append((y_pos, f'{name}{octave}'))

        if ticks:
            self._left_axis.setTicks([ticks, []])
        else:
            self._left_axis.setTicks([[], []])

    def set_segments(self, segments):
        """更新分段音高数据。

        Args:
            segments: list of (times_list, pitches_list) tuples.
        """
        if not self._ready:
            return

        # ── 诊断：首帧和每 120 帧输出一次 ──
        if not hasattr(self, '_pg_set_seg_cnt'):
            self._pg_set_seg_cnt = 0
        self._pg_set_seg_cnt += 1
        diag = (self._pg_set_seg_cnt <= 2 or self._pg_set_seg_cnt % 120 == 0)
        if diag:
            total_pts = sum(len(s[0]) for s in segments) if segments else 0
            print(f"[PG_SET_SEG] call=#{self._pg_set_seg_cnt} n_segs={len(segments)} total_pts={total_pts}")

        n = min(len(segments), self.MAX_SEGMENTS)
        gap_thr = 0.14  # 段内断开阈值（对齐 matplotlib line_gap_thr_local）

        for i in range(self.MAX_SEGMENTS):
            line = self._line_pool[i]
            scatter = self._scatter_pool[i]

            if i < n:
                try:
                    ts, ps = segments[i]
                except (IndexError, ValueError, TypeError):
                    line.setVisible(False)
                    scatter.setVisible(False)
                    continue

                if len(ts) < 1 or len(ps) < 1:
                    line.setVisible(False)
                    scatter.setVisible(False)
                    continue

                x = np.asarray(ts, dtype=np.float64)
                y = np.asarray(ps, dtype=np.float64)
                mn = min(len(x), len(y))
                x, y = x[:mn], y[:mn]

                # ── 线段：段内大间隔插入 NaN（对齐 matplotlib 的 NaN 断点逻辑）──
                if mn >= 2:
                    gap_x = [x[0]]
                    gap_y = [y[0]]
                    for j in range(1, mn):
                        if x[j] - x[j-1] > gap_thr:
                            gap_x.append(float('nan'))
                            gap_y.append(float('nan'))
                        gap_x.append(x[j])
                        gap_y.append(y[j])
                    line_x = np.asarray(gap_x, dtype=np.float64)
                    line_y = np.asarray(gap_y, dtype=np.float64)
                else:
                    line_x, line_y = x, y

                line.setData(line_x, line_y)
                line.setVisible(True)

                # ── 散点：始终显示（不因点数多而隐藏），用原始数据 ──
                scatter.setData(x, y)
                scatter.setVisible(True)
            else:
                for j in range(i, self.MAX_SEGMENTS):
                    self._line_pool[j].setVisible(False)
                    self._scatter_pool[j].setData([], [])
                    self._scatter_pool[j].setVisible(False)
                break

        self._current_segment_count = n
        self._segments_cache = segments[:n]  # 缓存供悬停命中检测

    def set_x_range(self, x_min, x_max):
        """设置 X 轴可见范围（时间窗）。X 轴起点固定为 0，不允许负时间。"""
        if not self._ready:
            return
        if not (x_max > x_min):
            return
        x_min = float(x_min)
        x_max = float(x_max)
        if x_min < 0:
            x_max -= x_min  # 保持窗口宽度不变
            x_min = 0.0
        key = (x_min, x_max)
        if key == self._last_x_range:
            return
        self._last_x_range = key
        self.plot_widget.setXRange(key[0], key[1], padding=0.0)
        self._update_note_label_x(key[0])

    def set_y_range(self, y_min, y_max):
        """设置 Y 轴可见范围（音高窗）。跳过未变化的值。"""
        if not self._ready:
            return
        if not (y_max > y_min):
            return
        key = (float(y_min), float(y_max))
        if key == self._last_y_range:
            return
        self._last_y_range = key
        self.plot_widget.setYRange(key[0], key[1], padding=0.02)

    def set_grid_lines(self, positions):
        """设置水平网格线位置（八度/半音边界）。"""
        if not self._ready:
            return
        positions = positions[:self.MAX_GRID_LINES]

        while len(self._grid_lines) < len(positions):
            hl = pg.InfiniteLine(
                angle=0,
                pen=pg.mkPen(color='#ffffff', width=0.5, style=QtCore.Qt.PenStyle.DashLine),
            )
            hl.setOpacity(0.12)
            self.plot_widget.addItem(hl)
            self._grid_lines.append(hl)

        for i, hl in enumerate(self._grid_lines):
            if i < len(positions):
                hl.setPos(float(positions[i]))
                hl.setVisible(True)
            else:
                hl.setVisible(False)

    def set_playhead(self, x):
        """设置播放头位置。"""
        if not self._ready:
            return
        if x is None:
            if self._playhead is not None:
                self._playhead.setVisible(False)
            return

        if self._playhead is None:
            self._playhead = pg.InfiniteLine(
                angle=90,
                pen=pg.mkPen(color='#5dade2', width=1.5),
            )
            self._playhead.setZValue(148)
            self.plot_widget.addItem(self._playhead)

        self._playhead.setPos(float(x))
        self._playhead.setVisible(True)

    def clear(self):
        """清空所有数据。"""
        if not self._ready:
            return
        for line in self._line_pool:
            line.setData([], [])
            line.setVisible(False)
        for scatter in self._scatter_pool:
            scatter.setData([], [])
            scatter.setVisible(False)
        self._current_segment_count = 0
        self._segments_cache = []
        self._hover_last_point = None
        self._hide_hover()
        self._hide_magnifier()

    def set_grid_from_range(self, y_start, y_end, zoom_mode=None):
        """根据可见 Y 范围计算并设置网格线 + Y 轴刻度 + 音符标签。

        使用与正常模式 _get_zoom_profile 一致的 note_filter，
        仅显示当前缩放配置下的相关音调，避免标签拥挤。
        """
        if not self._ready:
            return

        # 缓存
        cache_key = (round(y_start, 3), round(y_end, 3), zoom_mode)
        if cache_key == self._last_grid_cache_key:
            return
        self._last_grid_cache_key = cache_key

        # ── 网格线 ──
        pen_cache = {}
        def _get_pen(style, width):
            k = (style, width)
            if k not in pen_cache:
                pens = {
                    'solid': QtCore.Qt.PenStyle.SolidLine,
                    'dash': QtCore.Qt.PenStyle.DashLine,
                    'dot': QtCore.Qt.PenStyle.DotLine,
                }
                pen_cache[k] = pg.mkPen(color='#ffffff', width=width, style=pens.get(style, QtCore.Qt.PenStyle.SolidLine))
            return pen_cache[k]

        grid_entries = []

        for octave in range(max(0, int(y_start) - 1), min(9, int(y_end) + 2)):
            for semitone in range(12):
                y_pos = octave + semitone / 12.0
                if not (y_start <= y_pos <= y_end):
                    continue
                show, is_major = self._should_show_note(octave, semitone, zoom_mode)
                if not show:
                    continue
                if is_major:  # C 音 → 实线较明显
                    grid_entries.append((y_pos, _get_pen('solid', 1.5), 0.55))
                elif semitone in (2, 4, 5, 7, 9, 11):  # 自然音 → 虚线
                    grid_entries.append((y_pos, _get_pen('dash', 0.4), 0.30))
                else:  # 升降半音 → 点线
                    grid_entries.append((y_pos, _get_pen('dot', 0.3), 0.18))

        self._set_grid_entries(grid_entries)

        # ── Y 轴刻度 ──
        self._setup_y_axis_ticks(y_start, y_end, zoom_mode)

        # ── 音符标签 TextItem ──
        note_labels = []
        for octave in range(max(0, int(y_start)), min(9, int(y_end) + 2)):
            for semitone in range(12):
                y_pos = octave + semitone / 12.0
                if not (y_start <= y_pos <= y_end):
                    continue
                show, _is_major = self._should_show_note(octave, semitone, zoom_mode)
                if not show:
                    continue
                name = self.NOTE_NAMES[semitone]
                note_labels.append((y_pos, f'{name}{octave}'))
        self._set_note_labels(note_labels)

    def _set_grid_entries(self, entries):
        """内部：将网格条目应用到 InfiniteLine 池。"""
        n = min(len(entries), self.MAX_GRID_LINES)

        while len(self._grid_lines) < n:
            hl = pg.InfiniteLine(angle=0, pen=pg.mkPen(color='#ffffff', width=0.5))
            self.plot_widget.addItem(hl)
            self._grid_lines.append(hl)

        for i, hl in enumerate(self._grid_lines):
            if i < n:
                y_pos, pen, alpha = entries[i]
                hl.setPos(y_pos)
                hl.setPen(pen)
                hl.setOpacity(alpha)
                hl.setVisible(True)
            else:
                hl.setVisible(False)

    def _set_note_labels(self, labels):
        """内部：仅当标签内容变化时才重建 TextItem（避免每帧销毁创建的巨大开销）。"""
        cache_key = tuple((round(y, 4), t) for y, t in labels)
        if cache_key == self._last_note_label_key:
            return
        self._last_note_label_key = cache_key

        # 清除旧标签
        for txt in self._note_labels:
            try:
                self.plot_widget.removeItem(txt)
            except Exception:
                pass
        self._note_labels.clear()

        self._note_label_data = labels

        x_left = self._last_x_range[0] if self._last_x_range[0] is not None else 0.0

        for y_pos, text in labels:
            txt = pg.TextItem(
                text=text,
                color='#999999',
                anchor=(1, 0.5),
            )
            txt.setFont(QFont('sans-serif', 9))
            txt.setOpacity(0.6)
            txt.setPos(float(x_left), y_pos)
            self.plot_widget.addItem(txt)
            self._note_labels.append(txt)

    def _update_note_label_x(self, x_left):
        """更新所有音符标签的 X 位置，使其固定在视图左边缘。"""
        fx = float(x_left)
        for txt in self._note_labels:
            try:
                txt.setPos(fx, txt.pos().y())
            except Exception:
                pass

    def set_selection_range(self, x_left, x_right):
        """设置选区范围标记（回听/重录选区边界）。"""
        if not self._ready:
            return

        for pos, attr in [(x_left, '_sel_left'), (x_right, '_sel_right')]:
            line = getattr(self, attr, None)
            if pos is None:
                if line is not None:
                    line.setVisible(False)
                continue
            if line is None:
                line = pg.InfiniteLine(
                    angle=90,
                    pen=pg.mkPen(color='#FFB6C1', width=0.8),
                )
                line.setOpacity(0.88)
                line.setZValue(150)
                self.plot_widget.addItem(line)
                setattr(self, attr, line)
            line.setPos(float(pos))
            line.setVisible(True)

        self.set_selection_triangles(x_left, x_right)

    # ═══════════════════════════════════════════
    # 回听控制按钮（play ▶ / pause ⏸ / stop ⏹）
    # ═══════════════════════════════════════════

    _lb_ctrl_play = None       # pg.PlotDataItem (right-pointing triangle)
    _lb_ctrl_pause_left = None  # pg.PlotDataItem (square)
    _lb_ctrl_pause_right = None # pg.PlotDataItem (square)
    _lb_ctrl_stop = None        # pg.PlotDataItem (square)
    _lb_ctrl_hit_play = None    # (x0, x1, y0, y1) 数据坐标命中区
    _lb_ctrl_hit_pause = None
    _lb_ctrl_hit_stop = None

    # 选区三角形标记（对齐 normal 模式 _sel_tri_top/bot_left/right）
    _sel_tri_top_left = None    # pg.PlotDataItem
    _sel_tri_bot_left = None    # pg.PlotDataItem
    _sel_tri_top_right = None   # pg.PlotDataItem
    _sel_tri_bot_right = None   # pg.PlotDataItem

    def set_listenback_controls(self, show_play, show_pause_stop, center_x, center_y, size):
        """设置回听控制按钮的位置、大小和可见性（使用 PlotDataItem 原生符号）。

        Args:
            show_play: 是否显示播放按钮 ▶
            show_pause_stop: 是否显示暂停 ⏸ 和停止 ⏹ 按钮
            center_x, center_y: 按钮组中心（数据坐标）
            size: 按钮总尺寸（数据单位）
        """
        if not self._ready:
            return
        try:
            vb = self.plot_widget.getViewBox()
            # 将数据尺寸转换为像素尺寸
            view_h = max(vb.rect().height(), 1)
            y0, y1 = float(vb.viewRange()[1][0]), float(vb.viewRange()[1][1])
            sy = view_h / max(abs(y1 - y0), 0.001)
            s = float(size)
            half = s * 0.5
            cx, cy = float(center_x), float(center_y)
            # 数据尺寸 → 像素尺寸（以视图高度为基准）
            px_size = lambda d: max(d * sy, 0.5)

            # ── 播放按钮（绿色右指三角 ▶）──
            if show_play:
                play_path = QPainterPath()
                play_path.moveTo(-0.4, -0.55)
                play_path.lineTo(-0.4, 0.55)
                play_path.lineTo(0.6, 0)
                play_path.closeSubpath()
                psize = max(px_size(s), 14)
                if self._lb_ctrl_play is None:
                    self._lb_ctrl_play = pg.PlotDataItem(
                        [cx], [cy], pen=None,
                        symbol=play_path,
                        symbolBrush=pg.mkBrush(0, 200, 100, 200),
                        symbolPen=pg.mkPen(0, 180, 80, 1),
                        symbolSize=psize,
                    )
                    self._lb_ctrl_play.setZValue(149)
                    self.plot_widget.addItem(self._lb_ctrl_play)
                else:
                    self._lb_ctrl_play.setData([cx], [cy])
                    self._lb_ctrl_play.opts['symbolSize'] = psize
                    self._lb_ctrl_play.updateItems()
                self._lb_ctrl_hit_play = (cx - half, cx + half, cy - half, cy + half)
            else:
                if self._lb_ctrl_play is not None:
                    self._lb_ctrl_play.setData([], [])
                self._lb_ctrl_hit_play = None

            # ── 暂停 + 停止按钮 ──
            if show_pause_stop:
                bar_w_data = s * 0.25
                inner_gap_data = s * 0.24
                # spread pause group and stop button further apart
                pause_cx = cx - s * 0.82
                stop_cx = cx + s * 1.08

                # 暂停条中心 = 组中心 ± (内间距/2 + 条宽/2)
                left_x = pause_cx - inner_gap_data * 0.5 - bar_w_data * 0.5
                right_x = pause_cx + inner_gap_data * 0.5 + bar_w_data * 0.5
                # 条的高度 ≈ s（与 normal 模式 bar_h*2 = s 一致）
                bar_size = max(px_size(s * 0.55), 14)

                if self._lb_ctrl_pause_left is None:
                    self._lb_ctrl_pause_left = pg.PlotDataItem(
                        [left_x], [cy], pen=None,
                        symbol='s',
                        symbolBrush=pg.mkBrush(255, 255, 255, 180),
                        symbolPen=pg.mkPen(220, 220, 220, 1),
                        symbolSize=bar_size,
                    )
                    self._lb_ctrl_pause_left.setZValue(149)
                    self.plot_widget.addItem(self._lb_ctrl_pause_left)
                else:
                    self._lb_ctrl_pause_left.setData([left_x], [cy])
                    self._lb_ctrl_pause_left.opts['symbolSize'] = bar_size
                    self._lb_ctrl_pause_left.updateItems()

                if self._lb_ctrl_pause_right is None:
                    self._lb_ctrl_pause_right = pg.PlotDataItem(
                        [right_x], [cy], pen=None,
                        symbol='s',
                        symbolBrush=pg.mkBrush(255, 255, 255, 180),
                        symbolPen=pg.mkPen(220, 220, 220, 1),
                        symbolSize=bar_size,
                    )
                    self._lb_ctrl_pause_right.setZValue(149)
                    self.plot_widget.addItem(self._lb_ctrl_pause_right)
                else:
                    self._lb_ctrl_pause_right.setData([right_x], [cy])
                    self._lb_ctrl_pause_right.opts['symbolSize'] = bar_size
                    self._lb_ctrl_pause_right.updateItems()

                # 暂停命中区正方形
                pause_size = s * 1.00
                pause_x0 = pause_cx - pause_size * 0.5
                pause_y0 = cy - pause_size * 0.5
                self._lb_ctrl_hit_pause = (pause_x0, pause_x0 + pause_size, pause_y0, pause_y0 + pause_size)

                # ── 停止按钮（红色方块 ⏹）──
                stop_size_data = s * 1.00
                stop_x0 = stop_cx - stop_size_data * 0.5
                stop_y0 = cy - stop_size_data * 0.5
                stop_px = max(px_size(stop_size_data), 14)

                if self._lb_ctrl_stop is None:
                    self._lb_ctrl_stop = pg.PlotDataItem(
                        [stop_cx], [cy], pen=None,
                        symbol='s',
                        symbolBrush=pg.mkBrush(220, 60, 60, 200),
                        symbolPen=pg.mkPen(180, 40, 40, 1),
                        symbolSize=stop_px,
                    )
                    self._lb_ctrl_stop.setZValue(149)
                    self.plot_widget.addItem(self._lb_ctrl_stop)
                else:
                    self._lb_ctrl_stop.setData([stop_cx], [cy])
                    self._lb_ctrl_stop.opts['symbolSize'] = stop_px
                    self._lb_ctrl_stop.updateItems()
                self._lb_ctrl_hit_stop = (stop_x0, stop_x0 + stop_size_data, stop_y0, stop_y0 + stop_size_data)
            else:
                for attr in ('_lb_ctrl_pause_left', '_lb_ctrl_pause_right', '_lb_ctrl_stop'):
                    item = getattr(self, attr, None)
                    if item is not None:
                        item.setData([], [])
                self._lb_ctrl_hit_pause = None
                self._lb_ctrl_hit_stop = None

        except Exception:
            pass

    def hide_listenback_controls(self):
        """隐藏所有回听控制按钮。"""
        for attr in ('_lb_ctrl_play', '_lb_ctrl_pause_left', '_lb_ctrl_pause_right', '_lb_ctrl_stop',
                     '_lb_ctrl_hit_play', '_lb_ctrl_hit_pause', '_lb_ctrl_hit_stop'):
            if attr.startswith('_lb_ctrl_hit'):
                setattr(self, attr, None)
            else:
                item = getattr(self, attr, None)
                if item is not None:
                    item.setData([], [])
        self._hide_selection_triangles()

    def set_selection_triangles(self, x_left, x_right):
        """设置选区边界顶部/底部的三角形标记（使用 PlotDataItem 原生符号）。

        在左右框线的上下两端各放置一个灰色小三角，指示选区边界。

        Args:
            x_left: 左框线 X 数据坐标（None 则隐藏）
            x_right: 右框线 X 数据坐标（None 则隐藏）
        """
        if not self._ready:
            return
        try:
            vb = self.plot_widget.getViewBox()
            y_range = vb.viewRange()[1]
            ymin, ymax = float(y_range[0]), float(y_range[1])
            view_h = max(vb.rect().height(), 1)

            tri_h = max(0.06, (ymax - ymin) * 0.04)
            sy = view_h / max(abs(ymax - ymin), 0.001)
            tri_px = max(tri_h * sy, 8)  # 三角像素大小，最小 8px

            # 向上三角（顶点在上）
            tri_up = QPainterPath()
            tri_up.moveTo(0, -0.55)
            tri_up.lineTo(0.5, 0.45)
            tri_up.lineTo(-0.5, 0.45)
            tri_up.closeSubpath()

            # 向下三角（顶点在下）
            tri_down = QPainterPath()
            tri_down.moveTo(0, 0.55)
            tri_down.lineTo(0.5, -0.45)
            tri_down.lineTo(-0.5, -0.45)
            tri_down.closeSubpath()

            tri_brush = pg.mkBrush(0xA0, 0xA0, 0xA0, 242)

            for attr, cx, cy, up in [
                ('_sel_tri_top_left', x_left, ymax, True),
                ('_sel_tri_bot_left', x_left, ymin, False),
                ('_sel_tri_top_right', x_right, ymax, True),
                ('_sel_tri_bot_right', x_right, ymin, False),
            ]:
                item = getattr(self, attr, None)
                if cx is None:
                    if item is not None:
                        item.setData([], [])
                    continue
                symbol = tri_up if up else tri_down
                if item is None:
                    item = pg.PlotDataItem(
                        [float(cx)], [float(cy)],
                        pen=None,
                        symbol=symbol,
                        symbolBrush=tri_brush,
                        symbolPen=pg.mkPen(None),
                        symbolSize=tri_px,
                    )
                    item.setZValue(151)
                    self.plot_widget.addItem(item)
                    setattr(self, attr, item)
                else:
                    item.setData([float(cx)], [float(cy)])
                    item.opts['symbolSize'] = tri_px
                    item.updateItems()

        except Exception:
            pass

    def _hide_selection_triangles(self):
        """隐藏所有选区三角形标记。"""
        for attr in ('_sel_tri_top_left', '_sel_tri_bot_left',
                     '_sel_tri_top_right', '_sel_tri_bot_right'):
            item = getattr(self, attr, None)
            if item is not None:
                item.setData([], [])

    # ═══════════════════════════════════════════
    # 鼠标交互 + 辅助线
    # ═══════════════════════════════════════════

    def _on_wheel(self, delta, modifiers=None):
        """滚轮 → Y 轴滚动 / Ctrl+滚轮 → X 轴缩放。"""
        try:
            ctrl_pressed = False
            if modifiers is not None:
                try:
                    from PyQt6.QtCore import Qt as _QtW
                except ImportError:
                    from PyQt5.QtCore import Qt as _QtW
                ctrl_pressed = bool(int(modifiers) & int(_QtW.KeyboardModifier.ControlModifier))
        except Exception:
            ctrl_pressed = False

        if ctrl_pressed:
            # Ctrl+滚轮 → 水平缩放（时间窗口收放）
            self._zoom_x_wheel(delta)
        else:
            # 普通滚轮 → Y 轴滚动
            if self.on_wheel_scroll is not None:
                self.on_wheel_scroll(delta)

    def _zoom_x_wheel(self, delta):
        """Ctrl+滚轮：以视图中心为锚点缩放 X 轴时间窗口。"""
        try:
            vb = self.plot_widget.getViewBox()
            x_range = vb.viewRange()[0]
            x0, x1 = float(x_range[0]), float(x_range[1])
            span = x1 - x0
            if span <= 0:
                return
            # 缩放因子：向上滚放大（缩小时间窗），向下滚缩小（放大时间窗）
            factor = 0.85 if delta > 0 else 1.18
            new_span = max(0.5, min(300.0, span * factor))
            center = (x0 + x1) * 0.5
            new_x0 = max(0.0, center - new_span * 0.5)
            new_x1 = new_x0 + new_span
            self.set_x_range(new_x0, new_x1)
        except Exception:
            pass

    def set_guides(self, x_time, y_pitch,
                   glow_alpha_v=0.12, main_alpha_v=0.90,
                   glow_width_v=2.2, main_width_v=0.8,
                   glow_alpha_h=0.12, main_width_h=0.8):
        """设置辅助线位置与动态样式（对齐 normal 模式 update_guides）。

        纵向线跟随当前时间（current_global_time / _lb_playhead），
        横向线跟随当前识别音高（last_active_pitch_y），不由鼠标驱动。

        动态柔光对齐 normal 模式：根据移动强度调整 glow alpha 和主线粗细。

        Args:
            x_time: 纵向线 X 位置（None 则隐藏）
            y_pitch: 横向线 Y 位置（None 则隐藏）
            glow_alpha_v: 纵向柔光不透明度
            main_alpha_v: 纵向主线不透明度
            glow_width_v: 纵向柔光粗细
            main_width_v: 纵向主线粗细
            glow_alpha_h: 横向柔光不透明度
            main_width_h: 横向主线粗细
        """
        if not self._ready or not self._guides_enabled:
            return
        try:
            if x_time is not None:
                fx = float(x_time)
                self._v_guide_glow.setPos(fx)
                self._v_guide_main.setPos(fx)
                self._v_guide_glow.setVisible(True)
                self._v_guide_main.setVisible(True)
                # 动态样式：柔和度和粗细随移动强度变化
                try:
                    self._v_guide_glow.setOpacity(float(glow_alpha_v))
                    self._v_guide_main.setOpacity(float(main_alpha_v))
                    self._v_guide_glow.setPen(pg.mkPen(color='#C0C0C0', width=float(glow_width_v), style=QtCore.Qt.PenStyle.SolidLine))
                    self._v_guide_main.setPen(pg.mkPen(color='#C0C0C0', width=float(main_width_v), style=QtCore.Qt.PenStyle.DashLine))
                except Exception:
                    pass
            else:
                self._v_guide_glow.setVisible(False)
                self._v_guide_main.setVisible(False)

            if y_pitch is not None:
                fy = float(y_pitch)
                self._h_guide_glow.setPos(fy)
                self._h_guide_main.setPos(fy)
                self._h_guide_glow.setVisible(True)
                self._h_guide_main.setVisible(True)
                # 动态样式
                try:
                    self._h_guide_glow.setOpacity(float(glow_alpha_h))
                    self._h_guide_glow.setPen(pg.mkPen(color='#C0C0C0', width=float(glow_width_v), style=QtCore.Qt.PenStyle.SolidLine))
                    self._h_guide_main.setPen(pg.mkPen(color='#C0C0C0', width=float(main_width_h), style=QtCore.Qt.PenStyle.DashLine))
                except Exception:
                    pass
            else:
                self._h_guide_glow.setVisible(False)
                self._h_guide_main.setVisible(False)

            self._guides_visible = (x_time is not None or y_pitch is not None)
        except Exception:
            pass

    def set_guides_enabled(self, enabled):
        """启用/禁用辅助线（对齐 normal mode guides_enabled 标志）。"""
        self._guides_enabled = bool(enabled)
        if not enabled:
            self._guides_visible = False
            try:
                self._v_guide_glow.setVisible(False)
                self._v_guide_main.setVisible(False)
                self._h_guide_glow.setVisible(False)
                self._h_guide_main.setVisible(False)
            except Exception:
                pass

    def _on_mouse_clicked(self, event):
        """鼠标点击（sigMouseClicked on RELEASE）。

        eventFilter 已在 PRESS 阶段完成按钮命中 / 拖拽检测。
        此处只处理"普通点击 → 设置新选区"的剩余情形。
        """
        try:
            # 若 eventFilter 已处理（按钮/拖拽），跳过
            pending_btn = getattr(self, '_pending_btn_click', None)
            had_interaction = getattr(self, '_interaction_detected', False)
            if pending_btn is not None or had_interaction:
                return

            # 若 eventFilter 标记了普通点击未触发（release 时检查失败）→ 此处补发
            pending_normal = getattr(self, '_pending_normal_click', False)
            self._pending_normal_click = False

            if pending_normal and self.on_click_at_time is not None:
                vb = self.plot_widget.getViewBox()
                pos = event.scenePos()
                data_pos = vb.mapSceneToView(pos)
                x, y = float(data_pos.x()), float(data_pos.y())
                self.on_click_at_time(x, y, scene_pos=pos, event=event)
        except Exception:
            pass

    def set_viewbox_mouse_enabled(self, enabled: bool):
        """启用/禁用 ViewBox 鼠标交互（用于选区拖拽时禁止平移）。"""
        try:
            vb = self.plot_widget.getViewBox()
            vb.setMouseEnabled(x=enabled, y=False)
        except Exception:
            pass

    # ═══════════════════════════════════════════
    # 事件过滤器（捕捉 viewport 原始像素坐标 + 选区拖拽）
    # ═══════════════════════════════════════════

    def eventFilter(self, obj, event):
        """在 viewport 上拦截鼠标事件：

        - MouseButtonPress：检测按钮命中 / 交互类型（边缘/播放头/block拖拽）
        - MouseMove：记录 widget 像素坐标 + 触发选区拖拽回调
        - MouseButtonRelease：结束拖拽 / 触发按钮点击 / 触发"设置新选区"点击
        """
        try:
            try:
                ev_type = event.type() if event is not None else None
            except Exception:
                ev_type = None

            if ev_type is not None:
                # ── MouseButtonPress ──
                try:
                    is_press = bool(ev_type == QEvent.Type.MouseButtonPress)
                except (AttributeError, TypeError):
                    try:
                        is_press = bool(ev_type == QEvent.MouseButtonPress)
                    except Exception:
                        is_press = False
                if is_press:
                    # 记录光标位置
                    try:
                        pos = event.position()
                    except Exception:
                        try:
                            pos = event.pos()
                        except Exception:
                            pos = None
                    if pos is not None:
                        self._cursor_widget_pos = QtCore.QPointF(float(pos.x()), float(pos.y()))

                    # 转换为数据坐标
                    try:
                        pw = self.plot_widget
                        vb = pw.getViewBox()
                        pt_widget = QtCore.QPointF(self._cursor_widget_pos)
                        pt_scene = pw.mapToScene(pt_widget.toPoint())
                        data_pt = vb.mapSceneToView(pt_scene)
                        x, y = float(data_pt.x()), float(data_pt.y())
                    except Exception:
                        x, y = None, None

                    # ── 检测控制按钮命中 ──
                    btn_hit = None
                    if x is not None:
                        for hit_attr, btn_name in [
                            ('_lb_ctrl_hit_play', 'play'),
                            ('_lb_ctrl_hit_pause', 'pause'),
                            ('_lb_ctrl_hit_stop', 'stop'),
                        ]:
                            hit = getattr(self, hit_attr, None)
                            if hit is None:
                                continue
                            x0, x1, y0, y1 = hit
                            if x0 <= x <= x1 and y0 <= y <= y1:
                                btn_hit = btn_name
                                break

                    if btn_hit:
                        self._pending_btn_click = btn_hit
                        # 不拦截，让 release 时触发（避免与 drag 冲突）
                        try:
                            return super().eventFilter(obj, event)
                        except Exception:
                            return False

                    # ── 检测交互类型（边缘/播放头/block 拖拽）──
                    if x is not None and self.on_mouse_press_data is not None:
                        detected = self.on_mouse_press_data(x, y)
                        if detected:
                            self._sel_dragging = True
                            self.set_viewbox_mouse_enabled(False)
                            self._interaction_detected = True
                            try:
                                return super().eventFilter(obj, event)
                            except Exception:
                                return False

                # ── MouseMove ──
                try:
                    is_move = bool(ev_type == QEvent.Type.MouseMove)
                except (AttributeError, TypeError):
                    try:
                        is_move = bool(ev_type == QEvent.MouseMove)
                    except Exception:
                        is_move = False
                if is_move:
                    try:
                        pos = event.position()
                    except Exception:
                        try:
                            pos = event.pos()
                        except Exception:
                            pos = None
                    if pos is not None:
                        self._cursor_widget_pos = QtCore.QPointF(float(pos.x()), float(pos.y()))

                    try:
                        gp = event.globalPosition()
                        self._cursor_global_pos = QtCore.QPointF(float(gp.x()), float(gp.y()))
                    except Exception:
                        try:
                            gp = event.globalPos()
                            self._cursor_global_pos = QtCore.QPointF(float(gp.x()), float(gp.y()))
                        except Exception:
                            pass

                    # 选区拖拽中：回调父组件
                    if hasattr(self, '_sel_dragging') and self._sel_dragging:
                        try:
                            if self.on_selection_drag is not None:
                                pw = self.plot_widget
                                vb = pw.getViewBox()
                                pt_widget = QtCore.QPointF(self._cursor_widget_pos)
                                pt_scene2 = pw.mapToScene(pt_widget.toPoint())
                                data_pt = vb.mapSceneToView(pt_scene2)
                                self.on_selection_drag(float(data_pt.x()), float(data_pt.y()))
                        except Exception:
                            pass

                # ── MouseButtonRelease ──
                try:
                    is_release = bool(ev_type == QEvent.Type.MouseButtonRelease)
                except (AttributeError, TypeError):
                    try:
                        is_release = bool(ev_type == QEvent.MouseButtonRelease)
                    except Exception:
                        is_release = False
                if is_release:
                    # 按钮点击
                    pending_btn = getattr(self, '_pending_btn_click', None)
                    if pending_btn is not None:
                        self._pending_btn_click = None
                        if self.on_listenback_button is not None:
                            self.on_listenback_button(pending_btn)
                        try:
                            return super().eventFilter(obj, event)
                        except Exception:
                            return False

                    # 拖拽结束
                    if hasattr(self, '_sel_dragging') and self._sel_dragging:
                        self._sel_dragging = False
                        self.set_viewbox_mouse_enabled(True)
                        self._interaction_detected = False
                        try:
                            if self.on_selection_release is not None:
                                self.on_selection_release()
                        except Exception:
                            pass
                        try:
                            return super().eventFilter(obj, event)
                        except Exception:
                            return False

                    # 普通点击：未命中按钮、未拖拽 → 设为"新选区"点击
                    had_interaction = getattr(self, '_interaction_detected', False)
                    if not had_interaction:
                        self._pending_normal_click = True

        except Exception:
            pass
        try:
            return super().eventFilter(obj, event)
        except Exception:
            return False

    # ═══════════════════════════════════════════
    # 悬停高亮 + 注记 + 放大镜
    # ═══════════════════════════════════════════

    def _on_mouse_moved(self, evt):
        """SignalProxy 回调：鼠标在 PlotWidget 上移动（60fps 节流）。

        关键改进：
        - 滞回逻辑：上一帧命中点若仍在光标近处，保持不变，避免在相邻点间跳动
        - 放大镜抓取前先隐藏自身，避免出现"镜中镜"递归
        - 抓取中心 = 光标所在位置（而非命中的数据点），对齐 normal 模式行为
        """
        try:
            import time as _t
            now = _t.time()
            if now - self._hover_last_t < self._hover_throttle_sec:
                return
            self._hover_last_t = now

            # SignalProxy 将事件包装在 tuple 中；鼠标移动时 evt[0] 是 QPointF（场景坐标）
            scene_pos = evt[0] if isinstance(evt, tuple) and len(evt) > 0 else evt

            # 进入视图 → 蓝色羽毛光标（对齐 normal 模式 _update_hover_cursor）
            if not self._feather_cursor_active and self._feather_cursor is not None:
                try:
                    pw = self.plot_widget
                    pw.setCursor(self._feather_cursor)
                    self._feather_cursor_active = True
                except Exception:
                    pass

            # 离开 plot 区域 → 隐藏一切
            vb = self.plot_widget.getViewBox()
            view_rect = vb.sceneBoundingRect()
            if not view_rect.contains(scene_pos):
                self._hide_hover()
                self._hide_magnifier()
                self._hover_last_point = None
                return

            # 命中检测（带滞回）
            hit = self._find_nearest_point(scene_pos)
            if hit is None:
                self._hide_hover()
                self._hide_magnifier()
                self._hover_last_point = None
                return

            hx, hy = hit

            # ── 更新悬停高亮（数据点位置，始终在图上可见）──
            self._update_hover_highlight(hx, hy)

            # ── 格式化注记文本 ──
            text = self._pitch_to_note(hy)
            if self.on_hover_info is not None:
                try:
                    text = self.on_hover_info(hx, hy)
                except Exception:
                    pass

            # ── 更新放大镜（抓取中心 = 光标位置 scene_pos，对齐 normal 模式）──
            if self._magn_enabled:
                # 放大镜模式：隐藏图上的 _hover_annot，仅用 _magn_label 显示标注（避免两个标签）
                self._hover_annot.setVisible(False)
                self._update_magnifier(hx, hy, scene_pos, text)
            else:
                # 无放大镜时：图上的 _hover_annot 正常显示
                self._hover_annot.setText(text)
                self._hover_annot.setPos(hx, hy + 0.18)
                self._hover_annot.setVisible(True)
                self._hide_magnifier()
        except Exception:
            self._hide_hover()
            self._hide_magnifier()
            self._hover_last_point = None

    def _find_nearest_point(self, scene_pos):
        """在缓存的 segments 中查找离鼠标最近的细节点。

        关键改进（修正时序竞态）：
        - 不使用 scene_pos 做距离比较（scene_pos 来自 SignalProxy，使用
          鼠标事件时刻的 ViewBox 范围；音频播放时 set_x_range 每帧更新，
          回调时范围已变，mapFromScene(scene_pos) 会得到错误的控件坐标）
        - 改用 QCursor.pos() + mapFromGlobal() — 实时鼠标控件坐标，
          不依赖 ViewBox 范围，与数据点的 widget 坐标始终一致
        - 数据点距离在 widget 像素空间比较（等价 normal 模式 event.x/y）
        - 滞回：上一帧命中点在 8px 内保持不变
        """
        try:
            if not self._segments_cache:
                self._hover_last_point = None
                return None

            pw = self.plot_widget
            vb = pw.getViewBox()

            # ── 光标 → widget 像素坐标 ──
            #    优先用 viewport 事件过滤器捕获的原始像素坐标（事件时刻、
            #    不经过 ViewBox 变换、不受音频管道 set_x_range 时序影响）
            try:
                cwp = self._cursor_widget_pos
                wx, wy = cwp.x(), cwp.y()
                if wx == 0.0 and wy == 0.0:
                    # 尚未初始化，回退
                    raise ValueError('not initialised')
            except Exception:
                # 回退：QCursor.pos()（call-time 实时坐标）
                try:
                    cursor_global = QCursor.pos()
                    pt_cursor_widget = pw.mapFromGlobal(cursor_global)
                    wx, wy = pt_cursor_widget.x(), pt_cursor_widget.y()
                except Exception:
                    # 最终回退：scene_pos（可能受时序影响）
                    pt_cursor_widget = pw.mapFromScene(scene_pos)
                    wx, wy = pt_cursor_widget.x(), pt_cursor_widget.y()

            # ── 可见视口 X 范围 ──
            x_range = vb.viewRange()[0]
            vis_x0, vis_x1 = float(x_range[0]), float(x_range[1])

            # ── 滞回优先 ──
            if self._hover_last_point is not None:
                lx, ly = self._hover_last_point
                if vis_x0 <= lx <= vis_x1:
                    pt_scene = vb.mapToScene(vb.mapFromView(QtCore.QPointF(float(lx), float(ly))))
                    pt_w = pw.mapFromScene(pt_scene)
                    dx = pt_w.x() - wx
                    dy = pt_w.y() - wy
                    if dx * dx + dy * dy <= self._hover_stick_radius2:
                        return self._hover_last_point

            best_dist2 = float('inf')
            best = None
            radius2 = self._hover_hit_radius ** 2

            # ── 第一遍：可见视口内的精确细节点（widget 像素距离）──
            for ts, ps in self._segments_cache:
                if not ts:
                    continue
                for t, p in zip(ts, ps):
                    ft = float(t)
                    if ft < vis_x0 or ft > vis_x1:
                        continue
                    pt_scene = vb.mapToScene(vb.mapFromView(QtCore.QPointF(ft, float(p))))
                    pt_w = pw.mapFromScene(pt_scene)
                    dx = pt_w.x() - wx
                    dy = pt_w.y() - wy
                    dist2 = dx * dx + dy * dy
                    if dist2 < best_dist2:
                        best_dist2 = dist2
                        best = (ft, float(p))

            if best is not None and best_dist2 <= radius2:
                self._hover_last_point = best
                return best

            # ── 第二遍：线段密集采样回退 ──
            sample_cap = 200
            sampled = 0
            n_segs = max(1, len(self._segments_cache))
            per_seg = max(10, sample_cap // n_segs)
            for ts, ps in self._segments_cache:
                if sampled >= sample_cap or not ts:
                    continue
                n = len(ts)
                if n < 2:
                    continue
                step = max(1, n // per_seg)
                for i in range(0, n, step):
                    if sampled >= sample_cap:
                        break
                    ft = float(ts[i])
                    if ft < vis_x0 or ft > vis_x1:
                        continue
                    pt_scene = vb.mapToScene(vb.mapFromView(QtCore.QPointF(ft, float(ps[i]))))
                    pt_w = pw.mapFromScene(pt_scene)
                    dx = pt_w.x() - wx
                    dy = pt_w.y() - wy
                    dist2 = dx * dx + dy * dy
                    if dist2 < best_dist2:
                        best_dist2 = dist2
                        best = (ft, float(ps[i]))
                    sampled += 1

            if best is not None and best_dist2 <= radius2:
                self._hover_last_point = best
                return best
            self._hover_last_point = None
            return None
        except Exception:
            self._hover_last_point = None
            return None

    def _update_hover_highlight(self, x, y):
        """显示悬停高亮（柔光 + 圆环）在 (x, y) 处。"""
        try:
            self._hover_glow.setData([x], [y])
            self._hover_glow.setVisible(True)
            self._hover_ring.setData([x], [y])
            self._hover_ring.setVisible(True)
        except Exception:
            pass

    def _hide_hover(self):
        """隐藏悬停高亮 + 注记，清除滞回状态。"""
        try:
            self._hover_glow.setVisible(False)
            self._hover_ring.setVisible(False)
            self._hover_annot.setVisible(False)
        except Exception:
            pass
        self._hover_last_point = None

    def _update_magnifier(self, x, y, scene_pos, text=""):
        """抓取以悬停数据点 (x, y) 为中心的 ViewBox 区域，放大至圆形浮窗。

        核心修正（消除高亮偏移到放大镜右侧的持久 bug）：
        ── 旧方案用 pw.mapToScene(crop_rect_corners) 把 viewport 像素矩形
           映射到场景坐标。但 QGraphicsView.mapToScene() 和 pyqtgraph ViewBox
           内部的 item 定位使用不同的坐标映射路径，两者在 X 轴上存在系统性偏移
           （Y 轴标签区域的影响）。这导致 source_rect 相对 glow/ring 的实际
           场景位置整体偏左，glow 被挤到放大镜最右侧。
        ── 新方案：直接从数据点 (x,y) 经由 ViewBox 自身 API 计算场景位置，
           并用 ViewBox sceneBoundingRect 的比例把 40px 换算为场景单位。
           完全不使用 pw.mapToScene()，消除坐标系不一致。
        """
        try:
            pw = self.plot_widget
            vb = pw.getViewBox()
            vp = pw.viewport()

            half_px = _MagnifierOverlay.CAPTURE_HALF  # 40 viewport pixels

            # ── 1. 数据点的场景坐标（经由 ViewBox 自身映射，保证与 glow/ring
            #       的 scene position 完全一致）──
            data_pt = QtCore.QPointF(float(x), float(y))
            vb_local = vb.mapFromView(data_pt)
            scene_center = vb.mapToScene(vb_local)
            scx, scy = scene_center.x(), scene_center.y()

            # ── 2. 像素 → 场景单位换算（基于 ViewBox sceneBoundingRect 比例，
            #       与 item 实际所在的场景坐标系完全一致）──
            vb_sr = vb.sceneBoundingRect()
            vb_sw = float(vb_sr.width())
            vb_sh = float(vb_sr.height())
            vp_w = float(vp.width()) if vp.width() > 0 else vb_sw
            vp_h = float(vp.height()) if vp.height() > 0 else vb_sh

            half_scene_x = half_px * vb_sw / vp_w
            half_scene_y = half_px * vb_sh / vp_h

            # ── 3. source_rect 以数据点场景位置为中心（场景坐标系）──
            source_rect = QtCore.QRectF(
                scx - half_scene_x, scy - half_scene_y,
                half_scene_x * 2.0, half_scene_y * 2.0,
            )

            # ── 4. 数据点 → viewport 坐标（用于判断裁剪和放大镜屏幕位置）──
            scene_pt = vb.mapToScene(vb.mapFromView(data_pt))
            pt_vp = pw.mapFromScene(scene_pt)
            vpx = int(round(pt_vp.x()))
            vpy = int(round(pt_vp.y()))

            # ── 5. 限制在 ViewBox 场景区域内 ──
            vb_scene_rect = vb.sceneBoundingRect()
            source_rect = source_rect.intersected(vb_scene_rect)

            if source_rect.width() < 1e-6 or source_rect.height() < 1e-6:
                self._hide_magnifier()
                return

            # 计算对应的 pixmap 尺寸（保持像素比例）
            pw_pix = max(8, int(round(source_rect.width() * vp_w / vb_sw)))
            ph_pix = max(8, int(round(source_rect.height() * vp_h / vb_sh)))

            # ── 6. 抓取前隐藏会重复的元素 ──
            magn_was_visible = self._magnifier.isVisible()
            label_was_visible = self._magn_label.isVisible()
            annot_was_visible = self._hover_annot.isVisible()

            if magn_was_visible:
                self._magnifier.hide()
            if label_was_visible:
                self._magn_label.hide()
            if annot_was_visible:
                self._hover_annot.setVisible(False)

            # ── 7. QGraphicsScene.render() — 场景坐标系原生渲染 ──
            try:
                pw.scene().update()
                vp.repaint()
            except Exception:
                try:
                    pw.repaint()
                except Exception:
                    pass

            try:
                pixmap = QPixmap(pw_pix, ph_pix)
                pixmap.fill(QColor(26, 26, 26))
                painter = QPainter(pixmap)
                try:
                    try:
                        am = Qt.AspectRatioMode.IgnoreAspectRatio
                    except AttributeError:
                        am = Qt.IgnoreAspectRatio
                    pw.scene().render(
                        painter, QtCore.QRectF(pixmap.rect()), source_rect, am,
                    )
                finally:
                    painter.end()
            except Exception:
                # 回退：viewport grab 作为最后手段
                try:
                    crop_rect = QtCore.QRect(
                        vpx - half_px, vpy - half_px, half_px * 2, half_px * 2,
                    )
                    pixmap = vp.grab(crop_rect)
                except Exception:
                    try:
                        pixmap = pw.grab(crop_rect)
                    except Exception:
                        pixmap = None

            if annot_was_visible:
                self._hover_annot.setVisible(True)

            if pixmap is None or pixmap.isNull():
                self._hide_magnifier()
                return

            # ── 8. 放大镜放在光标全局位置（对齐 normal 模式）──
            #       用事件过滤器捕获的光标全局坐标；回退到 QCursor
            try:
                cgp = self._cursor_global_pos
                cursor_global = QtCore.QPoint(int(round(cgp.x())), int(round(cgp.y())))
                if cursor_global.x() == 0 and cursor_global.y() == 0:
                    raise ValueError('not initialised')
            except Exception:
                try:
                    cursor_global = QCursor.pos()
                except Exception:
                    cursor_global = pw.mapToGlobal(QtCore.QPoint(vpx, vpy))

            self._magnifier.show_at(cursor_global, pixmap)

            if text:
                magn_center_x = int(cursor_global.x()) + 36 + _MagnifierOverlay.SIZE // 2
                magn_top_y = int(cursor_global.y()) - _MagnifierOverlay.SIZE - 36
                label_global = QPoint(magn_center_x, magn_top_y)
                self._magn_label.show_at(label_global, text)
            else:
                self._magn_label.hide()
        except Exception:
            self._hide_magnifier()

    def _hide_magnifier(self):
        """隐藏放大镜 + 标注标签。"""
        try:
            self._magnifier.hide()
        except Exception:
            pass
        try:
            self._magn_label.hide()
        except Exception:
            pass

    def set_magnifier_enabled(self, enabled: bool):
        """启用/禁用放大镜（父组件控制）。"""
        self._magn_enabled = bool(enabled)
        if not self._magn_enabled:
            self._hide_magnifier()

    # ═══════════════════════════════════════════
    # 重录倒计时覆盖层（对齐 normal 模式 _render_retake_countdown_overlay）
    # ═══════════════════════════════════════════

    def _ensure_countdown_items(self):
        """懒创建倒计时覆盖层元素（对齐 matplotlib patches + lines + text）。"""
        vb = self.plot_widget.getViewBox()
        if not hasattr(self, '_cd_bg') or self._cd_bg is None:
            self._cd_bg = QGraphicsRectItem()
            self._cd_bg.setBrush(QColor(0, 0, 0, 36))  # alpha ~0.14
            self._cd_bg.setPen(QPen(Qt.PenStyle.NoPen))
            self._cd_bg.setZValue(150)
            vb.addItem(self._cd_bg)
            self._cd_bg.setVisible(False)

        if not hasattr(self, '_cd_progress') or self._cd_progress is None:
            self._cd_progress = QGraphicsRectItem()
            self._cd_progress.setBrush(QColor(255, 76, 76, 46))  # #FF4C4C alpha~0.18
            self._cd_progress.setPen(QPen(Qt.PenStyle.NoPen))
            self._cd_progress.setZValue(152)
            vb.addItem(self._cd_progress)
            self._cd_progress.setVisible(False)

        if not hasattr(self, '_cd_start_line') or self._cd_start_line is None:
            self._cd_start_line = pg.InfiniteLine(
                angle=90,
                pen=pg.mkPen(color='#FF6F61', width=1.6, style=QtCore.Qt.PenStyle.DashLine),
            )
            self._cd_start_line.setOpacity(0.60)
            self._cd_start_line.setZValue(188)
            vb.addItem(self._cd_start_line)
            self._cd_start_line.setVisible(False)

        if not hasattr(self, '_cd_goal_line') or self._cd_goal_line is None:
            self._cd_goal_line = pg.InfiniteLine(
                angle=90,
                pen=pg.mkPen(color='#FFC857', width=2.4),
            )
            self._cd_goal_line.setOpacity(0.92)
            self._cd_goal_line.setZValue(191)
            vb.addItem(self._cd_goal_line)
            self._cd_goal_line.setVisible(False)

        if not hasattr(self, '_cd_progress_line') or self._cd_progress_line is None:
            self._cd_progress_line = pg.InfiniteLine(
                angle=90,
                pen=pg.mkPen(color='#FFF4A3', width=2.8),
            )
            self._cd_progress_line.setOpacity(0.95)
            self._cd_progress_line.setZValue(193)
            vb.addItem(self._cd_progress_line)
            self._cd_progress_line.setVisible(False)

        if not hasattr(self, '_cd_text') or self._cd_text is None:
            self._cd_text = pg.TextItem('', color='#FFE066', anchor=(0.5, 0.5))
            self._cd_text.setZValue(200)
            self._cd_text.setVisible(False)
            vb.addItem(self._cd_text)
            try:
                font = QFont('sans-serif', 44, QFont.Weight.Bold)
                self._cd_text.setFont(font)
            except Exception:
                pass

        if not hasattr(self, '_cd_hint') or self._cd_hint is None:
            self._cd_hint = pg.TextItem('', color='#FFEEDD', anchor=(0.5, 0.5))
            self._cd_hint.setZValue(200)
            self._cd_hint.setVisible(False)
            vb.addItem(self._cd_hint)
            try:
                font = QFont('sans-serif', 16, QFont.Weight.Bold)
                self._cd_hint.setFont(font)
            except Exception:
                pass

    def set_countdown_overlay(self, active, rem, cur_t, start_t, target_t):
        """更新倒计时覆盖层（对齐 normal 模式 _render_retake_countdown_overlay 的视觉元素）。

        Args:
            active: 倒计时是否激活
            rem: 剩余秒数（0 = 已结束）
            cur_t: 当前平滑进度位置（数据时间坐标）
            start_t: 倒计时起点（数据时间坐标）
            target_t: 倒计时终点/目标位置
        """
        if not self._ready:
            return
        try:
            self._ensure_countdown_items()
            vb = self.plot_widget.getViewBox()
            x_range = vb.viewRange()[0]
            y_range = vb.viewRange()[1]
            x_min, x_max = float(x_range[0]), float(x_range[1])
            y_min, y_max = float(y_range[0]), float(y_range[1])
            visible = bool(active and rem > 0.02)

            # ── 背景遮罩 ──
            try:
                if visible:
                    self._cd_bg.setRect(x_min, y_min, x_max - x_min, y_max - y_min)
                self._cd_bg.setVisible(visible)
            except Exception:
                pass

            # ── 进度填充（红色条）──
            try:
                if visible:
                    width = max(1e-6, cur_t - start_t)
                    self._cd_progress.setRect(start_t, y_min, width, y_max - y_min)
                self._cd_progress.setVisible(visible)
            except Exception:
                pass

            # ── 起点/目标指示线 ──
            try:
                if visible:
                    self._cd_start_line.setPos(float(start_t))
                    self._cd_goal_line.setPos(float(target_t))
                self._cd_start_line.setVisible(visible)
                self._cd_goal_line.setVisible(visible)
            except Exception:
                pass

            # ── 动态进度指示线 ──
            try:
                if visible:
                    self._cd_progress_line.setPos(float(cur_t))
                self._cd_progress_line.setVisible(visible)
            except Exception:
                pass

            # ── 倒计时文本 ──
            try:
                if visible and rem > 0:
                    import math as _m
                    if rem <= 1.0:
                        display_val = f"{rem:.1f}s"
                    elif rem <= 2.0:
                        display_val = f"{rem:.1f}"
                    else:
                        display_val = str(int(max(1, _m.ceil(rem))))
                    self._cd_text.setText(display_val)
                    mid_x = (x_min + x_max) * 0.5
                    mid_y = (y_min + y_max) * 0.55
                    self._cd_text.setPos(mid_x, mid_y)
                    self._cd_text.setVisible(True)
                else:
                    self._cd_text.setVisible(False)
            except Exception:
                pass

            # ── 提示文字 ──
            try:
                if visible and rem > 0:
                    hint_text = f"准备回录… {cur_t:.2f}s → {target_t:.2f}s"
                    self._cd_hint.setText(hint_text.strip())
                    mid_x = (x_min + x_max) * 0.5
                    hint_y = (y_min + y_max) * 0.40
                    self._cd_hint.setPos(mid_x, hint_y)
                    self._cd_hint.setVisible(True)
                else:
                    self._cd_hint.setVisible(False)
            except Exception:
                pass

        except Exception:
            self.clear_countdown_overlay()

    def clear_countdown_overlay(self):
        """隐藏所有倒计时覆盖层元素。"""
        for attr in ('_cd_bg', '_cd_progress', '_cd_start_line', '_cd_goal_line',
                     '_cd_progress_line', '_cd_text', '_cd_hint'):
            try:
                item = getattr(self, attr, None)
                if item is not None:
                    item.setVisible(False)
            except Exception:
                pass

    # ═══════════════════════════════════════════
    # 重录覆盖预览点（对齐 normal 模式 retake overlay preview）
    # ═══════════════════════════════════════════

    def _ensure_overlay_preview_items(self):
        """懒创建覆盖预览线 + 散点 + 标签（对齐 matplotlib _ensure_overlay_preview_artists）。"""
        vb = self.plot_widget.getViewBox()
        if not hasattr(self, '_overlay_line') or self._overlay_line is None:
            preview_color = pg.mkPen(color='#FFD166', width=1.0)
            self._overlay_line = self.plot_widget.plot(
                [], [],
                pen=preview_color,
                connect='finite',
                skipFiniteCheck=True,
                autoDownsample=True,
                clipToView=True,
                antialias=True,
            )
            self._overlay_line.setZValue(13)
            self._overlay_line.setVisible(False)

        if not hasattr(self, '_overlay_scatter') or self._overlay_scatter is None:
            self._overlay_scatter = pg.ScatterPlotItem(
                [0], [0], size=5, pen=None, brush=pg.mkBrush(255, 255, 255, 250), pxMode=True,
            )
            self._overlay_scatter.setZValue(14)
            self._overlay_scatter.setVisible(False)
            vb.addItem(self._overlay_scatter)

        if not hasattr(self, '_overlay_label') or self._overlay_label is None:
            self._overlay_label = pg.TextItem(
                '', color='#FFD166', anchor=(1, 1),
            )
            self._overlay_label.setZValue(15)
            self._overlay_label.setVisible(False)
            self._overlay_label.setOpacity(0.95)
            vb.addItem(self._overlay_label)

    def set_retake_overlay_preview(self, points, active, start_t=0.0, end_t=0.0):
        """更新重录覆盖预览点（对齐 normal 模式 _update_overlay_preview_artists）。

        Args:
            points: list of (t, y, confidence) tuples
            active: 是否激活
            start_t: 选区起始时间（用于标签）
            end_t: 选区结束时间（用于标签）
        """
        if not self._ready:
            return
        try:
            self._ensure_overlay_preview_items()

            if not active or not points:
                self._overlay_line.setData([], [])
                self._overlay_line.setVisible(False)
                self._overlay_scatter.setData([], [])
                self._overlay_scatter.setVisible(False)
                self._overlay_label.setVisible(False)
                return

            import math as _m
            import numpy as _np

            # ── 构建分段（NaN 断点处理无音高间隙）──
            segments = []
            cur_t, cur_p = [], []
            for t_val, y_val, _c_val in points:
                try:
                    t_f = float(t_val)
                except Exception:
                    continue
                try:
                    y_f = float(y_val)
                except Exception:
                    y_f = float('nan')
                if not _m.isfinite(y_f):
                    if cur_t:
                        segments.append((cur_t, cur_p))
                        cur_t, cur_p = [], []
                    continue
                cur_t.append(t_f)
                cur_p.append(y_f)
            if cur_t:
                segments.append((cur_t, cur_p))

            if not segments:
                self._overlay_line.setData([], [])
                self._overlay_line.setVisible(False)
                self._overlay_scatter.setData([], [])
                self._overlay_scatter.setVisible(False)
                self._overlay_label.setVisible(False)
                return

            # ── 线段：拼接各段并插入 NaN ──
            all_x, all_y = [], []
            for seg_t, seg_p in segments:
                x = _np.asarray(seg_t, dtype=_np.float64)
                y = _np.asarray(seg_p, dtype=_np.float64)
                mn = min(len(x), len(y))
                x, y = x[:mn], y[:mn]
                if mn >= 2:
                    gap_x, gap_y = [x[0]], [y[0]]
                    for j in range(1, mn):
                        if x[j] - x[j-1] > 0.14:
                            gap_x.append(float('nan'))
                            gap_y.append(float('nan'))
                        gap_x.append(x[j])
                        gap_y.append(y[j])
                    all_x.extend(gap_x)
                    all_y.extend(gap_y)
                else:
                    all_x.extend(x.tolist())
                    all_y.extend(y.tolist())

            self._overlay_line.setData(_np.asarray(all_x, dtype=_np.float64),
                                       _np.asarray(all_y, dtype=_np.float64))
            self._overlay_line.setVisible(True)

            # ── 散点：取最新 N 个点 ──
            max_scatter = 300
            flat_pts = [(t, p) for seg_t, seg_p in segments for t, p in zip(seg_t, seg_p)]
            if len(flat_pts) > max_scatter:
                flat_pts = flat_pts[-max_scatter:]
            if flat_pts:
                sx = _np.asarray([p[0] for p in flat_pts], dtype=_np.float64)
                sy = _np.asarray([p[1] for p in flat_pts], dtype=_np.float64)
                self._overlay_scatter.setData(sx, sy)
                self._overlay_scatter.setVisible(True)
            else:
                self._overlay_scatter.setVisible(False)

            # ── 标签（右上角）──
            try:
                vb = self.plot_widget.getViewBox()
                x_range = vb.viewRange()[0]
                y_range = vb.viewRange()[1]
                label_x = float(x_range[1]) - (float(x_range[1]) - float(x_range[0])) * 0.015
                label_y = float(y_range[1]) - (float(y_range[1]) - float(y_range[0])) * 0.025
                self._overlay_label.setText(f"重录覆盖 {len(points)}点")
                self._overlay_label.setPos(label_x, label_y)
                self._overlay_label.setVisible(True)
            except Exception:
                pass

        except Exception:
            self.clear_retake_overlay_preview()

    def clear_retake_overlay_preview(self):
        """隐藏覆盖预览。"""
        try:
            if hasattr(self, '_overlay_line') and self._overlay_line is not None:
                self._overlay_line.setData([], [])
                self._overlay_line.setVisible(False)
        except Exception:
            pass
        try:
            if hasattr(self, '_overlay_scatter') and self._overlay_scatter is not None:
                self._overlay_scatter.setData([], [])
                self._overlay_scatter.setVisible(False)
        except Exception:
            pass
        try:
            if hasattr(self, '_overlay_label') and self._overlay_label is not None:
                self._overlay_label.setVisible(False)
        except Exception:
            pass

    def _on_user_view_changed(self, vb):
        """用户手动缩放/平移后，将新范围回传给父组件。
        X 轴起点固定为 0（禁止负时间），Y 轴限制在 0-8 八度。
        pyqtgraph 0.14 sigRangeChangedManually 只传递 vb 自身，需自行取 viewRange()。"""
        try:
            if self.on_view_changed is None:
                return
            vr = vb.viewRange()
            x_range = vr[0] if len(vr) > 0 else None
            y_range = vr[1] if len(vr) > 1 else None
            if x_range is not None and y_range is not None:
                x0, x1 = float(x_range[0]), float(x_range[1])
                y0, y1 = float(y_range[0]), float(y_range[1])
                # X 轴不可出现负时间
                if x0 < 0:
                    x1 -= x0
                    x0 = 0.0
                # Y 轴限制在 0-8 八度
                if y0 < 0:
                    y0 = 0.0
                if y1 > 8:
                    y1 = 8.0
                self._last_x_range = (x0, x1)
                self._last_y_range = (y0, y1)
                self.on_view_changed((x0, x1), (y0, y1))
        except Exception:
            pass

    def set_line_color(self, color_hex):
        """设置全线颜色。"""
        if not self._ready:
            return
        self._line_color = str(color_hex)
        pen = pg.mkPen(color=self._line_color, width=getattr(self, '_line_width', 1.5))
        for line in self._line_pool:
            line.setPen(pen)

    def set_line_width(self, width):
        """设置全线宽度（对齐 normal 模式 current_linewidth）。"""
        if not self._ready:
            return
        self._line_width = float(width)
        color = getattr(self, '_line_color', '#ff6b35')
        pen = pg.mkPen(color=color, width=self._line_width)
        for line in self._line_pool:
            line.setPen(pen)

    def set_point_size(self, size):
        """设置散点符号大小（对齐 normal 模式 _calc_marker_size）。"""
        if not self._ready:
            return
        self._point_size = float(size)
        for scatter in self._scatter_pool:
            scatter.setSymbolSize(self._point_size)


# ═══════════════════════════════════════════
# 保留旧类以兼容（引用此类的现有代码不会报错）
# ═══════════════════════════════════════════

class PyQtGraphColorGradientWidget(QWidget):
    """[兼容存根] 原彩色渐变组件。功能已迁移到 PyQtGraphPitchRenderer。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._renderer = PyQtGraphPitchRenderer(parent)
        layout.addWidget(self._renderer)

    @property
    def plot_widget(self):
        return self._renderer.plot_widget if hasattr(self, '_renderer') else None

    def add_pitch_data(self, time_val, pitch_val, confidence=1.0):
        pass

    def update_color_gradient_display(self):
        pass

    def render_gradient_segments(self, *args, **kwargs):
        pass

    def render_color_particles(self, *args, **kwargs):
        pass

    def render_highlight_point(self, *args, **kwargs):
        pass

    def clear_gradient_elements(self):
        pass

    def clear_all_data(self):
        if hasattr(self, '_renderer'):
            self._renderer.clear()

    def set_segments(self, segments):
        if hasattr(self, '_renderer'):
            self._renderer.set_segments(segments)

    def set_x_range(self, x_min, x_max):
        if hasattr(self, '_renderer'):
            self._renderer.set_x_range(x_min, x_max)

    def set_y_range(self, y_min, y_max):
        if hasattr(self, '_renderer'):
            self._renderer.set_y_range(y_min, y_max)

    def set_grid_lines(self, positions):
        if hasattr(self, '_renderer'):
            self._renderer.set_grid_lines(positions)

    def set_grid_from_range(self, y_start, y_end, zoom_mode=None):
        if hasattr(self, '_renderer'):
            self._renderer.set_grid_from_range(y_start, y_end, zoom_mode)

    def set_selection_range(self, x_left, x_right):
        if hasattr(self, '_renderer'):
            self._renderer.set_selection_range(x_left, x_right)

    def set_playhead(self, x):
        if hasattr(self, '_renderer'):
            self._renderer.set_playhead(x)


# ═══════════════════════════════════════════
# 独立测试
# ═══════════════════════════════════════════

def _test_renderer():
    """独立测试 PyQtGraphPitchRenderer 的帧率和正确性。"""
    import time
    import math

    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("PyQtGraphPitchRenderer — Phase 1 Test")
    window.setGeometry(100, 100, 1200, 800)

    layout = QVBoxLayout(window)
    renderer = PyQtGraphPitchRenderer()
    layout.addWidget(renderer)

    sample_rate = 100
    duration = 5.0
    n_total = int(duration * sample_rate)
    t = np.linspace(0, duration, n_total)
    pitch = 3.5 + 1.2 * np.sin(2 * np.pi * 0.8 * t) + 0.4 * np.sin(2 * np.pi * 2.3 * t)

    mask1 = t <= 2.8
    mask2 = t >= 3.2

    segments = [
        (t[mask1].tolist(), pitch[mask1].tolist()),
        (t[mask2].tolist(), pitch[mask2].tolist()),
    ]

    renderer.set_segments(segments)
    renderer.set_x_range(0, 6.0)
    renderer.set_y_range(1.0, 7.0)
    renderer.set_grid_from_range(1.0, 7.0)

    fps_label = QLabel("FPS: --")
    fps_label.setStyleSheet("color: #00ff00; font-size: 16px; font-weight: bold;")
    layout.addWidget(fps_label)

    frame_count = [0]
    last_time = [time.perf_counter()]

    def update_fps():
        frame_count[0] += 1
        now = time.perf_counter()
        elapsed = now - last_time[0]
        if elapsed >= 1.0:
            fps = frame_count[0] / elapsed
            fps_label.setText(f"FPS: {fps:.1f}")
            frame_count[0] = 0
            last_time[0] = now

    scroll_start = time.perf_counter()
    scroll_total = 20.0

    def scroll_tick():
        elapsed = time.perf_counter() - scroll_start
        if elapsed > scroll_total:
            timer.stop()
            fps_label.setText(fps_label.text() + " (done)")
            return
        win_start = max(0, elapsed - 3.0)
        win_end = elapsed + 3.0
        renderer.set_x_range(win_start, win_end)
        renderer.set_playhead(elapsed)
        update_fps()

    timer = QTimer()
    timer.timeout.connect(scroll_tick)
    timer.start(33)

    print("Phase 1 test running: 5s simulated pitch data, 20s auto-scroll")
    print("Expected: 45-60+ FPS, smooth scrolling, clean segment breaks")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    _test_renderer()
