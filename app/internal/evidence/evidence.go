// Package evidence 是 ZWorkbench 的「CompositionOwner（C26）」Go 等价实现，
// 属 roadmap 1-5-6-1（B2-narrow：只移植差异化证据语义，零 Python 进程依赖）。
//
// 它把 Python src/zworkbench/composition.py 里的「durable-owner 7 状态机 +
// 引用完整性（identity-violation）检测 + C28 一次性审批 token + fail-closed
// effect-claim 归属」用纯 Go + modernc.org/sqlite（无 cgo）重写进 app/。
// B2-narrow 范围仅含核心证据语义表：runs / approvals / effects /
// effect_attempts（effects 的逐次尝试日志，claim_effect 的 bounded-retry 路径
// 必写，属 effects 子系统而非 harness ledger）/ declared_exposure / events。
// provider/dsh/worker 的 retry ledger 与 caller-auth 不属于 app/ 工作台，
// 按 ADR 0016 不移植。
package evidence

import (
	"crypto/rand"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	_ "modernc.org/sqlite" // 纯 Go SQLite 驱动，无 cgo（与 1-5-5 一致）
)

// 运行（Run）的 7 个生命周期状态，权威定义见 composition.py 的 RUN_STATES。
const (
	StatusCreated         RunStatus = "created"
	StatusRunning         RunStatus = "running"
	StatusWaitingApproval RunStatus = "waiting_approval"
	StatusRecovering      RunStatus = "recovering"
	StatusCompleted       RunStatus = "completed"
	StatusFailed          RunStatus = "failed"
	StatusSafeStopped     RunStatus = "safe_stopped"
)

// RunStatus 是运行状态的枚举类型。
type RunStatus string

// 全部合法状态（用于矩阵校验与“未知状态”拒绝）。
var runStatuses = map[RunStatus]bool{
	StatusCreated:         true,
	StatusRunning:         true,
	StatusWaitingApproval: true,
	StatusRecovering:      true,
	StatusCompleted:       true,
	StatusFailed:          true,
	StatusSafeStopped:     true,
}

// 状态转移矩阵（composition.py _set_run_status 的 allowed 字典逐字移植）。
// 终态（completed/failed/safe_stopped）无出边；RestartRun 是绕过本矩阵的
// 审计逃生舱（见 owner.go）。
var runTransitions = map[RunStatus]map[RunStatus]bool{
	StatusCreated:         {StatusRunning: true, StatusWaitingApproval: true, StatusFailed: true, StatusSafeStopped: true},
	StatusRunning:         {StatusWaitingApproval: true, StatusRecovering: true, StatusCompleted: true, StatusFailed: true, StatusSafeStopped: true},
	StatusWaitingApproval: {StatusRunning: true, StatusFailed: true, StatusSafeStopped: true},
	StatusRecovering:      {StatusRunning: true, StatusFailed: true, StatusSafeStopped: true},
	StatusCompleted:       {},
	StatusFailed:          {},
	StatusSafeStopped:     {},
}

// 证据来源分类（与 Python EVIDENCE_SOURCE_* 对应）。
const (
	EvidenceSourceNative         = "native"
	EvidenceSourcePluginComposed = "plugin-composed"
	EvidenceSourceOuterComposed  = "outer-composed"
)

func validEvidenceSource(s string) bool {
	switch s {
	case EvidenceSourceNative, EvidenceSourcePluginComposed, EvidenceSourceOuterComposed:
		return true
	}
	return false
}

// 哨兵错误。
var (
	ErrInvalidTransition = errors.New("invalid transition")
	ErrRunNotFound       = errors.New("run not found")
	ErrRunExists         = errors.New("run already exists")
	ErrBadArgument       = errors.New("bad argument")
)

// schema 是 5 张核心表的建表语句（composition.py 核心 schema 移植）。
const schema = `
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    input_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    operation_id TEXT NOT NULL UNIQUE,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    reason TEXT NOT NULL,
    status TEXT NOT NULL,
    token_hash TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decision_reason TEXT,
    consumed_at TEXT
);
CREATE TABLE IF NOT EXISTS effects (
    effect_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    operation_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    effect_class TEXT NOT NULL,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    physical_effect_count INTEGER NOT NULL,
    approval_id TEXT REFERENCES approvals(approval_id),
    external_receipt_json TEXT,
    last_error_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS effect_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    effect_id TEXT NOT NULL REFERENCES effects(effect_id),
    attempt INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    result_json TEXT,
    error_json TEXT,
    UNIQUE(effect_id, attempt)
);
CREATE TABLE IF NOT EXISTS declared_exposure (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
    declared_side_effects_json TEXT NOT NULL,
    exposure_json TEXT NOT NULL,
    declared_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    evidence_source TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_run ON events(run_id, seq);
`

// Owner 是 CompositionOwner 的 Go 等价体：唯一持久拥有者，保证引用完整性。
// 直接持有 *sql.DB（依赖注入），测试用内存库、服务可传真实库。
type Owner struct {
	db *sql.DB
}

