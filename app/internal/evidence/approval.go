package evidence

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"time"
)

// ---- C28：一次性审批 token + fail-closed effect-claim 归属（composition.py 忠实移植） ----

// ALLOWED_EFFECT_CLASSES 是三种合法副作用类别（与 Python 一致）。
// read-only / idempotent 免审批；approval-required 必须绑精确的一次性 token。
var ALLOWED_EFFECT_CLASSES = map[string]bool{
	"read-only":          true,
	"idempotent":         true,
	"approval-required":  true,
}

// 哨兵错误（与 C26 的 ErrInvalidTransition 区分开）。
var (
	ErrApproval = errors.New("approval error")
	ErrNotFound = errors.New("not found")
)

// EffectClaim 是 owner 对「该 effect 是否可以执行」的决定（与 Python EffectClaim 对应）。
// Status 取值：claimed / denied / already_completed / in_flight / recovery_required /
// safe_stopped。Executable 仅当 status=="claimed"。
type EffectClaim struct {
	EffectID             string `json:"effect_id"`
	Status               string `json:"status"`
	Attempt              int    `json:"attempt"`
	PhysicalEffectCount  int    `json:"physical_effect_count"`
	Reason               string `json:"reason"`
}

// Executable 表示该调用方可以执行恰好一次物理尝试。
func (c *EffectClaim) Executable() bool { return c.Status == "claimed" }

// Approval 是审批请求记录（status: pending / approved / denied / consumed）。
type Approval struct {
	ApprovalID     string `json:"approval_id"`
	RunID          string `json:"run_id"`
	OperationID    string `json:"operation_id"`
	Action         string `json:"action"`
	Resource       string `json:"resource"`
	IdempotencyKey string `json:"idempotency_key"`
	Reason         string `json:"reason"`
	Status         string `json:"status"`
	CreatedAt      string `json:"created_at"`
	DecisionReason string `json:"decision_reason,omitempty"`
}

// ApprovalToken 是 Approve 返回的「一次性 bearer token」快照（token 明文只在此刻出现一次）。
type ApprovalToken struct {
	ApprovalID  string `json:"approval_id"`
	OperationID string `json:"operation_id"`
	Token       string `json:"token"`
	ExpiresAt   string `json:"expires_at"`
}

// approvalRow 是 approvals 表的内部投影（含 token_hash / consumed_at 等哈希与消费标记）。
// token_hash / expires_at / decided_at / decision_reason / consumed_at 在 pending 时为 NULL，用 NullString。
type approvalRow struct {
	ApprovalID     string
	RunID          string
	OperationID    string
	Action         string
	Resource       string
	IdempotencyKey string
	Reason         string
	Status         string
	TokenHash      sql.NullString
	ExpiresAt      sql.NullString
	CreatedAt      string
	DecidedAt      sql.NullString
	DecisionReason sql.NullString
	ConsumedAt     sql.NullString
}

// ---- RequestApproval：创建待审批请求（幂等：同 operation 属同 run 且 scope 一致则返现有） ----

func (o *Owner) RequestApproval(runID, operationID, action, resource, idempotencyKey, reason string) (*Approval, error) {
	type field struct{ v, name string }
	for _, f := range []field{
		{operationID, "operation_id"}, {action, "action"}, {resource, "resource"},
		{idempotencyKey, "idempotency_key"}, {reason, "reason"},
	} {
		if err := requireText(f.v, f.name); err != nil {
			return nil, err
		}
	}
	now := nowUTC()
	var out *Approval
	err := o.transact(func(tx *sql.Tx) error {
		if _, err := o.runRow(tx, runID); err != nil { // 确保 run 存在
			return err
		}
		existing, eerr := o.approvalRowByOperation(tx, operationID)
		if eerr == nil {
			if existing.RunID != runID {
				return fmt.Errorf("%w: approval operation belongs to another run", ErrApproval)
			}
			if !approvalScopeMatches(existing, action, resource, idempotencyKey) {
				return fmt.Errorf("%w: approval operation scope conflict", ErrApproval)
			}
			out = existing.toApproval()
			return nil
		}
		if !errors.Is(eerr, ErrNotFound) {
			return eerr
		}
		approvalID := newID()
		if _, err := tx.Exec(
			`INSERT INTO approvals(approval_id, run_id, operation_id, action, resource, idempotency_key, reason, status, created_at)
			 VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)`,
			approvalID, runID, operationID, action, resource, idempotencyKey, reason, now); err != nil {
			if isUniqueViolation(err) {
				return fmt.Errorf("%w: approval conflicts with an existing operation or idempotency key", ErrApproval)
			}
			return fmt.Errorf("创建 approval 失败：%w", err)
		}
		if err := o.appendEventTx(tx, runID, "approval.requested", map[string]any{
			"approval_id": approvalID, "operation_id": operationID, "action": action,
			"resource": resource, "idempotency_key": idempotencyKey,
		}, nil); err != nil {
			return err
		}
		out = &Approval{
			ApprovalID: approvalID, RunID: runID, OperationID: operationID, Action: action,
			Resource: resource, IdempotencyKey: idempotencyKey, Reason: reason,
			Status: "pending", CreatedAt: now,
		}
		return nil
	})
	return out, err
}

