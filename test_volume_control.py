#!/usr/bin/env python3
"""
测试音量控制功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt
from src.gui.integrated_recording_interface import VolumeControlDialog, IntegratedAudioProcessor

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("音量控制测试")
        self.setFixedSize(300, 200)
        
        # 创建音频处理器
        self.audio_processor = IntegratedAudioProcessor()
        
        # 创建UI
        central_widget = QWidget()
        layout = QVBoxLayout()
        
        # 测试按钮
        test_btn = QPushButton("🎚️ 测试音量控制")
        test_btn.clicked.connect(self.show_volume_control)
        layout.addWidget(test_btn)
        
        # 设置音量按钮
        set_volume_btn = QPushButton("设置音量到150%")
        set_volume_btn.clicked.connect(self.set_test_volume)
        layout.addWidget(set_volume_btn)
        
        # 获取音量按钮
        get_volume_btn = QPushButton("获取当前音量")
        get_volume_btn.clicked.connect(self.get_current_volume)
        layout.addWidget(get_volume_btn)
        
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
        
        # 音量控制对话框
        self.volume_dialog = None
        
    def show_volume_control(self):
        """显示音量控制对话框"""
        try:
            if not self.volume_dialog:
                current_volume = self.audio_processor.get_manual_volume()
                self.volume_dialog = VolumeControlDialog(self, current_volume)
                self.volume_dialog.volume_changed.connect(self.on_volume_changed)
            
            self.volume_dialog.show()
            self.volume_dialog.raise_()
            self.volume_dialog.activateWindow()
            
        except Exception as e:
            print(f"❌ 显示音量控制失败: {e}")
    
    def on_volume_changed(self, volume):
        """音量变化处理"""
        success = self.audio_processor.set_manual_volume(volume)
        if success:
            print(f"✅ 音量设置成功: {volume}%")
        else:
            print(f"❌ 音量设置失败: {volume}%")
    
    def set_test_volume(self):
        """设置测试音量"""
        success = self.audio_processor.set_manual_volume(150)
        if success:
            print("✅ 测试音量设置为150%")
            if self.volume_dialog:
                self.volume_dialog.set_volume(150)
        else:
            print("❌ 设置测试音量失败")
    
    def get_current_volume(self):
        """获取当前音量"""
        volume = self.audio_processor.get_manual_volume()
        print(f"📊 当前音量: {volume}%")

def main():
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyleSheet("""
        QMainWindow {
            background-color: #2b2b2b;
        }
        QPushButton {
            background-color: #404040;
            color: white;
            border: 1px solid #666666;
            padding: 10px;
            border-radius: 4px;
            font-size: 12px;
        }
        QPushButton:hover {
            background-color: #505050;
        }
        QPushButton:pressed {
            background-color: #303030;
        }
    """)
    
    window = TestWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
