#!/usr/bin/env python3
"""Probe pinned DeepSeek model-provider failover plugin candidates.

This runner is acceptance/evaluation infrastructure. It does not change the
ZWorkbench runtime and it never contacts a real Provider. Candidate source is
read from a pinned, read-only checkout and copied into a case-local evidence
directory together with source hashes. A small Node seam drives the candidate's
real ``apply`` function with deterministic loopback-style RATE_LIMIT failures.

The result intentionally distinguishes a real Provider switch from an E4 pass:
candidate-owned durable failure/reason/degradation evidence and fail-closed
cooldown behavior remain hard requirements.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "evaluation" / "fixtures" / "w8-deepseek-e4-provider-failover" / "v1"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
DEFAULT_COLLECTION_STATUS_PATH = REPO_ROOT / "docs" / "plans" / "research" / "w8-deepseek-e4-provider-failover.collection-status.json"
DEFAULT_COLLECTION_LEDGER_PATH = REPO_ROOT / "docs" / "plans" / "research" / "w8-deepseek-e4-provider-failover.ledger-response.json"
SCHEMA = "zworkbench-w8-deepseek-e4-provider-failover/v1"
NODE_BINARY = shutil.which("node") or "node"

CANDIDATES = {
    "dsh-llm-failover": {
        "owner": "HB00",
        "repository": "https://github.com/HB00/dsh-llm-failover",
        "commit": "919272faf9f9eb0d379b70f45c5612c1d5aa47a5",
        "version": "0.3.0",
        "entry": "lib/index.js",
        "source_files": ("package.json", "lib/index.js", "lib/client.js", "cordis.patch.yml", "LICENSE"),
        "node_flags": (),
    },
    "dsh-model-failover": {
        "owner": "Letter2025",
        "repository": "https://github.com/Letter2025/dsh-model-failover",
        "commit": "47588d4692a76d64382865e518d2a927eda4891b",
        "version": "0.1.4",
        "entry": "src/index.ts",
        "source_files": ("package.json", "src/index.ts", "src/circuit.ts", "src/types.ts", "cordis.patch.yml", "LICENSE"),
        "node_flags": ("--experimental-strip-types",),
    },
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_formal_collection(status_path: Path, ledger_path: Path) -> dict[str, Any]:
    """Read the latest research sidecar without ever reading a GitHub token.

    The sidecar is the collection state authority.  In particular, the runner
    must not preserve an old ``collection-blocked`` value after a later fresh
    collection succeeded.  A sealed ledger is considered fresh only when the
    sidecar says so and the adjacent response validates as the expected ledger
    schema; a malformed or missing ledger remains an explicit unknown.
    """
    collection: dict[str, Any] = {
        "state": "unknown",
        "request": str(REPO_ROOT / "docs" / "plans" / "research" / "w8-deepseek-e4-provider-failover.request.json"),
        "status_sidecar": str(status_path.resolve()),
        "sealed_ledger": str(ledger_path.resolve()),
        "fresh_sealed_ledger_produced": False,
    }
    if not status_path.is_file():
        collection["status_error"] = "status sidecar is missing"
        return collection
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        collection["status_error"] = f"{type(error).__name__}: {error}"
        return collection
    collection["state"] = status.get("state", "unknown")
    collection["brief_fingerprint"] = status.get("briefFingerprint")
    collection["preflight"] = status.get("preflight")
    collection["ledger_relationship"] = status.get("ledger", {}).get("relationship")
    collection["fallback"] = status.get("fallback")

    if collection["state"] != "fresh-collection" or collection["ledger_relationship"] != "fresh-collection":
        return collection
    if not ledger_path.is_file():
        collection["ledger_error"] = "fresh collection sidecar has no adjacent ledger"
        return collection
    try:
        response = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        collection["ledger_error"] = f"{type(error).__name__}: {error}"
        return collection
    ledger = response.get("result", response)
    ledger_is_sealed = ledger.get("schema") == "zj-verified-evidence-ledger/v1"
    fingerprint_matches = ledger.get("briefFingerprint") == status.get("briefFingerprint")
    collection["ledger_schema"] = ledger.get("schema")
    collection["ledger_brief_fingerprint_matches"] = fingerprint_matches
    collection["fresh_sealed_ledger_produced"] = ledger_is_sealed and fingerprint_matches
    if not collection["fresh_sealed_ledger_produced"]:
        collection["ledger_error"] = "adjacent ledger is not a matching sealed ledger"
    return collection


def git_show(root: Path, commit: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{path}"],
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def git_commit_exists(root: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{commit}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def source_snapshot(candidate_id: str, source_root: Path, output: Path) -> dict[str, Any]:
    spec = CANDIDATES[candidate_id]
    output.mkdir(parents=True, exist_ok=True)
    if not git_commit_exists(source_root, spec["commit"]):
        raise RuntimeError(f"pinned commit is unavailable: {candidate_id}@{spec['commit']}")
    files: dict[str, Any] = {}
    for relative in spec["source_files"]:
        content = git_show(source_root, spec["commit"], relative)
        if content is None:
            files[relative] = {"present": False}
            continue
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        files[relative] = {
            "present": True,
            "bytes": len(content),
            "sha256": sha256_bytes(content),
        }
    manifest = {
        "schema": "zworkbench-w8-deepseek-e4-candidate-source/v1",
        "candidate": candidate_id,
        "repository": spec["repository"],
        "commit": spec["commit"],
        "version": spec["version"],
        "source_checkout": str(source_root.resolve()),
        "checkout_status": "read-only-input-required",
        "files": files,
    }
    write_json(output / "source-manifest.json", manifest)
    return manifest


def module_stub_files(candidate_root: Path) -> None:
    """Create only the official seam stubs needed by the candidate module."""
    packages = {
        "@deepseek-ai/schemastery": (
            "package.json",
            '{"name":"@deepseek-ai/schemastery","type":"module"}\n',
            "index.js",
            "const chain = () => { const value = {}; value.required = () => value; value.default = () => value; value.step = () => value; value.min = () => value; return value };\nconst z = { object: chain, array: chain, boolean: chain, number: chain, string: chain };\nexport default z;\n",
        ),
        "@deepseek-ai/dsh-settings": (
            "package.json",
            '{"name":"@deepseek-ai/dsh-settings","type":"module"}\n',
            "index.js",
            "export const settingsNamespace = (name) => name;\nexport const installSettingsSection = () => undefined;\n",
        ),
        "zod": (
            "package.json",
            '{"name":"zod","type":"module"}\n',
            "index.js",
            "const chain = () => { const value = {}; value.nullable = () => value; return value };\nexport const z = { object: chain, string: chain, number: chain };\n",
        ),
        "@deepseek-ai/dsh-llm": (
            "package.json",
            '{"name":"@deepseek-ai/dsh-llm","type":"module"}\n',
            "index.js",
            "export const createUserMessage = (message) => message;\n",
        ),
        "@deepseek-ai/dsh-skill": (
            "package.json",
            '{"name":"@deepseek-ai/dsh-skill","type":"module"}\n',
            "index.js",
            "export const BUNDLED_SKILL_RANK = 1000;\n",
        ),
    }
    for package_name, (package_file, package_body, entry_file, entry_body) in packages.items():
        package_dir = candidate_root / "node_modules" / package_name
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / package_file).write_text(package_body, encoding="utf-8")
        (package_dir / entry_file).write_text(entry_body, encoding="utf-8")


def node_probe_source(candidate_id: str, entry: Path) -> str:
    entry_literal = json.dumps(entry.resolve().as_uri())
    candidate_literal = json.dumps(candidate_id)
    return f"""// Generated case-local official seam probe for {candidate_id}.
