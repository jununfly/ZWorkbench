# W8 H1 Bootstrap findings

状态：`product execution / fixture + formal clean artifact integration verified`
日期：2026-09-04

本轮完成了 `1-9-2` 的 ZWorkbench H1 runtime seam：固定 artifact-mode
manifest、profile、依赖锁、build receipt 和 policy/provider/environment identity，
由 [DshRuntimeAdapter](../../src/zworkbench/dsh_runtime.py) 以 `shell=false` 启动一个
case-local 外部进程，并通过 [CompositionOwner](../../src/zworkbench/composition.py)
记录 bootstrap event、exit receipt、结果和 safe-stop。

## Fixture-level result

隔离 fixture 位于 [`evaluation/fixtures/w8_dsh_bootstrap/v1`](../../evaluation/fixtures/w8_dsh_bootstrap/v1)，
测试入口为 [`tests/test_dsh_runtime.py`](../../tests/test_dsh_runtime.py)，可重复 runner 为
[`run_w8_dsh_bootstrap.py`](../../evaluation/runner/run_w8_dsh_bootstrap.py)。
`PYTHONPATH=src python -m unittest tests.test_dsh_runtime -v` 的结果为 `7/7 pass`；
runner 的 `success`、`unknown`、`nonzero` 三个场景为 `3/3 pass`；全量产品测试为
`68/68 pass`。

| 场景 | 观察 | 结果 |
|---|---|---|
| 固定 artifact 正常启动 | parent Run completed；`fixture-dsh-session-1`；`started → ready`；退出码 0 | pass |
| artifact 被篡改 | 启动前 digest mismatch；不启动进程；owner safe-stopped | pass |
| manifest 未知字段 | 启动前拒绝；owner safe-stopped | pass |
| case-local 路径越界 | 启动前拒绝；owner safe-stopped | pass |
| 未知 bootstrap wire message | 记录拒绝事件和 exit receipt；不产生 semantic success | pass |
| 非零退出码 | 记录退出码 7；owner safe-stopped | pass |
| owner event seam | 可用稳定 event id 幂等重放；原始 credential 字段拒绝 | pass |

## Evidence boundary

上述是 `fixture-level` 的产品 seam 证据，不是 ZDSHarness 原生能力或正式 DSH 集成通过。
本 fixture 使用确定性脚本、fake/loopback Provider 和空插件 profile，不访问网络、不读取凭证，
也不修改 sibling checkout。

正式 H1 的资格不由 fixture 结果代替；必须来自 clean pinned artifact，并由 adapter 校验
source commit、依赖锁、平台、artifact digest、profile digest 和 build receipt。

## Source-plane integration result

本轮还修复并验证了真实 DSH source/build plane 的 integration blocker。`@deepseek-ai/dsh-zworkbench-bootstrap` 的 `cordis.patch.yml` 原先把 bundle entry 写成普通 patch，DSH composer 因而报告 `patch: entry "zworkbench-bootstrap" not found`，bootstrap plugin 没有挂载，进程既没有 JSONL 输出也没有退出请求；改为标准 `insert` patch 后，built CLI regression e2e 通过（1/1），bundle 单测通过（2/2），`check:ci:artifacts` 通过（5/5）。

`evaluation/runner/run_w8_dsh_artifact_integration.py` 将已构建的 `apps/cli/lib` 与其 `apps/cli/node_modules` closure 放入独立 staging，再以 `dsh --profile zworkbench-bootstrap` 交给 `DshRuntimeAdapter`。不传 pinned commit 时，它只产生 source-plane 证据；传入完整 commit 时，会校验 clean checkout 与精确 commit 匹配，并生成正式 receipt。

## Formal clean maintainer-pinned artifact receipt

本轮在独立 ZDSHarness worktree `codex/h1-bootstrap-pinned` 上完成构建；主 ZWorkbench 和
ZDSHarness 原工作树均未被重置或推送。实际执行命令：

```text
pnpm install --frozen-lockfile --ignore-scripts --prefer-offline
pnpm run build:lib
pnpm run check:ci:artifacts       # 5/5 passed
PYTHONPATH=src python evaluation/runner/run_w8_dsh_artifact_integration.py \
  --dsh-repo /tmp/zds-h1-pinned.ZiFs62 \
  --pinned-commit c37c8483ce167a5019aeb65a196a09b5b67ccc01 \
  --output /tmp/zworkbench-h1-formal-final.lzXpXK
```

