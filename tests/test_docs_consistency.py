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
    assert "linux/macos" in content
    assert "unix domain socket" in content
    assert "windows is not" in content
    assert "official beta support matrix" in content


def test_readme_documents_supported_python_and_os_matrix():
    content = read_readme_lower()

    assert "linux" in content
    assert "macos" in content
    assert "3.10" in content
    assert "3.11" in content
    assert "3.12" in content
    assert "python 3.8 and 3.9 are not supported" in content
    assert "windows is not part of the official beta support matrix" in content


def test_readme_does_not_claim_windows_or_old_python_support():
    content = read_readme_lower()

    forbidden = [
        "windows default",
        "windows defaults",
        "windows uses tcp by default",
        "windows official support",
        "python `>=3.8`",
        "python >=3.8",
        "python 3.8 supported",
        "python 3.9 supported",
    ]

    for phrase in forbidden:
        assert phrase not in content


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


def test_readme_documents_ai_config_without_overclaiming():
    content = read_readme_lower()

    assert "ai assistant" in content
    assert "disabled by default" in content
    assert "magic_debug_ai_api_key" in content
    assert "configuration layer" in content
    assert "debug context" in content
    assert "include_source=false" in content
    assert "include_variables=false" in content
    assert "include_source=true" in content
    assert "include_variables=true" in content
    assert "max_context_chars" in content
    assert "automatic" in content
    assert "debug command" in content
    assert "automatically modify source code" in content
    assert "external" in content
    assert "api unless" in content
    assert "automatic code fixes are supported" not in content
    assert "automatically fixes code" not in content
    assert "automatically executes debug commands" not in content
    assert "rpc ai methods" in content
    assert "neovim ai commands are implemented" not in content


def test_readme_documents_ai_prompt_and_mock_without_overclaiming():
    content = read_readme_lower()

    assert "mock ai" in content
    assert "prompt builder" in content
    assert "no network access" in content
    assert "openai-compatible provider implementation" in content
    assert "magic_debug_ai_api_key" in content
    assert "disabled by default" in content
    assert "http ai endpoints" in content
    assert "rpc ai methods" in content
    assert "/api/ai/analyze" in content
    assert "/api/ai/config" in content
    assert "ai.getconfig" in content
    assert "ai.analyze" in content
    assert "api keys as `***`" in content
    assert "magicdebugaiconfig" in content
    assert "magicdebugaianalyze" in content
    assert "magicdebugaiexplainerror" in content
    assert "magicdebugaisuggestnextstep" in content
    assert "neovim plugin does not call openai-compatible providers directly" in content
    assert "http/rpc ai endpoints are implemented" not in content
    assert "automatically executes debug commands" not in content
    assert "automatically modifies source" not in content


def test_readme_documents_beta_release_materials():
    content = read_readme_lower()

    assert "beta" in content
    assert "release_notes.md" in content or "release notes" in content
    assert "docs/beta-checklist.md" in content or "beta validation checklist" in content


def test_beta_release_documents_exist():
    assert (ROOT / "docs" / "beta-checklist.md").exists()
    assert (ROOT / "docs" / "ai-beta-validation.md").exists()
    assert (ROOT / "docs" / "release-draft-v0.1.0-beta.md").exists()
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


def test_beta_checklist_uses_linux_macos_support_matrix():
    content = (ROOT / "docs" / "beta-checklist.md").read_text(encoding="utf-8").lower()

    assert "linux" in content
    assert "macos" in content
    assert "3.10" in content
    assert "3.11" in content
    assert "3.12" in content
    assert "windows tcp smoke" not in content
    assert "should not block" in content
    assert "beta release" in content
    assert "ai mock validation" in content
    assert "magicdebugaianalyze" in content
    assert "ai-beta-validation.md" in content


def test_release_notes_and_changelog_describe_support_matrix_update():
    release_notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8").lower()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").lower()

    assert "linux" in release_notes
    assert "macos" in release_notes
    assert "python 3.10-3.12" in release_notes
    assert "windows" in release_notes
    assert "not officially supported" in release_notes

    assert "official beta support target is linux/macos" in changelog
    assert "removed windows from the official ci/support matrix" in changelog
    assert "removed python 3.8 and 3.9" in changelog


def test_ai_beta_validation_document_exists_and_sets_privacy_boundaries():
    content = (ROOT / "docs" / "ai-beta-validation.md").read_text(
        encoding="utf-8"
    ).lower()

    assert "magicdebugaianalyze" in content
    assert "magicdebugaiconfig enable-mock" in content
    assert "api keys are not displayed" in content or "api key masking" in content
    assert "openai-compatible provider optional validation" in content
    assert "not a ci requirement" in content
    assert "ai is disabled by default" in content
    assert "source code is not included by default" in content
    assert "variable values are not included by default" in content
    assert "debug commands are not executed automatically" in content
    assert "source files are not modified" in content


def test_readme_links_ai_beta_validation_and_avoids_ai_overclaims():
    content = read_readme_lower()

    assert "docs/ai-beta-validation.md" in content
    assert "disabled by default" in content
    assert "mock provider" in content
    assert "openai-compatible provider" in content
    assert "source snippets and variable values remain disabled by default" in content
    assert "does not automatically execute debug commands" in content
    assert "does not automatically modify source code" in content
    assert "windows official support" not in content
    assert "ai automatically executes" not in content
    assert "ai automatically modifies" not in content


def test_release_draft_describes_beta_scope_and_ai_privacy():
    content = (ROOT / "docs" / "release-draft-v0.1.0-beta.md").read_text(
        encoding="utf-8"
    ).lower()

    assert "magic debug v0.1.0-beta" in content
    assert "linux/macos" in content
    assert "python 3.10-3.12" in content
    assert "gdb --interpreter=dap" in content
    assert "ai privacy defaults" in content
    assert "ai is disabled by default" in content
    assert "api keys are masked" in content
    assert "source snippets are disabled by default" in content
    assert "variable values are disabled by default" in content
    assert "does not automatically execute debugger commands" in content
    assert "does not automatically modify source code" in content
    assert "windows is not officially supported" in content
    assert "feedback wanted" in content
