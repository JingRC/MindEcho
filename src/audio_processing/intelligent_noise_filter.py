#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能环境噪音过滤器（修复版）
基于校准的噪音档案进行自适应噪音抑制，保持音质和听感
"""

import numpy as np
from scipy import signal
from scipy.signal import butter, filtfilt, savgol_filter
import time
from collections import deque

class IntelligentNoiseFilter:
    """智能环境噪音过滤器"""
    
    def __init__(self, sample_rate=48000, frame_size=1024):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        
        # 噪音档案
        self.noise_profile = None
        self.is_calibrated = False
        
        # 🔧 优化自适应参数（防止爆炸音效）
        self.noise_gate_threshold = 0.005  # 提高门限，避免过度处理
        self.noise_reduction_strength = 0.3  # 降低强度，温和处理
        self.preservation_factor = 0.7  # 增加原始信号保留比例
        
        # 频域处理
        self.fft_size = 2048
        self.overlap_factor = 0.5
        self.window = np.hanning(self.fft_size)
        
        # 动态调整
        self.signal_history = deque(maxlen=100)
        self.noise_estimation_history = deque(maxlen=50)
        
        # 音质保护
        self.preserve_speech_frequencies = True
        self.speech_freq_range = (85, 3400)  # 人声频率范围
        self.enhance_clarity = True
        
        # 实时统计
        self.processed_frames = 0
        self.noise_reduction_stats = {
            'total_reduction': 0,
            'preservation_ratio': 0,
            'quality_score': 0
        }
    
    def set_noise_profile(self, noise_profile):
        """设置噪音档案"""
        try:
            self.noise_profile = noise_profile
            self.is_calibrated = True
            
            # 分析噪音特征
            if 'spectral_profile' in noise_profile:
                self._setup_spectral_filter(noise_profile['spectral_profile'])
            
            print(f"✅ 噪音过滤器已配置: {noise_profile.get('noise_type', '未知类型')}")
            
        except Exception as e:
            print(f"⚠️ 设置噪音档案错误: {e}")
            self.is_calibrated = False
    
    def load_noise_profile(self, noise_profile):
        """加载噪音档案（兼容旧接口）"""
        self.set_noise_profile(noise_profile)
    
    def _setup_spectral_filter(self, spectral_profile):
        """设置频谱过滤器"""
        try:
            # 获取各频段的噪音功率
            self.low_freq_noise = spectral_profile.get('low_freq_power', 0.001)
            self.mid_freq_noise = spectral_profile.get('mid_freq_power', 0.0008)
            self.high_freq_noise = spectral_profile.get('high_freq_power', 0.0006)
            
            # 设计自适应滤波器
            nyquist = self.sample_rate / 2
            
            # 低频噪音过滤（如电源噪音）
            if self.low_freq_noise > 0.002:
                self.low_cut_freq = 80 / nyquist
                self.use_high_pass = True
            else:
                self.use_high_pass = False
            
            # 高频噪音过滤（如电流音）
            if self.high_freq_noise > 0.001:
                self.high_cut_freq = min(8000 / nyquist, 0.95)
                self.use_low_pass = True
            else:
                self.use_low_pass = False
                
        except Exception as e:
            print(f"⚠️ 频谱过滤器设置警告: {e}")
            self.use_high_pass = False
            self.use_low_pass = False
    
    def process(self, audio_data):
        """🎯 温和处理音频数据，避免爆炸音效"""
        if not self.is_calibrated or len(audio_data) == 0:
            return audio_data
        
        try:
            self.processed_frames += 1
            original_audio = audio_data.copy()
            
            # 1. 🔍 信号强度检测（安全检查）
            signal_power = np.sqrt(np.mean(audio_data ** 2))
            signal_peak = np.max(np.abs(audio_data))
            
            # 2. 🚨 防爆炸音效保护
            if signal_peak > 0.8 or signal_power > 0.3:
                # 强信号：最小化处理，防止失真
                gentle_factor = max(0.8, 1.0 - (signal_peak - 0.8) * 2)
                return audio_data * gentle_factor
            
            # 3. 🔇 智能噪音门（温和阈值）
            if signal_power < self.noise_gate_threshold:
                # 弱信号：温和衰减，不完全静音
                return audio_data * 0.3
            
            # 4. 🎵 音质优先的温和降噪
            if len(audio_data) >= 256:  # 降低最小处理长度
                # 使用温和的频域处理
                filtered_audio = self._gentle_spectral_reduction(audio_data)
            else:
                # 短音频：仅应用轻微时域衰减
                filtered_audio = audio_data * 0.9
            
            # 5. 🎭 人声信号保护（优先级最高）
            speech_detected = self._detect_speech_signal(audio_data, signal_power)
            if speech_detected:
                # 人声信号：大幅保留原始音频
                preserved_audio = original_audio * 0.8 + filtered_audio * 0.2
            else:
                # 非人声：正常降噪处理
                preserved_audio = original_audio * 0.5 + filtered_audio * 0.5
            
            # 6. 🛡️ 最终安全检查
            final_audio = self._safety_limiter(preserved_audio, original_audio)
            
            # 7. 📊 统计更新
            self._update_statistics(original_audio, final_audio)
            
            return final_audio
            
        except Exception as e:
            print(f"⚠️ 温和降噪处理错误: {e}")
            # 错误保护：返回轻微衰减的原始音频
            return audio_data * 0.9
    
    def _detect_speech_signal(self, audio_data, signal_power):
        """检测是否为人声信号"""
        try:
            # 基于功率的基础检测
            if signal_power < self.noise_gate_threshold * 2:
                return False
            
            # 频域特征检测
            if len(audio_data) >= 256:
                fft = np.fft.fft(audio_data, n=512)
                freqs = np.fft.fftfreq(512, 1/self.sample_rate)
                magnitude = np.abs(fft)
                
                # 检查人声频率范围内的能量
                speech_mask = (freqs >= self.speech_freq_range[0]) & (freqs <= self.speech_freq_range[1])
                speech_energy = np.sum(magnitude[speech_mask])
                total_energy = np.sum(magnitude)
                
                if total_energy > 0:
                    speech_ratio = speech_energy / total_energy
                    return speech_ratio > 0.3  # 30%以上的能量在人声频率范围内
            
            return signal_power > self.noise_gate_threshold * 3
            
        except Exception as e:
            print(f"⚠️ 人声检测错误: {e}")
            return signal_power > self.noise_gate_threshold * 2
    
    def _gentle_spectral_reduction(self, audio_data):
        """🎵 温和的频谱降噪处理（防止爆炸音效）"""
        try:
            # 使用更短的FFT以减少处理强度
            fft_size = min(512, len(audio_data))
            
            # 轻微的窗函数处理
            if len(audio_data) >= fft_size:
                windowed = audio_data[:fft_size] * np.hanning(fft_size)
            else:
                windowed = audio_data * np.hanning(len(audio_data))
                fft_size = len(audio_data)
            
            # FFT变换
            fft_data = np.fft.fft(windowed, n=fft_size)
            freqs = np.fft.fftfreq(fft_size, 1/self.sample_rate)
            magnitude = np.abs(fft_data)
            phase = np.angle(fft_data)
            
            # 温和的噪音抑制掩码
            gentle_mask = self._create_gentle_suppression_mask(freqs, magnitude)
            
            # 应用温和抑制
            suppressed_magnitude = magnitude * gentle_mask
            
            # 重构信号
            suppressed_fft = suppressed_magnitude * np.exp(1j * phase)
            suppressed_audio = np.fft.ifft(suppressed_fft).real
            
            # 返回原始长度，混合处理结果
            if len(suppressed_audio) >= len(audio_data):
                result = suppressed_audio[:len(audio_data)]
            else:
                result = audio_data.copy()
                result[:len(suppressed_audio)] = suppressed_audio
            
            # 与原始信号混合，确保不会产生爆炸音效
            return audio_data * 0.7 + result * 0.3
            
        except Exception as e:
            print(f"⚠️ 温和频谱处理错误: {e}")
            return audio_data * 0.95  # 错误时仅轻微衰减
    
    def _create_gentle_suppression_mask(self, freqs, magnitude):
        """创建温和的噪音抑制掩码"""
        mask = np.ones_like(magnitude)
        
        try:
            # 基于校准的噪音档案，但使用温和的抑制
            if self.noise_profile:
                dominant_freqs = self.noise_profile.get('dominant_frequencies', [])
                
                for noise_freq_info in dominant_freqs[:3]:  # 只处理前3个最强噪音频率
                    freq = noise_freq_info['frequency']
                    strength = noise_freq_info['relative_strength']
                    
                    # 在噪音频率附近应用温和抑制
                    freq_mask = np.abs(freqs - freq) < 100  # 100Hz窗口
                    suppression_factor = max(0.7, 1.0 - strength * 0.3)  # 最多30%抑制
                    mask[freq_mask] *= suppression_factor
            
            # 保护人声频率范围
            speech_mask = (np.abs(freqs) >= 85) & (np.abs(freqs) <= 3400)
            mask[speech_mask] = np.maximum(mask[speech_mask], 0.8)  # 人声频率最少保留80%
            
            return mask
            
        except Exception as e:
            print(f"⚠️ 温和掩码创建错误: {e}")
            return np.ones_like(magnitude) * 0.95  # 错误时轻微全频衰减
    
    def _safety_limiter(self, processed_audio, original_audio):
        """🛡️ 安全限制器（防止音频失真和爆炸音效）"""
        try:
            # 检查处理后的音频是否安全
            processed_peak = np.max(np.abs(processed_audio))
            original_peak = np.max(np.abs(original_audio))
            
            # 如果处理后峰值过高，进行保护性混合
            if processed_peak > original_peak * 2.0:
                # 处理后音频异常放大，大幅保留原始音频
                safety_mix = original_audio * 0.9 + processed_audio * 0.1
                print("🚨 检测到音频放大异常，应用安全保护")
                return safety_mix
            
            # 如果处理后音频过小，避免过度衰减
            if processed_peak < original_peak * 0.1 and original_peak > 0.01:
                # 处理后音频过度衰减，增加原始音频比例
                recovery_mix = original_audio * 0.6 + processed_audio * 0.4
                print("🔍 检测到过度衰减，应用恢复保护")
                return recovery_mix
            
            # 正常情况：轻微混合确保音质
            return original_audio * 0.3 + processed_audio * 0.7
            
        except Exception as e:
            print(f"⚠️ 安全限制器错误: {e}")
            return original_audio * 0.8 + processed_audio * 0.2
    
    def _update_statistics(self, original_audio, final_audio):
        """更新处理统计信息"""
        try:
            original_rms = np.sqrt(np.mean(original_audio ** 2))
            final_rms = np.sqrt(np.mean(final_audio ** 2))
            
            if original_rms > 0:
                reduction_ratio = 1.0 - (final_rms / original_rms)
                self.noise_reduction_stats['total_reduction'] += reduction_ratio
                self.noise_reduction_stats['preservation_ratio'] = final_rms / original_rms
            
            # 计算质量得分（简单的SNR估计）
            noise_estimate = max(original_rms - final_rms, 0.001)
            quality_score = 20 * np.log10(final_rms / noise_estimate) if noise_estimate > 0 else 50
            self.noise_reduction_stats['quality_score'] = quality_score
            
        except Exception as e:
            print(f"⚠️ 统计更新错误: {e}")
    
    def get_stats(self):
        """获取处理统计信息"""
        return {
            'processed_frames': self.processed_frames,
            'average_reduction': self.noise_reduction_stats['total_reduction'] / max(self.processed_frames, 1),
            'preservation_ratio': self.noise_reduction_stats['preservation_ratio'],
            'quality_score': self.noise_reduction_stats['quality_score'],
            'is_calibrated': self.is_calibrated
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.processed_frames = 0
        self.noise_reduction_stats = {
            'total_reduction': 0,
            'preservation_ratio': 0,
            'quality_score': 0
        }
