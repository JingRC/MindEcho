"""AI 声乐教练对话面板 —— 可嵌入 IntegratedRecordingInterface 的 QWidget"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..agent import VocalCoachAgent
from ..config import AppConfig, ConfigManager
from ..context.builder import SingingContext
from ..identity import CoachIdentity
from ..llm_client import LLMConfig
from .settings_panel import CoachSettingsDialog

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
# 语音输入线程
# ═══════════════════════════════════════════════════════════════

_VOICE_AVAILABLE = False
try:
    import speech_recognition as _sr
    _VOICE_AVAILABLE = True
except ImportError:
    pass


class _VoiceWorker(QThread):
    """后台语音识别线程"""
    result = pyqtSignal(str)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def run(self):
        try:
            r = _sr.Recognizer()
            with _sr.Microphone() as source:
                self.status.emit("正在聆听...")
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=8, phrase_time_limit=15)
            self.status.emit("正在识别...")
            text = r.recognize_google(audio, language="zh-CN")
            if text:
                self.result.emit(text)
            else:
                self.error.emit("未识别到语音内容")
        except _sr.WaitTimeoutError:
            self.error.emit("聆听超时，请点击麦克风重试")
        except _sr.UnknownValueError:
            self.error.emit("无法识别语音内容，请说得清晰一些")
        except _sr.RequestError as e:
            self.error.emit(f"语音服务不可用: {e}")
        except Exception as e:
            self.error.emit(f"语音输入失败: {e}")


# ═══════════════════════════════════════════════════════════════
# 对话面板
# ═══════════════════════════════════════════════════════════════


class AICoachPanel(QWidget):
    """AI 声乐教练对话面板"""

    # 配置变更回调（由 AICoachDockPanel 设置，用于同步桌宠）
    on_config_changed = None

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

        # 流式输出定时器：每 50ms 刷新一次，产生连续打字效果
        self._stream_timer = QTimer(self)
        self._stream_timer.setInterval(50)
        self._stream_timer.timeout.connect(self._flush_pending_tokens)

        self._init_ui()
        self._connect_signals()

        # 欢迎消息
        identity = self.agent.identity
        self._append_message("assistant", identity.get_greeting())

    # ── UI 构建 ───────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

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

        # 练习数据可视化标签页
        self.chart_display = QTextBrowser()
        self.chart_display.setStyleSheet("""
            QTextBrowser {
                background-color: #1a1a2e;
                color: #e0e0e0;
                border: 1px solid #333;
                font-size: 12px;
            }
        """)
        report_tabs.addTab(self.chart_display, "练习数据")

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

        # ── 按钮区：两行布局，主操作在上、辅助操作在下 ──
        _btn_style = """
            QPushButton {
                background-color: #2a2a4a; color: #e0e0e0;
                border: 1px solid #444; border-radius: 6px;
                padding: 7px 14px; font-size: 12px;
            }
            QPushButton:hover { background-color: #3a3a5a; border-color: #5a7aaa; }
            QPushButton:pressed { background-color: #4a4a6a; }
        """
        _btn_primary_style = """
            QPushButton {
                background-color: #3a4a6a; color: #c8d8ff;
                border: 1px solid #5a7aaa; border-radius: 6px;
                padding: 7px 16px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #4a5a7a; border-color: #7a9aca; }
            QPushButton:pressed { background-color: #5a6a8a; }
        """

        # ── 第一行：核心分析操作 ──
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        self.btn_analyze_recent = QPushButton("分析最近录音")
        self.btn_analyze_recent.setToolTip("自动加载最近一次录音并分析")
        self.btn_analyze_recent.setStyleSheet(_btn_primary_style)
        row1.addWidget(self.btn_analyze_recent)

        self.btn_analyze = QPushButton("选择分析")
        self.btn_analyze.setToolTip("选择已保存的分析 JSON 文件")
        self.btn_analyze.setStyleSheet(_btn_style)
        row1.addWidget(self.btn_analyze)

        self.btn_compare = QPushButton("对比分析")
        self.btn_compare.setToolTip("与专业歌手的音高曲线对比")
        self.btn_compare.setStyleSheet(_btn_style)
        row1.addWidget(self.btn_compare)

        row1.addSpacing(12)

        self.btn_settings = QPushButton("⚙ 设置")
        self.btn_settings.setToolTip("AI 教练设置 (API / 身份)")
        self.btn_settings.setStyleSheet(_btn_style + """
            QPushButton:hover { background-color: #3a3a5a; border-color: #7C5CFC; }
        """)
        row1.addWidget(self.btn_settings)

        layout.addLayout(row1)

        # ── 第二行：辅助工具 ──
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self.btn_plan = QPushButton("练习计划")
        self.btn_plan.setToolTip("生成个性化练习计划")
        self.btn_plan.setStyleSheet(_btn_style)
        row2.addWidget(self.btn_plan)

        self.btn_report = QPushButton("导出报告")
        self.btn_report.setToolTip("导出 Markdown 分析报告")
        self.btn_report.setStyleSheet(_btn_style)
        row2.addWidget(self.btn_report)

        self.btn_clear = QPushButton("清空对话")
        self.btn_clear.setToolTip("清空当前对话")
        self.btn_clear.setStyleSheet(_btn_style)
        row2.addWidget(self.btn_clear)

        row2.addStretch()
        layout.addLayout(row2)

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
        self.btn_mic = QPushButton("🎤")
        self.btn_mic.setFixedSize(36, 36)
        self.btn_mic.setToolTip("语音输入")
        self.btn_mic.setStyleSheet("""
            QPushButton {
                background-color: #2a2a4a;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                font-size: 16px;
            }
            QPushButton:hover { background-color: #3a3a5a; border-color: #4ADE80; }
            QPushButton:disabled { color: #555; }
        """)
        if not _VOICE_AVAILABLE:
            self.btn_mic.setEnabled(False)
            self.btn_mic.setToolTip("语音输入需要安装: pip install SpeechRecognition pyaudio")
        input_layout.addWidget(self.btn_mic)
        input_layout.addWidget(self.btn_send)
        layout.addLayout(input_layout)

        self.setMinimumSize(400, 500)

    def _connect_signals(self):
        self.btn_send.clicked.connect(self._on_send)
        self.input_field.returnPressed.connect(self._on_send)
        self.btn_mic.clicked.connect(self._on_voice_input)
        self.btn_analyze_recent.clicked.connect(self._on_analyze_recent)
        self.btn_analyze.clicked.connect(self._on_analyze)
        self.btn_compare.clicked.connect(self._on_compare)
        self.btn_plan.clicked.connect(self._on_plan)
        self.btn_report.clicked.connect(self._on_report)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_settings.clicked.connect(self._on_settings)
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

    def _on_voice_input(self):
        """语音输入按钮 —— 后台识别，完成后填入输入框"""
        if not _VOICE_AVAILABLE:
            return

        self.btn_mic.setEnabled(False)
        self.btn_mic.setText("🔴")
        self.btn_mic.setStyleSheet("""
            QPushButton {
                background-color: #4a2a2a;
                color: #F87171;
                border: 1px solid #F87171;
                border-radius: 4px;
                font-size: 16px;
            }
        """)

        self._voice_worker = _VoiceWorker()
        self._voice_worker.result.connect(self._on_voice_result)
        self._voice_worker.error.connect(self._on_voice_error)
        self._voice_worker.status.connect(self._on_voice_status)
        self._voice_worker.finished.connect(self._on_voice_done)
        self._voice_worker.start()

    def _on_voice_result(self, text: str):
        self.input_field.setText(text)
        self.input_field.setFocus()

    def _on_voice_error(self, msg: str):
        self._append_message("assistant", f"🎤 {msg}")

    def _on_voice_status(self, msg: str):
        self.btn_mic.setToolTip(msg)

    def _on_voice_done(self):
        self.btn_mic.setText("🎤")
        self.btn_mic.setEnabled(True)
        self.btn_mic.setToolTip("语音输入")
        self.btn_mic.setStyleSheet("""
            QPushButton {
                background-color: #2a2a4a;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                font-size: 16px;
            }
            QPushButton:hover { background-color: #3a3a5a; border-color: #4ADE80; }
        """)

    def _on_analyze_recent(self):
        """自动查找并分析最近一次录音的 JSON。"""
        try:
            recordings_dir = Path("recordings")
            if not recordings_dir.exists():
                self._append_message("assistant", "尚未找到录音目录。请先完成一次录音。")
                return

            candidates = []
            for p in sorted(recordings_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
                if p.name.startswith("._") or p.name.endswith("_temp.json"):
                    continue
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        head = f.read(512)
                    if '"pitch_analysis"' in head or '"recording_info"' in head:
                        candidates.append(p)
                except Exception:
                    continue
                if len(candidates) >= 10:  # 只扫描最近 10 个文件
                    break

            if not candidates:
                self._append_message(
                    "assistant",
                    "尚未找到录音分析文件。请先完成一次录音，或使用「选择分析」手动加载。"
                )
                return

            latest = max(candidates, key=lambda p: p.stat().st_mtime)
            song_name = latest.stem
            self._append_message("user", f"[分析最近录音] {song_name}")
            # 累计分析次数 +1
            try:
                self.agent.session_mgr.increment_analysis_count()
            except Exception:
                pass
            self._run_agent_task("analyze", json_path=str(latest), song_name=song_name)
        except Exception as e:
            self._append_message("assistant", f"❌ 分析失败: {str(e)}")

    def _on_analyze(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 MindEcho 分析文件", "",
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        song_name = Path(path).stem.replace("_analysis", "").replace("_", " ")
        self._append_message("user", f"[分析演唱] {song_name}")
        # 累计分析次数 +1
        try:
            self.agent.session_mgr.increment_analysis_count()
        except Exception:
            pass
        self._run_agent_task("analyze", json_path=path, song_name=song_name)

    def _on_compare(self):
        user_path, _ = QFileDialog.getOpenFileName(
            self, "选择你的演唱分析文件", "",
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not user_path:
            return
        ref_path, _ = QFileDialog.getOpenFileName(
            self, "选择专业参考分析文件", "",
            "JSON 文件 (*.json);;所有文件 (*)"
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
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        song_name = Path(path).stem.replace("_analysis", "").replace("_", " ")
        self._append_message("user", f"[生成报告] {song_name}")
        self._run_agent_task("report", json_path=str(path), song_name=song_name)

    def _on_clear(self):
        self.chat_display.clear()
        self.agent.session_mgr.clear_chat_history()

    def _on_settings(self):
        """打开 AI 教练设置对话框"""
        config = self.agent.app_config
        config_mgr = ConfigManager()
        dlg = CoachSettingsDialog(config, config_mgr, parent=self)
        if dlg.exec() == CoachSettingsDialog.DialogCode.Accepted:
            new_config = dlg.get_config()
            try:
                self.agent.reconfigure(new_config)
                self._append_message(
                    "assistant",
                    f"⚙ 设置已更新。现在由 **{new_config.identity.name}** 使用 "
                    f"**{new_config.llm.model}** 模型为你服务。"
                )
                # 通知外部（如 AICoachDockPanel）同步桌宠
                if callable(self.on_config_changed):
                    self.on_config_changed()
            except Exception as e:
                self._append_message("assistant", f"⚠ 配置已保存，但重新连接失败: {e}")

    def _on_thinking(self):
        self.thinking_bar.setVisible(True)

    def _on_stream_token(self, token: str):
        self._pending_tokens.append(token)
        # 首个 token 到达时启动定时刷新 (50ms 间隔，连续打字效果)
        if not self._stream_timer.isActive():
            self._stream_timer.start()

    def _on_response_done(self, response: str):
        self._stream_timer.stop()
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
        self._current_task_type = task_type  # 记录任务类型供结果处理用
        self.thinking_bar.setVisible(True)
        self._pending_tokens.clear()
        self._stream_timer.stop()

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
        # 分析/报告类任务：自动填充到报告标签页
        task = getattr(self, '_current_task_type', '')
        if task in ("analyze", "report"):
            self._last_analysis_result = result
            try:
                self.report_display.setMarkdown(result)
            except Exception:
                pass
        try:
            self._refresh_profile()
        except Exception:
            pass  # 图表刷新失败不影响主流程

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
        """刷新用户画像摘要 — 供外部（integration.py）调用显示"""
        self._refresh_charts()
        try:
            return self.agent.get_profile_summary()
        except Exception:
            return ""

    def _refresh_charts(self):
        """刷新练习数据可视化 — 3 张卡片同一行并排。

        QTextBrowser 基于 Qt Rich Text (HTML4 子集)，不支持:
          flexbox, gradient, text-shadow, pseudo-elements, CSS variables, animation.
        因此使用 <table> 布局 + 纯色 + 简单边框。"""
        try:
            stats = self.agent.session_mgr.get_stats()
            total = stats["total_sessions"]
            total_analyses = stats.get("total_analyses", 0)
            total_minutes = stats.get("total_minutes", 0.0) or stats["total_hours"] * 60

            # ── 时长格式化 ──
            if total_minutes >= 60:
                h = int(total_minutes // 60)
                m = int(total_minutes % 60)
                time_big = f"{h}"
                time_unit = "h"
                time_sub = f"{m}min"
            elif total_minutes >= 1:
                time_big = f"{int(total_minutes)}"
                time_unit = "min"
                time_sub = ""
            else:
                time_big = "—"
                time_unit = ""
                time_sub = ""

            # ── 状态描述 ──
            if total == 0:
                desc = "还没有练习记录，点击录音按钮开始第一次练习吧！"
            elif total < 5:
                desc = f"刚起步，已完成 {total} 次练习。坚持下去，每一遍都在进步！"
            else:
                h = int(total_minutes // 60) if total_minutes >= 60 else 0
                m = int(total_minutes % 60)
                if h > 0:
                    time_str = f"{h}小时{m}分钟"
                else:
                    time_str = f"{m}分钟"
                desc = f"共 {total} 次练习，累计 {time_str}。继续加油，每一遍都在进步！"

            # 时长标签: 数字+单位在一行
            duration_label = f"练习时长 {time_sub}" if time_sub else "练习时长"

            # ── Qt Rich Text 兼容的 3 卡片布局 ──
            # 用 <table> 保证同一行、等宽
            html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/><style>
  body {{
    margin:0; padding:18px 16px;
    background:#1a1a2e;
    font-family:"Microsoft YaHei","Segoe UI",sans-serif;
  }}
  .title {{
    font-size:14px; font-weight:bold; color:#C4B5FD;
    margin-bottom:4px;
  }}
  .subtitle {{
    font-size:10px; color:#6B7280;
    margin-bottom:16px;
  }}
  table.cards {{
    width:100%;
    border-collapse:separate;
    border-spacing:12px;
    margin-bottom:14px;
  }}
  td.card {{
    width:33%;
    background:#1E1E3A;
    border:1.5px solid #2D2D5A;
    border-radius:6px;
    padding:18px 8px 14px 8px;
    text-align:center;
  }}
  .num {{
    font-size:34px; font-weight:900;
    line-height:1.15;
  }}
  .num.c-purple {{ color:#A78BFA; }}
  .num.c-blue   {{ color:#60A5FA; }}
  .num.c-green  {{ color:#4ADE80; }}
  .unit {{
    font-size:16px; font-weight:600;
  }}
  .c-purple .unit {{ color:#A78BFA; }}
  .c-blue   .unit {{ color:#60A5FA; }}
  .c-green  .unit {{ color:#4ADE80; }}
  .label {{
    font-size:13px; font-weight:bold; color:#D1D5DB;
    margin-top:6px;
  }}
  .sub {{
    font-size:10px; color:#9CA3AF;
    margin-top:2px;
  }}
  .desc {{
    font-size:12px; color:#9CA3AF;
    line-height:1.6;
    border-left:2px solid #7C5CFC;
    padding:4px 0 4px 12px;
  }}
</style></head><body>

<div class="title">📊 练习数据总览</div>
<div class="subtitle">数据实时更新</div>

<table class="cards"><tr>
  <td class="card">
    <div class="num c-purple">{total}</div>
    <div class="label">练习次数</div>
    <div class="sub">PRACTICE SESSIONS</div>
  </td>
  <td class="card">
    <div class="num c-blue">{total_analyses}</div>
    <div class="label">AI 分析</div>
    <div class="sub">ANALYSIS REPORTS</div>
  </td>
  <td class="card">
    <div class="num c-green">{time_big}<span class="unit"> {time_unit}</span></div>
    <div class="label">{duration_label}</div>
    <div class="sub">PRACTICE DURATION</div>
  </td>
</tr></table>

<div class="desc">{desc}</div>
</body></html>'''

            self.chart_display.setHtml(html)

        except Exception:
            pass  # 图表失败不影响主功能
