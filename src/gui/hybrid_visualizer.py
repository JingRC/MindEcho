#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成PyQtGraph的高性能音高可视化器
解决Matplotlib彩色渐变模式问题的替代方案
"""

import sys
import os
import numpy as np
from collections import deque
import time

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

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

# 检查PyQtGraph可用性
try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
    print("✅ PyQtGraph 可用，将使用高性能渲染")
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    print("⚠️ PyQtGraph 不可用，建议安装: pip install pyqtgraph")

# 导入音频处理模块（兼容多种包结构，避免静态未解析错误）
try:
    import importlib
    try:
        IntegratedAudioProcessor = importlib.import_module('src.audio_processing.integrated_processor').IntegratedAudioProcessor
    except Exception:
        IntegratedAudioProcessor = importlib.import_module('audio_processing.integrated_processor').IntegratedAudioProcessor
except Exception:
    print("⚠️ 音频处理模块不可用，将使用模拟数据")
    IntegratedAudioProcessor = None


class HybridPitchVisualizer(QWidget):
    """混合型音高可视化器 - 支持Matplotlib和PyQtGraph"""
    
    def __init__(self, use_pyqtgraph=True):
        super().__init__()
        
        self.use_pyqtgraph = use_pyqtgraph and PYQTGRAPH_AVAILABLE
        
        # 数据存储
        self.max_points = 5000
        self.time_data = deque(maxlen=self.max_points)
        self.pitch_data = deque(maxlen=self.max_points)
        self.confidence_data = deque(maxlen=self.max_points)
        
        # 显示参数
        self.time_window = 10.0
        self.y_range = [1.0, 7.0]
        # 统一显示模式命名：原“心电图模式”改为“普通模式”
        self.display_mode = "普通模式"
        
        # 性能监控
        self.last_update_time = time.time()
        self.update_count = 0
        self.fps = 0
        
        # 初始化界面
        self.init_ui()
        self.setup_visualization()
        
        print(f"✅ 混合可视化器初始化完成 (PyQtGraph: {self.use_pyqtgraph})")
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("MindEcho - 高性能音高可视化 (PyQtGraph增强版)")
        self.setGeometry(100, 100, 1400, 900)
        
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
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px 0 8px;
                color: #00FF44;
            }
            QPushButton {
                background-color: #404040;
                border: 2px solid #606060;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 11px;
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
                padding: 6px;
                min-width: 140px;
                font-size: 11px;
            }
            QComboBox:drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QSlider::groove:horizontal {
                background: #404040;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00FF44;
                border: 2px solid #00AA00;
                width: 20px;
                border-radius: 10px;
                margin-top: -6px;
                margin-bottom: -6px;
            }
            QSlider::handle:horizontal:hover {
                background: #00FF66;
            }
            QLabel {
                font-size: 11px;
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
        group = QGroupBox("🎛️ 可视化控制")
        layout = QVBoxLayout(group)
        
        # 第一行：模式和引擎选择
        row1 = QHBoxLayout()
        
        row1.addWidget(QLabel("渲染引擎:"))
        self.engine_combo = QComboBox()
        engines = ["PyQtGraph (推荐)", "Matplotlib (兼容)"]
        self.engine_combo.addItems(engines)
        if self.use_pyqtgraph:
            self.engine_combo.setCurrentIndex(0)
        else:
            self.engine_combo.setCurrentIndex(1)
        self.engine_combo.currentTextChanged.connect(self.on_engine_changed)
        row1.addWidget(self.engine_combo)
        
        row1.addWidget(QLabel("显示模式:"))
        self.mode_combo = QComboBox()
        modes = ["普通模式", "彩色渐变", "频谱模式", "动态拖尾", "3D效果"]
        self.mode_combo.addItems(modes)
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        row1.addWidget(self.mode_combo)
        
        row1.addStretch()
        layout.addLayout(row1)
        
        # 第二行：参数控制
        row2 = QHBoxLayout()
        
        row2.addWidget(QLabel("时间窗口:"))
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(30, 300)  # 3-30秒
        self.time_slider.setValue(100)  # 默认10秒
        self.time_slider.valueChanged.connect(self.on_time_window_changed)
        row2.addWidget(self.time_slider)
        
        self.time_label = QLabel("10.0s")
        row2.addWidget(self.time_label)
        
        row2.addWidget(QLabel("细节级别:"))
        self.detail_slider = QSlider(Qt.Orientation.Horizontal)
        self.detail_slider.setRange(1, 10)
        self.detail_slider.setValue(5)
        self.detail_slider.valueChanged.connect(self.on_detail_changed)
        row2.addWidget(self.detail_slider)
        
        self.detail_label = QLabel("中等")
        row2.addWidget(self.detail_label)
        
        row2.addStretch()
        layout.addLayout(row2)
        
        # 第三行：功能按钮
        row3 = QHBoxLayout()
        
        self.clear_btn = QPushButton("🗑️ 清除数据")
        self.clear_btn.clicked.connect(self.clear_data)
        row3.addWidget(self.clear_btn)
        
        self.test_btn = QPushButton("🎵 加载颤音测试")
        self.test_btn.clicked.connect(self.load_vibrato_test)
        row3.addWidget(self.test_btn)
        
        self.gradient_test_btn = QPushButton("🌈 测试渐变效果")
        self.gradient_test_btn.clicked.connect(self.test_gradient_performance)
        row3.addWidget(self.gradient_test_btn)
        
        self.performance_btn = QPushButton("📊 性能测试")
        self.performance_btn.clicked.connect(self.run_performance_test)
        row3.addWidget(self.performance_btn)
        
        row3.addStretch()
        layout.addLayout(row3)
        
        return group
    
    def create_visualization_widget(self):
        """创建可视化组件"""
        if self.use_pyqtgraph:
            return self.create_pyqtgraph_widget()
        else:
            return self.create_matplotlib_widget()
    
    def create_pyqtgraph_widget(self):
        """创建PyQtGraph可视化组件"""
        # 设置PyQtGraph全局选项
        pg.setConfigOption('background', '#1a1a1a')
        pg.setConfigOption('foreground', '#ffffff')
        pg.setConfigOption('antialias', True)
        
        # 创建绘图widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setMinimumHeight(500)
        
        # 设置标签和网格
        self.plot_widget.setLabel('left', '音高 (八度)', color='#ffffff', size='12pt')
        self.plot_widget.setLabel('bottom', '时间 (秒)', color='#ffffff', size='12pt')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        # 设置范围
        self.plot_widget.setXRange(0, self.time_window)
        self.plot_widget.setYRange(*self.y_range)
        
        # 创建主线条
        self.main_curve = self.plot_widget.plot([], [], 
                                               pen=pg.mkPen(color='#00FF44', width=1.0),
                                               name="音高线")
        
        # 存储渐变线条
        self.gradient_curves = []
        self.highlight_point = None
        
        # 添加音名标注
        self.add_note_labels_pyqtgraph()
        
        return self.plot_widget
    
    def create_matplotlib_widget(self):
        """创建Matplotlib可视化组件（备用）"""
        try:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
            
            self.fig = Figure(figsize=(12, 6), facecolor='#1a1a1a')
            self.canvas = FigureCanvas(self.fig)
            self.canvas.setMinimumHeight(500)
            
            self.ax = self.fig.add_subplot(111, facecolor='#1a1a1a')
            self.ax.set_xlim(0, self.time_window)
            self.ax.set_ylim(*self.y_range)
            
            # 设置样式
            self.ax.tick_params(colors='#ffffff')
            self.ax.xaxis.label.set_color('#ffffff')
            self.ax.yaxis.label.set_color('#ffffff')
            self.ax.set_xlabel('时间 (秒)')
            self.ax.set_ylabel('音高 (八度)')
            
            # 创建主线条
            self.pitch_line, = self.ax.plot([], [], color='#00FF44', linewidth=1.0)
            
            self.canvas.draw()
            return self.canvas
            
        except ImportError:
            # 如果matplotlib也不可用，创建一个简单的标签
            label = QLabel("❌ 可视化引擎不可用\n请安装 PyQtGraph 或 Matplotlib")
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
        print(f"🎨 设置可视化 - 使用 {'PyQtGraph' if self.use_pyqtgraph else 'Matplotlib'}")
    
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
                
                # 性能统计
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
            if current_time - self.last_update_time >= 1.0:
                self.fps = self.update_count / (current_time - self.last_update_time)
                self.last_update_time = current_time
                self.update_count = 0
        except Exception as e:
            print(f"更新可视化错误: {e}")
    
    def update_pyqtgraph_visualization(self):
        """更新PyQtGraph可视化"""
        times = np.array(self.time_data)
        pitches = np.array(self.pitch_data)
        confidences = np.array(self.confidence_data)
        
        mode = self.mode_combo.currentText()
        
        if mode in ("普通模式", "心电图模式"):
            self.update_ecg_mode_pyqtgraph(times, pitches)
        elif mode == "彩色渐变":
            self.update_gradient_mode_pyqtgraph(times, pitches, confidences)
        elif mode == "频谱模式":
            self.update_spectrum_mode_pyqtgraph(times, pitches, confidences)
        elif mode == "动态拖尾":
            self.update_trail_mode_pyqtgraph(times, pitches)
        elif mode == "3D效果":
            self.update_3d_mode_pyqtgraph(times, pitches)
    
    def update_ecg_mode_pyqtgraph(self, times, pitches):
        """心电图模式 - PyQtGraph"""
        # 清除渐变线条
        self.clear_gradient_curves()
        
        # 设置细线条
        pen = pg.mkPen(color='#00FF44', width=1.0)
        self.main_curve.setData(times, pitches, pen=pen)
    
    def update_gradient_mode_pyqtgraph(self, times, pitches, confidences):
        """彩色渐变模式 - PyQtGraph高性能实现"""
        print(f"🌈 PyQtGraph渐变模式更新，数据点: {len(times)}")
        
        # 清除旧的渐变线条
        self.clear_gradient_curves()
        
        if len(times) < 2:
            return
        
        # 计算渐变段数
        detail_level = self.detail_slider.value()
        num_segments = min(len(times) - 1, detail_level * 5)
        
        for i in range(num_segments):
            start_idx = int(i * (len(times) - 1) / num_segments)
            end_idx = int((i + 1) * (len(times) - 1) / num_segments) + 1
            
            if start_idx >= len(times) or end_idx > len(times):
                continue
            
            segment_times = times[start_idx:end_idx]
            segment_pitches = pitches[start_idx:end_idx]
            
            if len(segment_pitches) == 0:
                continue
            
            # 音高颜色映射
            avg_pitch = np.mean(segment_pitches)
            color = self.get_pitch_color(avg_pitch)
            
            # 拖尾效果参数
            alpha = int(100 + 155 * (i / num_segments))
            width = 1.0 + 3.0 * (i / num_segments)
            
            # 创建颜色对象
            color_obj = QColor(color)
            color_obj.setAlpha(alpha)
            
            # 创建线条
            pen = pg.mkPen(color=color_obj, width=width)
            curve = self.plot_widget.plot(segment_times, segment_pitches, pen=pen)
            self.gradient_curves.append(curve)
        
        # 添加高亮点
        if len(times) > 0:
            self.update_highlight_point(times[-1], pitches[-1])
        
        print(f"✅ PyQtGraph渐变模式：创建了 {len(self.gradient_curves)} 个渐变段")
    
    def update_spectrum_mode_pyqtgraph(self, times, pitches, confidences):
        """频谱模式"""
        self.clear_gradient_curves()
        
        # 根据置信度调整透明度
        if len(confidences) > 0:
            avg_confidence = np.mean(confidences)
            alpha = int(100 + 155 * avg_confidence)
            color = QColor('#00AAFF')
            color.setAlpha(alpha)
            pen = pg.mkPen(color=color, width=2)
            self.main_curve.setData(times, pitches, pen=pen)
    
    def update_trail_mode_pyqtgraph(self, times, pitches):
        """动态拖尾模式"""
        self.clear_gradient_curves()
        
        if len(times) < 10:
            return
        
        # 创建多条递减的拖尾线
        trail_length = min(100, len(times))
        
        for i in range(5):  # 5条拖尾线
            start_idx = max(0, len(times) - trail_length + i * 20)
            end_idx = len(times)
            
            if start_idx >= end_idx:
                continue
            
            trail_times = times[start_idx:end_idx]
            trail_pitches = pitches[start_idx:end_idx]
            
            alpha = int(50 + 205 * (i / 4))
            width = 0.5 + 2.5 * (i / 4)
            
            color = QColor('#00FF44')
            color.setAlpha(alpha)
            pen = pg.mkPen(color=color, width=width)
            
            curve = self.plot_widget.plot(trail_times, trail_pitches, pen=pen)
            self.gradient_curves.append(curve)
    
    def update_3d_mode_pyqtgraph(self, times, pitches):
        """3D效果模式"""
        self.clear_gradient_curves()
        
        # 创建多层线条模拟3D效果
        for layer in range(4):
            offset = layer * 0.03
            alpha = 255 - layer * 60
            width = 3 - layer * 0.5
            
            layer_times = times + offset
            
            color = QColor('#00FF44')
            color.setAlpha(alpha)
            pen = pg.mkPen(color=color, width=width)
            
            curve = self.plot_widget.plot(layer_times, pitches, pen=pen)
            self.gradient_curves.append(curve)
    
    def update_matplotlib_visualization(self):
        """更新Matplotlib可视化（备用）"""
        if not hasattr(self, 'pitch_line'):
            return
        
        times = list(self.time_data)
        pitches = list(self.pitch_data)
        
        self.pitch_line.set_data(times, pitches)
        
        # 调整X轴范围
        if len(times) > 0:
            latest_time = times[-1]
            self.ax.set_xlim(max(0, latest_time - self.time_window), latest_time + 1)
        
        self.canvas.draw_idle()
    
    def get_pitch_color(self, pitch):
        """根据音高获取颜色"""
        if pitch < 2:
            return '#0066FF'  # 低音-蓝色
        elif pitch < 3.5:
            return '#00AAFF'  # 中低音-青色
        elif pitch < 5:
            return '#AADD00'  # 中音-黄绿
        elif pitch < 6.5:
            return '#FF9900'  # 中高音-橙色
        else:
            return '#FF3366'  # 高音-红色
    
    def update_highlight_point(self, time_val, pitch_val):
        """更新高亮点"""
        # 移除旧的高亮点
        if self.highlight_point is not None:
            try:
                self.plot_widget.removeItem(self.highlight_point)
            except:
                pass
        
        # 创建新的高亮点
        color = self.get_pitch_color(pitch_val)
        self.highlight_point = self.plot_widget.plot([time_val], [pitch_val],
                                                    pen=None,
                                                    symbol='o',
                                                    symbolSize=12,
                                                    symbolBrush=color,
                                                    symbolPen=pg.mkPen('white', width=2))
    
    def clear_gradient_curves(self):
        """清除渐变线条"""
        for curve in self.gradient_curves:
            try:
                self.plot_widget.removeItem(curve)
            except:
                pass
        self.gradient_curves.clear()
        
        # 清除高亮点
        if self.highlight_point is not None:
            try:
                self.plot_widget.removeItem(self.highlight_point)
            except:
                pass
            self.highlight_point = None
    
    def create_status_panel(self):
        """创建状态面板"""
        group = QGroupBox("📊 性能与状态")
        layout = QHBoxLayout(group)
        
        self.engine_status_label = QLabel("引擎: PyQtGraph")
        layout.addWidget(self.engine_status_label)
        
        self.data_count_label = QLabel("数据: 0点")
        layout.addWidget(self.data_count_label)
        
        self.fps_label = QLabel("FPS: 0")
        layout.addWidget(self.fps_label)
        
        self.mode_status_label = QLabel("模式: 普通模式")
        layout.addWidget(self.mode_status_label)
        
        layout.addStretch()
        return group
    
    def on_engine_changed(self, engine_text):
        """切换渲染引擎"""
        if "PyQtGraph" in engine_text and PYQTGRAPH_AVAILABLE:
            print("🔄 切换到 PyQtGraph 引擎")
            # 这里可以实现引擎切换逻辑
        elif "Matplotlib" in engine_text:
            print("🔄 切换到 Matplotlib 引擎")
            # 这里可以实现引擎切换逻辑
    
    def on_mode_changed(self, mode):
        """显示模式改变"""
        self.display_mode = mode
        self.mode_status_label.setText(f"模式: {mode}")
        print(f"🎨 切换显示模式: {mode}")
        self.update_visualization()
    
    def on_time_window_changed(self, value):
        """时间窗口改变"""
        self.time_window = value / 10.0
        self.time_label.setText(f"{self.time_window:.1f}s")
        
        if self.use_pyqtgraph:
            if len(self.time_data) > 0:
                latest_time = self.time_data[-1]
                self.plot_widget.setXRange(latest_time - self.time_window, latest_time)
            else:
                self.plot_widget.setXRange(0, self.time_window)
    
    def on_detail_changed(self, value):
        """细节级别改变"""
        levels = ["最低", "很低", "低", "中低", "中等", "中高", "高", "很高", "最高", "极致"]
        self.detail_label.setText(levels[value-1])
        
        # 重新更新显示
        self.update_visualization()
    
    def clear_data(self):
        """清除数据"""
        self.time_data.clear()
        self.pitch_data.clear()
        self.confidence_data.clear()
        
        if self.use_pyqtgraph:
            self.main_curve.setData([], [])
            self.clear_gradient_curves()
        else:
            if hasattr(self, 'pitch_line'):
                self.pitch_line.set_data([], [])
                self.canvas.draw()
        
        self.update_status()
        print("🗑️ 数据已清除")
    
    def load_vibrato_test(self):
        """加载颤音测试数据"""
        print("🎵 加载颤音测试数据...")
        self.clear_data()
        
        # 生成颤音数据
        duration = 6.0
        sample_rate = 80
        times = np.linspace(0, duration, int(duration * sample_rate))
        
        base_pitch = 4.0
        melody = 0.6 * np.sin(2 * np.pi * 0.3 * times)
        vibrato = 0.12 * np.sin(2 * np.pi * 7.0 * times)
        noise = 0.02 * np.random.random(len(times))
        
        pitches = base_pitch + melody + vibrato + noise
        confidences = 0.8 + 0.2 * np.random.random(len(times))
        
        # 模拟实时添加
        for i, (t, p, c) in enumerate(zip(times, pitches, confidences)):
            self.add_pitch_data({
                'time': t,
                'pitch': p,
                'confidence': c
            })
            
            if i % 30 == 0:  # 每30个点更新界面
                QApplication.processEvents()
        
        print("✅ 颤音测试数据加载完成")
    
    def test_gradient_performance(self):
        """测试渐变性能"""
        print("🌈 测试渐变性能...")
        
        # 切换到彩色渐变模式
        self.mode_combo.setCurrentText("彩色渐变")
        
        # 生成大量数据测试性能
        duration = 10.0
        sample_rate = 100
        times = np.linspace(0, duration, int(duration * sample_rate))
        
        # 复杂音高变化
        pitches = 4.0 + np.sin(2 * np.pi * 0.5 * times) + 0.3 * np.sin(2 * np.pi * 3 * times)
        confidences = np.ones_like(times) * 0.9
        
        start_time = time.time()
        
        for t, p, c in zip(times, pitches, confidences):
            self.add_pitch_data({'time': t, 'pitch': p, 'confidence': c})
        
        end_time = time.time()
        process_time = end_time - start_time
        
        print(f"✅ 渐变性能测试完成")
        print(f"   处理 {len(times)} 个数据点")
        print(f"   用时: {process_time:.2f}秒")
        print(f"   平均速度: {len(times)/process_time:.1f} 点/秒")
    
    def run_performance_test(self):
        """运行完整性能测试"""
        print("📊 运行完整性能测试...")
        
        modes = ["普通模式", "彩色渐变", "频谱模式", "动态拖尾"]
        results = {}
        
        for mode in modes:
            print(f"  测试 {mode}...")
            self.clear_data()
            self.mode_combo.setCurrentText(mode)
            
            # 生成测试数据
            test_data_size = 500
            times = np.linspace(0, 5, test_data_size)
            pitches = 4.0 + np.sin(2 * np.pi * times)
            
            start_time = time.time()
            
            for t, p in zip(times, pitches):
                self.add_pitch_data({'time': t, 'pitch': p, 'confidence': 0.9})
            
            end_time = time.time()
            process_time = end_time - start_time
            fps = test_data_size / process_time
            
            results[mode] = fps
            print(f"    {mode}: {fps:.1f} FPS")
        
        print("\n📈 性能测试结果:")
        for mode, fps in results.items():
            print(f"  {mode}: {fps:.1f} FPS")
        
        # 显示最佳模式
        best_mode = max(results, key=results.get)
        print(f"\n🏆 最佳性能模式: {best_mode} ({results[best_mode]:.1f} FPS)")
    
    def update_status(self):
        """更新状态信息"""
        # 更新数据计数
        data_count = len(self.time_data)
        self.data_count_label.setText(f"数据: {data_count}点")
        
        # 更新FPS
        self.fps_label.setText(f"FPS: {self.fps:.1f}")
        
        # 更新引擎状态
        engine = "PyQtGraph" if self.use_pyqtgraph else "Matplotlib"
        self.engine_status_label.setText(f"引擎: {engine}")


def test_hybrid_visualizer():
    """测试混合可视化器"""
    app = QApplication(sys.argv)
    
    print("🚀 启动 MindEcho PyQtGraph 增强版可视化器")
    print(f"✅ PyQtGraph 可用: {PYQTGRAPH_AVAILABLE}")
    
    # 优先使用PyQtGraph
    visualizer = HybridPitchVisualizer(use_pyqtgraph=PYQTGRAPH_AVAILABLE)
    visualizer.show()
    
    print("\n💡 使用说明:")
    print("  🎵 点击'加载颤音测试'查看细线条效果")
    print("  🌈 点击'测试渐变效果'验证彩色渐变")
    print("  📊 点击'性能测试'对比不同模式")
    print("  🎛️ 切换显示模式体验不同效果")
    print("\n🎯 重点测试:")
    print("  • 彩色渐变模式是否正常显示")
    print("  • 普通模式线条是否够细")
    print("  • 整体性能是否流畅")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    test_hybrid_visualizer()
