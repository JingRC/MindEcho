"""
增强的YIN音高检测算法
专门针对环境噪音和音调突变问题进行优化
"""

import numpy as np
import scipy.signal as signal
from collections import deque
import warnings
warnings.filterwarnings("ignore")

class EnhancedYIN:
    """增强的YIN音高检测算法"""
    
    def __init__(self, sr=44100, frame_size=1024):
        self.sr = sr
        self.frame_size = frame_size
        self.hop_size = 256  # 高时间分辨率
        self.threshold = 0.25  # 大幅提高阈值以适应轻微人声 (0.08→0.25)
        
        # 音高历史跟踪
        self.pitch_history = deque(maxlen=10)
        self.confidence_history = deque(maxlen=10)
        
        # 响度感知降噪 - 核心改进v3（极致敏感）
        self.noise_floor = 0.00005  # 极低噪音底限 (0.0001→0.00005)
        self.signal_threshold = 0.0008  # 极低信号阈值 (0.0015→0.0008)
        
        # 响度差异检测参数 - 极强化版
        self.environment_noise_level = 0.0003  # 进一步降低环境噪音基准
        self.voice_loudness_boost = 8.0  # 再次提高近场人声响度提升系数 (6.0→8.0)
        self.min_snr_db = 1  # 大幅降低最小信噪比要求 (3→1dB)
        
        # 轻微人声特殊处理 - 更强化
        self.quiet_voice_threshold = 0.010  # 提高轻微人声阈值范围
        self.quiet_voice_boost = 15.0       # 大幅提高轻微人声特殊增强 (10.0→15.0)
        
        print("🎯 增强YIN算法初始化（响度感知降噪）")
        print(f"  采样率: {sr} Hz")
        print(f"  帧大小: {frame_size} 样本")
        print(f"  跳跃长度: {self.hop_size} 样本")
        print(f"  检测阈值: {self.threshold}")
        print(f"  信号阈值: {self.signal_threshold} (超低阈值)")
        print(f"  噪音底限: {self.noise_floor}")
        print(f"  响度提升: {self.voice_loudness_boost}x")
        print(f"  最小信噪比: {self.min_snr_db}dB")
    
    def detect(self, audio):
        """音高检测主函数"""
        try:
            # 检查信号强度
            if not self._is_signal_present(audio):
                return 0, 0  # 信号太弱，可能是环境噪音
            
            # 加汉宁窗减少频谱泄漏
            window = np.hanning(len(audio))
            windowed = audio * window
            
            # 改进的CMNDF计算
            diff = self._cmndf(windowed)
            
            # 动态阈值局部最小值搜索
            valleys = self._find_valleys(diff)
            
            if len(valleys) == 0:
                return 0, 0
            
            # 谐波验证（防止八度错误）
            pitch, confidence = self._harmonic_validation(windowed, valleys)
            
            # 音高稳定性检查
            validated_pitch = self._stability_check(pitch, confidence)
            
            # 调试输出：更频繁地显示检测结果
            if hasattr(self, '_debug_counter'):
                self._debug_counter += 1
                # 每30帧输出一次（约每0.5秒）
                if self._debug_counter % 30 == 0:
                    signal_energy = np.sum(audio**2) / len(audio)
                    if validated_pitch > 0:
                        print(f"🎵 YIN检测成功: {validated_pitch:.1f}Hz (置信度: {confidence:.2f}, 能量: {signal_energy:.4f})")
                    elif pitch > 0:
                        print(f"🚫 YIN检测被过滤: {pitch:.1f}Hz → 0Hz (置信度: {confidence:.2f}, 能量: {signal_energy:.4f})")
                    else:
                        print(f"⭕ YIN无检测: 能量: {signal_energy:.4f}")
            else:
                self._debug_counter = 1
                print("🎯 增强YIN算法开始调试模式")
            
            return validated_pitch, confidence
            
        except Exception as e:
            print(f"❌ 增强YIN检测错误: {e}")
            return 0, 0
    
    def _is_signal_present(self, audio):
        """检测是否存在有效信号（响度感知降噪版本）"""
        # 计算信号能量
        signal_energy = np.sum(audio**2) / len(audio)
        
        # 响度感知检测 - 核心改进
        loudness_factor = self._calculate_loudness_factor(audio)
        adjusted_energy = signal_energy * loudness_factor
        
        # 计算零交叉率
        zero_crossings = np.sum(np.diff(np.sign(audio)) != 0)
        zcr = zero_crossings / len(audio)
        
        # 计算频谱集中度
        fft_data = np.abs(np.fft.rfft(audio))
        spectral_centroid = np.sum(fft_data * np.arange(len(fft_data))) / (np.sum(fft_data) + 1e-10)
        
        # 近场人声特征检测
        voice_frequency_energy = self._detect_voice_frequencies(fft_data)

        # 综合判断 - 大幅放宽条件（轻微人声优化）
        energy_ok = adjusted_energy > (self.signal_threshold * 0.9)  # 再放宽10%
        zcr_ok = 0.001 < zcr < 0.95  # 上限略放宽
        spectral_ok = spectral_centroid < len(fft_data) * 0.97  # 略放宽
        voice_ok = voice_frequency_energy > 0.008  # 再降阈值

        # 响度差异判断 - 新增
        snr_db = self._calculate_snr_db(signal_energy)
        snr_ok = snr_db > self.min_snr_db or adjusted_energy > self.signal_threshold * 2

        # 通过任意两个条件即可
        conditions = [energy_ok, zcr_ok, spectral_ok, voice_ok, snr_ok]
        passed_conditions = sum(conditions)

        # 添加详细调试输出
        if not (passed_conditions >= 2):
            if hasattr(self, '_signal_debug_counter'):
                self._signal_debug_counter += 1
                if self._signal_debug_counter % 50 == 0:  # 每50帧输出一次
                    print(f"🔍 信号检测详情: 能量={signal_energy:.6f}→{adjusted_energy:.6f}({energy_ok}), "
                          f"ZCR={zcr:.3f}({zcr_ok}), 频谱={spectral_centroid:.1f}({spectral_ok}), "
                          f"人声={voice_frequency_energy:.2f}({voice_ok}), SNR={snr_db:.1f}dB({snr_ok}), "
                          f"通过={passed_conditions}/5")
            else:
                self._signal_debug_counter = 1
                print(f"🔍 开始响度感知信号检测: 阈值={self.signal_threshold}")

        return passed_conditions >= 2  # 5个条件中通过2个即可（保持）
    
    def _calculate_loudness_factor(self, audio):
        """计算响度增强因子（优化轻微人声检测）"""
        rms = np.sqrt(np.mean(audio**2))
        
        # 轻微人声特殊增强处理
        if rms <= self.quiet_voice_threshold:
            # 轻微人声使用特殊增强
            return self.quiet_voice_boost
        elif rms <= 0.02:  # 正常轻声
            return self.voice_loudness_boost
        elif rms <= 0.05:  # 中等音量
            return self.voice_loudness_boost * 0.8
        else:  # 较强信号
            return self.voice_loudness_boost * 0.6
    
    def _detect_voice_frequencies(self, fft_data):
        """检测人声关键频段能量（优化轻微人声）"""
        freq_per_bin = self.sr / (2 * len(fft_data))
        
        # 扩大人声频段检测范围
        voice_start_bin = int(60 / freq_per_bin)  # 降低下限 80→60Hz
        voice_end_bin = int(5000 / freq_per_bin)  # 提高上限 4000→5000Hz  
        voice_end_bin = min(voice_end_bin, len(fft_data) - 1)
        
        if voice_end_bin > voice_start_bin:
            voice_energy = np.sum(fft_data[voice_start_bin:voice_end_bin])
            total_energy = np.sum(fft_data) + 1e-12  # 进一步降低分母保护
            
            # 加权处理：轻微人声的相对能量更容易通过
            voice_ratio = voice_energy / total_energy
            
            # 对极低能量信号进行增强
            if total_energy < 1e-6:  # 极低能量信号
                voice_ratio *= 5.0  # 5倍增强
            elif total_energy < 1e-5:  # 低能量信号
                voice_ratio *= 3.0  # 3倍增强
                
            return voice_ratio
        else:
            return 0.0
    
    def _calculate_snr_db(self, signal_energy):
        """计算信噪比（简化版本）"""
        noise_energy = self.environment_noise_level
        if noise_energy > 0:
            snr_linear = signal_energy / noise_energy
            return 10 * np.log10(max(snr_linear, 1e-10))
        else:
            return 20.0  # 假设高信噪比
    
    def _cmndf(self, audio):
        """改进的累积平均标准化差值函数"""
        audio_length = len(audio)
        half_length = audio_length // 2
        
        # 计算差值函数
        diff = np.zeros(half_length)
        
        for tau in range(1, half_length):
            for i in range(half_length):
                diff[tau] += (audio[i] - audio[i + tau])**2
        
        # 累积平均标准化
        cmndf = np.zeros(half_length)
        cmndf[0] = 1
        
        for tau in range(1, half_length):
            cmndf[tau] = diff[tau] / (np.sum(diff[1:tau+1]) / tau + 1e-10)
        
        return cmndf
    
    def _find_valleys(self, diff):
        """动态阈值局部最小值搜索"""
        valleys = []
        
        # 寻找可能的周期
        min_period = int(self.sr / 2000)  # 最高2000Hz (支持女高音、乐器高音)
        max_period = int(self.sr / 60)    # 最低60Hz (支持低音)
        
        if max_period >= len(diff):
            max_period = len(diff) - 1
        
        # 在有效范围内寻找谷值
        for tau in range(min_period, min(max_period, len(diff))):
            if (tau > 0 and tau < len(diff) - 1 and 
                diff[tau] < diff[tau-1] and diff[tau] < diff[tau+1] and
                diff[tau] < self.threshold):
                
                valleys.append((tau, diff[tau]))
        
        # 按置信度排序
        valleys.sort(key=lambda x: x[1])
        
        return [tau for tau, _ in valleys[:5]]  # 返回前5个候选
    
    def _harmonic_validation(self, windowed, candidates):
        """谐波验证（防止八度错误，增强弱基频场景如头声）

        策略：
        - 使用谐波支持评分 S(f)=∑ w_k * |X(k·f)|，w_k=1/k，弱化对基频幅度的依赖；
        - 对每个候选频率 f 同时评估 2f（纠正 “被降一倍” 的八度错误），择优；
        - 引入简化倒谱峰辅助，仅用于确认是否更倾向 2f；
        - 置信度基于谐波支持相对频谱总能量归一化。
        """
        if len(candidates) == 0:
            return 0, 0
        
        # FFT频谱分析
        spectrum = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(len(windowed), 1/self.sr)
        nyquist = self.sr / 2.0

        # 局部能量获取（±bins 范围求和）
        def local_energy_at(f, bins=2):
            if f <= 0 or f >= nyquist:
                return 0.0
            idx = int(np.round(f * len(freqs) / nyquist))
            idx = max(0, min(idx, len(spectrum)-1))
            lo = max(0, idx - bins)
            hi = min(len(spectrum)-1, idx + bins)
            return float(np.sum(spectrum[lo:hi+1]))

        # 谐波支持评分（弱化基频幅度依赖）
        def harmonic_support(f, max_harm=8, bins=2):
            if f <= 0:
                return 0.0, 0.0, 0.0  # score, E1, E2
            kmax = int(min(max_harm, np.floor(nyquist / max(f, 1e-6))))
            if kmax < 1:
                return 0.0, 0.0, 0.0
            score = 0.0
            e1 = local_energy_at(f, bins)
            e2 = local_energy_at(2*f, bins) if 2*f < nyquist else 0.0
            for k in range(1, kmax+1):
                ek = local_energy_at(k*f, bins)
                score += ek / k
            return score, e1, e2

        # 简化倒谱峰（用于判断是否倾向 2f）
        def cepstrum_f0_hint():
            try:
                spec = np.abs(np.fft.rfft(windowed)) + 1e-12
                log_spec = np.log(spec)
                ceps = np.fft.irfft(log_spec)
                # 将倒谱搜索范围限制到可行基音周期
                min_T = int(self.sr / 2000)  # 对应最高 2kHz
                max_T = int(self.sr / 60)    # 对应最低 60Hz
                max_T = min(max_T, len(ceps)-1)
                if max_T <= min_T+2:
                    return 0.0
                q = np.argmax(ceps[min_T:max_T]) + min_T
                f0 = self.sr / max(q, 1)
                return f0 if 60 <= f0 <= 2000 else 0.0
            except Exception:
                return 0.0
        
        best_pitch = 0
        best_confidence = 0.0

        f0_hint = cepstrum_f0_hint()
        
        for tau in candidates:
            frequency = self.sr / tau
            
            # 扩展频率范围，通过音质特征区分真实音高和噪音
            if not (60 <= frequency <= 2000):  # 支持更宽的音域范围
                continue
            
            # 计算候选 f 与 2f 的谐波支持
            score_f, e1_f, e2_f = harmonic_support(frequency, max_harm=8, bins=2)
            score_2f, e1_2f, e2_2f = (0.0, 0.0, 0.0)
            if 2*frequency <= 2000 and 2*frequency < nyquist:
                score_2f, e1_2f, e2_2f = harmonic_support(2*frequency, max_harm=6, bins=2)

            # 偶次谐波主导且 2f 支持明显更强 → 倾向纠正为 2f
            prefer_2f = False
            if score_2f > 0 and (score_2f >= score_f * 1.10):
                # 二倍频支持提升达到10%，或二次谐波远强于基频
                if e2_f > 0 and (e2_f >= e1_f * 1.4):
                    prefer_2f = True
            # 倒谱提示靠近 2f（在容差内）
            if f0_hint > 0 and abs(f0_hint - 2*frequency) < max(8.0, 0.03 * f0_hint):
                prefer_2f = True

            chosen_f = 2*frequency if prefer_2f else frequency
            chosen_score = score_2f if prefer_2f else score_f

            # 置信度：谐波支持相对频谱能量的归一化（裁剪到[0,1]）
            total_spec = float(np.sum(spectrum) + 1e-12)
            norm_conf = min(chosen_score / (total_spec * 0.25), 1.0)  # 分母放大以避免过饱和

            # 高频弱基频场景（>500Hz）给予小幅提升
            if chosen_f > 500:
                norm_conf = min(norm_conf * 1.15, 1.0)

            if norm_conf > best_confidence:
                best_confidence = norm_conf
                best_pitch = chosen_f
        
        # 标准化置信度
        if best_confidence > 0:
            return best_pitch, float(best_confidence)
        return 0, 0.0
    
    def _stability_check(self, pitch, confidence):
        """音高稳定性检查，智能区分环境噪音和真实高音"""
        if pitch == 0 or confidence < 0.1:  # 进一步降低最低置信度要求
            return 0
        
        # 添加到历史记录
        self.pitch_history.append(pitch)
        self.confidence_history.append(confidence)
        
        # 如果历史记录不足，根据置信度决定
        if len(self.pitch_history) < 2:  # 减少需要的历史记录
            # 对高置信度的音高更宽容，即使是高频
            if confidence > 0.4:  # 降低高置信度阈值
                return pitch
            elif confidence > 0.2:  # 降低中等置信度阈值
                return pitch if self._has_harmonic_structure(pitch) else 0
            else:
                return 0
        
        # 计算历史音高统计
        recent_pitches = [p for p in list(self.pitch_history)[-3:] if p > 0]  # 减少历史窗口
        
        if len(recent_pitches) < 1:  # 只需要1个历史点
            return pitch
        
        pitch_mean = np.mean(recent_pitches)
        pitch_std = np.std(recent_pitches) if len(recent_pitches) > 1 else 20
        
        # 检测异常跳跃 - 根据频率范围调整容忍度
        pitch_deviation = abs(pitch - pitch_mean)
        
        # 频率自适应阈值：高频音域允许更大的变化
        if pitch > 400:  # 高频段（包括D5及以上）
            # 高频段：女高音、乐器高音等自然变化较大
            base_threshold = 120  # 更宽松的基础阈值
            stability_factor = 3.0  # 更宽松的稳定性因子
        elif pitch > 200:  # 中频段
            base_threshold = 80
            stability_factor = 2.5
        else:  # 低频段
            base_threshold = 50
            stability_factor = 2.0
        
        # 自适应阈值：根据历史稳定性和频率段调整
        if pitch_std < 20:  # 历史很稳定
            deviation_threshold = max(base_threshold, pitch_std * stability_factor)
        else:  # 历史有波动
            deviation_threshold = max(base_threshold * 0.6, pitch_std * (stability_factor - 0.5))
        
        # 环境噪音突变检测 - 更智能的判断
        if pitch_deviation > deviation_threshold:
            # 检查是否是短暂噪音突变
            confidence_mean = np.mean(list(self.confidence_history)[-2:])  # 减少历史窗口
            
            # 区分环境噪音和真实音高跳跃 - 放宽判断条件
            is_likely_noise = (
                confidence < 0.2 or  # 降低置信度阈值
                confidence < confidence_mean * 0.4 or  # 更宽松的置信度比较
                (not self._has_harmonic_structure(pitch) and confidence < 0.5)  # 缺乏谐波结构且置信度不高
            )
            
            if is_likely_noise:
                if pitch_deviation > deviation_threshold * 1.5:  # 只有非常异常的才过滤
                    print(f"🚫 过滤环境噪音突变: {pitch:.1f}Hz (偏差: {pitch_deviation:.1f}Hz, 置信度: {confidence:.2f})")
                    return 0
                else:
                    # 允许一定程度的变化
                    return pitch
            else:
                # 可能是真实的音高跳跃（如歌唱中的跳音）
                print(f"✅ 保留真实音高跳跃: {pitch:.1f}Hz (偏差: {pitch_deviation:.1f}Hz, 置信度: {confidence:.2f})")
                return pitch
        
        return pitch
    
    def _has_harmonic_structure(self, frequency):
        """检查频率是否具有谐波结构（简化版本）"""
        # 这里可以添加更复杂的谐波验证逻辑
        # 暂时返回 True，表示大多数检测到的频率都可能是真实的
        return True

