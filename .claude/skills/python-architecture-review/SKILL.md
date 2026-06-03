---
name: python-architecture-review
description: >
  MindEcho 架构审查：子系统耦合度、模块职责划分、接口设计、大文件拆分建议。
  Triggers: "架构审查", "代码结构分析", "模块拆分", "重构建议", "系统设计评审"
user-invocable: true
argument-hint: "[subsystem: gui|audio|ai_coach|ml|lead_backing|all]"
allowed-tools: Read, Grep, Glob, Bash(python *), Bash(wc *), Bash(find *)
---

# Python Architecture Review for MindEcho

对 MindEcho 子系统进行多维度架构审查。

## 审查维度

对目标子系统，按以下维度打分（1-5）并给出具体建议：

1. **单一职责** — 每个模块/类是否只有一个变更理由
2. **耦合度** — 模块间依赖是否合理，是否有循环依赖
3. **接口设计** — 公共 API 是否清晰、稳定
4. **代码复用** — 是否有重复代码或可提取的共享逻辑
5. **可测试性** — 模块是否可独立测试，是否依赖全局状态
6. **错误处理** — 异常处理是否一致、完整
7. **配置管理** — 硬编码 vs 可配置参数
8. **性能瓶颈** — 识别潜在的性能/内存问题
9. **扩展性** — 添加新功能是否需要大面积修改
10. **文档与命名** — 中文注释是否与代码逻辑一致，命名是否自解释

## 各子系统审查重点

### GUI (`src/gui/`)
- 重点：`integrated_recording_interface.py` 的拆分策略
- 检查可视化引擎之间的重复代码（ecg/hybrid/pyqtgraph/improved_matplotlib）
- 评估 zoom/scroll/annotation 系统是否可提取为独立组件
- 检查信号/槽连接是否有内存泄漏风险

### 音频处理 (`src/audio_processing/`)
- 审查 AudioRecorder → NoiseReduction → PitchDetection 的数据流
- 检查 GPU 加速路径与 CPU 回退路径的一致性和覆盖
- 评估 PerformanceManager 三档模式的实际差异

### AI Coach (`src/ai_coach/`)
- LLMClient 多后端适配是否容易添加新 provider
- ContextBuilder 的 prompt 构建是否与模型耦合过紧
- Knowledge/Memory/Session 三者的依赖关系是否合理
- 检查 API key 管理和配置安全性

### 人声分离 (`src/audio_processing/lead_backing/`)
- Pipeline 各阶段的错误传播和回退策略
- 实时调度的延迟和缓冲区管理

### ML 模型 (`ml_dl_models/`)
- 模型加载/推理的生命周期管理
- 训练和推理代码的分离程度

## 执行方式

```bash
# 分析文件大小分布，识别拆分候选
find src/ -name "*.py" -exec wc -l {} + | sort -rn | head -20

# 检查模块间导入依赖
grep -r "^from\|^import" src/ai_coach/ --include="*.py" | grep -v "__pycache__" | sort | uniq -c | sort -rn | head -30

# 查找循环导入风险
python -c "
import ast, sys
# 简单 AST 分析...
print('检查完成')
"
```
