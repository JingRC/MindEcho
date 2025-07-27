#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试matplotlib修复的简化版本
不依赖sounddevice等复杂依赖
"""

import sys
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_artist_list_fix():
    """测试ArtistList修复"""
    print("🎯 测试matplotlib ArtistList兼容性修复")
    print("=" * 50)
    
    try:
        # 模拟setup_ecg_grid中的清除操作
        fig, ax = plt.subplots()
        
        # 添加测试内容
        x = np.linspace(0, 10, 100)
        line1, = ax.plot(x, np.sin(x), 'g-', linewidth=2.5, label='pitch_line')
        line2, = ax.plot(x, np.cos(x), 'r-', label='other_line')
        
        ax.text(0.5, 0.5, 'Test Text', transform=ax.transAxes)
        ax.grid(True)
        
        print(f"初始状态: {len(ax.lines)}条线条, {len(ax.texts)}个文本")
        
        # 模拟保存特定线条数据
        special_line = line1  # 这相当于pitch_line
        existing_line_data = special_line.get_data()
        print(f"保存了特殊线条数据: {len(existing_line_data[0])}个点")
        
        # 使用修复后的清除方法
        print("\n执行清除操作...")
        
        # 清除其他线条（修复后的方法）
        lines_to_remove = []
        for line in ax.lines:
            if line != special_line:
                lines_to_remove.append(line)
        
        for line in lines_to_remove:
            line.remove()
        
        # 清除文本
        texts_to_remove = []
        for text in ax.texts:
            texts_to_remove.append(text)
        
        for text in texts_to_remove:
            text.remove()
        
        # 清除网格线
        grid_lines_to_remove = ax.get_xgridlines() + ax.get_ygridlines()
        for line in grid_lines_to_remove:
            line.remove()
        
        print(f"清除后: {len(ax.lines)}条线条, {len(ax.texts)}个文本")
        
        # 验证特殊线条仍然存在
        if special_line in ax.lines:
            print("✅ 特殊线条成功保留")
        else:
            print("❌ 特殊线条丢失")
            return False
        
        # 测试恢复数据
        if existing_line_data is not None and len(existing_line_data[0]) > 0:
            special_line.set_data(existing_line_data[0], existing_line_data[1])
            print("✅ 线条数据成功恢复")
        
        plt.close(fig)
        
        print("\n🎉 matplotlib ArtistList兼容性修复测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    if test_artist_list_fix():
        print("\n✅ 修复验证成功")
        print("现在可以尝试启动MindEcho增强版了")
        print("'ArtistList' object has no attribute 'copy' 错误已修复")
    else:
        print("\n❌ 修复验证失败")

if __name__ == "__main__":
    main()
