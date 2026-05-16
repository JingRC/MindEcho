"""LLM API 客户端 —— 支持 DeepSeek / OpenAI / Anthropic 多后端统一适配"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════


@dataclass
class DeepSeekConfig:
    """DeepSeek API 配置 — 默认从 Claude Code settings 读取"""
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/anthropic"
    model: str = "deepseek-v4-pro"
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 120

    @classmethod
    def from_claude_settings(cls) -> "DeepSeekConfig":
        """从 Claude Code settings.json 自动读取配置"""
        settings_paths = [
            Path.home() / ".claude" / "settings.json",
            Path(os.getcwd()) / ".claude" / "settings.json",
        ]
        env = {}
        for sp in settings_paths:
            try:
                if sp.exists():
                    data = json.loads(sp.read_text(encoding="utf-8"))
                    env.update(data.get("env", {}))
            except Exception:
                pass

        return cls(
            api_key=env.get("ANTHROPIC_AUTH_TOKEN", os.environ.get("ANTHROPIC_AUTH_TOKEN", "")),
            base_url=env.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"),
            model=env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "deepseek-v4-pro"),
            max_tokens=4096,
            timeout=int(env.get("API_TIMEOUT_MS", "120000")) // 1000,
        )


# ═══════════════════════════════════════════════════════════════
# LLM Client
# ═══════════════════════════════════════════════════════════════


class LLMClient:
    """统一的 LLM 调用接口，优先使用 Anthropic SDK，失败时回退 OpenAI SDK"""

    def __init__(self, config: Optional[DeepSeekConfig] = None):
        self.config = config or DeepSeekConfig.from_claude_settings()
        self._backend: Optional[str] = None  # "anthropic" | "openai" | None
        self._client: Any = None
        self._init_client()

    def _init_client(self):
        """尝试初始化 SDK 客户端"""
        # 优先 Anthropic SDK
        try:
            import anthropic  # noqa: F811
            self._client = anthropic.Anthropic(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
            )
            self._backend = "anthropic"
            return
        except ImportError:
            pass

        # 回退 OpenAI SDK（使用 DeepSeek 的 OpenAI 兼容端点）
        try:
            from openai import OpenAI
            oai_base = self.config.base_url.replace("/anthropic", "/v1")
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

    # ── 公开 API ─────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_stream: Optional[Callable[[str], None]] = None,
    ) -> str:
        """发送对话请求，返回完整响应文本。

        Args:
            messages: [{"role": "user|assistant", "content": "..."}]
            system: 系统提示词
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大 token 数
            on_stream: 可选流式回调，每收到一个 token 调用一次

        Returns:
            模型响应文本
        """
        if self._backend == "anthropic":
            return self._chat_anthropic(
                messages, system=system,
                temperature=temperature, max_tokens=max_tokens,
                on_stream=on_stream,
            )
        else:
            return self._chat_openai(
                messages, system=system,
                temperature=temperature, max_tokens=max_tokens,
                on_stream=on_stream,
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
    ) -> str:
        import anthropic

        # 提取 system 消息并单独传递（Anthropic API 要求）
        sys_msg = system or ""
        # 将 system 从 messages 中分离（如果有）
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

        if on_stream:
            kwargs["messages"] = anthropic_msgs
            with self._client.messages.stream(**kwargs) as stream:
                full = []
                for text in stream.text_stream:
                    full.append(text)
                    on_stream(text)
                return "".join(full)
        else:
            response = self._client.messages.create(
                messages=anthropic_msgs, **kwargs
            )
            return response.content[0].text

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
