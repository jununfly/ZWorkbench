#!/usr/bin/env node
/*
 * Runtime probe for the dsh-config-migrate dynamic-plugin seam.
 *
 * This file is evaluation-only. It executes the pinned host/client function
 * bodies inside a deliberately small facade. The facade permits case-local
 * reads and a constrained crypto child process, but denies every write. It
 * never imports a network module and never exposes real credentials.
 */

import crypto from 'node:crypto'
import { spawn as nativeSpawn } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'

const args = Object.fromEntries(process.argv.slice(2).map((value) => {
  const index = value.indexOf('=')
  return index < 0 ? [value.replace(/^--/, ''), ''] : [value.slice(2, index), value.slice(index + 1)]
}))

const caseRoot = path.resolve(args['case-root'])
const hostPath = path.resolve(args.host)
const clientPath = path.resolve(args.client)
const homePath = path.resolve(args.home)
const workspacePath = path.resolve(args.workspace)
const allowedScriptHashes = new Set(JSON.parse(args['allowed-scripts-json'] || '[]'))

function inside(candidate, root = caseRoot) {
  const relative = path.relative(root, candidate)
  return relative === '' || (relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
}

function checkedPath(candidate) {
  const resolved = path.resolve(String(candidate))
  if (!inside(resolved)) {
    const error = new Error(`path outside adapter root: ${resolved}`)
    error.code = 'ADAPTER_PATH_DENY'
    throw error
  }
  return resolved
}

const writeAttempts = []
const subprocessRequests = []
const registration = {
  rpc: new Map(),
  tools: [],
  ui: [],
  styles: [],
}

function removeOnce(list, value) {
  const index = list.indexOf(value)
  if (index >= 0) list.splice(index, 1)
}

function facadeFs() {
  return {
    async resolve(candidate) {
      return checkedPath(candidate)
    },
    async stat(candidate) {
      const target = checkedPath(candidate)
      const info = await fs.stat(target)
      return { type: info.isDirectory() ? 'directory' : 'file', size: info.size }
    },
    async listDir(candidate) {
      const target = checkedPath(candidate)
      const entries = await fs.readdir(target, { withFileTypes: true })
      return Promise.all(entries.map(async (entry) => {
        const entryTarget = checkedPath(path.join(target, entry.name))
        let size = 0
        if (entry.isFile()) size = (await fs.stat(entryTarget)).size
        return {
          name: entry.name,
          type: entry.isDirectory() ? 'directory' : 'file',
          target: entryTarget,
          size,
        }
      }))
    },
    async readText(candidate) {
      return fs.readFile(checkedPath(candidate), 'utf8')
    },
    async readBytes(candidate, _offset, maxBytes) {
      const value = await fs.readFile(checkedPath(candidate))
      if (typeof maxBytes === 'number' && value.length > maxBytes) throw new Error('read exceeds adapter limit')
      return new Uint8Array(value)
    },
    async writeText(candidate, content, _encoding, _mode, requestedPolicy) {
      const target = checkedPath(candidate)
      writeAttempts.push({
        path: target,
        bytes: String(content).length,
        requested_policy: requestedPolicy || null,
        effective_policy: 'adapter-controlled-deny',
        decision: 'deny',
      })
      const error = new Error('write denied by dynamic-plugin adapter policy gate')
      error.code = 'ADAPTER_WRITE_DENY'
      throw error
    },
  }
}

function facadeSubprocess() {
  return {
    spawn(spec) {
      const argv = Array.isArray(spec && spec.argv) ? spec.argv.map(String) : []
      const cwd = path.resolve(String(spec && spec.cwd ? spec.cwd : caseRoot))
      const script = argv[2] || ''
      const record = {
        argv,
        cwd,
        shell: false,
        script_sha256: crypto.createHash('sha256').update(script).digest('hex'),
        source_hash_allowlisted: false,
        decision: 'deny',
        reason: null,
      }
      const forbidden = /(?:https?:\/\/|fetch\s*\(|WebSocket|require\s*\(\s*['"](?:net|http|https|tls|dns|dgram|child_process)['"]|process\.env|(?:exec|execFile|spawnSync)\s*\()/i
      const argsInside = argv.slice(3).every((value) => {
        if (!value || value.includes('\n')) return true
        try { return inside(path.resolve(value)) } catch (_) { return false }
      })
      if (argv[0] !== 'node' || argv[1] !== '-e') record.reason = 'executable-or-mode-not-allowlisted'
      else if (!inside(cwd)) record.reason = 'cwd-outside-adapter-root'
      else if (spec.shell === true) record.reason = 'shell-requested'
      else if (forbidden.test(script)) record.reason = 'script-contains-forbidden-capability'
      else if (!argsInside) record.reason = 'subprocess-argument-outside-adapter-root'
      else if (!allowedScriptHashes.has(record.script_sha256)) record.reason = 'script-hash-not-pinned'
      else record.decision = 'allow'
      record.source_hash_allowlisted = allowedScriptHashes.has(record.script_sha256)
      subprocessRequests.push(record)
      if (record.decision !== 'allow') {
        const error = new Error(`subprocess denied: ${record.reason}`)
        error.code = 'ADAPTER_SUBPROCESS_DENY'
        throw error
      }

      const child = nativeSpawn(argv[0], argv.slice(1), {
        cwd,
        shell: false,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { PATH: process.env.PATH || '', HOME: caseRoot, DSH_HOME: homePath },
      })
      const stdout = []
      const stderr = []
      child.stdout.on('data', (chunk) => stdout.push(Buffer.from(chunk)))
      child.stderr.on('data', (chunk) => stderr.push(Buffer.from(chunk)))
      if (spec.stdio && spec.stdio.stdin && typeof spec.stdio.stdin.data === 'string') child.stdin.end(spec.stdio.stdin.data)
      else child.stdin.end()
      const done = new Promise((resolve) => child.on('close', (exitCode) => resolve({ exitCode })))
      const collected = {
        stdout: { readFrom: () => ({ text: Buffer.concat(stdout).toString('utf8') }) },
        stderr: { readFrom: () => ({ text: Buffer.concat(stderr).toString('utf8') }) },
      }
      return { done, collected }
    },
  }
}

function makeHarness() {
  return {
    handle(name, handler) {
      const entry = { handler }
      this._rpc.set(name, entry)
      return () => {
        if (this._rpc.get(name) === entry) this._rpc.delete(name)
      }
    },
    defineTool(spec) {
      return { ...spec }
    },
    registerTool(_ctx, tool) {
      this._tools.push(tool)
      return () => removeOnce(this._tools, tool)
    },
    _rpc: registration.rpc,
    _tools: registration.tools,
  }
}

const harness = makeHarness()
const fsFacade = facadeFs()
const subprocessFacade = facadeSubprocess()
const effectDisposers = []
const hostContext = {
  get(name) {
    return {
      fs: fsFacade,
      settings: { prepareDocument: async () => path.join(homePath, 'settings.yaml') },
      sandboxPolicy: { mode: 'adapter-controlled', workspaceRoot: workspacePath },
      subprocess: subprocessFacade,
    }[name]
  },
  effect(callback) {
    const disposer = callback()
    if (typeof disposer === 'function') effectDisposers.push(disposer)
    return disposer
  },
}

function makeClientBridges() {
  const styles = {
    insert(value) {
      const entry = { value }
      registration.styles.push(entry)
      const disposer = () => removeOnce(registration.styles, entry)
      effectDisposers.push(disposer)
      return disposer
    },
  }
  const slots = {
    inject(name, callback) {
      const registrationEntry = { name, kind: 'inject' }
      registration.ui.push(registrationEntry)
      const disposer = callback()
      const cleanup = () => {
        removeOnce(registration.ui, registrationEntry)
        if (typeof disposer === 'function') disposer()
      }
      effectDisposers.push(cleanup)
      return cleanup
    },
    register(descriptor, factory) {
      const entry = { name: descriptor.id || descriptor.name, descriptor, factory, kind: 'register' }
      registration.ui.push(entry)
      return () => removeOnce(registration.ui, entry)
    },
  }
  const React = {
    createElement: (...value) => ({ value }),
    useState: (value) => [value, () => {}],
    useEffect: () => {},
  }
  const host = { call: async () => ({ error: 'host bridge not invoked during mount probe' }) }
  return { styles, slots, React, host }
}

async function readSource(sourcePath) {
  return fs.readFile(sourcePath, 'utf8')
}

function counts() {
  return { rpc: registration.rpc.size, tools: registration.tools.length, ui: registration.ui.length, styles: registration.styles.length }
}

function normalizeError(error) {
  return { code: error && error.code ? error.code : 'PLUGIN_ERROR', message: String(error && error.message ? error.message : error) }
}

async function invokeRpc(requestId, operation, payload) {
  const entry = registration.rpc.get(operation)
  if (!entry) return { request_id: requestId, kind: 'rpc', operation, status: 'denied', error: { code: 'ADAPTER_UNKNOWN_RPC', message: operation } }
  try {
    return { request_id: requestId, kind: 'rpc', operation, status: 'completed', value: await entry.handler(payload) }
  } catch (error) {
    return { request_id: requestId, kind: 'rpc', operation, status: 'denied', error: normalizeError(error) }
  }
}

async function invokeTool(requestId, payload) {
  const tool = registration.tools.find((item) => item.name === 'dsh_config_migrate')
  if (!tool) return { request_id: requestId, kind: 'tool', operation: 'dsh_config_migrate', status: 'denied', error: { code: 'ADAPTER_UNKNOWN_TOOL', message: 'dsh_config_migrate' } }
  try {
    return { request_id: requestId, kind: 'tool', operation: tool.name, status: 'completed', value: await tool.execute(payload, { requestId }) }
  } catch (error) {
    return { request_id: requestId, kind: 'tool', operation: tool.name, status: 'denied', error: normalizeError(error) }
  }
}

async function main() {
  const hostSource = await readSource(hostPath)
  const clientSource = await readSource(clientPath)
  const hostFactory = new Function('harness', hostSource)
  const hostModule = hostFactory(harness)
  await hostModule.apply(hostContext)

  const clientBridges = makeClientBridges()
  const clientFactory = new Function('styles', 'React', 'host', clientSource)
  const clientModule = clientFactory(clientBridges.styles, clientBridges.React, clientBridges.host)
  const clientContext = {
    get(name) {
      return name === 'slots' ? clientBridges.slots : undefined
    },
    effect(callback) {
      const disposer = callback()
      if (typeof disposer === 'function') effectDisposers.push(disposer)
      return disposer
    },
  }
  await clientModule.apply(clientContext)

  await new Promise((resolve) => setTimeout(resolve, 20))
  const beforeDispose = counts()
  const operations = []
  operations.push(await invokeRpc('rpc-status-1', 'config/status', { home: homePath }))
  operations.push(await invokeRpc('rpc-export-deny-1', 'config/export', {
    home: homePath,
    path: path.join(workspacePath, 'dsh-config-export.json'),
    password: 'fixture-password-only',
  }))
  operations.push(await invokeRpc('rpc-import-escape-1', 'config/import', {
    home: homePath,
    path: path.join(caseRoot, '..', 'outside-import.json'),
  }))
  operations.push(await invokeRpc('rpc-import-write-deny-1', 'config/import', {
    home: homePath,
    path: path.join(workspacePath, 'import-bundle.json'),
  }))
  operations.push(await invokeTool('tool-export-deny-1', {
    action: 'export',
    home: homePath,
    path: path.join(workspacePath, 'tool-export.json'),
  }))
  operations.push(await invokeRpc('rpc-unknown-1', 'future/config.v1', {}))

  let negativeSubprocess = null
  try {
    subprocessFacade.spawn({ argv: ['python', '-c', 'print(1)'], cwd: caseRoot, shell: true, stdio: { stdin: { data: '' } } })
  } catch (error) {
    negativeSubprocess = normalizeError(error)
  }

  const afterCalls = counts()
  while (effectDisposers.length) {
    const disposer = effectDisposers.pop()
    try { disposer() } catch (_) { /* evidence records remaining registrations below */ }
  }
  const afterDispose = counts()

  process.stdout.write(JSON.stringify({
    schema: 'zworkbench-dsh-config-migrate-runtime-seam/v1',
    plugin_contract: 'dsh.plugin.host/client',
    operations,
    registrations: { before_dispose: beforeDispose, after_calls: afterCalls, after_dispose: afterDispose },
    write_attempts: writeAttempts,
    subprocess: {
      requests: subprocessRequests,
      accepted_count: subprocessRequests.filter((item) => item.decision === 'allow').length,
      denied_count: subprocessRequests.filter((item) => item.decision === 'deny').length,
      negative_probe: negativeSubprocess,
    },
    paths: {
      case_root: caseRoot,
      home: homePath,
      workspace: workspacePath,
      migration_state: path.join(workspacePath, '.dshmig-state.json'),
    },
  }))
}

main().catch((error) => {
  process.stderr.write(`${error && error.stack ? error.stack : error}\n`)
  process.exitCode = 1
})
