#!/usr/bin/env python3
"""
调试彩色渐变模式 - 详细错误追踪
"""

import sys
import os
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def debug_gradient_mode():
    """调试彩色渐变模式"""
    try:
        from src.gui.integrated_recording_interface import IntegratedRecordingInterface
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer
        
        print("🔍 调试彩色渐变模式...")
        
        app = QApplication(sys.argv)
        
        # 创建界面
        window = IntegratedRecordingInterface()
        window.show()
        
        # 切换到彩色渐变模式
        print("🎨 切换到彩色渐变模式...")
        window.display_mode.setCurrentText("彩色渐变")
        
        # 生成简单测试数据
        def apply_simple_test_data():
            print("📊 应用简单测试数据...")
            
            # 简单的测试数据
            times = np.linspace(0, 3, 30)  # 3秒，30个点
            pitches = 4.0 + 0.5 * np.sin(2 * np.pi * 0.5 * times)  # C4附近的简单波形
            confidences = np.ones(len(times)) * 0.9
            
            print(f"📋 测试数据：{len(times)}个点，音域{pitches.min():.2f}-{pitches.max():.2f}")
            
            # 清空现有数据
            window.pitch_data_times.clear()
            window.pitch_data_values.clear()
            window.confidence_data.clear()
            
            # 添加数据
            for t, p, c in zip(times, pitches, confidences):
                window.pitch_data_times.append(t)
                window.pitch_data_values.append(p)
                window.confidence_data.append(c)
            
            print("🔄 触发显示更新...")
            window.update_display()
            
            # 检查结果
            QTimer.singleShot(1000, check_result)
        
        def check_result():
            print("\n🔍 检查渐变效果结果：")
            
            # 检查是否有LineCollection
            collections = window.ax.collections
            print(f"📊 当前collections数量: {len(collections)}")
            
            for i, collection in enumerate(collections):
                print(f"  {i+1}. {type(collection).__name__}")
            
            # 检查是否有gradient_lines
            if hasattr(window, 'gradient_lines'):
                print(f"📈 gradient_lines数量: {len(window.gradient_lines)}")
            else:
                print("❌ 没有gradient_lines属性")
            
            # 检查是否有高亮点
            if hasattr(window, 'highlight_point') and window.highlight_point is not None:
                print("✅ 有高亮点")
            else:
                print("❌ 没有高亮点")
            
            # 检查pitch_line状态
            if hasattr(window, 'pitch_line') and window.pitch_line is not None:
                alpha = window.pitch_line.get_alpha()
                color = window.pitch_line.get_color()
                linewidth = window.pitch_line.get_linewidth()
                data = window.pitch_line.get_data()
                print(f"🎯 pitch_line状态: alpha={alpha}, color={color}, linewidth={linewidth}")
                print(f"   数据点数: x={len(data[0])}, y={len(data[1])}")
            
            print("\n💡 如果没有看到彩色线条，请检查上面的调试信息")
        
        # 1秒后应用测试数据
        QTimer.singleShot(1000, apply_simple_test_data)
        
        print("🚀 启动调试测试...")
        print("请观察控制台输出和界面效果")
        
        app.exec()
        
    except Exception as e:
        print(f"❌ 调试测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_gradient_mode()
