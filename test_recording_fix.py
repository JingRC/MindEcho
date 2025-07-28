#!/usr/bin/env python3
"""
MindEcho 音高检测修复测试脚本
测试录音时的实时音高检测和断续音调曲线功能
"""

import sys
import os
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    print("🎵 MindEcho 音高检测修复验证 - 实时录音测试")
    print("=" * 60)
    print()
    
    print("📋 修复内容:")
    print("  ✅ 降低增强YIN算法置信度要求 (0.15 → 0.1)")
    print("  ✅ 减少稳定性检查所需历史记录 (3帧 → 1帧)")
    print("  ✅ 扩展简单检测器频率范围 (80-500Hz → 60-1000Hz)")
    print("  ✅ 降低音高过滤阈值 (50Hz → 40Hz)")
    print("  ✅ 添加断续音调曲线支持（时间轴持续推进）")
    print("  ✅ 增加调试输出（实时显示检测结果）")
    print()
    
    print("🚀 现在启动增强版MindEcho进行实际测试...")
    print()
    print("测试建议：")
    print("  1. 点击'开始录音分析'按钮")
    print("  2. 尝试哼唱不同音高（从低音到高音）")
    print("  3. 观察终端中的实时音高检测输出")
    print("  4. 验证断续音调曲线（停止唱歌时时间轴继续，重新唱歌时曲线继续）")
    print("  5. 特别测试D5 (587Hz) 及以上频率的检测")
    print()
    
    input("按回车键启动增强版MindEcho...")
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        integrated_main()
    except ImportError as e:
        print(f"❌ 启动失败: {e}")
        print("请确保所有依赖已安装")
    except Exception as e:
        print(f"❌ 运行错误: {e}")

if __name__ == "__main__":
    main()
