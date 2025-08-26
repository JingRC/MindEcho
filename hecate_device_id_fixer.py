#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HECATE G4 Pro 设备ID修复工具
解决设备ID在不同上下文中不匹配的问题

核心问题分析：
- 设备33在InputStream测试中完美工作
- 但在Stream创建时报告Invalid device -9996错误
- 这是sounddevice库中设备ID映射不一致导致的

解决方案：
1. 动态设备ID映射
2. 实时设备状态验证
3. 智能设备ID重新映射
4. 上下文感知的设备选择

作者: GitHub Copilot
日期: 2025-01-06
"""

import sounddevice as sd
import numpy as np
import time
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class HecateDeviceMapper:
    """HECATE设备ID动态映射器"""
    
    def __init__(self):
        self.device_cache = {}
        self.verified_mappings = {}
        self.last_scan_time = 0
        self.scan_interval = 5.0  # 5秒重新扫描一次
        
        print("🔧 HECATE设备映射器初始化")
        self._refresh_device_cache()

    # ——— 兼容主程序接口（integrated_recording_interface 期望的方法） ———
    def verify_hecate_available(self) -> bool:
        """检查是否存在可用于监听的HECATE输入设备（兼容主程序调用）。"""
        try:
            self._refresh_device_cache()
            for info in self.device_cache.values():
                dev = info.get('device_info') or {}
                if dev.get('max_input_channels', 0) > 0:
                    # 至少有一个HECATE输入设备
                    return True
            return False
        except Exception as e:
            print(f"⚠️ verify_hecate_available 失败: {e}")
            return False

    def get_working_hecate_config(self) -> Optional[Dict]:
        """返回一个经过快速验证可用的HECATE配置（兼容主程序调用）。
        优先返回已缓存的 verified_config；否则调用自带搜索验证。
        """
        try:
            # 优先使用近期已验证通过的配置
            self._refresh_device_cache()
            best = None
            for dev_id, info in self.device_cache.items():
                vc = info.get('verified_config')
                if vc:
                    # 简单打分：更小的 blocksize、更高的 samplerate 优先
                    score = (vc.get('samplerate', 0), -vc.get('blocksize', 10**9))
                    if (best is None) or (score > best[0]):
                        best = (score, vc)
            if best is not None:
                return best[1]

            # 无缓存则主动寻找可工作设备
            return self.find_working_hecate_device()
        except Exception as e:
            print(f"⚠️ get_working_hecate_config 失败: {e}")
            return None
    
    def _refresh_device_cache(self):
        """刷新设备缓存"""
        try:
            current_time = time.time()
            
            # 如果距离上次扫描不足间隔时间，直接返回
            if current_time - self.last_scan_time < self.scan_interval:
                return
            
            print(f"🔍 刷新设备缓存...")
            devices = sd.query_devices()
            
            # 清空旧缓存
            self.device_cache = {}
            
            for i, device in enumerate(devices):
                device_name = device.get('name', 'Unknown')
                
                # 检测HECATE设备
                if 'HECATE' in device_name or 'G4 Pro' in device_name:
                    print(f"🎯 发现HECATE设备: {device_name} (ID: {i})")
                    print(f"   └─ API: {device.get('hostapi', 'Unknown')}")
                    print(f"   └─ 输入通道: {device.get('max_input_channels', 0)}")
                    print(f"   └─ 默认采样率: {device.get('default_samplerate', 0)}Hz")
                    
                    # 存储设备信息
                    self.device_cache[i] = {
                        'name': device_name,
                        'device_info': device,
                        'last_verified': None,
                        'verified_config': None
                    }
            
            self.last_scan_time = current_time
            print(f"✅ 设备缓存刷新完成，发现 {len(self.device_cache)} 个HECATE设备")
            
        except Exception as e:
            print(f"❌ 刷新设备缓存失败: {e}")
    
    def get_hecate_devices(self) -> List[Dict]:
        """获取所有HECATE设备"""
        self._refresh_device_cache()
        return [
            {
                'device_id': device_id,
                'name': info['name'],
                'device_info': info['device_info']
            }
            for device_id, info in self.device_cache.items()
        ]
    
    def verify_device_for_monitoring(self, device_id: int) -> Optional[Dict]:
        """验证设备是否可用于监听"""
        try:
            print(f"🧪 验证设备 {device_id} 的监听功能...")
            
            # 获取设备信息
            device_info = sd.query_devices(device_id)
            device_name = device_info.get('name', f'Device_{device_id}')
            
            print(f"   设备名称: {device_name}")
            print(f"   API类型: {device_info.get('hostapi', 'Unknown')}")
            print(f"   输入通道: {device_info.get('max_input_channels', 0)}")
            
            # 检查是否是输入设备
            if device_info.get('max_input_channels', 0) == 0:
                print(f"   ❌ 不是输入设备")
                return None
            
            # 测试原生192kHz配置（HECATE的最佳配置）
            test_configs = [
                {'samplerate': 192000, 'blocksize': 32, 'channels': 1},
                {'samplerate': 192000, 'blocksize': 64, 'channels': 1},
                {'samplerate': 48000, 'blocksize': 128, 'channels': 1},
                {'samplerate': 44100, 'blocksize': 256, 'channels': 1},
            ]
            
            for config in test_configs:
                try:
                    print(f"   🧪 测试配置: {config['samplerate']}Hz/{config['blocksize']}样本")
                    
                    # 创建测试流（仅输入）
                    with sd.InputStream(
                        device=device_id,
                        channels=config['channels'],
                        samplerate=config['samplerate'],
                        blocksize=config['blocksize'],
                        dtype=np.float32
                    ) as test_stream:
                        # 启动流
                        test_stream.start()
                        
                        # 短暂测试
                        time.sleep(0.1)
                        
                        # 检查流状态
                        if test_stream.active:
                            print(f"   ✅ 配置可用！")
                            
                            # 缓存验证结果
                            verified_config = {
                                'device_id': device_id,
                                'device_name': device_name,
                                'samplerate': config['samplerate'],
                                'blocksize': config['blocksize'],
                                'channels': config['channels'],
                                'verified_time': datetime.now().isoformat(),
                                'latency_ms': config['blocksize'] / config['samplerate'] * 1000
                            }
                            
                            if device_id in self.device_cache:
                                self.device_cache[device_id]['verified_config'] = verified_config
                                self.device_cache[device_id]['last_verified'] = time.time()
                            
                            return verified_config
                        else:
                            print(f"   ❌ 流未激活")
                
                except Exception as e:
                    print(f"   ❌ 配置测试失败: {e}")
                    continue
            
            print(f"   ❌ 所有配置都失败")
            return None
            
        except Exception as e:
            print(f"❌ 设备验证失败: {e}")
            return None
    
    def find_working_hecate_device(self) -> Optional[Dict]:
        """找到一个可工作的HECATE设备"""
        print("🎯 搜索可工作的HECATE设备...")
        
        hecate_devices = self.get_hecate_devices()
        
        if not hecate_devices:
            print("❌ 未发现HECATE设备")
            return None
        
        print(f"📋 发现 {len(hecate_devices)} 个HECATE设备")
        
        # 按设备ID优先级排序（根据测试结果，设备33最佳）
        priority_devices = []
        other_devices = []
        
        for device in hecate_devices:
            device_id = device['device_id']
            if device_id == 33:  # 测试中表现最佳的设备
                priority_devices.insert(0, device)
            elif device_id in [1, 13]:  # 其他HECATE设备
                priority_devices.append(device)
            else:
                other_devices.append(device)
        
        # 合并列表（优先级设备在前）
        sorted_devices = priority_devices + other_devices
        
        # 依次测试每个设备
        for device in sorted_devices:
            device_id = device['device_id']
            device_name = device['name']
            
            print(f"\n🔍 测试设备 {device_id}: {device_name}")
            
            verified_config = self.verify_device_for_monitoring(device_id)
            if verified_config:
                print(f"🎉 找到可工作的HECATE设备！")
                print(f"   设备ID: {device_id}")
                print(f"   设备名称: {device_name}")
                print(f"   最佳配置: {verified_config['samplerate']}Hz/{verified_config['blocksize']}样本")
                print(f"   延迟: {verified_config['latency_ms']:.2f}ms")
                return verified_config
        
        print("❌ 没有找到可工作的HECATE设备")
        return None
    
    def create_monitoring_stream(self, config: Dict, callback) -> Optional[sd.Stream]:
        """使用验证过的配置创建监听流"""
        try:
            print(f"🎧 创建监听流...")
            print(f"   设备: {config['device_name']}")
            print(f"   配置: {config['samplerate']}Hz/{config['blocksize']}样本")
            
            # 创建监听流（输入+输出，支持实时监听）
            stream = sd.Stream(
                device=(config['device_id'], None),  # 输入设备，默认输出
                channels=config['channels'],
                samplerate=config['samplerate'],
                blocksize=config['blocksize'],
                dtype=np.float32,
                callback=callback
            )
            
            return stream
            
        except Exception as e:
            print(f"❌ 创建监听流失败: {e}")
            return None


class HecateMonitoringDemo:
    """HECATE监听演示"""
    
    def __init__(self):
        self.device_mapper = HecateDeviceMapper()
        self.current_stream = None
        self.is_monitoring = False
        self.callback_count = 0
        
    def monitoring_callback(self, indata, outdata, frames, time, status):
        """监听回调函数"""
        try:
            self.callback_count += 1
            
            # 状态检查
            if status:
                if self.callback_count <= 5:  # 只显示前几个状态警告
                    print(f"⚠️ 音频状态: {status}")
            
            # 处理音频数据
            if indata is not None and outdata is not None:
                # 获取输入音频
                if indata.shape[1] > 1:
                    # 立体声混合为单声道
                    audio_data = np.mean(indata, axis=1)
                else:
                    audio_data = indata[:, 0]
                
                # 简单的增益控制
                rms = np.sqrt(np.mean(audio_data ** 2))
                if rms > 0.001:  # 有信号时
                    # 自动增益控制
                    target_rms = 0.1
                    gain = min(3.0, target_rms / max(rms, 0.001))
                    audio_data *= gain
                
                # 输出到扬声器
                if outdata.shape[1] == 1:
                    outdata[:, 0] = audio_data
                else:
                    outdata[:, 0] = audio_data
                    outdata[:, 1] = audio_data
            
            # 定期显示状态（每1000次回调显示一次）
            if self.callback_count % 1000 == 0:
                print(f"🎤 监听正常，回调次数: {self.callback_count}")
        
        except Exception as e:
            if self.callback_count <= 3:
                print(f"⚠️ 回调错误: {e}")
    
    def start_monitoring(self) -> bool:
        """启动监听"""
        try:
            print("🚀 启动HECATE监听...")
            
            # 查找可工作的HECATE设备
            working_config = self.device_mapper.find_working_hecate_device()
            
            if not working_config:
                print("❌ 未找到可工作的HECATE设备")
                return False
            
            # 创建监听流
            self.current_stream = self.device_mapper.create_monitoring_stream(
                working_config, 
                self.monitoring_callback
            )
            
            if not self.current_stream:
                print("❌ 创建监听流失败")
                return False
            
            # 启动监听
            self.current_stream.start()
            self.is_monitoring = True
            
            print("✅ HECATE监听启动成功！")
            print("🎤 请说话或播放音频进行测试...")
            
            return True
            
        except Exception as e:
            print(f"❌ 启动监听失败: {e}")
            return False
    
    def stop_monitoring(self):
        """停止监听"""
        try:
            if self.current_stream and self.is_monitoring:
                print("🔄 停止监听...")
                
                self.is_monitoring = False
                self.current_stream.stop()
                self.current_stream.close()
                self.current_stream = None
                
                print(f"✅ 监听已停止，总回调次数: {self.callback_count}")
        
        except Exception as e:
            print(f"❌ 停止监听失败: {e}")
    
    def run_demo(self, duration: int = 10):
        """运行演示"""
        try:
            if self.start_monitoring():
                print(f"\n🎧 监听运行中 ({duration}秒)...")
                
                for i in range(duration):
                    time.sleep(1)
                    if i % 3 == 0:
                        print(f"   ⏱️  {i+1}/{duration}秒, 回调: {self.callback_count}")
                
                self.stop_monitoring()
                print("🎉 演示完成！")
            else:
                print("❌ 演示启动失败")
                
        except KeyboardInterrupt:
            print("\n⏹️ 用户中断")
            self.stop_monitoring()
        except Exception as e:
            print(f"❌ 演示错误: {e}")


def export_working_config():
    """导出可工作的配置供主程序使用"""
    try:
        print("💾 导出HECATE工作配置...")
        
        mapper = HecateDeviceMapper()
        working_config = mapper.find_working_hecate_device()
        
        if working_config:
            # 保存配置文件
            export_data = {
                'timestamp': datetime.now().isoformat(),
                'hecate_working_config': working_config,
                'usage_instructions': {
                    'device_id': working_config['device_id'],
                    'recommended_stream_params': {
                        'device': f"({working_config['device_id']}, None)",  # 输入设备ID, 默认输出
                        'channels': working_config['channels'],
                        'samplerate': working_config['samplerate'], 
                        'blocksize': working_config['blocksize'],
                        'dtype': 'float32'
                    }
                }
            }
            
            config_file = 'hecate_working_config.json'
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ 配置已导出到: {config_file}")
            print(f"🎯 主程序集成代码:")
            print(f"""
