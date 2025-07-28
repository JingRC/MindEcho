#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试控制面板时间显示与录音时长同步功能
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import QTimer
from gui.integrated_recording_interface import IntegratedRecordingInterface

class TimeSyncTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("控制面板时间同步测试")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中央控件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建测试按钮区域
        button_layout = QHBoxLayout()
        
        self.status_label = QLabel("测试状态：准备中...")
        button_layout.addWidget(self.status_label)
        
        test_sync_btn = QPushButton("检查时间同步")
        test_sync_btn.clicked.connect(self.test_time_sync)
        button_layout.addWidget(test_sync_btn)
        
        simulate_data_btn = QPushButton("模拟数据测试")
        simulate_data_btn.clicked.connect(self.simulate_data_test)
        button_layout.addWidget(simulate_data_btn)
        
        layout.addLayout(button_layout)
        
        # 创建录音接口
        self.recording_interface = IntegratedRecordingInterface()
        layout.addWidget(self.recording_interface)
        
        # 设置定时器定期检查时间同步
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.check_time_sync)
        self.sync_timer.start(1000)  # 每秒检查一次
        
        print("🚀 控制面板时间同步测试启动")
        print("📝 测试内容：")
        print("  - 验证控制面板时间显示与数据时长同步")
        print("  - 检查录音状态和非录音状态的时间显示")
        print("  - 确认时间计算的准确性")
    
    def test_time_sync(self):
        """手动测试时间同步"""
        print(f"\n🎯 手动检查时间同步...")
        self.check_time_sync()
    
    def check_time_sync(self):
        """检查时间同步状态"""
        try:
            # 获取时间数据
            time_data_len = len(self.recording_interface.time_data)
            recording_duration = self.recording_interface.recording_duration
            is_recording = self.recording_interface.is_recording
            
            # 计算实际数据时长
            if time_data_len > 0:
                actual_duration = max(self.recording_interface.time_data)
            else:
                actual_duration = 0
            
            # 获取控制面板显示的时间
            time_label_text = self.recording_interface.recording_time_label.text()
            
            # 更新状态显示
            status_text = f"数据点: {time_data_len}, "
            status_text += f"实际时长: {actual_duration:.1f}s, "
            status_text += f"录音时长: {recording_duration:.1f}s, "
            status_text += f"录音中: {is_recording}, "
            status_text += f"显示: {time_label_text}"
            
            self.status_label.setText(status_text)
            
            # 检查同步性
            expected_minutes = int(actual_duration // 60)
            expected_seconds = int(actual_duration % 60)
            expected_text = f"{expected_minutes:02d}:{expected_seconds:02d}"
            
            if expected_text in time_label_text:
                sync_status = "✅ 同步正确"
            else:
                sync_status = "❌ 同步错误"
            
            # 每5秒打印一次详细信息
            if hasattr(self, 'last_print_time'):
                if time.time() - self.last_print_time > 5:
                    self.print_detailed_status(actual_duration, expected_text, time_label_text, sync_status)
                    self.last_print_time = time.time()
            else:
                import time
                self.last_print_time = time.time()
                self.print_detailed_status(actual_duration, expected_text, time_label_text, sync_status)
                
        except Exception as e:
            print(f"❌ 检查时间同步时出错: {e}")
            self.status_label.setText(f"检查出错: {e}")
    
    def print_detailed_status(self, actual_duration, expected_text, time_label_text, sync_status):
        """打印详细状态信息"""
        print(f"🔍 时间同步检查:")
        print(f"  - 实际数据时长: {actual_duration:.1f}秒")
        print(f"  - 期望显示: {expected_text}")
        print(f"  - 实际显示: {time_label_text}")
        print(f"  - 同步状态: {sync_status}")
    
    def simulate_data_test(self):
        """模拟数据测试"""
        print(f"\n🧪 开始模拟数据测试...")
        
        # 模拟添加一些音高数据
        import time
        from collections import deque
        
        # 添加模拟数据点
        start_time = time.time()
        for i in range(10):
            timestamp = start_time + i * 0.5  # 每0.5秒一个数据点
            
            # 模拟pitch_data结构
            pitch_data = {
                'frequency': 440.0 + i * 10,  # 模拟频率变化
                'confidence': 0.8,
                'timestamp': timestamp,
                'note_info': {'note': 'A4', 'octave': 4}
            }
            
            # 添加到录音接口
            self.recording_interface.add_pitch_data(pitch_data)
        
        print(f"✅ 已添加10个模拟数据点，时间跨度约5秒")
        
        # 立即检查时间同步
        QTimer.singleShot(100, self.check_time_sync)

def main():
    app = QApplication(sys.argv)
    window = TimeSyncTestWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
