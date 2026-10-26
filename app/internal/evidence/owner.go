package evidence

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

// defaultEventLimit 是 ListEvents 在未显式给 limit 时的上限，避免事件流无界返回。
const defaultEventLimit = 500

// ---- 状态机核心方法（C26 CompositionOwner） ----

// CreateRun 创建持久运行身份（不启动执行），状态落 'created'。
// 向后兼容：repo/branch/environment 取空串（显示层按 unknown 处理）。
// ADR 0019 的上下文维度请改用 CreateRunWithContext。
func (o *Owner) CreateRun(runID, taskType string, input any, metadata map[string]any) (*Run, error) {
	return o.CreateRunWithContext(runID, taskType, input, metadata, "", "", "")
}

// CreateRunWithContext 同 CreateRun，但携带 ADR 0019 的 run 上下文维度
// （repo / branch / environment）。三参空串等价于未知语境。
func (o *Owner) CreateRunWithContext(runID, taskType string, input any, metadata map[string]any, repo, branch, environment string) (*Run, error) {
	if err := requireText(runID, "run_id"); err != nil {
		return nil, err
	}
	if err := requireText(taskType, "task_type"); err != nil {
		return nil, err
	}
	if metadata == nil {
		metadata = map[string]any{}
	}
	ij, err := jsonString(input)
	if err != nil {
		return nil, err
	}
	mj, err := jsonString(metadata)
	if err != nil {
		return nil, err
	}
	ts := nowUTC()
	if _, err := o.db.Exec(
		`INSERT INTO runs(run_id, task_type, input_json, metadata_json, status, repo, branch, environment, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		runID, taskType, ij, mj, StatusCreated, repo, branch, environment, ts, ts); err != nil {
		if isUniqueViolation(err) {
			return nil, fmt.Errorf("%w: run 已存在 %s", ErrRunExists, runID)
		}
		return nil, fmt.Errorf("创建 run 失败：%w", err)
	}
	if _, err := o.RecordEvent(runID, "run.created", map[string]any{"task_type": taskType}, EvidenceSourceNative); err != nil {
		return nil, err
	}
	return o.GetRun(runID)
}

// StartRun 把 created / recovering / waiting_approval 的运行推进到 running。
// 终态→running 被矩阵拒绝（fail-closed）；已 running 为幂等 no-op。
func (o *Owner) StartRun(runID string) (*Run, error) {
	if err := requireText(runID, "run_id"); err != nil {
		return nil, err
	}
	var out *Run
	err := o.transact(func(tx *sql.Tx) error {
		r, err := o.runRow(tx, runID)
		if err != nil {
			return err
		}
		if err := o.setRunStatus(tx, runID, r.Status, StatusRunning, "run.started", nil); err != nil {
			return err
		}
		out, err = o.getRunTx(tx, runID)
		return err
	})
	return out, err
}

// RestartRun 是审计逃生舱：把非 running 的终态/中间态重新武装为 running
// （绕过正常生命周期矩阵，与 composition.py restart_run 一一对应）。
// running 为幂等 no-op；其余来源（理论上不存在其他状态）拒绝。
func (o *Owner) RestartRun(runID, reason string) (*Run, error) {
	if err := requireText(reason, "reason"); err != nil {
		return nil, err
	}
	var out *Run
	err := o.transact(func(tx *sql.Tx) error {
		r, err := o.runRow(tx, runID)
		if err != nil {
			return err
		}
		old := r.Status
		if old == StatusRunning {
			out, _ = o.getRunTx(tx, runID)
			return nil
		}
		rearmable := map[RunStatus]bool{
			StatusCreated: true, StatusWaitingApproval: true, StatusRecovering: true,
			StatusCompleted: true, StatusFailed: true, StatusSafeStopped: true,
		}
		if !rearmable[old] {
			return fmt.Errorf("%w: run %s 不能从 %s 重启", ErrInvalidTransition, runID, old)
		}
		ts := nowUTC()
		if _, err := tx.Exec(`UPDATE runs SET status=?, updated_at=? WHERE run_id=?`, StatusRunning, ts, runID); err != nil {
			return fmt.Errorf("重启 run 失败：%w", err)
		}
		if err := o.appendEventTx(tx, runID, "run.restarted", map[string]any{"from": string(old), "to": "running", "reason": reason}, nil); err != nil {
			return err
		}
		out, err = o.getRunTx(tx, runID)
		return err
	})
	return out, err
}

// CompleteRun 仅在 running 且无待审批/无未决 effect/无身份违例时完成。
// 守卫忠实复刻 composition.py complete_run 的 fail-closed 语义。
// 注：Python 将 semantic result 写入 results 表；B2-narrow 范围不含 results 表，
// 故改为写入 run.completed 事件 payload（仍持久、可追溯）。results 表留待 1-5-6-2。
func (o *Owner) CompleteRun(runID string, semanticResult any) (*Run, error) {
	var out *Run
	err := o.transact(func(tx *sql.Tx) error {
		r, err := o.runRow(tx, runID)
		if err != nil {
			return err
		}
		if r.Status != StatusRunning {
			return fmt.Errorf("%w: run %s 状态非 running：%s", ErrInvalidTransition, runID, r.Status)
		}
		var pending int
		if err := tx.QueryRow(`SELECT COUNT(*) FROM approvals WHERE run_id=? AND status='pending'`, runID).Scan(&pending); err != nil {
			return err
		}
		if pending > 0 {
			return fmt.Errorf("%w: run %s 有 %d 个待审批", ErrInvalidTransition, runID, pending)
		}
		unresolved, err := o.unresolvedEffectsTx(tx, runID)
		if err != nil {
			return err
		}
		if unresolved > 0 {
			return fmt.Errorf("%w: run %s 有 %d 个未决 effect", ErrInvalidTransition, runID, unresolved)
		}
		violations, err := o.detectViolationsTx(tx, runID)
		if err != nil {
			return err
		}
		if len(violations) > 0 {
			return fmt.Errorf("%w: run %s 有 %d 个未决身份引用", ErrInvalidTransition, runID, len(violations))
		}
		return o.setRunStatus(tx, runID, r.Status, StatusCompleted, "run.completed", map[string]any{"semantic": semanticResult})
	})
	if err != nil {
		return nil, err
	}
	out, err = o.GetRun(runID)
	return out, err
}

// FailRun 在无未决 effect 时落 failed；若有未决 effect 则改为 safe_stopped 并拒。
// 忠实复刻 composition.py fail_run 的 fail-closed 转义。
func (o *Owner) FailRun(runID string, errVal any) (*Run, error) {
	var out *Run
	blocked := false
	err := o.transact(func(tx *sql.Tx) error {
		r, err := o.runRow(tx, runID)
		if err != nil {
			return err
		}
		unresolved, err := o.unresolvedEffectsTx(tx, runID)
		if err != nil {
			return err
		}
		if unresolved > 0 {
			if e := o.setRunStatus(tx, runID, r.Status, StatusSafeStopped, "run.safe_stopped", map[string]any{"reason": "uncertain_effect"}); e != nil {
				return e
			}
			blocked = true
			return nil
		}
		return o.setRunStatus(tx, runID, r.Status, StatusFailed, "run.failed", map[string]any{"error": errVal})
	})
	if err != nil {
		return nil, err
	}
	if blocked {
		return nil, fmt.Errorf("%w: run %s 因未决 effect 被 safe-stop", ErrInvalidTransition, runID)
	}
	out, err = o.GetRun(runID)
	return out, err
}

// SafeStopRun 使运行终态化（不尝试修复未知状态），任何非 safe_stopped 状态均可进入。
// 终态→safe_stopped 被矩阵拒绝（fail-closed，与 composition.py 一致）。
func (o *Owner) SafeStopRun(runID, reason string) (*Run, error) {
	if err := requireText(reason, "reason"); err != nil {
		return nil, err
	}
	var out *Run
	err := o.transact(func(tx *sql.Tx) error {
		r, err := o.runRow(tx, runID)
		if err != nil {
			return err
		}
		if err := o.setRunStatus(tx, runID, r.Status, StatusSafeStopped, "run.safe_stopped", map[string]any{"reason": reason}); err != nil {
			return err
		}
		out, err = o.getRunTx(tx, runID)
		return err
	})
	return out, err
}

// BeginRecovery 把 running 的运行移入显式 owner 控制的恢复态。
// 守卫：有未决 effect 时拒绝（fail-closed）。
func (o *Owner) BeginRecovery(runID, reason string) (*Run, error) {
	if err := requireText(reason, "reason"); err != nil {
		return nil, err
	}
	var out *Run
	err := o.transact(func(tx *sql.Tx) error {
		r, err := o.runRow(tx, runID)
		if err != nil {
			return err
		}
		unresolved, err := o.unresolvedEffectsTx(tx, runID)
		if err != nil {
			return err
		}
		if unresolved > 0 {
			return fmt.Errorf("%w: run %s 不能在有未决 effect 时恢复", ErrInvalidTransition, runID)
		}
		if err := o.setRunStatus(tx, runID, r.Status, StatusRecovering, "run.recovering", map[string]any{"reason": reason}); err != nil {
			return err
		}
		out, err = o.getRunTx(tx, runID)
		return err
	})
	return out, err
}

// ---- 读取与投影 ----

// GetRun 读取一个运行及其事件/效果/曝光投影。
func (o *Owner) GetRun(runID string) (*Run, error) {
	if err := requireText(runID, "run_id"); err != nil {
		return nil, err
	}
	var out *Run
	err := o.transact(func(tx *sql.Tx) error {
		var e error
		out, e = o.getRunTx(tx, runID)
		return e
	})
	return out, err
}

// ListRuns 按创建时间倒序列出全部运行（不含事件/效果投影，便于列表渲染）。
func (o *Owner) ListRuns() ([]*Run, error) {
	rows, err := o.db.Query(`SELECT run_id, task_type, input_json, metadata_json, status, repo, branch, environment, created_at, updated_at FROM runs ORDER BY created_at DESC, run_id DESC`)
	if err != nil {
		return nil, fmt.Errorf("列举 run 失败：%w", err)
	}
	defer rows.Close()
	out := make([]*Run, 0)
	for rows.Next() {
		var r runRow
		if err := rows.Scan(&r.RunID, &r.TaskType, &r.InputJSON, &r.MetadataJSON, &r.Status, &r.Repo, &r.Branch, &r.Environment, &r.CreatedAt, &r.UpdatedAt); err != nil {
			return nil, fmt.Errorf("扫描 run 失败：%w", err)
		}
		out = append(out, rowToRun(r))
	}
	return out, nil
}

// ListEvents 列出事件，供「事件流」视图消费（ADR 0016; formerly roadmap 1-5-6-3）。
// runID 为空 = 跨 run 查询；typeFilter 为空 = 不过滤类型（传 "safe_stopped" 即安全停止事件流）。
// limit <= 0 时取 defaultEventLimit。按 seq 升序（发生顺序）返回。
func (o *Owner) ListEvents(runID, typeFilter string, limit int) ([]Event, error) {
	if limit <= 0 {
		limit = defaultEventLimit
	}
	q := `SELECT seq, event_id, run_id, type, payload_json, evidence_source, created_at FROM events`
	var where []string
	var args []any
	if runID != "" {
		where = append(where, `run_id=?`)
		args = append(args, runID)
	}
	if typeFilter != "" {
		where = append(where, `type=?`)
		args = append(args, typeFilter)
	}
	if len(where) > 0 {
		q += ` WHERE ` + strings.Join(where, ` AND `)
	}
	q += ` ORDER BY seq LIMIT ?`
	args = append(args, limit)

	rows, err := o.db.Query(q, args...)
	if err != nil {
		return nil, fmt.Errorf("列举事件失败：%w", err)
	}
	defer rows.Close()
	out := make([]Event, 0)
	for rows.Next() {
		var e Event
		var pj string
		var src sql.NullString // evidence_source 可空：NULL 时取空串而非扫描失败
		if err := rows.Scan(&e.Seq, &e.EventID, &e.RunID, &e.Type, &pj, &src, &e.CreatedAt); err != nil {
			return nil, fmt.Errorf("扫描事件失败：%w", err)
		}
		_ = json.Unmarshal([]byte(pj), &e.Payload)
		e.EvidenceSource = src.String
		out = append(out, e)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历事件失败：%w", err)
	}
	return out, nil
}

// RecordEvent 追加一条结构化证据事件（adapter 消息即证据，owner 赋规范行）。
func (o *Owner) RecordEvent(runID, eventType string, payload map[string]any, evidenceSource string) (string, error) {
	if err := requireText(runID, "run_id"); err != nil {
		return "", err
	}
	if err := requireText(eventType, "event_type"); err != nil {
		return "", err
	}
	if payload == nil {
		payload = map[string]any{}
	}
	if !validEvidenceSource(evidenceSource) {
		evidenceSource = EvidenceSourceNative
	}
	pj, err := jsonString(payload)
	if err != nil {
		return "", err
	}
	eid := newID()
	if _, err := o.db.Exec(
		`INSERT INTO events(event_id, run_id, type, payload_json, evidence_source, created_at)
		 VALUES (?, ?, ?, ?, ?, ?)`,
		eid, runID, eventType, pj, evidenceSource, nowUTC()); err != nil {
		return "", fmt.Errorf("写事件失败：%w", err)
	}
	return eid, nil
}

// RecordDeclaredExposure 记录运行的声明副作用曝光面（幂等 upsert）。
func (o *Owner) RecordDeclaredExposure(runID string, sideEffects any, exposure any) (*DeclaredExposure, error) {
	if err := requireText(runID, "run_id"); err != nil {
		return nil, err
	}
	sj, err := jsonString(sideEffects)
	if err != nil {
		return nil, err
	}
	ej, err := jsonString(exposure)
	if err != nil {
		return nil, err
	}
	ts := nowUTC()
	if _, err := o.db.Exec(
		`INSERT INTO declared_exposure(run_id, declared_side_effects_json, exposure_json, declared_at)
		 VALUES (?, ?, ?, ?)
		 ON CONFLICT(run_id) DO UPDATE SET
		   declared_side_effects_json=excluded.declared_side_effects_json,
		   exposure_json=excluded.exposure_json, declared_at=excluded.declared_at`,
		runID, sj, ej, ts); err != nil {
		return nil, fmt.Errorf("写声明曝光失败：%w", err)
	}
	return &DeclaredExposure{RunID: runID, DeclaredSideEffects: sideEffects, Exposure: exposure, DeclaredAt: ts}, nil
}

// DetectIdentityViolations 扫描身份图里所有无法解析的引用（fail-closed）。
// 覆盖四类链接（1-4-5 补齐，对齐 composition.py detect_identity_violations）：
//  1. 子表的 run_id（effects / approvals / declared_exposure / events /
//     provider_exit_ledger——1-4-3 加了这张表却漏进扫描，本节点补上）；
//  2. effects.approval_id；
//  3. effect_attempts.effect_id（孤儿尝试无 run 可归属，仅全 owner 审计时报，
//     RunID 记 "unknown"）；
//  4. runs.metadata 的 parent_run_id / child_run_id（断链）。
//
// runID 非空时仅扫描该 run 的入/出边；空则为全 owner 完整性审计。
// 忠实复刻 composition.py 的 fail-closed 语义（只报告无法解析的引用，绝不臆造目标）。
func (o *Owner) DetectIdentityViolations(runID string) ([]Violation, error) {
	var v []Violation
	err := o.transact(func(tx *sql.Tx) error {
		var e error
		v, e = o.detectViolationsTx(tx, runID)
		return e
	})
	return v, err
}

// ---- 内部辅助 ----

func (o *Owner) runRow(tx *sql.Tx, runID string) (runRow, error) {
	row := tx.QueryRow(`SELECT run_id, task_type, input_json, metadata_json, status, repo, branch, environment, created_at, updated_at FROM runs WHERE run_id=?`, runID)
	var r runRow
	if err := row.Scan(&r.RunID, &r.TaskType, &r.InputJSON, &r.MetadataJSON, &r.Status, &r.Repo, &r.Branch, &r.Environment, &r.CreatedAt, &r.UpdatedAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return r, fmt.Errorf("%w: run %s", ErrRunNotFound, runID)
		}
		return r, fmt.Errorf("读取 run 失败：%w", err)
	}
	return r, nil
}

func (o *Owner) getRunTx(tx *sql.Tx, runID string) (*Run, error) {
	r, err := o.runRow(tx, runID)
	if err != nil {
		return nil, err
	}
	run := rowToRun(r)

	erows, err := tx.Query(`SELECT seq, event_id, run_id, type, payload_json, evidence_source, created_at FROM events WHERE run_id=? ORDER BY seq`, runID)
	if err != nil {
		return nil, fmt.Errorf("读取事件失败：%w", err)
	}
	defer erows.Close()
	for erows.Next() {
		var e Event
		var pj string
		if err := erows.Scan(&e.Seq, &e.EventID, &e.RunID, &e.Type, &pj, &e.EvidenceSource, &e.CreatedAt); err != nil {
			return nil, fmt.Errorf("扫描事件失败：%w", err)
		}
		_ = json.Unmarshal([]byte(pj), &e.Payload)
		run.Events = append(run.Events, e)
	}

	frows, err := tx.Query(`SELECT effect_id, run_id, operation_id, effect_class, action, resource, status, attempt, max_attempts, created_at, updated_at FROM effects WHERE run_id=? ORDER BY created_at, effect_id`, runID)
	if err != nil {
		return nil, fmt.Errorf("读取 effect 失败：%w", err)
	}
	defer frows.Close()
	for frows.Next() {
		var f Effect
		if err := frows.Scan(&f.EffectID, &f.RunID, &f.OperationID, &f.EffectClass, &f.Action, &f.Resource, &f.Status, &f.Attempt, &f.MaxAttempts, &f.CreatedAt, &f.UpdatedAt); err != nil {
			return nil, fmt.Errorf("扫描 effect 失败：%w", err)
		}
		run.Effects = append(run.Effects, f)
	}

	var dj, ej, dat string
	if err := tx.QueryRow(`SELECT declared_side_effects_json, exposure_json, declared_at FROM declared_exposure WHERE run_id=?`, runID).Scan(&dj, &ej, &dat); err == nil {
		var de, ex any
		_ = json.Unmarshal([]byte(dj), &de)
		_ = json.Unmarshal([]byte(ej), &ex)
		run.Exposure = &DeclaredExposure{RunID: runID, DeclaredSideEffects: de, Exposure: ex, DeclaredAt: dat}
	}
	return run, nil
}

// setRunStatus 按转移矩阵推进 run 状态，并追加对应事件（与 _set_run_status 等价）。
func (o *Owner) setRunStatus(tx *sql.Tx, runID string, old, new RunStatus, eventType string, payload map[string]any) error {
	if _, ok := runStatuses[new]; !ok {
		return fmt.Errorf("%w: 未知状态 %q", ErrInvalidTransition, new)
	}
	if old == new {
		return nil
	}
	if !runTransitions[old][new] {
		return fmt.Errorf("%w: run %s 不能从 %s 转移到 %s", ErrInvalidTransition, runID, old, new)
	}
	ts := nowUTC()
	if _, err := tx.Exec(`UPDATE runs SET status=?, updated_at=? WHERE run_id=?`, new, ts, runID); err != nil {
		return fmt.Errorf("更新 run 状态失败：%w", err)
	}
	return o.appendEventTx(tx, runID, eventType, map[string]any{"from": string(old), "to": string(new)}, payload)
}

// appendEventTx 在事务内写事件；base 与 payload 合并进 payload_json。
func (o *Owner) appendEventTx(tx *sql.Tx, runID, eventType string, base, extra map[string]any) error {
	if err := requireText(eventType, "event_type"); err != nil {
		return err
	}
	merged := map[string]any{}
	for k, v := range base {
		merged[k] = v
	}
	for k, v := range extra {
		merged[k] = v
	}
	pj, err := jsonString(merged)
	if err != nil {
		return err
	}
	eid := newID()
	if _, err := tx.Exec(
		`INSERT INTO events(event_id, run_id, type, payload_json, evidence_source, created_at)
		 VALUES (?, ?, ?, ?, ?, ?)`,
		eid, runID, eventType, pj, EvidenceSourceNative, nowUTC()); err != nil {
		return fmt.Errorf("写事件失败：%w", err)
	}
	return nil
}

func (o *Owner) unresolvedEffectsTx(tx *sql.Tx, runID string) (int, error) {
	var n int
	if err := tx.QueryRow(
		`SELECT COUNT(*) FROM effects WHERE run_id=? AND status IN ('claimed','uncertain','retryable','unknown')`,
		runID).Scan(&n); err != nil {
		return 0, fmt.Errorf("统计未决 effect 失败：%w", err)
	}
	return n, nil
}

// detectViolationsTx 是引用完整性扫描的事务实现（供 DetectIdentityViolations 与 CompleteRun 复用）。
func (o *Owner) detectViolationsTx(tx *sql.Tx, scopeRunID string) ([]Violation, error) {
	violations := make([]Violation, 0)
	validRuns := map[string]bool{}
	rr, err := tx.Query(`SELECT run_id FROM runs`)
	if err != nil {
		return nil, fmt.Errorf("读取 runs 失败：%w", err)
	}
	for rr.Next() {
		var r string
		if err := rr.Scan(&r); err != nil {
			rr.Close()
			return nil, err
		}
		validRuns[r] = true
	}
	rr.Close()

	// provider_exit_ledger（1-4-3 引入）也是 run 的子表，漏掉它等于身份图少半张。
	childTables := []string{"effects", "approvals", "declared_exposure", "events", "provider_exit_ledger"}
	for _, t := range childTables {
		cr, err := tx.Query(fmt.Sprintf(`SELECT run_id FROM %s`, t))
		if err != nil {
			return nil, fmt.Errorf("扫描 %s 失败：%w", t, err)
		}
		for cr.Next() {
			var childRun string
			if err := cr.Scan(&childRun); err != nil {
				cr.Close()
				return nil, err
			}
			if validRuns[childRun] {
				continue
			}
			if scopeRunID != "" && childRun != scopeRunID {
				continue
			}
			violations = append(violations, Violation{
				Kind:     "orphan_" + t + "_run",
				RunID:    childRun,
				RefTable: t,
				RefID:    childRun,
				Detail:   fmt.Sprintf("%s.run_id 引用了不存在的 run %s", t, childRun),
			})
		}
		cr.Close()
	}

	ar, err := tx.Query(`SELECT effect_id, approval_id, run_id FROM effects WHERE approval_id IS NOT NULL`)
	if err != nil {
		return nil, fmt.Errorf("扫描 effect approval 失败：%w", err)
	}
	for ar.Next() {
		var eid, aid, rid string
		if err := ar.Scan(&eid, &aid, &rid); err != nil {
			ar.Close()
			return nil, err
		}
		var cnt int
		if err := tx.QueryRow(`SELECT COUNT(*) FROM approvals WHERE approval_id=?`, aid).Scan(&cnt); err != nil {
			ar.Close()
			return nil, err
		}
		if cnt > 0 {
			continue
		}
		if scopeRunID != "" && rid != scopeRunID {
			continue
		}
		violations = append(violations, Violation{
			Kind:     "orphan_effect_approval",
			RunID:    rid,
			RefTable: "effects",
			RefID:    aid,
			Detail:   fmt.Sprintf("effects.approval_id 引用了不存在的 approval %s", aid),
		})
	}
	ar.Close()

	// effect_attempts → effects：孤儿尝试没有 run 可归属（它的 run 只能经
	// effect 反查），所以只在全 owner 审计里报，RunID 显式记 "unknown"。
	if scopeRunID == "" {
		erows, err := tx.Query(`SELECT effect_id, run_id FROM effects`)
		if err != nil {
			return nil, fmt.Errorf("扫描 effects 失败：%w", err)
		}
		effectRun := map[string]string{}
		for erows.Next() {
			var eid, rid string
			if err := erows.Scan(&eid, &rid); err != nil {
				erows.Close()
				return nil, err
			}
			effectRun[eid] = rid
		}
		erows.Close()
		atrows, err := tx.Query(`SELECT DISTINCT effect_id FROM effect_attempts ORDER BY effect_id`)
		if err != nil {
			return nil, fmt.Errorf("扫描 effect_attempts 失败：%w", err)
		}
		for atrows.Next() {
			var eid string
			if err := atrows.Scan(&eid); err != nil {
				atrows.Close()
				return nil, err
			}
			if _, ok := effectRun[eid]; ok {
				continue
			}
			violations = append(violations, Violation{
				Kind:     "orphan_effect_attempt_effect",
				RunID:    "unknown",
				RefTable: "effect_attempts",
				RefID:    eid,
				Detail:   fmt.Sprintf("effect_attempts.effect_id 引用了不存在的 effect %s", eid),
			})
		}
		atrows.Close()
	}

	// runs.metadata 的 parent/child 链接（AGENTS.md 要求 parent/child run 可查询）。
	metaV, err := detectMetadataLinkViolationsTx(tx, scopeRunID, validRuns)
	if err != nil {
		return nil, fmt.Errorf("扫描 metadata 链接失败：%w", err)
	}
	violations = append(violations, metaV...)

	return violations, nil
}

func rowToRun(r runRow) *Run {
	run := &Run{
		RunID:       r.RunID,
		TaskType:    r.TaskType,
		Status:      r.Status,
		Repo:        r.Repo,
		Branch:      r.Branch,
		Environment: r.Environment,
		CreatedAt:   r.CreatedAt,
		UpdatedAt:   r.UpdatedAt,
	}
	_ = json.Unmarshal([]byte(r.InputJSON), &run.Input)
	if err := json.Unmarshal([]byte(r.MetadataJSON), &run.Metadata); err != nil || run.Metadata == nil {
		run.Metadata = map[string]any{}
	}
	return run
}
