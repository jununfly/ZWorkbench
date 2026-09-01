# W8 DeepSeek C3/C4 fixture

This directory contains the loopback-only Chat Completions provider used by
the DeepSeek ACP parity runner. The runner intentionally reuses the exact
`w7-codex-c3-c4/effect-sink.py` so the durable effect semantics are not copied
or silently changed between candidates.

The provider emits one deterministic `bash` tool call, accepts a tool result,
and then emits `fixture-ok`. It can delay the first model response, the
case-local tool command, or the post-tool response so the runner can inject
provider, tool, and process interruption faults. An explicit `RETRY_TOOL`
marker takes precedence over prior tool-result history and emits the bounded
retry tool call. It never contacts a real Provider and has no external side
effect.

This is an acceptance/evaluation fixture, not ZWorkbench production code. A
pass is reported as `pass-with-composition`; it does not prove that DeepSeek
owns the W6 schedule, effect, approval, or replay contracts natively.
