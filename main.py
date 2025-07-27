#!/usr/bin/env python3
"""
MindEcho 统一启动入口
智能音频录制与分析系统
"""

import sys
import subprocess
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def check_and_install_deps():
    """检查并安装依赖"""
    required_packages = [
        'numpy', 'scipy', 'sounddevice', 
        'matplotlib', 'PyQt6'
    ]
    
    print("🔧 检查依赖包...")
    missing = []
    
    for package in required_packages:
        try:
            if package == 'PyQt6':
                __import__('PyQt6.QtWidgets')
            else:
                __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package}")
            missing.append(package)
    
    if missing:
        print(f"\n📦 安装缺失包: {', '.join(missing)}")
        for package in missing:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"  ✅ {package} 安装成功")
            except:
                print(f"  ❌ {package} 安装失败")
                return False
    
    return True

def main():
    """主函数"""
    print("🎵 MindEcho 智能音频分析系统 🎵")
    print("=" * 40)
    
    # 检查依赖
    if not check_and_install_deps():
        print("❌ 依赖安装失败，请手动安装")
        return
    
    print("\n🚀 启动增强版 MindEcho...")
    
    try:
        from src.gui.enhanced_main_window import main as enhanced_main
        enhanced_main()
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        print("\n尝试简化版...")
        try:
            from src.gui.simple_gui import main as simple_main
            simple_main()
        except Exception as e2:
            print(f"❌ 简化版也失败: {e2}")
            print("请检查安装和环境配置")

if __name__ == "__main__":
    main()
