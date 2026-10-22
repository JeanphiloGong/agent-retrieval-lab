# SQL 与业务 API

资料状态：教程、参考代码与测试已准备；你的实现从 v0 开始。前置：01 v2；SQL 基础。

你编写的主线文件是 `labs/live_data/query.py`；预写历史答案在 `reference/labs/live_data/checkpoints/`。先读[手动构建流程](../../docs/learning-workflow.md)。测试材料为 `tests/test_live_data.py`、`reference/tests/test_live_data_checkpoints.py`，后者只验证参考快照。

- [v0：固定查询](v0/tutorial.md)（[计划](v0/plan.md)）
- [v1：参数契约](v1/tutorial.md)（[计划](v1/plan.md)）
- [v2：受限查询](v2/tutorial.md)（[计划](v2/plan.md)）
- [v3：实时与历史结合](v3/tutorial.md)（[计划](v3/plan.md)）

每版在自己的 `query.py` 上继续写，完成本版例子后提交 Git 检查点，无需在 `labs/` 复制预写快照。现有主线测试在导入时需要最终 API，完整专题验收留到 v3；早期先用本版示例验证。参见[编写约定](../../docs/authoring.md)。
