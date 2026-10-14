package api

import (
	"encoding/json"
	"net/http"

	"github.com/jununfly/ZWorkbench/app/internal/agent"
	"github.com/jununfly/ZWorkbench/app/internal/config"
	"github.com/jununfly/ZWorkbench/app/internal/data"
	"github.com/jununfly/ZWorkbench/app/internal/domain"
	"github.com/jununfly/ZWorkbench/app/internal/limitup"
	"github.com/jununfly/ZWorkbench/app/internal/market"
)

// NewRouter 构建本地 API：鉴权中间件 + 路由（镜像 ES 本机鉴权范式）。
func NewRouter(cfg *config.Config, store data.Store, tabs []domain.Tab) http.Handler {
	mux := http.NewServeMux()

	// 鉴权：所有 /api/* 需 token（query 或 Bearer）
	auth := func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			// 跨域（dev: Vite :5173 → Go :18080）。prod 同源时此头无害。
			w.Header().Set("Access-Control-Allow-Origin", "*")
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type")
			if r.Method == "OPTIONS" {
				w.WriteHeader(http.StatusNoContent)
				return
			}
			tok := r.URL.Query().Get("token")
			if tok == "" {
				tok = bearer(r.Header.Get("Authorization"))
			}
			if tok != cfg.Token {
				http.Error(w, "unauthorized", http.StatusUnauthorized)
				return
			}
			next(w, r)
		}
	}

	mux.HandleFunc("/api/health", auth(func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, map[string]string{"status": "ok", "runtime": "go"})
	}))

	mux.HandleFunc("/api/tabs", auth(func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, tabs)
	}))

	// 镜像 ES 行情总览（C07）—— C36 多源适配/回退（远程优先，失败回退本地快照）
	mux.HandleFunc("/api/stock/overview", auth(func(w http.ResponseWriter, r *http.Request) {
		chain := market.NewDefaultChain()
		ov, err := chain.Fetch(r.Context())
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		writeJSON(w, ov)
	}))

	// 镜像 ES 超短连板/题材/情绪（C09）—— C36 多源适配/回退（同 C07 范式）
	mux.HandleFunc("/api/stock/limitup", auth(func(w http.ResponseWriter, r *http.Request) {
		chain := limitup.NewDefaultChain()
		board, err := chain.Fetch(r.Context())
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		writeJSON(w, board)
	}))

	mux.HandleFunc("/api/agent/chat", auth(func(w http.ResponseWriter, r *http.Request) {
		var req agent.ChatRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		p := agent.FromConfig(cfg.LLM()) // 每次请求读取最新配置，PUT /api/config 后立即生效
		resp, err := p.Chat(r.Context(), req)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		writeJSON(w, resp)
	}))

	// 「设置 / LLM」页后端：读取/写入 provider 配置（持久化到 config.json）。
	mux.HandleFunc("/api/config", auth(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			llm := cfg.LLM()
			writeJSON(w, map[string]any{
				"llm": map[string]any{
					"base_url":    llm.BaseURL,
					"model":       llm.Model,
					"enabled":     llm.Enabled,
					"api_key_set": llm.APIKey != "",
				},
			})
		case http.MethodPut, http.MethodPost:
			var body struct {
				LLM struct {
					BaseURL string `json:"base_url"`
					APIKey  string `json:"api_key"`
					Model   string `json:"model"`
					Enabled bool   `json:"enabled"`
				} `json:"llm"`
			}
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				http.Error(w, "bad request", http.StatusBadRequest)
				return
			}
			in := body.LLM
			// api_key 留空或传掩码占位时，保留原值（避免清空已存 key）。
			if in.APIKey == "" || in.APIKey == "********" {
				in.APIKey = cfg.LLM().APIKey
			}
			cfg.SetLLM(config.LLMConfig{
				BaseURL: in.BaseURL,
				APIKey:  in.APIKey,
				Model:   in.Model,
				Enabled: in.Enabled,
			})
			if err := cfg.SaveLLM(); err != nil {
				http.Error(w, "save failed: "+err.Error(), http.StatusInternalServerError)
				return
			}
			writeJSON(w, map[string]any{"ok": true, "api_key_set": cfg.LLM().APIKey != ""})
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	}))

	return mux
}

func bearer(h string) string {
	const p = "Bearer "
	if len(h) > len(p) && h[:len(p)] == p {
		return h[len(p):]
	}
	return ""
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_ = json.NewEncoder(w).Encode(v)
}
