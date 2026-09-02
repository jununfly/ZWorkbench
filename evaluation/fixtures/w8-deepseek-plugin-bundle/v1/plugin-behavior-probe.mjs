#!/usr/bin/env node
/*
 * Behavior probes for the pinned standard plugins in the W8 acceptance
 * fixture.  This is evaluation infrastructure, not ZWorkbench product code.
 * It exercises only deterministic, case-local functionality:
 *   - router-standard's pure task classification/staging helpers;
 *   - dsh-memoir's local store and bounded hot-memory selector.
 *
 * No Provider, network, credentials, or ZWorkbench owner database is used.
 */

import { pathToFileURL } from 'node:url'
import path from 'node:path'

const args = Object.fromEntries(process.argv.slice(2).map((value) => {
  const index = value.indexOf('=')
  return index < 0
    ? [value.replace(/^--/, ''), '']
    : [value.slice(2, index), value.slice(index + 1)]
}))

const caseRoot = path.resolve(args['case-root'])
const routerCore = path.resolve(args['router-core'])
const memoirDir = path.resolve(args['memoir-dir'])
const workspace = path.join(caseRoot, 'workspace')
const memoirStorePath = path.join(caseRoot, 'dsh-memoir.json')

const router = await import(pathToFileURL(routerCore).href)
const { MemoirStore } = await import(pathToFileURL(path.join(memoirDir, 'store.js')).href)
const { selectHotMemory } = await import(pathToFileURL(path.join(memoirDir, 'selector.js')).href)

const routeInputs = [
  '开始开发一个小型 Python 工具并运行测试',
  '修复这个报错并排查回归',
  '分析这个问题',
]
const routeA = routeInputs.map((text) => ({
  text,
  mode: router.classifyTask(text),
  band: router.bandOf(router.classifyTask(text)),
  core: router.coreFor(router.classifyTask(text)),
}))
const routeB = routeInputs.map((text) => ({
  text,
  mode: router.classifyTask(text),
  band: router.bandOf(router.classifyTask(text)),
  core: router.coreFor(router.classifyTask(text)),
}))

const stageA = router.advanceStage(0, ['todo_write'], '开始开发')
const stageB = router.advanceStage(stageA, ['edit'], '继续')
const stageC = router.advanceStage(stageB, ['delivery_check'], '完成验证')

const store = new MemoirStore(memoirStorePath, { mtimeCheckIntervalMs: 0 })
const fixedNow = 1_800_000_000_000
store.record(workspace, {
  section: 'actions',
  title: '验证 adapter 边界',
  content: '所有动态插件写入都必须经过 owner policy gate。',
  importance: 5,
  pinned: true,
}, { kind: 'fixture', sessionId: 'plugin-aware-e4' })
store.record(workspace, {
  section: 'lessons',
  title: '保留 unknown',
  content: '没有 Provider failover 合同就不能把同路重试算作切换。',
  importance: 4,
}, { kind: 'fixture', turnId: 'plugin-aware-e4' })
store.record(workspace, {
  section: 'note',
  title: '不应注入',
  content: 'note entry must not enter hot memory.',
}, { kind: 'fixture' })

const entries = store.entries(workspace)
const budget = { targetTokens: 80, hardMaxTokens: 120 }
const hotA = selectHotMemory(entries, budget, fixedNow, 'en')
const hotB = selectHotMemory(entries, budget, fixedNow, 'en')

process.stdout.write(JSON.stringify({
  schema: 'zworkbench-w8-deepseek-plugin-behavior/v1',
  isolation: {
    caseRoot,
    workspace,
    memoirStorePath,
    provider: 'none',
    externalNetwork: false,
    realCredentials: false,
  },
  router: {
    implementation: 'router-core-v34.mjs',
    routeA,
    routeB,
    deterministic: JSON.stringify(routeA) === JSON.stringify(routeB),
    stageSequence: [stageA, stageB, stageC],
    providerFailoverContract: 'not-provided-by-router-core',
  },
  memoir: {
    storePath: memoirStorePath,
    entryCount: entries.length,
    selectedCount: hotA.selected.length,
    selectedSections: hotA.selected.map((entry) => entry.section),
    hotTextA: hotA.text,
    hotTextB: hotB.text,
    deterministic: hotA.text === hotB.text,
    estimatedTokens: hotA.estimatedTokens,
    hardMaxTokens: budget.hardMaxTokens,
    noteExcluded: hotA.selected.every((entry) => entry.section !== 'note'),
    storeStats: store.stats(),
  },
}))
