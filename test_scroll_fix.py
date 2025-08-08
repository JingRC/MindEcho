#!/usr/bin/env python3
"""
测试音调线滚动修复效果
验证垂直滚动后音调线不会消失的问题
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
except ImportError:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QTimer

from src.gui.integrated_recording_interface import IntegratedRecordingInterface

def test_scroll_fix():
    """测试滚动修复效果"""
    print("🧪 开始测试音调线滚动修复效果...")
    
    app = QApplication(sys.argv)
    
    # 创建主界面
    interface = IntegratedRecordingInterface()
    interface.show()
    
    print("✅ 界面已启动")
    print("🔍 测试步骤:")
    print("1. 点击开始录音")
    print("2. 等待8秒，观察自动滚动开始")
    print("3. 拖动垂直滚动条，检查音调线是否仍然可见")
    print("4. 拖动水平滚动条，检查音调线是否正常显示")
    print("5. 点击清除按钮，检查是否能正常清除")
    print("6. 点击重置按钮，检查视图是否正常重置")
    
    # 运行应用
    sys.exit(app.exec())

if __name__ == "__main__":
    test_scroll_fix()
