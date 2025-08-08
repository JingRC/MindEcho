#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MindEcho优化启动器
自动检测最佳音频设备配置并启动MindEcho

特性:
1. 自动验证HECATE G4 Pro最佳配置
2. 实时设备状态检查
3. 优化监听模式启动
4. 智能错误恢复
"""

import sys
import json
import time
import subprocess
from pathlib import Path
import sounddevice as sd

def print_banner():
    """显示启动横幅"""
    print("=" * 60)
    print("🚀 MindEcho优化启动器")
    print("   专为HECATE G4 Pro音频设备优化")
    print("   192000Hz / 32样本 / 0.17ms超低延迟")
    print("=" * 60)

def check_optimal_config():
    """检查最佳配置"""
    print("🔍 检查最佳音频配置...")
    
    try:
        config_file = Path("optimal_wasapi_config.json")
        if not config_file.exists():
            print("⚠️ 未找到最佳配置文件")
            return False, None
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 验证设备可用性
        devices = sd.query_devices()
        device_id = config.get('device')
        
        if device_id and device_id < len(devices):
            device = devices[device_id]
            if device['max_input_channels'] > 0:
                print(f"✅ 最佳设备可用: {config['name']}")
                print(f"   ├─ 设备ID: {device_id}")
                print(f"   ├─ 配置: {config['samplerate']}Hz/{config['blocksize']}样本")
                print(f"   ├─ 延迟: {config['expected_latency']}")
                print(f"   └─ 模式: {config['driver_type']}")
                return True, config
            else:
                print(f"❌ 设备 {device_id} 不可用")
                return False, config
        else:
            print(f"❌ 设备 {device_id} 不存在")
            return False, config
    
    except Exception as e:
        print(f"❌ 配置检查失败: {e}")
        return False, None

def check_audio_system():
    """检查音频系统"""
    print("🎧 检查音频系统...")
    
    try:
        devices = sd.query_devices()
        input_devices = [d for d in devices if d['max_input_channels'] > 0]
        
        print(f"   ✅ 发现 {len(input_devices)} 个输入设备")
        
        # 查找HECATE设备
        hecate_devices = []
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0 and 'hecate' in device['name'].lower():
                hecate_devices.append((i, device))
        
        if hecate_devices:
            print(f"   🎯 发现 {len(hecate_devices)} 个HECATE设备:")
            for device_id, device in hecate_devices:
                print(f"      设备{device_id}: {device['name']}")
        else:
            print("   ⚠️ 未发现HECATE设备")
        
        return True
    
    except Exception as e:
        print(f"   ❌ 音频系统检查失败: {e}")
        return False

def test_optimal_config(config):
    """测试最佳配置"""
    if not config:
        return False
    
    print("🧪 测试最佳配置兼容性...")
    
    try:
        device_id = config.get('device')
        sample_rate = config.get('samplerate')
        block_size = config.get('blocksize')
        
        # 快速兼容性测试
        stream = sd.InputStream(
            device=device_id,
            channels=1,
            samplerate=sample_rate,
            blocksize=block_size,
            dtype='float32'
        )
        stream.close()
        
        print("   ✅ 兼容性测试通过")
        return True
    
    except Exception as e:
        print(f"   ❌ 兼容性测试失败: {str(e)[:100]}...")
        return False

def run_intelligent_config():
    """运行智能配置器"""
    print("🔧 运行智能WASAPI配置器...")
    
    try:
        result = subprocess.run([
            sys.executable, 
            "intelligent_wasapi_config.py"
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("   ✅ 智能配置完成")
            return True
        else:
            print("   ❌ 智能配置失败")
            if result.stderr:
                print(f"   错误: {result.stderr[:200]}...")
            return False
    
    except subprocess.TimeoutExpired:
        print("   ⚠️ 配置超时，继续启动...")
        return False
    except Exception as e:
        print(f"   ❌ 配置运行失败: {e}")
        return False

def start_mindecho():
    """启动MindEcho"""
    print("🚀 启动MindEcho...")
    
    try:
        # 检查MindEcho主文件
        main_files = [
            "main.py",
            "src/main.py",
            "mindecho.py"
        ]
        
        main_file = None
        for file_path in main_files:
            if Path(file_path).exists():
                main_file = file_path
                break
        
        if not main_file:
            print("❌ 未找到MindEcho主程序文件")
            print("   请确保在MindEcho项目目录中运行此脚本")
            return False
        
        print(f"   📁 使用主文件: {main_file}")
        
        # 启动MindEcho
        process = subprocess.Popen([
            sys.executable, main_file
        ])
        
        print("   ✅ MindEcho启动成功")
        print(f"   🔢 进程ID: {process.pid}")
        
        return True
    
    except Exception as e:
        print(f"   ❌ MindEcho启动失败: {e}")
        return False

def show_optimization_tips():
    """显示优化提示"""
    print("\n🎯 优化提示:")
    print("1. 确保HECATE G4 Pro设备已正确连接")
    print("2. 在MindEcho中启动监听功能")
    print("3. 系统将自动连接到最佳配置(设备24)")
    print("4. 预期延迟: 0.17ms (192000Hz/32样本)")
    print("5. 如遇问题，重新运行智能配置器")

def main():
    """主程序"""
    print_banner()
    
    # 步骤1：检查音频系统
    if not check_audio_system():
        print("\n❌ 音频系统检查失败，无法继续")
        input("按Enter键退出...")
        return
    
    # 步骤2：检查最佳配置
    config_valid, config = check_optimal_config()
    
    if not config_valid:
        print("\n🔧 最佳配置不可用，尝试重新配置...")
        if run_intelligent_config():
            config_valid, config = check_optimal_config()
    
    # 步骤3：测试配置
    if config_valid:
        if not test_optimal_config(config):
            print("   ⚠️ 配置测试失败，但仍可尝试启动")
    
    # 步骤4：启动MindEcho
    print("\n" + "="*40)
    if start_mindecho():
        show_optimization_tips()
        
        print(f"\n🎉 MindEcho优化启动完成!")
        print("   💡 可以运行 'python audio_device_status_panel.py' 监控设备状态")
        
        # 选择是否启动状态面板
        try:
            choice = input("\n是否启动音频设备状态监控面板? (y/n): ").lower().strip()
            if choice in ['y', 'yes', '是', '']:
                print("🎛️ 启动音频设备状态面板...")
                subprocess.Popen([sys.executable, "audio_device_status_panel.py"])
        except:
            pass
        
    else:
        print("\n❌ MindEcho启动失败")
        print("💡 请检查项目文件是否完整，或手动运行main.py")
        input("按Enter键退出...")

if __name__ == "__main__":
    main()
