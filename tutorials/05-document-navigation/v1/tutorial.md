# 长文档导航 v1：找出值得读取的节点

从自己的 v0 继续。目录已经保留，但问题“免费计划能否安装版本 3”可能需要附录。增加一个透明的词项定位器，先给出候选节点，尚不返回答案。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 只给节点自身的词项计分

`_terms` 提取英文标记和中文单字，转小写集合。`find_sections` 以标题与节点自身正文的词项交集大小评分，过滤零匹配。排序按分数、深度、来源、版本、起始行，保证并列结果稳定。输入节点不修改，结果仍带原来的版本和范围。

`labs/navigation/navigation.py` — patch：在现有导入之后加入下面的导入；不要重复已有项。

```python
from typing import Iterable
```

`labs/navigation/navigation.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text)}


def find_sections(sections: Iterable[Section], query: str) -> list[Section]:
    """Rank a node's own title/body; descendants do not inflate parent scores."""

    terms = _terms(query)
    if not terms:
        return []
    ranked: list[tuple[int, Section]] = []
    for section in sections:
        score = len((_terms(section.title) | _terms(section.text)) & terms)
        if score:
            ranked.append((score, section))
    ranked.sort(key=lambda item: (-item[0], -item[1].level,
                                  item[1].source_id, item[1].source_version,
                                  item[1].start_line))
    return [section for _, section in ranked]
```

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.navigation.navigation import document_tree, find_sections

text = Path("fixtures/navigation/manual-v1.md").read_text()
sections = document_tree(text, source_id="manual", source_version="v1")
hits = find_sections(sections, "free plan")
assert hits[0].title == "Free plan limits"
assert hits[0].start_line == 9
assert find_sections(sections, "unmentioned") == []
assert find_sections(sections, "") == []
assert "Version 3 can be installed" not in sections[0].text
print(hits[0].id, hits[0].title, hits[0].start_line)
PY
```

预期 `s4 Free plan limits 9`。这说明应读哪里；还没有读取限制原文，也不证明回答完整。

## 本版检查点

保留 v0，追加 _terms 与 find_sections 即为本版文件。当前定位只能识别词面重合，下一版把节点转换成有预算的可核对引文。

需要对照时可阅读[本版参考源码](../../../reference/labs/navigation/checkpoints/v1/navigation.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
