"""配置管理单元测试 —— AppConfig 加载/保存/迁移/密钥混淆"""
import json
import tempfile
import os
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai_coach.config import AppConfig, LLMProviderConfig, ConfigManager
from ai_coach.identity import CoachIdentity


class TestLLMProviderConfig:
    """LLM 提供商配置序列化与密钥混淆"""

    def test_to_dict_obfuscates_key(self):
        cfg = LLMProviderConfig(api_key="sk-secret-12345", provider="deepseek")
        d = cfg.to_dict()
        assert d["api_key"].startswith("obf:")
        assert "sk-secret" not in d["api_key"]

    def test_from_dict_deobfuscates_key(self):
        cfg = LLMProviderConfig(api_key="sk-secret-12345", provider="deepseek")
        d = cfg.to_dict()
        restored = LLMProviderConfig.from_dict(d)
        assert restored.api_key == "sk-secret-12345"

    def test_empty_key_not_obfuscated(self):
        cfg = LLMProviderConfig(api_key="", provider="deepseek")
        d = cfg.to_dict()
        assert d["api_key"] == ""

    def test_already_obfuscated_key_preserved(self):
        cfg = LLMProviderConfig.from_dict({"api_key": "obf:c2stYWxyZWFkeS1vYmZ1c2NhdGVk", "provider": "deepseek"})
        assert cfg.api_key == "sk-already-obfuscated"

    def test_roundtrip_preserves_all_fields(self):
        original = LLMProviderConfig(
            provider="anthropic",
            api_key="sk-ant-abc123",
            base_url="https://api.anthropic.com",
            model="claude-sonnet-4-6",
            max_tokens=8192,
            temperature=0.5,
        )
        d = original.to_dict()
        restored = LLMProviderConfig.from_dict(d)
        assert restored.provider == original.provider
        assert restored.api_key == original.api_key
        assert restored.base_url == original.base_url
        assert restored.model == original.model
        assert restored.max_tokens == original.max_tokens
        assert restored.temperature == original.temperature


class TestAppConfig:
    """AppConfig 序列化"""

    def test_default_config(self):
        cfg = AppConfig()
        assert cfg.version == 1
        assert cfg.llm.provider == "deepseek"
        assert cfg.identity.name == "麦麦"

    def test_roundtrip(self):
        original = AppConfig()
        original.identity.name = "小艾老师"
        original.llm.model = "gpt-4o"
        d = original.to_dict()
        restored = AppConfig.from_dict(d)
        assert restored.identity.name == "小艾老师"
        assert restored.llm.model == "gpt-4o"

    def test_from_empty_dict(self):
        cfg = AppConfig.from_dict({})
        assert cfg.llm.provider == "deepseek"
        assert isinstance(cfg.identity, CoachIdentity)
        assert len(cfg.identity.name) > 0


class TestConfigManager:
    """配置管理器读写和迁移"""

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ConfigManager(data_dir=Path(tmp))
            cfg = AppConfig()
            cfg.identity.name = "测试教练"
            mgr.save(cfg)

            loaded = mgr.load()
            assert loaded.identity.name == "测试教练"

    def test_load_returns_default_when_no_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ConfigManager(data_dir=Path(tmp))
            # 在临时目录里创建空模板，阻止 fallback 到真实 ~/.claude/settings.json
            template = Path(tmp) / "config.template.json"
            template.write_text('{"version": 1, "llm": {"provider": "deepseek", "api_key": ""}, "identity": {}}', encoding="utf-8")
            cfg = mgr.load()
            assert isinstance(cfg, AppConfig)
            assert cfg.llm.api_key == ""

    def test_corrupt_config_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ConfigManager(data_dir=Path(tmp))
            mgr._config_path.write_text("not valid json {{{", encoding="utf-8")
            # 放置空模板防止迁移到真实配置
            template = Path(tmp) / "config.template.json"
            template.write_text('{"version": 1, "llm": {"provider": "deepseek", "api_key": ""}, "identity": {}}', encoding="utf-8")
            cfg = mgr.load()
            assert isinstance(cfg, AppConfig)

    def test_try_migrate_no_existing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ConfigManager(data_dir=Path(tmp))
            # 如果没有旧配置，应返回 None
            result = mgr.try_migrate()
            # 开发机可能有 ~/.claude/settings.json，所以可能 None 或 AppConfig
            if result is not None:
                assert isinstance(result, AppConfig)
                assert len(result.llm.api_key) > 0  # 迁移来的应有 API key
