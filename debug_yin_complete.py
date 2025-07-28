#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试YIN算法的完整过程
"""

import sys
import numpy as np
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def debug_yin_algorithm():
    """调试YIN算法的完整检测过程"""
    print("🔍 调试YIN算法完整过程")
    print("=" * 50)
    
    try:
        from enhanced_yin_detector import EnhancedYIN
        
        # 创建检测器
        detector = EnhancedYIN(44100, 1024)
        
        # 生成测试信号
        sample_rate = 44100
        duration = 0.02  # 20ms帧
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # 测试220Hz轻微人声
        target_freq = 220
        target_rms = 0.005
        signal = np.sin(2 * np.pi * target_freq * t)
        current_rms = np.sqrt(np.mean(signal ** 2))
        audio_data = signal * (target_rms / current_rms)
        
        print(f"测试信号: {target_freq}Hz, RMS={target_rms}")
        print("-" * 50)
        
        # 步骤1: 信号检测
        signal_present = detector._is_signal_present(audio_data)
        print(f"1. 信号检测: {'通过' if signal_present else '失败'}")
        
        if not signal_present:
            print("❌ 信号检测失败，无法进行音高检测")
            return False
        
        # 步骤2: 预处理 - 加汉宁窗
        window = np.hanning(len(audio_data))
        windowed = audio_data * window
        print(f"2. 汉宁窗处理完成")
        
        # 步骤3: CMNDF计算
        try:
            cmndf = detector._cmndf(windowed)
            print(f"3. CMNDF计算: 长度={len(cmndf)}")
            
            # 查找最小值位置
            min_tau = int(0.5 * detector.sr / 800)  # 800Hz对应的最小tau
            max_tau = int(0.5 * detector.sr / 80)   # 80Hz对应的最大tau
            max_tau = min(max_tau, len(cmndf) - 1)
            
            if max_tau <= min_tau:
                print(f"❌ tau范围无效: min_tau={min_tau}, max_tau={max_tau}")
                return False
                
            search_range = cmndf[min_tau:max_tau]
            print(f"4. 查找范围: tau={min_tau}-{max_tau}, CMNDF值范围=[{np.min(search_range):.4f}, {np.max(search_range):.4f}]")
            
            # 寻找第一个低于阈值的点
            threshold_crossings = np.where(search_range < detector.threshold)[0]
            print(f"5. 阈值{detector.threshold}穿越点: {len(threshold_crossings)}个")
            
            if len(threshold_crossings) > 0:
                # 找到最小值点
                first_crossing = threshold_crossings[0] + min_tau
                local_search_start = max(first_crossing, min_tau)
                local_search_end = min(first_crossing + 50, max_tau)
                
                if local_search_end > local_search_start:
                    local_cmndf = cmndf[local_search_start:local_search_end]
                    min_idx = np.argmin(local_cmndf) + local_search_start
                    min_val = cmndf[min_idx]
                    
                    print(f"6. 找到最小值: tau={min_idx}, CMNDF={min_val:.4f}")
                    
                    # 计算音高
                    estimated_freq = detector.sr / (2 * min_idx) if min_idx > 0 else 0
                    confidence = 1 - min_val
                    
                    print(f"7. 估算音高: {estimated_freq:.1f}Hz, 置信度: {confidence:.3f}")
                    
                    # 检查置信度阈值
                    if confidence > 0.1:  # 当前要求
                        print(f"✅ 音高检测成功: {estimated_freq:.1f}Hz")
                        return True
                    else:
                        print(f"❌ 置信度不足: {confidence:.3f} <= 0.1")
                        return False
                else:
                    print("❌ 局部搜索范围无效")
                    return False
            else:
                print(f"❌ 没有找到低于阈值{detector.threshold}的点")
                # 显示最小值信息
                min_idx_global = np.argmin(search_range) + min_tau
                min_val_global = cmndf[min_idx_global]
                print(f"   全局最小值: tau={min_idx_global}, CMNDF={min_val_global:.4f}")
                
                if min_val_global < detector.threshold * 1.2:  # 如果接近阈值
                    print(f"   建议降低YIN阈值到 {min_val_global * 0.9:.3f}")
                
                return False
                
        except Exception as e:
            print(f"❌ CMNDF计算错误: {e}")
            return False
        
    except Exception as e:
        print(f"❌ 调试错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    debug_yin_algorithm()
    input("\n按回车键退出...")
