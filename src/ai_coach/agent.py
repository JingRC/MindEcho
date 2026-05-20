"""AI 声乐教练 Agent —— 主编排器

协调 LLM 调用、知识检索、上下文构建、会话管理、记忆系统和报告生成。
通过信号/回调机制与 GUI 解耦。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Optional

from .config import AppConfig, ConfigManager, LLMProviderConfig
from .identity import CoachIdentity, DEFAULT_IDENTITY
from .memory import MemoryManager, MemoryEntry
from .context.builder import (
    ContextBuilder, SingingContext, PitchStats, TechniqueSummary, ComparisonResult,
)
from .context.templates import (
    build_system_prompt,
    build_analysis_prompt, build_comparison_prompt,
    build_qa_prompt, build_practice_plan_prompt,
    detect_intent, detect_search_intent,
)
from .search import WebSearchProvider, get_search_provider
from .knowledge.retriever import KnowledgeRetriever, get_knowledge_store
from .knowledge.store import KnowledgeStore
from .llm_client import LLMClient, LLMConfig
from .session.manager import SessionManager
from .analysis.comparer import PitchComparer
from .analysis.reporter import ReportGenerator
from .tools import TOOL_DEFINITIONS, ToolExecutor


# ═══════════════════════════════════════════════════════════════
# Agent 主类
# ═══════════════════════════════════════════════════════════════


class VocalCoachAgent:
    """MindEcho AI 声乐教练 —— 集成 LLM + 知识库 + 记忆 + 音高分析的教学 Agent"""

    def __init__(
        self,
        *,
        app_config: Optional[AppConfig] = None,
        identity: Optional[CoachIdentity] = None,
        llm_config: Optional[LLMConfig] = None,
        session_dir: Optional[Path] = None,
        knowledge_dir: Optional[Path] = None,
        memory_dir: Optional[Path] = None,
        on_thinking: Optional[Callable[[], None]] = None,
        on_response: Optional[Callable[[str], None]] = None,
        on_stream_token: Optional[Callable[[str], None]] = None,
    ):
        # —— 配置 ——
        self._config_mgr = ConfigManager()
        if app_config is not None:
            self._app_config = app_config
        else:
            self._app_config = self._config_mgr.load()

        self._identity = identity or self._app_config.identity

        # —— 核心组件 ——
        # LLM 客户端：优先使用传入的 llm_config，否则从 app_config 构建
        if llm_config is not None:
            self.llm = LLMClient(llm_config)
        else:
            self.llm = LLMClient(LLMConfig.from_app_config(self._app_config))

        self.knowledge_retriever = KnowledgeRetriever(
            KnowledgeStore(knowledge_dir) if knowledge_dir else None
        )
        self.session_mgr = SessionManager(session_dir)
        self.ctx_builder = ContextBuilder()
        self.comparer = PitchComparer()
        self.reporter = ReportGenerator(self.ctx_builder, self.session_mgr)

        # —— 记忆系统 ——
        self.memory = MemoryManager(memory_dir)

        # —— 联网搜索 ——
        self._search_provider: Optional[WebSearchProvider] = None

        # —— 工具调用 ——
        self._tools_enabled = True
        self._tool_executor = ToolExecutor(self)

        # —— 最新演唱数据 ——
        self._last_singing_ctx: Optional[SingingContext] = None

        # —— 回调 ——
        self._on_thinking = on_thinking
        self._on_response = on_response
        self._on_stream = on_stream_token

    # ── 配置 API ─────────────────────────────────────────────

    @property
    def identity(self) -> CoachIdentity:
        return self._identity

    @property
    def app_config(self) -> AppConfig:
        return self._app_config

    def reconfigure(self, app_config: AppConfig):
        """运行时重新配置（API 密钥、模型、身份等变更后调用）"""
        self._app_config = app_config
        self._identity = app_config.identity
        new_llm_config = LLMConfig.from_app_config(app_config)
        self.llm.reconfigure(new_llm_config)
        self._config_mgr.save(app_config)

    def save_config(self):
        """持久化当前配置到磁盘"""
        self._config_mgr.save(self._app_config)

    # ── 记忆 API ─────────────────────────────────────────────

    def remember(self, name: str, content: str, mem_type: str = "user",
                 description: str = "", importance: int = 5):
        """手动添加一条长期记忆。"""
        entry = MemoryEntry(
            name=name,
            description=description or content[:80],
            type=mem_type,
            content=content,
            importance=importance,
        )
        self.memory.add(entry)

    def recall(self, query: str = "", max_items: int = 10) -> str:
        """检索记忆并格式化为文本。"""
        return self.memory.to_context_text(max_items=max_items, query=query or None)

    def forget(self, name: str) -> bool:
        """删除一条记忆。"""
        return self.memory.delete(name)

    # ── LLM 记忆提取 (OpenClaw 认知巩固模式) ─────────────────

    _MEMORY_EXTRACTION_PROMPT = """从以下对话中提取值得长期记住的**用户信息**。只提取用户明确说的内容，不要推测。

