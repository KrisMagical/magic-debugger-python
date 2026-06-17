#!/bin/bash
# Magic Debug startup script for the GDB DAP backend.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required"
    exit 1
fi

if ! python3 -c "from adapters.gdb import *" &> /dev/null; then
    echo "Error: Magic Debug GDB adapter cannot be imported"
    exit 1
fi

python3 main.py doctor
doctor_status=$?
if [ "$doctor_status" -eq 2 ]; then
    echo "Error: Magic Debug doctor reported blocking errors"
    exit 1
fi

if ! command -v gdb &> /dev/null; then
    echo "Error: gdb is required for the Magic Debug GDB DAP backend"
    echo "  macOS: brew install gdb"
    echo "  Linux: apt install gdb"
    exit 1
fi

echo "Using GDB DAP backend:"
gdb --version | head -n 1

exec python3 main.py "$@"
