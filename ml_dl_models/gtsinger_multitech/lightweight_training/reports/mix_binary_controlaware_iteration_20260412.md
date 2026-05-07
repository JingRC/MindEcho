# Mix Binary Control-Aware Iteration 2026-04-12

## Goal

在 upstream control curation 与 soft reranker 都没有建立替换优势后，这一轮进入更结构化的方向：

- 在同一个 backbone 上同时学习
  - 主任务 `mix / non-mix`
  - 辅助任务 `confusable non-mix / other non-mix`

核心假设是：

- 如果 `control-like non-mix` 真是当前主要瓶颈，那么共享 backbone 上的辅助 supervision 应该能把这一条边界拉开，而不是依赖后验阈值或硬门控。

## Implementation

新增脚本：

- `train_mix_binary_controlaware_squeezenet.py`

实现要点：

1. 复用现有 mel / dataloader / threshold search / multi-window evaluation 工具链
2. 新增 shared-backbone dual-head 结构：
   - mix head: 仍输出标准 `non_mix / mix` logits
   - auxiliary head: 输出 `other_non_mix / confusable_non_mix` logits
3. auxiliary positive role 做成可配置集合，支持直接用 `binary_role` 组合实验
4. 导出 checkpoint 时只写出 mix head 对应的标准 state dict，因此现有 `compare_mix_binary_checkpoints.py` 可以直接加载

这一轮还顺手修掉了一个实现 bug：

- best checkpoint 不能直接保存 `model.state_dict()` 的浅拷贝
- 否则若最优 epoch 不是最后一个，后续训练会把内存中的 best state 改写，导致训练总结与磁盘 checkpoint 不一致
- 当前脚本已经改成在保存 best state 时 clone tensors

## Experiment A: Head-Only Auxiliary Head, Control Negative Only

Artifact:

- `mix_binary_controlaware_v1_mean3_e4_gpu`

设置：

- `4` 个 head epoch
- `0` 个 finetune epoch
- auxiliary positive role: `control_negative`
- `control_loss_weight = 0.35`
- `3-window mean`

core test binary-role：

- `positive_mix 0.664`
- `control_negative 0.241`
- `falsetto_group 0.203`
- `breathy_group 0.537`
- `balanced_acc 0.675`

解释：

- `control_negative` 确实比 guarded baseline 的 `0.266` 更低
- 但代价是 `breathy_group` 被明显打穿，`falsetto_group` 也同步抬高

这不是可替换形状。

## Experiment B: Head-Only Auxiliary Head, Control + Breathy Roles

Artifact:

- `mix_binary_controlaware_v1_controlbreathy_mean3_e4_gpu`

设置唯一变化：

- auxiliary positive role 改成 `control_negative + breathy_group`

结果与 Experiment A 的 mix 指标完全一致：

- `positive_mix 0.664`
- `control_negative 0.241`
- `falsetto_group 0.203`
- `breathy_group 0.537`
- `balanced_acc 0.675`

这条观察本身很重要：

- 在 head-only quick screen 里，backbone features 是冻结的
- auxiliary head 只能单独学习自己的分类器，无法反过来塑形共享表示
- 因此 head-only multi-head smoke test 对主 mix 任务基本是 no-op

## Experiment C: Shared-Backbone Candidate With Short Finetune

Artifact:

- `mix_binary_controlaware_v2b_controlbreathy_h2f2_mean3_gpu`

设置：

- `2` 个 head epoch
- `2` 个 finetune epoch
- auxiliary positive role: `control_negative + breathy_group`
- `control_loss_weight = 0.35`
- `3-window mean`

validation best epoch 出现在 head stage 第 2 轮：

- `positive_mix 0.716`
- `control_negative 0.256`
- `breathy_group 0.347`
- `falsetto_group 0.308`
- `balanced_acc 0.700`

对应 core test：

- `positive_mix 0.706`
- `control_negative 0.304`
- `falsetto_group 0.342`
- `breathy_group 0.585`
- `balanced_acc 0.651`

这说明一旦让 auxiliary loss 真正作用到共享 backbone，当前实现不是把 confusable negative 拉开，而是把整体正类通道继续抬高。

## Compatibility Check

新 artifact 已通过现有比较脚本回放：

- `compare_mix_binary_checkpoints.py` 可直接加载 `best_mix_binary_squeezenet.pt`
- 说明标准导出链路没有被多头训练打断

## Decision

当前 control-aware multi-head 分支的结论是：

1. head-only 版本不能检验结构价值，因为冻结 backbone 使 auxiliary supervision 对主任务近似 no-op
2. 真正允许共享表示更新后，当前实现会把 `breathy_group` 与 `falsetto_group` 明显抬高
3. 无论是 `control_negative only` 还是 `control + breathy` auxiliary target，都没有形成可替换候选

因此：

- 当前这版 control-aware multi-head 不继续直接扩训
- 软件 checkpoint 维持现状
- 如果后续还沿这条线走，下一步更合理的是重新定义 auxiliary target 与 sampling，而不是继续放大当前 loss 配比