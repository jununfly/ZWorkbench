from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from evaluation.runner import run_codex_c5_c6 as runner


class CodexC5C6RunnerTests(unittest.TestCase):
    def test_router_uses_available_loopback_port_and_exposes_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case_dir = Path(temporary)
            router = runner.start_router(
                case_dir,
                {
                    "primary": "fake-a",
                    "fallback": None,
                    "providers": {"fake-a": {"endpoint": "http://127.0.0.1:1"}},
                },
            )
            try:
                self.assertTrue(router["endpoint"].startswith("http://127.0.0.1:"))
                self.assertNotEqual(router["endpoint"], "http://127.0.0.1:11434")
                self.assertEqual(router["endpoint"].rsplit(":", 1)[-1], router["port"] and str(router["port"]))
            finally:
                runner.stop_component(router)

    def test_codex_client_uses_non_reserved_loopback_provider_override(self) -> None:
        client = runner.CodexClient(
            Path("/tmp/c5-runner-test"),
            None,
            "read-only",
            "never",
            "http://127.0.0.1:43123",
        )
        command = client.command()
        self.assertIn('model_provider="c5-loopback"', command)
        self.assertNotIn('model_provider="ollama"', command)
        self.assertIn('model_providers.c5-loopback.base_url="http://127.0.0.1:43123/v1"', command)


if __name__ == "__main__":
    unittest.main()
