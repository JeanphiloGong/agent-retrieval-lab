# 混合检索 v3：重排

状态：verified。实现、教程、固定语料与测试已完成。独立 checkpoint：[labs/hybrid/checkpoints/v3_rerank.py](../../../labs/hybrid/checkpoints/v3_rerank.py)。重放：

```bash
uv run python -m labs.hybrid.checkpoints.v3_rerank
uv run python -m pytest -q tests/test_hybrid_checkpoints.py -k v3
```

## 本版写作任务

- 描述：从“融合前列仍有主题相似但不回答问题的块”出发，让读者观察“否定句和适用范围导致误排”，再引入本版机制。
- 前置：本专题 v2 的已验证检查点。
- 当前缺口：否定句和适用范围导致误排。
- 必要改变：对有界候选集合应用 reranker。
- 验收及验证：比较 nDCG、证据命中与延迟；模型失败可观测。
- 正文目标：本目录 `tutorial.md`；代码目标：`labs/hybrid/`；验证目标：`tests/hybrid/`。
- 代码角色：patch，正文末尾提供该版完整 checkpoint。
- 预计范围：一个版本；若实现需要多个独立机制，应先拆为多个写作任务。
- 提交策略：规划阶段不提交检查点；正文和实现通过复验后再保存版本 commit。

## 冻结与后续

完成后冻结“重排”及对应验证结果。本版仍未处理“平均分掩盖精确查询退化”；下一版推进“消融评测”。

编写前需补齐固定样例、精确文件名、输入输出、正常/非法/故障/边界检查和执行轨迹。遵循 [编写约定](../../../docs/authoring.md)，不把计划中的验收条件写成已通过结果。
