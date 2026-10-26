// Package executor 抽象「真正把东西跑起来」的能力（ADR 0020 首刀）。
//
// 边界（与 internal/envprobe、internal/evidence 的分工）：
//   - envprobe 只回答「这个环境此刻可达吗」，绝不驱动执行；
//   - evidence 是记账侧 durable owner，只回答「记下发生了什么」；
//   - 本包只回答「跑起来、跑完了、退出码多少、输出了什么」，
//     **不写任何存储、不改任何 run 状态**。记账由 internal/execution 编排层
//     交回 owner，保证「单一 durable owner」不变式不被执行器破坏。
//
// 零依赖：仅标准库 os/exec + context。不引 docker/containerd SDK，以过
// buildguard 的零依赖守卫（go.mod ⊆ allowlist，无 cgo）。
//
// 安全基线：**从不经过 shell**。调用方给 Command + Args，本包按 argv 直接
// exec，所以参数里的分号、管道、$ 都是普通字符。这条不写进注释就迟早被
// 「顺手加个 sh -c 支持通配符」改掉，因此在此显式声明为不变式。
package executor

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

// DefaultMaxOutputBytes 是单条流（stdout / stderr 各自）默认保留上限。
// 超出即截断并在 Result.Truncated 上标记，绝不把无限输出塞进证据库。
const DefaultMaxOutputBytes = 64 * 1024

// Spec 是一次执行的完整规格。由调用方（编排层）从预置执行档位构造，
// 不能直接来自 HTTP body —— 否则等于开放任意命令执行。
type Spec struct {
	// Command 是可执行文件：裸名走 PATH，或绝对路径。
	Command string
	// Args 是原样传给程序的参数，不经 shell 解析。
	Args []string
	// Dir 是工作目录；空 = 继承服务进程 cwd（调用方通常应显式给出）。
	Dir string
	// Timeout 是执行上限；<=0 走 DefaultExecutionTimeout 的语义由调用方保证，
	// 本层对 <=0 视为「不限时」，因为兜底默认值属于配置层职责。
	Timeout time.Duration
	// Env 是追加到当前进程环境之后的环境变量（"K=V" 形式）；nil = 仅继承。
	Env []string
	// MaxOutputBytes 是单条流的保留上限；<=0 走 DefaultMaxOutputBytes。
	MaxOutputBytes int
	// Container 非空表示在容器里执行（见 docker.go）；nil = 直接在宿主执行。
	// 由编排层按 run 声明的 environment 决定，不来自 HTTP body。
	Container *ContainerSpec
	// Remote 非空表示在远端执行（见 remote.go）；nil = 本地/容器执行。
	// 由编排层按 run 声明的 environment 决定，不来自 HTTP body。
	Remote *RemoteSpec
}

// Result 是一次执行的结果快照。
//
// ExitCode 语义：正常启动并退出时为真实退出码；进程未启动（命令不存在等）为 -1。
// StdoutBytes / StderrBytes 是**截断前**的原始总字节数，用于让证据能说明
// 「我们只保留了前 N 字节」而不是假装输出就这么短。
type Result struct {
	ExitCode    int           `json:"exit_code"`
	Stdout      string        `json:"stdout"`
	Stderr      string        `json:"stderr"`
	StdoutBytes int           `json:"stdout_bytes"`
	StderrBytes int           `json:"stderr_bytes"`
	Truncated   bool          `json:"truncated"`
	Duration    time.Duration `json:"duration"`
	TimedOut    bool          `json:"timed_out"`
	Canceled    bool          `json:"canceled"`
	// ContainerName / ContainerCleanup 只在容器执行时非空。
	// ContainerCleanup 三态：removed / absent / "failed: <原因>" —— 清场失败
	// 与「本来就没有容器」必须能区分，否则证据看不出到底是残留还是没建。
	ContainerName    string `json:"container_name,omitempty"`
	ContainerCleanup string `json:"container_cleanup,omitempty"`
	// RemoteEndpoint 只在远程执行时非空，记录「连的是哪台机器」（host:port），
	// 供证据事件/effect 展示——事后要能回答「这次副作用落在哪台远端」。
	RemoteEndpoint string `json:"remote_endpoint,omitempty"`
}

// Executor 是执行环境的统一抽象（ADR 0020 前提 1）。
// 首刀只有 Local；container / remote 是后续切片，接口保持不变。
type Executor interface {
	// Run 执行一次并等待结束。返回 error 仅表示**执行器没跑成**
	// （命令不存在、超时、取消、IO 故障）；程序本身的非 0 退出是正常返回。
	Run(ctx context.Context, spec Spec) (Result, error)
}

