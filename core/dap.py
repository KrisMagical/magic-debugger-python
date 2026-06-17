"""Debug Adapter Protocol client and byte-stream framing helpers."""

import json
import logging
import queue
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, BinaryIO, Callable, Dict, Optional, Union

from .session import DebugSession

logger = logging.getLogger(__name__)

DEFAULT_ADAPTER_ID = "gdb"
HEADER_DELIMITER = b"\r\n\r\n"


class DAPError(Exception):
    """DAP protocol error."""


def encode_dap_message(payload: Dict[str, Any]) -> bytes:
    """Encode a DAP payload with UTF-8 byte length in Content-Length."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    body_bytes = body.encode("utf-8")
    header = f"Content-Length: {len(body_bytes)}\r\n\r\n".encode("ascii")
    return header + body_bytes


def _parse_content_length(header_bytes: bytes) -> int:
    try:
        header_text = header_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise DAPError(f"Invalid DAP header encoding: {exc}") from exc

    headers: Dict[str, str] = {}
    for line in header_text.split("\r\n"):
        if not line:
            continue
        if ":" not in line:
            raise DAPError(f"Malformed DAP header line: {line}")
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    value = headers.get("content-length")
    if value is None:
        raise DAPError("Missing Content-Length header")

    try:
        return int(value)
    except ValueError as exc:
        raise DAPError(f"Invalid Content-Length: {value}") from exc


def _read_until_header_end(stream: BinaryIO) -> bytes:
    header = bytearray()
    while HEADER_DELIMITER not in header:
        chunk = stream.read(1)
        if not chunk:
            raise DAPError("EOF before DAP header complete")
        header.extend(chunk)
    return bytes(header)


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if data is None or len(data) != size:
        raise DAPError("EOF before DAP body complete")
    return data


def read_dap_message(stream: BinaryIO, timeout: Optional[float] = None) -> Dict[str, Any]:
    """Read one DAP message from a binary file-like stream."""
    del timeout
    framed_header = _read_until_header_end(stream)
    header_bytes, remainder = framed_header.split(HEADER_DELIMITER, 1)
    content_length = _parse_content_length(header_bytes)

    if len(remainder) > content_length:
        raise DAPError("DAP body exceeds Content-Length")

    body = remainder + _read_exact(stream, content_length - len(remainder))
    try:
        body_text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DAPError(f"Invalid UTF-8 DAP body: {exc}") from exc

    try:
        return json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise DAPError(f"Invalid JSON: {exc}") from exc


class MessageType(Enum):
    """DAP message type."""

    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"


@dataclass
class DAPMessage:
    """Base DAP message."""

    type: str
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.raw


@dataclass
class DAPRequest(DAPMessage):
    """DAP request message."""

    seq: int = 0
    command: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DAPResponse(DAPMessage):
    """DAP response message."""

    request_seq: int = 0
    success: bool = True
    command: str = ""
    message: Optional[str] = None
    body: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DAPEvent(DAPMessage):
    """DAP event message."""

    event: str = ""
    body: Dict[str, Any] = field(default_factory=dict)


class DAPClient:
    """Debug Adapter Protocol client."""

    DEFAULT_INIT_PARAMS = {
        "clientID": "magic-debug",
        "clientName": "Magic Debug",
        "adapterID": DEFAULT_ADAPTER_ID,
        "locale": "en-us",
        "linesStartAt1": True,
        "columnsStartAt1": True,
        "pathFormat": "path",
        "supportsVariableType": True,
        "supportsVariablePaging": True,
        "supportsRunInTerminalRequest": False,
        "supportsMemoryReferences": True,
        "supportsProgressReporting": True,
        "supportsInvalidatedEvent": True,
        "supportsMemoryEvent": True,
    }

    def __init__(self, session: DebugSession):
        self.session = session
        self.seq = 1
        self._lock = threading.Lock()
        self._pending_requests: Dict[int, queue.Queue] = {}
        self._response_timeout = 30.0
        self._event_handlers: Dict[str, Callable] = {}
        self._message_callback: Optional[Callable] = None
        self._message_queue: queue.Queue = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self._initialized = False
        self._capabilities: Dict[str, Any] = {}

    def start_reader(self):
        """Start the DAP message reader thread."""
        if self._reader_thread and self._reader_thread.is_alive():
            return

        self._running = True
        self._reader_thread = threading.Thread(
            target=self._event_loop,
            daemon=True,
            name="DAP-EventLoop",
        )
        self._reader_thread.start()
        logger.info("DAP reader thread started")

    def stop_reader(self):
        """Stop the DAP message reader thread."""
        self._running = False

    def _event_loop(self):
        """Continuously read and dispatch DAP messages."""
        logger.info("DAP event loop started")

        while self._running and self.session.is_alive():
            try:
                msg = self.read_message(timeout=1.0)
                if msg:
                    self._dispatch_message(msg)
            except Exception as exc:
                if self._running:
                    logger.error(f"Error in event loop: {exc}")

        logger.info("DAP event loop stopped")

    def read_message(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Read one complete DAP message from the session byte queue."""
        framed_header = self.session.read_until(HEADER_DELIMITER, timeout=timeout)
        if framed_header is None:
            return None

        header_bytes, remainder = framed_header.split(HEADER_DELIMITER, 1)
        content_length = _parse_content_length(header_bytes)
        if len(remainder) > content_length:
            raise DAPError("DAP body exceeds Content-Length")

        remaining = content_length - len(remainder)
        if remaining:
            chunk = self.session.read_exact(remaining, timeout=timeout)
            if chunk is None:
                raise DAPError("EOF before DAP body complete")
            body = remainder + chunk
        else:
            body = remainder

        try:
            return json.loads(body.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise DAPError(f"Invalid UTF-8 DAP body: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DAPError(f"Invalid JSON: {exc}") from exc

    def _dispatch_message(self, msg: Dict[str, Any]):
        """Dispatch a DAP message to response waiters or event handlers."""
        msg_type = msg.get("type")
        self._message_queue.put(msg)

        if self._message_callback:
            try:
                self._message_callback(msg)
            except Exception as exc:
                logger.error(f"Error in message callback: {exc}")

        if msg_type == "response":
            self._handle_response(msg)
        elif msg_type == "event":
            self._handle_event(msg)
        elif msg_type == "request":
            self._handle_reverse_request(msg)
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    def _handle_response(self, msg: Dict[str, Any]):
        request_seq = msg.get("request_seq")
        if request_seq in self._pending_requests:
            self._pending_requests[request_seq].put(msg)

    def _handle_event(self, msg: Dict[str, Any]):
        event = msg.get("event", "")
        if event in self._event_handlers:
            try:
                self._event_handlers[event](msg)
            except Exception as exc:
                logger.error(f"Error in event handler for '{event}': {exc}")
        logger.debug(f"DAP Event: {event}")

    def _handle_reverse_request(self, msg: Dict[str, Any]):
        command = msg.get("command", "")
        seq = msg.get("seq", 0)
        logger.debug(f"Reverse request: {command}")

        if command == "runInTerminal":
            self.send_response(
                seq,
                command,
                False,
                message="runInTerminal is not supported by Magic Debug yet",
            )

    def send(
        self,
        command: str,
        arguments: Optional[Dict[str, Any]] = None,
        wait_response: bool = True,
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Send a DAP request."""
        with self._lock:
            seq = self.seq
            self.seq += 1

        request = {
            "seq": seq,
            "type": "request",
            "command": command,
        }
        if arguments:
            request["arguments"] = arguments

        if wait_response:
            self._pending_requests[seq] = queue.Queue()

        self._send_raw(request)
        logger.debug(f"Sent request: {command} (seq={seq})")

        if wait_response:
            try:
                actual_timeout = timeout or self._response_timeout
                return self._pending_requests[seq].get(timeout=actual_timeout)
            except queue.Empty:
                logger.error(f"Timeout waiting for response to '{command}'")
                return None
            finally:
                del self._pending_requests[seq]

        return None

    def send_response(
        self,
        request_seq: int,
        command: str,
        success: bool,
        message: Optional[str] = None,
        body: Optional[Dict] = None,
    ):
        """Send a DAP response for a reverse request."""
        response = {
            "seq": self.seq,
            "type": "response",
            "request_seq": request_seq,
            "command": command,
            "success": success,
        }
        if message:
            response["message"] = message
        if body:
            response["body"] = body

        self.seq += 1
        self._send_raw(response)

    def _send_raw(self, msg: Dict[str, Any]):
        """Send a raw DAP message."""
        self.session.write(encode_dap_message(msg))

    def on_event(self, event: str, handler: Callable):
        """Register an event handler."""
        self._event_handlers[event] = handler

    def on_message(self, callback: Callable):
        """Register a callback for all messages."""
        self._message_callback = callback

    def get_message(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Get a queued message."""
        try:
            return self._message_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def initialize(self, params: Optional[Dict] = None) -> Optional[Dict]:
        actual_params = self.DEFAULT_INIT_PARAMS.copy()
        if params:
            actual_params.update(params)

        response = self.send("initialize", actual_params)
        if response and response.get("success"):
            self._initialized = True
            self._capabilities = response.get("body", {})
            logger.info("DAP initialized successfully")

        return response

    def launch(
        self,
        program: str,
        args: Optional[list] = None,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        stop_on_entry: bool = False,
        **kwargs,
    ) -> Optional[Dict]:
        arguments = {
            "program": program,
            "stopOnEntry": stop_on_entry,
        }
        if args:
            arguments["args"] = args
        if cwd:
            arguments["cwd"] = cwd
        if env:
            arguments["env"] = env
        arguments.update(kwargs)
        return self.send("launch", arguments)

    def attach(self, pid: int, **kwargs) -> Optional[Dict]:
        arguments = {"pid": pid}
        arguments.update(kwargs)
        return self.send("attach", arguments)

    def set_breakpoints(
        self,
        source: Dict,
        breakpoints: list,
        source_modified: bool = False,
    ) -> Optional[Dict]:
        return self.send(
            "setBreakpoints",
            {
                "source": source,
                "breakpoints": breakpoints,
                "sourceModified": source_modified,
            },
        )

    def set_function_breakpoints(self, breakpoints: list) -> Optional[Dict]:
        return self.send("setFunctionBreakpoints", {"breakpoints": breakpoints})

    def configuration_done(self) -> Optional[Dict]:
        return self.send("configurationDone")

    def continue_(self, thread_id: Optional[int] = None) -> Optional[Dict]:
        arguments = {}
        if thread_id is not None:
            arguments["threadId"] = thread_id
        return self.send("continue", arguments)

    def step_over(self, thread_id: int, single_thread: bool = False) -> Optional[Dict]:
        return self.send("next", {"threadId": thread_id, "singleThread": single_thread})

    def step_into(
        self,
        thread_id: int,
        single_thread: bool = False,
        target_id: Optional[int] = None,
    ) -> Optional[Dict]:
        args = {
            "threadId": thread_id,
            "singleThread": single_thread,
        }
        if target_id is not None:
            args["targetId"] = target_id
        return self.send("stepIn", args)

    def step_out(self, thread_id: int, single_thread: bool = False) -> Optional[Dict]:
        return self.send("stepOut", {"threadId": thread_id, "singleThread": single_thread})

    def pause(self, thread_id: Optional[int] = None) -> Optional[Dict]:
        arguments = {}
        if thread_id is not None:
            arguments["threadId"] = thread_id
        return self.send("pause", arguments)

    def disconnect(
        self,
        restart: bool = False,
        terminate_debuggee: Optional[bool] = None,
    ) -> Optional[Dict]:
        args = {"restart": restart}
        if terminate_debuggee is not None:
            args["terminateDebuggee"] = terminate_debuggee
        return self.send("disconnect", args)

    def terminate(self, restart: bool = False) -> Optional[Dict]:
        return self.send("terminate", {"restart": restart})

    def threads(self) -> Optional[Dict]:
        return self.send("threads")

    def stack_trace(
        self,
        thread_id: int,
        start_frame: int = 0,
        levels: int = 20,
    ) -> Optional[Dict]:
        return self.send(
            "stackTrace",
            {"threadId": thread_id, "startFrame": start_frame, "levels": levels},
        )

    def scopes(self, frame_id: int) -> Optional[Dict]:
        return self.send("scopes", {"frameId": frame_id})

    def variables(
        self,
        variables_reference: int,
        filter_type: Optional[str] = None,
        start: Optional[int] = None,
        count: Optional[int] = None,
    ) -> Optional[Dict]:
        args = {"variablesReference": variables_reference}
        if filter_type:
            args["filter"] = filter_type
        if start is not None:
            args["start"] = start
        if count is not None:
            args["count"] = count
        return self.send("variables", args)

    def evaluate(
        self,
        expression: str,
        frame_id: Optional[int] = None,
        context: str = "repl",
    ) -> Optional[Dict]:
        args = {"expression": expression, "context": context}
        if frame_id is not None:
            args["frameId"] = frame_id
        return self.send("evaluate", args)

    def set_variable(
        self,
        variables_reference: int,
        name: str,
        value: str,
        frame_id: Optional[int] = None,
    ) -> Optional[Dict]:
        args = {
            "variablesReference": variables_reference,
            "name": name,
            "value": value,
        }
        if frame_id is not None:
            args["frameId"] = frame_id
        return self.send("setVariable", args)

    def source(self, source: Dict, source_reference: int) -> Optional[Dict]:
        return self.send(
            "source",
            {"source": source, "sourceReference": source_reference},
        )

    def disassemble(
        self,
        memory_reference: str,
        instruction_count: int,
        offset: int = 0,
        instruction_offset: int = 0,
    ) -> Optional[Dict]:
        return self.send(
            "disassemble",
            {
                "memoryReference": memory_reference,
                "instructionCount": instruction_count,
                "offset": offset,
                "instructionOffset": instruction_offset,
            },
        )

    @property
    def capabilities(self) -> Dict[str, Any]:
        return self._capabilities

    @property
    def is_initialized(self) -> bool:
        return self._initialized


def parse_dap_message(msg: Dict[str, Any]) -> Union[DAPRequest, DAPResponse, DAPEvent]:
    """Convert a raw DAP message dict to a typed dataclass wrapper."""
    msg_type = msg.get("type", "")

    if msg_type == "request":
        return DAPRequest(
            type=msg_type,
            raw=msg,
            seq=msg.get("seq", 0),
            command=msg.get("command", ""),
            arguments=msg.get("arguments", {}),
        )
    if msg_type == "response":
        return DAPResponse(
            type=msg_type,
            raw=msg,
            request_seq=msg.get("request_seq", 0),
            success=msg.get("success", False),
            command=msg.get("command", ""),
            message=msg.get("message"),
            body=msg.get("body", {}),
        )
    if msg_type == "event":
        return DAPEvent(
            type=msg_type,
            raw=msg,
            event=msg.get("event", ""),
            body=msg.get("body", {}),
        )
    raise DAPError(f"Unknown message type: {msg_type}")
