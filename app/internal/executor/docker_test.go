package executor

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// fakeDocker 写一个假 docker CLI，测试不需要真 docker daemon：
//   - 每次调用的 argv 追加到日志，便于断言「跑了什么」「有没有清场」；
//   - run 按 FAKE_* 环境变量决定输出 / 退出码 / 睡眠；
//   - rm 按 FAKE_RM_* 决定清场成败（用它验证「清场失败要如实记录」）。
//
// 这样做而不是 mock 掉 exec：真起进程才能覆盖输出采集、退出码解析、
// context 取消这三处真正的失败模式。
func fakeDocker(t *testing.T) (bin, logPath string) {
	t.Helper()
	dir := t.TempDir()
	bin = filepath.Join(dir, "docker")
	logPath = filepath.Join(dir, "calls.log")
	script := `#!/bin/sh
printf '%s\n' "$*" >> "` + logPath + `"
case "$1" in
  run)
    [ -n "$FAKE_STDOUT" ] && printf '%s' "$FAKE_STDOUT"
    [ -n "$FAKE_STDERR" ] && printf '%s' "$FAKE_STDERR" >&2
    [ -n "$FAKE_SLEEP" ] && sleep "$FAKE_SLEEP"
    exit "${FAKE_EXIT:-0}"
    ;;
  rm)
    [ -n "$FAKE_RM_STDERR" ] && printf '%s' "$FAKE_RM_STDERR" >&2
    exit "${FAKE_RM_EXIT:-0}"
    ;;
esac
exit 0
`
	if err := os.WriteFile(bin, []byte(script), 0o755); err != nil {
		t.Fatalf("写假 docker 失败：%v", err)
	}
	return bin, logPath
}

func readCalls(t *testing.T, logPath string) []string {
	t.Helper()
	data, err := os.ReadFile(logPath)
	if err != nil {
		return nil
	}
	var out []string
	for _, line := range strings.Split(string(data), "\n") {
		if strings.TrimSpace(line) != "" {
			out = append(out, line)
		}
	}
	return out
}

func containerSpec() *ContainerSpec {
	return &ContainerSpec{
		Image:   "alpine:3.20",
		Workdir: "/workspace",
		Network: "none",
		Env:     []string{"CGO_ENABLED=0"},
		Name:    "zw-exec-test",
	}
}

// argv 必须精确：多一个 --rm 或少一个 -w 都会让「容器里跑什么」与配置不符。
func TestBuildRunArgs(t *testing.T) {
	spec := Spec{
		Command:   "go",
		Args:      []string{"test", "./..."},
		Dir:       "/repo/zw",
		Container: containerSpec(),
	}
	got := buildRunArgs(spec)
	want := []string{
		"run",
		"--init",
		"--name", "zw-exec-test",
		"--label", LabelExecution,
		"--network", "none",
		"-v", "/repo/zw:/workspace",
		"-w", "/workspace",
		"-e", "CGO_ENABLED=0",
		"alpine:3.20",
		"go", "test", "./...",
	}
	if strings.Join(got, " ") != strings.Join(want, " ") {
		t.Fatalf("argv 不符\n got: %v\nwant: %v", got, want)
	}

	// 未声明 user / network / workdir 时走默认：none + /workspace，且不带 --user。
	minimal := Spec{Command: "ls", Container: &ContainerSpec{Image: "alpine:3.20", Name: "n1"}}
	got = buildRunArgs(minimal)
	joined := strings.Join(got, " ")
	if !strings.Contains(joined, "--network none") {
		t.Fatalf("未声明网络必须回退 none（fail-closed），实际 %v", got)
	}
	if !strings.Contains(joined, "-w /workspace") {
		t.Fatalf("未声明容器工作目录必须回退 /workspace，实际 %v", got)
	}
	if strings.Contains(joined, "--user") {
		t.Fatalf("未声明 user 不应注入 --user，实际 %v", got)
	}
	if strings.Contains(joined, "-v") {
		t.Fatalf("宿主目录为空时不应挂载任何卷，实际 %v", got)
	}
}

