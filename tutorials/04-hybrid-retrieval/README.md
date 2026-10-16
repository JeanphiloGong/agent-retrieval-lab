# 混合检索

状态：verified，代码、固定语料和真实本地 ONNX 模型测量已实现。前置：01 v2、03 v3；模型下载需网络，模型文件保存在被忽略的 `artifacts/`。

实现目标：`labs/hybrid/retrieval.py`；历史检查点：`labs/hybrid/checkpoints/`；测试目标：`tests/test_hybrid.py`、`tests/test_hybrid_checkpoints.py`。

- [v0：BM25](v0/tutorial.md)（[计划](v0/plan.md)，重放 `uv run python -m labs.hybrid.checkpoints.v0_bm25`）
- [v1：向量检索](v1/tutorial.md)（[计划](v1/plan.md)，重放 `uv run python -m labs.hybrid.checkpoints.v1_vector`）
- [v2：结果融合](v2/tutorial.md)（[计划](v2/plan.md)，重放 `uv run python -m labs.hybrid.checkpoints.v2_fusion`）
- [v3：重排](v3/tutorial.md)（[计划](v3/plan.md)，重放 `uv run python -m labs.hybrid.checkpoints.v3_rerank`）
- [v4：消融评测](v4/tutorial.md)（[计划](v4/plan.md)，重放 `uv run python -m labs.hybrid.checkpoints.v4_benchmark --output artifacts/hybrid-heldout.json --split heldout`）

每版完成后保留可重放检查点，最后一版汇总该专题已讲解的完整实现与验证边界。参见 [编写约定](../../docs/authoring.md)。
