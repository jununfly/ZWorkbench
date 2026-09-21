"""Product-surface checks for the first visible Workbench home slice.

The protocol tests prove that references survive rendering.  These checks keep
the first visual shell honest as well: it must expose the information
architecture from the PRD, retain explicit status/source language, and fit the
two acceptance viewports without introducing horizontal scroll.
"""

import json
import sys
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from browser import browser, chrome_available
from zworkbench.ui_home import home_manifest, render_home
from zworkbench.ui_host import serve_workbench
from zworkbench.ui_runtime import audit_rendered_html
from zworkbench.ui_view_model import home_view_model, UNKNOWN


VIEW = {
    "workspace": {
        "name": "ZWorkbench case-local",
        "mode": "local_read_only",
        "status": "implemented",
    },
    "records": [
        {
            "title": "为工作台建立第一条 UI seam",
            "run_id": "run-home-01",
            "status": "running",
            "updated_at": "刚刚",
        },
    ],
    "state": "running",
    "run_facts": {
        "status": "running",
        "run_id": "run-home-01",
        "parent_child": "unknown",
        "workspace": "case-local",
        "provider": "fake-loopback",
        "evidence": "owner snapshot",
        "source": "CompositionOwner",
    },
    "intent": {
        "title": "为工作台建立第一条 UI seam",
        "summary": "先把已记录事实放进一个可读、可定位、不会伪造执行能力的首页。",
        "status": "running",
        "source": "Owner / recorded input",
    },
    "plan": {
        "steps": [
            {"title": "完成首页视觉壳", "status": "completed"},
            {"title": "补齐负向状态", "status": "running"},
        ]
    },
    "artifacts": [{"title": "ui_home.py", "description": "server-rendered view"}],
    "evidence": [{"title": "owner snapshot", "description": "read-only source"}],
    "preflight_result": {"status": "ready", "source": "local preflight"},
}


class HomeSurfaceMarkupTests(unittest.TestCase):
    def test_planning_surface_keeps_information_architecture_and_sources_visible(self):
        markup = render_home(VIEW)
        self.assertIn("为工作台建立第一条 UI seam", markup)
        self.assertIn("WORK RECORDS", markup)
        self.assertIn("RUNTIME FACTS", markup)
        self.assertIn("CompositionOwner", markup)
        self.assertIn("来源：CompositionOwner", markup)
        self.assertIn('aria-disabled="true"', markup)
        self.assertIn("不会从页面启动 Run", markup)

        audit = audit_rendered_html(home_manifest(), markup)
        self.assertEqual(audit["undeclared"], ())
        self.assertEqual(audit["instances"]["home.record-list.item"], 1)

    def test_unknown_run_facts_are_not_relabelled_as_success(self):
        view = dict(VIEW)
        view["run_facts"] = {"status": "unknown", "source": "missing identity"}
        markup = render_home(view)
        self.assertIn('data-status="unknown"', markup)
        self.assertIn("来源：missing identity", markup)
        self.assertNotIn('data-status="completed"', markup)

    def test_missing_workspace_context_stays_unknown(self):
        markup = render_home({"workspace": "unknown", "run_facts": {"status": "unknown"}})
        self.assertIn('class="scope-tag scope-unknown"', markup)
        self.assertIn("source unknown", markup)
        self.assertNotIn("owner-backed", markup)

    def test_top_bar_exposes_icon_button_and_status_semantics(self):
        # F2: the workspace bar carries the icon-button shell and status color
        # semantics on its status tag, without any run-time action.
        markup = render_home(VIEW)
        self.assertIn('class="icon-button"', markup)
        self.assertIn("工作台信息（只读）", markup)
        self.assertIn('aria-disabled="true"', markup)
        # A non run-status workspace status keeps the amber fallback.
        self.assertIn('class="scope-tag scope-target"', markup)
        # A run-status workspace status maps to a status-* color class.
        run_view = dict(VIEW)
        run_view["workspace"] = {
            "name": "ZWorkbench case-local",
            "mode": "local_read_only",
            "status": "running",
        }
        run_markup = render_home(run_view)
        self.assertIn('class="scope-tag status-running"', run_markup)

    def test_side_panel_exposes_navigation_groups_and_empty_states(self):
        # F3: the sidebar carries a navigation panel with a new-record action
        # and recent/workspace groups, degrading to explicit empty states when
        # the owner-backed projection has no entries yet.
        markup = render_home(VIEW)
        self.assertIn('class="side-panel"', markup)
        self.assertIn("新建工作记录", markup)
        self.assertIn('aria-disabled="true"', markup)
        self.assertIn("近期工作", markup)
        self.assertIn("工作区", markup)
        self.assertIn("暂无近期工作", markup)
        self.assertIn("暂无工作区", markup)
        # The sidebar wrapper keeps the records list in the same column.
        self.assertIn('class="home-sidebar"', markup)

    def test_side_panel_renders_recent_and_workspace_entries(self):
        view = dict(VIEW)
        view["recent"] = [{"title": "上周的会话", "updated_at": "3 天前"}]
        view["workspaces"] = [{"name": "ZWorkbench case-local", "mode": "local_read_only"}]
        markup = render_home(view)
        self.assertIn('class="side-list"', markup)
        self.assertIn("上周的会话", markup)
        self.assertIn("ZWorkbench case-local", markup)
        self.assertNotIn("暂无近期工作", markup)
        self.assertNotIn("暂无工作区", markup)


