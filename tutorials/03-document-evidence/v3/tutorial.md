# 文档处理与证据定位 v3：稳定引用

## 读者目标

回答“退款期限是七天”时，引用不能只保存一个会变化的行号。它必须说明 `handbook@v1`，并确认该范围的内容仍是生成答案时看到的内容。

## 压力示例

`handbook-v2.md` 把七天改成十四天。若系统只保存 `start_line=5`，旧答案会静默显示新内容，读者无法发现答案和证据来自不同时间。

## 第一步：把版本和内容摘要放进引用

`make_citation` 根据结构化文档的 1-based 行范围生成 `Citation`，保存 `source_id`、`source_version`、范围和引用文本的 SHA-256。`VersionedDocumentStore` 按 `(source_id, source_version)` 保存完整文档：同一版本不能被不同正文覆盖；新版本用新键保存。

```python
from pathlib import Path
from labs.documents.v0_extract import extract_document
from labs.documents.v1_structure import structure_document
from labs.documents.v3_citations import VersionedDocumentStore, cite_block

def load(name, version):
    raw = extract_document(Path("fixtures/documents") / name, "handbook", version)
    return structure_document(raw)

document = load("handbook-v1.md", "v1")
block = next(block for block in document.blocks if "seven days" in block.text)
citation = cite_block(document, block)
store = VersionedDocumentStore()
store.add(document)
print(citation)
print(store.resolve(citation))
```

解析时先查精确版本，再重新计算该行范围的摘要。版本不存在抛出 `CitationUnavailable`；摘要不一致抛出 `CitationMismatch`。这两个失败状态不能被“尽量返回附近文本”吞掉。

## 第二步：冻结完整检查点

下面是 `labs/documents/v3_citations.py` 的完整 checkpoint。它只包含上面已经解释的机制；保留前一版本模块并创建本版模块，不需要将分散片段拼接。

```python
"""v3: resolve citations against immutable source versions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .v1_structure import DocumentBlock, StructuredDocument


class CitationUnavailable(LookupError):
    """The cited source version is no longer available."""


class CitationMismatch(ValueError):
    """The cited range exists but no longer has the cited content."""


@dataclass(frozen=True)
class Citation:
    source_id: str
    source_version: str
    start_line: int
    end_line: int
    quote_sha256: str


def _range_text(document: StructuredDocument, start_line: int, end_line: int) -> str:
    if start_line < 1 or end_line < start_line:
        raise ValueError("citation line range is invalid")
    lines = document.text.splitlines()
    if end_line > len(lines):
        raise ValueError("citation line range is outside document")
    return "\n".join(lines[start_line - 1 : end_line])


def make_citation(document: StructuredDocument, start_line: int, end_line: int) -> Citation:
    quote = _range_text(document, start_line, end_line)
    return Citation(
        source_id=document.source_id,
        source_version=document.source_version,
        start_line=start_line,
        end_line=end_line,
        quote_sha256=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
    )


def cite_block(document: StructuredDocument, block: DocumentBlock) -> Citation:
    return make_citation(document, block.start_line, block.end_line)


class VersionedDocumentStore:
    """Keep each source version addressable without silently overwriting it."""

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], StructuredDocument] = {}

    def add(self, document: StructuredDocument) -> None:
        key = (document.source_id, document.source_version)
        existing = self._documents.get(key)
        if existing is not None and existing.text != document.text:
            raise ValueError(f"source version already contains different content: {key}")
        self._documents[key] = document

    def remove(self, source_id: str, source_version: str) -> None:
        self._documents.pop((source_id, source_version), None)

    def resolve(self, citation: Citation) -> str:
        document = self._documents.get((citation.source_id, citation.source_version))
        if document is None:
            raise CitationUnavailable(
                f"source version unavailable: {citation.source_id}@{citation.source_version}"
            )
        quote = _range_text(document, citation.start_line, citation.end_line)
        digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()
        if digest != citation.quote_sha256:
            raise CitationMismatch("cited range changed for the recorded source version")
        return quote
```



完整实现位于 [labs/documents/v3_citations.py](../../../labs/documents/v3_citations.py)。运行：

```bash
uv run pytest -q tests/documents/test_v3_citations.py
```

测试覆盖旧引用解析、新版本不重定向、删除版本显式不可用、同版本拒绝覆盖，以及相同行范围的内容变化检测。

## 专题检查点

四个版本组合成一条可运行链：

```text
v0 extract_document
  -> v1 structure_document
  -> v2 structure_chunks
  -> v3 make_citation / VersionedDocumentStore.resolve
```

全量运行：

```bash
uv run pytest -q tests/documents
```

这条链已经覆盖本专题的核心边界：来源和版本保留、标题与表格结构、固定预算下的分块，以及旧版本证据不会静默指向新内容。实际运行结果：23 passed。PDF 使用 pypdf 的文字提取；真正的 OCR、复杂版式、页内坐标、多语言分词和跨文档证据组合仍属于后续专题。
