# 学习实现的验收测试

这些测试导入你在根目录 `labs/` 手写的代码，不会自动选择参考实现。按各版正文选择可运行的测试；空白学习区运行全部测试会因缺少模块失败。

第一版完成后运行：

```bash
uv run python -m pytest -q tests/evaluation/test_validate.py
```

部分专题测试在收集阶段就导入最终 API，要等该专题完成后再运行；早期版本先使用正文中的行为检查。参考快照专用测试放在 `reference/tests/`，无需在你的学习代码里创建 `checkpoints/`。

全部专题实现后，`uv run python -m pytest -q` 默认只收集本目录。参考测试必须显式指定路径。

全套参考重放命令和导入隔离说明见 [参考区](../reference/README.md)。
