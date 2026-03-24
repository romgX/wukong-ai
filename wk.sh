#!/usr/bin/env bash
# ──────────────────────────────────────────────
#  悟空邀请码自动抢码工具 启动脚本
#  macOS / Linux / Windows(Git Bash/WSL) 通用
#  用法: bash wk.sh
# ──────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PY_SCRIPT="$SCRIPT_DIR/grab_code.py"

# ── 颜色 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[wk]${NC} $1"; }
warn() { echo -e "${YELLOW}[wk]${NC} $1"; }
err() { echo -e "${RED}[wk]${NC} $1"; }

# ── 检测 Python ──
find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 8 ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

install_python() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            log "使用 Homebrew 安装 Python..."
            brew install python3
        else
            err "请先安装 Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            err "或手动安装 Python: https://www.python.org/downloads/"
            exit 1
        fi
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
        log "正在下载 Python 安装包..."
        PY_URL="https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
        PY_INSTALLER="$TEMP/python_installer.exe"
        curl -L -o "$PY_INSTALLER" "$PY_URL"
        log "启动 Python 安装程序 (请勾选 'Add to PATH')..."
        "$PY_INSTALLER" /passive InstallAllUsers=0 PrependPath=1 Include_pip=1
        rm -f "$PY_INSTALLER"
        warn "安装完成后请重新打开终端再运行 bash wk.sh"
        exit 0
    else
        # Linux
        if command -v apt-get &>/dev/null; then
            sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
        elif command -v yum &>/dev/null; then
            sudo yum install -y python3 python3-pip
        else
            err "请手动安装 Python 3.8+: https://www.python.org/downloads/"
            exit 1
        fi
    fi
}

# ── 1. 检查 Python ──
PYTHON=$(find_python || true)
if [ -z "$PYTHON" ]; then
    warn "未检测到 Python 3.8+"
    read -rp "是否自动安装 Python? (y/n): " ans
    if [[ "$ans" =~ ^[Yy] ]]; then
        install_python
        PYTHON=$(find_python || true)
        if [ -z "$PYTHON" ]; then
            err "Python 安装失败，请手动安装"
            exit 1
        fi
    else
        err "需要 Python 3.8+ 才能运行"
        exit 1
    fi
fi
log "Python: $($PYTHON --version) ($PYTHON)"

# ── 2. 创建虚拟环境 & 安装依赖 ──
if [ ! -d "$VENV_DIR" ]; then
    log "创建虚拟环境..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

# 激活虚拟环境
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    source "$VENV_DIR/Scripts/activate"
else
    source "$VENV_DIR/bin/activate"
fi

# 检查 playwright 是否已安装
if ! python -c "import playwright" &>/dev/null; then
    log "安装 playwright..."
    pip install --quiet playwright
    log "安装 Chromium 浏览器..."
    python -m playwright install chromium
fi

log "依赖就绪"

# ── 3. 启动主程序 (终端关闭时自动结束) ──
log "启动抢码工具... (关闭此窗口自动停止)"

# 捕获终端关闭信号，清理子进程
cleanup() {
    log "收到退出信号，正在停止..."
    kill "$PY_PID" 2>/dev/null
    wait "$PY_PID" 2>/dev/null
    log "已停止"
    exit 0
}
trap cleanup EXIT INT TERM HUP

python -u "$PY_SCRIPT" &
PY_PID=$!
wait "$PY_PID"
