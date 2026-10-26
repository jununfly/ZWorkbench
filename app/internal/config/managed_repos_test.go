package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestManagedReposPersistence(t *testing.T) {
	dir := t.TempDir()
	os.Setenv("ZW_CONFIG", filepath.Join(dir, "config.json"))
	defer os.Unsetenv("ZW_CONFIG")

	// 用 Load 取默认（空 managed repos），再写入并回读。
	c := Load()
	if len(c.ManagedRepos().Repos) != 0 {
		t.Fatalf("默认应为空 managed repos，实际 %d", len(c.ManagedRepos().Repos))
	}

	want := ManagedRepos{Repos: []RepoSpec{
		{Name: "ZWorkbench", Path: "/repo/zw", Environments: []string{"local", "container"}},
	}}
	c.SetManagedRepos(want)
	if err := c.SaveManagedRepos(); err != nil {
		t.Fatalf("SaveManagedRepos: %v", err)
	}

	// 重新 Load（同路径）应读到持久化值。
	c2 := Load()
	got := c2.ManagedRepos()
	if len(got.Repos) != 1 {
		t.Fatalf("持久化后应有 1 个仓库，实际 %d", len(got.Repos))
	}
	if got.Repos[0].Name != "ZWorkbench" || got.Repos[0].Path != "/repo/zw" {
		t.Fatalf("仓库内容不符：%#v", got.Repos[0])
	}
	if len(got.Repos[0].Environments) != 2 || got.Repos[0].Environments[1] != "container" {
		t.Fatalf("环境枚举不符：%#v", got.Repos[0].Environments)
	}
}

func TestManagedReposEnvOverride(t *testing.T) {
	dir := t.TempDir()
	os.Setenv("ZW_CONFIG", filepath.Join(dir, "config.json"))
	defer os.Unsetenv("ZW_CONFIG")

	env := `[{"name":"EnvRepo","path":"/e","environments":["local"]}]`
	os.Setenv("ZW_MANAGED_REPOS", env)
	defer os.Unsetenv("ZW_MANAGED_REPOS")

	c := Load()
	got := c.ManagedRepos()
	if len(got.Repos) != 1 || got.Repos[0].Name != "EnvRepo" {
		t.Fatalf("env 覆盖未生效：%#v", got.Repos)
	}
}

func TestManagedReposBadEnvIgnored(t *testing.T) {
	dir := t.TempDir()
	os.Setenv("ZW_CONFIG", filepath.Join(dir, "config.json"))
	defer os.Unsetenv("ZW_CONFIG")
	os.Setenv("ZW_MANAGED_REPOS", "not-json")
	defer os.Unsetenv("ZW_MANAGED_REPOS")

	// 非法 JSON 必须静默忽略，不 panic。
	c := Load()
	if c == nil {
		t.Fatal("Load 不应因坏 env 返回 nil")
	}
}

func TestNormalizedEnvironments(t *testing.T) {
	cases := []struct {
		name string
		in   []string
		want []string
	}{
		{"空回退 local", nil, []string{"local"}},
		{"全空白回退 local", []string{"", "  "}, []string{"local"}},
		{"去空白保序", []string{" local ", "container"}, []string{"local", "container"}},
		{"去重", []string{"local", "local", "container"}, []string{"local", "container"}},
	}
	for _, c := range cases {
		got := RepoSpec{Environments: c.in}.NormalizedEnvironments()
		if len(got) != len(c.want) {
			t.Fatalf("%s: 长度不符 %v vs %v", c.name, got, c.want)
		}
		for i := range got {
			if got[i] != c.want[i] {
				t.Fatalf("%s: index %d 期望 %q 实际 %q", c.name, i, c.want[i], got[i])
			}
		}
	}
}

func TestAllowsEnvironment(t *testing.T) {
	r := RepoSpec{Name: "ZW", Environments: []string{"local", "container"}}
	if !r.AllowsEnvironment("local") || !r.AllowsEnvironment("container") {
		t.Fatal("白名单内环境应被允许")
	}
	if r.AllowsEnvironment("remote:tcp://x:1") {
		t.Fatal("白名单外环境不应被允许")
	}
	if r.AllowsEnvironment("") {
		t.Fatal("空环境名不应被允许（fail-closed，默认放行由调用方决定）")
	}
	// 未声明 environments 的仓库，白名单补默认 ["local"]。
	plain := RepoSpec{Name: "Plain"}
	if !plain.AllowsEnvironment("local") {
		t.Fatal("未声明环境应回退 local 且允许")
	}
	if plain.AllowsEnvironment("container") {
		t.Fatal("未声明环境不应允许 container")
	}
}

func TestFindRepo(t *testing.T) {
	m := ManagedRepos{Repos: []RepoSpec{{Name: "ZW"}, {Name: "Other"}}}
	if r, ok := m.FindRepo(" ZW "); !ok || r.Name != "ZW" {
		t.Fatalf("应找到 ZW（容忍首尾空白），实际 %#v ok=%v", r, ok)
	}
	if _, ok := m.FindRepo("nope"); ok {
		t.Fatal("不存在的仓库不应命中")
	}
	if _, ok := m.FindRepo(""); ok {
		t.Fatal("空名不应命中")
	}
}
