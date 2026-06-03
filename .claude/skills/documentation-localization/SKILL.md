---
name: documentation-localization
description: >
  中英双语文档翻译与维护。MindEcho 的代码注释和 UI 为中文，此技能帮助翻译文档、
  生成双语 README、确保翻译不破坏代码块和技术术语。
  Triggers: "翻译文档", "中英双语", "i18n", "本地化", "translate docs"
user-invocable: true
argument-hint: "[file] [--direction zh2en|en2zh|both] [--output <path>]"
allowed-tools: Read, Write, Edit, Glob, Grep
---

# Documentation Localization for MindEcho

## 翻译规则

### 保留不译
- **代码块** (```python ... ```)：完整保留
- **CLI 命令**：完整保留 (`python main.py`, `pip install numpy`)
- **文件路径**：完整保留 (`src/gui/integrated_recording_interface.py`)
- **变量名/函数名/类名**：完整保留 (`AudioRecorder`, `PitchDetector`)
- **技术术语对照**（保持一致性）：
  - 音高检测 → pitch detection
  - 五线谱 → staff notation
  - 声乐教练 → vocal coach
  - 人声分离 → vocal separation
  - 降噪 → noise reduction

### 翻译输出格式
生成的翻译文档命名规则：`<原名>_zh.md`（中文）或 `<原名>_en.md`（英文）

## 常用命令

```bash
# 将英文文档翻译为中文
/documentation-localization docs/user_guide.md --direction en2zh

# 将中文文档翻译为英文
/documentation-localization README.md --direction zh2en

# 生成中英双语版本
/documentation-localization docs/user_guide.md --direction both

# 扫描并翻译所有 .md 文件中的中文注释
/documentation-localization docs/ --direction zh2en --output docs/en/
```
