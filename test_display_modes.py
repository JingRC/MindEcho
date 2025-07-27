#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修复后的显示模式
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_display_modes():
    try:
        print("🔧 测试修复后的显示模式...")
        
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
            print("   应该只有: ['心电图模式', '彩色渐变']")
        
        # 检查修复的方法
        checks = [
            ("update_beautiful_pitch_line", hasattr(visualizer, 'update_beautiful_pitch_line')),
            ("update_gradient_mode", hasattr(visualizer, 'update_gradient_mode')),
            ("gradient_lines", hasattr(visualizer, 'gradient_lines')),
            ("highlight_point", hasattr(visualizer, 'highlight_point')),
        ]
        
        for name, result in checks:
            status = "✅" if result else "❌"
            print(f"{status} {name}: {result}")
        
        # 显示窗口
        visualizer.show()
        print("✅ 界面显示成功")
        print("📋 测试说明:")
        print("   • 心电图模式: 细绿色线条（1.5像素）")
        print("   • 彩色渐变模式: 美观的彩色渐变拖尾效果")
        print("   • 已移除无用的'频率曲线'和'音符阶梯'模式")
        print("   • 修复了'cannot remove artist'错误")
        print("🎵 请开始录音并切换显示模式测试效果！")
        
        # 运行应用程序
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_display_modes()
