package data

import "sync"

// Snapshot 是 ES 风格的证据快照：带来源与时间的版本化记录。
// Phase 2 接 SQLite 时，字段直接映射到表。
type Snapshot struct {
	ID        string `json:"id"`
	Topic     string `json:"topic"`
	Source    string `json:"source"`
	Payload   string `json:"payload"`
	CreatedAt string `json:"created_at"`
}

// Store 是本地证据底座接口。骨架先用 MemStore（离线可跑），
// Phase 2 换 SqliteStore（纯 Go 驱动如 modernc.org/sqlite，无 cgo）。
type Store interface {
	Save(s Snapshot) error
	Get(id string) (Snapshot, bool)
	List(topic string) []Snapshot
}

// MemStore 内存实现，仅用于骨架期。
type MemStore struct {
	mu sync.Mutex
	m  map[string]Snapshot
}

func NewMemStore() *MemStore {
	return &MemStore{m: make(map[string]Snapshot)}
}

func (s *MemStore) Save(snap Snapshot) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.m[snap.ID] = snap
	return nil
}

func (s *MemStore) Get(id string) (Snapshot, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	v, ok := s.m[id]
	return v, ok
}

func (s *MemStore) List(topic string) []Snapshot {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]Snapshot, 0)
	for _, v := range s.m {
		if topic == "" || v.Topic == topic {
			out = append(out, v)
		}
	}
	return out
}
