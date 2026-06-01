"""会话管理器 —— 管理教学会话、对话历史和用户画像"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════


@dataclass
class UserProfile:
    """用户学习画像"""
    level: str = "beginner"                        # beginner/elementary/intermediate/advanced
    vocal_range_low: float = 0.0                   # 最低有效音高 (Hz)
    vocal_range_high: float = 0.0                  # 最高有效音高 (Hz)
    total_practice_sessions: int = 0
    total_practice_time_minutes: float = 0.0
    total_analyses: int = 0  # 累计 AI 分析次数
    recent_accuracy_history: list[float] = field(default_factory=list)  # 最近 10 次的音准命中率
    focus_areas: list[str] = field(default_factory=list)                # 当前需关注的领域
    completed_stages: list[str] = field(default_factory=list)           # 已完成的课程阶段
    created_at: str = ""
    last_active: str = ""

    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.last_active:
            self.last_active = now


@dataclass
class PracticeSession:
    """单次练习记录"""
    session_id: str
    timestamp: str
    duration_minutes: float
    song_name: str = ""
    accuracy: float = 0.0              # 音准命中率
    main_focus: str = ""               # 本课重点练习的内容
    notes: str = ""                    # AI 或用户的备注
    analysis_data_path: str = ""       # 关联的 MindEcho 分析 JSON 路径


# ═══════════════════════════════════════════════════════════════
# SessionManager
# ═══════════════════════════════════════════════════════════════


class SessionManager:
    """管理用户画像、练习历史和对话记忆"""

    MAX_HISTORY_TURNS = 20        # 保留最近 N 轮对话
    MAX_ACCURACY_HISTORY = 20     # 保留最近 N 次音准记录

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path.home() / ".mindecho" / "ai_coach"
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # 会话持久化目录
        self._sessions_dir = self._data_dir.parent / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

        self.profile: UserProfile = self._load_profile()
        self.sessions: list[PracticeSession] = self._load_practice_sessions()
        self._chat_history: list[dict[str, str]] = self._load_chat_history()

    # ── 用户画像 ─────────────────────────────────────────────

    def _profile_path(self) -> Path:
        return self._data_dir / "profile.json"

    def _load_profile(self) -> UserProfile:
        path = self._profile_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return UserProfile(**data)
            except Exception:
                pass
        return UserProfile()

    @staticmethod
    def _atomic_write(file_path: Path, text: str):
        """原子写入：先写临时文件再 rename，避免写入中途崩溃导致文件损坏。"""
        tmp = file_path.with_suffix(file_path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(file_path)

    def save_profile(self):
        data = {k: v for k, v in self.profile.__dict__.items()}
        self._atomic_write(
            self._profile_path(),
            json.dumps(data, ensure_ascii=False, indent=2),
        )

    def update_profile(
        self,
        *,
        level: Optional[str] = None,
        vocal_range: Optional[tuple[float, float]] = None,
        focus_areas: Optional[list[str]] = None,
    ):
        if level:
            self.profile.level = level
        if vocal_range:
            self.profile.vocal_range_low = vocal_range[0]
            self.profile.vocal_range_high = vocal_range[1]
        if focus_areas is not None:
            self.profile.focus_areas = focus_areas
        self.profile.last_active = datetime.now().isoformat()
        self.save_profile()

    def increment_analysis_count(self):
        """AI 分析次数 +1"""
        self.profile.total_analyses += 1
        self.profile.last_active = datetime.now().isoformat()
        self.save_profile()

    def record_accuracy(self, accuracy: float):
        self.profile.recent_accuracy_history.append(accuracy)
        if len(self.profile.recent_accuracy_history) > self.MAX_ACCURACY_HISTORY:
            self.profile.recent_accuracy_history = self.profile.recent_accuracy_history[
                -self.MAX_ACCURACY_HISTORY:
            ]

    def get_progress_trend(self) -> str:
        """返回音准进步趋势描述"""
        hist = self.profile.recent_accuracy_history
        if len(hist) < 3:
            return "数据不足，继续录音积累更多数据"
        recent = hist[-5:]
        older = hist[:-5] if len(hist) > 5 else hist[:len(hist)//2]
        if not older:
            return "数据不足，继续录音积累更多数据"
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        diff = (recent_avg - older_avg) * 100
        if diff > 5:
            return f"显著进步 (+{diff:.0f}%)！继续保持当前的练习方法。"
        elif diff > 1:
            return f"平稳进步 (+{diff:.0f}%)，方向正确。"
        elif diff > -1:
            return "音准水平基本稳定，可能需要新的练习挑战来突破瓶颈。"
        else:
            return f"近期音准有所下滑 ({diff:.0f}%)，建议回顾基础呼吸和共鸣练习。"

    # ── 练习会话 ─────────────────────────────────────────────

    def start_session(self, focus: str = "", song_name: str = "") -> str:
        """开始一个新练习会话，返回 session_id"""
        sid = uuid.uuid4().hex[:12]
        session = PracticeSession(
            session_id=sid,
            timestamp=datetime.now().isoformat(),
            duration_minutes=0,
            song_name=song_name,
            main_focus=focus,
        )
        self.sessions.append(session)
        self.profile.total_practice_sessions += 1
        self.save_profile()
        self._save_practice_sessions()
        return sid

    def end_session(self, session_id: str, duration_minutes: float,
                    accuracy: float = 0.0, notes: str = "",
                    analysis_data_path: str = ""):
        """结束练习会话"""
        for s in self.sessions:
            if s.session_id == session_id:
                s.duration_minutes = duration_minutes
                s.accuracy = accuracy
                s.notes = notes
                s.analysis_data_path = analysis_data_path
                break
        self.profile.total_practice_time_minutes += duration_minutes
        if accuracy > 0:
            self.record_accuracy(accuracy)
        self.save_profile()
        self._save_practice_sessions()

    def recent_sessions(self, n: int = 5) -> list[PracticeSession]:
        return self.sessions[-n:] if self.sessions else []

    # ── 对话记忆 ─────────────────────────────────────────────

    def add_message(self, role: str, content: str):
        self._chat_history.append({"role": role, "content": content})
        if len(self._chat_history) > self.MAX_HISTORY_TURNS * 2:
            self._chat_history = self._chat_history[-(self.MAX_HISTORY_TURNS * 2):]
        self._save_chat_history()

    def get_chat_history(self, last_n: int = 10) -> list[dict[str, str]]:
        return self._chat_history[-last_n * 2:] if self._chat_history else []

    def clear_chat_history(self):
        self._chat_history.clear()
        self._save_chat_history()

    # ── 持久化：聊天历史 ──────────────────────────────────────

    def _chat_history_path(self) -> Path:
        return self._sessions_dir / "chat_history.json"

    def _save_chat_history(self):
        try:
            self._atomic_write(
                self._chat_history_path(),
                json.dumps(self._chat_history, ensure_ascii=False, indent=2),
            )
        except Exception:
            pass

    def _load_chat_history(self) -> list[dict[str, str]]:
        path = self._chat_history_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
        return []

    # ── 持久化：练习会话 ──────────────────────────────────────

    def _sessions_path(self) -> Path:
        return self._sessions_dir / "practice_log.json"

    def _save_practice_sessions(self):
        try:
            data = [
                {
                    "session_id": s.session_id,
                    "timestamp": s.timestamp,
                    "duration_minutes": s.duration_minutes,
                    "song_name": s.song_name,
                    "accuracy": s.accuracy,
                    "main_focus": s.main_focus,
                    "notes": s.notes,
                    "analysis_data_path": s.analysis_data_path,
                }
                for s in self.sessions
            ]
            self._atomic_write(
                self._sessions_path(),
                json.dumps(data, ensure_ascii=False, indent=2),
            )
        except Exception:
            pass

    def _load_practice_sessions(self) -> list[PracticeSession]:
        path = self._sessions_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [PracticeSession(**item) for item in data]
            except Exception:
                pass
        return []

    # ── 统计 ─────────────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "level": self.profile.level,
            "total_sessions": self.profile.total_practice_sessions,
            "total_analyses": self.profile.total_analyses,
            "total_hours": round(self.profile.total_practice_time_minutes / 60, 1),
            "total_minutes": round(self.profile.total_practice_time_minutes, 1),
            "vocal_range": f"{self.profile.vocal_range_low:.0f}-{self.profile.vocal_range_high:.0f}Hz",
            "recent_accuracy_trend": self.get_progress_trend(),
            "completed_stages": self.profile.completed_stages,
            "focus_areas": self.profile.focus_areas,
        }

    def format_practice_context(self) -> str:
        """将用户练习数据格式化为 LLM 上下文，注入 system prompt。

        只注入有实际数据的内容，避免空泛的模板字段。
        """
        s = self.get_stats()
        parts = []

        if s["total_sessions"] > 0:
            parts.append(f"- 累计练习 {s['total_sessions']} 次 ({s['total_hours']} 小时)")

        if s["vocal_range"] not in ("0-0Hz", "0.0-0.0Hz", "-Hz"):
            parts.append(f"- 当前音域 {s['vocal_range']}")

        if s["level"] and s["level"] != "beginner":
            parts.append(f"- 学习阶段: {s['level']}")

        if s["completed_stages"]:
            parts.append(f"- 已完成阶段: {', '.join(s['completed_stages'])}")

        if s["focus_areas"]:
            parts.append(f"- 需重点关注: {', '.join(s['focus_areas'])}")

        trend = s["recent_accuracy_trend"]
        if trend and "数据不足" not in trend:
            parts.append(f"- 近期趋势: {trend}")

        # 最近的练习记录
        recent = [s for s in self.sessions[-5:] if s.song_name]
        if recent:
            songs = [s.song_name for s in recent]
            accs = [f"{s.accuracy*100:.0f}%" if s.accuracy else "N/A" for s in recent]
            parts.append(f"- 最近练习曲目: {', '.join(f'{s}({a})' for s, a in zip(songs, accs))}")

        if not parts:
            return ""

        return "## 用户练习数据\n" + "\n".join(parts)
