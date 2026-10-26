// exit_ledger.go 是 Python composition.py 的 provider_exit_ledger 子系统
// ADR 0016 (formerly roadmap 1-6-6 / 1-4-3) 的 Go B2-narrow 移植。
//
// 核心不变式（fail-closed，逐字对齐 Python）：
//   - provider_remote_zero_residue 默认 = "unknown/delegated"。本地/owner
//     证据绝不能升级成「Provider 已清场」的证明。attach_receipt 若 receipt
//     声称其他值即拒。
//   - **唯一例外**：真远程执行（ssh 拉起远端进程）后，事实字段 provider / endpoint
//     必须记**真实值**（provider="ssh"、endpoint=真实 host:port），但
//     provider_remote_zero_residue **仍**记 "unknown" —— 远端进程跑在另一台机器上，
//     本机无法验证残留是否清除，绝不声称「已清场 / 零残留」。这是 ADR 0020 前提 4
//     的诚实化收窄（见 RecordRemoteProviderExitLedger）。
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

// RecordRemoteProviderExitLedger 记录一次**真实远程执行**的 provider 侧退出台账。
//
// 与 RecordProviderExitLedger（loopback 默认全部 unknown/delegated）的关键区别：
// 真远程执行**确实**经过了一个外部 provider（ssh 拉起的远端机器），所以
//   - provider 记为真实值 "ssh"（不空不 delegated）；
//   - endpoint 记为**真实** host:port（不是 unknown）；
//   - 但 provider_remote_zero_residue **仍**记 "unknown" —— 远端进程跑在另一台机器上，
//     本机无法验证其残留是否清除，绝不声称「已清场 / 零残留」。
//
// 这就是 ADR 0020 前提 4 的诚实化收窄：loopback 默认口径硬编码 unknown/delegated
// （因为根本没有真实远程 provider）；真远程执行后，provider / endpoint 这两个
// 事实字段必须如实填真值，但「清场」这个无法在本机复核的结论仍保持 unknown，
// 不默认升级。endpoint 为空时显式拒绝——不把一次真实远程执行记录成 unknown 端点。
func (o *Owner) RecordRemoteProviderExitLedger(runID, endpoint, accountScope string) (*ProviderExitLedger, error) {
	if err := requireText(runID, "run_id"); err != nil {
		return nil, err
	}
	ep := strings.TrimSpace(endpoint)
	as := strOrUnknown(accountScope)
	if ep == "" {
		return nil, fmt.Errorf("%w: 真实远程执行必须有 endpoint（host:port），不能记成 unknown", ErrBadArgument)
	}

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
			) VALUES (?, ?, 'ssh', ?, ?, 'remote-ssh-execution', 'unknown/safe-stop',
				'unknown', ?, ?, ?, 'unknown', 'remote-provider', ?)`,
			ledgerID, runID, ep, as, so, sj, uj, ts,
		); e != nil {
			return fmt.Errorf("写入 provider_exit_ledger (remote) 失败：%w", e)
		}
		if e := o.appendEventTx(tx, runID, "provider.exit.ledger.recorded", map[string]any{
			"ledger_id":                   ledgerID,
			"provider":                    "ssh",
			"endpoint":                    ep,
			"caliber":                     "remote-engaged/zero-residue-unknown",
			"provider_remote_zero_residue": "unknown",
		}, nil); e != nil {
			return e
		}
		out = &ProviderExitLedger{
			LedgerID:                  ledgerID,
			RunID:                     runID,
			Provider:                  "ssh",
			Endpoint:                  ep,
			AccountScope:              as,
			ExitMode:                  "remote-ssh-execution",
			ExitStatus:                "unknown/safe-stop",
			ProviderRemoteZeroResidue: "unknown",
			SurfaceObservations:       surface,
			Statuses:                  statuses,
			UnknownFields:             unknownFields,
			LocalStateFingerprint:     "unknown",
			EvidenceClass:             "remote-provider",
			RecordedAt:                ts,
		}
		return nil
	}); err != nil {
		return nil, err
	}
	return out, nil
}

// RecordRemoteProviderExitLedgerOnce 每 run 至多记一条真实远程 provider 退出台账。
// 幂等：run 已有 remote-provider 类条目则直接返回首条，不追加（与
// RecordProviderExitLedgerOnce 同口径，保证 harness / adapter 层只产生一条）。
func (o *Owner) RecordRemoteProviderExitLedgerOnce(runID, endpoint, accountScope string) (*ProviderExitLedger, error) {
	existing, err := o.ProviderExitLedgerForRun(runID)
	if err != nil {
		return nil, err
	}
	for _, e := range existing {
		if e.EvidenceClass == "remote-provider" {
			return e, nil
		}
	}
	return o.RecordRemoteProviderExitLedger(runID, endpoint, accountScope)
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
