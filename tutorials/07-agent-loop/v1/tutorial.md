# Agent 检索循环 v1：选择并执行注册工具

从自己的 v0 继续。库存、代码、手册要走不同数据源，调用者不能永远预先选一个搜索器。本版加入 ToolInfo、ToolCall、Finish 和一个单次选择的 Planner 协议，运行时只执行注册工具。本版会直接更新 Tool 的接口和下面所有调用方。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 先区分选择动作与执行权限

Tool.info 描述名字、说明和参数类型，Tool.run 仍接收一个参数映射。Evidence 增加 source_version/locator，citation 包含文本摘要，避免相同 ID 的不同证据混淆。Planner.decide 接收问题和 ToolInfo 元组，只返回 ToolCall 或拒答 Finish。此时尚未观察证据，所以任何 answerable=True 的 Finish 都拒绝，不能靠凭空 citation 获得成功。

完整替换 loop.py。answer_once 同步改成读取 tool.info.name，并保留真实工具名的 trace；run_agent 检查工具名唯一，处理未知工具，最后调用 answer_once。一个 Planner 只决定一次，本版不允许先搜索再规划第二次。

`labs/agent/loop.py` — checkpoint：将这个文件完整写为下面的代码。

```python
"""A version-local Agent contract; no future runtime imports."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

@dataclass(frozen=True)
class Evidence:
    source_id: str
    source_version: str
    locator: str
    text: str

    @property
    def citation(self) -> str:
        digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]
        return f"{self.source_id}@{self.source_version}:{self.locator}#{digest}"

@dataclass(frozen=True)
class ToolInfo:
    name: str
    description: str
    parameters: Mapping[str, str]

@dataclass(frozen=True)
class Tool:
    info: ToolInfo
    run: Callable[[Mapping[str, Any]], tuple[Evidence, ...]]

@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Mapping[str, Any]

@dataclass(frozen=True)
class Finish:
    answerable: bool
    text: str
    citations: tuple[str, ...] = ()

class Planner(Protocol):
    def decide(self, question: str, tools: tuple[ToolInfo, ...]) -> ToolCall | Finish:
        """Choose one registered tool or decline the question."""


@dataclass(frozen=True)
class AgentAnswer:
    answerable: bool
    text: str
    citations: tuple[str, ...]
    trace: tuple[str, ...]
    stop_reason: str


def answer_once(question: str, tool: Tool, arguments: Mapping[str, Any]) -> AgentAnswer:
    if not question.strip():
        raise ValueError("question must be nonempty")
    evidence = tool.run(arguments)
    if not evidence:
        return AgentAnswer(False, "The allowed sources do not answer this question.", (), (tool.info.name,), "no_evidence")
    return AgentAnswer(True, evidence[0].text, tuple(item.citation for item in evidence), (tool.info.name,), "answered")


def run_agent(question: str, tools: Sequence[Tool], planner: Planner) -> AgentAnswer:
    if not question.strip():
        raise ValueError("question must be nonempty")
    registry = {tool.info.name: tool for tool in tools}
    if len(registry) != len(tools):
        raise ValueError("tool names must be unique")
    decision = planner.decide(question, tuple(tool.info for tool in tools))
    if isinstance(decision, Finish):
        if decision.answerable or decision.citations:
            return AgentAnswer(False, "No observed evidence.", (), (), "invalid_citation")
        return AgentAnswer(False, decision.text, (), (), "no_evidence")
    tool = registry.get(decision.name)
    if tool is None:
        return AgentAnswer(False, "Unknown tool.", (), (), "unknown_tool")
    return answer_once(question, tool, decision.arguments)
```

