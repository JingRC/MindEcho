# Mix Binary Manifest Summary

- target_label: mix
- keep_control_ratio: 0.3
- keep_falsetto_ratio: 1.0
- keep_breathy_ratio: 0.8
- keep_other_negative_ratio: 0.15

## Fusion Intent

- This split trains mix as the primary learned classifier.
- Falsetto and breathy groups are kept as hard negatives so the mix model learns to reject head-only and airy-only segments.
- Strong mix / weak mix / 气混声 should stay in the rule layer, fused from mix confidence plus chest/falsetto and breathiness signals.

## Train

- items: 2797
- mix_positive: 1131
- mix_negative: 1666
- mix_positive_rate: 0.4044
- role_positive_mix: 1131
- role_falsetto_group: 750
- role_breathy_group: 407
- role_control_negative: 339
- role_other_negative: 170
- group_Falsetto_Group: 838
- group_Mixed_Voice_Group: 810
- group_Control_Group: 564
- group_Breathy_Group: 407
- group_Pharyngeal_Group: 164
- group_Vibrato_Group: 10
- group_Glissando_Group: 4
- mix_variant_clear_mix: 999
- mix_variant_head_mix: 125
- mix_variant_breathy_mix: 7

## Validation

- items: 362
- mix_positive: 141
- mix_negative: 221
- mix_positive_rate: 0.3895
- role_positive_mix: 141
- role_falsetto_group: 98
- role_breathy_group: 60
- role_control_negative: 42
- role_other_negative: 21
- group_Falsetto_Group: 105
- group_Mixed_Voice_Group: 99
- group_Control_Group: 76
- group_Breathy_Group: 60
- group_Pharyngeal_Group: 21
- group_Vibrato_Group: 1
- mix_variant_clear_mix: 125
- mix_variant_head_mix: 15
- mix_variant_breathy_mix: 1

## Test

- items: 338
- mix_positive: 143
- mix_negative: 195
- mix_positive_rate: 0.4231
- role_positive_mix: 143
- role_falsetto_group: 90
- role_control_negative: 43
- role_breathy_group: 41
- role_other_negative: 21
- group_Mixed_Voice_Group: 109
- group_Falsetto_Group: 98
- group_Control_Group: 68
- group_Breathy_Group: 41
- group_Pharyngeal_Group: 18
- group_Glissando_Group: 2
- group_Vibrato_Group: 2
- mix_variant_clear_mix: 126
- mix_variant_head_mix: 17

