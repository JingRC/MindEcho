#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQtGraph彩色渐变组件 - 专门替换integrated_recording_interface中的彩色渐变模式
"""

import sys
import numpy as np
import colorsys
from collections import deque

# 尝试导入PyQtGraph
PYQTGRAPH_AVAILABLE = False
try:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtWidgets
    PYQTGRAPH_AVAILABLE = True
    print("✅ PyQtGraph 导入成功")
except ImportError as e:
    print(f"❌ PyQtGraph 导入失败: {e}")
    print("将使用Matplotlib备用方案")

# 备用：导入Qt
try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    QT_VERSION = 6
    print("✅ PyQt6 可用")
except ImportError:
    try:
        from PyQt5.QtWidgets import *
        from PyQt5.QtCore import *
        from PyQt5.QtGui import *
        QT_VERSION = 5
        print("✅ PyQt5 可用")
    except ImportError:
        raise ImportError("需要安装 PyQt6 或 PyQt5")


class PyQtGraphColorGradientWidget(QWidget):
    """PyQtGraph彩色渐变widget - 专门用于替换matplotlib的彩色渐变显示"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_widget()
        
        # 数据存储
        self.max_points = 10000
        self.times = deque(maxlen=self.max_points)
        self.pitches = deque(maxlen=self.max_points)
        self.confidences = deque(maxlen=self.max_points)
        
        # 渲染元素
        self.gradient_curves = []
        self.particle_scatter = None
        self.highlight_point = None
        
    def setup_widget(self):
        """设置PyQtGraph widget"""
        if not PYQTGRAPH_AVAILABLE:
            # 备用显示
            layout = QVBoxLayout(self)
            label = QLabel("❌ PyQtGraph 不可用\n使用 pip install pyqtgraph 安装")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: red; font-size: 14px;")
            layout.addWidget(label)
            return
        
        # 设置PyQtGraph
        pg.setConfigOption('background', '#1a1a1a')
        pg.setConfigOption('foreground', '#ffffff')
        pg.setConfigOption('antialias', True)
        
        # 创建布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建绘图widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', '音高 (八度)', color='#ffffff', size='12pt')
        self.plot_widget.setLabel('bottom', '时间 (秒)', color='#ffffff', size='12pt')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        # 设置Y轴范围（音高范围）
        self.plot_widget.setYRange(1, 7)
        
        # 添加到布局
        layout.addWidget(self.plot_widget)
        
        print("✅ PyQtGraph彩色渐变组件初始化完成")
    
    def add_pitch_data(self, time_val, pitch_val, confidence=1.0):
        """添加音高数据点"""
        if not PYQTGRAPH_AVAILABLE:
            return
        
        self.times.append(time_val)
        self.pitches.append(pitch_val)
        self.confidences.append(confidence)
        
        # 自动更新X轴范围
        if len(self.times) > 1:
            time_range = max(self.times) - min(self.times)
            if time_range > 0:
                self.plot_widget.setXRange(min(self.times), max(self.times))
    
    def update_color_gradient_display(self):
        """更新彩色渐变显示 - 主要方法"""
        if not PYQTGRAPH_AVAILABLE or len(self.times) < 2:
            return
        
        # 清除旧的渐变元素
        self.clear_gradient_elements()
        
        # 转换为numpy数组
        times_array = np.array(self.times)
        pitches_array = np.array(self.pitches)
        confidences_array = np.array(self.confidences)
        
        print(f"🌈 PyQtGraph更新彩色渐变：{len(times_array)}个数据点")
        
        # 方法1：分段彩色线条
        self.render_gradient_segments(times_array, pitches_array, confidences_array)
        
        # 方法2：彩色粒子散点
        self.render_color_particles(times_array, pitches_array, confidences_array)
        
        # 方法3：高亮当前位置
        self.render_highlight_point(times_array, pitches_array)
        
    def render_gradient_segments(self, times, pitches, confidences):
        """渲染彩色渐变线段"""
        num_segments = min(20, len(times) - 1)  # 最多20段
        
        for i in range(num_segments):
            start_idx = int(i * (len(times) - 1) / num_segments)
            end_idx = int((i + 1) * (len(times) - 1) / num_segments) + 1
            
            if start_idx >= len(times) or end_idx > len(times) or end_idx - start_idx < 2:
                continue
            
            # 获取线段数据
            segment_times = times[start_idx:end_idx]
            segment_pitches = pitches[start_idx:end_idx]
            segment_confidence = np.mean(confidences[start_idx:end_idx])
            
            # 计算HSV彩虹色
            avg_pitch = np.mean(segment_pitches)
            hue = ((avg_pitch - 1.0) % 6.0) / 6.0  # 音高映射到色相
            saturation = 0.8 + 0.2 * segment_confidence  # 置信度影响饱和度
            value = 0.9 + 0.1 * (i / num_segments)  # 线段位置影响亮度
            
            # HSV转RGB
            rgb = colorsys.hsv_to_rgb(hue, saturation, value)
            color = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            
            # 计算线宽（拖尾效果）
            width = 1.5 + 3.0 * (i / num_segments)  # 1.5到4.5的渐变
            
            # 创建线条
            pen = pg.mkPen(color=color, width=width, style=QtCore.Qt.PenStyle.SolidLine)
            curve = self.plot_widget.plot(segment_times, segment_pitches, pen=pen)
            self.gradient_curves.append(curve)
        
        print(f"✅ 创建了 {len(self.gradient_curves)} 个彩色线段")
    
    def render_color_particles(self, times, pitches, confidences):
        """渲染彩色粒子散点"""
        # 选择粒子点（降采样以提高性能）
        step = max(1, len(times) // 50)  # 最多50个粒子
        particle_indices = range(0, len(times), step)
        
        particle_times = times[particle_indices]
        particle_pitches = pitches[particle_indices] 
        particle_confidences = confidences[particle_indices]
        
        # 计算每个粒子的颜色
        colors = []
        sizes = []
        
        for i, (pitch, confidence) in enumerate(zip(particle_pitches, particle_confidences)):
            # HSV彩虹色
            hue = ((pitch - 1.0) % 6.0) / 6.0
            saturation = 1.0
            value = 1.0
            
            rgb = colorsys.hsv_to_rgb(hue, saturation, value)
            color = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            colors.append(color)
            
            # 粒子大小基于置信度
            size = 6 + 8 * confidence
            sizes.append(size)
        
        # 创建散点图
        if len(particle_times) > 0:
            self.particle_scatter = self.plot_widget.plot(
                particle_times, particle_pitches,
                pen=None, symbol='o', symbolSize=sizes,
                symbolBrush=colors, symbolPen=None
            )
        
        print(f"✅ 创建了 {len(particle_times)} 个彩色粒子")
    
    def render_highlight_point(self, times, pitches):
        """渲染高亮当前位置点"""
        if len(times) == 0:
            return
        
        # 最新位置
        latest_time = times[-1]
        latest_pitch = pitches[-1]
        
        # 计算高亮颜色
        hue = ((latest_pitch - 1.0) % 6.0) / 6.0
        rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        color = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
        
        # 创建高亮点（大号带边框）
        self.highlight_point = self.plot_widget.plot(
            [latest_time], [latest_pitch],
            pen=None, symbol='o', symbolSize=20,
            symbolBrush=color, 
            symbolPen=pg.mkPen('white', width=3)
        )
        
        print(f"✅ 高亮点位置: 时间={latest_time:.2f}, 音高={latest_pitch:.2f}")
    
    def clear_gradient_elements(self):
        """清除所有渐变元素"""
        # 清除线段
        for curve in self.gradient_curves:
            try:
                self.plot_widget.removeItem(curve)
            except:
                pass
        self.gradient_curves.clear()
        
        # 清除粒子
        if self.particle_scatter is not None:
            try:
                self.plot_widget.removeItem(self.particle_scatter)
            except:
                pass
            self.particle_scatter = None
        
        # 清除高亮点
        if self.highlight_point is not None:
            try:
                self.plot_widget.removeItem(self.highlight_point)
            except:
                pass
            self.highlight_point = None
    
    def clear_all_data(self):
        """清除所有数据"""
        self.times.clear()
        self.pitches.clear()
        self.confidences.clear()
        self.clear_gradient_elements()
        
        if PYQTGRAPH_AVAILABLE:
            self.plot_widget.clear()


def test_pyqtgraph_gradient():
    """测试PyQtGraph彩色渐变组件"""
    if not PYQTGRAPH_AVAILABLE:
        print("❌ PyQtGraph不可用，无法测试")
        return
    
    app = QApplication(sys.argv)
    
    # 创建主窗口
    window = QWidget()
    window.setWindowTitle("PyQtGraph 彩色渐变测试")
    window.setGeometry(100, 100, 1200, 800)
    
    layout = QVBoxLayout(window)
    
    # 创建渐变组件
    gradient_widget = PyQtGraphColorGradientWidget()
    layout.addWidget(gradient_widget)
    
    # 生成测试数据
    print("🎵 生成彩虹测试数据...")
    duration = 6.0
    sample_rate = 60
    times = np.linspace(0, duration, int(duration * sample_rate))
    
    # 彩虹音高序列
    pitches = 2.0 + 3.5 * (times / duration) + 0.3 * np.sin(2 * np.pi * 2 * times)
    confidences = 0.8 + 0.2 * np.random.random(len(times))
    
    # 添加数据并更新显示
    for t, p, c in zip(times, pitches, confidences):
        gradient_widget.add_pitch_data(t, p, c)
    
    gradient_widget.update_color_gradient_display()
    
    print("✅ PyQtGraph彩色渐变测试准备完成")
    print("💡 您应该看到:")
    print("  • 彩色渐变线段（不同颜色对应不同音高）")
    print("  • 彩色粒子散点")
    print("  • 白边高亮当前位置点")
    
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    test_pyqtgraph_gradient()
