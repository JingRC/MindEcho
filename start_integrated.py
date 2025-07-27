"""
MindEcho 快速启动脚本
一键启动集成录音分析界面
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def check_dependencies():
    """简单检查依赖"""
    missing = []
    try:
        import numpy
        print("✅ numpy")
    except ImportError:
        print("❌ numpy")
        missing.append("numpy")
    
    try:
        import scipy
        print("✅ scipy")
    except ImportError:
        print("❌ scipy")
        missing.append("scipy")
    
    try:
        import sounddevice
        print("✅ sounddevice")
    except ImportError:
        print("❌ sounddevice")
        missing.append("sounddevice")
    
    try:
        import matplotlib
        print("✅ matplotlib")
    except ImportError:
        print("❌ matplotlib")
        missing.append("matplotlib")
    
    try:
        from PyQt6.QtWidgets import QApplication
        print("✅ PyQt6")
    except ImportError:
        try:
            from PyQt5.QtWidgets import QApplication
            print("✅ PyQt5")
        except ImportError:
            print("❌ PyQt6/PyQt5")
            missing.append("PyQt6 或 PyQt5")
    
    return missing

def main():
    print("🎵 MindEcho 集成录音分析系统")
    print("=" * 50)
    print("检查依赖...")
    
    missing = check_dependencies()
    
    if missing:
        print(f"\n❌ 缺少依赖: {', '.join(missing)}")
        print("请运行以下命令安装:")
        print("pip install numpy scipy matplotlib sounddevice PyQt6")
        input("按回车键退出...")
        return
    
    print("\n✅ 所有依赖已安装")
    print("🚀 启动集成录音分析界面...")
    print()
    print("功能说明:")
    print("• 录音控制: 开始/停止/暂停录音")
    print("• 实时分析: 64fps音高检测")
    print("• 心电图式可视化: 时间-音高二维曲线")
    print("• 多种显示模式: 心电图/频率曲线/音符阶梯/彩色渐变")
    print("• 音域渐变: 低音蓝色→高音红色")
    print("• 保存选项: 可选择是否保存录音文件")
    print()
    
    try:
        from src.gui.integrated_recording_interface import IntegratedRecordingInterface
        from PyQt6.QtWidgets import QApplication
        
        app = QApplication(sys.argv)
        app.setApplicationName("MindEcho 集成录音分析")
        
        window = IntegratedRecordingInterface()
        window.show()
        
        print("界面已打开，请在图形界面中操作...")
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        print("\n错误详情:")
        import traceback
        traceback.print_exc()
        input("按回车键退出...")

if __name__ == "__main__":
    main()
