"""应用配置管理 —— 用户配置的加载、保存和迁移"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .identity import CoachIdentity, DEFAULT_IDENTITY


# ── 数据结构 ──────────────────────────────────────────────────

@dataclass
class LLMProviderConfig:
    """LLM 提供商配置"""
    provider: str = "deepseek"      # anthropic | openai | deepseek | custom
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7

    def to_dict(self) -> dict:
        d = asdict(self)
        # 混淆 api_key（非安全加密，仅防明文泄露）
        if d.get("api_key") and not d["api_key"].startswith("obf:"):
            try:
                d["api_key"] = "obf:" + base64.b64encode(
                    d["api_key"].encode("utf-8")
                ).decode("utf-8")
            except Exception:
                pass
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LLMProviderConfig":
        api_key = data.get("api_key", "")
        if api_key.startswith("obf:"):
            try:
                api_key = base64.b64decode(
                    api_key[4:].encode("utf-8")
                ).decode("utf-8")
            except Exception:
                api_key = ""
        return cls(
            provider=data.get("provider", "deepseek"),
            api_key=api_key,
            base_url=data.get("base_url", ""),
            model=data.get("model", ""),
            max_tokens=data.get("max_tokens", 4096),
            temperature=data.get("temperature", 0.7),
        )


@dataclass
class AppConfig:
    """应用总配置"""
    llm: LLMProviderConfig = field(default_factory=LLMProviderConfig)
    identity: CoachIdentity = field(default_factory=lambda: DEFAULT_IDENTITY)
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "llm": self.llm.to_dict(),
            "identity": asdict(self.identity),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        llm_data = data.get("llm", {})
        identity_data = data.get("identity", {})
        return cls(
            version=data.get("version", 1),
            llm=LLMProviderConfig.from_dict(llm_data),
            identity=CoachIdentity(**{
                k: v for k, v in identity_data.items()
                if k in CoachIdentity.__dataclass_fields__
            }) if identity_data else DEFAULT_IDENTITY,
        )


# ── 配置管理器 ────────────────────────────────────────────────

class ConfigManager:
    """管理 ~/.mindecho/config.json 的读写和迁移"""

    _CONFIG_FILENAME = "config.json"

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path.home() / ".mindecho"
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._config_path = self._dir / self._CONFIG_FILENAME

    # ── 加载 / 保存 ──────────────────────────────────────────

    def load(self) -> AppConfig:
        """加载配置，优先用户配置，回退模板，最后用默认值。"""
        # 1. 用户配置
        if self._config_path.exists():
            try:
                data = json.loads(self._config_path.read_text(encoding="utf-8"))
                return AppConfig.from_dict(data)
            except Exception:
                pass

        # 2. 模板文件：优先 data_dir 内，再查安装目录
        for template_path in (
            self._dir / "config.template.json",
            Path(os.getcwd()) / "config.template.json",
        ):
            if template_path.exists():
                try:
                    data = json.loads(template_path.read_text(encoding="utf-8"))
                    config = AppConfig.from_dict(data)
                    # 模板中的 api_key 应为空
                    config.llm.api_key = ""
                    return config
                except Exception:
                    pass

        # 3. 兜底默认值 + 尝试从旧 Claude Code settings 迁移
        config = AppConfig()
        self._migrate_from_claude_settings(config)
        return config

    def save(self, config: AppConfig):
        """保存配置到用户目录（原子写入）。"""
        text = json.dumps(config.to_dict(), ensure_ascii=False, indent=2)
        tmp = self._config_path.with_suffix(self._config_path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self._config_path)

    # ── 迁移 ─────────────────────────────────────────────────

    def _migrate_from_claude_settings(self, config: AppConfig):
        """从 Claude Code 的 settings.json 迁移 API 配置（仅首次）。"""
        if config.llm.api_key and config.llm.base_url:
            return  # 已配置，无需迁移

        settings_paths = [
            Path.home() / ".claude" / "settings.json",
            Path(os.getcwd()) / ".claude" / "settings.json",
        ]
        for sp in settings_paths:
            try:
                if sp.exists():
                    data = json.loads(sp.read_text(encoding="utf-8"))
                    env = data.get("env", {})
                    api_key = env.get("ANTHROPIC_AUTH_TOKEN", "")
                    base_url = env.get("ANTHROPIC_BASE_URL", "")
                    model = env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
                    if api_key:
                        config.llm.api_key = api_key
                    if base_url:
                        config.llm.base_url = base_url
                    if model:
                        config.llm.model = model
                    if api_key or base_url:
                        # 保存迁移后的配置
                        self.save(config)
                    return
            except Exception:
                pass

    # ── 便捷方法 ─────────────────────────────────────────────

    def try_migrate(self) -> Optional[AppConfig]:
        """如果用户配置不存在但存在旧格式，自动迁移并返回配置。"""
        if self._config_path.exists():
            return None  # 已有配置，不覆盖

        config = AppConfig()
        old_migrated = False

        settings_paths = [
            Path.home() / ".claude" / "settings.json",
            Path(os.getcwd()) / ".claude" / "settings.json",
        ]
        for sp in settings_paths:
            try:
                if sp.exists():
                    data = json.loads(sp.read_text(encoding="utf-8"))
                    env = data.get("env", {})
                    if env.get("ANTHROPIC_AUTH_TOKEN"):
                        config.llm.api_key = env["ANTHROPIC_AUTH_TOKEN"]
                        config.llm.base_url = env.get("ANTHROPIC_BASE_URL", "")
                        config.llm.model = env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
                        old_migrated = True
                    break
            except Exception:
                pass

        if old_migrated:
            self.save(config)
            return config
        return None
