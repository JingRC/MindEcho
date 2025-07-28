#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试响度感知音高检测修复
"""

import sys
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_loudness_aware_detection():
    """测试响度感知检测"""
    print("🎵 测试响度感知音高检测修复")
    print("=" * 50)
    
    try:
        from enhanced_yin_detector import StabilizedAudioProcessor
        
        # 创建处理器
        processor = StabilizedAudioProcessor(44100)
        
        # 生成测试信号
        sample_rate = 44100
        duration = 0.02  # 20ms帧
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 更全面的测试场景
        test_scenarios = [
            ("环境噪音", 0.001, 0),        # 不应检测
            ("轻微人声", 0.003, 220),      # 应该检测（新增）
            ("耳语级别", 0.008, 300),      # 应该检测（新增）
            ("轻声哼唱", 0.015, 220),      # 应该检测
            ("正常对话", 0.030, 330),      # 应该检测（新增）
            ("正常唱歌", 0.050, 330),      # 应该检测
            ("大声唱歌", 0.100, 440),      # 应该检测
            ("女高音", 0.080, 800),        # 应该检测
            ("乐器声", 0.060, 523),        # 应该检测（新增）
        ]
        
        print("测试场景（响度感知版本）：")
        print("-" * 50)
        
        success_count = 0
        total_count = len(test_scenarios)
        
        for scenario_name, target_rms, target_freq in test_scenarios:
            if target_freq > 0:
                # 生成带少量噪音的正弦波
                signal = np.sin(2 * np.pi * target_freq * t) 
                noise = np.random.normal(0, 0.001, len(signal))
                audio_data = signal + noise
                
                # 调整到目标RMS
                current_rms = np.sqrt(np.mean(audio_data ** 2))
                if current_rms > 0:
                    audio_data = audio_data * (target_rms / current_rms)
            else:
                # 生成噪音
                audio_data = np.random.normal(0, target_rms, int(sample_rate * duration))
            
            # 检测音高
            detected_freq, confidence = processor.process_with_stability(audio_data)
            actual_rms = np.sqrt(np.mean(audio_data ** 2))
            
            # 判断结果
            if target_freq > 0:
                # 应该检测到音高
                success = detected_freq > 0
                status = "✅ 正确检测" if success else "❌ 检测失败"
                freq_error = abs(detected_freq - target_freq) if detected_freq > 0 else "N/A"
                if success:
                    success_count += 1
            else:
                # 不应该检测到音高  
                success = detected_freq == 0
                status = "✅ 正确过滤" if success else "❌ 误检测"
                freq_error = "N/A"
                if success:
                    success_count += 1
            
            print(f"{scenario_name:8s} | RMS:{actual_rms:.4f} | 目标:{target_freq:3.0f}Hz | 检测:{detected_freq:3.0f}Hz | 置信:{confidence:.2f} | {status}")
        
        success_rate = (success_count / total_count) * 100
        
        print("\n" + "=" * 50)
        print(f"🎯 响度感知检测修复结果: {success_count}/{total_count} ({success_rate:.1f}%)")
        print()
        print("核心改进：")
        print("• 信号阈值: 0.005 → 0.003 (更敏感)")
        print("• 响度增强: 近场人声3x响度提升")
        print("• 多条件检测: 5个条件中通过2个即可")
        print("• 人声频段保护: 80Hz-4000Hz重点检测")
        print("• SNR自适应: 最小6dB信噪比要求")
        print("• 瞬态保护: 极低敏感度，避免误触发")
        
        if success_rate >= 80:
            print("\n✅ 修复效果良好！应該可以检测到您的唱歌了。")
            return True
        else:
            print(f"\n⚠️ 修复效果一般，成功率{success_rate:.1f}%，可能需要进一步调整。")
            return False
        
    except Exception as e:
        print(f"❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_loudness_aware_detection()
    
    if success:
        print(f"\n🚀 现在启动 MindEcho 测试实际效果:")
        print("python run_enhanced.py")
        print("选择选项 1，启用'基础频域降噪'")
        print("尝试不同音量的唱歌：轻声哼唱 → 正常音量 → 大声唱歌")
    
    input("\n按回车键退出...")
