"""Process/session management for the GDB DAP adapter."""

import logging
import os
import queue
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class ProcessInfo:
    """Process information."""

    pid: int
    command: List[str]
    is_running: bool = True
    exit_code: Optional[int] = None


class DebugSession:
    """Manage a debug adapter process and its byte-oriented stdio streams."""

    def __init__(self, command: List[str], env: Optional[dict] = None):
        self.command = command
        self.proc: Optional[subprocess.Popen] = None
        self.info: Optional[ProcessInfo] = None
        self.output_queue: queue.Queue[bytes] = queue.Queue()
        self.error_queue: queue.Queue[str] = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._error_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_exit: Optional[Callable[[int], None]] = None

        self.env = os.environ.copy()
        if env:
            self.env.update(env)

    def start(self) -> bool:
        """Start the debug adapter process in binary stdio mode."""
        try:
            logger.info(f"Starting debug adapter: {' '.join(self.command)}")

            self.proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                env=self.env,
            )

            self.info = ProcessInfo(
                pid=self.proc.pid,
                command=self.command,
                is_running=True,
            )

            self._running = True

            self._reader_thread = threading.Thread(
                target=self._read_output,
                daemon=True,
                name="DAP-Reader",
            )
            self._reader_thread.start()

            self._error_thread = threading.Thread(
                target=self._read_error,
                daemon=True,
                name="DAP-Error",
            )
            self._error_thread.start()

            logger.info(f"Debug adapter started with PID: {self.proc.pid}")
            return True

        except FileNotFoundError:
            logger.error(f"Debug adapter not found: {self.command[0]}")
            return False
        except Exception as e:
            logger.error(f"Failed to start debug adapter: {e}")
            return False

    def _read_output(self):
        """Read process stdout as bytes for DAP framing."""
        try:
            while self._running and self.proc and self.proc.stdout:
                chunk = self.proc.stdout.read(1)
                if not chunk:
                    break
                self.output_queue.put(chunk)
        except Exception as e:
            logger.debug(f"Output reader stopped: {e}")
        finally:
            self._check_exit()

    def _read_error(self):
        """Read process stderr as text logs, separate from DAP stdout."""
        try:
            while self._running and self.proc and self.proc.stderr:
                line = self.proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                self.error_queue.put(text)
                logger.debug(f"Debugger stderr: {text.strip()}")
        except Exception as e:
            logger.debug(f"Error reader stopped: {e}")

    def _check_exit(self):
        """Check whether the process has exited."""
        if self.proc and self.proc.poll() is not None:
            self._running = False
            if self.info:
                self.info.is_running = False
                self.info.exit_code = self.proc.returncode
            logger.info(f"Debug adapter exited with code: {self.proc.returncode}")
            if self._on_exit:
                self._on_exit(self.proc.returncode)

    def write(self, data: Union[str, bytes]) -> bool:
        """Write bytes to process stdin."""
        if not self.is_alive() or not self.proc or not self.proc.stdin:
            logger.warning("Cannot write: process is not running")
            return False

        try:
            if isinstance(data, str):
                data = data.encode("utf-8")
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
            logger.debug(f"Sent {len(data)} bytes")
            return True
        except Exception as e:
            logger.error(f"Write failed: {e}")
            return False

    def read(self, n: int, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read up to n bytes from stdout."""
        result = bytearray()
        remaining = n

        while remaining > 0:
            try:
                chunk = self.output_queue.get(timeout=timeout)
            except queue.Empty:
                break
            result.extend(chunk)
            remaining -= len(chunk)

        return bytes(result) if result else None

    def read_exact(self, n: int, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read exactly n bytes from stdout."""
        data = self.read(n, timeout=timeout)
        if data is None or len(data) != n:
            return None
        return data

    def readline(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read one LF-terminated stdout line as bytes."""
        result = bytearray()
        while True:
            try:
                chunk = self.output_queue.get(timeout=timeout)
            except queue.Empty:
                return bytes(result) if result else None
            result.extend(chunk)
            if chunk == b"\n":
                return bytes(result)

    def read_until(self, delimiter: bytes, timeout: Optional[float] = None) -> Optional[bytes]:
        """Read stdout bytes until delimiter is included."""
        result = bytearray()
        while delimiter not in result:
            try:
                chunk = self.output_queue.get(timeout=timeout)
            except queue.Empty:
                return None
            result.extend(chunk)
        return bytes(result)

    def read_available(self, timeout: float = 0.1) -> bytes:
        """Read all currently available stdout bytes."""
        result = bytearray()
        while True:
            try:
                chunk = self.output_queue.get(timeout=timeout)
            except queue.Empty:
                break
            result.extend(chunk)
        return bytes(result)

    def read_error(self, timeout: float = 0.1) -> str:
        """Read all currently available stderr text."""
        result = []
        while True:
            try:
                line = self.error_queue.get(timeout=timeout)
            except queue.Empty:
                break
            result.append(line)
        return "".join(result)

    def is_alive(self) -> bool:
        """Return whether the process is alive."""
        if self.proc is None:
            return False
        return self.proc.poll() is None

    def terminate(self):
        """Terminate the process."""
        if self.proc and self.is_alive():
            logger.info("Terminating debug adapter...")
            self._running = False
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

            if self.info:
                self.info.is_running = False

    def on_exit(self, callback: Callable[[int], None]):
        """Set process exit callback."""
        self._on_exit = callback

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.terminate()
        return False

    def __repr__(self):
        status = "running" if self.is_alive() else "stopped"
        return f"<DebugSession pid={self.info.pid if self.info else 'N/A'} status={status}>"


class SessionManager:
    """Manage multiple debug sessions."""

    def __init__(self):
        self.sessions: dict[str, DebugSession] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        name: str,
        command: List[str],
        env: Optional[dict] = None,
    ) -> DebugSession:
        with self._lock:
            if name in self.sessions:
                raise ValueError(f"Session '{name}' already exists")

            session = DebugSession(command, env)
            self.sessions[name] = session
            return session

    def get_session(self, name: str) -> Optional[DebugSession]:
        """Get a session by name."""
        return self.sessions.get(name)

    def remove_session(self, name: str):
        """Remove and terminate a named session."""
        with self._lock:
            session = self.sessions.pop(name, None)
            if session:
                session.terminate()

    def list_sessions(self) -> List[str]:
        """List session names."""
        return list(self.sessions.keys())

    def terminate_all(self):
        """Terminate all sessions."""
        with self._lock:
            for session in self.sessions.values():
                session.terminate()
            self.sessions.clear()
