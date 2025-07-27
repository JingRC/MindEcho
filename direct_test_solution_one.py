#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案一直接启动器 - 不依赖音频录制
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

def direct_test_solution_one():
    """直接测试方案一（不需要音频依赖）"""
    print("🎨 MindEcho 方案一：改进的彩色渐变可视化器")
    print("=" * 55)
    print()
    print("📋 方案一特点:")
    print("  ✅ 专门解决 Matplotlib 3.10.1 兼容性问题")
    print("  ✅ 使用 LineCollection 优化渐变效果")
    print("  ✅ 5种渐变模式：彩色渐变、高性能渐变、分段彩色、光谱渐变、3D效果")
    print("  ✅ 4个质量等级：性能优先 → 平衡 → 质量优先 → 极致效果")
    print("  ✅ 内置强制刷新和回退机制")
    print("  ✅ 无需额外依赖，直接运行")
    print()
    
    # 检查基本依赖
    print("🔍 检查依赖...")
    dependencies = {
        'numpy': 'numpy',
        'matplotlib': 'matplotlib',
        'colorsys': 'colorsys'
    }
    
    missing = []
    for name, module in dependencies.items():
        try:
            __import__(module)
            print(f"  ✅ {name}")
        except ImportError:
            print(f"  ❌ {name}")
            missing.append(name)
    
    # 检查Qt
    qt_available = False
    try:
        import PyQt6.QtWidgets
        print("  ✅ PyQt6")
        qt_available = True
    except ImportError:
        try:
            import PyQt5.QtWidgets
            print("  ✅ PyQt5")
            qt_available = True
        except ImportError:
            print("  ❌ PyQt6/PyQt5")
            missing.append("PyQt6 或 PyQt5")
    
    if missing:
        print(f"\n❌ 缺少依赖: {', '.join(missing)}")
        print("请安装缺少的依赖包")
        return False
    
    print("\n🚀 启动改进的Matplotlib可视化器...")
    
    try:
        # 导入和启动
        from src.gui.improved_matplotlib_visualizer import ImprovedMatplotlibVisualizer
        
        if qt_available:
            try:
                from PyQt6.QtWidgets import QApplication
            except ImportError:
                from PyQt5.QtWidgets import QApplication
            
            app = QApplication(sys.argv)
            
            # 创建可视化器
            visualizer = ImprovedMatplotlibVisualizer()
            visualizer.show()
            
            print("✅ 启动成功！")
            print()
            print("🎯 测试步骤:")
            print("  1️⃣ 点击 '🎵 测试颤音' 加载测试数据")
            print("  2️⃣ 切换到 '彩色渐变' 模式")
            print("  3️⃣ 观察是否显示彩色渐变线条")
            print("  4️⃣ 尝试不同的 '渐变质量' 设置")
            print("  5️⃣ 如有问题，点击 '🔄 强制刷新'")
            print()
            print("🔍 重点验证:")
            print("  • 彩色渐变模式是否正常显示")
            print("  • 心电图模式线条是否够细 (1.0px)")
            print("  • 各种渐变效果的稳定性")
            
            # 运行应用
            sys.exit(app.exec())
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print()
        print("🔧 可能的解决方案:")
        print("  1. 确保已安装 PyQt6: pip install PyQt6")
        print("  2. 或安装 PyQt5: pip install PyQt5")
        print("  3. 确保已安装 matplotlib: pip install matplotlib")
        print("  4. 确保已安装 numpy: pip install numpy")
        return False
        
    except Exception as e:
        print(f"❌ 运行错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    direct_test_solution_one()
