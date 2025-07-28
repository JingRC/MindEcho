"""
快速测试调整后的高频音高检测能力
"""

import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_yin_detector import EnhancedYIN, StabilizedAudioProcessor

def quick_test():
    """快速测试"""
    print("🔧 快速测试调整后的高频检测能力")
    print("="*50)
    
    # 创建简单测试信号
    sr = 44100
    duration = 0.4
    t = np.linspace(0, duration, int(sr * duration))
    
    # 测试频率
    test_frequencies = {
        'C4 (261Hz)': 261.6,
        'A4 (440Hz)': 440.0,
        'D5 (587Hz)': 587.3,
        'F5 (698Hz)': 698.5,
        'C6 (1047Hz)': 1047.0
    }
    
    # 初始化处理器
    yin_processor = EnhancedYIN(sr=sr, frame_size=1024)
    stabilized_processor = StabilizedAudioProcessor(yin_processor)
    
    for note_name, freq in test_frequencies.items():
        print(f"\n🎵 测试 {note_name}")
        print("-" * 30)
        
        # 生成带谐波的信号
        fundamental = 0.7 * np.sin(2 * np.pi * freq * t)
        harmonic2 = 0.25 * np.sin(2 * np.pi * freq * 2 * t)
        harmonic3 = 0.12 * np.sin(2 * np.pi * freq * 3 * t)
        signal = fundamental + harmonic2 + harmonic3
        
        # 添加包络，模拟真实音符
        envelope = np.exp(-1 * np.abs(t - duration/2))
        signal *= envelope
        
        # 分块处理
        chunk_size = 1024
        detections = []
        confidences = []
        
        for i in range(0, len(signal) - chunk_size, chunk_size // 8):  # 更多重叠
            chunk = signal[i:i + chunk_size]
            detected_freq, conf = stabilized_processor.process_with_stability(chunk)
            
            if detected_freq > 0 and conf > 0.1:
                detections.append(detected_freq)
                confidences.append(conf)
        
        # 分析结果
        if detections:
            mean_freq = np.mean(detections)
            mean_conf = np.mean(confidences)
            accuracy = abs(mean_freq - freq) / freq * 100
            detection_rate = len(detections)
            
            print(f"  ✅ 检测成功!")
            print(f"    目标频率: {freq:.1f} Hz")
            print(f"    检测频率: {mean_freq:.1f} Hz")
            print(f"    精度: {100-accuracy:.1f}% (误差: {accuracy:.1f}%)")
            print(f"    平均置信度: {mean_conf:.2f}")
            print(f"    检测次数: {detection_rate}")
            
            if accuracy < 5:
                print(f"    🎯 精度: 优秀")
            elif accuracy < 10:
                print(f"    ✅ 精度: 良好")
            else:
                print(f"    ⚠️  精度: 需改进")
        else:
            print(f"  ❌ 未检测到音高")
            if freq > 500:
                print(f"    可能原因: 高频检测参数仍需调整")
            else:
                print(f"    可能原因: 检测阈值过高或信号太弱")
    
    print(f"\n" + "="*50)
    print(f"🚀 测试完成! 现在可以启动MindEcho增强版进行实际录音测试")

if __name__ == "__main__":
    quick_test()
