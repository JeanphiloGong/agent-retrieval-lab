# 长文档导航 v2：读取有限范围

## 你要手动构建的部分

从自己的 v1 继续，在 `labs/navigation/navigation.py` 增加 `RangeRead` 与 `read_range`，不重写已有导航逻辑。按下面的截断、跨边界和过期内容实验验证自己的代码。完整参考供对照，不能以参考回放替代个人验收；参见[学习流程](../../../docs/learning-workflow.md)。

v1 只给出值得打开的节点。手册可能在下一段或下一章节才写限制，读取结果还可能因为预算而被截断。本版增加 `RangeRead` 和 `read_range()`：结果始终携带实际返回的来源、版本、行范围、字符范围与截断状态。

完整代码是 `reference/labs/navigation/checkpoints/v2/navigation.py`。本版只在 v1 之后增加结果类型和读取函数。返回对象替代朴素的 `(text, truncated)`，因为后者无法准确表达跨章节扩展和截断后的证据位置。

## 1. 先验证节点没有过期

节点来自某一份确切文本。`read_range()` 对文本重新计算 SHA-256，与节点的 `source_digest` 对比，不相等就报错。仅凭调用者仍传 `source_version='v1'` 无法保证内容没被修改；摘要检查避免旧行号静默指向新内容。

`before` 和 `after` 允许从章节边界向前后扩展，均为非负行数。`max_lines` 必须为正数，约束真正返回的行数。所有索引以从 1 开始且包含端点的行号表示，对外不暴露列表的从 0 开始规则。

## 2. 观察截断后的真实范围

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.navigation.navigation import document_tree, read_range

text = Path('fixtures/navigation/manual-v1.md').read_text()
section = document_tree(text, source_id='manual', source_version='v1')[1]
result = read_range(text, section, max_lines=2)
print(result.start_line, result.end_line, result.truncated)
print(repr(result.quote))
assert result.quote == text[result.start_offset:result.end_offset]
PY
```

结果范围是第 3–4 行，`truncated=True`，quote 为 `## Install\nVersion 3 can be installed on Linux.\n`。它不会继续声称引用覆盖第 3–6 行。调用者看到截断后应决定补读，不能把没返回的限制条件当作已经检查。

## 3. 跨边界读取与行尾保持

把 `after=4`、`max_lines=20` 传入同一安装节点，会扩展到第 10 行，包含附录标题与“免费计划不支持版本 3”。这是调用者明确要求的范围扩展，结果仍返回实际起止位置。

内部使用 `splitlines(keepends=True)` 建立字符偏移，不用 `join` 重建文本，所以 CRLF、中文字符和末尾换行都与原文一致。测试 `test_range_expansion_crosses_section_boundary_exactly` 用 CRLF 和中文标题检查这一点。字符偏移不能直接当字节偏移传给文件系统读取；需要字节寻址时应单独定义并转换。

## 4. 拒绝错误输入

```bash
uv run python - <<'PY'
from labs.navigation.navigation import document_tree, read_range

text = '# Manual\nOriginal.\n'
section = document_tree(text)[0]
try:
    read_range(text + 'Changed.\n', section)
except ValueError as exc:
    print(str(exc))
PY
```

输出 `section belongs to different document content`。负数扩展、零预算与越界节点也被拒绝，不产生看似有效的空引用。

```bash
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/test_navigation.py -k 'range or stale'
```

上面的 pytest 命令只回放参考答案；个人验收使用前面的截断、范围扩展与错误输入实验。只有自己的代码得到相同边界行为才冻结本版。当前尚未把正文许可、附录排除和另一份发布说明组合起来；下一版保留每条出处，并分别评测单文档和多文档问题。
