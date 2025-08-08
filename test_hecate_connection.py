#!/usr/bin/env python3
"""
HECATE G4 Pro 设备连接测试工具
测试不同配置的设备连接和音频流稳定性
"""

import sounddevice as sd
import numpy as np
import time
import traceback

def find_hecate_device():
    """查找HECATE G4 Pro设备"""
    try:
        devices = sd.query_devices()
        print(f"🔍 扫描{len(devices)}个音频设备...")
        
        hecate_devices = []
        for i, device in enumerate(devices):
            name = device.get('name', '').lower()
            if 'hecate' in name and device.get('max_input_channels', 0) > 0:
                hecate_devices.append({
                    'id': i,
                    'name': device.get('name', 'Unknown'),
                    'max_inputs': device.get('max_input_channels', 0),
                    'max_outputs': device.get('max_output_channels', 0),
                    'default_samplerate': device.get('default_samplerate', 0),
                    'device_info': device
                })
                print(f"✅ 发现HECATE设备 {i}: {device.get('name', 'Unknown')}")
                print(f"   输入通道: {device.get('max_input_channels', 0)}")
                print(f"   输出通道: {device.get('max_output_channels', 0)}")
                print(f"   默认采样率: {device.get('default_samplerate', 0)}Hz")
        
        return hecate_devices
    except Exception as e:
        print(f"❌ 设备扫描失败: {e}")
        return []

def test_device_config(device_id, samplerate, blocksize, exclusive=False, test_duration=2.0):
    """测试特定设备配置"""
    try:
        print(f"\n🧪 测试设备{device_id}: {samplerate}Hz/{blocksize}样本/{'独占' if exclusive else '共享'}模式")
        
        # 创建WASAPI设置
        settings = sd.WasapiSettings(exclusive=exclusive)
        
        # 音频数据统计
        audio_stats = {
            'samples_processed': 0,
            'max_level': 0.0,
            'avg_level': 0.0,
            'level_sum': 0.0,
            'callback_count': 0
        }
        
        def audio_callback(indata, frames, time, status):
            """音频回调函数"""
            if status:
                print(f"⚠️ 音频状态: {status}")
            
            # 统计音频数据
            audio_stats['callback_count'] += 1
            audio_stats['samples_processed'] += len(indata)
            
            level = float(np.max(np.abs(indata)))
            audio_stats['max_level'] = max(audio_stats['max_level'], level)
            audio_stats['level_sum'] += level
        
        # 创建音频流
        stream = sd.InputStream(
            device=device_id,
            channels=1,
            samplerate=samplerate,
            blocksize=blocksize,
            dtype='float32',
            callback=audio_callback,
            extra_settings=settings
        )
        
        print(f"   创建音频流成功...")
        
        # 启动流
        stream.start()
        print(f"   音频流已启动，测试{test_duration}秒...")
        
        # 测试期间
        start_time = time.time()
        while time.time() - start_time < test_duration:
            time.sleep(0.1)
            
            # 实时显示统计
            if audio_stats['callback_count'] > 0:
                avg_level = audio_stats['level_sum'] / audio_stats['callback_count']
                print(f"\r   实时统计: 回调{audio_stats['callback_count']}次, "
                      f"处理样本{audio_stats['samples_processed']}, "
                      f"最大电平{audio_stats['max_level']:.4f}, "
                      f"平均电平{avg_level:.4f}", end='')
        
        print()  # 换行
        
        # 停止流
        stream.stop()
        stream.close()
        
        # 计算最终统计
        if audio_stats['callback_count'] > 0:
            final_avg = audio_stats['level_sum'] / audio_stats['callback_count']
            expected_callbacks = int(test_duration * samplerate / blocksize)
            callback_ratio = audio_stats['callback_count'] / expected_callbacks
            
            print(f"✅ 测试完成!")
            print(f"   总回调次数: {audio_stats['callback_count']} (期望: {expected_callbacks}, 比率: {callback_ratio:.2f})")
            print(f"   总处理样本: {audio_stats['samples_processed']}")
            print(f"   最大音频电平: {audio_stats['max_level']:.4f}")
            print(f"   平均音频电平: {final_avg:.4f}")
            print(f"   估计延迟: {blocksize / samplerate * 1000:.2f}ms")
            
            # 评估测试结果
            success = callback_ratio >= 0.9 and audio_stats['callback_count'] > 0
            if success:
                print(f"   ✅ 配置测试通过")
            else:
                print(f"   ⚠️ 配置可能不稳定")
                
            return success
        else:
            print(f"❌ 没有接收到音频回调")
            return False
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        print(f"   错误详情: {traceback.format_exc()}")
        return False

