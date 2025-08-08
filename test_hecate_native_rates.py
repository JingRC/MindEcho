#!/usr/bin/env python3
"""
HECATE G4 Pro 原生采样率测试工具
专门测试设备支持的原生采样率和配置
"""

import sounddevice as sd
import numpy as np
import time

def detect_hecate_devices():
    """检测所有HECATE设备"""
    try:
        devices = sd.query_devices()
        hecate_devices = []
        
        print(f"🔍 扫描{len(devices)}个设备...")
        
        for i, device in enumerate(devices):
            name = device.get('name', '').lower()
            if 'hecate' in name and device.get('max_input_channels', 0) > 0:
                hecate_devices.append({
                    'id': i,
                    'name': device.get('name', 'Unknown'),
                    'max_inputs': device.get('max_input_channels', 0),
                    'default_samplerate': device.get('default_samplerate', 0),
                    'device_info': device
                })
                
                print(f"✅ 发现HECATE设备 {i}: {device.get('name')}")
                print(f"   输入通道: {device.get('max_input_channels', 0)}")
                print(f"   原生采样率: {device.get('default_samplerate', 0)}Hz")
        
        return hecate_devices
        
    except Exception as e:
        print(f"❌ 设备扫描失败: {e}")
        return []

def test_native_sample_rates(device_id, device_name):
    """测试设备支持的采样率"""
    print(f"\n🧪 测试设备{device_id}: {device_name}")
    print("-" * 50)
    
    # 常见采样率列表（包括高端设备支持的采样率）
    test_rates = [
        8000, 11025, 16000, 22050, 24000,
        32000, 44100, 48000, 88200, 96000,
        176400, 192000, 352800, 384000
    ]
    
    # 测试缓冲区大小
    test_blocks = [32, 64, 128, 256, 512, 1024]
    
    supported_configs = []
    
    for sample_rate in test_rates:
        print(f"\n📊 测试采样率: {sample_rate}Hz")
        
        rate_supported = False
        for block_size in test_blocks:
            try:
                # 测试WASAPI共享模式
                settings = sd.WasapiSettings(exclusive=False)
                stream = sd.InputStream(
                    device=device_id,
                    channels=1,
                    samplerate=sample_rate,
                    blocksize=block_size,
                    dtype='float32',
                    extra_settings=settings
                )
                
                # 快速测试
                stream.start()
                time.sleep(0.05)  # 50ms测试
                stream.stop()
                stream.close()
                
                latency_ms = block_size / sample_rate * 1000
                print(f"   ✅ {sample_rate}Hz/{block_size}样本 (延迟: {latency_ms:.2f}ms) - WASAPI共享")
                
                supported_configs.append({
                    'rate': sample_rate,
                    'block': block_size,
                    'latency': latency_ms,
                    'mode': 'wasapi_shared'
                })
                
                rate_supported = True
                
                # 测试独占模式
                try:
                    settings_exclusive = sd.WasapiSettings(exclusive=True)
                    stream_exc = sd.InputStream(
                        device=device_id,
                        channels=1,
                        samplerate=sample_rate,
                        blocksize=block_size,
                        dtype='float32',
                        extra_settings=settings_exclusive
                    )
                    
                    stream_exc.start()
                    time.sleep(0.05)
                    stream_exc.stop()
                    stream_exc.close()
                    
                    print(f"   🎯 {sample_rate}Hz/{block_size}样本 (延迟: {latency_ms:.2f}ms) - WASAPI独占")
                    
                    supported_configs.append({
                        'rate': sample_rate,
                        'block': block_size,
                        'latency': latency_ms,
                        'mode': 'wasapi_exclusive'
                    })
                    
                except Exception:
                    pass  # 独占模式失败是正常的
                
                break  # 找到一个可用配置就测试下一个采样率
                
            except Exception as e:
                error_str = str(e)
                if "Invalid sample rate" in error_str or "PaErrorCode -9997" in error_str:
                    continue  # 尝试下一个缓冲区大小
                elif "Invalid device" in error_str or "PaErrorCode -9996" in error_str:
                    print(f"   ❌ 设备不可用")
                    break
                else:
                    continue  # 尝试下一个配置
        
        if not rate_supported:
            print(f"   ❌ {sample_rate}Hz 不支持")
    
    return supported_configs

