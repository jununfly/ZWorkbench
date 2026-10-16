// exit_ledger.go 是 Python composition.py 的 provider_exit_ledger 子系统
// （1-6-6 / roadmap 1-4-3）的 Go B2-narrow 移植。
//
// 核心不变式（fail-closed，逐字对齐 Python）：
//   - provider_remote_zero_residue 永远 = "unknown/delegated"。本地/owner
//     证据绝不能升级成「Provider 已清场」的证明。attach_receipt 若 receipt
//     声称其他值即拒。
//   - owner 库绝不摄入原始凭证：含 secret/token/password/credential/api_key
//     字段且带非 unknown 真值、或值呈 ak-/ark-/hex64 形状，一律拒。
// 默认（loopback/fake）产品路径无真实远程 provider，caliber 天然是
// unknown/delegated：本 ledger 只记录 run 用了哪个 provider、各资源状态全
// unknown、远程残留显式 unknown/delegated。这与 AGENTS.md「exit ledger 属于
// 唯一持久 owner」约束一致，也与 opt-in Ark inventory wizard（独立 owner
// 授权证据流）区分开。

package evidence

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"sort"
	"strings"
)

// hex64Re 匹配 64 位十六进制 SHA-256 指纹（local_state_fingerprint 合法值之一）。
var hex64Re = regexp.MustCompile("^[0-9a-fA-F]{64}$")

// ProviderExitLedger 是 provider 侧退出台账的一条记录（durable-owner 拥有）。
type ProviderExitLedger struct {
	LedgerID                  string            `json:"ledger_id"`
	RunID                     string            `json:"run_id"`
	Provider                  string            `json:"provider"`
	Endpoint                  string            `json:"endpoint"`
	AccountScope              string            `json:"account_scope"`
	ExitMode                  string            `json:"exit_mode"`
	ExitStatus                string            `json:"exit_status"`
	ProviderRemoteZeroResidue string            `json:"provider_remote_zero_residue"`
	SurfaceObservations       map[string]string `json:"surface_observations"`
	Statuses                  map[string]string `json:"statuses"`
	UnknownFields             []string          `json:"unknown_fields"`
	LocalStateFingerprint     string            `json:"local_state_fingerprint"`
	EvidenceClass             string            `json:"evidence_class"`
	RecordedAt                string            `json:"recorded_at"`
}

// 默认（loopback/unknown/delegated）口径下的状态与表面观测——全部 unknown。
func defaultExitStatuses() map[string]string {
	return map[string]string{
		"task_or_run":          "unknown",
		"webhook_or_integration": "unknown",
		"backup_or_snapshot":   "unknown",
		"coding_data":          "unknown",
		"api_key":              "unknown",
		"billing":              "unknown",
		"subscription":         "unknown",
		"account":              "unknown",
		"local_case":           "unknown",
		"exit_action":          "unknown",
	}
}

func defaultSurfaceObservations() map[string]string {
	return map[string]string{
		"task_or_run":      "unknown",
		"backup_or_snapshot": "unknown",
		"retention_policy": "unknown",
	}
}

// rejectSecretShapedAny 拒绝原始凭证形状：含凭证字段名且带真值，或值呈
// ak-/ark-/hex64 形状。对齐 Python 的 _reject_raw_credentials /
// _reject_secret_shaped_values。空值 / "unknown" 放行（属占位语义）。
func rejectSecretShapedAny(m map[string]any, ctx string) error {
	for k, v := range m {
		lk := strings.ToLower(k)
		isCredKey := strings.Contains(lk, "secret") ||
			strings.Contains(lk, "token") ||
			strings.Contains(lk, "password") ||
			strings.Contains(lk, "credential") ||
			(strings.Contains(lk, "api") && strings.Contains(lk, "key"))
		if isCredKey {
			if s, ok := v.(string); ok && s != "" && s != "unknown" {
				return fmt.Errorf("%w: %s 含疑似凭证字段 %q，owner 库不接收原始凭证", ErrBadArgument, ctx, k)
			}
		}
		if s, ok := v.(string); ok {
			if strings.HasPrefix(s, "ak-") || strings.HasPrefix(s, "ark-") {
				return fmt.Errorf("%w: %s 含密钥形状值（%q），owner 库不接收原始凭证", ErrBadArgument, ctx, k)
			}
			if hex64Re.MatchString(s) {
				return fmt.Errorf("%w: %s 含 hex64 密钥形状值（%q），owner 库不接收原始凭证", ErrBadArgument, ctx, k)
			}
		}
	}
	return nil
}

func strOrUnknown(v any) string {
	if s, ok := v.(string); ok && strings.TrimSpace(s) != "" {
		return s
	}
	return "unknown"
}

