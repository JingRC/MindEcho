#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试time_data属性错误修复
验证控制面板状态更新不再出现属性错误
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton, QHBoxLayout
from PyQt6.QtCore import QTimer
from gui.integrated_recording_interface import IntegratedRecordingInterface

class AttributeErrorTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("time_data属性错误修复测试")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中央控件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建测试信息显示
        test_layout = QHBoxLayout()
        
        self.error_count_label = QLabel("错误计数: 0")
        test_layout.addWidget(self.error_count_label)
        
        self.status_info_label = QLabel("状态: 监控中...")
        test_layout.addWidget(self.status_info_label)
        
        test_btn = QPushButton("强制测试控制面板更新")
        test_btn.clicked.connect(self.force_test_update)
        test_layout.addWidget(test_btn)
        
        layout.addLayout(test_layout)
        
        # 创建录音接口
        self.recording_interface = IntegratedRecordingInterface()
        layout.addWidget(self.recording_interface)
        
        # 错误监控
        self.error_count = 0
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.monitor_errors)
        self.monitor_timer.start(1000)  # 每秒检查一次
        
        # 重定向错误输出到我们的监控函数
        self.original_print = print
        import builtins
        builtins.print = self.custom_print
        
        print("🚀 time_data属性错误修复测试启动")
        print("📝 测试内容：")
        print("  - 监控控制面板状态更新错误")
        print("  - 验证time_data属性安全检查")
        print("  - 确认不再出现AttributeError")
    
    def custom_print(self, *args, **kwargs):
        """自定义print函数，捕获错误信息"""
        message = ' '.join(str(arg) for arg in args)
        
        # 检查是否是我们要监控的错误
        if "time_data" in message and "属性不存在" in message:
            self.error_count += 1
            print(f"🔍 捕获到time_data属性错误: {message}")
        elif "更新状态显示错误" in message and "time_data" in message:
            self.error_count += 1
            print(f"⚠️  捕获到状态更新错误: {message}")
        
        # 调用原始print函数
        self.original_print(*args, **kwargs)
    
    def monitor_errors(self):
        """监控错误状态"""
        try:
            # 更新错误计数显示
            self.error_count_label.setText(f"错误计数: {self.error_count}")
            
            # 检查录音接口的属性状态
            has_time_data = hasattr(self.recording_interface, 'time_data')
            has_control_labels = (
                hasattr(self.recording_interface, 'recording_time_label') and
                hasattr(self.recording_interface, 'current_pitch_label') and
                hasattr(self.recording_interface, 'detection_count_label')
            )
            
            # 更新状态信息
            status_text = f"time_data存在: {has_time_data}, 控制标签存在: {has_control_labels}"
            if self.error_count == 0:
                status_text += " - ✅ 运行正常"
            else:
                status_text += f" - ❌ 发现{self.error_count}个错误"
            
            self.status_info_label.setText(status_text)
            
            # 每10秒打印一次详细状态
            if hasattr(self, 'last_detail_print'):
                if time.time() - self.last_detail_print > 10:
                    self.print_detailed_status(has_time_data, has_control_labels)
                    self.last_detail_print = time.time()
            else:
                import time
                self.last_detail_print = time.time()
                self.print_detailed_status(has_time_data, has_control_labels)
                
        except Exception as e:
            self.original_print(f"❌ 监控错误时出错: {e}")
    
    def print_detailed_status(self, has_time_data, has_control_labels):
        """打印详细状态信息"""
        self.original_print(f"🔍 属性状态检查:")
        self.original_print(f"  - time_data属性存在: {has_time_data}")
        self.original_print(f"  - 控制面板标签存在: {has_control_labels}")
        self.original_print(f"  - 累计错误数量: {self.error_count}")
        
        if has_time_data:
            time_data_len = len(self.recording_interface.time_data)
            self.original_print(f"  - time_data长度: {time_data_len}")
        
        if self.error_count == 0:
            self.original_print("  ✅ 修复有效，未发现属性错误")
        else:
            self.original_print("  ⚠️  仍有错误，需要进一步检查")
    
    def force_test_update(self):
        """强制测试控制面板更新"""
        self.original_print(f"\n🧪 强制测试控制面板更新...")
        
        try:
            # 直接调用控制面板更新函数
            self.recording_interface.update_control_panel_status()
            self.original_print("✅ 强制更新成功，未出现错误")
        except Exception as e:
            self.error_count += 1
            self.original_print(f"❌ 强制更新失败: {e}")

def main():
    app = QApplication(sys.argv)
    window = AttributeErrorTestWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
