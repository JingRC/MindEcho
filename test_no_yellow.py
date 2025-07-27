#!/usr/bin/env python3
"""
测试移除黄色条纹后的效果
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def main():
    print("🎵 启动无黄色条纹版本...")
    print()
    print("✨ 本次更新:")
    print("  ❌ 完全移除黄色条纹")
    print("  ✅ 保留纯净的绿色音调线")
    print("  ✅ 简洁的心电图风格")
    print("  ✅ 突出音高变化的连续性")
    print("  ✅ 绿色主线线宽2.5，完全不透明")
    print()
    print("🚀 启动集成界面...")
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        integrated_main()
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