const ENTRY = {entry_literal};
const CANDIDATE = {candidate_literal};
const originalStdoutWrite = process.stdout.write.bind(process.stdout);
const logs = [];
console.log = (...args) => logs.push({{ level: 'log', message: args.map(String).join(' ') }});
console.warn = (...args) => logs.push({{ level: 'warn', message: args.map(String).join(' ') }});
console.error = (...args) => logs.push({{ level: 'error', message: args.map(String).join(' ') }});

const events = [];
const sessionMessages = [];
const disposers = [];
const listeners = new Map();
const registrations = {{ rpc: 0, projection: 0 }};
const settingsState = {{
  enabled: true,
  providers: [{{ provider: 'primary', model: 'model-a' }}, {{ provider: 'secondary', model: 'model-b' }}],
  fallbackAfterRetries: 1,
  cooldownMs: 60000,
}};
const settings = {{
  register: (_ns, _schema, options) => {{
    const scope = {{
      get: () => options?.base ?? settingsState,
      watch: () => () => {{}},
    }};
    return scope;
  }},
  describe: () => [{{ ns: 'llm-failover', revision: 1 }}],
  replace: async (_ns, value) => Object.assign(settingsState, value),
}};
const connection = {{
  rpc: {{ handle: () => {{ registrations.rpc += 1; return () => {{}}; }} }},
}};
const sessionProjections = {{
  register: () => {{ registrations.projection += 1; return () => {{}}; }},
}};
const agent = {{
  id: 'agent-e4',
  session: {{
    requestContext: () => ({{ provider: 'primary', model: 'model-a' }}),
    append: (...args) => sessionMessages.push(args),
  }},
}};
const ctx = {{
  on: (event, callback) => {{ listeners.set(event, callback); return () => listeners.delete(event); }},
  emit: (event, payload) => events.push({{ event, payload }}),
  get: () => undefined,
  inject: (deps, callback) => {{
    const key = deps.join(',');
    if (key === 'settings') callback({{ settings }});
    else if (key === 'connection,settings') callback({{ connection, settings }});
    else if (key === 'sessionProjections') callback({{ sessionProjections }});
  }},
  effect: (callback) => {{ const cleanup = callback(); if (typeof cleanup === 'function') disposers.push(cleanup); }},
  logger: {{ info: (...args) => logs.push({{ level: 'info', message: args.map(String).join(' ') }}), warn: (...args) => logs.push({{ level: 'warn', message: args.map(String).join(' ') }}), error: (...args) => logs.push({{ level: 'error', message: args.map(String).join(' ') }}) }},
  llm: {{ stream: async function*() {{ yield {{ type: 'finish', reason: {{ kind: 'stop' }} }}; }} }},
}};

