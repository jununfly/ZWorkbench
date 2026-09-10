"""The ui-ref/v1 feedback token and the local review deep link.

A token locates a semantic element for discussion.  It is not a credential, an
approval, a state-restoration instruction or an execution entry point: the
``state`` field describes what a reviewer saw, and nothing in the token
authorises an action.

Every field is whitelisted.  Prompts, run titles, full run identifiers, raw
events, owner snapshots, credentials, input contents and local absolute paths
must never reach a token, and free-form context is not accepted.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from .ui_ref import UiRefError


TOKEN_PROTOCOL = "ui-ref/v1"
MAX_TOKEN_BYTES = 1024

VIEWPORTS = frozenset({"compact", "wide"})
STATES = frozenset(
    {
        "draft",
        "loading",
        "empty",
        "created",
        "running",
        "recovering",
        "completed",
        "failed",
        "denied",
        "safe-stopped",
        "unknown",
        "not-applicable",
    }
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_HANDLE_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class TokenError(UiRefError):
    """A token or deep link violates the ui-ref/v1 contract."""


def build_token(
    manifest: Dict[str, Any],
    ref: str,
    *,
    viewport: str,
    state: str,
    instance: Optional[str] = None,
) -> str:
    """Serialise one review token from a validated manifest.

    Values come from the manifest and the allowed presentation metadata only;
    the caller cannot inject an extra field.
    """
    if viewport not in VIEWPORTS:
        raise TokenError("viewport must be one of {0}".format(sorted(VIEWPORTS)))
    if state not in STATES:
        raise TokenError("state {0!r} is not an allowed display state".format(state))
    if not any(entry["ref"] == ref for entry in manifest["refs"]):
        raise TokenError("reference {0!r} is not declared in this manifest".format(ref))

    if instance is not None and not _HANDLE_PATTERN.match(instance):
        raise TokenError(
            "instance handle must be 32 lowercase hexadecimal characters"
        )

    payload = {
        "protocol": TOKEN_PROTOCOL,
        "ref": ref,
        "ui_map": manifest["ui_map"],
        "build": manifest["build"],
        "viewport": viewport,
        "state": state,
    }
    if instance is not None:
        payload["instance"] = instance
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_REQUIRED_FIELDS = ("protocol", "ref", "ui_map", "build", "viewport", "state")
_ALLOWED_FIELDS = _REQUIRED_FIELDS + ("instance",)
_REF_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*$")
MAX_REF_LENGTH = 128


def _reject(outcome: str, detail: str) -> Dict[str, Any]:
    """Describe a rejection without echoing the offending input."""
    return {"outcome": outcome, "detail": detail}


def parse_token(raw: str) -> Dict[str, Any]:
    """Parse one review token as data.

    The input is never interpreted as HTML, script, an instruction or a path,
    and a rejection never echoes it back.  Duplicate keys are refused rather
    than resolved last-one-wins, which a plain JSON load would do silently.
    """
    if len(raw.encode("utf-8")) > MAX_TOKEN_BYTES:
        return _reject("too-large", "token exceeds the size budget")

    seen: Dict[str, int] = {}

    def _hook(pairs: Any) -> Dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                seen[key] = seen.get(key, 1) + 1
            result[key] = value
        return result

    try:
        payload = json.loads(raw, object_pairs_hook=_hook)
    except ValueError:
        return _reject("malformed", "token is not valid JSON")
    if not isinstance(payload, dict):
        return _reject("malformed", "token must be a JSON object")
    if seen:
        return _reject("duplicate-key", "token repeats a field")

    unknown = sorted(set(payload) - set(_ALLOWED_FIELDS))
    if unknown:
        return _reject("unknown-key", "token carries a field outside the whitelist")
    missing = [field for field in _REQUIRED_FIELDS if field not in payload]
    if missing:
        return _reject("missing-field", "token omits a required field")
    if any(not isinstance(value, str) for value in payload.values()):
        return _reject("invalid-type", "every token field must be a string")
    if payload["protocol"] != TOKEN_PROTOCOL:
        return _reject("unknown-protocol", "token protocol version is not supported")

    ref = payload["ref"]
    if len(ref) > MAX_REF_LENGTH or not _REF_PATTERN.match(ref):
        return _reject("invalid-value", "reference name violates the naming contract")
    for field in ("ui_map", "build"):
        if not _SHA256_PATTERN.match(payload[field]):
            return _reject("invalid-value", "{0} must be a sha256 digest".format(field))
    if payload["viewport"] not in VIEWPORTS:
        return _reject("invalid-value", "viewport class is not allowed")
    if payload["state"] not in STATES:
        return _reject("invalid-value", "display state is not allowed")
    if "instance" in payload and not _HANDLE_PATTERN.match(payload["instance"]):
        return _reject("invalid-value", "instance handle is malformed")

    return {"outcome": "valid", "token": dict(payload)}


MAX_LINK_BYTES = 1024
_LINK_PARAMETERS = ("ui_ref", "ui_map")


def build_deep_link(manifest: Dict[str, Any], ref: str) -> str:
    """Build a local link that locates one declared semantic element.

    The link carries the two locating parameters only.  It performs pure UI
    navigation to the view the manifest assigns, and cannot load a run, restore
    state, trigger preflight or apply anything.
    """
    from urllib.parse import urlencode

    for entry in manifest["refs"]:
        if entry["ref"] == ref:
            query = urlencode([("ui_ref", ref), ("ui_map", manifest["ui_map"])])
            return "/{0}?{1}".format(entry["view"], query)
    raise TokenError("reference {0!r} is not declared in this manifest".format(ref))


def parse_deep_link(raw: str) -> Dict[str, Any]:
    """Parse one local review link.

    A repeated locating parameter, an unknown parameter or an oversized link is
    refused: the link is a locator, never an instruction.
    """
    from urllib.parse import parse_qsl, urlsplit

    if len(raw.encode("utf-8")) > MAX_LINK_BYTES:
        return _reject("too-large", "link exceeds the size budget")

    try:
        pairs = parse_qsl(urlsplit(raw).query, strict_parsing=True)
    except ValueError:
        return _reject("malformed", "link query cannot be parsed")

    collected: Dict[str, str] = {}
    for key, value in pairs:
        if key in collected:
            return _reject("duplicate-parameter", "link repeats a locating parameter")
        collected[key] = value

    unknown = sorted(set(collected) - set(_LINK_PARAMETERS))
    if unknown:
        return _reject("unknown-parameter", "link carries a parameter outside the whitelist")
    missing = [name for name in _LINK_PARAMETERS if name not in collected]
    if missing:
        return _reject("missing-parameter", "link omits a locating parameter")

    ref = collected["ui_ref"]
    if len(ref) > MAX_REF_LENGTH or not _REF_PATTERN.match(ref):
        return _reject("invalid-value", "reference name violates the naming contract")
    if not _SHA256_PATTERN.match(collected["ui_map"]):
        return _reject("invalid-value", "ui_map must be a sha256 digest")

    return {"outcome": "valid", "ui_ref": ref, "ui_map": collected["ui_map"]}
