# 长文档导航 v3：组合证据并比较两种检索

从自己的 v2 和 04 v2 继续。安装说明、免费计划限制、发布说明的维护窗口可能共同约束一个回答。本版按明确子问题收集多来源证据，不把冲突文本合成无出处摘要；再比较树定位与混合召回。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 从候选节点读取并保留多来源证据

documents 的键是 `(source_id, version)`，queries 是调用者明确提供的证据子问题。tree 路径复用 find_sections；hybrid 把节点自己的标题和正文装入 Document，调用已完成的 BM25、vector 和 RRF，再映射回 Section。这个固定 MiniLM 模型使用对称的 embed 编码接口；其他模型的查询前缀/编码规则不能直接套用。

每个候选都经过 read_range，Evidence 保存实际位置和 truncated。去重键包含来源、版本、节点 ID，因此不同文档的同名章节不会覆盖。embedding 由调用者显式传入，缺失时拒绝 hybrid；库不隐式下载模型。

`labs/navigation/navigation.py` — patch：在现有导入之后加入下面的导入；不要重复已有项。

```python
from typing import Literal, Mapping
```

`labs/navigation/navigation.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
@dataclass(frozen=True)
class Evidence:
    source_id: str
    section_id: str
    quote: str
    start_line: int
    end_line: int
    source_version: str
    start_offset: int
    end_offset: int
    truncated: bool


def combine_evidence(
    documents: Mapping[tuple[str, str], str],
    queries: Iterable[str],
    *,
    strategy: Literal["tree", "hybrid"] = "tree",
    top_k: int = 1,
    max_lines: int = 40,
    embedding=None,
) -> list[Evidence]:
    """Gather evidence across sources without merging contradictory quotes.

    Queries are explicit evidence subquestions, supplied by the caller.  This
    function does not infer that a question is completely answered merely
    because one section was returned.
    """

    if strategy not in {"tree", "hybrid"}:
        raise ValueError("unknown navigation strategy")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    sections: list[Section] = []
    for (source_id, version), text in documents.items():
        sections.extend(document_tree(text, source_id=source_id, source_version=version))
    if strategy == "hybrid":
        from labs.hybrid.retrieval import Document, bm25_rank, rrf_fuse, vector_rank

        if embedding is None:
            raise ValueError("hybrid navigation requires an embedding model")
        corpus = [Document(str(index), section.title + "\n" + section.text)
                  for index, section in enumerate(sections)]
        vectors = [list(vector) for vector in embedding.embed([document.text for document in corpus])]
    chosen: list[Evidence] = []
    known: set[tuple[str, str, str]] = set()
    for query in queries:
        if strategy == "tree":
            ranked = find_sections(sections, query)
        else:
            query_vector = list(next(iter(embedding.embed([query]))))
            fused = rrf_fuse(bm25_rank(corpus, query), vector_rank(corpus, vectors, query_vector))
            ranked = [sections[int(hit.document.id)] for hit in fused]
        for section in ranked[:top_k]:
            identity = (section.source_id, section.source_version, section.id)
            if identity in known:
                continue
            result = read_range(documents[(section.source_id, section.source_version)],
                                section, max_lines=max_lines)
            chosen.append(Evidence(result.source_id, result.section_id, result.quote,
                                   result.start_line, result.end_line, result.source_version,
                                   result.start_offset, result.end_offset, result.truncated))
            known.add(identity)
    return chosen
```

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.navigation.navigation import combine_evidence

root = Path("fixtures/navigation")
documents = {("manual", "v1"): (root / "manual-v1.md").read_text(),
             ("release", "v1"): (root / "release-v1.md").read_text()}
items = combine_evidence(documents, ["Install Linux", "free plan limits", "maintenance"])
assert len(items) == 3
assert {item.source_id for item in items} == {"manual", "release"}
for item in items:
    text = documents[item.source_id, item.source_version]
    assert item.quote == text[item.start_offset:item.end_offset]
assert len(combine_evidence(documents, ["Install Linux", "Install Linux"])) == 1
try:
    combine_evidence(documents, ["install"], strategy="hybrid")
except ValueError:
    print("sources, deduplication and explicit model boundary passed")
else:
    raise AssertionError("hybrid ran without an encoder")
PY
```

预期打印 `sources, deduplication and explicit model boundary passed`。三条证据同时保留，不依据章节顺序擅自认定某一条更权威。

## 2. 按单文档与多文档问题分别评测

`compare_navigation` 消费固定 cases，gold_evidence 是来源/版本/节点的集合。mean_recall 衡量找回比例，complete_evidence_rate 要求所有 gold 同时出现。两个分组分别报告题数，避免简单单文档题掩盖跨文档缺口。无 gold 或未知组别是标注错误，直接拒绝。

`labs/navigation/navigation.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
def compare_navigation(
    documents: Mapping[tuple[str, str], str],
    cases: Sequence[dict],
    *,
    top_k: int = 1,
    embedding=None,
) -> dict[str, dict[str, dict[str, float | int]]]:
    """Compare evidence recall, separately for single/multiple source questions."""

    report: dict[str, dict[str, dict[str, float | int]]] = {}
    for strategy in ("tree", "hybrid"):
        groups: dict[str, list[tuple[float, bool]]] = {"single_document": [], "multi_document": []}
        for case in cases:
            category = case["category"]
            if category not in groups:
                raise ValueError("unknown question category")
            expected = {(item["source_id"], item["source_version"], item["section_id"])
                        for item in case["gold_evidence"]}
            if not expected:
                raise ValueError("evaluation case requires gold evidence")
            evidence = combine_evidence(documents, case["queries"], strategy=strategy,
                                        top_k=top_k, embedding=embedding)
            actual = {(item.source_id, item.source_version, item.section_id) for item in evidence}
            recall = len(expected & actual) / len(expected)
            groups[category].append((recall, expected <= actual))
        report[strategy] = {
            category: {
                "questions": len(values),
                "mean_recall": sum(value[0] for value in values) / len(values) if values else 0.0,
                "complete_evidence_rate": sum(value[1] for value in values) / len(values) if values else 0.0,
            }
            for category, values in groups.items()
        }
    return report
```

```bash
uv run python -m pytest -q tests/test_navigation.py
```

10 项测试应通过，覆盖树、精确范围、过期内容、冲突证据和模型契约。测试的 FixtureEmbedding 只验证接线算术。

```bash
uv run python - <<'PY'
import json
from pathlib import Path
from labs.hybrid.models import load_embedding
from labs.navigation.navigation import compare_navigation

root = Path("fixtures/navigation")
documents = {("manual", "v1"): (root / "manual-v1.md").read_text(),
             ("release", "v1"): (root / "release-v1.md").read_text()}
cases = json.loads((root / "questions.json").read_text())
report = compare_navigation(documents, cases, embedding=load_embedding(Path("artifacts/models")))
for groups in report.values():
    assert groups["single_document"]["questions"] == 1
    assert groups["multi_document"]["questions"] == 1
Path("artifacts/my-navigation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
PY
```

应输出 tree/hybrid 各两个分组，每组 1 题，并保存自己的报告。记录实际 recall 和完整证据率；这两题只检查功能链路，不能作为模型质量或容量结论。

## 本版检查点

v0 的树、v1 的定位、v2 的读取与本版 Evidence/combine_evidence/compare_navigation 组成最终 navigation.py。回答层仍须判断证据是否支持结论；PDF/OCR、权限和并发索引分别在其他专题处理。

需要对照时可阅读[本版参考源码](../../../reference/labs/navigation/navigation.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
