#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试绿色音高线条显示问题
"""

import sys
import time
import math
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_green_line():
    """测试绿色线条显示"""
    print("🎯 测试绿色音高线条显示")
    print("=" * 50)
    
    try:
        # 导入GUI模块
        from PyQt6.QtWidgets import QApplication
        from src.gui.integrated_recording_interface import ECGStylePitchVisualizer
        
        print("✅ 模块导入成功")
        
        # 创建应用
        app = QApplication(sys.argv)
        
        # 创建可视化器
        visualizer = ECGStylePitchVisualizer()
        visualizer.show()
        
        print("✅ 可视化器创建成功")
        
        # 模拟音高数据
        print("\n📊 开始添加模拟音高数据...")
        
        # 生成一些测试音高数据
        for i in range(50):
            # 模拟A4(440Hz)到C5(523Hz)的音高变化
            frequency = 440 + 80 * math.sin(i * 0.2)  # 频率在440-520Hz之间变化
            
            pitch_data = {
                'frequency': frequency,
                'confidence': 0.8,
                'timestamp': time.time(),
                'note_info': {
                    'note_name': 'A' if frequency < 480 else 'B',
                    'octave': 4,
                    'cents': 0
                }
            }
            
            visualizer.add_pitch_data(pitch_data)
            
            if i % 10 == 0:
                print(f"  添加数据点 {i+1}/50, 频率: {frequency:.1f}Hz")
            
            # 短暂延迟模拟实时数据
            QApplication.processEvents()
            time.sleep(0.1)
        
        print("\n✅ 数据添加完成")
        print(f"📈 总数据点: {len(visualizer.pitch_data)}")
        print(f"🎵 时间范围: {len(visualizer.time_data)}点")
        
        # 检查线条状态
        if hasattr(visualizer, 'pitch_line'):
            line_data = visualizer.pitch_line.get_data()
            print(f"📏 线条数据: X轴{len(line_data[0])}点, Y轴{len(line_data[1])}点")
            print(f"🎨 线条颜色: {visualizer.pitch_line.get_color()}")
            print(f"📐 线条宽度: {visualizer.pitch_line.get_linewidth()}")
            print(f"👁️ 线条透明度: {visualizer.pitch_line.get_alpha()}")
        else:
            print("❌ pitch_line不存在")
        
        print("\n🖼️ 强制更新显示...")
        visualizer.update_display()
        visualizer.canvas.draw()
        
        print("\n✨ 如果看到绿色线条，说明修复成功！")
        print("📝 如果没有绿色线条，请检查:")
        print("  1. 数据是否正确添加到pitch_data和time_data")
        print("  2. pitch_line是否被ax.clear()误删")
        print("  3. 线条的zorder是否足够高")
        print("  4. 坐标轴范围是否正确")
        
        # 运行应用
        app.exec()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    test_green_line()

if __name__ == "__main__":
    main()
