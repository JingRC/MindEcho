"""练声练习浏览器 — 现代科技渐变风格

设计理念：
  - 暗色主题：与 MindEcho 主界面 #1a1a1a 背景一致
  - 蓝紫青渐变：呼应 AI 教练的紫色渐变 + 练声模式的金色点缀
  - 左侧「分类导航」：深色半透明面板，图标化分类
  - 右侧「练习卡片」：暗色卡片 + 悬停发光边框
  - 顶部栏：渐变搜索栏 + 等级标签筛选
  - 点击卡片选中练习，底部栏显示并可直接开始
"""

from __future__ import annotations

from typing import Optional, Callable

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QLineEdit, QScrollArea, QFrame, QWidget, QSplitter,
        QSizePolicy, QApplication, QGraphicsDropShadowEffect,
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal
    from PyQt6.QtGui import QFont, QColor, QFontDatabase
    QT_VERSION = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QLineEdit, QScrollArea, QFrame, QWidget, QSplitter,
        QSizePolicy, QApplication, QGraphicsDropShadowEffect,
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal
    from PyQt5.QtGui import QFont, QColor, QFontDatabase
    QT_VERSION = 5

from src.vocal_training.exercise_library import (
    VocalExercise, CATEGORIES,
    list_all_exercises, get_exercises_by_category, get_category_summary,
    get_exercises_by_level,
)


# ══════════════════════════════════════════════════════════
#  现代科技暗色主题配色（对齐 MindEcho 主界面）
# ══════════════════════════════════════════════════════════

class TechColors:
    """现代科技暗色主题 — 与 MindEcho 主界面 #1a1a1a 保持一致"""

    # 底色
    BG_DARKEST    = "#0D1117"      # 最深底色（侧边栏）
    BG_DARK       = "#1a1a1a"      # 主底色（与主窗口一致）
    BG_CARD       = "#21262D"      # 卡片底色
    BG_CARD_HOVER = "#292E36"      # 卡片悬停
    BG_SEARCH     = "#161B22"      # 搜索栏底色
    BG_FOOTER     = "#161B22"      # 底部栏

    # 文字
    TEXT_PRIMARY   = "#E6EDF3"     # 主文字
    TEXT_SECONDARY = "#8B949E"     # 副文字
    TEXT_ACCENT    = "#58A6FF"     # 强调文字（蓝）
    TEXT_GOLD      = "#DAA520"     # 金色文字

    # 边框
    BORDER_DEFAULT = "#30363D"     # 默认边框
    BORDER_ACTIVE  = "#58A6FF"     # 激活边框
    BORDER_GOLD    = "#DAA520"     # 金色边框

    # 渐变
    GRAD_HEADER_START = "#1A1F35"  # 标题栏渐变起点（深蓝）
    GRAD_HEADER_END   = "#2D1F3D"  # 标题栏渐变终点（深紫）
    GRAD_SIDEBAR_START = "#0D1117" # 侧边栏渐变起点
    GRAD_SIDEBAR_END   = "#161B22" # 侧边栏渐变终点

    # 强调色
    ACCENT_BLUE   = "#58A6FF"      # 蓝色强调
    ACCENT_PURPLE = "#A78BFA"      # 紫色强调（对齐 AI 教练）
    ACCENT_CYAN   = "#39D2C0"      # 青色强调
    ACCENT_GOLD   = "#DAA520"      # 金色（对齐练声模式）
    ACCENT_GREEN  = "#3FB950"      # 绿色

    # 星级
    STAR_FILLED = "#DAA520"
    STAR_EMPTY  = "#30363D"

    # 难度标签色
    DIFF_BEGINNER     = "#8B949E"  # 入门 - 灰
    DIFF_ELEMENTARY   = "#3FB950"  # 初级 - 绿
    DIFF_INTERMEDIATE = "#58A6FF"  # 进阶 - 蓝
    DIFF_MID          = "#DAA520"  # 中级 - 金
    DIFF_ADVANCED     = "#F85149"  # 高级 - 红

    @classmethod
    def diff_color(cls, label: str) -> tuple:
        """返回 (文字色, 背景色)"""
        m = {
            "入门": (cls.DIFF_BEGINNER, f"{cls.DIFF_BEGINNER}20"),
            "初级": (cls.DIFF_ELEMENTARY, f"{cls.DIFF_ELEMENTARY}20"),
            "进阶": (cls.DIFF_INTERMEDIATE, f"{cls.DIFF_INTERMEDIATE}20"),
            "中级": (cls.DIFF_MID, f"{cls.DIFF_MID}20"),
            "高级": (cls.DIFF_ADVANCED, f"{cls.DIFF_ADVANCED}20"),
        }
        return m.get(label, (cls.TEXT_SECONDARY, f"{cls.TEXT_SECONDARY}20"))


