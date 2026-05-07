# Mix Binary Manifest Summary

- target_label: mix
- keep_control_ratio: 0.55
- keep_falsetto_ratio: 0.55
- keep_breathy_ratio: 0.35
- keep_other_negative_ratio: 0.25

## Fusion Intent

- This split trains mix as the primary learned classifier.
- Falsetto and breathy groups are kept as hard negatives so the mix model learns to reject head-only and airy-only segments.
- Strong mix / weak mix / 气混声 should stay in the rule layer, fused from mix confidence plus chest/falsetto and breathiness signals.

## Train

- items: 3054
- mix_positive: 1131
- mix_negative: 1923
- mix_positive_rate: 0.3703
- role_positive_mix: 1131
- role_control_negative: 622
- role_falsetto_group: 622
- role_breathy_group: 396
- role_other_negative: 283
- group_Control_Group: 847
- group_Mixed_Voice_Group: 810
- group_Falsetto_Group: 710
- group_Breathy_Group: 396
- group_Pharyngeal_Group: 277
- group_Vibrato_Group: 10
- group_Glissando_Group: 4
- mix_variant_clear_mix: 999
- mix_variant_head_mix: 125
- mix_variant_breathy_mix: 7

## Validation

- items: 381
- mix_positive: 141
- mix_negative: 240
- mix_positive_rate: 0.3701
- role_positive_mix: 141
- role_control_negative: 78
- role_falsetto_group: 78
- role_breathy_group: 49
- role_other_negative: 35
- group_Control_Group: 112
- group_Mixed_Voice_Group: 99
- group_Falsetto_Group: 85
- group_Breathy_Group: 49
- group_Pharyngeal_Group: 35
- group_Vibrato_Group: 1
- mix_variant_clear_mix: 125
- mix_variant_head_mix: 15
- mix_variant_breathy_mix: 1

## Test

- items: 378
- mix_positive: 143
- mix_negative: 235
- mix_positive_rate: 0.3783
- role_positive_mix: 143
- role_control_negative: 79
- role_falsetto_group: 79
- role_breathy_group: 41
- role_other_negative: 36
- group_Mixed_Voice_Group: 109
- group_Control_Group: 104
- group_Falsetto_Group: 87
- group_Breathy_Group: 41
- group_Pharyngeal_Group: 33
- group_Glissando_Group: 2
- group_Vibrato_Group: 2
- mix_variant_clear_mix: 126
- mix_variant_head_mix: 17

