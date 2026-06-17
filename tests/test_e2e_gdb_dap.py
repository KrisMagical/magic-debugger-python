import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dap import encode_dap_message, read_dap_message


def require_tool(name):
    path = shutil.which(name)
    if not path:
        pytest.skip(f"{name} not available")
    return path


def require_gdb_dap(gdb):
    try:
        result = subprocess.run(
            [gdb, "--interpreter=dap", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"gdb --interpreter=dap not available: {exc}")

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        pytest.skip(f"gdb does not support --interpreter=dap: {stderr}")


class DAPProcessClient:
    def __init__(self, process):
        self.process = process
        self.seq = 1
        self.messages = queue.Queue()
        self.stderr_lines = queue.Queue()
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader_thread.start()
        self._stderr_thread.start()

    def _read_stdout(self):
        while self.process.poll() is None:
            try:
                msg = read_dap_message(self.process.stdout)
                if msg.get("type") == "request":
                    self._handle_reverse_request(msg)
                else:
                    self.messages.put(msg)
            except Exception as exc:
                self.messages.put(exc)
                break

    def _read_stderr(self):
        while self.process.poll() is None and self.process.stderr:
            line = self.process.stderr.readline()
            if not line:
                break
            self.stderr_lines.put(line.decode("utf-8", errors="replace"))

    def _handle_reverse_request(self, msg):
        command = msg.get("command", "")
        response = {
            "seq": self.seq,
            "type": "response",
            "request_seq": msg.get("seq"),
            "command": command,
            "success": False,
            "message": f"{command} is not supported in the e2e test client",
        }
        self.seq += 1
        self.process.stdin.write(encode_dap_message(response))
        self.process.stdin.flush()

    def send_request(self, command, arguments=None):
        seq = self.seq
        self.seq += 1
        payload = {"seq": seq, "type": "request", "command": command}
        if arguments is not None:
            payload["arguments"] = arguments
        self.process.stdin.write(encode_dap_message(payload))
        self.process.stdin.flush()
        return seq

    def read_message(self, timeout=5.0):
        item = self.messages.get(timeout=timeout)
        if isinstance(item, Exception):
            raise item
        return item

    def wait_for_response(self, command, request_seq=None, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self.read_message(timeout=max(0.01, deadline - time.monotonic()))
            if msg.get("type") == "response" and msg.get("command") == command:
                if request_seq is None or msg.get("request_seq") == request_seq:
                    return msg
        raise TimeoutError(f"Timed out waiting for {command} response")

    def wait_for_event(self, event, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self.read_message(timeout=max(0.01, deadline - time.monotonic()))
            if msg.get("type") == "event" and msg.get("event") == event:
                return msg
        raise TimeoutError(f"Timed out waiting for {event} event")

    def drain_stderr(self):
        lines = []
        while True:
            try:
                lines.append(self.stderr_lines.get_nowait())
            except queue.Empty:
                break
        return "".join(lines)


def terminate_process(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_gdb_dap_breakpoint_stacktrace_e2e(tmp_path):
    gcc = require_tool("gcc")
    gdb = require_tool("gdb")
    require_gdb_dap(gdb)

    sample = ROOT / "tests" / "fixtures" / "test_sample.c"
    binary = tmp_path / ("test_sample.exe" if sys.platform.startswith("win") else "test_sample")

    compile_result = subprocess.run(
        [gcc, "-g", "-O0", str(sample), "-o", str(binary)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    process = subprocess.Popen(
        [gdb, "--interpreter=dap"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    client = DAPProcessClient(process)

    try:
        seq = client.send_request("initialize", {
            "adapterID": "gdb",
            "clientID": "magic-debug-test",
            "clientName": "Magic Debug E2E Test",
            "linesStartAt1": True,
            "columnsStartAt1": True,
            "pathFormat": "path",
        })
        response = client.wait_for_response("initialize", request_seq=seq, timeout=5)
        if not response.get("success"):
            pytest.skip(f"GDB DAP initialize failed: {response}")

        try:
            client.wait_for_event("initialized", timeout=2)
        except TimeoutError:
            pass

        seq = client.send_request("setBreakpoints", {
            "source": {"path": str(sample)},
            "breakpoints": [{"line": 3}],
            "sourceModified": False,
        })
        response = client.wait_for_response("setBreakpoints", request_seq=seq, timeout=5)
        if not response.get("success"):
            pytest.xfail(f"GDB DAP setBreakpoints failed: {response}")
        breakpoints = response.get("body", {}).get("breakpoints", [])
        assert breakpoints, response

        seq = client.send_request("launch", {
            "program": str(binary),
            "cwd": str(tmp_path),
            "stopAtBeginningOfMainSubprogram": True,
        })
        response = client.wait_for_response("launch", request_seq=seq, timeout=5)
        if not response.get("success"):
            pytest.xfail(f"GDB DAP launch failed: {response}")

        seq = client.send_request("configurationDone")
        response = client.wait_for_response("configurationDone", request_seq=seq, timeout=5)
        if not response.get("success"):
            pytest.xfail(f"GDB DAP configurationDone failed: {response}")

        thread_id = None
        final_stopped = None
        try:
            stopped = client.wait_for_event("stopped", timeout=5)
            thread_id = stopped.get("body", {}).get("threadId")
            if stopped.get("body", {}).get("reason") == "breakpoint":
                final_stopped = stopped
        except TimeoutError:
            stopped = None

        if final_stopped is None:
            seq = client.send_request("continue", {"threadId": thread_id} if thread_id else {})
            try:
                client.wait_for_response("continue", request_seq=seq, timeout=5)
            except TimeoutError:
                pass

        stopped = final_stopped or client.wait_for_event("stopped", timeout=10)
        thread_id = stopped.get("body", {}).get("threadId") or thread_id
        if thread_id is None:
            seq = client.send_request("threads")
            response = client.wait_for_response("threads", request_seq=seq, timeout=5)
            threads = response.get("body", {}).get("threads", [])
            assert threads, response
            thread_id = threads[0]["id"]

        seq = client.send_request("stackTrace", {
            "threadId": thread_id,
            "startFrame": 0,
            "levels": 20,
        })
        response = client.wait_for_response("stackTrace", request_seq=seq, timeout=5)
        assert response.get("success"), response
        frames = response.get("body", {}).get("stackFrames", [])
        assert frames, response
        assert any(
            frame.get("name") == "main"
            or frame.get("source", {}).get("path") == str(sample)
            for frame in frames
        ), frames

        client.send_request("disconnect", {
            "terminateDebuggee": True,
            "killDebuggee": True,
        })
    finally:
        terminate_process(process)
