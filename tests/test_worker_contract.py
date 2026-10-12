import json
import unittest
from dataclasses import replace

from zworkbench import (
    WORKER_CONTRACT_SCHEMA,
    CapabilityFacade,
    CapabilityRequest,
    ComponentIdentity,
    CompletionBlocked,
    IdentityChain,
    ProviderIdentity,
    SafeStopRequired,
    UNKNOWN,
    WorkerContractError,
    WorkerEnvelope,
)


def make_envelope(**overrides):
    values = {
        "message_type": "handshake.response",
        "identity": IdentityChain(
            parent_run_id="parent-1",
            child_run_id="child-1",
            attempt_id="attempt-1",
            dsh_session_id="dsh-session-1",
            dsh_turn_id="dsh-turn-1",
            worker_run_id="worker-1",
            codex_thread_id="thread-1",
            codex_turn_id="turn-1",
            event_id="event-1",
            artifact_id="artifact-1",
        ),
        "provider_identity": ProviderIdentity(
            provider="fake-loopback",
            model="fake-model",
            endpoint="http://127.0.0.1:11434",
            transport="loopback-only",
        ),
        "replay_mode": "normal",
        "policy_digest": "sha256:policy",
        "environment_digest": "sha256:environment",
        "workspace_digest": "sha256:workspace",
        "worker_artifact_identity": ComponentIdentity(
            name="codex-worker",
            version="0.139.0",
            digest="sha256:worker",
            source="pinned-package",
        ),
        "worker_schema_identity": ComponentIdentity(
            name="codex-app-server",
            version="v1",
            digest="sha256:schema",
            source="pinned-schema",
        ),
        "payload": {"status": "ready"},
    }
    values.update(overrides)
    return WorkerEnvelope(**values)


def make_capability_envelope(
    *,
    capability="workspace.read",
    effect_class="none",
    declared_permissions=("workspace.read",),
    replay_mode="normal",
):
    return make_envelope(
        message_type="capability.request",
        replay_mode=replay_mode,
        capability_request=CapabilityRequest(
            request_id="request-1",
            capability=capability,
            operation="read-file",
            resource="case://workspace/README.md",
            effect_class=effect_class,
            declared_permissions=declared_permissions,
            arguments={"path": "README.md"},
        ),
    )


