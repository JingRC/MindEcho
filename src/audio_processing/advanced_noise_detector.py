"""
🎵 MindEcho 增强型音频处理器 - 基于专业级电流音检测

参考专利CN114640926A和Venus EQ调音技术，实现多维度电流音检测
完美保护人声技巧（大声唱歌、气泡音、颤音等）
"""

import numpy as np
from scipy import signal
from collections import deque
import time

class AdvancedElectricNoiseDetector:
    """增强型电流音检测器 - 多维度特征分析"""
    
    def __init__(self, sample_rate=48000):
        self.sr = sample_rate
        self.frame_size = 64  # 超低延迟
        
        # 🎵 动态阈值配置（基于HECATE G4 Pro参数）
        self.thresholds = {
            'high_freq_energy': 0.012,     # 8-16kHz能量阈值（进一步降低）
            'peak_to_average': 10.0,       # 峰值/平均比（大幅提高）
            'duration_threshold': 0.8,     # 最小持续时间（增加稳定性）
            'spectral_centroid': 15000,    # 频谱质心阈值（提高）
            'harmonic_ratio': 0.25,        # 谐波/噪声比（降低）
            'rms_protection': 0.001        # RMS保护阈值（提高）
        }
        
        # 🎵 人声保护参数
        self.vocal_protection = {
            'rms_min': 0.001,              # 最小RMS保护阈值（提高）
            'vocal_range': (80, 1000),     # 人声基频范围
            'bubble_detection': True,      # 气泡音特征识别
            'vibrato_tolerance': 0.3,      # 颤音容忍度（提高）
            'loud_singing_threshold': 0.02 # 大声唱歌阈值
        }
        
        # 状态追踪
        self.history_buffer = deque(maxlen=30)
        self.detection_history = deque(maxlen=20)
        self.last_features = None
        self.consecutive_detections = 0
        
    def detect(self, audio_frame):
        """增强型电流音检测 - 多维度分析"""
        if len(audio_frame) < 32:
            return False
            
        # 1. 基础信号检查
        rms = np.sqrt(np.mean(audio_frame ** 2))
        
        # 🎵 强化人声保护：有实际音量的信号直接通过
        if rms >= self.vocal_protection['rms_min']:
            self.consecutive_detections = 0
            return False
            
        # 2. 频谱分析
        try:
            spectrum = np.fft.rfft(audio_frame)
            power_spectrum = np.abs(spectrum) ** 2
            freqs = np.fft.rfftfreq(len(audio_frame), 1/self.sr)
        except:
            return False
            
        # 3. 多维特征提取
        features = self._extract_features(power_spectrum, freqs, rms)
        if features is None:
            return False
            
        # 4. 归零曲线分析
        zeroed_analysis = self._analyze_with_zeroed_curve(power_spectrum)
        
        # 5. 人声技巧检测
        is_vocal_technique = self._detect_vocal_techniques(audio_frame, features)
        if is_vocal_technique:
            self.consecutive_detections = 0
            return False
            
        # 6. 动态阈值调整
        self._update_thresholds_for_vocal_style(features)
        
        # 7. 综合判定
        detection_result = self._make_detection_decision(features, zeroed_analysis)
        
        # 8. 更新历史
        self.last_features = features
        self.history_buffer.append(features)
        
        return detection_result
        
    def _extract_features(self, power_spectrum, freqs, rms):
        """提取多维特征"""
        total_power = np.sum(power_spectrum)
        if total_power < 1e-10:
            return None
            
        try:
            # 高频能量分析（8-16kHz） - 针对电流音主要频段
            high_freq_mask = (freqs >= 8000) & (freqs <= 16000)
            if np.sum(high_freq_mask) == 0:
                high_freq_energy = 0
            else:
                high_freq_energy = np.sum(power_spectrum[high_freq_mask]) / total_power
            
            # 峰值/平均比 - 电流音特征
            peak_power = np.max(power_spectrum)
            avg_power = np.mean(power_spectrum[power_spectrum > 0])
            peak_to_avg = peak_power / (avg_power + 1e-10)
            
            # 频谱质心 - 频率分布中心
            spectral_centroid = np.sum(freqs * power_spectrum) / total_power
            
            # 谐波结构分析 - 区分人声和噪声
            harmonic_ratio = self._calculate_harmonic_ratio(power_spectrum, freqs)
            
            # 频谱平坦度 - 噪声特征
            geometric_mean = np.exp(np.mean(np.log(power_spectrum + 1e-10)))
            arithmetic_mean = np.mean(power_spectrum)
            spectral_flatness = geometric_mean / (arithmetic_mean + 1e-10)
            
            return {
                'high_freq_energy': high_freq_energy,
                'peak_to_average': peak_to_avg,
                'spectral_centroid': spectral_centroid,
                'harmonic_ratio': harmonic_ratio,
                'spectral_flatness': spectral_flatness,
                'rms': rms,
                'total_power': total_power
            }
        except:
            return None
        
    def _analyze_with_zeroed_curve(self, spectrum):
        """基于归零曲线的精细分析（专利算法）"""
        try:
            # 计算基准值（去除异常点）
            sorted_amp = np.sort(spectrum)
            if len(sorted_amp) < 10:
                return {'over_threshold_count': 0, 'over_threshold_power': 0}
                
            trim_start = int(len(sorted_amp) * 0.1)
            trim_end = int(len(sorted_amp) * 0.9)
            trimmed = sorted_amp[trim_start:trim_end]
            
            if len(trimmed) == 0:
                return {'over_threshold_count': 0, 'over_threshold_power': 0}
                
            baseline = np.mean(trimmed)
            
            # 生成归零曲线
            zeroed_curve = spectrum - baseline
            
            # 噪声底线（更保守的计算）
            noise_floor = np.std(trimmed) * 3  # 提高到3倍标准差
            
            # 超阈值分析
            over_threshold = zeroed_curve > noise_floor
            count = np.sum(over_threshold)
            total_power = np.sum(zeroed_curve[over_threshold]**2) if count > 0 else 0
            
            return {
                'over_threshold_count': count,
                'over_threshold_power': total_power,
                'relative_count': count / len(spectrum) if len(spectrum) > 0 else 0
            }
        except:
            return {'over_threshold_count': 0, 'over_threshold_power': 0, 'relative_count': 0}
        
    def _detect_vocal_techniques(self, audio_frame, features):
        """检测人声技巧（气泡音、颤音、大声唱歌等）"""
        try:
            # 大声唱歌检测：高RMS + 丰富谐波结构
            if features['rms'] > self.vocal_protection['loud_singing_threshold']:
                if features['harmonic_ratio'] > 0.3:  # 有明显谐波结构
                    return True
                    
            # 气泡音检测：低频集中 + 特定RMS范围
            if (features['spectral_centroid'] < 1200 and 
                0.0005 < features['rms'] < 0.01):
                return True
                
            # 颤音检测：频谱质心的规律性变化
            if len(self.history_buffer) >= 8:
                recent_centroids = [h['spectral_centroid'] for h in self.history_buffer[-8:]]
                if len(recent_centroids) >= 6:
                    centroid_variation = np.std(recent_centroids) / (np.mean(recent_centroids) + 1)
                    if centroid_variation > self.vocal_protection['vibrato_tolerance']:
                        return True
                        
            # 假声/头声检测：高频集中但有谐波结构
            if (features['spectral_centroid'] > 3000 and 
                features['harmonic_ratio'] > 0.4):
                return True
                
            # 呼吸音/气声检测：高频但有音调特征
            if (features['spectral_flatness'] < 0.5 and  # 不是纯噪声
                features['high_freq_energy'] > 0.1 and
                features['rms'] > 0.0008):
                return True
                
            return False
        except:
            return False
        
    def _calculate_harmonic_ratio(self, power_spectrum, freqs):
        """计算谐波/噪声比 - 区分音调和噪声"""
        try:
            # 查找可能的基频（人声范围）
            vocal_mask = (freqs >= 80) & (freqs <= 1000)
            if np.sum(vocal_mask) == 0:
                return 0
                
            vocal_spectrum = power_spectrum[vocal_mask]
            if len(vocal_spectrum) == 0:
                return 0
                
            # 查找最强的低频成分作为基频候选
            peak_idx = np.argmax(vocal_spectrum)
            fundamental_freq = freqs[vocal_mask][peak_idx]
            
            if fundamental_freq < 80:
                return 0
                
            # 查找谐波能量
            harmonic_power = 0
            total_analyzed_power = 0
            
            for h in range(1, 6):  # 1-5次谐波
                harmonic_freq = fundamental_freq * h
                if harmonic_freq > self.sr / 2:
                    break
                    
                # 查找最接近的频率bin（允许一定偏差）
                freq_tolerance = fundamental_freq * 0.1  # 10%容忍度
                harmonic_mask = np.abs(freqs - harmonic_freq) <= freq_tolerance
                
                if np.sum(harmonic_mask) > 0:
                    harmonic_energy = np.sum(power_spectrum[harmonic_mask])
                    harmonic_power += harmonic_energy
                    total_analyzed_power += np.sum(power_spectrum)
                    
            if total_analyzed_power > 0:
                return harmonic_power / total_analyzed_power
            else:
                return 0
        except:
            return 0
        
    def _update_thresholds_for_vocal_style(self, features):
        """根据人声特征动态调整阈值"""
        try:
            # 重置阈值到基础值
            base_thresholds = {
                'high_freq_energy': 0.012,
                'peak_to_average': 10.0,
                'spectral_centroid': 15000,
                'harmonic_ratio': 0.25
            }
            
            # 强声压演唱时大幅放宽阈值
            if features['rms'] > 0.02:
                base_thresholds['high_freq_energy'] *= 3.0
                base_thresholds['peak_to_average'] *= 1.5
                
            # 中等音量时适度放宽
            elif features['rms'] > 0.005:
                base_thresholds['high_freq_energy'] *= 2.0
                
            # 气泡音/低频特征时调整
            if features['spectral_centroid'] < 1000:
                base_thresholds['peak_to_average'] *= 1.8
                base_thresholds['harmonic_ratio'] *= 0.7
                
            # 高频演唱时的保护
            if features['spectral_centroid'] > 2500:
                base_thresholds['high_freq_energy'] *= 2.5
                
            # 应用调整后的阈值
            for key, value in base_thresholds.items():
                if key in self.thresholds:
                    self.thresholds[key] = value
        except:
            pass
        
    def _make_detection_decision(self, features, zeroed_analysis):
        """综合判定决策 - 多条件严格检查"""
        try:
            # 🎵 严格的多条件检查
            condition1 = features['high_freq_energy'] > self.thresholds['high_freq_energy']
            condition2 = features['peak_to_average'] > self.thresholds['peak_to_average']
            condition3 = features['spectral_centroid'] > self.thresholds['spectral_centroid']
            condition4 = features['harmonic_ratio'] < self.thresholds['harmonic_ratio']
            condition5 = zeroed_analysis['relative_count'] > 0.4  # 40%以上频点异常
            condition6 = features['spectral_flatness'] > 0.7  # 接近白噪声特征
            
            # 计算检测分数
            conditions = [condition1, condition2, condition3, condition4, condition5, condition6]
            detection_score = sum(conditions)
            
            # 需要至少4个条件同时满足（严格要求）
            current_detection = detection_score >= 4
            
            # 记录检测历史
            self.detection_history.append(1 if current_detection else 0)
            
            # 持续性检查：需要连续检测才确认
            if current_detection:
                self.consecutive_detections += 1
            else:
                self.consecutive_detections = 0
                
            # 最终判定：需要连续多帧检测 + 最近历史中有足够检测
            recent_detections = sum(list(self.detection_history)[-8:])  # 最近8帧
            
            return (self.consecutive_detections >= 3 and recent_detections >= 5)
        except:
            return False


