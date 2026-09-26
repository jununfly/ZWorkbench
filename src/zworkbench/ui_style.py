"""The visual system for the server-rendered workbench.

Selectors here address elements structurally: by tag, by document position and
by the shape of the markup. None of them mention ``data-ui-ref``.

That restriction is the point of this module rather than a stylistic
preference. A reference carries semantic identity across releases -- the PRD
requires visual rearrangement to leave a ref untouched, and a change in meaning
to mint a new one with an explicit alias or replaced-by. A stylesheet that
selected on ``[data-ui-ref="..."]`` would make refs load-bearing for
appearance, so restyling would start renaming them and the lifecycle contract
would quietly stop holding.

The information architecture follows the Issue #1 implementation spec: a
warm, editorial three-column workbench with a quiet evidence rail.  These
rules are intentionally independent of the reference protocol so visual
rearrangement never forces a semantic reference migration.
"""

from __future__ import annotations

from .ui_matrix import VIEWPORT_BREAKPOINT_PX

_TEMPLATE = """\
:root {
  color-scheme: light;
  --ink: #333333;
  --muted: #5d5d5d;
  --quiet: #707070;
  --canvas: #fae8c5;
  --surface: #fff8eb;
  --surface-raised: #fffdf7;
  --surface-strong: #f3deb6;
  --line: #d8c5a2;
  --line-soft: #ead9b9;
  --sage: #6e6f50;
  --sage-strong: #55563d;
  --sage-wash: rgba(110, 111, 80, 0.13);
  --amber: #a96f31;
  --amber-wash: rgba(208, 156, 101, 0.16);
  --rose: #8f6650;
  --rose-wash: rgba(143, 102, 80, 0.13);
  --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  --sans: "PingFang SC", "Noto Sans CJK SC", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --display: "Iowan Old Style", "Noto Serif CJK SC", "Songti SC", Georgia, serif;
  --elevation-1: 0 1px 2px rgba(62, 57, 48, 0.08), 0 2px 8px rgba(62, 57, 48, 0.045);
  --shadow: 0 16px 34px rgba(62, 57, 48, 0.11), 0 2px 7px rgba(62, 57, 48, 0.05);
}

* { box-sizing: border-box; }

html {
  min-width: 320px;
  background: var(--canvas);
}

body {
  min-width: 320px;
  min-height: 100vh;
  margin: 0;
  color: var(--ink);
  background: var(--canvas);
  font-family: var(--sans);
  font-size: 14px;
  letter-spacing: -0.01em;
  line-height: 1.5;
  overflow: hidden;
}

button, input { font: inherit; }
button { color: inherit; }
button:focus-visible, a:focus-visible {
  outline: 2px solid var(--sage-strong);
  outline-offset: 3px;
}

main {
  --viewport-class: wide;
  display: flex;
  flex-direction: column;
}

.workbench-page {
  height: 100vh;
  min-height: 100vh;
  overflow-x: hidden;
  overflow-y: auto;
  background: radial-gradient(circle at 54% 6%, rgba(110, 111, 80, 0.08), transparent 25%), var(--canvas);
}

.workspace-bar {
  display: flex;
  min-height: 58px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 20px;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 253, 247, 0.86);
}

.brand-lockup, .workspace-meta, .intent-context, .section-heading, .records-heading {
  display: flex;
  align-items: center;
}

.brand-lockup { min-width: 0; gap: 10px; }
.brand-mark {
  display: grid;
  width: 22px;
  height: 22px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--sage-strong);
  border: 1px solid var(--sage);
  border-radius: 7px;
}
.brand-mark svg { width: 13px; height: 13px; fill: none; stroke: currentColor; stroke-width: 1.8; }
.brand-name { color: var(--ink); font-weight: 700; letter-spacing: -0.035em; }
.breadcrumb { color: var(--quiet); font-family: var(--mono); font-size: 11px; }
.workspace-meta { min-width: 0; gap: 8px; margin-left: auto; }
.icon-button { display: grid; place-items: center; flex: 0 0 auto; width: 30px; height: 30px; padding: 0; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--muted); cursor: pointer; transition: background .18s, border-color .18s; }
.icon-button:hover { background: var(--surface-raised); border-color: var(--line); }
.icon-button svg { width: 16px; height: 16px; stroke: currentColor; stroke-width: 1.7; fill: none; }
.icon-button[aria-disabled="true"] { cursor: not-allowed; opacity: .7; }
.meta-pill, .scope-tag, .source-badge, .section-source, .record-count {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  border-radius: 999px;
  font-family: var(--mono);
  font-size: 10px;
  line-height: 1;
}
.meta-pill { padding: 7px 9px; color: var(--muted); border: 1px solid var(--line); background: var(--surface); }
.scope-tag { padding: 6px 8px; color: var(--sage-strong); border: 1px solid rgba(110, 111, 80, 0.28); background: var(--sage-wash); }
.scope-target { color: var(--amber); border-color: rgba(169, 111, 49, 0.28); background: var(--amber-wash); }
.scope-implemented { color: var(--sage-strong); border-color: rgba(110, 111, 80, 0.28); background: var(--sage-wash); }
.scope-unknown { color: var(--rose); border-color: rgba(143, 102, 80, 0.28); background: var(--rose-wash); }
.status-dot { display: inline-block; width: 6px; height: 6px; flex: 0 0 auto; border-radius: 99px; background: currentColor; }

.view-nav {
  display: flex;
  min-height: 40px;
  align-items: center;
  gap: 6px;
  padding: 6px 20px;
  border-bottom: 1px solid var(--line-soft);
  background: rgba(255, 253, 247, 0.64);
}
.view-nav a {
  padding: 5px 9px;
  border-radius: 6px;
  color: var(--muted);
  font-size: 12px;
  text-decoration: none;
}
.view-nav a:hover, .view-nav a[aria-current="page"] {
  color: var(--ink);
  background: var(--surface-strong);
}

.record-picker-form, .record-filter-form {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 16px;
  border: 1px solid var(--line-soft);
  background: var(--surface);
}
.record-picker-form label, .record-filter-form label { color: var(--quiet); font-size: 12px; }
.record-picker-form select, .record-filter-form input {
  min-width: 0;
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--ink);
  background: var(--surface-raised);
}
.record-picker-form select { flex: 1 1 220px; }
.record-filter-form input { flex: 1 1 180px; }
.record-picker-form button, .record-filter-form button {
  padding: 6px 10px;
  border: 1px solid var(--sage);
  border-radius: 6px;
  color: var(--sage-strong);
  background: var(--sage-wash);
  cursor: pointer;
}

.home-layout {
  display: grid;
  min-height: calc(100vh - 58px);
  grid-template-columns: 236px minmax(460px, 1fr) 318px;
  grid-template-areas: "sidebar content inspector";
}

.home-sidebar {
  grid-area: sidebar;
  min-width: 0;
  background: var(--surface);
  box-shadow: 1px 0 0 var(--line);
  display: flex;
  flex-direction: column;
}

.home-records, .home-inspector {
  min-width: 0;
  background: var(--surface);
}

.home-records {
  flex: 1 1 auto;
  padding: 17px 12px;
}

.home-inspector {
  grid-area: inspector;
  padding: 19px 16px;
  border-left: 1px solid var(--line);
}

/* F3 — side-panel navigation: 新建 / 近期工作 / 工作区 (A-session) */
.side-panel { padding: 12px 12px 10px; border-bottom: 1px solid var(--line); }
.side-action { display: flex; justify-content: space-between; align-items: center; width: 100%; margin: 0 0 14px; padding: 9px 10px; color: var(--ink); border: 1px solid var(--line); border-radius: 9px; background: var(--surface-raised); box-shadow: var(--elevation-1); cursor: pointer; text-align: left; font: inherit; font-size: 12px; transition: background .18s, border-color .18s; }
.side-action:hover { background: var(--surface-strong); border-color: color-mix(in srgb, var(--sage) 45%, var(--line)); }
.side-action svg { width: 15px; height: 15px; stroke: var(--sage); fill: none; stroke-width: 1.8; }
.nav-label { margin: 12px 2px 6px; font-family: var(--mono); font-size: 11px; font-weight: 500; color: var(--muted); letter-spacing: .04em; }
.side-list { list-style: none; margin: 0; padding: 0; }
.side-item { display: block; padding: 6px 8px; border-radius: 7px; color: var(--ink); font-size: 12px; text-decoration: none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.side-item:hover { background: var(--surface-strong); }
.side-item small { display: block; color: var(--muted); font-size: 10px; margin-top: 1px; }
.side-empty { padding: 6px 8px; color: var(--muted); font-size: 11px; }

.home-content {
  grid-area: content;
  min-width: 0;
  padding: clamp(22px, 4vw, 44px) clamp(18px, 4vw, 48px) 58px;
}

.eyebrow {
  margin: 0 0 7px;
  color: var(--sage);
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.085em;
  line-height: 1.2;
  text-transform: uppercase;
}

.records-heading { justify-content: space-between; gap: 12px; margin: 0 8px 5px; }
.records-heading h2, .inspector-heading h2, .section-heading h2 { margin: 0; font-size: 14px; font-weight: 650; letter-spacing: -0.025em; }
.record-count { padding: 5px 7px; color: var(--sage-strong); border: 1px solid rgba(110, 111, 80, 0.28); background: var(--sage-wash); }
.records-caption, .records-boundary, .source-note { color: var(--quiet); font-family: var(--mono); font-size: 10px; line-height: 1.55; }
.records-caption { margin: 0 8px 14px; }
.records-boundary { margin: 17px 8px 0; }
.record-list { display: flex; flex-direction: column; gap: 3px; margin: 0; padding: 0; list-style: none; }
.record-item {
  display: block;
  min-width: 0;
  padding: 10px 9px;
  border: 1px solid transparent;
  border-radius: 9px;
  color: var(--muted);
  background: transparent;
  transition: border-color 180ms ease, background 180ms ease, color 180ms ease;
}
.record-item:first-child, .record-item:hover { color: var(--ink); border-color: var(--line); background: var(--surface-strong); }
.record-title { display: block; overflow: hidden; margin-bottom: 6px; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 600; }
.record-meta { display: flex; justify-content: space-between; gap: 8px; color: var(--quiet); font-family: var(--mono); font-size: 10px; }
.record-meta code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.record-activity { display: block; margin-top: 5px; color: var(--quiet); font-size: 10px; }
.records-empty { display: grid; gap: 7px; padding: 21px 10px; color: var(--muted); font-size: 11px; line-height: 1.5; }
.records-empty strong { color: var(--ink); font-size: 12px; }
.empty-mark { width: 29px; height: 29px; border: 1px dashed #b8b1a5; border-radius: 9px; }

.home-section { min-width: 0; }
.intent-section { padding-bottom: 27px; border-bottom: 1px solid var(--line); }
.section-heading { justify-content: space-between; gap: 14px; }
.section-heading .eyebrow { margin-bottom: 0; }
.intent-section .section-heading { align-items: flex-start; }
.intent-section h1 {
  max-width: 720px;
  margin: 14px 0 10px;
  color: var(--ink);
  font-family: var(--display);
  font-size: clamp(28px, 4vw, 45px);
  font-weight: 600;
  letter-spacing: -0.055em;
  line-height: 1.12;
}
.intent-summary { max-width: 680px; margin: 0; color: var(--muted); font-size: 15px; line-height: 1.65; }
.intent-context { flex-wrap: wrap; gap: 7px 10px; margin-top: 21px; color: var(--quiet); font-family: var(--mono); font-size: 10px; }
.intent-context code { padding: 4px 6px; color: var(--sage-strong); border: 1px solid rgba(110, 111, 80, 0.2); border-radius: 5px; background: var(--sage-wash); }
.section-source { padding: 5px 7px; color: var(--quiet); border: 1px solid var(--line); background: rgba(255, 253, 247, 0.55); }

.status-chip { display: inline-flex; min-width: 0; align-items: center; gap: 6px; padding: 6px 8px; border: 1px solid var(--line); border-radius: 7px; color: var(--quiet); background: var(--surface); font-family: var(--mono); font-size: 10px; }
.status-chip b { color: var(--ink); font-family: var(--sans); font-size: 11px; font-weight: 650; }
.status-chip code { color: currentColor; }
.status-chip small { color: var(--quiet); font-family: var(--sans); }
.status-running, .status-completed, .status-ready { color: var(--sage-strong); border-color: rgba(110, 111, 80, 0.3); background: var(--sage-wash); }
.status-failed, .status-safe-stopped, .status-denied { color: var(--rose); border-color: rgba(143, 102, 80, 0.3); background: var(--rose-wash); }
.status-recovering, .status-created { color: var(--amber); border-color: rgba(169, 111, 49, 0.3); background: var(--amber-wash); }

.plan-section { padding: 23px 0 20px; border-bottom: 1px solid var(--line); }
.plan-list { display: grid; gap: 0; margin: 15px 0 0; padding: 0; list-style: none; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; background: var(--surface); box-shadow: var(--elevation-1); }
.plan-row { display: grid; grid-template-columns: 23px minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 12px; border-top: 1px solid var(--line-soft); color: var(--muted); font-size: 12px; }
.plan-row:first-child { border-top: 0; }
.plan-row strong { display: block; color: var(--ink); font-weight: 600; }
.plan-row small { display: block; margin-top: 3px; color: var(--quiet); font-size: 11px; }
.plan-row code { color: var(--quiet); font-family: var(--mono); font-size: 10px; }
.plan-step { display: grid; width: 20px; height: 20px; place-items: center; color: var(--quiet); border: 1px solid var(--line); border-radius: 50%; font-family: var(--mono); font-size: 9px; }
.plan-completed, .plan-running { background: rgba(110, 111, 80, 0.055); }
.plan-completed .plan-step, .plan-running .plan-step { color: var(--sage-strong); border-color: rgba(110, 111, 80, 0.42); background: var(--sage-wash); }
/* F5 plan card — done / current / pending step states (owner-backed) */
.plan-row.plan-done { color: var(--ink); }
.plan-row.plan-done .plan-step { color: var(--sage-strong); border-color: rgba(110, 111, 80, 0.42); background: var(--sage-wash); }
.plan-row.plan-done strong { color: var(--sage-strong); }
.plan-row.plan-current { border-left: 3px solid var(--amber); padding-left: 9px; background: var(--amber-wash); }
.plan-row.plan-current .plan-step { color: var(--amber); border-color: var(--amber); background: var(--surface-raised); }
.plan-row.plan-current strong { color: var(--ink); }
.plan-row.plan-pending { color: var(--quiet); }
.plan-row.plan-pending .plan-step { color: var(--quiet); border-color: var(--line-soft); }
.plan-row.plan-pending strong { color: var(--muted); }
.plan-legend { display: flex; gap: 16px; margin: 12px 0 0; padding: 0; list-style: none; font-size: 11px; color: var(--quiet); }
.plan-legend li { display: flex; align-items: center; gap: 6px; }
.legend-dot { display: grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; border: 1px solid var(--line); font-size: 10px; font-family: var(--mono); }
.legend-done { color: var(--sage-strong); border-color: rgba(110, 111, 80, 0.42); background: var(--sage-wash); }
.legend-current { color: var(--amber); border-color: var(--amber); background: var(--surface-raised); }
.legend-pending { color: var(--quiet); border-color: var(--line-soft); }
.section-copy { margin: 15px 0 0; color: var(--muted); line-height: 1.6; }
.section-empty { color: var(--quiet); }
.home-secondary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 17px; padding: 17px 0; }
.compact-section { min-height: 141px; padding: 15px; border: 1px solid var(--line); border-radius: 10px; background: rgba(255, 253, 247, 0.62); }
.artifact-list, .evidence-list { display: grid; gap: 0; margin: 14px 0 0; padding: 0; list-style: none; }
.artifact-row, .evidence-row { display: grid; grid-template-columns: 10px minmax(0, 1fr); gap: 9px; padding: 9px 0; border-top: 1px solid var(--line-soft); color: var(--muted); font-size: 11px; line-height: 1.4; }
.artifact-row:first-child, .evidence-row:first-child { border-top: 0; }
.artifact-row strong, .evidence-row strong { display: block; color: var(--ink); font-family: var(--mono); font-size: 11px; font-weight: 500; }
.artifact-row small, .evidence-row small { display: block; margin-top: 2px; color: var(--quiet); }
.row-mark { width: 7px; height: 9px; margin-top: 3px; border: 1px solid var(--sage); border-radius: 2px; }
.evidence-row .row-mark { width: 7px; height: 7px; border-radius: 50%; background: var(--sage); }
.home-action-block { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 16px; border: 1px solid rgba(169, 111, 49, 0.32); border-radius: 10px; background: var(--amber-wash); }
.home-action-block strong { display: block; color: var(--ink); font-size: 13px; }
.home-action-block p { max-width: 560px; margin: 5px 0 0; color: var(--muted); font-size: 11px; line-height: 1.5; }
.preflight-button { display: inline-flex; flex: 0 0 auto; flex-direction: column; align-items: center; gap: 2px; min-width: 126px; padding: 10px 13px; color: #fffdf9; border: 1px solid var(--sage-strong); border-radius: 8px; background: var(--sage); box-shadow: var(--elevation-1); cursor: not-allowed; font-weight: 650; }
.preflight-button span { color: rgba(255, 253, 249, 0.78); font-family: var(--mono); font-size: 9px; font-weight: 400; }
.preflight-result { padding-top: 18px; }
.preflight-result .status-chip { margin-top: 11px; }

.inspector-heading { justify-content: space-between; gap: 10px; margin: 0 2px 17px; }
.source-badge { padding: 5px 7px; color: var(--sage-strong); border: 1px solid rgba(110, 111, 80, 0.28); background: var(--sage-wash); }
.state-card { padding: 11px 0 15px; border-bottom: 1px solid var(--line); }
.fact-list { margin: 0; padding: 10px 0 0; }
.fact-row { display: flex; justify-content: space-between; gap: 12px; padding: 7px 0; font-family: var(--mono); font-size: 10px; }
.fact-row dt { color: var(--quiet); }
.fact-row dd { max-width: 170px; overflow: hidden; margin: 0; color: var(--muted); text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.source-note { margin: 13px 0 0; padding-top: 12px; border-top: 1px solid var(--line); }

/* F7 — run-facts inspector: evidence links (render shell, read-only routes) */
.evidence-links { margin: 13px 0 0; padding-top: 12px; border-top: 1px solid var(--line); }
.evidence-links .eyebrow { margin: 0 0 8px; }
.evidence-link-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
.evidence-link-row { display: grid; gap: 2px; padding: 6px 8px; border: 1px solid var(--line); border-radius: 7px; background: var(--surface-raised); }
.evidence-link { color: var(--sage-strong); font-family: var(--mono); font-size: 10px; text-decoration: none; }
.evidence-link:hover { text-decoration: underline; }
.evidence-link-row small { color: var(--quiet); font-family: var(--mono); font-size: 9px; word-break: break-all; }
.evidence-empty { color: var(--quiet); font-family: var(--mono); font-size: 10px; }

/* F10 — run-rail inspector: lifecycle rail + disabled Run + owner records + evidence timeline */
.run-rail { margin-top: 22px; padding-top: 20px; border-top: 1px solid var(--line); }
.rail-track { display: flex; align-items: center; margin: 2px 0 16px; }
.rail-node { display: inline-flex; align-items: center; gap: 6px; font-family: var(--mono); font-size: 10px; color: var(--quiet); white-space: nowrap; }
.rail-node i { width: 9px; height: 9px; border-radius: 99px; background: var(--line); flex: 0 0 auto; }
.rail-node:not(:last-child)::after { content: ""; width: 22px; height: 1px; background: var(--line); margin: 0 8px; }
.rail-done { color: var(--muted); }
.rail-done i { background: var(--sage); }
.rail-current { color: var(--ink); font-weight: 600; }
.rail-current i { background: var(--ink); box-shadow: 0 0 0 3px var(--sage-wash); }
.rail-pending { color: var(--quiet); }
.rail-terminal { margin-left: 10px; padding: 3px 8px; border-radius: 6px; font-family: var(--mono); font-size: 9px; color: var(--rose); background: var(--rose-wash); }
.rail-run-button { display: flex; justify-content: space-between; align-items: center; width: 100%; margin: 0 0 16px; padding: 9px 11px; color: var(--muted); border: 1px dashed var(--line); border-radius: 9px; background: var(--surface-raised); font: inherit; font-size: 12px; cursor: not-allowed; text-align: left; }
.rail-run-button .rail-run-glyph { color: var(--muted); font-size: 11px; margin-right: 2px; }
.rail-run-button span { font-family: var(--mono); font-size: 9px; color: var(--quiet); }
.rail-records, .rail-timeline { margin-top: 4px; }
.rail-records .eyebrow, .rail-timeline .eyebrow { margin: 0 0 8px; }
.rail-record-list, .rail-timeline-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
.rail-record-list li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; padding: 6px 8px; border: 1px solid var(--line); border-radius: 7px; background: var(--surface-raised); font-family: var(--mono); font-size: 10px; }
.rail-record-list code { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rail-record-list span { color: var(--quiet); }
.rail-record-list time { grid-column: 1 / -1; color: var(--quiet); font-size: 9px; }
.rail-timeline-list li { display: grid; grid-template-columns: minmax(0, 1fr); gap: 2px; padding: 7px 0; border-top: 1px solid var(--line-soft); font-family: var(--mono); font-size: 10px; }
.rail-timeline-list li:first-child { border-top: 0; }
.rail-timeline-list time { color: var(--quiet); font-size: 9px; }
.rail-timeline-link { color: var(--sage-strong); text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rail-timeline-link:hover { text-decoration: underline; }
.rail-timeline-list code { color: var(--quiet); font-size: 9px; word-break: break-all; }
.rail-empty { color: var(--quiet); font-family: var(--mono); font-size: 10px; }

/* F6/1-2-1 — input composer: A-session prompt box + send. Disabled shell and
   live form share one component; the disabled state mirrors the run-rail
   button's read-only treatment (dashed border, not-allowed cursor). */
.composer-section { margin-top: 16px; }
.composer { display: grid; gap: 8px; padding: 12px; border: 1px solid var(--line); border-radius: 11px; background: var(--surface-raised); }
.composer[aria-disabled="true"] { border-style: dashed; background: var(--surface); }
.composer-label { font-family: var(--mono); font-size: 10px; color: var(--quiet); text-transform: uppercase; letter-spacing: 0.04em; }
.composer-input { width: 100%; resize: vertical; padding: 9px 11px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--ink); font: inherit; font-size: 13px; line-height: 1.5; }
.composer-input:focus { outline: none; border-color: var(--sage); box-shadow: 0 0 0 3px var(--sage-wash); }
.composer-input:disabled { color: var(--quiet); cursor: not-allowed; }
.composer-send { justify-self: start; padding: 8px 18px; border: 1px solid var(--sage); border-radius: 8px; background: var(--sage-wash); color: var(--sage-strong); font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; }
.composer-send:hover:not(:disabled) { background: var(--sage); color: #fff; }
.composer-send:disabled { border-style: dashed; color: var(--quiet); background: var(--surface); cursor: not-allowed; }
.composer-hint { font-family: var(--mono); font-size: 9px; color: var(--quiet); }

/* F12/1-2-2 — approval-execution console: pending-approval + claimed-effect
   lists with Approve/Deny/Record-receipt controls. Disabled shell and the
   command-facade-wired form share one component; the disabled state mirrors
   the run-rail button's read-only treatment (dashed border, not-allowed). */
.approval-console-section { margin-top: 16px; }
.approval-empty { color: var(--quiet); font-family: var(--mono); font-size: 11px; padding: 12px 0; }
.approval-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.approval-row { display: grid; grid-template-columns: minmax(0, auto) auto auto auto; grid-auto-flow: column; align-items: center; gap: 10px; padding: 9px 11px; border: 1px solid var(--line); border-radius: 9px; background: var(--surface-raised); font-family: var(--mono); font-size: 11px; }
.approval-id { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.approval-op { color: var(--ink); }
.approval-res { color: var(--quiet); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.approval-reason-zh { color: var(--quiet); font-size: 10px; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.approval-status-zh { color: var(--amber); }
.approval-actions { display: inline-flex; align-items: center; gap: 6px; }
.approval-approve, .approval-deny, .effect-receipt { padding: 6px 12px; border-radius: 7px; font: inherit; font-size: 12px; font-weight: 600; cursor: pointer; }
.approval-approve { border: 1px solid var(--sage); background: var(--sage-wash); color: var(--sage-strong); }
.approval-approve:hover:not(:disabled) { background: var(--sage); color: #fff; }
.approval-deny { border: 1px solid var(--rose); background: var(--rose-wash); color: var(--rose); }
.approval-deny:hover:not(:disabled) { background: var(--rose); color: #fff; }
.effect-receipt { border: 1px solid var(--amber); background: var(--amber-wash, #fdf3e0); color: var(--amber-strong, #8a5a00); }
.effect-receipt:hover:not(:disabled) { background: var(--amber, #e0a200); color: #fff; }
.approval-reason { width: 130px; padding: 5px 7px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); color: var(--ink); font: inherit; font-size: 11px; }
.approval-reason:focus { outline: none; border-color: var(--sage); box-shadow: 0 0 0 3px var(--sage-wash); }
.approval-reason:disabled { color: var(--quiet); cursor: not-allowed; }
.approval-approve:disabled, .approval-deny:disabled, .effect-receipt:disabled { border-style: dashed; color: var(--quiet); background: var(--surface); cursor: not-allowed; }
.approval-disabled-hint { font-family: var(--mono); font-size: 9px; color: var(--quiet); }
.approval-readonly-hint { margin: 8px 0 0; font-family: var(--mono); font-size: 9px; color: var(--quiet); }
.approval-row { display: grid; grid-template-columns: auto 1fr auto; gap: 4px 10px; align-items: center; padding: 8px 10px; border: 1px solid var(--hairline); border-radius: 8px; background: var(--surface); }
.approval-row .approval-id { grid-column: 1; font-family: var(--mono); font-size: 11px; color: var(--ink); }
.approval-row .approval-op { grid-column: 2; font-size: 12px; color: var(--ink); }
.approval-row .approval-res { grid-column: 3; font-family: var(--mono); font-size: 10px; color: var(--quiet); }
.approval-row .approval-reason-zh, .approval-row .approval-status-zh { grid-column: 1 / -1; font-family: var(--mono); font-size: 10px; color: var(--quiet); }
.approval-row .approval-actions { grid-column: 1 / -1; display: flex; gap: 8px; align-items: center; }
.approval-reason { flex: 1; max-width: 220px; padding: 5px 8px; border-radius: 6px; border: 1px solid var(--hairline); font: inherit; font-size: 11px; }

/* F11/1-2-7 — scenario state machine: four-state banner + stepper + controls.
   Tone accents reuse existing palette tokens: empty=neutral, planning=sage,
   approval=amber, stopped=rose. The controls are real triggers only when a
   scenario command facade is wired (scenario_capable=True); otherwise they
   render disabled (read-only host invariant). */
.scenario-state-wrap { margin: 14px 0 0; }
.scenario-state { padding: 16px 18px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface-raised); border-left: 4px solid var(--line); }
.scenario-state.ss-planning { border-left-color: var(--sage); }
.scenario-state.ss-approval { border-left-color: var(--amber); }
.scenario-state.ss-stopped { border-left-color: var(--rose); }
.scenario-state.ss-empty { border-left-color: var(--line); }
.scenario-state.ss-unknown { border-left-color: var(--line); }
.ss-track { list-style: none; margin: 12px 0 10px; padding: 0; display: flex; flex-wrap: wrap; gap: 10px; }
.ss-node { display: inline-flex; align-items: center; gap: 7px; font-family: var(--mono); font-size: 11px; color: var(--quiet); padding: 5px 10px; border: 1px solid var(--line-soft); border-radius: 99px; background: var(--surface); }
.ss-node .ss-dot { width: 9px; height: 9px; border-radius: 99px; background: var(--line); flex: 0 0 auto; }
.ss-node.ss-active { color: var(--ink); font-weight: 600; border-color: currentColor; }
.ss-node.ss-planning .ss-dot { background: var(--sage); }
.ss-node.ss-planning.ss-active { color: var(--sage-strong); }
.ss-node.ss-planning.ss-active .ss-dot { box-shadow: 0 0 0 3px var(--sage-wash); }
.ss-node.ss-approval .ss-dot { background: var(--amber); }
.ss-node.ss-approval.ss-active { color: var(--amber); }
.ss-node.ss-approval.ss-active .ss-dot { box-shadow: 0 0 0 3px var(--amber-wash); }
.ss-node.ss-stopped .ss-dot { background: var(--rose); }
.ss-node.ss-stopped.ss-active { color: var(--rose); }
.ss-node.ss-stopped.ss-active .ss-dot { box-shadow: 0 0 0 3px var(--rose-wash); }
.ss-node.ss-unknown .ss-dot { background: var(--line); }
.ss-blurb { margin: 2px 0 0; font-size: 12px; color: var(--muted); }
.scenario-controls { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
.scenario-readonly-hint { margin: 8px 0 0; font-size: 11px; color: var(--muted); }
.scenario-control { font-family: var(--mono); font-size: 12px; font-weight: 600; padding: 7px 13px;
  border-radius: 8px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); }
.scenario-control[disabled] { cursor: not-allowed; opacity: 0.6; color: var(--muted); }
.scenario-control-request-approval:not([disabled]) { cursor: pointer; border-color: var(--amber); color: var(--amber); }
.scenario-control-request-stop:not([disabled]) { cursor: pointer; border-color: var(--rose); color: var(--rose); }

/* F13/1-2-8 — safe-stop / reconcile banner. The reconcile trigger is wired via
   POST /api/reconcile when a control-plane reconcile facade is injected; a
   read-only host keeps the button disabled (see _render_safe_stop). */
.safe-stop { margin: 12px 0 0; }
.safe-stop-inactive { margin: 0; }
.safe-stop.ss-stopped { padding: 16px 18px; border: 1px solid var(--rose); border-radius: 12px;
  background: var(--rose-wash); border-left: 4px solid var(--rose); }
.safe-stop-message { margin: 4px 0 12px; font-size: 13px; color: var(--ink); line-height: 1.5; }
.safe-stop-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.reconcile-button { font-family: var(--mono); font-size: 12px; font-weight: 600; padding: 8px 14px;
  border-radius: 8px; border: 1px solid var(--rose); background: var(--surface); color: var(--rose); }
.reconcile-button[disabled] { cursor: not-allowed; opacity: 0.7; }
.reconcile-button:not([disabled]) { cursor: pointer; opacity: 1; }
.safe-stop-hint { font-size: 11px; color: var(--muted); }

/* F15 r2 — r2-ui-reference-skills 协同可视化面板（只读投影） */
.ui-ref-collab { margin: 12px 0 0; padding: 16px 18px; border: 1px solid var(--line);
  border-radius: 12px; background: var(--surface-raised); border-left: 4px solid var(--ink-soft); }
.ui-ref-collab-empty { display: none; }
.urc-caption { margin: 6px 0 12px; font-size: 12px; color: var(--muted); line-height: 1.5; }
.urc-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
.urc-row { display: grid; grid-template-columns: minmax(140px, 200px) 1fr; gap: 16px;
  align-items: start; padding: 12px; border: 1px solid var(--line-soft); border-radius: 10px;
  background: var(--surface); }
.urc-skill { display: flex; flex-direction: column; gap: 2px; }
.urc-skill-name { font-size: 13px; font-weight: 600; color: var(--ink); }
.urc-skill-id { font-family: var(--mono); font-size: 11px; color: var(--quiet); }
.urc-statuses { display: grid; gap: 10px; }
.urc-status { display: grid; grid-template-columns: auto auto 1fr; gap: 8px 10px; align-items: baseline;
  padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: 8px; background: var(--surface-raised); }
.urc-status-key { font-family: var(--mono); font-size: 11px; color: var(--muted); }
.urc-pill { display: inline-flex; align-items: center; padding: 2px 9px; border-radius: 999px;
  font-family: var(--mono); font-size: 11px; font-weight: 600; border: 1px solid var(--line); }
.urc-reason { font-size: 11px; color: var(--quiet); }
.urc-evidence { list-style: disc; margin: 4px 0 0 18px; grid-column: 1 / -1; }
.urc-evidence li { font-size: 11px; color: var(--muted); line-height: 1.45; }
.urc-boundary { margin: 12px 0 0; font-size: 11px; color: var(--muted);
  border-top: 1px dashed var(--line); padding-top: 8px; }
@media (max-width: 760px) {
  .urc-row { grid-template-columns: 1fr; }
  .urc-status { grid-template-columns: auto auto; }
  .urc-reason, .urc-evidence { grid-column: 1 / -1; }
}

/* F19 — three-variant debug switcher (Round 1 shell + read-only projection). */
.variant-switcher { margin: 12px 0 0; padding: 16px 18px; border: 1px solid var(--line);
  border-radius: 12px; background: var(--surface-raised); border-left: 4px solid var(--amber); }
.vs-caption { margin: 6px 0 12px; font-size: 12px; color: var(--muted); line-height: 1.5; }
.vs-options { display: inline-flex; gap: 8px; flex-wrap: wrap; }
.vs-option { display: inline-flex; align-items: center; justify-content: center; min-width: 38px;
  padding: 7px 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface);
  color: var(--ink); font-family: var(--mono); font-size: 13px; font-weight: 600; text-decoration: none;
  transition: border-color .12s ease, background .12s ease; }
.vs-option:hover { border-color: var(--ink-soft); }
.vs-option-active { background: var(--amber-wash); border-color: var(--amber); color: var(--amber-strong); }
.vs-state { margin: 12px 0 0; font-size: 12px; color: var(--quiet); }
.vs-current { font-family: var(--mono); font-weight: 700; color: var(--ink); padding: 1px 7px;
  border: 1px solid var(--line); border-radius: 6px; background: var(--surface); }
.vs-invalid { color: var(--rose); margin-left: 4px; }
@media (max-width: 760px) {
  .vs-options { width: 100%; }
  .vs-option { flex: 1; }
}

/* 1-3 — B 命令画布 / C 项目日记 只读变体布局（?variant=B|C 驱动，服务端分支）。 */
.variant-canvas, .variant-journal { margin: 0; }
.variant-canvas > .section-heading, .variant-journal > .section-heading { margin-bottom: 14px; }
.canvas-grid, .journal-grid { display: grid; gap: 14px; }
.canvas-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.journal-grid { grid-template-columns: 1fr 1.4fr 1.2fr; }
.canvas-panel, .journal-panel { padding: 14px 16px; border: 1px solid var(--line);
  border-radius: 12px; background: var(--surface-raised); }
.canvas-panel > .panel-heading, .journal-panel > .panel-heading { margin: 0 0 10px; }
.canvas-panel h3, .journal-panel h3 { margin: 0; font-size: 13px; font-weight: 700;
  color: var(--muted); letter-spacing: .02em; }
.canvas-run-rail { grid-column: 1 / -1; }
.run-rail-run, .run-rail-status, .journal-run, .journal-workspace, .journal-prompt {
  margin: 4px 0; font-size: 13px; color: var(--ink); }
.journal-prompt { color: var(--muted); line-height: 1.6; }
.journal-workspace { color: var(--quiet); }
.variant-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.variant-table th, .variant-table td { text-align: left; padding: 6px 8px;
  border-bottom: 1px solid var(--line); vertical-align: top; }
.variant-table th { color: var(--quiet); font-weight: 600; font-size: 11px;
  text-transform: uppercase; letter-spacing: .04em; }
.variant-table td { color: var(--ink); font-family: var(--mono); }
.variant-table tbody tr:hover { background: var(--surface); }
.variant-empty { margin: 6px 0; font-size: 12px; color: var(--quiet); font-style: italic; }
.journal-plan { margin-top: 10px; }
@media (max-width: 980px) {
  .canvas-grid, .journal-grid { grid-template-columns: 1fr; }
}

/* The review layer covers the viewport. Covering matters: a layer with no
   area intercepts nothing, so passthrough would be vacuously true and the
   hit test in tests/test_ui_overlay.py would prove nothing. pointer-events is
   set inline from the ReviewMode descriptor rather than here, so the contract
   has one source. */
[data-ui-overlay] {
  position: fixed;
  inset: 0;
  display: block;
}

[data-ui-overlay] > span {
  position: absolute;
  top: 0;
  right: 0;
  padding: 4px 8px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

/* The review panel is a fixed side region, visually above the business page
   but below nothing the page owns: it appears only in review mode, so these
   rules can never reshape the normal document. */
[data-ui-panel] {
  position: fixed;
  top: 0;
  right: 0;
  width: 300px;
  max-height: 100vh;
  overflow: auto;
  margin: 0;
  padding: 12px;
  background: Canvas;
  border-left: 2px solid rgba(128, 128, 128, 0.5);
  font-size: 13px;
  z-index: 2;
}

[data-ui-panel-entries] {
  list-style: none;
  margin: 8px 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

[data-ui-panel-entry] {
  padding: 4px 8px;
  border: 1px solid rgba(128, 128, 128, 0.3);
  border-radius: 4px;
}

[data-ui-panel-locked="true"] {
  outline: 2px solid Highlight;
}

[data-ui-panel-action] {
  display: block;
  width: 100%;
  margin: 4px 0;
  padding: 6px 8px;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

/* The panel is docked, not overlaid: the page makes room for it, so it can
   never cover the element a reviewer is pointing at. ``:has`` keeps the
   padding review-only -- this stylesheet is shared with normal mode, whose
   document has no panel to match, and ``:not([hidden])`` hands the space back
   the moment the panel closes. */
body:has([data-ui-panel]:not([hidden])) {
  /* panel width + its padding and border: the page must make room for the
     whole box, or the root unit's edge slides underneath it. */
  padding-right: 332px;
}

/* Declared elements become focusable in review mode; the ring makes the
   focus stop visible, the preview badge names it. The selector keys off the
   behaviour hook the page layer adds, never the reference attribute itself:
   the style layer stays independent of the reference protocol. */
[data-ui-review-focusable]:focus {
  outline: 2px solid Highlight;
  outline-offset: 2px;
}

/* Visible rings for the two ways an element gets pointed at: a deep link
   locating it, and a reviewer locking it from the panel. Same ring, because
   both mean "this is the element under discussion". */
[data-ui-located],
[data-ui-locked-target] {
  outline: 3px solid Highlight;
  outline-offset: 2px;
}

/* The hover preview lives in the overlay: a dashed box matching the hovered
   element, carrying its Chinese semantic name. The overlay is pointer-events
   none, so the preview can never intercept a click. */
[data-ui-preview-box] {
  position: absolute;
  border: 2px dashed Highlight;
  border-radius: 4px;
}

[data-ui-preview-badge] {
  position: absolute;
  top: -1.7em;
  left: 0;
  padding: 2px 6px;
  background: Canvas;
  border: 1px solid rgba(128, 128, 128, 0.5);
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
}

/* F4 — conversation message stream (A-session-first, read-only projection).
   The avatar column is fixed; the body uses minmax(0, 1fr) so a long run id or
   plan never forces horizontal scroll, and the whole block inherits the
   reduced-motion rule declared last in this sheet. */
.conversation-section { padding-bottom: 24px; }
.conversation-empty { margin: 14px 0 0; color: var(--quiet); font-size: 12px; line-height: 1.5; }
.conversation-list { display: flex; flex-direction: column; gap: 14px; margin: 14px 0 0; padding: 0; list-style: none; }
.msg { display: grid; grid-template-columns: 38px minmax(0, 1fr); gap: 12px; min-width: 0; }
.msg-avatar {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  flex: 0 0 auto;
  color: var(--sage-strong);
  border: 1px solid rgba(110, 111, 80, 0.34);
  border-radius: 11px;
  background: var(--sage-wash);
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 600;
}
.msg-body {
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface-raised);
  box-shadow: var(--elevation-1);
}
.msg-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 7px; color: var(--quiet); font-family: var(--mono); font-size: 10px; }
.msg-role { color: var(--sage-strong); font-weight: 600; }
.msg-run { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.msg-time { margin-left: auto; color: var(--quiet); }
.msg-content { min-width: 0; }
.msg-title { margin: 0; color: var(--ink); font-size: 13px; font-weight: 600; letter-spacing: -0.02em; }
.msg-intent { margin: 3px 0 0; color: var(--muted); font-size: 12px; line-height: 1.5; }
.msg .plan-list { margin: 11px 0 0; }

/* Last, deliberately. These rules have the same specificity as the ones above,
   so ordering is what decides the outcome -- a media query placed earlier is
   silently overridden, which string inspection of the stylesheet cannot show.
   The class is also published as a custom property, so a reviewer and a test
   can read which branch applied rather than infer it from a measurement. */
@media (max-width: __COMPACT_MAX__px) {
  main { --viewport-class: compact; padding: 8px; }
  .workspace-bar { min-height: 54px; padding: 0 13px; }
  .breadcrumb, .workspace-meta .scope-target { display: none; }
  .workspace-meta { gap: 5px; }
  .home-layout { display: grid; min-height: 0; grid-template-columns: 1fr; grid-template-areas: "content" "sidebar" "inspector"; }
  .home-content { padding: 28px 17px 38px; }
  .home-records { border-top: 1px solid var(--line); border-right: 0; }
  .home-inspector { border-top: 1px solid var(--line); border-left: 0; }
  .intent-section h1 { font-size: 30px; }
  .intent-summary { font-size: 14px; }
  .home-secondary-grid { grid-template-columns: 1fr; }
  .home-action-block { align-items: flex-start; flex-direction: column; }
  .preflight-button { width: 100%; }
  /* A 300px side panel would leave a compact page 70px wide. Dock it at the
     bottom instead, and let the page make room downwards. */
  [data-ui-panel] {
    top: auto;
    bottom: 0;
    left: 0;
    width: auto;
    max-height: 50vh;
    border-left: none;
    border-top: 2px solid rgba(128, 128, 128, 0.5);
  }
  body:has([data-ui-panel]:not([hidden])) {
    padding-right: 0;
    padding-bottom: 50vh;
  }
}

@media (max-width: 1100px) and (min-width: __COMPACT_MIN__px) {
  .home-layout { grid-template-columns: 214px minmax(0, 1fr); grid-template-areas: "sidebar content" "inspector inspector"; }
  .home-inspector { border-top: 1px solid var(--line); border-left: 0; }
}

/* Review mode docks a 300px panel at the viewport edge and the body reserves
   332px for it.  The normal shell's 460px content minimum would overflow that
   reduced canvas and put the inspector underneath the panel, so the host
   narrows only this presentation state while keeping the semantic order. */
body:has([data-ui-panel]:not([hidden])) .home-layout {
  grid-template-columns: 214px minmax(0, 1fr) 280px;
}

@media (max-width: __COMPACT_MAX__px) {
  body:has([data-ui-panel]:not([hidden])) .home-layout {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; }
}
"""


#: A plain substitution rather than str.format: CSS is full of braces, and
#: escaping every one of them would make the stylesheet hard to read and easy
#: to break.
STYLESHEET = _TEMPLATE.replace("__COMPACT_MAX__", str(VIEWPORT_BREAKPOINT_PX - 1)).replace(
    "__COMPACT_MIN__", str(VIEWPORT_BREAKPOINT_PX)
)


def stylesheet() -> str:
    """Return the workbench stylesheet, pinned to the declared breakpoint."""
    return STYLESHEET
