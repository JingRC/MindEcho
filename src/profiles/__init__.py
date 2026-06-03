# MindEcho 用户存档模块
# SingerProfile: 歌手个性化存档，包含声部、换声点、音域统计、音色指纹等

from src.profiles.profile_model import (
    SingerProfile,
    PitchStats,
    PassaggioData,
    TimbreFingerprint,
    UsageStats,
    PROFILE_VERSION,
)
from src.profiles.profile_manager import ProfileManager

__all__ = [
    'SingerProfile',
    'PitchStats',
    'PassaggioData',
    'TimbreFingerprint',
    'UsageStats',
    'ProfileManager',
    'PROFILE_VERSION',
]
