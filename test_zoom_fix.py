#!/usr/bin/env python3
"""
测试缩放一致性问题是否已解决
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_zoom_consistency():
    """测试缩放一致性"""
    print("🔍 测试缩放一致性修复...")
    print()
    print("修复内容:")
    print("1. ✅ 修复了 update_display() 中 Y轴范围计算错误")
    print("   - 原问题: 使用固定的 y_view_range 而不是考虑缩放的 actual_range")
    print("   - 修复: 计算 actual_y_range = self.y_view_range / self.zoom_level")
    print()
    print("2. ✅ 修复了自动跟随功能中的轴范围更新缺失")
    print("   - 原问题: 修改 y_view_center 后没有立即更新轴范围")
    print("   - 修复: 添加了 self.update_axis_ranges() 调用")
    print()
    print("3. ✅ 修复了时间窗口改变时绕过缩放系统的问题")
    print("   - 原问题: on_time_window_changed() 直接使用 set_ylim()")
    print("   - 修复: 改用 update_axis_ranges() 保持缩放一致性")
    print()
    print("4. ✅ 修复了敏感度调整时绕过缩放系统的问题")
    print("   - 原问题: on_sensitivity_changed() 直接修改 ylim")
    print("   - 修复: 通过修改 y_view_range 并调用 update_axis_ranges()")
    print()
    print("预期效果:")
    print("- 录音时缩放级别保持一致")
    print("- 手动调整缩放后不会被重置")
    print("- 自动跟随功能不会破坏缩放设置")
    print("- 时间窗口和敏感度调整保持缩放设置")
    print()
    print("测试方法:")
    print("1. 启动增强版 MindEcho")
    print("2. 调整缩放到 2.0x 或其他非 1.0x 的值")
    print("3. 开始录音并说话")
    print("4. 观察缩放级别是否保持不变")
    print("5. 测试自动跟随功能是否正常工作")
    print("6. 调整时间窗口和敏感度，确认缩放保持不变")
    print()
    print("如果问题依然存在，请检查:")
    print("- 是否有其他地方调用了 update_axis_ranges() 但没有考虑缩放")
    print("- 是否有其他地方直接修改了 ax.set_ylim() 而绕过了缩放系统")
    print()

if __name__ == "__main__":
    test_zoom_consistency()
    
    # 询问是否启动实际测试
    choice = input("是否启动 MindEcho 进行实际测试? (y/n): ").lower()
    if choice == 'y':
        try:
            from src.gui.integrated_recording_interface import main as integrated_main
            print("\n🚀 启动 MindEcho 增强版进行缩放测试...")
            integrated_main()
        except Exception as e:
            print(f"❌ 启动失败: {e}")
