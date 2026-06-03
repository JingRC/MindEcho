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
from .mascot_svg import get_svg, MASCOT_ANIMATION_CSS, THEMES, DEFAULT_THEME, PAW_CURSOR_SVG, PAW_PETTING_SVG

if _QT_AVAILABLE:
    from PyQt6.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QSizePolicy,
    )
    from PyQt6.QtCore import Qt, QTimer, QSize, QEvent, QObject
    from PyQt6.QtGui import QIcon, QPixmap, QPainter
    try:
        from PyQt6.QtSvgWidgets import QSvgWidget
        _QT_SVG_AVAILABLE = True
    except ImportError:
        _QT_SVG_AVAILABLE = False
else:
    _QT_SVG_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════
# 毛茸茸肉球手掌光标
# ═══════════════════════════════════════════════════════════════

_paw_cursor_cache = None


def _get_paw_cursor(size: int = 36):
    """创建毛茸茸肉球手掌光标（缓存复用）。

    优先使用 SVG 渲染（高清），失败则用 QPainter 直接绘制（零依赖）。
    """
    global _paw_cursor_cache
    if _paw_cursor_cache is not None:
        return _paw_cursor_cache

    try:
        # QSvgRenderer 在 PyQt6.QtSvg，不在 QtSvgWidgets
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtGui import QPixmap, QPainter, QCursor
        from PyQt6.QtCore import Qt as QtCore_Qt

        renderer = QSvgRenderer(PAW_CURSOR_SVG.encode("utf-8"))
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCore_Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        renderer.render(painter)
        painter.end()

        hot_x = int(size * 0.46)
        hot_y = int(size * 0.28)
        _paw_cursor_cache = QCursor(pixmap, hot_x, hot_y)
        return _paw_cursor_cache
    except Exception:
        pass

    # ── Fallback: QPainter 直接绘制肉球手掌（无需 SVG 模块）──
    try:
        from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QBrush, QPen, QCursor
        from PyQt6.QtCore import Qt as QtCore_Qt, QPointF
        from PyQt6.QtGui import QRadialGradient, QColor

        pixmap = QPixmap(size, size)
        pixmap.fill(QtCore_Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        s = size / 48.0  # 缩放因子 (SVG viewBox=48)

        # ── 主体大掌垫 ──
        body_color = QColor(245, 230, 210)
        body_stroke = QColor(232, 201, 160)
        p.setBrush(QBrush(body_color))
        p.setPen(QPen(body_stroke, 1.2 * s))
        p.drawEllipse(QPointF(22 * s, 30 * s), 15 * s, 13 * s)

        # ── 掌垫中央大肉球 ──
        pad_grad = QRadialGradient(QPointF(22 * s, 32 * s), 8 * s)
        pad_grad.setColorAt(0, QColor(255, 208, 217))
        pad_grad.setColorAt(1, QColor(244, 160, 181))
        p.setBrush(QBrush(pad_grad))
        p.setPen(QtCore_Qt.PenStyle.NoPen)
        p.setOpacity(0.85)
        p.drawEllipse(QPointF(22 * s, 32 * s), 8 * s, 7.5 * s)
        p.setOpacity(1.0)

        # ── 四个指头肉球 ──
        toes = [
            (13, 18, 5.0, 2.8),    # 食指
            (22, 14, 5.5, 3.0),    # 中指
            (31, 16, 5.0, 2.8),    # 无名指
            (35, 22, 4.3, 2.3),    # 小指
        ]
        for cx, cy, outer_r, inner_r in toes:
            # 外圈（奶油色）
            p.setBrush(QBrush(body_color))
            p.setPen(QPen(body_stroke, 1.0 * s))
            p.drawEllipse(QPointF(cx * s, cy * s), outer_r * s, outer_r * s)
            # 内圈（粉色肉球）
            igrad = QRadialGradient(QPointF(cx * s, cy * s), inner_r * s)
            igrad.setColorAt(0, QColor(255, 215, 222))
            igrad.setColorAt(1, QColor(244, 160, 181))
            p.setBrush(QBrush(igrad))
            p.setPen(QtCore_Qt.PenStyle.NoPen)
            p.setOpacity(0.8)
            p.drawEllipse(QPointF(cx * s, (cy + 0.5) * s), inner_r * s, inner_r * s)
            p.setOpacity(1.0)

        # ── 毛茸边缘小突起 ──
        fluff_color = QColor(255, 245, 238)
        fluff_color2 = QColor(245, 220, 195)
        fluffs = [
            (8, 22, 2.5, fluff_color),
            (6, 28, 2.0, fluff_color),
            (10, 38, 2.2, fluff_color2),
            (18, 42, 2.5, fluff_color2),
            (30, 41, 2.3, fluff_color2),
            (36, 34, 2.0, fluff_color2),
            (38, 26, 2.0, fluff_color),
        ]
        p.setPen(QtCore_Qt.PenStyle.NoPen)
        for cx, cy, r, color in fluffs:
            p.setBrush(QBrush(color))
            p.setOpacity(0.55)
            p.drawEllipse(QPointF(cx * s, cy * s), r * s, r * s)
        p.setOpacity(1.0)

        p.end()

        hot_x = int(size * 0.46)
        hot_y = int(size * 0.28)
        _paw_cursor_cache = QCursor(pixmap, hot_x, hot_y)
        return _paw_cursor_cache
    except Exception:
        return None


_petting_cursor_cache = None


def _get_petting_cursor(size: int = 40):
    """抚摸时的手掌光标（旋转按压角度，稍大一圈）。"""
    global _petting_cursor_cache
    if _petting_cursor_cache is not None:
        return _petting_cursor_cache

    try:
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtGui import QPixmap, QPainter, QCursor
        from PyQt6.QtCore import Qt as QtCore_Qt

        renderer = QSvgRenderer(PAW_PETTING_SVG.encode("utf-8"))
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCore_Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        renderer.render(painter)
        painter.end()

        hot_x = int(size * 0.50)
        hot_y = int(size * 0.20)
        _petting_cursor_cache = QCursor(pixmap, hot_x, hot_y)
        return _petting_cursor_cache
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# 桌宠小部件
# ═══════════════════════════════════════════════════════════════


class MascotWidget(QWidget):
    """桌面宠物小部件 —— 显示 AI 教练的当前状态，支持多主题切换 + 多点抚摸交互"""

    EXPRESSIONS = ["idle", "singing", "thinking", "happy", "surprised", "loved"]
    # 连续点击阈值：3 次以内 = 开心，3 次以上 = 抚摸
    _PET_CLICK_THRESHOLD = 3
    _PET_CLICK_WINDOW_MS = 2000

    def __init__(self, size: int = 120, display_name: str = "麦麦",
                 theme: str = DEFAULT_THEME, parent=None):
        super().__init__(parent)
        self._size = size
        self._current_expr = "idle"
        self._display_name = display_name
        self._theme = theme
        self._svg_data: dict[str, str] = {}
        self._load_svgs()

        # 抚摸交互状态
        self._click_count = 0
        self._click_reset_timer: Optional[QTimer] = None

        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 毛茸茸肉球手掌光标
        paw = _get_paw_cursor()
        if paw is not None:
            self.setCursor(paw)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        if _QT_SVG_AVAILABLE:
            self._svg_widget = QSvgWidget(self)
            self._svg_widget.setFixedSize(size, size)
            self._set_svg("idle")
        else:
            self._label = QLabel(self)
            self._label.setFixedSize(size, size)
            self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._label.setText("🎵")

        self.setToolTip(
            f"MindEcho AI 声乐教练 - {display_name}\n"
            "点击互动  |  连续点击抚摸  |  右键菜单"
        )
        self._anim_timer: Optional[QTimer] = None

    def _load_svgs(self):
        """预加载 SVG 数据"""
        for expr in self.EXPRESSIONS:
            self._svg_data[expr] = get_svg(expr, self._theme)

    def set_theme(self, theme: str):
        """切换形象主题并重新加载所有 SVG"""
        if theme not in THEMES:
            return
        self._theme = theme
        self._load_svgs()
        self._set_svg(self._current_expr)

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

    def anim_loved(self, duration_ms: int = 3000):
        """被抚摸 — 爱心雨 + 极度开心 (♥‿♥)"""
        self.set_expression("loved")
        # 抚摸时保持肉球手掌光标（更贴合抚摸感受）
        if self._anim_timer:
            self._anim_timer.stop()
        self._anim_timer = QTimer(self)
        self._anim_timer.setSingleShot(True)
        self._anim_timer.timeout.connect(self._on_loved_end)
        self._anim_timer.start(duration_ms)

    def _on_loved_end(self):
        """抚摸结束 → 恢复待机"""
        self.anim_idle()

    def mousePressEvent(self, event):
        """点击桌宠 — 智能交互 + 肉球手掌抚摸动画
        第 1-2 次点击: 开心 (^_^)
        第 3+ 次点击(2秒内): 被抚摸 (♥‿♥ + 爱心雨)

        每次点击时肉球手掌会变为"按下抚摸"角度 (~400ms)，
        模拟手掌放在 agent 头上轻拍的效果。
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # ── 肉球手掌 → 按下抚摸角度 ──
            self._show_petting_cursor()

            # 累加点击计数
            self._click_count += 1
            # 重置计时器
            if self._click_reset_timer:
                self._click_reset_timer.stop()
            self._click_reset_timer = QTimer(self)
            self._click_reset_timer.setSingleShot(True)
            self._click_reset_timer.timeout.connect(self._reset_clicks)
            self._click_reset_timer.start(self._PET_CLICK_WINDOW_MS)

            if self._click_count >= self._PET_CLICK_THRESHOLD:
                # 连续点击 ≥ 3 → 抚摸模式
                self._click_count = 0
                if self._click_reset_timer:
                    self._click_reset_timer.stop()
                self.anim_loved(3000)
            else:
                # 1-2 次点击 → 开心
                self.anim_happy(1800)
        elif event.button() == Qt.MouseButton.RightButton:
            # 右键 — 预留菜单（后续扩展：投喂/洗澡等）
            from PyQt6.QtWidgets import QMenu
            menu = QMenu(self)
            menu.addAction("🐟 投喂").triggered.connect(lambda: self.anim_surprised(2000))
            menu.addAction("🫧 洗澡").triggered.connect(lambda: self.anim_happy(2500))
            menu.addAction("💤 休息").triggered.connect(self.anim_idle)
            menu.exec(event.globalPos())
        super().mousePressEvent(event)

    def _show_petting_cursor(self):
        """短暂切换到「按下抚摸」角度的手掌光标"""
        petting = _get_petting_cursor()
        if petting is None:
            return
        self.setCursor(petting)
        # 400ms 后恢复普通肉球手掌
        if hasattr(self, '_cursor_restore_timer') and self._cursor_restore_timer:
            self._cursor_restore_timer.stop()
        self._cursor_restore_timer = QTimer(self)
        self._cursor_restore_timer.setSingleShot(True)
        self._cursor_restore_timer.timeout.connect(self._restore_paw_cursor)
        self._cursor_restore_timer.start(400)

    def _restore_paw_cursor(self):
        """恢复普通肉球手掌光标"""
        paw = _get_paw_cursor()
        if paw is not None:
            self.setCursor(paw)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _reset_clicks(self):
        """超时重置点击计数"""
        self._click_count = 0


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

        # ── 桌宠栏 ──
        mascot_bar = QHBoxLayout()
        self.mascot = MascotWidget(size=80, display_name="麦麦")
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

        # 设置按钮 — 放在桌宠栏右侧
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(28, 28)
        self.btn_settings.setToolTip("AI 教练设置 — API 密钥、模型、教练身份")
        self.btn_settings.setStyleSheet("""
            QPushButton {
                background: transparent; color: #888; border: 1px solid #444;
                border-radius: 14px; font-size: 14px;
            }
            QPushButton:hover { color: #fff; border-color: #A78BFA; background: #2a2a4a; }
        """)
        mascot_bar.addWidget(self.btn_settings)
        layout.addLayout(mascot_bar)

        # AI Coach 对话面板
        self.coach_panel = AICoachPanel(parent=self)

        # 从 agent identity 更新桌宠显示
        self._sync_mascot_identity()

        # 将 Agent 的回调连接到桌宠
        agent = self.coach_panel.agent
        agent._on_thinking = self._on_agent_thinking
        agent._on_response = self._on_agent_response
        agent._on_stream = None  # 使用 panel 自己的流式回调

        # 设置按钮 → 打开设置对话框，保存后同步桌宠
        self.coach_panel.on_config_changed = self._sync_mascot_identity
        self.btn_settings.clicked.connect(self.coach_panel._on_settings)

        # 定期刷新用户画像到状态栏
        self._profile_timer = QTimer(self)
        self._profile_timer.timeout.connect(self._refresh_status_profile)
        self._profile_timer.start(30000)  # 每30秒刷新一次

        layout.addWidget(self.coach_panel)

    def _sync_mascot_identity(self):
        """从 agent identity 同步桌宠显示"""
        identity = self.coach_panel.agent.identity
        self.mascot_name.setText(identity.display_name)
        self.mascot.setToolTip(f"MindEcho AI 声乐教练 - {identity.display_name}")
        if identity.avatar_theme:
            self.mascot.set_theme(identity.avatar_theme)

    def _on_agent_thinking(self):
        self.mascot_status.setText("思考中...")
        self.mascot.anim_thinking()

    def _on_agent_response(self, response: str):
        self.mascot_status.setText("随时准备帮你~")
        self.mascot.anim_happy(2000)
        self._refresh_status_profile()

    def _refresh_status_profile(self):
        """将用户画像摘要显示在桌宠状态栏"""
        try:
            summary = self.coach_panel._refresh_profile()
            if summary:
                short = summary.split("\n")[0] if summary else ""
                if len(short) > 40:
                    short = short[:40] + "..."
                if short:
                    self.mascot.setToolTip(f"MindEcho AI 声乐教练 - {summary}")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# 悬浮球（当停靠面板关闭时显示）
# ═══════════════════════════════════════════════════════════════


class _FloatingBubble(QWidget):
    """悬浮桌宠球 —— 停靠面板关闭后的小窗口，悬停提示 + 点击唤回 + 磁吸拖拽停靠"""

    SNAP_THRESHOLD = 80   # 距离屏幕边缘此像素内触发磁吸提示
    SNAP_COMMIT = 40      # 释放时距边缘此像素内执行停靠

    def __init__(self, dock: QDockWidget, mascot_theme: str = DEFAULT_THEME):
        super().__init__(None)
        self._dock = dock
        self._main_window = dock.parentWidget()
        self._drag_pos = None
        self._hovered = False
        self._snap_edge = None   # 'left' | 'right' | None
        self._dragging = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(100, 140)

        # ── 整体布局 ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 提示标签 (悬停 / 拖拽磁吸时显示) ──
        self._hint_label = QLabel("点击唤回\nAI 声乐教练")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a4a, stop:1 #3a2a5a);
                border: 2px solid #5B3FD9;
                border-radius: 14px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: bold;
                font-family: "Microsoft YaHei", sans-serif;
            }
        """)
        self._hint_label.setFixedWidth(110)
        self._hint_label.hide()
        self._hint_label.setGraphicsEffect(self._make_glow())

        hint_container = QHBoxLayout()
        hint_container.setContentsMargins(0, 0, 0, 0)
        hint_container.addStretch()
        hint_container.addWidget(self._hint_label)
        hint_container.addStretch()
        layout.addLayout(hint_container)

        # ── 桌宠本体 ──
        mascot_container = QHBoxLayout()
        mascot_container.setContentsMargins(0, 4, 0, 0)
        mascot_container.addStretch()
        self.mascot = MascotWidget(size=68, display_name="麦麦", theme=mascot_theme)
        # 悬浮球桌宠也用毛茸茸肉球手掌光标
        paw = _get_paw_cursor()
        if paw is not None:
            self.mascot.setCursor(paw)
        else:
            self.mascot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mascot.setGraphicsEffect(self._make_glow())
        mascot_container.addWidget(self.mascot)
        mascot_container.addStretch()
        layout.addLayout(mascot_container)
        layout.addStretch()

        self.setStyleSheet("background: transparent;")

        # ── 呼吸脉冲动画 (100ms 间隔, ~10fps, 避免频繁 SVG 重渲染) ──
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self._pulse_phase = 0
        self._pulse_timer.start(100)

        # ── 初始位置：屏幕右下角 ──
        try:
            from PyQt6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.move(geo.right() - 120, geo.bottom() - 160)
        except Exception:
            pass

    def _make_glow(self):
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(20)
        glow.setOffset(0, 0)
        glow.setColor(Qt.GlobalColor.white)
        glow.setEnabled(False)
        self._glow_effect = glow
        return glow

    def _pulse_tick(self):
        """呼吸脉冲: 待机时微微缩放 (低频低幅，减少重绘)"""
        if self._hovered or self._dragging:
            return
        import math
        self._pulse_phase = (self._pulse_phase + 0.08) % 6.283
        scale = 1.0 + 0.02 * math.sin(self._pulse_phase)
        new_size = int(68 * scale)
        # 仅当尺寸实际变化 > 1px 时才更新，避免无效重绘
        current = self.mascot.width()
        if abs(new_size - current) >= 1:
            self.mascot.setFixedSize(new_size, new_size)

    # ── 磁吸逻辑 ───────────────────────────────────────────────

    def _get_screen_geo(self):
        try:
            from PyQt6.QtGui import QGuiApplication
            screen = QGuiApplication.screenAt(self.frameGeometry().center())
            if not screen:
                screen = QGuiApplication.primaryScreen()
            if screen:
                return screen.availableGeometry()
        except Exception:
            pass
        return None

    def _check_snap_edge(self) -> Optional[str]:
        """检测悬浮球靠近哪个屏幕边缘"""
        geo = self._get_screen_geo()
        if not geo:
            return None
        br = self.frameGeometry()
        dist_left = br.left() - geo.left()
        dist_right = geo.right() - br.right()
        if dist_left < self.SNAP_THRESHOLD and dist_left < dist_right:
            return 'left'
        elif dist_right < self.SNAP_THRESHOLD:
            return 'right'
        return None

    def _show_snap_hint(self, edge: str):
        """显示磁吸提示"""
        if edge == 'left':
            self._hint_label.setText("◀ 释放以嵌入\n左侧面板")
        else:
            self._hint_label.setText("释放以嵌入 ▶\n右侧面板")
        self._hint_label.setStyleSheet("""
            QLabel {
                color: #FFD93D;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a1a3a, stop:1 #3a1a5a);
                border: 2px solid #FFD93D;
                border-radius: 14px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: bold;
                font-family: "Microsoft YaHei", sans-serif;
            }
        """)
        self._hint_label.show()
        if hasattr(self, '_glow_effect'):
            self._glow_effect.setEnabled(True)
        self.mascot.setFixedSize(80, 80)

    def _hide_snap_hint(self):
        """隐藏磁吸提示"""
        self._snap_edge = None
        self._hint_label.setText("点击唤回\nAI 声乐教练")
        self._hint_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a4a, stop:1 #3a2a5a);
                border: 2px solid #5B3FD9;
                border-radius: 14px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: bold;
                font-family: "Microsoft YaHei", sans-serif;
            }
        """)
        self._hint_label.hide()

    # ── 事件处理 ───────────────────────────────────────────────

    def enterEvent(self, event):
        """鼠标进入：显示提示文字 + 发光 + 放大"""
        self._hovered = True
        if not self._dragging:
            self._hint_label.show()
        if hasattr(self, '_glow_effect'):
            self._glow_effect.setEnabled(True)
        self.mascot.setFixedSize(78, 78)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开：隐藏提示文字 + 取消发光 + 恢复大小"""
        self._hovered = False
        if not self._dragging:
            self._hint_label.hide()
        if hasattr(self, '_glow_effect'):
            self._glow_effect.setEnabled(False)
        self.mascot.setFixedSize(68, 68)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            # 判断是否已进入拖拽状态 (移动超过 3px)
            delta = event.globalPosition().toPoint() - self.frameGeometry().topLeft() - self._drag_pos
            if not self._dragging and (abs(delta.x()) > 3 or abs(delta.y()) > 3):
                self._dragging = True

            self.move(event.globalPosition().toPoint() - self._drag_pos)

            # 磁吸检测
            if self._dragging:
                edge = self._check_snap_edge()
                if edge != self._snap_edge:
                    self._snap_edge = edge
                    if edge:
                        self._show_snap_hint(edge)
                    else:
                        self._hide_snap_hint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self.frameGeometry().topLeft() - self._drag_pos

            if self._dragging:
                # 拖拽释放 → 检查是否应磁吸停靠
                edge = self._check_snap_edge()
                if edge:
                    # 更严格的阈值：必须非常接近边缘才停靠
                    geo = self._get_screen_geo()
                    if geo:
                        br = self.frameGeometry()
                        dist = (br.left() - geo.left()) if edge == 'left' else (geo.right() - br.right())
                        if dist < self.SNAP_COMMIT:
                            self._do_snap_dock(edge)
                self._hide_snap_hint()
            else:
                # 点击 (没有拖拽) → 唤回面板并重新停靠
                if abs(delta.x()) < 5 and abs(delta.y()) < 5:
                    self._restore_dock()
        self._drag_pos = None
        self._dragging = False
        self.mascot.setFixedSize(68, 68)
        super().mouseReleaseEvent(event)

    def _do_snap_dock(self, edge: str):
        """执行磁吸停靠：将 dock 吸附到指定屏幕边缘并显示"""
        try:
            mw = self._main_window
            if mw and hasattr(mw, 'addDockWidget'):
                area = (Qt.DockWidgetArea.LeftDockWidgetArea if edge == 'left'
                        else Qt.DockWidgetArea.RightDockWidgetArea)
                mw.removeDockWidget(self._dock)
                mw.addDockWidget(area, self._dock)
        except Exception:
            pass
        self._dock.show()
        self._dock.raise_()

    def _restore_dock(self):
        """唤回 dock 面板 — 处理浮动/隐藏状态"""
        dock = self._dock
        # 如果 dock 处于浮动状态，先取消浮动才能重新停靠
        if dock.isFloating():
            dock.setFloating(False)
        dock.show()
        dock.raise_()

    def mouseDoubleClickEvent(self, event):
        self._restore_dock()
        super().mouseDoubleClickEvent(event)

    def set_theme(self, theme: str):
        """更新桌宠主题"""
        self.mascot.set_theme(theme)


