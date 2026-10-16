"""v2 checkpoint: bounded read-only SQLite queries."""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class InventoryResult:
    sku: str
    category: str
    quantity: int
    observed_at: str
    source_id: str = "inventory"


def current_time() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_database(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Create the local fixture database; this is the writer, not an Agent tool."""
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE IF NOT EXISTS inventory ("
        "sku TEXT PRIMARY KEY, category TEXT NOT NULL, "
        "quantity INTEGER NOT NULL CHECK(quantity >= 0))"
    )
    connection.commit()
    return connection


def seed(connection: sqlite3.Connection, rows: Iterable[tuple[str, str, int]]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO inventory(sku, category, quantity) VALUES (?, ?, ?)",
        rows,
    )
    connection.commit()


def _category(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError("category must be a nonempty string of at most 64 characters")


def get_product(connection: sqlite3.Connection, sku: str) -> InventoryResult | None:
    if not isinstance(sku, str) or not re.fullmatch(r"[A-Z0-9_-]{1,32}", sku):
        raise ValueError("sku must be a bounded uppercase identifier")
    row = connection.execute(
        "SELECT sku, category, quantity FROM inventory WHERE sku = ?", (sku,)
    ).fetchone()
    if row is None:
        return None
    return InventoryResult(row["sku"], row["category"], row["quantity"], current_time())


def list_products(
    connection: sqlite3.Connection,
    category: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> tuple[InventoryResult, ...]:
    _category(category)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    if type(offset) is not int or not 0 <= offset <= 10_000:
        raise ValueError("offset must be an integer between 0 and 10000")
    rows = connection.execute(
        "SELECT sku, category, quantity FROM inventory WHERE category = ? "
        "ORDER BY sku LIMIT ? OFFSET ?",
        (category, limit, offset),
    ).fetchall()
    observed_at = current_time()
    return tuple(
        InventoryResult(row["sku"], row["category"], row["quantity"], observed_at)
        for row in rows
    )


class QueryRejected(ValueError):
    """SQL violates the read-only execution contract."""


class QueryBudgetExceeded(RuntimeError):
    """The execution deadline or SQLite operation budget was exhausted."""


class QueryRowLimitExceeded(RuntimeError):
    """The result contains more rows than the caller's explicit budget."""


@dataclass(frozen=True)
class QueryResult:
    rows: tuple[dict[str, Any], ...]
    observed_at: str
    source_id: str = "inventory"


def query_readonly(
    path: str | Path,
    statement: str,
    parameters: Sequence[Any] = (),
    *,
    max_rows: int = 100,
    timeout_seconds: float = 0.05,
    max_operations: int = 100_000,
) -> QueryResult:
    """Execute one bounded SELECT using a new, read-only SQLite connection."""
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("statement must be a nonempty string")
    if type(max_rows) is not int or not 1 <= max_rows <= 1000:
        raise ValueError("max_rows must be between 1 and 1000")
    if timeout_seconds <= 0 or max_operations < 1:
        raise ValueError("query budgets must be positive")

    uri = Path(path).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=timeout_seconds)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    allowed_functions = {"sum", "count", "min", "max", "avg", "coalesce"}

    def authorize(action: int, first: str | None, second: str | None, *_: Any) -> int:
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            return sqlite3.SQLITE_OK if first == "inventory" else sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and second in allowed_functions:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    deadline = time.monotonic() + timeout_seconds
    operations = 0
    interrupted = False

    def check_budget() -> int:
        nonlocal operations, interrupted
        operations += 100
        interrupted = operations > max_operations or time.monotonic() >= deadline
        return int(interrupted)

    connection.set_authorizer(authorize)
    connection.set_progress_handler(check_budget, 100)
    try:
        if time.monotonic() >= deadline:
            raise QueryBudgetExceeded("query deadline exceeded before execution")
        # execute, unlike executescript, accepts exactly one SQL statement.
        cursor = connection.execute(statement, tuple(parameters))
        if cursor.description is None:
            raise QueryRejected("query must produce a result set")
        rows = cursor.fetchmany(max_rows + 1)
        if len(rows) > max_rows:
            raise QueryRowLimitExceeded(f"query exceeds {max_rows} result rows")
        return QueryResult(tuple(dict(row) for row in rows), current_time())
    except sqlite3.DatabaseError as exc:
        if interrupted:
            raise QueryBudgetExceeded("query deadline or operation budget exceeded") from exc
        raise QueryRejected(str(exc)) from exc
    finally:
        connection.close()