提取类型:
- "personal": 姓名、身份、个人特征
- "preference": 歌曲/歌手/风格偏好
- "goal": 学习目标、想提升的方向
- "vocal": 音域、声部、嗓音特点、唱歌习惯
- "fact": 其他值得记住的个人信息

对每条信息评估 importance (1-10):
- 9-10: 核心身份信息、长期目标
- 7-8: 重要偏好或习惯
- 5-6: 一般性信息
- 3-4: 一次性提及

以纯 JSON 数组输出，每个元素: {"type":"...", "content":"...", "importance":N}
没有值得提取的信息返回 []。只输出 JSON，不要其他文字。"""

    def _extract_memories_async(self, user_message: str, assistant_response: str):
        """在后台线程中执行 LLM 记忆提取，不阻塞主流程。"""
        thread = threading.Thread(
            target=self._llm_extract_memories,
            args=(user_message, assistant_response),
            daemon=True,
        )
        thread.start()

    def _llm_extract_memories(self, user_message: str, assistant_response: str):
        """LLM 驱动的记忆提取（替换旧的正则方案）。

        异步执行不阻塞主流程：失败静默，不影响对话。
        """
        import json as _json

        conversation = f"用户: {user_message}\nAI: {assistant_response[:500]}"

        try:
            result = self.llm.chat(
                [{"role": "user", "content": conversation}],
                system=self._MEMORY_EXTRACTION_PROMPT,
                max_tokens=600,
                temperature=0.1,
            )
            # 提取 JSON（可能被 markdown 代码块包裹）
            json_str = result.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("\n", 1)[1].rsplit("\n```", 1)[0]
            data = _json.loads(json_str)
            if not isinstance(data, list):
                return

            for item in data:
                if not isinstance(item, dict):
                    continue
                content = item.get("content", "").strip()
                mem_type = item.get("type", "fact").strip()
                importance = min(10, max(1, int(item.get("importance", 5))))

                if not content or len(content) < 4:
                    continue

                # 生成稳定的 name
                name = f"{mem_type}_{abs(hash(content)) % 100000}"

                # 检查是否已有相似记忆 → 更新而非新增
                existing = self.memory.get(name)
                if existing and existing.importance >= importance:
                    continue  # 已有更重要的版本，跳过

                self.remember(
                    name=name,
                    content=content,
                    mem_type=mem_type,
                    description=content[:80],
                    importance=importance,
                )

        except Exception:
            pass  # 静默失败，不影响对话

    # ── 知识自增长 ─────────────────────────────────────────────

    _KNOWLEDGE_EXTRACTION_PROMPT = """从以下AI声乐教练的回答中，提取出值得沉淀为知识库条目的**声乐知识**。

只提取有实质内容、可复用的声乐教学知识。日常闲聊、简单鼓励、对个人的具体反馈不提取。