# ═══════════════════════════════════════════════════════════════
# 自定义 Dock 标题栏
# ═══════════════════════════════════════════════════════════════


class _CoachTitleBar(QWidget):
    """自定义标题栏：标题 + 最小化 / 浮动 / 关闭 三个按钮。
    支持拖拽分离 dock，双击切换浮动/停靠。"""

    def __init__(self, title: str, dock: "QDockWidget", parent=None):
        super().__init__(parent)
        self._dock = dock
        self._drag_start = None
        self._dragging = False

        self.setFixedHeight(36)
        self.setStyleSheet(
            "background:#1E1E36; border-bottom:1px solid #2A2A4A;"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 4, 0)
        layout.setSpacing(2)

        # 标题
        self._label = QLabel(title)
        self._label.setStyleSheet(
            "color:#B8A9E8; font-weight:600; font-size:12px;"
            "background:transparent; border:none;"
        )
        layout.addWidget(self._label)
        layout.addStretch()

        # ── 统一按钮样式：极简扁平，hover 才显底色 ──
        _btn_common = """
            QPushButton {
                background:transparent;
                color:#8888AA;
                border:none;
                border-radius:5px;
                font-size:13px; font-weight:bold;
                font-family:"Segoe UI","Microsoft YaHei",sans-serif;
                padding:0px;
                min-width:28px; max-width:28px;
                min-height:28px; max-height:28px;
            }
            QPushButton:hover {
                background:#454568;
                color:#E8E8FF;
            }
            QPushButton:pressed {
                background:#2E2E48;
            }
        """

        # ① 最小化
        self.btn_min = QPushButton("–")
        self.btn_min.setToolTip("最小化 — 缩小为悬浮桌宠")
        self.btn_min.setStyleSheet(_btn_common)
        layout.addWidget(self.btn_min)

        # ② 浮动/停靠
        self.btn_float = QPushButton("□")
        self.btn_float.setToolTip("分离窗口 / 重新停靠")
        self.btn_float.setStyleSheet(_btn_common)
        self.btn_float.clicked.connect(self._toggle_float)
        layout.addWidget(self.btn_float)

        # ③ 关闭
        self.btn_close = QPushButton("×")
        self.btn_close.setToolTip("关闭（最小化到悬浮球）")
        self.btn_close.setStyleSheet(_btn_common + """
            QPushButton:hover { background:#D94A4A; color:#FFF; }
            QPushButton:pressed { background:#A83232; }
        """)
        layout.addWidget(self.btn_close)

    def _toggle_float(self):
        """切换浮动/停靠"""
        self._dock.setFloating(not self._dock.isFloating())

    # ── 拖拽支持 ──
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            delta = event.globalPosition().toPoint() - self._drag_start
            if abs(delta.x()) > 6 or abs(delta.y()) > 6:
                if not self._dragging:
                    self._dragging = True
                    if not self._dock.isFloating():
                        self._dock.setFloating(True)
                # 移动浮动窗口
                self._dock.move(event.globalPosition().toPoint() - self._drag_start +
                                self._dock.mapToGlobal(self._dock.rect().topLeft()))
                self._drag_start = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._toggle_float()
        super().mouseDoubleClickEvent(event)


