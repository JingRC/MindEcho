"""
集成录音与音高检测的模块
实现边录音边进行实时音高分析
"""

import numpy as np
import threading
import queue
import time
import json
from pathlib import Path
from collections import deque
import sounddevice as sd
import scipy.io.wavfile as wavfile

# 修复导入路径
import sys
sys.path.append('..')
from src.analysis.pitch_detection import PitchDetector

class IntegratedRecorderAnalyzer:
    """集成录音器和音高分析器"""
    
    def __init__(self, sample_rate=44100, channels=1, chunk_size=4096, output_dir="recordings"):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 录音相关
        self.is_recording = False
        self.recording_data = []
        self.stream = None
        
        # 音高分析相关
        self.pitch_detector = PitchDetector(sample_rate, chunk_size)
        self.pitch_history = []
        self.time_history = []
        self.note_history = []
        
        # 实时回调
        self.pitch_callback = None
        
        # 配置
        self.volume_threshold = 0.01
        self.save_analysis_data = True
    
    def set_pitch_callback(self, callback):
        """设置音高检测回调函数"""
        self.pitch_callback = callback
    
    def _audio_callback(self, indata, frames, time_info, status):
        """音频流回调函数"""
        if status:
            # 只在非溢出错误时打印警告
            if 'input overflow' not in str(status).lower():
                print(f"音频流状态: {status}")
            # 对于input overflow，可以选择忽略或记录但不打印
        
        # 保存录音数据
        audio_data = indata.copy()
        self.recording_data.append(audio_data)
        
        # 转换为单声道进行音高分析
        if self.channels > 1:
            mono_data = np.mean(audio_data, axis=1)
        else:
            mono_data = audio_data.flatten()
        
        # 检查音量 - 降低阈值提高敏感性
        rms = np.sqrt(np.mean(mono_data ** 2))
        
        if rms > self.volume_threshold * 0.5:  # 降低阈值，提高敏感性
            # 音高检测
            try:
                frequency = self.pitch_detector.detect_pitch_yin(mono_data, self.sample_rate)
                
                if frequency and frequency > 60:  # 降低频率阈值，从80Hz降到60Hz
                    # 转换为音符信息
                    note_name, octave, midi_note, cents = self.pitch_detector.frequency_to_note_info(frequency)
                    
                    # 记录数据
                    current_time = time.time()
                    
                    pitch_data = {
                        'timestamp': current_time,
                        'frequency': frequency,
                        'note_name': note_name,
                        'octave': octave,
                        'midi_note': midi_note,
                        'cents_deviation': cents,
                        'volume': rms,
                        'confidence': 0.8  # YIN算法的置信度
                    }
                    
                    # 保存历史数据
                    self.pitch_history.append(frequency)
                    self.time_history.append(current_time)
                    self.note_history.append(pitch_data)
                    
                    # 调用回调函数
                    if self.pitch_callback:
                        try:
                            self.pitch_callback(pitch_data)
                        except Exception as e:
                            print(f"回调函数错误: {e}")
                
            except Exception as e:
                print(f"音高检测错误: {e}")
    
    def start_recording_with_analysis(self, filename=None):
        """开始录音并同时进行音高分析"""
        if self.is_recording:
            print("已在录音中")
            return False
        
        # 生成文件名
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"recording_with_analysis_{timestamp}"
        
        self.current_filename = filename
        self.start_time = time.time()
        
        # 清空历史数据
        self.recording_data = []
        self.pitch_history = []
        self.time_history = []
        self.note_history = []
        
        try:
            # 启动音频流
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.float32,
                blocksize=self.chunk_size,
                callback=self._audio_callback
            )
            
            self.stream.start()
            self.is_recording = True
            
            print(f"开始录音并分析音高...")
            print(f"采样率: {self.sample_rate} Hz")
            print(f"声道数: {self.channels}")
            print(f"块大小: {self.chunk_size}")
            
            return True
            
        except Exception as e:
            print(f"启动录音失败: {e}")
            return False
    
    def stop_recording_with_analysis(self):
        """停止录音并保存所有数据"""
        if not self.is_recording:
            print("未在录音中")
            return None
        
        self.is_recording = False
        
        # 停止音频流
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        print("录音已停止，正在保存数据...")
        
        # 保存音频文件
        audio_file = self._save_audio_file()
        
        # 保存音高分析数据
        analysis_file = self._save_analysis_data()
        
        # 生成音高曲线图像
        curve_file = self._save_pitch_curve()
        
        return {
            'audio_file': audio_file,
            'analysis_file': analysis_file,
            'curve_file': curve_file,
            'duration': time.time() - self.start_time,
            'pitch_points': len(self.pitch_history),
            'notes_detected': len([n for n in self.note_history if n['frequency'] > 0])
        }
    
    def _save_audio_file(self):
        """保存音频文件"""
        if not self.recording_data:
            print("没有录音数据")
            return None
        
        try:
            # 合并音频数据
            audio_array = np.concatenate(self.recording_data, axis=0)
            
            # 转换为int16格式
            if audio_array.dtype == np.float32:
                audio_array = np.clip(audio_array * 32767, -32768, 32767).astype(np.int16)
            
            # 保存WAV文件
            audio_filename = self.output_dir / f"{self.current_filename}.wav"
            wavfile.write(audio_filename, self.sample_rate, audio_array)
            
            print(f"音频已保存: {audio_filename}")
            return str(audio_filename)
            
        except Exception as e:
            print(f"保存音频文件失败: {e}")
            return None
    
    def _save_analysis_data(self):
        """保存音高分析数据为JSON"""
        if not self.note_history:
            print("没有音高分析数据")
            return None
        
        try:
            # 准备数据 - 转换numpy类型为Python原生类型
            analysis_data = {
                'recording_info': {
                    'filename': self.current_filename,
                    'sample_rate': int(self.sample_rate),
                    'channels': int(self.channels),
                    'duration': float(time.time() - self.start_time),
                    'start_time': float(self.start_time)
                },
                'pitch_data': [
                    {
                        'timestamp': float(item['timestamp']),
                        'frequency': float(item['frequency']),
                        'note_name': str(item['note_name']),
                        'octave': int(item['octave']) if item['octave'] is not None else None,
                        'cents_deviation': float(item['cents_deviation']) if item['cents_deviation'] is not None else None,
                        'volume': float(item['volume']) if 'volume' in item else None,
                        'confidence': float(item['confidence']) if 'confidence' in item else None
                    }
                    for item in self.note_history
                ],
                'statistics': {
                    'total_points': len(self.pitch_history),
                    'valid_pitches': len([f for f in self.pitch_history if f > 0]),
                    'frequency_range': {
                        'min': float(min(self.pitch_history)) if self.pitch_history else 0,
                        'max': float(max(self.pitch_history)) if self.pitch_history else 0
                    }
                }
            }
            
            # 保存JSON文件
            analysis_filename = self.output_dir / f"{self.current_filename}_analysis.json"
            with open(analysis_filename, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, indent=2, ensure_ascii=False)
            
            print(f"分析数据已保存: {analysis_filename}")
            return str(analysis_filename)
            
        except Exception as e:
            print(f"保存分析数据失败: {e}")
            return None
    
    def _save_pitch_curve(self):
        """保存音高曲线图像"""
        if not self.pitch_history or not self.time_history:
            print("没有音高曲线数据")
            return None
        
        try:
            import matplotlib
            # 设置非交互式后端，避免GUI线程问题
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            from datetime import datetime
            
            # 设置中文字体支持
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial']
            plt.rcParams['axes.unicode_minus'] = False
            
            # 创建图形
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
            
            # 转换时间戳为相对时间
            start_time = min(self.time_history)
            relative_times = [(t - start_time) for t in self.time_history]
            
            # 过滤有效数据
            valid_data = [(t, f) for t, f in zip(relative_times, self.pitch_history) if f > 0]
            
            if valid_data:
                valid_times, valid_freqs = zip(*valid_data)
                
                # 绘制频率曲线
                ax1.plot(valid_times, valid_freqs, 'b-', linewidth=1.5, alpha=0.8)
                ax1.scatter(valid_times, valid_freqs, c='red', s=10, alpha=0.6)
                ax1.set_ylabel('频率 (Hz)')
                ax1.set_title(f'音高检测结果 - {self.current_filename}')
                ax1.grid(True, alpha=0.3)
                ax1.set_yscale('log')
                
                # 添加音符标记
                note_times = []
                note_labels = []
                for note_data in self.note_history[-50:]:  # 显示最后50个音符
                    if note_data['frequency'] > 0:
                        rel_time = note_data['timestamp'] - start_time
                        note_times.append(rel_time)
                        note_labels.append(f"{note_data['note_name']}{note_data['octave']}")
                
                if note_times:
                    for i, (t, label) in enumerate(zip(note_times, note_labels)):
                        if i % 5 == 0:  # 每5个标记一个，避免重叠
                            ax1.annotate(label, (t, valid_freqs[min(i, len(valid_freqs)-1)]),
                                       xytext=(5, 5), textcoords='offset points',
                                       fontsize=8, alpha=0.7)
                
                # 绘制音量包络
                if hasattr(self, 'volume_history'):
                    ax2.plot(relative_times, self.volume_history, 'g-', linewidth=1)
                    ax2.set_ylabel('音量 (RMS)')
                    ax2.set_xlabel('时间 (秒)')
                    ax2.grid(True, alpha=0.3)
                else:
                    # 如果没有音量数据，显示音符分布
                    note_names = [n['note_name'] for n in self.note_history if n['frequency'] > 0]
                    if note_names:
                        unique_notes = list(set(note_names))
                        note_counts = [note_names.count(note) for note in unique_notes]
                        
                        ax2.bar(unique_notes, note_counts)
                        ax2.set_ylabel('出现次数')
                        ax2.set_xlabel('音符')
                        ax2.set_title('音符分布统计')
            
            plt.tight_layout()
            
            # 保存图像
            curve_filename = self.output_dir / f"{self.current_filename}_pitch_curve.png"
            plt.savefig(curve_filename, dpi=150, bbox_inches='tight')
            plt.close()
            
            print(f"音高曲线已保存: {curve_filename}")
            return str(curve_filename)
            
        except Exception as e:
            print(f"保存音高曲线失败: {e}")
            return None
    
    def get_current_stats(self):
        """获取当前统计信息"""
        if not self.is_recording:
            return None
        
        current_time = time.time()
        duration = current_time - self.start_time
        
        return {
            'duration': duration,
            'pitch_points': len(self.pitch_history),
            'valid_pitches': len([f for f in self.pitch_history if f > 0]),
            'current_frequency': self.pitch_history[-1] if self.pitch_history else 0,
            'current_note': self.note_history[-1] if self.note_history else None
        }

