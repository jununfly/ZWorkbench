package execution

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/jununfly/ZWorkbench/app/internal/config"
	"github.com/jununfly/ZWorkbench/app/internal/evidence"
	"github.com/jununfly/ZWorkbench/app/internal/executor"
)

// 编排层的职责边界（ADR 0020）：
//   - 决定「这次执行允不允许发生」：档位解析 + 环境匹配 + 工作目录可确定；
//   - 决定「审批门怎么走」：无 token 一律不开跑；
//   - 决定「跑完怎么记账」：退出码 → complete/fail，超时/取消 → safe_stop。
//
// 它自己**不实现** token 校验、effect 归属、状态机——那些一律回到 owner
// （ClaimEffect + CompleteEffect + CompleteRun/FailRun/SafeStopRun），保证
// 「单一 durable owner」不变式。测试正是按这个边界写的：断言 owner 里的
// 状态与事件，而不是断言编排层自己的内部字段。

type fakeExec struct {
	res     executor.Result
	err     error
	gotSpec executor.Spec
	calls   int
}

func (f *fakeExec) Run(_ context.Context, spec executor.Spec) (executor.Result, error) {
	f.calls++
	f.gotSpec = spec
	return f.res, f.err
}

type fixture struct {
	svc   *Service
	owner *evidence.Owner
	exec  *fakeExec
	cfg   *config.Config
	repo  string
}

// newFixture 建一个内存证据库 + 一个被管理仓库 + 两个执行档位。
func newFixture(t *testing.T) *fixture {
	t.Helper()
	t.Setenv("ZW_CONFIG", filepath.Join(t.TempDir(), "config.json"))

	owner, err := evidence.Open(filepath.Join(t.TempDir(), "evidence.sqlite3"))
	if err != nil {
		t.Fatalf("打开证据库：%v", err)
	}
	t.Cleanup(func() { _ = owner.Close() })

	repoDir := t.TempDir()
	cfg := config.Load()
	cfg.SetManagedRepos(config.ManagedRepos{Repos: []config.RepoSpec{
		{Name: "ZW", Path: repoDir, Environments: []string{"local"}},
	}})
	cfg.SetExecutionProfiles(config.ExecutionProfiles{Profiles: []config.ExecutionProfile{
		{Name: "echo-ok", Command: "echo", Args: []string{"hi"}, TimeoutSec: 30},
		{Name: "in-app", Command: "go", Args: []string{"test", "./..."}, Workdir: "app"},
	}})

	fx := &fakeExec{res: executor.Result{ExitCode: 0, Stdout: "ok"}}
	return &fixture{svc: New(owner, fx, cfg), owner: owner, exec: fx, cfg: cfg, repo: repoDir}
}

// newRun 建一个带 local 语境的 run。
func (f *fixture) newRun(t *testing.T, runID, env string) *evidence.Run {
	t.Helper()
	run, err := f.owner.CreateRunWithContext(runID, "manual", nil, nil, "ZW", "", env)
	if err != nil {
		t.Fatalf("建 run：%v", err)
	}
	return run
}

func TestRequestUnknownProfile(t *testing.T) {
	fx := newFixture(t)
	fx.newRun(t, "r1", "local")

	_, err := fx.svc.Request("r1", "nope")
	if !errors.Is(err, ErrProfileNotFound) {
		t.Fatalf("未知档位应返回 ErrProfileNotFound，实际 %v", err)
	}
}

func TestRequestUnknownRun(t *testing.T) {
	fx := newFixture(t)
	_, err := fx.svc.Request("missing", "echo-ok")
	if !errors.Is(err, evidence.ErrRunNotFound) {
		t.Fatalf("未知 run 应返回 ErrRunNotFound，实际 %v", err)
	}
}

func TestRequestEnvironmentMismatch(t *testing.T) {
	fx := newFixture(t)
	// 档位只允许 local；run 却声称 container（config 白名单里没有，直接建 run 绕过 API 校验）。
	if _, err := fx.owner.CreateRunWithContext("r1", "manual", nil, nil, "ZW", "", "container"); err != nil {
		t.Fatalf("建 run：%v", err)
	}
	_, err := fx.svc.Request("r1", "echo-ok")
	if !errors.Is(err, ErrEnvironmentNotAllowed) {
		t.Fatalf("环境不匹配应返回 ErrEnvironmentNotAllowed，实际 %v", err)
	}
}

