#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试横轴滚动控制功能
验证在没有录音数据时的滚动行为
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtCore import QTimer
from gui.integrated_recording_interface import IntegratedRecordingInterface

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("测试横轴滚动控制")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中央控件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建录音接口
        self.recording_interface = IntegratedRecordingInterface()
        layout.addWidget(self.recording_interface)
        
        # 测试时间轴控制
        self.test_timeline_controls()
    
    def test_timeline_controls(self):
        """测试时间轴控制功能"""
        print("🔧 开始测试横轴滚动控制功能...")
        
        # 验证初始设置
        print(f"📊 初始设置:")
        print(f"  - 时间窗口: {self.recording_interface.time_window}秒")
        print(f"  - 最大历史时间: {self.recording_interface.max_history_time}秒")
        print(f"  - 时间偏移: {self.recording_interface.time_offset}秒")
        print(f"  - 滚动条位置: {self.recording_interface.horizontal_scrollbar.value()}")
        
        # 测试不同的最大长度设置
        def test_max_length(duration):
            print(f"\n🎯 测试设置最大长度为{duration}秒...")
            self.recording_interface.set_max_history_time(duration)
            print(f"  - 新的最大历史时间: {self.recording_interface.max_history_time}秒")
            
            # 测试滚动到不同位置
            positions = [0, 25, 50, 75, 100]
            for pos in positions:
                self.recording_interface.horizontal_scrollbar.setValue(pos)
                expected_offset = (pos / 100.0) * max(0, duration - self.recording_interface.time_window)
                actual_offset = self.recording_interface.time_offset
                print(f"  - 滚动条{pos}% -> 时间偏移: {actual_offset:.1f}s (期望: {expected_offset:.1f}s)")
        
        # 设置定时器进行测试
        QTimer.singleShot(1000, lambda: test_max_length(100))
        QTimer.singleShot(3000, lambda: test_max_length(200))
        QTimer.singleShot(5000, lambda: test_max_length(300))
        
        # 测试滚动范围
        def test_scroll_range():
            print(f"\n📏 测试滚动范围 (无录音数据状态):")
            self.recording_interface.set_max_history_time(300)
            
            # 滚动到最左端
            self.recording_interface.horizontal_scrollbar.setValue(0)
            print(f"  - 最左端: 时间偏移 {self.recording_interface.time_offset:.1f}s")
            print(f"    显示范围: {self.recording_interface.time_offset:.1f}s - {self.recording_interface.time_offset + self.recording_interface.time_window:.1f}s")
            
            # 滚动到最右端
            self.recording_interface.horizontal_scrollbar.setValue(100)
            print(f"  - 最右端: 时间偏移 {self.recording_interface.time_offset:.1f}s")
            print(f"    显示范围: {self.recording_interface.time_offset:.1f}s - {self.recording_interface.time_offset + self.recording_interface.time_window:.1f}s")
        
        QTimer.singleShot(7000, test_scroll_range)
        
        print("✅ 测试已启动，请观察控制台输出和界面响应...")

def main():
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    
    print("🚀 横轴滚动控制测试程序已启动")
    print("📝 测试内容:")
    print("  1. 验证初始设置 (16秒显示窗口，300秒最大历史)")
    print("  2. 测试不同最大长度设置 (100s, 200s, 300s)")
    print("  3. 验证滚动范围 (0-16s 到 284-300s)")
    print("  4. 确认无录音数据时的滚动行为")
    print("\n🎮 操作提示:")
    print("  - 使用界面上的横轴长度控制按钮")
    print("  - 拖动水平滚动条测试滚动")
    print("  - 观察时间轴标签的变化")
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
