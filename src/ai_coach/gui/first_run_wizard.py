"""首次启动向导 —— 引导用户完成 API 配置和教练身份设置"""

from __future__ import annotations

from typing import Optional

# PyQt6 / PyQt5 双兼容
try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QComboBox, QPushButton, QStackedWidget, QWidget, QFrame,
        QFormLayout, QSlider, QSpinBox, QMessageBox,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
    from PyQt6.QtGui import QFont, QColor, QPalette
    _QT6 = True
except ImportError:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QComboBox, QPushButton, QStackedWidget, QWidget, QFrame,
        QFormLayout, QSlider, QSpinBox, QMessageBox,
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
    from PyQt5.QtGui import QFont, QColor, QPalette
    _QT6 = False

# 枚举兼容
_ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter if _QT6 else Qt.AlignCenter
_ALIGN_LEFT = Qt.AlignmentFlag.AlignLeft if _QT6 else Qt.AlignLeft
_ALIGN_RIGHT = Qt.AlignmentFlag.AlignRight if _QT6 else Qt.AlignRight
_ECHO_PASSWORD = QLineEdit.EchoMode.Password if _QT6 else QLineEdit.Password
_ECHO_NORMAL = QLineEdit.EchoMode.Normal if _QT6 else QLineEdit.Normal
_FRAME_NOFRAME = QFrame.Shape.NoFrame if _QT6 else QFrame.NoFrame
_FRAME_HLINE = QFrame.Shape.HLine if _QT6 else QFrame.HLine
_ORIENT_HORIZONTAL = Qt.Orientation.Horizontal if _QT6 else Qt.Horizontal

from ..config import AppConfig, LLMProviderConfig, ConfigManager
from ..identity import CoachIdentity, AVATAR_THEMES


# ═══════════════════════════════════════════════════════════════
# 样式常量
# ═══════════════════════════════════════════════════════════════

_PRIMARY = "#7C5CFC"
_PRIMARY_LIGHT = "#A78BFA"
_BG_DARK = "#1a1a2e"
_BG_CARD = "#222240"
_BG_INPUT = "#16162A"
_BORDER = "#3a3a5a"
_TEXT_PRIMARY = "#e8e8f0"
_TEXT_SECONDARY = "#9999aa"
_SUCCESS = "#4ADE80"
_DANGER = "#F87171"
_RADIUS = "8px"


def _wizard_style() -> str:
    return f"""
        QDialog {{
            background-color: {_BG_DARK};
            color: {_TEXT_PRIMARY};
        }}
        QLabel {{
            color: {_TEXT_PRIMARY};
        }}
        QLineEdit {{
            background-color: {_BG_INPUT};
            color: {_TEXT_PRIMARY};
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS};
            padding: 10px 14px;
            font-size: 13px;
        }}
        QLineEdit:focus {{
            border-color: {_PRIMARY};
        }}
        QComboBox {{
            background-color: {_BG_INPUT};
            color: {_TEXT_PRIMARY};
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS};
            padding: 10px 14px;
            font-size: 13px;
        }}
        QComboBox:hover {{
            border-color: {_PRIMARY_LIGHT};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {_BG_CARD};
            color: {_TEXT_PRIMARY};
            border: 1px solid {_BORDER};
            selection-background-color: {_PRIMARY};
            outline: none;
        }}
        QPushButton {{
            background-color: {_PRIMARY};
            color: white;
            border: none;
            border-radius: {_RADIUS};
            padding: 10px 20px;
            font-size: 13px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {_PRIMARY_LIGHT};
        }}
        QPushButton:pressed {{
            background-color: #5B3FD9;
        }}
        QPushButton[secondary="true"] {{
            background-color: transparent;
            color: {_TEXT_SECONDARY};
            border: 1px solid {_BORDER};
        }}
        QPushButton[secondary="true"]:hover {{
            border-color: {_TEXT_PRIMARY};
            color: {_TEXT_PRIMARY};
        }}
        QSlider::groove:horizontal {{
            background: {_BORDER};
            height: 6px;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {_PRIMARY};
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSpinBox {{
            background-color: {_BG_INPUT};
            color: {_TEXT_PRIMARY};
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS};
            padding: 8px;
        }}
    """


