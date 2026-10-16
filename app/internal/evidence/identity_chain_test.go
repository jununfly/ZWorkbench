package evidence

import (
	"errors"
	"testing"
)

// newChainOwner 打开一个内存 owner。注意 Open(":memory:") 走 cache=shared，
// 同进程内所有 owner 共用一份库，因此每个用例必须用全局唯一的 id 前缀。
func newChainOwner(t *testing.T) *Owner {
	t.Helper()
	ow, err := Open(":memory:")
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { _ = ow.Close() })
	return ow
}

// TestIdentityChain_FullLink 验证完整链路 run → effect → attempt → approval。
func TestIdentityChain_FullLink(t *testing.T) {
	ow := newChainOwner(t)
	runID := "ic-full-run"
	if _, err := ow.CreateRun(runID, "coding", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	op := "ic-full-op"
	appr, err := ow.RequestApproval(runID, op, "write", "/tmp/ic-full.txt", "ic-full-key", "需要审批")
	if err != nil {
		t.Fatalf("RequestApproval: %v", err)
	}
	tok, err := ow.Approve(appr.ApprovalID, 300)
	if err != nil {
		t.Fatalf("Approve: %v", err)
	}
	claim, err := ow.ClaimEffect(runID, op, "write", "/tmp/ic-full.txt", "ic-full-key", "approval-required", tok.Token, 3, nil)
	if err != nil {
		t.Fatalf("ClaimEffect: %v", err)
	}
	if !claim.Executable() {
		t.Fatalf("claim 应可执行，实际 %s/%s", claim.Status, claim.Reason)
	}
	if _, err := ow.CompleteEffect(claim.EffectID, map[string]any{"bytes": 12}, nil); err != nil {
		t.Fatalf("CompleteEffect: %v", err)
	}

	chain, err := ow.GetIdentityChain(runID)
	if err != nil {
		t.Fatalf("GetIdentityChain: %v", err)
	}
	if chain.RunID != runID || chain.Run == nil {
		t.Fatalf("链缺少 run 投影: %+v", chain)
	}
	if chain.Entry.Kind != EntryRunID || chain.Entry.ID != runID {
		t.Fatalf("entry 不符: %+v", chain.Entry)
	}
	if len(chain.Effects) != 1 {
		t.Fatalf("effects 应为 1 条, 实际 %d", len(chain.Effects))
	}
	node := chain.Effects[0]
	if node.ApprovalLink != ApprovalLinked {
		t.Fatalf("approval_link 应为 linked, 实际 %s", node.ApprovalLink)
	}
	if node.Approval == nil || node.Approval.ApprovalID != appr.ApprovalID {
		t.Fatalf("approval 未挂到 effect 上: %+v", node.Approval)
	}
	if len(node.Attempts) != 1 {
		t.Fatalf("attempts 应为 1 条, 实际 %d", len(node.Attempts))
	}
	if node.Attempts[0].Status != "completed" {
		t.Fatalf("attempt 状态应为 completed, 实际 %s", node.Attempts[0].Status)
	}
	if node.Attempts[0].EffectID != node.EffectID {
		t.Fatalf("attempt 未回指 effect: %+v", node.Attempts[0])
	}
	if chain.Counts.Effects != 1 || chain.Counts.Attempts != 1 || chain.Counts.PhysicalEffects != 1 {
		t.Fatalf("counts 不符: %+v", chain.Counts)
	}
	if len(chain.Approvals) != 1 || chain.Approvals[0].Status != "consumed" {
		t.Fatalf("run 级 approvals 不符: %+v", chain.Approvals)
	}
	// approval 被消费后链上不得出现 token_hash 之类字段（Approval 结构体本身也不带）。
	if chain.Approvals[0].ApprovalID != appr.ApprovalID {
		t.Fatalf("approval_id 不符: %s", chain.Approvals[0].ApprovalID)
	}
}

// TestIdentityChain_UnlinkedAndDangling 验证 effect→approval 的另两种状态。
func TestIdentityChain_UnlinkedAndDangling(t *testing.T) {
	ow := newChainOwner(t)
	runID := "ic-dangling-run"
	if _, err := ow.CreateRun(runID, "coding", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	// 免审批类：approval_id 为 NULL → unlinked
	claim, err := ow.ClaimEffect(runID, "ic-dangling-op-ro", "read", "/tmp/ic-ro.txt", "ic-ro-key", "read-only", "", 1, nil)
	if err != nil {
		t.Fatalf("ClaimEffect(read-only): %v", err)
	}
	// 断链：手工插一条 approval_id 指向不存在审批的 effect
	if _, err := ow.DB().Exec(
		`INSERT INTO effects(effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, status, attempt, max_attempts, physical_effect_count, approval_id, created_at, updated_at)
		 VALUES (?, ?, ?, ?, 'approval-required', 'write', '/tmp/ic-dangling.txt', 'claimed', 1, 1, 0, ?, ?, ?)`,
		"ic-dangling-effect", runID, "ic-dangling-op", "ic-dangling-key", "no-such-approval", nowUTC(), nowUTC()); err != nil {
		t.Fatalf("插入断链 effect: %v", err)
	}

	chain, err := ow.GetIdentityChain(runID)
	if err != nil {
		t.Fatalf("GetIdentityChain: %v", err)
	}
	if len(chain.Effects) != 2 {
		t.Fatalf("effects 应为 2 条, 实际 %d", len(chain.Effects))
	}
	byID := map[string]EffectNode{}
	for _, n := range chain.Effects {
		byID[n.EffectID] = n
	}
	if got := byID[claim.EffectID].ApprovalLink; got != ApprovalUnlinked {
		t.Fatalf("免审批 effect 应为 unlinked, 实际 %s", got)
	}
	if got := byID["ic-dangling-effect"].ApprovalLink; got != ApprovalDangling {
		t.Fatalf("孤儿 approval 引用应为 dangling, 实际 %s", got)
	}
	if byID["ic-dangling-effect"].Approval != nil {
		t.Fatalf("dangling 不得凭空造出 approval: %+v", byID["ic-dangling-effect"].Approval)
	}
	if chain.Counts.DanglingLinks != 1 {
		t.Fatalf("DanglingLinks 应为 1, 实际 %d", chain.Counts.DanglingLinks)
	}
}

// TestIdentityChain_UnknownIdentityFailsClosed 验证未知 id / 非法入口一律报错，不返空链。
func TestIdentityChain_UnknownIdentityFailsClosed(t *testing.T) {
	ow := newChainOwner(t)
	if _, err := ow.ResolveIdentityChain(EntryRunID, "ic-no-such-run"); !errors.Is(err, ErrRunNotFound) && !errors.Is(err, ErrNotFound) {
		t.Fatalf("未知 run 应拒 ErrNotFound, 实际: %v", err)
	}
	if _, err := ow.ResolveIdentityChain(EntryEffectID, "ic-no-such-effect"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("未知 effect 应拒 ErrNotFound, 实际: %v", err)
	}
	if _, err := ow.ResolveIdentityChain(EntryApprovalID, "ic-no-such-approval"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("未知 approval 应拒 ErrNotFound, 实际: %v", err)
	}
	if _, err := ow.ResolveIdentityChain(EntryOperationID, "ic-no-such-op"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("未知 operation 应拒 ErrNotFound, 实际: %v", err)
	}
	if _, err := ow.ResolveIdentityChain("whatever", "x"); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("未知 kind 应拒 ErrBadArgument, 实际: %v", err)
	}
	if _, err := ow.ResolveIdentityChain(EntryRunID, ""); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("空 id 应拒 ErrBadArgument, 实际: %v", err)
	}
	if _, err := ow.ListEffectAttempts("ic-no-such-effect"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("未知 effect 的 attempts 应拒 ErrNotFound, 实际: %v", err)
	}
}

