"""
MindEcho 集成录音与实时音高分析界面
将录音、音高分析和心电图式可视化集成到一个统一界面
"""

import sys
import os
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class PitchFrame:
    """Phase1: 统一的音高帧结构 (仍通过 to_dict 兼容旧UI)。"""
    timestamp: float
    f0_raw: float
    f0_smooth: float
    confidence: float
    note_info: Optional[Dict[str, Any]]
    has_pitch: bool
    audio_rms: float
    vibrato_info: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'frequency': self.f0_smooth,  # 旧字段名 frequency -> 平滑后的频率
            'raw_frequency': self.f0_raw,
            'confidence': self.confidence,
            'note_info': self.note_info,
            'has_pitch': self.has_pitch,
            'audio_rms': self.audio_rms,
            'vibrato_info': self.vibrato_info
        }
import threading
import numpy as np
from pathlib import Path
from collections import deque
import sounddevice as sd
import wave
import json
import queue  # 添加queue模块，用于异步音频处理
import psutil
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

# HECATE G4 Pro 设备映射和修复
class HecateDeviceMapper:
    """HECATE设备修复映射器 - 基于测试结果的优化配置"""
    
    @staticmethod
    def get_working_hecate_config():
        """获取经过验证的HECATE工作配置"""
        # 基于测试结果：设备33工作稳定，使用固定最优参数
        return {
            'device_id': 33,
            'device_name': '麦克风 (2- HECATE G4 Pro)',
            'samplerate': 192000,
            'blocksize': 32,
            'channels': 1,
            'latency_ms': 0.17,
            'driver_type': 'WASAPI',
            'extra_settings': None,
            'verified': True
        }
    
    @staticmethod
    def verify_hecate_available():
        """验证HECATE设备是否可用"""
        try:
            devices = sd.query_devices()
            
            # 检查设备33是否存在且为HECATE
            if len(devices) > 33:
                device_33 = devices[33]
                device_name = device_33.get('name', '')
                
                if 'HECATE' in device_name or 'G4 Pro' in device_name:
                    return True, device_name
            
            # 查找其他HECATE设备
            for i, device in enumerate(devices):
                device_name = device.get('name', '')
                if 'HECATE' in device_name or 'G4 Pro' in device_name:
                    print(f"🔍 发现HECATE设备 {i}: {device_name}")
                    return True, device_name
            
            return False, "未找到HECATE设备"
            
        except Exception as e:
            return False, f"设备检查失败: {e}"
    
    @staticmethod
    def find_optimal_hecate_device():
        """查找最优HECATE设备配置（简化版，避免先前残余代码破坏结构）"""
        try:
            devices = sd.query_devices()
            priority_devices = [33, 1, 13]
            for device_id in priority_devices:
                if device_id < len(devices):
                    name = devices[device_id].get('name', '')
                    if 'HECATE' in name or 'G4 Pro' in name:
                        return {
                            'device_id': device_id,
                            'device_name': name,
                            'samplerate': 192000 if device_id == 33 else 44100,
                            'blocksize': 32,
                            'channels': 1,
                            'latency_ms': 0.17 if device_id == 33 else 1.0,
                            'driver_type': 'WASAPI',
                            'extra_settings': None,
                            'verified': True
                        }
            return None
        except Exception:
            return None

# 延迟测量器（恢复丢失的类）
class LatencyMeasurer:
    def __init__(self, window_size=200):
        self.timestamps = deque(maxlen=window_size)

    def add_sample(self, value_ms: float):
        self.timestamps.append(value_ms)

    def get_stats(self):
        if not self.timestamps:
            return None
        arr = np.array(self.timestamps)
        return {
            'avg': float(np.mean(arr)),
            'max': float(np.max(arr)),
            'min': float(np.min(arr)),
            'std': float(np.std(arr)),
            'count': int(len(arr))
        }

class AudioProcessor:
    """精简音频处理器（与IntegratedAudioProcessor解耦）"""
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self.alpha = 0.12  # 平滑系数
        self.smooth_state = 0.0

    def fast_smoothing(self, data):
        if len(data) == 0:
            return data
        smoothed = np.zeros_like(data, dtype=np.float32)
        smoothed[0] = self.alpha * data[0] + (1 - self.alpha) * self.smooth_state
        for i in range(1, len(data)):
            smoothed[i] = self.alpha * data[i] + (1 - self.alpha) * smoothed[i-1]
        self.smooth_state = smoothed[-1]
        return smoothed

    def compute_gain(self, audio_chunk):
        rms = np.sqrt(np.mean(np.square(audio_chunk)))
        target_rms = 0.12
        return np.clip(target_rms / (rms + 1e-6), 1.0, 2.5)

    def optimized_audio_process(self, input_data, enable_smooth=True):
        if len(input_data) == 0:
            return np.zeros_like(input_data, dtype=np.float32)  # 处理空输入
        input_rms = np.sqrt(np.mean(np.square(input_data)))
        input_max = np.max(np.abs(input_data))
        if input_rms < 0.001 and input_max < 0.002:
            return np.zeros_like(input_data, dtype=np.float32)
        processed = input_data.copy().astype(np.float32)
        if input_rms < 0.02:
            safe_gain = min(2.0, 0.05 / (input_rms + 1e-6))
            processed = processed * safe_gain
        processed = np.tanh(processed * 0.95) * 0.9
        if enable_smooth and len(processed) > 2:
            smoothed = processed.copy()
            for i in range(1, len(smoothed)-1):
                smoothed[i] = processed[i] * 0.7 + processed[i-1] * 0.15 + processed[i+1] * 0.15
            processed = smoothed
        processed = np.clip(processed, -0.8, 0.8)
        return processed

# 系统优化工具
def set_realtime_priority():
    """设置进程为实时优先级"""
    try:
        p = psutil.Process(os.getpid())
        if sys.platform == "win32":
            p.nice(psutil.HIGH_PRIORITY_CLASS)
        else:
            p.nice(-10)  # Unix系统
        print("🚀 已设置高优先级")
        return True
    except Exception as e:
        print(f"⚠️ 设置优先级失败: {e}")
        return False

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
                                 QScrollBar, QDialog, QMenu)
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QMetaObject, pyqtSlot
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

# 统一音高检测服务（Phase1）
try:
    from src.audio_processing.pitch_service import PitchDetectionService
    _PITCH_SERVICE_AVAILABLE = True
except Exception as _e:
    print(f"⚠️ PitchDetectionService 不可用: {_e}")
    _PITCH_SERVICE_AVAILABLE = False

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

        # 基础状态控制变量
        self.is_recording = False
        self.should_save = False
        self.recording_filename = None
        self.is_audio_processing = False
        self.is_global_monitoring_active = False
        self.is_monitoring_only = False
        # 可视化控制：录音分析时 True，纯监听 False
        self.enable_pitch_visualization = False
        
        # 🔥 关键修复：初始化音频队列
        self.audio_buffer_queue = queue.Queue(maxsize=100)  # 音频数据队列
        self.processing_queue = queue.Queue(maxsize=50)     # 处理队列
        self.audio_buffer = []
        self.pitch_history = deque(maxlen=1000)  # 保存最近1000个音高点
        
        print("🔥 关键修复：基础状态变量已初始化")
        
        # �🚀 专业级音频设备配置（Windows优化）
        print("🎵 正在配置专业级音频处理器...")
        self._configure_professional_audio_settings()
        
        # 录音参数 - 终极超低延迟配置
        self.sample_rate = 96000  # 🚀 96kHz超高采样率，提升时间分辨率
        self.channels = 1
        self.chunk_size = 32      # 🎵 终极小块（理论延迟0.33ms @96kHz）
        
        # 🔥 初始化性能优化工具
        self.audio_processor = AudioProcessor(sample_rate=96000)  # 🚀 使用96kHz处理器
        self.latency_measurer = LatencyMeasurer(window_size=200)
        
        # 🔥 设置系统优先级
        set_realtime_priority()
        
        # 🎯 实时延迟监控
        self._latency_monitor_counter = 0
        self._last_latency_report_time = time.time()
        self._processing_times = []
        
        # 音频缓冲区管理器 - 解决input overflow问题
        # self.audio_buffer_queue = queue.Queue(maxsize=100)  # 🔥 已在上方初始化
        # self.processing_queue = queue.Queue(maxsize=50)     # 🔥 已在上方初始化
        self.buffer_overflow_count = 0
        self.total_audio_frames = 0

        # ===== 统一日志 RateLimiter =====
        class _RateLimiter:
            def __init__(self):
                self.state = {}
            def allow(self, key: str, interval: float, burst: int = 1):
                now = time.time()
                st = self.state.get(key, {'next': 0.0, 'remain': burst})
                if now >= st['next']:
                    st['next'] = now + interval
                    st['remain'] = burst - 1
                    self.state[key] = st
                    return True
                if st['remain'] > 0:
                    st['remain'] -= 1
                    self.state[key] = st
                    return True
                return False
        self._rate_limiter = _RateLimiter()
        def _log_rate_limit(key: str, msg: str, interval: float = 0.6, burst: int = 1):
            if self._rate_limiter.allow(key, interval, burst):
                try:
                    print(msg)
                except Exception:
                    pass
        self._log_rate_limit = _log_rate_limit
        # Scroll日志去重签名
        self._last_scroll_signature = None
        self._last_scroll_log_time = 0.0
        # 歌声保护防抖状态
        self._over_suppress_counter = 0
        self._suppress_cooldown_until = 0.0
        # 监听自然模式：尽量保留呼吸质感
        self.monitor_natural_mode = True
        # 自然耳返强度（0.0~1.0）：0 最原味，1 最强自然化抑制（默认 0.6）
        self.natural_earback_strength = 0.6
        # RAW直通模式（最小处理，保持原味，仅做安全限幅）
        self.monitor_raw_mode = False
        # 耳返头房（dB），用于避免瞬态削波（与VRMS限幅配合）。谨慎设置，默认-6dB。
        self.headroom_db = -6.0
        # VRMS限幅器状态
        self._vrms_state = {}

        # ===== 调试标志（处理线程本地）=====
        # 防止在回调中访问 self.debug_flags 抛出 AttributeError
        # 仅包含本线程实际使用的键；可与可视化器的 debug_flags 独立
        self.debug_flags = {
            'latency_warn_verbose': True,     # 输出延迟警告详细信息
            'vocal_protect_verbose': True,    # 输出声带保护逻辑细节（若实现）
            'summary_enabled': True,          # 周期性统计汇总
            'perf_verbose': False,            # 额外性能日志（默认关闭）
            'display_diag': False,            # 显示层诊断（处理线程中通常不用）
            'segment_log': False              # 分段调试（处理线程中通常不用）
        }
        # 🔧 统计计数器（回调中引用，避免 AttributeError）
        self._stat_counters = {
            'vocal_protect': 0,
            'high_latency': 0,
            'segments_recomputed': 0,
            'segment_cache_hits': 0
        }
        # 兼容性保障：若后续代码仍直接访问 self.debug_flags.get(...) 则不会再报错

        # （Visualizer 相关参数应在 ECGStylePitchVisualizer 内部，不应出现在此处）

        # 状态控制 - 🔥 已在上方初始化
        # self.is_recording = False
        # self.should_save = False
        # self.recording_filename = None
        
        # 🚀 零延迟优化组件
        self.audio_processing_thread = None
        self.zero_copy_enabled = True
        self.memory_pool = None
        self.preallocated_buffers = {}
        
        # 🎯 独立音频处理线程配置
        self.dedicated_audio_thread = None
        self.audio_queue = queue.Queue(maxsize=10)  # 小队列，减少延迟
        self.processing_lock = threading.Lock()
        
        # 🔥 零拷贝内存管理
        self._init_memory_pool()
        
        # 启动专用音频处理线程
        self._start_dedicated_audio_thread()
        
        # 音频数据存储 - 🔥 已在上方初始化
        # self.audio_buffer = []
        self.audio_stream = None
        
        # 异步音频处理线程 - 🔥 已在上方初始化
        self.audio_processing_thread = None
        # self.is_audio_processing = False
        
        # 颤音检测相关 - 🔥 pitch_history已在上方初始化
        # self.pitch_history = deque(maxlen=300)  # 增加历史长度，支持颤音检测
        self.vibrato_detection_window = 60      # 颤音检测窗口
        self.vibrato_threshold = 2.0            # 颤音深度阈值(Hz)

        # 🎯 可配置的频率范围设置
        self.min_frequency = 80     # 最低检测频率（可通过界面调整）
        self.max_frequency = 1047   # 最高检测频率（C6，可通过界面调整）

        # 音高分析器
        self.pitch_analyzer = None
        self.overlapping_analyzer = None
        # 统一音高检测服务实例
        self.pitch_service = None

        # 🔥 关键修复：降噪处理器初始化 - 设置为温和模式
        try:
            from src.audio_processing.noise_reduction import NoiseReductionProcessor
            self.noise_processor = NoiseReductionProcessor(sample_rate=44100, frame_size=2048)
            # 🔥 关键修复：设置降噪为温和模式，避免过度抑制歌声
            if hasattr(self.noise_processor, 'set_noise_reduction_mode'):
                self.noise_processor.set_noise_reduction_mode("轻度")  # 使用轻度降噪模式
                print("✅ IntegratedAudioProcessor: 降噪处理器设置为轻度模式")
            print("✅ IntegratedAudioProcessor: 降噪处理器初始化成功")
        except ImportError as e:
            print(f"❌ IntegratedAudioProcessor: 降噪处理器初始化失败: {e}")
            self.noise_processor = None

        # 🔥 初始化电流音检测器
        self.electric_noise_detector = {
            'enabled': True,
            'threshold': 2.0,
            'consecutive_count': 0,
            'last_detection_time': 0,
            'rms_threshold': 0.0008,
            'high_freq_ratio_threshold': 0.95
        }
        print("✅ IntegratedAudioProcessor: 电流音检测器初始化完成")

        # 🎤 优化的智能音量增强配置（大音量/高音优化）
        self.intelligent_volume_booster = {
            'enabled': True,
            'base_gain': 1.0,           # 基础增益
            'max_gain': 1.2,            # 温和的最大增益（1.6dB，避免失真）
            'noise_gate_threshold': 0.002, # 合理的噪声门限
            'auto_gain_speed': 0.015,   # 平衡的调整速度
            'target_level': 0.18,       # 适中目标音量
            'voice_freq_boost': 1.0,    # 关闭频段增强（避免失真）
            'current_gain': 1.0,        # 当前增益
            'rms_history': [],          # RMS历史（减少历史长度）
            'gain_smoothing': 0.975,    # 高平滑系数（稳定性优先）
            'gain_change_limit': 0.015, # 严格增益变化限制
            'stability_buffer': 0.04,   # 适中稳定缓冲区
            'manual_volume': 1.0,       # 🎚️ 手动音量控制
            'manual_control_enabled': False,  # 🎚️ 手动控制默认禁用
            'quality_priority': True,   # 🎵 音质优先模式
            'gentle_enhancement': True, # 🎵 温和增强模式
            'high_volume_fast_response': True, # � 大音量快速响应
            'bypass_on_transients': False,     # 🎯 关闭瞬态绕过（避免音质问题）
            'optimize_for_vocals': True        # 🎵 针对人声优化
        }

        # 实时统计 - 🔥 pitch_history已在上方初始化
        # self.pitch_history = deque(maxlen=1000)  # 保存最近1000个音高点
        self.recording_start_time = None
        self.current_duration = 0

        # 性能相关属性
        self.use_gpu_acceleration = False
        self.performance_config = None
        self.gpu_processor = None

        # 尝试初始化GPU处理器
        try:
            from src.audio_processing.gpu_accelerator import GPUAcceleratedProcessor
            self.gpu_processor = GPUAcceleratedProcessor(self.sample_rate)
            if self.gpu_processor.is_gpu_available():
                print("✅ IntegratedAudioProcessor: GPU加速器可用")
            else:
                print("ℹ️ IntegratedAudioProcessor: GPU加速器不可用，使用CPU")
        except ImportError:
            print("ℹ️ IntegratedAudioProcessor: GPU加速器未安装")
            self.gpu_processor = None

        # 🎯 加载用户首选设备配置
        self._load_user_preferred_device()
        # 初始化统一音高服务（懒加载保证安全）
        try:
            if _PITCH_SERVICE_AVAILABLE:
                _mn = getattr(self, 'current_performance_mode', None)
                _mode_name = str(getattr(_mn, 'name', 'BALANCED'))
                self.pitch_service = PitchDetectionService(
                    sample_rate=float(self.sample_rate),
                    min_frequency=float(self.min_frequency),
                    max_frequency=float(self.max_frequency),
                    yin_threshold=float(getattr(self, 'yin_threshold', 0.12)),
                    mode_name=_mode_name
                )
                print("✅ PitchDetectionService 初始化完成")
        except Exception as _e:
            print(f"⚠️ PitchDetectionService 初始化失败: {_e}")
    
    def _load_user_preferred_device(self):
        """加载用户首选设备配置"""
        try:
            import json
            import os
            
            config_file = os.path.join(os.path.expanduser("~"), ".mindecho", "preferred_device.json")
            
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    preferred_config = json.load(f)
                
                # 验证设备是否仍然可用
                if self._verify_device_availability(preferred_config.get('device')):
                    self._selected_device_config = preferred_config
                    print(f"✅ 已加载首选设备: {preferred_config.get('name', 'Unknown')}")
                    print(f"   设备{preferred_config.get('device')}@{preferred_config.get('samplerate')}Hz/{preferred_config.get('blocksize')}样本")
                else:
                    print(f"⚠️ 首选设备不再可用，将使用智能自动选择")
                    self._selected_device_config = None
            else:
                print("📝 没有找到首选设备配置，将使用智能自动选择")
                self._selected_device_config = None
                
        except Exception as e:
            print(f"⚠️ 加载首选设备配置失败: {e}")
            self._selected_device_config = None
            
        
    def diagnose_wasapi_issues(self):
        """🔧 WASAPI问题诊断和系统优化"""
        try:
            import sounddevice as sd
            print("🔍 开始WASAPI系统诊断...")
            
            # 1. 检查音频服务状态
            try:
                import subprocess
                result = subprocess.run(['sc', 'query', 'Audiosrv'], 
                                      capture_output=True, text=True, timeout=5)
                if 'RUNNING' in result.stdout:
                    print("✅ Windows音频服务运行正常")
                else:
                    print("⚠️ Windows音频服务状态异常，建议重启服务")
            except Exception as service_error:
                print(f"⚠️ 无法检查音频服务状态: {service_error}")
            
            # 2. 检查sounddevice版本和WASAPI支持
            try:
                print(f"📦 sounddevice版本: {sd.__version__}")
                
                # 检查PortAudio版本和WASAPI支持
                info = sd.query_hostapis()
                wasapi_found = False
                for api in info:
                    if 'WASAPI' in api['name']:
                        print(f"✅ 发现WASAPI API: {api['name']} (设备数: {api['device_count']})")
                        wasapi_found = True
                
                if not wasapi_found:
                    print("❌ 未找到WASAPI支持，请检查PortAudio安装")
                
            except Exception as version_error:
                print(f"⚠️ 版本检查失败: {version_error}")
            
            # 3. 设备兼容性分析和智能过滤
            try:
                devices = sd.query_devices()
                hecate_devices = []
                problematic_devices = []
                valid_input_devices = []
                
                print("🔍 智能设备过滤和分析:")
                
                for i, device in enumerate(devices):
                    device_name = device.get('name', '')
                    max_input_channels = device.get('max_input_channels', 0)
                    max_output_channels = device.get('max_output_channels', 0)
                    host_api = device.get('hostapi', -1)
                    
                    if 'HECATE' in device_name or 'G4 Pro' in device_name:
                        hecate_devices.append((i, device))
                        
                        # 智能过滤：只处理有输入通道的设备
                        if max_input_channels > 0:
                            valid_input_devices.append((i, device))
                            print(f"✅ 有效输入设备{i}: {device_name}")
                            print(f"   ├─ 输入通道: {max_input_channels}")
                            print(f"   ├─ 默认采样率: {device.get('default_samplerate', 0)}Hz")
                            print(f"   └─ 主机API: {host_api}")
                            
                            # 预测试设备兼容性
                            compatibility_issues = []
                            
                            # 检查采样率兼容性
                            default_rate = device.get('default_samplerate', 44100)
                            if default_rate > 96000:
                                compatibility_issues.append("高采样率可能不稳定")
                            
                            # 检查主机API类型
                            if host_api == 0:  # MME
                                compatibility_issues.append("MME API - 延迟较高但兼容性好")
                            elif host_api == 1:  # DirectSound
                                compatibility_issues.append("DirectSound - 平衡的性能和兼容性")
                            elif host_api == 2:  # WASAPI
                                compatibility_issues.append("WASAPI - 低延迟但可能有兼容性问题")
                            
                            if compatibility_issues:
                                print(f"   ⚠️ 预测问题: {'; '.join(compatibility_issues)}")
                            
                            # 智能测试基本连接
                            test_configs = [
                                # 配置1：保守配置（最高兼容性）
                                {
                                    'device': i,
                                    'channels': 1,  # 强制单声道
                                    'samplerate': 44100,  # 标准采样率
                                    'blocksize': 1024,  # 大缓冲区
                                    'dtype': 'float32',
                                    'name': '保守配置'  # 仅用于日志，不传给InputStream
                                },
                                # 配置2：动态通道配置
                                {
                                    'device': i,
                                    'channels': min(max_input_channels, 2),  # 动态通道数
                                    'samplerate': min(int(default_rate), 48000),  # 限制采样率
                                    'blocksize': 512,
                                    'dtype': 'float32',
                                    'name': '动态配置'  # 仅用于日志，不传给InputStream
                                }
                            ]
                            
                            working_configs = []
                            for config in test_configs:
                                try:
                                    # 移除仅日志用键，避免 0.5.x 版本 sounddevice 不支持 'name' 形参
                                    stream_args = {k: v for k, v in config.items() if k != 'name'}
                                    # 额外安全：校验通道数不超过设备最大输入通道
                                    if stream_args['channels'] > max_input_channels:
                                        print(f"   ❌ {config['name']}通道数超出设备支持: {stream_args['channels']} > {max_input_channels}")
                                        raise ValueError("channels_not_supported")
                                    test_stream = sd.InputStream(**stream_args)
                                    test_stream.close()
                                    working_configs.append(config)
                                    print(f"   ✅ {config['name']}测试通过")
                                except Exception as test_error:
                                    print(f"   ❌ {config['name']}测试失败: {test_error}")
                            
                            if not working_configs:
                                problematic_devices.append((i, device, "所有基础配置都失败"))
                        else:
                            print(f"⚠️ 跳过输出设备{i}: {device_name} (无输入通道)")
                
                print(f"📊 发现{len(valid_input_devices)}个有效HECATE输入设备")
                
                # 4. 智能修复建议生成
                if problematic_devices:
                    print("\n🔧 智能问题诊断和修复建议:")
                    for device_id, device, issue in problematic_devices:
                        device_name = device.get('name', 'Unknown')
                        host_api = device.get('hostapi', -1)
                        
                        print(f"\n设备{device_id} ({device_name}):")
                        print(f"   问题: {issue}")
                        
                        # 基于主机API的特定建议
                        if host_api == 0:  # MME
                            print("   建议: 1) MME驱动较老，考虑更新音频驱动")
                            print("        2) 增加缓冲区大小到2048样本")
                        elif host_api == 1:  # DirectSound  
                            print("   建议: 1) DirectSound通常稳定，检查设备是否被占用")
                            print("        2) 尝试关闭其他音频应用程序")
                        elif host_api == 2:  # WASAPI
                            print("   建议: 1) WASAPI严格，检查Windows音频独占模式设置")
                            print("        2) 在控制面板中禁用'允许应用程序独占控制此设备'")
                            print("        3) 尝试以管理员身份运行程序")
                        
                        # 基于采样率的建议
                        default_rate = device.get('default_samplerate', 44100)
                        if default_rate > 96000:
                            print(f"   建议: 4) 设备默认{default_rate}Hz过高，在Windows声音设置中")
                            print(f"           降低到48000Hz或44100Hz")
                        
                        # 通道数建议
                        max_channels = device.get('max_input_channels', 0)
                        if max_channels == 0:
                            print("   建议: 5) 此设备无输入通道，可能是输出专用设备")
                        elif max_channels > 2:
                            print(f"   建议: 6) 设备支持{max_channels}通道，尝试使用立体声(2通道)")
                
                # 5. 生成最佳实践配置
                if valid_input_devices:
                    print("\n🎯 推荐的最佳实践配置:")
                    
                    best_device = None
                    best_score = 0
                    
                    for device_id, device in valid_input_devices:
                        score = 0
                        device_name = device.get('name', '')
                        host_api = device.get('hostapi', -1)
                        default_rate = device.get('default_samplerate', 44100)
                        max_channels = device.get('max_input_channels', 1)
                        
                        # 评分系统
                        if '麦克风' in device_name:  # 优先麦克风设备
                            score += 50
                        if host_api == 1:  # DirectSound平衡
                            score += 30
                        elif host_api == 2:  # WASAPI性能好但兼容性差
                            score += 20
                        elif host_api == 0:  # MME兼容性好
                            score += 10
                        
                        if 44100 <= default_rate <= 48000:  # 标准采样率
                            score += 20
                        elif default_rate <= 96000:
                            score += 10
                        
                        if max_channels >= 2:  # 支持立体声
                            score += 10
                        
                        if score > best_score:
                            best_score = score
                            best_device = (device_id, device)
                    
                    if best_device:
                        device_id, device = best_device
                        print(f"🏆 最佳设备: 设备{device_id} - {device.get('name', '')}")
                        print(f"   评分: {best_score}/100")
                        print(f"   推荐配置:")
                        print(f"   ├─ 采样率: 44100Hz (稳定)")
                        print(f"   ├─ 通道数: 1 (单声道，兼容性最佳)")
                        print(f"   ├─ 缓冲区: 512样本 (平衡延迟和稳定性)")
                        print(f"   └─ 数据类型: float32")
                
                # 6. 系统级优化建议
                print("\n🚀 系统级WASAPI优化建议:")
                print("   Windows音频设置优化:")
                print("   ├─ 1. 打开'控制面板' → '声音'")
                print("   ├─ 2. 选择HECATE设备 → '属性' → '高级'")
                print("   ├─ 3. 取消勾选'允许应用程序独占控制此设备'")
                print("   ├─ 4. 设置默认格式为'16位，44100Hz'或'16位，48000Hz'")
                print("   ├─ 5. 禁用所有音频增强效果")
                print("   └─ 6. 重启Windows音频服务: 'net stop Audiosrv && net start Audiosrv'")
                
                print("\n   HECATE驱动优化:")
                print("   ├─ 1. 确保使用最新的HECATE官方驱动")
                print("   ├─ 2. 在HECATE控制软件中禁用特效和增强")
                print("   ├─ 3. 设置为'游戏模式'或'低延迟模式'")
                print("   └─ 4. 重启计算机让设置生效")
                
            except Exception as diag_error:
                print(f"❌ 智能设备兼容性分析失败: {diag_error}")
                import traceback
                traceback.print_exc()
                
            print("🔍 WASAPI智能诊断完成")
            
        except Exception as e:
            print(f"❌ WASAPI诊断失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _calculate_device_priority(self, device_info):
        """计算设备优先级评分（用于智能设备选择）"""
        try:
            score = 0
            device_name = device_info.get('name', '').lower()
            host_api = device_info.get('hostapi', -1)
            default_samplerate = device_info.get('default_samplerate', 44100)
            max_input_channels = device_info.get('max_input_channels', 0)
            
            # 设备名称评分
            if '麦克风' in device_name or 'microphone' in device_name:
                score += 50  # 明确的麦克风设备优先级最高
            elif 'hecate' in device_name and 'g4 pro' in device_name:
                score += 40  # HECATE G4 Pro设备
            elif 'hecate' in device_name:
                score += 30  # 其他HECATE设备
            
            # 主机API评分
            if host_api == 1:  # DirectSound - 平衡性能和兼容性
                score += 25
            elif host_api == 2:  # WASAPI - 低延迟但兼容性可能有问题
                score += 20
            elif host_api == 0:  # MME - 兼容性好但延迟高
                score += 15
            
            # 采样率评分（偏向标准采样率）
            if 44100 <= default_samplerate <= 48000:
                score += 20  # 标准采样率最佳
            elif 48000 < default_samplerate <= 96000:
                score += 15  # 高采样率可接受
            elif default_samplerate > 96000:
                score += 5   # 过高采样率可能有问题
            else:
                score += 10  # 低采样率
            
            # 输入通道数评分
            if max_input_channels == 2:
                score += 15  # 立体声输入理想
            elif max_input_channels == 1:
                score += 10  # 单声道可用
            elif max_input_channels > 2:
                score += 8   # 多通道输入可用但可能过度
            
            return score
            
        except Exception as e:
            print(f"⚠️ 设备优先级计算失败: {e}")
            return 0
    
    def _generate_smart_device_configs(self, device_id, max_channels, device_samplerate, host_api, callback):
        """为设备生成智能配置序列（从最兼容到最高性能）"""
        try:
            configs = []
            
            # 智能通道数选择
            safe_channels = min(max_channels, 2) if max_channels > 0 else 1
            
            # 智能采样率选择
            safe_samplerates = [44100, 48000]
            if device_samplerate <= 96000:
                safe_samplerates.extend([int(device_samplerate)])
            safe_samplerates = sorted(list(set(safe_samplerates)))  # 去重并排序
            
            # 配置1：最高兼容性（单声道 + 44100Hz + 大缓冲区）
            configs.append({
                'device': device_id,
                'channels': 1,
                'samplerate': 44100,
                'blocksize': 1024,
                'callback': callback,
                'dtype': np.float32,
                'name': f'设备{device_id}最高兼容性'
            })
            
            # 配置2：标准配置（设备通道数 + 标准采样率）
            configs.append({
                'device': device_id,
                'channels': safe_channels,
                'samplerate': safe_samplerates[0],  # 最安全的采样率
                'blocksize': 512,
                'callback': callback,
                'dtype': np.float32,
                'latency': 'low',
                'name': f'设备{device_id}标准配置'
            })
            
            # 配置3：优化配置（如果有更高的采样率可用）
            if len(safe_samplerates) > 1:
                configs.append({
                    'device': device_id,
                    'channels': safe_channels,
                    'samplerate': safe_samplerates[-1],  # 最高的安全采样率
                    'blocksize': 256,
                    'callback': callback,
                    'dtype': np.float32,
                    'latency': 'low',
                    'name': f'设备{device_id}优化配置'
                })
            
            # 配置4：WASAPI配置（仅对WASAPI主机API）
            if host_api == 2:  # WASAPI
                configs.append({
                    'device': device_id,
                    'channels': safe_channels,
                    'samplerate': min(safe_samplerates[-1], 48000),  # WASAPI用保守采样率
                    'blocksize': 256,
                    'callback': callback,
                    'dtype': np.float32,
                    'latency': 'low',
                    'extra_settings': sd.WasapiSettings(exclusive=False),
                    'name': f'设备{device_id}WASAPI共享'
                })
            
            return configs
            
        except Exception as e:
            print(f"⚠️ 智能配置生成失败: {e}")
            # 返回最基础的配置
            return [{
                'device': device_id,
                'channels': 1,
                'samplerate': 44100,
                'blocksize': 1024,
                'callback': callback,
                'dtype': np.float32,
                'name': f'设备{device_id}基础配置'
            }]
    
    def _handle_device_error(self, error, config_name, device_id, config):
        """增强的设备错误处理"""
        try:
            error_msg = str(error)
            print(f"   ❌ {config_name}失败: {error_msg}")
            
            # 分析具体错误并给出建议
            if 'PaErrorCode -9984' in error_msg:
                print(f"      🔍 主机API不兼容错误")
                print(f"      💡 建议：设备{device_id}的WASAPI设置与主机API不匹配")
            elif 'PaErrorCode -9998' in error_msg:
                print(f"      🔍 通道数错误 - 可能是输出设备或通道数设置错误")
                print(f"      💡 建议：设备{device_id}可能不支持{config.get('channels', '未知')}声道输入")
            elif 'PaErrorCode -9997' in error_msg:
                print(f"      🔍 采样率不支持 - {config.get('samplerate', '未知')}Hz")
                print(f"      💡 建议：设备{device_id}不支持此采样率，尝试44100Hz")
            elif 'PaErrorCode -9999' in error_msg:
                print(f"      🔍 端点类型错误 - WASAPI配置问题")
                print(f"      💡 建议：移除WASAPI设置或检查设备权限")
            elif 'PaErrorCode -9996' in error_msg:
                print(f"      🔍 设备失效 - 可能被占用或断开")
                print(f"      💡 建议：检查设备{device_id}是否被其他程序使用")
            else:
                print(f"      🔍 未知错误类型: {error_msg[:100]}...")
                
        except Exception as handle_error:
            print(f"      ⚠️ 错误处理失败: {handle_error}")
    
    def _load_user_preferred_device(self):
        """加载用户首选设备配置"""
        try:
            import json
            import os
            
            config_file = os.path.join(os.path.expanduser("~"), ".mindecho", "preferred_device.json")
            
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 验证设备是否仍然可用
                if self._verify_device_availability(config.get('device')):
                    self._selected_device_config = config
                    print(f"✅ 已加载首选设备配置: {config.get('name', 'Unknown')}")
                    print(f"   配置: {config.get('samplerate', 0)}Hz / {config.get('blocksize', 0)}样本")
                else:
                    print("⚠️ 首选设备配置中的设备不可用，将使用自动检测")
                    # 删除无效的配置文件
                    try:
                        os.remove(config_file)
                        print("🗑️ 已清理无效的设备配置文件")
                    except:
                        pass
            else:
                print("📝 没有找到首选设备配置，将使用智能自动选择")
                
        except Exception as e:
            print(f"⚠️ 加载首选设备配置失败: {e}")
            self._selected_device_config = None
    
    def _configure_professional_audio_settings(self):
        """配置专业级音频设备设置（Windows ASIO/WASAPI优化）"""
        try:
            print("🔧 正在配置专业音频设备设置...")
            
            # 🎯 检测可用的专业音频设备
            devices = sd.query_devices()
            self.audio_device_info = {
                'asio_devices': [],
                'wasapi_devices': [],
                'directsound_devices': [],
                'recommended_device': None,
                'native_sample_rates': [],
                'wasapi_input_devices': [],  # 专门存储WASAPI输入设备
                'wasapi_output_devices': []  # 专门存储WASAPI输出设备
            }
            
            # 分类音频设备并动态获取WASAPI设备索引
            for i, device in enumerate(devices):
                device_name = str(device.get('name', '')).upper()
                max_inputs = device.get('max_input_channels', 0)
                max_outputs = device.get('max_output_channels', 0)
                default_sr = device.get('default_samplerate', 44100)
                
                device_info = {
                    'index': i,
                    'name': device.get('name', 'Unknown'),
                    'inputs': max_inputs,
                    'outputs': max_outputs,
                    'sample_rate': default_sr,
                    'device': device
                }
                
                # WASAPI设备检测（第二优先级）- 更准确的检测方法
                if device.get('hostapi', 0) == 2:  # hostapi=2 是WASAPI
                    self.audio_device_info['wasapi_devices'].append(device_info)
                    print(f"🔊 检测到WASAPI设备: {device.get('name')} (索引{i}, {max_inputs}输入/{max_outputs}输出@{default_sr}Hz)")
                    
                    # 分别存储输入和输出设备
                    if max_inputs > 0:
                        self.audio_device_info['wasapi_input_devices'].append(device_info)
                        # 检测特定设备
                        if 'HECATE' in device_name and 'G4' in device_name:
                            print(f"🎧 找到HECATE G4 Pro输入设备: 索引{i}")
                        elif 'REALTEK' in device_name:
                            print(f"🔊 找到Realtek输入设备: 索引{i}")
                    
                    if max_outputs > 0:
                        self.audio_device_info['wasapi_output_devices'].append(device_info)
                
                # ASIO设备检测（最高优先级）
                elif 'ASIO' in device_name or max_inputs > 8:
                    self.audio_device_info['asio_devices'].append(device_info)
                    print(f"🎧 检测到ASIO设备: {device.get('name')} ({max_inputs}输入/{max_outputs}输出@{default_sr}Hz)")
                
                # DirectSound设备（第三优先级）
                elif max_inputs > 0:
                    self.audio_device_info['directsound_devices'].append(device_info)
            
            # 🚀 设置推荐设备和采样率
            if self.audio_device_info['asio_devices']:
                recommended = self.audio_device_info['asio_devices'][0]
                self.audio_device_info['recommended_device'] = recommended
                # ASIO设备通常支持48kHz或96kHz
                native_rates = [48000, 96000, 192000, 44100]
                print(f"✅ 推荐设备: {recommended['name']} (ASIO专业级)")
            elif self.audio_device_info['wasapi_devices']:
                recommended = self.audio_device_info['wasapi_devices'][0]
                self.audio_device_info['recommended_device'] = recommended
                # WASAPI设备通常支持44.1kHz或48kHz
                native_rates = [48000, 44100, 96000]
                print(f"✅ 推荐设备: {recommended['name']} (WASAPI独占)")
            else:
                # 使用默认设备
                native_rates = [44100, 48000]
                print("📡 使用系统默认设备 (DirectSound兼容)")
            
            self.audio_device_info['native_sample_rates'] = native_rates
            
            # 🎯 优化采样率选择（使用设备原生采样率）
            if hasattr(self, 'sample_rate'):
                if self.sample_rate not in native_rates:
                    old_rate = self.sample_rate
                    self.sample_rate = native_rates[0]  # 使用第一个推荐采样率
                    print(f"🔄 采样率优化: {old_rate}Hz → {self.sample_rate}Hz (设备原生)")
                else:
                    print(f"✅ 采样率匹配: {self.sample_rate}Hz (设备原生支持)")
            
            # 🚀 配置缓冲区大小建议
            self._configure_optimal_buffer_size()
            
            print("🎵 专业音频设备配置完成")
            
        except Exception as e:
            print(f"⚠️ 专业音频设备配置失败: {e}")
            print("📡 将使用默认音频配置")
    
    def _configure_optimal_buffer_size(self):
        """配置最优缓冲区大小"""
        try:
            # 根据设备类型推荐缓冲区大小
            if self.audio_device_info['asio_devices']:
                # ASIO设备：超低延迟
                suggested_sizes = [32, 64, 128]  # 0.67-2.67ms @48kHz
                print("🎯 ASIO设备缓冲区建议: 32-128样本 (0.67-2.67ms @48kHz)")
            elif self.audio_device_info['wasapi_devices']:
                # WASAPI设备：低延迟
                suggested_sizes = [64, 128, 256]  # 1.33-5.33ms @48kHz
                print("🎯 WASAPI设备缓冲区建议: 64-256样本 (1.33-5.33ms @48kHz)")
            else:
                # DirectSound设备：稳定优先
                suggested_sizes = [128, 256, 512]  # 2.67-10.67ms @48kHz
                print("🎯 DirectSound设备缓冲区建议: 128-512样本 (2.67-10.67ms @48kHz)")
            
            # 验证当前chunk_size是否合理
            if hasattr(self, 'chunk_size'):
                if self.chunk_size not in suggested_sizes:
                    old_size = self.chunk_size
                    self.chunk_size = suggested_sizes[0]  # 使用最小建议值
                    theoretical_latency = (self.chunk_size / self.sample_rate) * 1000
                    print(f"🔄 缓冲区优化: {old_size} → {self.chunk_size}样本 ({theoretical_latency:.2f}ms延迟)")
                else:
                    theoretical_latency = (self.chunk_size / self.sample_rate) * 1000
                    print(f"✅ 缓冲区匹配: {self.chunk_size}样本 ({theoretical_latency:.2f}ms延迟)")
            
        except Exception as e:
            print(f"⚠️ 缓冲区配置失败: {e}")
    
    def _get_wasapi_device_by_name(self, device_name_pattern, prefer_inputs=True):
        """根据设备名称模式动态获取WASAPI设备索引"""
        try:
            if not hasattr(self, 'audio_device_info'):
                return None
            
            # 优先从输入设备中查找
            search_list = self.audio_device_info.get('wasapi_input_devices', []) if prefer_inputs else self.audio_device_info.get('wasapi_output_devices', [])
            
            for device_info in search_list:
                device_name = device_info['name'].upper()
                if device_name_pattern.upper() in device_name:
                    return device_info
            
            # 如果没找到，从所有WASAPI设备中查找
            for device_info in self.audio_device_info.get('wasapi_devices', []):
                device_name = device_info['name'].upper()
                if device_name_pattern.upper() in device_name:
                    if prefer_inputs and device_info['inputs'] > 0:
                        return device_info
                    elif not prefer_inputs and device_info['outputs'] > 0:
                        return device_info
            
            return None
        except Exception as e:
            print(f"⚠️ WASAPI设备查找失败: {e}")
            return None
    
    def _get_optimal_wasapi_configs(self):
        """动态生成最优WASAPI配置 - 智能设备发现版本"""
        configs = []
        
        try:
            # 确保sounddevice模块可用
            import sounddevice as sd
            
            print("🔍 智能发现最佳WASAPI设备...")
            
            # 首先尝试加载已验证的最佳配置
            optimal_config = self._load_verified_optimal_config()
            if optimal_config:
                configs.append(optimal_config)
                print(f"✅ 加载已验证最佳配置: {optimal_config['name']}")
            
            # 获取所有输入设备
            devices = sd.query_devices()
            device_rankings = []
            
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    # 计算设备质量评分
                    score = self._calculate_device_quality_score(device)
                    device_rankings.append({
                        'id': i,
                        'name': device['name'],
                        'score': score,
                        'sample_rate': int(device['default_samplerate']),
                        'channels': device['max_input_channels'],
                        'hostapi': sd.query_hostapis()[device['hostapi']]['name']
                    })
            
            # 🎯 特殊处理HECATE设备：验证可用性，过滤无效设备
            verified_devices = []
            for device in device_rankings:
                if 'hecate' in device['name'].lower() and 'g4 pro' in device['name'].lower():
                    # HECATE设备需要严格验证
                    print(f"🎧 验证HECATE设备{device['id']}: {device['name']}")
                    if self._verify_device_availability(device['id']):
                        verified_devices.append(device)
                        print(f"✅ HECATE设备{device['id']}验证成功，支持{device['sample_rate']}Hz")
                    else:
                        print(f"❌ 跳过无效HECATE设备{device['id']}")
                else:
                    # 非HECATE设备使用简单验证
                    verified_devices.append(device)
            
            # 按评分排序，HECATE设备优先
            verified_devices.sort(key=lambda x: (1 if 'hecate' in x['name'].lower() else 0, x['score']), reverse=True)
            top_devices = verified_devices[:3]
            
            print(f"🏆 发现 {len([d for d in top_devices if 'hecate' in d['name'].lower()])} 个可用HECATE设备:")
            for device in top_devices:
                device_type = "🎧 HECATE G4 Pro" if 'hecate' in device['name'].lower() else "🎤 通用设备"
                print(f"   {device_type}: {device['name']} (设备{device['id']}, 评分: {device['score']}/100)")
            
            # 为每个验证通过的设备生成多种配置
            for device in top_devices:
                device_configs = self._generate_device_wasapi_configs(device)
                configs.extend(device_configs)
                
            # 按预期延迟排序
            configs.sort(key=lambda x: x.get('expected_latency_ms', 999))
            
            print(f"✅ 智能生成了 {len(configs)} 个WASAPI配置")
            return configs[:5]  # 返回前5个最佳配置
            
        except Exception as e:
            print(f"⚠️ 智能WASAPI配置生成失败: {e}")
            # 返回默认配置
            return [{
                'name': 'DirectSound兼容模式',
                'device': None,
                'samplerate': 48000,
                'blocksize': 128,
                'settings': None,
                'expected_latency': 'medium',
                'expected_latency_ms': 128 / 48000 * 1000
            }]
    
    def _load_verified_optimal_config(self):
        """加载已验证的最佳配置"""
        try:
            import json
            from pathlib import Path
            
            config_file = Path(__file__).parent.parent.parent / "optimal_wasapi_config.json"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    optimal_data = json.load(f)
                
                # 验证设备是否仍然可用
                if self._verify_device_availability(optimal_data['device']):
                    # 转换为MindEcho内部格式
                    import sounddevice as sd
                    return {
                        'name': optimal_data['name'],
                        'device': optimal_data['device'],
                        'samplerate': optimal_data['samplerate'],
                        'blocksize': optimal_data['blocksize'],
                        'settings': sd.WasapiSettings(exclusive=True) if optimal_data['driver_type'] == 'wasapi_exclusive' else sd.WasapiSettings(exclusive=False),
                        'expected_latency': 'ultra-low',
                        'expected_latency_ms': float(optimal_data['expected_latency'].replace('ms', '')),
                        'verified': True,
                        'quality_score': 100
                    }
                else:
                    print(f"⚠️ 已验证设备 {optimal_data['device']} 不再可用")
            
        except Exception as e:
            print(f"⚠️ 加载最佳配置失败: {e}")
        
        return None
    
    def _verify_device_availability(self, device_id):
        """验证设备是否可用"""
        try:
            import sounddevice as sd
            if device_id is None:
                return False
                
            devices = sd.query_devices()
            if device_id >= len(devices):
                print(f"⚠️ 设备索引{device_id}超出范围（共{len(devices)}个设备）")
                return False
                
            device = devices[device_id]
            max_inputs = device.get('max_input_channels', 0)
            
            if max_inputs <= 0:
                print(f"⚠️ 设备{device_id}没有输入通道")
                return False
                
            # 🎯 专门验证HECATE设备的可用性
            device_name = device.get('name', '').lower()
            if 'hecate' in device_name and 'g4 pro' in device_name:
                print(f"🎧 验证HECATE G4 Pro设备{device_id}: {device.get('name', 'Unknown')}")
                
                # 获取设备的原生采样率
                native_sr = device.get('default_samplerate', 192000)
                print(f"   设备原生采样率: {native_sr}Hz")
                
                # 🎯 HECATE专用快速测试：直接测试192kHz/32样本（根据测试结果优化）
                if native_sr >= 192000:
                    # 优先测试192kHz/32样本（已知可用的配置）
                    test_configs = [
                        {'sr': 192000, 'bs': 32, 'mode': 'shared'},    # 最佳配置
                        {'sr': 192000, 'bs': 64, 'mode': 'shared'},    # 备用配置
                        {'sr': 192000, 'bs': 128, 'mode': 'shared'},   # 稳定配置
                    ]
                else:
                    # 对于非192k设备，测试标准配置
                    test_configs = [
                        {'sr': 48000, 'bs': 128, 'mode': 'shared'},
                        {'sr': 44100, 'bs': 128, 'mode': 'shared'},
                    ]
                
                for i, config in enumerate(test_configs):
                    try:
                        print(f"   🧪 测试 {config['sr']}Hz/{config['bs']}样本/{config['mode']}...")
                        
                        if config['mode'] == 'shared':
                            settings = sd.WasapiSettings(exclusive=False)
                        else:
                            settings = sd.WasapiSettings(exclusive=True)
                        
                        # 创建并测试流
                        test_stream = sd.InputStream(
                            device=device_id,
                            channels=1,
                            samplerate=config['sr'],
                            blocksize=config['bs'],
                            dtype='float32',
                            extra_settings=settings
                        )
                        
                        # 快速启动测试（0.05秒）
                        test_stream.start()
                        import time
                        time.sleep(0.05)
                        test_stream.stop()
                        test_stream.close()
                        
                        print(f"   ✅ HECATE设备{device_id}验证通过：{config['sr']}Hz/{config['bs']}样本")
                        return True
                        
                    except Exception as test_error:
                        print(f"   ❌ 配置{i+1}测试失败: {test_error}")
                        continue
                
                print(f"❌ HECATE设备{device_id}所有配置验证失败")
                return False
            
            else:
                # 通用设备的简单验证
                try:
                    test_stream = sd.InputStream(
                        device=device_id,
                        channels=1,
                        samplerate=48000,
                        blocksize=256,
                        dtype='float32'
                    )
                    test_stream.start()
                    test_stream.stop()
                    test_stream.close()
                    print(f"✅ 通用设备{device_id}验证通过")
                    return True
                except Exception as test_error:
                    print(f"⚠️ 通用设备{device_id}测试失败: {test_error}")
                    return False
            
        except Exception as e:
            print(f"⚠️ 验证设备{device_id}失败: {e}")
            return False
    
    def _calculate_device_quality_score(self, device):
        """计算设备质量评分"""
        score = 0
        name = device['name'].lower()
        
        # 基础分数
        score += 30
        
        # 高端设备品牌加分
        if 'hecate' in name and 'g4 pro' in name:
            score += 50  # HECATE G4 Pro最高分
        elif any(brand in name for brand in ['hecate', 'scarlett', 'apollo', 'rme']):
            score += 40
        elif any(brand in name for brand in ['audio-technica', 'shure', 'beyerdynamic']):
            score += 30
        elif 'realtek' in name:
            score += 15
        
        # 采样率评分
        sample_rate = device['default_samplerate']
        if sample_rate >= 192000:
            score += 20
        elif sample_rate >= 96000:
            score += 15
        elif sample_rate >= 48000:
            score += 10
        
        # 通道数评分
        channels = device['max_input_channels']
        if channels >= 8:
            score += 10
        elif channels >= 2:
            score += 5
        
        return min(score, 100)
    
    def _generate_device_wasapi_configs(self, device):
        """为单个设备生成WASAPI配置"""
        import sounddevice as sd
        configs = []
        
        device_id = device['id']
        device_name = device['name']
        base_sample_rate = device['sample_rate']
        
        # 🎧 针对HECATE G4 Pro的特殊优化配置
        is_hecate = 'hecate' in device_name.lower() and 'g4 pro' in device_name.lower()
        
        if is_hecate:
            print(f"🎯 为HECATE G4 Pro生成优化配置...")
            
            # 获取设备的原生采样率
            native_sr = base_sample_rate
            print(f"   HECATE原生采样率: {native_sr}Hz")
            
            # 🎯 HECATE G4 Pro优化配置：基于测试结果，优先192kHz/32样本
            hecate_configs = []
            
            # 如果设备原生支持192kHz（基于测试，设备24支持）
            if native_sr >= 192000:
                hecate_configs.extend([
                    # 根据测试结果，优先32样本（已验证可用）
                    {'sr': 192000, 'bs': 32, 'name': 'HECATE G4 Pro (192k极致 - 0.17ms)'},
                    {'sr': 192000, 'bs': 64, 'name': 'HECATE G4 Pro (192k高性能 - 0.33ms)'},
                    {'sr': 192000, 'bs': 128, 'name': 'HECATE G4 Pro (192k平衡 - 0.67ms)'},
                    {'sr': 192000, 'bs': 256, 'name': 'HECATE G4 Pro (192k稳定 - 1.33ms)'},
                ])
                print(f"   ✅ 生成4个192kHz配置（基于测试验证）")
            else:
                # 对于非192k原生采样率的HECATE设备，使用标准配置
                hecate_configs.extend([
                    {'sr': 48000, 'bs': 128, 'name': 'HECATE G4 Pro (48k平衡)'},
                    {'sr': 44100, 'bs': 128, 'name': 'HECATE G4 Pro (44k平衡)'},
                ])
                print(f"   ℹ️ 生成标准配置（设备不支持192kHz）")
            
            config_count = 0
            for config in hecate_configs:
                # 先测试共享模式
                if self._test_wasapi_compatibility(device_id, config['sr'], config['bs'], exclusive=False):
                    # WASAPI共享配置
                    shared_config = {
                        'name': f"WASAPI共享 - {config['name']}",
                        'device': device_id,
                        'samplerate': config['sr'],
                        'blocksize': config['bs'],
                        'settings': sd.WasapiSettings(exclusive=False),
                        'expected_latency': 'ultra-low' if config['bs'] <= 64 else 'low',
                        'expected_latency_ms': config['bs'] / config['sr'] * 1000,
                        'quality_score': device['score']
                    }
                    configs.append(shared_config)
                    config_count += 1
                    
                    # 测试独占模式
                    if self._test_wasapi_compatibility(device_id, config['sr'], config['bs'], exclusive=True):
                        exclusive_config = {
                            'name': f"WASAPI独占 - {config['name']}",
                            'device': device_id,
                            'samplerate': config['sr'],
                            'blocksize': config['bs'],
                            'settings': sd.WasapiSettings(exclusive=True),
                            'expected_latency': 'ultra-low' if config['bs'] <= 64 else 'low',
                            'expected_latency_ms': config['bs'] / config['sr'] * 1000,
                            'quality_score': device['score']
                        }
                        configs.append(exclusive_config)
                        config_count += 1
                    
                    # 限制配置数量，优先质量
                    if config_count >= 4:
                        break
            
            print(f"   📊 成功生成{len(configs)}个HECATE配置")
        else:
            # 通用设备配置
            test_sample_rates = [base_sample_rate]
            if base_sample_rate != 48000:
                test_sample_rates.append(48000)
            if base_sample_rate != 44100:
                test_sample_rates.append(44100)
            
            test_block_sizes = [128, 256, 512]  # 使用更稳定的缓冲区大小
            
            for sample_rate in test_sample_rates[:2]:
                for block_size in test_block_sizes[:2]:
                    if self._test_wasapi_compatibility(device_id, sample_rate, block_size, exclusive=False):
                        # 先尝试共享模式（更稳定）
                        shared_config = {
                            'name': f'WASAPI共享 ({device_name})',
                            'device': device_id,
                            'samplerate': sample_rate,
                            'blocksize': block_size,
                            'settings': sd.WasapiSettings(exclusive=False),
                            'expected_latency': 'low',
                            'expected_latency_ms': block_size / sample_rate * 1000,
                            'quality_score': device['score']
                        }
                        configs.append(shared_config)
                        
                        # 对于高质量设备测试独占模式
                        if device['score'] >= 70 and self._test_wasapi_compatibility(device_id, sample_rate, block_size, exclusive=True):
                            exclusive_config = {
                                'name': f'WASAPI独占 ({device_name})',
                                'device': device_id,
                                'samplerate': sample_rate,
                                'blocksize': block_size,
                                'settings': sd.WasapiSettings(exclusive=True),
                                'expected_latency': 'ultra-low',
                                'expected_latency_ms': block_size / sample_rate * 1000,
                                'quality_score': device['score']
                            }
                            configs.append(exclusive_config)
                        break  # 找到一个稳定配置就停止
        
        return configs[:3]  # 限制配置数量，避免过多选项
    
    def _test_wasapi_compatibility(self, device_id, sample_rate, block_size, exclusive=False):
        """快速测试WASAPI设备兼容性（增强版）"""
        try:
            import sounddevice as sd
            
            # 创建WASAPI设置
            settings = sd.WasapiSettings(exclusive=exclusive)
            
            print(f"   🧪 测试 {sample_rate}Hz/{block_size}样本/{'独占' if exclusive else '共享'}模式...", end='')
            
            # 创建测试流但不启动
            stream = sd.InputStream(
                device=device_id,
                channels=1,
                samplerate=sample_rate,
                blocksize=block_size,
                dtype=np.float32,
                extra_settings=settings
            )
            stream.close()
            print(" ✅")
            return True
            
        except Exception as e:
            error_str = str(e)
            if "Invalid sample rate" in error_str or "PaErrorCode -9997" in error_str:
                print(f" ❌ 不支持采样率{sample_rate}Hz")
            elif "Invalid device" in error_str or "PaErrorCode -9996" in error_str:
                print(f" ❌ 设备不可用")
            elif "exclusive" in error_str.lower():
                print(f" ❌ 独占模式不可用")
            else:
                print(f" ❌ {error_str[:50]}")
            return False
        
    def _init_memory_pool(self):
        """初始化零拷贝内存池"""
        try:
            # 预分配音频缓冲区
            buffer_size = int(self.sample_rate * 0.1)  # 100ms缓冲
            self.preallocated_buffers = {
                'input_buffer': np.zeros(buffer_size, dtype=np.float32),
                'output_buffer': np.zeros(buffer_size, dtype=np.float32),
                'processing_buffer': np.zeros(buffer_size, dtype=np.float32)
            }
            print("🔥 IntegratedAudioProcessor: 零拷贝内存池初始化完成")
        except Exception as e:
            print(f"⚠️ IntegratedAudioProcessor: 内存池初始化失败: {e}")
            self.zero_copy_enabled = False

    def _start_dedicated_audio_thread(self):
        """启动专用音频处理线程"""
        if self.dedicated_audio_thread is None or not self.dedicated_audio_thread.is_alive():
            self.dedicated_audio_thread = threading.Thread(
                target=self._audio_processing_worker,
                daemon=True,
                name="AudioProcessor"
            )
            self.dedicated_audio_thread.start()
            print("🚀 IntegratedAudioProcessor: 专用音频处理线程已启动")

    def _audio_processing_worker(self):
        """专用音频处理工作线程"""
        while True:
            try:
                # 非阻塞获取音频数据
                audio_data = self.audio_queue.get(timeout=0.001)
                if audio_data is None:  # 停止信号
                    break
                
                # 零拷贝处理音频数据
                with self.processing_lock:
                    self._process_audio_zero_copy(audio_data)
                
                self.audio_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"⚠️ IntegratedAudioProcessor: 音频处理线程错误: {e}")

    def _process_audio_zero_copy(self, indata):
        """零拷贝音频处理"""
        try:
            if not self.zero_copy_enabled:
                return self._fallback_audio_processing(indata)
            
            # 直接操作内存视图，避免数据复制
            audio_view = indata.view()  # 零拷贝视图
            
            # 使用预分配缓冲区
            buffer_size = min(len(audio_view), len(self.preallocated_buffers['processing_buffer']))
            processing_slice = self.preallocated_buffers['processing_buffer'][:buffer_size]
            
            # 零拷贝赋值
            processing_slice[:] = audio_view.flatten()[:buffer_size]
            
            # 快速信号检测（零拷贝）
            if np.max(np.abs(processing_slice)) > 0.01:
                # 触发界面更新（使用信号）
                try:
                    self.audio_level_updated.emit(float(np.max(np.abs(processing_slice))))
                except RuntimeError:
                    pass  # 如果Qt对象已销毁，忽略
                
        except Exception as e:
            print(f"⚠️ IntegratedAudioProcessor: 零拷贝处理失败，回退到标准处理: {e}")
            return self._fallback_audio_processing(indata)

    def _fallback_audio_processing(self, indata):
        """标准音频处理（回退方案）"""
        try:
            audio_data = indata.copy()
            if np.max(np.abs(audio_data)) > 0.01:
                try:
                    self.audio_level_updated.emit(float(np.max(np.abs(audio_data))))
                except RuntimeError:
                    pass  # 如果Qt对象已销毁，忽略
        except Exception as e:
            print(f"⚠️ IntegratedAudioProcessor: 标准处理失败: {e}")
        
    def setup_analyzers(self):
        """设置分析器 - 简化版本，只保留必需的组件"""
        try:
            # 🎯 简化：移除多余的分析器，只保留基本需求
            # self.overlapping_analyzer = None  # 不再使用
            # self.pitch_detector = None        # 不再使用
            
            self.status_updated.emit("简化分析器初始化完成")
            # 默认启用YIN基线算法，保证与知唱音域音调仪类似的稳定体验
            try:
                if not hasattr(self, 'pitch_algo_mode'):
                    self.pitch_algo_mode = 'yin'
                    print("🎚️ 默认算法模式: yin (简化YIN基线)")
                # 确保统一音高服务存在
                if _PITCH_SERVICE_AVAILABLE and (self.pitch_service is None):
                    self.pitch_service = PitchDetectionService(
                        sample_rate=float(self.sample_rate),
                        min_frequency=float(self.min_frequency),
                        max_frequency=float(self.max_frequency),
                        yin_threshold=float(getattr(self, 'yin_threshold', 0.12)),
                        mode_name=str(getattr(getattr(self, 'current_performance_mode', None), 'name', 'BALANCED'))
                    )
                    print("✅ PitchDetectionService 就绪")
            except Exception:
                pass
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"分析器初始化失败: {e}")
            return False
    
    def set_frequency_range(self, min_freq, max_freq):
        """设置音高检测的频率范围"""
        if 50 <= min_freq <= 200 and 500 <= max_freq <= 3000 and min_freq < max_freq:
            self.min_frequency = min_freq
            self.max_frequency = max_freq
            print(f"🎵 频率范围已设置: {min_freq}-{max_freq}Hz")
            # 同步到统一音高服务
            try:
                if self.pitch_service:
                    self.pitch_service.set_frequency_range(float(min_freq), float(max_freq))
            except Exception:
                pass
            return True
        else:
            print(f"❌ 无效的频率范围: {min_freq}-{max_freq}Hz")
            return False
    
    def get_frequency_range(self):
        """获取当前的频率范围设置"""
        return self.min_frequency, self.max_frequency
    
    def set_noise_reduction_mode(self, mode):
        """设置降噪模式"""
        if self.noise_processor:
            self.noise_processor.set_noise_reduction_mode(mode)
            print(f"🔧 IntegratedAudioProcessor: 降噪模式设置为 {mode}")
        else:
            print("❌ IntegratedAudioProcessor: 降噪处理器未初始化")

    def _reset_pitch_analysis_state(self, reason: str = ""):
        """统一重置音高分析相关的内部状态，确保不同启动路径获得一致结果。
        reason: 触发原因便于调试。"""
        try:
            self.pitch_history.clear()
        except Exception:
            pass
        # 清除平滑/跳变抑制内部变量
        for attr in ["_last_stable_frequency", "_freq_smooth", "_pitch_analysis_counter", "_audio_accumulator_buffer", "_last_raw_frequency"]:
            if hasattr(self, attr):
                try:
                    delattr(self, attr)
                except Exception:
                    setattr(self, attr, None)
        print(f"🔄 重置音高分析状态完成: {reason}")

    # ========= 音高后处理（Phase1: 提取独立逻辑） ========= #
    def _post_process_pitch(self, raw_frequency: float) -> float:
        """对原始检测频率执行跳变抑制与平滑，返回平滑后的频率。
        - 保留 raw_frequency 以供 vibrato 与调试
        - self._last_stable_frequency / self._freq_smooth 维护内部状态
        """
        if raw_frequency <= 0:
            return 0.0

        if not hasattr(self, '_last_stable_frequency'):
            self._last_stable_frequency = 0.0
        if not hasattr(self, '_freq_smooth'):
            self._freq_smooth = 0.0

        # 针对简化YIN模式，采用更轻的平滑，不做强跳变压制，避免“水平直线”与慢跟随
        try:
            mode = getattr(self, 'pitch_algo_mode', 'yin')
        except Exception:
            mode = 'yin'
        if mode == 'yin':
            # 大幅下跳直接复位（防止高位残留拖慢回落）
            if (self._last_stable_frequency > 300 and
                raw_frequency < self._last_stable_frequency * 0.45 and
                (self._last_stable_frequency - raw_frequency) > 180):
                self._freq_smooth = raw_frequency
                self._last_stable_frequency = raw_frequency
                return raw_frequency
            # 自适应轻量平滑：更高alpha以保留微小变化
            prev = self._freq_smooth if self._freq_smooth != 0 else raw_frequency
            delta_hz = abs(raw_frequency - prev)
            alpha = 0.85
            if delta_hz < 2.0:
                alpha = 0.93  # 极小波动，尽量贴近raw
            elif delta_hz < 5.0:
                alpha = 0.88
            else:
                alpha = 0.82
            # 低电平时提高跟随，减少“直线化”
            if getattr(self, '_last_frame_rms', 0.0) < 0.02:
                alpha = min(0.96, alpha + 0.03)
            # 上行加速一点点
            if raw_frequency > prev * 1.04:
                alpha = min(0.97, alpha + 0.04)
            # 指数平滑
            self._freq_smooth = alpha * raw_frequency + (1 - alpha) * prev
            smooth = self._freq_smooth
            # 微变化注入：在变化很小时保留少量原始细节，避免水平
            if delta_hz < 3.0:
                smooth = 0.94 * smooth + 0.06 * raw_frequency
            smooth = max(50, min(2500, smooth))
            self._freq_smooth = smooth
            self._last_stable_frequency = smooth
            return smooth

        # ====== 异常大幅下跳快速复位逻辑 ======
        # 说明: 之前算法在遇到 800Hz -> 150Hz 这类巨大下降时会“拉回”导致 smooth 远高于真实 raw
        # 当出现显著下降且之前频率较高，很可能是进入新音或前面是假高频/噪声，应直接重置平滑状态
        if (self._last_stable_frequency > 300 and
            raw_frequency < self._last_stable_frequency * 0.45 and  # 大幅下降
            (self._last_stable_frequency - raw_frequency) > 180):     # 绝对差值
            # 直接复位，防止高位残留造成后续多帧粘滞
            self._freq_smooth = raw_frequency
            self._last_stable_frequency = raw_frequency
            return raw_frequency

        # 跳变抑制
        if self._last_stable_frequency > 0:
            jump = abs(raw_frequency - self._last_stable_frequency)
            if jump > max(150, self._last_stable_frequency * 0.35):  # 更温和参数
                raw_frequency = self._last_stable_frequency + (raw_frequency - self._last_stable_frequency) * 0.25

        # 指数平滑（自适应）：小幅变化时提高alpha保留细微起伏，较大变化时保守平滑
        if not hasattr(self, '_last_frame_rms'):
            self._last_frame_rms = 0.0
        delta = abs(raw_frequency - (self._last_stable_frequency or raw_frequency))
        if delta < 0.8:
            alpha = 0.60
        elif delta < 2.0:
            alpha = 0.45
        else:
            alpha = 0.28
        # 低电平段适当提高alpha，避免“直线化”
        if self._last_frame_rms < 0.02:
            alpha = min(0.70, alpha + 0.10)
        if self._freq_smooth == 0:
            self._freq_smooth = raw_frequency
        else:
            self._freq_smooth = alpha * raw_frequency + (1 - alpha) * self._freq_smooth

        smooth = self._freq_smooth
        # ====== 平滑结果异常抑制 ======
        # 若平滑值远高于当前 raw（>1.9倍）且 raw 合理且变化较大，限制回落速度
        if raw_frequency > 0 and smooth > raw_frequency * 1.9 and delta > 5.0:
            smooth = raw_frequency * 1.9
        # 若平滑值远低于 raw（极端快速上跳被压制），允许稍快跟随
        if raw_frequency > 0 and raw_frequency > self._last_stable_frequency * 1.8:
            # 加速上行：重新加权
            smooth = self._last_stable_frequency * 0.4 + raw_frequency * 0.6

        # 合理范围裁剪
        smooth = max(50, min(2500, smooth))
        self._last_stable_frequency = smooth
        return smooth

    # ========= 简化YIN基线检测（稳定、轻依赖，避免过度复杂引入冲突） ========= #
    def set_pitch_algorithm_mode(self, mode: str = 'yin'):
        """设置音高检测算法模式：'yin'（简化YIN基线，默认）或 'fusion'（多候选融合）。"""
        try:
            if mode not in ('yin', 'fusion'):
                print(f"❌ 无效的算法模式: {mode}")
                return False
            self.pitch_algo_mode = mode
            print(f"🎚️ 检测算法切换为: {mode}")
            # 切换时重置平滑状态，避免模式残留影响
            self._reset_pitch_analysis_state(f"switch_algo->{mode}")
            return True
        except Exception as e:
            print(f"❌ 设置算法模式失败: {e}")
            return False

    def detect_pitch_simple_yin(self, audio_data: np.ndarray) -> float:
        """简化YIN/CMNDF检测：
        - 使用FFT自相关快速差分近似，CMNDF阈值优先选择首个最小值，避免低八度
        - 采用窗口(≈40–46ms)与UI频率范围一致的tau边界
        - 返回Hz，失败返回0
        """
        try:
            x_in = np.array(audio_data, dtype=np.float64)
            if len(x_in) < 64:
                return 0.0
            sr = float(getattr(self, 'sample_rate', 48000.0) or 48000.0)
            # 使用已配置的帧窗口，避免重复累计与额外延迟
            win_len = int(getattr(self, '_frame_window', 2048))
            # 若当前数据不足窗口长度，尽量使用已有数据（不足则提前返回0）
            if len(x_in) < win_len:
                # 在处理循环中会按hop拼接足量数据，这里直接返回等待下一帧
                return 0.0
            # 使用当前帧数据末段，保证与处理循环一致
            x = x_in[-win_len:]
            # 在高采样率场景（>=88.2k/96k）下做x2下采样以降低计算量
            # 仅用于检测阶段，不改变UI时间轴与原始采样
            if sr >= 88000.0 and len(x) >= 1024:
                x = x[::2]
                sr = sr / 2.0
                # 同步窗口长度变量，便于后续缓存匹配
                win_len = len(x)
            # 去均值 + 汉宁窗（带缓存，减少重复分配）
            try:
                if getattr(self, '_hann_cache_len', 0) != len(x):
                    self._hann_win_cache = np.hanning(len(x))
                    self._hann_cache_len = len(x)
                x = (x - float(np.mean(x))) * self._hann_win_cache
            except Exception:
                x = (x - float(np.mean(x))) * np.hanning(len(x))
            N = len(x)
            # tau范围与UI一致
            try:
                ui_min_f, ui_max_f = self.get_frequency_range()
            except Exception:
                ui_min_f = float(getattr(self, 'min_frequency', 80.0))
                ui_max_f = float(getattr(self, 'max_frequency', 1047.0))
            tau_min = int(max(2, np.floor(sr / max(ui_max_f, 1.0))))
            tau_max = int(min(N - 3, np.ceil(sr / max(ui_min_f, 50.0))))
            if tau_max <= tau_min + 2:
                return 0.0
            # FFT自相关 -> 差分函数近似 d(tau) = 2*(r(0)-r(tau))
            nfft = 1 << int(np.ceil(np.log2(2 * N)))
            spec = np.fft.rfft(x, n=nfft)
            ac = np.fft.irfft(spec * np.conj(spec), n=nfft)[:N]
            ac0 = float(ac[0])
            d = 2.0 * (ac0 - ac[:tau_max + 1])
            # CMNDF
            d1 = d[1:tau_max + 1]
            if np.any(d1 < 0):
                d1 = np.maximum(d1, 0.0)
            cumsum = np.cumsum(d1)
            idx = np.arange(1, len(d1) + 1, dtype=np.float64)
            cmndf = np.ones_like(d)
            denom = cumsum / idx
            # 避免除零
            denom = np.where(denom <= 1e-12, 1e-12, denom)
            cmndf[1:tau_max + 1] = d1 / denom
            # 阈值与选择：优先第一个过阈且为局部最小
            yin_thr = float(getattr(self, 'yin_threshold', 0.12))
            # 根据性能模式对阈值做轻微自适应，提升弱声段命中率
            try:
                from src.audio_processing.performance_manager import get_performance_manager, PerformanceMode
                _pm_m = get_performance_manager()
                _mode_m = _pm_m.get_current_mode() if _pm_m else None
                if _mode_m == PerformanceMode.HIGH_PERFORMANCE:
                    yin_thr = max(0.08, yin_thr - 0.02)
                elif _mode_m == PerformanceMode.BALANCED:
                    yin_thr = max(0.10, yin_thr - 0.01)
            except Exception:
                pass
            search = cmndf[tau_min:tau_max + 1]
            # 找到过阈位置
            cand_tau = None
            below = np.where(search < yin_thr)[0]
            if below.size > 0:
                # 取第一个过阈位置的局部最小
                start = int(below[0])
                # 在[start .. start+8]范围内找局部最小进一步稳定
                s0 = tau_min + start
                s1 = min(tau_max, s0 + 8)
                loc = int(np.argmin(cmndf[s0:s1 + 1]))
                cand_tau = s0 + loc
            else:
                # 回退：全局最小
                cand_tau = int(np.argmin(cmndf[tau_min:tau_max + 1]) + tau_min)
            if not (tau_min <= cand_tau <= tau_max):
                return 0.0
            # 抛物线插值（在CMNDF曲线）
            if 1 < cand_tau < len(cmndf) - 1:
                y1, y2, y3 = cmndf[cand_tau - 1], cmndf[cand_tau], cmndf[cand_tau + 1]
                denom_q = (y1 - 2 * y2 + y3)
                off = 0.0 if abs(denom_q) < 1e-12 else 0.5 * (y1 - y3) / denom_q
            else:
                off = 0.0
            tau_hat = float(cand_tau) + float(np.clip(off, -1.0, 1.0))
            if tau_hat <= 1e-6:
                return 0.0
            f0 = float(sr / tau_hat)
            # 范围裁剪
            if not (ui_min_f <= f0 <= ui_max_f * 1.02):
                return 0.0
            return f0
        except Exception as e:
            try:
                if getattr(self, 'debug_flags', {}).get('pitch_log', False):
                    self._log_rate_limit('yin_err', f"❌ YIN错误: {e}", interval=2.0)
            except Exception:
                pass
            return 0.0

    def _benchmark_stream_config(self, stream_params: dict, duration_s: float = 0.35) -> dict:
        """对给定输入流参数进行短时基准测试，返回XRUN/稳定性与理论延迟等指标。
        仅创建输入流（不回放），使用极轻回调统计状态，避免占用太多时间。
        """
        metrics = {
            'ok': False,
            'callbacks': 0,
            'xrun': 0,
            'overflow': 0,
            'underflow': 0,
            'latency_ms': None,
            'error': None
        }
        try:
            import sounddevice as sd
            import time as _t
            sr = int(stream_params.get('samplerate', getattr(self, 'sample_rate', 48000)))
            bs = int(stream_params.get('blocksize', getattr(self, 'chunk_size', 256)))
            theoretical = (bs / max(1, sr)) * 1000.0
            metrics['latency_ms'] = theoretical

            counters = {'cb': 0, 'xrun': 0, 'overflow': 0, 'underflow': 0}

            def _probe_cb(indata, frames, time_info, status):
                counters['cb'] += 1
                if status:
                    s = str(status).lower()
                    # 统计XRUN/溢出/欠载
                    if 'overflow' in s:
                        counters['overflow'] += 1
                        counters['xrun'] += 1
                    if 'underflow' in s:
                        counters['underflow'] += 1
                        counters['xrun'] += 1
                # 不做任何处理，最大程度模拟监听读取成本
                return

            probe_args = {
                'channels': max(1, int(stream_params.get('channels', getattr(self, 'channels', 1)))) ,
                'samplerate': sr,
                'blocksize': bs,
                'dtype': np.float32,
                'callback': _probe_cb
            }
            # 设备/设置
            if 'device' in stream_params:
                probe_args['device'] = stream_params['device']
            if 'extra_settings' in stream_params and stream_params['extra_settings'] is not None:
                probe_args['extra_settings'] = stream_params['extra_settings']

            with sd.InputStream(**probe_args) as s:
                # 运行短时，收集N个回调
                deadline = _t.time() + max(0.2, min(0.6, duration_s))
                while _t.time() < deadline:
                    _t.sleep(0.02)
                metrics['callbacks'] = counters['cb']
                metrics['xrun'] = counters['xrun']
                metrics['overflow'] = counters['overflow']
                metrics['underflow'] = counters['underflow']
                metrics['ok'] = True
        except Exception as e:
            metrics['error'] = str(e)
        return metrics

    def _rank_monitoring_configs(self, monitoring_configs: list) -> list:
        """对候选监听配置进行基准测试并按得分排序，优先无XRUN且延迟低的配置。
        返回新的排序列表（包含原字段）。失败的配置会被排至末尾。
        """
        ranked = []
        try:
            # 构造可基准的输入流参数集合
            candidates = []
            for cfg in monitoring_configs:
                try:
                    # 基于现有逻辑构造 InputStream 所需的参数
                    params = {
                        'channels': getattr(self, 'channels', 1),
                        'samplerate': cfg.get('samplerate', getattr(self, 'sample_rate', 48000)),
                        'blocksize': cfg.get('blocksize', getattr(self, 'chunk_size', 256)),
                    }
                    if 'device' in cfg:
                        params['device'] = cfg['device']
                    if cfg.get('settings') is not None:
                        params['extra_settings'] = cfg['settings']
                    candidates.append((cfg, params))
                except Exception:
                    # 跳过无法构造的配置
                    candidates.append((cfg, None))

            scored = []
            for cfg, params in candidates:
                if params is None:
                    # 无法基准，置于末尾
                    scored.append((cfg, 1e9, {'ok': False, 'error': 'params_none'}))
                    continue
                m = self._benchmark_stream_config(params, duration_s=0.35)
                # 评分：延迟 + XRUN重罚
                score = (m.get('latency_ms') or 999.0) + (m.get('xrun', 0) * 500.0)
                # 优先考虑基准成功
                if not m.get('ok'):
                    score += 2000.0
                scored.append((cfg, score, m))

            scored.sort(key=lambda x: x[1])
            # 打印简单榜单
            for i, (cfg, sc, m) in enumerate(scored[:5]):
                try:
                    name = cfg.get('name', '未知配置')
                    sr = cfg.get('samplerate', getattr(self, 'sample_rate', 48000))
                    bs = cfg.get('blocksize', getattr(self, 'chunk_size', 256))
                    print(f"🏁 基准{ i+1 }: {name} — {sr}Hz/{bs}样本 | 延迟≈{(m.get('latency_ms') or 0):.2f}ms XRUN:{m.get('xrun',0)}")
                except Exception:
                    pass
            ranked = [cfg for (cfg, _, __) in scored]
        except Exception as e:
            print(f"⚠️ 配置基准排序失败: {e}")
            return monitoring_configs
        return ranked if ranked else monitoring_configs
    
    def start_recording(self, filename=None, should_save=True):
        """开始录音"""
        try:
            # 🎯 检查全局监听状态 - 如果已有监听运行，不要干扰
            if self.is_global_monitoring_active:
                print("🎯 检测到全局监听模式已激活，录音将与监听共享音频流")
                # 只更新录音状态，不重新创建音频流
                self.recording_filename = filename
                self.should_save = should_save
                self.is_recording = True  # 标记为录音状态
                self.is_monitoring_only = False  # 🎯 重要：录音时需要完整音频处理，不是纯监听
                if self.should_save:
                    self.audio_buffer = []  # 只有需要保存时才清空缓冲区
                    # 进入录音时重置录音计时，确保时长准确
                    self.recording_start_time = time.time()
                
                # 🔁 统一：在监听基础上转入录音必须重置音高相关状态，保证与“直接录音”一致
                self._reset_pitch_analysis_state(reason="monitor->record switch")

                # 🔥 重要修复：确保录音时全局监控的音频处理线程会进行音高检测
                print("🔥 全局监控模式录音：强制启用音高检测处理")
                self.enable_pitch_visualization = True  # 录音分析允许绘制
                
                self.status_updated.emit("录音已在全局监听中启动")
                return True
            
            self.recording_filename = filename
            self.should_save = should_save
            self.audio_buffer = []
            self.pitch_history.clear()
            self.recording_start_time = time.time()
            
            # 🎯 重要：录音模式下需要确保音高检测正常工作
            self.is_monitoring_only = False  # 录音时不是纯监听模式，需要完整音频处理
            self.enable_pitch_visualization = True
            
            # 统一重置分析状态
            self._reset_pitch_analysis_state(reason="fresh record start")

            # 设置分析器
            if not self.setup_analyzers():
                return False
            
            # 录音回调前置：根据性能模式设置合批与限频
            try:
                from src.audio_processing.performance_manager import get_performance_manager, PerformanceMode
                _pm = get_performance_manager()
                _cfg = _pm.get_current_config() if _pm else None
                _mode = _pm.get_current_mode() if _pm else None
                # 进一步细化：按模式将回调入队阈值设为 chunk_size 的一半，降低延迟
                base_chunk = int(getattr(_cfg, 'chunk_size', 128)) if _cfg else 128
                if _mode == PerformanceMode.HIGH_PERFORMANCE:
                    self._callback_min_enqueue_samples = max(96, base_chunk // 2)  # e.g., 256->128
                elif _mode == PerformanceMode.BALANCED:
                    self._callback_min_enqueue_samples = max(96, base_chunk // 2)  # e.g., 512->256
                else:
                    self._callback_min_enqueue_samples = max(128, base_chunk // 2) # e.g., 1024->512
            except Exception:
                # 无配置时默认128样本（@48kHz≈2.7ms；@96kHz≈1.3ms）
                self._callback_min_enqueue_samples = 128
            # 回调侧累积缓冲与信号限频
            self._enqueue_accum = np.empty(0, dtype=np.float32)
            self._last_level_emit_t = time.time()
            self._last_progress_emit_t = time.time()
            self._level_emit_interval = 0.05   # 50ms 一次
            self._progress_emit_interval = 0.10 # 100ms 一次
            # 关闭回调内重处理，保留必要削峰，减负载
            self.enable_callback_dsp = False

            # 音频回调函数 - 优化以减少input overflow，增加详细调试
            def audio_callback(indata, frames, time_info, status):
                # 🎯 开始延迟监控
                callback_start_time = time.time()
                
                # 添加调试计数器
                if not hasattr(self, '_callback_counter'):
                    self._callback_counter = 0
                    print("🎤 音频回调函数首次调用（录音模式）")
                    print(f"🎤 回调参数: 输入形状={indata.shape}, 帧数={frames}")
                
                self._callback_counter += 1
                
                # 🎯 增强调试：前10次回调详细输出
                if self._callback_counter <= 10:
                    audio_rms = np.sqrt(np.mean(indata ** 2)) if len(indata) > 0 else 0
                    print(f"🎤 回调#{self._callback_counter}: 输入RMS={audio_rms:.4f}, 形状={indata.shape}, 状态={status}")
                
                if status and getattr(self, 'debug_flags', {}).get('audio_status_log', False):
                    # 只记录非overflow的状态信息，减少控制台输出
                    if 'input overflow' in str(status).lower():
                        self.buffer_overflow_count += 1
                        # 每100次overflow才输出一次警告
                        if self.buffer_overflow_count % 100 == 0:
                            print(f"⚠️ 音频缓冲区溢出警告 (第{self.buffer_overflow_count}次)")
                    else:
                        print(f"🔊 音频状态: {status}")
                
                # 每1000次回调输出一次状态
                if self._callback_counter % 1500 == 0:
                    # 🔥 修复：RMS计算应该与实际处理的数据一致
                    audio_data_preview = indata[:, 0] if self.channels == 1 else indata
                    audio_rms = np.sqrt(np.mean(audio_data_preview ** 2))
                    print(f"🎤 音频回调#{self._callback_counter}: RMS={audio_rms:.4f}, 帧数={frames}")
                    print(f"     原始输入形状: {indata.shape}, 处理后形状: {audio_data_preview.shape}")
                
                self.total_audio_frames += 1
                
                # 获取单声道数据 - 🔥 关键修复：对于双声道输入，混合到单声道而不是只取第一个声道
                if self.channels == 1 and indata.shape[1] > 1:
                    # 双声道混合到单声道，保持音量
                    audio_data = np.mean(indata, axis=1)  # 平均两个声道
                    print(f"🔊 双声道混合: {indata.shape} → {audio_data.shape}, RMS={np.sqrt(np.mean(audio_data**2)):.4f}")
                else:
                    audio_data = indata[:, 0] if len(indata.shape) > 1 else indata
                
                # 🎯 回调内最小处理：仅削峰裁剪，重处理可选开启
                try:
                    if self.enable_callback_dsp:
                        # 保留原高级处理路径（按需启用）
                        rms = np.sqrt(np.mean(audio_data ** 2))
                        peak = np.max(np.abs(audio_data))
                        if peak > 0.95:
                            audio_data = np.tanh(audio_data * 0.8) * 0.9
                        if rms > 0.5:
                            audio_data = audio_data * 0.6
                        elif rms < 0.05:
                            enhancement_ratio = min(2.0, 0.05 / max(rms, 0.001))
                            audio_data = audio_data * enhancement_ratio
                    # 最终安全限制：确保信号不会超出[-1, 1]范围
                    audio_data = np.clip(audio_data, -1.0, 1.0)
                except Exception:
                    audio_data = np.clip(audio_data, -1.0, 1.0)
                
                # 合批入队：累积到 >= 指定样本再入队，显著降低队列操作频率
                try:
                    # 追加到累积缓冲
                    if self._enqueue_accum.size == 0:
                        self._enqueue_accum = audio_data.copy()
                    else:
                        self._enqueue_accum = np.concatenate((self._enqueue_accum, audio_data))

                    # 批量吐出满足阈值的包
                    min_samples = int(self._callback_min_enqueue_samples)
                    while self._enqueue_accum.size >= min_samples:
                        packet = self._enqueue_accum[:min_samples]
                        self._enqueue_accum = self._enqueue_accum[min_samples:]

                        if not self.audio_buffer_queue.full():
                            self.audio_buffer_queue.put_nowait({
                                'data': packet.copy(),
                                'timestamp': time.time(),
                                'should_save': self.is_recording and self.should_save
                            })
                        else:
                            # 队列满时覆盖旧数据，保持最新
                            try:
                                self.audio_buffer_queue.get_nowait()
                                self.audio_buffer_queue.put_nowait({
                                    'data': packet.copy(),
                                    'timestamp': time.time(),
                                    'should_save': self.is_recording and self.should_save
                                })
                            except queue.Empty:
                                pass
                
                except Exception as e:
                    print(f"音频队列错误: {e}")
                
                # 计算音频电平（简化版本，减少计算）- 添加Qt对象检查
                try:
                    now_t = time.time()
                    if (now_t - self._last_level_emit_t) >= self._level_emit_interval:
                        audio_level = np.sqrt(np.mean(audio_data ** 2))
                        if hasattr(self, 'is_audio_processing') and self.is_audio_processing and not self.isFinished():
                            self.audio_level_updated.emit(float(audio_level))
                        self._last_level_emit_t = now_t
                except RuntimeError:
                    # Qt对象已被销毁，停止回调
                    print("⚠️ 音频回调: Qt对象已销毁，停止音频回调")
                    self.is_audio_processing = False  # 标记停止音频处理
                    return
                except Exception as e:
                    print(f"⚠️ 音频电平更新错误: {e}")
                
                # 更新录音进度 - 添加Qt对象检查
                try:
                    now_t = time.time()
                    if (now_t - self._last_progress_emit_t) >= self._progress_emit_interval:
                        if self.recording_start_time and hasattr(self, 'is_audio_processing') and self.is_audio_processing and not self.isFinished():
                            self.current_duration = now_t - self.recording_start_time
                            self.recording_progress.emit(self.current_duration)
                            self._last_progress_emit_t = now_t
                except RuntimeError:
                    # Qt对象已被销毁，停止录音进度更新
                    print("⚠️ 音频回调: Qt对象已销毁，停止录音进度更新")
                    self.is_audio_processing = False  # 标记停止音频处理
                    return
                except Exception as e:
                    print(f"⚠️ 录音进度更新错误: {e}")
                
                # 🎯 结束延迟监控和报告
                callback_end_time = time.time()
                processing_time = (callback_end_time - callback_start_time) * 1000  # 转换为毫秒
                self._processing_times.append(processing_time)
                
                # 保持处理时间历史在合理大小
                if len(self._processing_times) > 100:
                    self._processing_times = self._processing_times[-50:]
                
                # 每500次回调报告一次延迟统计
                if self._callback_counter % 500 == 0:
                    avg_processing_time = np.mean(self._processing_times)
                    max_processing_time = np.max(self._processing_times)
                    theoretical_latency = (self.chunk_size / self.sample_rate) * 1000
                    total_latency = theoretical_latency + avg_processing_time
                    
                    if self.debug_flags.get('latency_report', False):
                        print(f"🕐 延迟报告#{self._callback_counter}: ")
                        print(f"     理论延迟: {theoretical_latency:.2f}ms")
                        print(f"     处理延迟: {avg_processing_time:.2f}ms (最大: {max_processing_time:.2f}ms)")
                        print(f"     总延迟: {total_latency:.2f}ms")
                    
                    # 延迟警告
                    if total_latency > 1.0:
                        if self.debug_flags.get('latency_warn_verbose'):
                            if getattr(self, 'debug_flags', {}).get('latency_warn_verbose', False):
                                self._log_rate_limit('high_latency', f"⚠️ 延迟偏高: {total_latency:.2f}ms > 1.0ms", interval=0.5)
                        self._stat_counters['high_latency'] += 1
                    else:
                        if getattr(self, 'debug_flags', {}).get('latency_warn_verbose', False):
                            self._log_rate_limit('latency_ok', f"✅ 延迟良好: {total_latency:.2f}ms", interval=0.8)
                    
                    # 清理旧数据
                    self._processing_times = []
            
            # 🎯 如果全局监听已激活，跳过音频流创建
            if self.is_global_monitoring_active:
                print("🎯 使用现有全局监听音频流进行录音")
                self.is_recording = True
                
                # 🎯 重要修复：确保音频处理线程在录音时正常运行
                if not self.is_audio_processing:
                    print("🔧 全局监听模式：启动音频处理线程进行录音分析")
                    self.start_audio_processing_thread()
                else:
                    print("🔧 全局监听模式：音频处理线程已运行，继续录音分析")
                
                return True
            
            # 启动音频流 - 专业级超低延迟配置（智能设备选择）
            audio_stream_created = False
            
            # 🚀 专业音频配置序列（按延迟性能排序）- 修复lambda闭包问题
            audio_configs = [
                # 第一优先级：ASIO专业驱动（最低延迟）
                {
                    'name': 'ASIO专业模式',
                    'settings': sd.AsioSettings(channel_selectors=[0]),  # 🔧 修复：直接创建对象
                    'expected_latency': 'ultra-low'
                },
                # 第二优先级：DirectSound模式（最兼容）
                {
                    'name': 'DirectSound兼容模式',
                    'settings': None,  # 🔧 修复：直接使用None
                    'expected_latency': 'medium'  
                }
            ]
            
            # 🔧 动态添加WASAPI配置（使用动态设备发现）
            try:
                wasapi_configs = self._get_optimal_wasapi_configs()
                # 在ASIO后、DirectSound前插入WASAPI配置
                for i, config in enumerate(wasapi_configs):
                    audio_configs.insert(1 + i, {
                        'name': config['name'],
                        'device': config['device'],
                        'samplerate': config['samplerate'],
                        'blocksize': config['blocksize'],
                        'settings': config['settings'],  # 已经是对象，不是lambda
                        'expected_latency': config['expected_latency'],
                        'verified_latency': config.get('verified_latency')
                    })
                print(f"✅ 动态添加了 {len(wasapi_configs)} 个WASAPI配置")
            except Exception as e:
                print(f"⚠️ WASAPI动态配置失败，使用基础配置: {e}")
            
            for config in audio_configs:
                try:
                    # 构建音频流参数
                    stream_params = {
                        'callback': audio_callback,
                        'channels': self.channels,
                        'latency': 'low',
                        'dtype': np.float32
                    }
                    
                    # 为WASAPI设备使用测试验证的参数
                    if 'device' in config and 'samplerate' in config:
                        stream_params['device'] = config['device']
                        stream_params['samplerate'] = config['samplerate']
                        # 覆盖录音路径 blocksize 以匹配当前性能模式，降低回调频率
                        try:
                            from src.audio_processing.performance_manager import get_performance_manager
                            _pm = get_performance_manager()
                            _cfg = _pm.get_current_config() if _pm else None
                            mode_block = int(getattr(_cfg, 'chunk_size', self.chunk_size)) if _cfg else self.chunk_size
                            stream_params['blocksize'] = config.get('blocksize', mode_block)
                        except Exception:
                            stream_params['blocksize'] = config.get('blocksize', self.chunk_size)
                        verified_latency = config.get('verified_latency', 'unknown')
                        print(f"🎯 使用WASAPI设备{config['device']}@{config['samplerate']}Hz (测试验证延迟: {verified_latency}ms)")
                    else:
                        stream_params['samplerate'] = self.sample_rate
                        try:
                            from src.audio_processing.performance_manager import get_performance_manager
                            _pm = get_performance_manager()
                            _cfg = _pm.get_current_config() if _pm else None
                            mode_block = int(getattr(_cfg, 'chunk_size', self.chunk_size)) if _cfg else self.chunk_size
                            stream_params['blocksize'] = mode_block
                        except Exception:
                            stream_params['blocksize'] = self.chunk_size
                    
                    # 🔧 修复：添加特定驱动设置（避免lambda调用错误）
                    if config['settings'] is not None:
                        stream_params['extra_settings'] = config['settings']
                    
                    # 创建音频流
                    self.audio_stream = sd.InputStream(**stream_params)
                    
                    # 计算实际延迟（使用实际参数）
                    actual_sample_rate = stream_params['samplerate']
                    actual_blocksize = stream_params['blocksize']
                    # 记录实际输入参数供保存与统计使用
                    try:
                        self.active_input_samplerate = int(actual_sample_rate)
                        self.active_input_channels = int(stream_params.get('channels', self.channels))
                        self.active_blocksize = int(actual_blocksize)
                    except Exception:
                        self.active_input_samplerate = int(getattr(self, 'active_input_samplerate', self.sample_rate))
                        self.active_input_channels = int(getattr(self, 'active_input_channels', self.channels))
                        self.active_blocksize = int(getattr(self, 'active_blocksize', self.chunk_size))
                    theoretical_latency = (actual_blocksize / actual_sample_rate) * 1000
                    verified_latency = config.get('verified_latency', theoretical_latency)
                    
                    print(f"✅ {config['name']}启动成功:")
                    print(f"   ├─ 配置: {actual_sample_rate}Hz, {actual_blocksize}样本")
                    print(f"   ├─ 理论延迟: {theoretical_latency:.2f}ms")
                    print(f"   ├─ 验证延迟: {verified_latency}ms ⭐")
                    print(f"   ├─ 预期性能: {config['expected_latency']}")
                    print(f"   └─ 音频格式: float32")
                    
                    # 同步检测器采样率到实际输入采样率，避免频率缩放误差
                    try:
                        self._apply_actual_input_samplerate(actual_sample_rate)
                    except Exception:
                        pass

                    audio_stream_created = True
                    break
                    
                except Exception as e:
                    print(f"⚠️ {config['name']}失败: {str(e)[:100]}...")
                    continue
            
            if not audio_stream_created:
                raise Exception("所有音频驱动配置都失败，请检查音频设备")
            
            self.audio_stream.start()
            
            # 启动异步音频处理线程
            self.start_audio_processing_thread()
            
            self.is_recording = True
            
            start_msg = "开始录音和实时分析" if should_save else "开始实时分析（不保存）"
            self.status_updated.emit(start_msg)
            
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"启动录音失败: {e}")
            return False
    
    # 原process_audio_for_pitch方法已移除，使用异步版本process_audio_for_pitch_async
    
    def simple_pitch_detection(self, audio_data):
        """简单的音高检测（终极优化版本，适应32样本极小块处理）"""
        try:
            # 确保数据长度合适 - 针对32样本块优化
            if len(audio_data) < 32:
                return 0
            
            # 🚀 极小块处理优化：累积足够的数据再进行检测
            if not hasattr(self, '_audio_accumulator'):
                self._audio_accumulator = []
            
            self._audio_accumulator.extend(audio_data)
            
            # 累积到至少256样本再检测（减小等待，提升实时性）
            if len(self._audio_accumulator) < 256:
                return 0
            
            # 取最新的768样本进行检测（更短窗口降低延迟）
            detection_data = np.array(self._audio_accumulator[-768:])
            
            # 保持累积器在合理大小
            if len(self._audio_accumulator) > 2048:
                self._audio_accumulator = self._audio_accumulator[-1024:]
            
            # 如果启用GPU加速且可用，使用GPU处理
            if self.use_gpu_acceleration and self.gpu_processor and self.gpu_processor.is_gpu_available():
                try:
                    frequency, confidence = self.gpu_processor.accelerated_yin_detection(detection_data, 0.25)
                    if frequency > 60 and confidence > 0.3:
                        # GPU加速检测成功
                        if hasattr(self, '_gpu_debug_counter'):
                            self._gpu_debug_counter += 1
                            if self._gpu_debug_counter % 200 == 0:  # 减少打印频率
                                print(f"🚀 GPU检测: {frequency:.1f}Hz (置信度: {confidence:.2f})")
                        else:
                            self._gpu_debug_counter = 1
                            print("🚀 GPU音高检测开始（96kHz模式）")
                        return frequency
                except Exception as e:
                    print(f"⚠️ GPU检测失败，回退到CPU: {e}")
                    # 继续使用CPU处理
            
            # CPU处理：应用窗函数
            windowed = detection_data * np.hanning(len(detection_data))
            
            # 自相关方法检测音高
            correlation = np.correlate(windowed, windowed, mode='full')
            correlation = correlation[len(correlation)//2:]
            
            # 找到第一个峰值后的最大峰值
            # 改进：支持更宽的音高范围，适应96kHz采样率
            min_period = int(self.sample_rate / 2000)  # 降低上限提升鲁棒性
            max_period = int(self.sample_rate / 70)    # 提高低频稳定性
            
            if max_period < len(correlation):
                search_range = correlation[min_period:max_period]
                if len(search_range) > 0:
                    peak_index = np.argmax(search_range) + min_period
                    frequency = self.sample_rate / peak_index
                    
                    # 🎯 适应96kHz的检测阈值调整
                    if 60 <= frequency <= 3000:  # 更宽的频率范围
                        # 计算置信度（改进算法）
                        peak_correlation = correlation[peak_index]
                        base_correlation = correlation[0] if correlation[0] > 0 else 1e-10
                        confidence = peak_correlation / base_correlation
                        
                        if confidence > 0.15:  # 略微降低阈值提升灵敏度
                            # 每200次检测输出一次调试信息
                            if hasattr(self, '_cpu_debug_counter'):
                                self._cpu_debug_counter += 1
                                if self._cpu_debug_counter % 200 == 0:
                                    print(f"🎵 CPU检测: {frequency:.1f}Hz (置信度: {confidence:.2f}, 96kHz)")
                            else:
                                self._cpu_debug_counter = 1
                                print("� CPU音高检测开始（96kHz模式）")
                            return frequency
                        else:
                            # 低置信度，可能是噪声
                            if hasattr(self, '_low_confidence_counter'):
                                self._low_confidence_counter += 1
                                if self._low_confidence_counter % 300 == 0:  # 减少低置信度打印
                                    print(f"🔍 过滤低置信度: {frequency:.1f}Hz (置信度: {confidence:.3f})")
                            else:
                                self._low_confidence_counter = 1
            
            return 0
                
        except Exception as e:
            print(f"音高检测错误: {e}")
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
            
            # 🎯 如果全局监听模式激活，不要停止音频流，只停止录音
            if self.is_global_monitoring_active:
                print("🎯 全局监听模式激活中，只停止录音功能，保持监听")
                
                # 🔥 重要：恢复纯监听模式状态
                self.is_monitoring_only = True
                
                # 后台保存录音文件（如果需要）以避免UI阻塞
                output_file = None
                # 预先准备分析结果与快照，避免后续状态改变
                analysis_results = {
                    'total_pitches': len(self.pitch_history),
                    'recording_duration': self.current_duration,
                    'pitches': [p.get('frequency', 0) for p in self.pitch_history],
                    'timestamps': [p.get('timestamp', 0) for p in self.pitch_history],
                    'confidences': [p.get('confidence', 0.8) for p in self.pitch_history],
                    'note_sequence': [p.get('note_info', {}) for p in self.pitch_history]
                }
                if self.should_save and self.audio_buffer and self.recording_filename:
                    try:
                        import threading as _th
                        # 捕获快照，避免后续监听继续时缓冲被修改
                        _buf = np.array(self.audio_buffer, dtype=np.float32)
                        _pitches = list(self.pitch_history)
                        _fname = self.recording_filename
                        _sr = int(getattr(self, 'active_input_samplerate', self.sample_rate))
                        _ch = int(getattr(self, 'active_input_channels', self.channels))
                        _dur = float(self.current_duration)
                        def _bg_save():
                            try:
                                out_path = self._save_recording_snapshot(_fname, _sr, _ch, _buf, _pitches, _dur)
                                self.recording_finished.emit(out_path or "", analysis_results)
                                self.status_updated.emit("录音完成，监听继续")
                            except Exception as _e:
                                self.error_occurred.emit(f"后台保存录音失败: {_e}")
                        t = _th.Thread(target=_bg_save, daemon=True)
                        t.start()
                        self.status_updated.emit("录音完成，正在后台保存...")
                        return
                    except Exception as _e:
                        # 快照失败则回退同步保存
                        output_file = self.save_recording()
                        self.recording_finished.emit(output_file or "", analysis_results)
                        self.status_updated.emit("录音完成，监听继续")
                        return
                else:
                    # 不需要保存，直接结束
                    self.recording_finished.emit("", analysis_results)
                    self.status_updated.emit("录音完成，监听继续")
                    return
            
            # 非全局监听模式：正常停止流程
            # 停止异步音频处理线程
            self.stop_audio_processing_thread()
            
            if self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
                self.audio_stream = None
            
            # 保存录音文件（异步后台）
            output_file = None
            # 准备分析结果（添加安全检查）
            analysis_results = {
                'total_pitches': len(self.pitch_history),
                'recording_duration': self.current_duration,
                'pitches': [p.get('frequency', 0) for p in self.pitch_history],
                'timestamps': [p.get('timestamp', 0) for p in self.pitch_history],
                'confidences': [p.get('confidence', 0.8) for p in self.pitch_history],
                'note_sequence': [p.get('note_info', {}) for p in self.pitch_history]
            }
            if self.should_save and self.audio_buffer and self.recording_filename:
                try:
                    import threading as _th
                    _buf = np.array(self.audio_buffer, dtype=np.float32)
                    _pitches = list(self.pitch_history)
                    _fname = self.recording_filename
                    _sr = int(getattr(self, 'active_input_samplerate', self.sample_rate))
                    _ch = int(getattr(self, 'active_input_channels', self.channels))
                    _dur = float(self.current_duration)
                    def _bg_save2():
                        try:
                            out_path = self._save_recording_snapshot(_fname, _sr, _ch, _buf, _pitches, _dur)
                            self.recording_finished.emit(out_path or "", analysis_results)
                            self.status_updated.emit("录音和分析完成")
                        except Exception as _e:
                            self.error_occurred.emit(f"后台保存录音失败: {_e}")
                    _t = _th.Thread(target=_bg_save2, daemon=True)
                    _t.start()
                    self.status_updated.emit("录音结束，正在后台保存...")
                    return
                except Exception as _e:
                    # 快照失败则同步保存
                    output_file = self.save_recording()
                    self.recording_finished.emit(output_file or "", analysis_results)
                    self.status_updated.emit("录音和分析完成")
                    return
            else:
                # 不保存时直接结束
                self.recording_finished.emit("", analysis_results)
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

            # 使用实际输入采样率与声道数
            _sr = int(getattr(self, 'active_input_samplerate', self.sample_rate))
            _ch = int(getattr(self, 'active_input_channels', self.channels))
            with wave.open(str(output_path), 'wb') as wav_file:
                wav_file.setnchannels(_ch)
                wav_file.setsampwidth(2)  # 16位
                wav_file.setframerate(_sr)

                # 转换为16位整数
                audio_int16 = (audio_array * 32767).astype(np.int16)
                wav_file.writeframes(audio_int16.tobytes())

            # 保存分析结果
            analysis_path = output_path.with_suffix('.json')
            analysis_data = {
                'recording_info': {
                    'filename': self.recording_filename,
                    'sample_rate': _sr,
                    'channels': _ch,
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

    def _save_recording_snapshot(self, filename: str, sample_rate: int, channels: int,
                                 audio_array: np.ndarray, pitch_history: list, duration: float) -> str:
        """使用提供的快照数据保存录音与分析，避免与实时状态竞争。返回保存的wav路径。"""
        try:
            recordings_dir = project_root / "recordings"
            recordings_dir.mkdir(exist_ok=True)
            if not filename.endswith('.wav'):
                filename = filename + '.wav'
            output_path = recordings_dir / filename
            # 保存WAV
            with wave.open(str(output_path), 'wb') as wav_file:
                wav_file.setnchannels(int(channels))
                wav_file.setsampwidth(2)
                wav_file.setframerate(int(sample_rate))
                audio_int16 = (audio_array * 32767).astype(np.int16)
                wav_file.writeframes(audio_int16.tobytes())
            # 保存分析
            analysis_path = output_path.with_suffix('.json')
            analysis_data = {
                'recording_info': {
                    'filename': filename,
                    'sample_rate': int(sample_rate),
                    'channels': int(channels),
                    'duration': float(duration),
                    'total_samples': int(len(audio_array))
                },
                'pitch_analysis': {
                    'total_detections': len(pitch_history),
                    'detection_rate': (len(pitch_history) / max(float(duration), 1.0)),
                    'pitch_data': list(pitch_history)
                }
            }
            with open(analysis_path, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, indent=2, ensure_ascii=False)
            return str(output_path)
        except Exception as e:
            self.error_occurred.emit(f"保存录音失败: {e}")
            return ""

    # 🔥 智能噪声抑制类（极简版本，减少电流音）
    class NoiseSuppressor:
        """智能噪声抑制器（极简版本，专注减少电流音）"""
        def __init__(self, sr=48000):
            self.sample_rate = sr
            self.noise_floor = 0.001
            
        def update_profile(self, noise_sample):
            """更新噪声样本"""
            if len(noise_sample) > 0:
                self.noise_floor = np.sqrt(np.mean(np.square(noise_sample)))
        
        def process(self, audio_data):
            """极简降噪处理，主要防止电流音"""
            if len(audio_data) == 0:
                return audio_data
                
            try:
                # 🔥 只做最基本的处理
                signal_power = np.mean(np.square(audio_data))
                
                # 🔥 极弱信号直接静音
                if signal_power < 0.000001:
                    return np.zeros_like(audio_data)
                
                # 🔥 检测异常高频噪声（电流音特征）
                if len(audio_data) > 3:
                    high_freq_diff = np.sum(np.abs(np.diff(audio_data, 2)))  # 二阶差分
                    if high_freq_diff > signal_power * 1000:  # 异常高频成分
                        # 简单平滑滤除高频噪声
                        filtered = np.zeros_like(audio_data)
                        filtered[0] = audio_data[0]
                        filtered[-1] = audio_data[-1]
                        for i in range(1, len(audio_data)-1):
                            filtered[i] = (audio_data[i-1] + audio_data[i] + audio_data[i+1]) / 3
                        return filtered * 0.8
                
                # 🔥 正常信号直接返回，不做额外处理
                return audio_data
                
            except Exception:
                # 处理失败时直接返回原信号
                return audio_data

    def start_monitoring(self):
        """启动监听功能（只分析，不录音）- 全局监听模式"""
        try:
            # 🎯 如果已经有监听在运行，先停止
            if self.is_global_monitoring_active:
                print("🔄 检测到已有监听模式运行，先停止现有监听...")
                self.stop_monitoring()
            
            # 监听模式的关键：不保存录音，只做实时分析
            self.recording_filename = None
            self.should_save = False
            self.is_recording = False  # 不是录音状态
            self.audio_buffer = []
            self.pitch_history.clear()
            self.recording_start_time = time.time()
            
            # 🎯 设置全局监听状态
            self.is_global_monitoring_active = True
            self.monitoring_mode = 'basic'
            # 🔥 关键设置：纯监听模式，不生成音调线
            self.is_monitoring_only = True
            self.enable_pitch_visualization = False
            
            # 设置分析器
            if not self.setup_analyzers():
                return False
            
            print("🎧 正在启动监听模式...")
            
            # 启动音频流（复用录音的音频回调，但不保存数据）
            try:
                import sounddevice as sd
                
                # 音频回调函数（与录音相同，但不保存）
                def monitoring_callback(indata, frames, time_info, status):
                    # 🎯 开始延迟监控
                    callback_start_time = time.time()
                    
                    if status:
                        if 'input overflow' not in str(status).lower():
                            print(f"🔊 监听音频状态: {status}")
                    
                    # 获取单声道数据
                    if self.channels == 1 and indata.shape[1] > 1:
                        audio_data = np.mean(indata, axis=1)
                    else:
                        audio_data = indata[:, 0] if len(indata.shape) > 1 else indata
                    
                    # 🎯 监听模式的大音量稳定性优化
                    try:
                        # 计算RMS和峰值
                        rms = np.sqrt(np.mean(audio_data ** 2))
                        peak = np.max(np.abs(audio_data))
                        
                        # 智能削峰限制
                        if peak > 0.95:
                            audio_data = np.tanh(audio_data * 0.8) * 0.9
                        
                        # 动态范围压缩
                        if rms > 0.5:  # 大音量压缩
                            audio_data = audio_data * 0.6
                        elif rms < 0.05:  # 小音量增强
                            enhancement_ratio = min(2.0, 0.05 / max(rms, 0.001))
                            audio_data = audio_data * enhancement_ratio
                        
                        # 最终安全限制
                        audio_data = np.clip(audio_data, -1.0, 1.0)
                        
                    except Exception as e:
                        # 基本削峰保护
                        audio_data = np.clip(audio_data, -1.0, 1.0)
                    
                    # 🎯 处理监听和录音（全局模式）
                    try:
                        # 判断是否需要保存音频数据
                        should_save_audio = self.is_recording and self.should_save
                        
                        if not self.audio_buffer_queue.full():
                            self.audio_buffer_queue.put_nowait({
                                'data': audio_data.copy(),
                                'timestamp': time.time(),
                                'should_save': should_save_audio  # 根据录音状态决定是否保存
                            })
                        else:
                            # 队列满时，移除最老的数据
                            try:
                                self.audio_buffer_queue.get_nowait()
                                self.audio_buffer_queue.put_nowait({
                                    'data': audio_data.copy(),
                                    'timestamp': time.time(),
                                    'should_save': should_save_audio
                                })
                            except queue.Empty:
                                pass
                        
                        # 注意：录音缓冲区由处理线程统一写入，避免回调与线程重复写入导致时长/音质问题
                            
                    except Exception as e:
                        print(f"监听队列错误: {e}")
                    
                    # 计算音频电平
                    try:
                        audio_level = np.sqrt(np.mean(audio_data ** 2))
                        if not self.isFinished():
                            self.audio_level_updated.emit(float(audio_level))
                    except RuntimeError:
                        return
                    
                    # 🎯 监听模式延迟监控
                    callback_end_time = time.time()
                    monitoring_processing_time = (callback_end_time - callback_start_time) * 1000
                    
                    # 累积监听处理时间
                    if not hasattr(self, '_monitoring_processing_times'):
                        self._monitoring_processing_times = []
                        self._monitoring_callback_counter = 0
                    
                    self._monitoring_processing_times.append(monitoring_processing_time)
                    self._monitoring_callback_counter += 1
                    
                    # 保持处理时间历史在合理大小
                    if len(self._monitoring_processing_times) > 100:
                        self._monitoring_processing_times = self._monitoring_processing_times[-50:]
                    
                    # 延迟报告节流：每800次或显著超出理论延迟(>理论+0.5ms)
                    theoretical_latency = (self.chunk_size / self.sample_rate) * 1000
                    avg_monitoring_time = np.mean(self._monitoring_processing_times)
                    max_monitoring_time = np.max(self._monitoring_processing_times)
                    total_monitoring_latency = theoretical_latency + avg_monitoring_time
                    need_report = (self._monitoring_callback_counter % 800 == 0) or (total_monitoring_latency > theoretical_latency + 0.5)
                    if need_report:
                        self._log_rate_limit('latency_report', f"🎧 延迟#{self._monitoring_callback_counter} 理论:{theoretical_latency:.2f}ms 处理:{avg_monitoring_time:.2f}/{max_monitoring_time:.2f}ms 总:{total_monitoring_latency:.2f}ms", interval=1.0, burst=1)
                        if total_monitoring_latency > 1.0:
                            if self.debug_flags.get('latency_warn_verbose'):
                                self._log_rate_limit('high_latency_monitor', f"⚠️ 监听延迟偏高 {total_monitoring_latency:.2f}ms", interval=1.0)
                            self._stat_counters['high_latency'] += 1
                        else:
                            self._log_rate_limit('latency_ok_monitor', f"✅ 监听延迟良好 {total_monitoring_latency:.2f}ms", interval=2.0)
                        self._monitoring_processing_times = []
                
                # 创建专业级低延迟音频流（监听模式智能配置）
                monitoring_stream_created = False
                
                # 🚀 监听模式专业音频配置（动态WASAPI设备发现版本）
                monitoring_configs = [
                    # 第一优先级：ASIO专业驱动（监听专用）
                    {
                        'name': 'ASIO专业监听',
                        'settings': sd.AsioSettings(channel_selectors=[0]),
                        'latency_class': 'ultra-low'
                    }
                ]
                
                # 动态添加WASAPI监听配置
                wasapi_configs = self._get_optimal_wasapi_configs()
                for config in wasapi_configs:
                    monitoring_configs.append({
                        'name': f"{config['name']}监听",
                        'device': config['device'],
                        'samplerate': config['samplerate'],
                        'blocksize': config['blocksize'],
                        'settings': config['settings'],  # 🔧 修复：直接使用对象，不调用
                        'latency_class': config['expected_latency'],
                        'verified_latency': config.get('verified_latency')
                    })
                
                # 添加DirectSound兼容配置
                monitoring_configs.append({
                    'name': 'DirectSound监听',
                    'settings': None,
                    'latency_class': 'medium'
                })
                
                # 基于真实设备跑分对配置进行智能排序（先快又稳）
                try:
                    monitoring_configs = self._rank_monitoring_configs(monitoring_configs)
                except Exception as _rank_e:
                    print(f"⚠️ 监听配置排序跳过: {_rank_e}")

                for config in monitoring_configs:
                    try:
                        # 构建监听流参数
                        stream_params = {
                            'channels': self.channels,
                            'callback': monitoring_callback,
                            'dtype': np.float32,
                            'latency': 'low'
                        }
                        
                        # 为WASAPI设备使用测试验证的参数
                        if 'device' in config and 'samplerate' in config:
                            stream_params['device'] = config['device']
                            stream_params['samplerate'] = config['samplerate']
                            stream_params['blocksize'] = config.get('blocksize', self.chunk_size)
                            verified_latency = config.get('verified_latency', 'unknown')
                            print(f"🎯 监听使用WASAPI设备{config['device']}@{config['samplerate']}Hz (验证延迟: {verified_latency}ms)")
                        else:
                            stream_params['samplerate'] = self.sample_rate
                            stream_params['blocksize'] = self.chunk_size
                        
                        # 添加特定驱动设置
                        if config['settings']:
                            stream_params['extra_settings'] = config['settings']
                        
                        # 创建监听音频流
                        self.audio_stream = sd.InputStream(**stream_params)
                        
                        # 计算实际延迟（使用实际参数）
                        actual_sample_rate = stream_params['samplerate']
                        actual_blocksize = stream_params['blocksize']
                        # 记录实际输入参数供保存与统计使用
                        try:
                            self.active_input_samplerate = int(actual_sample_rate)
                            self.active_input_channels = int(stream_params.get('channels', self.channels))
                            self.active_blocksize = int(actual_blocksize)
                        except Exception:
                            self.active_input_samplerate = int(getattr(self, 'active_input_samplerate', self.sample_rate))
                            self.active_input_channels = int(getattr(self, 'active_input_channels', self.channels))
                            self.active_blocksize = int(getattr(self, 'active_blocksize', self.chunk_size))
                        theoretical_latency = (actual_blocksize / actual_sample_rate) * 1000
                        verified_latency = config.get('verified_latency', theoretical_latency)
                        
                        print(f"✅ {config['name']}启动成功:")
                        print(f"   ├─ 配置: {actual_sample_rate}Hz, {actual_blocksize}样本")
                        print(f"   ├─ 理论延迟: {theoretical_latency:.2f}ms")
                        print(f"   ├─ 验证延迟: {verified_latency}ms ⭐")
                        print(f"   ├─ 性能级别: {config['latency_class']}")
                        print(f"   └─ 音频格式: float32")
                        
                        monitoring_stream_created = True
                        break
                        
                    except Exception as config_error:
                        print(f"⚠️ {config['name']}失败: {str(config_error)[:100]}...")
                        continue
                
                if not monitoring_stream_created:
                    raise Exception("所有监听音频驱动配置都失败")
                
                # 🎯 使用统一的音频流管理
                self.active_audio_stream = self.audio_stream
                self.active_audio_stream.start()
                # 记录监控流的实际参数
                try:
                    self.active_input_samplerate = int(getattr(self, 'active_input_samplerate', 0) or getattr(self.audio_stream, 'samplerate', None) or stream_params.get('samplerate', self.sample_rate))
                except Exception:
                    self.active_input_samplerate = int(self.sample_rate)
                try:
                    self.active_input_channels = int(getattr(self, 'active_input_channels', 0) or getattr(self.audio_stream, 'channels', None) or stream_params.get('channels', self.channels))
                except Exception:
                    self.active_input_channels = int(self.channels)
                try:
                    self.active_blocksize = int(getattr(self, 'active_blocksize', 0) or stream_params.get('blocksize', self.chunk_size))
                except Exception:
                    self.active_blocksize = int(self.chunk_size)
                print(f"🎧 全局监听音频流已启动: {self.active_input_samplerate}Hz, {self.active_input_channels}声道, 块大小{self.active_blocksize}")
                
                # 启动音频处理线程
                # 启动前同步检测器采样率
                try:
                    self._apply_actual_input_samplerate(self.active_input_samplerate)
                except Exception:
                    pass
                self.start_audio_processing_thread()
                
                print("✅ 全局监听模式已激活，优先级最高")
                self.status_updated.emit("全局监听模式已启动")
                return True
                
            except Exception as e:
                print(f"❌ 启动监听音频流失败: {e}")
                self.is_global_monitoring_active = False
                return False
                
        except Exception as e:
            print(f"❌ 启动监听功能失败: {e}")
            self.is_global_monitoring_active = False
            self.error_occurred.emit(f"启动监听失败: {e}")
            return False
    
    def stop_monitoring(self):
        """停止监听功能"""
        try:
            print("🛑 正在停止全局监听模式...")
            
            # 停止音频处理线程
            self.stop_audio_processing_thread()
            
            # 🎯 统一音频流管理 - 停止所有音频流
            if self.active_audio_stream:
                self.active_audio_stream.stop()
                self.active_audio_stream.close()
                self.active_audio_stream = None
                print("🎧 全局音频流已停止")
                
            # 兼容性：也检查旧的音频流
            if self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
                self.audio_stream = None
                
            if self.monitoring_stream:
                self.monitoring_stream.stop()
                self.monitoring_stream.close()
                self.monitoring_stream = None
            
            # 🎯 重置全局监听状态
            self.is_global_monitoring_active = False
            self.monitoring_mode = None
            self.is_monitoring_only = False  # 🔥 重置监听标志
            
            print("✅ 全局监听模式已停止")
            self.status_updated.emit("监听已停止")
            
        except Exception as e:
            print(f"❌ 停止监听功能失败: {e}")
            self.error_occurred.emit(f"停止监听失败: {e}")

    def start_unified_monitoring(self):
        """启动HECATE G4 Pro优化监听：基于设备33最优配置"""
        try:
            import sounddevice as sd
            import numpy as np
            
            # 🎯 检查全局监听状态 - 如果已有监听运行，继续使用
            if self.is_global_monitoring_active:
                print("� 检测到全局监听模式已激活，跳过重复启动")
                self.status_updated.emit("监听模式已运行中")
                return True
            
            print("�🎧 正在启动HECATE G4 Pro优化监听...")
            
            # 启动WASAPI诊断系统
            self.diagnose_wasapi_issues()
            
            # 🔧 HECATE监听模式配置（基于诊断结果优化）
            self.monitoring_filename = None
            self.monitoring_should_save = False
            self.is_monitoring_only = True
            self.audio_buffer = []
            self.channels = 1  # HECATE优化：单声道
            self.enable_pitch_visualization = False
            
            # 🎯 设置全局监听状态
            self.is_global_monitoring_active = True
            self.monitoring_mode = 'unified'
            
            # 清理历史数据
            if hasattr(self, 'pitch_history'):
                self.pitch_history.clear()
            self.recording_start_time = time.time()
            
            # � HECATE优化监听回调：基于设备33测试结果
            def hecate_optimized_callback(indata, outdata, frames, time_info, status):
                """HECATE G4 Pro优化回调：192kHz/32样本/0.17ms延迟"""
                try:
                    # 音频数据处理
                    if self.channels == 1 and indata.shape[1] > 1:
                        raw_audio = (indata[:, 0] + indata[:, 1]) * 0.5
                    else:
                        raw_audio = indata[:, 0] if len(indata.shape) > 1 else indata.flatten()

                    # 👉 关键差异修复：录音直接模式与监听模式音高结果差异大的根源之一
                    # 之前：监听路径对原始数据做了多步增益/平滑后才入队，导致波形被改写 => 音高不同
                    # 现在：始终把“原始未处理”数据(raw_audio)送入分析队列，独立于监听增强处理
                    audio_data = raw_audio.copy()
                    
                    # 智能音量增强（基于HECATE特性优化）
                    if hasattr(self, 'hecate_volume_booster') and self.hecate_volume_booster['enabled']:
                        rms = np.sqrt(np.mean(audio_data ** 2))
                        
                        if rms > self.hecate_volume_booster['noise_gate']:
                            target_level = self.hecate_volume_booster['target_level']
                            
                            # HECATE专用增益算法（针对192kHz优化）
                            if rms < target_level * 0.4:
                                target_gain = min(1.6, target_level * 0.6 / max(rms, 0.002))
                            else:
                                target_gain = max(0.95, min(1.1, target_level / rms))
                            
                            # 平滑增益变化
                            current_gain = self.hecate_volume_booster.get('current_gain', 1.0)
                            smooth_factor = 0.92  # HECATE快速响应
                            new_gain = current_gain * smooth_factor + target_gain * (1 - smooth_factor)
                            self.hecate_volume_booster['current_gain'] = new_gain
                            
                            if new_gain > 1.02:
                                audio_data = audio_data * new_gain
                                # 峰值保护
                                peak = np.max(np.abs(audio_data))
                                if peak > 0.94:
                                    audio_data = audio_data * (0.92 / peak)
                        else:
                            # 微弱信号处理
                            audio_data = audio_data * 0.8
                    
                    # 高频稳定性处理（HECATE电流音优化）
                    if len(audio_data) > 4:
                        high_freq_diff = np.sum(np.abs(np.diff(audio_data, 2)))
                        total_energy = np.sum(np.abs(audio_data))
                        
                        if total_energy > 1e-8:
                            noise_ratio = high_freq_diff / total_energy
                            if noise_ratio > 12.0:  # HECATE电流音检测阈值
                                smoothed = np.copy(audio_data)
                                smoothed[1:-1] = (audio_data[:-2] + audio_data[1:-1] + audio_data[2:]) / 3.0
                                audio_data = audio_data * 0.75 + smoothed * 0.25
                    
                    # 🎯 处理录音需求（在全局监听模式下）
                    try:
                        if self.is_recording and self.should_save:
                            self.audio_buffer.extend(audio_data)
                        
            # 🔥 重要修复：分析用队列使用 raw_audio 保持与纯录音一致
                        if not self.audio_buffer_queue.full():
                            self.audio_buffer_queue.put_nowait({
                'data': raw_audio.copy(),
                                'timestamp': time.time(),
                                'should_save': self.is_recording and self.should_save
                            })
                            
                            # 🔥 强制调试：确认数据入队成功
                            if not hasattr(self, '_hecate_queue_debug_counter'):
                                self._hecate_queue_debug_counter = 0
                                print("🔥 HECATE回调首次数据入队成功!")
                            
                            self._hecate_queue_debug_counter += 1
                            if self._hecate_queue_debug_counter % 1000 == 0:
                                queue_size = self.audio_buffer_queue.qsize()
                                if getattr(self, 'debug_flags', {}).get('queue_log', False):
                                    print(f"🔥 HECATE入队#{self._hecate_queue_debug_counter}: 队列大小={queue_size}")
                        else:
                            if not hasattr(self, '_hecate_queue_full_warned'):
                                print("⚠️ HECATE: 音频队列已满")
                                self._hecate_queue_full_warned = True
                                
                    except Exception as process_error:
                        print(f"⚠️ HECATE音频处理错误: {process_error}")
                    
                    # 音频输出（仅在启用监听回传时）
                    if self.monitor_audio_passthrough:
                        # RAW直通：最小处理，仅保留安全头房+VRMS限幅
                        if getattr(self, 'monitor_raw_mode', False):
                            audio_out = raw_audio.copy()
                        else:
                            # 仅对耳返音频在低RMS呼吸段进行轻量抑制，不影响 raw_audio 入队
                            audio_out = self._apply_breath_noise_suppress(audio_data, key='hecate')
                        # 安全头房 + VRMS限幅（无感）
                        audio_out = self._apply_headroom_and_vrms(audio_out, key='hecate')
                        if outdata.shape[1] == 1:
                            outdata[:, 0] = audio_out  # 输出仍可用增强/平滑后的版本
                        else:
                            outdata[:, 0] = audio_out
                            outdata[:, 1] = audio_out
                    else:
                        outdata.fill(0)
                        
                except Exception as e:
                    outdata.fill(0)
                    print(f"⚠️ HECATE回调错误: {e}")
            
            # HECATE音量增强配置
            self.hecate_volume_booster = {
                'enabled': True,
                'target_level': 0.25,
                'noise_gate': 0.003,
                'current_gain': 1.0
            }
            
            # 🎯 HECATE设备配置：优先使用设备33最优配置
            hecate_mapper = HecateDeviceMapper()
            hecate_available = hecate_mapper.verify_hecate_available()
            
            if hecate_available:
                print("🎯 检测到HECATE G4 Pro，使用专用优化配置")
                optimal_config = hecate_mapper.get_working_hecate_config()
                
                if optimal_config:
                    print(f"⭐ 使用最优HECATE配置：设备{optimal_config['device_id']}@{optimal_config['samplerate']}Hz/{optimal_config['blocksize']}样本")
                    
                    # 🔧 智能设备能力检测和配置优化
                    try:
                        device_info = sd.query_devices(optimal_config['device_id'])
                        max_input_channels = device_info.get('max_input_channels', 2)
                        default_samplerate = device_info.get('default_samplerate', 44100)
                        device_name = device_info.get('name', 'Unknown')
                        host_api = device_info.get('hostapi', -1)
                        
                        print(f"📊 设备{optimal_config['device_id']}智能分析:")
                        print(f"   ├─ 设备名称: {device_name}")
                        print(f"   ├─ 最大输入通道: {max_input_channels}")
                        print(f"   ├─ 默认采样率: {default_samplerate}Hz")
                        print(f"   ├─ 主机API: {host_api} ({'MME' if host_api == 0 else 'DirectSound' if host_api == 1 else 'WASAPI' if host_api == 2 else 'Unknown'})")
                        print(f"   └─ 设备类型: {'输入设备' if max_input_channels > 0 else '输出设备'}")
                        
                        # 智能过滤：跳过无输入通道的设备
                        if max_input_channels == 0:
                            print(f"⚠️ 设备{optimal_config['device_id']}无输入通道，跳过HECATE优化")
                            print("🔄 将尝试其他HECATE输入设备...")
                            # 跳转到后续的备用设备搜索
                        else:
                            # 自动调整通道数到设备支持的最大值
                            optimal_channels = min(self.channels, max_input_channels) if max_input_channels > 0 else 1
                            if optimal_channels != self.channels:
                                print(f"🔧 智能调整通道数: {self.channels} → {optimal_channels}")
                                self.channels = optimal_channels
                            
                            # ==== 改进的智能采样率探测（优先真实可用 + 原生速率）====
                            def _probe_first_supported(rates, block_sizes=(64,128,256,512)):
                                for sr in rates:
                                    for bs in block_sizes:
                                        try:
                                            tmp = sd.InputStream(device=optimal_config['device_id'], channels=1, samplerate=sr, blocksize=bs, dtype=np.float32)
                                            tmp.close()
                                            return sr, bs
                                        except Exception:
                                            continue
                                return None, None

                            # 优先顺序：设备默认 / 192k / 96k / 48k / 44.1k （去重）
                            candidate_rates = []
                            for r in [default_samplerate, 192000, 96000, 48000, 44100]:
                                if isinstance(r, (int, float)) and r > 0 and r not in candidate_rates and r <= default_samplerate + 1:  # 允许默认略浮点
                                    candidate_rates.append(int(r))
                            probed_sr, probed_bs = _probe_first_supported(candidate_rates)
                            if probed_sr is None:
                                # 回退策略：再放宽一次，不限制 <= default_samplerate 逻辑
                                for r in [192000, 96000, 48000, 44100]:
                                    if r not in candidate_rates:
                                        candidate_rates.append(r)
                                probed_sr, probed_bs = _probe_first_supported(candidate_rates)
                            if probed_sr is None:
                                optimal_samplerate = 48000
                                probed_bs = 256
                                print("⚠️ 采样率快速探测全部失败，使用保守 48kHz/256")
                            else:
                                optimal_samplerate = probed_sr
                                print(f"🔧 智能采样率选择: {optimal_samplerate}Hz (探测块大小建议: {probed_bs})")
                            
                            # 基于主机API优化WASAPI设置
                            wasapi_available = (host_api == 2)  # 只有WASAPI主机API才支持WASAPI设置
                            
                            if wasapi_available:
                                # 测试WASAPI兼容性
                                try:
                                    test_stream = sd.InputStream(
                                        device=optimal_config['device_id'],
                                        channels=optimal_channels,
                                        samplerate=optimal_samplerate,
                                        blocksize=512,
                                        dtype=np.float32,
                                        extra_settings=sd.WasapiSettings(exclusive=False)
                                    )
                                    test_stream.close()
                                    print("✅ WASAPI兼容性测试通过")
                                except Exception as wasapi_test_error:
                                    print(f"⚠️ WASAPI不兼容: {wasapi_test_error}")
                                    wasapi_available = False
                            else:
                                print(f"ℹ️ 设备使用{['MME', 'DirectSound', 'WASAPI'][host_api]}主机API，跳过WASAPI测试")
                        
                    except Exception as capability_error:
                        print(f"⚠️ 设备能力检测失败: {capability_error}")
                        # 使用保守的默认值
                        max_input_channels = 1
                        default_samplerate = 44100
                        optimal_samplerate = 44100
                        optimal_channels = 1
                        wasapi_available = False
                    
                    # 构建智能配置序列：从最高性能到兼容（先尝试原生最佳）
                    hecate_configs = []

                    # ==== 新增：输出设备自动匹配（用于全双工监听回传）====
                    def _find_hecate_output_device():
                        try:
                            devices = sd.query_devices()
                            candidates = []
                            for idx, dev in enumerate(devices):
                                name = dev.get('name','').lower()
                                if dev.get('max_output_channels',0) > 0:
                                    # 优先同品牌 + WASAPI
                                    score = 0
                                    if 'hecate' in name: score += 20
                                    if 'g4 pro' in name: score += 10
                                    if dev.get('hostapi') == 2: score += 15
                                    candidates.append((score, idx, dev))
                            if not candidates:
                                return None
                            candidates.sort(reverse=True)
                            return candidates[0][1]
                        except Exception:
                            return None

                    output_device_id = _find_hecate_output_device()
                    if output_device_id is None:
                        # 退回默认输出设备
                        try:
                            default_in, default_out = sd.default.device
                            output_device_id = default_out
                        except Exception:
                            output_device_id = None
                    if output_device_id is not None:
                        print(f"🔎 绑定输出设备用于监听回传: {output_device_id}")
                    else:
                        print("⚠️ 未找到合适输出设备，回传监听将停用（仅采集输入）")

                    # 原生性能模式（若探测得出192k或设备默认值且已通过初步探测）
                    if 'optimal_samplerate' in locals() and optimal_samplerate >= 96000 and default_samplerate >= optimal_samplerate:
                        hecate_configs.append({
                            'input_device': optimal_config['device_id'],
                            'output_device': output_device_id,
                            'input_channels': optimal_channels,
                            'output_channels': 2 if output_device_id is not None else 0,
                            'samplerate': optimal_samplerate,
                            'blocksize': 64 if optimal_samplerate >= 96000 else 128,
                            'callback': hecate_optimized_callback,
                            'dtype': np.float32,
                            'latency': 'low',
                            'name': '原生性能模式'
                        })
                    
                    # 配置1：最高兼容性模式（DirectSound/MME）
                    hecate_configs.append({
                        'input_device': optimal_config['device_id'],
                        'output_device': output_device_id,
                        'input_channels': 1,  # 强制单声道提高兼容性
                        'output_channels': 2 if output_device_id is not None else 0,
                        'samplerate': 44100,  # 最兼容的采样率
                        'blocksize': 1024,  # 大缓冲区提高稳定性
                        'callback': hecate_optimized_callback,
                        'dtype': np.float32,
                        'name': '最高兼容性模式'
                    })
                    
                    # 配置2：平衡模式（使用探测到的 optimal_samplerate 与探测建议块）
                    hecate_configs.append({
                        'input_device': optimal_config['device_id'],
                        'output_device': output_device_id,
                        'input_channels': optimal_channels,
                        'output_channels': 2 if output_device_id is not None else 0,
                        'samplerate': optimal_samplerate,
                        'blocksize': min(512, probed_bs if 'probed_bs' in locals() and probed_bs else 512),
                        'callback': hecate_optimized_callback,
                        'dtype': np.float32,
                        'latency': 'low',
                        'name': '平衡性能模式'
                    })
                    
                    # 配置3：WASAPI共享模式（仅在WASAPI可用时）
                    if wasapi_available:
                        hecate_configs.append({
                            'input_device': optimal_config['device_id'],
                            'output_device': output_device_id,
                            'input_channels': optimal_channels,
                            'output_channels': 2 if output_device_id is not None else 0,
                            'samplerate': optimal_samplerate,
                            'blocksize': 256,
                            'callback': hecate_optimized_callback,
                            'dtype': np.float32,
                            'latency': 'low',
                            'extra_settings': sd.WasapiSettings(exclusive=False),
                            'name': 'WASAPI共享模式'
                        })
                    
            # 配置4：WASAPI独占模式（仅在WASAPI可用且是纯输入设备时）
                    if wasapi_available and max_input_channels > 0:
                        hecate_configs.append({
                            'input_device': optimal_config['device_id'],
                            'output_device': output_device_id,
                            'input_channels': optimal_channels,
                            'output_channels': 2 if output_device_id is not None else 0,
                'samplerate': min(max(optimal_samplerate, 44100), 192000),  # 放宽上限，若192k已探测通过则使用
                'blocksize': 128 if optimal_samplerate < 96000 else 64,
                            'callback': hecate_optimized_callback,
                            'dtype': np.float32,
                            'latency': 'low',
                            'extra_settings': sd.WasapiSettings(exclusive=True),
                            'name': 'WASAPI独占模式'
                        })
                    
                    print(f"🔧 准备测试{len(hecate_configs)}种智能HECATE配置...")
                    
                    # 尝试每个配置
                    for i, stream_params in enumerate(hecate_configs):
                        try:
                            print(f"🔧 尝试HECATE配置 {i+1}/{len(hecate_configs)}: {stream_params['name']}")
                            
                            # 移除name键用于创建stream
                            config_name = stream_params.pop('name')
                            build_copy = stream_params.copy()
                            # 统一构造 sounddevice 参数
                            def _construct_stream_args(cfg: dict):
                                args = {}
                                # samplerate / blocksize / dtype / latency / callback / extra_settings
                                for k in ['samplerate','blocksize','dtype','latency','callback','extra_settings']:
                                    if k in cfg and cfg[k] is not None:
                                        # extra_settings 可能是 WasapiSettings/AsioSettings
                                        if k == 'latency' and cfg[k] is None:
                                            continue
                                        if k == 'extra_settings':
                                            args['extra_settings'] = cfg[k]
                                        else:
                                            args[k] = cfg[k]
                                # 设备与通道
                                in_dev = cfg.get('input_device')
                                out_dev = cfg.get('output_device')
                                in_ch = cfg.get('input_channels', 1)
                                out_ch = cfg.get('output_channels', 0)
                                if out_dev is not None and out_ch > 0:
                                    args['device'] = (in_dev, out_dev)
                                    args['channels'] = (in_ch, out_ch)
                                else:
                                    # 仅输入
                                    args['device'] = in_dev
                                    args['channels'] = in_ch
                                return args, (out_dev is not None and out_ch > 0)

                            sd_args, is_duplex = _construct_stream_args(build_copy)
                            # 创建流
                            self.monitoring_stream = sd.Stream(**sd_args)
                            
                            # 计算延迟
                            theoretical_latency = stream_params['blocksize'] / stream_params['samplerate'] * 1000
                            
                            print(f"✅ HECATE G4 Pro优化监听启动成功:")
                            print(f"   ├─ 设备: HECATE G4 Pro (设备{optimal_config['device_id']})")
                            print(f"   ├─ 配置: {stream_params['samplerate']}Hz/{stream_params['blocksize']}样本")
                            print(f"   ├─ 延迟: {theoretical_latency:.2f}ms")
                            print(f"   ├─ 驱动: {config_name}")
                            print(f"   └─ 特性: HECATE专用优化 / {'双工回传' if is_duplex else '仅输入'}")
                            
                            # 🎯 启动流并设为全局音频流
                            self.monitoring_stream.start()
                            # 启用监听回传
                            self.monitor_audio_passthrough = True
                            self.active_audio_stream = self.monitoring_stream
                            print("🎧 HECATE G4 Pro全局监听已启动")
                            print("✨ 特性: 192kHz原生采样 + 超低延迟 + 专业音质")
                            
                            # 🔥 重要修复：同步采样率到音频处理器
                            actual_samplerate = stream_params['samplerate']
                            if hasattr(self, 'sample_rate') and self.sample_rate != actual_samplerate:
                                print(f"🔧 同步采样率: {self.sample_rate}Hz → {actual_samplerate}Hz")
                                self.sample_rate = actual_samplerate
                            
                            # 🔥 关键修复：启动音频处理线程进行音高检测
                            self.start_audio_processing_thread()
                            print("🔥 HECATE音频处理线程已启动，音高检测功能激活")
                            
                            self.status_updated.emit("HECATE全局监听已启动")
                            return True
                            
                        except Exception as e:
                            error_msg = str(e)
                            print(f"❌ {config_name}失败: {error_msg}")
                            
                            # 🔧 增强的WASAPI错误分析与处理
                            if 'AUDCLNT_E_WRONG_ENDPOINT_TYPE' in error_msg or 'PaErrorCode -9999' in error_msg:
                                print("🔍 WASAPI端点类型错误 - 输入/输出设备类型混淆")
                                print("   解决方案: 检查设备是否为输入设备，或尝试WasapiLoopback")
                                # 自动补救：若使用双工，尝试改为仅输入模式
                                if 'input_device' in stream_params and output_device_id is not None:
                                    try:
                                        print("🔄 自动补救: 改为仅输入模式重新尝试...")
                                        retry_args = stream_params.copy()
                                        # 去掉输出相关
                                        for k in ['output_device','output_channels']:
                                            retry_args.pop(k, None)
                                        input_only_args, _ = (lambda cfg: ( { 'device': cfg['input_device'], 'channels': cfg.get('input_channels',1), 'samplerate': cfg['samplerate'], 'blocksize': cfg['blocksize'], 'dtype': cfg['dtype'], 'latency': cfg.get('latency','low'), 'callback': cfg['callback'], **({'extra_settings': cfg['extra_settings']} if cfg.get('extra_settings') else {}) }, False))(retry_args)
                                        self.monitoring_stream = sd.Stream(**input_only_args)
                                        self.monitoring_stream.start()
                                        print("✅ 端点类型问题通过仅输入模式解决")
                                        self.monitor_audio_passthrough = False
                                        self.active_audio_stream = self.monitoring_stream
                                        if hasattr(self, 'sample_rate') and self.sample_rate != retry_args['samplerate']:
                                            print(f"🔧 同步采样率: {self.sample_rate}Hz → {retry_args['samplerate']}Hz")
                                            self.sample_rate = retry_args['samplerate']
                                        self.start_audio_processing_thread()
                                        self.status_updated.emit("HECATE监听(仅输入)已启动")
                                        return True
                                    except Exception as retry_err:
                                        print(f"⚠️ 仅输入模式补救失败: {retry_err}")
                                # 尝试自动修复：强制使用输入设备配置
                                if hasattr(stream_params, 'extra_settings') and stream_params.get('extra_settings'):
                                    print("🔄 尝试移除WASAPI专用设置...")
                                    stream_params_fixed = stream_params.copy()
                                    stream_params_fixed.pop('extra_settings', None)
                                    try:
                                        self.monitoring_stream = sd.Stream(**stream_params_fixed)
                                        print("✅ 端点类型错误已修复 - 移除WASAPI专用设置")
                                        break
                                    except:
                                        pass
                            
                            elif 'DEVICE_INVALIDATED' in error_msg or 'PaErrorCode -9996' in error_msg:
                                print("🔍 设备已失效 - 设备被拔出、禁用或驱动重置")
                                print("   解决方案: 重新枚举设备或切换到默认设备")
                                # 尝试刷新设备列表
                                try:
                                    sd._terminate()
                                    sd._initialize()
                                    print("🔄 已重新初始化音频系统")
                                except:
                                    pass
                            
                            elif 'UNSUPPORTED_FORMAT' in error_msg or 'PaErrorCode -9997' in error_msg:
                                print("🔍 采样率不支持 - 硬件不支持指定的采样率")
                                print("   解决方案: 降级到设备支持的采样率")
                                # 尝试自动降级采样率
                                if stream_params['samplerate'] > 48000:
                                    print("🔄 尝试降级到48kHz...")
                                    stream_params_fixed = stream_params.copy()
                                    stream_params_fixed['samplerate'] = 48000
                                    stream_params_fixed['blocksize'] = 256
                                    try:
                                        if output_device_id is not None and stream_params_fixed.get('output_channels',0) > 0:
                                            self.monitoring_stream = sd.Stream(**stream_params_fixed)
                                        else:
                                            self.monitoring_stream = sd.InputStream(device=stream_params_fixed['input_device'], channels=stream_params_fixed.get('input_channels',1), samplerate=stream_params_fixed['samplerate'], blocksize=stream_params_fixed['blocksize'], dtype=stream_params_fixed['dtype'], latency=stream_params_fixed.get('latency','low'), callback=stream_params_fixed['callback'], extra_settings=stream_params_fixed.get('extra_settings'))
                                        print("✅ 采样率已自动降级到48kHz")
                                        break
                                    except:
                                        pass
                                elif stream_params['samplerate'] > 44100:
                                    print("🔄 尝试降级到44.1kHz...")
                                    stream_params_fixed = stream_params.copy()
                                    stream_params_fixed['samplerate'] = 44100
                                    stream_params_fixed['blocksize'] = 256
                                    try:
                                        if output_device_id is not None and stream_params_fixed.get('output_channels',0) > 0:
                                            self.monitoring_stream = sd.Stream(**stream_params_fixed)
                                        else:
                                            self.monitoring_stream = sd.InputStream(device=stream_params_fixed['input_device'], channels=stream_params_fixed.get('input_channels',1), samplerate=stream_params_fixed['samplerate'], blocksize=stream_params_fixed['blocksize'], dtype=stream_params_fixed['dtype'], latency=stream_params_fixed.get('latency','low'), callback=stream_params_fixed['callback'], extra_settings=stream_params_fixed.get('extra_settings'))
                                        print("✅ 采样率已自动降级到44.1kHz")
                                        break
                                    except:
                                        pass
                            
                            elif 'INVALID_CHANNEL_COUNT' in error_msg or 'PaErrorCode -9998' in error_msg:
                                print("🔍 通道数无效 - 单声道设备配置为立体声")
                                print("   解决方案: 强制使用单声道配置")
                                # 尝试强制单声道
                                # 允许两种结构: 'channels' 或 'input_channels'
                                ch_val = stream_params.get('channels', stream_params.get('input_channels', 1))
                                if isinstance(ch_val, tuple):
                                    in_ch = ch_val[0]
                                else:
                                    in_ch = ch_val
                                if in_ch > 1:
                                    print("🔄 尝试强制单声道配置...")
                                    stream_params_fixed = stream_params.copy()
                                    stream_params_fixed['input_channels'] = 1
                                    if 'channels' in stream_params_fixed:
                                        stream_params_fixed.pop('channels', None)
                                    try:
                                        fixed_args, is_duplex2 = (lambda cfg: _construct_stream_args(cfg))(stream_params_fixed)
                                        # 如果双工且输出需要保持，仍提供原输出通道，但输入降为1
                                        self.monitoring_stream = sd.Stream(**fixed_args)
                                        print("✅ 已强制使用单声道配置")
                                        self.channels = 1  # 更新全局输入通道
                                        break
                                    except:
                                        pass
                            
                            elif 'INVALID_DEVICE' in error_msg or 'Invalid device' in error_msg:
                                print("🔍 设备ID无效 - 设备不存在或已断开连接")
                                print("   解决方案: 切换到默认输入设备")
                            
                            elif 'Unanticipated host error' in error_msg:
                                print("🔍 主机音频系统错误 - Windows音频服务问题")
                                print("   解决方案: 尝试DirectSound模式或重启音频服务")
                            
                            else:
                                print(f"🔍 未知WASAPI错误: {error_msg}")
                            
                            # 继续尝试下一个配置
                            continue
                    
                    # 所有HECATE配置都失败了
                    print("❌ 所有HECATE配置都失败，将尝试通用配置")
            
            # 降级到通用配置：智能搜索有输入能力的HECATE设备
            print("⚠️ 主HECATE设备不可用，搜索备用HECATE输入设备...")
            
            # 智能搜索所有HECATE设备，优先选择有输入能力的设备
            hecate_input_devices = []
            other_hecate_found = False
            
            try:
                devices = sd.query_devices()
                print("🔍 智能HECATE设备发现:")
                
                # 第一轮：搜索所有HECATE设备并分析输入能力
                for device_id in range(len(devices)):
                    try:
                        device_info = devices[device_id]
                        device_name = device_info.get('name', '')
                        max_input_channels = device_info.get('max_input_channels', 0)
                        max_output_channels = device_info.get('max_output_channels', 0)
                        default_samplerate = device_info.get('default_samplerate', 44100)
                        host_api = device_info.get('hostapi', -1)
                        
                        # 识别HECATE设备
                        if ('HECATE' in device_name or 'G4 Pro' in device_name):
                            # 过滤有输入能力的设备
                            if max_input_channels > 0:
                                hecate_input_devices.append({
                                    'device_id': device_id,
                                    'device_info': device_info,
                                    'name': device_name,
                                    'input_channels': max_input_channels,
                                    'samplerate': default_samplerate,
                                    'host_api': host_api,
                                    'priority_score': self._calculate_device_priority(device_info)
                                })
                                print(f"✅ 发现输入设备{device_id}: {device_name}")
                                print(f"   ├─ 输入通道: {max_input_channels}")
                                print(f"   ├─ 采样率: {default_samplerate}Hz")
                                print(f"   ├─ 主机API: {host_api}")
                                print(f"   └─ 优先级: {self._calculate_device_priority(device_info)}")
                            else:
                                print(f"⚠️ 跳过输出设备{device_id}: {device_name} (输入通道: {max_input_channels})")
                                
                    except Exception as device_error:
                        print(f"⚠️ 设备{device_id}检查失败: {device_error}")
                        continue
                
                # 按优先级排序HECATE输入设备
                hecate_input_devices.sort(key=lambda x: x['priority_score'], reverse=True)
                print(f"📊 发现{len(hecate_input_devices)}个HECATE输入设备")
                
                # 第二轮：尝试每个HECATE输入设备
                for device_config in hecate_input_devices:
                    device_id = device_config['device_id']
                    device_name = device_config['name']
                    max_channels = device_config['input_channels']
                    device_samplerate = device_config['samplerate']
                    host_api = device_config['host_api']
                    
                    print(f"🔍 测试设备{device_id}: {device_name}")
                    
                    # 为每个设备生成智能配置序列
                    device_configs = self._generate_smart_device_configs(
                        device_id, max_channels, device_samplerate, host_api, hecate_optimized_callback
                    )
                    
                    # 尝试每个配置
                    for config in device_configs:
                        try:
                            config_name = config.pop('name')
                            
                            # 创建音频流
                            self.monitoring_stream = sd.Stream(**config)
                            
                            theoretical_latency = config['blocksize'] / config['samplerate'] * 1000
                            
                            print(f"✅ {config_name}成功:")
                            print(f"   ├─ 设备: {device_name}")
                            print(f"   ├─ 配置: {config['samplerate']}Hz/{config['blocksize']}样本")
                            print(f"   ├─ 通道: {config['channels']}声道")
                            print(f"   └─ 延迟: {theoretical_latency:.2f}ms")
                            
                            # 🎯 启动流并设为全局音频流
                            self.monitoring_stream.start()
                            self.monitor_audio_passthrough = True
                            self.active_audio_stream = self.monitoring_stream
                            self.channels = config['channels']  # 更新全局通道数
                            print("🎧 HECATE备用设备全局监听已启动")
                            
                            # 🔥 重要修复：同步采样率到音频处理器
                            actual_samplerate = config['samplerate']
                            if hasattr(self, 'sample_rate') and self.sample_rate != actual_samplerate:
                                print(f"🔧 同步采样率: {self.sample_rate}Hz → {actual_samplerate}Hz")
                                self.sample_rate = actual_samplerate
                            
                            # 🔥 关键修复：启动音频处理线程进行音高检测
                            self.start_audio_processing_thread()
                            print("🔥 HECATE备用设备音频处理线程已启动，音高检测功能激活")
                            
                            self.status_updated.emit(f"HECATE备用设备全局监听已启动")
                            other_hecate_found = True
                            return True
                            
                        except Exception as e:
                            # 使用增强的错误处理
                            self._handle_device_error(e, config_name, device_id, config)
                            continue
                    
                    # 如果设备的所有配置都失败
                    print(f"❌ 设备{device_id}所有配置都失败")
                    
            except Exception as e:
                print(f"⚠️ HECATE输入设备搜索失败: {e}")
            
            # 如果没有找到备用HECATE设备，使用通用DirectSound/MME配置
            if not other_hecate_found:
                print("🔧 使用通用音频驱动配置...")
                fallback_configs = [
                    {
                        'name': 'DirectSound高质量',
                        'device': None,  # 使用默认输入设备
                        'rate': 48000,
                        'block': 128,
                        'settings': None,
                        'latency': 'low'
                    },
                    {
                        'name': 'DirectSound标准',
                        'device': None,
                        'rate': 44100,
                        'block': 256,
                        'settings': None,
                        'latency': 'low'
                    },
                    {
                        'name': 'MME兼容模式', 
                        'device': None,
                        'rate': 44100,
                        'block': 512,
                        'settings': None,
                        'latency': None
                    },
                    {
                        'name': '最小兼容配置',
                        'device': None,
                        'rate': 22050,
                        'block': 1024,
                        'settings': None,
                        'latency': None
                    }
                ]
                
                # 尝试降级配置
                for config in fallback_configs:
                    try:
                        print(f"🔧 尝试{config['name']}...")
                        
                        stream_params = {
                            'channels': self.channels,
                            'samplerate': config['rate'],
                            'blocksize': config['block'],
                            'callback': hecate_optimized_callback,
                            'dtype': np.float32
                        }
                        
                        if config['device'] is not None:
                            stream_params['device'] = config['device']
                        if config['latency']:
                            stream_params['latency'] = config['latency']
                        if config['settings']:
                            stream_params['extra_settings'] = config['settings']
                        
                        self.monitoring_stream = sd.Stream(**stream_params)
                        
                        theoretical_latency = config['block'] / config['rate'] * 1000
                        
                        print(f"✅ {config['name']}启动成功:")
                        print(f"   ├─ 配置: {config['rate']}Hz/{config['block']}样本")
                        print(f"   ├─ 延迟: {theoretical_latency:.2f}ms")
                        print(f"   └─ 设备: 系统默认")
                        
                        # 🎯 启动流并设为全局音频流
                        self.monitoring_stream.start()
                        self.monitor_audio_passthrough = True
                        self.active_audio_stream = self.monitoring_stream
                        print("🎧 通用全局监听已启动")
                        
                        # 🔥 重要修复：同步采样率到音频处理器
                        actual_samplerate = config['rate']
                        if hasattr(self, 'sample_rate') and self.sample_rate != actual_samplerate:
                            print(f"🔧 同步采样率: {self.sample_rate}Hz → {actual_samplerate}Hz")
                            self.sample_rate = actual_samplerate
                        
                        # 🔥 关键修复：启动音频处理线程进行音高检测
                        self.start_audio_processing_thread()
                        print("🔥 通用音频处理线程已启动，音高检测功能激活")
                        
                        self.status_updated.emit("通用全局监听已启动")
                        return True
                        
                    except Exception as e:
                        print(f"❌ {config['name']}失败: {e}")
                        continue
            
            # 如果所有配置都失败
            raise Exception("所有音频配置都失败，无法启动监听功能")
        
        except Exception as e:
            error_msg = f"🔴 HECATE监听启动失败: {str(e)}"
            print(error_msg)
            # 🎯 重置全局监听状态
            self.is_global_monitoring_active = False
            self.monitoring_mode = None
            self.error_occurred.emit(f"监听启动失败: {str(e)}")
            return False
    
    def start_professional_monitoring(self):
        """启动专业级监听模式"""
        try:
            # 确保sounddevice模块可用
            import sounddevice as sd
            
            print("🎧 正在启动专业级超低延迟监听模式...")
            
            # 监听模式：不录音，不分析，只实时音频回放
            self.monitoring_filename = None
            self.monitoring_should_save = False
            self.is_monitoring_only = True  # 标记为纯监听模式
            self.audio_buffer = []
            
            # 🚀 终极低延迟监听配置（基于测试验证优化）
            self.professional_monitoring_config = {
                'sample_rate': 44100,      # 44.1kHz最佳兼容性（测试验证）
                'block_size': 4,           # 4样本终极小块（0.09ms理论延迟）
                'use_float32': True,       # 32位浮点精度
                'minimal_processing': True, # 最小化处理
                'zero_latency_mode': True, # 零延迟模式
                'high_freq_protection': True, # 高频保护
                'intelligent_fallback': True, # 智能降级
                'directsound_priority': True,  # DirectSound优先
                'compatibility_mode': True     # 兼容模式
            }
            
            # 🎤 智能音量增强配置（超稳定版本）
            self.intelligent_volume_booster = {
                'enabled': True,
                'base_gain': 1.0,           # 基础增益
                'max_gain': 2.2,            # 最大增益（7dB，更保守避免过度增强）
                'noise_gate_threshold': 0.002, # 噪声门限
                'auto_gain_speed': 0.03,    # 自动增益调整速度（更慢，更平滑）
                'target_level': 0.22,       # 目标音量水平（更保守）
                'voice_freq_boost': 1.05,   # 人声频段增强（更温和）
                'current_gain': 1.0,        # 当前增益
                'rms_history': [],          # RMS历史
                'gain_smoothing': 0.985,    # 增益平滑系数（更高，超级稳定）
                'gain_change_limit': 0.02,  # 单次增益变化限制（新增，防止突变）
                'stability_buffer': 0.05,   # 稳定缓冲区（新增，避免频繁调整）
                'manual_volume': 1.0,       # 🎚️ 手动音量控制（新增，1.0=100%）
                'manual_control_enabled': False  # 🎚️ 手动控制是否启用
            }
            
            # 🎯 高频稳定性专业配置
            self.high_freq_stabilizer = {
                'enabled': True,
                'nyquist_protection': True,    # 奈奎斯特频率保护
                'anti_aliasing': True,         # 抗混叠
                'dynamic_headroom': 6.0,       # 6dB动态余量
                'phase_coherence': True        # 相位一致性
            }
            
            # 🎵 大音量优雅处理配置
            self.large_volume_handler = {
                'enabled': True,
                'soft_knee_compression': True,  # 软拐点压缩
                'transparent_limiting': True,   # 透明限制
                'preserve_transients': True,    # 保持瞬态
                'maintain_clarity': True        # 保持清晰度
            }
            
            # 🔥 延迟优化配置
            self.latency_optimizer = {
                'callback_priority': 'realtime', # 实时优先级
                'buffer_prefill': False,          # 禁用缓冲区预填充
                'interrupt_driven': True,         # 中断驱动
                'minimal_context_switch': True    # 最小上下文切换
            }
            
            # 🔥 音频质量保护配置
            self.quality_protection = {
                'enabled': True,
                'soft_limiter_threshold': 0.85,   # 软限制阈值
                'hard_limiter_threshold': 0.95,   # 硬限制阈值  
                'gentle_compression': True        # 启用温和压缩
            }
            
            # 🔥 校准样本收集
            self.calibration_frames = []
            self.calibration_complete = False
            
            # 🔥 性能统计
            self.processing_times = []
            self.detection_stats = {'total': 0, 'detected': 0, 'vocal_protected': 0}
            
            # 🔥 延迟测量工具
            self.latency_timestamps = []
            self.frame_counter = 0
            
            # 启动专业级音频流
            try:
                import sounddevice as sd
                
                # 🚀 高品质低延迟监听回调：简洁稳定版本
                def professional_monitoring_callback(indata, outdata, frames, time_info, status):
                    """� 高品质低延迟回调：2样本@48kHz + 简洁处理 + 音质优先"""
                    
                    try:
                        # 🎵 高品质音频路由
                        if self.channels == 1 and indata.shape[1] > 1:
                            # 高品质立体声到单声道混合
                            raw_audio = (indata[:, 0] + indata[:, 1]) * 0.5
                        else:
                            raw_audio = indata[:, 0] if len(indata.shape) > 1 else indata.flatten()

                        # 👉 与纯录音保持一致：分析队列使用原始 raw_audio，监听耳返音频可做处理
                        audio_data = raw_audio.copy()
                        
                        # 🎤 优化的智能音量增强（针对大音量/高音快速响应）
                        if self.intelligent_volume_booster['enabled']:
                            rms = np.sqrt(np.mean(audio_data ** 2))
                            peak = np.max(np.abs(audio_data))

                            # 🌿 自然耳返：低音量时避免AGC抬升噪声/呼吸
                            agc_freeze = False
                            if self.monitor_audio_passthrough and getattr(self, 'monitor_natural_mode', True):
                                # 轻量指标：ZCR + 高频差分比
                                try:
                                    zc = float(np.mean((audio_data[:-1] * audio_data[1:]) < 0)) if len(audio_data) > 1 else 0.0
                                    if len(audio_data) > 4:
                                        hfdiff = float(np.sum(np.abs(np.diff(audio_data, 2))))
                                        energy = float(np.sum(np.abs(audio_data))) + 1e-9
                                        hf_ratio = hfdiff / energy
                                    else:
                                        hf_ratio = 0.0
                                except Exception:
                                    zc, hf_ratio = 0.0, 0.0
                                thr_low = 0.010
                                thr_mid = thr_low * 2.0
                                if rms < thr_mid and (zc > 0.10 or hf_ratio > 6.0):
                                    agc_freeze = True
                            
                            # 🎵 大音量快速处理路径
                            if peak > 0.6 or rms > 0.15:  # 大音量/高音检测
                                # 快速响应模式：减少历史依赖
                                noise_gate = self.intelligent_volume_booster['noise_gate_threshold']
                                if rms > noise_gate:
                                    target_level = self.intelligent_volume_booster['target_level']
                                    
                                    # 大音量时使用更直接的增益计算
                                    if rms > target_level:
                                        # 大音量压缩：快速响应，防止失真
                                        target_gain = max(0.95, min(1.05, target_level / rms))
                                    else:
                                        # 适度增强
                                        target_gain = min(1.15, target_level * 0.9 / max(rms, noise_gate))
                                    if agc_freeze:
                                        target_gain = min(target_gain, 1.0)
                                    
                                    # 快速增益调整（减少平滑延迟）
                                    current_gain = self.intelligent_volume_booster['current_gain']
                                    smoothing = 0.85  # 大音量时使用更快的响应
                                    
                                    new_gain = current_gain * smoothing + target_gain * (1 - smoothing)
                                    if agc_freeze:
                                        new_gain = min(new_gain, 1.0)
                                    self.intelligent_volume_booster['current_gain'] = new_gain
                                    
                                    # 应用增益
                                    if abs(new_gain - 1.0) > 0.02:
                                        audio_data = audio_data * new_gain
                                        
                                        # 快速峰值限制（大音量保护）
                                        if np.max(np.abs(audio_data)) > 0.95:
                                            audio_data = audio_data * 0.92
                            else:
                                # 🎵 正常音量的优化处理路径
                                # 更新RMS历史（保持4个样本，减少计算）
                                if len(self.intelligent_volume_booster['rms_history']) >= 4:
                                    self.intelligent_volume_booster['rms_history'].pop(0)
                                self.intelligent_volume_booster['rms_history'].append(rms)
                                
                                # 计算平均RMS
                                avg_rms = np.mean(self.intelligent_volume_booster['rms_history']) if len(self.intelligent_volume_booster['rms_history']) >= 2 else rms
                                
                                # 噪声门限检测
                                noise_gate = self.intelligent_volume_booster['noise_gate_threshold']
                                if avg_rms > noise_gate:
                                    target_level = self.intelligent_volume_booster['target_level']
                                    
                                    # 正常增益计算
                                    if avg_rms < target_level * 0.5:
                                        target_gain = min(1.2, target_level * 0.7 / max(avg_rms, noise_gate))
                                    else:
                                        target_gain = max(0.98, min(1.02, target_level / avg_rms))
                                    if agc_freeze:
                                        target_gain = min(target_gain, 1.0)
                                    
                                    # 标准平滑增益变化
                                    current_gain = self.intelligent_volume_booster['current_gain']
                                    smoothing = self.intelligent_volume_booster['gain_smoothing']
                                    new_gain = current_gain * smoothing + target_gain * (1 - smoothing)
                                    if agc_freeze:
                                        new_gain = min(new_gain, 1.0)
                                    
                                    # 增益变化限制
                                    max_gain_change = self.intelligent_volume_booster['gain_change_limit']
                                    if abs(new_gain - current_gain) > max_gain_change:
                                        new_gain = current_gain + max_gain_change if new_gain > current_gain else current_gain - max_gain_change
                                    
                                    self.intelligent_volume_booster['current_gain'] = new_gain
                                    
                                    # 温和应用增益
                                    if new_gain > 1.01:
                                        audio_data = audio_data * new_gain
                                        # 温和限制（只在必要时）
                                        peak = np.max(np.abs(audio_data))
                                        if peak > 0.93:
                                            audio_data = audio_data * (0.91 / peak)
                                else:
                                    # 微弱信号轻微衰减
                                    # 自然耳返时保持更原味：不要过度衰减，避免“呼吸被抽空”感
                                    audio_data = audio_data * (0.90 if getattr(self, 'monitor_natural_mode', True) else 0.88)
                        
                        # �️ 手动音量控制（新增：与线程优化集成）
                        if hasattr(self, 'intelligent_volume_booster') and self.intelligent_volume_booster.get('manual_control_enabled', False):
                            manual_volume = self.intelligent_volume_booster.get('manual_volume', 1.0)
                            audio_data = audio_data * manual_volume
                        
                        # �🎵 高品质音频输出（受监听回传开关控制）
                        if self.monitor_audio_passthrough:
                            if getattr(self, 'monitor_raw_mode', False):
                                audio_out = raw_audio.copy()
                            else:
                                audio_out = self._apply_breath_noise_suppress(audio_data, key='pro')
                            # 始终应用头房+VRMS限幅，避免削波且不失真
                            audio_out = self._apply_headroom_and_vrms(audio_out, key='pro')
                            if outdata.shape[1] == 1:
                                outdata[:, 0] = audio_out
                            else:
                                outdata[:, 0] = audio_out
                                outdata[:, 1] = audio_out
                        else:
                            outdata.fill(0)
                        
                        # 🔥 优化延迟监控（减少打印频率，降低回调延迟）
                        if hasattr(self, '_opt_frame_counter'):
                            self._opt_frame_counter += 1
                        else:
                            self._opt_frame_counter = 1
                        
                        # 每96000帧报告一次（2秒间隔，减少控制台输出延迟）
                        if self._opt_frame_counter % 96000 == 0:
                            theoretical_latency = (frames / self.professional_monitoring_config['sample_rate']) * 1000
                            current_gain = self.intelligent_volume_booster.get('current_gain', 1.0)
                            print(f"🎵 超低延迟监听 (第{self._opt_frame_counter//1000:.0f}k帧) - 延迟: {theoretical_latency:.3f}ms, 增益: {current_gain:.2f}x")
                    
                    except Exception as e:
                        # 错误处理：安全静音输出
                        if 'outdata' in locals():
                            outdata.fill(0)
                        print(f"⚠️ 监听处理错误: {e}")
                        
                        # � 智能音量增强处理（保持低延迟）
                        if self.intelligent_volume_booster['enabled']:
                            # 快速计算音频特征
                            rms = np.sqrt(np.mean(audio_data ** 2))
                            peak = np.max(np.abs(audio_data))
                            
                            # 更新RMS历史（保持最近8个样本，减少计算负担）
                            self.intelligent_volume_booster['rms_history'].append(rms)
                            if len(self.intelligent_volume_booster['rms_history']) > 8:
                                self.intelligent_volume_booster['rms_history'].pop(0)
                            
                            # 计算平均RMS以提高稳定性
                            avg_rms = np.mean(self.intelligent_volume_booster['rms_history']) if len(self.intelligent_volume_booster['rms_history']) >= 3 else rms
                            # 噪声门限检测：只对有意义的信号进行增强
                            noise_gate = self.intelligent_volume_booster['noise_gate_threshold']
                            if avg_rms > noise_gate:
                                # 计算目标增益
                                target_level = self.intelligent_volume_booster['target_level']
                                
                                # 🎵 音质优先的温和增益计算（微调版本）
                                if self.intelligent_volume_booster.get('quality_priority', True):
                                    # 更温和的增益计算，保护音质
                                    if avg_rms < target_level * 0.3:  # 很小的声音
                                        target_gain = min(1.5, target_level * 0.5 / max(avg_rms, noise_gate))  # 更保守的最大增益
                                    elif avg_rms < target_level * 0.6:  # 中等偏小的声音
                                        target_gain = min(1.3, target_level * 0.7 / max(avg_rms, noise_gate))  # 轻微增益
                                    elif avg_rms < target_level * 0.9:  # 中等音量
                                        target_gain = min(1.1, target_level * 0.9 / max(avg_rms, noise_gate))  # 极轻微增益
                                    else:  # 足够大的声音
                                        target_gain = max(0.98, min(1.02, target_level / avg_rms))  # 几乎不变
                                else:
                                    # 原始增益计算（向后兼容）
                                    if avg_rms < target_level * 0.2:
                                        target_gain = min(2.5, target_level * 0.4 / max(avg_rms, noise_gate))
                                    elif avg_rms < target_level * 0.5:
                                        target_gain = min(1.8, target_level * 0.6 / max(avg_rms, noise_gate))
                                    elif avg_rms < target_level * 0.8:
                                        target_gain = min(1.3, target_level * 0.8 / max(avg_rms, noise_gate))
                                    else:
                                        target_gain = max(0.95, min(1.05, target_level / avg_rms))
                                
                                # 🎯 超稳定增益变化（使用新配置参数）
                                current_gain = self.intelligent_volume_booster['current_gain']
                                smoothing = self.intelligent_volume_booster['gain_smoothing']  # 使用配置值0.985
                                new_gain = current_gain * smoothing + target_gain * (1 - smoothing)
                                
                                # 🔒 超严格限制增益变化（使用新配置参数防止突变）
                                max_gain_change = self.intelligent_volume_booster['gain_change_limit']  # 使用配置值0.02
                                stability_buffer = self.intelligent_volume_booster['stability_buffer']  # 稳定缓冲区0.05
                                
                                # 只有当增益变化超过稳定缓冲区时才调整
                                gain_difference = abs(new_gain - current_gain)
                                if gain_difference > stability_buffer:
                                    if abs(new_gain - current_gain) > max_gain_change:
                                        if new_gain > current_gain:
                                            new_gain = current_gain + max_gain_change
                                        else:
                                            new_gain = current_gain - max_gain_change
                                else:
                                    # 在稳定缓冲区内，保持当前增益不变
                                    new_gain = current_gain
                                
                                # 更新当前增益
                                self.intelligent_volume_booster['current_gain'] = new_gain
                                
                                # 🎵 保真应用增益（避免音质损失）
                                if new_gain > 1.02:  # 只有增益明显时才应用
                                    # 线性增益，保持音频特征
                                    enhanced_audio = audio_data * new_gain
                                    
                                    # 🎯 保真软限制（只在绝对必要时使用）
                                    limit_threshold = 0.96  # 提高限制阈值，减少干预
                                    if np.max(np.abs(enhanced_audio)) > limit_threshold:
                                        # 使用更温和的限制算法
                                        scale_factor = limit_threshold / np.max(np.abs(enhanced_audio))
                                        enhanced_audio = enhanced_audio * scale_factor
                                    
                                    audio_data = enhanced_audio
                                else:
                                    # 衰减时直接线性处理
                                    audio_data = audio_data * new_gain
                                
                            else:
                                # 信号太弱，轻微衰减噪音（减少衰减程度）
                                audio_data = audio_data * 0.7  # 从0.3提高到0.7，减少过度衰减
                        
                        # �🎵 专业级大音量稳定处理（保持音质）
                        if self.large_volume_handler['enabled']:
                            # 计算音频特征（快速方法）
                            peak = np.max(np.abs(audio_data))
                            
                            # 🎯 提高检测阈值，减少不必要的处理
                            if peak > 0.90:  # 大音量检测（从0.85提高到0.90）
                                if self.large_volume_handler['soft_knee_compression']:
                                    # 更温和的软拐点压缩（保持音质）
                                    compression_threshold = 0.90  # 提高压缩阈值
                                    compression_ratio = 0.5  # 降低压缩比，更温和（从0.3提高到0.5）
                                    
                                    # 查找超过阈值的样本
                                    mask = np.abs(audio_data) > compression_threshold
                                    
                                    # 应用极温和的软压缩
                                    if np.any(mask):
                                        audio_data[mask] = np.sign(audio_data[mask]) * (
                                            compression_threshold + 
                                            (np.abs(audio_data[mask]) - compression_threshold) * compression_ratio
                                        )
                                
                                # 🔒 最后的安全限制（只在极端情况下使用）
                                if self.large_volume_handler['transparent_limiting']:
                                    final_peak = np.max(np.abs(audio_data))
                                    if final_peak > 0.98:  # 只在接近削峰时才限制
                                        # 简单线性缩放，保持波形形状
                                        scale_factor = 0.95 / final_peak
                                        audio_data = audio_data * scale_factor
                        
                        # 🔥 保真高频稳定性保护（精准电流音抑制）
                        if self.high_freq_stabilizer['enabled']:
                            # 奈奎斯特频率保护（防止混叠）
                            if self.high_freq_stabilizer['nyquist_protection']:
                                # 🎯 精确检测异常高频噪声（电流音特征）
                                if len(audio_data) > 6:
                                    # 计算高频能量比例（更精确的算法）
                                    high_freq_diff = np.sum(np.abs(np.diff(audio_data, 2)))
                                    total_energy = np.sum(np.abs(audio_data))
                                    
                                    if total_energy > 1e-8:  # 避免除零错误
                                        high_freq_ratio = high_freq_diff / total_energy
                                        
                                        # 🔍 严格的电流音检测（提高阈值，减少误判）
                                        if high_freq_ratio > 15.0:  # 极强电流音（提高阈值从8.0到15.0）
                                            # 保守的电流音抑制：只处理真正的异常信号
                                            smoothed = np.copy(audio_data)
                                            if len(audio_data) > 6:
                                                # 轻微3点平均（减少对音质的影响）
                                                for i in range(1, len(audio_data) - 1):
                                                    smoothed[i] = (audio_data[i-1] * 0.25 + 
                                                                 audio_data[i] * 0.5 + 
                                                                 audio_data[i+1] * 0.25)
                                            audio_data = audio_data * 0.7 + smoothed * 0.3  # 更温和的混合
                                        elif high_freq_ratio > 10.0:  # 中等电流音（提高阈值从3.0到10.0）
                                            # 极轻微的电流音抑制
                                            smoothed = np.copy(audio_data)
                                            smoothed[1:-1] = (audio_data[:-2] + audio_data[1:-1] + audio_data[2:]) / 3.0
                                            audio_data = audio_data * 0.9 + smoothed * 0.1  # 90%保持原始信号
                        
                        # 🎯 专业级音频输出（保持相位一致性 + 手动音量控制）
                        # 🎚️ 应用手动音量控制
                        if self.intelligent_volume_booster.get('manual_control_enabled', False):
                            manual_volume = self.intelligent_volume_booster.get('manual_volume', 1.0)
                            audio_data = audio_data * manual_volume
                        
                        if outdata.shape[1] == 1:
                            # 单声道输出
                            outdata[:, 0] = audio_data
                        else:
                            # 立体声输出（保持声像）
                            outdata[:, 0] = audio_data  # 左声道
                            outdata[:, 1] = audio_data  # 右声道

                        # 🔥 补充：把原始raw_audio送入分析队列（避免处理后波形影响音高）
                        try:
                            if not self.audio_buffer_queue.full():
                                self.audio_buffer_queue.put_nowait({
                                    'data': raw_audio.copy(),
                                    'timestamp': time.time(),
                                    'should_save': self.is_recording and self.should_save
                                })
                        except Exception:
                            pass
                        
                        # 🔥 实时延迟监控（精确测量）
                        if hasattr(self, '_monitor_frame_counter'):
                            self._monitor_frame_counter += 1
                        else:
                            self._monitor_frame_counter = 1
                        
                        # 每32000帧报告一次状态（减少输出频率，提升性能）
                        if self._monitor_frame_counter % 32000 == 0:
                            theoretical_latency = (frames / self.professional_monitoring_config['sample_rate']) * 1000
                            
                            # 智能状态报告：只在增益变化显著时显示详细信息
                            current_gain = self.intelligent_volume_booster.get('current_gain', 1.0)
                            
                            # 检查是否需要详细报告（增益变化超过0.1x或每96000帧强制报告一次）
                            if not hasattr(self, '_last_reported_gain'):
                                self._last_reported_gain = current_gain
                                should_report_detail = True
                                gain_change = 0.0  # 初始化增益变化
                            else:
                                gain_change = abs(current_gain - self._last_reported_gain)
                                should_report_detail = (gain_change > 0.1 or self._monitor_frame_counter % 96000 == 0)
                            
                            if should_report_detail:
                                audio_rms = np.sqrt(np.mean(audio_data ** 2))
                                audio_peak = np.max(np.abs(audio_data))
                                
                                print(f"🎧 监听状态 (第{self._monitor_frame_counter//1000:.1f}k帧):")
                                print(f"   ├─ 系统延迟: {theoretical_latency:.3f}ms")  
                                print(f"   ├─ 智能增益: {current_gain:.2f}x ({20*np.log10(current_gain):.1f}dB)")
                                print(f"   ├─ 音频质量: RMS={audio_rms:.4f}, 峰值={audio_peak:.3f}")
                                print(f"   └─ 增益稳定性: 变化{gain_change:.3f}x")
                                
                                self._last_reported_gain = current_gain
                            else:
                                # 简化报告：仅显示关键信息
                                if self._monitor_frame_counter % 32000 == 0:
                                    print(f"🎧 监听运行中 ({self._monitor_frame_counter//1000:.0f}k帧) - 延迟: {theoretical_latency:.3f}ms")
                        
                    
                    except Exception as e:
                        # 错误处理：静音输出，避免噪声
                        if 'outdata' in locals():
                            outdata.fill(0)
                        print(f"⚠️ 监听处理错误: {e}")
                
                # 🚀 配置专业级音频流
                optimized_sample_rate = self.professional_monitoring_config['sample_rate']
                optimized_block_size = self.professional_monitoring_config['block_size']
                
                print(f"🎵 配置稳定监听: {optimized_sample_rate}Hz, {optimized_block_size}样本, 理论延迟={optimized_block_size/optimized_sample_rate*1000:.3f}ms")
                
                # 🎤 显示智能音量增强配置（音质优先微调版本）
                if self.intelligent_volume_booster['enabled']:
                    booster = self.intelligent_volume_booster
                    manual_volume = booster.get('manual_volume', 1.0)
                    manual_enabled = booster.get('manual_control_enabled', False)
                    quality_priority = booster.get('quality_priority', True)
                    
                    print(f"🎤 稳定音质增强已启用:")
                    print(f"   ├─ 自动增益: 1.0x - {booster['max_gain']:.1f}x (0 - {20*np.log10(booster['max_gain']):.1f}dB)")
                    print(f"   ├─ 目标水平: {booster['target_level']:.3f} (平衡音质与延迟)")
                    print(f"   ├─ 响应速度: {booster['auto_gain_speed']:.3f} (稳定优先)")
                    print(f"   └─ 特性: 自然动态 + 抗失真 + 通用处理")
                else:
                    print("🎤 智能音量增强已禁用")
                
                # ⚡ 动态初始化专业监听状态
                self.frame_counter = 0
                self.latency_timestamps = []
                self.processing_times = []
                
                # � 电流音检测器（专业级）
                self.electric_noise_detector = {
                    'enabled': True,
                    'consecutive_count': 0,
                    'threshold': 0.0008
                }
                
                # 🚀 专业级低延迟音频流配置（动态WASAPI设备发现版本）
                audio_configs = [
                    # 第一优先级：ASIO专业驱动（最低延迟）
                    {
                        'name': 'ASIO专业模式',
                        'rate': 48000,
                        'block': 2,
                        'settings': sd.AsioSettings(channel_selectors=[0]),
                        'latency': 'low',
                        'priority': 'ultra-low'
                    }
                ]
                
                # 动态添加WASAPI配置
                wasapi_configs = self._get_optimal_wasapi_configs()
                for config in wasapi_configs:
                    # 转换格式以匹配专业监听所需的参数
                    audio_configs.append({
                        'name': config['name'],
                        'device': config['device'],
                        'rate': config['samplerate'],
                        'block': config['blocksize'],
                        'settings': config['settings'],  # 🔧 修复：直接使用对象，不调用
                        'latency': 'low',
                        'priority': config['expected_latency'],
                        'verified_latency': config.get('verified_latency')
                    })
                
                # 添加DirectSound兼容模式
                audio_configs.append({
                    'name': 'DirectSound模式',
                    'rate': 48000,
                    'block': 4,
                    'settings': None,
                    'latency': 'low',
                    'priority': 'medium'
                })
                
                audio_stream_started = False
                for i, config in enumerate(audio_configs):
                    try:
                        # 构建流参数
                        stream_params = {
                            'channels': self.channels,
                            'dtype': 'float32'
                        }
                        if 'device' in config:
                            stream_params['device'] = config['device']
                            print(f"🎯 专业监听使用WASAPI设备{config['device']}@{config['rate']}Hz")
                        stream_params['samplerate'] = config['rate']
                        
                        # 添加可选参数
                        if config['latency']:
                            stream_params['latency'] = config['latency']
                        if config['settings']:
                            stream_params['extra_settings'] = config['settings']
                        
                        # 尝试创建音频流
                        self.monitoring_stream = sd.Stream(**stream_params)
                        
                        theoretical_latency = config['block'] / config['rate'] * 1000
                        verified_latency = config.get('verified_latency', theoretical_latency)
                        
                        print(f"✅ {config['name']}启动成功:")
                        print(f"   ├─ 配置: {config['rate']}Hz/{config['block']}样本")
                        print(f"   ├─ 理论延迟: {theoretical_latency:.2f}ms")
                        if 'verified_latency' in config:
                            print(f"   ├─ 验证延迟: {verified_latency}ms ⭐")
                        print(f"   ├─ 优先级: {config['priority']}")
                        print(f"   └─ 音频格式: float32")
                        
                        audio_stream_started = True
                        break
                        
                    except Exception as config_error:
                        print(f"⚠️ {config['name']}失败: {str(config_error)[:100]}...")
                        if i < len(audio_configs) - 1:
                            print(f"🔄 尝试下一个配置...")
                        continue
                
                if not audio_stream_started:
                    raise Exception("所有音频驱动配置都失败，请检查音频设备和驱动")
                
                # 启动专业监听流
                self.monitoring_stream.start()
                self.monitor_audio_passthrough = True
                print("� 拍掌同步专业监听已启动")
                print("✨ 特性: 零延迟直通模式 + 瞬态绕过处理 + 拍掌同步优化")
                print("� 优化: 1样本@48kHz(0.021ms) + 直通优先 + 最小处理")
                print("⚡ 延迟: 理论0.021ms + 瞬态信号零处理延迟")
                print("🎯 目标: 真正的拍掌同步效果，接近零感知延迟")
                print("🔥 新特性: 拍掌等瞬态信号自动检测并绕过所有处理")
                print("🎚️ 提示: 右键监听按钮可调节音量")
                
                self.status_updated.emit("稳定音质监听已启动")
                return True
                
            except Exception as e:
                error_msg = f"🔴 专业监听流启动失败: {str(e)}"
                print(error_msg)
                print("💡 解决方案: 检查音频设备连接、更新驱动程序或重启音频服务")
                return False
                
        except Exception as e:
            error_msg = f"🔴 专业监听启动失败: {str(e)}"
            print(error_msg)
            print("💡 建议: 检查音频设备是否正常工作，重启程序或更新音频驱动")
            self.error_occurred.emit(f"监听启动失败: {str(e)}")
            return False
    
    def stop_audio_monitoring(self):
        """停止纯音频监听（显示性能统计）"""
        try:
            self.is_monitoring_only = False
            self.monitor_audio_passthrough = False  # 关闭回传
            # 🔧 确保后续可以重新启动：立即标记全局监听未激活（避免标志残留导致二次启动被跳过）
            if getattr(self, 'is_global_monitoring_active', False):
                print("🔧 stop_audio_monitoring: 重置全局监听激活标志")
            self.is_global_monitoring_active = False
            
            # 🔥 生成最终延迟统计报告（修复计算错误）
            if hasattr(self, 'latency_timestamps') and len(self.latency_timestamps) > 10:
                # 🔥 过滤异常延迟值
                valid_latencies = [lat for lat in self.latency_timestamps if 0 <= lat <= 1000]
                
                if len(valid_latencies) > 5:
                    stats = {
                        'avg': np.mean(valid_latencies),
                        'max': np.max(valid_latencies),
                        'min': np.min(valid_latencies),
                        'std': np.std(valid_latencies),
                        'count': len(valid_latencies),
                        'total_count': len(self.latency_timestamps)
                    }
                    
                    print("📊 监听模式性能统计报告:")
                    print(f"   ├─ 平均延迟: {stats['avg']:.1f}ms")
                    print(f"   ├─ 最大延迟: {stats['max']:.1f}ms") 
                    print(f"   ├─ 最小延迟: {stats['min']:.1f}ms")
                    print(f"   ├─ 延迟抖动: {stats['std']:.1f}ms")
                    print(f"   ├─ 有效测量: {stats['count']}/{stats['total_count']}")
                    print(f"   └─ 理论延迟: ~{128/96000*1000:.1f}ms (128样本@96kHz)")
                    
                    # 🔥 电流音检测统计
                    if hasattr(self, 'electric_noise_detector'):
                        noise_count = self.electric_noise_detector.get('consecutive_count', 0)
                        if noise_count > 0:
                            print(f"⚡ 电流音检测: 发现{noise_count}次异常信号")
                        else:
                            print(f"⚡ 电流音检测: 运行正常，无异常信号")
                    
                    # 🎤 音量增强器统计
                    if hasattr(self, 'intelligent_volume_booster'):
                        booster = self.intelligent_volume_booster
                        final_gain = booster.get('current_gain', 1.0)
                        rms_history = booster.get('rms_history', [])
                        if rms_history:
                            avg_input = np.mean(rms_history)
                            print(f"🎤 音量增强统计:")
                            print(f"   ├─ 最终增益: {final_gain:.2f}x ({20*np.log10(final_gain):.1f}dB)")
                            print(f"   ├─ 平均输入: {avg_input:.4f}")
                            print(f"   └─ 增强效果: {'活跃' if avg_input > booster.get('noise_gate_threshold', 0.003) else '待机'}")
                        else:
                            print("✅ 电流音检测: 未发现异常信号")
                    
                    # � 处理时间性能统计
                    if hasattr(self, 'processing_times') and len(self.processing_times) > 10:
                        process_stats = {
                            'avg': np.mean(self.processing_times),
                            'max': np.max(self.processing_times),
                            'min': np.min(self.processing_times),
                            'std': np.std(self.processing_times),
                            'count': len(self.processing_times)
                        }
                        
                        print("🚀 音频处理性能统计:")
                        print(f"   ├─ 平均处理时间: {process_stats['avg']:.2f}ms")
                        print(f"   ├─ 最大处理时间: {process_stats['max']:.2f}ms")
                        print(f"   ├─ 最小处理时间: {process_stats['min']:.2f}ms")
                        print(f"   ├─ 处理抖动: {process_stats['std']:.2f}ms")
                        print(f"   └─ 测量次数: {process_stats['count']}")
                        
                        # 🚀 处理性能评估
                        if process_stats['avg'] < 0.5:
                            print("🎉 处理性能: 极佳 (< 0.5ms)")
                        elif process_stats['avg'] < 1.0:
                            print("👍 处理性能: 优秀 (< 1ms)")
                        elif process_stats['avg'] < 2.0:
                            print("✅ 处理性能: 良好 (< 2ms)")
                        else:
                            print("⚠️ 处理性能: 需要优化 (> 2ms)")
                    
                    # �🔥 修正的延迟性能评估
                    if stats['avg'] < 2:
                        print("🎉 延迟性能: 极致 (< 2ms)")
                    elif stats['avg'] < 5:
                        print("👍 延迟性能: 优秀 (< 5ms)")
                    elif stats['avg'] < 10:
                        print("✅ 延迟性能: 良好 (< 10ms)")
                    elif stats['avg'] < 20:
                        print("⚠️ 延迟性能: 一般 (< 20ms)")
                    else:
                        print("❌ 延迟性能: 需要优化 (> 20ms)")
                        
                    # 🔥 电流音相关提示
                    if stats['std'] > 5:
                        print("💡 延迟抖动较大，可能影响音质稳定性")
                else:
                    print("📊 延迟测量数据异常，可能存在系统兼容性问题")
                    print(f"   理论延迟: ~{128/96000*1000:.1f}ms (基于128样本@96kHz)")
            else:
                print("📊 未收集到足够的延迟数据")
                print(f"   理论延迟: ~{128/48000*1000:.1f}ms (基于128样本@48kHz)")
            
            # 停止监听音频流
            if hasattr(self, 'monitoring_stream') and self.monitoring_stream:
                self.monitoring_stream.stop()
                self.monitoring_stream.close()
                self.monitoring_stream = None
                print("🎧 纯音频监听流已停止")
            # 同步清理统一引用，防止残留引用导致下一次启动误判
            if hasattr(self, 'active_audio_stream') and self.active_audio_stream:
                try:
                    # 避免重复关闭已在上面关闭的同对象
                    if self.active_audio_stream is not self.monitoring_stream:
                        try:
                            self.active_audio_stream.stop()
                        except Exception:
                            pass
                        try:
                            self.active_audio_stream.close()
                        except Exception:
                            pass
                finally:
                    self.active_audio_stream = None
            
            # 清理监听相关的临时数据
            if hasattr(self, 'latency_timestamps'):
                self.latency_timestamps.clear()
            if hasattr(self, 'frame_counter'):
                self.frame_counter = 0
            
            self.status_updated.emit("监听已停止")
            
        except Exception as e:
            print(f"❌ 停止纯音频监听失败: {e}")
            self.error_occurred.emit(f"停止监听失败: {e}")

    def configure_volume_booster(self, max_gain=4.0, target_level=0.3, noise_gate=0.003):
        """配置智能音量增强参数
        
        Args:
            max_gain (float): 最大增益倍数 (1.0-6.0，建议2.0-4.0)
            target_level (float): 目标音量水平 (0.1-0.6，建议0.2-0.4)
            noise_gate (float): 噪声门限 (0.001-0.01，建议0.002-0.005)
        """
        if hasattr(self, 'intelligent_volume_booster'):
            # 参数验证和调整
            max_gain = max(1.0, min(6.0, max_gain))
            target_level = max(0.1, min(0.6, target_level))
            noise_gate = max(0.001, min(0.01, noise_gate))
            
            # 更新配置
            self.intelligent_volume_booster['max_gain'] = max_gain
            self.intelligent_volume_booster['target_level'] = target_level
            self.intelligent_volume_booster['noise_gate_threshold'] = noise_gate
            
            print(f"🎤 音量增强配置更新:")
            print(f"   ├─ 最大增益: {max_gain:.1f}x ({20*np.log10(max_gain):.1f}dB)")
            print(f"   ├─ 目标水平: {target_level:.3f}")
            print(f"   └─ 噪声门限: {noise_gate:.4f}")
        else:
            print("⚠️ 智能音量增强器未初始化")
    
    def set_manual_volume(self, volume_percent):
        """设置手动音量控制
        
        Args:
            volume_percent (float): 音量百分比 (0-300，100=原始音量)
        """
        if hasattr(self, 'intelligent_volume_booster'):
            # 参数验证和调整（0-300%范围）
            volume_percent = max(0, min(300, volume_percent))
            volume_multiplier = volume_percent / 100.0
            
            # 更新手动音量设置
            self.intelligent_volume_booster['manual_volume'] = volume_multiplier
            self.intelligent_volume_booster['manual_control_enabled'] = True
            
            print(f"🎚️ 手动音量设置: {volume_percent}% ({volume_multiplier:.2f}x)")
            return True
        else:
            print("⚠️ 智能音量增强器未初始化")
            return False
    
    def get_manual_volume(self):
        """获取当前手动音量设置"""
        if hasattr(self, 'intelligent_volume_booster'):
            volume_multiplier = self.intelligent_volume_booster.get('manual_volume', 1.0)
            return int(volume_multiplier * 100)
        return 100
    
    def enable_manual_volume_control(self, enabled=True):
        """启用或禁用手动音量控制"""
        if hasattr(self, 'intelligent_volume_booster'):
            self.intelligent_volume_booster['manual_control_enabled'] = enabled
            status = "启用" if enabled else "禁用"
            print(f"🎚️ 手动音量控制已{status}")
            return True
        else:
            print("⚠️ 智能音量增强器未初始化")
            return False
    
    def get_volume_booster_status(self):
        """获取音量增强器当前状态"""
        if hasattr(self, 'intelligent_volume_booster'):
            booster = self.intelligent_volume_booster
            current_gain = booster.get('current_gain', 1.0)
            rms_history = booster.get('rms_history', [])
            avg_rms = np.mean(rms_history) if rms_history else 0.0
            
            status = {
                'enabled': booster.get('enabled', False),
                'current_gain': current_gain,
                'current_gain_db': 20 * np.log10(current_gain),
                'max_gain': booster.get('max_gain', 4.0),
                'target_level': booster.get('target_level', 0.3),
                'noise_gate': booster.get('noise_gate_threshold', 0.003),
                'avg_input_rms': avg_rms,
                'is_active': avg_rms > booster.get('noise_gate_threshold', 0.003)
            }
            return status
        return None
    
    def enable_volume_booster(self, enabled=True):
        """启用或禁用音量增强器"""
        if hasattr(self, 'intelligent_volume_booster'):
            self.intelligent_volume_booster['enabled'] = enabled
            status = "启用" if enabled else "禁用"
            print(f"🎤 智能音量增强器已{status}")
        else:
            print("⚠️ 智能音量增强器未初始化")

    # =============== 监听回传开关接口 ===============
    def set_monitor_passthrough(self, enabled: bool):
        """设置是否将监听音频回传到耳机输出"""
        self.monitor_audio_passthrough = bool(enabled)
        print(f"🎧 监听回传已{'开启' if enabled else '关闭'}")
        return self.monitor_audio_passthrough

    def start_audio_processing_thread(self):
        """启动异步音频处理线程"""
        if self.is_audio_processing:
            print("⚠️ 音频处理线程已在运行")
            return
        
        print("🔄 准备启动音频处理线程...")
        self.is_audio_processing = True
        self.audio_processing_thread = threading.Thread(target=self._audio_processing_loop, daemon=True)
        self.audio_processing_thread.start()
        print("✅ 异步音频处理线程启动")
        
        # 验证线程是否真的启动了
        import time
        time.sleep(0.1)  # 给线程一点启动时间
        if self.audio_processing_thread.is_alive():
            print("✅ 音频处理线程状态: 运行中")
            print(f"✅ 线程ID: {self.audio_processing_thread.ident}")
        else:
            print("❌ 音频处理线程状态: 未启动")
            
        # 调试：检查队列初始状态
        print(f"📦 音频队列初始状态: 大小={self.audio_buffer_queue.qsize()}, 最大大小={self.audio_buffer_queue.maxsize}")
        print(f"🎯 is_audio_processing标志: {self.is_audio_processing}")
        print(f"🎯 is_recording标志: {self.is_recording}")
        print(f"🎯 is_monitoring_only标志: {getattr(self, 'is_monitoring_only', 'Not set')}")
    
    def stop_audio_processing_thread(self):
        """停止异步音频处理线程"""
        try:
            print("🔄 正在停止异步音频处理线程...")
            self.is_audio_processing = False
            if self.audio_processing_thread and self.audio_processing_thread.is_alive():
                self.audio_processing_thread.join(timeout=2.0)  # 等待最多2秒
                if self.audio_processing_thread.is_alive():
                    print("⚠️ 音频处理线程未能正常停止")
                else:
                    print("✅ 异步音频处理线程已停止")
            else:
                print("✅ 异步音频处理线程已停止")
        except Exception as e:
            print(f"❌ 停止音频处理线程错误: {e}")

    def _apply_actual_input_samplerate(self, actual_rate: int):
        """将检测器采样率与实际输入采样率对齐，避免频率缩放/八度错误。
        - 更新 self.sample_rate 及相关子模块
        - 触发帧化参数重算
        - 清理检测缓冲和平滑状态
        """
        try:
            ar = int(actual_rate)
        except Exception:
            return
        if ar <= 0:
            return
        old = getattr(self, 'sample_rate', None)
        if old != ar:
            self.sample_rate = ar
            try:
                print(f"🔁 采样率同步: {old} -> {ar} Hz")
            except Exception:
                pass
            # 同步相关组件
            try:
                if hasattr(self, 'audio_processor') and self.audio_processor is not None:
                    if hasattr(self.audio_processor, 'sample_rate'):
                        self.audio_processor.sample_rate = ar
            except Exception:
                pass
            try:
                if hasattr(self, 'noise_processor') and self.noise_processor is not None:
                    if hasattr(self.noise_processor, 'sample_rate'):
                        self.noise_processor.sample_rate = ar
            except Exception:
                pass
            # 让帧化在新采样率下重新计算：删除标志以触发初始化分支
            try:
                if hasattr(self, '_frame_config_initialized'):
                    delattr(self, '_frame_config_initialized')
            except Exception:
                pass
            # 清理检测缓冲与平滑缓存（避免旧SR残留）
            try:
                self._dpv_buf = np.zeros(0, dtype=np.float64)
            except Exception:
                pass
            for attr, val in (('_freq_smooth', 0.0), ('_last_stable_frequency', 0.0)):
                try:
                    setattr(self, attr, val)
                except Exception:
                    pass
    
    def _audio_processing_loop(self):
        """音频处理循环 - 在独立线程中运行"""
        # ================== 优化版本：提高分析帧率 ==================
        # 目标：减少窗口等待时间 + 加快队列清空速度 + 动态节流
        target_hz = 500.0                    # 上限循环频率（仅在无 backlog 时）
        processing_interval = 1.0 / target_hz

        # 按性能模式限速音高分析频率（与检测频率对齐）
        try:
            from src.audio_processing.performance_manager import get_performance_manager
            _pm = get_performance_manager()
            _cfg = _pm.get_current_config() if _pm else None
            self._analysis_target_hz = float(_cfg.detection_frequency) if _cfg else 30.0
        except Exception:
            self._analysis_target_hz = 30.0
        # 安全下限与上限，避免过低导致细节点稀疏
        try:
            if self._analysis_target_hz < 45.0:
                try:
                    cfg_val = getattr(_cfg, 'detection_frequency', 'N/A') if '_cfg' in locals() and _cfg else 'N/A'
                except Exception:
                    cfg_val = 'N/A'
                print(f"⚠️ 检测频率过低({cfg_val}Hz)，使用默认45Hz")
                self._analysis_target_hz = 45.0
            elif self._analysis_target_hz > 120.0:
                self._analysis_target_hz = 120.0
        except Exception:
            pass
        self._min_analysis_interval = 1.0 / max(1.0, self._analysis_target_hz)
        if not hasattr(self, '_last_analysis_time'):
            self._last_analysis_time = 0.0

        if not hasattr(self, '_frame_config_initialized'):
            # 根据最小频率动态设置窗口（覆盖旧的固定40ms设计）
            min_f = getattr(self, 'min_frequency', 80) or 80
            # 至少包含 ~2.5 个周期，保证低频分辨率，同时不过大
            desired_window = int(self.sample_rate / min_f * 2.5)  # ~3000(96k/80*2.5)
            # 规范到常见处理长度，利于 FFT / 自相关效率
            allowed_windows = [1024, 1536, 2048, 2560, 3072, 3584, 4096]
            self._frame_window = min(4096, next((w for w in allowed_windows if w >= desired_window), 4096))
            # hop 随性能模式自适应：Quiet=1/4, Balanced≈1/7, High≈1/8（进一步提高时间分辨率）
            hop_div = 4
            try:
                from src.audio_processing.performance_manager import get_performance_manager, PerformanceMode
                _pm0 = get_performance_manager()
                _mode0 = _pm0.get_current_mode() if _pm0 else None
                if _mode0 == PerformanceMode.HIGH_PERFORMANCE:
                    hop_div = 8
                elif _mode0 == PerformanceMode.BALANCED:
                    hop_div = 7
                else:
                    hop_div = 4
            except Exception:
                hop_div = 4
            # 允许更小的 hop 下限（128 样本），减少端到端延迟
            self._frame_hop = max(128, self._frame_window // hop_div)
            self._frame_window_sec = self._frame_window / self.sample_rate
            self._frame_hop_sec = self._frame_hop / self.sample_rate
            self._frame_buffer = []
            self._frame_config_initialized = True
            if getattr(self, 'debug_flags', {}).get('queue_log', False):
                print(f"⚙️ 新帧配置: window={self._frame_window}({self._frame_window_sec*1000:.1f}ms) hop={self._frame_hop}({self._frame_hop_sec*1000:.1f}ms)")
        else:
            # 防御：若窗口或hop未设置，立即重新初始化（避免递归）
            if not hasattr(self, '_frame_window') or not hasattr(self, '_frame_hop'):
                min_f = getattr(self, 'min_frequency', 80) or 80
                desired_window = int(self.sample_rate / min_f * 2.5)
                allowed_windows = [1024, 1536, 2048, 2560, 3072, 3584, 4096]
                self._frame_window = min(4096, next((w for w in allowed_windows if w >= desired_window), 4096))
                # 自适应hop
                hop_div = 4
                try:
                    from src.audio_processing.performance_manager import get_performance_manager, PerformanceMode
                    _pm0 = get_performance_manager()
                    _mode0 = _pm0.get_current_mode() if _pm0 else None
                    if _mode0 == PerformanceMode.HIGH_PERFORMANCE:
                        hop_div = 8
                    elif _mode0 == PerformanceMode.BALANCED:
                        hop_div = 7
                    else:
                        hop_div = 4
                except Exception:
                    hop_div = 4
                # 更小的 hop 下限（128 样本）
                self._frame_hop = max(128, self._frame_window // hop_div)
                self._frame_window_sec = self._frame_window / self.sample_rate
                self._frame_hop_sec = self._frame_hop / self.sample_rate
                if not hasattr(self, '_frame_buffer'):
                    self._frame_buffer = []
                if getattr(self, 'debug_flags', {}).get('queue_log', False):
                    print(f"⚙️ 帧配置修复: window={self._frame_window}({self._frame_window_sec*1000:.1f}ms) hop={self._frame_hop}({self._frame_hop_sec*1000:.1f}ms)")
            # 若已有旧配置且窗口过大（>4096或>45ms）则在空闲时渐进收缩
            if self._frame_window > 4096 or self._frame_window_sec > 0.045:
                self._frame_window = 4096
                self._frame_hop = max(192, self._frame_window // 5)
                self._frame_window_sec = self._frame_window / self.sample_rate
                self._frame_hop_sec = self._frame_hop / self.sample_rate
                if getattr(self, 'debug_flags', {}).get('queue_log', False):
                    print(f"⚙️ 帧配置回落: window={self._frame_window} hop={self._frame_hop}")
        
        # 🔥 记录处理开始时间用于检测频率计算
        self.processing_start_time = time.time()
        
        # 添加调试计数器
        loop_counter = 0
        print("🔄 音频处理循环开始运行")
        print(f"🔄 处理线程状态: is_audio_processing={self.is_audio_processing}")
        print(f"🔥 处理开始时间已记录: {self.processing_start_time}")
        
        while self.is_audio_processing:
            start_time = time.time()
            loop_counter += 1
            # 周期性刷新目标检测频率（响应模式切换）
            if loop_counter % 200 == 0:
                try:
                    from src.audio_processing.performance_manager import get_performance_manager
                    _pm = get_performance_manager()
                    if _pm:
                        _cfg = _pm.get_current_config()
                        new_hz = float(_cfg.detection_frequency)
                        # 安全下限/上限
                        if new_hz < 45.0:
                            new_hz = 45.0
                        elif new_hz > 120.0:
                            new_hz = 120.0
                        if abs(new_hz - getattr(self, '_analysis_target_hz', new_hz)) > 0.1:
                            self._analysis_target_hz = new_hz
                            self._min_analysis_interval = 1.0 / max(1.0, self._analysis_target_hz)
                except Exception:
                    pass
            
            # 🎯 增强调试：更频繁地输出状态信息
            if loop_counter <= 5 or loop_counter % 100 == 0:
                queue_size = self.audio_buffer_queue.qsize()
                if getattr(self, 'debug_flags', {}).get('queue_log', False):
                    self._log_rate_limit('loop_brief', f"🔄 处理循环#{loop_counter}: 队列={queue_size}", interval=0.5, burst=3)
                
                # 检查关键状态
                if loop_counter <= 5:
                    print(f"   🎯 is_recording={self.is_recording}")
                    print(f"   🎯 is_monitoring_only={getattr(self, 'is_monitoring_only', 'Not set')}")
                    print(f"   🎯 should_save={getattr(self, 'should_save', 'Not set')}")
            
            # ================== 队列摄取优化 ==================
            audio_packets = []
            try:
                queue_backlog = self.audio_buffer_queue.qsize()
                # 自适应批量：不足一帧时一次性尽可能填满，避免高等待
                need_samples = max(0, getattr(self, '_frame_window', 2048) - len(getattr(self, '_frame_buffer', [])))
                # 预计需要的包数（考虑 chunk_size）
                est_needed_packets = (need_samples // self.chunk_size) + 1 if need_samples > 0 else 1
                # 基础批量 + backlog 放大， capped（进一步提高上限并更积极摄取）
                max_batch = min(120, max(12, est_needed_packets * 2, queue_backlog))
                while not self.audio_buffer_queue.empty() and len(audio_packets) < max_batch:
                    audio_packets.append(self.audio_buffer_queue.get_nowait())
            except queue.Empty:
                pass
            
            # 🔥 强制调试：每100次循环检查队列状态
            if loop_counter % 100 == 0:
                queue_size = self.audio_buffer_queue.qsize()
                got_packets = len(audio_packets)
                if getattr(self, 'debug_flags', {}).get('queue_log', False):
                    self._log_rate_limit('queue_force', f"🔥 队列调试#{loop_counter}: size={queue_size} got={got_packets}", interval=1.2)
                if got_packets == 0 and queue_size > 0:
                    self._log_rate_limit('queue_anomaly', f"⚠️ 队列有数据但获取失败 size={queue_size}", interval=2.0)
                elif got_packets > 0:
                    total_samples = sum(len(p['data']) for p in audio_packets)
                    if getattr(self, 'debug_flags', {}).get('queue_log', False):
                        self._log_rate_limit('queue_ok', f"✅ 获取{got_packets}包 共{total_samples}样本", interval=1.0, burst=2)
            
            # 首次获取到数据时的调试信息
            if audio_packets and loop_counter <= 10:
                if getattr(self, 'debug_flags', {}).get('queue_log', False):
                    print(f"🎵 音频处理循环首次获取数据! 循环#{loop_counter}, 音频包数量={len(audio_packets)}")
                    for i, packet in enumerate(audio_packets[:1]):  # 只显示第一个包的详情
                        data_len = len(packet['data'])
                        rms = np.sqrt(np.mean(packet['data'] ** 2))
                        print(f"   📦 包{i}: 数据长度={data_len}, RMS={rms:.4f}, should_save={packet['should_save']}")
            
            # 🎯 额外的调试：如果队列一直为空
            if loop_counter > 500 and loop_counter % 500 == 0:
                queue_size = self.audio_buffer_queue.qsize()
                if queue_size == 0 and getattr(self, 'debug_flags', {}).get('queue_log', False):
                    print("⚠️ 音频队列持续为空 - 可能原因:")
                    print("   1. 音频回调函数未被调用")
                    print("   2. 音频流未正确启动")
                    print("   3. 音频设备权限问题")
                    print(f"   📊 状态检查: is_audio_processing={self.is_audio_processing}")
                    print(f"   📊 音频流状态: {getattr(self, 'audio_stream', 'None')}")
            
            if audio_packets:
                try:
                    # 保存需求处理
                    for packet in audio_packets:
                        if packet['should_save']:
                            self.audio_buffer.extend(packet['data'])

                    # 累加帧缓冲
                    for packet in audio_packets:
                        self._frame_buffer.extend(packet['data'])

                    # 维护最大长度（2秒）
                    max_len = int(self.sample_rate * 2)
                    if len(self._frame_buffer) > max_len:
                        self._frame_buffer = self._frame_buffer[-max_len:]

                    produced = 0
                    # 根据性能模式设置本循环帧产出上限，防止阻塞GUI
                    try:
                        from src.audio_processing.performance_manager import get_performance_manager, PerformanceMode
                        _pm = get_performance_manager()
                        _mode = _pm.get_current_mode() if _pm else None
                        if _mode == PerformanceMode.HIGH_PERFORMANCE:
                            _max_frames = 64  # 高性能：更高单轮上限
                        elif _mode == PerformanceMode.QUIET:
                            _max_frames = 24  # 安静：适度提高
                        else:
                            _max_frames = 56  # 平衡：提高追赶能力与密度
                    except Exception:
                        _max_frames = 24
                    # 自适应突发：积压较多时临时提升本轮上限，加速清空，避免累计延迟
                    try:
                        qsz = int(self.audio_buffer_queue.qsize())
                    except Exception:
                        qsz = 0
                    try:
                        buf_len = int(len(self._frame_buffer)) if hasattr(self, '_frame_buffer') else 0
                    except Exception:
                        buf_len = 0
                    # 重度积压：更早触发显著提升（设更高硬上限，避免阻塞GUI）
                    if (qsz >= 12) or (buf_len >= (self._frame_window + self._frame_hop * 4)):
                        _max_frames = min(96, int(max(_max_frames, 56)))
                    # 轻中度积压：更早倍增以快速追平
                    elif (qsz >= 4) or (buf_len >= (self._frame_window + self._frame_hop * 2)):
                        _max_frames = min(72, int(_max_frames * 2))
                    # 单循环尽量多产出，提升时间分辨率（有限上限防止阻塞GUI）
                    while len(self._frame_buffer) >= self._frame_window and produced < _max_frames:
                        frame = np.array(self._frame_buffer[:self._frame_window])
                        self._frame_buffer = self._frame_buffer[self._frame_hop:]
                        produced += 1

                        # 在录音或全局监听下均执行分析；即使为纯监听也分析，以保持绘制密度与诊断
                        should_analyze_pitch = (
                            getattr(self, 'is_recording', False) or
                            self.is_global_monitoring_active or
                            getattr(self, 'is_monitoring_only', False)
                        )
                        if should_analyze_pitch:
                            # 对每个产出的帧直接执行一次分析，提升有效FPS与点密度
                            self.process_audio_for_pitch_async(frame)
                    if produced and loop_counter % 300 == 0:
                        if getattr(self, 'debug_flags', {}).get('queue_log', False):
                            self._log_rate_limit('frame_prod', f"🎵 帧产出={produced} 剩余={len(self._frame_buffer)}", interval=2.0)
                except Exception as audio_error:
                    print(f"❌ 帧化处理错误: {audio_error}")
                    continue
            
            # ================== 动态节流 ==================
            elapsed = time.time() - start_time
            backlog = self.audio_buffer_queue.qsize()
            if backlog == 0 and elapsed < processing_interval:
                # 只有在无 backlog 时才 sleep，确保积压快速清空
                time.sleep(processing_interval - elapsed)
    
    def process_audio_for_pitch_async(self, audio_data):
        """异步音高分析 - 简化版本，只使用单一可靠的检测算法"""
        try:
            # 纯监听模式下也执行分析，确保绘制与诊断一致
            
            # 🎯 增加调试计数器
            if not hasattr(self, '_pitch_analysis_counter'):
                self._pitch_analysis_counter = 0
                print("🔍 音高分析函数首次调用")
            
            self._pitch_analysis_counter += 1
            # 先记录当前时间
            current_time = time.time()
            # 诊断：帧间隔统计（仅在启用调试时计算，避免热路径开销）
            if getattr(self, 'debug_flags', {}).get('queue_log', False):
                if not hasattr(self, '_diag_last_pitch_time'):
                    self._diag_last_pitch_time = current_time
                    self._diag_pitch_intervals = deque(maxlen=300)
                    self._diag_pitch_last_report = current_time
                else:
                    pitch_interval = current_time - self._diag_last_pitch_time
                    if 0 < pitch_interval < 1.0:
                        self._diag_pitch_intervals.append(pitch_interval)
                    self._diag_last_pitch_time = current_time
                    if current_time - self._diag_pitch_last_report > 2.0 and self._diag_pitch_intervals:
                        avg_pi = sum(self._diag_pitch_intervals)/len(self._diag_pitch_intervals)
                        max_pi = max(self._diag_pitch_intervals)
                        sorted_pi = sorted(self._diag_pitch_intervals)
                        p95_pi = sorted_pi[int(0.95*len(sorted_pi)) - 1] if len(sorted_pi) >= 5 else max_pi
                        est_fps = 1.0/avg_pi if avg_pi > 0 else 0.0
                        now = time.time()
                        if not hasattr(self, '_last_frame_diag_log'):
                            self._last_frame_diag_log = 0.0
                        if now - self._last_frame_diag_log > 2.0:  # 2s节流
                            print(f"🎯 分析帧诊断: 平均间隔={avg_pi*1000:.1f}ms, 最大={max_pi*1000:.1f}ms, p95={p95_pi*1000:.1f}ms, 估计FPS={est_fps:.1f}")
                            self._last_frame_diag_log = now
                        self._diag_pitch_last_report = current_time
            audio_rms = np.sqrt(np.mean(audio_data ** 2))
            # 保存本帧RMS供平滑阶段自适应使用
            try:
                self._last_frame_rms = float(audio_rms)
            except Exception:
                self._last_frame_rms = float(audio_rms)
            
            # 前几次调用的详细调试
            # 初始若需详细调试，可通过 debug_flags 控制；默认禁用以减轻开销
            if getattr(self, 'debug_flags', {}).get('pitch_log', False) and self._pitch_analysis_counter <= 5:
                print(f"🔍 音高分析#{self._pitch_analysis_counter}: 数据长度={len(audio_data)}, RMS={audio_rms:.4f}")
            
            # 🎯 快速路径：Balanced/High默认走超轻量路径：关闭降噪/融合/颤音/频域精修
            fast_path = True
            try:
                from src.audio_processing.performance_manager import get_performance_manager, PerformanceMode
                _pm = get_performance_manager()
                _mode = _pm.get_current_mode() if _pm else None
                if _mode == PerformanceMode.QUIET:
                    fast_path = False
            except Exception:
                fast_path = True

            processed_audio = audio_data
            original_rms = np.sqrt(np.mean(audio_data ** 2))
            if not fast_path and self.noise_processor and self.noise_processor.noise_reduction_mode != "关闭":
                try:
                    processed_audio = self.noise_processor.process_audio(audio_data)
                except Exception:
                    processed_audio = audio_data
            
            # ========= 呼吸/静音判定 (避免假高频 2500Hz) ========= #
            if not hasattr(self, '_last_valid_pitch_time'):
                self._last_valid_pitch_time = current_time

            breath_rms_threshold = 0.0025  # 更宽松：提升弱声段的检测机会
            # 进一步放宽静音阈值，减少安静高音被直接判无音高
            min_voice_rms = 0.0005

            # 若 RMS 极低，直接判定无音高（不更新平滑状态）
            if audio_rms < min_voice_rms:
                # 节流无音高信号，避免淹没UI队列（时间轴由独立计时器驱动，无需每帧发）
                if not hasattr(self, '_no_pitch_emit_interval'):
                    # 按模式初始化默认节流
                    self._no_pitch_emit_interval = float(getattr(self, '_no_pitch_emit_interval_default', 0.05))
                    self._last_no_pitch_emit_t = 0.0
                if (current_time - getattr(self, '_last_no_pitch_emit_t', 0.0)) >= self._no_pitch_emit_interval:
                    frame = PitchFrame(
                        timestamp=current_time,
                        f0_raw=0.0,
                        f0_smooth=0.0,
                        confidence=0.0,
                        note_info=None,
                        has_pitch=False,
                        audio_rms=audio_rms,
                        vibrato_info={'has_vibrato': False}
                    )
                    try:
                        self._emit_pitch_data_throttled(frame.to_dict())
                    except Exception:
                        pass
                    self._last_no_pitch_emit_t = current_time
                return

            # 🎯 统一检测服务优先；保持原有模式开关与回退
            raw_frequency = 0.0
            if hasattr(self, 'pitch_service') and self.pitch_service is not None:
                try:
                    f0, conf = self.pitch_service.detect(np.array(processed_audio, dtype=np.float64, copy=False))
                    raw_frequency = float(f0 or 0.0)
                except Exception:
                    raw_frequency = 0.0

            if raw_frequency <= 0.0:
                # 快速路径仅一次轻量YIN；仅在非快速路径时才考虑融合
                if not hasattr(self, '_yin_miss_streak'):
                    self._yin_miss_streak = 0
                raw_frequency = self.detect_pitch_simple_yin(processed_audio)
                if raw_frequency <= 0 and not fast_path:
                    self._yin_miss_streak += 1
                    if self._yin_miss_streak >= 3:
                        # 仅在非快速路径下尝试融合
                        raw_frequency = self.detect_pitch_with_vibrato(processed_audio)
                        self._yin_miss_streak = 0
                else:
                    self._yin_miss_streak = 0

            # 仅在存在“低八度”风险或与2f接近历史时才进行谱域精修，减少FFT开销
            if raw_frequency > 0 and not fast_path:
                # 非快速路径下的保守精修（已在上一次提交中严格节流）
                try:
                    # 若有队列积压则跳过精修
                    if self.audio_buffer_queue.qsize() < 6:
                        lf = float(getattr(self, '_last_stable_frequency', 0.0) or 0.0)
                        if (raw_frequency < 150.0) and (lf > 0):
                            ratio = max((raw_frequency * 2.0) / max(lf, 1e-6), 1e-6)
                            if abs(np.log2(ratio)) <= (1.0 / 24.0):
                                raw_frequency = self._finalize_frequency(float(raw_frequency), np.array(processed_audio, dtype=np.float64))
                except Exception:
                    pass

            # ========= 假高频 / 呼吸尖峰抑制 ========= #
            spurious_high = False
            if raw_frequency > 0:
                # 条件1：超高频且能量低（典型呼吸尖峰）
                if raw_frequency > 1700 and audio_rms < 0.015:
                    spurious_high = True
                # 条件2：相对上一稳定频率跳变倍数过大且信号不强
                if not spurious_high and hasattr(self, '_last_stable_frequency') and self._last_stable_frequency > 0:
                    if raw_frequency > self._last_stable_frequency * 2.5 and audio_rms < 0.015:
                        spurious_high = True
                # 条件3：呼吸期（RMS 在静音与正常之间）且高频>1500
                if not spurious_high and breath_rms_threshold > audio_rms >= min_voice_rms and raw_frequency > 1500:
                    spurious_high = True

            if spurious_high:
                # 不更新平滑状态，直接视为无音高（制造时间间隔用于段断开）
                if not hasattr(self, '_no_pitch_emit_interval'):
                    self._no_pitch_emit_interval = float(getattr(self, '_no_pitch_emit_interval_default', 0.05))
                    self._last_no_pitch_emit_t = 0.0
                if (current_time - getattr(self, '_last_no_pitch_emit_t', 0.0)) >= self._no_pitch_emit_interval:
                    frame = PitchFrame(
                        timestamp=current_time,
                        f0_raw=0.0,
                        f0_smooth=0.0,
                        confidence=0.0,
                        note_info=None,
                        has_pitch=False,
                        audio_rms=audio_rms,
                        vibrato_info={'has_vibrato': False}
                    )
                    try:
                        self._emit_pitch_data_throttled(frame.to_dict())
                    except Exception:
                        pass
                    self._last_no_pitch_emit_t = current_time
                return

            # Phase1: 后处理（跳变抑制 + 平滑）仅在非假高频情况下执行
            smooth_frequency = self._post_process_pitch(raw_frequency) if raw_frequency > 0 else 0.0
            
            # 🔥 关键修复：大幅降低有效音高的最低要求
            if smooth_frequency > 10:  # 🔥 极低有效音高阈值 (20Hz → 10Hz)
                note_info = self.frequency_to_note_info(smooth_frequency)
                
                # 检测颤音：降低频度与在极低RMS时跳过，减少CPU负担
                # 快速路径：跳过颤音检测
                vibrato_info = {'has_vibrato': False}
                
                # 简单置信度占位：后续可从检测器返回值改造
                confidence = 0.9 if raw_frequency > 0 else 0.0

                # Phase1: 使用 PitchFrame 抽象（仍向外发 dict 保持兼容）
                frame = PitchFrame(
                    timestamp=current_time,
                    f0_raw=raw_frequency,
                    f0_smooth=smooth_frequency,
                    confidence=confidence,
                    note_info=note_info,
                    has_pitch=True,
                    audio_rms=audio_rms,
                    vibrato_info=vibrato_info
                )
                pitch_data = frame.to_dict()
                
                # 🔥 强制保存历史数据和发送信号
                try:
                    self.pitch_history.append({
                        'frequency': smooth_frequency,
                        'timestamp': current_time,
                        'confidence': confidence,
                        'note_info': note_info
                    })
                    # 节流发射：避免Qt事件队列拥塞
                    self._emit_pitch_data_throttled(pitch_data)
                    
                    # 成功检测调试输出
                    # 仅在调试需要时打印，避免热路径开销
                    if getattr(self, 'debug_flags', {}).get('pitch_log', False) and (self._pitch_analysis_counter % 10 == 0):
                        print(f"🎵✅ 音高成功(raw={raw_frequency:.1f}Hz, smooth={smooth_frequency:.1f}Hz) → {note_info.get('note_name', 'N/A')}{note_info.get('octave', '')}")
                except Exception as emit_error:
                    print(f"❌ 信号发送失败: {emit_error}")
                    
            else:
                # 无音高：节流时间戳信号（时间轴由timer推进，无需每帧发）
                if not hasattr(self, '_no_pitch_emit_interval'):
                    self._no_pitch_emit_interval = float(getattr(self, '_no_pitch_emit_interval_default', 0.05))
                    self._last_no_pitch_emit_t = 0.0
                if (current_time - getattr(self, '_last_no_pitch_emit_t', 0.0)) >= self._no_pitch_emit_interval:
                    frame = PitchFrame(
                        timestamp=current_time,
                        f0_raw=0.0,
                        f0_smooth=0.0,
                        confidence=0.0,
                        note_info=None,
                        has_pitch=False,
                        audio_rms=audio_rms,
                        vibrato_info={'has_vibrato': False}
                    )
                    timestamp_data = frame.to_dict()
                    try:
                        self._emit_pitch_data_throttled(timestamp_data)
                    except Exception:
                        pass
                    self._last_no_pitch_emit_t = current_time
        
        except Exception as e:
            print(f"❌ 异步音高分析错误: {e}")
            # 错误时的时间戳信号也做节流，避免持续错误淹没UI
            try:
                now_err = time.time()
                if not hasattr(self, '_no_pitch_emit_interval'):
                    self._no_pitch_emit_interval = 0.08
                    self._last_no_pitch_emit_t = 0.0
                if (now_err - getattr(self, '_last_no_pitch_emit_t', 0.0)) >= self._no_pitch_emit_interval:
                    timestamp_data = {
                        'timestamp': now_err,
                        'frequency': 0,
                        'confidence': 0,
                        'note_info': None,
                        'has_pitch': False,
                        'audio_rms': 0,
                        'vibrato_info': {'has_vibrato': False}
                    }
                    self._emit_pitch_data_throttled(timestamp_data)
                    self._last_no_pitch_emit_t = now_err
            except Exception:
                pass  # 忽略错误情况下的信号发送失败

    # ========= UI发射节流，防止Qt事件队列拥塞 ========= #
    def _emit_pitch_data_throttled(self, pitch_dict: dict):
        try:
            now = time.time()
            if not hasattr(self, '_ui_emit_min_interval'):
                # 缺省最小间隔 30ms，可由模式调整 elsewhere
                self._ui_emit_min_interval = float(getattr(self, '_ui_emit_min_interval_default', 0.03))
                self._ui_last_emit_t = 0.0
                self._ui_pending = None
            # 到达最小间隔则发射，否则合并为待发，保留最新
            if (now - getattr(self, '_ui_last_emit_t', 0.0)) >= self._ui_emit_min_interval:
                try:
                    self.pitch_detected.emit(pitch_dict)
                finally:
                    self._ui_last_emit_t = now
                    self._ui_pending = None
            else:
                self._ui_pending = pitch_dict
        except Exception:
            try:
                self.pitch_detected.emit(pitch_dict)
            except Exception:
                pass
    
    # ========= 辅助：频域与谐波精修（避免弱基频的低八度误判） ========= #
    def _get_fft_for_refine(self, audio: np.ndarray):
        """计算用于谐波精修的FFT频谱，返回 (freqs, magnitude)。"""
        try:
            windowed = audio * np.hanning(len(audio))
            spec = np.fft.rfft(windowed)
            mag = np.abs(spec)
            freqs = np.fft.rfftfreq(len(windowed), 1 / float(self.sample_rate))
            return freqs, mag
        except Exception:
            return None, None

    def _harmonic_support(self, f: float, freqs: np.ndarray, mag: np.ndarray, max_h: int = 6) -> float:
        """对候选基频 f 计算谐波支持分数：S(f)=sum_k |X(kf)|/k，带宽±3%。"""
        if f <= 0 or freqs is None or mag is None or len(freqs) != len(mag):
            return 0.0
        total = 0.0
        # 频率分辨率，用于设定最小带宽，避免因bin间隔过大导致mask为空
        try:
            df = float(freqs[1] - freqs[0]) if len(freqs) > 1 else 0.0
        except Exception:
            df = 0.0
        for k in range(1, max_h + 1):
            target = k * f
            if target > freqs[-1]:
                break
            # 带宽至少覆盖≥1个bin，且不少于2Hz；高频放宽到4%
            bw = max(2.0, target * (0.03 if target < 800 else 0.04), df * 1.25)
            mask = (freqs >= (target - bw)) & (freqs <= (target + bw))
            if not np.any(mask):
                continue
            peak = float(np.max(mag[mask]))
            total += peak / k
        return total

    def _hps_candidate_from_fft(self, freqs: np.ndarray, mag: np.ndarray, min_f: float, max_f: float, n_harm: int = 4) -> tuple:
        """谐波乘积谱(HPS)候选：在频谱上做多次下采样相乘，突出基频，返回(best_f, score)。"""
        try:
            if freqs is None or mag is None or len(freqs) != len(mag) or len(mag) < 8:
                return 0.0, 0.0
            m = np.array(mag, dtype=np.float64)
            hps = m.copy()
            L = len(m)
            for h in range(2, max(2, int(n_harm)) + 1):
                l = L // h
                if l <= 1:
                    break
                hps[:l] *= m[::h][:l]
                # 其余尾部缩短，避免用未定义数据
            # 频率范围内找峰
            mask = (freqs >= float(min_f)) & (freqs <= float(max_f))
            if not np.any(mask):
                return 0.0, 0.0
            idxs = np.where(mask)[0]
            if idxs.size == 0:
                return 0.0, 0.0
            # 只在有效HPS长度内搜索
            valid_len = np.max([L // max(2, int(n_harm)), 2])
            lo, hi = int(idxs[0]), int(idxs[-1])
            hi = min(hi, valid_len - 1)
            if hi <= lo:
                return 0.0, 0.0
            seg = hps[lo:hi+1]
            pi = int(np.argmax(seg))
            best_idx = lo + pi
            best_f = float(freqs[best_idx])
            best_s = float(seg[pi])
            return best_f, best_s
        except Exception:
            return 0.0, 0.0

    def _shs_candidate_from_fft(self, freqs: np.ndarray, mag: np.ndarray, min_f: float, max_f: float,
                                top_k: int = 8, max_harm: int = 6) -> tuple:
        """从FFT峰值构建子谐波求和(SHS)候选，返回 (best_f, score)。
        - 从人声范围内选取前K个峰值
        - 对每个峰值 fp 产生候选 f = fp / h (h=1..max_harm)，用权重 mag/h 累加
        - 将相近候选(±3%)聚合
        """
        try:
            if freqs is None or mag is None or len(freqs) != len(mag) or len(freqs) == 0:
                return 0.0, 0.0
            mask = (freqs >= min_f) & (freqs <= max_f)
            if not np.any(mask):
                return 0.0, 0.0
            vf = freqs[mask]
            vm = mag[mask]
            if len(vf) < 4:
                return 0.0, 0.0
            # 选取前K个峰：使用argpartition近似快速选择
            k = min(top_k, len(vm))
            idxs = np.argpartition(vm, -k)[-k:]
            # 排序方便权重累加稳定
            idxs = idxs[np.argsort(vm[idxs])[::-1]]

            buckets = []  # [(f_center, score)]
            def _accumulate(f_cand: float, w: float):
                if f_cand < min_f or f_cand > max_f:
                    return
                # 合并到±3%内的桶
                for i, (fc, sc) in enumerate(buckets):
                    if abs(f_cand - fc) <= max(2.0, 0.03 * fc):
                        # 简单加权平均与分数累加
                        new_fc = (fc * sc + f_cand * w) / (sc + w)
                        buckets[i] = (new_fc, sc + w)
                        return
                buckets.append((f_cand, w))

            for idx in idxs:
                fp = float(vf[idx])
                amp = float(vm[idx])
                if amp <= 0:
                    continue
                for h in range(1, max_harm + 1):
                    f_cand = fp / h
                    # 权重：峰值幅度/谐波序号（移除对~200Hz的集中偏置，改为更温和的极低频轻惩罚）
                    # 原先以200Hz为分界的惩罚会造成候选在200Hz附近聚集，这里改为对<120Hz做极轻惩罚
                    low_bias = 1.0 + 0.05 * max(0.0, (120.0 - f_cand) / 120.0)
                    w = amp / (h * low_bias)
                    _accumulate(f_cand, w)

            if not buckets:
                return 0.0, 0.0
            # 选择分数最高者
            buckets.sort(key=lambda t: t[1], reverse=True)
            best_f, best_s = buckets[0]
            return float(best_f), float(best_s)
        except Exception:
            return 0.0, 0.0

    def _refine_f0_with_harmonics(self, f: float, freqs: np.ndarray, mag: np.ndarray, min_f: float, max_f: float,
                                  last_stable: float = 0.0, rms: float = None) -> float:
        """基于谐波支持、轻量倒谱提示与时间连续性的温和精修，仅向上修正以抑制“低八度”误判。"""
        if f <= 0 or freqs is None or mag is None:
            return f
        cand = float(f)
        # 谱域谐波支持
        s1 = self._harmonic_support(cand, freqs, mag)
        f2 = cand * 2.0
        s2 = self._harmonic_support(f2, freqs, mag) if f2 <= max_f * 1.02 else 0.0
        f3 = cand * 3.0
        s3 = self._harmonic_support(f3, freqs, mag) if f3 <= max_f * 1.02 else 0.0

        # 轻量 cepstrum 提示：比较 T 与 T/2 的倒谱峰
        cep_hint_up = False
        try:
            # 从 rfft 幅度估计倒谱长度 N≈2*(len(mag)-1)
            N = max(2 * (len(mag) - 1), 2)
            # 防止 log(0)
            cep = np.fft.irfft(np.log(mag + 1e-12), n=N)
            # 期望周期（采样点）
            T = int(round(float(self.sample_rate) / max(cand, 1e-6)))
            T2 = int(round(float(self.sample_rate) / max(f2, 1e-6))) if f2 > 0 else 0
            # 在安全范围内取局部最大值（±1邻域平均）
            def _cep_peak(idx: int) -> float:
                if idx <= 1 or idx >= len(cep) - 2:
                    return 0.0
                return float(max(cep[idx-1:idx+2].mean(), 0.0))
            c1 = _cep_peak(T)
            c2 = _cep_peak(T2)
            # 当 T/2 线索显著更强时，给出“上修”提示
            if c2 > c1 * 1.12 and c2 > 0:
                cep_hint_up = True
        except Exception:
            cep_hint_up = False

        # 时间连续性：2f 与上一稳定频率接近（≤1个半音）时，放宽上修条件
        allow_up_by_temporal = False
        try:
            if last_stable and last_stable > 0 and f2 > 0:
                # 以log2域衡量半音差：1个半音≈1/12
                semitone_diff = abs(np.log2(max(f2, 1e-6) / max(last_stable, 1e-6)))
                allow_up_by_temporal = semitone_diff <= (1.0 / 12.0)
        except Exception:
            allow_up_by_temporal = False

        # 音量自适应：很小声时，适度放宽上修门槛
        low_rms = False
        try:
            if rms is not None:
                low_rms = rms < 0.010
        except Exception:
            low_rms = False

        # 仅在候选较低、且 2f 在范围内时考虑上修
        if (cand <= 480.0) and (f2 >= min_f) and (f2 <= max_f * 1.02):
            cond_spec_strong = (s2 > s1 * 1.35 and s2 > s3 * 0.85)
            cond_spec_moderate = (s2 > s1 * 1.20 and s2 > 0.0)
            if allow_up_by_temporal:
                # 有时间一致性时，倒谱提示或轻度谱域优势即可上修
                if cep_hint_up or (s2 > s1 * (1.05 if low_rms else 1.10)):
                    prev = cand
                    cand = f2
                    try:
                        if getattr(self, 'debug_flags', {}).get('pitch_log', False):
                            self._log_rate_limit('harm_refine', f"⬆️ 倍频上修 {prev:.1f}-> {cand:.1f}Hz (temporal ok, low_rms={low_rms})", interval=1.0)
                    except Exception:
                        pass
            else:
                # 无时间一致性，要求更强证据；很小声时略放宽
                if (cond_spec_strong and cep_hint_up) or (s2 > s1 * (1.45 if not low_rms else 1.30)) or (cep_hint_up and cond_spec_moderate):
                    prev = cand
                    cand = f2
                    try:
                        if getattr(self, 'debug_flags', {}).get('pitch_log', False):
                            self._log_rate_limit('harm_refine', f"⬆️ 倍频上修 {prev:.1f}-> {cand:.1f}Hz (spec/cep ok, low_rms={low_rms})", interval=1.0)
                    except Exception:
                        pass

        return float(max(min_f, min(max_f, cand)))

    def _yin_cmndf_at_period(self, x: np.ndarray, period: int) -> float:
        """计算给定周期的YIN CMNDF值（越小越像周期信号）。仅用于候选对比，性能开销小。"""
        try:
            N = len(x)
            if N < 4 or period < 2 or period >= N:
                return 1.0
            # 差分函数 d(tau)
            tau = period
            diff = np.sum((x[:N-tau] - x[tau:]) ** 2)
            # 累积平均归一化差分 CMNDF(tau)
            # 这里用近似：cmndf(tau) = d(tau) / ( (1/tau) * sum_{k=1..tau} d(k) )
            # 逐步累积到 tau 的总差分（简化近似，足够做相对比较）
            acc = 0.0
            for k in range(1, tau + 1):
                # 简化：使用等长窗口的滑动近似（权衡性能）
                if k >= N:
                    break
                acc += np.sum((x[:N-k] - x[k:]) ** 2)
            denom = acc / max(1, tau)
            if denom <= 1e-12:
                return 1.0
            return float(diff / denom)
        except Exception:
            return 1.0

    def _finalize_frequency(self, freq: float, audio_data: np.ndarray, fft_tuple=None, rms: float = None) -> float:
        """统一的返回前精修与裁剪：谐波支持上修 + 与UI设定一致范围 + 轻量YIN判据的八度决策。"""
        if freq is None or freq <= 0:
            return 0.0
        try:
            # 与控制面板保持一致
            if hasattr(self, 'get_frequency_range'):
                min_f, max_f = self.get_frequency_range()
            else:
                min_f = float(getattr(self, 'min_frequency', 80.0))
                max_f = float(getattr(self, 'max_frequency', 1047.0))
            # 频谱（若未提供则计算一次）
            if fft_tuple is not None and isinstance(fft_tuple, (tuple, list)) and len(fft_tuple) == 2:
                freqs, mag = fft_tuple
            else:
                freqs, mag = self._get_fft_for_refine(audio_data)
            last_stable = float(getattr(self, '_last_stable_frequency', 0.0) or 0.0)
            refined = self._refine_f0_with_harmonics(float(freq), freqs, mag, float(min_f), float(max_f), last_stable=last_stable, rms=rms)

            # 在非常可能低八度的场景中，允许迭代x2上修（最多到4f），以覆盖 C3->C5 这类误判
            try:
                if refined > 0 and refined <= 520.0:
                    # 依据谱域支持与时间连续性，做至多一次额外上修
                    f2 = refined * 2.0
                    f4 = refined * 4.0
                    candidates = [refined]
                    if f2 <= max_f * 1.02:
                        candidates.append(f2)
                    if f4 <= max_f * 1.02:
                        candidates.append(f4)
                    if freqs is None or mag is None:
                        freqs, mag = self._get_fft_for_refine(audio_data)
                    # 结合谐波支持与轻量YIN进行评分
                    sr = float(getattr(self, 'sample_rate', 48000.0))
                    best = refined
                    best_score = -1e9
                    for fc in candidates:
                        # 谐波支持
                        s_h = self._harmonic_support(fc, freqs, mag)
                        # YIN近似周期一致性（越小越好，这里用 1/(1+cmndf) 作为分值）
                        T = int(round(sr / max(fc, 1e-6)))
                        c = self._yin_cmndf_at_period(np.array(audio_data, dtype=np.float64), T)
                        y_score = 1.0 / (1.0 + c)
                        # 时间连续性偏好（与上一稳定频率接近者加分，且允许对2f/4f有偏好）
                        temporal = 0.0
                        if last_stable > 0:
                            semitone = abs(np.log2(max(fc,1e-6) / max(last_stable,1e-6))) * 12.0
                            temporal = max(0.0, 1.0 - (semitone / 2.0))  # 2半音内较大加分
                        score = (0.65 * s_h) + (0.25 * y_score) + (0.10 * temporal)
                        if score > best_score:
                            best_score = score
                            best = fc
                    refined = best
            except Exception:
                pass

            # 追加：在低电平时用轻量YIN判据对 refined 与 2f 进行一次八度决策（仅向上）
            try:
                x = np.array(audio_data, dtype=np.float64)
                if rms is None:
                    rms = float(np.sqrt(np.mean(x * x))) if len(x) > 0 else 0.0
                low_level = rms < 0.012
                if low_level and refined > 0 and refined <= 520.0:
                    sr = float(getattr(self, 'sample_rate', 48000.0))
                    f2 = refined * 2.0
                    f4 = refined * 4.0 if refined * 4.0 <= max_f * 1.02 else None
                    # 计算候选的 CMNDF
                    T1 = int(round(sr / max(refined, 1e-6)))
                    c1 = self._yin_cmndf_at_period(x, T1)
                    choose = refined
                    best_val = c1
                    # 2f
                    if f2 <= max_f * 1.02:
                        T2 = int(round(sr / max(f2, 1e-6)))
                        c2 = self._yin_cmndf_at_period(x, T2)
                        # 时间偏好
                        temporal_bias2 = 0.0
                        if last_stable > 0:
                            try:
                                sd2 = abs(np.log2(max(f2,1e-6)/max(last_stable,1e-6)))
                                temporal_bias2 = -0.04 if sd2 <= (1.0/12.0) else 0.0
                            except Exception:
                                temporal_bias2 = 0.0
                        if (c2 + temporal_bias2) < (best_val - 0.04):
                            choose = f2
                            best_val = c2 + temporal_bias2
                    # 4f
                    if f4 is not None:
                        T4 = int(round(sr / max(f4, 1e-6)))
                        c4 = self._yin_cmndf_at_period(x, T4)
                        temporal_bias4 = 0.0
                        if last_stable > 0:
                            try:
                                sd4 = abs(np.log2(max(f4,1e-6)/max(last_stable,1e-6)))
                                temporal_bias4 = -0.03 if sd4 <= (2.0/12.0) else 0.0
                            except Exception:
                                temporal_bias4 = 0.0
                        if (c4 + temporal_bias4) < (best_val - 0.04):
                            choose = f4
                            best_val = c4 + temporal_bias4
                    refined = choose
            except Exception:
                pass
            # 最终裁剪
            return float(max(min_f, min(max_f, refined)))
        except Exception:
            return float(freq)

    def detect_pitch_with_vibrato(self, audio_data):
        """终极敏感音高检测 - 多候选融合 (ACF/FFT/ZCR/SHS) + 谐波与YIN精修"""
        try:
            # 🔥 简化计数器
            if not hasattr(self, '_detection_counter'):
                self._detection_counter = 0
                print("🔥 终极敏感检测器启动")
            
            self._detection_counter += 1
            
            # 🔥 确保输入是numpy数组
            audio_data = np.array(audio_data, dtype=np.float64)
            if len(audio_data) < 16:
                return 0
            
            # 🔥 内部滚动缓冲，确保足够窗长进行稳定检测（对头声/弱基频很重要）
            try:
                if not hasattr(self, '_dpv_buf') or self._dpv_buf is None:
                    self._dpv_buf = np.zeros(0, dtype=np.float64)
                # 追加新数据
                if len(audio_data) > 0:
                    self._dpv_buf = np.concatenate([self._dpv_buf, audio_data])
                # 根据采样率和最低频率动态设定检测窗与缓冲上限
                sr = float(getattr(self, 'sample_rate', 48000) or 48000.0)
                try:
                    ui_min_f = float(getattr(self, 'min_frequency', 80.0))
                except Exception:
                    ui_min_f = 80.0
                # 至少覆盖 ~2.5 个周期，且不低于 ~35ms 的时间窗，上限做保护
                desired_win_period = int(max(1024, min(12288, sr / max(ui_min_f, 50.0) * 2.5)))
                desired_win_time = int(max(1024, min(12288, sr * 0.035)))
                win_len = int(max(desired_win_period, desired_win_time))
                # 滚动缓冲上限：~80ms 或 2x 窗口，取较大者，保护上限 16384
                max_len = int(min(16384, max(int(sr * 0.08), win_len * 2)))
                if len(self._dpv_buf) > max_len:
                    self._dpv_buf = self._dpv_buf[-max_len:]
                if len(self._dpv_buf) < win_len:
                    # 缓冲尚不够，先不检测
                    return 0
                x = self._dpv_buf[-win_len:]
            except Exception:
                x = audio_data

            # 🔥 计算基本信号特征（基于检测窗）
            original_rms = np.sqrt(np.mean(x ** 2))
            
            # 🔥 超低阈值：检测极微弱信号
            if original_rms < 0.0001:
                if self._detection_counter % 1200 == 0:
                    self._log_rate_limit('weak_sig', f"🔇 微弱信号 RMS={original_rms:.6f}", interval=5.0)
                return 0
            
            # 🔥 激进的信号增强
            if original_rms < 0.1:
                enhancement_factor = min(0.2 / original_rms, 100.0)
                x = x * enhancement_factor
                if self._detection_counter % 400 == 0:
                    new_rms = np.sqrt(np.mean(x ** 2))
                    self._log_rate_limit('gain', f"🔊 增强 {original_rms:.4f}->{new_rms:.4f} x{enhancement_factor:.1f}", interval=4.0)
            
            # 🔥 基本预处理
            x = x - np.mean(x)  # 去DC
            
            # 准备与UI一致的频率范围（例如 C2–C6）
            try:
                ui_min_f, ui_max_f = self.get_frequency_range()
            except Exception:
                ui_min_f = float(getattr(self, 'min_frequency', 80.0))
                ui_max_f = float(getattr(self, 'max_frequency', 1047.0))

            # 统一候选收集容器
            candidates = []  # (name, freq, score, extra)

            # 方法1：ACF候选（带抛物线插值）
            try:
                windowed_audio = x * np.hanning(len(x))
                ac = np.correlate(windowed_audio, windowed_audio, mode='full')
                ac = ac[len(ac)//2:]
                if ac[0] > 0:
                    ac = ac / ac[0]
                min_freq, max_freq = float(ui_min_f), float(ui_max_f)
                min_period = max(int(self.sample_rate / max_freq), 2)
                max_period = min(int(self.sample_rate / min_freq), len(ac) - 1)
                if max_period > min_period:
                    seg = ac[min_period:max_period]
                    if len(seg) > 0:
                        pi = int(np.argmax(seg))
                        pv = float(seg[pi])
                        ap = pi + min_period
                        if 0 < pi < len(seg) - 1:
                            y1, y2, y3 = seg[pi-1], seg[pi], seg[pi+1]
                            off = 0.5 * (y1 - y3) / (y1 - 2*y2 + y3) if (y1 - 2*y2 + y3) != 0 else 0.0
                            ip = ap + off
                        else:
                            ip = float(ap)
                        f_acf = float(self.sample_rate / ip) if ip > 0 else 0.0
                        if min_freq <= f_acf <= max_freq and pv > 0.0025 and f_acf < 3000:
                            candidates.append(("acf", f_acf, pv, None))
                            if self._detection_counter % 150 == 0:
                                self._log_rate_limit('acf_freq', f"🎵 ACF {f_acf:.2f}Hz pk={pv:.3f}", interval=1.5)
            except Exception as e:
                if self._detection_counter % 600 == 0:
                    self._log_rate_limit('acf_fail', f"⚠️ ACF失败: {e}", interval=10.0)

            # 方法2：FFT峰值候选 + 频谱缓存
            fft_freqs = None
            fft_magnitude = None
            try:
                fft_result = np.fft.rfft(x)
                fft_magnitude = np.abs(fft_result)
                fft_freqs = np.fft.rfftfreq(len(x), 1/self.sample_rate)
                voice_mask = (fft_freqs >= ui_min_f) & (fft_freqs <= ui_max_f)
                if np.any(voice_mask):
                    vm = fft_magnitude[voice_mask]
                    vf = fft_freqs[voice_mask]
                    if len(vm) > 0:
                        pidx = int(np.argmax(vm))
                        pf = float(vf[pidx])
                        pm = float(vm[pidx])
                        # 抛物线插值
                        if 0 < pidx < len(vm) - 1:
                            y1, y2, y3 = vm[pidx-1], vm[pidx], vm[pidx+1]
                            if (y1 - 2*y2 + y3) != 0:
                                xoff = 0.5 * (y1 - y3) / (y1 - 2*y2 + y3)
                                fres = (fft_freqs[1] - fft_freqs[0]) if len(fft_freqs) > 1 else 1.0
                                pf = pf + xoff * fres
                        mean_mag = float(np.mean(vm))
                        snr = pm / (mean_mag + 1e-10)
                        if snr > 1.05 and pm > 0.001 and pf < 3000:
                            candidates.append(("fft", pf, snr, {"fft": True}))
                            if self._detection_counter % 300 == 0 and getattr(self, 'debug_flags', {}).get('fft_log', False):
                                self._log_rate_limit('fft_freq', f"🎵 FFT {pf:.2f}Hz SNR={snr:.2f}", interval=2.0)
            except Exception as e:
                if self._detection_counter % 600 == 0:
                    self._log_rate_limit('fft_fail', f"⚠️ FFT失败: {e}", interval=10.0)

            # 方法3：精确零交叉候选
            try:
                zero_cross = np.where(np.diff(np.sign(x)))[0]
                if len(zero_cross) > 4:
                    pz = []
                    for i in zero_cross:
                        if i < len(x) - 1:
                            y1, y2 = x[i], x[i+1]
                            if y2 != y1:
                                pz.append(i - y1 / (y2 - y1))
                            else:
                                pz.append(float(i))
                    if len(pz) > 1:
                        per = np.diff(pz)
                        if len(per) > 0:
                            avgp = float(np.mean(per) * 2.0)
                            f_zc = float(self.sample_rate / avgp) if avgp > 0 else 0.0
                            if ui_min_f <= f_zc <= ui_max_f and f_zc > 0:
                                candidates.append(("zcr", f_zc, 0.5, None))
                                if self._detection_counter % 50 == 0:
                                    self._log_rate_limit('zc_freq', f"🎵 ZCR {f_zc:.2f}Hz", interval=2.0)
            except Exception as e:
                if self._detection_counter % 100 == 0:
                    self._log_rate_limit('zc_fail', f"⚠️ ZCR失败: {e}", interval=10.0)

            # 方法4：SHS子谐波候选（强修正低八度）
            try:
                if fft_freqs is None or fft_magnitude is None:
                    fft_freqs, fft_magnitude = self._get_fft_for_refine(x)
                if fft_freqs is not None and fft_magnitude is not None:
                    f_shs, s_shs = self._shs_candidate_from_fft(fft_freqs, fft_magnitude, float(ui_min_f), float(ui_max_f))
                    if f_shs > 0 and s_shs > 0:
                        candidates.append(("shs", f_shs, s_shs, {"fft": True}))
            except Exception:
                pass

            # 方法5：HPS谐波乘积候选（增强弱基频/假声）
            try:
                if fft_freqs is None or fft_magnitude is None:
                    fft_freqs, fft_magnitude = self._get_fft_for_refine(x)
                if fft_freqs is not None and fft_magnitude is not None:
                    f_hps, s_hps = self._hps_candidate_from_fft(fft_freqs, fft_magnitude, float(ui_min_f), float(ui_max_f), n_harm=4)
                    if f_hps > 0 and s_hps > 0:
                        candidates.append(("hps", f_hps, s_hps, {"fft": True}))
            except Exception:
                pass

            # 没有任何候选
            if not candidates:
                if self._detection_counter % 200 == 0:
                    print(f"❌ 未检测到音高: RMS={original_rms:.4f}, 数据长度={len(audio_data)}")
                return 0

            # 选择器：融合多源证据，倾向与历史一致且谱域有力的候选
            try:
                last_stable = float(getattr(self, '_last_stable_frequency', 0.0) or 0.0)
                # 归一化权重：SHS≈HPS > ACF > FFT > ZCR
                base_w = {"shs": 1.00, "hps": 0.96, "acf": 0.90, "fft": 0.80, "zcr": 0.40}
                # 找到分数范围便于归一
                raw_scores = np.array([max(1e-9, c[2]) for c in candidates], dtype=np.float64)
                s_min, s_max = float(np.min(raw_scores)), float(np.max(raw_scores))
                def _norm(v: float) -> float:
                    if s_max <= s_min:
                        return 0.5
                    return (v - s_min) / (s_max - s_min)

                best_freq = 0.0
                best_total = -1e9
                for name, f_cand, s_val, extra in candidates:
                    if not (ui_min_f <= f_cand <= ui_max_f):
                        continue
                    # 基础分 + 归一分
                    score = 0.6 * base_w.get(name, 0.5) + 0.4 * _norm(float(s_val))
                    # 谱域谐波支持再加分
                    if fft_freqs is not None and fft_magnitude is not None:
                        hs = self._harmonic_support(f_cand, fft_freqs, fft_magnitude)
                        score += 0.15 * (np.tanh(hs / (np.max(fft_magnitude) + 1e-9)))
                        # 对具有明显谐波结构的更高频候选给予额外偏好，缓解低八度粘连
                        # 若存在近似2倍频的更强谐波支持，则对较低候选施加惩罚
                        f2 = f_cand * 2.0
                        if ui_min_f <= f2 <= ui_max_f:
                            hs2 = self._harmonic_support(f2, fft_freqs, fft_magnitude)
                            if hs2 > hs * 1.25:
                                score -= 0.12
                    # 时间连续性（与上一稳定频率接近有利；允许八度就近）
                    if last_stable > 0:
                        semitone = abs(np.log2(max(f_cand,1e-6) / max(last_stable,1e-6))) * 12.0
                        octave_prox = abs(np.log2(max(f_cand*2,1e-6) / max(last_stable,1e-6))) * 12.0
                        temporal = max(0.0, 1.0 - (min(semitone, octave_prox) / 3.0))
                        score += 0.20 * temporal
                    # 低八度惩罚：当存在明显更高的SHS候选时（如4f更合理），对过低频率施加轻惩罚
                    for n2, f2cand, s2, _ in candidates:
                        if n2 == "shs" and f2cand > f_cand * 1.9 and f2cand < f_cand * 4.2:
                            score -= 0.10
                            break
                    if score > best_total:
                        best_total = score
                        best_freq = f_cand

                if best_freq <= 0:
                    # 后备：取分最高的候选
                    best_freq = max(candidates, key=lambda t: t[2])[1]

                # 最终谐波/YIN精修 + 范围裁剪
                return self._finalize_frequency(best_freq, audio_data, (fft_freqs, fft_magnitude) if (fft_freqs is not None and fft_magnitude is not None) else None, rms=original_rms)
            except Exception:
                # 后备路径：取shs>acf>fft>zcr的优先级
                order = {"shs": 4, "acf": 3, "fft": 2, "zcr": 1}
                candidates.sort(key=lambda t: (order.get(t[0], 0), t[2]))
                best = candidates[-1]
                return self._finalize_frequency(best[1], audio_data, rms=original_rms)
            
        except Exception as e:
            if self._detection_counter % 100 == 0:
                print(f"❌ 音高检测总体错误: {e}")
            return 0

    # ========= 监听耳返专用：呼吸期轻微电流/滋啦抑制（零感知延迟） ========= #
    def _apply_breath_noise_suppress(self, audio_data: np.ndarray, key: str = 'default') -> np.ndarray:
        """在低音量呼吸段，温和抑制高频滋啦与电流音。
        - 仅作用于监听耳返，不影响分析队列（保持 raw_audio 原样入队）
        - 条件触发：RMS 很低且高频差分比偏高
        - 算法：一阶低通(IIR) + 高频残差动态抑制 + 轻混合平滑 +（可选）软门控 + 边界短交叉淡入
        """
        try:
            if audio_data is None or len(audio_data) == 0:
                return audio_data
            x = audio_data.astype(np.float32, copy=False)
            rms = float(np.sqrt(np.mean(x * x)))
            # 自然模式参数（更轻的处理，尽量保留呼吸质感）
            natural = bool(getattr(self, 'monitor_natural_mode', True))
            thr_low = 0.012 if not natural else 0.010
            # 设备环境自校准：在非常安静且非有声的段落，估计底噪RMS，微调阈值
            try:
                if not hasattr(self, '_env_noise_floor'):
                    self._env_noise_floor = {}
                env = float(self._env_noise_floor.get(key, 0.0))
                # 极低电平才更新，避免在有声时受到影响
                if rms < thr_low * 0.6:
                    # 慢速一阶平均做地板估计
                    env = 0.995 * env + 0.005 * rms
                    self._env_noise_floor[key] = env
                # 根据地板调节阈值：噪声地板越高，阈值略升，减少误触；反之略降，增强敏感度
                if env > 0.0:
                    # 自然模式调幅更小，保持气声
                    adj = 0.25 if not natural else 0.15
                    thr_low *= (1.0 + adj * min(1.0, env / max(1e-6, thr_low)))
            except Exception:
                pass
            if rms >= thr_low:
                return audio_data

            # 高频差分比例（检测滋啦）
            if len(x) > 4:
                hfdiff = float(np.sum(np.abs(np.diff(x, 2))))
                energy = float(np.sum(np.abs(x))) + 1e-9
                hf_ratio = hfdiff / energy
            else:
                hf_ratio = 0.0

            # 零交叉率（ZCR），帮助识别呼吸/噪声类无周期成分
            if len(x) > 1:
                zc = float(np.mean((x[:-1] * x[1:]) < 0))
            else:
                zc = 0.0

            # 触发条件：低RMS 且 (hf_ratio 或 ZCR 达到一定水平)，否则直接原样返回
            if not getattr(self, '_breath_gate_state', None):
                self._breath_gate_state = {}
            gate = self._breath_gate_state.get(key, False)
            # 更保守的高频触发阈值，减少对真实呼吸与轻声的误触
            hf_trigger = hf_ratio > (6.5 if natural else 5.8)
            zc_trigger = zc > (0.10 if natural else 0.08)
            if not (hf_trigger or zc_trigger):
                self._breath_gate_state[key] = False
                return audio_data
            else:
                self._breath_gate_state[key] = True

            # 将 hf_ratio 映射为 [0,1] 抑制强度 s
            if natural:
                hf_start, hf_end = 7.0, 13.5
            else:
                hf_start, hf_end = 5.5, 11.5
            s = 0.0
            if hf_end > hf_start:
                s = (hf_ratio - hf_start) / (hf_end - hf_start)
                s = 0.0 if s < 0.0 else (1.0 if s > 1.0 else s)

            # 用户强度映射（0.0~1.0），影响 s 与压缩强度
            user_strength = float(getattr(self, 'natural_earback_strength', 0.6))
            user_strength = 0.0 if user_strength < 0.0 else (1.0 if user_strength > 1.0 else user_strength)
            s *= (0.45 + 0.45 * user_strength)  # 更轻的强度映射，保留更多原味
            # 简单迟滞：跨回调平滑 s，避免忽隐忽现
            if not hasattr(self, '_breath_prev_s'):
                self._breath_prev_s = {}
            s_prev = self._breath_prev_s.get(key, s)
            s = 0.7 * s_prev + 0.3 * s
            self._breath_prev_s[key] = float(s)

            # 低音量时稍增强抑制强度（只在呼吸/极弱段生效）
            thr_mid = thr_low * (1.8 if natural else 2.0)
            if rms < thr_mid:
                w = (thr_mid - rms) / max(1e-9, (thr_mid - thr_low))
                w = 0.0 if w < 0.0 else (1.0 if w > 1.0 else w)
                s = min(1.0, s + 0.35 * w)

            # 根据 ZCR 提升无周期“沙沙”的抑制
            zcr_start, zcr_end = (0.08, 0.22) if natural else (0.06, 0.20)
            if zcr_end > zcr_start:
                s_z = (zc - zcr_start) / (zcr_end - zcr_start)
                s_z = 0.0 if s_z < 0.0 else (1.0 if s_z > 1.0 else s_z)
                s = min(1.0, s + 0.25 * s_z)

            # IIR 低通，跨回调保持状态，减少边界伪影
            if not hasattr(self, '_breath_lp_state'):
                self._breath_lp_state = {}
            prev = self._breath_lp_state.get(key, 0.0)
            # alpha 随 s 动态变化：高频越多，低通稍强
            if natural:
                alpha_base, alpha_max = 0.08, 0.18
            else:
                alpha_base, alpha_max = 0.13, 0.26
            alpha = alpha_base + (alpha_max - alpha_base) * s
            y_lp = np.empty_like(x)
            for i in range(len(x)):
                prev = prev + alpha * (x[i] - prev)
                y_lp[i] = prev
            self._breath_lp_state[key] = float(prev)

            # === 额外中频低通（~2kHz），用于分离中频与更高频的残差 ===
            try:
                if not hasattr(self, '_breath_lp2_state'):
                    self._breath_lp2_state = {}
                prev2 = float(self._breath_lp2_state.get(key, 0.0))
                sr = float(getattr(self, 'sample_rate', 48000.0))
                fc = 2000.0  # 约2kHz分界
                # 指数平滑等效一阶RC：alpha = 1 - exp(-2πfc/fs)
                alpha_mid = 1.0 - np.exp(-2.0 * np.pi * fc / max(1000.0, sr))
                alpha_mid = 0.0 if alpha_mid < 0.0 else (0.99 if alpha_mid > 0.99 else float(alpha_mid))
                y_lp2 = np.empty_like(x)
                for i in range(len(x)):
                    prev2 = prev2 + alpha_mid * (x[i] - prev2)
                    y_lp2[i] = prev2
                self._breath_lp2_state[key] = float(prev2)
            except Exception:
                # 失败则回退：使用现有低通作为近似
                y_lp2 = y_lp

            # === 新增：更高分界低通（~6kHz），用于进一步分离超高频（>6k）以更精确地门限抑制底噪 ===
            try:
                if not hasattr(self, '_breath_lp3_state'):
                    self._breath_lp3_state = {}
                prev3 = float(self._breath_lp3_state.get(key, 0.0))
                sr = float(getattr(self, 'sample_rate', 48000.0))
                fc3 = 6000.0
                alpha_high = 1.0 - np.exp(-2.0 * np.pi * fc3 / max(1000.0, sr))
                alpha_high = 0.0 if alpha_high < 0.0 else (0.995 if alpha_high > 0.995 else float(alpha_high))
                y_lp3 = np.empty_like(x)
                for i in range(len(x)):
                    prev3 = prev3 + alpha_high * (x[i] - prev3)
                    y_lp3[i] = prev3
                self._breath_lp3_state[key] = float(prev3)
            except Exception:
                y_lp3 = y_lp2

            # === 新增：8kHz低通（~8kHz），便于分离6–8k子带用于“远距小声”专治“滋啦” ===
            try:
                if not hasattr(self, '_breath_lp4_state'):
                    self._breath_lp4_state = {}
                prev4 = float(self._breath_lp4_state.get(key, 0.0))
                sr = float(getattr(self, 'sample_rate', 48000.0))
                fc4 = 8000.0
                alpha_8k = 1.0 - np.exp(-2.0 * np.pi * fc4 / max(1000.0, sr))
                alpha_8k = float(np.clip(alpha_8k, 0.0, 0.996))
                y_lp4 = np.empty_like(x)
                for i in range(len(x)):
                    prev4 = prev4 + alpha_8k * (x[i] - prev4)
                    y_lp4[i] = prev4
                self._breath_lp4_state[key] = float(prev4)
            except Exception:
                y_lp4 = y_lp3

            # 🎯 识别“很小声的嗡嗡声”（低频调制为主，谱心低且谱平坦度低）
            tonal_hum = False
            try:
                sr = float(getattr(self, 'sample_rate', 48000))
                if len(x) >= 64:
                    spec = np.fft.rfft(x)
                    mag = np.abs(spec) + 1e-12
                    freqs = np.fft.rfftfreq(len(x), 1.0/sr)
                    centroid = float(np.sum(freqs * mag) / np.sum(mag)) if np.sum(mag) > 0 else 0.0
                    # 谱平坦度（tonal 越低越“尖锐”）
                    flatness = float(np.exp(np.mean(np.log(mag))) / (np.mean(mag) + 1e-12))
                    # 条件：很低电平 + 低ZCR（更接近正弦）+ 谱心较低 + 平坦度较低（有明显峰）
                    tonal_hum = (rms < thr_mid) and (zc <= (0.08 if natural else 0.07)) 
                    tonal_hum = tonal_hum and (centroid < (800.0 if natural else 700.0)) and (flatness < 0.60)
                    # 中高频能量比，用于识别“轻声有声”（中频相对高于高频，保留清晰度）
                    try:
                        mid_mask = (freqs >= 300.0) & (freqs <= 3000.0)
                        high_mask = (freqs > 3000.0)
                        mid_energy = float(np.mean(mag[mid_mask])) if np.any(mid_mask) else 0.0
                        high_energy = float(np.mean(mag[high_mask])) if np.any(high_mask) else 1e-12
                        mid_high_ratio = (mid_energy + 1e-9) / (high_energy + 1e-9)
                        # 供“头声/高音亮度”判断使用的低/中/高能量比
                        midp_mask = (freqs >= 300.0) & (freqs <= 1200.0)
                        high6_mask_l = (freqs >= 6000.0)
                        midp_e2 = float(np.mean(mag[midp_mask])) if np.any(midp_mask) else 1e-12
                        high6_e2 = float(np.mean(mag[high6_mask_l])) if np.any(high6_mask_l) else 1e-12
                        hf_to_mid_est = (high6_e2 + 1e-9) / (midp_e2 + 1e-9)
                    except Exception:
                        mid_high_ratio = 1.0
                        hf_to_mid_est = 0.0
                else:
                    mid_high_ratio = 1.0
                    hf_to_mid_est = 0.0
            except Exception:
                tonal_hum = False
                mid_high_ratio = 1.0
                hf_to_mid_est = 0.0

            # 轻声有声：低电平 + 中频相对占优 + ZCR较低（更接近有声音色），且不属于嗡嗡
            voiced_soft = (rms < thr_mid) and (mid_high_ratio > 2.0) and (zc <= 0.12) and (not tonal_hum)

            # 🎤 头声/高音亮度保护：高音（谱心较高）+ 高频相对中频不低 + 不像噪声
            voiced_bright = False
            try:
                voiced_bright = (rms > thr_low * 0.9) and (zc <= 0.14) and (flatness < 0.75) and (centroid > 2000.0) and (hf_to_mid_est > 0.60)
            except Exception:
                voiced_bright = False

            # 📏 动态“距离因子”估计（0=近，1=远）：基于低/中/高频能量比 + ZCR + 音量
            distance_factor = 0.0
            try:
                # 若已有频谱 mag/freqs，则复用；否则回退为0
                if 'mag' in locals() and 'freqs' in locals() and len(mag) == len(freqs):
                    low_mask = (freqs >= 80.0) & (freqs <= 250.0)
                    midp_mask = (freqs >= 300.0) & (freqs <= 1200.0)
                    high6_mask = (freqs >= 6000.0)
                    low_e = float(np.mean(mag[low_mask])) if np.any(low_mask) else 0.0
                    midp_e = float(np.mean(mag[midp_mask])) if np.any(midp_mask) else 1e-12
                    high6_e = float(np.mean(mag[high6_mask])) if np.any(high6_mask) else 1e-12
                    low_to_mid = (low_e + 1e-9) / (midp_e + 1e-9)
                    hf_to_mid = (high6_e + 1e-9) / (midp_e + 1e-9)
                    # 特征映射：近讲低频相对高、远距高频相对高
                    t1 = np.clip((0.7 - low_to_mid) / 0.5, 0.0, 1.0)    # 低于0.7越多越远
                    t2 = np.clip((hf_to_mid - 0.8) / 0.8, 0.0, 1.0)     # 高于0.8越多越远
                    t3 = np.clip((zc - 0.10) / 0.15, 0.0, 1.0)          # ZCR升高→更像远距/噪声
                    t4 = np.clip((thr_mid - rms) / max(1e-9, (thr_mid - thr_low)), 0.0, 1.0)  # 越小声越远
                    df_raw = 0.38 * t1 + 0.34 * t2 + 0.18 * t3 + 0.10 * t4
                    # 平滑到状态
                    if not hasattr(self, '_distance_factor_state'):
                        self._distance_factor_state = {}
                    prev_df = float(self._distance_factor_state.get(key, 0.0))
                    distance_factor = float(0.80 * prev_df + 0.20 * df_raw)
                    self._distance_factor_state[key] = distance_factor
                else:
                    distance_factor = float(self._distance_factor_state.get(key, 0.0)) if hasattr(self, '_distance_factor_state') else 0.0
            except Exception:
                distance_factor = 0.0

            # 远距小声：低电平 + ZCR中等 + 中频优势不明显（近场弱），容易出现“微弱滋啦”
            try:
                far_quiet = (rms < thr_mid) and (0.10 <= zc <= 0.22) and (mid_high_ratio < 1.6) and (not tonal_hum)
            except Exception:
                far_quiet = (rms < thr_mid) and (0.10 <= zc <= 0.22) and (not tonal_hum)
            # 远距“像有人声”的提示：很小声但zcr不高且中频不弱，避免误判为噪声
            try:
                far_voiced_hint = (rms < thr_mid) and (zc <= 0.14) and (mid_high_ratio > 1.3) and (not tonal_hum)
            except Exception:
                far_voiced_hint = False

            # 频带分离：
            # - mid_band: ~2kHz附近的带（帮助保持清晰度）
            # - hf_mid: ~2k-6k 之间的能量（影响“清晰/齿音”）
            # - hf_high: >6k 的超高频（更可能是底噪“电流音”）
            mid_band = y_lp2 - y_lp
            hf_mid = y_lp3 - y_lp2
            hf_high = x - y_lp3
            # 向后兼容：保留原 hf_res（>~2kHz 的整体）以复用既有包络/门限逻辑
            hf_res = x - y_lp2
            # 呼吸检测：低电平 + 高ZCR（更像气声）+ 2-6k 相对占优，且非嗡嗡/非轻声有声
            try:
                e_hm = float(np.mean(np.abs(hf_mid))) + 1e-9
                e_hh = float(np.mean(np.abs(hf_high))) + 1e-9
                hm_over_hh = e_hm / e_hh
            except Exception:
                hm_over_hh = 1.0
            breath_detect = (rms < thr_mid) and (zc >= (0.14 if natural else 0.12))
            breath_detect = breath_detect and (hm_over_hh > 1.20) and (not tonal_hum) and (not voiced_soft)
            # 基于 s 设定静态高频保留系数 g_base（越大越保留）
            if tonal_hum:
                # 嗡嗡声场景：更强的高频抑制，减少砂感
                if natural:
                    k_min, k_max = 0.22, 0.52
                else:
                    k_min, k_max = 0.20, 0.50
            else:
                if natural:
                    k_min, k_max = 0.08, 0.32
                else:
                    k_min, k_max = 0.16, 0.48
            k = k_min + (k_max - k_min) * s
            g_base = 1.0 - k
            # 轻声有声时，进一步降低抑制力度、避免“模糊”
            if voiced_soft:
                g_base = min(1.0, g_base * 1.06)
                s *= 0.88

            # 轻声有声保护：若低频包络高于高频包络，提升 g_base（少削高频）并给低频极轻增益
            env_l = float(np.mean(np.abs(y_lp))) + 1e-9
            env_h = float(np.mean(np.abs(hf_res))) + 1e-9
            low_boost = 0.0
            if env_l > env_h * 1.25:
                g_base = min(1.0, g_base + 0.10)
                s *= 0.9
                low_boost = (0.04 if natural else 0.05) if tonal_hum else (0.02 if natural else 0.03)
            # 轻声有声：略增低频温暖，帮助清晰度
            if voiced_soft:
                low_boost += 0.01

            # 软膝压缩：当高频包络占比过高时进一步降低高频（防“砂感”）
            base_amp = float(np.mean(np.abs(x))) + 1e-9
            env_h_ratio = env_h / base_amp
            t_ratio = 0.88 if natural else 0.78
            if env_h_ratio <= t_ratio:
                g_comp = 1.0
            else:
                over = (env_h_ratio - t_ratio) / max(1e-6, (1.0 - t_ratio))
                # 嗡嗡声时对>2kHz更强的抑制，整体降砂但不压中频
                c_base = (0.36 if natural else 0.46)
                c = c_base + (0.55 * s) * (0.6 + 0.4 * user_strength)
                g_comp = 1.0 - c * over
                g_comp = 0.30 if g_comp < 0.30 else (1.0 if g_comp > 1.0 else g_comp)

            g = g_base * g_comp
            # 呼吸保护：对2-6k带宽（hf_mid）保留更多细节，避免“抽空空气感”
            g_mid = g
            if breath_detect:
                g_mid = min(1.0, g * (1.06 if natural else 1.08))

            # 高频残差包络（跨回调保持），抑制极低电平的高频底噪（软膝，避免“砂”）
            if not hasattr(self, '_breath_hf_env'):
                self._breath_hf_env = {}
            hf_env_prev = self._breath_hf_env.get(key, 0.0)
            hf_env = float(0.6 * hf_env_prev + 0.4 * np.mean(np.abs(hf_res)))
            self._breath_hf_env[key] = hf_env
            # 阈值随 RMS 自适应：音量越小，阈值越低，但不为0
            env_thr = max(1e-6, 0.6 * thr_low + 0.4 * rms)
            if hf_env < env_thr * 0.9:
                ratio = hf_env / (env_thr * 0.9 + 1e-9)
                # 二次软膝，轻柔抑制底噪；嗡嗡声场景更加强一些
                knee_pow = (1.8 if tonal_hum else (1.5 if natural else 1.2))
                knee = 1.0 - (1.0 - ratio) ** knee_pow
                g *= knee

            # ➕ 持续“电流音”治理：高频噪声地板自适应（仅作用于高频残差增益 g）
            try:
                if not hasattr(self, '_breath_hf_floor'):
                    self._breath_hf_floor = {}
                floor = float(self._breath_hf_floor.get(key, hf_env))
                # 在“更像噪声”的场景更新地板更快：低电平 + ZCR较高 或 频谱平坦度高
                flatness_val = 0.0
                try:
                    flatness_val = float(flatness)  # 若上方已计算
                except Exception:
                    flatness_val = 0.0
                if rms < (thr_low * 1.2) and (zc > 0.12 or flatness_val > 0.75):
                    floor = 0.98 * floor + 0.02 * hf_env  # 稍快更新
                else:
                    floor = 0.995 * floor + 0.005 * hf_env  # 极慢漂移
                self._breath_hf_floor[key] = floor

                # 根据地板与当前HF包络的比值决定附加抑制；确保留一点“空气”
                if floor > 1e-9:
                    ratio_h = hf_env / (1.25 * floor)
                    ratio_h = 0.0 if ratio_h < 0.0 else (2.0 if ratio_h > 2.0 else ratio_h)
                    # ratio_h < 1 表示接近地板（更像“电流音”），附加降低高频增益
                    # 映射：ratio_h∈[0,1] → hiss_gate∈[gate_min,1]
                    gate_min = 0.57 if natural else 0.50
                    # 若是嗡嗡声，为避免“闷”，提高最小门限
                    if tonal_hum:
                        gate_min = max(gate_min, 0.66)
                    hiss_gate = gate_min + (1.0 - gate_min) * min(1.0, ratio_h)
                    g *= hiss_gate
            except Exception:
                pass

            # ➕ 新增：超高频(>6k)专属自适应门控，进一步减少“细微电流底噪”但保留2-6k清晰度
            try:
                if not hasattr(self, '_breath_vh_env'):
                    self._breath_vh_env = {}
                if not hasattr(self, '_breath_vh_floor'):
                    self._breath_vh_floor = {}
                vh_env_prev = float(self._breath_vh_env.get(key, 0.0))
                vh_env = float(0.5 * vh_env_prev + 0.5 * np.mean(np.abs(hf_high)))
                self._breath_vh_env[key] = vh_env
                vh_floor = float(self._breath_vh_floor.get(key, vh_env))
                # 更快速的上升跟踪、更慢的下降，噪声地板平稳
                if vh_env > vh_floor:
                    vh_floor = 0.98 * vh_floor + 0.02 * vh_env
                else:
                    vh_floor = 0.997 * vh_floor + 0.003 * vh_env
                self._breath_vh_floor[key] = vh_floor

                # 计算>6k门控因子 g_vh（与 g 相乘用于超高频）
                if vh_floor > 1e-9:
                    r = vh_env / (1.20 * vh_floor)
                    r = 0.0 if r < 0.0 else (2.0 if r > 2.0 else r)
                    # 基础最小保留量，避免“抽空空气感”
                    base_keep = 0.40 if natural else 0.35
                    # 嗡嗡声：可更强抑制；轻声有声：更保留清晰度
                    if tonal_hum:
                        base_keep = max(base_keep, 0.48)
                    if voiced_soft:
                        base_keep = min(0.55, base_keep + 0.08)
                    # 头声/高音：进一步提高保留，增强通透感
                    if 'voiced_bright' in locals() and voiced_bright:
                        base_keep = max(base_keep, 0.58 if natural else 0.55)
                    g_vh = base_keep + (1.0 - base_keep) * min(1.0, r)
                else:
                    g_vh = 0.6 if natural else 0.5
            except Exception:
                g_vh = 0.6 if natural else 0.5

            # ➕ 新增：>6kHz 频谱地板掩蔽（极轻）——在低电平且更像噪声时，按频带自适应降低“滋啦”
            try:
                hiss_like = (rms < thr_mid) and (zc > 0.12 or ("flatness" in locals() and flatness > 0.75))
                if hiss_like and len(hf_high) >= 64:
                    sr = float(getattr(self, 'sample_rate', 48000))
                    spec = np.fft.rfft(hf_high)
                    mag = np.abs(spec) + 1e-12
                    freqs = np.fft.rfftfreq(len(hf_high), 1.0/sr)
                    # 仅对>6k频段做地板掩蔽
                    band = (freqs >= 6000.0)
                    if not hasattr(self, '_breath_vh_floor_spec'):
                        self._breath_vh_floor_spec = {}
                    st = self._breath_vh_floor_spec.get(key)
                    if st is None or (hasattr(st, 'shape') and getattr(st, 'shape', (0,))[0] != mag.shape[0]):
                        st = mag.copy()
                    # 更新（上升稍快、下降慢），仅限>6k
                    floor = st
                    alpha_up, alpha_down = 0.06, 0.006
                    higher = mag > floor
                    floor[higher] = (1.0 - alpha_up) * floor[higher] + alpha_up * mag[higher]
                    floor[~higher] = (1.0 - alpha_down) * floor[~higher] + alpha_down * mag[~higher]
                    # 计算掩蔽增益
                    base_keep_hi = 0.40 if natural else 0.35
                    if tonal_hum:
                        base_keep_hi = max(base_keep_hi, 0.50)
                    if voiced_soft:
                        base_keep_hi = min(0.58, base_keep_hi + 0.08)
                    if 'breath_detect' in locals() and breath_detect:
                        base_keep_hi = min(0.62, base_keep_hi + 0.10)
                    if 'far_quiet' in locals() and far_quiet:
                        base_keep_hi = max(0.28 if natural else 0.25, base_keep_hi - 0.08)
                    # 距离因子：越远越降低>6k保留（更干净）
                    base_keep_hi = max(0.22 if natural else 0.20, base_keep_hi - 0.10 * distance_factor)
                    # 远距像有人声：适度抬高保留，避免“被当噪声”导致丝丝感
                    try:
                        if far_voiced_hint:
                            base_keep_hi = min(0.70, base_keep_hi + 0.04)
                    except Exception:
                        pass
                    # 头声/高音：提高>6k保留下限，避免“通透感”丢失
                    if 'voiced_bright' in locals() and voiced_bright:
                        base_keep_hi = max(base_keep_hi, 0.60 if natural else 0.56)
                    # 掩蔽比例阈值：远距非高音→更严；高音→更宽松
                    ratio_div = 1.30
                    if 'voiced_bright' in locals() and voiced_bright:
                        ratio_div = 1.45
                    else:
                        try:
                            if far_voiced_hint:
                                ratio_div = 1.32  # 放宽阈值，避免过压
                            else:
                                if distance_factor > 0.8:
                                    ratio_div = 1.18
                                elif distance_factor > 0.5:
                                    ratio_div = 1.22
                        except Exception:
                            pass
                    ratio = np.ones_like(mag)
                    ratio[band] = mag[band] / (ratio_div * floor[band])
                    ratio = np.clip(ratio, 0.0, 2.0)
                    mask = np.ones_like(mag)
                    mask[band] = base_keep_hi + (1.0 - base_keep_hi) * np.minimum(1.0, ratio[band])
                    # 远距超静音且非高音：对>10k再轻收一点，专治极细“丝丝”
                    if ('far_quiet' in locals() and far_quiet) and (distance_factor > 0.7) and (not ('voiced_bright' in locals() and voiced_bright)):
                        band10 = (freqs >= 10000.0)
                        if np.any(band10):
                            extra = np.clip(0.92 - 0.12 * float(distance_factor), 0.78, 0.92)
                            try:
                                if far_voiced_hint:
                                    extra = max(0.90, extra)
                            except Exception:
                                pass
                            mask[band10] *= extra
                    # 平滑，避免频带抖动
                    if not hasattr(self, '_breath_vh_mask_prev'):
                        self._breath_vh_mask_prev = {}
                    prev_m = self._breath_vh_mask_prev.get(key)
                    if prev_m is None or prev_m.shape[0] != mask.shape[0]:
                        prev_m = mask
                    smooth_k = 0.7
                    try:
                        if far_quiet and far_voiced_hint:
                            smooth_k = 0.85  # 更慢释放，减少抖动“丝丝”
                    except Exception:
                        pass
                    mask_s = smooth_k * prev_m + (1.0 - smooth_k) * mask
                    self._breath_vh_mask_prev[key] = mask_s
                    # 应用掩蔽
                    spec_f = spec * mask_s
                    hf_high = np.fft.irfft(spec_f, n=len(hf_high)).astype(hf_high.dtype, copy=False)
                    self._breath_vh_floor_spec[key] = floor
            except Exception:
                pass

            # ➕ 新增：自适应窄带陷波（notch）- 仅在低电平噪声场景，对>6kHz稳定尖峰做极窄抑制
            try:
                use_notch = False
                f0_est = None
                # 仅在低电平且更像噪声的场景考虑陷波，避免对有声音色的破坏
                hiss_like = (rms < thr_mid) and (zc > 0.12 or ("flatness" in locals() and flatness > 0.75))
                if hiss_like and len(hf_high) >= 128:
                    # 对hf_high做FFT，寻找>6k的稳定尖峰
                    sr = float(getattr(self, 'sample_rate', 48000))
                    spec_h = np.fft.rfft(hf_high)
                    mag_h = np.abs(spec_h) + 1e-12
                    freqs_h = np.fft.rfftfreq(len(hf_high), 1.0/sr)
                    # 6k-12k搜索窗（上限不超过Nyquist-1k）
                    fmax = min(12000.0, 0.5*sr - 1000.0)
                    band = (freqs_h >= 6000.0) & (freqs_h <= fmax)
                    if np.any(band):
                        band_mag = mag_h[band]
                        if band_mag.size > 8:
                            peak_idx_local = int(np.argmax(band_mag))
                            peak_mag = float(band_mag[peak_idx_local])
                            median_mag = float(np.median(band_mag)) + 1e-12
                            mean_mag = float(np.mean(band_mag)) + 1e-12
                            # 极窄“哨声”判定：峰值明显高于整体与中位
                            whistle_like = (peak_mag / median_mag > 5.0) and (peak_mag / mean_mag > 4.0)
                            # 尖峰判定：明显高于中值且高于均值，避免误杀随机起伏
                            if peak_mag > 2.8 * median_mag and peak_mag > 1.6 * mean_mag:
                                freqs_band = freqs_h[band]
                                f0_candidate = float(freqs_band[peak_idx_local])
                                # 稳定度跟踪：需要连续数帧附近一致
                                if not hasattr(self, '_breath_notch'):
                                    self._breath_notch = {}
                                st_notch = self._breath_notch.get(key, {
                                    'f': f0_candidate,
                                    'q': 18.0,
                                    'z1': 0.0,
                                    'z2': 0.0,
                                    'stability': 0
                                })
                                # 频率接近则累计稳定度，否则缓慢回落
                                if abs(f0_candidate - st_notch['f']) <= max(60.0, 0.02*st_notch['f']):
                                    st_notch['f'] = 0.9 * st_notch['f'] + 0.1 * f0_candidate
                                    st_notch['stability'] = min(10, st_notch['stability'] + 1)
                                else:
                                    st_notch['f'] = 0.8 * st_notch['f'] + 0.2 * f0_candidate
                                    st_notch['stability'] = max(0, st_notch['stability'] - 2)
                                # 当稳定度足够时启用陷波
                                if st_notch['stability'] >= 3:
                                    use_notch = True
                                    f0_est = float(st_notch['f'])
                                self._breath_notch[key] = st_notch

                hf_high_f = hf_high
                if use_notch and f0_est is not None and 2000.0 < f0_est < 0.5*sr - 500.0:
                    # 计算二阶陷波系数（双二阶会更陡，这里先用单节，Q适中以避免振铃）
                    Q = float(self._breath_notch[key]['q']) if hasattr(self, '_breath_notch') and key in self._breath_notch else 18.0
                    w0 = 2.0 * np.pi * (f0_est / sr)
                    alpha = np.sin(w0) / max(1e-6, (2.0 * Q))
                    cosw = np.cos(w0)
                    b0 = 1.0
                    b1 = -2.0 * cosw
                    b2 = 1.0
                    a0 = 1.0 + alpha
                    a1 = -2.0 * cosw
                    a2 = 1.0 - alpha
                    # 归一化
                    b0n = b0 / a0
                    b1n = b1 / a0
                    b2n = b2 / a0
                    a1n = a1 / a0
                    a2n = a2 / a0
                    # 读取/初始化状态
                    stn = self._breath_notch.get(key, None)
                    if stn is None:
                        stn = {'f': f0_est, 'q': Q, 'z1': 0.0, 'z2': 0.0, 'stability': 3}
                    z1 = float(stn.get('z1', 0.0))
                    z2 = float(stn.get('z2', 0.0))
                    out_h = np.empty_like(hf_high_f)
                    # IIR 直达形式II
                    for i in range(len(hf_high_f)):
                        x0 = float(hf_high_f[i])
                        y0 = b0n * x0 + z1
                        z1_new = b1n * x0 - a1n * y0 + z2
                        z2 = b2n * x0 - a2n * y0
                        z1 = z1_new
                        out_h[i] = y0
                    # 存回状态
                    stn['z1'] = float(z1)
                    stn['z2'] = float(z2)
                    self._breath_notch[key] = stn
                    # 与原信号做温和混合，避免过度抽空
                    notch_strength = min(0.75, 0.50 + 0.10 * (self._breath_notch[key].get('stability', 3)))  # 0.5~0.75
                    if voiced_soft:
                        notch_strength *= 0.75  # 轻声有声更保守
                    if breath_detect:
                        notch_strength *= 0.60  # 呼吸段进一步减弱陷波强度，保留空气感
                    if 'far_quiet' in locals() and far_quiet:
                        notch_strength = min(0.92, notch_strength * 1.18)  # 远距小声更积极去除稳定窄峰
                    # 距离因子：越远，陷波可再加强（上限控制）
                    if distance_factor > 0.0:
                        notch_strength = min(0.92, notch_strength * (1.0 + 0.25 * distance_factor))
                    # 头声/高音：降低陷波强度，避免“炸麦/刺耳”与通透受损
                    if 'voiced_bright' in locals() and voiced_bright:
                        try:
                            if 'whistle_like' in locals() and whistle_like:
                                notch_strength *= 0.90
                            else:
                                notch_strength *= 0.70
                        except Exception:
                            notch_strength *= 0.75
                    # 远距像有人声：进一步降低陷波，避免细丝伪像
                    try:
                        if far_voiced_hint:
                            notch_strength *= 0.85
                    except Exception:
                        pass
                    hf_high = out_h * notch_strength + hf_high_f * (1.0 - notch_strength)

                    # 头声抗“炸”：>6k对峰值做极轻软膝压制，仅在高音亮度明显时启用
                    try:
                        if 'voiced_bright' in locals() and voiced_bright and len(hf_high) >= 16:
                            ah = np.abs(hf_high)
                            # 95分位作“峰值感”参考，更鲁棒
                            pk = float(np.percentile(ah, 95)) + 1e-12
                            if pk > 1e-6:
                                knee = 0.60 * pk
                                # 2:1软膝，光滑压制
                                over = ah - knee
                                over[over < 0] = 0.0
                                comp = knee + 0.5 * over
                                g = np.where(ah > 0, comp / (ah + 1e-12), 1.0)
                                # 仅少量混合，避免暗
                                mix = 0.25
                                hf_high = (1.0 - mix) * hf_high + mix * (np.sign(hf_high) * comp)
                    except Exception:
                        pass
            except Exception:
                pass

            # 组合：低频（略增益）+ 中频（基本保留）+ 抑制后的高频
            if tonal_hum:
                mid_gain = 1.02 if natural else 1.01
            elif voiced_soft:
                mid_gain = 1.04 if natural else 1.03
            else:
                mid_gain = 1.00
            # 远距小声专治：对6–8k子带做更强抑制，同时提升2–4.5k存在感
            try:
                # 使用x构造6–8k与>8k比例，然后在陷波/门控后的hf_high上按比例切分
                high_6_8_x = (y_lp4 - y_lp3)
                hf_high_x = (x - y_lp3)
                e_h68 = float(np.mean(np.abs(high_6_8_x))) + 1e-12
                e_hh = float(np.mean(np.abs(hf_high_x))) + 1e-12
                ratio_h68 = max(0.0, min(1.0, e_h68 / e_hh))
                high_6_8_post = hf_high * ratio_h68
                high_8p_post = hf_high - high_6_8_post

                # 6–8k地板门控（仅在远距小声时更严格）
                if not hasattr(self, '_breath_68_env'): self._breath_68_env = {}
                if not hasattr(self, '_breath_68_floor'): self._breath_68_floor = {}
                env68_prev = float(self._breath_68_env.get(key, 0.0))
                env68 = float(0.6 * env68_prev + 0.4 * e_h68)
                self._breath_68_env[key] = env68
                floor68 = float(self._breath_68_floor.get(key, env68))
                if env68 > floor68:
                    floor68 = 0.985 * floor68 + 0.015 * env68
                else:
                    floor68 = 0.997 * floor68 + 0.003 * env68
                self._breath_68_floor[key] = floor68

                g_68 = 1.0
                if floor68 > 0.0:
                    r68 = env68 / (1.18 * floor68)
                    r68 = 0.0 if r68 < 0.0 else (2.0 if r68 > 2.0 else r68)
                    base_keep_68 = 0.50 if natural else 0.45
                    if voiced_soft:
                        base_keep_68 = min(0.60, base_keep_68 + 0.08)
                    if far_quiet:
                        base_keep_68 = max(0.30, base_keep_68 - 0.12)  # 远距小声更强去“滋啦”
                    # 头声/高音：保留更多6–8k，以提升清亮度；同时减弱远距影响系数
                    if 'voiced_bright' in locals() and voiced_bright:
                        base_keep_68 = max(base_keep_68, 0.50)
                        base_keep_68 = max(0.24, base_keep_68 - 0.15 * distance_factor * 0.5)
                    else:
                        # 距离因子：越远越再降一点6–8k保留
                        df_scale = 0.15 * (0.5 if ('far_voiced_hint' in locals() and far_voiced_hint) else 1.0)
                        base_keep_68 = max(0.24, base_keep_68 - df_scale * distance_factor)
                    # 跨帧平滑，降低门控抖动
                    if not hasattr(self, '_g68_smooth_state'):
                        self._g68_smooth_state = {}
                    g68_prev = float(self._g68_smooth_state.get(key, base_keep_68))
                    g_68_inst = base_keep_68 + (1.0 - base_keep_68) * min(1.0, r68)
                    g_68 = 0.75 * g68_prev + 0.25 * g_68_inst
                    self._g68_smooth_state[key] = g_68

                # >8k地板门控（独立因子）
                try:
                    e_8p = float(np.mean(np.abs(hf_high_x - high_6_8_x))) + 1e-12
                except Exception:
                    e_8p = max(1e-12, e_hh - e_h68)
                if not hasattr(self, '_breath_8p_env'): self._breath_8p_env = {}
                if not hasattr(self, '_breath_8p_floor'): self._breath_8p_floor = {}
                env8_prev = float(self._breath_8p_env.get(key, 0.0))
                env8 = float(0.6 * env8_prev + 0.4 * e_8p)
                self._breath_8p_env[key] = env8
                floor8 = float(self._breath_8p_floor.get(key, env8))
                if env8 > floor8:
                    floor8 = 0.985 * floor8 + 0.015 * env8
                else:
                    floor8 = 0.997 * floor8 + 0.003 * env8
                self._breath_8p_floor[key] = floor8
                g_8p = 1.0
                if floor8 > 0.0:
                    r8 = env8 / (1.20 * floor8)
                    r8 = 0.0 if r8 < 0.0 else (2.0 if r8 > 2.0 else r8)
                    base_keep_8 = 0.42 if natural else 0.38
                    if voiced_soft:
                        base_keep_8 = min(0.55, base_keep_8 + 0.08)
                    if far_quiet:
                        base_keep_8 = max(0.22, base_keep_8 - 0.12)
                    # 头声/高音：保留更多>8k 的空气与倍频；同时减弱远距影响系数
                    if 'voiced_bright' in locals() and voiced_bright:
                        base_keep_8 = max(base_keep_8, 0.45)
                        base_keep_8 = max(0.18, base_keep_8 - 0.15 * distance_factor * 0.5)
                    else:
                        # 距离因子：越远越再降一点>8k保留
                        # 远距+很远：允许更低下限到0.16以压极细“丝丝”
                        min8 = 0.16 if (('far_quiet' in locals() and far_quiet) and distance_factor > 0.7 and not ('far_voiced_hint' in locals() and far_voiced_hint)) else 0.18
                        df_scale8 = 0.15 * (0.5 if ('far_voiced_hint' in locals() and far_voiced_hint) else 1.0)
                        base_keep_8 = max(min8, base_keep_8 - df_scale8 * distance_factor)
                    # 跨帧平滑
                    if not hasattr(self, '_g8p_smooth_state'):
                        self._g8p_smooth_state = {}
                    g8_prev = float(self._g8p_smooth_state.get(key, base_keep_8))
                    g_8p_inst = base_keep_8 + (1.0 - base_keep_8) * min(1.0, r8)
                    g_8p = 0.75 * g8_prev + 0.25 * g_8p_inst
                    self._g8p_smooth_state[key] = g_8p

                # 2–4.5k存在感提升（避免远距小声变“薄/糊”）
                try:
                    if not hasattr(self, '_breath_lp25_state'):
                        self._breath_lp25_state = {}
                    prev25 = float(self._breath_lp25_state.get(key, 0.0))
                    sr = float(getattr(self, 'sample_rate', 48000.0))
                    fc25 = 4500.0
                    a25 = 1.0 - np.exp(-2.0 * np.pi * fc25 / max(1000.0, sr))
                    a25 = float(np.clip(a25, 0.0, 0.995))
                    y_lp25 = np.empty_like(x)
                    for i in range(len(x)):
                        prev25 = prev25 + a25 * (x[i] - prev25)
                        y_lp25[i] = prev25
                    self._breath_lp25_state[key] = float(prev25)
                    band_2_45 = (y_lp25 - y_lp2)
                except Exception:
                    band_2_45 = mid_band

                pres_far = 0.0
                if far_quiet:
                    pres_far = (0.020 if natural else 0.015) + 0.015 * distance_factor

                # 合成（带6–8k专治）
                y = y_lp * (1.0 + low_boost) + (mid_gain * mid_band) + pres_far * band_2_45 + g_mid * hf_mid + (g * g_vh) * (g_68 * high_6_8_post + g_8p * high_8p_post)
            except Exception:
                # 回退到旧合成
                y = y_lp * (1.0 + low_boost) + mid_gain * mid_band + g_mid * hf_mid + (g * g_vh) * hf_high

            # 🎛️ 假声高音柔化（亮而不刺）：>6k轻度动态高架压制 + 中频存在感回填
            try:
                if 'voiced_bright' in locals() and voiced_bright and len(x) >= 32:
                    # 以 4.5–8k 带的相对能量估计“刺度”
                    if not hasattr(self, '_breath_lp25_state'):
                        self._breath_lp25_state = {}
                    prev25 = float(self._breath_lp25_state.get(key, 0.0))
                    sr = float(getattr(self, 'sample_rate', 48000.0))
                    fc25 = 4500.0
                    a25 = 1.0 - np.exp(-2.0 * np.pi * fc25 / max(1000.0, sr))
                    a25 = float(np.clip(a25, 0.0, 0.995))
                    y_lp25 = np.empty_like(x)
                    for i in range(len(x)):
                        prev25 = prev25 + a25 * (x[i] - prev25)
                        y_lp25[i] = prev25
                    self._breath_lp25_state[key] = float(prev25)
                    band_48 = (y_lp4 - y_lp25)  # ≈4.5–8k
                    e_48 = float(np.mean(np.abs(band_48))) + 1e-9
                    e_mid = float(np.mean(np.abs(mid_band))) + 1e-9
                    t_soft = float(np.clip((e_48 / e_mid - 0.8) / 0.9, 0.0, 1.0))
                    # 轻度高架压制量（对>6k部分 y - y_lp3），与distance_factor收敛
                    user_strength = float(getattr(self, 'natural_earback_strength', 0.6))
                    shelf_amt = (0.05 + 0.06 * user_strength) * t_soft * (0.9 - 0.4 * float(distance_factor))
                    shelf_amt = float(np.clip(shelf_amt, 0.0, 0.12))
                    if shelf_amt > 0.0:
                        y = y - shelf_amt * (y - y_lp3)
                        # 轻度存在感回填，保持柔和但不“闷”
                        y = y + (0.010 + 0.010 * t_soft) * mid_band
            except Exception:
                pass

            # 呼吸期：轻微提升“空气带”（约4.5–6kHz），让气声更通透（极轻）
            try:
                if 'breath_detect' in locals() and breath_detect and len(x) >= 32:
                    if not hasattr(self, '_breath_lp25_state'):
                        self._breath_lp25_state = {}
                    prev25 = float(self._breath_lp25_state.get(key, 0.0))
                    sr = float(getattr(self, 'sample_rate', 48000.0))
                    fc25 = 4500.0
                    a25 = 1.0 - np.exp(-2.0 * np.pi * fc25 / max(1000.0, sr))
                    a25 = float(np.clip(a25, 0.0, 0.995))
                    y_lp25 = np.empty_like(x)
                    for i in range(len(x)):
                        prev25 = prev25 + a25 * (x[i] - prev25)
                        y_lp25[i] = prev25
                    self._breath_lp25_state[key] = float(prev25)
                    air_band = (y_lp3 - y_lp25)  # ≈4.5–6k
                    air_gain = 0.02 if natural else 0.015
                    y = y + air_gain * air_band
            except Exception:
                pass

            # 三点均值极轻混合，进一步柔化边缘
            if len(y) > 2:
                avg3 = y.copy()
                avg3[1:-1] = (y[:-2] + y[1:-1] + y[2:]) / 3.0
                if natural:
                    blend = 0.02 + 0.05 * s  # 更轻的邻域均值混合，减少“抽空”感/模糊
                else:
                    blend = 0.08 + 0.16 * s

                # 跨回调平滑参数，避免“拉链噪声”
                if not hasattr(self, '_breath_prev_params'):
                    self._breath_prev_params = {}
                prevp = self._breath_prev_params.get(key, {'alpha': alpha, 'g': g, 'blend': blend})
                smooth = 0.85
                alpha = prevp['alpha'] * smooth + alpha * (1.0 - smooth)
                g = prevp['g'] * smooth + g * (1.0 - smooth)
                blend = prevp['blend'] * smooth + blend * (1.0 - smooth)
                # 呼吸段：进一步降低平滑比例，避免“糊”
                if breath_detect:
                    blend *= 0.70
                # 头声/高音：减少邻域混合，保持瞬态与通透
                if 'voiced_bright' in locals() and voiced_bright:
                    blend *= 0.70
                self._breath_prev_params[key] = {'alpha': float(alpha), 'g': float(g), 'blend': float(blend)}
                y = y * (1.0 - blend) + avg3 * blend

            # 嗡嗡声场景：后置轻微“倾斜”到低通版本，进一步减小高频底噪
            if tonal_hum:
                tilt = 0.06 if natural else 0.08   # 减小整体“闷感”
                y = y * (1.0 - tilt) + y_lp * tilt

            # 软门控（随 RMS 渐变），避免完全静音导致不自然
            if not natural:
                # 非自然模式保留轻门控，强度也随 s 调整
                gate_min = 0.55
                gate = gate_min + (1.0 - gate_min) * min(1.0, rms / (thr_low * 1.5))
                y = y * (0.9 + 0.1 * s)  # 极轻动态，避免泵动
                y = y * gate

            # 轻度干声回灌：保留呼吸与轻声的气感（不参与高频抑制判断）
            dry_mix = 0.0
            if rms < thr_mid:
                if tonal_hum:
                    # 嗡嗡声尽量避免把高频底噪带回
                    dry_mix = 0.0 + 0.02 * min(1.0, (thr_mid - rms) / max(1e-9, thr_mid))
                else:
                    if zc >= 0.15:  # 呼吸偏多
                        dry_mix = 0.06 + 0.06 * min(1.0, (thr_mid - rms) / max(1e-9, thr_mid))
                    elif zc <= 0.08:  # 轻声有声（更少ZCR）
                        dry_mix = 0.04 + 0.05 * min(1.0, (thr_mid - rms) / max(1e-9, thr_mid))
            # 远距小声：降低干声回灌，避免把“滋啦”带回
            try:
                if far_quiet and dry_mix > 0.0:
                    dry_mix *= (0.6 * (1.0 - 0.5 * distance_factor))
            except Exception:
                pass
            # 呼吸段：小幅增加干声混合以保留空气感
            if breath_detect:
                dry_mix = min(0.20, dry_mix + (0.03 if natural else 0.04))
            if 0.0 < dry_mix < 0.20:
                y = y * (1.0 - dry_mix) + x * dry_mix

            # 仅对高频残差做极轻的抗振铃滤波（- - + 型三抽头），让砂感更顺滑
            try:
                if len(y) > 4:
                    hf_only = y - (y_lp * (1.0 + low_boost) + mid_gain * mid_band)
                    sm = hf_only.copy()
                    sm[2:-2] = (-0.15*hf_only[0:-4] - 0.15*hf_only[1:-3] + 0.60*hf_only[2:-2] - 0.15*hf_only[3:-1] - 0.15*hf_only[4:])
                    hf_blend = 0.12 if tonal_hum else 0.08
                    if voiced_soft:
                        hf_blend *= 0.5  # 进一步减少高频平滑导致的“糊感”
                    if breath_detect:
                        hf_blend *= 0.7  # 呼吸段进一步降低高频平滑，保留气声细节
                    if 'voiced_bright' in locals() and voiced_bright:
                        hf_blend *= 0.6  # 高音时减少抗振铃平滑以保留通透
                    y = y + (sm - hf_only) * hf_blend
            except Exception:
                pass

            # （可选）微型KTV氛围：三抽头短延迟（7/11/17ms），极轻混合，带来更“房间感”
            try:
                ktv_enabled = bool(getattr(self, 'monitor_ktv_ambience', True))
                if ktv_enabled and len(y) >= 8:
                    sr = float(getattr(self, 'sample_rate', 48000.0))
                    ds = [int(0.007*sr), int(0.011*sr), int(0.017*sr)]
                    gs = [0.20, 0.13, 0.08] if natural else [0.16, 0.11, 0.07]
                    maxd = max(ds)
                    if not hasattr(self, '_ktv_delay_state'):
                        self._ktv_delay_state = {}
                    st = self._ktv_delay_state.get(key, np.zeros((maxd,), dtype=np.float32))
                    if st.shape[0] < maxd:
                        # 扩容
                        tmp = np.zeros((maxd,), dtype=np.float32)
                        tmp[-st.shape[0]:] = st
                        st = tmp
                    # 叠加三抽头
                    out = y.copy()
                    for d, gtap in zip(ds, gs):
                        if d <= 0 or gtap <= 0:
                            continue
                        if len(y) > d:
                            tap = np.concatenate([st[-d:], y[:-d]])
                        else:
                            pad = d - len(y)
                            tap = np.concatenate([st[-d:-d+len(y)], np.zeros((pad,), dtype=y.dtype)])
                        out += gtap * tap[:len(y)]
                    # 轻度色彩保护：对out做极小高频软膝，避免叠加后尖峰
                    pk = float(np.max(np.abs(out))+1e-12)
                    if pk > 0.98:
                        out *= (0.97/pk)
                    # 更新状态（保留最近 maxd 个样本）
                    new_tail = np.concatenate([st, y])
                    self._ktv_delay_state[key] = new_tail[-maxd:].astype(np.float32, copy=False)
                    # 融合比例极轻，避免明显回声
                    mix_k = 0.08
                    if 'voiced_bright' in locals() and voiced_bright:
                        mix_k *= 0.75
                    y = (1.0 - mix_k)*y + mix_k*out
            except Exception:
                pass

            # 头声/高音：极轻“空气带”（6–8k）提升，避免通透感流失（远距时自动收敛）
            try:
                if 'voiced_bright' in locals() and voiced_bright and len(x) >= 32:
                    sr = float(getattr(self, 'sample_rate', 48000.0))
                    # 使用已算的低通：y_lp4(≈8k) - y_lp3(≈6k) 近似6–8k带
                    air_head_gain = (0.018 + 0.012 * float(getattr(self, 'natural_earback_strength', 0.6))) * (1.0 - 0.6 * float(distance_factor))
                    # 更保守的上限，避免极高音时“沙化/炸感”
                    air_head_gain = float(np.clip(air_head_gain, 0.0, 0.038))
                    y = y + air_head_gain * (y_lp4 - y_lp3)
            except Exception:
                pass

            # 轻声有声：极轻的“presence”提升（以中频带为依据），增强齿音/清晰度
            if voiced_soft and len(y) == len(mid_band):
                pres = 0.045 if natural else 0.035
                y = y + pres * mid_band

            # ➕ 微弱语音智能增强：只在“低音量且像有声音色”的片段做小幅度增强，避免放大呼吸/电流噪
            try:
                # 声像判断：低RMS + 低ZCR(更接近有声) + 中频优于高频 + 高频底噪不高
                voiced_quiet = (rms > thr_low * 0.85) and (rms < thr_mid)
                voiced_quiet = voiced_quiet and (zc <= 0.12)
                voiced_quiet = voiced_quiet and (mid_high_ratio > 1.6)
                # 高频底噪门控（避免把“滋啦”放大）
                hf_ok = True
                try:
                    hf_ok = (hf_env < (0.95 * max(1e-6, env_thr)))
                except Exception:
                    hf_ok = True

                if voiced_quiet and hf_ok:
                    # 目标增益：随RMS与用户强度温和变化，最大约+3.5dB（≈1.5x以内）
                    user_strength = float(getattr(self, 'natural_earback_strength', 0.6))
                    # 基础目标随音量线性插值：越靠近thr_low增益越高
                    t_q = 1.0 - min(1.0, max(0.0, (rms - thr_low) / max(1e-9, (thr_mid - thr_low))))
                    g_target = 1.0 + (0.18 + 0.12 * user_strength) * t_q  # 约 +1.8~+3.0 dB
                    # 远距轻增益：distance_factor越高，额外给到最多约+2 dB（与音量因子相乘，近似0.5~2 dB）
                    g_target += (0.06 + 0.10 * user_strength) * float(distance_factor) * (0.5 + 0.5 * t_q)
                    g_target = min(g_target, 1.55)  # 总体上限约 +3.8 dB，仍受VRMS保护
                    # 轻存在感倾斜：以 mid_band + 少量 hf_mid 提升发音清晰
                    pres2 = (0.025 + 0.02 * user_strength) * t_q  # 额外 presence
                    # 远距时再加一丝存在感，避免“远处放大但仍偏薄”
                    pres2 += 0.008 * float(distance_factor) * (0.5 + 0.5 * t_q)
                    y = y + pres2 * (mid_band + 0.25 * hf_mid)

                    # 平滑增强增益，避免跳动
                    if not hasattr(self, '_breath_voice_gain_state'):
                        self._breath_voice_gain_state = {}
                    g_prev = float(self._breath_voice_gain_state.get(key, 1.0))
                    g_s = 0.85 * g_prev + 0.15 * g_target
                    self._breath_voice_gain_state[key] = g_s
                    # 应用整体微增强（在 presence 倾斜后）
                    y = y * g_s
                else:
                    # 非“像有声”的低音量片段：可适当加强>6k抑制的保守性（通过g_vh已实现），此处不做增强
                    if hasattr(self, '_breath_voice_gain_state'):
                        # 轻松回落到1.0，避免长时间残留
                        g_prev = float(self._breath_voice_gain_state.get(key, 1.0))
                        self._breath_voice_gain_state[key] = 0.9 * g_prev + 0.1 * 1.0
            except Exception:
                pass

            # 极低电平时对整体做一个极轻的扩展器（下倾），帮助“电流尾巴”更自然淡出
            try:
                if rms < (thr_low * 0.85):
                    # 避免对纯正弦/很纯嗡嗡过度扩展
                    if not tonal_hum or zc > 0.10:
                        # downward expander: y *= expander_gain(rms)
                        # 将极低电平范围映射到 [exp_min,1.0]
                        exp_min = 0.85 if natural else 0.80
                        t = min(1.0, max(0.0, rms / max(1e-9, thr_low * 0.85)))
                        exp_g = exp_min + (1.0 - exp_min) * t
                        y *= exp_g
            except Exception:
                pass

            # 温和限幅，避免偶发尖峰
            peak = float(np.max(np.abs(y)))
            if peak > 0.98:
                y = y * (0.97 / peak)

            # 边界短交叉淡入，抑制分块边界“沙沙”
            if natural:
                if not hasattr(self, '_breath_tail'):
                    self._breath_tail = {}
                tail = self._breath_tail.get(key)
                if tail is not None and len(y) > 8 and len(tail) >= 8:
                    # 自适应交叉长度：不超过当前块/尾部长度的一半，上限64
                    cap = max(8, min(len(y)//2, len(tail)))
                    N = min(64, cap)
                    if N > 0:
                        # 线性淡入，前 N 样本与上块尾部融合
                        t = np.linspace(0.0, 1.0, N, dtype=np.float32)
                        y[:N] = tail[-N:] * (1.0 - t) + y[:N] * t
                # 记录当前尾部
                M = min(64, len(y))
                if M > 0:
                    self._breath_tail[key] = y[-M:].copy()
            return y.astype(audio_data.dtype, copy=False)
        except Exception:
            return audio_data
    
    # ========= 监听耳返安全输出：头房 + VRMS软限幅（无染色） ========= #
    def _apply_headroom_and_vrms(self, audio_data: np.ndarray, key: str = 'default') -> np.ndarray:
        """对耳返输出添加固定头房和慢速VRMS软限幅，避免削波又尽量不改变音色。
        - 头房：将整体电平降低 headroom_db（默认 -6 dB）
        - VRMS软限幅：RMS 阈值约 0.7FS，Attack 100ms，Release 4s，软膝
        """
        try:
            if audio_data is None or len(audio_data) == 0:
                return audio_data
            x = audio_data.astype(np.float32, copy=False)
            # 头房预增益（线性）
            headroom_db = float(getattr(self, 'headroom_db', -6.0))
            headroom_lin = 10.0 ** (headroom_db / 20.0)
            y = x * headroom_lin

            # VRMS软限幅
            if not hasattr(self, '_vrms_state') or self._vrms_state is None:
                self._vrms_state = {}
            st = self._vrms_state.get(key, {
                'env': 0.0,
                'gain': 1.0
            })
            # 估计块RMS
            rms = float(np.sqrt(np.mean(y * y)) + 1e-12)
            # 平滑RMS包络（Attack快，Release慢）
            sr = float(getattr(self, 'sample_rate', 48000))
            atk_t = 0.10  # 100ms
            rel_t = 4.0   # 4s
            atk_a = np.exp(-1.0 / max(1.0, atk_t * sr))
            rel_a = np.exp(-1.0 / max(1.0, rel_t * sr))
            env = st['env']
            if rms > env:
                env = atk_a * env + (1 - atk_a) * rms
            else:
                env = rel_a * env + (1 - rel_a) * rms

            # 软膝压缩曲线（针对RMS），阈值约 0.70FS
            thr = 0.70
            knee = 0.10
            if env <= thr - knee:
                tgt_gain = 1.0
            elif env >= thr + knee:
                # 比率约 4:1 的温和压缩，避免泵动
                ratio = 4.0
                over = env / thr
                comp = over ** ((ratio - 1.0) / ratio)
                tgt_gain = 1.0 / max(1e-6, comp)
            else:
                # 软膝插值
                t = (env - (thr - knee)) / (2 * knee)
                t = 0.0 if t < 0 else (1.0 if t > 1.0 else t)
                ratio = 4.0
                over = env / thr
                comp = over ** ((ratio - 1.0) / ratio)
                comp_gain = 1.0 / max(1e-6, comp)
                tgt_gain = (1 - t) * 1.0 + t * comp_gain

            # 平滑限幅增益（超慢，避免闪动）
            g = st['gain']
            g_smooth = 0.995 * g + 0.005 * tgt_gain
            st['env'] = float(env)
            st['gain'] = float(g_smooth)
            self._vrms_state[key] = st

            out = y * g_smooth
            # 最后安全峰值限制（极少触发）
            peak = float(np.max(np.abs(out)) + 1e-12)
            if peak > 0.995:
                out = out * (0.990 / peak)
            return out.astype(np.float32, copy=False)
        except Exception:
            return audio_data
    
    def _apply_intelligent_smoothing(self, frequency, confidence):
        """
        智能平滑算法：保持稳定歌声的自然微弱变化
        - 对于稳定音高：允许小范围自然变化（±5-15Hz）
        - 对于音高跳跃：保留真实的音乐跳跃
        - 对于异常抖动：进行平滑处理
        """
        try:
            # 初始化平滑历史
            if not hasattr(self, '_smooth_history'):
                self._smooth_history = []
                self._stable_frequency = 0
                self._frequency_trend = 0
            
            # 添加当前频率到历史
            self._smooth_history.append({
                'frequency': frequency,
                'confidence': confidence,
                'timestamp': time.time()
            })
            
            # 保持历史窗口大小（约1秒的历史，假设60fps）
            max_history = 60
            if len(self._smooth_history) > max_history:
                self._smooth_history.pop(0)
            
            # 如果历史数据不足，直接返回当前频率
            if len(self._smooth_history) < 3:
                self._stable_frequency = frequency
                return frequency
            
            # 分析最近的频率趋势
            recent_frequencies = [h['frequency'] for h in self._smooth_history[-10:]]
            current_mean = np.mean(recent_frequencies)
            current_std = np.std(recent_frequencies)
            
            # 🎯 核心逻辑：区分稳定歌声的自然变化 vs 异常抖动
            
            # 情况1：稳定歌声的自然变化（标准差小于20Hz）
            if current_std < 20:
                # 允许小范围的自然变化，使用轻度平滑
                natural_variation_threshold = 15  # 允许±15Hz的自然变化
                
                if abs(frequency - current_mean) <= natural_variation_threshold:
                    # 在自然变化范围内，使用轻微的移动平均
                    alpha = 0.7  # 较高的响应性，保留自然变化
                    smoothed = alpha * frequency + (1 - alpha) * self._stable_frequency
                    self._stable_frequency = smoothed
                    return smoothed
                else:
                    # 超出自然变化范围，可能是音高跳跃
                    self._stable_frequency = frequency
                    return frequency
            
            # 情况2：检测到音高跳跃（变化超过50Hz）
            elif abs(frequency - current_mean) > 50:
                # 真实的音高跳跃，保留原始频率
                self._stable_frequency = frequency
                return frequency
            
            # 情况3：中等程度的抖动（20-50Hz标准差）
            else:
                # 使用适中的平滑
                alpha = 0.3  # 中等平滑
                smoothed = alpha * frequency + (1 - alpha) * self._stable_frequency
                self._stable_frequency = smoothed
                return smoothed
                
        except Exception as e:
            print(f"❌ 平滑算法错误: {e}")
            return frequency
    
    def _is_test_signal(self, audio_data):
        """检测是否为测试信号（简单的正弦波）"""
        try:
            # 🎯 改进的测试信号检测逻辑 - 提高噪声容忍度
            rms = np.sqrt(np.mean(audio_data ** 2))
            
            # 1. 检查信号幅度（放宽范围，适应噪声环境）
            if 0.05 <= rms <= 1.0:  # 降低最低要求 (0.1 → 0.05)
                # 2. 检查信号的纯度（正弦波特征）
                # 使用FFT检查频谱特征
                fft = np.abs(np.fft.rfft(audio_data))
                if len(fft) > 10:
                    # 找到主峰
                    peak_idx = np.argmax(fft)
                    peak_magnitude = fft[peak_idx]
                    
                    # 计算总能量
                    total_energy = np.sum(fft)
                    
                    # 主峰能量占比（正弦波应该有很高的单峰占比）
                    peak_energy_ratio = peak_magnitude / (total_energy + 1e-10)
                    
                    # 3. 检查是否为清晰的单频信号（降低要求适应噪声）
                    if peak_energy_ratio > 0.15:  # 降低要求 (0.3 → 0.15)
                        # 4. 验证频率范围（测试频率通常在这个范围）
                        freqs = np.fft.rfftfreq(len(audio_data), 1/44100)  # 假设44100Hz采样率
                        peak_frequency = freqs[peak_idx]
                        
                        if self.min_frequency <= peak_frequency <= self.max_frequency:  # 使用可配置范围
                            print(f"🧪 识别为测试信号: RMS={rms:.3f}, 主峰频率={peak_frequency:.1f}Hz, 能量占比={peak_energy_ratio:.3f}")
                            return True
            
            return False
        except Exception as e:
            print(f"测试信号检测错误: {e}")
            return False
    
    def _test_mode_detection(self, audio_data):
        """测试模式的简化检测"""
        try:
            print(f"🧪 测试模式激活：信号长度={len(audio_data)}, RMS={np.sqrt(np.mean(audio_data**2)):.3f}")
            
            # 🎯 方法1：FFT峰值检测（对测试信号最可靠）
            fft = np.abs(np.fft.rfft(audio_data))
            freqs = np.fft.rfftfreq(len(audio_data), 1/self.sample_rate)
            
            # 找到最强的频率分量
            if len(fft) > 0:
                peak_idx = np.argmax(fft)
                peak_frequency = freqs[peak_idx]
                peak_magnitude = fft[peak_idx]
                
                # 计算信噪比（主峰与其他频率的比值）
                sorted_fft = np.sort(fft)[::-1]  # 从大到小排序
                if len(sorted_fft) > 1:
                    snr = sorted_fft[0] / (sorted_fft[1] + 1e-10)
                else:
                    snr = peak_magnitude
                
                if getattr(self, 'debug_flags', {}).get('fft_log', False):
                    print(f"🧪 FFT分析: 主频率={peak_frequency:.1f}Hz, 幅度={peak_magnitude:.3f}, SNR={snr:.1f}")
                
                # 验证频率范围和信噪比（降低要求，提高噪声容忍度）
                if 80 <= peak_frequency <= 800 and snr > 1.5 and peak_magnitude > 0.005:
                    if getattr(self, 'debug_flags', {}).get('fft_log', False):
                        print(f"🧪 FFT检测成功: {peak_frequency:.1f}Hz")
                    return peak_frequency
            
            # 🎯 方法2：自相关检测（更严格的验证）
            try:
                # 使用汉明窗减少边界效应
                windowed = audio_data * np.hamming(len(audio_data))
                correlation = np.correlate(windowed, windowed, mode='full')
                correlation = correlation[len(correlation)//2:]
                
                if len(correlation) > 1 and correlation[0] > 0:
                    correlation = correlation / correlation[0]
                    
                    # 搜索范围（对应80-800Hz）
                    min_period = max(int(self.sample_rate / 800), 1)
                    max_period = min(int(self.sample_rate / 80), len(correlation) - 1)
                    
                    if max_period > min_period:
                        search_range = correlation[min_period:max_period]
                        if len(search_range) > 0:
                            peak_idx = np.argmax(search_range)
                            peak_index = peak_idx + min_period
                            frequency = self.sample_rate / peak_index
                            confidence = correlation[peak_index]
                            
                            print(f"🧪 自相关分析: 频率={frequency:.1f}Hz, 置信度={confidence:.3f}")
                            
                            # 双重验证：FFT和自相关结果要接近（降低置信度要求）
                            if (80 <= frequency <= 800 and confidence > 0.05 and 
                                abs(frequency - peak_frequency) / frequency < 0.15):  # 放宽误差容忍度 (0.1 → 0.15)
                                print(f"🧪 双重验证成功: {frequency:.1f}Hz")
                                return frequency
            except Exception as e:
                print(f"🧪 自相关检测错误: {e}")
            
            print("🧪 测试模式检测失败 - 无有效音高")
            return 0
            
        except Exception as e:
            print(f"🧪 测试模式检测错误: {e}")
            return 0
    
    def detect_vibrato(self, current_frequency, current_time):
        """检测颤音"""
        vibrato_info = {
            'has_vibrato': False,
            'rate': 0.0,
            'depth': 0.0,
            'description': ''
        }
        
        try:
            if len(self.pitch_history) < self.vibrato_detection_window:
                return vibrato_info
            
            # 获取最近的音高历史
            recent_history = list(self.pitch_history)[-self.vibrato_detection_window:]
            frequencies = [h['frequency'] for h in recent_history]
            times = [h['timestamp'] for h in recent_history]
            
            if len(frequencies) < 20:
                return vibrato_info
            
            # 音高变化分析
            freq_array = np.array(frequencies)
            time_array = np.array(times)
            
            # 去除趋势，只看振动
            mean_freq = np.mean(freq_array)
            freq_detrend = freq_array - mean_freq
            
            # 计算变化幅度
            pitch_variation = np.std(freq_detrend)
            
            # 检测周期性
            if pitch_variation > self.vibrato_threshold:
                # 简单的周期性检测
                autocorr = np.correlate(freq_detrend, freq_detrend, mode='full')
                autocorr = autocorr[len(autocorr)//2:]
                
                if len(autocorr) > 5:
                    # 寻找周期性峰值
                    search_range = autocorr[2:min(30, len(autocorr))]
                    if len(search_range) > 0:
                        max_idx = np.argmax(search_range) + 2
                        max_autocorr = search_range[max_idx - 2]
                        
                        # 估算颤音频率
                        if len(times) > 1:
                            time_interval = (times[-1] - times[0]) / len(times)
                            vibrato_period = max_idx * time_interval
                            vibrato_rate = 1.0 / vibrato_period if vibrato_period > 0 else 0
                            
                            # 判断是否为有效颤音 (3-12Hz)
                            if 3.0 <= vibrato_rate <= 12.0 and max_autocorr > 0.2:
                                vibrato_info.update({
                                    'has_vibrato': True,
                                    'rate': vibrato_rate,
                                    'depth': pitch_variation,
                                    'description': f"颤音 {vibrato_rate:.1f}Hz，深度±{pitch_variation:.1f}Hz"
                                })
        
        except Exception as e:
            print(f"颤音检测错误: {e}")
        
        return vibrato_info

    # ============================================================================
    # 🔧 向后兼容的监听方法接口（重定向到统一方法）
    # ============================================================================
    
    def start_audio_monitoring(self):
        """启动音频监听（重定向到统一方法）"""
        return self.start_unified_monitoring()
    
    def stop_audio_monitoring(self):
        """停止音频监听（重定向到统一方法）"""
        return self.stop_unified_monitoring()
    
    def start_monitoring(self):
        """启动监听（重定向到统一方法）"""
        return self.start_unified_monitoring()
    
    def stop_monitoring(self):
        """停止监听（重定向到统一方法）"""
        return self.stop_unified_monitoring()
    
    def stop_unified_monitoring(self):
        """停止统一监听功能"""
        try:
            print("🛑 正在停止监听(统一)...")

            # 立即关闭回传，避免用户继续听到自身声音
            if hasattr(self, 'monitor_audio_passthrough'):
                self.monitor_audio_passthrough = False

            # 更新状态标志
            self.is_monitoring_only = False

            # 停止后台音频处理线程（先停处理再关流，避免回调访问已关闭流）
            try:
                self.stop_audio_processing_thread()
            except Exception as e_proc:
                print(f"⚠️ 停止音频处理线程时出错: {e_proc}")

            # 关闭所有可能的音频流
            for attr in ['active_audio_stream', 'monitoring_stream', 'audio_stream']:
                stream = getattr(self, attr, None)
                if stream is None:
                    continue
                try:
                    try:
                        stream.stop()
                    except Exception:
                        pass
                    try:
                        stream.close()
                    except Exception:
                        pass
                    print(f"🔇 已关闭音频流: {attr}")
                except Exception as e_close:
                    print(f"⚠️ 关闭音频流 {attr} 出错: {e_close}")
                finally:
                    setattr(self, attr, None)

            # 重置全局监听标志
            self.is_global_monitoring_active = False
            if hasattr(self, 'monitoring_mode'):
                self.monitoring_mode = None

            print("✅ 监听已完全停止 (所有流与回传已关闭)")
            self.status_updated.emit("监听已停止")
            return True
        except Exception as e:
            print(f"❌ 停止监听失败: {e}")
            self.error_occurred.emit(f"停止监听失败: {e}")
            return False


class ECGStylePitchVisualizer(QWidget):
    """心电图式音高可视化器（支持交互拖拽）"""

    def __init__(self):
        super().__init__()
        # ================== 基础与参数 ==================
        self.audio_processor = None  # 运行时再注入
        self.time_window = 16.0
        self.max_points = 1024
        self.update_interval = 16  # ~60FPS，提升实时感

        # ===== 视图 / 历史窗口初始化 =====
        self.max_history_time = 300.0
        self.y_view_center = 4.0
        self.y_view_range = 3.0
        self.time_offset = 0.0
        self.center_display_time = 8.0
        self.auto_scroll_enabled = True
        self.zoom_level = 1.0
        self.base_y_view_range = self.y_view_range
        self._last_zoom_preset_logged = None
        self.auto_scale = True
        self.auto_follow = True
        # 默认不锁定，允许缩放/滚动立即生效
        self.freeze_y_center = False
        self._initial_y_center = self.y_view_center
        self._last_warn_y_shift = 0.0
        self.label_x_frac = 0.0
        self.label_left_pixel_offset = -6
        self._last_manual_scroll_time = 0.0

        # ================== 拖拽状态 ==================
        self.dragging = False
        self.drag_start_pos = None
        self.drag_start_y_center = None
        self.drag_start_time_offset = None

        # ================== 数据缓冲 ==================
        max_data_points = int(64 * self.max_history_time)
        print(f"📊 初始化数据缓冲区: {max_data_points} 个数据点 ({self.max_history_time}秒)")
        self.pitch_data = deque(maxlen=max_data_points)
        self.time_data = deque(maxlen=max_data_points)
        self.confidence_data = deque(maxlen=max_data_points)
        self.note_data = deque(maxlen=max_data_points)

        # ================== 时间轴状态 ==================
        self.start_time = None
        self.current_global_time = 0.0
        self.is_recording_active = False
        self.last_pitch_time = 0
        

        # ================== 绘制辅助 ==================
        self.gradient_lines = []
        self.highlight_point = None
        self._force_redraw_on_next_update = False

        # ================== 初始化组件 ==================
        self.setup_colors()
        self.setup_pitch_mapping()
        self.setup_performance_manager()
        self.init_ui()

        # ================== 调试控制 ==================
        self.debug_flags = {
            # 默认关闭高频日志，避免影响实时性；需要时可在调试面板开启
            'display_diag': False,
            'segment_log': False,
            'incremental_miss': True,
            'vocal_protect_verbose': False,
            'latency_warn_verbose': False,
            'summary_enabled': False,    # 关闭周期性SUMMARY，按需开启
            'axis_log': False,           # 轴范围日志
            'detection_log': False,      # 检测统计UI打印
            'latency_report': False,     # 回调详尽延迟报告
            'pitch_log': False,          # 逐条音高成功日志
            'pitch_precision_log': False,# 音高精度修复/验证日志
            'fft_log': False,            # FFT频率与高频抑制日志
            'queue_log': False,          # 队列/帧产出/循环诊断
            'artist_dump': False         # 轴Artist对象转储
        }
        # 启用单集合批量细节点（减少每帧 set_offsets 调用次数）
        self._use_batched_points = True
        # 仅更新末尾N段的细节点（旧段点位不变，减少每帧 set_offsets 开销）
        self._lazy_points_update_n = 3
        # 分段签名缓存：[(first_t, last_t, length), ...]
        self._segment_sigs = []
        # 时间轴平滑滚动状态
        self._smoothed_xlim = None  # (start, end)
        # 性能/绘制采样容器
        self._seg_timing_samples = deque(maxlen=120)
        self._draw_timing_samples = deque(maxlen=120)
        self._diag_last_perf_report = 0
        # 速率限制日志 & 统计
        self._last_log_times = {
            'vocal_protect': 0.0,
            'segment_draw': 0.0,
            'display_diag': 0.0
        }
        self._pending_counts = {}
        self._stat_counters = {
            'vocal_protect': 0,
            'high_latency': 0,
            'segments_recomputed': 0,
            'segment_cache_hits': 0
        }
        self._summary_interval = 2.0
        self._last_summary_time = time.time()
        self._vocal_protect_active = False
        # 显示诊断容器
        self._diag_last_display_time = None
        self._diag_display_intervals = []
        self._diag_add_to_display_latencies = []
        self._diag_pending_points = 0
        self._diag_last_report = 0.0
        # 日志辅助
        import time as _t
        def _log_rate_limit(key: str, msg: str, interval: float = 0.5):
            now = _t.time()
            last = self._last_log_times.get(key, 0.0)
            if now - last >= interval:
                pending = self._pending_counts.get(key, 0)
                if pending > 0:
                    print(f"{msg} (+{pending} more)")
                    self._pending_counts[key] = 0
                else:
                    print(msg)
                self._last_log_times[key] = now
            else:
                self._pending_counts[key] = self._pending_counts.get(key, 0) + 1
        self._log_rate_limit = _log_rate_limit
        def _maybe_summary():
            if not self.debug_flags.get('summary_enabled'):
                return
            now = _t.time()
            if now - self._last_summary_time >= self._summary_interval:
                dur = now - self._last_summary_time
                vp = self._stat_counters['vocal_protect']
                hl = self._stat_counters['high_latency']
                sre = self._stat_counters['segments_recomputed']
                sch = self._stat_counters['segment_cache_hits']
                fps_est = 0.0
                if self._draw_timing_samples:
                    avg_interval = sum(self._draw_timing_samples)/len(self._draw_timing_samples)
                    if avg_interval > 0:
                        fps_est = 1000.0/avg_interval
                print(f"[SUMMARY {dur:.1f}s] vocalProtect={vp} highLatency={hl} segRecompute={sre} segCacheHit={sch} fps~={fps_est:.1f}")
                for k in self._stat_counters:
                    self._stat_counters[k] = 0
            self._last_summary_time = now
            self._maybe_summary = _maybe_summary

            # ================== 运行/刷新计时器与阈值 ==================
            # 最小重绘间隔（秒）：避免过度重绘导致卡顿，但允许自适应策略在 update_display 内调节
            # 该值用于 add_pitch_data/_fast_update_tick 的快速判定，必须在此初始化
            self._min_heavy_interval = 0.020  # ~20ms，约等于 50FPS 的间隔基线，减少卡段感

            # 高频轻量帧定时器（即使没有新点也推动时间轴+细节点刷新）
            # 使用较小间隔以提升平滑度；如 CPU 允许可调至 8-12ms
            # 默认放缓轻量刷新，减轻总负载；需要更丝滑可调到 8-10ms
            self.fast_update_interval_ms = 10
        try:
            self.fast_update_timer = QTimer(self)
            # 精确定时器降低抖动
            self.fast_update_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self.fast_update_timer.timeout.connect(self._fast_update_tick)
            self.fast_update_timer.start(self.fast_update_interval_ms)
        except Exception:
            # 防御：在极端环境下保持逻辑安全
            self.fast_update_timer = None

        # 时间轴追踪定时器（独立于数据到来推进 current_global_time/auto-follow）
        # 在 start_time_tracking/stop_time_tracking 中启停
        self.time_update_interval = 16  # 约 60Hz 刷新
        try:
            self.time_update_timer = QTimer(self)
            self.time_update_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self.time_update_timer.timeout.connect(self.update_time_axis)
        except Exception:
            self.time_update_timer = None

        # 显示更新相关运行状态（防御性初始化，避免属性缺失报错）
        self._last_heavy_redraw_time = 0.0
        self._last_fast_tick = 0.0
        self._new_points_since_last_draw = 0
        self._auto_scroll_started = False
        # 轻量轴更新与网格重建节流
        try:
            self._last_grid_build_time = time.time()
        except Exception:
            self._last_grid_build_time = 0.0
        self._grid_rebuild_interval = 1.2  # 网格/标签重建最小间隔（秒）
        self._grid_dirty = True            # 有变化时由其他路径置为 True

        # ================== 辅助线（纵向/横向）配置 ==================
        self.guides_enabled = True  # 默认显示辅助线
        # 辅助线（主线 + 柔光底线）引用
        self.v_guide_line = None            # 纵向时间辅助线（主线 Line2D）
        self.h_guide_line = None            # 横向音高辅助线（主线 Line2D）
        self.v_guide_glow_line = None       # 纵向时间辅助线（柔光底线 Line2D）
        self.h_guide_glow_line = None       # 横向音高辅助线（柔光底线 Line2D）
        # 辅助线样式（更美观：主虚线 + 柔光底线）
        self.guide_v_color = '#C0C0C0'   # 银灰色（Silver），主色
        self.guide_h_color = '#C0C0C0'   # 与纵线同色
        self.guide_alpha_main = 0.90     # 主线不透明度（薄线略提亮）
        self.guide_alpha_glow = 0.12     # 柔光底线不透明度（更轻）
        self.guide_linewidth_main = 0.8  # 主线粗细（更细）
        self.guide_linewidth_glow = 2.2  # 柔光底线粗细（更克制）
        self.guide_dash_pattern = (6, 4) # 主虚线的破折间距（更轻快）
        self.last_active_pitch_y = None  # 记录最后一次有效音高（八度坐标）

    def _reset_display_diagnostics(self):
        """重置显示相关诊断统计，避免历史数据污染新阶段均值。"""
        self._diag_last_display_time = None
        self._diag_display_intervals.clear()
        self._diag_add_to_display_latencies.clear()
        self._diag_pending_points = 0
        # 也重置性能采样，防止停用后旧值残留
        self._seg_timing_samples.clear()
        self._draw_timing_samples.clear()
        self._diag_last_perf_report = 0
        self._last_log_times['display_diag'] = 0.0
        # 强制下一次刷新不早返回
        if hasattr(self, '_last_update_state'):
            self._last_update_state = (-1, (-1,-1), -999)

    def set_audio_processor(self, audio_processor):
        self.audio_processor = audio_processor
        print("🔗 音频处理器引用已设置到可视化器")
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(self.update_interval)
        print(f"🖥️ 可视化刷新定时器启动: {self.update_interval}ms")
    
    def start_time_tracking(self):
        """开始时间追踪（录音开始时调用）"""
        if self.start_time is None:
            self.start_time = time.time()

        self.is_recording_active = True
        # 开始新会话重置诊断
        if hasattr(self, '_reset_display_diagnostics'):
            self._reset_display_diagnostics()
        self.time_update_timer.start(self.time_update_interval)
        print(f"⏰ 开始时间追踪，基准时间: {self.start_time}")
    
    def stop_time_tracking(self):
        """停止时间追踪（录音停止时调用）"""
        self.is_recording_active = False
        self.time_update_timer.stop()
        # 停止时也重置，后续查看历史不再继续累计
        if hasattr(self, '_reset_display_diagnostics'):
            self._reset_display_diagnostics()
        print(f"⏸️ 停止时间追踪，当前时长: {self.current_global_time:.2f}秒")
        # 清除平滑与渲染窗口缓存，防止停止后被历史窗口/平滑拖拽回录音末端
        try:
            self._smoothed_xlim = None
            if hasattr(self, '_last_render_window'):
                delattr(self, '_last_render_window')
        except Exception:
            pass
    
    def update_time_axis(self):
        """更新时间轴（支持断续音调曲线）"""
        if self.start_time is None or not self.is_recording_active:
            return

        now_ts = time.time()
        # 更新当前全局时间
        self.current_global_time = now_ts - self.start_time

        # 是否处于手动滚动冻结期（2秒内不自动改写 time_offset）
        manual_freeze = (now_ts - getattr(self, '_last_manual_scroll_time', 0)) < 2.0

        if self.is_recording_active and self.auto_follow and self.auto_scroll_enabled and not manual_freeze:
            if self.current_global_time > self.center_display_time:
                self.time_offset = self.current_global_time - self.center_display_time
                max_offset = max(0, self.max_history_time - self.time_window)
                self.time_offset = min(self.time_offset, max_offset)
                self.update_scrollbars()
            else:
                self.time_offset = 0.0

        # 没有新数据也让显示推进：缩短触发阈值，避免“半秒一卡”观感
        if hasattr(self, 'last_pitch_time') and self.current_global_time - self.last_pitch_time > 0.12:
            try:
                self.update_display()
                if hasattr(self, 'canvas'):
                    self.canvas.draw_idle()
            except Exception:
                pass
    
    def clear_data(self):
        """清除所有数据（包括断续曲线）"""
        # ===== 诊断：清除前快照 =====
        try:
            if getattr(self, 'debug_flags', {}).get('artist_dump', False):
                self.debug_dump_axis_artists(context_tag="before_clear")
        except Exception:
            pass
        self.pitch_data.clear()
        self.time_data.clear()
        self.confidence_data.clear()
        self.note_data.clear()
        
        # 重置时间追踪变量
        self.start_time = None
        self.current_global_time = 0.0
        self.last_pitch_time = 0
        # 关键：重置时间轴导航/滚动状态，恢复“初始视图”但不改动用户其它设置
        try:
            # 回到最左端（0s），避免下一次开始时沿用旧偏移导致显示在数秒处
            self.time_offset = 0.0
            # 重新允许自动滚动，并清除手动滚动冻结痕迹
            self.auto_scroll_enabled = True
            self._last_manual_scroll_time = 0.0
            # 下次超过中心阈值时再启用自动滚动标志
            self._auto_scroll_started = False
            # 清除平滑滚动与上次渲染窗口缓存，防止延续旧的 xlim
            self._smoothed_xlim = None
            if hasattr(self, '_last_render_window'):
                delattr(self, '_last_render_window')
            # 停止可能存在的自动启用定时器，立即生效
            if hasattr(self, 'auto_scroll_timer') and getattr(self, 'auto_scroll_timer') is not None:
                try:
                    self.auto_scroll_timer.stop()
                except Exception:
                    pass
        except Exception:
            pass
        
        # 🔥 清除更新状态缓存，防止清除后无法正常更新
        if hasattr(self, '_last_update_state'):
            delattr(self, '_last_update_state')
        if hasattr(self, '_segments_cache'):
            delattr(self, '_segments_cache')
        if hasattr(self, '_segments_cache_key'):
            delattr(self, '_segments_cache_key')
        if hasattr(self, '_force_redraw_on_next_update'):
            delattr(self, '_force_redraw_on_next_update')
        
        # 清理主音调线
        if hasattr(self, 'pitch_line') and self.pitch_line is not None:
            self.pitch_line.set_data([], [])
            try:
                self.pitch_line.set_alpha(0.0)
            except Exception:
                pass
            # 移除对象引用，避免后续误用旧实例
            try:
                if self.pitch_line in self.ax.lines:
                    self.pitch_line.remove()
            except Exception:
                pass
            self.pitch_line = None
        
        # 🔥 清理断续曲线的所有段线条
        if hasattr(self, '_segment_lines'):
            for line in self._segment_lines:
                try:
                    line.remove()
                except:
                    pass
            self._segment_lines = []
        # 🔥 清理断续曲线的散点集合
        if hasattr(self, '_segment_points'):
            for pts in self._segment_points:
                try:
                    if pts in self.ax.collections:
                        pts.remove()
                except Exception:
                    pass
            self._segment_points = []
        # 清理批量细节点集合
    # 不销毁对象，仅从轴上移除时会在 safe_clear_axis 中被保存并恢复
    # 若对象仍存在但被Matplotlib清空，则保持引用待后续 update_display 重新填充
        
        # 清理段信息
        if hasattr(self, '_segments'):
            self._segments = []
        
        # 🔥 清理彩色渐变线条
        if hasattr(self, 'gradient_lines'):
            for line in self.gradient_lines:
                try:
                    if line is not None and line in self.ax.collections:
                        line.remove()
                except:
                    pass
            self.gradient_lines = []
        # 清理高亮前端粒子
        if hasattr(self, 'highlight_point') and self.highlight_point is not None:
            try:
                if self.highlight_point in self.ax.collections:
                    self.highlight_point.remove()
            except Exception:
                pass
            self.highlight_point = None
        # 清理动态音符标签
        if hasattr(self, '_note_label_texts'):
            for t in self._note_label_texts:
                try: t.remove()
                except Exception: pass
            self._note_label_texts = []
        # 清理活动音符高亮线
        if hasattr(self, '_active_note_highlight_lines'):
            for ln in self._active_note_highlight_lines:
                try:
                    if ln in self.ax.lines: ln.remove()
                except Exception: pass
            self._active_note_highlight_lines = []
        # 重置当前活动音高状态
        self.current_pitch_active = False
        if hasattr(self, 'current_pitch_y'):
            self.current_pitch_y = self.y_view_center if hasattr(self, 'y_view_center') else 4.0

        # 🔍 深度清理：移除可能残留的高 zorder 线条 (>=9 视为数据/高亮层)，保留网格 (低 zorder)
        try:
            for ln in list(self.ax.lines):
                z = getattr(ln, 'get_zorder', lambda: 0)()
                if z >= 9:  # 数据/高亮/曲线/段线
                    try: ln.remove()
                    except Exception: pass
        except Exception:
            pass

        # 彻底清轴后 立即重建网格 + 音名标签（用户期望“初始网格”而不是裸 0.0/0.2 数字刻度）
        try:
            self.ax.cla()
            self.ax.set_facecolor(self.bg_color)
            # 立即重建（不再等待新数据），保持视觉一致性
            try:
                self.setup_ecg_grid(create_pitch_line=True)
                # 明确取消延迟标记
                self._needs_grid_rebuild = False
                self._suppress_updates_until_new_data = False
            except Exception as _grid_e:
                print(f"⚠️ clear_data 内部重建网格失败: {_grid_e}; 将退回延迟模式")
                # 退回延迟模式
                self._needs_grid_rebuild = True
                self._suppress_updates_until_new_data = True
        except Exception as _regrid_e:
            print(f"⚠️ 清除时轴 cla 失败: {_regrid_e}")
        
        # 同步滚动条（确保水平滚动条复位到0）
        try:
            self.update_scrollbars()
        except Exception:
            pass

        if hasattr(self, 'canvas'):
            self.canvas.draw_idle()
        
        print("🗑️ 数据已清除（包括断续曲线和缓存状态）")
        # ===== 诊断：清除后快照 =====
        try:
            if getattr(self, 'debug_flags', {}).get('artist_dump', False):
                self.debug_dump_axis_artists(context_tag="after_clear")
        except Exception:
            pass

    def purge_visual_elements(self):
        """强制移除所有潜在残留的高层绘制元素（PathCollection/Line2D/Text）。"""
        try:
            # 移除高 zorder 线条
            for ln in list(self.ax.lines):
                try:
                    if getattr(ln, 'get_zorder', lambda:0)() >= 9:
                        ln.remove()
                except Exception:
                    pass
            # 移除数据集合（散点/渐变等）
            for coll in list(self.ax.collections):
                try:
                    if getattr(coll, 'get_zorder', lambda:0)() >= 9:
                        coll.remove()
                except Exception:
                    pass
            # 移除音符文本（依据典型格式 A-G 或含 # / b + 八度数字）
            import re
            note_pat = re.compile(r'^[A-G][#b]?\d$')
            for txt in list(self.ax.texts):
                try:
                    if note_pat.match(txt.get_text()):
                        txt.remove()
                except Exception:
                    pass
        except Exception as e:
            print(f"⚠️ purge_visual_elements 失败: {e}")
    
    # ================= 诊断辅助：列出当前轴对象 =================
    def debug_dump_axis_artists(self, context_tag: str = "runtime"):
        """打印当前轴上所有相关 Artist（线条/集合/文本）用于诊断残留。

        context_tag: 调用场景标记 (before_clear / after_clear / manual)
        """
        if not getattr(self, 'debug_flags', {}).get('artist_dump', False):
            return
        if not hasattr(self, 'ax'):
            print(f"[debug_dump_axis_artists:{context_tag}] ❌ 无 ax")
            return
        try:
            lines_info = []
            for i, ln in enumerate(list(self.ax.lines)):
                try:
                    lines_info.append({
                        'idx': i,
                        'id': hex(id(ln)),
                        'cls': ln.__class__.__name__,
                        'z': getattr(ln, 'get_zorder', lambda:0)(),
                        'label': ln.get_label(),
                        'color': getattr(ln, 'get_color', lambda:None)(),
                        'alpha': getattr(ln, 'get_alpha', lambda:None)(),
                        'npts': len(ln.get_xdata()) if hasattr(ln, 'get_xdata') else None
                    })
                except Exception:
                    pass
            colls_info = []
            for i, coll in enumerate(list(self.ax.collections)):
                try:
                    npts = None
                    if hasattr(coll, 'get_offsets'):
                        try:
                            npts = len(coll.get_offsets())
                        except Exception:
                            npts = 'err'
                    colls_info.append({
                        'idx': i,
                        'id': hex(id(coll)),
                        'cls': coll.__class__.__name__,
                        'z': getattr(coll, 'get_zorder', lambda:0)(),
                        'label': getattr(coll, 'get_label', lambda:None)(),
                        'alpha': getattr(coll, 'get_alpha', lambda:None)(),
                        'npts': npts
                    })
                except Exception:
                    pass
            texts_info = []
            for i, txt in enumerate(list(self.ax.texts)):
                try:
                    texts_info.append({
                        'idx': i,
                        'id': hex(id(txt)),
                        'txt': txt.get_text(),
                        'z': getattr(txt, 'get_zorder', lambda:0)(),
                        'color': txt.get_color(),
                        'alpha': txt.get_alpha()
                    })
                except Exception:
                    pass
            print(f"[debug_dump_axis_artists:{context_tag}] lines={len(lines_info)} collections={len(colls_info)} texts={len(texts_info)}")
            if lines_info:
                for info in lines_info:
                    print(f"  Line#{info['idx']} z={info['z']} npts={info['npts']} color={info['color']} alpha={info['alpha']} label={info['label']} id={info['id']}")
            if colls_info:
                for info in colls_info:
                    print(f"  Coll#{info['idx']} z={info['z']} npts={info['npts']} alpha={info['alpha']} label={info['label']} cls={info['cls']} id={info['id']}")
            if texts_info:
                shown = 0
                for info in texts_info:
                    if shown >= 25:
                        print(f"  ... 其余 {len(texts_info)-shown} 条文本省略 ...")
                        break
                    print(f"  Text#{info['idx']} z={info['z']} '{info['txt']}' color={info['color']} alpha={info['alpha']} id={info['id']}")
                    shown += 1
        except Exception as e:
            print(f"[debug_dump_axis_artists:{context_tag}] 失败: {e}")
    
    def setup_colors(self):
        """设置颜色配置"""
        # 心电图式颜色配置
        self.bg_color = '#000000'  # 黑色背景
        self.grid_color = '#003300'  # 深绿色网格
        # 音调主线颜色：琉璃蓝（DeepSkyBlue）
        self.line_color = '#00BFFF'
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
        
        # 打印频率控制
        self.ecg_print_counter = 0
        self.ecg_print_interval = 50  # 每50次调用只打印一次
    
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
    
    def setup_performance_manager(self):
        """设置性能管理器"""
        try:
            from src.audio_processing.performance_manager import get_performance_manager, PerformanceMode
            from src.audio_processing.gpu_accelerator import GPUAcceleratedProcessor
            
            self.performance_manager = get_performance_manager()
            self.gpu_accelerator = GPUAcceleratedProcessor()
            
            # 默认使用平衡模式
            self.current_performance_mode = PerformanceMode.BALANCED
            # 监听全局性能模式变更（确保在任何地方切换都能同步本界面与处理器）
            try:
                if hasattr(self.performance_manager, 'register_listener'):
                    self.performance_manager.register_listener(self._on_global_performance_mode_changed)
            except Exception as _reg_e:
                print(f"⚠️ 注册性能模式监听器失败: {_reg_e}")
            
            print("✅ 性能管理器初始化成功")
            print(f"   GPU加速: {'✅ 可用' if self.gpu_accelerator.is_gpu_available() else '❌ 不可用'}")

            # 启动时自动评估本机并选择更优模式
            try:
                self._auto_selected_mode_name = None
                self._auto_select_best_performance_mode()
            except Exception as _e:
                print(f"⚠️ 自动选择性能模式失败: {_e}")
            
        except ImportError as e:
            print(f"⚠️ 性能管理器初始化失败: {e}")
            self.performance_manager = None
            self.gpu_accelerator = None
            self.current_performance_mode = None

    def _auto_select_best_performance_mode(self):
        """基于系统能力与预测吞吐量，自动选择最适合的性能模式。
        规则：
        - 遍历三种模式，计算 predicted_actual_frequency 与目标 detection_frequency 的差距；
        - 满足目标的模式优先；GPU可用且启用的模式加分；
        - 选出得分最高者并设为当前模式；记录名称供UI初始化使用。
        """
        if not self.performance_manager:
            return
        from src.audio_processing.performance_manager import PerformanceMode
        pm = self.performance_manager
        modes = [PerformanceMode.QUIET, PerformanceMode.BALANCED, PerformanceMode.HIGH_PERFORMANCE]
        best_mode = pm.get_current_mode() if hasattr(pm, 'get_current_mode') else PerformanceMode.BALANCED
        best_score = -1e9
        original_mode = best_mode
        for m in modes:
            try:
                pm.set_performance_mode(m)
                cfg = pm.get_current_config()
                opt = pm.optimize_for_realtime()
                pred = float(opt.get('predicted_actual_frequency', 0.0))
                target = float(cfg.detection_frequency)
                shortfall = max(0.0, target - pred)
                score = pred - 0.6 * shortfall
                # GPU加分（仅当可用并启用）
                if getattr(cfg, 'use_gpu_acceleration', False) and getattr(pm, 'gpu_available', False):
                    score += 3.0
                # 高性能模式微量偏好
                if m == PerformanceMode.HIGH_PERFORMANCE:
                    score += 0.5
                if score > best_score:
                    best_score = score
                    best_mode = m
            except Exception:
                continue
        # 应用最佳模式
        try:
            pm.set_performance_mode(best_mode)
            self.current_performance_mode = best_mode
            self._auto_selected_mode_name = best_mode.value
            print(f"🧠 自动选择性能模式: {best_mode.value} (score={best_score:.2f})")
        except Exception:
            # 回退原模式
            try:
                pm.set_performance_mode(original_mode)
            except Exception:
                pass
            self._auto_selected_mode_name = None
    
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
        
        # 性能模式选择
        controls_row1_layout.addWidget(QLabel(" | 性能:"))
        self.performance_mode = QComboBox()
        self.performance_mode.addItems([
            "安静模式",      # 最低配置，节省资源  
            "平衡模式",      # 合理优化配置
            "高性能模式"     # 充分利用计算资源
        ])
        # 若自动选择了模式，使用其作为初始显示
        try:
            if hasattr(self, '_auto_selected_mode_name') and self._auto_selected_mode_name:
                self.performance_mode.setCurrentText(self._auto_selected_mode_name)
            else:
                self.performance_mode.setCurrentText("平衡模式")  # 默认平衡模式
        except Exception:
            self.performance_mode.setCurrentText("平衡模式")
        self.performance_mode.currentTextChanged.connect(self.on_performance_mode_changed)
        self.performance_mode.setToolTip(
            "安静模式: 最低资源消耗，15Hz检测频率\n"
            "平衡模式: 合理性能与质量平衡，30Hz检测频率\n"
            "高性能模式: 充分利用计算资源，60Hz检测频率，GPU加速"
        )
        self.performance_mode.setStyleSheet("""
            QComboBox {
                background-color: #2E2E2E;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 3px 8px;
                min-width: 80px;
            }
            QComboBox:hover {
                background-color: #3E3E3E;
                border: 1px solid #707070;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::item {
                background-color: #2E2E2E;
                color: white;
                padding: 5px;
            }
            QComboBox::item:selected {
                background-color: #006600;
            }
        """)
        controls_row1_layout.addWidget(self.performance_mode)
        
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
        
    # (原功能按钮组移动至第二行)
        
        # 第一行布局添加到主布局
        main_controls_layout.addLayout(controls_row1_layout)
        
        # 第二行：线条粗细控制 + 频率范围控制 + 状态信息显示
        controls_row2_layout = QHBoxLayout()
        
        # 线条粗细控制 - 改为按钮形式
        self.linewidth_btn = QPushButton(f"线条: 0.6px")
        self.linewidth_btn.setMaximumWidth(80)
        self.linewidth_btn.setStyleSheet("""
            QPushButton {
                background: #404040;
                border: 1px solid #606060;
                color: white;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #505050;
                border: 1px solid #707070;
            }
            QPushButton:pressed {
                background: #303030;
            }
        """)
        self.linewidth_btn.clicked.connect(self.show_linewidth_dialog)
        controls_row2_layout.addWidget(self.linewidth_btn)
        
        # 频率范围控制按钮
        self.frequency_range_btn = QPushButton(f"频率: 80-1047Hz")
        self.frequency_range_btn.setMaximumWidth(120)
        self.frequency_range_btn.setStyleSheet("""
            QPushButton {
                background: #404040;
                border: 1px solid #606060;
                color: white;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #505050;
                border: 1px solid #707070;
            }
            QPushButton:pressed {
                background: #303030;
            }
        """)
        self.frequency_range_btn.clicked.connect(self.show_frequency_range_dialog)
        controls_row2_layout.addWidget(self.frequency_range_btn)
        
        # 监听功能按钮
        self.monitor_button = QPushButton("开启监听")
        self.monitor_button.setMaximumWidth(80)
        self.monitor_button.setCheckable(True)
        self.monitor_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)  # 启用右键菜单
        self.monitor_button.customContextMenuRequested.connect(self.show_monitor_context_menu)  # 连接右键菜单
        self.monitor_button.setStyleSheet("""
            QPushButton {
                background: #1976D2;
                border: 1px solid #2196F3;
                border-radius: 4px;
                padding: 4px 8px;
                color: white;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #1E88E5;
                border: 1px solid #42A5F5;
            }
            QPushButton:checked {
                background: #D32F2F;
                border: 1px solid #F44336;
            }
            QPushButton:pressed {
                background: #0D47A1;
            }
        """)
        # 注意：toggle_monitoring方法在主窗口中，稍后会重新连接
        controls_row2_layout.addWidget(self.monitor_button)
        
        # 添加原第一行的功能按钮（智能标注 / 清除 / 重置 / 跟随）
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
                padding: 5px 6px;
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
        controls_row2_layout.addWidget(self.auto_scale_btn)
        
        # 清除按钮
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.clear_data)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #444444;
                border: 1px solid #666666;
                border-radius: 3px;
                padding: 5px 6px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #555555;
            }
        """)
        controls_row2_layout.addWidget(clear_btn)
        
        # 重置视图按钮
        reset_view_btn = QPushButton("重置")
        reset_view_btn.clicked.connect(self.reset_view)
        reset_view_btn.setStyleSheet("""
            QPushButton {
                background-color: #006600;
                border: 1px solid #008800;
                border-radius: 3px;
                padding: 5px 6px;
                color: white;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #008800;
            }
        """)
        controls_row2_layout.addWidget(reset_view_btn)
        
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
                padding: 5px 6px;
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
        controls_row2_layout.addWidget(self.auto_follow_btn)
        
        # 分隔符（移到功能按钮之后）
        controls_row2_layout.addWidget(QLabel(" | "))

        # 显示辅助线开关
        self.guides_checkbox = QCheckBox("显示辅助线")
        self.guides_checkbox.setChecked(True)
        self.guides_checkbox.stateChanged.connect(self.on_guides_toggled)
        # 蓝色主题，提升可见性
        self.guides_checkbox.setStyleSheet(
            "QCheckBox { color: #A5D6FF; font-weight: 600; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
            "QCheckBox::indicator:unchecked { border: 1px solid #1E88E5; background: #0D47A1; }"
            "QCheckBox::indicator:checked { border: 1px solid #64B5F6; background: #2196F3; }"
        )
        controls_row2_layout.addWidget(self.guides_checkbox)

        # 状态信息显示（合并到一行）
        self.status_label = QLabel("中心: C4 | 时间: 实时 | 缩放: 1.0x | 标注: 智能 | 跟随: 开启 | 数据: 0点(0.0%)")
        self.status_label.setStyleSheet("color: #AAAAAA; font-family: monospace; font-size: 11px;")
        controls_row2_layout.addWidget(self.status_label)

        # 第二行布局添加到主布局
        main_controls_layout.addLayout(controls_row2_layout)

        return controls_group

    def on_guides_toggled(self, state):
        """控制辅助线开关"""
        try:
            checked_state = getattr(Qt, 'Checked', None)
            if checked_state is None:
                # 兼容性：PyQt6
                checked_state = Qt.CheckState.Checked
            self.guides_enabled = (state == checked_state)
        except Exception:
            # 回退：直接判断非零
            self.guides_enabled = bool(state)
        # 立即应用：创建/更新/显示或隐藏
        try:
            # 启用时确保创建并定位
            if self.guides_enabled:
                self.update_guides()
            # 同步可见性
            if self.v_guide_line is not None:
                self.v_guide_line.set_visible(self.guides_enabled)
            if self.h_guide_line is not None:
                self.h_guide_line.set_visible(self.guides_enabled)
            if hasattr(self, 'canvas'):
                self.canvas.draw_idle()
        except Exception:
            pass
    
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
        # 初始化一次辅助线
        try:
            self.update_guides()
        except Exception:
            pass
    
    def safe_clear_axis(self):
        """安全地清除轴内容，但保留彩色渐变collections和坐标轴范围"""
        # 保存现有的坐标轴范围
        saved_xlim = self.ax.get_xlim()
        saved_ylim = self.ax.get_ylim()
        
        # 保存现有的彩色渐变effects
        saved_gradient_lines = []
        saved_highlight_point = None
        # 保存批量细节点集合（避免被 clear 后丢失导致仅剩曲线无细节点）
        saved_batched_points = None
        # 保存分段曲线对象（避免被 clear 抹掉后下一帧才重绘导致的闪烁 / 丢失感）
        saved_segment_lines = []
        saved_segment_points = []
        try:
            if hasattr(self, '_segment_lines') and self._segment_lines:
                for ln in self._segment_lines:
                    if ln in self.ax.lines:
                        saved_segment_lines.append(ln)
            if hasattr(self, '_segment_points') and self._segment_points:
                for pts in self._segment_points:
                    # segment points 是 PathCollection, 位于 collections
                    if pts in self.ax.collections:
                        saved_segment_points.append(pts)
            # 批量点集合
            if hasattr(self, '_batched_points') and self._batched_points is not None:
                if self._batched_points in self.ax.collections:
                    saved_batched_points = self._batched_points
        except Exception:
            pass
        
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
        # 重要：清空后旧的辅助线对象会失去可见挂载关系，直接置空以便后续重建
        try:
            self.v_guide_line = None
            self.h_guide_line = None
            self.v_guide_glow_line = None
            self.h_guide_glow_line = None
        except Exception:
            pass
        
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

        # 恢复批量细节点集合（若存在），确保滚动/回看历史时仍有细节点
        if saved_batched_points is not None:
            try:
                if saved_batched_points not in self.ax.collections:
                    self.ax.add_collection(saved_batched_points)
                self._batched_points = saved_batched_points
                # 保守地确保可见
                try:
                    self._batched_points.set_alpha(max(0.5, getattr(self._batched_points, 'get_alpha', lambda:0.95)() or 0.95))
                    self._batched_points.set_zorder(13)
                except Exception:
                    pass
            except Exception:
                pass

        # 恢复分段曲线（保持对象身份，避免重复创建）
        if saved_segment_lines or saved_segment_points:
            try:
                for ln in saved_segment_lines:
                    if ln.axes is None:
                        self.ax.add_line(ln)
                for pts in saved_segment_points:
                    if pts not in self.ax.collections:
                        self.ax.add_collection(pts)
                # 重新赋回引用，防止被外部认为已失效
                self._segment_lines = saved_segment_lines
                self._segment_points = saved_segment_points
            except Exception as _rec_e:
                print(f"⚠️ 重新挂载分段曲线失败: {_rec_e}")

    def setup_ecg_grid(self, create_pitch_line: bool = True):
        """设置心电图式网格（智能标注）
        create_pitch_line: 是否创建/恢复数据线对象（清除后可跳过以保持空白初始状态）"""
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
        # 根据缩放级别选择可见半范围（zoom 越大显示越多音调）
        half_range = self.compute_half_range()
        # 拖动后保持中心可见
        self.clamp_y_center(half_range)
        y_start = self.y_view_center - half_range
        y_end = self.y_view_center + half_range
        # 对整体允许的物理范围做硬裁剪（假设支持 0-8 八度）
        if y_start < 0:
            shift = -y_start
            y_start += shift
            y_end += shift
        if y_end > 8:
            shift = y_end - 8
            y_start -= shift
            y_end -= shift

        # 计算显示范围（八度数）
        display_range = y_end - y_start

        # 智能标注密度控制
        if self.auto_scale:
            if display_range > 6:
                self.setup_sparse_grid(y_start, y_end)
            elif display_range > 3:
                self.setup_medium_grid(y_start, y_end)
            else:
                self.setup_dense_grid(y_start, y_end)
        else:
            self.setup_dense_grid(y_start, y_end)

        # 时间网格线
        time_start = self.time_offset
        time_end = self.time_offset + self.time_window
        for second in range(int(time_start), int(time_end) + 2):
            if time_start <= second <= time_end:
                self.ax.axvline(x=second, color=self.grid_color,
                                linestyle='--', linewidth=0.5, alpha=0.5)

        if create_pitch_line:
            # 确保pitch_line存在并恢复数据
            self.pitch_line, = self.ax.plot([], [], color=self.line_color,
                                            linewidth=self.current_linewidth, alpha=1.0, zorder=10)
            if existing_line_data is not None and len(existing_line_data[0]) > 0:
                self.pitch_line.set_data(existing_line_data[0], existing_line_data[1])
        else:
            # 标记为空线对象占位（避免其它代码访问时报错）
            self.pitch_line = None

        # X轴范围保持 16 秒窗口
        x_min = self.time_offset
        x_max = self.time_offset + self.time_window
        self.ax.set_xlim(x_min, x_max)

        # Y轴范围（音高）
        self.ax.set_ylim(y_start, y_end)

        # 纵轴漂移监控（锁定模式下）
        if getattr(self, 'freeze_y_center', False):
            drift = abs(self.y_view_center - getattr(self, '_initial_y_center', self.y_view_center))
            if drift > 0.05 and abs(drift - getattr(self, '_last_warn_y_shift', 0.0)) > 0.02:
                print(f"⚠️ [YDRIFT-DETECT] setup_ecg_grid drift={drift:.3f} center={self.y_view_center:.3f}")
                self._last_warn_y_shift = drift

        # 重建网格后，确保辅助线存在并位置正确
        try:
            self.update_guides()
        except Exception:
            pass
    
    # should_show_note_label 逻辑已被各 zoom 模式的严格规则替换
    
    def draw_interactive_note_labels(self, y_start, y_end):
        """绘制交互式音调标签 (重新精简 & 修复缩进，5.0x 保持十二平均律垂直位置)"""
        # 清理旧元素
        if hasattr(self, '_note_label_texts'):
            for t in self._note_label_texts:
                try: t.remove()
                except Exception: pass
        self._note_label_texts = []
        if hasattr(self, '_active_note_highlight_lines'):
            for ln in self._active_note_highlight_lines:
                try:
                    if ln in self.ax.lines: ln.remove()
                except Exception: pass
            self._active_note_highlight_lines.clear()
        else:
            self._active_note_highlight_lines = []
        # 保障字段
        if not hasattr(self, 'current_pitch_y'): self.current_pitch_y = 4.0
        if not hasattr(self, 'current_pitch_active'): self.current_pitch_active = False
        # 变换
        import matplotlib.transforms as mtransforms
        if not hasattr(self, '_axis_blended_transform'):
            self._axis_blended_transform = mtransforms.blended_transform_factory(self.ax.transAxes, self.ax.transData)
        label_x = self.label_x_frac
        current_center = self.current_pitch_y if self.current_pitch_active else self.y_view_center
        # 显示缓冲
        display_start = max(0.0, y_start - 1.0)
        display_end = min(8.0, y_end + 1.0)
        profile = getattr(self, '_current_zoom_profile', None) or self._get_zoom_profile()
        self._current_zoom_profile = profile
        mode = profile.get('mode')
        filt = profile['note_filter']
        fixed_mode = mode in ('zoom_0_5','zoom_0_8')
        # 遍历十二平均律位置
        for octave in range(int(display_start), int(display_end) + 1):
            for semitone in range(12):
                # 模式过滤
                if mode == 'zoom_0_5':
                    if not (semitone == 0 and 3 <= octave <= 5):
                        continue
                elif mode == 'zoom_0_8':
                    if semitone != 0: continue
                elif mode == 'zoom_1_5':
                    if semitone not in (0,5,7): continue
                elif mode == 'zoom_2_5':
                    if 3 <= octave <= 5:
                        if semitone not in (0,2,4,5,7,9,11): continue
                    else:
                        if semitone not in (0,5,7): continue
                elif mode == 'zoom_5_0':
                    pass
                else:
                    if not filt(octave, semitone): continue
                # 统一再次通过 filter 保障
                if not filt(octave, semitone):
                    continue
                y_pos = octave + semitone / 12.0
                if not (display_start <= y_pos <= display_end):
                    continue
                note_full = f"{self.note_names[semitone]}{octave}"
                distance = abs(y_pos - current_center)
                # 样式层级
                if mode == 'zoom_5_0':
                    if semitone == 0:
                        font_size = 11; alpha = 1.0; color = '#FFFF88'; font_weight = 'bold'
                    elif semitone in (2,4,5,7,9,11):
                        font_size = 10; alpha = 0.80; color = self.text_color; font_weight = 'normal'
                    else:
                        font_size = 9; alpha = 0.52; color = self.text_color; font_weight = 'normal'
                elif mode == 'zoom_0_5':
                    font_size = 12; alpha = 1.0; color = '#FFFF88'; font_weight = 'bold'
                elif mode == 'zoom_2_5' and not (3 <= octave <= 5):
                    if semitone == 0:
                        font_size = 11; alpha = 0.9; color = '#FFFFAA'; font_weight = 'bold'
                    else:
                        font_size = 9; alpha = 0.55; color = self.text_color; font_weight = 'normal'
                elif semitone == 0:
                    font_size = 11; alpha = 1.0; color = '#FFFF88'; font_weight = 'bold'
                elif semitone in (2,4,5,7,9,11):
                    font_size = 10; alpha = 0.8; color = self.text_color; font_weight = 'normal'
                else:
                    font_size = 9; alpha = 0.5; color = self.text_color; font_weight = 'normal'
                if self.current_pitch_active:
                    if distance <= 0.2:
                        font_size = max(font_size, 12); alpha = 1.0; color = '#FFD700'; font_weight = 'bold'
                    elif distance <= 0.5:
                        alpha = max(alpha, 0.9); color = '#FFC107'; font_weight = 'bold'
                    elif distance <= 1.0:
                        alpha = max(alpha, 0.8); color = '#FFEB3B'
                # 边缘淡出（固定模式主音 & 全局边界C0/C8 不淡出）
                apply_fade = True
                if (fixed_mode and semitone == 0) or (semitone == 0 and octave in (0,8)):
                    apply_fade = False
                if apply_fade:
                    vd = min(abs(y_pos - y_start), abs(y_pos - y_end))
                    if vd < 0.5:
                        alpha *= (vd / 0.5)
                if alpha < 0.2:
                    continue
                txt = self.ax.text(label_x, y_pos, note_full,
                                   fontsize=font_size, ha='right', va='center',
                                   color=color, alpha=alpha, fontweight=font_weight,
                                   transform=self._axis_blended_transform,
                                   clip_on=False, zorder=50,
                                   bbox=dict(facecolor=self.bg_color, edgecolor='none', pad=0.2, alpha=0.55))
                try:
                    base_px = self.ax.transAxes.transform((label_x,0))[0]
                    extra_px = 0
                    if mode == 'zoom_5_0':  # 水平交错：奇数半音再左移 4px
                        if semitone % 2 == 1:
                            extra_px = -4
                    new_axes_x = self.ax.transAxes.inverted().transform(
                        (base_px + self.label_left_pixel_offset + extra_px, 0))[0]
                    txt.set_x(new_axes_x)
                except Exception:
                    pass
                self._note_label_texts.append(txt)
                if self.current_pitch_active and distance <= 1.0 and self.zoom_level < 4.5:
                    ln_alpha = alpha * 0.3
                    try:
                        ln = self.ax.axhline(y=y_pos, color=color, linestyle=':', linewidth=0.8, alpha=ln_alpha, zorder=5)
                        self._active_note_highlight_lines.append(ln)
                    except Exception:
                        pass
        # 边界标签保障（滚动模式）
        if mode in ('zoom_1_5','zoom_2_5','zoom_5_0'):
            for boundary_oct in (0,8):
                if not (y_start - 0.001 <= boundary_oct <= y_end + 0.001):
                    continue
                wanted = f"C{boundary_oct}"
                if any(t.get_text() == wanted for t in self._note_label_texts):
                    continue
                txt = self.ax.text(label_x, boundary_oct, wanted,
                                   fontsize=12, ha='right', va='center',
                                   color='#FFFFAA', alpha=0.95, fontweight='bold',
                                   transform=self._axis_blended_transform,
                                   clip_on=False, zorder=60,
                                   bbox=dict(facecolor=self.bg_color, edgecolor='none', pad=0.25, alpha=0.65))
                try:
                    base_px = self.ax.transAxes.transform((label_x,0))[0]
                    new_axes_x = self.ax.transAxes.inverted().transform(
                        (base_px + self.label_left_pixel_offset, 0))[0]
                    txt.set_x(new_axes_x)
                except Exception:
                    pass
                self._note_label_texts.append(txt)
    
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
        profile = getattr(self, '_current_zoom_profile', None)
        if not profile:
            profile = self._get_zoom_profile(); self._current_zoom_profile = profile
        filt = profile['note_filter']
        for octave in range(max(0, int(y_start)), min(9, int(y_end) + 2)):
            y_oct = octave
            if y_start <= y_oct <= y_end:
                self.ax.axhline(y=y_oct, color=self.grid_color, linestyle='-', linewidth=1.2, alpha=0.75)
            for semitone in (0,2,4,5,7,9,11):
                if semitone == 0 or not filt(octave, semitone):
                    continue
                y_pos = octave + semitone / 12
                if y_start <= y_pos <= y_end:
                    self.ax.axhline(y=y_pos, color=self.grid_color, linestyle=':', linewidth=0.7, alpha=0.5)
        
        # 使用智能交互式标签
        self.draw_interactive_note_labels(y_start, y_end)
    
    def setup_dense_grid(self, y_start, y_end):
        """密集网格模式（显示所有音符）"""
        profile = getattr(self, '_current_zoom_profile', None)
        if not profile:
            profile = self._get_zoom_profile(); self._current_zoom_profile = profile
        filt = profile['note_filter']
        mode = profile.get('mode')
        for octave in range(max(0, int(y_start)), min(9, int(y_end) + 2)):
            y_oct = octave
            if y_start <= y_oct <= y_end:
                self.ax.axhline(y=y_oct, color=self.grid_color, linestyle='-', linewidth=1.0, alpha=0.65)
            for semitone in range(12):
                if semitone == 0 or not filt(octave, semitone):
                    continue
                y_pos = octave + semitone / 12
                if y_start <= y_pos <= y_end:
                    if mode == 'zoom_5_0':
                        # 5.0 模式：黑键最淡，白键次之
                        if semitone in [1,3,6,8,10]:
                            alpha = 0.18; lw = 0.4
                        elif semitone in [2,4,7,9,11]:
                            alpha = 0.36; lw = 0.5
                        else:
                            alpha = 0.5; lw = 0.55
                    elif mode == 'zoom_2_5':
                        if 3 <= octave <= 5:
                            if semitone in [2,4,7,9,11]:
                                alpha = 0.50; lw = 0.55
                            else:
                                alpha = 0.35; lw = 0.45
                        else:
                            alpha = 0.28; lw = 0.45
                    else:
                        alpha = 0.55 if semitone in [2,4,7,9,11] else 0.32
                        lw = 0.55
                    self.ax.axhline(y=y_pos, color=self.grid_color, linestyle=':', linewidth=lw, alpha=alpha)
        
        # 使用智能交互式标签
        self.draw_interactive_note_labels(y_start, y_end)
    
    def update_axis_ranges(self):
        """更新坐标轴范围（支持缩放）"""
        # 如果启用纵轴锁定（freeze_y_center），保持最初锁定的Y范围不随数据滚动变化
        if getattr(self, 'freeze_y_center', False):
            # 确定当前X轴范围（仍需随时间滚动）
            if hasattr(self, '_last_render_window'):
                x_min, x_max = self._last_render_window
            else:
                x_min = self.time_offset
                x_max = self.time_offset + self.time_window
            self.ax.set_xlim(x_min, x_max)

            # 首次锁定：记录当时的Y范围（避免之后因 zoom_level 或 center 计算被改写）
            if not hasattr(self, '_locked_y_limits') or self._locked_y_limits is None:
                self._locked_y_limits = self.ax.get_ylim()
            else:
                # 强制使用锁定范围
                self.ax.set_ylim(*self._locked_y_limits)
                try:
                    if getattr(self, 'debug_flags', {}).get('axis_log', False):
                        print(f"[AXIS LOCKED] ylim={self._locked_y_limits}")
                except Exception:
                    pass

            # 冻结模式下也刷新标签使其始终出现在当前左边界
            try:
                y_min, y_max = self.ax.get_ylim()
                self.draw_interactive_note_labels(y_min, y_max)
            except Exception:
                pass

            # 在锁定模式下无须每帧重建网格，避免闪烁；仅在显式缩放/解锁时再调用 setup_ecg_grid
            self.canvas.draw_idle()
            return

        # 正常（未锁定）模式：根据当前中心与缩放计算Y范围
        half_range = self.compute_half_range()
        profile = getattr(self, '_current_zoom_profile', None) or self._get_zoom_profile()
        # 更新当前可视半范围供拖拽换算使用
        self.y_view_range = half_range
        if profile.get('disable_v_scroll'):
            # 固定模式直接根据规范设置范围
            if profile['mode'] == 'zoom_0_8':
                y_min, y_max = 0.0, 8.0
                self.y_view_center = 4.0
            else:  # zoom_0_5
                # 保证完整覆盖 C3,C4,C5 三个标签 (含上下边界微扩展避免边界裁剪)
                y_min, y_max = 2.95, 5.05
                self.y_view_center = 4.0
        else:
            # 可滚动模式：限制中心避免超出 0-8
            self.clamp_y_center(half_range)
            y_min = self.y_view_center - half_range
            y_max = self.y_view_center + half_range
            if y_min < 0:
                shift = -y_min; y_min += shift; y_max += shift; self.y_view_center += shift
            if y_max > 8:
                shift = y_max - 8; y_min -= shift; y_max -= shift; self.y_view_center -= shift
        self.ax.set_ylim(y_min, y_max)
        try:
            if getattr(self, 'debug_flags', {}).get('axis_log', False):
                print(f"[AXIS] mode={profile.get('mode')} center={self.y_view_center:.2f} ylim=({y_min:.2f},{y_max:.2f})")
        except Exception:
            pass
        # 记录当前内部 profile 半范围与可滚动状态，便于诊断“看起来没动”问题
        try:
            if getattr(self, 'debug_flags', {}).get('axis_log', False):
                now = time.time()
                if not hasattr(self, '_last_axis_diag_log'):
                    self._last_axis_diag_log = 0.0
                if now - self._last_axis_diag_log > 1.0:  # 1s节流
                    print(f"[AXIS DIAG] half_range={half_range:.2f} disable_scroll={profile.get('disable_v_scroll')} center={self.y_view_center:.2f}")
                    self._last_axis_diag_log = now
        except Exception:
            pass

        # 更新X轴范围（时间）
        # 停止态：严格尊重 time_offset/time_window，禁止使用历史渲染窗口和平滑，以防被“拉回末尾”
        if not getattr(self, 'is_recording_active', False):
            x_min = self.time_offset
            x_max = self.time_offset + self.time_window
            try:
                self.ax.set_xlim(x_min, x_max)
            except Exception:
                pass
        else:
            # 录音态：优先使用最后渲染窗口，必要时启用平滑
            if hasattr(self, '_last_render_window'):
                x_min, x_max = self._last_render_window
            else:
                x_min = self.time_offset
                x_max = self.time_offset + self.time_window
            # 平滑滚动：超过中心时间后且自动跟随时使用平滑过渡
            try:
                smooth_active = (
                    getattr(self, 'is_recording_active', False)
                    and getattr(self, 'auto_follow', True)
                    and getattr(self, 'auto_scroll_enabled', True)
                    and not getattr(self, 'freeze_y_center', False)
                    and getattr(self, 'current_global_time', 0.0) > self.center_display_time
                )
            except Exception:
                smooth_active = False
            if smooth_active and hasattr(self, '_smooth_set_xlim'):
                # 使用更灵敏的跟随参数，限制单步位移，避免“分段感”
                try:
                    self._smooth_set_xlim(x_min, x_max, strength=float(getattr(self,'_smooth_strength',0.9)), max_step=float(getattr(self,'_smooth_max_step',0.05)))
                except Exception:
                    self.ax.set_xlim(x_min, x_max)
            else:
                self.ax.set_xlim(x_min, x_max)

        # 重新设置网格（无论是否有数据都要设置）
        self.setup_ecg_grid()

        # 强制刷新画布以确保时间轴标签正确显示
        self.canvas.draw_idle()

    # ================= Y轴锁定控制 =================
    def lock_y_axis(self):
        """显式锁定当前Y轴范围，防止后续被自动缩放或跟随修改"""
        self.freeze_y_center = True
        self._locked_y_limits = self.ax.get_ylim()
        self._initial_y_center = (self._locked_y_limits[0] + self._locked_y_limits[1]) / 2.0
        print(f"🔒 锁定Y轴: {self._locked_y_limits}")

    def unlock_y_axis(self):
        """解除Y轴锁定，允许根据中心/缩放重新计算"""
        prev_limits = getattr(self, '_locked_y_limits', None)
        self.freeze_y_center = False
        self._locked_y_limits = None
        print(f"🔓 解锁Y轴 (之前={prev_limits})，即将重新计算网格")
        # 解除锁定后立刻重建网格以反映当前中心和 zoom
        self.update_axis_ranges()
    
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
        
        # 垂直拖拽调整音高范围（若允许）
        prof = getattr(self, '_current_zoom_profile', None) or self._get_zoom_profile()
        if not prof.get('disable_v_scroll'):
            if not hasattr(self, 'y_view_range'):
                self.y_view_range = self.compute_half_range()
            dy_data = -dy / fig_height * (self.y_view_range * 2)
            new_y_center = self.drag_start_y_center + dy_data
            self.y_view_center = max(1.0, min(7.0, new_y_center))
        
        # 水平拖拽调整时间偏移
        dx_data = -dx / fig_width * self.time_window * 1.5  # 负号实现反向拖拽
        new_time_offset = self.drag_start_time_offset + dx_data
        self.time_offset = max(0, min(self.max_history_time - self.time_window, new_time_offset))
        
        # 更新显示（轻量：仅设置 xlim，避免重建网格导致粘滞感）
        try:
            x_min = self.time_offset
            x_max = self.time_offset + self.time_window
            # 手动拖拽：直接设置，避免“跟随平滑器”带来的滞后
            self.ax.set_xlim(x_min, x_max)
        except Exception:
            pass
        # 录音中：轻量刷新批量细节点；停止后：空白区域快速路径，返回数据区再完整重绘
        if getattr(self, 'is_recording_active', False):
            self._refresh_batched_points_for_current_xlim()
        else:
            try:
                # 快速判断：若当前视口完全在最后数据点之后，则走轻路径避免重帧
                last_t = None
                try:
                    last_t = self.time_data[-1] if self.time_data else None
                except Exception:
                    last_t = None
                x_min = self.time_offset
                x_max = self.time_offset + self.time_window
                in_blank_future = (last_t is not None) and (x_min > last_t + 1e-3)
                # 完全空工程（无数据）也视为空白区域
                if (last_t is None) or in_blank_future:
                    # 轻路径：仅更新辅助线/滚动条/画布
                    try:
                        self.update_guides()
                    except Exception:
                        pass
                else:
                    # 回到数据区：强制一次完整重绘，保证逐段散点与线条同步
                    self._force_redraw_on_next_update = True
                    self.update_display()
            except Exception:
                pass
        if hasattr(self, 'canvas'):
            self.canvas.draw_idle()
        
        # 同步更新滚动条
        self.update_scrollbars()
    
    def on_mouse_scroll(self, event):
        """鼠标滚轮事件（上下移动音高视图）"""
        if event.inaxes != self.ax:
            return
        prof = getattr(self, '_current_zoom_profile', None) or self._get_zoom_profile()
        if prof.get('disable_v_scroll'):
            return  # 不允许滚动
        
        # 滚轮上下移动音高视图中心
        scroll_sensitivity = 0.3  # 滚动敏感度
        if event.step > 0:  # 向上滚动
            delta_y = scroll_sensitivity
        else:  # 向下滚动
            delta_y = -scroll_sensitivity
        
        # 更新音高视图中心
        prev_center = self.y_view_center
        new_y_center = self.y_view_center + delta_y
        self.y_view_center = max(0.5, min(7.5, new_y_center))
        try:
            print(f"[MWHEEL] mode={prof.get('mode')} delta={delta_y:+.2f} center={self.y_view_center:.3f} Δ={self.y_view_center-prev_center:+.3f}")
        except Exception:
            pass
        self._user_overrode_center = True
        
        # 🔥 完全按照vertical_scroll的模式处理，确保一致性
        # 先更新坐标轴范围
        self.update_axis_ranges()
        
        # 🔥 修复音调线消失问题：强制重新绘制音调线数据
        if len(self.pitch_data) > 0:
            # 强制更新显示，确保音调线在滚轮滚动后重新绘制
            self._force_redraw_on_next_update = True
            # 🔥 关键修复：设置一个更持久的重绘标志，防止定时器覆盖
            self._scroll_triggered_redraw = True
            self.update_display()
        else:
            self.canvas.draw_idle()
        
        # 同步更新垂直滚动条位置
        if hasattr(self, 'v_scrollbar'):
            # 将y_view_center (1.5-6.5) 映射到滚动条范围 (0-100)
            scroll_value = int((self.y_view_center - 1.5) / 5.0 * 100)
            self.v_scrollbar.blockSignals(True)  # 阻止信号避免循环
            self.v_scrollbar.setValue(100 - scroll_value)  # 反转，顶部对应高音
            self.v_scrollbar.blockSignals(False)
        
        # 🔥 阻止事件传播，避免与matplotlib默认滚轮行为冲突
        return True
    
    def on_vertical_scroll(self, value):
        """垂直滚动条事件（控制音高视图中心, 遵从 zoom profile 的 disable_v_scroll）"""
        prof = getattr(self, '_current_zoom_profile', None) or self._get_zoom_profile()
        if prof.get('disable_v_scroll'):
            # 强制保持其指定中心
            fc = prof.get('force_center', 4.0)
            if self.y_view_center != fc:
                self.y_view_center = fc
                self.update_axis_ranges()
            self.update_scrollbars()
            return
        half_range = self.compute_half_range()
        min_center = half_range
        max_center = 8.0 - half_range
        normalized_value = (100 - value) / 100.0
        self.y_view_center = min_center + normalized_value * (max_center - min_center)
        self._user_overrode_center = True
        try:
            print(f"[VSCROLL] value={value} center={self.y_view_center:.3f} half={half_range:.2f} bounds=({min_center:.2f},{max_center:.2f}) mode={prof.get('mode')}")
        except Exception:
            pass
        self.update_axis_ranges()
        # 立即同步以避免下一次刷新覆盖视觉效果
        self.update_scrollbars()
        try:
            ylim = self.ax.get_ylim()
            print(f"[VSCROLL AXIS] mode={prof.get('mode')} ylim={ylim}")
        except Exception:
            pass
        if len(self.pitch_data) > 0:
            self._force_redraw_on_next_update = True
            self.update_display()
        else:
            self.canvas.draw_idle()
        # 更新辅助线位置
        try:
            self.update_guides()
        except Exception:
            pass
    
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
        
        # 🔥 修复音调线显示问题：强制重新绘制数据
        self._force_redraw_on_next_update = True
        
        # 更新显示（轻量：直接设置 xlim + 刷新批量细节点，避免每次重建网格造成卡顿）
        try:
            x_min = self.time_offset
            x_max = self.time_offset + self.time_window
            # 滚动条为明确的用户导航：直接设置，避免粘滞
            self.ax.set_xlim(x_min, x_max)
        except Exception:
            pass
        if getattr(self, 'is_recording_active', False):
            self._refresh_batched_points_for_current_xlim()
        else:
            try:
                # 快速判断：若当前视口完全在最后数据点之后，则走轻路径避免重帧
                last_t = None
                try:
                    last_t = self.time_data[-1] if self.time_data else None
                except Exception:
                    last_t = None
                x_min = self.time_offset
                x_max = self.time_offset + self.time_window
                in_blank_future = (last_t is not None) and (x_min > last_t + 1e-3)
                if (last_t is None) or in_blank_future:
                    try:
                        self.update_guides()
                    except Exception:
                        pass
                else:
                    self._force_redraw_on_next_update = True
                    self.update_display()
            except Exception:
                pass
        if hasattr(self, 'canvas'):
            self.canvas.draw_idle()
        # 更新辅助线位置
        try:
            self.update_guides()
        except Exception:
            pass
    
    def re_enable_auto_scroll(self):
        """重新启用自动滚动"""
        self.auto_scroll_enabled = True
        print("🔄 自动滚动已重新启用")
    
    def update_scrollbars(self):
        """更新滚动条位置以同步当前视图状态"""
        if hasattr(self, 'v_scrollbar'):
            prof = getattr(self, '_current_zoom_profile', None) or self._get_zoom_profile()
            half_range = self.compute_half_range()
            if prof.get('disable_v_scroll'):
                # 0.5x 需固定显示 C3-C5; 0.8x 固定全区中心
                fc = prof.get('force_center', 4.0)
                self.y_view_center = fc
                self.v_scrollbar.setEnabled(False)
                self.v_scrollbar.blockSignals(True)
                self.v_scrollbar.setValue(50)
                self.v_scrollbar.blockSignals(False)
            else:
                self.v_scrollbar.setEnabled(True)
                min_center = half_range
            if getattr(self, 'v_guide_glow_line', None) is not None:
                self.v_guide_glow_line.set_visible(self.guides_enabled)
            if getattr(self, 'h_guide_glow_line', None) is not None:
                self.h_guide_glow_line.set_visible(self.guides_enabled)
                max_center = 8.0 - half_range
                # 不主动改写 center，只在极端越界时校正
                changed = False
                if self.y_view_center < min_center:
                    self.y_view_center = min_center; changed = True
                elif self.y_view_center > max_center:
                    self.y_view_center = max_center; changed = True
                if max_center > min_center:
                    ratio = (self.y_view_center - min_center) / (max_center - min_center)
                else:
                    ratio = 0.5
                scroll_value = int((1.0 - ratio) * 100)
                try:
                    sig = (prof.get('mode'), round(self.y_view_center,2), half_range, scroll_value, changed)
                    now_ts = time.time()
                    if sig != self._last_scroll_signature or (now_ts - self._last_scroll_log_time) > 1.5:
                        self._log_rate_limit('scroll_sync', f"[SCROLLBAR SYNC] mode={prof.get('mode')} center={self.y_view_center:.2f} half={half_range} val={scroll_value} changed={changed}", interval=0.5, burst=2)
                        self._last_scroll_signature = sig
                        self._last_scroll_log_time = now_ts
                except Exception:
                    pass
                self.v_scrollbar.blockSignals(True)
                self.v_scrollbar.setValue(scroll_value)
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
        """添加音高数据（支持历史数据存储和断续音调曲线）"""
        try:
            add_receive_time = time.time()
            frequency = pitch_data.get('frequency', 0)
            confidence = pitch_data.get('confidence', 0)
            timestamp = pitch_data.get('timestamp', time.time())
            note_info = pitch_data.get('note_info', {})
            has_pitch = pitch_data.get('has_pitch', frequency > 0)
            
            # 计算全局时间（从开始到现在的总时间）- 修复NoneType错误
            if not hasattr(self, 'start_time') or self.start_time is None:
                self.start_time = timestamp
                print(f"🕐 设置开始时间: {self.start_time}")
            
            global_time = timestamp - self.start_time
            
            # 总是更新当前全局时间，保持时间轴推进
            self.current_global_time = global_time
            
            if has_pitch and frequency > 0:
                # 若清除后尚未重建网格，先构建一次
                if getattr(self, '_needs_grid_rebuild', False):
                    try:
                        self.setup_ecg_grid(create_pitch_line=True)
                        self._needs_grid_rebuild = False
                    except Exception as _rg_e:
                        print(f"⚠️ 网格重建失败: {_rg_e}")
                if getattr(self, '_suppress_updates_until_new_data', False):
                    self._suppress_updates_until_new_data = False
                # 🔥 修复音高精度丢失问题：保持完整的小数精度
                # 转换频率到Y轴位置（保持连续精度，不量化到半音）
                midi_number = 69 + 12 * np.log2(frequency / 440)  # A4 = 440Hz = MIDI 69
                # 🎯 关键修复：保持完整的MIDI音符精度，不进行整数化
                octave_exact = midi_number / 12 - 1  # 保持小数精度的八度
                y_pos = octave_exact  # 直接使用精确的八度值作为Y轴位置
                
                # 🔥 调试：每50个点打印一次精度对比
                if len(self.pitch_data) % 50 == 0:
                    old_octave = int(midi_number // 12) - 1
                    old_semitone = int(midi_number % 12)
                    old_y_pos = old_octave + old_semitone / 12
                    if getattr(self, 'debug_flags', {}).get('pitch_precision_log', False):
                        print(f"🎵 音高精度修复: {frequency:.2f}Hz → 原始Y={old_y_pos:.2f}, 精确Y={y_pos:.4f} (差值={abs(y_pos-old_y_pos):.4f})")
                
                # 只有在有音高时才添加到音高数据中
                self.pitch_data.append(y_pos)
                self.time_data.append(global_time)
                self.confidence_data.append(confidence)
                self.note_data.append(note_info)
                
                # 更新当前音高状态（用于交互式标注）
                self.current_pitch_y = y_pos
                self.current_pitch_active = True
                self.last_pitch_time = time.time()  # 记录最后活跃时间
                # 记录最后一次有效音高用于横向辅助线
                self.last_active_pitch_y = y_pos
                
                # 调试信息（每10个数据点打印一次）
                if len(self.pitch_data) % 10 == 0:
                    print(f"✅ 音高数据点: {len(self.pitch_data)}, 最新: {y_pos:.2f}, 时间: {global_time:.2f}s")
                
                # 自动跟随功能（只在有音高且未锁定纵轴时调整音高轴）
                if self.auto_follow and self.auto_scroll_enabled and not getattr(self, 'freeze_y_center', False):
                    # 音高轴自动跟随（平滑移动到新音高区域）
                    # 新缩放模型：compute_half_range() 已直接返回当前可见半范围
                    current_display_range = self.compute_half_range()
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
                        shift = abs(self.y_view_center - old_center)
                        if shift > 0.01:
                            self.update_axis_ranges()
                            if shift > 0.25:
                                print(f"⚠️ [YDRIFT] auto-follow center shift={shift:.2f} new_center={self.y_view_center:.2f}")
            else:
                # 无音高时，仍然更新时间相关状态，但不添加音高数据点
                # 这样音调线条会断开，但时间轴继续推进
                self.current_pitch_active = False
                # 抑制期不进行显示刷新
                if getattr(self, '_suppress_updates_until_new_data', False):
                    return
                
                # 调试信息（每200帧打印一次）
                if hasattr(self, '_no_pitch_counter'):
                    self._no_pitch_counter += 1
                    if self._no_pitch_counter % 200 == 0:
                        audio_rms = pitch_data.get('audio_rms', 0)
                        print(f"⏸️ 无音高时间: {global_time:.2f}s (RMS: {audio_rms:.4f}) - 时间轴继续推进")
                else:
                    self._no_pitch_counter = 1
                    print("⏸️ 进入无音高模式 - 时间轴继续，音调线断开")
            
            # 时间轴自动跟随（无论是否有音高都要处理）
            if self.auto_follow and self.auto_scroll_enabled:
                # 新的滚动逻辑：第8秒之前不滚动，第8秒后开始滚动
                if global_time <= self.center_display_time:
                    # 前8秒：时间偏移保持为0，显示从0到16秒的内容
                    self.time_offset = 0.0
                else:
                    # 第8秒后：开始滚动，保持音调曲线在屏幕中央生成
                    # 计算需要的时间偏移，使当前时间点在屏幕中央（8秒位置）
                    if not hasattr(self, '_auto_scroll_started'):
                        print(f"▶ 自动滚动启动: t={global_time:.2f}s (center={self.center_display_time}s)")
                        self._auto_scroll_started = True
                    self.time_offset = global_time - self.center_display_time
                    
                    # 确保时间偏移不超过最大历史时间限制
                    max_offset = max(0, self.max_history_time - self.time_window)
                    self.time_offset = min(self.time_offset, max_offset)
                    
                    # 实时更新滚动条位置，确保滚动条与时间偏移同步
                    self.update_scrollbars()

            # 触发一次即时刷新（去除0.5秒后批量突显）
            # === 增量刷新节流与分段快速追加 ===
            # 仅记录新增点，由 update_display 中的增量逻辑处理，避免短时间重复全量重算
            if not hasattr(self, '_new_points_since_last_draw'):
                self._new_points_since_last_draw = 0
            self._new_points_since_last_draw += 1
            # Push 策略：若距离上次重帧超出最小间隔则立即重绘，否则仍合并
            now_push = add_receive_time
            if not hasattr(self, '_last_heavy_redraw_time'):
                self._last_heavy_redraw_time = 0.0
            gap = now_push - getattr(self, '_last_heavy_redraw_time', 0.0)
            # 按模式自适应：高性能模式更积极触发有新点时的重绘
            try:
                from src.audio_processing.performance_manager import PerformanceMode
                mode = getattr(self, 'current_performance_mode', None)
                push_factor = float(getattr(self, '_push_heavy_factor', 0.95))
            except Exception:
                push_factor = 0.95
            if gap >= self._min_heavy_interval * push_factor:
                self._pending_instant_update = False
                try:
                    self.update_display()
                except Exception as _e_push:
                    print(f"⚠️ push重绘失败: {_e_push}")
            else:
                if not hasattr(self, '_pending_instant_update') or not self._pending_instant_update:
                    self._pending_instant_update = True
                    QTimer.singleShot(0, self._instant_refresh)

            # 轻量更新辅助线（不强制重绘主曲线）
            try:
                self.update_guides()
            except Exception:
                pass

            # 诊断: 记录进入但尚未显示的点数
            self._diag_pending_points += 1
            # 暂存接收时间，用于在 update_display 中计算延迟
            self._last_add_pitch_receive_time = add_receive_time
                
        except Exception as e:
            print(f"添加音高数据错误: {e}")

    def _instant_refresh(self):
        """即时刷新封装，合并短时间内的多次 add 调用。"""
        try:
            self._pending_instant_update = False
            self.update_display()
        except Exception:
            pass

    # --- 平滑时间轴工具 ---
    def _smooth_set_xlim(self, target_start: float, target_end: float, strength: float = 0.35, max_step: float = 0.12):
        """
        将当前xlim以插值方式逼近目标，减少跳变。strength∈(0,1] 越大响应越快；
        max_step 限制每次最大移动（秒），避免大跨度瞬移。
        """
        try:
            if not hasattr(self, 'ax'):
                return
            cur_start, cur_end = self.ax.get_xlim()
            # 首次或无平滑历史：直接设置并记录
            if self._smoothed_xlim is None:
                self._smoothed_xlim = (cur_start, cur_end)
            s_cur, e_cur = self._smoothed_xlim
            # 目标与当前差值
            ds = target_start - s_cur
            de = target_end - e_cur
            # 限制单步最大位移
            step_s = max(-max_step, min(max_step, ds * strength))
            step_e = max(-max_step, min(max_step, de * strength))
            s_new = s_cur + step_s
            e_new = e_cur + step_e
            # 若已接近目标（误差<1ms），直接落到目标
            if abs(target_start - s_new) < 0.001 and abs(target_end - e_new) < 0.001:
                s_new, e_new = target_start, target_end
            # 应用并缓存
            if abs(cur_start - s_new) > 1e-6 or abs(cur_end - e_new) > 1e-6:
                self.ax.set_xlim(s_new, e_new)
                if hasattr(self, 'canvas'):
                    self.canvas.draw_idle()
            self._smoothed_xlim = (s_new, e_new)
        except Exception:
            # 退回直接设置
            try:
                self.ax.set_xlim(target_start, target_end)
                if hasattr(self, 'canvas'):
                    self.canvas.draw_idle()
                self._smoothed_xlim = (target_start, target_end)
            except Exception:
                pass

    def _fast_update_tick(self):
        """高频轻量刷新：无新点时仅驱动轻量帧以保持平滑滚动。"""
        if not getattr(self, 'is_recording_active', False):
            return
        now_t = time.time()
        # 简单去抖：避免在极短间隔内重复触发
        if hasattr(self, '_last_fast_tick') and (now_t - self._last_fast_tick) < (self.fast_update_interval_ms/1000.0 * 0.8):
            return
        # 若有新点，fast tick 不做额外事情（push 已经触发）
        if getattr(self, '_new_points_since_last_draw', 0) == 0:
            # 距离最近一次重帧时间过短则跳过，避免过度调用（更保守，降低CPU占用）
            if hasattr(self, '_last_heavy_redraw_time') and (now_t - self._last_heavy_redraw_time) < self._min_heavy_redraw_time_threshold():
                return
        try:
            self.update_display()
            # 轻量 tick 后主动触发一次 draw_idle，提升感知流畅
            if hasattr(self, 'canvas'):
                self.canvas.draw_idle()
        except Exception as e:
            if hasattr(self, 'debug_flags') and self.debug_flags.get('perf_verbose'):
                print(f"⚠️ fast tick 异常: {e}")
        self._last_fast_tick = now_t

    def _min_heavy_redraw_time_threshold(self):
        """返回轻量帧跳过重绘的最小时间阈值，随模式微调。"""
        try:
            from src.audio_processing.performance_manager import PerformanceMode
            mode = getattr(self, 'current_performance_mode', None)
            base = float(getattr(self, '_min_heavy_interval', 0.028))
            if mode == PerformanceMode.HIGH_PERFORMANCE:
                return base * 0.70  # 更频繁允许轻量帧，但仍避免过密
            if mode == PerformanceMode.QUIET:
                return base * 0.90  # 安静模式更倾向跳过
            return base * 0.80
        except Exception:
            return float(getattr(self, '_min_heavy_interval', 0.028)) * 0.80

    def _refresh_batched_points_for_current_xlim(self):
        """轻量刷新：根据当前 xlim 更新批量细节点集合，用于手动水平滚动/拖拽时保持细节点可见。"""
        try:
            # 录音停止后：使用分段散点高保真显示，不再使用批量集合
            if not getattr(self, 'is_recording_active', False):
                return
            if not getattr(self, '_use_batched_points', False):
                return
            if not hasattr(self, 'ax') or self.ax is None:
                return
            # 确保集合存在并已挂载
            detail_rgb = tuple(c/255.0 for c in (255, 255, 255))
            if not hasattr(self, '_batched_points') or self._batched_points is None:
                self._batched_points = self.ax.scatter([], [], s=16, c=[detail_rgb], alpha=0.0, linewidths=0, zorder=13)
            elif self._batched_points not in getattr(self.ax, 'collections', []):
                try:
                    self.ax.add_collection(self._batched_points)
                except Exception:
                    pass
            # 仅当已有分段数据时更新
            if not hasattr(self, '_segments') or not self._segments:
                return
            try:
                x0, x1 = self.ax.get_xlim()
            except Exception:
                x0, x1 = self.time_offset, self.time_offset + self.time_window
            import numpy as np
            chunks = []
            for (seg_times, seg_pitches) in self._segments:
                if not seg_times:
                    continue
                for t, y in zip(seg_times, seg_pitches):
                    if x0 <= t <= x1:
                        chunks.append((t, y))
            if chunks:
                arr = np.asarray(chunks, dtype=float)
                # 限制点数，避免过度绘制
                max_pts = int(getattr(self, '_batched_points_cap_heavy', 1200))
                if arr.shape[0] > max_pts:
                    step = int(np.ceil(arr.shape[0] / max_pts))
                    arr = arr[::step]
                # 统一计算尺寸
                def _calc_marker_size():
                    base_w = float(getattr(self, 'current_linewidth', 0.6))
                    zoom = float(getattr(self, 'zoom_level', 1.0))
                    diameter = max(1.6, min(base_w * 3.2 / (0.6 if zoom < 1 else min(zoom, 3.0)), 4.0))
                    return diameter ** 2
                s_val_global = _calc_marker_size()
                self._batched_points.set_offsets(arr)
                self._batched_points.set_sizes([s_val_global] * len(arr))
                self._batched_points.set_alpha(0.95)
                self._batched_points.set_zorder(13)
            else:
                # 无可见点则隐藏
                try:
                    import numpy as np
                    self._batched_points.set_offsets(np.empty((0, 2)))
                except Exception:
                    pass
                self._batched_points.set_alpha(0.0)
        except Exception:
            # 轻量刷新失败不影响主流程
            pass

    def update_guides(self):
        """更新或创建纵向/横向辅助线（主线+柔光）位置与可见性。"""
        try:
            if not hasattr(self, 'ax'):
                return
            # 纵向位置：≤8s 跟随当前时间，>8s 时严格居中（基于当前 xlim 中点，避免与 time_offset 误差）
            time_start, time_end = self.ax.get_xlim() if hasattr(self, 'ax') else (self.time_offset, self.time_offset + self.time_window)
            cur_t = getattr(self, 'current_global_time', 0.0)
            if cur_t > self.center_display_time:
                v_x = (time_start + time_end) * 0.5
            else:
                v_x = min(max(time_start, cur_t), time_end)

            # 横向位置：最后一次有效音高（静音保持不变），默认以当前中心代替
            if self.last_active_pitch_y is None:
                self.last_active_pitch_y = getattr(self, 'current_pitch_y', self.y_view_center)

            # 纵向：柔光底线
            need_new_v_glow = (
                getattr(self, 'v_guide_glow_line', None) is None or
                getattr(getattr(self, 'v_guide_glow_line', None), 'axes', None) is None or
                self.v_guide_glow_line not in getattr(self.ax, 'lines', [])
            )
            if need_new_v_glow:
                self.v_guide_glow_line = self.ax.axvline(
                    x=v_x, color=self.guide_v_color, linestyle='-',
                    linewidth=self.guide_linewidth_glow, alpha=self.guide_alpha_glow,
                    zorder=80, visible=self.guides_enabled
                )
                try:
                    self.v_guide_glow_line.set_solid_capstyle('round')
                except Exception:
                    pass
            else:
                try:
                    self.v_guide_glow_line.set_xdata([v_x, v_x])
                    self.v_guide_glow_line.set_visible(self.guides_enabled)
                    self.v_guide_glow_line.set_zorder(80)
                except Exception:
                    pass

            # 纵向：主虚线
            need_new_v = (
                self.v_guide_line is None or
                getattr(self.v_guide_line, 'axes', None) is None or
                self.v_guide_line not in getattr(self.ax, 'lines', [])
            )
            if need_new_v:
                self.v_guide_line = self.ax.axvline(
                    x=v_x, color=self.guide_v_color, linestyle='--',
                    linewidth=self.guide_linewidth_main, alpha=self.guide_alpha_main,
                    zorder=90, visible=self.guides_enabled
                )
                try:
                    self.v_guide_line.set_linestyle((0, self.guide_dash_pattern))
                except Exception:
                    try:
                        self.v_guide_line.set_dashes(self.guide_dash_pattern)
                    except Exception:
                        pass
                try:
                    self.v_guide_line.set_solid_capstyle('round')
                except Exception:
                    pass
            else:
                try:
                    self.v_guide_line.set_xdata([v_x, v_x])
                    self.v_guide_line.set_visible(self.guides_enabled)
                    self.v_guide_line.set_zorder(90)
                except Exception:
                    pass

            # 横向：柔光底线
            need_new_h_glow = (
                getattr(self, 'h_guide_glow_line', None) is None or
                getattr(getattr(self, 'h_guide_glow_line', None), 'axes', None) is None or
                self.h_guide_glow_line not in getattr(self.ax, 'lines', [])
            )
            if need_new_h_glow:
                self.h_guide_glow_line = self.ax.axhline(
                    y=self.last_active_pitch_y, color=self.guide_h_color, linestyle='-',
                    linewidth=self.guide_linewidth_glow, alpha=self.guide_alpha_glow,
                    zorder=80, visible=self.guides_enabled
                )
                try:
                    self.h_guide_glow_line.set_solid_capstyle('round')
                except Exception:
                    pass
            else:
                try:
                    self.h_guide_glow_line.set_ydata([self.last_active_pitch_y, self.last_active_pitch_y])
                    self.h_guide_glow_line.set_visible(self.guides_enabled)
                    self.h_guide_glow_line.set_zorder(80)
                except Exception:
                    pass

            # 横向：主虚线
            need_new_h = (
                self.h_guide_line is None or
                getattr(self.h_guide_line, 'axes', None) is None or
                self.h_guide_line not in getattr(self.ax, 'lines', [])
            )
            if need_new_h:
                self.h_guide_line = self.ax.axhline(
                    y=self.last_active_pitch_y, color=self.guide_h_color, linestyle='--',
                    linewidth=self.guide_linewidth_main, alpha=self.guide_alpha_main,
                    zorder=90, visible=self.guides_enabled
                )
                try:
                    self.h_guide_line.set_linestyle((0, self.guide_dash_pattern))
                except Exception:
                    try:
                        self.h_guide_line.set_dashes(self.guide_dash_pattern)
                    except Exception:
                        pass
                try:
                    self.h_guide_line.set_solid_capstyle('round')
                except Exception:
                    pass
            else:
                try:
                    self.h_guide_line.set_ydata([self.last_active_pitch_y, self.last_active_pitch_y])
                    self.h_guide_line.set_visible(self.guides_enabled)
                    self.h_guide_line.set_zorder(90)
                except Exception:
                    pass

            # 轻触发重绘，确保立即可见
            if hasattr(self, 'canvas'):
                try:
                    self.canvas.draw_idle()
                except Exception:
                    pass
        except Exception:
            pass
    
    def update_time_axis(self):
        """更新时间轴（支持断续音调曲线模式）"""
        try:
            if not self.is_recording_active:
                return
            
            # 计算当前全局时间
            current_time = time.time()
            if self.start_time is None:
                self.start_time = current_time
            
            self.current_global_time = current_time - self.start_time
            
            # 如果有新音高数据，记录最后音高时间
            if len(self.pitch_data) > 0:
                latest_pitch_time = self.time_data[-1] if self.time_data else 0
                if latest_pitch_time > self.last_pitch_time:
                    self.last_pitch_time = latest_pitch_time
            
            # 检查是否长时间没有音高数据（超过0.5秒认为是静音/换气）
            time_since_last_pitch = self.current_global_time - self.last_pitch_time
            
            # 无论是否有音高数据，都要更新时间相关的UI元素（仅录音中自动跟随）
            if self.is_recording_active and self.auto_follow and self.auto_scroll_enabled:
                # 新的滚动逻辑：第8秒之前不滚动，第8秒后开始滚动
                if self.current_global_time <= self.center_display_time:
                    # 前8秒：时间偏移保持为0，显示从0到16秒的内容
                    self.time_offset = 0.0
                else:
                    # 第8秒后：开始滚动，保持时间轴在屏幕中央生成
                    if not hasattr(self, '_auto_scroll_started'):
                        print(f"▶ 自动滚动启动: t={self.current_global_time:.2f}s (center={self.center_display_time}s)")
                        self._auto_scroll_started = True
                    self.time_offset = self.current_global_time - self.center_display_time
                    
                    # 确保时间偏移不超过最大历史时间限制
                    max_offset = max(0, self.max_history_time - self.time_window)
                    self.time_offset = min(self.time_offset, max_offset)
                
                # 更新滚动条位置
                self.update_scrollbars()
                # 同步辅助线位置
                try:
                    self.update_guides()
                except Exception:
                    pass
            
            # 即使没有新音高数据，也要刷新显示（显示时间轴推进）
            if time_since_last_pitch > 0.1:  # 超过100ms没有音高数据
                # 不更新音高数据，但更新轴范围显示时间推进
                try:
                    if hasattr(self, 'ax') and self.main_plot_area == self.canvas:
                        # 更新X轴范围以显示当前时间窗口
                        time_start = self.time_offset
                        time_end = self.time_offset + self.time_window
                        
                        current_xlim = self.ax.get_xlim()
                        # 使用平滑过渡，避免“分段移动”的观感
                        try:
                            self._smooth_set_xlim(time_start, time_end, strength=float(getattr(self,'_smooth_strength',0.9)), max_step=float(getattr(self,'_smooth_max_step',0.05)))
                        except Exception:
                            if abs(current_xlim[0] - time_start) > 0.02 or abs(current_xlim[1] - time_end) > 0.02:
                                self.ax.set_xlim(time_start, time_end)
                                self.canvas.draw_idle()
                        try:
                            self.update_guides()
                        except Exception:
                            pass
                except Exception as e:
                    # 静默处理绘制错误
                    pass
                    
        except Exception as e:
            print(f"时间轴更新错误: {e}")
    
    def start_time_tracking(self):
        """开始时间追踪（录音开始时调用）"""
        self.is_recording_active = True
        self.start_time = time.time()
        self.current_global_time = 0.0
        self.last_pitch_time = 0
        self.time_update_timer.start(self.time_update_interval)
        print("🕐 开始时间轴追踪（支持断续音调曲线）")
    
    def stop_time_tracking(self):
        """停止时间追踪（录音停止时调用）"""
        self.is_recording_active = False
        self.time_update_timer.stop()
        print("⏹️ 停止时间轴追踪")

    def update_display(self):
        """更新显示（支持历史数据查看和断续音调曲线）"""
        # 重入保护：多定时器可能同时触发，避免并发重绘造成状态不一致/抖动
        if getattr(self, '_in_update_display', False):
            return
        self._in_update_display = True
        if getattr(self, '_suppress_updates_until_new_data', False):
            self._in_update_display = False
            return
        if len(self.pitch_data) == 0:
            self._in_update_display = False
            return
        
        try:
            t_start = time.time()
            now = t_start
            # 帧调试标志（集中初始化，供后续使用）
            frame_trace = bool(getattr(self, 'debug_flags', {}).get('frame_trace', False))
            perf_verbose = bool(getattr(self, 'debug_flags', {}).get('perf_verbose', False))
            frame_cpu_start = t_start
            if frame_trace:
                print("[FRAME] ==== 新帧 begin t={:.3f}s total_pts={} new_pts={} ====".format(
                    (now - getattr(self, 'start_time', now)) if getattr(self, 'start_time', None) else now % 1000,
                    len(self.pitch_data), getattr(self, '_new_points_since_last_draw', 0)))
            # 统计刷新间隔（包含轻量帧）
            # 修复: 初始化时属性已存在但值为 None（__init__ 里设为 None），原逻辑使用 hasattr 会进入减法路径导致 now - None 异常
            if (not hasattr(self, '_diag_last_display_time')) or (self._diag_last_display_time is None):
                self._diag_last_display_time = now
            else:
                interval = now - self._diag_last_display_time
                # 只记录合理区间，过滤极端长间隔（避免停止后噪声影响统计）
                if 0 <= interval < 5.0:
                    self._diag_display_intervals.append(interval)
                self._diag_last_display_time = now
            if not hasattr(self, '_total_frame_count'):
                self._total_frame_count = 0
            self._total_frame_count += 1
            # =============== 轻量/重帧策略 (抗卡顿强化) ===============
            if not hasattr(self, '_last_heavy_redraw_time'):
                self._last_heavy_redraw_time = 0.0
            if not hasattr(self, '_light_frame_count'):
                self._light_frame_count = 0
            if not hasattr(self, '_aggressive_mode'):
                self._aggressive_mode = True  # 激进平滑模式开关
            if not hasattr(self, '_heavy_redraw_base'):
                self._heavy_redraw_base = 0.035
            # 激进模式进一步压缩基线
            base_target = 0.020 if self._aggressive_mode else 0.030
            # 若存在最近的自适应压缩历史则平滑过渡
            self._heavy_redraw_base = (self._heavy_redraw_base*0.65 + base_target*0.35)
            adaptive_factor = 1.0
            if self._draw_timing_samples:
                recent = list(self._draw_timing_samples)[-30:] if len(self._draw_timing_samples) > 30 else list(self._draw_timing_samples)
                avg_draw = sum(recent)/len(recent)
                if avg_draw > 8:
                    adaptive_factor = 1.55
                elif avg_draw < 3 and getattr(self, '_stutter_events', 0) > 5:
                    adaptive_factor = 0.72  # 更积极收紧但更稳
            heavy_interval_threshold = self._heavy_redraw_base * adaptive_factor
            # 最近延迟窗口（避免全历史拉高平均）
            if self._diag_add_to_display_latencies:
                _lat_list = list(self._diag_add_to_display_latencies)[-120:]
                sl = sorted(_lat_list)
                p90_lat = sl[int(0.9*len(sl))-1] if len(sl) > 5 else 0
                p50_lat = sl[int(0.5*len(sl))-1] if len(sl) > 1 else 0
                # 若 p90 延迟 >50ms 或 p50 >35ms 说明输出滞后，主动再收紧重帧阈值
                if (p90_lat > 0.050 or p50_lat > 0.035):
                    if not hasattr(self,'_last_latency_compress') or (now - self._last_latency_compress) > 0.4:
                        heavy_interval_threshold *= 0.78  # 适度压缩，避免过度重绘引起抖动
                        self._last_latency_compress = now
                        if frame_trace:
                            print(f"[FRAME_ADAPT] latency compress p50={p50_lat*1000:.1f}ms p90={p90_lat*1000:.1f}ms new_thr={heavy_interval_threshold*1000:.1f}ms")
            # 最新延迟判断: 如果 add→display 延迟 >60ms 强制重帧
            force_latency_redraw = False
            if self._diag_add_to_display_latencies:
                last_lat = self._diag_add_to_display_latencies[-1]
                if last_lat > 0.060:
                    force_latency_redraw = True
            # 轻量帧 watchdog：最近显示间隔>120ms 也强制重帧
            if not force_latency_redraw and self._diag_display_intervals:
                try:
                    if self._diag_display_intervals[-1] > 0.120:
                        force_latency_redraw = True
                except Exception:
                    pass
            # 轻量帧条件：无新点 + 正在录音的自动跟随阶段 + 未到重帧间隔 + 无强制延迟重绘
            if (getattr(self, '_new_points_since_last_draw', 0) == 0 and
                getattr(self, 'is_recording_active', False) and
                getattr(self, 'auto_follow', True) and getattr(self, 'auto_scroll_enabled', True) and
                # 使用全局时间判断进入平滑滚动阶段，避免以“最新数据时间”造成卡段
                getattr(self, 'current_global_time', 0.0) > self.center_display_time and
                # 用户主动滚动时放宽阈值，保持连续感
                (now - self._last_heavy_redraw_time) < (heavy_interval_threshold * (1.4 if (now - getattr(self, '_last_manual_scroll_time', 0)) < 2.0 else 1.0)) and
                not force_latency_redraw):
                try:
                    # 轻量帧：以“全局时间”为滚动基准，消除按数据到达批次带来的分段感
                    latest_time = self.time_data[-1] if self.time_data else 0.0
                    cur_t = getattr(self, 'current_global_time', latest_time)
                    manual_freeze = (now - getattr(self, '_last_manual_scroll_time', 0)) < 2.0
                    if (not manual_freeze) and cur_t > self.center_display_time:
                        time_start = cur_t - self.center_display_time
                        time_end = time_start + self.time_window
                    else:
                        # 初期(<8s)或手动冻结：保持固定窗口
                        time_start = 0.0 if cur_t <= self.center_display_time else self.time_offset
                        time_end = time_start + self.time_window
                    if hasattr(self, 'ax'):
                        # 使用平滑过渡，避免“瞬移/齿感”
                        try:
                            self._smooth_set_xlim(time_start, time_end, strength=float(getattr(self,'_smooth_strength',0.9)), max_step=float(getattr(self,'_smooth_max_step',0.05)))
                        except Exception:
                            self.ax.set_xlim(time_start, time_end)
                        # 记录最近渲染窗口为实际 xlim，确保后续使用一致窗口
                        try:
                            self._last_render_window = self.ax.get_xlim()
                        except Exception:
                            self._last_render_window = (time_start, time_end)
                        # 轻量帧也维护批量细节点集合（否则看起来像“点消失”）
                        if getattr(self, '_use_batched_points', False):
                            # 若集合不存在或被 clear 掉，重建并挂回轴
                            if (not hasattr(self, '_batched_points')) or (self._batched_points is None):
                                try:
                                    detail_rgb = tuple(c/255.0 for c in (255, 255, 255))
                                    self._batched_points = self.ax.scatter([], [], s=16, c=[detail_rgb], alpha=0.0, linewidths=0, zorder=13)
                                except Exception:
                                    self._batched_points = None
                            elif self._batched_points not in getattr(self.ax, 'collections', []):
                                # 可能被 clear() 移除，重新添加
                                try:
                                    self.ax.add_collection(self._batched_points)
                                except Exception:
                                    pass
                            # 仅当集合存在时，按当前可视窗口快速刷新 offsets（无新点，仅滚动）
                            if self._batched_points is not None and hasattr(self, '_segments') and self._segments:
                                try:
                                    import numpy as np
                                    x0, x1 = self.ax.get_xlim()
                                    chunks = []
                                    for (seg_times, seg_pitches) in self._segments:
                                        if not seg_times:
                                            continue
                                        # 只收集视口范围内的点
                                        for t, y in zip(seg_times, seg_pitches):
                                            if x0 <= t <= x1:
                                                chunks.append((t, y))
                                    if chunks:
                                        arr = np.asarray(chunks, dtype=float)
                                        # 轻量抽样限制（稍放宽以减少“断续”感）
                                        max_pts = int(getattr(self, '_batched_points_cap_light', 900))
                                        if arr.shape[0] > max_pts:
                                            step = int(np.ceil(arr.shape[0] / max_pts))
                                            arr = arr[::step]
                                        # 基于当前缩放计算大小（与重帧一致）
                                        def _calc_marker_size():
                                            base_w = float(getattr(self, 'current_linewidth', 0.6))
                                            zoom = float(getattr(self, 'zoom_level', 1.0))
                                            diameter = max(1.6, min(base_w * 3.2 / (0.6 if zoom < 1 else min(zoom, 3.0)), 4.0))
                                            return diameter ** 2
                                        s_val_global = _calc_marker_size()
                                        self._batched_points.set_offsets(arr)
                                        self._batched_points.set_sizes([s_val_global] * len(arr))
                                        self._batched_points.set_alpha(0.95)
                                        self._batched_points.set_zorder(13)
                                    else:
                                        # 视口内无点则隐藏
                                        self._batched_points.set_offsets(np.empty((0, 2)))
                                        self._batched_points.set_alpha(0.0)
                                except Exception:
                                    # 避免轻量帧异常影响流畅度
                                    pass
                    else:
                        # 安全后备：轴未就绪时直接返回
                        return
                    self._light_frame_count += 1
                    if frame_trace:
                        print(f"[FRAME] 轻量帧 skip heavy redraw gap={(now - self._last_heavy_redraw_time)*1000:.1f}ms thr={heavy_interval_threshold*1000:.0f}ms lat_force={force_latency_redraw}")
                    self.update_status_display()
                    self.update_scrollbars()
                    # 轻量帧手动触发一次重绘，避免仅改 xlim 而未刷新导致的“齿感”和细节点暂隐
                    if hasattr(self, 'canvas'):
                        self.canvas.draw_idle()
                    return
                except Exception:
                    pass
            # 诊断: 计算从上次显示到本次的间隔
            if self._diag_last_display_time is not None:
                try:
                    interval = now - self._diag_last_display_time
                    if 0 <= interval < 5.0:
                        self._diag_display_intervals.append(interval)
                except TypeError:
                    # 防御: 若出现 None 导致的类型错误，直接重置
                    pass
            self._diag_last_display_time = now
            # 诊断: 如果有待显示点，估算延迟
            if hasattr(self, '_last_add_pitch_receive_time'):
                latency = now - self._last_add_pitch_receive_time
                # 只记录合理范围 (<1s) 的延迟
                if 0 <= latency < 1.0:
                    self._diag_add_to_display_latencies.append(latency)
            if self._diag_pending_points > 0:
                self._diag_pending_points = 0  # 已消费
            # 每2秒打印一次诊断统计
            if not hasattr(self, '_diag_last_report'):
                self._diag_last_report = now
            if now - self._diag_last_report > 2.0 and self._diag_display_intervals and getattr(self, 'debug_flags', {}).get('display_diag'):
                # 仅统计最近 200 帧，避免历史拖慢
                recent_int = list(self._diag_display_intervals)[-200:]
                avg_interval = sum(recent_int)/len(recent_int)
                max_interval = max(recent_int)
                si = sorted(recent_int)
                p50_int = si[int(0.5*len(si))-1]
                p90_int = si[int(0.9*len(si))-1] if len(si) > 10 else max_interval
                p95_int = si[int(0.95*len(si))-1] if len(si) > 20 else max_interval
                if self._diag_add_to_display_latencies:
                    lat_recent = list(self._diag_add_to_display_latencies)[-200:]
                    sl = sorted(lat_recent)
                    avg_latency = sum(lat_recent)/len(lat_recent)
                    p50_latency = sl[int(0.5*len(sl))-1]
                    p90_latency = sl[int(0.9*len(sl))-1] if len(sl) > 10 else sl[-1]
                    p95_latency = sl[int(0.95*len(sl))-1] if len(sl) > 20 else sl[-1]
                else:
                    avg_latency = p50_latency = p90_latency = p95_latency = 0
                print("⏱️ 显示诊断: int_avg={:.1f}ms p50={:.1f} p90={:.1f} p95={:.1f} max={:.1f} | lat_avg={:.1f}ms p50={:.1f} p90={:.1f} p95={:.1f} nLat={}".format(
                    avg_interval*1000, p50_int*1000, p90_int*1000, p95_int*1000, max_interval*1000,
                    avg_latency*1000, p50_latency*1000, p90_latency*1000, p95_latency*1000, len(self._diag_add_to_display_latencies)))
                self._diag_last_report = now
            # 🚀 智能更新优化：避免过度重复计算
            current_data_size = len(self.pitch_data)
            current_time_window = (self.time_offset, self.time_offset + self.time_window)
            current_y_center = self.y_view_center  # 添加Y轴中心到状态检查
            
            # 检查是否需要更新（避免无意义的重复计算）
            # 🔥 修复闪烁问题：添加强制重绘标志，确保滚动后重新绘制
            force_redraw = getattr(self, '_force_redraw_on_next_update', False)
            scroll_triggered = getattr(self, '_scroll_triggered_redraw', False)
            
            if force_redraw:
                self._force_redraw_on_next_update = False  # 重置标志
            elif scroll_triggered:
                # 滚轮触发的重绘，确保至少执行一次完整重绘
                self._scroll_triggered_redraw = False  # 重置标志
                # 记录手动滚动时间，短时间内冻结自动滚动
                self._last_manual_scroll_time = now
                force_redraw = True  # 强制重绘
            elif hasattr(self, '_last_update_state'):
                last_size, last_window, last_y_center = self._last_update_state
                # 若处于用户手动水平滚动的冻结期（2秒内），即便窗口未变也允许更新以维持细节点刷新
                manual_freeze = (now - getattr(self, '_last_manual_scroll_time', 0)) < 2.0
                if (not manual_freeze and current_data_size == last_size and 
                    current_time_window == last_window and
                    abs(current_y_center - last_y_center) < 0.01 and  # Y轴中心变化检查
                    current_data_size > 0):
                    return  # 数据、窗口和Y轴都没变化，跳过更新
            
            # 更新状态记录
            self._last_update_state = (current_data_size, current_time_window, current_y_center)
            
            # 调试信息（减少冗余输出）
            if self.debug_flags.get('display_diag') and current_data_size % 40 == 0:
                real_fps = 0.0
                if self._diag_display_intervals:
                    avg_int = sum(self._diag_display_intervals)/len(self._diag_display_intervals)
                    real_fps = 1.0/avg_int if avg_int>0 else 0
                print(f"[DISP_DIAG] 总数据={current_data_size} pitch_line={hasattr(self, 'pitch_line')} light_frames={getattr(self,'_light_frame_count',0)} total_frames={self._total_frame_count} realFPS={real_fps:.1f}")
            
            # 根据当前时间偏移过滤数据
            # 动态窗口策略：录制早期(<完整窗口)时右侧边界跟随最新时间，避免一开始就铺满16秒导致8秒居中逻辑失效
            # === 轴窗口 & 数据窗口分离 ===
            # 轴显示窗口(视觉范围)：统一以“最新数据时间”为中心（>=8s）作为目标，确保细节点始终居中且无抖动
            latest_time = self.time_data[-1] if self.time_data else 0.0
            cur_t = getattr(self, 'current_global_time', latest_time)
            manual_freeze = (now - getattr(self, '_last_manual_scroll_time', 0)) < 2.0
            if getattr(self, 'is_recording_active', False):
                if (getattr(self, 'auto_follow', True) and getattr(self, 'auto_scroll_enabled', True)
                    and (not manual_freeze) and cur_t > self.center_display_time):
                    axis_start = cur_t - self.center_display_time
                    axis_end = axis_start + self.time_window
                else:
                    # 初期(<8s)或冻结/关闭自动跟随：依据 time_offset
                    axis_start = self.time_offset if cur_t > self.center_display_time else 0.0
                    axis_end = axis_start + self.time_window
            else:
                # 停止录音：永远尊重用户 time_offset（允许拖到未来空白区）
                axis_start = self.time_offset
                axis_end = axis_start + self.time_window
            # 录音态才允许平滑设置坐标轴范围；停止态直接设置，防止被回拽
            try:
                if hasattr(self, 'ax') and self.ax is not None:
                    if getattr(self, 'is_recording_active', False) and getattr(self, 'auto_follow', True) and getattr(self, 'auto_scroll_enabled', True) and (not getattr(self, 'freeze_y_center', False)) and cur_t > self.center_display_time:
                        try:
                            self._smooth_set_xlim(axis_start, axis_end, strength=float(getattr(self,'_smooth_strength',0.9)), max_step=float(getattr(self,'_smooth_max_step',0.05)))
                        except Exception:
                            self.ax.set_xlim(axis_start, axis_end)
                    else:
                        self.ax.set_xlim(axis_start, axis_end)
            except Exception:
                pass
            # 数据窗口：向左保留一个缓冲尾迹，减少“段块截尾”视觉感
            if not hasattr(self, '_tail_buffer_sec'):
                self._tail_buffer_sec = 0.25  # 下调尾迹缓冲，减少“批量刷新”边界效应
            data_start = max(0.0, axis_start - self._tail_buffer_sec)
            data_end = axis_end
            # 记录最近渲染窗口（以当前 xlim 为准）
            try:
                self._last_render_window = self.ax.get_xlim() if hasattr(self, 'ax') else (axis_start, axis_end)
            except Exception:
                self._last_render_window = (axis_start, axis_end)
            
            # 过滤时间窗口内的数据（保持顺序）
            # 修复：原实现只前向递增start_idx，向左/回到早期时间会丢失旧点
            # 统一使用bisect二分定位窗口起始索引，支持双向滚动；性能O(logN)
            # 为避免 deque 在某些极端情况下与 bisect/索引交互导致意外 slice 对象索引错误，用列表拷贝做局部只读视图
            _time_seq = list(self.time_data)
            data_len = len(_time_seq)
            if data_len == 0:
                valid_indices = []
            else:
                import bisect
                try:
                    start_idx = bisect.bisect_left(_time_seq, data_start - 1e-6)
                except Exception as _bis_e:
                    print(f"[BISect_ERR] {type(_bis_e).__name__}: {_bis_e} len_time_seq={len(_time_seq)} data_start={data_start:.4f}")
                    # 回退线性查找
                    start_idx = 0
                    while start_idx < data_len and _time_seq[start_idx] < data_start - 1e-6:
                        start_idx += 1
                # 仍向后线性扩展到窗口结束（数据局部连续，线性更快）
                end_idx = start_idx
                while end_idx < data_len and _time_seq[end_idx] <= data_end + 1e-6:
                    end_idx += 1
                valid_indices = list(range(start_idx, end_idx))
                # 记录用于下一帧（允许轻微回退缓存1个点）
                self._last_window_start_index = max(0, start_idx - 1)
                # 调试：可选打印一次方向变化（节流）
                if hasattr(self, '_last_window_start_index_real'):
                    if start_idx < getattr(self, '_last_window_start_index_real_previous', start_idx+1):
                        # 向后滚动发生
                        if self.debug_flags.get('segment_log') and not hasattr(self, '_last_backward_scroll_logged'):
                            print(f"🔁 回退滚动重建窗口: start_idx={start_idx}")
                            self._last_backward_scroll_logged = True
                    else:
                        # 正向滚动恢复可再次允许一次回退日志
                        if hasattr(self, '_last_backward_scroll_logged'):
                            delattr(self, '_last_backward_scroll_logged')
                self._last_window_start_index_real_previous = start_idx
                self._last_window_start_index_real = start_idx
            
            # 停止录音后且完全在数据末尾之后的空白区域，直接走轻路径：不重算段、不绘制，保留当前空视图，避免粘滞
            if not valid_indices:
                try:
                    last_t = _time_seq[-1] if _time_seq else None
                except Exception:
                    last_t = None
                viewing_future_blank = (not getattr(self,'is_recording_active', False)) and (last_t is not None) and (axis_start > last_t + 1e-3)
                if viewing_future_blank:
                    # 轻量：仅保持 xlim 与辅助线同步
                    try:
                        self.update_guides()
                    except Exception:
                        pass
                    # 更新状态显示与滚动条
                    self.update_status_display()
                    self.update_scrollbars()
                    if hasattr(self, 'canvas'):
                        self.canvas.draw_idle()
                    return
                # 其他情况（窗口内确无数据）：清空显示
                self.pitch_line.set_data([], [])
                self.canvas.draw_idle()
                return
            
            # 提取有效数据
            try:
                times = [_time_seq[i] for i in valid_indices]
                pitches = [self.pitch_data[i] for i in valid_indices]
                confidences = [self.confidence_data[i] for i in valid_indices]
            except TypeError as _idx_e:
                # 捕获可能的 slice 索引异常，输出详细上下文
                print(f"[INDEX_ERR] {type(_idx_e).__name__}: {_idx_e} valid_indices_sample={valid_indices[:10]} len_valid={len(valid_indices)} data_len={data_len}")
                print(f"[INDEX_STATE] start_idx={valid_indices[0] if valid_indices else 'NA'} end_idx={(valid_indices[-1] if valid_indices else 'NA')} axis_window=({axis_start:.3f},{axis_end:.3f}) data_window=({data_start:.3f},{data_end:.3f})")
                import traceback as _tb
                print("[INDEX_TRACE]" + ''.join(_tb.format_exc()))
                # 回退：直接整窗截取（线性扫描）
                times = _time_seq
                pitches = list(self.pitch_data)
                confidences = list(self.confidence_data)
            phase_after_window = time.time()
            if 'frame_trace' in locals() and frame_trace:
                print("[FRAME] 窗口过滤 点数={} 用时={:.2f}ms".format(len(times), (phase_after_window - frame_cpu_start)*1000))
            
            # 断续段分割：增量优化（新增点 / 数据窗口平移 / 超时 才重算）
            segments = []
            recompute_needed = False
            if len(times) > 1:
                now_time = now
                if not hasattr(self, '_last_segments_recompute'):
                    self._last_segments_recompute = 0.0
                prev_window = getattr(self, '_segments_cache_window', None)
                window_shift = 0.0
                if prev_window:
                    # 使用数据窗口起点比较（含 tail 缓冲）
                    window_shift = abs(data_start - prev_window[0])
                # 条件：
                #   - 有新点：总是重算
                #   - 窗口平移较大：>0.08s（原0.02s，降低自滚期间的抖动）
                #   - 时间过久：>X（按模式自适应，Quiet≈0.14s / Balanced≈0.09s / High≈0.06s）
                # 在>8s自动滚动阶段且无新点时，尽量沿用缓存（减少算力），靠轻量帧移动视窗
                # 阈值来自模式：缺省时给出安全默认
                _recomp_age = float(getattr(self, '_segments_recompute_max_age_s', 0.10))
                _large_shift_th = float(getattr(self, '_segments_large_shift_threshold', 0.06))
                has_new_pts = getattr(self, '_new_points_since_last_draw', 0) > 0
                large_shift = window_shift > _large_shift_th
                too_old = (now_time - self._last_segments_recompute) > _recomp_age
                if has_new_pts or large_shift or too_old:
                    recompute_needed = True
                if (hasattr(self, '_segments_cache') and not recompute_needed and
                    prev_window and prev_window == (data_start, data_end)):
                    segments = self._segments_cache
                    if self.debug_flags.get('segment_log'):
                        if not hasattr(self, '_last_cache_hit_log') or now_time - self._last_cache_hit_log > 1.0:
                            print(f"[SEG_DIAG] cache_hit dataWin=({data_start:.2f},{data_end:.2f}) axisWin=({axis_start:.2f},{axis_end:.2f}) pts_cached={sum(len(s[0]) for s in segments)} segs={len(segments)} shift={window_shift:.3f}s dt={(now_time-self._last_segments_recompute)*1000:.0f}ms")
                            self._last_cache_hit_log = now_time
                        # 统计 cache 命中
                        if hasattr(self, '_stat_counters'):
                            self._stat_counters['segment_cache_hits'] = self._stat_counters.get('segment_cache_hits', 0) + 1
                else:
                    seg_t0 = time.time()
                    detected_gaps = []
                    current_segment_times = [times[0]]
                    current_segment_pitches = [pitches[0]]
                    for i in range(1, len(times)):
                        time_gap = times[i] - times[i-1]
                        if time_gap < 0.3:
                            current_segment_times.append(times[i])
                            current_segment_pitches.append(pitches[i])
                        else:
                            if len(current_segment_times) >= 1:
                                segments.append((current_segment_times.copy(), current_segment_pitches.copy()))
                            detected_gaps.append({'time_gap': time_gap,'prev_time': times[i-1],'new_time': times[i]})
                            current_segment_times = [times[i]]
                            current_segment_pitches = [pitches[i]]
                    if len(current_segment_times) >= 1:
                        segments.append((current_segment_times, current_segment_pitches))
                    self._segments_cache = segments
                    self._segments_cache_window = (data_start, data_end)
                    self._last_segments_recompute = now_time
                    seg_dur = (time.time() - seg_t0) * 1000
                    self._seg_timing_samples.append(seg_dur)
                    if recompute_needed and has_new_pts:
                        if (self.debug_flags.get('segment_log') and
                            (not hasattr(self, '_last_segments_count') or self._last_segments_count != len(segments) or len(detected_gaps) > 0)):
                            for gap in detected_gaps:
                                print(f"[SEG] gap={gap['time_gap']:.2f}s prev={gap['prev_time']:.2f}s new={gap['new_time']:.2f}s")
                            if segments:
                                print(f"[SEG] segments={len(segments)} pts={sum(len(seg[0]) for seg in segments)} range={segments[0][0][0]:.2f}-{segments[-1][0][-1]:.2f}s seg_dur={seg_dur:.1f}ms shift={window_shift:.3f}s dt={(now_time-self._last_segments_recompute)*1000:.0f}ms tail={self._tail_buffer_sec:.2f}s")
                            self._last_segments_count = len(segments)
                            if hasattr(self, '_stat_counters'):
                                self._stat_counters['segments_recomputed'] = self._stat_counters.get('segments_recomputed', 0) + 1
                    if 'frame_trace' in locals() and frame_trace:
                        print("[FRAME] 分段处理 segs={} 重算?={} seg_time={:.2f}ms cache_data_window={} axisWin=({:.2f},{:.2f}) shift={:.3f}s tail={:.2f}s".format(
                            len(segments), recompute_needed, seg_dur if 'seg_dur' in locals() else 0.0, getattr(self,'_segments_cache_window',None), axis_start, axis_end, window_shift, self._tail_buffer_sec))

                    # === 细节点可视性诊断 / 异常检测 ===
                    try:
                        total_visible_points = sum(len(seg[0]) for seg in segments)
                        single_point_segs = sum(1 for seg in segments if len(seg[0]) == 1)
                        window_span = axis_end - axis_start
                        now_diag = now_time
                        if not hasattr(self, '_diag_last_fine_log'):
                            self._diag_last_fine_log = 0
                        if not hasattr(self, '_prev_visible_point_count'):
                            self._prev_visible_point_count = total_visible_points
                            self._prev_single_point_segs = single_point_segs
                            self._prev_visible_window = (axis_start, axis_end)
                            self._last_visible_time_set = set()

                        # 生成当前可见 time 集合（取整到 4ms 以压缩）
                        cur_time_set = set()
                        for seg_times, _sp in segments:
                            for tval in seg_times:
                                if axis_start - 1e-6 <= tval <= axis_end + 1e-6:
                                    cur_time_set.add(round(tval, 4))

                        # 检测丢失：上一帧仍在窗口、当前窗口几乎未左移（<0.05s）且大量点消失
                        if hasattr(self, '_last_visible_time_set') and self._last_visible_time_set:
                            prev_window_start, prev_window_end = self._prev_visible_window
                            window_shift = abs(prev_window_start - axis_start)
                            if window_shift < 0.05 and len(self._last_visible_time_set) > 0:
                                missing_prev = [tv for tv in self._last_visible_time_set if tv not in cur_time_set]
                                # 排除由于窗口右移自然滑出左边界的点
                                missing_in_window = [tv for tv in missing_prev if tv >= axis_start]
                                if missing_in_window:
                                    loss_ratio = len(missing_in_window) / max(1, len(self._last_visible_time_set))
                                    if loss_ratio > 0.15:  # 阈值：可见点骤减>15%
                                        print(f"⚠️ [FINE_LOSS] abrupt loss ratio={loss_ratio*100:.1f}% lost={len(missing_in_window)} prev_total={len(self._last_visible_time_set)} axisWin=({axis_start:.2f},{axis_end:.2f}) dataWin=({data_start:.2f},{data_end:.2f}) segs={len(segments)} single_seg={single_point_segs}")
                                        # 触发一次强制重绘标志，便于后续定位
                                        self._force_redraw_on_next_update = True

                        # 定期记录状态（1.2s节流）
                        if now_diag - self._diag_last_fine_log > 1.2 and getattr(self, 'debug_flags', {}).get('display_diag'):
                            print(f"[FINE] axisWin=({axis_start:.2f},{axis_end:.2f}) dataWin=({data_start:.2f},{data_end:.2f}) span={window_span:.2f}s pts={total_visible_points} segs={len(segments)} single_seg={single_point_segs} cache={'no' if recompute_needed else 'maybe'} tail={self._tail_buffer_sec:.2f}s")
                            self._diag_last_fine_log = now_diag

                        # 保存当前状态
                        self._prev_visible_point_count = total_visible_points
                        self._prev_single_point_segs = single_point_segs
                        self._prev_visible_window = (axis_start, axis_end)
                        self._last_visible_time_set = cur_time_set
                    except Exception as _fine_e:
                        if self.debug_flags.get('segment_log'):
                            print(f"[FINE_DIAG_ERR] { _fine_e }")
                self.draw_segmented_pitch_line(segments)
            else:
                self.pitch_line.set_data(times, pitches)
            self._new_points_since_last_draw = 0
            draw_dur = (time.time() - t_start) * 1000
            self._draw_timing_samples.append(draw_dur)
            self._last_heavy_redraw_time = now
            # 重帧后立即刷新批量细节点集合，避免轻量帧间隙出现“点稀疏/暂隐”
            try:
                if getattr(self, '_use_batched_points', False):
                    self._refresh_batched_points_for_current_xlim()
            except Exception:
                pass
            if ('frame_trace' in locals() and frame_trace) or (perf_verbose and draw_dur > 12):
                print(f"[FRAME] 重绘完成 CPU耗时={draw_dur:.1f}ms segs={len(segments) if 'segments' in locals() else 0} pts={len(times)}")

            # 周期性性能打印（与原显示诊断区分）
            if self.debug_flags.get('display_diag'):
                if now - getattr(self, '_diag_last_perf_report', 0) > 2.5:
                    if self._seg_timing_samples:
                        seg_avg = sum(self._seg_timing_samples)/len(self._seg_timing_samples)
                        seg_max = max(self._seg_timing_samples)
                    else:
                        seg_avg = seg_max = 0
                    if self._draw_timing_samples:
                        draw_avg = sum(self._draw_timing_samples)/len(self._draw_timing_samples)
                        draw_max = max(self._draw_timing_samples)
                    else:
                        draw_avg = draw_max = 0
                    print(f"[DISP] seg_avg={seg_avg:.1f}ms seg_max={seg_max:.1f}ms draw_avg={draw_avg:.1f}ms draw_max={draw_max:.1f}ms")
                    self._diag_last_perf_report = now
            
            # 根据显示模式进行额外处理
            display_mode = self.display_mode.currentText() if hasattr(self, 'display_mode') else "心电图模式"
            
            if display_mode == "心电图模式":
                # 确保使用Matplotlib组件
                if self.main_plot_area != self.canvas:
                    self.switch_display_widget(use_pyqtgraph=False)
                
                # 心电图模式：更细的线条，提高颤音等细节显示清晰度
                # 注意：这里不再使用set_data，因为已经在draw_segmented_pitch_line中处理
                if hasattr(self, '_last_display_mode') and self._last_display_mode != "心电图模式":
                    print("💚 切换到心电图模式（断续曲线）")
                self._last_display_mode = "心电图模式"
                
            elif display_mode == "彩色渐变":
                # 彩色渐变模式：使用优化的Matplotlib LineCollection超细渐变
                print(f"🎨 超细平滑彩色渐变模式（断续）- 数据点数: {len(times)}")
                
                # 强制使用优化的Matplotlib LineCollection方案
                print("✨ 使用优化的Matplotlib超细渐变方案（断续版本）")
                # 确保使用Matplotlib组件
                if self.main_plot_area != self.canvas:
                    self.switch_display_widget(use_pyqtgraph=False)
                
                # 尝试添加超细平滑的渐变效果（断续版本）
                gradient_success = False
                try:
                    # 为每个音调段创建渐变效果
                    if hasattr(self, '_segments') and self._segments:
                        for seg_times, seg_pitches in self._segments:
                            result = self.update_beautiful_pitch_line(seg_times, seg_pitches, 
                                                                    [0.8] * len(seg_pitches))
                            gradient_success = (result is not False)
                        if gradient_success:
                            print("✅ 断续彩色渐变LineCollection创建成功")
                except Exception as e:
                    print(f"⚠️ 断续彩色渐变创建失败: {e}")
                    gradient_success = False
                
                # 如果渐变失败，使用断续彩色回退方案
                if not gradient_success:
                    print("🔄 使用断续彩色回退方案...")
                    # draw_segmented_pitch_line已经处理了断续绘制
                    import colorsys
                    if len(pitches) > 0:
                        avg_pitch = sum(pitches) / len(pitches)
                        hue = ((avg_pitch - 1.0) % 6.0) / 6.0
                        rgb = colorsys.hsv_to_rgb(hue, 0.8, 1.0)
                        if hasattr(self, 'pitch_line'):
                            self.pitch_line.set_color(rgb)
                    else:
                        if hasattr(self, 'pitch_line'):
                            self.pitch_line.set_color('#FF6600')  # 橙色作为默认
                else:
                    # 渐变成功，隐藏背景线
                    if hasattr(self, 'pitch_line'):
                        self.pitch_line.set_data([], [])
                        self.pitch_line.set_alpha(0.0)
            
            # 只在使用Matplotlib时更新坐标轴和刷新
            if self.main_plot_area == self.canvas and not ((getattr(self, '_new_points_since_last_draw', 0) == 0) and getattr(self, 'auto_follow', True) and getattr(self, 'auto_scroll_enabled', True)):
                # 更新坐标轴范围（如果需要） - 修复缩放一致性问题
                current_xlim = self.ax.get_xlim()
                current_ylim = self.ax.get_ylim()
                
                # 计算考虑缩放的实际Y轴范围
                # 新缩放：直接使用 compute_half_range() 作为半范围
                actual_y_range = self.compute_half_range()
                expected_y_min = self.y_view_center - actual_y_range
                expected_y_max = self.y_view_center + actual_y_range
                
                # 兼容：若上段未定义（防御）
                axis_start = locals().get('axis_start', getattr(self,'time_offset',0.0))
                axis_end = locals().get('axis_end', axis_start + getattr(self,'time_window',16.0))
                if (abs(current_xlim[0] - axis_start) > 0.1 or 
                    abs(current_xlim[1] - axis_end) > 0.1 or
                    abs(current_ylim[0] - expected_y_min) > 0.1 or
                    abs(current_ylim[1] - expected_y_max) > 0.1):
                    # 避免在轻量帧频繁调用 update_axis_ranges（内部可能 clear），仅在重帧或显著偏差时更新
                    self.update_axis_ranges()
                
                # 推迟到末尾统一 draw_idle，避免多次调度
                pass
            
            # 更新状态显示
            self.update_status_display()
            
            # 每次显示更新时也同步更新滚动条，确保实时响应
            self.update_scrollbars()
            # ---- 末尾帧总结 ----
            total_cpu = (time.time() - frame_cpu_start) * 1000
            if ('frame_trace' in locals() and frame_trace) or (perf_verbose and total_cpu > 15):
                print(f"[FRAME] 结束 total_cpu={total_cpu:.1f}ms heavy_draw={draw_dur:.1f}ms axisWin=({axis_start:.2f},{axis_end:.2f}) dataWin=({data_start:.2f},{data_end:.2f}) zoom={self.zoom_level:.2f} next_heavy_gap_target={heavy_interval_threshold*1000:.0f}ms tail={self._tail_buffer_sec:.2f}s")
            # 统计异常刷新间隔（卡顿触发）
            if not hasattr(self, '_stutter_events'): self._stutter_events = 0
            if self._diag_display_intervals:
                last_interval = self._diag_display_intervals[-1]
                if last_interval > 0.15:  # 150ms 认为肉眼可见卡顿
                    self._stutter_events += 1
                    if perf_verbose:
                        print("⚠️ [STUTTER] interval={:.1f}ms total_cpu={:.1f}ms new_pts={} cache_hit?={} segs={} light_frames={}".format(
                            last_interval*1000,
                            total_cpu,
                            getattr(self,'_new_points_since_last_draw',0),
                            (not recompute_needed and hasattr(self,'_segments_cache_window') and self._segments_cache_window==(time_start,time_end)),
                            len(segments) if 'segments' in locals() else 0,
                            getattr(self,'_light_frame_count',0)))
            # 定期输出卡顿统计
            if perf_verbose and (now - getattr(self, '_last_stutter_report',0)) > 5:
                st = self._stutter_events
                total_frames = len(self._diag_display_intervals)
                if total_frames:
                    ratio = st/total_frames*100
                    avg_int = sum(self._diag_display_intervals)/total_frames*1000
                    p95_int = sorted(self._diag_display_intervals)[int(0.95*total_frames)-1]*1000 if total_frames>5 else 0
                    print(f"[STATS] frames={total_frames} stutters={st} stutter%={ratio:.1f}% avgInt={avg_int:.1f}ms p95Int={p95_int:.1f}ms heavyDrawAvg={(sum(self._draw_timing_samples)/len(self._draw_timing_samples)):.1f}ms")
                self._last_stutter_report = now
            
        except Exception as e:
            import traceback, sys
            print(f"❌ 更新显示错误: {type(e).__name__}: {e}")
            # 输出栈追踪与关键状态快照，便于定位 slice 来源
            print(''.join(traceback.format_exc()))
            try:
                print(f"[STATE_SNAPSHOT] len_time={len(getattr(self,'time_data',[]))} len_pitch={len(getattr(self,'pitch_data',[]))} last_time={getattr(self,'time_data',[-1])[-1] if getattr(self,'time_data',None) else 'NA'} window=({getattr(self,'time_offset','?')},{getattr(self,'time_offset','?') + getattr(self,'time_window',0)}) new_pts={getattr(self,'_new_points_since_last_draw','?')} heavy_gap={(time.time()-getattr(self,'_last_heavy_redraw_time',0)) if hasattr(self,'_last_heavy_redraw_time') else 'NA'}")
            except Exception as _snap_e:
                print(f"[STATE_SNAPSHOT_ERR] {_snap_e}")
        finally:
            # 清理重入标记
            self._in_update_display = False
    
    def draw_segmented_pitch_line(self, segments):
        """绘制断续的音调曲线（每段独立绘制，换气段不连接），带签名缓存与懒更新以提升实时性"""
        try:
            # 存储段信息供其他函数使用
            self._segments = segments
            
            if not segments:
                self.pitch_line.set_data([], [])
                self.canvas.draw_idle()  # 🔥 修复：即使没有段也要重绘画布
                return
            
            # 增量策略：保留已有对象，按段索引更新，减少闪烁并保持>8秒自动滚动时细节点可见
            if not hasattr(self, '_segment_lines'):
                self._segment_lines = []
            if not hasattr(self, '_segment_points'):
                self._segment_points = []

            # 隐藏原整体线（使用分段显示）
            self.pitch_line.set_data([], [])

            # 曲线改为琉璃蓝（DeepSkyBlue），细节点为白色
            curve_rgb = tuple(c/255.0 for c in (0, 191, 255))
            detail_rgb = tuple(c/255.0 for c in (255, 255, 255))

            # 浏览历史（停止后）优先高保真：禁用批量细节点，使用逐段散点全强度
            high_fidelity_browse = not getattr(self, 'is_recording_active', True)
            use_batched_points = getattr(self, '_use_batched_points', False) and (not high_fidelity_browse)

            # 如果启用批量细节点，确保集合存在
            if use_batched_points:
                if not hasattr(self, '_batched_points') or self._batched_points is None:
                    try:
                        self._batched_points = self.ax.scatter([], [], s=16, c=[detail_rgb], alpha=0.95, linewidths=0, zorder=12)
                    except Exception:
                        self._batched_points = None
                # 确保可见（可能在历史浏览时被隐藏）
                try:
                    if self._batched_points is not None:
                        self._batched_points.set_visible(True)
                except Exception:
                    pass
            else:
                # 高保真浏览：如存在批量集合则隐藏之，避免与逐段散点重复/冲突
                try:
                    if hasattr(self, '_batched_points') and self._batched_points is not None:
                        self._batched_points.set_alpha(0.0)
                        try:
                            self._batched_points.set_visible(False)
                        except Exception:
                            pass
                except Exception:
                    pass

            # 如果段数量减少，移除多余对象
            if len(self._segment_lines) > len(segments):
                for extra in self._segment_lines[len(segments):]:
                    try: extra.remove()
                    except: pass
                self._segment_lines = self._segment_lines[:len(segments)]
            if len(self._segment_points) > len(segments):
                for extra in self._segment_points[len(segments):]:
                    try: extra.remove()
                    except: pass
                self._segment_points = self._segment_points[:len(segments)]

            # 尺寸计算函数：保证细节点在高缩放/低缩放下都可见
            def _calc_marker_size():
                base_w = float(getattr(self, 'current_linewidth', 0.6))
                # 线宽与缩放综合：放大倍数越大点可适当变小，反之放大
                zoom = float(getattr(self, 'zoom_level', 1.0))
                # 期望直径（points单位）
                diameter = max(1.6, min(base_w * 3.2 / (0.6 if zoom < 1 else min(zoom, 3.0)), 4.0))
                # matplotlib scatter s = points^2
                return diameter ** 2

            loop_start = time.time()
            worst_seg_cpu = 0.0
            worst_seg_idx = -1
            import time as _tmod
            # 本帧固定一次点大小，避免每段重复计算
            s_val_global = _calc_marker_size()
            # 生成本帧分段签名，用于跳过未变更段
            cur_sigs = []
            for (seg_times, seg_pitches) in segments:
                if len(seg_times):
                    cur_sigs.append((seg_times[0], seg_times[-1], len(seg_times)))
                else:
                    cur_sigs.append((None, None, 0))
            sig_mismatch = (len(getattr(self, '_segment_sigs', [])) != len(cur_sigs))
            lazy_tail = max(0, min(getattr(self, '_lazy_points_update_n', 3), len(segments)))

            for i, (seg_times, seg_pitches) in enumerate(segments):
                seg_loop_start = _tmod.time()
                # 允许单点段（显示细节点）
                if i >= len(self._segment_lines):
                    # 新建 line
                    if len(seg_times) >= 2:
                        line, = self.ax.plot(seg_times, seg_pitches,
                                             color=curve_rgb,
                                             linewidth=self.current_linewidth,
                                             alpha=0.85,
                                             solid_capstyle='round',
                                             solid_joinstyle='round')
                    else:
                        line, = self.ax.plot(seg_times, seg_pitches,
                                             color=curve_rgb,
                                             linewidth=self.current_linewidth,
                                             alpha=0.0)
                    self._segment_lines.append(line)
                    pts = self.ax.scatter(seg_times, seg_pitches,
                                          s=s_val_global,
                                          c=detail_rgb,
                                          alpha=(0.2 if use_batched_points else 0.95),
                                          linewidths=0,
                                          zorder=12)
                    self._segment_points.append(pts)
                else:
                    line = self._segment_lines[i]
                    # 若被 ax.clear() 移除，重新挂载
                    if line.axes is None or line not in self.ax.lines:
                        try:
                            self.ax.add_line(line)
                        except Exception:
                            pass
                    # 判断是否需要更新该段数据（签名变化或数量变化）
                    need_update = sig_mismatch or (i >= len(getattr(self, '_segment_sigs', []))) or (self._segment_sigs[i] != cur_sigs[i])
                    if len(seg_times) >= 2:
                        if need_update:
                            line.set_data(seg_times, seg_pitches)
                        line.set_alpha(0.85)
                        line.set_linewidth(self.current_linewidth)
                    else:
                        if need_update:
                            line.set_data(seg_times, seg_pitches)
                        line.set_alpha(0.0)
                    # 处理散点
                    old_pts = self._segment_points[i]
                    if old_pts not in self.ax.collections:
                        try:
                            self.ax.add_collection(old_pts)
                        except Exception:
                            pass
                    try:
                        import numpy as np
                        # 浏览历史时强制逐段更新，保证与实时一致；录音中启用懒更新/批量优化
                        if high_fidelity_browse:
                            update_points = True
                        else:
                            # 使用批量散点时，跳过逐段 offsets 更新，降低每帧 set_offsets 次数
                            update_points = (not use_batched_points) and (need_update or (i >= len(segments) - lazy_tail))
                        if update_points:
                            offs = np.column_stack((seg_times, seg_pitches)) if len(seg_times) else np.empty((0, 2))
                            old_pts.set_offsets(offs)
                            old_pts.set_sizes([s_val_global] * (len(seg_times) if len(seg_times) else 1))
                            # 历史浏览：高可见度；实时：与原逻辑一致
                            old_pts.set_alpha(0.95 if len(seg_times) else 0.0)
                        else:
                            # 仅同步可见性/透明度，保留 offsets 与 sizes，降低每帧压力
                            if use_batched_points:
                                # 实时批量点：分段点集弱可见，避免重复
                                old_pts.set_alpha(0.15 if len(seg_times) else 0.0)
                            else:
                                old_pts.set_alpha(0.95 if len(seg_times) else 0.0)
                        old_pts.set_zorder(12)
                    except Exception:
                        try:
                            if old_pts in self.ax.collections:
                                old_pts.remove()
                        except Exception:
                            pass
                        new_pts = self.ax.scatter(seg_times, seg_pitches,
                                                  s=s_val_global,
                                                  c=detail_rgb,
                                                  alpha=0.95,
                                                  linewidths=0,
                                                  zorder=12)
                        self._segment_points[i] = new_pts

                if self.debug_flags.get('segment_log') and i % 8 == 0:
                    print(f"[SEG_DRAW] 段{i+1} 点数={len(seg_times)} 范围={seg_times[0]:.2f}-{seg_times[-1]:.2f}s")
                seg_cpu = (_tmod.time() - seg_loop_start)*1000
                if seg_cpu > worst_seg_cpu:
                    worst_seg_cpu = seg_cpu
                    worst_seg_idx = i
            total_seg_cpu = (time.time() - loop_start)*1000
            if getattr(self,'debug_flags',{}).get('perf_verbose', False) and total_seg_cpu > 4:
                print(f"[SEG_PERF] segs={len(segments)} total_seg_cpu={total_seg_cpu:.2f}ms worst_seg={worst_seg_idx+1} worst_cpu={worst_seg_cpu:.2f}ms")
            # 批量细节点：实时优化；历史浏览关闭（使用逐段高保真）
            if use_batched_points and hasattr(self, '_batched_points') and (self._batched_points is not None):
                try:
                    import numpy as np
                    # 当前可视窗口裁剪，避免对屏外大量点做无效更新
                    try:
                        x0, x1 = self.ax.get_xlim()
                    except Exception:
                        x0, x1 = None, None
                    # 若集合被 clear 移除，则重新挂回
                    if self._batched_points not in getattr(self.ax, 'collections', []):
                        try:
                            self.ax.add_collection(self._batched_points)
                        except Exception:
                            pass
                    chunks = []
                    total_pts = 0
                    for (seg_times, seg_pitches) in segments:
                        if not seg_times:
                            continue
                        if x0 is not None and x1 is not None:
                            # 仅保留窗口内点（含边界）
                            for t, y in zip(seg_times, seg_pitches):
                                if x0 <= t <= x1:
                                    chunks.append((t, y))
                        else:
                            for t, y in zip(seg_times, seg_pitches):
                                chunks.append((t, y))
                    if chunks:
                        arr = np.asarray(chunks, dtype=float)
                        total_pts = arr.shape[0]
                        # 视口点数过多时做等距抽样，限制 offsets 更新量，避免抖动
                        max_pts = int(getattr(self, '_batched_points_cap_heavy', 1200))
                        if total_pts > max_pts:
                            step = int(np.ceil(total_pts / max_pts))
                            arr = arr[::step]
                        self._batched_points.set_offsets(arr)
                        self._batched_points.set_sizes([s_val_global] * len(arr))
                        self._batched_points.set_alpha(0.95)
                        self._batched_points.set_zorder(13)
                    else:
                        self._batched_points.set_offsets(np.empty((0, 2)))
                        self._batched_points.set_alpha(0.0)
                except Exception as _bp_e:
                    # 降级：关闭批量点以避免持续异常，并恢复逐段散点可见
                    try:
                        self._use_batched_points = False
                        if hasattr(self, '_segment_points'):
                            for coll in self._segment_points:
                                try:
                                    coll.set_alpha(0.95)
                                    if coll not in getattr(self.ax, 'collections', []):
                                        self.ax.add_collection(coll)
                                except Exception:
                                    pass
                    except Exception:
                        pass

            # 更新签名缓存
            self._segment_sigs = cur_sigs
            
            # 停止后不降级线条透明度，保持与实时一致的样式（alpha 在段更新处统一为 0.85）
            if self.debug_flags.get('display_diag'):
                print(f"✅ 断续音调曲线绘制完成: {len(segments)}段 (增量更新)")
            # 周期性摘要输出（低频，避免淹没日志）
            if hasattr(self, '_maybe_summary'):
                self._maybe_summary()
            
            # 🔥 关键修复：绘制完成后必须重绘画布（重帧用强一点的触发）
            try:
                self.canvas.draw_idle()
            except Exception:
                pass
            
        except Exception as e:
            print(f"❌ 绘制断续音调曲线错误: {e}")
            # 回退到普通绘制
            if segments:
                all_times = []
                all_pitches = []
                for seg_times, seg_pitches in segments:
                    all_times.extend(seg_times)
                    all_pitches.extend(seg_pitches)
                self.pitch_line.set_data(all_times, all_pitches)
                self.canvas.draw_idle()  # 🔥 修复：回退情况下也要重绘画布
            
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
        # 控制打印频率，避免刷屏
        self.ecg_print_counter += 1
        if self.ecg_print_counter % self.ecg_print_interval == 0:
            print(f"💚 心电图模式：{self.current_linewidth:.1f}px绿线，数据点={len(times)} (第{self.ecg_print_counter}次更新)")
    
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
    
    def on_performance_mode_changed(self, mode_name):
        """性能模式改变处理"""
        if not self.performance_manager:
            print("⚠️ 性能管理器未初始化")
            return
        
        try:
            from src.audio_processing.performance_manager import PerformanceMode
            
            # 映射模式名称到枚举
            mode_mapping = {
                "安静模式": PerformanceMode.QUIET,
                "平衡模式": PerformanceMode.BALANCED,
                "高性能模式": PerformanceMode.HIGH_PERFORMANCE
            }
            
            if mode_name in mode_mapping:
                new_mode = mode_mapping[mode_name]
                # 防止广播回调重复执行（UI触发 → set → 广播 → 回调）
                self._handling_local_mode_change = True
                success = self.performance_manager.set_performance_mode(new_mode)
                try:
                    if success:
                        self.current_performance_mode = new_mode
                        
                        # 获取新的配置
                        config = self.performance_manager.get_current_config()
                        
                        # 应用配置到音频处理器（如果存在）
                        if hasattr(self, 'audio_processor') and self.audio_processor:
                            self.apply_performance_config_to_processor(config)
                        
                        # 获取性能优化信息
                        optimization = self.performance_manager.optimize_for_realtime()
                        
                        print(f"🎯 性能模式切换成功: {mode_name}")
                        print(f"   预期检测频率: {optimization['predicted_actual_frequency']:.1f}Hz")
                        print(f"   GPU加速: {'✅' if config.use_gpu_acceleration else '❌'}")
                        print(f"   线程数: {config.thread_pool_size}")
                        print(f"   内存缓冲: {config.memory_buffer_mb}MB")
                        
                        # 显示性能建议
                        recommendations = optimization['recommendations']
                        if recommendations:
                            print("💡 性能建议:")
                            for rec in recommendations:
                                print(f"   {rec}")
                        
                        # 更新状态显示
                        self.update_status_display()

                        # 根据性能模式调整可视化刷新节奏
                        self._apply_performance_mode_to_timers(config, new_mode)
                    else:
                        print(f"❌ 性能模式切换失败: {mode_name}")
                finally:
                    # 结束本地处理标志
                    self._handling_local_mode_change = False
            else:
                print(f"❌ 未知的性能模式: {mode_name}")
                
        except Exception as e:
            print(f"❌ 性能模式切换错误: {e}")

    def _on_global_performance_mode_changed(self, new_mode, config):
        """接收来自全局 PerformanceManager 的模式切换广播。
        任何模块触发的模式变更，都会同步到本界面、处理器与UI控件。"""
        try:
            # 若是本地UI刚触发过的切换，避免重复应用
            if getattr(self, '_handling_local_mode_change', False):
                return
            # 防止重入
            if getattr(self, '_handling_perf_broadcast', False):
                return
            self._handling_perf_broadcast = True
            # 更新内部状态
            self.current_performance_mode = new_mode
            # 同步UI下拉框但不二次触发信号
            try:
                if hasattr(self, 'performance_mode') and self.performance_mode is not None:
                    self.performance_mode.blockSignals(True)
                    self.performance_mode.setCurrentText(getattr(new_mode, 'value', str(new_mode)))
                    self.performance_mode.blockSignals(False)
            except Exception:
                pass
            # 应用到处理器与刷新节奏
            try:
                if hasattr(self, 'audio_processor') and self.audio_processor:
                    self.apply_performance_config_to_processor(config)
            except Exception:
                pass
            try:
                self._apply_performance_mode_to_timers(config, new_mode)
            except Exception:
                pass
            # 刷新状态显示
            try:
                self.update_status_display()
            except Exception:
                pass
        finally:
            self._handling_perf_broadcast = False

    def _apply_performance_mode_to_timers(self, config, mode_enum=None):
        """根据性能模式调整 UI 相关定时器与阈值。"""
        try:
            # 依据模式设定三个关键节奏：
            # - update_interval（重绘/重图）：影响绘图主循环
            # - fast_update_interval_ms（轻量轴/细节点刷新）
            # - time_update_interval（时间轴推进）
            # 目标：
            #   QUIET: 轻负载，降低刷新频率，平稳省电
            #   BALANCED: 默认现状
            #   HIGH: 略提速，但保持安全阈值避免主线程被压满
            from src.audio_processing.performance_manager import PerformanceMode
            mode = mode_enum or self.current_performance_mode or PerformanceMode.BALANCED

            if mode == PerformanceMode.QUIET:
                new_update_ms = 36   # ~27 FPS（略提速保证顺滑）
                new_fast_ms = 12     # ~83 Hz 轻量
                new_time_ms = 16     # ~60 Hz 时间轴
                min_heavy_interval = 0.030
                # 无音高发射节流（更保守）
                self._no_pitch_emit_interval_default = 0.08  # ~12.5 Hz
                # UI信号发射节流（更保守）
                self._ui_emit_min_interval_default = 0.04
                # 分段与细节点策略（更保守）
                self._segments_recompute_max_age_s = 0.14
                self._segments_large_shift_threshold = 0.08
                self._batched_points_cap_light = 900
                self._batched_points_cap_heavy = 1200
                # 平滑时间轴参数（更温和）
                self._smooth_strength = 0.75
                self._smooth_max_step = 0.05
                # push重绘触发因子（更保守）
                self._push_heavy_factor = 0.98
            elif mode == PerformanceMode.HIGH_PERFORMANCE:
                # 更激进但保持安全余量
                new_update_ms = 18   # ~55 FPS（接近60FPS）
                new_fast_ms = 6      # ~166 Hz 轻量
                new_time_ms = 10     # ~100 Hz 时间轴
                min_heavy_interval = 0.018
                # 无音高发射节流（更积极以维持高密度时间线）
                self._no_pitch_emit_interval_default = 0.03  # ~33 Hz
                # UI信号发射节流（更积极）
                self._ui_emit_min_interval_default = 0.02
                # 分段与细节点策略（更积极，保证密度&实时感）
                self._segments_recompute_max_age_s = 0.06
                self._segments_large_shift_threshold = 0.05
                self._batched_points_cap_light = 1800
                self._batched_points_cap_heavy = 2400
                # 平滑时间轴参数（更迅速）
                self._smooth_strength = 0.95
                self._smooth_max_step = 0.08
                # push重绘触发因子（更积极）
                self._push_heavy_factor = 0.88
            else:
                # BALANCED
                new_update_ms = 24   # ~41 FPS
                new_fast_ms = 10     # ~100 Hz 轻量
                new_time_ms = 12     # ~83 Hz 时间轴
                min_heavy_interval = 0.022
                # 无音高发射节流（折中略提速，提升时间线连续性）
                self._no_pitch_emit_interval_default = 0.04  # ~25 Hz
                # UI信号发射节流（折中）
                self._ui_emit_min_interval_default = 0.03
                # 分段与细节点策略（折中）
                self._segments_recompute_max_age_s = 0.09
                self._segments_large_shift_threshold = 0.06
                self._batched_points_cap_light = 1200
                self._batched_points_cap_heavy = 1600
                # 平滑时间轴参数（折中）
                self._smooth_strength = 0.90
                self._smooth_max_step = 0.06
                # push重绘触发因子（适中）
                self._push_heavy_factor = 0.93

            # 应用并尽量无闪断地重启定时器
            try:
                if hasattr(self, 'update_interval'):
                    self.update_interval = int(new_update_ms)
                if hasattr(self, 'update_timer') and self.update_timer is not None:
                    self.update_timer.stop()
                    self.update_timer.start(self.update_interval)
            except Exception:
                pass

            try:
                self.fast_update_interval_ms = int(new_fast_ms)
                if hasattr(self, 'fast_update_timer') and self.fast_update_timer is not None:
                    self.fast_update_timer.stop()
                    self.fast_update_timer.start(self.fast_update_interval_ms)
            except Exception:
                pass

            try:
                self.time_update_interval = int(new_time_ms)
                if hasattr(self, 'time_update_timer') and self.time_update_timer is not None and self.is_recording_active:
                    # 仅在计时活动时调整，避免未启动状态误操作
                    self.time_update_timer.stop()
                    self.time_update_timer.start(self.time_update_interval)
            except Exception:
                pass

            # 更新重绘最小间隔阈值
            try:
                self._min_heavy_interval = float(min_heavy_interval)
            except Exception:
                pass

            # 打印一次精简反馈
            print(f"🛠️ 已应用性能模式到定时器: 绘制={new_update_ms}ms 轻量={new_fast_ms}ms 时间轴={new_time_ms}ms")
        except Exception as e:
            print(f"⚠️ 应用模式到定时器失败: {e}")
    
    def apply_performance_config_to_processor(self, config):
        """将性能配置应用到音频处理器"""
        try:
            # 同步YIN阈值到本类，确保简化YIN使用一致阈值
            try:
                self.yin_threshold = float(getattr(config, 'yin_threshold', getattr(self, 'yin_threshold', 0.12)))
            except Exception:
                pass
            if hasattr(self.audio_processor, 'chunk_size'):
                # 更新块大小
                old_chunk_size = self.audio_processor.chunk_size
                self.audio_processor.chunk_size = config.chunk_size
                print(f"🔧 更新块大小: {old_chunk_size} → {config.chunk_size}")
            
            # 更新增强处理器的参数（如果存在）
            if hasattr(self.audio_processor, 'enhanced_yin_processor'):
                if hasattr(self.audio_processor.enhanced_yin_processor, 'yin_threshold'):
                    self.audio_processor.enhanced_yin_processor.yin_threshold = config.yin_threshold
                    print(f"🔧 更新YIN阈值: {config.yin_threshold}")
            
            # 设置GPU加速（如果可用）
            if config.use_gpu_acceleration and self.gpu_processor and self.gpu_processor.is_gpu_available():
                # 启用GPU加速标志
                self.audio_processor.use_gpu_acceleration = True
                print("🚀 启用GPU加速")
            else:
                # 禁用GPU加速
                if hasattr(self.audio_processor, 'use_gpu_acceleration'):
                    self.audio_processor.use_gpu_acceleration = False
                print("💻 使用CPU处理")

            # 同步到统一音高服务
            try:
                if self.pitch_service and config is not None:
                    # 为便携性补充 mode_name 字段
                    if not hasattr(config, 'mode_name'):
                        try:
                            # 粗略推断
                            mode_name = getattr(self, 'current_performance_mode', None)
                            if mode_name:
                                setattr(config, 'mode_name', str(getattr(mode_name, 'name', mode_name)))
                        except Exception:
                            pass
                    self.pitch_service.apply_config(config)
            except Exception as _e:
                print(f"⚠️ 同步 PitchDetectionService 配置失败: {_e}")
            
        except Exception as e:
            print(f"⚠️ 应用性能配置失败: {e}")
    
    def show_linewidth_dialog(self):
        """显示线条粗细设置对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("线条粗细设置")
        dialog.setModal(True)
        dialog.setFixedSize(300, 150)
        dialog.setStyleSheet("""
            QDialog {
                background: #2D2D2D;
                color: white;
            }
            QLabel {
                color: white;
                font-size: 12px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #606060;
                height: 6px;
                background: #404040;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0078D4;
                border: 1px solid #0066B2;
                width: 16px;
                height: 16px;
                border-radius: 8px;
                margin: -5px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #106EBE;
            }
            QPushButton {
                background: #0078D4;
                border: none;
                color: white;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #106EBE;
            }
            QPushButton:pressed {
                background: #005A9E;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("调整线条粗细")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title_label)
        
        # 滑块
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(QLabel("细"))
        
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(1, 50)  # 0.1px到5.0px
        slider.setValue(int(self.current_linewidth * 10))
        slider_layout.addWidget(slider)
        
        slider_layout.addWidget(QLabel("粗"))
        layout.addLayout(slider_layout)
        
        # 当前值显示
        value_label = QLabel(f"当前: {self.current_linewidth:.1f}px")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_label)
        
        # 更新值显示
        def update_value():
            value = slider.value() / 10.0
            value_label.setText(f"当前: {value:.1f}px")
            
        slider.valueChanged.connect(update_value)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        reset_btn = QPushButton("重置")
        reset_btn.clicked.connect(lambda: slider.setValue(6))  # 默认0.6px
        button_layout.addWidget(reset_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_value = slider.value() / 10.0
            self.current_linewidth = new_value
            self.apply_linewidth(new_value)
            self.linewidth_btn.setText(f"线条: {new_value:.1f}px")
            print(f"🖊️ 线条粗细设置为: {new_value:.1f}px")

    def show_frequency_range_dialog(self):
        """显示频率范围设置对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("频率范围设置")
        dialog.setModal(True)
        dialog.setFixedSize(400, 250)
        dialog.setStyleSheet("""
            QDialog {
                background: #2D2D2D;
                color: white;
            }
            QLabel {
                color: white;
                font-size: 12px;
            }
            QSpinBox {
                background: #404040;
                border: 1px solid #606060;
                color: white;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
                min-height: 30px;
                min-width: 100px;
            }
            QSpinBox:focus {
                border: 2px solid #0078D4;
            }
            QSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 22px;
                height: 15px;
                background: #505050;
                border: 1px solid #606060;
                border-top-right-radius: 4px;
                margin: 1px;
            }
            QSpinBox::up-button:hover {
                background: #0078D4;
                border: 1px solid #0066B2;
            }
            QSpinBox::up-button:pressed {
                background: #005A9E;
            }
            QSpinBox::up-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-bottom: 5px solid white;
                width: 0;
                height: 0;
                margin: 2px;
            }
            QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 22px;
                height: 15px;
                background: #505050;
                border: 1px solid #606060;
                border-bottom-right-radius: 4px;
                margin: 1px;
            }
            QSpinBox::down-button:hover {
                background: #0078D4;
                border: 1px solid #0066B2;
            }
            QSpinBox::down-button:pressed {
                background: #005A9E;
            }
            QSpinBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                width: 0;
                height: 0;
                margin: 2px;
            }
            QPushButton {
                background: #0078D4;
                border: none;
                color: white;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #106EBE;
            }
            QPushButton:pressed {
                background: #005A9E;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("设置音频检测频率范围")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title_label)
        
        # 说明
        info_label = QLabel("人声范围通常为80-1047Hz (C2-C6)，可根据需要调整")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("color: #AAAAAA; font-size: 10px;")
        layout.addWidget(info_label)
        
        # 获取当前频率范围
        if self.audio_processor:
            current_min, current_max = self.audio_processor.get_frequency_range()
        else:
            current_min, current_max = 80, 1047  # 默认值
            print("⚠️ 音频处理器未设置，使用默认频率范围")
        
        # 输入区域
        input_layout = QVBoxLayout()
        
        # 最小频率
        min_layout = QHBoxLayout()
        min_layout.addWidget(QLabel("最小频率:"))
        min_spin = QSpinBox()
        min_spin.setRange(50, 200)
        min_spin.setValue(int(current_min))
        min_spin.setSuffix(" Hz")
        min_spin.setMinimumWidth(100)
        min_spin.setMinimumHeight(30)
        min_layout.addWidget(min_spin)
        min_layout.addWidget(QLabel("(50-200Hz)"))
        input_layout.addLayout(min_layout)
        
        # 最大频率
        max_layout = QHBoxLayout()
        max_layout.addWidget(QLabel("最大频率:"))
        max_spin = QSpinBox()
        max_spin.setRange(500, 3000)
        max_spin.setValue(int(current_max))
        max_spin.setSuffix(" Hz")
        max_spin.setMinimumWidth(100)
        max_spin.setMinimumHeight(30)
        max_layout.addWidget(max_spin)
        max_layout.addWidget(QLabel("(500-3000Hz)"))
        input_layout.addLayout(max_layout)
        
        layout.addLayout(input_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        preset_btn = QPushButton("人声预设")
        preset_btn.clicked.connect(lambda: (min_spin.setValue(80), max_spin.setValue(1047)))
        button_layout.addWidget(preset_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            min_freq = min_spin.value()
            max_freq = max_spin.value()
            
            # 验证范围
            if min_freq >= max_freq:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "错误", "最小频率必须小于最大频率！")
                return
                
            # 应用新设置到音频处理器
            if self.audio_processor:
                self.audio_processor.set_frequency_range(min_freq, max_freq)
                self.frequency_range_btn.setText(f"频率: {min_freq}-{max_freq}Hz")
                print(f"🎵 频率范围设置为: {min_freq}-{max_freq}Hz")
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "错误", "音频处理器未初始化！")

    def on_linewidth_preset_changed(self, preset_text):
        """线条粗细预设改变"""
        # 这个函数现在已经不使用了，保留以防有遗留引用
        pass

    def on_linewidth_slider_changed(self, value):
        """线条粗细滑块改变"""
        # 这个函数现在已经不使用了，保留以防有遗留引用
        pass
    
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
        # 重新获取并应用 zoom profile
        self._apply_zoom_profile_center()
        try:
            prof = getattr(self, '_current_zoom_profile', None) or self._get_zoom_profile()
            print(f"[ZOOM CHANGED] slider_value={value} zoom={self.zoom_level:.2f} mode={prof.get('mode')}")
        except Exception:
            pass
        self.update_preset_button_highlight()
        # 刷新显示
        self.update_axis_ranges()
        self.update_scrollbars()
        if hasattr(self, 'canvas'):
            self.canvas.draw()
        self.update_status_display()
    
    def set_zoom_preset(self, zoom_level):
        """设置预设缩放级别"""
        # 更新滑块位置
        slider_value = int(zoom_level * 10)
        # 防止触发 valueChanged -> on_zoom_changed 造成双重应用与日志混乱
        if hasattr(self, 'zoom_slider'):
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(slider_value)
            self.zoom_slider.blockSignals(False)
        # 更新缩放级别
        self.zoom_level = zoom_level
        self.zoom_label.setText(f"{self.zoom_level:.1f}x")
        # 应用缩放配置（可能重置中心）
        self._apply_zoom_profile_center()
        # 若进入可滚动模式且之前被锁定，则自动解锁以避免用户误以为无效
        prof_tmp = getattr(self, '_current_zoom_profile', None) or self._get_zoom_profile()
        if not prof_tmp.get('disable_v_scroll') and getattr(self, 'freeze_y_center', False):
            print("[AUTO UNLOCK] 进入可滚动缩放模式，自动解除Y轴锁定")
            self.freeze_y_center = False
            self._locked_y_limits = None
        try:
            prof = getattr(self, '_current_zoom_profile', None) or self._get_zoom_profile()
            print(f"[ZOOM PRESET APPLY] preset={zoom_level} slider={slider_value} mode={prof.get('mode')} center={self.y_view_center:.2f}")
        except Exception:
            pass
        # 更新预设按钮高亮
        self.update_preset_button_highlight()

        # 更新显示
        self.update_axis_ranges()
        self.update_scrollbars()
        self.canvas.draw()

        # 显示设置信息
        preset_info = {
            0.5: "固定 C3–C5 仅显示 C3/C4/C5 主音C (禁止纵向滚动)",
            0.8: "固定 C0–C8 仅显示各八度主音C (禁止纵向滚动)",
            1.5: "可滚动 C0–C8 初始窗口 C2–C6 显示 C/F/G",
            2.5: "可滚动 C0–C8 初始窗口 C3–C5 窗口内白键 其余区域 C/F/G",
            5.0: "可滚动 C0–C8 初始窗口 C3–C5 显示全部半音"
        }

        if zoom_level in preset_info:
            if getattr(self, '_last_zoom_preset_logged', None) != zoom_level:
                print(f"[PRESET INFO] {zoom_level}x -> {preset_info[zoom_level]}")
                self._last_zoom_preset_logged = zoom_level

    def reset_view(self):
        """重置视图到初始观感（仅视图相关：时间偏移/缩放/Y中心），不改变其他设置。"""
        try:
            # 时间轴回到起点
            self.time_offset = 0.0
            # 清除平滑/历史渲染窗口缓存
            if hasattr(self, '_smoothed_xlim'):
                self._smoothed_xlim = None
            if hasattr(self, '_last_render_window'):
                try:
                    delattr(self, '_last_render_window')
                except Exception:
                    pass
            # 恢复Y轴中心
            self.y_view_center = getattr(self, '_initial_y_center', 4.0)
            # 恢复缩放
            self.zoom_level = 1.0
            if hasattr(self, 'zoom_slider'):
                self.zoom_slider.blockSignals(True)
                self.zoom_slider.setValue(10)
                self.zoom_slider.blockSignals(False)
            if hasattr(self, 'zoom_label'):
                self.zoom_label.setText("1.0x")
            # 刷新坐标与界面
            self.update_axis_ranges()
            try:
                self.update_scrollbars()
            except Exception:
                pass
            if hasattr(self, 'canvas'):
                self.canvas.draw_idle()
            if hasattr(self, 'update_status_display'):
                self.update_status_display()
            print("🔄 视图已重置（time_offset=0, zoom=1.0x, y_center 初始）")
        except Exception as e:
            print(f"⚠️ reset_view 失败: {e}")

    def get_vertical_compression_factor(self, zoom_level: float) -> float:
        """(已废弃) 兼容旧代码的占位。现改用 compute_half_range。"""
        return 1.0

    def compute_half_range(self) -> float:
        """根据当前 zoom_level 返回可见半范围(八度)。
        设计目标：
        - zoom 越小 -> 只看核心/稀疏信息（半范围较小）
        - zoom 越大 -> 展示更多音调，直到 5.0 全可视 (0-8 八度)
        半范围 *2 即总高度。
        """
        z = self.zoom_level
        # 保持与 zoom preset 语义一致：
        if z <= 0.55:   # 0.5x C3-C5
            return 1.0
        if z <= 0.95:   # 0.8x 全区
            return 4.0
        if z <= 1.9:    # 1.5x C2-C6
            return 2.0
        if z <= 3.2:    # 2.5x C3-C5
            return 1.0
        return 1.0      # 5.0x C3-C5 细节（保持）

    # === 新增：缩放配置与标签过滤 ===
    def _get_zoom_profile(self):
        """返回当前 zoom 的标签/网格策略配置。
        返回 dict: {
          'mode': str,
          'note_filter': callable(octave:int,semitone:int)->bool,
          'force_center': float|None (进入该缩放首次时重置中心)
        }"""
        z = self.zoom_level
        if z <= 0.55:  # 0.5x 固定 C3-C5 只主音
            return {
                'mode': 'zoom_0_5',
                'force_center': 4.0,
                'disable_v_scroll': True,
                'note_filter': lambda o, s: (s == 0 and 3 <= o <= 5)
            }
        if z <= 0.95:  # 0.8x 全区主音 C0-C8
            return {
                'mode': 'zoom_0_8',
                'force_center': 4.0,
                'disable_v_scroll': True,
                'note_filter': lambda o, s: s == 0
            }
        if z <= 1.9:  # 1.5x C/F/G 可滚动
            return {
                'mode': 'zoom_1_5',
                'force_center': 4.0,
                'disable_v_scroll': False,
                'note_filter': lambda o, s: s in {0,5,7}
            }
        if z <= 3.2:  # 2.5x 窗口内 C3-C5 自然音，其他区域 C/F/G
            return {
                'mode': 'zoom_2_5',
                'force_center': 4.0,
                'disable_v_scroll': False,
                'note_filter': lambda o, s: ((3 <= o <= 5 and s in {0,2,4,5,7,9,11}) or (s in {0,5,7}))
            }
        # 5.0x 全部半音
        return {
            'mode': 'zoom_5_0',
            'force_center': 4.0,
            'disable_v_scroll': False,
            'note_filter': lambda o, s: True
        }

    def _should_show_note_by_profile(self, octave:int, semitone:int) -> bool:
        profile = getattr(self, '_current_zoom_profile', None)
        if not profile:
            profile = self._get_zoom_profile()
            self._current_zoom_profile = profile
        return profile['note_filter'](octave, semitone)

    def _apply_zoom_profile_center(self):
        profile = self._get_zoom_profile()
        # 如果模式变化或首次进入该模式，重设中心
        prev_mode = getattr(self, '_prev_zoom_mode', None)
        if profile['mode'] != prev_mode:
            fc = profile.get('force_center')
            if fc is not None and not getattr(self, '_user_overrode_center', False):
                self.y_view_center = fc
            # 针对禁止滚动模式，强制窗口固定：
            if profile.get('disable_v_scroll'):
                # 0.5x: 固定显示 C3-C5 (中心=4 半高=1) compute_half_range() 已返回1
                # 0.8x: 全区 C0-C8 (中心=4 半高=4)
                # 这里仅确保 center 正确，范围计算在 update_axis_ranges 中完成
                pass
        self._prev_zoom_mode = profile['mode']
        self._current_zoom_profile = profile

    # 修改 set_zoom_preset 进入时应用 profile

    def clamp_y_center(self, half_range: float):
        """防止拖动后中心越界，确保显示窗口保持在 0-8 八度范围。"""
        min_center = half_range
        max_center = 8.0 - half_range
        if self.y_view_center < min_center:
            self.y_view_center = min_center
        elif self.y_view_center > max_center:
            self.y_view_center = max_center
    
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
            from PyQt6.QtWidgets import QInputDialog as _QID
        except ImportError:
            try:
                from PyQt5.QtWidgets import QInputDialog as _QID
            except ImportError:
                print("❌ 无法导入QInputDialog")
                return
        
        # 弹出输入对话框
        value, ok = _QID.getDouble(
            self,
            "设置自定义最大历史时间",
            "请输入最大历史时间（秒）:",
            value=self.max_history_time,
            min=60,
            max=3600,
            decimals=0,
        )
        if ok:
            self.set_max_history_time(value)
        
        self.zoom_level = 1.0  # 重置缩放级别
        
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
            # 新缩放：compute_half_range() 返回当前半范围
            actual_range = self.compute_half_range()
            
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
    
    def clear_data_simple_legacy(self):  # 不再绑定按钮，保留兼容（不要覆盖高级 clear_data）
        """[LEGACY - DO NOT USE] 旧版简化清除：仅清空缓存与主曲线，不做深度 artist 清理/网格延迟重建。"""
        try:
            self.pitch_data.clear(); self.time_data.clear(); self.confidence_data.clear(); self.note_data.clear()
            self.start_time = None; self.current_global_time = 0.0; self.last_pitch_time = 0; self.is_recording_active = False
            if hasattr(self, 'time_update_timer'): self.time_update_timer.stop()
            if hasattr(self, 'pitch_line') and self.pitch_line is not None:
                try: self.pitch_line.set_data([], [])
                except: pass
            if hasattr(self, 'canvas'): self.canvas.draw_idle()
            try: self.update_status_display()
            except: pass
            print("[clear_data_simple_legacy] 已执行 (仅基础清空) -> 建议使用高级 clear_data() 实现彻底深度清除")
        except Exception as e:
            print(f"[clear_data_simple_legacy] 执行出错: {e}")
    
    def start_time_tracking(self):
        """开始时间追踪（支持断续音调曲线）"""
        self.start_time = time.time()
        self.current_global_time = 0.0
        self.is_recording_active = True
        # 启动时间更新定时器
        if hasattr(self, 'time_update_timer'):
            self.time_update_timer.start(self.time_update_interval)
        # 重置自动滚动偏移
        self.time_offset = 0.0
        if hasattr(self, 'update_status_display'):
            self.update_status_display()
    def update_time_axis(self):
        """更新时间轴（支持断续音调曲线）"""
        if not self.is_recording_active or self.start_time is None:
            return
        
        try:
            # 更新全局时间
            self.current_global_time = time.time() - self.start_time
            
            # 手动滚动冻结逻辑：最近 2 秒用户交互则暂不自动滚动
            manual_freeze = (time.time() - getattr(self, '_last_manual_scroll_time', 0)) < 2.0

            if self.auto_follow and self.auto_scroll_enabled and not manual_freeze:
                if self.current_global_time > self.center_display_time:
                    new_offset = self.current_global_time - self.center_display_time
                    # 直接更新 offset，但使用平滑 xlim 过渡
                    self.time_offset = min(new_offset, max(0, self.max_history_time - self.time_window))
                    try:
                        if hasattr(self, 'ax'):
                            x_min = self.time_offset
                            x_max = self.time_offset + self.time_window
                            self._smooth_set_xlim(x_min, x_max, strength=float(getattr(self,'_smooth_strength',0.9)), max_step=float(getattr(self,'_smooth_max_step',0.05)))
                    except Exception:
                        self.update_axis_ranges()
                else:
                    # 初期阶段保持 offset=0，窗口缩放在 update_display 中处理
                    if self.time_offset != 0.0:
                        self.time_offset = 0.0
                        self.update_axis_ranges()
            
            # 每秒更新一次状态显示
            if hasattr(self, '_last_status_update'):
                if self.current_global_time - self._last_status_update >= 1.0:
                    self.update_status_display()
                    self._last_status_update = self.current_global_time
            else:
                self._last_status_update = self.current_global_time
                
        except Exception as e:
            print(f"❌ 时间轴更新错误: {e}")
    
    def show_monitor_context_menu(self, position):
        """显示监听按钮的右键菜单（增强版：包含设备选择）"""
        try:
            from PyQt6.QtWidgets import QMenu, QWidgetAction, QLabel
            from PyQt6.QtCore import Qt
            
            context_menu = QMenu(self)
            context_menu.setStyleSheet("""
                QMenu {
                    background-color: #2b2b2b;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 2px;
                    min-width: 280px;
                }
                QMenu::item {
                    background-color: transparent;
                    color: white;
                    padding: 8px 20px;
                    border-radius: 2px;
                }
                QMenu::item:selected {
                    background-color: #1976D2;
                }
                QMenu::item:disabled {
                    color: #888888;
                }
                QMenu::separator {
                    height: 1px;
                    background: #555555;
                    margin: 4px 0px;
                }
            """)
            
            # 🎯 设备选择子菜单
            device_menu = QMenu("🎧 选择音频设备", self)
            device_menu.setStyleSheet(context_menu.styleSheet())
            
            # 获取可用的音频设备配置
            try:
                main_window = self.get_main_window()
                if main_window and hasattr(main_window, 'audio_processor'):
                    # 获取WASAPI配置
                    wasapi_configs = main_window.audio_processor._get_optimal_wasapi_configs()
                    
                    # 添加已验证的最佳配置（优先显示）
                    verified_config = main_window.audio_processor._load_verified_optimal_config()
                    if verified_config:
                        device_action = device_menu.addAction(f"⭐ {verified_config['name']} (推荐)")
                        device_action.triggered.connect(lambda checked, config=verified_config: self.switch_to_device_config(config))
                        device_menu.addSeparator()
                    
                    # 按质量评分排序显示其他配置
                    sorted_configs = sorted(wasapi_configs, key=lambda x: x.get('quality_score', 0), reverse=True)
                    
                    for config in sorted_configs[:8]:  # 限制显示最多8个配置
                        quality_score = config.get('quality_score', 0)
                        latency_ms = config['blocksize'] / config['samplerate'] * 1000
                        
                        # 设备信息格式化
                        device_name = config['name']
                        if len(device_name) > 25:
                            device_name = device_name[:22] + "..."
                        
                        # 质量指示器
                        if quality_score >= 90:
                            quality_icon = "🏆"
                        elif quality_score >= 80:
                            quality_icon = "🥇"
                        elif quality_score >= 70:
                            quality_icon = "🥈"
                        else:
                            quality_icon = "🥉"
                        
                        menu_text = f"{quality_icon} {device_name}"
                        menu_text += f"\n   {config['samplerate']}Hz/{config['blocksize']}样本 ({latency_ms:.2f}ms)"
                        
                        device_action = device_menu.addAction(menu_text)
                        device_action.triggered.connect(lambda checked, config=config: self.switch_to_device_config(config))
                    
                    # 添加默认DirectSound选项
                    device_menu.addSeparator()
                    directsound_action = device_menu.addAction("🔧 DirectSound (兼容模式)")
                    directsound_action.triggered.connect(lambda: self.switch_to_directsound_mode())
                
                else:
                    # 如果无法获取配置，显示占位项
                    device_menu.addAction("⚠️ 无法获取设备列表").setEnabled(False)
                    
            except Exception as e:
                print(f"⚠️ 获取音频设备列表失败: {e}")
                device_menu.addAction("❌ 设备列表获取失败").setEnabled(False)
            
            context_menu.addMenu(device_menu)
            context_menu.addSeparator()
            
            # 🎚️ 音量控制选项
            volume_action = context_menu.addAction("🎚️ 调节音量")
            volume_action.triggered.connect(self.show_volume_control)

            # 🌿 自然耳返强度
            natural_action = context_menu.addAction("🌿 自然耳返强度…")
            natural_action.triggered.connect(self.show_natural_earback_dialog)

            # RAW直通（最小处理）开关（可勾选）
            raw_label = "🧪 RAW直通（最小处理）"
            raw_action = context_menu.addAction(raw_label)
            raw_action.setCheckable(True)
            raw_action.setChecked(bool(getattr(self, 'monitor_raw_mode', False)))
            def on_raw_toggled(checked: bool):
                self.monitor_raw_mode = bool(checked)
                state = "开" if checked else "关"
                self._log_rate_limit("raw_mode_toggle", f"🧪 RAW直通: {state}", 0.6, 1)
            raw_action.toggled.connect(on_raw_toggled)

            # 头房预设子菜单
            headroom_menu = QMenu("📉 头房(dB)", self)
            headroom_menu.setStyleSheet(context_menu.styleSheet())
            def set_headroom(db):
                try:
                    self.headroom_db = float(db)
                    self._log_rate_limit("headroom_set", f"📉 头房: {self.headroom_db:.1f} dB", 0.8, 1)
                except Exception:
                    pass
            # 预设项
            for db in (-4.0, -6.0, -8.0):
                label = f"{int(db)} dB"
                act = headroom_menu.addAction(label)
                act.triggered.connect(lambda checked=False, v=db: set_headroom(v))
            # 当前值提示
            cur_db = float(getattr(self, 'headroom_db', -6.0))
            headroom_menu.addSeparator()
            headroom_menu.addAction(f"当前: {cur_db:.1f} dB").setEnabled(False)

            context_menu.addMenu(headroom_menu)
            
            # 📊 实时状态选项
            status_action = context_menu.addAction("📊 查看实时状态")
            status_action.triggered.connect(self.show_audio_status)
            
            context_menu.addSeparator()
            
            # 🔄 配置管理选项
            refresh_action = context_menu.addAction("🔄 刷新设备列表")
            refresh_action.triggered.connect(self.refresh_device_list)
            
            # 重置音量选项
            reset_action = context_menu.addAction("🔄 重置音量")
            reset_action.triggered.connect(self.reset_volume)
            
            context_menu.addSeparator()
            
            # 🛠️ 高级选项
            advanced_menu = QMenu("🛠️ 高级选项", self)
            advanced_menu.setStyleSheet(context_menu.styleSheet())
            
            # AI降噪选项
            noise_action = advanced_menu.addAction("🤖 AI降噪 (开发中)")
            noise_action.setEnabled(False)
            
            # 缓冲区优化
            buffer_action = advanced_menu.addAction("⚡ 缓冲区优化")
            buffer_action.triggered.connect(self.optimize_buffer_settings)
            
            # 延迟测试
            latency_action = advanced_menu.addAction("🕐 延迟测试")
            latency_action.triggered.connect(self.test_audio_latency)
            
            context_menu.addMenu(advanced_menu)
            
            # 显示菜单
            context_menu.exec(self.monitor_button.mapToGlobal(position))
            
        except Exception as e:
            print(f"❌ 显示右键菜单失败: {e}")
    
    def show_volume_control(self):
        """显示音量控制对话框"""
        try:
            # 获取主窗口的引用
            main_window = self.get_main_window()
            if main_window and hasattr(main_window, 'show_volume_control'):
                main_window.show_volume_control()
            else:
                print("⚠️ 无法找到主窗口或音量控制方法")
        except Exception as e:
            print(f"❌ 显示音量控制失败: {e}")
    
    def reset_volume(self):
        """重置音量到100%"""
        try:
            # 获取主窗口的引用
            main_window = self.get_main_window()
            if main_window and hasattr(main_window, 'reset_volume'):
                main_window.reset_volume()
            else:
                print("⚠️ 无法找到主窗口或重置音量方法")
        except Exception as e:
            print(f"❌ 重置音量失败: {e}")
    
    def show_natural_earback_dialog(self):
        """显示自然耳返强度调节对话框"""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QSlider, QDialogButtonBox
            from PyQt6.QtCore import Qt

            dlg = QDialog(self)
            dlg.setWindowTitle("自然耳返强度")
            dlg.setModal(True)
            dlg.setStyleSheet("""
                QDialog { background-color: #2b2b2b; }
                QLabel { color: white; }
            """)

            layout = QVBoxLayout(dlg)
            label = QLabel("越大越干净（但更加工）；越小越原味（但可能略沙）")
            layout.addWidget(label)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            current = int(max(0.0, min(1.0, getattr(self, 'natural_earback_strength', 0.6))) * 100)
            slider.setValue(current)
            layout.addWidget(slider)

            value_label = QLabel(f"当前: {current}")
            layout.addWidget(value_label)

            def on_change(v):
                value_label.setText(f"当前: {v}")
            slider.valueChanged.connect(on_change)

            btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            layout.addWidget(btns)

            def accept():
                self.natural_earback_strength = slider.value() / 100.0
                self._log_rate_limit("natural_strength_set", f"🌿 自然耳返强度: {self.natural_earback_strength:.2f}", 0.8, 1)
                dlg.accept()
            def reject():
                dlg.reject()
            btns.accepted.connect(accept)
            btns.rejected.connect(reject)

            dlg.resize(380, 140)
            dlg.exec()
        except Exception as e:
            print(f"❌ 显示自然耳返强度对话框失败: {e}")

    def get_main_window(self):
        """获取主窗口的引用"""
        try:
            # 遍历父对象查找主窗口
            parent = self.parent()
            while parent:
                if isinstance(parent, QMainWindow):
                    return parent
                parent = parent.parent()
            return None
        except Exception as e:
            print(f"❌ 获取主窗口失败: {e}")
            return None
    
    def switch_to_device_config(self, config):
        """切换到指定的设备配置"""
        try:
            import sounddevice as sd
            main_window = self.get_main_window()
            if main_window and hasattr(main_window, 'audio_processor'):
                print(f"🎯 切换到设备配置: {config['name']}")
                print(f"   设备: {config.get('device', 'N/A')} ({config.get('samplerate', 0)}Hz/{config.get('blocksize', 0)}样本)")
                
                # 🔧 验证设备可用性（改进版）
                device_available = True
                fallback_needed = False
                
                if 'device' in config and config['device'] is not None:
                    device_available = main_window.audio_processor._verify_device_availability(config['device'])
                    if not device_available:
                        print(f"⚠️ 设备{config['device']}不可用，需要创建兼容配置")
                        fallback_needed = True
                        
                        # 🎯 对HECATE设备尝试降级配置
                        original_config = config.copy()
                        if 'hecate' in config.get('name', '').lower():
                            print("🔧 为HECATE设备尝试降级配置...")
                            
                            # 降级配置序列
                            fallback_configs = [
                                # 使用WASAPI共享模式（最稳定）
                                {**config, 'settings': sd.WasapiSettings(exclusive=False), 
                                 'name': config['name'] + ' (WASAPI共享)', 'blocksize': 256},
                                # 降低采样率
                                {**config, 'samplerate': 48000, 'blocksize': 256,
                                 'name': config['name'] + ' (降级48kHz)'},
                                # DirectSound模式
                                {'name': f"{config['name']} (DirectSound兼容)",
                                 'samplerate': 48000, 'blocksize': 256, 'device': config['device'],
                                 'settings': None, 'mode': 'directsound'}
                            ]
                            
                            for i, fallback in enumerate(fallback_configs):
                                print(f"   尝试降级配置 {i+1}/{len(fallback_configs)}: {fallback['name']}")
                                if main_window.audio_processor._verify_device_availability(fallback.get('device')):
                                    config = fallback
                                    fallback_needed = False
                                    device_available = True
                                    print(f"✅ HECATE降级配置成功: {config['name']}")
                                    break
                        
                        # 如果所有降级都失败，创建通用DirectSound配置
                        if fallback_needed:
                            config = {
                                'name': f"{original_config['name']} (通用兼容)",
                                'samplerate': min(original_config.get('samplerate', 48000), 48000),
                                'blocksize': max(original_config.get('blocksize', 128), 256),
                                'mode': 'directsound',
                                'device': None,  # 使用默认设备
                                'settings': None
                            }
                            print(f"🔄 已创建通用兼容配置: {config['name']}")

                # 如果正在监听，先停止
                if hasattr(main_window, 'is_monitoring') and main_window.is_monitoring:
                    print("🔄 停止当前监听以切换设备...")
                    main_window.stop_monitoring()
                    
                # 设置新的设备配置
                main_window.audio_processor._selected_device_config = config
                
                # 🎯 智能重启监听（带重试机制）
                if hasattr(main_window, 'is_monitoring'):
                    print("🚀 使用新设备配置重启监听...")
                    
                    # 尝试3次启动监听
                    success = False
                    for attempt in range(3):
                        print(f"   启动尝试 {attempt + 1}/3...")
                        success = main_window.start_monitoring()
                        if success:
                            break
                        elif attempt < 2:  # 不是最后一次尝试
                            print(f"   启动失败，等待重试...")
                            import time
                            time.sleep(0.5)  # 短暂等待
                    
                    if success:
                        print(f"✅ 已成功切换到: {config['name']}")
                        
                        # 保存配置（只在成功时保存，且不是回退配置）
                        if device_available and not fallback_needed:
                            self.save_preferred_device_config(config)
                    else:
                        print(f"❌ 多次尝试后仍无法启动: {config['name']}")
                        print("🔄 最后尝试：DirectSound兼容模式...")
                        self.switch_to_directsound_mode()
                else:
                    print(f"✅ 设备配置已设置: {config['name']}")
                    
            else:
                print("⚠️ 无法获取音频处理器引用")
        except Exception as e:
            print(f"❌ 切换设备配置失败: {e}")
            import traceback
            traceback.print_exc()
            # 发生错误时回退到DirectSound
            print("🔄 发生异常，回退到DirectSound兼容模式...")
            self.switch_to_directsound_mode()
    
    def switch_to_directsound_mode(self):
        """切换到DirectSound兼容模式"""
        try:
            main_window = self.get_main_window()
            if main_window and hasattr(main_window, 'audio_processor'):
                print("🔧 切换到DirectSound兼容模式")
                
                # 如果正在监听，先停止
                if hasattr(main_window, 'is_monitoring') and main_window.is_monitoring:
                    main_window.stop_monitoring()
                
                # 创建DirectSound配置
                directsound_config = {
                    'name': 'DirectSound兼容模式',
                    'device': None,
                    'samplerate': 48000,
                    'blocksize': 128,
                    'settings': None,
                    'priority': 'high-compatibility',
                    'mode': 'directsound'
                }
                
                # 设置配置
                main_window.audio_processor._selected_device_config = directsound_config
                
                # 重新启动监听（如果之前在监听）
                if hasattr(main_window, 'is_monitoring') and main_window.is_monitoring:
                    main_window.start_monitoring()
                
                print("✅ 已切换到DirectSound模式")
            else:
                print("⚠️ 无法获取音频处理器引用")
        except Exception as e:
            print(f"❌ 切换到DirectSound模式失败: {e}")
    
    def show_audio_status(self):
        """显示实时音频状态"""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton
            from PyQt6.QtCore import QTimer
            
            # 创建状态对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("📊 实时音频状态")
            dialog.setModal(False)
            dialog.resize(500, 400)
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #1e1e1e;
                    color: white;
                }
                QLabel {
                    color: #FFFFFF;
                    font-weight: bold;
                    margin: 5px;
                }
                QTextEdit {
                    background-color: #2d2d2d;
                    color: #FFFFFF;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    font-family: 'Consolas', monospace;
                    font-size: 11px;
                }
                QPushButton {
                    background: #1976D2;
                    border: 1px solid #2196F3;
                    border-radius: 4px;
                    padding: 8px 16px;
                    color: white;
                    font-size: 12px;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background: #1E88E5;
                }
            """)
            
            layout = QVBoxLayout(dialog)
            
            # 状态标题
            title_label = QLabel("🎧 当前音频监听状态")
            layout.addWidget(title_label)
            
            # 状态文本区域
            status_text = QTextEdit()
            status_text.setReadOnly(True)
            layout.addWidget(status_text)
            
            # 关闭按钮
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dialog.close)
            layout.addWidget(close_btn)
            
            # 更新状态函数
            def update_status():
                try:
                    main_window = self.get_main_window()
                    if main_window and hasattr(main_window, 'audio_processor'):
                        processor = main_window.audio_processor
                        
                        status_info = "📊 实时音频状态监控\n"
                        status_info += "=" * 50 + "\n\n"
                        
                        # 监听状态
                        if hasattr(main_window, 'is_monitoring'):
                            status_info += f"🎧 监听状态: {'运行中' if main_window.is_monitoring else '已停止'}\n"
                        
                        # 当前配置
                        if hasattr(processor, '_selected_device_config'):
                            config = processor._selected_device_config
                            if config:
                                status_info += f"🎯 当前设备: {config['name']}\n"
                                status_info += f"📈 采样率: {config['samplerate']} Hz\n"
                                status_info += f"📊 缓冲区: {config['blocksize']} 样本\n"
                                latency = config['blocksize'] / config['samplerate'] * 1000
                                status_info += f"⚡ 理论延迟: {latency:.2f} ms\n"
                        
                        # 音量增强状态
                        if hasattr(processor, 'intelligent_volume_booster'):
                            booster = processor.intelligent_volume_booster
                            status_info += f"\n🎚️ 智能音量增强:\n"
                            status_info += f"   状态: {'启用' if booster['enabled'] else '禁用'}\n"
                            status_info += f"   当前增益: {booster['current_gain']:.2f}x\n"
                            status_info += f"   最大增益: {booster['max_gain']:.2f}x\n"
                            status_info += f"   目标水平: {booster['target_level']:.3f}\n"
                        
                        # 设备信息
                        try:
                            import sounddevice as sd
                            devices = sd.query_devices()
                            status_info += f"\n🔌 可用音频设备数量: {len(devices)}\n"
                        except:
                            pass
                        
                        # 性能统计
                        status_info += f"\n⚡ 性能统计:\n"
                        status_info += f"   处理线程: {'活跃' if hasattr(processor, 'is_audio_processing') and processor.is_audio_processing else '停止'}\n"
                        
                        status_text.setPlainText(status_info)
                    else:
                        status_text.setPlainText("❌ 无法获取音频处理器状态")
                except Exception as e:
                    status_text.setPlainText(f"❌ 状态更新失败: {e}")
            
            # 设置定时器更新状态
            timer = QTimer()
            timer.timeout.connect(update_status)
            timer.start(1000)  # 每秒更新
            
            # 初始更新
            update_status()
            
            # 显示对话框
            dialog.exec()
            
            # 停止定时器
            timer.stop()
            
        except Exception as e:
            print(f"❌ 显示音频状态失败: {e}")
    
    def refresh_device_list(self):
        """刷新音频设备列表"""
        try:
            main_window = self.get_main_window()
            if main_window and hasattr(main_window, 'audio_processor'):
                print("🔄 正在刷新音频设备列表...")
                
                # 清除缓存的配置
                if hasattr(main_window.audio_processor, '_cached_wasapi_configs'):
                    delattr(main_window.audio_processor, '_cached_wasapi_configs')
                
                # 重新扫描设备
                try:
                    import sounddevice as sd
                    sd._terminate()
                    sd._initialize()
                    print("✅ 音频系统已重新初始化")
                except:
                    print("⚠️ 无法重新初始化音频系统，使用现有连接")
                
                # 重新获取WASAPI配置
                try:
                    configs = main_window.audio_processor._get_optimal_wasapi_configs()
                    print(f"✅ 已刷新设备列表，发现 {len(configs)} 个配置")
                except Exception as e:
                    print(f"⚠️ 刷新设备配置失败: {e}")
                
                print("✅ 设备列表刷新完成")
            else:
                print("⚠️ 无法获取音频处理器引用")
        except Exception as e:
            print(f"❌ 刷新设备列表失败: {e}")
    
    def optimize_buffer_settings(self):
        """优化缓冲区设置"""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QCheckBox
            from PyQt6.QtCore import Qt
            
            # 创建优化对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("⚡ 缓冲区优化")
            dialog.setModal(True)
            dialog.resize(400, 300)
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #1e1e1e;
                    color: white;
                }
                QLabel {
                    color: #FFFFFF;
                    margin: 5px;
                }
                QSlider::groove:horizontal {
                    border: 1px solid #555555;
                    height: 8px;
                    background: #2d2d2d;
                    margin: 2px 0;
                    border-radius: 4px;
                }
                QSlider::handle:horizontal {
                    background: #1976D2;
                    border: 1px solid #2196F3;
                    width: 18px;
                    margin: -2px 0;
                    border-radius: 9px;
                }
                QPushButton {
                    background: #1976D2;
                    border: 1px solid #2196F3;
                    border-radius: 4px;
                    padding: 8px 16px;
                    color: white;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background: #1E88E5;
                }
                QCheckBox {
                    color: white;
                    spacing: 5px;
                }
                QCheckBox::indicator:unchecked {
                    border: 1px solid #555555;
                    background: #2d2d2d;
                }
                QCheckBox::indicator:checked {
                    border: 1px solid #1976D2;
                    background: #1976D2;
                }
            """)
            
            layout = QVBoxLayout(dialog)
            
            # 标题
            title_label = QLabel("⚡ 音频缓冲区优化设置")
            title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
            layout.addWidget(title_label)
            
            # 缓冲区大小滑块
            buffer_layout = QHBoxLayout()
            buffer_label = QLabel("缓冲区大小:")
            buffer_layout.addWidget(buffer_label)
            
            buffer_slider = QSlider(Qt.Orientation.Horizontal)
            buffer_slider.setMinimum(0)  # 对应32样本
            buffer_slider.setMaximum(4)  # 对应512样本
            buffer_slider.setValue(2)    # 默认128样本
            buffer_layout.addWidget(buffer_slider)
            
            buffer_value_label = QLabel("128 样本")
            buffer_layout.addWidget(buffer_value_label)
            layout.addLayout(buffer_layout)
            
            # 采样率滑块
            rate_layout = QHBoxLayout()
            rate_label = QLabel("采样率:")
            rate_layout.addWidget(rate_label)
            
            rate_slider = QSlider(Qt.Orientation.Horizontal)
            rate_slider.setMinimum(0)  # 对应44100Hz
            rate_slider.setMaximum(3)  # 对应192000Hz
            rate_slider.setValue(1)    # 默认48000Hz
            rate_layout.addWidget(rate_slider)
            
            rate_value_label = QLabel("48000 Hz")
            rate_layout.addWidget(rate_value_label)
            layout.addLayout(rate_layout)
            
            # 优化选项
            options_label = QLabel("优化选项:")
            options_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
            layout.addWidget(options_label)
            
            low_latency_cb = QCheckBox("🚀 极低延迟模式")
            low_latency_cb.setChecked(True)
            layout.addWidget(low_latency_cb)
            
            exclusive_cb = QCheckBox("🎯 独占模式 (WASAPI)")
            exclusive_cb.setChecked(True)
            layout.addWidget(exclusive_cb)
            
            # 预计延迟显示
            latency_label = QLabel("预计延迟: 2.67ms")
            latency_label.setStyleSheet("color: #4CAF50; font-weight: bold; margin-top: 10px;")
            layout.addWidget(latency_label)
            
            # 更新函数
            def update_values():
                buffer_sizes = [32, 64, 128, 256, 512]
                sample_rates = [44100, 48000, 96000, 192000]
                
                buffer_size = buffer_sizes[buffer_slider.value()]
                sample_rate = sample_rates[rate_slider.value()]
                
                buffer_value_label.setText(f"{buffer_size} 样本")
                rate_value_label.setText(f"{sample_rate} Hz")
                
                latency_ms = (buffer_size / sample_rate) * 1000
                latency_label.setText(f"预计延迟: {latency_ms:.2f}ms")
                
                # 延迟颜色指示
                if latency_ms < 2.0:
                    latency_label.setStyleSheet("color: #4CAF50; font-weight: bold; margin-top: 10px;")
                elif latency_ms < 5.0:
                    latency_label.setStyleSheet("color: #FF9800; font-weight: bold; margin-top: 10px;")
                else:
                    latency_label.setStyleSheet("color: #F44336; font-weight: bold; margin-top: 10px;")
            
            buffer_slider.valueChanged.connect(update_values)
            rate_slider.valueChanged.connect(update_values)
            
            # 按钮
            button_layout = QHBoxLayout()
            apply_btn = QPushButton("应用设置")
            cancel_btn = QPushButton("取消")
            
            def apply_settings():
                try:
                    buffer_sizes = [32, 64, 128, 256, 512]
                    sample_rates = [44100, 48000, 96000, 192000]
                    
                    buffer_size = buffer_sizes[buffer_slider.value()]
                    sample_rate = sample_rates[rate_slider.value()]
                    
                    print(f"🔧 应用优化设置: {sample_rate}Hz/{buffer_size}样本")
                    print(f"   极低延迟: {'启用' if low_latency_cb.isChecked() else '禁用'}")
                    print(f"   独占模式: {'启用' if exclusive_cb.isChecked() else '禁用'}")
                    
                    # 这里可以应用设置到音频处理器
                    main_window = self.get_main_window()
                    if main_window and hasattr(main_window, 'audio_processor'):
                        # 创建优化配置
                        optimized_config = {
                            'name': f'优化配置 ({sample_rate}Hz/{buffer_size}样本)',
                            'samplerate': sample_rate,
                            'blocksize': buffer_size,
                            'low_latency': low_latency_cb.isChecked(),
                            'exclusive': exclusive_cb.isChecked(),
                            'optimized': True
                        }
                        
                        main_window.audio_processor._optimized_config = optimized_config
                        print("✅ 优化配置已保存")
                    
                    dialog.accept()
                except Exception as e:
                    print(f"❌ 应用设置失败: {e}")
            
            apply_btn.clicked.connect(apply_settings)
            cancel_btn.clicked.connect(dialog.reject)
            
            button_layout.addWidget(apply_btn)
            button_layout.addWidget(cancel_btn)
            layout.addLayout(button_layout)
            
            # 初始更新
            update_values()
            
            # 显示对话框
            dialog.exec()
            
        except Exception as e:
            print(f"❌ 缓冲区优化失败: {e}")
    
    def test_audio_latency(self):
        """测试音频延迟"""
        try:
            print("🕐 开始音频延迟测试...")
            
            main_window = self.get_main_window()
            if not main_window or not hasattr(main_window, 'audio_processor'):
                print("❌ 无法获取音频处理器")
                return
            
            processor = main_window.audio_processor
            
            # 获取当前配置信息
            if hasattr(processor, '_selected_device_config') and processor._selected_device_config:
                config = processor._selected_device_config
                theoretical_latency = config['blocksize'] / config['samplerate'] * 1000
                
                print(f"📊 延迟测试结果:")
                print(f"   当前设备: {config['name']}")
                print(f"   配置: {config['samplerate']}Hz / {config['blocksize']}样本")
                print(f"   理论延迟: {theoretical_latency:.2f}ms")
                
                # 延迟等级评估
                if theoretical_latency < 1.0:
                    print(f"   等级: 🏆 极佳 (专业级)")
                elif theoretical_latency < 3.0:
                    print(f"   等级: 🥇 优秀 (实时监听)")
                elif theoretical_latency < 10.0:
                    print(f"   等级: 🥈 良好 (一般应用)")
                else:
                    print(f"   等级: 🥉 可接受 (基础应用)")
                
            else:
                print("⚠️ 当前没有选定的设备配置")
            
            print("✅ 延迟测试完成")
            
        except Exception as e:
            print(f"❌ 延迟测试失败: {e}")
    
    def save_preferred_device_config(self, config):
        """保存首选设备配置"""
        try:
            import json
            import os
            
            # 配置文件路径
            config_dir = os.path.join(os.path.expanduser("~"), ".mindecho")
            os.makedirs(config_dir, exist_ok=True)
            config_file = os.path.join(config_dir, "preferred_device.json")
            
            # 🔧 清理配置中不可序列化的对象
            serializable_config = {}
            for key, value in config.items():
                if key == 'settings':
                    # 转换WasapiSettings对象为字符串描述
                    if hasattr(value, 'exclusive'):
                        serializable_config[key] = {
                            'type': 'wasapi',
                            'exclusive': getattr(value, 'exclusive', False)
                        }
                    else:
                        serializable_config[key] = None
                elif isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                    serializable_config[key] = value
                else:
                    # 跳过不可序列化的对象
                    print(f"📝 跳过不可序列化字段: {key} ({type(value)})")
                    serializable_config[key] = str(value) if value is not None else None
            
            # 保存配置
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_config, f, indent=2, ensure_ascii=False)
            
            print(f"✅ 首选设备配置已保存: {config['name']}")
            
        except Exception as e:
            print(f"⚠️ 保存首选配置失败: {e}")
    
    def load_preferred_device_config(self):
        """加载首选设备配置"""
        try:
            import json
            import os
            
            config_file = os.path.join(os.path.expanduser("~"), ".mindecho", "preferred_device.json")
            
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                print(f"✅ 已加载首选设备配置: {config.get('name', 'Unknown')}")
                return config
            else:
                print("📝 没有找到首选设备配置文件")
                return None
                
        except Exception as e:
            print(f"⚠️ 加载首选配置失败: {e}")
            return None

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
        
        # 降噪处理器
        try:
            from src.audio_processing.noise_reduction import NoiseReductionProcessor
            self.noise_processor = NoiseReductionProcessor(sample_rate=44100, frame_size=2048)
            print("✅ 降噪处理器初始化成功")
        except ImportError as e:
            print(f"❌ 降噪处理器初始化失败: {e}")
            self.noise_processor = None
        
        # 🔥 初始化电流音检测器（主窗口）
        self.electric_noise_detector = {
            'enabled': True,
            'threshold': 2.0,
            'consecutive_count': 0,
            'last_detection_time': 0,
            'rms_threshold': 0.0008,
            'high_freq_ratio_threshold': 0.95
        }
        
        # 🔥 增强型检测器初始化变量
        self.advanced_detector = None
        self.precision_processor = None
        self.calibration_system = None
        self.calibration_frames = []
        self.calibration_complete = False
        self.detection_stats = {'total': 0, 'detected': 0, 'vocal_protected': 0}
        self.latency_timestamps = []
        self.frame_counter = 0
        
        # 🚀 零延迟优化组件
        self.audio_processing_thread = None
        self.zero_copy_enabled = True
        self.memory_pool = None
        self.preallocated_buffers = {}
        
        # 🎯 独立音频处理线程配置
        self.dedicated_audio_thread = None
        self.audio_queue = queue.Queue(maxsize=10)  # 小队列，减少延迟
        self.processing_lock = threading.Lock()
        
        # 🔥 零拷贝内存管理
        self._init_memory_pool()
        
        # 启动专用音频处理线程
        self._start_dedicated_audio_thread()
        
        # 统计数据
        self.total_pitches_detected = 0
        self.recording_duration = 0
        self.current_note = "--"
        self.current_frequency = 0
        
        # 字体状态
        self.chinese_font_available = False
        
        # 🎚️ 音量控制对话框
        self.volume_control_dialog = None
        
        # 初始化界面
        self.init_ui()
        self.setup_connections()
        
        # 🎯 加载用户首选设备配置到音频处理器
        if hasattr(self.audio_processor, '_selected_device_config') and self.audio_processor._selected_device_config:
            print(f"🎧 主窗口已加载首选设备配置: {self.audio_processor._selected_device_config['name']}")
        
        # 🔧 移除自动启动实时分析 - 只有用户主动录音时才启动
        # QTimer.singleShot(1000, self.start_realtime_analysis)  # 已禁用
        
        # 状态定时器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status_display)
        self.status_timer.start(100)  # 100ms更新一次
    
    def _init_memory_pool(self):
        """初始化零拷贝内存池"""
        try:
            # 预分配音频缓冲区
            buffer_size = int(48000 * 0.1)  # 100ms缓冲@48kHz
            self.preallocated_buffers = {
                'input_buffer': np.zeros(buffer_size, dtype=np.float32),
                'output_buffer': np.zeros(buffer_size, dtype=np.float32),
                'processing_buffer': np.zeros(buffer_size, dtype=np.float32)
            }
            print("🔥 零拷贝内存池初始化完成")
        except Exception as e:
            print(f"⚠️ 内存池初始化失败: {e}")
            self.zero_copy_enabled = False

    def _start_dedicated_audio_thread(self):
        """启动专用音频处理线程"""
        if self.dedicated_audio_thread is None or not self.dedicated_audio_thread.is_alive():
            self.dedicated_audio_thread = threading.Thread(
                target=self._audio_processing_worker,
                daemon=True,
                name="AudioProcessor"
            )
            self.dedicated_audio_thread.start()
            print("🚀 专用音频处理线程已启动")

    def _audio_processing_worker(self):
        """专用音频处理工作线程"""
        while True:
            try:
                # 非阻塞获取音频数据
                audio_data = self.audio_queue.get(timeout=0.001)
                if audio_data is None:  # 停止信号
                    break
                
                # 零拷贝处理音频数据
                with self.processing_lock:
                    self._process_audio_zero_copy(audio_data)
                
                self.audio_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"⚠️ 音频处理线程错误: {e}")

    def _process_audio_zero_copy(self, indata):
        """零拷贝音频处理"""
        try:
            if not self.zero_copy_enabled:
                return self._fallback_audio_processing(indata)
            
            # 直接操作内存视图，避免数据复制
            audio_view = indata.view()  # 零拷贝视图
            
            # 使用预分配缓冲区
            buffer_size = min(len(audio_view), len(self.preallocated_buffers['processing_buffer']))
            processing_slice = self.preallocated_buffers['processing_buffer'][:buffer_size]
            
            # 零拷贝赋值
            processing_slice[:] = audio_view.flatten()[:buffer_size]
            
            # 快速信号检测（零拷贝）
            if np.max(np.abs(processing_slice)) > 0.01:
                # 触发界面更新（使用信号）
                QMetaObject.invokeMethod(self, "update_ui", Qt.QueuedConnection)
                
        except Exception as e:
            print(f"⚠️ 零拷贝处理失败，回退到标准处理: {e}")
            return self._fallback_audio_processing(indata)

    def _fallback_audio_processing(self, indata):
        """标准音频处理（回退方案）"""
        audio_data = indata.copy()
        if np.max(np.abs(audio_data)) > 0.01:
            QMetaObject.invokeMethod(self, "update_ui", Qt.QueuedConnection)
    
    @pyqtSlot()
    def update_ui(self):
        """线程安全的UI更新"""
        # 更新界面显示
        pass
        # QTimer.singleShot(1000, self.start_realtime_analysis)  # 已禁用
        
        # 状态定时器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status_display)
        self.status_timer.start(100)  # 100ms更新一次
    
    def start_realtime_analysis(self):
        """启动实时音高分析（不录音模式）"""
        try:
            print("🎤 自动启动实时音高分析...")
            # 启动音频流进行实时分析，但不录音
            if self.audio_processor.start_recording(should_save=False):
                print("✅ 实时音高分析已启动")
                self.is_analyzing = True
                # 更新UI状态
                if hasattr(self, 'status_label'):
                    self.update_status_display()
            else:
                print("❌ 启动实时音高分析失败")
        except Exception as e:
            print(f"❌ 启动实时音高分析错误: {e}")
    
    def closeEvent(self, event):
        """窗口关闭事件处理 - 确保所有资源正确释放"""
        try:
            print("🔄 正在关闭MindEcho...")
            
            # 停止音频处理器
            if hasattr(self, 'audio_processor') and self.audio_processor:
                self.audio_processor.stop_recording()
                # 等待线程停止
                if self.audio_processor.isRunning():
                    self.audio_processor.wait(3000)  # 等待最多3秒
                    if self.audio_processor.isRunning():
                        self.audio_processor.terminate()  # 强制终止
                        print("⚠️ 音频处理器被强制终止")
                
            # 停止状态定时器
            if hasattr(self, 'status_timer'):
                self.status_timer.stop()
            
            print("✅ MindEcho已安全关闭")
            event.accept()
            
        except Exception as e:
            print(f"❌ 关闭窗口错误: {e}")
            event.accept()  # 即使出错也要关闭窗口
    
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
        # 设置音频处理器引用
        self.visualizer.set_audio_processor(self.audio_processor)
        
        # 连接监听按钮到主窗口的方法
        if hasattr(self.visualizer, 'monitor_button'):
            self.visualizer.monitor_button.clicked.connect(self.toggle_monitoring)
            print("🎧 监听按钮已连接到主窗口")
        
        main_layout.addWidget(self.visualizer)
        
        # 创建状态信息面板
        status_panel = self.create_status_panel()
        main_layout.addWidget(status_panel)
        
        # 🎯 初始化默认降噪模式为"基础频域降噪"
        self.init_default_noise_reduction()
    
    def init_default_noise_reduction(self):
        """初始化默认降噪模式"""
        try:
            default_mode = "基础频域降噪"
            print(f"🔧 初始化默认降噪模式: {default_mode}")
            
            # 设置界面组合框
            if hasattr(self, 'noise_reduction_combo'):
                self.noise_reduction_combo.setCurrentText(default_mode)
            
            # 设置主窗口降噪处理器
            if hasattr(self, 'noise_processor') and self.noise_processor:
                self.noise_processor.set_noise_reduction_mode(default_mode)
                print(f"✅ 主窗口降噪处理器模式设置为: {default_mode}")
            
            # 设置音频处理器降噪处理器
            if hasattr(self, 'audio_processor') and self.audio_processor:
                self.audio_processor.set_noise_reduction_mode(default_mode)
                print(f"✅ 音频处理器降噪模式设置为: {default_mode}")
            
            # 触发一次降噪模式切换回调，确保界面状态同步
            self.on_noise_reduction_changed(default_mode)
            
        except Exception as e:
            print(f"❌ 初始化默认降噪模式失败: {e}")
    
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
        self.sample_rate_combo.addItems(["48000", "44100", "96000"])  # 48kHz优先
        self.sample_rate_combo.setCurrentText("48000")  # 默认48kHz
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
        
        # 降噪控制
        params_layout.addWidget(QLabel("降噪模式:"))
        self.noise_reduction_combo = QComboBox()
        self.noise_reduction_combo.addItems([
            "关闭",
            "基础频域降噪", 
            "AI降噪",
            "高级音乐保护"
        ])
        self.noise_reduction_combo.setCurrentText("基础频域降噪")  # 🎯 修改默认为基础频域降噪
        self.noise_reduction_combo.currentTextChanged.connect(self.on_noise_reduction_changed)
        self.noise_reduction_combo.setStyleSheet("""
            QComboBox {
                background-color: #2C2C2C;
                border: 2px solid #4A90E2;
                border-radius: 4px;
                padding: 4px 8px;
                color: white;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: #66BB6A;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                margin-right: 5px;
            }
        """)
        params_layout.addWidget(self.noise_reduction_combo)
        
        # 🔥 APO电流音检测控制
        params_layout.addWidget(QLabel("电流音检测:"))
        self.electric_noise_checkbox = QCheckBox("启用APO检测")
        self.electric_noise_checkbox.setChecked(True)  # 默认启用
        self.electric_noise_checkbox.toggled.connect(self.on_electric_noise_detection_changed)
        self.electric_noise_checkbox.setStyleSheet("""
            QCheckBox {
                color: white;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #4A90E2;
                border-radius: 3px;
                background-color: #2C2C2C;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                border-color: #66BB6A;
            }
            QCheckBox::indicator:hover {
                border-color: #66BB6A;
            }
        """)
        params_layout.addWidget(self.electric_noise_checkbox)
        
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
        
        # 降噪状态显示
        self.noise_status_label = QLabel("降噪: 关闭")
        self.noise_status_label.setStyleSheet("font-size: 12px; color: #CCCCCC;")
        system_status_layout.addWidget(self.noise_status_label)
        
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
        
        # 🔥 验证信号连接
        print("🔥 信号连接已建立:")
        print(f"   🎯 pitch_detected -> on_pitch_detected: 已连接")
        print(f"   🎯 audio_level_updated -> on_audio_level_updated: 已连接")
        print(f"   🎯 recording_progress -> on_recording_progress: 已连接")
        print(f"   🎯 status_updated -> on_status_updated: 已连接")
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
                self.is_analyzing = True  # 录音时也是分析状态
                
                print(f"✅ 录音已启动: 文件={filename}, 保存={should_save}")
                
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
                
                # 🔥 立即更新检测统计显示为初始状态
                self.detection_count_label.setText("检测点数: 0")
                self.detection_rate_label.setText("检测频率: 0/秒")
                print("🔥 检测统计已重置为初始状态")
                
                # 清除可视化
                self.visualizer.clear_data()
                
                # 开始时间追踪（支持断续音调曲线）
                self.visualizer.start_time_tracking()
                
        except Exception as e:
            QMessageBox.critical(self, "录音错误", f"启动录音失败: {e}")
    
    def stop_recording(self):
        """停止录音"""
        try:
            self.audio_processor.stop_recording()
            self.is_recording = False
            
            # 停止时间追踪
            self.visualizer.stop_time_tracking()
            
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
    
    def toggle_monitoring(self):
        """切换监听功能（优化版：只音频回放，不分析）"""
        try:
            if not hasattr(self, 'is_monitoring'):
                self.is_monitoring = False
                
            if not self.is_monitoring:
                # 启动优化监听功能
                success = self.start_monitoring()
                if success:
                    self.is_monitoring = True
                    # 通过可视化器访问监听按钮
                    if hasattr(self.visualizer, 'monitor_button'):
                        self.visualizer.monitor_button.setText("关闭监听")
                        self.visualizer.monitor_button.setChecked(True)
                    print("🎧 优化监听功能已启动")
            else:
                # 关闭监听功能
                self.stop_monitoring()
                self.is_monitoring = False
                # 通过可视化器访问监听按钮
                if hasattr(self.visualizer, 'monitor_button'):
                    self.visualizer.monitor_button.setText("开启监听")
                    self.visualizer.monitor_button.setChecked(False)
                print("🎧 监听功能已关闭")
                
        except Exception as e:
            print(f"❌ 切换监听功能失败: {e}")
            
    def start_monitoring(self):
        """启动监听功能（优化版：只音频回放，不分析）"""
        try:
            # 检查是否有耳机连接
            if self.check_headphone_connection():
                print("🎧 检测到耳机连接，启动优化监听功能")
                
                # 🔥 开始优化的音频监听（48kHz + 128样本块 + 智能降噪）
                if self.audio_processor.start_audio_monitoring():
                    self.system_status_label.setText("状态: 监听中（优化版）")
                    return True
                else:
                    print("❌ 启动优化音频监听失败")
                    return False
            else:
                print("⚠️  未检测到耳机，建议连接耳机以避免啸叫")
                # 询问用户是否继续
                from PyQt6.QtWidgets import QMessageBox
                reply = QMessageBox.question(
                    self, 
                    "监听模式提醒", 
                    "未检测到耳机连接。\n\n在没有耳机的情况下使用优化监听功能可能会产生啸叫声。\n\n是否继续启动监听？\n\n✨ 新功能特性:\n• 48kHz高质量采样\n• 128样本超低延迟\n• 智能降噪处理\n• 实时延迟监测",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    if self.audio_processor.start_audio_monitoring():
                        self.system_status_label.setText("状态: 监听中(无耳机)")
                        return True
                    else:
                        print("❌ 启动音频监听失败")
                        return False
                else:
                    return False
                    
        except Exception as e:
            print(f"❌ 启动监听功能失败: {e}")
            return False
    
    def stop_monitoring(self):
        """停止监听功能"""
        try:
            if hasattr(self.audio_processor, 'stop_audio_monitoring'):
                self.audio_processor.stop_audio_monitoring()
                
            self.system_status_label.setText("状态: 就绪")
            print("🎧 监听功能已停止")
            
        except Exception as e:
            print(f"❌ 停止监听功能失败: {e}")
    
    def show_monitor_context_menu(self, position):
        """显示监听按钮的右键菜单"""
        context_menu = QMenu(self)
        context_menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 2px;
            }
            QMenu::item {
                background-color: transparent;
                color: white;
                padding: 8px 20px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #1976D2;
            }
            QMenu::item:disabled {
                color: #888888;
            }
        """)
        
        # 调节音量选项
        volume_action = context_menu.addAction("🎚️ 调节音量")
        volume_action.triggered.connect(self.show_volume_control)
        
        # AI降噪选项（暂时禁用）
        noise_action = context_menu.addAction("🤖 AI降噪")
        noise_action.setEnabled(False)  # 后续开发
        noise_action.triggered.connect(self.show_noise_control)
        
        # 分隔符
        context_menu.addSeparator()
        
        # 重置音量选项
        reset_action = context_menu.addAction("🔄 重置音量")
        reset_action.triggered.connect(self.reset_volume)
        
        # 显示菜单
        context_menu.exec(self.monitor_button.mapToGlobal(position))
    
    def show_volume_control(self):
        """显示音量控制对话框"""
        try:
            if not self.volume_control_dialog:
                current_volume = 100
                if hasattr(self.audio_processor, 'get_manual_volume'):
                    current_volume = self.audio_processor.get_manual_volume()
                
                self.volume_control_dialog = VolumeControlDialog(self, current_volume)
                self.volume_control_dialog.volume_changed.connect(self.on_volume_changed)
            
            # 获取当前音量并更新对话框
            if hasattr(self.audio_processor, 'get_manual_volume'):
                current_volume = self.audio_processor.get_manual_volume()
                self.volume_control_dialog.set_volume(current_volume)
            
            self.volume_control_dialog.show()
            self.volume_control_dialog.raise_()
            self.volume_control_dialog.activateWindow()
            
        except Exception as e:
            print(f"❌ 显示音量控制失败: {e}")
    
    def show_noise_control(self):
        """显示AI降噪控制（待开发）"""
        print("🤖 AI降噪功能正在开发中...")
        # 后续添加AI降噪控制界面
    
    def on_volume_changed(self, volume):
        """音量变化时的处理"""
        try:
            if hasattr(self.audio_processor, 'set_manual_volume'):
                success = self.audio_processor.set_manual_volume(volume)
                if success:
                    print(f"🎚️ 监听音量已调节至: {volume}%")
                else:
                    print("⚠️ 音量调节失败")
        except Exception as e:
            print(f"❌ 音量调节错误: {e}")
    
    def reset_volume(self):
        """重置音量到100%"""
        try:
            if hasattr(self.audio_processor, 'set_manual_volume'):
                self.audio_processor.set_manual_volume(100)
                if self.volume_control_dialog:
                    self.volume_control_dialog.set_volume(100)
                print("🔄 监听音量已重置为100%")
        except Exception as e:
            print(f"❌ 重置音量失败: {e}")
    
    def set_monitoring_volume(self, volume_percent):
        """设置监听音量的便捷方法"""
        try:
            if hasattr(self.audio_processor, 'set_manual_volume'):
                success = self.audio_processor.set_manual_volume(volume_percent)
                if success:
                    print(f"🎚️ 监听音量设置为: {volume_percent}%")
                    return True
                else:
                    print("⚠️ 音量设置失败")
                    return False
        except Exception as e:
            print(f"❌ 设置监听音量错误: {e}")
            return False
    
    def get_monitoring_volume(self):
        """获取当前监听音量"""
        try:
            if hasattr(self.audio_processor, 'get_manual_volume'):
                return self.audio_processor.get_manual_volume()
            return 100
        except Exception as e:
            print(f"❌ 获取监听音量错误: {e}")
            return 100
    
    def enable_volume_control(self, enabled=True):
        """启用或禁用音量控制"""
        try:
            if hasattr(self.audio_processor, 'enable_manual_volume_control'):
                success = self.audio_processor.enable_manual_volume_control(enabled)
                if success:
                    status = "启用" if enabled else "禁用"
                    print(f"🎚️ 音量控制已{status}")
                    return True
            return False
        except Exception as e:
            print(f"❌ 音量控制状态切换错误: {e}")
            return False
            
    def check_headphone_connection(self):
        """检查耳机连接状态"""
        try:
            import pyaudio
            
            # 获取音频设备信息
            p = pyaudio.PyAudio()
            
            # 检查输出设备
            for i in range(p.get_device_count()):
                device_info = p.get_device_info_by_index(i)
                device_name = device_info.get('name', '').lower()
                
                # 检查是否包含耳机相关关键词
                headphone_keywords = [
                    'headphone', 'headset', 'earphone', 'earbuds', 
                    'beats', 'sony', 'bose', 'sennheiser',
                    '耳机', '头戴', '入耳'
                ]
                
                if any(keyword in device_name for keyword in headphone_keywords):
                    print(f"🎧 检测到耳机设备: {device_info.get('name')}")
                    p.terminate()
                    return True
            
            p.terminate()
            return False
            
        except Exception as e:
            print(f"❌ 检查耳机连接失败: {e}")
            # 如果检测失败，假设没有耳机
            return False

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
    
    def on_noise_reduction_changed(self, mode):
        """降噪模式改变回调"""
        try:
            # 同时设置主窗口和音频处理器的降噪模式
            if self.noise_processor:
                self.noise_processor.set_noise_reduction_mode(mode)
            
            # 设置音频处理器的降噪模式
            if hasattr(self, 'audio_processor') and self.audio_processor:
                self.audio_processor.set_noise_reduction_mode(mode)
                
            # 更新降噪状态显示
            if mode == "关闭":
                status_msg = "降噪: 关闭"
                status_style = "font-size: 12px; color: #CCCCCC;"
            elif mode == "基础频域降噪":
                status_msg = "降噪: 频域降噪 🎵"
                status_style = "font-size: 12px; color: #4CAF50; font-weight: bold;"
            elif mode == "AI降噪":
                status_msg = "降噪: AI降噪 🤖 (开发中)"
                status_style = "font-size: 12px; color: #FFC107; font-weight: bold;"
            elif mode == "高级音乐保护":
                status_msg = "降噪: 音乐保护 🎼 (开发中)"
                status_style = "font-size: 12px; color: #FFC107; font-weight: bold;"
            else:
                status_msg = f"降噪: {mode}"
                status_style = "font-size: 12px; color: #CCCCCC;"
            
            # 更新降噪状态标签
            self.noise_status_label.setText(status_msg)
            self.noise_status_label.setStyleSheet(status_style)
            
            print(f"🔧 降噪模式已切换到: {mode}")
            
            # 如果AI降噪或高级音乐保护，显示提示
            if mode in ["AI降噪", "高级音乐保护"]:
                print(f"ℹ️  {mode} 功能正在开发中，当前不进行降噪处理")
                
        except Exception as e:
            print(f"❌ 切换降噪模式时出错: {e}")
            if hasattr(self, 'noise_status_label'):
                self.noise_status_label.setText("降噪: 错误")
                self.noise_status_label.setStyleSheet("font-size: 12px; color: #F44336;")
    
    def on_electric_noise_detection_changed(self, enabled):
        """电流音检测开关回调"""
        try:
            # 更新音频处理器的电流音检测状态
            if hasattr(self, 'audio_processor') and self.audio_processor:
                if hasattr(self.audio_processor, 'electric_noise_detector'):
                    self.audio_processor.electric_noise_detector['enabled'] = enabled
                    
            # 更新复选框文本和样式
            if enabled:
                self.electric_noise_checkbox.setText("启用APO检测")
                status_msg = "APO电流音检测: 启用 🛡️"
                print(f"🔧 APO电流音检测已启用（多算法融合，阈值2.0）")
            else:
                self.electric_noise_checkbox.setText("关闭APO检测")
                status_msg = "APO电流音检测: 关闭"
                print(f"🔧 APO电流音检测已关闭")
            
            # 如果需要，可以添加状态标签更新
            # self.electric_noise_status_label.setText(status_msg)
            
        except Exception as e:
            print(f"❌ 切换电流音检测状态时出错: {e}")
    
    def on_pitch_detected(self, pitch_data):
        """音高检测回调（支持断续音调曲线模式）"""
        try:
            # 更新统计
            self.total_pitches_detected += 1
            
            # 🔥 立即更新检测统计显示
            self.detection_count_label.setText(f"检测点数: {self.total_pitches_detected}")
            
            # 计算并更新检测频率
            if hasattr(self, 'recording_duration') and self.recording_duration > 0:
                detection_rate = self.total_pitches_detected / self.recording_duration
                self.detection_rate_label.setText(f"检测频率: {detection_rate:.1f}/秒")
            else:
                # 如果没有录音时长，使用音频处理器的运行时间估算
                if hasattr(self.audio_processor, 'processing_start_time'):
                    elapsed_time = time.time() - self.audio_processor.processing_start_time
                    if elapsed_time > 0:
                        detection_rate = self.total_pitches_detected / elapsed_time
                        self.detection_rate_label.setText(f"检测频率: {detection_rate:.1f}/秒")
                    else:
                        self.detection_rate_label.setText("检测频率: 计算中...")
                else:
                    self.detection_rate_label.setText("检测频率: 启动中...")
            
            # 🎯 调试输出检测统计更新（受开关和节流控制）
            if getattr(self, 'debug_flags', {}).get('detection_log', False):
                if hasattr(self, '_detection_debug_counter'):
                    self._detection_debug_counter += 1
                else:
                    self._detection_debug_counter = 1
                # 每3秒最多打印一次
                now_ts = time.time()
                if not hasattr(self, '_last_detection_log_time'):
                    self._last_detection_log_time = 0.0
                if now_ts - self._last_detection_log_time > 3.0:
                    print(f"🎯 检测统计更新#{self._detection_debug_counter}: 总检测数={self.total_pitches_detected}")
                    self._last_detection_log_time = now_ts
            
            # 更新当前音高信息
            frequency = pitch_data.get('frequency', 0)  # 平滑后的
            raw_frequency = pitch_data.get('raw_frequency', None)
            note_info = pitch_data.get('note_info', {})
            has_pitch = pitch_data.get('has_pitch', frequency > 0)
            
            if has_pitch and frequency > 0:
                # 记录平滑频率用于原逻辑
                self.current_frequency = frequency
                # 增加调试：显示 raw vs smooth（仅首次若开启）
                if raw_frequency is not None:
                    if not hasattr(self, '_raw_smooth_debug'):
                        self._raw_smooth_debug = 0
                    self._raw_smooth_debug += 1
                    if self._raw_smooth_debug <= 10:
                        print(f"🎯 UI接收频率: raw={raw_frequency:.2f}Hz smooth={frequency:.2f}Hz diff={abs(raw_frequency-frequency):.2f}Hz")
                
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
            else:
                # 无音高时显示"静音"状态，但不清除上一个音符信息
                # 这样用户可以看到最后检测到的音符和当前的静音状态
                if not hasattr(self, '_silence_counter'):
                    self._silence_counter = 0
                self._silence_counter += 1
                
                # 每100帧更新一次静音状态显示
                if self._silence_counter % 100 == 0:
                    audio_rms = pitch_data.get('audio_rms', 0)
                    self.current_note_label.setText(f"当前音符: -- (静音中, RMS: {audio_rms:.4f})")
            
            # 发送到可视化器（录音分析模式下显示音调线，纯监听模式跳过）
            should_show_pitch_line = (
                getattr(self.audio_processor, 'is_recording', False) or  # 录音模式
                (self.audio_processor.is_global_monitoring_active and not getattr(self.audio_processor, 'is_monitoring_only', False))  # 监听+录音模式
            )
            
            if should_show_pitch_line:
                # 录音分析模式：显示音调线
                self.visualizer.add_pitch_data(pitch_data)
            else:
                # 纯监听模式：跳过音调线绘制
                if self._pitch_precision_debug_counter <= 5:
                    print("🎧 纯监听模式：跳过音调线绘制")
            
            # 🔥 音高精度验证调试（前50次检测）
            if hasattr(self, '_pitch_precision_debug_counter'):
                self._pitch_precision_debug_counter += 1
            else:
                self._pitch_precision_debug_counter = 1
                print("🎵 开始音高精度验证...")
            
            if self._pitch_precision_debug_counter <= 50 and has_pitch and frequency > 0:
                if raw_frequency is not None:
                    print(f"🎵 音高精度#{self._pitch_precision_debug_counter}: raw={raw_frequency:.3f}Hz smooth={frequency:.3f}Hz")
                else:
                    print(f"🎵 音高精度#{self._pitch_precision_debug_counter}: 输入={frequency:.3f}Hz")
            
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


    def _advanced_electric_noise_detection(self, audio_data):
        """增强型多维度电流音检测（基于专利CN114640926A）"""
        try:
            # 使用高级检测器进行分析
            detection_result = self.advanced_detector.detect_electric_noise(audio_data)
            
            if detection_result['is_electric_noise']:
                # 检测到电流音，应用精密处理
                processed_audio = self.precision_processor.process_audio(audio_data)
                
                # 统计日志（低频输出）
                if self.frame_counter % 1000 == 0:
                    features = detection_result['features']
                    print(f"🔇 多维度检测到电流音:")
                    print(f"   频谱质心: {features['spectral_centroid']:.1f}")
                    print(f"   峰均比: {features['peak_to_average_ratio']:.2f}")
                    print(f"   谐波比: {features['harmonic_ratio']:.3f}")
                
                return processed_audio
            else:
                # 正常音频，应用轻度优化
                return self.precision_processor.enhance_audio(audio_data)
                
        except Exception as e:
            print(f"⚠️ 高级检测错误，回退到基础模式: {e}")
            return self._legacy_electric_noise_detection(audio_data)
    
    def _legacy_electric_noise_detection(self, audio_data):
        """遗留的基础电流音检测（向后兼容）"""
        try:
            input_rms = np.sqrt(np.mean(audio_data ** 2))
            is_electric_noise = False
            
            if len(audio_data) > 10 and self.electric_noise_detector['enabled']:
                if input_rms < 0.0008:  # 极低信号强度
                    if len(audio_data) >= 32:
                        fft_data = np.fft.rfft(audio_data)
                        power_spectrum = np.abs(fft_data) ** 2
                        total_power = np.sum(power_spectrum)
                        
                        if total_power > 0:
                            high_freq_start = len(power_spectrum) * 7 // 8
                            high_freq_power = np.sum(power_spectrum[high_freq_start:])
                            high_freq_ratio = high_freq_power / total_power
                            
                            if high_freq_ratio > 0.95 and input_rms < 0.0005:
                                is_electric_noise = True
            
            if is_electric_noise or input_rms < 0.0003:
                return np.zeros_like(audio_data)
            else:
                processed_audio = audio_data.copy()
                
                # 动态范围控制
                max_amplitude = np.max(np.abs(processed_audio))
                if max_amplitude > 0.85:
                    compression_ratio = 0.85 / max_amplitude
                    processed_audio *= compression_ratio
                
                # DC偏移处理
                dc_offset = np.mean(processed_audio)
                if abs(dc_offset) > 0.03:
                    processed_audio -= dc_offset
                    
                return processed_audio
                
        except Exception as e:
            print(f"⚠️ 基础检测错误: {e}")
            return audio_data.copy()
    
    def _log_performance_stats(self):
        """记录性能统计信息"""
        try:
            # 延迟统计
            if len(self.latency_timestamps) > 10:
                recent_latencies = self.latency_timestamps[-50:]
                avg_latency = np.mean(recent_latencies)
                max_latency = np.max(recent_latencies)
                print(f"🎵 监听延迟: 平均 {avg_latency:.1f}ms, 最大 {max_latency:.1f}ms")
            
            # 检测统计
            if hasattr(self, 'detection_stats') and self.detection_stats['total'] > 0:
                total = self.detection_stats['total']
                detected = self.detection_stats['detected']
                protected = self.detection_stats['vocal_protected']
                
                detection_rate = (detected / total) * 100
                protection_rate = (protected / total) * 100
                
                print(f"🔍 检测统计: 电流音 {detection_rate:.1f}%, 人声保护 {protection_rate:.1f}%")
                
                # 重置统计
                self.detection_stats = {'total': 0, 'detected': 0, 'vocal_protected': 0}
                
        except Exception as e:
            print(f"⚠️ 统计记录错误: {e}")


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


class VolumeControlDialog(QDialog):
    """音量调节对话框"""
    
    volume_changed = pyqtSignal(int)  # 音量变化信号
    
    def __init__(self, parent=None, current_volume=100):
        super().__init__(parent)
        self.setWindowTitle("监听音量调节")
        self.setFixedSize(300, 150)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        
        # 设置样式
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                border-radius: 8px;
            }
            QLabel {
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
            }
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 8px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B1B1B1, stop:1 #c4c4c4);
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b4b4b4, stop:1 #8f8f8f);
                border: 1px solid #5c5c5c;
                width: 18px;
                margin: -2px 0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffffff, stop:1 #a8a8a8);
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #66e0ff, stop:1 #0099cc);
                border: 1px solid #777;
                height: 10px;
                border-radius: 4px;
            }
            QSlider::add-page:horizontal {
                background: #404040;
                border: 1px solid #777;
                height: 10px;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #404040;
                color: white;
                border: 1px solid #666666;
                padding: 5px 15px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #303030;
            }
        """)
        
        self.setup_ui(current_volume)
        
    def setup_ui(self, current_volume):
        """设置UI"""
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title_label = QLabel("🎚️ 监听音量调节")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #66e0ff; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # 音量滑块容器
        slider_layout = QHBoxLayout()
        
        # 音量图标
        volume_icon = QLabel("🔊")
        volume_icon.setStyleSheet("font-size: 16px;")
        slider_layout.addWidget(volume_icon)
        
        # 音量滑块
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 300)  # 0-300%
        self.volume_slider.setValue(current_volume)
        self.volume_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.volume_slider.setTickInterval(50)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        slider_layout.addWidget(self.volume_slider)
        
        # 音量数值显示
        self.volume_label = QLabel(f"{current_volume}%")
        self.volume_label.setMinimumWidth(50)
        self.volume_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.volume_label.setStyleSheet("color: #66e0ff; font-weight: bold;")
        slider_layout.addWidget(self.volume_label)
        
        layout.addLayout(slider_layout)
        
        # 快捷按钮
        button_layout = QHBoxLayout()
        
        # 静音按钮
        mute_btn = QPushButton("静音")
        mute_btn.clicked.connect(lambda: self.set_volume(0))
        button_layout.addWidget(mute_btn)
        
        # 50%按钮
        half_btn = QPushButton("50%")
        half_btn.clicked.connect(lambda: self.set_volume(50))
        button_layout.addWidget(half_btn)
        
        # 100%按钮
        normal_btn = QPushButton("100%")
        normal_btn.clicked.connect(lambda: self.set_volume(100))
        button_layout.addWidget(normal_btn)
        
        # 150%按钮
        boost_btn = QPushButton("150%")
        boost_btn.clicked.connect(lambda: self.set_volume(150))
        button_layout.addWidget(boost_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
    def on_volume_changed(self, value):
        """音量变化时的处理"""
        self.volume_label.setText(f"{value}%")
        self.volume_changed.emit(value)
        
        # 根据音量大小改变颜色
        if value == 0:
            color = "#888888"  # 灰色-静音
        elif value < 50:
            color = "#66e0ff"  # 蓝色-低音量
        elif value <= 100:
            color = "#00ff00"  # 绿色-正常音量
        elif value <= 200:
            color = "#ffaa00"  # 橙色-高音量
        else:
            color = "#ff4444"  # 红色-很高音量
            
        self.volume_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        
    def set_volume(self, volume):
        """设置音量"""
        self.volume_slider.setValue(volume)
        
    def closeEvent(self, event):
        """关闭事件"""
        self.hide()
        event.ignore()  # 不真正关闭，只是隐藏


if __name__ == "__main__":
    main()
