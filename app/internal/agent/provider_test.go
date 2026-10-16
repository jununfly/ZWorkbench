package agent

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/jununfly/ZWorkbench/app/internal/config"
)

func TestFromConfigUnconfigured(t *testing.T) {
	p := FromConfig(config.LLMConfig{Enabled: false})
	if p.Name() != "unconfigured" {
		t.Fatalf("未配置时 Name 应为 unconfigured，得到 %q", p.Name())
	}
	_, err := p.Chat(context.Background(), ChatRequest{Model: "m", Messages: []Msg{{Role: "user", Content: "hi"}}})
	if err == nil {
		t.Fatalf("unconfiguredProvider.Chat 应返回错误")
	}
	if !strings.Contains(err.Error(), "未配置") {
		t.Fatalf("错误应含 未配置，得到 %q", err.Error())
	}
}

func TestFromConfigEnabledBuildsClient(t *testing.T) {
	p := FromConfig(config.LLMConfig{Enabled: true, APIKey: "k"})
	if p.Name() != "openai-compatible" {
		t.Fatalf("启用时应返回 openai-compatible，得到 %q", p.Name())
	}
}

func TestOpenAIClientChatOK(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat/completions" {
			t.Errorf("路径应为 /chat/completions，得到 %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer k" {
			t.Errorf("Authorization 头应为 Bearer k")
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"model": "gpt-4o",
			"choices": []map[string]any{
				{"message": map[string]any{"role": "assistant", "content": "hi back"}},
			},
		})
	}))
	defer srv.Close()

	p := FromConfig(config.LLMConfig{Enabled: true, APIKey: "k", BaseURL: srv.URL, Model: "gpt-4o"})
	resp, err := p.Chat(context.Background(), ChatRequest{Messages: []Msg{{Role: "user", Content: "hi"}}})
	if err != nil {
		t.Fatalf("Chat 失败：%v", err)
	}
	if resp.Content != "hi back" {
		t.Fatalf("Content 期望 hi back，得到 %q", resp.Content)
	}
	if resp.Model != "gpt-4o" {
		t.Fatalf("Model 期望 gpt-4o，得到 %q", resp.Model)
	}
}

func TestOpenAIClientChatModelFallback(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body["model"] != "fallback-model" {
			t.Errorf("req.Model 为空时应兜底为 fallback-model，得到 %v", body["model"])
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"choices": []map[string]any{{"message": map[string]any{"role": "assistant", "content": "x"}}},
		})
	}))
	defer srv.Close()
	p := FromConfig(config.LLMConfig{Enabled: true, APIKey: "k", BaseURL: srv.URL, Model: "fallback-model"})
	resp, err := p.Chat(context.Background(), ChatRequest{}) // req.Model 为空
	if err != nil {
		t.Fatalf("Chat 失败：%v", err)
	}
	if resp.Model != "fallback-model" {
		t.Fatalf("out.Model 应回退为 fallback-model，得到 %q", resp.Model)
	}
}

func TestOpenAIClientChatHTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("boom"))
	}))
	defer srv.Close()
	p := FromConfig(config.LLMConfig{Enabled: true, APIKey: "k", BaseURL: srv.URL, Model: "m"})
	_, err := p.Chat(context.Background(), ChatRequest{})
	if err == nil {
		t.Fatalf("HTTP 500 应返回错误")
	}
	if !strings.Contains(err.Error(), "HTTP 500") {
		t.Fatalf("错误应含 HTTP 500，得到 %q", err.Error())
	}
}

func TestOpenAIClientChatEmptyChoices(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"choices": []any{}})
	}))
	defer srv.Close()
	p := FromConfig(config.LLMConfig{Enabled: true, APIKey: "k", BaseURL: srv.URL, Model: "m"})
	_, err := p.Chat(context.Background(), ChatRequest{})
	if err == nil {
		t.Fatalf("空 choices 应返回错误")
	}
	if !strings.Contains(err.Error(), "空 choices") {
		t.Fatalf("错误应含 空 choices，得到 %q", err.Error())
	}
}

func TestOpenAIClientChatProviderError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"error": map[string]any{"message": "rate limited"},
		})
	}))
	defer srv.Close()
	p := FromConfig(config.LLMConfig{Enabled: true, APIKey: "k", BaseURL: srv.URL, Model: "m"})
	_, err := p.Chat(context.Background(), ChatRequest{})
	if err == nil {
		t.Fatalf("provider error 应返回错误")
	}
	if !strings.Contains(err.Error(), "rate limited") {
		t.Fatalf("错误应透传 rate limited，得到 %q", err.Error())
	}
}
