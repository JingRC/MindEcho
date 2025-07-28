#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接测试轻微人声检测修复
"""

import sys
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_quiet_voice_direct():
    """直接测试轻微人声检测"""
    print("🎵 直接测试轻微人声检测修复")
    print("=" * 50)
    
    try:
        from enhanced_yin_detector import EnhancedYIN
        
        # 创建检测器
        detector = EnhancedYIN(44100, 1024)
        
        # 生成更真实的测试信号
        sample_rate = 44100
        duration = 0.02  # 20ms帧
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 测试轻微人声的情况
        test_scenarios = [
            ("环境噪音", 0.0008, 0),       # 不应检测
            ("轻微人声A", 0.003, 220),      # 新修复目标
            ("轻微人声B", 0.005, 330),      # 新修复目标  
            ("轻微人声C", 0.008, 440),      # 新修复目标
            ("轻声哼唱", 0.015, 220),       # 应该检测
            ("正常音量", 0.050, 330),       # 应该检测
            ("大声音量", 0.100, 440),       # 应该检测
        ]
        
        print("直接YIN检测测试：")
        print("-" * 50)
        
        success_count = 0
        total_count = len(test_scenarios)
        
        for scenario_name, target_rms, target_freq in test_scenarios:
            if target_freq > 0:
                # 生成纯正弦波（高质量信号）
                signal = np.sin(2 * np.pi * target_freq * t)
                # 调整到目标RMS
                current_rms = np.sqrt(np.mean(signal ** 2))
                if current_rms > 0:
                    audio_data = signal * (target_rms / current_rms)
            else:
                # 生成白噪音
                audio_data = np.random.normal(0, target_rms, int(sample_rate * duration))
            
            # 直接调用YIN检测
            detected_freq, confidence = detector.detect(audio_data)
            actual_rms = np.sqrt(np.mean(audio_data ** 2))
            
            # 判断结果
            if target_freq > 0:
                success = detected_freq > 0
                status = "✅ 检测成功" if success else "❌ 检测失败"
                freq_error = abs(detected_freq - target_freq) if detected_freq > 0 else "N/A"
                if success:
                    success_count += 1
                    
                # 显示检测详情
                print(f"{scenario_name:10s} | RMS:{actual_rms:.4f} | 目标:{target_freq:3.0f}Hz | 检测:{detected_freq:3.0f}Hz | 置信:{confidence:.3f} | {status}")
                if success and isinstance(freq_error, (int, float)):
                    print(f"            频率误差: {freq_error:.1f}Hz")
            else:
                success = detected_freq == 0
                status = "✅ 正确过滤" if success else "❌ 误检测"
                if success:
                    success_count += 1
                print(f"{scenario_name:10s} | RMS:{actual_rms:.4f} | 目标:{target_freq:3.0f}Hz | 检测:{detected_freq:3.0f}Hz | 置信:{confidence:.3f} | {status}")
        
        success_rate = (success_count / total_count) * 100
        
        print("\n" + "=" * 50)
        print(f"🎯 直接检测结果: {success_count}/{total_count} ({success_rate:.1f}%)")
        
        # 如果轻微人声检测成功率还是不高，我们试试更激进的参数
        if success_rate < 70:
            print("\n⚠️ 轻微人声检测仍有问题，建议再次降低阈值")
            print("• 当前信号阈值:", detector.signal_threshold)
            print("• 建议信号阈值: 0.0008")
            print("• 当前轻微人声增强:", detector.quiet_voice_boost if hasattr(detector, 'quiet_voice_boost') else "未设置")
            print("• 建议轻微人声增强: 15.0")
        else:
            print(f"\n✅ 轻微人声检测修复成功！")
            
        return success_rate >= 70
        
    except Exception as e:
        print(f"❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_quiet_voice_direct()
    
    if success:
        print(f"\n🚀 现在可以启动 MindEcho:")
        print("python run_enhanced.py")
        print("轻微人声应该可以检测到了！")
    
    input("\n按回车键退出...")
