"""分析报告生成器 —— 生成 Markdown/HTML 格式的声乐分析报告"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from ..context.builder import SingingContext, ContextBuilder
from ..session.manager import SessionManager


class ReportGenerator:
    """生成歌唱分析报告（Markdown 格式，可导出为 PDF）"""

    def __init__(
        self,
        context_builder: Optional[ContextBuilder] = None,
        session_manager: Optional[SessionManager] = None,
    ):
        self.ctx_builder = context_builder or ContextBuilder()
        self.session_mgr = session_manager

    def generate_analysis_report(
        self,
        ctx: SingingContext,
        *,
        song_name: str = "未命名",
        user_name: str = "歌手",
        ai_feedback: str = "",
    ) -> str:
        """生成单次演唱分析报告 Markdown"""
        s = ctx.stats
        t = ctx.techniques

        lines = [
            f"# MindEcho 演唱分析报告",
            f"**歌曲**: {song_name}",
            f"**演唱者**: {user_name}",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "---",
            "",
            "## 一、整体评估",
            "",
        ]

        # 等级判定
        if s and s.pitch_accuracy > 0.9:
            grade = "优秀 (A)"
        elif s and s.pitch_accuracy > 0.75:
            grade = "良好 (B)"
        elif s and s.pitch_accuracy > 0.6:
            grade = "一般 (C)"
        else:
            grade = "需加强 (D)"

        lines.append(f"**综合评级**: {grade}")
        lines.append("")

        # 音准统计
        if s:
            lines.append("## 二、音准分析")
            lines.append("")
            lines.append("| 指标 | 数值 | 说明 |")
            lines.append("|------|------|------|")
            lines.append(f"| 音准命中率 | {s.pitch_accuracy:.0%} | ±50音分内算命中 |")
            lines.append(f"| 平均音分偏差 | {s.mean_cent_deviation:.0f} 音分 | 越小越好 |")
            lines.append(f"| 稳定性 | {s.std_cent_deviation:.0f} 音分 | 标准差，越小越稳定 |")
            lines.append(f"| 偏高比例 | {s.sharp_ratio:.0%} | 接近 50% 最理想 |")
            lines.append(f"| 有效音域 | {s.min_freq:.0f} - {s.max_freq:.0f} Hz | |")
            lines.append(f"| 检测置信度 | {s.mean_confidence:.0%} | >70% 为可靠 |")
            lines.append("")

        # 技巧检测
        if t:
            lines.append("## 三、技巧使用")
            lines.append("")
            if t.vibrato_count > 0:
                lines.append(f"- **颤音**: 检测到 {t.vibrato_count} 次，平均速率 {t.vibrato_avg_rate:.1f} Hz，平均深度 {t.vibrato_avg_depth:.0f} 音分")
            else:
                lines.append(f"- **颤音**: 未检测到")
            lines.append(f"- **滑音**: {t.slide_count} 次")
            lines.append(f"- **换气**: {t.breath_count} 次")
            lines.append(f"- **声区切换**: {t.register_transition_count} 次")
            if t.voice_type_distribution:
                vtd = t.voice_type_distribution
                lines.append(f"- **声音类型分布**: " + ", ".join(f"{k}: {v:.0%}" for k, v in vtd.items()))
            lines.append("")

        # 问题段落
        if ctx.segments:
            problem_segs = [seg for seg in ctx.segments if seg.accuracy < 0.7]
            if problem_segs:
                lines.append("## 四、需重点关注的段落")
                lines.append("")
                for seg in problem_segs:
                    lines.append(f"- **{seg.label}** ({seg.start_time:.1f}s-{seg.end_time:.1f}s): 准确度 {seg.accuracy:.0%}")
                    for issue in seg.issues:
                        lines.append(f"  - {issue}")
                lines.append("")

        # AI 反馈
        if ai_feedback:
            lines.append("## 五、AI 教练建议")
            lines.append("")
            lines.append(ai_feedback)
            lines.append("")

        # 进步曲线
        if self.session_mgr:
            lines.append("## 六、学习进度")
            lines.append("")
            trend = self.session_mgr.get_progress_trend()
            lines.append(f"- {trend}")
            stats = self.session_mgr.get_stats()
            lines.append(f"- 累计练习: {stats['total_sessions']} 次，共 {stats['total_hours']} 小时")
            lines.append(f"- 当前阶段: {stats['level']}")
            lines.append("")

        lines.extend([
            "---",
            f"*报告由 MindEcho AI 声乐教练自动生成*",
        ])

        return "\n".join(lines)

    def generate_comparison_report(
        self,
        user_ctx: SingingContext,
        *,
        song_name: str = "未命名",
        user_name: str = "你",
        reference_name: str = "专业歌手",
        ai_feedback: str = "",
    ) -> str:
        """生成对比分析报告 Markdown"""
        comp = user_ctx.comparison

        lines = [
            f"# MindEcho 对比分析报告",
            f"**歌曲**: {song_name}",
            f"**对比**: {user_name} vs {reference_name}",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "---",
            "",
        ]

        if comp:
            lines.append("## 一、综合对比")
            lines.append("")
            lines.append(f"- 综合音准差距: **{comp.overall_accuracy_gap:.0f} 音分**")
            lines.append(f"- 对齐数据点: {comp.dtw_aligned_points}")
            if comp.best_segment:
                lines.append(f"- 表现最佳: {comp.best_segment}")
            if comp.worst_segment:
                lines.append(f"- 最需改进: {comp.worst_segment}")
            lines.append("")

            if comp.strengths:
                lines.append("## 二、你的优势")
                lines.append("")
                for s in comp.strengths:
                    lines.append(f"- {s}")
                lines.append("")

            if comp.weaknesses:
                lines.append("## 三、需要改进")
                lines.append("")
                for w in comp.weaknesses:
                    lines.append(f"- {w}")
                lines.append("")

            if comp.technique_comparison:
                lines.append("## 四、技巧使用对比")
                lines.append("")
                lines.append("| 技巧 | 你的表现 | 参考歌手 |")
                lines.append("|------|----------|----------|")
                for tech, vals in comp.technique_comparison.items():
                    lines.append(f"| {tech} | {vals.get('user', 'N/A')} | {vals.get('ref', 'N/A')} |")
                lines.append("")

        if ai_feedback:
            lines.append("## 五、AI 教练分析与建议")
            lines.append("")
            lines.append(ai_feedback)
            lines.append("")

        lines.extend([
            "---",
            f"*报告由 MindEcho AI 声乐教练自动生成*",
        ])

        return "\n".join(lines)

    def save_report(self, content: str, path: str | Path):
        Path(path).write_text(content, encoding="utf-8")
