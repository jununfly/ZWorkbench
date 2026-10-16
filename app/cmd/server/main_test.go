package main

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jununfly/ZWorkbench/app/internal/config"
)

// TestBuildHandlerWiresAuthAndEvidence 校验 main 的装配链产出可用 handler：
// 无 token → 401（鉴权中间件生效）；带 token → 200（证据库已接线，非 503）。
// 这锁住 cmd/server 的接线契约——若 main 漏接证据库或鉴权，本测试会红。
func TestBuildHandlerWiresAuthAndEvidence(t *testing.T) {
	cfg := &config.Config{Port: "18080", Token: "test-token", DB: "mem", EvidenceDB: ":memory:"}
	handler, sqliteStore, ev, err := buildHandler(cfg)
	if err != nil {
		t.Fatalf("buildHandler 失败：%v", err)
	}
	t.Cleanup(func() {
		_ = ev.Close()
		if sqliteStore != nil {
			_ = sqliteStore.Close()
		}
	})
	if handler == nil {
		t.Fatalf("handler 为 nil")
	}

	// 无 token → 401
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/evidence/runs", nil)
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("无 token 期望 401，实际 %d", rec.Code)
	}

	// 带 token → 200（证据库已接线）
	rec2 := httptest.NewRecorder()
	req2 := httptest.NewRequest(http.MethodGet, "/api/evidence/runs?token=test-token", nil)
	handler.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusOK {
		t.Fatalf("带 token 期望 200，实际 %d", rec2.Code)
	}
}