// Local 在服务进程所在机器上直接执行（environment = "local"）。
type Local struct{}

// 包级依赖抽出来便于测试注入（与本仓 envprobe 同风格）。
var (
	lookPath = exec.LookPath
)

// Run 实现 Executor。fail-closed：任何失败都封闭成 Result + error，绝不 panic。
func (Local) Run(ctx context.Context, spec Spec) (Result, error) {
	res := Result{ExitCode: -1}
	if spec.Command == "" {
		return res, errors.New("executor: Command 不能为空")
	}

	bin := spec.Command
	// 裸名先 LookPath：既能让「命令不存在」在启动前就给出清晰错误，
	// 也让错误不会被误判成超时（cmd.Run 对不存在命令的报错与超时不同，但提前判定更稳）。
	if !isAbsPath(bin) {
		p, err := lookPath(bin)
		if err != nil || p == "" {
			return res, fmt.Errorf("executor: 找不到可执行文件 %q: %w", bin, err)
		}
		bin = p
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

	start := time.Now()
	runErr := commandRun(runCtx, bin, spec, outBuf, errBuf)
	res.Duration = time.Since(start)

	// 先把已采集的输出落到 Result，无论后续成败 —— 超时的进程往往正是
	// 因为输出了线索才值得回看。
	res.Stdout, res.StdoutBytes, res.Truncated = outBuf.snapshot()
	stderr, stderrBytes, stderrTrunc := errBuf.snapshot()
	res.Stderr, res.StderrBytes = stderr, stderrBytes
	if stderrTrunc {
		res.Truncated = true
	}

	if runErr == nil {
		res.ExitCode = 0
		return res, nil
	}

	// 判定顺序很重要：先看**父 context**是否被取消（用户主动停），
	// 再看本次执行是否超时，最后才把 *exec.ExitError 当正常结果。
	// 反过来会让「超时 kill 产生的 ExitError」被误记成「程序返回 1」。
	if errors.Is(ctx.Err(), context.Canceled) {
		res.Canceled = true
		return res, fmt.Errorf("executor: 执行被取消: %w", context.Canceled)
	}
	if errors.Is(runCtx.Err(), context.DeadlineExceeded) {
		res.TimedOut = true
		return res, fmt.Errorf("executor: 执行超时（上限 %v）: %w", spec.Timeout, context.DeadlineExceeded)
	}

	var exitErr *exec.ExitError
	if errors.As(runErr, &exitErr) {
		res.ExitCode = exitErr.ExitCode()
		// 非 0 退出是结果，不是执行器故障。
		return res, nil
	}
	return res, fmt.Errorf("executor: 启动或等待进程失败: %w", runErr)
}

// commandRun 起进程并等待结束，输出写入调用方给的 writer。
// 抽成包级 var 便于测试注入启动失败；生产路径就是真实的
// exec.CommandContext(...).Run()。**不经 shell** —— 这是安全不变式。
var commandRun = func(ctx context.Context, bin string, spec Spec, stdout, stderr io.Writer) error {
	cmd := exec.CommandContext(ctx, bin, spec.Args...)
	cmd.Dir = spec.Dir
	cmd.Stdout = stdout
	cmd.Stderr = stderr
	if len(spec.Env) > 0 {
		cmd.Env = append(os.Environ(), spec.Env...)
	}
	return cmd.Run()
}

func isAbsPath(p string) bool { return filepath.IsAbs(p) }

// limitedBuffer 是带上限的 io.Writer：只保留前 limit 字节，
// 但持续统计总写入量，让 Result 能诚实报告「被截断了、原长多少」。
type limitedBuffer struct {
	mu      sync.Mutex
	buf     []byte
	limit   int
	total   int
	dropped bool
}

func newLimitedBuffer(limit int) *limitedBuffer {
	return &limitedBuffer{limit: limit}
}

func (b *limitedBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.total += len(p)
	room := b.limit - len(b.buf)
	if room > 0 {
		n := len(p)
		if n > room {
			n = room
		}
		b.buf = append(b.buf, p[:n]...)
		if n < len(p) {
			b.dropped = true
		}
	} else if len(p) > 0 {
		b.dropped = true
	}
	// 始终报告全部写入成功：让子进程继续正常输出，而不是因短写提前退出。
	return len(p), nil
}

// snapshot 返回（保留内容, 原始总字节, 是否截断）。
func (b *limitedBuffer) snapshot() (string, int, bool) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return string(b.buf), b.total, b.dropped
}
