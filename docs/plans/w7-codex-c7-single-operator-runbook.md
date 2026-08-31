# W7 Codex C7 单人生命周期签核 Runbook

状态：`partial evidence / candidate-signoff-unknown-stop` · 适用候选：Codex Harness `codex-cli 0.139.0`

这是一份 C7 人工证据模板，不是自动安装脚本。任何会改变全局 npm、全局
`CODEX_HOME`、真实凭证、真实 Provider、生产项目或外部数据的步骤，都必须由
单一操作者在场、明确授权后亲自执行。Codex evaluation agent 不代执行这些步骤。

## 1. 签核目标

| Gate | 硬阈值 | 必须有的证据 |
|---|---:|---|
| 首次安装 | ≤90 分钟 | 从准备开始到版本/入口验证完成的真实 wall-clock stopwatch |
| 升级 + 回滚 | ≤30 分钟 | 旧/新 identity、配置/ledger snapshot、升级验证、回滚后 identity |
| backup / restore | ≤30 分钟 | backup digest、损坏或故障注入、恢复 digest、C2-C6 identity 完整 |
| 故障定位 | ≤30 分钟 | 固定 `fault_id`、run/event 关联、诊断结论、下一步动作 |
| 维护复杂度 | ≤3 个常驻维护对象 | service manifest；不把测试 fake service 当生产服务 |
| 专家依赖 | 0 个额外专家 | 操作者独立完成；记录任何求助即不满足此门 |

任一 gate 缺少 stopwatch、identity、操作者记录或关键输出，都必须判为
`unknown/stop`，不能用机器 subprocess 时间替代人工时间，也不能用其他 gate 的
通过抵消。

## 2. 执行前安全检查

由操作者在开始 stopwatch 前填写：

| 项目 | 记录 |
|---|---|
| operator / date / timezone |  |
| candidate executable | `/opt/homebrew/bin/codex`（如变更必须说明） |
| expected version | `codex-cli 0.139.0` |
| release / commit | `rust-v0.139.0` / `a7dff904308535e965aee87680c1fc5ef1d19eec` |
| current version before change |  |
| real credentials in use | 必须为 `false`，除非该 gate 明确获批且记录范围 |
| production data in scope | 必须为 `false` |
| backup destination | case-local 或已批准的可恢复位置： |
| rollback target |  |
| composition owner | 单一 owner 名称/版本： |
| explicit authorization id | 真实 install/upgrade/rollback 必填： |

停止条件：目标版本、回滚版本、备份位置或授权范围无法写清；出现未预期的
权限提升、非 case-local 写入、凭证输出、外网目的地或不可逆副作用；或 C4
composition approval owner 不可用。停止时保留当前日志和状态，不继续猜测。

## 3. 计时规则

每项 gate 使用独立 stopwatch。开始时记录 `T_start`，完成最后一项验证并保存证据
时记录 `T_end`；总时间为 `T_end - T_start`，包括等待、权限处理、失败恢复和
重新验证。普通网络或进程等待不能暂停计时。

### Stopwatch ledger

| gate | T_start | T_end | elapsed minutes | threshold | operator | helper count | result | evidence path |
|---|---|---|---:|---:|---:|---:|---|---|
| install |  |  |  | ≤90 |  |  |  |  |
| upgrade + rollback |  |  |  | ≤30 |  |  |  |  |
| backup / restore |  |  |  | ≤30 |  |  |  |  |
| fault diagnosis |  |  |  | ≤30 |  |  |  |  |

`helper count > 0`、操作者无法独立完成、或 elapsed 超阈值，结果为 `fail`；未开始
或证据不完整，结果为 `unknown`。

### 当前已报告的人工计时

