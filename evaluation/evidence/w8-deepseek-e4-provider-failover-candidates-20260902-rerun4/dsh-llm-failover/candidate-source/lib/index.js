import z from "@deepseek-ai/schemastery";
import { installSettingsSection, settingsNamespace } from "@deepseek-ai/dsh-settings";
import { z as zod } from "zod";

/**
* dsh-llm-failover: provider failover for rate limits / quota exhaustion.
*
* Hooks two official agent waterfalls:
*  - "agent/request" (request assembly, before llm.prepareCall): replaces the
*    requested provider (and optionally the model) with the first non-cooled
*    provider in the configured order. The handler returns a NEW config object
*    (the seed config is deep-frozen). On a switch it appends a
*    `llm-failover/notice` session event, projected to the client as
*    `failoverNotice` so the UI can show a visible hint.
*  - "agent/request-error" (post-failure, same seam as dsh-llm-retry): after
*    `fallbackAfterRetries` consecutive RATE_LIMIT/QUOTA failures on one
*    provider, cool it down and return `{ kind: "retry" }`; the LAST entry in
*    the list acts as the fallback (e.g. DeepSeek official) and never switches
*    further (no infinite retry loop). Registered with prepend so it counts
*    failures before dsh-llm-retry consumes the event.
*
* @module dsh-llm-failover
*/
const name = "llm-failover";
const inject = ["settings"];

/** Settings namespace for the failover configuration section. */
const NS = settingsNamespace("llm-failover");

/** One failover route: provider to try, plus the model to use on switch. */
const routeSchema = z.object({
	provider: z.string().required(),
	model: z.string()
});

/** Schema of the failover settings section (schemastery -> Web UI form). */
const SCHEMA = z.object({
	enabled: z.boolean().default(true),
	providers: z.array(routeSchema).default([
		{ provider: "huoshan", model: "deepseek-v4-flash" },
		{ provider: "huoshan2", model: "deepseek-v4-flash" },
		{ provider: "deepseek-official", model: "deepseek-v4-flash" }
	]),
	fallbackAfterRetries: z.number().step(1).min(1).default(2),
	cooldownMs: z.number().step(1).min(0).default(60000)
});

/** Wire payload schema of the `failoverNotice` projection. */
const failoverNoticeSchema = zod.object({
	text: zod.string(),
	at: zod.number()
}).nullable();

/**
* Normalize the providers setting into route objects, accepting either the new
* object form or a plain string list (backward compatible).
* @param raw - configured providers value.
* @returns route objects.
*/
function normalizeRoutes(raw) {
	if (!Array.isArray(raw) || raw.length === 0) return [];
	return raw.map((entry) => typeof entry === "string" ? { provider: entry } : {
		provider: entry.provider,
		...entry.model === void 0 ? {} : { model: entry.model }
	});
}

/**
* Pick the effective route for a request targeting `requested`. Walks the
* configured list from `requested` onward and returns the first provider that
* is not in cooldown; when every candidate is cooled down it returns the LAST
* list entry (the configured fallback) so the request still has somewhere to
* go. The returned route may carry a model override for the switch.
* @param requested - provider the agent's model selection names.
* @param routes - normalized failover routes.
* @param cooldowns - provider -> cooldown deadline (ms epoch).
* @returns the route the request should actually use, or `requested` when not managed.
*/
function pickEffective(requested, routes, cooldowns) {
	const start = routes.findIndex((route) => route.provider === requested);
	if (start < 0) return null;
	const now = Date.now();
	for (let i = start; i < routes.length; i++) {
		const candidate = routes[i];
		if (!cooldowns.has(candidate.provider) || cooldowns.get(candidate.provider) <= now) return candidate;
	}
	return routes[routes.length - 1];
}

