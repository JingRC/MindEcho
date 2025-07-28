"""
智能降噪增强系统
集成动态WebRTC参数调整和音乐感知谱减法
"""

import numpy as np
import scipy.signal as signal
from scipy.fft import rfft, irfft
from collections import deque
import warnings
warnings.filterwarnings("ignore")

class AdaptiveNoiseReduction:
    """自适应降噪处理器"""
    
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self.frame_size = 2048
        
        # 降噪参数
        self.aggressiveness_levels = {
            0: {'over_sub': 1.0, 'spectral_floor': 0.1},    # 最轻
            1: {'over_sub': 1.5, 'spectral_floor': 0.05},   # 轻度
            2: {'over_sub': 2.0, 'spectral_floor': 0.02},   # 中度
            3: {'over_sub': 2.5, 'spectral_floor': 0.01}    # 强力
        }
        
        self.current_aggressiveness = 1
        
        # 噪声估计
        self.noise_profile = None
        self.noise_frames = deque(maxlen=10)
        self.adaptation_rate = 0.01
        
        # 音乐感知
        self.protected_bands = []
        self.harmonic_threshold = 0.6
        
        print("🎛️ 自适应降噪处理器初始化完成")
        print(f"  采样率: {sample_rate} Hz")
        print(f"  帧大小: {self.frame_size} 样本")
    
    def set_aggressiveness(self, level):
        """设置降噪强度"""
        if 0 <= level <= 3:
            self.current_aggressiveness = level
            print(f"🔧 降噪强度设置为: {level} ({'最轻,轻度,中度,强力'.split(',')[level]})")
        else:
            print(f"❌ 无效的降噪强度: {level}")
    
    def process_with_pitch_awareness(self, audio_data, pitch=0):
        """音高感知降噪处理"""
        try:
            # 根据音高动态调整降噪强度
            self._adjust_aggressiveness_by_pitch(pitch)
            
            # 确保数据长度
            if len(audio_data) < self.frame_size:
                padded = np.zeros(self.frame_size, dtype=np.float32)
                padded[:len(audio_data)] = audio_data
                audio_data = padded
            elif len(audio_data) > self.frame_size:
                audio_data = audio_data[:self.frame_size]
            
            # 应用窗函数
            windowed = audio_data * np.hanning(len(audio_data))
            
            # FFT变换
            fft_data = rfft(windowed)
            magnitude = np.abs(fft_data)
            phase = np.angle(fft_data)
            
            # 更新噪声档案
            self._update_noise_profile(magnitude)
            
            if self.noise_profile is not None:
                # 音乐感知谱减法
                clean_magnitude = self._musical_spectral_subtraction(
                    magnitude, self.noise_profile, pitch
                )
                
                # 重建信号
                clean_fft = clean_magnitude * np.exp(1j * phase)
                clean_audio = irfft(clean_fft, n=len(audio_data))
                
                return clean_audio.astype(np.float32)
            else:
                return audio_data
                
        except Exception as e:
            print(f"❌ 音高感知降噪错误: {e}")
            return audio_data
    
    def _adjust_aggressiveness_by_pitch(self, pitch):
        """根据音高动态调整降噪强度"""
        if 80 < pitch < 500:  # 人声/乐器主要频段
            target_level = 1  # 轻度降噪，保护音质
        elif pitch == 0:  # 无音高，可能是噪音
            target_level = 2  # 中度降噪
        else:  # 异常频率
            target_level = 3  # 强力降噪
        
        # 平滑过渡
        if target_level != self.current_aggressiveness:
            if hasattr(self, '_aggressiveness_transition_count'):
                self._aggressiveness_transition_count += 1
                if self._aggressiveness_transition_count >= 5:  # 5帧后切换
                    self.set_aggressiveness(target_level)
                    self._aggressiveness_transition_count = 0
            else:
                self._aggressiveness_transition_count = 1
    
    def _update_noise_profile(self, magnitude):
        """更新噪声档案"""
        if len(self.noise_frames) < 10:
            self.noise_frames.append(magnitude.copy())
            if len(self.noise_frames) == 10:
                self.noise_profile = np.mean(np.array(self.noise_frames), axis=0)
                print("✅ 自适应噪声档案建立完成")
        else:
            if self.noise_profile is not None:
                self.noise_profile = ((1 - self.adaptation_rate) * self.noise_profile + 
                                    self.adaptation_rate * magnitude)
    
    def _musical_spectral_subtraction(self, magnitude, noise_profile, pitch):
        """音乐感知谱减法"""
        # 获取当前降噪参数
        params = self.aggressiveness_levels[self.current_aggressiveness]
        over_subtraction = params['over_sub']
        spectral_floor = params['spectral_floor']
        
        # 计算频率轴
        freqs = np.fft.rfftfreq(self.frame_size, 1/self.sample_rate)
        
        # 基础谱减法
        enhanced_magnitude = magnitude - over_subtraction * noise_profile
        floor_magnitude = spectral_floor * magnitude
        enhanced_magnitude = np.maximum(enhanced_magnitude, floor_magnitude)
        
        # 音乐保护处理
        if pitch > 0 and 80 <= pitch <= 500:
            enhanced_magnitude = self._protect_harmonic_structure(
                magnitude, enhanced_magnitude, freqs, pitch
            )
        
        # 平滑处理
        if hasattr(self, '_prev_magnitude'):
            smoothing_factor = 0.7
            enhanced_magnitude = (smoothing_factor * self._prev_magnitude + 
                                (1 - smoothing_factor) * enhanced_magnitude)
        
        self._prev_magnitude = enhanced_magnitude.copy()
        
        return enhanced_magnitude
    
    def _protect_harmonic_structure(self, original_mag, processed_mag, freqs, pitch):
        """保护谐波结构"""
        try:
            # 生成谐波频率列表
            harmonics = [pitch * i for i in range(1, 6)]  # 1-5次谐波
            protection_factor = 0.8  # 保护强度
            
            protected_magnitude = processed_mag.copy()
            
            for harmonic_freq in harmonics:
                if harmonic_freq < self.sample_rate / 2:
                    # 找到谐波频率附近的索引
                    freq_tolerance = pitch * 0.1  # 10%容差
                    harmonic_mask = (freqs >= harmonic_freq - freq_tolerance) & \
                                  (freqs <= harmonic_freq + freq_tolerance)
                    
                    # 在谐波区域减少降噪强度
                    protected_magnitude[harmonic_mask] = (
                        protection_factor * processed_mag[harmonic_mask] + 
                        (1 - protection_factor) * original_mag[harmonic_mask]
                    )
            
            return protected_magnitude
            
        except Exception as e:
            print(f"❌ 谐波保护错误: {e}")
            return processed_mag

