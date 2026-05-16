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

        self.profile: UserProfile = self._load_profile()
        self.sessions: list[PracticeSession] = []
        self._chat_history: list[dict[str, str]] = []

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

    def save_profile(self):
        data = {k: v for k, v in self.profile.__dict__.items()}
        self._profile_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
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

    def recent_sessions(self, n: int = 5) -> list[PracticeSession]:
        return self.sessions[-n:] if self.sessions else []

    # ── 对话记忆 ─────────────────────────────────────────────

    def add_message(self, role: str, content: str):
        self._chat_history.append({"role": role, "content": content})
        if len(self._chat_history) > self.MAX_HISTORY_TURNS * 2:
            self._chat_history = self._chat_history[-(self.MAX_HISTORY_TURNS * 2):]

    def get_chat_history(self, last_n: int = 10) -> list[dict[str, str]]:
        return self._chat_history[-last_n * 2:] if self._chat_history else []

    def clear_chat_history(self):
        self._chat_history.clear()

    # ── 统计 ─────────────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "level": self.profile.level,
            "total_sessions": self.profile.total_practice_sessions,
            "total_hours": round(self.profile.total_practice_time_minutes / 60, 1),
            "vocal_range": f"{self.profile.vocal_range_low:.0f}-{self.profile.vocal_range_high:.0f}Hz",
            "recent_accuracy_trend": self.get_progress_trend(),
            "completed_stages": self.profile.completed_stages,
            "focus_areas": self.profile.focus_areas,
        }
