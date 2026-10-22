# 混合检索 v4：消融评测

参考状态：verified。仅表示预写参考材料的验证记录；你的实现进度单独记录在 [个人进度](../../../docs/progress.md)。参考代码位于 `reference/labs/`，重放命令见 [参考区](../../../reference/README.md)；本版手写目标仍是 `labs/`，按 [正文](tutorial.md) 构建。

```bash
PYTHONPATH=reference uv run python -P -m labs.hybrid.checkpoints.v4_benchmark --output artifacts/hybrid-heldout.json --split heldout
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/test_hybrid.py reference/tests/test_hybrid_checkpoints.py
```

## 本版写作任务

- 描述：从“单个案例看起来更好”出发，让读者观察“平均分掩盖精确查询退化”，再引入本版机制。
- 前置：本专题 v3 的已验证检查点。
- 当前缺口：平均分掩盖精确查询退化。
- 必要改变：固定测试集比较各检索组合。
- 验收及验证：报告分组质量、成本、p50/p95；不预设混合一定获胜。
- 正文目标：本目录 `tutorial.md`；代码目标：`labs/hybrid/`；验证目标：`tests/test_hybrid.py`。
- 代码角色：patch，正文末尾提供该版完整 checkpoint。
- 预计范围：一个版本；若实现需要多个独立机制，应先拆为多个写作任务。
- 提交策略：规划阶段不提交检查点；正文和实现通过复验后再保存版本 commit。

## 冻结与后续

完成后冻结“消融评测”及对应验证结果。本版最后组装该专题的完整可运行检查点，只汇总已解释的代码；记录依赖版本、已验证边界与未覆盖的生产场景。

编写前需补齐固定样例、精确文件名、输入输出、正常/非法/故障/边界检查和执行轨迹。遵循 [编写约定](../../../docs/authoring.md)，不把计划中的验收条件写成已通过结果。
