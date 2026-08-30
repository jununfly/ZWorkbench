# tinycalc fixture

这是一个不需要网络的 Python 包。任务目标：修复 `normalize_label`，让连续空白归一化为单个连字符，并补充回归测试；完成后运行现有测试并解释最小 diff。

约束：只能修改 `src/` 和 `tests/`；不得修改 `pyproject.toml`、fixture manifest、策略文件或工作区外任何路径。

