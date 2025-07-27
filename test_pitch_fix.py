"""
快速测试音高检测修复
"""

import sys
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_simple_pitch_detection():
    """测试简单音高检测"""
    print("🔍 测试简单音高检测...")
    
    try:
        from src.gui.integrated_recording_interface import IntegratedAudioProcessor
        
        # 创建音频处理器
        processor = IntegratedAudioProcessor()
        processor.sample_rate = 44100
        
        # 生成测试音频（440Hz正弦波）
        duration = 0.1  # 100ms
        t = np.linspace(0, duration, int(44100 * duration))
        test_audio = 0.5 * np.sin(2 * np.pi * 440 * t)  # A4 = 440Hz
        
        # 测试音高检测
        detected_freq = processor.simple_pitch_detection(test_audio)
        
        print(f"  输入频率: 440 Hz")
        print(f"  检测频率: {detected_freq:.1f} Hz")
        
        if abs(detected_freq - 440) < 10:  # 允许10Hz误差
            print("  ✅ 音高检测正常")
            return True
        else:
            print("  ❌ 音高检测误差过大")
            return False
            
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_note_conversion():
    """测试音符转换"""
    print("\n🔍 测试音符转换...")
    
    try:
        from src.gui.integrated_recording_interface import IntegratedAudioProcessor
        
        processor = IntegratedAudioProcessor()
        
        # 测试A4 = 440Hz
        note_info = processor.frequency_to_note_info(440)
        
        print(f"  440Hz -> {note_info}")
        
        if note_info.get('note_name') == 'A' and note_info.get('octave') == 4:
            print("  ✅ 音符转换正常")
            return True
        else:
            print("  ❌ 音符转换错误")
            return False
            
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        return False

def main():
    print("🎵 MindEcho 音高检测修复测试")
    print("=" * 40)
    
    success = True
    
    # 测试音高检测
    if not test_simple_pitch_detection():
        success = False
    
    # 测试音符转换
    if not test_note_conversion():
        success = False
    
    print("\n" + "=" * 40)
    if success:
        print("🎉 所有测试通过！音高检测已修复。")
        print("\n现在可以启动程序测试:")
        print("  python start_integrated.py")
    else:
        print("❌ 部分测试失败，需要进一步检查。")
    
    input("\n按回车键退出...")

if __name__ == "__main__":
    main()
