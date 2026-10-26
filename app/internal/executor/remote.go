package executor

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// RemoteSpec 是「在远端跑」的包装参数（environment = "remote"，ADR 0020 remote 切片）。
//
// 与 config.RemoteConfig 刻意分开：config 负责「配置能不能通过校验」，
// 本包负责「拿到手的参数能不能安全地变成 ssh argv」。执行器不 import config，
// 避免分层倒置；重复的几个默认值方法很便宜。
type RemoteSpec struct {
	// Host 是远端主机（域名或 IP），必填。
	Host string
	// Port 是 SSH 端口；0 = 默认 22。
	Port int
	// User 是登录用户；空 = ssh 默认（当前用户）。
	User string
	// IdentityFile 是本地私钥路径；空 = ssh 默认（~/.ssh/id_*）。
	IdentityFile string
}

func (r *RemoteSpec) effectivePort() int {
	if r.Port <= 0 {
		return 22
	}
	return r.Port
}

func (r *RemoteSpec) endpoint() string {
	return r.Host + ":" + strconv.Itoa(r.effectivePort())
}

// hostPart 拼出 ssh 的 [user@]host 段。
func (r *RemoteSpec) hostPart() string {
	if u := strings.TrimSpace(r.User); u != "" {
		return u + "@" + strings.TrimSpace(r.Host)
	}
	return strings.TrimSpace(r.Host)
}

// validate 是执行器侧的最后一道闸。config 已经校验过一遍，这里再校验一遍：
// 执行器不能假设调用方一定校验过（Spec 也可能由测试或未来别的调用方构造）。
func (r *RemoteSpec) validate() error {
	host := strings.TrimSpace(r.Host)
	if host == "" {
		return errors.New("executor: remote host 不能为空")
	}
	if r.Port < 0 || r.Port > 65535 {
		return fmt.Errorf("executor: remote port 超出合法范围 [0, 65535]，实际 %d", r.Port)
	}
	return nil
}

// Remote 在远端通过 SSH 执行（environment = "remote"，ADR 0020 remote 切片）。
//
// 走 ssh CLI（os/exec）而不是 SSH/SDK：SDK 会破坏 buildguard 的零依赖守卫，
// 而 CLI 的能力对本切片完全够用（ADR 0020 前提 1 的结论）。
//
// 安全基线（与 Local / Docker 同源）：
//   - **从不经过 shell**：把 command + args 作为独立 argv 传给 ssh，远端按
//     可执行文件 + 参数执行，参数里的 ;/|/$ 都是普通字符，不会在本地或远端被解析。
//   - **只走密钥、绝不走口令**：以 BatchMode=yes 起 ssh，缺密钥立即失败而不是
//     卡在密码提示（fail-closed，否则执行会无限挂起）；
//   - **首次连接不交互**：StrictHostKeyChecking=accept-new 自动收录主机密钥，
//     既不卡提示也不跳过校验（避免 MITM 风险）。
type Remote struct {
	// Bin 是 ssh CLI 路径；空 = LookPath("ssh")。
	Bin string
}

// 包级依赖抽出来便于测试注入（与 Local / Docker / envprobe 同风格）。
var (
	sshRun = func(ctx context.Context, bin string, args []string, stdout, stderr io.Writer) error {
		cmd := exec.CommandContext(ctx, bin, args...)
		cmd.Stdout = stdout
		cmd.Stderr = stderr
		return cmd.Run()
	}
)

