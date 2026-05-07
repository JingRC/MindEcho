# Mix Binary Backbone Iteration 2026-04-13

## Goal

上一轮已经明确：

- 继续堆 loss / gate / suppressor / control-target 小技巧，边际收益很低

因此这轮同时把 feature-side 路线真正落地：

- 支持切换 backbone
- 保证训练、compare、calibration、manifest mining、batch inference 都能读到同一份 backbone 与输入尺度配置

## Code Changes

本轮把以下脚本改成了对 artifact 输入配置敏感，而不是默认写死 SqueezeNet + `224/22050/1024/256/128`：

- `train_mix_binary_squeezenet.py`
- `compare_mix_binary_checkpoints.py`
- `calibrate_mix_binary_artifact.py`
- `compare_mix_binary_with_control_suppressor.py`
- `prepare_mix_binary_manifests.py`
- `batch_infer_mix_binary_squeezenet.py`

新增能力：

1. `train_mix_binary_squeezenet.py` 支持：
   - `squeezenet11`
   - `mobilenet_v3_small`
   - `efficientnet_b0`
2. training summary 现在会写出：
   - `backbone_name`
   - `image_size`
   - `sample_rate`
   - `n_fft`
   - `hop_length`
3. compare / calibration / manifest mining / batch inference 会自动继承这些参数

这意味着后续 feature-side 实验不再需要额外改工具链。

## Experiment 1: EfficientNet-B0 Smoke

Artifact:

- `mix_binary_efficientnet_b0_mean3_h2_gpu`

设置：

- backbone: `efficientnet_b0`
- `2` 个 head epoch
- `0` 个 finetune epoch
- `3-window mean`
- selection metric: `balanced_acc`

### Validation best

epoch 2 validation：

- `positive_mix 0.745`
- `control_negative 0.372`
- `breathy_group 0.286`
- `falsetto_group 0.192`
- `balanced_acc 0.695`

这已经说明：

- code path 没问题
- 但仅靠 2 个 head epoch，EfficientNet 早期形状仍然是 recall 高、false positive 也高

### Core test same-manifest result

在 `mix_binary_core/test_manifest.csv` 上：

- `positive_mix 0.720`
- `control_negative 0.380`
- `falsetto_group 0.266`
- `breathy_group 0.512`
- `balanced_acc 0.656`

对照 guarded baseline：

- baseline: `0.657 / 0.266 / 0.025 / 0.244 / 0.718`
- efficientnet smoke: `0.720 / 0.380 / 0.266 / 0.512 / 0.656`

## Experiment 2: EfficientNet-B0 Full Finetune With Larger Input

Artifact:

- `mix_binary_efficientnet_b0_img256_mel160_mean3_h4f6_proxy_gpu`

设置：

- backbone: `efficientnet_b0`
- `image_size = 256`
- `n_mels = 160`
- `4` 个 head epoch
- `6` 个 finetune epoch
- `3-window mean`
- `selection_metric = product_proxy`
- validation 继续要求：
   - `positive_mix >= 0.65`
   - `control_negative <= 0.24`
   - `falsetto_group <= 0.10`
   - `breathy_group <= 0.07`

### Validation best

best validation 出现在 epoch 10：

- `positive_mix 0.780`
- `control_negative 0.141`
- `breathy_group 0.041`
- `falsetto_group 0.077`
- `balanced_acc 0.825`
- `product_proxy score 1.0365`
- constraints satisfied
- `best_threshold = 0.475`

重要的是：

- 从 finetune 第 3 轮开始，这条线已经连续进入 product-like 区间
- 不再是“找不到约束阈值，只能退回 unconstrained 高召回高误报形状”

### Core test same-manifest result

在 `mix_binary_core/test_manifest.csv` 上：

- `positive_mix 0.685`
- `control_negative 0.152`
- `falsetto_group 0.000`
- `breathy_group 0.146`
- `balanced_acc 0.787`

对照几个关键参考：

- stable software checkpoint `mix_binary_ce_v2_calibrated_gpu`:
   - `0.650 / 0.152 / 0.215 / 0.366 / 0.708`
