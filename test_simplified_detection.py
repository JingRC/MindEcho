#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试简化的音高检测系统
验证：
1. 只使用单一算法 detect_pitch_with_vibrato
2. 智能平滑算法是否有效控制抖动
3. 降噪模式是否真正区分"关闭"和"基础频域降噪"
"""

import numpy as np
import time
import sys
import os

# 添加src路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def test_single_algorithm():
    """测试单一算法的效果"""
    print("🎯 测试1: 验证单一算法")
    print("=" * 50)
    
    try:
        from src.gui.integrated_recording_interface import IntegratedAudioProcessor
        
        processor = IntegratedAudioProcessor()
        processor.sample_rate = 44100
        
        # 生成测试音频：稳定440Hz + 小范围噪音
        duration = 0.5  # 🎯 增加到500ms，提供足够的信号长度
        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 基础440Hz信号
        base_signal = 0.3 * np.sin(2 * np.pi * 440 * t)
        
        print("\n测试稳定歌声的平滑效果:")
        print("-" * 30)
        
        # 🎯 改进测试信号生成
        frequencies = []
        for i in range(10):
            # 添加小范围随机变化模拟真实歌声
            noise_freq = 440 + np.random.uniform(-8, 8)  # ±8Hz随机变化
            test_signal = 0.3 * np.sin(2 * np.pi * noise_freq * t)
            # 🎯 进一步减少噪音，确保是清晰的测试信号
            test_signal += np.random.normal(0, 0.001, len(test_signal))  # 极少噪音
            
            # 🎯 不重置状态，让算法自己判断是否为测试信号
            # 只调用一次检测算法
            detected_freq = processor.detect_pitch_with_vibrato(test_signal)
            frequencies.append(detected_freq)
            
            print(f"第{i+1:2d}次: 输入={noise_freq:.1f}Hz → 检测={detected_freq:.1f}Hz")
        
        # 分析结果
        valid_frequencies = [f for f in frequencies if f > 0]
        if len(valid_frequencies) > 0:
            mean_freq = np.mean(valid_frequencies)
            std_freq = np.std(valid_frequencies)
            
            print(f"\n📊 结果分析:")
            print(f"   有效检测: {len(valid_frequencies)}/10")
            print(f"   平均频率: {mean_freq:.1f}Hz")
            print(f"   标准差: {std_freq:.1f}Hz")
            
            if std_freq < 10:
                print("   ✅ 平滑效果良好，抖动控制在10Hz以内")
            elif std_freq < 20:
                print("   ⚠️ 平滑效果一般，还有改进空间")
            else:
                print("   ❌ 平滑效果不佳，抖动仍然严重")
        else:
            print("   ❌ 没有检测到有效音高")
            
        return len(valid_frequencies) > 7 and (std_freq < 15 if len(valid_frequencies) > 0 else False)
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_noise_reduction_modes():
    """测试降噪模式的区别"""
    print("\n🎯 测试2: 验证降噪模式区别")
    print("=" * 50)
    
    try:
        from src.gui.integrated_recording_interface import IntegratedAudioProcessor
        
        processor = IntegratedAudioProcessor()
        processor.sample_rate = 44100
        
        # 生成带噪音的测试信号
        duration = 0.5  # 🎯 增加信号长度
        t = np.linspace(0, duration, int(44100 * duration))
        clean_signal = 0.3 * np.sin(2 * np.pi * 440 * t)
        noise = np.random.normal(0, 0.02, len(clean_signal))  # 🎯 适量噪音，测试降噪效果
        noisy_signal = clean_signal + noise
        
        # 测试关闭降噪
        print("\n测试: 关闭降噪")
        if processor.noise_processor:
            processor.set_noise_reduction_mode("关闭")
        freq_no_denoise = processor.detect_pitch_with_vibrato(noisy_signal)
        print(f"   关闭降噪检测结果: {freq_no_denoise:.1f}Hz")
        
        # 测试基础频域降噪
        print("\n测试: 基础频域降噪")
        if processor.noise_processor:
            processor.set_noise_reduction_mode("基础频域降噪")
        freq_basic_denoise = processor.detect_pitch_with_vibrato(noisy_signal)
        print(f"   基础降噪检测结果: {freq_basic_denoise:.1f}Hz")
        
        # 分析差异
        if freq_no_denoise > 0 and freq_basic_denoise > 0:
            diff = abs(freq_no_denoise - freq_basic_denoise)
            print(f"\n📊 模式差异分析:")
            print(f"   频率差异: {diff:.1f}Hz")
            
            if diff > 2:
                print("   ✅ 降噪模式有明显区别")
                return True
            else:
                print("   ⚠️ 降噪模式差异较小，可能仍有重叠")
                return False
        else:
            print("   ❌ 检测失败，无法比较")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_algorithm_count():
    """验证算法数量是否真的简化了"""
    print("\n🎯 测试3: 验证算法简化")
    print("=" * 50)
    
    # 检查代码中是否还有多个算法调用
    import inspect
    from src.gui.integrated_recording_interface import IntegratedAudioProcessor
    
    processor = IntegratedAudioProcessor()
    
    # 检查process_audio_for_pitch_async方法的源代码
    source = inspect.getsource(processor.process_audio_for_pitch_async)
    
    # 统计检测算法调用次数
    detection_calls = []
    if "detect_pitch_with_vibrato" in source:
        detection_calls.append("detect_pitch_with_vibrato")
    if "simple_pitch_detection" in source:
        detection_calls.append("simple_pitch_detection")
    if "enhanced_yin" in source.lower():
        detection_calls.append("enhanced_yin")
    if "improved_processor" in source.lower():
        detection_calls.append("improved_processor")
    
    print(f"📊 检测到的算法调用:")
    for call in detection_calls:
        print(f"   - {call}")
    
    if len(detection_calls) == 1 and detection_calls[0] == "detect_pitch_with_vibrato":
        print("   ✅ 算法简化成功，只使用单一检测方法")
        return True
    else:
        print(f"   ❌ 仍有多个算法调用 ({len(detection_calls)}个)")
        return False

def main():
    """主测试函数"""
    print("🚀 MindEcho 简化音高检测系统测试")
    print("=" * 60)
    
    results = []
    
    # 测试1: 单一算法效果
    results.append(test_single_algorithm())
    
    # 测试2: 降噪模式区别
    results.append(test_noise_reduction_modes())
    
    # 测试3: 算法简化验证
    results.append(test_algorithm_count())
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    test_names = [
        "单一算法平滑效果",
        "降噪模式区别",
        "算法简化验证"
    ]
    
    passed = 0
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"测试{i+1}: {name} - {status}")
        if result:
            passed += 1
    
    print(f"\n总体结果: {passed}/{len(results)} 项测试通过")
    
    if passed == len(results):
        print("🎉 所有测试通过！简化方案实施成功")
        print("\n💡 预期效果:")
        print("   • 稳定歌声显示为小范围自然变化")
        print("   • 不再有剧烈抖动")
        print("   • 降噪模式有明显区别")
        print("   • 系统响应更快，CPU占用更低")
    else:
        print("⚠️ 部分测试失败，需要进一步调优")
    
    return passed == len(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
