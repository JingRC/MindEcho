"""
MindEcho 集成录音与实时音高分析界面
将录音、音高分析和心电图式可视化集成到一个统一界面
"""

import sys
import os
import time
import threading
import numpy as np
from pathlib import Path
from collections import deque
import sounddevice as sd
import wave
import json

# 添加项目根目录到路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

# PyQt导入
try:
    from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                 QPushButton, QLabel, QSlider, QComboBox,
                                 QGroupBox, QProgressBar, QCheckBox, QSpinBox,
                                 QApplication, QMessageBox, QFrame, QGridLayout,
                                 QScrollBar)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt6.QtGui import QFont, QPalette, QColor
    PYQT_VERSION = 6
except ImportError:
    try:
        from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                     QPushButton, QLabel, QSlider, QComboBox,
                                     QGroupBox, QProgressBar, QCheckBox, QSpinBox,
                                     QApplication, QMessageBox, QFrame)
        from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
        from PyQt5.QtGui import QFont, QPalette, QColor
        PYQT_VERSION = 5
    except ImportError:
        print("PyQt6/PyQt5 未安装")
        exit(1)

# 导入分析模块
try:
    from src.analysis.overlapping_frame_analyzer import OverlappingFrameAnalyzer
    from src.analysis.pitch_detection import PitchDetector
except ImportError as e:
    print(f"导入分析模块失败: {e}")

# 导入PyQtGraph彩色渐变组件
PYQTGRAPH_GRADIENT_AVAILABLE = False
try:
    from src.gui.pyqtgraph_gradient_widget import PyQtGraphColorGradientWidget
    PYQTGRAPH_GRADIENT_AVAILABLE = True
    print("✅ PyQtGraph彩色渐变组件可用")
except ImportError as e:
    print(f"⚠️ PyQtGraph彩色渐变组件不可用: {e}")
    print("将使用Matplotlib备用渐变方案")

# 导入scipy用于线条平滑插值
SCIPY_AVAILABLE = False
try:
    from scipy.interpolate import interp1d
    SCIPY_AVAILABLE = True
    print("✅ SciPy平滑插值可用")
except ImportError:
    print("⚠️ SciPy不可用，使用原始数据点")

# matplotlib导入
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as patches
from matplotlib import font_manager


