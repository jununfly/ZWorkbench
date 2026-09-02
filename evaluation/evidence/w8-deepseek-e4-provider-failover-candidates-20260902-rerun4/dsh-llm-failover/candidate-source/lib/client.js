window.__ModuleLoader__.load({
	id: "dsh-llm-failover",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		let react_jsx_runtime = require("react/jsx-runtime");
		let react = require("react");

		// Failover notice bar: renders in the composer dock when the host has
		// switched providers (projection `failoverNotice`), auto-dismisses after
		// a few seconds or when the user clicks it.
		const css = ".lXshSW_notice{box-sizing:border-box;width:calc(100% - var(--dsh-composer-side-clearance) - var(--dsh-composer-side-clearance) - var(--dsh-composer-dock-inset) - var(--dsh-composer-dock-inset));max-width:calc(var(--dsh-composer-card-max-width) - var(--dsh-composer-dock-inset) - var(--dsh-composer-dock-inset));margin:0 auto;padding:6px 12px;border:1px solid var(--dsw-alias-state-warn-border);background:var(--dsw-specific-tip);border-radius:10px;flex:none;color:var(--dsw-alias-label-secondary);font-size:12px;line-height:18px;display:flex;align-items:center;gap:8px;cursor:pointer}";
		const tagId = "dsh-llm-failover/notice.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "dsh-llm-failover";
			tag.dataset.pluginCss = tagId;
			tag.textContent = css;
			document.head.appendChild(tag);
		}

		// Configuration card: renders inside Settings → Plugins → "Plugin
		// configuration". The official settings RPC refuses third-party
		// namespaces (hardcoded WEB_SETTINGS_NAMESPACES), so the card reads and
		// writes through the plugin-owned `/llm-failover` RPC channel instead.
		const css2 = ".r7K2fQ_card{border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-module);border-radius:12px;padding:16px;flex-direction:column;gap:12px;display:flex}.r7K2fQ_head{flex-direction:column;gap:4px;display:flex}.r7K2fQ_title{margin:0;font-size:15px;font-weight:600;color:var(--dsw-alias-label-primary)}.r7K2fQ_desc{color:var(--dsw-alias-label-tertiary);margin:0;font-size:12px;line-height:18px}.r7K2fQ_field{flex-direction:column;gap:6px;display:flex}.r7K2fQ_label{color:var(--dsw-alias-label-primary);font-size:13px;font-weight:500;line-height:1.5}.r7K2fQ_input{border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-3);height:34px;font:inherit;color:var(--dsw-alias-label-primary);border-radius:8px;padding:0 12px;font-size:13px;line-height:1.5;min-width:0}.r7K2fQ_input:focus-visible{border-color:var(--dsw-alias-brand-primary);outline:none}.r7K2fQ_check{align-items:center;gap:8px;display:flex}.r7K2fQ_checkbox{accent-color:var(--dsw-alias-brand-primary);width:16px;height:16px;margin:0;cursor:pointer}.r7K2fQ_checkbox:disabled{cursor:default}.r7K2fQ_route{align-items:center;gap:8px;display:flex}.r7K2fQ_routeInput{flex:1;min-width:0}.r7K2fQ_modelInput{flex:1;min-width:0}.r7K2fQ_remove{font:inherit;flex:none;color:var(--dsw-alias-label-secondary);cursor:pointer;background:0 0;border:none;padding:4px 6px;font-size:12px;line-height:1.5}.r7K2fQ_remove:hover:not(:disabled){color:var(--dsw-alias-label-primary)}.r7K2fQ_add{font:inherit;flex:none;color:var(--dsw-alias-label-secondary);cursor:pointer;background:0 0;border:none;padding:0;font-size:12px;line-height:1.5;align-self:flex-start}.r7K2fQ_add:hover{color:var(--dsw-alias-label-primary)}.r7K2fQ_hint{color:var(--dsw-alias-label-tertiary);margin:0;font-size:12px;line-height:1.5}.r7K2fQ_actions{align-items:center;gap:8px;display:flex}.r7K2fQ_btn{font:inherit;cursor:pointer;border-radius:8px;padding:6px 14px;font-size:13px;line-height:1.5;border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-3);color:var(--dsw-alias-label-primary)}.r7K2fQ_btn:disabled{cursor:default;opacity:.6}.r7K2fQ_primary{background:var(--dsw-alias-brand-primary);border-color:transparent;color:var(--dsw-alias-bg-layer-1)}.r7K2fQ_err{color:var(--dsw-alias-state-error-primary);margin:0;font-size:12px;line-height:18px}.r7K2fQ_loading{color:var(--dsw-alias-label-tertiary);margin:0;font-size:13px}";
		const tagId2 = "dsh-llm-failover/config.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId2) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "dsh-llm-failover";
			tag.dataset.pluginCss = tagId2;
			tag.textContent = css2;
			document.head.appendChild(tag);
		}

		const NS = "llm-failover";
		const zh = {
			"notice.dismiss": "关闭提示",
			"card.title": "LLM 故障转移（429 自动切换）",
			"card.desc": "按顺序尝试这些提供方：连续失败指定次数后冷却当前提供方并自动切换；列表最后一条是最终兜底，永远不会被切走。修改会写入 settings.yaml。",
			"card.enabled": "启用自动切换",
			"card.providers": "提供方顺序",
			"card.provider": "提供方",
			"card.model": "模型（可留空，留空则沿用原模型）",
			"card.addProvider": "添加提供方",
			"card.removeProvider": "移除",
			"card.retries": "切换前连续失败次数",
			"card.retriesHint": "同一提供方连续出现多少次限流/配额错误后冷却并切换（默认 2）",
			"card.cooldown": "冷却时长（毫秒）",
			"card.cooldownHint": "冷却期间该提供方直接跳过，到期自动恢复（默认 60000）",
			"card.save": "保存",
			"card.saving": "保存中…",
			"card.discard": "放弃修改",
			"card.loading": "加载配置中…",
			"card.readFailed": "读取配置失败：{msg}",
			"card.saveFailed": "保存失败：{msg}",
			"card.invalidProviders": "每个提供方都需要填写名称，且至少保留一条",
			"card.invalidNumber": "请输入有效数字"
		};
		const en = {
			"notice.dismiss": "Dismiss",
			"card.title": "LLM failover (429 auto-switch)",
			"card.desc": "Providers are tried in order: after the configured number of consecutive failures the current provider is cooled down and the next one is used; the last entry is the permanent fallback and is never switched away. Changes are written to settings.yaml.",
			"card.enabled": "Enable automatic failover",
			"card.providers": "Provider order",
			"card.provider": "Provider",
			"card.model": "Model (optional; empty keeps the original model)",
			"card.addProvider": "Add provider",
			"card.removeProvider": "Remove",
			"card.retries": "Consecutive failures before switching",
			"card.retriesHint": "How many rate-limit/quota failures on one provider before it is cooled down and switched (default 2)",
			"card.cooldown": "Cooldown (ms)",
			"card.cooldownHint": "While cooled down the provider is skipped; it recovers automatically (default 60000)",
			"card.save": "Save",
			"card.saving": "Saving…",
			"card.discard": "Discard",
			"card.loading": "Loading…",
			"card.readFailed": "Failed to read config: {msg}",
			"card.saveFailed": "Save failed: {msg}",
			"card.invalidProviders": "Every provider needs a name, and at least one entry must remain",
			"card.invalidNumber": "Enter a valid number"
		};

		/** Minimal uSES-compatible snapshot store for the card's config state. */
		function createSnapshotStore(initial) {
			let snapshot = initial;
			const listeners = new Set();
			return {
				getSnapshot: () => snapshot,
				subscribe: (listener) => {
					listeners.add(listener);
					return () => {
						listeners.delete(listener);
					};
				},
				set: (next) => {
					snapshot = next;
					for (const listener of [...listeners]) listener();
				}
			};
		}

		/**
		* Card controller: loads and saves the failover config over the
		* plugin-owned `/llm-failover` RPC channel, publishing every outcome into
		* the snapshot store the card reads through its `useFailoverConfig` hook.
		* @param ctx - client plugin context (provides `connection.rpc`).
		*/
		function FailoverConfigController(ctx) {
			const store = createSnapshotStore({ status: "loading", value: null, error: null });
			const call = (endpoint, payload) => ctx.get("connection").rpc.call("/llm-failover", endpoint, payload);
			const load = async () => {
				try {
					const result = await call("config.read", {});
					if (!result.ok) throw new Error(result.error?.message ?? "config.read failed");
					store.set({ status: "ready", value: result.value, error: null });
				} catch (error) {
					store.set({ status: "error", value: null, error: error instanceof Error ? error.message : String(error) });
				}
			};
			load();
			return {
				inject: () => ({
					hooks: { failoverConfig: store },
					reload: load,
					save: async (config) => {
						try {
							const result = await call("config.write", { config });
							if (!result.ok) throw new Error(result.error?.message ?? "config.write failed");
							store.set({ status: "ready", value: result.value, error: null });
							return true;
						} catch (error) {
							store.set({ status: "error", value: null, error: error instanceof Error ? error.message : String(error) });
							return false;
						}
					}
				})
			};
		}

		/** Dock adapter: shows the latest failover notice, auto-hides after 4s. */
		function FailoverNoticeDock({ useProjection, t }) {
			const notice = useProjection("failoverNotice");
			const [dismissedAt, setDismissedAt] = (0, react.useState)(null);
			const [visible, setVisible] = (0, react.useState)(false);
			const at = notice?.at ?? 0;
			(0, react.useEffect)(() => {
				if (at === 0) return;
				setVisible(true);
				const timer = setTimeout(() => setVisible(false), 4000);
				return () => clearTimeout(timer);
			}, [at]);
			if (!notice || !visible || dismissedAt === at) return null;
			return (0, react_jsx_runtime.jsx)("div", {
				className: "lXshSW_notice",
				role: "status",
				title: t("notice.dismiss"),
				onClick: () => {
					setDismissedAt(at);
				},
				children: notice.text
			});
		}

		/**
		* Config card: staged form over the controller's snapshot. Nothing here
		* writes — save is the single point where the draft becomes a settings
		* mutation on the host.
		* @param props - locale copy, the config snapshot, and the controller actions.
		* @returns the card.
		*/
		function FailoverConfigCard(props) {
			const { t } = props;
			const snap = props.useFailoverConfig((snapshot) => snapshot);
			const [draft, setDraft] = (0, react.useState)(null);
			const [localError, setLocalError] = (0, react.useState)(null);
			const [saving, setSaving] = (0, react.useState)(false);
			const dirtyRef = (0, react.useRef)(false);
			const value = snap?.status === "ready" ? snap.value : null;
			(0, react.useEffect)(() => {
				if (value === null || dirtyRef.current) return;
				setDraft(value);
			}, [value]);
			if (snap?.status === "error" && draft === null) {
				return (0, react_jsx_runtime.jsx)("div", {
					className: "r7K2fQ_card",
					children: (0, react_jsx_runtime.jsxs)("div", {
						className: "r7K2fQ_head",
						children: [(0, react_jsx_runtime.jsx)("h3", {
							className: "r7K2fQ_title",
							children: t("card.title")
						}), (0, react_jsx_runtime.jsx)("p", {
							className: "r7K2fQ_err",
							children: t("card.readFailed", { msg: snap.error })
						})]
					})
				});
			}
			if (snap?.status !== "ready" || draft === null) {
				return (0, react_jsx_runtime.jsx)("div", {
					className: "r7K2fQ_card",
					children: (0, react_jsx_runtime.jsx)("p", {
						className: "r7K2fQ_loading",
						children: t("card.loading")
					})
				});
			}
			const update = (patch) => {
				dirtyRef.current = true;
				setDraft((current) => ({ ...current, ...patch }));
			};
			const updateRoute = (index, patch) => {
				dirtyRef.current = true;
				setDraft((current) => ({
					...current,
					providers: current.providers.map((route, at) => at === index ? { ...route, ...patch } : route)
				}));
			};
			const removeRoute = (index) => {
				dirtyRef.current = true;
				setDraft((current) => ({
					...current,
					providers: current.providers.filter((_, at) => at !== index)
				}));
			};
			const addRoute = () => {
				dirtyRef.current = true;
				setDraft((current) => ({ ...current, providers: [...current.providers, { provider: "", model: "" }] }));
			};
			const onSave = async () => {
				const providers = draft.providers.map((route) => {
					const provider = route.provider.trim();
					const model = (route.model ?? "").trim();
					return { provider, ...model.length > 0 ? { model } : {} };
				});
				if (providers.length === 0 || providers.some((route) => route.provider.length === 0)) {
					setLocalError(t("card.invalidProviders"));
					return;
				}
				const fallbackAfterRetries = Math.floor(Number(draft.fallbackAfterRetries));
				const cooldownMs = Math.floor(Number(draft.cooldownMs));
				if (!Number.isFinite(fallbackAfterRetries) || fallbackAfterRetries < 1 || !Number.isFinite(cooldownMs) || cooldownMs < 0) {
					setLocalError(t("card.invalidNumber"));
					return;
				}
				setLocalError(null);
				setSaving(true);
				const ok = await props.save({
					enabled: !!draft.enabled,
					providers,
					fallbackAfterRetries,
					cooldownMs
				});
				setSaving(false);
				if (ok) dirtyRef.current = false;
			};
			const onDiscard = () => {
				dirtyRef.current = false;
				setLocalError(null);
				setDraft(value);
			};
			return (0, react_jsx_runtime.jsxs)("div", {
				className: "r7K2fQ_card",
				children: [
					(0, react_jsx_runtime.jsxs)("div", {
						className: "r7K2fQ_head",
						children: [(0, react_jsx_runtime.jsx)("h3", {
							className: "r7K2fQ_title",
							children: t("card.title")
						}), (0, react_jsx_runtime.jsx)("p", {
							className: "r7K2fQ_desc",
							children: t("card.desc")
						})]
					}),
					(0, react_jsx_runtime.jsx)("label", {
						className: "r7K2fQ_check",
						children: (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, {
							children: [(0, react_jsx_runtime.jsx)("input", {
								type: "checkbox",
								className: "r7K2fQ_checkbox",
								checked: !!draft.enabled,
								onChange: (event) => {
									update({ enabled: event.target.checked });
								}
							}), (0, react_jsx_runtime.jsx)("span", {
								className: "r7K2fQ_label",
								children: t("card.enabled")
							})]
						})
					}),
					(0, react_jsx_runtime.jsxs)("div", {
						className: "r7K2fQ_field",
						children: [
							(0, react_jsx_runtime.jsx)("span", {
								className: "r7K2fQ_label",
								children: t("card.providers")
							}),
							...(draft.providers ?? []).map((route, index) => (0, react_jsx_runtime.jsxs)("div", {
								className: "r7K2fQ_route",
								children: [
									(0, react_jsx_runtime.jsx)("input", {
										className: "r7K2fQ_input r7K2fQ_routeInput",
										placeholder: t("card.provider"),
										value: route.provider,
										onChange: (event) => {
											updateRoute(index, { provider: event.target.value });
										}
									}),
									(0, react_jsx_runtime.jsx)("input", {
										className: "r7K2fQ_input r7K2fQ_modelInput",
										placeholder: t("card.model"),
										value: route.model ?? "",
										onChange: (event) => {
											updateRoute(index, { model: event.target.value });
										}
									}),
									(0, react_jsx_runtime.jsx)("button", {
										type: "button",
										className: "r7K2fQ_remove",
										disabled: (draft.providers ?? []).length <= 1,
										onClick: () => {
											removeRoute(index);
										},
										children: t("card.removeProvider")
									})
								]
							}, index)),
							(0, react_jsx_runtime.jsx)("button", {
								type: "button",
								className: "r7K2fQ_add",
								onClick: addRoute,
								children: t("card.addProvider")
							})
						]
					}),
					(0, react_jsx_runtime.jsxs)("div", {
						className: "r7K2fQ_field",
						children: [(0, react_jsx_runtime.jsx)("label", {
							className: "r7K2fQ_label",
							htmlFor: "llm-failover-retries",
							children: t("card.retries")
						}), (0, react_jsx_runtime.jsx)("input", {
							id: "llm-failover-retries",
							className: "r7K2fQ_input",
							type: "number",
							min: 1,
							value: draft.fallbackAfterRetries,
							onChange: (event) => {
								update({ fallbackAfterRetries: event.target.value });
							}
						}), (0, react_jsx_runtime.jsx)("p", {
							className: "r7K2fQ_hint",
							children: t("card.retriesHint")
						})]
					}),
					(0, react_jsx_runtime.jsxs)("div", {
						className: "r7K2fQ_field",
						children: [(0, react_jsx_runtime.jsx)("label", {
							className: "r7K2fQ_label",
							htmlFor: "llm-failover-cooldown",
							children: t("card.cooldown")
						}), (0, react_jsx_runtime.jsx)("input", {
							id: "llm-failover-cooldown",
							className: "r7K2fQ_input",
							type: "number",
							min: 0,
							value: draft.cooldownMs,
							onChange: (event) => {
								update({ cooldownMs: event.target.value });
							}
						}), (0, react_jsx_runtime.jsx)("p", {
							className: "r7K2fQ_hint",
							children: t("card.cooldownHint")
						})]
					}),
					(snap?.status === "error" || localError !== null) && (0, react_jsx_runtime.jsx)("p", {
						className: "r7K2fQ_err",
						role: "status",
						children: snap?.status === "error" ? t("card.saveFailed", { msg: snap.error }) : localError
					}),
					(0, react_jsx_runtime.jsxs)("div", {
						className: "r7K2fQ_actions",
						children: [(0, react_jsx_runtime.jsx)("button", {
							type: "button",
							className: "r7K2fQ_btn r7K2fQ_primary",
							disabled: saving || !dirtyRef.current,
							onClick: onSave,
							children: saving ? t("card.saving") : t("card.save")
						}), (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							className: "r7K2fQ_btn",
							disabled: saving,
							onClick: onDiscard,
							children: t("card.discard")
						})]
					})
				]
			});
		}

		const inject = [
			"slots",
			"locale",
			"connection"
		];

		function apply(ctx) {
			ctx.effect(() => ctx.locale.register(NS, {
				zh,
				en
			}), "llm-failover: dictionaries");
			ctx.slots.inject("conversation.input.dock", () => ctx.slots.register({
				name: "conversation.input.dock",
				id: "failover-notice",
				order: 30,
				locale: NS
			}, FailoverNoticeDock));
			const failoverConfig = new FailoverConfigController(ctx);
			ctx.slots.inject("settings.plugin.item", function* () {
				yield ctx.slots.register({
					name: "settings.plugin.item",
					id: "llm-failover",
					order: 30,
					locale: NS,
					inject: () => failoverConfig.inject()
				}, FailoverConfigCard);
			});
		}
		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	}
});
