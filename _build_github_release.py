#!/usr/bin/env python3
"""Build a clean GitHub release copy of MindEcho."""
import shutil
import os
from pathlib import Path

SRC = Path(r"d:\-MindEcho-main")
DST = Path(r"d:\-MindEcho-main\_github_release")

# Clean destination
if DST.exists():
    shutil.rmtree(DST)
DST.mkdir(parents=True)

def copy_file(rel_path):
    """Copy a single file, creating parent dirs."""
    src = SRC / rel_path
    dst = DST / rel_path
    if not src.exists():
        print(f"  MISSING: {rel_path}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True

def copy_dir(rel_path):
    """Copy entire directory recursively."""
    src = SRC / rel_path
    dst = DST / rel_path
    if not src.is_dir():
        print(f"  MISSING DIR: {rel_path}")
        return
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))

# =============================================
# 1. ROOT FILES
# =============================================
print("=== Root files ===")
for f in ['main.py', 'requirements.txt', 'requirements-optional.txt', '.gitignore', '.gitattributes']:
    copy_file(f)

# =============================================
# 2. CORE SOURCE CODE
# =============================================
print("\n=== Core source code ===")
copy_dir('src')

# =============================================
# 3. DOCUMENTATION
# =============================================
print("\n=== Documentation ===")
copy_dir('docs')

# =============================================
# 4. SELF-TRAINED MODELS (production checkpoints only)
# =============================================
print("\n=== Self-trained models ===")

# Chest/falsetto models
for f in [
    'ml_dl_models/chest_falsetto/squeezenet_binary/artifacts_mel_safe_v2/best_squeezenet_fourclass.pt',
    'ml_dl_models/chest_falsetto/squeezenet_binary/artifacts_mel_safe_v2/best_squeezenet_binary.pt',
    'ml_dl_models/chest_falsetto/squeezenet_binary/artifacts_mel_safe_v2/training_summary.json',
    'ml_dl_models/chest_falsetto/squeezenet_binary/artifacts_mel_safe_v2/training_summary_fourclass.json',
    'ml_dl_models/chest_falsetto/squeezenet_binary/artifacts_mel_safe_v2/history.csv',
    'ml_dl_models/chest_falsetto/squeezenet_binary/artifacts_mel_safe_v2/history_fourclass.csv',
]:
    copy_file(f)

# Mix binary V6 model (primary)
for f in [
    'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/mix_binary_latefusion_v6_song_level/best_mix_binary_latefusion.pt',
    'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/mix_binary_latefusion_v6_song_level/training_summary.json',
]:
    copy_file(f)

# Breath binary V1 model
for f in [
    'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/breath_binary_latefusion_v1/best_breath_binary_latefusion.pt',
    'ml_dl_models/gtsinger_multitech/lightweight_training/artifacts/breath_binary_latefusion_v1/training_summary.json',
]:
    copy_file(f)

# =============================================
# 5. TRAINING SCRIPTS (for reproducibility)
# =============================================
print("\n=== Training scripts ===")
for f in [
    'ml_dl_models/chest_falsetto/squeezenet_binary/train_squeezenet_binary.py',
    'ml_dl_models/chest_falsetto/squeezenet_binary/train_squeezenet_fourclass.py',
    'ml_dl_models/gtsinger_multitech/lightweight_training/train_mix_binary_squeezenet_latefusion.py',
    'ml_dl_models/gtsinger_multitech/lightweight_training/train_breath_binary_latefusion.py',
    'ml_dl_models/gtsinger_multitech/lightweight_training/prepare_breath_binary_manifest.py',
    'ml_dl_models/gtsinger_multitech/lightweight_training/prepare_female_weighted_manifest.py',
    'ml_dl_models/evaluation/calibrate_temporal_smoothing.py',
    'ml_dl_models/evaluation/evaluate_mix_voice.py',
    'ml_dl_models/evaluation/evaluate_chest_falsetto.py',
]:
    copy_file(f)

# =============================================
# 6. TOOLS
# =============================================
print("\n=== Tools ===")
for f in [
    'tools/spleeter_bridge.py',
]:
    copy_file(f)

