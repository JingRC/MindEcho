#!/usr/bin/env python3
"""
音频优化配置测试脚本
测试ASIO/WASAPI独占模式和低延迟设置
"""

import sounddevice as sd
import numpy as np
import time

def test_audio_optimization():
    """测试音频优化配置"""
    print("🎵 音频优化配置测试")
    print("=" * 50)
    
    # 测试全局设置
    print("1. 全局设置测试:")
    print(f"   ├─ 默认延迟模式: {sd.default.latency}")
    print(f"   ├─ 默认数据类型: {sd.default.dtype}")
    print(f"   └─ 默认采样率: {sd.default.samplerate}")
    
    # 列出所有音频设备
    print("\n2. 音频设备检测:")
    devices = sd.query_devices()
    
    asio_devices = []
    wasapi_devices = []
    directsound_devices = []
    
    for i, device in enumerate(devices):
        device_name = str(device.get('name', '')).upper()
        max_inputs = device.get('max_input_channels', 0)
        max_outputs = device.get('max_output_channels', 0)
        default_sr = device.get('default_samplerate', 44100)
        hostapi = device.get('hostapi', 0)
        low_latency = device.get('default_low_input_latency', 0.1)
        
        if max_inputs > 0:  # 只关注输入设备
            # 更准确的设备分类：基于hostapi而不是名称
            if hostapi == 2:  # WASAPI设备
                wasapi_devices.append((i, device))
                exclusive_support = "独占模式" if low_latency < 0.01 else "共享模式"
                print(f"   🔊 WASAPI设备: {device.get('name')} ({max_inputs}输入@{default_sr}Hz, {exclusive_support}, 延迟{low_latency*1000:.1f}ms)")
            elif 'ASIO' in device_name or max_inputs > 8:
                asio_devices.append((i, device))
                print(f"   🎧 ASIO设备: {device.get('name')} ({max_inputs}输入@{default_sr}Hz, 延迟{low_latency*1000:.1f}ms)")
            else:
                directsound_devices.append((i, device))
                host_name = ["DirectSound", "MME", "WASAPI", "WDM-KS"][min(hostapi, 3)]
                print(f"   📡 {host_name}设备: {device.get('name')} ({max_inputs}输入@{default_sr}Hz, 延迟{low_latency*1000:.1f}ms)")
    
    print(f"\n   总计: {len(asio_devices)}个ASIO, {len(wasapi_devices)}个WASAPI, {len(directsound_devices)}个DirectSound设备")
    
    # 测试不同的音频驱动配置
    print("\n3. 音频驱动配置测试:")
    
    test_configs = [
        {
            'name': 'ASIO专业模式',
            'settings': sd.AsioSettings(channel_selectors=[0]) if asio_devices else None,
            'enabled': len(asio_devices) > 0
        },
        {
            'name': 'WASAPI独占模式',
            'device': wasapi_devices[0][0] if wasapi_devices else None,
            'settings': sd.WasapiSettings(exclusive=True) if wasapi_devices else None,
            'enabled': len(wasapi_devices) > 0
        },
        {
            'name': 'WASAPI共享模式',
            'device': wasapi_devices[0][0] if wasapi_devices else None,
            'settings': sd.WasapiSettings(exclusive=False) if wasapi_devices else None,
            'enabled': len(wasapi_devices) > 0
        },
        {
            'name': 'DirectSound模式',
            'settings': None,
            'enabled': True
        }
    ]
    
    successful_configs = []
    
    for config in test_configs:
        if not config['enabled']:
            print(f"   ⏭️ {config['name']}: 跳过（无相应设备）")
            continue
            
        try:
            # 测试参数
            test_params = {
                'channels': 1,
                'samplerate': 48000,
                'blocksize': 128,  # 保守的缓冲区大小用于测试
                'dtype': np.float32,
                'latency': 'low'
            }
            
            # 为WASAPI设备指定设备索引
            if 'device' in config and config['device'] is not None:
                test_params['device'] = config['device']
            
            if config['settings']:
                test_params['extra_settings'] = config['settings']
            
            # 创建测试流（仅测试创建，不启动）
            test_stream = sd.InputStream(**test_params)
            test_latency = (128 / 48000) * 1000  # 理论延迟
            
            print(f"   ✅ {config['name']}: 成功 (理论延迟: {test_latency:.2f}ms)")
            successful_configs.append(config['name'])
            
            # 清理测试流
            test_stream.close()
            
        except Exception as e:
            print(f"   ❌ {config['name']}: 失败 - {str(e)[:80]}...")
    
    # 测试结果总结
    print(f"\n4. 测试结果总结:")
    print(f"   ├─ 可用配置: {len(successful_configs)}/{len(test_configs)}个")
    print(f"   ├─ 成功配置: {', '.join(successful_configs)}")
    
    if 'ASIO专业模式' in successful_configs:
        print(f"   ├─ 推荐使用: ASIO专业模式 (最低延迟)")
    elif 'WASAPI独占模式' in successful_configs:
        print(f"   ├─ 推荐使用: WASAPI独占模式 (专业级)")
    elif 'WASAPI共享模式' in successful_configs:
        print(f"   ├─ 推荐使用: WASAPI共享模式 (标准级)")
    else:
        print(f"   ├─ 推荐使用: DirectSound模式 (兼容性)")
    
    print(f"   └─ 优化状态: {'✅ 专业级配置可用' if successful_configs else '⚠️ 仅基础配置可用'}")
    
    # 延迟优化建议
    print(f"\n5. 延迟优化建议:")
    if 'ASIO专业模式' in successful_configs:
        print(f"   🚀 超低延迟设置:")
        print(f"      ├─ 缓冲区大小: 32-64样本 (0.67-1.33ms @48kHz)")
        print(f"      ├─ 采样率: 48000Hz (设备原生)")
        print(f"      └─ 预期延迟: <2ms (专业录音级别)")
    elif any('WASAPI' in config for config in successful_configs):
        print(f"   🎯 低延迟设置:")
        print(f"      ├─ 缓冲区大小: 64-128样本 (1.33-2.67ms @48kHz)")
        print(f"      ├─ 采样率: 48000Hz")
        print(f"      └─ 预期延迟: 2-5ms (实时监听级别)")
    else:
        print(f"   📡 标准设置:")
        print(f"      ├─ 缓冲区大小: 128-256样本 (2.67-5.33ms @48kHz)")
        print(f"      ├─ 采样率: 44100Hz")
        print(f"      └─ 预期延迟: 5-10ms (日常使用级别)")
    
    print("\n🎵 音频优化测试完成！")

if __name__ == "__main__":
    try:
        test_audio_optimization()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
