from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

from zworkbench import (
    ComponentIdentity,
    CompositionOwner,
    ProviderIdentity,
    WorkerBridge,
    WorkerBridgeError,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "evaluation" / "fixtures" / "w8_worker_coding" / "v1" / "worker_fixture.py"
REAL_ADAPTER = REPO_ROOT / "evaluation" / "fixtures" / "w8_worker_coding" / "v1" / "codex_worker_adapter.py"


def digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def tree_digest(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class WorkerCodingTests(unittest.TestCase):
    def _case(
        self,
        scenario: str = "success",
        expected_executable_digest: str | None = None,
        require_host_sandbox: bool = False,
        host_sandbox_attestation: str | None = None,
    ):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        case_root = root / "case"
        workspace = case_root / "workspace"
        artifact_root = case_root / "evidence" / "artifacts"
        workspace.mkdir(parents=True)
        artifact_root.mkdir(parents=True)
        (workspace / "README.md").write_text("fixture project\n", encoding="utf-8")
        owner = CompositionOwner(case_root / "state" / "composition.sqlite3")
        owner.create_run("parent-1", "dsh.bootstrap", {"operation": "read-only-coding"})
        owner.start_run("parent-1")
        kwargs: dict = {}
        if expected_executable_digest is not None:
            kwargs["expected_executable_digest"] = expected_executable_digest
        if require_host_sandbox:
            kwargs["require_host_sandbox"] = True
        if host_sandbox_attestation is not None:
            kwargs["host_sandbox_attestation"] = host_sandbox_attestation
        bridge = WorkerBridge(
            owner,
            sys.executable,
            case_root,
            worker_args=(str(FIXTURE), "--scenario", scenario),
            worker_artifact_identity=ComponentIdentity(
                name="codex-worker-coding-fixture",
                version="1.0.0",
                digest=digest("coding-worker-artifact"),
                source="pinned-fixture",
            ),
            worker_schema_identity=ComponentIdentity(
                name="codex-app-server-fixture",
                version="v1",
                digest=digest("coding-worker-schema"),
                source="pinned-fixture-schema",
            ),
            provider_identity=ProviderIdentity(
                provider="fake-loopback",
                model="fixture-model",
                endpoint="http://127.0.0.1:11434",
                transport="loopback-only",
            ),
            policy_digest=digest("read-only-policy"),
            environment_digest=digest("coding-environment"),
            workspace_digest=digest("coding-workspace"),
            **kwargs,
        )
        return temporary, case_root, workspace, artifact_root, owner, bridge

    def _run(
        self,
        scenario: str = "success",
        require_host_sandbox: bool = False,
        host_sandbox_attestation: str | None = None,
    ):
        self.temporary, self.case_root, self.workspace, self.artifact_root, self.owner, self.bridge = self._case(
            scenario,
            require_host_sandbox=require_host_sandbox,
            host_sandbox_attestation=host_sandbox_attestation,
        )
        return self.bridge.read_only_coding(
            "parent-1",
            child_run_id="child-1",
            attempt_id="attempt-1",
            dsh_session_id="dsh-session-1",
            dsh_turn_id="dsh-turn-1",
            prompt="Inspect README.md, run the read-only fixture test, and return fixture-ok. Do not edit files.",
            artifact_root=self.artifact_root,
            timeout=2.0,
        )

    def _close_case(self) -> None:
        bridge = getattr(self, "bridge", None)
        owner = getattr(self, "owner", None)
        temporary = getattr(self, "temporary", None)
        if bridge is not None:
            bridge.close()
        if owner is not None:
            owner.close()
        if temporary is not None:
            temporary.cleanup()
        for name in ("bridge", "owner", "temporary"):
            if hasattr(self, name):
                delattr(self, name)

    def tearDown(self) -> None:
        self._close_case()

    def test_read_only_coding_records_artifacts_and_keeps_workspace_unchanged(self) -> None:
        before = None
        self.temporary, self.case_root, self.workspace, self.artifact_root, self.owner, self.bridge = self._case()
        before = tree_digest(self.workspace)
        result = self.bridge.read_only_coding(
            "parent-1",
            child_run_id="child-1",
            attempt_id="attempt-1",
            dsh_session_id="dsh-session-1",
            dsh_turn_id="dsh-turn-1",
            prompt="Inspect README.md, run the read-only fixture test, and return fixture-ok. Do not edit files.",
            artifact_root=self.artifact_root,
            timeout=2.0,
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.semantic_result["text"], "fixture-ok")
        # ADR 0011: declared UNKNOWN, not fabricated.
        self.assertEqual(result.identity.codex_thread_id, "unknown")
        self.assertEqual(result.identity.codex_turn_id, "unknown")
        self.assertEqual(tree_digest(self.workspace), before)
        for descriptor in result.artifacts.values():
            path = self.artifact_root / descriptor["path"]
            self.assertTrue(path.is_file())
            self.assertEqual("sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(), descriptor["digest"])
        parent = self.owner.get_run("parent-1")
        child = self.owner.get_run("child-1")
        self.assertEqual(parent["status"], "running")
        self.assertEqual(child["status"], "completed")
        self.assertIn("worker.coding", {item["kind"] for item in child["results"]})
        self.assertIn("worker.exit", {item["kind"] for item in child["results"]})
        self.assertEqual(parent["effects"], [])
        self.assertEqual(child["effects"], [])
        self.assertIsNone(self.bridge.process)

    def test_coding_wire_and_artifact_failures_safe_stop_both_runs(self) -> None:
        cases = (
            ("result-unknown", "coding_identity_incomplete"),
            ("artifact-mismatch", "coding_artifact_digest_mismatch"),
            ("artifact-extra", "coding_artifact_set_mismatch"),
            ("workspace-mutation", "coding_workspace_changed"),
            ("extra-message", "coding_extra_message"),
            ("nonzero", "worker_exit_nonzero"),
            ("malformed", "handshake_invalid_json"),
        )
        for scenario, expected_code in cases:
            with self.subTest(scenario=scenario):
                self._close_case()
                self.temporary, self.case_root, self.workspace, self.artifact_root, self.owner, self.bridge = self._case(scenario)
                with self.assertRaises(WorkerBridgeError) as raised:
                    self.bridge.read_only_coding(
                        "parent-1",
                        child_run_id="child-1",
                        attempt_id="attempt-1",
                        dsh_session_id="dsh-session-1",
                        dsh_turn_id="dsh-turn-1",
                        prompt="Inspect README.md without editing files.",
                        artifact_root=self.artifact_root,
                        timeout=1.0,
                    )
                self.assertEqual(raised.exception.code, expected_code)
                self.assertEqual(self.owner.get_run("parent-1")["status"], "safe_stopped")
                self.assertEqual(self.owner.get_run("child-1")["status"], "safe_stopped")
                self.assertIsNone(self.bridge.process)

    def test_credential_like_prompt_is_rejected_before_worker_start(self) -> None:
        self.temporary, self.case_root, self.workspace, self.artifact_root, self.owner, self.bridge = self._case()
        with self.assertRaises(WorkerBridgeError) as raised:
            self.bridge.read_only_coding(
                "parent-1",
                child_run_id="child-1",
                attempt_id="attempt-1",
                dsh_session_id="dsh-session-1",
                dsh_turn_id="dsh-turn-1",
                prompt="use api_key=sk-12345678901234567890",
                artifact_root=self.artifact_root,
                timeout=1.0,
            )
        self.assertEqual(raised.exception.code, "prompt_credential_forbidden")
        self.assertEqual(self.owner.get_run("parent-1")["status"], "running")
        self.assertEqual(len(self.owner.snapshot()["runs"]), 1)
        self.assertEqual(self.owner.get_run("parent-1")["results"], [])

    # ------------------------------------------------------------------
    # Node 1-8-2: value-level credential-shape rejection on the Worker
    # output surface (stdout structural fields + stderr), fail-closed.
    # ------------------------------------------------------------------

    def test_credential_shaped_worker_stderr_fails_closed(self) -> None:
        with self.assertRaises(WorkerBridgeError) as raised:
            self._run("stderr-secret")
        self.assertEqual(raised.exception.code, "worker_stderr_credential_forbidden")
        self.assertEqual(self.owner.get_run("parent-1")["status"], "safe_stopped")
        self.assertEqual(self.owner.get_run("child-1")["status"], "safe_stopped")
        self.assertIsNone(self.bridge.process)

    def test_credential_shaped_envelope_field_fails_closed(self) -> None:
        # A credential-shaped value inside a structural payload field is
        # rejected at parse time; semantic_result content is deliberately
        # excluded from this rejection (node 1-8-3 redacts it instead).
        with self.assertRaises(WorkerBridgeError) as raised:
            self._run("envelope-secret")
        self.assertEqual(raised.exception.code, "worker_output_credential_forbidden")
        self.assertEqual(self.owner.get_run("parent-1")["status"], "safe_stopped")
        self.assertEqual(self.owner.get_run("child-1")["status"], "safe_stopped")
        self.assertIsNone(self.bridge.process)

    # ------------------------------------------------------------------
    # Node 1-8-3: free-text semantic_result content is redacted on the
    # way into the owner, not rejected.
    # ------------------------------------------------------------------

    def test_credential_shaped_semantic_result_is_redacted_not_rejected(self) -> None:
        result = self._run("semantic-secret")
        self.assertEqual(result.status, "completed")
        text = result.semantic_result["text"]
        self.assertIn("<redacted>", text)
        self.assertNotIn("sk-", text)
        child = self.owner.get_run("child-1")
        self.assertEqual(child["status"], "completed")
        coding_records = [item["value"] for item in child["results"] if item["kind"] == "worker.coding"]
        self.assertTrue(coding_records)
        self.assertNotIn("sk-", json.dumps(coding_records, ensure_ascii=False))

    # ------------------------------------------------------------------
    # Node 1-8-5: the Worker executable digest is measured (not declared)
    # into the exit receipt and can be pinned at construction time.
    # ------------------------------------------------------------------

    def test_exit_receipt_pins_measured_executable_digest(self) -> None:
        result = self._run()
        self.assertEqual(result.status, "completed")
        child = self.owner.get_run("child-1")
        receipts = [item["value"] for item in child["results"] if item["kind"] == "worker.exit"]
        self.assertEqual(len(receipts), 1)
        expected = "sha256:" + hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
        self.assertEqual(receipts[0]["executable_digest"], expected)

    def test_expected_executable_digest_mismatch_fails_closed_at_construction(self) -> None:
        with self.assertRaises(WorkerBridgeError) as raised:
            self._case(expected_executable_digest="sha256:" + "0" * 64)
        self.assertEqual(raised.exception.code, "worker_executable_digest_mismatch")

    def test_expected_executable_digest_match_constructs(self) -> None:
        measured = "sha256:" + hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
        _, _, _, _, _, bridge = self._case(expected_executable_digest=measured)
        self.assertIsNotNone(bridge)

    def test_host_sandbox_absent_refuses_to_start_fail_closed(self) -> None:
        # Node 1-8-1: when require_host_sandbox=True but no operator attestation
        # is supplied, the Worker must refuse to start (fail-closed).  This is a
        # precondition failure, so the parent run is left untouched and no child
        # run is ever created.
        self.temporary, self.case_root, self.workspace, self.artifact_root, self.owner, self.bridge = self._case(
            require_host_sandbox=True
        )
        with self.assertRaises(WorkerBridgeError) as raised:
            self._run(require_host_sandbox=True)
        self.assertEqual(raised.exception.code, "host_sandbox_absent")
        self.assertFalse(getattr(raised.exception, "safe_stop", True))
        self.assertEqual(self.owner.get_run("parent-1")["status"], "running")
        self.assertEqual(len(self.owner.snapshot()["runs"]), 1)
        self.assertIsNone(self.bridge.process)

    def test_host_sandbox_attested_starts_normally(self) -> None:
        # Node 1-8-1: with require_host_sandbox=True and a valid operator
        # attestation, the gate passes and the coding turn completes.
        self.temporary, self.case_root, self.workspace, self.artifact_root, self.owner, self.bridge = self._case(
            require_host_sandbox=True, host_sandbox_attestation="operator-asserts-host-boundary-present"
        )
        result = self._run(
            require_host_sandbox=True,
            host_sandbox_attestation="operator-asserts-host-boundary-present",
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.owner.get_run("parent-1")["status"], "running")
        self.assertEqual(self.owner.get_run("child-1")["status"], "completed")

    def test_host_sandbox_off_by_default_does_not_gate(self) -> None:
        # Backward compatibility: existing deployments (no require flag) are not
        # gated by the host-sandbox contract.
        self.temporary, self.case_root, self.workspace, self.artifact_root, self.owner, self.bridge = self._case()
        result = self._run()
        self.assertEqual(result.status, "completed")

    def test_real_adapter_consumes_completion_buffered_before_turn_start_response(self) -> None:
        fake_codex = """
        import json
        import sys

        THREAD_ID = "buffered-thread"
        TURN_ID = "buffered-turn"

        def send(message):
            sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\\n")
            sys.stdout.flush()

        for line in sys.stdin:
            message = json.loads(line)
            if "id" not in message:
                continue
            request_id = message["id"]
            method = message.get("method")
            if method == "initialize":
                send({"jsonrpc": "2.0", "id": request_id, "result": {}})
            elif method == "thread/start":
                send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": THREAD_ID}}})
            elif method == "turn/start":
                # Force request() to buffer the completion notification before
                # it sees the matching turn/start response.
                send({"jsonrpc": "2.0", "method": "turn/completed", "params": {"threadId": THREAD_ID, "turn": {"id": TURN_ID, "status": "completed"}}})
                send({"jsonrpc": "2.0", "id": request_id, "result": {"turn": {"id": TURN_ID}}})
        """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "fake-codex"
            executable.write_text("#!{0}\n{1}".format(sys.executable, textwrap.dedent(fake_codex)), encoding="utf-8")
            executable.chmod(executable.stat().st_mode | 0o100)
            spec = importlib.util.spec_from_file_location("h3_codex_worker_adapter", REAL_ADAPTER)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            client = module.CodexProcess(executable, root / "codex-home", "http://127.0.0.1:1")
            try:
                client.start()
                thread_id, turn_id = client.start_turn("return fixture-ok")
                completed = client.wait_turn(thread_id, turn_id)
            finally:
                client.close()
            self.assertEqual((thread_id, turn_id), ("buffered-thread", "buffered-turn"))
            self.assertEqual(completed["status"], "completed")


if __name__ == "__main__":
    unittest.main()
