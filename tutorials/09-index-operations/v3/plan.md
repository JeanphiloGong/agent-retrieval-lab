# 索引更新与运行成本 v3：并发与背压

参考状态：verified。仅表示预写参考材料的验证记录；你的实现进度单独记录在 [个人进度](../../../docs/progress.md)。参考代码位于 `reference/labs/`，重放命令见 [参考区](../../../reference/README.md)；本版手写目标仍是 `labs/`，按 [正文](tutorial.md) 构建。
重放命令：`PYTHONPATH=reference uv run python -P -c "from labs.operations.checkpoints.v3.serving import WorkerPool; print(WorkerPool)"`。

## 本版写作任务

- 描述：从“并发请求无上限”出发，让读者观察“模型或索引处理变慢造成排队膨胀”，再引入本版机制。
- 前置：本专题 v2 的已验证检查点。
- 当前缺口：模型或索引处理变慢造成排队膨胀。
- 必要改变：增加有界队列与执行并发。
- 验收及验证：过载有明确拒绝；取消释放资源；队列不无限增长。
- 正文目标：本目录 `tutorial.md`；代码目标：`labs/operations/`；验证目标：`tests/test_operations.py`。
- 代码角色：patch，正文末尾提供该版完整 checkpoint。
- 预计范围：一个版本；若实现需要多个独立机制，应先拆为多个写作任务。
- 提交策略：规划阶段不提交检查点；正文和实现通过复验后再保存版本 commit。

## 冻结与后续

完成后冻结“并发与背压”及对应验证结果。本版仍未处理“优化提高吞吐却丢失证据质量”；下一版推进“质量成本联合报告”。

编写前需补齐固定样例、精确文件名、输入输出、正常/非法/故障/边界检查和执行轨迹。遵循 [编写约定](../../../docs/authoring.md)，不把计划中的验收条件写成已通过结果。
