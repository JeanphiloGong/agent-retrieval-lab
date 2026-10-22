# 权限与多租户 v1：文档授权

参考状态：verified。仅表示预写参考材料的验证记录；你的实现进度单独记录在 [个人进度](../../../docs/progress.md)。参考代码位于 `reference/labs/`，重放命令见 [参考区](../../../reference/README.md)；本版手写目标仍是 `labs/`，按 [正文](tutorial.md) 构建。
重放命令：`PYTHONPATH=reference uv run python -P -c "from labs.access.checkpoints.v1.control import authorize; print(authorize)"`。

## 本版写作任务

- 描述：从“只按租户过滤”出发，让读者观察“同租户普通成员无权看财务文档”，再引入本版机制。
- 前置：本专题 v0 的已验证检查点。
- 当前缺口：同租户普通成员无权看财务文档。
- 必要改变：在检索和读取边界执行文档授权。
- 验收及验证：未授权证据不进入重排或模型上下文；撤权后读被拒绝。
- 正文目标：本目录 `tutorial.md`；代码目标：`labs/access/`；验证目标：`tests/test_access.py`。
- 代码角色：patch，正文末尾提供该版完整 checkpoint。
- 预计范围：一个版本；若实现需要多个独立机制，应先拆为多个写作任务。
- 提交策略：规划阶段不提交检查点；正文和实现通过复验后再保存版本 commit。

## 冻结与后续

完成后冻结“文档授权”及对应验证结果。本版仍未处理“管理员缓存被普通用户命中”；下一版推进“缓存隔离”。

编写前需补齐固定样例、精确文件名、输入输出、正常/非法/故障/边界检查和执行轨迹。遵循 [编写约定](../../../docs/authoring.md)，不把计划中的验收条件写成已通过结果。
