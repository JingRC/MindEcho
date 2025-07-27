#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版智能缩放系统演示
不依赖外部库，仅展示核心概念
"""

class SmartZoomDemo:
    def __init__(self):
        self.zoom_levels = [0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0]
        self.notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        self.white_keys = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
        self.octaves = range(1, 8)  # C1 to B7
        
    def get_annotation_mode(self, zoom_level):
        """根据缩放级别确定标注模式"""
        if zoom_level <= 0.5:
            return "sparse"  # 稀疏模式
        elif zoom_level <= 1.5:
            return "medium"  # 中等模式
        else:
            return "dense"   # 密集模式
    
    def get_visible_notes(self, zoom_level, octave_range=4):
        """根据缩放级别获取可见音符"""
        mode = self.get_annotation_mode(zoom_level)
        
        if mode == "sparse":
            # 只显示八度线和C音
            notes = []
            for octave in self.octaves:
                if octave >= 2 and octave <= 6:  # 限制显示范围
                    notes.append(f"C{octave}")
            return notes
            
        elif mode == "medium":
            # 显示白键
            notes = []
            for octave in self.octaves:
                if octave >= 2 and octave <= 6:
                    for note in self.white_keys:
                        notes.append(f"{note}{octave}")
            return notes
            
        else:  # dense
            # 显示所有半音，但根据缩放级别进一步过滤
            notes = []
            for octave in self.octaves:
                if octave >= 2 and octave <= 6:
                    for note in self.notes:
                        # 在超高缩放时，考虑进一步智能过滤
                        if zoom_level >= 3.0:
                            notes.append(f"{note}{octave}")
                        elif zoom_level >= 2.0:
                            # 中高缩放时，跳过一些#号
                            if '#' not in note or note in ['C#', 'F#']:
                                notes.append(f"{note}{octave}")
                        else:
                            # 低缩放时，主要显示重要音符
                            if note in self.white_keys or note in ['C#', 'F#', 'A#']:
                                notes.append(f"{note}{octave}")
            return notes
    
    def demonstrate_smart_zoom(self):
        """演示智能缩放功能"""
        print("🎵 智能缩放系统演示")
        print("=" * 50)
        
        for zoom in self.zoom_levels:
            mode = self.get_annotation_mode(zoom)
            notes = self.get_visible_notes(zoom)
            
            mode_desc = {
                "sparse": "稀疏(八度+C音)",
                "medium": "中等(白键)",
                "dense": "密集(全部半音)"
            }
            
            print(f"\n🔍 缩放级别: {zoom:.1f}x")
            print(f"📊 标注模式: {mode_desc[mode]}")
            print(f"🎵 显示音符数量: {len(notes)}")
            print(f"🎼 音符预览: {', '.join(notes[:8])}" + ("..." if len(notes) > 8 else ""))
            
            # 计算显示密度
            if zoom <= 1.0:
                display_range = f"{4.0/zoom:.1f}个八度"
            else:
                display_range = f"{4.0/zoom:.1f}个八度"
            print(f"📏 显示范围: {display_range}")
            print("-" * 40)

def main():
    print("🎯 MindEcho 智能缩放系统 - 核心算法演示")
    print("🔧 解决音调密集重叠问题的智能方案")
    print()
    
    demo = SmartZoomDemo()
    demo.demonstrate_smart_zoom()
    
    print("\n✨ 智能缩放优势:")
    print("  • 🎯 自动适应: 根据缩放级别智能调整标注密度")
    print("  • 🎨 视觉清晰: 避免音符标注重叠和拥挤")
    print("  • 🎵 音乐准确: 保持音乐理论的准确性和完整性") 
    print("  • 🎛️ 用户控制: 提供手动/自动模式切换")
    print("  • 📊 三级策略: 稀疏/中等/密集三种显示策略")
    
    print("\n🚀 完整版本请安装依赖后运行:")
    print("  pip install sounddevice matplotlib numpy PyQt6 scipy")
    print("  python run_enhanced.py")

if __name__ == "__main__":
    main()
