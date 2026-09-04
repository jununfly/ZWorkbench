#!/usr/bin/env bash
#
# Owner-facing, one-shot real Codex app-server + Ark staging wizard.
# This is deliberately separate from the default local_read_only product path.

set -euo pipefail

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
RUNNER="$REPO_ROOT/scripts/run_real_codex_provider_staging.py"
EVIDENCE_ROOT="${ZWB_REMOTE_CODEX_EVIDENCE_DIR:-$REPO_ROOT/evaluation/evidence/remote-codex-provider}"
CODEX="${CODEX_EXECUTABLE:-/opt/homebrew/bin/codex}"
BASE_URL="https://ark.cn-beijing.volces.com/api/coding/v3"
REGION="cn-beijing"
PROJECT_FINGERPRINT=""
ARK_API_KEY=""

say() { printf '  %s\n' "$1"; }
warn() { printf '  ⚠ %s\n' "$1"; }
ask() {
  local prompt="$1" input
  printf '  %s ' "$prompt"
  read -r input || true
  printf -v REPLY_VALUE '%s' "$input"
}
confirm() {
  local prompt="$1" input
  printf '  ? %s [y/N] ' "$prompt"
  read -r input || true
  [[ "$input" =~ ^[Yy] ]]
}

printf '\n  Optional real Codex runtime + Ark read-only staging\n\n'
say "This run starts the installed Codex app-server 0.139.0 for exactly one synthetic, read-only turn."
say "It uses a new case-local workspace/owner DB and a private temporary CODEX_HOME plus redacted event log."
say "It does not use the real ZWorkbench workspace, plugins, apps, tools, callbacks, tasks, Webhooks, backups or retries."
say "The API key is requested only after the checks below, read hidden, and passed through stdin."
if ! confirm "Proceed to the account and safety checks before any key is requested?"; then
  say "Stopped before any credential was requested or network access occurred."
  exit 0
fi

say "Fixed Ark base URL: $BASE_URL"
say "Fixed model: ark-code-latest"
say "Fixed account/data region for this helper: cn-beijing"
if [[ ! -x "$CODEX" ]]; then
  warn "Codex executable is missing or not executable: $CODEX"
  exit 1
fi

ask "Confirm actual Ark account/data region [enter keeps cn-beijing]:"
REGION="${REPLY_VALUE:-cn-beijing}"
if [[ "$REGION" != "cn-beijing" ]]; then
  warn "This helper only accepts cn-beijing; do not translate or infer another region."
  exit 1
fi

say "project_fingerprint means SHA-256 of the actual Ark Project ID or billing-scope ID that owns this request."
say "Do not enter ZWorkbench, a local workspace/project name, model, endpoint, region, API Key, or API Key fingerprint."
say 'Generate locally with: printf %s "$ARK_PROJECT_ID" | shasum -a 256 | awk '\''{print $1}'\'''
ask "Ark Project/billing ID fingerprint [64 hex characters]:"
PROJECT_FINGERPRINT="$REPLY_VALUE"
if [[ ! "$PROJECT_FINGERPRINT" =~ ^[0-9A-Fa-f]{64}$ ]]; then
  warn "Project fingerprint must be exactly 64 hexadecimal characters."
  exit 1
fi

if ! confirm "Have you confirmed Provider=Volcengine Ark, model=ark-code-latest, region=cn-beijing and this project/billing fingerprint?"; then
  warn "Provider identity is not confirmed; stopping before credential input."
  exit 1
fi
if ! confirm "Have you confirmed the API key scope and its disable/delete/revocation path?"; then
  warn "API key lifecycle is not confirmed; stopping before credential input."
  exit 1
fi
if ! confirm "Have you confirmed the Ark Coding endpoint data categories, retention and deletion basis for this synthetic turn?"; then
  warn "Data/retention scope is not confirmed; stopping before credential input."
  exit 1
fi
if ! confirm "Have you inventoried any Provider-side task/run/queue, scheduler, Webhook, backup, file and response resources?"; then
  warn "Provider resource inventory is not confirmed; stopping before credential input."
  exit 1
fi
if ! confirm "Have you confirmed the local stop, cleanup and Provider-side exit owner/path?"; then
  warn "Exit path is not confirmed; stopping before credential input."
  exit 1
fi
if ! confirm "Authorize exactly one synthetic, case-local, read-only Codex turn now, with a 90-second limit and no retry?"; then
  warn "One-time runtime authorization was not granted; stopping before credential input."
  exit 1
fi

printf '  Ark API key (hidden; never paste it into chat): '
read -rs ARK_API_KEY || true
printf '\n'
if [[ -z "$ARK_API_KEY" ]]; then
  warn "No API key entered; stopping before network access."
  unset ARK_API_KEY
  exit 1
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
evidence_dir="$EVIDENCE_ROOT/${stamp}-$$"
mkdir -m 700 -p "$evidence_dir"
say "Case-local evidence directory: $evidence_dir"
set +e
printf '%s' "$ARK_API_KEY" | python3 "$RUNNER" \
  --output "$evidence_dir" \
  --codex "$CODEX" \
  --region "$REGION" \
  --project-fingerprint "$PROJECT_FINGERPRINT" \
  --timeout 90
status=$?
set -e
unset ARK_API_KEY
say "The API key has been removed from this wizard's shell variable."
say "Only share the redacted summary path: $evidence_dir/summary.json"
say "A successful runtime turn is not production approval and does not prove H4/H5, failover or Provider-side exit."
exit "$status"