# Create download_spleeter_models script
download_script = DST / 'tools' / 'download_spleeter_models.sh'
download_script.parent.mkdir(parents=True, exist_ok=True)
download_script.write_text("""#!/bin/bash
# Download Spleeter pretrained models for MindEcho
# These are third-party models from Deezer Spleeter (MIT license)
# Place them in pretrained_models/ after downloading

set -e

MODEL_DIR="pretrained_models"
BASE_URL="https://github.com/deezer/spleeter/releases/download/v2.0.0"

mkdir -p "$MODEL_DIR"

echo "Downloading Spleeter 2stems model (vocals/accompaniment)..."
curl -L "${BASE_URL}/2stems.tar.gz" -o /tmp/spleeter_2stems.tar.gz
tar -xzf /tmp/spleeter_2stems.tar.gz -C "$MODEL_DIR"
rm /tmp/spleeter_2stems.tar.gz

echo "Done! Models placed in $MODEL_DIR/"
echo ""
echo "To download 4stems and 5stems (optional, larger):"
echo "  curl -L ${BASE_URL}/4stems.tar.gz -o /tmp/spleeter_4stems.tar.gz"
echo "  tar -xzf /tmp/spleeter_4stems.tar.gz -C $MODEL_DIR"
echo "  curl -L ${BASE_URL}/5stems.tar.gz -o /tmp/spleeter_5stems.tar.gz"
echo "  tar -xzf /tmp/spleeter_5stems.tar.gz -C $MODEL_DIR"
""")

download_script_bat = DST / 'tools' / 'download_spleeter_models.bat'
download_script_bat.write_text("""@echo off
REM Download Spleeter pretrained models for MindEcho (Windows)
REM These are third-party models from Deezer Spleeter (MIT license)

set MODEL_DIR=pretrained_models
set BASE_URL=https://github.com/deezer/spleeter/releases/download/v2.0.0

if not exist "%MODEL_DIR%" mkdir "%MODEL_DIR%"

echo Downloading Spleeter 2stems model (vocals/accompaniment)...
curl -L "%BASE_URL%/2stems.tar.gz" -o %TEMP%\spleeter_2stems.tar.gz
tar -xzf %TEMP%\spleeter_2stems.tar.gz -C %MODEL_DIR%
del %TEMP%\spleeter_2stems.tar.gz

echo Done! Models placed in %MODEL_DIR%/
""")

print("\n=== Creating placeholder directories ===")
# Create pretrained_models placeholder with README
pretrained_readme = DST / 'pretrained_models' / 'README.md'
pretrained_readme.parent.mkdir(parents=True, exist_ok=True)
pretrained_readme.write_text("""# Third-Party Pretrained Models

This directory stores third-party models used by MindEcho.

## Spleeter (Deezer) - Vocal/Accompaniment Separation

Used for lead vocal separation in the accompaniment pipeline.

**Download:**
- 2stems (vocals + accompaniment, 76 MB): `https://github.com/deezer/spleeter/releases/download/v2.0.0/2stems.tar.gz`
- 4stems (vocals/drums/bass/other, 152 MB): `https://github.com/deezer/spleeter/releases/download/v2.0.0/4stems.tar.gz`
- 5stems (vocals/drums/bass/piano/other, 190 MB): `https://github.com/deezer/spleeter/releases/download/v2.0.0/5stems.tar.gz`

**Installation:**
1. Download the 2stems archive (minimum required)
2. Extract to `pretrained_models/2stems/`
3. The app automatically detects models in this directory

**License:** MIT (Deezer Spleeter project)
**Source:** https://github.com/deezer/spleeter
""")

# Create recordings placeholder
(DST / 'recordings' / '.gitkeep').parent.mkdir(parents=True, exist_ok=True)
(DST / 'recordings' / '.gitkeep').write_text('')

# =============================================
# 7. CREATE UPDATED .gitignore
# =============================================
print("\n=== Updating .gitignore ===")
gitignore = DST / '.gitignore'
gitignore.write_text("""# Python
__pycache__/
*.py[cod]
*.so
*.egg-info/
dist/
build/
*.egg
.eggs/

# Virtual environments
.venv/
venv/
.venv*/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
Desktop.ini

# Models - third party (download separately)
pretrained_models/2stems/
pretrained_models/4stems/
pretrained_models/5stems/

# User data
recordings/*.wav
recordings/*.json
test_recordings/

# Training data (not for distribution)
ml_dl_models/*/dataset/
ml_dl_models/*/*/dataset/
*.zip
!requirements*.txt

# Temporary files
_tmp*/
*.tmp
*.log

# pytest
.pytest_cache/

# Jupyter
.ipynb_checkpoints/

# Backup files
recovery/
*.bak
""")

print("\n=== Done! ===")
print(f"Release prepared at: {DST}")