// TestIdentityChain_ResolveFromEffectAndApproval 验证从链中段反向解析到整条链。
func TestIdentityChain_ResolveFromEffectAndApproval(t *testing.T) {
	ow := newChainOwner(t)
	runID := "ic-reverse-run"
	if _, err := ow.CreateRun(runID, "coding", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	// 一个只申请、从没被 effect 认领的审批：链上必须仍看得见。
	appr, err := ow.RequestApproval(runID, "ic-reverse-op", "write", "/tmp/ic-rev.txt", "ic-rev-key", "待审批")
	if err != nil {
		t.Fatalf("RequestApproval: %v", err)
	}
	claim, err := ow.ClaimEffect(runID, "ic-reverse-op2", "read", "/tmp/ic-rev2.txt", "ic-rev-key2", "read-only", "", 1, nil)
	if err != nil {
		t.Fatalf("ClaimEffect: %v", err)
	}

	byEffect, err := ow.ResolveIdentityChain(EntryEffectID, claim.EffectID)
	if err != nil {
		t.Fatalf("ResolveIdentityChain(effect_id): %v", err)
	}
	if byEffect.RunID != runID || byEffect.Entry.Kind != EntryEffectID {
		t.Fatalf("从 effect 反解失败: run=%s entry=%+v", byEffect.RunID, byEffect.Entry)
	}
	byApproval, err := ow.ResolveIdentityChain(EntryApprovalID, appr.ApprovalID)
	if err != nil {
		t.Fatalf("ResolveIdentityChain(approval_id): %v", err)
	}
	if byApproval.RunID != runID || byApproval.Entry.Kind != EntryApprovalID {
		t.Fatalf("从 approval 反解失败: run=%s entry=%+v", byApproval.RunID, byApproval.Entry)
	}
	if len(byApproval.Approvals) != 1 || byApproval.Approvals[0].Status != "pending" {
		t.Fatalf("未被认领的审批必须出现在链上: %+v", byApproval.Approvals)
	}
	if byApproval.Counts.Approvals != 1 {
		t.Fatalf("approvals 计数不符: %+v", byApproval.Counts)
	}
	// 同一 operation 只命中 approval（尚无 effect）时也要能解析。
	byOp, err := ow.ResolveIdentityChain(EntryOperationID, "ic-reverse-op")
	if err != nil {
		t.Fatalf("ResolveIdentityChain(operation_id): %v", err)
	}
	if byOp.RunID != runID {
		t.Fatalf("operation 解析到错误 run: %s", byOp.RunID)
	}
}

// TestIdentityChain_OperationCrossRunAmbiguous 验证 operation_id 跨 run 冲突时拒绝猜测。
func TestIdentityChain_OperationCrossRunAmbiguous(t *testing.T) {
	ow := newChainOwner(t)
	runA, runB := "ic-amb-run-a", "ic-amb-run-b"
	for _, r := range []string{runA, runB} {
		if _, err := ow.CreateRun(r, "coding", nil, nil); err != nil {
			t.Fatalf("CreateRun(%s): %v", r, err)
		}
	}
	op := "ic-amb-op"
	if _, err := ow.RequestApproval(runA, op, "write", "/tmp/ic-amb.txt", "ic-amb-key", "A 的审批"); err != nil {
		t.Fatalf("RequestApproval: %v", err)
	}
	if _, err := ow.ClaimEffect(runB, op, "read", "/tmp/ic-amb.txt", "ic-amb-key2", "read-only", "", 1, nil); err != nil {
		t.Fatalf("ClaimEffect: %v", err)
	}
	if _, err := ow.ResolveIdentityChain(EntryOperationID, op); !errors.Is(err, ErrAmbiguousIdentity) {
		t.Fatalf("跨 run 的 operation 应拒 ErrAmbiguousIdentity, 实际: %v", err)
	}
}

// TestListEffectAttempts_Ordered 验证一次 effect 的多次尝试按序数可查（含 bounded retry）。
func TestListEffectAttempts_Ordered(t *testing.T) {
	ow := newChainOwner(t)
	runID := "ic-attempts-run"
	if _, err := ow.CreateRun(runID, "coding", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	claim, err := ow.ClaimEffect(runID, "ic-attempts-op", "write", "/tmp/ic-at.txt", "ic-at-key", "idempotent", "", 3, nil)
	if err != nil {
		t.Fatalf("ClaimEffect: %v", err)
	}
	if _, err := ow.MarkEffectUncertain(claim.EffectID, map[string]any{"why": "caller crashed"}); err != nil {
		t.Fatalf("MarkEffectUncertain: %v", err)
	}
	if _, err := ow.ReconcileEffect(claim.EffectID, "not-applied", map[string]any{"observed": true}); err != nil {
		t.Fatalf("ReconcileEffect: %v", err)
	}
	second, err := ow.ClaimEffect(runID, "ic-attempts-op", "write", "/tmp/ic-at.txt", "ic-at-key", "idempotent", "", 3, nil)
	if err != nil {
		t.Fatalf("ClaimEffect(retry): %v", err)
	}
	if second.Attempt != 2 {
		t.Fatalf("第二次尝试序数应为 2, 实际 %d", second.Attempt)
	}

	attempts, err := ow.ListEffectAttempts(claim.EffectID)
	if err != nil {
		t.Fatalf("ListEffectAttempts: %v", err)
	}
	if len(attempts) != 2 {
		t.Fatalf("attempts 应为 2 条, 实际 %d", len(attempts))
	}
	if attempts[0].Attempt != 1 || attempts[1].Attempt != 2 {
		t.Fatalf("attempts 未按序数升序: %+v", attempts)
	}
	if attempts[0].Status != "reconciled_not_applied" {
		t.Fatalf("attempt 1 状态应为 reconciled_not_applied, 实际 %s", attempts[0].Status)
	}
	if attempts[0].Error == nil {
		t.Fatalf("attempt 1 应带 error 投影")
	}
	if attempts[1].Status != "claimed" {
		t.Fatalf("attempt 2 状态应为 claimed, 实际 %s", attempts[1].Status)
	}

	chain, err := ow.GetIdentityChain(runID)
	if err != nil {
		t.Fatalf("GetIdentityChain: %v", err)
	}
	if chain.Counts.Attempts != 2 {
		t.Fatalf("链上 attempts 计数应为 2, 实际 %d", chain.Counts.Attempts)
	}
}
