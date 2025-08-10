# MindEcho统一音高检测系统 - 最终版本\n# 解决所有算法冲突问题\n\n
    def detect_pitch_with_vibrato(self, audio_data):
        """🎯 统一音高检测系统 - 解决所有算法冲突的唯一入口"""
        if not hasattr(self, '_unified_pitch_system'):
            self._unified_pitch_system = self._create_unified_pitch_system()
        return self._unified_pitch_system.detect_pitch(audio_data)
    
    def _create_unified_pitch_system(self):
        """创建统一音高检测系统实例"""
        import numpy as np
        import time
        
        class UnifiedPitchDetection:
            def __init__(self, sample_rate):
                self.sample_rate = sample_rate
                self.config = {
                    'frequency_range': (60, 1200),     # 🎯 统一频率范围：60-1200Hz
                    'min_rms_threshold': 0.0005,      # 🎯 统一RMS阈值
                    'min_data_length': 256,           # 🎯 适中数据长度（提高稳定性）
                    'detection_rate': 20               # 🎯 目标检测频率：20Hz
                }
                self.state = {
                    'counter': 0,
                    'last_detection_time': 0,
                    'pitch_history': [],
                    'last_frequency': 0,
                    'consecutive_detections': 0
                }
                print("🎯 统一音高检测系统启动 - 60-1200Hz范围，20Hz检测频率，解决算法冲突")
            
            def detect_pitch(self, audio_data):
                """主检测函数：集成频率控制、静音检测、连续性验证"""
                try:
                    self.state['counter'] += 1
                    current_time = time.time()
                    
                    # 🎯 智能频率控制：维持20Hz检测频率
                    target_interval = 1.0 / self.config['detection_rate']  # 50ms
                    time_since_last = current_time - self.state['last_detection_time']
                    if time_since_last < target_interval:
                        return 0  # 跳过此次检测
                    
                    self.state['last_detection_time'] = current_time
                    
                    # 🔥 输入验证和预处理
                    audio_data = np.array(audio_data, dtype=np.float64)
                    if len(audio_data) < self.config['min_data_length']:
                        return 0
                    
                    # 🔥 信号特征分析
                    rms = np.sqrt(np.mean(audio_data ** 2))
                    if rms < self.config['min_rms_threshold']:
                        return 0
                    
                    # 🎯 智能静音/换气检测
                    if self._is_silence_or_breathing(audio_data, rms):
                        return 0
                    
                    # 🔥 信号预处理
                    audio_data = audio_data - np.mean(audio_data)  # 去DC偏移
                    
                    # 🎯 核心音高检测：改进的自相关算法
                    raw_frequency = self._enhanced_autocorrelation(audio_data)
                    
                    # 🎯 频率范围验证
                    min_freq, max_freq = self.config['frequency_range']
                    if not (min_freq <= raw_frequency <= max_freq):
                        return 0
                    
                    # 🎯 智能连续性验证和平滑
                    final_frequency = self._apply_continuity_check(raw_frequency)
                    
                    # 🔥 调试输出（适度频率）
                    if self.state['counter'] % 40 == 0:  # 每2秒输出一次
                        smoothing_info = ""
                        if abs(raw_frequency - final_frequency) > 2:
                            smoothing_info = f" (平滑:{raw_frequency:.1f}→{final_frequency:.1f})"
                        print(f"🎵 统一检测: {final_frequency:.1f}Hz{smoothing_info}, RMS={rms:.6f}")
                    
                    return final_frequency
                
                except Exception as e:
                    if self.state['counter'] % 200 == 0:
                        print(f"❌ 统一检测错误: {e}")
                    return 0
            
            def _is_silence_or_breathing(self, audio_data, rms):
                """统一的静音/换气检测算法"""
                try:
                    # 极低音量直接判断为静音
                    if rms < 0.0001:
                        return True
                    
                    # 频域分析检测换气特征
                    if len(audio_data) >= 128:
                        fft_data = np.abs(np.fft.rfft(audio_data))
                        freqs = np.fft.rfftfreq(len(audio_data), 1/self.sample_rate)
                        
                        # 分析低频能量比例
                        low_freq_mask = freqs <= 80  # 80Hz以下为低频
                        total_energy = np.sum(fft_data)
                        
                        if total_energy > 0:
                            low_freq_ratio = np.sum(fft_data[low_freq_mask]) / total_energy
                            # 只有在极低频占绝对主导且能量很低时才认为是换气
                            if low_freq_ratio > 0.95 and rms < 0.001:
                                return True
                    
                    return False
                except Exception:
                    return rms < 0.0001
            
            def _enhanced_autocorrelation(self, audio_data):
                """增强的自相关音高检测算法"""
                try:
                    # 应用汉宁窗减少频谱泄漏
                    windowed = audio_data * np.hanning(len(audio_data))
                    
                    # 计算自相关
                    correlation = np.correlate(windowed, windowed, mode='full')
                    correlation = correlation[len(correlation)//2:]
                    
                    # 归一化处理
                    if correlation[0] > 0:
                        correlation = correlation / correlation[0]
                    else:
                        return 0
                    
                    # 计算搜索范围
                    min_freq, max_freq = self.config['frequency_range']
                    min_period = max(int(self.sample_rate / max_freq), 3)
                    max_period = min(int(self.sample_rate / min_freq), len(correlation) - 1)
                    
                    if max_period <= min_period:
                        return 0
                    
                    # 避免边界效应，增加安全边距
                    search_start = min_period + 5
                    search_end = max_period - 5
                    
                    if search_end <= search_start:
                        return 0
                    
                    search_corr = correlation[search_start:search_end]
                    if len(search_corr) == 0:
                        return 0
                    
                    # 寻找最强峰值
                    peak_idx = np.argmax(search_corr)
                    peak_value = search_corr[peak_idx]
                    actual_period = peak_idx + search_start
                    
                    # 置信度检查：峰值应该明显高于平均值
                    avg_correlation = np.mean(search_corr)
                    if peak_value < avg_correlation * 1.5:  # 峰值至少是平均值的1.5倍
                        return 0
                    
                    # 抛物线插值提高精度
                    if peak_idx > 0 and peak_idx < len(search_corr) - 1:
                        y1, y2, y3 = search_corr[peak_idx-1], search_corr[peak_idx], search_corr[peak_idx+1]
                        denominator = y1 - 2*y2 + y3
                        if abs(denominator) > 1e-10:  # 避免除零
                            x_offset = 0.5 * (y1 - y3) / denominator
                            interpolated_period = actual_period + x_offset
                        else:
                            interpolated_period = actual_period
                    else:
                        interpolated_period = actual_period
                    
                    # 计算最终频率
                    frequency = self.sample_rate / interpolated_period
                    return frequency
                    
                except Exception:
                    return 0
            
            def _apply_continuity_check(self, raw_frequency):
                """
                应用连续性检查和智能平滑：
                1. 防止不合理的八度跳跃
                2. 允许自然的音乐跳跃
                3. 保持微小的自然颤音
                """
                try:
                    # 添加到历史记录
                    self.state['pitch_history'].append({
                        'frequency': raw_frequency,
                        'timestamp': time.time()
                    })
                    
                    # 保持历史记录在合理范围（最近3秒）
                    cutoff_time = time.time() - 3.0
                    self.state['pitch_history'] = [
                        h for h in self.state['pitch_history'] 
                        if h['timestamp'] > cutoff_time
                    ]
                    
                    # 如果历史数据不足，直接返回原始频率
                    if len(self.state['pitch_history']) < 3:
                        self.state['last_frequency'] = raw_frequency
                        self.state['consecutive_detections'] = 1
                        return raw_frequency
                    
                    last_freq = self.state['last_frequency']
                    freq_diff = abs(raw_frequency - last_freq)
                    
                    # 情况1：小幅变化（< 25Hz），认为是自然颤音或微调
                    if freq_diff < 25:
                        self.state['last_frequency'] = raw_frequency
                        self.state['consecutive_detections'] += 1
                        return raw_frequency
                    
                    # 情况2：检查是否为合理的音程跳跃
                    if last_freq > 0:
                        ratio = raw_frequency / last_freq
                        semitones = 12 * np.log2(ratio) if ratio > 0 else 0
                        
                        # 常见音程（半音为单位），允许更大的误差范围
                        reasonable_intervals = [1, 2, 3, 4, 5, 7, 12, -1, -2, -3, -4, -5, -7, -12]
                        is_reasonable = any(abs(semitones - interval) < 1.0 for interval in reasonable_intervals)
                        
                        if is_reasonable:
                            # 合理的音程跳跃，接受
                            self.state['last_frequency'] = raw_frequency
                            self.state['consecutive_detections'] = 1
                            return raw_frequency
                    
                    # 情况3：检查连续性 - 如果是新的稳定频率
                    recent_frequencies = [h['frequency'] for h in self.state['pitch_history'][-5:]]
                    if len(recent_frequencies) >= 3:
                        recent_std = np.std(recent_frequencies)
                        recent_mean = np.mean(recent_frequencies)
                        
                        # 如果最近的频率都很接近原始频率，可能是新的稳定音高
                        if abs(raw_frequency - recent_mean) < 20 and recent_std < 15:
                            self.state['last_frequency'] = raw_frequency
                            self.state['consecutive_detections'] += 1
                            return raw_frequency
                    
                    # 情况4：异常跳跃，使用渐进平滑
                    if freq_diff > 80:
                        # 计算加权平均，给最近的稳定频率更高权重
                        if self.state['consecutive_detections'] > 3:
                            # 如果之前的频率很稳定，平滑更保守
                            smoothed = 0.2 * raw_frequency + 0.8 * last_freq
                        else:
                            # 如果之前频率不稳定，响应更积极
                            smoothed = 0.4 * raw_frequency + 0.6 * last_freq
                        
                        self.state['last_frequency'] = smoothed
                        self.state['consecutive_detections'] = 1
                        return smoothed
                    
                    # 情况5：中等程度变化，轻微平滑
                    alpha = 0.7  # 响应性参数
                    smoothed = alpha * raw_frequency + (1 - alpha) * last_freq
                    self.state['last_frequency'] = smoothed
                    self.state['consecutive_detections'] = 1
                    return smoothed
                    
                except Exception as e:
                    # 出错时返回原始频率
                    self.state['last_frequency'] = raw_frequency
                    return raw_frequency
        
        return UnifiedPitchDetection(self.sample_rate)
    
    # 🚫 建议移除的冲突函数列表：
    # def simple_pitch_detection(self, audio_data):
    # def _unified_pitch_detection(self, audio_data, rms):
    # def _apply_intelligent_smoothing(self, frequency, confidence):
    # def _validate_pitch_continuity(self, raw_frequency, controller):
    # def _is_breathing_or_silence(self, audio_data, rms): # 如果没有其他地方使用
