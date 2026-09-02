# W8 DeepSeek 首个 pinned plugin bundle：E1–E6 首轮结果

日期：2026-09-02
路线：`1-8-3`，acceptance/evaluation
证据：[首轮 evidence](../../evaluation/evidence/w8-deepseek-plugin-bundle-e1-e6-20260902/summary.json)
fixture：[bundle manifest](../../evaluation/fixtures/w8-deepseek-plugin-bundle/v1/manifest.json)

## 结论先行

首个请求的四插件组合没有通过 E1，结果为 `blocked`，不是“DeepSeek
插件生态无效”，也不是“前三个插件不能运行”。阻断是一个可定位的 ABI
边界：

| 请求成员 | 实际版本 | 实际 contract | E1 结论 |
|---|---:|---|---|
| `dsh-context` | `0.40.1` | `dsh.bundle` | 标准 bundle 成员 |
| `dsh-routing-suite` / `@dsh-external/dsh-super-injector` | `0.3.3` | `dsh.bundle` | 标准 bundle 成员 |
| `dsh-memoir` | `0.6.0` | `dsh.bundle` | 标准 bundle 成员 |
| `dsh-config-migrate` | `1.0.0` | `dsh.plugin.host/client` | **不是标准 bundle，fail-closed** |

因此当前不能把四件套称为一个“标准 plugin-composed bundle”，也不能用
前三件套的 profile dump、已有 Codex owner 证据或 README 自述替代四件套
的 E3–E6。

## 固定输入与隔离

- Core：DeepSeek Harness Alpha.4，commit
  `4e84901e6471b79ec0338099867ebb4606d12bb`，使用固定 archive SHA-256
  `c5acde3cc3ce7a01ab6daa6cc7fd1f7dc7b8a62d5e8bcc053caaf916f5ca00bb`。
- 插件 commits：
  `552bb9077f9ec5885bd37e35037c5e0de51d4c6d`、
  `f753bb1cd793a8e74b01d8fa5ad2c3d87a2e3c30`、
  `4416d50ee6d888f12677a81b36c4b4d5954c546a`、
  `24aa64188386181bdaf21f4b46fea02bddf77e71`。
- 输入只来自固定 source checkout、本地 tarball 和 case-local profile；不使用
  实时 registry。
- 使用 case-local `DSH_HOME`，loopback/fake Provider 边界，禁止真实 API key、
  生产数据、远端任务、Webhook、备份和外部副作用。
- profile 的 `pnpm-lock.yaml`、`dsh --version`、`--help` 和 `--dump-config`
  均被保存。此次 dump 成功加载 core、`dsh-super-injector`、`dsh-context`、
  `dsh-memoir`，没有把 `dsh-config-migrate` 静默当成 bundle layer。

## E1–E6 结果

| Gate | 首轮状态 | 实测/阻断原因 |
|---|---|---|
| E1 ABI 与版本封账 | **fail** | core 与四个 package 的 identity 均已记录；profile boot/dump 成功；但 `dsh-config-migrate` 没有 `dsh.bundle`，四件套不满足标准 bundle contract。 |
| E2 provenance 与安装安全 | **pass（限定范围）** | source identity、标准包 artifact hash、许可证、依赖、生命周期脚本和 network/credential 声明已记录；未执行 registry install、外网、真实凭据或外部副作用。此 pass 不等于插件运行时安全或可复现构建证明。 |
| E3 C2/C4 安全与副作用 | **blocked-by-E1** | 未将 Codex/owner evidence 迁移给不兼容的四件套；尚无 plugin-aware C2/C4 adapter。 |
| E4 C3/C5/C6 parity | **blocked-by-E1** | 未运行 scheduler/effect/failover/replay 的插件组合合同；不把 profile dump 当作 capability parity。 |
| E5 小团队 C7 与退出 | **blocked-by-E1** | 未对这个四件套执行完整 install/upgrade/backup/restore/diagnosis/uninstall/exit runbook；不得借用 Codex 真人计时。 |
| E6 组合增量收益 | **blocked-by-E1** | 还没有满足 E1–E5 的可比组合，不能计算非重复、可复现的相对 Codex 收益。 |

## 可标准装配的前三件套

runner 另外记录了 `core + dsh-context + dsh-routing-suite + dsh-memoir` 的
partial observation：固定 identity、三个 `dsh.bundle` 声明、profile lockfile
和 isolated `dump-config` 均通过。这只是“标准装配可观察”，不是 E1–E6
整体通过；该 partial bundle 的 E3–E6 标记为 `not-run`，因为目前没有
plugin-aware C2–C7 adapter，不能借用 ZWorkbench composition owner 的结果。

## 需要保留的工程判断

1. `dsh-config-migrate` 的能力仍有价值，但它应进入单独的
   `dynamic-plugin / outer-composed adapter` 轨道。它主要迁移 profile、插件、
   preset 和加密凭据，不能直接替代 composition owner 对 run/effect/event/
   replay state 的 backup/restore。
2. `dsh-routing-suite` checkout 中存在构建产生的工作树变化，`dsh-memoir`
   checkout 也不是干净工作树；runner 已记录这些变化。package hash + commit
   能封账输入，但尚不足以宣称 source-to-binary reproducible-build provenance。
3. Codex 仍保持当前主 Harness。这个结果只说明 DeepSeek 的第一种插件组合
   尚未过硬门，不能把“E1 fail”扩大解释为生态没有差异化价值。

## 下一步

先为 `dsh-config-migrate` 设计并单独验证一个显式 dynamic-plugin adapter：
定义加载入口、权限/网络/凭据边界、配置迁移与 owner backup/restore 的责任
切分；adapter 通过 E1/E2 后，才在同一隔离环境重开 E3–E6。若 adapter 的
新增状态、权限、维护、升级和退出成本超过它带来的非重复收益，则停止这条
组合路线，继续 Codex + 单一 composition owner。

本报告不构成第三方安全、合规、许可证或商业保证。
