"""Consistency checks for the GDB-backed project naming."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_gdb_adapter_importable():
    import adapters.gdb as gdb

    assert gdb.GDBAdapter is not None


def test_lldb_adapter_is_not_present():
    assert not (ROOT / "adapters" / "lldb.py").exists()


def test_makefile_does_not_reference_missing_lldb_adapter():
    content = read_text("Makefile")
    assert "adapters.lldb" not in content


def test_start_script_does_not_reference_missing_lldb_adapter():
    content = read_text("start.sh")
    assert "adapters.lldb" not in content
    assert "lldb-dap" not in content


def test_dap_adapter_id_is_gdb():
    content = read_text("core/dap.py")
    assert "lldb-dap" not in content
    assert 'DEFAULT_ADAPTER_ID = "gdb"' in content


def test_pyproject_keywords_do_not_include_lldb():
    content = read_text("pyproject.toml").lower()
    assert "lldb" not in content
    assert "gdb" in content


def test_readme_does_not_require_lldb_dap():
    content = read_text("README.md")
    assert "lldb-dap" not in content
    assert "adapters.lldb" not in content
