package agent

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/config"
)

// ChatRequest / ChatResponse 是 Provider 统一接口的最小契约。
type ChatRequest struct {
	Model    string `json:"model"`
	Messages []Msg  `json:"messages"`
}

type Msg struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ChatResponse struct {
	Model   string `json:"model"`
	Content string `json:"content"`
}

// Provider 统一 LLM 接口（动机②：顺畅对接 LLM provider）。
type Provider interface {
	Name() string
	Chat(ctx context.Context, req ChatRequest) (ChatResponse, error)
}

// FromConfig 按 LLM 配置构造 provider：已启用且有 key → 真实 OpenAI 兼容客户端；
// 否则返回 unconfiguredProvider，调用时给出明确引导（1-5-4）。
func FromConfig(llm config.LLMConfig) Provider {
	if llm.Enabled && llm.APIKey != "" {
		return openAICompatibleClient{
			baseURL: llm.BaseURL,
			apiKey:  llm.APIKey,
			model:   llm.Model,
		}
	}
	return unconfiguredProvider{}
}

// openAICompatibleClient 实现 OpenAI / DeepSeek 兼容的 /chat/completions 端点。
// 纯 stdlib net/http，零外部依赖，符合 ADR 0015（1-5-4 D1/D4）。
type openAICompatibleClient struct {
	baseURL string
	apiKey  string
	model   string
}

func (c openAICompatibleClient) Name() string { return "openai-compatible" }

func (c openAICompatibleClient) Chat(ctx context.Context, req ChatRequest) (ChatResponse, error) {
	model := req.Model
	if model == "" {
		model = c.model
	}

	payload := map[string]any{
		"model":    model,
		"messages": req.Messages,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return ChatResponse{}, err
	}

	base := c.baseURL
	if base == "" {
		base = "https://api.openai.com/v1"
	}
	u := strings.TrimRight(base, "/") + "/chat/completions"

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	if err != nil {
		return ChatResponse{}, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+c.apiKey)

	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return ChatResponse{}, fmt.Errorf("调用 LLM provider 失败：%w", err)
	}
	defer resp.Body.Close()

	data, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return ChatResponse{}, fmt.Errorf("LLM provider 返回 HTTP %d: %s", resp.StatusCode, string(data))
	}

	var out struct {
		Model   string `json:"model"`
		Choices []struct {
			Message Msg `json:"message"`
		} `json:"choices"`
		Error *struct {
			Message string `json:"message"`
		} `json:"error"`
	}
	if err := json.Unmarshal(data, &out); err != nil {
		return ChatResponse{}, fmt.Errorf("解析 LLM 响应失败：%w", err)
	}
	if out.Error != nil && out.Error.Message != "" {
		return ChatResponse{}, fmt.Errorf("LLM provider 错误：%s", out.Error.Message)
	}
	if len(out.Choices) == 0 {
		return ChatResponse{}, fmt.Errorf("LLM provider 返回空 choices")
	}
	outModel := out.Model
	if outModel == "" {
		outModel = model
	}
	return ChatResponse{Model: outModel, Content: out.Choices[0].Message.Content}, nil
}

// unconfiguredProvider 在未配置时给出明确引导，避免静默 stub。
type unconfiguredProvider struct{}

func (unconfiguredProvider) Name() string { return "unconfigured" }
func (unconfiguredProvider) Chat(_ context.Context, _ ChatRequest) (ChatResponse, error) {
	return ChatResponse{}, fmt.Errorf("LLM provider 未配置：请在「设置 / LLM」页填写 BaseURL / API Key / Model 并启用")
}
