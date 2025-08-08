#!/usr/bin/env python3
"""
WASAPI专业音频测试脚本
测试你的WASAPI设备的实际性能
"""

import sounddevice as sd
import numpy as np
import time

def test_wasapi_devices():
    """测试WASAPI设备的实际性能"""
    print("🔊 WASAPI设备专业测试")
    print("=" * 50)
    
    # 应用全局优化设置
    sd.default.latency = 'low'
    sd.default.dtype = 'float32'
    
    print("1. WASAPI设备详细信息:")
    devices = sd.query_devices()
    
    wasapi_devices = []
    for i, device in enumerate(devices):
        if device.get('hostapi') == 2:  # WASAPI设备
            wasapi_devices.append((i, device))
            low_latency = device.get('default_low_input_latency', 0.1) * 1000
            high_latency = device.get('default_high_input_latency', 0.2) * 1000
            print(f"   设备{i}: {device.get('name')}")
            print(f"      ├─ 输入通道: {device.get('max_input_channels', 0)}")
            print(f"      ├─ 采样率: {device.get('default_samplerate', 0)}Hz")
            print(f"      ├─ 低延迟: {low_latency:.1f}ms")
            print(f"      └─ 高延迟: {high_latency:.1f}ms")
    
    if not wasapi_devices:
        print("   ❌ 未检测到WASAPI设备")
        return
    
    print(f"\n2. 测试配置 (发现{len(wasapi_devices)}个WASAPI设备):")
    
    # 测试配置
    test_configs = [
        # 测试你的HECATE G4 Pro (设备22)
        {
            'name': 'HECATE G4 Pro (192kHz独占)',
            'device': 22,
            'samplerate': 192000,
            'blocksize': 32,  # 很小的缓冲区
            'exclusive': True
        },
        {
            'name': 'HECATE G4 Pro (96kHz独占)',
            'device': 22,
            'samplerate': 96000,
            'blocksize': 64,
            'exclusive': True
        },
        # 测试Realtek设备 (设备23)
        {
            'name': 'Realtek (48kHz独占)',
            'device': 23,
            'samplerate': 48000,
            'blocksize': 64,
            'exclusive': True
        },
        {
            'name': 'Realtek (48kHz共享)',
            'device': 23,
            'samplerate': 48000,
            'blocksize': 128,
            'exclusive': False
        }
    ]
    
    successful_configs = []
    
    for config in test_configs:
        print(f"\n   测试: {config['name']}")
        try:
            # 创建测试流
            stream_params = {
                'device': config['device'],
                'channels': 1,
                'samplerate': config['samplerate'],
                'blocksize': config['blocksize'],
                'dtype': np.float32,
                'latency': 'low',
                'extra_settings': sd.WasapiSettings(exclusive=config['exclusive'])
            }
            
            # 简单的回调函数用于测试
            def test_callback(indata, frames, time, status):
                if status:
                    print(f"      状态: {status}")
            
            stream_params['callback'] = test_callback
            
            # 尝试创建并启动流
            test_stream = sd.InputStream(**stream_params)
            test_stream.start()
            
            # 运行短时间测试
            time.sleep(0.5)
            
            # 停止并关闭流
            test_stream.stop()
            test_stream.close()
            
            # 计算理论延迟
            theoretical_latency = (config['blocksize'] / config['samplerate']) * 1000
            
            print(f"      ✅ 成功!")
            print(f"         ├─ 理论延迟: {theoretical_latency:.2f}ms")
            print(f"         ├─ 缓冲区: {config['blocksize']}样本")
            print(f"         └─ 模式: {'独占' if config['exclusive'] else '共享'}")
            
            successful_configs.append(config)
            
        except Exception as e:
            error_msg = str(e)
            if "Invalid sample rate" in error_msg:
                print(f"      ❌ 采样率不支持: {config['samplerate']}Hz")
            elif "Invalid number of channels" in error_msg:
                print(f"      ❌ 通道数不支持: 1通道")
            else:
                print(f"      ❌ 失败: {error_msg[:80]}...")
    
    # 测试结果总结
    print(f"\n3. 测试结果总结:")
    print(f"   ├─ 成功配置: {len(successful_configs)}/{len(test_configs)}个")
    
    if successful_configs:
        print(f"   ├─ 可用配置:")
        for config in successful_configs:
            latency = (config['blocksize'] / config['samplerate']) * 1000
            mode = "独占" if config['exclusive'] else "共享"
            print(f"      • {config['name']}: {latency:.2f}ms ({mode})")
        
        # 推荐最佳配置
        best_config = min(successful_configs, 
                         key=lambda x: (x['blocksize'] / x['samplerate']) * 1000)
        best_latency = (best_config['blocksize'] / best_config['samplerate']) * 1000
        
        print(f"   └─ 推荐配置: {best_config['name']} ({best_latency:.2f}ms)")
        
        # 生成代码建议
        print(f"\n4. 代码优化建议:")
        print(f"   在你的代码中使用以下配置获得最佳性能:")
        print(f"   ```python")
        print(f"   # 最佳WASAPI配置")
        print(f"   stream_params = {{")
        print(f"       'device': {best_config['device']},")
        print(f"       'samplerate': {best_config['samplerate']},")
        print(f"       'blocksize': {best_config['blocksize']},")
        print(f"       'channels': 1,")
        print(f"       'dtype': np.float32,")
        print(f"       'latency': 'low',")
        print(f"       'extra_settings': sd.WasapiSettings(exclusive={best_config['exclusive']})")
        print(f"   }}")
        print(f"   ```")
    else:
        print(f"   └─ ⚠️ 所有WASAPI配置都失败，使用DirectSound作为备选")
        print(f"       建议检查: 音频设备驱动、独占模式权限、采样率支持")
    
    print(f"\n🔊 WASAPI测试完成!")

if __name__ == "__main__":
    try:
        test_wasapi_devices()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
