@echo off
setlocal enableextensions
set FOUND=
set "C1=%USERPROFILE%\.cache\spleeter\models\2stems"
set "C2=%LOCALAPPDATA%\spleeter\models\2stems"
set "C3=%APPDATA%\spleeter\models\2stems"
set "C4=D:\spleeter_models\2stems"
set "C5=D:\AI\models\spleeter\2stems"
set "C6=%USERPROFILE%\spleeter_models\2stems"

for %%P in ("%C1%" "%C2%" "%C3%" "%C4%" "%C5%" "%C6%") do (
  if exist %%~P (
    echo Found: %%~P
    set FOUND=1
  )
)

if not defined FOUND echo 未发现常见位置的 2stems 模型目录
endlocal & exit /b 0