func TestRequestEmptyEnvironmentAssumesLocal(t *testing.T) {
	fx := newFixture(t)
	fx.newRun(t, "r1", "") // 未声明环境

	out, err := fx.svc.Request("r1", "echo-ok")
	if err != nil {
		t.Fatalf("未声明环境应回退 local 而非拒绝：%v", err)
	}
	if out.Environment != "local" || !out.EnvironmentAssumed {
		t.Fatalf("应显式标记「环境按 local 假设」，实际 env=%q assumed=%v", out.Environment, out.EnvironmentAssumed)
	}
}

func TestRequestCreatesPendingApprovalAndWaitingRun(t *testing.T) {
	fx := newFixture(t)
	fx.newRun(t, "r1", "local")

	out, err := fx.svc.Request("r1", "echo-ok")
	if err != nil {
		t.Fatalf("请求执行：%v", err)
	}
	if out.Approval == nil || out.Approval.Status != "pending" {
		t.Fatalf("应创建 pending 审批，实际 %#v", out.Approval)
	}
	if out.Approval.Action != ActionExecute {
		t.Fatalf("approval action 期望 %q，实际 %q", ActionExecute, out.Approval.Action)
	}
	if out.Approval.Resource != "echo-ok" {
		t.Fatalf("approval resource 应是被引用的档位名，实际 %q", out.Approval.Resource)
	}

	run, err := fx.owner.GetRun("r1")
	if err != nil {
		t.Fatalf("读 run：%v", err)
	}
	if run.Status != evidence.StatusWaitingApproval {
		t.Fatalf("请求执行后 run 应进 waiting_approval，实际 %s", run.Status)
	}
}

func TestRequestIsIdempotent(t *testing.T) {
	fx := newFixture(t)
	fx.newRun(t, "r1", "local")

	a, err := fx.svc.Request("r1", "echo-ok")
	if err != nil {
		t.Fatalf("第一次请求：%v", err)
	}
	b, err := fx.svc.Request("r1", "echo-ok")
	if err != nil {
		t.Fatalf("重复请求应幂等而非报错：%v", err)
	}
	if a.Approval.ApprovalID != b.Approval.ApprovalID {
		t.Fatalf("同 run 同档位重复请求应复用同一 approval，实际 %s vs %s",
			a.Approval.ApprovalID, b.Approval.ApprovalID)
	}
}

// TestConfirmWithoutApprovalDoesNotExecute 是审批门的核心断言：
// 没有批准就绝不跑，run 也不能被推到 running。
func TestConfirmWithoutApprovalDoesNotExecute(t *testing.T) {
	fx := newFixture(t)
	fx.newRun(t, "r1", "local")
	req, err := fx.svc.Request("r1", "echo-ok")
	if err != nil {
		t.Fatalf("请求执行：%v", err)
	}

	out, err := fx.svc.Confirm(context.Background(), "r1", req.Approval.ApprovalID, "")
	if err != nil {
		t.Fatalf("审批未通过属于语义拒绝，不应返回 error：%v", err)
	}
	if out.Executed {
		t.Fatal("未批准绝不允许执行")
	}
	if fx.exec.calls != 0 {
		t.Fatalf("未批准不应触达执行器，实际调用 %d 次", fx.exec.calls)
	}
	if out.Claim == nil || out.Claim.Executable() {
		t.Fatalf("claim 应为不可执行，实际 %#v", out.Claim)
	}

	run, _ := fx.owner.GetRun("r1")
	if run.Status != evidence.StatusWaitingApproval {
		t.Fatalf("run 应停在 waiting_approval，实际 %s", run.Status)
	}
}

