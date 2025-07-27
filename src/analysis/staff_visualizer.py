"""
音乐谱线可视化模块
实时生成和显示音高谱线
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.patches import Rectangle, Circle
import matplotlib.patches as patches
from collections import deque
import time

# 设置中文字体支持
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial Unicode MS', 'Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 全局变量控制是否使用ASCII符号替代Unicode音乐符号
USE_ASCII_SYMBOLS = True

try:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout
    from PyQt6.QtCore import QTimer
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    PYQT_AVAILABLE = True
except ImportError:
    try:
        from PyQt5.QtWidgets import QWidget, QVBoxLayout
        from PyQt5.QtCore import QTimer
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure
        PYQT_AVAILABLE = True
    except ImportError:
        PYQT_AVAILABLE = False
        print("PyQt不可用，将使用matplotlib独立显示")

class StaffRenderer:
    """五线谱渲染器"""
    
    def __init__(self, width=800, height=400):
        self.width = width
        self.height = height
        
        # 五线谱参数
        self.staff_lines = 5
        self.line_spacing = 20  # 线间距离
        self.staff_y_center = height // 2
        
        # 音符映射到五线谱位置
        self.note_positions = self._create_note_position_map()
        
    def _create_note_position_map(self):
        """创建音符到五线谱位置的映射"""
        # 以高音谱号为例，中央C在第一条加线下方
        positions = {}
        
        # 基准线位置 (五线谱的中间线是第3线)
        middle_line_y = self.staff_y_center
        
        # C4 (中央C) 在第一条加线下方
        base_position = middle_line_y + 6 * self.line_spacing // 2
        
        # 音符名称和相对位置
        note_offsets = {
            'C': 0, 'D': -1, 'E': -2, 'F': -3, 'G': -4, 'A': -5, 'B': -6
        }
        
        # 生成多个八度的位置
        for octave in range(2, 8):  # C2 到 B7
            for note, offset in note_offsets.items():
                octave_offset = (octave - 4) * 7  # 每个八度7个位置
                total_offset = offset + octave_offset
                y_position = base_position + total_offset * (self.line_spacing // 2)
                
                positions[f"{note}{octave}"] = y_position
        
        return positions
    
    def draw_staff_lines(self, ax):
        """绘制五线谱线"""
        ax.clear()
        ax.set_xlim(0, self.width)
        ax.set_ylim(0, self.height)
        ax.set_aspect('equal')
        
        # 绘制五线谱的五条线
        staff_top = self.staff_y_center - 2 * self.line_spacing
        
        for i in range(self.staff_lines):
            y = staff_top + i * self.line_spacing
            ax.axhline(y=y, color='black', linewidth=1.5, alpha=0.8)
        
        # 绘制中央C的加线
        central_c_y = self.staff_y_center + 3 * self.line_spacing
        ax.plot([self.width * 0.1, self.width * 0.9], [central_c_y, central_c_y], 
               color='black', linewidth=1, alpha=0.6, linestyle='--')
        
        # 添加谱号 (简化版高音谱号标记)
        ax.text(20, self.staff_y_center, '𝄞', fontsize=40, color='black', 
               verticalalignment='center')
        
        # 移除坐标轴
        ax.set_xticks([])
        ax.set_yticks([])
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_visible(False)
    
    def get_note_y_position(self, note_name, octave):
        """获取音符在五线谱上的Y坐标"""
        note_key = f"{note_name}{octave}"
        
        # 处理升降号 - 使用基本音名的位置
        base_note = note_name[0]
        base_key = f"{base_note}{octave}"
        
        return self.note_positions.get(base_key, self.staff_y_center)
    
    def draw_note(self, ax, x, note_name, octave, note_type='quarter', color='black'):
        """
        在指定位置绘制音符
        note_type: 'quarter', 'eighth', 'half', 'whole'
        """
        y = self.get_note_y_position(note_name, octave)
        
        # 绘制符头
        if note_type == 'whole':
            # 全音符 - 空心椭圆
            ellipse = patches.Ellipse((x, y), 15, 10, facecolor='white', 
                                    edgecolor=color, linewidth=2)
            ax.add_patch(ellipse)
        else:
            # 其他音符 - 实心椭圆
            ellipse = patches.Ellipse((x, y), 12, 8, facecolor=color, 
                                    edgecolor=color)
            ax.add_patch(ellipse)
        
        # 绘制符干
        if note_type != 'whole':
            stem_height = 60
            if y < self.staff_y_center:  # 高音区，符干向下
                ax.plot([x + 6, x + 6], [y, y + stem_height], 
                       color=color, linewidth=2)
            else:  # 低音区，符干向上
                ax.plot([x - 6, x - 6], [y, y - stem_height], 
                       color=color, linewidth=2)
        
        # 绘制符尾 (八分音符等)
        if note_type == 'eighth':
            flag_x = x + 6 if y < self.staff_y_center else x - 6
            flag_y = y + stem_height - 10 if y < self.staff_y_center else y - stem_height + 10
            # 简化的符尾
            ax.text(flag_x, flag_y, '♪', fontsize=12, color=color)
        
        # 绘制升降号
        if len(note_name) > 1:
            accidental_x = x - 20
            if '#' in note_name:
                ax.text(accidental_x, y, '♯', fontsize=16, color=color,
                       verticalalignment='center', horizontalalignment='center')
            elif 'b' in note_name:
                ax.text(accidental_x, y, '♭', fontsize=16, color=color,
                       verticalalignment='center', horizontalalignment='center')

class PitchCurveVisualizer:
    """音高曲线可视化器"""
    
    def __init__(self, width=800, height=200, time_window=10):
        self.width = width
        self.height = height
        self.time_window = time_window  # 显示的时间窗口（秒）
        
        # 频率范围 (对数刻度)
        self.min_freq = 80    # 约 E2
        self.max_freq = 2000  # 约 B6
        
        # 数据存储
        self.times = deque(maxlen=1000)
        self.frequencies = deque(maxlen=1000)
        self.notes = deque(maxlen=1000)
        
    def add_pitch_point(self, time_stamp, frequency, note_info=None):
        """添加音高点"""
        self.times.append(time_stamp)
        self.frequencies.append(frequency)
        self.notes.append(note_info)
    
    def draw_pitch_curve(self, ax):
        """绘制音高曲线"""
        ax.clear()
        
        if len(self.times) < 2:
            ax.set_xlim(0, self.time_window)
            ax.set_ylim(self.min_freq, self.max_freq)
            ax.set_yscale('log')
            ax.set_ylabel('频率 (Hz)')
            ax.set_xlabel('时间 (秒)')
            ax.grid(True, alpha=0.3)
            return
        
        # 获取时间窗口内的数据
        current_time = max(self.times)
        start_time = current_time - self.time_window
        
        # 过滤数据
        filtered_times = []
        filtered_freqs = []
        filtered_notes = []
        
        for t, f, n in zip(self.times, self.frequencies, self.notes):
            if t >= start_time and f is not None:
                filtered_times.append(t - start_time)  # 相对时间
                filtered_freqs.append(f)
                filtered_notes.append(n)
        
        if len(filtered_times) < 2:
            ax.set_xlim(0, self.time_window)
            ax.set_ylim(self.min_freq, self.max_freq)
            ax.set_yscale('log')
            ax.grid(True, alpha=0.3)
            return
        
        # 绘制曲线
        ax.plot(filtered_times, filtered_freqs, 'b-', linewidth=2, alpha=0.8)
        ax.scatter(filtered_times, filtered_freqs, c='red', s=20, alpha=0.6)
        
        # 设置坐标轴
        ax.set_xlim(0, self.time_window)
        ax.set_ylim(self.min_freq, self.max_freq)
        ax.set_yscale('log')
        ax.set_ylabel('频率 (Hz)')
        ax.set_xlabel('时间 (秒)')
        ax.grid(True, alpha=0.3)
        
        # 添加音名标注
        if filtered_notes:
            for i, (t, f, note) in enumerate(zip(filtered_times[-10:], filtered_freqs[-10:], filtered_notes[-10:])):
                if note and i % 2 == 0:  # 每隔一个点标注，避免重叠
                    ax.annotate(f"{note.get('note_name', '')}{note.get('octave', '')}", 
                              (t, f), xytext=(5, 5), textcoords='offset points',
                              fontsize=8, alpha=0.7)
    
    def clear(self):
        """清空数据"""
        self.times.clear()
        self.frequencies.clear()
        self.notes.clear()

class RealTimeStaffWidget(QWidget if PYQT_AVAILABLE else object):
    """实时五线谱显示组件"""
    
    def __init__(self, parent=None):
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt不可用，无法创建Qt组件")
        
        super().__init__(parent)
        self.setup_ui()
        
        # 渲染器
        self.staff_renderer = StaffRenderer()
        self.curve_visualizer = PitchCurveVisualizer()
        
        # 当前音符信息
        self.current_notes = deque(maxlen=50)
        
        # 更新定时器
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(50)  # 20 FPS
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        
        # 创建matplotlib图形
        self.figure = Figure(figsize=(12, 8))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        # 创建子图
        self.staff_ax = self.figure.add_subplot(2, 1, 1)  # 五线谱
        self.curve_ax = self.figure.add_subplot(2, 1, 2)  # 音高曲线
        
        self.figure.tight_layout()
    
    def add_pitch_data(self, time_stamp, frequency, note_info):
        """添加音高数据"""
        # 添加到曲线可视化器
        self.curve_visualizer.add_pitch_point(time_stamp, frequency, note_info)
        
        # 添加音符到当前音符列表
        if note_info:
            self.current_notes.append({
                'time': time_stamp,
                'note_name': note_info.get('note_name'),
                'octave': note_info.get('octave'),
                'frequency': frequency
            })
    
    def update_display(self):
        """更新显示"""
        try:
            # 绘制五线谱
            self.staff_renderer.draw_staff_lines(self.staff_ax)
            
            # 绘制最近的音符
            current_time = time.time()
            display_window = 5  # 显示最近5秒的音符
            
            x_position = 100  # 起始X位置
            x_spacing = 50    # 音符间距
            
            for i, note in enumerate(list(self.current_notes)[-20:]):  # 最近20个音符
                if current_time - note['time'] <= display_window:
                    x = x_position + i * x_spacing
                    if x < self.staff_renderer.width - 50:
                        self.staff_renderer.draw_note(
                            self.staff_ax, x, 
                            note['note_name'], note['octave'],
                            note_type='quarter', 
                            color='blue' if i == len(list(self.current_notes)) - 1 else 'black'
                        )
            
            # 绘制音高曲线
            self.curve_visualizer.draw_pitch_curve(self.curve_ax)
            
            # 刷新画布
            self.canvas.draw()
            
        except Exception as e:
            print(f"显示更新错误: {e}")
    
    def clear_display(self):
        """清空显示"""
        self.current_notes.clear()
        self.curve_visualizer.clear()

class StandaloneStaffVisualizer:
    """独立的五线谱可视化器（不依赖Qt）"""
    
    def __init__(self):
        self.staff_renderer = StaffRenderer()
        self.curve_visualizer = PitchCurveVisualizer()
        
        # 创建matplotlib图形
        self.fig, (self.staff_ax, self.curve_ax) = plt.subplots(2, 1, figsize=(12, 8))
        plt.ion()  # 交互模式
        
        self.current_notes = deque(maxlen=50)
        
    def add_pitch_data(self, time_stamp, frequency, note_info):
        """添加音高数据"""
        self.curve_visualizer.add_pitch_point(time_stamp, frequency, note_info)
        
        if note_info:
            self.current_notes.append({
                'time': time_stamp,
                'note_name': note_info.get('note_name'),
                'octave': note_info.get('octave'),
                'frequency': frequency
            })
    
    def update_display(self):
        """更新显示"""
        # 绘制五线谱
        self.staff_renderer.draw_staff_lines(self.staff_ax)
        
        # 绘制音符
        x_position = 100
        x_spacing = 50
        
        for i, note in enumerate(list(self.current_notes)[-15:]):
            x = x_position + i * x_spacing
            if x < self.staff_renderer.width - 50:
                self.staff_renderer.draw_note(
                    self.staff_ax, x,
                    note['note_name'], note['octave'],
                    color='red' if i == len(list(self.current_notes)) - 1 else 'black'
                )
        
        # 绘制音高曲线
        self.curve_visualizer.draw_pitch_curve(self.curve_ax)
        
        plt.pause(0.01)
    
    def show(self):
        """显示窗口"""
        plt.show()

if __name__ == "__main__":
    # 测试五线谱渲染
    import matplotlib.pyplot as plt
    
    renderer = StaffRenderer()
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # 绘制五线谱
    renderer.draw_staff_lines(ax)
    
    # 测试音符
    test_notes = [
        ('C', 4, 150), ('D', 4, 200), ('E', 4, 250), 
        ('F', 4, 300), ('G', 4, 350), ('A', 4, 400), ('B', 4, 450), ('C', 5, 500)
    ]
    
    for note_name, octave, x in test_notes:
        renderer.draw_note(ax, x, note_name, octave)
    
    plt.title("五线谱音符测试")
    plt.show()
    
    print("五线谱渲染测试完成")
