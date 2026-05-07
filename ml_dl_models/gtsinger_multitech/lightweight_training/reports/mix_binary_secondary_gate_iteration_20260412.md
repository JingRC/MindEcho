# Mix Binary Secondary Gate Iteration 2026-04-12

## Goal

在上一轮单级 `support_gate` 之后，问题已经收敛得很明确：

- 单级离散门控能改形状
- 但还不足以把 `control_negative` 压到可替换水平

因此本轮不再做一般性阈值微调，而是直接验证两个二级 gate 变体：

1. `support_gate_conservative`
   - `2-of-3` 通过后，不直接取全均值
   - 改为取 `min(全均值, 支持窗均值)`
2. `support_gate_dual`
   - 维持 `2-of-3` 弱支持门槛
   - 额外要求至少 1 个窗口达到更高支持档

## Code Changes

新增聚合模式：

- `support_gate_conservative`
- `support_gate_dual`

新增参数：

- `eval_window_high_support_threshold`
- `eval_window_min_high_support_windows`

这些参数已经接入：

- `train_mix_binary_squeezenet.py`
- `compare_mix_binary_checkpoints.py`
- `calibrate_mix_binary_artifact.py`

## Validation Screening

Base artifact:

- `mix_binary_hardneg_v2_gpu`

Manifest:

- `dataset/curated/mix_binary_hardneg_v2/validation_manifest.csv`

统一设置：

- `eval_window_count = 3`
- 主弱支持门槛：`0.45 x 2`

### Variant A: `support_gate_conservative`

Validation result at artifact threshold `0.425`:

- `positive_mix = 0.666667`
- `control_negative = 0.271429`
- `breathy_group = 0.116667`
- `falsetto_group = 0.071429`
- `balanced_acc = 0.746988`

这组指标与上一轮单级 `support_gate 0.45 x 2` 基本一致，说明：

- 在当前样本分布下，`min(全均值, 支持窗均值)` 几乎没有产生新的约束效果
- 因此它没有继续进入 core test 阶段

### Variant B: `support_gate_dual`

Validation setup:

- weak support: `0.45 x 2`
- high support: `0.55 x 1`

Validation result at artifact threshold `0.425`:

- `positive_mix = 0.687943`
- `control_negative = 0.285714`
- `breathy_group = 0.116667`
- `falsetto_group = 0.071429`
- `balanced_acc = 0.755618`

解释：

- 相比单级 `support_gate 0.45 x 2`，dual gate 在 validation 上更激进一些
- `positive_mix` 提升明显
- 但 `control_negative` 也同步回升

它仍然像一个值得上 core test 的候选，因此被保留下来。

## New Candidate

Artifact:

- `mix_binary_hardneg_v2_3win_supportgate_dual45x2_hi55x1_guarded_gpu`

Validation constraints:

- `positive_mix >= 0.68`
- `control_negative <= 0.29`
- `breathy_group <= 0.12`
- `falsetto_group <= 0.08`

Calibration result:

- `threshold = 0.425`
- 说明当前 candidate 的最优可行点仍落在原始阈值附近

## Core Test Comparison

Manifest:

- `dataset/curated/mix_binary_core/test_manifest.csv`

对比对象：

- `mix_binary_ce_v2_calibrated_gpu`
- `mix_binary_hardneg_v2_3win_guarded_gpu`
- `mix_binary_hardneg_v2_3win_strict_gpu`
- `mix_binary_hardneg_v2_3win_supportgate_dual45x2_hi55x1_guarded_gpu`

### Key binary-role metrics

| artifact | positive_mix | control_negative | breathy_group | falsetto_group | balanced_acc |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline 3-win | 0.664336 | 0.215190 | 0.414634 | 0.101266 | 0.710891 |
| mean guarded | 0.657343 | 0.265823 | 0.243902 | 0.025316 | 0.718033 |
| mean strict | 0.615385 | 0.202532 | 0.195122 | 0.012658 | 0.720458 |
| dual gate 0.45x2 + 0.55x1 | 0.664336 | 0.291139 | 0.243902 | 0.075949 | 0.706636 |

## Decision

`support_gate_dual` 没有形成替换优势，结论比上一轮更明确：

1. 它把 recall 拉回到接近 baseline 的水平
2. 但 `control_negative` 明显高于 baseline、guarded、strict
3. `falsetto_group` 也明显高于 guarded 与 strict
4. 整体 `balanced_acc` 甚至低于 baseline 3-window

因此：

- 当前软件仍保持现有 checkpoint
- 二级门控这条分支先到此为止，不继续深挖同类轻规则变体

## What This Round Proved

这轮把一个关键判断彻底坐实了：

- 仅靠输出层的多窗 gate 逻辑，已经很难再把当前模型推进到“可替换产品 checkpoint”的程度

原因是：

1. 只要 recall 被拉回，`control_negative` 就跟着回升
2. 只要 control 被压住，Mixed recall 就重新掉回 guarded/strict 的旧区间

这说明当前瓶颈更像是：

- 模型本体对 control-like non-mix 的表示仍不够分离
- 而不是单纯缺一个更聪明的窗口聚合函数

## Recommended Next Direction

下一轮不建议继续在同一层做 gate 微分化。更有价值的方向是：

1. 补 control-like non-mix 的定向 hard negatives
2. 或者显式引入 control 抑制特征 / 二阶段 re-ranker
3. 多窗口聚合保留现有工具链能力，但不再作为主优化方向