// New 用已有 *sql.DB 构造 Owner（不建表，调用方需确保 schema 已就绪）。
func New(db *sql.DB) *Owner { return &Owner{db: db} }

// Open 打开（或创建）SQLite 并建 5 张核心表。path 为空或 ":memory:" 走共享内存库。
func Open(path string) (*Owner, error) {
	var dsn string
	if path == "" || path == ":memory:" {
		dsn = "file::memory:?cache=shared&_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)"
	} else {
		dsn = "file:" + path + "?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)"
	}
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("打开 evidence SQLite 失败：%w", err)
	}
	if err := db.Ping(); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("连接 evidence SQLite 失败：%w", err)
	}
	if _, err := db.Exec(schema); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("建 evidence 核心表失败：%w", err)
	}
	return New(db), nil
}

// DB 暴露底层连接，便于上层（1-5-6-3）在同一物理库上挂路由。
func (o *Owner) DB() *sql.DB { return o.db }

// Close 释放连接。
func (o *Owner) Close() error { return o.db.Close() }

// ---- 内部类型与工具 ----

type runRow struct {
	RunID         string
	TaskType      string
	InputJSON     string
	MetadataJSON  string
	Status        RunStatus
	CreatedAt     string
	UpdatedAt     string
}

func nowUTC() string { return time.Now().UTC().Format(time.RFC3339) }

func requireText(v, name string) error {
	if strings.TrimSpace(v) == "" {
		return fmt.Errorf("%w: %s 不能为空", ErrBadArgument, name)
	}
	return nil
}

func jsonString(v any) (string, error) {
	b, err := json.Marshal(v)
	if err != nil {
		return "", fmt.Errorf("序列化 JSON 失败：%w", err)
	}
	return string(b), nil
}

func newID() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

func isUniqueViolation(err error) bool {
	return err != nil && strings.Contains(err.Error(), "UNIQUE constraint")
}

// transact 在写事务里执行 fn；fn 返回错误则回滚，否则提交。用于保证状态机原子性。
func (o *Owner) transact(fn func(tx *sql.Tx) error) error {
	tx, err := o.db.Begin()
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer func() {
		if p := recover(); p != nil {
			_ = tx.Rollback()
			panic(p)
		}
	}()
	if err := fn(tx); err != nil {
		_ = tx.Rollback()
		return err
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit tx: %w", err)
	}
	return nil
}

// Run 是运行记录（含可选的事件/效果/曝光投影，便于前端可视化）。
type Run struct {
	RunID     string         `json:"run_id"`
	TaskType  string         `json:"task_type"`
	Input     any            `json:"input,omitempty"`
	Metadata  map[string]any `json:"metadata,omitempty"`
	Status    RunStatus      `json:"status"`
	CreatedAt string         `json:"created_at"`
	UpdatedAt string         `json:"updated_at"`
	Events    []Event        `json:"events,omitempty"`
	Effects   []Effect       `json:"effects,omitempty"`
	Exposure  *DeclaredExposure `json:"exposure,omitempty"`
}

// Event 是结构化证据事件（adapter 消息即证据，owner 赋规范行）。
type Event struct {
	Seq            int64          `json:"seq"`
	EventID        string         `json:"event_id"`
	RunID          string         `json:"run_id"`
	Type           string         `json:"type"`
	Payload        map[string]any `json:"payload,omitempty"`
	EvidenceSource string         `json:"evidence_source,omitempty"`
	CreatedAt      string         `json:"created_at"`
}

// Effect 是副作用记录（C28 核心：claim/complete 归属与 exactly-once 提交）。
type Effect struct {
	EffectID           string `json:"effect_id"`
	RunID              string `json:"run_id"`
	OperationID        string `json:"operation_id"`
	IdempotencyKey     string `json:"idempotency_key"`
	EffectClass        string `json:"effect_class"`
	Action             string `json:"action"`
	Resource           string `json:"resource"`
	Status             string `json:"status"`
	Attempt            int    `json:"attempt"`
	MaxAttempts        int    `json:"max_attempts"`
	PhysicalEffectCount int   `json:"physical_effect_count"`
	ApprovalID         string `json:"approval_id,omitempty"`
	CreatedAt          string `json:"created_at"`
	UpdatedAt          string `json:"updated_at"`
}

// DeclaredExposure 是运行声明的副作用曝光面。
type DeclaredExposure struct {
	RunID               string `json:"run_id"`
	DeclaredSideEffects any    `json:"declared_side_effects,omitempty"`
	Exposure            any    `json:"exposure,omitempty"`
	DeclaredAt          string `json:"declared_at"`
}

// Violation 是引用完整性扫描出的孤儿引用（durable-owner 语义核心）。
type Violation struct {
	Kind      string `json:"kind"`
	RunID     string `json:"run_id"`
	RefTable  string `json:"ref_table"`
	RefID     string `json:"ref_id"`
	Detail    string `json:"detail"`
}
