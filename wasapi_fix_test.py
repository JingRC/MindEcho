#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WASAPI错误修复测试脚本
针对HECATE G4 Pro的WASAPI错误进行系统性测试和验证
"""

import sys
import os
import sounddevice as sd
import numpy as np
import time

def test_wasapi_fixes():
    """测试WASAPI修复效果"""
    print("🔧 WASAPI错误修复测试 - HECATE G4 Pro专版")
    print("="*60)
    
    # 1. 基础环境检查
    print("\n📊 1. 基础环境检查")
    try:
        print(f"   sounddevice版本: {sd.__version__}")
        print(f"   numpy版本: {np.__version__}")
        print(f"   Python版本: {sys.version}")
        
        # 检查WASAPI支持
        hostapis = sd.query_hostapis()
        wasapi_found = False
        for api in hostapis:
            if 'WASAPI' in api['name']:
                print(f"   ✅ WASAPI支持: {api['name']} (设备数: {api['device_count']})")
                wasapi_found = True
        
        if not wasapi_found:
            print("   ❌ 未找到WASAPI支持")
    except Exception as e:
        print(f"   ❌ 环境检查失败: {e}")
    
    # 2. 设备发现和分析
    print("\n🎯 2. HECATE设备发现")
    hecate_devices = []
    try:
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            device_name = device.get('name', '')
            if 'HECATE' in device_name or 'G4 Pro' in device_name:
                hecate_devices.append((i, device))
                print(f"   设备{i}: {device_name}")
                print(f"      输入通道: {device.get('max_input_channels', 0)}")
                print(f"      输出通道: {device.get('max_output_channels', 0)}")
                print(f"      默认采样率: {device.get('default_samplerate', 0)}Hz")
                print(f"      主机API: {device.get('hostapi', -1)}")
                
    except Exception as e:
        print(f"   ❌ 设备发现失败: {e}")
    
    if not hecate_devices:
        print("   ⚠️ 未发现HECATE设备，使用默认设备进行测试")
        hecate_devices = [(None, {'name': '默认设备', 'max_input_channels': 2, 'default_samplerate': 44100})]
    
    # 3. 错误修复测试
    print("\n🔧 3. 错误修复测试")
    
    for device_id, device_info in hecate_devices:
        device_name = device_info.get('name', 'Unknown')
        print(f"\n   测试设备: {device_name} (设备{device_id})")
        
        # 测试配置集合
        test_configs = [
            {
                'name': 'WASAPI独占模式',
                'params': {
                    'device': device_id,
                    'channels': 1,
                    'samplerate': 48000,
                    'blocksize': 256,
                    'dtype': 'float32',
                    'extra_settings': sd.WasapiSettings(exclusive=True) if device_id is not None else None
                }
            },
            {
                'name': 'WASAPI共享模式', 
                'params': {
                    'device': device_id,
                    'channels': 1,
                    'samplerate': 48000,
                    'blocksize': 256,
                    'dtype': 'float32',
                    'extra_settings': sd.WasapiSettings(exclusive=False) if device_id is not None else None
                }
            },
            {
                'name': '通道修复模式',
                'params': {
                    'device': device_id,
                    'channels': min(device_info.get('max_input_channels', 2), 1),
                    'samplerate': 44100,
                    'blocksize': 512,
                    'dtype': 'float32'
                }
            },
            {
                'name': '兼容性模式',
                'params': {
                    'device': device_id,
                    'channels': 1,
                    'samplerate': 44100,
                    'blocksize': 1024,
                    'dtype': 'float32'
                }
            }
        ]
        
        # 测试每个配置
        successful_configs = []
        for config in test_configs:
            try:
                # 移除None参数
                params = {k: v for k, v in config['params'].items() if v is not None}
                
                # 创建测试流
                stream = sd.InputStream(**params)
                
                # 计算延迟
                latency = params['blocksize'] / params['samplerate'] * 1000
                
                print(f"      ✅ {config['name']}: {params['samplerate']}Hz/{params['blocksize']}样本 ({latency:.2f}ms)")
                successful_configs.append(config['name'])
                
                # 关闭测试流
                stream.close()
                
            except Exception as e:
                error_str = str(e)
                print(f"      ❌ {config['name']}: {error_str}")
                
                # 分析错误类型
                if 'PaErrorCode -9999' in error_str or 'WRONG_ENDPOINT_TYPE' in error_str:
                    print(f"         🔍 端点类型错误 - WASAPI设备权限问题")
                elif 'PaErrorCode -9996' in error_str or 'DEVICE_INVALIDATED' in error_str:
                    print(f"         🔍 设备失效 - 设备被占用或驱动问题")
                elif 'PaErrorCode -9997' in error_str or 'Invalid sample rate' in error_str:
                    print(f"         🔍 采样率不支持 - 硬件限制")
                elif 'PaErrorCode -9998' in error_str or 'Invalid number of channels' in error_str:
                    print(f"         🔍 通道数错误 - 单/立体声配置问题")
        
        # 总结设备测试结果
        if successful_configs:
            print(f"      📊 成功配置: {len(successful_configs)}/{len(test_configs)}")
            print(f"      🎯 推荐配置: {successful_configs[0]}")
        else:
            print(f"      ❌ 所有配置失败，设备可能存在问题")
    
    # 4. 实际监听测试
    print("\n🎧 4. 实际监听测试")
    if hecate_devices and hecate_devices[0][0] is not None:
        device_id, device_info = hecate_devices[0]
        try:
            # 使用最保守的配置
            stream = sd.InputStream(
                device=device_id,
                channels=1,
                samplerate=44100,
                blocksize=1024,
                dtype='float32'
            )
            
            print("   🎧 启动3秒监听测试...")
            stream.start()
            time.sleep(3)
            stream.stop()
            stream.close()
            print("   ✅ 监听测试成功完成")
            
        except Exception as e:
            print(f"   ❌ 监听测试失败: {e}")
    else:
        print("   ⚠️ 跳过监听测试（无可用HECATE设备）")
    
    print("\n🎯 5. 修复建议总结")
    print("   1. 检查Windows设备管理器中的音频设备状态")
    print("   2. 确保HECATE驱动程序是最新版本")
    print("   3. 在Windows音频设置中禁用独占模式")
    print("   4. 尝试重启Windows音频服务 (Audiosrv)")
    print("   5. 检查其他程序是否占用音频设备")
    
    print("\n" + "="*60)
    print("🔧 WASAPI错误修复测试完成")

if __name__ == "__main__":
    test_wasapi_fixes()
