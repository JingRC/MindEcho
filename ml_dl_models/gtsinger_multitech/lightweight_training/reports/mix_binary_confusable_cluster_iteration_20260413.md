# Mix Binary Confusable Cluster Iteration 2026-04-13

## Goal

上一轮的 control-aware multi-head 仍然依赖手写 auxiliary target：

- `control_negative`
- `control_negative + breathy_group`

这一轮改成更语义化的 confusable-negative clustering：

- 先用现有 artifact 的 learned embedding + 元数据 + mix 概率做聚类
- 再把 cluster id 写回 manifest
- 最后直接把 cluster id 当 auxiliary target 训练 shared-backbone 多头模型

目标不是继续微调 control/breathy 权重，而是验证：

- 更细粒度的 confusable cluster supervision 能否避免“压 control、炸 breathy/falsetto”的旧形状

## Code Changes

新增脚本：

- `cluster_mix_confusable_negatives.py`
- `train_mix_binary_clusteraware_squeezenet.py`

其中：

### 1. Cluster generation

`cluster_mix_confusable_negatives.py` 会：

1. 加载指定 artifact
2. 对 focus roles 提取：
   - checkpoint embedding
   - `group_name` / `language` / 技巧 flags 元数据
   - 当前 artifact 的 `mix_prob`
3. 做标准化 + PCA + KMeans
4. 把以下字段写回各 split manifest：
   - `confusable_cluster_focus`
   - `confusable_cluster_id`
   - `confusable_cluster_label`
   - `confusable_cluster_distance`
   - `confusable_cluster_mix_prob`

### 2. Cluster-aware training

`train_mix_binary_clusteraware_squeezenet.py` 会：

- 读取 manifest 中的 `confusable_cluster_id`
- 把它作为 auxiliary 多分类目标
- mix 主头继续维持标准二分类导出格式
- 因此新 artifact 仍然能被现有 `compare_mix_binary_checkpoints.py` 直接加载

## Dataset Generation

Dataset:

- `dataset/curated/mix_binary_confusable_cluster_v1`

Embedding source artifact:

- `mix_binary_hardneg_v2_3win_guarded_gpu`

Focus roles:

- `control_negative`
- `breathy_group`
- `falsetto_group`

Cluster count:

- `6`

Train focus sample count:

- `1640`

split 结构：

- train: `622 control / 396 breathy / 622 falsetto`
- validation: `78 / 49 / 78`
- test: `79 / 41 / 79`

## Cluster Shape

这批 cluster 确实不是简单按原 group 一刀切开，而是出现了几类更像“难度 + 语义”混合结构：

### Train cluster 00

- `214` samples
- `202 control + 9 falsetto + 3 breathy`
- `mix_prob_mean 0.293`

### Train cluster 02

- `178` samples
- `66 control + 82 breathy + 30 falsetto`
- `mix_prob_mean 0.567`

这是最接近“高混淆 confusable cluster”的一簇。

### Train cluster 04

- `391` samples
- `266 falsetto + 120 breathy + 5 control`
- `mix_prob_mean 0.246`

### Train cluster 01 / 05

- 都是 breathy / falsetto / control 的混合簇
- 但 `mix_prob_mean` 与组成比例明显不同

这说明聚类本身并不是无效空操作；它至少把“最像 mix 的负样本”从角色标签中再切成了更细结构。

## Experiment: Cluster-Aware Quick Candidate

Artifact:

- `mix_binary_clusteraware_v1_h2f2_mean3_gpu`

设置：

- train / validation / test 使用 `mix_binary_confusable_cluster_v1`
- `2` 个 head epoch
- `2` 个 finetune epoch
- `3-window mean`
- `aux_loss_weight = 0.25`
- selection metric: `balanced_acc`

### Validation best epoch

best validation 出现在 epoch 4：

- `positive_mix 0.681`
- `control_negative 0.192`
- `breathy_group 0.347`
- `falsetto_group 0.308`
- `balanced_acc 0.693`

观察：

- control 通道确实压下来了
- 但 breathy / falsetto 仍然大幅抬高
- product constraints 仍不满足

### Core test same-manifest result

在 `mix_binary_core/test_manifest.csv` 上：

- `positive_mix 0.692`
- `control_negative 0.228`
- `falsetto_group 0.430`
- `breathy_group 0.634`
- `balanced_acc 0.640`

对照 guarded baseline：

- baseline: `0.657 / 0.266 / 0.025 / 0.244 / 0.718`
- cluster-aware: `0.692 / 0.228 / 0.430 / 0.634 / 0.640`

## Decision

这一轮已经可以下结论：

1. “语义化 confusable cluster” 作为数据表示是有效的，聚类并不是退化到原始 group 标签
2. 但把这些 cluster 直接接成当前这版 auxiliary target 后，模型仍然会用“整体抬高正类通道”去换 control 改善
3. control 的确下降了，但 breathy / falsetto 被严重击穿，整体仍远弱于 guarded baseline

因此：

- 当前 `confusable_cluster_v1 + cluster-aware multi-head` 不继续直接扩训
- 如果还沿 cluster 路线走，下一步更合理的是重新定义 auxiliary objective，而不是继续放大当前 cluster loss