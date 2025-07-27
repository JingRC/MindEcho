"""
MindEcho 音高检测问题诊断和修复验证
"""

import sys
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    print("🎵 MindEcho 音高检测修复验证")
    print("=" * 50)
    
    # 1. 检查修复状态
    print("1. 检查修复内容...")
    
    try:
        from src.gui.integrated_recording_interface import IntegratedAudioProcessor
        processor = IntegratedAudioProcessor()
        print("  ✅ IntegratedAudioProcessor 类加载成功")
        
        # 检查是否有simple_pitch_detection方法
        if hasattr(processor, 'simple_pitch_detection'):
            print("  ✅ simple_pitch_detection 方法存在")
        else:
            print("  ❌ simple_pitch_detection 方法不存在")
        
        # 检查process_audio_for_pitch方法
        if hasattr(processor, 'process_audio_for_pitch'):
            print("  ✅ process_audio_for_pitch 方法存在")
        else:
            print("  ❌ process_audio_for_pitch 方法不存在")
            
    except Exception as e:
        print(f"  ❌ 类加载失败: {e}")
        return
    
    # 2. 测试音高检测算法
    print("\n2. 测试音高检测算法...")
    
    try:
        # 生成测试信号
        sample_rate = 44100
        duration = 0.1  # 100ms
        frequency = 440  # A4
        
        t = np.linspace(0, duration, int(sample_rate * duration))
        test_signal = 0.5 * np.sin(2 * np.pi * frequency * t)
        
        processor.sample_rate = sample_rate
        detected_freq = processor.simple_pitch_detection(test_signal)
        
        print(f"  输入: {frequency} Hz (A4)")
        print(f"  检测: {detected_freq:.1f} Hz")
        
        error = abs(detected_freq - frequency)
        if error < 20:  # 允许20Hz误差
            print(f"  ✅ 检测正确 (误差: {error:.1f} Hz)")
        else:
            print(f"  ⚠️ 检测误差较大 (误差: {error:.1f} Hz)")
            
    except Exception as e:
        print(f"  ❌ 音高检测测试失败: {e}")
    
    # 3. 测试音符转换
    print("\n3. 测试音符转换...")
    
    try:
        note_info = processor.frequency_to_note_info(440)
        print(f"  440 Hz -> {note_info}")
        
        if note_info.get('note_name') == 'A' and note_info.get('octave') == 4:
            print("  ✅ 音符转换正确")
        else:
            print("  ❌ 音符转换错误")
            
    except Exception as e:
        print(f"  ❌ 音符转换测试失败: {e}")
    
    # 4. 总结
    print("\n" + "=" * 50)
    print("📋 修复总结:")
    print("• 移除了有问题的重叠帧分析器")
    print("• 使用稳定的自相关音高检测算法")
    print("• 修复了数组广播错误")
    print("• 简化了音频处理流程")
    print()
    print("🚀 现在可以启动程序:")
    print("   python start_integrated.py")
    print("   或")
    print("   python run_enhanced.py  (选择选项1)")
    
    input("\n按回车键退出...")

if __name__ == "__main__":
    main()
