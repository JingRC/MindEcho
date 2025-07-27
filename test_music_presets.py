#!/usr/bin/env python3
"""
测试基于乐理的智能缩放预设系统
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_music_theory_presets():
    """测试乐理基础的缩放预设"""
    print("🎼 基于乐理的智能缩放预设系统")
    print("="*60)
    print()
    print("🎯 设计原理:")
    print("• 基于钢琴88键布局和乐理知识")
    print("• 避免标签重叠，提供清晰的视觉层次")
    print("• 不同缩放级别显示不同密度的音符标签")
    print("• 智能过滤算法确保最佳可读性")
    print()
    
    print("🎹 5档智能缩放预设:")
    print()
    
    presets = [
        {
            "level": "0.5x",
            "name": "中央聚焦",
            "description": "仅显示中央C附近3个八度(C3-C5)",
            "display": "C3, C4, C5",
            "usage": "极端缩放时的核心区域，最简洁视图"
        },
        {
            "level": "0.8x", 
            "name": "基础八度框架",
            "description": "仅显示C0-C8每个八度的主音",
            "display": "C0, C1, C2, C3, C4, C5, C6, C7, C8",
            "usage": "最简化的参考框架，建立基础音高概念"
        },
        {
            "level": "1.5x",
            "name": "中音区聚焦", 
            "description": "突出显示C3-C6核心演奏区",
            "display": "C3-C6所有白键 + 其他八度主音",
            "usage": "突出常用演奏区域，适合日常练习分析"
        },
        {
            "level": "2.5x",
            "name": "八度主音显示",
            "description": "显示C0-C8每个八度主音及关键半音", 
            "display": "所有主音 + 核心区域白键",
            "usage": "保持整体结构清晰，显示重要音程关系"
        },
        {
            "level": "5.0x",
            "name": "全音区显示",
            "description": "显示所有88键(C0-C8)及中间半音",
            "display": "完整十二平均律所有音符",
            "usage": "适合需要查看全部细节的专业分析"
        }
    ]
    
    for preset in presets:
        print(f"🎵 {preset['level']} - {preset['name']}")
        print(f"   📝 说明: {preset['description']}")
        print(f"   🎹 显示: {preset['display']}")
        print(f"   💡 用途: {preset['usage']}")
        print()
    
    print("🧠 智能过滤算法:")
    print("✅ 主音识别: 自动识别C、D、E、F、G、A、B等白键")
    print("✅ 八度框架: 基于八度主音(C0-C8)建立结构")
    print("✅ 核心区域: 突出C3-C6常用演奏范围")
    print("✅ 渐进显示: 缩放级别越高，显示音符越多")
    print("✅ 避免重叠: 智能过滤确保标签不会密集重叠")
    print()
    
    print("🎼 音乐理论支持:")
    print("• 钢琴标准88键布局 (C0-C8)")
    print("• 十二平均律音程关系")
    print("• 白键黑键层次结构")
    print("• 演奏频率统计优化")
    print("• 视觉认知负荷控制")
    print()
    
    print("🚀 技术实现:")
    print("• should_show_note_label() 智能过滤算法")
    print("• 基于 octave 和 semitone 的音符分类")
    print("• 核心区域 (C3-C6) 特殊处理")
    print("• 主音 (semitone=0) 优先显示")
    print("• 白键 (semitone in [0,2,4,5,7,9,11]) 分层显示")
    print()

if __name__ == "__main__":
    test_music_theory_presets()
    
    # 询问是否启动实际测试
    choice = input("是否启动 MindEcho 测试新的乐理缩放预设? (y/n): ").lower()
    if choice == 'y':
        try:
            from src.gui.integrated_recording_interface import main as integrated_main
            print("\n🚀 启动 MindEcho 增强版...")
            print()
            print("测试重点:")
            print("• 点击不同缩放预设，观察音符标签密度变化")
            print("• 验证标签不会重叠，保持清晰可读")
            print("• 确认乐理逻辑正确（主音、白键、八度等）")
            print("• 测试各缩放级别的视觉效果和实用性")
            print()
            print("预设测试顺序:")
            print("1. 0.5x 中央聚焦 - 最简洁视图")
            print("2. 0.8x 基础八度框架 - 主音框架")
            print("3. 1.5x 中音区聚焦 - 核心演奏区")
            print("4. 2.5x 八度主音显示 - 结构清晰")
            print("5. 5.0x 全音区显示 - 完整细节")
            print()
            integrated_main()
        except Exception as e:
            print(f"❌ 启动失败: {e}")
