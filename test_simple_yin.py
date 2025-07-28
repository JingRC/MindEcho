#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的YIN敏感度测试
"""

import sys
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("🎵 测试增强YIN检测器修复")
print("=" * 40)

try:
    from enhanced_yin_detector import EnhancedYIN
    
    # 创建检测器
    yin = EnhancedYIN(sr=44100, frame_size=1024)
    
    # 生成220Hz的测试信号
    sample_rate = 44100
    duration = 0.1  # 100ms
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # 生成不同强度的220Hz信号
    base_signal = np.sin(2 * np.pi * 220 * t)
    
    test_levels = [0.01, 0.02, 0.05, 0.1]
    
    print("测试不同音量的220Hz信号：")
    for level in test_levels:
        signal = base_signal * level
        # 添加少量噪音
        signal += np.random.normal(0, 0.001, len(signal))
        
        freq, conf = yin.detect(signal[:1024])  # 使用1024样本
        rms = np.sqrt(np.mean(signal**2))
        
        status = "✅" if freq > 0 else "❌"
        print(f"  音量{level:4.2f} | RMS:{rms:.4f} | 检测:{freq:5.1f}Hz | 置信:{conf:.2f} | {status}")
    
    print("\n✅ 测试完成！现在启动MindEcho测试实际效果。")
    
except Exception as e:
    print(f"❌ 测试错误: {e}")

input("按回车键退出...")
