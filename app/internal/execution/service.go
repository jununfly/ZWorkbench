// Package execution 是「真执行器」的编排层（ADR 0020 首刀）。
//
// 它把三件独立的东西缝在一起，并只做缝的动作：
//
//	config.ExecutionProfile  —— 允许跑什么（白名单档位，不是任意 argv）
//	executor.Executor        —— 怎么跑（本地 os/exec，不经 shell）
//	evidence.Owner           —— 跑了算什么（审批门 + effect 归属 + 状态机 + 事件）
//
// 刻意**不**在本包重新实现 token 校验、effect 归属或状态转移：那些一律回
// owner 的 ClaimEffect / CompleteEffect / CompleteRun / FailRun / SafeStopRun。
// 理由很直接——C28 的 token 语义（常量时间比对、防重放、过期、scope 匹配）
// 已经在 owner 里被完整实现并有测试；在编排层重写一遍只会多一处能悄悄偏离
// 的实现。ADR 0020 的不变式「执行器不得自成第二事实源」就是这条纪律。
package execution

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jununfly/ZWorkbench/app/internal/config"
	"github.com/jununfly/ZWorkbench/app/internal/evidence"
	"github.com/jununfly/ZWorkbench/app/internal/executor"
)

// ActionExecute 是执行审批与 effect 的 action 标识。
// 与 ClaimEffect 的 action 参数共用同一个值，保证 approval 的 scope 匹配能过。
const ActionExecute = "execute"

// 执行相关事件类型。命名沿用 run.* / effect.* 的点号分段风格，
// 让 /api/evidence/events?type= 能按前缀筛出一次执行的完整时间线。
const (
	EventExecutionStarted  = "execution.started"
	EventExecutionStdout   = "execution.stdout"
	EventExecutionStderr   = "execution.stderr"
	EventExecutionFinished = "execution.finished"
)

// 编排层的语义拒绝（都是「请求不合法」，不是服务故障）。
var (
	// ErrProfileNotFound：引用了配置里不存在的执行档位。
	ErrProfileNotFound = errors.New("execution profile not found")
	// ErrEnvironmentNotAllowed：run 声称的环境不在档位允许范围内。
	ErrEnvironmentNotAllowed = errors.New("execution environment not allowed")
	// ErrNoWorkdir：无法确定执行工作目录（reject 而不是猜一个 cwd）。
	ErrNoWorkdir = errors.New("execution workdir undetermined")
)

// Service 是执行编排。构造后并发安全（内部无可变状态）。
type Service struct {
	owner *evidence.Owner
	exec  executor.Executor
	cfg   *config.Config
}

// New 注入依赖。任一为 nil 时返回 nil —— 由调用方（路由层）显式 503，
// 而不是让一个半死掉的执行器静默接单。
func New(owner *evidence.Owner, ex executor.Executor, cfg *config.Config) *Service {
	if owner == nil || ex == nil || cfg == nil {
		return nil
	}
	return &Service{owner: owner, exec: ex, cfg: cfg}
}

// RequestResult 是「请求执行」的结果：审批单 + 解析后的执行规格。
// 规格在此一并返回，是为了让调用方/UI 能**在批准前就看到将要跑什么**——
// 「先批后看」等于让人盲签。
type RequestResult struct {
	Run                *evidence.Run       `json:"run"`
	Approval           *evidence.Approval  `json:"approval"`
	Profile            string              `json:"profile"`
	Command            string              `json:"command"`
	Args               []string            `json:"args"`
	Dir                string              `json:"dir"`
	TimeoutSec         int                 `json:"timeout_sec"`
	Environment        string              `json:"environment"`
	EnvironmentAssumed bool                `json:"environment_assumed"`
}

// ConfirmResult 是「确认执行」的结果。
//
// Claim 不可执行时（未批准、token 不匹配、已消费、run 已终态…）Executed=false
// 且 error 为 nil：这是**语义拒绝**，调用方应按 4xx 呈现，而不是当成 500。
type ConfirmResult struct {
	Claim    *evidence.EffectClaim `json:"claim"`
	Result   executor.Result       `json:"result"`
	Run      *evidence.Run         `json:"run"`
	Executed bool                  `json:"executed"`
	Reason   string                `json:"reason,omitempty"`
}