def comprehensive_hecate_test():
    """全面的HECATE设备测试"""
    print("🎧 HECATE G4 Pro 设备连接测试工具")
    print("=" * 50)
    
    # 查找HECATE设备
    hecate_devices = find_hecate_device()
    
    if not hecate_devices:
        print("❌ 未找到HECATE设备")
        return
    
    print(f"\n🎯 找到{len(hecate_devices)}个HECATE设备，开始测试...")
    
    # 测试配置
    test_configs = [
        # 稳定性优先配置
        {'sr': 48000, 'bs': 256, 'ex': False, 'desc': '稳定配置(48kHz/256/共享)'},
        {'sr': 48000, 'bs': 128, 'ex': False, 'desc': '平衡配置(48kHz/128/共享)'},
        {'sr': 48000, 'bs': 256, 'ex': True, 'desc': '稳定独占(48kHz/256/独占)'},
        
        # 高性能配置
        {'sr': 96000, 'bs': 128, 'ex': False, 'desc': '高性能配置(96kHz/128/共享)'},
        {'sr': 96000, 'bs': 64, 'ex': False, 'desc': '高性能配置(96kHz/64/共享)'},
        {'sr': 96000, 'bs': 128, 'ex': True, 'desc': '高性能独占(96kHz/128/独占)'},
        
        # 极致配置（如果支持）
        {'sr': 192000, 'bs': 64, 'ex': False, 'desc': '极致配置(192kHz/64/共享)'},
        {'sr': 192000, 'bs': 32, 'ex': False, 'desc': '极致配置(192kHz/32/共享)'},
        {'sr': 192000, 'bs': 64, 'ex': True, 'desc': '极致独占(192kHz/64/独占)'},
    ]
    
    # 对每个HECATE设备进行测试
    for device in hecate_devices:
        device_id = device['id']
        device_name = device['name']
        
        print(f"\n🎧 测试设备: {device_name} (ID: {device_id})")
        print("-" * 40)
        
        successful_configs = []
        failed_configs = []
        
        for config in test_configs:
            # 检查设备是否支持该采样率
            default_sr = device['device_info'].get('default_samplerate', 48000)
            if config['sr'] > default_sr * 4:  # 跳过过高的采样率
                print(f"⏭️  跳过配置: {config['desc']} (超出设备能力)")
                continue
            
            print(f"\n📋 测试: {config['desc']}")
            
            success = test_device_config(
                device_id, 
                config['sr'], 
                config['bs'], 
                config['ex'],
                test_duration=3.0  # 3秒测试
            )
            
            if success:
                successful_configs.append(config)
            else:
                failed_configs.append(config)
        
        # 总结设备测试结果
        print(f"\n📊 设备 {device_name} 测试总结:")
        print(f"   ✅ 成功配置: {len(successful_configs)}")
        print(f"   ❌ 失败配置: {len(failed_configs)}")
        
        if successful_configs:
            print("   🏆 推荐配置:")
            for i, config in enumerate(successful_configs[:3], 1):
                latency = config['bs'] / config['sr'] * 1000
                print(f"      {i}. {config['desc']} (延迟: {latency:.2f}ms)")
        
        print()

if __name__ == "__main__":
    try:
        comprehensive_hecate_test()
    except KeyboardInterrupt:
        print("\n🛑 用户中断测试")
    except Exception as e:
        print(f"\n❌ 测试过程发生错误: {e}")
        traceback.print_exc()
    finally:
        print("\n🔚 测试结束")
        input("按回车键退出...")
