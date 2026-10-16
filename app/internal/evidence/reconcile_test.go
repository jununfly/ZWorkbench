package evidence

import (
	"errors"
	"testing"
)

// 白盒插入一个 effect（绕过 ClaimEffect，聚焦 uncertain/reconcile 状态机）。
// operation_id / idempotency_key 由 effectID 派生以保证唯一；effect_class 透传给调用方，
// 需要走 ClaimEffect 有界重试的测试必须传合法 class（如 idempotent）。
func insertEffect(t *testing.T, ow *Owner, effectID, runID, status, effectClass string) {
	t.Helper()
	op := "op-" + effectID
	idem := "idem-" + effectID
	_, err := ow.db.Exec(
		`INSERT INTO effects(effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, status, attempt, max_attempts, physical_effect_count, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, 'act', 'res', ?, 1, 3, 0, 'now', 'now')`,
		effectID, runID, op, idem, effectClass, status)
	if err != nil {
		t.Fatalf("insert effect %s: %v", effectID, err)
	}
}

func findEffect(r *Run, effectID string) *Effect {
	for i := range r.Effects {
		if r.Effects[i].EffectID == effectID {
			return &r.Effects[i]
		}
	}
	return nil
}

// ================= 1-4-1：reconcile / uncertain 恢复路径 =================

func TestMarkEffectUncertain(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	insertEffect(t, ow, "e1", "r1", "claimed", "idempotent")

	e, err := ow.MarkEffectUncertain("e1", map[string]any{"why": "caller crashed"})
	if err != nil {
		t.Fatalf("MarkEffectUncertain: %v", err)
	}
	if e.Status != "uncertain" {
		t.Fatalf("effect status = %q, want uncertain", e.Status)
	}
	run, _ := ow.GetRun("r1")
	if run.Status != StatusRecovering {
		t.Fatalf("run status = %q, want recovering", run.Status)
	}
	// effect.uncertain 事件已记录
	var found bool
	for _, ev := range run.Events {
		if ev.Type == "effect.uncertain" {
			found = true
		}
	}
	if !found {
		t.Fatalf("缺少 effect.uncertain 事件")
	}

	// 幂等：再标记一次不报错、不重复写状态
	if _, err := ow.MarkEffectUncertain("e1", nil); err != nil {
		t.Fatalf("idempotent MarkEffectUncertain: %v", err)
	}
	run, _ = ow.GetRun("r1")
	if run.Status != StatusRecovering {
		t.Fatalf("幂等后 run 仍应 recovering，得到 %s", run.Status)
	}

	// 非 claimed 状态 → fail-closed 拒绝（completed）
	insertEffect(t, ow, "e2", "r1", "completed", "idempotent")
	if _, err := ow.MarkEffectUncertain("e2", nil); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("mark completed effect err = %v, want ErrInvalidTransition", err)
	}
}

func TestReconcileEffectApplied(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	insertEffect(t, ow, "e1", "r1", "claimed", "idempotent")
	if _, err := ow.MarkEffectUncertain("e1", "crash"); err != nil {
		t.Fatalf("mark uncertain: %v", err)
	}
	// run 现在 recovering
	run, _ := ow.GetRun("r1")
	if run.Status != StatusRecovering {
		t.Fatalf("precondition run = %q, want recovering", run.Status)
	}

	receipt := map[string]any{"remote_id": "abc", "confirmed": true}
	e, err := ow.ReconcileEffect("e1", "applied", receipt)
	if err != nil {
		t.Fatalf("ReconcileEffect applied: %v", err)
	}
	if e.Status != "completed" || e.PhysicalEffectCount != 1 {
		t.Fatalf("effect 应 completed/count=1，得到 %+v", e)
	}
	run, _ = ow.GetRun("r1")
	if run.Status != StatusRunning {
		t.Fatalf("applied 后 run 应回到 running，得到 %s", run.Status)
	}
	// external_receipt_json 应记录 receipt（随事件 payload/effect 投影）
	var found bool
	for _, ev := range run.Events {
		if ev.Type == "effect.reconciled" && ev.Payload["outcome"] == "applied" {
			found = true
		}
	}
	if !found {
		t.Fatalf("缺少 effect.reconciled(applied) 事件")
	}
	fe := findEffect(run, "e1")
	if fe == nil {
		t.Fatalf("effect e1 未投影")
	}
}