// ---- Approve：批准一个精确操作，返回一次性 bearer token（明文仅此一次） ----

func (o *Owner) Approve(approvalID string, ttlSeconds int) (*ApprovalToken, error) {
	if ttlSeconds <= 0 {
		return nil, fmt.Errorf("%w: ttl_seconds must be positive", ErrApproval)
	}
	token := generateToken()
	tokenHash := sha256Hex(token)
	now := nowUTC()
	expiresAt := time.Now().UTC().Add(time.Duration(ttlSeconds) * time.Second).Format(time.RFC3339)
	var out *ApprovalToken
	err := o.transact(func(tx *sql.Tx) error {
		row, eerr := o.approvalRow(tx, approvalID)
		if eerr != nil {
			return eerr
		}
		if row.Status != "pending" {
			return fmt.Errorf("%w: approval is not pending: %s", ErrApproval, row.Status)
		}
		if _, err := tx.Exec(
			`UPDATE approvals SET status='approved', token_hash=?, expires_at=?, decided_at=? WHERE approval_id=?`,
			tokenHash, expiresAt, now, approvalID); err != nil {
			return fmt.Errorf("批准 approval 失败：%w", err)
		}
		if err := o.appendEventTx(tx, row.RunID, "approval.approved", map[string]any{
			"approval_id": approvalID, "operation_id": row.OperationID, "expires_at": expiresAt,
		}, nil); err != nil {
			return err
		}
		out = &ApprovalToken{ApprovalID: approvalID, OperationID: row.OperationID, Token: token, ExpiresAt: expiresAt}
		return nil
	})
	return out, err
}

// ---- DenyApproval：拒绝待审批；denied 永远不可再批准 ----

func (o *Owner) DenyApproval(approvalID, reason string) (*Approval, error) {
	if err := requireText(reason, "reason"); err != nil {
		return nil, err
	}
	now := nowUTC()
	var out *Approval
	err := o.transact(func(tx *sql.Tx) error {
		row, eerr := o.approvalRow(tx, approvalID)
		if eerr != nil {
			return eerr
		}
		if row.Status != "pending" {
			return fmt.Errorf("%w: approval is not pending: %s", ErrApproval, row.Status)
		}
		if _, err := tx.Exec(
			`UPDATE approvals SET status='denied', decided_at=?, decision_reason=? WHERE approval_id=?`,
			now, reason, approvalID); err != nil {
			return fmt.Errorf("拒绝 approval 失败：%w", err)
		}
		if err := o.appendEventTx(tx, row.RunID, "approval.denied", map[string]any{
			"approval_id": approvalID, "operation_id": row.OperationID, "reason": reason,
		}, nil); err != nil {
			return err
		}
		// row 是 UPDATE 之前读的快照，状态仍是 pending；返回前必须反映实际结果，
		// 否则调用方（API/UI）会拿到「已拒绝但 status=pending」的自相矛盾响应。
		out = row.toApproval()
		out.Status = "denied"
		out.DecisionReason = reason
		return nil
	})
	return out, err
}

// ---- ClaimEffect：C28 核心，fail-closed 归属逻辑（十几个 safe_stopped 转义逐字移植） ----

