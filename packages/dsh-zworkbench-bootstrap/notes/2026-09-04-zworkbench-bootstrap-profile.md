# Agent Note: ZWorkbench bootstrap profile

Status: implemented

English | [中文](2026-09-04-zworkbench-bootstrap-profile.zh.md)

## Problem

ZWorkbench starts DSH as an external artifact and needs a small, versioned process handshake before Worker capabilities are introduced. The ordinary `dsh-headless` profile creates an Agent and prints task text, so its stdout cannot be consumed as an all-JSONL bootstrap stream. Adding handshake records to that profile would also mix a bridge protocol with the user-facing task surface.

## Decision

ZDSHarness ships `@deepseek-ai/dsh-zworkbench-bootstrap` as a separate profile bundle and exposes the `zworkbench-bootstrap` profile template. Its plugin creates one empty DSH Session, emits exactly `bootstrap.started` and `bootstrap.ready` under `zworkbench.dsh.bootstrap/v1`, waits for Loader settlement and Session flush before requesting the launcher's bounded exit. The parent Run and profile identity come from launcher-owned `ZWORKBENCH_RUN_ID` and `ZWORKBENCH_DSH_PROFILE` variables. The plugin does not create an Agent, call a Provider, print task output, or write ZWorkbench state.

## Consequences

The external adapter can consume a strict JSONL stream and correlate one real DSH-owned Session to its parent Run without parsing task output or reading DSH storage. Ordinary headless behavior remains unchanged. The profile adds one shipped bundle to the installation dependency closure and leaves the Worker handshake, coding, and Provider behavior to later bridges.

## Alternatives considered

**Add records to `dsh-headless`.** Rejected because the profile's final assistant output is plain text and would violate the bootstrap stream's all-JSONL contract.

**Have ZWorkbench wrap or inspect DSH session files.** Rejected because it would make the external owner depend on DSH's storage format and would not prove the child emitted an identity at the process boundary.

**Create a second Agent loop for bootstrap.** Rejected because H1 needs only a DSH-owned Session identity and profile settlement; an additional loop would duplicate durable behavior before the Worker seam exists.

## Testing

The bundle unit tests assert exact message order, shared Session identity, launcher identity, flush-before-exit, and missing-identity rejection. The built CLI e2e asserts the shipped profile emits only the two protocol records and exits successfully.
