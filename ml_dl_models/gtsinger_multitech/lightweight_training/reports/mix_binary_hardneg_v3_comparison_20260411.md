# Mix Binary Hardneg v3 Comparison (2026-04-11)

## Training Result

- Artifact: `mix_binary_hardneg_v3_gpu`
- Best validation score metric: `balanced_acc`
- Best validation balanced_acc: `0.679215`
- Best threshold: `0.45`
- Training choice: head-only 6 epochs, because finetune started regressing after the head stage peak
- Own test split metrics:
  - accuracy: `0.663239`
  - balanced_acc: `0.644437`
  - mix_f1: `0.555932`
  - mix_precision: `0.539474`
  - mix_recall: `0.573427`

## Recall-Calibrated Candidate

- Artifact: `mix_binary_hardneg_v3_recall_calibrated_gpu`
- Source artifact: `mix_binary_hardneg_v3_gpu`
- Calibration target: `mix_recall`
- Constraint inputs attempted from validation summary:
  - min balanced_acc: `0.669215`
  - min mix_precision: `0.52`
- Selected threshold: `0.15`
- Validation-manifest metrics at that threshold:
  - accuracy: `0.388350`
  - balanced_acc: `0.533354`
  - mix_f1: `0.526316`
  - mix_precision: `0.358056`
  - mix_recall: `0.992908`

Interpretation:

- The recall-leaning candidate collapses into an almost-all-positive classifier.
- Even with constraints, the threshold search still chose a value that is far too aggressive.
- This candidate is not suitable for software replacement.

## Same-Manifest Four-Way Comparison

Compared on the same original manifest:

- Manifest: `dataset/curated/mix_binary_core/test_manifest.csv`
- Baseline artifact: `mix_binary_ce_v2_calibrated_gpu`
- Reference hard-negative artifact: `mix_binary_hardneg_v2_gpu`
- New balanced artifact: `mix_binary_hardneg_v3_gpu`
- New recall artifact: `mix_binary_hardneg_v3_recall_calibrated_gpu`

Overall:

- baseline_v2
  - acc: `0.722222`
  - balanced_acc: `0.708154`
  - mix_f1: `0.639175`
  - mix_precision: `0.628378`
  - mix_recall: `0.650350`
  - predicted_positive_rate: `0.391534`
- hardneg_v2
  - acc: `0.724868`
  - balanced_acc: `0.704806`
  - mix_f1: `0.631206`
  - mix_precision: `0.640288`
  - mix_recall: `0.622378`
  - predicted_positive_rate: `0.367725`
- hardneg_v3_balanced
  - acc: `0.650794`
  - balanced_acc: `0.635649`
  - mix_f1: `0.554054`
  - mix_precision: `0.535948`
  - mix_recall: `0.573427`
  - predicted_positive_rate: `0.404762`
- hardneg_v3_recall
  - acc: `0.394180`
  - balanced_acc: `0.511397`
  - mix_f1: `0.553606`
  - mix_precision: `0.383784`
  - mix_recall: `0.993007`
  - predicted_positive_rate: `0.978836`

Interpretation:

- `mix_binary_hardneg_v3_gpu` regresses strongly against both baseline and hardneg_v2 on the original test manifest.
- `mix_binary_hardneg_v3_recall_calibrated_gpu` recovers recall by predicting nearly everything as mix, which is unusable.
- The current baseline remains the best replacement candidate for software use.

## Group-Level Behavior

Use `predicted_positive_rate` as the main recall proxy for `Mixed_Voice_Group` and as the main false-positive proxy for the negative groups.

- Mixed_Voice_Group
  - baseline_v2: `0.633028`
  - hardneg_v2: `0.623853`
  - hardneg_v3_balanced: `0.568807`
  - hardneg_v3_recall: `1.000000`
  - result: v3 balanced failed to recover recall; recall-calibrated only wins by saturating positives
- Falsetto_Group
  - baseline_v2: `0.229885`
  - hardneg_v2: `0.091954`
  - hardneg_v3_balanced: `0.183908`
  - hardneg_v3_recall: `0.942529`
  - result: v3 balanced loses part of the v2 suppression benefit; recall candidate is catastrophic
- Breathy_Group
  - baseline_v2: `0.365854`
  - hardneg_v2: `0.268293`
  - hardneg_v3_balanced: `0.414634`
  - hardneg_v3_recall: `1.000000`
  - result: v3 balanced is worse than both baseline and v2; recall candidate completely collapses
- Control_Group
  - baseline_v2: `0.307692`
  - hardneg_v2: `0.355769`
  - hardneg_v3_balanced: `0.375000`
  - hardneg_v3_recall: `0.971154`
  - result: v3 balanced worsens the control false-positive channel further; recall candidate is unacceptable

## Decision

- `mix_binary_hardneg_v3_gpu` is not a replacement candidate.
- `mix_binary_hardneg_v3_recall_calibrated_gpu` is also not a replacement candidate.
- The software should remain on `mix_binary_ce_v2_calibrated_gpu`.
- `mix_binary_hardneg_v2_gpu` remains useful as evidence that falsetto and breathy suppression can be improved, but it is still not strong enough overall to replace the baseline.

## Recommended Next Step

- Stop pushing threshold-only recall recovery on the current v3 family.
- If training continues, the next iteration should target `Mixed_Voice_Group` recall by changing positive coverage or feature quality, while explicitly constraining `Control_Group` and `Breathy_Group` false-positive rates during model selection.

## Artifacts

- `_tmp_mix_binary_hardneg_v3_family_vs_baselines_core_test.json`
- `artifacts/mix_binary_hardneg_v3_gpu/training_summary.json`
- `artifacts/mix_binary_hardneg_v3_recall_calibrated_gpu/training_summary.json`