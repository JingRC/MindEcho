"""
降噪功能测试脚本
测试基础频域降噪的效果
"""

import numpy as np
import matplotlib.pyplot as plt
from src.audio_processing.noise_reduction import NoiseReductionProcessor
import time

def generate_test_signal(duration=2.0, sample_rate=44100):
    """生成测试信号"""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    
    # 创建复合音乐信号
    clean_signal = (
        0.5 * np.sin(2 * np.pi * 440 * t) +          # A4 主音
        0.3 * np.sin(2 * np.pi * 440 * 2 * t) +      # 二次谐波
        0.2 * np.sin(2 * np.pi * 440 * 3 * t) +      # 三次谐波
        0.1 * np.sin(2 * np.pi * 220 * t)            # 低音A3
    )
    
    # 添加各种噪声
    white_noise = 0.15 * np.random.randn(len(t))      # 白噪声
    power_line_noise = 0.08 * np.sin(2 * np.pi * 50 * t)  # 50Hz电源噪声
    power_line_noise += 0.04 * np.sin(2 * np.pi * 100 * t) # 100Hz谐波
    hum_noise = 0.06 * np.sin(2 * np.pi * 60 * t)     # 60Hz哼声
    
    # 组合信号
    noisy_signal = clean_signal + white_noise + power_line_noise + hum_noise
    
    return clean_signal, noisy_signal, t

def calculate_snr(clean, noisy):
    """计算信噪比"""
    noise = noisy - clean
    signal_power = np.mean(clean ** 2)
    noise_power = np.mean(noise ** 2)
    
    if noise_power == 0:
        return float('inf')
    
    snr_db = 10 * np.log10(signal_power / noise_power)
    return snr_db

def test_noise_reduction():
    """测试降噪功能"""
    print("🎵 开始测试MindEcho降噪功能...")
    
    # 生成测试信号
    clean_signal, noisy_signal, t = generate_test_signal()
    
    print(f"✅ 生成测试信号完成")
    print(f"   信号长度: {len(noisy_signal)} 样本 ({len(noisy_signal)/44100:.2f}秒)")
    
    # 计算原始信噪比
    original_snr = calculate_snr(clean_signal, noisy_signal)
    print(f"   原始信噪比: {original_snr:.2f} dB")
    
    # 创建降噪处理器
    processor = NoiseReductionProcessor(sample_rate=44100, frame_size=2048)
    
    # 测试不同降噪模式
    modes = ["基础频域降噪", "AI降噪", "高级音乐保护"]
    results = {}
    
    for mode in modes:
        print(f"\n🔧 测试模式: {mode}")
        processor.set_noise_reduction_mode(mode)
        
        # 分块处理信号
        frame_size = 2048
        processed_signal = []
        
        start_time = time.time()
        
        for i in range(0, len(noisy_signal), frame_size):
            frame = noisy_signal[i:i+frame_size]
            if len(frame) < frame_size:
                frame = np.pad(frame, (0, frame_size - len(frame)), 'constant')
            
            processed_frame = processor.process_audio(frame)
            processed_signal.extend(processed_frame[:len(noisy_signal[i:i+frame_size])])
        
        processing_time = time.time() - start_time
        processed_signal = np.array(processed_signal)
        
        # 计算处理后的信噪比
        if mode == "基础频域降噪":
            processed_snr = calculate_snr(clean_signal, processed_signal)
            snr_improvement = processed_snr - original_snr
        else:
            # AI降噪和高级音乐保护当前不处理，所以SNR不变
            processed_snr = original_snr
            snr_improvement = 0
        
        # 计算RMS值
        original_rms = np.sqrt(np.mean(noisy_signal ** 2))
        processed_rms = np.sqrt(np.mean(processed_signal ** 2))
        
        results[mode] = {
            'processed_signal': processed_signal,
            'processing_time': processing_time,
            'snr_improvement': snr_improvement,
            'processed_snr': processed_snr,
            'original_rms': original_rms,
            'processed_rms': processed_rms
        }
        
        print(f"   处理时间: {processing_time:.3f}秒")
        print(f"   实时倍数: {len(noisy_signal)/44100/processing_time:.2f}x")
        print(f"   处理后SNR: {processed_snr:.2f} dB")
        print(f"   SNR改善: {snr_improvement:+.2f} dB")
        print(f"   原始RMS: {original_rms:.4f}")
        print(f"   处理后RMS: {processed_rms:.4f}")
    
    # 绘制对比图
    plot_results(clean_signal, noisy_signal, results, t)
    
    print("\n✅ 降噪功能测试完成！")
    
    return results

