"""
重叠音框音高分析器
实现心电图式的高敏感度音高检测和可视化
"""

import numpy as np
import threading
import time
import queue
from collections import deque
from scipy.signal import butter, filtfilt, medfilt
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from datetime import datetime, timedelta

class OverlappingFrameAnalyzer:
    """重叠音框音高分析器"""
    
    def __init__(self, sample_rate=44100, frame_size=256, overlap=84):
        self.sample_rate = sample_rate
        self.frame_size = frame_size  # 音框长度
        
        # 计算合理的参数以达到64帧/秒
        target_frame_rate = 64  # 目标64帧/秒
        self.hop_size = int(sample_rate / target_frame_rate)  # 689样本
        
        # 确保frame_size >= hop_size，避免负重叠
        if self.frame_size < self.hop_size:
            self.frame_size = self.hop_size + 128  # 增加frame_size，保证有重叠
        
        self.overlap = self.frame_size - self.hop_size  # 重新计算重叠
        
        print(f"音框参数:")
        print(f"  帧长度: {self.frame_size} 样本 ({self.frame_size/sample_rate*1000:.1f}ms)")
        print(f"  跳跃大小: {self.hop_size} 样本 ({self.hop_size/sample_rate*1000:.1f}ms)")
        print(f"  重叠大小: {self.overlap} 样本 ({self.overlap/sample_rate*1000:.1f}ms)")
        print(f"  音框率: {sample_rate/self.hop_size:.1f} 帧/秒")
        
        # 音高历史数据（心电图式记录）
        self.max_history = 1000  # 保存1000个点，约15秒数据
        self.pitch_history = deque(maxlen=self.max_history)
        self.time_history = deque(maxlen=self.max_history)
        self.note_history = deque(maxlen=self.max_history)
        self.confidence_history = deque(maxlen=self.max_history)
        
        # 音频缓冲区
        self.audio_buffer = np.zeros(frame_size * 2)  # 双倍缓冲
        self.buffer_pos = 0
        
        # 控制变量
        self.is_running = False
        self.analysis_thread = None
        
        # 回调函数
        self.pitch_callback = None
        self.visualization_callback = None
        
        # 音符映射
        self.note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
    def start_analysis(self, pitch_callback=None, visualization_callback=None):
        """开始分析"""
        if self.is_running:
            return False
        
        self.pitch_callback = pitch_callback
        self.visualization_callback = visualization_callback
        self.is_running = True
        
        self.analysis_thread = threading.Thread(target=self._analysis_loop)
        self.analysis_thread.daemon = True
        self.analysis_thread.start()
        
        return True
    
    def stop_analysis(self):
        """停止分析"""
        self.is_running = False
        if self.analysis_thread:
            self.analysis_thread.join()
    
    def add_audio_data(self, audio_data):
        """添加音频数据到缓冲区"""
        if not self.is_running:
            return
        
        # 将新数据添加到缓冲区
        data_len = len(audio_data)
        
        # 确保输入数据不超过缓冲区容量
        if data_len > len(self.audio_buffer):
            # 如果输入数据太大，只取最后部分
            audio_data = audio_data[-len(self.audio_buffer):]
            data_len = len(audio_data)
        
        # 循环缓冲区处理
        if self.buffer_pos + data_len <= len(self.audio_buffer):
            # 直接添加到缓冲区
            self.audio_buffer[self.buffer_pos:self.buffer_pos + data_len] = audio_data
            self.buffer_pos += data_len
        else:
            # 缓冲区溢出处理
            remaining_space = len(self.audio_buffer) - self.buffer_pos
            
            # 先填满剩余空间
            if remaining_space > 0:
                self.audio_buffer[self.buffer_pos:] = audio_data[:remaining_space]
            
            # 计算溢出的数据量
            overflow = data_len - remaining_space
            
            if overflow > 0:
                # 移动缓冲区数据，为新数据腾出空间
                move_amount = min(overflow, len(self.audio_buffer) - self.frame_size)
                if move_amount > 0:
                    self.audio_buffer[:-move_amount] = self.audio_buffer[move_amount:]
                    # 添加溢出的数据到末尾
                    insert_amount = min(overflow, move_amount)
                    self.audio_buffer[-insert_amount:] = audio_data[remaining_space:remaining_space + insert_amount]
                    self.buffer_pos = len(self.audio_buffer)
                else:
                    # 重置缓冲区
                    self.buffer_pos = min(data_len, len(self.audio_buffer))
                    self.audio_buffer[:self.buffer_pos] = audio_data[:self.buffer_pos]
    
    def _analysis_loop(self):
        """分析循环 - 以64帧/秒的速度处理"""
        frame_interval = 1.0 / 64  # 约15.6ms间隔
        
        while self.is_running:
            start_time = time.time()
            
            # 检查是否有足够的数据进行分析
            if self.buffer_pos >= self.frame_size:
                # 提取当前音框
                frame_start = max(0, self.buffer_pos - self.frame_size)
                frame = self.audio_buffer[frame_start:frame_start + self.frame_size].copy()
                
                # 分析当前音框
                self._analyze_frame(frame)
                
                # 移动到下一个音框位置
                # 不移动缓冲区位置，让add_audio_data处理
            
            # 控制帧率
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def _analyze_frame(self, frame):
        """分析单个音框"""
        try:
            current_time = time.time()
            
            # 1. 预处理
            processed_frame = self._preprocess_frame(frame)
            
            # 2. 音高检测
            frequency, confidence = self._detect_pitch_yin(processed_frame)
            
            # 3. 转换为音符
            note_info = self._frequency_to_note(frequency) if frequency > 0 else None
            
            # 4. 记录历史数据
            self.pitch_history.append(frequency if frequency > 0 else 0)
            self.time_history.append(current_time)
            self.note_history.append(note_info)
            self.confidence_history.append(confidence)
            
            # 5. 回调通知
            if self.pitch_callback:
                pitch_data = {
                    'frequency': frequency,
                    'note_info': note_info,
                    'confidence': confidence,
                    'timestamp': current_time
                }
                self.pitch_callback(pitch_data)
            
            # 6. 可视化回调
            if self.visualization_callback:
                vis_data = {
                    'pitch_history': list(self.pitch_history),
                    'time_history': list(self.time_history),
                    'note_history': list(self.note_history),
                    'confidence_history': list(self.confidence_history)
                }
                self.visualization_callback(vis_data)
                
        except Exception as e:
            print(f"音框分析错误: {e}")
    
    def _preprocess_frame(self, frame):
        """音框预处理"""
        # 1. 归一化
        frame = frame.astype(np.float32)
        if np.max(np.abs(frame)) > 0:
            frame = frame / np.max(np.abs(frame))
        
        # 2. 加窗 (汉明窗)
        window = np.hamming(len(frame))
        frame = frame * window
        
        # 3. 高通滤波去除直流分量
        if len(frame) > 10:
            nyquist = self.sample_rate / 2
            cutoff = 80.0 / nyquist
            try:
                b, a = butter(2, cutoff, btype='high')
                frame = filtfilt(b, a, frame)
            except:
                pass
        
        return frame
    
    def _detect_pitch_yin(self, frame):
        """YIN音高检测算法"""
        try:
            frame_length = len(frame)
            if frame_length < 64:
                return 0, 0.0
            
            # YIN算法参数
            min_period = int(self.sample_rate / 800)  # 最高800Hz
            max_period = int(self.sample_rate / 60)   # 最低60Hz
            max_period = min(max_period, frame_length // 2)
            
            if max_period <= min_period:
                return 0, 0.0
            
            # 1. 差分函数
            diff = self._yin_difference_function(frame, max_period)
            
            # 2. 累积平均归一化差分函数
            cmnd = self._yin_cumulative_mean_normalized_difference(diff)
            
            # 3. 绝对阈值
            tau = self._yin_absolute_threshold(cmnd, 0.1, min_period)
            
            if tau == 0:
                return 0, 0.0
            
            # 4. 抛物线插值
            if tau < len(cmnd) - 1:
                interpolated_tau = self._parabolic_interpolation(cmnd, tau)
                if interpolated_tau > 0:
                    tau = interpolated_tau
            
            # 5. 计算频率和置信度
            frequency = self.sample_rate / tau
            confidence = 1.0 - cmnd[tau] if tau < len(cmnd) else 0.0
            
            # 频率范围检查
            if 60 <= frequency <= 2000:
                return frequency, confidence
            else:
                return 0, 0.0
                
        except Exception as e:
            return 0, 0.0
    
    def _yin_difference_function(self, frame, max_period):
        """YIN差分函数"""
        diff = np.zeros(max_period + 1)
        for tau in range(1, max_period + 1):
            if tau < len(frame):
                diff[tau] = np.sum((frame[:-tau] - frame[tau:]) ** 2)
        return diff
    
    def _yin_cumulative_mean_normalized_difference(self, diff):
        """累积平均归一化差分函数"""
        cmnd = np.zeros_like(diff)
        cmnd[0] = 1.0
        
        cumulative_sum = 0.0
        for tau in range(1, len(diff)):
            cumulative_sum += diff[tau]
            if cumulative_sum > 0:
                cmnd[tau] = diff[tau] / (cumulative_sum / tau)
            else:
                cmnd[tau] = 1.0
        
        return cmnd
    
    def _yin_absolute_threshold(self, cmnd, threshold, min_period):
        """绝对阈值法找到最小值"""
        for tau in range(min_period, len(cmnd)):
            if cmnd[tau] < threshold:
                return tau
        
        # 如果没有找到低于阈值的，返回最小值位置
        if len(cmnd) > min_period:
            return np.argmin(cmnd[min_period:]) + min_period
        return 0
    
    def _parabolic_interpolation(self, array, peak_index):
        """抛物线插值细化峰值位置"""
        if peak_index == 0 or peak_index == len(array) - 1:
            return peak_index
        
        y1, y2, y3 = array[peak_index-1], array[peak_index], array[peak_index+1]
        
        # 抛物线插值公式
        denom = 2 * (2*y2 - y1 - y3)
        if abs(denom) < 1e-10:
            return peak_index
        
        offset = (y3 - y1) / denom
        return peak_index + offset
    
    def _frequency_to_note(self, frequency):
        """频率转音符信息"""
        if frequency <= 0:
            return None
        
        # A4 = 440Hz 作为参考
        A4 = 440.0
        
        # 计算相对于A4的半音数
        semitones = 12 * np.log2(frequency / A4)
        
        # 计算MIDI音符号
        midi_note = int(round(69 + semitones))
        
        # 计算音符名和八度
        note_index = (midi_note - 12) % 12
        octave = (midi_note - 12) // 12
        note_name = self.note_names[note_index]
        
        # 计算音分偏差
        exact_semitones = 69 + semitones - midi_note
        cents = exact_semitones * 100
        
        return {
            'note': note_name,
            'octave': octave,
            'midi_note': midi_note,
            'frequency': frequency,
            'cents_deviation': cents,
            'note_display': f"{note_name}{octave}"
        }
    
    def get_ecg_style_data(self, time_window=10.0):
        """获取心电图式数据用于可视化"""
        if not self.time_history:
            return None
        
        current_time = time.time()
        start_time = current_time - time_window
        
        # 过滤时间窗口内的数据
        indices = [i for i, t in enumerate(self.time_history) if t >= start_time]
        
        if not indices:
            return None
        
        return {
            'times': [self.time_history[i] - start_time for i in indices],
            'frequencies': [self.pitch_history[i] for i in indices],
            'notes': [self.note_history[i] for i in indices],
            'confidences': [self.confidence_history[i] for i in indices],
            'time_window': time_window
        }
