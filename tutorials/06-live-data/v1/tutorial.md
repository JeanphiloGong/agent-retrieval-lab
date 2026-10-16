# SQL 与业务 API v1：参数契约

## 从当前查询到外部输入

v0 的调用者手工传入 `A-1`；真实 Agent 的参数来自模型或用户。现在尝试空 SKU、`A' OR 1=1 --`，以及 `limit=1000000`。SQL 占位符已经把值当数据处理，但它没有表达业务允许的 SKU 形状，也没有限制返回量。

本版只增加一个边界：SKU 是 1–32 个大写字母、数字、下划线或短横线；类别是最多 64 字符的非空字符串；分页 `limit` 是 1–100 的整数，`offset` 是 0–10000 的整数。布尔值不作为整数页大小接受。服务内部不反复清理这些值。

## 第一步：参数化不能替代业务约束

`get_product` 在调用 SQL 前校验 SKU。`list_products` 先校验类别和分页，再用参数化 SQL 查询，并固定 `ORDER BY sku`，否则相同分页不能得到稳定顺序。工具返回一个 tuple，零库存仍是有效结果，未命中仍是空结果。

```bash
uv run python - <<'PY'
from labs.live_data.checkpoints.v1 import get_product, list_products, open_database, seed

db = open_database()
seed(db, [("A-1", "cable", 12), ("A-2", "cable", 0)])
print([row.sku for row in list_products(db, "cable", limit=1, offset=1)])
print(list_products(db, "cable' OR 1=1 --"))
try:
    list_products(db, "cable", limit=1000000)
except ValueError as error:
    print(type(error).__name__, str(error))
db.close()
PY
```

预期输出为 `['A-2']`、`()`、以及 `limit` 的 `ValueError`。注入字符串没有扩大查询，因为它始终是一个类别值。

## 第二步：冻结完整参数工具

保留 v0 快照，创建 `labs/live_data/checkpoints/v1.py`。这是本版完整 checkpoint；它加入输入校验和有界列表，尚未开放任意 SQL。

```python
"""v1 checkpoint: validated fixed inventory tools with bounded pagination."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
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
```

## 检查和冻结

```bash
uv run python -m pytest -q tests/test_live_data.py -k v1
uv run python -m pytest -q tests/test_live_data_checkpoints.py -k v1
```

测试包括合法分页、注入输入、不存在与零库存、空/小写/超长 SKU、布尔页大小和页边界。现在 Agent 可以安全填充固定业务参数，但“每个类别的库存总量”还没有对应的固定工具。下一版提供真正受限的 SQL 执行环境，并把只读与资源预算放在执行边界实现。
