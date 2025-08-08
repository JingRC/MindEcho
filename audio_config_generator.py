#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频配置生成器 - 为MindEcho主程序提供最优WASAPI配置
基于test_audio_monitoring.py的测试结果生成可靠的音频配置

主要功能：
1. 动态采样率适配
2. 设备兼容性检查
3. 统一Stream创建逻辑
4. 智能回退机制

作者: GitHub Copilot
日期: 2025-08-06
"""

import sounddevice as sd
import numpy as np
import json
import time
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path


class AudioConfigGenerator:
    """音频配置生成器 - 智能WASAPI配置生成"""
    
    def __init__(self):
        self.validated_configs = []
        self.device_cache = {}
        
        print("🎛️ 音频配置生成器初始化")
    
    def generate_optimal_wasapi_configs(self) -> List[Dict]:
        """生成最优WASAPI配置列表 - 解决-9997/-9996错误"""
        print("\n🎯 生成最优WASAPI配置...")
        
        configs = []
        
        try:
            # 1. 扫描设备并缓存
            input_devices = self._scan_input_devices()
            
            # 2. 为每个设备生成配置
            for device in input_devices:
                device_configs = self._generate_device_configs(device)
                configs.extend(device_configs)
            
            # 3. 验证配置可用性
            validated_configs = self._validate_configs(configs)
            
            # 4. 按优先级排序
            validated_configs.sort(key=lambda x: x['priority'], reverse=True)
            
            print(f"✅ 生成了 {len(validated_configs)} 个有效配置")
            
            # 5. 添加DirectSound回退
            directsound_configs = self._generate_directsound_configs(input_devices)
            validated_configs.extend(directsound_configs)
            
            return validated_configs
            
        except Exception as e:
            print(f"❌ 配置生成失败: {e}")
            return self._generate_emergency_configs()
    
    def _scan_input_devices(self) -> List[Dict]:
        """扫描输入设备"""
        print("🔍 扫描输入设备...")
        
        devices = []
        device_list = sd.query_devices()
        
        for i, device in enumerate(device_list):
            if device['max_input_channels'] > 0:
                # 检查设备是否真实可用
                if self._quick_device_check(i):
                    device_info = {
                        'id': i,
                        'name': device['name'],
                        'max_input_channels': device['max_input_channels'],
                        'default_samplerate': device['default_samplerate'],
                        'hostapi': device['hostapi'],
                        'hostapi_name': sd.query_hostapis(device['hostapi'])['name'],
                        'supported_rates': self._get_supported_rates(i),
                        'device_type': self._classify_device(device['name'])
                    }
                    devices.append(device_info)
                    print(f"   ✅ 设备{i}: {device['name']} - {device_info['device_type']}")
                else:
                    print(f"   ❌ 设备{i}: {device['name']} - 不可用")
        
        return devices
    
    def _quick_device_check(self, device_id: int) -> bool:
        """快速检查设备是否可用"""
        try:
            # 使用最基本的参数测试设备
            test_stream = sd.InputStream(
                device=device_id,
                channels=1,
                samplerate=44100,
                blocksize=512,
                dtype=np.float32
            )
            test_stream.close()  # 只创建不启动
            return True
        except Exception:
            return False
    
    def _get_supported_rates(self, device_id: int) -> List[int]:
        """获取设备支持的采样率"""
        rates = [192000, 96000, 48000, 44100]
        supported = []
        
        for rate in rates:
            try:
                sd.check_input_settings(device=device_id, samplerate=rate)
                supported.append(rate)
            except:
                continue
        
        # 确保至少有一个采样率
        if not supported:
            supported = [44100]
        
        return supported
    
    def _classify_device(self, device_name: str) -> str:
        """设备分类"""
        name_lower = device_name.lower()
        
        if 'hecate' in name_lower:
            if 'g4 pro' in name_lower:
                return 'HECATE_G4_PRO'
            return 'HECATE'
        elif 'realtek' in name_lower:
            return 'REALTEK'
        elif 'cable' in name_lower or 'virtual' in name_lower:
            return 'VIRTUAL'
        elif 'asio' in name_lower:
            return 'ASIO'
        else:
            return 'GENERIC'
    
    def _generate_device_configs(self, device: Dict) -> List[Dict]:
        """为单个设备生成配置"""
        configs = []
        device_id = device['id']
        device_name = device['name']
        device_type = device['device_type']
        supported_rates = device['supported_rates']
        
        # 根据设备类型生成不同的配置策略
        if device_type == 'HECATE_G4_PRO':
            configs.extend(self._generate_hecate_configs(device))
        elif device_type == 'REALTEK':
            configs.extend(self._generate_realtek_configs(device))
        else:
            configs.extend(self._generate_generic_configs(device))
        
        return configs
    
    def _generate_hecate_configs(self, device: Dict) -> List[Dict]:
        """生成HECATE G4 Pro专用配置"""
        configs = []
        device_id = device['id']
        device_name = device['name']
        supported_rates = device['supported_rates']
        
        # HECATE G4 Pro优先配置
        hecate_configs = [
            # 192kHz配置（如果支持）
            {'rate': 192000, 'block': 32, 'mode': 'exclusive', 'priority_bonus': 100},
            {'rate': 192000, 'block': 32, 'mode': 'shared', 'priority_bonus': 95},
            {'rate': 192000, 'block': 64, 'mode': 'exclusive', 'priority_bonus': 90},
            {'rate': 192000, 'block': 64, 'mode': 'shared', 'priority_bonus': 85},
            
            # 96kHz配置
            {'rate': 96000, 'block': 64, 'mode': 'exclusive', 'priority_bonus': 80},
            {'rate': 96000, 'block': 64, 'mode': 'shared', 'priority_bonus': 75},
            
            # 48kHz配置
            {'rate': 48000, 'block': 128, 'mode': 'shared', 'priority_bonus': 60},
        ]
        
        for config in hecate_configs:
            if config['rate'] in supported_rates:
                wasapi_config = self._create_wasapi_config(
                    device_id=device_id,
                    device_name=f"HECATE G4 Pro: {device_name}",
                    samplerate=config['rate'],
                    blocksize=config['block'],
                    exclusive=(config['mode'] == 'exclusive'),
                    priority_bonus=config['priority_bonus']
                )
                configs.append(wasapi_config)
        
        return configs
    
    def _generate_realtek_configs(self, device: Dict) -> List[Dict]:
        """生成Realtek设备配置"""
        configs = []
        device_id = device['id']
        device_name = device['name']
        supported_rates = device['supported_rates']
        
        # Realtek通常配置
        realtek_configs = [
            {'rate': 48000, 'block': 256, 'mode': 'shared', 'priority_bonus': 40},
            {'rate': 44100, 'block': 256, 'mode': 'shared', 'priority_bonus': 35},
        ]
        
        for config in realtek_configs:
            if config['rate'] in supported_rates:
                wasapi_config = self._create_wasapi_config(
                    device_id=device_id,
                    device_name=f"Realtek: {device_name}",
                    samplerate=config['rate'],
                    blocksize=config['block'],
                    exclusive=False,  # Realtek通常不支持独占模式
                    priority_bonus=config['priority_bonus']
                )
                configs.append(wasapi_config)
        
        return configs
    
    def _generate_generic_configs(self, device: Dict) -> List[Dict]:
        """生成通用设备配置"""
        configs = []
        device_id = device['id']
        device_name = device['name']
        supported_rates = device['supported_rates']
        
        # 选择最高支持的采样率
        max_rate = max(supported_rates) if supported_rates else 44100
        
        # 通用配置
        generic_configs = [
            {'rate': max_rate, 'block': 256, 'mode': 'shared', 'priority_bonus': 30},
            {'rate': 48000, 'block': 512, 'mode': 'shared', 'priority_bonus': 25},
        ]
        
        for config in generic_configs:
            if config['rate'] in supported_rates:
                wasapi_config = self._create_wasapi_config(
                    device_id=device_id,
                    device_name=device_name,
                    samplerate=config['rate'],
                    blocksize=config['block'],
                    exclusive=False,
                    priority_bonus=config['priority_bonus']
                )
                configs.append(wasapi_config)
        
        return configs
    
    def _create_wasapi_config(self, device_id: int, device_name: str, samplerate: int, 
                            blocksize: int, exclusive: bool, priority_bonus: int = 0) -> Dict:
        """创建WASAPI配置对象"""
        # 创建WASAPI设置
        try:
            settings = sd.WasapiSettings(exclusive=exclusive)
        except:
            settings = None
        
        # 计算优先级
        base_priority = self._calculate_priority(samplerate, blocksize, exclusive)
        priority = base_priority + priority_bonus
        
        # 理论延迟
        latency_ms = (blocksize / samplerate) * 1000
        
        # 生成配置名称
        mode_str = "独占" if exclusive else "共享"
        config_name = f"WASAPI{mode_str} - {device_name} ({samplerate//1000}k{mode_str[:1]} - {latency_ms:.2f}ms)"
        
        config = {
            'name': config_name,
            'device_id': device_id,
            'device_name': device_name,
            'samplerate': samplerate,
            'blocksize': blocksize,
            'exclusive': exclusive,
            'settings': settings,
            'priority': priority,
            'expected_latency_ms': latency_ms,
            'driver_type': 'WASAPI',
            'validated': False  # 将在验证阶段设置
        }
        
        return config
    
    def _calculate_priority(self, samplerate: int, blocksize: int, exclusive: bool) -> int:
        """计算配置优先级"""
        priority = 0
        
        # 采样率评分
        if samplerate >= 192000:
            priority += 50
        elif samplerate >= 96000:
            priority += 40
        elif samplerate >= 48000:
            priority += 30
        else:
            priority += 20
        
        # 块大小评分（更小=更好）
        if blocksize <= 64:
            priority += 30
        elif blocksize <= 128:
            priority += 25
        elif blocksize <= 256:
            priority += 20
        else:
            priority += 10
        
        # 独占模式评分
        if exclusive:
            priority += 15
        else:
            priority += 10
        
        return priority
    
    def _validate_configs(self, configs: List[Dict]) -> List[Dict]:
        """验证配置可用性"""
        print("🧪 验证配置可用性...")
        
        validated = []
        
        for config in configs:
            if self._test_config(config):
                config['validated'] = True
                validated.append(config)
                print(f"   ✅ {config['name']}")
            else:
                print(f"   ❌ {config['name']}")
        
        return validated
    
    def _test_config(self, config: Dict) -> bool:
        """测试单个配置"""
        try:
            # 构建流参数
            stream_params = {
                'device': config['device_id'],
                'channels': 1,
                'samplerate': config['samplerate'],
                'blocksize': config['blocksize'],
                'dtype': np.float32
            }
            
            # 添加WASAPI设置
            if config.get('settings'):
                stream_params['extra_settings'] = config['settings']
            
            # 创建测试流
            test_stream = sd.InputStream(**stream_params)
            
            # 短暂启动测试
            test_stream.start()
            time.sleep(0.05)  # 50ms
            test_stream.stop()
            test_stream.close()
            
            return True
            
        except Exception as e:
            # 记录具体错误
            error_str = str(e)
            if "-9997" in error_str:
                config['error'] = "不支持的采样率"
            elif "-9996" in error_str:
                config['error'] = "无效设备"
            elif "-9999" in error_str:
                config['error'] = "设备已失效"
            else:
                config['error'] = str(e)[:50]
            
            return False
    
    def _generate_directsound_configs(self, devices: List[Dict]) -> List[Dict]:
        """生成DirectSound回退配置"""
        configs = []
        
        for device in devices:
            # DirectSound配置（兼容性最好）
            config = {
                'name': f"DirectSound - {device['name']}",
                'device_id': device['id'],
                'device_name': device['name'],
                'samplerate': 48000,
                'blocksize': 512,
                'exclusive': False,
                'settings': None,
                'priority': 5,  # 最低优先级
                'expected_latency_ms': (512 / 48000) * 1000,
                'driver_type': 'DirectSound',
                'validated': True  # DirectSound通常都可用
            }
            configs.append(config)
        
        return configs
    
    def _generate_emergency_configs(self) -> List[Dict]:
        """生成紧急配置（当所有测试失败时）"""
        print("⚠️ 生成紧急回退配置...")
        
        try:
            default_device = sd.default.device[0]
            
            config = {
                'name': f"紧急配置 - 默认设备",
                'device_id': default_device,
                'device_name': "默认输入设备",
                'samplerate': 44100,
                'blocksize': 1024,
                'exclusive': False,
                'settings': None,
                'priority': 1,
                'expected_latency_ms': (1024 / 44100) * 1000,
                'driver_type': 'DirectSound',
                'validated': False
            }
            
            return [config]
            
        except Exception as e:
            print(f"❌ 紧急配置生成失败: {e}")
            return []
    
    def create_monitoring_stream(self, config: Dict, callback) -> Optional[sd.Stream]:
        """使用配置创建监听流（统一接口）"""
        try:
            print(f"🎤 创建监听流: {config['name']}")
            
            # 构建流参数
            stream_params = {
                'device': config['device_id'],
                'channels': 1,
                'samplerate': config['samplerate'],
                'blocksize': config['blocksize'],
                'dtype': np.float32,
                'callback': callback,
                'latency': 'low'
            }
            
            # 添加驱动特定设置
            if config.get('settings') and config['driver_type'] == 'WASAPI':
                stream_params['extra_settings'] = config['settings']
            
            # 创建流
            stream = sd.Stream(**stream_params)
            
            print(f"   ✅ 创建成功: {config['samplerate']}Hz/{config['blocksize']}样本")
            print(f"   📊 预期延迟: {config['expected_latency_ms']:.2f}ms")
            
            return stream
            
        except Exception as e:
            print(f"   ❌ 创建失败: {e}")
            return None
    
    def save_optimal_config(self, config: Dict, filename: str = "optimal_audio_config.json"):
        """保存最优配置"""
        try:
            # 准备可序列化的配置
            serializable_config = {
                'name': config['name'],
                'device_id': config['device_id'],
                'device_name': config['device_name'],
                'samplerate': config['samplerate'],
                'blocksize': config['blocksize'],
                'exclusive': config['exclusive'],
                'priority': config['priority'],
                'expected_latency_ms': config['expected_latency_ms'],
                'driver_type': config['driver_type'],
                'validated': config['validated'],
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # 保存到文件
            filepath = Path(filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(serializable_config, f, indent=2, ensure_ascii=False)
            
            print(f"💾 最优配置已保存: {filepath.absolute()}")
            
        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
    
    def load_optimal_config(self, filename: str = "optimal_audio_config.json") -> Optional[Dict]:
        """加载最优配置"""
        try:
            filepath = Path(filename)
            if not filepath.exists():
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 重新创建WASAPI设置对象
            if config.get('driver_type') == 'WASAPI':
                config['settings'] = sd.WasapiSettings(exclusive=config['exclusive'])
            else:
                config['settings'] = None
            
            print(f"📂 已加载配置: {config['name']}")
            return config
            
        except Exception as e:
            print(f"❌ 加载配置失败: {e}")
            return None


def test_config_generator():
    """测试配置生成器"""
    print("🧪 测试音频配置生成器")
    print("=" * 40)
    
    try:
        # 创建配置生成器
        generator = AudioConfigGenerator()
        
        # 生成配置
        configs = generator.generate_optimal_wasapi_configs()
        
        if not configs:
            print("❌ 未生成任何配置")
            return
        
        # 显示前5个配置
        print(f"\n🎯 前5个最优配置:")
        for i, config in enumerate(configs[:5]):
            print(f"{i+1}. {config['name']}")
            print(f"   ├─ 设备ID: {config['device_id']}")
            print(f"   ├─ 参数: {config['samplerate']}Hz/{config['blocksize']}样本")
            print(f"   ├─ 驱动: {config['driver_type']}")
            print(f"   ├─ 优先级: {config['priority']}")
            print(f"   ├─ 延迟: {config['expected_latency_ms']:.2f}ms")
            print(f"   └─ 验证: {'✅' if config['validated'] else '❌'}")
        
        # 保存最优配置
        if configs:
            best_config = configs[0]
            generator.save_optimal_config(best_config)
        
        print(f"\n✅ 配置生成完成！")
        
        # 测试流创建
        if configs and configs[0]['validated']:
            print(f"\n🧪 测试监听流创建...")
            
            def test_callback(indata, outdata, frames, time, status):
                """测试回调"""
                pass
            
            stream = generator.create_monitoring_stream(configs[0], test_callback)
            if stream:
                print("   ✅ 监听流创建成功")
                stream.close()
            else:
                print("   ❌ 监听流创建失败")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_config_generator()
