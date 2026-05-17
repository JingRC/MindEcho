"""AI Coach 长期记忆管理器

参考 OpenClaw PowerMem 的遗忘曲线 + ai-memory 的零 token 存储思路：
- 每个记忆存为 .md 文件（YAML frontmatter + markdown body）
- MEMORY.md 作为索引
- 重要性评分 (1-10) + 访问次数 + Ebbinghaus 遗忘曲线加权
- 支持 4 种类型 + [[wikilink]] 记忆关联
- 记忆巩固：定期合并相关记忆

目录结构：
    ~/.mindecho/memory/
        MEMORY.md          ← 索引
        user_name.md
        user_preferences.md
        ...
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── 数据结构 ──────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """单条记忆"""
    name: str               # kebab-case 短标识，用作文件名
    description: str        # 一行摘要，用于索引和相关性判断
    type: str               # user | feedback | project | reference
    content: str            # markdown 正文
    importance: int = 5     # 重要性 1-10 (OpenClaw: 10=核心身份, 7=重要偏好, 5=一般, 3=临时)
    access_count: int = 0   # 被检索/使用的次数
    last_accessed: str = "" # 最近一次被检索的时间
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ── frontmatter ───────────────────────────────────────────────

def _default_frontmatter(entry: MemoryEntry) -> str:
    return (
        f"---\n"
        f"name: {entry.name}\n"
        f"description: {entry.description}\n"
        f"metadata:\n"
        f"  type: {entry.type}\n"
        f"  importance: {entry.importance}\n"
        f"  access_count: {entry.access_count}\n"
        f"  last_accessed: {entry.last_accessed or entry.created_at}\n"
        f"  created_at: {entry.created_at}\n"
        f"  updated_at: {entry.updated_at}\n"
        f"---\n"
    )


# ── 遗忘曲线权重 ──────────────────────────────────────────────

def _ebbinghaus_weight(entry: MemoryEntry) -> float:
    """Ebbinghaus 遗忘曲线启发的权重计算。

    组合三个因素：
    1. 重要性 (importance) — 线性权重 (0.1-1.0)
    2. 访问频率 — log(1 + access_count) / log(1 + max_access)
    3. 时间衰减 — 1 / (1 + days_since_last_access)

    返回 0.0-1.0 的综合权重。
    """
    # 重要性分量
    imp = entry.importance / 10.0

    # 访问频率分量
    freq = math.log(1 + entry.access_count) / math.log(1 + 10)

    # 时间衰减分量 (Ebbinghaus: 遗忘速度随时间递减)
    days = 0.0
    last = entry.last_accessed or entry.created_at
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            delta = datetime.now().astimezone() - last_dt.replace(tzinfo=last_dt.tzinfo)
            days = max(0, delta.days)
        except Exception:
            pass
    decay = 1.0 / (1.0 + days * 0.1)  # 10天后权重降到 0.5

    return imp * 0.5 + freq * 0.2 + decay * 0.3


# ── Manager ───────────────────────────────────────────────────

class MemoryManager:
    """AI 教练长期记忆管理器（OpenClaw 风格）"""

    _MEMORY_INDEX = "MEMORY.md"
    _MAX_INDEX_LINES = 200

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path.home() / ".mindecho" / "memory"
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / self._MEMORY_INDEX
        if not self._index_path.exists():
            self._index_path.write_text("# AI Coach Memory Index\n\n", encoding="utf-8")

    # ── CRUD ─────────────────────────────────────────────────

    def add(self, entry: MemoryEntry) -> MemoryEntry:
        """添加一条新记忆，自动去重合并已有记忆。"""
        existing = self.get(entry.name)
        if existing:
            # 更新已有记忆：保留原有 importance 或取更高值
            entry.importance = max(existing.importance, entry.importance)
            entry.access_count = existing.access_count
            entry.created_at = existing.created_at
            return self._write_entry(entry)

        return self._write_entry(entry)

    def get(self, name: str) -> Optional[MemoryEntry]:
        """按 name 读取单条记忆。"""
        file_path = self._dir / f"{name}.md"
        if not file_path.exists():
            return None
        return self._parse_file(file_path)

    def get_all(self) -> list[MemoryEntry]:
        """读取所有记忆。"""
        entries = []
        for f in sorted(self._dir.glob("*.md")):
            if f.name == self._MEMORY_INDEX:
                continue
            entry = self._parse_file(f)
            if entry:
                entries.append(entry)
        return entries

    def update(self, name: str, content: str, description: Optional[str] = None,
               importance: Optional[int] = None) -> bool:
        """更新已有记忆的正文和可选描述/重要性。"""
        entry = self.get(name)
        if entry is None:
            return False
        entry.content = content
        entry.updated_at = datetime.now().isoformat()
        if description:
            entry.description = description
        if importance is not None:
            entry.importance = max(1, min(10, importance))
        return self._write_entry(entry, add_to_index=False) is not None

    def delete(self, name: str) -> bool:
        """删除记忆及其索引条目。"""
        file_path = self._dir / f"{name}.md"
        if not file_path.exists():
            return False
        file_path.unlink()
        self._remove_from_index(name)
        return True

    def touch(self, name: str):
        """标记记忆为已访问（增加 access_count + 更新 last_accessed）"""
        entry = self.get(name)
        if entry:
            entry.access_count += 1
            entry.last_accessed = datetime.now().isoformat()
            self._write_entry(entry, add_to_index=False)

    # ── 搜索 ─────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """关键词 + 遗忘曲线加权搜索。"""
        query_lower = query.lower()
        scored = []
        for entry in self.get_all():
            score = 0.0
            if query_lower in entry.name.lower():
                score += 10
            if query_lower in entry.description.lower():
                score += 5
            body_lower = entry.content.lower()
            score += body_lower.count(query_lower) * 2
            if query_lower in entry.type.lower():
                score += 3
            if score > 0:
                # 乘以遗忘曲线权重
                ebb_weight = _ebbinghaus_weight(entry)
                scored.append((score * (0.5 + 0.5 * ebb_weight), entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    # ── LLM 上下文注入 ───────────────────────────────────────

    def to_context_text(self, max_items: int = 10, query: Optional[str] = None) -> str:
        """将记忆格式化为 LLM system prompt 片段。

        按遗忘曲线权重 + 关键词相关性排序。
        """
        if query:
            entries = self.search(query, top_k=max_items)
        else:
            entries = self.get_all()
            entries.sort(key=lambda e: _ebbinghaus_weight(e), reverse=True)
            entries = entries[:max_items]

        if not entries:
            return ""

        lines = ["[用户记忆]"]
        for e in entries:
            summary = e.content.strip().split("\n")[0][:120]
            # 标记并 touch (增加访问计数)
            self.touch(e.name)
            lines.append(f"- [{e.type.upper()}] {e.description}: {summary}")
        return "\n".join(lines)

    # ── 记忆巩固 (OpenClaw openclaw-auto-dream 模式) ──────────

    def consolidate(self, dry_run: bool = False) -> list[tuple[MemoryEntry, MemoryEntry]]:
        """审查所有记忆，标记可合并的相似记忆对。

        返回 (保留, 可删除) 的对列表。不自动执行合并，需外部确认。
        """
        all_entries = self.get_all()
        if len(all_entries) < 2:
            return []

        merges = []
        for i, a in enumerate(all_entries):
            for b in all_entries[i + 1:]:
                if a.type == b.type and self._similarity(a, b) > 0.6:
                    # 保留 importance 更高的，合并内容
                    if a.importance >= b.importance:
                        merges.append((a, b))
                    else:
                        merges.append((b, a))

        if not dry_run and merges:
            for keep, remove in merges:
                keep.content += f"\n\n（合并自 {remove.name}）\n{remove.content}"
                keep.importance = max(keep.importance, remove.importance)
                keep.updated_at = datetime.now().isoformat()
                self._write_entry(keep, add_to_index=False)
                self.delete(remove.name)

        return merges

    def _similarity(self, a: MemoryEntry, b: MemoryEntry) -> float:
        """简单的 Jaccard 相似度（基于词级 overlap）"""
        words_a = set(a.content.lower().split())
        words_b = set(b.content.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    # ── 统计 ─────────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        entries = self.get_all()
        return {
            "total": len(entries),
            "by_type": {
                t: sum(1 for e in entries if e.type == t)
                for t in ["user", "feedback", "project", "reference"]
            },
            "avg_importance": (
                sum(e.importance for e in entries) / len(entries) if entries else 0
            ),
        }

    # ── 内部 ─────────────────────────────────────────────────

    @staticmethod
    def _atomic_write(file_path: Path, text: str):
        """原子写入：先写临时文件再 rename，避免写入中途崩溃导致文件损坏。"""
        tmp = file_path.with_suffix(file_path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(file_path)  # os.replace = 原子 rename（Windows 也支持）

    def _write_entry(self, entry: MemoryEntry, add_to_index: bool = True) -> MemoryEntry:
        """写入记忆文件并可选更新索引。"""
        file_path = self._dir / f"{entry.name}.md"
        full_text = _default_frontmatter(entry) + "\n" + entry.content + "\n"
        self._atomic_write(file_path, full_text)
        if add_to_index:
            self._add_to_index(entry)
        return entry

    def _parse_file(self, file_path: Path) -> Optional[MemoryEntry]:
        """解析 .md 文件为 MemoryEntry。"""
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception:
            return None

        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
        body = text[fm_match.end():] if fm_match else text
        fm_text = fm_match.group(1) if fm_match else ""

        def _fm_str(key: str, default: str = "") -> str:
            m = re.search(rf'^\s*{key}:\s*(.+)$', fm_text, re.MULTILINE)
            return m.group(1).strip().strip('"').strip("'") if m else default

        def _fm_int(key: str, default: int = 0) -> int:
            m = re.search(rf'^\s*{key}:\s*(\d+)\s*$', fm_text, re.MULTILINE)
            return int(m.group(1)) if m else default

        name = _fm_str("name", file_path.stem)
        description = _fm_str("description", "")
        mem_type = _fm_str("type", "user")
        importance = _fm_int("importance", 5)
        access_count = _fm_int("access_count", 0)
        last_accessed = _fm_str("last_accessed", "")

        return MemoryEntry(
            name=name,
            description=description,
            type=mem_type or "user",
            content=body.strip(),
            importance=importance,
            access_count=access_count,
            last_accessed=last_accessed,
            created_at=_fm_str("created_at", ""),
            updated_at=_fm_str("updated_at", ""),
        )

    def _add_to_index(self, entry: MemoryEntry):
        line = f"- [{entry.name}]({entry.name}.md) — {entry.description} (重要度:{entry.importance})\n"
        current = self._index_path.read_text(encoding="utf-8") if self._index_path.exists() else ""
        existing_pattern = rf'- \[{re.escape(entry.name)}\]\(.*?\) — .*\n'
        if re.search(existing_pattern, current):
            current = re.sub(existing_pattern, line, current)
        else:
            current += line
        self._atomic_write(self._index_path, current)

    def _update_index_entry(self, entry: MemoryEntry):
        self._add_to_index(entry)

    def _remove_from_index(self, name: str):
        if not self._index_path.exists():
            return
        current = self._index_path.read_text(encoding="utf-8")
        pattern = rf'- \[{re.escape(name)}\]\(.*?\) — .*\n'
        current = re.sub(pattern, "", current)
        self._atomic_write(self._index_path, current)
