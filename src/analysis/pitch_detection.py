"""
音高检测模块
实现基于频率的音高识别和音乐理论计算
"""

import numpy as np
import scipy.signal
from scipy.fft import fft, fftfreq
import math

class PitchDetector:
    def __init__(self, sample_rate=44100, frame_size=4096):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.window = np.hanning(frame_size)
        
        # A4 = 440Hz 作为参考音高
        self.reference_frequency = 440.0
        self.reference_note = 69  # A4 在MIDI中是69
        
        # 音名映射 (十二平均律)
        self.note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        self.note_names_flat = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
        
        # 频率范围限制 (人声和乐器常见范围)
        self.min_frequency = 80.0   # 约 E2
        self.max_frequency = 2000.0 # 约 B6
        
    def frequency_to_midi_note(self, frequency):
        """
        将频率转换为MIDI音符编号
        公式: midi_note = 69 + 12 * log2(f / 440)
        """
        if frequency <= 0:
            return None
        
        midi_note = 69 + 12 * math.log2(frequency / self.reference_frequency)
        return midi_note
    
    def midi_note_to_frequency(self, midi_note):
        """
        将MIDI音符编号转换为频率
        公式: f = 440 * 2^((midi_note - 69) / 12)
        """
        frequency = self.reference_frequency * (2 ** ((midi_note - 69) / 12))
        return frequency
    
    def midi_note_to_note_name(self, midi_note, use_sharps=True):
        """
        将MIDI音符编号转换为音名和八度
        """
        if midi_note is None:
            return None, None
        
        # 四舍五入到最近的半音
        midi_note_rounded = round(midi_note)
        
        # 计算音名索引 (0-11)
        note_index = midi_note_rounded % 12
        
        # 计算八度 (C4 = MIDI 60)
        octave = (midi_note_rounded // 12) - 1
        
        # 获取音名
        note_names = self.note_names if use_sharps else self.note_names_flat
        note_name = note_names[note_index]
        
        return note_name, octave
    
    def frequency_to_note_info(self, frequency, use_sharps=True):
        """
        将频率转换为完整的音符信息
        返回: (音名, 八度, MIDI音符号, 音分偏差)
        """
        if not (self.min_frequency <= frequency <= self.max_frequency):
            return None, None, None, None
        
        midi_note = self.frequency_to_midi_note(frequency)
        if midi_note is None:
            return None, None, None, None
        
        # 计算与最近半音的偏差 (音分, cents)
        midi_note_rounded = round(midi_note)
        cents_deviation = (midi_note - midi_note_rounded) * 100
        
        note_name, octave = self.midi_note_to_note_name(midi_note, use_sharps)
        
        return note_name, octave, midi_note_rounded, cents_deviation
    
    def detect_pitch_autocorrelation(self, audio_frame):
        """
        使用自相关方法检测音高
        适合单音音高检测
        """
        if len(audio_frame) != self.frame_size:
            return None
        
        # 应用窗函数
        windowed_frame = audio_frame * self.window
        
        # 计算自相关
        autocorr = np.correlate(windowed_frame, windowed_frame, mode='full')
        autocorr = autocorr[autocorr.size // 2:]
        
        # 寻找第一个峰值 (跳过零延迟)
        min_period = int(self.sample_rate / self.max_frequency)
        max_period = int(self.sample_rate / self.min_frequency)
        
        if max_period >= len(autocorr):
            return None
        
        # 在有效范围内寻找最大值
        autocorr_range = autocorr[min_period:max_period]
        if len(autocorr_range) == 0:
            return None
        
        peak_index = np.argmax(autocorr_range) + min_period
        
        # 计算频率
        frequency = self.sample_rate / peak_index
        
        # 验证频率是否在合理范围内
        if self.min_frequency <= frequency <= self.max_frequency:
            return frequency
        
        return None
    
    def detect_pitch_fft(self, audio_frame):
        """
        使用FFT方法检测音高
        适合谐波丰富的音频
        """
        if len(audio_frame) != self.frame_size:
            return None
        
        # 应用窗函数
        windowed_frame = audio_frame * self.window
        
        # 计算FFT
        fft_result = fft(windowed_frame)
        magnitude = np.abs(fft_result[:len(fft_result)//2])
        frequencies = fftfreq(len(windowed_frame), 1/self.sample_rate)[:len(magnitude)]
        
        # 在有效频率范围内寻找峰值
        valid_indices = np.where((frequencies >= self.min_frequency) & 
                                (frequencies <= self.max_frequency))[0]
        
        if len(valid_indices) == 0:
            return None
        
        valid_magnitudes = magnitude[valid_indices]
        valid_frequencies = frequencies[valid_indices]
        
        # 找到最强的频率分量
        peak_index = np.argmax(valid_magnitudes)
        fundamental_frequency = valid_frequencies[peak_index]
        
        return fundamental_frequency
    
    def detect_pitch_yin(self, audio_frame, threshold=0.1):
        """
        使用YIN算法检测音高
        更准确的音高检测算法
        """
        if len(audio_frame) != self.frame_size:
            return None
        
        # YIN算法的差函数
        frame_length = len(audio_frame)
        half_frame = frame_length // 2
        
        # 计算差函数
        diff_function = np.zeros(half_frame)
        for tau in range(1, half_frame):
            for j in range(half_frame):
                diff_function[tau] += (audio_frame[j] - audio_frame[j + tau]) ** 2
        
        # 累积平均归一化差函数 (CMNDF)
        cmndf = np.zeros_like(diff_function)
        cmndf[0] = 1.0
        
        running_sum = 0.0
        for tau in range(1, half_frame):
            running_sum += diff_function[tau]
            if running_sum != 0:
                cmndf[tau] = diff_function[tau] / (running_sum / tau)
            else:
                cmndf[tau] = 1.0
        
        # 寻找第一个低于阈值的最小值
        min_period = int(self.sample_rate / self.max_frequency)
        max_period = int(self.sample_rate / self.min_frequency)
        
        tau_min = min_period
        for tau in range(min_period, min(max_period, len(cmndf))):
            if cmndf[tau] < threshold:
                # 在阈值以下寻找局部最小值
                while tau + 1 < len(cmndf) and cmndf[tau + 1] < cmndf[tau]:
                    tau += 1
                tau_min = tau
                break
        
        if tau_min == min_period:
            return None
        
        # 计算频率
        frequency = self.sample_rate / tau_min
        
        if self.min_frequency <= frequency <= self.max_frequency:
            return frequency
        
        return None
    
    def get_note_position_on_staff(self, note_name, octave, clef='treble'):
        """
        计算音符在五线谱上的位置
        返回相对于中央线的位置 (正数向上，负数向下)
        """
        if note_name is None or octave is None:
            return None
        
        # 定义基准位置 (中央C = C4)
        base_notes = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
        
        # 处理升降号
        base_note = note_name[0]
        if base_note not in base_notes:
            return None
        
        # 计算相对于C4的位置
        note_index = base_notes.index(base_note)
        octave_offset = (octave - 4) * 7  # 每个八度7个基本音
        
        total_position = octave_offset + note_index
        
        # 高音谱号: 中央C在第一条加线下方
        if clef == 'treble':
            staff_position = total_position - 0  # C4为基准
        # 低音谱号: 中央C在第一条加线上方  
        elif clef == 'bass':
            staff_position = total_position - 12  # 低音谱号的C2为基准
        else:
            staff_position = total_position
        
        return staff_position

# 音高平滑滤波器
class PitchSmoother:
    def __init__(self, window_size=5, confidence_threshold=0.7):
        self.window_size = window_size
        self.confidence_threshold = confidence_threshold
        self.pitch_history = []
        self.confidence_history = []
        
    def add_pitch(self, frequency, confidence=1.0):
        """
        添加新的音高检测结果
        confidence: 0-1之间的置信度
        """
        self.pitch_history.append(frequency)
        self.confidence_history.append(confidence)
        
        # 保持窗口大小
        if len(self.pitch_history) > self.window_size:
            self.pitch_history.pop(0)
            self.confidence_history.pop(0)
    
    def get_smoothed_pitch(self):
        """
        获取平滑后的音高
        """
        if not self.pitch_history:
            return None
        
        # 过滤低置信度的结果
        valid_pitches = []
        valid_confidences = []
        
        for pitch, conf in zip(self.pitch_history, self.confidence_history):
            if pitch is not None and conf >= self.confidence_threshold:
                valid_pitches.append(pitch)
                valid_confidences.append(conf)
        
        if not valid_pitches:
            return None
        
        # 加权平均
        if len(valid_confidences) > 0:
            weights = np.array(valid_confidences)
            weighted_pitch = np.average(valid_pitches, weights=weights)
            return weighted_pitch
        else:
            return np.mean(valid_pitches)
    
    def clear(self):
        """清空历史记录"""
        self.pitch_history.clear()
        self.confidence_history.clear()

if __name__ == "__main__":
    # 测试音高检测器
    detector = PitchDetector()
    
    # 测试频率到音名的转换
    test_frequencies = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25]
    test_names = ['C4', 'D4', 'E4', 'F4', 'G4', 'A4', 'B4', 'C5']
    
    print("频率到音名转换测试:")
    for freq, expected in zip(test_frequencies, test_names):
        note_name, octave, midi, cents = detector.frequency_to_note_info(freq)
        actual = f"{note_name}{octave}"
        print(f"{freq:7.2f} Hz -> {actual:3s} (期望: {expected:3s}) | MIDI: {midi:2d} | 偏差: {cents:+5.1f} cents")
    
    print("\n音符在五线谱上的位置:")
    for freq, expected in zip(test_frequencies, test_names):
        note_name, octave, _, _ = detector.frequency_to_note_info(freq)
        position = detector.get_note_position_on_staff(note_name, octave)
        print(f"{expected:3s} -> 位置: {position:2d}")