- `mix_binary_hardneg_v2_3win_guarded_gpu`:
   - `0.657 / 0.266 / 0.025 / 0.244 / 0.718`
- `mix_binary_hardneg_v2_3win_strict_gpu`:
   - `0.615 / 0.203 / 0.013 / 0.195 / 0.720`

可以直接看到：

- 相比 stable software checkpoint：
   - `positive_mix` 更高
   - `control_negative` 持平
   - `falsetto_group` 大幅更低
   - `breathy_group` 大幅更低
   - `balanced_acc` 明显更高
- 相比 guarded / strict：
   - `positive_mix` 更高
   - `control_negative` 更低
   - `breathy_group` 更低
   - `falsetto_group` 不差于 strict，且显著优于 guarded

这已经不是局部 tradeoff，而是第一次建立了比较明确的全域优势。

## Experiment 3: Longer EfficientNet Finetune Did Not Improve Core-Test Shape

Artifact:

- `mix_binary_efficientnet_b0_img256_mel160_mean3_h4f10_proxy_gpu`

设置：

- backbone: `efficientnet_b0`
- `image_size = 256`
- `n_mels = 160`
- `4` 个 head epoch
- `10` 个 finetune epoch
- 其余约束与 `h4f6` 保持一致

### Validation best

best validation 出现在总 epoch 10：

- `positive_mix 0.730`
- `control_negative 0.103`
- `breathy_group 0.020`
- `falsetto_group 0.064`
- `balanced_acc 0.817`
- `product_proxy score 1.0285`
- constraints satisfied
- `best_threshold = 0.525`

形状上它更保守：

- `control_negative / breathy_group / falsetto_group` 进一步下降
- 但 `positive_mix` 相比 `h4f6` 的 validation best 明显回落

### Core test same-manifest result

在同一个 `mix_binary_core/test_manifest.csv` 上重新比较：

- `mix_binary_ce_v2_calibrated_gpu`:
   - `0.650 / 0.152 / 0.215 / 0.366 / 0.708`
- `mix_binary_efficientnet_b0_img256_mel160_mean3_h4f6_proxy_gpu`:
   - `0.685 / 0.152 / 0.000 / 0.146 / 0.787`
- `mix_binary_efficientnet_b0_img256_mel160_mean3_h4f10_proxy_gpu`:
   - `0.573 / 0.076 / 0.013 / 0.000 / 0.763`

这里可以看到：

- `h4f10` 确实把负样本通道压得更低
- 但代价是 `positive_mix` 从 `0.685` 明显掉到 `0.573`
- 最终 `balanced_acc` 也从 `0.787` 回落到 `0.763`

因此 `h4f10` 不是更好的产品候选，而是一个“过度保守”的延长 finetune 版本。

## Decision

这一轮对 backbone 路线的结论应该收敛为：

1. feature-side 路线现在已经具备完整实验入口，后续可以直接换 backbone / image size / mel scale
2. smoke 结果本身仍然只证明 code path 打通，不足以代表 backbone 路线价值
3. `h4f10` 说明继续机械性拉长 finetune 并不会自然带来更好 core-test 结果，反而可能把阈值和模型形状一起推向过度保守
4. 完整 finetune 的 `mix_binary_efficientnet_b0_img256_mel160_mean3_h4f6_proxy_gpu` 仍然是当前第一条明确优于稳定软件 checkpoint 的 backbone 候选

因此：

- `mix_binary_efficientnet_b0_mean3_h2_gpu` 仍只是 smoke 候选，不作为 checkpoint 候选
- `mix_binary_efficientnet_b0_img256_mel160_mean3_h4f10_proxy_gpu` 不优于 `h4f6`，不作为替换候选
- `mix_binary_efficientnet_b0_img256_mel160_mean3_h4f6_proxy_gpu` 仍具备“可以考虑切换软件 checkpoint”的资格
- 当前不自动改软件路径；如果下一步要落产品，优先围绕 `h4f6` 做集成回归，而不是继续单纯延长同配方 finetune