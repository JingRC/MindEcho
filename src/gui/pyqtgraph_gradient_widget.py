#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQtGraph 分段音高线渲染器 — 替代 matplotlib draw_segmented_pitch_line。

Phase 1: 核心渲染引擎，独立于 ECGStylePitchVisualizer 可测试。
Phase 2+: 通过 _use_pyqtgraph 标志桥接到主类。
"""

import sys
import numpy as np
from collections import deque

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


class PyQtGraphPitchRenderer(QWidget):
    """pyqtgraph 分段音高线渲染器。

    替代 draw_segmented_pitch_line 的核心渲染。关键设计：
    - PlotDataItem 复用池，通过 setData() 更新，绝不每帧 removeItem + plot
    - NaN 断点连接（connect='finite'），自动处理换气段间的不连线
    - 内置 autoDownsample + clipToView，GPU 级 LOD + 裁剪
    - InfiniteLine 池用于网格，setPos() 更新而非重建
    """

    # 池大小常量
    MAX_SEGMENTS = 60       # 同时活跃分段数上限
    MAX_GRID_LINES = 40     # 水平网格线数上限

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
        pg.setConfigOption('antialias', False)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Pitch (octave)', color='#aaaaaa')
        self.plot_widget.setLabel('bottom', 'Time (s)', color='#aaaaaa')
        self.plot_widget.showGrid(x=True, y=False, alpha=0.15)

        # Y 轴默认范围：1-7 八度（对应 C2-C7）
        self.plot_widget.setYRange(1.0, 7.0, padding=0.02)
        self.plot_widget.setXRange(0, 16.0, padding=0.0)

        # 隐藏 Y 轴刻度数字（与现有 matplotlib 风格一致）
        self.plot_widget.getPlotItem().getAxis('left').setStyle(showValues=False)

        layout.addWidget(self.plot_widget)

        # ── 艺术家复用池 ──
        self._line_pool: list = []       # PlotDataItem 列表（分段线）
        self._scatter_pool: list = []    # PlotDataItem 列表（分段散点）
        self._grid_lines: list = []      # InfiniteLine 列表（水平网格）
        self._playhead: object = None    # InfiniteLine（播放头）

        self._init_pools()

        # ── 状态 ──
        self._current_segment_count = 0

    # ═══════════════════════════════════════════
    # 池初始化
    # ═══════════════════════════════════════════

    def _init_pools(self):
        """预分配艺术家池。创建后通过 setData() 更新，不再新建/删除。"""
        base_pen = pg.mkPen(color='#ff6b35', width=1)
        base_scatter_pen = pg.mkPen(color='#ffffff', width=0)

        for _ in range(self.MAX_SEGMENTS):
            # 分段线 — connect='finite' 自动跳过 NaN
            line = self.plot_widget.plot(
                [], [],
                pen=base_pen,
                connect='finite',
                skipFiniteCheck=True,
                autoDownsample=True,
                clipToView=True,
                antialias=False,
            )
            line.setVisible(False)
            self._line_pool.append(line)

            # 分段散点
            scatter = self.plot_widget.plot(
                [], [],
                pen=None,
                symbol='o',
                symbolSize=3,
                symbolBrush='#ffffff',
                symbolPen=base_scatter_pen,
                skipFiniteCheck=True,
                autoDownsample=True,
                clipToView=True,
                antialias=False,
            )
            scatter.setVisible(False)
            self._scatter_pool.append(scatter)

    # ═══════════════════════════════════════════
    # 公开 API（与现有 matplotlib 调用方对齐）
    # ═══════════════════════════════════════════

    def set_segments(self, segments):
        """更新分段音高数据。

        Args:
            segments: list of (times_list, pitches_list) tuples.
                      每个元组是一个分段的数据（Python list 或 numpy array）。
        """
        if not self._ready:
            return

        n = min(len(segments), self.MAX_SEGMENTS)

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

                # 转为 numpy（若尚未是），确保 float64 以获得最快的 searchsorted
                x = np.asarray(ts, dtype=np.float64)
                y = np.asarray(ps, dtype=np.float64)
                mn = min(len(x), len(y))
                x, y = x[:mn], y[:mn]

                # 线段 — 数据本身连续，段间由调用方保证不连
                line.setData(x, y)
                line.setVisible(True)

                # 散点 — 仅当点数尚可时显示
                if mn <= 2000:
                    scatter.setData(x, y)
                    scatter.setVisible(True)
                else:
                    scatter.setVisible(False)
            else:
                line.setVisible(False)
                scatter.setVisible(False)

        self._current_segment_count = n

    def set_x_range(self, x_min, x_max):
        """设置 X 轴可见范围（时间窗）。"""
        if not self._ready:
            return
        if x_max > x_min:
            self.plot_widget.setXRange(float(x_min), float(x_max), padding=0.0)

    def set_y_range(self, y_min, y_max):
        """设置 Y 轴可见范围（音高窗）。"""
        if not self._ready:
            return
        if y_max > y_min:
            self.plot_widget.setYRange(float(y_min), float(y_max), padding=0.02)

    def set_grid_lines(self, positions):
        """设置水平网格线位置（八度/半音边界）。

        Args:
            positions: list of float — Y 坐标列表
        """
        if not self._ready:
            return
        positions = positions[:self.MAX_GRID_LINES]

        # 补充分配不足的 InfiniteLine
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
        """设置播放头位置。

        Args:
            x: float — X 坐标（秒），None 则隐藏
        """
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

    def set_line_color(self, color_hex):
        """设置全线颜色。

        Args:
            color_hex: str — '#rrggbb' 格式
        """
        if not self._ready:
            return
        pen = pg.mkPen(color=color_hex, width=1)
        for line in self._line_pool:
            line.setPen(pen)


# ═══════════════════════════════════════════
# 保留旧类以兼容（引用此类的现有代码不会报错）
# ═══════════════════════════════════════════

class PyQtGraphColorGradientWidget(QWidget):
    """[兼容存根] 原彩色渐变组件。功能已迁移到 PyQtGraphPitchRenderer。

    保留此类的 import 路径兼容性。新代码应使用 PyQtGraphPitchRenderer。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._renderer = PyQtGraphPitchRenderer(parent)
        layout.addWidget(self._renderer)

    # 代理到新渲染器的属性和关键方法
    @property
    def plot_widget(self):
        return self._renderer.plot_widget if hasattr(self, '_renderer') else None

    def add_pitch_data(self, time_val, pitch_val, confidence=1.0):
        pass  # 废弃

    def update_color_gradient_display(self):
        pass  # 废弃

    def render_gradient_segments(self, *args, **kwargs):
        pass  # 废弃

    def render_color_particles(self, *args, **kwargs):
        pass  # 废弃

    def render_highlight_point(self, *args, **kwargs):
        pass  # 废弃

    def clear_gradient_elements(self):
        pass  # 废弃

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

    # 生成模拟音高数据：3 秒正弦 + 换气 + 2 秒上行
    sample_rate = 100  # 100 Hz 模拟
    duration = 5.0
    n_total = int(duration * sample_rate)
    t = np.linspace(0, duration, n_total)

    # 模拟音高：在 3-5 八度间波动
    pitch = 3.5 + 1.2 * np.sin(2 * np.pi * 0.8 * t) + 0.4 * np.sin(2 * np.pi * 2.3 * t)

    # 分成两段：0-2.8s, 3.2-5.0s（中间 0.4s 模拟换气）
    mask1 = t <= 2.8
    mask2 = t >= 3.2

    segments = [
        (t[mask1].tolist(), pitch[mask1].tolist()),
        (t[mask2].tolist(), pitch[mask2].tolist()),
    ]

    renderer.set_segments(segments)
    renderer.set_x_range(0, 6.0)
    renderer.set_y_range(1.0, 7.0)
    renderer.set_grid_lines([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    renderer.set_playhead(4.0)

    # FPS 计数器
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

    # 滚动模拟：每 50ms 推进时间窗
    scroll_start = time.perf_counter()
    scroll_total = 20.0  # 模拟 20 秒滚动

    def scroll_tick():
        elapsed = time.perf_counter() - scroll_start
        if elapsed > scroll_total:
            timer.stop()
            fps_label.setText(fps_label.text() + " (done)")
            return

        # 推进时间窗
        win_start = max(0, elapsed - 3.0)
        win_end = elapsed + 3.0
        renderer.set_x_range(win_start, win_end)
        renderer.set_playhead(elapsed)
        update_fps()

    timer = QTimer()
    timer.timeout.connect(scroll_tick)
    timer.start(33)  # ~30 FPS 驱动

    print("Phase 1 test running: 5s simulated pitch data, 20s auto-scroll")
    print("Expected: 45-60+ FPS, smooth scrolling, clean segment breaks")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    _test_renderer()
