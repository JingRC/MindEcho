#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强版WASAPI错误修复测试 - HECATE G4 Pro专版
基于实际错误日志的智能修复策略
"""

import sounddevice as sd
import numpy as np
import time
import sys

def test_enhanced_wasapi_fixes():
    """测试增强版WASAPI修复方案"""
    print("🔧 增强版WASAPI错误修复测试 - HECATE G4 Pro专版")
    print("=" * 60)
    
    # 1. 环境检查
    print("\n📊 1. 增强环境检查")
    try:
        print(f"   sounddevice版本: {sd.__version__}")
        print(f"   numpy版本: {np.__version__}")
        print(f"   Python版本: {sys.version}")
        
        # 检查主机API
        host_apis = sd.query_hostapis()
        for i, api in enumerate(host_apis):
            api_name = api['name']
            # 统计该API下的设备数量
            devices = sd.query_devices()
            api_device_count = sum(1 for device in devices if device.get('hostapi', -1) == i)
            print(f"   主机API {i}: {api_name} ({api_device_count}设备)")
        
        print("   ✅ 增强环境检查完成")
    except Exception as e:
        print(f"   ❌ 环境检查失败: {e}")
        return False
    
    # 2. 智能HECATE设备发现和分析
    print("\n🎯 2. 智能HECATE设备发现")
    hecate_input_devices = []
    
    try:
        devices = sd.query_devices()
        
        for i, device in enumerate(devices):
            device_name = device.get('name', '')
            if 'HECATE' in device_name or 'G4 Pro' in device_name:
                max_input = device.get('max_input_channels', 0)
                max_output = device.get('max_output_channels', 0)
                sample_rate = device.get('default_samplerate', 44100)
                host_api = device.get('hostapi', -1)
                
                print(f"   设备{i}: {device_name}")
                print(f"      输入通道: {max_input}")
                print(f"      输出通道: {max_output}")
                print(f"      默认采样率: {sample_rate}Hz")
                print(f"      主机API: {host_api}")
                
                # 智能过滤：只收集有输入通道的设备
                if max_input > 0:
                    priority_score = calculate_device_priority(device)
                    hecate_input_devices.append({
                        'id': i,
                        'device': device,
                        'name': device_name,
                        'input_channels': max_input,
                        'samplerate': sample_rate,
                        'host_api': host_api,
                        'priority': priority_score
                    })
                    print(f"      ✅ 有效输入设备 (优先级: {priority_score})")
                else:
                    print(f"      ⚠️ 输出专用设备，跳过")
        
        # 按优先级排序
        hecate_input_devices.sort(key=lambda x: x['priority'], reverse=True)
        print(f"   📊 发现{len(hecate_input_devices)}个HECATE输入设备")
        
    except Exception as e:
        print(f"   ❌ 设备发现失败: {e}")
        return False
    
    # 3. 智能错误修复测试
    print("\n🔧 3. 智能错误修复测试")
    successful_configs = []
    
    for device_config in hecate_input_devices:
        device_id = device_config['id']
        device_name = device_config['name']
        max_channels = device_config['input_channels']
        device_samplerate = device_config['samplerate']
        host_api = device_config['host_api']
        
        print(f"\n   测试设备: {device_name} (设备{device_id})")
        
        # 生成智能配置序列
        test_configs = generate_smart_configs(device_id, max_channels, device_samplerate, host_api)
        
        device_success_count = 0
        device_best_config = None
        
        for config in test_configs:
            config_name = config.pop('name')  # 移除name用于测试
            
            try:
                # 测试配置
                test_stream = sd.InputStream(**config)
                test_stream.close()
                
                # 计算延迟
                latency_ms = config['blocksize'] / config['samplerate'] * 1000
                
                print(f"      ✅ {config_name}: {config['samplerate']}Hz/{config['blocksize']}样本 ({latency_ms:.2f}ms)")
                device_success_count += 1
                
                # 保存成功配置
                config['name'] = config_name
                config['latency_ms'] = latency_ms
                config['device_name'] = device_name
                
                if device_best_config is None:
                    device_best_config = config.copy()
                
            except Exception as e:
                error_msg = str(e)
                print(f"      ❌ {config_name}: {error_msg}")
                
                # 智能错误分析
                analyze_error(error_msg, config_name)
        
        print(f"      📊 成功配置: {device_success_count}/{len(test_configs)}")
        
        if device_best_config:
            successful_configs.append(device_best_config)
            print(f"      🎯 推荐配置: {device_best_config['name']}")
        else:
            print(f"      ❌ 所有配置失败，设备可能存在问题")
    
    # 4. 实际监听测试（使用最佳配置）
    print("\n🎧 4. 实际监听测试")
    if successful_configs:
        best_config = successful_configs[0]  # 使用优先级最高的成功配置
        
        try:
            print(f"   使用配置: {best_config['name']}")
            print(f"   设备: {best_config['device_name']}")
            print(f"   参数: {best_config['samplerate']}Hz/{best_config['blocksize']}样本/{best_config['channels']}声道")
            
            # 移除测试添加的键
            clean_config = {k: v for k, v in best_config.items() 
                          if k in ['device', 'channels', 'samplerate', 'blocksize', 'dtype']}
            
            def test_callback(indata, outdata, frames, time, status):
                if status:
                    print(f"      状态: {status}")
                # 简单的音频处理
                if outdata.shape[1] == 1:
                    outdata[:, 0] = indata[:, 0] * 0.1  # 降低音量的监听
                else:
                    outdata[:, 0] = indata[:, 0] * 0.1
                    outdata[:, 1] = indata[:, 0] * 0.1
            
            clean_config['callback'] = test_callback
            
            print("   🎧 启动3秒监听测试...")
            with sd.Stream(**clean_config):
                time.sleep(3)
            
            print("   ✅ 监听测试成功完成")
            
        except Exception as e:
            print(f"   ❌ 监听测试失败: {e}")
    else:
        print("   ⚠️ 没有可用的配置进行监听测试")
    
    # 5. 修复建议总结
    print("\n🎯 5. 智能修复建议总结")
    if successful_configs:
        print("   ✅ 找到可用配置，建议:")
        for i, config in enumerate(successful_configs[:3], 1):  # 显示前3个最佳配置
            print(f"   {i}. {config['device_name']}")
            print(f"      配置: {config['name']}")
            print(f"      延迟: {config['latency_ms']:.2f}ms")
    else:
        print("   ❌ 未找到可用配置，系统级建议:")
    
    print("   系统优化建议:")
    print("   1. 在Windows声音设置中将HECATE设备设为默认设备")
    print("   2. 右键HECATE设备 → 属性 → 高级 → 取消'独占模式'")
    print("   3. 设置默认格式为 '16位，44100Hz' 或 '16位，48000Hz'")
    print("   4. 禁用所有音频增强和特效")
    print("   5. 重启Windows音频服务: 'net stop Audiosrv && net start Audiosrv'")
    print("   6. 确保HECATE驱动是最新版本")
    print("   7. 关闭其他音频程序（如Discord、OBS等）")
    
    print("\n" + "=" * 60)
    print("🔧 增强版WASAPI错误修复测试完成")
    return len(successful_configs) > 0

def calculate_device_priority(device_info):
    """计算设备优先级"""
    score = 0
    device_name = device_info.get('name', '').lower()
    host_api = device_info.get('hostapi', -1)
    sample_rate = device_info.get('default_samplerate', 44100)
    input_channels = device_info.get('max_input_channels', 0)
    
    # 设备名称评分
    if '麦克风' in device_name or 'microphone' in device_name:
        score += 50
    elif 'hecate' in device_name and 'g4 pro' in device_name:
        score += 40
    elif 'hecate' in device_name:
        score += 30
    
    # 主机API评分
    if host_api == 1:  # DirectSound
        score += 25
    elif host_api == 2:  # WASAPI
        score += 20
    elif host_api == 0:  # MME
        score += 15
    
    # 采样率评分
    if 44100 <= sample_rate <= 48000:
        score += 20
    elif 48000 < sample_rate <= 96000:
        score += 15
    else:
        score += 5
    
    # 输入通道评分
    if input_channels == 2:
        score += 15
    elif input_channels == 1:
        score += 10
    
    return score

def generate_smart_configs(device_id, max_channels, device_samplerate, host_api):
    """生成智能配置序列"""
    configs = []
    safe_channels = min(max_channels, 2) if max_channels > 0 else 1
    
    # 配置1：最高兼容性
    configs.append({
        'device': device_id,
        'channels': 1,
        'samplerate': 44100,
        'blocksize': 1024,
        'dtype': 'float32',
        'name': '最高兼容性模式'
    })
    
    # 配置2：标准配置
    configs.append({
        'device': device_id,
        'channels': safe_channels,
        'samplerate': 44100,
        'blocksize': 512,
        'dtype': 'float32',
        'name': '标准配置'
    })
    
    # 配置3：48kHz配置
    configs.append({
        'device': device_id,
        'channels': safe_channels,
        'samplerate': 48000,
        'blocksize': 256,
        'dtype': 'float32',
        'name': '48kHz配置'
    })
    
    # 配置4：WASAPI配置（仅对WASAPI设备）
    if host_api == 2:
        configs.append({
            'device': device_id,
            'channels': safe_channels,
            'samplerate': 44100,
            'blocksize': 256,
            'dtype': 'float32',
            'extra_settings': sd.WasapiSettings(exclusive=False),
            'name': 'WASAPI共享模式'
        })
    
    # 配置5：高采样率（如果设备支持）
    if device_samplerate > 48000 and device_samplerate <= 96000:
        configs.append({
            'device': device_id,
            'channels': safe_channels,
            'samplerate': min(int(device_samplerate), 96000),
            'blocksize': 512,
            'dtype': 'float32',
            'name': f'高采样率模式({int(device_samplerate)}Hz)'
        })
    
    return configs

def analyze_error(error_msg, config_name):
    """分析错误并给出建议"""
    if 'PaErrorCode -9984' in error_msg:
        print(f"         🔍 主机API不兼容 - WASAPI设置与设备不匹配")
    elif 'PaErrorCode -9998' in error_msg:
        print(f"         🔍 通道数错误 - 单/立体声配置问题")
    elif 'PaErrorCode -9997' in error_msg:
        print(f"         🔍 采样率不支持 - 硬件限制")
    elif 'PaErrorCode -9999' in error_msg:
        print(f"         🔍 端点类型错误 - WASAPI权限问题")
    elif 'PaErrorCode -9996' in error_msg:
        print(f"         🔍 设备失效 - 被占用或断开")
    else:
        print(f"         🔍 未知错误: {error_msg[:50]}...")

if __name__ == "__main__":
    success = test_enhanced_wasapi_fixes()
    sys.exit(0 if success else 1)
