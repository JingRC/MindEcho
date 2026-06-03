---
name: python-engineering
description: >
  MindEcho Python 工程化开发：启动应用、运行测试、依赖管理、代码规范。
  Python 3.7+ 项目，主 GUI 为 PyQt6/PyQt5，音频处理基于 sounddevice+numpy+scipy。
  Triggers: "启动项目", "运行测试", "安装依赖", "检查代码", "Python 版本兼容"
user-invocable: true
argument-hint: "[start|test|deps|lint|check|analyze]"
allowed-tools: Bash(python *), Bash(pip *), Read, Edit, Grep, Glob
---

# Python Engineering for MindEcho

## 启动应用

```bash
# 直接启动主界面（最简单）
python main.py

# 菜单式启动器（多模式：增强版/标准版/简化版/测试）
python run_enhanced.py
```

## 依赖管理

```bash
# 核心依赖（必需）
pip install numpy scipy sounddevice matplotlib PyQt6

# ML 可选依赖（人声分离、模型推理）
pip install -r requirements-optional.txt

# 检查所有核心导入是否正常
python -c "
from src.audio_processing.recorder import AudioRecorder
from src.analysis.pitch_detection import PitchDetector
from src.ai_coach import VocalCoachAgent
print('All core imports OK')
"
```

## 运行测试

此项目没有 pytest/unittest 框架。测试是独立的 .py 脚本：

```bash
# 基础功能验证
python test_mindecho.py

# 运行单个测试脚本（根目录有 ~250 个 test_*.py）
python test_pitch_detection.py
python test_recording.py
python test_visualization.py

# AI Coach 模块测试
python -m pytest src/ai_coach/tests/ -v 2>/dev/null || \
  python src/ai_coach/tests/test_llm_client.py
```

## 代码质量检查（无正式 linting 配置）

```bash
# PEP 8 风格检查（如果安装了 flake8）
pip install flake8
flake8 src/ --select=E,F,W --max-line-length=120

# 快速语法检查所有源文件
python -m compileall src/ -q 2>&1 | head -20
```

## 项目特点需注意

1. **中文注释和 UI**：所有注释、docstring、用户界面均为中文。变量名和函数名使用英文。
2. **主 GUI 是巨石文件**：`src/gui/integrated_recording_interface.py` (~80,000 行) 需谨慎修改，改动前先运行 `/genskills--refactor` 评估风险。
3. **Python 版本兼容**：代码需兼容 3.7+，但部分新模块使用 `from __future__ import annotations`。
4. **多 GUI 框架降级链**：PyQt6 → PyQt5 → tkinter。导入失败时自动回退。
5. **Windows 优先**：多数开发在 Windows 上进行，Unix 路径和编码需额外注意。
6. **音频管线性能**：不要修改音频管线的帧率/hop_size 来优化 UI 性能 — 视觉实时感应通过可视化层优化（见 `[[feedback_throttle_pipeline]]`）。
7. **matplotlib 限制**：不要用 matplotlib 做高频实时渲染，用 PyQtGraph 或直接 QPainter（见 `[[feedback_matplotlib_optimization]]`）。
