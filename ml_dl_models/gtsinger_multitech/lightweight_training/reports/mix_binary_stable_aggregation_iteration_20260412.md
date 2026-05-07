# Mix Binary Stable Aggregation Iteration 2026-04-12

## Goal

在上一轮多窗口实验中，3 窗简单平均已经证明对 `mix_binary_hardneg_v2_gpu` 有真实增益，但收益主要被 `control_negative` 的放大抵消。

本轮不再改训练数据，而是测试一个更定向的推理侧改动：

- 保留 3 窗覆盖
- 不再直接平均 3 个窗口 logits
- 改为使用更稳定的窗口聚合，优先抑制单个异常高窗

## Code Changes

本轮新增可配置聚合参数：

- `train_mix_binary_squeezenet.py`
  - `eval_window_aggregation`
  - `eval_window_consistency_penalty`
  - 支持聚合模式：`mean` / `mean_minus_std` / `median` / `trimmed_mean`
- `compare_mix_binary_checkpoints.py`
  - 可读取 artifact 内的聚合配置
  - 也可通过 CLI 覆盖聚合模式与 penalty
- `calibrate_mix_binary_artifact.py`
  - 可在后验阈值校准时一并覆盖聚合模式与 penalty
  - 校准结果会写回 artifact summary

默认行为仍保持原样：

- 单窗默认不变
- 多窗若未指定聚合，仍为 `mean`

## Validation Sweep

Artifact:

- `mix_binary_hardneg_v2_gpu`

Manifest:

- `dataset/curated/mix_binary_hardneg_v2/validation_manifest.csv`

统一设置：

- `eval_window_count = 3`

### Best unconstrained threshold by balanced_acc

| aggregation | penalty | threshold | balanced_acc | positive_mix | control_negative | breathy_group | falsetto_group |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mean | 0.00 | 0.400 | 0.774545 | 0.765957 | 0.357143 | 0.150000 | 0.091837 |
| mean_minus_std | 0.25 | 0.375 | 0.763907 | 0.744681 | 0.328571 | 0.183333 | 0.091837 |
| mean_minus_std | 0.50 | 0.375 | 0.758224 | 0.709220 | 0.314286 | 0.133333 | 0.071429 |
| mean_minus_std | 0.75 | 0.350 | 0.752670 | 0.702128 | 0.328571 | 0.133333 | 0.071429 |
| mean_minus_std | 1.00 | 0.350 | 0.728787 | 0.638298 | 0.285714 | 0.116667 | 0.071429 |
| median | 0.00 | 0.375 | 0.767709 | 0.808511 | 0.414286 | 0.233333 | 0.142857 |
| trimmed_mean | 0.00 | 0.375 | 0.767709 | 0.808511 | 0.414286 | 0.233333 | 0.142857 |

### Interpretation

1. `median` 和 `trimmed_mean` 在 3 窗场景下几乎等价，而且都把负类通道放大得过多，不适合作为下一步。
2. `mean_minus_std` 的确能降低 `control_negative / breathy_group / falsetto_group`，但 penalty 越大，`positive_mix` 也会同步下滑。
3. 在本次扫描中，原始 tight guarded 条件
   - `positive_mix >= 0.65`
   - `control_negative <= 0.26`
   - `breathy_group <= 0.10`
   - `falsetto_group <= 0.08`
   只有 simple `mean` 能在当前阈值网格里命中；`mean_minus_std` 没有直接产生更强的 dominate 点。

## New Stable Candidate

为了验证稳定聚合是否至少能改善 core test 上的 tradeoff，本轮额外构建了一个较宽松的稳定版候选：

- artifact: `mix_binary_hardneg_v2_3win_stable025_guarded_gpu`
- aggregation: `mean_minus_std`
- penalty: `0.25`
- validation constraints:
  - `positive_mix >= 0.65`
  - `control_negative <= 0.28`
  - `breathy_group <= 0.12`
  - `falsetto_group <= 0.08`
- calibrated threshold: `0.425`

Validation result:

- `balanced_acc = 0.739896`
- `positive_mix = 0.652482`
- `control_negative = 0.271429`
- `breathy_group = 0.116667`
- `falsetto_group = 0.071429`

## Core Test Comparison

Manifest:

- `dataset/curated/mix_binary_core/test_manifest.csv`

统一设置：

- `eval_window_count = 3`
- 不统一覆盖聚合方式，允许每个 artifact 使用自己的 summary 配置

### Key candidates

| artifact | aggregation | threshold | balanced_acc | positive_mix | control_negative | breathy_group | falsetto_group |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `mix_binary_ce_v2_calibrated_gpu` | mean | 0.450 | 0.710891 | 0.664336 | 0.215190 | 0.414634 | 0.101266 |
| `mix_binary_hardneg_v2_gpu` | mean | 0.425 | 0.734608 | 0.720280 | 0.329114 | 0.243902 | 0.037975 |
| `mix_binary_hardneg_v2_3win_guarded_gpu` | mean | 0.450 | 0.718033 | 0.657343 | 0.265823 | 0.243902 | 0.025316 |
| `mix_binary_hardneg_v2_3win_strict_gpu` | mean | 0.475 | 0.720458 | 0.615385 | 0.202532 | 0.195122 | 0.012658 |
| `mix_binary_hardneg_v2_3win_stable025_guarded_gpu` | mean_minus_std(0.25) | 0.425 | 0.717423 | 0.643357 | 0.253165 | 0.243902 | 0.012658 |

## Decision

`mix_binary_hardneg_v2_3win_stable025_guarded_gpu` 没有形成替换级优势：

- 相比 `mix_binary_hardneg_v2_3win_guarded_gpu`
  - `control_negative` 略降（`0.265823 -> 0.253165`）
  - `falsetto_group` 略降（`0.025316 -> 0.012658`）
  - `breathy_group` 基本不变（`0.243902`）
  - `positive_mix` 回退（`0.657343 -> 0.643357`）
  - `balanced_acc` 也略降（`0.718033 -> 0.717423`）
- 相比当前 baseline 3 窗
  - breathy / falsetto 明显更干净
  - 但 `positive_mix` 没有建立明显优势，`control_negative` 也仍高于 baseline

因此本轮结论仍然是：

- 不切换当前软件 checkpoint
- 稳定聚合是有帮助的局部修正，但还不足以单独解决多窗口下的 control 假阳性问题

## What This Clarified

这一轮把问题进一步收敛了：

1. 多窗口 simple mean 的问题确实包含“单个异常高窗”因素，因为 `mean_minus_std` 能把 control/falsetto 压下去。
2. 但当前 `mean_minus_std` 属于连续惩罚，不够选择性，压 control 的同时也压掉了部分真实 mix 召回。
3. 下一步更值得尝试的是离散式稳定门控，而不是更强的连续 penalty。

## Recommended Next Step

下一轮优先尝试：

1. 基于“稳定高窗个数”的门控聚合
   - 例如至少 2 个窗口达到弱 mix 支持，才允许整条样本维持较高 mix 判定
2. 只对单高窗样本做惩罚，而不是对所有多窗样本统一减 `std`
3. 保持 `mean_minus_std` 代码路径作为可用对照组，但不作为当前主候选