# ═══════════════════════════════════════════════════════════════
# API 连接测试线程
# ═══════════════════════════════════════════════════════════════

class _TestWorker(QThread):
    """后台测试 API 连接"""
    result_signal = pyqtSignal(bool, str)

    def __init__(self, provider: str, api_key: str, base_url: str, model: str):
        super().__init__()
        self._provider = provider
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    def run(self):
        try:
            if self._provider in ("anthropic", "deepseek"):
                import anthropic
                url = self._base_url or "https://api.deepseek.com/anthropic"
                client = anthropic.Anthropic(
                    api_key=self._api_key, base_url=url, timeout=15
                )
                response = client.messages.create(
                    model=self._model or "deepseek-v4-pro",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hi"}],
                )
                if response.content:
                    self.result_signal.emit(True, "连接成功！API 响应正常。")
                else:
                    self.result_signal.emit(False, "API 返回了空响应。")
            elif self._provider == "ollama":
                from openai import OpenAI
                url = self._base_url or "http://localhost:11434/v1"
                client = OpenAI(api_key="ollama", base_url=url, timeout=10)
                models = client.models.list()
                if models.data:
                    self.result_signal.emit(True, f"Ollama 连接成功，{len(models.data)} 个模型可用。")
                else:
                    self.result_signal.emit(False, "Ollama 连接成功但没有可用模型。")
            else:
                from openai import OpenAI
                url = self._base_url or "https://api.openai.com/v1"
                client = OpenAI(api_key=self._api_key, base_url=url, timeout=15)
                response = client.chat.completions.create(
                    model=self._model or "gpt-4o",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hi"}],
                )
                if response.choices:
                    self.result_signal.emit(True, "连接成功！API 响应正常。")
                else:
                    self.result_signal.emit(False, "API 返回了空响应。")
        except Exception as e:
            self.result_signal.emit(False, f"连接失败: {str(e)[:200]}")


# ═══════════════════════════════════════════════════════════════
# 提供商标识
# ═══════════════════════════════════════════════════════════════

PROVIDER_PRESETS = [
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "desc": "推荐 · 性价比高，中文能力强",
        "default_url": "https://api.deepseek.com/anthropic",
        "default_model": "deepseek-v4-pro",
        "models": ["deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
    },
    {
        "id": "anthropic",
        "name": "Anthropic",
        "desc": "Claude 系列模型，理解力最强",
        "default_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-6",
        "models": ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5"],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "desc": "GPT 系列模型，生态最成熟",
        "default_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini"],
    },
    {
        "id": "ollama",
        "name": "Ollama",
        "desc": "本地运行，完全离线，免费",
        "default_url": "http://localhost:11434/v1",
        "default_model": "llama3.2",
        "models": ["llama3.2", "qwen3", "mistral", "gemma3"],
    },
]

PERSONALITY_OPTIONS = ["温暖鼓励", "严格专业", "幽默风趣", "知性温柔", "元气活泼"]


# ═══════════════════════════════════════════════════════════════
# 向导页
# ═══════════════════════════════════════════════════════════════

