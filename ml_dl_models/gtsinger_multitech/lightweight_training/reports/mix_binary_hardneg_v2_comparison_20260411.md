# Mix Binary Hardneg v2 Comparison (2026-04-11)

## Training Result

- Artifact: `mix_binary_hardneg_v2_gpu`
- Best validation score metric: `balanced_acc`
- Best validation balanced_acc: `0.707639`
- Best threshold: `0.425`
- Own test split metrics:
  - accuracy: `0.746594`
  - balanced_acc: `0.721607`
  - mix_f1: `0.651685`
  - mix_precision: `0.701613`
  - mix_recall: `0.608392`

## Same-Manifest Comparison

Compared on the same original manifest:

- Manifest: `dataset/curated/mix_binary_core/test_manifest.csv`
- Baseline artifact: `mix_binary_ce_v2_calibrated_gpu`
- Candidate artifact: `mix_binary_hardneg_v2_gpu`

Overall:

- baseline_v2
  - acc: `0.716931`
  - balanced_acc: `0.702529`
  - mix_f1: `0.632302`
  - mix_precision: `0.621622`
  - mix_recall: `0.643357`
  - predicted_positive_rate: `0.391534`
- hardneg_v2
  - acc: `0.724868`
  - balanced_acc: `0.702068`
  - mix_f1: `0.625899`
  - mix_precision: `0.644444`
  - mix_recall: `0.608392`
  - predicted_positive_rate: `0.357143`

Interpretation:

- hardneg_v2 is more conservative than baseline_v2.
- It improves overall accuracy and mix precision.
- It does not improve balanced_acc.
- It loses mix recall and slightly lowers overall mix_f1 on the original test manifest.

## Group-Level Behavior

Use `predicted_positive_rate` as the primary false-positive proxy for all-negative groups.

- Mixed_Voice_Group
  - baseline predicted_positive_rate: `0.633028`
  - hardneg_v2 predicted_positive_rate: `0.614679`
  - result: positive recall proxy decreased slightly
- Falsetto_Group
  - baseline predicted_positive_rate: `0.218391`
  - hardneg_v2 predicted_positive_rate: `0.080460`
  - result: clear false-positive improvement
- Breathy_Group
  - baseline predicted_positive_rate: `0.390244`
  - hardneg_v2 predicted_positive_rate: `0.268293`
  - result: false-positive improvement
- Control_Group
  - baseline predicted_positive_rate: `0.307692`
  - hardneg_v2 predicted_positive_rate: `0.326923`
  - result: slightly worse than baseline

## Decision

- `mix_binary_hardneg_v2_gpu` is not yet a replacement candidate for the current software checkpoint.
- It is useful as evidence that harder falsetto/breathy negatives can suppress those two false-positive channels.
- The next round should retain that benefit while recovering Mixed_Voice recall and avoiding the Control_Group regression.

## Artifacts

- `_tmp_mix_binary_hardneg_v2_vs_baseline_core_test.json`
- `artifacts/mix_binary_hardneg_v2_gpu/training_summary.json`