class EnvironmentalNoiseFilter:
    """环境噪音过滤器"""
    
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        
        # 常见环境噪音频率
        self.common_noise_freqs = [50, 60, 100, 120, 240, 300, 400, 500]
        
        # 动态噪音检测
        self.noise_energy_threshold = 0.001
        self.spectral_flatness_threshold = 0.8  # 噪音的频谱平坦度高
        
        # 历史记录
        self.energy_history = deque(maxlen=20)
        self.spectral_history = deque(maxlen=10)
        
        print("🌊 环境噪音过滤器初始化完成")
    
    def is_environmental_noise(self, audio_data):
        """判断是否为环境噪音"""
        try:
            # 能量检测
            signal_energy = np.mean(audio_data**2)
            self.energy_history.append(signal_energy)
            
            # 频谱平坦度检测
            fft_data = np.abs(rfft(audio_data * np.hanning(len(audio_data))))
            if len(fft_data) > 1:
                # 计算频谱平坦度（几何平均/算术平均）
                geometric_mean = np.exp(np.mean(np.log(fft_data + 1e-10)))
                arithmetic_mean = np.mean(fft_data)
                spectral_flatness = geometric_mean / (arithmetic_mean + 1e-10)
                self.spectral_history.append(spectral_flatness)
                
                # 环境噪音特征：能量低，频谱平坦
                is_low_energy = signal_energy < self.noise_energy_threshold
                is_flat_spectrum = spectral_flatness > self.spectral_flatness_threshold
                
                # 历史一致性检查
                if len(self.energy_history) >= 5:
                    energy_stability = np.std(list(self.energy_history)[-5:])
                    is_stable_noise = energy_stability < signal_energy * 0.5
                else:
                    is_stable_noise = False
                
                # 综合判断
                is_noise = (is_low_energy and is_flat_spectrum) or \
                          (is_stable_noise and spectral_flatness > 0.6)
                
                if is_noise:
                    print(f"🔍 检测到环境噪音: 能量={signal_energy:.4f}, 平坦度={spectral_flatness:.2f}")
                
                return is_noise
            
            return False
            
        except Exception as e:
            print(f"❌ 环境噪音检测错误: {e}")
            return False
    
    def filter_noise_frequencies(self, audio_data):
        """过滤特定噪音频率"""
        try:
            filtered_audio = audio_data.copy()
            
            # 对每个噪音频率应用陷波滤波
            for noise_freq in self.common_noise_freqs:
                if noise_freq < self.sample_rate / 2:
                    # 设计陷波滤波器
                    q_factor = 30  # 品质因数
                    b, a = signal.iirnotch(noise_freq, q_factor, self.sample_rate)
                    
                    # 应用滤波
                    filtered_audio = signal.filtfilt(b, a, filtered_audio)
            
            return filtered_audio.astype(np.float32)
            
        except Exception as e:
            print(f"❌ 噪音频率过滤错误: {e}")
            return audio_data