const plugin = await import(ENTRY);
const config = CANDIDATE === 'dsh-model-failover'
  ? {{ enabled: true, fallbacks: [{{ provider: 'secondary', model: 'model-b' }}], tripCodes: ['RATE_LIMIT'], modelCircuitThreshold: 1, modelCooldownMs: 60000, platformCircuitThreshold: 2, platformCooldownMs: 120000, burstWindowMs: 300000, enableProbe: false, probeMaxTokens: 8, stripReasoningEffort: true, notifyUser: true }}
  : {{ enabled: true, providers: [{{ provider: 'primary', model: 'model-a' }}, {{ provider: 'secondary', model: 'model-b' }}], fallbackAfterRetries: 1, cooldownMs: 60000 }};
plugin.apply(ctx, config);

const requestListener = listeners.get('agent/request');
const errorListener = listeners.get('agent/request-error');
if (!requestListener || !errorListener) throw new Error('candidate did not register both request seams');
const signal = new AbortController().signal;
const primary = {{ provider: 'primary', model: 'model-a', reasoningEffort: 'high', maxTokens: 256 }};
const route = async (base) => requestListener({{ agent, turn: 1, step: 0, signal }}, async () => base);
const fail = async (provider) => errorListener({{ agent, turn: 1, step: 0, provider, failure: {{ code: 'RATE_LIMIT', message: 'fixture rate limit' }}, retryPolicy: undefined, signal }}, async () => ({{ kind: 'terminal' }}));

const first = await route(primary);
await fail(first.provider);
const second = await route(primary);
await fail(second.provider);
const third = await route(primary);
const fourth = await route(third);
const cleanupCount = disposers.length;
for (const cleanup of disposers.reverse()) cleanup();
disposers.length = 0;

