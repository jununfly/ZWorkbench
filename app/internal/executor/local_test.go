package executor

import (
	"context"
	"errors"
	"os/exec"
	"strings"
	"testing"
	"time"
)

// 执行器的语义约定（ADR 0020）：
//
//	退出码不是错误。非 0 退出是「执行发生了且拿到结果」，属于正常返回
//	（ExitCode=N, err=nil）；只有「执行器自己没跑成」（命令不存在、超时、
//	取消、IO 故障）才返回 error。这条边界若反了，owner 会把「程序返回 1」
//	误记成「证据链故障」，也把「真的跑挂了」误记成成功。
//
// 所有用例都显式设置 Dir，避免测试跟着 cwd 漂。

// shPath 返回本机 sh；没有就跳过（执行器必须有真实进程才能验证）。
func shPath(t *testing.T) string {
	t.Helper()
	p, err := exec.LookPath("sh")
	if err != nil {
		t.Skip("本机无 sh，跳过真实进程执行测试")
	}
	return p
}

func TestLocalRunSuccess(t *testing.T) {
	sh := shPath(t)
	res, err := Local{}.Run(context.Background(), Spec{
		Command: sh,
		Args:    []string{"-c", "printf hello"},
		Dir:     t.TempDir(),
		Timeout: 5 * time.Second,
	})
	if err != nil {
		t.Fatalf("正常退出不应报错：%v", err)
	}
	if res.ExitCode != 0 {
		t.Fatalf("exit code 期望 0，实际 %d", res.ExitCode)
	}
	if res.Stdout != "hello" {
		t.Fatalf("stdout 期望 hello，实际 %q", res.Stdout)
	}
	if res.TimedOut || res.Canceled {
		t.Fatal("正常执行不应标记超时/取消")
	}
	if res.Duration <= 0 {
		t.Fatal("应记录执行耗时")
	}
}

// TestLocalRunNonZeroExitIsNotAnError 是这张表里最关键的一条：
// 程序返回非 0 是**结果**，不是**执行器故障**。
func TestLocalRunNonZeroExitIsNotAnError(t *testing.T) {
	sh := shPath(t)
	res, err := Local{}.Run(context.Background(), Spec{
		Command: sh,
		Args:    []string{"-c", "echo boom >&2; exit 3"},
		Dir:     t.TempDir(),
		Timeout: 5 * time.Second,
	})
	if err != nil {
		t.Fatalf("非 0 退出不应返回 error（它是结果而非故障）：%v", err)
	}
	if res.ExitCode != 3 {
		t.Fatalf("exit code 期望 3，实际 %d", res.ExitCode)
	}
	if !strings.Contains(res.Stderr, "boom") {
		t.Fatalf("stderr 应含 boom，实际 %q", res.Stderr)
	}
}

func TestLocalRunTimeout(t *testing.T) {
	sh := shPath(t)
	start := time.Now()
	res, err := Local{}.Run(context.Background(), Spec{
		Command: sh,
		Args:    []string{"-c", "sleep 5"},
		Dir:     t.TempDir(),
		Timeout: 150 * time.Millisecond,
	})
	if err == nil {
		t.Fatal("超时必须返回 error（不能让调用方以为执行正常结束）")
	}
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("超时 error 应 wrap context.DeadlineExceeded，实际 %v", err)
	}
	if !res.TimedOut {
		t.Fatal("应标记 TimedOut")
	}
	if res.Canceled {
		t.Fatal("超时不应同时标记 Canceled（两者要能区分）")
	}
	if time.Since(start) > 3*time.Second {
		t.Fatalf("超时未及时生效，耗时 %v", time.Since(start))
	}
}

func TestLocalRunCancel(t *testing.T) {
	sh := shPath(t)
	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(100 * time.Millisecond)
		cancel()
	}()
	res, err := Local{}.Run(ctx, Spec{
		Command: sh,
		Args:    []string{"-c", "sleep 5"},
		Dir:     t.TempDir(),
		Timeout: 10 * time.Second,
	})
	if err == nil {
		t.Fatal("取消必须返回 error")
	}
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("取消 error 应 wrap context.Canceled，实际 %v", err)
	}
	if !res.Canceled {
		t.Fatal("应标记 Canceled")
	}
	if res.TimedOut {
		t.Fatal("取消不应同时标记 TimedOut")
	}
}

func TestLocalRunOutputTruncation(t *testing.T) {
	if testing.Short() {
		t.Skip("short 模式跳过")
	}
	sh := shPath(t)
	const limit = 64
	res, err := Local{}.Run(context.Background(), Spec{
		Command:        sh,
		Args:           []string{"-c", "printf '%0200d' 0"},
		Dir:            t.TempDir(),
		Timeout:        5 * time.Second,
		MaxOutputBytes: limit,
	})
	if err != nil {
		t.Fatalf("执行不应报错：%v", err)
	}
	if !res.Truncated {
		t.Fatal("超过上限应标记 Truncated")
	}
	if len(res.Stdout) != limit {
		t.Fatalf("保留长度应等于上限 %d，实际 %d", limit, len(res.Stdout))
	}
	if res.StdoutBytes <= limit {
		t.Fatalf("应记录原始总字节数（>%d），实际 %d", limit, res.StdoutBytes)
	}
}

func TestLocalRunCommandNotFound(t *testing.T) {
	res, err := Local{}.Run(context.Background(), Spec{
		Command: "definitely-not-a-real-binary-zw",
		Dir:     t.TempDir(),
		Timeout: 2 * time.Second,
	})
	if err == nil {
		t.Fatal("命令不存在必须返回 error")
	}
	if res.TimedOut || res.Canceled {
		t.Fatal("命令不存在不应标记超时/取消")
	}
	if res.ExitCode != -1 {
		t.Fatalf("未启动应记 exit code -1，实际 %d", res.ExitCode)
	}
}

func TestLocalRunDir(t *testing.T) {
	sh := shPath(t)
	dir := t.TempDir()
	res, err := Local{}.Run(context.Background(), Spec{
		Command: sh,
		Args:    []string{"-c", "pwd"},
		Dir:     dir,
		Timeout: 5 * time.Second,
	})
	if err != nil {
		t.Fatalf("执行不应报错：%v", err)
	}
	// macOS /tmp 是 /private/tmp 的符号链接，用后缀匹配避免平台差异。
	if !strings.HasSuffix(strings.TrimSpace(res.Stdout), strings.TrimPrefix(dir, "/private")) {
		t.Fatalf("cwd 未生效：期望 %q，实际 %q", dir, strings.TrimSpace(res.Stdout))
	}
}

// TestLocalRunDoesNotUseShell 证明执行器不经过 shell 解释：
// 参数里的分号必须是普通字符，不能被当成命令分隔符。
func TestLocalRunDoesNotUseShell(t *testing.T) {
	sh := shPath(t)
	res, err := Local{}.Run(context.Background(), Spec{
		Command: sh,
		Args:    []string{"-c", `printf '%s' "$1"`, "sh", "a;b"},
		Dir:     t.TempDir(),
		Timeout: 5 * time.Second,
	})
	if err != nil {
		t.Fatalf("执行不应报错：%v", err)
	}
	if res.Stdout != "a;b" {
		t.Fatalf("分号应原样传递（不解释），实际 %q", res.Stdout)
	}
}
