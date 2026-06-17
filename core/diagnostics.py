"""Runtime diagnostics for Magic Debug."""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from server.rpc import DEFAULT_RPC_HOST, DEFAULT_RPC_PORT, resolve_rpc_endpoint


RESULT_EXIT_CODES = {
    "ok": 0,
    "warn": 1,
    "error": 2,
}


def check(
    name: str,
    status: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "message": message,
        "details": details or {},
    }


def result_exit_code(result: str) -> int:
    return RESULT_EXIT_CODES.get(result, 2)


def summarize_checks(checks: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {"ok": 0, "warn": 0, "error": 0}
    for item in checks:
        summary[item["status"]] = summary.get(item["status"], 0) + 1
    return summary


def overall_result(checks: List[Dict[str, Any]]) -> str:
    if any(item["status"] == "error" for item in checks):
        return "error"
    if any(item["status"] == "warn" for item in checks):
        return "warn"
    return "ok"


def can_bind_port(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, int(port)))
        except OSError:
            return False
    return True


def default_log_dir(env: Optional[Dict[str, str]] = None) -> Path:
    env = env or os.environ

    def root_is_writable(root_value: Optional[str]) -> bool:
        if not root_value:
            return False
        root = Path(root_value)
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / ".magic-debug-write-test"
            probe.mkdir(exist_ok=True)
            probe.rmdir()
            return True
        except Exception:
            return False

    if sys.platform.startswith("win"):
        roots = [
            env.get("LOCALAPPDATA"),
            env.get("APPDATA"),
            tempfile.gettempdir(),
            str(Path.home()),
        ]
        for root in roots:
            if root_is_writable(root):
                return Path(root) / "magic-debug" / "logs"
        return Path(tempfile.gettempdir()) / "magic-debug" / "logs"

    state_home = env.get("XDG_STATE_HOME")
    if root_is_writable(state_home):
        return Path(state_home) / "magic-debug" / "logs"
    local_state = Path.home() / ".local" / "state"
    if root_is_writable(str(local_state)):
        return local_state / "magic-debug" / "logs"
    if root_is_writable(tempfile.gettempdir()):
        return Path(tempfile.gettempdir()) / "magic-debug" / "logs"
    return Path.home() / ".local" / "state" / "magic-debug" / "logs"


def check_log_dir(path: Optional[Path] = None) -> Dict[str, Any]:
    log_dir = path or default_log_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        probe = log_dir / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:
        return check(
            "log_dir",
            "error",
            f"Log directory is not writable: {log_dir}",
            {"path": str(log_dir), "error": str(exc)},
        )
    return check("log_dir", "ok", f"Log directory is writable: {log_dir}", {"path": str(log_dir)})


def detect_config_file(cwd: Optional[Path] = None) -> Dict[str, Any]:
    base = cwd or Path.cwd()
    candidates = [base / "magic-debug.json", base / ".magic-debug.json"]
    for candidate in candidates:
        if candidate.exists():
            return check(
                "config_file",
                "ok",
                f"Found config file: {candidate}",
                {"path": str(candidate)},
            )
    return check(
        "config_file",
        "ok",
        "No local config file found",
        {"searched": [str(candidate) for candidate in candidates]},
    )


def gdb_version(gdb_path: str) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            [gdb_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return check("gdb_version", "warn", "Could not read gdb version", {"error": str(exc)})

    if result.returncode != 0:
        return check(
            "gdb_version",
            "warn",
            "gdb --version failed",
            {"stderr": result.stderr.strip()},
        )
    first_line = result.stdout.splitlines()[0] if result.stdout else "unknown"
    return check("gdb_version", "ok", first_line, {"version": result.stdout.strip()})


def gdb_dap_support(gdb_path: Optional[str]) -> Dict[str, Any]:
    if not gdb_path:
        return check("gdb_dap", "warn", "Cannot check GDB DAP support without gdb")

    try:
        result = subprocess.run(
            [gdb_path, "--interpreter=dap", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return check("gdb_dap", "warn", "Could not check GDB DAP support", {"error": str(exc)})

    if result.returncode != 0:
        return check(
            "gdb_dap",
            "warn",
            "gdb --interpreter=dap appears unavailable",
            {"stderr": result.stderr.strip(), "stdout": result.stdout.strip()},
        )
    return check("gdb_dap", "ok", "gdb --interpreter=dap appears available")


def run_doctor(
    rpc_transport: str = "auto",
    rpc_host: str = DEFAULT_RPC_HOST,
    rpc_port: int = DEFAULT_RPC_PORT,
    rpc_socket_path: Optional[str] = None,
    http_host: str = DEFAULT_RPC_HOST,
    http_port: int = 8765,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    py_version = platform.python_version()
    checks.append(check(
        "python",
        "ok" if sys.version_info >= (3, 8) else "error",
        f"Python {py_version}",
        {"version": py_version, "executable": sys.executable},
    ))

    checks.append(check(
        "platform",
        "ok",
        platform.platform(),
        {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
    ))

    gdb_path = shutil.which("gdb")
    if gdb_path:
        checks.append(check("gdb_path", "ok", f"Found gdb: {gdb_path}", {"path": gdb_path}))
        checks.append(gdb_version(gdb_path))
    else:
        checks.append(check("gdb_path", "warn", "gdb not found; real debugging will be unavailable"))
        checks.append(check("gdb_version", "warn", "Skipping gdb version because gdb was not found"))
    checks.append(gdb_dap_support(gdb_path))

    try:
        endpoint = resolve_rpc_endpoint(
            transport=rpc_transport,
            host=rpc_host,
            port=rpc_port,
            socket_path=rpc_socket_path,
            env=env,
        )
        checks.append(check(
            "rpc_transport",
            "ok",
            f"RPC endpoint resolves to {endpoint.url()}",
            {
                "transport": endpoint.transport,
                "host": endpoint.host,
                "port": endpoint.port,
                "socket_path": endpoint.socket_path,
            },
        ))
    except Exception as exc:
        checks.append(check("rpc_transport", "error", "RPC transport resolution failed", {"error": str(exc)}))

    http_available = can_bind_port(http_host, http_port)
    checks.append(check(
        "http_port",
        "ok" if http_available else "warn",
        f"HTTP port {http_host}:{http_port} is {'available' if http_available else 'in use'}",
        {"host": http_host, "port": http_port},
    ))

    rpc_available = can_bind_port(rpc_host, rpc_port)
    checks.append(check(
        "rpc_port",
        "ok" if rpc_available else "warn",
        f"RPC TCP port {rpc_host}:{rpc_port} is {'available' if rpc_available else 'in use'}",
        {"host": rpc_host, "port": rpc_port},
    ))

    checks.append(detect_config_file())
    checks.append(check_log_dir())
    checks.append(check(
        "entrypoint",
        "ok",
        "magic-debug CLI entrypoint is configured",
        {"argv0": sys.argv[0], "version": "1.0.0"},
    ))

    result = overall_result(checks)
    return {
        "result": result,
        "checks": checks,
        "summary": summarize_checks(checks),
    }


def format_doctor_report(report: Dict[str, Any]) -> str:
    lines = ["Magic Debug doctor", ""]
    for item in report["checks"]:
        lines.append(f"[{item['status'].upper()}] {item['name']}: {item['message']}")
    lines.append("")
    lines.append(
        "Summary: "
        f"ok={report['summary'].get('ok', 0)} "
        f"warn={report['summary'].get('warn', 0)} "
        f"error={report['summary'].get('error', 0)}"
    )
    lines.append(f"Result: {report['result']}")
    return "\n".join(lines)


def report_to_json(report: Dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)