func TestConfirmWithApprovalExecutesAndCompletes(t *testing.T) {
	fx := newFixture(t)
	fx.newRun(t, "r1", "local")
	req, err := fx.svc.Request("r1", "echo-ok")
	if err != nil {
		t.Fatalf("请求执行：%v", err)
	}
	tok, err := fx.owner.Approve(req.Approval.ApprovalID, 300)
	if err != nil {
		t.Fatalf("批准：%v", err)
	}

	out, err := fx.svc.Confirm(context.Background(), "r1", req.Approval.ApprovalID, tok.Token)
	if err != nil {
		t.Fatalf("确认执行：%v", err)
	}
	if !out.Executed {
		t.Fatalf("已批准应执行，claim=%#v", out.Claim)
	}
	if fx.exec.calls != 1 {
		t.Fatalf("执行器应被调用 1 次，实际 %d", fx.exec.calls)
	}
	if out.Result.ExitCode != 0 {
		t.Fatalf("退出码应为 0，实际 %d", out.Result.ExitCode)
	}
	if out.Run.Status != evidence.StatusCompleted {
		t.Fatalf("退出 0 后 run 应为 completed，实际 %s", out.Run.Status)
	}

	// 工作目录来自被管理仓库的 Path。
	if fx.exec.gotSpec.Dir != fx.repo {
		t.Fatalf("执行工作目录应为仓库路径 %q，实际 %q", fx.repo, fx.exec.gotSpec.Dir)
	}
	if fx.exec.gotSpec.Command != "echo" {
		t.Fatalf("命令应来自档位，实际 %q", fx.exec.gotSpec.Command)
	}
	if fx.exec.gotSpec.Timeout != 30*time.Second {
		t.Fatalf("超时应来自档位，实际 %v", fx.exec.gotSpec.Timeout)
	}
}

func TestConfirmNonZeroExitFailsRun(t *testing.T) {
	fx := newFixture(t)
	fx.exec.res = executor.Result{ExitCode: 2, Stderr: "boom"}
	fx.newRun(t, "r1", "local")
	req, _ := fx.svc.Request("r1", "echo-ok")
	tok, err := fx.owner.Approve(req.Approval.ApprovalID, 300)
	if err != nil {
		t.Fatalf("批准：%v", err)
	}

	out, err := fx.svc.Confirm(context.Background(), "r1", req.Approval.ApprovalID, tok.Token)
	if err != nil {
		t.Fatalf("非 0 退出不是编排故障：%v", err)
	}
	if !out.Executed {
		t.Fatal("应已执行")
	}
	if out.Run.Status != evidence.StatusFailed {
		t.Fatalf("非 0 退出应把 run 记 failed，实际 %s", out.Run.Status)
	}
}

func TestConfirmTimeoutSafeStopsRun(t *testing.T) {
	fx := newFixture(t)
	fx.exec.res = executor.Result{ExitCode: -1, TimedOut: true}
	fx.exec.err = context.DeadlineExceeded
	fx.newRun(t, "r1", "local")
	req, _ := fx.svc.Request("r1", "echo-ok")
	tok, _ := fx.owner.Approve(req.Approval.ApprovalID, 300)

	out, err := fx.svc.Confirm(context.Background(), "r1", req.Approval.ApprovalID, tok.Token)
	if err != nil {
		t.Fatalf("超时由编排记账，不应再返回 error：%v", err)
	}
	if out.Run.Status != evidence.StatusSafeStopped {
		t.Fatalf("超时应把 run 记 safe_stopped（不是 failed），实际 %s", out.Run.Status)
	}
}

func TestConfirmCancelSafeStopsRun(t *testing.T) {
	fx := newFixture(t)
	fx.exec.res = executor.Result{ExitCode: -1, Canceled: true}
	fx.exec.err = context.Canceled
	fx.newRun(t, "r1", "local")
	req, _ := fx.svc.Request("r1", "echo-ok")
	tok, _ := fx.owner.Approve(req.Approval.ApprovalID, 300)

	out, err := fx.svc.Confirm(context.Background(), "r1", req.Approval.ApprovalID, tok.Token)
	if err != nil {
		t.Fatalf("取消由编排记账，不应再返回 error：%v", err)
	}
	if out.Run.Status != evidence.StatusSafeStopped {
		t.Fatalf("取消应把 run 记 safe_stopped，实际 %s", out.Run.Status)
	}
}

