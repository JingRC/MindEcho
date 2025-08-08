#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MindEcho音频设备自动优化器
动态监控和优化音频设备配置，确保始终连接到最佳设备

基于智能WASAPI配置系统的结果:
- HECATE G4 Pro (设备24): 192000Hz/32样本/0.17ms延迟
- 自动WASAPI独占模式切换
- 实时设备状态监控
"""

import sounddevice as sd
import numpy as np
import time
import json
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class OptimalDeviceConfig:
    """最优设备配置"""
    device_id: int
    device_name: str
    sample_rate: int
    block_size: int
    expected_latency: float
    driver_mode: str
    quality_score: int
    settings: object

class MindEchoAudioOptimizer:
    """MindEcho音频设备自动优化器"""
    
    def __init__(self):
        """初始化优化器"""
        self.optimal_configs = []
        self.current_config = None
        self.monitoring = False
        self.monitor_thread = None
        self.callback = None
        
        # 加载已验证的最佳配置
        self.load_verified_configs()
        print("🚀 MindEcho音频优化器初始化完成")
    
    def load_verified_configs(self):
        """加载已验证的最佳配置"""
        try:
            config_file = Path("optimal_wasapi_config.json")
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 验证HECATE G4 Pro设备
                if self.verify_device_available(data['device']):
                    optimal_config = OptimalDeviceConfig(
                        device_id=data['device'],
                        device_name=data['name'],
                        sample_rate=data['samplerate'],
                        block_size=data['blocksize'],
                        expected_latency=float(data['expected_latency'].replace('ms', '')),
                        driver_mode=data['driver_type'],
                        quality_score=100,
                        settings=sd.WasapiSettings(exclusive=True)
                    )
                    
                    self.optimal_configs.append(optimal_config)
                    print(f"✅ 加载HECATE G4 Pro最佳配置:")
                    print(f"   ├─ 设备: {optimal_config.device_name}")
                    print(f"   ├─ 配置: {optimal_config.sample_rate}Hz/{optimal_config.block_size}样本")
                    print(f"   ├─ 延迟: {optimal_config.expected_latency}ms")
                    print(f"   └─ 模式: {optimal_config.driver_mode}")
                else:
                    print("⚠️ HECATE G4 Pro设备不可用，将使用动态发现")
            
        except Exception as e:
            print(f"⚠️ 配置加载失败: {e}")
        
        # 如果没有加载到最佳配置，进行动态发现
        if not self.optimal_configs:
            self.discover_optimal_configs()
    
    def verify_device_available(self, device_id):
        """验证设备是否可用"""
        try:
            devices = sd.query_devices()
            return (device_id < len(devices) and 
                   devices[device_id]['max_input_channels'] > 0)
        except:
            return False
    
    def discover_optimal_configs(self):
        """发现最优配置"""
        try:
            print("🔍 动态发现音频设备...")
            devices = sd.query_devices()
            
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    score = self.calculate_device_score(device)
                    
                    if score >= 70:  # 只考虑高质量设备
                        # 测试不同配置
                        best_config = self.find_best_config_for_device(i, device)
                        if best_config:
                            self.optimal_configs.append(best_config)
            
            # 按质量排序
            self.optimal_configs.sort(key=lambda x: x.quality_score, reverse=True)
            
            print(f"✅ 发现 {len(self.optimal_configs)} 个优化配置")
            
        except Exception as e:
            print(f"❌ 动态发现失败: {e}")
    
    def calculate_device_score(self, device):
        """计算设备评分"""
        score = 30  # 基础分
        name = device['name'].lower()
        
        if 'hecate' in name and 'g4 pro' in name:
            score += 50
        elif 'realtek' in name:
            score += 20
        
        # 采样率加分
        if device['default_samplerate'] >= 192000:
            score += 20
        elif device['default_samplerate'] >= 96000:
            score += 15
        
        return min(score, 100)
    
    def find_best_config_for_device(self, device_id, device):
        """为设备找到最佳配置"""
        try:
            device_name = device['name']
            sample_rate = int(device['default_samplerate'])
            
            # 测试不同的缓冲区大小
            test_block_sizes = [32, 64, 128, 256]
            
            for block_size in test_block_sizes:
                try:
                    # 快速测试配置
                    stream = sd.InputStream(
                        device=device_id,
                        channels=1,
                        samplerate=sample_rate,
                        blocksize=block_size,
                        dtype=np.float32
                    )
                    stream.close()
                    
                    # 计算延迟
                    latency = block_size / sample_rate * 1000
                    
                    # 确定驱动模式
                    driver_mode = "wasapi_exclusive" if "HECATE" in device_name.upper() else "wasapi_shared"
                    
                    return OptimalDeviceConfig(
                        device_id=device_id,
                        device_name=device_name,
                        sample_rate=sample_rate,
                        block_size=block_size,
                        expected_latency=latency,
                        driver_mode=driver_mode,
                        quality_score=self.calculate_device_score(device),
                        settings=sd.WasapiSettings(exclusive=(driver_mode == "wasapi_exclusive"))
                    )
                    
                except Exception:
                    continue
            
        except Exception as e:
            print(f"⚠️ 设备{device_id}配置测试失败: {e}")
        
        return None
    
    def get_mindecho_config(self, config: OptimalDeviceConfig):
        """转换为MindEcho格式配置"""
        return {
            'name': f'{config.device_name} - 优化模式',
            'device': config.device_id,
            'samplerate': config.sample_rate,
            'blocksize': config.block_size,
            'settings': config.settings,
            'expected_latency': 'ultra-low' if config.expected_latency < 1.0 else 'low',
            'expected_latency_ms': config.expected_latency,
            'quality_score': config.quality_score,
            'driver_mode': config.driver_mode
        }
    
    def get_best_config(self):
        """获取最佳配置"""
        if not self.optimal_configs:
            return None
        
        # 验证当前最佳配置是否可用
        best_config = self.optimal_configs[0]
        if self.verify_device_available(best_config.device_id):
            return self.get_mindecho_config(best_config)
        
        # 如果最佳设备不可用，寻找下一个可用设备
        for config in self.optimal_configs[1:]:
            if self.verify_device_available(config.device_id):
                return self.get_mindecho_config(config)
        
        return None
    
    def start_monitoring(self, callback=None):
        """开始监控设备变化"""
        if self.monitoring:
            return
        
        self.callback = callback
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print("🔄 开始监控音频设备变化...")
    
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        print("🔄 停止设备监控")
    
    def _monitor_loop(self):
        """监控循环"""
        while self.monitoring:
            try:
                current_best = self.get_best_config()
                
                if current_best and current_best != self.current_config:
                    print(f"🔄 检测到更优设备配置: {current_best['name']}")
                    
                    if self.callback:
                        self.callback(current_best)
                    
                    self.current_config = current_best
                
                time.sleep(5.0)  # 每5秒检查一次
                
            except Exception as e:
                print(f"⚠️ 监控错误: {e}")
                time.sleep(5.0)
    
    def print_status(self):
        """打印当前状态"""
        print("\n" + "=" * 50)
        print("🎯 MindEcho音频优化器状态")
        print("=" * 50)
        
        if self.optimal_configs:
            print(f"📱 发现 {len(self.optimal_configs)} 个优化配置:")
            
            for i, config in enumerate(self.optimal_configs, 1):
                status = "✅ 可用" if self.verify_device_available(config.device_id) else "❌ 不可用"
                print(f"{i}. {config.device_name} {status}")
                print(f"   ├─ 评分: {config.quality_score}/100")
                print(f"   ├─ 配置: {config.sample_rate}Hz/{config.block_size}样本")
                print(f"   ├─ 延迟: {config.expected_latency:.2f}ms")
                print(f"   └─ 模式: {config.driver_mode}")
            
            best_config = self.get_best_config()
            if best_config:
                print(f"\n🏆 当前推荐配置:")
                print(f"设备: {best_config['name']}")
                print(f"延迟: {best_config['expected_latency_ms']:.2f}ms")
                print(f"质量: {best_config['quality_score']}/100")
        else:
            print("❌ 未发现优化配置")
        
        print(f"\n🔄 监控状态: {'运行中' if self.monitoring else '已停止'}")

def test_optimizer():
    """测试优化器"""
    print("🚀 测试MindEcho音频优化器")
    
    optimizer = MindEchoAudioOptimizer()
    optimizer.print_status()
    
    # 测试获取最佳配置
    best_config = optimizer.get_best_config()
    if best_config:
        print(f"\n✨ 最佳配置测试:")
        print(f"设备ID: {best_config['device']}")
        print(f"采样率: {best_config['samplerate']}Hz")
        print(f"缓冲区: {best_config['blocksize']}样本")
        print(f"预期延迟: {best_config['expected_latency_ms']:.2f}ms")
        
        # 快速兼容性测试
        try:
            print(f"\n🧪 测试设备兼容性...")
            stream = sd.InputStream(
                device=best_config['device'],
                channels=1,
                samplerate=best_config['samplerate'],
                blocksize=best_config['blocksize'],
                dtype=np.float32,
                extra_settings=best_config['settings']
            )
            stream.close()
            print("✅ 兼容性测试通过")
        except Exception as e:
            print(f"❌ 兼容性测试失败: {e}")
    
    # 简短监控测试
    def test_callback(config):
        print(f"🔄 测试回调: 切换到 {config['name']}")
    
    optimizer.start_monitoring(test_callback)
    time.sleep(2)
    optimizer.stop_monitoring()

if __name__ == "__main__":
    test_optimizer()
