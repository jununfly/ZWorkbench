package webstatic

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func tempDist(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "index.html"), []byte("<html>ZW</html>"), 0o644); err != nil {
		t.Fatalf("write index.html: %v", err)
	}
	if err := os.MkdirAll(filepath.Join(dir, "assets"), 0o755); err != nil {
		t.Fatalf("mkdir assets: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "assets", "app.js"), []byte("console.log(1)"), 0o644); err != nil {
		t.Fatalf("write app.js: %v", err)
	}
	return dir
}

func TestHandlerMissingDirReturns503(t *testing.T) {
	h := NewHandler("")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("want 503, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "前端产物缺失") {
		t.Fatalf("want actionable message, got %q", rec.Body.String())
	}
}

func TestHandlerMissingDirKeepsApi404(t *testing.T) {
	h := NewHandler("")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/nope", nil))
	if rec.Code != http.StatusNotFound {
		t.Fatalf("want 404 for /api/, got %d", rec.Code)
	}
}

func TestHandlerServesIndexAndAssets(t *testing.T) {
	dir := tempDist(t)
	h := NewHandler(dir)

	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))
	if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), "ZW") {
		t.Fatalf("index: want 200 + ZW, got %d %q", rec.Code, rec.Body.String())
	}

	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/assets/app.js", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("asset: want 200, got %d", rec.Code)
	}
}

func TestHandlerSpaFallback(t *testing.T) {
	dir := tempDist(t)
	h := NewHandler(dir)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/some/deep/route", nil))
	if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), "ZW") {
		t.Fatalf("spa fallback: want 200 + index, got %d %q", rec.Code, rec.Body.String())
	}
}

func TestDirRespectsExplicitDist(t *testing.T) {
	dir := tempDist(t)
	if got := Dir(dir); got != dir {
		t.Fatalf("want %q, got %q", dir, got)
	}
}

func TestDirReturnsEmptyForNonDist(t *testing.T) {
	empty := t.TempDir()
	if got := Dir(empty); got != "" {
		t.Fatalf("non-dist dir must resolve to empty, got %q", got)
	}
}
