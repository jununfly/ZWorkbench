package api

import (
	"context"
	"encoding/json"
	"net/http"
	"path/filepath"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/agent"
	"github.com/jununfly/ZWorkbench/app/internal/config"
	"github.com/jununfly/ZWorkbench/app/internal/data"
	"github.com/jununfly/ZWorkbench/app/internal/domain"
	"github.com/jununfly/ZWorkbench/app/internal/evidence"
	"github.com/jununfly/ZWorkbench/app/internal/inspection"
	"github.com/jununfly/ZWorkbench/app/internal/limitup"
	"github.com/jununfly/ZWorkbench/app/internal/market"
	"github.com/jununfly/ZWorkbench/app/internal/mastery"
	"github.com/jununfly/ZWorkbench/app/internal/optimization"
	"github.com/jununfly/ZWorkbench/app/internal/research"
	"github.com/jununfly/ZWorkbench/app/internal/review"
	"github.com/jununfly/ZWorkbench/app/internal/vcs"
	"github.com/jununfly/ZWorkbench/app/internal/webstatic"
)

// NewRouter 构建本地 API：鉴权中间件 + 路由（镜像 ES 本机鉴权范式）。
// ev 为本地证据 owner（1-5-6 的 Go evidence 包）；传 nil 时 /api/evidence/* 返回 503。
func NewRouter(cfg *config.Config, store data.Store, tabs []domain.Tab, ev *evidence.Owner) http.Handler {
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
		chain := market.NewDefaultChain(cfg.DataSource())
		ov, err := chain.Fetch(r.Context())
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		writeJSON(w, ov)
	}))

	// 镜像 ES 超短连板/题材/情绪（C09）—— C36 多源适配/回退（同 C07 范式）
	mux.HandleFunc("/api/stock/limitup", auth(func(w http.ResponseWriter, r *http.Request) {
		chain := limitup.NewDefaultChain(cfg.DataSource())
		board, err := chain.Fetch(r.Context())
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		writeJSON(w, board)
	}))

	// 镜像 ES 个股分级研究（C08）—— C36 多源适配/回退
	mux.HandleFunc("/api/stock/research", auth(func(w http.ResponseWriter, r *http.Request) {
		chain := research.NewDefaultChain(cfg.DataSource())
		body, err := chain.Fetch(r.Context())
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		writeJSON(w, body)
	}))

	// 镜像 ES 大V自动复盘（C10）—— C36 多源适配/回退
	mux.HandleFunc("/api/stock/review", auth(func(w http.ResponseWriter, r *http.Request) {
		chain := review.NewDefaultChain(cfg.DataSource())
		body, err := chain.Fetch(r.Context())
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		writeJSON(w, body)
	}))

	// 镜像 ES 持仓AI巡检（C11）—— C36 多源适配/回退；真实持仓文件优先（1-2-4 D11）
	mux.HandleFunc("/api/portfolio/inspection", auth(func(w http.ResponseWriter, r *http.Request) {
		chain := inspection.NewDefaultChain(cfg.DataSource(), cfg.PortfolioPath())
		body, err := chain.Fetch(r.Context())
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		writeJSON(w, body)
	}))

	// 镜像 ES AI持仓优化（C12）—— C36 多源适配/回退；真实持仓文件优先（1-2-4 D12）
	mux.HandleFunc("/api/portfolio/optimization", auth(func(w http.ResponseWriter, r *http.Request) {
		chain := optimization.NewDefaultChain(cfg.DataSource(), cfg.PortfolioPath())
		body, err := chain.Fetch(r.Context())
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		writeJSON(w, body)
	}))

	// 镜像 ES 游资心法与AI Copilot（C19）—— C36 多源适配/回退
	mux.HandleFunc("/api/mastery", auth(func(w http.ResponseWriter, r *http.Request) {
		// 导入文件（本地可导入数据集）优先，见 ADR 0017; formerly roadmap 1-2-3 D9。
		chain := mastery.NewDefaultChain(cfg.DataSource(), cfg.MasteryPath())
		body, err := chain.Fetch(r.Context())
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		writeJSON(w, body)
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

	// 本地证据底座（1-5-5）：列 / 存快照。让 router 既有的 store 参数真正被使用。
	mux.HandleFunc("/api/snapshots", auth(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			topic := r.URL.Query().Get("topic")
			writeJSON(w, store.List(topic))
		case http.MethodPost:
			var snap struct {
				ID              string `json:"id"`
				Topic           string `json:"topic"`
				Source          string `json:"source"`
				Payload         string `json:"payload"`
				CreatedAt       string `json:"created_at"`
				CompositionOwner string `json:"composition_owner"`
			}
			if err := json.NewDecoder(r.Body).Decode(&snap); err != nil {
				http.Error(w, "bad request", http.StatusBadRequest)
				return
			}
			if snap.ID == "" {
				http.Error(w, "id required", http.StatusBadRequest)
				return
			}
			if err := store.Save(data.Snapshot{
				ID:              snap.ID,
				Topic:           snap.Topic,
				Source:          snap.Source,
				Payload:         snap.Payload,
				CreatedAt:       snap.CreatedAt,
				CompositionOwner: snap.CompositionOwner,
			}); err != nil {
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}
			writeJSON(w, map[string]any{"ok": true, "id": snap.ID})
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	}))

	// 「设置 / LLM」页后端：读取/写入 provider 配置（持久化到 config.json）。
	// 1-2-1：返回体同时暴露 data_source 开关状态（enabled/base_url/token_set/timeout_sec），
	// 便于前端显示「现在哪个远端在生效」，区分未配置/源失败/陈旧快照。
	mux.HandleFunc("/api/config", auth(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			llm := cfg.LLM()
			ds := cfg.DataSource()
			writeJSON(w, map[string]any{
				"llm": map[string]any{
					"base_url":    llm.BaseURL,
					"model":       llm.Model,
					"enabled":     llm.Enabled,
					"api_key_set": llm.APIKey != "",
				},
				"data_source": map[string]any{
					"enabled":      ds.Enabled,
					"base_url":     ds.BaseURL,
					"token_set":    ds.Token != "",
					"timeout_sec":  ds.TimeoutSec,
					"usable":       ds.Usable(),
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
				DataSource struct {
					BaseURL    string `json:"base_url"`
					Token      string `json:"token"`
					Enabled    bool   `json:"enabled"`
					TimeoutSec int    `json:"timeout_sec"`
				} `json:"data_source"`
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
			// 1-3-2 fail-closed：启用却最终无 key，明确拒绝，避免
			// FromConfig 静默退回 unconfigured 而前端却显示「已启用」。
			if in.Enabled && in.APIKey == "" {
				http.Error(w, "启用 LLM 需要提供 API Key（留空表示保留原值，但原值也为空）", http.StatusBadRequest)
				return
			}
			cfg.SetLLM(config.LLMConfig{
				BaseURL: in.BaseURL,
				APIKey:  in.APIKey,
				Model:   in.Model,
				Enabled: in.Enabled,
			})
			dsIn := body.DataSource
			// token 留空时保留原值（避免清空已存 token）。
			tok := dsIn.Token
			if tok == "" || tok == "********" {
				tok = cfg.DataSource().Token
			}
			cfg.SetDataSource(config.DataSourceConfig{
				BaseURL:    dsIn.BaseURL,
				Token:      tok,
				Enabled:    dsIn.Enabled,
				TimeoutSec: dsIn.TimeoutSec,
			})
			if err := cfg.SaveDataSource(); err != nil {
				http.Error(w, "save failed: "+err.Error(), http.StatusInternalServerError)
				return
			}
			writeJSON(w, map[string]any{
				"ok":          true,
				"api_key_set": cfg.LLM().APIKey != "",
				"data_source": map[string]any{
					"enabled":     cfg.DataSource().Enabled,
					"base_url":    cfg.DataSource().BaseURL,
					"token_set":   cfg.DataSource().Token != "",
					"timeout_sec": cfg.DataSource().TimeoutSec,
					"usable":      cfg.DataSource().Usable(),
				},
			})
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	}))

	// 1-3-3 Settings 页连通性自检：轻量探针，复用真实客户端做最小调用，
	// 返回结构化 {ok, latency_ms, model, error}。探针本身恒 200，负结果走 ok:false，
	// 前端据此渲染绿/红徽标与真实错误（错误直显），不依赖全量对话。
	mux.HandleFunc("/api/config/test", auth(func(w http.ResponseWriter, r *http.Request) {
		llm := cfg.LLM()
		if !llm.Enabled || llm.APIKey == "" {
			writeJSON(w, map[string]any{
				"ok":         false,
				"error":      "LLM 未启用或未配置 API Key（请先在上方填写并保存）",
				"latency_ms": 0,
			})
			return
		}
		p := agent.FromConfig(llm)
		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		start := time.Now()
		resp, err := p.Chat(ctx, agent.ChatRequest{
			Messages: []agent.Msg{{Role: "user", Content: "ping"}},
		})
		latency := time.Since(start).Milliseconds()
		if err != nil {
			writeJSON(w, map[string]any{
				"ok":         false,
				"error":      err.Error(),
				"latency_ms": latency,
			})
			return
		}
		writeJSON(w, map[string]any{
			"ok":         true,
			"model":      resp.Model,
			"latency_ms": latency,
		})
	}))

	// 编码证据上下文（ADR 0019）：被管理仓库列表 + 每仓当前分支，供前端 chips 预填。
	// git 探测失败一律 unknown，本端点恒 200，绝不 500。
	mux.HandleFunc("GET /api/context", auth(func(w http.ResponseWriter, _ *http.Request) {
		repos := cfg.ManagedRepos().Repos
		// 无显式配置时，把「当前工作目录所在 git 仓库」自动登记为默认被管理仓库
		// （如 ZWorkbench 自身），让开箱即有语境；非 git 仓库则留空。
		if len(repos) == 0 {
			if p, ok := vcs.Toplevel("."); ok {
				repos = []config.RepoSpec{{
					Name:         filepath.Base(p),
					Path:         p,
					Environments: []string{"local"},
				}}
			}
		}
		out := make([]map[string]any, 0, len(repos))
		defaultRepo := ""
		for i, r := range repos {
			branch := vcs.CurrentBranch(r.Path)
			envs := r.Environments
			if len(envs) == 0 {
				envs = []string{"local"}
			}
			out = append(out, map[string]any{
				"name":         r.Name,
				"path":         r.Path,
				"environments": envs,
				"current_branch": branch,
			})
			if i == 0 {
				defaultRepo = r.Name
			}
		}
		writeJSON(w, map[string]any{
			"repos":               out,
			"default_repo":        defaultRepo,
			"default_environment": "local",
		})
	}))

	// 本地证据（1-5-6-3）：run 生命周期 + safe-stop 事件流 + identity 完整性。
	registerEvidence(mux, auth, ev)

	// 前端托管（1-1-3）：打包后窗口加载 http://127.0.0.1:<port>/ 必须拿到 SPA，
	// 否则只会显示 404。产物缺失时该 handler 返 503 + 明确文案（fail-closed）。
	mux.Handle("/", webstatic.NewHandler(webstatic.Dir(cfg.WebDir)))

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
