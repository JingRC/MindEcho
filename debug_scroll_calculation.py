#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试横轴滚动问题诊断脚本
专门检查滚动到最右端时的显示范围问题
"""

def test_scroll_calculation():
    """测试滚动计算逻辑"""
    print("🔍 横轴滚动计算测试")
    print("="*50)
    
    # 模拟参数
    max_history_time = 300.0  # 最大历史时间
    time_window = 16.0        # 时间窗口
    
    print(f"参数设置:")
    print(f"  - 最大历史时间: {max_history_time}秒")
    print(f"  - 时间窗口: {time_window}秒")
    
    # 计算最大偏移
    max_offset = max(0, max_history_time - time_window)
    print(f"  - 最大偏移: {max_offset}秒")
    
    # 测试不同滚动条位置的时间偏移
    positions = [0, 25, 50, 75, 100]
    
    print(f"\n滚动条位置 -> 时间偏移 -> 显示范围:")
    for pos in positions:
        normalized_value = pos / 100.0
        time_offset = normalized_value * max_offset
        
        # 计算显示范围
        x_min = time_offset
        x_max = time_offset + time_window
        
        print(f"  {pos:3d}% -> {time_offset:6.1f}s -> [{x_min:6.1f}s, {x_max:6.1f}s]")
    
    print(f"\n✅ 预期结果:")
    print(f"  - 滚动条0%: 显示范围应为 [0.0s, 16.0s]")
    print(f"  - 滚动条100%: 显示范围应为 [284.0s, 300.0s]")
    
    # 验证最右端的计算
    actual_right_min = max_offset
    actual_right_max = max_offset + time_window
    print(f"\n🎯 最右端验证:")
    print(f"  - 实际计算结果: [{actual_right_min}s, {actual_right_max}s]")
    
    if actual_right_min == 284.0 and actual_right_max == 300.0:
        print(f"  ✅ 计算正确!")
    else:
        print(f"  ❌ 计算错误!")
        print(f"  期望: [284.0s, 300.0s]")
        print(f"  实际: [{actual_right_min}s, {actual_right_max}s]")

if __name__ == "__main__":
    test_scroll_calculation()
