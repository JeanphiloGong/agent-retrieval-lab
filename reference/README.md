# 参考实现与重放

`labs/` 保存预先编写的完整参考实现和历史版本，`tests/` 检查参考快照与课程材料。它们用于卡住时对照、检查输出和重放旧版；不代表你已经实现这些版本。你的代码写在仓库根目录的 `labs/`。

从仓库根目录显式选择参考代码：

```bash
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests reference/tests
PYTHONPATH=reference uv run python -P -m labs.verify_course
PYTHONPATH=reference uv run python -P -m labs.evaluation.checkpoints.v0.validate \
  fixtures/evaluation/questions.json fixtures/evaluation/sources.json
```

参考区内部仍使用 `labs.*` 包名，所以可以与学习区使用同一份验收测试。命令前的 `PYTHONPATH=reference` 只影响本次进程，`-P` 去掉当前目录的优先导入，pytest 的 `--import-mode=importlib` 避免测试收集时重新加入该目录。即使以后你创建了 `labs/__init__.py`，这组命令仍明确选择参考实现。

不要全局 `export PYTHONPATH=reference`。验证你自己的代码时使用教程中的普通 `uv run ...` 命令。演示与 benchmark 都从仓库根目录运行，共用根目录的 `fixtures/` 与 `artifacts/`。

参考区的 `checkpoints/` 是预写答案快照。你自己的检查点是亲手实现并验证之后保存的 Git commit，不需要复制这些目录。此前的 Git 历史仍保留，未重写或删除。
