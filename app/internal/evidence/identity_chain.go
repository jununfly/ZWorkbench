// identity_chain.go 是 ADR 0016 (formerly roadmap 1-4-4) 的落地：让 B2-narrow 证据核心的身份链
// （run → attempt → effect → approval）成为**可查询**对象。
//
// 设计不变式（与 composition.py 的 fail-closed 口径一致）：
//  1. 只读。不新增表、不新增列、不开写口；链的形状完全由既有 runs /
//     effects / effect_attempts / approvals 四表推导。
//  2. 未知 id = ErrNotFound，绝不返回空链。空链会被下游误读成「没有证据」，
//     而「查不到」和「不存在」在本产品里是两种必须分开的事实。
//  3. 断链显式化。effect → approval 标注三态 linked / unlinked / dangling，
//     dangling 与 DetectIdentityViolations 的 orphan_effect_approval 同源；
//     链只负责**看见**它，不替审计、绝不静默补洞。
//  4. 入口（entry）随链返回。同一条链可以从 run / effect / approval /
//     operation 四个起点进入，读的人必须知道自己是站在哪看的。
//
// attempt 不是入口：effect_attempts.attempt 是 effect 内序数，没有全局
// attempt_id 语义，因此只能作为 effect 的子节点被查询（ListEffectAttempts）。

package evidence

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
)

// 身份链的四种解析入口（ResolveIdentityChain 的 kind 参数）。
const (
	EntryRunID       = "run_id"
	EntryEffectID    = "effect_id"
	EntryApprovalID  = "approval_id"
	EntryOperationID = "operation_id"
)

// ErrAmbiguousIdentity 表示同一个 id 在不同表里解析到了互相冲突的归属。
// 不做「挑一个看起来更像的」猜测——歧义必须拒绝（fail-closed）。
var ErrAmbiguousIdentity = errors.New("ambiguous identity")

// effect→approval 的三种连接态（绝不出现第四种「默认按成功算」）。
const (
	ApprovalLinked   = "linked"   // effects.approval_id 有值且 approval 存在
	ApprovalUnlinked = "unlinked" // effects.approval_id 为 NULL（read-only/idempotent 免审批）
	ApprovalDangling = "dangling" // effects.approval_id 有值但 approval 不存在（断链，等同孤儿引用）
)

// ChainEntry 记录这条链是从哪个身份解析出来的。
type ChainEntry struct {
	Kind string `json:"kind"`
	ID   string `json:"id"`
	// Detail 补充解析结论（例如 operation_id 同时命中 effect 与 approval 时
	// 的归属一致性判断），便于 Human 复核「为什么是这条链」。
	Detail string `json:"detail,omitempty"`
}

// EffectAttempt 是 effect_attempts 的一行：一次物理尝试的身份记录。
// 此前 attempt 没有任何查询口，是身份链上唯一的缺口（1-4-4 补）。
type EffectAttempt struct {
	AttemptID  int64  `json:"attempt_id"`
	EffectID   string `json:"effect_id"`
	Attempt    int    `json:"attempt"`
	Status     string `json:"status"`
	StartedAt  string `json:"started_at"`
	FinishedAt string `json:"finished_at,omitempty"`
	Result     any    `json:"result,omitempty"`
	Error      any    `json:"error,omitempty"`
}

// EffectNode 是链上的一个 effect 节点：effect 本体 + 它的全部尝试 + 所绑审批。
type EffectNode struct {
	Effect
	Attempts        []EffectAttempt `json:"attempts"`
	Approval        *Approval       `json:"approval,omitempty"`
	ApprovalLink    string          `json:"approval_link"`
	ExternalReceipt any             `json:"external_receipt,omitempty"`
	LastError       any             `json:"last_error,omitempty"`
}

// ChainCounts 是链的规模统计，供 UI 一眼判断「这条链有多少实体」。
type ChainCounts struct {
	Effects         int `json:"effects"`
	Attempts        int `json:"attempts"`
	Approvals       int `json:"approvals"`
	PhysicalEffects int `json:"physical_effects"`
	DanglingLinks   int `json:"dangling_links"`
}

// IdentityChain 是一条完整可查询的身份链。
type IdentityChain struct {
	RunID string `json:"run_id"`
	// Run 只带身份与状态投影（不含 events/effects，避免与链本身重复）。
	Run       *Run         `json:"run"`
	Entry     ChainEntry   `json:"entry"`
	Effects   []EffectNode `json:"effects"`
	Approvals []Approval   `json:"approvals"`
	Counts    ChainCounts  `json:"counts"`
}

// ListEffectAttempts 列出一个 effect 的全部物理尝试（按 attempt 升序）。
// effect 不存在时返回 ErrNotFound（fail-closed，不返回空列表冒充「没尝试过」）。
func (o *Owner) ListEffectAttempts(effectID string) ([]EffectAttempt, error) {
	if err := requireText(effectID, "effect_id"); err != nil {
		return nil, err
	}
	var out []EffectAttempt
	err := o.transact(func(tx *sql.Tx) error {
		if _, e := o.effectRow(tx, effectID); e != nil { // 存在性守卫
			return e
		}
		var e error
		out, e = o.attemptsByEffectTx(tx, effectID)
		return e
	})
	return out, err
}

