# 权限与多租户

资料状态：教程、参考代码与测试已准备；你的实现从 v0 开始。前置：02 v0、03 v3、04 v2；实现用于本地教学，仍需生产级身份系统和审计设施。

你的实现：`labs/access/control.py`；参考版本：`reference/labs/access/checkpoints/v0/` 至 `v3/`；测试材料：`tests/test_access.py`。先读[手动构建流程](../../docs/learning-workflow.md)。

- [v0：租户隔离](v0/tutorial.md) · [范围计划](v0/plan.md)
- [v1：文档授权](v1/tutorial.md) · [范围计划](v1/plan.md)
- [v2：缓存隔离](v2/tutorial.md) · [范围计划](v2/plan.md)
- [v3：对抗检查](v3/tutorial.md) · [范围计划](v3/plan.md)

每版在自己的文件上增加一个权限边界，检查后提交 Git 检查点；参考源码只供对照与显式回放。现有测试导入最终 API，早期用本版例子检查，v3 再完整验收。参见[编写约定](../../docs/authoring.md)。
