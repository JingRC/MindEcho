#!/usr/bin/env python3
"""
MindEcho 监听功能高频稳定性优化测试
专门解决高音大音量时监听返回声音不稳定的问题
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def show_high_freq_optimization():
    """显示高频稳定性优化详情"""
    print("🎵 MindEcho 高频稳定性优化")
    print("="*60)
    print()
    print("📋 问题分析:")
    print("  ❌ 原始问题: 高音大音量时监听返回声音不稳定")
    print("  🔍 根本原因: 高频内容在大音量时处理不当 + 缓冲区过小")
    print()
    print("🛠️ 高频优化方案:")
    print("  ✅ 1. 高频内容智能识别:")
    print("     - 频谱分析: 检测高频能量比例(>30%)")
    print("     - 大音量检测: 识别幅度>70%的信号")
    print("     - 联合判断: 高频+大音量触发特殊处理")
    print()
    print("  ✅ 2. 分层稳定性处理:")
    print("     - 极大音量(>95%): 软限制器(tanh函数)")
    print("     - 大音量(85-95%): 轻微压缩+高频保护")
    print("     - 中等音量(<85%): 完全保持原音质")
    print()
    print("  ✅ 3. 缓冲区优化:")
    print("     - 块大小: 128→256样本（提高稳定性）")
    print("     - 延迟: 2.7ms→5.3ms（可接受的权衡）")
    print("     - 预分配: 避免运行时内存分配")
    print()
    print("  ✅ 4. DC偏移保护:")
    print("     - 阈值提高到8%，减少对音频的干扰")
    print("     - 使用60%渐进式去除而非完全去除")
    print()
    print("🎯 预期效果:")
    print("  🎵 高音大音量时稳定清晰，无抖动或失真")
    print("  🎵 不同音量级别的平滑过渡")
    print("  🎵 保护高频细节，避免过度处理")
    print("  🎵 延迟控制在可接受范围内(~5ms)")
    print()

def test_high_freq_scenarios():
    """测试高频场景"""
    print("🧪 高频稳定性测试场景")
    print("="*40)
    print()
    print("测试重点:")
    print("1. 🎵 高音测试:")
    print("   - 女高音(C5-C6): 523-1047Hz")
    print("   - 男高音(C4-C5): 262-523Hz") 
    print("   - 假声技巧: 各种高频泛音")
    print()
    print("2. 🔊 音量梯度测试:")
    print("   - 轻声高音: 检查是否保持清晰")
    print("   - 中等音量高音: 检查音质是否自然")
    print("   - 大音量高音: 重点测试稳定性")
    print("   - 极大音量高音: 检查是否有软限制保护")
    print()
    print("3. 🎭 特殊技巧测试:")
    print("   - 颤音(高频): 快速音高变化")
    print("   - 滑音(上滑): 连续音高上升")
    print("   - 气泡音: 高频谐波丰富")
    print("   - 哨音: 纯高频信号")
    print()
    print("✅ 通过标准:")
    print("  - 所有高音场景下监听声音稳定")
    print("  - 大音量时无抖动、无失真")
    print("  - 音质自然，高频细节保留")
    print("  - 延迟在可接受范围内")
    print()

def start_high_freq_test():
    """启动高频优化测试"""
    print("🚀 启动MindEcho进行高频稳定性测试...")
    print()
    print("💡 测试指南:")
    print("1. 程序启动后，找到可视化器区域")
    print("2. 点击'开启监听'按钮")
    print("3. 注意查看控制台输出的新优化信息")
    print("4. 按照高频测试场景进行验证")
    print("5. 特别关注高音大音量时的稳定性")
    print()
    print("🔍 观察要点:")
    print("  - 控制台显示'高稳定性监听流已启动'")
    print("  - 显示'256样本块'和'~5.3ms延迟'")
    print("  - 显示'高频优化模式'信息")
    print()
    
    input("按回车键启动MindEcho...")
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        integrated_main()
        
    except ImportError as e:
        print(f"❌ 导入模块失败: {e}")
        print("请确保在MindEcho项目根目录下运行此脚本")
        return False
    except Exception as e:
        print(f"❌ 启动MindEcho失败: {e}")
        return False
    
    return True

def main():
    """主函数"""
    print("🎵 MindEcho 高频稳定性优化测试")
    print("="*60)
    print()
    
    print("选择操作:")
    print("1. 查看高频优化详情")
    print("2. 查看测试场景")
    print("3. 启动MindEcho测试")
    print("0. 退出")
    
    try:
        choice = input("\n请选择 (0-3): ").strip()
        
        if choice == '1':
            show_high_freq_optimization()
            print("\n" + "="*60)
            input("按回车键返回主菜单...")
            main()
        
        elif choice == '2':
            test_high_freq_scenarios()
            print("\n" + "="*60)
            input("按回车键继续...")
            main()
        
        elif choice == '3':
            start_high_freq_test()
        
        elif choice == '0':
            print("👋 测试结束")
        
        else:
            print("❌ 无效选择，请重试")
            main()
            
    except KeyboardInterrupt:
        print("\n\n👋 测试被中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")

if __name__ == "__main__":
    main()
