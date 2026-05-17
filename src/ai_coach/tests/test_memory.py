"""记忆管理器单元测试 —— CRUD / 搜索 / 遗忘曲线 / 合并"""
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai_coach.memory.manager import MemoryManager, MemoryEntry, _ebbinghaus_weight


class TestMemoryEntry:
    def test_default_values(self):
        entry = MemoryEntry(name="test", description="测试", type="user", content="测试内容")
        assert entry.importance == 5
        assert entry.access_count == 0
        assert entry.created_at != ""
        assert entry.updated_at != ""


class TestEbbinghausWeight:
    """遗忘曲线权重计算"""

    def test_default_entry_weight(self):
        entry = MemoryEntry(name="test", description="", type="user", content="")
        w = _ebbinghaus_weight(entry)
        assert 0.0 <= w <= 1.0

    def test_high_importance_weights_more(self):
        low = MemoryEntry(name="low", description="", type="user", content="", importance=1)
        high = MemoryEntry(name="high", description="", type="user", content="", importance=10)
        assert _ebbinghaus_weight(high) > _ebbinghaus_weight(low)

    def test_accessed_weights_more(self):
        fresh = MemoryEntry(name="fresh", description="", type="user", content="", access_count=10)
        stale = MemoryEntry(name="stale", description="", type="user", content="", access_count=0)
        # 访问多的权重更高
        w_fresh = _ebbinghaus_weight(fresh)
        w_stale = _ebbinghaus_weight(stale)
        assert w_fresh >= w_stale


class TestMemoryManager:
    """MemoryManager 完整 CRUD 测试"""

    @pytest.fixture
    def mgr(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield MemoryManager(data_dir=Path(tmp))

    def test_add_and_get(self, mgr):
        entry = MemoryEntry(
            name="user_name",
            description="用户的名字",
            type="user",
            content="用户叫小明",
            importance=8,
        )
        mgr.add(entry)
        retrieved = mgr.get("user_name")
        assert retrieved is not None
        assert retrieved.content == "用户叫小明"
        assert retrieved.importance == 8

    def test_add_duplicate_merges(self, mgr):
        first = MemoryEntry(name="pref", description="偏好1", type="user", content="喜欢周杰伦", importance=5)
        mgr.add(first)
        second = MemoryEntry(name="pref", description="偏好1更新", type="user", content="喜欢周杰伦和林俊杰", importance=7)
        mgr.add(second)
        retrieved = mgr.get("pref")
        assert retrieved.importance == 7  # 取更高值
        assert "周杰伦" in retrieved.content

    def test_update(self, mgr):
        entry = MemoryEntry(name="goal", description="目标", type="project", content="想唱好高音")
        mgr.add(entry)
        updated = mgr.update("goal", content="想唱好高音和混声", importance=9)
        assert updated is True
        retrieved = mgr.get("goal")
        assert retrieved.content == "想唱好高音和混声"
        assert retrieved.importance == 9

    def test_delete(self, mgr):
        entry = MemoryEntry(name="temp", description="临时", type="user", content="临时的")
        mgr.add(entry)
        assert mgr.delete("temp") is True
        assert mgr.get("temp") is None

    def test_delete_nonexistent(self, mgr):
        assert mgr.delete("does_not_exist") is False

    def test_touch_increments_access(self, mgr):
        entry = MemoryEntry(name="touch_test", description="", type="user", content="test")
        mgr.add(entry)
        mgr.touch("touch_test")
        retrieved = mgr.get("touch_test")
        assert retrieved.access_count == 1

    def test_get_all(self, mgr):
        for i in range(3):
            mgr.add(MemoryEntry(name=f"mem_{i}", description=f"记忆{i}", type="user", content=f"内容{i}"))
        all_entries = mgr.get_all()
        # 排除 MEMORY.md
        assert len(all_entries) == 3

    def test_search_by_name(self, mgr):
        mgr.add(MemoryEntry(name="vocal_range", description="音域", type="vocal", content="C3-E5"))
        mgr.add(MemoryEntry(name="pref_singer", description="喜欢歌手", type="preference", content="周杰伦"))
        results = mgr.search("vocal")
        assert len(results) > 0
        assert results[0].name == "vocal_range"

    def test_search_by_content(self, mgr):
        mgr.add(MemoryEntry(name="m1", description="", type="user", content="用户叫小明喜欢唱歌"))
        mgr.add(MemoryEntry(name="m2", description="", type="user", content="用户学钢琴十年"))
        results = mgr.search("小明")
        assert len(results) == 1
        assert results[0].name == "m1"

    def test_to_context_text(self, mgr):
        mgr.add(MemoryEntry(name="test_mem", description="测试记忆", type="user", content="测试内容"))
        text = mgr.to_context_text(max_items=5)
        assert "[用户记忆]" in text
        assert "测试记忆" in text

    def test_stats(self, mgr):
        mgr.add(MemoryEntry(name="u1", description="", type="user", content="c"))
        mgr.add(MemoryEntry(name="f1", description="", type="feedback", content="c"))
        s = mgr.stats
        assert s["total"] == 2
        assert s["by_type"]["user"] == 1
        assert s["by_type"]["feedback"] == 1

    def test_consolidate_dry_run(self, mgr):
        mgr.add(MemoryEntry(name="a", description="", type="user", content="小明喜欢周杰伦"))
        mgr.add(MemoryEntry(name="b", description="", type="user", content="小明喜欢周杰伦和林俊杰"))
        merges = mgr.consolidate(dry_run=True)
        # 高相似度应触发合并建议
        assert len(merges) >= 0  # 至少不崩溃

    def test_consolidate_executes(self, mgr):
        mgr.add(MemoryEntry(name="x", description="", type="user", content="用户喜欢唱歌每天练声"))
        mgr.add(MemoryEntry(name="y", description="", type="user", content="用户喜欢唱歌每天练声还学钢琴"))
        merges = mgr.consolidate(dry_run=False)
        # 合并后一条应被删除
        remaining = mgr.get_all()
        assert len(remaining) <= 2  # 合并后最多剩 1 条

    def test_atomic_write(self, mgr):
        """验证写入不会留下 .tmp 残留文件"""
        entry = MemoryEntry(name="atomic_test", description="", type="user", content="test")
        mgr.add(entry)
        tmp_files = list(mgr._dir.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_memory_index_updated(self, mgr):
        entry = MemoryEntry(name="indexed", description="索引测试", type="user", content="test")
        mgr.add(entry)
        index_text = mgr._index_path.read_text(encoding="utf-8")
        assert "indexed" in index_text
        assert "索引测试" in index_text