// GetIdentityChain 以 run_id 为入口取整条身份链。
// run 不存在 = ErrNotFound。
func (o *Owner) GetIdentityChain(runID string) (*IdentityChain, error) {
	if err := requireText(runID, "run_id"); err != nil {
		return nil, err
	}
	var out *IdentityChain
	err := o.transact(func(tx *sql.Tx) error {
		if _, e := o.runRow(tx, runID); e != nil {
			return e
		}
		var e error
		out, e = o.buildChainTx(tx, runID, ChainEntry{Kind: EntryRunID, ID: runID})
		return e
	})
	return out, err
}

// ResolveIdentityChain 从任意一种身份出发解析整条链：
//
//	run_id / effect_id / approval_id —— 直接定位所属 run；
//	operation_id —— effects 与 approvals 都有该唯一键，同 run 才解析成功，
//	                跨 run 即 ErrAmbiguousIdentity（绝不猜归属）。
//
// 未知 kind 或空 id = ErrBadArgument；查不到 = ErrNotFound。
func (o *Owner) ResolveIdentityChain(kind, id string) (*IdentityChain, error) {
	if err := requireText(id, "id"); err != nil {
		return nil, err
	}
	if kind == EntryRunID {
		return o.GetIdentityChain(id)
	}
	var out *IdentityChain
	err := o.transact(func(tx *sql.Tx) error {
		switch kind {
		case EntryEffectID:
			e, eerr := o.effectRow(tx, id)
			if eerr != nil {
				return eerr
			}
			out, eerr = o.buildChainTx(tx, e.RunID, ChainEntry{Kind: kind, ID: id})
			return eerr
		case EntryApprovalID:
			a, aerr := o.approvalRow(tx, id)
			if aerr != nil {
				return aerr
			}
			out, aerr = o.buildChainTx(tx, a.RunID, ChainEntry{Kind: kind, ID: id})
			return aerr
		case EntryOperationID:
			return o.resolveByOperationTx(tx, id, &out)
		default:
			return fmt.Errorf("%w: 未知入口 kind %q（可选 %s/%s/%s/%s）",
				ErrBadArgument, kind, EntryRunID, EntryEffectID, EntryApprovalID, EntryOperationID)
		}
	})
	return out, err
}

// resolveByOperationTx 处理 operation_id 入口：effects.operation_id 与
// approvals.operation_id 都是唯一键，两者可能同时命中。
// 同 run → 解析成功；只有一个命中 → 解析成功；跨 run → 拒绝。
func (o *Owner) resolveByOperationTx(tx *sql.Tx, operationID string, out **IdentityChain) error {
	effectRun := ""
	if e, eerr := o.effectRowByOperationTx(tx, operationID); eerr == nil {
		effectRun = e.RunID
	}
	approvalRun := ""
	if a, aerr := o.approvalRowByOperation(tx, operationID); aerr == nil {
		approvalRun = a.RunID
	}
	switch {
	case effectRun == "" && approvalRun == "":
		return fmt.Errorf("%w: effect/approval 均无 operation %s", ErrNotFound, operationID)
	case effectRun != "" && approvalRun != "" && effectRun != approvalRun:
		return fmt.Errorf("%w: operation %s 的 effect 属 run %s，approval 属 run %s",
			ErrAmbiguousIdentity, operationID, effectRun, approvalRun)
	}
	runID := effectRun
	detail := "matched by operation_id"
	if runID == "" {
		runID = approvalRun
		detail = "matched approval.operation_id（尚无 effect）"
	} else if approvalRun != "" {
		detail = "matched effect.operation_id + approval.operation_id（同 run）"
	}
	var err error
	*out, err = o.buildChainTx(tx, runID, ChainEntry{Kind: EntryOperationID, ID: operationID, Detail: detail})
	return err
}

// effectRowByOperationTx 按 operation_id 精确查 effect（effects.operation_id 唯一）。
func (o *Owner) effectRowByOperationTx(tx *sql.Tx, operationID string) (Effect, error) {
	row := tx.QueryRow(
		`SELECT effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, status, attempt, max_attempts, physical_effect_count, approval_id
		 FROM effects WHERE operation_id=?`, operationID)
	var e Effect
	var apprID sql.NullString
	if err := row.Scan(&e.EffectID, &e.RunID, &e.OperationID, &e.IdempotencyKey, &e.EffectClass, &e.Action, &e.Resource, &e.Status, &e.Attempt, &e.MaxAttempts, &e.PhysicalEffectCount, &apprID); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return e, fmt.Errorf("%w: effect operation %s", ErrNotFound, operationID)
		}
		return e, fmt.Errorf("查 effect by operation 失败：%w", err)
	}
	e.ApprovalID = apprID.String
	return e, nil
}

