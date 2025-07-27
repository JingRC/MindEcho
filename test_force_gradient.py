#!/usr/bin/env python3
"""
强制测试彩色渐变模式 - 确保完全覆盖绿色线条
"""

import sys
import os
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_force_gradient_mode():
    """强制测试彩色渐变模式"""
    try:
        from src.gui.integrated_recording_interface import IntegratedRecordingInterface
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer
        
        print("🎨 强制彩色渐变模式测试...")
        
        app = QApplication(sys.argv)
        
        # 创建界面
        window = IntegratedRecordingInterface()
        window.show()
        
        # 生成测试数据
        def generate_colorful_test_data():
            """生成多彩测试数据"""
            times = np.linspace(0, 5, 150)  # 5秒，150个点
            
            # 创建跨越多个八度的音高变化，确保彩色效果明显
            pitches = []
            for i, t in enumerate(times):
                # 从C3到C6的大范围变化
                base = 3.0 + 3.0 * (t / 5.0)  # 3.0 -> 6.0 (3个八度)
                
                # 添加波动让颜色变化更明显
                wave = 0.5 * np.sin(2 * np.pi * 2 * t)  # 2Hz波动
                
                final_pitch = base + wave
                pitches.append(final_pitch)
            
            pitches = np.array(pitches)
            confidences = np.ones(len(times)) * 0.95
            
            print(f"📊 生成跨域测试数据：{len(times)}点，音域{pitches.min():.1f}-{pitches.max():.1f}")
            return times, pitches, confidences
        
        # 强制切换到彩色渐变模式
        def force_gradient_mode():
            print("🌈 强制切换到彩色渐变模式...")
            
            # 先切换到心电图模式，再切换回彩色渐变
            window.display_mode.setCurrentText("心电图模式")
            app.processEvents()
            
            # 等待一下再切换到彩色渐变
            QTimer.singleShot(500, switch_to_gradient)
        
        def switch_to_gradient():
            print("✨ 切换到彩色渐变...")
            window.display_mode.setCurrentText("彩色渐变")
            app.processEvents()
            
            # 应用测试数据
            QTimer.singleShot(500, apply_test_data)
        
        def apply_test_data():
            print("📋 应用跨域测试数据...")
            
            test_times, test_pitches, test_confidences = generate_colorful_test_data()
            
            # 清空现有数据
            window.pitch_data_times.clear()
            window.pitch_data_values.clear()
            window.confidence_data.clear()
            
            # 分批添加数据，模拟实时效果
            chunk_size = 10
            
            def add_chunk(start_idx=0):
                if start_idx >= len(test_times):
                    print("✅ 数据应用完成！")
                    show_result_message()
                    return
                
                end_idx = min(start_idx + chunk_size, len(test_times))
                
                # 添加这一批数据
                for i in range(start_idx, end_idx):
                    window.pitch_data_times.append(test_times[i])
                    window.pitch_data_values.append(test_pitches[i])
                    window.confidence_data.append(test_confidences[i])
                
                # 强制更新显示
                window.update_display()
                app.processEvents()
                
                # 继续下一批
                QTimer.singleShot(50, lambda: add_chunk(end_idx))
            
            add_chunk()
        
        def show_result_message():
            print("\n🎯 测试完成！请观察效果：")
            print("✅ 应该看到：0.8px超细彩虹渐变线条")
            print("✅ 应该看到：仅前端一个高亮粒子")
            print("✅ 不应该看到：绿色粗线条")
            print("✅ 颜色应该：从蓝色渐变到红色")
            print("\n如果仍然看到绿色线条，请检查控制台输出...")
        
        # 1秒后开始测试序列
        QTimer.singleShot(1000, force_gradient_mode)
        
        print("🚀 启动强制彩色渐变测试...")
        print("测试序列：")
        print("  1. 初始状态 -> 1秒")
        print("  2. 强制心电图模式 -> 0.5秒")
        print("  3. 切换彩色渐变模式 -> 0.5秒")
        print("  4. 分批应用跨域数据")
        print("  5. 观察彩虹渐变效果")
        
        app.exec()
        
    except Exception as e:
        print(f"❌ 强制测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_force_gradient_mode()
