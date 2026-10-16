package evidence

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

// openFileOwner 打开一个临时文件库（WAL 模式），用于 backup/restore 测试。
func openFileOwner(t *testing.T) *Owner {
	t.Helper()
	dir := t.TempDir()
	ow, err := Open(filepath.Join(dir, "evidence.db"))
	if err != nil {
		t.Fatalf("Open 文件库失败: %v", err)
	}
	t.Cleanup(func() { _ = ow.Close() })
	return ow
}

// seedOwner 写入一组合成数据（run + event + effect + approval）。
func seedOwner(t *testing.T, ow *Owner) {
	t.Helper()
	if _, err := ow.CreateRun("r1", "task", map[string]any{"k": "v"}, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}
	if _, err := ow.RecordEvent("r1", "run.started", map[string]any{"x": 1}, EvidenceSourceNative); err != nil {
		t.Fatalf("RecordEvent: %v", err)
	}
	if _, err := ow.ClaimEffect("r1", "op-1", "act", "res", "idem-1", "idempotent", "", 3, nil); err != nil {
		t.Fatalf("ClaimEffect: %v", err)
	}
	// approval 写一条，校验 approvals 表也在快照/备份范围内。
	if _, err := ow.RequestApproval("r1", "op-a", "act", "res", "idem-a", "reason"); err != nil {
		t.Fatalf("RequestApproval: %v", err)
	}
}

func TestBackupRestoreRoundTrip(t *testing.T) {
	ow := openFileOwner(t)
	seedOwner(t, ow)

	backupDir := filepath.Join(t.TempDir(), "backup")
	manifest, err := ow.Backup(backupDir)
	if err != nil {
		t.Fatalf("Backup: %v", err)
	}
	// 三件套齐全。
	for _, f := range []string{backupManifestFile, backupDBFilename, backupStateFile} {
		if _, serr := os.Stat(filepath.Join(backupDir, f)); serr != nil {
			t.Fatalf("备份缺少文件 %s: %v", f, serr)
		}
	}
	if manifest.SchemaVersion != SchemaVersion {
		t.Fatalf("manifest.schema_version=%d 期望 %d", manifest.SchemaVersion, SchemaVersion)
	}
	if manifest.DatabaseFilename != backupDBFilename || manifest.StateFilename != backupStateFile {
		t.Fatalf("manifest 文件名不符: %+v", manifest)
	}
	if !manifest.IntegrityCheck.OK {
		t.Fatalf("manifest integrity 非 ok: %+v", manifest.IntegrityCheck)
	}
	if manifest.Counts["runs"] != 1 || manifest.Counts["effects"] != 1 || manifest.Counts["approvals"] != 1 || manifest.Counts["events"] < 1 {
		t.Fatalf("manifest counts 不符: %+v", manifest.Counts)
	}
	if manifest.StateDigest == "" || manifest.DatabaseSHA256 == "" {
		t.Fatalf("manifest digest/sha 为空")
	}

	// 备份后再写一个 run，验证 restore 是时间点恢复（不含 r2）。
	if _, err := ow.CreateRun("r2", "task2", nil, nil); err != nil {
		t.Fatalf("CreateRun r2: %v", err)
	}

	target := filepath.Join(t.TempDir(), "restored.db")
	res, err := Restore(backupDir, target, false)
	if err != nil {
		t.Fatalf("Restore: %v", err)
	}
	if !res.IntegrityCheck.OK {
		t.Fatalf("restore integrity 非 ok: %+v", res.IntegrityCheck)
	}
	if res.StateDigest != manifest.StateDigest {
		t.Fatalf("restore state_digest=%s 期望 %s", res.StateDigest, manifest.StateDigest)
	}

	restored, err := Open(target)
	if err != nil {
		t.Fatalf("Open 恢复库: %v", err)
	}
	defer restored.Close()
	runs, err := restored.ListRuns()
	if err != nil {
		t.Fatalf("ListRuns: %v", err)
	}
	if len(runs) != 1 || runs[0].RunID != "r1" {
		t.Fatalf("恢复库 run 集合不符: 期望仅 r1, 实际 %d 条", len(runs))
	}
}

func TestBackupDirNotEmpty(t *testing.T) {
	ow := openFileOwner(t)
	seedOwner(t, ow)
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "stray.txt"), []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := ow.Backup(dir); !errors.Is(err, ErrBackupDirNotEmpty) {
		t.Fatalf("目录非空应拒 ErrBackupDirNotEmpty, 实际: %v", err)
	}
}

