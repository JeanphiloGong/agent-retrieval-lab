# Agent Retrieval Lab

一个 Python 学习仓库，围绕技术知识助手研究代码检索、混合 RAG、文档导航和实时数据查询。

本仓库提供 9 个专题、37 个版本的教程、固定样例、验收测试和预写参考实现。你的实现区 `labs/` 从空白开始；参考代码通过测试不代表你的学习检查点已经完成。

从 [总路线](docs/roadmap.md) 了解依赖，再阅读 [环境准备](docs/environment.md) 和 [01 v0 教程](tutorials/01-evaluation/v0/tutorial.md)。

- [专题目录](tutorials/README.md)
- [手动构建流程](docs/learning-workflow.md)
- [你的学习进度](docs/progress.md)：初始为 0/37，按亲手实现的结果更新
- [编写与验收约定](docs/authoring.md)

```text
tutorials/       按专题、版本组织的教程
labs/            你逐版手写的代码，当前只有说明
tests/           你的代码可使用的验收测试
fixtures/        已提供的固定输入和标注
reference/labs/  预写实现与各版参考快照
reference/tests/ 参考快照和课程材料检查
```

每个专题独立维护 v0-vn，共享语料、评测契约和 Git 主线。版本号是学习检查点，不是包版本。混合检索使用锁定 revision 的 FastEmbed 模型；模型文件和评测产物存放在被忽略的 `artifacts/`。
