"""Pinned, external-process DSH bootstrap adapter.

This module implements only the H1 runtime seam.  It verifies a small,
artifact-mode manifest, starts one case-local DSH process without a shell, and
records bootstrap evidence through :class:`CompositionOwner`.  It does not
implement a DSH agent loop, a Worker handshake, Codex coding, Provider calls,
or any side effect.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import selectors
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from .composition import CompositionOwner, InvalidTransition


RUNTIME_ADAPTER_SCHEMA = "zworkbench-dsh-runtime-adapter/v1"
RUNTIME_MANIFEST_SCHEMA = "zworkbench-dsh-runtime-manifest/v1"
BOOTSTRAP_SCHEMA = "zworkbench.dsh.bootstrap/v1"
RUNTIME_MODE = "artifact"
KNOWN_BOOTSTRAP_MESSAGES = frozenset({"bootstrap.started", "bootstrap.ready"})
BOOTSTRAP_TOP_LEVEL_FIELDS = frozenset({"schema", "message_type", "identity", "payload"})
BOOTSTRAP_IDENTITY_FIELDS = frozenset({"parent_run_id", "dsh_session_id"})
BOOTSTRAP_PAYLOAD_FIELDS = frozenset({"status", "profile_id"})
SAFE_INHERITED_ENVIRONMENT = frozenset({"PATH", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "TZ"})
SAFE_LAUNCH_ENVIRONMENT = frozenset({"LANG", "LC_ALL", "TZ", "DSH_LOG_LEVEL"})
SHA256_PREFIX = "sha256:"
MAX_BOOTSTRAP_LINE_BYTES = 64 * 1024
MAX_BOOTSTRAP_EVENTS = 100


class DshRuntimeError(RuntimeError):
    """Base class for an H1 failure that must not be treated as success."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code
        self.safe_stop = True


class DshManifestError(DshRuntimeError):
    """The pinned runtime manifest or one of its files is not admissible."""


class DshBootstrapProtocolError(DshRuntimeError):
    """The external DSH emitted an unknown or malformed bootstrap message."""


class DshProcessError(DshRuntimeError):
    """The external DSH could not start, finish, or exit cleanly."""