CONVERSATION_VIEW = dict(VIEW)
CONVERSATION_VIEW["conversation"] = [
    {
        "role": "agent",
        "avatar_label": "A",
        "run_id": "run-msg-01",
        "status": "completed",
        "updated_at": "刚刚",
        "title": "为工作台建立第一条 UI seam",
        "intent": "已记录输入",
        "plan": {
            "steps": [
                {"title": "完成首页视觉壳", "status": "completed"},
                {"title": "补齐负向状态", "status": "running"},
            ]
        },
        "source": "CompositionOwner",
    },
]


class HomeConversationTests(unittest.TestCase):
    def test_conversation_stream_renders_messages_with_avatar_meta_and_plan_card(self):
        # F4: the A-session conversation stream is the lead home section and
        # renders each work record as a message with avatar, meta and an
        # owner-backed plan-card.
        markup = render_home(CONVERSATION_VIEW)
        self.assertIn("会话消息流", markup)
        self.assertIn('class="msg msg-agent"', markup)
        self.assertIn('class="msg-avatar"', markup)
        self.assertIn(">A<", markup)
        self.assertIn('data-ui-ref="home.conversation.message"', markup)
        self.assertIn("智能体", markup)
        self.assertIn("run-msg-01", markup)
        # Embedded plan-card keeps its step states from ui_view_model.
        self.assertIn('class="plan-list"', markup)
        self.assertIn("完成首页视觉壳", markup)
        self.assertIn('data-status="completed"', markup)
        audit = audit_rendered_html(home_manifest(), markup)
        self.assertEqual(audit["undeclared"], ())
        self.assertEqual(audit["instances"]["home.conversation.message"], 1)

    def test_conversation_stream_degrades_to_explicit_empty_state(self):
        markup = render_home({})
        self.assertIn('class="conversation-empty"', markup)
        self.assertIn("暂无会话消息", markup)
        self.assertNotIn('class="msg ', markup)

    def test_view_model_projects_runs_into_read_only_conversation_stream(self):
        # The owner-backed facade composes the message stream from recorded runs
        # without reaching back into the owner for any writable path.
        class FakeOwner:
            def snapshot(self):
                return {
                    "runs": [
                        {
                            "run_id": "r1",
                            "status": "completed",
                            "updated_at": "t1",
                            "task_type": "local_read_only_run",
                            "input": {"prompt": "do x"},
                            "metadata": {
                                "plan": [{"title": "step1", "status": "completed"}]
                            },
                        }
                    ]
                }

        model = home_view_model(FakeOwner())
        self.assertNotEqual(model["conversation"], UNKNOWN)
        message = model["conversation"][0]
        self.assertEqual(message["role"], "agent")
        self.assertEqual(message["run_id"], "r1")
        self.assertEqual(message["status"], "completed")
        self.assertEqual(message["intent"], "已记录输入")
        self.assertEqual(message["plan"]["steps"][0]["title"], "step1")
        self.assertEqual(message["plan"]["steps"][0]["status"], "completed")


