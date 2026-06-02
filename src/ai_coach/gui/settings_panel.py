"""AI 教练设置面板 —— API 配置 + 教练身份定制"""

from __future__ import annotations

from typing import Optional

# PyQt6 / PyQt5 双兼容
try:
    from PyQt6.QtWidgets import (
        QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QComboBox, QSlider, QSpinBox,
        QPushButton, QTextEdit, QFormLayout, QGroupBox,
        QCheckBox, QMessageBox, QFrame, QScrollArea, QSizePolicy,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt6.QtGui import QFont, QIcon
    _QT6 = True
except ImportError:
    from PyQt5.QtWidgets import (
        QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QComboBox, QSlider, QSpinBox,
        QPushButton, QTextEdit, QFormLayout, QGroupBox,
        QCheckBox, QMessageBox, QFrame, QScrollArea, QSizePolicy,
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt5.QtGui import QFont, QIcon
    _QT6 = False

# PyQt5/PyQt6 枚举兼容
_ALIGN_RIGHT = Qt.AlignmentFlag.AlignRight if _QT6 else Qt.AlignRight
_ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter if _QT6 else Qt.AlignCenter
_FRAME_NOFRAME = QFrame.Shape.NoFrame if _QT6 else QFrame.NoFrame
_FRAME_HLINE = QFrame.Shape.HLine if _QT6 else QFrame.HLine
_ECHO_PASSWORD = QLineEdit.EchoMode.Password if _QT6 else QLineEdit.Password
_ECHO_NORMAL = QLineEdit.EchoMode.Normal if _QT6 else QLineEdit.Normal
_ORIENT_HORIZONTAL = Qt.Orientation.Horizontal if _QT6 else Qt.Horizontal

from ..config import AppConfig, LLMProviderConfig, ConfigManager
from ..identity import CoachIdentity, DEFAULT_IDENTITY, AVATAR_THEMES, AVATAR_CHARACTERS
from .mascot_svg import THEMES as MASCOT_THEMES, DEFAULT_THEME, CHARACTERS, get_svg


# ═══════════════════════════════════════════════════════════════
# 样式常量
# ═══════════════════════════════════════════════════════════════

_PRIMARY = "#7C5CFC"
_PRIMARY_LIGHT = "#A78BFA"
_PRIMARY_DARK = "#5B3FD9"
_BG_DARK = "#1a1a2e"
_BG_CARD = "#222240"
_BG_INPUT = "#16162A"
_BORDER = "#3a3a5a"
_BORDER_FOCUS = "#7C5CFC"
_TEXT_PRIMARY = "#e8e8f0"
_TEXT_SECONDARY = "#9999aa"
_TEXT_HINT = "#7777aa"
_SUCCESS = "#4ADE80"
_DANGER = "#F87171"
_WARNING = "#FBBF24"
_RADIUS = "8px"
_RADIUS_SM = "5px"


# ═══════════════════════════════════════════════════════════════
# 通用样式表
# ═══════════════════════════════════════════════════════════════

def _dialog_style() -> str:
    return f"""
        QDialog {{
            background-color: {_BG_DARK};
            color: {_TEXT_PRIMARY};
        }}
        QLabel {{
            color: {_TEXT_PRIMARY};
        }}
        QGroupBox {{
            background-color: {_BG_CARD};
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS};
            margin-top: 16px;
            padding: 20px 16px 14px 16px;
            font-size: 13px;
            font-weight: bold;
            color: {_PRIMARY_LIGHT};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 2px 10px;
            background-color: {_BG_DARK};
            border: 1px solid {_BORDER};
            border-radius: 4px;
            left: 12px;
        }}
        QLineEdit, QTextEdit, QSpinBox, QComboBox {{
            background-color: {_BG_INPUT};
            color: {_TEXT_PRIMARY};
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS_SM};
            padding: 7px 10px;
            font-size: 13px;
            selection-background-color: {_PRIMARY};
        }}
        QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border-color: {_BORDER_FOCUS};
        }}
        QComboBox {{
            min-height: 22px;
        }}
        QComboBox::drop-down {{
            border: none;
            padding-right: 8px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {_BG_CARD};
            color: {_TEXT_PRIMARY};
            border: 1px solid {_BORDER};
            selection-background-color: {_PRIMARY};
            border-radius: 4px;
        }}
        QTabWidget::pane {{
            background-color: {_BG_DARK};
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS};
            border-top-left-radius: 0;
        }}
        QTabBar::tab {{
            background-color: {_BG_CARD};
            color: {_TEXT_SECONDARY};
            border: 1px solid {_BORDER};
            border-bottom: none;
            padding: 8px 20px;
            margin-right: 2px;
            font-size: 13px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
        }}
        QTabBar::tab:selected {{
            background-color: {_BG_DARK};
            color: {_PRIMARY_LIGHT};
            border-bottom: 2px solid {_PRIMARY};
        }}
        QTabBar::tab:hover:!selected {{
            color: {_TEXT_PRIMARY};
            background-color: #2a2a4a;
        }}
        QSlider::groove:horizontal {{
            border: none;
            height: 6px;
            background-color: {_BG_INPUT};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {_PRIMARY_LIGHT}, stop:1 {_PRIMARY_DARK});
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
            border: 2px solid {_PRIMARY_LIGHT};
        }}
        QSlider::handle:horizontal:hover {{
            border-color: #fff;
        }}
        QSlider::sub-page:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {_PRIMARY_DARK}, stop:1 {_PRIMARY_LIGHT});
            border-radius: 3px;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            background-color: {_BG_CARD};
            border: 1px solid {_BORDER};
            border-radius: 2px;
            width: 16px;
        }}
    """


def _primary_btn_style() -> str:
    return f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {_PRIMARY_LIGHT}, stop:1 {_PRIMARY});
            color: white;
            border: none;
            border-radius: {_RADIUS_SM};
            padding: 8px 20px;
            font-size: 13px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #C4B5FD, stop:1 {_PRIMARY_LIGHT});
        }}
        QPushButton:pressed {{
            background: {_PRIMARY_DARK};
        }}
    """


def _secondary_btn_style() -> str:
    return f"""
        QPushButton {{
            background: transparent;
            color: {_TEXT_SECONDARY};
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS_SM};
            padding: 8px 20px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            color: {_TEXT_PRIMARY};
            border-color: {_PRIMARY_LIGHT};
        }}
    """


def _danger_btn_style() -> str:
    return f"""
        QPushButton {{
            background: transparent;
            color: {_DANGER};
            border: 1px solid {_DANGER};
            border-radius: {_RADIUS_SM};
            padding: 8px 20px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: rgba(248, 113, 113, 0.1);
        }}
    """


# ── 预设 ──────────────────────────────────────────────────────

PROVIDER_PRESETS = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/anthropic",
        "models": ["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat"],
    },
    "anthropic": {
        "name": "Anthropic",
        "base_url": "https://api.anthropic.com",
        "models": ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-7"],
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1"],
    },
    "ollama": {
        "name": "Ollama (本地)",
        "base_url": "http://localhost:11434/v1",
        "models": ["llama3.2", "qwen3", "mistral", "gemma3", "deepseek-r1"],
    },
    "custom": {
        "name": "自定义",
        "base_url": "",
        "models": [],
    },
}

PERSONALITIES = ["温暖鼓励", "严格专业", "幽默风趣", "简洁直接", "自定义"]


# ═══════════════════════════════════════════════════════════════
# API 配置标签页
# ═══════════════════════════════════════════════════════════════

class _APITab(QWidget):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_FRAME_NOFRAME)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)

        # ── 提供商 ──
        provider_group = QGroupBox("LLM 提供商")
        form = QFormLayout(provider_group)
        form.setLabelAlignment(_ALIGN_RIGHT)
        form.setSpacing(12)

        # 提供商选择 + 模型行（水平排列更紧凑）
        provider_row = QHBoxLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.setMinimumWidth(130)
        for key, preset in PROVIDER_PRESETS.items():
            self.provider_combo.addItem(preset["name"], key)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_row.addWidget(QLabel("提供商"))
        provider_row.addWidget(self.provider_combo)
        provider_row.addStretch()
        form.addRow(provider_row)

        # API 密钥
        key_layout = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(_ECHO_PASSWORD)
        self.api_key_input.setPlaceholderText("输入 API 密钥...")
        key_layout.addWidget(self.api_key_input)

        show_key_btn = QPushButton("👁")
        show_key_btn.setFixedSize(32, 32)
        show_key_btn.setCheckable(True)
        show_key_btn.setToolTip("显示/隐藏密钥")
        show_key_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_BG_CARD}; color: {_TEXT_SECONDARY};
                border: 1px solid {_BORDER}; border-radius: {_RADIUS_SM};
            }}
            QPushButton:hover {{ border-color: {_PRIMARY_LIGHT}; }}
            QPushButton:checked {{ background: {_PRIMARY_DARK}; color: white; }}
        """)
        show_key_btn.toggled.connect(
            lambda checked: self.api_key_input.setEchoMode(
                _ECHO_NORMAL if checked else _ECHO_PASSWORD
            )
        )
        key_layout.addWidget(show_key_btn)
        form.addRow("API 密钥", key_layout)

        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.deepseek.com/anthropic")
        form.addRow("Base URL", self.base_url_input)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        form.addRow("模型", self.model_combo)

        layout.addWidget(provider_group)

        # ── 参数 ──
        param_group = QGroupBox("调用参数")
        param_form = QFormLayout(param_group)
        param_form.setSpacing(12)

        # Temperature
        temp_row = QHBoxLayout()
        self.temp_slider = QSlider(_ORIENT_HORIZONTAL)
        self.temp_slider.setRange(0, 200)
        self.temp_slider.setSingleStep(5)
        self.temp_slider.setValue(int(self._config.llm.temperature * 100))
        self.temp_label = QLabel(f"{self._config.llm.temperature:.2f}")
        self.temp_label.setFixedWidth(38)
        self.temp_label.setAlignment(_ALIGN_CENTER)
        self.temp_label.setStyleSheet(f"""
            QLabel {{
                background: {_BG_INPUT}; color: {_PRIMARY_LIGHT};
                border-radius: 4px; padding: 3px 6px;
                font-weight: bold; font-size: 12px;
            }}
        """)
        self.temp_slider.valueChanged.connect(
            lambda v: self.temp_label.setText(f"{v / 100:.2f}")
        )
        temp_row.addWidget(self.temp_slider)
        temp_row.addWidget(self.temp_label)
        # 添加快速预设
        temp_presets = QHBoxLayout()
        for val, label_text in [(0.3, "精确"), (0.7, "平衡"), (1.0, "创意"), (1.5, "发散")]:
            btn = QPushButton(label_text)
            btn.setFixedSize(42, 24)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {_BG_INPUT}; color: {_TEXT_SECONDARY};
                    border: 1px solid {_BORDER}; border-radius: 3px;
                    font-size: 11px; padding: 2px 4px;
                }}
                QPushButton:hover {{ color: {_TEXT_PRIMARY}; border-color: {_PRIMARY_LIGHT}; }}
            """)
            btn.clicked.connect(lambda checked, v=val: self.temp_slider.setValue(int(v * 100)))
            temp_presets.addWidget(btn)
        temp_presets.addStretch()

        param_form.addRow("Temperature", temp_row)
        param_form.addRow("", temp_presets)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(256, 32768)
        self.max_tokens_spin.setSingleStep(256)
        self.max_tokens_spin.setValue(self._config.llm.max_tokens)
        param_form.addRow("Max Tokens", self.max_tokens_spin)

        layout.addWidget(param_group)

        # ── 测试连接 ──
        test_row = QHBoxLayout()
        self.test_btn = QPushButton(" 测试连接")
        self.test_btn.setStyleSheet(_secondary_btn_style())
        self.test_status = QLabel("")
        self.test_status.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 12px;")
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_status)
        test_row.addStretch()
        layout.addLayout(test_row)
        layout.addStretch()

        self.test_btn.clicked.connect(self._on_test_connection)

        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._load_config()

    def _load_config(self):
        llm = self._config.llm
        idx = self.provider_combo.findData(llm.provider or "deepseek")
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        else:
            self.provider_combo.setCurrentIndex(self.provider_combo.findData("custom"))
        self.api_key_input.setText(llm.api_key)
        self.base_url_input.setText(llm.base_url)
        if llm.model:
            self.model_combo.setCurrentText(llm.model)
        self.temp_slider.setValue(int(llm.temperature * 100))
        self.max_tokens_spin.setValue(llm.max_tokens)

    def _on_provider_changed(self, idx: int):
        provider_key = self.provider_combo.itemData(idx)
        if not provider_key:
            return
        preset = PROVIDER_PRESETS.get(provider_key, {})
        if preset.get("base_url"):
            self.base_url_input.setText(preset["base_url"])
        self.model_combo.clear()
        for m in preset.get("models", []):
            self.model_combo.addItem(m)
        if provider_key == "custom":
            self.model_combo.setEditable(True)
            self.base_url_input.setText("")
            self.base_url_input.setPlaceholderText("输入自定义端点 URL...")

    def _show_test_result(self, success: bool, detail: str):
        if success:
            self.test_status.setStyleSheet(
                f"color: {_SUCCESS}; font-size: 12px; font-weight: bold;"
            )
            self.test_status.setText(f"  {detail}")
        else:
            self.test_status.setStyleSheet(
                f"color: {_DANGER}; font-size: 12px; font-weight: bold;"
            )
            self.test_status.setText(f"  {detail}")
        QTimer.singleShot(5000, lambda: self.test_status.setText(""))

    def _on_test_connection(self):
        """在后台线程中测试 LLM 连接，避免阻塞 UI。"""
        cfg = self.collect_config()
        self.test_btn.setEnabled(False)
        self.test_status.setStyleSheet(f"color: {_WARNING}; font-size: 12px;")
        self.test_status.setText("  正在测试...")

        class _TestWorker(QThread):
            result_signal = pyqtSignal(bool, str)

            def __init__(self, llm_cfg):
                super().__init__()
                self.llm_cfg = llm_cfg

            def run(self):
                try:
                    from ...llm_client import LLMClient, LLMConfig
                    config = LLMConfig(
                        api_key=self.llm_cfg.api_key,
                        base_url=self.llm_cfg.base_url,
                        model=self.llm_cfg.model,
                        max_tokens=64,
                        temperature=0.1,
                        timeout=15,
                        provider=self.llm_cfg.provider,
                    )
                    client = LLMClient(config)
                    result = client.chat(
                        [{"role": "user", "content": "hi"}],
                        system="Reply with just 'OK'.",
                        max_tokens=32,
                    )
                    if result and len(result.strip()) > 0:
                        self.result_signal.emit(True, f"连接成功 ({config.model})")
                    else:
                        self.result_signal.emit(False, "API 返回了空响应")
                except Exception as e:
                    msg = str(e)[:120]
                    self.result_signal.emit(False, f"连接失败: {msg}")

        self._test_worker = _TestWorker(cfg)
        self._test_worker.result_signal.connect(self._on_test_result)
        self._test_worker.finished.connect(lambda: self.test_btn.setEnabled(True))
        self._test_worker.start()

    def _on_test_result(self, success: bool, detail: str):
        self._show_test_result(success, detail)

    def collect_config(self) -> LLMProviderConfig:
        provider = self.provider_combo.currentData() or "deepseek"
        temp = self.temp_slider.value() / 100.0
        return LLMProviderConfig(
            provider=provider,
            api_key=self.api_key_input.text().strip(),
            base_url=self.base_url_input.text().strip(),
            model=self.model_combo.currentText().strip(),
            max_tokens=self.max_tokens_spin.value(),
            temperature=temp,
        )


# ═══════════════════════════════════════════════════════════════
# 教练身份标签页
# ═══════════════════════════════════════════════════════════════

class _IdentityTab(QWidget):
    """教练身份定制 —— 名称、性格、形象（角色+主题）"""

    def __init__(self, identity: CoachIdentity, parent=None):
        super().__init__(parent)
        self._identity = identity
        self._current_theme = identity.avatar_theme or DEFAULT_THEME
        # 从当前主题推断选中的角色
        current_palette = MASCOT_THEMES.get(self._current_theme, MASCOT_THEMES[DEFAULT_THEME])
        self._current_character = current_palette.get("character", "maimai")
        self._preview_svg: Optional[object] = None  # QSvgWidget ref
        self._preview_expr_widgets: dict = {}  # expression thumbnails
        self._current_preview_expr: str = "idle"  # 当前大预览的表情
        self._init_ui()

    def _init_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── 左侧：设置区域 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_FRAME_NOFRAME)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)

        # ── 基本信息 ──
        info_group = QGroupBox("基本信息")
        form = QFormLayout(info_group)
        form.setSpacing(12)

        self.name_input = QLineEdit()
        self.name_input.setText(self._identity.name)
        self.name_input.setPlaceholderText("例如：麦麦、声乐教练...")
        form.addRow("教练名称", self.name_input)

        self.display_name_input = QLineEdit()
        self.display_name_input.setText(self._identity.display_name)
        self.display_name_input.setPlaceholderText("例如：麦麦、音符精灵...")
        form.addRow("吉祥物名称", self.display_name_input)

        self.personality_combo = QComboBox()
        self.personality_combo.setEditable(True)
        for p in PERSONALITIES:
            self.personality_combo.addItem(p)
        idx = self.personality_combo.findText(self._identity.personality)
        if idx >= 0:
            self.personality_combo.setCurrentIndex(idx)
        else:
            self.personality_combo.setCurrentText(self._identity.personality)
        form.addRow("性格风格", self.personality_combo)

        layout.addWidget(info_group)

        # ── 角色选择器 ──
        char_group = QGroupBox("选择桌宠角色")
        char_layout = QVBoxLayout(char_group)

        char_desc = QLabel("每个角色都有独特的外形和配件，选择一个你喜欢的吧！")
        char_desc.setStyleSheet(f"color: {_TEXT_HINT}; font-size: 11px; padding-bottom: 6px;")
        char_layout.addWidget(char_desc)

        # 角色卡片行
        char_cards = QHBoxLayout()
        char_cards.setSpacing(10)

        self._char_buttons: dict[str, QPushButton] = {}
        char_emojis = {"maimai": "", "tuantuan": "", "yinyin": "",
                       "qiuqiu": "", "mianmian": ""}
        for char_key, char_info in CHARACTERS.items():
            card = self._make_character_card(char_key, char_info)
            self._char_buttons[char_key] = card
            char_cards.addWidget(card)

        char_layout.addLayout(char_cards)
        layout.addWidget(char_group)

        # ── 主题颜色选择器 ──
        self._color_group = QGroupBox("选择配色方案")
        self._color_layout = QVBoxLayout(self._color_group)
        self._color_layout.setSpacing(8)

        self._color_desc = QLabel("")
        self._color_desc.setStyleSheet(f"color: {_TEXT_HINT}; font-size: 11px;")
        self._color_layout.addWidget(self._color_desc)

        self._theme_buttons_layout = QHBoxLayout()
        self._theme_buttons_layout.setSpacing(10)
        self._color_layout.addLayout(self._theme_buttons_layout)

        # 色块展示
        self._palette_row = QHBoxLayout()
        self._palette_row.setSpacing(4)
        self._palette_swatches: list[QFrame] = []
        for _ in range(7):
            swatch = QFrame()
            swatch.setFixedSize(18, 18)
            swatch.setStyleSheet(f"border: 1px solid {_BORDER}; border-radius: 9px;")
            self._palette_swatches.append(swatch)
            self._palette_row.addWidget(swatch)
        self._palette_row.addStretch()
        self._color_layout.addLayout(self._palette_row)

        layout.addWidget(self._color_group)

        # 初始化：显示当前角色对应的主题
        self._theme_buttons: dict[str, QPushButton] = {}
        self._refresh_theme_cards()

        # ── 欢迎语 ──
        greeting_group = QGroupBox("欢迎语模板")
        greeting_layout = QVBoxLayout(greeting_group)
        greeting_hint = QLabel("可用变量: {name} = 教练名称")
        greeting_hint.setStyleSheet(f"color: {_TEXT_HINT}; font-size: 11px; padding-bottom: 4px;")
        self.greeting_edit = QTextEdit()
        self.greeting_edit.setPlainText(self._identity.greeting_template)
        self.greeting_edit.setMaximumHeight(160)
        self.greeting_edit.setPlaceholderText("你好！我是{name}，你的AI声乐教练...")
        greeting_layout.addWidget(greeting_hint)
        greeting_layout.addWidget(self.greeting_edit)
        layout.addWidget(greeting_group)

        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)  # stretch=1: 设置区域占据剩余空间

        # ── 右侧：形象实时预览 ──
        self._preview_panel = self._build_preview_panel()
        outer.addWidget(self._preview_panel)
        # 初始化预览
        self._update_preview()

    def _build_preview_panel(self) -> QFrame:
        """构建右侧形象预览面板"""
        panel = QFrame()
        panel.setFixedWidth(220)
        panel.setStyleSheet(f"""
            QFrame {{
                background: {_BG_CARD};
                border: 1px solid {_BORDER};
                border-radius: {_RADIUS};
            }}
        """)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(14, 14, 14, 14)
        pv.setSpacing(8)

        # 标题
        title = QLabel("形象预览")
        title.setAlignment(_ALIGN_CENTER)
        title.setStyleSheet(f"color: {_PRIMARY_LIGHT}; font-weight: bold; font-size: 13px;")
        pv.addWidget(title)

        # 核心大预览（idle）
        self._preview_container = QFrame()
        self._preview_container.setFixedSize(180, 180)
        self._preview_container.setStyleSheet(f"""
            QFrame {{
                background: {_BG_DARK};
                border: 2px solid {_BORDER};
                border-radius: 12px;
            }}
        """)
        pc_layout = QVBoxLayout(self._preview_container)
        pc_layout.setContentsMargins(0, 0, 0, 0)
        pc_layout.setAlignment(_ALIGN_CENTER)
        try:
            from PyQt6.QtSvgWidgets import QSvgWidget
            self._preview_svg = QSvgWidget(self._preview_container)
            self._preview_svg.setFixedSize(160, 160)
            pc_layout.addWidget(self._preview_svg, 0, _ALIGN_CENTER)
        except ImportError:
            self._preview_svg = QLabel("🐱")
            self._preview_svg.setAlignment(_ALIGN_CENTER)
            self._preview_svg.setStyleSheet(f"font-size: 64px;")
            pc_layout.addWidget(self._preview_svg, 0, _ALIGN_CENTER)
        pv.addWidget(self._preview_container, 0, _ALIGN_CENTER)

        # 当前角色/主题名称
        self._preview_info = QLabel("")
        self._preview_info.setAlignment(_ALIGN_CENTER)
        self._preview_info.setWordWrap(True)
        self._preview_info.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 11px;")
        pv.addWidget(self._preview_info)

        # 表情小预览行
        expr_label = QLabel("点击表情预览")
        expr_label.setAlignment(_ALIGN_CENTER)
        expr_label.setStyleSheet(f"color: {_TEXT_HINT}; font-size: 10px;")
        pv.addWidget(expr_label)

        expr_row = QHBoxLayout()
        expr_row.setSpacing(6)
        _expr_emoji = [("happy", "😊"), ("singing", "🎤"),
                       ("thinking", "🤔"), ("loved", "😍")]
        for expr_key, emoji in _expr_emoji:
            mini = QPushButton(emoji)
            mini.setFixedSize(36, 36)
            mini.setCheckable(True)
            mini.setChecked(False)  # idle 是默认，其他都不选中
            mini.setToolTip(f"点击预览「{expr_key}」表情")
            mini.setStyleSheet(f"""
                QPushButton {{
                    background: {_BG_DARK};
                    color: {_TEXT_PRIMARY};
                    border: 1px solid {_BORDER};
                    border-radius: 8px;
                    font-size: 18px;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    border: 2px solid {_PRIMARY_LIGHT};
                    background: #2A2A4A;
                }}
                QPushButton:checked {{
                    border: 2px solid #FFD93D;
                    background: #2E2E4A;
                }}
            """)
            mini.clicked.connect(
                lambda checked, k=expr_key: self._on_expression_clicked(k)
            )
            self._preview_expr_widgets[expr_key] = mini
            expr_row.addWidget(mini)
        expr_row.addStretch()
        pv.addLayout(expr_row)

        pv.addStretch()
        return panel

    def _on_expression_clicked(self, expr_key: str):
        """点击表情缩略图 → 切换大预览"""
        if self._current_preview_expr == expr_key:
            # 再次点击同一个 → 回到 idle
            self._current_preview_expr = "idle"
        else:
            self._current_preview_expr = expr_key
        # 更新按钮高亮
        for key, btn in self._preview_expr_widgets.items():
            btn.setChecked(key == self._current_preview_expr)
        self._update_preview()

    def _update_preview(self, expression: str | None = None):
        """刷新右侧形象预览——角色/主题变更时调用。

        Args:
            expression: 要预览的表情名称，默认使用 _current_preview_expr
        """
        expr = expression if expression is not None else self._current_preview_expr
        try:
            # 更新大预览
            if self._preview_svg is not None:
                palette = MASCOT_THEMES.get(self._current_theme, MASCOT_THEMES[DEFAULT_THEME])
                char_key = palette.get("character", "maimai")
                svg_data = get_svg(expr, self._current_theme)
                try:
                    from PyQt6.QtSvgWidgets import QSvgWidget
                    if isinstance(self._preview_svg, QSvgWidget):
                        self._preview_svg.load(svg_data.encode("utf-8"))
                except ImportError:
                    pass
            # 更新信息文本
            palette = MASCOT_THEMES.get(self._current_theme, MASCOT_THEMES[DEFAULT_THEME])
            char_key = palette.get("character", "maimai")
            char_name = AVATAR_CHARACTERS.get(char_key, char_key)
            theme_name = AVATAR_THEMES.get(self._current_theme, self._current_theme)
            # 标注当前表情
            expr_labels = {"idle": "常态", "happy": "开心", "singing": "唱歌",
                           "thinking": "思考", "loved": "心动"}
            expr_display = expr_labels.get(expr, expr)
            self._preview_info.setText(f"{char_name}\n{theme_name}\n[{expr_display}]")
            # 更新 expression thumbnail 高亮
            for key, btn in self._preview_expr_widgets.items():
                btn.setChecked(key == expr)
        except Exception:
            pass

    def _make_character_card(self, char_key: str, char_info: dict) -> QPushButton:
        """创建角色选择卡片"""
        is_selected = (char_key == self._current_character)

        border_color = "#FFD93D" if is_selected else _BORDER
        border_width = "3px" if is_selected else "1px"
        bg_color = "#2E2E4A" if is_selected else _BG_CARD

        btn = QPushButton()
        btn.setFixedSize(90, 80)
        btn.setCheckable(True)
        btn.setChecked(is_selected)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                color: {_TEXT_PRIMARY};
                border: {border_width} solid {border_color};
                border-radius: 12px;
                font-size: 13px;
                font-weight: bold;
                padding-top: 8px;
            }}
            QPushButton:hover {{ border: 2px solid {_PRIMARY_LIGHT}; }}
            QPushButton:checked {{ border: 3px solid #FFD93D; background: #2E2E4A; }}
        """)
        btn.setText(f"{char_info['name']}\n{char_info['desc']}")
        btn.setToolTip(f"{char_info['name']} — {char_info['desc']}")
        btn.clicked.connect(lambda checked, k=char_key: self._on_character_selected(k))
        return btn

    def _on_character_selected(self, char_key: str):
        """选择角色后，刷新其可用配色方案并自动选第一个"""
        self._current_character = char_key
        for key, btn in self._char_buttons.items():
            is_sel = (key == char_key)
            btn.setChecked(is_sel)
            border_color = "#FFD93D" if is_sel else _BORDER
            border_width = "3px" if is_sel else "1px"
            bg_color = "#2E2E4A" if is_sel else _BG_CARD
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg_color}; color: {_TEXT_PRIMARY};
                    border: {border_width} solid {border_color};
                    border-radius: 12px; font-size: 13px; font-weight: bold;
                    padding-top: 8px;
                }}
                QPushButton:hover {{ border: 2px solid {_PRIMARY_LIGHT}; }}
            """)

        # 切换到该角色的第一个主题
        char_themes = self._get_themes_for_character(char_key)
        if char_themes:
            self._on_theme_selected(char_themes[0])

        self._refresh_theme_cards()
        self._update_preview()

    def _get_themes_for_character(self, char_key: str) -> list[str]:
        """获取指定角色的所有主题 key"""
        return [k for k, v in MASCOT_THEMES.items() if v.get("character") == char_key]

    def _refresh_theme_cards(self):
        """重建当前角色的配色方案卡片"""
        # 清除旧按钮
        for btn in self._theme_buttons.values():
            btn.deleteLater()
        self._theme_buttons.clear()

        char_info = CHARACTERS.get(self._current_character, CHARACTERS["maimai"])
        self._color_desc.setText(f"为「{char_info['name']}」选择一个配色：")

        char_themes = self._get_themes_for_character(self._current_character)
        for theme_key in char_themes:
            palette = MASCOT_THEMES[theme_key]
            card = self._make_theme_card(theme_key, palette)
            self._theme_buttons[theme_key] = card
            self._theme_buttons_layout.addWidget(card)

        # 刷新调色盘
        if self._current_theme in MASCOT_THEMES:
            palette = MASCOT_THEMES[self._current_theme]
            for swatch, color_key in zip(self._palette_swatches,
                                          ["body", "body_light", "body_dark", "belly", "cheek", "mic", "scarf"]):
                swatch.setStyleSheet(f"""
                    background: {palette[color_key]};
                    border: 1px solid {_BORDER};
                    border-radius: 9px;
                """)
                swatch.setToolTip(f"{color_key}: {palette[color_key]}")

    def _make_theme_card(self, theme_key: str, palette: dict) -> QPushButton:
        """创建配色方案卡片 — 带渐变背景和角色名"""
        is_selected = (theme_key == self._current_theme)

        body_color = palette["body"]
        body_light = palette["body_light"]

        border_color = "#FFD93D" if is_selected else _BORDER
        border_width = "3px" if is_selected else "1px"

        btn = QPushButton()
        btn.setFixedSize(72, 62)
        btn.setCheckable(True)
        btn.setChecked(is_selected)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {body_light}, stop:0.5 {body_color}, stop:1 {palette.get('body_dark', body_color)});
                color: white;
                border: {border_width} solid {border_color};
                border-radius: 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{ border: 2px solid {_PRIMARY_LIGHT}; }}
            QPushButton:checked {{ border: 3px solid #FFD93D; }}
        """)
        # 提取简短名称（去掉角色前缀）
        short_name = palette["name"].split("·")[-1] if "·" in palette["name"] else palette["name"]
        btn.setText(short_name)
        btn.setToolTip(f"{palette['name']}\n主色: {body_color}")
        btn.clicked.connect(lambda checked, k=theme_key: self._on_theme_selected(k))
        return btn

    def _on_theme_selected(self, theme_key: str):
        self._current_theme = theme_key
        palette = MASCOT_THEMES.get(theme_key, MASCOT_THEMES[DEFAULT_THEME])

        # 同步角色选择
        char_key = palette.get("character", "maimai")
        if char_key != self._current_character:
            self._current_character = char_key
            for key, btn in self._char_buttons.items():
                is_sel = (key == char_key)
                btn.setChecked(is_sel)
                border_color = "#FFD93D" if is_sel else _BORDER
                border_width = "3px" if is_sel else "1px"
                bg_color = "#2E2E4A" if is_sel else _BG_CARD
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {bg_color}; color: {_TEXT_PRIMARY};
                        border: {border_width} solid {border_color};
                        border-radius: 12px; font-size: 13px; font-weight: bold;
                        padding-top: 8px;
                    }}
                    QPushButton:hover {{ border: 2px solid {_PRIMARY_LIGHT}; }}
                """)

        # 更新配色卡片高亮
        for key, btn in self._theme_buttons.items():
            p = MASCOT_THEMES[key]
            is_sel = (key == theme_key)
            btn.setChecked(is_sel)
            border_color = "#FFD93D" if is_sel else _BORDER
            border_width = "3px" if is_sel else "1px"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {p['body_light']}, stop:0.5 {p['body']}, stop:1 {p.get('body_dark', p['body'])});
                    color: white;
                    border: {border_width} solid {border_color};
                    border-radius: 10px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ border: 2px solid {_PRIMARY_LIGHT}; }}
            """)

        # 更新调色盘
        for swatch, color_key in zip(self._palette_swatches,
                                      ["body", "body_light", "body_dark", "belly", "cheek", "mic", "scarf"]):
            swatch.setStyleSheet(f"""
                background: {palette[color_key]};
                border: 1px solid {_BORDER};
                border-radius: 9px;
            """)
            swatch.setToolTip(f"{color_key}: {palette[color_key]}")

        self._update_preview()

    def collect_identity(self) -> CoachIdentity:
        return CoachIdentity(
            name=self.name_input.text().strip() or DEFAULT_IDENTITY.name,
            display_name=self.display_name_input.text().strip() or DEFAULT_IDENTITY.display_name,
            personality=self.personality_combo.currentText().strip() or DEFAULT_IDENTITY.personality,
            avatar_theme=self._current_theme,
            greeting_template=self.greeting_edit.toPlainText().strip() or DEFAULT_IDENTITY.greeting_template,
        )


