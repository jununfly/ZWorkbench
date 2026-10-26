package executor

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// fakeSSH 写一个假 ssh CLI，测试不需要真 ssh daemon 或真主机：
//   - 每次调用的 argv 追加到日志，便于断言「连了谁、跑了什么」；
//   - 按 FAKE_* 环境变量决定输出 / 退出码 / 睡眠；
//   - 始终尊重 BatchMode=yes（不模拟口令提示挂起），让超时/失败测试可控。
func fakeSSH(t *testing.T) (bin, logPath string) {
	t.Helper()
	dir := t.TempDir()
	bin = filepath.Join(dir, "ssh")
	logPath = filepath.Join(dir, "calls.log")
	script := `#!/bin/sh
printf '%s\n' "$*" >> "` + logPath + `"
[ -n "$FAKE_STDOUT" ] && printf '%s' "$FAKE_STDOUT"
[ -n "$FAKE_STDERR" ] && printf '%s' "$FAKE_STDERR" >&2
[ -n "$FAKE_SLEEP" ] && sleep "$FAKE_SLEEP"
exit "${FAKE_EXIT:-0}"
`
	if err := os.WriteFile(bin, []byte(script), 0o755); err != nil {
		t.Fatalf("写假 ssh 失败：%v", err)
	}
	return bin, logPath
}

func remoteSpec() *RemoteSpec {
	return &RemoteSpec{Host: "build.example.com", Port: 2222}
}

// argv 必须精确：BatchMode / StrictHostKeyChecking 两根保险 + 端口 + 命令。
func TestBuildSSHArgs(t *testing.T) {
	spec := Spec{Command: "go", Args: []string{"test", "./..."}, Remote: remoteSpec()}
	got := buildSSHArgs(spec, *spec.Remote)
	want := []string{
		"-o", "BatchMode=yes",
		"-o", "StrictHostKeyChecking=accept-new",
		"-p", "2222",
		"build.example.com",
		"go", "test", "./...",
	}
	if strings.Join(got, " ") != strings.Join(want, " ") {
		t.Fatalf("argv 不符\n got: %v\nwant: %v", got, want)
	}

	// 默认端口 22 不应注入 -p；有 user / identity 时须带上。
	full := Spec{Command: "echo", Args: []string{"hi"},
		Remote: &RemoteSpec{Host: "h", Port: 0, User: "ci", IdentityFile: "/keys/id"}}
	got = buildSSHArgs(full, *full.Remote)
	joined := strings.Join(got, " ")
	if strings.Contains(joined, "-p") {
		t.Fatalf("默认端口不应注入 -p，实际 %v", got)
	}
	if !strings.Contains(joined, "-i /keys/id") {
		t.Fatalf("identity 文件必须注入，实际 %v", got)
	}
	if !strings.Contains(joined, "ci@h") {
		t.Fatalf("user@host 必须拼接，实际 %v", got)
	}
}

func TestRemoteRejectsBadSpec(t *testing.T) {
	bin, _ := fakeSSH(t)
	r := Remote{Bin: bin}
	cases := []struct {
		name string
		spec Spec
		want string
	}{
		{"缺远程段", Spec{Command: "go"}, "Remote"},
		{"host 为空", Spec{Command: "go", Remote: &RemoteSpec{}}, "host"},
		{"命令为空", Spec{Remote: remoteSpec()}, "Command"},
		{"端口越界", Spec{Command: "go", Remote: &RemoteSpec{Host: "h", Port: 70000}}, "port"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := r.Run(context.Background(), tc.spec)
			if err == nil {
				t.Fatal("期望拒绝，实际通过")
			}
			if !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("错误应含 %q，实际 %q", tc.want, err.Error())
			}
		})
	}
}

