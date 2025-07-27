#!/usr/bin/env python3
"""
简化彩色渐变测试 - 基础功能验证
"""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
import colorsys

def test_basic_gradient():
    """测试基础彩色渐变功能"""
    print("🧪 测试基础彩色渐变功能...")
    
    # 创建测试数据
    times = np.linspace(0, 3, 30)
    pitches = 4.0 + 0.5 * np.sin(2 * np.pi * 0.5 * times)
    
    print(f"📊 测试数据：{len(times)}个点，音域{pitches.min():.2f}-{pitches.max():.2f}")
    
    # 创建图形
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # 创建线段
    points = np.array([times, pitches]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    
    print(f"📈 创建了{len(segments)}个线段")
    
    # 为每个线段计算HSV彩虹色
    colors = []
    for i in range(len(segments)):
        if i+1 < len(pitches):
            mid_pitch = (pitches[i] + pitches[i+1]) / 2
            hue = ((mid_pitch - 1.0) % 6.0) / 6.0
            rgb = colorsys.hsv_to_rgb(hue, 0.95, 1.0)
            colors.append(rgb)
    
    print(f"🎨 生成了{len(colors)}个颜色")
    
    # 创建LineCollection
    if len(colors) > 0:
        line_collection = LineCollection(segments, colors=colors, 
                                       linewidths=2.0, alpha=0.95,
                                       capstyle='round', joinstyle='round')
        ax.add_collection(line_collection)
        print("✅ LineCollection创建成功")
    
    # 添加前端高亮点
    if len(times) > 0:
        latest_time = times[-1]
        latest_pitch = pitches[-1]
        hue = ((latest_pitch - 1.0) % 6.0) / 6.0
        rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        
        ax.scatter([latest_time], [latest_pitch], 
                  s=150, c=[rgb], alpha=1.0, 
                  edgecolors='white', linewidths=2, zorder=20)
        print("✅ 高亮点创建成功")
    
    # 设置坐标轴
    ax.set_xlim(times.min() - 0.1, times.max() + 0.1)
    ax.set_ylim(pitches.min() - 0.2, pitches.max() + 0.2)
    ax.set_xlabel('时间 (秒)')
    ax.set_ylabel('音高')
    ax.set_title('基础彩色渐变测试')
    ax.grid(True, alpha=0.3)
    
    # 显示图形
    plt.tight_layout()
    plt.show()
    
    print("🎯 测试完成！如果看到彩色渐变线条，说明基础功能正常")

if __name__ == "__main__":
    test_basic_gradient()
