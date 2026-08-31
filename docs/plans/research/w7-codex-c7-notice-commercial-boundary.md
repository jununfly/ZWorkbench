# W7 Codex C7 NOTICE 与商业边界决策地图

状态：`bounded-evidence / signoff-open` · 审计日期：`2026-08-31`（Asia/Shanghai）
候选：Codex `0.139.0` · Darwin arm64 · `rust-v0.139.0` / `a7dff904308535e965aee87680c1fc5ef1d19eec`

本文是 C7 的事实、边界和后续签核清单，不是法律意见，不授权再分发、转售或
商业化。它把“个人工作台继续试用”与“把 Codex 或其服务包装成产品”分开，避免
把 `Apache-2.0`、OpenAI 服务条款和第三方依赖许可证混成一个结论。

## 1. 决策范围

| 维度 | 本轮固定假设 |
|---|---|
| 产品阶段 | ZWorkbench acceptance/evaluation；面向个人开发者或小团队的受控内部试用 |
| 候选物 | 通过 npm 安装的 Codex `0.139.0` root package + Darwin arm64 platform package |
| 当前使用形态 | 操作者自己安装并在本机运行；不把 Codex 二进制重新打包进 ZWorkbench 发布物 |
| 不在本轮放行 | 对外分发 Codex/npm/binary、提供带 Codex 的 SaaS、共享或转售 OpenAI 账户/API key、使用 OpenAI logo 或暗示背书 |
| 需要单独确认 | 使用哪一种 OpenAI 账户/服务路径、所在地区、输入数据类型、是否会让第三方访问、是否发布可安装 artifact |

## 2. 证据摘要

| 主题 | 一手事实 | 当前判定 |
|---|---|---|
| Codex 源码许可证 | 固定 commit 的 `LICENSE` 是 Apache License 2.0；第 2 节授予复制、修改、分发等许可，第 4 节要求随分发提供许可证、保留归属/版权等声明；第 6 节不授予商标使用权 | `pass-as-declared`，仅覆盖 Codex Work 本身 |
| npm root/platform metadata | registry 与本机 package metadata 均声明 `Apache-2.0`；root tarball 的文件为 wrapper、`package.json`、`README.md`，platform 包携带 vendor 内容 | `pass-as-declared`；不能由 metadata 推导完整 NOTICE |
| 安装包 NOTICE | 对 `/opt/homebrew` 安装和本轮临时 prefix 均未发现 `LICENSE*`、`NOTICE*`、`COPYING*`、`THIRD-PARTY*` | `notice-material-missing / signoff-open` |
| vendor ripgrep | ripgrep `15.1.0` 的官方 `COPYING` 为 `MIT OR Unlicense` | `review-required`；若再分发需确认所选许可路径及随包材料 |
| vendor PCRE2 | PCRE2 `10.45` 官方许可证为 `BSD-3-Clause WITH PCRE2-exception`；BSD 二进制分发条件要求在文档或材料中重现声明、条件和免责声明 | `review-required`；需核对实际链接/随包文本 |
| vendor zsh | zsh `5.9` 官方许可证允许使用、复制、修改、分发，但明确提示部分 shell functions 可能受 GPL 约束 | `review-required`；需确认实际 vendor binary 及 resources 包含哪些 functions |
| Cargo transitive | 固定 `Cargo.lock` 有 `1332` 个 entry（workspace `123`、registry `1197`、git `12`） | `unknown`；尚未逐包解析 SPDX、版权、NOTICE 和例外 |
| OpenAI 开发者/企业服务 | 官方《OpenAI 服务协议》适用于 API、企业/开发者服务；允许将 API 集成到客户应用并向最终用户开放，但禁止共享/转售账户或 API key，并要求遵守政策 | `conditional / account-path-dependent` |
| OpenAI 个人服务 | 官方《使用条款》适用于 ChatGPT 等个人服务，禁止修改、复制、出租、出售或分发服务；其中的软件开源组件受其自身许可约束 | `不能将个人服务条款当作 Codex 源码再分发授权` |
| OpenAI 使用政策 | 官方《使用政策》禁止非法、有害、滥用、恶意网络活动、规避安全措施等使用 | `必须随工作台策略持续执行` |
| OpenAI 名称和 logo | 官方品牌指南称 OpenAI 名称、logo、ChatGPT、GPT 及其他商标属于 OpenAI；使用不得误导关系或暗示认可，logo 使用有额外规范 | `review-required`；不使用 logo，不把 OpenAI/Codex 作为产品品牌或背书 |

