"""
MindEcho 增强版主窗口
集成实时音高检测和谱线可视化
"""

import sys
import os
import time
import threading
import numpy as np
from pathlib import Path

# 添加项目根目录到路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

# 尝试导入PyQt6，失败时降级到PyQt5
try:
    from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                 QPushButton, QLabel, QFileDialog, QMessageBox,
                                 QTabWidget, QSlider, QSpinBox, QComboBox,
                                 QTextEdit, QProgressBar, QGroupBox)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt6.QtGui import QFont, QIcon
    PYQT_VERSION = 6
    print("使用 PyQt6")
except ImportError:
    try:
        from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                     QPushButton, QLabel, QFileDialog, QMessageBox,
                                     QTabWidget, QSlider, QSpinBox, QComboBox,
                                     QTextEdit, QProgressBar, QGroupBox)
        from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
        from PyQt5.QtGui import QFont, QIcon
        PYQT_VERSION = 5
        print("使用 PyQt5")
    except ImportError:
        print("错误：需要安装 PyQt6 或 PyQt5")
        sys.exit(1)

# 导入本地模块
try:
    from src.audio_processing.recorder import AudioRecorder
    from src.audio_processing.integrated_recorder import IntegratedRecorderAnalyzer
    from src.analysis.pitch_detection import PitchDetector
    from src.analysis.enhanced_realtime_analyzer import EnhancedRealTimeAnalyzer
    from src.analysis.staff_visualizer import RealTimeStaffWidget
    from src.gui.full_range_visualizer import FullRangePitchVisualizer
except ImportError as e:
    print(f"导入模块错误: {e}")
    print("请确保所有模块文件都存在")

class PitchAnalysisThread(QThread):
    """音高分析线程"""
    
    pitch_detected = pyqtSignal(float, float, dict)  # 时间戳, 频率, 音符信息
    analysis_status = pyqtSignal(str)  # 分析状态信息
    
    def __init__(self):
        super().__init__()
        self.analyzer = None
        self.is_analyzing = False
        
    def start_analysis(self, sample_rate=44100, frame_size=4096):
        """开始音高分析"""
        try:
            self.analyzer = EnhancedRealTimeAnalyzer()
            self.is_analyzing = True
            self.start()
            self.analysis_status.emit("音高分析已启动")
        except Exception as e:
            self.analysis_status.emit(f"启动音高分析失败: {e}")
    
    def stop_analysis(self):
        """停止音高分析"""
        self.is_analyzing = False
        if self.analyzer:
            self.analyzer.stop()
        self.analysis_status.emit("音高分析已停止")
    
    def _on_pitch_detected(self, pitch_data):
        """音高检测回调"""
        if pitch_data and 'frequency' in pitch_data:
            timestamp = time.time()
            frequency = pitch_data['frequency']
            note_info = pitch_data.get('note_info', {})
            
            self.pitch_detected.emit(timestamp, frequency, note_info)
    
    def run(self):
        """线程运行"""
        if self.analyzer:
            self.analyzer.start()
            
            while self.is_analyzing:
                time.sleep(0.01)  # 10ms 间隔

