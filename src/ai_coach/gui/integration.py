"""AI Coach 集成模块 —— 将 AI 声乐教练嵌入 MindEcho 主界面

使用方法：
  在 IntegratedRecordingInterface.init_ui() 末尾添加:
      from src.ai_coach.gui.integration import integrate_ai_coach
      integrate_ai_coach(self)

  或在独立模式运行:
      python -m src.ai_coach.gui.integration
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .coach_panel import AICoachPanel, _QT_AVAILABLE
from .mascot_svg import get_svg, MASCOT_ANIMATION_CSS

if _QT_AVAILABLE:
    from PyQt6.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QSizePolicy,
    )
    from PyQt6.QtCore import Qt, QTimer, QSize
    from PyQt6.QtGui import QIcon, QPixmap, QPainter
    try:
        from PyQt6.QtSvgWidgets import QSvgWidget
        _QT_SVG_AVAILABLE = True
    except ImportError:
        _QT_SVG_AVAILABLE = False
else:
    _QT_SVG_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════
# 桌宠小部件
# ═══════════════════════════════════════════════════════════════


class MascotWidget(QWidget):
    """桌面宠物小部件 —— 显示 AI 教练的当前状态"""

    EXPRESSIONS = ["idle", "singing", "thinking", "happy", "surprised"]

    def __init__(self, size: int = 120, parent=None):
        super().__init__(parent)
        self._size = size
        self._current_expr = "idle"
        self._svg_data: dict[str, str] = {}
        self._load_svgs()

        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if _QT_SVG_AVAILABLE:
            self._svg_widget = QSvgWidget(self)
            self._svg_widget.setFixedSize(size, size)
            self._set_svg("idle")
        else:
            self._label = QLabel(self)
            self._label.setFixedSize(size, size)
            self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._label.setText("🎵")

        self.setToolTip("MindEcho AI 声乐教练 - 麦麦")
        self._anim_timer: Optional[QTimer] = None

    def _load_svgs(self):
        """预加载 SVG 数据"""
        for expr in self.EXPRESSIONS:
            self._svg_data[expr] = get_svg(expr)

    def _set_svg(self, expr: str):
        """设置当前 SVG"""
        svg_bytes = self._svg_data.get(expr, self._svg_data["idle"]).encode("utf-8")
        if _QT_SVG_AVAILABLE and hasattr(self, "_svg_widget"):
            self._svg_widget.load(svg_bytes)
            self._svg_widget.setFixedSize(self._size, self._size)

    def set_expression(self, expr: str):
        """切换表情"""
        if expr not in self.EXPRESSIONS:
            expr = "idle"
        if expr == self._current_expr:
            return
        self._current_expr = expr
        self._set_svg(expr)

    def anim_idle(self):
        """切换到待机状态"""
        self.set_expression("idle")

    def anim_singing(self):
        """切换到唱歌状态（分析中）"""
        self.set_expression("singing")

    def anim_thinking(self):
        """切换到思考状态（LLM 调用中）"""
        self.set_expression("thinking")

    def anim_happy(self, duration_ms: int = 2000):
        """短暂开心动画"""
        self.set_expression("happy")
        if self._anim_timer:
            self._anim_timer.stop()
        self._anim_timer = QTimer(self)
        self._anim_timer.setSingleShot(True)
        self._anim_timer.timeout.connect(self.anim_idle)
        self._anim_timer.start(duration_ms)

    def anim_surprised(self, duration_ms: int = 1500):
        """短暂惊讶动画"""
        self.set_expression("surprised")
        if self._anim_timer:
            self._anim_timer.stop()
        self._anim_timer = QTimer(self)
        self._anim_timer.setSingleShot(True)
        self._anim_timer.timeout.connect(self.anim_idle)
        self._anim_timer.start(duration_ms)

    def mousePressEvent(self, event):
        """点击桌宠时触发交互"""
        self.anim_happy(1500)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════
# AI Coach Dock Panel
# ═══════════════════════════════════════════════════════════════


class AICoachDockPanel(QWidget):
    """AI Coach 完整面板 —— 桌宠 + 对话面板的组合"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 桌宠栏
        mascot_bar = QHBoxLayout()
        self.mascot = MascotWidget(size=80)
        mascot_bar.addWidget(self.mascot)

        mascot_info = QVBoxLayout()
        self.mascot_name = QLabel("麦麦")
        self.mascot_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #A78BFA;")
        self.mascot_status = QLabel("随时准备帮你~")
        self.mascot_status.setStyleSheet("font-size: 11px; color: #888;")
        mascot_info.addWidget(self.mascot_name)
        mascot_info.addWidget(self.mascot_status)
        mascot_bar.addLayout(mascot_info)
        mascot_bar.addStretch()
        layout.addLayout(mascot_bar)

        # AI Coach 对话面板
        self.coach_panel = AICoachPanel(parent=self)

        # 将 Agent 的回调连接到桌宠
        agent = self.coach_panel.agent
        agent._on_thinking = self._on_agent_thinking
        agent._on_response = self._on_agent_response
        agent._on_stream = None  # 使用 panel 自己的流式回调

        layout.addWidget(self.coach_panel)

    def _on_agent_thinking(self):
        self.mascot_status.setText("思考中...")
        self.mascot.anim_thinking()

    def _on_agent_response(self, response: str):
        self.mascot_status.setText("随时准备帮你~")
        self.mascot.anim_happy(2000)