class HomePlanCardTests(unittest.TestCase):
    def test_plan_card_renders_done_current_pending_step_states(self):
        # F5: the plan card renders a working-plan's done/current/pending steps,
        # state driven by the owner-backed projection (not run-status vocabulary).
        view = dict(VIEW)
        view["plan"] = {
            "steps": [
                {"title": "锁定 IA 方向", "status": "done"},
                {"title": "实现会话消息流", "status": "current"},
                {"title": "接入运行轨道栏", "status": "pending"},
            ]
        }
        markup = render_home(view)
        self.assertIn('class="home-section plan-section plan-card"', markup)
        self.assertIn("PLAN CARD", markup)
        self.assertIn("plan-row plan-done", markup)
        self.assertIn("plan-row plan-current", markup)
        self.assertIn("plan-row plan-pending", markup)
        self.assertIn(">✓<", markup)
        self.assertIn(">▸<", markup)
        self.assertIn(">·<", markup)
        self.assertIn('class="plan-legend"', markup)
        self.assertIn("已完成", markup)
        self.assertIn("进行中", markup)
        self.assertIn("待办", markup)
        audit = audit_rendered_html(home_manifest(), markup)
        self.assertEqual(audit["undeclared"], ())

    def test_plan_card_maps_completed_running_to_done_current(self):
        # Backwards-compatible: an owner projection using run-status vocabulary
        # still lands on the right plan-card state, never plan-completed/-running.
        view = dict(VIEW)
        view["plan"] = {
            "steps": [
                {"title": "已完成的步骤", "status": "completed"},
                {"title": "进行中的步骤", "status": "running"},
            ]
        }
        markup = render_home(view)
        self.assertIn("plan-row plan-done", markup)
        self.assertIn("plan-row plan-current", markup)
        self.assertNotIn("plan-row plan-completed", markup)
        self.assertNotIn("plan-row plan-running", markup)

    def test_view_model_projection_preserves_plan_step_states(self):
        # The owner-backed facade must pass plan step states through untouched
        # (done/current/pending) so the plan card can drive its own vocabulary.
        class FakeOwner:
            def snapshot(self):
                return {
                    "runs": [
                        {
                            "run_id": "r1",
                            "status": "completed",
                            "updated_at": "t1",
                            "task_type": "local_read_only_run",
                            "input": {"prompt": "do x"},
                            "metadata": {
                                "plan": [
                                    {"title": "s1", "status": "done"},
                                    {"title": "s2", "status": "current"},
                                    {"title": "s3", "status": "pending"},
                                ]
                            },
                        }
                    ]
                }

        model = home_view_model(FakeOwner())
        steps = model["plan"]["steps"]
        self.assertEqual(steps[0]["status"], "done")
        self.assertEqual(steps[1]["status"], "current")
        self.assertEqual(steps[2]["status"], "pending")

    def test_plan_card_section_renders_without_plan(self):
        markup = render_home({})
        self.assertIn('class="home-section plan-section plan-card"', markup)
        self.assertIn("PLAN CARD", markup)
        self.assertIn('class="plan-legend"', markup)


