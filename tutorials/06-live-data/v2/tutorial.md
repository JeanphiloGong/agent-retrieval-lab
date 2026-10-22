# SQL 与业务 API v2：受限查询

## 你要手动构建的部分

从自己的 v1 继续修改 `labs/live_data/query.py`，加入查询结果、拒绝和预算错误类型，以及 `query_readonly`。下面完整代码是组装结果，实验应在你实现对应函数后运行。不要让主线导入参考 checkpoint；按[学习流程](../../../docs/learning-workflow.md)检查数据没有被拒绝的写操作修改，再保存自己的版本。

## 聚合需求暴露固定工具的边界

用户从“查 A-1”转而问“cable 类别总共有多少库存”。不断新增固定函数可以解决部分需求，但本版选择一个小而完整的受限 SQL 实验：只读取本地 `inventory` 表，允许少量聚合函数，单次只能执行一个语句，并限制结果行数与执行工作量。

提示词里写“只允许 SELECT”不是执行权限。`SELECT load_extension(...)`、`ATTACH` 或一次提交多条语句都可能突破这种口头约束。本版的核心不变量是：查询入口永远创建自己新的只读连接；调用者不能传入一个已获得写权限的连接。

## 第一步：让 SQLite 保证只读范围

`query_readonly` 把文件路径转成 `file:...?...mode=ro` URI，避免创建不存在的数据库，再设置 `PRAGMA query_only=ON`。SQLite authorizer 只放行 SELECT、读取 `inventory`，以及 `sum/count/min/max/avg/coalesce`。所有写入、PRAGMA、ATTACH、系统表读取和未授权函数默认拒绝。这里不靠字符串前缀判断 SQL，真正的 SQL 解析由 SQLite 完成。

执行使用 `connection.execute`，它拒绝多语句。参数仍通过占位符传入，查询完成时间和来源一起返回。可以先运行实际聚合：

```bash
uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from labs.live_data.query import open_database, query_readonly, seed, QueryRejected

with TemporaryDirectory() as directory:
    path = Path(directory) / "inventory.sqlite"
    db = open_database(path)
    seed(db, [("A-1", "cable", 12), ("A-2", "cable", 0)])
    print(query_readonly(path, "SELECT SUM(quantity) AS total FROM inventory WHERE category = ?", ("cable",)).rows)
    try:
        query_readonly(path, "DELETE FROM inventory")
    except QueryRejected:
        print("write rejected")
    db.close()
PY
```

预期结果为 `({'total': 12},)` 和 `write rejected`。后者不能仅凭异常成立；测试还会重新读取库存，确认数据没有变化。

## 第二步：预算也是执行契约

只读查询仍可能让三个大表做笛卡尔积。SQLite progress handler 每 100 个虚拟机操作检查 monotonic deadline 和操作预算；超出时终止并抛 `QueryBudgetExceeded`。它属于合作式中断，精度是检查间隔，不是操作系统级硬隔离。连接的锁等待也使用相同秒数的 timeout。

结果用 `fetchmany(max_rows + 1)` 读取；一旦多出一行就抛 `QueryRowLimitExceeded`，避免静默截断后让 Agent 以为得到了完整聚合。`max_rows` 限制行数，单元格大小由这个教学表的整数/短文本 schema 约束；本版不声称支持任意 blob 数据。

## 第三步：冻结完整执行边界

将下面组装代码落实到自己的 `labs/live_data/query.py`，保留 v1 的固定工具并增加三种明确错误和 `query_readonly`。它包含已经解释的连接权限、authorizer、单语句和预算机制；完整参考答案在 `reference/labs/live_data/checkpoints/v2.py`。

```python
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
```

## 检查和冻结

先用自己的代码运行聚合与拒绝写入实验，再重新读取数据库确认内容没变。以下命令只回放参考答案对应的验收，不要求你的 v2 提前实现 v3 API：

```bash
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/test_live_data.py -k v2
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q reference/tests/test_live_data_checkpoints.py -k v2
```

验证覆盖正常聚合、绑定参数、写入、DDL、多语句、关闭 query-only、ATTACH、系统表和扩展读取、结果超限、操作预算、极短 deadline，以及不存在数据库不会被创建。现在 SQL 工具能回答受限聚合。它仍不知道手册中的备货政策是否与当前库存处于同一时间和范围；下一版只在证据可组合时给出政策判断。
