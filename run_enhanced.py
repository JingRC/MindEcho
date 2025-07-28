"""
MindEcho 增强版启动器
支持多种启动模式和GUI框架自动检测
"""

import sys
import os
import subprocess
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def check_package(package_name, import_name=None):
    """检查包是否已安装"""
    if import_name is None:
        import_name = package_name
    
    try:
        __import__(import_name)
        return True
    except ImportError:
        return False

def install_package(package_name):
    """安装包"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        return True
    except subprocess.CalledProcessError:
        return False

def check_dependencies():
    """检查所有依赖"""
    required_packages = {
        'numpy': 'numpy',
        'scipy': 'scipy', 
        'sounddevice': 'sounddevice',
        'matplotlib': 'matplotlib'
    }
    
    missing = []
    
    print("检查核心依赖...")
    for package, import_name in required_packages.items():
        if check_package(package, import_name):
            print(f"  ✅ {package}")
        else:
            print(f"  ❌ {package}")
            missing.append(package)
    
    return missing

def detect_gui_framework():
    """检测可用的GUI框架"""
    print("\n检查GUI框架...")
    
    # 检查PyQt6
    if check_package('PyQt6', 'PyQt6.QtWidgets'):
        print("  ✅ PyQt6")
        return "PyQt6"
    
    # 检查PyQt5
    if check_package('PyQt5', 'PyQt5.QtWidgets'):
        print("  ✅ PyQt5")
        return "PyQt5"
    
    # 检查tkinter
    if check_package('tkinter'):
        print("  ✅ tkinter")
        return "tkinter"
    
    print("  ❌ 没有可用的GUI框架")
    return None

def install_dependencies(packages):
    """安装依赖包"""
    print(f"\n安装依赖包: {', '.join(packages)}")
    
    for package in packages:
        print(f"正在安装 {package}...")
        if install_package(package):
            print(f"  ✅ {package} 安装成功")
        else:
            print(f"  ❌ {package} 安装失败")
            return False
    
    return True

def show_menu():
    """显示启动菜单"""
    print("\n" + "="*60)
    print("🎵 MindEcho 智能音频录制与分析系统 🎵")
    print("="*60)
    print()
    print("请选择启动模式:")
    print("1. 🚀 增强版 - 集成录音+实时音高分析+心电图可视化")
    print("2. 📱 标准版 - 基础录音功能 (PyQt界面)")
    print("3. 🔧 简化版 - 轻量级录音 (tkinter界面)")
    print("4. 🎨 渐变测试 - 改进的彩色渐变可视化器 (方案一)")
    print("5. ✨ 超细渐变 - 优化的超细平滑彩色渐变 (新版本)")
    print("6. 🎯 测试模式 - 功能测试")
    print("7. ❓ 帮助信息")
    print("0. 🚪 退出")
    print()
    
    choice = input("请输入选项 (0-7): ").strip()
    return choice

def launch_enhanced_mode():
    """启动增强版"""
    print("\n🚀 启动增强版 MindEcho...")
    print("功能包括:")
    print("  • 实时音频录制")
    print("  • 实时音高检测分析 (64fps)")
    print("  • 🎯 增强YIN音高检测算法（智能环境噪音过滤）")
    print("  • 🔇 智能降噪系统（基础频域降噪+AI降噪+音乐保护）")
    print("    - 环境噪音智能识别和过滤")
    print("    - 音高稳定性验证（智能区分噪音和真实高音）")
    print("    - 支持女高音、乐器高音等宽频域检测（60Hz-2000Hz）")
    print("    - 谐波结构验证（区分音乐音高和环境噪音）")
    print("    - 自适应降噪强度调整")
    print("    - 谐波结构保护")
    print("  • 交互式心电图可视化（智能缩放+滚动条导航）")
    print("  • 🔍 专业缩放系统（手动滑块+5档预设：0.5x/0.8x/1.5x/2.5x/5.0x）")
    print("  • 🖊️ 控制面板可调节线条粗细（8个预设+自定义滑块：0.1px-5.0px）")
    print("  • 📊 优化双行布局（控制按钮+状态信息分层显示，界面更清晰）")
    print("  • 详细音名显示（C4, D4, E4等）")
    print("  • 录音+分析一体化")
    print("  • 时间-音高二维曲线")
    print("  • 🎨 优化彩色渐变显示（支持长时间录制）")
    print("  • 🔤 智能中文字体支持（自动回退）")
    print("  • 💾 扩展数据缓冲区（支持5分钟历史）")
    
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
        integrated_main()
    except ImportError as e:
        print(f"❌ 增强版启动失败: {e}")
        print("尝试使用旧版界面...")
        try:
            from src.gui.enhanced_main_window import main as enhanced_main
            enhanced_main()
        except:
            print("可能缺少依赖，尝试标准版...")
            return False
    except Exception as e:
        print(f"❌ 增强版运行错误: {e}")
        return False
    
    return True

def launch_standard_mode():
    """启动标准版"""
    print("\n📱 启动标准版 MindEcho...")
    print("功能包括:")
    print("  • 音频录制")
    print("  • 文件管理")
    print("  • 基础播放")
    
    try:
        # 优先尝试集成录音界面
        from src.gui.integrated_recording_interface import main as pyqt_main
        pyqt_main()
    except ImportError:
        try:
            # 备选：尝试其他可用的PyQt界面
            from src.gui.enhanced_main_window import main as enhanced_main
            enhanced_main()
        except ImportError as e:
            print(f"❌ 标准版启动失败: {e}")
            print("建议使用增强版（选项1）获得完整功能")
            return False
    except Exception as e:
        print(f"❌ 标准版运行错误: {e}")
        return False
    
    return True

def launch_simple_mode():
    """启动简化版"""
    print("\n🔧 启动简化版 MindEcho...")
    print("功能包括:")
    print("  • 基础录音")
    print("  • 简单控制")
    
    try:
        from src.gui.simple_gui import main as tkinter_main
        tkinter_main()
    except ImportError as e:
        print(f"❌ 简化版启动失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 简化版运行错误: {e}")
        return False
    
    return True

def launch_ultra_thin_gradient():
    """启动超细平滑彩色渐变测试"""
    print("\n✨ 启动超细平滑彩色渐变测试...")
    print("优化功能包括:")
    print("  • 超细线条 (0.8px linewidth)")
    print("  • SciPy平滑插值 (3倍数据点密度)")
    print("  • 仅前端单个粒子效果")
    print("  • HSV彩虹色彩空间映射")
    print("  • 圆形端点和连接优化")
    print("  • 强制使用Matplotlib LineCollection")
    print("  • 解决PyQtGraph兼容性问题")
    
    try:
        # 直接运行超细渐变测试
        import subprocess
        import sys
        result = subprocess.run([sys.executable, "test_ultra_thin_gradient.py"], 
                              capture_output=False, cwd=".")
        return result.returncode == 0
    except Exception as e:
        print(f"❌ 超细渐变测试启动失败: {e}")
        print("尝试直接启动增强版...")
        return launch_enhanced_mode()

def launch_gradient_test():
    """启动渐变测试模式（方案一）"""
    print("\n🎨 启动改进的彩色渐变可视化器 (方案一)...")
    print("功能包括:")
    print("  • 专门解决Matplotlib 3.10.1兼容性问题")
    print("  • 5种渐变模式：彩色渐变、高性能渐变、分段彩色、光谱渐变、3D效果")
    print("  • 4个质量等级：性能优先 → 平衡 → 质量优先 → 极致效果")
    print("  • 内置强制刷新和回退机制")
    print("  • 优化的心电图模式（1.0px细线条）")
    print("  • 颤音测试数据生成")
    
    try:
        from src.gui.improved_matplotlib_visualizer import test_improved_matplotlib
        test_improved_matplotlib()
        return True
    except ImportError as e:
        print(f"❌ 渐变测试器启动失败: {e}")
        print("可能的原因：")
        print("  • PyQt6/PyQt5 未安装")
        print("  • matplotlib 未安装")
        print("  • numpy 未安装")
        return False
    except Exception as e:
        print(f"❌ 渐变测试器运行错误: {e}")
        return False

def launch_test_mode():
    """启动测试模式"""
    print("\n🎯 启动测试模式...")
    
    # 测试录音模块
    print("测试录音模块...")
    try:
        from src.audio_processing.recorder import AudioRecorder
        print("  ✅ AudioRecorder 模块正常")
    except Exception as e:
        print(f"  ❌ AudioRecorder 模块错误: {e}")
    
    # 测试音高检测
    print("测试音高检测模块...")
    try:
        from src.analysis.pitch_detection import PitchDetector
        print("  ✅ PitchDetector 模块正常")
    except Exception as e:
        print(f"  ❌ PitchDetector 模块错误: {e}")
    
    # 测试可视化
    print("测试可视化模块...")
    try:
        from src.analysis.staff_visualizer import StaffRenderer
        print("  ✅ StaffRenderer 模块正常")
    except Exception as e:
        print(f"  ❌ StaffRenderer 模块错误: {e}")
    
    print("\n测试完成！")
    input("按回车键继续...")

def show_help():
    """显示帮助信息"""
    print("\n" + "="*60)
    print("📖 MindEcho 帮助信息")
    print("="*60)
    print()
    print("🚀 增强版功能:")
    print("  • 一体化录音与实时音高分析界面")
    print("  • 64fps高频音高检测 (重叠帧分析)")
    print("  • 🎯 增强YIN音高检测算法")
    print("    - 环境噪音智能识别（基于能量、频谱平坦度、零交叉率）")
    print("    - 音高稳定性验证（智能区分环境噪音和真实音高变化）") 
    print("    - 宽频域支持（60Hz-2000Hz，包含女高音、乐器高音）")
    print("    - 谐波验证机制（防止八度错误，区分音乐和噪音）")
    print("    - 连续性跟踪（高频音高需2帧确认，低频需3帧确认）")
    print("  • 🔇 智能多模式降噪系统")
    print("    - 基础频域降噪 (改进的频谱减法+陷波滤波)")
    print("    - 环境噪音过滤器（50/60/100/120Hz等电源噪声）")
    print("    - 自适应降噪强度（根据音高动态调整）")
    print("    - 音乐感知谱减法（保护谐波结构）")
    print("    - 瞬态检测器（避免降噪破坏音乐瞬态）")
    print("    - AI降噪 (开发中)")
    print("    - 高级音乐保护降噪 (开发中)")
    print("  • 交互式心电图可视化（智能缩放+滚动条+拖拽操作）")
    print("  • 智能标注系统（根据缩放级别自动调整密度）")
    print("  • 详细音名显示（C4, D4, E4等完整十二平均律）")
    print("  • 实时绿色音高线条显示（心电图模式+彩色渐变模式）")
    print("  • 可调节线条粗细（8个预设+自定义滑块控制）")
    print("  • 多行状态显示（信息分类显示，界面更清晰）")
    print("  • 自动跟随音高区域功能")
    print("  • 实时音频电平监控")
    print("  • 多种渲染引擎（Matplotlib/PyQtGraph高性能选项）")
    print("  • 优化的彩色渐变显示（解决兼容性问题）")
    print("  • 录音控制：开始/暂停/停止/保存选项")
    print("  • 音高-时间二维曲线显示")
    print("  • 颜色渐变区分音域（低音蓝色到高音红色）")
    print("  • 支持不保存录音的纯分析模式")
    print()
    print("📱 标准版功能:")
    print("  • 音频录制和播放")
    print("  • 文件格式转换")
    print("  • 录音文件管理")
    print()
    print("🔧 简化版功能:")
    print("  • 基础录音功能")
    print("  • 轻量级界面")
    print()
    print("🔧 系统要求:")
    print("  • Python 3.7+")
    print("  • numpy, scipy, sounddevice")
    print("  • PyQt6/PyQt5 (推荐) 或 tkinter")
    print("  • matplotlib (增强版需要)")
    print()
    print("❓ 使用说明:")
    print("  • 增强版将录音、分析、可视化集成在一个界面")
    print("  • 支持边录音边分析，实时显示音高变化")
    print("  • 智能缩放系统：自动调整标注密度，解决音调重叠问题")
    print("  • 多种交互方式：滚动条导航，鼠标拖拽微调，滚轮快速移动")
    print("  • 详细音名标注：C4, D4, E4等完整十二平均律显示")
    print("  • 可选择录音模式：录音+分析+保存 / 仅分析 / 录音+保存")
    print("  • 时间-音高曲线横轴为时间，纵轴为频率(转换为音名)")
    print("  • 缩放控制：0.1x-5.0x精确缩放，智能/手动标注模式切换")
    print()
    input("按回车键返回主菜单...")

def main():
    """主函数"""
    # 检查依赖
    missing_deps = check_dependencies()
    
    if missing_deps:
        print(f"\n❌ 缺少依赖包: {', '.join(missing_deps)}")
        
        response = input("是否自动安装? (y/n): ").lower()
        if response == 'y':
            if not install_dependencies(missing_deps):
                print("依赖安装失败，请手动安装")
                input("按回车键退出...")
                return
        else:
            print("请手动安装依赖包后重新运行")
            input("按回车键退出...")
            return
    
    # 检测GUI框架
    gui_framework = detect_gui_framework()
    
    if gui_framework is None:
        print("\n❌ 没有可用的GUI框架")
        print("请安装 PyQt6、PyQt5 或确保 tkinter 可用")
        input("按回车键退出...")
        return
    
    print(f"\n✅ 使用 {gui_framework} 作为GUI框架")
    
    # 主循环
    while True:
        choice = show_menu()
        
        if choice == '1':
            # 增强版
            if gui_framework in ['PyQt6', 'PyQt5']:
                if not launch_enhanced_mode():
                    print("尝试标准版...")
                    launch_standard_mode()
            else:
                print("❌ 增强版需要 PyQt6 或 PyQt5")
                print("启动简化版...")
                launch_simple_mode()
        
        elif choice == '2':
            # 标准版
            if gui_framework in ['PyQt6', 'PyQt5']:
                launch_standard_mode()
            else:
                print("❌ 标准版需要 PyQt6 或 PyQt5")
                print("启动简化版...")
                launch_simple_mode()
        
        elif choice == '3':
            # 简化版
            launch_simple_mode()
        
        elif choice == '4':
            # 渐变测试
            if gui_framework in ['PyQt6', 'PyQt5']:
                launch_gradient_test()
            else:
                print("❌ 渐变测试需要 PyQt6 或 PyQt5")
                print("启动简化版...")
                launch_simple_mode()
        
        elif choice == '5':
            # 超细渐变测试
            if gui_framework in ['PyQt6', 'PyQt5']:
                launch_ultra_thin_gradient()
            else:
                print("❌ 超细渐变测试需要 PyQt6 或 PyQt5")
                print("启动简化版...")
                launch_simple_mode()
        
        elif choice == '6':
            # 测试模式
            launch_test_mode()
        
        elif choice == '7':
            # 帮助
            show_help()
        
        elif choice == '0':
            # 退出
            print("👋 感谢使用 MindEcho！")
            break
        
        else:
            print("❌ 无效选项，请重新选择")
            input("按回车键继续...")

if __name__ == "__main__":
    main()