# 使用示例和测试函数
if __name__ == "__main__":
    def pitch_callback(pitch_data):
        """示例回调函数"""
        freq = pitch_data['frequency']
        note = pitch_data['note_name']
        octave = pitch_data['octave']
        cents = pitch_data['cents_deviation']
        
        print(f"实时音高: {freq:.2f} Hz | 音符: {note}{octave} | 偏差: {cents:+.0f} cents")
    
    # 创建集成录音分析器
    recorder = IntegratedRecorderAnalyzer(sample_rate=44100, chunk_size=4096)
    recorder.set_pitch_callback(pitch_callback)
    
    print("集成录音音高分析器测试")
    print("按Enter开始录音...")
    input()
    
    # 开始录音和分析
    if recorder.start_recording_with_analysis("test_recording"):
        print("录音中... 按Enter停止")
        input()
        
        # 停止并保存
        result = recorder.stop_recording_with_analysis()
        
        if result:
            print(f"\n录音完成!")
            print(f"音频文件: {result['audio_file']}")
            print(f"分析数据: {result['analysis_file']}")
            print(f"音高曲线: {result['curve_file']}")
            print(f"录音时长: {result['duration']:.2f} 秒")
            print(f"检测到音高点: {result['pitch_points']}")
            print(f"有效音符: {result['notes_detected']}")
    else:
        print("录音启动失败")

# 向下兼容的别名
IntegratedAudioRecorder = IntegratedRecorderAnalyzer