func (o *Owner) ClaimEffect(
	runID, operationID, action, resource, idempotencyKey, effectClass string,
	approvalToken string, maxAttempts int, requiredExposure []string,
) (*EffectClaim, error) {
	if err := validateEffectInputs(operationID, action, resource, idempotencyKey, effectClass, maxAttempts); err != nil {
		return nil, err
	}
	now := nowUTC()
	var claim *EffectClaim
	err := o.transact(func(tx *sql.Tx) error {
		r, err := o.runRow(tx, runID)
		if err != nil {
			return err
		}
		// 终态 run：直接 denied，绝不执行
		if r.Status == StatusCompleted || r.Status == StatusFailed || r.Status == StatusSafeStopped {
			claim = &EffectClaim{Status: "denied", Reason: "run_terminal:" + string(r.Status)}
			return nil
		}
		// 既有 effect 查重（operation_id 或 idempotency_key）
		existing, eerr := o.effectRowByOpOrKey(tx, operationID, idempotencyKey)
		if eerr == nil {
			if existing.RunID != runID {
				if e := o.failStop(tx, runID, r.Status, "effect_belongs_to_other_run", map[string]any{"operation_id": operationID, "existing_effect_id": existing.EffectID}); e != nil {
					return e
				}
				claim = &EffectClaim{EffectID: existing.EffectID, Status: "denied", Attempt: existing.Attempt, PhysicalEffectCount: existing.PhysicalEffectCount, Reason: "effect_belongs_to_other_run"}
				return nil
			}
			if !effectScopeMatches(existing, operationID, action, resource, idempotencyKey, effectClass) {
				if e := o.failStop(tx, runID, r.Status, "effect_scope_mismatch", map[string]any{"operation_id": operationID, "existing_effect_id": existing.EffectID}); e != nil {
					return e
				}
				claim = &EffectClaim{EffectID: existing.EffectID, Status: "denied", Attempt: existing.Attempt, PhysicalEffectCount: existing.PhysicalEffectCount, Reason: "effect_scope_mismatch"}
				return nil
			}
			switch existing.Status {
			case "completed":
				claim = &EffectClaim{EffectID: existing.EffectID, Status: "already_completed", Attempt: existing.Attempt, PhysicalEffectCount: existing.PhysicalEffectCount, Reason: "idempotent_replay"}
				return nil
			case "claimed":
				claim = &EffectClaim{EffectID: existing.EffectID, Status: "in_flight", Attempt: existing.Attempt, PhysicalEffectCount: existing.PhysicalEffectCount, Reason: "attempt_already_claimed"}
				return nil
			case "uncertain", "unknown":
				claim = &EffectClaim{EffectID: existing.EffectID, Status: "recovery_required", Attempt: existing.Attempt, PhysicalEffectCount: existing.PhysicalEffectCount, Reason: "effect_" + existing.Status}
				return nil
			case "retryable":
				if existing.Attempt >= existing.MaxAttempts {
					if e := o.failStop(tx, runID, r.Status, "retry_budget_exhausted", map[string]any{"operation_id": operationID}); e != nil {
						return e
					}
					claim = &EffectClaim{EffectID: existing.EffectID, Status: "safe_stopped", Attempt: existing.Attempt, PhysicalEffectCount: existing.PhysicalEffectCount, Reason: "retry_budget_exhausted"}
					return nil
				}
				nextAttempt := existing.Attempt + 1
				if _, err := tx.Exec(`UPDATE effects SET status='claimed', attempt=?, updated_at=? WHERE effect_id=?`, nextAttempt, now, existing.EffectID); err != nil {
					return fmt.Errorf("更新 effect 重试失败：%w", err)
				}
				if _, err := tx.Exec(`INSERT INTO effect_attempts(effect_id, attempt, status, started_at) VALUES (?, ?, 'claimed', ?)`, existing.EffectID, nextAttempt, now); err != nil {
					return fmt.Errorf("写 effect_attempts 失败：%w", err)
				}
				if e := o.setRunStatus(tx, runID, r.Status, StatusRunning, "run.resumed", nil); e != nil {
					return e
				}
				if err := o.appendEventTx(tx, runID, "effect.claimed", map[string]any{"effect_id": existing.EffectID, "attempt": nextAttempt, "retry": true}, nil); err != nil {
					return err
				}
				claim = &EffectClaim{EffectID: existing.EffectID, Status: "claimed", Attempt: nextAttempt, PhysicalEffectCount: existing.PhysicalEffectCount, Reason: "bounded_retry"}
				return nil
			}
		} else if !errors.Is(eerr, ErrNotFound) {
			return eerr
		}

		// 声明曝光面 preflight 检查（opt-in：仅当有 declared_exposure 时生效）
		declared, derr := o.declaredExposureRow(tx, runID)
		if derr != nil {
			return derr
		}
		if declared != nil {
			declaredClasses := toStringSlice(declared.DeclaredSideEffects)
			if !contains(declaredClasses, effectClass) {
				if e := o.failStop(tx, runID, r.Status, "side_effect_not_declared", map[string]any{"operation_id": operationID, "effect_class": effectClass}); e != nil {
					return e
				}
				claim = &EffectClaim{Status: "denied", Reason: "side_effect_not_declared"}
				return nil
			}
			exposure := toMap(declared.Exposure)
			workspaceRoot := strOrEmpty(exposure["workspace_root"])
			if workspaceRoot != "" {
				if !filepath.IsAbs(resource) {
					if e := o.failStop(tx, runID, r.Status, "workspace_out_of_bounds", map[string]any{"operation_id": operationID, "resource": resource, "workspace_root": workspaceRoot, "detail": "relative resource is ambiguous under a declared workspace boundary"}); e != nil {
						return e
					}
					claim = &EffectClaim{Status: "denied", Reason: "workspace_out_of_bounds"}
					return nil
				}
				resolvedResource := absPath(resource)
				resolvedRoot := absPath(workspaceRoot)
				if resolvedResource != resolvedRoot && !isWithin(resolvedResource, resolvedRoot) {
					if e := o.failStop(tx, runID, r.Status, "workspace_out_of_bounds", map[string]any{"operation_id": operationID, "resource": resource, "workspace_root": workspaceRoot}); e != nil {
						return e
					}
					claim = &EffectClaim{Status: "denied", Reason: "workspace_out_of_bounds"}
					return nil
				}
			}
			for _, capability := range []string{"network", "credentials", "subprocess"} {
				if contains(requiredExposure, capability) && !truthy(exposure[capability]) {
					if e := o.failStop(tx, runID, r.Status, "exposure_not_declared", map[string]any{"operation_id": operationID, "capability": capability}); e != nil {
						return e
					}
					claim = &EffectClaim{Status: "denied", Reason: "exposure_not_declared"}
					return nil
				}
			}
		}

		// 未知 effect_class：fail-closed
		if !ALLOWED_EFFECT_CLASSES[effectClass] {
			if e := o.failStop(tx, runID, r.Status, "unknown_effect_class", map[string]any{"operation_id": operationID}); e != nil {
				return e
			}
			claim = &EffectClaim{Status: "denied", Reason: "unknown_effect_class"}
			return nil
		}

		// approval-required：必须精确、未消费、未过期的一次性 token
		var approval *approvalRow
		if effectClass == "approval-required" {
			arow, aerr := o.approvalRowByOperation(tx, operationID)
			if aerr != nil || arow.Status != "approved" {
				if e := o.setRunStatus(tx, runID, r.Status, StatusWaitingApproval, "run.waiting_approval", nil); e != nil {
					return e
				}
				if err := o.appendEventTx(tx, runID, "effect.claim.denied", map[string]any{"operation_id": operationID, "reason": "approval_missing_or_not_approved"}, nil); err != nil {
					return err
				}
				claim = &EffectClaim{Status: "denied", Reason: "approval_missing_or_not_approved"}
				return nil
			}
			if !approvalScopeMatches(arow, action, resource, idempotencyKey) {
				if e := o.failStop(tx, runID, r.Status, "approval_scope_mismatch", map[string]any{"operation_id": operationID}); e != nil {
					return e
				}
				claim = &EffectClaim{Status: "denied", Reason: "approval_scope_mismatch"}
				return nil
			}
			if approvalToken == "" {
				if e := o.setRunStatus(tx, runID, r.Status, StatusWaitingApproval, "run.waiting_approval", nil); e != nil {
					return e
				}
				if err := o.appendEventTx(tx, runID, "effect.claim.denied", map[string]any{"operation_id": operationID, "reason": "approval_token_missing"}, nil); err != nil {
					return err
				}
				claim = &EffectClaim{Status: "denied", Reason: "approval_token_missing"}
				return nil
			}
			if arow.ConsumedAt.String != "" {
				if e := o.failStop(tx, runID, r.Status, "approval_token_replay", map[string]any{"operation_id": operationID}); e != nil {
					return e
				}
				claim = &EffectClaim{Status: "denied", Reason: "approval_token_replay"}
				return nil
			}
			if !constantTimeTokenMatch(arow.TokenHash.String, approvalToken) {
				if e := o.failStop(tx, runID, r.Status, "approval_token_mismatch", map[string]any{"operation_id": operationID}); e != nil {
					return e
				}
				claim = &EffectClaim{Status: "denied", Reason: "approval_token_mismatch"}
				return nil
			}
			if arow.ExpiresAt.String != "" && arow.ExpiresAt.String <= now {
				if e := o.failStop(tx, runID, r.Status, "approval_expired", map[string]any{"operation_id": operationID}); e != nil {
					return e
				}
				claim = &EffectClaim{Status: "denied", Reason: "approval_expired"}
				return nil
			}
			if _, err := tx.Exec(`UPDATE approvals SET consumed_at=?, status='consumed' WHERE approval_id=?`, now, arow.ApprovalID); err != nil {
				return fmt.Errorf("消费 approval token 失败：%w", err)
			}
			approval = arow
		}

		// 新 effect
		effectID := newID()
		if _, err := tx.Exec(
			`INSERT INTO effects(effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, status, attempt, max_attempts, physical_effect_count, approval_id, created_at, updated_at)
			 VALUES (?, ?, ?, ?, ?, ?, ?, 'claimed', 1, ?, 0, ?, ?, ?)`,
			effectID, runID, operationID, idempotencyKey, effectClass, action, resource, maxAttempts, approvalApprovalID(approval), now, now); err != nil {
			if isUniqueViolation(err) {
				// 并发 owner 赢得幂等竞赛：返回不可执行结果比尝试 effect 更安全
				if e := o.appendEventTx(tx, runID, "effect.claim.denied", map[string]any{"operation_id": operationID, "reason": "idempotency_race"}, nil); e != nil {
					return e
				}
				claim = &EffectClaim{Status: "in_flight", Reason: "idempotency_race"}
				return nil
			}
			return fmt.Errorf("创建 effect 失败：%w", err)
		}
		if _, err := tx.Exec(`INSERT INTO effect_attempts(effect_id, attempt, status, started_at) VALUES (?, 1, 'claimed', ?)`, effectID, now); err != nil {
			return fmt.Errorf("写 effect_attempts 失败：%w", err)
		}
		if e := o.setRunStatus(tx, runID, r.Status, StatusRunning, "run.started", nil); e != nil {
			return e
		}
		if err := o.appendEventTx(tx, runID, "effect.claimed", map[string]any{"effect_id": effectID, "operation_id": operationID, "attempt": 1, "effect_class": effectClass}, nil); err != nil {
			return err
		}
		claim = &EffectClaim{EffectID: effectID, Status: "claimed", Attempt: 1, Reason: "new_effect"}
		return nil
	})
	return claim, err
}

