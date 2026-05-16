"""知识库检索器 —— 为 Agent 提供统一的检索接口"""
from __future__ import annotations

from typing import Optional

from .store import KnowledgeEntry, KnowledgeStore

# 全局单例
_store: Optional[KnowledgeStore] = None


def get_knowledge_store() -> KnowledgeStore:
    global _store
    if _store is None:
        _store = KnowledgeStore()
        _store.load_all()
    return _store


class KnowledgeRetriever:
    """知识检索器 —— 组合关键词和语义检索，返回格式化结果"""

    def __init__(self, store: Optional[KnowledgeStore] = None):
        self.store = store or get_knowledge_store()

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        use_semantic: bool = True,
        category_filter: Optional[str] = None,
        level_filter: Optional[str] = None,
    ) -> list[KnowledgeEntry]:
        """检索知识条目

        Args:
            query: 用户问题或查询文本
            top_k: 返回条数
            use_semantic: 是否使用向量语义检索（需 chromadb + sentence-transformers）
            category_filter: 限定分类
            level_filter: 限定难度
        """
        if use_semantic:
            entries = self.store.search_semantic(query, top_k * 2)
        else:
            entries = self.store.search_by_keyword(query, top_k * 2)

        # 过滤
        if category_filter:
            entries = [e for e in entries if e.category == category_filter]
        if level_filter:
            entries = [e for e in entries if e.level == level_filter]

        return entries[:top_k]

    def retrieve_for_prompt(
        self,
        query: str,
        *,
        top_k: int = 3,
        use_semantic: bool = True,
    ) -> str:
        """检索并格式化为可直接嵌入 LLM prompt 的知识文本"""
        entries = self.retrieve(query, top_k=top_k, use_semantic=use_semantic)
        if not entries:
            return ""

        parts = ["【声乐知识库参考内容】"]
        for i, entry in enumerate(entries, 1):
            parts.append(f"\n--- 参考 {i}: {entry.title} ---")
            parts.append(entry.to_prompt_context())
        return "\n".join(parts)

    def get_curriculum_context(self, level: str) -> str:
        """获取当前阶段课程上下文"""
        stage = self.store.get_curriculum_for_level(level)
        if not stage:
            return ""

        lines = [
            f"【当前学习阶段: {stage.name}】",
            f"难度: {stage.level}",
            f"概述: {stage.description}",
            "\n本阶段模块:",
        ]
        for mod in stage.modules:
            lines.append(f"- {mod.get('title', '')}: {mod.get('goals', [])}")
        return "\n".join(lines)

    @property
    def store_stats(self) -> dict:
        return {
            "entry_count": self.store.entry_count,
            "categories": self.store.categories,
            "semantic_available": hasattr(self.store, "_chroma_client"),
        }
