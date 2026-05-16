"""上下文构建器 __init__"""
from .builder import (
    ContextBuilder, SingingContext, PitchStats,
    TechniqueSummary, SegmentAnalysis, ComparisonResult,
)
from .templates import (
    SYSTEM_PROMPT,
    build_analysis_prompt, build_comparison_prompt,
    build_qa_prompt, build_practice_plan_prompt,
)

__all__ = [
    "ContextBuilder", "SingingContext", "PitchStats",
    "TechniqueSummary", "SegmentAnalysis", "ComparisonResult",
    "SYSTEM_PROMPT",
    "build_analysis_prompt", "build_comparison_prompt",
    "build_qa_prompt", "build_practice_plan_prompt",
]
