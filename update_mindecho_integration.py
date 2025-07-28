#!/usr/bin/env python3
"""
MindEcho音频处理集成更新
应用增强YIN检测和智能降噪
"""

def update_integrated_recording_interface():
    """更新集成录音界面以支持增强音频处理"""
    
    file_path = "src/gui/integrated_recording_interface.py"
    
    # 读取文件内容
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找并替换process_audio_for_pitch函数
        old_function_start = 'def process_audio_for_pitch(self, audio_data):'
        
        new_function = '''def process_audio_for_pitch(self, audio_data):
        """处理音频进行音高分析 - 使用增强YIN和智能降噪"""
        try:
            current_time = time.time()
            
            # 初始化增强的音频处理器（如果还没有）
            if not hasattr(self, 'enhanced_yin_processor'):
                from enhanced_yin_detector import StabilizedAudioProcessor
                self.enhanced_yin_processor = StabilizedAudioProcessor(self.sample_rate)
                print("✅ 集成增强YIN音高检测器")
            
            if not hasattr(self, 'smart_noise_processor'):
                from smart_noise_reduction import IntegratedSmartProcessor
                self.smart_noise_processor = IntegratedSmartProcessor(self.sample_rate)
                print("✅ 集成智能降噪处理器")
            
            # 步骤1: 智能降噪和稳定音高检测
            if self.noise_processor and self.noise_processor.noise_reduction_mode == "基础频域降噪":
                # 使用增强的稳定音高检测
                frequency, confidence = self.enhanced_yin_processor.process_with_stability(audio_data)
                
                if frequency > 0:
                    # 使用检测到的音高进行智能降噪
                    processed_audio_data = self.smart_noise_processor.process_audio_intelligently(audio_data, frequency)
                else:
                    # 无音高时仍进行环境噪音过滤
                    processed_audio_data = self.smart_noise_processor.process_audio_intelligently(audio_data, 0)
                
                # 减少调试输出
                if hasattr(self, '_enhanced_debug_counter'):
                    self._enhanced_debug_counter += 1
                    if self._enhanced_debug_counter % 300 == 0:  # 每300帧打印一次
                        try:
                            stats = self.smart_noise_processor.get_processing_stats()
                            print(f"🎯 智能音频处理 | 帧数: {self._enhanced_debug_counter} | 当前: {frequency:.1f}Hz | 噪音过滤率: {stats['noise_filter_ratio']:.1%}")
                        except:
                            print(f"🎯 智能音频处理 | 帧数: {self._enhanced_debug_counter} | 当前: {frequency:.1f}Hz")
                else:
                    self._enhanced_debug_counter = 1
                    print("🔥 启用增强YIN检测 + 智能降噪系统")
            else:
                # 使用原始简单检测
                frequency = self.simple_pitch_detection(audio_data)
                confidence = 0.5 if frequency > 0 else 0'''
        
        # 找到函数位置并替换
        function_start = content.find(old_function_start)
        if function_start == -1:
            print("❌ 找不到目标函数")
            return False
        
        # 找到函数结束位置（下一个同级函数）
        lines = content[function_start:].split('\n')
        new_lines = []
        in_function = True
        indent_level = None
        
        for i, line in enumerate(lines):
            if i == 0:  # 函数定义行
                continue
                
            # 确定缩进级别
            if indent_level is None and line.strip():
                indent_level = len(line) - len(line.lstrip())
            
            # 检查是否到达函数结束
            if (line.strip() and 
                len(line) - len(line.lstrip()) <= 4 and  # 类方法级别的缩进
                (line.strip().startswith('def ') or 
                 line.strip().startswith('class ') or
                 line.strip().startswith('@'))):
                # 找到下一个函数，结束当前函数
                function_end = function_start + len('\n'.join(lines[:i]))
                break
        else:
            # 如果没找到下一个函数，取到文件末尾
            function_end = len(content)
        
        # 构建新内容
        new_content = (content[:function_start] + 
                      new_function + '\n' + 
                      content[function_end:])
        
        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        print("✅ 成功更新integrated_recording_interface.py")
        return True
        
    except Exception as e:
        print(f"❌ 更新失败: {e}")
        return False

if __name__ == "__main__":
    print("🔄 开始更新MindEcho音频处理集成...")
    
    success = update_integrated_recording_interface()
    
    if success:
        print("🎉 更新完成！现在MindEcho支持:")
        print("  • 增强YIN音高检测算法")
        print("  • 环境噪音智能过滤")
        print("  • 音高稳定性验证")
        print("  • 自适应降噪强度调整")
        print("  • 谐波结构保护")
        print("\n🚀 可以启动MindEcho测试新功能了！")
    else:
        print("❌ 更新失败，请检查错误信息")