func TestRestoreTargetExists(t *testing.T) {
	ow := openFileOwner(t)
	seedOwner(t, ow)
	backupDir := filepath.Join(t.TempDir(), "backup")
	if _, err := ow.Backup(backupDir); err != nil {
		t.Fatalf("Backup: %v", err)
	}
	// 目标文件已存在，未显式 replace → 拒绝。
	target := filepath.Join(t.TempDir(), "exists.db")
	if err := os.WriteFile(target, []byte("old"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Restore(backupDir, target, false); !errors.Is(err, ErrRestoreTargetExists) {
		t.Fatalf("目标存在未 replace 应拒 ErrRestoreTargetExists, 实际: %v", err)
	}
	// 显式 replace → 成功，且恢复的是备份内容。
	if _, err := Restore(backupDir, target, true); err != nil {
		t.Fatalf("replace 恢复应成功, 实际: %v", err)
	}
	restored, err := Open(target)
	if err != nil {
		t.Fatalf("Open 恢复库: %v", err)
	}
	defer restored.Close()
	runs, _ := restored.ListRuns()
	if len(runs) != 1 {
		t.Fatalf("replace 恢复后 run 数=%d 期望 1", len(runs))
	}
}

func TestRestoreDigestMismatch(t *testing.T) {
	ow := openFileOwner(t)
	seedOwner(t, ow)
	backupDir := filepath.Join(t.TempDir(), "backup")
	if _, err := ow.Backup(backupDir); err != nil {
		t.Fatalf("Backup: %v", err)
	}
	// 篡改 state.json 的 runs 内容 → digest 必失配。
	statePath := filepath.Join(backupDir, backupStateFile)
	b, err := os.ReadFile(statePath)
	if err != nil {
		t.Fatal(err)
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatal(err)
	}
	runs := m["runs"].([]any)
	runs[0].(map[string]any)["status"] = "tampered"
	out, _ := json.MarshalIndent(m, "", "  ")
	if err := os.WriteFile(statePath, append(out, '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Restore(backupDir, filepath.Join(t.TempDir(), "x.db"), false); !errors.Is(err, ErrBackupDigest) {
		t.Fatalf("篡改 state.json 应拒 ErrBackupDigest, 实际: %v", err)
	}
}

func TestRestoreSchemaMismatch(t *testing.T) {
	ow := openFileOwner(t)
	seedOwner(t, ow)
	backupDir := filepath.Join(t.TempDir(), "backup")
	if _, err := ow.Backup(backupDir); err != nil {
		t.Fatalf("Backup: %v", err)
	}
	manifestPath := filepath.Join(backupDir, backupManifestFile)
	b, _ := os.ReadFile(manifestPath)
	var m map[string]any
	_ = json.Unmarshal(b, &m)
	m["schema_version"] = SchemaVersion + 99
	out, _ := json.MarshalIndent(m, "", "  ")
	_ = os.WriteFile(manifestPath, append(out, '\n'), 0o600)
	if _, err := Restore(backupDir, filepath.Join(t.TempDir(), "x.db"), false); !errors.Is(err, ErrBackupSchema) {
		t.Fatalf("schema 版本不符应拒 ErrBackupSchema, 实际: %v", err)
	}
}

func TestRestoreMissingFiles(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, backupManifestFile), []byte("{}"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Restore(dir, filepath.Join(t.TempDir(), "x.db"), false); !errors.Is(err, ErrBackupMissing) {
		t.Fatalf("缺文件应拒 ErrBackupMissing, 实际: %v", err)
	}
}

func TestBackupCorruptDBRejected(t *testing.T) {
	ow := openFileOwner(t)
	seedOwner(t, ow)
	backupDir := filepath.Join(t.TempDir(), "backup")
	if _, err := ow.Backup(backupDir); err != nil {
		t.Fatalf("Backup: %v", err)
	}
	// 尾部追加垃圾字节破坏库 → sha256 失配（先于 integrity）。
	dbPath := filepath.Join(backupDir, backupDBFilename)
	f, err := os.OpenFile(dbPath, os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = f.Write([]byte("GARBAGE"))
	_ = f.Close()
	if _, err := Restore(backupDir, filepath.Join(t.TempDir(), "x.db"), false); !errors.Is(err, ErrBackupDigest) {
		t.Fatalf("破坏库应拒 ErrBackupDigest, 实际: %v", err)
	}
}