对每条知识评估：
- title: 简短的标题（10字以内）
- category: 分类（breathing/resonance/range/technique/practice/health/style/theory）
- level: 难度（beginner/elementary/intermediate/advanced）
- tags: 1-3个标签
- summary: 一句话摘要（30字内）
- theory: 理论知识要点
- practice: 练习方法
- common_mistakes: 常见错误（列表）

以纯 JSON 数组输出，每个元素: {"title":"...", "category":"...", "level":"...", "tags":[...], "summary":"...", "theory":"...", "practice":"...", "common_mistakes":[...]}
没有值得沉淀的知识返回 []。只输出 JSON，不要其他文字。"""

    def _extract_knowledge_async(self, assistant_response: str):
        """在后台从 coach 回复中提取可沉淀的声乐知识。"""
        if len(assistant_response) < 200:
            return  # 短回复不太可能含结构化知识

        def _run():
            try:
                from .knowledge.store import KnowledgeEntry
                import json as _json

                result = self.llm.chat(
                    [{"role": "user", "content": assistant_response[:2000]}],
                    system=self._KNOWLEDGE_EXTRACTION_PROMPT,
                    max_tokens=800,
                    temperature=0.1,
                )
                json_str = result.strip()
                if json_str.startswith("```"):
                    json_str = json_str.split("\n", 1)[1].rsplit("\n```", 1)[0]
                data = _json.loads(json_str)
                if not isinstance(data, list) or len(data) == 0:
                    return

                store = self.knowledge_retriever.store
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    entry = KnowledgeEntry({
                        "title": item.get("title", ""),
                        "category": item.get("category", "technique"),
                        "level": item.get("level", "intermediate"),
                        "tags": item.get("tags", []),
                        "content": {
                            "summary": item.get("summary", ""),
                            "theory": item.get("theory", ""),
                            "practice": item.get("practice", ""),
                            "common_mistakes": item.get("common_mistakes", []),
                        },
                    })
                    if entry.title and (entry.theory or entry.practice):
                        store.add_entry(entry, persist=True, source="llm_extract")

            except Exception:
                pass  # 静默失败

        threading.Thread(target=_run, daemon=True).start()

    # ── 对话摘要 (OpenClaw 工作记忆 → 情景记忆压缩) ──────────

    _SUMMARY_PROMPT = """将以下对话历史压缩为结构化摘要。输出 JSON：

{
  "summary": "一句话概述这段对话（50字内）",
  "key_facts": ["用户提到的关键事实1", "事实2", ...],
  "questions_asked": ["用户提出的重要问题"],
  "progress": ["用户在唱歌/练习方面的进展"],
  "preferences": ["用户表达的音乐/风格偏好"],
  "decisions": ["用户做出的决定或计划"]
}

