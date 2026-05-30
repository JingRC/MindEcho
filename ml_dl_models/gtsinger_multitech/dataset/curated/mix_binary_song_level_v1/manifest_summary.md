# Mix Binary Song-Level Split Summary

- split_method: song_level_70_15_15
- keep_control_ratio: 0.55
- keep_falsetto_ratio: 0.55
- keep_breathy_ratio: 0.35
- keep_other_negative_ratio: 0.25
- seed: 42

## Key Difference from Original

- Split is by SONG, not by clip.
- All clips from a given (singer, song) pair go to exactly one split.
- Zero song overlap between train/val/test.
- Tests generalization to UNSEEN songs, not unseen clips from known songs.

## Train

- items: 7046
- songs: 177
- mix_positive: 2973
- mix_negative: 4073
- mix_positive_rate: 0.4219
- role_breathy_group: 531
- role_control_negative: 1635
- role_falsetto_group: 1164
- role_other_negative: 743
- role_positive_mix: 2973
- group_Breathy_Group: 624
- group_Control_Group: 2767
- group_Falsetto_Group: 1237
- group_Glissando_Group: 240
- group_Mixed_Voice_Group: 1213
- group_Pharyngeal_Group: 530
- group_Vibrato_Group: 435
- singer_EN-Alto-1: 764
- singer_EN-Alto-2: 1178
- singer_EN-Tenor-1: 1322
- singer_ZH-Alto-1: 2155
- singer_ZH-Tenor-1: 1627
- language_Chinese: 3782
- language_English: 3264
- mix_variant_breathy_mix: 70
- mix_variant_clear_mix: 2757
- mix_variant_head_mix: 146

## Validation

- items: 1351
- songs: 40
- mix_positive: 541
- mix_negative: 810
- mix_positive_rate: 0.4004
- role_breathy_group: 124
- role_control_negative: 298
- role_falsetto_group: 253
- role_other_negative: 135
- role_positive_mix: 541
- group_Breathy_Group: 141
- group_Control_Group: 470
- group_Falsetto_Group: 261
- group_Glissando_Group: 44
- group_Mixed_Voice_Group: 257
- group_Pharyngeal_Group: 61
- group_Vibrato_Group: 117
- singer_EN-Alto-1: 223
- singer_EN-Alto-2: 227
- singer_EN-Tenor-1: 261
- singer_ZH-Alto-1: 363
- singer_ZH-Tenor-1: 277
- language_Chinese: 640
- language_English: 711
- mix_variant_breathy_mix: 4
- mix_variant_clear_mix: 530
- mix_variant_head_mix: 7

## Test

- items: 1522
- songs: 39
- mix_positive: 670
- mix_negative: 852
- mix_positive_rate: 0.4402
- role_breathy_group: 98
- role_control_negative: 369
- role_falsetto_group: 217
- role_other_negative: 168
- role_positive_mix: 670
- group_Breathy_Group: 104
- group_Control_Group: 654
- group_Falsetto_Group: 240
- group_Glissando_Group: 63
- group_Mixed_Voice_Group: 243
- group_Pharyngeal_Group: 170
- group_Vibrato_Group: 48
- singer_EN-Alto-1: 219
- singer_EN-Alto-2: 271
- singer_EN-Tenor-1: 209
- singer_ZH-Alto-1: 447
- singer_ZH-Tenor-1: 376
- language_Chinese: 823
- language_English: 699
- mix_variant_breathy_mix: 10
- mix_variant_clear_mix: 628
- mix_variant_head_mix: 32

