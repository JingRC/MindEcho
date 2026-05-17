"""AI 教练工具集 —— Function calling 工具定义和执行器"""

from __future__ import annotations

from typing import Any, Optional

# ═══════════════════════════════════════════════════════════════
# 工具定义（Anthropic/OpenAI 兼容 JSON Schema）
# ═══════════════════════════════════════════════════════════════

TOOL_DEFINITIONS = [
    {
        "name": "search_knowledge",
        "description": "搜索声乐知识库，获取关于特定声乐话题的专业知识。用于需要具体理论、练习方法或技巧说明时调用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "要搜索的声乐话题，如'混声技巧'、'呼吸控制'、'高音练习'等",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最多返回几条结果，默认 3",
                    "default": 3,
                },
            },
            "required": ["topic"],
        },
    },
    {
        "name": "get_practice_stats",
        "description": "获取用户的练习统计数据：累计练习次数、时长、音准趋势、最近练习记录等。在用户问'我最近练得怎么样'或需要量化数据时调用。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "save_note",
        "description": "保存一条练习笔记或提醒。用户说'帮我记一下'、'提醒我'时调用。笔记会持久化到长期记忆中。",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要保存的笔记或提醒内容",
                },
                "importance": {
                    "type": "integer",
                    "description": "重要性 1-10，默认 7",
                    "default": 7,
                },
            },
            "required": ["content"],
        },
    },
]

# ═══════════════════════════════════════════════════════════════
# 工具执行器
# ═══════════════════════════════════════════════════════════════

class ToolExecutor:
    """执行 AI 教练工具调用，将结果返回给 LLM。"""

    def __init__(self, agent):
        self._agent = agent

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """执行单个工具调用，返回格式化的结果文本。"""
        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            return f"未知工具: {tool_name}"
        try:
            return handler(tool_input)
        except Exception as e:
            return f"工具执行出错 ({tool_name}): {e}"

    def execute_all(self, tool_uses: list[dict]) -> list[dict]:
        """批量执行工具调用，返回 tool_result 消息列表。"""
        results = []
        for tu in tool_uses:
            result_text = self.execute(tu["name"], tu["input"])
            results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": result_text,
            })
        return results

    # ── 工具实现 ─────────────────────────────────────────────

    def _tool_search_knowledge(self, args: dict) -> str:
        topic = args.get("topic", "")
        max_results = min(args.get("max_results", 3), 5)
        if not topic:
            return "请提供要搜索的声乐话题。"

        text = self._agent.knowledge_retriever.retrieve_for_prompt(
            topic, top_k=max_results
        )
        if not text:
            return f"知识库中未找到与 '{topic}' 直接相关的内容。可以换个关键词试试，或者直接问我，我会用自己的知识回答。"
        return text

    def _tool_get_practice_stats(self, _args: dict) -> str:
        mgr = self._agent.session_mgr
        stats = mgr.get_stats()
        lines = [
            "## 用户练习统计",
            f"- 学习阶段: {stats['level']}",
            f"- 累计练习: {stats['total_sessions']} 次",
            f"- 累计时长: {stats['total_hours']} 小时",
            f"- 音域: {stats['vocal_range']}",
            f"- 近期趋势: {stats['recent_accuracy_trend']}",
        ]
        if stats["focus_areas"]:
            lines.append(f"- 重点关注: {', '.join(stats['focus_areas'])}")
        if stats["completed_stages"]:
            lines.append(f"- 已完成阶段: {', '.join(stats['completed_stages'])}")

        recent = mgr.recent_sessions(5)
        if recent:
            lines.append("\n最近 5 次练习:")
            for s in recent:
                acc_str = f"{s.accuracy*100:.0f}%" if s.accuracy else "N/A"
                name = s.song_name or "自由练习"
                lines.append(f"  - {s.timestamp[:10]} | {name} | 音准: {acc_str} | {s.duration_minutes:.0f}分钟")
        return "\n".join(lines)

    def _tool_save_note(self, args: dict) -> str:
        content = args.get("content", "")
        importance = min(10, max(1, args.get("importance", 7)))
        if not content:
            return "请提供要保存的笔记内容。"

        name = f"note_{abs(hash(content)) % 100000}"
        self._agent.remember(
            name=name,
            content=content,
            mem_type="project",
            description=content[:80],
            importance=importance,
        )
        return f"已保存笔记（重要度:{importance}）: {content[:100]}"
