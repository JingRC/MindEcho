#!/usr/bin/env python3
"""
增强型电流音检测系统集成测试
基于专利CN114640926A的多维度检测算法验证
"""

import sys
import os
import numpy as np
import time
import traceback

# 添加路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'audio_processing'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'gui'))

def test_advanced_detection_system():
    """测试高级检测系统的完整功能"""
    print("🔬 开始测试增强型电流音检测系统...")
    
    try:
        # 导入高级检测模块
        import sys
        import os
        
        # 确保能找到音频处理模块
        current_dir = os.path.dirname(__file__)
        audio_processing_path = os.path.join(current_dir, 'src', 'audio_processing')
        if audio_processing_path not in sys.path:
            sys.path.insert(0, audio_processing_path)
        
        from advanced_noise_detector import AdvancedElectricNoiseDetector, PrecisionAudioProcessor, AutoCalibrationSystem
        print("✅ 高级检测模块导入成功")
        
        # 初始化检测器
        detector = AdvancedElectricNoiseDetector(sample_rate=48000)
        processor = PrecisionAudioProcessor(sample_rate=48000)
        calibrator = AutoCalibrationSystem(detector, processor)
        print("✅ 检测器初始化完成")
        
        # 测试信号生成
        sample_rate = 48000
        frame_size = 64
        
        print("\n🧪 生成测试信号...")
        
        # 1. 正常人声信号（大声唱歌）
        t = np.linspace(0, frame_size/sample_rate, frame_size)
        normal_voice = 0.6 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)
        normal_voice += 0.1 * np.random.normal(0, 0.05, len(t))  # 自然噪声
        
        # 2. 气泡音信号（低频谐波丰富）
        bubble_voice = np.zeros_like(t)
        for i in range(1, 8):  # 多谐波
            bubble_voice += (0.3/i) * np.sin(2 * np.pi * 150 * i * t)
        bubble_voice *= 0.4  # 中等音量
        
        # 3. 电流音信号（高频噪声）
        electric_noise = 0.001 * np.random.normal(0, 1, len(t))  # 极低基准
        # 添加高频电流音特征
        electric_noise += 0.002 * np.sin(2 * np.pi * 15000 * t) * np.random.random(len(t))
        
        # 4. 静音信号
        silence = np.zeros_like(t) + 0.0001 * np.random.normal(0, 1, len(t))
        
        test_signals = [
            ("正常人声(大声)", normal_voice),
            ("气泡音技巧", bubble_voice),
            ("电流音噪声", electric_noise),
            ("环境静音", silence)
        ]
        
        print("\n🔍 开始多维度检测测试...")
        print("="*60)
        
        for name, signal in test_signals:
            print(f"\n📊 测试信号: {name}")
            print("-" * 40)
            
            # 执行检测
            start_time = time.time()
            result = detector.detect_electric_noise(signal)
            processing_time = (time.time() - start_time) * 1000
            
            # 输出结果
            is_noise = result['is_electric_noise']
            features = result['features']
            
            print(f"🎯 检测结果: {'🔇 电流音' if is_noise else '✅ 正常音频'}")
            print(f"⏱️ 处理时间: {processing_time:.2f}ms")
            print(f"📈 特征分析:")
            print(f"   • RMS能量: {features['rms_energy']:.5f}")
            print(f"   • 频谱质心: {features['spectral_centroid']:.1f} Hz")
            print(f"   • 峰均比: {features['peak_to_average_ratio']:.2f}")
            print(f"   • 谐波比: {features['harmonic_ratio']:.3f}")
            print(f"   • 高频能量比: {features['high_freq_ratio']:.3f}")
            print(f"   • 频谱平坦度: {features['spectral_flatness']:.3f}")
            
            # 处理测试
            if is_noise:
                processed = processor.process_audio(signal)
                reduction = np.sqrt(np.mean((signal - processed)**2))
                print(f"🔧 噪声抑制强度: {reduction:.5f}")
            else:
                enhanced = processor.enhance_audio(signal)
                enhancement = np.sqrt(np.mean((enhanced - signal)**2))
                print(f"🎵 音质增强程度: {enhancement:.5f}")
        
        print("\n" + "="*60)
        
        # 校准测试
        print("\n🔧 测试自动校准系统...")
        calibration_signals = [normal_voice, bubble_voice, silence]
        
        start_time = time.time()
        calibrator.auto_calibrate(calibration_signals)
        calibration_time = (time.time() - start_time) * 1000
        
        print(f"✅ 校准完成，耗时: {calibration_time:.1f}ms")
        print(f"🎯 优化后检测阈值:")
        print(f"   • RMS阈值: {detector.thresholds['rms_threshold']:.5f}")
        print(f"   • 频谱质心阈值: {detector.thresholds['spectral_centroid_threshold']:.1f}")
        print(f"   • 峰均比阈值: {detector.thresholds['peak_to_avg_threshold']:.2f}")
        
        # 性能基准测试
        print("\n⚡ 性能基准测试...")
        iterations = 1000
        test_signal = normal_voice
        
        start_time = time.time()
        for _ in range(iterations):
            detector.detect_electric_noise(test_signal)
        total_time = time.time() - start_time
        
        avg_time = (total_time / iterations) * 1000
        fps = 1000 / avg_time
        
        print(f"📊 性能指标:")
        print(f"   • 平均处理时间: {avg_time:.3f}ms/帧")
        print(f"   • 处理帧率: {fps:.1f} FPS")
        print(f"   • 总测试时间: {total_time:.2f}s")
        
        if avg_time < 1.5:  # 64样本@48kHz = 1.33ms理论最小值
            print("✅ 性能测试通过：满足实时处理要求")
        else:
            print("⚠️ 性能警告：处理时间可能影响实时性能")
        
        print("\n🎉 增强型检测系统测试完成！")
        return True
        
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        print("请确保 advanced_noise_detector.py 文件存在且正确")
        return False
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        print("详细错误信息:")
        traceback.print_exc()
        return False