class IntegratedSmartProcessor:
    """集成智能处理器 - 整合所有增强功能"""
    
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        
        # 初始化子模块
        self.adaptive_nr = AdaptiveNoiseReduction(sample_rate)
        self.env_filter = EnvironmentalNoiseFilter(sample_rate)
        
        # 处理统计
        self.frames_processed = 0
        self.noise_filtered_count = 0
        
        print("🚀 集成智能处理器初始化完成")
    
    def process_audio_intelligently(self, audio_data, pitch=0):
        """智能音频处理"""
        try:
            self.frames_processed += 1
            
            # 步骤1: 环境噪音检测和过滤
            if self.env_filter.is_environmental_noise(audio_data):
                self.noise_filtered_count += 1
                # 对环境噪音使用强力降噪
                self.adaptive_nr.set_aggressiveness(3)
                processed_audio = self.env_filter.filter_noise_frequencies(audio_data)
            else:
                processed_audio = audio_data
            
            # 步骤2: 自适应降噪处理
            final_audio = self.adaptive_nr.process_with_pitch_awareness(processed_audio, pitch)
            
            # 统计信息（每100帧输出一次）
            if self.frames_processed % 100 == 0:
                noise_ratio = self.noise_filtered_count / self.frames_processed
                print(f"📊 处理统计: {self.frames_processed}帧, 环境噪音过滤率: {noise_ratio:.1%}")
            
            return final_audio
            
        except Exception as e:
            print(f"❌ 智能处理错误: {e}")
            return audio_data
    
    def get_processing_stats(self):
        """获取处理统计信息"""
        return {
            'frames_processed': self.frames_processed,
            'noise_filtered_count': self.noise_filtered_count,
            'noise_filter_ratio': self.noise_filtered_count / max(self.frames_processed, 1),
            'current_aggressiveness': self.adaptive_nr.current_aggressiveness
        }

# 测试函数
def test_smart_noise_reduction():
    """测试智能降噪系统"""
    print("🧪 测试智能降噪系统")
    
    processor = IntegratedSmartProcessor()
    
    # 测试场景1: 正常语音信号
    print("\n📊 测试1: 正常语音信号")
    t = np.linspace(0, 0.1, 4410)
    voice_signal = 0.3 * np.sin(2 * np.pi * 150 * t) + 0.1 * np.random.normal(0, 1, len(t))
    
    processed = processor.process_audio_intelligently(voice_signal, pitch=150)
    print(f"  处理完成，信号长度: {len(processed)}")
    
    # 测试场景2: 环境噪音
    print("\n📊 测试2: 环境噪音信号")
    noise_signal = 0.001 * np.random.normal(0, 1, len(t))  # 低能量白噪声
    
    processed_noise = processor.process_audio_intelligently(noise_signal, pitch=0)
    print(f"  环境噪音处理完成")
    
    # 显示统计
    stats = processor.get_processing_stats()
    print(f"\n📈 处理统计:")
    print(f"  总帧数: {stats['frames_processed']}")
    print(f"  噪音过滤次数: {stats['noise_filtered_count']}")
    print(f"  噪音过滤率: {stats['noise_filter_ratio']:.1%}")
    print(f"  当前降噪强度: {stats['current_aggressiveness']}")
    
    return processor

if __name__ == "__main__":
    test_smart_noise_reduction()
