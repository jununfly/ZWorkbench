#!/usr/bin/env python3
"""Run one bounded real Codex app-server turn against Ark in case-local staging.

This is an acceptance/evaluation runner, not the default ZWorkbench product
path.  It reads the API key from stdin, passes it only to the supervised Codex
child process through the configured environment key, and writes only
non-secret owner/evidence metadata.  The app-server event log is deliberately
redacted before it is persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from zworkbench.codex_adapter import CodexAppServerAdapter, CodexAdapterError  # noqa: E402
from zworkbench.composition import CompositionOwner  # noqa: E402


SCHEMA = "zworkbench-real-codex-provider-staging/v1"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/coding/v3"
DEFAULT_ENDPOINT = DEFAULT_BASE_URL + "/responses"
DEFAULT_MODEL = "ark-code-latest"
DEFAULT_REGION = "cn-beijing"
DEFAULT_PROVIDER_CONFIG_NAME = "ark-real-staging"
DEFAULT_CREDENTIAL_ENV = "ARK_API_KEY"
CODEX_VERSION = "codex-cli 0.139.0"
RUN_ID = "remote-codex-staging-1"
FIXTURE_ID = "staging-fixture-001"
FIXTURE_PROMPT = (
    'Return exactly JSON with keys "status" and "answer". '
    'Use status="ok" and answer="staging-fixture-001". '
    "Do not call tools, access files, create tasks, send callbacks, or write anything."
)
PROJECT_FINGERPRINT = re.compile(r"[0-9a-fA-F]{64}")
ENVIRONMENT_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,63}")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return digest(encoded)


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_digest(path: Path) -> Optional[str]:
    try:
        return digest(path.read_bytes())
    except OSError:
        return None


def validate_base_url(base_url: str) -> None:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "ark.cn-beijing.volces.com"
        or parsed.path != "/api/coding/v3"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("base_url must be the fixed Ark Coding base URL")


def validate_inputs(
    base_url: str,
    model: str,
    region: str,
    project_fingerprint: str,
    credential_env_name: str,
    timeout: int,
) -> None:
    validate_base_url(base_url)
    if model != DEFAULT_MODEL:
        raise ValueError(f"model must be {DEFAULT_MODEL} for this staging runner")
    if region != DEFAULT_REGION:
        raise ValueError(f"region must be {DEFAULT_REGION} for the fixed Ark staging endpoint")
    if not PROJECT_FINGERPRINT.fullmatch(project_fingerprint):
        raise ValueError("project_fingerprint must be a 64-character SHA-256 hex fingerprint")
    if not ENVIRONMENT_NAME.fullmatch(credential_env_name):
        raise ValueError("credential environment name must be an uppercase environment variable name")
    if not 5 <= timeout <= 120:
        raise ValueError("timeout must be between 5 and 120 seconds")


def _safe_event(value: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep event protocol shape while dropping prompts, responses, and paths."""

    direction = value.get("direction")
    message = value.get("message")
    safe: Dict[str, Any] = {"direction": direction}
    if not isinstance(message, Mapping):
        safe["message_type"] = type(message).__name__
        return safe
    safe_message: Dict[str, Any] = {}
    for key in ("jsonrpc", "id", "method"):
        if key in message:
            safe_message[key] = message[key]
    params = message.get("params")
    if isinstance(params, Mapping):
        safe_params: Dict[str, Any] = {"keys": sorted(str(key) for key in params.keys())}
        if "input" in params and isinstance(params["input"], list):
            safe_params["input_count"] = len(params["input"])
        safe_message["params"] = safe_params
    if "result" in message:
        result = message.get("result")
        safe_message["result_type"] = type(result).__name__
        if isinstance(result, Mapping):
            safe_message["result_keys"] = sorted(str(key) for key in result.keys())
    if "error" in message:
        error = message.get("error")
        safe_message["error_present"] = True
        safe_message["error_type"] = type(error).__name__
    safe["message"] = safe_message
    return safe


class RedactedCodexAppServerAdapter(CodexAppServerAdapter):
    """Codex adapter variant whose persisted event log contains no raw payload."""

    def _append_event(self, value: Mapping[str, Any]) -> None:
        safe_value = _safe_event(value)
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        with self.event_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _fail_owner_run(self, run_id: str, error: Exception) -> None:
        """Persist only a stable error class, never a Provider error payload."""

        try:
            run = self.owner.get_run(run_id)
            if run["status"] in {"created", "running", "waiting_approval", "recovering"}:
                self.owner.fail_run(run_id, {"type": type(error).__name__, "message": "remote Codex staging failed"})
        except Exception:
            return


def semantic_fixture_exact(text: str) -> bool:
    """Accept only the exact synthetic JSON object, optionally in a code fence."""

    candidate = text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(candidate)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value == {"answer": FIXTURE_ID, "status": "ok"}


