package api

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"sync/atomic"

	"github.com/jununfly/ZWorkbench/app/internal/evidence"
)

// registerEvidence 挂载本地证据 API（ADR 0016; formerly roadmap 1-5-6-3）：
// run 生命周期 + safe-stop 事件流 + identity 完整性。
//
// 范围（B2-narrow 接线版）：只读可视化 + 最小生命周期驱动。
// 不含 approval / effect 的写操作——1-5-6-2 已实现 ClaimEffect/Approve 等能力，
// 但对外暴露需要 human-in-the-loop 的审批界面，留作后续节点，不在本节点静默开放。
// 1-4-4 新增 identity-chain / attempts 两个只读查询口；1-4-5 新增
// safe-stop-on-violation / reconcile-identity 两个**安全方向**的 owner 动作
// （只把 run 往终态推，不放行副作用执行）。effect 写路径（ClaimEffect/Approve）
// 始终不开放。
func registerEvidence(mux *http.ServeMux, auth func(http.HandlerFunc) http.HandlerFunc, ev *evidence.Owner) {
	if ev == nil {
		// 证据库不可用时显式 503，而不是让 tab 静默空白（空白会被误读成"没有证据"）。
		mux.HandleFunc("/api/evidence/", auth(func(w http.ResponseWriter, _ *http.Request) {
			http.Error(w, "evidence store unavailable", http.StatusServiceUnavailable)
		}))
		return
	}

	// GET /api/evidence/runs —— 列表（不含事件投影，便于列表渲染）
	mux.HandleFunc("GET /api/evidence/runs", auth(func(w http.ResponseWriter, _ *http.Request) {
		runs, err := ev.ListRuns()
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, runs)
	}))

	// POST /api/evidence/runs —— 建 run（run_id 可省略，服务端生成）
	mux.HandleFunc("POST /api/evidence/runs", auth(func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			RunID    string         `json:"run_id"`
			TaskType string         `json:"task_type"`
			Input    any            `json:"input"`
			Metadata map[string]any `json:"metadata"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		if body.TaskType == "" {
			body.TaskType = "manual"
		}
		if body.RunID == "" {
			body.RunID = newRunID()
		}
		run, err := ev.CreateRun(body.RunID, body.TaskType, body.Input, body.Metadata)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, run)
	}))

	// GET /api/evidence/runs/{id} —— 详情（含 events / effects / exposure 投影）
	mux.HandleFunc("GET /api/evidence/runs/{id}", auth(func(w http.ResponseWriter, r *http.Request) {
		run, err := ev.GetRun(r.PathValue("id"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		writeJSON(w, run)
	}))

	// POST /api/evidence/runs/{id}/transition —— 驱动生命周期（最小集，便于可视化验证）
	mux.HandleFunc("POST /api/evidence/runs/{id}/transition", auth(func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		var body struct {
			Action string `json:"action"` // start|complete|fail|safe_stop|recover
			Reason string `json:"reason"`
			Result any    `json:"result"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		var (
			run *evidence.Run
			err error
		)
		switch body.Action {
		case "start":
			run, err = ev.StartRun(id)
		case "complete":
			run, err = ev.CompleteRun(id, body.Result)
		case "fail":
			run, err = ev.FailRun(id, body.Result)
		case "safe_stop":
			run, err = ev.SafeStopRun(id, body.Reason)
		case "recover":
			run, err = ev.BeginRecovery(id, body.Reason)
		default:
			http.Error(w, "unknown action: "+body.Action, http.StatusBadRequest)
			return
		}
		if err != nil {
			// 非法转移 / 未知 run 都是语义拒绝（fail-closed 是设计），不是服务故障 → 400。
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		writeJSON(w, run)
	}))

	// POST /api/evidence/runs/{id}/safe-stop-on-violation —— 扫身份图，有未解析引用就 safe-stop（1-4-5）。
	// 无违例 = 不改状态（检测本身不中断健康 run）；未知 run = 404。
	mux.HandleFunc("POST /api/evidence/runs/{id}/safe-stop-on-violation", auth(func(w http.ResponseWriter, r *http.Request) {
		out, err := ev.SafeStopOnIdentityViolation(r.PathValue("id"))
		if err != nil {
			status := http.StatusBadRequest
			if isNotFound(err) {
				status = http.StatusNotFound
			}
			http.Error(w, err.Error(), status)
			return
		}
		writeJSON(w, out)
	}))

	// POST /api/evidence/runs/{id}/reconcile-identity —— 记录身份收口决策并复查（1-4-5）。
	// outcome=resolved 时不改状态（safe_stopped 是终态，收口成功也不复活）。
	mux.HandleFunc("POST /api/evidence/runs/{id}/reconcile-identity", auth(func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Evidence any `json:"evidence"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body) // 无 body 也允许（evidence 本就不落盘）
		out, err := ev.ReconcileIdentity(r.PathValue("id"), body.Evidence)
		if err != nil {
			status := http.StatusBadRequest
			if isNotFound(err) {
				status = http.StatusNotFound
			}
			http.Error(w, err.Error(), status)
			return
		}
		writeJSON(w, out)
	}))

	// GET /api/evidence/events —— 事件流：?run_id= &type= &limit=
	// type=run.safe_stopped 即 C28 安全停止事件流，是本 tab 的核心视图。
	mux.HandleFunc("GET /api/evidence/events", auth(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		limit, _ := strconv.Atoi(q.Get("limit"))
		events, err := ev.ListEvents(q.Get("run_id"), q.Get("type"), limit)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, events)
	}))

	// GET /api/evidence/violations —— 引用完整性审计：?run_id=（空 = 全 owner 审计）
	mux.HandleFunc("GET /api/evidence/violations", auth(func(w http.ResponseWriter, r *http.Request) {
		v, err := ev.DetectIdentityViolations(r.URL.Query().Get("run_id"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, v)
	}))

	// GET /api/evidence/identity-chain —— 身份链（run → attempt → effect → approval，1-4-4）。
	// 入参四选一：?run_id= / ?effect_id= / ?approval_id= / ?operation_id=。
	// 多选或都不选 = 400（歧义必须拒绝，不猜）；查不到 = 404（绝不返空链冒充"没数据"）。
	mux.HandleFunc("GET /api/evidence/identity-chain", auth(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		pairs := []struct{ kind, value string }{
			{evidence.EntryRunID, q.Get("run_id")},
			{evidence.EntryEffectID, q.Get("effect_id")},
			{evidence.EntryApprovalID, q.Get("approval_id")},
			{evidence.EntryOperationID, q.Get("operation_id")},
		}
		var kind, id string
		hits := 0
		for _, p := range pairs {
			if p.value == "" {
				continue
			}
			kind, id, hits = p.kind, p.value, hits+1
		}
		if hits != 1 {
			http.Error(w, "需要且仅需要 run_id / effect_id / approval_id / operation_id 之一", http.StatusBadRequest)
			return
		}
		chain, err := ev.ResolveIdentityChain(kind, id)
		if err != nil {
			// 未知 id / 歧义归属都是语义拒绝（fail-closed 是设计），不是服务故障 → 4xx。
			status := http.StatusBadRequest
			if isNotFound(err) {
				status = http.StatusNotFound
			}
			http.Error(w, err.Error(), status)
			return
		}
		writeJSON(w, chain)
	}))

	// GET /api/evidence/effects/{id}/attempts —— 一次 effect 的全部物理尝试（身份链的 attempt 段）。
	mux.HandleFunc("GET /api/evidence/effects/{id}/attempts", auth(func(w http.ResponseWriter, r *http.Request) {
		attempts, err := ev.ListEffectAttempts(r.PathValue("id"))
		if err != nil {
			status := http.StatusBadRequest
			if isNotFound(err) {
				status = http.StatusNotFound
			}
			http.Error(w, err.Error(), status)
			return
		}
		writeJSON(w, attempts)
	}))
}

// isNotFound 判定「查不到」语义：run 缺失是 ErrRunNotFound，其余实体是 ErrNotFound。
// 二者都是 fail-closed 的语义拒绝（404），不是服务故障（500）。
func isNotFound(err error) bool {
	return errors.Is(err, evidence.ErrNotFound) || errors.Is(err, evidence.ErrRunNotFound)
}

var runIDFallback atomic.Uint64

// newRunID 生成 run 标识；crypto/rand 不可用时才退化为计数器（不引入时钟依赖）。
func newRunID() string {
	b := make([]byte, 8)
	if _, err := rand.Read(b); err != nil {
		return "run-" + strconv.FormatUint(runIDFallback.Add(1), 10)
	}
	return "run-" + hex.EncodeToString(b)
}
