# 混合检索

资料状态：参考代码、固定语料和本地 ONNX 模型回放已准备；这不代表你已完成实现。前置：01 v2、03 v3；模型下载需网络，模型文件保存在被忽略的 `artifacts/`。

你逐版编写 `labs/hybrid/retrieval.py`、`models.py` 和 `benchmark.py`；预写答案位于 `reference/labs/hybrid/`，各版回放入口位于其 `checkpoints/`。这些入口复用完整参考模块，不是逐版独立源码。先读[手动构建流程](../../docs/learning-workflow.md)；参考回放不能记为学习完成。

- [v0：BM25](v0/tutorial.md)（[计划](v0/plan.md)）
- [v1：向量检索](v1/tutorial.md)（[计划](v1/plan.md)）
- [v2：结果融合](v2/tutorial.md)（[计划](v2/plan.md)）
- [v3：重排](v3/tutorial.md)（[计划](v3/plan.md)）
- [v4：消融评测](v4/tutorial.md)（[计划](v4/plan.md)）

每版从自己的上一版代码继续，只加入当版能力，检查后提交自己的 Git 检查点。现有 `tests/test_hybrid.py` 导入最终 API，`reference/tests/test_hybrid_checkpoints.py` 验证参考快照；早期版本先运行本版示例，不必提前写完未来 API。参见[编写约定](../../docs/authoring.md)。
