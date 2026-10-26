package api

import (
	"encoding/json"
	"net/http"
	"os/exec"
	"testing"

	"github.com/jununfly/ZWorkbench/app/internal/config"
	"github.com/jununfly/ZWorkbench/app/internal/evidence"
)

// newContextRouter 构造带被管理仓库配置的测试 router；
// repos 为要登记的仓库（Path 指向真实或临时目录）。
func newContextRouter(t *testing.T, repos []config.RepoSpec) (http.Handler, *evidence.Owner) {
	t.Helper()
	ev, err := evidence.Open(":memory:")
	if err != nil {
		t.Fatalf("evidence.Open: %v", err)
	}
	t.Cleanup(func() { _ = ev.Close() })
	cfg := &config.Config{Port: "18080", Token: testToken}
	cfg.SetManagedRepos(config.ManagedRepos{Repos: repos})
	return NewRouter(cfg, nil, nil, ev), ev
}

// initGitRepo 在 dir 里初始化一个 git 仓库并切到 branch 分支（供 current_branch 探测）。
func initGitRepo(t *testing.T, dir, branch string) {
	t.Helper()
	cmd := exec.Command("git", "init", "-q", "-b", branch, dir)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("git init: %v (%s)", err, out)
	}
}

func TestContextAPIGitRepo(t *testing.T) {
	gitDir := t.TempDir()
	initGitRepo(t, gitDir, "feature-x")

	h, _ := newContextRouter(t, []config.RepoSpec{
		{Name: "MyRepo", Path: gitDir, Environments: []string{"local", "container"}},
	})

	rec := doJSON(t, h, "GET", "/api/context?token="+testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("context code=%d body=%s", rec.Code, rec.Body.String())
	}
	var body struct {
		Repos               []map[string]any `json:"repos"`
		DefaultRepo         string            `json:"default_repo"`
		DefaultEnvironment  string            `json:"default_environment"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode context: %v", err)
	}
	if len(body.Repos) != 1 {
		t.Fatalf("应返回 1 个仓库，实际 %d", len(body.Repos))
	}
	if body.Repos[0]["current_branch"] != "feature-x" {
		t.Fatalf("current_branch 应为 feature-x，实际 %v", body.Repos[0]["current_branch"])
	}
	if body.Repos[0]["name"] != "MyRepo" {
		t.Fatalf("仓库名不符：%v", body.Repos[0]["name"])
	}
	if body.DefaultRepo != "MyRepo" {
		t.Fatalf("default_repo 应为 MyRepo，实际 %q", body.DefaultRepo)
	}
	if body.DefaultEnvironment != "local" {
		t.Fatalf("default_environment 应为 local，实际 %q", body.DefaultEnvironment)
	}
}

func TestContextAPINonGitDir(t *testing.T) {
	// 纯临时目录（无 .git）→ current_branch 必须 unknown，HTTP 仍 200。
	plainDir := t.TempDir()

	h, _ := newContextRouter(t, []config.RepoSpec{
		{Name: "Plain", Path: plainDir, Environments: nil},
	})

	rec := doJSON(t, h, "GET", "/api/context?token="+testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("context code=%d body=%s", rec.Code, rec.Body.String())
	}
	var body struct {
		Repos []map[string]any `json:"repos"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode context: %v", err)
	}
	if body.Repos[0]["current_branch"] != "unknown" {
		t.Fatalf("非 git 目录 current_branch 应为 unknown，实际 %v", body.Repos[0]["current_branch"])
	}
	// 无 environments 时端点应补默认 ["local"]。
	envs, _ := body.Repos[0]["environments"].([]any)
	if len(envs) != 1 || envs[0] != "local" {
		t.Fatalf("environments 应补默认 [local]，实际 %v", envs)
	}
}

