"""AI 教练身份配置 —— 支持按安装实例定制教练形象"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# 可用的桌宠形象主题（角色 → 主题列表）
AVATAR_CHARACTERS = {
    "maimai": "麦麦",
    "tuantuan": "团团",
    "yinyin": "音音",
    "qiuqiu": "球球",
    "mianmian": "绵绵",
}

AVATAR_THEMES = {
    # 麦麦
    "classic": "麦麦·经典紫",
    "ocean": "麦麦·海洋蓝",
    "midnight": "麦麦·暗夜紫",
    "cherry": "麦麦·樱莓粉",
    # 团团
    "honey": "团团·蜂蜜棕",
    "caramel": "团团·焦糖橘",
    "matcha": "团团·抹茶绿",
    "cocoa": "团团·可可棕",
    # 音音
    "mint": "音音·薄荷绿",
    "sky": "音音·天蓝",
    "peach": "音音·蜜桃粉",
    "lavender": "音音·薰衣草",
    # 球球
    "sunset": "球球·暖橙",
    "bubblegum": "球球·泡泡糖",
    "seafoam": "球球·海沫绿",
    "starry": "球球·星辰紫",
    # 绵绵
    "sakura": "绵绵·樱花粉",
    "snow": "绵绵·雪白",
    "latte": "绵绵·奶茶棕",
    "haze": "绵绵·雾霾蓝",
}


@dataclass
class CoachIdentity:
    """AI 教练身份配置 —— 每个安装实例可独立定制"""

    name: str = "麦麦"
    display_name: str = "麦麦"
    personality: str = "温暖鼓励"
    avatar_theme: str = "classic"   # 形象主题标识（见 AVATAR_THEMES）
    accent_color: str = "#7C5CFC"
    greeting_template: str = (
        "嗨～我是{name}！\n"
        "平时可以陪你聊聊天、聊聊音乐，有什么唱歌上的问题也尽管问我。\n"
        "想分析录音的话录完点「分析演唱」就行，想对比专业歌手的版本也可以～"
    )

    def get_greeting(self) -> str:
        return self.greeting_template.format(name=self.name)


# 默认身份 —— 当用户未自定义时使用
DEFAULT_IDENTITY = CoachIdentity()

