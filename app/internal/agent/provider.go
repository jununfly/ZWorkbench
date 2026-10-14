package agent

import "context"

// ChatRequest / ChatResponse 是 Provider 统一接口的最小契约（stub）。
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

// Provider 统一 LLM 接口；后续接真实 Responses API（动机②）。
type Provider interface {
	Name() string
	Chat(ctx context.Context, req ChatRequest) (ChatResponse, error)
}

type openAIProvider struct{}

func (openAIProvider) Name() string { return "openai" }
func (openAIProvider) Chat(_ context.Context, req ChatRequest) (ChatResponse, error) {
	return ChatResponse{Model: req.Model, Content: "[stub] openai response"}, nil
}

type deepSeekProvider struct{}

func (deepSeekProvider) Name() string { return "deepseek" }
func (deepSeekProvider) Chat(_ context.Context, req ChatRequest) (ChatResponse, error) {
	return ChatResponse{Model: req.Model, Content: "[stub] deepseek response"}, nil
}

// DefaultProviders 返回可用 provider 注册表（stub，待接真实端点）。
func DefaultProviders() map[string]Provider {
	return map[string]Provider{
		"openai":   openAIProvider{},
		"deepseek": deepSeekProvider{},
	}
}
