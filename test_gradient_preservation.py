#!/usr/bin/env python
"""
测试彩色渐变preservation在grid setup中的效果
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import time
import threading
import numpy as np
from PyQt6.QtWidgets import QApplication
from src.gui.integrated_recording_interface import IntegratedRecordingInterface

def test_gradient_preservation():
    """测试网格设置中的渐变保持"""
    app = QApplication([])
    
    # 创建界面
    interface = IntegratedRecordingInterface()
    interface.show()
    
    # 等待界面初始化
    time.sleep(1)
    
    # 切换到beautiful模式
    interface.display_mode = 'beautiful'
    interface.mode_switch_button.setText("模式: 彩色渐变")
    print("🎨 已切换到彩色渐变模式")
    
    # 生成测试音高数据（彩虹频谱）
    test_pitches = []
    test_times = []
    for i in range(100):
        # 创建从C4到C6的渐变音高
        pitch = 4.0 + 2.0 * (i / 99.0)  # 从4.0到6.0
        time_point = i * 0.05  # 5秒钟的数据
        test_pitches.append(pitch)
        test_times.append(time_point)
    
    # 添加测试数据
    for i, (pitch, timestamp) in enumerate(zip(test_pitches, test_times)):
        interface.current_pitch_data.append((timestamp, pitch))
        
        # 每20个点更新一次显示
        if i % 20 == 0:
            interface.update_beautiful_pitch_line()
            app.processEvents()
            time.sleep(0.1)
    
    print("📊 已添加测试音高数据，应该看到彩色渐变")
    time.sleep(2)
    
    # 测试网格刷新（这里应该保持彩色渐变）
    print("🔄 测试网格刷新...")
    interface.setup_ecg_grid()
    interface.canvas.draw()
    print("✅ 网格刷新完成，检查彩色渐变是否保持")
    
    # 保持显示
    time.sleep(10)
    
    app.quit()

if __name__ == "__main__":
    test_gradient_preservation()
