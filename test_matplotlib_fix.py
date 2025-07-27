#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试matplotlib ArtistList兼容性修复
"""

def test_matplotlib_compatibility():
    """测试matplotlib版本兼容性"""
    print("🔧 测试matplotlib版本兼容性")
    print("=" * 50)
    
    try:
        import matplotlib
        print(f"matplotlib版本: {matplotlib.__version__}")
        
        import matplotlib.pyplot as plt
        import numpy as np
        
        # 创建测试图形
        fig, ax = plt.subplots()
        
        # 添加一些测试线条和文本
        x = np.linspace(0, 10, 100)
        y = np.sin(x)
        
        line1, = ax.plot(x, y, 'r-', label='sin')
        line2, = ax.plot(x, np.cos(x), 'b-', label='cos')
        
        ax.text(0.5, 0.5, 'Test Text', transform=ax.transAxes)
        ax.grid(True)
        
        print(f"创建了{len(ax.lines)}条线条")
        print(f"创建了{len(ax.texts)}个文本")
        
        # 测试清除操作（模拟setup_ecg_grid的逻辑）
        print("\n测试清除操作...")
        
        # 保存特定线条
        special_line = line1
        
        # 清除其他线条（兼容版本）
        lines_to_remove = []
        for line in ax.lines:
            if line != special_line:
                lines_to_remove.append(line)
        
        for line in lines_to_remove:
            line.remove()
        
        print(f"清除后剩余{len(ax.lines)}条线条")
        
        # 清除文本
        texts_to_remove = []
        for text in ax.texts:
            texts_to_remove.append(text)
        
        for text in texts_to_remove:
            text.remove()
        
        print(f"清除后剩余{len(ax.texts)}个文本")
        
        print("✅ matplotlib兼容性测试通过")
        
        plt.close(fig)
        
    except Exception as e:
        print(f"❌ matplotlib兼容性测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_gui_import():
    """测试GUI模块导入"""
    print("\n🔧 测试GUI模块导入")
    print("=" * 50)
    
    try:
        from src.gui.integrated_recording_interface import ECGStylePitchVisualizer
        print("✅ ECGStylePitchVisualizer导入成功")
        
        # 测试创建实例（不显示）
        visualizer = ECGStylePitchVisualizer()
        print("✅ 可视化器实例创建成功")
        
        return True
        
    except Exception as e:
        print(f"❌ GUI模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🎯 MindEcho matplotlib兼容性修复测试")
    print("=" * 60)
    
    # 测试matplotlib兼容性
    if not test_matplotlib_compatibility():
        return
    
    # 测试GUI导入
    if not test_gui_import():
        return
    
    print("\n🎉 所有测试通过！")
    print("现在可以尝试启动增强版：")
    print("  python run_enhanced.py")

if __name__ == "__main__":
    main()
