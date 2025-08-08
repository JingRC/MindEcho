#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专用音频监听测试工具 - 解决WASAPI配置失败问题
针对HECATE G4 Pro等专业设备的最优连接测试

主要解决问题：
1. 采样率不匹配 (-99997)
2. 设备ID传递问题 (-9996)
3. 参数不一致性
4. WASAPI模式兼容性

作者: GitHub Copilot
日期: 2025-08-06
"""

import sounddevice as sd
import numpy as np
import time
import traceback
import threading
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import queue
import platform
import subprocess

class AudioDeviceTester:
    """专业音频设备测试器 - 智能设备发现与监听测试"""
    
    def __init__(self):
        self.test_results = {}
        self.optimal_configs = []
        self.current_stream = None
        self.monitoring = False
        self.callback_stats = {'count': 0, 'errors': 0}
        
        # 测试配置
        self.test_sample_rates = [192000, 96000, 48000, 44100]
        self.test_block_sizes = [32, 64, 128, 256, 512]
        self.wasapi_modes = ['shared', 'exclusive']
        
        print("🎧 专业音频设备测试器初始化完成")
        print("📊 支持WASAPI/DirectSound/ASIO驱动测试")
    
    def get_system_info(self):
        """获取系统音频信息"""
        print("\n🖥️ 系统音频环境检查")
        print("=" * 50)
        
        # 操作系统信息
        os_info = platform.platform()
        print(f"操作系统: {os_info}")
        
        # PortAudio版本
        try:
            print(f"PortAudio版本: {sd.get_portaudio_version()}")
        except:
            print("PortAudio版本: 未知")
        
        # 默认设备
        try:
            default_input = sd.default.device[0]
            default_output = sd.default.device[1]
            print(f"默认输入设备: {default_input}")
            print(f"默认输出设备: {default_output}")
        except Exception as e:
            print(f"获取默认设备失败: {e}")
        
        return {
            'os': os_info,
            'portaudio': sd.get_portaudio_version(),
            'default_input': sd.default.device[0] if hasattr(sd.default, 'device') else None,
            'default_output': sd.default.device[1] if hasattr(sd.default, 'device') else None
        }
    
    def scan_all_devices(self) -> List[Dict]:
        """扫描所有可用音频设备"""
        print("\n🔍 扫描所有音频设备...")
        
        devices = []
        device_list = sd.query_devices()
        
        for i, device in enumerate(device_list):
            if device['max_input_channels'] > 0:  # 只关注输入设备
                device_info = {
                    'id': i,
                    'name': device['name'],
                    'max_input_channels': device['max_input_channels'],
                    'max_output_channels': device['max_output_channels'],
                    'default_samplerate': device['default_samplerate'],
                    'hostapi': device['hostapi'],
                    'hostapi_name': sd.query_hostapis(device['hostapi'])['name']
                }
                devices.append(device_info)
                
                # 分类设备类型
                device_type = "🎤 通用"
                if 'hecate' in device['name'].lower():
                    device_type = "🎧 HECATE"
                elif 'realtek' in device['name'].lower():
                    device_type = "🔊 Realtek"
                elif 'cable' in device['name'].lower() or 'virtual' in device['name'].lower():
                    device_type = "📡 虚拟"
                
                print(f"   {device_type} 设备{i}: {device['name']}")
                print(f"      ├─ 输入通道: {device['max_input_channels']}")
                print(f"      ├─ 输出通道: {device['max_output_channels']}")
                print(f"      ├─ 默认采样率: {device['default_samplerate']}Hz")
                print(f"      └─ 驱动: {sd.query_hostapis(device['hostapi'])['name']}")
        
        print(f"\n✅ 发现 {len(devices)} 个输入设备")
        return devices
    
    def check_sample_rate_support(self, device_id: int, device_name: str) -> Dict:
        """检查设备支持的采样率"""
        print(f"\n🧪 测试设备{device_id}采样率支持: {device_name}")
        
        supported_rates = []
        rate_test_results = {}
        
        for rate in self.test_sample_rates:
            try:
                # 使用sounddevice的check_input_settings进行测试
                sd.check_input_settings(device=device_id, samplerate=rate)
                supported_rates.append(rate)
                rate_test_results[rate] = True
                print(f"   ✅ {rate}Hz - 支持")
                
            except Exception as e:
                rate_test_results[rate] = False
                error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
                print(f"   ❌ {rate}Hz - 不支持 ({error_msg})")
        
        if not supported_rates:
            print("   ⚠️ 警告：设备不支持任何测试采样率")
            
        return {
            'supported_rates': supported_rates,
            'max_rate': max(supported_rates) if supported_rates else 44100,
            'rate_details': rate_test_results
        }
    
    def test_wasapi_configurations(self, device_id: int, device_name: str, supported_rates: List[int]) -> List[Dict]:
        """测试WASAPI配置组合"""
        print(f"\n⚙️ 测试WASAPI配置: 设备{device_id}")
        
        working_configs = []
        
        # 只测试设备支持的采样率
        test_rates = [rate for rate in supported_rates if rate in self.test_sample_rates]
        if not test_rates:
            test_rates = [44100]  # 兜底采样率
            
        for rate in test_rates:
            for block_size in self.test_block_sizes:
                for mode in self.wasapi_modes:
                    try:
                        # 创建WASAPI设置
                        if mode == 'exclusive':
                            settings = sd.WasapiSettings(exclusive=True)
                        else:
                            settings = sd.WasapiSettings(exclusive=False)
                        
                        # 测试流创建
                        print(f"   🧪 测试 {rate}Hz/{block_size}样本/{mode}模式...", end='')
                        
                        # 创建测试流
                        test_stream = sd.InputStream(
                            device=device_id,
                            channels=1,
                            samplerate=rate,
                            blocksize=block_size,
                            dtype=np.float32,
                            extra_settings=settings
                        )
                        
                        # 短暂启动测试
                        test_stream.start()
                        time.sleep(0.1)  # 100ms测试
                        test_stream.stop()
                        test_stream.close()
                        
                        # 计算理论延迟
                        theoretical_latency = (block_size / rate) * 1000
                        
                        config = {
                            'device_id': device_id,
                            'device_name': device_name,
                            'samplerate': rate,
                            'blocksize': block_size,
                            'mode': mode,
                            'settings': settings,
                            'theoretical_latency_ms': theoretical_latency,
                            'priority': self._calculate_config_priority(rate, block_size, mode)
                        }
                        
                        working_configs.append(config)
                        print(f" ✅ (延迟: {theoretical_latency:.2f}ms)")
                        
                    except Exception as e:
                        error_code = str(e)
                        if "Invalid sample rate" in error_code or "-9997" in error_code:
                            print(" ❌ 不支持此采样率")
                        elif "Invalid device" in error_code or "-9996" in error_code:
                            print(" ❌ 设备无效")
                        elif "exclusive" in error_code.lower():
                            print(" ❌ 独占模式不可用")
                        else:
                            print(f" ❌ {str(e)[:30]}...")
                        continue
        
        # 按优先级排序
        working_configs.sort(key=lambda x: x['priority'], reverse=True)
        
        print(f"   📊 发现 {len(working_configs)} 个可用WASAPI配置")
        return working_configs
    
    def _calculate_config_priority(self, rate: int, block_size: int, mode: str) -> int:
        """计算配置优先级分数"""
        score = 0
        
        # 采样率评分 (更高=更好)
        if rate >= 192000:
            score += 50
        elif rate >= 96000:
            score += 40
        elif rate >= 48000:
            score += 30
        else:
            score += 20
        
        # 块大小评分 (更小=更好，低延迟)
        if block_size <= 64:
            score += 30
        elif block_size <= 128:
            score += 25
        elif block_size <= 256:
            score += 20
        else:
            score += 10
        
        # 模式评分 (独占模式通常延迟更低)
        if mode == 'exclusive':
            score += 20
        else:
            score += 15
        
        return score
    
    def test_directsound_fallback(self, device_id: int, device_name: str) -> Dict:
        """测试DirectSound回退模式"""
        print(f"\n🔄 测试DirectSound回退: 设备{device_id}")
        
        try:
            # DirectSound配置 (不使用extra_settings)
            test_stream = sd.InputStream(
                device=device_id,
                channels=1,
                samplerate=48000,
                blocksize=256,
                dtype=np.float32
                # DirectSound不需要extra_settings
            )
            
            test_stream.start()
            time.sleep(0.1)
            test_stream.stop()
            test_stream.close()
            
            config = {
                'device_id': device_id,
                'device_name': device_name,
                'samplerate': 48000,
                'blocksize': 256,
                'mode': 'directsound',
                'settings': None,
                'theoretical_latency_ms': (256 / 48000) * 1000,
                'priority': 10  # 最低优先级
            }
            
            print("   ✅ DirectSound模式可用")
            return config
            
        except Exception as e:
            print(f"   ❌ DirectSound模式失败: {e}")
            return None
    
    def find_optimal_devices(self, devices: List[Dict]) -> List[Dict]:
        """找到最优设备配置"""
        print("\n🎯 寻找最优设备配置...")
        
        all_configs = []
        
        for device in devices:
            device_id = device['id']
            device_name = device['name']
            
            print(f"\n📍 测试设备: {device_name}")
            
            # 1. 检查采样率支持
            rate_info = self.check_sample_rate_support(device_id, device_name)
            supported_rates = rate_info['supported_rates']
            
            if not supported_rates:
                print("   ⚠️ 跳过：无可用采样率")
                continue
            
            # 2. 测试WASAPI配置
            wasapi_configs = self.test_wasapi_configurations(device_id, device_name, supported_rates)
            all_configs.extend(wasapi_configs)
            
            # 3. 测试DirectSound回退
            directsound_config = self.test_directsound_fallback(device_id, device_name)
            if directsound_config:
                all_configs.append(directsound_config)
        
        # 按优先级排序所有配置
        all_configs.sort(key=lambda x: x['priority'], reverse=True)
        
        print(f"\n🏆 找到 {len(all_configs)} 个可用配置")
        return all_configs
    
    def test_monitoring_callback(self, config: Dict, duration: float = 5.0) -> Dict:
        """测试监听回调功能"""
        print(f"\n🎤 测试监听功能: {config['device_name']} @ {config['samplerate']}Hz")
        
        # 重置统计
        self.callback_stats = {'count': 0, 'errors': 0, 'max_level': 0.0, 'avg_level': 0.0}
        level_history = []
        start_time = time.time()
        
        def monitoring_callback(indata, outdata, frames, time_info, status):
            """监听回调函数"""
            try:
                self.callback_stats['count'] += 1
                
                # 状态检查
                if status:
                    self.callback_stats['errors'] += 1
                    print(f"⚠️ 回调状态: {status}")
                
                # 音频级别计算
                if indata is not None and len(indata) > 0:
                    # 处理单声道/立体声
                    if len(indata.shape) > 1 and indata.shape[1] > 1:
                        audio_data = np.mean(indata, axis=1)  # 立体声混合
                    else:
                        audio_data = indata.flatten()
                    
                    level = np.sqrt(np.mean(audio_data ** 2))  # RMS
                    level_history.append(level)
                    
                    if level > self.callback_stats['max_level']:
                        self.callback_stats['max_level'] = level
                
                # 如果有输出数据，进行监听（可选）
                if outdata is not None:
                    if indata is not None:
                        # 简单的监听功能
                        outdata[:] = indata
                    else:
                        outdata.fill(0)
                
            except Exception as e:
                self.callback_stats['errors'] += 1
                print(f"⚠️ 回调错误: {e}")
        
        try:
            # 根据配置创建流
            stream_params = {
                'device': config['device_id'],
                'channels': 1,
                'samplerate': config['samplerate'],
                'blocksize': config['blocksize'],
                'dtype': np.float32,
                'callback': monitoring_callback
            }
            
            # 添加WASAPI设置
            if config.get('settings'):
                stream_params['extra_settings'] = config['settings']
            
            # 创建并启动监听流
            with sd.Stream(**stream_params):
                print(f"   🔊 监听中... ({duration}秒)")
                print("   💡 请说话或播放音频进行测试")
                
                time.sleep(duration)
                
            # 计算平均音频级别
            if level_history:
                self.callback_stats['avg_level'] = np.mean(level_history)
            
            # 计算实际回调频率
            actual_duration = time.time() - start_time
            expected_callbacks = int((config['samplerate'] / config['blocksize']) * actual_duration)
            callback_ratio = self.callback_stats['count'] / max(expected_callbacks, 1)
            
            test_result = {
                'success': True,
                'callback_count': self.callback_stats['count'],
                'error_count': self.callback_stats['errors'],
                'max_audio_level': self.callback_stats['max_level'],
                'avg_audio_level': self.callback_stats['avg_level'],
                'callback_ratio': callback_ratio,
                'actual_duration': actual_duration,
                'theoretical_latency_ms': config['theoretical_latency_ms']
            }
            
            print(f"   ✅ 测试完成:")
            print(f"      ├─ 回调次数: {self.callback_stats['count']}")
            print(f"      ├─ 错误次数: {self.callback_stats['errors']}")
            print(f"      ├─ 最大音频级别: {self.callback_stats['max_level']:.4f}")
            print(f"      ├─ 平均音频级别: {self.callback_stats['avg_level']:.4f}")
            print(f"      ├─ 回调效率: {callback_ratio:.1%}")
            print(f"      └─ 理论延迟: {config['theoretical_latency_ms']:.2f}ms")
            
            return test_result
            
        except Exception as e:
            error_result = {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }
            
            print(f"   ❌ 监听测试失败: {e}")
            return error_result
    
    def run_comprehensive_test(self) -> Dict:
        """运行综合测试"""
        print("🚀 启动综合音频设备测试")
        print("=" * 60)
        
        test_results = {
            'system_info': self.get_system_info(),
            'devices': [],
            'optimal_configs': [],
            'test_timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 1. 扫描设备
        devices = self.scan_all_devices()
        test_results['devices'] = devices
        
        if not devices:
            print("❌ 未发现任何输入设备")
            return test_results
        
        # 2. 找到最优配置
        optimal_configs = self.find_optimal_devices(devices)
        test_results['optimal_configs'] = optimal_configs
        
        if not optimal_configs:
            print("❌ 未找到任何可用配置")
            return test_results
        
        # 3. 测试前几个最优配置的监听功能
        print("\n🎤 测试最优配置的监听功能")
        print("-" * 40)
        
        tested_configs = []
        for i, config in enumerate(optimal_configs[:3]):  # 只测试前3个最优配置
            print(f"\n第{i+1}个配置测试:")
            print(f"设备: {config['device_name']}")
            print(f"参数: {config['samplerate']}Hz/{config['blocksize']}样本/{config['mode']}")
            
            monitoring_result = self.test_monitoring_callback(config, duration=3.0)
            config['monitoring_test'] = monitoring_result
            tested_configs.append(config)
        
        test_results['tested_configs'] = tested_configs
        
        # 4. 推荐最佳配置
        best_config = self._select_best_config(tested_configs)
        if best_config:
            test_results['recommended_config'] = best_config
            print(f"\n🎯 推荐最佳配置:")
            print(f"   设备: {best_config['device_name']} (ID: {best_config['device_id']})")
            print(f"   配置: {best_config['samplerate']}Hz/{best_config['blocksize']}样本")
            print(f"   模式: {best_config['mode']}")
            print(f"   延迟: {best_config['theoretical_latency_ms']:.2f}ms")
            if 'monitoring_test' in best_config and best_config['monitoring_test']['success']:
                print(f"   监听测试: ✅ 成功 (效率: {best_config['monitoring_test']['callback_ratio']:.1%})")
        
        return test_results
    
    def _select_best_config(self, tested_configs: List[Dict]) -> Optional[Dict]:
        """选择最佳配置"""
        if not tested_configs:
            return None
        
        # 过滤成功的配置
        successful_configs = [c for c in tested_configs 
                            if c.get('monitoring_test', {}).get('success', False)]
        
        if not successful_configs:
            return None
        
        # 综合评分
        def calculate_score(config):
            score = config['priority']  # 基础优先级
            
            # 监听测试加分
            monitoring = config.get('monitoring_test', {})
            if monitoring.get('success'):
                score += 100
                # 回调效率加分
                callback_ratio = monitoring.get('callback_ratio', 0)
                if callback_ratio > 0.95:
                    score += 50
                elif callback_ratio > 0.8:
                    score += 30
                else:
                    score += 10
                
                # 错误率扣分
                error_count = monitoring.get('error_count', 0)
                score -= error_count * 10
            
            return score
        
        # 选择得分最高的配置
        best_config = max(successful_configs, key=calculate_score)
        return best_config
    
    def save_test_results(self, results: Dict, filename: str = None):
        """保存测试结果"""
        if filename is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f"audio_test_results_{timestamp}.json"
        
        filepath = Path(filename)
        
        # 序列化处理 (sounddevice设置对象无法直接序列化)
        serializable_results = self._make_serializable(results)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(serializable_results, f, indent=2, ensure_ascii=False)
            
            print(f"\n💾 测试结果已保存到: {filepath.absolute()}")
            
        except Exception as e:
            print(f"❌ 保存测试结果失败: {e}")
    
    def _make_serializable(self, obj):
        """使对象可序列化"""
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            return str(obj)  # 对象转字符串
        else:
            return obj
    
    def test_specific_device(self, device_id: int, verbose: bool = True):
        """测试特定设备的详细信息"""
        try:
            device_info = sd.query_devices(device_id)
            device_name = device_info['name']
            
            if verbose:
                print(f"\n🔍 详细测试设备{device_id}: {device_name}")
                print("-" * 50)
            
            # 基本信息
            if verbose:
                print(f"基本信息:")
                print(f"  └─ 输入通道: {device_info['max_input_channels']}")
                print(f"  └─ 输出通道: {device_info['max_output_channels']}")
                print(f"  └─ 默认采样率: {device_info['default_samplerate']}Hz")
                print(f"  └─ 驱动API: {sd.query_hostapis(device_info['hostapi'])['name']}")
            
            # 采样率测试
            rate_info = self.check_sample_rate_support(device_id, device_name)
            
            # 配置测试
            configs = self.test_wasapi_configurations(device_id, device_name, rate_info['supported_rates'])
            
            # DirectSound测试
            ds_config = self.test_directsound_fallback(device_id, device_name)
            if ds_config:
                configs.append(ds_config)
            
            return {
                'device_info': device_info,
                'rate_info': rate_info,
                'configs': configs
            }
            
        except Exception as e:
            print(f"❌ 测试设备{device_id}失败: {e}")
            return None


def main():
    """主测试程序"""
    print("🎵 MindEcho 专业音频设备测试工具")
    print("🎯 专门解决WASAPI配置失败问题")
    print("📅 版本: 2025-08-06")
    print("=" * 60)
    
    try:
        # 创建测试器
        tester = AudioDeviceTester()
        
        # 运行综合测试
        results = tester.run_comprehensive_test()
        
        # 保存结果
        tester.save_test_results(results)
        
        # 总结
        print("\n📊 测试总结")
        print("=" * 30)
        print(f"发现设备: {len(results.get('devices', []))} 个")
        print(f"可用配置: {len(results.get('optimal_configs', []))} 个")
        
        if 'recommended_config' in results:
            rec = results['recommended_config']
            print(f"\n🎯 建议配置:")
            print(f"设备名称: {rec['device_name']}")
            print(f"设备ID: {rec['device_id']}")
            print(f"采样率: {rec['samplerate']}Hz")
            print(f"块大小: {rec['blocksize']}样本")
            print(f"模式: {rec['mode']}")
            print(f"理论延迟: {rec['theoretical_latency_ms']:.2f}ms")
            
            # 生成集成代码
            print(f"\n📝 集成代码示例:")
            print(f"```python")
            print(f"# 最优配置参数")
            print(f"OPTIMAL_CONFIG = {{")
            print(f"    'device_id': {rec['device_id']},")
            print(f"    'samplerate': {rec['samplerate']},")
            print(f"    'blocksize': {rec['blocksize']},")
            print(f"    'mode': '{rec['mode']}'")
            print(f"}}")
            print(f"```")
        else:
            print("\n⚠️ 未找到可用的最佳配置")
        
        print(f"\n✅ 测试完成！")
        
        # 特定HECATE设备测试
        print(f"\n🎧 HECATE设备专项测试")
        print("-" * 30)
        hecate_found = False
        for device in results.get('devices', []):
            if 'hecate' in device['name'].lower():
                hecate_found = True
                print(f"发现HECATE设备: {device['name']} (ID: {device['id']})")
                tester.test_specific_device(device['id'], verbose=True)
        
        if not hecate_found:
            print("未发现HECATE设备")
        
    except KeyboardInterrupt:
        print("\n\n⏹️ 用户中断测试")
    except Exception as e:
        print(f"\n❌ 测试程序出错: {e}")
        traceback.print_exc()
    
    print("\n👋 测试结束，按Enter键退出...")
    input()


if __name__ == "__main__":
    main()
