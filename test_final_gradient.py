#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试最终的LineCollection彩色渐变实现
验证集成到主界面中的效果
"""

import sys
import os
import numpy as np
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_final_gradient():
    """测试最终的彩色渐变实现"""
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            print("❌ 需要安装 PyQt5 或 PyQt6")
            return False
    
    try:
        from src.gui.integrated_recording_interface import IntegratedRecordingInterface
        import numpy as np
        
        print("🌈 启动最终彩色渐变测试...")
        
        app = QApplication(sys.argv)
        
        # 创建主界面
        interface = IntegratedRecordingInterface()
        interface.show()
        
        print("✅ 主界面已启动")
        
        # 等待界面完全加载
        app.processEvents()
        time.sleep(1)
        
        # 生成彩虹测试数据
        print("🎵 生成彩虹测试数据...")
        duration = 6.0
        sample_rate = 60
        times = np.linspace(0, duration, int(duration * sample_rate))
        
        # 跨越多个八度的彩虹音高序列
        pitches = 2.0 + 4.0 * (times / duration) + 0.2 * np.sin(2 * np.pi * 3 * times)
        confidences = 0.8 + 0.2 * np.random.random(len(times))
        
        print(f"📊 数据范围: {min(pitches):.2f} - {max(pitches):.2f} 八度")
        
        # 切换到彩色渐变模式
        print("🎨 切换到彩色渐变模式...")
        try:
            # 找到彩色渐变模式的按钮并点击
            for i in range(interface.visualizer.display_mode.count()):
                item_text = interface.visualizer.display_mode.itemText(i)
                if "彩色渐变" in item_text:
                    interface.visualizer.display_mode.setCurrentIndex(i)
                    print(f"✅ 切换到: {item_text}")
                    break
            
            app.processEvents()
            time.sleep(0.5)
            
            # 清空现有数据
            interface.visualizer.pitch_data.clear()
            interface.visualizer.time_data.clear()
            interface.visualizer.confidence_data.clear()
            
            # 批量添加数据
            print("🎶 添加彩虹测试数据...")
            for t, p, c in zip(times, pitches, confidences):
                interface.visualizer.add_pitch_data(t, p, c)
            
            # 强制更新显示
            interface.visualizer.update_display()
            app.processEvents()
            
            print("✅ 彩虹测试数据加载完成！")
            
            # 等待5秒后切换到心电图模式对比
            print("\n⏱️ 5秒后将切换到心电图模式对比效果...")
            start_time = time.time()
            while time.time() - start_time < 5:
                app.processEvents()
                time.sleep(0.1)
            
            # 切换到心电图模式
            print("💚 切换到心电图模式对比...")
            for i in range(interface.visualizer.display_mode.count()):
                item_text = interface.visualizer.display_mode.itemText(i)
                if "心电图" in item_text:
                    interface.visualizer.display_mode.setCurrentIndex(i)
                    print(f"✅ 切换到: {item_text}")
                    break
            
            app.processEvents()
            interface.visualizer.update_display()
            
            print("\n🔍 验证指南:")
            print("  ✅ 彩色渐变模式:")
            print("    • 应显示LineCollection真彩色渐变线条")
            print("    • 音高低到高对应红到紫的彩虹色变化")
            print("    • 彩色粒子散点增强效果")
            print("    • 彩色高亮点跟随最新位置")
            print("  ✅ 心电图模式:")
            print("    • 应显示单色绿色细线条")
            print("    • 线条宽度1.0像素，颤音细节清晰")
            print("    • 无彩色渐变效果")
            
            print("\n✅ 测试完成！您可以在两种模式间切换对比效果")
            print("💡 关闭窗口或按Ctrl+C退出")
            
            # 保持程序运行
            sys.exit(app.exec())
            
        except Exception as e:
            print(f"❌ 测试过程中出错: {e}")
            import traceback
            traceback.print_exc()
            
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 启动错误: {e}")
        return False

if __name__ == "__main__":
    test_final_gradient()
