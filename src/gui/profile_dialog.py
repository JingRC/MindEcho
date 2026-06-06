"""存档选择对话框 —— ProfileSelectionDialog / ProfileCreationDialog

在开始录音前弹出，让用户选择或创建歌手存档。
支持：选择已有存档、创建新存档、访客模式、记住本次选择。
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QWidget,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QComboBox,
    QCheckBox,
    QStackedWidget,
    QFrame,
    QMessageBox,
    QSizePolicy,
)

from src.profiles.profile_model import SingerProfile
from src.profiles.profile_manager import ProfileManager
from src.gui.passaggio_calibration_dialog import PassaggioCalibrationDialog
from src.gui.voice_type_assessment_dialog import VoiceTypeAssessmentDialog


# ── 声部选项 ──────────────────────────────────────────────

_VOICE_TYPE_OPTIONS = [
    ("", "不指定（后续可校准）"),
    ("tenor", "男高音"),
    ("baritone", "男中音"),
    ("bass", "男低音"),
    ("soprano", "女高音"),
    ("mezzo_soprano", "女中音"),
    ("contralto", "女低音"),
]

_GENDER_OPTIONS = [
    ("", "不指定"),
    ("male", "男"),
    ("female", "女"),
]


def _voice_type_display(key: str) -> str:
    for k, v in _VOICE_TYPE_OPTIONS:
        if k == key:
            return v
    return key or "不指定"


def _gender_display(key: str) -> str:
    for k, v in _GENDER_OPTIONS:
        if k == key:
            return v
    return key or "不指定"


# ── 存档选择对话框 ──────────────────────────────────────────

class ProfileSelectionDialog(QDialog):
    """存档选择对话框

    用法:
        dlg = ProfileSelectionDialog(profile_manager, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.result_profile
            # result 为 (SingerProfile | None, is_guest: bool)
    """

    profile_created = pyqtSignal(str)  # 新建存档名称

    def __init__(
        self,
        profile_manager: ProfileManager,
        parent: Optional[QWidget] = None,
        session_remembered: bool = False,
    ):
        super().__init__(parent)
        self._mgr = profile_manager
        self._session_remembered = session_remembered
        self.result_profile: Optional[SingerProfile] = None
        self.result_is_guest: bool = False

        self.setWindowTitle("选择歌手存档")
        self.setMinimumSize(480, 420)
        self.setModal(True)

        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── 标题 ──
        title = QLabel("🎤 选择或创建歌手存档")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        desc = QLabel(
            "存档用于记录你的音域、换声点和音色特征，\n"
            "让音高识别和技巧标注更精准。"
        )
        desc.setStyleSheet("color: #888;")
        layout.addWidget(desc)

        # ── 存档列表 ──
        list_label = QLabel("已有存档：")
        list_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(list_label)

        self._list_widget = QListWidget()
        self._list_widget.setMinimumHeight(150)
        self._list_widget.setStyleSheet("""
            QListWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
            }
        """)
        self._list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self._list_widget.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self._list_widget)

        # 无存档时的提示
        self._empty_label = QLabel(
            "还没有存档。创建存档后，系统会学习你的声音特征，\n"
            "让识别越来越精准。"
        )
        self._empty_label.setStyleSheet("color: #999; padding: 20px;")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

        # ── 选中存档的信息 ──
        self._info_frame = QFrame()
        self._info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._info_frame.setStyleSheet("QFrame { background: #f5f5f5; border-radius: 6px; padding: 8px; }")
        info_layout = QVBoxLayout(self._info_frame)
        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)
        info_layout.addWidget(self._info_label)
        self._info_frame.setVisible(False)
        layout.addWidget(self._info_frame)

        # ── 按钮行 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._select_btn = QPushButton("✓ 使用此存档")
        self._select_btn.setEnabled(False)
        self._select_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "padding: 8px 20px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #388E3C; }"
            "QPushButton:disabled { background-color: #ccc; }"
        )
        self._select_btn.clicked.connect(self._accept_selection)
        btn_layout.addWidget(self._select_btn)

        self._new_btn = QPushButton("＋ 新建存档")
        self._new_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #e0e0e0; }"
        )
        self._new_btn.clicked.connect(self._on_create_new)
        btn_layout.addWidget(self._new_btn)

        self._guest_btn = QPushButton("访客模式")
        self._guest_btn.setToolTip("不建立存档，使用默认参数（不保存任何数据）")
        self._guest_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; border-radius: 4px; color: #666; }"
            "QPushButton:hover { background-color: #e0e0e0; }"
        )
        self._guest_btn.clicked.connect(self._on_guest_mode)
        btn_layout.addWidget(self._guest_btn)

        layout.addLayout(btn_layout)

        # ── 记住选择 ──
        self._remember_cb = QCheckBox("本次会话记住选择（关闭窗口前不再询问）")
        self._remember_cb.setChecked(self._session_remembered)
        layout.addWidget(self._remember_cb)

    def _refresh_list(self) -> None:
        self._list_widget.clear()
        profiles = self._mgr.list_profiles()
        self._empty_label.setVisible(len(profiles) == 0)

        for profile in profiles:
            vt = _voice_type_display(profile.effective_voice_type)
            gender = _gender_display(profile.effective_gender)
            minutes = profile.usage.total_minutes
            item_text = f"{profile.name}"
            sub_text = f"声部: {vt}  |  性别: {gender}  |  累计 {minutes:.0f} 分钟"

            item = QListWidgetItem()
            item.setText(item_text)
            item.setData(Qt.ItemDataRole.UserRole, profile.id)
            item.setToolTip(sub_text)

            # 创建自定义 widget 显示两行
            widget = QWidget()
            w_layout = QVBoxLayout(widget)
            w_layout.setContentsMargins(0, 2, 0, 2)
            w_layout.setSpacing(2)

            name_label = QLabel(item_text)
            name_font = QFont()
            name_font.setPointSize(11)
            name_font.setBold(True)
            name_label.setFont(name_font)
            w_layout.addWidget(name_label)

            sub_label = QLabel(sub_text)
            sub_label.setStyleSheet("color: #888; font-size: 10pt;")
            w_layout.addWidget(sub_label)

            widget.setLayout(w_layout)
            item.setSizeHint(widget.sizeHint())
            self._list_widget.addItem(item)
            self._list_widget.setItemWidget(item, widget)

    def _on_selection_changed(self) -> None:
        selected = self._list_widget.currentItem()
        if selected is None:
            self._select_btn.setEnabled(False)
            self._info_frame.setVisible(False)
            return

        self._select_btn.setEnabled(True)
        profile_id = selected.data(Qt.ItemDataRole.UserRole)
        profile = self._mgr.get_profile(profile_id)
        if profile is None:
            self._info_frame.setVisible(False)
            return

        self._info_frame.setVisible(True)
        vt = _voice_type_display(profile.effective_voice_type)
        gender = _gender_display(profile.effective_gender)
        p50 = profile.pitch_stats.p50_hz
        t4 = profile.passaggio.t4_hz
        conf = profile.passaggio.confidence
        minutes = profile.usage.total_minutes

        lines = [
            f"📛 名称：{profile.name}",
            f"🎵 声部：{vt}　　👤 性别：{gender}",
            f"📊 累计练习：{minutes:.0f} 分钟　　🎯 录音 {profile.usage.total_sessions} 次",
        ]
        if p50 > 0:
            lines.append(f"🎶 中位音高：{p50:.0f} Hz")
        if t4 > 0 and conf > 0:
            lines.append(f"🔄 换声点：{t4:.0f} Hz（置信度 {conf:.0%}）")
        self._info_label.setText("\n".join(lines))

    def _accept_selection(self) -> None:
        selected = self._list_widget.currentItem()
        if selected is None:
            return
        profile_id = selected.data(Qt.ItemDataRole.UserRole)
        profile = self._mgr.get_profile(profile_id)
        if profile is None:
            QMessageBox.warning(self, "错误", "存档文件可能已被删除，请刷新。")
            self._refresh_list()
            return
        self.result_profile = profile
        self.result_is_guest = False
        self.accept()

    def _on_create_new(self) -> None:
        dlg = ProfileCreationDialog(self._mgr, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.created_profile is not None:
                self.result_profile = dlg.created_profile
                self.result_is_guest = False
                self.profile_created.emit(self.result_profile.name)
                # 创建后立即打开声部鉴定测评
                if dlg._should_assess:
                    self._open_assessment_for(dlg.created_profile)
                self.accept()
            else:
                self._refresh_list()

    def _open_assessment_for(self, profile: SingerProfile) -> None:
        """在创建存档后打开声部鉴定测评（非模态，不阻塞创建流程）"""
        dlg = VoiceTypeAssessmentDialog(profile, self._mgr, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # 重新加载更新后的存档
            updated = self._mgr.get_profile(profile.id)
            if updated is not None and hasattr(self, '_active_profile'):
                self._active_profile = updated
                if hasattr(self, 'result_profile'):
                    self.result_profile = updated
                self.profile_changed.emit(updated.name)

    def _on_guest_mode(self) -> None:
        self.result_profile = None
        self.result_is_guest = True
        self.accept()

    def remember_choice(self) -> bool:
        return self._remember_cb.isChecked()


# ── 存档创建对话框 ──────────────────────────────────────────

class ProfileCreationDialog(QDialog):
    """新建存档对话框

    步骤:
    1. 输入名称
    2. 选择性别
    3. 选择声部（可跳过）
    """

    def __init__(
        self,
        profile_manager: ProfileManager,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._mgr = profile_manager
        self.created_profile: Optional[SingerProfile] = None
        self._should_assess: bool = False

        self.setWindowTitle("创建歌手存档")
        self.setMinimumSize(440, 420)
        self.setModal(True)
        self.setStyleSheet("""
            ProfileCreationDialog {
                background-color: #0D1117;
            }
        """)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # ── 顶部图标+标题 ──
        header_layout = QHBoxLayout()
        header_icon = QLabel("✨")
        header_icon.setStyleSheet("font-size: 24px; background: transparent;")
        header_layout.addWidget(header_icon)
        title = QLabel("创建歌手存档")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #E6EDF3; background: transparent;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        info = QLabel(
            "存档会记录你的音域、换声点、音色特征，"
            "使用越多识别越精准。后续可随时在校准页面测定换声点。"
        )
        info.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── 分割线 ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("QFrame { background-color: #21262D; max-height: 1px; border: none; }")
        layout.addWidget(line)

        # ── 名称 ──
        name_label = QLabel("存档名称")
        name_label.setStyleSheet("color: #C9D1D9; font-size: 12px; font-weight: bold; background: transparent;")
        layout.addWidget(name_label)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("输入你的名字或昵称，例如：张三")
        self._name_edit.setMinimumHeight(40)
        self._name_edit.setStyleSheet("""
            QLineEdit {
                background: #161B22; border: 1px solid #30363D; border-radius: 8px;
                padding: 8px 14px; color: #E6EDF3; font-size: 13px;
            }
            QLineEdit:focus { border-color: #58A6FF; }
            QLineEdit::placeholder { color: #484F58; }
        """)
        layout.addWidget(self._name_edit)

        # ── 性别 ──
        gender_label = QLabel("性别")
        gender_label.setStyleSheet("color: #C9D1D9; font-size: 12px; font-weight: bold; background: transparent;")
        layout.addWidget(gender_label)

        self._gender_group = QButtonGroup(self)
        gender_opts_layout = QHBoxLayout()
        gender_opts_layout.setSpacing(8)
        for key, label in _GENDER_OPTIONS:
            rb = QRadioButton(label)
            rb.setStyleSheet(f"""
                QRadioButton {{
                    color: #C9D1D9; font-size: 12px;
                    padding: 8px 16px; background: transparent;
                    border: 1px solid #30363D; border-radius: 8px;
                }}
                QRadioButton:hover {{ border-color: #58A6FF; background: #161B22; }}
                QRadioButton::checked {{
                    border-color: #58A6FF;
                    background: rgba(88, 166, 255, 0.12);
                    color: #58A6FF; font-weight: bold;
                }}
                QRadioButton::indicator {{ width: 0px; height: 0px; }}
            """)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            self._gender_group.addButton(rb)
            gender_opts_layout.addWidget(rb)
            if key == "":
                rb.setChecked(True)
        gender_opts_layout.addStretch()
        layout.addLayout(gender_opts_layout)

        # ── 声部 ──
        voice_label = QLabel("声部（可选）")
        voice_label.setStyleSheet("color: #C9D1D9; font-size: 12px; font-weight: bold; background: transparent;")
        layout.addWidget(voice_label)

        self._voice_combo = QComboBox()
        self._voice_combo.setMinimumHeight(40)
        self._voice_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._voice_combo.setStyleSheet("""
            QComboBox {
                background: #161B22; border: 1px solid #30363D; border-radius: 8px;
                padding: 8px 14px; color: #E6EDF3; font-size: 13px;
            }
            QComboBox:hover { border-color: #58A6FF; }
            QComboBox::drop-down { border: none; width: 30px; }
            QComboBox::down-arrow { image: none; }
            QComboBox QAbstractItemView {
                background: #161B22; border: 1px solid #30363D; border-radius: 6px;
                color: #E6EDF3; selection-background-color: #1F2937;
                padding: 4px;
            }
        """)
        for key, label in _VOICE_TYPE_OPTIONS:
            self._voice_combo.addItem(label, key)
        self._voice_combo.setCurrentIndex(0)
        layout.addWidget(self._voice_combo)

        # ── 提示 ──
        hint = QLabel("💡 声部可选「不指定」，后续通过换声点校准功能自动测定。")
        hint.setStyleSheet("color: #484F58; font-size: 10px; background: transparent;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── 创建后测评选项 ──
        self._assess_after_create = QCheckBox("创建后立即进行声部鉴定测评（推荐）")
        self._assess_after_create.setChecked(True)
        self._assess_after_create.setCursor(Qt.CursorShape.PointingHandCursor)
        self._assess_after_create.setStyleSheet("""
            QCheckBox {
                color: #A78BFA; font-size: 11px; background: transparent;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px; height: 16px; border: 1px solid #A78BFA;
                border-radius: 4px; background: transparent;
            }
            QCheckBox::indicator:checked {
                background: #A78BFA; border-color: #A78BFA;
            }
        """)
        layout.addWidget(self._assess_after_create)

        layout.addStretch()

        # ── 按钮行 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumHeight(38)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8B949E;
                padding: 8px 20px; border-radius: 8px;
                font-size: 12px; border: 1px solid #30363D;
            }
            QPushButton:hover { background: #21262D; color: #C9D1D9; }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        btn_layout.addStretch()

        self._create_btn = QPushButton("创建存档")
        self._create_btn.setMinimumHeight(38)
        self._create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #238636, stop:1 #1F6F30);
                color: white; padding: 8px 28px; border-radius: 8px;
                font-weight: bold; font-size: 13px; border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2EA043, stop:1 #238636);
            }
        """)
        self._create_btn.clicked.connect(self._on_create)
        btn_layout.addWidget(self._create_btn)

        layout.addLayout(btn_layout)

    def _get_selected_gender(self) -> str:
        checked = self._gender_group.checkedButton()
        if checked is None:
            return ""
        text = checked.text()
        for key, label in _GENDER_OPTIONS:
            if label == text:
                return key
        return ""

    def _on_create(self) -> None:
        name = self._name_edit.text().strip()
        gender = self._get_selected_gender()
        voice_type = self._voice_combo.currentData() or ""

        # 验证名称
        if not name:
            QMessageBox.warning(self, "提示", "请输入存档名称。")
            self._name_edit.setFocus()
            return

        # 检查非法字符
        illegal = set(r'<>:"/\|?*')
        if any(c in name for c in illegal):
            QMessageBox.warning(
                self, "提示",
                f"存档名称不能包含以下字符：{' '.join(sorted(illegal))}"
            )
            self._name_edit.setFocus()
            return

        # 检查同名
        existing = self._mgr.get_profile_by_name(name)
        if existing is not None:
            QMessageBox.warning(
                self, "同名提示",
                f"存档「{name}」已存在，请换一个名称。"
            )
            self._name_edit.setFocus()
            self._name_edit.selectAll()
            return

        try:
            self.created_profile = self._mgr.create_profile(
                name=name,
                voice_type=voice_type,
                gender=gender,
            )
            self._should_assess = self._assess_after_create.isChecked()
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "创建失败", str(e))


# ── 头像颜色生成 ──────────────────────────────────────────

# 10 种精心挑选的渐变配色，用于头像圆圈
_AVATAR_GRADIENTS = [
    ("#667EEA", "#764BA2"),  # 紫蓝
    ("#F093FB", "#F5576C"),  # 粉红
    ("#4FACFE", "#00F2FE"),  # 青蓝
    ("#43E97B", "#38F9D7"),  # 绿青
    ("#FA709A", "#FEE140"),  # 粉黄
    ("#A18CD1", "#FBC2EB"),  # 淡紫粉
    ("#FAD0C4", "#FFD1FF"),  # 暖粉
    ("#96FBC4", "#F9F586"),  # 薄荷黄
    ("#E0C3FC", "#8EC5FC"),  # 淡紫蓝
    ("#F9D423", "#FF4E50"),  # 金红
]


def _get_avatar_color(name: str) -> tuple:
    """根据名称哈希选取头像渐变色"""
    if not name:
        return _AVATAR_GRADIENTS[0]
    h = sum(ord(c) for c in name)
    return _AVATAR_GRADIENTS[h % len(_AVATAR_GRADIENTS)]


def _get_initials(name: str) -> str:
    """取名称的首字（中文）或首字母（英文）"""
    if not name:
        return "?"
    # 中文名取第一个字
    if '一' <= name[0] <= '鿿':
        return name[0]
    # 英文取首字母大写
    return name[0].upper()


# ── 用户中心对话框 ──────────────────────────────────────────

class UserCenterDialog(QDialog):
    """用户中心 —— 管理歌手存档的主入口

    功能：查看当前存档 / 切换存档 / 新建 / 编辑 / 删除 / 访客模式
    """

    profile_changed = pyqtSignal(str)  # 切换存档后发射新存档名称

    def __init__(
        self,
        profile_manager: "ProfileManager",
        active_profile: Optional[SingerProfile],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._mgr = profile_manager
        self._active_profile = active_profile
        self.result_profile: Optional[SingerProfile] = active_profile
        self.result_is_guest: bool = (active_profile is None)

        self.setWindowTitle("用户中心")
        self.setMinimumSize(620, 560)
        self.setModal(False)
        # 设置窗口背景
        self.setStyleSheet("""
            UserCenterDialog {
                background-color: #0D1117;
            }
        """)

        self._build_ui()
        self._refresh()

    # ── UI 构建 ─────────────────────────────────────────────

    def _build_ui(self) -> None:
        """构建高端卡片式 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 20)
        main_layout.setSpacing(16)

        # ── 顶部标题栏 ──
        header_layout = QHBoxLayout()
        title_icon = QLabel("🎙️")
        title_icon.setStyleSheet("font-size: 22px; background: transparent;")
        header_layout.addWidget(title_icon)

        title = QLabel("用户中心")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #E6EDF3; background: transparent;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # 当前存档计数 badge
        self._profile_count_label = QLabel("")
        self._profile_count_label.setStyleSheet("""
            QLabel {
                color: #8B949E; font-size: 11px;
                background: #21262D; border-radius: 10px;
                padding: 3px 10px;
            }
        """)
        header_layout.addWidget(self._profile_count_label)

        main_layout.addLayout(header_layout)

        # ── 当前存档 Hero 卡片 ──
        self._hero_card = QFrame()
        self._hero_card.setMinimumHeight(80)
        self._hero_card.setStyleSheet("""
            QFrame#heroCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1A1F2E, stop:0.5 #1C2333, stop:1 #1A2030);
                border: 1px solid #30363D;
                border-radius: 12px;
            }
        """)
        self._hero_card.setObjectName("heroCard")
        hero_layout = QHBoxLayout(self._hero_card)
        hero_layout.setContentsMargins(16, 12, 16, 12)
        hero_layout.setSpacing(14)

        # 大头像圆圈
        self._hero_avatar = QLabel("?")
        self._hero_avatar.setFixedSize(56, 56)
        self._hero_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hero_avatar.setStyleSheet("""
            QLabel {
                color: white; font-size: 22px; font-weight: bold;
                border-radius: 28px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #667EEA, stop:1 #764BA2);
            }
        """)
        hero_layout.addWidget(self._hero_avatar)

        # 中间信息区
        hero_info_layout = QVBoxLayout()
        hero_info_layout.setSpacing(4)

        self._hero_name_label = QLabel("访客模式")
        self._hero_name_label.setStyleSheet("""
            QLabel { color: #E6EDF3; font-size: 16px; font-weight: bold; background: transparent; }
        """)
        hero_info_layout.addWidget(self._hero_name_label)

        self._hero_subtitle_label = QLabel("未登录歌手存档")
        self._hero_subtitle_label.setStyleSheet("""
            QLabel { color: #8B949E; font-size: 12px; background: transparent; }
        """)
        hero_info_layout.addWidget(self._hero_subtitle_label)

        # 统计标签行
        self._hero_stats_layout = QHBoxLayout()
        self._hero_stats_layout.setSpacing(6)
        hero_info_layout.addLayout(self._hero_stats_layout)

        hero_layout.addLayout(hero_info_layout)
        hero_layout.addStretch()

        # 右侧状态指示
        self._hero_status_badge = QLabel("● 使用中")
        self._hero_status_badge.setStyleSheet("""
            QLabel {
                color: #3FB950; font-size: 11px; font-weight: bold;
                background: rgba(63, 185, 80, 0.12);
                border: 1px solid rgba(63, 185, 80, 0.3);
                border-radius: 10px;
                padding: 4px 12px;
            }
        """)
        hero_layout.addWidget(self._hero_status_badge)

        main_layout.addWidget(self._hero_card)

        # ── 分割区域标题 ──
        section_layout = QHBoxLayout()
        section_label = QLabel("全部存档")
        section_label.setStyleSheet("""
            QLabel { color: #8B949E; font-size: 11px; font-weight: bold;
                     letter-spacing: 1px; text-transform: uppercase; background: transparent; }
        """)
        section_layout.addWidget(section_label)
        section_layout.addStretch()
        main_layout.addLayout(section_layout)

        # ── 存档卡片列表 ──
        self._list_widget = QListWidget()
        self._list_widget.setMinimumHeight(200)
        self._list_widget.setSpacing(6)
        self._list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list_widget.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background: #161B22;
                border: 1px solid #21262D;
                border-radius: 10px;
                margin-bottom: 6px;
                padding: 0px;
            }
            QListWidget::item:hover {
                border: 1px solid #30363D;
                background: #1C2129;
            }
            QListWidget::item:selected {
                border: 1px solid #58A6FF;
                background: #161B22;
            }
        """)
        self._list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list_widget.verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #30363D; border-radius: 3px; min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #484F58; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        main_layout.addWidget(self._list_widget)

        # ── 空状态 ──
        self._empty_widget = QWidget()
        empty_layout = QVBoxLayout(self._empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = QLabel("🎤")
        empty_icon.setStyleSheet("font-size: 40px; background: transparent;")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_text = QLabel("还没有歌手存档")
        empty_text.setStyleSheet("color: #8B949E; font-size: 14px; background: transparent;")
        empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_text)
        empty_sub = QLabel("点击下方「＋ 新建存档」创建你的第一个歌手身份")
        empty_sub.setStyleSheet("color: #484F58; font-size: 11px; background: transparent;")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_sub)
        main_layout.addWidget(self._empty_widget)

        # ── 操作按钮行 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self._activate_btn = QPushButton("★ 设为当前")
        self._activate_btn.setEnabled(False)
        self._activate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._activate_btn.setMinimumHeight(36)
        self._activate_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #238636, stop:1 #1F6F30);
                color: white; padding: 8px 18px; border-radius: 8px;
                font-weight: bold; font-size: 12px; border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2EA043, stop:1 #238636);
            }
            QPushButton:disabled {
                background: #21262D; color: #484F58; border: 1px solid #30363D;
            }
        """)
        self._activate_btn.clicked.connect(self._on_activate)
        btn_layout.addWidget(self._activate_btn)

        self._new_btn = QPushButton("＋ 新建存档")
        self._new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_btn.setMinimumHeight(36)
        self._new_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #58A6FF;
                padding: 8px 16px; border-radius: 8px;
                font-weight: bold; font-size: 12px;
                border: 1px solid #30363D;
            }
            QPushButton:hover {
                background: rgba(88, 166, 255, 0.1);
                border-color: #58A6FF;
            }
        """)
        self._new_btn.clicked.connect(self._on_create)
        btn_layout.addWidget(self._new_btn)

        self._edit_btn = QPushButton("✎ 编辑")
        self._edit_btn.setEnabled(False)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setMinimumHeight(36)
        self._edit_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #C9D1D9;
                padding: 8px 14px; border-radius: 8px;
                font-size: 12px; border: 1px solid #30363D;
            }
            QPushButton:hover {
                background: #21262D; border-color: #8B949E;
            }
            QPushButton:disabled {
                color: #484F58; border-color: #21262D;
            }
        """)
        self._edit_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(self._edit_btn)

        self._delete_btn = QPushButton("🗑 删除")
        self._delete_btn.setEnabled(False)
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.setMinimumHeight(36)
        self._delete_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #F85149;
                padding: 8px 14px; border-radius: 8px;
                font-size: 12px; border: 1px solid #30363D;
            }
            QPushButton:hover {
                background: rgba(248, 81, 73, 0.1);
                border-color: #F85149;
            }
            QPushButton:disabled {
                color: #484F58; border-color: #21262D;
            }
        """)
        self._delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._delete_btn)

        btn_layout.addStretch()

        self._guest_btn = QPushButton("🚪 切换访客模式")
        self._guest_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._guest_btn.setMinimumHeight(36)
        self._guest_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8B949E;
                padding: 8px 14px; border-radius: 8px;
                font-size: 11px; border: 1px solid #21262D;
            }
            QPushButton:hover {
                background: #21262D; color: #C9D1D9;
            }
        """)
        self._guest_btn.clicked.connect(self._on_guest_mode)
        btn_layout.addWidget(self._guest_btn)

        main_layout.addLayout(btn_layout)

        # ── 列表选中事件 ──
        self._list_widget.itemSelectionChanged.connect(self._on_list_selection)
        self._list_widget.itemDoubleClicked.connect(self._on_view_details)

    # ── 数据刷新 ────────────────────────────────────────────

    def _refresh(self) -> None:
        """刷新卡片列表和 Hero 头部"""
        self._list_widget.clear()
        profiles = self._mgr.list_profiles()
        active_id = self._active_profile.id if self._active_profile else ""

        # 更新计数 badge
        count = len(profiles)
        self._profile_count_label.setText(f"{count} 位用户" if count > 0 else "暂无存档")
        self._profile_count_label.setVisible(True)

        # 显示/隐藏空状态和列表
        self._empty_widget.setVisible(count == 0)
        self._list_widget.setVisible(count > 0)

        # 构建卡片列表
        for p in profiles:
            is_active = (p.id == active_id)
            card_widget = self._build_profile_card(p, is_active)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, p.id)
            item.setSizeHint(card_widget.sizeHint())
            self._list_widget.addItem(item)
            self._list_widget.setItemWidget(item, card_widget)

        self._update_hero()
        self._activate_btn.setEnabled(False)
        self._edit_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)

    def _build_profile_card(self, profile: SingerProfile, is_active: bool) -> QWidget:
        """构建单个存档的卡片 widget"""
        card = QWidget()
        card.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        # 小头像
        c1, c2 = _get_avatar_color(profile.name)
        initials = _get_initials(profile.name)
        avatar = QLabel(initials)
        avatar.setFixedSize(44, 44)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(f"""
            QLabel {{
                color: white; font-size: 18px; font-weight: bold;
                border-radius: 22px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {c1}, stop:1 {c2});
            }}
        """)
        layout.addWidget(avatar)

        # 中间信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        name_row = QHBoxLayout()
        name_label = QLabel(profile.name)
        name_label.setStyleSheet("color: #E6EDF3; font-size: 13px; font-weight: bold; background: transparent;")
        name_row.addWidget(name_label)

        # 活跃标记
        if is_active:
            active_badge = QLabel("使用中")
            active_badge.setStyleSheet("""
                QLabel {
                    color: #3FB950; font-size: 9px; font-weight: bold;
                    background: rgba(63, 185, 80, 0.15);
                    border-radius: 6px; padding: 1px 8px;
                }
            """)
            name_row.addWidget(active_badge)

        name_row.addStretch()
        info_layout.addLayout(name_row)

        # 详情行
        vt = _voice_type_display(profile.effective_voice_type)
        gender = _gender_display(profile.effective_gender)
        mins = profile.usage.total_minutes
        sessions = profile.usage.total_sessions

        detail_parts = []
        if vt != "不指定":
            detail_parts.append(f"🎵 {vt}")
        if gender != "不指定":
            detail_parts.append(f"👤 {gender}")
        if mins > 0:
            detail_parts.append(f"⏱ {mins:.0f}分钟")
        if sessions > 0:
            detail_parts.append(f"🎯 {sessions}次")

        detail_text = "  ·  ".join(detail_parts) if detail_parts else "新存档，开始你的第一次练习吧"
        detail_label = QLabel(detail_text)
        detail_label.setStyleSheet("color: #8B949E; font-size: 11px; background: transparent;")
        info_layout.addWidget(detail_label)

        layout.addLayout(info_layout)
        layout.addStretch()

        # 详情按钮（Phase 2：单击进入详情页）
        detail_btn = QPushButton("详情 ›")
        detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        detail_btn.setMinimumHeight(30)
        detail_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #58A6FF;
                padding: 4px 12px; border-radius: 6px;
                font-size: 11px; border: 1px solid #30363D;
            }
            QPushButton:hover {
                background: rgba(88, 166, 255, 0.1);
                border-color: #58A6FF;
            }
        """)
        # 用闭包捕获当前 profile
        pid = profile.id
        detail_btn.clicked.connect(lambda checked=False, p=pid: self._on_view_details_for(p))
        layout.addWidget(detail_btn)

        return card

    def _update_hero(self) -> None:
        """更新 Hero 头部卡片"""
        if self._active_profile is None:
            self._hero_avatar.setText("?")
            self._hero_avatar.setStyleSheet("""
                QLabel {
                    color: white; font-size: 22px; font-weight: bold;
                    border-radius: 28px;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #484F58, stop:1 #30363D);
                }
            """)
            self._hero_name_label.setText("访客模式")
            self._hero_subtitle_label.setText("未登录歌手存档 · 使用默认识别参数")
            self._hero_status_badge.setText("● 访客")
            self._hero_status_badge.setStyleSheet("""
                QLabel {
                    color: #8B949E; font-size: 11px; font-weight: bold;
                    background: rgba(139, 148, 158, 0.12);
                    border: 1px solid rgba(139, 148, 158, 0.3);
                    border-radius: 10px;
                    padding: 4px 12px;
                }
            """)
            # 清除统计标签
            self._clear_hero_stats()
            return

        p = self._active_profile
        c1, c2 = _get_avatar_color(p.name)
        initials = _get_initials(p.name)
        self._hero_avatar.setText(initials)
        self._hero_avatar.setStyleSheet(f"""
            QLabel {{
                color: white; font-size: 22px; font-weight: bold;
                border-radius: 28px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {c1}, stop:1 {c2});
            }}
        """)

        vt = _voice_type_display(p.effective_voice_type)
        gender = _gender_display(p.effective_gender)
        self._hero_name_label.setText(p.name)
        self._hero_subtitle_label.setText(f"{vt}  ·  {gender}" if vt != "不指定" else "声部与性别未指定")

        self._hero_status_badge.setText("● 使用中")
        self._hero_status_badge.setStyleSheet("""
            QLabel {
                color: #3FB950; font-size: 11px; font-weight: bold;
                background: rgba(63, 185, 80, 0.12);
                border: 1px solid rgba(63, 185, 80, 0.3);
                border-radius: 10px;
                padding: 4px 12px;
            }
        """)

        # 重建统计标签
        self._clear_hero_stats()
        stats_data = []
        mins = p.usage.total_minutes
        sessions = p.usage.total_sessions
        if mins > 0:
            stats_data.append(("⏱", f"{mins:.0f}分钟"))
        if sessions > 0:
            stats_data.append(("🎯", f"{sessions}次录音"))
        if p.passaggio.t4_hz > 0 and p.passaggio.confidence > 0:
            stats_data.append(("🔄", f"换声点 {p.passaggio.t4_hz:.0f}Hz"))
        if p.pitch_stats.p50_hz > 0:
            stats_data.append(("🎶", f"中位 {p.pitch_stats.p50_hz:.0f}Hz"))

        for icon, text in stats_data:
            chip = QLabel(f"{icon} {text}")
            chip.setStyleSheet("""
                QLabel {
                    color: #C9D1D9; font-size: 10px;
                    background: rgba(255,255,255,0.06);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 8px;
                    padding: 2px 10px;
                }
            """)
            self._hero_stats_layout.addWidget(chip)
        self._hero_stats_layout.addStretch()

    def _clear_hero_stats(self) -> None:
        """清除 Hero 中的统计标签"""
        while self._hero_stats_layout.count():
            item = self._hero_stats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ── 事件处理（业务逻辑不变） ──────────────────────────────

    def _on_list_selection(self) -> None:
        selected = self._list_widget.currentItem()
        has_selection = selected is not None
        self._activate_btn.setEnabled(has_selection)
        self._edit_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)

    def _on_view_details(self) -> None:
        """双击卡片 → 打开存档详情面板"""
        selected = self._list_widget.currentItem()
        if selected is None:
            return
        profile_id = selected.data(Qt.ItemDataRole.UserRole)
        self._on_view_details_for(profile_id)

    def _on_view_details_for(self, profile_id: str) -> None:
        """指定 profile_id 打开详情面板（按钮点击使用）"""
        profile = self._mgr.get_profile(profile_id)
        if profile is None:
            return
        dlg = ProfileDetailDialog(profile, self._mgr, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # 详情面板内的评估/编辑可能已更新存档，重新加载
            updated = self._mgr.get_profile(profile_id)
            if updated is not None:
                if self._active_profile and self._active_profile.id == profile_id:
                    self._active_profile = updated
                    self.result_profile = updated
                    self.profile_changed.emit(updated.name)
                self._refresh()
        # 通知主窗口同步 AI 教练（无论是否进行了编辑，查看详情时就同步）
        try:
            self._sync_ai_coach_for_profile(profile)
        except Exception:
            pass

    def _sync_ai_coach_for_profile(self, profile) -> None:
        """将指定存档同步到主窗口的 AI 教练面板"""
        # 遍历父窗口链找到主窗口
        ancestor = self.parent()
        while ancestor is not None:
            if hasattr(ancestor, '_notify_ai_coach_profile_changed'):
                old_profile = getattr(ancestor, '_active_profile', None)
                try:
                    ancestor._active_profile = profile
                    ancestor._notify_ai_coach_profile_changed()
                finally:
                    ancestor._active_profile = old_profile
                return
            ancestor = ancestor.parent()

    def _on_activate(self) -> None:
        selected = self._list_widget.currentItem()
        if selected is None:
            return
        profile_id = selected.data(Qt.ItemDataRole.UserRole)
        profile = self._mgr.get_profile(profile_id)
        if profile is None:
            QMessageBox.warning(self, "错误", "存档文件可能已被删除。")
            self._refresh()
            return
        self._active_profile = profile
        self.result_profile = profile
        self.result_is_guest = False
        self._mgr.set_active_profile(profile)
        self.profile_changed.emit(profile.name)
        self._refresh()

    def _on_create(self) -> None:
        dlg = ProfileCreationDialog(self._mgr, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.created_profile is not None:
            self._active_profile = dlg.created_profile
            self.result_profile = dlg.created_profile
            self.result_is_guest = False
            self._mgr.set_active_profile(dlg.created_profile)
            self.profile_changed.emit(dlg.created_profile.name)
            # 创建后立即打开声部鉴定测评
            if dlg._should_assess:
                assess_dlg = VoiceTypeAssessmentDialog(dlg.created_profile, self._mgr, self)
                if assess_dlg.exec() == QDialog.DialogCode.Accepted:
                    # 重新加载以获取评估更新的数据
                    updated = self._mgr.get_profile(dlg.created_profile.id)
                    if updated is not None:
                        self._active_profile = updated
                        self.result_profile = updated
                        # 评估完成后再次触发通知，将声部/换声点/音域同步给AI教练
                        self.profile_changed.emit(updated.name)
            self._refresh()

    def _on_edit(self) -> None:
        selected = self._list_widget.currentItem()
        if selected is None:
            return
        profile_id = selected.data(Qt.ItemDataRole.UserRole)
        profile = self._mgr.get_profile(profile_id)
        if profile is None:
            return
        dlg = ProfileEditDialog(profile, self._mgr, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if self._active_profile and self._active_profile.id == profile.id:
                self._active_profile = self._mgr.get_profile(profile.id)
                self.result_profile = self._active_profile
                self.profile_changed.emit(self._active_profile.name)
            self._refresh()

    def _on_delete(self) -> None:
        selected = self._list_widget.currentItem()
        if selected is None:
            return
        profile_id = selected.data(Qt.ItemDataRole.UserRole)
        profile = self._mgr.get_profile(profile_id)
        if profile is None:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除存档「{profile.name}」吗？\n\n"
            f"该存档的所有录音文件将被删除，此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._mgr.delete_profile(profile_id)
        if self._active_profile and self._active_profile.id == profile_id:
            self._active_profile = None
            self.result_profile = None
            self.result_is_guest = True
            self._mgr.clear_active_profile()
            self.profile_changed.emit("")
        self._refresh()

    def _on_guest_mode(self) -> None:
        self._active_profile = None
        self.result_profile = None
        self.result_is_guest = True
        self._mgr.clear_active_profile()
        self.profile_changed.emit("")
        self._refresh()


# ── 存档编辑对话框 ─────────────────────────────────────────

class ProfileEditDialog(QDialog):
    """编辑存档名称、声部、性别"""

    def __init__(
        self,
        profile: SingerProfile,
        profile_manager: "ProfileManager",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._profile = profile
        self._mgr = profile_manager

        self.setWindowTitle(f"编辑存档 — {profile.name}")
        self.setMinimumSize(420, 340)
        self.setModal(True)
        self.setStyleSheet("""
            ProfileEditDialog {
                background-color: #0D1117;
            }
        """)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # ── 顶部标题 ──
        header_layout = QHBoxLayout()
        header_icon = QLabel("✏️")
        header_icon.setStyleSheet("font-size: 22px; background: transparent;")
        header_layout.addWidget(header_icon)
        title = QLabel(f"编辑「{self._profile.name}」")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #E6EDF3; background: transparent;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("QFrame { background-color: #21262D; max-height: 1px; border: none; }")
        layout.addWidget(line)

        # 名称
        name_label = QLabel("存档名称")
        name_label.setStyleSheet("color: #C9D1D9; font-size: 12px; font-weight: bold; background: transparent;")
        layout.addWidget(name_label)

        self._name_edit = QLineEdit(self._profile.name)
        self._name_edit.setMinimumHeight(40)
        self._name_edit.setStyleSheet("""
            QLineEdit {
                background: #161B22; border: 1px solid #30363D; border-radius: 8px;
                padding: 8px 14px; color: #E6EDF3; font-size: 13px;
            }
            QLineEdit:focus { border-color: #58A6FF; }
        """)
        layout.addWidget(self._name_edit)

        # 性别
        gender_label = QLabel("性别")
        gender_label.setStyleSheet("color: #C9D1D9; font-size: 12px; font-weight: bold; background: transparent;")
        layout.addWidget(gender_label)

        self._gender_group = QButtonGroup(self)
        g_layout = QHBoxLayout()
        g_layout.setSpacing(8)
        for key, label in _GENDER_OPTIONS:
            rb = QRadioButton(label)
            rb.setStyleSheet(f"""
                QRadioButton {{
                    color: #C9D1D9; font-size: 12px;
                    padding: 8px 16px; background: transparent;
                    border: 1px solid #30363D; border-radius: 8px;
                }}
                QRadioButton:hover {{ border-color: #58A6FF; background: #161B22; }}
                QRadioButton::checked {{
                    border-color: #58A6FF;
                    background: rgba(88, 166, 255, 0.12);
                    color: #58A6FF; font-weight: bold;
                }}
                QRadioButton::indicator {{ width: 0px; height: 0px; }}
            """)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            self._gender_group.addButton(rb)
            g_layout.addWidget(rb)
            if key == self._profile.gender_manual:
                rb.setChecked(True)
        if self._gender_group.checkedButton() is None:
            for btn in self._gender_group.buttons():
                if btn.text() == "不指定":
                    btn.setChecked(True)
                    break
        g_layout.addStretch()
        layout.addLayout(g_layout)

        # 声部
        voice_label = QLabel("声部（可选）")
        voice_label.setStyleSheet("color: #C9D1D9; font-size: 12px; font-weight: bold; background: transparent;")
        layout.addWidget(voice_label)

        self._voice_combo = QComboBox()
        self._voice_combo.setMinimumHeight(40)
        self._voice_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._voice_combo.setStyleSheet("""
            QComboBox {
                background: #161B22; border: 1px solid #30363D; border-radius: 8px;
                padding: 8px 14px; color: #E6EDF3; font-size: 13px;
            }
            QComboBox:hover { border-color: #58A6FF; }
            QComboBox::drop-down { border: none; width: 30px; }
            QComboBox QAbstractItemView {
                background: #161B22; border: 1px solid #30363D; border-radius: 6px;
                color: #E6EDF3; selection-background-color: #1F2937;
                padding: 4px;
            }
        """)
        for key, label in _VOICE_TYPE_OPTIONS:
            self._voice_combo.addItem(label, key)
        for i in range(self._voice_combo.count()):
            if self._voice_combo.itemData(i) == self._profile.voice_type_manual:
                self._voice_combo.setCurrentIndex(i)
                break
        layout.addWidget(self._voice_combo)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumHeight(38)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8B949E;
                padding: 8px 20px; border-radius: 8px;
                font-size: 12px; border: 1px solid #30363D;
            }
            QPushButton:hover { background: #21262D; color: #C9D1D9; }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        save_btn = QPushButton("保存修改")
        save_btn.setMinimumHeight(38)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #238636, stop:1 #1F6F30);
                color: white; padding: 8px 24px; border-radius: 8px;
                font-weight: bold; font-size: 13px; border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2EA043, stop:1 #238636);
            }
        """)
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def _get_selected_gender(self) -> str:
        checked = self._gender_group.checkedButton()
        if checked is None:
            return ""
        text = checked.text()
        for key, label in _GENDER_OPTIONS:
            if label == text:
                return key
        return ""

    def _on_save(self) -> None:
        new_name = self._name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "提示", "名称不能为空。")
            return
        illegal = set(r'<>:"/\|?*')
        if any(c in new_name for c in illegal):
            QMessageBox.warning(self, "提示", f"名称不能包含：{' '.join(sorted(illegal))}")
            return

        # 如果改名了，检查同名
        if new_name != self._profile.name:
            existing = self._mgr.get_profile_by_name(new_name)
            if existing is not None and existing.id != self._profile.id:
                QMessageBox.warning(self, "同名提示", f"存档「{new_name}」已存在。")
                return

        new_gender = self._get_selected_gender()
        new_voice = self._voice_combo.currentData() or ""

        # 更新并保存
        old_name = self._profile.name
        self._profile.name = new_name
        self._profile.gender_manual = new_gender
        self._profile.voice_type_manual = new_voice

        # 如果改名了，需要迁移文件夹
        if new_name != old_name:
            old_folder = self._mgr._root / old_name
            new_folder = self._mgr._root / new_name
            if old_folder.exists() and not new_folder.exists():
                import shutil
                shutil.move(str(old_folder), str(new_folder))

        self._mgr.save_profile(self._profile)
        self.accept()


# ── 存档详情对话框（Phase 2）─────────────────────────────────

# 简易 Hz→音名 转换（避免循环引用，不依赖 pitch_detection 模块）
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _hz_to_note_name(hz: float) -> str:
    """将频率转换为音名+八度，如 440.0 → 'A4'"""
    if hz <= 0:
        return "—"
    # MIDI note = 69 + 12 * log2(f / 440)
    import math
    midi = 69 + 12 * math.log2(hz / 440.0)
    note_idx = int(round(midi)) % 12
    octave = int(round(midi)) // 12 - 1
    return f"{_NOTE_NAMES[note_idx]}{octave}"


class ProfileDetailDialog(QDialog):
    """存档详情面板 —— 展示歌手的完整数据画像

    Phase 2 核心：练习统计 / 音域分析 / 换声点 / 音色指纹 / AI Coach 联动
    """

    def __init__(
        self,
        profile: SingerProfile,
        profile_manager: "ProfileManager",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._profile = profile
        self._mgr = profile_manager

        self.setWindowTitle(f"存档详情 — {profile.name}")
        self.setMinimumSize(560, 640)
        self.setModal(False)
        self.setStyleSheet("""
            ProfileDetailDialog {
                background-color: #0D1117;
            }
        """)

        self._build_ui()

    # ── UI 构建 ─────────────────────────────────────────────

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 20)
        main_layout.setSpacing(16)

        # ── 滚动区域 ──
        from PyQt6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; }
            QScrollBar::handle:vertical { background: #30363D; border-radius: 3px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #484F58; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        # ── Hero 头部 ──
        content_layout.addWidget(self._build_hero())

        # ── 分割线 ──
        content_layout.addWidget(self._divider())

        # ── 练习统计 ──
        content_layout.addWidget(self._build_practice_stats())

        # ── 音域分析 ──
        content_layout.addWidget(self._build_pitch_range())

        # ── 换声点 ──
        content_layout.addWidget(self._build_passaggio())

        # ── 音色指纹 ──
        content_layout.addWidget(self._build_timbre())

        # ── 分析报告 ──
        content_layout.addWidget(self._build_reports())

        # ── AI Coach 联动 ──
        content_layout.addWidget(self._build_ai_coach())

        content_layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        # ── 底部按钮 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_layout.addStretch()

        edit_btn = QPushButton("✎ 编辑")
        edit_btn.setMinimumHeight(36)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #58A6FF;
                padding: 8px 20px; border-radius: 8px;
                font-size: 12px; border: 1px solid #30363D;
            }
            QPushButton:hover { background: rgba(88, 166, 255, 0.1); border-color: #58A6FF; }
        """)
        edit_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(edit_btn)

        close_btn = QPushButton("关闭")
        close_btn.setMinimumHeight(36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #21262D; color: #C9D1D9;
                padding: 8px 20px; border-radius: 8px;
                font-size: 12px; border: 1px solid #30363D;
            }
            QPushButton:hover { background: #30363D; }
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        main_layout.addLayout(btn_layout)

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("QFrame { background-color: #21262D; max-height: 1px; border: none; }")
        return line

    # ── Hero 头部 ───────────────────────────────────────────

    def _build_hero(self) -> QWidget:
        hero = QFrame()
        hero.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1A1F2E, stop:0.5 #1C2333, stop:1 #1A2030);
                border: 1px solid #30363D; border-radius: 12px;
            }
        """)
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # 大头像
        c1, c2 = _get_avatar_color(self._profile.name)
        initials = _get_initials(self._profile.name)
        avatar = QLabel(initials)
        avatar.setFixedSize(64, 64)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(f"""
            QLabel {{
                color: white; font-size: 26px; font-weight: bold;
                border-radius: 32px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {c1}, stop:1 {c2});
            }}
        """)
        layout.addWidget(avatar)

        # 信息
        info = QVBoxLayout()
        info.setSpacing(2)

        name_label = QLabel(self._profile.name)
        name_label.setStyleSheet("color: #E6EDF3; font-size: 18px; font-weight: bold; background: transparent;")
        info.addWidget(name_label)

        vt = _voice_type_display(self._profile.effective_voice_type)
        gender = _gender_display(self._profile.effective_gender)
        subtitle = f"{vt}  ·  {gender}" if vt != "不指定" else "声部与性别未指定"
        sub_label = QLabel(subtitle)
        sub_label.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
        info.addWidget(sub_label)

        layout.addLayout(info)
        layout.addStretch()

        # 右侧编辑按钮
        edit_btn = QPushButton("✎ 编辑")
        edit_btn.setMinimumHeight(32)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #58A6FF;
                padding: 6px 14px; border-radius: 6px;
                font-size: 11px; border: 1px solid #30363D;
            }
            QPushButton:hover { background: rgba(88, 166, 255, 0.1); border-color: #58A6FF; }
        """)
        edit_btn.clicked.connect(self._on_edit)
        layout.addWidget(edit_btn)

        return hero

    # ── 练习统计 ────────────────────────────────────────────

    def _build_practice_stats(self) -> QWidget:
        return self._build_section(
            "📊 练习统计",
            self._build_stats_cards()
        )

    def _build_stats_cards(self) -> QWidget:
        p = self._profile
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 计算活跃天数
        from datetime import datetime
        active_days = 0
        if p.created_at:
            try:
                created = datetime.strptime(p.created_at[:10], "%Y-%m-%d")
                active_days = max(1, (datetime.now() - created).days)
            except Exception:
                pass

        cards = [
            ("⏱", f"{p.usage.total_minutes:.0f} 分钟", "累计练习"),
            ("🎯", f"{p.usage.total_sessions} 次", "录音次数"),
            ("📅", f"{active_days} 天", "活跃天数"),
        ]

        for icon, value, label in cards:
            card = self._stat_card(icon, value, label)
            layout.addWidget(card)

        return widget

    def _stat_card(self, icon: str, value: str, label: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #161B22; border: 1px solid #21262D;
                border-radius: 10px; padding: 12px;
            }
        """)
        clayout = QVBoxLayout(card)
        clayout.setContentsMargins(14, 12, 14, 12)
        clayout.setSpacing(4)
        clayout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 20px; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clayout.addWidget(icon_lbl)

        val_lbl = QLabel(value)
        val_lbl.setStyleSheet("color: #E6EDF3; font-size: 16px; font-weight: bold; background: transparent;")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clayout.addWidget(val_lbl)

        lbl = QLabel(label)
        lbl.setStyleSheet("color: #8B949E; font-size: 10px; background: transparent;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clayout.addWidget(lbl)

        return card

    # ── 音域分析 ────────────────────────────────────────────

    def _build_pitch_range(self) -> QWidget:
        stats = self._profile.pitch_stats

        if stats.total_voiced_frames <= 0:
            empty = QLabel("还没有足够的练习数据。开始录音后，系统会自动分析你的音域。")
            empty.setStyleSheet("color: #484F58; font-size: 12px; background: transparent; padding: 8px 0;")
            empty.setWordWrap(True)
            return self._build_section("🎵 音域分析", empty)

        p50_hz = stats.p50_hz
        p5_hz = stats.p5_hz
        p95_hz = stats.p95_hz

        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 关键数值行
        nums_layout = QHBoxLayout()
        nums_layout.setSpacing(16)
        nums = [
            ("最低", f"{stats.min_hz:.0f} Hz", _hz_to_note_name(stats.min_hz)),
            ("P5", f"{stats.p5_hz:.0f} Hz", _hz_to_note_name(stats.p5_hz)),
            ("中位 P50", f"{stats.p50_hz:.0f} Hz", _hz_to_note_name(stats.p50_hz)),
            ("P95", f"{stats.p95_hz:.0f} Hz", _hz_to_note_name(stats.p95_hz)),
            ("最高", f"{stats.max_hz:.0f} Hz", _hz_to_note_name(stats.max_hz)),
        ]
        for title, freq, note in nums:
            chip = QLabel(f"{title}\n{freq}\n{note}")
            chip.setStyleSheet("""
                QLabel {
                    color: #C9D1D9; font-size: 10px; background: #161B22;
                    border: 1px solid #21262D; border-radius: 8px;
                    padding: 6px 10px;
                }
            """)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            nums_layout.addWidget(chip)
        nums_layout.addStretch()
        layout.addLayout(nums_layout)

        # 音域可视化条
        range_bar = self._build_range_bar(stats)
        layout.addWidget(range_bar)

        # 总帧数提示
        frames_label = QLabel(f"基于 {stats.total_voiced_frames} 帧发声数据 · {stats.session_count} 次录音")
        frames_label.setStyleSheet("color: #484F58; font-size: 10px; background: transparent;")
        layout.addWidget(frames_label)

        return self._build_section("🎵 音域分析", widget)

    def _build_range_bar(self, stats) -> QWidget:
        """绘制音域范围可视化条"""
        bar_widget = QWidget()
        bar_widget.setStyleSheet("background: transparent;")
        bar_widget.setFixedHeight(32)

        # 用 QFrame 模拟范围条
        bar = QFrame()
        bar.setStyleSheet("""
            QFrame {
                background: #161B22; border: 1px solid #21262D; border-radius: 8px;
            }
        """)

        # 计算相对位置（基于常见人声音域 80~1200Hz）
        min_log = 80.0
        max_log = 1200.0

        def _pos(hz):
            if hz <= 0:
                return 0.0
            import math
            return max(0, min(1, (math.log(hz) - math.log(min_log)) / (math.log(max_log) - math.log(min_log))))

        p5_pos = _pos(stats.p5_hz)
        p95_pos = _pos(stats.p95_hz)
        p50_pos = _pos(stats.p50_hz)

        # 用水平布局里面的彩色 span 来画
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(4, 4, 4, 4)
        bar_layout.setSpacing(0)

        # 左侧空白
        if p5_pos > 0:
            left_spacer = QWidget()
            left_spacer.setFixedWidth(int(max(4, p5_pos * 500)))
            left_spacer.setStyleSheet("background: transparent;")
            bar_layout.addWidget(left_spacer)

        # 音域范围条 (P5→P95)
        range_width = max(4, int((p95_pos - p5_pos) * 500))
        range_span = QLabel()
        range_span.setFixedWidth(range_width)
        range_span.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #58A6FF, stop:1 #A78BFA);
                border-radius: 5px;
            }
        """)
        bar_layout.addWidget(range_span)

        # 中位标记点
        mid_marker = QLabel("▼")
        mid_marker.setStyleSheet("color: #E6EDF3; font-size: 10px; background: transparent;")
        mid_marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_layout.addWidget(mid_marker)

        # 右侧空白
        bar_layout.addStretch()

        bar_widget_layout = QVBoxLayout(bar_widget)
        bar_widget_layout.setContentsMargins(0, 0, 0, 0)
        bar_widget_layout.addWidget(bar)

        # 标签行
        lbl_row = QHBoxLayout()
        p5_note = _hz_to_note_name(stats.p5_hz)
        p95_note = _hz_to_note_name(stats.p95_hz)
        left_lbl = QLabel(f"P5: {p5_note}")
        left_lbl.setStyleSheet("color: #8B949E; font-size: 9px; background: transparent;")
        right_lbl = QLabel(f"P95: {p95_note}")
        right_lbl.setStyleSheet("color: #8B949E; font-size: 9px; background: transparent;")
        lbl_row.addWidget(left_lbl)
        lbl_row.addStretch()
        lbl_row.addWidget(right_lbl)
        bar_widget_layout.addLayout(lbl_row)

        return bar_widget

    # ── 换声点 ──────────────────────────────────────────────

    def _build_passaggio(self) -> QWidget:
        p = self._profile
        pp = p.passaggio

        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if pp.t4_hz <= 0:
            hint = QLabel("尚未测定换声点。累计足够练习数据后，系统会自动估计；你也可以进行手动校准。")
            hint.setStyleSheet("color: #484F58; font-size: 12px; background: transparent;")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        else:
            # T4 频率 + 音名
            t4_row = QHBoxLayout()
            t4_val = QLabel(f"T4 ≈ {pp.t4_hz:.0f} Hz ({_hz_to_note_name(pp.t4_hz)})")
            t4_val.setStyleSheet("color: #E6EDF3; font-size: 15px; font-weight: bold; background: transparent;")
            t4_row.addWidget(t4_val)
            t4_row.addStretch()
            layout.addLayout(t4_row)

            # 来源 + 置信度
            source_text = {"calibrated": "手动校准（多特征融合）", "auto_estimated": "自动估计（音域统计）", "default": "默认值"}.get(pp.source, pp.source)
            meta_label = QLabel(f"来源: {source_text}　｜　置信度: {pp.confidence:.0%}")
            meta_label.setStyleSheet("color: #8B949E; font-size: 11px; background: transparent;")
            layout.addWidget(meta_label)

            # 置信度进度条
            conf_bar = QFrame()
            conf_bar.setFixedHeight(6)
            conf_bar.setStyleSheet(f"""
                QFrame {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #58A6FF, stop:{pp.confidence:.2f} #58A6FF,
                        stop:{pp.confidence:.2f} #21262D, stop:1 #21262D);
                    border-radius: 3px;
                }}
            """)
            layout.addWidget(conf_bar)

            # 对比自动估计值（来自音域统计，与校准检测是不同的算法）
            if pp.auto_estimated_t4 > 0 and pp.source != "auto_estimated":
                auto_note = _hz_to_note_name(pp.auto_estimated_t4)
                delta_semitones = abs(12 * math.log2(pp.t4_hz / pp.auto_estimated_t4)) if pp.auto_estimated_t4 > 0 and pp.t4_hz > 0 else 0
                cmp_label = QLabel(
                    f"📊 音域统计估计: {pp.auto_estimated_t4:.0f} Hz ({auto_note})　"
                    f"｜　偏差 {delta_semitones:.1f} 半音\n"
                    f"   ↑ 基于音域 P85 百分位的粗略估计，不如校准检测精确。仅供参考。"
                )
                cmp_label.setStyleSheet("color: #484F58; font-size: 10px; background: transparent;")
                layout.addWidget(cmp_label)

        # ── 手动校准 / 重测按钮 ──
        if pp.t4_hz > 0 and pp.confidence < 0.6:
            # 已有数据但置信度低 → 显示重测提示
            retest_hint = QLabel("⚠️ 当前换声点置信度较低，建议重新校准以获得更准确的结果。")
            retest_hint.setStyleSheet("color: #D29922; font-size: 11px; background: transparent; padding: 4px 0;")
            retest_hint.setWordWrap(True)
            layout.addWidget(retest_hint)

        cal_btn = QPushButton(
            "🔄 重新校准换声点" if pp.t4_hz > 0 else "🎤 手动校准换声点"
        )
        cal_btn.setMinimumHeight(34)
        cal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cal_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #58A6FF, stop:1 #A78BFA);
                color: #FFFFFF; font-weight: bold;
                padding: 8px 16px; border-radius: 8px;
                font-size: 12px; border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #79B8FF, stop:1 #B794F4);
            }
        """)
        cal_btn.clicked.connect(self._on_calibrate_passaggio)
        layout.addWidget(cal_btn)

        # ── 声部鉴定测评按钮 ──
        assess_btn = QPushButton("🔍 声部鉴定测评（音域 + 换声点 + 音色）")
        assess_btn.setMinimumHeight(34)
        assess_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        assess_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #A78BFA; font-size: 11px;
                padding: 8px 16px; border-radius: 8px;
                border: 1px dashed #A78BFA;
            }
            QPushButton:hover {
                background: rgba(167, 139, 250, 0.1);
                border-color: #B794F4;
                color: #B794F4;
            }
        """)
        assess_btn.clicked.connect(self._on_voice_type_assessment)
        layout.addWidget(assess_btn)

        return self._build_section("🔄 换声点", widget)

    # ── 音色指纹 ────────────────────────────────────────────

    def _build_timbre(self) -> QWidget:
        t = self._profile.timbre

        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if t.sample_count <= 0:
            hint = QLabel("还没有音色数据。开始录音后，系统会自动收集音色特征。")
            hint.setStyleSheet("color: #484F58; font-size: 12px; background: transparent;")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        else:
            # 两行三列的网格
            grid = QHBoxLayout()
            grid.setSpacing(12)

            items = [
                ("频谱倾斜", f"{t.avg_spectral_tilt:.1f} dB",
                 "负值=偏暗/头声，正值=偏亮/胸声"),
                ("谐波比 Hm/Hh", f"{t.avg_hm_over_hh:.2f}",
                 "谐波能量在基频vs高频的比值"),
                ("中高频比", f"{t.avg_mid_high_ratio:.2f}",
                 "中频(1-3kHz) vs 高频(>3kHz)能量比"),
                ("过零率 ZCR", f"{t.avg_zcr:.4f}",
                 "声带闭合紧密度指标"),
                ("RMS 能量", f"{t.avg_rms:.4f}",
                 "平均声强水平"),
                ("采样数", f"{t.sample_count} 帧",
                 "音色数据的可靠程度"),
            ]

            for i, (name, value, tooltip) in enumerate(items):
                if i > 0 and i % 3 == 0:
                    layout.addLayout(grid)
                    grid = QHBoxLayout()
                    grid.setSpacing(12)

                cell = QFrame()
                cell.setStyleSheet("""
                    QFrame { background: #161B22; border: 1px solid #21262D; border-radius: 8px; }
                """)
                cell_layout = QVBoxLayout(cell)
                cell_layout.setContentsMargins(10, 8, 10, 8)
                cell_layout.setSpacing(2)

                val_lbl = QLabel(value)
                val_lbl.setStyleSheet("color: #E6EDF3; font-size: 14px; font-weight: bold; background: transparent;")
                cell_layout.addWidget(val_lbl)

                name_lbl = QLabel(name)
                name_lbl.setStyleSheet("color: #8B949E; font-size: 10px; background: transparent;")
                name_lbl.setToolTip(tooltip)
                cell_layout.addWidget(name_lbl)

                grid.addWidget(cell)

            # 最后一行可能不满 3 个
            if grid.count() > 0:
                while grid.count() < 3:
                    spacer = QWidget()
                    spacer.setStyleSheet("background: transparent;")
                    grid.addWidget(spacer)
                grid.addStretch()
                layout.addLayout(grid)

        return self._build_section("🎨 音色指纹", widget)

    # ── 分析报告 ────────────────────────────────────────────

    def _build_reports(self) -> QWidget:
        """展示历史分析报告列表，或提示尚未测评 / 从评估数据生成报告"""
        report_files = self._find_report_files()
        has_assessment_data = self._has_assessment_data()

        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if not report_files:
            if has_assessment_data:
                # ── 有评估数据但未导出报告 ──
                vt = self._profile.effective_voice_type
                _vt_map = {
                    "tenor": "男高音", "baritone": "男中音", "bass": "男低音",
                    "soprano": "女高音", "mezzo_soprano": "女中音", "contralto": "女低音",
                }
                vt_display = _vt_map.get(vt, vt) if vt else "待测定"
                hint = QLabel(
                    f"📋 已完成声部鉴定测评\n"
                    f"   声部：{vt_display}\n"
                    f"   换声点：{_hz_to_note_name(self._profile.passaggio.t4_hz)} "
                    f"({self._profile.passaggio.t4_hz:.0f} Hz)　"
                    f"置信度 {self._profile.passaggio.confidence:.0%}\n\n"
                    f"报告尚未导出，点击下方按钮生成。"
                )
                hint.setStyleSheet("color: #C9D1D9; font-size: 12px; background: transparent;")
                hint.setWordWrap(True)
                layout.addWidget(hint)

                gen_btn = QPushButton("📄 生成分析报告")
                gen_btn.setMinimumHeight(34)
                gen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                gen_btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #238636, stop:1 #1F6FEB);
                        color: #FFFFFF; font-weight: bold;
                        padding: 8px 16px; border-radius: 8px;
                        font-size: 12px; border: none;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #2EA043, stop:1 #388BFD);
                    }
                """)
                gen_btn.clicked.connect(self._on_generate_report_from_profile)
                layout.addWidget(gen_btn)

                retest_btn = QPushButton("🔄 重新声部鉴定测评")
                retest_btn.setMinimumHeight(30)
                retest_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                retest_btn.setStyleSheet("""
                    QPushButton {
                        background: transparent; color: #A78BFA;
                        padding: 4px 12px; border-radius: 6px;
                        font-size: 11px; border: 1px solid #A78BFA;
                    }
                    QPushButton:hover { background: rgba(167, 139, 250, 0.1); }
                """)
                retest_btn.clicked.connect(self._on_voice_type_assessment)
                layout.addWidget(retest_btn)
            else:
                # ── 无评估数据，无报告 ──
                hint = QLabel("暂无分析报告，你还没有进行过声部鉴定测评。")
                hint.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent;")
                hint.setWordWrap(True)
                layout.addWidget(hint)

                assess_btn = QPushButton("🔍 开始声部鉴定测评（音域 + 换声点 + 音色）")
                assess_btn.setMinimumHeight(34)
                assess_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                assess_btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #A78BFA, stop:1 #58A6FF);
                        color: #FFFFFF; font-weight: bold;
                        padding: 8px 16px; border-radius: 8px;
                        font-size: 12px; border: none;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #B794F4, stop:1 #79B8FF);
                    }
                """)
                assess_btn.clicked.connect(self._on_voice_type_assessment)
                layout.addWidget(assess_btn)

            return self._build_section("📄 分析报告", widget)

        # ── 有报告：展示列表 ──
        count = len(report_files)
        info_label = QLabel(f"共 {count} 份分析报告")
        info_label.setStyleSheet("color: #C9D1D9; font-size: 12px; background: transparent;")
        layout.addWidget(info_label)

        # 列出最近的报告（最多显示 5 个）
        from datetime import datetime
        for rf in report_files[:5]:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            # 从文件名解析时间戳
            fname = rf.name
            ts_str = ""
            try:
                # 文件名格式: report_YYYYMMDD_HHMMSS.html
                stem = fname.replace("report_", "").replace(".html", "")
                dt = datetime.strptime(stem, "%Y%m%d_%H%M%S")
                ts_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                ts_str = fname

            report_label = QLabel(f"🕐 {ts_str}")
            report_label.setStyleSheet("color: #8B949E; font-size: 11px; background: transparent;")
            row_layout.addWidget(report_label)
            row_layout.addStretch()

            # 查看按钮
            view_btn = QPushButton("📄 查看")
            view_btn.setMinimumHeight(28)
            view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            view_btn.setStyleSheet("""
                QPushButton {
                    background: #21262D; color: #58A6FF;
                    padding: 4px 12px; border-radius: 6px;
                    font-size: 11px; border: 1px solid #30363D;
                }
                QPushButton:hover {
                    background: rgba(88, 166, 255, 0.1);
                    border-color: #58A6FF;
                }
            """)
            filepath = str(rf.absolute())
            view_btn.clicked.connect(lambda checked=False, fp=filepath: self._on_view_report(fp))
            row_layout.addWidget(view_btn)

            layout.addLayout(row_layout)

        # 打开报告目录按钮
        open_dir_btn = QPushButton("📂 打开报告目录")
        open_dir_btn.setMinimumHeight(30)
        open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_dir_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8B949E;
                padding: 4px 12px; border-radius: 6px;
                font-size: 11px; border: 1px solid #30363D;
            }
            QPushButton:hover { background: #21262D; color: #C9D1D9; }
        """)
        reports_dir = str(report_files[0].parent)
        open_dir_btn.clicked.connect(lambda: self._on_open_reports_dir(reports_dir))
        layout.addWidget(open_dir_btn)

        return self._build_section("📄 分析报告", widget)

    def _find_report_files(self) -> list:
        """查找当前存档的所有 HTML 报告文件（按时间倒序）"""
        try:
            from pathlib import Path
            report_dir = self._mgr._root / self._profile.folder_name / "reports"
            if not report_dir.exists():
                return []
            files = sorted(
                report_dir.glob("report_*.html"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            return files
        except Exception:
            return []

    def _on_view_report(self, filepath: str) -> None:
        """在浏览器中打开指定报告"""
        import webbrowser
        try:
            webbrowser.open(filepath)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开报告:\n{filepath}\n\n错误: {e}")

    def _on_open_reports_dir(self, dirpath: str) -> None:
        """在文件管理器中打开报告目录"""
        import os
        import subprocess
        try:
            if os.name == 'nt':
                os.startfile(dirpath)
            else:
                subprocess.Popen(['xdg-open', dirpath])
        except Exception:
            pass

    def _has_assessment_data(self) -> bool:
        """检查 profile 中是否已有声部鉴定评估数据"""
        p = self._profile
        # 有推断声部 + 换声点数据 = 已完成测评
        return bool(
            p.voice_type_inferred
            and p.passaggio.t4_hz > 0
        )

    def _on_generate_report_from_profile(self) -> None:
        """从现有 profile 评估数据生成并导出 HTML 报告"""
        try:
            from src.gui.voice_type_assessment_dialog import generate_report_from_profile

            filepath = generate_report_from_profile(self._profile, self._mgr)
            QMessageBox.information(
                self, "报告已生成",
                f"声乐评估报告已保存到:\n{filepath}\n\n已在浏览器中打开。"
            )
            self._rebuild_content()
        except ValueError as e:
            QMessageBox.warning(self, "无法生成", f"无法生成报告：{e}\n请先完成声部鉴定测评。")
        except Exception as e:
            QMessageBox.warning(self, "生成失败", f"无法生成报告：{e}")

    # ── AI Coach 联动 ───────────────────────────────────────

    def _build_ai_coach(self) -> QWidget:
        """展示当前存档的评估数据摘要，并提供同步到AI教练的按钮"""
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        p = self._profile
        vt = p.effective_voice_type
        pp = p.passaggio
        ps = p.pitch_stats
        t = p.timbre

        # ── 声部 & 性别 ──
        _vt_map = {
            "tenor": "男高音", "baritone": "男中音", "bass": "男低音",
            "soprano": "女高音", "mezzo_soprano": "女中音", "contralto": "女低音",
        }
        vt_display = _vt_map.get(vt, vt) if vt else "未测定"
        gender_display = _gender_display(p.effective_gender)

        # 数据行 - 用 compact grid
        data_grid = QHBoxLayout()
        data_grid.setSpacing(10)

        # 左列
        left_col = QVBoxLayout()
        left_col.setSpacing(6)

        # 声部
        vt_row = QHBoxLayout()
        vt_icon = QLabel("🎵")
        vt_icon.setStyleSheet("font-size: 14px; background: transparent;")
        vt_label = QLabel(f"声部：<b>{vt_display}</b>  ·  {gender_display}")
        vt_label.setStyleSheet("color: #E6EDF3; font-size: 12px; background: transparent;")
        vt_row.addWidget(vt_icon)
        vt_row.addWidget(vt_label)
        vt_row.addStretch()
        left_col.addLayout(vt_row)

        # 换声点
        if pp.t4_hz > 0:
            t4_note = _hz_to_note_name(pp.t4_hz)
            src_str = "已校准" if pp.source == "calibrated" else "自动估计"
            t4_row = QHBoxLayout()
            t4_icon = QLabel("🔄")
            t4_icon.setStyleSheet("font-size: 14px; background: transparent;")
            t4_label = QLabel(f"换声点 T4：<b>{t4_note}</b> ({pp.t4_hz:.0f}Hz)  ·  {src_str}  ·  置信度 {pp.confidence:.0%}")
            t4_label.setStyleSheet("color: #C9D1D9; font-size: 12px; background: transparent;")
            t4_row.addWidget(t4_icon)
            t4_row.addWidget(t4_label)
            t4_row.addStretch()
            left_col.addLayout(t4_row)

        # 音域
        if ps.min_hz > 0 and ps.max_hz > 0:
            range_note_low = _hz_to_note_name(ps.min_hz)
            range_note_high = _hz_to_note_name(ps.max_hz)
            range_span = 12 * math.log2(ps.max_hz / ps.min_hz) if ps.min_hz > 0 else 0
            range_row = QHBoxLayout()
            range_icon = QLabel("🎶")
            range_icon.setStyleSheet("font-size: 14px; background: transparent;")
            range_label = QLabel(
                f"音域：<b>{range_note_low}</b> → <b>{range_note_high}</b> "
                f"（{range_span:.1f} 半音） · 中位 {_hz_to_note_name(ps.p50_hz)}"
            )
            range_label.setStyleSheet("color: #C9D1D9; font-size: 12px; background: transparent;")
            range_row.addWidget(range_icon)
            range_row.addWidget(range_label)
            range_row.addStretch()
            left_col.addLayout(range_row)

        # 练习统计
        practice_row = QHBoxLayout()
        practice_icon = QLabel("⏱")
        practice_icon.setStyleSheet("font-size: 14px; background: transparent;")
        practice_label = QLabel(f"累计练习：<b>{p.usage.total_minutes:.0f}</b> 分钟 · <b>{p.usage.total_sessions}</b> 次录音")
        practice_label.setStyleSheet("color: #C9D1D9; font-size: 12px; background: transparent;")
        practice_row.addWidget(practice_icon)
        practice_row.addWidget(practice_label)
        practice_row.addStretch()
        left_col.addLayout(practice_row)

        # 音色样本数
        if t.sample_count > 0:
            timbre_row = QHBoxLayout()
            timbre_icon = QLabel("🎨")
            timbre_icon.setStyleSheet("font-size: 14px; background: transparent;")
            timbre_label = QLabel(f"音色指纹：已分析 <b>{t.sample_count}</b> 个样本")
            timbre_label.setStyleSheet("color: #C9D1D9; font-size: 12px; background: transparent;")
            timbre_row.addWidget(timbre_icon)
            timbre_row.addWidget(timbre_label)
            timbre_row.addStretch()
            left_col.addLayout(timbre_row)

        data_grid.addLayout(left_col)
        layout.addLayout(data_grid)

        # ── 尝试获取 AI Coach 在线数据 ──
        coach_data = self._get_coach_data()
        if coach_data is not None:
            total_coach_sessions = coach_data.get("total_sessions", 0)
            last_topic = coach_data.get("last_topic", "—")
            if total_coach_sessions > 0:
                coach_info = QLabel(
                    f"🧠 AI 教练已对话 <b>{total_coach_sessions}</b> 次"
                    f"{'  ·  最近主题：' + last_topic if last_topic and last_topic != '—' else ''}"
                )
                coach_info.setStyleSheet("color: #58A6FF; font-size: 11px; background: transparent; padding: 4px 0;")
                coach_info.setWordWrap(True)
                layout.addWidget(coach_info)

        # ── 同步按钮 ──
        sync_btn = QPushButton("🔄 同步数据到 AI 教练")
        sync_btn.setMinimumHeight(34)
        sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_btn.setToolTip("将当前存档的声部、换声点、音域等数据同步到 AI 教练面板")
        sync_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #58A6FF;
                padding: 8px 16px; border-radius: 8px;
                font-size: 12px; border: 1px solid #30363D;
            }
            QPushButton:hover { background: rgba(88, 166, 255, 0.1); border-color: #58A6FF; }
        """)
        sync_btn.clicked.connect(self._on_sync_to_ai_coach)
        layout.addWidget(sync_btn)

        return self._build_section("🧠 AI 教练联动", widget)

    def _get_coach_data(self) -> Optional[dict]:
        """尝试从主窗口的 AI Coach 模块获取训练数据"""
        try:
            # 遍历父窗口链找到主窗口
            ancestor = self.parent()
            while ancestor is not None:
                # 主窗口有 _ai_coach_panel 属性
                panel = getattr(ancestor, '_ai_coach_panel', None)
                if panel is not None:
                    cp = getattr(panel, 'coach_panel', None)
                    if cp is not None:
                        agent = getattr(cp, 'agent', None)
                        if agent is not None:
                            sm = getattr(agent, 'session_mgr', None)
                            if sm is not None:
                                return {
                                    "total_sessions": getattr(sm, 'total_sessions', getattr(sm, 'session_count', 0)),
                                    "last_topic": getattr(sm, 'last_topic', '—'),
                                    "mastery_pct": getattr(sm, 'mastery_pct', 0),
                                }
                        # 回退：没有 agent 就没有对话数据
                        break
                ancestor = ancestor.parent()
        except Exception:
            pass
        return None

    def _on_sync_to_ai_coach(self) -> None:
        """将当前存档数据同步到 AI 教练面板"""
        try:
            # 遍历父窗口链找到主窗口
            ancestor = self.parent()
            while ancestor is not None:
                if hasattr(ancestor, '_notify_ai_coach_profile_changed'):
                    # 先临时设置主窗口的 _active_profile 为当前存档
                    old_profile = getattr(ancestor, '_active_profile', None)
                    try:
                        ancestor._active_profile = self._profile
                        ancestor._notify_ai_coach_profile_changed()
                    finally:
                        # 恢复原来的 active_profile
                        ancestor._active_profile = old_profile
                    QMessageBox.information(
                        self, "同步成功",
                        f"已将「{self._profile.name}」的存档数据同步到 AI 教练面板。\n"
                        "请切换到 AI 教练面板查看更新。"
                    )
                    return
                ancestor = ancestor.parent()
            QMessageBox.warning(self, "同步失败", "未找到 AI 教练面板，请先启动 AI 教练。")
        except Exception as e:
            QMessageBox.warning(self, "同步失败", f"无法同步：{e}")

    # ── 通用工具 ────────────────────────────────────────────

    def _build_section(self, title: str, content: QWidget) -> QWidget:
        """构建带标题的区块"""
        section = QWidget()
        section.setStyleSheet("background: transparent;")
        slayout = QVBoxLayout(section)
        slayout.setContentsMargins(0, 0, 0, 0)
        slayout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #8B949E; font-size: 11px; font-weight: bold; letter-spacing: 0.5px; background: transparent;")
        slayout.addWidget(title_label)

        slayout.addWidget(content)
        return section

    def _on_calibrate_passaggio(self) -> None:
        """打开换声点手动校准对话框"""
        dlg = PassaggioCalibrationDialog(self._profile, self._mgr, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # 重新加载更新后的存档
            updated = self._mgr.get_profile(self._profile.id)
            if updated is not None:
                self._profile = updated
                self.setWindowTitle(f"存档详情 — {updated.name}")
                self._rebuild_content()
            # 通知父窗口数据已更新
            self.accept()

    def _on_voice_type_assessment(self) -> None:
        """打开声部鉴定测评对话框"""
        dlg = VoiceTypeAssessmentDialog(self._profile, self._mgr, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # 重新加载更新后的存档
            updated = self._mgr.get_profile(self._profile.id)
            if updated is not None:
                self._profile = updated
                self.setWindowTitle(f"存档详情 — {updated.name}")
                self._rebuild_content()
            # 通知父窗口 (ProfileSelectionDialog) 数据已更新
            self.accept()

    def _on_edit(self) -> None:
        dlg = ProfileEditDialog(self._profile, self._mgr, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # 重新加载存档
            updated = self._mgr.get_profile(self._profile.id)
            if updated is not None:
                self._profile = updated
                self.setWindowTitle(f"存档详情 — {updated.name}")
                # 刷新 UI（简单重建）
                self._rebuild_content()

    def _rebuild_content(self) -> None:
        """编辑保存后重建 UI"""
        # 清除布局中的旧 widget
        main_layout = self.layout()
        if main_layout is None:
            return
        while main_layout.count():
            item = main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._build_ui()
