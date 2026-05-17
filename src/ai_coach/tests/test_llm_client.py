"""LLM 配置单元测试"""
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai_coach.llm_client import LLMConfig
from ai_coach.config import AppConfig, LLMProviderConfig


class TestLLMConfig:
    """LLMConfig 构建和 from_app_config 工厂方法"""

    def test_default_config(self):
        cfg = LLMConfig()
        assert cfg.base_url == "https://api.deepseek.com/anthropic"
        assert cfg.model == "deepseek-v4-pro"
        assert cfg.max_tokens == 4096

    def test_from_app_config_deepseek(self):
        ac = AppConfig()
        ac.llm.provider = "deepseek"
        ac.llm.api_key = "sk-test"
        cfg = LLMConfig.from_app_config(ac)
        assert cfg.base_url == "https://api.deepseek.com/anthropic"
        assert cfg.model == "deepseek-v4-pro"
        assert cfg.api_key == "sk-test"

    def test_from_app_config_anthropic(self):
        ac = AppConfig()
        ac.llm.provider = "anthropic"
        ac.llm.api_key = "sk-ant-test"
        cfg = LLMConfig.from_app_config(ac)
        assert cfg.base_url == "https://api.anthropic.com"
        assert cfg.model == "claude-sonnet-4-6"

    def test_from_app_config_openai(self):
        ac = AppConfig()
        ac.llm.provider = "openai"
        ac.llm.api_key = "sk-oai-test"
        cfg = LLMConfig.from_app_config(ac)
        assert cfg.base_url == "https://api.openai.com/v1"
        assert cfg.model == "gpt-4o"

    def test_from_app_config_custom_model(self):
        ac = AppConfig()
        ac.llm.provider = "deepseek"
        ac.llm.model = "custom-model-v2"
        cfg = LLMConfig.from_app_config(ac)
        assert cfg.model == "custom-model-v2"

    def test_from_app_config_custom_base_url(self):
        ac = AppConfig()
        ac.llm.provider = "custom"
        ac.llm.base_url = "https://my-proxy.example.com/v1"
        cfg = LLMConfig.from_app_config(ac)
        assert cfg.base_url == "https://my-proxy.example.com/v1"

    def test_from_app_config_max_tokens(self):
        ac = AppConfig()
        ac.llm.max_tokens = 16384
        cfg = LLMConfig.from_app_config(ac)
        assert cfg.max_tokens == 16384

    def test_from_app_config_temperature(self):
        ac = AppConfig()
        ac.llm.temperature = 0.3
        cfg = LLMConfig.from_app_config(ac)
        assert cfg.temperature == 0.3
