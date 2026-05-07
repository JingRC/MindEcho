# Mix Binary Support-Gate Iteration 2026-04-12

## Goal

在确认多窗口 simple mean 的主要问题是“单个异常高窗会把 control 样本抬正”之后，本轮转向离散式稳定门控，而不是继续使用连续 penalty。

目标是假设：

- 如果一条样本只有单个窗口异常偏高，不应该轻易把整条样本判成 mix。
- 只有当至少多个窗口同时达到弱 mix 支持时，才允许整条样本维持较高 mix 判定。

## Code Changes

本轮新增了 `support_gate` 聚合模式：

- 文件：`train_mix_binary_squeezenet.py`
- 新参数：
  - `eval_window_support_threshold`
  - `eval_window_min_support_windows`
- 行为：
  - 若达到支持阈值的窗口数 `>= min_support_windows`，使用整段 3 窗 `mean` 聚合
  - 否则回退到更稳的 `median`

同时已经把上述参数接入：

- `compare_mix_binary_checkpoints.py`
- `calibrate_mix_binary_artifact.py`

因此当前 compare / calibrate / artifact summary 都能够完整记录离散门控配置。

## Validation Results

Artifact:

- `mix_binary_hardneg_v2_gpu`

Manifest:

- `dataset/curated/mix_binary_hardneg_v2/validation_manifest.csv`

统一设置：

- `eval_window_count = 3`
- 原始判定阈值先保持 artifact 默认 `0.425`

### Support gate 0.40 x 2

- `positive_mix = 0.659574`
- `control_negative = 0.300000`
- `breathy_group = 0.133333`
- `falsetto_group = 0.061224`
- `balanced_acc = 0.739426`

这个组合已经进入“可校准区域”，说明离散门控方向本身是成立的。

### Support gate 0.45 x 2

- `positive_mix = 0.666667`
- `control_negative = 0.271429`
- `breathy_group = 0.116667`
- `falsetto_group = 0.071429`
- `balanced_acc = 0.746988`

相较 `0.40 x 2`：

- `control_negative` 更低
- `breathy_group` 更低
- `positive_mix` 没有额外被明显砍穿

因此本轮最终选择 `0.45 x 2` 作为 discrete-gate 主候选。

## New Candidate

Artifact:

- `mix_binary_hardneg_v2_3win_supportgate45x2_guarded_gpu`

Validation constraints:

- `positive_mix >= 0.66`
- `control_negative <= 0.28`
- `breathy_group <= 0.12`
- `falsetto_group <= 0.08`

结果：

- `calibrated_threshold = 0.425`
- 说明当前 best threshold 恰好仍停留在原阈值，不需要再额外上调或下调。

## Core Test Comparison

Manifest:

- `dataset/curated/mix_binary_core/test_manifest.csv`

对比对象：

- `mix_binary_ce_v2_calibrated_gpu`
- `mix_binary_hardneg_v2_3win_guarded_gpu`
- `mix_binary_hardneg_v2_3win_strict_gpu`
- `mix_binary_hardneg_v2_3win_supportgate45x2_guarded_gpu`

### Key binary-role metrics

| artifact | positive_mix | control_negative | breathy_group | falsetto_group | balanced_acc |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline 3-win | 0.664336 | 0.215190 | 0.414634 | 0.101266 | 0.710891 |
| mean guarded | 0.657343 | 0.265823 | 0.243902 | 0.025316 | 0.718033 |
| mean strict | 0.615385 | 0.202532 | 0.195122 | 0.012658 | 0.720458 |
| support_gate 0.45 x 2 | 0.657343 | 0.278481 | 0.243902 | 0.037975 | 0.711650 |

## Decision

`support_gate 0.45 x 2` 仍然没有成为替换候选。

原因很明确：

1. 与 mean guarded 相比：
   - `positive_mix` 没有提升（同为 `0.657343`）
   - `control_negative` 更差（`0.278481 > 0.265823`）
   - `falsetto_group` 也更差（`0.037975 > 0.025316`）
2. 与 mean strict 相比：
   - recall 更高，但负类抑制明显不如 strict
   - 整体 `balanced_acc` 也更低
3. 与 baseline 相比：
   - breathy / falsetto 更干净
   - 但 control 仍远高于 baseline，无法构成全域优势

## What This Proved

这轮的价值主要在于排除了一个很像正确答案、但还不够强的方案：

1. “至少 2 窗弱支持才允许抬高整条样本”这个思路本身是合理的。
2. 但当前这个 `mean-or-median` 的 support gate 还不够精细。
3. 它能改变形状，却还没有把 `control_negative` 压到足以抵消 recall 代价的程度。

## Next Best Direction

下一轮更值得尝试的，不是继续堆同一类阈值，而是把 support gate 做得更细：

1. `2-of-3` 通过后，不直接用全均值，而是用“支持窗均值和全均值的较低者”
2. 对 `2-of-3` 中仅勉强过线的窗口增加二级条件，比如要求至少一个窗口达到更高支持档
3. 将 discrete gate 与 control 特定规则结合，而不是只在模型输出层做统一门控

## Product Safety

本轮新增 artifact：

- `mix_binary_hardneg_v2_3win_supportgate40x2_midguard_gpu`
- `mix_binary_hardneg_v2_3win_supportgate45x2_guarded_gpu`

它们都位于独立目录，不会自动影响当前软件使用的 checkpoint。