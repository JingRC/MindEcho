"""GUI 模块 __init__"""
from .coach_panel import AICoachPanel
from .mascot_svg import get_svg, get_all_expressions, MASCOT_ANIMATION_CSS
from .integration import (
    MascotWidget, AICoachDockPanel, integrate_ai_coach, run_standalone,
)

__all__ = [
    "AICoachPanel",
    "MascotWidget",
    "AICoachDockPanel",
    "integrate_ai_coach",
    "run_standalone",
    "get_svg",
    "get_all_expressions",
    "MASCOT_ANIMATION_CSS",
]
