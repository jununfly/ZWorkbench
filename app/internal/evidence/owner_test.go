package evidence

import (
	"errors"
	"testing"
)

func newTestOwner(t *testing.T) *Owner {
	t.Helper()
	ow, err := Open(":memory:")
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { _ = ow.Close() })
	return ow
}

// 直接把某个 run 的状态设为指定值（白盒测试用，绕过生命周期方法）。
func setStatus(t *testing.T, ow *Owner, runID string, s RunStatus) {
	t.Helper()
	if _, err := ow.db.Exec(`UPDATE runs SET status=? WHERE run_id=?`, s, runID); err != nil {
		t.Fatalf("setStatus: %v", err)
	}
}

func TestCreateRun(t *testing.T) {
	ow := newTestOwner(t)
	r, err := ow.CreateRun("r1", "task-a", map[string]any{"x": 1}, map[string]any{"owner": "zw"})
	if err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	if r.Status != StatusCreated {
		t.Fatalf("status = %q, want created", r.Status)
	}
	if r.RunID != "r1" || r.TaskType != "task-a" {
		t.Fatalf("fields wrong: %+v", r)
	}
	// 重复创建 → ErrRunExists
	if _, err := ow.CreateRun("r1", "task-a", nil, nil); !errors.Is(err, ErrRunExists) {
		t.Fatalf("dup create err = %v, want ErrRunExists", err)
	}
	// 空 run_id → ErrBadArgument
	if _, err := ow.CreateRun("", "t", nil, nil); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("empty id err = %v, want ErrBadArgument", err)
	}
}

func TestStartRunTransitions(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	// created → running
	r, err := ow.StartRun("r1")
	if err != nil {
		t.Fatalf("StartRun: %v", err)
	}
	if r.Status != StatusRunning {
		t.Fatalf("status = %q, want running", r.Status)
	}
	// running → running 幂等
	if _, err := ow.StartRun("r1"); err != nil {
		t.Fatalf("idempotent StartRun: %v", err)
	}
	// 终态 → running 被拒
	ow.CreateRun("r2", "t", nil, nil)
	ow.StartRun("r2")
	if _, err := ow.CompleteRun("r2", nil); err != nil {
		t.Fatalf("complete r2: %v", err)
	}
	if _, err := ow.StartRun("r2"); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("start terminal err = %v, want ErrInvalidTransition", err)
	}
}

func TestCompleteRunGuards(t *testing.T) {
	ow := newTestOwner(t)
	// running 且无挂起 → completed
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	r, err := ow.CompleteRun("r1", map[string]any{"ok": true})
	if err != nil {
		t.Fatalf("CompleteRun: %v", err)
	}
	if r.Status != StatusCompleted {
		t.Fatalf("status = %q, want completed", r.Status)
	}
	// 找到 run.completed 事件且携带 semantic payload
	var found bool
	for _, e := range r.Events {
		if e.Type == "run.completed" {
			found = true
			if e.Payload["semantic"] == nil {
				t.Fatalf("run.completed 缺 semantic payload")
			}
		}
	}
	if !found {
		t.Fatalf("未记录 run.completed 事件")
	}

	// 非 running → 拒绝
	ow.CreateRun("r2", "t", nil, nil)
	if _, err := ow.CompleteRun("r2", nil); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("complete created err = %v, want ErrInvalidTransition", err)
	}

	// 有 pending approval → 拒绝
	ow.CreateRun("r3", "t", nil, nil)
	ow.StartRun("r3")
	_, err = ow.db.Exec(`INSERT INTO approvals(approval_id, run_id, operation_id, action, resource, idempotency_key, reason, status, created_at)
		VALUES ('a1','r3','op1','act','res','idem1','why','pending','now')`)
	if err != nil {
		t.Fatalf("insert approval: %v", err)
	}
	if _, err := ow.CompleteRun("r3", nil); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("complete w/ pending approval err = %v, want ErrInvalidTransition", err)
	}

	// 有 unresolved effect → 拒绝
	ow.CreateRun("r4", "t", nil, nil)
	ow.StartRun("r4")
	_, err = ow.db.Exec(`INSERT INTO effects(effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, status, attempt, max_attempts, physical_effect_count, created_at, updated_at)
		VALUES ('e1','r4','op2','idem2','cls','act','res','claimed',1,3,0,'now','now')`)
	if err != nil {
		t.Fatalf("insert effect: %v", err)
	}
	if _, err := ow.CompleteRun("r4", nil); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("complete w/ unresolved effect err = %v, want ErrInvalidTransition", err)
	}
}

