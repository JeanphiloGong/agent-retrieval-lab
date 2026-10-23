"""v1 checkpoint: validated fixed inventory tools with bounded pagination."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


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
