# ZWorkbench

ZWorkbench 是面向个人资深开发者的本地优先工作台。v1 在 **Codex-only 回退基线** 上出货：以 `codex_adapter` 为唯一执行器，由 CompositionOwner 维护唯一的 durable state；**DSH 主 Harness 仍属 `target/unknown`**（不在 v1 依赖闭包内，H7 标 deferred-until-demand，见 ADR 0009）。

v1 今天能交付的是**零凭证首跑**：一条命令在真实 repo 上跑一次 Codex 任务，由 CompositionOwner 记账并产出 owner-backed 的可回放证据，随即可在本地 loopback UI 查看 recorded view。

```bash
zworkbench run --prompt "解释这个函数的意图"
# 完成后 stdout 末尾打印 next_steps：
#   zworkbench ui --db <case_root>/state/composition.sqlite3
```

默认边界：未知工具、越界 workspace、未确认 approval、网络/凭证要求和不可关联事件都会 safe-stop。**真实写副作用（diff apply + commit）、Git push、真实 Provider 接入都不是默认入口的隐含能力**——它们须经 S0 host enforcement 出证（当前 0 行实现，未证明）后，作为显式、可记账、进 receipt 的授权动作开启（见 ADR 0009 与 `docs/prds/r3-real-usability-roadmap.md`）。

本地评审入口是只读 loopback 宿主：`zworkbench ui-host` 服务三个声明视图；`zworkbench ui-host --review` 显式开启本地评审标注模式（悬停语义名、脱敏反馈 token、深链接定位）。宿主只绑定 127.0.0.1，不打开 owner 数据库，中断即释放端口。

AI 侧「token → 代码」闭环（R1）：先在本地生成 UI Reference Manifest 产物 `zworkbench ui-build --store <dir>`（只读、不启动业务 Run、不改 owner 状态），再把浏览器复制的反馈 token 中的 `ref`/`ui_map`/`build` 交给 `zworkbench ui-ref resolve <ref> --store <dir> --ui-map <m> --build <b>` 定位代码声明；`ui-ref` 按精确 identity 只读查询，缺失返回 `manifest-missing`，不联网下载历史版本。

真实 Provider 的按需、路线外验证见 `docs/references/optional-real-provider-staging.md`（账户 owner 自持 Key、env+stdin 注入、secret 0 落盘）。

## 安装为正式构建产物

`zworkbench` 是 `pyproject.toml` 声明的 console 脚本（`zworkbench = "zworkbench.cli:main"`）。从源码构建并安装后即为 PATH 上的真实命令；UI 在源码布局与 wheel 布局下均能正确解析源码根（2026-10-06 修复其写死的 `src/zworkbench` 路径假设，否则 `pip install` 后 `ui-host`/`ui-build` 会 `FileNotFoundError`）。

```bash
python -m pip wheel . -w dist --no-build-isolation --no-deps   # 产出 dist/zworkbench-0.1.0-py3-none-any.whl
python -m pip install dist/zworkbench-0.1.0-py3-none-any.whl   # 安装后 zworkbench 进入当前 Python 的 bin
zworkbench ui-host        # 只读三视图，浏览器打开 stdout 打印的 base_url（/ 会 302 到 /home）
zworkbench ui --db <db>   # 连真实 owner DB 的可写 dogfood UI
```

注：`--no-build-isolation` 复用当前环境的 setuptools（缺失先 `pip install setuptools`）。纯 Python、`dependencies = []`，wheel 自包含、无需前端打包步骤（UI 为 server-rendered HTML，见 ADR 0003）。

从 [文档地图](docs/README.md) 开始：领域语言解释对象，方法论解释判定，架构解释责任边界，ADR 解释长期选择；外部 staging 的受控操作边界见 references。
