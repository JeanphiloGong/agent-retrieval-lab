# 长文档导航 v0：先保留文档树

前置是 03 v3 的来源版本和 04 v2 的召回结果。离散块可以找到一段话，却无法回答“这份安装手册有哪些章节，哪些限制属于安装条件”。本版以固定的 `fixtures/navigation/manual-v1.md` 为输入，保留章节顺序、父子关系与原文范围。

实现文件是 `labs/navigation/navigation.py`。本版完整源码保存在 `labs/navigation/checkpoints/v0/navigation.py`，仅含标题解析，不依赖之后的检索、读取或组合能力。可以从这个文件逐行构建，或直接按检查点导入重放。

## 1. 把标题变成可定位节点

`Section` 有 `id`、标题、标题级别、父节点和子节点。`start_line` 从标题行开始，`end_line` 到同级或更高级标题之前；子章节属于父章节范围。`own_end_line` 则只到下一个任意标题之前，避免之后检索时把全部后代文字重复计入父节点。

它还保存 `source_id`、`source_version`、内容摘要与字符偏移。偏移量采用 Python 字符索引，不是 UTF-8 字节数；`text[start_offset:end_offset]` 必须等于该章节包含后代的原文。内容摘要用于拒绝后续拿旧节点读取修改后的文本。

## 2. 顺序扫描标题与围栏

朴素的 `line.startswith('#')` 会把 Markdown 代码示例里的标题误当章节。`document_tree()` 先识别最多三格缩进的反引号或波浪号围栏；围栏内所有行都作为内容。只有围栏外的 ATX 标题才进入树。维护一个标题栈：新标题到来时，弹出同级或更深节点并冻结它们的结束位置，栈顶就是父节点。

重复标题保留不同顺序 ID，不以标题文字作为唯一键。无标题且非空的文档返回一个 `level=0` 的 `Document` 节点；标题前的文字保留为 `preamble` 节点；空文档返回空列表。这三个行为避免把“没有标题”误当“没有可读材料”。

## 3. 运行固定输入

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.navigation.checkpoints.v0.navigation import document_tree

text = Path('fixtures/navigation/manual-v1.md').read_text()
for section in document_tree(text, source_id='manual', source_version='v1'):
    print(section.id, section.title, section.start_line, section.end_line,
          section.parent, section.children)
PY
```

输出顺序是 `Installation Manual`、`Install`、`Appendix`、`Free plan limits`、`Examples`。样例第 16–17 行的 `# This is not a real chapter` 和 `## Neither is this` 不出现在目录中。`Install` 范围是第 3–6 行，附录范围包含第 9 行的限制子章节。

检查 `tests/test_navigation.py` 中的标题顺序、无标题、前言、重复标题和围栏实验。测试还验证四空格缩进代码中的 `#` 不成为标题，以及 `C#` 中的末尾 `#` 不被当作关闭标记删除。

```bash
uv run python -m unittest tests.test_navigation -v
```

本专题的 11 项确定性测试通过，其中本版先运行前三项即可重放目录边界。本解析器支持 ATX 标题和围栏代码；没有实现 Setext 标题、HTML 块和 Markdown 全语法。需要任意来源文档时应接入完整 Markdown 解析器并继续保留相同的范围契约。

本版冻结结构和来源位置，尚不知道该打开哪个节点。下一版使用节点自身的标题与正文做确定性定位。