```bash
uv run python - <<'PY'
from labs.agent.loop import Evidence, Finish, Tool, ToolCall, ToolInfo, run_agent

item = Evidence("manual", "v1", "lines:1-1", "deploy safely")
tool = Tool(ToolInfo("read", "Read the fixed source", {}), lambda args: (item,))
class FixedPlanner:
    def decide(self, question, infos):
        assert infos[0].name == "read"
        return ToolCall("read", {})
answer = run_agent("deployment", (tool,), FixedPlanner())
assert answer.answerable and answer.citations == (item.citation,)
assert answer.trace == ("read",)
class FabricatingPlanner:
    def decide(self, question, infos):
        return Finish(True, "unsupported", ("never-seen",))
rejected = run_agent("deployment", (), FabricatingPlanner())
assert not rejected.answerable and rejected.stop_reason == "invalid_citation"
print("registered tool executed; unsupported Finish rejected")
PY
```

预期打印 `registered tool executed; unsupported Finish rejected`。仅有一个字符串形式的引用不等于取得了证据。

## 2. 连接版本化文档的搜索与读取

新建 tools.py。SourceDocument 是宿主提供的文档快照；_arguments 在工具边界检查字段集合、实际类型与非空字符串。lexical_tool 闭包保存这份可信快照，复用 BM25 并把 Hit 转成 Evidence；read_tool 只接受快照中的 source_id，不能把它当任意文件路径。重复 ID 报错，未知 ID 返回空证据。

`labs/agent/tools.py` — checkpoint：将这个文件完整写为下面的代码。

```python
"""Bind real retrieval, file, and SQLite operations to the Agent contract."""
from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from labs.code_search.reader import read_range
from labs.hybrid.retrieval import Document, bm25_rank
from labs.live_data.query import get_product
from .loop import Evidence, Tool, ToolInfo


@dataclass(frozen=True)
class SourceDocument:
    source_id: str
    source_version: str
    text: str


def _arguments(arguments: Mapping[str, Any], expected: Mapping[str, type]) -> None:
    if set(arguments) != set(expected):
        raise ValueError(f"expected exactly {', '.join(sorted(expected))}")
    for name, value_type in expected.items():
        if type(arguments[name]) is not value_type:
            raise ValueError(f'{name} must be {value_type.__name__}')
        if value_type is str and (not arguments[name].strip()):
            raise ValueError(f'{name} must be nonempty')


def lexical_tool(documents: Sequence[SourceDocument], *, limit: int=1) -> Tool:
    """Run the existing BM25 implementation over versioned documents."""
    if limit < 1:
        raise ValueError('limit must be positive')
    by_id = {document.source_id: document for document in documents}
    if len(by_id) != len(documents):
        raise ValueError('source IDs must be unique in a searchable snapshot')
    corpus = [Document(document.source_id, document.text) for document in documents]

    def run(arguments: Mapping[str, Any]) -> tuple[Evidence, ...]:
        _arguments(arguments, {'query': str})
        hits = bm25_rank(corpus, arguments['query'])[:limit]
        evidence: list[Evidence] = []
        for hit in hits:
            document = by_id[hit.document.id]
            evidence.append(Evidence(document.source_id, document.source_version, f'lines:1-{max(1, len(document.text.splitlines()))}', document.text))
        return tuple(evidence)
    return Tool(ToolInfo('bm25_search', 'Search versioned source text using BM25', {'query': 'string'}), run)


def read_tool(documents: Sequence[SourceDocument]) -> Tool:
    """Read a whole small document from a trusted in-memory source registry."""
    by_id = {document.source_id: document for document in documents}
    if len(by_id) != len(documents):
        raise ValueError('source IDs must be unique in a readable snapshot')

    def run(arguments: Mapping[str, Any]) -> tuple[Evidence, ...]:
        _arguments(arguments, {'source_id': str})
        document = by_id.get(arguments['source_id'])
        if document is None:
            return ()
        return tuple([Evidence(document.source_id, document.source_version, f'lines:1-{max(1, len(document.text.splitlines()))}', document.text)])
    return Tool(ToolInfo('read_document', 'Read a known source ID, never an arbitrary path', {'source_id': 'string'}), run)
```

