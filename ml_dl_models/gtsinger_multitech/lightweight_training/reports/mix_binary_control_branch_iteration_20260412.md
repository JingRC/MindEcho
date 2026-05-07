# Mix Binary Control Branch Iteration 2026-04-12

## Goal

前一轮已经把多窗口输出层优化基本证伪：

- simple mean 之外的连续 penalty 没有建立替换优势
- 单级 / 二级 support gate 也没有把 `control_negative` 压到可替换水平

因此这一轮改成直接处理当前最明确的根因：

1. `control-like non-mix` 定向 hard-negative
2. 如果单模型数据修补不够，再试二阶段 control suppressor

## Code Changes

这一轮新增了两类能力：

### 1. Control-oriented dataset mining

`prepare_mix_binary_manifests.py` 已支持：

- `control_selection_mode=hardest_by_artifact`
- 使用现有 artifact 对 `Control_Group` 打分
- 按 `mined_mix_prob` 选择最像 mix 的 control negatives

这使得后续可以复用同一套 manifest 生成逻辑去做：

- control-hard binary 训练集
- control-only suppressor 训练集

### 2. Two-stage evaluation tooling

新增脚本：

- `compare_mix_binary_with_control_suppressor.py`
- `calibrate_mix_binary_control_suppressor.py`

用途分别是：

1. 在同一 manifest 上评估 `primary mix model + control suppressor`
2. 在 in-domain validation 上扫描 suppressor threshold，再把最佳阈值应用到 test

两个脚本都支持：

- 共享预处理缓存前提下的双模型一次前向
- 复用现有 artifact 的多窗口配置
- 直接输出 binary-role summary

## Dataset Generation

### A. Control-hard retraining dataset

Dataset:

- `dataset/curated/mix_binary_controlhard_v1`

Mining base artifact:

- `mix_binary_hardneg_v2_gpu`

3-window mean 打分后，control negatives 的 `mined_mix_prob` 很尖：

- train mean `0.733456`
- validation mean `0.725617`
- test mean `0.712586`

这说明它确实抓到了“最像 mix 的 control”。

### B. Control-only suppressor dataset

Dataset:

- `dataset/curated/mix_control_only_v1`

组成：

- `positive_mix`
- `control_negative`

split 基本均衡：

- train `1131 / 1131`
- validation `141 / 141`
- test `143 / 143`

## Experiment 1: Data-only Control-Hard Retraining

Quick candidate:

- `mix_binary_controlhard_v1_mean3_e4_gpu`

训练只做 4 个 head epoch，目的是快速筛掉明显坏方向。

### Own validation / test shape

- best validation balanced_acc `0.659233`
- own test balanced_acc `0.608657`

这时模型就已经不稳。

### Core test same-manifest result

Manifest:

- `dataset/curated/mix_binary_core/test_manifest.csv`

Binary-role result:

| artifact | positive_mix | control_negative | falsetto_group | breathy_group | balanced_acc |
| --- | ---: | ---: | ---: | ---: | ---: |
| `mix_binary_controlhard_v1_mean3_e4_gpu` | 0.650350 | 0.810127 | 0.253165 | 0.170732 | 0.563473 |

## Decision on Control-Hard Retraining

这条路在当前实现下可以直接判死：

1. `control_negative` 被严重击穿
2. `overall / balanced_acc` 同时明显崩掉
3. 说明“只换成最硬 control negatives”会把边界整体抬歪，而不是定向修正 control 通道

因此它不适合作为下一轮主方向。

## Experiment 2: Control-Only Suppressor Training

Quick suppressor candidate:

- `mix_control_only_v1_mean3_e4_gpu`

Training result:

- best validation balanced_acc `0.741135`
- best threshold `0.575`
- own test balanced_acc `0.716783`

从 suppressor 自己的 control-only split 看，它是一个健康模型。

问题在于：

- 它能否作为二阶段过滤器泛化到完整 mix domain

## Experiment 3: Direct Two-Stage Test at Suppressor Threshold 0.575

### Raw primary: `mix_binary_hardneg_v2_gpu` + suppressor

统一设置：

- core test manifest
- 3-window mean
- primary threshold `0.425`
- suppressor threshold `0.575`

