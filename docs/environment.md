# 环境准备

需要 Python 3.12+、uv 和 Git。以下命令在仓库根目录执行：

```bash
uv sync --locked
uv run python --version
```

`labs/` 留给你逐版实现；已经写好的系统在 `reference/labs/`。BM25、PDF、AST、SQLite 和测试依赖由锁文件管理；混合检索额外使用 FastEmbed 的两个固定 revision。首次运行真实模型测量时需要网络下载约百 MB 级模型到 `artifacts/models/`，之后可离线重放已下载模型。01、02、03、06、07、08、09 的基础测试不需要模型下载。

数据只使用自建或许可明确的样例。生成索引、缓存、评测报告放在被忽略的 `artifacts/`；人工样例和标注保存在 `fixtures/`。密钥放在不提交的 `.env`，需要时显式使用 `uv run --env-file .env ...`。

准备环境后阅读 [01 v0](../tutorials/01-evaluation/v0/tutorial.md)，按步骤创建文件。完成该版后验证你自己的代码：

```bash
uv run --locked python -m pytest -q tests/evaluation/test_validate.py
```

空白学习区不能通过完整测试。先按各版正文运行当前检查；后续专题的测试要等相关模块实现后再运行。

如需确认已提供的参考材料可运行，请显式重放参考代码：

```bash
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests reference/tests
PYTHONPATH=reference uv run python -P -m labs.verify_course
```

下面两项是可选的真实模型测量，可能下载模型；它们验证参考系统，不计为你的完成进度：

```bash
PYTHONPATH=reference uv run python -P -m labs.hybrid.benchmark --output artifacts/hybrid-heldout.json
PYTHONPATH=reference uv run python -P -m labs.operations.benchmark --output artifacts/operations.json
```

命令中的 `PYTHONPATH` 只为这次参考重放设置，不要全局导出。更多说明见 [参考区](../reference/README.md)。