func TestDockerRejectsBadSpec(t *testing.T) {
	d := Docker{Bin: "/bin/true"}
	cases := []struct {
		name string
		spec Spec
		want string
	}{
		{"缺容器段", Spec{Command: "go"}, "Container"},
		{"镜像为空", Spec{Command: "go", Container: &ContainerSpec{Image: " "}}, "image"},
		{"容器工作目录非绝对", Spec{Command: "go", Container: &ContainerSpec{Image: "a", Workdir: "rel"}}, "workdir"},
		{"命令为空", Spec{Container: containerSpec()}, "Command"},
		{"容器名非法", Spec{Command: "go", Container: &ContainerSpec{Image: "a", Name: "-bad"}}, "name"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := d.Run(context.Background(), tc.spec)
			if err == nil {
				t.Fatal("期望拒绝，实际通过")
			}
			if !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("错误应含 %q，实际 %q", tc.want, err.Error())
			}
		})
	}
}

// 宿主目录不存在时必须拒跑：docker 会静默创建一个空目录挂进去，
// 命令于是跑在「空仓库」上并返回成功——这是最危险的假成功。
func TestDockerRejectsMissingHostDir(t *testing.T) {
	bin, log := fakeDocker(t)
	d := Docker{Bin: bin}
	spec := Spec{Command: "go", Dir: filepath.Join(t.TempDir(), "nope"), Container: containerSpec()}

	if _, err := d.Run(context.Background(), spec); err == nil {
		t.Fatal("宿主目录不存在应拒绝执行")
	}
	for _, call := range readCalls(t, log) {
		if strings.HasPrefix(call, "run ") {
			t.Fatalf("宿主目录不存在时不应起容器，实际调用了：%s", call)
		}
	}
}

func TestDockerSuccessRecordsCleanup(t *testing.T) {
	bin, log := fakeDocker(t)
	t.Setenv("FAKE_STDOUT", "hello from container")
	t.Setenv("FAKE_EXIT", "0")

	d := Docker{Bin: bin}
	res, err := d.Run(context.Background(), Spec{
		Command: "echo", Args: []string{"hi"}, Dir: t.TempDir(), Container: containerSpec(),
	})
	if err != nil {
		t.Fatalf("正常退出不应报错：%v", err)
	}
	if res.ExitCode != 0 || !strings.Contains(res.Stdout, "hello from container") {
		t.Fatalf("结果不符：%+v", res)
	}
	if res.ContainerName != "zw-exec-test" {
		t.Fatalf("应记录容器名，实际 %q", res.ContainerName)
	}
	if res.ContainerCleanup != CleanupRemoved {
		t.Fatalf("成功路径也必须显式清场并记为 %q，实际 %q", CleanupRemoved, res.ContainerCleanup)
	}
	calls := readCalls(t, log)
	if len(calls) != 2 {
		t.Fatalf("期望 run + rm 两次调用，实际 %d：%v", len(calls), calls)
	}
	if !strings.HasPrefix(calls[1], "rm -f zw-exec-test") {
		t.Fatalf("第二次调用应是显式清场，实际 %q", calls[1])
	}
	// 刻意不使用 --rm：清场必须是我们自己的可观测动作，
	// 否则「容器到底还在不在」只能靠猜。
	for _, call := range calls {
		if strings.Contains(call, "--rm") {
			t.Fatalf("不应使用 --rm（清场要显式可观测），实际 %q", call)
		}
	}
}

func TestDockerNonZeroExitIsResult(t *testing.T) {
	bin, _ := fakeDocker(t)
	t.Setenv("FAKE_EXIT", "7")
	t.Setenv("FAKE_STDERR", "oops")

	d := Docker{Bin: bin}
	res, err := d.Run(context.Background(), Spec{Command: "false", Container: containerSpec()})
	if err != nil {
		t.Fatalf("非 0 退出是执行结论，不是执行器故障：%v", err)
	}
	if res.ExitCode != 7 {
		t.Fatalf("退出码应为 7，实际 %d", res.ExitCode)
	}
	if !strings.Contains(res.Stderr, "oops") {
		t.Fatalf("stderr 未采集：%+v", res)
	}
}

// 125 是 docker run 自身的失败（daemon 不可用、参数非法等），不是容器里程序的退出码。
// 把它当程序结果会让证据里出现「exit 125 的假结论」。
func TestDockerDaemonFailure125IsError(t *testing.T) {
	bin, log := fakeDocker(t)
	t.Setenv("FAKE_EXIT", "125")
	t.Setenv("FAKE_STDERR", "Cannot connect to the Docker daemon")

	d := Docker{Bin: bin}
	_, err := d.Run(context.Background(), Spec{Command: "go", Container: containerSpec()})
	if err == nil {
		t.Fatal("125 应作为执行器故障返回 error")
	}
	if !strings.Contains(err.Error(), "125") {
		t.Fatalf("错误应点明 125，实际 %q", err.Error())
	}
	calls := readCalls(t, log)
	if len(calls) < 2 || !strings.HasPrefix(calls[len(calls)-1], "rm -f") {
		t.Fatalf("失败路径也要尝试清场，实际调用：%v", calls)
	}
}

