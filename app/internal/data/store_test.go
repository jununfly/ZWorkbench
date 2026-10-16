package data

import (
	"testing"
)

func TestMemStoreSaveGetList(t *testing.T) {
	s := NewMemStore()
	var _ Store = s
	if err := s.Save(Snapshot{ID: "a", Topic: "t1", Payload: "p"}); err != nil {
		t.Fatalf("Save: %v", err)
	}
	got, ok := s.Get("a")
	if !ok || got.Payload != "p" {
		t.Fatalf("Get 失败：%v %q", ok, got.Payload)
	}
	if _, ok := s.Get("missing"); ok {
		t.Fatalf("缺失键应返回 ok=false")
	}
	if n := len(s.List("t1")); n != 1 {
		t.Fatalf("List(t1) 应 1 条，得到 %d", n)
	}
	if n := len(s.List("")); n != 1 {
		t.Fatalf("List(\"\") 应全量 1 条，得到 %d", n)
	}
	// 同 ID 覆盖写，不新增行
	_ = s.Save(Snapshot{ID: "a", Topic: "t1", Payload: "p2"})
	if g, _ := s.Get("a"); g.Payload != "p2" {
		t.Fatalf("覆盖写未生效：%q", g.Payload)
	}
	if n := len(s.List("")); n != 1 {
		t.Fatalf("覆盖写不应新增行，得到 %d", n)
	}
}

func TestSqliteStoreContract(t *testing.T) {
	s, err := NewSqliteStore(":memory:")
	if err != nil {
		t.Fatalf("NewSqliteStore: %v", err)
	}
	defer s.Close()
	var _ Store = s

	if err := s.Save(Snapshot{ID: "a", Topic: "t1", Payload: "p"}); err != nil {
		t.Fatalf("Save: %v", err)
	}
	// CreatedAt 自动填充
	g, ok := s.Get("a")
	if !ok {
		t.Fatalf("Get 失败")
	}
	if g.CreatedAt == "" {
		t.Fatalf("CreatedAt 应自动填充")
	}
	if _, ok := s.Get("missing"); ok {
		t.Fatalf("缺失键应 ok=false")
	}
	if n := len(s.List("t1")); n != 1 {
		t.Fatalf("List(t1) 应 1，得到 %d", n)
	}
	// 同 ID upsert，不新增行
	_ = s.Save(Snapshot{ID: "a", Topic: "t1", Payload: "p2"})
	if g, _ := s.Get("a"); g.Payload != "p2" {
		t.Fatalf("upsert 未生效：%q", g.Payload)
	}
	if n := len(s.List("")); n != 1 {
		t.Fatalf("upsert 不应新增行，得到 %d", n)
	}
}
