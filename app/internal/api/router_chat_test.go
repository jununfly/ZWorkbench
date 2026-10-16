package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/jununfly/ZWorkbench/app/internal/agent"
	"github.com/jununfly/ZWorkbench/app/internal/config"
)

// mockOpenAI 是 OpenAI 兼容 /chat/completions 的最小伪端点，用于端到端联调
// 「路由鉴权 → FromConfig → 真实客户端 → 解析响应」整条链路（1-3-1 联调证据）。
func mockOpenAI(t *testing.T, status int, body string) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat/completions" {
			t.Errorf("路径应为 /chat/completions，得到 %s", r.URL.Path)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer test-key" {
			t.Errorf("Authorization 应为 Bearer test-key，得到 %q", got)
		}
		w.WriteHeader(status)
		_, _ = w.Write([]byte(body))
	}))
}

// TestAgentChatEndToEnd 端到端验证 /api/agent/chat：鉴权 + LLM 配置读取 +
// 真实 OpenAI 兼容客户端 + 响应解析，整条链路打通（不是 stub）。
func TestAgentChatEndToEnd(t *testing.T) {
	srv := mockOpenAI(t, http.StatusOK, `{"model":"deepseek-chat","choices":[{"message":{"role":"assistant","content":"pong"}}]}`)
	defer srv.Close()

	cfg := &config.Config{
		Port:  "18080",
		Token: testToken,
	}
	cfg.SetLLM(config.LLMConfig{
		Enabled: true,
		APIKey:  "test-key",
		BaseURL: srv.URL,
		Model:   "deepseek-chat",
	})
	h := NewRouter(cfg, nil, nil, nil)

	rec := doJSON(t, h, "POST", "/api/agent/chat?token="+testToken, agent.ChatRequest{
		Messages: []agent.Msg{{Role: "user", Content: "ping"}},
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("chat code=%d body=%s", rec.Code, rec.Body.String())
	}
	var resp agent.ChatResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode chat resp: %v", err)
	}
	if resp.Content != "pong" {
		t.Fatalf("Content 期望 pong，得到 %q", resp.Content)
	}
	if resp.Model != "deepseek-chat" {
		t.Fatalf("Model 期望 deepseek-chat，得到 %q", resp.Model)
	}
}

// TestAgentChatUnconfigured 未配置时应透传明确引导错误（502），而非静默成功。
func TestAgentChatUnconfigured(t *testing.T) {
	cfg := &config.Config{Port: "18080", Token: testToken}
	h := NewRouter(cfg, nil, nil, nil)

	rec := doJSON(t, h, "POST", "/api/agent/chat?token="+testToken, agent.ChatRequest{
		Messages: []agent.Msg{{Role: "user", Content: "hi"}},
	})
	if rec.Code != http.StatusBadGateway {
		t.Fatalf("未配置应 502，得到 %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "未配置") {
		t.Fatalf("错误应含 未配置，得到 %q", rec.Body.String())
	}
}

// TestAgentChatProviderError 上游 500 应透传为 502 + HTTP 状态码，错误直显。
func TestAgentChatProviderError(t *testing.T) {
	srv := mockOpenAI(t, http.StatusInternalServerError, "boom")
	defer srv.Close()

	cfg := &config.Config{Port: "18080", Token: testToken}
	cfg.SetLLM(config.LLMConfig{Enabled: true, APIKey: "test-key", BaseURL: srv.URL, Model: "m"})
	h := NewRouter(cfg, nil, nil, nil)

	rec := doJSON(t, h, "POST", "/api/agent/chat?token="+testToken, agent.ChatRequest{})
	if rec.Code != http.StatusBadGateway {
		t.Fatalf("上游 500 应 502，得到 %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "HTTP 500") {
		t.Fatalf("错误应含 HTTP 500，得到 %q", rec.Body.String())
	}
}

// TestAgentChatAuth 无 token 应 401（确认 chat 也落在鉴权中间件之下）。
func TestAgentChatAuth(t *testing.T) {
	cfg := &config.Config{Port: "18080", Token: testToken}
	h := NewRouter(cfg, nil, nil, nil)
	rec := doJSON(t, h, "POST", "/api/agent/chat", agent.ChatRequest{})
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("无 token 应 401，得到 %d", rec.Code)
	}
}

// TestConfigEnableWithoutKeyRejected 1-3-2 fail-closed：
// 启用 LLM 但（最终）无 API Key 应 400，不能静默回退 unconfigured 却显示「已启用」。
func TestConfigEnableWithoutKeyRejected(t *testing.T) {
	// PUT 会触发 SaveDataSource，重定向到临时路径避免污染仓库 cwd。
	t.Setenv("ZW_CONFIG", t.TempDir()+"/config.json")
	cfg := &config.Config{Port: "18080", Token: testToken}
	h := NewRouter(cfg, nil, nil, nil)

	rec := doJSON(t, h, "PUT", "/api/config?token="+testToken, map[string]any{
		"llm": map[string]any{"enabled": true, "api_key": ""},
	})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("启用却无 key 应 400，得到 %d（%s）", rec.Code, rec.Body.String())
	}

	// 反向确认：未启用时允许无 key 保存（沿用默认关闭状态）。
	rec = doJSON(t, h, "PUT", "/api/config?token="+testToken, map[string]any{
		"llm": map[string]any{"enabled": false, "api_key": ""},
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("未启用无 key 应 200，得到 %d（%s）", rec.Code, rec.Body.String())
	}
}
