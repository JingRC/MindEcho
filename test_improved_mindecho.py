#!/usr/bin/env python3
"""
测试改进后的MindEcho降噪和音高检测系统
验证是否能有效解决D5等高频噪声误检测问题
"""

import numpy as np
import time
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_improved_mindecho_system():
    """测试改进后的MindEcho系统"""
    print("🎵 测试改进后的MindEcho降噪和音高检测系统")
    print("="*60)
    
    try:
        # 导入改进的音频处理器
        from improved_audio_processor import ImprovedAudioProcessor
        processor = ImprovedAudioProcessor()
        
        # 导入降噪处理器
        from src.audio_processing.noise_reduction import NoiseReductionProcessor
        noise_processor = NoiseReductionProcessor()
        noise_processor.set_noise_reduction_mode("基础频域降噪")
        
        print("✅ 所有处理器初始化完成\n")
        
        # 测试场景1: 正常人声信号
        print("🎤 测试场景1: 正常人声信号 (150Hz基音)")
        test_normal_voice(processor)
        
        # 测试场景2: 带有D5噪声的信号
        print("\n🔊 测试场景2: 带有D5高频噪声的信号 (150Hz + 587Hz噪声)")
        test_with_d5_noise(processor)
        
        # 测试场景3: 纯高频噪声
        print("\n⚡ 测试场景3: 纯高频噪声信号 (587Hz)")
        test_pure_d5_noise(processor)
        
        # 测试场景4: 快速频率跳跃
        print("\n🏃 测试场景4: 快速频率跳跃 (150Hz → 587Hz → 150Hz)")
        test_frequency_jumping(processor)
        
        print("\n" + "="*60)
        print("✅ 测试完成！改进的系统应该能有效过滤高频噪声误检测")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def test_normal_voice(processor):
    """测试正常人声信号"""
    # 生成150Hz基音（接近D3）
    duration = 0.5
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # 基音 + 谐波 + 轻微噪声
    fundamental = 0.8 * np.sin(2 * np.pi * 150 * t)
    harmonic2 = 0.3 * np.sin(2 * np.pi * 300 * t)
    harmonic3 = 0.1 * np.sin(2 * np.pi * 450 * t)
    noise = 0.1 * np.random.normal(0, 1, len(t))
    
    signal = fundamental + harmonic2 + harmonic3 + noise
    
    # 分段测试
    chunk_size = 2048
    detected_frequencies = []
    
    for i in range(0, len(signal) - chunk_size, chunk_size // 2):
        chunk = signal[i:i + chunk_size]
        freq, processed = processor.process_audio_with_improved_detection(chunk)
        if freq > 0:
            detected_frequencies.append(freq)
    
    if detected_frequencies:
        avg_freq = np.mean(detected_frequencies)
        std_freq = np.std(detected_frequencies)
        print(f"  检测结果: {avg_freq:.1f}±{std_freq:.1f} Hz ({len(detected_frequencies)}/{len(range(0, len(signal) - chunk_size, chunk_size // 2))} 帧)")
        print(f"  误差: {abs(avg_freq - 150):.1f} Hz")
    else:
        print("  检测结果: 无有效音高检测")

def test_with_d5_noise(processor):
    """测试带有D5噪声的信号"""
    duration = 0.5
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # 150Hz基音 + D5噪声(587Hz) + 随机噪声
    fundamental = 0.7 * np.sin(2 * np.pi * 150 * t)
    d5_noise = 0.4 * np.sin(2 * np.pi * 587 * t)  # D5噪声
    random_noise = 0.3 * np.random.normal(0, 1, len(t))
    
    signal = fundamental + d5_noise + random_noise
    
    # 分段测试
    chunk_size = 2048
    detected_frequencies = []
    high_freq_detections = 0
    
    for i in range(0, len(signal) - chunk_size, chunk_size // 2):
        chunk = signal[i:i + chunk_size]
        freq, processed = processor.process_audio_with_improved_detection(chunk)
        if freq > 0:
            detected_frequencies.append(freq)
            if freq > 500:  # 统计高频误检测
                high_freq_detections += 1
    
    if detected_frequencies:
        avg_freq = np.mean(detected_frequencies)
        std_freq = np.std(detected_frequencies)
        print(f"  检测结果: {avg_freq:.1f}±{std_freq:.1f} Hz ({len(detected_frequencies)} 帧)")
        print(f"  高频误检测: {high_freq_detections} 次")
        print(f"  基音误差: {abs(avg_freq - 150):.1f} Hz")
        
        if high_freq_detections == 0:
            print("  ✅ 成功过滤D5噪声！")
        else:
            print("  ⚠️  仍有高频误检测")
    else:
        print("  检测结果: 无有效音高检测")

def test_pure_d5_noise(processor):
    """测试纯D5噪声"""
    duration = 0.3
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # 纯D5信号(587Hz) + 噪声
    d5_signal = 0.8 * np.sin(2 * np.pi * 587 * t)
    noise = 0.2 * np.random.normal(0, 1, len(t))
    
    signal = d5_signal + noise
    
    # 分段测试
    chunk_size = 2048
    detected_frequencies = []
    
    for i in range(0, len(signal) - chunk_size, chunk_size // 2):
        chunk = signal[i:i + chunk_size]
        freq, processed = processor.process_audio_with_improved_detection(chunk)
        if freq > 0:
            detected_frequencies.append(freq)
    
    print(f"  D5噪声检测次数: {len(detected_frequencies)}")
    
    if len(detected_frequencies) == 0:
        print("  ✅ 成功过滤纯D5噪声信号！")
    else:
        avg_freq = np.mean(detected_frequencies)
        print(f"  ⚠️  仍检测到频率: {avg_freq:.1f} Hz")

def test_frequency_jumping(processor):
    """测试快速频率跳跃"""
    sample_rate = 44100
    chunk_size = 2048
    
    # 创建快速跳跃信号：150Hz → 587Hz → 150Hz
    segments = []
    
    # 150Hz段
    t1 = np.linspace(0, 0.2, int(sample_rate * 0.2))
    seg1 = 0.8 * np.sin(2 * np.pi * 150 * t1)
    segments.append(seg1)
    
    # 587Hz段（应该被过滤）
    t2 = np.linspace(0, 0.1, int(sample_rate * 0.1))
    seg2 = 0.8 * np.sin(2 * np.pi * 587 * t2)
    segments.append(seg2)
    
    # 150Hz段
    t3 = np.linspace(0, 0.2, int(sample_rate * 0.2))
    seg3 = 0.8 * np.sin(2 * np.pi * 150 * t3)
    segments.append(seg3)
    
    signal = np.concatenate(segments)
    
    # 分段测试
    detected_frequencies = []
    timestamps = []
    
    for i in range(0, len(signal) - chunk_size, chunk_size // 2):
        chunk = signal[i:i + chunk_size]
        freq, processed = processor.process_audio_with_improved_detection(chunk)
        timestamp = i / sample_rate
        
        if freq > 0:
            detected_frequencies.append(freq)
            timestamps.append(timestamp)
            
            # 分析检测结果
            if timestamp < 0.2:
                expected = "150Hz"
            elif 0.2 <= timestamp < 0.3:
                expected = "587Hz(应过滤)"
            else:
                expected = "150Hz"
                
            print(f"    时间{timestamp:.2f}s: {freq:.1f}Hz (期望: {expected})")
    
    # 统计结果
    if detected_frequencies:
        high_freq_count = sum(1 for f in detected_frequencies if f > 500)
        print(f"  总检测次数: {len(detected_frequencies)}")
        print(f"  高频检测次数: {high_freq_count}")
        
        if high_freq_count == 0:
            print("  ✅ 成功过滤跳跃中的高频噪声！")
        else:
            print("  ⚠️  仍有高频跳跃检测")

if __name__ == "__main__":
    test_improved_mindecho_system()
