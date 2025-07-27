#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试美观渐变线条效果
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.gui.integrated_recording_interface import ECGStylePitchVisualizer
    from PyQt6.QtWidgets import QApplication
    
    print("✓ 成功导入必要模块")
    
    # 创建应用程序
    app = QApplication(sys.argv)
    
    # 创建主窗口
    visualizer = ECGStylePitchVisualizer()
    print("✓ 成功创建ECGStylePitchVisualizer")
    
    # 检查是否正确初始化了gradient_lines和highlight_point
    print(f"✓ gradient_lines初始化状态: {hasattr(visualizer, 'gradient_lines')}")
    print(f"✓ highlight_point初始化状态: {hasattr(visualizer, 'highlight_point')}")
    
    # 检查新方法是否存在
    print(f"✓ update_beautiful_pitch_line方法存在: {hasattr(visualizer, 'update_beautiful_pitch_line')}")
    print(f"✓ fallback_simple_line方法存在: {hasattr(visualizer, 'fallback_simple_line')}")
    
    # 显示窗口
    visualizer.show()
    print("✓ 成功显示界面")
    print("✓ 测试完成 - 可以开始录音测试渐变线条效果")
    
    # 运行应用程序
    sys.exit(app.exec())
    
except ImportError as e:
    print(f"❌ 导入错误: {e}")
except Exception as e:
    print(f"❌ 运行错误: {e}")
    import traceback
    traceback.print_exc()