| gate | 实际耗时 | 时间判定 | 操作环境 | 当前证据状态 |
|---|---:|---|---|---|
| install | `17.01 秒`（`0.2835 分钟`） | 时间项通过（≤90 分钟） | 临时 C7 prefix；全新安装；单人 | 同一次 raw log 已绑定版本、help、npm tree、四个 artifact digest；SHA-256 `6db2fe3a…` |
| upgrade + rollback | `14.35 秒`（`0.2392 分钟`） | 时间项通过（≤30 分钟） | `0.138.0 → 0.139.0 → 0.138.0`，临时 C7 prefix，单人 | 原始 log 已归档并完成 SHA-256 校验 |
| backup / restore | `12.38 秒`（`0.2063 分钟`） | 时间项通过（≤30 分钟） | 隔离 owner-backed case，单人，loopback-only Provider | `status: pass`，20/20 checks；[evidence](../../evaluation/runs/w7-codex-c7-human-20260831T180332/README.md) |

机器可读副本：[`w7-codex-c7-human-timings.json`](./w7-codex-c7-human-timings.json)。这些记录只关闭时间阈值，不等于 C7 签核。

## 4. Gate A：真实安装（人工执行）

前提：操作者确认当前没有需要保护的全局 Codex 变更，已记录当前 PATH、Node/npm
版本和回滚计划，并确认没有真实生产数据进入测试。

1. 开始 stopwatch。
2. 按已批准的 release 安装方式安装固定版本：
   `npm install -g @openai/codex@0.139.0`。
3. 记录安装输出、权限提示、网络等待、失败及恢复动作；不要隐藏失败。
4. 执行 `codex --version`，确认 `codex-cli 0.139.0`。
5. 执行 `codex app-server --help`，保存入口和 experimental 标记。
6. 核对 wrapper、npm package、platform package、vendor binary 的 digest 与
   [`w7-codex-candidate-manifest.json`](./w7-codex-candidate-manifest.json)。
7. 保存日志并停止 stopwatch。

安装 gate 只回答“单人能否完成固定 release 的真实安装”。本次在临时 C7 prefix
完成全新安装，人工 stopwatch 为 `17.01 秒`（`0.2835 分钟`），同一次 raw log
包含 `codex-cli 0.139.0`、完整 `app-server --help`、npm tree、wrapper/npm
package/platform package/vendor binary 四个 digest，以及
`=== C7_INSTALL_T_END_SAVED ===` 结束标记。日志为
[`fresh-install-human-bound.Vta7cz`](../../evaluation/evidence/w7-codex-c7/fresh-install-human-bound.Vta7cz)，
SHA-256 为 `6db2fe3abaf3febe72ab6a6acbd282e587daf1876b7c5cb255fd66e7eaefecb5`；四个
digest 与候选 manifest 一致。此前机器 fresh-install `2.314s` 的独立日志仍保留，
机器时间不替代人工 stopwatch。该项关闭 fresh-install 的人工日志绑定，但不证明
app-server 原生调度、approval、Provider routing 或 replay 能力。

## 5. Gate B：真实升级与回滚（人工执行）

1. 开始 stopwatch；记录升级前 `codex --version`、入口 help、配置 identity、
   composition ledger digest 和 C2-C6 evidence identity。
2. 复制并校验 upgrade 前 snapshot；确认 rollback target 与 snapshot 可读。
3. 在批准的目标 release 上执行升级，并保存完整输出。
4. 运行版本、入口、配置、ledger schema 和最小受控 smoke check；禁止把 smoke
   结果写成 C4 native approval 或 C3-C6 原生能力通过。
5. 执行回滚到预先记录的 target，重新核对版本、入口、配置、ledger digest 和
   identity；若升级失败，按 runbook 停止新触发并先恢复旧 snapshot。
6. 保存 upgrade/rollback 前后 identity、输出、失败恢复记录并停止 stopwatch。

升级 gate 必须验证“升级后可回滚且 durable state 没有静默漂移”，不能只验证命令
返回码为 0。任何 schema migration、配置改写或 ledger 损坏都使 gate `fail` 或
`unknown/stop`，不得继续触发危险动作。

补充的隔离 machine probe 已在同一 SQLite owner 上完成上述边界的最小验证：三个版本
阶段的 owner schema 都是 `zworkbench-composition-owner/v1`，adapter config identity
保持不变，升级前 run 在回滚后仍保留；中间受控 app-server 启动失败被持久化为
`failed` 且无 effect，owner reopen 后 digest 一致。证据见第 10 节的
`upgrade compatibility summary`。这只是 machine contract，不是该 gate 的人工计时签核。