class TransientDetector:
    """瞬态检测器 - 检测音频中的瞬态变化（极低敏感度，主要用于保护）"""
    
    def __init__(self, sr):
        self.sr = sr
        self.energy_history = deque(maxlen=5)
        self.detection_threshold = 5.0  # 大幅提高阈值，几乎不触发
        self.min_energy_threshold = 0.2  # 大幅提高最小能量阈值
    
    def detect(self, frame):
        """检测是否为极强瞬态帧（只检测非常明显的瞬态）"""
        # 计算短时能量变化率
        current_energy = np.sum(frame**2)
        
        if len(self.energy_history) == 0:
            self.energy_history.append(current_energy)
            return False
        
        mean_energy = np.mean(self.energy_history)
        delta = current_energy - mean_energy
        
        # 更新历史
        self.energy_history.append(current_energy)
        
        # 只检测极强瞬态 - 避免影响正常音高检测
        threshold = mean_energy * self.detection_threshold
        is_transient = delta > threshold and current_energy > self.min_energy_threshold
        
        if is_transient:
            print(f"🔍 检测到極強瞬态: 能量变化 {delta:.4f} (阈值: {threshold:.4f}) - 仅保护性使用")
            
        return is_transient

class StabilizedAudioProcessor:
    """稳定化音频处理器 - 集成增强YIN和瞬态检测"""
    
    def __init__(self, yin_detector_or_sr=44100):
        # 支持两种初始化方式：传入YIN检测器对象或采样率
        if isinstance(yin_detector_or_sr, EnhancedYIN):
            # 传入的是YIN检测器对象
            self.yin_detector = yin_detector_or_sr
            self.sample_rate = self.yin_detector.sr
        else:
            # 传入的是采样率
            self.sample_rate = yin_detector_or_sr
            self.yin_detector = EnhancedYIN(sr=self.sample_rate)
        
        self.transient_detector = TransientDetector(self.sample_rate)
        
        # 连续性跟踪
        self.last_stable_pitch = 0
        self.stable_count = 0
        self.min_stable_frames = 1  # 减少到只需要1帧连续确认
        
        print("🎵 稳定化音频处理器初始化完成")
    
    def process_with_stability(self, audio_data):
        """处理音频数据，返回稳定的音高检测结果"""
        try:
            # 检测瞬态 - 但不要让瞬态检测阻止音高检测
            is_transient = self.transient_detector.detect(audio_data)
            
            # 即使是瞬态帧也要进行音高检测，因为歌声开始时常常是瞬态
            # 只有在瞬态且置信度很低时才使用上一个音高
            
            # 使用增强YIN检测
            pitch, confidence = self.yin_detector.detect(audio_data)
            
            # 如果是瞬态且检测失败，才使用保持策略
            if is_transient and pitch == 0 and self.last_stable_pitch > 0:
                # 瞬态帧且检测失败：保持上一个稳定音高，但降低置信度
                return self.last_stable_pitch, 0.3
            
            # 放宽稳定性验证，特别是对高频音高
            if pitch > 0 and confidence > 0.1:  # 进一步降低置信度要求
                # 对高频音高采用更宽松的连续性检查
                if pitch > 400:  # 高频段
                    continuity_threshold = 150  # 更宽松的连续性阈值
                    required_frames = 1         # 只需要1帧确认
                elif pitch > 200:  # 中频段
                    continuity_threshold = 100
                    required_frames = 1
                else:
                    continuity_threshold = 50   # 原有阈值
                    required_frames = 1         # 统一减少到1帧
                
                if abs(pitch - self.last_stable_pitch) < continuity_threshold or self.last_stable_pitch == 0:
                    self.stable_count += 1
                else:
                    self.stable_count = 1
                
                # 检查是否达到稳定要求
                if self.stable_count >= required_frames:
                    self.last_stable_pitch = pitch
                    return pitch, confidence
                else:
                    # 对于高置信度的检测，即使还在确认中也返回结果
                    if confidence > 0.5:
                        self.last_stable_pitch = pitch  # 更新稳定音高
                        return pitch, confidence * 0.9
                    elif confidence > 0.3:
                        return pitch, confidence * 0.8
                    elif confidence > 0.15:  # 进一步降低阈值
                        return pitch, confidence * 0.7
                    else:
                        # 还在确认中，但置信度较低时返回0
                        return 0, 0
            else:
                # 检测失败，重置计数
                self.stable_count = 0
                return 0, 0
                
        except Exception as e:
            print(f"❌ 稳定化处理错误: {e}")
            return 0, 0

