"""AI 声乐教练 Agent —— 主编排器

协调 LLM 调用、知识检索、上下文构建、会话管理和报告生成。
通过信号/回调机制与 GUI 解耦。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from .context.builder import (
    ContextBuilder, SingingContext, PitchStats, TechniqueSummary, ComparisonResult,
)
from .context.templates import (
    SYSTEM_PROMPT,
    build_analysis_prompt, build_comparison_prompt,
    build_qa_prompt, build_practice_plan_prompt,
)
from .knowledge.retriever import KnowledgeRetriever, get_knowledge_store
from .knowledge.store import KnowledgeStore
from .llm_client import LLMClient, DeepSeekConfig
from .session.manager import SessionManager
from .analysis.comparer import PitchComparer
from .analysis.reporter import ReportGenerator


# ═══════════════════════════════════════════════════════════════
# Agent 主类
# ═══════════════════════════════════════════════════════════════


class VocalCoachAgent:
    """MindEcho AI 声乐教练 —— 集成 LLM + 知识库 + 音高分析的教学 Agent"""

    def __init__(
        self,
        *,
        llm_config: Optional[DeepSeekConfig] = None,
        session_dir: Optional[Path] = None,
        knowledge_dir: Optional[Path] = None,
        on_thinking: Optional[Callable[[], None]] = None,
        on_response: Optional[Callable[[str], None]] = None,
        on_stream_token: Optional[Callable[[str], None]] = None,
    ):
        # 核心组件
        self.llm = LLMClient(llm_config)
        self.knowledge_retriever = KnowledgeRetriever(
            KnowledgeStore(knowledge_dir) if knowledge_dir else None
        )
        self.session_mgr = SessionManager(session_dir)
        self.ctx_builder = ContextBuilder()
        self.comparer = PitchComparer()
        self.reporter = ReportGenerator(self.ctx_builder, self.session_mgr)

        # 最新演唱数据
        self._last_singing_ctx: Optional[SingingContext] = None

        # 回调
        self._on_thinking = on_thinking
        self._on_response = on_response
        self._on_stream = on_stream_token

    # ── 主要交互入口 ─────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        *,
        singing_context: Optional[SingingContext] = None,
        with_knowledge: bool = True,
        with_curriculum: bool = False,
    ) -> str:
        """自由对话 —— 用户提问，Agent 结合知识库和演唱数据回答。

        Args:
            user_message: 用户消息
            singing_context: 如果有最近的演唱数据，传入以提供个性化反馈
            with_knowledge: 是否检索知识库
            with_curriculum: 是否附带课程上下文
        """
        ctx = singing_context or self._last_singing_ctx

        # 知识检索
        knowledge_text = ""
        if with_knowledge:
            knowledge_text = self.knowledge_retriever.retrieve_for_prompt(user_message, top_k=3)

        # 演唱数据上下文
        singing_text = ""
        if ctx:
            singing_text = self.ctx_builder.build_full_context(ctx, "l2")

        # 课程上下文
        curriculum_text = ""
        if with_curriculum:
            level = self.session_mgr.profile.level
            curriculum_text = self.knowledge_retriever.get_curriculum_context(level)

        # 构建 prompt
        task_prompt = build_qa_prompt(knowledge_text, singing_text)
        if curriculum_text:
            task_prompt += f"\n\n{curriculum_text}"

        # 对话历史
        history = self.session_mgr.get_chat_history(6)
        messages = history + [{"role": "user", "content": user_message}]

        # 调用 LLM
        if self._on_thinking:
            self._on_thinking()

        response = self.llm.chat(
            messages,
            system=SYSTEM_PROMPT + "\n" + task_prompt,
            on_stream=self._on_stream,
        )

        # 保存对话
        self.session_mgr.add_message("user", user_message)
        self.session_mgr.add_message("assistant", response)

        if self._on_response:
            self._on_response(response)

        return response

    def analyze_performance(
        self,
        analysis_json_path: Optional[str | Path] = None,
        *,
        singing_context: Optional[SingingContext] = None,
        song_name: str = "",
    ) -> str:
        """演唱后分析 —— 对刚完成的演唱给出详细反馈。

        Args:
            analysis_json_path: MindEcho 分析 JSON 文件路径
            singing_context: 或直接传入已构建的 SingingContext
            song_name: 歌曲名称
        """
        # 构建上下文
        if singing_context:
            ctx = singing_context
        elif analysis_json_path:
            ctx = self.ctx_builder.from_analysis_json(analysis_json_path)
        else:
            ctx = self._last_singing_ctx

        if ctx is None:
            return "请先提供演唱分析数据。"

        self._last_singing_ctx = ctx
        singing_text = self.ctx_builder.build_full_context(ctx, "l2")

        # 保存 session 记录
        if ctx.stats:
            sid = self.session_mgr.start_session(
                focus="演唱分析", song_name=song_name
            )
            self.session_mgr.end_session(
                sid,
                duration_minutes=0,  # 可以在 GUI 层传入实际时长
                accuracy=ctx.stats.pitch_accuracy,
                analysis_data_path=str(analysis_json_path or ""),
            )

        # 调用 LLM
        task_prompt = build_analysis_prompt(singing_text)
        if self._on_thinking:
            self._on_thinking()

        response = self.llm.chat(
            [{"role": "user", "content": f"请分析我刚刚演唱的{song_name}。"}],
            system=SYSTEM_PROMPT + "\n" + task_prompt,
            on_stream=self._on_stream,
        )

        self.session_mgr.add_message("user", f"分析我的演唱: {song_name}")
        self.session_mgr.add_message("assistant", response)

        if self._on_response:
            self._on_response(response)

        return response

    def compare_with_reference(
        self,
        user_json: str | Path,
        ref_json: str | Path,
        *,
        song_name: str = "",
        reference_name: str = "专业歌手",
    ) -> str:
        """与专业歌手对比分析。

        Args:
            user_json: 用户演唱的 MindEcho 分析 JSON
            ref_json: 参考歌手的分析 JSON
            song_name: 歌曲名称
            reference_name: 参考歌手名称
        """
        # DTW 对比
        comp_result = self.comparer.compare(
            user_json, ref_json,
            reference_name=reference_name,
        )

        # 构建上下文
        user_ctx = self.ctx_builder.from_analysis_json(user_json)
        user_ctx.comparison = comp_result
        self._last_singing_ctx = user_ctx

        singing_text = self.ctx_builder.build_full_context(user_ctx, "l3")

        # 调用 LLM
        task_prompt = build_comparison_prompt(
            singing_text, song_name, reference_name,
        )
        if self._on_thinking:
            self._on_thinking()

        response = self.llm.chat(
            [{"role": "user", "content": f"我唱了{song_name}，请和专业歌手{reference_name}的版本对比分析。"}],
            system=SYSTEM_PROMPT + "\n" + task_prompt,
            on_stream=self._on_stream,
        )

        self.session_mgr.add_message("user", f"对比分析: {song_name} vs {reference_name}")
        self.session_mgr.add_message("assistant", response)

        if self._on_response:
            self._on_response(response)

        return response

    def generate_practice_plan(
        self,
        *,
        user_goal: str = "全面提升歌唱能力",
        singing_context: Optional[SingingContext] = None,
    ) -> str:
        """生成个性化练习计划"""
        ctx = singing_context or self._last_singing_ctx
        level = self.session_mgr.profile.level

        singing_text = ""
        if ctx:
            singing_text = self.ctx_builder.build_full_context(ctx, "l1")

        curriculum_text = self.knowledge_retriever.get_curriculum_context(level)

        task_prompt = build_practice_plan_prompt(
            curriculum_text, singing_text, user_goal,
        )
        if self._on_thinking:
            self._on_thinking()

        response = self.llm.chat(
            [{"role": "user", "content": f"请根据我的当前水平（{level}），制定一个练习计划。我的目标是：{user_goal}"}],
            system=SYSTEM_PROMPT + "\n" + task_prompt,
            on_stream=self._on_stream,
        )

        self.session_mgr.add_message("user", "请帮我制定练习计划")
        self.session_mgr.add_message("assistant", response)

        if self._on_response:
            self._on_response(response)

        return response

    def generate_report(
        self,
        analysis_json_path: Optional[str | Path] = None,
        *,
        song_name: str = "",
        user_name: str = "歌手",
    ) -> str:
        """生成 Markdown 格式的分析报告"""
        ctx = None
        if analysis_json_path:
            ctx = self.ctx_builder.from_analysis_json(analysis_json_path)
        elif self._last_singing_ctx:
            ctx = self._last_singing_ctx

        if ctx is None:
            return ""

        # 如果需要 AI 反馈，先调用一次分析
        ai_feedback = ""
        try:
            singing_text = self.ctx_builder.build_full_context(ctx, "l2")
            task_prompt = build_analysis_prompt(singing_text)
            ai_feedback = self.llm.chat(
                [{"role": "user", "content": "请简要分析（200字内）"}],
                system=SYSTEM_PROMPT + "\n" + task_prompt,
                max_tokens=500,
            )
        except Exception:
            pass

        return self.reporter.generate_analysis_report(
            ctx, song_name=song_name, user_name=user_name, ai_feedback=ai_feedback,
        )

    def generate_comparison_report(
        self,
        user_json: str | Path,
        ref_json: str | Path,
        *,
        song_name: str = "",
        user_name: str = "你",
        reference_name: str = "专业歌手",
    ) -> str:
        """生成 Markdown 格式的对比分析报告"""
        user_ctx = self.ctx_builder.from_analysis_json(user_json)
        comp_result = self.comparer.compare(user_json, ref_json, reference_name=reference_name)
        user_ctx.comparison = comp_result

        ai_feedback = ""
        try:
            singing_text = self.ctx_builder.build_full_context(user_ctx, "l3")
            task_prompt = build_comparison_prompt(singing_text, song_name, reference_name)
            ai_feedback = self.llm.chat(
                [{"role": "user", "content": "请简要分析（200字内）"}],
                system=SYSTEM_PROMPT + "\n" + task_prompt,
                max_tokens=500,
            )
        except Exception:
            pass

        return self.reporter.generate_comparison_report(
            user_ctx, song_name=song_name, user_name=user_name,
            reference_name=reference_name, ai_feedback=ai_feedback,
        )

    # ── 便捷方法 ─────────────────────────────────────────────

    def set_singing_context(self, ctx: SingingContext):
        """设置当前演唱上下文（供 GUI 传入实时数据）"""
        self._last_singing_ctx = ctx

    def load_analysis_file(self, path: str | Path) -> SingingContext:
        """加载 MindEcho 分析 JSON 并设为当前上下文"""
        ctx = self.ctx_builder.from_analysis_json(path)
        self._last_singing_ctx = ctx
        return ctx

    def get_profile_summary(self) -> str:
        """获取用户画像摘要"""
        stats = self.session_mgr.get_stats()
        lines = [
            f"学习阶段: {stats['level']}",
            f"累计练习: {stats['total_sessions']} 次, {stats['total_hours']} 小时",
            f"音域: {stats['vocal_range']}",
            f"趋势: {stats['recent_accuracy_trend']}",
        ]
        if stats["focus_areas"]:
            lines.append(f"重点关注: {', '.join(stats['focus_areas'])}")
        return "\n".join(lines)

    @property
    def knowledge_stats(self) -> dict:
        return self.knowledge_retriever.store_stats
