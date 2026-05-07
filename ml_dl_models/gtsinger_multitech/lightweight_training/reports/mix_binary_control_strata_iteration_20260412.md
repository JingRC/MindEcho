# Mix Binary Control-Strata Iteration 2026-04-12

## Goal

上一轮已经证明两件事：

1. `hardest-only` control negative 重训会把边界整体带歪
2. 独立 control-only suppressor + hard gate 在完整 mix domain 中没有可用工作区间

因此这一轮回到 upstream negative curation，但不再走“只取最硬 control”这条极端路线，而是改成：

- 用现有 artifact 对 control negatives 打分
- 再按 easy / mid / hard 三档分层抽样
- 保留 hard bias，同时恢复 control 分布覆盖

## Code Changes

`prepare_mix_binary_manifests.py` 新增了：

- `control_selection_mode=stratified_by_artifact`
- `control_easy_share`
- `control_mid_share`
- `control_hard_share`
- `control_easy_quantile`
- `control_hard_quantile`
- 输出字段 `control_stratum`

现在 control negatives 可以按 artifact 分数分成三档，再按指定比例混合进入训练集，而不是只保留最高分那一段。

## New Dataset

Dataset:

- `dataset/curated/mix_binary_controlstrata_v1`

统一设置仍与 `hardneg_v2` 保持一致：

- `keep_control_ratio = 0.50`
- `keep_falsetto_ratio = 0.90`
- `keep_breathy_ratio = 0.60`
- `keep_other_negative_ratio = 0.15`

Control 分层参数：

- easy share `0.20`
- mid share `0.30`
- hard share `0.50`
- easy quantile `0.33`
- hard quantile `0.67`

### Selected control strata

Train:

- easy `113`
- mid `170`
- hard `283`

Validation:

- easy `14`
- mid `21`
- hard `35`

Test:

- easy `14`
- mid `22`
- hard `36`

### Control mined score range

Train selected controls:

- min `0.144731`
- mean `0.536567`
- max `0.900099`

Validation selected controls:

- min `0.172726`
- mean `0.536652`
- max `0.865904`

Test selected controls:

- min `0.121373`
- mean `0.547088`
- max `0.844290`

这说明：

- 这版数据不再像 `hardest-only` 那样只保留极高分 control
- 但 hard 档仍然是主力，占一半

## Quick Training Screen

Candidate:

- `mix_binary_controlstrata_v1_mean3_e4_gpu`

Training setup:

- 4 head epochs
- no finetune
- `selection_metric=balanced_acc`
- `eval_window_count=3`
- `eval_window_aggregation=mean`

### Validation trajectory

Epoch 1:

- `positive_mix 0.496`
- `control_negative 0.414`
- `breathy 0.300`
- `falsetto 0.092`
- `balanced_acc 0.622`

Epoch 2:

- `positive_mix 0.489`
- `control_negative 0.371`
- `breathy 0.150`
- `falsetto 0.071`
- `balanced_acc 0.646`

Epoch 3:

- `positive_mix 0.589`
- `control_negative 0.529`
- `breathy 0.100`
- `falsetto 0.143`
- `balanced_acc 0.660`

Epoch 4:

- `positive_mix 0.844`
- `control_negative 0.843`
- `breathy 0.400`
- `falsetto 0.337`
- `balanced_acc 0.661`

Training summary:

- best threshold `0.425`
- best validation balanced_acc `0.660942`
- own test balanced_acc `0.655516`
- own test mix recall `0.860140`

### Interpretation

这版比 `hardest-only` 更平滑：

- 没有从前几轮就直接炸穿到极端 control 误报
- 说明 easy / mid / hard 混合确实降低了数据选择的极端性

但到 epoch 4 仍然出现明显的全局抬高：

- `positive_mix` 与 `control_negative` 一起往上漂

这已经是一个危险信号。

## Core Test Comparison

Manifest:

- `dataset/curated/mix_binary_core/test_manifest.csv`

对照对象：

- `mix_binary_ce_v2_calibrated_gpu`
- `mix_binary_hardneg_v2_gpu`
- `mix_binary_hardneg_v2_3win_guarded_gpu`
- `mix_binary_hardneg_v2_3win_strict_gpu`
- `mix_binary_controlstrata_v1_mean3_e4_gpu`

### Key binary-role metrics

| artifact | positive_mix | control_negative | falsetto_group | breathy_group | balanced_acc |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline 3-win | 0.664336 | 0.215190 | 0.101266 | 0.414634 | 0.710891 |
| raw v2 3-win | 0.720280 | 0.329114 | 0.037975 | 0.243902 | 0.734608 |
| guarded 3-win | 0.657343 | 0.265823 | 0.025316 | 0.243902 | 0.718033 |
| strict 3-win | 0.615385 | 0.202532 | 0.012658 | 0.195122 | 0.720458 |
| control-strata v1 | 0.860140 | 0.721519 | 0.329114 | 0.463415 | 0.649219 |

## Decision

`stratified_by_artifact` 虽然比 `hardest-only` 稳一点，但最终仍然失败，而且失败方式已经很清楚：

1. `positive_mix` 被大幅抬高到 `0.860`
2. `control_negative` 同步被抬到 `0.722`
3. `falsetto_group` 与 `breathy_group` 也一起显著恶化
4. core test `balanced_acc` 只有 `0.649`，明显低于 baseline / v2 / guarded / strict

它的行为不是“更聪明地学会 control”，而是：

- 把整体 positive 通道抬高了

因此：

- 这版 upstream control curation 不作为可继续深挖的主候选

## What This Round Proved

这轮把一个更具体的判断坐实了：

- 问题不只是 `hardest-only` 过于极端

因为现在已经恢复了 easy / mid / hard 混合覆盖，结果仍然没有变成“control 被压住、true mix 保持住”，而是又回到了整条正类通道一起抬高的形状。

这说明仅靠“按现有 artifact 的混淆分数重抽 control negatives”还不够，根因更像是：

1. 当前 control negatives 的内部语义仍然不够可分
2. 或者现有单头 mix classifier 不擅长显式建模 control-like non-mix

## Recommended Next Direction

当前更合理的下一步不再是继续改 artifact-score 抽样比例，而是：

1. 进入显式 control-aware 结构，例如 soft reranker 或多头模型
2. 或者先做更语义化的 control curation，例如把 control 再按声音形态 / 发声模式聚类，而不是只按当前 mix artifact 分数分层