// failStop 是 claim_effect 里高频复用的「safe-stop + 记录 denied 事件」原子操作。
func (o *Owner) failStop(tx *sql.Tx, runID string, old RunStatus, reason string, extra map[string]any) error {
	if e := o.setRunStatus(tx, runID, old, StatusSafeStopped, "run.safe_stopped", map[string]any{"reason": reason}); e != nil {
		return e
	}
	return o.appendEventTx(tx, runID, "effect.claim.denied", extra, nil)
}

// ---- CompleteEffect：恰好一次提交一个物理 effect 及其结果（C28 exactly-once 保证） ----

func (o *Owner) CompleteEffect(effectID string, result any, externalReceipt map[string]any) (*Effect, error) {
	now := nowUTC()
	var out *Effect
	err := o.transact(func(tx *sql.Tx) error {
		e, eerr := o.effectRow(tx, effectID)
		if eerr != nil {
			return eerr
		}
		if e.Status == "completed" { // 幂等：已完成直接返
			out = &e
			return nil
		}
		if e.Status != "claimed" {
			return fmt.Errorf("%w: effect %s 不能从 %s 完成", ErrInvalidTransition, effectID, e.Status)
		}
		rj, _ := jsonString(result)
		erj, _ := jsonString(externalReceipt)
		if _, err := tx.Exec(
			`UPDATE effects SET status='completed', physical_effect_count=physical_effect_count+1, external_receipt_json=?, updated_at=? WHERE effect_id=?`,
			erj, now, effectID); err != nil {
			return fmt.Errorf("完成 effect 失败：%w", err)
		}
		if _, err := tx.Exec(
			`UPDATE effect_attempts SET finished_at=?, status='completed', result_json=? WHERE effect_id=? AND attempt=?`,
			now, rj, effectID, e.Attempt); err != nil {
			return fmt.Errorf("完成 effect_attempts 失败：%w", err)
		}
		if err := o.appendEventTx(tx, e.RunID, "effect.completed", map[string]any{"effect_id": effectID, "physical_effect_count": e.PhysicalEffectCount + 1}, nil); err != nil {
			return err
		}
		e.Status = "completed"
		e.PhysicalEffectCount = e.PhysicalEffectCount + 1
		out = &e
		return nil
	})
	return out, err
}

