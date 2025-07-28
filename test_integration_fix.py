#!/usr/bin/env python3
"""
快速测试修复后的MindEcho集成
"""

def test_integration_fix():
    """测试集成修复"""
    print("🔍 测试MindEcho集成修复...")
    
    try:
        # 测试语法是否正确
        print("1️⃣ 测试语法修复...")
        from src.gui.integrated_recording_interface import IntegratedAudioProcessor
        print("   ✅ IntegratedAudioProcessor 导入成功")
        
        # 测试初始化
        print("2️⃣ 测试处理器初始化...")
        processor = IntegratedAudioProcessor()
        print("   ✅ 处理器初始化成功")
        
        # 测试设置降噪
        print("3️⃣ 测试降噪设置...")
        processor.set_noise_reduction_mode("基础频域降噪")
        print("   ✅ 降噪模式设置成功")
        
        # 测试增强模块导入
        print("4️⃣ 测试增强模块...")
        from enhanced_yin_detector import StabilizedAudioProcessor
        from smart_noise_reduction import IntegratedSmartProcessor
        print("   ✅ 增强模块导入成功")
        
        print("\n🎉 所有测试通过！MindEcho增强功能已准备就绪")
        return True
        
    except SyntaxError as e:
        print(f"   ❌ 语法错误: {e}")
        return False
    except ImportError as e:
        print(f"   ❌ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"   ❌ 其他错误: {e}")
        return False

if __name__ == "__main__":
    success = test_integration_fix()
    
    if success:
        print("\n🚀 可以启动MindEcho增强版了！")
        print("💡 新功能包括:")
        print("   • 增强YIN音高检测（防止D5等噪音误检测）")
        print("   • 智能降噪系统（环境噪音过滤）")
        print("   • 音高稳定性验证")
        print("   • 自适应降噪强度调整")
    else:
        print("\n❌ 还有问题需要修复")
