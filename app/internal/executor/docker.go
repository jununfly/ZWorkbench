package executor

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"time"
)

// LabelExecution 打在每一个执行容器上。
//
// 它的存在不是装饰：服务进程若被 SIGKILL（清场代码根本没机会跑），容器会残留。
// 有这条 label 就能用 `docker ps -a --filter label=zworkbench.execution=1` 把
// 「ZWorkbench 起过但没清掉的容器」全找出来，而不是靠人记得有哪些。
const LabelExecution = "zworkbench.execution=1"

// DefaultContainerWorkdir 是容器内工作目录默认值（宿主工作目录 1:1 挂到这里）。
const DefaultContainerWorkdir = "/workspace"

// DefaultCleanupTimeout 是清场命令（docker rm -f）的上限。
// 清场用独立 context：执行超时/取消时原 ctx 已经死了，拿它清场等于不清。
const DefaultCleanupTimeout = 15 * time.Second

// dockerRunFailed 是 docker CLI 表达「docker run 本身失败」的保留退出码。
// 容器内程序的退出码与它不冲突（docker 不会把程序退出码透传成 125）。
const dockerRunFailed = 125

// 清场结论。刻意用三态字符串而不是 bool：清场失败与「本来就没有容器」是
// 两件不同的事，压成一个 false 会让证据无法区分「没问题」和「没清干净」。
const (
	// CleanupRemoved：确认已移除。
	CleanupRemoved = "removed"
	// CleanupAbsent：容器不存在（未创建或已被移除）—— 无残留。
	CleanupAbsent = "absent"
	// CleanupFailed 是前缀，后面拼失败原因：`failed: <原因>`。
	CleanupFailed = "failed: "
)

// ContainerSpec 是「在容器里跑」的包装参数（environment = "container"）。
//
// 与 config.ContainerConfig 刻意分开：config 负责「配置能不能通过校验」，
// 本包负责「拿到手的参数能不能安全地变成 docker argv」。执行器不 import
// config，避免分层倒置；重复的几个默认值方法很便宜。
type ContainerSpec struct {
	// Image 是镜像引用（如 alpine:3.20，或带 digest 的固定引用）。
	Image string
	// Workdir 是**容器内**绝对路径工作目录；空 = DefaultContainerWorkdir。
	// 宿主 Dir 会 1:1 挂载到这里——不做「挂 A 跑 B」的映射，否则
	// 「你以为在测的目录」和「实际跑的目录」会悄悄分叉。
	Workdir string
	// Network 是 --network 取值：none（默认）/ bridge。host 在配置层已被拒绝。
	Network string
	// User 是 --user 取值；空 = 镜像默认用户。
	User string
	// Env 是容器内额外环境变量（"K=V"）。
	Env []string
	// Name 是容器名；空 = 由 Run 生成唯一名。
	// 清场依赖它，所以绝不能为空（生成也必须有）。
	Name string
}

func (c *ContainerSpec) effectiveWorkdir() string {
	if wd := strings.TrimSpace(c.Workdir); wd != "" {
		return wd
	}
	return DefaultContainerWorkdir
}

func (c *ContainerSpec) effectiveNetwork() string {
	if n := strings.TrimSpace(c.Network); n != "" {
		return n
	}
	return "none"
}

// validate 是执行器侧的最后一道闸。配置层已经校验过一遍，这里再校验一遍：
// 执行器不能假设调用方一定校验过（Spec 也可能由测试或未来别的调用方构造）。
func (c *ContainerSpec) validate() error {
	img := strings.TrimSpace(c.Image)
	if img == "" {
		return errors.New("executor: container image 不能为空")
	}
	if strings.HasPrefix(img, "-") {
		return fmt.Errorf("executor: container image 不能以 - 开头（会被当成 docker 选项）：%q", img)
	}
	if strings.ContainsAny(img, " \t\n\r") {
		return fmt.Errorf("executor: container image 不能包含空白：%q", img)
	}
	wd := c.effectiveWorkdir()
	if !strings.HasPrefix(wd, "/") {
		return fmt.Errorf("executor: container workdir 必须是绝对路径，实际 %q", wd)
	}
	if strings.Contains(wd, "..") {
		return fmt.Errorf("executor: container workdir 不能包含 ..，实际 %q", wd)
	}
	if strings.ContainsAny(wd, " \t\n\r") {
		return fmt.Errorf("executor: container workdir 不能包含空白，实际 %q", wd)
	}
	if name := strings.TrimSpace(c.Name); name != "" && !validContainerName(name) {
		return fmt.Errorf("executor: container name %q 非法（只允许字母数字与 _ . -，且不能以符号开头）", name)
	}
	if u := strings.TrimSpace(c.User); u != "" && strings.ContainsAny(u, " \t\n\r") {
		return fmt.Errorf("executor: container user 不能包含空白，实际 %q", u)
	}
	for i, e := range c.Env {
		if strings.ContainsAny(e, "\n\r") {
			return fmt.Errorf("executor: container env[%d] 不能包含换行", i)
		}
	}
	return nil
}

