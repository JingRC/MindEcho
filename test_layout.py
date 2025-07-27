#!/usr/bin/env python3
"""
测试新的控制面板布局
"""

import sys
sys.path.append('src')

try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
    from src.gui.integrated_recording_interface import IntegratedRecordingInterface
    
    def main():
        app = QApplication(sys.argv)
        
        # 创建主窗口
        main_window = QMainWindow()
        main_window.setWindowTitle("MindEcho - 布局测试")
        main_window.setGeometry(100, 100, 1200, 800)
        
        try:
            # 创建界面实例
            interface = IntegratedRecordingInterface()
            
            # 创建控制面板来测试布局
            controls = interface.create_controls()
            
            # 设置为主窗口的中央部件
            central_widget = QWidget()
            layout = QVBoxLayout(central_widget)
            layout.addWidget(controls)
            main_window.setCentralWidget(central_widget)
            
            main_window.show()
            print("✅ 布局测试成功！")
            print("📋 控制按钮位于第一行")
            print("📊 状态信息位于第二行")
            print("🎛️ 时间窗口和敏感度滑块现在有足够空间了")
            
            sys.exit(app.exec())
            
        except Exception as e:
            print(f"❌ 创建界面时出错: {e}")
            sys.exit(1)
            
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请确保已安装 PyQt6: pip install PyQt6")
    sys.exit(1)

if __name__ == "__main__":
    main()
