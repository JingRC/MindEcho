#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试PyQtGraph彩色渐变集成
验证integrated_recording_interface中的PyQtGraph彩色渐变模式
"""

import sys
import os
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_pyqtgraph_integration():
    """测试PyQtGraph集成到主界面"""
    try:
        # 导入Qt应用
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            print("❌ 需要安装 PyQt5 或 PyQt6")
            return False
    
    try:
        from src.gui.integrated_recording_interface import IntegratedRecordingInterface
        
        print("🚀 启动PyQtGraph彩色渐变集成测试...")
        
        app = QApplication(sys.argv)
        
        # 创建主界面
        interface = IntegratedRecordingInterface()
        interface.show()
        
        print("✅ 主界面已启动")
        print("\n💡 测试步骤:")
        print("1. 等待界面完全加载")
        print("2. 切换到'彩色渐变'模式")
        print("3. 开始录音或加载测试数据")
        print("4. 观察是否显示PyQtGraph彩色渐变效果")
        print("\n🔍 预期效果:")
        print("• 彩色渐变模式：显示PyQtGraph硬件加速渲染")
        print("• 心电图模式：显示Matplotlib传统渲染")
        print("• 界面在两种模式间平滑切换")
        
        # 检查PyQtGraph组件是否成功初始化
        if hasattr(interface.visualizer, 'pyqtgraph_gradient_widget'):
            if interface.visualizer.pyqtgraph_gradient_widget is not None:
                print("✅ PyQtGraph彩色渐变组件初始化成功")
            else:
                print("❌ PyQtGraph彩色渐变组件初始化失败")
        else:
            print("❌ 没有找到PyQtGraph彩色渐变组件属性")
        
        # 启动应用事件循环
        sys.exit(app.exec())
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 启动错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_pyqtgraph_installation():
    """检查PyQtGraph安装状态"""
    print("🔧 检查PyQtGraph安装状态...")
    
    try:
        import pyqtgraph as pg
        print(f"✅ PyQtGraph 已安装，版本: {pg.__version__}")
        
        # 检查OpenGL支持
        try:
            import pyqtgraph.opengl as gl
            print("✅ OpenGL 支持可用")
        except ImportError:
            print("⚠️ OpenGL 支持不可用")
        
        # 检查Qt后端
        try:
            from pyqtgraph.Qt import QtCore, QtWidgets
            print("✅ Qt 后端可用")
        except ImportError:
            print("❌ Qt 后端不可用")
        
        return True
        
    except ImportError as e:
        print(f"❌ PyQtGraph 未安装: {e}")
        print("💡 安装命令: pip install pyqtgraph")
        return False

def test_gradient_widget_standalone():
    """测试PyQtGraph渐变组件独立运行"""
    print("\n🎨 测试PyQtGraph渐变组件...")
    
    try:
        from src.gui.pyqtgraph_gradient_widget import test_pyqtgraph_gradient
        print("✅ 找到PyQtGraph渐变组件")
        
        # 运行独立测试
        test_pyqtgraph_gradient()
        
    except ImportError as e:
        print(f"❌ PyQtGraph渐变组件导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ PyQtGraph渐变组件测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🌈 MindEcho PyQtGraph彩色渐变集成测试")
    print("=" * 60)
    
    # 1. 检查PyQtGraph安装
    if not check_pyqtgraph_installation():
        print("\n❌ PyQtGraph未正确安装，无法继续测试")
        input("按回车键退出...")
        return
    
    print("\n选择测试模式:")
    print("1. 集成测试 - 在主界面中测试PyQtGraph彩色渐变")
    print("2. 独立测试 - 单独测试PyQtGraph渐变组件")
    print("3. 退出")
    
    choice = input("请选择 (1-3): ").strip()
    
    if choice == '1':
        test_pyqtgraph_integration()
    elif choice == '2':
        test_gradient_widget_standalone()
    elif choice == '3':
        print("👋 退出测试")
    else:
        print("❌ 无效选择")

if __name__ == "__main__":
    main()