// Request 请求一次执行：解析档位 → 校验环境与工作目录 → 建审批 → run 进 waiting_approval。
//
// 幂等：同 run 同档位重复请求复用同一张审批单（operation_id 相同），
// 不会堆出一串待批条目。
func (s *Service) Request(runID, profileName string) (*RequestResult, error) {
	run, err := s.owner.GetRun(runID)
	if err != nil {
		return nil, err
	}

	profile, err := s.findProfile(profileName)
	if err != nil {
		return nil, err
	}

	env, assumed := resolveEnvironment(run.Environment)
	if !profile.AllowsEnvironment(env) {
		return nil, fmt.Errorf("%w: 档位 %q 不允许在环境 %q 执行（允许：%s）",
			ErrEnvironmentNotAllowed, profile.Name, env, profileAllowedEnvs(profile))
	}

	dir, err := s.resolveDir(run, profile)
	if err != nil {
		return nil, err
	}

	opID := operationID(runID, profile.Name)
	reason := buildReason(profile, assumed)
	approval, err := s.owner.RequestApproval(runID, opID, ActionExecute, profile.Name, opID, reason)
	if err != nil {
		return nil, err
	}
	// 显式推 waiting_approval：让 UI 在「请求」这一刻就看到 run 在等批，
	// 而不是点了确认才被告知（那时已经晚了）。
	updated, err := s.owner.WaitForApproval(runID, reason)
	if err != nil {
		return nil, err
	}

	return &RequestResult{
		Run:                updated,
		Approval:           approval,
		Profile:            profile.Name,
		Command:            profile.Command,
		Args:               profile.Args,
		Dir:                dir,
		TimeoutSec:         int(profile.EffectiveTimeout().Seconds()),
		Environment:        env,
		EnvironmentAssumed: assumed,
	}, nil
}

// Confirm 带审批 token 确认并执行。
//
// 流程严格按 owner 的语义走：ClaimEffect 通过（=审批有效且未被消费）才起进程；
// 跑完先 CompleteEffect 收口 effect，再把 run 推到终态。终态映射：
//
//	退出码 0        → completed
//	退出码非 0      → failed
//	超时 / 取消     → safe_stopped（不是 failed：这不是程序的问题，是被叫停）
//	执行器启动失败  → failed
func (s *Service) Confirm(ctx context.Context, runID, approvalID, token string) (*ConfirmResult, error) {
	run, err := s.owner.GetRun(runID)
	if err != nil {
		return nil, err
	}

	approval, err := s.findApproval(runID, approvalID)
	if err != nil {
		return nil, err
	}
	if approval.Action != ActionExecute {
		return nil, fmt.Errorf("%w: approval %s 不是执行审批（action=%q）",
			evidence.ErrBadArgument, approvalID, approval.Action)
	}

	profile, err := s.findProfile(approval.Resource)
	if err != nil {
		return nil, err
	}
	dir, err := s.resolveDir(run, profile)
	if err != nil {
		return nil, err
	}
	if env, _ := resolveEnvironment(run.Environment); !profile.AllowsEnvironment(env) {
		return nil, fmt.Errorf("%w: 档位 %q 不允许在环境 %q 执行",
			ErrEnvironmentNotAllowed, profile.Name, env)
	}

	opID := operationID(runID, profile.Name)
	claim, err := s.owner.ClaimEffect(
		runID, opID, ActionExecute, profile.Name, opID,
		"approval-required", token, 1, []string{"subprocess"},
	)
	if err != nil {
		return nil, err
	}
	if claim == nil || !claim.Executable() {
		return &ConfirmResult{Claim: claim, Reason: claimReason(claim)}, nil
	}

	spec := executor.Spec{
		Command: profile.Command,
		Args:    profile.Args,
		Dir:     dir,
		Timeout: profile.EffectiveTimeout(),
	}

	// 起跑前先留痕：进程若被 kill -9，至少「它起过」这件事在证据里。
	s.recordEvent(runID, EventExecutionStarted, map[string]any{
		"effect_id":   claim.EffectID,
		"profile":     profile.Name,
		"command":     profile.Command,
		"args":        profile.Args,
		"dir":         dir,
		"timeout_sec": int(profile.EffectiveTimeout().Seconds()),
	})

	res, runErr := s.exec.Run(ctx, spec)
	s.recordExecutionOutput(runID, claim.EffectID, res)

	// effect 先收口再改 run 终态：effect 是「副作用实际发生过」的记录，
	// 它比 run 的结论更基础。反过来会让 run 已 completed 但 effect 悬空。
	if _, cerr := s.owner.CompleteEffect(claim.EffectID, effectSummary(res), nil); cerr != nil {
		// effect 收不了口时不能假装成功：把 run 压到 safe_stopped 并如实返回错误。
		_, _ = s.owner.SafeStopRun(runID, "effect_completion_failed: "+cerr.Error())
		return nil, fmt.Errorf("收口 effect 失败：%w", cerr)
	}

	finalRun, reason := s.finalizeRun(runID, res, runErr)
	return &ConfirmResult{
		Claim:    claim,
		Result:   res,
		Run:      finalRun,
		Executed: true,
		Reason:   reason,
	}, nil
}

