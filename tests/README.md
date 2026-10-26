# tests/ — 全量回归门禁

## 规范命令（repo 根目录执行）

```bash
env PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
```

**必须从 repo 根目录跑**：`tests/` 里 10 个重环境模块 import 根目录的
`evaluation/`、`scripts/`（靠 `-m` 把 cwd 放进 `sys.path`）。换目录跑会得到
一批 `ModuleNotFoundError` 伪影。

## UI 真引擎门（ADR 0014）— 当前无消费者

- `tests/browser.py` 驱动本机 Chrome（ADR 0004 证据通道），仍保留为受认可的真引擎
  证据通道；但 R1 层二（ADR 0018，2026-10-24）删除了全部 43 个 `test_ui_*.py` 后，
  **仓库内已无任何测试引用它**（`ZW_UI_ENGINE` 门控只剩代码本身）。
- 若将来重新需要真引擎证据，直接复用该模块；若确认永不再用，应连同 ADR 0004 一起
  立项退役，而不是让一个零消费者的通道长期悬空。
- `chrome_available()` 语义不变：只回答"本机是否有引擎"。

## 当前基线（2026-10-26，ADR 0018 层二收口后）

- **502 tests / ~45s / skipped=1 / OK（exit 0）**。
- 相对上一基线（1261 tests / ~188s / skipped=110）：R1 层二删除了 43 个 `test_ui_*.py`，
  skipped 从 110 降到 1 是同一原因——被 skip 的一大批正是真引擎/浏览器门用例。
- 变更纪律：删测试必须与删实现同一批次推进，且删除后**非 ui 套件基线不得变化**
  （本次剥离前后均为 484 个非 ui 用例全绿）。

## 历史基线（2026-10-14，1-4-4 收口后）

- 1261 tests / ~188s / skipped=110 / **OK（exit 0）**——门禁首次全绿。
- 历史 4 个 FAIL 已在 1-4-4 处置：`skill_installation`（R1/R2 指向退役的
  `docs/prds/`，改指 `docs/designs/pf-ui-reference-*` 新实体）；
  `deep_link`/`runtime_skill`（side-panel 3 个 ref 声明未渲染＝真回归，产品侧
  修复；variant-canvas/journal 属 F8/F9 条件渲染，测试改按 `?variant=` 路由
  断言）；`overlay`（剥离启发式裸 `<aside>`/`<script>` 误删业务标记，改用
  `data-ui-overlay="review"` 与 `src="/static/review.js"` 判别）。
  → 上述 4 个模块随 ADR 0018 层二整体删除。

## 已知环境坑

- macOS 自带 BSD grep 不认 BRE 交替 `\|`，排查日志用 `grep -E`。
- 无头环境下 Electron/Chrome 需要 `--no-sandbox` 类绕行（见 desktop/README.md）。
