# W7 Codex C7 vendor / transitive dependency ledger

状态：`bounded-inventory / signoff-open` · 审计日期：`2026-08-31` · 候选：Codex `0.139.0` Darwin arm64

这份 ledger 只固化机器观察到的组件、版本、路径、摘要和一手许可证来源；它不是
完整 SPDX 清单、NOTICE 文件或法律意见。机器能确认的“声明存在”与责任人要签核的
“可再分发/商业使用边界”保持分离。机器可读副本见
[`w7-codex-c7-dependency-ledger.json`](./w7-codex-c7-dependency-ledger.json)。

## 固定边界与来源

- Codex release：`rust-v0.139.0`，peeled commit
  `a7dff904308535e965aee87680c1fc5ef1d19eec`。
- root/platform npm package 都声明 `Apache-2.0`，且本机安装目录没有发现
  `LICENSE*`、`NOTICE*`、`COPYING*` 或 `THIRD-PARTY*` 文件。
- vendor layout manifest 是 `layoutVersion=1`、target `aarch64-apple-darwin`；它只列出
  Codex entrypoint、`rg` 和 zsh runtime resource，不提供完整第三方归属清单。
- 固定源码 workspace 的 `Cargo.lock` SHA-256 为
  `4315b596d910df46b6091580476f9df6a388b9d90874e45544a93346ccf24e37`。

## 直接包与 vendor 组件

| 对象 | 观察 | 许可证来源/状态 | NOTICE/商业边界 |
|---|---|---|---|
| `@openai/codex@0.139.0` | root package，无 runtime dependencies；6 个 optional platform dependencies | package metadata 与 Codex source `LICENSE` 为 Apache-2.0；`declared-only` | 安装包无 NOTICE；已形成服务条款、API、商标和商业使用边界地图，模式签核未完成 |
| `@openai/codex@0.139.0-darwin-arm64` | platform package，无 package dependencies，包含 `vendor` | package metadata 为 Apache-2.0；`declared-only` | 安装包无 NOTICE；vendor 归属未由 metadata 完成；再分发 clearance 未完成 |
| Codex vendor binary | `0.139.0` / `aarch64-apple-darwin`；SHA-256 `c6ede9ef…83915` | 源码 workspace 声明 Apache-2.0；二进制内 transitive 归属未抽出 | `unknown`，不能只凭 root license 放行 |
| ripgrep | `15.1.0`，revision `af60c2de9d`；SHA-256 `4fdf1d83…f3e94` | 上游 `COPYING`：`MIT OR Unlicense`；来源文件 SHA-256 `01c266bc…2390f` | 已找到源许可证，二进制再分发材料仍需审 |
| PCRE2 | `10.45`，由 `rg --version` 报告可用 | 上游 `LICENCE.md`：`BSD-3-Clause WITH PCRE2-exception`；来源文件 SHA-256 `9cf7ac69…885a` | exact linkage 和随二进制提供的归属材料未核 |
| zsh | `5.9.0.3-test`；SHA-256 `db6fe1a7…8dd71` | 上游 `LICENCE` 含 Zsh license，并提示包含的 GPL shell functions 需单独考虑；来源文件 SHA-256 `d06fdf3e…0ef5f5` | exact binary contents 与 GPL function inclusion 未核 |

上表中的本机路径、完整摘要和证据 URL 在 JSON ledger 中保留。`rg` 的 PCRE2 项是
功能输出观察，不等于已经完成二进制链接分析；zsh 的版本字符串也不等于已证明发布
包包含哪些 shell functions。这两个点因此保持 `review-required`。

## Rust/Cargo transitive inventory

固定 commit 的 `codex-rs/Cargo.lock` 是 Cargo lock format 4，共 1332 个 package entry：

| 分类 | 数量 | 当前含义 |
|---|---:|---|
| workspace package | 123 | Codex 自有 workspace crate；需从对应 `Cargo.toml`/源文件收集许可证与版权 |
| crates.io registry package | 1197 | 需逐包解析 crate metadata、版权和再分发材料 |
| git package | 12 | 需锁定 git source、commit 和对应许可证/NOTICE |

这里记录的是可复核的 lock inventory，不把 1332 个包静默标成 Apache-2.0，也不把
Cargo lock 的存在误读成 NOTICE 清单。当前 `license_resolution` 和
`notice_resolution` 均为 `not-per-package-resolved`。

## 签核边界

当前已经完成：

- 直接 npm 包的 declared license 观察；
- vendor 文件布局、版本字符串和本机摘要；
- ripgrep、PCRE2、zsh 的一手许可证来源定位与来源文件摘要；
- 固定 Cargo lock 的总量分类。

仍不能签核：

- 逐包 SPDX、版权、NOTICE 和例外条款清单；
- vendor binary 是否带齐所需再分发文本，以及具体归属应放在哪里；
- OpenAI 服务/API 条款、商标规则、商业使用和组织内部合规边界；
- 独立 source-to-binary reproducible rebuild；
- 真实账户、Provider、远端 backup/retention 的删除责任。

因此，本 ledger 只把 C7 的依赖未知从“完全未盘点”收窄为“组件边界已盘点、边界地图
已形成、完整逐项 clearance 未完成”，C7/G7 继续 `unknown/stop`。边界地图见
[`w7-codex-c7-notice-commercial-boundary.md`](./w7-codex-c7-notice-commercial-boundary.md)，
一手条款与固定版本来源见 [`w7-codex-c7-primary-sources.md`](./w7-codex-c7-primary-sources.md)，
独立核查见
[`w7-codex-c7-notice-commercial-primary-sources.md`](./w7-codex-c7-notice-commercial-primary-sources.md)。
