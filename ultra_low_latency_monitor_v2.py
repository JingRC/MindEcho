#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 MindEcho 终极低延迟监听系统
Ultra Low Latency Monitoring System v2.0

专为实现近似零延迟的实时音频监听而设计
"""

import numpy as np
import sounddevice as sd
import time
from collections import deque

class UltraLowLatencyMonitor:
    """终极低延迟监听器"""
    
    def __init__(self):
        # 🚀 终极低延迟配置
        self.config = {
            'sample_rate': 44100,      # 44.1kHz 最佳兼容性
            'block_size': 4,           # 4样本 = 0.09ms 理论延迟
            'channels': 1,             # 单声道减少处理负担
            'dtype': np.float32,       # 32位浮点精度
            'latency': 'low'           # 低延迟模式
        }
        
        # 🎚️ 智能音量控制
        self.volume_control = {
            'enabled': True,
            'base_gain': 1.0,
            'max_gain': 2.0,           # 最大2倍增益
            'target_level': 0.25,      # 目标音量
            'current_gain': 1.0,
            'smoothing': 0.95,         # 增益平滑
            'manual_volume': 1.0,      # 手动音量控制
            'manual_enabled': False,    # 手动控制开关
            'rms_history': deque(maxlen=5)  # 短历史，快速响应
        }
        
        # 状态管理
        self.stream = None
        self.is_monitoring = False
        self.frame_counter = 0
        
        print("🚀 终极低延迟监听器初始化完成")
        print(f"📊 配置: {self.config['sample_rate']}Hz, {self.config['block_size']}样本")
        print(f"⚡ 理论延迟: {self.config['block_size']/self.config['sample_rate']*1000:.2f}ms")
    
    def audio_callback(self, indata, outdata, frames, time_info, status):
        """极简音频回调 - 最小化处理延迟"""
        try:
            self.frame_counter += 1
            
            # 状态报告（每10000帧一次，减少输出）
            if self.frame_counter % 10000 == 0:
                print(f"🎧 监听运行中: {self.frame_counter//1000}k帧")
            
            # 获取音频数据（快速路径）
            if indata.shape[1] > 1:
                # 立体声快速混合
                audio = np.sum(indata, axis=1) * 0.5
            else:
                audio = indata[:, 0]
            
            # 智能音量处理
            if self.volume_control['enabled']:
                # 快速RMS计算
                rms = np.sqrt(np.mean(audio ** 2))
                self.volume_control['rms_history'].append(rms)
                
                if len(self.volume_control['rms_history']) >= 3:
                    avg_rms = np.mean(self.volume_control['rms_history'])
                    
                    # 噪声门限
                    if avg_rms > 0.002:
                        # 计算目标增益
                        target_level = self.volume_control['target_level']
                        if avg_rms < target_level * 0.5:
                            target_gain = min(self.volume_control['max_gain'], 
                                            target_level * 0.6 / max(avg_rms, 0.002))
                        else:
                            target_gain = max(0.9, min(1.1, target_level / avg_rms))
                        
                        # 快速增益平滑
                        current_gain = self.volume_control['current_gain']
                        smoothing = self.volume_control['smoothing']
                        new_gain = current_gain * smoothing + target_gain * (1 - smoothing)
                        
                        # 限制增益变化
                        if abs(new_gain - current_gain) > 0.05:
                            new_gain = current_gain + (0.05 if new_gain > current_gain else -0.05)
                        
                        self.volume_control['current_gain'] = new_gain
                        
                        # 应用增益
                        if new_gain > 1.05:
                            audio = audio * new_gain
                            # 软限制
                            if np.max(np.abs(audio)) > 0.95:
                                audio = audio * (0.95 / np.max(np.abs(audio)))
                    else:
                        # 噪声衰减
                        audio = audio * 0.8
            
            # 应用手动音量控制
            if self.volume_control['manual_enabled']:
                audio = audio * self.volume_control['manual_volume']
            
            # 输出到扬声器
            if outdata.shape[1] == 1:
                outdata[:, 0] = audio
            else:
                outdata[:, 0] = audio  # 左声道
                outdata[:, 1] = audio  # 右声道
                
        except Exception as e:
            print(f"⚠️ 音频回调错误: {e}")
            outdata.fill(0)  # 静音输出
    
    def start_monitoring(self):
        """启动超低延迟监听"""
        try:
            print("🚀 启动终极低延迟监听...")
            
            # 尝试不同的音频驱动配置
            configs = [
                # 配置1: 最低延迟
                {
                    'name': 'ASIO超低延迟',
                    'sample_rate': 44100,
                    'block_size': 4,
                    'extra_settings': sd.AsioSettings(channel_selectors=[0])
                },
                # 配置2: DirectSound低延迟
                {
                    'name': 'DirectSound低延迟',
                    'sample_rate': 44100,
                    'block_size': 8,
                    'extra_settings': None
                },
                # 配置3: 标准配置
                {
                    'name': '标准低延迟',
                    'sample_rate': 44100,
                    'block_size': 16,
                    'extra_settings': None
                }
            ]
            
            for config in configs:
                try:
                    stream_params = {
                        'channels': self.config['channels'],
                        'samplerate': config['sample_rate'],
                        'blocksize': config['block_size'],
                        'callback': self.audio_callback,
                        'dtype': self.config['dtype'],
                        'latency': self.config['latency']
                    }
                    
                    if config['extra_settings']:
                        stream_params['extra_settings'] = config['extra_settings']
                    
                    self.stream = sd.Stream(**stream_params)
                    
                    latency = config['block_size'] / config['sample_rate'] * 1000
                    print(f"✅ {config['name']}启动成功")
                    print(f"📊 {config['sample_rate']}Hz, {config['block_size']}样本 = {latency:.2f}ms延迟")
                    break
                    
                except Exception as e:
                    print(f"⚠️ {config['name']}失败: {e}")
                    continue
            
            if self.stream is None:
                raise Exception("所有音频配置都失败")
            
            self.stream.start()
            self.is_monitoring = True
            self.frame_counter = 0
            
            print("🎧 终极低延迟监听已启动")
            print("🎚️ 提示: 使用set_manual_volume()调节音量")
            return True
            
        except Exception as e:
            print(f"❌ 启动监听失败: {e}")
            return False
    
    def stop_monitoring(self):
        """停止监听"""
        try:
            self.is_monitoring = False
            
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            
            print("🎧 监听已停止")
            print(f"📊 总处理帧数: {self.frame_counter}")
            
        except Exception as e:
            print(f"❌ 停止监听失败: {e}")
    
    def set_manual_volume(self, volume_percent):
        """设置手动音量 (0-300%)"""
        volume_percent = max(0, min(300, volume_percent))
        self.volume_control['manual_volume'] = volume_percent / 100.0
        self.volume_control['manual_enabled'] = True
        
        print(f"🎚️ 手动音量设置为 {volume_percent}%")
    
    def get_manual_volume(self):
        """获取当前手动音量"""
        return self.volume_control['manual_volume'] * 100
    
    def disable_manual_volume(self):
        """禁用手动音量控制"""
        self.volume_control['manual_enabled'] = False
        print("🎚️ 手动音量控制已禁用")
    
    def get_status(self):
        """获取监听状态"""
        if self.is_monitoring:
            current_gain = self.volume_control['current_gain']
            manual_vol = self.volume_control['manual_volume'] * 100
            manual_enabled = self.volume_control['manual_enabled']
            
            return {
                'monitoring': True,
                'frames_processed': self.frame_counter,
                'auto_gain': f"{current_gain:.2f}x",
                'manual_volume': f"{manual_vol:.0f}%",
                'manual_enabled': manual_enabled
            }
        else:
            return {'monitoring': False}

# 测试代码
if __name__ == "__main__":
    print("🚀 MindEcho 终极低延迟监听系统测试")
    print("=" * 50)
    
    monitor = UltraLowLatencyMonitor()
    
    try:
        if monitor.start_monitoring():
            print("\n✅ 监听已启动，按回车键停止...")
            input()
        else:
            print("\n❌ 监听启动失败")
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
    finally:
        monitor.stop_monitoring()
        print("\n🎉 测试完成")