class _WelcomePage(QWidget):
    """第 1 页：欢迎"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        layout.addStretch()

        icon = QLabel("🎙")
        icon.setAlignment(_ALIGN_CENTER)
        icon.setStyleSheet("font-size: 64px;")
        layout.addWidget(icon)

        title = QLabel("欢迎使用 MindEcho\nAI 声乐教练")
        title.setAlignment(_ALIGN_CENTER)
        title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {_PRIMARY_LIGHT};")
        layout.addWidget(title)

        desc = QLabel(
            "我是你的专属 AI 声乐教练，可以帮你分析演唱、指导练习、\n"
            "追踪进步。在开始之前，需要先做两个简单的设置。"
        )
        desc.setAlignment(_ALIGN_CENTER)
        desc.setStyleSheet(f"font-size: 14px; color: {_TEXT_SECONDARY}; line-height: 1.6;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(20)

        tips = QLabel(
            "📡 设置大模型 API  →  🔊 定制教练形象  →  🎵 开始你的声乐之旅"
        )
        tips.setAlignment(_ALIGN_CENTER)
        tips.setStyleSheet(f"font-size: 12px; color: {_TEXT_SECONDARY};")
        layout.addWidget(tips)

        layout.addStretch()


class _APIPage(QWidget):
    """第 2 页：API 配置"""

    def __init__(self, on_test=None, parent=None):
        super().__init__(parent)
        self._on_test = on_test
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(14)

        title = QLabel("步骤 1/3 · 设置大模型 API")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {_PRIMARY_LIGHT};")
        layout.addWidget(title)

        hint = QLabel("MindEcho 需要连接一个大语言模型来驱动 AI 教练。\n推荐使用 DeepSeek，性价比高且中文能力强。")
        hint.setStyleSheet(f"font-size: 12px; color: {_TEXT_SECONDARY};")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addSpacing(6)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(_ALIGN_RIGHT)

        # 提供商
        self.provider_combo = QComboBox()
        for i, p in enumerate(PROVIDER_PRESETS):
            self.provider_combo.addItem(f"{p['name']}  — {p['desc']}", p["id"])
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_label = QLabel("提供商")
        provider_label.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 13px;")
        form.addRow(provider_label, self.provider_combo)

        # API 密钥
        key_row = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(_ECHO_PASSWORD)
        self.key_input.setPlaceholderText("输入你的 API 密钥...")
        self.btn_toggle_key = QPushButton("👁")
        self.btn_toggle_key.setFixedSize(36, 36)
        self.btn_toggle_key.setStyleSheet(f"""
            QPushButton {{
                background: {_BG_CARD};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                font-size: 14px;
            }}
            QPushButton:hover {{ border-color: {_PRIMARY_LIGHT}; }}
        """)
        self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self.key_input)
        key_row.addWidget(self.btn_toggle_key)
        key_widget = QWidget()
        key_widget.setLayout(key_row)
        key_label = QLabel("API 密钥")
        key_label.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 13px;")
        form.addRow(key_label, key_widget)

        # Base URL
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://api.deepseek.com/anthropic")
        url_label = QLabel("接口地址")
        url_label.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 13px;")
        form.addRow(url_label, self.url_input)

        # 模型
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert if _QT6 else QComboBox.NoInsert)
        model_label = QLabel("模型")
        model_label.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 13px;")
        form.addRow(model_label, self.model_combo)

        layout.addLayout(form)

        # 测试连接
        test_layout = QHBoxLayout()
        self.btn_test = QPushButton("🔌 测试连接")
        self.btn_test.setFixedWidth(140)
        self.btn_test.setStyleSheet(f"""
            QPushButton {{
                background-color: {_BG_CARD};
                color: {_TEXT_PRIMARY};
                border: 1px solid {_BORDER};
                border-radius: {_RADIUS};
                padding: 8px 16px;
            }}
            QPushButton:hover {{ border-color: {_PRIMARY_LIGHT}; }}
        """)
        self.btn_test.clicked.connect(self._on_test_clicked)
        self.test_status = QLabel("")
        self.test_status.setStyleSheet(f"font-size: 12px; color: {_TEXT_SECONDARY};")
        test_layout.addWidget(self.btn_test)
        test_layout.addWidget(self.test_status)
        test_layout.addStretch()
        layout.addLayout(test_layout)

        layout.addStretch()

        # 初始化默认值
        self._on_provider_changed(0)

    def _on_provider_changed(self, index: int):
        provider_id = self.provider_combo.currentData()
        for p in PROVIDER_PRESETS:
            if p["id"] == provider_id:
                self.url_input.setPlaceholderText(p["default_url"])
                self.model_combo.clear()
                self.model_combo.addItems(p["models"])
                # Ollama 不需要 API key
                if p["id"] == "ollama":
                    self.key_input.setPlaceholderText("Ollama 无需密钥")
                    self.key_input.setEnabled(False)
                else:
                    self.key_input.setPlaceholderText("输入你的 API 密钥...")
                    self.key_input.setEnabled(True)
                break

    def _toggle_key_visibility(self):
        if self.key_input.echoMode() == _ECHO_PASSWORD:
            self.key_input.setEchoMode(_ECHO_NORMAL)
            self.btn_toggle_key.setText("🙈")
        else:
            self.key_input.setEchoMode(_ECHO_PASSWORD)
            self.btn_toggle_key.setText("👁")

    def _on_test_clicked(self):
        provider = self.provider_combo.currentData()
        api_key = self.key_input.text().strip()
        base_url = self.url_input.text().strip() or self.url_input.placeholderText()
        model = self.model_combo.currentText().strip()

        if provider != "ollama" and not api_key:
            self.test_status.setText("请先输入 API 密钥")
            self.test_status.setStyleSheet(f"font-size: 12px; color: {_DANGER};")
            return

        self.test_status.setText("正在测试连接...")
        self.test_status.setStyleSheet(f"font-size: 12px; color: {_TEXT_SECONDARY};")
        self.btn_test.setEnabled(False)

        self._worker = _TestWorker(provider, api_key, base_url, model)
        self._worker.result_signal.connect(self._on_test_result)
        self._worker.start()

    def _on_test_result(self, success: bool, message: str):
        self.btn_test.setEnabled(True)
        color = _SUCCESS if success else _DANGER
        self.test_status.setText(message)
        self.test_status.setStyleSheet(f"font-size: 12px; color: {color};")

    def get_config(self) -> LLMProviderConfig:
        provider = self.provider_combo.currentData()
        api_key = self.key_input.text().strip()
        base_url = self.url_input.text().strip() or self.url_input.placeholderText()
        model = self.model_combo.currentText().strip()
        if not model:
            for p in PROVIDER_PRESETS:
                if p["id"] == provider:
                    model = p["default_model"]
                    break
        return LLMProviderConfig(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )


class _IdentityPage(QWidget):
    """第 3 页：教练身份"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(14)

        title = QLabel("步骤 2/3 · 定制你的 AI 教练")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {_PRIMARY_LIGHT};")
        layout.addWidget(title)

        hint = QLabel("给你的 AI 教练起个名字，选择一个性格和形象主题。\n之后随时可以在设置中修改。")
        hint.setStyleSheet(f"font-size: 12px; color: {_TEXT_SECONDARY};")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addSpacing(6)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(_ALIGN_RIGHT)

        # 教练名称
        self.name_input = QLineEdit("麦麦")
        name_label = QLabel("教练名称")
        name_label.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 13px;")
        form.addRow(name_label, self.name_input)

        # 性格
        self.personality_combo = QComboBox()
        self.personality_combo.addItems(PERSONALITY_OPTIONS)
        self.personality_combo.setCurrentText("温暖鼓励")
        pers_label = QLabel("性格")
        pers_label.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 13px;")
        form.addRow(pers_label, self.personality_combo)

        # 形象主题
        self.theme_combo = QComboBox()
        for theme_id, theme_name in AVATAR_THEMES.items():
            self.theme_combo.addItem(theme_name, theme_id)
        self.theme_combo.setCurrentIndex(0)
        theme_label = QLabel("形象主题")
        theme_label.setStyleSheet(f"color: {_TEXT_SECONDARY}; font-size: 13px;")
        form.addRow(theme_label, self.theme_combo)

        layout.addLayout(form)

        # 预览区
        preview_label = QLabel("设置完成后，你的 AI 教练会以这个形象出现在屏幕右侧陪你练歌 🎵")
        preview_label.setStyleSheet(f"font-size: 12px; color: {_TEXT_SECONDARY}; padding: 12px;")
        preview_label.setWordWrap(True)
        layout.addWidget(preview_label)

        layout.addStretch()

    def get_identity(self) -> CoachIdentity:
        name = self.name_input.text().strip() or "麦麦"
        theme = self.theme_combo.currentData()
        return CoachIdentity(
            name=name,
            display_name=name,
            personality=self.personality_combo.currentText(),
            avatar_theme=theme,
            accent_color="#7C5CFC",
        )


