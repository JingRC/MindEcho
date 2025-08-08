#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试录音模式的音调检测调试版本
"""

import sys
import os
import time
import threading
import traceback

# 添加src路径
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QTextEdit
from PyQt5.QtCore import QTimer, pyqtSignal, QObject
from gui.integrated_recording_interface import IntegratedAudioProcessor

class DebugRecordingWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.audio_processor = None
        self.pitch_count = 0
        self.debug_timer = None
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("录音音调检测调试")
        self.setGeometry(100, 100, 800, 600)
        
        layout = QVBoxLayout()
        
        # 状态标签
        self.status_label = QLabel("状态: 未开始")
        layout.addWidget(self.status_label)
        
        # 音调信息标签
        self.pitch_label = QLabel("音调: --")
        layout.addWidget(self.pitch_label)
        
        # 统计信息标签
        self.stats_label = QLabel("统计: 检测次数=0")
        layout.addWidget(self.stats_label)
        
        # 按钮
        self.start_btn = QPushButton("开始录音测试")
        self.start_btn.clicked.connect(self.start_recording)
        layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("停止录音")
        self.stop_btn.clicked.connect(self.stop_recording)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)
        
        # 调试日志区域
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(400)
        layout.addWidget(self.log_text)
        
        self.setLayout(layout)
        
        # 启动调试定时器
        self.debug_timer = QTimer()
        self.debug_timer.timeout.connect(self.update_debug_info)
        self.debug_timer.start(1000)  # 每秒更新一次
        
    def start_recording(self):
        try:
            print("🎤 启动录音测试...")
            self.log_text.append("🎤 启动录音测试...")
            
            self.audio_processor = IntegratedAudioProcessor()
            
            # 连接信号
            self.audio_processor.pitch_detected.connect(self.on_pitch_detected)
            self.audio_processor.status_updated.connect(self.on_status_updated)
            self.audio_processor.error_occurred.connect(self.on_error)
            
            # 开始录音（不保存文件，只做实时分析）
            success = self.audio_processor.start_recording(
                filename="debug_test.wav", 
                should_save=False  # 不保存文件，只做实时分析
            )
            
            if success:
                self.start_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
                self.status_label.setText("状态: 录音中...")
                self.log_text.append("✅ 录音启动成功，等待音调检测...")
                
                # 重置计数器
                self.pitch_count = 0
                self.update_stats()
            else:
                self.log_text.append("❌ 录音启动失败")
                
        except Exception as e:
            error_msg = f"❌ 启动错误: {e}\n{traceback.format_exc()}"
            self.log_text.append(error_msg)
            print(error_msg)
            
    def stop_recording(self):
        try:
            if self.audio_processor:
                self.audio_processor.stop_recording()
                self.audio_processor = None
                
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("状态: 已停止")
            self.log_text.append("🛑 录音已停止")
            
            # 显示最终统计
            self.log_text.append(f"📊 最终统计: 总检测次数={self.pitch_count}")
            
        except Exception as e:
            error_msg = f"❌ 停止错误: {e}"
            self.log_text.append(error_msg)
            print(error_msg)
    
    def on_pitch_detected(self, pitch_data):
        """音调检测回调"""
        try:
            self.pitch_count += 1
            frequency = pitch_data.get('frequency', 0)
            confidence = pitch_data.get('confidence', 0)
            has_pitch = pitch_data.get('has_pitch', False)
            note_info = pitch_data.get('note_info', {})
            
            if frequency > 0 and has_pitch:
                note_name = note_info.get('note_name', '?')
                octave = note_info.get('octave', '?')
                
                self.pitch_label.setText(f"音调: {frequency:.1f}Hz ({note_name}{octave})")
                
                # 每5次有效检测记录一次
                if self.pitch_count % 5 == 1:
                    self.log_text.append(f"🎵 检测#{self.pitch_count}: {frequency:.1f}Hz ({note_name}{octave}) - 置信度: {confidence:.2f}")
                    # 自动滚动到底部
                    self.log_text.verticalScrollBar().setValue(
                        self.log_text.verticalScrollBar().maximum()
                    )
            else:
                self.pitch_label.setText("音调: -- (无音调)")
                
            self.update_stats()
                
        except Exception as e:
            self.log_text.append(f"⚠️ 音调处理错误: {e}")
    
    def update_stats(self):
        """更新统计信息"""
        self.stats_label.setText(f"统计: 检测次数={self.pitch_count}")
    
    def update_debug_info(self):
        """更新调试信息"""
        if self.audio_processor:
            try:
                # 检查音频处理线程状态
                is_processing = getattr(self.audio_processor, 'is_audio_processing', False)
                queue_size = self.audio_processor.audio_buffer_queue.qsize() if hasattr(self.audio_processor, 'audio_buffer_queue') else -1
                
                debug_info = f"调试: 处理线程={is_processing}, 队列大小={queue_size}"
                self.status_label.setText(f"状态: 录音中... | {debug_info}")
                
            except Exception as e:
                pass
    
    def on_status_updated(self, status):
        """状态更新回调"""
        self.log_text.append(f"ℹ️ {status}")
        
    def on_error(self, error):
        """错误回调"""
        self.log_text.append(f"❌ 错误: {error}")
        
    def closeEvent(self, event):
        """关闭窗口时清理资源"""
        if self.debug_timer:
            self.debug_timer.stop()
        if self.audio_processor:
            try:
                self.audio_processor.stop_recording()
            except:
                pass
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    print("🚀 启动录音音调检测调试程序...")
    print("📝 使用说明:")
    print("1. 点击'开始录音测试'启动录音和实时音调检测")
    print("2. 对着麦克风说话或唱歌")
    print("3. 观察调试日志中的详细信息")
    print("4. 检查是否有'🎵 检测到音调'的输出")
    print("5. 如果没有检测到音调，查看调试信息找出问题")
    
    window = DebugRecordingWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
