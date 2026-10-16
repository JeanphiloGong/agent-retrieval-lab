"""Workspace-bounded file reads.

The reader is deliberately small.  It is a trust boundary for paths supplied
by a caller, so it resolves the workspace and the requested file before
opening it and rejects symlinks that leave the workspace.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(ValueError):
    """An input cannot be safely read from the workspace."""


@dataclass(frozen=True)
class FileRead:
    """A bounded, line-addressed file result."""

    path: str
    start_line: int
    end_line: int
    text: str

    @property
    def bytes_read(self) -> int:
        return len(self.text.encode("utf-8"))


def _resolve_file(workspace: Path, relative_path: str) -> tuple[Path, Path]:
    if not isinstance(relative_path, str) or not relative_path:
        raise WorkspaceError("path must be a nonempty string")
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise WorkspaceError("path is outside workspace")
    try:
        root = workspace.resolve(strict=True)
        target = (root / relative).resolve(strict=True)
    except OSError as exc:
        raise WorkspaceError(type(exc).__name__) from exc
    if not target.is_relative_to(root):
        raise WorkspaceError("path is outside workspace")
    if not target.is_file():
        raise WorkspaceError("expected a file inside workspace")
    return root, target


def read_range(
    workspace: Path,
    relative_path: str,
    *,
    start_line: int = 1,
    end_line: int | None = None,
    max_bytes: int = 8192,
) -> FileRead:
    """Read an inclusive line range from one UTF-8 file.

    ``workspace`` is the only allowed root.  The selected text, including
    line endings, must fit in ``max_bytes``.  A bounded line iterator avoids
    loading a whole large file into memory.
    """

    if start_line < 1:
        raise WorkspaceError("start_line must be positive")
    if end_line is not None and end_line < start_line:
        raise WorkspaceError("end_line must be >= start_line")
    if max_bytes < 1:
        raise WorkspaceError("max_bytes must be positive")
    _, target = _resolve_file(workspace, relative_path)

    selected: list[bytes] = []
    selected_bytes = 0
    try:
        with target.open("rb") as source:
            line_number = 1
            while end_line is None or line_number <= end_line:
                chunk = source.readline(max_bytes + 1)
                if not chunk:
                    break
                if line_number >= start_line:
                    selected.append(chunk)
                    selected_bytes += len(chunk)
                    if selected_bytes > max_bytes:
                        raise WorkspaceError("selected range exceeds max_bytes")
                # A line may be larger than the budget.  Bounded chunks let
                # skipped lines stay bounded without changing line numbers.
                if chunk.endswith(b"\n"):
                    line_number += 1
            data = b"".join(selected)
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceError("file is not valid UTF-8") from exc
    except OSError as exc:
        raise WorkspaceError(type(exc).__name__) from exc

    if start_line > 1 and not selected:
        raise WorkspaceError("start_line is past end of file")
    line_count = data.count(b"\n") + int(bool(data) and not data.endswith(b"\n"))
    actual_end = start_line + line_count - 1
    return FileRead(
        path=target.relative_to(Path(workspace).resolve()).as_posix(),
        start_line=start_line,
        end_line=actual_end,
        text=text,
    )


def read_file(
    workspace: Path,
    relative_path: str,
    *,
    max_bytes: int = 8192,
) -> FileRead:
    """Read a complete bounded file through :func:`read_range`."""

    return read_range(workspace, relative_path, max_bytes=max_bytes)
