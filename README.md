# ZWorkbench

ZWorkbench 是面向个人资深开发者的本地优先工作台。v1 在 **Codex-only 回退基线** 上出货：以 `codex_adapter` 为唯一执行器，由 CompositionOwner 维护唯一的 durable state；**DSH 主 Harness 仍属 `target/unknown`**（不在 v1 依赖闭包内，H7 标 deferred-until-demand，见 ADR 0009）。

v1 今天能交付的是**零凭证首跑**：一条命令在真实 repo 上跑一次 Codex 任务，由 CompositionOwner 记账并产出 owner-backed 的可回放证据。

```bash
zworkbench run --prompt "解释这个函数的意图"
# 完成后 stdout 末尾打印 next_steps：
#   zworkbench snapshot --db <case_root>/state/composition.sqlite3
```

默认边界：未知工具、越界 workspace、未确认 approval、网络/凭证要求和不可关联事件都会 safe-stop。**真实写副作用（diff apply + commit）、Git push、真实 Provider 接入都不是默认入口的隐含能力**——它们须经 S0 host enforcement 出证（当前 0 行实现，未证明）后，作为显式、可记账、进 receipt 的授权动作开启（见 ADR 0009 与 `docs/designs/ps-solo-real-provider.md`）。

本地 UI 面由 Go 工作台承担（`app/`，默认 `:18080`；Electron 壳在 `app/electron`）。Python 侧的本地 UI 实现层已于 2026-10-24 整体退役——`ui-ref` / `ui-host` / `ui-build` / `ui` 四个子命令与 20 个 `ui_*.py` 模块（8206 行）全部下线，`tests/test_r1_layer2_retirement.py` 守卫其不回流。决策与 blast radius 见 [ADR 0018](docs/zj-adr/0018-retire-r1-ui-reference-system.md)。

真实 Provider 的按需、路线外验证见 `docs/references/optional-real-provider-staging.md`（账户 owner 自持 Key、env+stdin 注入、secret 0 落盘）。

## 安装为正式构建产物

`zworkbench` 是 `pyproject.toml` 声明的 console 脚本（`zworkbench = "zworkbench.cli:main"`）。从源码构建并安装后即为 PATH 上的真实命令。

```bash
python -m pip wheel . -w dist --no-build-isolation --no-deps   # 产出 dist/zworkbench-0.1.0-py3-none-any.whl
python -m pip install dist/zworkbench-0.1.0-py3-none-any.whl   # 安装后 zworkbench 进入当前 Python 的 bin
zworkbench --help        # 7 个子命令：run / write / snapshot / export / backup / restore / doctor
```

注：`--no-build-isolation` 复用当前环境的 setuptools（缺失先 `pip install setuptools`）。纯 Python、`dependencies = []`，wheel 自包含。

从 [文档地图](docs/README.md) 开始：领域语言解释对象，方法论解释判定，架构解释责任边界，ADR 解释长期选择；外部 staging 的受控操作边界见 references。