class IntegratedAudioProcessor(QThread):
    """集成音频处理线程 - 同时处理录音和音高分析"""
    
    # 信号定义
    pitch_detected = pyqtSignal(dict)
    audio_level_updated = pyqtSignal(float)
    recording_progress = pyqtSignal(float)
    status_updated = pyqtSignal(str)
    recording_finished = pyqtSignal(str, dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        
        # 录音参数
        self.sample_rate = 44100
        self.channels = 1
        self.chunk_size = 1024
        
        # 状态控制
        self.is_recording = False
        self.should_save = False
        self.recording_filename = None
        
        # 音频数据存储
        self.audio_buffer = []
        self.audio_stream = None
        
        # 音高分析器
        self.pitch_analyzer = None
        self.overlapping_analyzer = None
        
        # 实时统计
        self.pitch_history = deque(maxlen=1000)  # 保存最近1000个音高点
        self.recording_start_time = None
        self.current_duration = 0
        
    def setup_analyzers(self):
        """设置分析器"""
        try:
            # 重叠帧分析器 - 64fps检测
            self.overlapping_analyzer = OverlappingFrameAnalyzer(
                sample_rate=self.sample_rate,
                frame_size=256,
                overlap=84
            )
            
            # 基础音高检测器
            self.pitch_detector = PitchDetector(
                sample_rate=self.sample_rate,
                frame_size=1024
            )
            
            self.status_updated.emit("分析器初始化完成")
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"分析器初始化失败: {e}")
            return False
    
    def start_recording(self, filename=None, should_save=True):
        """开始录音"""
        try:
            self.recording_filename = filename
            self.should_save = should_save
            self.audio_buffer = []
            self.pitch_history.clear()
            self.recording_start_time = time.time()
            
            # 设置分析器
            if not self.setup_analyzers():
                return False
            
            # 音频回调函数
            def audio_callback(indata, frames, time_info, status):
                if status:
                    print(f"音频状态: {status}")
                
                # 获取单声道数据
                audio_data = indata[:, 0] if self.channels == 1 else indata
                
                # 保存录音数据
                if self.is_recording and self.should_save:
                    self.audio_buffer.extend(audio_data)
                
                # 计算音频电平
                audio_level = np.sqrt(np.mean(audio_data ** 2))
                self.audio_level_updated.emit(float(audio_level))
                
                # 实时音高分析
                if self.is_recording:
                    self.process_audio_for_pitch(audio_data)
                
                # 更新录音进度
                if self.recording_start_time:
                    self.current_duration = time.time() - self.recording_start_time
                    self.recording_progress.emit(self.current_duration)
            
            # 启动音频流
            self.audio_stream = sd.InputStream(
                callback=audio_callback,
                samplerate=self.sample_rate,
                channels=self.channels,
                blocksize=self.chunk_size,
                dtype=np.float32
            )
            
            self.audio_stream.start()
            self.is_recording = True
            
            start_msg = "开始录音和实时分析" if should_save else "开始实时分析（不保存）"
            self.status_updated.emit(start_msg)
            
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"启动录音失败: {e}")
            return False
    
    def process_audio_for_pitch(self, audio_data):
        """处理音频进行音高分析"""
        try:
            current_time = time.time()
            
            # 简化处理：直接使用简单音高检测，避免复杂的重叠帧分析
            if len(audio_data) >= 512:  # 确保有足够的数据
                frequency = self.simple_pitch_detection(audio_data)
                if frequency > 50:  # 过滤噪声
                    note_info = self.frequency_to_note_info(frequency)
                    
                    pitch_data = {
                        'timestamp': current_time,
                        'frequency': frequency,
                        'confidence': 0.8,  # 默认置信度
                        'note_info': note_info
                    }
                    
                    self.pitch_history.append(pitch_data)
                    self.pitch_detected.emit(pitch_data)
                        
        except Exception as e:
            print(f"音高分析错误: {e}")
    
    def simple_pitch_detection(self, audio_data):
        """简单的音高检测（使用自相关方法）"""
        try:
            # 确保数据长度合适
            if len(audio_data) < 512:
                return 0
            
            # 限制数据长度以提高性能
            if len(audio_data) > 2048:
                audio_data = audio_data[:2048]
            
            # 应用窗函数
            windowed = audio_data * np.hanning(len(audio_data))
            
            # 自相关方法检测音高
            correlation = np.correlate(windowed, windowed, mode='full')
            correlation = correlation[len(correlation)//2:]
            
            # 找到第一个峰值后的最大峰值
            # 忽略前面的低频部分
            min_period = int(self.sample_rate / 800)  # 最高800Hz
            max_period = int(self.sample_rate / 80)   # 最低80Hz
            
            if max_period < len(correlation):
                search_range = correlation[min_period:max_period]
                if len(search_range) > 0:
                    peak_index = np.argmax(search_range) + min_period
                    frequency = self.sample_rate / peak_index
                    
                    # 验证频率范围
                    if 80 <= frequency <= 800:
                        return frequency
            
            return 0
                
        except Exception as e:
            print(f"简单音高检测错误: {e}")
            return 0
    
    def frequency_to_note_info(self, frequency):
        """将频率转换为音符信息"""
        if frequency <= 0:
            return {}
        
        # 基准音A4 = 440Hz
        A4 = 440.0
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        # 计算相对于A4的半音数
        semitones_from_A4 = 12 * np.log2(frequency / A4)
        
        # 计算音符索引和八度
        note_index = (9 + round(semitones_from_A4)) % 12
        octave = 4 + (9 + round(semitones_from_A4)) // 12
        
        # 计算偏差（分）
        closest_freq = A4 * (2 ** ((note_index - 9 + (octave - 4) * 12) / 12))
        cents = 1200 * np.log2(frequency / closest_freq)
        
        return {
            'note_name': notes[note_index],
            'octave': octave,
            'cents': cents,
            'midi_number': 69 + (note_index - 9) + (octave - 4) * 12
        }
    
    def stop_recording(self):
        """停止录音"""
        try:
            self.is_recording = False
            
            if self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
                self.audio_stream = None
            
            # 保存录音文件
            output_file = None
            if self.should_save and self.audio_buffer and self.recording_filename:
                output_file = self.save_recording()
            
            # 准备分析结果
            analysis_results = {
                'total_pitches': len(self.pitch_history),
                'recording_duration': self.current_duration,
                'pitches': [p['frequency'] for p in self.pitch_history],
                'timestamps': [p['timestamp'] for p in self.pitch_history],
                'confidences': [p['confidence'] for p in self.pitch_history],
                'note_sequence': [p['note_info'] for p in self.pitch_history]
            }
            
            self.recording_finished.emit(output_file or "", analysis_results)
            self.status_updated.emit("录音和分析完成")
            
        except Exception as e:
            self.error_occurred.emit(f"停止录音失败: {e}")
    
    def save_recording(self):
        """保存录音文件"""
        try:
            # 确保录音目录存在
            recordings_dir = project_root / "recordings"
            recordings_dir.mkdir(exist_ok=True)
            
            # 生成文件路径
            if not self.recording_filename.endswith('.wav'):
                self.recording_filename += '.wav'
            
            output_path = recordings_dir / self.recording_filename
            
            # 保存WAV文件
            audio_array = np.array(self.audio_buffer, dtype=np.float32)
            
            with wave.open(str(output_path), 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(2)  # 16位
                wav_file.setframerate(self.sample_rate)
                
                # 转换为16位整数
                audio_int16 = (audio_array * 32767).astype(np.int16)
                wav_file.writeframes(audio_int16.tobytes())
            
            # 保存分析结果
            analysis_path = output_path.with_suffix('.json')
            analysis_data = {
                'recording_info': {
                    'filename': self.recording_filename,
                    'sample_rate': self.sample_rate,
                    'channels': self.channels,
                    'duration': self.current_duration,
                    'total_samples': len(self.audio_buffer)
                },
                'pitch_analysis': {
                    'total_detections': len(self.pitch_history),
                    'detection_rate': len(self.pitch_history) / max(self.current_duration, 1),
                    'pitch_data': list(self.pitch_history)
                }
            }
            
            with open(analysis_path, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, indent=2, ensure_ascii=False)
            
            return str(output_path)
            
        except Exception as e:
            self.error_occurred.emit(f"保存录音失败: {e}")
            return None


class ECGStylePitchVisualizer(QWidget):
    """心电图式音高可视化器（支持交互拖拽）"""
    
    def __init__(self):
        super().__init__()
        
        # 可视化参数
        self.time_window = 16.0  # 显示时间窗口（秒）- 修改为16秒
        self.max_points = 1024   # 最大显示点数 (64fps * 16秒)
        self.update_interval = 15  # 更新间隔（ms）- 约67fps刷新
        
        # 交互参数
        self.y_view_center = 4.0  # 音高视图中心（C4）
        self.y_view_range = 3.0   # 音高视图范围（±3个八度）
        self.time_offset = 0.0    # 时间偏移量（用于查看历史数据）
        self.max_history_time = 300.0  # 最大历史时间（300秒，5分钟）
        
        # 横轴滚动控制参数
        self.center_display_time = 8.0  # 音调曲线在屏幕中央生成的时间点（8秒）
        self.auto_scroll_enabled = True  # 自动滚动功能开关
        
        # 智能缩放参数
        self.zoom_level = 1.0     # 缩放级别（0.1到5.0）
        self.auto_scale = True    # 自动调整标注密度
        self.auto_follow = True   # 自动跟随最新音高区域
        
        # 拖拽状态
        self.dragging = False
        self.drag_start_pos = None
        self.drag_start_y_center = None
        self.drag_start_time_offset = None
        
        # 数据存储（扩展为历史数据，支持更长时间录制）
        # 使用更大的缓冲区：64fps * 300秒 = 19200个数据点
        max_data_points = int(64 * self.max_history_time)
        print(f"📊 初始化数据缓冲区: {max_data_points} 个数据点 ({self.max_history_time}秒)")
        
        self.pitch_data = deque(maxlen=max_data_points)
        self.time_data = deque(maxlen=max_data_points)
        self.confidence_data = deque(maxlen=max_data_points)  
        self.note_data = deque(maxlen=max_data_points)
        
        # 用于美观渐变线条的存储
        self.gradient_lines = []
        self.highlight_point = None
        
        # 颜色配置
        self.setup_colors()
        
        # 音高范围映射
        self.setup_pitch_mapping()
        
        # 初始化UI
        self.init_ui()
        
        # 更新定时器
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(self.update_interval)
    
    def setup_colors(self):
        """设置颜色配置"""
        # 心电图式颜色配置
        self.bg_color = '#000000'  # 黑色背景
        self.grid_color = '#003300'  # 深绿色网格
        self.line_color = '#00FF00'  # 亮绿色波形
        self.text_color = '#FFFFFF'  # 白色文字
        
        # 音高区域颜色（渐变色）
        self.pitch_colors = {
            'low': '#0066FF',      # 低音 - 蓝色
            'mid_low': '#00CCFF',  # 中低音 - 青色
            'mid': '#00FF00',      # 中音 - 绿色
            'mid_high': '#AADD00', # 中高音 - 柔和黄绿色（降低黄色强度）
            'high': '#FF6600',     # 高音 - 橙色
            'very_high': '#FF0000' # 超高音 - 红色
        }
        
        # 线条粗细设置
        self.current_linewidth = 0.6  # 默认线条粗细（心电图模式推荐极细）
    
    def setup_pitch_mapping(self):
        """设置音高映射（详细音名显示）"""
        # 完整十二平均律音名
        self.note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        self.note_names_flat = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
        
        # 生成完整音域的频率映射（C0到C8）
        self.pitch_frequencies = {}
        self.frequency_to_y = {}
        self.y_to_note = {}
        
        for octave in range(0, 9):  # C0 到 C8
            for i, note in enumerate(self.note_names):
                # 计算MIDI音符号（C4 = 60）
                midi_number = octave * 12 + i + 12  # C0 = 12
                frequency = 440 * (2 ** ((midi_number - 69) / 12))  # A4 = 440Hz
                
                note_full = f"{note}{octave}"
                self.pitch_frequencies[note_full] = frequency
                
                # Y轴位置映射（精确到半音）
                y_pos = octave + i / 12
                self.frequency_to_y[frequency] = y_pos
                self.y_to_note[y_pos] = note_full
        
        # 设置Y轴范围（可调节）
        self.y_min = 0   # C0
        self.y_max = 8   # C8
    
    def init_ui(self):
        """初始化用户界面（带滚动条）"""
        layout = QVBoxLayout(self)
        
        # 控制面板
        controls = self.create_controls()
        layout.addWidget(controls)
        
        # 创建带滚动条的图形区域
        self.create_plot_with_scrollbars()
        layout.addWidget(self.plot_container)
        
        # 设置样式
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {self.bg_color};
                color: {self.text_color};
            }}
            QGroupBox {{
                border: 1px solid #444444;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }}
            QScrollBar {{
                background-color: #222222;
                border: 1px solid #444444;
            }}
            QScrollBar::handle {{
                background-color: #555555;
                border-radius: 3px;
            }}
            QScrollBar::handle:hover {{
                background-color: #666666;
            }}
            QScrollBar:vertical {{
                width: 16px;
            }}
            QScrollBar:horizontal {{
                height: 16px;
            }}
        """)
    
    def create_controls(self):
        """创建控制面板"""
        controls_group = QGroupBox("控制面板")
        main_controls_layout = QVBoxLayout(controls_group)
        
        # 第一行：主要控制按钮（时间窗口、敏感度、显示模式、缩放控制、功能按钮）
        controls_row1_layout = QHBoxLayout()
        
        # 时间窗口控制
        controls_row1_layout.addWidget(QLabel("时间窗口:"))
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(8, int(self.max_history_time))  # 5秒到最大历史时间
        self.time_slider.setValue(int(self.time_window))
        self.time_slider.valueChanged.connect(self.on_time_window_changed)
        controls_row1_layout.addWidget(self.time_slider)
        
        self.time_label = QLabel(f"{self.time_window:.1f}s")
        controls_row1_layout.addWidget(self.time_label)
        
        # 添加横轴最大长度控制按钮
        controls_row1_layout.addWidget(QLabel(" | 最大长度:"))
        
        # 预设按钮
        preset_100_btn = QPushButton("100s")
        preset_100_btn.clicked.connect(lambda: self.set_max_history_time(100))
        preset_100_btn.setStyleSheet("""
            QPushButton {
                background-color: #2E2E2E;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 10px;
                min-width: 30px;
            }
            QPushButton:hover {
                background-color: #3E3E3E;
            }
        """)
        controls_row1_layout.addWidget(preset_100_btn)
        
        preset_200_btn = QPushButton("200s")
        preset_200_btn.clicked.connect(lambda: self.set_max_history_time(200))
        preset_200_btn.setStyleSheet("""
            QPushButton {
                background-color: #2E2E2E;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 10px;
                min-width: 30px;
            }
            QPushButton:hover {
                background-color: #3E3E3E;
            }
        """)
        controls_row1_layout.addWidget(preset_200_btn)
        
        preset_300_btn = QPushButton("300s")
        preset_300_btn.clicked.connect(lambda: self.set_max_history_time(300))
        preset_300_btn.setStyleSheet("""
            QPushButton {
                background-color: #2E2E2E;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 10px;
                min-width: 30px;
            }
            QPushButton:hover {
                background-color: #3E3E3E;
            }
        """)
        controls_row1_layout.addWidget(preset_300_btn)
        
        # 自定义输入按钮
        custom_btn = QPushButton("自定义")
        custom_btn.clicked.connect(self.set_custom_max_history_time)
        custom_btn.setStyleSheet("""
            QPushButton {
                background-color: #2E2E2E;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 10px;
                min-width: 40px;
            }
            QPushButton:hover {
                background-color: #3E3E3E;
            }
        """)
        controls_row1_layout.addWidget(custom_btn)
        
        # 敏感度控制
        controls_row1_layout.addWidget(QLabel("敏感度:"))
        self.sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity_slider.setRange(1, 20)
        self.sensitivity_slider.setValue(10)
        self.sensitivity_slider.valueChanged.connect(self.on_sensitivity_changed)
        controls_row1_layout.addWidget(self.sensitivity_slider)
        
        self.sensitivity_label = QLabel("1.0x")
        controls_row1_layout.addWidget(self.sensitivity_label)
        
        # 显示模式
        controls_row1_layout.addWidget(QLabel("显示模式:"))
        self.display_mode = QComboBox()
        self.display_mode.addItems([
            "心电图模式", 
            "彩色渐变"
        ])
        self.display_mode.currentTextChanged.connect(self.on_display_mode_changed)
        controls_row1_layout.addWidget(self.display_mode)
        
        
        # 智能缩放控制（简化版）
        zoom_group = QGroupBox("缩放控制")
        zoom_layout = QHBoxLayout()
        
        # 缩放滑块
        zoom_layout.addWidget(QLabel("缩放:"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(1, 50)  # 0.1x到5.0x
        self.zoom_slider.setValue(10)  # 默认1.0x
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        zoom_layout.addWidget(self.zoom_slider)
        
        self.zoom_label = QLabel("1.0x")
        zoom_layout.addWidget(self.zoom_label)
        
        # 快速预设按钮（紧凑版）
        zoom_presets = [
            (0.5, "0.5x"),
            (0.8, "0.8x"),
            (1.5, "1.5x"),
            (2.5, "2.5x"),
            (5.0, "5.0x")
        ]
        
        self.preset_buttons = []
        for zoom_level, name in zoom_presets:
            btn = QPushButton(name)
            btn.setToolTip(f"{zoom_level}x 缩放")
            btn.clicked.connect(lambda checked, level=zoom_level: self.set_zoom_preset(level))
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2E2E2E;
                    border: 1px solid #505050;
                    border-radius: 3px;
                    padding: 3px 6px;
                    color: white;
                    font-size: 9px;
                    min-width: 30px;
                    max-width: 35px;
                }
                QPushButton:hover {
                    background-color: #404040;
                    border: 1px solid #707070;
                }
                QPushButton:pressed {
                    background-color: #1A5A1A;
                    border: 1px solid #2A7A2A;
                }
            """)
            zoom_layout.addWidget(btn)
            self.preset_buttons.append(btn)
        
        zoom_group.setLayout(zoom_layout)
        controls_row1_layout.addWidget(zoom_group)
        
        # 功能按钮组
        controls_row1_layout.addWidget(QLabel("|"))  # 分隔符
        
        # 自动标注按钮
        self.auto_scale_btn = QPushButton("智能标注")
        self.auto_scale_btn.setCheckable(True)
        self.auto_scale_btn.setChecked(True)
        self.auto_scale_btn.clicked.connect(self.on_auto_scale_toggled)
        self.auto_scale_btn.setStyleSheet("""
            QPushButton {
                background-color: #006600;
                border: 1px solid #008800;
                border-radius: 3px;
                padding: 5px 8px;
                color: white;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #008800;
            }
            QPushButton:checked {
                background-color: #00AA00;
                border: 1px solid #00CC00;
            }
        """)
        controls_row1_layout.addWidget(self.auto_scale_btn)
        
        # 清除按钮
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.clear_data)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #444444;
                border: 1px solid #666666;
                border-radius: 3px;
                padding: 5px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #555555;
            }
        """)
        controls_row1_layout.addWidget(clear_btn)
        
        # 重置视图按钮
        reset_view_btn = QPushButton("重置")
        reset_view_btn.clicked.connect(self.reset_view)
        reset_view_btn.setStyleSheet("""
            QPushButton {
                background-color: #006600;
                border: 1px solid #008800;
                border-radius: 3px;
                padding: 5px 8px;
                color: white;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #008800;
            }
        """)
        controls_row1_layout.addWidget(reset_view_btn)
        
        # 自动跟随按钮
        self.auto_follow_btn = QPushButton("跟随")
        self.auto_follow_btn.setCheckable(True)
        self.auto_follow_btn.setChecked(True)  # 默认开启
        self.auto_follow_btn.clicked.connect(self.on_auto_follow_toggled)
        self.auto_follow_btn.setStyleSheet("""
            QPushButton {
                background-color: #006600;
                border: 1px solid #008800;
                border-radius: 3px;
                padding: 5px 8px;
                color: white;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #008800;
            }
            QPushButton:checked {
                background-color: #00AA00;
                border: 1px solid #00CC00;
            }
        """)
        controls_row1_layout.addWidget(self.auto_follow_btn)
        
        # 第一行布局添加到主布局
        main_controls_layout.addLayout(controls_row1_layout)
        
        # 第二行：线条粗细控制 + 状态信息显示
        controls_row2_layout = QHBoxLayout()
        
        # 线条粗细控制
        controls_row2_layout.addWidget(QLabel("线条粗细:"))
        self.linewidth_combo = QComboBox()
        self.linewidth_combo.setEditable(False)
        self.linewidth_combo.addItems([
            "0.5px 极细",
            "0.6px 超细",
            "0.8px 细线",
            "1.0px 标准",
            "1.5px 中等",
            "2.0px 粗线",
            "2.5px 很粗",
            "3.0px 极粗",
            "自定义..."
        ])
        self.linewidth_combo.setCurrentText("0.6px 超细")  # 默认心电图模式
        self.linewidth_combo.currentTextChanged.connect(self.on_linewidth_preset_changed)
        controls_row2_layout.addWidget(self.linewidth_combo)
        
        # 线条粗细滑块（初始隐藏，选择"自定义..."时显示）
        self.linewidth_slider = QSlider(Qt.Orientation.Horizontal)
        self.linewidth_slider.setRange(1, 50)  # 0.1px到5.0px
        self.linewidth_slider.setValue(6)  # 默认0.6px
        self.linewidth_slider.valueChanged.connect(self.on_linewidth_slider_changed)
        self.linewidth_slider.setVisible(False)  # 初始隐藏
        controls_row2_layout.addWidget(self.linewidth_slider)
        
        self.linewidth_label = QLabel("0.6px")
        self.linewidth_label.setVisible(False)  # 初始隐藏
        controls_row2_layout.addWidget(self.linewidth_label)
        
        # 分隔符
        controls_row2_layout.addWidget(QLabel(" | "))
        
        # 状态信息显示（合并到一行）
        self.status_label = QLabel("中心: C4 | 时间: 实时 | 缩放: 1.0x | 标注: 智能 | 跟随: 开启 | 数据: 0点(0.0%)")
        self.status_label.setStyleSheet("color: #AAAAAA; font-family: monospace; font-size: 11px;")
        controls_row2_layout.addWidget(self.status_label)
        
        # 第二行布局添加到主布局
        main_controls_layout.addLayout(controls_row2_layout)
        
        return controls_group
    
    def create_plot_with_scrollbars(self):
        """创建带滚动条的绘图区域"""
        # 创建主容器
        self.plot_container = QWidget()
        container_layout = QGridLayout(self.plot_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # 创建matplotlib图形
        self.create_ecg_plot()
        
        # 垂直滚动条（右侧）- 控制音高范围
        self.v_scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self.v_scrollbar.setRange(0, 100)  # 0-100的范围
        self.v_scrollbar.setValue(50)  # 默认中间位置（C4附近）
        self.v_scrollbar.valueChanged.connect(self.on_vertical_scroll)
        self.v_scrollbar.setStyleSheet("""
            QScrollBar:vertical {
                background-color: rgba(0, 0, 0, 0.2);
                width: 12px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: rgba(0, 255, 0, 0.3);
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: rgba(0, 255, 0, 0.5);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)
        
        # 水平滚动条（底部）- 控制时间偏移
        self.h_scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self.h_scrollbar.setRange(0, 100)  # 0-100的范围
        self.h_scrollbar.setValue(0)  # 默认最左边（显示最开始的时间）
        self.h_scrollbar.setSingleStep(1)  # 单步移动1%
        self.h_scrollbar.setPageStep(10)   # 页面移动10%
        self.h_scrollbar.valueChanged.connect(self.on_horizontal_scroll)
        self.h_scrollbar.setStyleSheet("""
            QScrollBar:horizontal {
                background-color: rgba(0, 0, 0, 0.2);
                height: 12px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background-color: rgba(0, 255, 0, 0.3);
                border-radius: 6px;
                min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: rgba(0, 255, 0, 0.5);
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
            }
        """)
        
        # 布局安排 - 支持动态切换PyQtGraph和Matplotlib
        self.main_plot_area = self.canvas  # 默认使用matplotlib
        container_layout.addWidget(self.main_plot_area, 0, 0)  # 图形区域
        container_layout.addWidget(self.v_scrollbar, 0, 1)  # 垂直滚动条
        container_layout.addWidget(self.h_scrollbar, 1, 0)  # 水平滚动条
        
        # 右下角填充
        corner = QWidget()
        corner.setFixedSize(12, 12)
        corner.setStyleSheet("background-color: rgba(0, 0, 0, 0.2);")
        container_layout.addWidget(corner, 1, 1)
    
    def switch_display_widget(self, use_pyqtgraph=False):
        """切换显示组件：PyQtGraph vs Matplotlib"""
        if not hasattr(self, 'plot_container') or not hasattr(self, 'main_plot_area'):
            return
        
        container_layout = self.plot_container.layout()
        
        # 移除当前的主显示组件
        container_layout.removeWidget(self.main_plot_area)
        self.main_plot_area.setParent(None)
        
        if use_pyqtgraph and self.pyqtgraph_gradient_widget is not None:
            # 切换到PyQtGraph彩色渐变
            self.main_plot_area = self.pyqtgraph_gradient_widget
            print("🌈 切换到PyQtGraph彩色渐变显示")
        else:
            # 切换到Matplotlib
            self.main_plot_area = self.canvas
            print("📊 切换到Matplotlib显示")
        
        # 重新添加到布局
        container_layout.addWidget(self.main_plot_area, 0, 0)
    
    def setup_chinese_font(self):
        """设置中文字体支持"""
        try:
            # 检查系统中可用的中文字体
            available_fonts = [f.name for f in font_manager.fontManager.ttflist]
            
            # 按优先级排序的中文字体列表
            chinese_fonts = [
                'Microsoft YaHei',      # 微软雅黑
                'SimHei',              # 黑体  
                'Microsoft JhengHei',   # 微软正黑体
                'PingFang SC',         # 苹果系统字体
                'Hiragino Sans GB',    # 冬青黑体
                'Source Han Sans CN',   # 思源黑体
                'WenQuanYi Micro Hei', # 文泉驿微米黑
                'Arial Unicode MS',     # Arial Unicode
                'DejaVu Sans'          # 备用字体
            ]
            
            # 找到第一个可用的中文字体
            selected_font = None
            for font in chinese_fonts:
                if font in available_fonts:
                    selected_font = font
                    break
            
            if selected_font:
                plt.rcParams['font.sans-serif'] = [selected_font] + chinese_fonts
                plt.rcParams['axes.unicode_minus'] = False  # 正确显示负号
                print(f"✅ 中文字体配置成功: {selected_font}")
                self.chinese_font_available = True
            else:
                # 没有找到中文字体，使用默认设置
                plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']
                plt.rcParams['axes.unicode_minus'] = False
                print("⚠️ 未找到中文字体，使用默认字体")
                self.chinese_font_available = False
                
        except Exception as e:
            print(f"⚠️ 中文字体配置失败: {e}")
            self.chinese_font_available = False
            # 使用最基本的配置
            try:
                plt.rcParams['font.family'] = 'sans-serif'
                plt.rcParams['axes.unicode_minus'] = False
            except:
                pass
        
        
        # 刷新布局
        self.plot_container.update()
    
    def create_ecg_plot(self):
        """创建心电图式绘图区域（支持交互和PyQtGraph彩色渐变）"""
        # 设置matplotlib参数
        plt.rcParams['figure.facecolor'] = self.bg_color
        plt.rcParams['axes.facecolor'] = self.bg_color
        plt.rcParams['text.color'] = self.text_color
        plt.rcParams['axes.labelcolor'] = self.text_color
        plt.rcParams['xtick.color'] = self.text_color
        plt.rcParams['ytick.color'] = self.text_color
        
        # 设置中文字体支持
        self.setup_chinese_font()
        
        # 显示字体配置状态
        if self.chinese_font_available:
            print("✅ matplotlib中文字体配置成功")
        else:
            print("⚠️ matplotlib中文字体配置失败，可能显示方块字符")
        
        # 创建图形
        self.figure = Figure(figsize=(14, 8), facecolor=self.bg_color)
        self.canvas = FigureCanvas(self.figure)
        
        # 创建坐标轴
        self.ax = self.figure.add_subplot(111, facecolor=self.bg_color)
        
        # 设置心电图式网格
        self.setup_ecg_grid()
        
        # 初始化空的线条
        self.pitch_line, = self.ax.plot([], [], color=self.line_color, 
                                       linewidth=self.current_linewidth, alpha=1.0)
        self.confidence_scatter = self.ax.scatter([], [], c=[], 
                                                s=20, alpha=0.7, cmap='viridis')
        
        # 初始化PyQtGraph彩色渐变组件（如果可用）
        self.pyqtgraph_gradient_widget = None
        if PYQTGRAPH_GRADIENT_AVAILABLE:
            try:
                self.pyqtgraph_gradient_widget = PyQtGraphColorGradientWidget()
                print("✅ PyQtGraph彩色渐变组件初始化成功")
            except Exception as e:
                print(f"⚠️ PyQtGraph彩色渐变组件初始化失败: {e}")
                self.pyqtgraph_gradient_widget = None
        
        # 设置初始坐标轴范围
        self.update_axis_ranges()
        
        # 设置坐标轴标签（支持中文显示）
        try:
            # 创建中文字体属性
            from matplotlib import font_manager
            chinese_font = {'fontsize': 12, 'family': 'sans-serif'}
            title_font = {'fontsize': 14, 'fontweight': 'bold', 'family': 'sans-serif'}
            
            if self.chinese_font_available:
                self.ax.set_xlabel('时间 (秒)', **chinese_font)
                self.ax.set_ylabel('音高', **chinese_font)
                self.ax.set_title('实时音高分析 - 心电图式显示 (可拖拽查看)', **title_font)
                print("🔤 使用中文标签")
            else:
                self.ax.set_xlabel('Time (seconds)', **chinese_font)
                self.ax.set_ylabel('Pitch', **chinese_font)  
                self.ax.set_title('Real-time Pitch Analysis - ECG Style Display', **title_font)
                print("🔤 使用英文标签（中文字体不可用）")
                
        except Exception as e:
            print(f"⚠️ 设置坐标轴标签时出错: {e}")
            # 备用方案：使用英文标签
            self.ax.set_xlabel('Time (seconds)', fontsize=12)
            self.ax.set_ylabel('Pitch', fontsize=12)
            self.ax.set_title('Real-time Pitch Analysis - ECG Style Display', fontsize=14, fontweight='bold')
        
        # 隐藏Y轴的数字刻度，只保留音名标注
        self.ax.set_yticklabels([])
        self.ax.tick_params(axis='y', which='both', left=False, right=False)
        
        # 绑定鼠标事件
        self.canvas.mpl_connect('button_press_event', self.on_mouse_press)
        self.canvas.mpl_connect('button_release_event', self.on_mouse_release)
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        self.canvas.mpl_connect('scroll_event', self.on_mouse_scroll)
        
        # 添加交互说明文本（支持中文字体）
        try:
            hint_font = {'fontsize': 10, 'family': 'sans-serif'}
            if self.chinese_font_available:
                self.ax.text(0.02, 0.98, '交互提示：拖拽查看历史数据，上下拖拽调整音高范围，滚轮缩放', 
                            transform=self.ax.transAxes, 
                            verticalalignment='top', color=self.text_color, alpha=0.7, **hint_font)
            else:
                self.ax.text(0.02, 0.98, 'Interactive: Drag to view history, scroll to zoom', 
                            transform=self.ax.transAxes, 
                            verticalalignment='top', color=self.text_color, alpha=0.7, **hint_font)
        except Exception as e:
            print(f"⚠️ 设置交互提示文本时出错: {e}")
            # 备用英文提示
            self.ax.text(0.02, 0.98, 'Interactive: Drag to view history, scroll to zoom', 
                        transform=self.ax.transAxes, fontsize=10,
                        verticalalignment='top', color=self.text_color, alpha=0.7)
    
    def safe_clear_axis(self):
        """安全地清除轴内容，但保留彩色渐变collections和坐标轴范围"""
        # 保存现有的坐标轴范围
        saved_xlim = self.ax.get_xlim()
        saved_ylim = self.ax.get_ylim()
        
        # 保存现有的彩色渐变effects
        saved_gradient_lines = []
        saved_highlight_point = None
        
        if hasattr(self, 'gradient_lines') and self.gradient_lines:
            # 保存gradient_lines中的collections
            for line in self.gradient_lines:
                if line in self.ax.collections:
                    saved_gradient_lines.append(line)
        
        if hasattr(self, 'highlight_point') and self.highlight_point is not None:
            # 保存高亮点
            saved_highlight_point = self.highlight_point
        
        # 清除轴
        self.ax.clear()
        
        # 恢复坐标轴范围
        self.ax.set_xlim(saved_xlim)
        self.ax.set_ylim(saved_ylim)
        
        # 恢复保存的彩色渐变effects
        if saved_gradient_lines:
            print(f"🔄 恢复 {len(saved_gradient_lines)} 个彩色渐变元素")
            for line in saved_gradient_lines:
                self.ax.add_collection(line)
            self.gradient_lines = saved_gradient_lines
        
        if saved_highlight_point is not None:
            print("🔄 恢复高亮点")
            self.ax.add_collection(saved_highlight_point)
            self.highlight_point = saved_highlight_point

    def setup_ecg_grid(self):
        """设置心电图式网格（智能标注）"""
        # 保存现有的pitch_line数据
        existing_line_data = None
        if hasattr(self, 'pitch_line') and self.pitch_line in self.ax.lines:
            existing_line_data = self.pitch_line.get_data()
        
        # 使用安全清除方法保护彩色渐变
        self.safe_clear_axis()
        
        # 重新设置基本属性
        self.ax.set_facecolor(self.bg_color)
        
        # 隐藏Y轴的数字刻度，只保留音名标注
        self.ax.set_yticklabels([])
        self.ax.tick_params(axis='y', which='both', left=False, right=False)
        
        # 根据当前视图范围设置网格
        y_start = self.y_view_center - self.y_view_range / self.zoom_level
        y_end = self.y_view_center + self.y_view_range / self.zoom_level
        
        # 计算显示范围（八度数）
        display_range = y_end - y_start
        
        # 智能标注密度控制
        if self.auto_scale:
            # 根据缩放级别和显示范围智能调整标注
            if display_range > 6:  # 显示范围大于6个八度，只显示八度线和C音
                self.setup_sparse_grid(y_start, y_end)
            elif display_range > 3:  # 显示范围3-6个八度，显示主要音符
                self.setup_medium_grid(y_start, y_end)
            else:  # 显示范围小于3个八度，显示所有音符
                self.setup_dense_grid(y_start, y_end)
        else:
            # 手动模式，总是显示详细标注
            self.setup_dense_grid(y_start, y_end)
        
        # 时间网格线
        time_start = self.time_offset
        time_end = self.time_offset + self.time_window
        for second in range(int(time_start), int(time_end) + 2):
            if time_start <= second <= time_end:
                self.ax.axvline(x=second, color=self.grid_color, 
                               linestyle='--', linewidth=0.5, alpha=0.5)
        
        # 确保pitch_line存在并恢复数据
        self.pitch_line, = self.ax.plot([], [], color=self.line_color, 
                                       linewidth=self.current_linewidth, alpha=1.0, zorder=10)
        
        # 如果有保存的数据，恢复它
        if existing_line_data is not None and len(existing_line_data[0]) > 0:
            self.pitch_line.set_data(existing_line_data[0], existing_line_data[1])
        
        # 强制设置正确的坐标轴范围（防止ax.clear()重置范围）
        # X轴范围（时间）
        x_min = self.time_offset
        x_max = self.time_offset + self.time_window
        self.ax.set_xlim(x_min, x_max)
        
        # Y轴范围（音高，考虑缩放级别）
        actual_range = self.y_view_range / self.zoom_level
        y_min = self.y_view_center - actual_range
        y_max = self.y_view_center + actual_range
        self.ax.set_ylim(y_min, y_max)
    
    def should_show_note_label(self, octave, semitone, y_pos):
        """基于缩放级别决定是否显示音符标签"""
        # 检查是否在中音区核心范围内（C3-C6）
        is_core_range = 3 <= octave <= 6
        
        # 检查是否是主音（C音，即semitone=0）
        is_main_note = semitone == 0
        
        # 检查是否是关键半音（C、D、E、F、G、A、B，即白键）
        is_white_key = semitone in [0, 2, 4, 5, 7, 9, 11]
        
        # 检查是否是重要音程点（C、F、G，即完全音程）
        is_perfect_interval = semitone in [0, 5, 7]  # C、F、G
        
        # 检查是否是扩展核心范围（C2-C7）
        is_extended_range = 2 <= octave <= 7
        
        # 根据缩放级别决定显示策略
        if self.zoom_level >= 4.5:  # 5.0x 全音区显示 - 改进：显示主要音符避免过密
            # 显示C音和白键，避免黑键造成过密
            return is_main_note or is_white_key
        elif self.zoom_level >= 2.0:  # 2.5x 八度主音显示
            return is_main_note or (is_core_range and is_white_key)
        elif self.zoom_level >= 1.2:  # 1.5x 中音区聚焦 - 重新设计，更稀疏
            # 核心策略：显示更少但更重要的音符，避免重叠
            if is_core_range:
                # 在核心范围内，只显示C、F、G（完全音程）
                return is_perfect_interval
            elif is_extended_range:
                # 在扩展范围内，只显示主音
                return is_main_note
            else:
                # 其他范围，只显示主音
                return is_main_note
        elif self.zoom_level >= 0.7:  # 0.8x 基础八度框架
            return is_main_note  # 仅显示各八度主音
        else:  # 0.5x 中央聚焦
            return is_main_note and is_core_range  # 仅显示C3-C6的主音
    
    def draw_interactive_note_labels(self, y_start, y_end):
        """绘制交互式音调标签（根据当前音高智能高亮显示）"""
        if not hasattr(self, 'current_pitch_y'):
            self.current_pitch_y = 4.0
        if not hasattr(self, 'current_pitch_active'):
            self.current_pitch_active = False
        
        # 固定标签位置在左侧（不随时间偏移移动）
        current_xlim = self.ax.get_xlim()
        x_min = current_xlim[0]  # 当前视图的左边界
        label_x = x_min + (current_xlim[1] - current_xlim[0]) * 0.02  # 固定在视图左侧2%位置
        
        # 当前音高区域（用于高亮计算）
        current_center = self.current_pitch_y if self.current_pitch_active else self.y_view_center
        
        # 智能显示范围：当前视图范围 + 额外缓冲区
        display_start = max(0, y_start - 1)  # 扩展显示范围
        display_end = min(8, y_end + 1)
        
        # 遍历整个显示范围内的音符
        for octave in range(int(display_start), int(display_end) + 1):
            for semitone in range(12):
                y_pos = octave + semitone / 12
                if display_start <= y_pos <= display_end:
                    # 基于缩放级别的智能标签过滤
                    should_show = self.should_show_note_label(octave, semitone, y_pos)
                    if not should_show:
                        continue
                        
                    note_name = self.note_names[semitone]
                    note_full = f"{note_name}{octave}"
                    
                    # 计算与当前音高的距离（用于透明度和高亮）
                    distance = abs(y_pos - current_center)
                    
                    # 分层透明度系统
                    if self.current_pitch_active:
                        # 5.0x缩放时使用与非录音一致的透明度逻辑，避免显示过多标签
                        if self.zoom_level >= 4.5:  # 5.0x全音区显示
                            if semitone == 0:  # C音特殊高亮
                                alpha = 1.0
                                color = '#FFFF88'
                                font_size = 11
                                font_weight = 'bold'
                            elif semitone in [2, 4, 5, 7, 9, 11]:  # 白键
                                alpha = 0.8
                                color = self.text_color
                                font_size = 10
                                font_weight = 'normal'
                            else:  # 黑键
                                alpha = 0.5
                                color = self.text_color
                                font_size = 9
                                font_weight = 'normal'
                            
                            # 添加当前音高的额外高亮（不改变透明度，只改变颜色）
                            if distance <= 0.2:
                                color = '#FFD700'  # 金色高亮
                                font_weight = 'bold'
                            elif distance <= 0.5:
                                color = '#FFC107'  # 橙色
                                font_weight = 'bold'
                            elif distance <= 1.0:
                                color = '#FFEB3B'  # 黄色
                        else:
                            # 其他缩放级别使用原有的距离动态逻辑
                            if distance <= 0.2:  # 非常接近当前音高
                                alpha = 1.0
                                color = '#FFD700'  # 金色高亮
                                font_weight = 'bold'
                            elif distance <= 0.5:  # 临近半音
                                alpha = 0.9
                                color = '#FFC107'  # 橙色
                                font_weight = 'bold'
                            elif distance <= 1.0:  # 临近全音
                                alpha = 0.8
                                color = '#FFEB3B'  # 黄色
                                font_weight = 'normal'
                            elif distance <= 2.0:  # 同八度内
                                alpha = 0.6
                                color = self.text_color
                                font_weight = 'normal'
                            else:  # 远距离
                                alpha = 0.3
                                color = self.text_color
                                font_weight = 'normal'
                            
                            # 其他缩放级别使用距离动态字体
                            if distance <= 0.2:
                                font_size = 12
                            elif distance <= 0.5:
                                font_size = 11
                            elif distance <= 1.0:
                                font_size = 10
                            elif distance <= 2.0:
                                font_size = 9
                            else:
                                font_size = 8
                    else:
                        # 无活跃音高时，使用标准显示
                        if semitone == 0:  # C音特殊高亮
                            alpha = 1.0
                            color = '#FFFF88'
                            font_size = 11
                            font_weight = 'bold'
                        elif semitone in [2, 4, 5, 7, 9, 11]:  # 白键
                            alpha = 0.8
                            color = self.text_color
                            font_size = 10
                            font_weight = 'normal'
                        else:  # 黑键
                            alpha = 0.5
                            color = self.text_color
                            font_size = 9
                            font_weight = 'normal'
                    
                    # 根据显示范围调整透明度（确保边缘渐变）
                    view_distance = min(abs(y_pos - y_start), abs(y_pos - y_end))
                    if view_distance < 0.5:
                        alpha *= (view_distance / 0.5)  # 边缘渐变效果
                    
                    # 只显示在有效透明度范围内的标签
                    if alpha >= 0.2:
                        # 绘制音符标签
                        self.ax.text(label_x, y_pos, note_full, 
                                   fontsize=font_size, ha='right', va='center',
                                   color=color, alpha=alpha, fontweight=font_weight)
                        
                        # 5.0x缩放时不添加额外网格线，避免视觉干扰
                        if self.current_pitch_active and distance <= 1.0 and self.zoom_level < 4.5:
                            line_alpha = alpha * 0.3
                            self.ax.axhline(y=y_pos, color=color, linestyle=':', 
                                          linewidth=0.8, alpha=line_alpha)
    
    def setup_sparse_grid(self, y_start, y_end):
        """稀疏网格模式（只显示八度线）"""
        for octave in range(max(0, int(y_start)), min(9, int(y_end) + 2)):
            y_pos = octave
            if y_start <= y_pos <= y_end:
                # 八度线
                self.ax.axhline(y=y_pos, color=self.grid_color, linestyle='-', 
                               linewidth=2.0, alpha=0.9)
        
        # 使用智能交互式标签
        self.draw_interactive_note_labels(y_start, y_end)
    
    def setup_medium_grid(self, y_start, y_end):
        """中等密度网格（显示主要音符）"""
        for octave in range(max(0, int(y_start)), min(9, int(y_end) + 2)):
            # 八度线
            y_pos = octave
            if y_start <= y_pos <= y_end:
                self.ax.axhline(y=y_pos, color=self.grid_color, linestyle='-', 
                               linewidth=1.5, alpha=0.8)
            
            # 主要音符网格线
            major_notes = [0, 2, 4, 5, 7, 9, 11]  # C, D, E, F, G, A, B
            for semitone in major_notes:
                y_pos = octave + semitone / 12
                if y_start <= y_pos <= y_end and semitone != 0:
                    self.ax.axhline(y=y_pos, color=self.grid_color, 
                                   linestyle=':', linewidth=0.8, alpha=0.6)
        
        # 使用智能交互式标签
        self.draw_interactive_note_labels(y_start, y_end)
    
    def setup_dense_grid(self, y_start, y_end):
        """密集网格模式（显示所有音符）"""
        for octave in range(max(0, int(y_start)), min(9, int(y_end) + 2)):
            # 八度线
            y_pos = octave
            if y_start <= y_pos <= y_end:
                self.ax.axhline(y=y_pos, color=self.grid_color, linestyle='-', 
                               linewidth=1.5, alpha=0.8)
            
            # 所有半音网格线
            for semitone in range(12):
                y_pos = octave + semitone / 12
                if y_start <= y_pos <= y_end and semitone != 0:
                    alpha = 0.6 if semitone in [2, 4, 7, 9, 11] else 0.3
                    self.ax.axhline(y=y_pos, color=self.grid_color, 
                                   linestyle=':', linewidth=0.8, alpha=alpha)
        
        # 使用智能交互式标签
        self.draw_interactive_note_labels(y_start, y_end)
    
    def update_axis_ranges(self):
        """更新坐标轴范围（支持缩放）"""
        # 更新Y轴范围（音高，考虑缩放级别）
        actual_range = self.y_view_range / self.zoom_level
        y_min = self.y_view_center - actual_range
        y_max = self.y_view_center + actual_range
        self.ax.set_ylim(y_min, y_max)
        
        # 更新X轴范围（时间）
        x_min = self.time_offset
        x_max = self.time_offset + self.time_window
        self.ax.set_xlim(x_min, x_max)
        
        # 重新设置网格（无论是否有数据都要设置）
        self.setup_ecg_grid()
        
        # 强制刷新画布以确保时间轴标签正确显示
        self.canvas.draw_idle()
    
    def on_mouse_press(self, event):
        """鼠标按下事件"""
        if event.inaxes != self.ax:
            return
        
        self.dragging = True
        self.drag_start_pos = (event.x, event.y)
        self.drag_start_y_center = self.y_view_center
        self.drag_start_time_offset = self.time_offset
    
    def on_mouse_release(self, event):
        """鼠标释放事件"""
        self.dragging = False
        self.drag_start_pos = None
    
    def on_mouse_move(self, event):
        """鼠标移动事件"""
        if not self.dragging or event.inaxes != self.ax:
            return
        
        if self.drag_start_pos is None:
            return
        
        # 计算移动距离
        dx = event.x - self.drag_start_pos[0]
        dy = event.y - self.drag_start_pos[1]
        
        # 转换为数据坐标
        fig_height = self.figure.get_figheight() * self.figure.dpi
        fig_width = self.figure.get_figwidth() * self.figure.dpi
        
        # 垂直拖拽调整音高范围
        dy_data = -dy / fig_height * (self.y_view_range * 2) * 2  # 负号因为屏幕坐标向下为正
        new_y_center = self.drag_start_y_center + dy_data
        self.y_view_center = max(1.5, min(6.5, new_y_center))  # 限制在合理范围内
        
        # 水平拖拽调整时间偏移
        dx_data = -dx / fig_width * self.time_window * 1.5  # 负号实现反向拖拽
        new_time_offset = self.drag_start_time_offset + dx_data
        self.time_offset = max(0, min(self.max_history_time - self.time_window, new_time_offset))
        
        # 更新显示
        self.update_axis_ranges()
        self.canvas.draw_idle()
        
        # 同步更新滚动条
        self.update_scrollbars()
    
    def on_mouse_scroll(self, event):
        """鼠标滚轮事件（上下移动音高视图）"""
        if event.inaxes != self.ax:
            return
        
        # 滚轮上下移动音高视图中心
        scroll_sensitivity = 0.3  # 滚动敏感度
        if event.step > 0:  # 向上滚动
            delta_y = scroll_sensitivity
        else:  # 向下滚动
            delta_y = -scroll_sensitivity
        
        # 更新音高视图中心
        new_y_center = self.y_view_center + delta_y
        self.y_view_center = max(1.5, min(6.5, new_y_center))  # 限制在合理范围内
        
        # 更新显示
        self.update_axis_ranges()
        self.canvas.draw_idle()
        
        # 同步更新垂直滚动条位置
        if hasattr(self, 'v_scrollbar'):
            # 将y_view_center (1.5-6.5) 映射到滚动条范围 (0-100)
            scroll_value = int((self.y_view_center - 1.5) / 5.0 * 100)
            self.v_scrollbar.blockSignals(True)  # 阻止信号避免循环
            self.v_scrollbar.setValue(100 - scroll_value)  # 反转，顶部对应高音
            self.v_scrollbar.blockSignals(False)
    
    def on_vertical_scroll(self, value):
        """垂直滚动条事件（控制音高视图中心）"""
        # 将滚动条值 (0-100) 映射到音高范围 (1.5-6.5)
        # 滚动条顶部(0)对应高音(6.5)，底部(100)对应低音(1.5)
        normalized_value = (100 - value) / 100.0  # 反转映射
        self.y_view_center = 1.5 + normalized_value * 5.0
        
        # 更新显示
        self.update_axis_ranges()
        self.canvas.draw_idle()
    
    def on_horizontal_scroll(self, value):
        """水平滚动条事件（控制时间偏移）"""
        # 将滚动条值 (0-100) 映射到时间偏移范围
        # 移除对time_data的依赖，改为直接使用max_history_time
        max_time = self.max_history_time  # 直接使用最大历史时间
        
        # 滚动条左端(0)对应最开始时间(时间偏移0)，右端(100)对应最大偏移
        normalized_value = value / 100.0
        max_offset = max(0, max_time - self.time_window)
        self.time_offset = normalized_value * max_offset
        
        # 手动滚动时暂时禁用自动滚动
        if hasattr(self, 'auto_scroll_enabled'):
            self.auto_scroll_enabled = False
            
            # 设置定时器，3秒后重新启用自动滚动
            if not hasattr(self, 'auto_scroll_timer'):
                self.auto_scroll_timer = QTimer()
                self.auto_scroll_timer.timeout.connect(self.re_enable_auto_scroll)
                self.auto_scroll_timer.setSingleShot(True)
            
            self.auto_scroll_timer.start(3000)  # 3秒后重新启用
        
        # 更新显示
        self.update_axis_ranges()
        self.canvas.draw_idle()
    
    def re_enable_auto_scroll(self):
        """重新启用自动滚动"""
        self.auto_scroll_enabled = True
        print("🔄 自动滚动已重新启用")
    
    def update_scrollbars(self):
        """更新滚动条位置以同步当前视图状态"""
        if hasattr(self, 'v_scrollbar'):
            # 更新垂直滚动条
            scroll_value = int((self.y_view_center - 1.5) / 5.0 * 100)
            self.v_scrollbar.blockSignals(True)
            self.v_scrollbar.setValue(100 - scroll_value)
            self.v_scrollbar.blockSignals(False)
        
        if hasattr(self, 'h_scrollbar'):
            # 更新水平滚动条 - 适应新的滚动逻辑
            # 移除对time_data的依赖，直接使用max_history_time
            max_time = self.max_history_time  # 直接使用最大历史时间
            max_offset = max(0, max_time - self.time_window)
            
            if max_offset > 0:
                # 左端(0)对应时间偏移0，右端(100)对应最大偏移
                normalized_offset = self.time_offset / max_offset
                scroll_value = int(normalized_offset * 100)
            else:
                scroll_value = 0  # 默认最左边位置
            
            self.h_scrollbar.blockSignals(True)
            self.h_scrollbar.setValue(scroll_value)
            self.h_scrollbar.blockSignals(False)
    
    def add_pitch_data(self, pitch_data):
        """添加音高数据（支持历史数据存储）"""
        try:
            frequency = pitch_data.get('frequency', 0)
            confidence = pitch_data.get('confidence', 0)
            timestamp = pitch_data.get('timestamp', time.time())
            note_info = pitch_data.get('note_info', {})
            
            if frequency > 0:
                # 转换频率到Y轴位置（精确到半音）
                midi_number = 69 + 12 * np.log2(frequency / 440)  # A4 = 440Hz = MIDI 69
                octave = int(midi_number // 12) - 1
                semitone = int(midi_number % 12)
                y_pos = octave + semitone / 12
                
                # 计算全局时间（从开始到现在的总时间）
                if not hasattr(self, 'start_time'):
                    self.start_time = timestamp
                
                global_time = timestamp - self.start_time
                
                # 添加数据
                self.pitch_data.append(y_pos)
                self.time_data.append(global_time)
                self.confidence_data.append(confidence)
                self.note_data.append(note_info)
                
                # 更新当前音高状态（用于交互式标注）
                self.current_pitch_y = y_pos
                self.current_pitch_active = True
                self.last_pitch_time = time.time()  # 记录最后活跃时间
                
                # 调试信息（每10个数据点打印一次）
                if len(self.pitch_data) % 10 == 0:
                    print(f"音高数据点: {len(self.pitch_data)}, 最新: {y_pos:.2f}, 时间: {global_time:.2f}s")
                
                # 自动跟随功能
                if self.auto_follow and self.auto_scroll_enabled:
                    # 新的滚动逻辑：第8秒之前不滚动，第8秒后开始滚动
                    if global_time <= self.center_display_time:
                        # 前8秒：时间偏移保持为0，显示从0到16秒的内容
                        self.time_offset = 0.0
                    else:
                        # 第8秒后：开始滚动，保持音调曲线在屏幕中央生成
                        # 计算需要的时间偏移，使当前时间点在屏幕中央（8秒位置）
                        self.time_offset = global_time - self.center_display_time
                        
                        # 确保时间偏移不超过最大历史时间限制
                        max_offset = max(0, self.max_history_time - self.time_window)
                        self.time_offset = min(self.time_offset, max_offset)
                        
                        # 实时更新滚动条位置，确保滚动条与时间偏移同步
                        self.update_scrollbars()
                    
                    # 音高轴自动跟随（平滑移动到新音高区域）
                    current_display_range = self.y_view_range / self.zoom_level
                    margin = current_display_range * 0.2  # 20%的边距
                    
                    # 检查是否需要调整视图中心
                    if (y_pos < self.y_view_center - current_display_range + margin or 
                        y_pos > self.y_view_center + current_display_range - margin):
                        # 平滑移动到新的中心位置
                        target_center = y_pos
                        # 限制在合理范围内
                        target_center = max(1.5, min(6.5, target_center))
                        
                        # 使用加权平均实现平滑跟随
                        old_center = self.y_view_center
                        self.y_view_center = self.y_view_center * 0.8 + target_center * 0.2
                        
                        # 如果视图中心有明显变化，立即更新轴范围以保持缩放一致性
                        if abs(self.y_view_center - old_center) > 0.01:
                            self.update_axis_ranges()
                
        except Exception as e:
            print(f"添加音高数据错误: {e}")
    
    def update_display(self):
        """更新显示（支持历史数据查看）"""
        if len(self.pitch_data) == 0:
            return
        
        try:
            # 调试信息
            if len(self.pitch_data) % 20 == 0:  # 每20个数据点打印一次
                print(f"更新显示: 总数据{len(self.pitch_data)}点, pitch_line存在: {hasattr(self, 'pitch_line')}")
            
            # 根据当前时间偏移过滤数据
            time_start = self.time_offset
            time_end = self.time_offset + self.time_window
            
            # 过滤时间窗口内的数据
            valid_indices = []
            for i, t in enumerate(self.time_data):
                if time_start <= t <= time_end:
                    valid_indices.append(i)
            
            if not valid_indices:
                # 清空显示
                self.pitch_line.set_data([], [])
                self.canvas.draw_idle()
                return
            
            # 提取有效数据
            times = [self.time_data[i] for i in valid_indices]
            pitches = [self.pitch_data[i] for i in valid_indices]
            confidences = [self.confidence_data[i] for i in valid_indices]
            
            # 根据显示模式更新
            display_mode = self.display_mode.currentText() if hasattr(self, 'display_mode') else "心电图模式"
            
            if display_mode == "心电图模式":
                # 确保使用Matplotlib组件
                if self.main_plot_area != self.canvas:
                    self.switch_display_widget(use_pyqtgraph=False)
                
                # 心电图模式：更细的线条，提高颤音等细节显示清晰度
                self.pitch_line.set_data(times, pitches)
                self.update_ecg_mode(times, pitches, confidences)
                
            elif display_mode == "彩色渐变":
                # 彩色渐变模式：使用优化的Matplotlib LineCollection超细渐变
                print(f"🎨 超细平滑彩色渐变模式 - 数据点数: {len(times)}")
                
                # 强制使用优化的Matplotlib LineCollection方案
                print("✨ 使用优化的Matplotlib超细渐变方案")
                # 确保使用Matplotlib组件
                if self.main_plot_area != self.canvas:
                    self.switch_display_widget(use_pyqtgraph=False)
                
                # 尝试添加超细平滑的渐变效果
                gradient_success = False
                try:
                    result = self.update_beautiful_pitch_line(times, pitches, confidences)
                    gradient_success = (result is not False)
                    if gradient_success:
                        print("✅ 彩色渐变LineCollection创建成功")
                except Exception as e:
                    print(f"⚠️ 彩色渐变创建失败: {e}")
                    gradient_success = False
                
                # 如果渐变失败，提供彩色回退方案（不是绿色！）
                if not gradient_success:
                    print("🔄 使用彩色回退方案...")
                    self.pitch_line.set_data(times, pitches)
                    # 使用彩色而不是绿色
                    import colorsys
                    if len(pitches) > 0:
                        avg_pitch = sum(pitches) / len(pitches)
                        hue = ((avg_pitch - 1.0) % 6.0) / 6.0
                        rgb = colorsys.hsv_to_rgb(hue, 0.8, 1.0)
                        self.pitch_line.set_color(rgb)
                    else:
                        self.pitch_line.set_color('#FF6600')  # 橙色作为默认
                    self.pitch_line.set_linewidth(self.current_linewidth)  # 使用用户设置的线条粗细
                    self.pitch_line.set_alpha(0.9)
                else:
                    # 渐变成功，隐藏背景线
                    self.pitch_line.set_data([], [])
                    self.pitch_line.set_alpha(0.0)
            
            # 只在使用Matplotlib时更新坐标轴和刷新
            if self.main_plot_area == self.canvas:
                # 更新坐标轴范围（如果需要） - 修复缩放一致性问题
                current_xlim = self.ax.get_xlim()
                current_ylim = self.ax.get_ylim()
                
                # 计算考虑缩放的实际Y轴范围
                actual_y_range = self.y_view_range / self.zoom_level
                expected_y_min = self.y_view_center - actual_y_range
                expected_y_max = self.y_view_center + actual_y_range
                
                if (abs(current_xlim[0] - time_start) > 0.1 or 
                    abs(current_xlim[1] - time_end) > 0.1 or
                    abs(current_ylim[0] - expected_y_min) > 0.1 or
                    abs(current_ylim[1] - expected_y_max) > 0.1):
                    self.update_axis_ranges()
                
                self.canvas.draw_idle()
            
            # 更新状态显示
            self.update_status_display()
            
            # 每次显示更新时也同步更新滚动条，确保实时响应
            self.update_scrollbars()
            
        except Exception as e:
            print(f"更新显示错误: {e}")
    
    def update_beautiful_pitch_line(self, times, pitches, confidences):
        """更新美观的音高线条（彩色渐变模式专用 - 真彩色LineCollection实现）"""
        print(f"🎨 开始创建彩色渐变，数据点: {len(times)}")
        
        if len(times) == 0:
            print("⚠️ 没有数据点，退出")
            return False
        
        try:
            # 导入matplotlib线条集合
            from matplotlib.collections import LineCollection
            import colorsys
            print("✅ 成功导入LineCollection和colorsys")
            
            # 只清除旧的渐变效果，不影响其他collections
            if hasattr(self, 'gradient_lines'):
                for line in self.gradient_lines:
                    try:
                        if line is not None and line in self.ax.collections:
                            line.remove()
                    except:
                        pass
            self.gradient_lines = []
            
            # 安全地移除旧的高亮点
            if hasattr(self, 'highlight_point') and self.highlight_point is not None:
                try:
                    if self.highlight_point in self.ax.collections:
                        self.highlight_point.remove()
                except:
                    pass
                self.highlight_point = None
            
            print(f"🌈 LineCollection真彩色渐变，数据点: {len(times)}")
            
            if len(times) < 2:
                print("⚠️ 数据点不足，至少需要2个点来创建线段")
                return False
            
            # 方法1：超平滑LineCollection真彩色渐变（使用插值增加数据点）
            if len(times) >= 2 and SCIPY_AVAILABLE:
                # 插值增加数据点，让线条更平滑
                # 如果数据点少于100个，进行插值
                if len(times) < 100:
                    interp_times = np.linspace(times[0], times[-1], len(times) * 3)
                    if len(times) >= 4:  # 三次插值需要至少4个点
                        interp_pitches = interp1d(times, pitches, kind='cubic')(interp_times)
                    elif len(times) >= 2:  # 线性插值需要至少2个点
                        interp_pitches = interp1d(times, pitches, kind='linear')(interp_times)
                    else:
                        interp_times = times
                        interp_pitches = pitches
                else:
                    interp_times = times
                    interp_pitches = pitches
                
                points = np.array([interp_times, interp_pitches]).T.reshape(-1, 1, 2)
                segments = np.concatenate([points[:-1], points[1:]], axis=1)
                print(f"🔧 使用SciPy插值: {len(times)} -> {len(interp_times)} 数据点")
            else:
                # 没有scipy或数据不足时，使用原始数据
                interp_times = times
                interp_pitches = pitches
                points = np.array([times, pitches]).T.reshape(-1, 1, 2)
                segments = np.concatenate([points[:-1], points[1:]], axis=1)
                print(f"🔧 使用原始数据点: {len(times)} 个")
            
            # 为每个线段计算HSV彩虹色
            colors = []
            # 使用插值后的数据计算颜色
            interp_pitches = interp_pitches if 'interp_pitches' in locals() else pitches
            for i in range(len(segments)):
                if i+1 < len(interp_pitches):
                    # 使用线段中点的音高
                    mid_pitch = (interp_pitches[i] + interp_pitches[i+1]) / 2
                    
                    # 音高映射到HSV色相 (1-7八度 -> 0-1色相)
                    hue = ((mid_pitch - 1.0) % 6.0) / 6.0
                    
                    # 置信度影响饱和度（插值模式使用默认高置信度）
                    saturation = 0.95
                    
                    # 固定高亮度
                    value = 1.0
                    
                    # HSV转RGB
                    rgb = colorsys.hsv_to_rgb(hue, saturation, value)
                    colors.append(rgb)
            
            # 创建超细线条的LineCollection，提升平滑度
            if len(colors) > 0:
                line_collection = LineCollection(segments, colors=colors, 
                                               linewidths=self.current_linewidth, alpha=0.95, zorder=10,
                                               capstyle='round', joinstyle='round')
                self.ax.add_collection(line_collection)
                self.gradient_lines.append(line_collection)
                print(f"✅ LineCollection创建成功：{len(segments)}个线段，线条粗细={self.current_linewidth:.1f}px")
            
            # 方法2：仅显示最前端的单个高亮粒子
            if len(times) > 0:
                latest_time = times[-1]
                latest_pitch = pitches[-1]
                
                # 根据最新音高确定HSV彩虹高亮点颜色
                hue = ((latest_pitch - 1.0) % 6.0) / 6.0
                rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                
                # 创建中等大小的最前端高亮点
                try:
                    self.highlight_point = self.ax.scatter([latest_time], [latest_pitch], 
                                                         s=120, c=[rgb], alpha=1.0, 
                                                         zorder=20, edgecolors='white', 
                                                         linewidths=2)
                    print(f"✅ 前端高亮点创建成功: 时间={latest_time:.2f}, 音高={latest_pitch:.2f}")
                except Exception as e:
                    print(f"❌ 前端高亮点创建失败: {e}")
                    
            print(f"🎨 超细平滑彩虹渐变更新完成，共创建 {len(self.gradient_lines)} 个视觉元素")
            return True  # 返回成功状态
            
        except Exception as e:
            print(f"❌ 真彩色渐变更新错误: {e}")
            import traceback
            traceback.print_exc()
            # 在彩色渐变模式下，返回失败状态而不是强制回退
            print("⚠️ 彩色渐变失败，调用方将处理回退")
            return False  # 返回失败状态
    
    def fallback_simple_line(self, times, pitches):
        """回退到简单线条显示"""
        try:
            # 安全检查pitch_line是否还存在于axes中
            if not hasattr(self, 'pitch_line') or self.pitch_line is None or self.pitch_line not in self.ax.lines:
                # 重新创建pitch_line（使用用户设置的粗细）
                self.pitch_line, = self.ax.plot([], [], color='#00DD44', 
                                               linewidth=self.current_linewidth, alpha=0.9, zorder=10)
            
            # 设置线条数据
            self.pitch_line.set_data(times, pitches)
            
            # 设置美观的线条属性
            self.pitch_line.set_color('#00DD44')  # 浅绿色
            self.pitch_line.set_linewidth(self.current_linewidth)   # 使用用户设置的线条粗细
            self.pitch_line.set_alpha(0.9)       # 略微透明
            self.pitch_line.set_zorder(10)
            
        except Exception as e:
            print(f"简单线条回退错误: {e}")
            # 最后的备用方案 - 重新创建一切
            try:
                self.safe_clear_axis()
                self.setup_ecg_grid()
                self.pitch_line, = self.ax.plot(times, pitches, color='#00DD44', 
                                               linewidth=self.current_linewidth, alpha=0.9, zorder=10)
            except Exception as e2:
                print(f"完全重建线条失败: {e2}")
    
    def update_ecg_mode(self, times, pitches, confidences):
        """心电图模式更新 - 可调节线条显示，提高颤音等细节清晰度"""
        # 设置线条样式，使用用户设置的粗细
        self.pitch_line.set_color('#00FF44')  # 明亮绿色，心电图特征色
        self.pitch_line.set_linewidth(self.current_linewidth)  # 使用用户设置的线条粗细
        self.pitch_line.set_alpha(1.0)       # 完全不透明，确保清晰可见
        
        # 心电图模式专注于精细音高变化分析
        # 可调节线条粗细以适应不同的分析需求
        print(f"💚 心电图模式：{self.current_linewidth:.1f}px绿线，数据点={len(times)}")
    
    def update_frequency_mode(self, times, pitches, confidences):
        """频率曲线模式"""
        self.pitch_line.set_color('#00AAFF')
        self.pitch_line.set_linewidth(self.current_linewidth)  # 使用用户设置的线条粗细
        
        # 根据置信度调整透明度
        if confidences:
            avg_confidence = np.mean(confidences)
            self.pitch_line.set_alpha(0.5 + 0.5 * avg_confidence)
    
    def update_stepped_mode(self, times, pitches, confidences):
        """音符阶梯模式"""
        # 量化到最近的半音
        quantized_pitches = []
        for pitch in pitches:
            octave = int(pitch)
            semitone = round((pitch - octave) * 12)
            quantized_pitch = octave + semitone / 12
            quantized_pitches.append(quantized_pitch)
        
        self.pitch_line.set_data(times, quantized_pitches)
        self.pitch_line.set_color('#FF9900')
        self.pitch_line.set_linewidth(max(self.current_linewidth, 1.5))  # 阶梯模式使用较粗的线条
        self.pitch_line.set_drawstyle('steps-post')
    
    def update_gradient_mode(self, times, pitches, confidences):
        """彩色渐变模式 - 修复版本，避免artist错误"""
        if len(times) > 1:
            # 安全地清除旧的散点
            if hasattr(self, 'gradient_scatter') and self.gradient_scatter is not None:
                try:
                    self.gradient_scatter.remove()
                except:
                    pass  # 忽略移除失败的情况
                self.gradient_scatter = None
            
            # 根据音高高度设置颜色
            colors = []
            for pitch in pitches:
                if pitch < 2:
                    colors.append('#0066FF')  # 低音-蓝
                elif pitch < 4:
                    colors.append('#00FF66')  # 中低音-青绿
                elif pitch < 5:
                    colors.append('#AADD00')  # 中音-柔和黄绿（降低黄色强度）
                elif pitch < 6:
                    colors.append('#FF9900')  # 中高音-橙
                else:
                    colors.append('#FF0000')  # 高音-红
            
            # 创建渐变散点图
            try:
                self.gradient_scatter = self.ax.scatter(times, pitches, 
                                                      c=colors, s=30, alpha=0.8)
                
                # 连线 - 淡化基本线条
                if hasattr(self, 'pitch_line') and self.pitch_line is not None:
                    self.pitch_line.set_alpha(0.3)
                    self.pitch_line.set_color('#666666')  # 灰色背景线
                    
            except Exception as e:
                print(f"渐变散点创建失败: {e}")
                # 回退到基本显示
    
    def on_time_window_changed(self, value):
        """时间窗口改变"""
        self.time_window = float(value)
        self.time_label.setText(f"{self.time_window:.1f}s")
        
        # 重新设置时间网格
        self.safe_clear_axis()
        self.setup_ecg_grid()
        self.pitch_line, = self.ax.plot([], [], color=self.line_color, 
                                       linewidth=self.current_linewidth, alpha=0.9)
        # 使用缩放系统设置坐标轴范围，而不是直接设置
        self.update_axis_ranges()
        
        # 更新滚动条以反映新的时间窗口
        self.update_scrollbars()
    
    def on_sensitivity_changed(self, value):
        """敏感度改变"""
        sensitivity = value / 10.0
        self.sensitivity_label.setText(f"{sensitivity:.1f}x")
        
        # 调整Y轴范围 - 通过修改 y_view_range 而不是直接设置 ylim
        # 保持缩放系统的一致性
        base_range = 3.0  # 基础范围
        self.y_view_range = base_range / sensitivity
        
        # 使用缩放系统更新坐标轴范围
        self.update_axis_ranges()
    
    def on_display_mode_changed(self, mode):
        """显示模式改变"""
        # 重置线条样式
        if hasattr(self, 'pitch_line') and self.pitch_line is not None:
            self.pitch_line.set_drawstyle('default')
        
        # 安全地移除gradient_scatter（如果存在）
        if hasattr(self, 'gradient_scatter') and self.gradient_scatter is not None:
            try:
                self.gradient_scatter.remove()
            except:
                pass  # 忽略移除失败的情况
            self.gradient_scatter = None
        
        # 确保线条粗细设置在模式切换后保持
        if hasattr(self, 'current_linewidth'):
            # 延迟应用线条粗细，确保新模式的元素已创建
            QTimer.singleShot(100, lambda: self.apply_linewidth(self.current_linewidth))
        
        print(f"🔄 显示模式切换到: {mode}，将保持当前线条粗细: {getattr(self, 'current_linewidth', 0.6):.1f}px")
    
    def on_linewidth_preset_changed(self, preset_text):
        """线条粗细预设改变"""
        if preset_text == "自定义...":
            # 显示滑块和标签
            self.linewidth_slider.setVisible(True)
            self.linewidth_label.setVisible(True)
            # 使用当前滑块值
            current_value = self.linewidth_slider.value()
            linewidth = current_value / 10.0
            self.linewidth_label.setText(f"{linewidth:.1f}px")
        else:
            # 隐藏滑块和标签
            self.linewidth_slider.setVisible(False)
            self.linewidth_label.setVisible(False)
            
            # 解析预设值
            linewidth_map = {
                "0.5px 极细": 0.5,
                "0.6px 超细": 0.6,
                "0.8px 细线": 0.8,
                "1.0px 标准": 1.0,
                "1.5px 中等": 1.5,
                "2.0px 粗线": 2.0,
                "2.5px 很粗": 2.5,
                "3.0px 极粗": 3.0
            }
            linewidth = linewidth_map.get(preset_text, 0.6)
        
        # 应用线条粗细
        self.current_linewidth = linewidth
        self.apply_linewidth(linewidth)
        print(f"🖊️ 线条粗细设置为: {linewidth:.1f}px")
    
    def on_linewidth_slider_changed(self, value):
        """线条粗细滑块改变"""
        linewidth = value / 10.0  # 1-50 映射到 0.1-5.0
        self.linewidth_label.setText(f"{linewidth:.1f}px")
        self.current_linewidth = linewidth
        self.apply_linewidth(linewidth)
    
    def apply_linewidth(self, linewidth):
        """应用线条粗细到当前线条"""
        # 更新主线条的粗细
        if hasattr(self, 'pitch_line') and self.pitch_line is not None:
            self.pitch_line.set_linewidth(linewidth)
        
        # 更新当前渐变线条集合的粗细
        if hasattr(self, 'gradient_lines') and self.gradient_lines:
            for line_collection in self.gradient_lines:
                if line_collection is not None:
                    try:
                        # LineCollection使用set_linewidths方法
                        line_collection.set_linewidths(linewidth)
                        print(f"🔧 已更新LineCollection线条粗细: {linewidth:.1f}px")
                    except Exception as e:
                        print(f"⚠️ 更新LineCollection粗细失败: {e}")
                        # 备用方法：直接设置linewidths属性
                        try:
                            line_collection._linewidths = linewidth
                        except:
                            pass
        
        # 立即刷新显示
        if hasattr(self, 'canvas'):
            self.canvas.draw_idle()
        
        print(f"✅ 线条粗细已更新为: {linewidth:.1f}px")
    
    def on_zoom_changed(self, value):
        """缩放级别改变"""
        self.zoom_level = value / 10.0  # 1-50 映射到 0.1-5.0
        self.zoom_label.setText(f"{self.zoom_level:.1f}x")
        
        # 更新预设按钮的高亮状态
        self.update_preset_button_highlight()
        
        # 更新显示
        self.update_axis_ranges()
        self.canvas.draw()
        
        # 更新状态显示
        self.update_status_display()
    
    def set_zoom_preset(self, zoom_level):
        """设置预设缩放级别"""
        # 更新滑块位置
        slider_value = int(zoom_level * 10)
        self.zoom_slider.setValue(slider_value)
        
        # 更新缩放级别（这会触发 on_zoom_changed）
        self.zoom_level = zoom_level
        self.zoom_label.setText(f"{self.zoom_level:.1f}x")
        
        # 更新预设按钮高亮
        self.update_preset_button_highlight()
        
        # 更新显示
        self.update_axis_ranges()
        self.canvas.draw()
        
        # 显示设置信息
        preset_info = {
            0.5: "中央聚焦 - 仅显示中央C附近3个八度(C3-C5)，极端缩放时的核心区域",
            0.8: "基础八度框架 - 仅显示C0-C8每个八度的主音，最简化的参考框架",
            1.5: "稀疏音程 - 显示完全音程(C-F-G)避免重叠，清晰的音程关系",
            2.5: "八度主音显示 - 显示C0-C8每个八度主音及少量关键半音，保持整体结构清晰",
            5.0: "全音区显示 - 显示所有88键(C0-C8)及中间半音，适合需要查看全部细节的情况"
        }
        
        if zoom_level in preset_info:
            print(f"🔍 缩放预设: {zoom_level}x - {preset_info[zoom_level]}")
    
    def update_preset_button_highlight(self):
        """更新预设按钮的高亮状态"""
        if not hasattr(self, 'preset_buttons'):
            return
            
        # 预设值列表（更新为新的乐理预设）
        preset_values = [0.5, 0.8, 1.5, 2.5, 5.0]
        
        for i, btn in enumerate(self.preset_buttons):
            if i < len(preset_values):
                preset_value = preset_values[i]
                # 检查当前缩放是否接近这个预设值
                if abs(self.zoom_level - preset_value) < 0.05:
                    # 高亮当前预设
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #2A7A2A;
                            border: 2px solid #40B040;
                            border-radius: 4px;
                            padding: 4px 6px;
                            color: white;
                            font-size: 10px;
                            font-weight: bold;
                            min-width: 45px;
                            max-width: 60px;
                        }
                        QPushButton:hover {
                            background-color: #3A8A3A;
                            border: 2px solid #50C050;
                        }
                    """)
                else:
                    # 普通状态
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #2E2E2E;
                            border: 1px solid #505050;
                            border-radius: 4px;
                            padding: 4px 6px;
                            color: white;
                            font-size: 10px;
                            min-width: 45px;
                            max-width: 60px;
                        }
                        QPushButton:hover {
                            background-color: #404040;
                            border: 1px solid #707070;
                        }
                        QPushButton:pressed {
                            background-color: #1A5A1A;
                            border: 1px solid #2A7A2A;
                        }
                    """)
    
    def on_auto_scale_toggled(self, checked):
        """智能标注切换"""
        self.auto_scale = checked
        
        # 更新按钮样式
        if checked:
            self.auto_scale_btn.setText("智能标注")
            self.auto_scale_btn.setStyleSheet("""
                QPushButton {
                    background-color: #00AA00;
                    border: 1px solid #00CC00;
                    border-radius: 3px;
                    padding: 5px 10px;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #00CC00;
                }
            """)
        else:
            self.auto_scale_btn.setText("手动标注")
            self.auto_scale_btn.setStyleSheet("""
                QPushButton {
                    background-color: #666666;
                    border: 1px solid #888888;
                    border-radius: 3px;
                    padding: 5px 10px;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #888888;
                }
            """)
        
        # 重新设置网格
        self.setup_ecg_grid()
        self.canvas.draw()
    
    def set_max_history_time(self, max_time):
        """设置最大历史时间"""
        self.max_history_time = float(max_time)
        
        # 重新计算数据缓冲区大小
        max_data_points = int(64 * self.max_history_time)
        print(f"📊 更新数据缓冲区: {max_data_points} 个数据点 ({self.max_history_time}秒)")
        
        # 更新数据队列的最大长度
        # 注意：deque不支持动态修改maxlen，需要重新创建
        old_pitch_data = list(self.pitch_data)
        old_time_data = list(self.time_data)
        old_confidence_data = list(self.confidence_data)
        old_note_data = list(self.note_data)
        
        self.pitch_data = deque(old_pitch_data, maxlen=max_data_points)
        self.time_data = deque(old_time_data, maxlen=max_data_points)
        self.confidence_data = deque(old_confidence_data, maxlen=max_data_points)
        self.note_data = deque(old_note_data, maxlen=max_data_points)
        
        # 更新时间滑块的最大值
        if hasattr(self, 'time_slider'):
            # 横轴长度应该设置成最大历史时间，而不是限制在60秒
            self.time_slider.setRange(5, int(max_time))  # 5秒到最大历史时间
            # 如果当前时间窗口超过新的最大值，调整它
            if self.time_window > max_time:
                self.time_window = min(max_time, 60)  # 显示窗口最大60秒，但滑块范围到最大历史时间
                self.time_slider.setValue(int(self.time_window))
                self.time_label.setText(f"{self.time_window:.1f}s")
        
        print(f"✅ 最大历史时间设置为 {max_time} 秒")
    
    def set_custom_max_history_time(self):
        """自定义设置最大历史时间"""
        try:
            from PyQt6.QtWidgets import QInputDialog
        except ImportError:
            try:
                from PyQt5.QtWidgets import QInputDialog
            except ImportError:
                print("❌ 无法导入QInputDialog")
                return
        
        # 弹出输入对话框
        value, ok = QInputDialog.getDouble(
            self, 
            "设置自定义最大历史时间", 
            "请输入最大历史时间（秒）:",
            value=self.max_history_time,
            min=60,  # 最少60秒
            max=3600,  # 最多3600秒（1小时）
            decimals=0
        )
        
        if ok:
            self.set_max_history_time(value)
    
    def reset_view(self):
        """重置视图到默认状态"""
        self.y_view_center = 4.0  # C4为中心
        self.y_view_range = 3.0   # ±3个八度
        self.time_offset = 0.0    # 回到最新数据
        self.zoom_level = 1.0     # 重置缩放级别
        
        # 重置控件状态
        if hasattr(self, 'zoom_slider'):
            self.zoom_slider.setValue(10)  # 1.0x对应值10
            self.zoom_label.setText("1.0x")
        
        # 更新显示
        self.update_axis_ranges()
        self.canvas.draw()
        
        # 同步滚动条
        self.update_scrollbars()
        
        # 更新状态显示
        self.update_status_display()
    
    def on_auto_follow_toggled(self, checked):
        """自动跟随切换"""
        self.auto_follow = checked
        
        # 更新按钮样式
        if checked:
            self.auto_follow_btn.setText("自动跟随")
            self.auto_follow_btn.setStyleSheet("""
                QPushButton {
                    background-color: #00AA00;
                    border: 1px solid #00CC00;
                    border-radius: 3px;
                    padding: 5px 10px;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #00CC00;
                }
            """)
        else:
            self.auto_follow_btn.setText("手动模式")
            self.auto_follow_btn.setStyleSheet("""
                QPushButton {
                    background-color: #666666;
                    border: 1px solid #888888;
                    border-radius: 3px;
                    padding: 5px 10px;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #888888;
                }
            """)
    
    def update_status_display(self):
        """更新状态显示"""
        try:
            # 检查音高活跃状态（1秒无输入则认为不活跃）
            if hasattr(self, 'last_pitch_time') and self.current_pitch_active:
                if time.time() - self.last_pitch_time > 1.0:
                    self.current_pitch_active = False
                    # 重新绘制以更新标签显示
                    self.setup_ecg_grid()
                    self.canvas.draw_idle()
            
            # 音高中心显示
            center_octave = int(self.y_view_center)
            center_semitone = int((self.y_view_center - center_octave) * 12)
            center_note = self.note_names[center_semitone] + str(center_octave)
            
            # 时间偏移显示
            time_str = f"{self.time_offset:.1f}s"
            if self.time_offset == 0:
                time_str = "实时"
            
            # 显示范围（考虑缩放）
            actual_range = self.y_view_range / self.zoom_level
            
            # 数据统计和缓冲区状态
            data_count = len(self.pitch_data)
            max_data_points = self.pitch_data.maxlen if self.pitch_data.maxlen else 0
            buffer_usage = (data_count / max_data_points * 100) if max_data_points > 0 else 0
            
            # 缓冲区警告
            buffer_warning = ""
            if buffer_usage > 90:
                buffer_warning = " ⚠️缓冲区将满"
            elif buffer_usage > 80:
                buffer_warning = " 📊缓冲区较满"
            
            # 标注模式
            mode_str = "智能" if self.auto_scale else "手动"
            
            # 跟随模式
            follow_str = "开启" if self.auto_follow else "关闭"
            
            # 合并为一行显示状态信息
            status_text = f"中心: {center_note} | 时间: {time_str} | 缩放: {self.zoom_level:.1f}x | 标注: {mode_str} | 跟随: {follow_str} | 数据: {data_count}点({buffer_usage:.1f}%){buffer_warning}"
            self.status_label.setText(status_text)
            
        except Exception as e:
            self.status_label.setText(f"状态更新错误: {e}")
    
    def clear_data(self):
        """清除数据"""
        self.pitch_data.clear()
        self.time_data.clear()
        self.confidence_data.clear()
        self.note_data.clear()
        
        # 重置时间相关变量
        if hasattr(self, 'start_time'):
            delattr(self, 'start_time')
        
        self.pitch_line.set_data([], [])
        self.canvas.draw()
        
        # 更新状态
        self.update_status_display()


