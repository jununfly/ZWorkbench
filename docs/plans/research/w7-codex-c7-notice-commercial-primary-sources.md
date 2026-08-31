# W7 Codex C7 NOTICE / 商业边界一手来源核查

状态：`independent-primary-source-review / signoff-open`
核查日期：`2026-08-31`（Asia/Shanghai）
固定候选：Codex release `rust-v0.139.0`，peeled commit
`a7dff904308535e965aee87680c1fc5ef1d19eec`

本文件是对 ZWorkbench 当前 Codex C7 NOTICE、许可证、发布 provenance 与商业边界阻断的独立取证记录。它只记录官方源码、官方 package metadata、官方发布/attestation、官方文档或一手法律文本能支持的事实；不构成法律意见、法律签核、再分发授权或技术推荐。

## 1. 范围与判定词

固定范围如下：

- Codex `rust-v0.139.0` / commit `a7dff904308535e965aee87680c1fc5ef1d19eec`；
- npm root package、Darwin arm64 platform package 及其 vendor 内容；
- Codex 源码 `LICENSE` / `NOTICE`；
- vendor 与 Cargo transitive 依赖；
- OpenAI 与第三方商标/名称边界；
- Codex/OpenAI API、账户、服务条款与商业使用边界。

判定词的含义：

| 判定 | 含义 |
|---|---|
| `verified` | 一手来源直接支持，且本轮观察与来源相符。 |
| `partial` | 只确认了声明、清单或 release-level 绑定，不能推出完整法律/再分发结论。 |
| `unknown` | 在固定范围内没有足够一手证据，不能用推断或扫描结果补齐。 |
| `not-a-legal-signoff` | 工程事实已记录，但仍需适当责任人作法律/合规判断。 |

## 2. 固定身份

