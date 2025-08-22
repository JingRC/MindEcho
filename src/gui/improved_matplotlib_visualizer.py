#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
改进的Matplotlib彩色渐变可视化器
专门解决Matplotlib 3.10.1的渐变兼容性问题
"""

import sys
import os
import numpy as np
from collections import deque
import time
import colorsys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    QT_VERSION = 6
except ImportError:
    try:
        from PyQt5.QtWidgets import *
        from PyQt5.QtCore import *
        from PyQt5.QtGui import *
        QT_VERSION = 5
    except ImportError:
        raise ImportError("需要安装 PyQt6 或 PyQt5")

import matplotlib
matplotlib.use('Qt5Agg')  # 强制使用Qt后端
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
import matplotlib.colors as mcolors


class ImprovedMatplotlibVisualizer(QWidget):
    """改进的Matplotlib可视化器 - 解决渐变兼容性问题"""
    
    def __init__(self):
        super().__init__()
        
        # 数据存储
        self.max_points = 3000
        self.time_data = deque(maxlen=self.max_points)
        self.pitch_data = deque(maxlen=self.max_points)
        self.confidence_data = deque(maxlen=self.max_points)
        
        # 显示参数
        self.time_window = 10.0
        self.y_range = [1.0, 7.0]
        # 默认模式：统一为“普通模式”（兼容原“心电图模式”）
        self.display_mode = "普通模式"
        
        # 性能监控
        self.update_count = 0
        self.last_fps_time = time.time()
        self.fps = 0
        
        # 初始化界面
        self.init_ui()
        self.setup_matplotlib()
        
        print("✅ 改进的Matplotlib可视化器初始化完成")
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("MindEcho - 改进的彩色渐变可视化器 (Matplotlib优化版)")
        self.setGeometry(100, 100, 1400, 900)
        
        # 设置样式
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a;
                color: #ffffff;
                font-family: 'Microsoft YaHei', sans-serif;
            }
            QGroupBox {
                border: 2px solid #404040;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 15px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: #00FF44;
            }
            QPushButton {
                background-color: #404040;
                border: 2px solid #606060;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QComboBox {
                background-color: #404040;
                border: 1px solid #606060;
                border-radius: 4px;
                padding: 6px;
                min-width: 140px;
            }
            QSlider::groove:horizontal {
                background: #404040;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00FF44;
                border: 2px solid #00AA00;
                width: 20px;
                border-radius: 10px;
                margin-top: -6px;
                margin-bottom: -6px;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # 控制面板
        control_panel = self.create_control_panel()
        layout.addWidget(control_panel)
        
        # Matplotlib画布
        self.canvas = self.create_matplotlib_canvas()
        layout.addWidget(self.canvas)
        
        # 状态面板
        status_panel = self.create_status_panel()
        layout.addWidget(status_panel)
    
    def create_control_panel(self):
        """创建控制面板"""
        group = QGroupBox("🎨 渐变可视化控制")
        layout = QVBoxLayout(group)
        
        # 第一行
        row1 = QHBoxLayout()
        
        row1.addWidget(QLabel("显示模式:"))
        self.mode_combo = QComboBox()
        modes = ["普通模式", "彩色渐变", "高性能渐变", "分段彩色", "光谱渐变"]
        self.mode_combo.addItems(modes)
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        row1.addWidget(self.mode_combo)
        
        row1.addWidget(QLabel("渐变质量:"))
        self.quality_combo = QComboBox()
        qualities = ["性能优先", "平衡", "质量优先", "极致效果"]
        self.quality_combo.addItems(qualities)
        self.quality_combo.setCurrentText("平衡")
        self.quality_combo.currentTextChanged.connect(self.on_quality_changed)
        row1.addWidget(self.quality_combo)
        
        row1.addStretch()
        layout.addLayout(row1)
        
        # 第二行
        row2 = QHBoxLayout()
        
        row2.addWidget(QLabel("时间窗口:"))
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(30, 300)
        self.time_slider.setValue(100)
        self.time_slider.valueChanged.connect(self.on_time_changed)
        row2.addWidget(self.time_slider)
        
        self.time_label = QLabel("10.0s")
        row2.addWidget(self.time_label)
        
        row2.addWidget(QLabel("线条细节:"))
        self.detail_slider = QSlider(Qt.Orientation.Horizontal)
        self.detail_slider.setRange(1, 10)
        self.detail_slider.setValue(5)
        self.detail_slider.valueChanged.connect(self.on_detail_changed)
        row2.addWidget(self.detail_slider)
        
        self.detail_label = QLabel("中等")
        row2.addWidget(self.detail_label)
        
        row2.addStretch()
        layout.addLayout(row2)
        
        # 第三行
        row3 = QHBoxLayout()
        
        self.clear_btn = QPushButton("🗑️ 清除数据")
        self.clear_btn.clicked.connect(self.clear_data)
        row3.addWidget(self.clear_btn)
        
        self.test_btn = QPushButton("🎵 测试颤音")
        self.test_btn.clicked.connect(self.load_vibrato_test)
        row3.addWidget(self.test_btn)
        
        self.gradient_btn = QPushButton("🌈 测试渐变")
        self.gradient_btn.clicked.connect(self.test_gradient_modes)
        row3.addWidget(self.gradient_btn)
        
        self.force_redraw_btn = QPushButton("🔄 强制刷新")
        self.force_redraw_btn.clicked.connect(self.force_redraw)
        row3.addWidget(self.force_redraw_btn)
        
        row3.addStretch()
        layout.addLayout(row3)
        
        return group
    
    def create_matplotlib_canvas(self):
        """创建Matplotlib画布"""
        # 创建图形
        self.fig = Figure(figsize=(14, 7), facecolor='#1a1a1a', tight_layout=True)
        canvas = FigureCanvas(self.fig)
        canvas.setMinimumHeight(500)
        
        return canvas
    
    def setup_matplotlib(self):
        """设置Matplotlib"""
        # 清除并创建子图
        self.fig.clear()
        self.ax = self.fig.add_subplot(111, facecolor='#1a1a1a')
        
        # 设置坐标轴样式
        self.ax.set_xlim(0, self.time_window)
        self.ax.set_ylim(*self.y_range)
        self.ax.tick_params(colors='#ffffff', labelsize=10)
        self.ax.set_xlabel('时间 (秒)', color='#ffffff', fontsize=12)
        self.ax.set_ylabel('音高 (八度)', color='#ffffff', fontsize=12)
        
        # 设置网格
        self.ax.grid(True, alpha=0.3, color='#606060', linewidth=0.5)
        
        # 创建主线条（用于心电图模式）
        self.main_line, = self.ax.plot([], [], color='#00FF44', linewidth=1.0, alpha=1.0)
        
        # 存储渐变对象
        self.gradient_collections = []
        self.highlight_scatter = None
        
        # 添加音名标注
        self.add_note_labels()
        
        # 初始绘制
        self.canvas.draw()
        
        print("✅ Matplotlib画布设置完成")
    
    def add_note_labels(self):
        """添加音名标注"""
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        for octave in range(1, 8):
            for i, note in enumerate(note_names):
                y_pos = octave + i / 12
                if self.y_range[0] <= y_pos <= self.y_range[1]:
                    self.ax.text(-0.5, y_pos, f"{note}{octave}", 
                                color='#cccccc', fontsize=9, 
                                verticalalignment='center',
                                horizontalalignment='right')
    
    def create_status_panel(self):
        """创建状态面板"""
        group = QGroupBox("📊 渲染状态")
        layout = QHBoxLayout(group)
        
        self.mode_label = QLabel("模式: 心电图")
        layout.addWidget(self.mode_label)
        
        self.data_label = QLabel("数据: 0点")
        layout.addWidget(self.data_label)
        
        self.fps_label = QLabel("FPS: 0")
        layout.addWidget(self.fps_label)
        
        self.render_label = QLabel("渲染: Matplotlib 3.10.1")
        layout.addWidget(self.render_label)
        
        layout.addStretch()
        return group
    
    def add_pitch_data(self, pitch_data):
        """添加音高数据"""
        try:
            time_val = pitch_data.get('time', time.time())
            pitch_val = pitch_data.get('pitch', 0)
            confidence = pitch_data.get('confidence', 1.0)
            
            if pitch_val > 0:
                self.time_data.append(time_val)
                self.pitch_data.append(pitch_val)
                self.confidence_data.append(confidence)
                
                # 更新显示
                self.update_visualization()
                
                # FPS统计
                self.update_count += 1
                
        except Exception as e:
            print(f"添加数据错误: {e}")
    
    def update_visualization(self):
        """更新可视化"""
        if len(self.time_data) == 0:
            return
        
        try:
            mode = self.mode_combo.currentText()
            
            if mode in ("普通模式", "心电图模式"):
                self.render_ecg_mode()
            elif mode == "彩色渐变":
                self.render_color_gradient()
            elif mode == "高性能渐变":
                self.render_performance_gradient()
            elif mode == "分段彩色":
                self.render_segmented_colors()
            elif mode == "光谱渐变":
                self.render_spectrum_gradient()
            
            # 更新画布
            self.canvas.draw_idle()
            
            # 更新状态
            self.update_status()
            
        except Exception as e:
            print(f"更新可视化错误: {e}")
            import traceback
            traceback.print_exc()
    
    def render_ecg_mode(self):
        """渲染心电图模式"""
        # 清除渐变集合
        self.clear_gradient_collections()
        
        # 更新主线条
        times = list(self.time_data)
        pitches = list(self.pitch_data)
        
        self.main_line.set_data(times, pitches)
        self.main_line.set_color('#00FF44')
        self.main_line.set_linewidth(1.0)  # 细线条
        self.main_line.set_alpha(1.0)
        self.main_line.set_visible(True)
        
        # 移除高亮点
        if self.highlight_scatter is not None:
            self.highlight_scatter.remove()
            self.highlight_scatter = None
    
    def render_color_gradient(self):
        """渲染彩色渐变模式 - 真正的彩色渐变实现"""
        print(f"🌈 渲染彩色渐变模式，数据点: {len(self.time_data)}")
        
        # 隐藏主线条
        self.main_line.set_visible(False)
        
        # 清除旧的渐变
        self.clear_gradient_collections()
        
        if len(self.time_data) < 2:
            return
        
        times = np.array(self.time_data)
        pitches = np.array(self.pitch_data)
        
        try:
            # 获取质量设置
            quality = self.quality_combo.currentText()
            if quality == "性能优先":
                segments = min(len(times) - 1, 8)
            elif quality == "平衡":
                segments = min(len(times) - 1, 15)
            elif quality == "质量优先":
                segments = min(len(times) - 1, 25)
            else:  # 极致效果
                segments = min(len(times) - 1, 40)
            
            print(f"创建 {segments} 个彩色渐变段")
            
            # 方法1: 使用scatter plot实现真正的彩色渐变
            # 为每个数据点分配颜色
            colors = []
            sizes = []
            alphas = []
            
            for i, pitch in enumerate(pitches):
                # 根据音高计算颜色（HSV色彩空间）
                hue = ((pitch - 1) % 6) / 6  # 将音高映射到0-1的色相
                saturation = 0.8
                value = 0.9
                
                # 转换HSV到RGB
                rgb = colorsys.hsv_to_rgb(hue, saturation, value)
                hex_color = '#%02x%02x%02x' % (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
                colors.append(hex_color)
                
                # 计算大小和透明度（拖尾效果）
                progress = i / len(pitches)
                size = 5 + 15 * progress  # 从5到20的大小变化
                alpha = 0.3 + 0.7 * progress  # 从0.3到1.0的透明度变化
                
                sizes.append(size)
                alphas.append(alpha)
            
            # 创建散点图（彩色点）
            for i in range(0, len(times), max(1, len(times)//200)):  # 控制点密度
                scatter = self.ax.scatter([times[i]], [pitches[i]], 
                                        c=[colors[i]], s=sizes[i], alpha=alphas[i],
                                        zorder=10, edgecolors='none')
                self.gradient_collections.append(scatter)
            
            # 方法2: 线段渐变
            for i in range(segments):
                start_idx = int(i * (len(times) - 1) / segments)
                end_idx = int((i + 1) * (len(times) - 1) / segments) + 1
                
                if start_idx >= len(times) or end_idx > len(times) or start_idx == end_idx:
                    continue
                
                # 提取段数据
                segment_times = times[start_idx:end_idx]
                segment_pitches = pitches[start_idx:end_idx]
                
                if len(segment_times) < 2:
                    continue
                
                # 计算段的平均音高
                avg_pitch = np.mean(segment_pitches)
                
                # 根据音高计算颜色
                hue = ((avg_pitch - 1) % 6) / 6
                rgb = colorsys.hsv_to_rgb(hue, 0.9, 1.0)
                color = '#%02x%02x%02x' % (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
                
                # 计算透明度和线宽（拖尾效果）
                alpha = 0.4 + 0.6 * (i / segments)
                linewidth = 1.0 + 2.5 * (i / segments)
                
                # 绘制线段
                line, = self.ax.plot(segment_times, segment_pitches, 
                                   color=color, alpha=alpha, linewidth=linewidth,
                                   solid_capstyle='round', zorder=5+i)
                
                self.gradient_collections.append(line)
            
            # 添加高亮点（最新位置）
            if len(times) > 0:
                latest_time = times[-1]
                latest_pitch = pitches[-1]
                
                # 计算最新点的颜色
                hue = ((latest_pitch - 1) % 6) / 6
                rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                color = '#%02x%02x%02x' % (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
                
                # 移除旧的高亮点
                if self.highlight_scatter is not None:
                    self.highlight_scatter.remove()
                
                # 创建新的高亮点（带光晕效果）
                # 外圈光晕
                glow = self.ax.scatter([latest_time], [latest_pitch],
                                     s=150, c=color, alpha=0.3,
                                     edgecolors='white', linewidths=1,
                                     zorder=95)
                self.gradient_collections.append(glow)
                
                # 内圈高亮
                self.highlight_scatter = self.ax.scatter([latest_time], [latest_pitch],
                                                       s=80, c=color, alpha=0.9,
                                                       edgecolors='white', linewidths=2,
                                                       zorder=100)
            
            print(f"✅ 彩色渐变模式：创建了 {len(self.gradient_collections)} 个彩色元素")
            
        except Exception as e:
            print(f"❌ 彩色渐变渲染失败: {e}")
            import traceback
            traceback.print_exc()
            # 回退到基本线条
            self.fallback_to_basic_line()
    
    def render_performance_gradient(self):
        """高性能渐变模式"""
        print("⚡ 渲染高性能渐变模式")
        
        self.main_line.set_visible(False)
        self.clear_gradient_collections()
        
        if len(self.time_data) < 2:
            return
        
        times = np.array(self.time_data)
        pitches = np.array(self.pitch_data)
        
        # 简化的渐变：只使用5个段
        num_segments = min(5, len(times) - 1)
        
        for i in range(num_segments):
            start_idx = int(i * (len(times) - 1) / num_segments)
            end_idx = int((i + 1) * (len(times) - 1) / num_segments) + 1
            
            segment_times = times[start_idx:end_idx]
            segment_pitches = pitches[start_idx:end_idx]
            
            if len(segment_times) < 2:
                continue
            
            # 计算平均音高
            avg_pitch = np.mean(segment_pitches)
            color = self.get_pitch_color(avg_pitch)
            
            # 透明度和线宽
            alpha = 0.4 + 0.6 * (i / num_segments)
            linewidth = 1.5 + 2.5 * (i / num_segments)
            
            # 直接绘制线条
            line, = self.ax.plot(segment_times, segment_pitches, 
                               color=color, alpha=alpha, linewidth=linewidth,
                               solid_capstyle='round')
            
            # 存储以便清理
            self.gradient_collections.append(line)
    
    def render_segmented_colors(self):
        """分段彩色模式"""
        print("🎨 渲染分段彩色模式")
        
        self.main_line.set_visible(False)
        self.clear_gradient_collections()
        
        if len(self.time_data) < 2:
            return
        
        times = np.array(self.time_data)
        pitches = np.array(self.pitch_data)
        
        # 按音高高度分段着色
        segments = []
        current_segment = {'times': [], 'pitches': [], 'color': None}
        
        for i, (t, p) in enumerate(zip(times, pitches)):
            color = self.get_pitch_color(p)
            
            if current_segment['color'] is None:
                current_segment['color'] = color
            
            if color == current_segment['color']:
                current_segment['times'].append(t)
                current_segment['pitches'].append(p)
            else:
                # 保存当前段
                if len(current_segment['times']) > 1:
                    segments.append(current_segment.copy())
                
                # 开始新段
                current_segment = {'times': [t], 'pitches': [p], 'color': color}
        
        # 添加最后一段
        if len(current_segment['times']) > 1:
            segments.append(current_segment)
        
        # 绘制各段
        for segment in segments:
            line, = self.ax.plot(segment['times'], segment['pitches'],
                               color=segment['color'], linewidth=2.5,
                               alpha=0.8, solid_capstyle='round')
            self.gradient_collections.append(line)
    
    def render_spectrum_gradient(self):
        """光谱渐变模式"""
        print("🌈 渲染光谱渐变模式")
        
        self.main_line.set_visible(False)
        self.clear_gradient_collections()
        
        if len(self.time_data) < 2:
            return
        
        times = np.array(self.time_data)
        pitches = np.array(self.pitch_data)
        
        # 使用scatter plot创建点渐变
        colors = [self.get_pitch_color(p) for p in pitches]
        
        # 创建散点图
        scatter = self.ax.scatter(times, pitches, c=colors, s=20, alpha=0.7)
        self.gradient_collections.append(scatter)
        
        # 添加连接线（细线）
        line, = self.ax.plot(times, pitches, color='white', alpha=0.3, linewidth=0.5)
        self.gradient_collections.append(line)
    
    def get_pitch_color(self, pitch):
        """根据音高获取颜色"""
        # 将音高映射到色相 (0-360度)
        hue = ((pitch - 1) % 6) / 6  # 6个八度范围
        
        # 使用HSV颜色空间创建彩虹效果
        rgb = colorsys.hsv_to_rgb(hue, 0.8, 1.0)
        
        # 转换为十六进制
        return '#%02x%02x%02x' % (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
    
    def clear_gradient_collections(self):
        """清除所有渐变集合"""
        for collection in self.gradient_collections:
            try:
                if hasattr(collection, 'remove'):
                    collection.remove()
                else:
                    # 对于LineCollection等
                    collection.set_visible(False)
            except:
                pass
        
        self.gradient_collections.clear()
    
    def fallback_to_basic_line(self):
        """回退到基本线条"""
        print("⚠️ 回退到基本线条显示")
        times = list(self.time_data)
        pitches = list(self.pitch_data)
        
        self.main_line.set_data(times, pitches)
        self.main_line.set_color('#00FF44')
        self.main_line.set_linewidth(2.0)
        self.main_line.set_alpha(1.0)
        self.main_line.set_visible(True)
    
    def force_redraw(self):
        """强制重绘"""
        print("🔄 强制重绘画布")
        
        # 清除所有内容
        self.ax.clear()
        
        # 重新设置
        self.setup_matplotlib()
        
        # 重新渲染
        if len(self.time_data) > 0:
            self.update_visualization()
    
    def on_mode_changed(self, mode):
        """模式改变"""
        self.display_mode = mode
        self.mode_label.setText(f"模式: {mode}")
        print(f"🔄 切换到: {mode}")
        self.update_visualization()
    
    def on_quality_changed(self, quality):
        """质量改变"""
        print(f"🎯 渐变质量: {quality}")
        self.update_visualization()
    
    def on_time_changed(self, value):
        """时间窗口改变"""
        self.time_window = value / 10.0
        self.time_label.setText(f"{self.time_window:.1f}s")
        
        # 更新X轴
        if len(self.time_data) > 0:
            latest_time = self.time_data[-1]
            self.ax.set_xlim(latest_time - self.time_window, latest_time)
        else:
            self.ax.set_xlim(0, self.time_window)
        
        self.canvas.draw_idle()
    
    def on_detail_changed(self, value):
        """细节级别改变"""
        levels = ["最低", "很低", "低", "中低", "中等", "中高", "高", "很高", "最高", "极致"]
        self.detail_label.setText(levels[value-1])
        self.update_visualization()
    
    def clear_data(self):
        """清除数据"""
        self.time_data.clear()
        self.pitch_data.clear()
        self.confidence_data.clear()
        
        self.main_line.set_data([], [])
        self.clear_gradient_collections()
        
        if self.highlight_scatter is not None:
            self.highlight_scatter.remove()
            self.highlight_scatter = None
        
        self.canvas.draw()
        self.update_status()
        print("🗑️ 数据已清除")
    
    def load_vibrato_test(self):
        """加载颤音测试数据"""
        print("🎵 加载颤音测试数据")
        self.clear_data()
        
        # 生成测试数据
        duration = 8.0
        sample_rate = 50
        times = np.linspace(0, duration, int(duration * sample_rate))
        
        # 基础音高
        base_pitch = 4.0
        
        # 主旋律变化
        melody = 1.0 * np.sin(2 * np.pi * 0.3 * times)
        
        # 颤音效果
        vibrato = 0.2 * np.sin(2 * np.pi * 6 * times)
        
        # 微小噪声
        noise = 0.05 * np.random.random(len(times))
        
        pitches = base_pitch + melody + vibrato + noise
        confidences = 0.8 + 0.2 * np.random.random(len(times))
        
        # 模拟实时添加
        for t, p, c in zip(times, pitches, confidences):
            self.add_pitch_data({
                'time': t,
                'pitch': p,
                'confidence': c
            })
        
        print("✅ 颤音测试数据加载完成")
    
    def test_gradient_modes(self):
        """测试所有渐变模式"""
        print("🌈 测试所有渐变模式")
        
        modes = ["彩色渐变", "高性能渐变", "分段彩色", "光谱渐变"]
        
        for mode in modes:
            print(f"  测试 {mode}...")
            self.mode_combo.setCurrentText(mode)
            QApplication.processEvents()
            time.sleep(1)  # 暂停1秒观察效果
        
        print("✅ 渐变模式测试完成")
    
    def update_status(self):
        """更新状态"""
        # 数据统计
        data_count = len(self.time_data)
        self.data_label.setText(f"数据: {data_count}点")
        
        # FPS计算
        current_time = time.time()
        if current_time - self.last_fps_time >= 1.0:
            self.fps = self.update_count / (current_time - self.last_fps_time)
            self.fps_label.setText(f"FPS: {self.fps:.1f}")
            self.last_fps_time = current_time
            self.update_count = 0


def test_improved_matplotlib():
    """测试改进的Matplotlib可视化器"""
    app = QApplication(sys.argv)
    
    print("🚀 启动改进的Matplotlib彩色渐变可视化器")
    print("🎯 专门解决Matplotlib 3.10.1的渐变兼容性问题")
    
    try:
        visualizer = ImprovedMatplotlibVisualizer()
        visualizer.show()
        
        print("\n💡 测试说明:")
        print("  🎵 点击'测试颤音'加载测试数据")
        print("  🌈 点击'测试渐变'循环测试所有模式")
        print("  🔄 点击'强制刷新'解决显示问题")
        print("  🎛️ 调整'渐变质量'优化性能")
        print("\n🎯 重点验证:")
        print("  • 彩色渐变模式是否正常显示")
        print("  • 心电图模式线条是否够细")
        print("  • 各种渐变效果的稳定性")
        
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_improved_matplotlib()
