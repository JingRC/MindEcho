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
        "quality_score", "review_status",
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

        # 质量控制字段
        self.quality_score: float = float(raw.get("quality_score", 0.0))
        self.review_status: str = raw.get("review_status", "approved")  # pending / approved / rejected

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

    # ── 动态增长 ──────────────────────────────────────────────

    def _title_similarity(self, title1: str, title2: str) -> float:
        """计算两个标题的相似度（基于字符 trigram Jaccard）。"""
        def _trigrams(s: str) -> set:
            s = s.strip().lower()
            return {s[i:i+3] for i in range(len(s) - 2)} if len(s) >= 3 else {s}
        t1 = _trigrams(title1)
        t2 = _trigrams(title2)
        if not t1 or not t2:
            return 0.0
        return len(t1 & t2) / len(t1 | t2)

    def _content_overlap(self, text1: str, text2: str, top_n: int = 30) -> float:
        """基于高频词的 Jaccard 重叠率。"""
        import re
        def _top_words(text: str, n: int) -> set:
            words = re.findall(r'[一-鿿]+|[a-zA-Z]+', text.lower())
            freq: dict[str, int] = {}
            for w in words:
                if len(w) >= 2:
                    freq[w] = freq.get(w, 0) + 1
            return {w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:n]}
        s1 = _top_words(text1, top_n)
        s2 = _top_words(text2, top_n)
        if not s1 or not s2:
            return 0.0
        return len(s1 & s2) / len(s1 | s2)

    def _find_duplicate(self, entry: KnowledgeEntry) -> Optional[KnowledgeEntry]:
        """查找与新条目高度重复的已有条目，未找到则返回 None。"""
        for existing in self.entries.values():
            # 同类别优先
            cat_match = entry.category == existing.category
            # 标题相似度
            title_sim = self._title_similarity(entry.title, existing.title)
            if title_sim > 0.75:
                return existing
            # 标题 + 内容综合判断
            content_sim = self._content_overlap(entry.full_text, existing.full_text)
            if title_sim > 0.4 and content_sim > 0.5:
                return existing
            if cat_match and content_sim > 0.7:
                return existing
            # 标签高度重叠
            common_tags = set(t.lower() for t in entry.tags) & set(t.lower() for t in existing.tags)
            if len(common_tags) >= 3 and content_sim > 0.4:
                return existing
        return None

    def _merge_into(self, existing: KnowledgeEntry, new: KnowledgeEntry):
        """将新条目的增量信息合并到已有条目。"""
        # 合并标签
        existing_tags_lower = {t.lower() for t in existing.tags}
        for tag in new.tags:
            if tag.lower() not in existing_tags_lower:
                existing.tags.append(tag)
                existing_tags_lower.add(tag.lower())
        # 合并常见错误（去重）
        existing_mistakes = set(m.strip().lower() for m in existing.common_mistakes)
        for m in new.common_mistakes:
            if m.strip().lower() not in existing_mistakes:
                existing.common_mistakes.append(m)
                existing_mistakes.add(m.strip().lower())
        # 合并练习（按名称去重）
        existing_ex_names = {ex.get("name", "").strip() for ex in existing.exercises}
        for ex in new.exercises:
            if ex.get("name", "").strip() not in existing_ex_names:
                existing.exercises.append(ex)
                existing_ex_names.add(ex.get("name", "").strip())
        # 补充 theory/practice 如果已有为空
        if not existing.theory and new.theory:
            existing.theory = new.theory
        if not existing.practice and new.practice:
            existing.practice = new.practice
        # 更新 update 时间
        existing._raw["updated"] = max(
            existing._raw.get("updated", ""), new._raw.get("updated", "")
        )

    def add_entry(self, entry: KnowledgeEntry, persist: bool = True,
                  source: str = "manual"):
        """运行时添加知识条目（带去重合并 + 质量控制）。

        Args:
            entry: 待添加的知识条目
            persist: 是否持久化到 YAML
            source: 来源标记 — "manual" (人工, 默认审核通过),
                    "llm_extract" (LLM 提取, 需审核)
        """
        if not entry.id:
            import uuid
            entry.id = uuid.uuid4().hex[:12]

        # 自动计算质量评分
        entry.quality_score = self._compute_quality_score(entry)

        # LLM 提取的条目默认标记为待审核
        if source == "llm_extract":
            if entry.review_status == "approved":
                pass  # 显式标记为 approved 则保留
            else:
                entry.review_status = "pending"

        # 质量阈值：低于 0.15 的 LLM 提取条目直接丢弃
        if source == "llm_extract" and entry.quality_score < 0.15:
            return

        # 去重检查
        dup = self._find_duplicate(entry)
        if dup is not None:
            # 若新条目的信息更丰富，提升已有条目的质量评分
            dup.quality_score = max(dup.quality_score, entry.quality_score)
            self._merge_into(dup, entry)
            if persist:
                self._save_entry_yaml(dup)
            return

        self.entries[entry.id] = entry
        for tag in entry.tags:
            self._tag_index.setdefault(tag.lower(), []).append(entry.id)
        if persist:
            self._save_entry_yaml(entry)

    def _compute_quality_score(self, entry: KnowledgeEntry) -> float:
        """自动评估知识条目的质量（0.0-1.0）。

        评分因素:
        - 标题存在且有意义 (0.15)
        - 理论知识是否充实 (0.30)
        - 练习方法是否具体 (0.25)
        - 常见错误是否列出 (0.15)
        - 标签是否完整 (0.10)
        - 摘要是否清晰 (0.05)
        """
        score = 0.0
        if entry.title and len(entry.title) >= 2:
            score += 0.15
        if entry.theory and len(entry.theory) >= 50:
            score += 0.30
        elif entry.theory and len(entry.theory) >= 20:
            score += 0.15
        if entry.practice and len(entry.practice) >= 30:
            score += 0.25
        elif entry.practice and len(entry.practice) >= 10:
            score += 0.12
        if entry.common_mistakes and len(entry.common_mistakes) >= 1:
            score += 0.15
        if entry.tags and len(entry.tags) >= 2:
            score += 0.10
        elif entry.tags and len(entry.tags) >= 1:
            score += 0.05
        if entry.summary and len(entry.summary) >= 10:
            score += 0.05
        return min(1.0, score)

    def approve_entry(self, entry_id: str) -> bool:
        """审核通过一条待审核的知识条目。"""
        entry = self.entries.get(entry_id)
        if entry is None:
            return False
        entry.review_status = "approved"
        entry._raw["review_status"] = "approved"
        self._save_entry_yaml(entry)
        return True

    def reject_entry(self, entry_id: str) -> bool:
        """拒绝并删除一条待审核的知识条目。"""
        entry = self.entries.get(entry_id)
        if entry is None:
            return False
        # 删除 YAML 文件和内存条目
        file_path = self._dir / f"_grown_{entry.id}.yaml"
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass
        del self.entries[entry_id]
        for tag in entry.tags:
            tag_ids = self._tag_index.get(tag.lower(), [])
            if entry_id in tag_ids:
                tag_ids.remove(entry_id)
        return True

    def get_pending_entries(self) -> list[KnowledgeEntry]:
        """获取所有待审核的知识条目。"""
        return [e for e in self.entries.values() if e.review_status == "pending"]

    def get_entries_by_quality(self, min_score: float = 0.4) -> list[KnowledgeEntry]:
        """按质量评分过滤条目。"""
        return [e for e in self.entries.values() if e.quality_score >= min_score]

    def _entry_to_dict(self, entry: KnowledgeEntry) -> dict:
        return {
            "id": entry.id,
            "title": entry.title,
            "category": entry.category,
            "level": entry.level,
            "tags": entry.tags,
            "related": entry.related,
            "quality_score": entry.quality_score,
            "review_status": entry.review_status,
            "content": {
                "summary": entry.summary,
                "theory": entry.theory,
                "practice": entry.practice,
                "common_mistakes": entry.common_mistakes,
                "criteria": entry.criteria,
                "exercises": entry.exercises,
                "faq": entry.faq,
            },
        }

    def _save_entry_yaml(self, entry: KnowledgeEntry):
        """将单条知识条目持久化为 YAML 文件。"""
        import yaml
        file_path = self._dir / f"_grown_{entry.id}.yaml"
        data = {"entries": [self._entry_to_dict(entry)]}
        try:
            file_path.write_text(
                yaml.dump(data, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def categories(self) -> list[str]:
        cats = set(e.category for e in self.entries.values())
        return sorted(cats)