// RecordProviderExitLedger 记录 owner 拥有的 provider 侧退出台账（loopback
// 默认口径全部 unknown/delegated）。run 必须存在（引用完整性）。返回新建记录。
func (o *Owner) RecordProviderExitLedger(runID string, providerIdentity map[string]string) (*ProviderExitLedger, error) {
	if err := requireText(runID, "run_id"); err != nil {
		return nil, err
	}
	pid := make(map[string]any, len(providerIdentity))
	for k, v := range providerIdentity {
		pid[k] = v
	}
	if err := rejectSecretShapedAny(pid, "provider_identity"); err != nil {
		return nil, err
	}
	provider := strOrUnknown(pid["provider"])
	endpoint := strOrUnknown(pid["endpoint"])

	statuses := defaultExitStatuses()
	surface := defaultSurfaceObservations()
	unknownFields := sortedKeys(statuses)

	ts := nowUTC()
	ledgerID := newID()

	so, err := jsonString(surface)
	if err != nil {
		return nil, err
	}
	sj, err := jsonString(statuses)
	if err != nil {
		return nil, err
	}
	uj, err := jsonString(unknownFields)
	if err != nil {
		return nil, err
	}

	var out *ProviderExitLedger
	if err := o.transact(func(tx *sql.Tx) error {
		if _, err := o.runRow(tx, runID); err != nil {
			return err
		}
		if _, e := tx.Exec(`
			INSERT INTO provider_exit_ledger(
				ledger_id, run_id, provider, endpoint, account_scope,
				exit_mode, exit_status, provider_remote_zero_residue,
				surface_observations_json, statuses_json, unknown_fields_json,
				local_state_fingerprint, evidence_class, recorded_at
			) VALUES (?, ?, ?, ?, 'unknown', 'inventory-only', 'unknown/safe-stop',
				'unknown/delegated', ?, ?, ?, 'unknown', 'local-inventory', ?)`,
			ledgerID, runID, provider, endpoint, so, sj, uj, ts,
		); e != nil {
			return fmt.Errorf("写入 provider_exit_ledger 失败：%w", e)
		}
		if e := o.appendEventTx(tx, runID, "provider.exit.ledger.recorded", map[string]any{
			"ledger_id":                  ledgerID,
			"provider":                   provider,
			"caliber":                    "unknown/delegated",
			"provider_remote_zero_residue": "unknown/delegated",
		}, nil); e != nil {
			return e
		}
		out = &ProviderExitLedger{
			LedgerID:                  ledgerID,
			RunID:                     runID,
			Provider:                  provider,
			Endpoint:                  endpoint,
			AccountScope:              "unknown",
			ExitMode:                  "inventory-only",
			ExitStatus:                "unknown/safe-stop",
			ProviderRemoteZeroResidue: "unknown/delegated",
			SurfaceObservations:       surface,
			Statuses:                  statuses,
			UnknownFields:             unknownFields,
			LocalStateFingerprint:     "unknown",
			EvidenceClass:             "local-inventory",
			RecordedAt:                ts,
		}
		return nil
	}); err != nil {
		return nil, err
	}
	return out, nil
}

// RecordProviderExitLedgerOnce 每 run 至多记录一次 provider 侧退出台账。
// 幂等：run 已有记录则直接返回首条，不追加新 entry（保留 append-only 多 entry
// 契约，同时保证 harness 与 adapter 层对同一 run 只产生一条 Provider 侧记账）。
func (o *Owner) RecordProviderExitLedgerOnce(runID string, providerIdentity map[string]string) (*ProviderExitLedger, error) {
	existing, err := o.ProviderExitLedgerForRun(runID)
	if err != nil {
		return nil, err
	}
	if len(existing) > 0 {
		return existing[0], nil
	}
	return o.RecordProviderExitLedger(runID, providerIdentity)
}

