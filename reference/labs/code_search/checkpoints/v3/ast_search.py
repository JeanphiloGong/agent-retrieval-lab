"""Python definition lookup using the standard-library AST."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .reader import WorkspaceError, _resolve_file


@dataclass(frozen=True)
class Definition:
    path: str
    name: str
    kind: Literal["function", "async_function", "class"]
    line: int
    end_line: int
    qualified_name: str


@dataclass(frozen=True)
class SyntaxErrorResult:
    path: str
    message: str
    line: int | None


def _walk_definitions(node: ast.AST, parents: tuple[str, ...] = ()) -> list[Definition]:
    found: list[Definition] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind: Literal["function", "async_function", "class"]
            if isinstance(child, ast.ClassDef):
                kind = "class"
            elif isinstance(child, ast.AsyncFunctionDef):
                kind = "async_function"
            else:
                kind = "function"
            qualified = ".".join((*parents, child.name))
            found.append(
                Definition(
                    path="",
                    name=child.name,
                    kind=kind,
                    line=child.lineno,
                    end_line=getattr(child, "end_lineno", child.lineno),
                    qualified_name=qualified,
                )
            )
            # A class/function body may contain nested definitions.  Include
            # them so callers can distinguish a nested definition from a call.
            found.extend(_walk_definitions(child, (*parents, child.name)))
        else:
            found.extend(_walk_definitions(child, parents))
    return found


def find_definitions(
    workspace: Path,
    relative_path: str,
    name: str | None = None,
) -> list[Definition] | SyntaxErrorResult:
    """Return Python definitions in a file, optionally filtered by name.

    Syntax failures are returned as data because a repository search should
    explain which file could not be indexed rather than pretending it had no
    definitions.
    """

    if name is not None and (not isinstance(name, str) or not name):
        raise WorkspaceError("name must be a nonempty string")
    root, target = _resolve_file(workspace, relative_path)
    try:
        source = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceError("file is not valid UTF-8") from exc
    except OSError as exc:
        raise WorkspaceError(type(exc).__name__) from exc
    try:
        tree = ast.parse(source, filename=str(target))
    except SyntaxError as exc:
        return SyntaxErrorResult(
            path=target.relative_to(root).as_posix(),
            message=exc.msg,
            line=exc.lineno,
        )
    definitions = []
    for definition in _walk_definitions(tree):
        if name is None or definition.name == name:
            definitions.append(
                Definition(
                    path=target.relative_to(root).as_posix(),
                    name=definition.name,
                    kind=definition.kind,
                    line=definition.line,
                    end_line=definition.end_line,
                    qualified_name=definition.qualified_name,
                )
            )
    return definitions
