"""
实时音域可视化组件
支持A0到C8完整音域显示和音高波动可视化
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as patches
from collections import deque
import time

try:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel
    from PyQt6.QtCore import Qt, QTimer
    PYQT_AVAILABLE = True
except ImportError:
    try:
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel
        from PyQt5.QtCore import Qt, QTimer
        PYQT_AVAILABLE = True
    except ImportError:
        PYQT_AVAILABLE = False

class FullRangePitchVisualizer(QWidget):
    """完整音域音高可视化器"""
    
    def __init__(self):
        super().__init__()
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 音域定义
        self.setup_note_frequencies()
        
        # 音高历史数据
        self.pitch_history = deque(maxlen=500)  # 保存500个点
        self.time_history = deque(maxlen=500)
        self.confidence_history = deque(maxlen=500)
        
        # 显示参数
        self.time_window = 10.0  # 显示最近10秒
        self.update_interval = 50  # 50ms更新一次
        
        # 初始化UI
        self.init_ui()
        
        # 更新定时器
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(self.update_interval)
    
    def setup_note_frequencies(self):
        """设置音符频率映射"""
        # A0到C8的所有音符
        self.note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        # 计算所有音符的频率
        self.note_frequencies = {}
        self.frequency_to_note = {}
        
        # A4 = 440Hz 作为参考
        A4_freq = 440.0
        A4_midi = 69  # A4 的 MIDI 音符号
        
        # 计算从C0到C8的所有音符频率
        for midi_number in range(12, 109):  # C0 到 C8
            octave = (midi_number - 12) // 12
            note_index = (midi_number - 12) % 12
            note_name = self.note_names[note_index]
            
            # 计算频率
            frequency = A4_freq * (2 ** ((midi_number - A4_midi) / 12))
            
            full_note_name = f"{note_name}{octave}"
            self.note_frequencies[full_note_name] = frequency
            self.frequency_to_note[frequency] = full_note_name
        
        # 创建频率数组用于绘图
        self.all_frequencies = sorted(self.note_frequencies.values())
        self.all_note_names = [self.frequency_to_note[freq] for freq in self.all_frequencies]
        
        # 主要音符（C音符）用于标记
        self.major_notes = [name for name in self.all_note_names if name.startswith('C')]
        self.major_frequencies = [self.note_frequencies[name] for name in self.major_notes]
    
    def init_ui(self):
        """初始化用户界面"""
        layout = QVBoxLayout(self)
        
        # 控制面板
        controls_layout = QHBoxLayout()
        
        # 时间窗口控制
        time_label = QLabel("时间窗口:")
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setMinimum(5)
        self.time_slider.setMaximum(30)
        self.time_slider.setValue(int(self.time_window))
        self.time_slider.valueChanged.connect(self.on_time_window_changed)
        self.time_value_label = QLabel(f"{self.time_window:.1f}s")
        
        controls_layout.addWidget(time_label)
        controls_layout.addWidget(self.time_slider)
        controls_layout.addWidget(self.time_value_label)
        controls_layout.addStretch()
        
        layout.addLayout(controls_layout)
        
        # 创建matplotlib图形
        self.figure = Figure(figsize=(12, 8), facecolor='white')
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        # 创建子图
        self.setup_plots()
    
    def setup_plots(self):
        """设置绘图区域"""
        self.figure.clear()
        
        # 创建两个子图：实时波形和音域图谱
        self.ax_waveform = self.figure.add_subplot(211)
        self.ax_spectrum = self.figure.add_subplot(212)
        
        # 设置实时波形图
        self.ax_waveform.set_title('实时音高波动', fontsize=14, fontweight='bold')
        self.ax_waveform.set_ylabel('频率 (Hz)')
        self.ax_waveform.grid(True, alpha=0.3)
        self.ax_waveform.set_ylim(self.all_frequencies[0] * 0.8, self.all_frequencies[-1] * 1.2)
        
        # 设置音域图谱
        self.ax_spectrum.set_title('完整音域图谱 (A0 - C8)', fontsize=14, fontweight='bold')
        self.ax_spectrum.set_xlabel('时间 (秒)')
        self.ax_spectrum.set_ylabel('音符')
        
        # 在音域图上绘制音符线
        self.setup_note_lines()
        
        # 调整布局
        self.figure.tight_layout()
        self.canvas.draw()
    
    def setup_note_lines(self):
        """在音域图上设置音符参考线"""
        # 清除现有内容
        self.ax_spectrum.clear()
        
        # 设置Y轴为音符
        note_positions = range(len(self.all_note_names))
        self.ax_spectrum.set_yticks(note_positions[::12])  # 每八度显示一个标记
        self.ax_spectrum.set_yticklabels([self.all_note_names[i] for i in range(0, len(self.all_note_names), 12)])
        
        # 绘制主要音符的参考线
        for i, note_name in enumerate(self.all_note_names):
            if note_name.startswith('C'):
                self.ax_spectrum.axhline(y=i, color='lightgray', linestyle='-', alpha=0.5)
            elif note_name.endswith('#'):
                continue  # 黑键不画线
            else:
                self.ax_spectrum.axhline(y=i, color='lightgray', linestyle=':', alpha=0.3)
        
        # 设置网格
        self.ax_spectrum.grid(True, alpha=0.3)
        self.ax_spectrum.set_ylim(-1, len(self.all_note_names))
    
    def add_pitch_data(self, frequency, confidence=1.0, timestamp=None):
        """添加音高数据"""
        if timestamp is None:
            timestamp = time.time()
        
        self.pitch_history.append(frequency)
        self.time_history.append(timestamp)
        self.confidence_history.append(confidence)
    
    def update_display(self):
        """更新显示"""
        if len(self.pitch_history) == 0:
            return
        
        try:
            current_time = time.time()
            
            # 过滤时间窗口内的数据
            valid_indices = []
            times = list(self.time_history)
            pitches = list(self.pitch_history)
            confidences = list(self.confidence_history)
            
            for i, t in enumerate(times):
                if current_time - t <= self.time_window:
                    valid_indices.append(i)
            
            if not valid_indices:
                return
            
            # 提取有效数据
            valid_times = [times[i] - min(times[valid_indices[0]:]) for i in valid_indices]
            valid_pitches = [pitches[i] for i in valid_indices if pitches[i] > 0]
            valid_confidences = [confidences[i] for i in valid_indices if pitches[i] > 0]
            valid_times_filtered = [valid_times[i] for i in range(len(valid_indices)) if pitches[valid_indices[i]] > 0]
            
            if not valid_pitches:
                return
            
            # 更新实时波形图
            self.update_waveform_plot(valid_times_filtered, valid_pitches, valid_confidences)
            
            # 更新音域图谱
            self.update_spectrum_plot(valid_times_filtered, valid_pitches, valid_confidences)
            
            # 刷新画布
            self.canvas.draw()
            
        except Exception as e:
            print(f"显示更新错误: {e}")
    
    def update_waveform_plot(self, times, pitches, confidences):
        """更新实时波形图"""
        self.ax_waveform.clear()
        
        # 设置标题和标签
        self.ax_waveform.set_title('实时音高波动', fontsize=14, fontweight='bold')
        self.ax_waveform.set_ylabel('频率 (Hz)')
        self.ax_waveform.grid(True, alpha=0.3)
        
        if len(pitches) > 1:
            # 根据置信度设置颜色
            colors = plt.cm.viridis(np.array(confidences))
            
            # 绘制音高曲线
            self.ax_waveform.plot(times, pitches, 'o-', linewidth=2, markersize=3, alpha=0.8)
            
            # 添加置信度颜色映射
            scatter = self.ax_waveform.scatter(times, pitches, c=confidences, 
                                             cmap='viridis', s=20, alpha=0.7)
            
            # 设置Y轴范围
            if pitches:
                margin = (max(pitches) - min(pitches)) * 0.1
                self.ax_waveform.set_ylim(min(pitches) - margin, max(pitches) + margin)
            
            # 添加主要音符参考线
            for freq in self.major_frequencies:
                if self.ax_waveform.get_ylim()[0] <= freq <= self.ax_waveform.get_ylim()[1]:
                    self.ax_waveform.axhline(y=freq, color='red', linestyle='--', alpha=0.3)
        
        # 设置X轴
        self.ax_waveform.set_xlim(0, self.time_window)
    
    def update_spectrum_plot(self, times, pitches, confidences):
        """更新音域图谱"""
        self.setup_note_lines()
        
        if len(pitches) > 1:
            # 将频率转换为音符位置
            note_positions = []
            for freq in pitches:
                # 找到最接近的音符
                closest_note_idx = np.argmin([abs(f - freq) for f in self.all_frequencies])
                note_positions.append(closest_note_idx)
            
            # 根据置信度设置颜色和大小
            colors = plt.cm.plasma(np.array(confidences))
            sizes = np.array(confidences) * 50 + 10
            
            # 绘制音高点
            scatter = self.ax_spectrum.scatter(times, note_positions, 
                                             c=confidences, s=sizes,
                                             cmap='plasma', alpha=0.7, edgecolors='white')
            
            # 连接相邻的点
            if len(note_positions) > 1:
                self.ax_spectrum.plot(times, note_positions, '-', 
                                    color='white', linewidth=1, alpha=0.5)
        
        # 设置X轴
        self.ax_spectrum.set_xlim(0, self.time_window)
        self.ax_spectrum.set_xlabel('时间 (秒)')
    
    def on_time_window_changed(self, value):
        """时间窗口改变回调"""
        self.time_window = value
        self.time_value_label.setText(f"{self.time_window:.1f}s")
    
    def clear_data(self):
        """清除数据"""
        self.pitch_history.clear()
        self.time_history.clear()
        self.confidence_history.clear()
        
        # 清除图形
        self.ax_waveform.clear()
        self.ax_spectrum.clear()
        self.setup_plots()
        self.canvas.draw()
    
    def get_current_note_info(self):
        """获取当前音符信息"""
        if not self.pitch_history:
            return None
        
        current_freq = self.pitch_history[-1]
        if current_freq <= 0:
            return None
        
        # 找到最接近的音符
        closest_freq = min(self.all_frequencies, key=lambda f: abs(f - current_freq))
        note_name = self.frequency_to_note[closest_freq]
        
        # 计算偏差
        cents = 1200 * np.log2(current_freq / closest_freq)
        
        return {
            'frequency': current_freq,
            'note_name': note_name,
            'closest_frequency': closest_freq,
            'cents_deviation': cents
        }