# 在integrated_recording_interface.py中使用：
import json

# 加载HECATE配置
with open('hecate_working_config.json', 'r', encoding='utf-8') as f:
    hecate_config = json.load(f)['hecate_working_config']

# 创建监听流
self.monitoring_stream = sd.Stream(
    device=(hecate_config['device_id'], None),
    channels=hecate_config['channels'],
    samplerate=hecate_config['samplerate'],
    blocksize=hecate_config['blocksize'],
    dtype=np.float32,
    callback=self._monitoring_callback
)
""")
            return working_config
        else:
            print("❌ 没有找到可工作的配置")
            return None
            
    except Exception as e:
        print(f"❌ 导出配置失败: {e}")
        return None


def main():
    """主函数"""
    print("🎧 HECATE G4 Pro 设备ID修复工具")
    print("🎯 解决设备ID映射不一致问题")
    print("=" * 50)
    
    try:
        # 显示菜单
        print("\n📋 请选择操作:")
        print("1. 查找并测试HECATE设备")
        print("2. 运行监听演示 (10秒)")
        print("3. 导出工作配置供主程序使用")
        print("4. 全部执行")
        
        choice = input("\n请输入选项 (1-4): ").strip()
        
        if choice == '1':
            mapper = HecateDeviceMapper()
            working_config = mapper.find_working_hecate_device()
            if working_config:
                print("🎉 找到可工作的配置！")
            else:
                print("❌ 未找到可工作的配置")
        
        elif choice == '2':
            demo = HecateMonitoringDemo()
            demo.run_demo(10)
        
        elif choice == '3':
            export_working_config()
        
        elif choice == '4':
            print("🚀 执行完整测试流程...")
            
            # 1. 查找设备
            mapper = HecateDeviceMapper()
            working_config = mapper.find_working_hecate_device()
            
            if working_config:
                # 2. 运行演示
                demo = HecateMonitoringDemo()
                demo.run_demo(5)  # 短时间演示
                
                # 3. 导出配置
                export_working_config()
                
                print("🎉 完整测试流程完成！")
            else:
                print("❌ 未找到可工作的设备，无法继续")
        
        else:
            print("❌ 无效选项")
    
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断")
    except Exception as e:
        print(f"❌ 程序错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
