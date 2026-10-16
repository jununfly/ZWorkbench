package api

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/jununfly/ZWorkbench/app/internal/config"
	"github.com/jununfly/ZWorkbench/app/internal/evidence"
)

const testToken = "test-token"

func newTestRouter(t *testing.T) (http.Handler, *evidence.Owner) {
	t.Helper()
	ev, err := evidence.Open(":memory:")
	if err != nil {
		t.Fatalf("evidence.Open: %v", err)
	}
	t.Cleanup(func() { _ = ev.Close() })
	cfg := &config.Config{Port: "18080", Token: testToken}
	return NewRouter(cfg, nil, nil, ev), ev
}

func doJSON(t *testing.T, h http.Handler, method, path string, body any) *httptest.ResponseRecorder {
	t.Helper()
	var rdr io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal: %v", err)
		}
		rdr = strings.NewReader(string(b))
	}
	req := httptest.NewRequest(method, path, rdr)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

// TestEvidenceRunLifecycle 端到端跑一遍 run 生命周期：建 → 读 → start → safe_stop，
// 并校验每一步都在事件流里留下证据（1-5-6-3 的核心契约）。
func TestEvidenceRunLifecycle(t *testing.T) {
	h, _ := newTestRouter(t)

	// 1) 创建
	rec := doJSON(t, h, "POST", "/api/evidence/runs?token="+testToken, map[string]any{
		"task_type": "coding-evidence-demo",
		"input":     map[string]any{"prompt": "hello"},
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("create code=%d body=%s", rec.Code, rec.Body.String())
	}
	var run evidence.Run
	if err := json.Unmarshal(rec.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v (%s)", err, rec.Body.String())
	}
	if run.RunID == "" || run.TaskType != "coding-evidence-demo" {
		t.Fatalf("create 返回不对：%+v", run)
	}
	if run.Status != evidence.StatusCreated {
		t.Fatalf("新 run 应为 created，得到 %s", run.Status)
	}
	id := run.RunID

	// 2) 列表包含该 run
	rec = doJSON(t, h, "GET", "/api/evidence/runs?token="+testToken, nil)
	var runs []*evidence.Run
	if err := json.Unmarshal(rec.Body.Bytes(), &runs); err != nil {
		t.Fatalf("decode runs: %v", err)
	}
	found := false
	for _, r := range runs {
		if r.RunID == id {
			found = true
		}
	}
	if !found {
		t.Fatalf("列表里找不到 %s：%+v", id, runs)
	}

	// 3) 详情带事件投影（CreateRun 自带 run.created）
	rec = doJSON(t, h, "GET", "/api/evidence/runs/"+id+"?token="+testToken, nil)
	var detail evidence.Run
	if err := json.Unmarshal(rec.Body.Bytes(), &detail); err != nil {
		t.Fatalf("decode detail: %v", err)
	}
	if len(detail.Events) == 0 {
		t.Fatalf("详情应含事件投影，得到 %+v", detail)
	}

	// 4) start → running
	rec = doJSON(t, h, "POST", "/api/evidence/runs/"+id+"/transition?token="+testToken, map[string]any{"action": "start"})
	if rec.Code != http.StatusOK {
		t.Fatalf("start code=%d body=%s", rec.Code, rec.Body.String())
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode start: %v", err)
	}
	if run.Status != evidence.StatusRunning {
		t.Fatalf("start 后应 running，得到 %s", run.Status)
	}

	// 5) safe_stop → safe_stopped，并留下 reason
	rec = doJSON(t, h, "POST", "/api/evidence/runs/"+id+"/transition?token="+testToken, map[string]any{
		"action": "safe_stop",
		"reason": "api-smoke-test",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("safe_stop code=%d body=%s", rec.Code, rec.Body.String())
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode safe_stop: %v", err)
	}
	if run.Status != evidence.StatusSafeStopped {
		t.Fatalf("safe_stop 后应 safe_stopped，得到 %s", run.Status)
	}

	// 6) safe-stop 事件流：这是本 tab 的核心视图
	rec = doJSON(t, h, "GET", "/api/evidence/events?token="+testToken+"&type=run.safe_stopped", nil)
	var evs []evidence.Event
	if err := json.Unmarshal(rec.Body.Bytes(), &evs); err != nil {
		t.Fatalf("decode events: %v", err)
	}
	if len(evs) != 1 {
		t.Fatalf("safe_stopped 事件应 1 条，得到 %d（%+v）", len(evs), evs)
	}
	if evs[0].RunID != id || evs[0].Payload["reason"] != "api-smoke-test" {
		t.Fatalf("safe_stopped 事件不对：%+v", evs[0])
	}

	// 7) 终态再转移 → 400（fail-closed 是语义拒绝，不是 500）
	rec = doJSON(t, h, "POST", "/api/evidence/runs/"+id+"/transition?token="+testToken, map[string]any{"action": "start"})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("终态再 start 应 400，得到 %d（%s）", rec.Code, rec.Body.String())
	}

	// 8) 未知 action → 400
	rec = doJSON(t, h, "POST", "/api/evidence/runs/"+id+"/transition?token="+testToken, map[string]any{"action": "nope"})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("未知 action 应 400，得到 %d", rec.Code)
	}
}

