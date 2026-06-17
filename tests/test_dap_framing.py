"""DAP byte-stream framing tests."""

from io import BytesIO
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dap import DAPError, encode_dap_message, read_dap_message


def split_frame(encoded: bytes):
    header, body = encoded.split(b"\r\n\r\n", 1)
    length_line = header.decode("ascii").split(":", 1)[1].strip()
    return int(length_line), body


def test_ascii_json_content_length_is_byte_length():
    payload = {"seq": 1, "type": "request", "command": "initialize"}

    encoded = encode_dap_message(payload)
    declared_length, body = split_frame(encoded)

    assert encoded.startswith(b"Content-Length: ")
    assert declared_length == len(body)
    assert read_dap_message(BytesIO(encoded)) == payload


def test_non_ascii_json_content_length_is_utf8_byte_length():
    payload = {
        "seq": 1,
        "type": "event",
        "event": "output",
        "body": {"output": "你好"},
    }

    encoded = encode_dap_message(payload)
    declared_length, body = split_frame(encoded)

    assert declared_length == len(body)
    assert declared_length != len(body.decode("utf-8"))
    assert read_dap_message(BytesIO(encoded)) == payload


def test_multiple_messages_can_be_read_from_one_stream():
    payload1 = {"seq": 1, "type": "request", "command": "initialize"}
    payload2 = {"seq": 2, "type": "request", "command": "threads"}
    stream = BytesIO(encode_dap_message(payload1) + encode_dap_message(payload2))

    assert read_dap_message(stream) == payload1
    assert read_dap_message(stream) == payload2


def test_missing_content_length_raises():
    with pytest.raises(DAPError, match="Missing Content-Length"):
        read_dap_message(BytesIO(b"Header: x\r\n\r\n{}"))


def test_invalid_content_length_raises():
    with pytest.raises(DAPError, match="Invalid Content-Length"):
        read_dap_message(BytesIO(b"Content-Length: abc\r\n\r\n{}"))


def test_incomplete_body_raises():
    with pytest.raises(DAPError, match="EOF before DAP body complete"):
        read_dap_message(BytesIO(b"Content-Length: 10\r\n\r\n{}"))


def test_invalid_json_raises():
    with pytest.raises(DAPError, match="Invalid JSON"):
        read_dap_message(BytesIO(b"Content-Length: 5\r\n\r\nabcde"))
