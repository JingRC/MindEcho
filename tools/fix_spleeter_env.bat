@echo off
setlocal enableextensions enabledelayedexpansion
set PYTHONUTF8=1
chcp 65001 >nul
echo [MindEcho] 外部 Spleeter 环境修复与冒烟测试

REM 可选镜像
set "PIP_OPTS="
if /i "%~1"=="mirror" (
  set "PIP_OPTS=-i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn"
)

if not defined MIND_ECHO_SPLEETER_PY (
  echo [错误] 未设置 MIND_ECHO_SPLEETER_PY，请先将其指向外部 python.exe。
  exit /b 1
)
if not exist "%MIND_ECHO_SPLEETER_PY%" (
  echo [错误] MIND_ECHO_SPLEETER_PY 指向的 python.exe 不存在:
  echo   %MIND_ECHO_SPLEETER_PY%
  exit /b 1
)
echo 使用解释器: %MIND_ECHO_SPLEETER_PY%

echo [1/3] 检查是否已安装 spleeter ...
for /f "usebackq delims=" %%A in (`"%MIND_ECHO_SPLEETER_PY%" -c "import importlib;print('YES' if importlib.util.find_spec('spleeter') else 'NO')" 2^>nul`) do set HAS_SPLEETER=%%A
if /i not "%HAS_SPLEETER%"=="YES" (
  echo  - 未检测到 spleeter，开始安装依赖...
  "%MIND_ECHO_SPLEETER_PY%" -m pip install --upgrade pip wheel setuptools %PIP_OPTS% || goto :fail
  "%MIND_ECHO_SPLEETER_PY%" -m pip install numpy==1.23.5 scipy==1.10.1 numba==0.56.4 llvmlite==0.39.1 %PIP_OPTS% || goto :fail
  "%MIND_ECHO_SPLEETER_PY%" -m pip install tensorflow==2.9.3 %PIP_OPTS% || goto :fail
  "%MIND_ECHO_SPLEETER_PY%" -m pip install spleeter==2.4.0 soundfile==0.12.1 librosa==0.9.2 norbert==0.2.1 %PIP_OPTS% || goto :fail
  echo  - 安装完成。
) else (
  echo  - 已检测到 spleeter（略过安装）。
)

echo [2/3] 配置本地模型目录（会话内）...
set "SPLEETER_MODEL_PATH=D:\-MindEcho-main\pretrained_models"
echo  - SPLEETER_MODEL_PATH=%SPLEETER_MODEL_PATH%

echo [3/3] 运行冒烟测试（2stems）...
if not exist tools\test_tone.wav (
  "%MIND_ECHO_SPLEETER_PY%" tools\gen_test_wav.py || goto :fail
)
"%MIND_ECHO_SPLEETER_PY%" tools\spleeter_bridge.py --input "tools\test_tone.wav" --vocals "out_vocal.wav" --acc "out_acc.wav" --sr 44100 --stems 2 --model_dir "%SPLEETER_MODEL_PATH%" || goto :fail
if exist out_vocal.wav if exist out_acc.wav (
  echo ✅ 冒烟测试成功：已生成 out_vocal.wav / out_acc.wav
  goto :end
)

:fail
echo ❌ 失败，请查看上方错误日志。
exit /b 1

:end
echo 完成。
endlocal & exit /b 0
