package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"testing"

	"github.com/jununfly/ZWorkbench/app/internal/config"
	"github.com/jununfly/ZWorkbench/app/internal/evidence"
	"github.com/jununfly/ZWorkbench/app/internal/execution"
)

// 执行 API 的契约（ADR 0020）：
//   - profiles 只读暴露档位 + 环境可达性（不含任意 argv 入口）；
//   - execute 只接受**档位名**，不接受命令/参数；
//   - confirm 走审批 token，未批准一律 400 且 executed=false；
//   - 所有语义拒绝都是 4xx，不拿 500 掩盖。

// newExecRouter 建一个带执行档位的路由：档位用真实 echo，
// 让接线本身被端到端验证（真起进程、真记账），而不是只测假对象。
func newExecRouter(t *testing.T) (http.Handler, *evidence.Owner, string) {
	t.Helper()
	return newExecRouterWithProfiles(t, []config.ExecutionProfile{
		{Name: "echo-ok", Command: "echo", Args: []string{"hi"}, TimeoutSec: 20},
	})
}

// newExecRouterWithProfiles 允许用例自定义档位集合（例如容器档位）。
func newExecRouterWithProfiles(t *testing.T, profiles []config.ExecutionProfile) (http.Handler, *evidence.Owner, string) {
	t.Helper()
	ev, err := evidence.Open(":memory:")
	if err != nil {
		t.Fatalf("evidence.Open: %v", err)
	}
	t.Cleanup(func() { _ = ev.Close() })

	repoDir := t.TempDir()
	cfg := &config.Config{Port: "18080", Token: testToken}
	cfg.SetManagedRepos(config.ManagedRepos{Repos: []config.RepoSpec{
		{Name: "ZW", Path: repoDir, Environments: []string{"local", "container"}},
	}})
	cfg.SetExecutionProfiles(config.ExecutionProfiles{Profiles: profiles})
	return NewRouter(cfg, nil, nil, ev), ev, repoDir
}