func TestContextAPIDefaultsToCwdRepo(t *testing.T) {
	// 无显式被管理仓库配置时，应自动把当前 git 仓库（如 ZWorkbench）登记为默认仓库。
	h, _ := newContextRouter(t, nil)

	rec := doJSON(t, h, "GET", "/api/context?token="+testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("context code=%d body=%s", rec.Code, rec.Body.String())
	}
	var body struct {
		Repos []map[string]any `json:"repos"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode context: %v", err)
	}
	if len(body.Repos) != 1 {
		t.Fatalf("应自动登记 1 个 cwd 仓库，实际 %d", len(body.Repos))
	}
	if body.Repos[0]["name"] != "ZWorkbench" {
		t.Fatalf("cwd 仓库名应为 ZWorkbench，实际 %v", body.Repos[0]["name"])
	}
	if body.Repos[0]["current_branch"] == "unknown" {
		t.Fatalf("cwd 仓库应能探测到真实分支，却得到 unknown（非 git 环境？）")
	}
}

func TestCreateRunWithContextRoundtrip(t *testing.T) {
	// 显式配置一个允许 container 的仓库（白名单强制后，cwd fallback 只有 local）。
	h, _ := newContextRouter(t, []config.RepoSpec{
		{Name: "ZWorkbench", Path: t.TempDir(), Environments: []string{"local", "container"}},
	})

	rec := doJSON(t, h, "POST", "/api/evidence/runs?token="+testToken, map[string]any{
		"task_type":   "coding",
		"repo":        "ZWorkbench",
		"branch":      "main",
		"environment": "container",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("create code=%d body=%s", rec.Code, rec.Body.String())
	}
	var run evidence.Run
	if err := json.Unmarshal(rec.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	if run.Repo != "ZWorkbench" || run.Branch != "main" || run.Environment != "container" {
		t.Fatalf("run 上下文维度未回显：%#v", run)
	}

	// 详情接口也应带三字段。
	rec = doJSON(t, h, "GET", "/api/evidence/runs/"+run.RunID+"?token="+testToken, nil)
	var detail evidence.Run
	if err := json.Unmarshal(rec.Body.Bytes(), &detail); err != nil {
		t.Fatalf("decode detail: %v", err)
	}
	if detail.Repo != "ZWorkbench" || detail.Branch != "main" || detail.Environment != "container" {
		t.Fatalf("详情三字段不符：%#v", detail)
	}
}

// TestCreateRunRejectsUnlistedEnvironment 覆盖 ADR 0019 Follow-up ② 的核心不变量：
// 声称白名单外的环境必须 400 fail-closed，而不是静默落库。
func TestCreateRunRejectsUnlistedEnvironment(t *testing.T) {
	h, ev := newContextRouter(t, []config.RepoSpec{
		{Name: "ZW", Path: t.TempDir(), Environments: []string{"local"}},
	})

	rec := doJSON(t, h, "POST", "/api/evidence/runs?token="+testToken, map[string]any{
		"task_type":   "coding",
		"repo":        "ZW",
		"environment": "container",
	})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("白名单外环境应 400，实际 code=%d body=%s", rec.Code, rec.Body.String())
	}
	// fail-closed：被拒的请求不得留下任何 run。
	runs, err := ev.ListRuns()
	if err != nil {
		t.Fatalf("ListRuns: %v", err)
	}
	if len(runs) != 0 {
		t.Fatalf("被拒请求不应落库，实际有 %d 个 run", len(runs))
	}
}

// TestCreateRunRejectsUnknownRepo：声称不受管理的仓库应 400。
func TestCreateRunRejectsUnknownRepo(t *testing.T) {
	h, _ := newContextRouter(t, []config.RepoSpec{
		{Name: "ZW", Path: t.TempDir(), Environments: []string{"local"}},
	})

	rec := doJSON(t, h, "POST", "/api/evidence/runs?token="+testToken, map[string]any{
		"task_type":   "coding",
		"repo":        "Ghost",
		"environment": "local",
	})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("未知仓库应 400，实际 code=%d body=%s", rec.Code, rec.Body.String())
	}
}

// TestCreateRunAllowsEmptyEnvironment：仓库已声明但不声称环境 → 允许（不构成伪造）。
func TestCreateRunAllowsEmptyEnvironment(t *testing.T) {
	h, _ := newContextRouter(t, []config.RepoSpec{
		{Name: "ZW", Path: t.TempDir(), Environments: []string{"local"}},
	})

	rec := doJSON(t, h, "POST", "/api/evidence/runs?token="+testToken, map[string]any{
		"task_type": "coding",
		"repo":      "ZW",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("不声称环境应允许，实际 code=%d body=%s", rec.Code, rec.Body.String())
	}
	var run evidence.Run
	if err := json.Unmarshal(rec.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	if run.Environment != "" {
		t.Fatalf("未声称环境时应留空，实际 %q", run.Environment)
	}
}

// TestContextAPICarriesEnvironmentStatus：/api/context 应给出每个环境的可达性快照，
// 且 local 恒可用（只读探测，不影响授权）。
func TestContextAPICarriesEnvironmentStatus(t *testing.T) {
	h, _ := newContextRouter(t, []config.RepoSpec{
		{Name: "ZW", Path: t.TempDir(), Environments: []string{"local", "staging"}},
	})

	rec := doJSON(t, h, "GET", "/api/context?token="+testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("context code=%d body=%s", rec.Code, rec.Body.String())
	}
	var body struct {
		Repos []map[string]any `json:"repos"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode context: %v", err)
	}
	raw, ok := body.Repos[0]["environment_status"].([]any)
	if !ok {
		t.Fatalf("environment_status 缺失或类型不符：%v", body.Repos[0]["environment_status"])
	}
	if len(raw) != 2 {
		t.Fatalf("应探测 2 个环境，实际 %d", len(raw))
	}
	byName := map[string]map[string]any{}
	for _, it := range raw {
		m, _ := it.(map[string]any)
		name, _ := m["name"].(string)
		byName[name] = m
	}
	if byName["local"] == nil || byName["local"]["available"] != true {
		t.Fatalf("local 应可用，实际 %v", byName["local"])
	}
	// staging 是未知种类 → 不可用，但必须给出可读 reason（不是空）。
	if st := byName["staging"]; st == nil || st["available"] != false || st["reason"] == "" {
		t.Fatalf("staging 应不可用且带 reason，实际 %v", st)
	}
}

func TestCreateRunBackwardCompatEmptyContext(t *testing.T) {
	h, _ := newContextRouter(t, nil)
	// 不传 repo/branch/environment，应仍成功且三字段为空串。
	rec := doJSON(t, h, "POST", "/api/evidence/runs?token="+testToken, map[string]any{
		"task_type": "coding",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("create code=%d body=%s", rec.Code, rec.Body.String())
	}
	var run evidence.Run
	if err := json.Unmarshal(rec.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	if run.Repo != "" || run.Branch != "" || run.Environment != "" {
		t.Fatalf("未传上下文时应全空，实际 %#v", run)
	}
}
