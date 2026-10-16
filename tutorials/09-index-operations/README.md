# 索引更新与运行成本

状态：verified，代码、测试和本地测量脚本已实现。前置：04 v4、08 v3；报告明确记录本地小规模限制。

实现：`labs/operations/index.py`、`labs/operations/serving.py`；独立版本源码：`labs/operations/checkpoints/v0/` 至 `v4/`；测试：`tests/test_operations.py`。

- [v0：批量索引](v0/tutorial.md) · [范围计划](v0/plan.md)
- [v1：增量与删除](v1/tutorial.md) · [范围计划](v1/plan.md)
- [v2：缓存](v2/tutorial.md) · [范围计划](v2/plan.md)
- [v3：并发与背压](v3/tutorial.md) · [范围计划](v3/plan.md)
- [v4：质量成本联合报告](v4/tutorial.md) · [范围计划](v4/plan.md)

每版完整源码都能从对应 checkpoint 目录直接导入重放；最后一版汇总已讲解的实现与验证边界。参见 [编写约定](../../docs/authoring.md)。
