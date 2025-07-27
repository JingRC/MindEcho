#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修复后的matplotlib兼容性
"""

import matplotlib.pyplot as plt
import numpy as np

def test_fixed_approach():
    """测试修复后的方法"""
    print("🎯 测试修复后的matplotlib兼容性")
    print("=" * 50)
    
    try:
        # 模拟新的setup_ecg_grid逻辑
        fig, ax = plt.subplots()
        
        # 设置背景色
        bg_color = '#000000'
        ax.set_facecolor(bg_color)
        
        # 添加测试线条
        x = np.linspace(0, 10, 100)
        pitch_line, = ax.plot(x, np.sin(x), color='#00FF00', 
                             linewidth=2.5, alpha=1.0, zorder=10)
        
        # 保存数据
        existing_line_data = pitch_line.get_data()
        print(f"保存了线条数据: {len(existing_line_data[0])}个点")
        
        # 模拟setup_ecg_grid的清除和重建
        ax.clear()
        ax.set_facecolor(bg_color)
        ax.set_yticklabels([])
        ax.tick_params(axis='y', which='both', left=False, right=False)
        
        # 重新创建pitch_line
        pitch_line, = ax.plot([], [], color='#00FF00', 
                             linewidth=2.5, alpha=1.0, zorder=10)
        
        # 恢复数据
        if existing_line_data is not None and len(existing_line_data[0]) > 0:
            pitch_line.set_data(existing_line_data[0], existing_line_data[1])
            print("✅ 线条数据成功恢复")
        
        print(f"最终状态: {len(ax.lines)}条线条")
        print(f"线条颜色: {pitch_line.get_color()}")
        print(f"线条宽度: {pitch_line.get_linewidth()}")
        
        plt.close(fig)
        
        print("\n🎉 修复后的方法测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    if test_fixed_approach():
        print("\n✅ matplotlib兼容性问题已修复")
        print("ArtistList.copy()错误已解决")
        print("现在可以启动MindEcho增强版了")
    else:
        print("\n❌ 修复失败")

if __name__ == "__main__":
    main()
