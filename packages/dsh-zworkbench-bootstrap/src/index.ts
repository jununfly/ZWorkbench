/**
 * @deepseek-ai/dsh-zworkbench-bootstrap — the process-level DSH identity
 * handshake consumed by ZWorkbench before later Worker capabilities mount.
 * The bundle creates an empty DSH Session, emits two JSONL records, and exits
 * after the complete profile settles. It does not create an Agent or call a
 * Provider.
 *
 * @module @deepseek-ai/dsh-zworkbench-bootstrap
 */

import { randomUUID } from 'node:crypto'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/cordis-plugin-loader'
import type {} from '@deepseek-ai/dsh-cmdline'
import { SessionId } from '@deepseek-ai/dsh-session'
import type { Session } from '@deepseek-ai/dsh-session'

/** Stable Cordis plugin name. */
export const name = 'zworkbench-bootstrap'

/** The DSH service required before an empty Session can be created. */
export const inject = ['sessions']

/** Versioned JSONL protocol consumed by ZWorkbench's DSH runtime adapter. */
export const BOOTSTRAP_SCHEMA = 'zworkbench.dsh.bootstrap/v1'

/** The two records emitted by this one-shot process. */
export type BootstrapMessageType = 'bootstrap.started' | 'bootstrap.ready'

interface BootstrapIdentity {
  parent_run_id: string
  dsh_session_id: string
}

interface BootstrapMessage {
  schema: typeof BOOTSTRAP_SCHEMA
  message_type: BootstrapMessageType
  identity: BootstrapIdentity
  payload: {
    status: 'started' | 'ready'
    profile_id: string
  }
}

/** Process streams used by tests to observe the exact protocol without a child process. */
export const internals: {
  stdout: { write(chunk: string): unknown }
  stderr: { write(chunk: string): unknown }
} = {
  stdout: process.stdout,
  stderr: process.stderr,
}

/** Read a required bridge identity without accepting an empty value. */
function requiredEnvironment(name: string): string {
  const value = process.env[name]
  if (value === undefined || value.trim() === '') {
    throw new Error(`zworkbench-bootstrap: ${name} must be set by the launching bridge`)
  }
  return value
}

/** Emit one canonical JSONL protocol record to stdout. */
function emit(message: BootstrapMessage): void {
  internals.stdout.write(JSON.stringify(message) + '\n')
}

/** Convert an asynchronous bootstrap failure into a bounded failing process. */
function fail(error: unknown, exit: (code: number) => void): void {
  internals.stderr.write(`zworkbench-bootstrap: ${error instanceof Error ? error.message : String(error)}\n`)
  exit(1)
}

/** Create and flush an empty Session, then announce the settled profile. */
async function settle(
  ctx: Context,
  session: Session,
  profileId: string,
  identity: BootstrapIdentity,
  exit: (code: number) => void,
): Promise<void> {
  await ctx.get('loader')?.await()
  const sessions = ctx.get('sessions')
  if (sessions === undefined) throw new Error('the sessions service disappeared during bootstrap')
  await sessions.flush(session)
  emit({
    schema: BOOTSTRAP_SCHEMA,
    message_type: 'bootstrap.ready',
    identity,
    payload: { status: 'ready', profile_id: profileId },
  })
  exit(0)
}

/**
 * Create the DSH Session identity and announce the two-phase bootstrap.
 * @param ctx - the profile context carrying Session, Loader, and launcher exit services.
 */
export function apply(ctx: Context): void {
  const exit = ctx.get('appExit')
  if (exit === undefined) {
    throw new Error('zworkbench-bootstrap: the launcher must provide ctx.appExit before the tree mounts')
  }
  const sessions = ctx.get('sessions')
  if (sessions === undefined) {
    throw new Error('zworkbench-bootstrap: the profile must provide the sessions service')
  }
  const identity: BootstrapIdentity = {
    parent_run_id: requiredEnvironment('ZWORKBENCH_RUN_ID'),
    dsh_session_id: `dsh-${randomUUID()}`,
  }
  const profileId = requiredEnvironment('ZWORKBENCH_DSH_PROFILE')
  const session = sessions.create(SessionId(identity.dsh_session_id), {
    meta: { cwd: process.cwd() },
  })
  emit({
    schema: BOOTSTRAP_SCHEMA,
    message_type: 'bootstrap.started',
    identity,
    payload: { status: 'started', profile_id: profileId },
  })
  void settle(ctx, session, profileId, identity, exit).catch(error => { fail(error, exit) })
}
