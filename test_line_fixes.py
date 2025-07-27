#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试线条显示修复效果
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_line_display_fixes():
    try:
        print("🔧 测试线条显示修复效果...")
        
        # 导入模块
        from src.gui.integrated_recording_interface import ECGStylePitchVisualizer
        from PyQt6.QtWidgets import QApplication
        
        print("✅ 模块导入成功")
        
        # 创建应用程序
        app = QApplication(sys.argv)
        
        # 创建主窗口
        visualizer = ECGStylePitchVisualizer()
        print("✅ 可视化器创建成功")
        
        # 检查显示模式选项
        if hasattr(visualizer, 'display_mode'):
            modes = [visualizer.display_mode.itemText(i) for i in range(visualizer.display_mode.count())]
            print(f"✅ 显示模式: {modes}")
        
        # 显示窗口
        visualizer.show()
        print("✅ 界面显示成功")
        print("\n📋 修复内容:")
        print("1. 💚 心电图模式:")
        print("   • 线条宽度: 1.5像素 → 1.0像素 (更细)")
        print("   • 提高颤音等细节的显示清晰度")
        print("   • 适合精细音高分析")
        print("\n2. 🌈 彩色渐变模式:")
        print("   • 添加调试信息，帮助问题定位")
        print("   • 增强线条可见性 (1.5-4.0像素宽度)")
        print("   • 提高透明度 (0.4-1.0)")
        print("   • 更高的zorder确保前景显示")
        print("   • 圆润端点美化")
        print("   • 彩色高亮点指示当前位置")
        print("\n🎵 请开始录音并测试两种显示模式！")
        print("💡 注意观察控制台的调试信息")
        
        # 运行应用程序
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_line_display_fixes()