```bash
uv run python - <<'PY'
from labs.agent.loop import ToolCall, run_agent
from labs.agent.tools import SourceDocument, lexical_tool, read_tool

sources = (SourceDocument("deploy", "v1", "rolling deployment"),)
search, read = lexical_tool(sources), read_tool(sources)
class SearchPlanner:
    def decide(self, question, infos):
        return ToolCall("bm25_search", {"query": question})
answer = run_agent("rolling deployment", (search, read), SearchPlanner())
assert answer.answerable and "deploy@v1:" in answer.citations[0]
assert read.run({"source_id": "missing"}) == ()
try:
    read.run({"path": "/etc/passwd"})
except ValueError:
    print("document bindings and argument boundary passed")
else:
    raise AssertionError("unexpected path accepted")
PY
```

预期打印 `document bindings and argument boundary passed`。描述里的参数类型供规划器阅读，真正校验由 _arguments 执行。

## 3. 连接库存和代码读取

继续追加两个工具。inventory_tool 接收宿主创建的 SQLite 连接，调用 06 的 get_product，只接受 SKU；返回数量和 observed_at，后者成为这条实时证据的版本。code_tool 复用 02 的工作区安全 read_range，只允许路径与行号，固定返回上限 65536 字节。它们返回同一种 Evidence，规划器不获得数据库连接或工作区外路径权限。

`labs/agent/tools.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
def code_tool(workspace: Path, *, source_version: str) -> Tool:
    """Reuse the code-search topic's bounded, workspace-confined range reader."""

    def run(arguments: Mapping[str, Any]) -> tuple[Evidence, ...]:
        _arguments(arguments, {'path': str, 'start_line': int, 'end_line': int})
        result = read_range(workspace, arguments['path'], start_line=arguments['start_line'], end_line=arguments['end_line'], max_bytes=65536)
        return tuple([Evidence(result.path, source_version, f'lines:{result.start_line}-{result.end_line}', result.text)])
    return Tool(ToolInfo('read_code', 'Read an inclusive UTF-8 line range inside the fixed workspace', {'path': 'string', 'start_line': 'integer', 'end_line': 'integer'}), run)


def inventory_tool(connection: sqlite3.Connection) -> Tool:
    """Use the real allow-listed inventory lookup; never accept model SQL."""

    def run(arguments: Mapping[str, Any]) -> tuple[Evidence, ...]:
        _arguments(arguments, {'sku': str})
        result = get_product(connection, arguments['sku'])
        if result is None:
            return ()
        text = json.dumps({'sku': result.sku, 'category': result.category, 'quantity': result.quantity, 'observed_at': result.observed_at}, sort_keys=True)
        return tuple([Evidence('inventory', result.observed_at, f'sku:{result.sku}', text)])
    return Tool(ToolInfo('inventory_lookup', 'Read current quantity of a validated product SKU', {'sku': 'string'}), run)
```

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.agent.loop import ToolCall, run_agent
from labs.agent.tools import inventory_tool, code_tool
from labs.live_data.query import open_database, seed

db = open_database()
try:
    seed(db, [("SKU_1", "widget", 12)])
    inventory = inventory_tool(db)
    code = code_tool(Path("fixtures/code_search/repository"), source_version="fixture-v1")
    class InventoryPlanner:
        def decide(self, question, infos):
            return ToolCall("inventory_lookup", {"sku": "SKU_1"})
    answer = run_agent("inventory SKU_1", (inventory, code), InventoryPlanner())
    assert answer.answerable and '"quantity": 12' in answer.text
    assert code.run({"path": "app.py", "start_line": 1, "end_line": 2})
    try:
        inventory.run({"sql": "SELECT * FROM inventory"})
    except ValueError:
        print("inventory and code bindings passed")
    else:
        raise AssertionError("arbitrary SQL accepted")
finally:
    db.close()
PY
```

预期打印 `inventory and code bindings passed`。连接由宿主关闭，工具函数不拥有生命周期。本版异常仍向调用者传播；下一版先加入多轮轨迹，再在 v3 统一停止原因。

## 本版检查点

本版完整 checkpoint 是 loop.py 与三步组成的 tools.py，所有工具都采用单参数回调。不要将 v3 带预算的 tools.py 混进此版。下一版扩展规划器输入，让它基于已见结果补充来源。

需要对照时可阅读[本版参考源码](../../../reference/labs/agent/checkpoints/v1)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