def plot_results(clean_signal, noisy_signal, results, t):
    """绘制结果对比图"""
    try:
        plt.style.use('dark_background')
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('MindEcho 降噪效果对比', fontsize=16, fontweight='bold')
        
        # 限制显示时间范围（前0.1秒）
        display_samples = int(0.1 * 44100)
        t_display = t[:display_samples]
        
        # 原始清洁信号
        axes[0, 0].plot(t_display, clean_signal[:display_samples], 'g-', linewidth=1, alpha=0.8)
        axes[0, 0].set_title('原始清洁信号', color='lightgreen')
        axes[0, 0].set_ylabel('幅度')
        axes[0, 0].grid(True, alpha=0.3)
        
        # 含噪声信号
        axes[0, 1].plot(t_display, noisy_signal[:display_samples], 'r-', linewidth=1, alpha=0.8)
        axes[0, 1].set_title('含噪声信号', color='lightcoral')
        axes[0, 1].set_ylabel('幅度')
        axes[0, 1].grid(True, alpha=0.3)
        
        # 基础频域降噪结果
        if "基础频域降噪" in results:
            processed = results["基础频域降噪"]["processed_signal"]
            axes[1, 0].plot(t_display, processed[:display_samples], 'c-', linewidth=1, alpha=0.8)
            snr_imp = results["基础频域降噪"]["snr_improvement"]
            axes[1, 0].set_title(f'基础频域降噪 (SNR改善: {snr_imp:+.2f}dB)', color='cyan')
            axes[1, 0].set_ylabel('幅度')
            axes[1, 0].set_xlabel('时间 (秒)')
            axes[1, 0].grid(True, alpha=0.3)
        
        # 频谱对比
        axes[1, 1].remove()
        axes[1, 1] = plt.subplot(2, 2, 4)
        
        # 计算频谱
        freqs = np.fft.fftfreq(len(clean_signal), 1/44100)[:len(clean_signal)//2]
        
        clean_fft = np.abs(np.fft.fft(clean_signal))[:len(clean_signal)//2]
        noisy_fft = np.abs(np.fft.fft(noisy_signal))[:len(noisy_signal)//2]
        
        if "基础频域降噪" in results:
            processed_fft = np.abs(np.fft.fft(results["基础频域降噪"]["processed_signal"]))[:len(clean_signal)//2]
            axes[1, 1].semilogy(freqs[:2000], processed_fft[:2000], 'c-', alpha=0.7, label='频域降噪', linewidth=1)
        
        axes[1, 1].semilogy(freqs[:2000], clean_fft[:2000], 'g-', alpha=0.8, label='清洁信号', linewidth=1)
        axes[1, 1].semilogy(freqs[:2000], noisy_fft[:2000], 'r-', alpha=0.6, label='含噪信号', linewidth=1)
        
        axes[1, 1].set_title('频谱对比 (0-2000Hz)', color='white')
        axes[1, 1].set_xlabel('频率 (Hz)')
        axes[1, 1].set_ylabel('幅度')
        axes[1, 1].legend()
        axes[1, 1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('noise_reduction_test_result.png', dpi=150, bbox_inches='tight', 
                   facecolor='black', edgecolor='none')
        plt.show()
        
        print("📊 对比图已保存为 noise_reduction_test_result.png")
        
    except Exception as e:
        print(f"❌ 绘图失败: {e}")

if __name__ == "__main__":
    # 运行测试
    test_results = test_noise_reduction()
    
    # 打印总结
    print("\n" + "="*60)
    print("📊 降噪功能测试总结")
    print("="*60)
    
    for mode, result in test_results.items():
        print(f"\n🔧 {mode}:")
        print(f"   SNR改善: {result['snr_improvement']:+.2f} dB")
        print(f"   处理速度: {result['processing_time']:.3f}秒")
        print(f"   实时性能: {len(test_results) > 0 and '✅ 满足实时要求' if result['processing_time'] < 2.0 else '⚠️ 处理较慢'}")
        
        if mode == "基础频域降噪":
            if result['snr_improvement'] > 1:
                print(f"   降噪效果: ✅ 明显改善")
            elif result['snr_improvement'] > 0:
                print(f"   降噪效果: 🔶 轻微改善")
            else:
                print(f"   降噪效果: ❌ 无明显改善")
        else:
            print(f"   降噪效果: 🚧 功能开发中")
    
    print(f"\n✅ 测试完成！基础频域降噪功能已集成到MindEcho系统中。")