// AttachProviderExitReceipt 追加一条 owner 提供的、已脱敏的 Provider 退出回执
// （v2 schema）。它补充默认 local-inventory 条目，提供 owner-backed 证据
// （回执指纹 + 背书），但永远不让本地/owner 证据升级成 Provider 清场证明。
//
// fail-closed：receipt 必须是 v2 schema；provider_remote_zero_residue 必须保持
// "unknown/delegated"（声称其他值即拒）；任何密钥形状字符串拒绝摄入。
func (o *Owner) AttachProviderExitReceipt(runID string, receipt map[string]any) (*ProviderExitLedger, error) {
	if err := requireText(runID, "run_id"); err != nil {
		return nil, err
	}
	if len(receipt) == 0 {
		return nil, fmt.Errorf("%w: receipt 必须是非空映射（Provider exit receipt v2）", ErrBadArgument)
	}
	if strOrUnknown(receipt["schema"]) != "zworkbench-provider-exit-receipt/v2" {
		return nil, fmt.Errorf("%w: receipt schema 必须为 zworkbench-provider-exit-receipt/v2", ErrBadArgument)
	}
	if strOrUnknown(receipt["provider_remote_zero_residue"]) != "unknown/delegated" {
		return nil, fmt.Errorf("%w: provider_remote_zero_residue 必须保持 'unknown/delegated'；本地/owner 证据不能声称 Provider 清场", ErrBadArgument)
	}
	if err := rejectSecretShapedAny(receipt, "receipt"); err != nil {
		return nil, err
	}

	provider := strOrUnknown(receipt["provider"])
	endpoint := strOrUnknown(receipt["endpoint"])
	accountScope := strOrUnknown(receipt["account_scope"])
	exitMode := strOrUnknown(receipt["exit_mode"])
	if exitMode == "unknown" {
		exitMode = "authorized-manual-exit"
	}
	exitStatus := strOrUnknown(receipt["exit_status"])
	if exitStatus == "unknown" {
		exitStatus = "unknown/safe-stop"
	}
	localStateFP := strOrUnknown(receipt["local_state_fingerprint"])
	if localStateFP != "unknown" && !hex64Re.MatchString(localStateFP) {
		return nil, fmt.Errorf("%w: local_state_fingerprint 必须是 64 位 hex 或 'unknown'", ErrBadArgument)
	}

	surface := toStringMap(receipt["surface_observations"])
	statuses := toStringMap(receipt["statuses"])
	unknownFields := toStringSlice(receipt["unknown_fields"])

	ts := nowUTC()
	ledgerID := newID()

	so, err := jsonString(surface)
	if err != nil {
		return nil, err
	}
	sj, err := jsonString(statuses)
	if err != nil {
		return nil, err
	}
	uj, err := jsonString(unknownFields)
	if err != nil {
		return nil, err
	}

	var out *ProviderExitLedger
	if err := o.transact(func(tx *sql.Tx) error {
		if _, err := o.runRow(tx, runID); err != nil {
			return err
		}
		if _, e := tx.Exec(`
			INSERT INTO provider_exit_ledger(
				ledger_id, run_id, provider, endpoint, account_scope,
				exit_mode, exit_status, provider_remote_zero_residue,
				surface_observations_json, statuses_json, unknown_fields_json,
				local_state_fingerprint, evidence_class, recorded_at
			) VALUES (?, ?, ?, ?, ?, ?, ?, 'unknown/delegated', ?, ?, ?, ?, 'owner-backed', ?)`,
			ledgerID, runID, provider, endpoint, accountScope, exitMode, exitStatus,
			so, sj, uj, localStateFP, ts,
		); e != nil {
			return fmt.Errorf("写入 provider_exit_ledger (owner-backed) 失败：%w", e)
		}
		if e := o.appendEventTx(tx, runID, "provider.exit.ledger.recorded", map[string]any{
			"ledger_id":                  ledgerID,
			"provider":                   provider,
			"evidence_class":             "owner-backed",
			"evidence_fingerprint":       strOrUnknown(receipt["evidence_fingerprint"]),
			"provider_remote_zero_residue": "unknown/delegated",
		}, nil); e != nil {
			return e
		}
		out = &ProviderExitLedger{
			LedgerID:                  ledgerID,
			RunID:                     runID,
			Provider:                  provider,
			Endpoint:                  endpoint,
			AccountScope:              accountScope,
			ExitMode:                  exitMode,
			ExitStatus:                exitStatus,
			ProviderRemoteZeroResidue: "unknown/delegated",
			SurfaceObservations:       surface,
			Statuses:                  statuses,
			UnknownFields:             unknownFields,
			LocalStateFingerprint:     localStateFP,
			EvidenceClass:             "owner-backed",
			RecordedAt:                ts,
		}
		return nil
	}); err != nil {
		return nil, err
	}
	return out, nil
}

// GetProviderExitLedger 按 ledger_id 读一条 provider 侧退出台账；不存在返 ErrNotFound。
func (o *Owner) GetProviderExitLedger(ledgerID string) (*ProviderExitLedger, error) {
	if err := requireText(ledgerID, "ledger_id"); err != nil {
		return nil, err
	}
	row := o.db.QueryRow(`
		SELECT ledger_id, run_id, provider, endpoint, account_scope, exit_mode,
			exit_status, provider_remote_zero_residue, surface_observations_json,
			statuses_json, unknown_fields_json, local_state_fingerprint,
			evidence_class, recorded_at
		FROM provider_exit_ledger WHERE ledger_id = ?`, ledgerID)
	rec, err := scanProviderExitLedger(row)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, fmt.Errorf("%w: provider exit ledger entry not found: %s", ErrNotFound, ledgerID)
		}
		return nil, err
	}
	return rec, nil
}

