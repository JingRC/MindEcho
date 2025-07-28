"""
改进的降噪和音高检测算法
解决D5等高频噪声误检测问题
"""

import numpy as np
import scipy.signal as signal
from scipy.fft import fft, ifft, fftfreq, rfft, irfft
from collections import deque
import warnings
warnings.filterwarnings("ignore")

class ImprovedAudioProcessor:
    """改进的音频处理器，集成降噪和稳定音高检测"""
    
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self.frame_size = 2048
        
        # 音高检测参数优化
        self.min_frequency = 80    # 最低频率 (E2)
        self.max_frequency = 500   # 最高频率 (B4+) - 减小范围避免噪声
        
        # 音高跟踪和平滑
        self.pitch_history = deque(maxlen=10)  # 保存最近10个检测结果
        self.confidence_threshold = 0.3       # 置信度阈值
        self.stability_threshold = 50         # 稳定性阈值(Hz)
        
        # 降噪参数优化
        self.noise_profile = None
        self.noise_frames = deque(maxlen=5)   # 减少噪声估计帧数
        self.adaptation_rate = 0.005          # 更慢的适应速度
        
        # 高频噪声抑制
        self.high_freq_cutoff = 600  # 高频截止点
        self.noise_gate_threshold = 0.01  # 噪声门限
        
        print("🎵 改进音频处理器初始化")
        print(f"  音高检测范围: {self.min_frequency}-{self.max_frequency} Hz")
        print(f"  高频截止: {self.high_freq_cutoff} Hz")
        print(f"  稳定性阈值: {self.stability_threshold} Hz")
    
    def process_audio_with_improved_detection(self, audio_data):
        """改进的音频处理和音高检测"""
        try:
            # 步骤1: 预处理 - 去除明显的高频噪声
            filtered_audio = self._apply_anti_alias_filter(audio_data)
            
            # 步骤2: 智能降噪
            denoised_audio = self._intelligent_noise_reduction(filtered_audio)
            
            # 步骤3: 稳定音高检测
            frequency, confidence = self._stable_pitch_detection(denoised_audio)
            
            # 步骤4: 音高跟踪和验证
            validated_frequency = self._validate_and_track_pitch(frequency, confidence)
            
            return validated_frequency, denoised_audio
            
        except Exception as e:
            print(f"❌ 改进音频处理错误: {e}")
            return 0, audio_data
    
    def _apply_anti_alias_filter(self, audio_data):
        """应用抗混叠滤波器，移除高频噪声"""
        try:
            # 设计低通滤波器，截止频率为600Hz
            nyquist = self.sample_rate / 2
            cutoff = min(self.high_freq_cutoff, nyquist * 0.9)
            
            # 5阶巴特沃斯低通滤波器
            b, a = signal.butter(5, cutoff / nyquist, btype='low')
            filtered_audio = signal.filtfilt(b, a, audio_data)
            
            return filtered_audio.astype(np.float32)
            
        except Exception as e:
            print(f"❌ 抗混叠滤波错误: {e}")
            return audio_data
    
    def _intelligent_noise_reduction(self, audio_data):
        """智能降噪 - 针对音高检测优化"""
        try:
            if len(audio_data) < self.frame_size:
                padded_data = np.zeros(self.frame_size)
                padded_data[:len(audio_data)] = audio_data
                audio_data = padded_data
            elif len(audio_data) > self.frame_size:
                audio_data = audio_data[:self.frame_size]
            
            # 应用窗函数
            windowed_data = audio_data * np.hanning(len(audio_data))
            
            # FFT到频域
            fft_data = rfft(windowed_data)
            magnitude = np.abs(fft_data)
            phase = np.angle(fft_data)
            
            # 更新噪声档案
            self._update_noise_profile_conservative(magnitude)
            
            if self.noise_profile is not None:
                # 保守的频谱减法
                clean_magnitude = self._conservative_spectral_subtraction(magnitude)
                
                # 噪声门限
                clean_magnitude = self._apply_noise_gate(clean_magnitude)
                
                # 重建信号
                clean_fft = clean_magnitude * np.exp(1j * phase)
                clean_audio = irfft(clean_fft)
                
                if len(clean_audio) > len(audio_data):
                    clean_audio = clean_audio[:len(audio_data)]
                
                return clean_audio.astype(np.float32)
            else:
                return audio_data
                
        except Exception as e:
            print(f"❌ 智能降噪错误: {e}")
            return audio_data
    
    def _update_noise_profile_conservative(self, magnitude):
        """保守的噪声档案更新"""
        # 只在前5帧建立噪声档案
        if len(self.noise_frames) < 5:
            self.noise_frames.append(magnitude.copy())
            if len(self.noise_frames) == 5:
                self.noise_profile = np.mean(np.array(self.noise_frames), axis=0)
                print("✅ 保守噪声档案建立完成")
        else:
            # 非常慢的适应
            if self.noise_profile is not None:
                self.noise_profile = (1 - self.adaptation_rate) * self.noise_profile + self.adaptation_rate * magnitude
    
    def _conservative_spectral_subtraction(self, signal_magnitude):
        """保守的频谱减法 - 避免过度处理"""
        if self.noise_profile is None:
            return signal_magnitude
        
        # 计算信噪比
        snr = signal_magnitude / (self.noise_profile + 1e-10)
        
        # 更保守的减法因子
        subtraction_factor = np.where(snr > 5, 0.8,      # 很强信号：轻微降噪
                                   np.where(snr > 3, 0.6,  # 强信号：中等降噪  
                                         np.where(snr > 2, 0.4,  # 中等信号：轻降噪
                                               np.where(snr > 1.2, 0.2, 0.1))))  # 弱信号：极轻降噪
        
        # 执行保守频谱减法
        enhanced_magnitude = signal_magnitude - subtraction_factor * self.noise_profile
        
        # 设置较高的频谱底层（50%原始信号）
        spectral_floor = 0.5 * signal_magnitude
        enhanced_magnitude = np.maximum(enhanced_magnitude, spectral_floor)
        
        return enhanced_magnitude
    
    def _apply_noise_gate(self, magnitude):
        """应用噪声门限"""
        # 计算总能量
        total_energy = np.sum(magnitude**2)
        threshold = self.noise_gate_threshold * np.max(magnitude)
        
        # 应用软门限
        gated_magnitude = np.where(magnitude > threshold, magnitude, 
                                 magnitude * (magnitude / threshold)**2)
        
        return gated_magnitude
    
    def _stable_pitch_detection(self, audio_data):
        """稳定的音高检测算法"""
        try:
            if len(audio_data) < 1024:
                return 0, 0
            
            # 限制数据长度
            if len(audio_data) > 2048:
                audio_data = audio_data[:2048]
            
            # 应用窗函数
            windowed = audio_data * np.hanning(len(audio_data))
            
            # 检查信号强度
            signal_power = np.sum(windowed**2)
            if signal_power < 1e-8:  # 信号太弱
                return 0, 0
            
            # 多种方法结合检测
            freq1, conf1 = self._autocorrelation_pitch(windowed)
            freq2, conf2 = self._fft_peak_pitch(windowed)
            
            # 选择置信度更高的结果
            if conf1 > conf2:
                return freq1, conf1
            else:
                return freq2, conf2
                
        except Exception as e:
            print(f"❌ 稳定音高检测错误: {e}")
            return 0, 0
    
    def _autocorrelation_pitch(self, audio_data):
        """自相关音高检测"""
        try:
            correlation = np.correlate(audio_data, audio_data, mode='full')
            correlation = correlation[len(correlation)//2:]
            
            # 计算搜索范围
            min_period = max(1, int(self.sample_rate / self.max_frequency))
            max_period = min(len(correlation), int(self.sample_rate / self.min_frequency))
            
            if max_period <= min_period:
                return 0, 0
            
            # 在指定范围内搜索峰值
            search_range = correlation[min_period:max_period]
            if len(search_range) == 0:
                return 0, 0
            
            # 找到最大峰值
            peak_index = np.argmax(search_range) + min_period
            max_correlation = correlation[peak_index]
            
            # 计算频率和置信度
            frequency = self.sample_rate / peak_index
            confidence = max_correlation / correlation[0] if correlation[0] > 0 else 0
            
            # 验证频率范围
            if self.min_frequency <= frequency <= self.max_frequency and confidence > 0.2:
                return frequency, confidence
            else:
                return 0, 0
                
        except Exception as e:
            print(f"❌ 自相关检测错误: {e}")
            return 0, 0
    
    def _fft_peak_pitch(self, audio_data):
        """FFT峰值音高检测"""
        try:
            # FFT分析
            fft_data = np.fft.fft(audio_data)
            magnitude = np.abs(fft_data[:len(fft_data)//2])
            freqs = np.fft.fftfreq(len(audio_data), 1/self.sample_rate)[:len(magnitude)]
            
            # 限制频率范围
            freq_mask = (freqs >= self.min_frequency) & (freqs <= self.max_frequency)
            valid_magnitudes = magnitude[freq_mask]
            valid_freqs = freqs[freq_mask]
            
            if len(valid_magnitudes) == 0:
                return 0, 0
            
            # 找到最大峰值
            peak_index = np.argmax(valid_magnitudes)
            peak_frequency = valid_freqs[peak_index]
            peak_magnitude = valid_magnitudes[peak_index]
            
            # 计算置信度
            mean_magnitude = np.mean(valid_magnitudes)
            confidence = (peak_magnitude - mean_magnitude) / (peak_magnitude + 1e-10)
            
            if confidence > 0.3:
                return peak_frequency, confidence
            else:
                return 0, 0
                
        except Exception as e:
            print(f"❌ FFT峰值检测错误: {e}")
            return 0, 0
    
    def _validate_and_track_pitch(self, frequency, confidence):
        """验证和跟踪音高"""
        if frequency == 0 or confidence < self.confidence_threshold:
            return 0
        
        # 添加到历史记录
        self.pitch_history.append((frequency, confidence))
        
        # 如果历史记录不足，直接返回
        if len(self.pitch_history) < 3:
            return frequency
        
        # 检查稳定性
        recent_freqs = [f for f, c in list(self.pitch_history)[-5:] if f > 0]
        
        if len(recent_freqs) < 2:
            return frequency
        
        # 计算频率变化
        freq_std = np.std(recent_freqs)
        freq_mean = np.mean(recent_freqs)
        
        # 如果变化太大，可能是噪声
        if freq_std > self.stability_threshold:
            # 检查是否是孤立的高频噪声点
            if frequency > freq_mean + 2 * freq_std and frequency > 400:
                print(f"🚫 检测到疑似高频噪声: {frequency:.1f}Hz (均值: {freq_mean:.1f}Hz)")
                return 0
        
        return frequency

# 测试函数
def test_improved_processor():
    """测试改进的处理器"""
    processor = ImprovedAudioProcessor()
    
    # 生成测试信号：150Hz基音 + 噪声
    duration = 0.1
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # 基音信号
    fundamental = 0.8 * np.sin(2 * np.pi * 150 * t)
    
    # 添加噪声
    noise = 0.3 * np.random.normal(0, 1, len(t))
    high_freq_noise = 0.2 * np.sin(2 * np.pi * 580 * t)  # 模拟D5噪声
    
    test_signal = fundamental + noise + high_freq_noise
    
    # 处理
    detected_freq, processed_audio = processor.process_audio_with_improved_detection(test_signal)
    
    print(f"🎯 测试结果:")
    print(f"  原始基音: 150.0 Hz")
    print(f"  检测频率: {detected_freq:.1f} Hz")
    print(f"  检测误差: {abs(detected_freq - 150):.1f} Hz")
    
    return processor

if __name__ == "__main__":
    test_improved_processor()