func TestFailRun(t *testing.T) {
	ow := newTestOwner(t)
	// 无未决 effect → failed
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	if _, err := ow.FailRun("r1", "boom"); err != nil {
		t.Fatalf("FailRun: %v", err)
	}
	r, _ := ow.GetRun("r1")
	if r.Status != StatusFailed {
		t.Fatalf("status = %q, want failed", r.Status)
	}
	// 有未决 effect → safe_stopped + ErrInvalidTransition
	ow.CreateRun("r2", "t", nil, nil)
	ow.StartRun("r2")
	_, err := ow.db.Exec(`INSERT INTO effects(effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, status, attempt, max_attempts, physical_effect_count, created_at, updated_at)
		VALUES ('e2','r2','op3','idem3','cls','act','res','uncertain',1,3,0,'now','now')`)
	if err != nil {
		t.Fatalf("insert effect: %v", err)
	}
	if _, err := ow.FailRun("r2", "boom"); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("fail w/ uncertain effect err = %v, want ErrInvalidTransition", err)
	}
	r, _ = ow.GetRun("r2")
	if r.Status != StatusSafeStopped {
		t.Fatalf("status = %q, want safe_stopped", r.Status)
	}
}

func TestSafeStopRun(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	if _, err := ow.SafeStopRun("r1", "manual"); err != nil {
		t.Fatalf("SafeStopRun: %v", err)
	}
	r, _ := ow.GetRun("r1")
	if r.Status != StatusSafeStopped {
		t.Fatalf("status = %q, want safe_stopped", r.Status)
	}
	// 终态(completed) → safe_stopped 被矩阵拒绝（注意：已 safe_stopped 的 run 是 no-op，不报错）
	ow.CreateRun("r3", "t", nil, nil)
	ow.StartRun("r3")
	ow.CompleteRun("r3", nil)
	if _, err := ow.SafeStopRun("r3", "again"); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("safe-stop terminal err = %v, want ErrInvalidTransition", err)
	}
	// 空 reason → ErrBadArgument
	if _, err := ow.SafeStopRun("r1", ""); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("empty reason err = %v, want ErrBadArgument", err)
	}
}

func TestBeginRecovery(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	if _, err := ow.BeginRecovery("r1", "investigate"); err != nil {
		t.Fatalf("BeginRecovery: %v", err)
	}
	r, _ := ow.GetRun("r1")
	if r.Status != StatusRecovering {
		t.Fatalf("status = %q, want recovering", r.Status)
	}
	// 有未决 effect → 拒绝
	_, err := ow.db.Exec(`INSERT INTO effects(effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, status, attempt, max_attempts, physical_effect_count, created_at, updated_at)
		VALUES ('e3','r1','op4','idem4','cls','act','res','retryable',1,3,0,'now','now')`)
	if err != nil {
		t.Fatalf("insert effect: %v", err)
	}
	if _, err := ow.BeginRecovery("r1", "x"); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("recover w/ unresolved effect err = %v, want ErrInvalidTransition", err)
	}
}

func TestRestartRun(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	ow.CompleteRun("r1", nil)
	// 终态 → 重新武装为 running（审计逃生舱）
	r, err := ow.RestartRun("r1", "redeploy")
	if err != nil {
		t.Fatalf("RestartRun: %v", err)
	}
	if r.Status != StatusRunning {
		t.Fatalf("status = %q, want running", r.Status)
	}
	// running → no-op
	if _, err := ow.RestartRun("r1", "x"); err != nil {
		t.Fatalf("restart running: %v", err)
	}
	// 空 reason → ErrBadArgument
	if _, err := ow.RestartRun("r1", ""); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("empty reason err = %v, want ErrBadArgument", err)
	}
}

func TestWaitingApprovalTransitions(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	// 直接把状态置为 waiting_approval（request_approval 属 1-5-6-2，此处白盒设置以测矩阵）
	setStatus(t, ow, "r1", StatusWaitingApproval)
	// waiting_approval → running
	if _, err := ow.StartRun("r1"); err != nil {
		t.Fatalf("waiting→running: %v", err)
	}
	// 再置回，测 waiting_approval → safe_stopped
	setStatus(t, ow, "r1", StatusWaitingApproval)
	if _, err := ow.SafeStopRun("r1", "abort"); err != nil {
		t.Fatalf("waiting→safe_stopped: %v", err)
	}
	// 再建一个测 waiting_approval → failed
	ow.CreateRun("r2", "t", nil, nil)
	ow.StartRun("r2")
	setStatus(t, ow, "r2", StatusWaitingApproval)
	if _, err := ow.FailRun("r2", "denied"); err != nil {
		t.Fatalf("waiting→failed: %v", err)
	}
	r, _ := ow.GetRun("r2")
	if r.Status != StatusFailed {
		t.Fatalf("status = %q, want failed", r.Status)
	}
}

