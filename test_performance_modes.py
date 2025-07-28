"""
测试性能模式系统
验证GPU加速和性能管理器功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_performance_manager():
    """测试性能管理器"""
    print("🧪 测试性能管理器...")
    
    try:
        from src.audio_processing.performance_manager import PerformanceManager, PerformanceMode
        
        manager = PerformanceManager()
        
        print(f"\n📊 系统信息:")
        info = manager.get_system_info()
        for key, value in info.items():
            print(f"   {key}: {value}")
        
        print(f"\n🔄 测试模式切换:")
        for mode in PerformanceMode:
            print(f"\n   切换到: {mode.value}")
            success = manager.set_performance_mode(mode)
            if success:
                config = manager.get_current_config()
                optimization = manager.optimize_for_realtime()
                print(f"     检测频率: {optimization['predicted_actual_frequency']:.1f}Hz")
                print(f"     块大小: {config.chunk_size}")
                print(f"     GPU加速: {'✅' if config.use_gpu_acceleration else '❌'}")
                
                recommendations = optimization['recommendations']
                if recommendations:
                    print(f"     建议: {recommendations[0]}")
            else:
                print(f"     ❌ 切换失败")
                
        return True
        
    except Exception as e:
        print(f"❌ 性能管理器测试失败: {e}")
        return False

def test_gpu_accelerator():
    """测试GPU加速器"""
    print("\n🚀 测试GPU加速器...")
    
    try:
        from src.audio_processing.gpu_accelerator import GPUAcceleratedProcessor
        import numpy as np
        
        processor = GPUAcceleratedProcessor()
        
        print(f"GPU可用: {'✅' if processor.is_gpu_available() else '❌'}")
        print(f"GPU类型: {processor.gpu_type if processor.gpu_available else 'None'}")
        
        # 测试音高检测
        print(f"\n🎵 测试音高检测:")
        test_signal = np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 4410))  # 440Hz测试信号
        
        freq, conf = processor.accelerated_yin_detection(test_signal)
        print(f"   检测频率: {freq:.1f}Hz (目标: 440Hz)")
        print(f"   置信度: {conf:.3f}")
        print(f"   误差: {abs(freq - 440):.1f}Hz")
        
        # 测试渐变处理
        print(f"\n🎨 测试渐变处理:")
        test_frequencies = [200, 300, 400, 500, 600]
        test_timestamps = [0, 1, 2, 3, 4]
        colors = processor.accelerated_gradient_processing(test_frequencies, test_timestamps)
        print(f"   生成颜色数量: {len(colors)}")
        print(f"   颜色格式: {colors.shape}")
        print(f"   颜色范围: R={colors[:, 0].min():.2f}-{colors[:, 0].max():.2f}")
        
        # 性能基准测试（简化版，快速测试）
        print(f"\n⚡ 快速性能测试:")
        
        # 只做简单的CPU测试
        import time
        start_time = time.time()
        cpu_count = 0
        test_duration = 0.5  # 0.5秒快速测试
        
        while time.time() - start_time < test_duration:
            processor._cpu_yin_detection(test_signal, 0.25)
            cpu_count += 1
        
        actual_duration = time.time() - start_time
        cpu_detections_per_sec = cpu_count / actual_duration
        
        print(f"   CPU: {cpu_detections_per_sec:.1f} 检测/秒")
        
        if processor.is_gpu_available():
            print(f"   GPU: 将提供额外加速")
        else:
            print(f"   GPU: 不可用，使用CPU计算")
        
        return True
        
    except Exception as e:
        print(f"❌ GPU加速器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_integrated_interface():
    """测试集成界面的性能模式"""
    print("\n🖥️ 测试集成界面性能模式...")
    
    try:
        # 只测试导入，不创建GUI实例
        from src.gui.integrated_recording_interface import ECGStylePitchVisualizer
        print("✅ 集成界面模块导入成功")
        
        # 测试性能管理器导入
        from src.audio_processing.performance_manager import get_performance_manager
        manager = get_performance_manager()
        print("✅ 性能管理器可以被集成界面使用")
        
        # 测试GPU加速器导入
        from src.audio_processing.gpu_accelerator import GPUAcceleratedProcessor
        gpu_proc = GPUAcceleratedProcessor()
        print("✅ GPU加速器可以被集成界面使用")
        
        return True
        
    except Exception as e:
        print(f"❌ 集成界面测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("=" * 60)
    print("🎯 MindEcho 性能模式系统测试")
    print("=" * 60)
    
    results = []
    
    # 测试性能管理器
    results.append(("性能管理器", test_performance_manager()))
    
    # 测试GPU加速器
    results.append(("GPU加速器", test_gpu_accelerator())) 
    
    # 测试集成界面
    results.append(("集成界面", test_integrated_interface()))
    
    # 输出测试结果
    print("\n" + "=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)
    
    success_count = 0
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        if result:
            success_count += 1
    
    print(f"\n总体结果: {success_count}/{len(results)} 项测试通过")
    
    if success_count == len(results):
        print("🎉 所有测试通过！性能模式系统运行正常。")
    else:
        print("⚠️ 部分测试失败，请检查依赖和配置。")
    
    return success_count == len(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
