"""Behavior tests for the ui-ref/v1 feedback token and local deep link."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zworkbench.ui_ref import SourceAnchor, UiRefDeclaration, UiRefRegistry
from zworkbench.ui_token import (
    TOKEN_PROTOCOL,
    TokenError,
    build_token,
    build_deep_link,
    parse_deep_link,
    parse_token,
)


def sample_manifest():
    registry = UiRefRegistry()
    for ref, name in (
        ("home.root", "工作台首页"),
        ("home.record-list.item", "工作记录项"),
    ):
        registry.declare(
            UiRefDeclaration(
                ref=ref,
                semantic_zh=name,
                kind="region",
                view="home",
                source=SourceAnchor(
                    repo_path="ui/home.py",
                    symbol="render_home",
                    content_digest="a" * 64,
                ),
            )
        )
    return registry.build_manifest(build="b" * 64)


class BuildingATokenTests(unittest.TestCase):
    def test_a_token_carries_the_whitelisted_fields_only(self):
        manifest = sample_manifest()
        token = build_token(manifest, "home.root", viewport="wide", state="running")
        self.assertEqual(
            sorted(json.loads(token)),
            ["build", "protocol", "ref", "state", "ui_map", "viewport"],
        )

    def test_a_token_pins_the_protocol_and_manifest_identity(self):
        manifest = sample_manifest()
        payload = json.loads(build_token(manifest, "home.root", viewport="wide", state="running"))
        self.assertEqual(payload["protocol"], TOKEN_PROTOCOL)
        self.assertEqual(payload["ui_map"], manifest["ui_map"])
        self.assertEqual(payload["build"], manifest["build"])

    def test_an_instance_handle_is_included_when_supplied(self):
        manifest = sample_manifest()
        handle = "0123456789abcdef" * 2
        payload = json.loads(
            build_token(
                manifest,
                "home.record-list.item",
                viewport="compact",
                state="unknown",
                instance=handle,
            )
        )
        self.assertEqual(payload["instance"], handle)

    def test_a_token_without_an_instance_omits_the_field_entirely(self):
        manifest = sample_manifest()
        payload = json.loads(build_token(manifest, "home.root", viewport="wide", state="running"))
        self.assertNotIn("instance", payload)

    def test_an_instance_handle_that_is_not_32_hex_characters_is_rejected(self):
        manifest = sample_manifest()
        for bad in ("short", "A" * 32, "0" * 31, "0" * 33, "run-abc-123"):
            with self.assertRaises(TokenError):
                build_token(
                    manifest,
                    "home.record-list.item",
                    viewport="wide",
                    state="running",
                    instance=bad,
                )

    def test_an_undeclared_reference_cannot_become_a_token(self):
        with self.assertRaises(TokenError):
            build_token(sample_manifest(), "home.ghost", viewport="wide", state="running")

    def test_an_unknown_viewport_class_is_rejected(self):
        with self.assertRaises(TokenError):
            build_token(sample_manifest(), "home.root", viewport="mobile", state="running")

    def test_a_state_outside_the_allowed_vocabulary_is_rejected(self):
        with self.assertRaises(TokenError):
            build_token(sample_manifest(), "home.root", viewport="wide", state="probably-fine")

    def test_a_token_stays_within_the_size_budget(self):
        manifest = sample_manifest()
        token = build_token(
            manifest,
            "home.record-list.item",
            viewport="wide",
            state="safe-stopped",
            instance="0" * 32,
        )
        self.assertLessEqual(len(token.encode("utf-8")), 1024)

class ParsingAValidTokenTests(unittest.TestCase):
    def test_a_round_tripped_token_parses_back_to_its_fields(self):
        manifest = sample_manifest()
        token = build_token(manifest, "home.root", viewport="wide", state="running")
        parsed = parse_token(token)
        self.assertEqual(parsed["outcome"], "valid")
        self.assertEqual(parsed["token"]["ref"], "home.root")
        self.assertEqual(parsed["token"]["ui_map"], manifest["ui_map"])

    def test_a_parsed_token_without_an_instance_reports_no_instance(self):
        manifest = sample_manifest()
        token = build_token(manifest, "home.root", viewport="wide", state="running")
        self.assertNotIn("instance", parse_token(token)["token"])


class RejectingAMalformedTokenTests(unittest.TestCase):
    """Structured errors, no guessing, and no echo of the offending input."""

    def _reject(self, raw, expected):
        parsed = parse_token(raw)
        self.assertEqual(parsed["outcome"], expected)
        self.assertNotIn("token", parsed)
        return parsed

    def test_a_duplicate_key_is_rejected_rather_than_last_one_wins(self):
        raw = (
            '{"protocol":"ui-ref/v1","ref":"home.root","ref":"home.evil",'
            '"ui_map":"' + "a" * 64 + '","build":"' + "b" * 64 + '",'
            '"viewport":"wide","state":"running"}'
        )
        self._reject(raw, "duplicate-key")

    def test_an_unknown_key_is_rejected(self):
        raw = (
            '{"protocol":"ui-ref/v1","ref":"home.root",'
            '"ui_map":"' + "a" * 64 + '","build":"' + "b" * 64 + '",'
            '"viewport":"wide","state":"running","note":"free text"}'
        )
        self._reject(raw, "unknown-key")

    def test_a_missing_required_field_is_rejected(self):
        raw = (
            '{"protocol":"ui-ref/v1","ref":"home.root",'
            '"ui_map":"' + "a" * 64 + '","viewport":"wide","state":"running"}'
        )
        self._reject(raw, "missing-field")

    def test_an_unknown_protocol_version_is_rejected(self):
        raw = (
            '{"protocol":"ui-ref/v2","ref":"home.root",'
            '"ui_map":"' + "a" * 64 + '","build":"' + "b" * 64 + '",'
            '"viewport":"wide","state":"running"}'
        )
        self._reject(raw, "unknown-protocol")

    def test_a_wrong_value_type_is_rejected(self):
        raw = (
            '{"protocol":"ui-ref/v1","ref":123,'
            '"ui_map":"' + "a" * 64 + '","build":"' + "b" * 64 + '",'
            '"viewport":"wide","state":"running"}'
        )
        self._reject(raw, "invalid-type")

    def test_a_token_over_the_size_limit_is_rejected(self):
        raw = '{"protocol":"ui-ref/v1","ref":"' + "a" * 2000 + '"}'
        self._reject(raw, "too-large")

    def test_malformed_json_is_rejected(self):
        self._reject("not json at all", "malformed")

    def test_a_json_array_is_rejected(self):
        self._reject('["ui-ref/v1"]', "malformed")

    def test_an_invalid_enum_value_is_rejected(self):
        raw = (
            '{"protocol":"ui-ref/v1","ref":"home.root",'
            '"ui_map":"' + "a" * 64 + '","build":"' + "b" * 64 + '",'
            '"viewport":"mobile","state":"running"}'
        )
        self._reject(raw, "invalid-value")

    def test_a_rejection_does_not_echo_the_offending_input(self):
        raw = (
            '{"protocol":"ui-ref/v1","ref":"<script>alert(1)</script>",'
            '"ui_map":"' + "a" * 64 + '","build":"' + "b" * 64 + '",'
            '"viewport":"wide","state":"running"}'
        )
        parsed = parse_token(raw)
        self.assertEqual(parsed["outcome"], "invalid-value")
        self.assertNotIn("script", json.dumps(parsed, ensure_ascii=False))

    def test_a_reference_is_never_interpreted_as_a_path_or_markup(self):
        for hostile in ("../../etc/passwd", "<b>home.root</b>", "home.root;rm -rf /"):
            raw = json.dumps(
                {
                    "protocol": "ui-ref/v1",
                    "ref": hostile,
                    "ui_map": "a" * 64,
                    "build": "b" * 64,
                    "viewport": "wide",
                    "state": "running",
                }
            )
            self.assertEqual(parse_token(raw)["outcome"], "invalid-value")

class TokenCarriesNoBusinessDataTests(unittest.TestCase):
    """Pollute every allowed input with sensitive values and check the token."""

    FORBIDDEN = (
        "sk-live-abcdef1234567890",
        "run-01J8XYZABCDEF",
        "Bearer eyJhbGciOi",
        "/Users/someone/Documents/workspace",
        "重构支付网关的密钥轮换",
        "session=deadbeefcafe",
    )

    def test_no_forbidden_value_can_reach_a_token(self):
        manifest = sample_manifest()
        token = build_token(
            manifest,
            "home.record-list.item",
            viewport="wide",
            state="running",
            instance="0" * 32,
        )
        for secret in self.FORBIDDEN:
            self.assertNotIn(secret, token)

    def test_a_polluted_state_value_is_rejected_not_carried(self):
        manifest = sample_manifest()
        with self.assertRaises(TokenError):
            build_token(
                manifest,
                "home.root",
                viewport="wide",
                state="running; prompt=重构支付网关",
            )

    def test_the_token_reveals_no_semantic_copy_or_source_path(self):
        manifest = sample_manifest()
        token = build_token(manifest, "home.root", viewport="wide", state="running")
        self.assertNotIn("工作台首页", token)
        self.assertNotIn("ui/home.py", token)

    def test_a_parsed_token_exposes_only_whitelisted_fields(self):
        manifest = sample_manifest()
        token = build_token(
            manifest,
            "home.record-list.item",
            viewport="wide",
            state="running",
            instance="0" * 32,
        )
        parsed = parse_token(token)
        self.assertEqual(
            sorted(parsed["token"]),
            ["build", "instance", "protocol", "ref", "state", "ui_map", "viewport"],
        )


class TokenIsNotAnAuthorisationTests(unittest.TestCase):
    def test_a_parsed_token_yields_no_action_or_approval_field(self):
        manifest = sample_manifest()
        parsed = parse_token(build_token(manifest, "home.root", viewport="wide", state="completed"))
        for forbidden in ("action", "approval", "effect", "run_id", "restore", "command"):
            self.assertNotIn(forbidden, parsed["token"])

    def test_a_completed_state_is_presentation_only(self):
        manifest = sample_manifest()
        parsed = parse_token(build_token(manifest, "home.root", viewport="wide", state="completed"))
        self.assertEqual(parsed["token"]["state"], "completed")
        self.assertEqual(sorted(parsed), ["outcome", "token"])

class BuildingADeepLinkTests(unittest.TestCase):
    """A link locates an existing element; it restores no business state."""

    def test_a_link_carries_only_the_two_locating_parameters(self):
        from urllib.parse import parse_qs, urlsplit

        manifest = sample_manifest()
        link = build_deep_link(manifest, "home.root")
        query = parse_qs(urlsplit(link).query, strict_parsing=True)
        self.assertEqual(sorted(query), ["ui_map", "ui_ref"])
        self.assertEqual(query["ui_ref"], ["home.root"])
        self.assertEqual(query["ui_map"], [manifest["ui_map"]])

    def test_a_link_omits_build_state_and_instance(self):
        manifest = sample_manifest()
        link = build_deep_link(manifest, "home.record-list.item")
        for excluded in ("build", "state", "instance", "run_id", "run="):
            self.assertNotIn(excluded, link)

    def test_a_link_targets_the_view_the_manifest_assigns(self):
        manifest = sample_manifest()
        self.assertIn("/home", build_deep_link(manifest, "home.root"))

    def test_a_link_uses_a_local_entry_point(self):
        manifest = sample_manifest()
        self.assertTrue(build_deep_link(manifest, "home.root").startswith("/"))

    def test_an_undeclared_reference_cannot_become_a_link(self):
        with self.assertRaises(TokenError):
            build_deep_link(sample_manifest(), "home.ghost")


class ParsingADeepLinkTests(unittest.TestCase):
    def test_a_round_tripped_link_parses_back_to_its_parameters(self):
        manifest = sample_manifest()
        parsed = parse_deep_link(build_deep_link(manifest, "home.root"))
        self.assertEqual(parsed["outcome"], "valid")
        self.assertEqual(parsed["ui_ref"], "home.root")
        self.assertEqual(parsed["ui_map"], manifest["ui_map"])

    def test_a_repeated_locating_parameter_is_rejected(self):
        manifest = sample_manifest()
        raw = "/home?ui_ref=home.root&ui_ref=home.evil&ui_map=" + manifest["ui_map"]
        parsed = parse_deep_link(raw)
        self.assertEqual(parsed["outcome"], "duplicate-parameter")
        self.assertNotIn("ui_ref", parsed)

    def test_an_unknown_parameter_is_rejected(self):
        manifest = sample_manifest()
        raw = "/home?ui_ref=home.root&ui_map=" + manifest["ui_map"] + "&run_id=01J8XYZ"
        self.assertEqual(parse_deep_link(raw)["outcome"], "unknown-parameter")

    def test_a_missing_locating_parameter_is_rejected(self):
        self.assertEqual(parse_deep_link("/home?ui_ref=home.root")["outcome"], "missing-parameter")

    def test_an_oversized_link_is_rejected(self):
        raw = "/home?ui_ref=" + "a" * 2000 + "&ui_map=" + "b" * 64
        self.assertEqual(parse_deep_link(raw)["outcome"], "too-large")

    def test_an_invalid_reference_in_a_link_is_rejected(self):
        raw = "/home?ui_ref=../../etc/passwd&ui_map=" + "b" * 64
        self.assertEqual(parse_deep_link(raw)["outcome"], "invalid-value")

    def test_a_link_rejection_does_not_echo_the_input(self):
        raw = "/home?ui_ref=<script>alert(1)</script>&ui_map=" + "b" * 64
        parsed = parse_deep_link(raw)
        self.assertNotIn("script", json.dumps(parsed, ensure_ascii=False))

    def test_an_external_origin_is_not_a_local_deep_link(self):
        raw = "https://external.example/home?ui_ref=home.root&ui_map=" + "b" * 64

        parsed = parse_deep_link(raw)

        self.assertEqual(parsed["outcome"], "invalid-origin")

    def test_a_backslash_prefixed_path_cannot_be_normalised_to_an_external_origin(self):
        raw = "/\\\\evil.example/home?ui_ref=home.root&ui_map=" + "b" * 64

        parsed = parse_deep_link(raw)

        self.assertEqual(parsed["outcome"], "invalid-origin")

class TokenResolvesAgainstASessionTests(unittest.TestCase):
    """A token resolves structure/code separately from the live DOM instance."""

    def setUp(self) -> None:
        from zworkbench.ui_runtime import ReviewSession

        self.manifest = sample_manifest()
        self.session = ReviewSession(self.manifest)

    def test_a_token_with_a_live_handle_locates_that_instance(self):
        handle = self.session.mount("home.record-list.item", entity_key="e1")
        self.session.mount("home.record-list.item", entity_key="e2")
        token = build_token(
            self.manifest,
            "home.record-list.item",
            viewport="wide",
            state="running",
            instance=handle,
        )
        parsed = parse_token(token)
        located = self.session.resolve_instance(parsed["token"]["instance"])
        self.assertEqual(located["outcome"], "found")
        self.assertEqual(self.session.entity_key_of(located["instance"]), "e1")

    def test_a_token_from_a_closed_session_is_expired(self):
        handle = self.session.mount("home.record-list.item", entity_key="e1")
        token = build_token(
            self.manifest,
            "home.record-list.item",
            viewport="wide",
            state="running",
            instance=handle,
        )
        self.session.close()
        parsed = parse_token(token)
        self.assertEqual(
            self.session.resolve_instance(parsed["token"]["instance"])["outcome"], "expired"
        )

    def test_a_token_without_a_handle_is_ambiguous_across_repeated_items(self):
        self.session.mount("home.record-list.item", entity_key="e1")
        self.session.mount("home.record-list.item", entity_key="e2")
        token = build_token(
            self.manifest, "home.record-list.item", viewport="wide", state="running"
        )
        parsed = parse_token(token)
        self.assertNotIn("instance", parsed["token"])
        located = self.session.resolve_structural(parsed["token"]["ref"])
        self.assertEqual(located["outcome"], "ambiguous")

    def test_a_token_for_a_hidden_target_is_unavailable(self):
        token = build_token(self.manifest, "home.root", viewport="wide", state="running")
        parsed = parse_token(token)
        located = self.session.resolve_structural(parsed["token"]["ref"])
        self.assertEqual(located["outcome"], "unavailable")

    def test_a_stale_ui_map_is_incompatible_before_any_instance_lookup(self):
        from zworkbench.ui_ref import resolve

        token = build_token(self.manifest, "home.root", viewport="wide", state="running")
        parsed = parse_token(token)
        structural = resolve(self.manifest, parsed["token"]["ref"], ui_map="0" * 64)
        self.assertEqual(structural["outcome"], "incompatible")


if __name__ == "__main__":
    unittest.main()
