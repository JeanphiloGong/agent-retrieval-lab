# 索引更新与运行成本

资料状态：教程、参考代码、测试和本地测量脚本已准备；你的实现从 v0 开始。前置：04 v4、08 v3；报告明确记录本地小规模限制。

你的实现：`labs/operations/index.py`，之后增加 `serving.py`、`benchmark.py`；参考版本：`reference/labs/operations/checkpoints/v0/` 至 `v4/`；测试材料：`tests/test_operations.py`。先读[手动构建流程](../../docs/learning-workflow.md)。

- [v0：批量索引](v0/tutorial.md) · [范围计划](v0/plan.md)
- [v1：增量与删除](v1/tutorial.md) · [范围计划](v1/plan.md)
- [v2：缓存](v2/tutorial.md) · [范围计划](v2/plan.md)
- [v3：并发与背压](v3/tutorial.md) · [范围计划](v3/plan.md)
- [v4：质量成本联合报告](v4/tutorial.md) · [范围计划](v4/plan.md)

每版修改自己的主线文件，检查后提交 Git 检查点；参考源码用于对照和显式回放。现有测试导入最终 API，早期按本版例子验证，v4 再运行完整专题验收。参见[编写约定](../../docs/authoring.md)。