正式 receipt：`/tmp/zworkbench-h1-formal-final.lzXpXK/maintainer-pinned-artifact-receipt.json`，
digest 为 `sha256:170173b527e57e5d17adaafb01da7473b126186e65558a17cc8117afcc8a56cb`。
脱敏 provenance 如下：

| 项目 | 实际值 |
|---|---|
| source commit / pinned commit | `c37c8483ce167a5019aeb65a196a09b5b67ccc01` |
| source worktree | `clean` |
| DSH runtime / profile | `0.1.0-rc.5` / `zworkbench-bootstrap@0.1.0-rc.5` |
| dependency lock digest | `sha256:a55c665bbc62bc0bf96b49bd1853ab2997022ad65dfed96992516ec98f9c12d4` |
| artifact digest | `sha256:c0226687bb20f45c603ec6fe50f3de16d1c3510c3a803304ec575ef9bc366c62` |
| profile digest | `sha256:2f8bf241bbed1c12f8fb0257179c9c829b816eb6818921f730e97d8d0d3e05be` |
| build receipt digest | `sha256:99d6ccc53188c066b5e4610a03e85f8615b62e879316d82691a4ff7fff4e1788` |

正式 runner 结果为 `status=pass`、`formal_h1_status=completed`：owner parent Run
`completed`，DSH session identity 存在，owner 严格记录 `dsh.bootstrap.started →
dsh.bootstrap.ready`，`dsh.exit` 为 0、stderr 0 bytes、session persistence 存在、
network requests / real credentials / external effects 均为 0。该 receipt 是本地
maintainer-pinned provenance 证据，不是签名的公开 release asset；H2-H8、宿主 sandbox
和真实 Provider 兼容性仍未声称通过。

## Earlier clean artifact provenance probe

为避免污染 ZDSHarness sibling 工作树，本轮将其 `HEAD` 通过 `git archive` 解包到独立临时目录，
在该目录内执行受控安装和构建 gate。脱敏结果如下：

| 项目 | 结果 |
|---|---|
| source commit | `a603e94485ab282e2c940ed56daee3b20b9bd475` |
| source archive digest | `sha256:aa75f8ff59f9494a6d8e129af8cedc24b0519ff2b2ea43a63f95457da9cad449` |
| dependency lock digest | `sha256:c0c932ef1e4931189159833ca99e1ff937519469a6cc0c3a744047e9dca777df` |
| build environment | Node `v22.23.1`；pnpm `11.19.0`；`darwin arm64` |
| install gate | `pnpm install --frozen-lockfile --ignore-scripts --prefer-offline`：通过 |
| build gate | `pnpm run build:lib`：通过 |
| artifact gate | `pnpm run check:ci:artifacts`：5 个 gate 全部通过 |
| 临时 CLI lib snapshot | `sha256:af41a71411852cd09563415e4e26a33fa471cc48695a6cd8c826eef779e05610` |

最后一项只是临时构建出的 `apps/cli/lib` snapshot digest，不是正式 release artifact digest，
不能单独作为可交付 artifact receipt。该 clean archive 取自 bootstrap bundle 尚未进入的
`HEAD`，所以它只证明了当时 source/lock/platform 和构建 gate 的 provenance，不能代表当时
dirty source plane 的 bootstrap wire；本轮已由正式 pinned receipt 补齐这条证据。

结论：原有 DSH profile/bootstrap 阻塞已在 source/build/integration plane 解决；本轮 clean
maintainer-pinned receipt 与正式 H1 integration 已闭合，允许进入 `1-9-3` H2。

## Verification note

全量产品测试首次复跑出现一次已有 fixture 时序失败；根因是 unknown-wire fixture 在 adapter
终止前自然退出 0。fixture 现保持存活以稳定覆盖 fail-closed process cleanup，并同步更新
artifact/build receipt digests。修正后 `PYTHONPATH=src python -m unittest discover -s tests
-p 'test*.py'` 为 `68/68 pass`，unknown-wire 定向回归为 `20/20 pass`。
