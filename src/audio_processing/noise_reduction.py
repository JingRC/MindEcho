"""
音频降噪处理模块
支持多种降噪算法：基础频域降噪、AI降噪、高级音乐保护
"""

import numpy as np
import scipy.signal as signal
from scipy.fft import fft, ifft, fftfreq, rfft, irfft
from scipy.signal import butter, filtfilt, iirnotch
from collections import deque
import warnings
warnings.filterwarnings("ignore")

VERBOSE = False  # 全局降噪模块日志开关（默认关闭）

class NoiseReductionProcessor:
    """降噪处理器主类"""
    
    def __init__(self, sample_rate=44100, frame_size=2048):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.hop_length = frame_size // 4  # 75%重叠
        
        # 降噪模式 - 🎯 默认设置为基础频域降噪
        self.noise_reduction_mode = "基础频域降噪"  # 关闭, 基础频域降噪, AI降噪, 高级音乐保护
        
        # 基础频域降噪参数
        self.noise_floor_ratio = 0.1  # 噪声底层比例
        self.spectral_floor = 0.02    # 频谱底层
        self.smoothing_factor = 0.8   # 平滑因子
        
        # 噪声估计历史缓冲区
        self.noise_profile_buffer = deque(maxlen=10)  # 保存10帧噪声档案
        self.noise_profile = None
        self.frame_count = 0
        
        # 动态陷波滤波器参数
        self.notch_frequencies = [50, 60, 100, 120, 240]  # 常见电源噪声频率
        self.notch_quality = 30  # Q因子
        
        # 保护音乐频段 (基本音高范围: 80Hz - 4000Hz)
        self.music_freq_low = 80
        self.music_freq_high = 4000
        self._analysis_window = None
        self._freq_bins = None
        self._music_mask = None
        self._notch_attenuation_mask = None
        self._frame_buffer = None
        self._refresh_processing_cache()
        
        if VERBOSE:
            print(f"🎵 降噪处理器初始化完成")
            print(f"  采样率: {sample_rate} Hz")
            print(f"  帧大小: {frame_size} 样本")
            print(f"  跳跃长度: {self.hop_length} 样本")
            print(f"  音乐保护频段: {self.music_freq_low}-{self.music_freq_high} Hz")
            print(f"  🎯 默认降噪模式: {self.noise_reduction_mode}")  # 新增调试信息
    
    def set_noise_reduction_mode(self, mode):
        """设置降噪模式"""
        if mode in ["关闭", "基础频域降噪", "AI降噪", "高级音乐保护"]:
            self.noise_reduction_mode = mode
            if VERBOSE:
                print(f"🔧 降噪模式已设置为: {mode}")
            
            # 重置噪声档案
            if mode != "关闭":
                self.noise_profile_buffer.clear()
                self.noise_profile = None
                self.frame_count = 0
        else:
            if VERBOSE:
                print(f"❌ 无效的降噪模式: {mode}")

    def _refresh_processing_cache(self):
        """缓存固定帧长下可复用的窗函数和频域掩码。"""
        try:
            frame_size = max(1, int(self.frame_size))
            self._analysis_window = np.hanning(frame_size).astype(np.float32)
            freq_len = frame_size // 2 + 1
            self._freq_bins = np.fft.rfftfreq(frame_size, d=1.0 / float(self.sample_rate))
            self._music_mask = (self._freq_bins >= float(self.music_freq_low)) & (self._freq_bins <= float(self.music_freq_high))
            self._frame_buffer = np.zeros(frame_size, dtype=np.float32)

            notch_mask = np.ones(freq_len, dtype=np.float32)
            bandwidth = max(1, int(self.sample_rate / frame_size * 2))
            gaussian_div = 2.0 * max((bandwidth / 3.0) ** 2, 1e-12)
            for notch_freq in self.notch_frequencies:
                if notch_freq >= self.sample_rate / 2:
                    continue
                freq_idx = int(np.argmin(np.abs(self._freq_bins - notch_freq)))
                start_idx = max(0, freq_idx - bandwidth)
                end_idx = min(freq_len, freq_idx + bandwidth + 1)
                idx_range = np.arange(start_idx, end_idx, dtype=np.float32)
                attenuation = np.exp(-((idx_range - float(freq_idx)) ** 2) / gaussian_div)
                notch_mask[start_idx:end_idx] *= (1.0 - 0.8 * attenuation).astype(np.float32)
            self._notch_attenuation_mask = notch_mask
        except Exception:
            self._analysis_window = None
            self._freq_bins = None
            self._music_mask = None
            self._notch_attenuation_mask = None
            self._frame_buffer = None
    
    def process_audio(self, audio_data):
        """处理音频数据 - 主入口"""
        # 🔥 添加详细的模式检查调试信息
        if not hasattr(self, '_process_counter'):
            self._process_counter = 0
            if VERBOSE:
                print(f"🎛️ 降噪处理器首次调用，当前模式: {self.noise_reduction_mode}")
        
        self._process_counter += 1
        
        if self.noise_reduction_mode == "关闭":
            if VERBOSE and self._process_counter % 500 == 1:  # 每500次输出一次状态
                print(f"🔇 降噪处理器: 模式={self.noise_reduction_mode}，完全跳过所有降噪处理")
                print(f"   ⚙️ 音频数据直接通过，无任何修改")
            return audio_data.copy()  # 🎯 确保返回原始数据的副本，避免任何引用问题
        elif self.noise_reduction_mode == "基础频域降噪":
            if VERBOSE and self._process_counter % 100 == 1:  # 每100次输出一次状态
                original_rms = np.sqrt(np.mean(audio_data ** 2))
                print(f"🎵 降噪处理器: 模式={self.noise_reduction_mode}，开始频域降噪处理")
                print(f"   📊 输入RMS: {original_rms:.4f}")
            
            result = self._basic_spectral_noise_reduction(audio_data)
            
            if VERBOSE and self._process_counter % 100 == 1:  # 对应输出处理结果
                result_rms = np.sqrt(np.mean(result ** 2))
                print(f"   📊 输出RMS: {result_rms:.4f}")
                print(f"   🔄 降噪强度: {((result_rms/np.sqrt(np.mean(audio_data ** 2)) - 1) * 100):+.1f}%")
            
            return result
        elif self.noise_reduction_mode == "AI降噪":
            # TODO: 未来实现AI降噪
            if VERBOSE and self._process_counter % 200 == 1:
                print("🚧 AI降噪功能开发中，返回原始音频...")
            return audio_data
        elif self.noise_reduction_mode == "高级音乐保护":
            # TODO: 未来实现高级音乐保护
            if VERBOSE and self._process_counter % 200 == 1:
                print("🚧 高级音乐保护功能开发中，返回原始音频...")
            return audio_data
        else:
            if VERBOSE and self._process_counter % 200 == 1:
                print(f"⚠️ 未知降噪模式: {self.noise_reduction_mode}，返回原始音频")
            return audio_data
    
    def _basic_spectral_noise_reduction(self, audio_data):
        """基础频域降噪算法"""
        try:
            original_length = len(audio_data)
            # 确保输入数据长度合适
            if original_length < self.frame_size:
                # 如果数据不够，零填充
                if self._frame_buffer is None or self._frame_buffer.size != self.frame_size:
                    self._refresh_processing_cache()
                padded_data = self._frame_buffer
                padded_data.fill(0.0)
                padded_data[:original_length] = audio_data
                audio_data = padded_data
                return self._process_single_frame(audio_data, original_length)
            elif original_length > self.frame_size:
                # 滑动窗口逐帧处理，避免截断丢数据
                hop = max(1, self.frame_size // 4)
                output = np.zeros(original_length, dtype=np.float32)
                weight = np.zeros(original_length, dtype=np.float32)
                win = self._analysis_window if self._analysis_window is not None and len(self._analysis_window) == self.frame_size else np.hanning(self.frame_size).astype(np.float32)
                for start in range(0, original_length, hop):
                    end = min(start + self.frame_size, original_length)
                    chunk = np.zeros(self.frame_size, dtype=np.float32)
                    seg_len = end - start
                    chunk[:seg_len] = audio_data[start:end]
                    processed_chunk = self._process_single_frame(chunk, seg_len)
                    out_len = min(seg_len, len(processed_chunk))
                    output[start:start+out_len] += processed_chunk[:out_len] * win[:out_len]
                    weight[start:start+out_len] += win[:out_len]
                mask = weight > 1e-9
                output[mask] /= weight[mask]
                return output.astype(np.float32)
            else:
                return self._process_single_frame(audio_data, original_length)
        except Exception as e:
            print(f"❌ 基础频域降噪处理错误: {e}")
            return audio_data

    def _process_single_frame(self, audio_data, original_length):
        """处理单个帧的频谱降噪"""
        try:
            # 步骤1: 应用窗函数
            if self._analysis_window is None or self._analysis_window.size != len(audio_data):
                self._refresh_processing_cache()
            windowed_data = audio_data * self._analysis_window
            
            # 步骤2: FFT变换到频域
            fft_data = rfft(windowed_data)
            magnitude = np.abs(fft_data)
            phase = np.angle(fft_data)
            
            # 步骤3: 噪声估计 (使用前几帧作为噪声档案)
            self._update_noise_profile(magnitude)
            
            if self.noise_profile is not None:
                # 步骤4: 频谱减法降噪
                clean_magnitude = self._spectral_subtraction(magnitude, self.noise_profile)
                
                # 步骤5: 动态陷波滤波去除固定频率噪声
                clean_magnitude = self._apply_notch_filtering_freq_domain(clean_magnitude)
                
                # 步骤6: 音乐频段保护
                clean_magnitude = self._protect_music_frequencies(magnitude, clean_magnitude)
                
                # 步骤7: 重建信号
                clean_fft = clean_magnitude * np.exp(1j * phase)
                clean_audio = irfft(clean_fft)
                
                # 步骤8: 去除窗函数效果和长度调整
                if len(clean_audio) > original_length:
                    clean_audio = clean_audio[:original_length]
                
                return clean_audio.astype(np.float32)
            else:
                # 噪声档案还未建立，返回原始数据
                return np.array(audio_data[:original_length], copy=True)
                
        except Exception as e:
            print(f"❌ 基础频域降噪处理错误: {e}")
            return audio_data
    
    def _update_noise_profile(self, magnitude):
        """更新噪声档案"""
        self.frame_count += 1
        
        # 前10帧用于建立噪声档案
        if self.frame_count <= 10:
            self.noise_profile_buffer.append(magnitude.copy())
            
            if self.frame_count == 10:
                # 计算平均噪声档案
                self.noise_profile = np.mean(np.array(self.noise_profile_buffer), axis=0)
                if VERBOSE:
                    print(f"✅ 噪声档案建立完成 (基于前10帧数据)")
        else:
            # 动态更新噪声档案 (慢速适应)
            if self.noise_profile is not None:
                adaptation_rate = 0.01  # 很慢的适应速度，保持稳定
                self.noise_profile = (1 - adaptation_rate) * self.noise_profile + adaptation_rate * magnitude
    
    def _spectral_subtraction(self, signal_magnitude, noise_magnitude):
        """频谱减法核心算法"""
        # 计算信噪比
        snr = signal_magnitude / (noise_magnitude + 1e-10)
        
        # 自适应减法因子
        subtraction_factor = np.where(snr > 3, 1.5, 
                                   np.where(snr > 2, 1.2, 
                                         np.where(snr > 1.5, 1.0, 0.5)))
        
        # 执行谱减法
        enhanced_magnitude = signal_magnitude - subtraction_factor * noise_magnitude
        
        # 设置频谱底层，防止过度削减
        spectral_floor = self.spectral_floor * signal_magnitude
        enhanced_magnitude = np.maximum(enhanced_magnitude, spectral_floor)
        
        # 平滑处理
        if hasattr(self, '_prev_magnitude'):
            enhanced_magnitude = (self.smoothing_factor * self._prev_magnitude + 
                                (1 - self.smoothing_factor) * enhanced_magnitude)
        
        self._prev_magnitude = enhanced_magnitude.copy()
        
        return enhanced_magnitude
    
    def _apply_notch_filtering_freq_domain(self, magnitude):
        """在频域应用陷波滤波"""
        if self._notch_attenuation_mask is None or self._notch_attenuation_mask.size != len(magnitude):
            self._refresh_processing_cache()
        if self._notch_attenuation_mask is None:
            return magnitude
        return magnitude * self._notch_attenuation_mask
    
    def _protect_music_frequencies(self, original_magnitude, processed_magnitude):
        """保护音乐频段，避免过度处理"""
        if self._music_mask is None or self._music_mask.size != len(original_magnitude):
            self._refresh_processing_cache()
        music_mask = self._music_mask
        if music_mask is None:
            return processed_magnitude.copy()
        
        # 在音乐频段内，减少降噪强度
        protection_factor = 0.7  # 保护因子，0.7表示只应用70%的降噪效果
        
        protected_magnitude = processed_magnitude.copy()
        protected_magnitude[music_mask] = (
            protection_factor * processed_magnitude[music_mask] + 
            (1 - protection_factor) * original_magnitude[music_mask]
        )
        
        return protected_magnitude
    
    def apply_time_domain_notch_filter(self, audio_data):
        """时域陷波滤波器 (可独立使用)"""
        try:
            filtered_audio = audio_data.copy()
            
            for freq in self.notch_frequencies:
                if freq < self.sample_rate / 2:
                    # 设计IIR陷波滤波器
                    b, a = iirnotch(freq, self.notch_quality, self.sample_rate)
                    filtered_audio = filtfilt(b, a, filtered_audio)
            
            return filtered_audio.astype(np.float32)
            
        except Exception as e:
            print(f"❌ 时域陷波滤波错误: {e}")
            return audio_data
    
    def get_noise_reduction_info(self):
        """获取降噪处理信息"""
        return {
            'mode': self.noise_reduction_mode,
            'sample_rate': self.sample_rate,
            'frame_size': self.frame_size,
            'noise_profile_ready': self.noise_profile is not None,
            'frame_count': self.frame_count,
            'music_protection_range': f"{self.music_freq_low}-{self.music_freq_high} Hz",
            'notch_frequencies': self.notch_frequencies
        }

# 单独的动态陷波滤波器类
class DynamicNotchFilter:
    """动态陷波滤波器"""
    
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self.notch_freqs = [50, 60, 100, 120, 240]  # 默认电源噪声频率
        self.quality_factor = 30
    
    def add_notch_frequency(self, frequency):
        """添加需要滤除的频率"""
        if frequency not in self.notch_freqs and frequency < self.sample_rate / 2:
            self.notch_freqs.append(frequency)
            print(f"✅ 添加陷波频率: {frequency} Hz")
    
    def remove_notch_frequency(self, frequency):
        """移除陷波频率"""
        if frequency in self.notch_freqs:
            self.notch_freqs.remove(frequency)
            print(f"❌ 移除陷波频率: {frequency} Hz")
    
    def apply(self, audio_data):
        """应用陷波滤波"""
        try:
            filtered_audio = audio_data.copy()
            
            for freq in self.notch_freqs:
                if freq < self.sample_rate / 2:
                    b, a = iirnotch(freq, self.quality_factor, self.sample_rate)
                    filtered_audio = filtfilt(b, a, filtered_audio)
            
            return filtered_audio.astype(np.float32)
            
        except Exception as e:
            print(f"❌ 动态陷波滤波器错误: {e}")
            return audio_data

# 测试函数
if __name__ == "__main__":
    # 创建测试信号
    sample_rate = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    
    # 创建包含噪声的测试信号
    clean_signal = np.sin(2 * np.pi * 440 * t)  # 440Hz正弦波
    noise = 0.1 * np.random.randn(len(t))       # 白噪声
    power_line_noise = 0.05 * np.sin(2 * np.pi * 50 * t)  # 50Hz电源噪声
    
    noisy_signal = clean_signal + noise + power_line_noise
    
    # 测试降噪处理器
    processor = NoiseReductionProcessor(sample_rate=sample_rate, frame_size=2048)
    processor.set_noise_reduction_mode("基础频域降噪")
    
    # 分块处理
    frame_size = 2048
    processed_signal = []
    
    for i in range(0, len(noisy_signal), frame_size):
        frame = noisy_signal[i:i+frame_size]
        if len(frame) < frame_size:
            frame = np.pad(frame, (0, frame_size - len(frame)), 'constant')
        
        processed_frame = processor.process_audio(frame)
        processed_signal.extend(processed_frame[:len(noisy_signal[i:i+frame_size])])
    
    processed_signal = np.array(processed_signal)
    
    print("✅ 降噪测试完成")
    print(f"原始信号RMS: {np.sqrt(np.mean(noisy_signal**2)):.4f}")
    print(f"处理后信号RMS: {np.sqrt(np.mean(processed_signal**2)):.4f}")
    print(f"信噪比改善: {20*np.log10(np.sqrt(np.mean(processed_signal**2))/np.sqrt(np.mean((processed_signal-clean_signal[:len(processed_signal)])**2))):.2f} dB")