// ---- 内部读取与工具 ----

func (o *Owner) approvalRow(tx *sql.Tx, approvalID string) (*approvalRow, error) {
	row := tx.QueryRow(
		`SELECT approval_id, run_id, operation_id, action, resource, idempotency_key, reason, status, token_hash, expires_at, created_at, decided_at, decision_reason, consumed_at
		 FROM approvals WHERE approval_id=?`, approvalID)
	var r approvalRow
	if err := row.Scan(&r.ApprovalID, &r.RunID, &r.OperationID, &r.Action, &r.Resource, &r.IdempotencyKey, &r.Reason, &r.Status, &r.TokenHash, &r.ExpiresAt, &r.CreatedAt, &r.DecidedAt, &r.DecisionReason, &r.ConsumedAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, fmt.Errorf("%w: approval %s", ErrNotFound, approvalID)
		}
		return nil, fmt.Errorf("读取 approval 失败：%w", err)
	}
	return &r, nil
}

func (o *Owner) approvalRowByOperation(tx *sql.Tx, operationID string) (*approvalRow, error) {
	row := tx.QueryRow(
		`SELECT approval_id, run_id, operation_id, action, resource, idempotency_key, reason, status, token_hash, expires_at, created_at, decided_at, decision_reason, consumed_at
		 FROM approvals WHERE operation_id=?`, operationID)
	var r approvalRow
	if err := row.Scan(&r.ApprovalID, &r.RunID, &r.OperationID, &r.Action, &r.Resource, &r.IdempotencyKey, &r.Reason, &r.Status, &r.TokenHash, &r.ExpiresAt, &r.CreatedAt, &r.DecidedAt, &r.DecisionReason, &r.ConsumedAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, fmt.Errorf("查 approval by operation 失败：%w", err)
	}
	return &r, nil
}

