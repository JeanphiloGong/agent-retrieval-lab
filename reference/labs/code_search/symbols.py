"""Python symbol lookup using Jedi's source-only static analysis."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import jedi

from .reader import WorkspaceError


@dataclass(frozen=True)
class Symbol:
    path: str
    module: str
    name: str
    qualified_name: str
    kind: Literal["function", "async_function", "class"]
    line: int
    end_line: int


@dataclass(frozen=True)
class Reference:
    path: str
    line: int
    column: int
    expression: str
    resolution: Literal["confirmed", "candidate", "unresolved"]
    target: Symbol | None = None
    candidates: tuple[Symbol, ...] = ()


def _module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or root.name


def _collect_symbols(
    node: ast.AST,
    path: str,
    module: str,
    scope: tuple[str, ...] = (),
) -> list[Symbol]:
    symbols: list[Symbol] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind: Literal["function", "async_function", "class"]
            kind = "class" if isinstance(child, ast.ClassDef) else "function"
            if isinstance(child, ast.AsyncFunctionDef):
                kind = "async_function"
            symbols.append(Symbol(path, module, child.name,
                                  ".".join((module, *scope, child.name)), kind,
                                  child.lineno, child.end_lineno or child.lineno))
            symbols.extend(_collect_symbols(child, path, module, (*scope, child.name)))
        else:
            symbols.extend(_collect_symbols(child, path, module, scope))
    return symbols


def _reference_position(node: ast.AST) -> tuple[int, int, str] | None:
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        return node.lineno, node.col_offset, node.id
    if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
        return (node.end_lineno or node.lineno,
                (node.end_col_offset or 0) - len(node.attr.encode("utf-8")),
                ast.unparse(node))
    return None


class SymbolIndex:
    """Index definitions with AST and delegate reference targets to Jedi."""

    def __init__(
        self,
        root: Path,
        symbols: tuple[Symbol, ...],
        references: tuple[Reference, ...],
        syntax_errors: tuple[tuple[str, str], ...],
    ) -> None:
        self.root = root
        self.symbols = symbols
        self._references = references
        self.syntax_errors = syntax_errors

    @classmethod
    def build(cls, workspace: Path) -> "SymbolIndex":
        root = workspace.resolve(strict=True)
        if not root.is_dir():
            raise WorkspaceError("workspace must be a directory")
        parsed: list[tuple[Path, str, ast.AST]] = []
        errors: list[tuple[str, str]] = []
        symbols: list[Symbol] = []
        for path in sorted(path for path in root.glob("**/*.py") if path.is_file()):
            if not path.resolve(strict=True).is_relative_to(root):
                continue
            relative = path.relative_to(root).as_posix()
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=relative)
            except (SyntaxError, UnicodeDecodeError) as exc:
                message = exc.msg if isinstance(exc, SyntaxError) else "file is not valid UTF-8"
                errors.append((relative, message))
                continue
            module = _module_name(root, path)
            symbols.extend(_collect_symbols(tree, relative, module))
            parsed.append((path, source, tree))

        by_location = {(str((root / symbol.path).resolve()), symbol.line, symbol.name): symbol
                       for symbol in symbols}
        references: list[Reference] = []
        project = jedi.Project(path=str(root), added_sys_path=[str(root)], smart_sys_path=False)
        for path, source, tree in parsed:
            script = jedi.Script(code=source, path=str(path), project=project)
            for node in ast.walk(tree):
                position = _reference_position(node)
                if position is None:
                    continue
                line, column, expression = position
                # AST columns count UTF-8 bytes; Jedi columns count characters.
                raw_line = source.splitlines()[line - 1]
                column = len(raw_line.encode("utf-8")[:column].decode("utf-8"))
                targets: list[Symbol] = []
                for name in script.goto(line, column, follow_imports=True):
                    target = by_location.get((str(name.module_path), name.line, name.name))
                    if target is not None and target not in targets:
                        targets.append(target)
                targets.sort(key=lambda target: (target.path, target.line))
                status: Literal["confirmed", "candidate", "unresolved"]
                status = "confirmed" if len(targets) == 1 else "candidate" if targets else "unresolved"
                references.append(Reference(
                    path.relative_to(root).as_posix(), line, column, expression, status,
                    targets[0] if len(targets) == 1 else None,
                    tuple(targets) if len(targets) > 1 else (),
                ))
        return cls(root, tuple(symbols), tuple(references), tuple(errors))

    def find_symbols(self, name: str, *, path: str | None = None) -> tuple[Symbol, ...]:
        """Find definitions by short or module-qualified name."""

        return tuple(symbol for symbol in self.symbols
                     if (symbol.name == name or symbol.qualified_name == name)
                     and (path is None or symbol.path == path))

    def references(self, name: str, *, path: str | None = None) -> tuple[Reference, ...]:
        """Return confirmed targets, ambiguous targets and unresolved mentions."""

        symbols = self.find_symbols(name)
        qualified = {symbol.qualified_name for symbol in symbols}
        short = {symbol.name for symbol in symbols} or {name.rsplit(".", 1)[-1]}
        return tuple(
            reference for reference in self._references
            if (path is None or reference.path == path) and (
                (reference.target and reference.target.qualified_name in qualified)
                or any(candidate.qualified_name in qualified for candidate in reference.candidates)
                or (reference.resolution == "unresolved" and (
                    reference.expression in short
                    or any(reference.expression.endswith(f".{item}") for item in short)
                ))
            )
        )
