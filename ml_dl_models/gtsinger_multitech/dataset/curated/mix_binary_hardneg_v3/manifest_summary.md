# Mix Binary Manifest Summary

- target_label: mix
- keep_control_ratio: 0.6
- keep_falsetto_ratio: 0.7
- keep_breathy_ratio: 0.45
- keep_other_negative_ratio: 0.2

## Fusion Intent

- This split trains mix as the primary learned classifier.
- Falsetto and breathy groups are kept as hard negatives so the mix model learns to reject head-only and airy-only segments.
- Strong mix / weak mix / 气混声 should stay in the rule layer, fused from mix confidence plus chest/falsetto and breathiness signals.

## Train

- items: 3193
- mix_positive: 1131
- mix_negative: 2062
- mix_positive_rate: 0.3542
- role_positive_mix: 1131
- role_falsetto_group: 750
- role_control_negative: 679
- role_breathy_group: 407
- role_other_negative: 226
- group_Control_Group: 904
- group_Falsetto_Group: 838
- group_Mixed_Voice_Group: 810
- group_Breathy_Group: 407
- group_Pharyngeal_Group: 220
- group_Vibrato_Group: 10
- group_Glissando_Group: 4
- mix_variant_clear_mix: 999
- mix_variant_head_mix: 125
- mix_variant_breathy_mix: 7

## Validation

- items: 412
- mix_positive: 141
- mix_negative: 271
- mix_positive_rate: 0.3422
- role_positive_mix: 141
- role_falsetto_group: 98
- role_control_negative: 85
- role_breathy_group: 60
- role_other_negative: 28
- group_Control_Group: 119
- group_Falsetto_Group: 105
- group_Mixed_Voice_Group: 99
- group_Breathy_Group: 60
- group_Pharyngeal_Group: 28
- group_Vibrato_Group: 1
- mix_variant_clear_mix: 125
- mix_variant_head_mix: 15
- mix_variant_breathy_mix: 1

## Test

- items: 389
- mix_positive: 143
- mix_negative: 246
- mix_positive_rate: 0.3676
- role_positive_mix: 143
- role_falsetto_group: 90
- role_control_negative: 86
- role_breathy_group: 41
- role_other_negative: 29
- group_Control_Group: 111
- group_Mixed_Voice_Group: 109
- group_Falsetto_Group: 98
- group_Breathy_Group: 41
- group_Pharyngeal_Group: 26
- group_Glissando_Group: 2
- group_Vibrato_Group: 2
- mix_variant_clear_mix: 126
- mix_variant_head_mix: 17