def generate_optimal_configs(supported_configs):
    """生成最优配置建议"""
    if not supported_configs:
        return []
    
    print(f"\n🎯 配置优化建议:")
    print("=" * 50)
    
    # 按延迟排序
    sorted_configs = sorted(supported_configs, key=lambda x: x['latency'])
    
    # 超低延迟配置（<2ms）
    ultra_low = [c for c in sorted_configs if c['latency'] < 2.0]
    if ultra_low:
        print(f"🚀 超低延迟配置 (<2ms):")
        for config in ultra_low[:3]:
            print(f"   🎯 {config['rate']}Hz/{config['block']}样本 "
                  f"({config['latency']:.2f}ms) - {config['mode']}")
    
    # 低延迟配置（<5ms）
    low_latency = [c for c in sorted_configs if 2.0 <= c['latency'] < 5.0]
    if low_latency:
        print(f"\n⚡ 低延迟配置 (2-5ms):")
        for config in low_latency[:3]:
            print(f"   ⚡ {config['rate']}Hz/{config['block']}样本 "
                  f"({config['latency']:.2f}ms) - {config['mode']}")
    
    # 稳定配置（<10ms）
    stable = [c for c in sorted_configs if 5.0 <= c['latency'] < 10.0]
    if stable:
        print(f"\n🔒 稳定配置 (5-10ms):")
        for config in stable[:3]:
            print(f"   🔒 {config['rate']}Hz/{config['block']}样本 "
                  f"({config['latency']:.2f}ms) - {config['mode']}")
    
    # 高采样率配置
    high_rate = [c for c in sorted_configs if c['rate'] >= 96000]
    if high_rate:
        print(f"\n🎵 高保真配置 (≥96kHz):")
        for config in sorted(high_rate, key=lambda x: -x['rate'])[:3]:
            print(f"   🎵 {config['rate']}Hz/{config['block']}样本 "
                  f"({config['latency']:.2f}ms) - {config['mode']}")
    
    return sorted_configs

def main():
    """主测试函数"""
    print("🎧 HECATE G4 Pro 原生采样率测试工具")
    print("=" * 60)
    
    # 检测HECATE设备
    hecate_devices = detect_hecate_devices()
    
    if not hecate_devices:
        print("❌ 未发现HECATE设备")
        return
    
    print(f"\n🎯 发现{len(hecate_devices)}个HECATE设备")
    
    all_configs = {}
    
    # 对每个设备进行测试
    for device in hecate_devices:
        device_id = device['id']
        device_name = device['name']
        
        print(f"\n{'='*60}")
        print(f"测试设备: {device_name} (ID: {device_id})")
        print(f"原生采样率: {device['default_samplerate']}Hz")
        print(f"输入通道: {device['max_inputs']}")
        print('='*60)
        
        try:
            supported = test_native_sample_rates(device_id, device_name)
            all_configs[device_name] = supported
            
            if supported:
                print(f"\n✅ 设备{device_id}支持{len(supported)}种配置")
                generate_optimal_configs(supported)
            else:
                print(f"\n❌ 设备{device_id}没有找到可用配置")
                
        except Exception as e:
            print(f"❌ 测试设备{device_id}时发生错误: {e}")
    
    # 生成总结报告
    print(f"\n{'='*60}")
    print("📊 测试总结")
    print('='*60)
    
    for device_name, configs in all_configs.items():
        if configs:
            best_config = min(configs, key=lambda x: x['latency'])
            highest_rate = max(configs, key=lambda x: x['rate'])
            
            print(f"\n🎧 {device_name}:")
            print(f"   🚀 最低延迟: {best_config['rate']}Hz/{best_config['block']}样本 "
                  f"({best_config['latency']:.2f}ms)")
            print(f"   🎵 最高采样率: {highest_rate['rate']}Hz/{highest_rate['block']}样本 "
                  f"({highest_rate['latency']:.2f}ms)")
            print(f"   📊 总配置数: {len(configs)}种")
        else:
            print(f"\n❌ {device_name}: 无可用配置")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 用户中断测试")
    except Exception as e:
        print(f"\n❌ 测试过程发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🔚 测试完成")
        input("按回车键退出...")
