# 代码与精确检索

状态：已实现并通过本地验证。前置：01 v1。

实现：`labs/code_search/`；固定样例：`fixtures/code_search/repository/`；测试：`tests/code_search/`。

- [v0：受限文件读取](v0/tutorial.md) · [原计划](v0/plan.md)
- [v1：grep 定位](v1/tutorial.md) · [原计划](v1/plan.md)
- [v2：AST 定位](v2/tutorial.md) · [原计划](v2/plan.md)
- [v3：符号与引用](v3/tutorial.md) · [原计划](v3/plan.md)

四版采用增量文件检查点：v0 使用 `reader.py`，v1 再加入 `grep_search.py`，v2 再加入 `ast_search.py`，v3 再加入 `symbols.py`。完整源码分别保存在 `labs/code_search/checkpoints/v0/` 至 `v3/`，可直接按版本导入重放，不依赖未来最新实现。最后一版汇总验证边界。参见 [编写约定](../../docs/authoring.md)。
