# W7 Codex C7 一手来源与 provenance ledger

状态：`evidence captured / release provenance narrowed` · 仅记录可复核来源，不构成法律意见或候选采用签核

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
Apache-2.0”。另外，本机 package 树的 root 和 Darwin arm64 platform package 都没有
随包分发的 LICENSE/NOTICE 文件；README 只引用源码仓库中的 `LICENSE`。以下事项不能
仅凭该 LICENSE 或 package.json 放行：

- 所有 transitive dependency、platform package、嵌入组件和发布包内 NOTICE 的
  完整归属与再分发义务；
- 商业使用、商标、服务端/API 使用条款以及组织内部合规要求；
- 本机二进制是否由固定 commit 以可复现方式构建。

因此 C7 的 `commercial_boundary` 和 `redistribution_notice_review` 保持
`unknown`，需要在采用前由适当的许可证/合规审查补齐。

### 2.1 npm registry artifact 与发布 provenance

本轮在 2026-08-31 通过 npm registry 重新观察固定版本的 metadata、tarball 和
attestation；可复核摘要见
[`w7-codex-c7-license-provenance-audit.md`](./w7-codex-c7-license-provenance-audit.md)。

| artifact | registry integrity / attestation subject | provenance 绑定 | 本机绑定 |
|---|---|---|---|
| `@openai/codex@0.139.0` root | `sha512-wr2fRE+fzW0CjEbfFsLh1ftarVEcw0CMLWS7QyA0nyOz5qacQPVq3cq2+/U7oEbwm1TOqoi0Fm1nxniB5FkpmA==` / `c2bd9f44…92998` | SLSA v1；`.github/workflows/rust-release.yml`；`rust-v0.139.0`；`a7dff904…` | 官方 registry tarball hash 与 metadata 一致；本机 root 内容仅多已安装的 `node_modules` |
| `@openai/codex@0.139.0-darwin-arm64` platform | `sha512-o+0ZKWwgDFMMLO7rwinzO0PQsgK+Vme1pMN2GeAxsX29ZgGZcyPICfpJbeGSUO1mb2a36Skjx6nfdRnxMY0r7w==` / `a3ed1929…d2bef` | 同一 workflow、tag 和 commit；GitHub-hosted builder；run `27229104633/attempts/1` | 解包官方 tarball 与本机 platform package `diff -rq` 无差异；其中包含 vendor Codex binary |

这把原先“没有 attestation”的判断收窄为 `pass-at-npm-slsa-release-level`：发布
artifact 的 provenance 已将 npm package subject 绑定到固定源码 tag/commit，本机
安装内容也绑定到对应 tarball；隔离临时项目的 `npm audit signatures` 进一步报告两个
包的 registry signatures 和 attestations 均验证通过。尚未独立重建，未检查另一安装
渠道的等价性；因此不写成“可复现构建已证明”。

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
| npm root package → source release | `pass-at-release-level` | npm SLSA attestation 的 resolved dependency 为 `git+https://github.com/openai/codex@refs/tags/rust-v0.139.0`，digest 为 `a7dff904…` |
| platform package → source release | `pass-at-release-level` | Darwin arm64 npm package 有同一 release workflow 的 SLSA attestation，subject 包含 vendor binary |
| registry package → local installed bytes | `pass-for-this-npm-install` | 官方 registry tarball integrity 与 attestation subject 一致；本机 root/platform 内容核对通过 |
| reproducible rebuild | `unknown` | 未在本轮独立重建源码和二进制，不能把发布 attestation 等同于独立可复现构建 |
| independent attestation verification | `pass-via-npm-cli` | 隔离 Codex 安装运行 `npm audit signatures`，2/2 registry signatures 与 2/2 attestations 验证通过；未使用 standalone policy tool |
| commit signature | `unsigned` | 官方 API 的事实字段；不被解释为 build provenance |

所以候选 manifest 现在记录 `binary_build_provenance=pass-at-npm-slsa-release-level`
和 `source_to_binary_verified=true`，并明确限定为该 npm release 与本机 npm 安装；
独立重建、完整依赖许可证/NOTICE 和商业边界仍不因 provenance attestation
而自动通过。C7 仍可继续测量 release-level 运维行为，但不能宣称“所有发布渠道和
独立可复现构建均已证明”。

## 4. 运维与退出相关来源边界

本轮直接观察到的候选入口是本机 `codex --version` 与
`codex app-server --help`。fixture 本身不执行真实的全局安装、升级、回滚或网络下载；
另有 Human 在临时 C7 npm prefix 中真实完成 `0.138.0 → 0.139.0 → 0.138.0`，并将
版本/help 输出归档为 [`upgrade-rollback.log`](../../../evaluation/evidence/w7-codex-c7/upgrade-rollback.log)。
C7 fixture 的 backup/restore、export/re-import/delete 只操作每个 case 的隔离目录。

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
