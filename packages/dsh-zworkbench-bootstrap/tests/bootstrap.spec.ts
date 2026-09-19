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

    apply(ctx)
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
})
