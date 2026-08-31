# W7 Codex C7 一手来源与 provenance ledger

状态：`evidence captured` · 仅记录可复核来源，不构成法律意见或候选采用签核

本记录服务于固定候选 Codex Harness `0.139.0` 的 C7 运维、许可证与退出审计。
来源优先级为 Codex 官方仓库、官方 GitHub release/API 和本机已安装 artifact；
所有“未知”都保留为未知，不用推断填补。

## 1. 固定身份

| 项目 | 证据 | 结论 |
|---|---|---|
| canonical repository | [openai/codex](https://github.com/openai/codex) | 官方仓库；本轮不把仓库活跃度当作运行或维护能力证明 |
| release tag | [`rust-v0.139.0`](https://github.com/openai/codex/releases/tag/rust-v0.139.0) | release 页面存在 |
| tag resolution | `git ls-remote`: `rust-v0.139.0` → `7cadca4c6e8c821fa7b75b50006b1806ccebdf1c`；peeled commit → `a7dff904308535e965aee87680c1fc5ef1d19eec` | 候选源码身份固定到 peeled commit |
| fixed commit | [a7dff904…](https://github.com/openai/codex/commit/a7dff904308535e965aee87680c1fc5ef1d19eec) | C7 引用的源码 revision |
| installed CLI | `/opt/homebrew/bin/codex` → `codex-cli 0.139.0` | 本机入口和版本检查通过 |
| app-server entrypoint | `codex app-server --help` | `stdio://` 默认入口和 `generate-json-schema` 等子命令可见；帮助文本标记 app-server 为 experimental |

## 2. 许可证和 package metadata

- 官方固定 commit 的 [LICENSE](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/LICENSE)
  是 Apache License 2.0。它是代码仓库许可证声明的依据。
- 官方固定 commit 的 [`codex-cli/package.json`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/codex-cli/package.json)
  声明：`license: Apache-2.0`、`version: 0.0.0-dev`、`node >=16`，package manager
  为 pnpm `10.33.0`（带完整 pnpm integrity suffix）。
- 本机候选 manifest
  [`w7-codex-candidate-manifest.json`](../w7-codex-candidate-manifest.json)
  记录已安装 npm package `0.139.0`、Darwin arm64 platform package
  `0.139.0-darwin-arm64`、wrapper 与 vendor binary 的 SHA-256；C7 fixture 会逐个
  重算这些 digest。

这里可以确认的是“固定源码仓库 LICENSE 和本机 package metadata 均声明
Apache-2.0”。以下事项不能仅凭该 LICENSE 或 package.json 放行：

- 所有 transitive dependency、platform package、嵌入组件和发布包内 NOTICE 的
  完整归属与再分发义务；
- 商业使用、商标、服务端/API 使用条款以及组织内部合规要求；
- 本机二进制是否由固定 commit 以可复现方式构建。

因此 C7 的 `commercial_boundary` 和 `redistribution_notice_review` 保持
`unknown`，需要在采用前由适当的许可证/合规审查补齐。

## 3. source-to-binary provenance

官方 [commit API](https://api.github.com/repos/openai/codex/commits/a7dff904308535e965aee87680c1fc5ef1d19eec)
对该 commit 返回的 signature 字段为：`verified: false`、`reason: unsigned`。
这只记录 GitHub 当前看到的提交签名状态，不单独证明代码内容不可信，也不等于
发布 artifact 的构建证明。

本轮保守记录如下：

| 问题 | 当前值 | 为什么不能升级为 pass |
|---|---|---|
| release/tag → commit | `pass` | tag peeled commit 已由 `git ls-remote` 固定 |
| local artifact digest | `pass` | wrapper、npm package、platform package、vendor binary 均可重算 |
| source package version | `0.0.0-dev` | 来自固定 commit 的源码 package.json |
| installed package version | `0.139.0` | 来自本机 release package |
| source package → installed binary | `unknown` | `0.0.0-dev` 与 `0.139.0` 的发布/构建映射未由 attestation 证明 |
| reproducible build | `unknown` | 没有本轮可验证的 build recipe、source digest、artifact attestation 和独立重建结果 |
| commit signature | `unsigned` | 官方 API 的事实字段；不被解释为 build provenance |

所以候选 manifest 中的 `source_to_binary_verified=false` 和
`binary_build_provenance=unknown` 是有意保留的审计结论。C7 允许继续测量 release-level
运维行为，但不能宣称“该二进制可复现地来自该源码 commit”。

## 4. 运维与退出相关来源边界

本轮直接观察到的候选入口是本机 `codex --version` 与
`codex app-server --help`。安装/升级命令只写入 case-local runbook，不执行真实的
全局安装、升级、回滚或网络下载。C7 fixture 的 backup/restore、export/re-import/delete
只操作每个 case 的隔离目录。

因此以下不是官方原生能力结论，而是本轮 composition audit 的边界：

- durable schedule、幂等、恢复、Provider routing、canonical replay ledger 和
  approval owner 由外部薄 adapter 持有；C3/C4/C5/C6 的证据必须继续携带
  `pass-with-composition` 或 `approval-boundary-unknown` 标签。
- C7 的维护服务计数按“候选运行时 + 一个外部 composition owner”计算为 `2`；
  host OS、Node runtime、case-local fake Provider 不作为常驻维护服务。
- case-local export 可以独立读取、删除并达到零残留；这证明退出 fixture 的机器
  合同，不证明真实用户数据、Provider 账户、组织 retention 或生产部署已迁移/删除。

## 5. 访问记录

- 访问日期：`2026-08-31`（Asia/Shanghai 环境；来源内容可能随官方站点变化）。
- C7 runner 应保存本地运行 summary、case evidence 和本 manifest digest；重新审计
  时必须重新确认 URL、tag resolution、package/binary digest 与许可证清单。