def workspace_snapshot(root: Path) -> Dict[str, str]:
    return {
        str(path.relative_to(root)): digest(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def raw_value_in_case(case_root: Path, key: bytes) -> bool:
    if not key:
        return False
    for path in sorted(case_root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            if key in path.read_bytes():
                return True
        except OSError:
            return True
    return False


def provider_identity(region: str, project_fingerprint: str, key_fingerprint: str) -> Dict[str, Any]:
    return {
        "provider": "volcengine-ark",
        "model": DEFAULT_MODEL,
        "endpoint": DEFAULT_ENDPOINT,
        "transport": "https",
        "metadata": {
            "base_url": DEFAULT_BASE_URL,
            "region": region,
            "project_fingerprint": project_fingerprint.lower(),
            "api_key_fingerprint": key_fingerprint,
            "credential_env_name": DEFAULT_CREDENTIAL_ENV,
            "stage": "authorized-read-only-case-local",
        },
    }


def run_staging(
    output_dir: Path,
    codex: Path,
    *,
    region: str,
    project_fingerprint: str,
    key: bytes,
    timeout: int = 90,
) -> Dict[str, Any]:
    validate_inputs(DEFAULT_BASE_URL, DEFAULT_MODEL, region, project_fingerprint, DEFAULT_CREDENTIAL_ENV, timeout)
    if not key:
        return {
            "schema": SCHEMA,
            "classification": "external/on-demand; not a ZWorkbench product gate",
            "outcome": "input_empty",
            "request_count": 0,
            "retry_count": 0,
            "credential": {"fingerprint_algorithm": "SHA-256", "api_key_fingerprint": digest(key)},
            "raw_credential_persisted": False,
        }
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    codex = codex.expanduser().resolve()
    if not codex.is_file() or not os.access(codex, os.X_OK):
        raise ValueError("Codex executable must already exist and be executable")
    # Codex writes shell snapshots and session files under CODEX_HOME.  That
    # runtime state is not evidence and can contain inherited environment
    # values, including the credential used for this one process.  Keep it in
    # a private temporary directory and remove it before the redacted summary
    # is produced.
    code_home = Path(tempfile.mkdtemp(prefix="zworkbench-real-codex-home-"))
    try:
        code_home.chmod(0o700)
    except OSError:
        pass
    runtime_home_cleaned = False
    runtime_home_cleanup_error: Optional[str] = None
    try:
        key_text = key.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("API key input must be UTF-8") from exc

    workspace = output_dir / "workspace"
    event_log = output_dir / "events" / "codex-redacted.jsonl"
    database = output_dir / "state" / "composition.sqlite3"
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("synthetic remote Codex staging workspace\n", encoding="utf-8")
    before_workspace = workspace_snapshot(workspace)
    key_fingerprint = digest(key)
    identity = provider_identity(region, project_fingerprint, key_fingerprint)
    config_overrides = (
        'model_provider="ark-real-staging"',
        f'model="{DEFAULT_MODEL}"',
        'model_providers.ark-real-staging.name="Volcengine Ark staging"',
        'model_providers.ark-real-staging.wire_api="responses"',
        f'model_providers.ark-real-staging.base_url="{DEFAULT_BASE_URL}"',
        f'model_providers.ark-real-staging.env_key="{DEFAULT_CREDENTIAL_ENV}"',
        "disable_response_storage=true",
    )
    adapter: Optional[RedactedCodexAppServerAdapter] = None
    execution = None
    error: Optional[Dict[str, str]] = None
    owner_snapshot: Dict[str, Any] = {}
    try:
        with CompositionOwner(database) as owner:
            adapter = RedactedCodexAppServerAdapter(
                owner,
                codex,
                code_home,
                workspace,
                model=DEFAULT_MODEL,
                model_provider=DEFAULT_PROVIDER_CONFIG_NAME,
                provider_identity=identity,
                sandbox="read-only",
                approval_policy="never",
                config_overrides=config_overrides,
                disabled_features=("plugins", "apps"),
                event_log=event_log,
                client_name="zworkbench-remote-codex-staging",
                client_version=SCHEMA,
                extra_environment={DEFAULT_CREDENTIAL_ENV: key_text},
            )
            try:
                execution = adapter.execute(
                    RUN_ID,
                    FIXTURE_PROMPT,
                    task_type="remote_codex_provider_staging",
                    input_value={"operation": "synthetic_read_only", "fixture_id": FIXTURE_ID},
                    metadata={
                        "staging_schema": SCHEMA,
                        "provider_identity": identity,
                        "codex_version": CODEX_VERSION,
                        "sandbox": "read-only",
                        "approval_policy": "never",
                        "plugins_disabled": True,
                        "apps_disabled": True,
                        "retry_count": 0,
                    },
                    timeout=timeout,
                )
            except (CodexAdapterError, OSError, TimeoutError, ValueError) as exc:
                error = {"type": type(exc).__name__, "code": "remote_codex_staging_failed"}
            finally:
                adapter.close()
            owner_snapshot = owner.snapshot()
            state_digest = owner.state_digest()
    finally:
        try:
            shutil.rmtree(code_home)
            runtime_home_cleaned = True
        except OSError as exc:
            runtime_home_cleanup_error = type(exc).__name__
        key_text = ""
        del key_text

    run = next((item for item in owner_snapshot.get("runs", []) if item.get("run_id") == RUN_ID), {})
    raw_credential_persisted = raw_value_in_case(output_dir, key)
    after_workspace = workspace_snapshot(workspace)
    semantic = bool(execution is not None and semantic_fixture_exact(execution.text))
    effects = [
        effect
        for effect in owner_snapshot.get("effects", [])
        if effect.get("run_id") == RUN_ID
    ]
    success = (
        execution is not None
        and execution.status == "completed"
        and semantic
        and run.get("status") == "completed"
        and not effects
        and before_workspace == after_workspace
        and not raw_credential_persisted
        and adapter is not None
        and adapter.process is None
        and runtime_home_cleaned
        and runtime_home_cleanup_error is None
    )
    summary: Dict[str, Any] = {
        "schema": SCHEMA,
        "classification": "external/on-demand; not a ZWorkbench product gate",
        "provider": "volcengine-ark",
        "base_url": DEFAULT_BASE_URL,
        "endpoint": DEFAULT_ENDPOINT,
        "model": DEFAULT_MODEL,
        "region": region,
        "project_fingerprint": project_fingerprint.lower(),
        "credential": {"fingerprint_algorithm": "SHA-256", "api_key_fingerprint": digest(key)},
        "codex_runtime": {
            "version": CODEX_VERSION,
            "executable": str(codex),
            "executable_sha256": file_digest(codex),
            "config_provider_name": DEFAULT_PROVIDER_CONFIG_NAME,
            "credential_env_name": DEFAULT_CREDENTIAL_ENV,
            "home_scope": "ephemeral-private-outside-evidence",
            "home_cleaned": runtime_home_cleaned,
            "sandbox": "read-only",
            "approval_policy": "never",
            "plugins_disabled": True,
            "apps_disabled": True,
            "disable_response_storage_requested": True,
        },
        "synthetic_fixture": {"id": FIXTURE_ID, "prompt_sha256": digest(FIXTURE_PROMPT.encode("utf-8"))},
        "request_count": 1 if execution is not None else 0,
        "retry_count": 0,
        "outcome": "http_and_codex_success" if success else "unknown/stop",
        "compatibility_status": "verified-for-authorized-read-only-codex-staging" if success else "unknown/stop",
        "owner_correlation": {
            "run_id": RUN_ID,
            "run_status": run.get("status"),
            "thread_id": execution.thread_id if execution is not None else None,
            "turn_id": execution.turn_id if execution is not None else None,
            "event_digest": execution.event_digest if execution is not None else file_digest(event_log),
            "environment_digest": execution.environment_digest if execution is not None else None,
            "owner_state_digest": state_digest,
            "raw_event_count": execution.raw_event_count if execution is not None else 0,
        },
        "safety": {
            "workspace_unchanged": before_workspace == after_workspace,
            "effect_count": len(effects),
            "raw_credential_persisted": raw_credential_persisted,
            "event_log_redacted": True,
            "worker_or_codex_process_absent": adapter is not None and adapter.process is None,
            "ephemeral_runtime_home_cleaned": runtime_home_cleaned,
            "ephemeral_runtime_home_cleanup_error": runtime_home_cleanup_error,
        },
        "semantic": {
            "turn_completed": execution is not None and execution.status == "completed",
            "fixture_exact": semantic,
            "text_sha256": digest(execution.text.encode("utf-8")) if execution is not None else None,
        },
        "error": error,
        "non_claims": [
            "This is one authorized case-local Codex turn, not default remote Provider routing.",
            "This does not prove H4 lifecycle/recovery, H5 replay, failover/degradation, or Provider-side exit.",
            "This does not prove production data, write, task, Webhook, backup, or deployment safety.",
        ],
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex", type=Path, default=Path("/opt/homebrew/bin/codex"))
    parser.add_argument("--region", required=True)
    parser.add_argument("--project-fingerprint", required=True)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    try:
        key = sys.stdin.buffer.read().strip()
        summary = run_staging(
            args.output,
            args.codex,
            region=args.region,
            project_fingerprint=args.project_fingerprint,
            key=key,
            timeout=args.timeout,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"schema": SCHEMA, "outcome": "preflight_blocked", "error_type": type(exc).__name__}, ensure_ascii=False))
        return 2
    summary_path = args.output / "summary.json"
    if not summary_path.exists():
        write_json(summary_path, summary)
    print(json.dumps({"summary": str(summary_path.resolve()), "outcome": summary.get("outcome")}, ensure_ascii=False))
    return 0 if summary.get("outcome") == "http_and_codex_success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
