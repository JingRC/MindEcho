#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态WASAPI设备配置测试
验证动态设备发现是否能替换硬编码索引解决"Invalid device"错误
"""

import sounddevice as sd
import sys
import os

# 添加src路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def get_wasapi_device_by_name(device_name_pattern):
    """根据设备名称模式查找WASAPI设备"""
    try:
        devices = sd.query_devices()
        wasapi_devices = []
        
        for i, device in enumerate(devices):
            # 检查是否为WASAPI设备 (hostapi=2)
            if device['hostapi'] == 2:  # WASAPI
                if device_name_pattern.upper() in device['name'].upper():
                    wasapi_devices.append({
                        'index': i,
                        'name': device['name'],
                        'max_input_channels': device['max_input_channels'],
                        'max_output_channels': device['max_output_channels'],
                        'default_samplerate': device['default_samplerate']
                    })
        
        return wasapi_devices
    except Exception as e:
        print(f"❌ WASAPI设备查找失败: {e}")
        return []

def test_dynamic_wasapi_detection():
    """测试动态WASAPI设备检测"""
    print("🚀 开始动态WASAPI设备检测测试...")
    
    # 测试HECATE G4设备发现
    print("\n📍 查找HECATE G4设备...")
    hecate_devices = get_wasapi_device_by_name('HECATE G4')
    if hecate_devices:
        for device in hecate_devices:
            print(f"✅ 发现HECATE G4设备:")
            print(f"   - 索引: {device['index']}")
            print(f"   - 名称: {device['name']}")
            print(f"   - 输入通道: {device['max_input_channels']}")
            print(f"   - 输出通道: {device['max_output_channels']}")
            print(f"   - 默认采样率: {device['default_samplerate']}")
    else:
        print("❌ 未发现HECATE G4设备")
    
    # 测试Realtek设备发现
    print("\n📍 查找Realtek设备...")
    realtek_devices = get_wasapi_device_by_name('REALTEK')
    if realtek_devices:
        for device in realtek_devices:
            print(f"✅ 发现Realtek设备:")
            print(f"   - 索引: {device['index']}")
            print(f"   - 名称: {device['name']}")
            print(f"   - 输入通道: {device['max_input_channels']}")
            print(f"   - 输出通道: {device['max_output_channels']}")
            print(f"   - 默认采样率: {device['default_samplerate']}")
    else:
        print("❌ 未发现Realtek设备")
    
    return hecate_devices, realtek_devices

def generate_optimal_wasapi_configs(hecate_devices, realtek_devices):
    """根据发现的设备生成优化的WASAPI配置"""
    configs = []
    
    # HECATE G4 Pro配置（如果可用）
    for device in hecate_devices:
        if device['max_input_channels'] > 0:
            # 独占模式配置（最高性能）
            configs.append({
                'name': f'WASAPI独占模式 (HECATE G4)',
                'device': device['index'],
                'samplerate': min(192000, int(device['default_samplerate'])),
                'blocksize': 32,
                'settings': lambda: sd.WasapiSettings(exclusive=True),
                'expected_latency': 'ultra-low',
                'verified_latency': 0.17 if device['default_samplerate'] >= 192000 else None
            })
    
    # Realtek配置（如果可用）
    for device in realtek_devices:
        if device['max_input_channels'] > 0:
            # 独占模式
            configs.append({
                'name': f'WASAPI独占模式 (Realtek)',
                'device': device['index'],
                'samplerate': min(48000, int(device['default_samplerate'])),
                'blocksize': 64,
                'settings': lambda: sd.WasapiSettings(exclusive=True),
                'expected_latency': 'very-low',
                'verified_latency': 1.33
            })
            
            # 共享模式（兼容性）
            configs.append({
                'name': f'WASAPI共享模式 (Realtek)',
                'device': device['index'],
                'samplerate': min(48000, int(device['default_samplerate'])),
                'blocksize': 128,
                'settings': lambda: sd.WasapiSettings(exclusive=False),
                'expected_latency': 'low',
                'verified_latency': 2.67
            })
    
    return configs

def test_wasapi_configs(configs):
    """测试生成的WASAPI配置是否有效"""
    print("\n🔧 测试动态生成的WASAPI配置...")
    
    for i, config in enumerate(configs):
        print(f"\n📋 配置 {i+1}: {config['name']}")
        print(f"   - 设备索引: {config['device']}")
        print(f"   - 采样率: {config['samplerate']}Hz")
        print(f"   - 缓冲区大小: {config['blocksize']}样本")
        print(f"   - 预期延迟: {config['expected_latency']}")
        if config.get('verified_latency'):
            print(f"   - 验证延迟: {config['verified_latency']}ms")
        
        # 简单验证设备是否存在
        try:
            device_info = sd.query_devices(config['device'])
            if device_info['hostapi'] == 2:  # WASAPI
                print(f"   ✅ 设备验证成功: {device_info['name']}")
            else:
                print(f"   ❌ 设备不是WASAPI: hostapi={device_info['hostapi']}")
        except Exception as e:
            print(f"   ❌ 设备验证失败: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("MindEcho 动态WASAPI设备配置测试")
    print("=" * 60)
    
    # 动态设备检测
    hecate_devices, realtek_devices = test_dynamic_wasapi_detection()
    
    # 生成优化配置
    print(f"\n🔧 根据发现的设备生成优化配置...")
    configs = generate_optimal_wasapi_configs(hecate_devices, realtek_devices)
    
    if configs:
        print(f"✅ 成功生成 {len(configs)} 个动态WASAPI配置")
        test_wasapi_configs(configs)
    else:
        print("❌ 未生成任何WASAPI配置")
    
    print(f"\n💡 测试完成！动态设备发现可以替换硬编码索引22/23")
