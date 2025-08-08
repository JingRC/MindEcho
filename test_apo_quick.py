#!/usr/bin/env python3
"""
APO多层音频监听快速测试脚本
基于HECATE G4 Pro驱动架构优化

测试重点：
1. 电流音检测准确性（阈值从0.1提升到2.0）
2. APO三层处理架构效果
3. 延迟性能测试
4. 音质提升验证
"""

import sys
import os
import time

# 添加源码路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def main():
    print("="*60)
    print("   MindEcho APO多层音频监听测试")
    print("   基于HECATE G4 Pro驱动架构")
    print("="*60)
    print()
    print("🎵 APO架构特性:")
    print("   ✅ EFX层: 音频明亮化 + 人声清晰化")
    print("   ✅ MFX层: 智能音量控制 + 动态低音增强")
    print("   ✅ SFX层: 噪音抑制 + 实时RAW模式")
    print()
    print("🔧 优化改进:")
    print("   • 电流音检测阈值: 0.1 → 2.0 (减少误判)")
    print("   • 多算法融合: 高频+频域+稳定性检测")
    print("   • VRMS限制器: 防止过载失真")
    print("   • 128样本块: 专业驱动配置")
    print("   • 手动控制: 可关闭电流音检测")
    print()
    print("🎧 测试指南:")
    print("   1. 启动后自动开启APO监听")
    print("   2. 观察电流音检测警告频率")
    print("   3. 在界面中可关闭'启用APO检测'")
    print("   4. 对比开启/关闭检测的音质差异")
    print()
    print("正在启动MindEcho APO测试...")
    print()
    
    try:
        # 导入主界面
        from gui.integrated_recording_interface import main as gui_main
        
        # 启动GUI
        gui_main()
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("请确保在正确的环境中运行此脚本")
    except Exception as e:
        print(f"❌ 启动错误: {e}")

if __name__ == "__main__":
    main()