class HomeInspectorF7Tests(unittest.TestCase):
    def test_inspector_renders_f7_field_set(self):
        # F7: the run-facts inspector shell exposes mode, workspace, worker,
        # approval, effect and evidence links as static structure, driven by the
        # owner-backed projection. No runtime access.
        view = dict(VIEW)
        view["run_facts"] = {
            "status": "running",
            "run_id": "run-f7-01",
            "parent_child": "parent-1 / child-1",
            "mode": "local_read_only",
            "workspace": "case-local",
            "worker": "fake-loopback · fake-model",
            "approval": "granted",
            "effect": "claimed",
            "provider": "fake-loopback",
            "model": "fake-model",
            "evidence": "owner snapshot",
            "evidence_links": [
                {"title": "run.started", "identity": "evt-1", "event_id": "evt-1",
                 "href": "/record-view?run_id=run-f7-01"},
                {"title": "replay", "identity": "rep-1", "event_id": "rep-1",
                 "href": "/record-view?run_id=run-f7-01"},
            ],
            "source": "CompositionOwner",
        }
        markup = render_home(view)
        self.assertIn("运行事实", markup)
        self.assertIn(">mode<", markup)
        self.assertIn(">worker<", markup)
        self.assertIn("fake-loopback · fake-model", markup)
        self.assertIn(">approval<", markup)
        self.assertIn(">effect<", markup)
        self.assertIn('class="evidence-links"', markup)
        self.assertIn('class="evidence-link"', markup)
        self.assertIn('data-evidence-id="evt-1"', markup)
        self.assertIn("/record-view?run_id=run-f7-01", markup)
        # No undeclared reference introduced by the F7 shell.
        audit = audit_rendered_html(home_manifest(), markup)
        self.assertEqual(audit["undeclared"], ())

    def test_inspector_degrades_evidence_links_to_empty_state(self):
        view = dict(VIEW)
        view["run_facts"] = {
            "status": "unknown",
            "source": "source unknown",
            "evidence_links": UNKNOWN,
        }
        markup = render_home(view)
        self.assertIn("暂无证据链接", markup)
        self.assertNotIn('class="evidence-link-list"', markup)
        self.assertIn('data-status="unknown"', markup)

    def test_inspector_renders_unknown_f7_facts_without_relabel(self):
        view = dict(VIEW)
        view["run_facts"] = {
            "status": "unknown",
            "source": "missing identity",
            "mode": UNKNOWN,
            "worker": UNKNOWN,
            "approval": UNKNOWN,
            "effect": UNKNOWN,
        }
        markup = render_home(view)
        # F7 fields stay structurally present, showing unknown rather than a
        # fabricated value.
        self.assertIn(">mode<", markup)
        self.assertIn(">worker<", markup)
        self.assertIn(">approval<", markup)
        self.assertIn(">effect<", markup)

    def test_view_model_projects_f7_facts_from_owner(self):
        # The owner-backed facade composes mode/worker/approval/effect/evidence
        # links from recorded runs, approvals and effects without a writable path.
        class FakeOwner:
            def snapshot(self):
                return {
                    "runs": [
                        {
                            "run_id": "r1",
                            "status": "completed",
                            "updated_at": "t1",
                            "task_type": "local_read_only_run",
                            "input": {"prompt": "do x"},
                            "metadata": {
                                "workspace": "case-local",
                                "workspace_mode": "local_read_only",
                                "plan": [{"title": "step1", "status": "completed"}],
                            },
                        }
                    ],
                    "approvals": [
                        {"run_id": "r1", "status": "granted", "operation_id": "op-1"}
                    ],
                    "effects": [
                        {"run_id": "r1", "status": "claimed", "effect_id": "ef-1"}
                    ],
                    "events": [
                        {"run_id": "r1", "type": "run.started", "event_id": "evt-1"}
                    ],
                    "replays": [
                        {
                            "run_id": "r1",
                            "mode": "recorded_view",
                            "replay_id": "rep-1",
                            "provider_identity": {
                                "provider": "fake-loopback",
                                "model": "fake-model",
                            },
                        }
                    ],
                }

        model = home_view_model(FakeOwner())
        facts = model["run_facts"]
        self.assertEqual(facts["mode"], "local_read_only")
        self.assertEqual(facts["worker"], "fake-loopback · fake-model")
        self.assertEqual(facts["approval"], "granted")
        self.assertEqual(facts["effect"], "claimed")
        self.assertNotEqual(facts["evidence_links"], UNKNOWN)
        titles = [link["title"] for link in facts["evidence_links"]]
        self.assertIn("run.started", titles)
        self.assertIn("recorded_view", titles)
        for link in facts["evidence_links"]:
            self.assertTrue(link["href"].startswith("/record-view?run_id="))