class WorkerContractTests(unittest.TestCase):
    def test_valid_envelope_round_trips_as_canonical_json(self):
        envelope = make_envelope()

        wire = envelope.to_dict()
        self.assertEqual(wire["schema"], WORKER_CONTRACT_SCHEMA)
        self.assertTrue(envelope.identity.is_complete())

        restored = WorkerEnvelope.from_json(envelope.to_json())
        self.assertEqual(restored, envelope)
        self.assertEqual(json.loads(envelope.to_json()), wire)

    def test_unknown_wire_message_requires_safe_stop(self):
        with self.assertRaises(SafeStopRequired) as raised:
            make_envelope(message_type="future.message")

        self.assertEqual(raised.exception.code, "unknown_wire_message")
        self.assertTrue(raised.exception.safe_stop)

    def test_unknown_wire_field_requires_safe_stop(self):
        wire = make_envelope().to_dict()
        wire["future_field"] = "must not be guessed"

        with self.assertRaises(SafeStopRequired) as raised:
            WorkerEnvelope.from_dict(wire)

        self.assertEqual(raised.exception.code, "unknown_wire_field")
        self.assertTrue(raised.exception.safe_stop)

    def test_allowlisted_capability_requires_matching_declared_permission(self):
        decision = CapabilityFacade().authorize(make_capability_envelope())

        self.assertEqual(decision.decision, "allow")
        self.assertEqual(decision.request_id, "request-1")
        self.assertFalse(decision.safe_stop)

    def test_unknown_capability_requires_safe_stop(self):
        with self.assertRaises(SafeStopRequired) as raised:
            CapabilityFacade().authorize(
                make_capability_envelope(capability="future.capability")
            )

        self.assertEqual(raised.exception.code, "unknown_capability")
        self.assertTrue(raised.exception.safe_stop)

    def test_unknown_effect_requires_safe_stop(self):
        with self.assertRaises(SafeStopRequired) as raised:
            CapabilityFacade().authorize(
                make_capability_envelope(effect_class="future.effect")
            )

        self.assertEqual(raised.exception.code, "unknown_effect")
        self.assertTrue(raised.exception.safe_stop)

    def test_replay_cannot_authorize_worker_provider_or_tool_capability(self):
        with self.assertRaises(SafeStopRequired) as raised:
            CapabilityFacade().authorize(
                make_capability_envelope(replay_mode="simulated_replay")
            )

        self.assertEqual(raised.exception.code, "replay_execution_forbidden")
        self.assertTrue(raised.exception.safe_stop)

    def test_worker_completion_is_blocked_when_identity_is_unknown(self):
        # Required layer: a ZWorkbench-owned field may never be UNKNOWN.
        envelope = make_envelope(
            message_type="result",
            identity=replace(make_envelope().identity, worker_run_id=UNKNOWN),
            payload={"status": "completed"},
        )

        with self.assertRaises(CompletionBlocked) as raised:
            envelope.validate_worker_completion()

        self.assertIn("worker_run_id", raised.exception.missing)

    def test_identity_completion_is_layered(self):
        from zworkbench.worker_contract import CODEX_WORKER_SCHEMA_NAMES, codex_identity_required

        identity = make_envelope().identity
        declared_unknown = replace(identity, codex_thread_id=UNKNOWN, codex_turn_id=UNKNOWN)

        # Non-Codex Worker: declared UNKNOWN Codex identity is a legal completion.
        self.assertTrue(declared_unknown.is_complete_for(False))
        self.assertFalse(declared_unknown.is_complete())
        self.assertEqual(declared_unknown.missing_required_fields(), ())
        self.assertEqual(declared_unknown.missing_conditional_fields(), ("codex_thread_id", "codex_turn_id"))

        # Declared Codex Worker: the conditional layer becomes required.
        self.assertFalse(declared_unknown.is_complete_for(True))
        self.assertEqual(declared_unknown.missing_fields(), ("codex_thread_id", "codex_turn_id"))

        # Declaration is exact-match, never prefix/substring.
        self.assertIn("codex-app-server", CODEX_WORKER_SCHEMA_NAMES)
        self.assertTrue(codex_identity_required(ComponentIdentity(name="codex-app-server", version="v1", digest="sha256:x", source="pinned")))
        self.assertFalse(codex_identity_required(ComponentIdentity(name="codex-app-server-fixture", version="v1", digest="sha256:x", source="pinned-fixture-schema")))

    def test_fabricated_codex_identity_is_rejected(self):
        # A non-Codex Worker cannot invent a Codex identity to satisfy the seal.
        envelope = make_envelope(
            message_type="result",
            identity=replace(make_envelope().identity, worker_run_id="worker-1"),
            worker_schema_identity=ComponentIdentity(
                name="codex-app-server-fixture",
                version="v1",
                digest="sha256:schema",
                source="pinned-fixture-schema",
            ),
            payload={"status": "completed"},
        )

        with self.assertRaises(WorkerContractError) as raised:
            envelope.validate_worker_completion()

        self.assertEqual(raised.exception.code, "codex_identity_fabricated")

    def test_worker_completion_requires_explicit_completed_result(self):
        envelope = make_envelope(message_type="result", payload={"status": "completed"})

        envelope.validate_worker_completion()

    def test_raw_provider_credential_cannot_enter_contract(self):
        with self.assertRaises(WorkerContractError) as raised:
            ProviderIdentity(
                provider="fake-loopback",
                model="fake-model",
                endpoint="http://127.0.0.1:11434",
                transport="loopback-only",
                metadata={"api_key": "secret-value"},
            )

        self.assertEqual(raised.exception.code, "credential_value_forbidden")

    def test_provider_credential_fingerprint_is_safe_identity_metadata(self):
        identity = ProviderIdentity(
            provider="ark",
            model="ark-code-latest",
            endpoint="https://example.invalid/v1",
            transport="openai-compatible",
            metadata={"api_key_fingerprint": "sha256:fingerprint"},
        )

        self.assertEqual(
            identity.to_dict()["metadata"]["api_key_fingerprint"],
            "sha256:fingerprint",
        )

    def test_nested_raw_credential_cannot_enter_payload(self):
        with self.assertRaises(WorkerContractError) as raised:
            make_envelope(payload={"nested": [{"token": "secret-value"}]})

        self.assertEqual(raised.exception.code, "credential_value_forbidden")

    def test_permission_mismatch_requires_safe_stop(self):
        with self.assertRaises(SafeStopRequired) as raised:
            CapabilityFacade().authorize(
                make_capability_envelope(declared_permissions=("workspace.write",))
            )

        self.assertEqual(raised.exception.code, "permission_mismatch")
        self.assertTrue(raised.exception.safe_stop)

    def test_completion_keeps_incomplete_provenance_blocked(self):
        cases = (
            ("policy_digest", {"policy_digest": UNKNOWN}),
            ("environment_digest", {"environment_digest": UNKNOWN}),
            ("workspace_digest", {"workspace_digest": UNKNOWN}),
            (
                "provider_identity.model",
                {"provider_identity": replace(make_envelope().provider_identity, model=UNKNOWN)},
            ),
            (
                "worker_artifact_identity.digest",
                {
                    "worker_artifact_identity": replace(
                        make_envelope().worker_artifact_identity, digest=UNKNOWN
                    )
                },
            ),
        )
        for expected_missing, overrides in cases:
            with self.subTest(expected_missing=expected_missing):
                envelope = make_envelope(
                    message_type="result",
                    payload={"status": "completed"},
                    **overrides,
                )
                with self.assertRaises(CompletionBlocked) as raised:
                    envelope.validate_worker_completion()
                self.assertIn(expected_missing, raised.exception.missing)


if __name__ == "__main__":
    unittest.main()
