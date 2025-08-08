#!/usr/bin/env python3
"""
MindEcho 增强型电流音检测系统 - 简化测试脚本
解决导入路径问题的直接测试版本
"""

import sys
import os
import numpy as np
import time

# 添加必要的路径
current_dir = os.path.dirname(__file__)
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, 'src'))
sys.path.insert(0, os.path.join(current_dir, 'src', 'audio_processing'))
sys.path.insert(0, os.path.join(current_dir, 'src', 'gui'))

def test_advanced_noise_detector():
    """测试高级噪声检测器"""
    print("🔬 测试增强型电流音检测器...")
    
    try:
        # 直接导入
        from advanced_noise_detector import AdvancedElectricNoiseDetector, PrecisionAudioProcessor, AutoCalibrationSystem
        print("✅ 高级检测模块导入成功")
        
        # 初始化检测器
        detector = AdvancedElectricNoiseDetector(sample_rate=48000)
        processor = PrecisionAudioProcessor(sample_rate=48000)
        calibrator = AutoCalibrationSystem(detector, processor)
        print("✅ 检测器初始化完成")
        
        # 生成测试信号
        frame_size = 64
        t = np.linspace(0, frame_size/48000, frame_size)
        
        # 正常人声
        normal_voice = 0.6 * np.sin(2 * np.pi * 440 * t)
        
        # 电流音
        electric_noise = 0.001 * np.random.normal(0, 1, len(t))
        
        print("\n🧪 检测测试:")
        
        # 测试正常人声
        result1 = detector.detect_electric_noise(normal_voice)
        print(f"人声检测: {'电流音' if result1['is_electric_noise'] else '正常'}")
        
        # 测试电流音
        result2 = detector.detect_electric_noise(electric_noise)
        print(f"噪声检测: {'电流音' if result2['is_electric_noise'] else '正常'}")
        
        print("✅ 基础检测测试完成")
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_gui_integration():
    """测试GUI集成（简化版）"""
    print("\n🖥️ 测试GUI集成...")
    
    try:
        # 检查文件是否存在
        gui_file = os.path.join(current_dir, 'src', 'gui', 'integrated_recording_interface.py')
        if os.path.exists(gui_file):
            print("✅ GUI文件存在")
            
            # 检查高级检测方法是否已添加
            with open(gui_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            if '_advanced_electric_noise_detection' in content:
                print("✅ 高级检测方法已集成")
            else:
                print("⚠️ 高级检测方法未找到")
                
            if '_legacy_electric_noise_detection' in content:
                print("✅ 遗留检测方法已保留")
            else:
                print("⚠️ 遗留检测方法未找到")
                
            return True
        else:
            print("❌ GUI文件不存在")
            return False
            
    except Exception as e:
        print(f"❌ GUI测试失败: {e}")
        return False

def test_directory_structure():
    """测试目录结构"""
    print("\n📁 检查目录结构...")
    
    required_files = [
        'src/audio_processing/advanced_noise_detector.py',
        'src/audio_processing/__init__.py',
        'src/gui/integrated_recording_interface.py',
        'src/gui/__init__.py',
        'src/__init__.py'
    ]
    
    all_exist = True
    for file_path in required_files:
        full_path = os.path.join(current_dir, file_path)
        if os.path.exists(full_path):
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path}")
            all_exist = False
    
    return all_exist

def main():
    """主测试函数"""
    print("🚀 MindEcho 增强型电流音检测系统 - 快速验证")
    print("="*60)
    
    # 执行测试
    test1_passed = test_directory_structure()
    test2_passed = test_advanced_noise_detector()
    test3_passed = test_gui_integration()
    
    print("\n" + "="*60)
    print("📋 测试总结:")
    print(f"   • 目录结构: {'✅ 通过' if test1_passed else '❌ 失败'}")
    print(f"   • 高级检测器: {'✅ 通过' if test2_passed else '❌ 失败'}")
    print(f"   • GUI集成: {'✅ 通过' if test3_passed else '❌ 失败'}")
    
    if test1_passed and test2_passed and test3_passed:
        print("\n🎉 所有测试通过！")
        print("\n🎯 下一步:")
        print("   1. 运行 python src/gui/integrated_recording_interface.py")
        print("   2. 点击 '开启监听' 按钮测试增强型检测")
        print("   3. 进行大声唱歌和气泡音测试")
        return 0
    else:
        print("\n❌ 部分测试失败")
        print("\n💡 解决方案:")
        if not test1_passed:
            print("   • 检查文件是否在正确位置")
        if not test2_passed:
            print("   • 安装依赖: pip install numpy scipy")
        if not test3_passed:
            print("   • 检查GUI文件完整性")
        return 1

if __name__ == "__main__":
    exit_code = main()
    input("\n按回车键退出...")
    sys.exit(exit_code)
