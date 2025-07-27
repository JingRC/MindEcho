#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
验证横轴滚动修复结果
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QHBoxLayout
from PyQt6.QtCore import QTimer
from gui.integrated_recording_interface import IntegratedRecordingInterface

class ScrollFixTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("横轴滚动修复验证")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中央控件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建测试按钮区域
        button_layout = QHBoxLayout()
        
        test_left_btn = QPushButton("测试最左端 (0%)")
        test_left_btn.clicked.connect(lambda: self.test_scroll_position(0))
        button_layout.addWidget(test_left_btn)
        
        test_middle_btn = QPushButton("测试中间 (50%)")
        test_middle_btn.clicked.connect(lambda: self.test_scroll_position(50))
        button_layout.addWidget(test_middle_btn)
        
        test_right_btn = QPushButton("测试最右端 (100%)")
        test_right_btn.clicked.connect(lambda: self.test_scroll_position(100))
        button_layout.addWidget(test_right_btn)
        
        layout.addLayout(button_layout)
        
        # 状态显示
        self.status_label = QLabel("准备测试...")
        layout.addWidget(self.status_label)
        
        # 创建录音接口
        self.recording_interface = IntegratedRecordingInterface()
        layout.addWidget(self.recording_interface)
        
        print("🚀 横轴滚动修复验证启动")
        print("📝 测试内容:")
        print("  - 验证最左端显示 [0.0s, 16.0s]")
        print("  - 验证最右端显示 [284.0s, 300.0s]")
        print("  - 确认无录音数据时滚动正常")
    
    def test_scroll_position(self, position):
        """测试特定滚动位置"""
        print(f"\n🎯 测试滚动条位置: {position}%")
        
        # 设置滚动条位置
        self.recording_interface.horizontal_scrollbar.setValue(position)
        
        # 等待界面更新
        QTimer.singleShot(100, lambda: self.check_result(position))
    
    def check_result(self, position):
        """检查结果"""
        try:
            # 获取参数
            time_offset = self.recording_interface.time_offset
            time_window = self.recording_interface.time_window
            
            # 计算预期显示范围
            expected_x_min = time_offset
            expected_x_max = time_offset + time_window
            
            # 获取实际显示范围
            actual_xlim = self.recording_interface.ax.get_xlim()
            actual_x_min, actual_x_max = actual_xlim
            
            # 检查是否匹配
            x_min_match = abs(actual_x_min - expected_x_min) < 0.5
            x_max_match = abs(actual_x_max - expected_x_max) < 0.5
            
            # 更新状态显示
            status = f"滚动条{position}%: "
            status += f"预期[{expected_x_min:.1f}s, {expected_x_max:.1f}s], "
            status += f"实际[{actual_x_min:.1f}s, {actual_x_max:.1f}s] - "
            
            if x_min_match and x_max_match:
                status += "✅ 正确"
                print(f"  ✅ 正确! 显示范围: [{actual_x_min:.1f}s, {actual_x_max:.1f}s]")
            else:
                status += "❌ 错误"
                print(f"  ❌ 错误! 预期: [{expected_x_min:.1f}s, {expected_x_max:.1f}s], 实际: [{actual_x_min:.1f}s, {actual_x_max:.1f}s]")
            
            self.status_label.setText(status)
            
            # 特别检查最右端
            if position == 100:
                if abs(actual_x_min - 284.0) < 0.5 and abs(actual_x_max - 300.0) < 0.5:
                    print("  🎉 最右端测试通过! 显示范围284-300秒")
                else:
                    print("  ⚠️  最右端测试失败! 应该显示284-300秒")
                    
        except Exception as e:
            print(f"❌ 检查结果时出错: {e}")
            self.status_label.setText(f"检查出错: {e}")

def main():
    app = QApplication(sys.argv)
    window = ScrollFixTestWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
