"""
快速测试降噪模式音高检测修复
解决"静音中"问题
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_pitch_detection_fix():
    """测试音高检测修复"""
    
    print("🔧 测试降噪模式音高检测修复")
    print("="*60)
    print()
    print("本次修复内容:")
    print("1. ✅ 降低颤音检测器置信度阈值: 0.12 → 0.08")
    print("2. ✅ 降低有效音高频率阈值: 40Hz → 30Hz") 
    print("3. ✅ 添加异步处理循环调试信息")
    print("4. ✅ 添加颤音检测器调试输出")
    print()
    print("预期效果:")
    print("  🎵 应该能检测到更多音调")
    print("  🔊 界面不再显示'静音中'")
    print("  📊 控制台会显示音高检测信息")
    print("  🎼 颤音检测器调试信息")
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
    test_pitch_detection_fix()
