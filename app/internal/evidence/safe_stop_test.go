package evidence

import (
	"errors"
	"testing"
)

// ---- 1-4-5：C28 safe-stop 的触发与收口（对齐 composition.py:1045/1065）----
// 先红后绿：这些用例在实现落地前必须失败（方法不存在 / 语义未对齐）。

func newSafeStopOwner(t *testing.T) *Owner {
	t.Helper()
	ow := newTestOwner(t)
	return ow
}

// TestSafeStopOnIdentityViolation_CleanRun 校验「检测本身不中断健康 run」：
// 无违例时状态不动、SafeStopped=false，也不产生 safe_stopped 事件。
func TestSafeStopOnIdentityViolation_CleanRun(t *testing.T) {
	ow := newSafeStopOwner(t)
	if _, err := ow.CreateRun("ss-clean", "coding", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	out, err := ow.SafeStopOnIdentityViolation("ss-clean")
	if err != nil {
		t.Fatalf("SafeStopOnIdentityViolation: %v", err)
	}
	if out.SafeStopped {
		t.Fatalf("无违例不应 safe-stop: %+v", out)
	}
	if len(out.Violations) != 0 {
		t.Fatalf("无违例不应有 findings: %+v", out.Violations)
	}
	if out.Status != StatusCreated {
		t.Fatalf("状态应保持 created, 实际 %s", out.Status)
	}
	evs, err := ow.ListEvents("ss-clean", "run.safe_stopped", 0)
	if err != nil {
		t.Fatalf("ListEvents: %v", err)
	}
	if len(evs) != 0 {
		t.Fatalf("健康 run 不应产生 safe_stopped 事件: %+v", evs)
	}
}

// TestSafeStopOnIdentityViolation_Violation 校验有违例时触发 safe-stop，
// 并把完整 findings 落进 run.identity.violation 事件（可复核「为什么被停」）。
func TestSafeStopOnIdentityViolation_Violation(t *testing.T) {
	ow := newSafeStopOwner(t)
	// metadata 的 parent_run_id 指向不存在的 run → broken_parent_run_id（可归属到本 run）
	if _, err := ow.CreateRun("ss-dirty", "coding", nil, map[string]any{"parent_run_id": "ss-ghost-parent"}); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	out, err := ow.SafeStopOnIdentityViolation("ss-dirty")
	if err != nil {
		t.Fatalf("SafeStopOnIdentityViolation: %v", err)
	}
	if !out.SafeStopped {
		t.Fatalf("有违例应 safe-stop: %+v", out)
	}
	if out.Status != StatusSafeStopped {
		t.Fatalf("状态应为 safe_stopped, 实际 %s", out.Status)
	}
	if len(out.Violations) != 1 || out.Violations[0].Kind != "broken_parent_run_id" {
		t.Fatalf("findings 不符: %+v", out.Violations)
	}
	// 状态确实落到库里
	run, err := ow.GetRun("ss-dirty")
	if err != nil {
		t.Fatalf("GetRun: %v", err)
	}
	if run.Status != StatusSafeStopped {
		t.Fatalf("库内状态应为 safe_stopped, 实际 %s", run.Status)
	}
	// 事件双写：状态转移事件 + 违例明细事件
	evs, err := ow.ListEvents("ss-dirty", "run.identity.violation", 0)
	if err != nil {
		t.Fatalf("ListEvents(violation): %v", err)
	}
	if len(evs) != 1 {
		t.Fatalf("run.identity.violation 应 1 条, 实际 %d", len(evs))
	}
	if evs[0].Payload["reason"] != "identity_unresolved" {
		t.Fatalf("violation 事件应带 reason=identity_unresolved: %+v", evs[0].Payload)
	}
	ss, err := ow.ListEvents("ss-dirty", "run.safe_stopped", 0)
	if err != nil {
		t.Fatalf("ListEvents(safe_stopped): %v", err)
	}
	if len(ss) != 1 {
		t.Fatalf("run.safe_stopped 应 1 条, 实际 %d", len(ss))
	}
}

// TestSafeStopOnIdentityViolation_AlreadyStopped 校验已 safe_stopped 的 run
// 不重复转移（终态无出边），但违例事件仍然记录。
func TestSafeStopOnIdentityViolation_AlreadyStopped(t *testing.T) {
	ow := newSafeStopOwner(t)
	if _, err := ow.CreateRun("ss-twice", "coding", nil, map[string]any{"child_run_id": "ss-ghost-child"}); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	first, err := ow.SafeStopOnIdentityViolation("ss-twice")
	if err != nil {
		t.Fatalf("第一次: %v", err)
	}
	if !first.SafeStopped {
		t.Fatalf("第一次应 safe-stop: %+v", first)
	}
	second, err := ow.SafeStopOnIdentityViolation("ss-twice")
	if err != nil {
		t.Fatalf("第二次不应报错（终态 no-op）: %v", err)
	}
	if second.Status != StatusSafeStopped {
		t.Fatalf("第二次状态应仍为 safe_stopped, 实际 %s", second.Status)
	}
	ss, _ := ow.ListEvents("ss-twice", "run.safe_stopped", 0)
	if len(ss) != 1 {
		t.Fatalf("不应重复转移, run.safe_stopped 应 1 条, 实际 %d", len(ss))
	}
	ve, _ := ow.ListEvents("ss-twice", "run.identity.violation", 0)
	if len(ve) != 2 {
		t.Fatalf("每次调用都应记违例事件, 实际 %d", len(ve))
	}
}

// TestSafeStopOnIdentityViolation_UnknownRun 校验未知 run fail-closed。
func TestSafeStopOnIdentityViolation_UnknownRun(t *testing.T) {
	ow := newSafeStopOwner(t)
	if _, err := ow.SafeStopOnIdentityViolation("ss-no-such-run"); !errors.Is(err, ErrRunNotFound) {
		t.Fatalf("未知 run 应拒 ErrRunNotFound, 实际: %v", err)
	}
}

// TestReconcileIdentity_Resolved 校验图干净时 outcome=resolved 且不改状态。
func TestReconcileIdentity_Resolved(t *testing.T) {
	ow := newSafeStopOwner(t)
	if _, err := ow.CreateRun("ss-rec-clean", "coding", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	out, err := ow.ReconcileIdentity("ss-rec-clean", nil)
	if err != nil {
		t.Fatalf("ReconcileIdentity: %v", err)
	}
	if out.Outcome != "resolved" {
		t.Fatalf("outcome 应为 resolved, 实际 %s", out.Outcome)
	}
	if out.Status != StatusCreated {
		t.Fatalf("resolved 不应改状态, 实际 %s", out.Status)
	}
	if len(out.Violations) != 0 {
		t.Fatalf("resolved 不应带 findings: %+v", out.Violations)
	}
	evs, _ := ow.ListEvents("ss-rec-clean", "run.identity.reconciled", 0)
	if len(evs) != 1 || evs[0].Payload["outcome"] != "resolved" {
		t.Fatalf("reconciled 事件不符: %+v", evs)
	}
	if evs[0].Payload["violation_count"] != float64(0) {
		t.Fatalf("violation_count 应为 0: %+v", evs[0].Payload)
	}
}

// TestReconcileIdentity_UnknownNeverResurrects 校验：仍有违例 → outcome=unknown
// 且落 safe_stopped；违例清除后再收口 → outcome=resolved，但**终态不复活**。
func TestReconcileIdentity_UnknownNeverResurrects(t *testing.T) {
	ow := newSafeStopOwner(t)
	runID := "ss-rec-dirty"
	if _, err := ow.CreateRun(runID, "coding", nil, map[string]any{"parent_run_id": "ss-ghost-parent"}); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	out, err := ow.ReconcileIdentity(runID, map[string]any{"note": "first pass"})
	if err != nil {
		t.Fatalf("ReconcileIdentity(dirty): %v", err)
	}
	if out.Outcome != "unknown" {
		t.Fatalf("有违例 outcome 应为 unknown, 实际 %s", out.Outcome)
	}
	if out.Status != StatusSafeStopped {
		t.Fatalf("有违例应落 safe_stopped, 实际 %s", out.Status)
	}
	if len(out.Violations) != 1 {
		t.Fatalf("应带回 findings: %+v", out.Violations)
	}

	// 清掉断链（把 metadata 里的 parent_run_id 抹掉）后再收口
	if _, err := ow.DB().Exec(`UPDATE runs SET metadata_json='{}' WHERE run_id=?`, runID); err != nil {
		t.Fatalf("清理 metadata: %v", err)
	}
	again, err := ow.ReconcileIdentity(runID, nil)
	if err != nil {
		t.Fatalf("ReconcileIdentity(clean): %v", err)
	}
	if again.Outcome != "resolved" {
		t.Fatalf("清空后 outcome 应为 resolved, 实际 %s", again.Outcome)
	}
	if again.Status != StatusSafeStopped {
		t.Fatalf("safe_stopped 是终态，收口成功也不复活, 实际 %s", again.Status)
	}
	run, _ := ow.GetRun(runID)
	if run.Status != StatusSafeStopped {
		t.Fatalf("库内状态应仍为 safe_stopped, 实际 %s", run.Status)
	}
}

// TestReconcileIdentity_UnknownRun 校验未知 run fail-closed。
func TestReconcileIdentity_UnknownRun(t *testing.T) {
	ow := newSafeStopOwner(t)
	if _, err := ow.ReconcileIdentity("ss-no-such-run", nil); !errors.Is(err, ErrRunNotFound) {
		t.Fatalf("未知 run 应拒 ErrRunNotFound, 实际: %v", err)
	}
}

// TestDetectIdentityViolations_Coverage 校验 1-4-5 补上的三类覆盖面：
// provider_exit_ledger 子表 / effect_attempts→effects 孤儿 / metadata 双向断链。
func TestDetectIdentityViolations_Coverage(t *testing.T) {
	ow := newSafeStopOwner(t)
	if _, err := ow.CreateRun("ss-cov-run", "coding", nil, map[string]any{
		"parent_run_id": "ss-ghost-parent",
		"child_run_id":  "ss-ghost-child",
	}); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	// 1) provider_exit_ledger 孤儿（1-4-3 加了表却没进扫描）
	if _, err := ow.DB().Exec(
		`INSERT INTO provider_exit_ledger(ledger_id, run_id, provider, endpoint, account_scope, exit_mode, exit_status,
			provider_remote_zero_residue, surface_observations_json, statuses_json, unknown_fields_json,
			local_state_fingerprint, evidence_class, recorded_at)
		 VALUES ('ss-cov-ledger', 'ss-ghost-ledger-run', 'p', 'https://x', 'unknown', 'inventory-only',
			'unknown/safe-stop', 'unknown/delegated', '{}', '{}', '[]', 'unknown', 'local-inventory', 'now')`); err != nil {
		t.Fatalf("插入孤儿 ledger: %v", err)
	}
	// 2) effect_attempts 指向不存在的 effect
	if _, err := ow.DB().Exec(
		`INSERT INTO effect_attempts(effect_id, attempt, status, started_at) VALUES ('ss-ghost-effect', 1, 'claimed', 'now')`); err != nil {
		t.Fatalf("插入孤儿 attempt: %v", err)
	}

	all, err := ow.DetectIdentityViolations("")
	if err != nil {
		t.Fatalf("Detect: %v", err)
	}
	kinds := map[string]int{}
	for _, v := range all {
		kinds[v.Kind]++
	}
	for _, want := range []string{
		"orphan_provider_exit_ledger_run",
		"orphan_effect_attempt_effect",
		"broken_parent_run_id",
		"broken_child_run_id",
	} {
		if kinds[want] == 0 {
			t.Fatalf("缺 %s（实际 kinds=%+v）", want, kinds)
		}
	}

	// 作用域：metadata 断链可归属到本 run；孤儿 attempt 归属 unknown（full audit 才报）
	scoped, err := ow.DetectIdentityViolations("ss-cov-run")
	if err != nil {
		t.Fatalf("Detect(scoped): %v", err)
	}
	if len(scoped) != 2 {
		t.Fatalf("scoped 应 2 条(parent+child 断链), 实际 %d: %+v", len(scoped), scoped)
	}
	for _, v := range scoped {
		if v.RunID != "ss-cov-run" {
			t.Fatalf("scoped 结果不属于本 run: %+v", v)
		}
	}
}
