/**
 * Package-owned invariant companion for `@deepseek-ai/dsh-zworkbench-bootstrap`.
 * @module @deepseek-ai/dsh-zworkbench-bootstrap/invariant
 */

import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@deepseek-ai/dsh-zworkbench-bootstrap'

/** Cordis companion plugin name. */
export const name = 'zworkbench-bootstrap-invariant'
/** Service required before the companion can register. */
export const inject = ['invariants']

/**
 * No runtime invariant: the process-level JSONL handshake is observed by the
 * external ZWorkbench owner, while this package owns no mutable in-tree relation.
 */
const install: InvariantInstaller = () => {}

/**
 * Register this package's invariant companion.
 * @param ctx - Cordis context carrying the invariant service.
 * @returns the installed registration's disposer after setup succeeds.
 */
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
