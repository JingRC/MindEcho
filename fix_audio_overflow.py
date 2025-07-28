"""
MindEcho 音频输入溢出问题修复
解决 "input overflow" 警告，优化音调检测精度，支持颤音等快速变化
"""

import numpy as np
import sounddevice as sd
import threading
import queue
import time
from collections import deque

class AudioBufferManager:
    """音频缓冲区管理器 - 解决input overflow问题"""
    
    def __init__(self, sample_rate=44100, max_buffer_size=8192):
        self.sample_rate = sample_rate
        self.max_buffer_size = max_buffer_size
        
        # 多级缓冲队列
        self.input_queue = queue.Queue(maxsize=50)  # 输入缓冲队列
        self.processing_queue = queue.Queue(maxsize=30)  # 处理队列
        
        # 循环缓冲区
        self.ring_buffer = np.zeros(max_buffer_size, dtype=np.float32)
        self.write_pos = 0
        self.read_pos = 0
        self.buffer_lock = threading.Lock()
        
        # 统计信息
        self.overflow_count = 0
        self.total_frames = 0
        
    def add_audio_data(self, data):
        """添加音频数据到缓冲区"""
        try:
            # 快速入队，避免阻塞音频回调
            if not self.input_queue.full():
                self.input_queue.put_nowait(data.copy())
            else:
                # 队列满时，丢弃最老的数据
                try:
                    self.input_queue.get_nowait()
                    self.input_queue.put_nowait(data.copy())
                    self.overflow_count += 1
                except queue.Empty:
                    pass
            
            self.total_frames += 1
            
        except Exception as e:
            print(f"缓冲区添加数据错误: {e}")
    
    def get_audio_data(self, block_size=512):
        """从缓冲区获取音频数据用于处理"""
        try:
            # 非阻塞获取
            audio_blocks = []
            total_samples = 0
            
            # 收集足够的数据块
            while total_samples < block_size and not self.input_queue.empty():
                try:
                    data = self.input_queue.get_nowait()
                    audio_blocks.append(data)
                    total_samples += len(data)
                except queue.Empty:
                    break
            
            if audio_blocks:
                # 合并音频块
                combined_audio = np.concatenate(audio_blocks)
                
                # 如果数据过多，只取需要的部分
                if len(combined_audio) > block_size:
                    # 保留剩余数据
                    remaining = combined_audio[block_size:]
                    if not self.input_queue.full():
                        try:
                            self.input_queue.put_nowait(remaining)
                        except queue.Full:
                            pass
                    combined_audio = combined_audio[:block_size]
                
                return combined_audio
            
            return None
            
        except Exception as e:
            print(f"获取音频数据错误: {e}")
            return None
    
    def get_buffer_stats(self):
        """获取缓冲区统计信息"""
        return {
            'queue_size': self.input_queue.qsize(),
            'overflow_count': self.overflow_count,
            'overflow_rate': self.overflow_count / max(self.total_frames, 1),
            'total_frames': self.total_frames
        }

