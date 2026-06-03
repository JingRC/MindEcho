---
name: coach-debug
description: >
  MindEcho AI Coach 调试：检查 LLM 调用链（context → prompt → response）、
  验证知识检索质量、检查记忆召回准确性、调试多后端 API 配置。
  Triggers: "调试 AI Coach", "检查 LLM 调用", "coach 不工作", "API 配置问题", "知识检索问题"
user-invocable: true
argument-hint: "[config|llm|knowledge|memory|session|context|all]"
allowed-tools: Read, Bash(python *), Grep, Glob, Write
---

# AI Coach Debug for MindEcho

## 配置检查

```bash
# 检查配置文件
python -c "
from src.ai_coach.config import ConfigManager
mgr = ConfigManager()
config = mgr.load()
print(f'Provider: {config.llm.provider}')
print(f'Model: {config.llm.model}')
print(f'Base URL: {config.llm.base_url}')
print(f'API Key set: {bool(config.llm.api_key)}')
print(f'Identity: {config.identity.character_name}')
"
```

## LLM 连通性测试

```bash
# 测试各后端连通性
python -c "
from src.ai_coach.llm_client import LLMClient, LLMConfig

# DeepSeek
try:
    client = LLMClient(LLMConfig(provider='deepseek'))
    resp = client.chat('Reply with just: OK')
    print(f'DeepSeek: OK ({len(resp)} chars)')
except Exception as e:
    print(f'DeepSeek FAILED: {e}')

# Anthropic (if configured)
try:
    client = LLMClient(LLMConfig(provider='anthropic'))
    resp = client.chat('Reply with just: OK')
    print(f'Anthropic: OK ({len(resp)} chars)')
except Exception as e:
    print(f'Anthropic FAILED: {e}')
"
```

## 知识库检索验证

```bash
# 测试知识检索
python -c "
from src.ai_coach.knowledge.retriever import KnowledgeRetriever, get_knowledge_store

store = get_knowledge_store()
retriever = KnowledgeRetriever(store)

# 关键词检索
results = retriever.search('胸声和假声的区别')
for r in results[:3]:
    print(f'  [{r.score:.2f}] {r.title}: {r.snippet[:80]}')

# 语义检索
results = retriever.search_semantic('如何提高高音')
for r in results[:3]:
    print(f'  [{r.score:.2f}] {r.title}: {r.snippet[:80]}')
"
```

## 记忆系统检查

```bash
# 查看记忆状态
python -c "
from src.ai_coach.memory import MemoryManager

mgr = MemoryManager()
entries = mgr.list_entries(limit=20)
print(f'Total entries: {len(entries)}')
for e in entries:
    print(f'  [{e.importance}] {e.title} (reviews: {e.review_count}, due: {e.next_review_at})')
"
```

## Context 构建调试

```bash
# 模拟一次完整的 context 构建
python -c "
from src.ai_coach.context.builder import ContextBuilder, SingingContext, PitchStats

builder = ContextBuilder()
ctx = SingingContext(
    pitch_stats=PitchStats(avg_freq=330, min_freq=220, max_freq=440),
    recent_notes=['E4', 'F4', 'G4'],
    session_duration_sec=60
)
summary = builder.build_analysis_context(ctx)
print(summary[:500])
"
```
