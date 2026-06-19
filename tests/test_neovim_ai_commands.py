import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PLUGIN = ROOT / "vim-plugin" / "lua" / "magic-debug" / "init.lua"


def read_plugin():
    return PLUGIN.read_text(encoding="utf-8")


def test_neovim_ai_commands_are_registered():
    content = read_plugin()

    assert "MagicDebugAIConfig" in content
    assert "MagicDebugAIAnalyze" in content
    assert "MagicDebugAIExplainError" in content
    assert "MagicDebugAISuggestNextStep" in content


def test_neovim_ai_commands_use_backend_rpc_methods():
    content = read_plugin()

    assert '"ai.getConfig"' in content
    assert '"ai.updateConfig"' in content
    assert '"ai.analyze"' in content
    assert '"ai.explainError"' in content
    assert '"ai.suggestNextStep"' in content
    assert "rpc_call(" in content
    assert "pending_requests" in content
    assert "make_request" in content


def test_neovim_ai_result_and_error_handling_exist():
    content = read_plugin()

    assert "show_ai_result" in content
    assert "notify_ai_error" in content
    assert "AI_DISABLED" in content
    assert "AI_CONFIG_ERROR" in content
    assert "AI_PROVIDER_ERROR" in content
    assert "AI Suggested Next Step" in content
    assert "AI Error Explanation" in content
    assert "AI Analysis" in content


def test_neovim_ai_config_defaults_are_safe():
    content = read_plugin()

    assert "ai = {" in content
    assert "enabled = false" in content
    assert 'provider = "mock"' in content
    assert 'model = "mock-debugger"' in content
    assert "include_source = false" in content
    assert "include_variables = false" in content
    assert "include_stack = true" in content
    assert "include_breakpoints = true" in content


def test_neovim_ai_config_masks_api_key_display():
    content = read_plugin()

    assert 'safe.api_key = "***"' in content
    assert 'safe.api_key ~= ""' in content
    assert "show_ai_config" in content


def test_neovim_ai_config_has_mock_smoke_command():
    content = read_plugin()

    assert "enable-mock" in content
    assert "mock://local" in content
    assert "Magic Debug AI mock provider enabled" in content


def test_neovim_ai_does_not_call_external_provider_directly():
    content = read_plugin()

    assert "api.openai.com" not in content
    assert "Authorization" not in content
    assert "Bearer" not in content
    assert "chat/completions" not in content
    assert "curl" not in content


def test_neovim_ai_does_not_use_old_sync_chanread_pattern():
    content = read_plugin()

    assert "chanread" not in content
    assert "dispatch_rpc_message" in content
    assert 'msg.type == "response"' in content
    assert 'msg.type == "event"' in content


def test_existing_logs_command_remains_available():
    content = read_plugin()

    assert "MagicDebugLogs" in content
    assert "open_logs" in content