# ═══════════════════════════════════════════════════════════════
# 设置对话框
# ═══════════════════════════════════════════════════════════════

class CoachSettingsDialog(QDialog):
    """AI 教练设置对话框"""

    def __init__(
        self,
        config: AppConfig,
        config_manager: ConfigManager,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config
        self._config_mgr = config_manager
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("AI 教练设置")
        self.setMinimumSize(720, 600)
        self.resize(780, 680)
        self.setStyleSheet(_dialog_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)

        # ── 标题区 ──
        header = QHBoxLayout()
        title_icon = QLabel("")
        title_icon.setFixedSize(40, 40)
        title_icon.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {_PRIMARY_LIGHT}, stop:1 {_PRIMARY});
            border-radius: 20px;
            font-size: 20px;
        """)
        title_icon.setAlignment(_ALIGN_CENTER)
        title_text = QLabel("AI 声乐教练")
        title_text.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {_TEXT_PRIMARY};"
        )
        title_sub = QLabel("配置 API 与教练身份")
        title_sub.setStyleSheet(f"font-size: 12px; color: {_TEXT_SECONDARY};")

        title_col = QVBoxLayout()
        title_col.addWidget(title_text)
        title_col.addWidget(title_sub)
        header.addLayout(title_col)
        header.addStretch()
        layout.addLayout(header)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setFrameShape(_FRAME_HLINE)
        sep.setStyleSheet(f"background: {_BORDER}; max-height: 1px;")
        layout.addWidget(sep)

        # ── 标签页 ──
        self.tabs = QTabWidget()
        self.api_tab = _APITab(self._config)
        self.identity_tab = _IdentityTab(self._config.identity)
        self.tabs.addTab(self.api_tab, " API 配置")
        self.tabs.addTab(self.identity_tab, " 教练身份")
        layout.addWidget(self.tabs, 1)

        # ── 底部按钮栏 ──
        btn_row = QHBoxLayout()
        self.reset_btn = QPushButton("恢复默认")
        self.reset_btn.setStyleSheet(_danger_btn_style())
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setStyleSheet(_secondary_btn_style())
        self.save_btn = QPushButton("保存设置")
        self.save_btn.setStyleSheet(_primary_btn_style())
        self.save_btn.setDefault(True)

        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        # 信号
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self._on_save)
        self.reset_btn.clicked.connect(self._on_reset)

    def _on_save(self):
        llm_config = self.api_tab.collect_config()
        identity = self.identity_tab.collect_identity()

        self._config.llm = llm_config
        self._config.identity = identity

        self._config_mgr.save(self._config)
        self.accept()

    def _on_reset(self):
        reply = QMessageBox.question(
            self, "确认恢复默认",
            "将恢复所有设置为默认值，此操作不可撤销。\n继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._config_mgr._config_path.unlink(missing_ok=True)
            default = AppConfig()
            self._config.llm = default.llm
            self._config.identity = default.identity
            self.accept()

    def get_config(self) -> AppConfig:
        return self._config
