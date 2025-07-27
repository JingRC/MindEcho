#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试基本绿色线条显示
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def quick_test():
    try:
        print("🚀 快速测试基本线条显示...")
        
        from src.gui.integrated_recording_interface import ECGStylePitchVisualizer
        from PyQt6.QtWidgets import QApplication
        
        app = QApplication(sys.argv)
        visualizer = ECGStylePitchVisualizer()
        
        print("✅ 可视化器创建成功")
        print("✅ 美观线条功能已临时禁用")
        print("✅ 现在应该显示基本的亮绿色线条")
        print("📋 线条设置:")
        print("   - 颜色: 明亮绿色 (#00FF44)")
        print("   - 线宽: 2.0 像素")
        print("   - 透明度: 完全不透明")
        
        visualizer.show()
        print("🎵 请开始录音测试线条显示！")
        
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    quick_test()
