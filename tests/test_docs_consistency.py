import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read_readme():
    return (ROOT / "README.md").read_text(encoding="utf-8")


def read_readme_lower():
    return read_readme().lower()


def test_readme_exists():
    assert (ROOT / "README.md").exists()


def test_readme_documents_gdb_dap_backend():
    content = read_readme_lower()

    assert "gdb dap" in content
    assert "gdb --interpreter=dap" in content


def test_readme_documents_doctor_and_json_check():
    content = read_readme_lower()

    assert "magic-debug doctor" in content
    assert "magic-debug --check --json" in content


def test_readme_documents_rpc_transports_and_platform_defaults():
    content = read_readme_lower()

    assert "auto" in content
    assert "unix" in content
    assert "tcp" in content
    assert "windows" in content
    assert "tcp" in content
    assert "linux/macos" in content
    assert "unix domain socket" in content


def test_readme_does_not_present_lldb_as_current_requirement():
    content = read_readme_lower()

    assert "install lldb-dap" not in content
    assert "adapters.lldb" not in content


def test_readme_documents_config_and_plugin_commands():
    content = read_readme()

    assert "magic-debug.json" in content
    assert ".magic-debug.json" in content
    assert ":MagicDebugLogs" in content
    assert ":MagicDebugReconnect" in content


def test_readme_documents_testing_commands_and_e2e_skip():
    content = read_readme_lower()

    assert "pytest tests/ -q" in content
    assert "pytest tests/test_e2e_gdb_dap.py -q -rs" in content
    assert "skip" in content
    assert "gcc" in content
    assert "gdb" in content


def test_readme_documents_current_limitations():
    content = read_readme_lower()

    assert "current limitations" in content
    assert "runinterminal" in content
    assert "named pipe" in content
    assert "not implemented" in content


def test_readme_documents_beta_release_materials():
    content = read_readme_lower()

    assert "beta" in content
    assert "release_notes.md" in content or "release notes" in content
    assert "docs/beta-checklist.md" in content or "beta validation checklist" in content


def test_beta_release_documents_exist():
    assert (ROOT / "docs" / "beta-checklist.md").exists()
    assert (ROOT / "RELEASE_NOTES.md").exists()
    assert (ROOT / "CHANGELOG.md").exists()


def test_release_notes_describe_beta_and_limitations():
    content = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8").lower()

    assert "v0.1.0-beta" in content
    assert "known limitations" in content
    assert "gdb --interpreter=dap" in content


def test_changelog_describes_beta():
    content = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").lower()

    assert "v0.1.0-beta" in content
    assert "known limitations" in content
    assert "gdb dap" in content