# ═══════════════════════════════════════════════════════════════
# 集成入口
# ═══════════════════════════════════════════════════════════════


def integrate_ai_coach(main_window, dock_area=Qt.DockWidgetArea.RightDockWidgetArea):
    """将 AI 声乐教练面板集成到 MindEcho 主窗口

    Args:
        main_window: IntegratedRecordingInterface 实例
        dock_area: 停靠位置 (默认右侧)

    Returns:
        AICoachDockPanel 实例
    """
    if not _QT_AVAILABLE:
        print("[AI Coach] PyQt 不可用，跳过集成")
        return None

    # 创建停靠面板
    dock = QDockWidget("AI 声乐教练", main_window)
    dock.setObjectName("ai_coach_dock")

    # 创建内容
    panel = AICoachDockPanel(dock)
    dock.setWidget(panel)

    # 设置允许的停靠区域
    dock.setAllowedAreas(
        Qt.DockWidgetArea.LeftDockWidgetArea |
        Qt.DockWidgetArea.RightDockWidgetArea
    )

    # 添加到主窗口
    main_window.addDockWidget(dock_area, dock)

    # 设置默认尺寸
    dock.setMinimumWidth(380)
    dock.resize(420, 700)

    # 设置样式
    dock.setStyleSheet("""
        QDockWidget {
            color: #e0e0e0;
            font-size: 13px;
        }
        QDockWidget::title {
            background-color: #2a2a4a;
            padding: 8px;
            border-bottom: 2px solid #5B3FD9;
        }
    """)

    # 连接数据管道 —— 当主窗口有新的音高数据时更新 Agent 上下文
    _connect_data_pipeline(main_window, panel)

    print("[AI Coach] 集成完成 - 面板已添加到主窗口")
    return panel


def _connect_data_pipeline(main_window, panel: AICoachDockPanel):
    """连接 MindEcho 音高数据管道到 AI Coach"""
    agent = panel.coach_panel.agent

    # Hook: 每次录音保存时，自动加载分析数据到 Agent
    original_save = getattr(main_window, '_save_recording_data', None)
    if original_save is None:
        # 尝试其他可能的保存方法
        for attr_name in ['save_recording', '_on_recording_stopped', '_finish_recording']:
            if hasattr(main_window, attr_name):
                original_save = getattr(main_window, attr_name)
                break

    if original_save:
        def _hooked_save(*args, **kwargs):
            result = original_save(*args, **kwargs)
            # 延迟加载分析数据（等文件写入完成）
            QTimer.singleShot(500, lambda: _auto_load_analysis(main_window, agent))
            return result

        # 尝试替换方法
        for attr_name in ['save_recording', '_on_recording_stopped', '_finish_recording']:
            if hasattr(main_window, attr_name):
                try:
                    setattr(main_window, attr_name, _hooked_save)
                    print(f"[AI Coach] 已连接到录音保存管道: {attr_name}")
                    break
                except Exception:
                    pass

    # Hook: 可视化器的音高数据更新 -> Agent 上下文
    visualizer = getattr(main_window, 'visualizer', None)
    if visualizer and hasattr(visualizer, 'add_pitch_data'):
        original_add = visualizer.add_pitch_data

        def _hooked_add_pitch(pitch_dict):
            result = original_add(pitch_dict)
            # 累积音高帧（轻量操作，不阻塞 UI）
            if not hasattr(agent, '_live_pitch_frames'):
                agent._live_pitch_frames = []
            agent._live_pitch_frames.append(pitch_dict)
            if len(agent._live_pitch_frames) > 5000:
                agent._live_pitch_frames = agent._live_pitch_frames[-5000:]
            return result

        try:
            visualizer.add_pitch_data = _hooked_add_pitch
            print("[AI Coach] 已连接到实时音高数据管道")
        except Exception:
            pass


def _auto_load_analysis(main_window, agent):
    """自动加载最近的分析文件"""
    # 查找最近的录音分析文件
    recordings_dir = Path("recordings")
    if not recordings_dir.exists():
        return

    try:
        analysis_files = sorted(
            recordings_dir.glob("*_analysis.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if analysis_files:
            latest = analysis_files[0]
            agent.load_analysis_file(latest)
            print(f"[AI Coach] 自动加载分析数据: {latest.name}")
    except Exception as e:
        print(f"[AI Coach] 加载分析数据失败: {e}")


# ═══════════════════════════════════════════════════════════════
# 独立测试入口
# ═══════════════════════════════════════════════════════════════


def run_standalone():
    """独立运行 AI Coach 面板（无需启动完整 MindEcho）"""
    if not _QT_AVAILABLE:
        print("需要 PyQt6 或 PyQt5")
        return

    from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

    app = QApplication([])
    app.setStyle("Fusion")

    window = QMainWindow()
    window.setWindowTitle("MindEcho AI 声乐教练 - 独立测试")
    window.setGeometry(200, 200, 500, 700)
    window.setStyleSheet("background-color: #1a1a2e;")

    central = QWidget()
    layout = QVBoxLayout(central)
    panel = AICoachDockPanel(central)
    layout.addWidget(panel)
    window.setCentralWidget(central)

    window.show()
    app.exec()


if __name__ == "__main__":
    run_standalone()
