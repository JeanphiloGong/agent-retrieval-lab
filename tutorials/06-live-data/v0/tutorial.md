# SQL 与业务 API v0：固定查询

## 为什么需要实时工具

用户问“现在 A-1 还有多少库存”。手册昨天写着 12，但仓库刚完成一次出库。即使检索器完美找回手册，答案仍然会错，因为这个事实属于实时业务数据。这个版本把问题压缩为本地 SQLite 的一张 `inventory` 表和一个固定 SKU 查询，不引入模型、向量库或 HTTP 服务。

先从调用方能看到的输入开始：SKU `A-1`。输出必须区分不存在和零库存，并记录查询完成后的 UTC `observed_at`。这个时间说明何时观察到数据，不保证下一秒仍然相同。

## 第一步：让过期文档的缺陷可见

如果只把手册的“12”写进答案，下面第二次查询依然只能得到旧值。先运行一个实际会变化的数据源：

```bash
uv sync --locked
uv run python - <<'PY'
from labs.live_data.checkpoints.v0 import get_product, open_database, seed

db = open_database()
seed(db, [("A-1", "cable", 12)])
print(get_product(db, "A-1").quantity)
seed(db, [("A-1", "cable", 5)])
print(get_product(db, "A-1").quantity)
print(get_product(db, "UNKNOWN"))
db.close()
PY
```

预期输出为 `12`、`5`、`None`。朴素的静态文档答案在这里失效；需要增加的是实时读取边界，而不是更多召回候选。

## 第二步：固定查询成为第一个检查点

创建 `labs/live_data/checkpoints/v0.py`。`open_database` 和 `seed` 只给本地实验准备数据，Agent 不拿到这两个写入入口。`get_product` 只执行一个固定、参数化的 SELECT；找不到返回 `None`，找到返回带时间的 `InventoryResult`。下面是本版完整 checkpoint。

```python
"""v0 checkpoint: one fixed inventory lookup with an observation timestamp."""

from __future__ import annotations

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


def open_database(path: str = ":memory:") -> sqlite3.Connection:
    connection = sqlite3.connect(path)
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
        "INSERT OR REPLACE INTO inventory(sku, category, quantity) VALUES (?, ?, ?)", rows
    )
    connection.commit()


def get_product(connection: sqlite3.Connection, sku: str) -> InventoryResult | None:
    row = connection.execute(
        "SELECT sku, category, quantity FROM inventory WHERE sku = ?", (sku,)
    ).fetchone()
    if row is None:
        return None
    return InventoryResult(
        row["sku"], row["category"], row["quantity"],
        datetime.now(timezone.utc).isoformat(),
    )
```

## 检查和冻结

```bash
uv run python -m pytest -q tests/test_live_data_checkpoints.py -k v0
```

它重放创建表、读取、零库存与不存在的状态。最新实现的库存变化测试也可运行：

```bash
uv run python -m pytest -q tests/test_live_data.py -k v0
```

现在固定 SKU 的事实来自查询结果。仍然存在外部参数问题：超长或无效 SKU 会进入数据库，类别列表也可能请求无界页。下一版在工具输入边界定义参数契约。