# ═══════════════════════════════════════════════════════════════
# 自定义 Dock Widget
# ═══════════════════════════════════════════════════════════════


class _CoachDockWidget(QDockWidget):
    """自定义 Dock：追踪显式关闭 vs 窗口最小化，支持最小化到悬浮球。"""

    minimize_requested = None  # signal placeholder, set after init

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._explicitly_hidden = False

    def closeEvent(self, event):
        """用户点击关闭按钮 → 标记为显式隐藏 → 触发悬浮球"""
        self._explicitly_hidden = True
        super().closeEvent(event)

    def showEvent(self, event):
        """dock 重新显示 → 清除标记"""
        self._explicitly_hidden = False
        super().showEvent(event)

    def minimize_to_bubble(self):
        """最小化 → 隐藏 dock 并显示悬浮球"""
        self._explicitly_hidden = True
        self.hide()


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

    from PyQt6.QtGui import QAction, QKeySequence

    # ── 自定义 Dock ──
    dock = _CoachDockWidget("AI 声乐教练", main_window)
    dock.setObjectName("ai_coach_dock")
    dock.setMinimumWidth(340)
    dock.resize(370, 700)
    dock.setAllowedAreas(
        Qt.DockWidgetArea.LeftDockWidgetArea |
        Qt.DockWidgetArea.RightDockWidgetArea
    )
    dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable |
        QDockWidget.DockWidgetFeature.DockWidgetFloatable |
        QDockWidget.DockWidgetFeature.DockWidgetClosable
    )

    # 创建内容
    panel = AICoachDockPanel(dock)
    dock.setWidget(panel)

    # ── 自定义标题栏 (替换原生) ──
    title_bar = _CoachTitleBar("AI 声乐教练", dock)
    dock.setTitleBarWidget(title_bar)

    # dock widget 整体风格
    dock.setStyleSheet("""
        QDockWidget {
            color: #e0e0e0; font-size:13px;
            background:#1a1a2e; border:none;
        }
    """)

    # 添加到主窗口（侧边栏默认显示，点击 AI 教练按钮可切换显隐）
    main_window.addDockWidget(dock_area, dock)

    # ── 悬浮球 ──
    theme = panel.coach_panel.agent.identity.avatar_theme
    bubble = _FloatingBubble(dock, theme)
    bubble.hide()

    def _show_bubble():
        _sync_bubble_theme()
        bubble.show()

    # ── 标题栏按钮接线 ──
    # ① 最小化 → 悬浮球
    title_bar.btn_min.clicked.connect(lambda: dock.minimize_to_bubble())
    # ③ 关闭 → 悬浮球
    title_bar.btn_close.clicked.connect(lambda: dock.minimize_to_bubble())
    # ② 浮动/停靠 — 已在 _CoachTitleBar._toggle_float 中处理

    # ── Dock 显隐逻辑 ──
    def _on_dock_visibility(visible: bool):
        if visible:
            bubble.hide()
        else:
            # 主窗口最小化 → 不触发悬浮球
            if hasattr(main_window, 'isMinimized') and main_window.isMinimized():
                return
            # 只有显式关闭才显示悬浮球
            if not dock._explicitly_hidden:
                return
            dock._explicitly_hidden = False
            _show_bubble()

    dock.visibilityChanged.connect(_on_dock_visibility)

    # ── 修复：主窗口最小化再恢复后 dock 消失 ──
    # Qt 在父窗口最小化时会隐藏 QDockWidget，但恢复时不会自动显示回来。
    # 使用 EventFilter 监听 WindowStateChange 事件，恢复后重新显示 dock。
    _dock_was_visible = True

    class _WindowStateFilter(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._prev_state = None

        def eventFilter(self, obj, event):
            nonlocal _dock_was_visible
            if event.type() == QEvent.Type.WindowStateChange:
                is_min = main_window.isMinimized()
                _min_flag = Qt.WindowState.WindowMinimized.value
                if self._prev_state is not None:
                    was_min = bool(self._prev_state & _min_flag)
                    if was_min and not is_min:
                        if _dock_was_visible and not dock._explicitly_hidden:
                            dock.show()
                    if not was_min and is_min:
                        _dock_was_visible = dock.isVisible()
                self._prev_state = main_window.windowState().value
            return False

    _state_filter = _WindowStateFilter(main_window)
    main_window.installEventFilter(_state_filter)

    # ── 配置变更时同步悬浮球主题 ──
    def _sync_bubble_theme():
        identity = panel.coach_panel.agent.identity
        if identity.avatar_theme:
            bubble.set_theme(identity.avatar_theme)
            bubble.mascot.setToolTip(
                f"点击唤回 AI 声乐教练\n当前形象: {identity.display_name}"
            )

    # 在 dock panel 的 sync 之后也 sync bubble
    original_sync = panel._sync_mascot_identity
    def _sync_all():
        original_sync()
        _sync_bubble_theme()
    panel._sync_mascot_identity = _sync_all

    # ── 菜单/快捷键 ──
    # 添加到主窗口的 View 菜单（如果存在），否则只注册快捷键不占菜单栏
    toggle_action = QAction("AI 声乐教练", main_window)
    toggle_action.setCheckable(True)
    toggle_action.setChecked(True)
    toggle_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
    toggle_action.setToolTip("显示/隐藏 AI 声乐教练面板 (Ctrl+Shift+A)")

    def _toggle_coach(checked: bool):
        dock.setVisible(checked)

    toggle_action.toggled.connect(_toggle_coach)
    dock.visibilityChanged.connect(toggle_action.setChecked)

    # 只有当前已存在菜单栏且其中有视图/窗口类菜单时才添加进去，避免凭空创建菜单栏
    menu_bar = main_window.menuBar()
    existing_menus = menu_bar.findChildren(menu_bar.__class__)
    if existing_menus:
        added = False
        for menu in existing_menus:
            if menu.title() in ("查看", "视图", "View", "窗口", "Window"):
                menu.addAction(toggle_action)
                added = True
                break
        if not added:
            for action in menu_bar.actions():
                if action.text() in ("帮助", "Help", "关于", "About"):
                    menu_bar.insertAction(action, toggle_action)
                    added = True
                    break
        if not added:
            # 作为最后手段放到已有菜单中，而不是直接加到菜单栏
            for menu in existing_menus:
                menu.addAction(toggle_action)
                added = True
                break
    # 如果没有任何已有菜单，不把 action 挂到菜单栏（会凭空创建菜单栏显示"AI 声乐教练"文字）
    # 但仍然注册到主窗口以确保快捷键生效
    if not existing_menus:
        main_window.addAction(toggle_action)

    # ── 保存引用以便外部访问 ──
    main_window._ai_coach_dock = dock
    main_window._ai_coach_panel = panel
    main_window._ai_coach_bubble = bubble

    # 连接数据管道
    _connect_data_pipeline(main_window, panel)

    # ── 首次启动检测 ──
    _check_first_run(panel)

    print("[AI Coach] 集成完成 - 面板已添加到主窗口 (Ctrl+Shift+A 切换，关闭后悬浮球唤回)")
    return panel


def _check_first_run(panel: AICoachDockPanel):
    """检测是否需要显示首次启动向导"""
    from ..config import ConfigManager

    config_mgr = ConfigManager()
    config_path = config_mgr._config_path

    # 如果配置文件已存在且有 API key，跳过
    if config_path.exists():
        try:
            import json
            data = json.loads(config_path.read_text(encoding="utf-8"))
            llm_data = data.get("llm", {})
            api_key = llm_data.get("api_key", "")
            if api_key and not api_key.startswith("obf:"):
                return  # 已配置完成
            # 检查混淆后的 key
            if api_key.startswith("obf:") and len(api_key) > 10:
                return  # 已配置完成
        except Exception:
            pass

    # 延迟弹出向导，让主窗口先渲染
    def _show_wizard():
        from .first_run_wizard import FirstRunWizard

        wizard = FirstRunWizard(config_mgr, parent=panel)
        if wizard.exec() == 1:  # QDialog.Accepted (PyQt5=1, PyQt6=DialogCode.Accepted=1)
            new_config = wizard.get_config()
            try:
                panel.coach_panel.agent.reconfigure(new_config)
                panel._sync_mascot_identity()
                # 同步悬浮球主题
                if hasattr(panel, '_sync_mascot_identity'):
                    pass  # _sync_mascot_identity 已被包装为 _sync_all
                # 显示欢迎消息
                identity = new_config.identity
                greeting = identity.get_greeting()
                QTimer.singleShot(300, lambda: panel.coach_panel._append_message(
                    "assistant",
                    f"🎉 设置完成！{greeting}"
                ))
            except Exception as e:
                panel.coach_panel._append_message(
                    "assistant",
                    f"⚠ 配置已保存，但重新连接失败: {e}\n请在设置中检查 API 配置。"
                )

    QTimer.singleShot(600, _show_wizard)


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
        # 查找所有 JSON 文件，过滤出 MindEcho 分析 JSON（含 pitch_analysis 或 recording_info）
        candidates = []
        for p in recordings_dir.glob("*.json"):
            if p.name.startswith("._") or p.name.endswith("_temp.json"):
                continue
            try:
                with open(p, "r", encoding="utf-8") as f:
                    head = f.read(512)
                if '"pitch_analysis"' in head or '"recording_info"' in head:
                    candidates.append(p)
            except Exception:
                continue
        if candidates:
            latest = max(candidates, key=lambda p: p.stat().st_mtime)
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
