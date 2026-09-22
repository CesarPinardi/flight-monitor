"""Small atomic JSON store with one process lock for monitor runs."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
from typing import Any, Iterator, Mapping


class ConcurrentRunError(RuntimeError):
    """Another monitor process owns the data lock."""


class JsonStore:
    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self.history_path = self.directory / "history.json"
        self.state_path = self.directory / "state.json"
        self.public_path = self.directory / "public" / "data.json"
        self.lock_path = self.directory / ".monitor.lock"

    @contextmanager
    def lock(self, *, timeout: float = 0.0, poll: float = 0.05) -> Iterator[None]:
        self.directory.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        descriptor: int | None = None
        while descriptor is None:
            try:
                descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(descriptor, f"pid={os.getpid()}\n".encode())
            except FileExistsError:
                if time.monotonic() - started >= timeout:
                    raise ConcurrentRunError(f"monitor lock exists: {self.lock_path}")
                time.sleep(poll)
        try:
            yield
        finally:
            os.close(descriptor)
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass

    def read(self, path: Path, default: Any) -> Any:
        try:
            with path.open(encoding="utf-8") as stream:
                return json.load(stream)
        except FileNotFoundError:
            return default
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON store: {path}") from exc

    def write(self, path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
