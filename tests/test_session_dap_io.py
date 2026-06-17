"""DebugSession byte I/O tests."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dap import DAPClient, encode_dap_message
from core.session import DebugSession


class FakeStdin:
    def __init__(self):
        self.data = b""
        self.flushed = False

    def write(self, data):
        assert isinstance(data, bytes)
        self.data += data

    def flush(self):
        self.flushed = True


class FakeProcess:
    def __init__(self):
        self.stdin = FakeStdin()

    def poll(self):
        return None


def make_session_with_fake_process():
    session = DebugSession(["fake-gdb"])
    session.proc = FakeProcess()
    return session


def test_session_write_encodes_str_to_bytes():
    session = make_session_with_fake_process()

    assert session.write("abc")
    assert session.proc.stdin.data == b"abc"
    assert session.proc.stdin.flushed is True


def test_dap_client_send_raw_writes_bytes():
    session = make_session_with_fake_process()
    client = DAPClient(session)
    payload = {"seq": 1, "type": "request", "command": "initialize"}

    client._send_raw(payload)

    assert session.proc.stdin.data == encode_dap_message(payload)


def test_session_read_until_and_read_exact_return_bytes():
    session = DebugSession(["fake-gdb"])
    for byte in b"Content-Length: 2\r\n\r\n{}":
        session.output_queue.put(bytes([byte]))

    assert session.read_until(b"\r\n\r\n") == b"Content-Length: 2\r\n\r\n"
    assert session.read_exact(2) == b"{}"
