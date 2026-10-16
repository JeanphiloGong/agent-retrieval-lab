# 权限与多租户

状态：verified，代码与测试已实现。前置：02 v0、03 v3、04 v2；实现用于本地教学，仍需生产级身份系统和审计设施。

实现：`labs/access/control.py`；独立版本源码：`labs/access/checkpoints/v0/` 至 `v3/`；测试：`tests/test_access.py`。

- [v0：租户隔离](v0/tutorial.md) · [范围计划](v0/plan.md)
- [v1：文档授权](v1/tutorial.md) · [范围计划](v1/plan.md)
- [v2：缓存隔离](v2/tutorial.md) · [范围计划](v2/plan.md)
- [v3：对抗检查](v3/tutorial.md) · [范围计划](v3/plan.md)

每版完整源码都能从对应 checkpoint 目录直接导入重放；最后一版汇总已讲解的实现与验证边界。参见 [编写约定](../../docs/authoring.md)。
