package evidence

import (
	"database/sql"
	"path/filepath"
	"testing"
)

// writeV1DB 造一个 v1 旧库（runs 无 repo/branch/environment 列，user_version=1），
// 用于验证 Open 的 v1→v2 迁移。
func writeV1DB(t *testing.T, path string) {
	t.Helper()
	db, err := sql.Open("sqlite", "file:"+path)
	if err != nil {
		t.Fatalf("开 v1 测试库失败：%v", err)
	}
	defer db.Close()
	ddl := `
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    input_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);`
	if _, err := db.Exec(ddl); err != nil {
		t.Fatalf("建 v1 runs 表失败：%v", err)
	}
	if _, err := db.Exec(`INSERT INTO runs(run_id, task_type, input_json, metadata_json, status, created_at, updated_at)
		VALUES ('old1', 't', '{}', '{}', 'created', '2020-01-01T00:00:00Z', '2020-01-01T00:00:00Z')`); err != nil {
		t.Fatalf("插 v1 行失败：%v", err)
	}
	if _, err := db.Exec("PRAGMA user_version = 1"); err != nil {
		t.Fatalf("设 v1 user_version 失败：%v", err)
	}
}

func TestOpenMigratesV1ToV2(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "evidence.db")
	writeV1DB(t, dbPath)

	// Open 应自动迁移到 v2 且能写入新列。
	ow, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open 迁移失败：%v", err)
	}
	defer ow.Close()

	// 旧行仍可读，且新列默认为空串。
	old, err := ow.GetRun("old1")
	if err != nil {
		t.Fatalf("读 v1 旧行失败：%v", err)
	}
	if old.Repo != "" || old.Branch != "" || old.Environment != "" {
		t.Fatalf("v1 旧行新列应为空，实际 repo=%q branch=%q env=%q", old.Repo, old.Branch, old.Environment)
	}

	// 经迁移后的库可写入带上下文维度的新 run。
	r, err := ow.CreateRunWithContext("r-new", "coding", nil, nil, "ZWorkbench", "main", "local")
	if err != nil {
		t.Fatalf("迁移后 CreateRunWithContext 失败：%v", err)
	}
	if r.Repo != "ZWorkbench" || r.Branch != "main" || r.Environment != "local" {
		t.Fatalf("新 run 上下文维度未落库：%#v", r)
	}
}

func TestFreshDBIsV2(t *testing.T) {
	ow, err := Open(":memory:")
	if err != nil {
		t.Fatalf("Open 内存库失败：%v", err)
	}
	defer ow.Close()
	r, err := ow.CreateRunWithContext("r1", "t", nil, nil, "repoA", "dev", "container")
	if err != nil {
		t.Fatalf("CreateRunWithContext 失败：%v", err)
	}
	if r.Repo != "repoA" {
		t.Fatalf("fresh v2 库 repo 不符：%q", r.Repo)
	}
}
