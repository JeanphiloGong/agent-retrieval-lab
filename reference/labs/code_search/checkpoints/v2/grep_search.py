"""Literal, bounded text search for source trees."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .reader import WorkspaceError


class SearchTimeout(WorkspaceError):
    """The search exceeded its caller-provided time budget."""


@dataclass(frozen=True)
class GrepMatch:
    path: str
    line: int
    text: str


@dataclass(frozen=True)
class GrepResult:
    status: Literal["matched", "no_match", "timeout"]
    matches: tuple[GrepMatch, ...]


def _files(root: Path, glob: str) -> list[Path]:
    # A sorted list makes output stable across filesystems and test runs.
    return sorted(path for path in root.glob(glob) if path.is_file())


def grep_literal(
    workspace: Path,
    needle: str,
    *,
    glob: str = "**/*",
    max_results: int = 100,
    timeout_seconds: float = 2.0,
) -> GrepResult:
    """Find ``needle`` as a literal substring and return source lines.

    This intentionally does not use regular expressions: ``[`` and ``*`` in
    an error code or function name retain their literal meaning.  A timeout is
    represented separately from an empty result so callers cannot mistake an
    interrupted search for a proven miss.
    """

    if not isinstance(needle, str) or not needle:
        raise WorkspaceError("needle must be a nonempty string")
    if max_results < 1:
        raise WorkspaceError("max_results must be positive")
    if timeout_seconds <= 0:
        raise WorkspaceError("timeout_seconds must be positive")
    try:
        root = workspace.resolve(strict=True)
    except OSError as exc:
        raise WorkspaceError(type(exc).__name__) from exc
    if not root.is_dir():
        raise WorkspaceError("workspace must be a directory")

    deadline = time.monotonic() + timeout_seconds
    matches: list[GrepMatch] = []
    for path in _files(root, glob):
        if time.monotonic() >= deadline:
            return GrepResult("timeout", tuple(matches))
        try:
            if not path.resolve(strict=True).is_relative_to(root):
                continue
        except OSError as exc:
            raise WorkspaceError(type(exc).__name__) from exc
        try:
            with path.open("r", encoding="utf-8") as source:
                for line_number, line in enumerate(source, start=1):
                    if time.monotonic() >= deadline:
                        return GrepResult("timeout", tuple(matches))
                    if needle in line:
                        matches.append(
                            GrepMatch(
                                path=path.relative_to(root).as_posix(),
                                line=line_number,
                                text=line.rstrip("\r\n"),
                            )
                        )
                        if len(matches) >= max_results:
                            return GrepResult("matched", tuple(matches))
        except UnicodeDecodeError:
            # Binary or non-UTF-8 files are not source evidence.
            continue
        except OSError as exc:
            raise WorkspaceError(type(exc).__name__) from exc
    return GrepResult("matched" if matches else "no_match", tuple(matches))
