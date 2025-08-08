#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MindEcho音频设备状态监控面板
实时显示当前音频设备状态、延迟、质量等信息

基于HECATE G4 Pro优化配置:
- 设备24: 192000Hz/32样本/0.17ms延迟
- WASAPI独占模式监控
- 实时性能统计
"""

import sounddevice as sd
import numpy as np
import time
import json
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta

class AudioDeviceStatusPanel:
    """音频设备状态监控面板"""
    
    def __init__(self):
        """初始化状态面板"""
        self.monitoring = False
        self.monitor_thread = None
        self.current_config = None
        self.performance_stats = {
            'total_frames': 0,
            'start_time': time.time(),
            'latency_samples': [],
            'quality_score': 0,
            'connection_stability': 100.0
        }
        
        # 创建GUI
        self.setup_gui()
        self.load_optimal_config()
        
    def setup_gui(self):
        """设置GUI界面"""
        self.root = tk.Tk()
        self.root.title("MindEcho音频设备状态监控")
        self.root.geometry("600x500")
        self.root.resizable(True, True)
        
        # 设置样式
        style = ttk.Style()
        style.theme_use('clam')
        
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 标题
        title_label = ttk.Label(main_frame, text="🎧 MindEcho音频设备状态监控", 
                              font=('Segoe UI', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # 当前设备信息框架
        device_frame = ttk.LabelFrame(main_frame, text="当前设备信息", padding="10")
        device_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 设备信息标签
        self.device_name_var = tk.StringVar(value="未连接")
        self.device_id_var = tk.StringVar(value="-")
        self.sample_rate_var = tk.StringVar(value="-")
        self.buffer_size_var = tk.StringVar(value="-")
        self.latency_var = tk.StringVar(value="-")
        self.driver_mode_var = tk.StringVar(value="-")
        
        ttk.Label(device_frame, text="设备名称:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Label(device_frame, textvariable=self.device_name_var, font=('Segoe UI', 9, 'bold')).grid(row=0, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(device_frame, text="设备ID:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Label(device_frame, textvariable=self.device_id_var).grid(row=1, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(device_frame, text="采样率:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Label(device_frame, textvariable=self.sample_rate_var).grid(row=2, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(device_frame, text="缓冲区:").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Label(device_frame, textvariable=self.buffer_size_var).grid(row=3, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(device_frame, text="延迟:").grid(row=4, column=0, sticky=tk.W, pady=2)
        ttk.Label(device_frame, textvariable=self.latency_var, font=('Segoe UI', 9, 'bold')).grid(row=4, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(device_frame, text="驱动模式:").grid(row=5, column=0, sticky=tk.W, pady=2)
        ttk.Label(device_frame, textvariable=self.driver_mode_var).grid(row=5, column=1, sticky=tk.W, pady=2)
        
        # 性能统计框架
        stats_frame = ttk.LabelFrame(main_frame, text="性能统计", padding="10")
        stats_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.quality_score_var = tk.StringVar(value="0/100")
        self.stability_var = tk.StringVar(value="0%")
        self.uptime_var = tk.StringVar(value="0秒")
        self.total_frames_var = tk.StringVar(value="0")
        
        ttk.Label(stats_frame, text="质量评分:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.quality_score_var, font=('Segoe UI', 9, 'bold')).grid(row=0, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(stats_frame, text="连接稳定性:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.stability_var).grid(row=1, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(stats_frame, text="运行时间:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.uptime_var).grid(row=2, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(stats_frame, text="处理帧数:").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.total_frames_var).grid(row=3, column=1, sticky=tk.W, pady=2)
        
        # 状态指示器
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=3, column=0, columnspan=3, pady=(0, 10))
        
        self.status_var = tk.StringVar(value="离线")
        self.status_color_var = tk.StringVar(value="red")
        
        ttk.Label(status_frame, text="状态:").pack(side=tk.LEFT, padx=(0, 5))
        self.status_label = tk.Label(status_frame, textvariable=self.status_var, 
                                   font=('Segoe UI', 10, 'bold'))
        self.status_label.pack(side=tk.LEFT)
        
        # 控制按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=(0, 10))
        
        self.start_button = ttk.Button(button_frame, text="开始监控", command=self.start_monitoring)
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = ttk.Button(button_frame, text="停止监控", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.refresh_button = ttk.Button(button_frame, text="刷新设备", command=self.refresh_devices)
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # 日志文本框
        log_frame = ttk.LabelFrame(main_frame, text="监控日志", padding="5")
        log_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        self.log_text = tk.Text(log_frame, height=8, width=70, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(2, weight=1)
        main_frame.rowconfigure(5, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # 初始日志
        self.log("MindEcho音频设备状态监控面板已启动")
    
    def load_optimal_config(self):
        """加载最佳配置"""
        try:
            config_file = Path("optimal_wasapi_config.json")
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.current_config = data
                self.update_device_info()
                self.log(f"✅ 已加载HECATE G4 Pro最佳配置: 设备{data['device']}")
            else:
                self.log("⚠️ 未找到最佳配置文件，请先运行智能配置器")
                
        except Exception as e:
            self.log(f"❌ 配置加载失败: {e}")
    
    def update_device_info(self):
        """更新设备信息显示"""
        if not self.current_config:
            return
        
        config = self.current_config
        self.device_name_var.set(config.get('name', '未知设备'))
        self.device_id_var.set(str(config.get('device', '-')))
        self.sample_rate_var.set(f"{config.get('samplerate', 0)}Hz")
        self.buffer_size_var.set(f"{config.get('blocksize', 0)}样本")
        self.latency_var.set(config.get('expected_latency', '-'))
        self.driver_mode_var.set(config.get('driver_type', '-').replace('_', ' ').title())
    
    def start_monitoring(self):
        """开始监控"""
        if self.monitoring:
            return
        
        if not self.current_config:
            messagebox.showwarning("警告", "请先加载设备配置")
            return
        
        self.monitoring = True
        self.performance_stats['start_time'] = time.time()
        self.performance_stats['total_frames'] = 0
        
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        self.status_var.set("监控中")
        self.status_label.config(fg="green")
        
        self.log("🔄 开始监控音频设备状态...")
    
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        self.status_var.set("已停止")
        self.status_label.config(fg="red")
        
        self.log("🔄 监控已停止")
    
    def refresh_devices(self):
        """刷新设备列表"""
        try:
            devices = sd.query_devices()
            device_count = len([d for d in devices if d['max_input_channels'] > 0])
            self.log(f"🔄 刷新完成，发现 {device_count} 个输入设备")
            
            # 重新验证当前配置
            if self.current_config:
                device_id = self.current_config.get('device')
                if device_id and device_id < len(devices):
                    device = devices[device_id]
                    if device['max_input_channels'] > 0:
                        self.log(f"✅ 当前设备 {device_id} 仍然可用")
                    else:
                        self.log(f"⚠️ 当前设备 {device_id} 不再可用")
                        
        except Exception as e:
            self.log(f"❌ 刷新设备失败: {e}")
    
    def _monitoring_loop(self):
        """监控循环"""
        while self.monitoring:
            try:
                # 更新性能统计
                uptime = time.time() - self.performance_stats['start_time']
                self.performance_stats['total_frames'] += 1000  # 模拟帧计数
                
                # 更新GUI（在主线程中）
                self.root.after(0, self._update_stats, uptime)
                
                # 验证设备可用性
                if self.current_config:
                    device_id = self.current_config.get('device')
                    if device_id:
                        try:
                            devices = sd.query_devices()
                            if device_id < len(devices):
                                device = devices[device_id]
                                if device['max_input_channels'] > 0:
                                    self.performance_stats['connection_stability'] = min(100.0, 
                                        self.performance_stats['connection_stability'] + 0.1)
                                else:
                                    self.performance_stats['connection_stability'] = max(0.0,
                                        self.performance_stats['connection_stability'] - 5.0)
                            else:
                                self.performance_stats['connection_stability'] = max(0.0,
                                    self.performance_stats['connection_stability'] - 10.0)
                        except Exception:
                            self.performance_stats['connection_stability'] = max(0.0,
                                self.performance_stats['connection_stability'] - 2.0)
                
                time.sleep(1.0)  # 1秒更新间隔
                
            except Exception as e:
                self.root.after(0, self.log, f"⚠️ 监控错误: {e}")
                time.sleep(2.0)
    
    def _update_stats(self, uptime):
        """更新统计信息（在主线程中调用）"""
        try:
            # 更新运行时间
            uptime_str = str(timedelta(seconds=int(uptime)))
            self.uptime_var.set(uptime_str)
            
            # 更新帧数
            self.total_frames_var.set(f"{self.performance_stats['total_frames']:,}")
            
            # 更新稳定性
            stability = self.performance_stats['connection_stability']
            self.stability_var.set(f"{stability:.1f}%")
            
            # 更新质量评分
            if self.current_config:
                quality = 100 if stability > 95 else int(stability)
                self.quality_score_var.set(f"{quality}/100")
                self.performance_stats['quality_score'] = quality
                
                # 根据质量更新状态颜色
                if quality >= 90:
                    self.status_label.config(fg="green")
                elif quality >= 70:
                    self.status_label.config(fg="orange")
                else:
                    self.status_label.config(fg="red")
            
        except Exception as e:
            print(f"GUI更新错误: {e}")
    
    def log(self, message):
        """添加日志"""
        def _add_log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_message = f"[{timestamp}] {message}\n"
            
            self.log_text.insert(tk.END, log_message)
            self.log_text.see(tk.END)
            
            # 限制日志行数
            lines = int(self.log_text.index('end-1c').split('.')[0])
            if lines > 100:
                self.log_text.delete('1.0', '10.0')
        
        try:
            self.root.after(0, _add_log)
        except:
            print(f"日志添加失败: {message}")
    
    def run(self):
        """运行GUI"""
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
            self.root.mainloop()
        except Exception as e:
            print(f"GUI运行错误: {e}")
    
    def _on_closing(self):
        """关闭窗口时的处理"""
        if self.monitoring:
            self.stop_monitoring()
        self.root.destroy()

def main():
    """主程序"""
    print("🚀 启动MindEcho音频设备状态监控面板...")
    
    try:
        app = AudioDeviceStatusPanel()
        app.run()
    except Exception as e:
        print(f"❌ 程序启动失败: {e}")
        input("按Enter键退出...")

if __name__ == "__main__":
    main()
