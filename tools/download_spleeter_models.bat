@echo off
setlocal enableextensions
REM 下载并解压 Spleeter 2stems 模型，支持镜像、多下载器回退、或使用本地文件
REM 用法：download_spleeter_models.bat [目标目录] [模型URL或本地文件路径]
REM 示例：download_spleeter_models.bat D:\spleeter_models https://github.com/deezer/spleeter/releases/download/v2.0.0/2stems.tar.gz

set "DEST=%~1"
if not defined DEST set "DEST=D:\spleeter_models"

set "SRC=%~2"
if not defined SRC set "SRC=https://github.com/deezer/spleeter/releases/download/v2.0.0/2stems.tar.gz"

echo 目标目录: %DEST%
echo 来源: %SRC%

if not exist "%DEST%" mkdir "%DEST%" 2>nul

set "TMPFILE=%TEMP%\spleeter_2stems.tar.gz"
if exist "%TMPFILE%" del /q "%TMPFILE%" >nul 2>&1

REM 如果第二参数是本地文件，则直接复制到临时文件
if exist "%SRC%" (
  echo 使用本地文件作为来源: %SRC%
  copy /y "%SRC%" "%TMPFILE%" >nul
  goto :extract
)

echo 正在下载模型...
REM 构造候选下载地址（优先使用用户提供的）
set "U1=%SRC%"
set "U2=https://cdn.jsdelivr.net/gh/deezer/spleeter@v2.0.0/pretrained_models/2stems.tar.gz"
set "U3=https://github.moeyy.xyz/https://github.com/deezer/spleeter/releases/download/v2.0.0/2stems.tar.gz"
set "U4=https://ghproxy.com/https://github.com/deezer/spleeter/releases/download/v2.0.0/2stems.tar.gz"
set "U5=https://ghproxy.net/https://github.com/deezer/spleeter/releases/download/v2.0.0/2stems.tar.gz"
set "U6=https://github.com/deezer/spleeter/releases/download/v2.0.0/2stems.tar.gz"

call :try_download "%U1%"
if not exist "%TMPFILE%" call :try_download "%U2%"
if not exist "%TMPFILE%" call :try_download "%U3%"
if not exist "%TMPFILE%" call :try_download "%U4%"
if not exist "%TMPFILE%" call :try_download "%U5%"
if not exist "%TMPFILE%" call :try_download "%U6%"

if not exist "%TMPFILE%" (
  echo 下载失败。你可以提供镜像URL作为第二个参数重试，或将压缩包手动下载后作为第二参数传入本脚本。
  goto :end
)

:extract
echo 解压中...
tar -xf "%TMPFILE%" -C "%DEST%" 2>nul
if errorlevel 1 (
  echo tar 解压失败，尝试使用 Python 解压...
  for %%P in (python3 python py) do (
    %%P "%~dp0extract_tar_gz.py" "%TMPFILE%" "%DEST%" && goto :post_extract
  )
  echo 解压失败，请确认系统支持 tar 或 Python；也可以手动解压 %TMPFILE% 到 %DEST% 。
  goto :end
)

:post_extract

if exist "%DEST%\2stems" (
  setx SPLEETER_MODEL_PATH "%DEST%" >nul
  echo 已解压完成，并设置 SPLEETER_MODEL_PATH=%DEST%
) else (
  echo 未在 "%DEST%" 下找到 2stems 目录，请检查压缩包内容或更换URL。
)

goto :end

:: 子程序：尝试多种下载方式
:try_download
setlocal
set "DLURL=%~1"
if not defined DLURL exit /b 0
echo 尝试: %DLURL%

REM 优先使用 aria2c（如可用，速度更快）
where aria2c >nul 2>&1
if not errorlevel 1 (
  aria2c -x 16 -s 16 -k 1M -o "%TMPFILE%" "%DLURL%"
  if exist "%TMPFILE%" ( endlocal & exit /b 0 )
)

REM 其次使用 curl（Windows 10+ 自带）
where curl >nul 2>&1
if not errorlevel 1 (
  curl -fL --retry 5 --retry-all-errors --connect-timeout 20 -o "%TMPFILE%" "%DLURL%"
  if exist "%TMPFILE%" ( endlocal & exit /b 0 )
)

REM 回退到 PowerShell Invoke-WebRequest
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%DLURL%' -OutFile '%TMPFILE%' -UseBasicParsing -TimeoutSec 1800; exit 0 } catch { exit 1 }"
if exist "%TMPFILE%" ( endlocal & exit /b 0 )

REM 最后尝试 BITS（更适合断点续传，但某些环境被禁用）
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Start-BitsTransfer -Source '%DLURL%' -Destination '%TMPFILE%' -ErrorAction Stop; exit 0 } catch { exit 1 }"
endlocal & exit /b 0

:end
endlocal & exit /b 0