## 6. Gate C：backup / restore

该 gate 的真实对象是 composition owner 管理的 durable state；Codex 原生
ThreadItems 不得被当作唯一账本。

当前已有真实 composition owner：SQLite 文件由 owner 持有 run、approval、effect、
result、replay metadata 和 event ledger。接入 Codex adapter 后，owner-backed machine
backup/restore 已 `3/3 pass`，并且 exit machine control 已 `3/3 pass`；单一操作者随后在
隔离 owner-backed case 上完成 backup/restore，耗时 `12.38 秒`（`0.2063 分钟`），时间项
通过。备份保留/加密/远端责任和真实灾难恢复仍未签核，不能把该 fixture 结果写成完整
C7 signoff。

1. 开始 stopwatch；冻结新触发，记录当前 C2-C6 identity、schema、版本和 service
   manifest。
2. 导出 composition state、schedule/run identity、effect/result ledger、Provider
   capability/fallback ledger、canonical event/replay metadata 和策略引用。
3. 对 backup 计算 digest，并在独立但可恢复的位置保存；记录保留期限与访问范围。
4. 在受控副本中注入可识别的损坏或缺失，保留故障前副本。
5. 恢复 backup，核对 digest、schema、状态健康、C2-C6 identity 和“无重复执行”
   记录；未获批时不要触发 live replay 或真实副作用。
6. 保存 backup、restore、故障注入和核对输出，停止 stopwatch。

通过 restore 不等于通过真实灾难恢复；跨版本迁移、加密、retention、远端备份和
删除责任必须单独记录。任何恢复后 identity 不一致，立即 `unknown/stop`。

## 7. Gate D：预制故障定位

使用固定的、不会触碰生产数据的故障，例如当前审计中的
`w7-c7-build-provenance-unknown`。不要为了制造故障修改真实安装或真实用户数据。

1. 开始 stopwatch，读取故障的 `fault_id`、`run_id`、`event_id` 和 candidate
   identity。
2. 按事件顺序定位：入口/版本 → environment → composition owner → Provider →
   policy/approval → tool/effect/result → replay/exit metadata。
3. 写出故障分类、影响范围、当前未知、可执行且有边界的 next action；禁止把
   `unknown` 改写为 `pass`。
4. 若涉及危险动作，确认组合 approval owner 默认 deny/safe-stop；保存证据并停止
   stopwatch。

故障定位 gate 的通过标准是单一操作者能在 ≤30 分钟内得到可复核的 bounded
diagnosis，不是必须修复所有故障。机器 fixture 已验证 fault/run 关联和 bounded
diagnosis；跨版本 probe 还验证了受控 adapter startup failure 会被 owner 持久化为
terminal `failed`。本轮单一操作者完成同一隔离 fixture 的读取、判断和保存诊断，耗时
`2 分 51.31 秒`（`2.85517 分钟`），时间项通过；证据见
`evaluation/runs/w7-codex-c7-20260830T172916-565440Z/cases/fault_diagnosis/repeat-01/human-diagnosis.md`。

## 8. 退出与许可证补充审计

退出是机器 contract + 人工责任清单的组合：

- 导出候选 identity、composition schema、策略引用、Provider 配置引用、事件/回放
  元数据和许可证清单；
- 在独立目录 re-import 并校验；
- 明确删除本地 export/import、case-local `CODEX_HOME`、composition ledger 副本、
  Provider 账户/密钥引用、远端资源和 retention 记录的责任人；
- 保存删除前后清单，不把无法观察的远程残留写成零残留；
- 对固定源码 LICENSE、package/platform metadata、所有依赖 NOTICE、商标、API/
  商业使用边界和发布 artifact provenance 分别签核。

