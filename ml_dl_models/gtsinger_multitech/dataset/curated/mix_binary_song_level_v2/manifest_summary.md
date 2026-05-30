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

- items: 7218
- songs: 226
- mix_positive: 2966
- mix_negative: 4252
- mix_positive_rate: 0.4109
- role_breathy_group: 654
- role_control_negative: 1631
- role_falsetto_group: 1225
- role_other_negative: 742
- role_positive_mix: 2966
- group_Breathy_Group: 752
- group_Control_Group: 2711
- group_Falsetto_Group: 1297
- group_Glissando_Group: 242
- group_Mixed_Voice_Group: 1282
- group_Pharyngeal_Group: 605
- group_Vibrato_Group: 329
- singer_DE-Soprano-1: 31
- singer_EN-Alto-1: 802
- singer_EN-Alto-2: 1159
- singer_EN-Tenor-1: 1099
- singer_FR-Soprano-1: 732
- singer_FR-Tenor-1: 352
- singer_ZH-Alto-1: 1795
- singer_ZH-Tenor-1: 1248
- language_Chinese: 3043
- language_English: 3060
- language_French: 1084
- language_German: 31
- mix_variant_breathy_mix: 77
- mix_variant_clear_mix: 2747
- mix_variant_head_mix: 142

## Validation

- items: 1771
- songs: 49
- mix_positive: 749
- mix_negative: 1022
- mix_positive_rate: 0.4229
- role_breathy_group: 149
- role_control_negative: 412
- role_falsetto_group: 274
- role_other_negative: 187
- role_positive_mix: 749
- group_Breathy_Group: 156
- group_Control_Group: 722
- group_Falsetto_Group: 290
- group_Glissando_Group: 65
- group_Mixed_Voice_Group: 284
- group_Pharyngeal_Group: 170
- group_Vibrato_Group: 84
- singer_EN-Alto-1: 171
- singer_EN-Alto-2: 312
- singer_EN-Tenor-1: 365
- singer_FR-Soprano-1: 115
- singer_FR-Tenor-1: 23
- singer_ZH-Alto-1: 472
- singer_ZH-Tenor-1: 313
- language_Chinese: 785
- language_English: 848
- language_French: 138
- mix_variant_breathy_mix: 9
- mix_variant_clear_mix: 724
- mix_variant_head_mix: 16

## Test

- items: 1855
- songs: 51
- mix_positive: 762
- mix_negative: 1093
- mix_positive_rate: 0.4108
- role_breathy_group: 161
- role_control_negative: 419
- role_falsetto_group: 323
- role_other_negative: 190
- role_positive_mix: 762
- group_Breathy_Group: 189
- group_Control_Group: 669
- group_Falsetto_Group: 349
- group_Glissando_Group: 113
- group_Mixed_Voice_Group: 344
- group_Pharyngeal_Group: 89
- group_Vibrato_Group: 102
- singer_EN-Alto-1: 233
- singer_EN-Alto-2: 207
- singer_EN-Tenor-1: 335
- singer_FR-Soprano-1: 205
- singer_FR-Tenor-1: 80
- singer_ZH-Alto-1: 421
- singer_ZH-Tenor-1: 374
- language_Chinese: 795
- language_English: 775
- language_French: 285
- mix_variant_breathy_mix: 15
- mix_variant_clear_mix: 709
- mix_variant_head_mix: 38