class PrecisionAudioProcessor:
    """精确音质处理器 - Venus EQ风格"""
    
    def __init__(self, sample_rate=48000):
        self.sr = sample_rate
        self.is_initialized = False
        
        # Venus EQ风格的频段处理
        self.eq_bands = [
            {'freq': 7500, 'q': 6.0, 'type': 'notch'},   # 电流音预防
            {'freq': 10000, 'q': 4.0, 'type': 'notch'},  # 电流音主频段
            {'freq': 13000, 'q': 3.0, 'type': 'notch'},  # 电流音扩展
            {'freq': 16000, 'q': 8.0, 'type': 'notch'}   # 超高频噪声
        ]
        
        self._init_filters()
        
    def _init_filters(self):
        """初始化精确滤波器组"""
        try:
            self.filters = []
            for band in self.eq_bands:
                # 设计精确的陷波滤波器
                freq_low = band['freq'] * 0.85
                freq_high = band['freq'] * 1.15
                
                # 确保频率在有效范围内
                freq_low = max(freq_low, 100)
                freq_high = min(freq_high, self.sr * 0.48)
                
                if freq_low < freq_high:
                    sos = signal.iirfilter(
                        2, [freq_low, freq_high], 
                        btype='bandstop', fs=self.sr, output='sos'
                    )
                    self.filters.append(sos)
                    
            self.is_initialized = True
        except Exception as e:
            print(f"⚠️ 滤波器初始化失败: {e}")
            self.filters = []
            self.is_initialized = False
            
    def process_electric_noise_suppression(self, audio):
        """精确电流音抑制 - 保持音质"""
        if not self.is_initialized or len(self.filters) == 0:
            return audio
            
        try:
            processed = audio.copy().astype(np.float64)
            
            # 保存原始特征
            original_rms = np.sqrt(np.mean(audio**2))
            if original_rms < 1e-8:
                return audio
                
            # 应用精确滤波
            for sos in self.filters:
                try:
                    processed = signal.sosfilt(sos, processed)
                except:
                    continue
                    
            # 恢复到原始数据类型
            processed = processed.astype(audio.dtype)
            
            # 保持原始动态范围（温和恢复）
            processed_rms = np.sqrt(np.mean(processed**2))
            if processed_rms > 1e-8:
                gain_compensation = (original_rms / processed_rms) * 0.92  # 轻微衰减
                processed *= gain_compensation
                
            return processed
        except Exception as e:
            # 如果处理失败，返回原始音频
            return audio
            
    def apply_vrms_limiting(self, audio, threshold=0.88):
        """VRMS风格动态限制 - 更宽容的阈值"""
        try:
            max_amp = np.max(np.abs(audio))
            
            if max_amp > threshold:
                # 软限制算法（更温和）
                compression_ratio = threshold / max_amp
                
                # 渐进压缩曲线
                if compression_ratio < 0.7:
                    # 强压缩时使用对数曲线
                    compression_curve = np.log(compression_ratio + 0.3) / np.log(1.3)
                else:
                    # 轻压缩时使用线性
                    compression_curve = compression_ratio
                    
                audio = audio * compression_curve
                
            return audio
        except:
            return audio


