#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MindEcho设备选择功能测试脚本
"""

import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

def main():
    """启动MindEcho并测试设备选择功能"""
    try:
        print("🎧 启动MindEcho设备选择功能测试...")
        print("=" * 60)
        
        # 导入必要的模块
        from PyQt6.QtWidgets import QApplication
        from src.gui.integrated_recording_interface import IntegratedRecordingInterface
        
        # 创建应用
        app = QApplication(sys.argv)
        app.setApplicationName("MindEcho - 设备选择测试")
        
        # 创建主窗口
        main_window = IntegratedRecordingInterface()
        main_window.setWindowTitle("MindEcho - 音频设备选择功能测试")
        main_window.show()
        
        print("✅ MindEcho已启动")
        print("📝 使用说明:")
        print("   1. 右键点击'开启监听'按钮")
        print("   2. 选择'🎧 选择音频设备'子菜单")
        print("   3. 选择您想要的音频设备配置")
        print("   4. 点击'开启监听'测试选定的设备")
        print("   5. 使用'🎚️ 调节音量'调整监听音量")
        print("   6. 使用'📊 查看实时状态'查看设备状态")
        print("=" * 60)
        
        # 运行应用
        sys.exit(app.exec())
        
    except KeyboardInterrupt:
        print("\n🔄 用户中断，正在退出...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