本地组件盘点与发布 provenance 的已有证据：
[`w7-codex-c7-license-provenance-audit.md`](./w7-codex-c7-license-provenance-audit.md)、
[`w7-codex-c7-dependency-ledger.md`](./w7-codex-c7-dependency-ledger.md)、
[`w7-codex-c7-dependency-ledger.json`](./w7-codex-c7-dependency-ledger.json)。
独立的一手来源核查见
[`w7-codex-c7-notice-commercial-primary-sources.md`](./w7-codex-c7-notice-commercial-primary-sources.md)。

## 3. 商业边界矩阵

这里的“可继续”是工程治理姿态，不是法律意见；“停止”表示在缺少相应责任人
签核前，不应把该行为放进发布或对外服务路径。

| 行为 | 工程处置 | 原因与必须保留的条件 |
|---|---|---|
| 个人本机安装并运行 Codex，ZWorkbench 不分发 Codex 二进制 | **可继续受控内部试用** | 保持固定版本和 provenance；不共享凭证；不把私有代码/密钥写入 evidence；遵守适用服务条款和使用政策 |
| 小团队内部使用，但每台机器自行安装 Codex | **条件可继续** | 明确组织账户/权限/数据责任；不共享个人账户；记录版本、Provider、数据范围和退出责任；仍不能称为 NOTICE 已签核 |
| 在 ZWorkbench npm、安装器、容器或压缩包中捆绑 Codex | **停止再分发** | 先完成 root/platform/vendor/Cargo 逐项许可证和 NOTICE pack，保留 Apache/第三方文本，核对 vendor binary 组成并完成合规审查 |
| 将 Codex CLI 改造后作为公开下载的产品组件 | **停止再分发** | 需要 Apache 条件、第三方 notice、商标/产品命名、版本更新和支持责任的共同签核；不能以 root package metadata 代替 |
| 用 OpenAI API 驱动自己的产品并向最终用户提供功能 | **条件可行，尚未签核** | 先确认适用的开发者/企业协议、地区、账户和数据处理条款；不得共享/转售 API key 或 OpenAI 账户；为终端用户和输入数据建立自己的产品条款与隐私责任 |
| 用 ChatGPT/个人服务账户驱动一个对外 SaaS 或共享工作台 | **停止** | 个人服务条款与企业/API 集成路径不同；账户共享、服务分发和自动化使用边界不能靠猜测放行 |
| 在产品名、logo、官网、营销材料中使用 OpenAI/Codex/GPT 品牌 | **默认停止 logo/背书用法** | 仅保留必要、准确的兼容性说明；不暗示认可；任何超出事实性引用的命名或视觉使用交给商标责任人 |
| 把模型输出直接当作高风险决策或未经审查的代码/动作 | **禁止自动放行** | 遵守使用政策和人工审查要求；危险 effect 继续由 composition owner fail-closed 控制 |

## 4. 适用于 ZWorkbench 的当前决策

### 4.1 可以继续的最小路线

在不把 Codex 放进 ZWorkbench 可分发 artifact 的前提下，继续个人/小团队本机
受控试用。Codex 由操作者依据固定 release 自行安装；ZWorkbench 只保存自己的
composition state、事件、回放元数据和审计引用，不复制 Codex vendor binary，也
不把 OpenAI 凭证写进日志或 backup。

这条路线只关闭“当前内部试用是否有明确工程边界”，不关闭 C7 的法律签核，也不
代表任何 OpenAI 服务账户路径已经得到组织批准。

### 4.2 当前明确禁止的扩展

- 不提交或发布包含 Codex vendor binary、platform package 或未经整理的 Cargo
  依赖的安装包；
- 不新增“自动生成 NOTICE”并把扫描结果当作已清权；每个依赖的许可证、版权、
  例外和实际随包文本必须可追溯；
- 不把 OpenAI API、ChatGPT 账户和 Codex 开源代码视为同一个许可对象；
- 不使用 OpenAI logo、产品名或模型名制造官方合作/背书印象；
- 不把本文件的工程判定当作法律、出口管制、隐私或商标意见。

## 5. 关闭 NOTICE/商业阻断的验收条件

### A. 组件和 NOTICE

1. 对固定 `0.139.0` Darwin arm64 发布物生成可复核 SBOM/组件清单，至少覆盖
   root/platform package、Codex vendor、ripgrep、PCRE2、zsh 和 `Cargo.lock` 的
   全部 1332 entries。
