"""Value-level credential-shape scanning for real-architecture seams.

Roadmap 1-8-2 / 1-8-3: protocol/structural surfaces REJECT credential-shaped
values (fail-closed); free-text content surfaces REDACT them on the way into
durable sinks.  Field-NAME rejection (``api_key`` / ``token`` / ...) stays in
``worker_contract._reject_secrets`` and
``composition._reject_provider_secret_fields``; this module classifies only
the value shape.

Shapes: VolcEngine ``ark-`` (8+ body chars), OpenAI-style ``sk-`` (12+), AWS
``AKIA`` (12+ digits).  A leading lookbehind keeps word-embedded look-alikes
(``disk-full-read-access`` -> "sk-full-read-access") out of the match,
mirroring the owner-side scanner.  Test fixtures must build these shapes by
runtime concatenation, never as literals: GitHub push protection rejects the
ark- shape even as a test fixture.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

CREDENTIAL_SHAPED = re.compile(
    r"(?<![A-Za-z0-9])(?:ark-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{12,})"
)
REDACTED = "<redacted>"


def contains_credential_shape(text: str) -> bool:
    """Whether ``text`` contains a credential-shaped substring."""

    return isinstance(text, str) and CREDENTIAL_SHAPED.search(text) is not None


def redact_text(text: str) -> str:
    """Replace credential-shaped substrings with ``<redacted>``."""

    return CREDENTIAL_SHAPED.sub(REDACTED, text)


def reject_credential_shaped_values(value: Any, field_name: str) -> None:
    """Reject any string *value* leaf containing a credential-shaped value.

    Recurses mappings and sequences (values only, never mapping keys -- the
    owner-side scanners share that contract).  Raises ``ValueError`` so each
    caller wraps it in its own fail-closed error type and code.
    """

    def visit(current: Any, path: str) -> None:
        if isinstance(current, Mapping):
            for key, item in current.items():
                visit(item, f"{path}.{key}")
        elif isinstance(current, (list, tuple)):
            for index, item in enumerate(current):
                visit(item, f"{path}[{index}]")
        elif isinstance(current, str):
            if CREDENTIAL_SHAPED.search(current):
                raise ValueError(
                    f"{field_name} contains a credential-shaped value at {path}"
                )

    visit(value, field_name)


def redact_credential_shaped_values(value: Any) -> Any:
    """Return a copy of ``value`` with credential-shaped string leaves redacted.

    Mappings and sequences are rebuilt; every other value is returned as-is.
    """

    if isinstance(value, Mapping):
        return {key: redact_credential_shaped_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_credential_shaped_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_credential_shaped_values(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value
