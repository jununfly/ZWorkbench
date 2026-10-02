import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { internals, apply, BOOTSTRAP_SCHEMA } from '../src/index.ts'

const originalEnvironment = {
  run: process.env.ZWORKBENCH_RUN_ID,
  profile: process.env.ZWORKBENCH_DSH_PROFILE,
}
const originalInternals = { ...internals }

afterEach(() => {
  if (originalEnvironment.run === undefined) delete process.env.ZWORKBENCH_RUN_ID
  else process.env.ZWORKBENCH_RUN_ID = originalEnvironment.run
  if (originalEnvironment.profile === undefined) delete process.env.ZWORKBENCH_DSH_PROFILE
  else process.env.ZWORKBENCH_DSH_PROFILE = originalEnvironment.profile
  Object.assign(internals, originalInternals)
})

/** Wait for the bootstrap's bounded asynchronous settle callback. */
async function tick(): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, 0))
}

describe('zworkbench bootstrap bundle', () => {
  it('emits started then ready with one DSH session identity and exits after flush', async () => {
    process.env.ZWORKBENCH_RUN_ID = 'parent-run-1'
    process.env.ZWORKBENCH_DSH_PROFILE = 'zworkbench-bootstrap'
    let output = ''
    const exits: number[] = []
    internals.stdout = { write: chunk => { output += chunk; return true } }
    internals.stderr = { write: () => true }
    const flushed: unknown[] = []
    const session = { id: 'dsh-session-1' }
    const ctx = new Context()
    ctx.provide('appExit', (code: number) => { exits.push(code) })
    ctx.provide('sessions', {
      create: () => session,
      flush: async (value: unknown) => { flushed.push(value) },
    } as never)
    ctx.provide('loader', { await: async () => {} } as never)

    const disposer = apply(ctx)
    expect(typeof disposer).toBe('function')
    await tick()

    const messages = output.trimEnd().split('\n').map(line => JSON.parse(line) as Record<string, unknown>)
    expect(messages).toHaveLength(2)
    expect(messages.map(message => message.message_type)).toEqual(['bootstrap.started', 'bootstrap.ready'])
    expect(messages.every(message => message.schema === BOOTSTRAP_SCHEMA)).toBe(true)
    expect(messages[0]?.identity).toEqual(messages[1]?.identity)
    expect((messages[0]?.identity as Record<string, unknown>).parent_run_id).toBe('parent-run-1')
    expect((messages[0]?.payload as Record<string, unknown>).profile_id).toBe('zworkbench-bootstrap')
    expect(exits).toEqual([0])
    expect(flushed).toEqual([session])
    await ctx.fiber.dispose()
  })

  it('fails before emitting a partial handshake when the launcher identity is absent', () => {
    delete process.env.ZWORKBENCH_RUN_ID
    process.env.ZWORKBENCH_DSH_PROFILE = 'zworkbench-bootstrap'
    const ctx = new Context()
    ctx.provide('appExit', () => {})
    ctx.provide('sessions', { create: () => ({}) } as never)
    expect(() => apply(ctx)).toThrow('ZWORKBENCH_RUN_ID must be set')
  })

  it('returns a Cordis disposer that does not delete the durable Session (AGENTS §4)', async () => {
    process.env.ZWORKBENCH_RUN_ID = 'parent-run-2'
    process.env.ZWORKBENCH_DSH_PROFILE = 'zworkbench-bootstrap'
    let output = ''
    const exits: number[] = []
    internals.stdout = { write: chunk => { output += chunk; return true } }
    internals.stderr = { write: () => true }
    const flushed: unknown[] = []
    const removed: string[] = []
    const session = { id: 'dsh-session-2' }
    const ctx = new Context()
    ctx.provide('appExit', (code: number) => { exits.push(code) })
    ctx.provide('sessions', {
      create: () => session,
      flush: async (value: unknown) => { flushed.push(value) },
      // a real SessionStore removes the in-process entry on fiber dispose; the
      // bootstrap must never delete the durable Session itself.
      delete: (id: string) => { removed.push(id) },
    } as never)
    ctx.provide('loader', { await: async () => {} } as never)

    const disposer = apply(ctx)
    expect(typeof disposer).toBe('function')
    await tick()

    // dispose the plugin fiber; the returned disposer must run without deleting
    // the flushed (durable) Session, whose residual owner is the external runtime.
    disposer()
    expect(removed).toEqual([])
    expect(flushed).toEqual([session])
    expect(exits).toEqual([0])
  })
})