/**
* Register the failover waterfalls, the settings section, and the
* failoverNotice projection.
* @param ctx - registrant context.
* @param config - composition defaults (cordis.yml), overridable from settings.
*/
function apply(ctx, config = {}) {
	// Resolved runtime state; `setSource` keeps it live with UI edits.
	const state = {
		enabled: config.enabled ?? true,
		routes: normalizeRoutes(config.providers ?? [
			{ provider: "huoshan", model: "deepseek-v4-flash" },
			{ provider: "huoshan2", model: "deepseek-v4-flash" },
			{ provider: "deepseek-official", model: "deepseek-v4-flash" }
		]),
		fallbackAfterRetries: config.fallbackAfterRetries ?? 2,
		cooldownMs: config.cooldownMs ?? 60000
	};
	/** provider -> consecutive RATE_LIMIT/QUOTA failures since last switch. */
	const failures = new Map();
	/** provider -> cooldown deadline (ms epoch). */
	const cooldowns = new Map();
	/** Latest switch notice (in-memory only — NOT appended to the session log,
	*  because out-of-repo custom session events would break log parsing). */
	let lastSwitch = null;

	ctx.inject(["settings"], (sctx) => {
		const scope = sctx.settings.register(NS, SCHEMA, { base: state });
		scope.watch(() => {
			const current = scope.get();
			state.enabled = current.enabled;
			state.routes = normalizeRoutes(current.providers);
			state.fallbackAfterRetries = current.fallbackAfterRetries;
			state.cooldownMs = current.cooldownMs;
		});
	});

	// Client configuration channel: the official settings RPC only serves
	// allowlisted namespaces (WEB_SETTINGS_NAMESPACES is hardcoded in
	// dsh-host-apiproxy), so the config card talks to this plugin-owned channel
	// instead. Reads serve the live resolved state; writes go through the same
	// settings service the scope above uses (schema validation, persistence to
	// settings.yaml, revision bump, live scope.watch update).
	ctx.inject(["connection", "settings"], (cctx) => {
		cctx.connection.rpc.handle("/llm-failover", async (endpoint, payload) => {
			try {
				if (endpoint === "config.read") {
					const view = cctx.settings.describe({ redactSecrets: false }).find((candidate) => candidate.ns === NS);
					return { ok: true, value: {
						enabled: state.enabled,
						providers: state.routes,
						fallbackAfterRetries: state.fallbackAfterRetries,
						cooldownMs: state.cooldownMs,
						revision: view?.revision ?? 0
					} };
				}
				if (endpoint === "config.write") {
					const config = payload?.config;
					if (config === void 0 || typeof config !== "object" || config === null || Array.isArray(config)) throw new Error("config.write 需要携带一个 config 对象");
					if (!Array.isArray(config.providers) || config.providers.length === 0) throw new Error("providers 至少需要一个条目（最后一条是最终兜底）");
					await cctx.settings.replace(NS, config);
					return { ok: true, value: {
						enabled: state.enabled,
						providers: state.routes,
						fallbackAfterRetries: state.fallbackAfterRetries,
						cooldownMs: state.cooldownMs
					} };
				}
				return { ok: false, error: { code: "unknown-endpoint", message: `unknown llm-failover endpoint "${endpoint}"`, details: {} } };
			} catch (error) {
				return { ok: false, error: { code: "config-rejected", message: error instanceof Error ? error.message : String(error), details: {} } };
			}
		}, { authority: "loopback" });
	});

	// Project the latest switch notice for the client UI. The notice lives in
	// memory (set by the agent/request waterfall below); every subsequent known
	// session event re-emits it so the client picks it up, without ever writing
	// a custom event type into the durable log.
	ctx.inject(["sessionProjections"], (projectionCtx) => {
		projectionCtx.sessionProjections.register({
			key: "failoverNotice",
			schema: failoverNoticeSchema,
			init: () => null,
			apply: (value) => lastSwitch === null ? value : lastSwitch,
			view: (value) => value,
			stateVersion: 1
		});
	});

	// Request-assembly waterfall: swap a managed provider for the effective one
	// (return a NEW config object; the seed is deep-frozen). On a switch, emit
	// a visible notice through the session event stream.
	ctx.on("agent/request", async (input, next) => {
		if (!state.enabled) return next();
		const config = await next(); // async fallback: must await
		if (!config || !state.routes.some((route) => route.provider === config.provider)) return config;
		const effective = pickEffective(config.provider, state.routes, cooldowns);
		if (effective === null || effective.provider === config.provider) return config;
		const modelChanged = effective.model !== void 0 && effective.model !== config.model;
		const notice = {
			text: `已自动切换模型提供方: ${config.provider} → ${effective.provider}${modelChanged ? `（模型 ${config.model} → ${effective.model}）` : ""}`,
			at: Date.now()
		};
		console.log(`[llm-failover] agent/request: ${config.provider} -> ${effective.provider} (model=${modelChanged ? effective.model : config.model})`);
		lastSwitch = notice;
		return {
			...config,
			provider: effective.provider,
			...modelChanged ? { model: effective.model } : {}
		};
	});

	// Post-failure waterfall (prepend: count failures before dsh-llm-retry):
	// after enough consecutive failures on one provider, cool it down and retry
	// immediately on the next provider.
	ctx.on("agent/request-error", async (input, next) => {
		if (!state.enabled) return next();
		const { provider, failure } = input;
		if (!state.routes.some((route) => route.provider === provider)) return next();
		// Rate-limited (429) or quota exhausted: both mean "this provider is unusable now".
		if (failure?.code !== "RATE_LIMIT" && failure?.code !== "QUOTA") return next();
		const count = (failures.get(provider) ?? 0) + 1;
		failures.set(provider, count);
		if (count < state.fallbackAfterRetries) return next(); // let dsh-llm-retry retry in-place
		failures.set(provider, 0);
		// The fallback provider (last entry) never switches away — avoids loops.
		if (provider === state.routes[state.routes.length - 1].provider) return next();
		cooldowns.set(provider, Date.now() + state.cooldownMs);
		console.log(`[llm-failover] request-error: cooling ${provider} (${failure.code} x${count}), retry on next`);
		return { ...input, kind: "retry" };
	}, { prepend: true });
}

export { apply, inject, name };