// finalizeRun 把执行结果映射成 run 终态。返回终态快照与可复核的原因文本。
func (s *Service) finalizeRun(runID string, res executor.Result, runErr error) (*evidence.Run, string) {
	switch {
	case res.TimedOut:
		reason := fmt.Sprintf("execution_timeout: 超过 %v 未结束", res.Duration)
		r, err := s.owner.SafeStopRun(runID, reason)
		return orFallback(r, err, runID, s), reason
	case res.Canceled:
		reason := "execution_canceled: 执行被取消"
		r, err := s.owner.SafeStopRun(runID, reason)
		return orFallback(r, err, runID, s), reason
	case runErr != nil:
		reason := "executor_failure: " + runErr.Error()
		r, err := s.owner.FailRun(runID, map[string]any{"reason": reason})
		return orFallback(r, err, runID, s), reason
	case res.ExitCode == 0:
		r, err := s.owner.CompleteRun(runID, effectSummary(res))
		return orFallback(r, err, runID, s), ""
	default:
		reason := fmt.Sprintf("nonzero_exit: 退出码 %d", res.ExitCode)
		r, err := s.owner.FailRun(runID, map[string]any{"reason": reason, "exit_code": res.ExitCode})
		return orFallback(r, err, runID, s), reason
	}
}

// orFallback 在终态转移失败时回读当前快照，避免把一个「已经写不下去」的 run
// 伪装成成功返回。错误本身已由 owner 记录，这里只需给出可读状态。
func orFallback(r *evidence.Run, err error, runID string, s *Service) *evidence.Run {
	if err == nil {
		return r
	}
	if cur, gerr := s.owner.GetRun(runID); gerr == nil {
		return cur
	}
	return r
}

// recordExecutionOutput 记录 stdout / stderr 两条独立事件。
//
// 诚实标注：输出**未做脱敏**。执行输出可能包含密钥或个人信息，本层不猜也不改，
// 只把它落进本地证据库（文件权限 0600、不出本机），并在事件里显式写明
// redaction=none —— 让回看的人知道这是原始输出，而不是「已清洗」的假象。
func (s *Service) recordExecutionOutput(runID, effectID string, res executor.Result) {
	if res.Stdout != "" || res.StdoutBytes > 0 {
		s.recordEvent(runID, EventExecutionStdout, map[string]any{
			"effect_id":    effectID,
			"text":         res.Stdout,
			"total_bytes":  res.StdoutBytes,
			"truncated":    res.Truncated,
			"redaction":    "none",
		})
	}
	if res.Stderr != "" || res.StderrBytes > 0 {
		s.recordEvent(runID, EventExecutionStderr, map[string]any{
			"effect_id":    effectID,
			"text":         res.Stderr,
			"total_bytes":  res.StderrBytes,
			"truncated":    res.Truncated,
			"redaction":    "none",
		})
	}
	s.recordEvent(runID, EventExecutionFinished, map[string]any{
		"effect_id":    effectID,
		"exit_code":    res.ExitCode,
		"duration_ms":  res.Duration.Milliseconds(),
		"timed_out":    res.TimedOut,
		"canceled":     res.Canceled,
		"truncated":    res.Truncated,
	})
}

