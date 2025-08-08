#!/usr/bin/env python3
"""
🚀 MindEcho 优化后监听系统测试
验证终极低延迟优化效果
"""

import sys
import time
import numpy as np
from pathlib import Path

# 添加项目路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from PyQt6.QtWidgets import QApplication
    from src.gui.integrated_recording_interface import IntegratedAudioProcessor
    
    def test_optimized_monitoring():
        """测试优化版监听功能"""
        print("🚀 启动 MindEcho 优化监听功能测试")
        print("=" * 60)
        
        app = QApplication(sys.argv)
        
        # 创建主窗口
        window = MindEchoMainWindow()
        window.show()
        
        # 显示优化功能说明
        print("✨ 本次优化包含以下改进:")
        print("   🔧 核心参数优化:")
        print("      ├─ 48kHz专业采样率（提升音质）")
        print("      ├─ 128样本块大小（约2.7ms，大幅降低延迟）")
        print("      ├─ 预分配缓冲区（避免运行时内存分配）")
        print("      └─ 浮点32位精度（提高音质）")
        print()
        print("   🎯 音频处理优化:")
        print("      ├─ 替换高延迟SciPy滤波器为IIR滤波器")
        print("      ├─ 合并增益与限幅减少循环次数")
        print("      ├─ 快速RMS计算与动态增益调整")
        print("      └─ 智能噪声抑制处理")
        print()
        print("   📊 系统级优化:")
        print("      ├─ 实时延迟测量与统计")
        print("      ├─ 进程高优先级设置")
        print("      ├─ 性能分析装饰器")
        print("      └─ 专用音频处理流水线")
        print()
        print("🎧 测试说明:")
        print("   1. 点击界面中的'开启监听'按钮")
        print("   2. 对着麦克风说话或唱歌")
        print("   3. 注意观察控制台的延迟统计信息")
        print("   4. 比较优化前后的音质和延迟差异")
        print("   5. 停止监听时会显示详细的性能报告")
        print()
        print("🎯 预期效果:")
        print("   • 延迟降低至 < 10ms（专业级）")
        print("   • 音质更自然，噪声更少")
        print("   • CPU使用率更低，更稳定")
        print("   • 实时性能监测")
        print()
        print("=" * 60)
        print("💡 现在可以开始测试了！点击监听按钮体验优化效果")
        
        # 运行应用
        sys.exit(app.exec())
    
    if __name__ == "__main__":
        test_optimized_monitoring()
        
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("🔧 请确保安装了所有依赖:")
    print("   pip install PyQt6 sounddevice numpy scipy matplotlib")
except Exception as e:
    print(f"❌ 启动失败: {e}")
    print("🔧 请检查代码是否有语法错误")
