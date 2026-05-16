"""AI 声乐教练对话面板 —— 可嵌入 IntegratedRecordingInterface 的 QWidget"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..agent import VocalCoachAgent
from ..context.builder import SingingContext
from ..llm_client import DeepSeekConfig

# 以下为 PyQt6 导入，在无 GUI 环境会优雅降级
try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
        QPushButton, QLabel, QScrollArea, QSplitter, QTabWidget,
        QTextBrowser, QFileDialog, QMessageBox, QComboBox, QFrame,
        QProgressBar,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt6.QtGui import QFont, QTextCursor, QColor
    _QT_AVAILABLE = True
except ImportError:
    try:
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
            QPushButton, QLabel, QScrollArea, QSplitter, QTabWidget,
            QTextBrowser, QFileDialog, QMessageBox, QComboBox, QFrame,
            QProgressBar,
        )
        from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
        from PyQt5.QtGui import QFont, QTextCursor, QColor
        _QT_AVAILABLE = True
    except ImportError:
        _QT_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════
# LLM 工作线程
# ═══════════════════════════════════════════════════════════════


class _AgentWorker(QThread):
    """后台执行 Agent 调用，避免阻塞 UI"""
    finished = pyqtSignal(str)
    token = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, task: str, **kwargs):
        super().__init__()
        self.task = task
        self.kwargs = kwargs

    def run(self):
        pass  # 在 _AgentThread 中实现具体逻辑


class _AgentThread(QThread):
    """Agent 分析线程"""
    result_ready = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, agent: VocalCoachAgent, task_type: str, **kwargs):
        super().__init__()
        self.agent = agent
        self.task_type = task_type  # "chat", "analyze", "compare", "plan", "report"
        self.kwargs = kwargs

    def run(self):
        try:
            if self.task_type == "chat":
                result = self.agent.chat(
                    self.kwargs["message"],
                    with_knowledge=self.kwargs.get("with_knowledge", True),
                )
            elif self.task_type == "analyze":
                result = self.agent.analyze_performance(
                    analysis_json_path=self.kwargs.get("json_path"),
                    song_name=self.kwargs.get("song_name", ""),
                )
            elif self.task_type == "compare":
                result = self.agent.compare_with_reference(
                    self.kwargs["user_json"],
                    self.kwargs["ref_json"],
                    song_name=self.kwargs.get("song_name", ""),
                    reference_name=self.kwargs.get("reference_name", "专业歌手"),
                )
            elif self.task_type == "plan":
                result = self.agent.generate_practice_plan(
                    user_goal=self.kwargs.get("user_goal", "全面提升"),
                )
            elif self.task_type == "report":
                result = self.agent.generate_report(
                    analysis_json_path=self.kwargs.get("json_path"),
                    song_name=self.kwargs.get("song_name", ""),
                )
            else:
                result = "未知任务类型"
            self.result_ready.emit(result)
        except Exception as e:
            self.result_ready.emit(f"❌ 出错了: {str(e)}")


# ═══════════════════════════════════════════════════════════════
# 对话面板
# ═══════════════════════════════════════════════════════════════


class AICoachPanel(QWidget):
    """AI 声乐教练对话面板"""

    def __init__(
        self,
        agent: Optional[VocalCoachAgent] = None,
        parent=None,
    ):
        if not _QT_AVAILABLE:
            raise ImportError("需要 PyQt6 或 PyQt5")

        super().__init__(parent)
        self.agent = agent or VocalCoachAgent(
            on_thinking=self._on_thinking,
            on_response=self._on_response_done,
            on_stream_token=self._on_stream_token,
        )
        self._pending_tokens: list[str] = []
        self._init_ui()
        self._connect_signals()

        # 欢迎消息
        self._append_message(
            "assistant",
            "你好！我是 MindEcho AI 声乐教练 🎵\n\n"
            "我可以帮你：\n"
            "- 分析你的演唱录音，给出具体改进建议\n"
            "- 将你的演唱与专业歌手进行对比\n"
            "- 回答声乐相关的任何问题\n"
            "- 制定个性化的练习计划\n\n"
            "你可以：\n"
            "- 直接打字提问\n"
            "- 先录一首歌，然后点 **分析演唱**\n"
            "- 加载你和专业歌手的分析文件，点 **对比分析**\n\n"
            f"知识库已加载：{self.agent.knowledge_stats['entry_count']} 条声乐知识\n"
            f"涵盖分类：{', '.join(self.agent.knowledge_stats['categories'])}"
        )

    # ── UI 构建 ───────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Profile bar
        profile_bar = QHBoxLayout()
        self.profile_label = QLabel("加载中...")
        self.profile_label.setStyleSheet("color: #888; font-size: 11px;")
        profile_bar.addWidget(self.profile_label)
        profile_bar.addStretch()
        layout.addLayout(profile_bar)

        # Splitter: chat + report
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Chat display
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(True)
        self.chat_display.setStyleSheet("""
            QTextBrowser {
                background-color: #1a1a2e;
                color: #e0e0e0;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
            }
        """)
        splitter.addWidget(self.chat_display)

        # Report tab
        report_tabs = QTabWidget()
        self.report_display = QTextBrowser()
        self.report_display.setStyleSheet("""
            QTextBrowser {
                background-color: #1a1a2e;
                color: #e0e0e0;
                border: 1px solid #333;
                font-size: 12px;
            }
        """)
        report_tabs.addTab(self.report_display, "分析报告")
        splitter.addWidget(report_tabs)
        splitter.setSizes([400, 200])
        layout.addWidget(splitter)

        # Thinking indicator
        self.thinking_bar = QProgressBar()
        self.thinking_bar.setRange(0, 0)  # 不确定进度
        self.thinking_bar.setVisible(False)
        self.thinking_bar.setMaximumHeight(4)
        self.thinking_bar.setStyleSheet("QProgressBar { border: none; background: transparent; }")
        layout.addWidget(self.thinking_bar)

        # Action buttons
        btn_layout = QHBoxLayout()

        self.btn_analyze = QPushButton("分析演唱")
        self.btn_analyze.setToolTip("分析最近一次录音")
        btn_layout.addWidget(self.btn_analyze)

        self.btn_compare = QPushButton("对比分析")
        self.btn_compare.setToolTip("与专业歌手的音高曲线对比")
        btn_layout.addWidget(self.btn_compare)

        self.btn_plan = QPushButton("练习计划")
        self.btn_plan.setToolTip("生成个性化练习计划")
        btn_layout.addWidget(self.btn_plan)

        self.btn_report = QPushButton("导出报告")
        self.btn_report.setToolTip("导出 Markdown 分析报告")
        btn_layout.addWidget(self.btn_report)

        self.btn_clear = QPushButton("清空对话")
        btn_layout.addWidget(self.btn_clear)

        for btn in [self.btn_analyze, self.btn_compare, self.btn_plan, self.btn_report, self.btn_clear]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2a2a4a;
                    color: #e0e0e0;
                    border: 1px solid #444;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #3a3a5a;
                }
                QPushButton:pressed {
                    background-color: #4a4a6a;
                }
            """)

        layout.addLayout(btn_layout)

        # Input area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("输入你的问题，或点击上方按钮...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a4a;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
        """)
        self.btn_send = QPushButton("发送")
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #4a6a9a;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5a7aaa; }
        """)
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.btn_send)
        layout.addLayout(input_layout)

        self.setMinimumSize(400, 500)

    def _connect_signals(self):
        self.btn_send.clicked.connect(self._on_send)
        self.input_field.returnPressed.connect(self._on_send)
        self.btn_analyze.clicked.connect(self._on_analyze)
        self.btn_compare.clicked.connect(self._on_compare)
        self.btn_plan.clicked.connect(self._on_plan)
        self.btn_report.clicked.connect(self._on_report)
        self.btn_clear.clicked.connect(self._on_clear)

        # 延迟加载 profile
        QTimer.singleShot(100, self._refresh_profile)

    # ── 事件处理 ─────────────────────────────────────────────

    def _on_send(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self._append_message("user", text)
        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.btn_send.setEnabled(False)
        self._run_agent_task("chat", message=text)

    def _on_analyze(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 MindEcho 分析文件", "",
            "JSON 文件 (*_analysis.json);;所有文件 (*)"
        )
        if not path:
            return
        song_name = Path(path).stem.replace("_analysis", "").replace("_", " ")
        self._append_message("user", f"[分析演唱] {song_name}")
        self._run_agent_task("analyze", json_path=path, song_name=song_name)

    def _on_compare(self):
        user_path, _ = QFileDialog.getOpenFileName(
            self, "选择你的演唱分析文件", "",
            "JSON 文件 (*_analysis.json);;所有文件 (*)"
        )
        if not user_path:
            return
        ref_path, _ = QFileDialog.getOpenFileName(
            self, "选择专业参考分析文件", "",
            "JSON 文件 (*_analysis.json);;所有文件 (*)"
        )
        if not ref_path:
            return
        song_name = Path(user_path).stem.replace("_analysis", "").replace("_", " ")
        self._append_message("user", f"[对比分析] {song_name}")
        self._run_agent_task("compare", user_json=user_path, ref_json=ref_path,
                             song_name=song_name)

    def _on_plan(self):
        self._append_message("user", "[请求练习计划]")
        self._run_agent_task("plan", user_goal="全面提升歌唱能力")

    def _on_report(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 MindEcho 分析文件", "",
            "JSON 文件 (*_analysis.json);;所有文件 (*)"
        )
        if not path:
            return
        song_name = Path(path).stem.replace("_analysis", "").replace("_", " ")
        self._append_message("user", f"[生成报告] {song_name}")

        try:
            report = self.agent.generate_report(
                analysis_json_path=path, song_name=song_name
            )
            self.report_display.setMarkdown(report)
            self._append_message("assistant", '报告已生成，请在下方「分析报告」标签页查看。')
        except Exception as e:
            self._append_message("assistant", f"报告生成失败: {e}")

    def _on_clear(self):
        self.chat_display.clear()
        self.agent.session_mgr.clear_chat_history()

    def _on_thinking(self):
        self.thinking_bar.setVisible(True)

    def _on_stream_token(self, token: str):
        self._pending_tokens.append(token)
        # 每收到 5 个 token 更新一次 UI（减少刷新频率）
        if len(self._pending_tokens) >= 5:
            self._flush_pending_tokens()

    def _on_response_done(self, response: str):
        self._flush_pending_tokens()
        self.thinking_bar.setVisible(False)
        self.input_field.setEnabled(True)
        self.btn_send.setEnabled(True)
        self._refresh_profile()

    def _flush_pending_tokens(self):
        if self._pending_tokens:
            text = "".join(self._pending_tokens)
            self._pending_tokens.clear()
            cursor = self.chat_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text)
            self.chat_display.setTextCursor(cursor)
            self.chat_display.ensureCursorVisible()

    # ── 工具方法 ─────────────────────────────────────────────

    def _run_agent_task(self, task_type: str, **kwargs):
        """在后台线程中运行 Agent 任务"""
        self.thinking_bar.setVisible(True)
        self._pending_tokens.clear()

        # 禁用 UI（流式响应用 _flush 更新，非流式用 result_ready 更新）
        if task_type == "chat":
            self.thread = _AgentThread(self.agent, task_type, **kwargs)
        else:
            self.thread = _AgentThread(self.agent, task_type, **kwargs)
        self.thread.result_ready.connect(self._on_agent_result)
        self.thread.finished.connect(lambda: self.thinking_bar.setVisible(False))
        self.thread.finished.connect(lambda: self.input_field.setEnabled(True))
        self.thread.finished.connect(lambda: self.btn_send.setEnabled(True))
        self.thread.start()

    def _on_agent_result(self, result: str):
        # 流式会话已通过 on_stream 更新，直接追加最终结果
        if not self._pending_tokens:
            self._append_message("assistant", result)
        self._refresh_profile()

    def _append_message(self, role: str, content: str):
        """在对话区追加一条消息"""
        if role == "user":
            header = '<div style="color: #6a9fd8; font-weight: bold; margin-top: 8px;">你:</div>'
        else:
            header = '<div style="color: #8fd86a; font-weight: bold; margin-top: 8px;">AI 教练:</div>'

        # 简单 Markdown → HTML
        body = content.replace("\n\n", "</p><p>").replace("\n", "<br>")
        body = f"<p>{body}</p>"

        self.chat_display.append(f"{header}{body}")
        # 滚动到底部
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )

    def _refresh_profile(self):
        try:
            summary = self.agent.get_profile_summary()
            self.profile_label.setText(summary.replace("\n", " | "))
        except Exception:
            pass