class HomeRunRailF10Tests(unittest.TestCase):
    def test_run_rail_renders_lifecycle_rail_disabled_run_and_records_timeline(self):
        # F10: the run-rail shell exposes the lifecycle track, a disabled
        # "executable Run" button, owner-backed records and an evidence timeline.
        view = dict(VIEW)
        view["run_rail"] = {
            "status": "running",
            "run_id": "run-f10-01",
            "can_run": False,
            "workspace": "case-local",
            "parent_child": "parent-1 / child-1",
            "worker": "fake-loopback · fake-model",
            "owner_records": [
                {"run_id": "run-f10-01", "status": "running", "updated_at": "刚刚"},
                {"run_id": "run-f10-00", "status": "completed", "updated_at": "昨天"},
            ],
            "evidence_timeline": [
                {"type": "run.started", "event_id": "evt-1", "created_at": "2026-09-20T10:00",
                 "href": "/record-view?run_id=run-f10-01"},
                {"type": "replay", "event_id": "rep-1", "created_at": "2026-09-20T10:01",
                 "href": "/record-view?run_id=run-f10-01"},
            ],
            "source": "CompositionOwner",
        }
        markup = render_home(view)
        self.assertIn("运行轨道栏", markup)
        self.assertIn("RUN RAIL", markup)
        self.assertIn('data-ui-ref="home.run-rail"', markup)
        # Lifecycle track stages render in order.
        self.assertIn(">已创建<", markup)
        self.assertIn(">进行中<", markup)
        self.assertIn(">已完成<", markup)
        self.assertIn('rail-current', markup)
        # The executable Run button is rendered but inert.
        self.assertIn('class="rail-run-button"', markup)
        self.assertIn('aria-disabled="true"', markup)
        self.assertIn("可执行 Run", markup)
        self.assertIn("留 product gate", markup)
        # Owner records + evidence timeline.
        self.assertIn("OWNER RECORDS", markup)
        self.assertIn('class="rail-record-list"', markup)
        self.assertIn("run-f10-01", markup)
        self.assertIn("EVIDENCE TIMELINE", markup)
        self.assertIn('class="rail-timeline-list"', markup)
        self.assertIn('class="rail-timeline-link"', markup)
        self.assertIn('href="/record-view?run_id=run-f10-01"', markup)
        # No undeclared reference introduced by the F10 shell.
        audit = audit_rendered_html(home_manifest(), markup)
        self.assertEqual(audit["undeclared"], ())

    def test_run_rail_degrades_owner_records_and_timeline_to_empty(self):
        view = dict(VIEW)
        view["run_rail"] = {
            "status": "unknown",
            "source": "source unknown",
            "owner_records": UNKNOWN,
            "evidence_timeline": UNKNOWN,
        }
        markup = render_home(view)
        self.assertIn("暂无 Owner 记录", markup)
        self.assertIn("暂无证据时间线", markup)
        self.assertNotIn('class="rail-record-list"', markup)
        self.assertNotIn('class="rail-timeline-list"', markup)
        self.assertIn("source unknown", markup)

    def test_run_rail_renders_terminal_status_in_red(self):
        # A terminal status (failed / safe-stopped / denied) marks the running
        # node red and appends a terminal label instead of completing the track.
        view = dict(VIEW)
        view["run_rail"] = {
            "status": "failed",
            "run_id": "run-f10-02",
            "source": "CompositionOwner",
            "owner_records": UNKNOWN,
            "evidence_timeline": UNKNOWN,
        }
        markup = render_home(view)
        self.assertIn('class="rail-terminal"', markup)
        self.assertIn("失败", markup)
        self.assertIn("rail-current", markup)

    def test_view_model_projects_run_rail_from_owner(self):
        # The owner-backed facade composes the run-rail (records + chronological
        # timeline) from recorded runs and events without a writable path.
        class FakeOwner:
            def snapshot(self):
                return {
                    "runs": [
                        {
                            "run_id": "r1",
                            "status": "completed",
                            "updated_at": "t1",
                            "task_type": "local_read_only_run",
                            "input": {"prompt": "do x"},
                            "metadata": {
                                "workspace": "case-local",
                                "workspace_mode": "local_read_only",
                            },
                        },
                        {
                            "run_id": "r2",
                            "status": "running",
                            "updated_at": "t2",
                            "task_type": "local_read_only_run",
                            "input": {"prompt": "do y"},
                            "metadata": {"workspace": "case-local"},
                        },
                    ],
                    "events": [
                        {"run_id": "r2", "type": "run.started", "event_id": "evt-1",
                         "created_at": "2026-09-20T10:01"},
                        {"run_id": "r2", "type": "run.finished", "event_id": "evt-2",
                         "created_at": "2026-09-20T10:00"},
                    ],
                }

        model = home_view_model(FakeOwner())
        rail = model["run_rail"]
        self.assertEqual(rail["status"], "running")
        self.assertIs(rail["can_run"], False)
        # Owner records list both runs.
        self.assertNotEqual(rail["owner_records"], UNKNOWN)
        self.assertEqual(len(rail["owner_records"]), 2)
        # Evidence timeline is chronological by created_at (evt-2 before evt-1).
        self.assertNotEqual(rail["evidence_timeline"], UNKNOWN)
        titles = [n["type"] for n in rail["evidence_timeline"]]
        self.assertEqual(titles, ["run.finished", "run.started"])
        for node in rail["evidence_timeline"]:
            self.assertTrue(node["href"].startswith("/record-view?run_id="))


