# Mix Rule v3 Regression Summary (2026-04-11)

## Context

- Baseline batch report before weak_mix relaxation:
  - `ml_dl_models/gtsinger_multitech/lightweight_training/reports/mix_rule_batch8_offline_validation_20260411.md`
  - Positive `Mixed_Voice_Group` batch: any mix `2/8`, `strong_mix 1/8`
- v2 weak_mix relaxation improved positive sample-level any-mix recall to `6/8`, but sampled `Breathy_Group` controls exposed a weak_mix false positive on `失落沙洲#0007`.
- v3 adds one targeted rejection guard inside `_build_rule_based_mix_events()` for pure learned, head-dominant weak_mix candidates:
  - `learned_mix_prob >= learned_mix_threshold`
  - `head_bias >= 0.70`
  - `heuristic_mix_support <= 0.08`
  - reject when `mean_pitch_hz < 430.0` and `falsetto_prob < 0.90`

## Positive Batch Result

Rechecked the same 8 positive samples under v3 using explicit offline runs.

- Samples with any final mix event: `6/8`
- Samples with final `strong_mix`: `1/8`
- Samples still missing final mix events: `2/8`

Hit samples:

- `一次就好#0005`: `strong_mix 2`, `weak_mix 2`
- `三寸天堂#0008`: `weak_mix 1`
- `修炼爱情#0000`: `weak_mix 1`
- `别找我麻烦#0009`: `weak_mix 1`
- `化身孤岛的鲸#0006`: `weak_mix 1`
- `化身孤岛的鲸#0009`: `weak_mix 1`

Remaining misses:

- `剑伤#0009`: final counts `{'falsetto': 1}`, retained `mix_prob=0.315897`
- `化身孤岛的鲸#0016`: final counts `{'falsetto': 1, 'breath': 1}`, retained `mix_prob=0.366345`

Interpretation:

- v3 preserved the v2 positive recall gain.
- Remaining misses are still front-end limited rather than rule-gating limited, because retained voice segments stay below the calibrated mix threshold.
- `strong_mix` remains conservative; the recall improvement is still mainly from `weak_mix` recovery on falsetto-dominant positives.

## Control Result

Sampled `Breathy_Group` controls under v3:

- `可乐#0007`: no final mix event
- `失落沙洲#0007`: no final mix event
- `奇妙能力歌#0004`: no final mix event
- `奇妙能力歌#0010`: no final mix event
- Aggregate: `0/4` sampled breathy controls emitted final mix events

Sampled `Falsetto_Group` controls under v3:

- `三寸天堂#0003`: no final mix event
- `三寸天堂#0006`: no final mix event
- `别找我麻烦#0000`: no final mix event
- `别找我麻烦#0005`: no final mix event
- Aggregate: `0/4` sampled falsetto controls emitted final mix events

Interpretation:

- The known v2 breathy false positive (`失落沙洲#0007`) is removed by v3.
- On the current sampled controls, v3 restores a clean result without giving back the positive recall gain.

## Validation Artifacts

- `_tmp_mix_rule_v3_targeted_regression.json`
- `_tmp_mix_rule_v3_remaining_positive_checks.json`
- `_tmp_mix_rule_v3_breathy_control_regression.json`
- `_tmp_mix_rule_v3_falsetto_control_regression.json`
- `_tmp_mix_rule_batch_falsetto_controls_first2_after_rule_relax.json`
- `_tmp_mix_rule_batch_falsetto_controls_last2_after_rule_relax.json`
- `_tmp_mix_rule_batch_breathy_controls_first2_after_rule_relax.json`
- `_tmp_mix_rule_batch_last2_after_rule_relax.json`

## Next Step

- If we continue tuning, the highest-value target is no longer weak_mix recall. The next bottleneck is `strong_mix` conservatism plus front-end misses where retained `mix_prob` stays materially below threshold.