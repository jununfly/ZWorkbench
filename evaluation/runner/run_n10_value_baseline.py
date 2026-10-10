#!/usr/bin/env python3
"""N=10 product-path value-baseline harness (roadmap 1-10-6, gate ②).

This is ACCEPTANCE/EVALUATION infrastructure, not product code.  It does NOT
decide whether the product is "done"; it only measures, against a fixed task
set, whether the ZWorkbench product path (real Provider, default gate open)
saves the human time / manual re-checks relative to a bare-Codex control arm.

Three metrics per (task, arm):
  - net_time_s        wall-clock from task start to accepted completion
  - manual_review_count   times the human re-checked / re-ran mid-task
  - posthoc_review_count  times the human reviewed the artifact after the run

Two arms per task:
  - zw       the ZWorkbench product path (real_provider_gate open)
  - control  bare Codex with the SAME provider, NO orchestration layer

Value delta:
  - time_saved_pct       = (control_net - zw_net) / control_net * 100
  - review_reduction     = (control_review - zw_review)   (count, signed)

Modes:
  --self-test   embedded synthetic tasks; asserts the aggregation math; exits 0.
  --dry-run     loads --tasks, synthesizes deterministic metrics, computes + prints.
  --live        interactive; requires the human (zj) present + a REAL Provider
               (the harness never reads/prints that credential).  For each task/arm:
               EITHER a command wrapper (--zw-command / --control-command) OR manual
               ENTER timing.  Commands may embed '{prompt}' and '{id}' placeholders
               (substituted per task, shell-quoted) so a single command drives all N
               tasks with REAL wall-clock (the agent's runtime).  With
               --skip-review-prompts the two review counts default to 0 (hands-off).
               Writes an evidence summary (local-only, exercises_default_product_path=true).

NOTE: --live is NOT runnable in CI/sandbox.  It needs (a) zj at the keyboard
and (b) a real Provider credential in the environment.  The harness never
reads or prints that credential.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "zworkbench-n10-value-baseline/v1"
TASKS_SCHEMA = "zworkbench-n10-tasks/v1"


@dataclass(frozen=True)
class TaskMetrics:
    net_time_s: float
    manual_review_count: int
    posthoc_review_count: int

    @property
    def review_total(self) -> int:
        return self.manual_review_count + self.posthoc_review_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "net_time_s": self.net_time_s,
            "manual_review_count": self.manual_review_count,
            "posthoc_review_count": self.posthoc_review_count,
            "review_total": self.review_total,
        }


def compute_value_baseline(
    zw: List[TaskMetrics],
    control: Optional[List[TaskMetrics]],
) -> Dict[str, Any]:
    """Aggregate the three-metric comparison across N tasks.

    Returns signed / percentage deltas.  If ``control`` is None, only
    descriptive ZW stats are returned (no delta can be computed).
    """

    zw_total_time = sum(m.net_time_s for m in zw)
    zw_total_review = sum(m.review_total for m in zw)
    n = len(zw)

    out: Dict[str, Any] = {
        "n": n,
        "zw": {
            "total_net_time_s": zw_total_time,
            "mean_net_time_s": (zw_total_time / n) if n else 0.0,
            "total_review": zw_total_review,
            "mean_review": (zw_total_review / n) if n else 0.0,
        },
    }

    if control is None:
        out["control"] = None
        out["time_saved_pct"] = None
        out["review_reduction"] = None
        out["note"] = "no control arm supplied; delta not computable"
        return out

    if len(control) != n:
        raise ValueError("control arm length {0} != zw arm length {1}".format(len(control), n))

    control_total_time = sum(m.net_time_s for m in control)
    control_total_review = sum(m.review_total for m in control)

    out["control"] = {
        "total_net_time_s": control_total_time,
        "mean_net_time_s": (control_total_time / n) if n else 0.0,
        "total_review": control_total_review,
        "mean_review": (control_total_review / n) if n else 0.0,
    }

    time_saved_pct = (
        ((control_total_time - zw_total_time) / control_total_time * 100.0)
        if control_total_time > 0
        else None
    )
    review_reduction = control_total_review - zw_total_review

    out["time_saved_pct"] = time_saved_pct
    out["review_reduction"] = review_reduction

    per_task = []
    for i, (z, c) in enumerate(zip(zw, control)):
        ctl_t = c.net_time_s
        per_task.append(
            {
                "index": i,
                "time_saved_pct": ((ctl_t - z.net_time_s) / ctl_t * 100.0) if ctl_t > 0 else None,
                "review_reduction": c.review_total - z.review_total,
            }
        )
    out["per_task"] = per_task
    return out


def load_tasks(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != TASKS_SCHEMA:
        raise ValueError("unexpected tasks schema: {0}".format(data.get("schema")))
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("tasks must be a non-empty list")
    return tasks


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_self_test() -> int:
    # Embedded synthetic tasks; assert the math, no Provider needed.
    zw = [
        TaskMetrics(60.0, 1, 1),
        TaskMetrics(120.0, 2, 0),
        TaskMetrics(90.0, 0, 2),
    ]
    control = [
        TaskMetrics(120.0, 3, 3),
        TaskMetrics(240.0, 4, 2),
        TaskMetrics(180.0, 2, 4),
    ]
    result = compute_value_baseline(zw, control)
    # time: control 540s, zw 270s -> 50% saved
    assert abs(result["time_saved_pct"] - 50.0) < 1e-9, result
    # review: control 18, zw 6 -> reduction 12
    assert result["review_reduction"] == 12, result
    # per-task[0]: (120-60)/120*100 = 50%
    assert abs(result["per_task"][0]["time_saved_pct"] - 50.0) < 1e-9, result
    assert result["per_task"][0]["review_reduction"] == 4, result

    # control=None path
    no_ctl = compute_value_baseline(zw, None)
    assert no_ctl["time_saved_pct"] is None
    assert no_ctl["control"] is None

    # mismatch length
    try:
        compute_value_baseline(zw, control[:2])
        raise AssertionError("expected ValueError on length mismatch")
    except ValueError:
        pass

    print(json.dumps({"status": "self-test-pass", "checked": result}, ensure_ascii=False, indent=2))
    return 0


def _dry_run(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Deterministic synthetic metrics (no Provider).  ZW assumed 50% better on
    # time and 60% fewer reviews than control, with per-task jitter from index.
    zw: List[TaskMetrics] = []
    control: List[TaskMetrics] = []
    for i, t in enumerate(tasks):
        base = 60.0 + 30.0 * i
        c_time = base * 2.0
        z_time = base
        c_rev = 3 + (i % 3)
        z_rev = max(0, c_rev - 2)
        control.append(TaskMetrics(c_time, c_rev, c_rev))
        zw.append(TaskMetrics(z_time, z_rev, z_rev))
    result = compute_value_baseline(zw, control)
    return {
        "schema": SCHEMA,
        "mode": "dry-run",
        "exercises_default_product_path": False,
        "task_count": len(tasks),
        "metric_definition": {
            "net_time_s": "wall-clock task start->accepted completion (synthetic)",
            "manual_review_count": "mid-task human re-check/re-run (synthetic)",
            "posthoc_review_count": "post-run human review (synthetic)",
        },
        "synthetic_baseline": result,
        "interpretation": "Dry-run is NOT product evidence. It validates loading + math only.",
    }


def _prompt_count(prompt: str) -> int:
    while True:
        raw = input(prompt).strip()
        if raw == "":
            return 0
        try:
            v = int(raw)
            if v >= 0:
                return v
        except ValueError:
            pass
        print("  enter a non-negative integer (empty = 0)")


def _live_arm(arm: str, task: Dict[str, Any], command: Optional[str], skip_review_prompts: bool = False) -> TaskMetrics:
    print("\n--- {0} arm : task {1} ---".format(arm, task.get("id", "?")))
    print("prompt: {0}".format(task.get("prompt", "")))
    if command:
        substituted = command.replace("{prompt}", shlex.quote(str(task.get("prompt", "")))).replace(
            "{id}", shlex.quote(str(task.get("id", "")))
        )
        print("running: {0}".format(substituted))
        start = time.monotonic()
        rc = _run_command(substituted)
        elapsed = time.monotonic() - start
        print("  command exited rc={0} in {1:.1f}s".format(rc, elapsed))
    else:
        input("  press ENTER to START the timer, then complete the task in the product/Codex...")
        start = time.monotonic()
        input("  press ENTER to STOP the timer once the task is accepted...")
        elapsed = time.monotonic() - start
        print("  measured wall-clock: {0:.1f}s".format(elapsed))
    if skip_review_prompts:
        manual = 0
        posthoc = 0
    else:
        manual = _prompt_count("  manual re-check/re-run count: ")
        posthoc = _prompt_count("  post-run review count: ")
    return TaskMetrics(elapsed, manual, posthoc)


def _run_command(command: str) -> int:
    import subprocess

    rc = subprocess.call(command, shell=True, cwd=str(REPO_ROOT))
    return rc


def _live(tasks: List[Dict[str, Any]], zw_command: Optional[str], control_command: Optional[str], output: Path, skip_review_prompts: bool = False) -> int:
    zw: List[TaskMetrics] = []
    control: List[TaskMetrics] = []
    print("\n=== LIVE value baseline ===")
    print("Human (zj) must be present.  A REAL Provider credential is required in the")
    print("environment for the zw arm.  This mode is NOT runnable in CI/sandbox.\n")
    for t in tasks:
        zw.append(_live_arm("ZW (product path)", t, zw_command, skip_review_prompts))
        control.append(_live_arm("CONTROL (bare Codex)", t, control_command, skip_review_prompts))
    result = compute_value_baseline(zw, control)
    summary = {
        "schema": SCHEMA,
        "mode": "live",
        "exercises_default_product_path": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_count": len(tasks),
        "zw_metrics": [m.to_dict() for m in zw],
        "control_metrics": [m.to_dict() for m in control],
        "value_baseline": result,
        "metric_definition": {
            "net_time_s": "wall-clock task start->accepted completion",
            "manual_review_count": "mid-task human re-check/re-run",
            "posthoc_review_count": "post-run human review",
        },
        "caveat": "requires human subject + real Provider; not CI/sandbox reproducible",
    }
    _write_json(output / "n10-value-baseline.json", summary)
    print("\n=== RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nevidence written to: {0}".format(output / "n10-value-baseline.json"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, help="task list JSON ({0})".format(TASKS_SCHEMA))
    parser.add_argument("--output", type=Path, help="evidence directory (live mode)")
    parser.add_argument("--zw-command", type=str, default=None, help="optional shell cmd; '{prompt}' and '{id}' are substituted per task; runs with cwd=repo root")
    parser.add_argument("--control-command", type=str, default=None, help="optional shell cmd; '{prompt}' and '{id}' are substituted per task; runs with cwd=repo root")
    parser.add_argument("--skip-review-prompts", action="store_true", help="auto-fill review counts as 0 (hands-off); else prompted per arm")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true", help="embedded synthetic self-test of the math")
    group.add_argument("--dry-run", action="store_true", help="load --tasks, synthesize metrics, compute")
    group.add_argument("--live", action="store_true", help="interactive, requires human + real Provider")
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    if args.tasks is None:
        print(json.dumps({"status": "error", "error": "--tasks is required for dry-run/live"}, ensure_ascii=False))
        return 2
    tasks = load_tasks(args.tasks)

    if args.dry_run:
        summary = _dry_run(tasks)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.live:
        out = args.output or (REPO_ROOT / "evaluation" / "evidence" / "value-baseline-1-10-6" / "live")
        return _live(tasks, args.zw_command, args.control_command, out, args.skip_review_prompts)

    return 2


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT / "src"))
    raise SystemExit(main())
