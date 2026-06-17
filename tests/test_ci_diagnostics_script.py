import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ci_check_diagnostics import diagnostics_exit_code  # noqa: E402


def test_ok_result_passes_ci():
    assert diagnostics_exit_code({"result": "ok"}, 0) == 0


def test_warn_result_with_warn_exit_passes_ci():
    assert diagnostics_exit_code({"result": "warn"}, 1) == 0


def test_error_result_fails_ci():
    assert diagnostics_exit_code({"result": "error"}, 2) == 2


def test_warn_result_with_zero_exit_passes_ci():
    assert diagnostics_exit_code({"result": "warn"}, 0) == 0


def test_unexpected_result_fails_ci():
    assert diagnostics_exit_code({"result": "unknown"}, 0) == 2


def test_process_error_exit_fails_even_with_warn_payload():
    assert diagnostics_exit_code({"result": "warn"}, 2) == 2
