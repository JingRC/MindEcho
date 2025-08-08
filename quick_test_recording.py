#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的录音音调检测测试
"""

import sys
import os
import time

# 添加src路径
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.insert(0, src_path)

def test_recording_pitch_detection():
    """测试录音音调检测功能"""
    try:
        print("🎤 导入音频处理器...")
        from gui.integrated_recording_interface import IntegratedAudioProcessor
        
        print("🎤 创建音频处理器实例...")
        processor = IntegratedAudioProcessor()
        
        pitch_detected_count = 0
        
        def on_pitch_detected(pitch_data):
            nonlocal pitch_detected_count
            pitch_detected_count += 1
            frequency = pitch_data.get('frequency', 0)
            has_pitch = pitch_data.get('has_pitch', False)
            
            if frequency > 0 and has_pitch:
                note_info = pitch_data.get('note_info', {})
                note_name = note_info.get('note_name', '?')
                octave = note_info.get('octave', '?')
                print(f"🎵 检测到音调#{pitch_detected_count}: {frequency:.1f}Hz ({note_name}{octave})")
            else:
                if pitch_detected_count % 20 == 1:  # 每20次显示一次无音调
                    print(f"⏸️ 无音调#{pitch_detected_count}: RMS={pitch_data.get('audio_rms', 0):.4f}")
        
        def on_status_updated(status):
            print(f"ℹ️ 状态: {status}")
        
        def on_error(error):
            print(f"❌ 错误: {error}")
        
        # 连接信号
        processor.pitch_detected.connect(on_pitch_detected)
        processor.status_updated.connect(on_status_updated)
        processor.error_occurred.connect(on_error)
        
        print("🎤 开始录音测试...")
        success = processor.start_recording(filename="test.wav", should_save=False)
        
        if not success:
            print("❌ 录音启动失败")
            return False
        
        print("✅ 录音已启动，请对麦克风说话或唱歌...")
        print("📝 将在10秒后自动停止测试")
        
        # 等待10秒
        for i in range(10):
            time.sleep(1)
            print(f"⏰ 测试进行中... {10-i}秒后停止 (已检测{pitch_detected_count}次)")
        
        print("🛑 停止录音...")
        processor.stop_recording()
        
        print(f"📊 测试完成! 总检测次数: {pitch_detected_count}")
        
        if pitch_detected_count == 0:
            print("❌ 问题确认: 录音时没有音调检测!")
            return False
        else:
            print("✅ 录音音调检测正常工作!")
            return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("🚀 启动录音音调检测测试...")
    
    # 需要QApplication来处理信号
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    
    # 使用定时器运行测试
    from PyQt5.QtCore import QTimer
    timer = QTimer()
    timer.singleShot(100, test_recording_pitch_detection)
    
    # 10秒后退出
    exit_timer = QTimer()
    exit_timer.singleShot(12000, app.quit)
    
    app.exec_()
    print("🏁 测试程序结束")
