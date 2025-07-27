#!/usr/bin/env python
"""
测试交互式音调标注系统
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import time
import threading
import numpy as np
from PyQt6.QtWidgets import QApplication
from src.gui.integrated_recording_interface import IntegratedRecordingInterface

def test_interactive_labels():
    """测试交互式音调标注"""
    app = QApplication([])
    
    # 创建界面
    interface = IntegratedRecordingInterface()
    interface.show()
    
    # 等待界面初始化
    time.sleep(2)
    
    print("🎨 测试交互式音调标注系统")
    
    # 切换到彩色渐变模式以便看到效果
    index = interface.display_mode.findText("彩色渐变")
    if index >= 0:
        interface.display_mode.setCurrentIndex(index)
        print("✅ 已切换到彩色渐变模式")
    
    time.sleep(1)
    
    print("📊 测试1: 无音高输入时的标准显示")
    interface.current_pitch_active = False
    interface.setup_ecg_grid()
    interface.canvas.draw()
    print("  应该看到: C音高亮，白键正常显示，黑键半透明")
    time.sleep(3)
    
    print("🎵 测试2: 模拟不同音高区域的高亮效果")
    
    # 测试不同音高区域
    test_pitches = [
        (2.0, "C2 - 低音区"),
        (3.0, "C3 - 中低音区"), 
        (4.0, "C4 - 中音区"),
        (4.5, "F#4 - 中音区升半音"),
        (5.0, "C5 - 中高音区"),
        (6.0, "C6 - 高音区")
    ]
    
    for pitch_y, description in test_pitches:
        print(f"🎯 测试音高: {description}")
        
        # 设置当前音高状态
        interface.current_pitch_y = pitch_y
        interface.current_pitch_active = True
        interface.last_pitch_time = time.time()
        
        # 自动调整视图到当前音高区域
        interface.y_view_center = pitch_y
        interface.update_axis_ranges()
        
        # 重新绘制网格和标签
        interface.setup_ecg_grid()
        interface.canvas.draw()
        
        print(f"  当前音高: {pitch_y:.1f}")
        print(f"  应该看到: {description} 附近金色高亮，向外渐变透明度")
        
        # 添加一些模拟的音高数据点来显示彩色渐变
        times = [i * 0.1 for i in range(20)]
        pitches = [pitch_y + 0.1 * np.sin(i * 0.3) for i in range(20)]
        confidences = [0.8] * 20
        
        # 添加数据到界面存储
        for t, p in zip(times, pitches):
            interface.time_data.append(t)
            interface.pitch_data.append(p)
            interface.confidence_data.append(0.8)
        
        # 更新彩色渐变显示
        interface.update_beautiful_pitch_line(times, pitches, confidences)
        interface.canvas.draw()
        
        time.sleep(4)
        
        print(f"  ✅ {description} 测试完成")
    
    print("⏰ 测试3: 音高活跃状态超时测试")
    print("  等待2秒观察标签从高亮状态自动恢复到标准显示...")
    
    # 不更新 last_pitch_time，让系统自动检测超时
    start_time = time.time()
    while time.time() - start_time < 3:
        app.processEvents()
        time.sleep(0.1)
    
    print("🔍 测试4: 不同缩放级别下的标签完整性")
    zoom_levels = [0.3, 0.8, 1.5, 3.0]
    
    for zoom in zoom_levels:
        print(f"🔍 设置缩放级别: {zoom}x")
        zoom_value = int(zoom * 10)
        interface.zoom_slider.setValue(zoom_value)
        interface.setup_ecg_grid()
        interface.canvas.draw()
        
        print(f"  缩放 {zoom}x: 检查左侧标签是否完整可见")
        time.sleep(2)
    
    print("✅ 交互式音调标注测试完成!")
    print("🎯 验证要点:")
    print("  1. 无音高时: C音金色，白键正常，黑键半透明")
    print("  2. 有音高时: 当前音高金色，距离越远透明度越高")
    print("  3. 超时恢复: 1秒无音高输入后自动恢复标准显示")
    print("  4. 缩放适应: 任何缩放级别下标签都完整可见")
    print("  5. 渐变兼容: 音调高亮不影响彩色渐变线显示")
    
    # 保持显示10秒供最终检查
    time.sleep(10)
    
    app.quit()

if __name__ == "__main__":
    test_interactive_labels()