class HomeScenarioStateF11Tests(unittest.TestCase):
    def _view_with_state(self, state, *, source="CompositionOwner"):
        view = dict(VIEW)
        view["scenario_state"] = {"state": state, "source": source}
        return view

    def test_scenario_state_renders_four_state_stepper(self):
        # F11: the shell exposes all four scenario states in order, the active
        # one highlighted with its tone, and no undeclared reference leaks.
        markup = render_home(self._view_with_state("planning"))
        self.assertIn("场景状态", markup)
        self.assertIn("SCENARIO STATE", markup)
        self.assertIn('data-ui-ref="home.scenario-state"', markup)
        for label in ("空场景", "规划中", "待审批", "已停止"):
            self.assertIn(label, markup)
        self.assertIn("ss-node ss-active ss-planning", markup)
        self.assertNotIn("ss-node ss-active ss-empty", markup)
        self.assertNotIn("ss-node ss-active ss-approval", markup)
        self.assertNotIn("ss-node ss-active ss-stopped", markup)
        audit = audit_rendered_html(home_manifest(), markup)
        self.assertEqual(audit["undeclared"], ())

    def test_scenario_state_highlights_each_valid_state(self):
        for state, tone in (
            ("empty", "empty"),
            ("planning", "planning"),
            ("approval", "approval"),
            ("stopped", "stopped"),
        ):
            markup = render_home(self._view_with_state(state))
            self.assertIn("ss-node ss-active ss-{0}".format(tone), markup)

    def test_scenario_state_degrades_unknown_to_no_active(self):
        # A missing or unrecognised state reads as unknown: no node is active
        # and the blurb says the real judgment is deferred.
        view = dict(VIEW)
        view["scenario_state"] = {"state": "bogus", "source": "source unknown"}
        markup = render_home(view)
        self.assertNotIn("ss-active", markup)
        self.assertIn("状态未知", markup)
        self.assertIn("source unknown", markup)

    def test_scenario_state_shows_owner_backed_source(self):
        view = dict(VIEW)
        view["scenario_state"] = {"state": "stopped", "source": "CompositionOwner"}
        markup = render_home(view)
        self.assertIn("owner-backed", markup)
        self.assertIn('ss-node ss-active ss-stopped', markup)

    def test_view_model_projects_scenario_state_from_owner(self):
        # The owner-backed facade derives empty / stopped / planning from the
        # recorded runs without a writable path; "approval" derivation stays
        # behind the 1-2 product gate (F13).

        class EmptyOwner:
            def snapshot(self):
                return {"runs": []}

        class StoppedOwner:
            def snapshot(self):
                return {"runs": [{"run_id": "r1", "status": "safe_stopped", "updated_at": "t1"}]}

        class PlanningOwner:
            def snapshot(self):
                return {"runs": [{"run_id": "r1", "status": "running", "updated_at": "t1"}]}

        self.assertEqual(home_view_model(EmptyOwner())["scenario_state"]["state"], "empty")
        stopped = home_view_model(StoppedOwner())["scenario_state"]
        self.assertEqual(stopped["state"], "stopped")
        self.assertEqual(stopped["source"], "CompositionOwner")
        planning = home_view_model(PlanningOwner())["scenario_state"]
        self.assertEqual(planning["state"], "planning")


