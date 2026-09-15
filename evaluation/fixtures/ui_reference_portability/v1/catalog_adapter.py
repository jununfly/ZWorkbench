"""Independent HTML fixture for the UI Reference skills.

This fixture intentionally has no ZWorkbench imports, run model, or durable
owner. Its adapter uses ``data-ref`` and a static HTML component renderer to
exercise the same protocol with a different implementation vocabulary.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit


SCHEMA = "ui-ref-manifest/v1"
SOURCE_PATH = "catalog_adapter.py"
MAX_TOKEN_BYTES = 1024
MAX_LINK_BYTES = 1024
REF_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
HANDLE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
VIEWPORTS = {"compact", "wide"}
STATES = {
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
DECLARATIONS = (
    ("catalog.shell", "catalog shell", "component", None),
    ("catalog.items", "catalog item list", "list", "catalog.shell"),
    ("catalog.item", "catalog item", "list-item", "catalog.items"),
    ("catalog.add", "add item action", "action", "catalog.shell"),
)


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def manifest() -> Dict[str, Any]:
    source_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    refs = [
        {
            "ref": ref,
            "semantic": semantic,
            "kind": kind,
            "view": "catalog",
            "parent": parent,
            "source": {
                "repo_path": SOURCE_PATH,
                "symbol": "render_catalog",
                "content_digest": source_digest,
            },
        }
        for ref, semantic, kind, parent in DECLARATIONS
    ]
    semantics = [{key: value for key, value in ref.items() if key != "source"} for ref in refs]
    mapping = _digest({"schema": SCHEMA, "refs": semantics})
    return {
        "schema": SCHEMA,
        "refs": refs,
        "ui_map": mapping,
        "build": _digest({"mapping": mapping, "source": source_digest}),
    }


def _assert_declared(ref: str, current: Mapping[str, Any]) -> str:
    if not any(entry["ref"] == ref for entry in current["refs"]):
        raise ValueError("reference is not declared")
    return ref


def render_catalog(
    items: Iterable[Mapping[str, Any]], current: Optional[Mapping[str, Any]] = None
) -> str:
    current = current or manifest()
    shell = _assert_declared("catalog.shell", current)
    item_list = _assert_declared("catalog.items", current)
    item_ref = _assert_declared("catalog.item", current)
    add = _assert_declared("catalog.add", current)
    rows = "".join(
        '<li data-ref="{0}">{1}</li>'.format(
            item_ref, html.escape(str(item.get("label", "unknown")))
        )
        for item in items
    )
    return (
        '<catalog-shell data-ref="{shell}">'
        '<button type="button" data-ref="{add}">Add</button>'
        '<ul data-ref="{items}">{rows}</ul>'
        "</catalog-shell>"
    ).format(shell=shell, add=add, items=item_list, rows=rows)


_CATALOG_RUNTIME_SCRIPT = r"""
(() => {
  const initialItems = __INITIAL_ITEMS__;
  const mapping = __MAPPING__;
  const build = __BUILD__;
  const state = {
    items: initialItems.map((item, index) => ({label: item.label, key: "item-" + index})),
    enabled: false,
    sessionOpen: false,
    handles: new Map(),
    unmounted: new Map(),
    expired: new Set(),
    preview: null,
    selection: null,
    previousFocus: null,
    resources: 0,
    businessClicks: 0,
    copyAttempts: 0,
    copyOutcome: null,
    clipboardFailure: false,
    deepLinkTarget: null,
    hostUnloaded: false,
    reviewListeners: [],
    reviewEntryListener: null,
    beforeUnloadListener: null,
    displayState: new URLSearchParams(window.location.search).get("state") || null,
    businessEscapes: 0,
    reviewEscapes: 0,
  };

  const byId = (id) => document.getElementById(id);
  const list = byId("item-list");
  const panel = byId("review-panel");
  const overlay = document.querySelector("[data-review-overlay]");
  const status = byId("review-status");

  function addReviewListener(target, type, listener) {
    target.addEventListener(type, listener);
    state.reviewListeners.push({target: target, type: type, listener: listener});
  }

  function releaseReviewListeners() {
    for (const entry of state.reviewListeners) {
      entry.target.removeEventListener(entry.type, entry.listener);
    }
    state.reviewListeners = [];
  }

  function handle() {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  function viewport() {
    return window.innerWidth < 768 ? "compact" : "wide";
  }

  function assignHandle(item) {
    if (!state.sessionOpen) return null;
    if (state.handles.has(item.key)) return state.handles.get(item.key);
    const saved = state.unmounted.get(item.key);
    const value = saved ? saved.instance : handle();
    state.unmounted.delete(item.key);
    state.handles.set(item.key, value);
    return value;
  }

  function itemNode(item) {
    const node = document.createElement("li");
    node.tabIndex = 0;
    node.dataset.ref = "catalog.item";
    node.textContent = item.label;
    const instance = assignHandle(item);
    if (instance) node.dataset.instance = instance;
    if (state.enabled && state.sessionOpen) {
      node.addEventListener("mouseenter", () => preview(node));
      node.addEventListener("focus", () => preview(node));
    }
    node.addEventListener("click", () => {
      state.businessClicks += 1;
      status.textContent = "business action delivered";
    });
    return node;
  }

  function render() {
    list.textContent = "";
    if (state.displayState !== "empty" && state.displayState !== "unknown") {
      for (const item of state.items) list.appendChild(itemNode(item));
    }
    byId("empty-state").hidden = state.items.length !== 0 || state.displayState === "unknown";
    byId("unknown-state").hidden = state.displayState !== "unknown";
    byId("viewport").textContent = viewport();
  }

  function preview(node) {
    if (!state.enabled || !state.sessionOpen) return;
    state.preview = node.dataset.instance || null;
    node.dataset.preview = "true";
    status.textContent = state.preview ? "preview" : "no target";
  }

  function enable() {
    if (state.hostUnloaded) return;
    if (state.enabled && state.sessionOpen) {
      panel.hidden = false;
      overlay.hidden = false;
      byId("lock").focus();
      return;
    }
    state.previousFocus = document.activeElement;
    state.enabled = true;
    state.sessionOpen = true;
    state.resources = 4;
    panel.hidden = false;
    overlay.hidden = false;
    render();
    attachReviewListeners();
    state.resources = state.reviewListeners.length;
    byId("lock").focus();
  }

  function disable() {
    for (const instance of state.handles.values()) state.expired.add(instance);
    for (const entry of state.unmounted.values()) state.expired.add(entry.instance);
    state.enabled = false;
    state.sessionOpen = false;
    state.handles.clear();
    state.unmounted.clear();
    state.preview = null;
    state.selection = null;
    releaseReviewListeners();
    state.resources = 0;
    panel.hidden = true;
    overlay.hidden = true;
    render();
  }

  function endSession() {
    disable();
    status.textContent = "review session closed";
  }

  function lock() {
    if (state.preview && state.enabled) {
      state.selection = state.preview;
      status.textContent = "locked";
    }
  }

  async function copy() {
    if (!state.selection) {
      state.copyOutcome = "no-target";
      return;
    }
    state.copyAttempts += 1;
    const token = JSON.stringify({
      protocol: "ui-ref/v1",
      ref: "catalog.item",
      ui_map: mapping,
      build: build,
      viewport: viewport(),
      state: state.displayState || (state.items.length ? "normal" : "empty"),
      instance: state.selection,
    });
    try {
      if (state.clipboardFailure || !navigator.clipboard) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(token);
      state.copyOutcome = "copied";
      status.textContent = "copied";
    } catch (_) {
      state.copyOutcome = "copy-failed";
      status.textContent = "copy failed";
    }
  }

  function closePanel() {
    panel.hidden = true;
    const target = state.previousFocus && state.previousFocus.isConnected
      ? state.previousFocus
      : byId("review-entry");
    target.focus();
  }

  function onKeyDown(event) {
    if (event.key === "Escape" && state.enabled && !panel.hidden && panel.contains(document.activeElement)) {
      state.reviewEscapes += 1;
      closePanel();
      event.preventDefault();
    }
  }

  function attachReviewListeners() {
    if (state.reviewListeners.length) return;
    addReviewListener(document, "keydown", onKeyDown);
    addReviewListener(byId("lock"), "click", lock);
    addReviewListener(byId("copy"), "click", copy);
    addReviewListener(byId("close-panel"), "click", closePanel);
    addReviewListener(byId("disable"), "click", disable);
    addReviewListener(byId("end-session"), "click", endSession);
    addReviewListener(byId("reorder"), "click", reorder);
    addReviewListener(byId("rerender"), "click", rerender);
    addReviewListener(byId("unmount-first"), "click", unmountFirst);
    addReviewListener(byId("remount-first"), "click", remountFirst);
    addReviewListener(byId("delete-first"), "click", deleteFirst);
    addReviewListener(byId("set-clipboard-failure"), "click", () => { state.clipboardFailure = true; });
  }

  function unload() {
    if (state.hostUnloaded) return;
    disable();
    state.hostUnloaded = true;
    byId("review-entry").removeEventListener("click", state.reviewEntryListener);
    window.removeEventListener("beforeunload", state.beforeUnloadListener);
  }

  function resolve(instance) {
    if (state.expired.has(instance)) return {outcome: "expired"};
    for (const [key, value] of state.handles.entries()) {
      if (value === instance) return {outcome: "found", ref: "catalog.item", entity: key};
    }
    for (const entry of state.unmounted.values()) {
      if (entry.instance === instance) return {outcome: "unavailable", ref: "catalog.item"};
    }
    return {outcome: "expired"};
  }

  function reorder() {
    state.items.reverse();
    render();
  }

  function rerender() {
    render();
  }

  function unmountFirst() {
    const item = state.items.shift();
    if (!item) return;
    const instance = state.handles.get(item.key);
    state.handles.delete(item.key);
    state.unmounted.set(item.key, {label: item.label, instance: instance});
    render();
  }

  function remountFirst() {
    const entry = state.unmounted.entries().next().value;
    if (!entry) return;
    const key = entry[0];
    state.items.unshift({key: key, label: entry[1].label});
    state.handles.set(key, entry[1].instance);
    state.unmounted.delete(key);
    render();
  }

  function deleteFirst() {
    const item = state.items.shift();
    if (!item) return;
    const instance = state.handles.get(item.key);
    state.handles.delete(item.key);
    state.unmounted.delete(item.key);
    if (instance) state.expired.add(instance);
    render();
  }

  function analyseLink() {
    const params = new URLSearchParams(window.location.search);
    if (!params.has("ui_ref") && !params.has("ui_map")) return;
    state.deepLinkTarget = params.get("ui_map") === mapping ? params.get("ui_ref") : "incompatible";
  }

  byId("business-input").addEventListener("keydown", (event) => {
    if (event.key === "Escape") state.businessEscapes += 1;
  });
  state.reviewEntryListener = () => enable();
  state.beforeUnloadListener = () => unload();
  byId("review-entry").addEventListener("click", state.reviewEntryListener);
  window.addEventListener("beforeunload", state.beforeUnloadListener);

  window.__catalogReview = {
    snapshot() {
      return {
        enabled: state.enabled,
        viewport: viewport(),
        display_state: state.displayState || (state.items.length ? "normal" : "empty"),
        rows: Array.from(document.querySelectorAll("[data-ref='catalog.item']"), (node) => ({
          label: node.textContent,
          instance: node.dataset.instance || null,
        })),
        unmounted: Array.from(state.unmounted.values()),
        preview: state.preview,
        selection: state.selection,
        business_clicks: state.businessClicks,
        copy_attempts: state.copyAttempts,
        copy_outcome: state.copyOutcome,
        resources: state.resources,
        review_listeners: state.reviewListeners.length,
        session_handles: state.handles.size + state.unmounted.size,
        host_unloaded: state.hostUnloaded,
        deep_link_target: state.deepLinkTarget,
        remote_requests: 0,
        business_escapes: state.businessEscapes,
        review_escapes: state.reviewEscapes,
        active_element: document.activeElement && document.activeElement.id,
        persistent_storage: localStorage.length,
      };
    },
    resolve,
    setClipboardFailure(value) { state.clipboardFailure = Boolean(value); },
    disable,
    unload,
  };
  analyseLink();
  render();
})();
"""


def render_catalog_page(
    items: Iterable[Mapping[str, Any]], current: Optional[Mapping[str, Any]] = None
) -> str:
    """Render a self-contained browser fixture with an ephemeral review runtime."""
    current = current or manifest()
    _assert_declared("catalog.shell", current)
    _assert_declared("catalog.items", current)
    _assert_declared("catalog.item", current)
    _assert_declared("catalog.add", current)
    safe_items = [{"label": str(item.get("label", "unknown"))} for item in items]
    script = (
        _CATALOG_RUNTIME_SCRIPT.replace("__INITIAL_ITEMS__", json.dumps(safe_items))
        .replace("__MAPPING__", json.dumps(current["ui_map"]))
        .replace("__BUILD__", json.dumps(current["build"]))
    )
    return """<!doctype html>
<html><head><meta charset="utf-8"><title>Catalog</title>
<style>
  body { font-family: sans-serif; margin: 24px; }
  button, input { margin: 4px; padding: 6px; }
  li { margin: 8px; padding: 10px; border: 1px solid #ccc; width: 220px; }
  [data-review-overlay] { position: fixed; inset: 0; pointer-events: none; outline: 0; }
  #review-panel { border: 2px solid #3366cc; padding: 10px; margin-top: 12px; }
  [data-preview="true"] { outline: 2px solid orange; }
</style></head><body>
<button id="review-entry" type="button">Review</button>
<button id="reorder" type="button">Reorder</button>
<button id="rerender" type="button">Rerender</button>
<button id="unmount-first" type="button">Unmount first</button>
<button id="remount-first" type="button">Remount first</button>
<button id="delete-first" type="button">Delete first</button>
<input id="business-input" aria-label="Business input" value="">
<main data-ref="catalog.shell"><button id="catalog-add" type="button" data-ref="catalog.add">Add</button>
<ul id="item-list" data-ref="catalog.items"></ul>
<p id="empty-state" hidden>Empty</p><p id="unknown-state" hidden>Unknown</p></main>
<p>Viewport: <span id="viewport"></span></p>
<div id="business-dialog" hidden></div>
<div data-review-overlay hidden></div>
<section id="review-panel" hidden tabindex="-1" aria-label="Review panel">
  <button id="lock" type="button">Lock</button>
  <button id="copy" type="button">Copy</button>
  <button id="close-panel" type="button">Close panel</button>
  <button id="disable" type="button">Disable</button>
  <button id="end-session" type="button">End session</button>
  <button id="set-clipboard-failure" type="button">Inject clipboard failure</button>
  <p id="review-status" aria-live="polite"></p>
</section>
<script>""" + script + """</script>
</body></html>"""


def review_token(current: Mapping[str, Any], ref: str) -> str:
    _assert_declared(ref, current)
    token = json.dumps(
        {
            "protocol": "ui-ref/v1",
            "ref": ref,
            "ui_map": current["ui_map"],
            "build": current["build"],
            "viewport": "wide",
            "state": "unknown",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(token.encode("utf-8")) > MAX_TOKEN_BYTES:
        raise ValueError("token exceeds the size budget")
    return token


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _validate_ref(value: Any) -> None:
    if not isinstance(value, str) or len(value) > 128 or not REF_PATTERN.fullmatch(value):
        raise ValueError("reference name violates the naming contract")


def parse_review_token(raw: str) -> Dict[str, Any]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_TOKEN_BYTES:
        raise ValueError("token exceeds the size budget")

    def reject_duplicate_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("token repeats a field")
            value[key] = item
        return value

    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except (TypeError, ValueError) as error:
        raise ValueError("token is not valid JSON") from error
    required = {"protocol", "ref", "ui_map", "build", "viewport", "state"}
    allowed = required | {"instance"}
    if not isinstance(value, dict) or set(value) not in (required, allowed):
        raise ValueError("token fields are outside the whitelist")
    if any(not isinstance(item, str) for item in value.values()):
        raise ValueError("token fields have invalid types")
    if value["protocol"] != "ui-ref/v1":
        raise ValueError("unsupported token protocol")
    _validate_ref(value["ref"])
    if not _is_digest(value["ui_map"]) or not _is_digest(value["build"]):
        raise ValueError("token identity is not a sha256 digest")
    if value["viewport"] not in VIEWPORTS or value["state"] not in STATES:
        raise ValueError("token contains an invalid display value")
    if "instance" in value and HANDLE_PATTERN.fullmatch(value["instance"]) is None:
        raise ValueError("token instance handle is malformed")
    return value


def deep_link(current: Mapping[str, Any], ref: str) -> str:
    _assert_declared(ref, current)
    return "/catalog?" + urlencode({"ui_ref": ref, "ui_map": current["ui_map"]})


def parse_deep_link(raw: str) -> Dict[str, str]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_LINK_BYTES:
        raise ValueError("link exceeds the size budget")
    split = urlsplit(raw)
    if (
        split.scheme
        or split.netloc
        or not split.path.startswith("/")
        or "\\" in split.path
        or split.fragment
    ):
        raise ValueError("link must use a local relative entry point")
    try:
        pairs = parse_qsl(split.query, strict_parsing=True)
    except ValueError as error:
        raise ValueError("link query cannot be parsed") from error
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("link repeats a locating parameter")
        value[key] = item
    if set(value) != {"ui_ref", "ui_map"}:
        raise ValueError("link fields are outside the whitelist")
    _validate_ref(value["ui_ref"])
    if not _is_digest(value["ui_map"]):
        raise ValueError("link identity is not a sha256 digest")
    return value


def review_overlay(current: Mapping[str, Any], ref: str) -> str:
    _assert_declared(ref, current)
    return '<aside data-review-overlay data-ref="{0}"></aside>'.format(
        html.escape(ref, quote=True)
    )


def locate_source(current: Mapping[str, Any], ref: str) -> Dict[str, str]:
    entry = next((entry for entry in current["refs"] if entry["ref"] == ref), None)
    if entry is None:
        return {"outcome": "not-found"}
    source = Path(__file__).read_bytes()
    if hashlib.sha256(source).hexdigest() != entry["source"]["content_digest"]:
        return {"outcome": "source-mismatch"}
    return {"outcome": "found", "repo_path": entry["source"]["repo_path"]}


def browser_persistence() -> Dict[str, str]:
    return {}


def review_log() -> list:
    return ["target-selected"]
