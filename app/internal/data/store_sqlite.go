package data

import (
	"database/sql"
	"fmt"
	"time"

	_ "modernc.org/sqlite" // 纯 Go SQLite 驱动，无 cgo（1-5-5 D1）
)

// sqliteSchema 是 snapshots 表的建表语句。composition_owner 为预留列（1-5-5）。
const sqliteSchema = `
CREATE TABLE IF NOT EXISTS snapshots (
	id TEXT PRIMARY KEY,
	topic TEXT NOT NULL DEFAULT '',
	source TEXT NOT NULL DEFAULT '',
	payload TEXT NOT NULL DEFAULT '',
	created_at TEXT NOT NULL DEFAULT '',
	composition_owner TEXT NOT NULL DEFAULT ''
);
`

// SqliteStore 是 Store 的 SQLite 实现（modernc.org/sqlite，无 cgo）。
// 满足 Store 接口；快照持久化到本地文件，重启存活（退出判据验证）。
type SqliteStore struct {
	db *sql.DB
}

// NewSqliteStore 打开（或创建）指定路径的 SQLite 库并建表。
// path 为空时退回内存库（":memory:"）——仍走 SQLite 路径，便于测试。
func NewSqliteStore(path string) (*SqliteStore, error) {
	if path == "" {
		path = ":memory:"
	}
	// modernc 驱动名 "sqlite"；"?_pragma=busy_timeout(5000)" 缓解并发写锁。
	dsn := "file:" + path + "?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("打开 SQLite 失败：%w", err)
	}
	if err := db.Ping(); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("连接 SQLite 失败：%w", err)
	}
	if _, err := db.Exec(sqliteSchema); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("建表 snapshots 失败：%w", err)
	}
	return &SqliteStore{db: db}, nil
}

// Close 释放数据库连接。main 退出时调用。
func (s *SqliteStore) Close() error { return s.db.Close() }

func (s *SqliteStore) Save(snap Snapshot) error {
	if snap.CreatedAt == "" {
		snap.CreatedAt = time.Now().UTC().Format(time.RFC3339)
	}
	_, err := s.db.Exec(
		`INSERT INTO snapshots (id, topic, source, payload, created_at, composition_owner)
		 VALUES (?, ?, ?, ?, ?, ?)
		 ON CONFLICT(id) DO UPDATE SET
		   topic=excluded.topic, source=excluded.source, payload=excluded.payload,
		   created_at=excluded.created_at, composition_owner=excluded.composition_owner`,
		snap.ID, snap.Topic, snap.Source, snap.Payload, snap.CreatedAt, snap.CompositionOwner,
	)
	if err != nil {
		return fmt.Errorf("写快照失败：%w", err)
	}
	return nil
}

func (s *SqliteStore) Get(id string) (Snapshot, bool) {
	row := s.db.QueryRow(
		`SELECT id, topic, source, payload, created_at, composition_owner FROM snapshots WHERE id = ?`, id)
	var snap Snapshot
	err := row.Scan(&snap.ID, &snap.Topic, &snap.Source, &snap.Payload, &snap.CreatedAt, &snap.CompositionOwner)
	if err == sql.ErrNoRows {
		return Snapshot{}, false
	}
	if err != nil {
		return Snapshot{}, false
	}
	return snap, true
}

func (s *SqliteStore) List(topic string) []Snapshot {
	q := `SELECT id, topic, source, payload, created_at, composition_owner FROM snapshots`
	args := []any{}
	if topic != "" {
		q += ` WHERE topic = ?`
		args = append(args, topic)
	}
	q += ` ORDER BY created_at DESC, id DESC`
	rows, err := s.db.Query(q, args...)
	if err != nil {
		return nil
	}
	defer rows.Close()
	out := make([]Snapshot, 0)
	for rows.Next() {
		var snap Snapshot
		if err := rows.Scan(&snap.ID, &snap.Topic, &snap.Source, &snap.Payload, &snap.CreatedAt, &snap.CompositionOwner); err != nil {
			return out
		}
		out = append(out, snap)
	}
	return out
}
