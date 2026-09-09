from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "evaluation" / "runner"))

from run_w8_native_approval_matrix import (  # noqa: E402
    DECISION,
    MATRIX,
    NETWORK_URL,
    SCHEMA,
    command_for,
    detect_codex_version,
    feature_observation,
    build_threshold,
    native_chain,
    setup_case,
    unique_json_values,
)


class _Server:
    def __init__(self, native_requests):
        self.native_requests = native_requests


class W8NativeApprovalMatrixTests(unittest.TestCase):
    def test_matrix_has_one_variable_changes_from_successful_baseline(self) -> None:
        configs = {item["id"]: item for item in MATRIX}
        minimal = configs["protocol_minimal"]
        self.assertEqual(minimal["id"], "protocol_minimal")
        self.assertEqual(minimal["approval_policy"], "on-request")
        self.assertEqual(minimal["target_kind"], "protocol_minimal")
        self.assertTrue(minimal["disable_plugins_apps"])
        self.assertTrue(minimal["disable_unified_exec"])
        self.assertEqual(
            next(item for item in MATRIX if item["id"] == "protocol_minimal_untrusted")["approval_policy"],
            "untrusted",
        )
        granular = next(item for item in MATRIX if item["id"] == "protocol_minimal_granular")
        self.assertTrue(granular["approval_policy"]["granular"]["sandbox_approval"])
        baseline = configs["baseline"]
        self.assertEqual(baseline["id"], "baseline")
        self.assertFalse(baseline["codex_ci"])
        self.assertEqual(baseline["turn_sandbox"], "workspaceWrite")
        self.assertFalse(baseline["outer_host_profile"])
        self.assertEqual(baseline["client_name"], "my_product")
        self.assertTrue(baseline["enable_exec_permission_approvals"])
        self.assertEqual(configs["ci_only"]["codex_ci"], True)
        self.assertEqual(configs["minimal_turn_payload"]["turn_payload"], "minimal")
        self.assertEqual(configs["external_sandbox_only"]["turn_sandbox"], "externalSandbox")
        self.assertEqual(configs["outer_profile_only"]["outer_host_profile"], True)
        self.assertEqual(configs["legacy_client_only"]["client_name"], "w8-external-sandbox-runner")

    def test_command_is_case_local_and_uses_pinned_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case = setup_case(Path(temporary) / "case", MATRIX[0], 1)
            command = json.loads(command_for(case))["cmd"]
            self.assertIn(str(REPO_ROOT / "evaluation/fixtures/w8_external_sandbox_native_approval/v1/direct_write.py"), command)
            self.assertIn(str(case["outside"]), command)
            self.assertIn(str(case["probe_pid_file"]), command)
            self.assertIn(str(case["probe_ready_file"]), command)
            self.assertIn(str(case["probe_release_file"]), command)

    def test_protocol_minimal_declares_only_workspace_as_writable_root(self) -> None:
        config = next(item for item in MATRIX if item["id"] == "protocol_minimal")
        with tempfile.TemporaryDirectory() as temporary:
            case = setup_case(Path(temporary) / "case", config, 1)
            command = json.loads(command_for(case))["cmd"]
            self.assertEqual(case["writable_roots"], [case["workspace"]])
            self.assertIn(str(case["outside"]), command)
            self.assertEqual((case["case_dir"] / "codex-home" / "config.toml").read_text(encoding="utf-8"), "")

    def test_obsidian_probe_uses_new_target_and_existing_index_source(self) -> None:
        config = next(item for item in MATRIX if item["id"] == "obsidian_vault_probe")
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary) / "vault"
            (vault / ".obsidian").mkdir(parents=True)
            (vault / "wiki").mkdir()
            (vault / "wiki" / "index.md").write_text("# Existing index\n", encoding="utf-8")
            case = setup_case(Path(temporary) / "case", config, 1, obsidian_vault=vault)
            command = json.loads(command_for(case))["cmd"]
            self.assertIn(str(vault / "wiki" / "index.md"), command)
            self.assertIn(str(case["target"]), command)
            self.assertFalse(case["target"].exists())
            self.assertEqual(case["target_kind"], "obsidian_vault")

    def test_network_probe_uses_fixed_read_only_url_command(self) -> None:
        config = next(item for item in MATRIX if item["id"] == "network_access_probe")
        with tempfile.TemporaryDirectory() as temporary:
            case = setup_case(Path(temporary) / "case", config, 1)
            command = json.loads(command_for(case))["cmd"]
            self.assertIn("curl", command)
            self.assertIn(NETWORK_URL, command)
            self.assertIn("--output /dev/null", command)
            self.assertEqual(case["network_url"], NETWORK_URL)
            self.assertEqual(config["approval_policy"], "on-request")

    def test_network_untrusted_probe_only_changes_approval_policy(self) -> None:
        on_request = next(item for item in MATRIX if item["id"] == "network_access_probe")
        untrusted = next(item for item in MATRIX if item["id"] == "network_access_untrusted_probe")
        self.assertEqual(untrusted["target_kind"], on_request["target_kind"])
        self.assertEqual(untrusted["network_url"], on_request["network_url"])
        self.assertEqual(untrusted["turn_sandbox"], on_request["turn_sandbox"])
        self.assertEqual(untrusted["provider_mode"], on_request["provider_mode"])
        self.assertEqual(untrusted["approval_policy"], "untrusted")

    def test_network_untrusted_plugins_disabled_probe_only_disables_plugins_apps(self) -> None:
        untrusted = next(item for item in MATRIX if item["id"] == "network_access_untrusted_probe")
        isolated = next(item for item in MATRIX if item["id"] == "network_access_untrusted_plugins_disabled_probe")
        self.assertEqual(isolated["approval_policy"], untrusted["approval_policy"])
        self.assertEqual(isolated["network_url"], untrusted["network_url"])
        self.assertTrue(isolated["disable_plugins_apps"])

    def test_native_chain_requires_order_and_item_identity(self) -> None:
        thread_id = "thread-1"
        turn_id = "turn-1"
        item_id = "item-1"
        request_id = 0
        request = {
            "request_id": request_id,
            "thread_id": thread_id,
            "turn_id": turn_id,
            "item_id": item_id,
            "response": {"decision": DECISION},
        }
        events = [
            {"method": "item/started", "params": {"item": {"id": item_id, "type": "commandExecution"}}},
            {"method": "item/commandExecution/requestApproval", "id": request_id, "params": {"threadId": thread_id, "turnId": turn_id, "itemId": item_id}},
            {"method": "serverRequest/resolved", "params": {"requestId": request_id, "threadId": thread_id}},
            {"method": "item/completed", "params": {"threadId": thread_id, "turnId": turn_id, "item": {"id": item_id, "type": "commandExecution", "status": "declined"}}},
        ]
        observed = native_chain(events, _Server([request]), thread_id, turn_id)
        self.assertTrue(observed["request_observed"])
        self.assertTrue(observed["identity_complete"])
        self.assertTrue(observed["decision_returned"])
        self.assertTrue(observed["resolved_observed"])
        self.assertTrue(observed["resolved_identity_complete"])
        self.assertTrue(observed["item_completed_observed"])
        self.assertTrue(observed["completed_identity_complete"])
        self.assertTrue(observed["ordered"])
        self.assertEqual(observed["terminal_status"], "declined")

    def test_waiting_without_request_is_not_a_native_chain(self) -> None:
        observed = native_chain(
            [{"method": "thread/status/changed", "params": {"status": {"activeFlags": ["waitingOnApproval"]}}}],
            _Server([]),
            "thread-1",
            "turn-1",
        )
        self.assertFalse(observed["request_observed"])
        self.assertFalse(observed["ordered"])
        self.assertEqual(observed["request_id"], None)

    def test_feature_observation_uses_case_local_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case_dir = Path(temporary) / "case"
            code_home = case_dir / "codex-home"
            with patch(
                "run_w8_native_approval_matrix.subprocess.run",
                return_value=SimpleNamespace(stdout="exec_permission_approvals\n", returncode=0),
            ) as run:
                observed = feature_observation(
                    "/opt/codex",
                    True,
                    case_dir=case_dir,
                    code_home=code_home,
                    codex_ci=False,
                )

            kwargs = run.call_args.kwargs
            self.assertEqual(kwargs["cwd"], str(case_dir))
            self.assertEqual(kwargs["env"]["CODEX_HOME"], str(code_home))
            self.assertNotIn("CODEX_CI", kwargs["env"])
            self.assertEqual(observed["codex_home"], str(code_home))

    def test_detect_codex_version_records_selected_executable(self) -> None:
        with patch(
            "run_w8_native_approval_matrix.subprocess.run",
            return_value=SimpleNamespace(stdout="codex-cli 0.151.0-alpha.7.2\n", stderr="", returncode=0),
        ):
            self.assertEqual(detect_codex_version("/Applications/ChatGPT.app/Contents/Resources/codex"), "codex-cli 0.151.0-alpha.7.2")

    def test_schema_is_evaluation_only(self) -> None:
        self.assertEqual(SCHEMA, "zworkbench-w8-native-approval-matrix/v1")

    def test_structured_approval_policy_is_preserved_in_threshold(self) -> None:
        granular = next(item for item in MATRIX if item["id"] == "protocol_minimal_granular")
        self.assertEqual(
            unique_json_values(["on-request", granular["approval_policy"], "on-request"]),
            ["on-request", granular["approval_policy"]],
        )
        threshold = build_threshold((granular,), 3, None)
        self.assertEqual(threshold["approval_policies"], [granular["approval_policy"]])
        self.assertNotIn("network_probe", threshold)

    def test_network_threshold_is_only_present_for_network_matrix(self) -> None:
        network = next(item for item in MATRIX if item["id"] == "network_access_untrusted_probe")
        threshold = build_threshold((network,), 3, None)
        self.assertEqual(threshold["network_probe"]["url"], NETWORK_URL)


if __name__ == "__main__":
    unittest.main()
