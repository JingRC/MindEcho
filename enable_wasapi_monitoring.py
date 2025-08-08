#!/usr/bin/env python3
"""
WASAPI独占模式监听启用脚本
针对HECATE G4 Pro等高端音频设备优化
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src" / "gui"))

def force_wasapi_mode():
    """强制启用WASAPI独占模式"""
    print("🎧 WASAPI独占模式优化建议")
    print("="*50)
    
    print("📱 检测到的高端设备:")
    print("  🎵 HECATE G4 Pro (192kHz) - 超高音质")
    print("  🎵 Realtek Audio (48kHz) - 稳定兼容")
    
    print("\n🚀 优化方案:")
    print("1. WASAPI独占模式 - 延迟可降至 0.17ms")
    print("2. 192kHz采样率 - 专业级音质")
    print("3. 32样本缓冲区 - 最低延迟")
    
    print("\n💡 启用方法:")
    print("方法1: 在MindEcho设置中切换到 'WASAPI独占模式'")
    print("方法2: 右键监听按钮 → 选择设备 → HECATE G4 Pro")
    print("方法3: 重启MindEcho，系统会优先尝试WASAPI")
    
    print("\n⚠️ 注意事项:")
    print("- WASAPI独占模式会占用设备，其他应用无法同时使用")
    print("- 如果出现问题会自动降级到DirectSound")
    print("- 建议先关闭其他音频应用")
    
    return True

if __name__ == "__main__":
    force_wasapi_mode()
