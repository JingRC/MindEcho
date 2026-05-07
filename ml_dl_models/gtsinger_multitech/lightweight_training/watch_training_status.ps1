[CmdletBinding()]
param(
    [string]$ArtifactDir = "d:\-MindEcho-main\ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\multitech_focus3_squeezenet_v3_gpu",
    [string]$LogPath = "d:\-MindEcho-main\ml_dl_models\gtsinger_multitech\lightweight_training\artifacts\multitech_focus3_squeezenet_v3_gpu\training_watch.log",
    [int]$PollSeconds = 60,
    [switch]$StopWhenSummaryPresent = $true
)

if (-not (Test-Path $ArtifactDir)) {
    New-Item -ItemType Directory -Path $ArtifactDir | Out-Null
}

while ($true) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $gpuLine = "gpu=unavailable"
    try {
        $gpuLine = nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1
        if (-not $gpuLine) {
            $gpuLine = "gpu=unavailable"
        }
    } catch {
        $gpuLine = "gpu=unavailable"
    }

    $files = @()
    try {
        $files = Get-ChildItem -Path $ArtifactDir -File | Sort-Object LastWriteTime -Descending
    } catch {
        $files = @()
    }

    $bestCheckpoint = $files | Where-Object { $_.Name -eq 'best_multitech_squeezenet.pt' } | Select-Object -First 1
    $summaryFile = $files | Where-Object { $_.Name -eq 'training_summary.json' } | Select-Object -First 1

    $parts = @()
    $parts += $timestamp
    $parts += "gpu=$gpuLine"
    if ($bestCheckpoint) {
        $parts += "ckpt_time=$($bestCheckpoint.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))"
        $parts += "ckpt_size=$($bestCheckpoint.Length)"
    } else {
        $parts += "ckpt=none"
    }
    if ($summaryFile) {
        $parts += "summary_time=$($summaryFile.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))"
        $parts += "summary_size=$($summaryFile.Length)"
    } else {
        $parts += "summary=none"
    }

    $line = ($parts -join ' | ')
    Add-Content -Path $LogPath -Value $line
    Write-Output $line
    if ($StopWhenSummaryPresent -and $summaryFile) {
        break
    }
    Start-Sleep -Seconds $PollSeconds
}