# ══════════════════════════════════════════════════════════
#  练习卡片组件（现代暗色风格）
# ══════════════════════════════════════════════════════════

class ExerciseCard(QFrame):
    """单张练习卡片 — 暗色底 + 悬停发光边框"""

    clicked = pyqtSignal(str)  # exercise_id
    _CARD_BASE = f"""
        #exercise_card {{
            background-color: {TechColors.BG_CARD};
            border: 1px solid {TechColors.BORDER_DEFAULT};
            border-radius: 8px;
        }}
        #exercise_card:hover {{
            background-color: {TechColors.BG_CARD_HOVER};
            border-color: {TechColors.ACCENT_BLUE}66;
        }}
    """

    def __init__(self, exercise: VocalExercise, parent=None):
        super().__init__(parent)
        self._exercise = exercise
        self._selected = False
        self._init_card()

    def _init_card(self):
        e = self._exercise
        self.setObjectName("exercise_card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._CARD_BASE)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(16, 14, 16, 14)

        # 行1: 星级 + 难度 + 分类
        r1 = QHBoxLayout()
        r1.setSpacing(8)

        star = QLabel(e.star_display)
        star.setStyleSheet(f"color: {TechColors.STAR_FILLED}; font-size: 12px;")
        r1.addWidget(star)

        tc, bc = TechColors.diff_color(e.difficulty_label)
        diff = QLabel(e.difficulty_label)
        diff.setStyleSheet(
            f"color: {tc}; background-color: {bc}; "
            f"font-size: 10px; font-weight: bold; border-radius: 3px; padding: 1px 6px;"
        )
        r1.addWidget(diff)

        r1.addStretch()

        cat_text = e.category_name.split(" ")[-1] if " " in e.category_name else e.category_name
        cat = QLabel(cat_text)
        cat.setStyleSheet(f"color: {TechColors.TEXT_SECONDARY}; font-size: 11px;")
        r1.addWidget(cat)

        layout.addLayout(r1)

        # 行2: 名称
        name = QLabel(e.name)
        name.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        name.setStyleSheet(f"color: {TechColors.TEXT_PRIMARY};")
        layout.addWidget(name)

        # 行3: 描述
        desc_text = e.description.split("。")[0] + "。" if "。" in e.description else e.description[:72]
        desc = QLabel(desc_text)
        desc.setStyleSheet(f"color: {TechColors.TEXT_SECONDARY}; font-size: 11px;")
        desc.setWordWrap(True)
        desc.setMaximumHeight(28)
        layout.addWidget(desc)

        # 行4: 小贴士 + 信息
        r4 = QHBoxLayout()
        r4.setSpacing(6)
        if e.tip:
            tip = QLabel(f"💡 {e.tip[:42]}{'...' if len(e.tip) > 42 else ''}")
            tip.setStyleSheet(f"color: {TechColors.TEXT_SECONDARY}; font-size: 10px;")
            r4.addWidget(tip)
        r4.addStretch()
        info = QLabel(f"{e.note_count}音 · {e.key}调 · BPM{e.tempo} · {e.duration_seconds:.0f}s")
        info.setStyleSheet(f"color: {TechColors.TEXT_SECONDARY}; font-size: 10px;")
        r4.addWidget(info)
        layout.addLayout(r4)

    @property
    def exercise_id(self) -> str:
        return self._exercise.id

    def mousePressEvent(self, event):
        self.clicked.emit(self._exercise.id)
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════
#  分类侧边栏按钮（现代风格）
# ══════════════════════════════════════════════════════════

class CategoryChip(QPushButton):
    """现代侧边栏分类按钮 — 图标 + 标签 + 计数"""

    def __init__(self, cat_key: str, cat_info: dict, count: int, parent=None):
        super().__init__(parent)
        self._cat_key = cat_key
        self._active = False
        self._icon = cat_info.get("icon", "")
        self._name = cat_info.get("name", cat_key).split(" ")[-1] if " " in cat_info.get("name", "") else cat_info.get("name", cat_key)
        self._count = count
        self.setText(f"  {self._icon}  {self._name}  ·  {count}")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(cat_info.get("desc", ""))
        self._update_style()

    def set_active(self, active: bool):
        self._active = active
        self.setChecked(active)
        self._update_style()

    def _update_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {TechColors.ACCENT_BLUE}30, stop:1 {TechColors.ACCENT_PURPLE}25);
                    border: none;
                    border-left: 3px solid {TechColors.ACCENT_BLUE};
                    border-radius: 0 6px 6px 0;
                    padding: 8px 16px;
                    text-align: left;
                    color: {TechColors.TEXT_PRIMARY};
                    font-size: 12px;
                    font-weight: bold;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    border-left: 3px solid transparent;
                    border-radius: 0;
                    padding: 8px 16px;
                    text-align: left;
                    color: {TechColors.TEXT_SECONDARY};
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {TechColors.ACCENT_BLUE}15;
                    color: {TechColors.TEXT_PRIMARY};
                }}
            """)


# ══════════════════════════════════════════════════════════
#  等级标签（顶部筛选 chip）
# ══════════════════════════════════════════════════════════

class LevelChip(QPushButton):
    """等级筛选标签按钮"""

    def __init__(self, level_key: str, label: str, parent=None):
        super().__init__(label, parent)
        self._level_key = level_key
        self._active = (level_key == "all")
        self.setCheckable(True)
        self.setChecked(self._active)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        self._update_style()

    def set_active(self, active: bool):
        self._active = active
        self.setChecked(active)
        self._update_style()

    def _update_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {TechColors.ACCENT_BLUE}30;
                    border: 1px solid {TechColors.ACCENT_BLUE}80;
                    border-radius: 14px;
                    padding: 4px 14px;
                    color: {TechColors.ACCENT_BLUE};
                    font-size: 11px;
                    font-weight: bold;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid {TechColors.BORDER_DEFAULT};
                    border-radius: 14px;
                    padding: 4px 14px;
                    color: {TechColors.TEXT_SECONDARY};
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    border-color: {TechColors.ACCENT_BLUE}50;
                    color: {TechColors.TEXT_PRIMARY};
                }}
            """)


