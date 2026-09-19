# `@deepseek-ai/dsh-zworkbench-bootstrap`

English | [中文](README.zh.md)

The ZWorkbench bootstrap bundle. [`cordis.patch.yml`](cordis.patch.yml) mounts one process-level plugin over [`dsh-base`](../base/README.md). The plugin creates an empty DSH Session, emits `bootstrap.started` and `bootstrap.ready` as JSONL records under `zworkbench.dsh.bootstrap/v1`, and requests the launcher's bounded exit after the complete Loader tree settles. `ZWORKBENCH_RUN_ID` and `ZWORKBENCH_DSH_PROFILE` are launcher-owned identity inputs; missing or blank values fail before a partial handshake. The bundle creates no Agent, sends no Provider request, and prints no task output, so it is a dedicated external-runtime handshake rather than a variant of [`dsh-headless`](../headless/README.md).

The shipped `zworkbench-bootstrap` profile in [`apps/cli`](../../../apps/cli/README.md) composes `dsh-base` and this bundle. The profile is intended for the ZWorkbench artifact adapter, which validates the resulting JSONL and owns the parent Run. The DSH Session remains DSH-owned; the bundle does not write ZWorkbench state or interpret the owner's database.

## Model Experience

None, as this process-level handshake creates no model request or model-visible content.

#### KV Cache effect

None directly; the bundle does not assemble a model request.

## Known Limitations and Deferred Work

- **The handshake is not a Worker protocol** — Worker version, capability, process-tree, and Codex identity exchange belong to the later ZWorkbench H2 bridge.
- **The profile is not a task runner** — callers that need an Agent and final task text must use `dsh-headless` or another explicitly composed profile.
- **The session is empty** — this H1 Session proves DSH ownership and identity correlation, but it does not represent a completed coding task.
