#!/usr/bin/env python3
"""
诊断MindEcho音频流问题
检查为什么连关闭降噪也不显示音高
"""

import sys
import os
import time
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_simple_audio_detection():
    """测试简单的音频检测，不依赖复杂的处理逻辑"""
    print("=" * 60)
    print("🔍 诊断MindEcho音频流问题")
    print("=" * 60)
    
    try:
        import sounddevice as sd
        
        print("1. 测试sounddevice基本功能...")
        
        # 测试音频设备
        devices = sd.query_devices()
        print(f"✅ 找到 {len(devices)} 个音频设备")
        
        default_input = sd.query_devices(kind='input')
        print(f"✅ 默认输入设备: {default_input['name']}")
        
        # 测试简单录音
        print("\n2. 测试5秒简单录音...")
        print("请对麦克风说话...")
        
        sample_rate = 44100
        duration = 5
        
        # 录制音频
        audio_data = sd.rec(int(duration * sample_rate), 
                           samplerate=sample_rate, 
                           channels=1, 
                           dtype=np.float32)
        sd.wait()  # 等待录音完成
        
        # 计算音频统计
        audio_rms = np.sqrt(np.mean(audio_data ** 2))
        audio_max = np.max(np.abs(audio_data))
        
        print(f"✅ 录音完成!")
        print(f"   音频长度: {len(audio_data)} 样本")
        print(f"   RMS值: {audio_rms:.6f}")
        print(f"   峰值: {audio_max:.6f}")
        
        if audio_rms > 0.001:
            print("✅ 音频信号正常 - 麦克风工作正常")
        else:
            print("❌ 音频信号太弱 - 可能麦克风问题")
            
        # 测试简单音高检测
        print("\n3. 测试简单音高检测...")
        
        def simple_pitch_detection(audio):
            """超简单的音高检测"""
            # 自相关
            windowed = audio.flatten() * np.hanning(len(audio))
            correlation = np.correlate(windowed, windowed, mode='full')
            correlation = correlation[len(correlation)//2:]
            
            # 寻找峰值
            min_period = int(sample_rate / 2000)  # 最高2000Hz
            max_period = int(sample_rate / 50)    # 最低50Hz
            
            if max_period < len(correlation):
                search_range = correlation[min_period:max_period]
                if len(search_range) > 0:
                    peak_index = np.argmax(search_range) + min_period
                    frequency = sample_rate / peak_index
                    
                    # 简单置信度
                    peak_value = correlation[peak_index]
                    base_value = correlation[0] if correlation[0] > 0 else 1e-10
                    confidence = peak_value / base_value
                    
                    return frequency, confidence
            
            return 0, 0
        
        frequency, confidence = simple_pitch_detection(audio_data)
        
        print(f"检测结果:")
        print(f"   频率: {frequency:.1f} Hz")
        print(f"   置信度: {confidence:.3f}")
        
        if frequency > 50 and confidence > 0.01:
            print("✅ 音高检测成功 - 算法工作正常")
        else:
            print("❌ 音高检测失败 - 可能信号太弱或算法问题")
            
    except ImportError as e:
        print(f"❌ 导入sounddevice失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 音频测试失败: {e}")
        return False
        
def test_mindecho_audio_flow():
    """测试MindEcho的音频流程"""
    print("\n" + "=" * 60)
    print("🔍 测试MindEcho音频流程")
    print("=" * 60)
    
    try:
        from src.gui.integrated_recording_interface import IntegratedAudioProcessor
        
        print("1. 创建音频处理器...")
        processor = IntegratedAudioProcessor()
        
        print("2. 测试音高检测方法...")
        
        # 创建测试音频数据（440Hz正弦波）
        sample_rate = 44100
        duration = 1.0
        frequency = 440.0
        
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        test_audio = 0.1 * np.sin(2 * np.pi * frequency * t)
        
        print(f"生成测试音频: {frequency}Hz, 时长{duration}s")
        
        # 测试音高检测
        detected_freq = processor.detect_pitch_with_vibrato(test_audio)
        
        print(f"检测结果: {detected_freq:.1f}Hz")
        
        if abs(detected_freq - frequency) < 10:
            print("✅ 音高检测方法工作正常")
        else:
            print("❌ 音高检测方法有问题")
            
        print("\n3. 检查降噪处理器...")
        if hasattr(processor, 'noise_processor') and processor.noise_processor:
            print("✅ 降噪处理器存在")
            print(f"   降噪模式: {processor.noise_processor.noise_reduction_mode}")
        else:
            print("❌ 降噪处理器不存在")
            
    except Exception as e:
        print(f"❌ MindEcho音频流程测试失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主函数"""
    print("🔍 MindEcho音频问题诊断工具")
    print("用于诊断：关闭降噪模式也不显示声音曲线的问题")
    
    # 基础音频测试
    test_simple_audio_detection()
    
    # MindEcho特定测试
    test_mindecho_audio_flow()
    
    print("\n" + "=" * 60)
    print("📋 诊断建议:")
    print("1. 如果基础音频测试失败 → 检查麦克风设置和权限")
    print("2. 如果音高检测方法失败 → 检查算法实现")
    print("3. 如果都正常但MindEcho不工作 → 检查音频流程集成")
    print("=" * 60)

if __name__ == "__main__":
    main()
