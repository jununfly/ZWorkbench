# W7 Codex C7 许可证与发布 provenance 审计

状态：`release-artifact-pass / legal-and-independent-rebuild-open`  ·
审计日期：`2026-08-31`（Asia/Shanghai）  · 候选：Codex `0.139.0`

本文只记录可复核的发布包和本机安装观察，不构成法律意见，也不替代组织的许可证
或商业合规签核。审计目标是把 C7 的“source-to-binary provenance”拆成可独立判断
的 artifact provenance、installed-bytes binding、许可证/NOTICE 和商业边界。

## 1. 结论摘要

| Gate | 当前判定 | 证据边界 |
|---|---|---|
| npm root package provenance | `pass-at-release-level` | npm SLSA provenance 将 package subject 绑定到 Codex release tag/commit |
| Darwin arm64 platform provenance | `pass-at-release-level` | platform package 有同一 release workflow 的 SLSA provenance，且包含 vendor binary |
| registry tarball → 本机安装内容 | `pass-for-this-npm-install` | 重新下载的 official registry tarball integrity 与 registry metadata 一致；解包内容与本机包核对通过 |
| 独立 attestation 验签 | `pass-via-npm-cli` | 隔离临时项目运行 `npm audit signatures`，root/platform 两个包的 registry signatures 与 attestations 均验证通过；证据：[`npm-audit-signatures.txt`](../../../evaluation/evidence/w7-codex-c7/npm-audit-signatures.txt) |
| 独立 reproducible rebuild | `unknown` | 未从源码独立构建并比对二进制 |
| LICENSE 声明 | `pass-as-declared` | Codex 源码 LICENSE、root package 和 platform package metadata 均为 Apache-2.0 |
| 完整 NOTICE / 嵌入组件归属 | `unknown` | 发布包没有 LICENSE/NOTICE 文件；vendor 中还有 ripgrep、zsh 等组件，尚未完成归属清单 |
| 商业 / API / 商标边界 | `unknown` | Apache-2.0 不覆盖服务条款、API 使用、商标和组织内部合规边界 |

因此，路线图中的 provenance 阻断从“没有发布证明”收窄为“npm release artifact
有 provenance 且 npm CLI 验签通过，但独立重建和法律/再分发审查仍开放”。C7/G7 总体仍不能
签核。

## 2. 固定身份与 tarball digest

固定源码身份：