@dataclass(frozen=True)
class DshBootstrapExecution:
    """The owner-backed result of one successful H1 bootstrap."""

    run_id: str
    status: str
    dsh_session_id: str
    artifact_identity: Dict[str, Any]
    profile_identity: Dict[str, Any]
    source_commit: str
    provider_identity: Dict[str, Any]
    policy_identity: Dict[str, Any]
    workspace_digest: str
    environment_digest: str
    bootstrap_event_digest: str
    exit_code: int
    raw_event_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe, non-secret result shape."""

        return {
            "run_id": self.run_id,
            "status": self.status,
            "dsh_session_id": self.dsh_session_id,
            "artifact_identity": dict(self.artifact_identity),
            "profile_identity": dict(self.profile_identity),
            "source_commit": self.source_commit,
            "provider_identity": dict(self.provider_identity),
            "policy_identity": dict(self.policy_identity),
            "workspace_digest": self.workspace_digest,
            "environment_digest": self.environment_digest,
            "bootstrap_event_digest": self.bootstrap_event_digest,
            "exit_code": self.exit_code,
            "raw_event_count": self.raw_event_count,
        }


@dataclass(frozen=True)
class DshRuntimeManifest:
    """Validated manifest and resolved files for one fixed artifact bundle."""

    path: Path
    data: Dict[str, Any]
    bundle_root: Path
    artifact_path: Path
    lock_path: Path
    receipt_path: Path
    profile_path: Path
    workspace_relative: str
    dsh_home_relative: str

    @classmethod
    def load(cls, path: os.PathLike[str] | str) -> "DshRuntimeManifest":
        manifest_path = Path(path).expanduser().resolve(strict=False)
        if not manifest_path.is_file():
            raise DshManifestError(f"runtime manifest does not exist: {manifest_path}", code="manifest_missing")
        try:
            with manifest_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DshManifestError("runtime manifest is not valid JSON", code="manifest_invalid_json") from exc
        if not isinstance(data, dict):
            raise DshManifestError("runtime manifest must be an object", code="manifest_not_object")

        required = {
            "schema",
            "mode",
            "runtime",
            "artifact",
            "dependency_lock",
            "build_receipt",
            "profile",
            "schema_identity",
            "policy_identity",
            "provider_identity",
            "environment_identity",
            "workspace",
            "dsh_home",
            "launch",
        }
        _require_exact_fields(data, required, "manifest")
        if data["schema"] != RUNTIME_MANIFEST_SCHEMA:
            raise DshManifestError("unsupported runtime manifest schema", code="manifest_schema_unknown")
        if data["mode"] != RUNTIME_MODE:
            raise DshManifestError("H1 accepts artifact mode only", code="source_mode_forbidden")

        runtime = _mapping(data["runtime"], "runtime")
        _require_exact_fields(runtime, {"name", "version", "source_commit"}, "runtime")
        _text(runtime["name"], "runtime.name")
        _text(runtime["version"], "runtime.version")
        _text(runtime["source_commit"], "runtime.source_commit")

        artifact = _mapping(data["artifact"], "artifact")
        _require_exact_fields(artifact, {"name", "version", "path", "digest"}, "artifact")
        _text(artifact["name"], "artifact.name")
        _text(artifact["version"], "artifact.version")
        _digest(artifact["digest"], "artifact.digest")

        lock = _mapping(data["dependency_lock"], "dependency_lock")
        _require_exact_fields(lock, {"path", "digest"}, "dependency_lock")
        _digest(lock["digest"], "dependency_lock.digest")

        receipt = _mapping(data["build_receipt"], "build_receipt")
        _require_exact_fields(receipt, {"path", "digest"}, "build_receipt")
        _digest(receipt["digest"], "build_receipt.digest")

        profile = _mapping(data["profile"], "profile")
        _require_exact_fields(profile, {"id", "version", "path", "digest"}, "profile")
        _text(profile["id"], "profile.id")
        _text(profile["version"], "profile.version")
        _digest(profile["digest"], "profile.digest")

        schema_identity = _mapping(data["schema_identity"], "schema_identity")
        _require_exact_fields(schema_identity, {"name", "version", "digest"}, "schema_identity")
        _text(schema_identity["name"], "schema_identity.name")
        _text(schema_identity["version"], "schema_identity.version")
        _digest(schema_identity["digest"], "schema_identity.digest")

        policy = _mapping(data["policy_identity"], "policy_identity")
        _require_exact_fields(policy, {"id", "version", "digest", "mode"}, "policy_identity")
        _text(policy["id"], "policy_identity.id")
        _text(policy["version"], "policy_identity.version")
        _digest(policy["digest"], "policy_identity.digest")
        if policy["mode"] != "read-only":
            raise DshManifestError("H1 policy must be read-only", code="policy_not_read_only")

        provider = _mapping(data["provider_identity"], "provider_identity")
        required_provider = {"provider", "model", "endpoint", "transport"}
        unknown_provider = set(provider) - required_provider - {"metadata"}
        missing_provider = required_provider - set(provider)
        if missing_provider or unknown_provider:
            raise DshManifestError(
                "provider identity fields are incomplete or unknown",
                code="provider_identity_shape_invalid",
            )
        for name in required_provider:
            _text(provider[name], f"provider_identity.{name}")
        _reject_raw_credentials(provider, "provider_identity")
        endpoint = urlsplit(provider["endpoint"])
        if endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise DshManifestError("H1 Provider endpoint must be loopback", code="provider_not_loopback")
        if provider["transport"] not in {"loopback-only", "fake", "fake-loopback"}:
            raise DshManifestError("H1 Provider transport must be loopback-only", code="provider_transport_invalid")

        environment = _mapping(data["environment_identity"], "environment_identity")
        _require_exact_fields(environment, {"platform", "architecture", "runtime"}, "environment_identity")
        for name in ("platform", "architecture", "runtime"):
            _text(environment[name], f"environment_identity.{name}")
        current_platform = sys.platform
        current_architecture = platform.machine()
        if environment["platform"] not in {"any", current_platform}:
            raise DshManifestError("runtime platform does not match manifest", code="environment_platform_mismatch")
        if environment["architecture"] not in {"any", current_architecture}:
            raise DshManifestError("runtime architecture does not match manifest", code="environment_architecture_mismatch")

        workspace = _mapping(data["workspace"], "workspace")
        _require_exact_fields(workspace, {"path", "kind"}, "workspace")
        if workspace["kind"] != "case-local":
            raise DshManifestError("workspace must be case-local", code="workspace_kind_invalid")
        workspace_relative = _relative_path(workspace["path"], "workspace.path")

        dsh_home = _mapping(data["dsh_home"], "dsh_home")
        _require_exact_fields(dsh_home, {"path", "kind"}, "dsh_home")
        if dsh_home["kind"] != "case-local":
            raise DshManifestError("DSH_HOME must be case-local", code="dsh_home_kind_invalid")
        dsh_home_relative = _relative_path(dsh_home["path"], "dsh_home.path")

        launch = _mapping(data["launch"], "launch")
        _require_exact_fields(launch, {"args", "environment"}, "launch")
        if not isinstance(launch["args"], list) or any(not isinstance(item, str) or "\x00" in item for item in launch["args"]):
            raise DshManifestError("launch.args must be a NUL-free string list", code="launch_args_invalid")
        launch_environment = _mapping(launch["environment"], "launch.environment")
        if set(launch_environment) - SAFE_LAUNCH_ENVIRONMENT:
            raise DshManifestError("launch environment contains an undeclared key", code="launch_environment_invalid")
        for key, value in launch_environment.items():
            _text(key, "launch.environment.key")
            _text(value, f"launch.environment.{key}")
        _reject_raw_credentials(launch_environment, "launch.environment")

        bundle_root = manifest_path.parent
        artifact_path = _bundle_file(bundle_root, artifact["path"], "artifact.path")
        lock_path = _bundle_file(bundle_root, lock["path"], "dependency_lock.path")
        receipt_path = _bundle_file(bundle_root, receipt["path"], "build_receipt.path")
        profile_path = _bundle_file(bundle_root, profile["path"], "profile.path")
        manifest = cls(
            manifest_path,
            data,
            bundle_root,
            artifact_path,
            lock_path,
            receipt_path,
            profile_path,
            workspace_relative,
            dsh_home_relative,
        )
        manifest._verify_files_and_receipt()
        return manifest

    def _verify_files_and_receipt(self) -> None:
        artifact = self.data["artifact"]
        lock = self.data["dependency_lock"]
        receipt = self.data["build_receipt"]
        profile = self.data["profile"]
        for path, label in (
            (self.artifact_path, "artifact"),
            (self.lock_path, "dependency lock"),
            (self.receipt_path, "build receipt"),
            (self.profile_path, "profile"),
        ):
            if not path.is_file():
                raise DshManifestError(f"{label} file does not exist", code=f"{label.replace(' ', '_')}_missing")
        if not os.access(self.artifact_path, os.X_OK):
            raise DshManifestError("artifact is not executable", code="artifact_not_executable")
        if _file_digest(self.artifact_path) != artifact["digest"]:
            raise DshManifestError("artifact digest does not match manifest", code="artifact_digest_mismatch")
        if _file_digest(self.lock_path) != lock["digest"]:
            raise DshManifestError("dependency lock digest does not match manifest", code="lock_digest_mismatch")
        if _file_digest(self.receipt_path) != receipt["digest"]:
            raise DshManifestError("build receipt digest does not match manifest", code="receipt_digest_mismatch")
        if _file_digest(self.profile_path) != profile["digest"]:
            raise DshManifestError("profile digest does not match manifest", code="profile_digest_mismatch")

        try:
            with self.receipt_path.open("r", encoding="utf-8") as handle:
                receipt_data = json.load(handle)
            with self.profile_path.open("r", encoding="utf-8") as handle:
                profile_data = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DshManifestError("receipt or profile is not valid JSON", code="provenance_json_invalid") from exc
        if not isinstance(receipt_data, dict) or not isinstance(profile_data, dict):
            raise DshManifestError("receipt and profile must be JSON objects", code="provenance_shape_invalid")

        _require_exact_fields(
            receipt_data,
            {
                "schema",
                "runtime_name",
                "runtime_version",
                "source_commit",
                "dependency_lock_digest",
                "artifact_digest",
                "platform",
                "architecture",
            },
            "build_receipt.file",
        )
        if receipt_data["schema"] != "zworkbench-dsh-build-receipt/v1":
            raise DshManifestError("build receipt schema is unknown", code="receipt_schema_unknown")
        runtime = self.data["runtime"]
        if (
            receipt_data["runtime_name"] != runtime["name"]
            or receipt_data["runtime_version"] != runtime["version"]
            or receipt_data["source_commit"] != runtime["source_commit"]
            or receipt_data["dependency_lock_digest"] != lock["digest"]
            or receipt_data["artifact_digest"] != artifact["digest"]
        ):
            raise DshManifestError("build receipt identity does not match manifest", code="receipt_identity_mismatch")
        _text(receipt_data["platform"], "build_receipt.file.platform")
        _text(receipt_data["architecture"], "build_receipt.file.architecture")
        environment = self.data["environment_identity"]
        if receipt_data["platform"] not in {"any", environment["platform"], sys.platform}:
            raise DshManifestError("build receipt platform does not match environment", code="receipt_platform_mismatch")
        if receipt_data["architecture"] not in {"any", environment["architecture"], platform.machine()}:
            raise DshManifestError("build receipt architecture does not match environment", code="receipt_architecture_mismatch")

        _require_exact_fields(profile_data, {"schema", "id", "version", "mode", "plugins"}, "profile.file")
        if profile_data["schema"] != "zworkbench-dsh-profile/v1":
            raise DshManifestError("profile schema is unknown", code="profile_schema_unknown")
        if profile_data["id"] != self.data["profile"]["id"] or profile_data["version"] != self.data["profile"]["version"]:
            raise DshManifestError("profile identity does not match manifest", code="profile_identity_mismatch")
        if profile_data["mode"] != "headless-bootstrap" or profile_data["plugins"] != []:
            raise DshManifestError("H1 profile must be an empty headless bootstrap profile", code="profile_not_minimal")

    def identity(self) -> Dict[str, Any]:
        """Return the non-secret runtime provenance bound to a parent Run."""

        return {
            "adapter_schema": RUNTIME_ADAPTER_SCHEMA,
            "manifest_schema": self.data["schema"],
            "mode": self.data["mode"],
            "runtime": dict(self.data["runtime"]),
            "artifact": dict(self.data["artifact"]),
            "dependency_lock": dict(self.data["dependency_lock"]),
            "build_receipt": dict(self.data["build_receipt"]),
            "profile": dict(self.data["profile"]),
            "schema_identity": dict(self.data["schema_identity"]),
            "policy_identity": dict(self.data["policy_identity"]),
            "provider_identity": dict(self.data["provider_identity"]),
            "environment_identity": dict(self.data["environment_identity"]),
        }


class DshRuntimeAdapter:
    """Start one pinned DSH artifact and record its bootstrap lifecycle."""

    def __init__(
        self,
        owner: CompositionOwner,
        manifest_path: os.PathLike[str] | str,
        case_root: os.PathLike[str] | str,
    ) -> None:
        self.owner = owner
        self.manifest_path = Path(manifest_path).expanduser().resolve(strict=False)
        self.case_root = Path(case_root).expanduser().resolve(strict=False)
        self.process: Optional[subprocess.Popen[bytes]] = None
        self._selector = selectors.DefaultSelector()
        self._stderr_digest = hashlib.sha256()
        self._stderr_bytes = 0
        self._active_command: Optional[Tuple[str, ...]] = None
        self._last_exit_receipt: Optional[Dict[str, Any]] = None
        self._exit_receipt_recorded = False

    def execute(
        self,
        run_id: str,
        *,
        input_value: Optional[Any] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        timeout: float = 15.0,
    ) -> DshBootstrapExecution:
        """Bootstrap one DSH parent Run; all failures safe-stop that Run."""

        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._last_exit_receipt = None
        self._exit_receipt_recorded = False
        run_metadata = dict(metadata or {})
        run_metadata.update(
            {
                "adapter_schema": RUNTIME_ADAPTER_SCHEMA,
                "runtime_manifest": str(self.manifest_path),
                "runtime_mode": RUNTIME_MODE,
            }
        )
        self.owner.create_run(
            run_id,
            "dsh.bootstrap",
            input_value if input_value is not None else {"operation": "bootstrap"},
            run_metadata,
        )
        self.owner.start_run(run_id)
        try:
            manifest = DshRuntimeManifest.load(self.manifest_path)
            self._validate_case_paths(manifest)
            self.owner.record_result(run_id, "dsh.preflight", manifest.identity(), f"{run_id}:dsh-preflight")
            execution = self._run_process(run_id, manifest, timeout)
            self.owner.complete_run(run_id, execution.to_dict())
            return execution
        except Exception as exc:
            self._stop_process()
            try:
                self._record_exit_if_needed(run_id)
            except Exception:
                pass
            self._record_failure(run_id, exc)
            if isinstance(exc, (DshRuntimeError, DshManifestError, DshBootstrapProtocolError, DshProcessError)):
                raise
            raise DshRuntimeError(str(exc), code="h1_unexpected_failure") from exc
        finally:
            self._stop_process()

    def _validate_case_paths(self, manifest: DshRuntimeManifest) -> None:
        if not self.case_root.is_dir():
            raise DshManifestError("case root must already be a directory", code="case_root_missing")
        workspace = _case_path(self.case_root, manifest.workspace_relative, "workspace.path")
        dsh_home = _case_path(self.case_root, manifest.dsh_home_relative, "dsh_home.path")
        if not workspace.is_dir():
            raise DshManifestError("case-local workspace must already be a directory", code="workspace_missing")
        if workspace == dsh_home or workspace in dsh_home.parents or dsh_home in workspace.parents:
            raise DshManifestError("workspace and DSH_HOME must be distinct", code="case_paths_overlap")
        dsh_home.mkdir(parents=True, exist_ok=True)

    def command(self, manifest: Optional[DshRuntimeManifest] = None) -> list[str]:
        """Return the exact shell-free argv after manifest validation."""

        resolved = manifest or DshRuntimeManifest.load(self.manifest_path)
        return [str(resolved.artifact_path), *resolved.data["launch"]["args"]]

    def environment(self, run_id: str, manifest: Optional[DshRuntimeManifest] = None) -> Dict[str, str]:
        """Build the minimal environment passed to the external artifact."""

        resolved = manifest or DshRuntimeManifest.load(self.manifest_path)
        dsh_home = _case_path(self.case_root, resolved.dsh_home_relative, "dsh_home.path")
        environment = {key: value for key, value in os.environ.items() if key in SAFE_INHERITED_ENVIRONMENT}
        environment.update({key: str(value) for key, value in resolved.data["launch"]["environment"].items()})
        environment.update(
            {
                "DSH_HOME": str(dsh_home),
                "ZWORKBENCH_RUN_ID": run_id,
                "ZWORKBENCH_DSH_PROFILE": resolved.data["profile"]["id"],
                "ZWORKBENCH_DSH_PROFILE_DIGEST": resolved.data["profile"]["digest"],
                "ZWORKBENCH_H1": "1",
            }
        )
        return environment

    def _run_process(self, run_id: str, manifest: DshRuntimeManifest, timeout: float) -> DshBootstrapExecution:
        workspace = _case_path(self.case_root, manifest.workspace_relative, "workspace.path")
        command = self.command(manifest)
        environment = self.environment(run_id, manifest)
        workspace_digest = _sha256_json(
            {"kind": "case-local", "relative_path": manifest.workspace_relative, "resolved_path": str(workspace)}
        )
        environment_digest = _sha256_json(
            {
                "adapter_schema": RUNTIME_ADAPTER_SCHEMA,
                "argv": list(command),
                "environment": {key: value for key, value in environment.items() if key != "PATH"},
                "workspace_digest": workspace_digest,
                "policy_identity": manifest.data["policy_identity"],
                "provider_identity": manifest.data["provider_identity"],
            }
        )
        self._stderr_digest = hashlib.sha256()
        self._stderr_bytes = 0
        self._active_command = command
        self._last_exit_receipt = None
        self._exit_receipt_recorded = False
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(workspace),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
                close_fds=True,
            )
        except (OSError, ValueError) as exc:
            raise DshProcessError("DSH artifact failed to start", code="process_start_failed") from exc
        if self.process.stdout is None or self.process.stderr is None:
            raise DshProcessError("DSH process streams are unavailable", code="process_stream_missing")

        self._selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
        self._selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")
        stdout_buffer = bytearray()
        event_digest = hashlib.sha256()
        raw_event_count = 0
        dsh_session_id: Optional[str] = None
        started = False
        ready = False
        open_streams = 2
        deadline = time.monotonic() + timeout
        try:
            while open_streams:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DshProcessError("DSH bootstrap timed out", code="bootstrap_timeout")
                ready_streams = self._selector.select(min(0.25, remaining))
                if not ready_streams:
                    continue
                for selected, _ in ready_streams:
                    stream_name = selected.data
                    data = os.read(selected.fileobj.fileno(), 64 * 1024)
                    if not data:
                        try:
                            self._selector.unregister(selected.fileobj)
                        except Exception:
                            pass
                        open_streams -= 1
                        if stream_name == "stdout" and stdout_buffer:
                            raise DshBootstrapProtocolError(
                                "DSH emitted an incomplete JSONL message",
                                code="bootstrap_incomplete_jsonl",
                            )
                        continue
                    if stream_name == "stderr":
                        self._stderr_digest.update(data)
                        self._stderr_bytes += len(data)
                        continue
                    stdout_buffer.extend(data)
                    if len(stdout_buffer) > MAX_BOOTSTRAP_LINE_BYTES:
                        raise DshBootstrapProtocolError(
                            "DSH bootstrap message exceeds size limit",
                            code="bootstrap_message_too_large",
                        )
                    while b"\n" in stdout_buffer:
                        line, _, remainder = stdout_buffer.partition(b"\n")
                        stdout_buffer = bytearray(remainder)
                        if not line:
                            raise DshBootstrapProtocolError("DSH emitted an empty bootstrap line", code="bootstrap_empty_line")
                        if raw_event_count >= MAX_BOOTSTRAP_EVENTS:
                            raise DshBootstrapProtocolError("DSH emitted too many bootstrap events", code="bootstrap_event_limit")
                        message = self._parse_bootstrap_message(line, run_id, manifest)
                        canonical = _canonical_json(message).encode("utf-8") + b"\n"
                        event_digest.update(canonical)
                        raw_event_count += 1
                        identity = message["identity"]
                        if dsh_session_id is None:
                            dsh_session_id = identity["dsh_session_id"]
                        elif identity["dsh_session_id"] != dsh_session_id:
                            raise DshBootstrapProtocolError("DSH session identity changed", code="dsh_session_identity_changed")
                        message_type = message["message_type"]
                        if message_type == "bootstrap.started":
                            if started or ready:
                                raise DshBootstrapProtocolError("bootstrap.started was out of order", code="bootstrap_state_invalid")
                            started = True
                        elif message_type == "bootstrap.ready":
                            if not started or ready:
                                raise DshBootstrapProtocolError("bootstrap.ready was out of order", code="bootstrap_state_invalid")
                            ready = True
                        self.owner.record_event(
                            run_id,
                            f"dsh.{message_type}",
                            {
                                "schema": message["schema"],
                                "message_type": message_type,
                                "identity": dict(identity),
                                "status": message["payload"]["status"],
                                "profile_id": message["payload"]["profile_id"],
                            },
                        )
        finally:
            self._unregister_streams()

        if stdout_buffer:
            raise DshBootstrapProtocolError("DSH emitted an incomplete JSONL message", code="bootstrap_incomplete_jsonl")
        exit_code = self._wait_for_exit(deadline)
        exit_receipt = self._exit_receipt(exit_code, command)
        self._last_exit_receipt = exit_receipt
        self.owner.record_result(run_id, "dsh.exit", exit_receipt, f"{run_id}:dsh-exit")
        self._exit_receipt_recorded = True
        if exit_code != 0:
            raise DshProcessError("DSH exited with a non-zero code", code="process_exit_nonzero")
        if not started or not ready or dsh_session_id is None:
            raise DshBootstrapProtocolError("DSH did not complete the bootstrap state sequence", code="bootstrap_not_ready")

        result = DshBootstrapExecution(
            run_id=run_id,
            status="completed",
            dsh_session_id=dsh_session_id,
            artifact_identity=dict(manifest.data["artifact"]),
            profile_identity=dict(manifest.data["profile"]),
            source_commit=manifest.data["runtime"]["source_commit"],
            provider_identity=dict(manifest.data["provider_identity"]),
            policy_identity=dict(manifest.data["policy_identity"]),
            workspace_digest=workspace_digest,
            environment_digest=environment_digest,
            bootstrap_event_digest=f"{SHA256_PREFIX}{event_digest.hexdigest()}",
            exit_code=exit_code,
            raw_event_count=raw_event_count,
        )
        self.owner.record_result(run_id, "dsh.bootstrap", result.to_dict(), f"{run_id}:dsh-bootstrap")
        return result

    def _parse_bootstrap_message(self, line: bytes, run_id: str, manifest: DshRuntimeManifest) -> Dict[str, Any]:
        line_digest = hashlib.sha256(line).hexdigest()
        try:
            decoded = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.owner.record_event(
                run_id,
                "dsh.bootstrap.rejected",
                {"code": "bootstrap_invalid_json", "line_digest": f"{SHA256_PREFIX}{line_digest}"},
            )
            raise DshBootstrapProtocolError("DSH emitted invalid JSONL", code="bootstrap_invalid_json") from exc
        try:
            if not isinstance(decoded, dict):
                raise DshBootstrapProtocolError("bootstrap message must be an object", code="bootstrap_message_not_object")
            _require_exact_fields(decoded, BOOTSTRAP_TOP_LEVEL_FIELDS, "bootstrap message")
            if decoded["schema"] != BOOTSTRAP_SCHEMA:
                raise DshBootstrapProtocolError("bootstrap schema is unknown", code="bootstrap_schema_unknown")
            if decoded["message_type"] not in KNOWN_BOOTSTRAP_MESSAGES:
                raise DshBootstrapProtocolError("bootstrap message type is unknown", code="bootstrap_message_unknown")
            identity = _mapping(decoded["identity"], "bootstrap.identity")
            _require_exact_fields(identity, BOOTSTRAP_IDENTITY_FIELDS, "bootstrap.identity")
            _text(identity["parent_run_id"], "bootstrap.identity.parent_run_id")
            _text(identity["dsh_session_id"], "bootstrap.identity.dsh_session_id")
            if identity["parent_run_id"] != run_id:
                raise DshBootstrapProtocolError("bootstrap parent identity does not match Run", code="bootstrap_parent_identity_mismatch")
            payload = _mapping(decoded["payload"], "bootstrap.payload")
            _require_exact_fields(payload, BOOTSTRAP_PAYLOAD_FIELDS, "bootstrap.payload")
            expected_status = "started" if decoded["message_type"] == "bootstrap.started" else "ready"
            if payload["status"] != expected_status:
                raise DshBootstrapProtocolError("bootstrap status is unknown or invalid", code="bootstrap_status_unknown")
            if payload["profile_id"] != manifest.data["profile"]["id"]:
                raise DshBootstrapProtocolError("bootstrap profile identity does not match manifest", code="bootstrap_profile_mismatch")
            _text(payload["profile_id"], "bootstrap.payload.profile_id")
            return {
                "schema": decoded["schema"],
                "message_type": decoded["message_type"],
                "identity": {"parent_run_id": identity["parent_run_id"], "dsh_session_id": identity["dsh_session_id"]},
                "payload": {"status": payload["status"], "profile_id": payload["profile_id"]},
            }
        except DshBootstrapProtocolError:
            self.owner.record_event(
                run_id,
                "dsh.bootstrap.rejected",
                {"code": "bootstrap_message_rejected", "line_digest": f"{SHA256_PREFIX}{line_digest}"},
            )
            raise
        except DshManifestError as exc:
            self.owner.record_event(
                run_id,
                "dsh.bootstrap.rejected",
                {"code": "bootstrap_message_shape_invalid", "line_digest": f"{SHA256_PREFIX}{line_digest}"},
            )
            raise DshBootstrapProtocolError("bootstrap message shape is invalid", code="bootstrap_message_shape_invalid") from exc
        except (TypeError, ValueError) as exc:
            self.owner.record_event(
                run_id,
                "dsh.bootstrap.rejected",
                {"code": "bootstrap_shape_invalid", "line_digest": f"{SHA256_PREFIX}{line_digest}"},
            )
            raise DshBootstrapProtocolError("bootstrap message shape is invalid", code="bootstrap_shape_invalid") from exc

    def _wait_for_exit(self, deadline: float) -> int:
        if self.process is None:
            raise DshProcessError("DSH process is unavailable", code="process_missing")
        remaining = max(0.01, deadline - time.monotonic())
        try:
            return self.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise DshProcessError("DSH did not exit before timeout", code="process_exit_timeout") from exc

    def _exit_receipt(self, exit_code: int, command: Sequence[str]) -> Dict[str, Any]:
        return {
            "status": "exited",
            "exit_code": exit_code,
            "signal": -exit_code if exit_code < 0 else None,
            "stderr_sha256": f"{SHA256_PREFIX}{self._stderr_digest.hexdigest()}",
            "stderr_bytes": self._stderr_bytes,
            "argv_digest": _sha256_json(list(command)),
            "shell": False,
            "start_new_session": True,
        }

    def _record_failure(self, run_id: str, error: Exception) -> None:
        code = getattr(error, "code", "h1_failure")
        payload = {
            "code": str(code),
            "error_type": type(error).__name__,
            "message": str(error),
        }
        try:
            self.owner.record_result(run_id, "dsh.error", payload, f"{run_id}:dsh-error:{code}")
            run = self.owner.get_run(run_id)
            if run["status"] in {"created", "running", "waiting_approval", "recovering"}:
                self.owner.safe_stop_run(run_id, f"dsh:{code}")
        except Exception:
            # The original runtime failure remains the caller-visible error;
            # the owner database is inspected separately if this ledger write
            # itself fails.
            return

    def _record_exit_if_needed(self, run_id: str) -> None:
        if self._last_exit_receipt is None or self._exit_receipt_recorded:
            return
        self.owner.record_result(run_id, "dsh.exit", self._last_exit_receipt, f"{run_id}:dsh-exit")
        self._exit_receipt_recorded = True

    def _unregister_streams(self) -> None:
        for key in list(self._selector.get_map().values()):
            try:
                self._selector.unregister(key.fileobj)
            except Exception:
                pass

    def _stop_process(self) -> None:
        process = self.process
        if process is None:
            return
        try:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        process.kill()
                    process.wait(timeout=2)
            if process.returncode is not None and self._last_exit_receipt is None and self._active_command is not None:
                self._last_exit_receipt = self._exit_receipt(process.returncode, self._active_command)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
        finally:
            self._unregister_streams()
            self.process = None
            self._active_command = None

    def close(self) -> None:
        """Stop an active DSH process without deleting case-local evidence."""

        self._stop_process()

    def __enter__(self) -> "DshRuntimeAdapter":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()


def _mapping(value: Any, name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DshManifestError(f"{name} must be an object", code="manifest_field_not_object")
    return dict(value)


def _require_exact_fields(value: Mapping[str, Any], required: set[str] | frozenset[str], name: str) -> None:
    missing = set(required) - set(value)
    unknown = set(value) - set(required)
    if missing or unknown:
        raise DshManifestError(f"{name} fields are incomplete or unknown", code="manifest_field_shape_invalid")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise DshManifestError(f"{name} must be a non-empty NUL-free string", code="manifest_text_invalid")
    return value


def _digest(value: Any, name: str) -> str:
    _text(value, name)
    if len(value) != len(SHA256_PREFIX) + 64 or not value.startswith(SHA256_PREFIX):
        raise DshManifestError(f"{name} must be a sha256 digest", code="digest_format_invalid")
    try:
        int(value[len(SHA256_PREFIX) :], 16)
    except ValueError as exc:
        raise DshManifestError(f"{name} must be a sha256 digest", code="digest_format_invalid") from exc
    return value


def _relative_path(value: Any, name: str) -> str:
    _text(value, name)
    path = Path(value)
    if path.is_absolute() or value in {".", ""}:
        raise DshManifestError(f"{name} must be a relative case-local path", code="case_path_invalid")
    return value


def _bundle_file(bundle_root: Path, value: Any, name: str) -> Path:
    relative = _relative_path(value, name)
    resolved = (bundle_root / relative).resolve(strict=False)
    if resolved != bundle_root and bundle_root not in resolved.parents:
        raise DshManifestError(f"{name} escapes the manifest bundle", code="artifact_path_escape")
    return resolved


def _case_path(case_root: Path, relative: str, name: str) -> Path:
    resolved = (case_root / relative).resolve(strict=False)
    if resolved != case_root and case_root not in resolved.parents:
        raise DshManifestError(f"{name} escapes case root", code="case_path_escape")
    return resolved


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{SHA256_PREFIX}{digest.hexdigest()}"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    encoded = _canonical_json(value).encode("utf-8")
    return f"{SHA256_PREFIX}{hashlib.sha256(encoded).hexdigest()}"


def _reject_raw_credentials(value: Any, field_name: str) -> None:
    sensitive = {"api_key", "apikey", "authorization", "cookie", "password", "secret", "token", "key"}
    safe_suffixes = ("_ref", "_reference", "_fingerprint", "_digest", "_id")

    def visit(current: Any, path: str) -> None:
        if isinstance(current, Mapping):
            for key, item in current.items():
                normalized = str(key).lower().replace("-", "_")
                if not normalized.endswith(safe_suffixes):
                    parts = set(normalized.split("_"))
                    if normalized in sensitive or parts & sensitive:
                        raise DshManifestError(
                            f"{field_name} contains raw credential field {path}.{key}",
                            code="credential_value_forbidden",
                        )
                visit(item, f"{path}.{key}")
        elif isinstance(current, (list, tuple)):
            for index, item in enumerate(current):
                visit(item, f"{path}[{index}]")

    visit(value, field_name)


__all__ = [
    "BOOTSTRAP_SCHEMA",
    "DshBootstrapExecution",
    "DshBootstrapProtocolError",
    "DshManifestError",
    "DshProcessError",
    "DshRuntimeAdapter",
    "DshRuntimeError",
    "DshRuntimeManifest",
    "RUNTIME_ADAPTER_SCHEMA",
    "RUNTIME_MANIFEST_SCHEMA",
]