func TestDetectIdentityViolations(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	// 孤儿事件（run_id 不存在）
	_, err := ow.db.Exec(`INSERT INTO events(event_id, run_id, type, payload_json, evidence_source, created_at) VALUES ('ev1','ghost','x','{}','native','now')`)
	if err != nil {
		t.Fatalf("insert orphan event: %v", err)
	}
	v, err := ow.DetectIdentityViolations("")
	if err != nil {
		t.Fatalf("Detect: %v", err)
	}
	if len(v) != 1 || v[0].Kind != "orphan_events_run" {
		t.Fatalf("violations = %+v, want 1 orphan_events_run", v)
	}
	// 带 scope 仍命中 ghost
	v, _ = ow.DetectIdentityViolations("ghost")
	if len(v) != 1 {
		t.Fatalf("scoped violations = %d, want 1", len(v))
	}
	// scope 为合法 run → 0
	v, _ = ow.DetectIdentityViolations("r1")
	if len(v) != 0 {
		t.Fatalf("scoped r1 violations = %d, want 0", len(v))
	}

	// 孤儿 approval 引用
	_, err = ow.db.Exec(`INSERT INTO effects(effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, status, attempt, max_attempts, physical_effect_count, created_at, updated_at)
		VALUES ('e9','r1','op9','idem9','cls','act','res','claimed',1,3,0,'now','now')`)
	if err != nil {
		t.Fatalf("insert effect: %v", err)
	}
	_, err = ow.db.Exec(`UPDATE effects SET approval_id='missing' WHERE effect_id='e9'`)
	if err != nil {
		t.Fatalf("set approval_id: %v", err)
	}
	v, _ = ow.DetectIdentityViolations("")
	if len(v) != 2 {
		t.Fatalf("violations = %d, want 2 (orphan event + orphan approval)", len(v))
	}
	var hasApproval bool
	for _, x := range v {
		if x.Kind == "orphan_effect_approval" {
			hasApproval = true
		}
	}
	if !hasApproval {
		t.Fatalf("missing orphan_effect_approval: %+v", v)
	}
}

func TestRecordEventAndExposure(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	eid, err := ow.RecordEvent("r1", "custom.event", map[string]any{"k": "v"}, EvidenceSourcePluginComposed)
	if err != nil {
		t.Fatalf("RecordEvent: %v", err)
	}
	if eid == "" {
		t.Fatalf("empty event id")
	}
	if _, err := ow.RecordEvent("r1", "", nil, ""); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("empty type err = %v, want ErrBadArgument", err)
	}
	exp, err := ow.RecordDeclaredExposure("r1", []string{"side1"}, map[string]any{"level": "low"})
	if err != nil {
		t.Fatalf("RecordDeclaredExposure: %v", err)
	}
	if exp.DeclaredAt == "" {
		t.Fatalf("empty declared_at")
	}
	r, _ := ow.GetRun("r1")
	if r.Exposure == nil || r.Exposure.DeclaredAt == "" {
		t.Fatalf("exposure not loaded in GetRun")
	}
	if len(r.Events) < 2 { // run.created + custom.event
		t.Fatalf("events = %d, want >=2", len(r.Events))
	}
}

func TestFullLifecycle(t *testing.T) {
	ow := newTestOwner(t)
	r, _ := ow.CreateRun("r1", "deploy", map[string]any{"env": "prod"}, nil)
	if r.Status != StatusCreated {
		t.Fatalf("created")
	}
	ow.StartRun("r1")
	ow.BeginRecovery("r1", "flap")
	ow.RestartRun("r1", "ok") // recovering→running
	r, _ = ow.GetRun("r1")
	if r.Status != StatusRunning {
		t.Fatalf("after restart want running, got %q", r.Status)
	}
	ow.CompleteRun("r1", "done")
	r, _ = ow.GetRun("r1")
	if r.Status != StatusCompleted {
		t.Fatalf("want completed, got %q", r.Status)
	}
	// 终态不可再 restart 进 running？可（审计逃生舱），验证一次
	ow.RestartRun("r1", "redeploy")
	r, _ = ow.GetRun("r1")
	if r.Status != StatusRunning {
		t.Fatalf("escape-hatch restart want running, got %q", r.Status)
	}
}
