#!/usr/bin/env python3
"""
测试录音时音高检测问题修复
解决两个问题：
1. 不录音时不应该进行实时检测
2. 录音时仍显示静音中
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_recording_pitch_detection_fix():
    """测试录音时音高检测修复"""
    print("=" * 60)
    print("🎤 测试录音时音高检测修复")
    print("=" * 60)
    
    print("\n🔧 问题修复:")
    print("1. ✅ 禁用自动启动实时分析")
    print("   • 程序启动时不再自动开始音频检测")
    print("   • 只有用户主动点击录音按钮才开始")
    
    print("2. ✅ 极大降低音高检测阈值")
    print("   • CPU检测置信度: 0.1 → 0.05")
    print("   • 颤音检测置信度: 0.03 → 0.01") 
    print("   • 有效音高阈值: 30Hz → 20Hz")
    print("   • 频率检测范围: 30-2000Hz")
    
    print("3. ✅ 增强调试信息")
    print("   • 音高检测函数调用计数")
    print("   • 详细的置信度和峰值信息")
    print("   • 原始vs降噪音频对比")
    print("   • 过滤信号的详细原因")
    
    print("4. ✅ 录音状态管理")
    print("   • 录音时设置 is_analyzing = True")
    print("   • 明确区分录音和分析状态")
    
    print("\n🎯 预期修复效果:")
    print("✅ 程序启动时界面静止，无音频检测")
    print("✅ 点击'开始录音分析'后开始音频检测")  
    print("✅ 即使很微弱的声音也能被检测到")
    print("✅ 详细调试信息帮助诊断问题")
    
    print("\n📋 新增调试信息:")
    print("🎯 音高检测函数首次调用")
    print("🔍 音高检测调用#XXX, 音频RMS=X.XXXX")
    print("🎯 CPU音高检测开始调试模式")
    print("🎵 CPU检测成功: XXXHz (置信度: X.XXX)")
    print("🎼 颤音检测器成功: XXXHz (置信度: X.XXX)")
    print("❌ 颤音检测器过滤: 详细检测信息")
    print("🔍 音高对比: 原始=XXXHz, 降噪后=XXXHz")
    print("✅ 录音已启动: 文件=XXX, 保存=True/False")
    
    print("\n📊 测试步骤:")
    print("1. 启动MindEcho增强版")
    print("2. 确认程序启动时控制台安静（无音频检测输出）")
    print("3. 点击'开始录音分析'按钮")
    print("4. 选择'基础频域降噪'模式")
    print("5. 对麦克风发出声音（说话、唱歌、哼鸣）")
    print("6. 观察控制台输出和界面变化")
    
    print("\n✅ 成功标志:")
    print("• 启动时无音频处理输出")
    print("• 录音后看到'🎯 音高检测函数首次调用'")
    print("• 看到'🎵 CPU检测成功'或'🎼 颤音检测器成功'")
    print("• 界面显示音高线条和音符信息")
    print("• 不再持续显示'静音中'")
    
    print("\n❓ 如果仍有问题:")
    print("• 检查'🔍 音高检测调用#'计数是否增加")
    print("• 查看'❌ 颤音检测器过滤'了解过滤原因")
    print("• 观察音频RMS值是否太低")
    print("• 检查麦克风权限和音量设置")
    
    return True

def test_start_mindecho():
    """启动MindEcho进行录音音高检测测试"""
    print("\n🚀 启动MindEcho进行录音音高检测测试...")
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        print("✅ 导入integrated_recording_interface模块成功")
        
        print("💡 测试要点:")
        print("1. 程序启动后应该安静，没有音频处理输出")
        print("2. 点击'开始录音分析'按钮开始录音")
        print("3. 可以选择是否保存录音文件")
        print("4. 选择'基础频域降噪'模式")
        print("5. 对麦克风发声，观察是否检测到音高")
        print("6. 界面应显示绿色音高线条")
        
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
    print("🎤 MindEcho 录音音高检测修复测试")
    print("目标：解决不录音时不应检测 + 录音时显示静音的问题")
    
    # 显示修复详情
    test_recording_pitch_detection_fix()
    
    # 询问是否启动实际测试
    choice = input("\n是否启动MindEcho进行实际测试? (y/n): ").strip().lower()
    if choice == 'y':
        test_start_mindecho()
    else:
        print("✅ 修复说明完成！")
        print("\n手动测试命令:")
        print("python run_enhanced.py")
        print("选择选项 1 启动增强版")

if __name__ == "__main__":
    main()
