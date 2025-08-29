@echo off
setlocal enableextensions

echo [MindEcho] Spleeter 外部环境配置 (Windows)
echo 目标: 创建 Python 3.10 环境并安装 Spleeter + TensorFlow 2.9.3
echo 若已存在可用环境, 可跳过并设置环境变量 MIND_ECHO_SPLEETER_PY 指向 python.exe
echo.

REM 可选: 使用镜像源加速
REM 优先读取环境变量 MIND_ECHO_PIP_INDEX_URL / MIND_ECHO_PIP_TRUSTED_HOST
REM 也可在运行时加参数: mirror 以启用清华镜像 (例: setup_spleeter_env_windows.bat mirror)
set "PIP_OPTS="
if /i "%~1"=="mirror" (
  if not defined MIND_ECHO_PIP_INDEX_URL set "MIND_ECHO_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
  if not defined MIND_ECHO_PIP_TRUSTED_HOST set "MIND_ECHO_PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn"
)
if defined MIND_ECHO_PIP_INDEX_URL set "PIP_OPTS=%PIP_OPTS% -i %MIND_ECHO_PIP_INDEX_URL%"
if defined MIND_ECHO_PIP_TRUSTED_HOST set "PIP_OPTS=%PIP_OPTS% --trusted-host %MIND_ECHO_PIP_TRUSTED_HOST%"
if defined PIP_OPTS (
  echo 使用镜像参数: %PIP_OPTS%
)

REM 1) 优先使用 conda 创建环境 spleeter310
where conda >nul 2>nul
if errorlevel 1 goto no_conda

:do_conda
echo 检测到 conda, 正在创建/更新环境: spleeter310 ...
conda create -n spleeter310 python=3.10 -y || goto pip_fallback
conda run -n spleeter310 python -m pip install --upgrade pip %PIP_OPTS% || goto pip_fallback
conda run -n spleeter310 python -m pip install tensorflow==2.9.3 spleeter==2.4.0 soundfile==0.12.1 librosa==0.9.2 norbert==0.2.1 %PIP_OPTS% || goto pip_fallback
REM 额外固定与 TF2.9 兼容的科学计算栈，避免 numpy 2.x 冲突
conda run -n spleeter310 python -m pip install numpy==1.23.5 scipy==1.10.1 numba==0.56.4 llvmlite==0.39.1 %PIP_OPTS% || goto pip_fallback
for /f "usebackq tokens=*" %%I in (`conda run -n spleeter310 python -c "import sys;print(sys.executable)"") do set "PYEXE=%%~I"
set "MIND_ECHO_SPLEETER_PY=%PYEXE%"
REM 持久化，便于下次会话使用（需要新开终端才生效）
setx MIND_ECHO_SPLEETER_PY "%PYEXE%" >nul
echo.
echo 已创建/更新 conda 环境: spleeter310
echo MIND_ECHO_SPLEETER_PY(当前会话): %MIND_ECHO_SPLEETER_PY%
goto verify

:no_conda
echo 未检测到 conda, 将尝试使用 py -3.10 + venv 本地环境...
goto pip_fallback

:pip_fallback
echo 使用 venv 回退方案 (.venv_spleeter310)
where py >nul 2>nul
if errorlevel 1 (
  echo 未检测到 Windows 啟動器 py, 请手动安装 Python 3.10 并重试。
  goto fail
)
py -3.10 -m venv .venv_spleeter310 || goto fail
call .venv_spleeter310\Scripts\activate.bat || goto fail
python -m pip install --upgrade pip %PIP_OPTS% || goto fail
python -m pip install tensorflow==2.9.3 spleeter==2.4.0 soundfile==0.12.1 librosa==0.9.2 norbert==0.2.1 %PIP_OPTS% || goto fail
REM 额外固定与 TF2.9 兼容的科学计算栈，避免 numpy 2.x 冲突
python -m pip install numpy==1.23.5 scipy==1.10.1 numba==0.56.4 llvmlite==0.39.1 %PIP_OPTS% || goto fail
for /f "usebackq tokens=*" %%I in (`python -c "import sys;print(sys.executable)"") do set "PYEXE=%%~I"
set "MIND_ECHO_SPLEETER_PY=%PYEXE%"
setx MIND_ECHO_SPLEETER_PY "%PYEXE%" >nul
echo.
echo 已创建 venv: .venv_spleeter310
echo MIND_ECHO_SPLEETER_PY(当前会话): %MIND_ECHO_SPLEETER_PY%
goto verify

:verify
if not defined MIND_ECHO_SPLEETER_PY (
  echo 验证失败: 未设置 MIND_ECHO_SPLEETER_PY。
  goto fail
)
echo 正在验证 Spleeter 安装...
"%MIND_ECHO_SPLEETER_PY%" -c "import importlib; m=importlib.import_module('spleeter'); import sys; print('spleeter:', getattr(m,'__version__','unknown'))" >nul 2>nul
if errorlevel 1 (
  echo 验证失败: 无法导入 spleeter, 请检查安装日志。
  goto fail
)
echo 验证通过: 可用于桥接运行 Spleeter。
echo 如需固定模型目录, 可设置(需要新开终端才生效):
echo   setx SPLEETER_MODEL_PATH "D:\spleeter_models"
echo 或  setx SPLEETER_DATA_PATH "D:\spleeter_models"
echo 运行 MindEcho 再试 Spleeter 分离即可。
goto end

:fail
echo [失败] 未能配置可用的 Spleeter 环境。
echo 请确保:
echo  1) 有 Python 3.10 (或 3.9)
echo  2) 已安装 tensorflow==2.9.3 与 spleeter==2.4.0
echo  3) 将 python.exe 路径写入 MIND_ECHO_SPLEETER_PY（可用 setx 持久化）
exit /b 1

:end
echo 完成。
REM ---- 可选：自动探测并设置本地模型目录（离线模型） ----
REM 如果存在辅助脚本则调用它，以设置 SPLEETER_MODEL_PATH，方便离线模型使用
if exist "%~dp0set_spleeter_model_path.bat" (
  call "%~dp0set_spleeter_model_path.bat"
  echo [可选] 已尝试自动配置本地模型目录（SPLEETER_MODEL_PATH）。
) else (
  echo [提示] 可创建 tools\set_spleeter_model_path.bat 以自动设置本地模型目录。
)
exit /b 0
