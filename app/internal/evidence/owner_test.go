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

// ================= C28：一次性审批 token + fail-closed effect-claim =================

func TestRequestApprovalAndApprove(t *testing.T) {
	ow := newTestOwner(t)
	if _, err := ow.CreateRun("r1", "t", nil, nil); err != nil {
		t.Fatalf("create run: %v", err)
	}
	ap, err := ow.RequestApproval("r1", "op1", "write", "/tmp/x", "key1", "because")
	if err != nil {
		t.Fatalf("request approval: %v", err)
	}
	if ap.Status != "pending" {
		t.Fatalf("status = %q, want pending", ap.Status)
	}
	// 幂等：同 operation 同 run + scope 一致 → 返现有
	ap2, err := ow.RequestApproval("r1", "op1", "write", "/tmp/x", "key1", "because")
	if err != nil {
		t.Fatalf("request approval again: %v", err)
	}
	if ap2.ApprovalID != ap.ApprovalID {
		t.Fatalf("幂等失败：新生成了 approval %s != %s", ap2.ApprovalID, ap.ApprovalID)
	}
	// 另一个 run 用同 operation → 冲突
	if _, err := ow.CreateRun("r2", "t", nil, nil); err != nil {
		t.Fatalf("create run2: %v", err)
	}
	if _, err := ow.RequestApproval("r2", "op1", "write", "/tmp/x", "key1", "because"); !errors.Is(err, ErrApproval) {
		t.Fatalf("跨 run 同 operation 应返 ErrApproval，得到 %v", err)
	}

	// Approve 返回一次性 token
	tok, err := ow.Approve(ap.ApprovalID, 300)
	if err != nil {
		t.Fatalf("approve: %v", err)
	}
	if tok.Token == "" || len(tok.Token) < 20 {
		t.Fatalf("token 异常：%q", tok.Token)
	}
	// 非 pending 状态不能再批准
	if _, err := ow.Approve(ap.ApprovalID, 300); !errors.Is(err, ErrApproval) {
		t.Fatalf("重复 approve 应返 ErrApproval，得到 %v", err)
	}
}

func TestDenyApprovalBlocksApprove(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ap, _ := ow.RequestApproval("r1", "op1", "write", "/tmp/x", "key1", "because")
	if _, err := ow.DenyApproval(ap.ApprovalID, "no"); err != nil {
		t.Fatalf("deny: %v", err)
	}
	if _, err := ow.Approve(ap.ApprovalID, 300); !errors.Is(err, ErrApproval) {
		t.Fatalf("denied 后 approve 应返 ErrApproval，得到 %v", err)
	}
}

func TestClaimEffectReadonlyExecutable(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	c, err := ow.ClaimEffect("r1", "op1", "read", "/tmp/x", "k1", "read-only", "", 2, nil)
	if err != nil {
		t.Fatalf("claim read-only: %v", err)
	}
	if !c.Executable() {
		t.Fatalf("read-only 应可执行，得到 %+v", c)
	}
	if c.Reason != "new_effect" {
		t.Fatalf("reason = %q", c.Reason)
	}
}

func TestClaimEffectApprovalRequiredHappyPath(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	ap, _ := ow.RequestApproval("r1", "op1", "write", "/tmp/x", "k1", "because")
	tok, _ := ow.Approve(ap.ApprovalID, 300)
	c, err := ow.ClaimEffect("r1", "op1", "write", "/tmp/x", "k1", "approval-required", tok.Token, 2, nil)
	if err != nil {
		t.Fatalf("claim approval-required: %v", err)
	}
	if !c.Executable() {
		t.Fatalf("带有效 token 应可执行，得到 %+v", c)
	}
	// token 一次性：消费后 approval 状态变为 consumed（不再 'approved'），
	// 同一 token 不能再 claim 任何 effect（Python 先校验 status!='approved' →
	// 落入 approval_missing_or_not_approved；approval_token_replay 分支在正常流不可达）。
	c2, err := ow.ClaimEffect("r1", "op2", "write", "/tmp/x", "k2", "approval-required", tok.Token, 2, nil)
	if err != nil {
		t.Fatalf("second claim: %v", err)
	}
	if c2.Status != "denied" || c2.Reason != "approval_missing_or_not_approved" {
		t.Fatalf("token 重放应 denied(approval_missing_or_not_approved)，得到 %+v", c2)
	}
	run, _ := ow.GetRun("r1")
	if run.Status != StatusWaitingApproval {
		t.Fatalf("token 重放后 run 应 waiting_approval，得到 %s", run.Status)
	}
}

func TestClaimEffectApprovalMissingGoesWaiting(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	c, err := ow.ClaimEffect("r1", "op1", "write", "/tmp/x", "k1", "approval-required", "", 2, nil)
	if err != nil {
		t.Fatalf("claim no approval: %v", err)
	}
	if c.Status != "denied" || c.Reason != "approval_missing_or_not_approved" {
		t.Fatalf("缺审批应 denied，得到 %+v", c)
	}
	run, _ := ow.GetRun("r1")
	if run.Status != StatusWaitingApproval {
		t.Fatalf("缺审批 run 应 waiting_approval，得到 %s", run.Status)
	}
}

func TestClaimEffectApprovalScopeMismatchSafeStops(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	ap, _ := ow.RequestApproval("r1", "op1", "write", "/tmp/x", "k1", "because") // scope: action=write,resource=/tmp/x
	tok, _ := ow.Approve(ap.ApprovalID, 300)
	// 用不同 resource 申请 effect → scope 不匹配 → safe-stop
	c, err := ow.ClaimEffect("r1", "op1", "write", "/tmp/Y", "k1", "approval-required", tok.Token, 2, nil)
	if err != nil {
		t.Fatalf("claim scope mismatch: %v", err)
	}
	if c.Status != "denied" || c.Reason != "approval_scope_mismatch" {
		t.Fatalf("scope 不匹配应 denied，得到 %+v", c)
	}
	run, _ := ow.GetRun("r1")
	if run.Status != StatusSafeStopped {
		t.Fatalf("scope 不匹配 run 应 safe_stopped，得到 %s", run.Status)
	}
}

