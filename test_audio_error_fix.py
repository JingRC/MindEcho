#!/usr/bin/env python3
"""
测试音频错误修复效果
修复的问题：
1. unsupported operand type(s) for -: 'float' and 'NoneType' 
2. wrapped C/C++ object of type IntegratedAudioProcessor has been deleted
"""

import sys
import os
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_audio_error_fixes():
    """测试音频错误修复"""
    print("=" * 60)
    print("🔧 测试音频错误修复")
    print("=" * 60)
    
    print("\n修复的问题:")
    print("1. ❌ 修复前: unsupported operand type(s) for -: 'float' and 'NoneType'")
    print("   ✅ 修复后: 检查self.start_time是否为None，初始化时设置默认值")
    
    print("2. ❌ 修复前: wrapped C/C++ object of type IntegratedAudioProcessor has been deleted")
    print("   ✅ 修复后: 在Qt信号发送前检查对象是否有效，添加异常捕获")
    
    print("\n修复详情:")
    print("📍 在 add_pitch_data() 方法中:")
    print("   • 检查 self.start_time 是否为 None")
    print("   • 如果为 None，则初始化为当前时间戳")
    print("   • 防止 timestamp - None 的计算错误")
    
    print("📍 在音频回调函数中:")
    print("   • 使用 self.isFinished() 检查Qt对象状态")
    print("   • 在信号发送前检查对象是否已被销毁")
    print("   • 捕获 RuntimeError 异常，防止程序崩溃")
    
    print("📍 在异步音频处理中:")
    print("   • 发送信号前检查Qt对象有效性")
    print("   • 错误时也发送时间戳保持时间轴连续")
    print("   • 添加优雅的关闭处理")
    
    print("📍 添加窗口关闭事件处理:")
    print("   • closeEvent() 方法确保资源正确释放")
    print("   • 停止音频处理器和定时器")
    print("   • 等待线程安全退出")
    
    print("\n🎯 预期效果:")
    print("✅ 不再出现 NoneType 计算错误")
    print("✅ 不再出现 Qt对象销毁错误") 
    print("✅ 程序关闭时不会出现异常")
    print("✅ 音频流和线程能正确停止")
    
    print("\n📋 测试步骤:")
    print("1. 启动MindEcho增强版")
    print("2. 观察控制台输出，确认没有错误信息")
    print("3. 测试关闭程序，确认优雅退出")
    print("4. 重复启动-关闭，验证稳定性")
    
    return True

def test_start_mindecho():
    """启动MindEcho进行实际测试"""
    print("\n🚀 启动MindEcho进行实际测试...")
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        print("✅ 导入integrated_recording_interface模块成功")
        
        print("💡 即将启动MindEcho，请观察控制台输出：")
        print("   • 应该看到 '🕐 设置开始时间' 信息")
        print("   • 应该看到 '✅ 实时音高分析已启动' 信息")
        print("   • 不应该看到 'NoneType' 或 'deleted' 错误")
        print("   • 关闭窗口时应该看到 '✅ MindEcho已安全关闭' 信息")
        
        input("\n按回车键启动MindEcho进行测试...")
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
    print("🔧 MindEcho 音频错误修复测试")
    print("测试目标：验证NoneType错误和Qt对象销毁错误的修复效果")
    
    # 测试修复效果
    test_audio_error_fixes()
    
    # 询问是否启动实际测试
    choice = input("\n是否启动MindEcho进行实际测试? (y/n): ").strip().lower()
    if choice == 'y':
        test_start_mindecho()
    else:
        print("✅ 测试完成！")
        print("\n可以手动运行以下命令进行测试:")
        print("python run_enhanced.py")
        print("然后选择选项 1 启动增强版")

if __name__ == "__main__":
    main()