func (o *Owner) effectRow(tx *sql.Tx, effectID string) (Effect, error) {
	row := tx.QueryRow(
		`SELECT effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, status, attempt, max_attempts, physical_effect_count, approval_id
		 FROM effects WHERE effect_id=?`, effectID)
	var e Effect
	var apprID sql.NullString
	if err := row.Scan(&e.EffectID, &e.RunID, &e.OperationID, &e.IdempotencyKey, &e.EffectClass, &e.Action, &e.Resource, &e.Status, &e.Attempt, &e.MaxAttempts, &e.PhysicalEffectCount, &apprID); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return e, fmt.Errorf("%w: effect %s", ErrNotFound, effectID)
		}
		return e, fmt.Errorf("读取 effect 失败：%w", err)
	}
	e.ApprovalID = apprID.String
	return e, nil
}

func (o *Owner) effectRowByOpOrKey(tx *sql.Tx, operationID, idempotencyKey string) (Effect, error) {
	row := tx.QueryRow(
		`SELECT effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, status, attempt, max_attempts, physical_effect_count, approval_id
		 FROM effects WHERE operation_id=? OR idempotency_key=? ORDER BY created_at LIMIT 1`, operationID, idempotencyKey)
	var e Effect
	var apprID sql.NullString
	if err := row.Scan(&e.EffectID, &e.RunID, &e.OperationID, &e.IdempotencyKey, &e.EffectClass, &e.Action, &e.Resource, &e.Status, &e.Attempt, &e.MaxAttempts, &e.PhysicalEffectCount, &apprID); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return e, ErrNotFound
		}
		return e, fmt.Errorf("查 effect 失败：%w", err)
	}
	e.ApprovalID = apprID.String
	return e, nil
}

