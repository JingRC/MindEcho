"""
测试增强YIN算法对高频音高的处理能力
验证是否能区分真实高音和环境噪音
"""

import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from enhanced_yin_detector import EnhancedYIN, StabilizedAudioProcessor

def create_test_signals():
    """生成各种测试信号"""
    sr = 44100
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration))
    
    signals = {}
    
    # 1. D5 (587Hz) 真实音高 - 带谐波结构
    d5_fundamental = 0.6 * np.sin(2 * np.pi * 587 * t)
    d5_harmonic2 = 0.25 * np.sin(2 * np.pi * 1174 * t)  # 八度
    d5_harmonic3 = 0.12 * np.sin(2 * np.pi * 1761 * t)  # 第三谐波
    signals['D5_真实音高'] = d5_fundamental + d5_harmonic2 + d5_harmonic3
    
    # 2. F5 (698Hz) 更高的音高
    f5_fundamental = 0.7 * np.sin(2 * np.pi * 698 * t)
    f5_harmonic2 = 0.3 * np.sin(2 * np.pi * 1396 * t)
    f5_harmonic3 = 0.15 * np.sin(2 * np.pi * 2094 * t)
    signals['F5_更高音高'] = f5_fundamental + f5_harmonic2 + f5_harmonic3
    
    # 3. C6 (1047Hz) 女高音音域
    c6_fundamental = 0.5 * np.sin(2 * np.pi * 1047 * t)
    c6_harmonic2 = 0.2 * np.sin(2 * np.pi * 2094 * t)
    signals['C6_女高音'] = c6_fundamental + c6_harmonic2
    
    # 4. 587Hz 环境噪音 - 无谐波结构
    noise_587 = 0.4 * np.sin(2 * np.pi * 587 * t)  # 纯正弦波，无谐波
    noise_587 += 0.15 * np.random.normal(0, 1, len(t))  # 加噪音
    signals['587Hz_环境噪音'] = noise_587
    
    # 5. 随机高频噪音
    random_noise = np.random.normal(0, 0.3, len(t))
    # 添加一些高频分量模拟环境噪音
    for freq in [600, 800, 1200]:
        random_noise += 0.1 * np.sin(2 * np.pi * freq * t + np.random.random() * 2 * np.pi)
    signals['随机高频噪音'] = random_noise
    
    # 6. C4到D5的音阶 - 连续音高变化
    freqs = [261.6, 293.7, 329.6, 349.2, 392.0, 440.0, 493.9, 587.3]  # C4-D5
    scale_signal = np.zeros_like(t)
    segment_length = len(t) // len(freqs)
    
    for i, freq in enumerate(freqs):
        start_idx = i * segment_length
        end_idx = (i + 1) * segment_length if i < len(freqs) - 1 else len(t)
        segment_t = t[start_idx:end_idx] - t[start_idx]
        
        # 带谐波的音符
        fundamental = 0.6 * np.sin(2 * np.pi * freq * segment_t)
        harmonic2 = 0.2 * np.sin(2 * np.pi * freq * 2 * segment_t)
        scale_signal[start_idx:end_idx] = fundamental + harmonic2
    
    signals['C4到D5音阶'] = scale_signal
    
    return signals, sr

