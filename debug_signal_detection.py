#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试信号检测逻辑
"""

import sys
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def debug_signal_detection():
    """调试信号检测的每个步骤"""
    print("🔍 调试信号检测逻辑")
    print("=" * 50)
    
    try:
        from enhanced_yin_detector import EnhancedYIN
        
        # 创建检测器
        detector = EnhancedYIN(44100, 1024)
        
        # 生成一个轻微人声测试信号
        sample_rate = 44100
        duration = 0.02  # 20ms帧
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 测试220Hz轻微人声
        target_freq = 220
        target_rms = 0.005
        signal = np.sin(2 * np.pi * target_freq * t)
        current_rms = np.sqrt(np.mean(signal ** 2))
        audio_data = signal * (target_rms / current_rms)
        
        print(f"测试信号: {target_freq}Hz, RMS={target_rms}")
        print("-" * 50)
        
        # 调试信号检测过程
        signal_energy = np.sqrt(np.mean(audio_data**2))
        print(f"1. 信号能量: {signal_energy:.6f}")
        
        # 检查轻微人声特殊处理
        if signal_energy <= detector.quiet_voice_threshold:
            adjusted_energy = signal_energy * detector.quiet_voice_boost
            print(f"2. 轻微人声增强: {signal_energy:.6f} × {detector.quiet_voice_boost} = {adjusted_energy:.6f}")
        else:
            loudness_factor = detector._calculate_loudness_factor(audio_data)
            adjusted_energy = signal_energy * loudness_factor
            print(f"2. 响度增强: {signal_energy:.6f} × {loudness_factor} = {adjusted_energy:.6f}")
        
        # 能量条件检查
        energy_ok = adjusted_energy > detector.signal_threshold
        print(f"3. 能量检查: {adjusted_energy:.6f} > {detector.signal_threshold} = {energy_ok}")
        
        # 过零率检查
        zero_crossings = np.diff(np.signbit(audio_data)).sum()
        zcr = zero_crossings / len(audio_data)
        zcr_ok = 0.001 < zcr < 0.9
        print(f"4. 过零率检查: {zcr:.4f} 在 (0.001, 0.9) = {zcr_ok}")
        
        # 频谱检查
        fft_data = np.abs(np.fft.rfft(audio_data))
        spectral_centroid = np.sum(fft_data * np.arange(len(fft_data))) / (np.sum(fft_data) + 1e-10)
        spectral_ok = spectral_centroid < len(fft_data) * 0.95
        print(f"5. 频谱检查: {spectral_centroid:.1f} < {len(fft_data) * 0.95:.1f} = {spectral_ok}")
        
        # 人声频段检测
        voice_frequency_energy = detector._detect_voice_frequencies(fft_data)
        voice_ok = voice_frequency_energy > 0.01
        print(f"6. 人声频段: {voice_frequency_energy:.4f} > 0.01 = {voice_ok}")
        
        # SNR检查
        snr_db = detector._calculate_snr_db(signal_energy)
        snr_ok = snr_db > detector.min_snr_db or adjusted_energy > detector.signal_threshold * 1.5
        print(f"7. SNR检查: {snr_db:.1f}dB > {detector.min_snr_db}dB 或 {adjusted_energy:.6f} > {detector.signal_threshold * 1.5:.6f} = {snr_ok}")
        
        # 汇总条件
        conditions = [energy_ok, zcr_ok, spectral_ok, voice_ok, snr_ok]
        passed_conditions = sum(conditions)
        print(f"\n条件汇总:")
        print(f"  能量: {energy_ok}")
        print(f"  零交叉: {zcr_ok}")
        print(f"  频谱: {spectral_ok}")  
        print(f"  人声: {voice_ok}")
        print(f"  SNR: {snr_ok}")
        print(f"  通过: {passed_conditions}/5")
        
        # 轻微人声优先通道检查
        if signal_energy <= detector.quiet_voice_threshold:
            quiet_conditions = [energy_ok, voice_ok, spectral_ok]
            quiet_passed = sum(quiet_conditions)
            print(f"\n轻微人声优先通道:")
            print(f"  能量: {energy_ok}, 人声: {voice_ok}, 频谱: {spectral_ok}")
            print(f"  通过: {quiet_passed}/3 (需要>=1)")
            should_detect_quiet = quiet_passed >= 1
        else:
            should_detect_quiet = False
            
        should_detect = should_detect_quiet or passed_conditions >= 2
        print(f"\n最终判断: {'应该检测' if should_detect else '不应检测'}")
        
        # 实际运行检测
        actual_result = detector._is_signal_present(audio_data)
        print(f"实际结果: {'检测到信号' if actual_result else '未检测到信号'}")
        
        if should_detect != actual_result:
            print("⚠️ 逻辑不一致！")
        else:
            print("✅ 逻辑一致")
            
        return should_detect and actual_result
        
    except Exception as e:
        print(f"❌ 调试错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    debug_signal_detection()
    input("\n按回车键退出...")