func TestRemoteSuccess(t *testing.T) {
	bin, log := fakeSSH(t)
	t.Setenv("FAKE_STDOUT", "hello from remote")
	t.Setenv("FAKE_EXIT", "0")

	r := Remote{Bin: bin}
	res, err := r.Run(context.Background(), Spec{Command: "echo", Args: []string{"hi"}, Remote: remoteSpec()})
	if err != nil {
		t.Fatalf("正常退出不应报错：%v", err)
	}
	if res.ExitCode != 0 || !strings.Contains(res.Stdout, "hello from remote") {
		t.Fatalf("结果不符：%+v", res)
	}
	if res.RemoteEndpoint != "build.example.com:2222" {
		t.Fatalf("应记录远端端点，实际 %q", res.RemoteEndpoint)
	}
	calls := readCalls(t, log)
	if len(calls) != 1 {
		t.Fatalf("期望 1 次调用，实际 %d：%v", len(calls), calls)
	}
	if !strings.Contains(calls[0], "BatchMode=yes") || !strings.Contains(calls[0], "StrictHostKeyChecking=accept-new") {
		t.Fatalf("fail-closed 两根保险必须存在，实际 %q", calls[0])
	}
	if !strings.Contains(calls[0], "-p 2222") {
		t.Fatalf("端口必须透传，实际 %q", calls[0])
	}
}

func TestRemoteNonZeroExitIsResult(t *testing.T) {
	bin, _ := fakeSSH(t)
	t.Setenv("FAKE_EXIT", "7")
	t.Setenv("FAKE_STDERR", "oops")

	r := Remote{Bin: bin}
	res, err := r.Run(context.Background(), Spec{Command: "false", Remote: remoteSpec()})
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

// 超时后必须标记 TimedOut 并返回，且远端进程可能已成孤儿（诚实，不假装清场）。
func TestRemoteTimeout(t *testing.T) {
	bin, _ := fakeSSH(t)
	t.Setenv("FAKE_SLEEP", "5")

	r := Remote{Bin: bin}
	start := time.Now()
	res, err := r.Run(context.Background(), Spec{Command: "sleep", Timeout: 200 * time.Millisecond, Remote: remoteSpec()})
	elapsed := time.Since(start)
	if err == nil || !res.TimedOut {
		t.Fatalf("应超时并标记 TimedOut，实际 res=%+v err=%v", res, err)
	}
	if elapsed > 3*time.Second {
		t.Fatalf("超时后应尽快返回（ssh 客户端被杀），实际耗时 %v", elapsed)
	}
	if res.ExitCode != -1 {
		t.Fatalf("超时未启动成功应保留 -1，实际 %d", res.ExitCode)
	}
}

func TestRemoteMissingBinary(t *testing.T) {
	r := Remote{Bin: filepath.Join(t.TempDir(), "no-ssh")}
	_, err := r.Run(context.Background(), Spec{Command: "go", Remote: remoteSpec()})
	if err == nil || !strings.Contains(err.Error(), "ssh") {
		t.Fatalf("缺少 ssh CLI 应报清晰错误，实际 %v", err)
	}
}

// BatchMode=yes 保证「缺密钥」是立即失败而不是卡在口令提示上（fail-closed）。
// 这里用假的 exit 255（ssh 无可用认证时的典型退出码）模拟，验证不会挂起。
func TestRemoteBatchModeFailsFast(t *testing.T) {
	bin, _ := fakeSSH(t)
	t.Setenv("FAKE_EXIT", "255")
	t.Setenv("FAKE_STDERR", "Permission denied (publickey)")

	r := Remote{Bin: bin}
	start := time.Now()
	res, err := r.Run(context.Background(), Spec{Command: "go", Remote: remoteSpec()})
	elapsed := time.Since(start)
	if err != nil {
		t.Fatalf("非 0 退出是执行结论，不应返回 error：%v", err)
	}
	if res.ExitCode != 255 {
		t.Fatalf("缺密钥应以 exit 255 作为结论，实际 %d", res.ExitCode)
	}
	if elapsed > 2*time.Second {
		t.Fatalf("BatchMode=yes 下不应卡口令提示，实际耗时 %v", elapsed)
	}
}

func TestRemoteSpecDefaults(t *testing.T) {
	r := &RemoteSpec{Host: "h"}
	if r.effectivePort() != 22 {
		t.Fatalf("默认端口应为 22，实际 %d", r.effectivePort())
	}
	if r.endpoint() != "h:22" {
		t.Fatalf("endpoint 应回退默认端口，实际 %q", r.endpoint())
	}
	if r.hostPart() != "h" {
		t.Fatalf("未声明 user 时 hostPart 应是 host，实际 %q", r.hostPart())
	}
	if (&RemoteSpec{Host: "h", User: "ci"}).hostPart() != "ci@h" {
		t.Fatalf("user@host 应拼接，实际 %q", (&RemoteSpec{Host: "h", User: "ci"}).hostPart())
	}
}