class IntegratedRecordingThread(QThread):
    """集成录音和音高分析线程"""
    
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(str, dict)  # output_file, analysis_data
    recording_error = pyqtSignal(str)
    pitch_detected = pyqtSignal(dict)  # 实时音高数据
    stats_updated = pyqtSignal(dict)  # 统计信息更新
    
    def __init__(self):
        super().__init__()
        self.recorder = None
        self.is_recording = False
        self.filename = None
        self.sample_rate = 44100
        self.channels = 1
        self.stats_counter = 0
    
    def start_integrated_recording(self, filename, sample_rate=44100, channels=1):
        """开始集成录音"""
        try:
            # 确保录音目录存在
            recordings_dir = project_root / "recordings"
            recordings_dir.mkdir(exist_ok=True)
            
            self.filename = filename
            self.sample_rate = sample_rate
            self.channels = channels
            
            # 创建集成录音器
            self.recorder = IntegratedRecorderAnalyzer(
                sample_rate=sample_rate,
                channels=channels,
                chunk_size=4096,
                output_dir=str(recordings_dir)
            )
            
            # 设置音高回调
            self.recorder.set_pitch_callback(self._on_pitch_detected)
            
            self.is_recording = True
            self.start()
            
        except Exception as e:
            self.recording_error.emit(f"启动集成录音失败: {e}")
    
    def stop_integrated_recording(self):
        """停止集成录音"""
        self.is_recording = False
    
    def _on_pitch_detected(self, pitch_data):
        """音高检测回调"""
        self.pitch_detected.emit(pitch_data)
        
        # 每10次音高检测更新一次统计信息
        self.stats_counter += 1
        if self.stats_counter >= 10:
            self.stats_counter = 0
            if self.recorder:
                stats = self.recorder.get_current_stats()
                if stats:
                    self.stats_updated.emit(stats)
    
    def run(self):
        """线程运行"""
        try:
            if self.recorder:
                self.recording_started.emit()
                
                # 开始集成录音和分析
                if self.recorder.start_recording_with_analysis(self.filename):
                    
                    # 等待录音完成
                    while self.is_recording:
                        time.sleep(0.1)
                    
                    # 停止录音并获取结果
                    result = self.recorder.stop_recording_with_analysis()
                    
                    if result:
                        output_file = result.get('output_file', '')
                        analysis_data = result.get('analysis_data', {})
                        self.recording_stopped.emit(output_file, analysis_data)
                    else:
                        self.recording_error.emit("保存录音数据失败")
                else:
                    self.recording_error.emit("启动录音失败")
                
        except Exception as e:
            self.recording_error.emit(f"集成录音过程错误: {e}")

class RecordingThread(QThread):
    """录音线程"""
    
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(str)  # 录音文件路径
    recording_error = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.recorder = None
        self.is_recording = False
        self.output_path = None
        
    def start_recording(self, filename, sample_rate=44100, channels=1):
        """开始录音"""
        try:
            # 确保录音目录存在
            recordings_dir = project_root / "recordings"
            recordings_dir.mkdir(exist_ok=True)
            
            self.output_path = recordings_dir / filename
            
            self.recorder = AudioRecorder(
                sample_rate=sample_rate,
                channels=channels
            )
            
            self.is_recording = True
            self.start()
            
        except Exception as e:
            self.recording_error.emit(f"启动录音失败: {e}")
    
    def stop_recording(self):
        """停止录音"""
        self.is_recording = False
        if self.recorder:
            self.recorder.stop_recording()
    
    def run(self):
        """线程运行"""
        try:
            if self.recorder and self.output_path:
                self.recording_started.emit()
                
                # 开始录音
                self.recorder.start_recording(str(self.output_path))
                
                # 等待录音完成
                while self.is_recording:
                    time.sleep(0.1)
                
                # 停止录音
                self.recorder.stop_recording()
                self.recording_stopped.emit(str(self.output_path))
                
        except Exception as e:
            self.recording_error.emit(f"录音过程错误: {e}")