func (o *Owner) declaredExposureRow(tx *sql.Tx, runID string) (*DeclaredExposure, error) {
	row := tx.QueryRow(`SELECT run_id, declared_side_effects_json, exposure_json, declared_at FROM declared_exposure WHERE run_id=?`, runID)
	var r DeclaredExposure
	var dj, ej string
	if err := row.Scan(&r.RunID, &dj, &ej, &r.DeclaredAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, nil
		}
		return nil, fmt.Errorf("读取 declared_exposure 失败：%w", err)
	}
	_ = json.Unmarshal([]byte(dj), &r.DeclaredSideEffects)
	_ = json.Unmarshal([]byte(ej), &r.Exposure)
	return &r, nil
}

func (r *approvalRow) toApproval() *Approval {
	return &Approval{
		ApprovalID: r.ApprovalID, RunID: r.RunID, OperationID: r.OperationID, Action: r.Action,
		Resource: r.Resource, IdempotencyKey: r.IdempotencyKey, Reason: r.Reason,
		Status: r.Status, CreatedAt: r.CreatedAt, DecisionReason: r.DecisionReason.String,
	}
}

func approvalApprovalID(a *approvalRow) any {
	if a == nil {
		return nil
	}
	return a.ApprovalID
}

// ---- 纯函数工具 ----

func validateEffectInputs(operationID, action, resource, idempotencyKey, effectClass string, maxAttempts int) error {
	type field struct{ v, name string }
	for _, f := range []field{
		{operationID, "operation_id"}, {action, "action"}, {resource, "resource"},
		{idempotencyKey, "idempotency_key"}, {effectClass, "effect_class"},
	} {
		if err := requireText(f.v, f.name); err != nil {
			return err
		}
	}
	if maxAttempts < 1 {
		return fmt.Errorf("max_attempts 至少为 1")
	}
	return nil
}

func approvalScopeMatches(a *approvalRow, action, resource, idempotencyKey string) bool {
	return a.Action == action && a.Resource == resource && a.IdempotencyKey == idempotencyKey
}

func effectScopeMatches(e Effect, operationID, action, resource, idempotencyKey, effectClass string) bool {
	return e.OperationID == operationID && e.Action == action && e.Resource == resource &&
		e.IdempotencyKey == idempotencyKey && e.EffectClass == effectClass
}

func generateToken() string {
	var b [32]byte
	_, _ = rand.Read(b[:])
	return base64.RawURLEncoding.EncodeToString(b[:])
}

func sha256Hex(s string) string {
	h := sha256.Sum256([]byte(s))
	return hex.EncodeToString(h[:])
}

// constantTimeTokenMatch 用恒定时间比较 sha256 hex，避免时序侧信道。
func constantTimeTokenMatch(storedHash, providedToken string) bool {
	if storedHash == "" || providedToken == "" {
		return false
	}
	computed := sha256Hex(providedToken)
	return subtle.ConstantTimeCompare([]byte(storedHash), []byte(computed)) == 1
}

func contains(s []string, v string) bool {
	for _, x := range s {
		if x == v {
			return true
		}
	}
	return false
}

func toStringSlice(v any) []string {
	switch t := v.(type) {
	case []string:
		return t
	case []any:
		out := make([]string, 0, len(t))
		for _, x := range t {
			if s, ok := x.(string); ok {
				out = append(out, s)
			}
		}
		return out
	}
	return nil
}

func toMap(v any) map[string]any {
	if m, ok := v.(map[string]any); ok {
		return m
	}
	return map[string]any{}
}

func strOrEmpty(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func truthy(v any) bool {
	if b, ok := v.(bool); ok {
		return b
	}
	return false
}

func absPath(p string) string {
	abs, err := filepath.Abs(p)
	if err != nil {
		return p
	}
	return abs
}

// isWithin 判断 child 是否等于 root 或严格位于 root 之下（等价于 Python is_relative_to）。
func isWithin(child, root string) bool {
	rel, err := filepath.Rel(root, child)
	if err != nil {
		return false
	}
	return rel == "." || (rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)))
}
