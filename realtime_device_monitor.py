#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时音频设备监控器 - 为MindEcho优化监听体验
动态监控音频设备变化并自动切换到最佳设备

功能特点:
1. 实时监控音频设备插拔
2. 自动评估新设备质量
3. 智能切换到更优设备
4. 设备性能实时测试
5. 延迟和音质监控
6. 设备故障自动恢复
"""

import sounddevice as sd
import numpy as np
import time
import threading
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from pathlib import Path
import hashlib

@dataclass
class DeviceStatus:
    """设备状态信息"""
    device_id: int
    name: str
    is_available: bool
    quality_score: int
    current_latency: float
    sample_rate: int
    block_size: int
    error_count: int
    last_test_time: float
    connection_stability: float

class RealTimeAudioDeviceMonitor:
    """实时音频设备监控器"""
    
    def __init__(self, config_file: str = "device_monitor_config.json"):
        """初始化监控器"""
        self.config_file = config_file
        self.monitoring = False
        self.current_device = None
        self.device_statuses = {}
        self.monitor_thread = None
        self.callback_function = None
        
        # 监控配置
        self.monitor_interval = 2.0  # 监控间隔（秒）
        self.device_test_interval = 10.0  # 设备测试间隔（秒）
        self.auto_switch_enabled = True  # 自动切换启用
        self.switch_threshold = 20  # 切换阈值（质量评分差异）
        
        # 性能统计
        self.stats = {
            'total_switches': 0,
            'failed_switches': 0,
            'average_latency': 0.0,
            'uptime': 0.0,
            'start_time': time.time()
        }
        
        self.load_config()
        print("🔄 实时音频设备监控器初始化完成")
    
    def load_config(self):
        """加载配置文件"""
        try:
            if Path(self.config_file).exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                self.monitor_interval = config.get('monitor_interval', 2.0)
                self.auto_switch_enabled = config.get('auto_switch_enabled', True)
                self.switch_threshold = config.get('switch_threshold', 20)
                
                print(f"✅ 加载配置: 监控间隔 {self.monitor_interval}s, 自动切换 {self.auto_switch_enabled}")
        except Exception as e:
            print(f"⚠️ 配置加载失败，使用默认值: {e}")
    
    def save_config(self):
        """保存配置文件"""
        try:
            config = {
                'monitor_interval': self.monitor_interval,
                'auto_switch_enabled': self.auto_switch_enabled,
                'switch_threshold': self.switch_threshold,
                'device_statuses': {str(k): v.__dict__ if hasattr(v, '__dict__') else v 
                                  for k, v in self.device_statuses.items()},
                'stats': self.stats
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2, default=str)
            
        except Exception as e:
            print(f"⚠️ 配置保存失败: {e}")
    
    def calculate_device_score(self, device: Dict) -> int:
        """计算设备综合评分"""
        score = 0
        name = device['name'].lower()
        
        # 基础分数
        score += 30
        
        # 品牌评分 - 优化后的评分系统
        if 'hecate' in name:
            if 'g4 pro' in name:
                score += 50  # HECATE G4 Pro最高评分
            else:
                score += 40  # 其他HECATE设备
        elif any(brand in name for brand in ['scarlett', 'apollo', 'rme', 'motu']):
            score += 45  # 专业音频接口
        elif any(brand in name for brand in ['audio-technica', 'shure', 'beyerdynamic']):
            score += 35  # 专业音频品牌
        elif 'realtek' in name:
            score += 20  # Realtek集成声卡
        elif any(brand in name for brand in ['creative', 'sound blaster']):
            score += 25  # Creative声卡
        
        # 采样率评分
        sample_rate = device['default_samplerate']
        if sample_rate >= 192000:
            score += 20
        elif sample_rate >= 96000:
            score += 15
        elif sample_rate >= 48000:
            score += 10
        
        # 通道数评分
        channels = device['max_input_channels']
        if channels >= 8:
            score += 10
        elif channels >= 2:
            score += 5
        
        # 宿主API评分
        try:
            hostapi_name = sd.query_hostapis()[device['hostapi']]['name']
            if 'WASAPI' in hostapi_name:
                score += 15
            elif 'ASIO' in hostapi_name:
                score += 20  # ASIO最佳
            elif 'DirectSound' in hostapi_name:
                score += 10
        except:
            pass
        
        return min(score, 100)
    
    def discover_devices(self) -> List[Dict]:
        """发现所有可用设备"""
        try:
            devices = sd.query_devices()
            input_devices = []
            
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    score = self.calculate_device_score(device)
                    
                    device_info = {
                        'id': i,
                        'name': device['name'],
                        'score': score,
                        'sample_rate': int(device['default_samplerate']),
                        'channels': device['max_input_channels'],
                        'hostapi': device['hostapi']
                    }
                    input_devices.append(device_info)
            
            return sorted(input_devices, key=lambda x: x['score'], reverse=True)
            
        except Exception as e:
            print(f"❌ 设备发现失败: {e}")
            return []
    
    def test_device_performance(self, device_id: int) -> Dict:
        """测试设备性能"""
        try:
            # 快速性能测试
            test_configs = [
                (48000, 64),
                (96000, 32),
                (48000, 128)
            ]
            
            best_latency = float('inf')
            best_config = None
            success_count = 0
            
            for sample_rate, block_size in test_configs:
                try:
                    start_time = time.time()
                    
                    # 创建测试流
                    stream = sd.InputStream(
                        device=device_id,
                        channels=1,
                        samplerate=sample_rate,
                        blocksize=block_size,
                        dtype=np.float32
                    )
                    
                    # 计算理论延迟
                    theoretical_latency = block_size / sample_rate * 1000
                    
                    if theoretical_latency < best_latency:
                        best_latency = theoretical_latency
                        best_config = (sample_rate, block_size)
                    
                    stream.close()
                    success_count += 1
                    
                except Exception:
                    continue
            
            # 计算性能评分
            if success_count > 0:
                reliability = (success_count / len(test_configs)) * 100
                
                if best_latency < 2.0:
                    latency_score = 90
                elif best_latency < 5.0:
                    latency_score = 80
                elif best_latency < 10.0:
                    latency_score = 70
                else:
                    latency_score = 50
                
                return {
                    'success': True,
                    'best_latency': best_latency,
                    'best_config': best_config,
                    'reliability': reliability,
                    'latency_score': latency_score,
                    'performance_score': (reliability + latency_score) / 2
                }
            else:
                return {
                    'success': False,
                    'error': 'All configurations failed'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_device_status(self, device_id: int, device_info: Dict):
        """更新设备状态"""
        current_time = time.time()
        
        if device_id not in self.device_statuses:
            self.device_statuses[device_id] = DeviceStatus(
                device_id=device_id,
                name=device_info['name'],
                is_available=True,
                quality_score=device_info['score'],
                current_latency=0.0,
                sample_rate=device_info['sample_rate'],
                block_size=128,
                error_count=0,
                last_test_time=current_time,
                connection_stability=100.0
            )
        
        status = self.device_statuses[device_id]
        
        # 定期测试设备性能
        if current_time - status.last_test_time > self.device_test_interval:
            performance = self.test_device_performance(device_id)
            
            if performance['success']:
                status.current_latency = performance['best_latency']
                status.connection_stability = min(100.0, status.connection_stability + 2.0)
                status.error_count = max(0, status.error_count - 1)
            else:
                status.error_count += 1
                status.connection_stability = max(0.0, status.connection_stability - 10.0)
            
            status.last_test_time = current_time
    
    def get_best_device(self) -> Optional[Dict]:
        """获取当前最佳设备"""
        devices = self.discover_devices()
        if not devices:
            return None
        
        # 更新所有设备状态
        for device in devices:
            self.update_device_status(device['id'], device)
        
        # 计算综合评分（质量 + 性能 + 稳定性）
        best_device = None
        best_score = 0
        
        for device in devices:
            device_id = device['id']
            if device_id in self.device_statuses:
                status = self.device_statuses[device_id]
                
                # 综合评分计算
                quality_weight = 0.4
                performance_weight = 0.4
                stability_weight = 0.2
                
                composite_score = (
                    device['score'] * quality_weight +
                    (100 - min(status.current_latency * 10, 100)) * performance_weight +
                    status.connection_stability * stability_weight
                )
                
                if composite_score > best_score and status.error_count < 3:
                    best_score = composite_score
                    best_device = device
                    best_device['composite_score'] = composite_score
                    best_device['status'] = status
        
        return best_device
    
    def should_switch_device(self, current_device: Dict, new_device: Dict) -> bool:
        """判断是否应该切换设备"""
        if not self.auto_switch_enabled:
            return False
        
        if not current_device or not new_device:
            return True
        
        # 比较综合评分
        score_difference = new_device.get('composite_score', 0) - current_device.get('composite_score', 0)
        
        # 只有在新设备明显更优时才切换
        return score_difference > self.switch_threshold
    
    def start_monitoring(self, callback: Optional[Callable] = None):
        """开始设备监控"""
        if self.monitoring:
            print("⚠️ 监控已经在运行")
            return
        
        self.callback_function = callback
        self.monitoring = True
        self.stats['start_time'] = time.time()
        
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        print(f"🔄 开始实时设备监控 (间隔: {self.monitor_interval}s)")
    
    def stop_monitoring(self):
        """停止设备监控"""
        self.monitoring = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5.0)
        
        self.stats['uptime'] = time.time() - self.stats['start_time']
        self.save_config()
        
        print("🔄 设备监控已停止")
    
    def _monitoring_loop(self):
        """监控循环"""
        print("🔄 设备监控循环开始...")
        
        while self.monitoring:
            try:
                # 发现当前最佳设备
                best_device = self.get_best_device()
                
                if best_device:
                    # 判断是否需要切换设备
                    if self.should_switch_device(self.current_device, best_device):
                        print(f"🔄 检测到更优设备: {best_device['name']} (评分: {best_device['composite_score']:.1f})")
                        
                        if self.callback_function:
                            try:
                                self.callback_function(best_device)
                                self.current_device = best_device
                                self.stats['total_switches'] += 1
                                print(f"✅ 成功切换到设备: {best_device['name']}")
                            except Exception as e:
                                print(f"❌ 设备切换失败: {e}")
                                self.stats['failed_switches'] += 1
                    
                    # 更新统计信息
                    if 'status' in best_device:
                        self.stats['average_latency'] = best_device['status'].current_latency
                
                time.sleep(self.monitor_interval)
                
            except Exception as e:
                print(f"⚠️ 监控循环错误: {e}")
                time.sleep(self.monitor_interval)
    
    def get_status_report(self) -> Dict:
        """获取状态报告"""
        current_time = time.time()
        uptime = current_time - self.stats['start_time']
        
        report = {
            'monitoring': self.monitoring,
            'current_device': self.current_device,
            'total_devices': len(self.device_statuses),
            'uptime': uptime,
            'stats': self.stats.copy(),
            'top_devices': []
        }
        
        # 添加前5个设备的状态
        devices = self.discover_devices()[:5]
        for device in devices:
            device_id = device['id']
            if device_id in self.device_statuses:
                status = self.device_statuses[device_id]
                report['top_devices'].append({
                    'name': device['name'],
                    'score': device['score'],
                    'latency': status.current_latency,
                    'stability': status.connection_stability,
                    'errors': status.error_count
                })
        
        return report
    
    def print_status_report(self):
        """打印状态报告"""
        report = self.get_status_report()
        
        print("\n" + "=" * 50)
        print("🔄 实时音频设备监控状态报告")
        print("=" * 50)
        print(f"监控状态: {'运行中' if report['monitoring'] else '已停止'}")
        print(f"运行时间: {report['uptime']:.1f}秒")
        print(f"设备总数: {report['total_devices']}")
        print(f"切换次数: {report['stats']['total_switches']}")
        print(f"平均延迟: {report['stats']['average_latency']:.2f}ms")
        
        if report['current_device']:
            print(f"当前设备: {report['current_device']['name']}")
        
        print(f"\n🏆 设备排名:")
        for i, device in enumerate(report['top_devices'], 1):
            print(f"{i}. {device['name']}")
            print(f"   ├─ 评分: {device['score']}/100")
            print(f"   ├─ 延迟: {device['latency']:.2f}ms")
            print(f"   ├─ 稳定性: {device['stability']:.1f}%")
            print(f"   └─ 错误: {device['errors']}次")

# 示例用法
def example_callback(device_info):
    """示例回调函数"""
    print(f"🔄 回调: 切换到设备 {device_info['name']}")

def main():
    """主程序演示"""
    print("🚀 实时音频设备监控器演示")
    
    monitor = RealTimeAudioDeviceMonitor()
    
    # 设置回调函数
    monitor.start_monitoring(example_callback)
    
    try:
        # 运行30秒
        for i in range(30):
            time.sleep(1)
            if i % 10 == 0:
                monitor.print_status_report()
    
    except KeyboardInterrupt:
        print("\n用户中断")
    
    finally:
        monitor.stop_monitoring()
        monitor.print_status_report()

if __name__ == "__main__":
    main()
