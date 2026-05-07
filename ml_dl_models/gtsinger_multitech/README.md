# GTSinger Multi-Tech Workspace

This directory is reserved for GTSinger-based lightweight training and later multitech expansion.

## Layout

- dataset/raw
  - Put downloaded original GTSinger assets here.
  - Expected contents include language folders, wav, TextGrid, json, and musicxml.
  - If you later download only a subset, still keep the original folder hierarchy under this directory.

- dataset/processed
  - Put processed metadata here.
  - Recommended files: metadata.json, phone_set.json, spker_set.json.
  - This is the smallest required entry point for later filtering scripts.

- dataset/curated
  - Put task-specific filtered subsets here.
  - Examples:
    - chest_falsetto_aux
    - multitech_core
    - mix_falsetto_breathy
  - This directory is the best place for compact training manifests and selected wav lists.

- lightweight_training/cache
  - Temporary spectrograms, manifests, exported windows, feature caches.
  - Safe to delete after training is validated.

- lightweight_training/artifacts
  - Keep only final useful outputs here.
  - Recommended keep list:
    - best checkpoint
    - training_summary.json
    - inference label map

- lightweight_training/reports
  - Experiment notes, comparison reports, ablation summaries.

## Recommended Download Strategy

Do not start with the full 80+ hour corpus unless you are immediately training a full multitech recognizer.

### Phase 1: enough for current optimization

Download first:

- processed metadata for available languages
- raw singing data only for technique folders you will use soon:
  - Mixed_Voice_and_Falsetto
  - Breathy
  - Vibrato
  - Glissando
  - Pharyngeal
- keep the matching Control_Group data for those songs

You can skip for now:

- Paired_Speech_Group
- languages you do not plan to use in the next round
- any folder unrelated to the above five singing technique groups

### Phase 2: full multitech expansion

Only download the remaining languages and other groups when you start training a unified multitech model.

## Practical Retention Policy

After training is stable, keep:

- lightweight_training/artifacts/best_*.pt
- lightweight_training/artifacts/*.json
- lightweight_training/reports/*.md

You can delete:

- lightweight_training/cache
- regenerated spectrogram images
- temporary exported windows
- duplicate raw zips once extracted and verified

## Current Recommended Training Direction

Train mix first as a dedicated binary model instead of forcing mix, falsetto, and breathy into one shared lightweight head.

### Why

- GTSinger gives a usable positive signal for mix, but strong_mix / weak_mix / 气混声 are still not directly supervised labels.
- Falsetto and breathy are better treated as hard negatives for the mix classifier, then fused later with the existing chest/falsetto model and breathiness rules.
- This keeps the learned model lightweight and lets subtype logic stay interpretable in the rule layer.

### New Pipeline

1. Build mix-focused manifests:

```powershell
python ml_dl_models/gtsinger_multitech/lightweight_training/prepare_mix_binary_manifests.py
```

2. Train the mix binary model:

```powershell
python ml_dl_models/gtsinger_multitech/lightweight_training/train_mix_binary_squeezenet.py
```

The dedicated mix trainer now uses a true binary CrossEntropy route with a 2-class SqueezeNet head, matching the chest/falsetto training style much more closely than the earlier multi-label wrapper.

3. Fuse outputs later:

- mix main model output: determines whether the segment is likely mix at all
- chest/falsetto lightweight model: provides chest_bias vs head_bias
- existing breathiness signal: provides airy support
- rule layer: derives 强混声 / 弱混声 / 气混声

### Practical Fusion Rule

- high mix + chest bias + lower breathiness: strong mix
- high mix + head bias + lower breathiness: weak mix
- high mix + clear breathiness: 气混声

The current GUI already has a rule-based mix subtype layer. The new binary mix model is intended to replace the weakest part of that pipeline: the initial decision of whether a region should be considered mix at all.

## Why This Structure

- Keeps GTSinger isolated from the existing chest_falsetto dataset.
- Leaves room for future mix, breathy, vibrato, glissando, and pharyngeal training.
- Lets you keep only lightweight model weights and summaries after experiments.