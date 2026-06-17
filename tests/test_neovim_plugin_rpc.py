import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PLUGIN = ROOT / "vim-plugin" / "lua" / "magic-debug" / "init.lua"


def read_plugin():
    return PLUGIN.read_text(encoding="utf-8")


def test_plugin_uses_pending_requests_and_request_ids():
    content = read_plugin()

    assert "next_request_id" in content
    assert "pending_requests" in content
    assert "make_request" in content
    assert "request.id" in content


def test_plugin_dispatches_responses_and_events_separately():
    content = read_plugin()

    assert "dispatch_rpc_message" in content
    assert 'msg.type == "response"' in content
    assert 'msg.type == "event"' in content
    assert "handle_rpc_response" in content
    assert "handle_rpc_event" in content


def test_plugin_buffers_line_delimited_rpc_messages():
    content = read_plugin()

    assert "rpc_buffer" in content
    assert "on_rpc_data" in content
    assert 'find("\\n"' in content
    assert "dispatch_rpc_message(msg)" in content


def test_plugin_does_not_shell_append_background_operator():
    content = read_plugin()

    assert 'server_command .. " &"' not in content
    assert "vim.fn.system(state.config.server_command" not in content


def test_plugin_starts_server_with_managed_job_api():
    content = read_plugin()

    assert "server_command = { " in content
    assert "vim.system" in content or "jobstart" in content
    assert "state.server_job" in content
    assert "stop_server" in content


def test_plugin_has_logs_and_reconnect_commands():
    content = read_plugin()

    assert "MagicDebugLogs" in content
    assert "MagicDebugReconnect" in content
    assert "open_logs" in content
    assert "reconnect" in content


def test_plugin_supports_launch_config_files():
    content = read_plugin()

    assert "magic-debug.json" in content
    assert ".magic-debug.json" in content
    assert "find_launch_config" in content
    assert "load_launch_config" in content
    assert "stopAtEntry" in content
    assert "gdbPath" in content


def test_magic_debug_start_accepts_optional_program():
    content = read_plugin()

    assert 'nargs = "?"' in content
    assert "M.start(args.args)" in content


def test_plugin_declares_rpc_transport_config():
    content = read_plugin()

    assert "rpc_transport" in content
    assert "rpc_host" in content
    assert "rpc_port" in content
    assert "rpc_socket_path" in content


def test_plugin_has_platform_transport_selection():
    content = read_plugin()

    assert "is_windows" in content
    assert "win32" in content
    assert '"tcp"' in content
    assert '"unix"' in content
    assert "resolve_rpc_transport" in content


def test_plugin_passes_rpc_transport_to_server_command():
    content = read_plugin()

    assert "--rpc-transport" in content
    assert "--rpc-host" in content
    assert "--rpc-port" in content
    assert "--rpc-socket" in content
    assert "append_rpc_transport_args" in content


def test_plugin_has_tcp_and_unix_connection_branches():
    content = read_plugin()

    assert 'sockconnect("tcp"' in content
    assert 'sockconnect("unix"' in content
    assert "Unix RPC connection failed; trying TCP fallback" in content
