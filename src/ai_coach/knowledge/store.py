"""知识库存储 —— 加载 YAML 知识条目，支持关键词检索和向量检索"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml


# ═══════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════

class KnowledgeEntry:
    """单条知识条目"""
    __slots__ = (
        "id", "title", "category", "level", "tags", "related",
        "summary", "theory", "practice", "common_mistakes",
        "criteria", "exercises", "faq", "_raw",
    )

    def __init__(self, raw: dict):
        self._raw = raw
        self.id: str = raw.get("id", "")
        self.title: str = raw.get("title", "")
        self.category: str = raw.get("category", "")
        self.level: str = raw.get("level", "elementary")
        self.tags: list[str] = raw.get("tags", [])
        self.related: list[str] = raw.get("related", [])

        content = raw.get("content", {})
        self.summary: str = content.get("summary", "")
        self.theory: str = content.get("theory", "")
        self.practice: str = content.get("practice", "")
        self.common_mistakes: list[str] = content.get("common_mistakes", [])
        self.criteria: str = content.get("criteria", "")
        self.exercises: list[dict] = content.get("exercises", [])
        self.faq: list[dict] = content.get("faq", [])

    @property
    def full_text(self) -> str:
        """拼接所有文本字段用于检索"""
        parts = [
            self.title,
            self.summary,
            self.theory,
            self.practice,
            self.criteria,
            " ".join(self.tags),
            " ".join(self.common_mistakes),
        ]
        return "\n".join(p for p in parts if p)

    def to_prompt_context(self) -> str:
        """格式化为 LLM 可用的知识上下文"""
        lines = [f"## {self.title}", f"**分类**: {self.category} | **难度**: {self.level}"]
        if self.summary:
            lines.append(f"\n{self.summary}")
        if self.theory:
            lines.append(f"\n{self.theory.strip()}")
        if self.common_mistakes:
            lines.append("\n**常见错误**:")
            for m in self.common_mistakes:
                lines.append(f"- {m}")
        if self.criteria:
            lines.append(f"\n**判断标准**: {self.criteria}")
        if self.exercises:
            lines.append("\n**练习方法**:")
            for ex in self.exercises:
                lines.append(f"\n### {ex.get('name', '练习')}")
                for s in ex.get("steps", []):
                    lines.append(f"- {s}")
                if ex.get("duration"):
                    lines.append(f"  _时长: {ex['duration']}_")
        return "\n".join(lines)


class CurriculumStage:
    """课程阶段"""
    __slots__ = ("id", "name", "level", "description", "modules")

    def __init__(self, raw: dict):
        self.id: str = raw.get("id", "")
        self.name: str = raw.get("name", "")
        self.level: str = raw.get("level", "beginner")
        self.description: str = raw.get("description", "")
        self.modules: list[dict] = raw.get("modules", [])


# ═══════════════════════════════════════════════════════════════
# KnowledgeStore
# ═══════════════════════════════════════════════════════════════


class KnowledgeStore:
    """知识库管理器 —— 加载、检索、管理声乐知识条目"""

    def __init__(self, knowledge_dir: Optional[Path] = None):
        if knowledge_dir is None:
            knowledge_dir = Path(__file__).resolve().parent
        self._dir = knowledge_dir
        self.entries: dict[str, KnowledgeEntry] = {}
        self.stages: list[CurriculumStage] = []
        self._tag_index: dict[str, list[str]] = {}  # tag → entry_ids
        self._loaded = False

    # ── 加载 ──────────────────────────────────────────────────

    def load_all(self):
        """加载全部知识库文件"""
        if self._loaded:
            return

        yaml_files = sorted(self._dir.glob("*.yaml"))
        for yf in yaml_files:
            try:
                data = yaml.safe_load(yf.read_text(encoding="utf-8"))
                if data is None:
                    continue
                if yf.name == "curriculum.yaml":
                    self._load_curriculum(data)
                elif "entries" in data:
                    self._load_entries(data["entries"])
            except Exception as e:
                print(f"[KnowledgeStore] 加载 {yf.name} 失败: {e}")

        self._build_tag_index()
        self._loaded = True

    def _load_entries(self, entries: list[dict]):
        for raw in entries:
            entry = KnowledgeEntry(raw)
            if entry.id:
                self.entries[entry.id] = entry

    def _load_curriculum(self, data: dict):
        for stage_raw in data.get("stages", []):
            self.stages.append(CurriculumStage(stage_raw))

    def _build_tag_index(self):
        self._tag_index.clear()
        for eid, entry in self.entries.items():
            for tag in entry.tags:
                tag_lower = tag.lower()
                self._tag_index.setdefault(tag_lower, []).append(eid)

    # ── 检索 ──────────────────────────────────────────────────

    def search_by_keyword(self, query: str, top_k: int = 5) -> list[KnowledgeEntry]:
        """基于关键词匹配的检索（无需向量库的轻量方案）"""
        query_lower = query.lower()
        scored: list[tuple[float, KnowledgeEntry]] = []

        for eid, entry in self.entries.items():
            score = 0.0
            text_lower = entry.full_text.lower()

            # 标题命中加权
            if query_lower in entry.title.lower():
                score += 10.0
            # 标签命中
            for tag in entry.tags:
                if query_lower in tag.lower() or tag.lower() in query_lower:
                    score += 5.0

            # 全文 TF 评分
            words = re.findall(r'\w+', query_lower)
            for w in words:
                count = text_lower.count(w)
                if count > 0:
                    score += min(count, 5) * 1.0  # 上限避免异常词频主导

            # 分类匹配
            if query_lower in entry.category.lower():
                score += 3.0

            # 难度匹配
            level_map = {"入门": "beginner", "初级": "elementary", "中级": "intermediate", "高级": "advanced"}
            for cn, en in level_map.items():
                if cn in query_lower and en == entry.level:
                    score += 3.0

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    def search_semantic(
        self, query: str, top_k: int = 5
    ) -> list[KnowledgeEntry]:
        """基于 ChromaDB 向量的语义检索（需安装 chromadb 和 sentence-transformers）

        如果 ChromaDB 不可用，自动回退到关键词检索。
        """
        try:
            return self._search_chromadb(query, top_k)
        except Exception:
            return self.search_by_keyword(query, top_k)

    def _search_chromadb(self, query: str, top_k: int) -> list[KnowledgeEntry]:
        import numpy as np

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return self.search_by_keyword(query, top_k)

        # 懒加载 embedding 模型
        if not hasattr(self, "_embedder"):
            self._embedder = SentenceTransformer(
                "paraphrase-multilingual-MiniLM-L12-v2"
            )

        # 懒加载 ChromaDB 集合
        collection = self._get_or_build_chroma_collection()

        q_emb = self._embedder.encode([query], normalize_embeddings=True)
        results = collection.query(query_embeddings=q_emb.tolist(), n_results=min(top_k, len(self.entries)))

        entries = []
        for eid in results["ids"][0]:
            if eid in self.entries:
                entries.append(self.entries[eid])
        return entries

    def _get_or_build_chroma_collection(self):
        import chromadb

        if not hasattr(self, "_chroma_client"):
            self._chroma_client = chromadb.PersistentClient(
                path=str(self._dir.parent / "_chroma_cache")
            )

        try:
            collection = self._chroma_client.get_collection("vocal_knowledge")
        except Exception:
            collection = self._chroma_client.create_collection("vocal_knowledge")
            # 构建索引
            ids = list(self.entries.keys())
            docs = [self.entries[eid].full_text for eid in ids]
            embeddings = self._embedder.encode(docs, normalize_embeddings=True)
            metadatas = [
                {"title": self.entries[eid].title, "category": self.entries[eid].category}
                for eid in ids
            ]
            batch_size = 100
            for i in range(0, len(ids), batch_size):
                collection.add(
                    ids=ids[i:i + batch_size],
                    documents=docs[i:i + batch_size],
                    embeddings=embeddings[i:i + batch_size].tolist(),
                    metadatas=metadatas[i:i + batch_size],
                )

        return collection

    # ── 查询 ──────────────────────────────────────────────────

    def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        return self.entries.get(entry_id)

    def get_by_category(self, category: str) -> list[KnowledgeEntry]:
        return [e for e in self.entries.values() if e.category == category]

    def get_by_level(self, level: str) -> list[KnowledgeEntry]:
        return [e for e in self.entries.values() if e.level == level]

    def get_by_tag(self, tag: str) -> list[KnowledgeEntry]:
        eids = self._tag_index.get(tag.lower(), [])
        return [self.entries[eid] for eid in eids if eid in self.entries]

    def get_related(self, entry_id: str) -> list[KnowledgeEntry]:
        entry = self.entries.get(entry_id)
        if not entry:
            return []
        return [self.entries[rid] for rid in entry.related if rid in self.entries]

    def get_curriculum_for_level(self, level: str) -> Optional[CurriculumStage]:
        for stage in self.stages:
            if stage.level == level:
                return stage
        return None

    def get_next_stage(self, current_level: str) -> Optional[CurriculumStage]:
        levels = ["beginner", "elementary", "intermediate", "advanced"]
        try:
            idx = levels.index(current_level)
            next_lvl = levels[idx + 1] if idx + 1 < len(levels) else None
            if next_lvl:
                return self.get_curriculum_for_level(next_lvl)
        except ValueError:
            pass
        return None

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def categories(self) -> list[str]:
        cats = set(e.category for e in self.entries.values())
        return sorted(cats)
