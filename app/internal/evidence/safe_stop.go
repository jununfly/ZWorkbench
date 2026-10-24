// safe_stop.go 是 ADR 0016 (formerly roadmap 1-4-5) 的落地：C28 safe-stop 的**触发**与**收口**
// 两个 owner 动作（composition.py:1045 safe_stop_on_identity_violation 与
// :1065 reconcile_identity 的 Go 移植）。
//
// 为什么单独成节点：Go 侧 safe_stopped 状态本身早已齐备（SafeStopRun /
// FailRun 转义 / claim_effect 的 failStop / ReconcileEffect(unknown→safe_stopped)
// / safe_stopped 事件流），缺的正是「谁有资格把 run 停下来」和「停下来之后
// 怎么收口」这两个 owner 判定。没有它们，safe-stop 只能靠调用方自觉，
// 而 C28 的差异化恰恰在于 owner 主动 fail-closed。
//
// 不变式：
//  1. **检测本身不中断健康 run**。无违例 = 不改状态、SafeStopped=false。
//     （Python 原话：detection alone is never a reason to interrupt a healthy run。）
//  2. safe_stopped 是终态。收口成功（outcome=resolved）也**不复活** run。
//  3. 决策可复核：触发写 `run.identity.violation`（带完整 findings），
//     收口写 `run.identity.reconciled`（带 outcome + violation_count）。
//  4. 未知 run = ErrRunNotFound（fail-closed，不静默返空）。

package evidence

import (
	"database/sql"
	"encoding/json"
)

// IdentityViolationOutcome 是「扫身份图并按需 safe-stop」的返回契约。
// 三元组让调用方分清三种事实：没查到（error）/ 查了但没问题 / 查到并停了。
type IdentityViolationOutcome struct {
	Violations  []Violation `json:"violations"`
	SafeStopped bool        `json:"safe_stopped"`
	Status      RunStatus   `json:"status"`
}

// IdentityReconcileOutcome 是身份收口的返回契约。Outcome 只有两种：
// resolved（图已干净，仅记录决策，不改状态）/ unknown（仍有违例，保持终态）。
type IdentityReconcileOutcome struct {
	Outcome    string      `json:"outcome"`
	Violations []Violation `json:"violations"`
	Status     RunStatus   `json:"status"`
}

// SafeStopOnIdentityViolation 扫描一个 run 的身份图，有未解析引用就 safe-stop。
//
// 无违例 → 状态不变、SafeStopped=false；有违例 → 转 safe_stopped（已是
// safe_stopped 则不重复转移，但违例事件仍追加），并写 run.identity.violation。
// 未知 run → ErrRunNotFound。
func (o *Owner) SafeStopOnIdentityViolation(runID string) (*IdentityViolationOutcome, error) {
	if err := requireText(runID, "run_id"); err != nil {
		return nil, err
	}
	var out *IdentityViolationOutcome
	err := o.transact(func(tx *sql.Tx) error {
		r, err := o.runRow(tx, runID)
		if err != nil {
			return err
		}
		findings, err := o.detectViolationsTx(tx, runID)
		if err != nil {
			return err
		}
		if len(findings) == 0 {
			out = &IdentityViolationOutcome{Violations: []Violation{}, SafeStopped: false, Status: r.Status}
			return nil
		}
		if r.Status != StatusSafeStopped {
			if e := o.setRunStatus(tx, runID, r.Status, StatusSafeStopped, "run.safe_stopped",
				map[string]any{"reason": "identity_unresolved"}); e != nil {
				return e
			}
		}
		if e := o.appendEventTx(tx, runID, "run.identity.violation",
			map[string]any{"reason": "identity_unresolved"},
			map[string]any{"violations": findings}); e != nil {
			return e
		}
		out = &IdentityViolationOutcome{Violations: findings, SafeStopped: true, Status: StatusSafeStopped}
		return nil
	})
	return out, err
}

// ReconcileIdentity 记录一次身份收口决策并复查身份图。
//
// 仍有违例 → outcome=unknown，且 run 保持（或转入）safe_stopped；
// 图已干净 → outcome=resolved，只写事件、**不改状态**（终态不复活）。
//
// evidence 参数接但不落盘：与 Python 同理由——自由文本证据入账前需要脱敏
// 管道，而 owner 库拒收原始凭证字段；本切片没有 redaction 管道，所以只
// 接受参数以保持调用面对称。未知 run → ErrRunNotFound。
func (o *Owner) ReconcileIdentity(runID string, evidence any) (*IdentityReconcileOutcome, error) {
	_ = evidence // 显式标注：本切片不落盘（见上方注释）
	if err := requireText(runID, "run_id"); err != nil {
		return nil, err
	}
	var out *IdentityReconcileOutcome
	err := o.transact(func(tx *sql.Tx) error {
		r, err := o.runRow(tx, runID)
		if err != nil {
			return err
		}
		findings, err := o.detectViolationsTx(tx, runID)
		if err != nil {
			return err
		}
		outcome := "resolved"
		status := r.Status
		if len(findings) > 0 {
			outcome = "unknown"
			status = StatusSafeStopped
			if r.Status != StatusSafeStopped {
				if e := o.setRunStatus(tx, runID, r.Status, StatusSafeStopped, "run.safe_stopped",
					map[string]any{"reason": "identity_unresolved"}); e != nil {
					return e
				}
			}
		}
		payload := map[string]any{"outcome": outcome, "violation_count": len(findings)}
		if len(findings) > 0 {
			payload["violations"] = findings
		}
		if e := o.appendEventTx(tx, runID, "run.identity.reconciled", payload, nil); e != nil {
			return e
		}
		if findings == nil {
			findings = []Violation{}
		}
		out = &IdentityReconcileOutcome{Outcome: outcome, Violations: findings, Status: status}
		return nil
	})
	return out, err
}

// metadata 里承载的两条 run 间链接（AGENTS.md 长期约束要求 parent/child run
// 关系保持可查询）。断链 = 身份图被跨越，与孤儿 approval 同等处理。
var metadataRunLinks = []string{"parent_run_id", "child_run_id"}

// detectMetadataLinkViolationsTx 扫描 runs.metadata 里的 parent/child 链接，
// 报告指向不存在 run 的断链（顺序固定，保证输出可复现）。
func detectMetadataLinkViolationsTx(tx *sql.Tx, scopeRunID string, validRuns map[string]bool) ([]Violation, error) {
	rows, err := tx.Query(`SELECT run_id, metadata_json FROM runs ORDER BY run_id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]Violation, 0)
	for rows.Next() {
		var runID, mj string
		if err := rows.Scan(&runID, &mj); err != nil {
			return nil, err
		}
		if scopeRunID != "" && runID != scopeRunID {
			continue
		}
		var md map[string]any
		if err := json.Unmarshal([]byte(mj), &md); err != nil || md == nil {
			continue
		}
		for _, link := range metadataRunLinks {
			target := strOrEmpty(md[link])
			if target == "" || validRuns[target] {
				continue
			}
			out = append(out, Violation{
				Kind:     "broken_" + link,
				RunID:    runID,
				RefTable: "runs.metadata",
				RefID:    target,
				Detail:   runID + ".metadata." + link + " 引用了不存在的 run " + target,
			})
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}