# ══════════════════════════════════════════════════════════
#  主浏览器窗口
# ══════════════════════════════════════════════════════════

class ExerciseBrowser(QDialog):
    """练声练习浏览器 — 现代科技暗色风格"""

    exercise_selected = pyqtSignal(str)  # exercise_id

    def __init__(self, parent=None, on_start_exercise: Callable[[str], None] = None):
        super().__init__(parent)
        self._on_start_exercise = on_start_exercise
        self._all_exercises = list_all_exercises()
        self._current_category = "all"
        self._current_level = "all"
        self._search_text = ""
        self._selected_id: Optional[str] = None
        self._category_buttons: dict[str, CategoryChip] = {}
        self._level_chips: dict[str, LevelChip] = {}
        self._card_widgets: dict[str, ExerciseCard] = {}

        self._init_window()
        self._build_ui()
        self._populate_cards()

    def _init_window(self):
        self.setWindowTitle("练声练习浏览器")
        self.setMinimumSize(880, 620)
        self.resize(960, 680)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {TechColors.BG_DARK};
            }}
            QLabel {{
                color: {TechColors.TEXT_PRIMARY};
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {TechColors.BORDER_DEFAULT};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {TechColors.TEXT_SECONDARY};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── 顶部渐变标题栏 ──
        header = QFrame()
        header.setFixedHeight(56)
        header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0D1B2A, stop:0.4 #1A1F35, stop:0.7 #1F1A3A, stop:1 #1A1028);
                border: none;
                border-bottom: 1px solid {TechColors.BORDER_DEFAULT};
            }}
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 16, 0)

        title = QLabel("🎵  练声练习浏览器")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TechColors.TEXT_PRIMARY};")
        hl.addWidget(title)

        hl.addStretch()

        # 搜索框
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索练习...")
        self._search_input.setFixedWidth(220)
        self._search_input.setFixedHeight(32)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {TechColors.BG_SEARCH};
                border: 1px solid {TechColors.BORDER_DEFAULT};
                border-radius: 16px;
                padding: 6px 16px;
                color: {TechColors.TEXT_PRIMARY};
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {TechColors.ACCENT_BLUE};
            }}
        """)
        self._search_input.textChanged.connect(self._on_search)
        hl.addWidget(self._search_input)

        outer.addWidget(header)

        # ── 等级筛选栏 ──
        level_bar = QFrame()
        level_bar.setFixedHeight(44)
        level_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {TechColors.BG_SEARCH};
                border: none;
                border-bottom: 1px solid {TechColors.BORDER_DEFAULT};
            }}
        """)
        ll = QHBoxLayout(level_bar)
        ll.setContentsMargins(20, 6, 20, 6)
        ll.setSpacing(8)

        filter_label = QLabel("等级：")
        filter_label.setStyleSheet(f"color: {TechColors.TEXT_SECONDARY}; font-size: 11px;")
        ll.addWidget(filter_label)

        levels = [
            ("all", "全部"),
            ("beginner", "⭐ 入门"),
            ("intermediate", "⭐⭐ 初级·进阶"),
            ("advanced", "⭐⭐⭐⭐ 中·高级"),
        ]
        for key, text in levels:
            chip = LevelChip(key, text)
            chip.clicked.connect(lambda checked, k=key: self._on_level_changed(k))
            self._level_chips[key] = chip
            ll.addWidget(chip)

        ll.addStretch()
        self._result_label = QLabel()
        self._result_label.setStyleSheet(f"color: {TechColors.TEXT_SECONDARY}; font-size: 11px;")
        ll.addWidget(self._result_label)

        outer.addWidget(level_bar)

        # ── 主体：左分类导航 + 右卡片区 ──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # 左侧：分类导航面板
        sidebar = self._build_sidebar()
        body.addWidget(sidebar)

        # 分隔线
        div = QFrame()
        div.setFixedWidth(1)
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet(f"background-color: {TechColors.BORDER_DEFAULT};")
        body.addWidget(div)

        # 右侧：卡片滚动区
        content = self._build_content_area()
        body.addWidget(content, stretch=1)

        outer.addLayout(body, stretch=1)

        # ── 底部操作栏 ──
        footer = self._build_footer()
        outer.addWidget(footer)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setMinimumWidth(185)
        sidebar.setFixedWidth(200)
        sidebar.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {TechColors.BG_DARKEST};
                border: none;
            }}
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 14, 0, 14)
        layout.setSpacing(1)

        # 导航标题
        nav_title = QLabel("  分 类 导 航")
        nav_title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        nav_title.setStyleSheet(f"color: {TechColors.TEXT_PRIMARY}; padding: 8px 16px;")
        layout.addWidget(nav_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {TechColors.BORDER_DEFAULT}; margin: 4px 14px;")
        layout.addWidget(sep)

        layout.addSpacing(6)

        # "全部"按钮
        all_btn = CategoryChip("all", {
            "name": "全部练习",
            "icon": "📋",
            "desc": "浏览所有练声练习",
        }, len(self._all_exercises))
        all_btn.clicked.connect(lambda: self._on_category_clicked("all"))
        all_btn.set_active(True)
        self._category_buttons["all"] = all_btn
        layout.addWidget(all_btn)

        layout.addSpacing(3)

        # 各分类
        summary = get_category_summary()
        for s in summary:
            btn = CategoryChip(s["key"], s, s["count"])
            btn.clicked.connect(lambda checked, k=s["key"]: self._on_category_clicked(k))
            self._category_buttons[s["key"]] = btn
            layout.addWidget(btn)

        layout.addStretch()

        return sidebar

    def _build_content_area(self) -> QFrame:
        content = QFrame()
        content.setStyleSheet(f"background-color: {TechColors.BG_DARK}; border: none;")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._card_container = QWidget()
        self._card_container.setStyleSheet("background: transparent;")
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setSpacing(10)
        self._card_layout.setContentsMargins(0, 0, 10, 0)
        self._card_layout.addStretch()

        scroll.setWidget(self._card_container)
        layout.addWidget(scroll, stretch=1)

        return content

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setFixedHeight(52)
        footer.setStyleSheet(f"""
            QFrame {{
                background-color: {TechColors.BG_FOOTER};
                border-top: 1px solid {TechColors.BORDER_DEFAULT};
            }}
        """)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 8, 20, 8)

        self._selection_label = QLabel("选择一项练习后点击「开始练声」")
        self._selection_label.setStyleSheet(
            f"color: {TechColors.TEXT_SECONDARY}; font-size: 12px;"
        )
        fl.addWidget(self._selection_label)

        fl.addStretch()

        self._start_btn = QPushButton("开始练声")
        self._start_btn.setFixedHeight(34)
        self._start_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {TechColors.ACCENT_BLUE}, stop:1 {TechColors.ACCENT_PURPLE});
                border: none;
                border-radius: 6px;
                padding: 8px 28px;
                color: white;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6DB9FF, stop:1 #BBA0FF);
            }}
            QPushButton:disabled {{
                background: {TechColors.BORDER_DEFAULT};
                color: {TechColors.TEXT_SECONDARY};
            }}
        """)
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._on_start_clicked)
        fl.addWidget(self._start_btn)

        return footer

    # ── 填充卡片 ──────────────────────────────────────

    def _populate_cards(self):
        while self._card_layout.count() > 1:
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._card_widgets.clear()

        exercises = self._filter_exercises()
        self._result_label.setText(f"共 {len(exercises)} 项")

        for e in exercises:
            card = ExerciseCard(e)
            card.clicked.connect(self._on_card_clicked)
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)
            self._card_widgets[e.id] = card

    def _filter_exercises(self) -> list:
        result = self._all_exercises
        if self._current_category != "all":
            result = get_exercises_by_category(self._current_category)
        if self._current_level != "all":
            result = [e for e in result
                      if e.id in {ex.id for ex in get_exercises_by_level(self._current_level)}]
        if self._search_text:
            q = self._search_text.lower()
            result = [e for e in result
                      if q in e.name.lower()
                      or q in e.description.lower()
                      or q in e.category_name.lower()
                      or any(q in t.lower() for t in e.tags)]
        return sorted(result, key=lambda e: (e.difficulty, e.name))

    # ── 事件 ──────────────────────────────────────────

    def _on_category_clicked(self, cat_key: str):
        self._current_category = cat_key
        for k, btn in self._category_buttons.items():
            btn.set_active(k == cat_key)
        self._populate_cards()

    def _on_level_changed(self, level_key: str):
        self._current_level = level_key
        for k, chip in self._level_chips.items():
            chip.set_active(k == level_key)
        self._populate_cards()

    def _on_search(self, text: str):
        self._search_text = text.strip()
        self._populate_cards()

    def _on_card_clicked(self, exercise_id: str):
        self._selected_id = exercise_id
        for eid, card in self._card_widgets.items():
            if eid == exercise_id:
                card.setStyleSheet(f"""
                    #exercise_card {{
                        background-color: {TechColors.BG_CARD_HOVER};
                        border: 2px solid {TechColors.ACCENT_BLUE};
                        border-radius: 8px;
                    }}
                """)
            else:
                card.setStyleSheet(ExerciseCard._CARD_BASE)

        match = [e for e in self._all_exercises if e.id == exercise_id]
        if match:
            e = match[0]
            self._selection_label.setText(
                f"已选：{e.name}    {e.star_display}    {e.category_name}"
            )
            self._selection_label.setStyleSheet(
                f"color: {TechColors.TEXT_ACCENT}; font-size: 12px; font-weight: bold;"
            )
            self._start_btn.setEnabled(True)

    def _on_start_clicked(self):
        if not self._selected_id:
            return
        self.exercise_selected.emit(self._selected_id)
        if self._on_start_exercise:
            self._on_start_exercise(self._selected_id)
        self.accept()

    def get_selected_exercise_id(self) -> Optional[str]:
        return self._selected_id


# ══════════════════════════════════════════════════════════
#  便捷调用
# ══════════════════════════════════════════════════════════

def open_exercise_browser(
    parent=None,
    on_select: Callable[[str], None] = None,
) -> Optional[str]:
    browser = ExerciseBrowser(parent, on_start_exercise=on_select)
    if browser.exec() == QDialog.DialogCode.Accepted:
        return browser.get_selected_exercise_id()
    return None
