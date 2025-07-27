#!/usr/bin/env python
"""
测试音调显示和长时间录制修复
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import time
import threading
import numpy as np
from PyQt6.QtWidgets import QApplication
from src.gui.integrated_recording_interface import IntegratedRecordingInterface

def test_long_recording_and_labels():
    """测试长时间录制和音调标签显示"""
    app = QApplication([])
    
    # 创建界面
    interface = IntegratedRecordingInterface()
    interface.show()
    
    # 等待界面初始化
    time.sleep(2)
    
    print("🎨 测试1: 切换到彩色渐变模式")
    index = interface.display_mode.findText("彩色渐变")
    if index >= 0:
        interface.display_mode.setCurrentIndex(index)
        print("✅ 已切换到彩色渐变模式")
    
    # 等待切换完成
    time.sleep(1)
    
    print("🎯 测试2: 模拟长时间录制（5分钟的数据）")
    
    # 生成长时间测试数据
    total_time = 300  # 5分钟
    fps = 64
    total_points = total_time * fps
    
    print(f"📊 生成 {total_points} 个数据点（{total_time}秒）")
    
    # 分批添加数据（模拟实时录制）
    batch_size = 50
    for batch in range(0, total_points, batch_size):
        start_idx = batch
        end_idx = min(batch + batch_size, total_points)
        
        # 生成这一批的数据
        for i in range(start_idx, end_idx):
            timestamp = i / fps
            # 创建变化的音高（正弦波 + 随机颤音）
            base_pitch = 4.0 + 1.5 * np.sin(timestamp * 0.5)  # 慢变化
            vibrato = 0.1 * np.sin(timestamp * 15)  # 颤音
            pitch = base_pitch + vibrato
            
            # 添加到interface的数据
            interface.current_pitch_data.append((timestamp, pitch))
            interface.pitch_data.append(pitch)
            interface.time_data.append(timestamp)
            interface.confidence_data.append(0.8)
            interface.note_data.append(f"C{int(pitch)}")
        
        # 每批更新一次显示
        current_time = end_idx / fps
        print(f"⏱️ 添加数据到 {current_time:.1f}s ({end_idx}/{total_points} 点)")
        
        # 更新彩色渐变显示
        times = list(interface.time_data)[-batch_size:]
        pitches = list(interface.pitch_data)[-batch_size:]
        confidences = list(interface.confidence_data)[-batch_size:]
        
        if len(times) >= 2:
            result = interface.update_beautiful_pitch_line(times, pitches, confidences)
            print(f"📈 渐变更新结果: {result}")
        
        # 强制刷新界面
        interface.canvas.draw_idle()
        app.processEvents()
        
        # 检查数据缓冲区状态
        buffer_usage = len(interface.pitch_data) / interface.pitch_data.maxlen * 100
        print(f"💾 缓冲区使用率: {buffer_usage:.1f}%")
        
        # 每10批暂停一下以便观察
        if batch % (batch_size * 10) == 0:
            time.sleep(0.5)
    
    print("🎨 测试3: 检查音调标签显示")
    print("请检查左侧音调标签是否完整显示")
    
    print("🎯 测试4: 测试不同缩放级别下的标签显示")
    zoom_levels = [0.5, 1.0, 2.0, 3.0]
    for zoom in zoom_levels:
        print(f"🔍 设置缩放级别: {zoom}x")
        zoom_value = int(zoom * 10)  # 转换为滑块值
        interface.zoom_slider.setValue(zoom_value)
        interface.canvas.draw_idle()
        app.processEvents()
        time.sleep(2)
    
    print("✅ 所有测试完成!")
    print("🔍 验证项目:")
    print("  1. 彩色渐变是否持续显示不中断")
    print("  2. 左侧音调标签是否完整可见")
    print("  3. 长时间录制是否正常工作")
    print("  4. 数据缓冲区是否正常管理")
    
    # 保持显示15秒
    time.sleep(15)
    
    app.quit()

if __name__ == "__main__":
    test_long_recording_and_labels()