# 测试函数
def test_enhanced_yin():
    """测试增强YIN算法"""
    print("🧪 测试增强YIN算法")
    
    processor = StabilizedAudioProcessor()
    
    # 测试场景1: 稳定150Hz信号
    print("\n📊 测试1: 稳定150Hz信号")
    t = np.linspace(0, 0.5, 22050)
    stable_signal = 0.5 * np.sin(2 * np.pi * 150 * t)
    
    for i in range(0, len(stable_signal), 1024):
        chunk = stable_signal[i:i+1024]
        if len(chunk) == 1024:
            pitch, conf = processor.process_with_stability(chunk)
            if pitch > 0:
                print(f"  检测: {pitch:.1f}Hz (置信度: {conf:.2f})")
                break
    
    # 测试场景2: 环境噪音突变
    print("\n📊 测试2: 环境噪音突变 (150Hz + 587Hz噪音)")
    base_signal = 0.6 * np.sin(2 * np.pi * 150 * t)
    noise_burst = 0.8 * np.sin(2 * np.pi * 587 * t[:5000])  # 短暂高频噪音
    
    # 创建突变信号
    combined = base_signal.copy()
    combined[10000:15000] += noise_burst
    
    stable_detections = 0
    noise_filtered = 0
    
    for i in range(0, len(combined), 1024):
        chunk = combined[i:i+1024]
        if len(chunk) == 1024:
            pitch, conf = processor.process_with_stability(chunk)
            
            if 10240 <= i <= 15360:  # 噪音区域
                if pitch == 0 or abs(pitch - 150) < 50:
                    noise_filtered += 1
            else:  # 正常区域
                if 140 <= pitch <= 160:
                    stable_detections += 1
    
    print(f"  稳定检测: {stable_detections} 次")
    print(f"  噪音过滤: {noise_filtered} 次")
    
    return processor

if __name__ == "__main__":
    test_enhanced_yin()
