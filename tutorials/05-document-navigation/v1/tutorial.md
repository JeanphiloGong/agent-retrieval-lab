# 长文档导航 v1：定位节点而不是直接回答

v0 保留了手册目录，但“免费计划是否能安装版本 3”仍可能被 `Install` 标题吸引而漏掉附录。本版增加 `_terms()` 与 `find_sections()`，在节点标题和节点自身正文上建立透明的词项检索入口。输入仍为同一份手册，不新增摘要生成模型。

完整检查点是 `labs/navigation/checkpoints/v1/navigation.py`，在 v0 完整源码之后新增两个函数；此前函数保持一致。节点的 `text` 保留自己的正文，不把后代再次复制到父节点，所以同一句限制不会让根节点、附录和限制节点同时获得相同匹配。

## 1. 用具体问题观察结果

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.navigation.checkpoints.v1.navigation import document_tree, find_sections

text = Path('fixtures/navigation/manual-v1.md').read_text()
sections = document_tree(text, source_id='manual', source_version='v1')
for section in find_sections(sections, 'free plan'):
    print(section.id, section.title, section.start_line)
print(find_sections(sections, 'unmentioned'))
PY
```

第一条返回 `s4 Free plan limits 9`，第二条返回 `[]`。这只是“值得读取的节点”，不是“答案已得到确认”。标题写着 `Free plan limits` 并不说明限制到底是什么，仍须读取原文第 9–12 行。

## 2. 保持排序可解释

`_terms()` 将英文词、小写字母数字标记与中文单字转成集合。`find_sections()` 统计查询与节点词项交集大小，过滤零命中，然后按分数、节点深度、来源、版本与起始行稳定排序。分数只是这个定位器的内部排序值，不能拿它与 BM25 或向量余弦分数直接相加。

空查询与无命中均返回空列表，因为没有足够词项定位；文件解析错误不在这里处理，调用者应先成功构建 v0 的树。中文单字切分仅为本地可重放基线，不能据此宣称中文检索质量达标。

## 3. 检查结果与来源的关系

`find_sections()` 不改写节点和原文；每个结果仍带着 v0 的 `source_id`、版本、行范围和内容摘要。测试 `test_find_section_returns_appendix_condition` 验证附录限制排在首位，并验证根节点正文不包含安装子章节的文字。

```bash
uv run python -m unittest tests.test_navigation -v
```

专题 11 项测试通过。当前检索只表达词面重合，不能可靠处理同义改写，也没有证明检索结果支持一个回答。下一版通过有预算、可定位的原文读取把候选变成证据；v3 再与 04 的混合检索比较。
