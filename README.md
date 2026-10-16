# Agent Retrieval Lab

一个 Python 学习仓库，围绕技术知识助手研究代码检索、混合 RAG、文档导航和实时数据查询。

当前状态：9 个专题、37 个版本均已实现教程正文、可运行代码、测试和历史 checkpoint。全仓库验证为 `157 passed, 11 subtests`；真实 ONNX 检索测量另需首次下载模型。

从 [总路线](docs/roadmap.md) 了解依赖，再阅读 [环境准备](docs/environment.md) 和 [01 v0 教程](tutorials/01-evaluation/v0/tutorial.md)。

- [专题目录](tutorials/README.md)
- [编写与验收约定](docs/authoring.md)

每个专题独立维护 v0-vn，共享语料、评测契约和 Git 主线。版本号是学习检查点，不是包版本。混合检索使用锁定 revision 的 FastEmbed 模型；模型文件和评测产物存放在被忽略的 `artifacts/`。
