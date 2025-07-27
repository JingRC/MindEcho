#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
线条显示修复验证脚本
"""

import sys
import os
import time
import numpy as np

# 添加源码路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def generate_test_data():
    """生成测试数据，包含颤音效果"""
    # 生成5秒的数据，模拟颤音
    duration = 5.0
    sample_rate = 60  # 60fps
    times = np.linspace(0, duration, int(duration * sample_rate))
    
    # 基础音高（C4附近）
    base_pitch = 4.0
    
    # 添加颤音效果（快速的小幅度振动）
    vibrato_freq = 6.0  # 6Hz颤音
    vibrato_depth = 0.1  # 颤音深度
    vibrato = vibrato_depth * np.sin(2 * np.pi * vibrato_freq * times)
    
    # 添加主旋律变化
    melody = 0.5 * np.sin(2 * np.pi * 0.3 * times)  # 缓慢的主旋律
    
    # 组合音高数据
    pitches = base_pitch + melody + vibrato
    
    # 置信度
    confidences = np.ones_like(times) * 0.8
    
    return times.tolist(), pitches.tolist(), confidences.tolist()

def test_line_display():
    """测试线条显示修复效果"""
    try:
        print("🔧 启动线条显示修复验证...")
        
        # 导入模块
        from src.gui.integrated_recording_interface import ECGStylePitchVisualizer
        from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget, QLabel, QPushButton, QHBoxLayout
        from PyQt6.QtCore import QTimer
        
        # 创建应用程序
        app = QApplication(sys.argv)
        
        # 创建主窗口
        window = QWidget()
        window.setWindowTitle("线条显示修复验证 - MindEcho")
        window.setGeometry(100, 100, 1200, 800)
        
        layout = QVBoxLayout(window)
        
        # 添加说明标签
        info_label = QLabel("""
🎵 线条显示修复验证测试

📋 测试内容:
• 心电图模式: 线条宽度从 1.5像素 → 1.0像素，提高颤音细节清晰度
• 彩色渐变模式: 增强可见性，修复线条不显示问题

💡 测试方法:
1. 自动加载包含颤音的测试数据
2. 切换显示模式观察线条效果
3. 观察控制台的调试信息

🔍 重点观察:
• 心电图模式中颤音的细节是否更清晰
• 彩色渐变模式中是否能看到彩色的渐变线条
        """)
        info_label.setStyleSheet("font-family: monospace; font-size: 11px; padding: 10px; background-color: #f0f0f0;")
        layout.addWidget(info_label)
        
        # 添加控制按钮
        button_layout = QHBoxLayout()
        
        load_test_data_btn = QPushButton("加载颤音测试数据")
        load_test_data_btn.setStyleSheet("padding: 10px; font-weight: bold; background-color: #4CAF50; color: white;")
        button_layout.addWidget(load_test_data_btn)
        
        clear_data_btn = QPushButton("清除数据")
        clear_data_btn.setStyleSheet("padding: 10px; font-weight: bold; background-color: #f44336; color: white;")
        button_layout.addWidget(clear_data_btn)
        
        layout.addLayout(button_layout)
        
        # 创建可视化器
        visualizer = ECGStylePitchVisualizer()
        layout.addWidget(visualizer)
        
        # 状态标签
        status_label = QLabel("状态: 就绪")
        status_label.setStyleSheet("padding: 5px; font-weight: bold;")
        layout.addWidget(status_label)
        
        def load_test_data():
            """加载测试数据"""
            try:
                status_label.setText("状态: 正在加载颤音测试数据...")
                print("🎼 生成包含颤音的测试数据...")
                
                times, pitches, confidences = generate_test_data()
                
                print(f"📊 生成数据: {len(times)}个点，时长{times[-1]:.1f}秒")
                
                # 清除旧数据
                visualizer.clear_data()
                
                # 逐步添加数据（模拟实时输入）
                def add_data_gradually():
                    current_idx = 0
                    
                    def add_next_batch():
                        nonlocal current_idx
                        
                        # 每次添加10个点
                        batch_size = 10
                        end_idx = min(current_idx + batch_size, len(times))
                        
                        for i in range(current_idx, end_idx):
                            pitch_data = {
                                'time': times[i],
                                'pitch': pitches[i],
                                'frequency': 440 * (2 ** (pitches[i] - 4.75)),  # A4 = 440Hz
                                'confidence': confidences[i],
                                'note_info': {
                                    'note_name': 'C',
                                    'octave': int(pitches[i]),
                                    'cents': int((pitches[i] - int(pitches[i])) * 100)
                                }
                            }
                            visualizer.add_pitch_data(pitch_data)
                        
                        current_idx = end_idx
                        
                        if current_idx < len(times):
                            # 继续添加
                            status_label.setText(f"状态: 加载进度 {current_idx}/{len(times)} ({current_idx/len(times)*100:.1f}%)")
                            QTimer.singleShot(50, add_next_batch)  # 50ms后添加下一批
                        else:
                            status_label.setText("状态: 测试数据加载完成！请切换显示模式观察效果")
                            print("✅ 测试数据加载完成")
                            print("💡 请在可视化器中切换显示模式：")
                            print("   • 心电图模式 - 观察颤音细节的清晰度")
                            print("   • 彩色渐变 - 观察渐变线条是否正常显示")
                    
                    add_next_batch()
                
                add_data_gradually()
                
            except Exception as e:
                status_label.setText(f"状态: 加载失败 - {e}")
                print(f"❌ 加载测试数据失败: {e}")
                import traceback
                traceback.print_exc()
        
        def clear_data():
            """清除数据"""
            visualizer.clear_data()
            status_label.setText("状态: 数据已清除")
            print("🗑️ 数据已清除")
        
        # 连接按钮事件
        load_test_data_btn.clicked.connect(load_test_data)
        clear_data_btn.clicked.connect(clear_data)
        
        # 显示窗口
        window.show()
        
        print("✅ 测试界面启动成功")
        print("🎯 当前修复内容:")
        print("   1. 心电图模式线条宽度: 1.5px → 1.0px")
        print("   2. 彩色渐变模式: 增强可见性和调试信息")
        print("🚀 点击'加载颤音测试数据'开始测试")
        
        # 运行应用程序
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ 测试启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_line_display()
