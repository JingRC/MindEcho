# Mix Binary Multi-Window Iteration 2026-04-12

## Goal

在已经基本证伪 `threshold / sampler / loss-weight / product-proxy` 这类权重技巧之后，转向验证一个更结构性的假设：

- 弱混 / 头混线索可能没有稳定落在单一中心裁剪窗内。
- 如果用多窗口覆盖同一条样本，再对 logits 做平均，可能能提升 mix 正样本召回，而不必重新训练一套更重的模型。

本轮只做推理侧 feature coverage 试验，不改当前软件使用的 checkpoint。

## Code Changes

本轮已接通以下多窗口能力：

- `train_mix_binary_squeezenet.py`
  - 增加 `eval_window_count`
  - 支持 anchor-based eval cropping
  - eval dataset 可返回 stacked windows
  - 新增 `forward_with_window_average(...)` 对多窗 logits 取平均
- `compare_mix_binary_checkpoints.py`
  - 支持 `--eval-window-count`
  - 可读取 artifact 自带 `eval_window_count`
- `calibrate_mix_binary_artifact.py`
  - 支持基于多窗口推理做后验阈值校准
  - 校准后的 artifact 会写回 `eval_window_count`

默认行为仍保持单窗，不会影响现有产品路径。

## First Comparison: 3-Window Override on Core Test

Manifest:

- `dataset/curated/mix_binary_core/test_manifest.csv`

Artifacts:

- `mix_binary_ce_v2_calibrated_gpu`
- `mix_binary_hardneg_v2_gpu`

### Baseline (`mix_binary_ce_v2_calibrated_gpu`) with 3 windows

- `overall balanced_acc = 0.710891`
- `positive_mix = 0.664336`
- `control_negative = 0.215190`
- `falsetto_group = 0.101266`
- `breathy_group = 0.414634`

相对单窗 baseline：

- `positive_mix` 只小幅提升（约 `0.650 -> 0.664`）
- `falsetto_group` 下降（约 `0.215 -> 0.101`）
- `breathy_group` 反而升高（约 `0.366 -> 0.415`）

结论：3 窗平均对当前 baseline 有信号，但收益不稳定，不足以单独成为切换理由。

### Hardneg v2 (`mix_binary_hardneg_v2_gpu`) with 3 windows

- `overall balanced_acc = 0.734608`
- `positive_mix = 0.720280`
- `control_negative = 0.329114`
- `falsetto_group = 0.037975`
- `breathy_group = 0.243902`

相对单窗 hardneg_v2：

- `positive_mix` 明显上升（约 `0.622 -> 0.720`）
- `falsetto_group` 继续下降（约 `0.076 -> 0.038`）
- `breathy_group` 继续下降（约 `0.268 -> 0.244`）
- 主要代价集中在 `control_negative`（约 `0.228 -> 0.329`）

结论：多窗口覆盖对 `hardneg_v2` 是真实有效的结构性提升，说明此前瓶颈确实有一部分来自单窗覆盖不足，而不是纯阈值问题。

## Validation Threshold Sweep for 3-Window Hardneg v2

Validation manifest:

- `dataset/curated/mix_binary_hardneg_v2/validation_manifest.csv`

关键阈值点如下：

| threshold | balanced_acc | positive_mix | control_negative | falsetto_group | breathy_group |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.400 | 0.774545 | 0.765957 | 0.357143 | 0.091837 | 0.150000 |
| 0.425 | 0.751132 | 0.695035 | 0.314286 | 0.071429 | 0.150000 |
| 0.450 | 0.747458 | 0.659574 | 0.257143 | 0.071429 | 0.100000 |
| 0.475 | 0.743314 | 0.631206 | 0.214286 | 0.061224 | 0.083333 |

解释：

- `0.400` 是 validation 上的 balanced-acc 最优点，但 control 明显过高。
- `0.450` 是偏召回但仍有一定防守的可行点。
- `0.475` 是更保守、负类通道更干净的可行点。

## New 3-Window Candidates

### Candidate A: `mix_binary_hardneg_v2_3win_balanced_gpu`

来源：

- 3 窗推理
- validation 上直接按 `balanced_acc` 无约束选阈值
- 得到阈值 `0.400`

在 core test 上：

- `overall balanced_acc = 0.725949`
- `positive_mix = 0.741259`
- `control_negative = 0.341772`
- `falsetto_group = 0.088608`
- `breathy_group = 0.268293`

结论：召回继续升，但 control 仍然过高，不作为替换候选。

### Candidate B: `mix_binary_hardneg_v2_3win_guarded_gpu`

约束：

- `positive_mix >= 0.65`
- `control_negative <= 0.26`
- `breathy_group <= 0.10`
- `falsetto_group <= 0.08`

validation 选出阈值：

- `0.450`

在 core test 上：

- `overall balanced_acc = 0.718033`
- `positive_mix = 0.657343`
- `control_negative = 0.265823`
- `falsetto_group = 0.025316`
- `breathy_group = 0.243902`

结论：

- 比 raw 3-window v2 安全得多
- 假声与气声误报显著更低
- 但 `positive_mix` 退回到接近 baseline，`Mixed_Voice_Group` 也不再保持 raw 3-window v2 的提升
- 没有形成明确替换优势

### Candidate C: `mix_binary_hardneg_v2_3win_strict_gpu`

约束：

- `positive_mix >= 0.63`
- `control_negative <= 0.22`
- `breathy_group <= 0.09`
- `falsetto_group <= 0.07`

validation 选出阈值：

- `0.475`

在 core test 上：

- `overall balanced_acc = 0.720458`
- `positive_mix = 0.615385`
- `control_negative = 0.202532`
- `falsetto_group = 0.012658`
- `breathy_group = 0.195122`

结论：

- 负类通道最干净，`control_negative` 甚至略优于当前 baseline 3-window
- 但 `positive_mix` 明显掉回去，Mixed recall 不足以替换 baseline

## Current Decision

当前没有 3-window 候选形成足够清晰的全域优势，因此：

- 当前软件继续保持 `mix_binary_ce_v2_calibrated_gpu`
- `mix_binary_hardneg_v2_gpu` 的 3 窗能力只作为实验结论保留，不进入产品切换

## What This Round Proved

本轮最重要的不是产出了新产品 checkpoint，而是把问题进一步定位清楚：

1. 多窗口覆盖对 `hardneg_v2` 的确有效，说明 mix 识别仍受时域覆盖不足影响。
2. 这个收益并不平均分布在所有负类上，主要冲击集中在 `control_negative`。
3. 因此下一轮更值得做的不是继续堆权重，而是专门处理“多窗口带来的 control 假阳性放大”。

## Recommended Next Directions

下一轮优先级建议：

1. 改窗口聚合方式，而不是只做均值聚合
   - 例如 `top-k average`、trimmed mean、或对低置信窗做抑制
2. 为 control 设计更定向的多窗口判别约束
   - 例如只在多窗中出现稳定高 mix 才给正，避免单个偶发窗把整条样本抬正
3. 如果继续训练，优先补“control-like but non-mix”的 hard negatives
   - 因为当前多窗口收益几乎都卡在 control channel 上

## Product Safety

本轮所有新 artifact 都在独立目录下：

- `mix_binary_hardneg_v2_3win_balanced_gpu`
- `mix_binary_hardneg_v2_3win_guarded_gpu`
- `mix_binary_hardneg_v2_3win_strict_gpu`

不会自动影响当前软件使用。