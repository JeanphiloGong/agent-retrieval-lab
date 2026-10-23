# 长文档导航 v2：读取有边界的原文

从自己的 v1 继续。节点可能覆盖数百行，读取还可能因预算截断。本版返回 RangeRead 对象，准确记录实际返回的行号、字符偏移和截断状态；不会把计划读取范围当成已经获得的证据。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 读取前核对内容版本，再计算实际范围

`read_range` 首先重算摘要，拒绝用旧节点读新内容。before/after 是非负的前后扩展行数，max_lines 是正的返回行数预算。用 keepends=True 保持 CRLF；从原字符串直接切片，避免重组文本改变引文。RangeRead 的字段直接用于下一版 Evidence，调用者通过 `.quote` 和 `.truncated` 读取结果。

`labs/navigation/navigation.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
@dataclass(frozen=True)
class RangeRead:
    source_id: str
    source_version: str
    section_id: str
    quote: str
    start_line: int
    end_line: int
    start_offset: int
    end_offset: int
    truncated: bool


def read_range(
    text: str,
    section: Section,
    *,
    before: int = 0,
    after: int = 0,
    max_lines: int = 80,
) -> RangeRead:
    """Read an exact, budgeted slice and report the actual returned range."""

    if min(before, after) < 0 or max_lines < 1:
        raise ValueError("range limits must be non-negative and max_lines must be positive")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != section.source_digest:
        raise ValueError("section belongs to different document content")
    lines = text.splitlines(keepends=True)
    if not 1 <= section.start_line <= section.end_line <= len(lines):
        raise ValueError("section range is outside document")
    offsets = _line_offsets(lines)
    start = max(1, section.start_line - before)
    requested_end = min(len(lines), section.end_line + after)
    actual_end = min(requested_end, start + max_lines - 1)
    start_offset, end_offset = offsets[start - 1], offsets[actual_end]
    return RangeRead(section.source_id, section.source_version, section.id,
                     text[start_offset:end_offset], start, actual_end,
                     start_offset, end_offset, actual_end < requested_end)
```

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.navigation.navigation import document_tree, read_range

text = Path("fixtures/navigation/manual-v1.md").read_text()
section = document_tree(text, source_id="manual", source_version="v1")[1]
short = read_range(text, section, max_lines=2)
assert (short.start_line, short.end_line, short.truncated) == (3, 4, True)
assert short.quote == "## Install\nVersion 3 can be installed on Linux.\n"
assert short.quote == text[short.start_offset:short.end_offset]
expanded = read_range(text, section, after=4, max_lines=20)
assert expanded.end_line == 10
assert "free plan" in expanded.quote.lower()
crlf = "# 手册\r\n## Install\r\nAllowed.\r\n## Limit\r\nExcept free plans.\r\n"
node = document_tree(crlf)[1]
result = read_range(crlf, node, after=2)
assert result.quote == crlf[result.start_offset:result.end_offset]
assert "Except free plans.\r\n" in result.quote
print("exact ranges, expansion and CRLF passed")
PY
```

预期打印 `exact ranges, expansion and CRLF passed`。短结果只覆盖 3–4 行；扩展读取明确取得附录内容。

## 2. 让过期节点和非法预算失败

同一个 source_version 标签不保证文本没变，摘要才检查这次实际输入。不能用截断后的半句支持一个完整结论；调用者必须决定是否补读。

```bash
uv run python - <<'PY'
from labs.navigation.navigation import document_tree, read_range

text = "# Manual\nOriginal.\n"
node = document_tree(text)[0]
for content, options in ((text + "Changed.\n", {}), (text, {"max_lines": 0}), (text, {"before": -1})):
    try:
        read_range(content, node, **options)
    except ValueError:
        continue
    raise AssertionError("invalid read accepted")
print("stale content and invalid budgets rejected")
PY
```

预期打印 `stale content and invalid budgets rejected`；不返回一个看似有效的空引文掩盖错误。

## 本版检查点

在 v1 之后追加 RangeRead/read_range 就得到完整本版，不添加旧元组接口。下一版把多条读取结果组合，继续保留各自出处。

需要对照时可阅读[本版参考源码](../../../reference/labs/navigation/checkpoints/v2/navigation.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
