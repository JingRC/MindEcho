#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于PyQtGraph的实时音高可视化器
解决Matplotlib彩色渐变模式的兼容性问题
"""

import sys
import os
import numpy as np
from collections import deque
import time

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

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

class PyQtGraphPitchVisualizer(QWidget):
    """基于PyQtGraph的高性能音高可视化器"""
    
    def __init__(self):
        super().__init__()
        
        # 检查PyQtGraph可用性
        if not PYQTGRAPH_AVAILABLE:
            raise ImportError("需要安装 pyqtgraph: pip install pyqtgraph")
        
        # 数据存储
        self.max_points = 3000  # 最大数据点数
        self.time_data = deque(maxlen=self.max_points)
        self.pitch_data = deque(maxlen=self.max_points)
        self.confidence_data = deque(maxlen=self.max_points)

        # 显示参数
        self.time_window = 10.0  # 时间窗口（秒）
        self.y_range = [1.0, 7.0]  # 音高范围（八度）
        # 默认显示模式（原“心电图模式”统一更名为“普通模式”）
        self.display_mode = "普通模式"

        # 颜色方案
        self.colors = {
            'background': '#1a1a1a',
            'grid': '#404040',
            'text': '#ffffff',
            'ecg_line': '#00FF44',
            'gradient_colors': [
                '#0066FF',  # 低音-蓝色
                '#00FF66',  # 中低音-青绿
                '#AADD00',  # 中音-黄绿
                '#FF9900',  # 中高音-橙色
                '#FF0000'   # 高音-红色
            ]
        }
        
        # 初始化界面
        self.init_ui()
        self.setup_plot()
        
        # 渐变线条存储
        self.gradient_lines = []
        self.highlight_point = None
        
        print("✅ PyQtGraph 音高可视化器初始化完成")
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("PyQtGraph 高性能音高可视化")
        self.setGeometry(100, 100, 1200, 800)
        
        # 设置深色主题
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {self.colors['background']};
                color: {self.colors['text']};
            }}
            QGroupBox {{
                border: 2px solid {self.colors['grid']};
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }}
            QPushButton {{
                background-color: #404040;
                border: 2px solid #606060;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #505050;
            }}
            QComboBox {{
                background-color: #404040;
                border: 1px solid #606060;
                border-radius: 3px;
                padding: 5px;
                min-width: 120px;
            }}
            QSlider::groove:horizontal {{
                background: #404040;
                height: 8px;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: #00FF44;
                border: 1px solid #00AA00;
                width: 18px;
                border-radius: 9px;
                margin-top: -5px;
                margin-bottom: -5px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        
        # 控制面板
        control_panel = self.create_control_panel()
        layout.addWidget(control_panel)
        
        # 绘图区域
        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)
        
        # 状态面板
        status_panel = self.create_status_panel()
        layout.addWidget(status_panel)
    
    def create_control_panel(self):
        """创建控制面板"""
        group = QGroupBox("显示控制")
        layout = QHBoxLayout(group)
        
        # 显示模式选择
        layout.addWidget(QLabel("显示模式:"))
        self.mode_combo = QComboBox()
        # 统一名称：将“心电图模式”改为“普通模式”
        self.mode_combo.addItems(["普通模式", "彩色渐变", "频谱模式", "3D渐变"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        layout.addWidget(self.mode_combo)
        
        # 时间窗口控制
        layout.addWidget(QLabel("时间窗口:"))
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(30, 300)  # 3-30秒
        self.time_slider.setValue(100)  # 默认10秒
        self.time_slider.valueChanged.connect(self.on_time_window_changed)
        layout.addWidget(self.time_slider)
        
        self.time_label = QLabel("10.0s")
        layout.addWidget(self.time_label)
        
        # 清除数据按钮
        clear_btn = QPushButton("清除数据")
        clear_btn.clicked.connect(self.clear_data)
        layout.addWidget(clear_btn)
        
        # 测试数据按钮
        test_btn = QPushButton("加载测试数据")
        test_btn.clicked.connect(self.load_test_data)
        layout.addWidget(test_btn)
        
        layout.addStretch()
        return group
    
    def create_status_panel(self):
        """创建状态面板"""
        group = QGroupBox("状态信息")
        layout = QHBoxLayout(group)
        
        self.status_label = QLabel("状态: 就绪")
        layout.addWidget(self.status_label)
        
        self.data_count_label = QLabel("数据点: 0")
        layout.addWidget(self.data_count_label)
        
        self.performance_label = QLabel("性能: 优秀")
        layout.addWidget(self.performance_label)
        
        layout.addStretch()
        return group
    
    def setup_plot(self):
        """设置绘图区域"""
        # 设置背景和网格
        self.plot_widget.setBackground(self.colors['background'])
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        # 设置标签
        self.plot_widget.setLabel('left', '音高 (八度)', color=self.colors['text'])
        self.plot_widget.setLabel('bottom', '时间 (秒)', color=self.colors['text'])
        
        # 设置范围
        self.plot_widget.setXRange(0, self.time_window)
        self.plot_widget.setYRange(*self.y_range)
        
        # 创建主线条
        self.main_curve = self.plot_widget.plot([], [], 
                                               pen=pg.mkPen(color=self.colors['ecg_line'], width=2),
                                               name="音高线")
        
        # 音名标注
        self.setup_note_labels()
        
        print("✅ PyQtGraph 绘图区域设置完成")
    
    def setup_note_labels(self):
        """设置音名标注"""
        # 清除旧标注
        for item in self.plot_widget.listDataItems():
            if hasattr(item, 'note_label'):
                self.plot_widget.removeItem(item)
        
        # 添加音名标注
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        for octave in range(1, 8):
            for i, note in enumerate(note_names):
                y_pos = octave + i / 12
                if self.y_range[0] <= y_pos <= self.y_range[1]:
                    # 创建文本标注
                    text = pg.TextItem(f"{note}{octave}", 
                                     color=self.colors['text'], 
                                     anchor=(0, 0.5))
                    text.setPos(-0.5, y_pos)
                    text.note_label = True
                    self.plot_widget.addItem(text)
    
    def add_pitch_data(self, pitch_data):
        """添加音高数据"""
        try:
            time_val = pitch_data.get('time', time.time())
            pitch_val = pitch_data.get('pitch', 0)
            confidence = pitch_data.get('confidence', 1.0)
            
            if pitch_val > 0:  # 只添加有效音高
                self.time_data.append(time_val)
                self.pitch_data.append(pitch_val)
                self.confidence_data.append(confidence)
                
                # 更新显示
                self.update_display()
        
        except Exception as e:
            print(f"添加音高数据错误: {e}")
    
    def update_display(self):
        """更新显示"""
        if len(self.time_data) == 0:
            return
        
        try:
            # 转换为numpy数组以提高性能
            times = np.array(self.time_data)
            pitches = np.array(self.pitch_data)
            confidences = np.array(self.confidence_data)
            
            # 根据显示模式更新
            mode = self.mode_combo.currentText()
            # 兼容旧配置：同时识别“心电图模式”
            if mode in ("普通模式", "心电图模式"):
                self.update_ecg_mode(times, pitches, confidences)
            elif mode == "彩色渐变":
                self.update_gradient_mode(times, pitches, confidences)
            elif mode == "频谱模式":
                self.update_spectrum_mode(times, pitches, confidences)
            elif mode == "3D渐变":
                self.update_3d_gradient_mode(times, pitches, confidences)
            
            # 更新状态
            self.update_status()
            
        except Exception as e:
            print(f"更新显示错误: {e}")
    
    def update_ecg_mode(self, times, pitches, confidences):
        """普通模式 - 细线条显示（原心电图模式）"""
        print("✅ 更新普通模式")
        
        # 设置细线条
        pen = pg.mkPen(color=self.colors['ecg_line'], width=1.0)  # 细线条
        self.main_curve.setData(times, pitches, pen=pen)
        
        # 清除渐变效果
        self.clear_gradient_lines()
    
    def update_gradient_mode(self, times, pitches, confidences):
        """彩色渐变模式 - PyQtGraph实现"""
        print(f"🌈 更新彩色渐变模式，数据点: {len(times)}")
        
        # 清除旧的渐变线条
        self.clear_gradient_lines()
        
        if len(times) < 2:
            return
        
        # 创建分段渐变线条
        num_segments = min(len(times) - 1, 20)  # 最多20段
        
        for i in range(num_segments):
            # 计算当前段的索引范围
            start_idx = int(i * (len(times) - 1) / num_segments)
            end_idx = int((i + 1) * (len(times) - 1) / num_segments) + 1
            
            if start_idx >= len(times) or end_idx > len(times):
                continue
            
            # 提取段数据
            segment_times = times[start_idx:end_idx]
            segment_pitches = pitches[start_idx:end_idx]
            
            if len(segment_pitches) == 0:
                continue
            
            # 计算颜色（基于音高）
            avg_pitch = np.mean(segment_pitches)
            color = self.get_pitch_color(avg_pitch)
            
            # 计算透明度和线宽（拖尾效果）
            alpha = int(120 + 135 * (i / num_segments))  # 120-255
            width = 1.5 + 3.5 * (i / num_segments)  # 1.5-5.0
            
            # 创建颜色对象
            color_obj = QColor(color)
            color_obj.setAlpha(alpha)
            
            # 创建画笔
            pen = pg.mkPen(color=color_obj, width=width)
            
            # 创建线条
            try:
                curve = self.plot_widget.plot(segment_times, segment_pitches, pen=pen)
                self.gradient_lines.append(curve)
                print(f"✅ 渐变段 {i+1}/{num_segments} 创建成功")
            except Exception as e:
                print(f"❌ 渐变段 {i+1} 创建失败: {e}")
        
        # 添加高亮点
        if len(times) > 0:
            latest_time = times[-1]
            latest_pitch = pitches[-1]
            color = self.get_pitch_color(latest_pitch)
            
            # 移除旧的高亮点
            if self.highlight_point is not None:
                try:
                    self.plot_widget.removeItem(self.highlight_point)
                except:
                    pass
            
            # 创建新的高亮点
            self.highlight_point = self.plot_widget.plot([latest_time], [latest_pitch],
                                                        pen=None,
                                                        symbol='o',
                                                        symbolSize=15,
                                                        symbolBrush=color,
                                                        symbolPen=pg.mkPen('white', width=2))
        
        print(f"🎨 彩色渐变模式更新完成，共创建 {len(self.gradient_lines)} 条线段")
    
    def update_spectrum_mode(self, times, pitches, confidences):
        """频谱模式"""
        print("📊 更新频谱模式")
        
        # 根据置信度调整颜色
        if len(confidences) > 0:
            avg_confidence = np.mean(confidences)
            alpha = int(100 + 155 * avg_confidence)
            color = QColor(self.colors['ecg_line'])
            color.setAlpha(alpha)
            pen = pg.mkPen(color=color, width=2)
            self.main_curve.setData(times, pitches, pen=pen)
        
        self.clear_gradient_lines()
    
    def update_3d_gradient_mode(self, times, pitches, confidences):
        """3D渐变模式 (模拟3D效果)"""
        print("🎭 更新3D渐变模式")
        
        self.clear_gradient_lines()
        
        if len(times) < 2:
            return
        
        # 创建多层线条模拟3D效果
        for layer in range(3):
            offset = layer * 0.02  # 时间偏移
            alpha = 255 - layer * 80  # 透明度递减
            width = 4 - layer * 1  # 线宽递减
            
            layer_times = times + offset
            
            color = QColor(self.colors['ecg_line'])
            color.setAlpha(alpha)
            pen = pg.mkPen(color=color, width=width)
            
            curve = self.plot_widget.plot(layer_times, pitches, pen=pen)
            self.gradient_lines.append(curve)
    
    def get_pitch_color(self, pitch):
        """根据音高获取颜色"""
        if pitch < 2:
            return '#0066FF'  # 低音-蓝色
        elif pitch < 3.5:
            return '#00FF66'  # 中低音-青绿
        elif pitch < 5:
            return '#AADD00'  # 中音-黄绿
        elif pitch < 6.5:
            return '#FF9900'  # 中高音-橙色
        else:
            return '#FF0000'  # 高音-红色
    
    def clear_gradient_lines(self):
        """清除渐变线条"""
        for curve in self.gradient_lines:
            try:
                self.plot_widget.removeItem(curve)
            except:
                pass
        self.gradient_lines.clear()
        
        # 清除高亮点
        if self.highlight_point is not None:
            try:
                self.plot_widget.removeItem(self.highlight_point)
            except:
                pass
            self.highlight_point = None
    
    def on_mode_changed(self, mode):
        """显示模式改变"""
        self.display_mode = mode
        print(f"🔄 切换到: {mode}")
        self.update_display()
    
    def on_time_window_changed(self, value):
        """时间窗口改变"""
        self.time_window = value / 10.0  # 3-30秒
        self.time_label.setText(f"{self.time_window:.1f}s")
        
        # 更新X轴范围
        if len(self.time_data) > 0:
            latest_time = self.time_data[-1]
            self.plot_widget.setXRange(latest_time - self.time_window, latest_time)
        else:
            self.plot_widget.setXRange(0, self.time_window)
    
    def clear_data(self):
        """清除所有数据"""
        self.time_data.clear()
        self.pitch_data.clear()
        self.confidence_data.clear()
        
        self.main_curve.setData([], [])
        self.clear_gradient_lines()
        
        self.update_status()
        print("🗑️ 数据已清除")
    
    def load_test_data(self):
        """加载测试数据"""
        print("📊 加载测试数据...")
        
        # 清除旧数据
        self.clear_data()
        
        # 生成颤音测试数据
        duration = 8.0
        sample_rate = 60
        times = np.linspace(0, duration, int(duration * sample_rate))
        
        # 基础音高
        base_pitch = 4.0
        
        # 主旋律
        melody = 0.8 * np.sin(2 * np.pi * 0.2 * times)
        
        # 颤音
        vibrato = 0.15 * np.sin(2 * np.pi * 6.0 * times)
        
        # 组合
        pitches = base_pitch + melody + vibrato
        confidences = 0.8 + 0.2 * np.random.random(len(times))
        
        # 逐步添加数据
        for i, (t, p, c) in enumerate(zip(times, pitches, confidences)):
            self.add_pitch_data({
                'time': t,
                'pitch': p,
                'confidence': c
            })
            
            # 每50个点更新一次界面
            if i % 50 == 0:
                QApplication.processEvents()
        
        print("✅ 测试数据加载完成")
    
    def update_status(self):
        """更新状态信息"""
        data_count = len(self.time_data)
        self.data_count_label.setText(f"数据点: {data_count}")
        
        # 性能评估
        if data_count < 1000:
            performance = "优秀"
        elif data_count < 2000:
            performance = "良好"
        else:
            performance = "一般"
        
        self.performance_label.setText(f"性能: {performance}")
        
        # 状态信息
        mode = self.mode_combo.currentText()
        self.status_label.setText(f"状态: {mode} - {data_count}点")


def test_pyqtgraph_visualizer():
    """测试PyQtGraph可视化器"""
    app = QApplication(sys.argv)
    
    try:
        # 创建可视化器
        visualizer = PyQtGraphPitchVisualizer()
        visualizer.show()
        
        print("🚀 PyQtGraph 音高可视化器启动成功")
        print("💡 测试说明:")
        print("  • 点击'加载测试数据'查看效果")
        print("  • 切换显示模式对比不同效果")
        print("  • 特别观察彩色渐变模式的流畅效果")
        
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_pyqtgraph_visualizer()
