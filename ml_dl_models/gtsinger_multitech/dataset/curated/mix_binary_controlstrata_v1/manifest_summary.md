# Mix Binary Manifest Summary

- target_label: mix
- keep_control_ratio: 0.5
- keep_falsetto_ratio: 0.9
- keep_breathy_ratio: 0.6
- keep_other_negative_ratio: 0.15
- control_selection_mode: stratified_by_artifact
- hard_negative_artifact: ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\mix_binary_hardneg_v2_gpu
- control_easy_share: 0.2
- control_mid_share: 0.3
- control_hard_share: 0.5
- control_easy_quantile: 0.33
- control_hard_quantile: 0.67

## Fusion Intent

- This split trains mix as the primary learned classifier.
- Falsetto and breathy groups are kept as hard negatives so the mix model learns to reject head-only and airy-only segments.
- Strong mix / weak mix / 气混声 should stay in the rule layer, fused from mix confidence plus chest/falsetto and breathiness signals.

## Train

- items: 3024
- mix_positive: 1131
- mix_negative: 1893
- mix_positive_rate: 0.3740
- role_positive_mix: 1131
- role_falsetto_group: 750
- role_control_negative: 566
- role_breathy_group: 407
- role_other_negative: 170
- group_Falsetto_Group: 838
- group_Mixed_Voice_Group: 810
- group_Control_Group: 791
- group_Breathy_Group: 407
- group_Pharyngeal_Group: 164
- group_Vibrato_Group: 10
- group_Glissando_Group: 4
- control_stratum_hard: 283
- control_stratum_mid: 170
- control_stratum_easy: 113
- mix_variant_clear_mix: 999
- mix_variant_head_mix: 125
- mix_variant_breathy_mix: 7
- control_mined_mix_prob_min: 0.144731
- control_mined_mix_prob_mean: 0.536567
- control_mined_mix_prob_max: 0.900099

## Validation

- items: 390
- mix_positive: 141
- mix_negative: 249
- mix_positive_rate: 0.3615
- role_positive_mix: 141
- role_falsetto_group: 98
- role_control_negative: 70
- role_breathy_group: 60
- role_other_negative: 21
- group_Falsetto_Group: 105
- group_Control_Group: 104
- group_Mixed_Voice_Group: 99
- group_Breathy_Group: 60
- group_Pharyngeal_Group: 21
- group_Vibrato_Group: 1
- control_stratum_hard: 35
- control_stratum_mid: 21
- control_stratum_easy: 14
- mix_variant_clear_mix: 125
- mix_variant_head_mix: 15
- mix_variant_breathy_mix: 1
- control_mined_mix_prob_min: 0.172726
- control_mined_mix_prob_mean: 0.536652
- control_mined_mix_prob_max: 0.865904

## Test

- items: 367
- mix_positive: 143
- mix_negative: 224
- mix_positive_rate: 0.3896
- role_positive_mix: 143
- role_falsetto_group: 90
- role_control_negative: 72
- role_breathy_group: 41
- role_other_negative: 21
- group_Mixed_Voice_Group: 109
- group_Falsetto_Group: 98
- group_Control_Group: 97
- group_Breathy_Group: 41
- group_Pharyngeal_Group: 18
- group_Glissando_Group: 2
- group_Vibrato_Group: 2
- control_stratum_hard: 36
- control_stratum_mid: 22
- control_stratum_easy: 14
- mix_variant_clear_mix: 126
- mix_variant_head_mix: 17
- control_mined_mix_prob_min: 0.121373
- control_mined_mix_prob_mean: 0.547088
- control_mined_mix_prob_max: 0.844290

