from __future__ import annotations

import hashlib
import importlib.util
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
    def _case(self, scenario: str = "success"):
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
        )
        return temporary, case_root, workspace, artifact_root, owner, bridge

    def _run(self, scenario: str = "success"):
        self.temporary, self.case_root, self.workspace, self.artifact_root, self.owner, self.bridge = self._case(scenario)
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
        self.assertEqual(result.identity.codex_thread_id, "codex-thread-1")
        self.assertEqual(result.identity.codex_turn_id, "codex-turn-1")
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
