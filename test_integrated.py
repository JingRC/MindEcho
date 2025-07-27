"""
直接启动MindEcho集成录音分析界面的测试脚本
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        print("🚀 启动MindEcho集成录音分析界面...")
        print("功能包括:")
        print("  • 录音控制：开始/暂停/停止")
        print("  • 实时音高分析 (64fps)")
        print("  • 心电图式可视化")
        print("  • 时间-音高二维曲线")
        print("  • 录音保存选项")
        print()
        
        integrated_main()
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请确保所有依赖已安装:")
        print("  pip install numpy scipy matplotlib sounddevice PyQt6")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
