#!/usr/bin/env python3
"""
音频输入检查工具
检查麦克风是否正常工作，并提供实时音量监控
"""

import sounddevice as sd
import numpy as np
import time
import threading
import queue
from collections import deque

def list_audio_devices():
    """列出所有音频设备"""
    print("🎤 可用音频设备:")
    devices = sd.query_devices()
    
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:  # 只显示输入设备
            status = "✅" if i == sd.default.device[0] else "  "
            print(f"{status} [{i:2d}] {device['name']}")
            print(f"      最大输入通道: {device['max_input_channels']}")
            print(f"      默认采样率: {device['default_samplerate']:.0f} Hz")
            print()

def monitor_audio_input(device=None, duration=10):
    """监控音频输入"""
    print(f"🔊 开始监控音频输入 ({duration}秒)...")
    if device is not None:
        print(f"使用设备: {device}")
    else:
        print("使用默认输入设备")
    
    # 音频参数
    sample_rate = 44100
    channels = 1
    blocksize = 1024
    
    # 数据存储
    audio_queue = queue.Queue()
    rms_history = deque(maxlen=100)  # 保存最近100个RMS值
    peak_history = deque(maxlen=100)
    
    def audio_callback(indata, frames, time, status):
        """音频回调函数"""
        if status:
            print(f"⚠️ 音频状态: {status}")
        
        # 转换为float32
        audio_data = indata[:, 0].astype(np.float32)
        
        try:
            audio_queue.put_nowait(audio_data)
        except queue.Full:
            # 队列满了，丢弃旧数据
            try:
                audio_queue.get_nowait()
                audio_queue.put_nowait(audio_data)
            except queue.Empty:
                pass
    
    print("按 Ctrl+C 停止监控")
    print("RMS = 均方根值 (音量大小), Peak = 峰值 (最大振幅)")
    print("正常说话时 RMS 应该在 0.01-0.1 范围内")
    print("-" * 70)
    
    try:
        # 启动音频流
        with sd.InputStream(
            callback=audio_callback,
            device=device,
            samplerate=sample_rate,
            channels=channels,
            blocksize=blocksize,
            dtype=np.float32
        ):
            
            start_time = time.time()
            last_print_time = 0
            max_rms = 0
            max_peak = 0
            
            while time.time() - start_time < duration:
                try:
                    # 获取音频数据
                    audio_data = audio_queue.get(timeout=0.1)
                    
                    # 计算RMS和峰值
                    rms = np.sqrt(np.mean(audio_data ** 2))
                    peak = np.max(np.abs(audio_data))
                    
                    rms_history.append(rms)
                    peak_history.append(peak)
                    
                    # 更新最大值
                    max_rms = max(max_rms, rms)
                    max_peak = max(max_peak, peak)
                    
                    # 每0.5秒输出一次
                    current_time = time.time()
                    if current_time - last_print_time >= 0.5:
                        avg_rms = np.mean(list(rms_history)[-10:]) if rms_history else 0
                        avg_peak = np.mean(list(peak_history)[-10:]) if peak_history else 0
                        
                        # 音量条显示
                        volume_bars = int(avg_rms * 200)  # 缩放到合适范围
                        volume_display = "█" * min(volume_bars, 50)
                        
                        # 状态判断
                        if avg_rms > 0.01:
                            status = "🔊 正常"
                        elif avg_rms > 0.005:
                            status = "🔉 较低"
                        elif avg_rms > 0.001:
                            status = "🔈 很低"
                        else:
                            status = "🔇 静音"
                        
                        elapsed = current_time - start_time
                        print(f"[{elapsed:4.1f}s] RMS: {avg_rms:.4f} Peak: {avg_peak:.4f} {status} |{volume_display:<50}|")
                        last_print_time = current_time
                
                except queue.Empty:
                    continue
                except KeyboardInterrupt:
                    break
            
            print("\n" + "="*70)
            print("📊 监控结果统计:")
            print(f"  最大 RMS: {max_rms:.4f}")
            print(f"  最大 Peak: {max_peak:.4f}")
            print(f"  平均 RMS: {np.mean(list(rms_history)):.4f}")
            print(f"  平均 Peak: {np.mean(list(peak_history)):.4f}")
            
            # 诊断建议
            print("\n🔧 诊断建议:")
            if max_rms < 0.001:
                print("  ❌ 音频输入极低，可能问题:")
                print("     • 麦克风未连接或损坏")
                print("     • 麦克风被静音")
                print("     • 选择了错误的输入设备")
                print("     • 系统音频驱动问题")
            elif max_rms < 0.01:
                print("  ⚠️ 音频输入较低，建议:")
                print("     • 检查麦克风音量设置")
                print("     • 靠近麦克风说话")
                print("     • 检查麦克风增益设置")
            else:
                print("  ✅ 音频输入正常！")
    
    except Exception as e:
        print(f"❌ 音频监控错误: {e}")

