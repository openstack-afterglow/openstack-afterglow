"""Locked daily-size JSON file logging handler."""

import logging
import os
import re
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]


class DailySizeHandler(logging.Handler):
    """Production-safe locked daily-size file logging handler.

    File Naming:
    - Base file: backend-YYYY-MM-DD.log
    - Suffix file: backend-YYYY-MM-DD-01.log, backend-YYYY-MM-DD-02.log, ...

    Rotation behavior:
    - Rotates before writing a record if current_size > 0 and current_size + len(msg) > max_bytes.
    - An oversized first record/chunk writes alone to the unsuffixed or active empty file (size == 0)
      rather than creating an empty base file.
    - Date rollover starts the unsuffixed file backend-YYYY-MM-DD.log for the new local date.
    - Existing files are never renamed, overwritten, or re-numbered.
    - Process restart resumes the highest current-date suffix file if size < max_bytes;
      otherwise allocates a fresh higher suffix (max_suffix + 1).
    - Retention is unbounded: old date/size files are never deleted.
    """

    def __init__(
        self,
        log_directory: str | Path = "logs",
        max_bytes: int = 52428800,
        encoding: str = "utf-8",
        date_provider: Callable[[], date | datetime] | None = None,
    ) -> None:
        super().__init__()
        self.log_directory = Path(log_directory)
        self.max_bytes = max_bytes
        self.encoding = encoding
        self._date_provider = date_provider or (lambda: datetime.now().date())
        self._current_date_str: str | None = None
        self._current_file_path: Path | None = None
        self._current_stream: BinaryIO | None = None
        self._lock_fd: int | None = None

    def _get_date_str(self) -> str:
        current_d = self._date_provider()
        if isinstance(current_d, datetime):
            current_d = current_d.date()
        return current_d.isoformat()

    def _get_existing_suffixes(self, date_str: str) -> dict[int, Path]:
        pattern = re.compile(rf"^backend-{re.escape(date_str)}(?:-(\d+))?\.log$")
        results: dict[int, Path] = {}
        if not self.log_directory.exists():
            return results

        try:
            for entry in self.log_directory.iterdir():
                if not entry.is_file():
                    continue
                m = pattern.match(entry.name)
                if m:
                    suffix_str = m.group(1)
                    idx = int(suffix_str) if suffix_str is not None else 0
                    results[idx] = entry
        except OSError:
            pass

        return results

    def _format_file_path(self, date_str: str, suffix_index: int) -> Path:
        if suffix_index == 0:
            return self.log_directory / f"backend-{date_str}.log"
        return self.log_directory / f"backend-{date_str}-{suffix_index:02d}.log"

    def _resolve_active_file(self, date_str: str) -> Path:
        suffixes = self._get_existing_suffixes(date_str)
        if not suffixes:
            return self._format_file_path(date_str, 0)

        max_idx = max(suffixes.keys())
        highest_file = suffixes[max_idx]
        try:
            size = highest_file.stat().st_size
        except OSError:
            size = 0

        if size < self.max_bytes:
            return highest_file

        next_idx = max_idx + 1
        return self._format_file_path(date_str, next_idx)

    def _close_stream(self) -> None:
        if self._current_stream is not None:
            try:
                self._current_stream.close()
            except OSError:
                pass
            self._current_stream = None

    def _acquire_file_lock(self) -> int | None:
        if fcntl is None:
            return None
        try:
            lock_file_path = self.log_directory / ".backend_log.lock"
            if self._lock_fd is None or self._lock_fd < 0:
                self._lock_fd = os.open(lock_file_path, os.O_CREAT | os.O_RDWR, 0o666)
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
            return self._lock_fd
        except (OSError, AttributeError):
            return None

    def _release_file_lock(self, lock_fd: int | None) -> None:
        if lock_fd is not None and fcntl is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except (OSError, AttributeError):
                pass

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record) + "\n"
            msg_bytes = msg.encode(self.encoding, errors="replace")

            self.acquire()
            try:
                self._write_msg(msg_bytes)
            finally:
                self.release()
        except Exception:
            self.handleError(record)

    def _write_msg(self, msg_bytes: bytes) -> None:
        try:
            self.log_directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            return

        lock_fd = self._acquire_file_lock()
        try:
            date_str = self._get_date_str()
            msg_len = len(msg_bytes)

            active_file = self._resolve_active_file(date_str)
            if self._current_file_path != active_file or self._current_stream is None:
                self._close_stream()
                self._current_date_str = date_str
                self._current_file_path = active_file

            current_size = 0
            if self._current_file_path.exists():
                try:
                    current_size = self._current_file_path.stat().st_size
                except OSError:
                    current_size = 0

            if current_size > 0 and (current_size + msg_len) > self.max_bytes:
                self._close_stream()
                suffixes = self._get_existing_suffixes(date_str)
                max_idx = max(suffixes.keys()) if suffixes else 0
                next_idx = max_idx + 1
                self._current_file_path = self._format_file_path(date_str, next_idx)

            if self._current_stream is None:
                try:
                    # Retain the stream across records; _close_stream owns its lifecycle.
                    self._current_stream = open(self._current_file_path, "ab")  # noqa: SIM115
                except OSError:
                    return

            try:
                self._current_stream.write(msg_bytes)
                self._current_stream.flush()
            except OSError:
                self._close_stream()
        except OSError:
            pass
        finally:
            self._release_file_lock(lock_fd)

    def close(self) -> None:
        self.acquire()
        try:
            self._close_stream()
            if self._lock_fd is not None:
                if fcntl is not None:
                    try:
                        os.close(self._lock_fd)
                    except OSError:
                        pass
                self._lock_fd = None
            super().close()
        finally:
            self.release()
