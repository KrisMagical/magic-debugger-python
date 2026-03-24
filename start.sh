#!/bin/bash
# Magic Debug 启动脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required"
    exit 1
fi

# 检查 LLDB
if ! command -v lldb-dap &> /dev/null && ! command -v lldb &> /dev/null; then
    echo "Warning: LLDB not found. Please install it first."
    echo "  macOS: xcode-select --install"
    echo "  Linux: apt install lldb"
fi

# 启动服务器
exec python3 main.py "$@"
