"""
测试自动启动实时分析修复
验证静音问题是否解决
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_realtime_analysis():
    """测试自动启动实时分析"""
    
    print("🔧 测试自动启动实时分析修复")
    print("="*60)
    print()
    print("修复内容:")
    print("1. ✅ 音频回调函数修复 - 不管是否录音都处理音频数据")
    print("2. ✅ 自动启动实时分析 - 界面启动后1秒自动开始分析")
    print("3. ✅ 颤音检测阈值优化 - 置信度0.08，频率30Hz")
    print("4. ✅ 异步处理队列调试 - 每1000次循环输出状态")
    print()
    print("预期效果:")
    print("  🎤 界面启动后自动显示'实时音高分析已启动'")
    print("  📊 控制台显示'🔄 异步处理状态'信息，队列大小>0")
    print("  🎵 应该能检测到音高，不再显示'静音中'")
    print("  🎼 颤音检测器调试信息应该出现")
    print()
    print("测试步骤:")
    print("1. 启动程序，等待1秒")
    print("2. 观察控制台是否显示'✅ 实时音高分析已启动'")
    print("3. 发出声音，观察是否检测到音高")
    print("4. 检查界面是否不再显示'静音中'")
    print()
    
    try:
        print("🚀 启动增强版测试...")
        from src.gui.integrated_recording_interface import main as integrated_main
        integrated_main()
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_realtime_analysis()
