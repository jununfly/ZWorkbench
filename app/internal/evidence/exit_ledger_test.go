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
		"schema":                     "zworkbench-provider-exit-receipt/v2",
		"provider":                   "p",
		"endpoint":                   "https://x",
		"account_scope":              "acct-1",
		"exit_mode":                  "authorized-manual-exit",
		"exit_status":                "clean/safe-stop",
		"provider_remote_zero_residue": "unknown/delegated",
		"local_state_fingerprint":    "unknown",
		"evidence_fingerprint":       "fp-1",
		"surface_observations":       map[string]any{"task_or_run": "clean"},
		"statuses":                   map[string]any{"coding_data": "clean"},
		"unknown_fields":             []any{"billing"},
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

func TestProviderExitLedgerForRun_Order(t *testing.T) {
	ow := newExitLedgerOwner(t)
	if _, err := ow.CreateRun("r1", "task", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	if _, err := ow.RecordProviderExitLedger("r1", map[string]string{"provider": "p"}); err != nil {
		t.Fatalf("record: %v", err)
	}
	receipt := map[string]any{
		"schema":                       "zworkbench-provider-exit-receipt/v2",
		"provider_remote_zero_residue": "unknown/delegated",
	}
	if _, err := ow.AttachProviderExitReceipt("r1", receipt); err != nil {
		t.Fatalf("attach: %v", err)
	}
	all, err := ow.ProviderExitLedgerForRun("r1")
	if err != nil {
		t.Fatalf("ForRun: %v", err)
	}
	if len(all) != 2 {
		t.Fatalf("应有 2 条(local-inventory + owner-backed), 实际 %d", len(all))
	}
	if all[0].EvidenceClass != "local-inventory" || all[1].EvidenceClass != "owner-backed" {
		t.Fatalf("顺序不对: %q, %q", all[0].EvidenceClass, all[1].EvidenceClass)
	}
}