func TestClaimEffectTokenMismatchSafeStops(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	ap, _ := ow.RequestApproval("r1", "op1", "write", "/tmp/x", "k1", "because")
	ow.Approve(ap.ApprovalID, 300)
	c, err := ow.ClaimEffect("r1", "op1", "write", "/tmp/x", "k1", "approval-required", "wrong-token", 2, nil)
	if err != nil {
		t.Fatalf("claim wrong token: %v", err)
	}
	if c.Reason != "approval_token_mismatch" {
		t.Fatalf("token 错误应 mismatch，得到 %q", c.Reason)
	}
	run, _ := ow.GetRun("r1")
	if run.Status != StatusSafeStopped {
		t.Fatalf("token 错误 run 应 safe_stopped，得到 %s", run.Status)
	}
}

func TestClaimEffectUnknownClassSafeStops(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	c, err := ow.ClaimEffect("r1", "op1", "write", "/tmp/x", "k1", "forbidden", "", 2, nil)
	if err != nil {
		t.Fatalf("claim unknown class: %v", err)
	}
	if c.Reason != "unknown_effect_class" {
		t.Fatalf("未知 class 应 unknown_effect_class，得到 %q", c.Reason)
	}
	run, _ := ow.GetRun("r1")
	if run.Status != StatusSafeStopped {
		t.Fatalf("未知 class run 应 safe_stopped，得到 %s", run.Status)
	}
}

func TestClaimEffectTerminalRunDenied(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	ow.CompleteRun("r1", nil)
	c, err := ow.ClaimEffect("r1", "op1", "read", "/tmp/x", "k1", "read-only", "", 2, nil)
	if err != nil {
		t.Fatalf("claim on terminal run: %v", err)
	}
	if c.Status != "denied" || c.Reason != "run_terminal:completed" {
		t.Fatalf("终态 run 应 denied，得到 %+v", c)
	}
}

func TestClaimEffectIdempotentReplay(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	c1, _ := ow.ClaimEffect("r1", "op1", "read", "/tmp/x", "k1", "idempotent", "", 2, nil)
	if !c1.Executable() {
		t.Fatalf("首次 claim 应可执行，得到 %+v", c1)
	}
	// 同一 operation_id 重复申请（未 complete）→ in_flight（attempt_already_claimed）
	c2, err := ow.ClaimEffect("r1", "op1", "read", "/tmp/x", "k1", "idempotent", "", 2, nil)
	if err != nil {
		t.Fatalf("重复 claim: %v", err)
	}
	if c2.Status != "in_flight" || c2.Reason != "attempt_already_claimed" {
		t.Fatalf("重复 claim(未complete)应 in_flight，得到 %+v", c2)
	}
	// 完成后再 claim → already_completed（idempotent_replay）
	if _, err := ow.CompleteEffect(c1.EffectID, map[string]any{"ok": true}, nil); err != nil {
		t.Fatalf("complete: %v", err)
	}
	c3, err := ow.ClaimEffect("r1", "op1", "read", "/tmp/x", "k1", "idempotent", "", 2, nil)
	if err != nil {
		t.Fatalf("第三次 claim: %v", err)
	}
	if c3.Status != "already_completed" {
		t.Fatalf("完成后再 claim 应 already_completed，得到 %q", c3.Status)
	}
}

func TestCompleteEffectExactlyOnce(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	c, _ := ow.ClaimEffect("r1", "op1", "write", "/tmp/x", "k1", "idempotent", "", 2, nil)
	eff, err := ow.CompleteEffect(c.EffectID, map[string]any{"ok": true}, nil)
	if err != nil {
		t.Fatalf("complete effect: %v", err)
	}
	if eff.Status != "completed" || eff.PhysicalEffectCount != 1 {
		t.Fatalf("effect 应 completed/count=1，得到 %+v", eff)
	}
	// 幂等：再 complete 不应再 +1
	eff2, err := ow.CompleteEffect(c.EffectID, map[string]any{"ok": true}, nil)
	if err != nil {
		t.Fatalf("complete effect again: %v", err)
	}
	if eff2.PhysicalEffectCount != 1 {
		t.Fatalf("重复 complete 不应增加物理次数，得到 %d", eff2.PhysicalEffectCount)
	}
}

func TestClaimEffectDeclaredExposureBoundary(t *testing.T) {
	ow := newTestOwner(t)
	ow.CreateRun("r1", "t", nil, nil)
	ow.StartRun("r1")
	// 声明只放行 read-only；申请 idempotent 越界 → safe-stop
	_, err := ow.RecordDeclaredExposure("r1", []string{"read-only"}, map[string]any{"workspace_root": "/tmp/work"})
	if err != nil {
		t.Fatalf("record exposure: %v", err)
	}
	c, err := ow.ClaimEffect("r1", "op1", "write", "/tmp/x", "k1", "idempotent", "", 2, nil)
	if err != nil {
		t.Fatalf("claim over-declared: %v", err)
	}
	if c.Status != "denied" || c.Reason != "side_effect_not_declared" {
		t.Fatalf("越界 effect 应 side_effect_not_declared，得到 %+v", c)
	}
	run, _ := ow.GetRun("r1")
	if run.Status != StatusSafeStopped {
		t.Fatalf("越界 effect run 应 safe_stopped，得到 %s", run.Status)
	}
}
