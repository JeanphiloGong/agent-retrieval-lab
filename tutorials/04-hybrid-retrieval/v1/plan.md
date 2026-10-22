# 混合检索 v1：向量检索

参考状态：verified。仅表示预写参考材料的验证记录；你的实现进度单独记录在 [个人进度](../../../docs/progress.md)。参考代码位于 `reference/labs/`，重放命令见 [参考区](../../../reference/README.md)；本版手写目标仍是 `labs/`，按 [正文](tutorial.md) 构建。

```bash
PYTHONPATH=reference uv run python -P -m labs.hybrid.checkpoints.v1_vector
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q reference/tests/test_hybrid_checkpoints.py -k v1
```

## 本版写作任务

- 描述：从“只有词项相关性”出发，让读者观察“用户改写术语后没有共同关键词”，再引入本版机制。
- 前置：本专题 v0 的已验证检查点。
- 当前缺口：用户改写术语后没有共同关键词。
- 必要改变：增加固定模型的向量检索对照。
- 验收及验证：缓存模型版本；比较改写题与精确题；失败不返回伪结果。
- 正文目标：本目录 `tutorial.md`；代码目标：`labs/hybrid/`；验证目标：`tests/test_hybrid.py`。
- 代码角色：patch，正文末尾提供该版完整 checkpoint。
- 预计范围：一个版本；若实现需要多个独立机制，应先拆为多个写作任务。
- 提交策略：规划阶段不提交检查点；正文和实现通过复验后再保存版本 commit。

## 冻结与后续

完成后冻结“向量检索”及对应验证结果。本版仍未处理“两种分数尺度不同不能直接相加”；下一版推进“结果融合”。

编写前需补齐固定样例、精确文件名、输入输出、正常/非法/故障/边界检查和执行轨迹。遵循 [编写约定](../../../docs/authoring.md)，不把计划中的验收条件写成已通过结果。
