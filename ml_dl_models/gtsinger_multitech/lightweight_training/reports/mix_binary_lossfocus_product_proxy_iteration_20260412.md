# Mix Binary Loss-Focus Product-Proxy Iteration (2026-04-12)

## Goal

- Stop using sampler-heavy positive boosting.
- Keep batch composition natural.
- Try sample-wise loss weighting plus binary-role-aware product-proxy model selection.

## Code Changes

- `train_mix_binary_squeezenet.py`
  - added `loss_weight_mode=technique_focus`
  - added per-sample loss weighting for `head_mix`, `breathy_mix`, `control_negative`, `falsetto_negative`, `breathy_negative`
  - added `selection_metric=product_proxy`
  - added `val_selection_score` logging
  - added immediate best-checkpoint persistence during training
- existing binary-role comparison path reused:
  - `compare_mix_binary_checkpoints.py`

## Candidate Configuration

- artifact: `mix_binary_hardneg_v2_lossfocus_proxy_e4_gpu`
- manifests: `mix_binary_hardneg_v2`
- training schedule: head-only 4 epochs
- batch size: `16`
- loss focus:
  - `head_mix_loss_boost 1.25`
  - `breathy_mix_loss_boost 1.10`
  - `control_negative_loss_boost 1.10`
  - `falsetto_negative_loss_boost 1.15`
  - `breathy_negative_loss_boost 1.20`
- selection metric: `product_proxy`
- validation constraints:
  - `min_positive_mix_rate 0.56`
  - `max_control_negative_rate 0.26`
  - `max_breathy_negative_rate 0.28`
  - `max_falsetto_negative_rate 0.22`

## Validation Behavior

Best validation point occurred at epoch 2:

- threshold: `0.50`
- balanced_acc: `0.653508`
- mix_precision: `0.572519`
- mix_recall: `0.531915`
- positive_mix_rate: `0.531915`
- control_negative_rate: `0.185714`
- breathy_negative_rate: `0.216667`
- falsetto_negative_rate: `0.214286`
- product_proxy score: `0.750846`

Interpretation:

- this direction is healthier than sampler-heavy `technique_focus`
- negative partitions stayed much more controlled in early epochs
- but positive mix recall still did not recover enough

## Core Test Comparison

Manifest:

- `dataset/curated/mix_binary_core/test_manifest.csv`

Binary-role summaries:

- baseline `mix_binary_ce_v2_calibrated_gpu`
  - `positive_mix`: `0.650350`
  - `control_negative`: `0.151899`
  - `falsetto_group`: `0.215190`
  - `breathy_group`: `0.365854`
- `mix_binary_hardneg_v2_gpu`
  - `positive_mix`: `0.622378`
  - `control_negative`: `0.227848`
  - `falsetto_group`: `0.075949`
  - `breathy_group`: `0.268293`
- new candidate `mix_binary_hardneg_v2_lossfocus_proxy_e4_gpu`
  - `positive_mix`: `0.510490`
  - `control_negative`: `0.227848`
  - `falsetto_group`: `0.215190`
  - `breathy_group`: `0.341463`

Overall metrics:

- baseline
  - balanced_acc: `0.708154`
  - mix_f1: `0.639175`
  - mix_precision: `0.628378`
  - mix_recall: `0.650350`
- hardneg_v2
  - balanced_acc: `0.704806`
  - mix_f1: `0.631206`
  - mix_precision: `0.640288`
  - mix_recall: `0.622378`
- new candidate
  - balanced_acc: `0.610564`
  - mix_f1: `0.514085`
  - mix_precision: `0.517730`
  - mix_recall: `0.510490`

## Decision

- `mix_binary_hardneg_v2_lossfocus_proxy_e4_gpu` is not a replacement candidate.
- Sample-wise loss weighting plus product-proxy selection is less pathological than sampler-heavy positive boosting.
- But this combination still fails to recover enough `positive_mix` recall on the original core test.

## Practical Conclusion

- The problem is now less likely to be solved by threshold choice, sampler choice, or simple loss reweighting.
- The next useful optimization step should target feature quality or positive coverage directly.

## Recommended Next Step

- Keep the current software checkpoint unchanged.
- Next round should test one of these instead of more weighting tricks:
  - longer or multi-window audio coverage for mix examples
  - feature representation changes that better preserve chest-head blend cues
  - richer positive curation specifically for weak/head-mix cases

## Artifacts

- `artifacts/mix_binary_hardneg_v2_lossfocus_proxy_e4_gpu/training_summary.json`
- `_tmp_mix_binary_core_test_lossfocus_proxy_roles.json`