| 事实 | findings | 可复核一手来源 |
|---|---|---|
| 官方仓库 | 仓库为 `openai/codex`。 | [github.com/openai/codex](https://github.com/openai/codex) |
| release tag | `rust-v0.139.0` 存在；tag 的 peeled commit 为 `a7dff904308535e965aee87680c1fc5ef1d19eec`。本轮以 peeled commit 作为源码身份，而不是仅以可移动 tag 名称作为身份。 | [release page](https://github.com/openai/codex/releases/tag/rust-v0.139.0)；[fixed commit](https://github.com/openai/codex/commit/a7dff904308535e965aee87680c1fc5ef1d19eec) |
| 源码 workspace 版本 | 固定 commit 的 `codex-rs/Cargo.toml` workspace 版本为 `0.139.0`，license 字段为 `Apache-2.0`；`codex-cli/package.json` 的开发源码版本仍为 `0.0.0-dev`，由发布脚本在打包时覆盖。 | [`codex-rs/Cargo.toml`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/codex-rs/Cargo.toml)；[`codex-cli/package.json`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/codex-cli/package.json)；[`build_npm_package.py`](https://github.com/openai/codex/blob/a7dff904308535e965aee87680c1fc5ef1d19eec/codex-cli/scripts/build_npm_package.py) |

固定来源文件摘要：

```text
LICENSE SHA-256:         d17f227e4df5da1600391338865ce0f3055211760a36688f816941d58232d8dc
NOTICE SHA-256:          9d71575ecfd9a843fc1677b0efb08053c6ba9fd686a0de1a6f5382fd3c220915
codex-cli/package.json:  abd643cbd0b02d94818345bd363f2d81a4e1c09dcace90aa4448fcfd022aba6d
codex-rs/Cargo.lock:     4315b596d910df46b6091580476f9df6a388b9d90874e45544a93346ccf24e37
```

摘要是本轮对上述固定 commit 文件的本地重算值，不替代 URL/path/commit 身份。

## 3. Codex 源码 LICENSE / NOTICE

### 3.1 LICENSE

固定 commit 的 [`LICENSE`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/LICENSE) 是 Apache License 2.0。该文本直接支持以下事实：

- 第 2 条授予 copyright license；
- 第 3 条授予 patent license；
- 第 4 条允许以 source 或 object 形式复制、修改和分发，但要求随分发提供许可证、对修改文件作显著修改声明，并保留相应版权、专利、商标和 attribution notices；如果分发包含 NOTICE，则须保留其中相关 attribution；
- 第 6 条明确 Apache License 本身不授予商标、服务标记或产品名称使用权，只允许合理、惯常地描述来源以及复制 NOTICE 内容。

当前结论：`Codex_source_license = verified-as-declared`。这确认了 Codex 源码声明及其文本条件；它不自动确认 vendor、Cargo transitive 依赖、npm 发布物材料、OpenAI 服务或商标边界。

### 3.2 NOTICE

固定 commit 的 [`NOTICE`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/NOTICE) 内容为：

```text
OpenAI Codex
Copyright 2025 OpenAI

This project includes code derived from [Ratatui](https://github.com/ratatui/ratatui), licensed under the MIT license.
Copyright (c) 2016-2022 Florian Dehau
Copyright (c) 2023-2025 The Ratatui Developers
```

当前结论：`Codex_source_notice = verified`；`Ratatui_source_attribution = verified`。这只证明固定源码仓库提供了该归属文本，不证明该文本已经随每一种 npm/platform/binary 分发物正确交付。

## 4. npm root package

### 4.1 官方 metadata

官方 registry 的 [`@openai/codex@0.139.0 metadata`](https://registry.npmjs.org/@openai%2fcodex/0.139.0) 记录：

| 字段 | 观察 |
|---|---|
| `name` / `version` | `@openai/codex` / `0.139.0` |
| `license` | `Apache-2.0` |
| `repository` | `git+https://github.com/openai/codex.git`，directory `codex-cli` |
| `engines` | `node >=16` |
| optional platform aliases | 6 个平台别名；Darwin arm64 alias 指向 `@openai/codex@0.139.0-darwin-arm64` |
| release metadata | `dist.fileCount = 3`，`dist.unpackedSize = 9718` |

官方 root tarball：[`codex-0.139.0.tgz`](https://registry.npmjs.org/@openai/codex/-/codex-0.139.0.tgz)。本轮对该官方 tarball 的解包观察为 3 个文件：

```text
package/bin/codex.js
package/package.json
package/README.md
```

观察到 root tarball 不含 `LICENSE` 或 `NOTICE` 文件。root tarball SHA-256 为
`52ff8eab5eaefd248dadd608c734089015619357e9fab1356c5b751e97a78079`；其 SHA-512 与
registry metadata 的 `dist.integrity` 相符：

```text
sha512-wr2fRE+fzW0CjEbfFsLh1ftarVEcw0CMLWS7QyA0nyOz5qacQPVq3cq2+/U7oEbwm1TOqoi0Fm1nxniB5FkpmA==
```

当前结论：`root_package_license_metadata = verified-as-declared`，`root_package_notice_file_observed = absent`。后者不是“违反许可证”的法律判断；`root_package_notice_redistribution_sufficiency = unknown`，因为是否需要、如何交付源码及依赖归属材料不能只由 `license` 字段或三文件 tarball 推出。

### 4.2 官方构建脚本边界

固定 commit 的 [`codex-cli/scripts/build_npm_package.py`](https://github.com/openai/codex/blob/a7dff904308535e965aee87680c1fc5ef1d19eec/codex-cli/scripts/build_npm_package.py) 负责发布 npm package。其发布逻辑会写入版本、复制 `bin/codex.js` 和根 README，并生成 package metadata；在该脚本可复核的复制清单中没有根 `LICENSE` / `NOTICE` 的复制步骤。

当前结论：`npm_build_script_notice_copy = not-observed`。这只表示固定脚本中未观察到复制步骤，不替代对所有发布 job、包管理器重写和最终 artifact 的核对；最终 root tarball 文件清单以本节官方 tarball 观察为准。

## 5. Darwin arm64 platform package

### 5.1 官方 metadata 与本机已安装内容

官方 registry 的 [`@openai/codex@0.139.0-darwin-arm64 metadata`](https://registry.npmjs.org/@openai%2fcodex/0.139.0-darwin-arm64) 记录：

- `license = Apache-2.0`；
- `os = darwin`；
- `cpu = arm64`；
- `dist.fileCount = 6`；
- `dist.unpackedSize = 216960582`；
- `files = null`；
- package build metadata 将 `files` 设置为 `vendor`。

官方 platform tarball URL：[`codex-0.139.0-darwin-arm64.tgz`](https://registry.npmjs.org/@openai/codex/-/codex-0.139.0-darwin-arm64.tgz)。

本机已安装 package path：

```text
/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64
```

本机 package 树观察到：

```text
README.md
package.json
vendor/aarch64-apple-darwin/bin/codex
vendor/aarch64-apple-darwin/codex-package.json
vendor/aarch64-apple-darwin/codex-path/rg
vendor/aarch64-apple-darwin/codex-resources/zsh/bin/zsh
```

在该本机 platform package 目录未发现 package-level `LICENSE`、`NOTICE`、`COPYING`、`THIRD-PARTY` 或 `COPYRIGHT` 文件。vendor manifest 内容为：

```json
{
  "layoutVersion": 1,
  "version": "0.139.0",
  "target": "aarch64-apple-darwin",
  "variant": "codex",
  "entrypoint": "bin/codex",
  "resourcesDir": "codex-resources",
  "pathDir": "codex-path"
}
```

本机文件摘要：

```text
vendor/aarch64-apple-darwin/bin/codex SHA-256: c6ede9ef9b672ef5a99384e507bec5476cbb60934c03f19cbd0355d9fdd83915
vendor/aarch64-apple-darwin/codex-path/rg SHA-256: 4fdf1d8365af224bc70e3c1490d8461d859c37cc70e739a11e987af0215f3e94
vendor/aarch64-apple-darwin/codex-resources/zsh/bin/zsh SHA-256: db6fe1a78eaceaff3b0f0cde25fc25afe466d61b0bf76b4ebe35812e4bc8dd71
```

当前结论：`platform_package_metadata_license = verified-as-declared`；`platform_local_notice_bundle = absent-observed`。本轮未把不完整的 platform tarball 传输/解包过程当作最终内容清单，因此 `platform_tarball_complete_file_audit = unknown`；`platform_vendor_notice_redistribution_sufficiency = unknown`。

## 6. source-to-npm provenance

官方 npm attestation endpoints：

- [root attestation](https://registry.npmjs.org/-/npm/v1/attestations/@openai%2fcodex@0.139.0)
- [Darwin arm64 platform attestation](https://registry.npmjs.org/-/npm/v1/attestations/@openai%2fcodex@0.139.0-darwin-arm64)

两份 endpoint 都返回 npm publish attestation 和 SLSA provenance attestation。解码出的共同关键字段为：

```text
buildType:                 https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1
workflow.repository:       https://github.com/openai/codex
workflow.path:             .github/workflows/rust-release.yml
workflow.ref:              refs/tags/rust-v0.139.0
resolved dependency commit: a7dff904308535e965aee87680c1fc5ef1d19eec
builder:                   https://github.com/actions/runner/github-hosted
invocation:                https://github.com/openai/codex/actions/runs/27229104633/attempts/1
```

attestation subject digest：

```text
root:     c2bd9f444f9fcd6d028c46df16c2e1d5fb5aad511cc3408c2d64bb4320349f23b3e6a69c40f56addcab6fbf53ba046f09b54ceaa88b4166d67c67881e4592998
platform: a3ed19296c200c530c2ceeebc229f33b43d0b202be5667b5a4c37619e031b17dbd6601997323c809fa496de19250ed666f66b7e92923c7a9df7519f1318d2bef
```

当前结论：`npm_release_provenance = verified-at-release-level`。它支持 registry package subject 与 Codex release workflow/ref/commit 的绑定；它不等于独立可复现重建、每个 vendor/transitive 组件的许可证清权，也不等于所有下载渠道都等价。`independent_reproducible_rebuild = unknown`。

固定 commit 的官方 [GitHub commit API](https://api.github.com/repos/openai/codex/commits/a7dff904308535e965aee87680c1fc5ef1d19eec) 返回 signature 字段 `verified: false`、`reason: unsigned`。这是该 commit 当前在 GitHub API 中的签名事实；它不单独证明源码不可信，也不抵消或扩大 npm SLSA release attestation 的证明范围。`commit_signature = unsigned`，`source_to_binary_independent_verification = unknown`。

## 7. vendor 组件

### 7.1 ripgrep

Codex 固定 commit 的 [`scripts/codex_package/rg`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/scripts/codex_package/rg) 对 Darwin arm64 条目记录：

```text
version:      15.1.0
archive URL:  https://github.com/BurntSushi/ripgrep/releases/download/15.1.0/ripgrep-15.1.0-aarch64-apple-darwin.tar.gz
archive SHA:  378e973289176ca0c6054054ee7f631a065874a352bf43f0fa60ef079b6ba715
member:       ripgrep-15.1.0-aarch64-apple-darwin/rg
```

上游 tag `15.1.0` 的 peeled commit 为 `af60c2de9d85e7f3d81c78601669468cf02dabab`：[commit](https://github.com/BurntSushi/ripgrep/commit/af60c2de9d85e7f3d81c78601669468cf02dabab)。上游官方许可证文件为 [`COPYING`](https://raw.githubusercontent.com/BurntSushi/ripgrep/af60c2de9d85e7f3d81c78601669468cf02dabab/COPYING)、[`LICENSE-MIT`](https://raw.githubusercontent.com/BurntSushi/ripgrep/af60c2de9d85e7f3d81c78601669468cf02dabab/LICENSE-MIT) 和 [`UNLICENSE`](https://raw.githubusercontent.com/BurntSushi/ripgrep/af60c2de9d85e7f3d81c78601669468cf02dabab/UNLICENSE)。其 Cargo manifest 的 license expression 为 `Unlicense OR MIT`；官方 `COPYING` 是 dual-license 文本。

本机 `/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/codex-path/rg --version` 观察到 `ripgrep 15.1.0 (rev af60c2de9d)`，并报告 `PCRE2 10.45 is available`。这支持版本和功能观察，不支持“Codex platform package 已交付 ripgrep 所需许可证文本”的结论。

当前结论：`ripgrep_source_license = verified`；`ripgrep_archive_identity = verified-from-Codex-manifest`；`ripgrep_binary_redistribution_notice = unknown`。Codex manifest 记录的是上游 archive digest，不是本机 extracted binary digest 与其源码的独立重建证明。

### 7.2 PCRE2

上游 PCRE2 固定 tag `pcre2-10.45` 的 commit 为 `aa8a3e5ba20749965953a0bde69343b172f175b4`：[tag tree](https://github.com/PCRE2Project/pcre2/tree/pcre2-10.45)。官方 [`LICENCE.md`](https://raw.githubusercontent.com/PCRE2Project/pcre2/pcre2-10.45/LICENCE.md) 声明 SPDX 为 `BSD-3-Clause WITH PCRE2-exception`，并要求二进制再分发时在文档或随附材料中重现版权、条件和免责声明；文本还包含其 exception 的具体条件。

当前 `rg --version` 只证明 bundled `rg` 报告 PCRE2 10.45 可用；exact static/dynamic linkage、实际链接对象、以及 Codex package 是否随附 PCRE2 所需文本均未由本轮一手证据核实。

当前结论：`pcre2_license_text = verified`；`pcre2_exact_binary_linkage = unknown`；`pcre2_notice_delivery = unknown`。

### 7.3 zsh

固定 commit 的 [`scripts/codex_package/codex-zsh`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/scripts/codex_package/codex-zsh) 中，Darwin arm64 条目指向：

```text
https://github.com/openai/codex/releases/download/rust-v0.134.0-alpha.3/codex-zsh-aarch64-apple-darwin.tar.gz
archive SHA-256: 49dec9832379688c9090666694a3449502ac5eb4d76b9ffde1d0999cd088205
```

这是固定 `0.139.0` 源码 manifest 中实际出现的旧 Codex release URL。另一方面，固定 commit 的 [`.github/workflows/rust-release-zsh.yml`](https://github.com/openai/codex/blob/a7dff904308535e965aee87680c1fc5ef1d19eec/.github/workflows/rust-release-zsh.yml) 使用 [`.github/scripts/build-zsh-release-artifact.sh`](https://github.com/openai/codex/blob/a7dff904308535e965aee87680c1fc5ef1d19eec/.github/scripts/build-zsh-release-artifact.sh)，其中 `ZSH_COMMIT=77045ef899e53b9598bebc5a41db93a548a40ca6`，从 zsh upstream clone、checkout 该 commit、应用 Codex 的 [`zsh-exec-wrapper.patch`](https://github.com/openai/codex/blob/a7dff904308535e965aee87680c1fc5ef1d19eec/codex-rs/shell-escalation/patches/zsh-exec-wrapper.patch)，再 stage `codex-zsh/bin/zsh`。

zsh upstream 的固定源码：[commit tree](https://github.com/zsh-users/zsh/tree/77045ef899e53b9598bebc5a41db93a548a40ca6)、[`LICENCE`](https://raw.githubusercontent.com/zsh-users/zsh/77045ef899e53b9598bebc5a41db93a548a40ca6/LICENCE)、[`README`](https://raw.githubusercontent.com/zsh-users/zsh/77045ef899e53b9598bebc5a41db93a548a40ca6/README)。该 `LICENCE` 说明 zsh distribution license，并明确指出部分 shell functions 为 GPL，包含这些 functions 的 binary distributor 需要相应处理，且应查看 shell functions 的具体 copyright 信息。

当前结论：

- `zsh_source_license_text = verified`；
- `zsh_codex_0.139.0_artifact_same-release_provenance = unknown`：manifest 指向 `rust-v0.134.0-alpha.3`，而当前 workflow 又指向 zsh source commit，二者的精确发布关系未由固定范围内的一手材料闭合；
- `zsh_binary_contents_and_gpl_function_inclusion = unknown`；
- `zsh_notice_delivery = unknown`。

### 7.4 Ratatui

Codex 固定源码 [`NOTICE`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/NOTICE) 明确称项目包含 derived from Ratatui 的代码，并给出 MIT 与版权归属。固定 [`codex-rs/Cargo.lock`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/codex-rs/Cargo.lock) 将 Ratatui 锁定为 git source：

```text
https://github.com/nornagon/ratatui?rev=9b2ad1298408c45918ee9f8241a6f95498cdbed2
```

对应上游 commit：[9b2ad129…](https://github.com/nornagon/ratatui/commit/9b2ad1298408c45918ee9f8241a6f95498cdbed2)，其 [`LICENSE`](https://raw.githubusercontent.com/nornagon/ratatui/9b2ad1298408c45918ee9f8241a6f95498cdbed2/LICENSE) 为 MIT。

当前结论：`Ratatui_source_attribution = verified`；`Ratatui_published_package_notice_location = unknown`。源码 NOTICE 的存在不能证明 root/platform npm 包已携带或以其他合法方式交付该归属。

## 8. Cargo transitive 依赖

固定 commit 的 [`codex-rs/Cargo.lock`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/codex-rs/Cargo.lock) 共 1332 个 package entry：

| 类别 | 数量 | 目前能证明的事情 |
|---|---:|---|
| workspace package | 123 | 固定 lock 中存在这些 Codex workspace package。 |
| crates.io registry package | 1197 | 固定 lock 中存在这些 registry source/version。 |
| git package | 12 | 固定 lock 中存在这些 git source/revision。 |

固定 lock 中可直接识别的 git source 包括：

| 包/族 | 固定 source/revision |
|---|---|
| `crossterm` | [`nornagon/crossterm@87db8bfa6dc99427fd3b071681b07fc31c6ce995`](https://github.com/nornagon/crossterm/commit/87db8bfa6dc99427fd3b071681b07fc31c6ce995) |
| `libwebrtc`, `livekit-protocol`, `livekit-runtime`, `webrtc-sys`, `webrtc-sys-build` | [`juberti-oai/rust-sdks@e2d1d1d230c6fc9df171ccb181423f957bb3c0`](https://github.com/juberti-oai/rust-sdks/commit/e2d1d1d230c6fc9df171ccb181423f957bb3c0) |
| `nucleo`, `nucleo-matcher` | [`helix-editor/nucleo@4253de9faabb4e5c6d81d946a5e35a90f87347ee`](https://github.com/helix-editor/nucleo/commit/4253de9faabb4e5c6d81d946a5e35a90f87347ee) |
| `ratatui` | [`nornagon/ratatui@9b2ad1298408c45918ee9f8241a6f95498cdbed2`](https://github.com/nornagon/ratatui/commit/9b2ad1298408c45918ee9f8241a6f95498cdbed2) |
| `runfiles` | [`rules_rust@b56cbaa8465e74127f1ea216f813cd377295ad81`](https://github.com/dzbarsky/rules_rust/commit/b56cbaa8465e74127f1ea216f813cd377295ad81) |
| `tokio-tungstenite` | [`openai-oss-forks/tokio-tungstenite@132f5b39c862e3a970f731d709608b3e6276d5f6`](https://github.com/openai-oss-forks/tokio-tungstenite/commit/132f5b39c862e3a970f731d709608b3e6276d5f6) |
| `tungstenite` | [`openai-oss-forks/tungstenite-rs@9200079d3b54a1ff51072e24d81fd354f085156f`](https://github.com/openai-oss-forks/tungstenite-rs/commit/9200079d3b54a1ff51072e24d81fd354f085156f) |

Cargo lock 能提供可复现的 package/source/version inventory，但不等于逐包许可证、版权、NOTICE、exception 或实际二进制包含关系清单。固定范围内没有完成 1197 个 registry package 与 12 个 git package 的逐项法律记录抽取。

当前结论：`Cargo_lock_inventory = verified`；`transitive_license_clearance = unknown`；`complete_notice_inventory = unknown`。不能把 workspace 的 `Apache-2.0` 字段外推给所有 transitive 依赖。

## 9. OpenAI 名称、商标与服务边界

### 9.1 OpenAI 品牌

官方 [OpenAI Brand](https://openai.com/brand/) 页面说明 OpenAI name、logo、ChatGPT、GPT 及其他 OpenAI marks 属于 OpenAI，并要求：仅在与 OpenAI services 直接相关时使用；不得暗示 endorsement/partnership；不得将 logo 作为自己品牌/商标的一部分；不得将 GPT brand 用于 app/product/developer/company name；授权若适用具有非排他、不可转让、可撤销等限制。

当前结论：`OpenAI_GPT_ChatGPT_brand_guidance = verified`。本轮固定的一手品牌页面没有给出足以单独确认 “Codex” 专属商标状态的注册/授权文本，因此 `OpenAI_Codex_specific_trademark_status = unknown`；不能以 Codex 源码 Apache license 推出 OpenAI/Codex 商标授权。

### 9.2 第三方名称/商标

固定 Codex [`LICENSE`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/LICENSE) 的 Apache 条款第 6 条明确不授予商标、服务标记或产品名称使用权。固定源码 [`NOTICE`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/NOTICE)、Cargo.lock 中的 Ratatui source，以及 vendor manifest 中的 ripgrep、PCRE2、zsh 名称，能够证明这些名称与归属被用于描述组件；它们不能单独证明 ZWorkbench 获得任何第三方商标许可。

本轮核对到的上游许可证文本是 Ratatui [`LICENSE`](https://raw.githubusercontent.com/nornagon/ratatui/9b2ad1298408c45918ee9f8241a6f95498cdbed2/LICENSE)、ripgrep [`COPYING`](https://raw.githubusercontent.com/BurntSushi/ripgrep/af60c2de9d85e7f3d81c78601669468cf02dabab/COPYING)、PCRE2 [`LICENCE.md`](https://raw.githubusercontent.com/PCRE2Project/pcre2/pcre2-10.45/LICENCE.md) 和 zsh [`LICENCE`](https://raw.githubusercontent.com/zsh-users/zsh/77045ef899e53b9598bebc5a41db93a548a40ca6/LICENCE)；本轮没有在这些固定文本中建立 ZWorkbench 产品命名、logo 或营销使用的专属授权记录。因此 `third_party_trademark_status = unknown`，只保留事实性组件归属描述，不作商标放行判断。

### 9.3 API / developer / business service

官方 [OpenAI Business Terms](https://openai.com/policies/business-terms/) 页面显示该条款适用于 API、ChatGPT Enterprise/Business 及相关 enterprise/developer services；页面显示更新于 `2025-12-01`、生效于 `2026-01-01`。其中：

- Section 2.2 直接提供访问/使用服务并允许将 API 集成到 customer application、向最终用户开放 customer application；
- Section 3.1 禁止账户凭证共享及账户 resale/rental；
- Section 3.3 列出违法/违反政策、侵害第三方权利、reverse engineering、竞争性 AI model development（含条款例外）、超范围 extraction、API key sale/transfer、绕过 rate limits/controls 等限制；
- Section 3.4 规定 third-party services 受其各自条款约束；
- Section 4.1 规定 customer 对 input 保有相应权利并按法律拥有 output，OpenAI 转让其可能拥有的相应权利；Section 4.3 仍由 customer 对 input 权利和 output 评估/使用负责；
- Section 9.1 不把 service IP ownership 普遍转移给 customer，只授予条款明确的服务使用权；
- Section 10 限制未经事先书面许可公开使用对方名称/logo或发表公开声明；
- Section 11.3 规定终止后的效果和删除事项；Section 16.11/16.12 涉及 sanctions/export controls 与 supported countries/regions。

这些是页面所载条款事实，不是对 ZWorkbench 具体账户、地区、数据或产品模式的适用性意见。当前结论：`API_service_integration_text = verified`；`API_commercial_boundary_for_this_project = unknown-until-mode-specific-review`。

### 9.4 个人服务条款

官方 [OpenAI Terms of Use](https://openai.com/policies/terms-of-use/) 页面显示适用于 ChatGPT、DALL·E 等 personal services，并明确说明 API、Enterprise 等 business/developer services 适用 Business Terms。页面禁止或限制 modify/copy/rent/sell/distribute service、reverse engineering、自动化提取服务数据、绕过 rate limits/protections、侵害第三方权利以及使用 outputs 开发 competing models（按条款例外）。页面也说明 output ownership 受适用法律约束，服务 as-is，且用户需遵守 trade/export controls。

当前结论：不能把个人 ChatGPT 条款当作 Codex 源码再分发许可，也不能把个人账户自动当作对外 SaaS/API 集成授权。`personal_service_to_public_workbench_boundary = unknown-for-specific-use-case`，在未明确账户和产品模式前不放行推断。

### 9.5 Usage Policy

官方 [OpenAI Usage Policies](https://openai.com/policies/usage-policies/) 页面给出服务使用的行为边界，包括不得用于非法、有害或滥用活动、侵害第三方权利、恶意网络活动、规避安全措施等；页面同时说明政策会随服务和风险变化而更新。

当前结论：`OpenAI_usage_policy_source = verified`；`ZWorkbench_policy_compliance_for_specific_workflows = unknown`。本节只建立必须逐场景检查的官方政策来源，不对某个具体工作流作合规签核。

### 9.6 Codex authentication / API usage

官方 [Codex authentication documentation](https://developers.openai.com/codex/auth/) 说明 Codex CLI 支持 Sign in with ChatGPT 订阅路径和 Sign in with API key usage-based 路径；认证方式会影响管理控制和 data-handling policy；API key 使用按 API organization retention/data-sharing settings 处理并按标准 API rates 计费；API key 适合本地及 programmatic/CI/CD workflow，但不应暴露在不受信任的 public environment，且部分 ChatGPT workspace/cloud features 不可用。

该文档支持“认证路径不同、条款/数据/账户边界不能混为一谈”的工程事实；它没有替 ZWorkbench 确定组织合同、地区、数据处理协议、终端用户责任或商业许可。`account_region_data_processing_and_DPA = unknown`。

## 10. 逐项 findings 矩阵

| 主题 | 当前 findings | 判定 | 一手依据 |
|---|---|---|---|
| Codex 源码许可证 | 固定 commit LICENSE 为 Apache-2.0，文本含 source/object 分发条件，且不授予商标权。 | `verified-as-declared` | 固定 commit [`LICENSE`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/LICENSE) |
| Codex 源码 NOTICE | NOTICE 明确包含 OpenAI copyright 与 Ratatui MIT attribution。 | `verified` | 固定 commit [`NOTICE`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/NOTICE) |
| root npm metadata | `@openai/codex@0.139.0` metadata 声明 Apache-2.0。 | `verified-as-declared` | [npm metadata](https://registry.npmjs.org/@openai%2fcodex/0.139.0) |
| root npm artifact | 官方 tarball 解包为 3 文件，未观察到 LICENSE/NOTICE。 | `observed` | [official root tarball](https://registry.npmjs.org/@openai/codex/-/codex-0.139.0.tgz) |
| root NOTICE 再分发是否充分 | 不能凭 package metadata、README 或三文件 tarball 作法律判断。 | `unknown` | Apache [`LICENSE`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/LICENSE)；root [metadata](https://registry.npmjs.org/@openai%2fcodex/0.139.0) |
| Darwin arm64 metadata | platform package 声明 Apache-2.0、darwin/arm64、vendor 文件布局。 | `verified-as-declared` | [platform metadata](https://registry.npmjs.org/@openai%2fcodex/0.139.0-darwin-arm64) |
| platform NOTICE bundle | 本机 package 未观察到 package-level LICENSE/NOTICE/COPYING/THIRD-PARTY；完整官方 platform tarball 文件审计未闭合。 | `unknown` | [platform metadata](https://registry.npmjs.org/@openai%2fcodex/0.139.0-darwin-arm64)；固定 commit [`codex_package`](https://github.com/openai/codex/tree/a7dff904308535e965aee87680c1fc5ef1d19eec/scripts/codex_package) |
| ripgrep | Codex manifest 固定版本/archive；上游声明 `Unlicense OR MIT` 并提供 COPYING/许可证文本。 | `partial` | Codex [`rg manifest`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/scripts/codex_package/rg)；ripgrep [`COPYING`](https://raw.githubusercontent.com/BurntSushi/ripgrep/af60c2de9d85e7f3d81c78601669468cf02dabab/COPYING) |
| PCRE2 | `rg` 报告 PCRE2 10.45；上游许可证为 BSD-3-Clause with exception。 | `partial` | [PCRE2 LICENCE.md](https://raw.githubusercontent.com/PCRE2Project/pcre2/pcre2-10.45/LICENCE.md)；本机 `rg --version` 观察 |
| zsh | Codex source workflow 固定 upstream commit 与 patch，但 package manifest Darwin 条目指向较旧 Codex release artifact；zsh LICENCE 另提示 GPL shell functions。 | `partial` / 关键项 `unknown` | Codex [`codex-zsh`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/scripts/codex_package/codex-zsh)；[`rust-release-zsh.yml`](https://github.com/openai/codex/blob/a7dff904308535e965aee87680c1fc5ef1d19eec/.github/workflows/rust-release-zsh.yml)；zsh [`LICENCE`](https://raw.githubusercontent.com/zsh-users/zsh/77045ef899e53b9598bebc5a41db93a548a40ca6/LICENCE) |
| Ratatui | 源码 NOTICE 与 Cargo.lock source 均可核实；发布包中归属文本位置未知。 | `partial` | Codex [`NOTICE`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/NOTICE)；[`Cargo.lock`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/codex-rs/Cargo.lock) |
| Cargo transitive | lock inventory 为 1332 entries，但未逐包抽取 license/copyright/NOTICE/exception。 | `unknown` | 固定 commit [`Cargo.lock`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/codex-rs/Cargo.lock) |
| release provenance | npm root/platform attestation 将发布 subject 绑定到 `rust-v0.139.0` workflow 与固定 commit。 | `verified-at-release-level` | [root attestation](https://registry.npmjs.org/-/npm/v1/attestations/@openai%2fcodex@0.139.0)；[platform attestation](https://registry.npmjs.org/-/npm/v1/attestations/@openai%2fcodex@0.139.0-darwin-arm64) |
| independent rebuild | 未从固定源码独立重建并比较二进制。 | `unknown` | 固定 commit [release workflow](https://github.com/openai/codex/blob/a7dff904308535e965aee87680c1fc5ef1d19eec/.github/workflows/rust-release.yml) |
| OpenAI/GPT/ChatGPT marks | 官方品牌指南给出所有权、关联性、不得暗示背书等规则。 | `verified-guidance` | [OpenAI Brand](https://openai.com/brand/) |
| Codex 专属商标状态 | 固定范围内未找到足以确认 Codex 专属商标注册/授权状态的一手文本。 | `unknown` | [OpenAI Brand](https://openai.com/brand/)；Codex 官方仓库 [README](https://github.com/openai/codex) |
| 第三方名称/商标 | 组件名称和 attribution 可作事实性识别；本轮没有建立 ZWorkbench 使用第三方名称/logo/营销的专属授权。 | `unknown` | Codex [`LICENSE`](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/LICENSE)；Ratatui [`LICENSE`](https://raw.githubusercontent.com/nornagon/ratatui/9b2ad1298408c45918ee9f8241a6f95498cdbed2/LICENSE)；ripgrep [`COPYING`](https://raw.githubusercontent.com/BurntSushi/ripgrep/af60c2de9d85e7f3d81c78601669468cf02dabab/COPYING) |
| API integration | Business Terms 载明 API 可集成到 customer application 并向最终用户开放，同时规定账户、API key、使用限制、第三方服务和名称/logo约束。 | `verified-text / mode-dependent` | [Business Terms](https://openai.com/policies/business-terms/)，Sections 2.2, 3.1–3.4, 4.1, 9.1, 10 |
| 个人服务路径 | Terms of Use 将 personal services 与 API/business services 区分，并限制复制/分发服务等行为。 | `verified-text / mode-dependent` | [Terms of Use](https://openai.com/policies/terms-of-use/) |
| 使用政策 | 官方 Usage Policies 给出非法、有害、滥用、恶意网络活动和规避安全措施等行为边界。 | `verified-policy / workflow-dependent` | [Usage Policies](https://openai.com/policies/usage-policies/) |
| ZWorkbench 具体商业模式 | 尚未固定账户类型、地区、输入数据、终端用户、部署/分发形态和适用组织合同。 | `unknown` | [Codex auth docs](https://developers.openai.com/codex/auth/)；[Business Terms](https://openai.com/policies/business-terms/) |

## 11. 明确保留的 unknown register

以下项目不能由本轮材料升级为 `verified`：

1. root/platform npm 发布物是否已经满足 Codex、Ratatui、ripgrep、PCRE2、zsh 及 Cargo transitive 依赖的全部 LICENSE/NOTICE/版权/exception 交付义务；
2. Darwin arm64 官方 platform tarball 的完整文件清单与所有嵌入材料（本轮保留 `unknown`）；
3. 固定 Cargo.lock 中 1197 个 registry package、12 个 git package 和 workspace package 的逐包 SPDX/license expression、版权、NOTICE、例外与实际二进制包含关系；
4. ripgrep 的实际发布 binary 与上游源码之间的独立构建关系，以及 PCRE2 的 exact linkage 与 notice delivery；
5. zsh 旧 release artifact（`rust-v0.134.0-alpha.3`）与 `0.139.0` manifest/workflow 的精确关系；实际 zsh binary 是否包含 GPL shell functions，以及相应文本如何交付；
6. Ratatui attribution 在 npm root/platform/binary 交付物中的实际位置；
7. 从固定 commit 到目标 Darwin binary 的独立、可复现重建；npm attestation 只证明 release-level provenance，不替代该重建；
8. OpenAI 是否有本范围内可引用的 Codex 专属商标注册/授权文本，以及 ZWorkbench 具体名称、logo、截图或营销文案的适用许可；
9. Ratatui、ripgrep、PCRE2、zsh 等第三方名称、logo 或营销用法的具体授权边界；
10. 实际使用的 OpenAI 账户/认证路径、组织合同、地区、supported country、export/sanctions 状态、数据处理/retention/DPA、终端用户和产品条款；
11. 将 Codex/API/Provider 放入 ZWorkbench 的具体商业模式是否获得组织法律、合规、商标和再分发责任人的签核。

## 12. 边界结论

在本固定范围内，可以确认：Codex 源码仓库有 Apache-2.0 LICENSE 和含 Ratatui attribution 的 NOTICE；npm root/platform metadata 声明 Apache-2.0；root release artifact 有 npm/SLSA release-level provenance；ripgrep、PCRE2、zsh 的上游许可证文本可以定位；OpenAI 官方页面区分 personal service 与 API/business service，并公开给出 API、账户、使用政策和品牌规则。

仍不能确认：发布包 NOTICE/第三方材料已经完整交付；所有 vendor/transitive 依赖已经逐包清权；zsh 当前 artifact 的 same-release provenance；源码到二进制的独立可复现重建；Codex 专属商标许可；以及 ZWorkbench 具体账户、数据、地区、分发和商业模式的适用边界。

因此本文件的最终状态为：`NOTICE_clearance = unknown`、`commercial_boundary_for_specific_ZWorkbench_mode = unknown`、`legal_signoff = not performed`。本文件不作“可商业使用”“可再分发”“可转售”或候选采用建议。

---

来源访问日期：`2026-08-31`。官方页面、registry metadata、release artifact 和条款可能变更；重新审计时应重新固定 URL 返回内容、tag/commit、package integrity、attestation subject 和适用条款版本。