def test_enhanced_yin():
    """测试增强YIN算法"""
    print("🎵 测试增强YIN算法对高频音高的处理能力")
    print("="*60)
    
    # 创建测试信号
    signals, sr = create_test_signals()
    
    # 初始化增强YIN处理器
    yin_processor = EnhancedYIN(sr=sr, frame_size=1024)
    stabilized_processor = StabilizedAudioProcessor(yin_processor)
    
    results = {}
    
    for signal_name, signal_data in signals.items():
        print(f"\n🎯 测试信号: {signal_name}")
        print("-" * 40)
        
        # 分块处理
        chunk_size = 1024
        detections = []
        confidences = []
        
        for i in range(0, len(signal_data) - chunk_size, chunk_size // 4):
            chunk = signal_data[i:i + chunk_size]
            
            # 使用稳定化处理器
            freq, conf = stabilized_processor.process_with_stability(chunk)
            
            if freq > 0 and conf > 0.1:
                detections.append(freq)
                confidences.append(conf)
        
        # 分析结果
        if detections:
            mean_freq = np.mean(detections)
            std_freq = np.std(detections)
            mean_conf = np.mean(confidences)
            detection_rate = len(detections) / (len(signal_data) // (chunk_size // 4)) * 100
            
            print(f"  ✅ 检测结果:")
            print(f"    - 平均频率: {mean_freq:.1f} Hz")
            print(f"    - 频率稳定性: ±{std_freq:.1f} Hz")
            print(f"    - 平均置信度: {mean_conf:.2f}")
            print(f"    - 检测率: {detection_rate:.1f}%")
            print(f"    - 总检测次数: {len(detections)}")
            
            # 判断检测质量
            if '真实音高' in signal_name or '女高音' in signal_name or '音阶' in signal_name:
                if detection_rate > 70:
                    print(f"    ✅ 真实音高检测: 优秀")
                elif detection_rate > 40:
                    print(f"    ⚠️  真实音高检测: 良好，可能需要调优")
                else:
                    print(f"    ❌ 真实音高检测: 需要改进")
            else:  # 噪音信号
                if detection_rate < 20:
                    print(f"    ✅ 噪音过滤: 优秀")
                elif detection_rate < 50:
                    print(f"    ⚠️  噪音过滤: 良好")
                else:
                    print(f"    ❌ 噪音过滤: 需要改进，误检测过多")
        else:
            print(f"  ❌ 未检测到任何音高")
            if '噪音' in signal_name:
                print(f"    ✅ 这对噪音信号是好结果")
            else:
                print(f"    ⚠️  这可能表明真实音高被过度过滤")
        
        results[signal_name] = {
            'detections': detections,
            'mean_freq': np.mean(detections) if detections else 0,
            'detection_rate': detection_rate if detections else 0
        }
    
    # 总结报告
    print("\n" + "="*60)
    print("📊 测试总结报告")
    print("="*60)
    
    # 真实音高检测性能
    real_signals = [k for k in results.keys() if ('真实音高' in k or '女高音' in k or '音阶' in k)]
    noise_signals = [k for k in results.keys() if '噪音' in k]
    
    print("\n🎵 真实音高检测性能:")
    for signal in real_signals:
        rate = results[signal]['detection_rate']
        freq = results[signal]['mean_freq']
        status = "✅" if rate > 70 else "⚠️" if rate > 40 else "❌"
        print(f"  {status} {signal}: {rate:.1f}% (平均频率: {freq:.1f}Hz)")
    
    print("\n🔇 噪音过滤性能:")
    for signal in noise_signals:
        rate = results[signal]['detection_rate']
        freq = results[signal]['mean_freq']
        status = "✅" if rate < 20 else "⚠️" if rate < 50 else "❌"
        print(f"  {status} {signal}: {rate:.1f}% 误检测率 (平均频率: {freq:.1f}Hz)")
    
    print("\n💡 建议:")
    real_avg = np.mean([results[s]['detection_rate'] for s in real_signals])
    noise_avg = np.mean([results[s]['detection_rate'] for s in noise_signals])
    
    if real_avg > 60 and noise_avg < 30:
        print("  ✅ 系统表现良好，能有效区分真实音高和环境噪音")
        print(f"     真实音高平均检测率: {real_avg:.1f}%")
        print(f"     噪音平均误检测率: {noise_avg:.1f}%")
    elif real_avg > 60:
        print("  ⚠️  真实音高检测良好，但噪音过滤需要加强")
        print("     建议提高置信度阈值或加强谐波验证")
    elif noise_avg < 30:
        print("  ⚠️  噪音过滤良好，但真实音高检测偏保守")
        print("     建议降低稳定性要求或放宽频率范围")
    else:
        print("  ❌ 系统需要进一步调优")
        print("     建议重新平衡检测敏感度和噪音过滤强度")

if __name__ == "__main__":
    test_enhanced_yin()
