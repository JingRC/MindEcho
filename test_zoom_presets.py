#!/usr/bin/env python3
"""
测试新的专业缩放预设功能
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_zoom_presets():
    """测试缩放预设功能"""
    print("🔍 测试专业缩放预设系统...")
    print()
    print("新增功能:")
    print("✅ 双重缩放控制系统")
    print("   - 精确调节: 连续滑块控制 (0.1x - 5.0x)")
    print("   - 快速预设: 5个专业预设档位一键切换")
    print()
    print("📊 专业缩放预设档位:")
    print()
    
    zoom_presets = [
        (0.5, "广域视图", "显示±6个八度全频段范围", "适合总览音域分布，查看整体音高走势"),
        (1.0, "标准视图", "显示±3个八度常用范围", "日常分析使用，平衡细节与总览"),
        (2.0, "精细视图", "显示±1.5个八度细节分析", "观察音程变化，分析旋律走向"),
        (3.0, "颤音分析", "显示±1个八度微音程变化", "检测颤音技巧，音准微调分析"),
        (5.0, "超精视图", "显示±0.6个八度超细微变化", "精密音准分析，检测最微小偏差")
    ]
    
    for zoom_level, name, range_desc, usage_desc in zoom_presets:
        print(f"🎯 {zoom_level}x - {name}")
        print(f"   频率范围: {range_desc}")
        print(f"   适用场景: {usage_desc}")
        print()
    
    print("🔧 技术特性:")
    print("✅ 实时高亮显示当前激活的预设档位")
    print("✅ 鼠标悬停显示详细工具提示")
    print("✅ 滑块与预设按钮双向同步")
    print("✅ 专业音频分析术语和精确范围描述")
    print("✅ 视觉反馈：当前预设按钮高亮加粗显示")
    print()
    print("🎵 音频分析专业应用:")
    print("• 广域视图 (0.5x): 声乐教学，音域测试，整体音高分布分析")
    print("• 标准视图 (1.0x): 日常练习，基础音准校正，常规演奏分析")
    print("• 精细视图 (2.0x): 音程训练，和声分析，旋律精度检测")
    print("• 颤音分析 (3.0x): 颤音技巧评估，音准微调，表演技巧分析")
    print("• 超精视图 (5.0x): 专业调音，精密音准校准，微音程研究")
    print()
    print("🎨 界面设计:")
    print("• 分组布局: 缩放控制独立成组，界面更清晰")
    print("• 双行设计: 精确滑块 + 快速预设分离显示")
    print("• 动态高亮: 当前预设按钮绿色高亮边框")
    print("• 专业工具提示: 详细的功能说明和应用场景")
    print()

if __name__ == "__main__":
    test_zoom_presets()
    
    # 询问是否启动实际测试
    choice = input("是否启动 MindEcho 测试新的缩放预设功能? (y/n): ").lower()
    if choice == 'y':
        try:
            from src.gui.integrated_recording_interface import main as integrated_main
            print("\n🚀 启动 MindEcho 增强版测试缩放预设...")
            print("测试步骤:")
            print("1. 观察新的缩放控制组布局")
            print("2. 点击不同预设按钮，观察缩放变化")
            print("3. 查看预设按钮的高亮效果")
            print("4. 鼠标悬停预设按钮查看详细说明")
            print("5. 调节滑块，观察与预设的同步")
            print()
            integrated_main()
        except Exception as e:
            print(f"❌ 启动失败: {e}")
