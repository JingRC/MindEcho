@echo off
setlocal enableextensions
REM 从可移动盘或指定目录导入已存在的 Spleeter 2stems 模型
REM 用法：import_spleeter_models_from_usb.bat [可选:源目录] [可选:目标目录]
REM 默认目标目录：D:\spleeter_models

set "SRC=%~1"
set "DEST=%~2"
if not defined DEST set "DEST=D:\spleeter_models"

if not defined SRC (
  echo 未指定来源，将扫描常见U盘/移动盘路径...
  for %%D in (D E F G H I J K L M N O P Q R S T U V W X Y Z) do (
    if exist "%%D:\2stems" set "SRC=%%D:\" & goto :found
    if exist "%%D:\spleeter_models\2stems" set "SRC=%%D:\spleeter_models" & goto :found
    if exist "%%D:\AI\models\spleeter\2stems" set "SRC=%%D:\AI\models\spleeter" & goto :found
  )
)

:found
if not defined SRC (
  echo 未找到包含 2stems 的来源目录，请指定来源：
  echo   import_spleeter_models_from_usb.bat ^<来源目录^> [目标目录]
  exit /b 1
)

REM 规范化：若来源指向的是 2stems 上级目录或其父级，均可接受
if exist "%SRC%\2stems" (
  echo 检测到来源：%SRC%
) else if exist "%SRC%\models\2stems" (
  set "SRC=%SRC%\models"
  echo 调整来源到：%SRC%
) else if exist "%SRC%\pretrained_models\2stems" (
  set "SRC=%SRC%\pretrained_models"
  echo 调整来源到：%SRC%
) else (
  echo 来源目录不包含 2stems：%SRC%
  exit /b 2
)

if /I "%SRC%"=="%DEST%" (
  echo 来源与目标相同，直接设置环境变量...
  setx SPLEETER_MODEL_PATH "%DEST%" >nul
  echo 已设置 SPLEETER_MODEL_PATH=%DEST%
  exit /b 0
)

if not exist "%DEST%" mkdir "%DEST%" 2>nul
echo 正在复制模型到 %DEST% ...(可能需要数分钟)
xcopy "%SRC%\2stems" "%DEST%\2stems\" /E /I /Y >nul
if errorlevel 1 (
  echo 复制失败，请检查读写权限或磁盘空间。
  exit /b 3
)

if exist "%DEST%\2stems" (
  setx SPLEETER_MODEL_PATH "%DEST%" >nul
  echo 导入完成，已设置 SPLEETER_MODEL_PATH=%DEST%
  exit /b 0
) else (
  echo 复制后仍未找到 %DEST%\2stems ，请重试或手动复制。
  exit /b 4
)

