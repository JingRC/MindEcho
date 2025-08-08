#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化后的监听系统集成示例
展示如何将测试结果集成到MindEcho主程序中

基于测试结果的关键改进：
1. 动态采样率适配
2. 统一Stream创建逻辑  
3. 智能设备验证
4. 优化的回退机制

作者: GitHub Copilot
日期: 2025-08-06
"""

import sounddevice as sd
import numpy as np
import time
import threading
from typing import Dict, List, Optional, Callable
from audio_config_generator import AudioConfigGenerator


class OptimizedAudioMonitor:
    """优化的音频监听器 - 解决WASAPI配置问题的完整解决方案"""
    
    def __init__(self):
        self.config_generator = AudioConfigGenerator()
        self.current_config = None
        self.current_stream = None
        self.is_monitoring = False
        self.callback_stats = {'count': 0, 'errors': 0}
        
        # 音频处理参数
        self.channels = 1
        self.monitoring_callback = None
        
        print("🎧 优化音频监听器初始化完成")
    
    def start_optimized_monitoring(self, audio_callback: Callable = None) -> bool:
        """启动优化的监听功能"""
        print("\n🚀 启动优化监听模式...")
        
        try:
            # 1. 生成最优配置列表
            optimal_configs = self.config_generator.generate_optimal_wasapi_configs()
            
            if not optimal_configs:
                print("❌ 未找到任何可用配置")
                return False
            
            # 2. 设置默认回调
            if audio_callback is None:
                audio_callback = self._default_monitoring_callback
            
            self.monitoring_callback = audio_callback
            
            # 3. 按优先级尝试配置
            for i, config in enumerate(optimal_configs):
                print(f"\n🎯 尝试配置 {i+1}/{len(optimal_configs)}: {config['name']}")
                
                if self._try_start_monitoring_with_config(config):
                    self.current_config = config
                    self.is_monitoring = True
                    
                    print(f"✅ 监听启动成功!")
                    print(f"   📊 设备: {config['device_name']}")
                    print(f"   📊 参数: {config['samplerate']}Hz/{config['blocksize']}样本")
                    print(f"   📊 驱动: {config['driver_type']}")
                    print(f"   📊 预期延迟: {config['expected_latency_ms']:.2f}ms")
                    
                    # 保存成功的配置
                    self.config_generator.save_optimal_config(config)
                    return True
                else:
                    print(f"❌ 配置失败，尝试下一个...")
                    continue
            
            print("❌ 所有配置都失败")
            return False
            
        except Exception as e:
            print(f"❌ 启动监听失败: {e}")
            return False
    
    def _try_start_monitoring_with_config(self, config: Dict) -> bool:
        """尝试用指定配置启动监听"""
        try:
            # 创建监听流
            stream = self.config_generator.create_monitoring_stream(
                config=config,
                callback=self._create_stream_callback()
            )
            
            if stream is None:
                return False
            
            # 启动流
            stream.start()
            
            # 短暂测试
            time.sleep(0.2)
            
            # 检查是否有致命错误
            if self.callback_stats['errors'] > 10:  # 允许少量初始错误
                stream.stop()
                stream.close()
                return False
            
            # 保存流引用
            self.current_stream = stream
            return True
            
        except Exception as e:
            print(f"   配置启动错误: {e}")
            return False
    
    def _create_stream_callback(self):
        """创建流回调函数"""
        def stream_callback(indata, outdata, frames, time, status):
            """优化的流回调"""
            try:
                self.callback_stats['count'] += 1
                
                # 状态检查
                if status:
                    self.callback_stats['errors'] += 1
                    if self.callback_stats['count'] % 100 == 0:  # 减少错误输出频率
                        print(f"⚠️ 音频状态: {status}")
                
                # 处理音频数据
                if self.monitoring_callback:
                    self.monitoring_callback(indata, outdata, frames, time, status)
                
            except Exception as e:
                self.callback_stats['errors'] += 1
                if self.callback_stats['errors'] <= 5:  # 只显示前几个错误
                    print(f"⚠️ 回调错误: {e}")
        
        return stream_callback
    
    def _default_monitoring_callback(self, indata, outdata, frames, time, status):
        """默认监听回调 - 简单的音频直通"""
        try:
            if indata is not None and outdata is not None:
                # 处理单声道/立体声
                if self.channels == 1 and indata.shape[1] > 1:
                    # 立体声混合到单声道
                    audio_data = np.mean(indata, axis=1)
                    outdata[:, 0] = audio_data
                    if outdata.shape[1] > 1:
                        outdata[:, 1] = audio_data  # 复制到右声道
                else:
                    # 直接复制
                    outdata[:] = indata
                
                # 简单的音量控制（可选）
                volume_factor = 1.0  # 可调节
                outdata *= volume_factor
            
        except Exception as e:
            if hasattr(self, '_callback_error_count'):
                self._callback_error_count += 1
            else:
                self._callback_error_count = 1
                
            if self._callback_error_count <= 3:
                print(f"⚠️ 默认回调错误: {e}")
    
    def stop_monitoring(self):
        """停止监听"""
        try:
            if self.current_stream and self.is_monitoring:
                print("🔄 正在停止监听...")
                
                self.is_monitoring = False
                self.current_stream.stop()
                self.current_stream.close()
                self.current_stream = None
                
                # 显示统计信息
                if self.callback_stats['count'] > 0:
                    error_rate = (self.callback_stats['errors'] / self.callback_stats['count']) * 100
                    print(f"📊 监听统计:")
                    print(f"   ├─ 总回调: {self.callback_stats['count']}")
                    print(f"   ├─ 错误数: {self.callback_stats['errors']}")
                    print(f"   └─ 错误率: {error_rate:.2f}%")
                
                print("✅ 监听已停止")
                
        except Exception as e:
            print(f"❌ 停止监听错误: {e}")
    
    def get_monitoring_status(self) -> Dict:
        """获取监听状态"""
        return {
            'is_monitoring': self.is_monitoring,
            'current_config': self.current_config,
            'callback_count': self.callback_stats['count'],
            'error_count': self.callback_stats['errors'],
            'error_rate': (self.callback_stats['errors'] / max(self.callback_stats['count'], 1)) * 100
        }
    
    def set_custom_callback(self, callback: Callable):
        """设置自定义回调函数"""
        self.monitoring_callback = callback
        print("✅ 已设置自定义回调函数")
    
    def get_available_configs(self) -> List[Dict]:
        """获取可用配置列表"""
        return self.config_generator.generate_optimal_wasapi_configs()
    
    def switch_to_config(self, config: Dict) -> bool:
        """切换到指定配置"""
        try:
            # 停止当前监听
            if self.is_monitoring:
                self.stop_monitoring()
            
            # 使用新配置启动
            if self._try_start_monitoring_with_config(config):
                self.current_config = config
                self.is_monitoring = True
                print(f"✅ 已切换到: {config['name']}")
                return True
            else:
                print(f"❌ 切换失败: {config['name']}")
                return False
                
        except Exception as e:
            print(f"❌ 配置切换错误: {e}")
            return False


def demo_optimized_monitoring():
    """演示优化监听功能"""
    print("🎵 MindEcho优化监听系统演示")
    print("🎯 解决WASAPI配置失败问题")
    print("=" * 50)
    
    try:
        # 创建优化监听器
        monitor = OptimizedAudioMonitor()
        
        # 自定义音频回调示例
        def enhanced_callback(indata, outdata, frames, time, status):
            """增强的音频回调"""
            try:
                # 获取音频数据
                if indata is not None:
                    # 处理单声道
                    if indata.shape[1] > 1:
                        audio_data = np.mean(indata, axis=1)
                    else:
                        audio_data = indata[:, 0]
                    
                    # 简单的音量增强
                    rms = np.sqrt(np.mean(audio_data ** 2))
                    if rms > 0.01:  # 有声音时
                        enhanced_gain = min(2.0, 0.1 / max(rms, 0.001))
                        audio_data *= enhanced_gain
                    
                    # 输出到扬声器/耳机
                    if outdata is not None:
                        if outdata.shape[1] == 1:
                            outdata[:, 0] = audio_data
                        else:
                            outdata[:, 0] = audio_data
                            outdata[:, 1] = audio_data
            
            except Exception as e:
                print(f"回调错误: {e}")
        
        # 设置自定义回调
        monitor.set_custom_callback(enhanced_callback)
        
        # 启动监听
        if monitor.start_optimized_monitoring():
            print("\n✅ 监听启动成功！")
            
            # 显示当前配置
            status = monitor.get_monitoring_status()
            if status['current_config']:
                config = status['current_config']
                print(f"📊 当前配置:")
                print(f"   ├─ 设备: {config['device_name']}")
                print(f"   ├─ 采样率: {config['samplerate']}Hz")
                print(f"   ├─ 块大小: {config['blocksize']}样本")
                print(f"   └─ 延迟: {config['expected_latency_ms']:.2f}ms")
            
            # 运行监听
            print(f"\n🎤 监听运行中... (10秒测试)")
            print("💡 请说话或播放音频进行测试")
            
            for i in range(10):
                time.sleep(1)
                status = monitor.get_monitoring_status()
                if i % 3 == 0:  # 每3秒显示一次状态
                    print(f"   📊 回调: {status['callback_count']}, 错误: {status['error_count']}")
            
            # 停止监听
            monitor.stop_monitoring()
            
        else:
            print("❌ 监听启动失败")
            
            # 显示可用配置
            configs = monitor.get_available_configs()
            print(f"\n📋 可用配置 ({len(configs)}个):")
            for i, config in enumerate(configs[:5]):
                validation = "✅" if config.get('validated', False) else "❌"
                print(f"   {i+1}. {validation} {config['name']}")
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断")
        if 'monitor' in locals():
            monitor.stop_monitoring()
    except Exception as e:
        print(f"❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()


def generate_integration_code():
    """生成主程序集成代码"""
    print("\n📝 生成主程序集成代码")
    print("=" * 40)
    
    integration_code = '''
# 集成到 integrated_recording_interface.py 的代码示例

class IntegratedAudioProcessor(QThread):
    """集成优化后的音频处理器"""
    
    def __init__(self):
        super().__init__()
        # ... 原有初始化代码 ...
        
        # 添加优化的配置生成器
        self.config_generator = AudioConfigGenerator()
        self.optimal_configs = []
        
    def start_unified_monitoring(self):
        """优化的统一监听功能"""
        try:
            print("🎧 正在启动优化监听模式...")
            
            # 1. 生成最优配置（替换原有逻辑）
            self.optimal_configs = self.config_generator.generate_optimal_wasapi_configs()
            
            if not self.optimal_configs:
                print("❌ 未找到可用配置，使用紧急回退")
                return self._start_emergency_monitoring()
            
            # 2. 按优先级尝试配置
            for i, config in enumerate(self.optimal_configs):
                print(f"🎯 尝试配置 {i+1}: {config['name']}")
                
                if self._try_create_stream_with_config(config):
                    self._selected_device_config = config
                    print(f"✅ 成功使用: {config['name']}")
                    self.status_updated.emit("监听已启动")
                    return True
                else:
                    print(f"❌ 配置失败，尝试下一个...")
                    continue
            
            # 3. 所有配置失败，使用紧急模式
            print("⚠️ 所有优化配置失败，使用紧急模式")
            return self._start_emergency_monitoring()
            
        except Exception as e:
            print(f"❌ 优化监听启动失败: {e}")
            return False
    
    def _try_create_stream_with_config(self, config: Dict) -> bool:
        """使用配置创建音频流"""
        try:
            # 使用配置生成器的统一接口
            self.monitoring_stream = self.config_generator.create_monitoring_stream(
                config=config,
                callback=self._professional_monitoring_callback
            )
            
            if self.monitoring_stream is None:
                return False
            
            # 启动流并测试
            self.monitoring_stream.start()
            time.sleep(0.1)  # 短暂测试
            
            return True
            
        except Exception as e:
            print(f"   流创建失败: {e}")
            if hasattr(self, 'monitoring_stream') and self.monitoring_stream:
                try:
                    self.monitoring_stream.close()
                except:
                    pass
                self.monitoring_stream = None
            return False
    
    def _professional_monitoring_callback(self, indata, outdata, frames, time_info, status):
        """专业级监听回调 - 集成原有逻辑"""
        try:
            # ... 原有回调逻辑 ...
            # 可以直接使用原有的专业监听回调代码
            # 主要改进是配置生成和Stream创建部分
            
        except Exception as e:
            print(f"⚠️ 监听回调错误: {e}")
    
    def _start_emergency_monitoring(self):
        """紧急监听模式"""
        try:
            # 使用最基本的DirectSound配置
            self.monitoring_stream = sd.Stream(
                channels=self.channels,
                samplerate=44100,
                blocksize=1024,
                callback=self._professional_monitoring_callback,
                dtype=np.float32
            )
            
            self.monitoring_stream.start()
            print("🔄 紧急监听模式启动成功")
            return True
            
        except Exception as e:
            print(f"❌ 紧急监听也失败: {e}")
            return False

# 使用方法：
# 1. 将 audio_config_generator.py 复制到 src/audio_processing/ 目录
# 2. 在 integrated_recording_interface.py 顶部添加：
#    from src.audio_processing.audio_config_generator import AudioConfigGenerator
# 3. 替换 start_unified_monitoring 方法
# 4. 测试验证
'''
    
    print(integration_code)
    
    # 保存集成代码
    with open("integration_code.txt", "w", encoding="utf-8") as f:
        f.write(integration_code)
    
    print("💾 集成代码已保存到 integration_code.txt")


if __name__ == "__main__":
    # 运行演示
    demo_optimized_monitoring()
    
    # 生成集成代码
    generate_integration_code()
    
    print(f"\n🎉 优化监听系统演示完成！")
    print(f"📝 关键改进:")
    print(f"   ✅ 动态采样率适配")
    print(f"   ✅ 统一Stream创建逻辑")
    print(f"   ✅ 智能设备验证")
    print(f"   ✅ 优化回退机制")
    print(f"   ✅ 错误码细分处理")
    
    input("\n按Enter键退出...")
