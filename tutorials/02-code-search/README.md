# 代码与精确检索

参考材料状态：已验证；这不代表你已完成本专题。前置：01 v1。

手写实现：`labs/code_search/`（开始时没有实现）；参考答案：`reference/labs/code_search/`；固定样例：`fixtures/code_search/repository/`；验收测试：`tests/code_search/`。

- [v0：受限文件读取](v0/tutorial.md) · [原计划](v0/plan.md)
- [v1：grep 定位](v1/tutorial.md) · [原计划](v1/plan.md)
- [v2：AST 定位](v2/tutorial.md) · [原计划](v2/plan.md)
- [v3：符号与引用](v3/tutorial.md) · [原计划](v3/plan.md)

四版采用增量文件检查点：v0 手写 `reader.py`，v1 在自己的 v0 上加入 `grep_search.py`，v2 再加入 `ast_search.py`，v3 再加入 `symbols.py`。完成每版的行为实验和对应测试后，再提交自己的学习检查点。教程使用具体模块导入，因此 `labs/code_search/__init__.py` 可以为空，不必提前导入未来版本的符号。

完整参考源码保存在 `reference/labs/code_search/checkpoints/v0/` 至 `v3/`；它们用于对照和显式重放，不能代替你的实现或作为学习完成记录。最后一版汇总验证边界。参见 [编写约定](../../docs/authoring.md)。
