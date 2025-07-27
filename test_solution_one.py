#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案一测试启动器 - 改进的Matplotlib彩色渐变可视化器
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

def test_solution_one():
    """测试方案一：改进的Matplotlib实现"""
    print("🎨 启动方案一：改进的Matplotlib彩色渐变可视化器")
    print("=" * 60)
    print()
    print("📋 方案一特点:")
    print("  ✅ 专门解决Matplotlib 3.10.1兼容性问题")
    print("  ✅ 使用LineCollection优化渐变效果")
    print("  ✅ 5种渐变模式：彩色渐变、高性能渐变、分段彩色、光谱渐变、3D效果")
    print("  ✅ 4个质量等级：性能优先 → 平衡 → 质量优先 → 极致效果")
    print("  ✅ 内置强制刷新和回退机制")
    print("  ✅ 无需额外依赖，直接运行")
    print()
    print("🎯 测试重点:")
    print("  • 彩色渐变模式是否正常显示")
    print("  • 心电图模式线条是否够细（1.0px）")
    print("  • 各种渐变效果的稳定性")
    print("  • 强制刷新功能是否有效")
    print()
    print("💡 操作建议:")
    print("  1️⃣ 点击'测试颤音'加载测试数据")
    print("  2️⃣ 切换到'彩色渐变'模式")
    print("  3️⃣ 尝试不同的'渐变质量'设置")
    print("  4️⃣ 如有问题，点击'强制刷新'")
    print()
    
    try:
        # 导入改进的可视化器
        from src.gui.improved_matplotlib_visualizer import ImprovedMatplotlibVisualizer
        
        # 尝试导入Qt
        try:
            from PyQt6.QtWidgets import QApplication
            print("✅ 使用PyQt6")
        except ImportError:
            from PyQt5.QtWidgets import QApplication
            print("✅ 使用PyQt5")
        
        print("✅ 模块导入成功")
        
        # 创建应用程序
        app = QApplication(sys.argv)
        
        # 创建可视化器
        visualizer = ImprovedMatplotlibVisualizer()
        visualizer.show()
        
        print("🚀 改进的Matplotlib可视化器启动成功！")
        print()
        print("🔍 请验证以下效果:")
        print("  • 界面是否正常显示")
        print("  • 加载测试数据后渐变效果是否正常")
        print("  • 心电图模式线条是否细腻")
        print("  • 不同质量设置的性能差异")
        
        # 运行应用程序
        sys.exit(app.exec())
        
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        print()
        print("🔧 可能的解决方案:")
        print("  1. 检查PyQt6是否正确安装")
        print("  2. 检查matplotlib是否正确安装")
        print("  3. 尝试运行: pip install PyQt6 matplotlib numpy")
        
        # 尝试使用PyQt5
        print("\n🔄 尝试使用PyQt5...")
        try:
            from PyQt5.QtWidgets import QApplication
            print("✅ PyQt5可用，建议修改代码使用PyQt5")
        except ImportError:
            print("❌ PyQt5也不可用")
        
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        
        print("\n🔧 故障排除建议:")
        print("  1. 确保所有依赖包已安装")
        print("  2. 检查Python版本兼容性")
        print("  3. 尝试重启IDE/终端")
        print("  4. 检查项目路径是否正确")

def check_environment():
    """检查运行环境"""
    print("🔍 检查运行环境...")
    
    # 检查Python版本
    print(f"  Python版本: {sys.version}")
    
    # 检查关键依赖
    packages = ['numpy', 'matplotlib', 'PyQt6', 'PyQt5']
    
    for package in packages:
        try:
            if package == 'PyQt6':
                import PyQt6.QtWidgets
                print(f"  ✅ {package}")
            elif package == 'PyQt5':
                import PyQt5.QtWidgets
                print(f"  ✅ {package}")
            else:
                __import__(package)
                print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package}")
    
    # 检查matplotlib版本
    try:
        import matplotlib
        print(f"  📊 Matplotlib版本: {matplotlib.__version__}")
    except ImportError:
        print("  ❌ Matplotlib未安装")

if __name__ == "__main__":
    print("🎵 MindEcho 方案一测试器")
    print("=" * 40)
    
    # 检查环境
    check_environment()
    print()
    
    # 启动测试
    test_solution_one()
