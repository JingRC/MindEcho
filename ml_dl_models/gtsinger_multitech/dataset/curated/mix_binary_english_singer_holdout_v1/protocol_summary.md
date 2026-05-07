# English Singer Held-Out Protocol

- protocol_name: english_singer_holdout_v1
- source_manifest: D:\-MindEcho-main\ml_dl_models\gtsinger_multitech\dataset\curated\english_mix_binary_eval\full_manifest.csv
- train_singers: EN-Alto-1
- validation_singers: EN-Tenor-1
- test_singers: EN-Alto-2

## Notes

- This protocol is frozen by singer identity. Using validation or test singers in training invalidates the held-out claim.
- The default assignment keeps EN-Alto-1 as the adaptation singer, EN-Tenor-1 as validation, and EN-Alto-2 as the final test singer.
- That default maps the more permissive high-false-positive regime to validation and the more over-conservative high-false-negative regime to the final test.

## Split Counts

### Train

- items: 1255
- labels_1: 771
- labels_0: 484
- binary_roles_positive_mix: 771
- binary_roles_breathy_group: 6
- binary_roles_control_negative: 206
- binary_roles_falsetto_group: 180
- binary_roles_other_negative: 92
- groups_Breathy_Group: 103
- groups_Control_Group: 537
- groups_Glissando_Group: 99
- groups_Falsetto_Group: 181
- groups_Mixed_Voice_Group: 184
- groups_Pharyngeal_Group: 102
- groups_Vibrato_Group: 49
- mix_variants_breathy_mix: 48
- mix_variants_non_mix: 484
- mix_variants_clear_mix: 717
- mix_variants_head_mix: 6
- singers_EN-Alto-1: 1255

### Validation

- items: 1845
- labels_0: 850
- labels_1: 995
- binary_roles_breathy_group: 133
- binary_roles_control_negative: 305
- binary_roles_positive_mix: 995
- binary_roles_other_negative: 141
- binary_roles_falsetto_group: 271
- groups_Breathy_Group: 136
- groups_Control_Group: 787
- groups_Glissando_Group: 128
- groups_Falsetto_Group: 271
- groups_Mixed_Voice_Group: 271
- groups_Pharyngeal_Group: 125
- groups_Vibrato_Group: 127
- mix_variants_non_mix: 850
- mix_variants_clear_mix: 976
- mix_variants_head_mix: 16
- mix_variants_breathy_mix: 3
- singers_EN-Tenor-1: 1845

### Test

- items: 1727
- labels_0: 724
- labels_1: 1003
- binary_roles_breathy_group: 106
- binary_roles_positive_mix: 1003
- binary_roles_other_negative: 124
- binary_roles_control_negative: 249
- binary_roles_falsetto_group: 245
- groups_Breathy_Group: 122
- groups_Control_Group: 741
- groups_Glissando_Group: 126
- groups_Falsetto_Group: 245
- groups_Mixed_Voice_Group: 245
- groups_Pharyngeal_Group: 122
- groups_Vibrato_Group: 126
- mix_variants_non_mix: 724
- mix_variants_clear_mix: 972
- mix_variants_breathy_mix: 25
- mix_variants_head_mix: 6
- singers_EN-Alto-2: 1727