@unittest.skipUnless(chrome_available(), "the verification-stage browser is absent")
class HomeSurfaceBrowserTests(unittest.TestCase):
    def setUp(self):
        self.host = serve_workbench(view_source=lambda route: VIEW)
        self.addCleanup(self.host.close)

    def _measure(self, viewport):
        with browser() as engine:
            engine.open(self.host.base_url + "/home", viewport=viewport)
            return json.loads(
                engine.evaluate(
                    "JSON.stringify({"
                    "pageWidth: document.documentElement.clientWidth,"
                    "scrollWidth: document.documentElement.scrollWidth,"
                    "layout: getComputedStyle(document.querySelector('.home-layout')).display,"
                    "columns: getComputedStyle(document.querySelector('.home-layout')).gridTemplateColumns,"
                    "layoutWidth: document.querySelector('.home-layout').getBoundingClientRect().width,"
                    "sidebar: document.querySelector('.home-records').getBoundingClientRect().width,"
                    "content: document.querySelector('.home-content').getBoundingClientRect().width,"
                    "inspector: document.querySelector('.home-inspector').getBoundingClientRect().width"
                    "})"
                )
            )

    def test_wide_view_is_a_three_column_workbench(self):
        measured = self._measure((1280, 900))
        self.assertEqual(measured["layout"], "grid")
        self.assertEqual(measured["sidebar"], 236)
        self.assertEqual(measured["inspector"], 318)
        self.assertGreater(measured["content"], 460)
        self.assertLessEqual(measured["scrollWidth"], measured["pageWidth"])

    def test_compact_view_stacks_all_required_information_without_horizontal_scroll(self):
        measured = self._measure((390, 800))
        self.assertEqual(measured["layout"], "grid")
        self.assertEqual(measured["columns"], "{0}px".format(measured["layoutWidth"]))
        self.assertEqual(measured["sidebar"], measured["layoutWidth"])
        self.assertEqual(measured["inspector"], measured["layoutWidth"])
        self.assertLessEqual(measured["scrollWidth"], measured["pageWidth"])


if __name__ == "__main__":
    unittest.main()
