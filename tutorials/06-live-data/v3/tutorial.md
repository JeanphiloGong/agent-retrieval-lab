# SQL 与业务 API v3：实时与历史结合

## 两个来源不等于一个可靠答案

用户问“A-1 库存是否符合备货要求”。SQL 返回 12，手册说“至少 10”，看上去可以直接比较。但库存可能是昨天的缓存，手册可能已经到期，区域政策可能要求 20。本版不让模型随意拼接它们：只有时间和适用范围都通过检查，程序才返回可回答的判断。

我们把政策压缩成来源拥有的一份结构化 JSON。`minimum_stock` 是政策数据本身的字段，而不是调用者随手传入的默认值；`quote` 给读者检查其意义。生产中这一结构应来自受控业务数据或人工确认的抽取，本版不宣称程序证明了任意自然语言与数字的一致性。

## 第一步：把政策的时间和范围纳入证据

`fixtures/live_data/cable-policy-v1.json` 保存来源、版本、类别、最小库存、引文，以及包含起点、不含终点的生效区间。`load_policy` 在文件入口校验完整字段、非负整数阈值、带时区时间和非空区间。它返回 `PolicyEvidence`，不写数据库。

```json
{
  "source_id": "stock-policy",
  "source_version": "v1",
  "category": "cable",
  "minimum_stock": 10,
  "quote": "Keep at least 10 cable units available.",
  "effective_from": "2026-10-01T00:00:00+00:00",
  "effective_until": "2026-11-01T00:00:00+00:00"
}
```

## 第二步：先证明可以组合，再比较数字

`combine_with_policy` 先检查库存存在、观察时间没有来自未来且年龄不超过 `max_age_seconds`；然后按库存类别和当前生效区间筛政策。没有有效政策时返回 `no_current_policy`；多个有效来源的阈值不同则返回 `policy_source_conflict`，保留各自来源供人判断。只有阈值一致时才比较当前数量。

```bash
uv run python - <<'PY'
from datetime import datetime, timezone
from labs.live_data.checkpoints.v3 import InventoryResult, combine_with_policy, load_policy

now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
inventory = InventoryResult("A-1", "cable", 12, now.isoformat())
policy = load_policy("fixtures/live_data/cable-policy-v1.json")
decision = combine_with_policy(inventory, [policy], now=now)
print(decision["answerable"], decision["minimum_stock"], decision["meets_policy"])
print([source["source_id"] for source in decision["sources"]])
PY
```

预期为 `True 10 True` 和 `['inventory', 'stock-policy']`。测试使用固定的带时区 `now`，所以不会随着日历变化而失效。应用调用方可以使用真实时钟，但必须接受证据到期后拒答。

## 第三步：冻结完整专题检查点

`labs/live_data/checkpoints/v3.py` 保存本版完整来源，`labs/live_data/query.py` 是实际集成入口；两者相同逻辑，快照不被主线代码导入。下面是本版完整 checkpoint，只组装此前的固定查询、参数契约、只读预算和证据组合。

```python
"""v3 checkpoint: live inventory queries and dated policy evidence."""

from __future__ import annotations

import json
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


@dataclass(frozen=True)
class PolicyEvidence:
    source_id: str
    source_version: str
    category: str
    minimum_stock: int
    quote: str
    effective_from: str
    effective_until: str


def _timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("evidence timestamps must include a timezone")
    return result.astimezone(timezone.utc)


def load_policy(path: str | Path) -> PolicyEvidence:
    """Read a structured, source-owned rule; do not infer thresholds from prose."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {
        "source_id", "source_version", "category", "minimum_stock", "quote",
        "effective_from", "effective_until",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("policy fields do not match the evidence contract")
    for field in required - {"minimum_stock"}:
        if not isinstance(payload[field], str) or not payload[field]:
            raise ValueError(f"policy {field} must be a nonempty string")
    if type(payload["minimum_stock"]) is not int or payload["minimum_stock"] < 0:
        raise ValueError("policy minimum_stock must be a nonnegative integer")
    _category(payload["category"])
    if _timestamp(payload["effective_until"]) <= _timestamp(payload["effective_from"]):
        raise ValueError("policy validity interval is empty")
    return PolicyEvidence(**payload)


def combine_with_policy(
    inventory: InventoryResult | None,
    policies: Sequence[PolicyEvidence],
    *,
    now: datetime | None = None,
    max_age_seconds: float = 60,
) -> dict[str, object]:
    """Answer only when current inventory and applicable policy agree on scope."""
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("now must include a timezone")
    if inventory is None:
        return {"answerable": False, "reason": "sku_not_found", "sources": []}
    sources: list[dict[str, object]] = [
        {"source_id": inventory.source_id, "observed_at": inventory.observed_at}
    ]
    age = (instant - _timestamp(inventory.observed_at)).total_seconds()
    if age < 0:
        return {"answerable": False, "reason": "future_inventory", "sources": sources}
    if age > max_age_seconds:
        return {"answerable": False, "reason": "stale_inventory", "sources": sources}
    applicable = [
        policy for policy in policies
        if policy.category == inventory.category
        and _timestamp(policy.effective_from) <= instant < _timestamp(policy.effective_until)
    ]
    if not applicable:
        return {"answerable": False, "reason": "no_current_policy", "sources": sources}
    for policy in applicable:
        sources.append({
            "source_id": policy.source_id,
            "source_version": policy.source_version,
            "quote": policy.quote,
            "effective_from": policy.effective_from,
            "effective_until": policy.effective_until,
        })
    minimums = {policy.minimum_stock for policy in applicable}
    if len(minimums) != 1:
        return {"answerable": False, "reason": "policy_source_conflict", "sources": sources}
    minimum = minimums.pop()
    return {
        "answerable": True,
        "sku": inventory.sku,
        "quantity": inventory.quantity,
        "minimum_stock": minimum,
        "meets_policy": inventory.quantity >= minimum,
        "observed_at": inventory.observed_at,
        "sources": sources,
    }
```

## 检查和冻结

```bash
uv run python -m pytest -q tests/test_live_data.py tests/test_live_data_checkpoints.py
```

验证实时变化、零库存、参数和 SQL 边界、预算，以及政策的当前/过期/类别不符/来源冲突、库存 60 秒边界、未来和无时区时间。历史快照测试分别导入 v0–v3，不把最新源码冒充所有版本。

当前仍是单机 SQLite 实验；没有网络 API 身份认证、跨数据库一致性、事务快照间的外部数据同步，或自然语言政策抽取。下一专题把这些已经有契约的工具交给有预算和停止条件的 Agent 检索循环。