func TestReconcileEffectNotAppliedPermitsRetry(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	insertEffect(t, ow, "e1", "r1", "claimed", "idempotent")
	ow.MarkEffectUncertain("e1", "timeout")
	e, err := ow.ReconcileEffect("e1", "not-applied", map[string]any{"observed": "no-side-effect"})
	if err != nil {
		t.Fatalf("ReconcileEffect not-applied: %v", err)
	}
	if e.Status != "retryable" {
		t.Fatalf("not-applied 应置 retryable，得到 %q", e.Status)
	}
	run, _ := ow.GetRun("r1")
	if run.Status != StatusRunning {
		t.Fatalf("not-applied 后 run 应 running，得到 %s", run.Status)
	}
	// retryable 允许再次 ClaimEffect 走有界重试（bounded_retry 路径）；scope 须与原始 effect 一致
	c, err := ow.ClaimEffect("r1", "op-e1", "act", "res", "idem-e1", "idempotent", "", 3, nil)
	if err != nil {
		t.Fatalf("claim after not-applied: %v", err)
	}
	if !c.Executable() {
		t.Fatalf("not-applied 后应允许有界重试 claim，得到 %+v", c)
	}
}

func TestReconcileEffectUnknownSafeStops(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	insertEffect(t, ow, "e1", "r1", "claimed", "idempotent")
	ow.MarkEffectUncertain("e1", "crash")
	e, err := ow.ReconcileEffect("e1", "unknown", nil)
	if err != nil {
		t.Fatalf("ReconcileEffect unknown: %v", err)
	}
	if e.Status != "unknown" {
		t.Fatalf("unknown 出向 effect 应置 unknown，得到 %q", e.Status)
	}
	run, _ := ow.GetRun("r1")
	if run.Status != StatusSafeStopped {
		t.Fatalf("unknown 出向 run 应 safe_stopped，得到 %s", run.Status)
	}
	// 不推断成功、不自动 retry：effect 仍 unknown（非 completed、非 retryable）
	fe := findEffect(run, "e1")
	if fe == nil || fe.Status != "unknown" {
		t.Fatalf("effect 应保持 unknown，得到 %+v", fe)
	}
}

func TestReconcileEffectGuards(t *testing.T) {
	ow := newTestOwner(t)
	// 非法 observed_outcome → ErrBadArgument
	if _, err := ow.ReconcileEffect("eX", "bogus", nil); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("bogus outcome err = %v, want ErrBadArgument", err)
	}
	// 从 claimed 直接 reconcile（未先 uncertain）→ fail-closed
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	insertEffect(t, ow, "e1", "r1", "claimed", "idempotent")
	if _, err := ow.ReconcileEffect("e1", "applied", nil); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("reconcile from claimed err = %v, want ErrInvalidTransition", err)
	}
	// completed 幂等返回（即使从未 uncertain）
	insertEffect(t, ow, "e2", "r1", "completed", "idempotent")
	e, err := ow.ReconcileEffect("e2", "applied", nil)
	if err != nil {
		t.Fatalf("reconcile completed: %v", err)
	}
	if e.Status != "completed" {
		t.Fatalf("completed 应幂等返回 completed，得到 %q", e.Status)
	}
}

func TestReconcileEffectFromRetryable(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	insertEffect(t, ow, "e1", "r1", "retryable", "idempotent")
	// retryable 也允许收口（与 uncertain 同权）
	e, err := ow.ReconcileEffect("e1", "applied", map[string]any{"ok": true})
	if err != nil {
		t.Fatalf("reconcile retryable→applied: %v", err)
	}
	if e.Status != "completed" || e.PhysicalEffectCount != 1 {
		t.Fatalf("retryable→applied 应 completed/count=1，得到 %+v", e)
	}
}
