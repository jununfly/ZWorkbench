package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/jununfly/ZWorkbench/app/internal/config"
	"github.com/jununfly/ZWorkbench/app/internal/envprobe"
	"github.com/jununfly/ZWorkbench/app/internal/evidence"
	"github.com/jununfly/ZWorkbench/app/internal/execution"
)

// registerExecution 挂载真执行器 API（ADR 0020 首刀）。
//
// 暴露面的边界，逐条写清以免疫未来「顺手加个参数」：
//
//   - profiles 只读：只能查到配置里的档位，永远拿不到「跑任意命令」的能力；
//   - execute 只接受档位名：请求体里没有 command / args / dir 字段可填；
//   - confirm 必须有审批 token：没批准就是 400 + executed=false，不静默开跑；
//   - 执行是**同步**的：响应即结果。本地单用户工具里，让「点执行 → 直接看到
//     退出码与输出」是最好懂的语义；若将来要跑超长任务，再引入作业表 + 异步，
//     而不是现在就为一个假想的并发场景加复杂度。
func registerExecution(
	mux *http.ServeMux,
	auth func(http.HandlerFunc) http.HandlerFunc,
	svc *execution.Service,
	ev *evidence.Owner,
	cfg *config.Config,
) {
	if svc == nil || ev == nil {
		// 执行器不可用时显式 503，而不是让「点执行没反应」被误读成跑完了没输出。
		mux.HandleFunc("/api/execution/", auth(func(w http.ResponseWriter, _ *http.Request) {
			http.Error(w, "executor unavailable", http.StatusServiceUnavailable)
		}))
		return
	}

	// GET /api/execution/profiles —— 可用档位 + 各环境此刻可达性（只读提示）。
	// 可达性只是提示：真执行时仍以执行器结果为准，不拿探测结论替代执行结论。
	mux.HandleFunc("GET /api/execution/profiles", auth(func(w http.ResponseWriter, _ *http.Request) {
		profiles := cfg.ExecutionProfiles().Profiles
		out := make([]map[string]any, 0, len(profiles))
		for _, p := range profiles {
			envs := p.Environments
			if len(envs) == 0 {
				envs = []string{"local"}
			}
			item := map[string]any{
				"name":               p.Name,
				"command":            p.Command,
				"args":               p.Args,
				"environments":       envs,
				"environment_status": envprobe.ProbeAll(envs),
				"timeout_sec":        int(p.EffectiveTimeout().Seconds()),
				"workdir":            p.Workdir,
			}
			// 容器档位要把「跑在哪个镜像/哪个目录/有没有网络」一并暴露：
			// 审批面板若只显示命令，等于让人在看不见执行边界的情况下签字。
			if p.Container != nil {
				item["image"] = p.Container.Image
				item["container_workdir"] = p.Container.EffectiveWorkdir()
				item["container_network"] = p.Container.EffectiveNetwork()
			}
			out = append(out, item)
		}
		writeJSON(w, map[string]any{"profiles": out})
	}))

	// GET /api/evidence/approvals —— 审批列表：?run_id=（空 = 全部）&limit=
	mux.HandleFunc("GET /api/evidence/approvals", auth(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		limit, _ := strconv.Atoi(q.Get("limit"))
		list, err := ev.ListApprovals(q.Get("run_id"), limit)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, list)
	}))

	// POST /api/evidence/runs/{id}/execute —— 请求执行（只认档位名）。
	mux.HandleFunc("POST /api/evidence/runs/{id}/execute", auth(func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Profile string `json:"profile"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		if strings.TrimSpace(body.Profile) == "" {
			http.Error(w, "profile 不能为空（执行只能引用预置档位名）", http.StatusBadRequest)
			return
		}
		out, err := svc.Request(r.PathValue("id"), body.Profile)
		if err != nil {
			http.Error(w, err.Error(), executionStatus(err))
			return
		}
		writeJSON(w, out)
	}))

	// POST /api/evidence/runs/{id}/execute/confirm —— 带审批 token 确认并执行。
	//
	// 不可执行（未批准 / token 不匹配 / 已消费 / run 已终态）返 **200 + executed=false**，
	// 而不是 4xx：服务器确实成功求值了这次请求，结论在 payload 里（claim.status +
	// reason），调用方需要这份结构化诊断才能说清「为什么没跑」。协议层错误
	// （缺 approval_id、JSON 坏）仍然 400。
	mux.HandleFunc("POST /api/evidence/runs/{id}/execute/confirm", auth(func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			ApprovalID string `json:"approval_id"`
			Token      string `json:"token"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		if strings.TrimSpace(body.ApprovalID) == "" {
			http.Error(w, "approval_id 不能为空", http.StatusBadRequest)
			return
		}
		out, err := svc.Confirm(r.Context(), r.PathValue("id"), body.ApprovalID, body.Token)
		if err != nil {
			http.Error(w, err.Error(), executionStatus(err))
			return
		}
		writeJSON(w, out)
	}))

	// POST /api/evidence/approvals/{id}/approve —— 批准并拿一次性 token。
	// token 明文只在此刻出现一次，服务端只存哈希（C28）。
	mux.HandleFunc("POST /api/evidence/approvals/{id}/approve", auth(func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			TTLSeconds int `json:"ttl_seconds"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body) // 省略 body 时用默认 TTL
		if body.TTLSeconds <= 0 {
			body.TTLSeconds = 300
		}
		out, err := ev.Approve(r.PathValue("id"), body.TTLSeconds)
		if err != nil {
			http.Error(w, err.Error(), executionStatus(err))
			return
		}
		writeJSON(w, out)
	}))

	// POST /api/evidence/approvals/{id}/deny —— 拒绝；denied 之后永不可批。
	mux.HandleFunc("POST /api/evidence/approvals/{id}/deny", auth(func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Reason string `json:"reason"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		if strings.TrimSpace(body.Reason) == "" {
			body.Reason = "ui-deny"
		}
		out, err := ev.DenyApproval(r.PathValue("id"), body.Reason)
		if err != nil {
			http.Error(w, err.Error(), executionStatus(err))
			return
		}
		writeJSON(w, out)
	}))
}

// executionStatus 把语义拒绝映射成 4xx。
//
// 这里刻意不把「非法状态」返 500：fail-closed 是设计，不是故障。500 只留给
// 真正没预料到的存储/内部错误，否则监控会把设计内的拒绝当成服务崩溃。
func executionStatus(err error) int {
	switch {
	case errors.Is(err, evidence.ErrRunNotFound), errors.Is(err, evidence.ErrNotFound):
		return http.StatusNotFound
	case errors.Is(err, execution.ErrProfileNotFound),
		errors.Is(err, execution.ErrEnvironmentNotAllowed),
		errors.Is(err, execution.ErrNoWorkdir),
		// 该环境没有执行器（未接线 / 尚未实现）：这是「你指定了一个服务当前
		// 跑不了的环境」，属于请求层面可判定的拒绝，不是服务故障。
		errors.Is(err, execution.ErrExecutorUnavailable),
		errors.Is(err, evidence.ErrBadArgument),
		errors.Is(err, evidence.ErrInvalidTransition),
		errors.Is(err, evidence.ErrApproval):
		return http.StatusBadRequest
	default:
		return http.StatusInternalServerError
	}
}
