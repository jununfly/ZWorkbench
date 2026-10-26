# tests/ — 全量回归门禁

## 规范命令（repo 根目录执行）

```bash
env PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
```

**必须从 repo 根目录跑**：`tests/` 里 10 个重环境模块 import 根目录的
`evaluation/`、`scripts/`（靠 `-m` 把 cwd 放进 `sys.path`）。换目录跑会得到
一批 `ModuleNotFoundError` 伪影。

## UI 真引擎门 — 已退役（2026-10-26）

- `tests/browser.py`（ADR 0004 CDP 通道）与 `ZW_UI_ENGINE` 门控（ADR 0014）**均已删除**。
  它唯一的消费者是 R1 层二（ADR 0018）删掉的 43 个 `test_ui_*.py`；此后模块零消费者、自身
  无测试覆盖，按「有消费者的能力才配留在产品树里」退役，而不是继续悬空。
- 判据（可复核）：`git grep` 含隐藏目录零代码命中；`.github/` 只有 `web-build.yml`，零 CI 命中。
- **方法论没丢**：4 条 CDP 顺序规则（视口模拟须在导航后 / 只有 `http://127.0.0.1` 是安全上下文 /
  调试目标须筛选不得取 `targets[0]` / 夹具只经上下文管理器暴露）与「引擎缺席即 `unknown`」
  的口径，全部沉淀在 ADR 0004 的「实现附注」。
- 若将来重新需要真引擎证据：承载面是 **Go / Electron 侧**（chromedp 或 Playwright-CDP 驱动
  `127.0.0.1:18080` 的 SPA），不要回头复刻这个 Python 客户端——它服务的 Python 宿主已随
  ADR 0015 的 Go 全 pivot 消失。

## 当前基线（2026-10-26，ADR 0018 层二收口 + `tests/browser.py` 退役后）

- **502 tests / ~45s / skipped=1 / OK（exit 0）**。
- 相对上一基线（1261 tests / ~188s / skipped=110）：R1 层二删除了 43 个 `test_ui_*.py`，
  skipped 从 110 降到 1 也是同一原因——被 skip 的一大批正是真引擎/浏览器门用例。剩下的这 1 个
  skip 与浏览器无关，是 `test_worker_orphan_detection.py` 的 `ps enumeration unavailable on
  this host`（本机 `ps` 被环境拒绝）。
- 删 `tests/browser.py`（336 行）**不改变用例数**：它是测试支撑模块、不是测试用例，且零消费者。
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
