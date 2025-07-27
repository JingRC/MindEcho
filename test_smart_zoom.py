#!/usr/bin/env python3
"""
测试智能缩放功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def main():
    print("🎵 启动智能缩放功能测试版...")
    print()
    print("✨ 新增智能缩放功能:")
    print("  🔍 缩放滑块: 0.1x到5.0x精确缩放控制")
    print("  🧠 智能标注: 根据缩放级别自动调整音名标注密度")
    print("  📊 三级显示: 稀疏/中等/密集三种标注模式自动切换")
    print("  🎛️ 手动模式: 可关闭智能标注，总是显示详细信息")
    print()
    print("🎯 智能标注策略:")
    print("  • 缩放0.1x-0.5x (大范围): 只显示八度线和C音")
    print("  • 缩放0.5x-1.5x (中范围): 显示白键音符(C,D,E,F,G,A,B)")
    print("  • 缩放1.5x-5.0x (小范围): 显示所有半音")
    print("  • 超精细缩放: 根据缩放级别进一步智能过滤")
    print()
    print("🎛️ 操作控制:")
    print("  • 缩放滑块: 拖拽调整缩放级别")
    print("  • 智能标注按钮: 切换智能/手动标注模式")
    print("  • 重置视图: 一键回到1.0x缩放的默认状态")
    print("  • 状态栏: 显示当前缩放级别、显示范围、标注模式")
    print()
    print("🎨 视觉优化:")
    print("  • 网格线粗细根据重要性调整")
    print("  • C音始终高亮显示(黄色)")
    print("  • 白键和黑键使用不同的网格透明度")
    print("  • 按钮颜色指示当前模式状态")
    print()
    print("🔧 解决问题:")
    print("  • ✅ 音调密集重叠问题")
    print("  • ✅ 缩放时标注过多过少问题")
    print("  • ✅ 不同缩放级别的可读性问题")
    print("  • ✅ 手动精确控制需求")
    print()
    print("🚀 启动集成界面...")
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        integrated_main()
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