class _FinishPage(QWidget):
    """第 4 页：完成"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._summary_text = QLabel()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        layout.addStretch()

        check = QLabel("✅")
        check.setAlignment(_ALIGN_CENTER)
        check.setStyleSheet("font-size: 56px;")
        layout.addWidget(check)

        title = QLabel("设置完成！")
        title.setAlignment(_ALIGN_CENTER)
        title.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {_SUCCESS};")
        layout.addWidget(title)

        self._summary_text.setAlignment(_ALIGN_CENTER)
        self._summary_text.setStyleSheet(f"font-size: 13px; color: {_TEXT_SECONDARY}; line-height: 1.8;")
        self._summary_text.setWordWrap(True)
        layout.addWidget(self._summary_text)

        layout.addSpacing(8)

        reminder = QLabel("随时可以在 AI 教练面板的 ⚙ 设置中修改以上配置。")
        reminder.setAlignment(_ALIGN_CENTER)
        reminder.setStyleSheet(f"font-size: 11px; color: {_TEXT_SECONDARY};")
        layout.addWidget(reminder)

        layout.addStretch()

    def set_summary(self, provider_name: str, model: str, coach_name: str, personality: str):
        self._summary_text.setText(
            f"<b>大模型：</b>{provider_name} · {model}<br>"
            f"<b>教练：</b>{coach_name} · {personality}<br><br>"
            f"点击下方「开始使用」进入你的专属声乐教练。"
        )


# ═══════════════════════════════════════════════════════════════
# 主向导对话框
# ═══════════════════════════════════════════════════════════════

class FirstRunWizard(QDialog):
    """首次启动向导 —— 引导用户完成 API + 身份设置"""

    def __init__(self, config_mgr: ConfigManager, parent=None):
        super().__init__(parent)
        self._config_mgr = config_mgr
        self._current_step = 0
        self._total_steps = 3  # welcome 不算 step

        self._app_config = AppConfig()

        self.setWindowTitle("MindEcho · 首次设置")
        self.setMinimumSize(520, 560)
        self.setModal(True)
        self.setStyleSheet(_wizard_style())

        self._init_ui()
        self._update_nav()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 步骤指示器 ──
        self._step_indicators: list[QLabel] = []
        self._step_lines: list[QFrame] = []
        indicator_layout = QHBoxLayout()
        indicator_layout.setContentsMargins(32, 18, 32, 18)

        for i in range(3):
            circle = QLabel(str(i + 1))
            circle.setFixedSize(32, 32)
            circle.setAlignment(_ALIGN_CENTER)
            circle.setStyleSheet(f"""
                QLabel {{
                    background-color: {_BORDER};
                    color: {_TEXT_SECONDARY};
                    border-radius: 16px;
                    font-size: 14px;
                    font-weight: bold;
                }}
            """)
            self._step_indicators.append(circle)
            indicator_layout.addWidget(circle)

            if i < 2:
                line = QFrame()
                line.setFrameShape(_FRAME_HLINE)
                line.setFixedHeight(2)
                line.setStyleSheet(f"background-color: {_BORDER}; border: none;")
                self._step_lines.append(line)
                indicator_layout.addWidget(line, 1)

        indicator_layout.addStretch()
        main_layout.addLayout(indicator_layout)

        # 步骤标签
        self._step_labels = [
            QLabel("API 配置"),
            QLabel("教练身份"),
            QLabel("完成"),
        ]
        label_layout = QHBoxLayout()
        label_layout.setContentsMargins(32, 0, 32, 12)
        for lbl in self._step_labels:
            lbl.setAlignment(_ALIGN_CENTER)
            lbl.setStyleSheet(f"font-size: 11px; color: {_TEXT_SECONDARY};")
            label_layout.addWidget(lbl)
            label_layout.addStretch()
        main_layout.addLayout(label_layout)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(_FRAME_HLINE)
        sep.setStyleSheet(f"background-color: {_BORDER}; border: none; max-height: 1px;")
        main_layout.addWidget(sep)

        # ── 页面栈 ──
        self.stack = QStackedWidget()

        self._welcome_page = _WelcomePage()
        self._api_page = _APIPage()
        self._identity_page = _IdentityPage()
        self._finish_page = _FinishPage()

        self.stack.addWidget(self._welcome_page)   # 0
        self.stack.addWidget(self._api_page)       # 1
        self.stack.addWidget(self._identity_page)  # 2
        self.stack.addWidget(self._finish_page)    # 3

        main_layout.addWidget(self.stack, 1)

        # ── 底部导航栏 ──
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(24, 16, 24, 16)

        self.btn_skip = QPushButton("跳过，以后配置")
        self.btn_skip.setProperty("secondary", True)
        self.btn_skip.clicked.connect(self._on_skip)

        self.btn_back = QPushButton("← 上一步")
        self.btn_back.setProperty("secondary", True)
        self.btn_back.clicked.connect(self._on_back)

        nav_layout.addWidget(self.btn_skip)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_back)

        self.btn_next = QPushButton("下一步 →")
        self.btn_next.clicked.connect(self._on_next)
        nav_layout.addWidget(self.btn_next)

        main_layout.addLayout(nav_layout)

    # ── 导航逻辑 ─────────────────────────────────────────────

    def _update_nav(self):
        """根据当前页面更新导航按钮和步骤指示器"""
        idx = self.stack.currentIndex()

        # 步骤指示器高亮
        for i, circle in enumerate(self._step_indicators):
            if i < idx:
                circle.setStyleSheet(f"""
                    QLabel {{
                        background-color: {_SUCCESS};
                        color: white;
                        border-radius: 16px;
                        font-size: 14px;
                        font-weight: bold;
                    }}
                """)
            elif i == idx - 1 and idx > 0:
                circle.setStyleSheet(f"""
                    QLabel {{
                        background-color: {_PRIMARY};
                        color: white;
                        border-radius: 16px;
                        font-size: 14px;
                        font-weight: bold;
                    }}
                """)
            else:
                circle.setStyleSheet(f"""
                    QLabel {{
                        background-color: {_BORDER};
                        color: {_TEXT_SECONDARY};
                        border-radius: 16px;
                        font-size: 14px;
                        font-weight: bold;
                    }}
                """)

        # 步骤标签高亮
        for i, lbl in enumerate(self._step_labels):
            if i == idx - 1 and idx > 0:
                lbl.setStyleSheet(f"font-size: 11px; color: {_PRIMARY_LIGHT}; font-weight: bold;")
            else:
                lbl.setStyleSheet(f"font-size: 11px; color: {_TEXT_SECONDARY};")

        # 按钮可见性
        if idx == 0:  # Welcome
            self.btn_skip.setVisible(True)
            self.btn_back.setVisible(True)
            self.btn_back.setText("← 上一步")
            self.btn_back.setEnabled(False)
            self.btn_next.setText("开始设置 →")
            self.btn_next.setVisible(True)
        elif idx == 1:  # API
            self.btn_skip.setVisible(True)
            self.btn_back.setVisible(True)
            self.btn_back.setText("← 上一步")
            self.btn_back.setEnabled(True)
            self.btn_next.setText("下一步 →")
            self.btn_next.setVisible(True)
        elif idx == 2:  # Identity
            self.btn_skip.setVisible(True)
            self.btn_back.setVisible(True)
            self.btn_back.setEnabled(True)
            self.btn_next.setText("下一步 →")
            self.btn_next.setVisible(True)
        elif idx == 3:  # Finish
            self.btn_skip.setVisible(False)
            self.btn_back.setVisible(True)
            self.btn_back.setText("← 上一步")
            self.btn_back.setEnabled(True)
            self.btn_next.setText("🎵 开始使用")
            self.btn_next.setVisible(True)

    def _on_back(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._update_nav()

    def _on_next(self):
        idx = self.stack.currentIndex()

        if idx == 3:
            # 完成 → 保存并关闭
            self._save_and_accept()
            return

        if idx == 1:
            # API 页面 → 收集配置
            self._app_config.llm = self._api_page.get_config()

        if idx == 2:
            # Identity 页面 → 收集配置，更新完成页摘要
            self._app_config.identity = self._identity_page.get_identity()

            provider_name = ""
            for p in PROVIDER_PRESETS:
                if p["id"] == self._app_config.llm.provider:
                    provider_name = p["name"]
                    break
            self._finish_page.set_summary(
                provider_name=provider_name,
                model=self._app_config.llm.model,
                coach_name=self._app_config.identity.name,
                personality=self._app_config.identity.personality,
            )

        if idx < 3:
            self.stack.setCurrentIndex(idx + 1)
            self._update_nav()

    def _on_skip(self):
        """跳过设置，使用默认值"""
        reply = QMessageBox.question(
            self, "跳过设置",
            "你可以稍后在 AI 教练面板的 ⚙ 设置中随时配置。\n\n确定要跳过吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._app_config = AppConfig()
            self._save_and_accept()

    def _save_and_accept(self):
        """保存配置并关闭对话框"""
        try:
            self._config_mgr.save(self._app_config)
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"无法保存配置:\n{e}")

    def get_config(self) -> AppConfig:
        """获取用户配置"""
        return self._app_config
