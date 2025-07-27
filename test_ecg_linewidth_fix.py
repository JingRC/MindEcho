#!/usr/bin/env python3
"""
测试心电图模式线条宽度修复
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def main():
    print("🔧 心电图模式线条宽度修复测试")
    print("="*50)
    print()
    print("修复内容:")
    print("  ✅ 移除心电图模式中的重复线条宽度设置")
    print("  ✅ 统一由update_ecg_mode方法设置为0.6px极细线条")
    print("  ✅ 设置明亮绿色#00FF44作为心电图特色")
    print("  ✅ 完全不透明alpha=1.0确保清晰可见")
    print()
    print("预期效果:")
    print("  • 心电图模式线条宽度：0.6px（极细）")
    print("  • 颜色：明亮绿色#00FF44")
    print("  • 透明度：完全不透明")
    print("  • 适合显示颤音等精细技巧")
    print()
    print("测试方法:")
    print("  1. 选择'心电图模式'")
    print("  2. 开始录音")
    print("  3. 观察线条应该是极细的明亮绿色")
    print("  4. 控制台应显示'💚 心电图模式：0.6px极细绿线'")
    print()
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        print("启动增强版界面...")
        integrated_main()
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
