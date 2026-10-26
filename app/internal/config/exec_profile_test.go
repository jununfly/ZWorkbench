package config

import (
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// 预置执行档位（ADR 0020 首刀）：一次执行只能引用档位名，不能传任意 argv。
// 校验必须 fail-closed —— 任何「看起来能跑但其实跑不了」的配置都要当场拒绝，
// 不允许静默降级成运行时错误。

func TestExecutionProfileValidate(t *testing.T) {
	base := ExecutionProfile{Name: "go-test", Command: "go", Args: []string{"test", "./..."}}

	if err := base.Validate(); err != nil {
		t.Fatalf("合法档位不应报错：%v", err)
	}

	cases := []struct {
		name string
		mut  func(*ExecutionProfile)
		want string // 期望错误里出现的片段
	}{
		{"名字为空", func(p *ExecutionProfile) { p.Name = "  " }, "name"},
		{"命令为空", func(p *ExecutionProfile) { p.Command = " " }, "command"},
		{"命令含空格", func(p *ExecutionProfile) { p.Command = "go test" }, "command"},
		{"命令含 shell 元字符", func(p *ExecutionProfile) { p.Command = "go;rm" }, "command"},
		{"命令含管道", func(p *ExecutionProfile) { p.Command = "go|cat" }, "command"},
		{"参数含换行", func(p *ExecutionProfile) { p.Args = []string{"a\nb"} }, "args"},
		{"超时为负", func(p *ExecutionProfile) { p.TimeoutSec = -1 }, "timeout_sec"},
		{"环境非 local", func(p *ExecutionProfile) { p.Environments = []string{"container"} }, "environment"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			p := base
			p.Args = append([]string(nil), base.Args...)
			p.Environments = nil
			tc.mut(&p)
			err := p.Validate()
			if err == nil {
				t.Fatalf("期望拒绝，实际通过：%#v", p)
			}
			if !strings.Contains(strings.ToLower(err.Error()), tc.want) {
				t.Fatalf("错误应含 %q，实际 %q", tc.want, err.Error())
			}
		})
	}
}

func TestExecutionProfilesValidateDuplicateName(t *testing.T) {
	m := ExecutionProfiles{Profiles: []ExecutionProfile{
		{Name: "dup", Command: "go"},
		{Name: " dup ", Command: "go"},
	}}
	if err := m.Validate(); err == nil {
		t.Fatal("重名档位必须被拒绝（名字是执行请求的唯一引用键）")
	}
}

func TestExecutionProfilesFindProfile(t *testing.T) {
	m := ExecutionProfiles{Profiles: []ExecutionProfile{
		{Name: "go-test", Command: "go"},
		{Name: "go-vet", Command: "go"},
	}}
	if p, ok := m.FindProfile(" go-test "); !ok || p.Name != "go-test" {
		t.Fatalf("应找到 go-test（容忍首尾空白），实际 %#v ok=%v", p, ok)
	}
	if _, ok := m.FindProfile("nope"); ok {
		t.Fatal("不存在的档位不应命中")
	}
	if _, ok := m.FindProfile(""); ok {
		t.Fatal("空名不应命中")
	}
}

func TestExecutionProfileEffectiveTimeout(t *testing.T) {
	cases := []struct {
		in   int
		want time.Duration
	}{
		{0, DefaultExecutionTimeout},
		{30, 30 * time.Second},
		{600, 600 * time.Second},
	}
	for _, c := range cases {
		got := ExecutionProfile{TimeoutSec: c.in}.EffectiveTimeout()
		if got != c.want {
			t.Fatalf("TimeoutSec=%d 期望 %v 实际 %v", c.in, c.want, got)
		}
	}
}

func TestExecutionProfileAllowsEnvironment(t *testing.T) {
	// 未声明 = 只允许 local（首刀只有本地执行器，不声称支持其他环境）。
	p := ExecutionProfile{Name: "x", Command: "go"}
	if !p.AllowsEnvironment("local") {
		t.Fatal("未声明环境应回退 local 且允许")
	}
	if p.AllowsEnvironment("container") {
		t.Fatal("未声明环境不应允许 container（首刀无容器执行器）")
	}
	if p.AllowsEnvironment("") {
		t.Fatal("空环境不应被允许")
	}

	// 显式声明 local 仍然只允许 local。
	q := ExecutionProfile{Name: "y", Command: "go", Environments: []string{"local"}}
	if !q.AllowsEnvironment("local") || q.AllowsEnvironment("remote:x:1") {
		t.Fatal("显式 local 档位只应允许 local")
	}
}

