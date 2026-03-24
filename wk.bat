@echo off
chcp 65001 >nul 2>&1
title 悟空AI邀请码自动抢码工具
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "PY_SCRIPT=%SCRIPT_DIR%grab_code.py"

echo ============================================
echo   悟空AI邀请码自动抢码工具
echo   关闭此窗口自动停止
echo ============================================

:: ── 1. 检查 Python ──
set "PYTHON="
where python >nul 2>&1 && (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    set "PYTHON=python"
)
if not defined PYTHON (
    where python3 >nul 2>&1 && (
        for /f "tokens=2 delims= " %%v in ('python3 --version 2^>^&1') do set "PY_VER=%%v"
        set "PYTHON=python3"
    )
)

if not defined PYTHON (
    echo [wk] 未检测到 Python
    set /p "ans=是否自动安装 Python? (y/n): "
    if /i "!ans!"=="y" (
        echo [wk] 正在下载 Python 安装程序...
        powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"
        echo [wk] 启动安装 (请勾选 Add to PATH)...
        "%TEMP%\python_installer.exe" /passive InstallAllUsers=0 PrependPath=1 Include_pip=1
        del "%TEMP%\python_installer.exe"
        echo [wk] 安装完成，请重新打开此窗口再运行 wk.bat
        pause
        exit /b
    ) else (
        echo [wk] 需要 Python 3.8+ 才能运行
        pause
        exit /b 1
    )
)

echo [wk] Python: %PY_VER% (%PYTHON%)

:: ── 2. 创建虚拟环境 & 安装依赖 ──
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [wk] 创建虚拟环境...
    %PYTHON% -m venv "%VENV_DIR%"
)

call "%VENV_DIR%\Scripts\activate.bat"

python -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo [wk] 安装 playwright...
    pip install --quiet playwright
    echo [wk] 安装 Chromium 浏览器...
    python -m playwright install chromium
)

echo [wk] 依赖就绪

:: ── 3. 启动主程序 ──
echo [wk] 启动抢码工具...
python -u "%PY_SCRIPT%"

pause
