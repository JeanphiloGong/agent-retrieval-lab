# 检索基线与评测

材料状态：v0-v2 教程、固定输入、验收测试和参考实现已备好。你的学习进度：尚未开始，从 v0 自己创建文件。前置：无；Python、JSON 和基础测试。

你手动编写的实现放在 `labs/evaluation/`；预写答案位于 `reference/labs/evaluation/`；验收测试位于 `tests/evaluation/`；固定语料位于 `fixtures/evaluation/`。普通命令只导入你的实现，不自动调用参考答案。

- [v0：固定问题与证据](v0/tutorial.md)（范围计划：[plan.md](v0/plan.md)）
- [v1：关键词基线](v1/tutorial.md)（范围计划：[plan.md](v1/plan.md)）
- [v2：分别评估检索与回答](v2/tutorial.md)（范围计划：[plan.md](v2/plan.md)）

每版先按教程手动编写，再只运行该版及此前版本的测试；不要一开始运行包含未来模块的完整测试集。v0 从空包和 `validate.py` 开始，v1 增加 `keyword.py`，v2 增加 `metrics.py`。自己通过验收后再提交学习检查点；参考区通过验收不改变你的学习进度。参见 [编写约定](../../docs/authoring.md)。
