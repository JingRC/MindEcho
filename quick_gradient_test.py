#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化测试：PyQtGraph高性能渐变vs增强Matplotlib
"""

import sys
import os
import numpy as np
import colorsys
import time

# 检查PyQtGraph
PYQTGRAPH_AVAILABLE = False
try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
    print("✅ PyQtGraph 检测成功！")
except ImportError:
    print("❌ PyQtGraph 未安装")

# 检查Qt
try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    print("✅ PyQt6 可用")
except ImportError:
    try:
        from PyQt5.QtWidgets import *
        from PyQt5.QtCore import *
        from PyQt5.QtGui import *
        print("✅ PyQt5 可用")
    except ImportError:
        print("❌ 需要 PyQt5 或 PyQt6")
        sys.exit(1)

def test_pyqtgraph_gradient():
    """测试PyQtGraph彩色渐变"""
    if not PYQTGRAPH_AVAILABLE:
        print("⚠️ PyQtGraph不可用，跳过测试")
        return False
    
    try:
        app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
        
        # 设置PyQtGraph
        pg.setConfigOption('background', '#1a1a1a')
        pg.setConfigOption('foreground', '#ffffff')
        pg.setConfigOption('antialias', True)
        
        # 创建窗口
        widget = QWidget()
        widget.setWindowTitle("PyQtGraph 彩色渐变测试")
        widget.setGeometry(100, 100, 1200, 800)
        
        layout = QVBoxLayout(widget)
        
        # 创建绘图区域
        plot_widget = pg.PlotWidget()
        plot_widget.setLabel('left', '音高 (八度)', color='#ffffff')
        plot_widget.setLabel('bottom', '时间 (秒)', color='#ffffff')
        plot_widget.showGrid(x=True, y=True, alpha=0.3)
        plot_widget.setYRange(1, 7)
        
        layout.addWidget(plot_widget)
        
        # 生成测试数据
        duration = 8.0
        sample_rate = 100
        times = np.linspace(0, duration, int(duration * sample_rate))
        
        # 多层次渐变数据
        base_pitch = 3.5
        melody = 1.2 * np.sin(2 * np.pi * 0.3 * times)
        vibrato = 0.2 * np.sin(2 * np.pi * 8 * times)
        pitches = base_pitch + melody + vibrato
        
        # 清空并开始绘制彩色渐变
        plot_widget.clear()
        
        print("🎨 开始绘制PyQtGraph彩色渐变...")
        
        # 分段绘制，每段不同颜色
        num_segments = 50
        for i in range(num_segments):
            start_idx = int(i * len(times) / num_segments)
            end_idx = int((i + 1) * len(times) / num_segments)
            
            if start_idx >= len(times) or end_idx > len(times):
                continue
            
            segment_times = times[start_idx:end_idx]
            segment_pitches = pitches[start_idx:end_idx]
            
            if len(segment_pitches) < 2:
                continue
            
            # 计算HSV彩虹色
            hue = i / num_segments
            rgb = colorsys.hsv_to_rgb(hue, 0.9, 1.0)
            color = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            
            # 动态线宽
            width = 2.0 + 2.0 * (i / num_segments)
            
            # 绘制线段
            pen = pg.mkPen(color=color, width=width)
            plot_widget.plot(segment_times, segment_pitches, pen=pen)
        
        # 添加高亮粒子
        particle_indices = np.arange(0, len(times), 10)
        for idx in particle_indices:
            if idx >= len(times):
                continue
            
            hue = (idx / len(times))
            rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            color = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            
            plot_widget.plot([times[idx]], [pitches[idx]],
                           pen=None, symbol='o', symbolSize=6,
                           symbolBrush=color, symbolPen=None)
        
        print("✅ PyQtGraph彩色渐变绘制完成！")
        
        # 状态标签
        status_label = QLabel("✅ PyQtGraph硬件加速彩色渐变 - 真正的彩虹效果！")
        status_label.setStyleSheet("color: #00FF44; font-size: 16px; font-weight: bold; padding: 10px;")
        layout.addWidget(status_label)
        
        widget.show()
        
        print("\n🌈 PyQtGraph测试说明:")
        print("  • 每个线段都有不同的HSV彩虹色")
        print("  • 线宽动态变化增强视觉效果")
        print("  • 粒子点增加渐变细节")
        print("  • 硬件加速渲染，性能优异")
        
        return True
        
    except Exception as e:
        print(f"❌ PyQtGraph测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_enhanced_matplotlib():
    """测试增强的Matplotlib"""
    try:
        print("\n📊 开始增强Matplotlib测试...")
        
        import matplotlib
        matplotlib.use('Qt5Agg')
        import matplotlib.pyplot as plt
        from matplotlib.collections import LineCollection
        import matplotlib.cm as cm
        
        # 创建数据
        duration = 6.0
        sample_rate = 80
        times = np.linspace(0, duration, int(duration * sample_rate))
        
        base_pitch = 3.5
        melody = 1.0 * np.sin(2 * np.pi * 0.4 * times)
        vibrato = 0.15 * np.sin(2 * np.pi * 7 * times)
        pitches = base_pitch + melody + vibrato
        
        # 设置图形
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(12, 8))
        fig.patch.set_facecolor('#1a1a1a')
        ax.set_facecolor('#1a1a1a')
        
        ax.set_xlabel('时间 (秒)', color='white', fontsize=14)
        ax.set_ylabel('音高 (八度)', color='white', fontsize=14)
        ax.set_title('Enhanced Matplotlib 彩色渐变测试', color='#00FF44', fontsize=16, fontweight='bold')
        ax.grid(True, alpha=0.3, color='white')
        
        # 方法1：LineCollection真彩色渐变
        points = np.array([times, pitches]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        
        # 创建HSV彩色映射
        colors = []
        for i in range(len(segments)):
            hue = (i / len(segments))
            rgb = colorsys.hsv_to_rgb(hue, 0.9, 1.0)
            colors.append(rgb)
        
        # 创建LineCollection
        lc = LineCollection(segments, colors=colors, linewidths=2.0, alpha=0.8)
        ax.add_collection(lc)
        
        # 方法2：散点图增强
        scatter_indices = np.arange(0, len(times), 3)
        scatter_times = times[scatter_indices]
        scatter_pitches = pitches[scatter_indices]
        
        scatter_colors = []
        for i in scatter_indices:
            hue = (i / len(times))
            rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            scatter_colors.append(rgb)
        
        ax.scatter(scatter_times, scatter_pitches, c=scatter_colors, s=20, alpha=0.7, edgecolors='white', linewidths=0.5)
        
        # 设置范围
        ax.set_xlim(0, duration)
        ax.set_ylim(1, 7)
        
        # 添加说明文字
        ax.text(0.02, 0.98, '✅ Enhanced Matplotlib\n真彩色渐变 + 散点增强', 
                transform=ax.transAxes, fontsize=12, color='#00FF44',
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='black', alpha=0.7))
        
        plt.tight_layout()
        plt.show()
        
        print("✅ Enhanced Matplotlib彩色渐变测试完成！")
        print("  • LineCollection实现真彩色渐变")
        print("  • HSV色彩空间完整映射")
        print("  • 散点图增强细节显示")
        
        return True
        
    except Exception as e:
        print(f"❌ Enhanced Matplotlib测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🚀 MindEcho 彩色渐变方案对比测试")
    print("=" * 60)
    
    app = QApplication(sys.argv)
    
    success_count = 0
    
    # 测试PyQtGraph方案
    print("\n🎯 测试方案二：PyQtGraph硬件加速")
    if test_pyqtgraph_gradient():
        success_count += 1
        print("✅ PyQtGraph方案测试成功")
    else:
        print("❌ PyQtGraph方案测试失败")
    
    # 等待一下
    time.sleep(2)
    
    # 测试增强Matplotlib方案
    print("\n🎯 测试方案一：Enhanced Matplotlib")
    if test_enhanced_matplotlib():
        success_count += 1
        print("✅ Enhanced Matplotlib方案测试成功")
    else:
        print("❌ Enhanced Matplotlib方案测试失败")
    
    print(f"\n📊 测试结果总结：")
    print(f"  • 成功方案数: {success_count}/2")
    print(f"  • PyQtGraph可用: {'是' if PYQTGRAPH_AVAILABLE else '否'}")
    
    if success_count > 0:
        print(f"\n💡 推荐使用：")
        if PYQTGRAPH_AVAILABLE:
            print("  🚀 PyQtGraph方案 - 硬件加速，性能最佳")
        else:
            print("  📊 Enhanced Matplotlib方案 - 兼容性好，效果优秀")
    
    print(f"\n🎨 彩色渐变效果验证：")
    print(f"  • 线条是否显示彩虹渐变色？")
    print(f"  • 心电图模式线条是否足够细？")
    print(f"  • 渐变过渡是否平滑？")
    
    if success_count > 0 and PYQTGRAPH_AVAILABLE:
        # 只有当PyQtGraph成功时才启动事件循环
        sys.exit(app.exec())

if __name__ == "__main__":
    main()