func TestDockerTimeoutCleansUp(t *testing.T) {
	bin, log := fakeDocker(t)
	t.Setenv("FAKE_SLEEP", "5")

	d := Docker{Bin: bin}
	start := time.Now()
	res, err := d.Run(context.Background(), Spec{
		Command: "sleep", Timeout: 200 * time.Millisecond, Container: containerSpec(),
	})
	elapsed := time.Since(start)
	if err == nil || !res.TimedOut {
		t.Fatalf("应超时并标记 TimedOut，实际 res=%+v err=%v", res, err)
	}
	if elapsed > 3*time.Second {
		t.Fatalf("超时后应尽快返回（docker CLI 被杀），实际耗时 %v", elapsed)
	}
	calls := readCalls(t, log)
	var sawRm bool
	for _, c := range calls {
		if strings.HasPrefix(c, "rm -f zw-exec-test") {
			sawRm = true
		}
	}
	if !sawRm {
		t.Fatalf("超时后必须 docker rm -f 兜底（否则容器会一直跑），实际调用：%v", calls)
	}
	if res.ContainerCleanup != CleanupRemoved {
		t.Fatalf("清场成功应记为 %q，实际 %q", CleanupRemoved, res.ContainerCleanup)
	}
}

// 清场失败必须如实记录，不能因为「执行本身成功了」就吞掉。
// 这与 exit_ledger 的「unknown 不默认升级为已清场」是同一条纪律。
func TestDockerCleanupFailureIsRecorded(t *testing.T) {
	bin, _ := fakeDocker(t)
	t.Setenv("FAKE_RM_EXIT", "1")
	t.Setenv("FAKE_RM_STDERR", "permission denied")

	d := Docker{Bin: bin}
	res, err := d.Run(context.Background(), Spec{Command: "go", Container: containerSpec()})
	if err != nil {
		t.Fatalf("执行本身成功，不应因清场失败而报错：%v", err)
	}
	if !strings.HasPrefix(res.ContainerCleanup, CleanupFailed) {
		t.Fatalf("清场失败应记为 %q 前缀，实际 %q", CleanupFailed, res.ContainerCleanup)
	}
	if !strings.Contains(res.ContainerCleanup, "permission denied") {
		t.Fatalf("应保留清场失败原因，实际 %q", res.ContainerCleanup)
	}
}

// 「本来就没有这个容器」不等于「清场失败」：docker 用 stderr 文本表达这件事，
// 压成同一类会让证据看不出到底是残留还是压根没建。
func TestDockerCleanupAbsentIsDistinct(t *testing.T) {
	bin, _ := fakeDocker(t)
	t.Setenv("FAKE_RM_EXIT", "1")
	t.Setenv("FAKE_RM_STDERR", "Error: No such container: zw-exec-test")

	d := Docker{Bin: bin}
	res, _ := d.Run(context.Background(), Spec{Command: "go", Container: containerSpec()})
	if res.ContainerCleanup != CleanupAbsent {
		t.Fatalf("容器不存在应记为 %q，实际 %q", CleanupAbsent, res.ContainerCleanup)
	}
}

func TestDockerMissingBinary(t *testing.T) {
	d := Docker{Bin: filepath.Join(t.TempDir(), "no-docker")}
	_, err := d.Run(context.Background(), Spec{Command: "go", Container: containerSpec()})
	if err == nil || !strings.Contains(err.Error(), "docker") {
		t.Fatalf("缺少 docker CLI 应报清晰错误，实际 %v", err)
	}
}

func TestContainerSpecDefaults(t *testing.T) {
	c := &ContainerSpec{Image: "alpine"}
	if c.effectiveWorkdir() != DefaultContainerWorkdir {
		t.Fatalf("默认容器工作目录应为 %q，实际 %q", DefaultContainerWorkdir, c.effectiveWorkdir())
	}
	if c.effectiveNetwork() != "none" {
		t.Fatalf("默认网络应为 none，实际 %q", c.effectiveNetwork())
	}
}
