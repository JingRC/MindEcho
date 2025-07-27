#!/usr/bin/env python3
"""
测试线条粗细控制修复
验证所有模式下的线条粗细调整功能
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_linewidth_control():
    """测试线条粗细控制功能"""
    print("🧪 测试线条粗细控制修复")
    print("="*50)
    
    try:
        from src.gui.integrated_recording_interface import ECGStylePitchVisualizer
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer
        import sys
        
        # 创建应用
        app = QApplication(sys.argv)
        
        # 创建可视化器
        visualizer = ECGStylePitchVisualizer()
        visualizer.show()
        
        print("✅ 界面已启动")
        print("🔧 测试说明:")
        print("  1. 界面启动后，找到'线条粗细'控制")
        print("  2. 尝试切换不同的粗细预设（0.5px到3.0px）")
        print("  3. 尝试自定义滑块调节")
        print("  4. 在不同显示模式间切换（心电图模式↔彩色渐变）")
        print("  5. 验证线条粗细是否正确改变")
        print()
        print("💡 预期结果:")
        print("  • 心电图模式：绿色线条粗细应该实时改变")
        print("  • 彩色渐变模式：彩色线段粗细应该实时改变") 
        print("  • 模式切换时：线条粗细设置应该保持")
        print()
        print("⚠️  如果线条粗细不变，请检查控制台日志")
        
        # 运行应用
        app.exec()
        
        print("✅ 测试完成")
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请确保已安装PyQt6/PyQt5")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("🎯 MindEcho 线条粗细控制修复测试")
    print("目标：验证修复后的线条粗细调整功能")
    print()
    
    success = test_linewidth_control()
    
    if success:
        print("\n🎉 测试完成！")
        print("请手动验证线条粗细控制是否正常工作")
    else:
        print("\n❌ 测试失败")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
