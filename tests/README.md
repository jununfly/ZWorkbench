# tests/ — 全量回归门禁

## 规范命令（repo 根目录执行）

```bash
env PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
```

**必须从 repo 根目录跑**：`tests/` 里 10 个重环境模块 import 根目录的
`evaluation/`、`scripts/`（靠 `-m` 把 cwd 放进 `sys.path`）。换目录跑会得到
一批 `ModuleNotFoundError` 伪影。

## UI 真引擎门（ADR 0014）

- `tests/browser.py` 驱动本机 Chrome（ADR 0004 证据通道）的真引擎测试
  **默认 skip**（`browser()` 抛 `SkipTest`），理由文本随 skip 呈现。
- 需要真引擎证据时显式开启：`env PYTHONPATH=src ZW_UI_ENGINE=1 python -m unittest
  discover -s tests -p "test_ui_<某文件>.py" -v`（建议单文件跑，不要全量串行）。
- `chrome_available()` 语义不变：只回答"本机是否有引擎"。

## 当前基线（2026-10-14）

- 1261 tests / ~190s / skipped=110 / **failures=4**。
- 4 个 FAIL 是既有问题（与门无关，同名单独无门跑也挂）：
  `test_ui_deep_link` / `test_ui_overlay` / `test_ui_reference_runtime_skill` /
  `test_ui_reference_skill_installation`。处置走 roadmap 1-4-4。

## 已知环境坑

- macOS 自带 BSD grep 不认 BRE 交替 `\|`，排查日志用 `grep -E`。
- 无头环境下 Electron/Chrome 需要 `--no-sandbox` 类绕行（见 desktop/README.md）。
