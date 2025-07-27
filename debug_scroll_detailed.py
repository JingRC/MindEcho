#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
深度调试横轴滚动问题
检查实际运行时的X轴显示范围
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import QTimer
from gui.integrated_recording_interface import IntegratedRecordingInterface

class ScrollDebugWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("横轴滚动调试器")
        self.setGeometry(100, 100, 1400, 900)
        
        # 创建中央控件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建调试信息显示
        debug_layout = QHBoxLayout()
        self.info_label = QLabel("调试信息将在这里显示")
        debug_layout.addWidget(self.info_label)
        
        # 添加调试按钮
        debug_button = QPushButton("检查当前显示范围")
        debug_button.clicked.connect(self.check_display_range)
        debug_layout.addWidget(debug_button)
        
        scroll_test_button = QPushButton("测试滚动到最右端")
        scroll_test_button.clicked.connect(self.test_scroll_right)
        debug_layout.addWidget(scroll_test_button)
        
        layout.addLayout(debug_layout)
        
        # 创建录音接口
        self.recording_interface = IntegratedRecordingInterface()
        layout.addWidget(self.recording_interface)
        
        # 设置定时器定期检查显示范围
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_display_range)
        self.check_timer.start(2000)  # 每2秒检查一次
    
    def check_display_range(self):
        """检查当前显示范围"""
        try:
            # 获取参数
            time_offset = self.recording_interface.time_offset
            time_window = self.recording_interface.time_window
            max_history = self.recording_interface.max_history_time
            
            # 计算显示范围
            x_min = time_offset
            x_max = time_offset + time_window
            
            # 获取matplotlib实际显示范围
            if hasattr(self.recording_interface, 'ax'):
                actual_xlim = self.recording_interface.ax.get_xlim()
                actual_x_min, actual_x_max = actual_xlim
            else:
                actual_x_min, actual_x_max = "N/A", "N/A"
            
            # 获取滚动条位置
            scroll_value = self.recording_interface.horizontal_scrollbar.value()
            
            # 更新信息显示
            info_text = f"参数: offset={time_offset:.1f}s, window={time_window:.1f}s, max={max_history:.1f}s | "
            info_text += f"计算范围: [{x_min:.1f}s, {x_max:.1f}s] | "
            info_text += f"实际范围: [{actual_x_min:.1f}s, {actual_x_max:.1f}s] | "
            info_text += f"滚动条: {scroll_value}%"
            
            self.info_label.setText(info_text)
            
            # 打印详细信息
            print(f"🔍 显示范围检查:")
            print(f"  - 滚动条位置: {scroll_value}%")
            print(f"  - 时间偏移: {time_offset:.1f}s")
            print(f"  - 时间窗口: {time_window:.1f}s")
            print(f"  - 计算的显示范围: [{x_min:.1f}s, {x_max:.1f}s]")
            print(f"  - matplotlib实际范围: [{actual_x_min:.1f}s, {actual_x_max:.1f}s]")
            
            # 检查是否匹配
            if abs(float(actual_x_min) - x_min) > 0.5 or abs(float(actual_x_max) - x_max) > 0.5:
                print(f"  ⚠️  不匹配! 预期: [{x_min:.1f}s, {x_max:.1f}s], 实际: [{actual_x_min:.1f}s, {actual_x_max:.1f}s]")
            else:
                print(f"  ✅ 范围匹配")
                
        except Exception as e:
            print(f"❌ 检查显示范围时出错: {e}")
            self.info_label.setText(f"检查出错: {e}")
    
    def test_scroll_right(self):
        """测试滚动到最右端"""
        print(f"\n🎯 测试滚动到最右端...")
        
        # 设置滚动条到最右端
        self.recording_interface.horizontal_scrollbar.setValue(100)
        
        # 等待一下让界面更新
        QTimer.singleShot(100, self.check_display_range)
        QTimer.singleShot(500, self.check_display_range)

def main():
    app = QApplication(sys.argv)
    window = ScrollDebugWindow()
    window.show()
    
    print("🚀 横轴滚动调试器启动")
    print("📝 功能:")
    print("  - 实时监控时间偏移和显示范围")
    print("  - 对比计算值与实际matplotlib显示值")
    print("  - 测试滚动到最右端的行为")
    print("  - 每2秒自动检查显示状态")
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
