"""Shared external-process supervisor for shell-free child processes.

Encapsulates the read loop and the fail-closed teardown shared by the DSH
runtime adapter, the Worker bridge, and the Codex adapter.  Protocol-specific
parsing and error codes stay in each caller through callbacks, so this module
never invents a provider- or bootstrap-specific failure.
"""

from __future__ import annotations

import hashlib
import os
import selectors
import signal
import subprocess
import time
from typing import Any, Callable, Optional

DEFAULT_CHUNK_BYTES = 64 * 1024
DEFAULT_LINE_CAP_BYTES = 64 * 1024
DEFAULT_STDERR_CAP_BYTES = 64 * 1024
DEFAULT_TERMINATE_TIMEOUT = 2.0
DEFAULT_KILL_TIMEOUT = 2.0


def terminate_process(
    process: subprocess.Popen[bytes],
    *,
    term_timeout: float = DEFAULT_TERMINATE_TIMEOUT,
    kill_timeout: float = DEFAULT_KILL_TIMEOUT,
) -> tuple[Optional[int], bool]:
    """Fail-closed teardown: SIGTERM to the process group, then SIGKILL.

    Mirrors the ``killpg(SIGTERM)`` -> wait -> ``killpg(SIGKILL)`` -> wait
    sequence used by every adapter.  Returns ``(returncode, forced_kill)``:
    ``forced_kill`` is true when SIGTERM did not settle the group and SIGKILL
    was required.  ``returncode`` may be ``None`` if it could not be
    determined.  Callers remain responsible for closing streams and
    unregistering any selector they created.
    """

    forced_kill = False
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            process.terminate()
        try:
            return process.wait(timeout=term_timeout), False
        except subprocess.TimeoutExpired:
            forced_kill = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()
            try:
                return process.wait(timeout=kill_timeout), True
            except subprocess.TimeoutExpired:
                return process.returncode, True
    return process.returncode, forced_kill


class LineStreamSupervisor:
    """Drive a child process's stdout/stderr through a fixed-size select loop.

    Reads ``chunk_bytes`` chunks, splits stdout into newline-delimited lines,
    and invokes ``on_line`` for each complete line.  Accumulates a stderr
    SHA-256 digest and enforces optional byte caps.  Every failure mode is
    reported through a caller-supplied callback that raises the caller's own
    protocol error (with its own code), keeping this module provider-agnostic.
    """

    def __init__(
        self,
        *,
        on_line: Callable[[bytes], None],
        line_cap_bytes: Optional[int] = DEFAULT_LINE_CAP_BYTES,
        stderr_cap_bytes: Optional[int] = DEFAULT_STDERR_CAP_BYTES,
        chunk_bytes: int = DEFAULT_CHUNK_BYTES,
        on_timeout: Optional[Callable[[], Exception]] = None,
        on_line_too_large: Optional[Callable[[], Exception]] = None,
        on_stderr_too_large: Optional[Callable[[], Exception]] = None,
        on_incomplete_line: Optional[Callable[[], Exception]] = None,
        on_empty_line: Optional[Callable[[], Exception]] = None,
        on_iteration: Optional[Callable[[], None]] = None,
    ) -> None:
        self.on_line = on_line
        self.line_cap_bytes = line_cap_bytes
        self.stderr_cap_bytes = stderr_cap_bytes
        self.chunk_bytes = chunk_bytes
        self._on_timeout = on_timeout
        self._on_line_too_large = on_line_too_large
        self._on_stderr_too_large = on_stderr_too_large
        self._on_incomplete_line = on_incomplete_line
        self._on_empty_line = on_empty_line
        self._on_iteration = on_iteration
        self.stderr_digest = hashlib.sha256()
        self.stderr_bytes = 0

    def read(self, process: subprocess.Popen[bytes], *, deadline: float, select_timeout: float = 0.25) -> None:
        """Consume stdout/stderr until both streams close.

        Raises the caller-supplied exception (via the ``on_*`` callbacks) on a
        size cap, an incomplete final stdout line, or an empty line.  On
        timeout it raises ``TimeoutError`` unless ``on_timeout`` is supplied.
        The caller's ``on_iteration`` (if any) runs at the top of every loop
        iteration, e.g. to honour a stop request.
        """

        if process.stdout is None or process.stderr is None:
            raise RuntimeError("supervised process must expose stdout and stderr pipes")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        stdout_buffer = bytearray()
        open_streams = 2
        try:
            while open_streams:
                if self._on_iteration is not None:
                    self._on_iteration()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._raise(self._on_timeout, TimeoutError("supervised process timed out"))
                ready_streams = selector.select(min(select_timeout, remaining))
                if not ready_streams:
                    continue
                for selected, _ in ready_streams:
                    stream_name = selected.data
                    data = os.read(selected.fileobj.fileno(), self.chunk_bytes)
                    if not data:
                        self._unregister(selector, selected.fileobj)
                        open_streams -= 1
                        if stream_name == "stdout" and stdout_buffer:
                            self._raise(self._on_incomplete_line, RuntimeError("incomplete final stdout line"))
                        continue
                    if stream_name == "stderr":
                        self.stderr_bytes += len(data)
                        if self.stderr_cap_bytes is not None and self.stderr_bytes > self.stderr_cap_bytes:
                            self._raise(self._on_stderr_too_large, RuntimeError("stderr exceeds size limit"))
                        self.stderr_digest.update(data)
                        continue
                    stdout_buffer.extend(data)
                    if self.line_cap_bytes is not None and len(stdout_buffer) > self.line_cap_bytes:
                        self._raise(self._on_line_too_large, RuntimeError("stdout line exceeds size limit"))
                    while b"\n" in stdout_buffer:
                        line, _, remainder = stdout_buffer.partition(b"\n")
                        stdout_buffer = bytearray(remainder)
                        if not line:
                            self._raise(self._on_empty_line, RuntimeError("empty stdout line"))
                        self.on_line(line)
        finally:
            self._close_selector(selector)

    @staticmethod
    def _unregister(selector: selectors.DefaultSelector, fileobj: Any) -> None:
        try:
            selector.unregister(fileobj)
        except Exception:
            pass

    @staticmethod
    def _close_selector(selector: selectors.DefaultSelector) -> None:
        for key in list(selector.get_map().values()):
            try:
                selector.unregister(key.fileobj)
            except Exception:
                pass

    @staticmethod
    def _raise(factory: Optional[Callable[[], Exception]], default: Exception) -> None:
        if factory is not None:
            raise factory()
        raise default
