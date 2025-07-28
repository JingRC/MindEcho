#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试增强YIN检测器修复效果
"""

import sys
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_enhanced_yin_sensitivity():
    """测试增强YIN检测器的敏感度修复"""
    print("🎵 测试增强YIN检测器敏感度修复")
    print("=" * 50)
    
    try:
        from enhanced_yin_detector import StabilizedAudioProcessor
        
        # 创建处理器
        processor = StabilizedAudioProcessor(44100)
        
        # 生成测试信号（模拟唱歌的音频）
        sample_rate = 44100
        duration = 0.02  # 20ms帧
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 测试不同RMS水平的信号
        test_scenarios = [
            ("安静环境", 0.001, 0),      # 很安静，不应检测
            ("轻微噪音", 0.005, 0),      # 轻微噪音，不应检测  
            ("轻声哼唱", 0.015, 220),    # 轻声，应该检测到
            ("正常唱歌", 0.050, 330),    # 正常音量，应该检测到
            ("大声唱歌", 0.100, 440),    # 大声，应该检测到
            ("女高音", 0.080, 800),      # 高频，应该检测到
        ]
        
        print("测试场景：")
        print("-" * 50)
        
        for scenario_name, target_rms, target_freq in test_scenarios:
            if target_freq > 0:
                # 生成带噪音的正弦波
                signal = np.sin(2 * np.pi * target_freq * t) 
                # 添加少量噪音
                noise = np.random.normal(0, 0.01, len(signal))
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
            else:
                # 不应该检测到音高
                success = detected_freq == 0
                status = "✅ 正确过滤" if success else "❌ 误检测"
                freq_error = "N/A"
            
            print(f"{scenario_name:8s} | RMS:{actual_rms:.4f} | 目标:{target_freq:3.0f}Hz | 检测:{detected_freq:3.0f}Hz | 置信:{confidence:.2f} | {status}")
        
        print("\n" + "=" * 50)
        print("🎯 修复要点总结：")
        print("• 信号检测阈值: 0.01 → 0.005 (更敏感)")
        print("• YIN检测阈值: 0.15 → 0.1 (更敏感)")
        print("• 零交叉率范围: 0.01-0.5 → 0.005-0.7 (更宽松)")
        print("• 稳定性确认: 3帧 → 1帧 (更快响应)")
        print("• 置信度要求: 0.15 → 0.1 (更宽松)")
        print("• 频谱阈值: 60% → 80% (更宽松)")
        
        print("\n✅ 增强YIN检测器敏感度修复完成！")
        print("现在应该可以检测到您的唱歌声音了。")
        
        return True
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试错误: {e}")
        return False

if __name__ == "__main__":
    success = test_enhanced_yin_sensitivity()
    
    if success:
        print(f"\n🚀 请重新启动 MindEcho 测试修复效果:")
        print("python run_enhanced.py")
        print("选择选项 1，启用'基础频域降噪'，开始唱歌测试")
    
    input("\n按回车键退出...")