- 仓库：[openai/codex](https://github.com/openai/codex)
- release tag：[rust-v0.139.0](https://github.com/openai/codex/releases/tag/rust-v0.139.0)
- peeled commit：`a7dff904308535e965aee87680c1fc5ef1d19eec`
- 本机 CLI：`codex-cli 0.139.0`
- 本机平台：Darwin arm64

| 包 | registry tarball | npm `dist.integrity` | 本轮测得 SHA-512（base64） | attestation subject（SHA-512 hex） |
|---|---|---|---|---|
| `@openai/codex@0.139.0` | [`codex-0.139.0.tgz`](https://registry.npmjs.org/@openai/codex/-/codex-0.139.0.tgz) | `sha512-wr2fRE+fzW0CjEbfFsLh1ftarVEcw0CMLWS7QyA0nyOz5qacQPVq3cq2+/U7oEbwm1TOqoi0Fm1nxniB5FkpmA==` | 同左 | `c2bd9f444f9fcd6d028c46df16c2e1d5fb5aad511cc3408c2d64bb4320349f23b3e6a69c40f56addcab6fbf53ba046f09b54ceaa88b4166d67c67881e4592998` |
| `@openai/codex@0.139.0-darwin-arm64` | [`codex-0.139.0-darwin-arm64.tgz`](https://registry.npmjs.org/@openai/codex/-/codex-0.139.0-darwin-arm64.tgz) | `sha512-o+0ZKWwgDFMMLO7rwinzO0PQsgK+Vme1pMN2GeAxsX29ZgGZcyPICfpJbeGSUO1mb2a36Skjx6nfdRnxMY0r7w==` | 同左 | `a3ed19296c200c530c2ceeebc229f33b43d0b202be5667b5a4c37619e031b17dbd6601997323c809fa496de19250ed666f66b7e92923c7a9df7519f1318d2bef` |

attestation endpoint：

- root：[npm attestation](https://registry.npmjs.org/-/npm/v1/attestations/@openai%2fcodex@0.139.0)
- platform：[npm attestation](https://registry.npmjs.org/-/npm/v1/attestations/@openai%2fcodex@0.139.0-darwin-arm64)

两份 attestation 都包含 `https://slsa.dev/provenance/v1` predicate，解析出的关键
字段一致：

```text
buildType: https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1
workflow.repository: https://github.com/openai/codex
workflow.path: .github/workflows/rust-release.yml
workflow.ref: refs/tags/rust-v0.139.0
resolved dependency commit: a7dff904308535e965aee87680c1fc5ef1d19eec
builder: https://github.com/actions/runner/github-hosted
invocation: https://github.com/openai/codex/actions/runs/27229104633/attempts/1
```

## 3. 本机安装绑定

本机观察到的 artifact：

| 路径 | SHA-256 | 观察 |
|---|---|---|
| `/opt/homebrew/bin/codex` | `d3be844c45c4fd89392536e56e1010963f94785592596b50cd0c45bb8a341406` | npm wrapper |
| `/opt/homebrew/lib/node_modules/@openai/codex/package.json` | `c6e68915c8c7c2c5169ccb6d326789850a9a540875cbc3b04dc3df4d775e7412` | root package `0.139.0` |
| `/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/package.json` | `e690d7640a91f7045f621e18aa493e23a9b390e239834988eb6096676d21ca3a` | platform package `0.139.0-darwin-arm64` |
| `.../vendor/aarch64-apple-darwin/bin/codex` | `c6ede9ef9b672ef5a99384e507bec5476cbb60934c03f19cbd0355d9fdd83915` | Mach-O arm64 vendor binary |

重新从 `registry.npmjs.org` 获取两个 tarball 后：

- tarball 的 SHA-512 实测值与 `dist.integrity`、attestation subject 一致；
- root 解包目录与本机 root 包内容一致，差异仅为本机安装产生的 `node_modules` 目录；
- Darwin arm64 platform 解包目录与本机 platform package `diff -rq` 无差异；
- platform tarball 的 6 个文件包含 vendor Codex binary、`rg` 和 zsh runtime resource。

这证明的是“本机这次 npm 安装的 bytes 与 registry package 对上”，不是另一渠道、另一
机器或独立重建的证明。attestation 已被读取、base64 解码并检查关键字段，且 npm CLI
在隔离安装中报告 root/platform 两个包的 registry signatures 和 attestations 均验证
通过；本轮没有使用 standalone Sigstore policy 工具，也没有独立重建。

## 4. 许可证与 NOTICE 盘点

| 对象 | 观察 | 判定 |
|---|---|---|
| Codex 源码仓库 | 固定 commit 的 `LICENSE` 为 Apache License 2.0 | 声明通过 |
| root npm package | `license: Apache-2.0`；无 runtime `dependencies`；只有平台 optional dependency | package metadata 通过 |
| Darwin arm64 platform package | `license: Apache-2.0`；无 package dependencies；`files: [vendor]` | package metadata 通过 |
| npm package 文件 | root/platform 安装目录均未发现 `LICENSE*`、`NOTICE*`、`THIRD-PARTY*` | 再分发材料不完整，保持 unknown |
| vendor `rg` | 本机 `ripgrep 15.1.0`，启用 PCRE2 | 需要单独归属/许可证核对 |
| vendor zsh | 本机 `zsh 5.9.0.3-test` | 需要单独归属/许可证核对 |
| Rust/Cargo 依赖树 | 源码 workspace 声明 Apache-2.0，但包含大量 transitive crates | 尚未生成完整 SPDX/NOTICE 清单 |

下一步合规签核需要从固定发布包/源码锁定文件生成完整组件清单，并逐项确认许可证、
版权声明、NOTICE 再分发义务、商标限制、OpenAI 服务/API 条款和组织商业使用边界。
此项不应由 agent 以“root package 是 Apache-2.0”代签。

## 5. 后续关闭条件

在 C7/G7 重新评估前，仍需完成：

1. 若组织要求 standalone Sigstore policy verification，由责任人再确认其验证规则；
   npm CLI 的 registry signature/provenance verification 已通过；
2. 若要求“可复现构建”，从固定 commit 按 release workflow 重建并比较目标平台
   artifact；否则把目标明确降级为 `release-artifact provenance`；
3. 完成 vendor/ transitive dependency 的许可证与 NOTICE ledger；
4. 完成商业、API、商标和再分发边界签核；
5. 将真实账户、Provider 数据、远端 backup/retention 和删除责任加入退出清单。

本审计不会改变 C4 native approval `unknown`，也不会替代 C7 真实单人 backup/restore
和故障定位 stopwatch。