规则：
- 只提取明确提到的信息，不要推测
- 忽略礼节性问候和客套话
- 每个列表只保留有意义的内容（可为空数组）
- 直输出 JSON，不要其他文字"""

    def _maybe_summarize_conversation(self):
        """当对话历史过长时，将早期消息压缩为结构化情景记忆。

        保留最近 6 轮不变，将更早的对话压缩成结构化摘要和关键事实，
        注入 system prompt 以维持长对话的连贯性。
        """
        import json as _json

        MAX_MESSAGES = 20  # 超过此数量触发压缩
        KEEP_RECENT = 12   # 保留最近 12 条消息 (6 轮) 不压缩

        history = self.session_mgr._chat_history
        if len(history) <= MAX_MESSAGES:
            return ""

        # 取最早的消息进行压缩
        old_messages = history[:-KEEP_RECENT]
        if len(old_messages) < 4:
            return ""

        # 格式化为对话文本
        conversation = "\n".join(
            f"{'用户' if m['role']=='user' else 'AI'}: {m['content'][:200]}"
            for m in old_messages
        )

        try:
            result = self.llm.chat(
                [{"role": "user", "content": conversation}],
                system=self._SUMMARY_PROMPT,
                max_tokens=400,
                temperature=0.2,
            )
            # 解析 JSON
            json_str = result.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("\n", 1)[1].rsplit("\n```", 1)[0]
            data = _json.loads(json_str)

            summary = data.get("summary", "")
            key_facts = data.get("key_facts", [])
            questions = data.get("questions_asked", [])
            progress = data.get("progress", [])
            preferences = data.get("preferences", [])
            decisions = data.get("decisions", [])

            # 构建结构化上下文
            context_parts = []
            if summary:
                context_parts.append(f"[对话摘要] {summary}")
            if key_facts:
                context_parts.append("[关键事实]\n" + "\n".join(f"• {f}" for f in key_facts))
            if questions:
                context_parts.append("[用户关心的问题]\n" + "\n".join(f"• {q}" for q in questions))
            if progress:
                context_parts.append("[学习进展]\n" + "\n".join(f"• {p}" for p in progress))
            if preferences:
                context_parts.append("[偏好]\n" + "\n".join(f"• {p}" for p in preferences))
            if decisions:
                context_parts.append("[决定/计划]\n" + "\n".join(f"• {d}" for d in decisions))

            context_block = "\n\n".join(context_parts)

            # 存储压缩后的历史：系统消息 + 最近消息
            self.session_mgr._chat_history = [
                {"role": "system", "content": context_block}
            ] + history[-KEEP_RECENT:]
            return context_block
        except Exception:
            # JSON 解析失败 → 回退到简单摘要
            pass

        # 回退路径：使用简单摘要
        try:
            fallback_prompt = "将以下对话历史压缩为一段简洁摘要（中文，150字以内）。重点保留用户个人信息、偏好、目标、唱歌相关的问题。只输出摘要文本。"
            summary = self.llm.chat(
                [{"role": "user", "content": conversation}],
                system=fallback_prompt,
                max_tokens=250,
                temperature=0.2,
            )
            self.session_mgr._chat_history = [
                {"role": "system", "content": f"[对话摘要] {summary.strip()}"}
            ] + history[-KEEP_RECENT:]
            return summary.strip()
        except Exception:
            return ""

    # ── 联网搜索 ─────────────────────────────────────────────

    def _do_web_search(self, query: str) -> str:
        """执行联网搜索并返回格式化的上下文文本"""
        if self._search_provider is None:
            try:
                self._search_provider = get_search_provider()
            except Exception:
                return ""

        try:
            resp = self._search_provider.search(query)
            return self._search_provider.format_for_prompt(resp)
        except Exception:
            return ""

    # ── 主要交互入口 ─────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        *,
        singing_context: Optional[SingingContext] = None,
        with_knowledge: bool = True,
        with_curriculum: bool = False,
        with_memory: bool = True,
    ) -> str:
        """自由对话 —— 用户提问，Agent 自适应切换闲聊/专业指导模式。

        根据话题自动判断：日常聊天以朋友身份轻松回应；
        声乐相关问题时切换教练模式，注入知识库进行专业指导。
        """
        ctx = singing_context or self._last_singing_ctx

        # —— 意图检测：用户是在闲聊还是请教声乐 ——
        is_coaching, intent_conf = detect_intent(user_message)

        # —— 联网搜索：检测是否需要实时信息 ——
        search_text = ""
        if detect_search_intent(user_message):
            search_text = self._do_web_search(user_message)

        # —— 知识检索：仅在声乐教练意图时检索 ——
        knowledge_text = ""
        if with_knowledge and is_coaching:
            knowledge_text = self.knowledge_retriever.retrieve_for_prompt(
                user_message, top_k=3
            )

        # —— 记忆检索 ——
        memory_text = ""
        if with_memory:
            memory_text = self.memory.to_context_text(max_items=10, query=user_message)

        # —— 练习数据（量化反馈） ——
        practice_text = self.session_mgr.format_practice_context()

        # —— 演唱数据上下文 ——
        singing_text = ""
        if ctx:
            singing_text = self.ctx_builder.build_full_context(ctx, "l2")

        # —— 课程上下文（仅专业模式时注入） ——
        curriculum_text = ""
        if with_curriculum and is_coaching:
            level = self.session_mgr.profile.level
            curriculum_text = self.knowledge_retriever.get_curriculum_context(level)

        # —— 构建 system prompt ——
        system = build_system_prompt(
            self._identity, memory_text,
            coaching_mode=is_coaching, knowledge_text=knowledge_text,
        )
        # 练习数据注入（在记忆之后、任务之前）
        if practice_text:
            system += "\n\n" + practice_text
        # 联网搜索结果
        if search_text:
            system += "\n\n" + search_text

        # —— 构建任务 prompt：根据模式选择不同的对话引导 ——
        task_prompt = build_qa_prompt(singing_text, coaching_mode=is_coaching)
        if curriculum_text:
            task_prompt += f"\n\n{curriculum_text}"
        system += "\n" + task_prompt

        # —— 对话摘要：长聊时压缩早期历史 ——
        summary = self._maybe_summarize_conversation()
        if summary:
            system = f"[历史对话摘要] {summary}\n\n" + system

        # —— 对话历史 ——
        history = self.session_mgr.get_chat_history(6)
        messages = history + [{"role": "user", "content": user_message}]

        # —— 调用 LLM（支持 tool use） ——
        if self._on_thinking:
            self._on_thinking()

        use_tools = self._tools_enabled and is_coaching
        tool_uses = []

        if use_tools:
            # 第一轮：非流式调用，检测是否需要 tool use
            result = self.llm.chat_with_tools(
                messages,
                system=system,
                tools=TOOL_DEFINITIONS,
            )
            tool_uses = result.get("tool_uses", [])
            if tool_uses:
                # 执行工具并追加结果
                tool_results = self._tool_executor.execute_all(tool_uses)
                anthropic_msgs = []
                for m in messages:
                    if m["role"] != "system":
                        anthropic_msgs.append({"role": m["role"], "content": m["content"]})
                # 添加 assistant 消息（含 tool_use 块）
                assistant_content = []
                for tu in tool_uses:
                    assistant_content.append({
                        "type": "tool_use",
                        "id": tu["id"],
                        "name": tu["name"],
                        "input": tu["input"],
                    })
                anthropic_msgs.append({"role": "assistant", "content": assistant_content})
                # 添加 tool_result 消息
                anthropic_msgs.append({"role": "user", "content": tool_results})
                # 第二轮：流式调用，基于工具结果生成最终回复
                response = self.llm.chat(
                    anthropic_msgs,
                    system=system,
                    on_stream=self._on_stream,
                )
            elif result.get("text"):
                response = result["text"]
            else:
                # 无 text 也无 tool_uses，fallback 到流式
                response = self.llm.chat(
                    messages,
                    system=system,
                    on_stream=self._on_stream,
                )
        else:
            response = self.llm.chat(
                messages,
                system=system,
                on_stream=self._on_stream,
            )

        # —— 保存对话 ——
        self.session_mgr.add_message("user", user_message)
        self.session_mgr.add_message("assistant", response)

        # —— LLM 自动提取记忆（异步不阻塞主流程） ——
        self._extract_memories_async(user_message, response)

        # —— 知识自增长：教练模式下从回复中提取可沉淀知识 ——
        if is_coaching:
            self._extract_knowledge_async(response)

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
        """演唱后分析 —— 对刚完成的演唱给出详细反馈。"""
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

        if ctx.stats:
            sid = self.session_mgr.start_session(
                focus="演唱分析", song_name=song_name
            )
            # 从 JSON 中提取录音时长
            duration_min = 0.0
            if analysis_json_path:
                try:
                    import json
                    with open(analysis_json_path, "r") as f:
                        _d = json.load(f)
                    _ri = _d.get("recording_info", {}) or {}
                    duration_min = float(_ri.get("duration", 0)) / 60.0
                except Exception:
                    pass
            self.session_mgr.end_session(
                sid,
                duration_minutes=round(duration_min, 1),
                accuracy=ctx.stats.pitch_accuracy,
                analysis_data_path=str(analysis_json_path or ""),
            )

        memory_text = self.memory.to_context_text(max_items=5)
        task_prompt = build_analysis_prompt(singing_text)
        system = build_system_prompt(self._identity, memory_text) + "\n" + task_prompt

        if self._on_thinking:
            self._on_thinking()

        response = self.llm.chat(
            [{"role": "user", "content": f"请分析我刚刚演唱的{song_name}。"}],
            system=system,
            on_stream=self._on_stream,
        )

        self.session_mgr.add_message("user", f"分析我的演唱: {song_name}")
        self.session_mgr.add_message("assistant", response)

        self._extract_memories_async(f"分析我的演唱: {song_name}", response)

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
        """与专业歌手对比分析。"""
        comp_result = self.comparer.compare(
            user_json, ref_json,
            reference_name=reference_name,
        )

        user_ctx = self.ctx_builder.from_analysis_json(user_json)
        user_ctx.comparison = comp_result
        self._last_singing_ctx = user_ctx

        singing_text = self.ctx_builder.build_full_context(user_ctx, "l3")

        task_prompt = build_comparison_prompt(singing_text, song_name, reference_name)
        system = build_system_prompt(self._identity, "") + "\n" + task_prompt

        if self._on_thinking:
            self._on_thinking()

        response = self.llm.chat(
            [{"role": "user", "content": f"我唱了{song_name}，请和专业歌手{reference_name}的版本对比分析。"}],
            system=system,
            on_stream=self._on_stream,
        )

        self.session_mgr.add_message("user", f"对比分析: {song_name} vs {reference_name}")
        self.session_mgr.add_message("assistant", response)

        self._extract_memories_async(f"对比分析: {song_name} vs {reference_name}", response)

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
        memory_text = self.memory.to_context_text(max_items=5)

        task_prompt = build_practice_plan_prompt(curriculum_text, singing_text, user_goal)
        system = build_system_prompt(self._identity, memory_text) + "\n" + task_prompt

        if self._on_thinking:
            self._on_thinking()

        response = self.llm.chat(
            [{"role": "user", "content": f"请根据我的当前水平（{level}），制定一个练习计划。我的目标是：{user_goal}"}],
            system=system,
            on_stream=self._on_stream,
        )

        self.session_mgr.add_message("user", "请帮我制定练习计划")
        self.session_mgr.add_message("assistant", response)

        self._extract_memories_async("请帮我制定练习计划", response)

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

        ai_feedback = ""
        try:
            singing_text = self.ctx_builder.build_full_context(ctx, "l2")
            task_prompt = build_analysis_prompt(singing_text)
            system = build_system_prompt(self._identity, "")
            ai_feedback = self.llm.chat(
                [{"role": "user", "content": "请简要分析（200字内）"}],
                system=system + "\n" + task_prompt,
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
            system = build_system_prompt(self._identity, "")
            ai_feedback = self.llm.chat(
                [{"role": "user", "content": "请简要分析（200字内）"}],
                system=system + "\n" + task_prompt,
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
        self._last_singing_ctx = ctx

    def load_analysis_file(self, path: str | Path) -> SingingContext:
        ctx = self.ctx_builder.from_analysis_json(path)
        self._last_singing_ctx = ctx
        return ctx

    def get_profile_summary(self) -> str:
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

    # ── 记忆巩固 ─────────────────────────────────────────────

    def consolidate_memories(self, dry_run: bool = False) -> list[str]:
        """审查并合并相似记忆（OpenClaw 风格的认知巩固）。

        Args:
            dry_run: True 时只返回可合并的建议，不实际执行合并。

        Returns:
            操作日志列表。
        """
        merges = self.memory.consolidate(dry_run=dry_run)
        logs = []
        for keep, remove in merges:
            logs.append(
                f"合并记忆: '{remove.description[:40]}...' → '{keep.description[:40]}...'"
            )
        if not logs:
            logs.append("未发现可合并的记忆。")
        return logs

    @property
    def memory_stats(self) -> dict:
        return self.memory.stats

    @property
    def knowledge_stats(self) -> dict:
        return self.knowledge_retriever.store_stats
