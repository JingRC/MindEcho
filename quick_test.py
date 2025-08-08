#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试简化的音高检测系统
"""

import numpy as np
import sys
import os

# 添加src路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def quick_pitch_test():
    """快速音高检测测试"""
    print("🚀 快速音高检测测试")
    print("=" * 40)
    
    try:
        from src.gui.integrated_recording_interface import IntegratedAudioProcessor
        
        processor = IntegratedAudioProcessor()
        processor.sample_rate = 44100
        
        # 生成更强的测试信号
        duration = 0.5  # 500ms
        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 测试不同频率
        test_frequencies = [220, 440, 880]  # A3, A4, A5
        
        for freq in test_frequencies:
            print(f"\n测试频率: {freq}Hz")
            
            # 生成纯净的正弦波测试信号
            test_signal = 0.5 * np.sin(2 * np.pi * freq * t)  # 较强的信号
            
            # 调用检测
            detected_freq = processor.detect_pitch_with_vibrato(test_signal)
            
            if detected_freq > 0:
                error = abs(detected_freq - freq)
                error_percent = (error / freq) * 100
                status = "✅ 成功" if error_percent < 5 else "⚠️ 误差大"
                print(f"   检测结果: {detected_freq:.1f}Hz")
                print(f"   误差: {error:.1f}Hz ({error_percent:.1f}%) {status}")
            else:
                print("   ❌ 检测失败")
        
        print("\n" + "=" * 40)
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    quick_pitch_test()
