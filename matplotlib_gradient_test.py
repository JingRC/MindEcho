#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Matplotlib真彩色渐变实现 - 不依赖PyQtGraph
使用LineCollection实现高性能彩色渐变
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import ListedColormap
import colorsys

def create_rainbow_colormap(n_colors=256):
    """创建彩虹色彩映射"""
    colors = []
    for i in range(n_colors):
        hue = i / n_colors
        rgb = colorsys.hsv_to_rgb(hue, 0.9, 1.0)
        colors.append(rgb)
    return ListedColormap(colors)

def create_color_gradient_line(times, pitches, confidences=None):
    """创建彩色渐变线条 - 使用LineCollection"""
    if len(times) < 2:
        return None
    
    # 创建线段点
    points = np.array([times, pitches]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    
    # 根据音高计算颜色
    colors = []
    for i in range(len(segments)):
        # 使用线段中点的音高
        mid_pitch = (pitches[i] + pitches[i+1]) / 2
        
        # 音高映射到HSV色相 (1-7八度 -> 0-1色相)
        hue = ((mid_pitch - 1.0) % 6.0) / 6.0
        
        # 置信度影响饱和度
        if confidences is not None:
            confidence = (confidences[i] + confidences[i+1]) / 2
            saturation = 0.7 + 0.3 * confidence
        else:
            saturation = 0.9
        
        # 固定高亮度
        value = 1.0
        
        # HSV转RGB
        rgb = colorsys.hsv_to_rgb(hue, saturation, value)
        colors.append(rgb)
    
    # 创建LineCollection
    line_collection = LineCollection(segments, colors=colors, linewidths=2.0, alpha=0.8)
    
    return line_collection

def test_matplotlib_gradient():
    """测试Matplotlib彩色渐变"""
    print("🎨 测试Matplotlib真彩色渐变...")
    
    # 生成测试数据
    duration = 8.0
    sample_rate = 100
    times = np.linspace(0, duration, int(duration * sample_rate))
    
    # 创建跨越多个八度的音高数据
    base_pitch = 2.0 + 3.0 * (times / duration)  # 从2到5八度
    vibrato = 0.3 * np.sin(2 * np.pi * 6 * times)  # 颤音
    melody = 0.5 * np.sin(2 * np.pi * 0.5 * times)  # 旋律变化
    
    pitches = base_pitch + vibrato + melody
    confidences = 0.8 + 0.2 * np.random.random(len(times))
    
    # 创建图形
    plt.style.use('dark_background')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10))
    fig.suptitle('Matplotlib 真彩色渐变测试', fontsize=16, color='white')
    
    # 方法1：LineCollection彩色渐变
    ax1.set_title('方法1: LineCollection彩色渐变', color='white')
    line_collection = create_color_gradient_line(times, pitches, confidences)
    if line_collection is not None:
        ax1.add_collection(line_collection)
    ax1.set_xlim(times[0], times[-1])
    ax1.set_ylim(np.min(pitches)-0.5, np.max(pitches)+0.5)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylabel('音高 (八度)', color='white')
    
    # 方法2：分段彩色线条
    ax2.set_title('方法2: 分段彩色线条', color='white')
    num_segments = 30
    for i in range(num_segments):
        start_idx = int(i * len(times) / num_segments)
        end_idx = int((i + 1) * len(times) / num_segments)
        
        if start_idx >= len(times) or end_idx > len(times):
            continue
        
        segment_times = times[start_idx:end_idx]
        segment_pitches = pitches[start_idx:end_idx]
        
        if len(segment_pitches) < 2:
            continue
        
        # 计算颜色
        avg_pitch = np.mean(segment_pitches)
        hue = ((avg_pitch - 1.0) % 6.0) / 6.0
        rgb = colorsys.hsv_to_rgb(hue, 0.9, 1.0)
        
        # 绘制线段
        ax2.plot(segment_times, segment_pitches, color=rgb, linewidth=2.0, alpha=0.8)
    
    ax2.set_xlim(times[0], times[-1])
    ax2.set_ylim(np.min(pitches)-0.5, np.max(pitches)+0.5)
    ax2.grid(True, alpha=0.3)
    ax2.set_ylabel('音高 (八度)', color='white')
    
    # 方法3：散点+线条组合
    ax3.set_title('方法3: 彩色散点 + 线条', color='white')
    
    # 基础线条
    ax3.plot(times, pitches, color='gray', linewidth=1.0, alpha=0.5, zorder=1)
    
    # 彩色散点
    step = max(1, len(times) // 100)
    for i in range(0, len(times), step):
        hue = ((pitches[i] - 1.0) % 6.0) / 6.0
        rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        size = 20 + 30 * confidences[i]
        
        ax3.scatter(times[i], pitches[i], c=[rgb], s=size, alpha=0.8, zorder=2)
    
    ax3.set_xlim(times[0], times[-1])
    ax3.set_ylim(np.min(pitches)-0.5, np.max(pitches)+0.5)
    ax3.grid(True, alpha=0.3)
    ax3.set_ylabel('音高 (八度)', color='white')
    ax3.set_xlabel('时间 (秒)', color='white')
    
    plt.tight_layout()
    plt.show()
    
    print("✅ Matplotlib彩色渐变测试完成!")
    print("💡 观察要点:")
    print("  • 方法1: LineCollection - 性能最佳，渐变最平滑")
    print("  • 方法2: 分段线条 - 兼容性好，效果明显") 
    print("  • 方法3: 散点组合 - 颗粒感强，适合动态效果")
    
    return True

if __name__ == "__main__":
    test_matplotlib_gradient()
