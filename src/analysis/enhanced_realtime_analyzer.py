"""
增强实时音高分析器
支持降噪处理、完整音域显示和音高波动可视化
"""

import numpy as np
import threading
import time
import queue
from scipy.signal import butter, filtfilt, medfilt
from collections import deque

class EnhancedRealTimeAnalyzer:
    """增强版实时音高分析器"""
    
    def __init__(self, sample_rate=44100, chunk_size=2048):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        
        # 音高历史记录（用于波动显示）
        self.pitch_history = deque(maxlen=100)  # 保存最近100个音高点
        self.time_history = deque(maxlen=100)
        
        # 降噪参数
        self.noise_gate_threshold = 0.001  # 噪声门限
        self.median_filter_size = 5  # 中值滤波窗口大小
        
        # 音域定义（A0到C8）
        self.min_frequency = 27.5  # A0
        self.max_frequency = 4186.0  # C8
        
        # 回调函数
        self.pitch_callback = None
        self.spectrum_callback = None
        
        # 控制变量
        self.is_running = False
        self.analysis_thread = None
        
        # 数据队列
        self.audio_queue = queue.Queue()
        
    def set_callbacks(self, pitch_callback=None, spectrum_callback=None):
        """设置回调函数"""
        self.pitch_callback = pitch_callback
        self.spectrum_callback = spectrum_callback
    
    def start_analysis(self):
        """开始分析"""
        if not self.is_running:
            self.is_running = True
            self.analysis_thread = threading.Thread(target=self._analysis_loop)
            self.analysis_thread.start()
    
    def stop_analysis(self):
        """停止分析"""
        self.is_running = False
        if self.analysis_thread:
            self.analysis_thread.join()
    
    def add_audio_data(self, audio_data):
        """添加音频数据到队列"""
        try:
            self.audio_queue.put(audio_data, block=False)
        except queue.Full:
            # 如果队列满了，丢弃最旧的数据
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.put(audio_data, block=False)
            except queue.Empty:
                pass
    
    def _analysis_loop(self):
        """分析循环"""
        while self.is_running:
            try:
                # 从队列获取音频数据（超时1秒）
                audio_data = self.audio_queue.get(timeout=1.0)
                
                # 执行分析
                self._analyze_chunk(audio_data)
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"分析错误: {e}")
    
    def _analyze_chunk(self, audio_data):
        """分析音频块"""
        try:
            # 1. 预处理和降噪
            processed_audio = self._preprocess_audio(audio_data)
            
            # 2. 音高检测
            pitch, confidence = self._detect_pitch_enhanced(processed_audio)
            
            # 3. 频谱分析
            spectrum = self._compute_spectrum(processed_audio)
            
            # 4. 记录历史
            current_time = time.time()
            if pitch > 0:
                self.pitch_history.append(pitch)
                self.time_history.append(current_time)
            
            # 5. 计算音符信息
            note_info = self._frequency_to_note_info(pitch) if pitch > 0 else None
            
            # 6. 调用回调函数
            if self.pitch_callback:
                pitch_data = {
                    'frequency': pitch,
                    'confidence': confidence,
                    'note_info': note_info,
                    'timestamp': current_time,
                    'pitch_history': list(self.pitch_history),
                    'time_history': list(self.time_history)
                }
                self.pitch_callback(pitch_data)
            
            if self.spectrum_callback:
                spectrum_data = {
                    'frequencies': spectrum['frequencies'],
                    'magnitudes': spectrum['magnitudes'],
                    'timestamp': current_time
                }
                self.spectrum_callback(spectrum_data)
                
        except Exception as e:
            print(f"音频块分析错误: {e}")
    
    def _preprocess_audio(self, audio_data):
        """音频预处理和降噪"""
        try:
            # 确保是float类型
            audio = audio_data.astype(np.float32)
            
            # 1. 噪声门 - 去除低于阈值的信号
            audio_energy = np.sqrt(np.mean(audio ** 2))
            if audio_energy < self.noise_gate_threshold:
                return np.zeros_like(audio)
            
            # 2. 高通滤波器 - 去除低频噪声
            nyquist = self.sample_rate / 2
            low_cutoff = 80.0 / nyquist  # 80Hz高通
            b, a = butter(4, low_cutoff, btype='high')
            audio = filtfilt(b, a, audio)
            
            # 3. 低通滤波器 - 去除高频噪声
            high_cutoff = 4000.0 / nyquist  # 4kHz低通
            b, a = butter(4, high_cutoff, btype='low')
            audio = filtfilt(b, a, audio)
            
            # 4. 归一化
            max_val = np.max(np.abs(audio))
            if max_val > 0:
                audio = audio / max_val
            
            return audio
            
        except Exception as e:
            print(f"音频预处理错误: {e}")
            return audio_data
    
    def _detect_pitch_enhanced(self, audio_data):
        """增强音高检测（YIN算法改进版）"""
        try:
            # YIN算法参数
            threshold = 0.1
            min_period = int(self.sample_rate / self.max_frequency)
            max_period = int(self.sample_rate / self.min_frequency)
            
            # 确保音频长度足够
            if len(audio_data) < max_period * 2:
                return 0.0, 0.0
            
            # 计算差分函数
            diff_function = self._yin_difference_function(audio_data, max_period)
            
            # 计算累积均值归一化差分函数
            cmnd_function = self._yin_cumulative_mean_normalized_difference(diff_function)
            
            # 寻找第一个低于阈值的点
            period = self._yin_absolute_threshold(cmnd_function, threshold, min_period)
            
            if period == 0:
                return 0.0, 0.0
            
            # 抛物线插值提高精度
            period = self._parabolic_interpolation(cmnd_function, period)
            
            # 计算频率
            frequency = self.sample_rate / period
            
            # 计算置信度
            confidence = 1.0 - cmnd_function[int(period)]
            
            # 频率范围检查
            if not (self.min_frequency <= frequency <= self.max_frequency):
                return 0.0, 0.0
            
            # 中值滤波平滑结果
            if len(self.pitch_history) >= self.median_filter_size:
                recent_pitches = list(self.pitch_history)[-self.median_filter_size:]
                recent_pitches.append(frequency)
                frequency = np.median(recent_pitches)
            
            return frequency, confidence
            
        except Exception as e:
            print(f"音高检测错误: {e}")
            return 0.0, 0.0
    
    def _yin_difference_function(self, audio, max_period):
        """YIN差分函数"""
        diff = np.zeros(max_period)
        for tau in range(1, max_period):
            for j in range(len(audio) - max_period):
                diff[tau] += (audio[j] - audio[j + tau]) ** 2
        return diff
    
    def _yin_cumulative_mean_normalized_difference(self, diff):
        """YIN累积均值归一化差分函数"""
        cmnd = np.zeros_like(diff)
        cmnd[0] = 1.0
        
        for tau in range(1, len(diff)):
            if diff[tau] == 0:
                cmnd[tau] = 0
            else:
                cmnd[tau] = diff[tau] / ((1.0 / tau) * np.sum(diff[1:tau+1]))
        
        return cmnd
    
    def _yin_absolute_threshold(self, cmnd, threshold, min_period):
        """YIN绝对阈值"""
        for tau in range(min_period, len(cmnd)):
            if cmnd[tau] < threshold:
                return tau
        return 0
    
    def _parabolic_interpolation(self, array, peak_index):
        """抛物线插值提高精度"""
        if peak_index < 1 or peak_index >= len(array) - 1:
            return peak_index
        
        y1 = array[peak_index - 1]
        y2 = array[peak_index]
        y3 = array[peak_index + 1]
        
        x0 = (y3 - y1) / (2 * (2 * y2 - y1 - y3))
        
        return peak_index + x0
    
    def _compute_spectrum(self, audio_data):
        """计算频谱"""
        try:
            # 应用窗函数
            windowed = audio_data * np.hanning(len(audio_data))
            
            # FFT
            fft = np.fft.rfft(windowed)
            magnitude = np.abs(fft)
            
            # 频率轴
            frequencies = np.fft.rfftfreq(len(audio_data), 1/self.sample_rate)
            
            # 只保留感兴趣的频率范围
            mask = (frequencies >= self.min_frequency) & (frequencies <= self.max_frequency)
            
            return {
                'frequencies': frequencies[mask],
                'magnitudes': magnitude[mask]
            }
            
        except Exception as e:
            print(f"频谱计算错误: {e}")
            return {'frequencies': np.array([]), 'magnitudes': np.array([])}
    
    def _frequency_to_note_info(self, frequency):
        """将频率转换为音符信息"""
        if frequency <= 0:
            return None
        
        try:
            # A4 = 440Hz 作为参考
            A4 = 440.0
            
            # 计算相对于A4的半音数
            semitones_from_A4 = 12 * np.log2(frequency / A4)
            
            # 音符名称
            note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            
            # A是第9个音符（索引9）
            note_index = (9 + round(semitones_from_A4)) % 12
            note_name = note_names[note_index]
            
            # 计算八度
            octave = 4 + (9 + round(semitones_from_A4)) // 12
            
            # 计算音分偏差
            exact_semitone = 9 + semitones_from_A4
            rounded_semitone = round(exact_semitone)
            cents = (exact_semitone - rounded_semitone) * 100
            
            return {
                'note_name': note_name,
                'octave': octave,
                'cents': cents,
                'semitones_from_A4': semitones_from_A4
            }
            
        except Exception as e:
            print(f"音符转换错误: {e}")
            return None
    
    def get_current_pitch_stats(self):
        """获取当前音高统计信息"""
        if len(self.pitch_history) == 0:
            return None
        
        recent_pitches = [p for p in self.pitch_history if p > 0]
        if not recent_pitches:
            return None
        
        return {
            'current_pitch': recent_pitches[-1] if recent_pitches else 0,
            'average_pitch': np.mean(recent_pitches),
            'pitch_variance': np.var(recent_pitches),
            'pitch_range': (min(recent_pitches), max(recent_pitches)),
            'stability': 1.0 / (1.0 + np.var(recent_pitches) / np.mean(recent_pitches)) if recent_pitches else 0
        }
    
    def detect_pitch_yin(self, audio_data, sample_rate):
        """YIN音高检测的公共接口方法（兼容性）"""
        # 更新采样率（如果不同）
        if sample_rate != self.sample_rate:
            self.sample_rate = sample_rate
        
        # 预处理音频
        processed_audio = self._preprocess_audio(audio_data)
        
        # 检测音高
        frequency, confidence = self._detect_pitch_enhanced(processed_audio)
        
        return frequency if frequency > 0 else None
    
    def frequency_to_note_info(self, frequency):
        """频率转音符信息的公共接口方法（兼容性）"""
        note_info = self._frequency_to_note_info(frequency)
        if note_info:
            return (
                note_info['note'],
                note_info['octave'], 
                note_info['midi_note'],
                note_info['cents_deviation']
            )
        return ('?', 0, 0, 0)
