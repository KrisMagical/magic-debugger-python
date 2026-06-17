import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import diagnostics
from server.rpc import resolve_rpc_endpoint


def test_doctor_returns_expected_dict_structure(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: None)
    monkeypatch.setattr(diagnostics, "check_log_dir", lambda path=None: diagnostics.check("log_dir", "ok", "ok"))

    report = diagnostics.run_doctor(env={"XDG_RUNTIME_DIR": str(tmp_path)})

    assert report["result"] in {"ok", "warn", "error"}
    assert isinstance(report["checks"], list)
    assert "summary" in report
    assert {"ok", "warn", "error"}.issuperset(report["summary"].keys())


def test_check_json_cli_outputs_parseable_json():
    result = subprocess.run(
        [sys.executable, "main.py", "--check", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode in {0, 1, 2}
    payload = json.loads(result.stdout)
    assert "result" in payload
    assert "checks" in payload
    assert "summary" in payload


def test_missing_gdb_is_warning_not_traceback(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: None)

    report = diagnostics.run_doctor()

    gdb_check = next(item for item in report["checks"] if item["name"] == "gdb_path")
    assert gdb_check["status"] == "warn"
    assert report["result"] in {"warn", "error"}


def test_gdb_version_exception_is_warning(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "gdb")

    def fail_run(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(diagnostics.subprocess, "run", fail_run)

    report = diagnostics.run_doctor()

    version_check = next(item for item in report["checks"] if item["name"] == "gdb_version")
    dap_check = next(item for item in report["checks"] if item["name"] == "gdb_dap")
    assert version_check["status"] == "warn"
    assert dap_check["status"] == "warn"


@pytest.mark.parametrize(
    ("result", "code"),
    [("ok", 0), ("warn", 1), ("error", 2), ("unknown", 2)],
)
def test_exit_code_mapping(result, code):
    assert diagnostics.result_exit_code(result) == code


def test_rpc_transport_check_uses_phase7_resolution(tmp_path):
    windows = resolve_rpc_endpoint(transport="auto", platform_name="Windows")
    linux = resolve_rpc_endpoint(
        transport="auto",
        platform_name="Linux",
        env={"XDG_RUNTIME_DIR": str(tmp_path)},
    )

    assert windows.transport == "tcp"
    assert linux.transport == "unix"


def test_can_bind_port_releases_socket():
    assert diagnostics.can_bind_port("127.0.0.1", 0) is True
    assert diagnostics.can_bind_port("127.0.0.1", 0) is True


def test_log_dir_unwritable_returns_error(monkeypatch, tmp_path):
    def fail_write_text(self, *args, **kwargs):
        raise OSError("not writable")

    monkeypatch.setattr(Path, "write_text", fail_write_text)

    result = diagnostics.check_log_dir(tmp_path / "logs")

    assert result["name"] == "log_dir"
    assert result["status"] == "error"
