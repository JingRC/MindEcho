# SqueezeNet Binary Baseline

Date: 2026-04-01

Model:
- Backbone: SqueezeNet 1.1
- Task: binary chest vs falsetto
- Input: mel spectrogram images from mel.zip
- Device used: CPU

Training run:
- Head epochs: 4
- Finetune epochs: 6
- Batch size: 32

Results:
- Best validation accuracy: 0.867188
- Test accuracy: 0.875000
- Test loss: 0.335900
- Total training time: 387.744 seconds
- Checkpoint size: 2.78 MB

Confusion matrix:
- chest predicted as chest: 117
- chest predicted as falsetto: 12
- falsetto predicted as chest: 20
- falsetto predicted as falsetto: 107

Class metrics:
- chest: precision 0.8540, recall 0.9070, f1 0.8797
- falsetto: precision 0.8992, recall 0.8425, f1 0.8699

Files:
- checkpoint: artifacts/best_squeezenet_binary.pt
- summary: artifacts/training_summary.json
- history: artifacts/history.csv

Notes:
- This is already much lighter than the downloaded reference SqueezeNet checkpoint.
- Next optimization directions are safer augmentation, binary-only label cleanup, and short segment voting for inference stability.