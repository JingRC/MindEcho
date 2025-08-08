#!/usr/bin/env python3
"""
快速测试修改后的MindEcho设备选择功能
"""

import sys
import os

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(project_root, 'src'))

def test_device_discovery():
    """测试设备发现功能"""
    print("🎧 测试MindEcho设备发现功能")
    print("=" * 50)
    
    try:
        from gui.integrated_recording_interface import IntegratedAudioProcessor
        
        # 创建音频处理器实例
        processor = IntegratedAudioProcessor()
        
        print("🔍 测试WASAPI配置生成...")
        
        # 测试WASAPI配置生成
        configs = processor._get_optimal_wasapi_configs()
        
        if configs:
            print(f"\n✅ 成功生成{len(configs)}个配置:")
            for i, config in enumerate(configs, 1):
                device_id = config.get('device', 'N/A')
                name = config.get('name', 'Unknown')
                rate = config.get('samplerate', 0)
                block = config.get('blocksize', 0)
                latency = config.get('expected_latency_ms', 0)
                
                print(f"   {i}. {name}")
                print(f"      设备: {device_id}, 配置: {rate}Hz/{block}样本")
                print(f"      延迟: {latency:.2f}ms")
                
                # 检查是否是HECATE设备
                if 'hecate' in name.lower():
                    print(f"      🎧 HECATE G4 Pro设备 - 优化配置")
                print()
        else:
            print("❌ 没有生成任何配置")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def test_device_verification():
    """测试设备验证功能"""
    print("\n🧪 测试设备验证功能")
    print("=" * 50)
    
    try:
        from gui.integrated_recording_interface import IntegratedAudioProcessor
        
        processor = IntegratedAudioProcessor()
        
        # 测试已知的设备24
        print("🎯 测试设备24（HECATE G4 Pro）...")
        result = processor._verify_device_availability(24)
        print(f"   验证结果: {'✅ 可用' if result else '❌ 不可用'}")
        
        # 测试无效设备
        print("\n🧪 测试无效设备1...")
        result = processor._verify_device_availability(1)
        print(f"   验证结果: {'✅ 可用' if result else '❌ 不可用'}")
        
        print("\n🧪 测试无效设备10...")
        result = processor._verify_device_availability(10)
        print(f"   验证结果: {'✅ 可用' if result else '❌ 不可用'}")
        
    except Exception as e:
        print(f"❌ 验证测试失败: {e}")

if __name__ == "__main__":
    try:
        test_device_discovery()
        test_device_verification()
        
        print("\n🎉 测试完成！")
        print("💡 如果看到HECATE设备被正确识别，就可以启动MindEcho了")
        
    except Exception as e:
        print(f"\n❌ 总体测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        input("\n按回车键退出...")