// TestConfirmTokenReplayIsDenied 验证一次性 token 不能复用：
// 第二次确认必须被拒且**不**再次触达执行器。
func TestConfirmTokenReplayIsDenied(t *testing.T) {
	fx := newFixture(t)
	fx.newRun(t, "r1", "local")
	req, _ := fx.svc.Request("r1", "echo-ok")
	tok, _ := fx.owner.Approve(req.Approval.ApprovalID, 300)

	if _, err := fx.svc.Confirm(context.Background(), "r1", req.Approval.ApprovalID, tok.Token); err != nil {
		t.Fatalf("第一次确认：%v", err)
	}
	before := fx.exec.calls

	out, err := fx.svc.Confirm(context.Background(), "r1", req.Approval.ApprovalID, tok.Token)
	if err == nil && out.Executed {
		t.Fatal("重放 token 绝不允许再次执行")
	}
	if fx.exec.calls != before {
		t.Fatalf("重放不应触达执行器，实际多调用 %d 次", fx.exec.calls-before)
	}
}

func TestConfirmMissingWorkdir(t *testing.T) {
	fx := newFixture(t)
	// run 不挂仓库、档位也没有绝对 workdir → 无法确定 cwd，必须拒绝而不是猜。
	if _, err := fx.owner.CreateRunWithContext("r1", "manual", nil, nil, "", "", "local"); err != nil {
		t.Fatalf("建 run：%v", err)
	}
	_, err := fx.svc.Request("r1", "echo-ok")
	if !errors.Is(err, ErrNoWorkdir) {
		t.Fatalf("无法确定工作目录应返回 ErrNoWorkdir，实际 %v", err)
	}
}

func TestConfirmRecordsExecutionEvents(t *testing.T) {
	fx := newFixture(t)
	fx.exec.res = executor.Result{ExitCode: 0, Stdout: "hello", Stderr: "warn", StdoutBytes: 5, StderrBytes: 4}
	fx.newRun(t, "r1", "local")
	req, _ := fx.svc.Request("r1", "echo-ok")
	tok, _ := fx.owner.Approve(req.Approval.ApprovalID, 300)
	if _, err := fx.svc.Confirm(context.Background(), "r1", req.Approval.ApprovalID, tok.Token); err != nil {
		t.Fatalf("确认执行：%v", err)
	}

	events, err := fx.owner.ListEvents("r1", "", 200)
	if err != nil {
		t.Fatalf("列事件：%v", err)
	}
	seen := map[string]bool{}
	for _, e := range events {
		seen[e.Type] = true
	}
	for _, want := range []string{EventExecutionStarted, EventExecutionStdout, EventExecutionStderr, EventExecutionFinished} {
		if !seen[want] {
			t.Fatalf("缺少执行事件 %q，实际看到 %v", want, keys(seen))
		}
	}
}

func TestConfirmStartFailureFailsRun(t *testing.T) {
	fx := newFixture(t)
	fx.exec.res = executor.Result{ExitCode: -1}
	fx.exec.err = errors.New("找不到可执行文件")
	fx.newRun(t, "r1", "local")
	req, _ := fx.svc.Request("r1", "echo-ok")
	tok, _ := fx.owner.Approve(req.Approval.ApprovalID, 300)

	out, err := fx.svc.Confirm(context.Background(), "r1", req.Approval.ApprovalID, tok.Token)
	if err != nil {
		t.Fatalf("启动失败应记 failed 而非返回 error：%v", err)
	}
	if out.Run.Status != evidence.StatusFailed {
		t.Fatalf("启动失败应把 run 记 failed，实际 %s", out.Run.Status)
	}
	if !strings.Contains(out.Reason, "executor") && !strings.Contains(out.Reason, "执行器") {
		t.Fatalf("应记录可复核的失败原因，实际 %q", out.Reason)
	}
}

func keys(m map[string]bool) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}
