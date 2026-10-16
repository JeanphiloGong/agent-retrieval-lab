# 环境准备

需要 Python 3.12+、uv 和 Git。以下命令在仓库根目录执行：

```bash
uv sync --locked
uv run python --version
```

仓库包含可运行的检索系统。BM25、PDF、AST、SQLite 和测试依赖由锁文件管理；混合检索额外使用 FastEmbed 的两个固定 revision。首次运行真实模型测量时需要网络下载约百 MB 级模型到 `artifacts/models/`，之后可离线重放已下载模型。01、02、03、06、07、08、09 的基础测试不需要模型下载。

数据只使用自建或许可明确的样例。生成索引、缓存、评测报告放在被忽略的 `artifacts/`；人工样例和标注保存在 `fixtures/`。密钥放在不提交的 `.env`，需要时显式使用 `uv run --env-file .env ...`。

运行全套验证：

```bash
uv run --locked pytest -q
uv run python -m labs.verify_course
uv run python -m labs.hybrid.benchmark --output artifacts/hybrid-heldout.json
uv run python -m labs.operations.benchmark --output artifacts/operations.json
```
