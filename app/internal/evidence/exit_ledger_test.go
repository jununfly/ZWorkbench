package evidence

import (
	"errors"
	"testing"
)

func newExitLedgerOwner(t *testing.T) *Owner {
	t.Helper()
	ow, err := Open(":memory:")
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { _ = ow.Close() })
	return ow
}

func TestRecordProviderExitLedger_UnknownDelegated(t *testing.T) {
	ow := newExitLedgerOwner(t)
	if _, err := ow.CreateRun("r1", "task", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	rec, err := ow.RecordProviderExitLedger("r1", map[string]string{"provider": "workbuddy-code", "endpoint": "https://x"})
	if err != nil {
		t.Fatalf("RecordProviderExitLedger: %v", err)
	}
	if rec.ProviderRemoteZeroResidue != "unknown/delegated" {
		t.Fatalf("remote residue 应为 unknown/delegated, 实际 %q", rec.ProviderRemoteZeroResidue)
	}
	if rec.EvidenceClass != "local-inventory" {
		t.Fatalf("evidence_class 应为 local-inventory, 实际 %q", rec.EvidenceClass)
	}
	if rec.ExitMode != "inventory-only" || rec.ExitStatus != "unknown/safe-stop" {
		t.Fatalf("exit_mode/status 不符: %q/%q", rec.ExitMode, rec.ExitStatus)
	}
	for k, v := range rec.Statuses {
		if v != "unknown" {
			t.Fatalf("statuses[%s] 应为 unknown, 实际 %q", k, v)
		}
	}
	if len(rec.UnknownFields) != len(rec.Statuses) {
		t.Fatalf("unknown_fields 长度 %d != statuses 长度 %d", len(rec.UnknownFields), len(rec.Statuses))
	}
	// get 应取回同一记录
	got, err := ow.GetProviderExitLedger(rec.LedgerID)
	if err != nil {
		t.Fatalf("GetProviderExitLedger: %v", err)
	}
	if got.Provider != "workbuddy-code" {
		t.Fatalf("provider 不符: %q", got.Provider)
	}
}

func TestRecordProviderExitLedger_RunNotFound(t *testing.T) {
	ow := newExitLedgerOwner(t)
	if _, err := ow.RecordProviderExitLedger("nope", map[string]string{"provider": "p"}); !errors.Is(err, ErrRunNotFound) {
		t.Fatalf("缺失 run 应拒 ErrRunNotFound, 实际: %v", err)
	}
}

func TestRecordProviderExitLedger_RejectsCredentials(t *testing.T) {
	ow := newExitLedgerOwner(t)
	if _, err := ow.CreateRun("r1", "task", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	// 含 api_key 真值 → 拒
	if _, err := ow.RecordProviderExitLedger("r1", map[string]string{"provider": "p", "api_key": "ak-live-123"}); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("含 api_key 真值应拒 ErrBadArgument, 实际: %v", err)
	}
	// 值呈 ak- 形状 → 拒
	if _, err := ow.RecordProviderExitLedger("r1", map[string]string{"provider": "ak-phony"}); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("值呈 ak- 形状应拒 ErrBadArgument, 实际: %v", err)
	}
}

