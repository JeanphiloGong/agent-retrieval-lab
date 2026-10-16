# 长文档导航 v3：组合跨章节证据并比较检索

v2 可以按节点读取范围，但一个真实回答往往需要多条约束：正文允许安装、附录排除免费计划，另一份发布说明还给出支持截止日期。本版增加 `Evidence`、`combine_evidence()` 和 `compare_navigation()`，将多来源证据保留为独立记录，并把结构导航与 04 的混合检索放到同一组评测问题上。

完整源码是 `labs/navigation/checkpoints/v3/navigation.py`。前三个检查点的 API 仍可用；新增函数不把冲突证据合并成一段无出处的摘要。

## 1. 组合时保留来源

`combine_evidence(documents, queries, strategy='tree', top_k=1, max_lines=40)` 接受 `{(source_id, source_version): text}`，而不是一个可能混淆来源的长字符串。每个 query 是一个需要证据的子问题；函数在树定位或混合召回中选出节点，调用 v2 的范围读取，并把来源、版本、section_id、实际行/字符范围和 `truncated` 写入 `Evidence`。重复节点在同一来源版本内去重；不同文档中的同标题不会被覆盖。

```bash
uv run python - <<'PY'
import json
from pathlib import Path
from labs.navigation.checkpoints.v3.navigation import combine_evidence

root = Path('fixtures/navigation')
documents = {
    ('manual', 'v1'): (root / 'manual-v1.md').read_text(),
    ('release', 'v1'): (root / 'release-v1.md').read_text(),
}
items = combine_evidence(documents, ['Install Linux', 'free plan limits', 'maintenance'])
for item in items:
    print(item.source_id, item.source_version, item.section_id,
          item.start_line, item.end_line, item.truncated)
PY
```

结果分别包含手册安装、手册免费计划限制和发布说明支持期限。正文“可安装”和附录“免费计划不支持”同时出现，调用者必须向用户展示两条出处，由回答层解释条件关系。此工具不根据章节顺序擅自选择“更权威”的一条。

## 2. 比较结构导航与混合检索

`strategy='hybrid'` 要求传入已经加载的真实 embedding 模型。实现使用 04 的 `bm25_rank` 和 `vector_rank`，通过 RRF 合并候选，再读取同一 `Section`；不能使用教程早期的固定 HashEmbedding 冒充生产模型。模型与 tokenizer 由 `labs/hybrid/models.py` 的锁定 FastEmbed/ONNX 检查点提供。

```bash
uv run python - <<'PY'
import json
from pathlib import Path
from labs.hybrid.models import load_embedding
from labs.navigation.navigation import compare_navigation

root = Path('fixtures/navigation')
documents = {('manual', 'v1'): (root / 'manual-v1.md').read_text(),
             ('release', 'v1'): (root / 'release-v1.md').read_text()}
cases = json.loads((root / 'questions.json').read_text())
report = compare_navigation(documents, cases,
                            embedding=load_embedding(Path('artifacts/models')))
print(json.dumps(report, indent=2))
PY
```

2026-10-16 的本地模型运行报告为：tree 与 hybrid 的 single_document、multi_document 各 1 题，`mean_recall=1.0`、`complete_evidence_rate=1.0`。这是两个小问题和一份本地模型的功能检查，不是生产质量结论。固定问题集明确把单文档与多文档问题分组，新增数据集应保留这两个分组并报告样本数。

测试使用 `FixtureEmbedding` 验证检索后端契约，另有上述真实 FastEmbed 命令验证模型接线；两者不能互相替代。没有 embedding 时 hybrid 明确抛出错误，不能静默退回树或固定向量。

## 最终检查点

```bash
uv run python -m unittest tests.test_navigation -v
```

本专题目前 11 项确定性测试通过。覆盖树顺序、空文档、围栏标题、重复标题、精确 CRLF/中文范围、过期内容、截断、跨来源冲突、单/多文档分组和 hybrid 后端要求。仍未覆盖 PDF 版面、OCR、权限过滤、跨文档去重实体和大型索引容量；这些属于 03、08、09 的后续边界。导航完成的是证据定位，回答层仍须独立检查证据是否足以支持结论。