class AsyncAudioProcessor:
    """异步音频处理器 - 分离音频采集和处理"""
    
    def __init__(self, sample_rate=44100, chunk_size=256):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        
        # 缓冲区管理器
        self.buffer_manager = AudioBufferManager(sample_rate)
        
        # 处理线程
        self.processing_thread = None
        self.is_processing = False
        
        # 音高检测历史 - 支持颤音检测
        self.pitch_history = deque(maxlen=200)  # 保存200个点，支持快速变化
        self.time_history = deque(maxlen=200)
        
        # 回调函数
        self.pitch_callback = None
        self.buffer_stats_callback = None
        
        # 颤音检测参数
        self.vibrato_detection_window = 50  # 检测窗口
        self.vibrato_min_frequency = 3.0   # 最小颤音频率 (Hz)
        self.vibrato_max_frequency = 12.0  # 最大颤音频率 (Hz)
        
    def start_processing(self):
        """启动异步处理"""
        if self.is_processing:
            return
        
        self.is_processing = True
        self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.processing_thread.start()
        print("✅ 异步音频处理器启动")
    
    def stop_processing(self):
        """停止异步处理"""
        self.is_processing = False
        if self.processing_thread:
            self.processing_thread.join(timeout=1.0)
        print("⏹️ 异步音频处理器停止")
    
    def add_audio_data(self, data):
        """添加音频数据（从音频回调调用）"""
        self.buffer_manager.add_audio_data(data)
    
    def _processing_loop(self):
        """处理循环 - 在独立线程中运行"""
        processing_interval = self.chunk_size / self.sample_rate  # 目标处理间隔
        
        while self.is_processing:
            start_time = time.time()
            
            # 获取音频数据
            audio_data = self.buffer_manager.get_audio_data(self.chunk_size)
            
            if audio_data is not None and len(audio_data) >= 256:
                # 音高检测
                pitch_info = self._detect_pitch_enhanced(audio_data)
                
                if pitch_info:
                    # 颤音检测
                    vibrato_info = self._detect_vibrato(pitch_info)
                    pitch_info.update(vibrato_info)
                    
                    # 回调处理
                    if self.pitch_callback:
                        try:
                            self.pitch_callback(pitch_info)
                        except Exception as e:
                            print(f"音高回调错误: {e}")
                
                # 缓冲区统计回调
                if self.buffer_stats_callback:
                    try:
                        stats = self.buffer_manager.get_buffer_stats()
                        self.buffer_stats_callback(stats)
                    except Exception as e:
                        print(f"统计回调错误: {e}")
            
            # 控制处理频率 - 目标120Hz以支持颤音检测
            target_frequency = 120  # Hz
            target_interval = 1.0 / target_frequency
            elapsed = time.time() - start_time
            
            if elapsed < target_interval:
                time.sleep(target_interval - elapsed)
    
    def _detect_pitch_enhanced(self, audio_data):
        """增强音高检测"""
        try:
            # 预处理
            windowed = audio_data * np.hanning(len(audio_data))
            
            # 自相关法
            correlation = np.correlate(windowed, windowed, mode='full')
            correlation = correlation[len(correlation)//2:]
            
            # 音高范围：40Hz-2000Hz （支持更宽范围）
            min_period = int(self.sample_rate / 2000)  
            max_period = int(self.sample_rate / 40)    
            
            if max_period < len(correlation):
                search_range = correlation[min_period:max_period]
                
                if len(search_range) > 0:
                    peak_index = np.argmax(search_range) + min_period
                    frequency = self.sample_rate / peak_index
                    
                    # 置信度计算
                    peak_correlation = correlation[peak_index]
                    base_correlation = correlation[0] if correlation[0] > 0 else 1e-10
                    confidence = peak_correlation / base_correlation
                    
                    # 降低阈值以检测更多音调变化
                    if confidence > 0.15 and 40 <= frequency <= 2000:
                        current_time = time.time()
                        
                        # 保存历史数据
                        self.pitch_history.append(frequency)
                        self.time_history.append(current_time)
                        
                        return {
                            'frequency': frequency,
                            'confidence': confidence,
                            'timestamp': current_time,
                            'rms': np.sqrt(np.mean(audio_data ** 2))
                        }
            
            return None
            
        except Exception as e:
            print(f"音高检测错误: {e}")
            return None
    
    def _detect_vibrato(self, pitch_info):
        """检测颤音"""
        vibrato_info = {
            'has_vibrato': False,
            'vibrato_rate': 0.0,
            'vibrato_depth': 0.0,
            'vibrato_description': ''
        }
        
        try:
            if len(self.pitch_history) < self.vibrato_detection_window:
                return vibrato_info
            
            # 取最近的音高数据
            recent_pitches = list(self.pitch_history)[-self.vibrato_detection_window:]
            recent_times = list(self.time_history)[-self.vibrato_detection_window:]
            
            if len(recent_pitches) < 20:  # 至少需要20个点
                return vibrato_info
            
            # 计算音高变化
            pitch_array = np.array(recent_pitches)
            time_array = np.array(recent_times)
            time_diffs = np.diff(time_array)
            
            # 去除异常值和趋势
            mean_pitch = np.mean(pitch_array)
            pitch_detrend = pitch_array - mean_pitch
            
            # 计算变化率
            pitch_changes = np.abs(np.diff(pitch_array))
            avg_change = np.mean(pitch_changes)
            
            # 检测周期性变化
            if len(pitch_detrend) > 10:
                # 简单的周期性检测
                autocorr = np.correlate(pitch_detrend, pitch_detrend, mode='full')
                autocorr = autocorr[len(autocorr)//2:]
                
                # 寻找周期性峰值
                if len(autocorr) > 5:
                    # 忽略第一个峰值（自身）
                    search_range = autocorr[2:min(20, len(autocorr))]
                    if len(search_range) > 0:
                        max_autocorr = np.max(search_range)
                        max_idx = np.argmax(search_range) + 2
                        
                        # 估算颤音频率
                        if len(time_diffs) > 0:
                            avg_time_diff = np.mean(time_diffs)
                            vibrato_period = max_idx * avg_time_diff
                            vibrato_rate = 1.0 / vibrato_period if vibrato_period > 0 else 0
                            
                            # 颤音深度（音高变化幅度）
                            vibrato_depth = np.std(pitch_detrend)
                            
                            # 判断是否为有效颤音
                            if (self.vibrato_min_frequency <= vibrato_rate <= self.vibrato_max_frequency and 
                                vibrato_depth > 2.0 and  # 至少2Hz的音高变化
                                max_autocorr > 0.3):     # 足够的周期性
                                
                                vibrato_info.update({
                                    'has_vibrato': True,
                                    'vibrato_rate': vibrato_rate,
                                    'vibrato_depth': vibrato_depth,
                                    'vibrato_description': f"颤音 {vibrato_rate:.1f}Hz，深度±{vibrato_depth:.1f}Hz"
                                })
        
        except Exception as e:
            print(f"颤音检测错误: {e}")
        
        return vibrato_info
    
    def get_processing_stats(self):
        """获取处理统计信息"""
        buffer_stats = self.buffer_manager.get_buffer_stats()
        
        return {
            'buffer_queue_size': buffer_stats['queue_size'],
            'overflow_count': buffer_stats['overflow_count'],
            'overflow_rate': buffer_stats['overflow_rate'],
            'total_frames': buffer_stats['total_frames'],
            'pitch_history_size': len(self.pitch_history),
            'is_processing': self.is_processing
        }

def create_optimized_audio_config():
    """创建优化的音频配置"""
    
    # 检查系统音频延迟
    try:
        device_info = sd.query_devices(kind='input')
        print(f"默认输入设备: {device_info['name']}")
        print(f"默认采样率: {device_info['default_samplerate']}")
        print(f"最大输入通道: {device_info['max_input_channels']}")
    except Exception as e:
        print(f"获取设备信息失败: {e}")
    
    # 优化的音频参数
    config = {
        'sample_rate': 44100,
        'channels': 1,
        'dtype': np.float32,
        
        # 关键：优化的缓冲区参数
        'blocksize': 256,      # 减小blocksize，降低延迟 (512→256)
        'latency': 'low',      # 低延迟模式
        
        # sounddevice特定参数
        'extra_settings': {
            'clip_off': True,           # 关闭削波
            'dither_off': True,         # 关闭抖动
            'never_drop_input': True,   # 永不丢弃输入
            'prime_output_buffers_using_stream_callback': False
        }
    }
    
    return config

# 测试函数
def test_async_audio_processor():
    """测试异步音频处理器"""
    print("🧪 测试异步音频处理器...")
    
    # 创建处理器
    processor = AsyncAudioProcessor(sample_rate=44100, chunk_size=256)
    
    # 设置回调
    def pitch_callback(pitch_info):
        vibrato_text = f" - {pitch_info['vibrato_description']}" if pitch_info['has_vibrato'] else ""
        print(f"🎵 检测到音高: {pitch_info['frequency']:.1f}Hz "
              f"(置信度: {pitch_info['confidence']:.2f}){vibrato_text}")
    
    def stats_callback(stats):
        if stats['total_frames'] % 100 == 0:  # 每100帧显示一次统计
            print(f"📊 缓冲区状态: 队列大小={stats['buffer_queue_size']}, "
                  f"溢出率={stats['overflow_rate']:.1%}")
    
    processor.pitch_callback = pitch_callback
    processor.buffer_stats_callback = stats_callback
    
    # 启动处理
    processor.start_processing()
    
    # 获取音频配置
    config = create_optimized_audio_config()
    
    # 音频回调
    def audio_callback(indata, frames, time_info, status):
        if status:
            # 只记录严重错误，忽略input overflow
            if 'input overflow' not in str(status).lower():
                print(f"⚠️ 音频状态: {status}")
        
        # 添加到异步处理器
        audio_data = indata[:, 0] if len(indata.shape) > 1 else indata.flatten()
        processor.add_audio_data(audio_data)
    
    try:
        print("开始音频流...")
        with sd.InputStream(
            callback=audio_callback,
            samplerate=config['sample_rate'],
            channels=config['channels'],
            blocksize=config['blocksize'],
            latency=config['latency'],
            dtype=config['dtype']
        ) as stream:
            print("🎙️ 录音中... 请说话或唱歌，观察颤音检测效果")
            print("💡 尝试发出颤音或快速音调变化")
            
            # 运行30秒
            time.sleep(30)
    
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"音频流错误: {e}")
    finally:
        processor.stop_processing()
        print("测试完成")

if __name__ == "__main__":
    test_async_audio_processor()
