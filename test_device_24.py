#!/usr/bin/env python3
"""
HECATE G4 Pro 设备24专用测试工具
专门测试已知可用的设备24配置
"""

import sounddevice as sd
import numpy as np
import time

def test_device_24():
    """专门测试设备24的已知配置"""
    print("🎧 HECATE G4 Pro 设备24专用测试")
    print("=" * 50)
    
    device_id = 24
    
    # 根据测试结果，我们知道设备24支持192kHz/32样本
    test_config = {
        'device': device_id,
        'samplerate': 192000,
        'blocksize': 32,
        'channels': 1,
        'dtype': 'float32'
    }
    
    try:
        # 测试WASAPI共享模式
        print("🧪 测试WASAPI共享模式...")
        settings_shared = sd.WasapiSettings(exclusive=False)
        
        # 音频统计
        stats = {'samples': 0, 'callbacks': 0, 'peak': 0.0}
        
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"状态: {status}")
            
            stats['callbacks'] += 1
            stats['samples'] += len(indata)
            stats['peak'] = max(stats['peak'], float(np.max(np.abs(indata))))
        
        # 创建输入流
        stream = sd.InputStream(
            device=test_config['device'],
            channels=test_config['channels'],
            samplerate=test_config['samplerate'],
            blocksize=test_config['blocksize'],
            dtype=test_config['dtype'],
            callback=audio_callback,
            extra_settings=settings_shared
        )
        
        print(f"✅ 流创建成功: {test_config['samplerate']}Hz/{test_config['blocksize']}样本")
        
        # 启动流并测试3秒
        stream.start()
        print("🎵 开始3秒音频测试...")
        
        for i in range(30):  # 3秒，每100ms显示一次状态
            time.sleep(0.1)
            if i % 5 == 0:  # 每0.5秒显示一次
                theoretical_latency = test_config['blocksize'] / test_config['samplerate'] * 1000
                print(f"  📊 运行中... {i/10:.1f}s - 回调: {stats['callbacks']}, "
                      f"样本: {stats['samples']}, 峰值: {stats['peak']:.4f}, "
                      f"延迟: {theoretical_latency:.2f}ms")
        
        stream.stop()
        stream.close()
        
        # 显示最终统计
        total_time = 3.0
        expected_callbacks = int(total_time * test_config['samplerate'] / test_config['blocksize'])
        callback_ratio = stats['callbacks'] / expected_callbacks
        
        print("\n📊 测试完成统计:")
        print(f"   总运行时间: {total_time}秒")
        print(f"   音频回调: {stats['callbacks']} (期望: {expected_callbacks}, 比率: {callback_ratio:.2f})")
        print(f"   处理样本: {stats['samples']}")
        print(f"   最大峰值: {stats['peak']:.4f}")
        print(f"   理论延迟: {test_config['blocksize'] / test_config['samplerate'] * 1000:.2f}ms")
        
        if callback_ratio >= 0.95:
            print("   ✅ 设备24工作正常！")
            return True
        else:
            print("   ⚠️ 设备24可能不稳定")
            return False
            
    except Exception as e:
        print(f"❌ 设备24测试失败: {e}")
        return False

def test_device_24_exclusive():
    """测试设备24的独占模式"""
    print("\n🎯 测试WASAPI独占模式...")
    
    device_id = 24
    
    try:
        settings_exclusive = sd.WasapiSettings(exclusive=True)
        
        # 简单的创建和关闭测试
        stream = sd.InputStream(
            device=device_id,
            channels=1,
            samplerate=192000,
            blocksize=32,
            dtype='float32',
            extra_settings=settings_exclusive
        )
        
        stream.start()
        time.sleep(1.0)  # 1秒测试
        stream.stop()
        stream.close()
        
        print("✅ WASAPI独占模式测试成功")
        return True
        
    except Exception as e:
        print(f"❌ WASAPI独占模式失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🎧 HECATE G4 Pro 设备24专用连接测试")
    print("=" * 60)
    
    # 检查设备是否存在
    try:
        devices = sd.query_devices()
        if len(devices) <= 24:
            print("❌ 设备24不存在")
            return
        
        device_24 = devices[24]
        print(f"📱 设备24信息:")
        print(f"   名称: {device_24.get('name')}")
        print(f"   输入通道: {device_24.get('max_input_channels')}")
        print(f"   原生采样率: {device_24.get('default_samplerate')}Hz")
        
        if device_24.get('max_input_channels', 0) <= 0:
            print("❌ 设备24没有输入通道")
            return
        
    except Exception as e:
        print(f"❌ 设备查询失败: {e}")
        return
    
    # 执行测试
    print(f"\n🧪 开始设备24专用测试...")
    
    shared_success = test_device_24()
    exclusive_success = test_device_24_exclusive()
    
    print(f"\n🎯 测试结果总结:")
    print(f"   WASAPI共享模式: {'✅ 成功' if shared_success else '❌ 失败'}")
    print(f"   WASAPI独占模式: {'✅ 成功' if exclusive_success else '❌ 失败'}")
    
    if shared_success or exclusive_success:
        print(f"\n🎉 设备24可以正常使用！")
        print(f"💡 建议在MindEcho右键监听按钮，选择设备24的192kHz配置")
    else:
        print(f"\n❌ 设备24仍然有问题，可能需要检查驱动或设备连接")

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
        print("\n🔚 测试结束")
        input("按回车键退出...")
