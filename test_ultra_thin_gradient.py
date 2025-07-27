#!/usr/bin/env python3
"""
测试超细平滑彩色渐变实现
- 超细线条 (0.8px)
- 平滑插值
- 仅前端粒子
"""

import sys
import os
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_ultra_thin_gradient():
    """测试超细平滑彩色渐变"""
    try:
        from src.gui.integrated_recording_interface import IntegratedRecordingInterface
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer
        
        print("🎨 测试超细平滑彩色渐变...")
        
        app = QApplication(sys.argv)
        
        # 创建界面
        window = IntegratedRecordingInterface()
        window.show()
        
        # 设置为彩色渐变模式
        window.display_mode_combo.setCurrentText("彩色渐变")
        
        # 生成测试数据：包含颤音和滑音效果
        def generate_test_data():
            print("📊 生成包含颤音的测试数据...")
            
            # 时间轴：5秒数据
            times = np.linspace(0, 5, 300)  # 300个数据点，密度高
            
            # 基础音高：从C4到G5的旋律
            base_pitches = []
            for t in times:
                # 主旋律：C4-D4-E4-F4-G4-A4-B4-C5...
                note_progress = (t / 5.0) * 12  # 5秒内12个半音
                base_pitch = 4.0 + note_progress / 12.0  # C4开始
                
                # 添加颤音效果：快速振动
                vibrato_freq = 6.0  # 6Hz颤音
                vibrato_amplitude = 0.05  # 振幅±0.05个半音
                vibrato = vibrato_amplitude * np.sin(2 * np.pi * vibrato_freq * t)
                
                # 添加滑音效果：慢速漂移
                glissando = 0.1 * np.sin(2 * np.pi * 0.5 * t)
                
                final_pitch = base_pitch + vibrato + glissando
                base_pitches.append(final_pitch)
            
            pitches = np.array(base_pitches)
            confidences = np.ones(len(times)) * 0.9  # 高置信度
            
            print(f"✅ 测试数据生成完成：{len(times)}个点，音域{pitches.min():.2f}-{pitches.max():.2f}")
            return times, pitches, confidences
        
        # 生成并应用测试数据
        test_times, test_pitches, test_confidences = generate_test_data()
        
        def update_with_test_data():
            """使用测试数据更新可视化"""
            try:
                print("🔄 应用测试数据到彩色渐变模式...")
                
                # 模拟实时数据累积
                chunk_size = 20
                for i in range(0, len(test_times), chunk_size):
                    end_idx = min(i + chunk_size, len(test_times))
                    
                    current_times = test_times[:end_idx]
                    current_pitches = test_pitches[:end_idx]
                    current_confidences = test_confidences[:end_idx]
                    
                    # 应用到界面
                    window.pitch_data_times = list(current_times)
                    window.pitch_data_values = list(current_pitches)
                    window.confidence_data = list(current_confidences)
                    
                    # 强制更新显示
                    window.update_display()
                    
                    # 处理GUI事件
                    app.processEvents()
                    
                    # 短暂延迟模拟实时效果
                    QTimer.singleShot(50, lambda: None)
                
                print("✅ 超细平滑彩色渐变测试数据应用完成")
                print("🎵 观察效果：")
                print("  • 线条应该非常细腻 (0.8px)")
                print("  • 颜色应该平滑渐变")
                print("  • 只有最前端有一个高亮粒子")
                print("  • 颤音细节应该清晰可见")
                
            except Exception as e:
                print(f"❌ 测试数据应用失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 延迟应用测试数据
        QTimer.singleShot(1000, update_with_test_data)
        
        # 运行应用
        print("🚀 启动测试界面...")
        print("请观察彩色渐变效果的改进：")
        print("  1. 线条是否足够细腻")
        print("  2. 颜色渐变是否平滑")
        print("  3. 是否只有前端单个粒子")
        print("  4. 颤音细节是否清晰")
        
        app.exec()
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请确保已安装 PyQt6/PyQt5 和 matplotlib")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ultra_thin_gradient()