def test_simple_pitch_detection():
    """简单音高检测测试"""
    print("\n🎵 简单音高检测测试...")
    
    sample_rate = 44100
    duration = 5
    
    print(f"请在 {duration} 秒内发出稳定的音调...")
    
    # 录制音频
    try:
        print("🔴 开始录制...")
        audio_data = sd.rec(int(duration * sample_rate), 
                           samplerate=sample_rate, 
                           channels=1, 
                           dtype=np.float32)
        sd.wait()  # 等待录制完成
        
        audio_data = audio_data.flatten()
        rms = np.sqrt(np.mean(audio_data ** 2))
        peak = np.max(np.abs(audio_data))
        
        print(f"✅ 录制完成!")
        print(f"   音频长度: {len(audio_data)} 样本 ({len(audio_data)/sample_rate:.1f}秒)")
        print(f"   RMS: {rms:.4f}")
        print(f"   Peak: {peak:.4f}")
        
        if rms < 0.001:
            print("❌ 音频信号太弱，无法进行音高检测")
            return
        
        # 简单音高检测
        def detect_pitch_simple(audio, sr):
            # 加窗
            windowed = audio * np.hanning(len(audio))
            
            # 自相关
            correlation = np.correlate(windowed, windowed, mode='full')
            correlation = correlation[len(correlation)//2:]
            
            # 搜索范围
            min_period = int(sr / 1000)  # 最高1000Hz
            max_period = int(sr / 50)    # 最低50Hz
            
            if max_period < len(correlation):
                search_range = correlation[min_period:max_period]
                if len(search_range) > 0:
                    peak_index = np.argmax(search_range) + min_period
                    frequency = sr / peak_index
                    confidence = correlation[peak_index] / correlation[0] if correlation[0] > 0 else 0
                    return frequency, confidence
            
            return None, 0
        
        frequency, confidence = detect_pitch_simple(audio_data, sample_rate)
        
        if frequency and confidence > 0.1:
            print(f"🎼 检测到音高: {frequency:.1f} Hz (置信度: {confidence:.3f})")
            
            # 转换为音名
            def frequency_to_note(freq):
                A4 = 440.0
                note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
                
                if freq <= 0:
                    return "未知"
                
                # 计算相对于A4的半音数
                semitones = 12 * np.log2(freq / A4)
                octave = 4 + int((semitones + 9) // 12)
                note_index = int((semitones + 9) % 12)
                
                return f"{note_names[note_index]}{octave}"
            
            note = frequency_to_note(frequency)
            print(f"🎵 对应音名: {note}")
        else:
            print("❌ 未检测到明显音高")
            print(f"   尝试检测结果: {frequency:.1f if frequency else 0} Hz (置信度: {confidence:.3f})")
    
    except Exception as e:
        print(f"❌ 音高检测测试失败: {e}")

def main():
    """主函数"""
    print("🎤 MindEcho 音频输入检查工具")
    print("="*50)
    
    # 列出音频设备
    list_audio_devices()
    
    print("选择操作:")
    print("1. 监控默认麦克风 (10秒)")
    print("2. 选择特定设备监控")
    print("3. 简单音高检测测试")
    print("4. 全面测试")
    print("0. 退出")
    
    try:
        choice = input("\n请选择 (0-4): ").strip()
        
        if choice == '1':
            monitor_audio_input(duration=10)
        
        elif choice == '2':
            device_id = input("请输入设备ID: ").strip()
            try:
                device_id = int(device_id)
                monitor_audio_input(device=device_id, duration=10)
            except ValueError:
                print("❌ 无效的设备ID")
        
        elif choice == '3':
            test_simple_pitch_detection()
        
        elif choice == '4':
            print("🔄 执行全面测试...")
            monitor_audio_input(duration=5)
            test_simple_pitch_detection()
        
        elif choice == '0':
            print("👋 退出")
        
        else:
            print("❌ 无效选择")
    
    except KeyboardInterrupt:
        print("\n🛑 用户中断")
    except Exception as e:
        print(f"❌ 程序错误: {e}")

if __name__ == "__main__":
    main()
