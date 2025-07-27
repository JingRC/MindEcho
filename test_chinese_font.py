#!/usr/bin/env python
"""
测试中文字体显示修复
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import time
import threading
import numpy as np
from PyQt6.QtWidgets import QApplication
from src.gui.integrated_recording_interface import IntegratedRecordingInterface

def test_chinese_font():
    """测试中文字体显示"""
    app = QApplication([])
    
    # 创建界面
    interface = IntegratedRecordingInterface()
    interface.show()
    
    # 等待界面初始化
    time.sleep(2)
    
    print("🔤 测试中文字体显示...")
    print(f"✅ 中文字体状态: {interface.chinese_font_available}")
    
    # 测试两种模式的中文显示
    modes = ["心电图模式", "彩色渐变"]
    
    for mode in modes:
        print(f"\n🎨 测试 {mode} 的中文显示")
        
        # 设置模式
        index = interface.display_mode.findText(mode)
        if index >= 0:
            interface.display_mode.setCurrentIndex(index)
            print(f"  ✅ 已切换到 {mode}")
        
        # 等待界面更新
        app.processEvents()
        time.sleep(1)
        
        # 生成测试数据
        test_pitches = [4.0, 4.5, 5.0, 5.5, 6.0]
        test_times = [0.0, 1.0, 2.0, 3.0, 4.0]
        
        # 添加数据到界面
        for pitch, timestamp in zip(test_pitches, test_times):
            interface.current_pitch_data.append((timestamp, pitch))
        
        # 更新显示
        if mode == "心电图模式":
            interface.update_ecg_mode(test_times, test_pitches, [0.8] * len(test_pitches))
        else:
            interface.update_beautiful_pitch_line(test_times, test_pitches, [0.8] * len(test_pitches))
        
        interface.canvas.draw()
        print(f"  ✅ {mode} 数据已更新")
        
        # 显示3秒
        time.sleep(3)
    
    print("\n📊 中文字体测试完成!")
    print("请检查界面上的中文标签是否正常显示：")
    print("  • 标题: '实时音高分析 - 心电图式显示 (可拖拽查看)'")
    print("  • X轴标签: '时间 (秒)'") 
    print("  • Y轴标签: '音高'")
    print("  • 控件标签: '显示模式:', '心电图模式', '彩色渐变'")
    
    # 保持显示10秒
    time.sleep(10)
    
    app.quit()

if __name__ == "__main__":
    test_chinese_font()
