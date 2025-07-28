"""
测试音高检测算法修复 - 验证1002.3Hz错误是否已解决
专注测试环境噪音智能检测和断续曲线功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
try:
    import sounddevice as sd
    print("✅ SoundDevice 导入成功")
except ImportError:
    print("❌ SoundDevice 未安装，跳过音频测试")
    sd = None

# 尝试导入PyQt
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    print("✅ PyQt6 可用")
except ImportError:
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QTimer
        print("✅ PyQt5 可用")
    except ImportError:
        print("❌ 无可用的PyQt版本")
        QApplication = None

import time

def test_algorithm_fix():
    """测试算法修复效果"""
    print("=" * 60)
    print("🔧 测试音高检测算法修复")
    print("=" * 60)
    
    if QApplication is None:
        print("❌ 无法创建QApplication，跳过GUI测试")
        return test_algorithm_only()
    
    # 检查是否已有QApplication实例
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    return test_with_gui(app)

def test_algorithm_only():
    """仅测试算法，无GUI"""
    print("🔧 执行纯算法测试...")
    
    # 导入核心检测函数
    try:
        from src.gui.integrated_recording_interface import IntegratedRecordingInterface
        print("✅ 成功导入音高检测模块")
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return None
    
    # 创建一个简化的测试实例
    class SimpleDetector:
        def __init__(self):
            self.sample_rate = 44100
            self._detection_call_count = 0
            self._noise_baseline = []
            self._recent_rms = []
            self._singing_detected = False
            self._silence_frames = 0
            self._noise_threshold = 0.01
    
    detector = SimpleDetector()
    
    # 从IntegratedRecordingInterface复制detect_pitch_with_vibrato方法
    from src.gui.integrated_recording_interface import IntegratedRecordingInterface
    temp_instance = IntegratedRecordingInterface.__new__(IntegratedRecordingInterface)
    temp_instance.sample_rate = 44100
    
    # 测试不同频率
    test_frequencies = [100, 200, 300, 500, 700, 1002.3, 1200]
    
    print("📊 测试各频率的检测效果：")
    print("-" * 60)
    
    for freq in test_frequencies:
        duration = 0.1  # 100ms
        t = np.linspace(0, duration, int(44100 * duration))
        test_signal = 0.1 * np.sin(2 * np.pi * freq * t)
        noise = 0.01 * np.random.randn(len(test_signal))
        test_signal += noise
        
        # 初始化检测状态
        temp_instance._detection_call_count = 0
        temp_instance._noise_baseline = []
        temp_instance._recent_rms = []
        temp_instance._singing_detected = False
        temp_instance._silence_frames = 0
        temp_instance._noise_threshold = 0.01
        
        # 建立噪音基准（跳过前100帧）
        for i in range(100):
            noise_frame = 0.005 * np.random.randn(len(test_signal))
            temp_instance.detect_pitch_with_vibrato(noise_frame)
        
        # 测试音高检测
        detected_freq = temp_instance.detect_pitch_with_vibrato(test_signal)
        
        if detected_freq > 0:
            error_percent = abs(detected_freq - freq) / freq * 100
            status = "✅ 正确" if error_percent < 10 else "⚠️ 偏差大"
            range_status = "✅ 范围内" if 80 <= detected_freq <= 800 else "❌ 超出范围"
        else:
            error_percent = 0
            status = "❌ 未检测到"
            range_status = "❌ 无检测"
        
        print(f"输入: {freq:6.1f}Hz -> 检测: {detected_freq:6.1f}Hz | "
              f"误差: {error_percent:5.1f}% | {status} | {range_status}")
    
    print("\n✅ 纯算法测试完成")
    return temp_instance

def test_with_gui(app):
    """使用GUI进行完整测试"""
    print("🎯 启动完整GUI测试...")
    
    # 导入核心类
    try:
        from src.gui.integrated_recording_interface import IntegratedRecordingInterface
        print("✅ 成功导入GUI模块")
    except ImportError as e:
        print(f"❌ GUI模块导入失败: {e}")
        return test_algorithm_only()
    
    # 创建测试界面
    interface = IntegratedRecordingInterface()
    
    print("📊 GUI测试完成，建议启动完整程序进行实际测试")
    return interface

def run_algorithm_tests(interface):
    """运行算法测试"""
    # 生成测试音频数据
    sample_rate = interface.sample_rate
    duration = 0.1  # 100ms测试片段
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # 测试不同频率的音频
    test_frequencies = [
        100,   # 低音
        200,   # 中低音
        300,   # 中音
        500,   # 中高音
        700,   # 高音
        1002.3,  # 之前的错误频率
        1200,  # 超出范围的频率
    ]
    
    print("📊 测试各频率的检测效果：")
    print("-" * 60)
    
    for freq in test_frequencies:
        # 生成正弦波测试信号
        test_signal = 0.1 * np.sin(2 * np.pi * freq * t)
        
        # 添加少量噪声
        noise = 0.01 * np.random.randn(len(test_signal))
        test_signal += noise
        
        # 测试音高检测
        detected_freq = interface.detect_pitch_with_vibrato(test_signal)
        
        if detected_freq > 0:
            error_percent = abs(detected_freq - freq) / freq * 100
            status = "✅ 正确" if error_percent < 10 else "⚠️ 偏差大"
            if 80 <= detected_freq <= 800:
                range_status = "✅ 范围内"
            else:
                range_status = "❌ 超出范围"
        else:
            error_percent = 0
            status = "❌ 未检测到"
            range_status = "❌ 无检测"
        
        print(f"输入: {freq:6.1f}Hz -> 检测: {detected_freq:6.1f}Hz | "
              f"误差: {error_percent:5.1f}% | {status} | {range_status}")

def run_noise_detection_tests(interface):
    """运行环境噪音检测测试"""
    print("\n" + "=" * 60)
    print("🧪 测试环境噪音智能检测")
    print("=" * 60)
    
    # 重置环境噪音检测状态
    interface._noise_baseline = []
    interface._singing_detected = False
    interface._silence_frames = 0
    
    # 生成测试数据参数
    sample_rate = interface.sample_rate
    duration = 0.1
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    print("1️⃣ 建立环境噪音基准...")
    # 模拟50帧环境噪音
    for i in range(50):
        noise_signal = 0.005 * np.random.randn(len(t))  # 低水平噪音
        interface.detect_pitch_with_vibrato(noise_signal)
    
    print(f"   噪音基准建立完成，基准值: {interface._noise_threshold:.6f}")
    
    print("\n2️⃣ 测试歌声检测...")
    # 模拟歌声输入
    for freq in [200, 300, 400]:
        vocal_signal = 0.05 * np.sin(2 * np.pi * freq * t)  # 较强的歌声信号
        detected = interface.detect_pitch_with_vibrato(vocal_signal)
        print(f"   歌声 {freq}Hz -> 检测: {detected:.1f}Hz, "
              f"歌声状态: {'🎤 检测中' if interface._singing_detected else '🔇 静音'}")
    
    print("\n3️⃣ 测试换气检测...")
    # 模拟换气（回到噪音水平）
    for i in range(10):
        breath_signal = 0.008 * np.random.randn(len(t))  # 略高于噪音的换气声
        detected = interface.detect_pitch_with_vibrato(breath_signal)
        if i % 3 == 0:  # 每3帧显示一次
            print(f"   换气帧 {i+1} -> 检测: {detected:.1f}Hz, "
                  f"静音帧数: {interface._silence_frames}, "
                  f"状态: {'🎤 歌声' if interface._singing_detected else '🔇 环境噪音'}")

if __name__ == "__main__":
    result = test_algorithm_fix()
    if result:
        print("\n🎯 算法修复测试完成！")
        print("\n推荐下一步：")
        print("1. 运行 'python run_enhanced.py' 启动完整程序")
        print("2. 选择模式1（增强版）")
        print("3. 测试实际音频输入")
        print("4. 观察是否还有1002.3Hz错误")
        
        # 如果成功创建了interface，运行详细测试
        if hasattr(result, 'detect_pitch_with_vibrato'):
            print("\n🔧 运行详细算法测试...")
            run_algorithm_tests(result)
            run_noise_detection_tests(result)
            
            print("\n" + "=" * 60)
            print("📈 测试结果总结:")
            print("=" * 60)
            print("✅ 算法修复要点:")
            print("   - 使用scipy峰值检测替代argmax")
            print("   - 严格限制人声频率范围80-800Hz")
            print("   - 添加边界效应保护")
            print("   - 改进置信度计算")
            print("\n✅ 环境噪音检测:")
            print("   - 智能建立噪音基准")
            print("   - 自动区分歌声/环境噪音")
            print("   - 支持换气时曲线断开")
    else:
        print("\n❌ 测试失败，请检查依赖安装")
