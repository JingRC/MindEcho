#!/usr/bin/env python3
"""
音频设备连接检测脚本
检查是否连接到延迟最低、音质最好的监听设备
"""

import sounddevice as sd
import numpy as np

def check_optimal_device():
    """检查最佳监听设备连接状态"""
    print("🔍 检测最佳监听设备...")
    print("="*50)
    
    try:
        devices = sd.query_devices()
        
        # 分析设备质量
        device_scores = []
        
        for i, device in enumerate(devices):
            if device.get('max_input_channels', 0) > 0:
                name = device.get('name', '')
                sample_rate = device.get('default_samplerate', 44100)
                
                # 计算设备评分
                score = 0
                
                # 采样率评分 (40%)
                if sample_rate >= 192000:
                    score += 40
                elif sample_rate >= 96000:
                    score += 30
                elif sample_rate >= 48000:
                    score += 20
                else:
                    score += 10
                
                # 品牌/型号评分 (30%)
                if 'HECATE' in name.upper():
                    score += 30
                elif 'REALTEK' in name.upper():
                    score += 20
                elif 'USB' in name.upper():
                    score += 25
                else:
                    score += 10
                
                # WASAPI支持评分 (20%)
                if 'WASAPI' in str(device):
                    score += 20
                else:
                    score += 10
                
                # 延迟评分 (10%) - 基于设备类型估算
                if 'HECATE' in name.upper():
                    score += 10
                else:
                    score += 5
                
                device_scores.append({
                    'index': i,
                    'name': name,
                    'sample_rate': sample_rate,
                    'score': score,
                    'device': device
                })
        
        # 排序设备
        device_scores.sort(key=lambda x: x['score'], reverse=True)
        
        print("🏆 设备音质排名:")
        for rank, dev in enumerate(device_scores[:5], 1):
            quality = "🥇 极佳" if dev['score'] >= 80 else "🥈 优秀" if dev['score'] >= 60 else "🥉 良好" if dev['score'] >= 40 else "⭐ 一般"
            print(f"{rank}. {dev['name']}")
            print(f"   └─ 评分: {dev['score']}/100 {quality}")
            print(f"   └─ 采样率: {dev['sample_rate']:.0f}Hz")
            
        # 推荐最佳设备
        best_device = device_scores[0]
        print(f"\n🎯 推荐监听设备:")
        print(f"   设备: {best_device['name']}")
        print(f"   索引: {best_device['index']}")
        print(f"   采样率: {best_device['sample_rate']:.0f}Hz")
        print(f"   综合评分: {best_device['score']}/100")
        
        # 检查当前默认设备
        try:
            default_input = sd.query_devices(kind='input')
            print(f"\n📱 当前默认输入设备:")
            print(f"   {default_input['name']} (索引 {sd.default.device[0]})")
            
            if sd.default.device[0] == best_device['index']:
                print("   ✅ 已连接到最佳设备！")
            else:
                print("   ⚠️ 未使用最佳设备")
                print(f"   💡 建议切换到: {best_device['name']}")
                
        except Exception as e:
            print(f"   ❌ 无法获取默认设备: {e}")
            
        return best_device
        
    except Exception as e:
        print(f"❌ 设备检测失败: {e}")
        return None

def test_device_latency(device_index):
    """测试设备延迟"""
    print(f"\n⏱️ 测试设备 {device_index} 的延迟...")
    
    try:
        # 测试不同缓冲区大小的延迟
        buffer_sizes = [32, 64, 128, 256]
        
        for buffer_size in buffer_sizes:
            try:
                # 创建测试流
                with sd.Stream(
                    device=device_index,
                    channels=1,
                    blocksize=buffer_size,
                    samplerate=48000,
                    dtype='float32'
                ) as stream:
                    theoretical_latency = buffer_size / 48000 * 1000
                    print(f"   {buffer_size:3d}样本: {theoretical_latency:.2f}ms (理论)")
                    
            except Exception as e:
                print(f"   {buffer_size:3d}样本: 不支持 ({str(e)[:30]}...)")
                
    except Exception as e:
        print(f"   ❌ 延迟测试失败: {e}")

if __name__ == "__main__":
    best = check_optimal_device()
    if best:
        test_device_latency(best['index'])
        
        print(f"\n🚀 优化建议:")
        print(f"1. 在MindEcho中手动选择设备 {best['index']}")
        print(f"2. 启用WASAPI独占模式")
        print(f"3. 使用32-64样本缓冲区")
        print(f"4. 设置采样率为 {best['sample_rate']:.0f}Hz")
