#!/usr/bin/env python3
"""
简单测试脚本 - 验证音调线8秒后不消失
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from src.gui.integrated_recording_interface import IntegratedRecordingInterface
from PyQt6.QtWidgets import QApplication
import time

def test_simple():
    """简单测试"""
    print("🎯 启动简化版本测试...")
    print("📋 测试内容: 验证音调线8秒后不消失")
    print("💡 使用方法: 开始录音，持续唱歌超过10秒，观察音调线是否持续显示")
    
    app = QApplication(sys.argv)
    
    # 创建界面
    interface = IntegratedRecordingInterface()
    interface.show()
    
    print("✅ 测试界面已启动")
    print("🎤 请开始录音并持续唱歌，观察8秒后音调线是否仍然显示")
    
    app.exec()

if __name__ == "__main__":
    test_simple()
