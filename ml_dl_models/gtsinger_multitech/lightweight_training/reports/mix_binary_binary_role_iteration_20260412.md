# Mix Binary Binary-Role Iteration (2026-04-12)

## What Changed

- `train_mix_binary_squeezenet.py`
  - validation threshold selection now tracks clean `binary_role` partitions in addition to `group_name`
  - added validation constraints for:
    - `positive_mix`
    - `control_negative`
    - `breathy_group`
    - `falsetto_group`
  - added `technique_focus` weighted sampling mode
  - history now writes every epoch for easier monitoring in future runs
- `compare_mix_binary_checkpoints.py`
  - now reports `binary_roles` alongside existing group summaries
- `calibrate_mix_binary_artifact.py`
  - now supports binary-role-constrained threshold calibration
  - fixed a bug where constrained calibration could incorrectly keep an unconstrained initial threshold

## Key Finding

- Earlier evaluation was over-trusting `group_name`-level `predicted_positive_rate` as a false-positive proxy.
- In the mix manifests, `Control_Group` and `Falsetto_Group` both contain some true `mix=1` rows, so the clean product-facing proxy must be based on `binary_role` rather than whole-group rate.

Validation label composition confirmed on `mix_binary_hardneg_v2/validation_manifest.csv`:

- `positive_mix`: 141 positive rows
- `control_negative`: 70 negative rows
- `falsetto_group`: 98 negative rows
- `breathy_group`: 60 negative rows

## Current Reference on Core Test

Manifest:

- `dataset/curated/mix_binary_core/test_manifest.csv`

Binary-role summaries:

- baseline `mix_binary_ce_v2_calibrated_gpu`
  - `positive_mix` predicted_positive_rate: `0.650350`
  - `control_negative` predicted_positive_rate: `0.151899`
  - `falsetto_group` predicted_positive_rate: `0.215190`
  - `breathy_group` predicted_positive_rate: `0.365854`
- `mix_binary_hardneg_v2_gpu`
  - `positive_mix` predicted_positive_rate: `0.622378`
  - `control_negative` predicted_positive_rate: `0.227848`
  - `falsetto_group` predicted_positive_rate: `0.075949`
  - `breathy_group` predicted_positive_rate: `0.268293`

Interpretation:

- baseline still has the best positive recall proxy
- hardneg_v2 still suppresses falsetto and breathy much better
- hardneg_v2 still regresses control-negative behavior and positive recall

## Sampler Experiments

Two `technique_focus` training screens were launched on `mix_binary_hardneg_v2`.

### Aggressive Technique-Focus Screen

Config highlights:

- `head_mix_boost 2.2`
- `control_negative_boost 1.2`
- `falsetto_negative_boost 1.15`
- `breathy_negative_boost 1.25`

Observed by head epoch 3 on validation:

- `positive_mix_rate`: `0.765957`
- `control_negative_rate`: `0.528571`
- `breathy_negative_rate`: `0.366667`
- `falsetto_negative_rate`: `0.408163`

Decision:

- rejected early
- this configuration over-pulled positives and dragged every negative channel upward with it

### Soft Technique-Focus Screen

Config highlights:

- `head_mix_boost 1.5`
- `control_negative_boost 1.3`
- `falsetto_negative_boost 1.2`
- `breathy_negative_boost 1.35`

Observed by head epoch 2 on validation:

- epoch 1
  - `positive_mix_rate`: `0.645390`
  - `control_negative_rate`: `0.242857`
  - `breathy_negative_rate`: `0.450000`
  - `falsetto_negative_rate`: `0.367347`
- epoch 2
  - `positive_mix_rate`: `0.737589`
  - `control_negative_rate`: `0.457143`
  - `breathy_negative_rate`: `0.450000`
  - `falsetto_negative_rate`: `0.336735`

Decision:

- also rejected as a general direction
- softer weighting delayed the collapse but still drifted into the same failure mode

## Role-Constrained Threshold Calibration

Calibration target:

- source artifact: `mix_binary_hardneg_v2_gpu`
- manifest: `mix_binary_hardneg_v2/validation_manifest.csv`
- optimization metric: `mix_recall`
- constraints:
  - `control_negative <= 0.20`
  - `breathy_group <= 0.22`
  - `falsetto_group <= 0.21`

Result:

- calibrated threshold: `0.50`
- validation binary-role rates:
  - `positive_mix`: `0.468085`
  - `control_negative`: `0.185714`
  - `breathy_group`: `0.100000`
  - `falsetto_group`: `0.051020`

Core-test outcome for `mix_binary_hardneg_v2_role_calibrated_gpu`:

- overall balanced_acc: `0.689139`
- `positive_mix` predicted_positive_rate: `0.531469`
- `control_negative` predicted_positive_rate: `0.164557`
- `falsetto_group` predicted_positive_rate: `0.063291`
- `breathy_group` predicted_positive_rate: `0.195122`

Interpretation:

- binary-role-constrained threshold calibration does improve all three negative partitions relative to raw hardneg_v2
- but it does so by sacrificing too much positive mix recall
- this does not beat the current software baseline as an overall product candidate

## Decision

- Do not replace the current software checkpoint.
- Do not continue iterating on `technique_focus` weighted sampling as the main optimization direction.
- Do not expect `hardneg_v2` to be rescued by threshold-only calibration under clean negative constraints.

## Best Next Step

- Keep the current stable software mix checkpoint: `mix_binary_ce_v2_calibrated_gpu`.
- For the next training round, move away from sampler-level boosting and instead try one of these:
  - sample-wise loss weighting only on `head_mix` positives while keeping batch composition natural
  - an explicit product-proxy selection score using `binary_role` rates at epoch selection time
  - better positive feature coverage for `head_mix` rather than larger positive sampling frequency

## Artifacts

- `_tmp_mix_binary_core_test_baseline_vs_v2_roles.json`
- `_tmp_mix_binary_core_test_baseline_v2_rolecal_roles.json`
- `_tmp_mix_binary_hardneg_v2_validation_compare_roles.json`
- `artifacts/mix_binary_hardneg_v2_role_calibrated_gpu/training_summary.json`