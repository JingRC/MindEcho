# Mix Binary Confusable Cluster Summary

## Config

- artifact: `artifacts\mix_binary_hardneg_v2_3win_guarded_gpu`
- focus_roles: `control_negative, breathy_group, falsetto_group `
- cluster_count: `6`
- backbone_name: `squeezenet11`
- image_size: `224`
- sample_rate: `22050`
- sample_secs: `2.4`
- n_fft / hop_length / n_mels: `1024 / 256 / 128`

## Train

- focus_sample_count: `1640`
- focus_binary_roles: `{"breathy_group": 396, "control_negative": 622, "falsetto_group": 622}`

| cluster | count | roles | groups | mix_prob_mean |
| --- | ---: | --- | --- | ---: |
| cluster_00 | 214 | {"breathy_group": 3, "control_negative": 202, "falsetto_group": 9} | {"Breathy_Group": 3, "Control_Group": 202, "Falsetto_Group": 9} | 0.293327 |
| cluster_01 | 266 | {"breathy_group": 138, "control_negative": 18, "falsetto_group": 110} | {"Breathy_Group": 138, "Control_Group": 18, "Falsetto_Group": 110} | 0.136574 |
| cluster_02 | 178 | {"breathy_group": 82, "control_negative": 66, "falsetto_group": 30} | {"Breathy_Group": 82, "Control_Group": 66, "Falsetto_Group": 30} | 0.567103 |
| cluster_03 | 254 | {"breathy_group": 4, "control_negative": 221, "falsetto_group": 29} | {"Breathy_Group": 4, "Control_Group": 221, "Falsetto_Group": 29} | 0.363295 |
| cluster_04 | 391 | {"breathy_group": 120, "control_negative": 5, "falsetto_group": 266} | {"Breathy_Group": 120, "Control_Group": 5, "Falsetto_Group": 266} | 0.246289 |
| cluster_05 | 337 | {"breathy_group": 49, "control_negative": 110, "falsetto_group": 178} | {"Breathy_Group": 49, "Control_Group": 110, "Falsetto_Group": 178} | 0.232010 |

## Validation

- focus_sample_count: `205`
- focus_binary_roles: `{"breathy_group": 49, "control_negative": 78, "falsetto_group": 78}`

| cluster | count | roles | groups | mix_prob_mean |
| --- | ---: | --- | --- | ---: |
| cluster_00 | 25 | {"breathy_group": 1, "control_negative": 22, "falsetto_group": 2} | {"Breathy_Group": 1, "Control_Group": 22, "Falsetto_Group": 2} | 0.300735 |
| cluster_01 | 41 | {"breathy_group": 27, "control_negative": 3, "falsetto_group": 11} | {"Breathy_Group": 27, "Control_Group": 3, "Falsetto_Group": 11} | 0.133193 |
| cluster_02 | 17 | {"breathy_group": 4, "control_negative": 10, "falsetto_group": 3} | {"Breathy_Group": 4, "Control_Group": 10, "Falsetto_Group": 3} | 0.560614 |
| cluster_03 | 34 | {"control_negative": 27, "falsetto_group": 7} | {"Control_Group": 27, "Falsetto_Group": 7} | 0.382580 |
| cluster_04 | 45 | {"breathy_group": 14, "falsetto_group": 31} | {"Breathy_Group": 14, "Falsetto_Group": 31} | 0.249971 |
| cluster_05 | 43 | {"breathy_group": 3, "control_negative": 16, "falsetto_group": 24} | {"Breathy_Group": 3, "Control_Group": 16, "Falsetto_Group": 24} | 0.268532 |

## Test

- focus_sample_count: `199`
- focus_binary_roles: `{"breathy_group": 41, "control_negative": 79, "falsetto_group": 79}`

| cluster | count | roles | groups | mix_prob_mean |
| --- | ---: | --- | --- | ---: |
| cluster_00 | 27 | {"control_negative": 23, "falsetto_group": 4} | {"Control_Group": 23, "Falsetto_Group": 4} | 0.279530 |
| cluster_01 | 23 | {"breathy_group": 10, "control_negative": 3, "falsetto_group": 10} | {"Breathy_Group": 10, "Control_Group": 3, "Falsetto_Group": 10} | 0.143400 |
| cluster_02 | 22 | {"breathy_group": 10, "control_negative": 9, "falsetto_group": 3} | {"Breathy_Group": 10, "Control_Group": 9, "Falsetto_Group": 3} | 0.575482 |
| cluster_03 | 36 | {"control_negative": 33, "falsetto_group": 3} | {"Control_Group": 33, "Falsetto_Group": 3} | 0.390287 |
| cluster_04 | 56 | {"breathy_group": 17, "falsetto_group": 39} | {"Breathy_Group": 17, "Falsetto_Group": 39} | 0.246029 |
| cluster_05 | 35 | {"breathy_group": 4, "control_negative": 11, "falsetto_group": 20} | {"Breathy_Group": 4, "Control_Group": 11, "Falsetto_Group": 20} | 0.245591 |
