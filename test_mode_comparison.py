#!/usr/bin/env python3
"""
对比测试：彩色渐变模式 vs 心电图模式
展示线条粗细和效果差异
"""

import sys
import os
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_mode_comparison():
    """对比测试两种模式"""
    try:
        from src.gui.integrated_recording_interface import IntegratedRecordingInterface
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from PyQt6.QtCore import QTimer
        
        print("🎭 模式对比测试...")
        
        app = QApplication(sys.argv)
        
        # 创建界面
        window = IntegratedRecordingInterface()
        window.show()
        
        # 生成测试数据
        def generate_vibrato_data():
            """生成包含颤音的测试数据"""
            times = np.linspace(0, 3, 200)  # 3秒，200个点
            
            # 基础音高：C4到G4
            base_pitches = 4.0 + 0.5 * times / 3.0
            
            # 添加颤音
            vibrato = 0.08 * np.sin(2 * np.pi * 7 * times)  # 7Hz颤音
            
            pitches = base_pitches + vibrato
            confidences = np.ones(len(times)) * 0.9
            
            return times, pitches, confidences
        
        test_times, test_pitches, test_confidences = generate_vibrato_data()
        
        def apply_test_data():
            """应用测试数据"""
            window.pitch_data_times = list(test_times)
            window.pitch_data_values = list(test_pitches)
            window.confidence_data = list(test_confidences)
            window.update_display()
        
        def switch_to_gradient():
            """切换到彩色渐变模式"""
            print("🌈 切换到彩色渐变模式 (0.8px 彩虹线条 + 前端粒子)")
            window.display_mode_combo.setCurrentText("彩色渐变")
            apply_test_data()
            
            # 5秒后切换到心电图模式
            QTimer.singleShot(5000, switch_to_ecg)
        
        def switch_to_ecg():
            """切换到心电图模式"""
            print("💚 切换到心电图模式 (0.6px 极细绿线)")
            window.display_mode_combo.setCurrentText("心电图")
            apply_test_data()
            
            # 显示对比说明
            QTimer.singleShot(1000, show_comparison_info)
        
        def show_comparison_info():
            """显示对比信息"""
            msg = QMessageBox()
            msg.setWindowTitle("模式对比测试")
            msg.setText("""
🎭 两种模式对比结果：

🌈 彩色渐变模式：
  • 线条粗细：0.8px
  • 颜色：HSV彩虹渐变
  • 效果：前端高亮粒子
  • 平滑度：插值增强

💚 心电图模式：
  • 线条粗细：0.6px (更细)
  • 颜色：纯绿色
  • 效果：无粒子
  • 专注：颤音细节

观察到差异了吗？
            """)
            msg.exec()
        
        # 应用初始数据
        apply_test_data()
        
        # 开始测试序列
        QTimer.singleShot(1000, switch_to_gradient)
        
        print("🚀 启动对比测试...")
        print("测试序列：")
        print("  1. 初始状态 -> 1秒")
        print("  2. 彩色渐变模式 -> 5秒")
        print("  3. 心电图模式 -> 观察")
        print("  4. 显示对比信息")
        
        app.exec()
        
    except Exception as e:
        print(f"❌ 对比测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_mode_comparison()
