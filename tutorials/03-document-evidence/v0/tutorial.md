# 文档处理与证据定位 v0：文本提取

## 读者目标

技术助手需要回答“退款期限是多少”，并给出能复核的来源。手工复制正文看起来很快，但复制后来源、版本和页信息都消失了。这个版本只解决第一件事：把本地 Markdown 和小型 PDF 变成带来源和版本的提取记录。

## 压缩后的问题

我们只处理一个本地文件、一个稳定的 `source_id`、一个调用方提供的 `source_version`，以及两种输入格式。Markdown 以 UTF-8 读取，PDF 使用锁定的 `pypdf` 解析，逐页保留文字。扫描 PDF 不伪装成成功的空文档，而是返回页级 `ocr_required` 问题；加密和损坏 PDF 则明确失败。生产级版式、OCR 和页内坐标留到后续专题。

从仓库根目录运行 `uv sync --locked`。依赖与测试工具来自 `uv.lock`，无需 API 密钥或外部服务。样例是仓库自建数据；`uv run python fixtures/documents/build_pdfs.py` 可以重新生成两个真实 PDF。

## 第一步：从外部文件开始

先看调用方能提供的事实：

```python
from labs.documents.v0_extract import extract_document

document = extract_document(
    "fixtures/documents/handbook-v1.md",
    source_id="handbook",
    source_version="v1",
)
print(document.source_id, document.source_version)
print(document.text.splitlines()[0])
```

朴素的 `Path.read_text()` 能得到正文，却不能告诉回答者正文来自哪个版本；对扫描 PDF，它还会把“没有提取到文字”误报成成功。

## 第二步：保存提取状态

在 `labs/documents/v0_extract.py` 中，`ExtractedDocument` 保存 `source_id`、`source_version`、路径、格式、正文、页文本和提取问题。`extract_document` 是唯一的输入边界：它校验来源元数据和文件存在性，Markdown 使用 UTF-8 读取；PDF 由 `PdfReader` 解析，每页文字各自保存在 `page_text`，空页附加页号明确的 `ocr_required`。空页可能是真空页，也可能是扫描图，所以下游必须检查它，不能断言已经完成 OCR。

运行固定样例：

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.documents.v0_extract import extract_document

root = Path("fixtures/documents")
for name in ("handbook-v1.md", "notice.pdf", "scanned.pdf"):
    result = extract_document(root / name, name, "v1")
    print(name, result.format, repr(result.text), result.needs_ocr)
PY
```

你会看到 Markdown 和文字 PDF 有正文，`notice.pdf` 的两页文字通过换页符连接；`scanned.pdf` 的正文为空但 `needs_ocr` 为 `True`。这是一种可处理的失败，而不是静默丢证据。

## 第二步：冻结完整检查点

下面是 `labs/documents/v0_extract.py` 的完整 checkpoint。它只包含上面已经解释的机制；从空文件创建此模块，不需要将分散片段拼接。

```python
"""v0: extract local Markdown and PDF text with source and page metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True)
class ExtractionIssue:
    code: str
    message: str
    page_number: int | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    source_id: str
    source_version: str
    path: Path
    format: str
    text: str
    page_text: tuple[str, ...]
    issues: tuple[ExtractionIssue, ...] = ()

    @property
    def needs_ocr(self) -> bool:
        return any(issue.code == "ocr_required" for issue in self.issues)


def _require_metadata(source_id: str, source_version: str) -> None:
    if not source_id.strip():
        raise ValueError("source_id must be non-empty")
    if not source_version.strip():
        raise ValueError("source_version must be non-empty")


def extract_document(
    path: str | Path,
    source_id: str,
    source_version: str,
) -> ExtractedDocument:
    """Read a local document while retaining source and version metadata."""

    _require_metadata(source_id, source_version)
    document_path = Path(path)
    if not document_path.is_file():
        raise FileNotFoundError(document_path)

    suffix = document_path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        text = document_path.read_text(encoding="utf-8")
        return ExtractedDocument(
            source_id,
            source_version,
            document_path,
            "markdown",
            text,
            (text,),
        )

    if suffix == ".pdf":
        try:
            reader = PdfReader(document_path, strict=True)
            if reader.is_encrypted:
                raise ValueError("encrypted PDF requires a password")
            pages = tuple(page.extract_text().strip() for page in reader.pages)
            if not pages:
                raise ValueError("PDF has no pages")
        except PdfReadError as exc:
            raise ValueError("PDF could not be parsed") from exc
        issues = tuple(
            ExtractionIssue(
                "ocr_required",
                "page contains no extractable text; inspect it for OCR",
                page_number=index,
            )
            for index, text in enumerate(pages, start=1)
            if not text
        )
        return ExtractedDocument(
            source_id,
            source_version,
            document_path,
            "pdf",
            "\n\f\n".join(pages),
            pages,
            issues,
        )

    raise ValueError(f"unsupported document format: {suffix or '<none>'}")
```



完整实现位于 [labs/documents/v0_extract.py](../../../labs/documents/v0_extract.py)，测试位于 [tests/documents/test_v0_extract.py](../../../tests/documents/test_v0_extract.py)。运行：

```bash
uv run pytest -q tests/documents/test_v0_extract.py
```

测试覆盖 Markdown 的来源和版本、两页文字 PDF、OCR 页号、未知扩展名、空来源、不存在文件、损坏 PDF 和加密 PDF。实际运行结果：6 passed。扫描识别只说明没有可提取文字，不推测图片里的文本。

## 冻结与下一步

现在可以保留“正文来自哪个来源版本”并明确报告 OCR 缺口。它仍然把文档当成平面字符串：当两个 `## Refunds` 标题出现时，回答无法区分它们，表格边界也无法追踪。下一版本在这个检查点上增加标题路径和块的行范围。
