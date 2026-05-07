# Mix Rule Batch-8 Offline Validation (2026-04-11)

Source:
- Integrated one-pass offline path via debug_mix_rule_offline.py
- Positive set: first 8 Mixed_Voice_Group samples from mix_binary_core test manifest

Aggregate:
- Positive samples checked: 8
- Samples with strong_mix in final events: 1/8 (12.5%)
- Samples with any mix event in final events: 2/8 (25.0%)
- Samples with no final mix event: 6/8 (75.0%)
- No-mix samples that still had at least one retained falsetto/chest segment with mix_prob >= 0.45: 4/6
- No-mix samples whose retained falsetto/chest segments stayed below 0.45: 2/6

Interpretation:
- strong_mix recall is systematically low on this positive batch.
- The bottleneck is not purely the mix front-end: 4 of the 6 misses still showed mix_prob crossing threshold on retained voice segments, but the final rule layer still collapsed them to falsetto.
- The remaining 2 misses look like genuine front-end weakness because mix_prob stayed clearly below threshold.

Per-sample outcomes:
- 一次就好#0005: final counts = falsetto 2, breath 1, strong_mix 2. strong_mix intervals: 7.92-8.24, 10.48-11.04.
- 三寸天堂#0008: final counts = falsetto 1, weak_mix 1. No strong_mix.
- 修炼爱情#0000: final counts = falsetto 1. No mix event, retained falsetto max mix_prob = 0.498058.
- 别找我麻烦#0009: final counts = falsetto 1. No mix event, retained falsetto max mix_prob = 0.477124.
- 剑伤#0009: final counts = falsetto 2. No mix event, retained falsetto max mix_prob = 0.353691.
- 化身孤岛的鲸#0006: final counts = falsetto 1. No mix event, retained falsetto max mix_prob = 0.469946.
- 化身孤岛的鲸#0009: final counts = falsetto 1. No mix event, retained falsetto max mix_prob = 0.451712.
- 化身孤岛的鲸#0016: final counts = falsetto 1, breath 1. No mix event, retained falsetto max mix_prob = 0.366345.

Suggested next step:
- Relax rule-layer gating before retraining again. The highest-value target is the falsetto-dominant path where mix_prob >= threshold but weak_mix/strong_mix still fails to land.