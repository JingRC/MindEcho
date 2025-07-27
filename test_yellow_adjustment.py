#!/usr/bin/env python3
"""
测试黄色条纹调整效果
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def main():
    print("🎵 启动黄色条纹调整测试版本...")
    print()
    print("✨ 本次调整内容:")
    print("  • 黄色条纹敏感度: 0.1 → 0.25 (更少出现)")
    print("  • 黄色条纹透明度: 0.6 → 0.3 (更淡)")
    print("  • 黄色条纹线宽: 4 → 2 (更细)")
    print("  • 绿色主线线宽: 2 → 2.5 (更粗)")
    print("  • 绿色主线透明度: 0.9 → 1.0 (更鲜明)")
    print("  • 渐变色黄色: #FFFF00 → #AADD00 (更柔和)")
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
