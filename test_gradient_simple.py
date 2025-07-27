#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试渐变线条功能
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

def test_gradient_line():
    """测试渐变线条效果"""
    # 创建测试数据
    x = np.linspace(0, 10, 100)
    y = np.sin(x) + 0.1 * np.random.randn(100)
    
    # 创建图形
    fig, ax = plt.subplots(figsize=(12, 6), facecolor='black')
    ax.set_facecolor('black')
    
    # 设置网格
    ax.grid(True, color='#003300', alpha=0.5)
    
    # 渐变线条效果
    n_segments = min(20, len(x)-1)
    segment_length = (len(x)-1) // n_segments
    
    gradient_lines = []
    
    for i in range(n_segments):
        start_idx = i * segment_length
        end_idx = min(start_idx + segment_length + 1, len(x))
        
        if end_idx <= start_idx + 1:
            continue
            
        # 渐变参数
        alpha = 0.3 + 0.7 * (i / max(1, n_segments-1))
        width = 1.0 + 1.5 * (i / max(1, n_segments-1))
        color_intensity = 0.6 + 0.4 * (i / max(1, n_segments-1))
        
        # 绘制线段
        line = Line2D(x[start_idx:end_idx], y[start_idx:end_idx],
                     color=(0, color_intensity, 0),
                     linewidth=width,
                     alpha=alpha,
                     solid_capstyle='round')
        
        ax.add_line(line)
        gradient_lines.append(line)
    
    # 高亮点
    if len(x) > 0:
        highlight = ax.scatter(x[-1], y[-1], 
                              s=80, color='#00FF80', 
                              alpha=0.9, zorder=10)
    
    # 设置样式
    ax.set_xlim(0, 10)
    ax.set_ylim(-2, 2)
    ax.tick_params(colors='white')
    ax.spines['bottom'].set_color('white')
    ax.spines['top'].set_color('white') 
    ax.spines['right'].set_color('white')
    ax.spines['left'].set_color('white')
    
    plt.title('美观渐变线条测试', color='white', fontsize=14)
    plt.tight_layout()
    plt.show()
    
    print("✓ 渐变线条测试完成")

if __name__ == "__main__":
    test_gradient_line()