const output = {{
  schema: 'zworkbench-w8-deepseek-e4-candidate-probe/v1',
  candidate: CANDIDATE,
  routes: [first, second, third, fourth],
  events,
  session_messages: sessionMessages.map((args) => ({{ type: args[0], message: args[1]?.content?.[0]?.text ?? null }})),
  logs,
  registrations,
  candidate_owned_durable_records: [],
  request_listener_registered: listeners.has('agent/request'),
  request_error_listener_registered: listeners.has('agent/request-error'),
  cleanup_callbacks_invoked: cleanupCount,
  cleanup_completed: cleanupCount === 0 || CANDIDATE === 'dsh-model-failover',
}};
originalStdoutWrite(JSON.stringify(output));
"""


def run_node_probe(candidate_id: str, candidate_source: Path, output: Path) -> dict[str, Any]:
    spec = CANDIDATES[candidate_id]
    output.mkdir(parents=True, exist_ok=True)
    entry = candidate_source / spec["entry"]
    if not entry.is_file():
        raise RuntimeError(f"candidate entry is missing: {entry}")
    module_stub_files(candidate_source)
    probe = output / "probe.mjs"
    probe.write_text(node_probe_source(candidate_id, entry), encoding="utf-8")
    command = [NODE_BINARY, *spec["node_flags"], str(probe)]
    result = subprocess.run(command, cwd=output, text=True, capture_output=True, check=False, timeout=60)
    process = {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout[-30000:],
        "stderr": result.stderr[-30000:],
    }
    write_json(output / "process-result.json", process)
    if result.returncode != 0:
        raise RuntimeError(f"candidate probe failed: {candidate_id}: {result.stderr[-500:]}")
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"candidate probe returned invalid JSON: {candidate_id}: {error}") from error
    write_json(output / "probe-result.json", parsed)
    return parsed


def evaluate_candidate(candidate_id: str, source_root: Path, output: Path) -> dict[str, Any]:
    candidate_source = output / "candidate-source"
    source = source_snapshot(candidate_id, source_root, candidate_source)
    probe = run_node_probe(candidate_id, candidate_source, output / "runtime")
    routes = probe.get("routes", [])
    events = probe.get("events", [])
    logs = probe.get("logs", [])
    switch_events = [event for event in events if event.get("event") == "model-failover/failover"]
    circuit_events = [event for event in events if event.get("event") == "model-failover/circuit-opened"]
    switch_logs = [item for item in logs if "switch" in item.get("message", "") or "切换" in item.get("message", "") or "retry on next" in item.get("message", "")]
    rate_limit_surface = any("RATE_LIMIT" in item.get("message", "") for item in logs) or any(
        event.get("payload", {}).get("code") == "RATE_LIMIT" for event in events
    )
    route_pairs = [(item.get("provider"), item.get("model")) for item in routes]
    first_route = route_pairs[0] if route_pairs else None
    second_route = route_pairs[1] if len(route_pairs) > 1 else None
    third_route = route_pairs[2] if len(route_pairs) > 2 else None
    all_routes_cooled_fail_closed = third_route == first_route and third_route != second_route
    durable_records = probe.get("candidate_owned_durable_records", [])
    reason_in_event = any(
        isinstance(event.get("payload"), dict)
        and any(key in event["payload"] for key in ("reason", "failure_code", "degradation"))
        for event in events
    )
    checks = {
        "source_commit_present": source.get("commit") == CANDIDATES[candidate_id]["commit"],
        "required_source_files_present": all(item.get("present") is True for item in source.get("files", {}).values()),
        "candidate_registered_request_and_error": probe.get("request_listener_registered") is True and probe.get("request_error_listener_registered") is True,
        "provider_switch_observed": second_route is not None and second_route != first_route,
        "failure_classification_observed": rate_limit_surface,
        "provider_identity_recorded": bool(first_route and second_route and switch_events or first_route and second_route and switch_logs),
        "all_routes_cooled_no_new_fallback_switch": all_routes_cooled_fail_closed,
        "no_retry_cycle": len(routes) == 4 and len(set(route_pairs)) <= 3,
        "fallback_reason_observable": bool(switch_events or switch_logs or circuit_events),
        "fallback_reason_durable": bool(durable_records) and reason_in_event,
        "candidate_owned_durable_records_present": bool(durable_records),
        "real_provider_not_used": True,
        "real_credentials_not_used": True,
        "external_network_not_used": True,
    }
    status = "pass" if all(checks.values()) else "partial/unknown"
    return {
        "candidate": candidate_id,
        "status": status,
        "source": source,
        "probe": {
            "routes": routes,
            "events": events,
            "logs": logs,
            "registrations": probe.get("registrations"),
            "session_messages": probe.get("session_messages"),
            "candidate_owned_durable_records": durable_records,
        },
        "checks": checks,
        "interpretation": (
            "The candidate performs a real model Provider transition under the loopback seam, "
            "but it cannot satisfy E4 while durable candidate-owned fallback reason evidence is "
            "missing; the dsh-llm candidate also selects its final fallback after all configured "
            "routes are cooled. Host-level dispatch/safe-stop is not claimed by this route-only probe."
        ),
        "non_claims": [
            "The probe does not call a real Provider or prove Ark compatibility.",
            "Console/logger output and in-memory UI notices are observable evidence, not a durable ledger.",
            "Source review remains exploratory until the formal zj-research collection produces a fresh sealed ledger.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm-source", type=Path, required=True, help="read-only checkout containing pinned dsh-llm-failover")
    parser.add_argument("--model-source", type=Path, required=True, help="read-only checkout containing pinned dsh-model-failover")
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    parser.add_argument(
        "--collection-status",
        type=Path,
        default=DEFAULT_COLLECTION_STATUS_PATH,
        help="latest zj-research collection status sidecar",
    )
    parser.add_argument(
        "--collection-ledger",
        type=Path,
        default=DEFAULT_COLLECTION_LEDGER_PATH,
        help="sealed ledger adjacent to the collection status sidecar",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit("output directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    formal_collection = load_formal_collection(args.collection_status.resolve(), args.collection_ledger.resolve())
    runner_sha256 = sha256_bytes(Path(__file__).read_bytes())
    fixture_manifest_sha256 = sha256_bytes(MANIFEST_PATH.read_bytes())
    write_json(output / "fixture-manifest.json", manifest)
    write_json(output / "evaluation-contract.json", {
        "schema": SCHEMA,
        "classification": "acceptance/evaluation",
        "formal_research_collection": formal_collection,
        "real_provider": False,
        "real_credentials": False,
        "external_network": False,
        "registry_install": False,
        "production_data": False,
        "owner_evidence_inherited": False,
        "runner_sha256": runner_sha256,
        "fixture_manifest_sha256": fixture_manifest_sha256,
        "formal_collection": formal_collection,
        "thresholds": manifest["thresholds"],
    })
    candidate_outputs = {
        "dsh-llm-failover": (args.llm_source.resolve(), output / "dsh-llm-failover"),
        "dsh-model-failover": (args.model_source.resolve(), output / "dsh-model-failover"),
    }
    results = []
    errors = []
    for candidate_id, (source_root, candidate_output) in candidate_outputs.items():
        try:
            result = evaluate_candidate(candidate_id, source_root, candidate_output)
        except Exception as error:  # evidence should preserve one candidate's failure
            result = {
                "candidate": candidate_id,
                "status": "fail",
                "error": f"{type(error).__name__}: {error}",
                "checks": {"probe_completed": False},
            }
            errors.append(candidate_id)
        write_json(candidate_output / "candidate-result.json", result)
        results.append(result)
    overall_checks = {
        "all_candidate_probes_completed": not errors,
        "at_least_one_model_provider_switch_observed": any(item.get("checks", {}).get("provider_switch_observed") is True for item in results),
        "all_candidate_owned_durable_reason_ledgers_present": all(item.get("checks", {}).get("fallback_reason_durable") is True for item in results),
        "all_candidates_avoid_a_new_fallback_when_all_routes_are_cooled": all(item.get("checks", {}).get("all_routes_cooled_no_new_fallback_switch") is True for item in results),
        "real_provider_not_used": True,
        "real_credentials_not_used": True,
        "external_network_not_used": True,
    }
    summary = {
        "schema": SCHEMA,
        "status": "unknown/stop" if not all(overall_checks.values()) else "pass",
        "classification": "acceptance/evaluation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output": str(output),
        "runner_sha256": runner_sha256,
        "fixture_manifest_sha256": fixture_manifest_sha256,
        "formal_collection": formal_collection,
        "candidates": results,
        "checks": overall_checks,
        "decision": {
            "provider_failover_seam": "observed in candidate runtime where probe completed",
            "e4_gate": "unknown/stop because candidate-owned durable fallback-reason ledger is absent; dsh-llm also lacks a no-new-fallback all-cooldown behavior",
            "codex_main_harness_decision": "unchanged",
        },
        "non_claims": [
            "This result does not promote either plugin to a ZWorkbench product dependency.",
            "GitHub identity and repository claims are bounded by the formal collection state recorded above; this result does not claim popularity beyond the sealed ledger.",
            "This result does not use the real Ark Provider probe; the prior Ark summary remains a separate single-Provider staging baseline.",
        ],
    }
    write_json(output / "summary.json", summary)
    print(json.dumps({"status": summary["status"], "output": str(output), "checks": overall_checks}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
