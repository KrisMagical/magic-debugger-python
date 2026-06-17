import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.rpc import (
    DEFAULT_RPC_HOST,
    DEFAULT_RPC_PORT,
    RPCServer,
    RPCTransportError,
    encode_rpc_message,
    resolve_rpc_endpoint,
    should_remove_stale_socket,
)


class FakeController:
    def on(self, event, callback):
        pass


def test_auto_uses_tcp_on_windows():
    endpoint = resolve_rpc_endpoint(transport="auto", platform_name="Windows")

    assert endpoint.transport == "tcp"
    assert endpoint.host == DEFAULT_RPC_HOST
    assert endpoint.port == DEFAULT_RPC_PORT


def test_auto_uses_unix_on_linux_with_xdg_runtime_dir(tmp_path):
    endpoint = resolve_rpc_endpoint(
        transport="auto",
        platform_name="Linux",
        env={"XDG_RUNTIME_DIR": str(tmp_path)},
    )

    assert endpoint.transport == "unix"
    assert endpoint.socket_path == str(tmp_path / "magic-debug.sock")


def test_auto_uses_unix_on_darwin(tmp_path):
    endpoint = resolve_rpc_endpoint(
        transport="auto",
        platform_name="Darwin",
        env={"XDG_RUNTIME_DIR": str(tmp_path)},
    )

    assert endpoint.transport == "unix"
    assert endpoint.socket_path.endswith("magic-debug.sock")


def test_explicit_tcp_endpoint():
    endpoint = resolve_rpc_endpoint(
        transport="tcp",
        host="127.0.0.2",
        port=9876,
        platform_name="Linux",
    )

    assert endpoint.transport == "tcp"
    assert endpoint.host == "127.0.0.2"
    assert endpoint.port == 9876


def test_explicit_unix_endpoint(tmp_path):
    socket_path = tmp_path / "custom.sock"

    endpoint = resolve_rpc_endpoint(
        transport="unix",
        socket_path=str(socket_path),
        platform_name="Linux",
    )

    assert endpoint.transport == "unix"
    assert endpoint.socket_path == str(socket_path)


def test_explicit_unix_on_windows_is_error(tmp_path):
    with pytest.raises(RPCTransportError, match="Unix socket is not supported"):
        resolve_rpc_endpoint(
            transport="unix",
            socket_path=str(tmp_path / "magic-debug.sock"),
            platform_name="Windows",
        )


def test_socket_residue_protection_does_not_delete_regular_file(tmp_path):
    path = tmp_path / "magic-debug.sock"
    path.write_text("not a socket", encoding="utf-8")

    assert should_remove_stale_socket(str(path)) is False

    server = RPCServer(FakeController())
    with pytest.raises(RPCTransportError, match="Refusing to remove non-socket"):
        server._create_unix_server(str(path))

    assert path.read_text(encoding="utf-8") == "not a socket"


def test_rpc_messages_are_line_delimited_json():
    encoded = encode_rpc_message({"type": "response", "id": 1, "success": True})

    assert encoded.endswith(b"\n")
    assert encoded.count(b"\n") == 1


def test_main_cli_declares_rpc_transport_arguments():
    content = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "--rpc-transport" in content
    assert "--rpc-socket" in content
    assert "--rpc-host" in content
    assert "--rpc-port" in content