func TestRecordProviderExitLedgerOnce_Idempotent(t *testing.T) {
	ow := newExitLedgerOwner(t)
	if _, err := ow.CreateRun("r1", "task", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	a, err := ow.RecordProviderExitLedgerOnce("r1", map[string]string{"provider": "p"})
	if err != nil {
		t.Fatalf("once#1: %v", err)
	}
	b, err := ow.RecordProviderExitLedgerOnce("r1", map[string]string{"provider": "p2"})
	if err != nil {
		t.Fatalf("once#2: %v", err)
	}
	if a.LedgerID != b.LedgerID {
		t.Fatalf("once 应幂等返回同一条: %s vs %s", a.LedgerID, b.LedgerID)
	}
	all, err := ow.ProviderExitLedgerForRun("r1")
	if err != nil {
		t.Fatalf("ForRun: %v", err)
	}
	if len(all) != 1 {
		t.Fatalf("应只 1 条, 实际 %d", len(all))
	}
}

func TestAttachProviderExitReceipt_V2(t *testing.T) {
	ow := newExitLedgerOwner(t)
	if _, err := ow.CreateRun("r1", "task", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	if _, err := ow.RecordProviderExitLedger("r1", map[string]string{"provider": "p"}); err != nil {
		t.Fatalf("record: %v", err)
	}
	receipt := map[string]any{
		"schema":                       "zworkbench-provider-exit-receipt/v2",
		"provider":                     "p",
		"endpoint":                     "https://x",
		"account_scope":                "acct-1",
		"exit_mode":                    "authorized-manual-exit",
		"exit_status":                  "clean/safe-stop",
		"provider_remote_zero_residue": "unknown/delegated",
		"local_state_fingerprint":      "unknown",
		"evidence_fingerprint":         "fp-1",
		"surface_observations":         map[string]any{"task_or_run": "clean"},
		"statuses":                     map[string]any{"coding_data": "clean"},
		"unknown_fields":               []any{"billing"},
	}
	rec, err := ow.AttachProviderExitReceipt("r1", receipt)
	if err != nil {
		t.Fatalf("AttachProviderExitReceipt: %v", err)
	}
	if rec.EvidenceClass != "owner-backed" {
		t.Fatalf("evidence_class 应为 owner-backed, 实际 %q", rec.EvidenceClass)
	}
	if rec.ProviderRemoteZeroResidue != "unknown/delegated" {
		t.Fatalf("remote residue 必须仍为 unknown/delegated, 实际 %q", rec.ProviderRemoteZeroResidue)
	}
	if rec.AccountScope != "acct-1" {
		t.Fatalf("account_scope 不符: %q", rec.AccountScope)
	}
	if rec.Statuses["coding_data"] != "clean" {
		t.Fatalf("statuses 未被 receipt 覆盖: %q", rec.Statuses["coding_data"])
	}
}

func TestAttachProviderExitReceipt_FailClosed(t *testing.T) {
	ow := newExitLedgerOwner(t)
	if _, err := ow.CreateRun("r1", "task", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	base := func() map[string]any {
		return map[string]any{
			"schema":                       "zworkbench-provider-exit-receipt/v2",
			"provider_remote_zero_residue": "unknown/delegated",
		}
	}
	// 非 v2 schema
	if _, err := ow.AttachProviderExitReceipt("r1", map[string]any{"schema": "v1"}); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("非 v2 schema应拒 ErrBadArgument, 实际: %v", err)
	}
	// 声称 Provider 清场 → 拒
	bad := base()
	bad["provider_remote_zero_residue"] = "verified-zero"
	if _, err := ow.AttachProviderExitReceipt("r1", bad); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("声称 Provider 清场应拒 ErrBadArgument, 实际: %v", err)
	}
	// 密钥形状值 → 拒
	secret := base()
	secret["provider"] = "p"
	secret["token"] = "ark-secret-value"
	if _, err := ow.AttachProviderExitReceipt("r1", secret); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("含密钥形状值应拒 ErrBadArgument, 实际: %v", err)
	}
}

func TestGetProviderExitLedger_NotFound(t *testing.T) {
	ow := newExitLedgerOwner(t)
	if _, err := ow.GetProviderExitLedger("missing"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("未知 ledger 应拒 ErrNotFound, 实际: %v", err)
	}
}