class AutoCalibrationSystem:
    """自动校准系统 - 环境自适应"""
    
    def __init__(self, detector, processor):
        self.detector = detector
        self.processor = processor
        self.calibration_data = {}
        self.is_calibrated = False
        
    def quick_calibration(self, sample_audio_frames):
        """快速校准 - 基于实际音频样本"""
        if len(sample_audio_frames) < 10:
            return False
            
        try:
            # 分析静音和有声段
            noise_frames = []
            signal_frames = []
            
            for frame in sample_audio_frames:
                rms = np.sqrt(np.mean(frame**2))
                if rms < 0.001:
                    noise_frames.append(frame)
                else:
                    signal_frames.append(frame)
                    
            # 基于噪声特征调整阈值
            if len(noise_frames) > 0:
                self._adjust_thresholds_from_noise(noise_frames)
                
            # 基于有声段特征保护人声
            if len(signal_frames) > 0:
                self._enhance_vocal_protection(signal_frames)
                
            self.is_calibrated = True
            print("✅ 快速自动校准完成")
            return True
        except Exception as e:
            print(f"❌ 自动校准失败: {e}")
            return False
            
    def _adjust_thresholds_from_noise(self, noise_frames):
        """基于噪声特征调整检测阈值"""
        try:
            combined_noise = np.concatenate(noise_frames)
            if len(combined_noise) < 32:
                return
                
            # 分析噪声频谱
            spectrum = np.fft.rfft(combined_noise)
            power_spectrum = np.abs(spectrum) ** 2
            freqs = np.fft.rfftfreq(len(combined_noise), 1/self.detector.sr)
            
            # 计算噪声基线
            high_freq_mask = (freqs >= 8000) & (freqs <= 16000)
            noise_energy = np.sum(power_spectrum[high_freq_mask]) / np.sum(power_spectrum)
            
            # 调整阈值（保守策略）
            safety_margin = 3.0
            self.detector.thresholds['high_freq_energy'] = max(
                noise_energy * safety_margin, 
                self.detector.thresholds['high_freq_energy']
            )
        except:
            pass
            
    def _enhance_vocal_protection(self, signal_frames):
        """增强人声保护参数"""
        try:
            # 分析人声特征
            rms_values = []
            centroids = []
            
            for frame in signal_frames:
                rms = np.sqrt(np.mean(frame**2))
                rms_values.append(rms)
                
                if len(frame) >= 32:
                    spectrum = np.fft.rfft(frame)
                    power_spectrum = np.abs(spectrum) ** 2
                    freqs = np.fft.rfftfreq(len(frame), 1/self.detector.sr)
                    
                    if np.sum(power_spectrum) > 0:
                        centroid = np.sum(freqs * power_spectrum) / np.sum(power_spectrum)
                        centroids.append(centroid)
                        
            # 调整保护参数
            if len(rms_values) > 0:
                max_rms = np.max(rms_values)
                # 确保保护阈值能覆盖用户的正常音量
                self.detector.vocal_protection['rms_min'] = min(
                    max_rms * 0.1, 
                    self.detector.vocal_protection['rms_min']
                )
                
            if len(centroids) > 0:
                # 基于用户频率范围调整
                freq_range = np.max(centroids) - np.min(centroids)
                if freq_range > 500:  # 频率变化较大，可能有颤音等技巧
                    self.detector.vocal_protection['vibrato_tolerance'] *= 1.5
        except:
            pass
