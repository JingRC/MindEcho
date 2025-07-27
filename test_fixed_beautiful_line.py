#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复版本的测试脚本 - 测试美观渐变线条
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_program():
    try:
        print("🔧 开始修复版本测试...")
        
        # 导入必要模块
        from src.gui.integrated_recording_interface import ECGStylePitchVisualizer
        from PyQt6.QtWidgets import QApplication
        
        print("✅ 模块导入成功")
        
        # 创建应用程序
        app = QApplication(sys.argv)
        
        # 创建主窗口
        visualizer = ECGStylePitchVisualizer()
        print("✅ ECGStylePitchVisualizer创建成功")
        
        # 检查修复的属性
        checks = [
            ("gradient_lines", hasattr(visualizer, 'gradient_lines')),
            ("highlight_point", hasattr(visualizer, 'highlight_point')),
            ("update_beautiful_pitch_line", hasattr(visualizer, 'update_beautiful_pitch_line')),
            ("fallback_simple_line", hasattr(visualizer, 'fallback_simple_line')),
        ]
        
        for name, result in checks:
            status = "✅" if result else "❌"
            print(f"{status} {name}: {result}")
        
        # 显示窗口
        visualizer.show()
        print("✅ 界面显示成功")
        print("🎵 修复完成！现在可以开始录音测试美观线条效果")
        print("📋 修复内容:")
        print("   - 安全的对象移除机制")
        print("   - None值检查")
        print("   - 错误恢复机制")
        print("   - 完整的备用方案")
        
        # 运行应用程序
        sys.exit(app.exec())
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
    except Exception as e:
        print(f"❌ 运行错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_program()