| mode | positive_mix | control_negative | falsetto_group | breathy_group | balanced_acc |
| --- | ---: | ---: | ---: | ---: | ---: |
| primary only | 0.720280 | 0.329114 | 0.037975 | 0.243902 | 0.734608 |
| primary + suppressor | 0.461538 | 0.253165 | 0.037975 | 0.024390 | 0.662684 |

观察：

- `breathy_group` 被明显压下去
- `control_negative` 也略有改善
- 但 `positive_mix` 从 `0.720` 直接掉到 `0.462`

也就是说 suppressor 一旦真正开始工作，过抑制非常明显。

### Guarded primary: `mix_binary_hardneg_v2_3win_guarded_gpu` + suppressor

统一设置：

- core test manifest
- 3-window mean
- primary threshold `0.45`
- suppressor threshold `0.575`

| mode | positive_mix | control_negative | falsetto_group | breathy_group | balanced_acc |
| --- | ---: | ---: | ---: | ---: | ---: |
| primary only | 0.657343 | 0.265823 | 0.025316 | 0.243902 | 0.718033 |
| primary + suppressor | 0.419580 | 0.202532 | 0.025316 | 0.024390 | 0.654471 |

观察基本完全一致：

- breathy 确实被强压
- control 也有一小步改善
- 但代价仍然是大幅吞掉 true mix

## Experiment 4: In-Domain Suppressor Threshold Calibration

为了排除“只是阈值没校好”的可能，又在原 `mix_binary_core/validation_manifest.csv` 上单独扫了 suppressor threshold，然后把 validation 最优阈值应用到 core test。

### Raw primary calibration result

Validation best threshold:

- `0.30`

Validation summary:

- primary only: `positive_mix 0.695 / control_negative 0.282 / breathy 0.102 / falsetto 0.090 / balanced_acc 0.737`
- best threshold: `0.688 / 0.282 / 0.102 / 0.090 / 0.734`

Core test after applying best validation threshold:

- 与 primary-only 完全同形
- `positive_mix 0.720 / control_negative 0.329 / breathy 0.244 / falsetto 0.038 / balanced_acc 0.735`

解释：

- 最优阈值已经退化到几乎不让 suppressor 生效
- 一旦让 suppressor 更积极，validation 指标立刻变差

### Guarded primary calibration result

Validation best threshold:

- `0.30`

Validation summary:

- primary only: `positive_mix 0.660 / control_negative 0.231 / breathy 0.061 / falsetto 0.090 / balanced_acc 0.736`
- best threshold: `0.652 / 0.231 / 0.061 / 0.090 / 0.732`

Core test after applying best validation threshold:

- 同样与 primary-only 完全同形
- `positive_mix 0.657 / control_negative 0.266 / breathy 0.244 / falsetto 0.025 / balanced_acc 0.718`

这把结论钉得很死：

- 不是 suppressor threshold 选错了
- 而是它在完整 mix domain 中没有形成“有效且不伤 recall”的工作区间

## Final Decision

当前 control 分支得出的结论是：

1. `control-hard retraining` 在当前做法下失败，而且是明显失败
2. `control-only suppressor` 在自己的二分类任务上能学会东西
3. 但一旦接到完整 mix domain 上，真正生效就会明显误杀 `positive_mix`
4. 如果按 in-domain validation 校准，最佳阈值会退化到几乎 no-op

因此：

- 当前不继续推进这条“二阶段 control suppressor”实现
- 软件 checkpoint 维持现状

## What This Round Proved

这轮实际证明的是：

- 当前 control 问题不是一个简单的后验过滤问题

如果它只是“主模型打分后再加一个 control filter”就能解决，那么 in-domain calibration 至少应该能找到一个小范围阈值，让：

- `control_negative` 或 `breathy_group` 明显下降
- 同时 `positive_mix` 只做温和让步

但现在看到的是：

1. suppressor 不动时，结果就是 primary-only
2. suppressor 一动，Mixed recall 就先掉穿

所以更合理的解释是：

- primary true mix 与 control-like non-mix 在 suppressor 特征空间里并没有被可靠分开
- 这个问题更像需要从训练分布或模型结构本体解决，而不是靠后接一个单独 head

## Recommended Next Direction

下一轮更值得做的是：

1. 回到 upstream negative curation，而不是继续后验 suppressor
2. 重新设计 control-like negatives，避免只保留“最硬 control”导致边界整体漂移
3. 如果还想走结构化路线，优先考虑显式 control-aware 多头模型 / reranker，而不是当前这种独立二阶段 hard gate