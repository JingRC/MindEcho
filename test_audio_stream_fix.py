"""
快速修复音频流启动错误测试
修复 sounddevice 参数错误和重叠帧分析器参数问题
"""

import sys
from pathlib import Path
import time

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_audio_stream_fix():
    """测试音频流启动修复"""
    
    print("🔧 测试音频流启动修复")
    print("="*60)
    print()
    print("修复内容:")
    print("1. ✅ 移除无效的sounddevice参数")
    print("   - 删除 clip_off, dither_off, never_drop_input")
    print("   - 这些参数在当前版本的sounddevice中不受支持")
    print()
    print("2. ✅ 修复重叠帧分析器参数计算")
    print("   - 避免负重叠大小问题")
    print("   - 自动调整frame_size确保合理的重叠")
    print()
    print("3. ✅ 保留核心功能")
    print("   - 低延迟模式 (latency='low')")
    print("   - 小缓冲区 (blocksize=256)")
    print("   - 异步音频处理架构")
    print()
    
    print("🚀 启动增强版测试...")
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        print("✅ 导入成功，启动界面...")
        integrated_main()
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 提供诊断信息
        print("\n🔍 诊断信息:")
        print("如果仍有问题，可能的原因:")
        print("1. 音频设备被其他程序占用")
        print("2. 麦克风权限未开启")
        print("3. sounddevice版本兼容性问题")
        print("4. 系统音频驱动问题")
        
        print("\n💡 建议:")
        print("1. 关闭其他音频程序")
        print("2. 检查系统音频设备设置")
        print("3. 尝试重启程序")

def show_audio_device_info():
    """显示音频设备信息"""
    
    print("\n🔍 音频设备诊断")
    print("="*60)
    
    try:
        import sounddevice as sd
        
        print("📋 可用音频设备:")
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            device_type = []
            if device['max_input_channels'] > 0:
                device_type.append('输入')
            if device['max_output_channels'] > 0:
                device_type.append('输出')
            
            print(f"  ID {i}: {device['name']}")
            print(f"       类型: {'/'.join(device_type)}")
            print(f"       输入通道: {device['max_input_channels']}")
            print(f"       默认采样率: {device['default_samplerate']}")
            print()
        
        print("🎙️ 默认输入设备:")
        try:
            default_input = sd.query_devices(kind='input')
            print(f"  设备: {default_input['name']}")
            print(f"  通道数: {default_input['max_input_channels']}")
            print(f"  采样率: {default_input['default_samplerate']}")
        except Exception as e:
            print(f"  ❌ 获取默认输入设备失败: {e}")
        
        print("\n📊 sounddevice版本信息:")
        print(f"  版本: {sd.__version__}")
        
    except Exception as e:
        print(f"❌ 获取设备信息失败: {e}")

if __name__ == "__main__":
    print("选择操作:")
    print("1. 🧪 直接测试修复效果")
    print("2. 🔍 查看音频设备信息")
    print("3. 📋 查看设备信息后测试")
    
    choice = input("\n请选择 (1-3): ").strip()
    
    if choice == '1':
        test_audio_stream_fix()
    elif choice == '2':
        show_audio_device_info()
    elif choice == '3':
        show_audio_device_info()
        input("\n按回车键继续测试...")
        test_audio_stream_fix()
    else:
        print("❌ 无效选择，直接测试")
        test_audio_stream_fix()