// Docker 在容器里执行（environment = "container"）。
//
// 用 docker CLI（os/exec）而不是 docker SDK：SDK 会破坏 buildguard 的零依赖
// 守卫，而 CLI 的能力对本切片完全够用（ADR 0020 前提 1 的结论）。
type Docker struct {
	// Bin 是 docker CLI 路径；空 = LookPath("docker")。
	Bin string
	// CleanupTimeout 是清场命令上限；<=0 = DefaultCleanupTimeout。
	CleanupTimeout time.Duration
}

// 包级依赖抽出来便于测试注入（与 Local / envprobe 同风格）。
var (
	dockerRun = func(ctx context.Context, bin string, args []string, stdout, stderr io.Writer) error {
		cmd := exec.CommandContext(ctx, bin, args...)
		cmd.Stdout = stdout
		cmd.Stderr = stderr
		return cmd.Run()
	}
	dockerRemove = func(ctx context.Context, bin, name string) ([]byte, error) {
		return exec.CommandContext(ctx, bin, "rm", "-f", name).CombinedOutput()
	}
	nowUnixNano = func() int64 { return time.Now().UnixNano() }
)

// Run 实现 Executor。fail-closed：任何失败都封闭成 Result + error，绝不 panic。
//
// 与 Local 的关键差异：容器是**在宿主意外的进程树**里跑的。杀掉 docker CLI
// 不会杀掉容器，所以超时/取消后必须显式 `docker rm -f` 兜底，并把清场结论
// 如实写进 Result.ContainerCleanup（ADR 0020 前提 4 的「不留残留」）。
func (d Docker) Run(ctx context.Context, spec Spec) (Result, error) {
	res := Result{ExitCode: -1}

	if spec.Container == nil {
		return res, errors.New("executor: Docker 需要 Spec.Container（container 环境的档位必须声明镜像）")
	}
	cs := *spec.Container // 浅拷贝：下面可能要补容器名，不能改调用方的结构
	if err := cs.validate(); err != nil {
		return res, err
	}
	if strings.TrimSpace(spec.Command) == "" {
		return res, errors.New("executor: Command 不能为空")
	}
	if name := strings.TrimSpace(cs.Name); name == "" {
		cs.Name = fmt.Sprintf("zw-exec-%d", nowUnixNano())
	}
	if !validContainerName(cs.Name) {
		return res, fmt.Errorf("executor: container name %q 非法", cs.Name)
	}
	res.ContainerName = cs.Name
	spec.Container = &cs

	// 宿主目录必须先存在：docker 对不存在的 -v 源会**静默创建空目录**，
	// 命令于是跑在一个空仓库上并返回成功 —— 这是最危险的那种假成功。
	if dir := strings.TrimSpace(spec.Dir); dir != "" {
		st, err := os.Stat(dir)
		if err != nil {
			return res, fmt.Errorf("executor: 宿主工作目录不可用 %q: %w（docker 会静默建空目录，故此处拒跑）", dir, err)
		}
		if !st.IsDir() {
			return res, fmt.Errorf("executor: 宿主工作目录不是目录 %q", dir)
		}
	}

	bin := strings.TrimSpace(d.Bin)
	if bin == "" {
		bin = "docker"
	}
	if !isAbsPath(bin) {
		p, err := lookPath(bin)
		if err != nil || p == "" {
			return res, fmt.Errorf("executor: 找不到 docker CLI %q: %w", bin, err)
		}
		bin = p
	} else if _, err := os.Stat(bin); err != nil {
		return res, fmt.Errorf("executor: docker CLI 不可用 %q: %w", bin, err)
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

	args := buildRunArgs(spec)
	start := time.Now()
	runErr := dockerRun(runCtx, bin, args, outBuf, errBuf)
	res.Duration = time.Since(start)

	// 先把已采集的输出落到 Result，无论后续成败 —— 挂掉的容器往往正是
	// 因为输出了线索才值得回看。
	stdout, stdoutBytes, truncOut := outBuf.snapshot()
	res.Stdout, res.StdoutBytes = stdout, stdoutBytes
	stderr, stderrBytes, truncErr := errBuf.snapshot()
	res.Stderr, res.StderrBytes = stderr, stderrBytes
	res.Truncated = truncOut || truncErr

	// 清场先于结果判定：无论成败都要问一句「容器还在不在」。
	res.ContainerCleanup = d.cleanup(bin, cs.Name)

	if runErr == nil {
		res.ExitCode = 0
		return res, nil
	}

	// 判定顺序与 Local 一致：先父 ctx 取消，再本次超时，最后才把 ExitError
	// 当正常结果。反过来会把「超时 kill 产生的 ExitError」误记成程序返回 1。
	if errors.Is(ctx.Err(), context.Canceled) {
		res.Canceled = true
		return res, fmt.Errorf("executor: 容器执行被取消: %w", context.Canceled)
	}
	if errors.Is(runCtx.Err(), context.DeadlineExceeded) {
		res.TimedOut = true
		return res, fmt.Errorf("executor: 容器执行超时（上限 %v）: %w", spec.Timeout, context.DeadlineExceeded)
	}

	var exitErr *exec.ExitError
	if errors.As(runErr, &exitErr) {
		code := exitErr.ExitCode()
		// 125 是 docker run 自身失败，不是容器内程序的结论。当成程序退出码
		// 会让证据里留下「exit 125」这种读不出真假的记录。
		if code == dockerRunFailed {
			return res, fmt.Errorf("executor: docker run 失败（125）而非容器内程序退出: %s", firstLine(res.Stderr))
		}
		res.ExitCode = code
		return res, nil
	}
	return res, fmt.Errorf("executor: 启动或等待 docker 失败: %w", runErr)
}

// cleanup 显式移除容器并给出三态结论。
func (d Docker) cleanup(bin, name string) string {
	if strings.TrimSpace(name) == "" {
		return CleanupFailed + "无容器名，无法清理"
	}
	timeout := d.CleanupTimeout
	if timeout <= 0 {
		timeout = DefaultCleanupTimeout
	}
	// 独立 context：执行超时/取消时原 ctx 已经作废，用它清场等于不清。
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	out, err := dockerRemove(ctx, bin, name)
	if err == nil {
		return CleanupRemoved
	}
	msg := strings.TrimSpace(string(out))
	if msg == "" {
		msg = err.Error()
	}
	// docker 用这条文本表达「本来就没有这个容器」。归到 absent 而不是 failed：
	// 两者都意味着无残留，但 failed 会让人以为需要去手动清场。
	if strings.Contains(strings.ToLower(msg), "no such container") {
		return CleanupAbsent
	}
	return CleanupFailed + firstLine(msg)
}

// buildRunArgs 是纯函数：给定 Spec 产出精确 argv。单独抽出来是因为
// 「容器里到底跑的是什么」完全由这段 argv 决定，必须能被逐字断言。
func buildRunArgs(spec Spec) []string {
	c := spec.Container
	args := []string{
		"run",
		"--init", // 让 tini 收尸僵尸进程，避免 --init 缺失导致容器退出码语义漂移
		"--name", c.Name,
		"--label", LabelExecution,
		"--network", c.effectiveNetwork(),
	}
	if dir := strings.TrimSpace(spec.Dir); dir != "" {
		args = append(args, "-v", dir+":"+c.effectiveWorkdir())
	}
	args = append(args, "-w", c.effectiveWorkdir())
	if u := strings.TrimSpace(c.User); u != "" {
		args = append(args, "--user", u)
	}
	for _, e := range c.Env {
		if strings.TrimSpace(e) == "" {
			continue
		}
		args = append(args, "-e", e)
	}
	args = append(args, c.Image, spec.Command)
	return append(args, spec.Args...)
}

// validContainerName 判定是否符合 docker 的容器名约束。
func validContainerName(name string) bool {
	for i, r := range name {
		switch {
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9':
		case r == '_' || r == '.' || r == '-':
			if i == 0 {
				return false
			}
		default:
			return false
		}
	}
	return name != ""
}

// firstLine 取首行并限长，避免把整段 docker 报错塞进错误串。
func firstLine(s string) string {
	s = strings.TrimSpace(s)
	if i := strings.IndexAny(s, "\r\n"); i >= 0 {
		s = s[:i]
	}
	if len(s) > 300 {
		return s[:300] + "…"
	}
	return s
}
