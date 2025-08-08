#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MindEcho设备选择右键菜单功能快速测试
"""

import sys
import os

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

def test_device_detection():
    """测试设备检测功能"""
    print("🔍 测试音频设备检测...")
    
    try:
        import sounddevice as sd
        
        devices = sd.query_devices()
        print(f"📊 检测到 {len(devices)} 个音频设备:")
        
        wasapi_count = 0
        input_devices = []
        
        for i, device in enumerate(devices):
            device_name = device.get('name', 'Unknown')
            max_inputs = device.get('max_input_channels', 0)
            max_outputs = device.get('max_output_channels', 0)
            sample_rate = device.get('default_samplerate', 0)
            
            device_type = "输入" if max_inputs > 0 else "输出" if max_outputs > 0 else "无"
            
            print(f"   {i:2d}. {device_name}")
            print(f"       类型: {device_type} | 输入: {max_inputs} | 输出: {max_outputs} | 采样率: {sample_rate}Hz")
            
            if max_inputs > 0:
                input_devices.append((i, device_name, sample_rate))
                
            # 检测WASAPI设备
            if 'wasapi' in str(device.get('hostapi', '')).lower() or i >= 18:  # 通常WASAPI设备索引从18开始
                wasapi_count += 1
        
        print(f"\n📈 统计:")
        print(f"   WASAPI设备: {wasapi_count}")
        print(f"   输入设备: {len(input_devices)}")
        
        # 显示可用的输入设备
        if input_devices:
            print(f"\n🎤 可用输入设备:")
            for idx, name, sr in input_devices:
                print(f"   设备{idx}: {name} ({sr}Hz)")
        
        return True
        
    except Exception as e:
        print(f"❌ 设备检测失败: {e}")
        return False

def test_wasapi_config_generation():
    """测试WASAPI配置生成"""
    print("\n🔧 测试WASAPI配置生成...")
    
    try:
        # 导入音频处理器
        from src.gui.integrated_recording_interface import IntegratedAudioProcessor
        
        processor = IntegratedAudioProcessor()
        
        # 测试获取WASAPI配置
        configs = processor._get_optimal_wasapi_configs()
        
        print(f"✅ 生成了 {len(configs)} 个WASAPI配置:")
        
        for i, config in enumerate(configs):
            name = config.get('name', 'Unknown')
            device = config.get('device', 'N/A')
            samplerate = config.get('samplerate', 0)
            blocksize = config.get('blocksize', 0)
            quality_score = config.get('quality_score', 0)
            
            latency_ms = blocksize / samplerate * 1000 if samplerate > 0 else 0
            
            print(f"   {i+1}. {name}")
            print(f"      设备{device} | {samplerate}Hz/{blocksize}样本 | 延迟:{latency_ms:.2f}ms | 评分:{quality_score}")
        
        # 测试已验证配置加载
        verified_config = processor._load_verified_optimal_config()
        if verified_config:
            print(f"\n⭐ 已验证最佳配置:")
            print(f"   {verified_config['name']} (设备{verified_config['device']})")
        else:
            print(f"\n📝 没有已验证的配置")
        
        return True
        
    except Exception as e:
        print(f"❌ WASAPI配置生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🎧 MindEcho设备选择功能快速测试")
    print("=" * 50)
    
    # 测试设备检测
    device_test_ok = test_device_detection()
    
    # 测试WASAPI配置
    config_test_ok = test_wasapi_config_generation()
    
    print("\n" + "=" * 50)
    print("📊 测试结果:")
    print(f"   设备检测: {'✅ 通过' if device_test_ok else '❌ 失败'}")
    print(f"   配置生成: {'✅ 通过' if config_test_ok else '❌ 失败'}")
    
    if device_test_ok and config_test_ok:
        print("🎉 所有测试通过！可以启动完整测试。")
        print("\n💡 下一步：运行 test_device_selector.bat 启动图形界面测试")
    else:
        print("⚠️ 部分测试失败，请检查错误信息")
    
    return device_test_ok and config_test_ok

if __name__ == "__main__":
    try:
        success = main()
        input("\n按回车键退出...")
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n🔄 用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 测试脚本异常: {e}")
        import traceback
        traceback.print_exc()
        input("\n按回车键退出...")
        sys.exit(1)