// ProviderExitLedgerForRun 返回某 run 的全部 provider 侧退出台账（按记录序）。
func (o *Owner) ProviderExitLedgerForRun(runID string) ([]*ProviderExitLedger, error) {
	if err := requireText(runID, "run_id"); err != nil {
		return nil, err
	}
	// 先验 run 存在（引用完整性），与 Python _run_row 一致。
	if err := o.transact(func(tx *sql.Tx) error {
		_, e := o.runRow(tx, runID)
		return e
	}); err != nil {
		return nil, err
	}
	rows, err := o.db.Query(`
		SELECT ledger_id, run_id, provider, endpoint, account_scope, exit_mode,
			exit_status, provider_remote_zero_residue, surface_observations_json,
			statuses_json, unknown_fields_json, local_state_fingerprint,
			evidence_class, recorded_at
		FROM provider_exit_ledger WHERE run_id = ? ORDER BY recorded_at, ledger_id`, runID)
	if err != nil {
		return nil, fmt.Errorf("查询 provider_exit_ledger 失败：%w", err)
	}
	defer rows.Close()
	var out []*ProviderExitLedger
	for rows.Next() {
		rec, e := scanProviderExitLedger(rows)
		if e != nil {
			return nil, e
		}
		out = append(out, rec)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("遍历 provider_exit_ledger 失败：%w", err)
	}
	return out, nil
}

// scanProviderExitLedger 把一行（*sql.Row 或 *sql.Rows）扫描进结构体，并反序列化
// 三个 JSON 列。传入者须实现 Scan 接口（*sql.Row / *sql.Rows 均满足）。
func scanProviderExitLedger(scanner interface {
	Scan(dest ...any) error
}) (*ProviderExitLedger, error) {
	var (
		ledgerID, runID, provider, endpoint, accountScope, exitMode, exitStatus,
		remoteResidue, soJSON, sjJSON, ujJSON, localFP, evidenceClass, recordedAt string
	)
	if err := scanner.Scan(
		&ledgerID, &runID, &provider, &endpoint, &accountScope, &exitMode,
		&exitStatus, &remoteResidue, &soJSON, &sjJSON, &ujJSON, &localFP,
		&evidenceClass, &recordedAt,
	); err != nil {
		return nil, err
	}
	rec := &ProviderExitLedger{
		LedgerID:                  ledgerID,
		RunID:                     runID,
		Provider:                  provider,
		Endpoint:                  endpoint,
		AccountScope:              accountScope,
		ExitMode:                  exitMode,
		ExitStatus:                exitStatus,
		ProviderRemoteZeroResidue: remoteResidue,
		LocalStateFingerprint:     localFP,
		EvidenceClass:             evidenceClass,
		RecordedAt:                recordedAt,
	}
	rec.SurfaceObservations = toStringMapFromJSON(soJSON)
	rec.Statuses = toStringMapFromJSON(sjJSON)
	rec.UnknownFields = toStringSliceFromJSON(ujJSON)
	return rec, nil
}

// ---- JSON 辅助 ----

func sortedKeys(m map[string]string) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

// toStringMap 把 any（map[string]any / map[string]string / JSON 字符串）规范成
// map[string]string；nil / 空 → 空 map（不返回 nil，便于落库与序列化一致）。
func toStringMap(v any) map[string]string {
	out := map[string]string{}
	switch m := v.(type) {
	case nil:
		// 空
	case map[string]string:
		out = m
	case map[string]any:
		for k, val := range m {
			out[k] = strOrUnknown(val)
		}
	case string:
		if strings.TrimSpace(m) != "" {
			var tmp map[string]string
			if err := json.Unmarshal([]byte(m), &tmp); err == nil {
				out = tmp
			}
		}
	}
	return out
}

// toStringSlice 复用 approval.go 的同名辅助（仅处理 []string / []any-of-string）。

func toStringMapFromJSON(s string) map[string]string {
	out := map[string]string{}
	if strings.TrimSpace(s) == "" {
		return out
	}
	_ = json.Unmarshal([]byte(s), &out)
	return out
}

func toStringSliceFromJSON(s string) []string {
	if strings.TrimSpace(s) == "" {
		return nil
	}
	var out []string
	_ = json.Unmarshal([]byte(s), &out)
	return out
}
