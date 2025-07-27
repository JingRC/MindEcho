"""
MindEcho 简化版GUI界面
使用tkinter作为备选方案（Python内置，无需额外安装）
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import time
import os
import sys

# 添加项目路径
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.append(project_root)

from src.audio_processing.recorder import AudioRecorder

class MindEchoTkApp:
    def __init__(self, root):
        self.root = root
        self.recorder = None
        self.recording_thread = None
        self.is_recording = False
        self.recording_start_time = None
        
        self.setup_ui()
        self.setup_recorder()
        
    def setup_ui(self):
        """设置用户界面"""
        self.root.title("MindEcho - 智能录音分析系统")
        self.root.geometry("700x600")
        self.root.configure(bg='#f0f0f0')
        
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 标题
        title_label = tk.Label(main_frame, text="MindEcho - 智能录音分析系统", 
                              font=("Arial", 16, "bold"), bg='#f0f0f0', fg='#2c3e50')
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # 录音控制区域
        self.create_recording_controls(main_frame)
        
        # 参数设置区域
        self.create_parameter_settings(main_frame)
        
        # 设备信息区域
        self.create_device_info(main_frame)
        
        # 日志区域
        self.create_log_area(main_frame)
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
    def create_recording_controls(self, parent):
        """创建录音控制区域"""
        # 录音控制框架
        control_frame = ttk.LabelFrame(parent, text="录音控制", padding="10")
        control_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 状态显示
        self.status_var = tk.StringVar(value="状态: 准备录音")
        self.status_label = tk.Label(control_frame, textvariable=self.status_var, 
                                   font=("Arial", 11, "bold"), fg='#2980b9')
        self.status_label.grid(row=0, column=0, columnspan=4, pady=(0, 10))
        
        # 录音时间显示
        self.time_var = tk.StringVar(value="录音时间: 00:00")
        self.time_label = tk.Label(control_frame, textvariable=self.time_var, font=("Arial", 10))
        self.time_label.grid(row=1, column=0, columnspan=4, pady=(0, 10))
        
        # 按钮
        self.start_button = tk.Button(control_frame, text="🎤 开始录音", 
                                    command=self.start_recording, bg='#e74c3c', fg='white',
                                    font=("Arial", 10, "bold"), padx=20)
        self.start_button.grid(row=2, column=0, padx=(0, 5), pady=5)
        
        self.stop_button = tk.Button(control_frame, text="⏹ 停止录音", 
                                   command=self.stop_recording, bg='#95a5a6', fg='white',
                                   font=("Arial", 10, "bold"), padx=20, state='disabled')
        self.stop_button.grid(row=2, column=1, padx=5, pady=5)
        
        self.devices_button = tk.Button(control_frame, text="🔍 查询设备", 
                                      command=self.query_devices, bg='#3498db', fg='white',
                                      font=("Arial", 10, "bold"), padx=20)
        self.devices_button.grid(row=2, column=2, padx=5, pady=5)
        
        self.folder_button = tk.Button(control_frame, text="📁 打开文件夹", 
                                     command=self.open_folder, bg='#f39c12', fg='white',
                                     font=("Arial", 10, "bold"), padx=20)
        self.folder_button.grid(row=2, column=3, padx=(5, 0), pady=5)
        
    def create_parameter_settings(self, parent):
        """创建参数设置区域"""
        params_frame = ttk.LabelFrame(parent, text="录音参数设置", padding="10")
        params_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 采样率
        tk.Label(params_frame, text="采样率 (Hz):").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.sample_rate_var = tk.StringVar(value="44100")
        sample_rate_combo = ttk.Combobox(params_frame, textvariable=self.sample_rate_var,
                                        values=["8000", "16000", "22050", "44100", "48000"],
                                        state="readonly", width=10)
        sample_rate_combo.grid(row=0, column=1, padx=(0, 20))
        
        # 声道数
        tk.Label(params_frame, text="声道数:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.channels_var = tk.StringVar(value="1")
        channels_combo = ttk.Combobox(params_frame, textvariable=self.channels_var,
                                    values=["1", "2"], state="readonly", width=10)
        channels_combo.grid(row=0, column=3, padx=(0, 20))
        
        # 数据类型
        tk.Label(params_frame, text="数据类型:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(10, 0))
        self.dtype_var = tk.StringVar(value="int16")
        dtype_combo = ttk.Combobox(params_frame, textvariable=self.dtype_var,
                                 values=["int16", "float32"], state="readonly", width=10)
        dtype_combo.grid(row=1, column=1, padx=(0, 20), pady=(10, 0))
        
        # 输出目录
        tk.Label(params_frame, text="保存目录:").grid(row=1, column=2, sticky=tk.W, padx=(0, 5), pady=(10, 0))
        self.output_dir_button = tk.Button(params_frame, text="选择目录", command=self.select_output_dir,
                                         bg='#9b59b6', fg='white', padx=10)
        self.output_dir_button.grid(row=1, column=3, pady=(10, 0))
        
        # 当前目录显示
        self.output_dir_var = tk.StringVar(value=os.path.abspath("./recordings"))
        self.output_dir_label = tk.Label(params_frame, textvariable=self.output_dir_var, 
                                       font=("Arial", 9), fg='#7f8c8d')
        self.output_dir_label.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(5, 0))
        
    def create_device_info(self, parent):
        """创建设备信息区域"""
        device_frame = ttk.LabelFrame(parent, text="设备信息", padding="10")
        device_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.device_info_text = tk.Text(device_frame, height=4, wrap=tk.WORD)
        device_scrollbar = ttk.Scrollbar(device_frame, orient="vertical", command=self.device_info_text.yview)
        self.device_info_text.configure(yscrollcommand=device_scrollbar.set)
        
        self.device_info_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        device_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        device_frame.columnconfigure(0, weight=1)
        
        self.device_info_text.insert(tk.END, "点击'查询设备'获取音频设备信息")
        self.device_info_text.configure(state='disabled')
        
    def create_log_area(self, parent):
        """创建日志区域"""
        log_frame = ttk.LabelFrame(parent, text="运行日志", padding="10")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
    def setup_recorder(self):
        """初始化录音器"""
        self.update_recorder()
        
    def update_recorder(self):
        """更新录音器配置"""
        sample_rate = int(self.sample_rate_var.get())
        channels = int(self.channels_var.get())
        dtype = self.dtype_var.get()
        output_dir = self.output_dir_var.get()
        
        self.recorder = AudioRecorder(
            sample_rate=sample_rate,
            channels=channels,
            dtype=dtype,
            output_dir=output_dir
        )
        
        self.log_message(f"录音器已更新: {sample_rate}Hz, {channels}声道, {dtype}")
        
    def start_recording(self):
        """开始录音"""
        if self.is_recording:
            return
            
        self.update_recorder()
        
        def recording_worker():
            if self.recorder.start_recording():
                self.is_recording = True
                self.recording_start_time = time.time()
                
                # 更新UI（在主线程中）
                self.root.after(0, self.on_recording_started)
                
                # 更新录音时间显示
                while self.is_recording:
                    elapsed = int(time.time() - self.recording_start_time)
                    minutes = elapsed // 60
                    seconds = elapsed % 60
                    time_str = f"录音时间: {minutes:02d}:{seconds:02d}"
                    self.root.after(0, lambda: self.time_var.set(time_str))
                    time.sleep(1)
            else:
                self.root.after(0, lambda: self.log_message("录音启动失败"))
                
        self.recording_thread = threading.Thread(target=recording_worker)
        self.recording_thread.daemon = True
        self.recording_thread.start()
        
    def stop_recording(self):
        """停止录音"""
        if not self.is_recording:
            return
            
        self.is_recording = False
        
        def stop_worker():
            filename = self.recorder.stop_recording("voice_recording")
            if filename:
                self.root.after(0, lambda: self.on_recording_stopped(filename))
            else:
                self.root.after(0, lambda: self.log_message("保存录音失败"))
                
        stop_thread = threading.Thread(target=stop_worker)
        stop_thread.daemon = True
        stop_thread.start()
        
    def on_recording_started(self):
        """录音开始的UI更新"""
        self.status_var.set("状态: 正在录音...")
        self.start_button.configure(state='disabled', bg='#95a5a6')
        self.stop_button.configure(state='normal', bg='#e74c3c')
        self.log_message("录音已开始")
        
    def on_recording_stopped(self, filename):
        """录音停止的UI更新"""
        self.status_var.set("状态: 录音完成")
        self.start_button.configure(state='normal', bg='#e74c3c')
        self.stop_button.configure(state='disabled', bg='#95a5a6')
        self.time_var.set("录音时间: 00:00")
        self.log_message(f"录音已保存: {filename}")
        messagebox.showinfo("录音完成", f"录音已成功保存到:\n{filename}")
        
    def query_devices(self):
        """查询音频设备"""
        try:
            devices = self.recorder.query_devices()
            default_device = self.recorder.get_default_input_device_info()
            
            # 更新设备信息显示
            self.device_info_text.configure(state='normal')
            self.device_info_text.delete(1.0, tk.END)
            
            info_text = "可用音频设备:\n"
            for i, device in enumerate(devices):
                device_type = ""
                if device['max_input_channels'] > 0:
                    device_type += "[输入] "
                if device['max_output_channels'] > 0:
                    device_type += "[输出] "
                    
                info_text += f"ID: {i}, {device_type}{device['name']}\n"
                
            if default_device:
                info_text += f"\n默认输入设备: {default_device['name']}"
                
            self.device_info_text.insert(tk.END, info_text)
            self.device_info_text.configure(state='disabled')
            
            self.log_message("设备查询完成")
            
        except Exception as e:
            error_msg = f"查询设备失败: {str(e)}"
            self.device_info_text.configure(state='normal')
            self.device_info_text.delete(1.0, tk.END)
            self.device_info_text.insert(tk.END, error_msg)
            self.device_info_text.configure(state='disabled')
            self.log_message(error_msg)
            
    def open_folder(self):
        """打开录音文件夹"""
        output_dir = self.output_dir_var.get()
        
        # 将相对路径转换为绝对路径
        if not os.path.isabs(output_dir):
            output_dir = os.path.abspath(output_dir)
        
        # 如果目录不存在，先创建它
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
                self.log_message(f"创建录音目录: {output_dir}")
            except Exception as e:
                messagebox.showwarning("警告", f"无法创建目录: {output_dir}\n错误: {e}")
                return
        
        try:
            os.startfile(output_dir)  # Windows
            self.log_message(f"已打开文件夹: {output_dir}")
        except Exception as e:
            messagebox.showwarning("警告", f"无法打开文件夹: {output_dir}\n错误: {e}")
            
    def select_output_dir(self):
        """选择输出目录"""
        directory = filedialog.askdirectory()
        if directory:
            self.output_dir_var.set(directory)
            self.log_message(f"输出目录已更改: {directory}")
            
    def log_message(self, message):
        """添加日志消息"""
        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, formatted_message)
        self.log_text.see(tk.END)
        print(f"[{timestamp}] {message}")  # 同时输出到控制台

def main():
    """主函数"""
    root = tk.Tk()
    app = MindEchoTkApp(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序运行时发生错误: {e}")
        messagebox.showerror("错误", f"程序运行时发生错误:\n{e}")

if __name__ == "__main__":
    main()
