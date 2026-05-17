# MindEcho AI 声乐教练模块
# 提供基于 LLM 的智能歌唱教学、分析报告生成和知识库检索功能

from .agent import VocalCoachAgent
from .config import AppConfig, ConfigManager, LLMProviderConfig
from .identity import CoachIdentity
from .llm_client import LLMClient, LLMConfig, DeepSeekConfig
from .memory import MemoryManager, MemoryEntry
from .session.manager import SessionManager

__all__ = [
    "VocalCoachAgent",
    "LLMClient", "LLMConfig", "DeepSeekConfig",
    "AppConfig", "ConfigManager", "LLMProviderConfig",
    "CoachIdentity",
    "MemoryManager", "MemoryEntry",
    "SessionManager",
]
