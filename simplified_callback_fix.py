#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化监听回调修复脚本
解决音质下降和延迟问题
"""

import re

def create_simplified_callback():
    """生成简化的监听回调函数"""
    simplified_callback = '''                # 🚀 简化监听回调：音质优先，稳定性第一
                def professional_monitoring_callback(indata, outdata, frames, time_info, status):
                    """🎵 音质优先监听回调：2样本@48kHz + 简洁处理"""
                    
                    try:
                        # 🎵 音频数据提取
                        if self.channels == 1 and indata.shape[1] > 1:
                            audio_data = (indata[:, 0] + indata[:, 1]) * 0.5
                        else:
                            audio_data = indata[:, 0] if len(indata.shape) > 1 else indata.flatten()
                        
                        # 🎤 简化智能音量增强（避免复杂处理）
                        if self.intelligent_volume_booster['enabled']:
                            rms = np.sqrt(np.mean(audio_data ** 2))
                            noise_gate = self.intelligent_volume_booster['noise_gate_threshold']
                            
                            if rms > noise_gate:
                                target_level = self.intelligent_volume_booster['target_level']
                                max_gain = self.intelligent_volume_booster['max_gain']
                                
                                # 简单增益计算
                                if rms < target_level * 0.6:
                                    target_gain = min(max_gain, target_level * 0.8 / max(rms, noise_gate))
                                else:
                                    target_gain = max(0.95, min(1.1, target_level / rms))
                                
                                # 平滑增益变化
                                current_gain = self.intelligent_volume_booster['current_gain']
                                smoothing = self.intelligent_volume_booster['gain_smoothing']
                                new_gain = current_gain * smoothing + target_gain * (1 - smoothing)
                                
                                # 更新和应用增益
                                self.intelligent_volume_booster['current_gain'] = new_gain
                                audio_data = audio_data * new_gain
                        
                        # 🔒 简单音量保护（防止削峰）
                        peak = np.max(np.abs(audio_data))
                        if peak > 0.95:
                            audio_data = audio_data * (0.92 / peak)
                        
                        # 🎯 立体声输出
                        if outdata.shape[1] == 1:
                            outdata[:, 0] = audio_data
                        else:
                            outdata[:, 0] = audio_data
                            outdata[:, 1] = audio_data
                        
                        # 🔥 简化状态监控
                        if hasattr(self, '_opt_frame_counter'):
                            self._opt_frame_counter += frames
                        else:
                            self._opt_frame_counter = frames
                        
                        # 每96000帧报告一次状态
                        if self._opt_frame_counter % 96000 == 0:
                            theoretical_latency = (frames / self.professional_monitoring_config['sample_rate']) * 1000
                            current_gain = self.intelligent_volume_booster.get('current_gain', 1.0)
                            print(f"🎵 稳定监听 (第{self._opt_frame_counter//1000:.0f}k帧) - 延迟: {theoretical_latency:.3f}ms, 增益: {current_gain:.2f}x")
                    
                    except Exception as e:
                        # 错误处理：安全静音输出
                        if 'outdata' in locals():
                            outdata.fill(0)
                        print(f"⚠️ 监听处理错误: {e}")'''
    
    return simplified_callback

def apply_callback_fix(file_path):
    """应用简化回调修复"""
    print("🔧 正在应用简化监听回调修复...")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找并替换复杂的回调函数
        pattern = r'([ ]*# 🚀 高品质低延迟监听回调[^}]+?)(\n[ ]*# 🚀 配置专业级音频流)'
        
        simplified = create_simplified_callback()
        
        # 执行替换
        new_content = re.sub(pattern, simplified + '\n\n                # 🚀 配置专业级音频流', content, flags=re.MULTILINE | re.DOTALL)
        
        if new_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print("✅ 简化监听回调修复完成！")
            return True
        else:
            print("⚠️ 未找到需要修复的回调函数")
            return False
            
    except Exception as e:
        print(f"❌ 回调修复失败: {e}")
        return False

if __name__ == "__main__":
    file_path = r"d:\-MindEcho-main\src\gui\integrated_recording_interface.py"
    apply_callback_fix(file_path)
