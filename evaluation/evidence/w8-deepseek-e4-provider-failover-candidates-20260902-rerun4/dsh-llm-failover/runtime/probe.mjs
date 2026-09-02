// Generated case-local official seam probe for dsh-llm-failover.
const ENTRY = "file:///Users/bilibili/Documents/workspace/github/jununfly/ZWorkbench/evaluation/evidence/w8-deepseek-e4-provider-failover-candidates-20260902-rerun4/dsh-llm-failover/candidate-source/lib/index.js";
const CANDIDATE = "dsh-llm-failover";
const originalStdoutWrite = process.stdout.write.bind(process.stdout);
const logs = [];
console.log = (...args) => logs.push({ level: 'log', message: args.map(String).join(' ') });
console.warn = (...args) => logs.push({ level: 'warn', message: args.map(String).join(' ') });
console.error = (...args) => logs.push({ level: 'error', message: args.map(String).join(' ') });

const events = [];
const sessionMessages = [];
const disposers = [];
const listeners = new Map();
const registrations = { rpc: 0, projection: 0 };
const settingsState = {
  enabled: true,
  providers: [{ provider: 'primary', model: 'model-a' }, { provider: 'secondary', model: 'model-b' }],
  fallbackAfterRetries: 1,
  cooldownMs: 60000,
};
const settings = {
  register: (_ns, _schema, options) => {
    const scope = {
      get: () => options?.base ?? settingsState,
      watch: () => () => {},
    };
    return scope;
  },
  describe: () => [{ ns: 'llm-failover', revision: 1 }],
  replace: async (_ns, value) => Object.assign(settingsState, value),
};
const connection = {
  rpc: { handle: () => { registrations.rpc += 1; return () => {}; } },
};
const sessionProjections = {
  register: () => { registrations.projection += 1; return () => {}; },
};
const agent = {
  id: 'agent-e4',
  session: {
    requestContext: () => ({ provider: 'primary', model: 'model-a' }),
    append: (...args) => sessionMessages.push(args),
  },
};
const ctx = {
  on: (event, callback) => { listeners.set(event, callback); return () => listeners.delete(event); },
  emit: (event, payload) => events.push({ event, payload }),
  get: () => undefined,
  inject: (deps, callback) => {
    const key = deps.join(',');
    if (key === 'settings') callback({ settings });
    else if (key === 'connection,settings') callback({ connection, settings });
    else if (key === 'sessionProjections') callback({ sessionProjections });
  },
  effect: (callback) => { const cleanup = callback(); if (typeof cleanup === 'function') disposers.push(cleanup); },
  logger: { info: (...args) => logs.push({ level: 'info', message: args.map(String).join(' ') }), warn: (...args) => logs.push({ level: 'warn', message: args.map(String).join(' ') }), error: (...args) => logs.push({ level: 'error', message: args.map(String).join(' ') }) },
  llm: { stream: async function*() { yield { type: 'finish', reason: { kind: 'stop' } }; } },
};

const plugin = await import(ENTRY);
const config = CANDIDATE === 'dsh-model-failover'
  ? { enabled: true, fallbacks: [{ provider: 'secondary', model: 'model-b' }], tripCodes: ['RATE_LIMIT'], modelCircuitThreshold: 1, modelCooldownMs: 60000, platformCircuitThreshold: 2, platformCooldownMs: 120000, burstWindowMs: 300000, enableProbe: false, probeMaxTokens: 8, stripReasoningEffort: true, notifyUser: true }
  : { enabled: true, providers: [{ provider: 'primary', model: 'model-a' }, { provider: 'secondary', model: 'model-b' }], fallbackAfterRetries: 1, cooldownMs: 60000 };
plugin.apply(ctx, config);

const requestListener = listeners.get('agent/request');
const errorListener = listeners.get('agent/request-error');
if (!requestListener || !errorListener) throw new Error('candidate did not register both request seams');
const signal = new AbortController().signal;
const primary = { provider: 'primary', model: 'model-a', reasoningEffort: 'high', maxTokens: 256 };
const route = async (base) => requestListener({ agent, turn: 1, step: 0, signal }, async () => base);
const fail = async (provider) => errorListener({ agent, turn: 1, step: 0, provider, failure: { code: 'RATE_LIMIT', message: 'fixture rate limit' }, retryPolicy: undefined, signal }, async () => ({ kind: 'terminal' }));

const first = await route(primary);
await fail(first.provider);
const second = await route(primary);
await fail(second.provider);
const third = await route(primary);
const fourth = await route(third);
const cleanupCount = disposers.length;
for (const cleanup of disposers.reverse()) cleanup();
disposers.length = 0;

const output = {
  schema: 'zworkbench-w8-deepseek-e4-candidate-probe/v1',
  candidate: CANDIDATE,
  routes: [first, second, third, fourth],
  events,
  session_messages: sessionMessages.map((args) => ({ type: args[0], message: args[1]?.content?.[0]?.text ?? null })),
  logs,
  registrations,
  candidate_owned_durable_records: [],
  request_listener_registered: listeners.has('agent/request'),
  request_error_listener_registered: listeners.has('agent/request-error'),
  cleanup_callbacks_invoked: cleanupCount,
  cleanup_completed: cleanupCount === 0 || CANDIDATE === 'dsh-model-failover',
};
originalStdoutWrite(JSON.stringify(output));
