"""存档选择对话框 —— ProfileSelectionDialog / ProfileCreationDialog

在开始录音前弹出，让用户选择或创建歌手存档。
支持：选择已有存档、创建新存档、访客模式、记住本次选择。
"""

from __future__ import annotations

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
                self.accept()
            else:
                self._refresh_list()

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

        self.setWindowTitle("创建歌手存档")
        self.setMinimumSize(420, 380)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # ── 标题 ──
        title = QLabel("🎙️ 创建你的歌手存档")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        info = QLabel(
            "存档会记录你的音域、换声点、音色特征，\n"
            "随着使用次数增加，识别会越来越精准。\n"
            "后续可以随时在校准页面测定换声点。"
        )
        info.setStyleSheet("color: #666;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── 分割线 ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("QFrame { color: #e0e0e0; }")
        layout.addWidget(line)

        # ── 名称 ──
        name_layout = QHBoxLayout()
        name_label = QLabel("存档名称：")
        name_label.setMinimumWidth(80)
        name_layout.addWidget(name_label)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("例如：张三（建议使用你的名字或昵称）")
        self._name_edit.setMinimumHeight(32)
        name_layout.addWidget(self._name_edit)
        layout.addLayout(name_layout)

        # ── 性别 ──
        gender_layout = QHBoxLayout()
        gender_label = QLabel("性别：")
        gender_label.setMinimumWidth(80)
        gender_layout.addWidget(gender_label)
        self._gender_group = QButtonGroup(self)
        gender_opts_layout = QHBoxLayout()
        for key, label in _GENDER_OPTIONS:
            rb = QRadioButton(label)
            self._gender_group.addButton(rb)
            gender_opts_layout.addWidget(rb)
            if key == "":
                rb.setChecked(True)
        gender_opts_layout.addStretch()
        gender_layout.addLayout(gender_opts_layout)
        layout.addLayout(gender_layout)

        # ── 声部 ──
        voice_layout = QHBoxLayout()
        voice_label = QLabel("声部：")
        voice_label.setMinimumWidth(80)
        voice_layout.addWidget(voice_label)
        self._voice_combo = QComboBox()
        self._voice_combo.setMinimumHeight(32)
        for key, label in _VOICE_TYPE_OPTIONS:
            self._voice_combo.addItem(label, key)
        self._voice_combo.setCurrentIndex(0)  # 默认"不指定"
        voice_layout.addWidget(self._voice_combo)
        layout.addLayout(voice_layout)

        # ── 提示 ──
        hint = QLabel(
            "💡 提示：声部可选「不指定」，后续可通过\n"
            "　　 换声点校准功能自动测定。"
        )
        hint.setStyleSheet("color: #999; font-size: 10pt;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

        # ── 按钮行 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        btn_layout.addStretch()

        self._create_btn = QPushButton("创建存档")
        self._create_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "padding: 8px 24px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #388E3C; }"
        )
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
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "创建失败", str(e))


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
        self.setMinimumSize(500, 450)
        self.setModal(False)  # 非模态，允许用户在用户中心打开时继续操作

        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── 标题 ──
        title = QLabel("👤 用户中心")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # ── 当前存档状态 ──
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_frame.setStyleSheet(
            "QFrame { background: #263238; border-radius: 8px; padding: 10px; }"
        )
        status_layout = QVBoxLayout(status_frame)
        status_title = QLabel("📌 当前存档")
        status_title.setStyleSheet("color: #80CBC4; font-weight: bold; font-size: 12px;")
        status_layout.addWidget(status_title)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #fff; font-size: 13px;")
        self._status_label.setWordWrap(True)
        status_layout.addWidget(self._status_label)
        layout.addWidget(status_frame)

        # ── 存档列表 ──
        list_label = QLabel("全部存档：")
        list_label.setStyleSheet("font-weight: bold; color: #ccc;")
        layout.addWidget(list_label)

        self._list_widget = QListWidget()
        self._list_widget.setMinimumHeight(160)
        self._list_widget.setStyleSheet("""
            QListWidget {
                background: #1a1a2e; border: 1px solid #333; border-radius: 6px;
            }
            QListWidget::item {
                padding: 10px 12px; border-bottom: 1px solid #2a2a3a; color: #ddd;
            }
            QListWidget::item:selected {
                background-color: #2a3a4a;
            }
        """)
        layout.addWidget(self._list_widget)

        self._empty_label = QLabel("还没有存档。点击「新建存档」创建一个吧～")
        self._empty_label.setStyleSheet("color: #666; padding: 20px;")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

        # ── 按钮行 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._activate_btn = QPushButton("✓ 使用此存档")
        self._activate_btn.setEnabled(False)
        self._activate_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "padding: 8px 16px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #388E3C; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        self._activate_btn.clicked.connect(self._on_activate)
        btn_layout.addWidget(self._activate_btn)

        self._new_btn = QPushButton("＋ 新建")
        self._new_btn.setStyleSheet(
            "QPushButton { padding: 8px 14px; border-radius: 4px; "
            "background: #1a3a1a; color: #A5D6A7; border: 1px solid #388E3C; }"
            "QPushButton:hover { background: #2a4a2a; }"
        )
        self._new_btn.clicked.connect(self._on_create)
        btn_layout.addWidget(self._new_btn)

        self._edit_btn = QPushButton("✎ 编辑")
        self._edit_btn.setEnabled(False)
        self._edit_btn.setStyleSheet(
            "QPushButton { padding: 8px 14px; border-radius: 4px; "
            "background: #1a1a3a; color: #90CAF9; border: 1px solid #1565C0; }"
            "QPushButton:hover { background: #2a2a4a; }"
            "QPushButton:disabled { background: #222; color: #555; border-color: #333; }"
        )
        self._edit_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(self._edit_btn)

        self._delete_btn = QPushButton("🗑 删除")
        self._delete_btn.setEnabled(False)
        self._delete_btn.setStyleSheet(
            "QPushButton { padding: 8px 14px; border-radius: 4px; "
            "background: #3a1a1a; color: #EF9A9A; border: 1px solid #C62828; }"
            "QPushButton:hover { background: #4a2a2a; }"
            "QPushButton:disabled { background: #222; color: #555; border-color: #333; }"
        )
        self._delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._delete_btn)

        self._guest_btn = QPushButton("访客模式")
        self._guest_btn.setStyleSheet(
            "QPushButton { padding: 8px 14px; border-radius: 4px; color: #999; "
            "background: #222; border: 1px solid #555; }"
            "QPushButton:hover { background: #333; color: #ccc; }"
        )
        self._guest_btn.clicked.connect(self._on_guest_mode)
        btn_layout.addWidget(self._guest_btn)

        layout.addLayout(btn_layout)

        # 列表点击事件
        self._list_widget.itemSelectionChanged.connect(self._on_list_selection)

    def _refresh(self) -> None:
        """刷新列表和状态"""
        self._list_widget.clear()
        profiles = self._mgr.list_profiles()
        self._empty_label.setVisible(len(profiles) == 0)

        active_id = self._active_profile.id if self._active_profile else ""

        for p in profiles:
            vt = _voice_type_display(p.effective_voice_type)
            gender = _gender_display(p.effective_gender)
            mins = p.usage.total_minutes
            is_active = (p.id == active_id)
            marker = " ★" if is_active else ""
            text = f"{p.name}{marker}\n  {vt} · {gender} · {mins:.0f}分钟"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, p.id)
            if is_active:
                item.setForeground(Qt.GlobalColor.green)
            self._list_widget.addItem(item)

        self._update_status()
        self._activate_btn.setEnabled(False)
        self._edit_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)

    def _update_status(self) -> None:
        if self._active_profile is None:
            self._status_label.setText(
                "当前：🚪 访客模式\n"
                "使用默认参数，数据不会保存。建议创建存档以获得个性化识别。"
            )
            return
        p = self._active_profile
        vt = _voice_type_display(p.effective_voice_type)
        gender = _gender_display(p.effective_gender)
        lines = [
            f"📛 {p.name}　　🎵 {vt}　　👤 {gender}",
            f"📊 累计 {p.usage.total_minutes:.0f} 分钟 · {p.usage.total_sessions} 次录音",
        ]
        if p.passaggio.t4_hz > 0 and p.passaggio.confidence > 0:
            lines.append(f"🔄 换声点: {p.passaggio.t4_hz:.0f} Hz (置信度 {p.passaggio.confidence:.0%})")
        self._status_label.setText("\n".join(lines))

    def _on_list_selection(self) -> None:
        selected = self._list_widget.currentItem()
        has_selection = selected is not None
        self._activate_btn.setEnabled(has_selection)
        self._edit_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)

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
            # 如果编辑的是当前活跃存档，更新引用
            if self._active_profile and self._active_profile.id == profile.id:
                self._active_profile = self._mgr.get_profile(profile.id)
                self.result_profile = self._active_profile
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
        self.setMinimumSize(400, 300)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(f"✏️ 编辑「{self._profile.name}」")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # 名称
        name_layout = QHBoxLayout()
        name_label = QLabel("名称：")
        name_label.setMinimumWidth(60)
        name_layout.addWidget(name_label)
        self._name_edit = QLineEdit(self._profile.name)
        self._name_edit.setMinimumHeight(30)
        name_layout.addWidget(self._name_edit)
        layout.addLayout(name_layout)

        # 性别
        gender_layout = QHBoxLayout()
        gender_label = QLabel("性别：")
        gender_label.setMinimumWidth(60)
        gender_layout.addWidget(gender_label)
        self._gender_group = QButtonGroup(self)
        g_layout = QHBoxLayout()
        for key, label in _GENDER_OPTIONS:
            rb = QRadioButton(label)
            self._gender_group.addButton(rb)
            g_layout.addWidget(rb)
            if key == self._profile.gender_manual:
                rb.setChecked(True)
        if self._gender_group.checkedButton() is None:
            # 默认选"不指定"
            for btn in self._gender_group.buttons():
                if btn.text() == "不指定":
                    btn.setChecked(True)
                    break
        g_layout.addStretch()
        gender_layout.addLayout(g_layout)
        layout.addLayout(gender_layout)

        # 声部
        voice_layout = QHBoxLayout()
        voice_label = QLabel("声部：")
        voice_label.setMinimumWidth(60)
        voice_layout.addWidget(voice_label)
        self._voice_combo = QComboBox()
        self._voice_combo.setMinimumHeight(30)
        for key, label in _VOICE_TYPE_OPTIONS:
            self._voice_combo.addItem(label, key)
        # 选中当前值
        for i in range(self._voice_combo.count()):
            if self._voice_combo.itemData(i) == self._profile.voice_type_manual:
                self._voice_combo.setCurrentIndex(i)
                break
        voice_layout.addWidget(self._voice_combo)
        layout.addLayout(voice_layout)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "padding: 8px 20px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #388E3C; }"
        )
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
