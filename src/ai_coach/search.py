"""Web 搜索提供器 —— 为 AI 教练提供实时联网搜索能力

支持多种后端，默认使用 DuckDuckGo（免费、无需 API key）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str


@dataclass
class SearchResponse:
    query: str
    results: list[SearchResult] = field(default_factory=list)
    backend: str = ""
    error: str = ""


# ── 后端实现 ───────────────────────────────────────────────────

def _search_duckduckgo(query: str, max_results: int = 5) -> SearchResponse:
    """DuckDuckGo 搜索（免费，无需 API key）"""
    # 优先使用新版 ddgs，回退到旧版 duckduckgo_search
    DDGS = None
    try:
        from ddgs import DDGS  # 新版包
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # 旧版包
        except ImportError:
            return SearchResponse(
                query=query,
                error="搜索模块未安装。请运行: pip install ddgs",
            )

    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    snippet=r.get("body", ""),
                    url=r.get("href", ""),
                ))
        return SearchResponse(
            query=query,
            results=results,
            backend="duckduckgo",
        )
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")
        return SearchResponse(query=query, error=str(e), backend="duckduckgo")


# ── 统一接口 ───────────────────────────────────────────────────

# 后端优先级
_BACKENDS = [
    ("duckduckgo", _search_duckduckgo),
]


class WebSearchProvider:
    """联网搜索提供器 —— 按优先级尝试多个后端"""

    def __init__(self, max_results: int = 5, timeout: float = 10.0):
        self._max_results = max_results
        self._timeout = timeout

    def search(self, query: str, max_results: Optional[int] = None) -> SearchResponse:
        """执行搜索，自动选择可用后端"""
        limit = max_results or self._max_results
        for name, fn in _BACKENDS:
            resp = fn(query, limit)
            if resp.error:
                continue
            if resp.results:
                return resp
        # 所有后端都失败，返回错误信息
        return SearchResponse(
            query=query,
            error="搜索模块不可用。请运行: pip install ddgs",
        )

    def format_for_prompt(self, response: SearchResponse) -> str:
        """将搜索结果格式化为 LLM 上下文文本"""
        if not response.results:
            if response.error:
                return f"（联网搜索不可用：{response.error}）"
            return "（未找到相关结果）"

        lines = ["## 联网搜索结果", f"搜索词: {response.query}\n"]
        for i, r in enumerate(response.results, 1):
            lines.append(f"{i}. **{r.title}**")
            lines.append(f"   {r.snippet[:300]}")
            lines.append(f"   来源: {r.url}\n")
        return "\n".join(lines)

    @property
    def available(self) -> bool:
        """检查是否有可用的搜索后端"""
        resp = self.search("test", max_results=1)
        return len(resp.results) > 0


# 全局单例
_default_provider: Optional[WebSearchProvider] = None


def get_search_provider() -> WebSearchProvider:
    global _default_provider
    if _default_provider is None:
        _default_provider = WebSearchProvider()
    return _default_provider
