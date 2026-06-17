import queue
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dap import encode_dap_message, read_dap_message


class QueuePipe:
    def __init__(self):
        self._queue = queue.Queue()
        self._closed = False

    def write(self, data):
        for byte in data:
            self._queue.put(bytes([byte]))

    def read(self, size=-1):
        if self._closed and self._queue.empty():
            return b""
        if size is None or size < 0:
            size = 1
        chunks = bytearray()
        while len(chunks) < size:
            try:
                chunk = self._queue.get(timeout=0.5)
            except queue.Empty:
                if chunks:
                    break
                if self._closed:
                    return b""
                continue
            chunks.extend(chunk)
        return bytes(chunks)

    def flush(self):
        pass

    def close(self):
        self._closed = True


class FakeDAPProcess:
    def __init__(self):
        self.stdin = QueuePipe()
        self.stdout = QueuePipe()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._running = False
        self._seq = 100

    def start(self):
        self._running = True
        self._thread.start()

    def stop(self):
        self._running = False
        self.stdin.close()
        self.stdout.close()
        self._thread.join(timeout=2)

    def _send(self, message):
        self.stdout.write(encode_dap_message(message))

    def _response(self, request, success=True, body=None):
        self._seq += 1
        response = {
            "seq": self._seq,
            "type": "response",
            "request_seq": request["seq"],
            "command": request["command"],
            "success": success,
        }
        if body is not None:
            response["body"] = body
        self._send(response)

    def _event(self, event, body=None):
        self._seq += 1
        self._send({
            "seq": self._seq,
            "type": "event",
            "event": event,
            "body": body or {},
        })

    def _run(self):
        while self._running:
            try:
                request = read_dap_message(self.stdin)
            except Exception:
                break

            command = request.get("command")
            if command == "initialize":
                self._event("initialized")
                self._response(request, body={"supportsConfigurationDoneRequest": True})
            elif command == "setBreakpoints":
                self._response(request, body={
                    "breakpoints": [{"id": 1, "verified": True, "line": 2}]
                })
            elif command == "launch":
                self._response(request)
            elif command == "configurationDone":
                self._response(request)
                self._event("stopped", {"reason": "breakpoint", "threadId": 7})
            elif command == "continue":
                self._response(request, body={"allThreadsContinued": True})
                self._event("stopped", {"reason": "breakpoint", "threadId": 7})
            elif command == "stackTrace":
                self._response(request, body={
                    "stackFrames": [{
                        "id": 1,
                        "name": "main",
                        "line": 2,
                        "column": 1,
                        "source": {"path": "test_sample.c"},
                    }],
                    "totalFrames": 1,
                })
            elif command == "disconnect":
                self._response(request)
                self._running = False
            else:
                self._response(request, success=False)


class DAPTestClient:
    def __init__(self, process):
        self.process = process
        self.seq = 1
        self.messages = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        while True:
            try:
                self.messages.put(read_dap_message(self.process.stdout))
            except Exception as exc:
                self.messages.put(exc)
                break

    def send_request(self, command, arguments=None):
        seq = self.seq
        self.seq += 1
        payload = {"seq": seq, "type": "request", "command": command}
        if arguments is not None:
            payload["arguments"] = arguments
        self.process.stdin.write(encode_dap_message(payload))
        self.process.stdin.flush()
        return seq

    def read_message(self, timeout=2.0):
        item = self.messages.get(timeout=timeout)
        if isinstance(item, Exception):
            raise item
        return item

    def wait_for_response(self, command, request_seq=None, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self.read_message(timeout=max(0.01, deadline - time.monotonic()))
            if msg.get("type") == "response" and msg.get("command") == command:
                if request_seq is None or msg.get("request_seq") == request_seq:
                    return msg
        raise TimeoutError(f"Timed out waiting for {command} response")

    def wait_for_event(self, event, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self.read_message(timeout=max(0.01, deadline - time.monotonic()))
            if msg.get("type") == "event" and msg.get("event") == event:
                return msg
        raise TimeoutError(f"Timed out waiting for {event} event")


def test_fake_dap_process_response_event_flow():
    process = FakeDAPProcess()
    process.start()
    client = DAPTestClient(process)

    try:
        seq = client.send_request("initialize", {"adapterID": "gdb"})
        initialized = client.wait_for_event("initialized")
        response = client.wait_for_response("initialize", request_seq=seq)
        assert initialized["type"] == "event"
        assert response["success"] is True

        seq = client.send_request("setBreakpoints", {
            "source": {"path": "test_sample.c"},
            "breakpoints": [{"line": 2}],
        })
        response = client.wait_for_response("setBreakpoints", request_seq=seq)
        assert response["body"]["breakpoints"][0]["verified"] is True

        client.wait_for_response("launch", client.send_request("launch", {"program": "fake"}))
        client.wait_for_response("configurationDone", client.send_request("configurationDone"))
        stopped = client.wait_for_event("stopped")
        assert stopped["body"]["threadId"] == 7

        client.wait_for_response("continue", client.send_request("continue"))
        stopped = client.wait_for_event("stopped")
        assert stopped["body"]["reason"] == "breakpoint"

        response = client.wait_for_response(
            "stackTrace",
            client.send_request("stackTrace", {"threadId": 7}),
        )
        assert response["body"]["stackFrames"][0]["name"] == "main"
    finally:
        try:
            client.send_request("disconnect")
        except Exception:
            pass
        process.stop()
