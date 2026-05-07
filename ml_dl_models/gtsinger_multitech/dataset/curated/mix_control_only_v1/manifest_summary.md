# Mix Binary Manifest Summary

- target_label: mix
- keep_control_ratio: 1.0
- keep_falsetto_ratio: 0.0
- keep_breathy_ratio: 0.0
- keep_other_negative_ratio: 0.0
- control_selection_mode: hardest_by_artifact
- hard_negative_artifact: ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\mix_binary_hardneg_v2_gpu

## Fusion Intent

- This split trains mix as the primary learned classifier.
- Falsetto and breathy groups are kept as hard negatives so the mix model learns to reject head-only and airy-only segments.
- Strong mix / weak mix / 气混声 should stay in the rule layer, fused from mix confidence plus chest/falsetto and breathiness signals.

## Train

- items: 2262
- mix_positive: 1131
- mix_negative: 1131
- mix_positive_rate: 0.5000
- role_positive_mix: 1131
- role_control_negative: 1131
- group_Control_Group: 1356
- group_Mixed_Voice_Group: 810
- group_Falsetto_Group: 88
- group_Pharyngeal_Group: 4
- group_Vibrato_Group: 3
- group_Glissando_Group: 1
- mix_variant_clear_mix: 999
- mix_variant_head_mix: 125
- mix_variant_breathy_mix: 7
- control_mined_mix_prob_mean: 0.649080
- control_mined_mix_prob_max: 0.900099

## Validation

- items: 282
- mix_positive: 141
- mix_negative: 141
- mix_positive_rate: 0.5000
- role_control_negative: 141
- role_positive_mix: 141
- group_Control_Group: 175
- group_Mixed_Voice_Group: 99
- group_Falsetto_Group: 7
- group_Vibrato_Group: 1
- mix_variant_clear_mix: 125
- mix_variant_head_mix: 15
- mix_variant_breathy_mix: 1
- control_mined_mix_prob_mean: 0.649206
- control_mined_mix_prob_max: 0.899248

## Test

- items: 286
- mix_positive: 143
- mix_negative: 143
- mix_positive_rate: 0.5000
- role_control_negative: 143
- role_positive_mix: 143
- group_Control_Group: 168
- group_Mixed_Voice_Group: 109
- group_Falsetto_Group: 8
- group_Vibrato_Group: 1
- mix_variant_clear_mix: 126
- mix_variant_head_mix: 17
- control_mined_mix_prob_mean: 0.643309
- control_mined_mix_prob_max: 0.850482

