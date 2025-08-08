#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人声音高检测测试 - 验证修复效果
测试不同频率的正弦波，确保只检测正常人声范围
"""

import numpy as np
import sys
import os

# 添加src路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def test_voice_frequency_range():
    """测试人声频率范围检测"""
    print("🎤 人声音高检测范围测试")
    print("=" * 50)
    
    try:
        from src.gui.integrated_recording_interface import IntegratedAudioProcessor
        
        processor = IntegratedAudioProcessor()
        processor.sample_rate = 44100
        
        # 生成测试信号参数
        duration = 0.5  # 500ms
        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 测试频率范围：从极低到极高
        test_frequencies = [
            # 超低频（应该被过滤）
            50, 60, 70,
            # 正常人声范围（应该被检测）
            80, 100, 150, 200, 250, 300, 400, 500, 600, 700, 800,
            # 超高频（应该被过滤）
            900, 1000, 1200, 1500, 2000, 2500, 3000
        ]
        
        print("频率范围测试结果:")
        print("期望范围: 80-800Hz (正常人声)")
        print("-" * 50)
        
        detected_count = 0
        total_count = len(test_frequencies)
        
        for freq in test_frequencies:
            # 生成纯净的正弦波测试信号
            test_signal = 0.3 * np.sin(2 * np.pi * freq * t)  # 适中的信号强度
            
            # 调用检测
            detected_freq = processor.detect_pitch_with_vibrato(test_signal)
            
            # 判断是否在期望范围内
            in_expected_range = 80 <= freq <= 800
            was_detected = detected_freq > 0
            
            if was_detected:
                detected_count += 1
                error = abs(detected_freq - freq) if detected_freq > 0 else 0
                error_percent = (error / freq) * 100 if freq > 0 else 0
                
                if in_expected_range:
                    status = "✅ 正确检测"
                    if error_percent > 10:
                        status = "⚠️ 检测但误差大"
                else:
                    status = "❌ 不应检测"
                
                print(f"{freq:4d}Hz → {detected_freq:6.1f}Hz (误差:{error_percent:4.1f}%) {status}")
            else:
                if in_expected_range:
                    status = "❌ 应检测但未检测"
                else:
                    status = "✅ 正确过滤"
                
                print(f"{freq:4d}Hz → 未检测                            {status}")
        
        print("-" * 50)
        print(f"检测统计: {detected_count}/{total_count} 个频率被检测")
        
        # 分析结果
        expected_detections = [f for f in test_frequencies if 80 <= f <= 800]
        print(f"期望检测: {len(expected_detections)} 个频率 (80-800Hz)")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_noise_resistance():
    """测试抗噪声能力"""
    print("\n🔇 抗噪声测试")
    print("=" * 50)
    
    try:
        from src.gui.integrated_recording_interface import IntegratedAudioProcessor
        
        processor = IntegratedAudioProcessor()
        processor.sample_rate = 44100
        
        duration = 0.5
        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 测试不同强度的噪声
        test_freq = 220  # A3，正常人声频率
        noise_levels = [0.0, 0.1, 0.2, 0.3, 0.5, 0.8, 1.0]
        
        print(f"测试频率: {test_freq}Hz (A3)")
        print("噪声级别测试:")
        
        for noise_level in noise_levels:
            # 生成信号 + 噪声
            signal = 0.3 * np.sin(2 * np.pi * test_freq * t)
            noise = noise_level * np.random.normal(0, 0.1, len(signal))
            noisy_signal = signal + noise
            
            # 检测
            detected_freq = processor.detect_pitch_with_vibrato(noisy_signal)
            
            if detected_freq > 0:
                error = abs(detected_freq - test_freq)
                error_percent = (error / test_freq) * 100
                status = "✅ 检测成功" if error_percent < 5 else "⚠️ 误差较大"
                print(f"噪声级别 {noise_level:.1f} → {detected_freq:6.1f}Hz (误差:{error_percent:4.1f}%) {status}")
            else:
                status = "❌ 检测失败" if noise_level < 0.5 else "⚠️ 噪声过强"
                print(f"噪声级别 {noise_level:.1f} → 未检测                           {status}")
        
        return True
        
    except Exception as e:
        print(f"❌ 抗噪声测试失败: {e}")
        return False

if __name__ == "__main__":
    print("🎯 MindEcho 人声检测算法验证")
    print("测试目标: 确保只检测正常人声范围，避免C7等极高频率")
    print("=" * 60)
    
    # 运行测试
    test1_success = test_voice_frequency_range()
    test2_success = test_noise_resistance()
    
    print("\n" + "=" * 60)
    if test1_success and test2_success:
        print("✅ 所有测试完成！请检查上述结果是否符合预期。")
        print("期望结果:")
        print("  - 80-800Hz频率应该被正确检测")
        print("  - 超出此范围的频率应该被过滤")
        print("  - 噪声环境下仍能稳定检测")
    else:
        print("❌ 部分测试失败，请检查算法实现")
