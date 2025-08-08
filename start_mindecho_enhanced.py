#!/usr/bin/env python3
"""
MindEcho 增强型电流音检测系统 - 启动器
解决导入路径问题的直接启动脚本
"""

import sys
import os

# 添加必要的路径
current_dir = os.path.dirname(__file__)
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, 'src'))
sys.path.insert(0, os.path.join(current_dir, 'src', 'audio_processing'))
sys.path.insert(0, os.path.join(current_dir, 'src', 'gui'))

def main():
    try:
        print("🚀 启动MindEcho增强型电流音检测系统...")
        
        # 检查必要文件
        gui_file = os.path.join(current_dir, 'src', 'gui', 'integrated_recording_interface.py')
        if not os.path.exists(gui_file):
            print("❌ 找不到GUI文件，请检查项目结构")
            input("按回车键退出...")
            return 1
        
        # 设置PyQt6环境变量（如果需要）
        os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
        os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
        
        # 导入并启动GUI
        from PyQt6.QtWidgets import QApplication
        from integrated_recording_interface import IntegratedRecordingInterface
        
        app = QApplication(sys.argv)
        app.setApplicationName("MindEcho 增强型电流音检测系统")
        app.setApplicationVersion("2.0")
        
        # 创建主窗口
        main_window = IntegratedRecordingInterface()
        main_window.show()
        
        print("✅ MindEcho已启动！")
        print("🎯 特性：")
        print("   • 多维度电流音检测（基于专利CN114640926A）")
        print("   • 人声技巧保护（大声唱歌、气泡音等）")
        print("   • Venus EQ风格音频处理")
        print("   • 超低延迟监听（<1.5ms）")
        
        # 运行应用
        sys.exit(app.exec())
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("💡 解决方案:")
        print("   1. 安装PyQt6: pip install PyQt6")
        print("   2. 安装其他依赖: pip install numpy scipy sounddevice")
        input("按回车键退出...")
        return 1
    except Exception as e:
        print(f"❌ 启动错误: {e}")
        input("按回车键退出...")
        return 1

if __name__ == "__main__":
    main()
