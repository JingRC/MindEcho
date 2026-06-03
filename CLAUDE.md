# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

MindEcho 是一个中文智能音频录制与分析系统（歌唱教练），集成了实时音高检测、五线谱可视化、AI 声乐教练、ML 发声技术分类和人声/伴奏分离等功能。

## 启动 & 运行

```bash
# 直接启动主界面（推荐）
python main.py

# 菜单式启动器（多模式选择）
python run_enhanced.py

# 安装核心依赖
pip install numpy scipy sounddevice matplotlib PyQt6

# 安装可选 ML 依赖（人声分离、模型推理）
pip install -r requirements-optional.txt
```

项目没有正式的测试框架。根目录下约 250+ 个独立 `test_*.py` 脚本各自验证不同功能，用 `python test_xxx.py` 单独运行。

## 核心架构

### 音频管线（实时处理链路）

```
麦克风输入 → AudioRecorder (sounddevice.InputStream 回调)
  → 噪声过滤 (NoiseReductionProcessor, 频谱减法+陷波+自适应)
  → 音高检测 (PitchDetectionService, YIN 算法为主)
  → 可视化渲染 (ECG曲线 / 五线谱 / 彩色渐变 / PyQtGraph)
```

- **`src/audio_processing/recorder.py`** — `AudioRecorder`: 非阻塞音频流捕获，队列线程间传递
- **`src/audio_processing/pitch_service.py`** — `PitchDetectionService`: YIN 算法的统一入口，带可配置阈值
- **`src/analysis/pitch_detection.py`** — `PitchDetector`: YIN / 自相关 / FFT 三种算法实现，MIDI音符转换（频率↔音符名↔cents偏差）
- **`src/audio_processing/noise_reduction.py`** — `NoiseReductionProcessor`: 多模式降噪（频谱减法、陷波滤波50/60Hz、音乐谐波保护、瞬态保留）
- **`src/audio_processing/performance_manager.py`** — 三个性能档位：QUIET / BALANCED / HIGH_PERFORMANCE

### GUI 架构（最大的技术债）

- **`src/gui/integrated_recording_interface.py`** (~80,000 行) — **单体巨石文件**，集成了所有 GUI 功能：ECG 可视化、zoom/scroll 系统、控制面板、录音管理、AI Coach 面板嵌入
- 多种可视化引擎共存：`ecg_pitch_visualizer.py`、`hybrid_visualizer.py`、`pyqtgraph_visualizer.py`、`improved_matplotlib_visualizer.py`
- GUI 框架链：PyQt6 → PyQt5 → tkinter（自动降级）
- **历史教训**：matplotlib 不适合高频实时渲染，PyQtGraph 性能更优但不能完全替代（见 memory: `[[feedback_matplotlib_optimization]]`）

### AI Coach 子系统 (`src/ai_coach/`)

```
VocalCoachAgent（主编排器）
  ├── LLMClient（多后端：DeepSeek / Anthropic / OpenAI / Ollama）
  ├── ContextBuilder（将 PitchStats → LLM-readable 上下文）
  ├── Prompt Templates（analysis / comparison / qa / practice_plan 模板 + intent 检测）
  ├── KnowledgeStore + KnowledgeRetriever（YAML 知识库 + ChromaDB 向量检索）
  ├── MemoryManager（艾宾浩斯遗忘曲线权重记忆系统）
  ├── SessionManager（用户画像、练习历史追踪）
  ├── PitchComparer + ReportGenerator（Markdown/HTML 分析报告）
  ├── WebSearchProvider（联网搜索补充）
  └── CoachIdentity（5 个角色 × 20 个主题配色 + SVG 吉祥物）
```

- **`src/ai_coach/llm_client.py`** — 统一适配 Anthropic/OpenAI/DeepSeek/Ollama API，支持指数退避重试。默认使用 DeepSeek（`api.deepseek.com/anthropic` endpoint）
- **`src/ai_coach/config.py`** — `ConfigManager` 管理 `~/.mindecho/config.json`，含 api_key 的 base64 混淆存储和从 Claude Code settings 自动迁移
- **`src/ai_coach/context/builder.py`** — 将音高数据转为 `SingingContext`（含 PitchStats、TechniqueSummary），是 LLM 提示工程的核心
- **`src/ai_coach/knowledge/`** — YAML 结构化声乐课程（fundamentals.yaml、techniques.yaml、health_practice.yaml），支持关键词 + 语义向量混合检索
- **`src/ai_coach/memory/`** — 长期记忆系统，基于艾宾浩斯曲线的复习调度和重要性评分

### 人声/伴奏分离 (`src/audio_processing/lead_backing/`)

`LeadBackingPipeline` 编排 Stage2 分离管线：使用 Demucs（PyTorch）或 Spleeter（TensorFlow，通过 `tools/spleeter_bridge.py`）进行人声内部的主唱/和声分离。

- opt-in 模式，默认 pass-through
- 近实时分块调度（`realtime_chunk_scheduler.py`）
- 声纹嵌入选择主唱轨（`singer_embedding.py`）

### ML 模型 (`ml_dl_models/`)

- **chest_falsetto/** — SqueezeNet 二分类/四分类，胸声 vs 假声检测，mel-spectrogram 输入 @22050Hz
- **gtsinger_multitech/** — EfficientNet/SqueezeNet 多技术分类（混声、气息检测），late fusion 架构

## 关键设计约定

- **配置存储**: `~/.mindecho/config.json`（不提交到 git）
- **录音输出**: `recordings/`（在 .gitignore 中）
- **预训练模型**: `pretrained_models/`（在 .gitignore 中）
- **外部工具 venv**: `tools/.venv_spleeter310/`（Spleeter 的独立 Python 3.10 环境）
- **FFmpeg**: 捆绑在 `tools/ffmpeg/bin/`
- **语言**: 代码注释和用户界面均为中文；变量名/函数名为英文
- **平台**: Windows 优先，跨平台兼容（macOS/Linux 理论上可运行）
- **实时感原则**: 视觉实时感应从视觉层优化（雪花效果等），不能动音频管线帧率/hop 来降延迟（见 memory: `[[feedback_throttle_pipeline]]`）

## 注意

- 根目录下 ~250 个 `test_*.py` 文件是独立调试脚本，不是结构化测试，`test_mindecho.py` 也只是手动功能验证
- `_github_release/` 是独立 git 仓库，用于 GitHub Release 打包
- 项目无 CI/CD、无 linting 配置、无类型检查配置