当前已知：固定源码和 package metadata 声明 `Apache-2.0`；root/platform npm 包的
SLSA provenance 已将 release artifact 绑定到 `rust-v0.139.0` / `a7dff904…`，且本机
npm 安装内容与 registry tarball 核对通过；隔离 npm CLI `audit signatures` 也验证了
root/platform 两个包的 registry signatures 与 attestations。这只关闭 release-artifact
层，不等同于独立 reproducible rebuild、完整 NOTICE/商业边界或其他安装渠道的签核。
法律或供应链签核不能由本 runbook 自行代替。详细证据见
[`w7-codex-c7-license-provenance-audit.md`](./research/w7-codex-c7-license-provenance-audit.md)。

## 9. C4/C7 联合停止条件与签核

以下任一项出现，C7 不得签核：

- Codex native approval request 缺失被误写成 native pass；
- 组合 approval owner 不唯一、token 可重放、scope 不匹配仍有 effect，或未知请求未 deny；
- 升级/回滚后 run、effect、result、event 或 replay identity 漂移；
- 真实安装或故障定位未由单一操作者用 stopwatch 完成；
- 服务数超过 3、需要额外专家、或维护责任无法归属；
- NOTICE/商业边界/provenance 任何一项仍无签核；
- 退出只核对 case-local 文件，却声称真实账户、远端资源或 retention 已清理。

最终签核记录：

| 项目 | 结果/签名 |
|---|---|
| C4 composition path | `pass-with-composition`（证据：`w7-codex-c4-approval-20260831T032346-194000Z`） |
| C4 native approval | `unknown/not-required-for-composition` |
| C7 machine contract | `18/18 pass`（最新 run 见 `w7-codex-c7-20260831T032735-294299Z`） |
| C7 human timing | `fixture-level-pass`：install `17.01 秒`、upgrade/rollback `14.35 秒`、隔离 owner-backed backup/restore `12.38 秒`、预制故障定位 `2 分 51.31 秒`均由单一操作者报告并低于阈值；install 人工 stopwatch 已与同一次 raw log 绑定 |
| C7 real install | `pass-at-install-timing-and-identity-level`：临时 prefix 全新安装 `0.139.0`，人工耗时 `17.01 秒`，版本/help/npm tree/四个 digest 与 raw log 已关联；完整 C7 仍受其他阻断 |
| C7 real upgrade/rollback | `partial-exercised`：临时 prefix `0.138.0 → 0.139.0 → 0.138.0`，`14.35 秒`；版本/help 原始日志和同一 owner 跨版本 machine probe 已固化；生产 migration 未验证 |
| C7 license/NOTICE/commercial | `inventory-only / unknown`：vendor/transitive ledger 已生成，逐包 clearance 和商业/API/商标审查未签核 |
| C7 source-to-binary provenance | `pass-at-release-level`（npm SLSA + npm CLI 验签 + 本机 npm bytes binding）；独立重建 `unknown` |
| overall | **`unknown/stop` until all missing gates are signed** |

## 10. 关联资产

- [`w7-codex-c7-findings.md`](./w7-codex-c7-findings.md)
- [`w7-codex-c4-approval-findings.md`](./w7-codex-c4-approval-findings.md)
- [`w7-codex-candidate-manifest.json`](./w7-codex-candidate-manifest.json)
- [`w7-codex-c7-primary-sources.md`](./research/w7-codex-c7-primary-sources.md)
- [`fresh-install.log`](../../evaluation/evidence/w7-codex-c7/fresh-install.log)
- [`fresh-install-human-bound.Vta7cz`](../../evaluation/evidence/w7-codex-c7/fresh-install-human-bound.Vta7cz)
- [`w7-codex-c7-dependency-ledger.md`](./research/w7-codex-c7-dependency-ledger.md)
- [`upgrade compatibility summary`](../../evaluation/runs/w7-codex-owner-upgrade-20260831T095350-497892Z/summary.json)
- [`run_codex_owner_upgrade_compat.py`](../../evaluation/runner/run_codex_owner_upgrade_compat.py)
- [`run_codex_c7.py`](../../evaluation/runner/run_codex_c7.py)
