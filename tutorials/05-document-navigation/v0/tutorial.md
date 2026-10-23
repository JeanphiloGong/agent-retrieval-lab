# 长文档导航 v0：保存目录与原文位置

前置：03 v3 的来源/版本契约与 04 v2 的检索能力。分块能找到一句话，但安装限制可能藏在附录。本版先把 Markdown 变成有顺序、父子关系和精确范围的目录。输入是原始字符串，输出是 Section 列表；只支持 ATX 标题与围栏代码，不宣称实现完整 Markdown 规范。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 定义节点并扫描真实标题

`start_line/end_line` 是从 1 开始、包含端点的章节范围，包含后代。`own_end_line` 只到下一个标题之前，text 只保留自己的正文，防止父节点重复获得子节点的检索分数。字符偏移是 Python 字符索引，不是 UTF-8 字节数。`_line_offsets` 把行长度累加，用于将行边界转换成原文切片。

```bash
mkdir -p labs/navigation
touch labs/__init__.py labs/navigation/__init__.py
```

这两个 `__init__.py` 是空的包文件；已有文件保留，下面才开始实现本版行为。

扫描时先识别围栏，围栏内的 `#` 是代码数据。每个新标题弹出同级或更深的栈元素，冻结它们的结束位置；剩余栈顶就是父节点。无标题非空文档生成 Document 节点，标题前文字生成 preamble，空文档返回空列表。顺序 ID 使重复标题不会互相覆盖。

`labs/navigation/navigation.py` — checkpoint：将这个文件完整写为下面的代码。

```python
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class Section:
    id: str
    title: str
    level: int
    start_line: int
    end_line: int
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    text: str = ""
    own_end_line: int = 0
    start_offset: int = 0
    end_offset: int = 0
    source_id: str = "markdown"
    source_version: str = ""
    source_digest: str = ""


def _line_offsets(lines: Sequence[str]) -> list[int]:
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    return offsets


def document_tree(
    text: str,
    *,
    source_id: str = "markdown",
    source_version: str | None = None,
) -> list[Section]:
    """Build ordered sections without treating fenced examples as headings."""

    if not source_id or source_version == "":
        raise ValueError("source metadata must be nonempty")
    lines = text.splitlines(keepends=True)
    if not lines:
        return []
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    version = source_version or digest
    offsets = _line_offsets(lines)
    headings: list[tuple[int, int, str]] = []
    fence_char: str | None = None
    fence_length = 0
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\r\n")
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence_char:
            closing = re.match(rf"^ {{0,3}}{re.escape(fence_char)}{{{fence_length},}}[ \t]*$", line)
            if closing:
                fence_char = None
            continue
        if fence:
            marker, info = fence.groups()
            if marker[0] != "`" or "`" not in info:
                fence_char, fence_length = marker[0], len(marker)
            continue
        match = re.match(r"^ {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)$", line)
        if match:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2) or "").strip()
            headings.append((line_number, len(match.group(1)), title))

    if not headings:
        return [Section("s1", "Document", 0, 1, len(lines), text=text,
                        own_end_line=len(lines), end_offset=len(text),
                        source_id=source_id, source_version=version, source_digest=digest)]

    sections: list[Section] = []
    stack: list[Section] = []
    if headings[0][0] > 1 and any(line.strip() for line in lines[:headings[0][0] - 1]):
        end = headings[0][0] - 1
        sections.append(Section("preamble", "Preamble", 0, 1, end,
                                text="".join(lines[:end]), own_end_line=end,
                                end_offset=offsets[end], source_id=source_id,
                                source_version=version, source_digest=digest))
    for number, (start, level, title) in enumerate(headings):
        while stack and stack[-1].level >= level:
            previous = stack.pop()
            previous.end_line = start - 1
            previous.end_offset = offsets[start - 1]
        parent = stack[-1] if stack else None
        own_end = headings[number + 1][0] - 1 if number + 1 < len(headings) else len(lines)
        section = Section(
            f"s{number + 1}", title, level, start, len(lines),
            parent.id if parent else None,
            text="".join(lines[start:own_end]), own_end_line=own_end,
            start_offset=offsets[start - 1], end_offset=len(text),
            source_id=source_id, source_version=version, source_digest=digest,
        )
        if parent:
            parent.children.append(section.id)
        sections.append(section)
        stack.append(section)
    return sections
```

调用者给出 source_version，未给出时使用文本 SHA-256；source_digest 始终保存实际内容摘要。后续读取会验证摘要，避免旧节点指向已修改的文本。文档树只是来源定位，尚未选择证据。

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.navigation.navigation import document_tree

text = Path("fixtures/navigation/manual-v1.md").read_text()
sections = document_tree(text, source_id="manual", source_version="v1")
assert [s.title for s in sections] == ["Installation Manual", "Install", "Appendix", "Free plan limits", "Examples"]
assert (sections[1].start_line, sections[1].end_line) == (3, 6)
assert sections[3].parent == sections[2].id
assert sections[3].id in sections[2].children
assert document_tree("") == []
assert document_tree("plain text")[0].title == "Document"
assert document_tree("intro\n# Title\n")[0].id == "preamble"
for s in sections:
    assert s.start_offset < s.end_offset
print([(s.id, s.title, s.parent) for s in sections])
PY
```

预期五个节点，代码示例中的假标题不出现在目录。Install 覆盖 3–6 行，限制节点属于 Appendix。

## 2. 验证围栏和重复标题边界

标题字符串不能充当唯一键；四空格缩进中的 `#` 也不能成为节点。用小输入检验扫描器状态，错误最容易在这里暴露。

```bash
uv run python - <<'PY'
from labs.navigation.navigation import document_tree

text = "# Root\n```md\n# fake\n```\n~~~\n## also fake\n~~~~\n    # code\n## C#\n## Same\n## Same\n"
sections = document_tree(text)
assert [s.title for s in sections] == ["Root", "C#", "Same", "Same"]
assert sections[-1].id != sections[-2].id
assert [s.start_line for s in sections] == [1, 9, 10, 11]
print("fences and duplicate titles passed")
PY
```

预期打印 `fences and duplicate titles passed`。Setext 标题、HTML 块和 PDF 版面不在此解析器范围内。

## 本版检查点

完整 navigation.py 包含 Section、_line_offsets、document_tree。下一版在节点自己的标题/正文上定位问题。最终测试模块导入后续 API，此时只执行本页实验。

需要对照时可阅读[本版参考源码](../../../reference/labs/navigation/checkpoints/v0/navigation.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