// Run 实现 Executor。fail-closed：任何失败都封闭成 Result + error，绝不 panic。
//
// 与 Local 的关键差异：远程执行**没有本地清场概念**——远端进程跑在另一台机器上，
// 超时取消杀掉的只是本地的 ssh 客户端，远端进程可能成为孤儿。因此本执行器**不声称
// 任何清场结论**：provider 残留的 caliber 由证据层以「unknown」诚实记录（ADR 0020
// 前提 4 的「不留残留」= 不假装清场，而非声称已清场）。
func (r Remote) Run(ctx context.Context, spec Spec) (Result, error) {
	res := Result{ExitCode: -1}

	if spec.Remote == nil {
		return res, errors.New("executor: Remote 需要 Spec.Remote（remote 环境的档位必须声明 host）")
	}
	rs := *spec.Remote // 浅拷贝：下面可能要校验，不动调用方结构
	if err := rs.validate(); err != nil {
		return res, err
	}
	if strings.TrimSpace(spec.Command) == "" {
		return res, errors.New("executor: Command 不能为空")
	}
	res.RemoteEndpoint = rs.endpoint()

	bin := strings.TrimSpace(r.Bin)
	if bin == "" {
		bin = "ssh"
	}
	if !isAbsPath(bin) {
		p, err := lookPath(bin)
		if err != nil || p == "" {
			return res, fmt.Errorf("executor: 找不到 ssh CLI %q: %w", bin, err)
		}
		bin = p
	} else if _, err := os.Stat(bin); err != nil {
		return res, fmt.Errorf("executor: ssh CLI 不可用 %q: %w", bin, err)
	}

	limit := spec.MaxOutputBytes
	if limit <= 0 {
		limit = DefaultMaxOutputBytes
	}
	outBuf := newLimitedBuffer(limit)
	errBuf := newLimitedBuffer(limit)

	runCtx := ctx
	var cancel context.CancelFunc
	if spec.Timeout > 0 {
		runCtx, cancel = context.WithTimeout(ctx, spec.Timeout)
		defer cancel()
	}

	args := buildSSHArgs(spec, rs)
	start := time.Now()
	runErr := sshRun(runCtx, bin, args, outBuf, errBuf)
	res.Duration = time.Since(start)

	// 先把已采集的输出落到 Result，无论后续成败 —— 远端挂掉的进程往往正是
	// 因为输出了线索才值得回看。
	stdout, stdoutBytes, truncOut := outBuf.snapshot()
	res.Stdout, res.StdoutBytes = stdout, stdoutBytes
	stderr, stderrBytes, truncErr := errBuf.snapshot()
	res.Stderr, res.StderrBytes = stderr, stderrBytes
	res.Truncated = truncOut || truncErr

	if runErr == nil {
		res.ExitCode = 0
		return res, nil
	}

	// 判定顺序与 Local / Docker 一致：先父 ctx 取消，再本次超时，最后才把
	// ExitError 当正常结果。反过来会把「超时 kill 产生的 ExitError」误记成程序返回 1。
	if errors.Is(ctx.Err(), context.Canceled) {
		res.Canceled = true
		return res, fmt.Errorf("executor: 远程执行被取消: %w", context.Canceled)
	}
	if errors.Is(runCtx.Err(), context.DeadlineExceeded) {
		res.TimedOut = true
		return res, fmt.Errorf("executor: 远程执行超时（上限 %v）：远端进程可能已成孤儿，需人工确认: %w", spec.Timeout, context.DeadlineExceeded)
	}

	var exitErr *exec.ExitError
	if errors.As(runErr, &exitErr) {
		res.ExitCode = exitErr.ExitCode()
		// 非 0 退出是结果，不是执行器故障。
		return res, nil
	}
	return res, fmt.Errorf("executor: 启动或等待 ssh 失败: %w", runErr)
}

// buildSSHArgs 是纯函数：给定 Spec 产出精确 argv。单独抽出来是因为
// 「远端到底跑了什么」完全由这段 argv 决定，必须能被逐字断言。
//
// BatchMode=yes + StrictHostKeyChecking=accept-new 是 fail-closed 的两根保险：
// 缺密钥立即失败（不卡口令提示），首次连接不交互也不跳过主机密钥校验。
func buildSSHArgs(spec Spec, rs RemoteSpec) []string {
	args := []string{
		"-o", "BatchMode=yes",
		"-o", "StrictHostKeyChecking=accept-new",
	}
	if p := rs.effectivePort(); p != 22 {
		args = append(args, "-p", strconv.Itoa(p))
	}
	if id := strings.TrimSpace(rs.IdentityFile); id != "" {
		args = append(args, "-i", id)
	}
	args = append(args, rs.hostPart(), spec.Command)
	return append(args, spec.Args...)
}
