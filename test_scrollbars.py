#!/usr/bin/env python3
"""
测试心电图滚动条功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def main():
    print("🎵 启动心电图滚动条功能测试版...")
    print()
    print("✨ 新增滚动条功能:")
    print("  📜 垂直滚动条: 右侧淡绿色滚动条，控制音高范围上下移动")
    print("  📜 水平滚动条: 底部淡绿色滚动条，控制时间轴左右查看")
    print("  🖱️ 鼠标滚轮: 改为上下移动音高视图（原缩放功能移至滚动条）")
    print("  🔄 实时同步: 鼠标拖拽和滚动条操作完全同步")
    print()
    print("🎛️ 操作方式:")
    print("  • 垂直滚动条: 拖拽或点击调整音高显示范围")
    print("  • 水平滚动条: 拖拽或点击查看历史数据")
    print("  • 鼠标滚轮: 上下滚动移动音高视图中心")
    print("  • 鼠标拖拽: 保持原有拖拽功能，并同步更新滚动条")
    print("  • 重置视图: 一键回到默认状态，滚动条同步复位")
    print()
    print("🎨 视觉效果:")
    print("  • 滚动条: 半透明淡绿色设计，与心电图风格一致")
    print("  • 悬停效果: 鼠标悬停时滚动条变亮")
    print("  • 右下角: 小装饰块填充滚动条交叉区域")
    print()
    print("🔧 技术特性:")
    print("  • 双向同步: 滚动条和鼠标操作互相同步")
    print("  • 信号阻塞: 避免循环触发事件")
    print("  • 范围限制: 音高1.5-6.5，时间0-60秒")
    print()
    print("🚀 启动集成界面...")
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        integrated_main()
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
