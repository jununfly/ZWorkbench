---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.desktop.node.dependency.deviation
---

# ADR 0013：桌面壳引入 Node/Electron —— 零第三方依赖（C32）的有界偏离

> 状态 `accepted`：Human 于 2026-10-13 在路线图 Q1（`1-3-1`）明确选择「接受引入
> Node/Electron 依赖，登记为 tracked deviation」。

## Context

ZWorkbench 的核心是**零第三方依赖**的纯 Python（`pyproject.toml` 的
`dependencies = []`，对比项 C32）。这条约束不是洁癖：它保证 wheel 自包含、
安装不触发外部生态、durable 状态不被第三方库的版本漂移影响。

路线图 `1-1` 把客户端做成 Electron 桌面应用，必然引入 Node/Electron。若不显式登记，
会出现两类无声退化：

1. 有人为了"统一"把 Electron 相关依赖写进 `pyproject.toml`，核心不再是纯 Python；
2. 反过来，有人为了守住零依赖而拒绝桌面壳，产品拿不到桌面形态。

本 ADR 的作用是把偏离**划出边界**并让它**可机械验证**：偏离存在、范围固定、
不进 Python 运行时、且边界由测试守住。

## Decision

### 1. 偏离是有界的：Node/Electron 只存在于 `desktop/`

- Node/Electron 依赖**只**出现在 `desktop/package.json` 的 `devDependencies`，
  不出现在任何 Python 打包元数据里。
- `pyproject.toml` 的 `[project].dependencies` **必须保持 `[]`**。这是硬性边界，
  由 `tests/test_zero_dependency_guard.py` 静态断言守住。
- `desktop/` 是**可选外壳**：删掉整个目录，核心 CLI（`run`/`write`/`push`/`ui-host`）
  功能与测试不受影响。

### 2. 依赖性质是构建/分发期，不是 Python 运行时

`electron` 是 `desktop/` 的 devDependency：它只在"把桌面壳跑起来或打包分发"时需要。
核心运行时路径（`zworkbench ui-host`、`zworkbench run`）**不经过 Node**，
桌面壳也只是 spawn 既有 CLI 并把窗口指向它的 loopback 地址（ADR 0003）。

### 3. 边界由测试守住，不靠约定

`tests/test_zero_dependency_guard.py` 断言三件事：

1. `pyproject.toml` 的 `[project].dependencies` 为空列表；
2. `desktop/package.json` 里 `electron` 只出现在 `devDependencies`，不在 `dependencies`；
3. 仓库根不存在 `package.json` —— Node 生态的入口只能在 `desktop/`。

前两条分别守住"核心不被污染"与"Node 依赖是构建期而非运行时"，第三条守住
"偏离不向仓库根蔓延"。任何一项被破坏，测试即失败——偏离不能靠人记得边界。

该测试用手工解析 `[project].dependencies` 而非 `tomllib`：项目仍声明
`requires-python = ">=3.9"`，而 `tomllib` 自 3.11 才有，直接 import 会让守卫
在受支持的解释器上跑不起来。守卫自身不能成为版本瓶颈。

### 4. 与 C32 的关系：C32 的口径收窄为「Python 运行时零依赖」

对比项 C32 原表述为「ZW 无第三方依赖」。引入桌面壳后，准确表述是：
**ZW 的 Python 运行时零第三方依赖；桌面壳（`desktop/`）另有一层构建期 Node 依赖。**
本 ADR 是该收窄的唯一权威出处。

## Consequences

- `desktop/` 是仓库里唯一允许出现 Node 生态文件（`package.json`、
  `package-lock.json`、`node_modules/`）的目录，且 `node_modules/` 已 gitignore。
- 打包分发（`1-1-3`）会用 `electron-builder` 把 Python 运行时与 Electron 一起封进
  安装包；这不改变本 ADR 的边界——封进安装包的是**已有的纯 Python 核心**，
  不是新增 Python 依赖。
- 若将来要撤回偏离，删除 `desktop/` 即可，核心零改动。撤回成本是本 ADR 设计为
  "外壳而非内核"的直接收益。
- 本 ADR 不解决：macOS 签名/公证、Windows 构建、自动更新——属 `1-1-3` 及后续。

## 未解决（不在本 ADR 范围）

- 桌面壳是否长期保留，取决于 `1-2`（ES 常驻 tab）的成效；若废弃，本 ADR 由新 ADR
  `supersedes` 并记录撤回。
- Electron 版本升级策略与供应链校验（如锁定版本、校验镜像来源）未在此定义。
