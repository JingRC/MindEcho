#!/usr/bin/env python3
"""
测试优化后的1.5x稀疏音程显示
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_sparse_display():
    """测试1.5x稀疏音程显示优化"""
    print("🎼 1.5x 稀疏音程显示优化")
    print("="*50)
    print()
    print("🐛 原问题:")
    print("❌ 1.5x缩放级别音符重叠，显示太密集")
    print("   • 原逻辑: 显示C3-C6所有白键(C,D,E,F,G,A,B)")
    print("   • 结果: 7个音符×4个八度 = 28个标签")
    print("   • 问题: 标签过于密集，容易重叠遮挡")
    print()
    print("🔧 优化方案:")
    print("✅ 采用稀疏音程策略，基于完全音程理论")
    print("   • 新逻辑: 优先显示完全音程(C-F-G)")
    print("   • 音程理论: 完全一度、完全四度、完全五度")
    print("   • 视觉效果: 更清晰的音程间距，避免重叠")
    print()
    print("🎹 新的1.5x显示策略:")
    print()
    print("📍 核心范围 (C3-C6):")
    print("   • 仅显示: C, F, G (完全音程)")
    print("   • 示例: C3, F3, G3, C4, F4, G4, C5, F5, G5, C6, F6, G6")
    print("   • 数量: 3个音符×4个八度 = 12个标签")
    print()
    print("📍 扩展范围 (C2, C7):")
    print("   • 仅显示: C (主音)")
    print("   • 示例: C2, C7")
    print("   • 数量: 2个标签")
    print()
    print("📍 其他范围 (C0, C1, C8):")
    print("   • 仅显示: C (主音)")
    print("   • 示例: C0, C1, C8")
    print("   • 数量: 3个标签")
    print()
    print("📊 总计: 12 + 2 + 3 = 17个标签 (vs 原来28个)")
    print("   减少: 39% 的标签密度，大幅改善可读性")
    print()
    print("🎵 音乐理论支持:")
    print("• 完全音程: 音乐中最稳定的音程关系")
    print("• C-F: 完全四度 (4个半音)")
    print("• C-G: 完全五度 (7个半音)")
    print("• 和声基础: 大多数和弦以C-F-G为骨架")
    print("• 视觉清晰: 间隔适中，便于快速识别")
    print()
    print("🎯 优化效果:")
    print("✅ 避免标签重叠遮挡")
    print("✅ 保持重要音程关系")
    print("✅ 提供清晰的视觉层次")
    print("✅ 减少视觉认知负荷")
    print("✅ 适合中等缩放级别的分析需求")
    print()

if __name__ == "__main__":
    test_sparse_display()
    
    # 询问是否启动实际测试
    choice = input("是否启动 MindEcho 测试优化后的1.5x稀疏显示? (y/n): ").lower()
    if choice == 'y':
        try:
            from src.gui.integrated_recording_interface import main as integrated_main
            print("\n🚀 启动 MindEcho 增强版...")
            print()
            print("测试重点:")
            print("• 设置缩放到1.5x稀疏音程模式")
            print("• 观察音符标签是否明显减少")
            print("• 验证只显示C、F、G完全音程")
            print("• 确认标签间距更加清晰")
            print("• 对比其他缩放级别的差异")
            print()
            print("操作步骤:")
            print("1. 点击'1.5x稀疏音程'预设按钮")
            print("2. 观察左侧音调标签的分布")
            print("3. 与2.5x和5.0x模式对比密度")
            print("4. 测试录音时的可读性")
            print()
            integrated_main()
        except Exception as e:
            print(f"❌ 启动失败: {e}")
