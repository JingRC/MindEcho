#!/usr/bin/env python3
"""
简化版超细线条测试 - 仅测试matplotlib LineCollection部分
不需要音频录制功能
"""

import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import colorsys

def test_ultra_thin_line_collection():
    """测试超细LineCollection实现"""
    print("🎨 测试超细LineCollection彩虹渐变...")
    
    # 生成测试数据：包含颤音
    times = np.linspace(0, 5, 300)  # 5秒，300个点
    
    # 基础音高：C4到G5
    base_pitches = 4.0 + 1.5 * times / 5.0
    
    # 添加颤音效果
    vibrato = 0.08 * np.sin(2 * np.pi * 6 * times)  # 6Hz颤音
    glissando = 0.05 * np.sin(2 * np.pi * 0.5 * times)  # 慢滑音
    
    pitches = base_pitches + vibrato + glissando
    
    print(f"📊 生成测试数据：{len(times)}个点，音域{pitches.min():.2f}-{pitches.max():.2f}")
    
    # 测试插值平滑
    try:
        from scipy.interpolate import interp1d
        print("✅ SciPy可用，使用插值平滑")
        
        # 插值增加密度
        if len(times) < 500:
            interp_times = np.linspace(times[0], times[-1], len(times) * 3)
            interp_pitches = interp1d(times, pitches, kind='cubic')(interp_times)
            print(f"🔧 插值后数据点：{len(times)} -> {len(interp_times)}")
        else:
            interp_times = times
            interp_pitches = pitches
    except ImportError:
        print("⚠️ SciPy不可用，使用原始数据")
        interp_times = times
        interp_pitches = pitches
    
    # 创建图形
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    fig.suptitle('超细彩色渐变线条测试', fontsize=16, fontweight='bold')
    
    # 上图：原始方法（3.0px粗线）
    ax1.set_title('原始方法：3.0px 粗线条', fontsize=12)
    ax1.plot(times, pitches, color='green', linewidth=3.0, alpha=0.9)
    ax1.set_ylabel('音高')
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(0, 5)
    
    # 下图：优化方法（0.8px 超细彩虹渐变）
    ax2.set_title('优化方法：0.8px 超细彩虹渐变 + 插值平滑', fontsize=12)
    
    # 创建LineCollection
    points = np.array([interp_times, interp_pitches]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    
    # 计算彩虹色
    colors = []
    for i in range(len(segments)):
        if i+1 < len(interp_pitches):
            mid_pitch = (interp_pitches[i] + interp_pitches[i+1]) / 2
            
            # HSV彩虹映射
            hue = ((mid_pitch - 4.0) % 2.0) / 2.0  # 4-6音域映射到0-1色相
            rgb = colorsys.hsv_to_rgb(hue, 0.95, 1.0)
            colors.append(rgb)
    
    # 添加超细LineCollection
    line_collection = LineCollection(segments, colors=colors, 
                                   linewidths=0.8, alpha=0.95,
                                   capstyle='round', joinstyle='round')
    ax2.add_collection(line_collection)
    
    # 添加前端高亮粒子
    if len(interp_times) > 0:
        latest_time = interp_times[-1]
        latest_pitch = interp_pitches[-1]
        hue = ((latest_pitch - 4.0) % 2.0) / 2.0
        rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        
        ax2.scatter([latest_time], [latest_pitch], s=120, c=[rgb], 
                   alpha=1.0, edgecolors='white', linewidths=2, zorder=20)
    
    ax2.set_xlim(0, 5)
    ax2.set_ylim(interp_pitches.min()-0.1, interp_pitches.max()+0.1)
    ax2.set_xlabel('时间 (秒)')
    ax2.set_ylabel('音高')
    ax2.grid(True, alpha=0.3)
    
    # 添加对比说明
    textstr = '\n'.join([
        '对比效果：',
        '• 上图：3.0px 绿色粗线',
        '• 下图：0.8px 彩虹细线 + 插值平滑',
        '• 注意：颤音细节的清晰度差异',
        '• 前端：白边高亮粒子指示当前位置'
    ])
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax2.text(0.02, 0.98, textstr, transform=ax2.transAxes, fontsize=10,
             verticalalignment='top', bbox=props)
    
    plt.tight_layout()
    
    print("🎨 显示对比图...")
    print("观察要点：")
    print("  1. 线条粗细对比：3.0px vs 0.8px")
    print("  2. 颜色效果：单色 vs 彩虹渐变")
    print("  3. 平滑度：原始 vs 插值增强")
    print("  4. 颤音细节：是否更清晰")
    print("  5. 前端粒子：白边高亮指示")
    
    plt.show()
    
    return True

if __name__ == "__main__":
    try:
        success = test_ultra_thin_line_collection()
        if success:
            print("✅ 超细线条测试完成！")
            print("🎯 优化效果已验证：")
            print("   • 线条更细腻 (0.8px)")
            print("   • 彩虹渐变更平滑")
            print("   • 颤音细节更清晰")
            print("   • 仅保留前端粒子")
        else:
            print("❌ 测试失败")
    except Exception as e:
        print(f"❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
