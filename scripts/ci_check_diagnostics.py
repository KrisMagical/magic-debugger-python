import json
import subprocess
import sys
from typing import Any, Dict


def diagnostics_exit_code(payload: Dict[str, Any], process_returncode: int) -> int:
    status = payload.get("result")

    if status == "error" or process_returncode == 2:
        return 2
    if status in {"ok", "warn"}:
        return 0
    return 2


def run_diagnostics(command):
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Diagnostics did not output valid JSON", file=sys.stderr)
        return 2

    exit_code = diagnostics_exit_code(payload, result.returncode)
    if exit_code == 2:
        print("Diagnostics returned error status", file=sys.stderr)
    return exit_code


def main():
    # CI runners may not have gdb or GDB DAP available. That is a valid
    # diagnostics warning, while a diagnostics error should still fail CI.
    return run_diagnostics([sys.executable, "main.py", "--check", "--json"])


if __name__ == "__main__":
    raise SystemExit(main())
