# 混合检索 v0：BM25

状态：verified。实现、教程、固定语料与测试已完成。独立 checkpoint：[labs/hybrid/checkpoints/v0_bm25.py](../../../labs/hybrid/checkpoints/v0_bm25.py)。重放：

```bash
uv run python -m labs.hybrid.checkpoints.v0_bm25
uv run python -m pytest -q tests/test_hybrid.py tests/test_hybrid_checkpoints.py -k 'bm25 or v0'
```

## 本版写作任务

- 描述：从“已有关键词基线和文档块”出发，让读者观察“查询词出现次数与文档长度影响排序”，再引入本版机制。
- 前置：01 v2、03 v3。
- 当前缺口：查询词出现次数与文档长度影响排序。
- 必要改变：使用成熟 BM25 实现建立排名基线。
- 验收及验证：固定分词策略；错误码及中文查询分别评测。
- 正文目标：本目录 `tutorial.md`；代码目标：`labs/hybrid/`；验证目标：`tests/hybrid/`。
- 代码角色：checkpoint，从外部输入出发建立首个可运行单元。
- 预计范围：一个版本；若实现需要多个独立机制，应先拆为多个写作任务。
- 提交策略：规划阶段不提交检查点；正文和实现通过复验后再保存版本 commit。

## 冻结与后续

完成后冻结“BM25”及对应验证结果。本版仍未处理“用户改写术语后没有共同关键词”；下一版推进“向量检索”。

编写前需补齐固定样例、精确文件名、输入输出、正常/非法/故障/边界检查和执行轨迹。遵循 [编写约定](../../../docs/authoring.md)，不把计划中的验收条件写成已通过结果。