2. 每个可分发组件记录名称、版本、source/revision、license expression、版权/归属、
   NOTICE/例外文本来源、实际 artifact 路径和 digest；解析不到的项保持 `unknown`。
3. 对二进制内组件核对实际构建内容，而不是只看 `rg --version`、zsh 版本字符串
   或 root package 的 `license` 字段。
4. 生成随发布物携带的 NOTICE/许可包，并在独立目录做 re-import 检查；不得覆盖或
   改写上游许可文本。

### B. 服务、API、数据和商标

1. 明确每个运行模式的认证路径：Codex/ChatGPT 个人服务、OpenAI API、其他 Provider
   或纯本地模型；每种模式单独绑定适用条款和账户责任。
2. 明确输入、输出、日志、回放和 backup 是否包含个人数据、私有代码、密钥或第三方
   内容；在进入外部 Provider 前由策略和人工审批控制。
3. 对 OpenAI API 集成确认服务协议、使用政策、隐私/DPA、支持国家/地区、贸易管制、
   账户和 API key 不共享/不转售要求；不以 ChatGPT 个人条款代替 API 条款。
4. 对产品命名、兼容性说明、logo、截图和营销内容完成商标责任人审查；默认不使用
   logo，不暗示 OpenAI 认可或合作。

### C. 责任人和签核

最终需要项目维护者和合规/法律责任人分别确认：

- `notice_clearance`：逐项组件和发布 artifact 的再分发材料完整；
- `commercial_api_boundary`：各 Provider/账户路径、数据、地区和商业模式适用；
- `trademark_and_attribution`：名称、logo、归属和事实性引用合规；
- `exit_and_retention`：本地、远端 Provider、账户、backup 和 retention 的删除责任；
- `independent_rebuild`：若发布政策要求，源码到二进制的独立重建证据。

在这些字段没有明确责任人、签核日期和证据引用前，`complete_notice_signoff` 和
`commercial_api_trademark_signoff` 继续为 `false`，C7/G7 继续 `unknown/stop`。

真实 Provider、账户、远端 backup/retention 和第三方权限的退出责任不在本文件中
臆测，单独见 [`w7-codex-c7-remote-exit-responsibility.md`](../w7-codex-c7-remote-exit-responsibility.md)。

## 6. 一手来源

访问日期均为 `2026-08-31`；官方页面可能更新，重审时需重新记录页面版本/生效日。

### Codex 与第三方许可证

- [Codex fixed-commit LICENSE](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/LICENSE)
- [Codex fixed-commit codex-cli/package.json](https://raw.githubusercontent.com/openai/codex/a7dff904308535e965aee87680c1fc5ef1d19eec/codex-cli/package.json)
- [npm root metadata for @openai/codex@0.139.0](https://registry.npmjs.org/@openai%2fcodex/0.139.0)
- [npm root tarball](https://registry.npmjs.org/@openai/codex/-/codex-0.139.0.tgz)
- [npm Darwin arm64 metadata](https://registry.npmjs.org/@openai%2fcodex/0.139.0-darwin-arm64)
- [ripgrep 15.1.0 COPYING](https://raw.githubusercontent.com/BurntSushi/ripgrep/15.1.0/COPYING)
- [PCRE2 10.45 LICENCE.md](https://raw.githubusercontent.com/PCRE2Project/pcre2/pcre2-10.45/LICENCE.md)
- [zsh 5.9 LICENCE](https://raw.githubusercontent.com/zsh-users/zsh/zsh-5.9/LICENCE)

### OpenAI 服务和品牌

- [OpenAI 服务协议](https://openai.com/policies/services-agreement/)（页面显示更新于 2025-12-01，生效于 2026-01-01）
- [OpenAI 使用条款](https://openai.com/policies/terms-of-use/)（页面显示发布于 2026-01-01）
- [OpenAI 使用政策](https://openai.com/policies/usage-policies/)（页面显示生效于 2025-10-29）
- [OpenAI 品牌指南](https://openai.com/brand/)

## 7. 当前签核值

```text
license_declared: pass-as-declared (Codex root/platform/source)
notice_inventory: bounded-inventory; per-package clearance unknown
commercial_api_boundary: bounded-by-primary-terms; account/data/product mode still open
trademark_attribution: review-required
complete_notice_signoff: false
commercial_api_trademark_signoff: false
overall_c7_g7: unknown/stop
```