// createRun 建一个带 local 语境的 run，返回 run_id。
func createRun(t *testing.T, h http.Handler) string {
	t.Helper()
	rec := doJSON(t, h, "POST", "/api/evidence/runs?token="+testToken, map[string]any{
		"task_type":   "execution",
		"repo":        "ZW",
		"environment": "local",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("create run code=%d body=%s", rec.Code, rec.Body.String())
	}
	var run evidence.Run
	if err := json.Unmarshal(rec.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	return run.RunID
}

func TestListExecutionProfiles(t *testing.T) {
	h, _, repoDir := newExecRouter(t)

	rec := doJSON(t, h, "GET", "/api/execution/profiles?token="+testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
	var out struct {
		Profiles []struct {
			Name         string   `json:"name"`
			Command      string   `json:"command"`
			Args         []string `json:"args"`
			TimeoutSec   int      `json:"timeout_sec"`
			Environments []string `json:"environments"`
		} `json:"profiles"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v (%s)", err, rec.Body.String())
	}
	if len(out.Profiles) != 1 || out.Profiles[0].Name != "echo-ok" {
		t.Fatalf("档位列表不符：%#v", out.Profiles)
	}
	if out.Profiles[0].Command != "echo" || len(out.Profiles[0].Args) != 1 {
		t.Fatalf("档位内容不符：%#v", out.Profiles[0])
	}
	// 未声明环境时应回退 local（与 AllowsEnvironment 一致）。
	if len(out.Profiles[0].Environments) != 1 || out.Profiles[0].Environments[0] != "local" {
		t.Fatalf("环境枚举应回退 local，实际 %#v", out.Profiles[0].Environments)
	}
	if out.Profiles[0].TimeoutSec != 20 {
		t.Fatalf("timeout_sec 不符：%d", out.Profiles[0].TimeoutSec)
	}
	_ = repoDir
}

func TestExecuteRequestCreatesApproval(t *testing.T) {
	h, ev, _ := newExecRouter(t)
	runID := createRun(t, h)

	rec := doJSON(t, h, "POST", "/api/evidence/runs/"+runID+"/execute?token="+testToken, map[string]any{
		"profile": "echo-ok",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
	var out struct {
		Approval struct {
			ApprovalID string `json:"approval_id"`
			Status     string `json:"status"`
			Action     string `json:"action"`
		} `json:"approval"`
		Profile string `json:"profile"`
		Command string `json:"command"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v (%s)", err, rec.Body.String())
	}
	if out.Approval.Status != "pending" || out.Approval.Action != "execute" {
		t.Fatalf("应创建 pending 执行审批，实际 %#v", out.Approval)
	}
	if out.Command != "echo" {
		t.Fatalf("响应应回显将要执行的命令（批准前先能看），实际 %q", out.Command)
	}

	run, err := ev.GetRun(runID)
	if err != nil {
		t.Fatalf("GetRun: %v", err)
	}
	if run.Status != evidence.StatusWaitingApproval {
		t.Fatalf("run 应进 waiting_approval，实际 %s", run.Status)
	}
}

func TestExecuteUnknownProfileReturns400(t *testing.T) {
	h, _, _ := newExecRouter(t)
	runID := createRun(t, h)

	rec := doJSON(t, h, "POST", "/api/evidence/runs/"+runID+"/execute?token="+testToken, map[string]any{
		"profile": "nope",
	})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("未知档位应 400，实际 %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestExecuteMissingProfileReturns400(t *testing.T) {
	h, _, _ := newExecRouter(t)
	runID := createRun(t, h)

	rec := doJSON(t, h, "POST", "/api/evidence/runs/"+runID+"/execute?token="+testToken, map[string]any{})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("缺 profile 应 400，实际 %d", rec.Code)
	}
}

func TestExecuteUnknownRunReturns404(t *testing.T) {
	h, _, _ := newExecRouter(t)

	rec := doJSON(t, h, "POST", "/api/evidence/runs/nope/execute?token="+testToken, map[string]any{
		"profile": "echo-ok",
	})
	if rec.Code != http.StatusNotFound {
		t.Fatalf("未知 run 应 404，实际 %d body=%s", rec.Code, rec.Body.String())
	}
}

// TestConfirmWithoutApprovalReturnsExecutedFalse 是审批门的 API 侧断言：
// 没批准时不仅不执行，还要给出 executed=false 让人看得懂「为什么没跑」。
func TestConfirmWithoutApprovalReturnsExecutedFalse(t *testing.T) {
	h, ev, _ := newExecRouter(t)
	runID := createRun(t, h)
	req := doJSON(t, h, "POST", "/api/evidence/runs/"+runID+"/execute?token="+testToken, map[string]any{
		"profile": "echo-ok",
	})
	if req.Code != http.StatusOK {
		t.Fatalf("request code=%d body=%s", req.Code, req.Body.String())
	}
	var rr struct {
		Approval struct {
			ApprovalID string `json:"approval_id"`
		} `json:"approval"`
	}
	if err := json.Unmarshal(req.Body.Bytes(), &rr); err != nil {
		t.Fatalf("decode: %v", err)
	}

	rec := doJSON(t, h, "POST", "/api/evidence/runs/"+runID+"/execute/confirm?token="+testToken, map[string]any{
		"approval_id": rr.Approval.ApprovalID,
		"token":       "",
	})
	// 200 + executed=false：服务器成功求值了这次请求，结论是「不执行」。
	// 用 4xx 会逼前端在异常分支里解析诊断信息，反而更容易把拒绝原因丢掉。
	if rec.Code != http.StatusOK {
		t.Fatalf("未批准应 200+executed=0，实际 %d body=%s", rec.Code, rec.Body.String())
	}
	var out struct {
		Executed bool   `json:"executed"`
		Reason   string `json:"reason"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if out.Executed {
		t.Fatal("未批准绝不允许 executed=true")
	}
	if out.Reason == "" {
		t.Fatal("应给出可读的拒绝原因")
	}

	run, _ := ev.GetRun(runID)
	if run.Status != evidence.StatusWaitingApproval {
		t.Fatalf("run 应停在 waiting_approval，实际 %s", run.Status)
	}
}

// TestExecuteEndToEnd 走完整链路：请求 → 批准 → 确认 → run completed + 事件齐全。
func TestExecuteEndToEnd(t *testing.T) {
	h, ev, _ := newExecRouter(t)
	runID := createRun(t, h)

	req := doJSON(t, h, "POST", "/api/evidence/runs/"+runID+"/execute?token="+testToken, map[string]any{
		"profile": "echo-ok",
	})
	if req.Code != http.StatusOK {
		t.Fatalf("request code=%d body=%s", req.Code, req.Body.String())
	}
	var rr struct {
		Approval struct {
			ApprovalID string `json:"approval_id"`
		} `json:"approval"`
	}
	_ = json.Unmarshal(req.Body.Bytes(), &rr)

	appr := doJSON(t, h, "POST", "/api/evidence/approvals/"+rr.Approval.ApprovalID+"/approve?token="+testToken, map[string]any{
		"ttl_seconds": 300,
	})
	if appr.Code != http.StatusOK {
		t.Fatalf("approve code=%d body=%s", appr.Code, appr.Body.String())
	}
	var tok struct {
		Token string `json:"token"`
	}
	if err := json.Unmarshal(appr.Body.Bytes(), &tok); err != nil {
		t.Fatalf("decode token: %v", err)
	}
	if tok.Token == "" {
		t.Fatal("批准必须返回一次性 token")
	}

	conf := doJSON(t, h, "POST", "/api/evidence/runs/"+runID+"/execute/confirm?token="+testToken, map[string]any{
		"approval_id": rr.Approval.ApprovalID,
		"token":       tok.Token,
	})
	if conf.Code != http.StatusOK {
		t.Fatalf("confirm code=%d body=%s", conf.Code, conf.Body.String())
	}
	var cr struct {
		Executed bool `json:"executed"`
		Result   struct {
			ExitCode int    `json:"exit_code"`
			Stdout   string `json:"stdout"`
		} `json:"result"`
		Run struct {
			Status string `json:"status"`
		} `json:"run"`
	}
	if err := json.Unmarshal(conf.Body.Bytes(), &cr); err != nil {
		t.Fatalf("decode confirm: %v (%s)", err, conf.Body.String())
	}
	if !cr.Executed {
		t.Fatalf("已批准应执行，body=%s", conf.Body.String())
	}
	if cr.Result.ExitCode != 0 {
		t.Fatalf("echo 应退出 0，实际 %d", cr.Result.ExitCode)
	}
	if cr.Result.Stdout == "" {
		t.Fatal("应返回真实 stdout")
	}
	if cr.Run.Status != string(evidence.StatusCompleted) {
		t.Fatalf("run 应 completed，实际 %s", cr.Run.Status)
	}

	// 证据链：事件里必须有 started/stdout/finished。
	events, err := ev.ListEvents(runID, "", 200)
	if err != nil {
		t.Fatalf("ListEvents: %v", err)
	}
	seen := map[string]bool{}
	for _, e := range events {
		seen[e.Type] = true
	}
	for _, want := range []string{"execution.started", "execution.stdout", "execution.finished", "effect.completed"} {
		if !seen[want] {
			t.Fatalf("缺少事件 %q，实际 %v", want, seen)
		}
	}
}

func TestDenyApproval(t *testing.T) {
	h, ev, _ := newExecRouter(t)
	runID := createRun(t, h)
	req := doJSON(t, h, "POST", "/api/evidence/runs/"+runID+"/execute?token="+testToken, map[string]any{
		"profile": "echo-ok",
	})
	var rr struct {
		Approval struct {
			ApprovalID string `json:"approval_id"`
		} `json:"approval"`
	}
	_ = json.Unmarshal(req.Body.Bytes(), &rr)

	rec := doJSON(t, h, "POST", "/api/evidence/approvals/"+rr.Approval.ApprovalID+"/deny?token="+testToken, map[string]any{
		"reason": "不允许在本地跑",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("deny code=%d body=%s", rec.Code, rec.Body.String())
	}
	var out evidence.Approval
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if out.Status != "denied" {
		t.Fatalf("应为 denied，实际 %s", out.Status)
	}

	// denied 之后不能再批准（fail-closed）。
	again := doJSON(t, h, "POST", "/api/evidence/approvals/"+rr.Approval.ApprovalID+"/approve?token="+testToken, map[string]any{
		"ttl_seconds": 300,
	})
	if again.Code != http.StatusBadRequest {
		t.Fatalf("denied 后再批准应 400，实际 %d body=%s", again.Code, again.Body.String())
	}
	_ = ev
}

func TestListApprovalsByRun(t *testing.T) {
	h, _, _ := newExecRouter(t)
	runID := createRun(t, h)
	doJSON(t, h, "POST", "/api/evidence/runs/"+runID+"/execute?token="+testToken, map[string]any{
		"profile": "echo-ok",
	})

	rec := doJSON(t, h, "GET", "/api/evidence/approvals?run_id="+runID+"&token="+testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
	var list []evidence.Approval
	if err := json.Unmarshal(rec.Body.Bytes(), &list); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(list) != 1 || list[0].Action != "execute" {
		t.Fatalf("应列出该 run 的执行审批，实际 %#v", list)
	}
	// 审批列表绝不能带 token 哈希出库。
	if b := rec.Body.String(); containsAny(b, "token_hash", "tokenHash") {
		t.Fatalf("审批列表不应包含 token_hash：%s", b)
	}
}

func TestExecutionRequiresAuth(t *testing.T) {
	h, _, _ := newExecRouter(t)
	rec := doJSON(t, h, "GET", "/api/execution/profiles", nil)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("无 token 应 401，实际 %d", rec.Code)
	}
}

func containsAny(s string, subs ...string) bool {
	for _, sub := range subs {
		if len(sub) > 0 && len(s) >= len(sub) {
			for i := 0; i+len(sub) <= len(s); i++ {
				if s[i:i+len(sub)] == sub {
					return true
				}
			}
		}
	}
	return false
}

// 容器档位必须在 profiles 里暴露镜像/容器内目录/网络：
// 审批面板只显示命令等于让人在看不见执行边界的情况下签字。
func TestListExecutionProfilesExposesContainerFields(t *testing.T) {
	h, _, _ := newExecRouterWithProfiles(t, []config.ExecutionProfile{
		{
			Name:         "echo-ctr",
			Command:      "echo",
			Args:         []string{"hi"},
			Environments: []string{"container"},
			Container:    &config.ContainerConfig{Image: "alpine:3.20", Network: "bridge"},
		},
	})

	rec := doJSON(t, h, "GET", "/api/execution/profiles?token="+testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
	var out struct {
		Profiles []struct {
			Name             string   `json:"name"`
			Environments     []string `json:"environments"`
			Image            string   `json:"image"`
			ContainerWorkdir string   `json:"container_workdir"`
			ContainerNetwork string   `json:"container_network"`
		} `json:"profiles"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v (%s)", err, rec.Body.String())
	}
	if len(out.Profiles) != 1 {
		t.Fatalf("期望 1 个档位，实际 %d", len(out.Profiles))
	}
	p := out.Profiles[0]
	if p.Image != "alpine:3.20" {
		t.Fatalf("应暴露镜像，实际 %q", p.Image)
	}
	if p.ContainerWorkdir != config.DefaultContainerWorkdir {
		t.Fatalf("应暴露容器内工作目录（默认 %q），实际 %q", config.DefaultContainerWorkdir, p.ContainerWorkdir)
	}
	if p.ContainerNetwork != "bridge" {
		t.Fatalf("应暴露网络，实际 %q", p.ContainerNetwork)
	}
	if len(p.Environments) != 1 || p.Environments[0] != "container" {
		t.Fatalf("应暴露环境声明，实际 %v", p.Environments)
	}
}

// 「该环境没有执行器」是请求层面可判定的拒绝，不能返 500 让监控以为服务崩了。
func TestExecutionStatusMapsExecutorUnavailableTo400(t *testing.T) {
	err := fmt.Errorf("wrap: %w", execution.ErrExecutorUnavailable)
	if got := executionStatus(err); got != http.StatusBadRequest {
		t.Fatalf("ErrExecutorUnavailable 应映射 400，实际 %d", got)
	}
}

// 容器档位 + local run：环境不匹配必须 400，且绝不能静默降级成在宿主跑。
func TestExecuteContainerProfileOnLocalRunRejected(t *testing.T) {
	h, _, _ := newExecRouterWithProfiles(t, []config.ExecutionProfile{
		{
			Name:         "echo-ctr",
			Command:      "echo",
			Environments: []string{"container"},
			Container:    &config.ContainerConfig{Image: "alpine:3.20"},
		},
	})
	runID := createRun(t, h) // local 语境

	rec := doJSON(t, h, "POST", "/api/evidence/runs/"+runID+"/execute?token="+testToken,
		map[string]any{"profile": "echo-ctr"})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("环境不匹配应 400，实际 %d body=%s", rec.Code, rec.Body.String())
	}
	if !containsAny(rec.Body.String(), "environment", "环境") {
		t.Fatalf("错误应说明环境不匹配，实际 %s", rec.Body.String())
	}
}