class EnhancedMindEchoMainWindow(QMainWindow):
    """增强版 MindEcho 主窗口"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_audio_system()
        # 调试开关：默认全部关闭，可按需打开
        self.debug_flags = {
            'audio_status_log': False,
        }
        
        # 状态变量
        self.is_recording = False
        self.is_analyzing = False
        self.recording_mode = "integrated"  # "integrated" 或 "separate"
        
        # 线程
        self.recording_thread = RecordingThread()
        self.integrated_recording_thread = IntegratedRecordingThread()
        self.pitch_thread = PitchAnalysisThread()
        
        # 连接信号
        self.setup_signals()
        
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("MindEcho - 智能音频录制与分析系统")
        self.setGeometry(100, 100, 1200, 800)
        
        # 中央widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # 录音标签页
        self.create_recording_tab()
        
        # 音高分析标签页
        self.create_pitch_analysis_tab()
        
        # 谱线可视化标签页
        self.create_staff_visualization_tab()
        
        # 状态栏
        self.status_label = QLabel("就绪")
        main_layout.addWidget(self.status_label)
        
    def create_recording_tab(self):
        """创建录音标签页"""
        recording_widget = QWidget()
        layout = QVBoxLayout(recording_widget)
        
        # 录音控制组
        control_group = QGroupBox("录音控制")
        control_layout = QVBoxLayout(control_group)
        
        # 录音参数
        params_layout = QHBoxLayout()
        
        # 录音模式选择
        params_layout.addWidget(QLabel("录音模式:"))
        self.recording_mode_combo = QComboBox()
        self.recording_mode_combo.addItems([
            "集成模式 (录音+音高检测)", 
            "分离模式 (仅录音)"
        ])
        self.recording_mode_combo.currentTextChanged.connect(self.on_recording_mode_changed)
        params_layout.addWidget(self.recording_mode_combo)
        
        # 采样率选择
        params_layout.addWidget(QLabel("采样率:"))
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["44100", "48000", "96000"])
        self.sample_rate_combo.setCurrentText("44100")
        params_layout.addWidget(self.sample_rate_combo)
        
        # 通道数选择
        params_layout.addWidget(QLabel("通道:"))
        self.channels_combo = QComboBox()
        self.channels_combo.addItems(["1 (单声道)", "2 (立体声)"])
        params_layout.addWidget(self.channels_combo)
        
        control_layout.addLayout(params_layout)
        
        # 录音按钮
        button_layout = QHBoxLayout()
        
        self.record_button = QPushButton("开始录音")
        self.record_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.record_button.clicked.connect(self.toggle_recording)
        button_layout.addWidget(self.record_button)
        
        self.open_folder_button = QPushButton("打开录音文件夹")
        self.open_folder_button.clicked.connect(self.open_recordings_folder)
        button_layout.addWidget(self.open_folder_button)
        
        control_layout.addLayout(button_layout)
        layout.addWidget(control_group)
        
        # 实时统计信息组（仅在集成模式下显示）
        self.stats_group = QGroupBox("实时统计")
        stats_layout = QVBoxLayout(self.stats_group)
        
        # 统计信息标签
        self.duration_label = QLabel("录音时长: 00:00")
        self.pitch_count_label = QLabel("检测到音高点: 0")
        self.current_note_label = QLabel("当前音符: --")
        self.current_freq_label = QLabel("当前频率: -- Hz")
        self.stats_label = QLabel("实时统计: 准备就绪")
        
        stats_layout.addWidget(self.duration_label)
        stats_layout.addWidget(self.pitch_count_label)
        stats_layout.addWidget(self.current_note_label)
        stats_layout.addWidget(self.current_freq_label)
        stats_layout.addWidget(self.stats_label)
        
        layout.addWidget(self.stats_group)
        self.stats_group.setVisible(True)  # 默认显示（集成模式）
        
        # 录音日志
        log_group = QGroupBox("录音日志")
        log_layout = QVBoxLayout(log_group)
        
        self.recording_log = QTextEdit()
        self.recording_log.setMaximumHeight(200)
        log_layout.addWidget(self.recording_log)
        
        layout.addWidget(log_group)
        
        self.tab_widget.addTab(recording_widget, "录音")
    
    def create_pitch_analysis_tab(self):
        """创建音高分析标签页"""
        analysis_widget = QWidget()
        layout = QVBoxLayout(analysis_widget)
        
        # 分析控制组
        control_group = QGroupBox("音高分析控制")
        control_layout = QVBoxLayout(control_group)
        
        # 分析参数
        params_layout = QHBoxLayout()
        
        params_layout.addWidget(QLabel("分析方法:"))
        self.analysis_method_combo = QComboBox()
        self.analysis_method_combo.addItems(["YIN算法", "自相关", "FFT"])
        params_layout.addWidget(self.analysis_method_combo)
        
        params_layout.addWidget(QLabel("平滑强度:"))
        self.smoothing_slider = QSlider(Qt.Orientation.Horizontal)
        self.smoothing_slider.setRange(0, 10)
        self.smoothing_slider.setValue(5)
        params_layout.addWidget(self.smoothing_slider)
        
        control_layout.addLayout(params_layout)
        
        # 分析按钮
        self.analysis_button = QPushButton("开始音高分析")
        self.analysis_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.analysis_button.clicked.connect(self.toggle_pitch_analysis)
        control_layout.addWidget(self.analysis_button)
        
        layout.addWidget(control_group)
        
        # 完整音域可视化
        try:
            self.full_range_visualizer = FullRangePitchVisualizer()
            layout.addWidget(self.full_range_visualizer)
        except Exception as e:
            # 如果创建失败，显示错误信息
            error_label = QLabel(f"可视化组件加载失败: {e}")
            error_label.setStyleSheet("color: red;")
            layout.addWidget(error_label)
            self.full_range_visualizer = None
        
        # 实时信息显示面板（始终创建）
        info_group = QGroupBox("实时音高信息")
        info_layout = QVBoxLayout(info_group)
        
        self.pitch_info_label = QLabel("当前音高: --")
        self.pitch_info_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        info_layout.addWidget(self.pitch_info_label)
        
        self.note_info_label = QLabel("音符: --")
        self.note_info_label.setStyleSheet("font-size: 14px;")
        info_layout.addWidget(self.note_info_label)
        
        layout.addWidget(info_group)
        
        # 分析日志
        log_group = QGroupBox("分析日志")
        log_layout = QVBoxLayout(log_group)
        
        self.analysis_log = QTextEdit()
        self.analysis_log.setMaximumHeight(200)
        log_layout.addWidget(self.analysis_log)
        
        layout.addWidget(log_group)
        
        self.tab_widget.addTab(analysis_widget, "音高分析")
    
    def create_staff_visualization_tab(self):
        """创建谱线可视化标签页"""
        try:
            # 尝试创建Qt集成的五线谱组件
            self.staff_widget = RealTimeStaffWidget()
            self.tab_widget.addTab(self.staff_widget, "五线谱可视化")
        except Exception as e:
            # 如果创建失败，显示错误信息
            error_widget = QWidget()
            error_layout = QVBoxLayout(error_widget)
            
            error_label = QLabel(f"五线谱可视化加载失败: {e}")
            error_label.setStyleSheet("color: red; font-size: 14px;")
            error_layout.addWidget(error_label)
            
            fallback_button = QPushButton("使用独立窗口显示五线谱")
            fallback_button.clicked.connect(self.open_standalone_staff_viewer)
            error_layout.addWidget(fallback_button)
            
            self.tab_widget.addTab(error_widget, "五线谱可视化")
            self.staff_widget = None
    
    def init_audio_system(self):
        """初始化音频系统"""
        try:
            # 可以在这里进行音频设备检测等初始化工作
            self.log_message("音频系统初始化完成")
        except Exception as e:
            self.log_message(f"音频系统初始化失败: {e}")
    
    def on_recording_mode_changed(self, mode_text):
        """录音模式切换处理"""
        if "集成模式" in mode_text:
            self.recording_mode = "integrated"
            self.stats_group.setVisible(True)
            self.log_message("切换到集成模式 (录音+音高检测)")
        else:
            self.recording_mode = "separate"
            self.stats_group.setVisible(False)
            self.log_message("切换到分离模式 (仅录音)")
    
    def setup_signals(self):
        """设置信号连接"""
        # 录音线程信号
        self.recording_thread.recording_started.connect(
            lambda: self.log_message("录音开始")
        )
        self.recording_thread.recording_stopped.connect(
            self.on_recording_stopped
        )
        self.recording_thread.recording_error.connect(
            self.on_recording_error
        )
        
        # 集成录音线程信号
        self.integrated_recording_thread.recording_started.connect(
            lambda: self.log_message("开始集成录音和音高分析")
        )
        self.integrated_recording_thread.recording_stopped.connect(
            self.on_integrated_recording_stopped
        )
        self.integrated_recording_thread.recording_error.connect(
            self.on_recording_error
        )
        self.integrated_recording_thread.pitch_detected.connect(
            self.on_pitch_detected
        )
        self.integrated_recording_thread.stats_updated.connect(
            self.on_stats_updated
        )
        
        # 音高分析线程信号
        self.pitch_thread.pitch_detected.connect(
            self.on_pitch_detected
        )
        self.pitch_thread.analysis_status.connect(
            self.log_analysis_message
        )
    
    def toggle_recording(self):
        """切换录音状态"""
        if not self.is_recording:
            # 开始录音
            sample_rate = int(self.sample_rate_combo.currentText())
            channels = 1 if "单声道" in self.channels_combo.currentText() else 2
            
            # 生成文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            if self.recording_mode == "integrated":
                # 集成模式：录音+音高分析
                filename = f"integrated_recording_{timestamp}"
                self.integrated_recording_thread.start_integrated_recording(
                    filename, sample_rate, channels
                )
                self.log_message("启动集成录音模式")
            else:
                # 分离模式：仅录音
                filename = f"recording_{timestamp}.wav"
                self.recording_thread.start_recording(filename, sample_rate, channels)
                self.log_message("启动分离录音模式")
            
            self.is_recording = True
            self.record_button.setText("停止录音")
            self.record_button.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    font-size: 14px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #da190b;
                }
            """)
            
        else:
            # 停止录音
            if self.recording_mode == "integrated":
                self.integrated_recording_thread.stop_integrated_recording()
            else:
                self.recording_thread.stop_recording()
            
            self.is_recording = False
            self.record_button.setText("开始录音")
            self.record_button.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    font-size: 14px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)
    
    def toggle_pitch_analysis(self):
        """切换音高分析状态"""
        if not self.is_analyzing:
            # 开始分析
            try:
                # 创建增强实时分析器
                self.enhanced_analyzer = EnhancedRealTimeAnalyzer(
                    sample_rate=int(self.sample_rate_combo.currentText()),
                    chunk_size=2048  # 更小的块大小提高实时性
                )
                
                # 设置回调函数
                self.enhanced_analyzer.set_callbacks(
                    pitch_callback=self.on_enhanced_pitch_detected,
                    spectrum_callback=self.on_spectrum_updated
                )
                
                # 启动音频流（简化版，这里需要实际的音频输入）
                import sounddevice as sd
                
                def audio_callback(indata, frames, time, status):
                    if status and getattr(self, 'debug_flags', {}).get('audio_status_log', False):
                        print(f"音频流状态: {status}")
                    # 将音频数据添加到分析器
                    self.enhanced_analyzer.add_audio_data(indata[:, 0])
                
                # 启动音频流
                self.audio_stream = sd.InputStream(
                    callback=audio_callback,
                    samplerate=int(self.sample_rate_combo.currentText()),
                    channels=1,
                    blocksize=2048
                )
                self.audio_stream.start()
                
                # 启动分析
                self.enhanced_analyzer.start_analysis()
                
                # 清除可视化数据
                if self.full_range_visualizer:
                    self.full_range_visualizer.clear_data()
                
                self.is_analyzing = True
                self.analysis_button.setText("停止分析")
                self.analysis_button.setStyleSheet("""
                    QPushButton {
                        background-color: #f44336;
                        color: white;
                        border: none;
                        padding: 10px 20px;
                        font-size: 14px;
                        border-radius: 5px;
                    }
                    QPushButton:hover {
                        background-color: #da190b;
                    }
                """)
                
                print("增强音高分析已启动")
                
            except Exception as e:
                print(f"启动音高分析失败: {e}")
                QMessageBox.critical(self, "分析错误", f"启动音高分析失败: {e}")
            
        else:
            # 停止分析
            try:
                if hasattr(self, 'enhanced_analyzer'):
                    self.enhanced_analyzer.stop_analysis()
                
                if hasattr(self, 'audio_stream'):
                    self.audio_stream.stop()
                    self.audio_stream.close()
                
                self.is_analyzing = False
                self.analysis_button.setText("开始音高分析")
                self.analysis_button.setStyleSheet("""
                    QPushButton {
                        background-color: #2196F3;
                        color: white;
                        border: none;
                        padding: 10px 20px;
                        font-size: 14px;
                        border-radius: 5px;
                    }
                    QPushButton:hover {
                        background-color: #1976D2;
                    }
                """)
                
                print("音高分析已停止")
                
            except Exception as e:
                print(f"停止音高分析时出错: {e}")
    
    def on_enhanced_pitch_detected(self, pitch_data):
        """增强音高检测回调"""
        try:
            frequency = pitch_data.get('frequency', 0)
            confidence = pitch_data.get('confidence', 0)
            note_info = pitch_data.get('note_info', {})
            
            # 更新完整音域可视化
            if self.full_range_visualizer and frequency > 0:
                self.full_range_visualizer.add_pitch_data(frequency, confidence)
            
            # 更新实时信息显示
            if hasattr(self, 'pitch_info_label'):
                if frequency > 0:
                    self.pitch_info_label.setText(f"当前音高: {frequency:.1f} Hz")
                    
                    if note_info:
                        note_name = note_info.get('note_name', '--')
                        octave = note_info.get('octave', '')
                        cents = note_info.get('cents', 0)
                        
                        self.note_info_label.setText(
                            f"音符: {note_name}{octave} (偏差: {cents:+.0f} cents)"
                        )
                else:
                    self.pitch_info_label.setText("当前音高: -- Hz")
                    self.note_info_label.setText("音符: --")
            
            # 更新统计信息
            stats = self.enhanced_analyzer.get_current_pitch_stats()
            if stats and hasattr(self, 'stats_label'):
                stability = stats.get('stability', 0)
                variance = stats.get('pitch_variance', 0)
                self.stats_label.setText(
                    f"稳定性: {stability:.2f} | 方差: {variance:.1f}"
                )
                
        except Exception as e:
            print(f"处理音高数据时出错: {e}")
    
    def on_spectrum_updated(self, spectrum_data):
        """频谱更新回调"""
        try:
            # 这里可以添加频谱显示逻辑
            pass
        except Exception as e:
            print(f"处理频谱数据时出错: {e}")
    
    def on_recording_stopped(self, file_path):
        """录音停止回调"""
        self.log_message(f"录音完成: {file_path}")
    
    def on_recording_error(self, error_msg):
        """录音错误回调"""
        self.log_message(f"录音错误: {error_msg}")
        QMessageBox.critical(self, "录音错误", error_msg)
    
    def on_integrated_recording_stopped(self, output_file, analysis_data):
        """集成录音停止的回调"""
        try:
            print(f"集成录音完成: {output_file}")
            print(f"分析数据包含 {len(analysis_data.get('pitches', []))} 个音高点")
            
            # 更新状态显示
            self.update_status(f"录音已保存: {os.path.basename(output_file)}")
            
            # 显示分析结果
            if analysis_data and 'pitches' in analysis_data:
                pitch_count = len(analysis_data['pitches'])
                valid_pitches = len([p for p in analysis_data['pitches'] if p > 0])
                avg_pitch = sum([p for p in analysis_data['pitches'] if p > 0]) / max(valid_pitches, 1)
                
                self.update_status(f"音高分析完成: {valid_pitches}/{pitch_count} 有效音高点, 平均频率: {avg_pitch:.1f}Hz")
                
        except Exception as e:
            print(f"处理集成录音结果时出错: {e}")
    
    def on_stats_updated(self, stats):
        """实时统计信息更新的回调"""
        try:
            if stats:
                current_pitch = stats.get('current_pitch', 0)
                if current_pitch > 0:
                    note_name = self.frequency_to_note_name(current_pitch)
                    self.stats_label.setText(f"当前音高: {current_pitch:.1f}Hz ({note_name})")
                else:
                    self.stats_label.setText("当前音高: 检测中...")
        except Exception as e:
            print(f"更新统计信息时出错: {e}")
    
    def on_pitch_detected(self, data):
        """音高检测回调"""
        try:
            # 处理不同的数据格式
            if isinstance(data, dict):
                frequency = data.get('frequency', 0)
                timestamp = data.get('timestamp', 0)
                note_info = data.get('note_info', {})
            elif isinstance(data, (list, tuple)) and len(data) >= 3:
                timestamp, frequency, note_info = data[0], data[1], data[2]
            else:
                # 如果只有频率值
                frequency = float(data) if data else 0
                timestamp = 0
                note_info = {}
            
            # 更新实时显示
            if frequency > 0:
                self.pitch_info_label.setText(f"当前音高: {frequency:.2f} Hz")
                
                if note_info:
                    note_name = note_info.get('note_name', '--')
                    octave = note_info.get('octave', '')
                    cents = note_info.get('cents', 0)
                    
                    self.note_info_label.setText(
                        f"音符: {note_name}{octave} (偏差: {cents:+.0f} cents)"
                    )
                else:
                    # 如果没有音符信息，自己计算
                    note_name = self.frequency_to_note_name(frequency)
                    self.note_info_label.setText(f"音符: {note_name}")
            else:
                self.pitch_info_label.setText("当前音高: -- Hz")
                self.note_info_label.setText("音符: --")
            
            # 发送到五线谱显示器
            if self.staff_widget and frequency > 0:
                self.staff_widget.add_pitch_data(timestamp, frequency, note_info)
                
        except Exception as e:
            print(f"处理音高数据时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def frequency_to_note_name(self, frequency):
        """将频率转换为音符名称"""
        if frequency <= 0:
            return "--"
        
        # 基准音A4 = 440Hz
        A4 = 440.0
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        # 计算相对于A4的半音数
        semitones_from_A4 = 12 * np.log2(frequency / A4)
        
        # 计算音符索引（A = 9）
        note_index = (9 + round(semitones_from_A4)) % 12
        
        # 计算八度
        octave = 4 + (9 + round(semitones_from_A4)) // 12
        
        return f"{notes[note_index]}{octave}"
    
    def update_status(self, message):
        """更新状态显示"""
        try:
            # 可以在这里添加状态栏或日志显示
            print(f"状态: {message}")
            # 如果有状态标签，可以更新它
            # self.status_label.setText(message)
        except Exception as e:
            print(f"更新状态失败: {e}")
    
    def open_recordings_folder(self):
        """打开录音文件夹"""
        try:
            recordings_dir = project_root / "recordings"
            recordings_dir.mkdir(exist_ok=True)
            
            # 使用系统默认程序打开文件夹
            import subprocess
            import platform
            
            if platform.system() == "Windows":
                subprocess.run(["explorer", str(recordings_dir)])
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", str(recordings_dir)])
            else:  # Linux
                subprocess.run(["xdg-open", str(recordings_dir)])
                
        except Exception as e:
            self.log_message(f"打开录音文件夹失败: {e}")
            QMessageBox.warning(self, "警告", f"无法打开录音文件夹: {e}")
    
    def open_standalone_staff_viewer(self):
        """打开独立的五线谱查看器"""
        try:
            from src.analysis.staff_visualizer import StandaloneStaffVisualizer
            
            # 创建独立查看器（这将在新进程中运行）
            self.standalone_viewer = StandaloneStaffVisualizer()
            self.standalone_viewer.show()
            
            self.log_analysis_message("独立五线谱查看器已启动")
            
        except Exception as e:
            self.log_analysis_message(f"启动独立五线谱查看器失败: {e}")
    
    def log_message(self, message):
        """记录消息到录音日志"""
        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        self.recording_log.append(formatted_message)
        self.status_label.setText(message)
    
    def log_analysis_message(self, message):
        """记录消息到分析日志"""
        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        self.analysis_log.append(formatted_message)
        self.status_label.setText(message)

def main():
    """主函数"""
    try:
        if PYQT_VERSION == 6:
            from PyQt6.QtWidgets import QApplication
        else:
            from PyQt5.QtWidgets import QApplication
        
        app = QApplication(sys.argv)
        
        # 设置应用程序信息
        app.setApplicationName("MindEcho")
        app.setApplicationVersion("2.0")
        app.setOrganizationName("MindEcho Team")
        
        # 创建主窗口
        window = EnhancedMindEchoMainWindow()
        window.show()
        
        # 运行应用程序
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"应用程序启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
