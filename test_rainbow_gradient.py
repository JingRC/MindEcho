#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试真彩色渐变效果 - 验证HSV彩虹渐变实现
"""

import sys
import os
import numpy as np
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from PyQt6.QtWidgets import QApplication
    from src.gui.integrated_recording_interface import IntegratedRecordingInterface
except ImportError:
    try:
        from PyQt5.QtWidgets import QApplication
        from src.gui.integrated_recording_interface import IntegratedRecordingInterface
    except ImportError:
        print("❌ 需要 PyQt5 或 PyQt6")
        sys.exit(1)

def test_rainbow_gradient():
    """测试彩虹渐变效果"""
    print("🌈 启动彩虹渐变测试...")
    
    app = QApplication(sys.argv)
    
    # 创建录音界面
    interface = IntegratedRecordingInterface()
    interface.show()
    
    print("✅ 界面已启动")
    
    # 等待界面完全加载
    app.processEvents()
    time.sleep(1)
    
    # 切换到彩色渐变模式
    print("🎨 切换到彩色渐变模式...")
    try:
        # 找到彩色渐变模式的按钮并点击
        for i in range(interface.mode_combo.count()):
            if "彩色渐变" in interface.mode_combo.itemText(i):
                interface.mode_combo.setCurrentIndex(i)
                print(f"✅ 切换到: {interface.mode_combo.currentText()}")
                break
        
        app.processEvents()
        time.sleep(0.5)
        
        # 生成测试数据 - 跨越多个八度的彩虹色谱
        print("📊 生成彩虹测试数据...")
        duration = 8.0
        sample_rate = 80
        times = np.linspace(0, duration, int(duration * sample_rate))
        
        # 创建跨越1-7八度的彩虹音高序列
        pitches = []
        confidences = []
        
        for i, t in enumerate(times):
            # 主要旋律：缓慢扫过6个八度
            base_pitch = 1.5 + 5.0 * (t / duration)
            
            # 添加颤音细节
            vibrato = 0.2 * np.sin(2 * np.pi * 6 * t)
            
            # 添加快速音高变化
            rapid_change = 0.3 * np.sin(2 * np.pi * 2 * t)
            
            # 组合音高
            pitch = base_pitch + vibrato + rapid_change
            
            # 确保在合理范围内
            pitch = max(1.0, min(7.0, pitch))
            
            pitches.append(pitch)
            confidences.append(0.9)  # 高置信度
        
        print(f"📈 数据范围: {min(pitches):.2f} - {max(pitches):.2f} 八度")
        
        # 模拟实时数据添加
        print("🎵 开始播放彩虹音频...")
        
        # 清空现有数据
        interface.pitch_data.clear()
        interface.time_data.clear()
        interface.confidence_data.clear()
        
        # 批量添加数据以快速看到效果
        chunk_size = 5
        for i in range(0, len(times), chunk_size):
            end_idx = min(i + chunk_size, len(times))
            
            # 添加这一批数据
            for j in range(i, end_idx):
                interface.add_pitch_data(times[j], pitches[j], confidences[j])
            
            # 更新显示
            interface.update_display()
            app.processEvents()
            
            # 短暂延迟以看到渐变效果
            time.sleep(0.05)
            
            # 打印进度
            if i % 50 == 0:
                progress = (i / len(times)) * 100
                current_pitch = pitches[i] if i < len(pitches) else 0
                print(f"🎶 进度: {progress:.1f}% - 当前音高: {current_pitch:.2f}")
        
        print("✅ 彩虹测试数据加载完成！")
        
        # 显示测试结果信息
        print("\n🔍 验证指南:")
        print("  • 检查线条是否显示真正的彩虹色（红橙黄绿青蓝紫）")
        print("  • 音高从低到高应该对应颜色从红色到紫色的变化")
        print("  • 拖尾效果应该呈现渐变透明度")
        print("  • 高亮点应该跟随最新音高显示对应颜色")
        print("  • 线条应该够细以显示颤音细节")
        
        # 等待10秒后切换到心电图模式测试线条粗细
        print("\n⏱️ 10秒后将切换到心电图模式测试线条粗细...")
        start_time = time.time()
        while time.time() - start_time < 10:
            app.processEvents()
            time.sleep(0.1)
        
        # 切换到心电图模式
        print("💚 切换到心电图模式测试线条粗细...")
        for i in range(interface.mode_combo.count()):
            if "心电图" in interface.mode_combo.itemText(i):
                interface.mode_combo.setCurrentIndex(i)
                print(f"✅ 切换到: {interface.mode_combo.currentText()}")
                break
        
        app.processEvents()
        interface.update_display()
        
        print("\n🔍 心电图模式验证:")
        print("  • 线条应该是单色（绿色）")
        print("  • 线条应该足够细（1.0像素）以显示颤音细节")
        print("  • 应该能清楚看到音高的快速变化和颤音")
        
        print("\n✅ 测试完成！程序将保持运行以便您验证效果...")
        print("💡 关闭窗口或按Ctrl+C退出")
        
        # 保持程序运行
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_rainbow_gradient()
