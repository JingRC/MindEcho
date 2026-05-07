# Mix Binary Soft Reranker Iteration 2026-04-12

## Goal

在 `control-only suppressor + hard gate` 已被证伪后，这一轮改成真正的 soft reranker：

- 主模型仍输出 mix 概率
- suppressor 输出 control-like 概率
- 不再做二值 gate，而是在 centered-logit 空间做软融合

目标不是追求更高的 unconstrained balanced_acc，而是确认：

- 是否存在一个非 trivial 的 product-like operating region
- 能在不明显伤害 `positive_mix` 的前提下压住 `control_negative`

## Implementation

新增脚本：

- `calibrate_mix_binary_soft_reranker.py`

融合形式：

- `primary_margin = logit(primary_prob) - logit(primary_threshold)`
- `suppressor_margin = logit(suppressor_prob) - logit(suppressor_anchor)`
- `fused_margin = primary_margin + weight * suppressor_margin + bias`

其中：

- `weight` 扫描 `0.0 -> 2.0`，步长 `0.125`
- `bias` 扫描 `-1.0 -> 1.0`，步长 `0.1`

## Unconstrained Result

### Raw primary

Primary:

- `mix_binary_hardneg_v2_gpu`

Suppressor:

- `mix_control_only_v1_mean3_e4_gpu`

validation 最优融合：

- `weight = 0.25`
- `bias = 0.2`
- `positive_mix 0.887`
- `control_negative 0.487`
- `falsetto_group 0.218`
- `breathy_group 0.122`
- `balanced_acc 0.764`

应用到 core test 后：

- `positive_mix 0.874`
- `control_negative 0.456`
- `falsetto_group 0.177`
- `breathy_group 0.317`
- `balanced_acc 0.750`

### Guarded primary

Primary:

- `mix_binary_hardneg_v2_3win_guarded_gpu`

validation 最优融合：

- `weight = 0.375`
- `bias = 0.1`
- `positive_mix 0.837`
- `control_negative 0.423`
- `falsetto_group 0.179`
- `breathy_group 0.082`
- `balanced_acc 0.762`

应用到 core test 后：

- `positive_mix 0.797`
- `control_negative 0.354`
- `falsetto_group 0.152`
- `breathy_group 0.244`
- `balanced_acc 0.739`

结论很明确：

- soft fusion 不是 no-op
- 但 unconstrained 最优点仍然会走向更高 recall 与更高 false positive 一起上升

## Constrained Result

随后在 guarded primary 上加入 product-like validation 约束：

- `min_positive_mix_rate = 0.65`
- `max_control_negative_rate = 0.24`
- `max_falsetto_negative_rate = 0.10`
- `max_breathy_negative_rate = 0.07`

结果：

- `candidate_count = 357`
- `constraint_satisfied_candidate_count = 1`

唯一满足约束的候选是：

- `suppressor_weight = 0.0`
- `bias = 0.0`

也就是完全退化为 guarded primary 原模型。

它在 validation 上与 primary-only 完全同形：

- `positive_mix 0.660`
- `control_negative 0.231`
- `falsetto_group 0.090`
- `breathy_group 0.061`
- `balanced_acc 0.736`

在 core test 上同样与 primary-only 同形：

- `positive_mix 0.657`
- `control_negative 0.266`
- `falsetto_group 0.025`
- `breathy_group 0.244`
- `balanced_acc 0.718`

## Decision

这一轮已经足够证明：

1. soft reranker 作为结构分支是有效尝试，不是 hard gate 的重复包装
2. 但当前 `primary + control-only suppressor` 组合没有形成可用的 product-like operating region
3. 一旦允许融合真正起作用，validation 最优点就会抬高整个正类通道
4. 一旦施加产品约束，可行解只剩 `weight = 0.0` 的 no-op

因此：

- 当前 soft reranker 分支不继续深挖
- 软件 checkpoint 维持现状