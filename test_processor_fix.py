#!/usr/bin/env python3
"""
测试IntegratedAudioProcessor的降噪功能
"""

try:
    from src.gui.integrated_recording_interface import IntegratedAudioProcessor
    processor = IntegratedAudioProcessor()
    print('✅ IntegratedAudioProcessor 创建成功')
    print(f'降噪处理器状态: {"已初始化" if processor.noise_processor else "未初始化"}')
    
    if processor.noise_processor:
        processor.set_noise_reduction_mode('基础频域降噪')
        print('✅ 降噪模式设置成功')
        print(f'当前降噪模式: {processor.noise_processor.noise_reduction_mode}')
    else:
        print('❌ 降噪处理器未初始化')
        
except Exception as e:
    print(f'❌ 错误: {e}')
    import traceback
    traceback.print_exc()