class IntegratedRecordingInterface(QMainWindow):
    """集成录音与分析界面主窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 状态变量
        self.is_recording = False
        self.is_analyzing = False
        self.should_save_recording = True
        
        # 当前音高状态（用于交互式标注）
        self.current_pitch_y = 4.0  # 当前音高的y坐标
        self.current_pitch_active = False  # 是否有活跃的音高输入
        self.last_pitch_time = 0  # 最后一次音高输入的时间
        
        # 音频处理器
        self.audio_processor = IntegratedAudioProcessor()
        
        # 统计数据
        self.total_pitches_detected = 0
        self.recording_duration = 0
        self.current_note = "--"
        self.current_frequency = 0
        
        # 字体状态
        self.chinese_font_available = False
        
        # 初始化界面
        self.init_ui()
        self.setup_connections()
        
        # 状态定时器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status_display)
        self.status_timer.start(100)  # 100ms更新一次
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("MindEcho - 集成录音与实时音高分析")
        self.setGeometry(100, 100, 1400, 900)
        
        # 设置深色主题
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
                color: #ffffff;
            }
            QGroupBox {
                border: 2px solid #404040;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #ffffff;
            }
            QPushButton {
                background-color: #404040;
                border: 2px solid #606060;
                border-radius: 6px;
                padding: 8px 15px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
                border-color: #707070;
            }
            QPushButton:pressed {
                background-color: #303030;
            }
            QLabel {
                color: #ffffff;
            }
        """)
        
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 创建控制面板
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel)
        
        # 创建可视化区域
        self.visualizer = ECGStylePitchVisualizer()
        main_layout.addWidget(self.visualizer)
        
        # 创建状态信息面板
        status_panel = self.create_status_panel()
        main_layout.addWidget(status_panel)
    
    def create_control_panel(self):
        """创建控制面板"""
        control_group = QGroupBox("录音和分析控制")
        layout = QVBoxLayout(control_group)
        
        # 第一行：录音控制
        recording_layout = QHBoxLayout()
        
        # 录音模式
        recording_layout.addWidget(QLabel("录音模式:"))
        self.recording_mode = QComboBox()
        self.recording_mode.addItems([
            "录音+分析+保存",
            "仅分析(不保存)",
            "录音+保存(不分析)"
        ])
        self.recording_mode.currentTextChanged.connect(self.on_recording_mode_changed)
        recording_layout.addWidget(self.recording_mode)
        
        # 主录音按钮
        self.main_record_button = QPushButton("开始录音分析")
        self.main_record_button.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32;
                border: 2px solid #4CAF50;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                color: white;
            }
            QPushButton:hover {
                background-color: #388E3C;
                border-color: #66BB6A;
            }
            QPushButton:pressed {
                background-color: #1B5E20;
            }
        """)
        self.main_record_button.clicked.connect(self.toggle_main_recording)
        recording_layout.addWidget(self.main_record_button)
        
        # 暂停按钮
        self.pause_button = QPushButton("暂停")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.pause_recording)
        recording_layout.addWidget(self.pause_button)
        
        recording_layout.addStretch()
        layout.addLayout(recording_layout)
        
        # 第二行：录音参数
        params_layout = QHBoxLayout()
        
        params_layout.addWidget(QLabel("采样率:"))
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["44100", "48000", "96000"])
        self.sample_rate_combo.setCurrentText("44100")
        params_layout.addWidget(self.sample_rate_combo)
        
        params_layout.addWidget(QLabel("文件名前缀:"))
        self.filename_prefix = QComboBox()
        self.filename_prefix.setEditable(True)
        self.filename_prefix.addItems([
            "recording",
            "practice", 
            "performance",
            "test"
        ])
        params_layout.addWidget(self.filename_prefix)
        
        params_layout.addWidget(QLabel("保存录音:"))
        self.save_checkbox = QCheckBox()
        self.save_checkbox.setChecked(True)
        self.save_checkbox.toggled.connect(self.on_save_mode_changed)
        params_layout.addWidget(self.save_checkbox)
        
        params_layout.addStretch()
        layout.addLayout(params_layout)
        
        return control_group
    
    def create_status_panel(self):
        """创建状态信息面板"""
        status_group = QGroupBox("实时状态信息")
        layout = QHBoxLayout(status_group)
        
        # 录音状态
        recording_status_layout = QVBoxLayout()
        recording_status_layout.addWidget(QLabel("录音状态"))
        
        self.recording_time_label = QLabel("录音时长: 00:00")
        self.recording_time_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        recording_status_layout.addWidget(self.recording_time_label)
        
        self.audio_level_label = QLabel("音频电平: 0%")
        recording_status_layout.addWidget(self.audio_level_label)
        
        # 音频电平指示器
        self.audio_level_bar = QProgressBar()
        self.audio_level_bar.setRange(0, 100)
        self.audio_level_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #404040;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
        """)
        recording_status_layout.addWidget(self.audio_level_bar)
        
        layout.addLayout(recording_status_layout)
        
        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)
        
        # 音高分析状态
        pitch_status_layout = QVBoxLayout()
        pitch_status_layout.addWidget(QLabel("音高分析状态"))
        
        self.current_pitch_label = QLabel("当前音高: -- Hz")
        self.current_pitch_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #4CAF50;")
        pitch_status_layout.addWidget(self.current_pitch_label)
        
        self.current_note_label = QLabel("当前音符: --")
        self.current_note_label.setStyleSheet("font-size: 14px; color: #FFC107;")
        pitch_status_layout.addWidget(self.current_note_label)
        
        self.detection_count_label = QLabel("检测点数: 0")
        pitch_status_layout.addWidget(self.detection_count_label)
        
        self.detection_rate_label = QLabel("检测频率: 0/秒")
        pitch_status_layout.addWidget(self.detection_rate_label)
        
        layout.addLayout(pitch_status_layout)
        
        # 分隔线
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.VLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator2)
        
        # 系统状态
        system_status_layout = QVBoxLayout()
        system_status_layout.addWidget(QLabel("系统状态"))
        
        self.system_status_label = QLabel("状态: 就绪")
        system_status_layout.addWidget(self.system_status_label)
        
        self.performance_label = QLabel("性能: 良好")
        system_status_layout.addWidget(self.performance_label)
        
        # 清除数据按钮
        clear_button = QPushButton("清除可视化数据")
        clear_button.clicked.connect(self.visualizer.clear_data)
        system_status_layout.addWidget(clear_button)
        
        layout.addLayout(system_status_layout)
        
        return status_group
    
    def setup_connections(self):
        """设置信号连接"""
        # 音频处理器信号
        self.audio_processor.pitch_detected.connect(self.on_pitch_detected)
        self.audio_processor.audio_level_updated.connect(self.on_audio_level_updated)
        self.audio_processor.recording_progress.connect(self.on_recording_progress)
        self.audio_processor.status_updated.connect(self.on_status_updated)
        self.audio_processor.recording_finished.connect(self.on_recording_finished)
        self.audio_processor.error_occurred.connect(self.on_error_occurred)
    
    def toggle_main_recording(self):
        """切换主录音状态"""
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        """开始录音"""
        try:
            # 设置参数
            sample_rate = int(self.sample_rate_combo.currentText())
            should_save = self.save_checkbox.isChecked()
            
            # 生成文件名
            if should_save:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                prefix = self.filename_prefix.currentText()
                filename = f"{prefix}_{timestamp}"
            else:
                filename = None
            
            # 更新处理器参数
            self.audio_processor.sample_rate = sample_rate
            
            # 启动录音
            if self.audio_processor.start_recording(filename, should_save):
                self.is_recording = True
                
                # 更新UI
                self.main_record_button.setText("停止录音")
                self.main_record_button.setStyleSheet("""
                    QPushButton {
                        background-color: #D32F2F;
                        border: 2px solid #F44336;
                        border-radius: 8px;
                        padding: 12px 24px;
                        font-size: 14px;
                        font-weight: bold;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #F44336;
                        border-color: #EF5350;
                    }
                """)
                
                self.pause_button.setEnabled(True)
                
                # 清除统计数据
                self.total_pitches_detected = 0
                self.recording_duration = 0
                
                # 清除可视化
                self.visualizer.clear_data()
                
        except Exception as e:
            QMessageBox.critical(self, "录音错误", f"启动录音失败: {e}")
    
    def stop_recording(self):
        """停止录音"""
        try:
            self.audio_processor.stop_recording()
            self.is_recording = False
            
            # 更新UI
            self.main_record_button.setText("开始录音分析")
            self.main_record_button.setStyleSheet("""
                QPushButton {
                    background-color: #2E7D32;
                    border: 2px solid #4CAF50;
                    border-radius: 8px;
                    padding: 12px 24px;
                    font-size: 14px;
                    font-weight: bold;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #388E3C;
                    border-color: #66BB6A;
                }
            """)
            
            self.pause_button.setEnabled(False)
            
        except Exception as e:
            QMessageBox.critical(self, "录音错误", f"停止录音失败: {e}")
    
    def pause_recording(self):
        """暂停/恢复录音"""
        # 这里可以实现暂停逻辑
        if self.pause_button.text() == "暂停":
            self.pause_button.setText("继续")
            # 实现暂停逻辑
        else:
            self.pause_button.setText("暂停")
            # 实现继续逻辑
    
    def on_recording_mode_changed(self, mode):
        """录音模式改变"""
        if "不保存" in mode:
            self.save_checkbox.setChecked(False)
        elif "不分析" in mode:
            self.save_checkbox.setChecked(True)
        else:
            self.save_checkbox.setChecked(True)
    
    def on_save_mode_changed(self, checked):
        """保存模式改变"""
        self.should_save_recording = checked
        mode_text = "保存录音" if checked else "不保存录音"
        self.system_status_label.setText(f"状态: {mode_text}")
    
    def on_pitch_detected(self, pitch_data):
        """音高检测回调"""
        try:
            # 更新统计
            self.total_pitches_detected += 1
            
            # 更新当前音高信息
            frequency = pitch_data.get('frequency', 0)
            note_info = pitch_data.get('note_info', {})
            
            if frequency > 0:
                self.current_frequency = frequency
                
                if note_info:
                    note_name = note_info.get('note_name', '--')
                    octave = note_info.get('octave', '')
                    cents = note_info.get('cents', 0)
                    self.current_note = f"{note_name}{octave}"
                    
                    self.current_note_label.setText(
                        f"当前音符: {note_name}{octave} ({cents:+.0f} cents)"
                    )
                else:
                    self.current_note = "--"
                    self.current_note_label.setText("当前音符: --")
            
            # 发送到可视化器
            self.visualizer.add_pitch_data(pitch_data)
            
        except Exception as e:
            print(f"处理音高数据错误: {e}")
    
    def on_audio_level_updated(self, level):
        """音频电平更新"""
        try:
            # 转换为百分比
            level_percent = min(100, int(level * 1000))
            self.audio_level_bar.setValue(level_percent)
            self.audio_level_label.setText(f"音频电平: {level_percent}%")
            
        except Exception as e:
            print(f"更新音频电平错误: {e}")
    
    def on_recording_progress(self, duration):
        """录音进度更新"""
        self.recording_duration = duration
    
    def on_status_updated(self, status):
        """状态更新"""
        self.system_status_label.setText(f"状态: {status}")
    
    def on_recording_finished(self, filename, analysis_results):
        """录音完成"""
        try:
            # 显示结果
            total_pitches = analysis_results.get('total_pitches', 0)
            duration = analysis_results.get('recording_duration', 0)
            
            if filename:
                message = f"录音已保存: {os.path.basename(filename)}\n"
            else:
                message = "分析完成（未保存录音）\n"
            
            message += f"录音时长: {duration:.1f}秒\n"
            message += f"检测到音高点: {total_pitches}个\n"
            
            if duration > 0:
                detection_rate = total_pitches / duration
                message += f"平均检测频率: {detection_rate:.1f}次/秒"
            
            QMessageBox.information(self, "录音完成", message)
            
        except Exception as e:
            print(f"处理录音完成事件错误: {e}")
    
    def on_error_occurred(self, error_msg):
        """错误处理"""
        QMessageBox.critical(self, "错误", error_msg)
        self.system_status_label.setText(f"错误: {error_msg}")
    
    def update_status_display(self):
        """更新状态显示"""
        try:
            # 更新录音时长
            if self.is_recording and self.recording_duration > 0:
                minutes = int(self.recording_duration // 60)
                seconds = int(self.recording_duration % 60)
                self.recording_time_label.setText(f"录音时长: {minutes:02d}:{seconds:02d}")
            
            # 更新当前音高
            if self.current_frequency > 0:
                self.current_pitch_label.setText(f"当前音高: {self.current_frequency:.1f} Hz")
            else:
                self.current_pitch_label.setText("当前音高: -- Hz")
            
            # 更新检测统计
            self.detection_count_label.setText(f"检测点数: {self.total_pitches_detected}")
            
            if self.recording_duration > 0:
                detection_rate = self.total_pitches_detected / self.recording_duration
                self.detection_rate_label.setText(f"检测频率: {detection_rate:.1f}/秒")
            else:
                self.detection_rate_label.setText("检测频率: 0/秒")
            
        except Exception as e:
            print(f"更新状态显示错误: {e}")


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用信息
    app.setApplicationName("MindEcho 集成录音分析")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("MindEcho")
    
    # 创建主窗口
    main_window = IntegratedRecordingInterface()
    main_window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