func TestExecutionProfileResolveDir(t *testing.T) {
	// Workdir 为空 → 用仓库路径；相对 Workdir → 相对仓库路径；绝对 Workdir → 原样。
	p := ExecutionProfile{Name: "x", Command: "go"}
	if got := p.ResolveDir("/repo/zw"); got != "/repo/zw" {
		t.Fatalf("空 workdir 应回退仓库路径，实际 %q", got)
	}

	sub := ExecutionProfile{Name: "x", Command: "go", Workdir: "app"}
	if got := sub.ResolveDir("/repo/zw"); got != filepath.Join("/repo/zw", "app") {
		t.Fatalf("相对 workdir 应拼到仓库路径，实际 %q", got)
	}

	abs := ExecutionProfile{Name: "x", Command: "go", Workdir: "/tmp/wt"}
	if got := abs.ResolveDir("/repo/zw"); got != "/tmp/wt" {
		t.Fatalf("绝对 workdir 应原样使用，实际 %q", got)
	}
}

func TestExecutionProfilesPersistence(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("ZW_CONFIG", filepath.Join(dir, "config.json"))

	c := Load()
	if len(c.ExecutionProfiles().Profiles) != 0 {
		t.Fatalf("默认应为空执行档位，实际 %d", len(c.ExecutionProfiles().Profiles))
	}

	want := ExecutionProfiles{Profiles: []ExecutionProfile{
		{Name: "go-test", Command: "go", Args: []string{"test", "./..."}, TimeoutSec: 120},
	}}
	c.SetExecutionProfiles(want)
	if err := c.SaveExecutionProfiles(); err != nil {
		t.Fatalf("SaveExecutionProfiles: %v", err)
	}

	c2 := Load()
	got := c2.ExecutionProfiles()
	if len(got.Profiles) != 1 {
		t.Fatalf("持久化后应有 1 个档位，实际 %d", len(got.Profiles))
	}
	if got.Profiles[0].Name != "go-test" || got.Profiles[0].TimeoutSec != 120 {
		t.Fatalf("档位内容不符：%#v", got.Profiles[0])
	}
	if len(got.Profiles[0].Args) != 2 || got.Profiles[0].Args[1] != "./..." {
		t.Fatalf("参数不符：%#v", got.Profiles[0].Args)
	}
}

func TestExecutionProfilesEnvOverride(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("ZW_CONFIG", filepath.Join(dir, "config.json"))
	t.Setenv("ZW_EXEC_PROFILES", `[{"name":"from-env","command":"go","args":["version"]}]`)

	c := Load()
	got := c.ExecutionProfiles()
	if len(got.Profiles) != 1 || got.Profiles[0].Name != "from-env" {
		t.Fatalf("env 覆盖未生效：%#v", got.Profiles)
	}
}

func TestExecutionProfilesBadEnvIgnored(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("ZW_CONFIG", filepath.Join(dir, "config.json"))
	t.Setenv("ZW_EXEC_PROFILES", "not-json")

	// 非法 JSON 必须静默忽略（沿用文件/默认值），不 panic。
	c := Load()
	if c == nil {
		t.Fatal("Load 不应因坏 env 返回 nil")
	}
	if got := len(c.ExecutionProfiles().Profiles); got != 0 {
		t.Fatalf("坏 env 应被忽略，实际注入 %d 个档位", got)
	}
}

func TestSaveExecutionProfilesDoesNotDropOtherSections(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("ZW_CONFIG", filepath.Join(dir, "config.json"))

	c := Load()
	c.SetManagedRepos(ManagedRepos{Repos: []RepoSpec{{Name: "ZW", Path: "/r"}}})
	c.SetExecutionProfiles(ExecutionProfiles{Profiles: []ExecutionProfile{{Name: "p", Command: "go"}}})
	if err := c.SaveExecutionProfiles(); err != nil {
		t.Fatalf("save: %v", err)
	}

	c2 := Load()
	if len(c2.ManagedRepos().Repos) != 1 {
		t.Fatal("保存执行档位不应抹掉 managed_repos 段（静默丢配置）")
	}
	if len(c2.ExecutionProfiles().Profiles) != 1 {
		t.Fatal("执行档位未持久化")
	}
}
