"""LLM API 客户端 —— 支持 Anthropic / OpenAI / DeepSeek 多后端统一适配"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════


@dataclass
class LLMConfig:
    """LLM API 配置 —— 不再从 Claude Code settings 读取，由 AppConfig 驱动"""

    api_key: str = ""
    base_url: str = "https://api.deepseek.com/anthropic"
    model: str = "deepseek-v4-pro"
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 120
    provider: str = ""  # anthropic | openai | "" (自动检测)
    max_retries: int = 3
    retry_base_delay: float = 1.0  # 指数退避基础延迟（秒）

    @classmethod
    def from_app_config(cls, app_config) -> "LLMConfig":
        """从 AppConfig.llm (LLMProviderConfig) 创建 LLMConfig。"""
        llm = app_config.llm
        provider = llm.provider or ""

        # 根据 provider 自动补全默认 base_url
        base_url = llm.base_url
        if not base_url:
            defaults = {
                "deepseek": "https://api.deepseek.com/anthropic",
                "anthropic": "https://api.anthropic.com",
                "openai": "https://api.openai.com/v1",
                "ollama": "http://localhost:11434/v1",
            }
            base_url = defaults.get(provider, "")

        model = llm.model
        if not model:
            defaults_model = {
                "deepseek": "deepseek-v4-pro",
                "anthropic": "claude-sonnet-4-6",
                "openai": "gpt-4o",
                "ollama": "llama3.2",
            }
            model = defaults_model.get(provider, "deepseek-v4-pro")

        return cls(
            api_key=llm.api_key,
            base_url=base_url,
            model=model,
            max_tokens=llm.max_tokens,
            temperature=llm.temperature,
            provider=provider,
        )


# 向后兼容别名
DeepSeekConfig = LLMConfig


# ═══════════════════════════════════════════════════════════════
# LLM Client
# ═══════════════════════════════════════════════════════════════


class LLMClient:
    """统一的 LLM 调用接口，优先使用 Anthropic SDK，失败时回退 OpenAI SDK"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._backend: Optional[str] = None  # "anthropic" | "openai" | None
        self._client: Any = None
        self._init_client()

    def _init_client(self):
        """尝试初始化 SDK 客户端"""
        # 如果 config 指定了 provider 且后端不匹配，允许用 openai
        force_openai = (self.config.provider == "openai")

        if not force_openai:
            try:
                import anthropic
                self._client = anthropic.Anthropic(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    timeout=self.config.timeout,
                )
                self._backend = "anthropic"
                return
            except ImportError:
                pass

        try:
            from openai import OpenAI
            oai_base = self.config.base_url
            # 如果 URL 以 /anthropic 结尾，尝试转换为 /v1
            if oai_base.endswith("/anthropic"):
                oai_base = oai_base[:-len("/anthropic")] + "/v1"
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=oai_base,
                timeout=self.config.timeout,
            )
            self._backend = "openai"
            return
        except ImportError:
            pass

        raise RuntimeError(
            "需要安装 anthropic 或 openai Python SDK: "
            "pip install anthropic 或 pip install openai"
        )

    def reconfigure(self, config: LLMConfig):
        """运行时切换配置 —— 重新初始化底层客户端。"""
        self.config = config
        self._backend = None
        self._client = None
        self._fallback_client = None
        self._init_client()

    # ── 离线 fallback ───────────────────────────────────────────

    _fallback_client: Any = None

    def _ensure_fallback(self) -> bool:
        """初始化或检查本地 Ollama fallback 客户端是否可用。"""
        if self.config.provider == "ollama":
            return False  # 已经是本地模型，不需要 fallback

        if self._fallback_client is not None:
            return True

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key="ollama",  # Ollama 不需要真实 key
                base_url="http://localhost:11434/v1",
                timeout=30,
            )
            # 快速验证连接
            models = client.models.list()
            if models.data:
                self._fallback_client = client
                return True
        except Exception:
            self._fallback_client = False
        return False

    def _try_fallback_chat(
        self,
        messages: list[dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """使用本地 Ollama 模型执行对话（OpenAI 兼容 API）。"""
        oai_msgs = []
        if system:
            oai_msgs.append({"role": "system", "content": system})
        oai_msgs.extend(messages)

        response = self._fallback_client.chat.completions.create(
            model="llama3.2",  # 默认本地模型
            messages=oai_msgs,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature if temperature is not None else self.config.temperature,
        )
        return response.choices[0].message.content

    # ── 重试逻辑 ─────────────────────────────────────────────

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        """判断异常是否值得重试（网络/速率/服务端错误 → 重试；认证/参数错误 → 不重试）。"""
        msg = str(error).lower()
        # 不可重试的关键词
        non_retryable = (
            "401", "403", "invalid api key", "incorrect api key",
            "authentication", "unauthorized", "bad request", "400",
            "invalid request", "not found", "404",
        )
        for kw in non_retryable:
            if kw in msg:
                return False
        # 可重试的关键词 / 类型
        retryable = (
            "429", "rate limit", "too many requests",
            "500", "502", "503", "504",
            "timeout", "timed out", "connection",
            "reset by peer", "broken pipe", "eof",
            "service unavailable", "overloaded",
        )
        for kw in retryable:
            if kw in msg:
                return True
        # 默认对网络类异常重试
        return isinstance(error, (ConnectionError, TimeoutError, OSError))

    def _call_with_retry(self, fn, *args, **kwargs):
        """用指数退避重试调用 fn(*args, **kwargs)。"""
        max_retries = self.config.max_retries
        base_delay = self.config.retry_base_delay
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt >= max_retries or not self._is_retryable(e):
                    raise
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)

        raise last_error  # unreachable，但 satisfy type checker

    # ── 公开 API ─────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_stream: Optional[Callable[[str], None]] = None,
        tools: Optional[list[dict]] = None,
    ) -> str:
        """发送对话请求，返回完整响应文本。含指数退避重试，不可用时 fallback Ollama。"""
        try:
            if self._backend == "anthropic":
                return self._call_with_retry(
                    self._chat_anthropic,
                    messages, system=system,
                    temperature=temperature, max_tokens=max_tokens,
                    on_stream=on_stream, tools=tools,
                )
            else:
                return self._call_with_retry(
                    self._chat_openai,
                    messages, system=system,
                    temperature=temperature, max_tokens=max_tokens,
                    on_stream=on_stream,
                )
        except Exception as e:
            if not self._is_retryable(e):
                raise RuntimeError(f"LLM 调用失败: {e}")
            # 可重试错误已耗尽 → 尝试本地 Ollama fallback
            if self._ensure_fallback():
                try:
                    return self._try_fallback_chat(
                        messages, system=system,
                        temperature=temperature, max_tokens=max_tokens,
                    )
                except Exception:
                    pass
            raise RuntimeError(
                f"LLM 调用失败（已重试 {self.config.max_retries} 次），"
                f"本地 Ollama 也不可用。原始错误: {e}"
            )

    def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        """发送对话请求，返回包含 tool_use 信息的 dict。

        Returns:
            {"text": str, "tool_uses": list[dict]} 其中 tool_uses 为
            [{"id": "...", "name": "...", "input": {...}}, ...]
        """
        try:
            if self._backend == "anthropic":
                return self._call_with_retry(
                    self._chat_anthropic_raw,
                    messages, system=system,
                    temperature=temperature, max_tokens=max_tokens, tools=tools,
                )
            else:
                text = self._call_with_retry(
                    self._chat_openai,
                    messages, system=system,
                    temperature=temperature, max_tokens=max_tokens,
                )
                return {"text": text, "tool_uses": []}
        except Exception as e:
            if not self._is_retryable(e):
                raise RuntimeError(f"LLM 调用失败: {e}")
            if self._ensure_fallback():
                try:
                    text = self._try_fallback_chat(
                        messages, system=system,
                        temperature=temperature, max_tokens=max_tokens,
                    )
                    return {"text": text, "tool_uses": []}
                except Exception:
                    pass
            raise RuntimeError(
                f"LLM 调用失败（已重试 {self.config.max_retries} 次），"
                f"本地 Ollama 也不可用。原始错误: {e}"
            )

    # ── 后端实现 ─────────────────────────────────────────────

    def _chat_anthropic(
        self,
        messages: list[dict],
        *,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_stream: Optional[Callable[[str], None]] = None,
        tools: Optional[list[dict]] = None,
    ) -> str:
        """Anthropic 后端 —— 返回纯文本（忽略 tool_use 块）。"""
        result = self._chat_anthropic_raw(
            messages, system=system,
            temperature=temperature, max_tokens=max_tokens,
            tools=tools, on_stream=on_stream,
        )
        return result["text"]

    def _chat_anthropic_raw(
        self,
        messages: list[dict],
        *,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        on_stream: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """Anthropic 后端 —— 返回结构化响应（含 tool_use 块）。"""
        import anthropic

        sys_msg = system or ""
        anthropic_msgs = []
        for m in messages:
            if m["role"] == "system":
                if not sys_msg:
                    sys_msg = m["content"]
                else:
                    sys_msg += "\n" + m["content"]
            else:
                anthropic_msgs.append({"role": m["role"], "content": m["content"]})

        kwargs = {
            "model": self.config.model,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }
        if sys_msg:
            kwargs["system"] = sys_msg
        if tools:
            anthropic_tools = []
            for t in tools:
                at = {"name": t["name"], "description": t.get("description", ""), "input_schema": t.get("input_schema", t.get("parameters", {}))}
                anthropic_tools.append(at)
            kwargs["tools"] = anthropic_tools

        # 流式路径
        if on_stream is not None:
            text_parts = []
            with self._client.messages.stream(
                messages=anthropic_msgs, **kwargs
            ) as stream:
                for text_delta in stream.text_stream:
                    text_parts.append(text_delta)
                    on_stream(text_delta)
                final = stream.get_final_message()

            tool_uses = []
            for block in final.content:
                if getattr(block, 'type', '') == 'tool_use':
                    tool_uses.append({
                        "id": block.id,
                        "name": block.name,
                        "input": dict(block.input) if block.input else {},
                    })
            return {"text": "".join(text_parts), "tool_uses": tool_uses}

        # 非流式路径
        response = self._client.messages.create(
            messages=anthropic_msgs, **kwargs
        )

        text_parts = []
        tool_uses = []
        for block in response.content:
            if hasattr(block, 'text'):
                text_parts.append(block.text)
            elif getattr(block, 'type', '') == 'tool_use':
                tool_uses.append({
                    "id": block.id,
                    "name": block.name,
                    "input": dict(block.input) if block.input else {},
                })

        return {"text": "".join(text_parts), "tool_uses": tool_uses}

    def _chat_openai(
        self,
        messages: list[dict],
        *,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_stream: Optional[Callable[[str], None]] = None,
    ) -> str:
        oai_msgs = []
        if system:
            oai_msgs.append({"role": "system", "content": system})
        oai_msgs.extend(messages)

        kwargs = {
            "model": self.config.model,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }

        if on_stream:
            kwargs["messages"] = oai_msgs
            kwargs["stream"] = True
            full = []
            for chunk in self._client.chat.completions.create(**kwargs):
                delta = chunk.choices[0].delta
                if delta.content:
                    full.append(delta.content)
                    on_stream(delta.content)
            return "".join(full)
        else:
            response = self._client.chat.completions.create(
                messages=oai_msgs, **kwargs
            )
            return response.choices[0].message.content


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

_global_client: Optional[LLMClient] = None


def get_client() -> LLMClient:
    global _global_client
    if _global_client is None:
        _global_client = LLMClient()
    return _global_client
