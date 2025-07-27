import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wavfile
import threading
import queue
import time
import os

class AudioRecorder:
    def __init__(self,
                 sample_rate=44100,
                 channels=1,
                 dtype='int16',
                 output_dir="recordings"): # 录音文件保存的目录
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.output_dir = output_dir
        self.is_recording = False
        self.recording_data = []
        self.audio_queue = queue.Queue() # 用于线程间传递音频数据
        self.stream = None # 音频流对象
        self.output_file = None  # 输出文件路径

        # 创建录音文件保存目录（如果不存在）
        # 将相对路径转换为绝对路径
        if not os.path.isabs(self.output_dir):
            self.output_dir = os.path.abspath(self.output_dir)
        
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            print(f"录音目录已准备: {self.output_dir}")
        except Exception as e:
            print(f"创建录音目录失败: {e}")
            # 使用当前目录作为备选
            self.output_dir = os.path.abspath(".")
            print(f"使用当前目录: {self.output_dir}")

        # 设置默认设备（可选，如果你有特定需求可以调整）
        # print("可用设备：", sd.query_devices())
        # sd.default.device = 5 # 示例：设置为某个特定ID的输入设备
        # sd.default.channels = self.channels # 确保声道数匹配

    def _callback(self, indata, frames, time, status):
        """
        这是音频流的回调函数，当有新的音频数据时被调用。
        indata: 包含音频数据的numpy数组
        frames: 每次回调接收到的帧数
        time: 音频时间信息
        status: 状态信息 (如溢出等)
        """
        if status:
            print(f"Audio stream status: {status}")
        
        if self.is_recording:
            self.audio_queue.put(indata.copy()) # 将音频数据放入队列

    def start_recording(self, output_file=None):
        """
        开始录音。
        
        Args:
            output_file (str, optional): 输出文件路径。如果不指定，将在stop_recording时生成文件名。
        """
        if self.is_recording:
            print("已经在录音中。")
            return

        self.is_recording = True
        self.recording_data = [] # 清空之前的数据
        self.audio_queue = queue.Queue() # 重置队列
        self.output_file = output_file  # 保存输出文件路径

        try:
            # 使用回调函数模式录音 (非阻塞)
            self.stream = sd.InputStream(samplerate=self.sample_rate,
                                         channels=self.channels,
                                         dtype=self.dtype,
                                         callback=self._callback)
            self.stream.start()
            print("录音已开始...")
            return True
        except Exception as e:
            print(f"启动录音失败: {e}")
            self.is_recording = False
            return False

    def stop_recording(self, filename_prefix="recording"):
        """
        停止录音并保存到文件。
        """
        if not self.is_recording:
            print("未在录音中。")
            return None

        self.is_recording = False
        
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            print("录音已停止。")

        # 从队列中收集所有录音数据
        while not self.audio_queue.empty():
            self.recording_data.append(self.audio_queue.get())
            
        if not self.recording_data:
            print("没有录音数据可保存。")
            return None

        # 将列表中的numpy数组合并成一个大的numpy数组
        # 检查recording_data中的元素是否为numpy数组，以及它们的形状
        # print("Collected data shapes:", [item.shape for item in self.recording_data])
        
        # Ensure all elements are numpy arrays and have compatible shapes
        valid_data = [item for item in self.recording_data if isinstance(item, np.ndarray) and item.shape[1] == self.channels]
        if not valid_data:
            print("未找到有效的录音数据。")
            return None

        try:
            audio_array = np.concatenate(valid_data, axis=0)
        except ValueError as e:
            print(f"合并音频数据时出错: {e}")
            print("请检查录音数据是否一致（例如，所有录音段的声道数是否相同）")
            return None

        # 确定输出文件路径
        if hasattr(self, 'output_file') and self.output_file:
            # 使用开始录音时指定的文件路径
            filename = self.output_file
        else:
            # 生成文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.output_dir, f"{filename_prefix}_{timestamp}.wav")

        try:
            # 保存为WAV文件
            # 注意：如果dtype是'float32'，wavfile.write仍然可以处理，但通常写入int16更通用
            if self.dtype == 'int16':
                # 如果录制的原始数据是float32，需要先转换回int16
                if audio_array.dtype == np.float32:
                    # 确保值在 int16 的范围内 [-32768, 32767]
                    audio_array = np.clip(audio_array * 32767, -32768, 32767).astype(np.int16)
                elif audio_array.dtype != np.int16: # 如果是其他类型，也尝试转换
                    audio_array = audio_array.astype(np.int16)
            elif self.dtype == 'float32':
                # 如果用户指定float32，可以直接保存
                pass
            
            wavfile.write(filename, self.sample_rate, audio_array)
            print(f"录音已保存至 {filename}")
            return filename
        except Exception as e:
            print(f"保存录音文件失败: {e}")
            return None

    def query_devices(self):
        """
        查询并打印系统可用的音频输入/输出设备。
        """
        print("可用音频设备:")
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            print(f"  ID: {i}, Name: {device['name']}, Max Input Channels: {device['max_input_channels']}, Max Output Channels: {device['max_output_channels']}")
        print("-" * 20)
        return devices
        
    def get_default_input_device_info(self):
        """
        获取默认输入设备的详细信息。
        """
        try:
            info = sd.query_devices(kind='input')
            return info
        except Exception as e:
            print(f"获取默认输入设备信息失败: {e}")
            return None

if __name__ == "__main__":
    # --- 示例用法 ---
    
    # 1. 实例化Recorder
    recorder = AudioRecorder(sample_rate=44100, channels=1, dtype='int16')

    # 2. (可选) 查询设备，找到你想要使用的麦克风ID
    recorder.query_devices()
    default_device_info = recorder.get_default_input_device_info()
    if default_device_info:
        print(f"正在使用默认输入设备: {default_device_info['name']}")
    else:
        print("未能获取默认输入设备信息，可能使用系统默认或需要手动指定设备ID。")

    # 3. 开始录音
    if recorder.start_recording():
        # 假设我们要录制5秒
        record_duration = 5
        print(f"将录制 {record_duration} 秒...")
        time.sleep(record_duration) # 模拟用户录制一段时间
        
        # 4. 停止录音并保存
        saved_file = recorder.stop_recording("my_voice_test")
        if saved_file:
            print(f"录音已成功保存到: {saved_file}")
        else:
            print("录音保存失败。")
    else:
        print("无法开始录音，请检查麦克风设置或权限。")

    print("\n--- 尝试录制不同参数 ---")
    recorder_float = AudioRecorder(sample_rate=16000, channels=1, dtype='float32')
    if recorder_float.start_recording():
        record_duration = 3
        print(f"将录制 {record_duration} 秒 (float32)...")
        time.sleep(record_duration)
        saved_file_float = recorder_float.stop_recording("float_voice_test")
        if saved_file_float:
            print(f"录音已成功保存到: {saved_file_float}")
    else:
        print("无法开始录音 (float32)。")