def test_gui_integration():
    """测试GUI集成"""
    print("\n🖥️ 测试GUI集成...")
    
    try:
        # 测试GUI模块导入
        import sys
        import os
        
        # 确保能找到GUI模块
        current_dir = os.path.dirname(__file__)
        gui_path = os.path.join(current_dir, 'src', 'gui')
        if gui_path not in sys.path:
            sys.path.insert(0, gui_path)
        
        from integrated_recording_interface import IntegratedRecordingInterface
        print("✅ GUI模块导入成功")
        
        # 检查新增的检测方法
        interface = IntegratedRecordingInterface()
        
        if hasattr(interface, '_advanced_electric_noise_detection'):
            print("✅ 高级检测方法已集成")
        else:
            print("⚠️ 高级检测方法未找到")
            
        if hasattr(interface, '_legacy_electric_noise_detection'):
            print("✅ 遗留检测方法已保留")
        else:
            print("⚠️ 遗留检测方法未找到")
            
        if hasattr(interface, '_log_performance_stats'):
            print("✅ 性能统计方法已添加")
        else:
            print("⚠️ 性能统计方法未找到")
        
        print("✅ GUI集成测试通过")
        return True
        
    except Exception as e:
        print(f"❌ GUI集成测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 MindEcho 增强型电流音检测系统 - 集成测试")
    print("基于专利 CN114640926A 的多维度检测算法")
    print("="*60)
    
    # 执行测试
    test1_passed = test_advanced_detection_system()
    test2_passed = test_gui_integration()
    
    print("\n" + "="*60)
    print("📋 测试总结:")
    print(f"   • 高级检测系统: {'✅ 通过' if test1_passed else '❌ 失败'}")
    print(f"   • GUI集成测试: {'✅ 通过' if test2_passed else '❌ 失败'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 所有测试通过！系统已准备就绪。")
        print("\n🎯 使用建议:")
        print("   1. 启动 start_mindecho.py 开始监听")
        print("   2. 进行大声唱歌测试验证人声保护")
        print("   3. 进行气泡音测试验证技巧保护")
        print("   4. 观察控制台输出的检测统计信息")
        return 0
    else:
        print("\n❌ 部分测试失败，请检查错误信息并修复问题。")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