// buildChainTx 在事务内拼出整条链（调用方需保证 run 存在）。
func (o *Owner) buildChainTx(tx *sql.Tx, runID string, entry ChainEntry) (*IdentityChain, error) {
	r, err := o.runRow(tx, runID)
	if err != nil {
		return nil, err
	}
	chain := &IdentityChain{
		RunID:     runID,
		Run:       rowToRun(r),
		Entry:     entry,
		Effects:   make([]EffectNode, 0),
		Approvals: make([]Approval, 0),
	}

	counts := ChainCounts{}
	frows, err := tx.Query(
		`SELECT effect_id, run_id, operation_id, idempotency_key, effect_class, action, resource, status, attempt, max_attempts, physical_effect_count, approval_id, external_receipt_json, last_error_json, created_at, updated_at
		 FROM effects WHERE run_id=? ORDER BY created_at, effect_id`, runID)
	if err != nil {
		return nil, fmt.Errorf("读取 effect 链失败：%w", err)
	}
	defer frows.Close()
	for frows.Next() {
		var e Effect
		var apprID sql.NullString
		var ext, last sql.NullString
		if err := frows.Scan(&e.EffectID, &e.RunID, &e.OperationID, &e.IdempotencyKey, &e.EffectClass, &e.Action, &e.Resource, &e.Status, &e.Attempt, &e.MaxAttempts, &e.PhysicalEffectCount, &apprID, &ext, &last, &e.CreatedAt, &e.UpdatedAt); err != nil {
			return nil, fmt.Errorf("扫描 effect 链失败：%w", err)
		}
		e.ApprovalID = apprID.String
		node := EffectNode{Effect: e, Attempts: make([]EffectAttempt, 0)}

		attempts, err := o.attemptsByEffectTx(tx, e.EffectID)
		if err != nil {
			return nil, err
		}
		node.Attempts = attempts

		// effect → approval：三态显式标注，绝不把断链当成功、也绝不补洞。
		switch {
		case e.ApprovalID == "":
			node.ApprovalLink = ApprovalUnlinked
		default:
			if a, aerr := o.approvalRow(tx, e.ApprovalID); aerr == nil {
				node.Approval = a.toApproval()
				node.ApprovalLink = ApprovalLinked
			} else {
				node.ApprovalLink = ApprovalDangling
				counts.DanglingLinks++
			}
		}
		if ext.String != "" {
			var v any
			_ = json.Unmarshal([]byte(ext.String), &v)
			node.ExternalReceipt = v
		}
		if last.String != "" {
			var v any
			_ = json.Unmarshal([]byte(last.String), &v)
			node.LastError = v
		}
		chain.Effects = append(chain.Effects, node)
		counts.Effects++
		counts.Attempts += len(attempts)
		counts.PhysicalEffects += e.PhysicalEffectCount
	}
	if err := frows.Err(); err != nil {
		return nil, fmt.Errorf("遍历 effect 链失败：%w", err)
	}

	arows, err := tx.Query(
		`SELECT approval_id FROM approvals WHERE run_id=? ORDER BY created_at, approval_id`, runID)
	if err != nil {
		return nil, fmt.Errorf("读取 approval 链失败：%w", err)
	}
	defer arows.Close()
	for arows.Next() {
		var aid string
		if err := arows.Scan(&aid); err != nil {
			return nil, fmt.Errorf("扫描 approval 链失败：%w", err)
		}
		a, err := o.approvalRow(tx, aid)
		if err != nil {
			return nil, err
		}
		// toApproval 只导出 Approval 结构体已声明的字段（不含 token_hash）。
		chain.Approvals = append(chain.Approvals, *a.toApproval())
		counts.Approvals++
	}
	if err := arows.Err(); err != nil {
		return nil, fmt.Errorf("遍历 approval 链失败：%w", err)
	}

	chain.Counts = counts
	return chain, nil
}

// attemptsByEffectTx 按 attempt 升序列出一个 effect 的尝试记录。
func (o *Owner) attemptsByEffectTx(tx *sql.Tx, effectID string) ([]EffectAttempt, error) {
	rows, err := tx.Query(
		`SELECT attempt_id, effect_id, attempt, status, started_at, finished_at, result_json, error_json
		 FROM effect_attempts WHERE effect_id=? ORDER BY attempt`, effectID)
	if err != nil {
		return nil, fmt.Errorf("读取 effect_attempts 失败：%w", err)
	}
	defer rows.Close()
	out := make([]EffectAttempt, 0)
	for rows.Next() {
		var a EffectAttempt
		var fin, res, errj sql.NullString
		if err := rows.Scan(&a.AttemptID, &a.EffectID, &a.Attempt, &a.Status, &a.StartedAt, &fin, &res, &errj); err != nil {
			return nil, fmt.Errorf("扫描 effect_attempts 失败：%w", err)
		}
		a.FinishedAt = fin.String
		if res.String != "" {
			var v any
			_ = json.Unmarshal([]byte(res.String), &v)
			a.Result = v
		}
		if errj.String != "" {
			var v any
			_ = json.Unmarshal([]byte(errj.String), &v)
			a.Error = v
		}
		out = append(out, a)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历 effect_attempts 失败：%w", err)
	}
	return out, nil
}
