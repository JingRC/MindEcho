"""
MindEcho 超低延迟监听优化测试
验证96kHz采样率 + 128样本块的极致实时响应效果
"""

import sys
from pathlib import Path
import time

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_ultra_low_latency():
    """测试超低延迟监听优化"""
    
    print("🚀 测试超低延迟监听优化")
    print("=" * 60)
    print()
    print("本次优化包括:")
    print("1. ✅ 缓冲区大小: 256样本 → 128样本 (减少50%)")
    print("2. ✅ 采样率提升: 48kHz → 96kHz (实时响应翻倍)")
    print("3. ✅ 专业ASIO驱动: 支持极低延迟硬件加速")
    print("4. ✅ 智能处理优化: 减少不必要的计算开销")
    print("5. ✅ 实时性能监测: 音频处理时间 + 延迟统计")
    print()
    print("预期效果:")
    print("  ⚡ 理论延迟: ~1.33ms (128样本@96kHz)")
    print("  🎵 实时响应: 接近专业监听器级别")
    print("  🔧 音质保持: 保持高音稳定性和电流音保护")
    print("  📊 性能监测: 实时显示处理时间和延迟统计")
    print()
    
    # 显示优化细节
    print("🔧 技术优化细节:")
    print("  • 块大小: 256 → 128 样本")
    print("  • 采样率: 48kHz → 96kHz")
    print("  • 理论延迟: 5.33ms → 1.33ms")
    print("  • ASIO驱动: 专业级低延迟")
    print("  • 处理优化: 简化音频算法")
    print("  • 实时监测: 处理时间统计")
    print()
    
    print("🧪 测试说明:")
    print("  1. 启动监听功能，观察控制台延迟报告")
    print("  2. 说话或唱歌，感受实时响应速度")
    print("  3. 尝试高音和大音量，检查稳定性")
    print("  4. 观察'音频处理性能统计'和'延迟性能'评级")
    print()
    print("🎯 预期性能指标:")
    print("  • 平均延迟: < 2ms (极致级)")
    print("  • 处理时间: < 0.5ms (极佳级)")
    print("  • 延迟抖动: < 1ms")
    print("  • 音质稳定: 保持原有保护机制")
    print()
    
    # 启动测试
    try:
        print("🚀 启动超低延迟测试...")
        print("=" * 60)
        
        # 导入并启动主程序
        from src.gui.integrated_recording_interface import main as integrated_main
        integrated_main()
        
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        print("\n🔧 故障排除:")
        print("  1. 检查音频设备是否正常连接")
        print("  2. 尝试关闭其他音频应用程序")
        print("  3. 确认ASIO驱动是否可用")
        print("  4. 检查系统音频设置")

def show_optimization_details():
    """显示优化技术细节"""
    
    print("🔬 超低延迟优化技术细节")
    print("=" * 60)
    print()
    
    print("📊 延迟优化对比:")
    print("  原配置: 48kHz + 256样本 = 5.33ms")
    print("  新配置: 96kHz + 128样本 = 1.33ms")
    print("  延迟减少: 75% (4ms减少)")
    print()
    
    print("⚙️ 音频流配置:")
    print("  1. 优先级: ASIO > WaveOut > 兼容模式")
    print("  2. 采样率: 96000 Hz")
    print("  3. 块大小: 128 样本")
    print("  4. 延迟模式: 'low' (专业低延迟)")
    print("  5. 数据类型: float32")
    print()
    
    print("🚀 处理优化:")
    print("  1. 简化高频检测算法")
    print("  2. 减少不必要的FFT计算")
    print("  3. 优化DC偏移处理")
    print("  4. 内联音频限制器")
    print("  5. 实时性能监测")
    print()
    
    print("📈 性能监测:")
    print("  • 音频处理时间: 实时测量每次处理耗时")
    print("  • 延迟统计: 输入到输出的真实延迟")
    print("  • 性能评级: 自动评估系统性能")
    print("  • 抖动分析: 监测延迟稳定性")
    print()
    
    print("🛡️ 保护机制:")
    print("  • 电流音检测: 保持原有智能检测")
    print("  • 高音保护: 软限制器防止失真")
    print("  • 动态调整: 根据音量自适应处理")
    print("  • 兼容回退: 自动降级到稳定配置")

if __name__ == "__main__":
    print("选择测试模式:")
    print("1. 🚀 直接测试超低延迟优化")
    print("2. 🔬 查看优化技术细节")
    print("3. 📖 查看完整说明")
    
    choice = input("\n请选择 (1-3): ").strip()
    
    if choice == '1':
        test_ultra_low_latency()
    elif choice == '2':
        show_optimization_details()
        input("\n按回车键继续测试...")
        test_ultra_low_latency()
    elif choice == '3':
        show_optimization_details()
        print("\n" + "="*60)
        print("📖 使用说明")
        print("="*60)
        print()
        print("测试步骤:")
        print("1. 启动程序，点击'开启监听'")
        print("2. 观察控制台输出的延迟信息")
        print("3. 开始说话或唱歌，感受实时性")
        print("4. 尝试不同音量和音调")
        print("5. 观察性能统计报告")
        print()
        print("预期体验:")
        print("  ⚡ 几乎感觉不到延迟")
        print("  🎵 声音跟随嘴唇同步")
        print("  🔧 保持原有音质保护")
        print("  📊 实时性能监测信息")
        print()
        input("按回车键开始测试...")
        test_ultra_low_latency()
    else:
        print("无效选择，启动默认测试...")
        test_ultra_low_latency()
