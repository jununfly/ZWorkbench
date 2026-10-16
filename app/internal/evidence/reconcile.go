package evidence

import (
	"database/sql"
	"fmt"
)

// ---- 1-4-1：reconcile / uncertain 恢复路径（composition.py mark_effect_uncertain + reconcile_effect 移植） ----
//
// 背景：物理副作用尝试的外部结果为「未知」（例如 caller 进程在 complete 前崩溃）
// 时，C28 要求 owner 显式记录不确定、绝不隐式重试，并把 run 推入 recovering，
// 随后由外部观测真实结果后调用 ReconcileEffect 收口。这是「unknown → safe-stop」
// 失败关闭语义（ps-safe-stop-unknown）在 effect 维度的落地。

// MarkEffectUncertain 记录一次物理尝试的外部结果为未知，绝不隐式重试。
// 仅允许从 claimed 进入 uncertain（fail-closed，其余状态 ErrInvalidTransition）；
// 已是 uncertain 则幂等返回；effect_attempts 对应 attempt 同步置 uncertain；
// run 推入 recovering。
func (o *Owner) MarkEffectUncertain(effectID string, errVal any) (*Effect, error) {
	if errVal == nil {
		errVal = map[string]any{}
	}
	now := nowUTC()
	var out Effect
	err := o.transact(func(tx *sql.Tx) error {
		e, eerr := o.effectRow(tx, effectID)
		if eerr != nil {
			return eerr
		}
		if e.Status == "uncertain" { // 幂等
			out = e
			return nil
		}
		if e.Status != "claimed" {
			return fmt.Errorf("%w: effect %s 不能从 %s 标记为 uncertain", ErrInvalidTransition, effectID, e.Status)
		}
		ej, _ := jsonString(errVal)
		if _, err := tx.Exec(
			`UPDATE effects SET status='uncertain', last_error_json=?, updated_at=? WHERE effect_id=?`,
			ej, now, effectID); err != nil {
			return fmt.Errorf("标记 effect uncertain 失败：%w", err)
		}
		if _, err := tx.Exec(
			`UPDATE effect_attempts SET status='uncertain', finished_at=?, error_json=? WHERE effect_id=? AND attempt=?`,
			now, ej, effectID, e.Attempt); err != nil {
			return fmt.Errorf("标记 effect_attempts uncertain 失败：%w", err)
		}
		// run 推入 recovering（running→recovering 合法；已是 recovering 则为 no-op）
		if eerr := o.setRunStatus(tx, e.RunID, StatusRunning, StatusRecovering, "run.recovering", map[string]any{"effect_id": effectID}); eerr != nil {
			return eerr
		}
		if eerr := o.appendEventTx(tx, e.RunID, "effect.uncertain", nil, map[string]any{"effect_id": effectID, "attempt": e.Attempt}); eerr != nil {
			return eerr
		}
		out, _ = o.effectRow(tx, effectID)
		return nil
	})
	return &out, err
}

// ReconcileEffect 把 uncertain/retryable 的 effect 以 observed_outcome 收口：
//   applied     → completed（计一次物理 effect，即使原 caller 已崩）+ 记录外部回执
//   not-applied → retryable（唯一允许 owner 有界重试的出向）
//   unknown     → unknown 终态，run safe-stopped（永不推断成功、永不自动 retry）
//
// 与 composition.py reconcile_effect 一一对应：completed 幂等返回；
// 非 uncertain/retryable 状态 fail-closed 拒绝（ErrInvalidTransition）。
// B2-narrow 不含 results 表（见 owner.go CompleteRun 注释），reconcile 的对外证据
// 随 effect.reconciled 事件与 external_receipt_json 落盘，不另建 results 表。
func (o *Owner) ReconcileEffect(effectID, observedOutcome string, evidence any) (*Effect, error) {
	if evidence == nil {
		evidence = map[string]any{}
	}
	if observedOutcome != "applied" && observedOutcome != "not-applied" && observedOutcome != "unknown" {
		return nil, fmt.Errorf("%w: observed_outcome 必须是 applied/not-applied/unknown", ErrBadArgument)
	}
	now := nowUTC()
	var out Effect
	err := o.transact(func(tx *sql.Tx) error {
		e, eerr := o.effectRow(tx, effectID)
		if eerr != nil {
			return eerr
		}
		if e.Status == "completed" { // 幂等
			out = e
			return nil
		}
		if e.Status != "uncertain" && e.Status != "retryable" {
			return fmt.Errorf("%w: effect %s 不能从 %s 收口", ErrInvalidTransition, effectID, e.Status)
		}
		ej, _ := jsonString(evidence)
		var newStatus string
		var physicalCount int
		var attemptStatus string
		switch observedOutcome {
		case "applied":
			newStatus = "completed"
			physicalCount = 1
			attemptStatus = "reconciled_applied"
		case "not-applied":
			newStatus = "retryable"
			physicalCount = e.PhysicalEffectCount
			attemptStatus = "reconciled_not_applied"
		default: // unknown
			newStatus = "unknown"
			physicalCount = e.PhysicalEffectCount
			attemptStatus = "reconciled_unknown"
		}
		if observedOutcome == "applied" {
			if _, err := tx.Exec(
				`UPDATE effects SET status=?, physical_effect_count=?, last_error_json=?, external_receipt_json=?, updated_at=? WHERE effect_id=?`,
				newStatus, physicalCount, ej, ej, now, effectID); err != nil {
				return fmt.Errorf("收口 effect 失败：%w", err)
			}
		} else {
			if _, err := tx.Exec(
				`UPDATE effects SET status=?, physical_effect_count=?, last_error_json=?, updated_at=? WHERE effect_id=?`,
				newStatus, physicalCount, ej, now, effectID); err != nil {
				return fmt.Errorf("收口 effect 失败：%w", err)
			}
		}
		if _, err := tx.Exec(
			`UPDATE effect_attempts SET status=?, finished_at=?, error_json=? WHERE effect_id=? AND attempt=?`,
			attemptStatus, now, ej, effectID, e.Attempt); err != nil {
			return fmt.Errorf("收口 effect_attempts 失败：%w", err)
		}
		// run 状态收口（沿用 Python：unknown → safe_stopped；其余 → running，但已 safe_stopped 不回退）
		r, eerr := o.runRow(tx, e.RunID)
		if eerr != nil {
			return eerr
		}
		switch observedOutcome {
		case "unknown":
			if eerr := o.setRunStatus(tx, e.RunID, r.Status, StatusSafeStopped, "run.safe_stopped", map[string]any{"reason": "effect_outcome_unknown", "effect_id": effectID}); eerr != nil {
				return eerr
			}
		default:
			if r.Status != StatusSafeStopped {
				if eerr := o.setRunStatus(tx, e.RunID, r.Status, StatusRunning, "run.reconciled", map[string]any{"effect_id": effectID, "outcome": observedOutcome}); eerr != nil {
					return eerr
				}
			}
		}
		if eerr := o.appendEventTx(tx, e.RunID, "effect.reconciled", nil, map[string]any{
			"effect_id": effectID, "outcome": observedOutcome,
			"physical_effect_count": physicalCount, "evidence": evidence,
		}); eerr != nil {
			return eerr
		}
		out, _ = o.effectRow(tx, effectID)
		return nil
	})
	return &out, err
}

// ErrBadArgument 在 observed_outcome 非法时承载（保持哨兵一致）。