// TestEvidenceAuth 校验 /api/evidence/* 同样落在既有鉴权中间件之下。
func TestEvidenceAuth(t *testing.T) {
	h, _ := newTestRouter(t)
	rec := doJSON(t, h, "GET", "/api/evidence/runs", nil) // 无 token
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("无 token 应 401，得到 %d", rec.Code)
	}
}

// TestEvidenceViolations 校验引用完整性端点在无孤儿引用时返回空数组（而非 null）。
func TestEvidenceViolations(t *testing.T) {
	h, _ := newTestRouter(t)
	doJSON(t, h, "POST", "/api/evidence/runs?token="+testToken, map[string]any{"task_type": "t"})
	rec := doJSON(t, h, "GET", "/api/evidence/violations?token="+testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("violations code=%d body=%s", rec.Code, rec.Body.String())
	}
	var v []evidence.Violation
	if err := json.Unmarshal(rec.Body.Bytes(), &v); err != nil {
		t.Fatalf("decode violations: %v", err)
	}
	if len(v) != 0 {
		t.Fatalf("无孤儿引用时应为空，得到 %+v", v)
	}
}

// TestEvidenceIdentityChain 校验身份链端点的入参歧义与未知 id 语义（1-4-4）。
func TestEvidenceIdentityChain(t *testing.T) {
	h, ev := newTestRouter(t)
	if _, err := ev.CreateRun("chain-api-run", "coding", nil, nil); err != nil {
		t.Fatalf("CreateRun: %v", err)
	}

	// 1) 都不给 → 400（歧义必须拒绝，不猜）
	rec := doJSON(t, h, "GET", "/api/evidence/identity-chain?token="+testToken, nil)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("无入参应 400，得到 %d（%s）", rec.Code, rec.Body.String())
	}
	// 2) 多选 → 400
	rec = doJSON(t, h, "GET", "/api/evidence/identity-chain?token="+testToken+"&run_id=chain-api-run&effect_id=x", nil)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("多选入参应 400，得到 %d", rec.Code)
	}
	// 3) 未知 id → 404（绝不返 200 空链冒充"没数据"）
	rec = doJSON(t, h, "GET", "/api/evidence/identity-chain?token="+testToken+"&run_id=chain-no-such-run", nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("未知 run 应 404，得到 %d", rec.Code)
	}
	// 4) 正常解析：entry 说明起点，counts 结构齐全
	rec = doJSON(t, h, "GET", "/api/evidence/identity-chain?token="+testToken+"&run_id=chain-api-run", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("chain code=%d body=%s", rec.Code, rec.Body.String())
	}
	var got struct {
		RunID string `json:"run_id"`
		Entry struct {
			Kind string `json:"kind"`
			ID   string `json:"id"`
		} `json:"entry"`
		Counts struct {
			Effects  int `json:"effects"`
			Attempts int `json:"attempts"`
		} `json:"counts"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("decode chain: %v (%s)", err, rec.Body.String())
	}
	if got.RunID != "chain-api-run" || got.Entry.Kind != evidence.EntryRunID {
		t.Fatalf("chain 返回不对：%+v", got)
	}
	// 5) effect 不存在时 attempts 也应 404
	rec = doJSON(t, h, "GET", "/api/evidence/effects/chain-no-such-effect/attempts?token="+testToken, nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("未知 effect 的 attempts 应 404，得到 %d", rec.Code)
	}
}

// TestEvidenceSafeStopOnViolation 校验 safe-stop 触发端点的两种结局（1-4-5）：
// 健康 run 不动 / 有违例必停，且未知 run 404。
func TestEvidenceSafeStopOnViolation(t *testing.T) {
	h, _ := newTestRouter(t)

	// 1) 健康 run：检测本身不中断
	doJSON(t, h, "POST", "/api/evidence/runs?token="+testToken, map[string]any{
		"run_id": "ss-api-clean", "task_type": "t",
	})
	rec := doJSON(t, h, "POST", "/api/evidence/runs/ss-api-clean/safe-stop-on-violation?token="+testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("clean code=%d body=%s", rec.Code, rec.Body.String())
	}
	var clean struct {
		SafeStopped bool   `json:"safe_stopped"`
		Status      string `json:"status"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &clean); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if clean.SafeStopped || clean.Status != "created" {
		t.Fatalf("健康 run 不应被停: %+v", clean)
	}

	// 2) metadata 断链：必停
	doJSON(t, h, "POST", "/api/evidence/runs?token="+testToken, map[string]any{
		"run_id":    "ss-api-dirty",
		"task_type": "t",
		"metadata":  map[string]any{"parent_run_id": "ss-api-ghost-parent"},
	})
	rec = doJSON(t, h, "POST", "/api/evidence/runs/ss-api-dirty/safe-stop-on-violation?token="+testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("dirty code=%d body=%s", rec.Code, rec.Body.String())
	}
	var dirty struct {
		SafeStopped bool   `json:"safe_stopped"`
		Status      string `json:"status"`
		Violations  []struct {
			Kind string `json:"kind"`
		} `json:"violations"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &dirty); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if !dirty.SafeStopped || dirty.Status != "safe_stopped" {
		t.Fatalf("有违例应 safe-stop: %+v", dirty)
	}
	if len(dirty.Violations) != 1 || dirty.Violations[0].Kind != "broken_parent_run_id" {
		t.Fatalf("violations 不符: %+v", dirty.Violations)
	}

	// 3) 未知 run → 404
	rec = doJSON(t, h, "POST", "/api/evidence/runs/ss-api-nope/safe-stop-on-violation?token="+testToken, nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("未知 run 应 404，得到 %d", rec.Code)
	}

	// 4) reconcile-identity：终态不复活（outcome=resolved 但状态仍是 safe_stopped）
	if _, err := json.Marshal(map[string]any{}); err != nil {
		t.Fatalf("marshal: %v", err)
	}
	rec = doJSON(t, h, "POST", "/api/evidence/runs/ss-api-clean/reconcile-identity?token="+testToken, map[string]any{"evidence": "n/a"})
	if rec.Code != http.StatusOK {
		t.Fatalf("reconcile code=%d body=%s", rec.Code, rec.Body.String())
	}
	var recOut struct {
		Outcome string `json:"outcome"`
		Status  string `json:"status"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &recOut); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if recOut.Outcome != "resolved" || recOut.Status != "created" {
		t.Fatalf("干净 run 收口应为 resolved/created: %+v", recOut)
	}
	rec = doJSON(t, h, "POST", "/api/evidence/runs/ss-api-nope/reconcile-identity?token="+testToken, nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("未知 run reconcile 应 404，得到 %d", rec.Code)
	}
}

// TestEvidenceUnavailable 校验证据库缺失时显式 503，而不是让前端静默空白。
func TestEvidenceUnavailable(t *testing.T) {
	cfg := &config.Config{Port: "18080", Token: testToken}
	h := NewRouter(cfg, nil, nil, nil)
	rec := doJSON(t, h, "GET", "/api/evidence/runs?token="+testToken, nil)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("evidence 缺失应 503，得到 %d", rec.Code)
	}
}
