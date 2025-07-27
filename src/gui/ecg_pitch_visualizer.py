"""
心电图式音高可视化器
实现极度敏感的实时音高变化显示
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Rectangle
import threading
import time
from collections import deque
from datetime import datetime

try:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    PYQT_VERSION = 6
except ImportError:
    try:
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider
        from PyQt5.QtCore import Qt, QTimer, pyqtSignal
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure
        PYQT_VERSION = 5
    except ImportError:
        print("PyQt6/PyQt5 not available for ECG visualizer")
        PYQT_VERSION = None

class ECGPitchVisualizer(QWidget if PYQT_VERSION else object):
    """心电图式音高可视化器"""
    
    def __init__(self, parent=None):
        if PYQT_VERSION:
            super().__init__(parent)
        
        # 可视化参数
        self.time_window = 10.0  # 显示时间窗口（秒）
        self.update_interval = 50  # 更新间隔（ms）
        self.sensitivity = 1.0  # 敏感度
        
        # 数据存储
        self.max_points = 1000
        self.times = deque(maxlen=self.max_points)
        self.frequencies = deque(maxlen=self.max_points)
        self.notes = deque(maxlen=self.max_points)
        self.confidences = deque(maxlen=self.max_points)
        
        # 音符映射
        self.note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        self.note_colors = {
            'C': '#FF0000', 'C#': '#FF4000', 'D': '#FF8000', 'D#': '#FFBF00',
            'E': '#FFFF00', 'F': '#BFFF00', 'F#': '#80FF00', 'G': '#40FF00',
            'G#': '#00FF00', 'A': '#00FF80', 'A#': '#00FFFF', 'B': '#0080FF'
        }
        
        # 音符到数值的映射 (用于Y轴)
        self.note_to_y = {}
        self.y_to_note = {}
        self._setup_note_mapping()
        
        if PYQT_VERSION:
            self._setup_ui()
            self._setup_plot()
    
    def _setup_note_mapping(self):
        """建立音符到Y坐标的映射"""
        # 建立从C0到C8的音符映射
        y_value = 0
        for octave in range(9):  # 0-8八度
            for note_idx, note in enumerate(self.note_names):
                note_display = f"{note}{octave}"
                self.note_to_y[note_display] = y_value
                self.y_to_note[y_value] = note_display
                y_value += 1
    
    def _setup_ui(self):
        """设置用户界面"""
        layout = QVBoxLayout()
        
        # 控制面板
        control_panel = QHBoxLayout()
        
        # 时间窗口控制
        time_label = QLabel("时间窗口:")
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(5, 30)
        self.time_slider.setValue(int(self.time_window))
        self.time_slider.valueChanged.connect(self._on_time_window_changed)
        self.time_value_label = QLabel(f"{self.time_window:.1f}s")
        
        # 敏感度控制
        sens_label = QLabel("敏感度:")
        self.sens_slider = QSlider(Qt.Orientation.Horizontal)
        self.sens_slider.setRange(1, 10)
        self.sens_slider.setValue(int(self.sensitivity * 5))
        self.sens_slider.valueChanged.connect(self._on_sensitivity_changed)
        self.sens_value_label = QLabel(f"{self.sensitivity:.1f}x")
        
        # 清除按钮
        self.clear_button = QPushButton("清除")
        self.clear_button.clicked.connect(self.clear_data)
        
        control_panel.addWidget(time_label)
        control_panel.addWidget(self.time_slider)
        control_panel.addWidget(self.time_value_label)
        control_panel.addWidget(sens_label)
        control_panel.addWidget(self.sens_slider)
        control_panel.addWidget(self.sens_value_label)
        control_panel.addWidget(self.clear_button)
        control_panel.addStretch()
        
        layout.addLayout(control_panel)
        
        # 添加matplotlib图表
        self.figure = Figure(figsize=(12, 8))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        self.setLayout(layout)
        
        # 设置更新定时器
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_plot)
        self.update_timer.start(self.update_interval)
    
    def _setup_plot(self):
        """设置绘图"""
        self.figure.clear()
        
        # 创建子图
        self.ax1 = self.figure.add_subplot(211)  # 频率曲线
        self.ax2 = self.figure.add_subplot(212)  # 音符显示
        
        # 设置图表样式
        self.figure.patch.set_facecolor('black')
        
        # 频率曲线图
        self.ax1.set_facecolor('black')
        self.ax1.set_title('实时音高检测 (心电图模式)', color='white', fontsize=14)
        self.ax1.set_ylabel('频率 (Hz)', color='white')
        self.ax1.tick_params(colors='white')
        self.ax1.grid(True, alpha=0.3, color='gray')
        
        # 音符显示图
        self.ax2.set_facecolor('black')
        self.ax2.set_xlabel('时间 (秒)', color='white')
        self.ax2.set_ylabel('音符', color='white')
        self.ax2.tick_params(colors='white')
        self.ax2.grid(True, alpha=0.3, color='gray')
        
        # 初始化空曲线
        self.freq_line, = self.ax1.plot([], [], color='#00FF00', linewidth=2, alpha=0.8)
        self.confidence_fill = None
        
        # 音符散点
        self.note_scatter = self.ax2.scatter([], [], c=[], s=[], alpha=0.7)
        
        # 设置Y轴范围
        self.ax1.set_ylim(50, 1000)
        self.ax2.set_ylim(-1, len(self.note_to_y))
        
        # 设置音符Y轴标签
        note_labels = [f"{note}{octave}" for octave in range(2, 7) 
                      for note in ['C', 'D', 'E', 'F', 'G', 'A', 'B']]
        note_positions = [self.note_to_y.get(note, 0) for note in note_labels if note in self.note_to_y]
        self.ax2.set_yticks(note_positions[::6])  # 每隔6个显示一个
        self.ax2.set_yticklabels([note_labels[i] for i in range(0, len(note_labels), 6)])
        
        plt.tight_layout()
        self.canvas.draw()
    
    def _on_time_window_changed(self, value):
        """时间窗口改变"""
        self.time_window = float(value)
        self.time_value_label.setText(f"{self.time_window:.1f}s")
    
    def _on_sensitivity_changed(self, value):
        """敏感度改变"""
        self.sensitivity = value / 5.0
        self.sens_value_label.setText(f"{self.sensitivity:.1f}x")
    
    def add_pitch_data(self, frequency, note_info, confidence, timestamp=None):
        """添加音高数据"""
        if timestamp is None:
            timestamp = time.time()
        
        # 添加数据到队列
        self.times.append(timestamp)
        self.frequencies.append(frequency if frequency > 0 else np.nan)
        self.notes.append(note_info)
        self.confidences.append(confidence)
    
    def update_plot(self):
        """更新图表"""
        if not self.times:
            return
        
        try:
            # 获取当前时间窗口内的数据
            current_time = time.time()
            start_time = current_time - self.time_window
            
            # 过滤数据
            valid_indices = [i for i, t in enumerate(self.times) if t >= start_time]
            
            if not valid_indices:
                return
            
            # 提取数据
            times_array = np.array([self.times[i] - start_time for i in valid_indices])
            freqs_array = np.array([self.frequencies[i] for i in valid_indices])
            notes_array = [self.notes[i] for i in valid_indices]
            confs_array = np.array([self.confidences[i] for i in valid_indices])
            
            # 更新频率曲线
            valid_freq_mask = ~np.isnan(freqs_array)
            if np.any(valid_freq_mask):
                self.freq_line.set_data(times_array[valid_freq_mask], freqs_array[valid_freq_mask])
                
                # 根据敏感度调整Y轴范围
                valid_freqs = freqs_array[valid_freq_mask]
                if len(valid_freqs) > 0:
                    freq_min, freq_max = np.min(valid_freqs), np.max(valid_freqs)
                    margin = (freq_max - freq_min) * 0.1 * self.sensitivity
                    if margin < 10:
                        margin = 50
                    self.ax1.set_ylim(max(50, freq_min - margin), min(2000, freq_max + margin))
            
            # 更新音符散点
            note_times = []
            note_y_values = []
            note_colors = []
            note_sizes = []
            
            for i, note_info in enumerate(notes_array):
                if note_info and 'note_display' in note_info:
                    note_display = note_info['note_display']
                    if note_display in self.note_to_y:
                        note_times.append(times_array[i])
                        note_y_values.append(self.note_to_y[note_display])
                        
                        # 根据音符设置颜色
                        note_name = note_info['note']
                        color = self.note_colors.get(note_name, '#FFFFFF')
                        note_colors.append(color)
                        
                        # 根据置信度设置大小
                        size = max(20, confs_array[i] * 100 * self.sensitivity)
                        note_sizes.append(size)
            
            if note_times:
                # 清除旧的散点图
                self.ax2.clear()
                self.ax2.set_facecolor('black')
                self.ax2.set_xlabel('时间 (秒)', color='white')
                self.ax2.set_ylabel('音符', color='white')
                self.ax2.tick_params(colors='white')
                self.ax2.grid(True, alpha=0.3, color='gray')
                
                # 绘制新的散点图
                self.ax2.scatter(note_times, note_y_values, c=note_colors, s=note_sizes, alpha=0.7)
                
                # 重新设置音符标签
                note_labels = [f"{note}{octave}" for octave in range(2, 7) 
                              for note in ['C', 'D', 'E', 'F', 'G', 'A', 'B']]
                note_positions = [self.note_to_y.get(note, 0) for note in note_labels if note in self.note_to_y]
                self.ax2.set_yticks(note_positions[::6])
                self.ax2.set_yticklabels([note_labels[i] for i in range(0, len(note_labels), 6)])
            
            # 设置X轴范围
            self.ax1.set_xlim(0, self.time_window)
            self.ax2.set_xlim(0, self.time_window)
            
            # 重绘
            self.canvas.draw_idle()
            
        except Exception as e:
            print(f"绘图更新错误: {e}")
    
    def clear_data(self):
        """清除数据"""
        self.times.clear()
        self.frequencies.clear()
        self.notes.clear()
        self.confidences.clear()
        
        # 清除图表
        self.ax1.clear()
        self.ax2.clear()
        self._setup_plot()
    
    def set_data_from_analyzer(self, vis_data):
        """从分析器设置数据"""
        if not vis_data:
            return
        
        # 清除旧数据
        self.times.clear()
        self.frequencies.clear()
        self.notes.clear()
        self.confidences.clear()
        
        # 添加新数据
        for i in range(len(vis_data['time_history'])):
            self.times.append(vis_data['time_history'][i])
            self.frequencies.append(vis_data['pitch_history'][i])
            self.notes.append(vis_data['note_history'][i])
            self.confidences.append(vis_data['confidence_history'][i])

# 非GUI版本的可视化器
class SimpleECGVisualizer:
    """简单的心电图可视化器（无GUI依赖）"""
    
    def __init__(self):
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(12, 8))
        self.fig.patch.set_facecolor('black')
        
        # 设置图表样式
        for ax in [self.ax1, self.ax2]:
            ax.set_facecolor('black')
            ax.tick_params(colors='white')
            ax.grid(True, alpha=0.3, color='gray')
        
        self.ax1.set_title('实时音高检测 (心电图模式)', color='white', fontsize=14)
        self.ax1.set_ylabel('频率 (Hz)', color='white')
        self.ax2.set_xlabel('时间 (秒)', color='white')
        self.ax2.set_ylabel('音符', color='white')
        
        plt.ion()  # 交互模式
        plt.tight_layout()
    
    def update_plot(self, times, frequencies, notes, confidences):
        """更新图表"""
        self.ax1.clear()
        self.ax2.clear()
        
        # 重新设置样式
        for ax in [self.ax1, self.ax2]:
            ax.set_facecolor('black')
            ax.tick_params(colors='white')
            ax.grid(True, alpha=0.3, color='gray')
        
        # 绘制频率曲线
        valid_mask = np.array(frequencies) > 0
        if np.any(valid_mask):
            valid_times = np.array(times)[valid_mask]
            valid_freqs = np.array(frequencies)[valid_mask]
            self.ax1.plot(valid_times, valid_freqs, color='#00FF00', linewidth=2)
        
        self.ax1.set_title('实时音高检测 (心电图模式)', color='white', fontsize=14)
        self.ax1.set_ylabel('频率 (Hz)', color='white')
        
        # 绘制音符
        # 这里可以添加音符可视化逻辑
        
        self.ax2.set_xlabel('时间 (秒)', color='white')
        self.ax2.set_ylabel('音符', color='white')
        
        plt.draw()
        plt.pause(0.01)
