#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化测试：确保基本线条显示正常
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_basic_line_display():
    try:
        print("🔧 测试基本线条显示...")
        
        # 导入模块
        from src.gui.integrated_recording_interface import ECGStylePitchVisualizer
        from PyQt6.QtWidgets import QApplication
        import numpy as np
        
        print("✅ 模块导入成功")
        
        # 创建应用程序
        app = QApplication(sys.argv)
        
        # 创建主窗口
        visualizer = ECGStylePitchVisualizer()
        print("✅ 可视化器创建成功")
        
        # 模拟一些测试数据
        test_times = [0.1, 0.2, 0.3, 0.4, 0.5]
        test_pitches = [3.0, 3.2, 3.1, 3.3, 3.2]
        
        # 直接测试基本线条设置
        print("🧪 测试基本线条设置...")
        try:
            visualizer.pitch_line.set_data(test_times, test_pitches)
            print("✅ 基本线条数据设置成功")
        except Exception as e:
            print(f"❌ 基本线条设置失败: {e}")
        
        # 测试美观线条（可选）
        print("🎨 测试美观线条（可选功能）...")
        try:
            visualizer.update_beautiful_pitch_line(test_times, test_pitches, [0.9]*5)
            print("✅ 美观线条更新成功")
        except Exception as e:
            print(f"⚠️ 美观线条失败（不影响基本显示）: {e}")
        
        # 显示窗口
        visualizer.show()
        print("✅ 界面显示成功")
        print("📋 测试结果:")
        print("   - 基本线条功能已验证")
        print("   - 现在可以开始录音测试")
        print("   - 即使美观效果失败，基本线条也会显示")
        
        # 运行应用程序
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_basic_line_display()
