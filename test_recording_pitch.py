#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试录音时实时音调线功能
"""

import sys
import os
import time
import threading

# 添加src路径
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QTextEdit
from PyQt5.QtCore import QTimer, pyqtSignal, QObject
from gui.integrated_recording_interface import IntegratedAudioProcessor

class TestRecordingWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.audio_processor = None
        self.pitch_data_log = []
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("录音音调线测试")
        self.setGeometry(100, 100, 600, 400)
        
        layout = QVBoxLayout()
        
        # 状态标签
        self.status_label = QLabel("状态: 未开始")
        layout.addWidget(self.status_label)
        
        # 音调信息标签
        self.pitch_label = QLabel("音调: --")
        layout.addWidget(self.pitch_label)
        
        # 按钮
        self.start_btn = QPushButton("开始录音")
        self.start_btn.clicked.connect(self.start_recording)
        layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("停止录音")
        self.stop_btn.clicked.connect(self.stop_recording)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)
        
        # 日志区域
        self.log_text = QTextEdit()
        layout.addWidget(self.log_text)
        
        self.setLayout(layout)
        
    def start_recording(self):
        try:
            print("🎤 开始录音测试...")
            self.audio_processor = IntegratedAudioProcessor()
            
            # 连接信号
            self.audio_processor.pitch_detected.connect(self.on_pitch_detected)
            self.audio_processor.status_updated.connect(self.on_status_updated)
            self.audio_processor.error_occurred.connect(self.on_error)
            
            # 开始录音（不保存文件，只做实时分析）
            success = self.audio_processor.start_recording(
                filename="test_recording.wav", 
                should_save=False  # 不保存文件，只做实时分析
            )
            
            if success:
                self.start_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
                self.status_label.setText("状态: 录音中...")
                self.log_text.append("✅ 录音开始，等待音调检测...")
            else:
                self.log_text.append("❌ 录音启动失败")
                
        except Exception as e:
            self.log_text.append(f"❌ 启动错误: {e}")
            
    def stop_recording(self):
        try:
            if self.audio_processor:
                self.audio_processor.stop_recording()
                self.audio_processor = None
                
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("状态: 已停止")
            self.log_text.append("🛑 录音已停止")
            
            # 显示统计信息
            if self.pitch_data_log:
                valid_pitches = [p for p in self.pitch_data_log if p['frequency'] > 0]
                self.log_text.append(f"📊 检测统计: 总计{len(self.pitch_data_log)}次，有效音调{len(valid_pitches)}次")
            
        except Exception as e:
            self.log_text.append(f"❌ 停止错误: {e}")
    
    def on_pitch_detected(self, pitch_data):
        """音调检测回调"""
        try:
            frequency = pitch_data.get('frequency', 0)
            confidence = pitch_data.get('confidence', 0)
            note_info = pitch_data.get('note_info', {})
            
            # 记录数据
            self.pitch_data_log.append(pitch_data)
            
            if frequency > 0:
                note_name = note_info.get('note_name', '?')
                octave = note_info.get('octave', '?')
                
                self.pitch_label.setText(f"音调: {frequency:.1f}Hz ({note_name}{octave})")
                
                # 只记录每10次有效检测
                if len([p for p in self.pitch_data_log if p['frequency'] > 0]) % 10 == 1:
                    self.log_text.append(f"🎵 检测到音调: {frequency:.1f}Hz ({note_name}{octave}) - 置信度: {confidence:.2f}")
                    # 自动滚动到底部
                    self.log_text.verticalScrollBar().setValue(
                        self.log_text.verticalScrollBar().maximum()
                    )
            else:
                self.pitch_label.setText("音调: -- (无音调)")
                
        except Exception as e:
            self.log_text.append(f"⚠️ 音调处理错误: {e}")
    
    def on_status_updated(self, status):
        """状态更新回调"""
        self.log_text.append(f"ℹ️ {status}")
        
    def on_error(self, error):
        """错误回调"""
        self.log_text.append(f"❌ 错误: {error}")
        
    def closeEvent(self, event):
        """关闭窗口时清理资源"""
        if self.audio_processor:
            self.audio_processor.stop_recording()
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    print("🚀 启动录音音调线测试程序...")
    window = TestRecordingWindow()
    window.show()
    
    print("📝 使用说明:")
    print("1. 点击'开始录音'开始录音和实时音调检测")
    print("2. 对着麦克风唱歌或说话")
    print("3. 观察窗口中的实时音调显示")
    print("4. 点击'停止录音'结束测试")
    print("5. 如果看到音调检测信息，说明修复成功")
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
