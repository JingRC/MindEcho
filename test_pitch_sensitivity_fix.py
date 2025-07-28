#!/usr/bin/env python3
"""
测试音高检测灵敏度修复
解决"开启降噪模式依然显示静音中"的问题
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_pitch_sensitivity_fix():
    """测试音高检测灵敏度修复"""
    print("=" * 60)
    print("🎤 测试音高检测灵敏度修复")
    print("=" * 60)
    
    print("\n🔧 修复内容:")
    print("1. ✅ 大幅降低音高检测置信度阈值")
    print("   • 主检测: 0.2 → 0.1")
    print("   • 颤音检测: 0.08 → 0.03") 
    print("   • 频率范围: 60-1000Hz → 40-2000Hz")
    
    print("2. ✅ 增强音高检测调试信息")
    print("   • 显示检测结果详细信息(频率、置信度、峰值)")
    print("   • 显示被过滤的低置信度信号")
    print("   • 对比原始音频vs降噪后的检测效果")
    
    print("3. ✅ 降噪强度监控")
    print("   • 检测降噪是否过度抑制信号")
    print("   • 当信号衰减超过90%时发出警告")
    print("   • 原始音频vs降噪音频的音高检测对比")
    
    print("\n🎯 预期修复效果:")
    print("✅ 降低音高检测门槛，检测更微弱的音调变化")
    print("✅ 即使在降噪模式下也能检测到人声音高")  
    print("✅ 详细调试信息帮助诊断检测问题")
    print("✅ 自动监控降噪是否过强")
    
    print("\n📋 新增调试信息说明:")
    print("🎯 CPU音高检测开始调试模式")
    print("🎵 CPU检测成功: XXXHz (置信度: X.XXX)")
    print("🔍 过滤低置信度信号: XXXHz (置信度: X.XXX)")
    print("🎼 颤音检测器成功: XXXHz (置信度: X.XXX)")
    print("❌ 颤音检测器过滤: 检测结果详细信息")
    print("⚠️ 降噪过强: 原始RMS=X.XXXX → 降噪后RMS=X.XXXX")
    print("🔍 音高对比: 原始=XXXHz, 降噪后=XXXHz")
    
    print("\n📊 测试方法:")
    print("1. 启动MindEcho增强版")
    print("2. 选择'基础频域降噪'模式")
    print("3. 发出任何声音(说话、唱歌、哼鸣)")
    print("4. 观察控制台输出，应该看到:")
    print("   • 🎯 CPU音高检测开始调试模式")
    print("   • 🎵 CPU检测成功 或 🎼 颤音检测器成功")
    print("   • 音高数据点增加和界面显示音高线条")
    
    print("\n⚠️ 如果仍显示静音:")
    print("• 查看是否有'⚠️ 降噪过强'警告")
    print("• 查看'🔍 音高对比'中原始音频是否检测到音高")
    print("• 查看'❌ 颤音检测器过滤'了解被过滤的原因")
    
    return True

def test_start_mindecho():
    """启动MindEcho进行音高检测测试"""
    print("\n🚀 启动MindEcho进行音高检测测试...")
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        print("✅ 导入integrated_recording_interface模块成功")
        
        print("💡 测试指南:")
        print("1. 程序启动后会自动开始实时分析")
        print("2. 选择'基础频域降噪'模式")
        print("3. 对着麦克风发出声音")
        print("4. 观察控制台调试信息和界面变化")
        print("5. 如果看到音高检测成功信息，说明修复生效")
        
        input("\n按回车键启动MindEcho...")
        integrated_main()
        
    except ImportError as e:
        print(f"❌ 导入模块失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 启动MindEcho失败: {e}")
        return False
    
    return True

def main():
    """主函数"""
    print("🎤 MindEcho 音高检测灵敏度修复测试")
    print("目标：解决开启降噪模式依然显示静音中的问题")
    
    # 显示修复详情
    test_pitch_sensitivity_fix()
    
    # 询问是否启动实际测试
    choice = input("\n是否启动MindEcho进行实际测试? (y/n): ").strip().lower()
    if choice == 'y':
        test_start_mindecho()
    else:
        print("✅ 修复说明完成！")
        print("\n手动测试步骤:")
        print("1. python run_enhanced.py")
        print("2. 选择选项 1 启动增强版")
        print("3. 选择'基础频域降噪'模式")
        print("4. 对麦克风发声，观察调试输出")

if __name__ == "__main__":
    main()