// TestProviderExitLedgerForRun_MixedClasses 校验同一 run 上的两类证据
// （local-inventory 默认条目 + owner-backed 回执条目）都被 ForRun 取回。
//
// 这里**不**断言二者先后：nowUTC() 是 RFC3339 秒级精度，同一秒内落的两条记录
// recorded_at 完全相同，ORDER BY recorded_at, ledger_id 会退化成随机 UUID 的
// 字典序——那是「确定性但无语义」的兜底排序，不是业务先后。原
// TestProviderExitLedgerForRun_Order 正是在这条退化路径上断言顺序，约 50% 概率
// 抖红（1-4-4 跑 check-go.sh 时发现，与本次改动无关）。时间序契约改由下一条
// 用明确不同的 recorded_at 覆盖。
func TestProviderExitLedgerForRun_MixedClasses(t *testing.T) {
	ow := newExitLedgerOwner(t)
	runID := "el-mixed-run"
	if _, err := ow.CreateRun(runID, "task", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	if _, err := ow.RecordProviderExitLedger(runID, map[string]string{"provider": "p"}); err != nil {
		t.Fatalf("record: %v", err)
	}
	receipt := map[string]any{
		"schema":                       "zworkbench-provider-exit-receipt/v2",
		"provider_remote_zero_residue": "unknown/delegated",
	}
	if _, err := ow.AttachProviderExitReceipt(runID, receipt); err != nil {
		t.Fatalf("attach: %v", err)
	}
	all, err := ow.ProviderExitLedgerForRun(runID)
	if err != nil {
		t.Fatalf("ForRun: %v", err)
	}
	if len(all) != 2 {
		t.Fatalf("应有 2 条(local-inventory + owner-backed), 实际 %d", len(all))
	}
	classes := map[string]bool{}
	for _, rec := range all {
		if rec.RunID != runID {
			t.Fatalf("ForRun 返回了别的 run: %s", rec.RunID)
		}
		classes[rec.EvidenceClass] = true
	}
	if !classes["local-inventory"] || !classes["owner-backed"] {
		t.Fatalf("两类证据缺一: %+v", classes)
	}
}

// TestRecordRemoteProviderExitLedger_HonestCaliber 校验真远程执行后的诚实口径：
// provider/endpoint 记真实值，但 provider_remote_zero_residue 仍 unknown
// （本机无法验证远端残留）。这是 ADR 0020 前提 4 的收窄——不默认升级为已清场。
func TestRecordRemoteProviderExitLedger_HonestCaliber(t *testing.T) {
	ow := newExitLedgerOwner(t)
	if _, err := ow.CreateRun("r1", "task", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	rec, err := ow.RecordRemoteProviderExitLedger("r1", "192.168.1.10:22", "")
	if err != nil {
		t.Fatalf("RecordRemoteProviderExitLedger: %v", err)
	}
	if rec.Provider != "ssh" {
		t.Fatalf("provider 应为 ssh, 实际 %q", rec.Provider)
	}
	if rec.Endpoint != "192.168.1.10:22" {
		t.Fatalf("endpoint 应为真实 host:port, 实际 %q", rec.Endpoint)
	}
	// 关键：清场结论仍 unknown，不声称已清场。
	if rec.ProviderRemoteZeroResidue != "unknown" {
		t.Fatalf("provider_remote_zero_residue 应为 unknown, 实际 %q", rec.ProviderRemoteZeroResidue)
	}
	if rec.EvidenceClass != "remote-provider" {
		t.Fatalf("evidence_class 应为 remote-provider, 实际 %q", rec.EvidenceClass)
	}
	// 与 loopback 条目必须可区分：同一 run 上两种证据并存。
	if _, err := ow.RecordProviderExitLedger("r1", map[string]string{"provider": "workbuddy-code"}); err != nil {
		t.Fatalf("record loopback: %v", err)
	}
	all, err := ow.ProviderExitLedgerForRun("r1")
	if err != nil {
		t.Fatalf("ForRun: %v", err)
	}
	if len(all) != 2 {
		t.Fatalf("应有 2 条(remote-provider + local-inventory), 实际 %d", len(all))
	}
	classes := map[string]bool{}
	for _, e := range all {
		classes[e.EvidenceClass] = true
	}
	if !classes["remote-provider"] || !classes["local-inventory"] {
		t.Fatalf("两类证据缺一: %+v", classes)
	}
}

// TestRecordRemoteProviderExitLedger_RequiresEndpoint 校验真实远程执行必须有真
// 实 endpoint；空 endpoint 显式拒绝，不能把一次真实远程执行记成 unknown 端点。
func TestRecordRemoteProviderExitLedger_RequiresEndpoint(t *testing.T) {
	ow := newExitLedgerOwner(t)
	if _, err := ow.CreateRun("r1", "task", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	if _, err := ow.RecordRemoteProviderExitLedger("r1", "", ""); !errors.Is(err, ErrBadArgument) {
		t.Fatalf("空 endpoint 应拒 ErrBadArgument, 实际: %v", err)
	}
}

// TestRecordRemoteProviderExitLedgerOnce_Idempotent 校验幂等：run 已有
// remote-provider 条目则直接返回首条，不追加新 entry。
func TestRecordRemoteProviderExitLedgerOnce_Idempotent(t *testing.T) {
	ow := newExitLedgerOwner(t)
	if _, err := ow.CreateRun("r1", "task", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	a, err := ow.RecordRemoteProviderExitLedgerOnce("r1", "10.0.0.1:2222", "")
	if err != nil {
		t.Fatalf("once#1: %v", err)
	}
	b, err := ow.RecordRemoteProviderExitLedgerOnce("r1", "10.0.0.2:22", "")
	if err != nil {
		t.Fatalf("once#2: %v", err)
	}
	if a.LedgerID != b.LedgerID {
		t.Fatalf("once 应幂等返回同一条: %s vs %s", a.LedgerID, b.LedgerID)
	}
	all, err := ow.ProviderExitLedgerForRun("r1")
	if err != nil {
		t.Fatalf("ForRun: %v", err)
	}
	if len(all) != 1 {
		t.Fatalf("应只 1 条, 实际 %d", len(all))
	}
}

// TestProviderExitLedgerForRun_Chronological 用两条 recorded_at 明确不同的记录
// 验证 ForRun 的时间序契约（这是 ORDER BY 唯一有业务语义的一层）。
func TestProviderExitLedgerForRun_Chronological(t *testing.T) {
	ow := newExitLedgerOwner(t)
	runID := "el-chrono-run"
	if _, err := ow.CreateRun(runID, "task", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	for i, ts := range []string{"2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"} {
		if _, err := ow.DB().Exec(
			`INSERT INTO provider_exit_ledger(
				ledger_id, run_id, provider, endpoint, account_scope,
				exit_mode, exit_status, provider_remote_zero_residue,
				surface_observations_json, statuses_json, unknown_fields_json,
				local_state_fingerprint, evidence_class, recorded_at
			 ) VALUES (?, ?, 'p', 'https://x', 'unknown', 'inventory-only',
				'unknown/safe-stop', 'unknown/delegated', '{}', '{}', '[]', 'unknown',
				'local-inventory', ?)`,
			"el-chrono-"+string(rune('a'+i)), runID, ts); err != nil {
			t.Fatalf("插入 ledger %d: %v", i, err)
		}
	}
	all, err := ow.ProviderExitLedgerForRun(runID)
	if err != nil {
		t.Fatalf("ForRun: %v", err)
	}
	if len(all) != 2 {
		t.Fatalf("应有 2 条, 实际 %d", len(all))
	}
	if all[0].LedgerID != "el-chrono-b" || all[1].LedgerID != "el-chrono-a" {
		t.Fatalf("未按 recorded_at 升序: %q, %q", all[0].LedgerID, all[1].LedgerID)
	}
}
