package evidence

import (
	"crypto/sha256"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

// 备份文件名约定（与 Python composition.py 的 backup 三件套对齐，仅把
// composition.sqlite3 改名为 evidence.sqlite3 以贴合本包命名）。
const (
	backupDBFilename    = "evidence.sqlite3"
	backupManifestFile  = "manifest.json"
	backupStateFile     = "state.json"
	backupMetadataState = "state_digest"
	backupMetadataAt    = "exported_at"
)

// backupRequiredTables 是 Go B2-narrow 的权威表集合（6 张核心表）。
// 必须随 schema 常量保持同步；任何不属于本集合的用户表都是「第二份规范状态」，禁止。
var backupRequiredTables = []string{
	"runs", "approvals", "effects", "effect_attempts", "declared_exposure", "events",
}

// 哨兵错误（fail-closed 语义，便于调用方按错误类型分流）。
var (
	ErrBackupDirNotEmpty   = errors.New("backup destination is not empty")
	ErrBackupMissing       = errors.New("backup missing required file (manifest.json / evidence.sqlite3 / state.json)")
	ErrBackupSchema        = errors.New("unsupported evidence backup schema version")
	ErrBackupDigest        = errors.New("backup digest mismatch")
	ErrBackupIntegrity     = errors.New("backup database integrity check failed")
	ErrBackupCorrupt       = errors.New("backup database state does not match state.json")
	ErrRestoreTargetExists = errors.New("restore target exists; pass replace=true explicitly")
)

// Snapshot 是 owner 全部规范状态的确定性投影（对齐 Python _snapshot_from_connection）。
// 字段顺序固定，内部 map 由 json.Marshal 自动按 key 排序 → canonical JSON 可复现。
type Snapshot struct {
	SchemaVersion    int              `json:"schema_version"`
	Runs             []map[string]any `json:"runs"`
	Approvals        []map[string]any `json:"approvals"`
	Effects          []map[string]any `json:"effects"`
	EffectAttempts   []map[string]any `json:"effect_attempts"`
	DeclaredExposure []map[string]any `json:"declared_exposure"`
	Events           []map[string]any `json:"events"`
}

// BackupManifest 是备份目录的清单（对齐 Python backup() 返回的 manifest）。
type BackupManifest struct {
	SchemaVersion    int            `json:"schema_version"`
	CreatedAt        string         `json:"created_at"`
	DatabaseFilename string         `json:"database_filename"`
	DatabaseSHA256   string         `json:"database_sha256"`
	StateFilename    string         `json:"state_filename"`
	StateDigest      string         `json:"state_digest"`
	Counts           map[string]int `json:"counts"`
	IntegrityCheck   IntegrityInfo  `json:"integrity_check"`
}

// IntegrityInfo 是 PRAGMA integrity_check 的结果。
type IntegrityInfo struct {
	OK             bool   `json:"ok"`
	Reason         string `json:"reason,omitempty"`
	IntegrityCheck string `json:"integrity_check,omitempty"`
	UserVersion    int    `json:"user_version,omitempty"`
}

// RestoreResult 是 restore 的回执（对齐 Python restore() 返回值）。
type RestoreResult struct {
	TargetDatabase string       `json:"target_database"`
	DatabaseSHA256 string       `json:"database_sha256"`
	StateDigest    string       `json:"state_digest"`
	IntegrityCheck IntegrityInfo `json:"integrity_check"`
}

// Snapshot 读取 owner 全部规范状态（对外投影，供审计/导出/identity-chain 复用）。
func (o *Owner) Snapshot() (*Snapshot, error) {
	return snapshotFromDB(o.db)
}

// Backup 创建自校验备份目录（三件套）。目标目录必须为空，否则 fail-closed。
func (o *Owner) Backup(destination string) (*BackupManifest, error) {
	destPath, err := filepath.Abs(destination)
	if err != nil {
		return nil, fmt.Errorf("解析备份目标失败：%w", err)
	}
	if fi, serr := os.Stat(destPath); serr == nil {
		if !fi.IsDir() {
			return nil, fmt.Errorf("%w: 目标已存在且非目录 %s", ErrBackupDirNotEmpty, destPath)
		}
		entries, rerr := os.ReadDir(destPath)
		if rerr != nil {
			return nil, fmt.Errorf("读取备份目标失败：%w", rerr)
		}
		if len(entries) > 0 {
			return nil, fmt.Errorf("%w: %s", ErrBackupDirNotEmpty, destPath)
		}
	} else if !os.IsNotExist(serr) {
		return nil, fmt.Errorf("检查备份目标失败：%w", serr)
	}
	if err := os.MkdirAll(destPath, 0o700); err != nil {
		return nil, fmt.Errorf("创建备份目录失败：%w", err)
	}

	// 先把已提交数据落进主库（WAL 可能还持有未 checkpoint 的页）。
	if _, err := o.db.Exec("PRAGMA wal_checkpoint(FULL)"); err != nil {
		return nil, fmt.Errorf("wal_checkpoint 失败：%w", err)
	}

	// 在线备份等价物：VACUUM INTO 产出独立单文件库（无 WAL 依赖）。
	dbPath := filepath.Join(destPath, backupDBFilename)
	escaped := strings.ReplaceAll(dbPath, "'", "''")
	if _, err := o.db.Exec("VACUUM INTO '" + escaped + "'"); err != nil {
		return nil, fmt.Errorf("vacuum into 备份失败：%w", err)
	}

	integrity := checkIntegrity(dbPath)
	if !integrity.OK {
		return nil, fmt.Errorf("%w: %s", ErrBackupIntegrity, integrity.Reason)
	}

	snap, err := snapshotFromDB(o.db)
	if err != nil {
		return nil, fmt.Errorf("快照 owner 状态失败：%w", err)
	}
	stateDigest := digestOf(snap)

	statePayload := map[string]any{
		"schema_version":    SchemaVersion,
		"runs":              snap.Runs,
		"approvals":         snap.Approvals,
		"effects":           snap.Effects,
		"effect_attempts":   snap.EffectAttempts,
		"declared_exposure": snap.DeclaredExposure,
		"events":            snap.Events,
		backupMetadataAt:    nowUTC(),
		backupMetadataState: stateDigest,
	}
	if err := atomicWriteJSON(filepath.Join(destPath, backupStateFile), statePayload); err != nil {
		return nil, fmt.Errorf("写 state.json 失败：%w", err)
	}

	dbSHA, err := fileSHA256(dbPath)
	if err != nil {
		return nil, fmt.Errorf("计算备份库 sha256 失败：%w", err)
	}
	counts := map[string]int{
		"runs":             len(snap.Runs),
		"approvals":        len(snap.Approvals),
		"effects":          len(snap.Effects),
		"effect_attempts":  len(snap.EffectAttempts),
		"declared_exposure": len(snap.DeclaredExposure),
		"events":           len(snap.Events),
	}
	manifest := &BackupManifest{
		SchemaVersion:    SchemaVersion,
		CreatedAt:        nowUTC(),
		DatabaseFilename: backupDBFilename,
		DatabaseSHA256:   dbSHA,
		StateFilename:    backupStateFile,
		StateDigest:      stateDigest,
		Counts:           counts,
		IntegrityCheck:   integrity,
	}
	if err := atomicWriteJSON(filepath.Join(destPath, backupManifestFile), manifest); err != nil {
		return nil, fmt.Errorf("写 manifest.json 失败：%w", err)
	}
	return manifest, nil
}

// Restore 校验并恢复一个备份到目标库文件（目标存在需显式 replace）。
// 恢复是原子操作：先拷到目标目录内的临时文件，再 os.Rename 替换。
func Restore(backupDir, targetDB string, replace bool) (*RestoreResult, error) {
	backupPath, err := filepath.Abs(backupDir)
	if err != nil {
		return nil, fmt.Errorf("解析备份目录失败：%w", err)
	}
	targetPath, err := filepath.Abs(targetDB)
	if err != nil {
		return nil, fmt.Errorf("解析恢复目标失败：%w", err)
	}
	manifestPath := filepath.Join(backupPath, backupManifestFile)
	dbPath := filepath.Join(backupPath, backupDBFilename)
	statePath := filepath.Join(backupPath, backupStateFile)
	if !fileExists(manifestPath) || !fileExists(dbPath) || !fileExists(statePath) {
		return nil, ErrBackupMissing
	}

	manifestBytes, err := os.ReadFile(manifestPath)
	if err != nil {
		return nil, fmt.Errorf("读 manifest.json 失败：%w", err)
	}
	var manifest BackupManifest
	if err := json.Unmarshal(manifestBytes, &manifest); err != nil {
		return nil, fmt.Errorf("解析 manifest.json 失败：%w", err)
	}
	if manifest.SchemaVersion != SchemaVersion {
		return nil, fmt.Errorf("%w: 期望 %d 实际 %d", ErrBackupSchema, SchemaVersion, manifest.SchemaVersion)
	}

	// 1) 备份库 sha256 必须匹配 manifest。
	dbSHA, err := fileSHA256(dbPath)
	if err != nil {
		return nil, fmt.Errorf("计算备份库 sha256 失败：%w", err)
	}
	if dbSHA != manifest.DatabaseSHA256 {
		return nil, fmt.Errorf("%w: manifest %s 实际 %s", ErrBackupDigest, manifest.DatabaseSHA256, dbSHA)
	}

	// 2) state.json 的 digest 必须与自身及 manifest 双向一致。
	stateBytes, err := os.ReadFile(statePath)
	if err != nil {
		return nil, fmt.Errorf("读 state.json 失败：%w", err)
	}
	var state map[string]any
	if err := json.Unmarshal(stateBytes, &state); err != nil {
		return nil, fmt.Errorf("解析 state.json 失败：%w", err)
	}
	stateWithoutMeta := map[string]any{}
	for k, v := range state {
		if k == backupMetadataAt || k == backupMetadataState {
			continue
		}
		stateWithoutMeta[k] = v
	}
	calculated := digestMap(stateWithoutMeta)
	if state[backupMetadataState] != calculated || manifest.StateDigest != calculated {
		return nil, ErrBackupDigest
	}

	// 3) 备份库完整性检查（integrity_check == ok + user_version + 表集合）。
	integrity := checkIntegrity(dbPath)
	if !integrity.OK {
		return nil, fmt.Errorf("%w: %s", ErrBackupIntegrity, integrity.Reason)
	}

	// 4) 备份库 snapshot 必须与 state.json 深度一致（规避 int64/float64 抖动用 canonical JSON）。
	db, derr := sql.Open("sqlite", "file:"+dbPath+"?mode=ro&_pragma=busy_timeout(5000)")
	if derr != nil {
		return nil, fmt.Errorf("只读打开备份库失败：%w", derr)
	}
	defer db.Close()
	dbSnap, serr := snapshotFromDB(db)
	if serr != nil {
		return nil, fmt.Errorf("快照备份库失败：%w", serr)
	}
	dbState := map[string]any{
		"schema_version":    dbSnap.SchemaVersion,
		"runs":              dbSnap.Runs,
		"approvals":         dbSnap.Approvals,
		"effects":           dbSnap.Effects,
		"effect_attempts":   dbSnap.EffectAttempts,
		"declared_exposure": dbSnap.DeclaredExposure,
		"events":            dbSnap.Events,
	}
	if digestMap(dbState) != calculated {
		return nil, ErrBackupCorrupt
	}

	// 5) 目标保护：存在且未显式 replace 则拒绝。
	if fileExists(targetPath) && !replace {
		return nil, fmt.Errorf("%w: %s", ErrRestoreTargetExists, targetPath)
	}
	if err := os.MkdirAll(filepath.Dir(targetPath), 0o700); err != nil {
		return nil, fmt.Errorf("创建恢复目标目录失败：%w", err)
	}
	tmp, terr := os.CreateTemp(filepath.Dir(targetPath), "."+filepath.Base(targetPath)+".restore-")
	if terr != nil {
		return nil, fmt.Errorf("创建恢复临时文件失败：%w", terr)
	}
	tmpPath := tmp.Name()
	// 复制备份库到临时文件，失败也要清理临时文件。
	src, oerr := os.Open(dbPath)
	if oerr != nil {
		_ = tmp.Close()
		_ = os.Remove(tmpPath)
		return nil, fmt.Errorf("打开备份库失败：%w", oerr)
	}
	if _, cerr := io.Copy(tmp, src); cerr != nil {
		_ = src.Close()
		_ = tmp.Close()
		_ = os.Remove(tmpPath)
		return nil, fmt.Errorf("复制备份库失败：%w", cerr)
	}
	_ = src.Close()
	if cerr := tmp.Close(); cerr != nil {
		_ = os.Remove(tmpPath)
		return nil, fmt.Errorf("关闭恢复临时文件失败：%w", cerr)
	}
	if rerr := os.Rename(tmpPath, targetPath); rerr != nil {
		_ = os.Remove(tmpPath)
		return nil, fmt.Errorf("原子替换恢复目标失败：%w", rerr)
	}
	// 清掉旧目标可能遗留的 WAL/SHM 兄弟文件，避免陈旧 journal 污染恢复结果。
	_ = os.Remove(targetPath + "-wal")
	_ = os.Remove(targetPath + "-shm")
	restoredSHA, rerr := fileSHA256(targetPath)
	if rerr != nil {
		return nil, fmt.Errorf("计算恢复库 sha256 失败：%w", rerr)
	}
	return &RestoreResult{
		TargetDatabase: targetPath,
		DatabaseSHA256: restoredSHA,
		StateDigest:    calculated,
		IntegrityCheck: integrity,
	}, nil
}

// ---- 内部辅助 ----

// snapshotFromDB 从任意已校验连接读取 6 张核心表的确定性投影。
func snapshotFromDB(db *sql.DB) (*Snapshot, error) {
	runs, e1 := queryTable(db, "runs", "ORDER BY created_at, run_id", nil)
	approvals, e2 := queryTable(db, "approvals", "ORDER BY created_at, approval_id", nil)
	effects, e3 := queryTable(db, "effects", "ORDER BY created_at, effect_id", map[string]bool{
		"external_receipt_json": true, "last_error_json": true,
	})
	attempts, e4 := queryTable(db, "effect_attempts", "ORDER BY attempt_id", map[string]bool{
		"result_json": true, "error_json": true,
	})
	exposure, e5 := queryTable(db, "declared_exposure", "ORDER BY run_id", map[string]bool{
		"declared_side_effects_json": true, "exposure_json": true,
	})
	events, e6 := queryTable(db, "events", "ORDER BY seq", map[string]bool{
		"payload_json": true,
	})
	for _, e := range []error{e1, e2, e3, e4, e5, e6} {
		if e != nil {
			return nil, e
		}
	}
	return &Snapshot{
		SchemaVersion:    SchemaVersion,
		Runs:             runs,
		Approvals:        approvals,
		Effects:          effects,
		EffectAttempts:   attempts,
		DeclaredExposure: exposure,
		Events:           events,
	}, nil
}

// queryTable 读取整表为 []map[string]any，JSON 列解码为原生类型，其余 TEXT 转 string。
func queryTable(db *sql.DB, table, order string, jsonCols map[string]bool) ([]map[string]any, error) {
	rows, err := db.Query("SELECT * FROM " + table + " " + order)
	if err != nil {
		return nil, fmt.Errorf("读取表 %s 失败：%w", table, err)
	}
	defer rows.Close()
	cols, err := rows.Columns()
	if err != nil {
		return nil, fmt.Errorf("读取表 %s 列失败：%w", table, err)
	}
	out := make([]map[string]any, 0)
	for rows.Next() {
		vals := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range vals {
			ptrs[i] = &vals[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			return nil, fmt.Errorf("扫描表 %s 失败：%w", table, err)
		}
		m := make(map[string]any, len(cols))
		for i, c := range cols {
			v := vals[i]
			if b, ok := v.([]byte); ok {
				if jsonCols[c] {
					var jv any
					if err := json.Unmarshal(b, &jv); err == nil {
						m[c] = jv
						continue
					}
				}
				m[c] = string(b)
			} else {
				m[c] = v
			}
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

// checkIntegrity 打开库只读执行 PRAGMA integrity_check，并校验 user_version 与表集合。
func checkIntegrity(dbPath string) IntegrityInfo {
	db, err := sql.Open("sqlite", "file:"+dbPath+"?mode=ro&_pragma=busy_timeout(5000)")
	if err != nil {
		return IntegrityInfo{OK: false, Reason: fmt.Sprintf("打开备份库失败: %v", err)}
	}
	defer db.Close()
	var result string
	if err := db.QueryRow("PRAGMA integrity_check").Scan(&result); err != nil {
		return IntegrityInfo{OK: false, Reason: fmt.Sprintf("integrity_check 错误: %v", err)}
	}
	var userVersion int
	if err := db.QueryRow("PRAGMA user_version").Scan(&userVersion); err != nil {
		return IntegrityInfo{OK: false, Reason: fmt.Sprintf("user_version 错误: %v", err)}
	}
	rows, err := db.Query("SELECT name FROM sqlite_master WHERE type = 'table'")
	if err != nil {
		return IntegrityInfo{OK: false, Reason: fmt.Sprintf("读表清单失败: %v", err)}
	}
	tables := make(map[string]bool)
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			rows.Close()
			return IntegrityInfo{OK: false, Reason: fmt.Sprintf("扫描表失败: %v", err)}
		}
		tables[name] = true
	}
	rows.Close()
	if result != "ok" {
		return IntegrityInfo{OK: false, Reason: fmt.Sprintf("integrity_check=%s", result), UserVersion: userVersion}
	}
	if userVersion != SchemaVersion {
		return IntegrityInfo{OK: false, Reason: fmt.Sprintf("user_version=%d 期望 %d", userVersion, SchemaVersion), UserVersion: userVersion}
	}
	for _, t := range backupRequiredTables {
		if !tables[t] {
			return IntegrityInfo{OK: false, Reason: fmt.Sprintf("缺少核心表 %s", t), UserVersion: userVersion}
		}
	}
	return IntegrityInfo{OK: true, IntegrityCheck: result, UserVersion: userVersion}
}

// atomicWriteJSON 原子写 JSON：先写临时文件再 os.Rename 替换。
func atomicWriteJSON(path string, value any) error {
	b, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return fmt.Errorf("序列化 JSON 失败：%w", err)
	}
	b = append(b, '\n')
	dir := filepath.Dir(path)
	tmp, err := os.CreateTemp(dir, "."+filepath.Base(path)+".")
	if err != nil {
		return fmt.Errorf("创建临时文件失败：%w", err)
	}
	tmpPath := tmp.Name()
	if _, err := tmp.Write(b); err != nil {
		tmp.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("写临时文件失败：%w", err)
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("刷盘失败：%w", err)
	}
	if err := tmp.Close(); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("关闭临时文件失败：%w", err)
	}
	if err := os.Rename(tmpPath, path); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("原子替换失败：%w", err)
	}
	return nil
}

// digestOf 计算 Snapshot 的 canonical JSON sha256（对齐 Python state_digest）。
func digestOf(snap *Snapshot) string {
	m := map[string]any{
		"schema_version":    snap.SchemaVersion,
		"runs":              snap.Runs,
		"approvals":         snap.Approvals,
		"effects":           snap.Effects,
		"effect_attempts":   snap.EffectAttempts,
		"declared_exposure": snap.DeclaredExposure,
		"events":            snap.Events,
	}
	return digestMap(m)
}

// digestMap 计算任意 map 的 canonical JSON sha256（json.Marshal 自动排序 map key）。
func digestMap(m map[string]any) string {
	b, err := json.Marshal(m)
	if err != nil {
		// 结构受控，序列化不应失败；失败时退回空摘要（上层校验必失败）。
		return ""
	}
	sum := sha256.Sum256(b)
	return fmt.Sprintf("%x", sum)
}

func fileSHA256(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return fmt.Sprintf("%x", h.Sum(nil)), nil
}

func fileExists(path string) bool {
	fi, err := os.Stat(path)
	return err == nil && !fi.IsDir()
}
