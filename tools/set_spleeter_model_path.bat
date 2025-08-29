@echo off
setlocal enableextensions
REM 自动探测本机 Spleeter 模型目录并设置环境变量 SPLEETER_MODEL_PATH

if defined SPLEETER_MODEL_PATH (
  if exist "%SPLEETER_MODEL_PATH%\2stems" (
    echo 已存在 SPLEETER_MODEL_PATH=%SPLEETER_MODEL_PATH%
    goto :end
  )
)

set "MODEL_DIR="
if exist "%USERPROFILE%\.cache\spleeter\models\2stems" set "MODEL_DIR=%USERPROFILE%\.cache\spleeter\models"
if not defined MODEL_DIR if exist "%LOCALAPPDATA%\spleeter\models\2stems" set "MODEL_DIR=%LOCALAPPDATA%\spleeter\models"
if not defined MODEL_DIR if exist "%APPDATA%\spleeter\models\2stems" set "MODEL_DIR=%APPDATA%\spleeter\models"
if not defined MODEL_DIR if exist "D:\spleeter_models\2stems" set "MODEL_DIR=D:\spleeter_models"
if not defined MODEL_DIR if exist "D:\AI\models\spleeter\2stems" set "MODEL_DIR=D:\AI\models\spleeter"
if not defined MODEL_DIR if exist "%USERPROFILE%\spleeter_models\2stems" set "MODEL_DIR=%USERPROFILE%\spleeter_models"

if defined MODEL_DIR (
  set "SPLEETER_MODEL_PATH=%MODEL_DIR%"
  setx SPLEETER_MODEL_PATH "%MODEL_DIR%" >nul
  echo 已自动设置 SPLEETER_MODEL_PATH=%MODEL_DIR%
) else (
  echo 未找到本地模型目录, 如需离线使用可将模型放到 D:\spleeter_models 并包含子目录 "2stems"。
)

:end
endlocal & exit /b 0