// recordEvent 写一条证据事件；失败不打断执行流程（记账抖动不该中止已经起跑的
// 进程），但也绝不吞掉 —— 由 owner 的日志/调用方排查。这是本包唯一静默的地方，
// 且静默的是「补充证据」而非「状态转移」。
func (s *Service) recordEvent(runID, eventType string, payload map[string]any) {
	_, _ = s.owner.RecordEvent(runID, eventType, payload, evidence.EvidenceSourceNative)
}

// ---- 解析与校验 ----

func (s *Service) findProfile(name string) (config.ExecutionProfile, error) {
	profiles := s.cfg.ExecutionProfiles()
	p, ok := profiles.FindProfile(name)
	if !ok {
		return config.ExecutionProfile{}, fmt.Errorf("%w: %q", ErrProfileNotFound, name)
	}
	// 配置可能来自 env（ZW_EXEC_PROFILES）而未经保存时校验，这里再过一道。
	if err := p.Validate(); err != nil {
		return config.ExecutionProfile{}, fmt.Errorf("%w: %v", evidence.ErrBadArgument, err)
	}
	return p, nil
}

// resolveDir 确定执行工作目录。**不猜**：determine 不了就拒绝。
func (s *Service) resolveDir(run *evidence.Run, profile config.ExecutionProfile) (string, error) {
	repoPath := ""
	if name := strings.TrimSpace(run.Repo); name != "" {
		if spec, ok := s.cfg.ManagedRepos().FindRepo(name); ok {
			repoPath = strings.TrimSpace(spec.Path)
		}
	}
	dir := profile.ResolveDir(repoPath)
	if strings.TrimSpace(dir) == "" {
		return "", fmt.Errorf("%w: 档位 %q 的 workdir 与被管理仓库路径都为空，不确定在哪个目录执行",
			ErrNoWorkdir, profile.Name)
	}
	return dir, nil
}

func (s *Service) findApproval(runID, approvalID string) (*evidence.Approval, error) {
	list, err := s.owner.ListApprovals(runID, 200)
	if err != nil {
		return nil, err
	}
	for i := range list {
		if list[i].ApprovalID == approvalID {
			return &list[i], nil
		}
	}
	return nil, fmt.Errorf("%w: approval %s 不属于 run %s", evidence.ErrNotFound, approvalID, runID)
}

// resolveEnvironment 归一 run 的环境。未声明时按 local 处理并**显式标记**
// assumed=true —— 假设可以有，但必须留痕，不能当成「用户说了 local」。
func resolveEnvironment(env string) (string, bool) {
	e := strings.TrimSpace(env)
	if e == "" {
		return "local", true
	}
	return e, false
}

func operationID(runID, profileName string) string {
	return "exec:" + runID + ":" + profileName
}

func buildReason(profile config.ExecutionProfile, assumed bool) string {
	var b strings.Builder
	fmt.Fprintf(&b, "执行档位 %q：%s", profile.Name, profile.Command)
	if len(profile.Args) > 0 {
		b.WriteString(" " + strings.Join(profile.Args, " "))
	}
	if assumed {
		b.WriteString("（run 未声明环境，按 local 假设）")
	}
	return b.String()
}

func profileAllowedEnvs(p config.ExecutionProfile) string {
	if len(p.Environments) == 0 {
		return "local"
	}
	return strings.Join(p.Environments, ", ")
}

func claimReason(c *evidence.EffectClaim) string {
	if c == nil {
		return "claim_unavailable"
	}
	return c.Status + ": " + c.Reason
}

// effectSummary 是落到 effect 结果与 run 结论里的摘要。
// 刻意不含 stdout/stderr 全文——那两份在事件里，重复存一份只会让库无谓膨胀。
func effectSummary(res executor.Result) map[string]any {
	return map[string]any{
		"exit_code":    res.ExitCode,
		"duration_ms":  res.Duration.Milliseconds(),
		"stdout_bytes": res.StdoutBytes,
		"stderr_bytes": res.StderrBytes,
		"truncated":    res.Truncated,
		"timed_out":    res.TimedOut,
		"canceled":     res.Canceled,
	}
}
