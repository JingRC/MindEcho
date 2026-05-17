"""知识库检索单元测试"""
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai_coach.knowledge.store import KnowledgeStore


class TestKnowledgeStore:
    """知识库加载与检索"""

    @pytest.fixture
    def store(self):
        return KnowledgeStore()

    def test_load_all(self, store):
        store.load_all()
        assert store.entry_count > 0
        assert len(store.categories) > 0

    def test_search_by_keyword_finds_result(self, store):
        store.load_all()
        results = store.search_by_keyword("高音", top_k=3)
        assert len(results) > 0

    def test_search_by_keyword_returns_top_k(self, store):
        store.load_all()
        results = store.search_by_keyword("呼吸", top_k=2)
        assert len(results) <= 2

    def test_search_unknown_returns_empty(self, store):
        store.load_all()
        results = store.search_by_keyword("xyz不存在的查询abc123")
        assert len(results) == 0

    def test_get_by_category(self, store):
        store.load_all()
        for cat in store.categories:
            entries = store.get_by_category(cat)
            for e in entries:
                assert e.category == cat

    def test_get_by_level(self, store):
        store.load_all()
        levels = ["beginner", "elementary", "intermediate", "advanced"]
        for lvl in levels:
            entries = store.get_by_level(lvl)
            for e in entries:
                assert e.level == lvl

    def test_get_by_tag(self, store):
        store.load_all()
        entries = store.get_by_tag("breathing")
        assert isinstance(entries, list)

    def test_get_nonexistent_entry(self, store):
        assert store.get("nonexistent_id") is None

    def test_curriculum_loading(self, store):
        store.load_all()
        assert len(store.stages) > 0

    def test_get_curriculum_for_level(self, store):
        store.load_all()
        stage = store.get_curriculum_for_level("beginner")
        if stage:
            assert stage.level == "beginner"

    def test_semantic_search_fallback(self, store):
        """无 chromadb 时语义检索回退到关键词检索"""
        store.load_all()
        results = store.search_semantic("呼吸练习", top_k=3)
        assert len(results) <= 3


class TestKnowledgeEntry:
    """知识条目的格式化"""

    @pytest.fixture
    def store(self):
        ks = KnowledgeStore()
        ks.load_all()
        return ks

    def test_full_text_not_empty(self, store):
        for entry in store.entries.values():
            assert len(entry.full_text) > 0

    def test_to_prompt_context(self, store):
        for entry in store.entries.values():
            text = entry.to_prompt_context()
            assert len(text) > 0
            assert entry.title in text
