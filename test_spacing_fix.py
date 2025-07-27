#!/usr/bin/env python3
"""
测试5.0x缩放标签间距修复
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_spacing_fix():
    """测试标签间距修复"""
    print("🔧 测试5.0x缩放标签间距修复...")
    print()
    print("修复内容:")
    print("  ✅ 5.0x缩放时录音状态使用与非录音一致的透明度逻辑")
    print("  ✅ 避免显示过多标签导致视觉拥挤")
    print("  ✅ 保持颜色高亮功能（金色→橙色→黄色）")
    print("  ✅ 字体大小和间距完全一致")
    print()
    print("测试方法:")
    print("  1. 设置缩放为5.0x")
    print("  2. 比较录音前后标签垂直间距")
    print("  3. 应该看到完全一致的标签密度和间距")
    print()
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        print("启动增强版界面...")
        integrated_main()
        return True
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return False

if __name__ == "__main__":
    test_spacing_fix()
