#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案二：PyQtGraph高性能彩色渐变可视化器
如果PyQtGraph不可用，自动回退到增强的Matplotlib方案
"""

import sys
import os
import numpy as np
from collections import deque
import time
import colorsys

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

# 检查PyQtGraph可用性
try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
    print("✅ PyQtGraph 可用 - 将使用高性能渲染")
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    print("⚠️ PyQtGraph 不可用 - 将使用增强的Matplotlib渲染")

# 导入Qt
try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    QT_VERSION = 6
except ImportError:
    try:
        from PyQt5.QtWidgets import *
        from PyQt5.QtCore import *
        from PyQt5.QtGui import *
        QT_VERSION = 5
    except ImportError:
        raise ImportError("需要安装 PyQt6 或 PyQt5")


class SuperiorGradientVisualizer(QWidget):
    """高级彩色渐变可视化器 - PyQtGraph优先，Matplotlib备用"""
    
    def __init__(self):
        super().__init__()
        
        # 数据存储
        self.max_points = 5000
        self.time_data = deque(maxlen=self.max_points)
        self.pitch_data = deque(maxlen=self.max_points)
        self.confidence_data = deque(maxlen=self.max_points)
        
        # 显示参数
        self.time_window = 10.0
        self.y_range = [1.0, 7.0]
        self.use_pyqtgraph = PYQTGRAPH_AVAILABLE
        
        # 性能监控
        self.fps = 0
        self.update_count = 0
        self.last_fps_time = time.time()
        
        # 初始化界面
        self.init_ui()
        self.setup_visualization()
        
        engine = "PyQtGraph" if self.use_pyqtgraph else "Enhanced Matplotlib"
        print(f"✅ 高级可视化器初始化完成 - 引擎: {engine}")
    
    def init_ui(self):
        """初始化界面"""
        engine_name = "PyQtGraph" if self.use_pyqtgraph else "Enhanced Matplotlib"
        self.setWindowTitle(f"MindEcho - 高级彩色渐变可视化器 ({engine_name})")
        self.setGeometry(100, 100, 1500, 900)
        
        # 设置样式
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a;
                color: #ffffff;
                font-family: 'Microsoft YaHei', sans-serif;
            }
            QGroupBox {
                border: 2px solid #404040;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 15px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: #00FF44;
            }
            QPushButton {
                background-color: #404040;
                border: 2px solid #606060;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #505050;
                border-color: #707070;
            }
            QPushButton:pressed {
                background-color: #303030;
            }
            QComboBox {
                background-color: #404040;
                border: 1px solid #606060;
                border-radius: 4px;
                padding: 8px;
                min-width: 150px;
                font-size: 11px;
            }
            QSlider::groove:horizontal {
                background: #404040;
                height: 10px;
                border-radius: 5px;
            }
            QSlider::handle:horizontal {
                background: #00FF44;
                border: 2px solid #00AA00;
                width: 24px;
                border-radius: 12px;
                margin-top: -7px;
                margin-bottom: -7px;
            }
            QSlider::handle:horizontal:hover {
                background: #00FF66;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # 控制面板
        control_panel = self.create_control_panel()
        layout.addWidget(control_panel)
        
        # 可视化区域
        self.visualization_widget = self.create_visualization_widget()
        layout.addWidget(self.visualization_widget)
        
        # 状态面板
        status_panel = self.create_status_panel()
        layout.addWidget(status_panel)
    
    def create_control_panel(self):
        """创建控制面板"""
        group = QGroupBox("🎨 高级彩色渐变控制")
        layout = QVBoxLayout(group)
        
        # 第一行：引擎和模式
        row1 = QHBoxLayout()
        
        engine_text = "PyQtGraph (硬件加速)" if self.use_pyqtgraph else "Enhanced Matplotlib"
        engine_label = QLabel(f"渲染引擎: {engine_text}")
        engine_label.setStyleSheet("color: #00FF44; font-weight: bold;")
        row1.addWidget(engine_label)
        
        row1.addWidget(QLabel("显示模式:"))
        self.mode_combo = QComboBox()
        if self.use_pyqtgraph:
            modes = ["心电图模式", "彩色渐变", "粒子效果", "光谱渐变", "动态拖尾", "3D模拟"]
        else:
            modes = ["心电图模式", "真彩色渐变", "分段彩色", "光谱散点", "渐变拖尾"]
        self.mode_combo.addItems(modes)
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        row1.addWidget(self.mode_combo)
        
        row1.addStretch()
        layout.addLayout(row1)
        
        # 第二行：质量和性能
        row2 = QHBoxLayout()
        
        row2.addWidget(QLabel("渐变质量:"))
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 10)
        self.quality_slider.setValue(6)
        self.quality_slider.valueChanged.connect(self.on_quality_changed)
        row2.addWidget(self.quality_slider)
        
        self.quality_label = QLabel("高质量")
        row2.addWidget(self.quality_label)
        
        row2.addWidget(QLabel("更新频率:"))
        self.fps_slider = QSlider(Qt.Orientation.Horizontal)
        self.fps_slider.setRange(10, 120)
        self.fps_slider.setValue(60)
        self.fps_slider.valueChanged.connect(self.on_fps_changed)
        row2.addWidget(self.fps_slider)
        
        self.fps_target_label = QLabel("60 FPS")
        row2.addWidget(self.fps_target_label)
        
        row2.addStretch()
        layout.addLayout(row2)
        
        # 第三行：功能按钮
        row3 = QHBoxLayout()
        
        self.clear_btn = QPushButton("🗑️ 清除数据")
        self.clear_btn.clicked.connect(self.clear_data)
        row3.addWidget(self.clear_btn)
        
        self.vibrato_btn = QPushButton("🎵 颤音测试")
        self.vibrato_btn.clicked.connect(self.load_vibrato_test)
        row3.addWidget(self.vibrato_btn)
        
        self.rainbow_btn = QPushButton("🌈 彩虹测试")
        self.rainbow_btn.clicked.connect(self.load_rainbow_test)
        row3.addWidget(self.rainbow_btn)
        
        self.performance_btn = QPushButton("📊 性能测试")
        self.performance_btn.clicked.connect(self.run_performance_test)
        row3.addWidget(self.performance_btn)
        
        if not self.use_pyqtgraph:
            self.refresh_btn = QPushButton("🔄 强制刷新")
            self.refresh_btn.clicked.connect(self.force_refresh)
            row3.addWidget(self.refresh_btn)
        
        row3.addStretch()
        layout.addLayout(row3)
        
        return group
    
    def create_visualization_widget(self):
        """创建可视化组件"""
        if self.use_pyqtgraph:
            return self.create_pyqtgraph_widget()
        else:
            return self.create_enhanced_matplotlib_widget()
    
    def create_pyqtgraph_widget(self):
        """创建PyQtGraph可视化组件"""
        # 设置PyQtGraph全局选项
        pg.setConfigOption('background', '#1a1a1a')
        pg.setConfigOption('foreground', '#ffffff')
        pg.setConfigOption('antialias', True)
        
        # 创建绘图widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setMinimumHeight(600)
        
        # 设置标签和网格
        self.plot_widget.setLabel('left', '音高 (八度)', color='#ffffff', size='14pt')
        self.plot_widget.setLabel('bottom', '时间 (秒)', color='#ffffff', size='14pt')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        # 设置范围
        self.plot_widget.setXRange(0, self.time_window)
        self.plot_widget.setYRange(*self.y_range)
        
        # 创建主线条
        self.main_curve = self.plot_widget.plot([], [], 
                                               pen=pg.mkPen(color='#00FF44', width=1.0),
                                               name="音高线")
        
        # 存储渐变元素
        self.gradient_items = []
        self.highlight_point = None
        
        # 添加音名标注
        self.add_note_labels_pyqtgraph()
        
        return self.plot_widget
    
    def create_enhanced_matplotlib_widget(self):
        """创建增强的Matplotlib组件"""
        try:
            # 导入增强的matplotlib可视化器
            from src.gui.improved_matplotlib_visualizer import ImprovedMatplotlibVisualizer
            
            # 创建可视化器实例
            self.matplotlib_visualizer = ImprovedMatplotlibVisualizer()
            
            # 返回其canvas
            return self.matplotlib_visualizer.canvas
            
        except ImportError:
            # 创建简单的标签作为备用
            label = QLabel("❌ 可视化引擎不可用\n请安装 PyQtGraph 或检查 Matplotlib")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size: 16px; color: #ff6666;")
            return label
    
    def add_note_labels_pyqtgraph(self):
        """添加音名标注（PyQtGraph版本）"""
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        for octave in range(1, 8):
            for i, note in enumerate(note_names):
                y_pos = octave + i / 12
                if self.y_range[0] <= y_pos <= self.y_range[1]:
                    text = pg.TextItem(f"{note}{octave}", 
                                     color='#cccccc', 
                                     anchor=(1, 0.5))
                    text.setPos(-0.3, y_pos)
                    self.plot_widget.addItem(text)
    
    def setup_visualization(self):
        """设置可视化"""
        print(f"🎨 设置可视化 - 使用 {'PyQtGraph' if self.use_pyqtgraph else 'Enhanced Matplotlib'}")
    
    def create_status_panel(self):
        """创建状态面板"""
        group = QGroupBox("📊 性能与状态")
        layout = QHBoxLayout(group)
        
        engine = "PyQtGraph" if self.use_pyqtgraph else "Enhanced Matplotlib"
        self.engine_label = QLabel(f"引擎: {engine}")
        layout.addWidget(self.engine_label)
        
        self.data_label = QLabel("数据: 0点")
        layout.addWidget(self.data_label)
        
        self.fps_label = QLabel("FPS: 0")
        layout.addWidget(self.fps_label)
        
        self.mode_label = QLabel("模式: 心电图")
        layout.addWidget(self.mode_label)
        
        self.quality_status_label = QLabel("质量: 高")
        layout.addWidget(self.quality_status_label)
        
        layout.addStretch()
        return group
    
    def add_pitch_data(self, pitch_data):
        """添加音高数据"""
        try:
            time_val = pitch_data.get('time', time.time())
            pitch_val = pitch_data.get('pitch', 0)
            confidence = pitch_data.get('confidence', 1.0)
            
            if pitch_val > 0:
                self.time_data.append(time_val)
                self.pitch_data.append(pitch_val)
                self.confidence_data.append(confidence)
                
                # 更新显示
                self.update_visualization()
                
                # FPS统计
                self.update_count += 1
                
        except Exception as e:
            print(f"添加数据错误: {e}")
    
    def update_visualization(self):
        """更新可视化"""
        if len(self.time_data) == 0:
            return
        
        try:
            if self.use_pyqtgraph:
                self.update_pyqtgraph_visualization()
            else:
                self.update_matplotlib_visualization()
            
            # 计算FPS
            current_time = time.time()
            if current_time - self.last_fps_time >= 1.0:
                self.fps = self.update_count / (current_time - self.last_fps_time)
                self.last_fps_time = current_time
                self.update_count = 0
                self.update_status()
                
        except Exception as e:
            print(f"更新可视化错误: {e}")
    
    def update_pyqtgraph_visualization(self):
        """更新PyQtGraph可视化"""
        times = np.array(self.time_data)
        pitches = np.array(self.pitch_data)
        confidences = np.array(self.confidence_data)
        
        mode = self.mode_combo.currentText()
        
        if mode == "心电图模式":
            self.update_ecg_mode_pyqtgraph(times, pitches)
        elif mode == "彩色渐变":
            self.update_color_gradient_pyqtgraph(times, pitches)
        elif mode == "粒子效果":
            self.update_particle_mode_pyqtgraph(times, pitches)
        elif mode == "光谱渐变":
            self.update_spectrum_mode_pyqtgraph(times, pitches, confidences)
        elif mode == "动态拖尾":
            self.update_trail_mode_pyqtgraph(times, pitches)
        elif mode == "3D模拟":
            self.update_3d_mode_pyqtgraph(times, pitches)
    
    def update_color_gradient_pyqtgraph(self, times, pitches):
        """PyQtGraph彩色渐变模式 - 真正的硬件加速渐变"""
        print(f"🌈 PyQtGraph彩色渐变模式更新，数据点: {len(times)}")
        
        # 清除旧元素
        self.clear_gradient_items()
        
        if len(times) < 2:
            return
        
        # 隐藏主线条
        self.main_curve.setData([], [])
        
        # 获取质量设置
        quality = self.quality_slider.value()
        num_segments = min(len(times) - 1, quality * 8)
        
        # 创建彩色线段
        for i in range(num_segments):
            start_idx = int(i * (len(times) - 1) / num_segments)
            end_idx = int((i + 1) * (len(times) - 1) / num_segments) + 1
            
            if start_idx >= len(times) or end_idx > len(times):
                continue
            
            segment_times = times[start_idx:end_idx]
            segment_pitches = pitches[start_idx:end_idx]
            
            if len(segment_pitches) < 2:
                continue
            
            # 计算颜色
            avg_pitch = np.mean(segment_pitches)
            hue = ((avg_pitch - 1) % 6) / 6
            rgb = colorsys.hsv_to_rgb(hue, 0.9, 1.0)
            color = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            
            # 计算透明度和线宽
            alpha = int(100 + 155 * (i / num_segments))
            width = 1.0 + 4.0 * (i / num_segments)
            
            # 创建线条
            pen = pg.mkPen(color=color, width=width, style=Qt.PenStyle.SolidLine)
            curve = self.plot_widget.plot(segment_times, segment_pitches, pen=pen)
            self.gradient_items.append(curve)
        
        # 添加粒子效果
        if quality >= 7:
            # 高质量模式：添加粒子点
            particle_indices = np.arange(0, len(times), max(1, len(times)//50))
            for idx in particle_indices:
                if idx >= len(times):
                    continue
                
                # 计算粒子颜色
                hue = ((pitches[idx] - 1) % 6) / 6
                rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                color = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
                
                # 创建粒子
                particle = self.plot_widget.plot([times[idx]], [pitches[idx]],
                                                pen=None, symbol='o', symbolSize=8,
                                                symbolBrush=color, symbolPen=None)
                self.gradient_items.append(particle)
        
        # 添加高亮点
        if len(times) > 0:
            latest_time = times[-1]
            latest_pitch = pitches[-1]
            
            hue = ((latest_pitch - 1) % 6) / 6
            rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            color = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            
            # 移除旧高亮点
            if self.highlight_point is not None:
                self.plot_widget.removeItem(self.highlight_point)
            
            # 创建新高亮点
            self.highlight_point = self.plot_widget.plot([latest_time], [latest_pitch],
                                                        pen=None, symbol='o', symbolSize=15,
                                                        symbolBrush=color, 
                                                        symbolPen=pg.mkPen('white', width=3))
        
        print(f"✅ PyQtGraph彩色渐变：创建了 {len(self.gradient_items)} 个元素")
    
    def update_ecg_mode_pyqtgraph(self, times, pitches):
        """心电图模式"""
        self.clear_gradient_items()
        pen = pg.mkPen(color='#00FF44', width=1.0)
        self.main_curve.setData(times, pitches, pen=pen)
    
    def update_particle_mode_pyqtgraph(self, times, pitches):
        """粒子效果模式"""
        self.clear_gradient_items()
        self.main_curve.setData([], [])
        
        if len(times) == 0:
            return
        
        # 创建彩色粒子云
        for i in range(0, len(times), max(1, len(times)//100)):
            hue = ((pitches[i] - 1) % 6) / 6
            rgb = colorsys.hsv_to_rgb(hue, 0.8, 1.0)
            color = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            
            # 随机偏移创建粒子云效果
            offset_x = np.random.normal(0, 0.02)
            offset_y = np.random.normal(0, 0.05)
            
            particle = self.plot_widget.plot([times[i] + offset_x], [pitches[i] + offset_y],
                                            pen=None, symbol='o', symbolSize=6,
                                            symbolBrush=color, symbolPen=None)
            self.gradient_items.append(particle)
    
    def update_spectrum_mode_pyqtgraph(self, times, pitches, confidences):
        """光谱模式"""
        self.clear_gradient_items()
        self.main_curve.setData([], [])
        
        # 根据置信度和音高创建光谱效果
        for i in range(len(times)):
            hue = ((pitches[i] - 1) % 6) / 6
            confidence = confidences[i] if i < len(confidences) else 0.5
            
            rgb = colorsys.hsv_to_rgb(hue, confidence, 1.0)
            color = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            
            size = 4 + 8 * confidence
            
            point = self.plot_widget.plot([times[i]], [pitches[i]],
                                         pen=None, symbol='o', symbolSize=size,
                                         symbolBrush=color, symbolPen=None)
            self.gradient_items.append(point)
    
    def update_trail_mode_pyqtgraph(self, times, pitches):
        """动态拖尾模式"""
        self.clear_gradient_items()
        self.main_curve.setData([], [])
        
        if len(times) < 10:
            return
        
        # 创建多层拖尾
        trail_layers = 5
        trail_length = min(len(times), 100)
        
        for layer in range(trail_layers):
            start_idx = max(0, len(times) - trail_length + layer * 20)
            end_idx = len(times)
            
            if start_idx >= end_idx:
                continue
            
            layer_times = times[start_idx:end_idx]
            layer_pitches = pitches[start_idx:end_idx]
            
            # 计算拖尾颜色
            alpha = 50 + 205 * (layer / trail_layers)
            width = 0.5 + 3.5 * (layer / trail_layers)
            
            # 渐变色
            avg_pitch = np.mean(layer_pitches)
            hue = ((avg_pitch - 1) % 6) / 6
            rgb = colorsys.hsv_to_rgb(hue, 0.8, 1.0)
            color = (*[int(c*255) for c in rgb], int(alpha))
            
            pen = pg.mkPen(color=color, width=width)
            curve = self.plot_widget.plot(layer_times, layer_pitches, pen=pen)
            self.gradient_items.append(curve)
    
    def update_3d_mode_pyqtgraph(self, times, pitches):
        """3D模拟模式"""
        self.clear_gradient_items()
        self.main_curve.setData([], [])
        
        # 创建多层3D效果
        layers = 4
        for layer in range(layers):
            offset = layer * 0.05
            alpha = 255 - layer * 60
            width = 4 - layer * 0.8
            
            layer_times = times + offset
            
            # 层次颜色
            if layer == 0:
                color = (0, 255, 68, alpha)  # 前景绿色
            elif layer == 1:
                color = (0, 200, 100, alpha)
            elif layer == 2:
                color = (0, 150, 150, alpha)
            else:
                color = (0, 100, 200, alpha)  # 背景蓝色
            
            pen = pg.mkPen(color=color, width=width)
            curve = self.plot_widget.plot(layer_times, pitches, pen=pen)
            self.gradient_items.append(curve)
    
    def update_matplotlib_visualization(self):
        """更新Matplotlib可视化（备用）"""
        if hasattr(self, 'matplotlib_visualizer'):
            # 转发数据到matplotlib可视化器
            for i, (t, p, c) in enumerate(zip(self.time_data, self.pitch_data, self.confidence_data)):
                if i % 5 == 0:  # 降采样以提高性能
                    self.matplotlib_visualizer.add_pitch_data({
                        'time': t,
                        'pitch': p, 
                        'confidence': c
                    })
    
    def clear_gradient_items(self):
        """清除渐变元素"""
        for item in self.gradient_items:
            try:
                self.plot_widget.removeItem(item)
            except:
                pass
        self.gradient_items.clear()
        
        if self.highlight_point is not None:
            try:
                self.plot_widget.removeItem(self.highlight_point)
            except:
                pass
            self.highlight_point = None
    
    def on_mode_changed(self, mode):
        """模式改变"""
        self.mode_label.setText(f"模式: {mode}")
        print(f"🔄 切换模式: {mode}")
        self.update_visualization()
    
    def on_quality_changed(self, value):
        """质量改变"""
        quality_names = ["最低", "很低", "低", "中低", "中等", "中高", "高", "很高", "最高", "极致"]
        quality_name = quality_names[value-1] if value <= len(quality_names) else "超级"
        self.quality_label.setText(quality_name)
        self.quality_status_label.setText(f"质量: {quality_name}")
        self.update_visualization()
    
    def on_fps_changed(self, value):
        """FPS目标改变"""
        self.fps_target_label.setText(f"{value} FPS")
    
    def clear_data(self):
        """清除数据"""
        self.time_data.clear()
        self.pitch_data.clear()
        self.confidence_data.clear()
        
        if self.use_pyqtgraph:
            self.main_curve.setData([], [])
            self.clear_gradient_items()
        elif hasattr(self, 'matplotlib_visualizer'):
            self.matplotlib_visualizer.clear_data()
        
        self.update_status()
        print("🗑️ 数据已清除")
    
    def load_vibrato_test(self):
        """加载颤音测试数据"""
        print("🎵 加载颤音测试数据")
        self.clear_data()
        
        duration = 8.0
        sample_rate = 80
        times = np.linspace(0, duration, int(duration * sample_rate))
        
        base_pitch = 4.0
        melody = 0.8 * np.sin(2 * np.pi * 0.25 * times)
        vibrato = 0.15 * np.sin(2 * np.pi * 7.5 * times)
        noise = 0.03 * np.random.random(len(times))
        
        pitches = base_pitch + melody + vibrato + noise
        confidences = 0.8 + 0.2 * np.random.random(len(times))
        
        for t, p, c in zip(times, pitches, confidences):
            self.add_pitch_data({'time': t, 'pitch': p, 'confidence': c})
        
        print("✅ 颤音测试数据加载完成")
    
    def load_rainbow_test(self):
        """加载彩虹测试数据"""
        print("🌈 加载彩虹测试数据")
        self.clear_data()
        
        duration = 10.0
        sample_rate = 60
        times = np.linspace(0, duration, int(duration * sample_rate))
        
        # 创建跨越多个八度的彩虹音高变化
        pitches = 2.0 + 4.0 * (np.sin(2 * np.pi * 0.2 * times) + 1) / 2
        pitches += 0.3 * np.sin(2 * np.pi * 1.5 * times)  # 添加快速变化
        
        confidences = np.ones_like(times) * 0.9
        
        for t, p, c in zip(times, pitches, confidences):
            self.add_pitch_data({'time': t, 'pitch': p, 'confidence': c})
        
        print("✅ 彩虹测试数据加载完成")
    
    def run_performance_test(self):
        """运行性能测试"""
        print("📊 运行性能测试...")
        
        if not self.use_pyqtgraph:
            print("⚠️ 性能测试主要针对PyQtGraph引擎")
        
        # 测试大数据量性能
        start_time = time.time()
        
        duration = 5.0
        sample_rate = 200  # 高采样率
        times = np.linspace(0, duration, int(duration * sample_rate))
        pitches = 3.5 + 1.5 * np.sin(2 * np.pi * times) + 0.5 * np.sin(2 * np.pi * 5 * times)
        
        for t, p in zip(times, pitches):
            self.add_pitch_data({'time': t, 'pitch': p, 'confidence': 0.9})
        
        end_time = time.time()
        process_time = end_time - start_time
        
        print(f"✅ 性能测试完成")
        print(f"   处理 {len(times)} 个数据点")
        print(f"   用时: {process_time:.2f}秒")
        print(f"   平均速度: {len(times)/process_time:.1f} 点/秒")
        print(f"   当前FPS: {self.fps:.1f}")
    
    def force_refresh(self):
        """强制刷新（仅Matplotlib模式）"""
        if hasattr(self, 'matplotlib_visualizer'):
            self.matplotlib_visualizer.force_redraw()
        print("🔄 强制刷新完成")
    
    def update_status(self):
        """更新状态"""
        data_count = len(self.time_data)
        self.data_label.setText(f"数据: {data_count}点")
        self.fps_label.setText(f"FPS: {self.fps:.1f}")


def test_superior_gradient():
    """测试高级渐变可视化器"""
    app = QApplication(sys.argv)
    
    print("🚀 启动 MindEcho 高级彩色渐变可视化器")
    print("=" * 60)
    print(f"✅ PyQtGraph 可用: {PYQTGRAPH_AVAILABLE}")
    
    try:
        visualizer = SuperiorGradientVisualizer()
        visualizer.show()
        
        print("\n💡 使用说明:")
        if PYQTGRAPH_AVAILABLE:
            print("  🚀 PyQtGraph模式 - 硬件加速渲染")
            print("  🎵 点击'颤音测试'查看细腻的渐变效果")
            print("  🌈 点击'彩虹测试'查看全彩色范围")
            print("  📊 点击'性能测试'验证高性能渲染")
            print("  🎛️ 调整'渐变质量'体验不同效果")
            print("  🔄 切换显示模式体验多种渐变")
        else:
            print("  📊 Enhanced Matplotlib模式 - 优化兼容性")
            print("  🎵 点击'颤音测试'查看改进的渐变")
            print("  🔄 点击'强制刷新'解决显示问题")
        
        print("\n🎯 重点验证:")
        print("  • 彩色渐变模式是否显示真正的彩色效果")
        print("  • 心电图模式线条是否够细")
        print("  • 渐变拖尾效果是否流畅")
        print("  • 整体性能是否达到预期")
        
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_superior_gradient()
